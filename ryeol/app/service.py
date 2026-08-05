from time import perf_counter
from fastapi import HTTPException
from taek.adapter import to_case_cards, to_consult_payload, to_law_cards
from .calculator import apply_modifiers
from .config import settings
from .llm import explain
from .schemas import ConsultRequest, ConsultResponse, FollowUpRequest, FollowUpResponse, Modifier, Ratio, RecalculateRequest, RecalculateResponse
from .sessions import sessions

def _modifiers(payload):
    return [Modifier(**item) for item in payload.get("수정요소", [])]

def consult(searcher, request: ConsultRequest):
    started = perf_counter()
    hits = searcher.search(request.사고설명, mode="hybrid", reject=True, expand=True,
                           rerank=settings.search_rerank)
    trace = [{"step": 1, "tool": "search_kb", "result": len(hits),
              "elapsed_ms": round((perf_counter()-started)*1000)}]
    payload = to_consult_payload(hits, consultant_side=request.상담자측)
    if payload.get("경고") or not payload.get("기본과실"):
        sid = sessions.save({"request": request.model_dump(), "payload": payload}, request.session_id)
        return ConsultResponse(session_id=sid, status="not_found", 경고=payload.get("경고"),
            되묻기=payload.get("되묻기", []), trace=trace, llm_mode=settings.llm_mode)
    return _complete(searcher, request, payload, trace)

def _complete(searcher, request, payload, trace):
    base = Ratio(**payload["기본과실"])
    modifiers = _modifiers(payload)
    final, applied, skipped, steps = apply_modifiers(base, modifiers, request.적용할_수정요소)
    trace.append({"step": 2, "tool": "apply_modifiers", "result": f"{base.A}:{base.B}->{final.A}:{final.B}"})
    cases = to_case_cards(searcher.cases(request.사고설명))
    laws = to_law_cards(searcher.laws_for(payload.get("법조항", [])))
    context = {"사고설명": request.사고설명, "도표번호": payload.get("도표번호"),
               "제목": payload.get("제목"), "기본과실": base.model_dump(),
               "적용_수정요소": [x.model_dump() for x in applied],
               "최종과실": final.model_dump(), "법조항": laws, "판례": payload.get("판례", [])}
    answer, warnings = explain(context)
    sid = sessions.save({"request": request.model_dump(), "payload": payload,
        "base": base.model_dump(), "final": final.model_dump(),
        "modifiers": [x.model_dump() for x in modifiers]}, request.session_id)
    sessions.append(sid, "user", request.사고설명)
    sessions.append(sid, "assistant", answer)
    return ConsultResponse(session_id=sid, status="complete", 사고유형={"설명": payload.get("제목", "")},
        도표번호=payload.get("도표번호"), 제목=payload.get("제목", ""), 출처=payload.get("출처"),
        나_역할=payload.get("나_역할"), 상대_역할=payload.get("상대_역할"), 기본과실=base,
        적용_수정요소=applied, 미적용_수정요소=skipped, 최종과실=final, 계산_단계=steps,
        답변=answer, 유사사례=cases, 판례=payload.get("판례", []), 법조항=laws,
        image_url=payload.get("image_url"), pdf_page=payload.get("pdf_page"), trace=trace,
        신뢰도="낮음" if payload.get("검수필요") else "높음", 후보=payload.get("후보", []),
        되묻기=payload.get("되묻기", []), llm_mode=settings.llm_mode, warnings=warnings)

def recalculate(request: RecalculateRequest):
    state = sessions.get(request.session_id)
    if not state or not state.get("base"):
        raise HTTPException(status_code=404, detail="상담 세션을 찾을 수 없습니다")
    base = Ratio(**state["base"])
    modifiers = [Modifier(**item) for item in state["modifiers"]]
    final, applied, skipped, steps = apply_modifiers(base, modifiers, request.적용할_수정요소)
    return RecalculateResponse(session_id=request.session_id, 기본과실=base,
        적용_수정요소=applied, 미적용_수정요소=skipped, 최종과실=final, 계산_단계=steps)

def follow_up(request: FollowUpRequest):
    state = sessions.get(request.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="상담 세션을 찾을 수 없습니다")
    context = {"기존상담": state.get("payload", {}), "최종과실": state.get("final"),
               "후속질문": request.질문, "대화이력": state.get("history", [])}
    answer, warnings = explain(context)
    sessions.append(request.session_id, "user", request.질문)
    sessions.append(request.session_id, "assistant", answer)
    return FollowUpResponse(session_id=request.session_id, 답변=answer,
                            llm_mode=settings.llm_mode, warnings=warnings)
