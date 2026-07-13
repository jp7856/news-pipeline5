"""기존 Vocab Review 탭 19행(빈 행)에 자동 실행 감시 문구 1줄 추가 (1회성)."""
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\jp\work\news-pipeline5")
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
try:
    creds = Credentials.from_service_account_info(json.loads(GOOGLE_SHEETS_CREDENTIALS_JSON), scopes=SCOPES)
except (json.JSONDecodeError, TypeError):
    creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDENTIALS_JSON, scopes=SCOPES)
ss = gspread.authorize(creds).open_by_key(GOOGLE_SHEET_ID)
ws = ss.worksheet("Vocab Review")
line = "이 리뷰는 매달 1일 자동 실행된다(Railway cron) — 이번 달 Run Log 행이 없으면 실행이 죽은 것이니 Railway 로그를 확인할 것."
cur = ws.acell("A19").value
if cur:
    print(f"[중단] A19가 비어있지 않음: {cur!r}")
else:
    ws.update(values=[[line]], range_name="A19")
    print("[OK] A19에 감시 문구 추가")
print("A17~A20:", [ws.acell(f"A{i}").value for i in range(17, 21)])
