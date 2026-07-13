"""기존 Vocab Review 탭 19행 감시 문구를 주간 문구로 갱신 (1회성)."""
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
new_line = "매주 월요일 아침에 이 시트를 열어 Run Log 최신 행부터 확인. 이번 주 행이 없으면 실행이 죽은 것이니 Railway 로그 확인."
cur = ws.acell("A19").value or ""
if "매달 1일" in cur or "Railway cron" in cur:
    ws.update(values=[[new_line]], range_name="A19")
    print(f"[OK] A19 갱신: {cur[:40]}... -> {new_line[:40]}...")
else:
    print(f"[중단] A19 내용이 예상과 다름: {cur!r}")
print("A19 현재:", ws.acell("A19").value)
