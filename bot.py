"""Ishchilar davomat boti — aiogram 3.x + Google Sheets."""

import asyncio
import logging
import os
from datetime import datetime
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

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
sheets = Sheets(CREDS_FILE, SPREADSHEET_ID)


# ------------------ Yordamchilar ------------------
def now_date() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def now_time() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")


def main_kb(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="✅ Keldi"), KeyboardButton(text="🚪 Ketdi")],
        [KeyboardButton(text="📝 Ro'yxatdan o'tish")],
    ]
    if user_id == ADMIN_ID:
        rows.append([KeyboardButton(text="👥 Ishchilar"), KeyboardButton(text="📊 Bugungi davomat")])
        rows.append([KeyboardButton(text="📢 Broadcast")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


class Reg(StatesGroup):
    ism = State()
    familiya = State()
    lavozim = State()
    telefon = State()


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


# ------------------ Keldi / Ketdi ------------------
async def mark(message: Message, status: str):
    emp = await asyncio.to_thread(sheets.get_employee, message.from_user.id)
    if not emp:
        await message.answer("Avval ro'yxatdan o'ting: 📝 Ro'yxatdan o'tish")
        return
    full_name = f"{emp.get('Ism', '')} {emp.get('Familiya', '')}".strip()
    await asyncio.to_thread(
        sheets.add_attendance, message.from_user.id, full_name, status, now_date(), now_time()
    )
    await message.answer(f"<b>{status}</b> belgilandi ✅\nVaqt: {now_time()}")


@dp.message(Command("keldi"))
@dp.message(F.text == "✅ Keldi")
async def keldi(message: Message):
    await mark(message, "Keldi")


@dp.message(Command("ketdi"))
@dp.message(F.text == "🚪 Ketdi")
async def ketdi(message: Message):
    await mark(message, "Ketdi")


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
        lines.append(f"{r.get('Vaqt', '')} — {r.get('Ism Familiya', '')}: {r.get('Holat', '')}")
    await message.answer("\n".join(lines))


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


# ------------------ Render uchun kichik web-server (uxlab qolmasligi uchun) ------------------
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
