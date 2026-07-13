"""원본 기사 시트 무변경 검증용 스냅샷 — 행 수 + 전체 내용 해시 + 탭 목록."""
import hashlib
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
src = ss.sheet1
rows = src.get_all_values()
digest = hashlib.sha256(
    json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
).hexdigest()

print(f"원본 시트: {src.title!r}  행 수: {len(rows)}")
print(f"내용 SHA256: {digest}")
print(f"탭 목록: {[w.title for w in ss.worksheets()]}")
