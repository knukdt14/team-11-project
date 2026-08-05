from time import perf_counter
from fastapi import HTTPException
from taek.adapter import to_case_cards, to_consult_payload, to_law_cards
from .calculator import apply_modifiers
from .config import settings
from .llm import explain
from .schemas import AdditionalInfoRequest, ConsultRequest, ConsultResponse, FollowUpRequest, FollowUpResponse, Modifier, Ratio, RecalculateRequest, RecalculateResponse
from .sessions import sessions

def _modifiers(payload):
    return [Modifier(**item) for item in payload.get("수정요소", [])]

def _missing_information(query: str):
    questions = []
    if "교차로" in query:
        if not any(x in query for x in ("신호", "적색", "녹색", "황색")):
            questions.append("신호등이 있는 교차로였나요? 당시 각 차량의 신호는 무엇이었나요?")
        if not any(x in query for x in ("직진", "좌회전", "우회전", "회전", "진입")):
            questions.append("본인과 상대 차량은 각각 직진·좌회전·우회전 중 무엇을 하고 있었나요?")
        if any(x in query for x in ("신호 없는", "무신호")) and not any(
                x in query for x in ("맞은편", "왼쪽", "오른쪽", "대로", "소로", "도로 폭", "폭이")):
            questions.append("상대 차량은 맞은편·왼쪽·오른쪽 중 어디에서 왔고, 어느 도로가 더 넓었나요?")
    if len(query.strip()) < 12:
        questions.append("충돌 장소, 진행 방향, 충돌 상황을 조금 더 자세히 알려주세요.")
    return list(dict.fromkeys(questions))

def _source_for_query(query: str):
    if any(x in query for x in ("킥보드", "전동킥보드", "PM", "개인형 이동장치", "씽씽이")):
        return "PM2021"
    if any(x in query for x in ("회전교차로", "로터리")):
        return "ROUND2025"
    return "MAIN2023"

def consult(searcher, request: ConsultRequest):
    started = perf_counter()
    hits = searcher.search(request.사고설명, source_id=_source_for_query(request.사고설명),
                           mode="hybrid", reject=True, expand=True,
                           rerank=settings.search_rerank)
    trace = [{"step": 1, "tool": "search_kb", "result": len(hits),
              "elapsed_ms": round((perf_counter()-started)*1000)}]
    payload = to_consult_payload(hits, consultant_side=request.상담자측)
    if payload.get("경고") or not payload.get("기본과실"):
        sid = sessions.save({"request": request.model_dump(), "payload": payload}, request.session_id)
        return ConsultResponse(session_id=sid, status="not_found", 경고=payload.get("경고"),
            되묻기=payload.get("되묻기", []), trace=trace, llm_mode=settings.llm_mode)
    questions = _missing_information(request.사고설명)
    if questions:
        sid = sessions.save({"request": request.model_dump(), "payload": payload}, request.session_id)
        return ConsultResponse(session_id=sid, status="needs_information",
            사고유형=payload.get("사고유형"), 도표번호=payload.get("도표번호"), 제목=payload.get("제목", ""),
            후보=payload.get("후보", []), 되묻기=questions, 경고="정확한 계산을 위해 추가정보가 필요합니다",
            trace=trace, llm_mode=settings.llm_mode)
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
    return ConsultResponse(session_id=sid, status="complete", 사고유형=payload.get("사고유형"),
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
    sessions.update(request.session_id, final=final.model_dump(),
                    selected_modifiers=[x.id or x.조건 for x in applied])
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

def add_information(searcher, request: AdditionalInfoRequest):
    state = sessions.get(request.session_id)
    if not state or not state.get("request"):
        raise HTTPException(status_code=404, detail="상담 세션을 찾을 수 없습니다")
    previous = state["request"]
    merged = f"{previous.get('사고설명', '')} {request.추가정보}".strip()
    return consult(searcher, ConsultRequest(사고설명=merged,
        상담자측=previous.get("상담자측", "A"), 적용할_수정요소=request.적용할_수정요소,
        session_id=request.session_id))
