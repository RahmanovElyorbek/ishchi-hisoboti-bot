# Ishchilar Davomat Boti

Telegram bot — davomat (Keldi/Ketdi), ishchilar ro'yxati, broadcast — barchasi Google Sheets bilan sinxron.

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `bot.py` | Asosiy bot (barcha tugma va buyruqlar) |
| `sheets.py` | Google Sheets bilan ishlash |
| `requirements.txt` | Kerakli kutubxonalar |
| `.env.example` | Sozlama namunasi (`.env` qilib nusxalanadi) |
| `.gitignore` | Maxfiy fayllarni GitHub'dan yashiradi |
| `render.yaml` | Render Blueprint sozlamasi |

---

## Tayyorgarlik (bir marta)

1. **Bot token** — Telegramda [@BotFather](https://t.me/BotFather) → `/newbot` → tokenni saqlang.
2. **Admin ID** — [@userinfobot](https://t.me/userinfobot) → `/start` → ID'ingizni oling.
3. **Google Sheets**:
   - [Google Cloud Console](https://console.cloud.google.com/) → yangi loyiha.
   - APIs & Services → **Google Sheets API** va **Google Drive API** ni yoqing.
   - Credentials → Create → **Service Account** → Keys → Add Key → **JSON** → faylni yuklab, papkaga `credentials.json` nomi bilan saqlang.
   - [Sheets](https://sheets.google.com/) da yangi jadval yarating. URL'dan ID'ni oling:
     `https://docs.google.com/spreadsheets/d/`**BU_YER_ID**`/edit`
   - Jadval → Share → service account emailini (`...@....iam.gserviceaccount.com`) **Editor** huquqi bilan qo'shing.

---

## Lokal ishga tushirish (Windows)

```bat
:: 1. Papkaga kiring
cd employee-bot

:: 2. Virtual muhit
python -m venv venv
venv\Scripts\activate

:: 3. Kutubxonalar
pip install -r requirements.txt

:: 4. Sozlama: .env.example dan .env yarating va to'ldiring
copy .env.example .env
notepad .env

:: 5. credentials.json shu papkada turibdimi — tekshiring

:: 6. Ishga tushirish
python bot.py
```

Telegramda botga `/start` yuboring. Tugmalar chiqsa — tayyor.

---

## GitHub'ga yuklash

```bat
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/USERNAME/employee-bot.git
git push -u origin main
```

> `.gitignore` tufayli `.env` va `credentials.json` GitHub'ga **chiqmaydi** — bu xavfsizlik uchun shart.

---

## Render'ga deploy

1. [Render](https://render.com) → New → **Web Service** → GitHub repo'ni ulang.
2. Build: `pip install -r requirements.txt` | Start: `python bot.py`
3. **Environment** bo'limida o'zgaruvchilar: `BOT_TOKEN`, `ADMIN_ID`, `SPREADSHEET_ID`, `GOOGLE_CREDENTIALS_FILE=credentials.json`
4. **Secret Files** → Add → nom: `credentials.json`, ichiga JSON faylning to'liq matnini joylang.
5. Deploy. Bepul tarif 15 daqiqa harakatsizlikdan keyin uxlaydi — [cron-job.org](https://cron-job.org) orqali har 10 daqiqada Render URL'ingizni ping qilib uyg'oq saqlang.

---

## Buyruqlar

| Buyruq | Kim uchun |
|---|---|
| `/start` | Hammaga |
| `/royxat` | Yangi ishchilar |
| `/keldi`, `/ketdi` | Ishchilar |
| `/ishchilar`, `/davomat`, `/broadcast` | Faqat admin |
| `/cancel` | Amaliyotni bekor qilish |
