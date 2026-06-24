"""Ishchilar davomat boti — aiogram 3.x + Google Sheets + geolokatsiya."""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from math import radians, sin, cos, asin, sqrt
from zoneinfo import ZoneInfo

from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

from sheets import Sheets

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TZ = ZoneInfo("Asia/Tashkent")

# ============================================================
#  FILIALLAR — bu yerga HAR BIR filialning koordinatasini yozing.
#  Koordinatani Google Maps'dan oling:
#    - Telefonda: kerakli nuqtani bosib turing -> pastda lat, lon chiqadi
#    - Kompyuterda: nuqtaga o'ng tugma -> birinchi qator (raqamlar) koordinata
#  Faqat raqamlarni almashtiring (lat = kenglik, lon = uzunlik).
# ============================================================
BRANCHES = [
    {"name": "Haqqulobod", "lat": 40.900000, "lon": 71.700000},
    {"name": "To'rtko'l", "lat": 41.550000, "lon": 61.000000},
]

# Ruxsat etilgan masofa (metr). Ishchi shu masofadan yaqin bo'lsagina belgilay oladi.
ALLOWED_RADIUS_M = int(os.getenv("ALLOWED_RADIUS_M", "700"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
sheets = Sheets(CREDS_FILE, SPREADSHEET_ID)


# ------------------ Yordamchilar ------------------
def now_date() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def now_time() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")


def distance_m(lat1, lon1, lat2, lon2) -> float:
    """Ikki nuqta orasidagi masofa (metrda) — haversine formulasi."""
    r = 6371000
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))


def nearest_branch(lat, lon):
    """Eng yaqin filial va unga masofani qaytaradi."""
    best, best_d = None, None
    for b in BRANCHES:
        d = distance_m(lat, lon, b["lat"], b["lon"])
        if best_d is None or d < best_d:
            best, best_d = b, d
    return best, best_d


def _round_arrival_hour(t):
    """Kelgan vaqtni yuqoriga yaxlit soatga (soniya hisobga olinmaydi)."""
    dt = datetime.strptime(t, "%H:%M:%S")
    return dt.hour + 1 if dt.minute >= 1 else dt.hour


def _round_departure_hour(t):
    """Ketgan vaqt: daqiqa <=40 pastga, >=41 yuqoriga yaxlitlanadi."""
    dt = datetime.strptime(t, "%H:%M:%S")
    return dt.hour + 1 if dt.minute >= 41 else dt.hour


def _is_morning(t):
    dt = datetime.strptime(t, "%H:%M:%S")
    return dt.hour < 11 or (dt.hour == 11 and dt.minute == 0)


def rounded_work_hours(keldi, ketdi):
    """Oylik uchun yaxlit ishlagan soat (butun son) yoki None."""
    if not keldi:
        return None
    try:
        a = _round_arrival_hour(keldi)
        if ketdi:
            d = _round_departure_hour(ketdi)
        else:
            d = 16 if _is_morning(keldi) else 24
    except ValueError:
        return None
    w = d - a
    return w if w >= 0 else 0


def build_report_rows(attendance, employees):
    """Davomat jurnalidan kunlik hisobot qatorlarini hosil qiladi."""
    emp_map = {str(e.get("Telegram ID")): e for e in employees}
    groups = {}
    for r in attendance:
        sana = str(r.get("Sana", "")).strip()
        tg = str(r.get("Telegram ID", "")).strip()
        vaqt = str(r.get("Vaqt", "")).strip()
        if not sana or not tg:
            continue
        g = groups.setdefault((sana, tg), {"name": "", "keldi": [], "ketdi": []})
        if r.get("Ism Familiya"):
            g["name"] = r.get("Ism Familiya")
        if r.get("Holat") == "Keldi" and vaqt:
            g["keldi"].append(vaqt)
        elif r.get("Holat") == "Ketdi" and vaqt:
            g["ketdi"].append(vaqt)

    rows = []
    for (sana, tg), g in groups.items():
        lavozim = emp_map.get(tg, {}).get("Lavozim", "")
        keldi = min(g["keldi"]) if g["keldi"] else ""
        ketdi = max(g["ketdi"]) if g["ketdi"] else ""
        worked = ""
        if keldi and ketdi:
            try:
                t1 = datetime.strptime(keldi, "%H:%M:%S")
                t2 = datetime.strptime(ketdi, "%H:%M:%S")
                diff = t2 - t1
                if diff.total_seconds() < 0:
                    diff = timedelta(0)
                total_min = int(diff.total_seconds() // 60)
                worked = f"{total_min // 60}:{total_min % 60:02d}"
            except ValueError:
                worked = ""
        yaxlit = rounded_work_hours(keldi, ketdi)
        yaxlit_txt = str(yaxlit) if yaxlit is not None else "—"
        rows.append([sana, g["name"], lavozim, keldi or "—", ketdi or "—", worked or "—", yaxlit_txt])
    rows.sort(key=lambda x: (x[0], x[1]))
    return rows


def main_kb(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="✅ Keldi"), KeyboardButton(text="🚪 Ketdi")],
        [KeyboardButton(text="📝 Ro'yxatdan o'tish")],
    ]
    if user_id == ADMIN_ID:
        rows.append([KeyboardButton(text="👥 Ishchilar"), KeyboardButton(text="📊 Bugungi davomat")])
        rows.append([KeyboardButton(text="📅 Hisobot"), KeyboardButton(text="📢 Broadcast")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def location_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True,
    )


class Reg(StatesGroup):
    ism = State()
    familiya = State()
    lavozim = State()
    telefon = State()


class Attendance(StatesGroup):
    waiting_location = State()


class Broadcast(StatesGroup):
    text = State()


# ------------------ /start va /cancel ------------------
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Assalomu alaykum! <b>Ishchilar davomat botiga</b> xush kelibsiz.\n\n"
        "Quyidagi tugmalardan foydalaning 👇",
        reply_markup=main_kb(message.from_user.id),
    )


@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_kb(message.from_user.id))


# ------------------ Ro'yxatdan o'tish ------------------
@dp.message(Command("royxat"))
@dp.message(F.text == "📝 Ro'yxatdan o'tish")
async def reg_start(message: Message, state: FSMContext):
    if await asyncio.to_thread(sheets.get_employee, message.from_user.id):
        await message.answer("Siz allaqachon ro'yxatdan o'tgansiz.")
        return
    await state.set_state(Reg.ism)
    await message.answer("Ismingizni kiriting:", reply_markup=ReplyKeyboardRemove())


@dp.message(Reg.ism)
async def reg_ism(message: Message, state: FSMContext):
    await state.update_data(ism=message.text.strip())
    await state.set_state(Reg.familiya)
    await message.answer("Familiyangizni kiriting:")


@dp.message(Reg.familiya)
async def reg_familiya(message: Message, state: FSMContext):
    await state.update_data(familiya=message.text.strip())
    await state.set_state(Reg.lavozim)
    await message.answer("Lavozimingizni kiriting:")


@dp.message(Reg.lavozim)
async def reg_lavozim(message: Message, state: FSMContext):
    await state.update_data(lavozim=message.text.strip())
    await state.set_state(Reg.telefon)
    await message.answer("Telefon raqamingizni kiriting (masalan +998901234567):")


@dp.message(Reg.telefon)
async def reg_telefon(message: Message, state: FSMContext):
    data = await state.get_data()
    await asyncio.to_thread(
        sheets.add_employee,
        message.from_user.id,
        data["ism"], data["familiya"], data["lavozim"],
        message.text.strip(), now_date(),
    )
    await state.clear()
    await message.answer(
        f"✅ Ro'yxatdan o'tdingiz!\n\n"
        f"<b>{data['ism']} {data['familiya']}</b>\n"
        f"Lavozim: {data['lavozim']}",
        reply_markup=main_kb(message.from_user.id),
    )


# ------------------ Keldi / Ketdi (lokatsiya bilan) ------------------
async def ask_location(message: Message, state: FSMContext, action: str):
    emp = await asyncio.to_thread(sheets.get_employee, message.from_user.id)
    if not emp:
        await message.answer("Avval ro'yxatdan o'ting: 📝 Ro'yxatdan o'tish")
        return
    await state.set_state(Attendance.waiting_location)
    await state.update_data(action=action)
    await message.answer(
        f"<b>{action}</b> belgilash uchun joylashuvingizni yuboring 👇\n"
        "Pastdagi «📍 Lokatsiyani yuborish» tugmasini bosing.\n\n"
        "<i>Eslatma: lokatsiya faqat telefon ilovasidan yuboriladi.</i>",
        reply_markup=location_kb(),
    )


@dp.message(Command("keldi"))
@dp.message(F.text == "✅ Keldi")
async def keldi(message: Message, state: FSMContext):
    await ask_location(message, state, "Keldi")


@dp.message(Command("ketdi"))
@dp.message(F.text == "🚪 Ketdi")
async def ketdi(message: Message, state: FSMContext):
    await ask_location(message, state, "Ketdi")


@dp.message(Attendance.waiting_location, F.location)
async def got_location(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action", "Keldi")
    await state.clear()

    lat = message.location.latitude
    lon = message.location.longitude
    branch, dist = nearest_branch(lat, lon)
    dist_r = round(dist)

    emp = await asyncio.to_thread(sheets.get_employee, message.from_user.id)
    full_name = f"{emp.get('Ism', '')} {emp.get('Familiya', '')}".strip()

    if dist <= ALLOWED_RADIUS_M:
        await asyncio.to_thread(
            sheets.add_attendance,
            message.from_user.id, full_name, action,
            branch["name"], dist_r, now_date(), now_time(),
        )
        await message.answer(
            f"✅ <b>{action}</b> belgilandi!\n"
            f"Filial: {branch['name']}\n"
            f"Masofa: {dist_r} m\n"
            f"Vaqt: {now_time()}",
            reply_markup=main_kb(message.from_user.id),
        )
    else:
        await message.answer(
            f"❌ Siz ish joyidan uzoqdasiz.\n"
            f"Eng yaqin filial: {branch['name']} — {dist_r} m.\n"
            f"Faqat {ALLOWED_RADIUS_M} m masofada belgilash mumkin.\n\n"
            "Ish joyiga yetib kelgach, qayta urinib ko'ring.",
            reply_markup=main_kb(message.from_user.id),
        )


@dp.message(Attendance.waiting_location, F.text == "❌ Bekor qilish")
async def loc_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_kb(message.from_user.id))


@dp.message(Attendance.waiting_location)
async def loc_invalid(message: Message):
    await message.answer(
        "Iltimos, «📍 Lokatsiyani yuborish» tugmasi orqali joylashuv yuboring "
        "yoki «❌ Bekor qilish» ni bosing."
    )


# ------------------ Admin: ishchilar ------------------
@dp.message(Command("ishchilar"))
@dp.message(F.text == "👥 Ishchilar")
async def ishchilar(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    emps = await asyncio.to_thread(sheets.get_employees)
    if not emps:
        await message.answer("Hozircha ishchilar yo'q.")
        return
    lines = ["<b>Ishchilar ro'yxati:</b>\n"]
    for i, e in enumerate(emps, 1):
        lines.append(
            f"{i}. {e.get('Ism', '')} {e.get('Familiya', '')} — "
            f"{e.get('Lavozim', '')} ({e.get('Telefon', '')})"
        )
    await message.answer("\n".join(lines))


# ------------------ Admin: bugungi davomat ------------------
@dp.message(Command("davomat"))
@dp.message(F.text == "📊 Bugungi davomat")
async def davomat(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    rows = await asyncio.to_thread(sheets.get_today_attendance, now_date())
    if not rows:
        await message.answer("Bugun hali hech kim belgilamagan.")
        return
    lines = [f"<b>Bugungi davomat ({now_date()}):</b>\n"]
    for r in rows:
        branch = r.get("Filial", "")
        branch_txt = f" [{branch}]" if branch else ""
        lines.append(
            f"{r.get('Vaqt', '')} — {r.get('Ism Familiya', '')}: "
            f"{r.get('Holat', '')}{branch_txt}"
        )
    await message.answer("\n".join(lines))


# ------------------ Admin: hisobot ------------------
@dp.message(Command("hisobot"))
@dp.message(F.text == "📅 Hisobot")
async def hisobot(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Hisobot tayyorlanmoqda...")
    attendance = await asyncio.to_thread(sheets.get_all_attendance)
    employees = await asyncio.to_thread(sheets.get_employees)
    rows = build_report_rows(attendance, employees)
    if not rows:
        await message.answer(
            "Hozircha davomat ma'lumotlari yo'q.",
            reply_markup=main_kb(message.from_user.id),
        )
        return
    await asyncio.to_thread(sheets.update_report, rows)
    await message.answer(
        f"✅ <b>Hisobot</b> varag'i yangilandi ({len(rows)} qator).\n"
        "Google Sheets'da «Hisobot» varag'ini oching — har bir ishchining "
        "kunlik Keldi/Ketdi vaqti va ishlagan soati ko'rinadi.",
        reply_markup=main_kb(message.from_user.id),
    )


# ------------------ Admin: broadcast ------------------
@dp.message(Command("broadcast"))
@dp.message(F.text == "📢 Broadcast")
async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(Broadcast.text)
    await message.answer(
        "Yubormoqchi bo'lgan xabaringizni kiriting (/cancel — bekor qilish):",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Broadcast.text)
async def broadcast_send(message: Message, state: FSMContext):
    await state.clear()
    emps = await asyncio.to_thread(sheets.get_employees)
    sent, failed = 0, 0
    for e in emps:
        try:
            await bot.send_message(int(e.get("Telegram ID")), message.text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(
        f"✅ Yuborildi: {sent} ta, xato: {failed} ta",
        reply_markup=main_kb(message.from_user.id),
    )


# ------------------ Render uchun kichik web-server ------------------
async def health(request):
    return web.Response(text="Bot ishlayapti ✅")


async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server {port}-portda ishga tushdi")


async def main():
    await start_web()
    logging.info("Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
