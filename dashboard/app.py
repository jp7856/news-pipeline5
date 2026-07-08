"""웹 대시보드 — 토픽 입력 → 콘텐츠 제작 파이프라인 실행 → 결과 확인."""

import sys
import threading
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, join_room

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LEVEL_CONFIG, SUBLEVEL_CONFIG, DEFAULT_SUBLEVEL
from orchestrator import Orchestrator, PipelineCancelled
from agents.worksheet import WorksheetAgent, BYLINE_AUTHORS
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


def _load_history_from_sheet():
    """앱 시작 시 구글 시트에서 히스토리를 로드한다."""
    global _history
    try:
        ws = WorksheetAgent()
        _history = ws.load_history()
        logger.info(f"히스토리 {len(_history)}건 로드 완료")
    except Exception as e:
        logger.warning(f"히스토리 로드 실패 (빈 상태로 시작): {e}")
        _history = []


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

    _running[sid] = True
    _cancel_events[sid] = threading.Event()
    thread = threading.Thread(target=_run_phase2, args=(sid, pend), daemon=True)
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

    ws = WorksheetAgent()
    if not ws.mark_published(int(sheet_row)):
        return jsonify({"error": "발행 처리에 실패했습니다. 시트 연결을 확인하세요."}), 500

    for entry in _history:
        if entry.get("result", {}).get("sheet_row") == sheet_row:
            entry["result"]["published"] = True

    return jsonify({"message": "Published"})


@app.route("/api/published")
def api_published():
    """발행된 기사만 반환 (발행 뷰어 사이트용)."""
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
    return jsonify({
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


def _run_phase2(sid: str, state: dict):
    """Phase 2 — 교정부터 검수까지 완료."""
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
