"""Google Sheets bilan ishlash uchun yordamchi modul."""

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ATT_HEADERS = ["Telegram ID", "Ism Familiya", "Holat", "Sana", "Vaqt"]
EMP_HEADERS = ["Telegram ID", "Ism", "Familiya", "Lavozim", "Telefon", "Ro'yxatdan o'tgan sana"]


class Sheets:
    def __init__(self, creds_file: str, spreadsheet_id: str):
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.sh = self.client.open_by_key(spreadsheet_id)
        self.attendance = self._ensure_ws("Davomat", ATT_HEADERS)
        self.employees = self._ensure_ws("Ishchilar", EMP_HEADERS)

    def _ensure_ws(self, title: str, headers: list):
        try:
            ws = self.sh.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=title, rows=1000, cols=len(headers))
            ws.append_row(headers)
            return ws
        if not ws.row_values(1):
            ws.append_row(headers)
        return ws

    # --- Davomat ---
    def add_attendance(self, tg_id, full_name, status, date, time):
        self.attendance.append_row([str(tg_id), full_name, status, date, time])

    def get_today_attendance(self, date):
        return [r for r in self.attendance.get_all_records() if str(r.get("Sana")) == date]

    # --- Ishchilar ---
    def add_employee(self, tg_id, ism, familiya, lavozim, telefon, date):
        self.employees.append_row([str(tg_id), ism, familiya, lavozim, telefon, date])

    def get_employee(self, tg_id):
        for r in self.employees.get_all_records():
            if str(r.get("Telegram ID")) == str(tg_id):
                return r
        return None

    def get_employees(self):
        return self.employees.get_all_records()
