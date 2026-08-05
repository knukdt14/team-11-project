from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from taek.search import Searcher
from .config import settings
from .schemas import AdditionalInfoRequest, ConsultRequest, ConsultResponse, FollowUpRequest, FollowUpResponse, RecalculateRequest, RecalculateResponse
from .service import add_information, consult, follow_up, recalculate
from .sessions import sessions

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.searcher = Searcher()
        app.state.search_error = None
    except Exception as exc:
        app.state.searcher = None
        app.state.search_error = f"{type(exc).__name__}: {exc}"
    yield

app = FastAPI(title="Team 11 과실 계산·상담 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
images = Path(__file__).resolve().parents[2] / "hani" / "data" / "images"
if images.exists():
    app.mount("/images", StaticFiles(directory=images), name="images")

@app.get("/health")
def health(request: Request):
    ready = request.app.state.searcher is not None
    return {"status": "ok" if ready else "degraded", "search_ready": ready,
            "llm_mode": settings.llm_mode, "rerank": settings.search_rerank,
            "detail": request.app.state.search_error}

@app.post("/consult", response_model=ConsultResponse)
def post_consult(body: ConsultRequest, request: Request):
    if request.app.state.searcher is None:
        raise HTTPException(status_code=503, detail=request.app.state.search_error or "검색 준비 중")
    return consult(request.app.state.searcher, body)

@app.post("/recalculate", response_model=RecalculateResponse)
def post_recalculate(body: RecalculateRequest):
    return recalculate(body)

@app.post("/follow-up", response_model=FollowUpResponse)
def post_follow_up(body: FollowUpRequest):
    return follow_up(body)

@app.post("/consult/additional-info", response_model=ConsultResponse)
def post_additional_info(body: AdditionalInfoRequest, request: Request):
    if request.app.state.searcher is None:
        raise HTTPException(status_code=503, detail=request.app.state.search_error or "검색 준비 중")
    return add_information(request.app.state.searcher, body)

@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    state = sessions.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="상담 세션을 찾을 수 없습니다")
    return {"session_id": session_id, "history": state.get("history", [])}
