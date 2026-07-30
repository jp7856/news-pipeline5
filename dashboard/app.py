"""웹 대시보드 — 토픽 입력 → 콘텐츠 제작 파이프라인 실행 → 결과 확인."""

import sys
import threading
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request, send_file
from flask_socketio import SocketIO, join_room

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LEVEL_CONFIG, SUBLEVEL_CONFIG, DEFAULT_SUBLEVEL
from orchestrator import Orchestrator, PipelineCancelled
from agents.worksheet import WorksheetAgent, BYLINE_AUTHORS
from agents.sub_agents import audio_storage
from models import ContentPackage, Level, Section

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = "news-pipeline-secret"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
socketio = SocketIO(app, cors_allowed_origins="*")


@socketio.on("register_session")
def on_register_session(data):
    """클라이언트 재연결 시 지속 세션 ID로 room에 참가 — socket.id 변경에 무관하게 이벤트 수신."""
    session_id = (data or {}).get("session_id", "")
    if session_id:
        join_room(session_id)


# sid → 현재 실행 중 여부
_running: dict[str, bool] = {}

# sid → 중단 이벤트 (Running 배지 클릭 시 set)
_cancel_events: dict[str, threading.Event] = {}

# sid → Phase 1 완료 상태 ('이후 작업 진행' 대기 중)
_pending: dict[str, dict] = {}

# 전체 히스토리 — 앱 시작 시 구글 시트에서 로드, 이후 메모리에서 관리
_history: list[dict] = []


_history_load_lock = threading.Lock()


def _load_history_from_sheet(retries: int = 3, delay: float = 5.0):
    """구글 시트에서 히스토리를 로드한다.

    이 로드가 실패하면 _history가 비고 → /api/published가 빈 배열 →
    **발행 사이트에 기사가 하나도 안 보인다.** 실제로 재배포 후 그런 일이 있었으므로
    일시적 실패(시트 API 순간 오류 등)에는 재시도한다.
    """
    global _history
    import time
    with _history_load_lock:
        for attempt in range(1, retries + 1):
            try:
                ws = WorksheetAgent()
                _history = ws.load_history()
                logger.info(f"히스토리 {len(_history)}건 로드 완료 (시도 {attempt}/{retries})")
                return
            except Exception as e:
                logger.warning(f"히스토리 로드 실패 {attempt}/{retries}: {e}")
                if attempt < retries:
                    time.sleep(delay)
        logger.error("히스토리 로드를 포기했습니다 — 사이트가 빈 상태로 보입니다. "
                     "POST /api/reload_history 로 복구하세요.")


def _ensure_history():
    """_history가 비어 있으면 한 번 더 시트에서 읽어 본다 (부팅 로드 실패 대비 안전망).

    사이트가 조용히 비어 보이는 사고를 막는 것이 목적이라, 비어 있을 때만 동작한다.
    """
    if not _history:
        _load_history_from_sheet(retries=1)


# Gunicorn/Railway 배포 시에도 앱 시작과 함께 히스토리 로드
threading.Thread(target=_load_history_from_sheet, daemon=True).start()


@app.after_request
def add_no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # 발행 뷰어 사이트(GitHub Pages)에서 API 접근 허용
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    # POST(JSON)는 단순 요청이 아니어서 프리플라이트에 Allow-Methods가 필요하다
    # — 사이트의 '이번 주 발행' 버튼(/api/issue/publish)이 이걸 쓴다.
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/health")
def api_health():
    """환경변수 설정 상태 점검 (값은 노출하지 않음)."""
    import os
    def check(name):
        v = os.getenv(name, "")
        return {"set": bool(v), "length": len(v)}
    return jsonify({
        "ANTHROPIC_API_KEY": check("ANTHROPIC_API_KEY"),
        "GOOGLE_SHEETS_CREDENTIALS_JSON": check("GOOGLE_SHEETS_CREDENTIALS_JSON"),
        "GOOGLE_SHEET_ID": check("GOOGLE_SHEET_ID"),
        "UNSPLASH_ACCESS_KEY": check("UNSPLASH_ACCESS_KEY"),
        # 주간 발행 버튼용 — 값 확인 없이 설정 여부만 보려면 이 엔드포인트를 쓴다
        "ISSUE_ADMIN_KEY": check("ISSUE_ADMIN_KEY"),
        "GH_DISPATCH_TOKEN": check("GH_DISPATCH_TOKEN"),
    })


@app.route("/")
def index():
    def short_cefr(value: str) -> str:
        # "A2 (media range A1+ to A2+)" → "A2"
        return LEVEL_CONFIG[value]["cefr"].split(" (")[0]

    levels = [
        {
            "value": lv.value,
            "label": lv.value.upper().replace("_", " "),
            "cefr": short_cefr(lv.value),
        }
        for lv in Level
    ]
    sections = [{"value": sc.value, "label": sc.value} for sc in Section]
    # 레벨 → CEFR 전체 문자열 (미리보기·결과 배지용)
    level_cefr = {lv.value: LEVEL_CONFIG[lv.value]["cefr"] for lv in Level}
    # 레벨 → 서브레벨 목록 (드롭다운·서브레벨별 CEFR 배지용)
    sublevels = {
        lv.value: [
            {"key": key, "cefr": spec["cefr"], "words": spec["word_count_range"]}
            for key, spec in SUBLEVEL_CONFIG[lv.value].items()
        ]
        for lv in Level
    }
    return render_template(
        "index.html",
        levels=levels, sections=sections,
        level_cefr=level_cefr, sublevels=sublevels, default_sublevel=DEFAULT_SUBLEVEL,
    )


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.json
    sid = data.get("sid", "")
    topic = data.get("topic", "").strip()
    level_str = data.get("level", "junior")
    section_str = data.get("section", "환경")
    source_url = data.get("source_url", "").strip()
    sub_level = data.get("sub_level", "")
    hint_keywords = data.get("hint_keywords") or []
    if not isinstance(hint_keywords, list):
        hint_keywords = []
    if sub_level not in ("L1", "L2", "L3"):
        sub_level = ""  # 미지정 → 매체 기준 레벨 범위 안에서 랜덤 배정

    if not topic and not source_url:
        return jsonify({"error": "Topic or source URL is required."}), 400
    if not topic:
        topic = source_url
    if _running.get(sid):
        return jsonify({"error": "Pipeline already running."}), 409

    try:
        level = Level(level_str)
        section = Section(section_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    _running[sid] = True
    _cancel_events[sid] = threading.Event()
    _pending.pop(sid, None)
    thread = threading.Thread(
        target=_run_phase1, args=(sid, topic, level, section, source_url, sub_level, hint_keywords), daemon=True
    )
    thread.start()
    return jsonify({"message": "Pipeline started"})


@app.route("/api/suggest-keywords", methods=["POST"])
def api_suggest_keywords():
    data = request.json or {}
    topic = data.get("topic", "").strip()
    source_url = data.get("source_url", "").strip()
    section = data.get("section", "")
    if not topic and not source_url:
        return jsonify({"error": "Topic or source URL is required."}), 400
    query = topic or source_url
    try:
        from agents.sub_agents.keyword_suggester import suggest_keywords
        keywords = suggest_keywords(query, section)
        return jsonify({"keywords": keywords})
    except Exception as e:
        logger.error(f"suggest-keywords error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/stop", methods=["POST"])
def api_stop():
    sid = (request.json or {}).get("sid", "")
    event = _cancel_events.get(sid)
    if event is not None:
        event.set()
    # Phase 1 완료 후 대기 중이면 즉시 취소 처리
    if not _running.get(sid) and sid in _pending:
        _pending.pop(sid, None)
        socketio.emit("pipeline_cancelled", {}, to=sid)
    return jsonify({"message": "Stop requested"})


@app.route("/api/continue", methods=["POST"])
def api_continue():
    sid = (request.json or {}).get("sid", "")
    if _running.get(sid):
        return jsonify({"error": "Pipeline already running."}), 409
    pend = _pending.pop(sid, None)
    if pend is None:
        return jsonify({"error": "No pending article. Generate first."}), 404

    # 자동 발행 — 대량 생산용 옵션. 기본 꺼짐(수동 발행이 디폴트),
    # 검수 승인된 기사만 발행한다(거부는 자동 발행 대상 아님).
    auto_publish = bool((request.json or {}).get("auto_publish"))

    _running[sid] = True
    _cancel_events[sid] = threading.Event()
    thread = threading.Thread(
        target=_run_phase2, args=(sid, pend, auto_publish), daemon=True
    )
    thread.start()
    return jsonify({"message": "Phase 2 started"})


@app.route("/api/revise", methods=["POST"])
def api_revise():
    """Phase 1 초안에 대해 AI 수정 지시를 실행한다."""
    data = request.json or {}
    sid = data.get("sid", "")
    instruction = data.get("instruction", "").strip()

    if not instruction:
        return jsonify({"error": "수정 지시를 입력해주세요."}), 400
    if _running.get(sid):
        return jsonify({"error": "Pipeline already running."}), 409
    if sid not in _pending:
        return jsonify({"error": "세션이 만료됐습니다. 서버가 재시작되면 초안이 사라집니다. 다시 Generate 해주세요.", "session_expired": True}), 404

    _running[sid] = True
    thread = threading.Thread(target=_run_revise, args=(sid, instruction), daemon=True)
    thread.start()
    return jsonify({"message": "Revision started"})


def _run_revise(sid: str, instruction: str):
    """에디터 입력 처리 — 수정이면 기사 갱신, 질문이면 답변만."""
    try:
        from agents.sub_agents.reviser import ReviserAgent
        state = _pending[sid]
        state.setdefault("chat", [])

        reviser = ReviserAgent(log_callback=_emit_log_for(sid))
        article, reply, changed = reviser.run(
            state["article"], instruction, state["level"],
            plagiarism_report=state.get("plagiarism_report"),
            history=state["chat"],
        )
        state["article"] = article
        state["chat"].append({"user": instruction, "assistant": reply})

        # 기사가 수정됐으면 표절 재검사 (경고 상태 갱신)
        if changed:
            producer = state.get("producer")
            if producer is not None:
                state["plagiarism_report"] = producer._plagcheck.run(article)

        socketio.emit("revise_done", {
            "reply": reply,
            "changed": changed,
            "article": {
                "title": article.title,
                "text": article.text,
                "word_count": article.word_count,
                "vocabulary": article.vocabulary,
                "sources": article.sources,
            },
            "plagiarism_passed": state["plagiarism_report"].passed,
            "level": state["level"].value,
            "section": state["section"].value,
            "sub_level": state.get("sub_level", "L2"),
        }, to=sid)
    except Exception as e:
        socketio.emit("log", {"message": f"수정 오류: {e}"}, to=sid)
        socketio.emit("revise_error", {"error": str(e)}, to=sid)
    finally:
        _running.pop(sid, None)


@app.route("/api/publish", methods=["POST"])
def api_publish():
    data = request.json or {}
    sheet_row = data.get("sheet_row")
    if not sheet_row:
        return jsonify({"error": "sheet_row is required."}), 400

    ok, audio_ok = _publish_sheet_row(int(sheet_row))
    if not ok:
        return jsonify({"error": "발행 처리에 실패했습니다. 시트 연결을 확인하세요."}), 500
    return jsonify({"message": "Published", "audio": audio_ok})


def _publish_sheet_row(sheet_row: int) -> tuple[bool, bool]:
    """시트 상태를 '발행완료'로 바꾸고 TTS 오디오를 생성한다.

    수동 발행(/api/publish)과 자동 발행(Phase 2 훅)의 공용 경로.
    사이트 노출은 _history의 published 플래그가 기준이므로 여기서 함께 세운다.
    반환: (발행 성공, 오디오 성공)
    """
    ws = WorksheetAgent()
    if not ws.mark_published(sheet_row):
        return False, False

    target = None
    for entry in _history:
        if entry.get("result", {}).get("sheet_row") == sheet_row:
            entry["result"]["published"] = True
            target = entry

    # TTS 오디오 생성 — 실패해도 발행은 그대로 진행한다 (오디오만 누락 + 로그/시트 경고)
    audio_ok = _generate_publish_audio(sheet_row, target, ws)
    return True, audio_ok


def _generate_publish_audio(sheet_row: int, entry: dict | None, ws: WorksheetAgent) -> bool:
    if entry is None:
        logger.warning(f"[TTS] {sheet_row}행 히스토리 없음 — 오디오 생성 건너뜀")
        return False
    try:
        from agents.sub_agents.tts_voice import synthesize
        from agents.sub_agents.usage_tracker import record_tts_chars

        result = entry.get("result", {})
        art = result.get("article") or {}
        text = art.get("text", "")
        if not text:
            logger.warning(f"[TTS] {sheet_row}행 본문 없음 — 오디오 생성 건너뜀")
            return False
        # 낭독 대상 = 제목 + 영어 본문 (제목 분리 후에도 낭독에는 포함 — 구기사는 빈 제목)
        title = (art.get("title") or "").strip()
        if title:
            text = f"{title}{'' if title[-1] in '.!?' else '.'}\n\n{text}"
        byline = result.get("byline") or BYLINE_AUTHORS.get(entry.get("level", ""), "")
        audio_storage.save(sheet_row, synthesize(text, byline))
        record_tts_chars(len(text))
        return True
    except Exception as e:
        logger.warning(f"[TTS] {sheet_row}행 오디오 생성 실패 (발행은 정상 진행): {e}")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws.append_warning(sheet_row, f"⚠ TTS 오디오 생성 실패 ({stamp}): {str(e)[:150]}")
        return False


@app.route("/api/audio_backfill", methods=["POST"])
def api_audio_backfill():
    """오디오 없는 발행 기사에 MP3 소급 생성 — 발행 훅과 동일 규칙.

    TTS 장애로 오디오만 누락된 발행분의 재시도 용도도 겸한다.
    한 번에 limit건(기본 5)만 처리 — 남은 건수를 보고 반복 호출한다.
    force_rows에 든 행은 기존 파일이 있어도 재생성한다 (캐스팅 변경 반영용).
    """
    body = request.json or {}
    limit = int(body.get("limit", 5))
    force_rows = {int(x) for x in body.get("force_rows", [])}
    ws = WorksheetAgent()
    generated, failed = [], []
    remaining = 0
    for entry in _history:
        r = entry.get("result", {})
        row = r.get("sheet_row")
        if not r.get("published") or not row:
            continue
        if audio_storage.exists(row) and row not in force_rows:
            continue
        if len(generated) + len(failed) >= limit:
            remaining += 1
            continue
        if _generate_publish_audio(int(row), entry, ws):
            generated.append(row)
        else:
            failed.append(row)
    return jsonify({"generated": generated, "failed": failed, "remaining": remaining})


@app.route("/api/audio/<int:article_id>.mp3")
def api_audio(article_id: int):
    """발행 기사 오디오 서빙 — conditional=True로 Range 요청(모바일 <audio> 탐색) 지원."""
    path = audio_storage.file_path(article_id)
    if not path:
        return jsonify({"error": "Not found"}), 404
    return send_file(path, mimetype="audio/mpeg", conditional=True)


# ── 주간 발행(이번 주 발행 버튼) ─────────────────────────────────────
# 발행 사이트의 '이번 주 발행' 버튼이 호출한다.
#   1) 이번 주 기사를 매체 규정 수만큼 '발행완료'로 바꿔 사이트에 노출
#   2) GitHub Actions에 PDF 빌드를 요청 (러너에 크롬이 있어 여기서 굽지 않는다)
# 규정 수량은 jp-times-paper/config.py의 MEDIA.quota와 같은 값을 유지해야 한다.
ISSUE_QUOTAS = {"kinder": 4, "kids": 6, "junior": 8, "times": 10}
ISSUE_SITE_REPO = os.getenv("SITE_REPO", "jp7856/jp-times-site5")
ISSUE_SITE_URL = os.getenv("SITE_URL", "https://jp7856.github.io/jp-times-site5")

_issue_jobs: dict[str, dict] = {}
_issue_lock = threading.Lock()


def _issue_monday(day_text: str = "") -> str:
    """기준 날짜 → 그 주 월요일(YYYY-MM-DD). 빈 값이면 오늘 기준."""
    from datetime import date, timedelta
    try:
        base = date.fromisoformat((day_text or "")[:10])
    except ValueError:
        base = date.today()
    return (base - timedelta(days=base.weekday())).isoformat()


def _issue_candidates(monday: str) -> dict[str, list[dict]]:
    """그 주(월~일) 기사를 매체별 최신순으로. 시트 저장에 성공한 기사만 발행 대상."""
    from datetime import date, timedelta
    start = date.fromisoformat(monday)
    end = start + timedelta(days=6)

    buckets: dict[str, list[dict]] = {level: [] for level in ISSUE_QUOTAS}
    for entry in _history:
        level = entry.get("level", "")
        if level not in buckets:
            continue                                   # 월간지(junior_m) 등은 주간 발행 대상 아님
        try:
            day = date.fromisoformat(entry.get("created_at", "")[:10])
        except ValueError:
            continue
        if not (start <= day <= end):
            continue
        result = entry.get("result") or {}
        if not result.get("sheet_row"):
            continue                                   # 시트에 없으면 발행 상태를 세울 수 없다
        buckets[level].append(entry)
    for level in buckets:
        buckets[level].sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return buckets


def _dispatch_pdf_build(week: str) -> tuple[bool, str]:
    """GitHub Actions(build-issue)에 PDF 빌드 요청."""
    import requests
    token = os.getenv("GH_DISPATCH_TOKEN", "").strip()
    if not token:
        return False, "GH_DISPATCH_TOKEN 미설정 — PDF 빌드를 요청할 수 없습니다"
    try:
        res = requests.post(
            f"https://api.github.com/repos/{ISSUE_SITE_REPO}/dispatches",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json"},
            json={"event_type": "build-issue", "client_payload": {"week": week}},
            timeout=20)
    except Exception as e:                              # 네트워크 실패는 발행 자체를 되돌리지 않는다
        return False, f"요청 실패: {e}"
    if res.status_code == 204:
        return True, "PDF 빌드를 요청했습니다"
    return False, f"GitHub 응답 {res.status_code}: {res.text[:200]}"


def _run_issue_job(job_id: str, monday: str, build_pdf: bool) -> None:
    """백그라운드 — 기사별 발행(시트 + TTS)은 건당 수 초라 요청 안에서 처리하면 타임아웃 난다."""
    job = _issue_jobs[job_id]
    buckets = _issue_candidates(monday)
    job["total"] = sum(
        max(0, min(ISSUE_QUOTAS[lv], len(items))
            - len([e for e in items if e.get("result", {}).get("published")]))
        for lv, items in buckets.items()
    )

    for level, quota in ISSUE_QUOTAS.items():
        items = buckets[level]
        already = [e for e in items if e.get("result", {}).get("published")]
        pending = [e for e in items if not e.get("result", {}).get("published")]
        need = max(0, quota - len(already))
        picked = pending[:need]

        published_now, failed = 0, 0
        for entry in picked:
            row = entry["result"]["sheet_row"]
            try:
                ok, _audio = _publish_sheet_row(int(row))
            except Exception:
                logger.exception("주간 발행 실패 — sheet_row=%s", row)
                ok = False
            published_now += 1 if ok else 0
            failed += 0 if ok else 1
            with _issue_lock:
                job["done"] = job.get("done", 0) + 1

        with _issue_lock:
            job["media"][level] = {
                "quota": quota, "found": len(items),
                "already": len(already), "published_now": published_now,
                "failed": failed, "total_published": len(already) + published_now,
                "short": max(0, quota - (len(already) + published_now)),
            }

    if build_pdf:
        ok, message = _dispatch_pdf_build(monday)
        with _issue_lock:
            job["build_dispatched"] = ok
            job["build_message"] = message
    with _issue_lock:
        job["state"] = "done"
        job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@app.route("/api/issue/publish", methods=["POST"])
def api_issue_publish():
    """이번 주 발행 — 매체 규정 수만큼 사이트 노출 + PDF 빌드 요청."""
    import hmac
    data = request.json or {}
    expected = os.getenv("ISSUE_ADMIN_KEY", "").strip()
    if not expected:
        return jsonify({"error": "서버에 ISSUE_ADMIN_KEY가 설정되지 않았습니다."}), 503
    if not hmac.compare_digest((data.get("admin_key") or "").strip(), expected):
        return jsonify({"error": "관리자 키가 올바르지 않습니다."}), 403

    _ensure_history()
    monday = _issue_monday(data.get("week", ""))
    build_pdf = bool(data.get("build_pdf", True))

    with _issue_lock:
        running = [j for j in _issue_jobs.values() if j.get("state") == "running"]
        if running:
            return jsonify({"error": "이미 발행이 진행 중입니다.",
                            "job_id": running[0]["job_id"]}), 409
        job_id = f"issue-{monday}-{datetime.now().strftime('%H%M%S')}"
        _issue_jobs[job_id] = {
            "job_id": job_id, "state": "running", "week": monday,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "media": {}, "done": 0, "total": 0,
            "build_dispatched": None, "build_message": "",
            "site_url": f"{ISSUE_SITE_URL}/#issue-{monday}",
        }

    threading.Thread(target=_run_issue_job, args=(job_id, monday, build_pdf),
                     daemon=True).start()
    return jsonify(_issue_jobs[job_id]), 202


@app.route("/api/issue/status/<job_id>")
def api_issue_status(job_id):
    job = _issue_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Not found"}), 404
    return jsonify(job)


@app.route("/api/issue/preview")
def api_issue_preview():
    """버튼을 누르기 전 확인용 — 이번 주 매체별 기사 수와 발행 예정 수(키 불필요, 읽기 전용)."""
    _ensure_history()
    monday = _issue_monday(request.args.get("week", ""))
    buckets = _issue_candidates(monday)
    preview = {}
    for level, quota in ISSUE_QUOTAS.items():
        items = buckets[level]
        already = len([e for e in items if e.get("result", {}).get("published")])
        preview[level] = {
            "quota": quota, "found": len(items), "already": already,
            "will_publish": max(0, min(quota, len(items)) - already),
            "short": max(0, quota - len(items)),
        }
    return jsonify({"week": monday, "media": preview})


@app.route("/api/published")
def api_published():
    """발행된 기사만 반환 (발행 뷰어 사이트용)."""
    _ensure_history()                                  # 부팅 로드 실패 시 사이트가 비지 않게
    published = [
        {
            "created_at": e["created_at"],
            "topic": e["topic"],
            "level": e["level"],
            "section": e["section"],
            "article": e["result"]["article"],
            "image_url": e["result"].get("image_url", ""),
            "byline": e["result"].get("byline", ""),  # On Air 필자 (빈 값이면 프론트 폴백)
            "sub_level": e["result"].get("sub_level", ""),  # GA4 article_view 파라미터용
            # 오디오 파일이 있을 때만 경로 — 사이트는 API_BASE + audio_url (없으면 Web Speech 폴백)
            "audio_url": audio_storage.url_path(e["result"].get("sheet_row", 0)),
        }
        for e in _history
        if e.get("result", {}).get("published")
    ]
    return jsonify(published)


@app.route("/api/usage")
def api_usage():
    """월별 사용액 — 매월 1일 초기화 기준 누적."""
    monthly_krw: dict[str, float] = defaultdict(float)
    monthly_cnt: dict[str, int] = defaultdict(int)
    for e in _history:
        ym = (e.get("created_at") or "")[:7]  # "YYYY-MM"
        if ym:
            monthly_krw[ym] += e.get("cost_krw") or 0
            monthly_cnt[ym] += 1
    current_month = datetime.now().strftime("%Y-%m")
    months_sorted = sorted(monthly_krw.keys())
    from agents.sub_agents.usage_tracker import tts_usage, USD_TO_KRW
    from config import MONTHLY_BUDGET_USD
    # 월 예산 — 표시용 기준선(강제 차단 아님). 원화 환산은 USD_TO_KRW 단일 기준.
    budget_krw = round(MONTHLY_BUDGET_USD * USD_TO_KRW)
    used_krw = int(monthly_krw.get(current_month, 0))
    return jsonify({
        "budget": {
            "usd": MONTHLY_BUDGET_USD,
            "krw": budget_krw,
            "used_pct": round(used_krw / budget_krw * 100, 1) if budget_krw else 0,
            "remaining_krw": budget_krw - used_krw,
        },
        # TTS 월 누계 — 무료 한도(100만 자/월) 대비 % + 볼륨 사용량(연 2.4GB 페이스 확인용)
        "tts": {
            **tts_usage(),
            "volume_mb": round(audio_storage.total_bytes() / 1_048_576, 1),
        },
        "total_krw": int(sum(monthly_krw.values())),
        "count": len(_history),
        "current_month": current_month,
        "current_month_krw": int(monthly_krw.get(current_month, 0)),
        "current_month_count": monthly_cnt.get(current_month, 0),
        "monthly": [
            {"month": m, "krw": int(monthly_krw[m]), "count": monthly_cnt[m]}
            for m in months_sorted
        ],
    })


@app.route("/api/reload_history", methods=["POST"])
def api_reload_history():
    """시트에서 히스토리를 다시 읽는다 (재배포 없이 갱신).

    배치 스크립트처럼 **별도 프로세스**가 시트에 기사를 쓰면 이 앱의 _history에는
    없으므로 발행(사이트 노출 = published 플래그)이 불가능하다. 그 간극을 메운다.
    발행 상태는 시트의 상태 컬럼이 원본이므로 재읽기로 유실되지 않는다.
    """
    before = len(_history)
    _load_history_from_sheet()
    return jsonify({"before": before, "after": len(_history)})


@app.route("/api/history")
def api_history():
    return jsonify(_history)


@app.route("/api/history/<int:idx>")
def api_history_item(idx):
    if idx < 0 or idx >= len(_history):
        return jsonify({"error": "Not found"}), 404
    return jsonify(_history[idx])


def _emit_log_for(sid: str):
    def emit_log(msg: str):
        socketio.emit("log", {"message": msg}, to=sid)
    return emit_log


def _run_phase1(sid: str, topic: str, level: Level, section: Section, source_url: str = "", sub_level: str = "", hint_keywords: list | None = None):
    """Phase 1 — 기사 초안 생성 후 미리보기 전송, 사용자 확인 대기."""
    try:
        orchestrator = Orchestrator(
            log_callback=_emit_log_for(sid), cancel_event=_cancel_events.get(sid)
        )
        state = orchestrator.run_phase1(topic, level, section, source_url=source_url, sub_level=sub_level, hint_keywords=hint_keywords or [])
        state["orchestrator"] = orchestrator

        _pending[sid] = state
        article = state["article"]
        socketio.emit("article_ready", {
            "article": {
                "title": article.title,
                "text": article.text,
                "word_count": article.word_count,
                "vocabulary": article.vocabulary,
                "sources": article.sources,
            },
            "plagiarism_passed": state["plagiarism_report"].passed,
            "topic": topic,
            "level": level.value,
            "section": section.value,
            "sub_level": state.get("sub_level", ""),  # 랜덤 배정된 값
            "unmet_gates": getattr(article, "phase1_unmet", []) or [],
            "revision_history": getattr(article, "revision_history", ""),
        }, to=sid)
    except PipelineCancelled:
        socketio.emit("log", {"message": "=== 사용자에 의해 중단됨 ==="}, to=sid)
        socketio.emit("pipeline_cancelled", {}, to=sid)
    except Exception as e:
        socketio.emit("log", {"message": f"FATAL ERROR: {e}"}, to=sid)
        socketio.emit("pipeline_error", {"error": str(e)}, to=sid)
    finally:
        _running.pop(sid, None)


def _auto_publish(review, result: dict, log) -> bool:
    """자동 발행 훅 — 검수 승인 + 시트 행이 있는 기사만 발행한다.

    발행 실패는 기사 생성을 되돌리지 않는다(생성은 이미 끝난 상태) —
    로그만 남기고 False를 반환해 사람이 수동 발행할 수 있게 한다.
    """
    row = result.get("sheet_row")
    if review is None or not review.passed:
        log("[자동발행] 건너뜀 — 검수 승인되지 않은 기사는 발행하지 않습니다")
        return False
    if not row:
        log("[자동발행] 건너뜀 — 시트 저장이 안 돼 발행할 행이 없습니다")
        return False
    try:
        ok, audio_ok = _publish_sheet_row(int(row))
    except Exception as e:
        logger.error(f"auto-publish error: {e}")
        log(f"[자동발행] 실패 ({e}) — 수동 발행이 필요합니다")
        return False
    if not ok:
        log("[자동발행] 실패 — 시트 상태 갱신 불가. 수동 발행이 필요합니다")
        return False
    result["published"] = True
    log("[자동발행] 발행 완료 — 사이트 노출됨" + (
        "" if audio_ok else " (TTS 오디오 실패 — 사이트는 브라우저 음성으로 폴백)"))
    return True


def _run_phase2(sid: str, state: dict, auto_publish: bool = False):
    """Phase 2 — 교정부터 검수까지 완료 (auto_publish면 검수 승인 시 발행까지)."""
    try:
        orchestrator: Orchestrator = state["orchestrator"]
        orchestrator._cancel_event = _cancel_events.get(sid)
        # 기존 기사들이 쓴 이미지를 제외 목록으로 전달 (같은 주제 매체별 이미지 중복 방지)
        orchestrator.used_image_urls = [
            e.get("result", {}).get("image_url", "") for e in _history
        ]
        pkg, sheet_url = orchestrator.run_phase2(state)
        result = _serialize(pkg, sheet_url)
        result["sheet_row"] = getattr(orchestrator, "sheet_row", None)
        result["published"] = False

        entry = {
            "idx": len(_history),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "topic": state["topic"],
            "level": state["level"].value,
            "section": state["section"].value,
            "cost_krw": getattr(orchestrator, "cost_krw", 0),
            "result": result,
        }
        _history.append(entry)

        # ── 자동 발행 훅 (기본 꺼짐) ────────────────────────────────
        # 검수 승인 + 시트 저장 성공한 기사만 발행한다. 실패해도 기사 생성은
        # 이미 끝난 상태이므로 로그만 남기고 파이프라인은 정상 종료시킨다.
        if auto_publish:
            _auto_publish(pkg.review_result, result, _emit_log_for(sid))

        socketio.emit("pipeline_done", {"result": result}, to=sid)
    except PipelineCancelled:
        socketio.emit("log", {"message": "=== 사용자에 의해 중단됨 ==="}, to=sid)
        socketio.emit("pipeline_cancelled", {}, to=sid)
    except Exception as e:
        socketio.emit("log", {"message": f"FATAL ERROR: {e}"}, to=sid)
        socketio.emit("pipeline_error", {"error": str(e)}, to=sid)
    finally:
        _running.pop(sid, None)


def _serialize(pkg: ContentPackage, sheet_url: str = "") -> dict:
    review = pkg.review_result
    return {
        "topic": pkg.topic,
        "level": pkg.level.value,
        "section": pkg.section.value,
        "sub_level": pkg.sub_level,
        "article": {
            "title": pkg.article.title,
            "text": pkg.article.text,
            "text_ko": pkg.article.text_ko,
            "summary_ko": pkg.article.summary_ko,
            "word_count": pkg.article.word_count,
            "vocabulary": pkg.article.vocabulary,
            "sources": pkg.article.sources,
        },
        "plagiarism": {
            "passed": pkg.plagiarism_report.passed,
            "checklist": pkg.plagiarism_report.checklist,
            "notes": pkg.plagiarism_report.notes,
        },
        "editing": [
            {"original": s.original, "suggestion": s.suggestion, "reason": s.reason}
            for s in pkg.editing_suggestions
        ],
        "crossword": [
            {
                "word": c.word,
                "korean_definition": c.korean_definition,
                "sentence_b1": c.sentence_b1,
                "sentence_b1_b2": c.sentence_b1_b2,
            }
            for c in pkg.crossword_sentences
        ],
        "workbook": [
            {
                "set_number": w.set_number,
                "vocabulary_activity": w.vocabulary_activity,
                "true_false": w.true_false,
                "comprehension_questions": w.comprehension_questions,
                "discussion_questions": w.discussion_questions,
            }
            for w in pkg.workbook_sets
        ],
        "image_url": pkg.image_url,
        "image_candidates": pkg.image_candidates,
        "byline": BYLINE_AUTHORS.get(pkg.level.value, ""),
        "sheet_url": sheet_url,
        "review": {
            "passed": review.passed,
            "status": review.status.value,
            "notes": review.notes,
            "warnings": review.warnings,
        } if review else None,
    }


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
