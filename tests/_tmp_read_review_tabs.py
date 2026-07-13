"""Vocab Review / Run Log 탭 실물 내용 읽기 (보고용, 읽기 전용)."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")

import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds_val = GOOGLE_SHEETS_CREDENTIALS_JSON
try:
    creds = Credentials.from_service_account_info(json.loads(creds_val), scopes=SCOPES)
except (json.JSONDecodeError, TypeError):
    creds = Credentials.from_service_account_file(creds_val, scopes=SCOPES)

ss = gspread.authorize(creds).open_by_key(GOOGLE_SHEET_ID)

for title in ("Vocab Review", "Run Log"):
    ws = ss.worksheet(title)
    print(f"===== {title} (frozen rows: {ws.frozen_row_count}) =====")
    for i, row in enumerate(ws.get_all_values(), 1):
        line = " | ".join(c for c in row if c.strip())
        if line:
            print(f"{i:>3}: {line}")
    print()

# 확인 위치 셀의 수식(HYPERLINK) 원문도 확인
vr = ss.worksheet("Vocab Review")
formulas = vr.get(f"K21:K{vr.row_count}", value_render_option="FORMULA")
print("확인 위치 수식 원문:", formulas)
