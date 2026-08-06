"""
상담 페이지 — 4번(전승우) 개인 핵심 기능의 중심 화면.

레이아웃은 KNIA 과실비율 정보포털(accident.knia.or.kr)의 도표 페이지 구성을 참고했습니다:
경로/표제 → [사고 상황 / 적용요소 / 기본과실 해설] 탭 → 법규 → 판례.
차이점: KNIA 원본은 수정요소가 정적 테이블(클릭 불가)이지만, 여기서는 토글하면
즉시 재계산됩니다 — 이게 이 프로젝트의 핵심 차별점입니다(README §3-②).

    입력 → 경로/표제 → 사고상황·적용요소(비율 히어로+게이지)·해설 탭 → 법규·판례
    → 대화형 후속 질문

⚠️ 3번(정우렬)의 실제 백엔드(`ryeol/app/`)와 세션 기반으로 통합돼 있습니다
   (`components/api.py` 참고). 백엔드가 꺼져 있으면 자동으로 로컬 폴백(hani/taek 직접
   호출)으로 동작합니다 — 이때는 "답변"(LLM 설명문)이 정형 문구로 대체되고, 되묻기
   판단 로직(`_missing_information`)도 없어 "complete" 아니면 "not_found"만 냅니다.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from woo.components.api import additional_info, consult, follow_up_chat, recalculate  # noqa: E402
from woo.components.react_gauge import react_fault_gauge  # noqa: E402
from woo.components.widgets import (  # noqa: E402
    confidence_badge,
    consult_report_text,
    disclaimer,
    follow_up_chips,
    hero,
    inject_css,
    ratio_hero,
    top_nav,
)

st.set_page_config(page_title="상담 · 과실비율", page_icon="💬", layout="wide")
inject_css()
top_nav("consult")
# 홈·지식베이스 페이지와 같은 큰 그라데이션 제목 박스로 통일 (예전엔 이 페이지만 작은 텍스트였음).
hero("💬 과실비율 상담", "사고 상황을 편하게 말씀해 주세요. 채팅하듯 입력하시면 됩니다.")

st.session_state.setdefault("consult_result", None)
st.session_state.setdefault("applied_mods", set())  # 수정요소 id(str) 집합
st.session_state.setdefault("consultant_side", "A")
st.session_state.setdefault("chat_history", [])
st.session_state.setdefault("history", [])

# ⚠️ "↔ 반대쪽이에요" 버튼은 st.radio(key="consultant_side")가 이미 이번 실행에서
# 그려진 "뒤에" 그 값을 바꾸려고 해서 StreamlitAPIException이 났었습니다("위젯이 이미
# 만들어진 뒤엔 그 key를 코드로 못 바꾼다"는 Streamlit 규칙). 그래서 즉시 바꾸는 대신
# "다음 실행에서 바꿔달라"는 예약만 해두고, 라디오 위젯을 그리기 "전"인 지금 여기서
# 반영합니다.
if "_pending_side" in st.session_state:
    st.session_state["consultant_side"] = st.session_state.pop("_pending_side")

# ── 사이드바: 상담 히스토리 ────────────────────────────────────────
with st.sidebar:
    st.divider()
    hist_title, hist_clear = st.columns([3, 1])
    hist_title.markdown("**🕘 이전 상담 내역**")
    if st.session_state["history"] and hist_clear.button("🗑️", key="clear_all_history", help="전체 삭제"):
        st.session_state["history"] = []
        st.rerun()

    if not st.session_state["history"]:
        st.caption("아직 상담 기록이 없어요.")
    for h in reversed(st.session_state["history"]):
        hid = h["id"]
        row_label, row_del = st.columns([5, 1])
        label = f"{h['도표번호'] or '?'} · {h['질문'][:16]}{'…' if len(h['질문']) > 16 else ''}"
        if row_label.button(label, key=f"hist_{hid}", use_container_width=True):
            st.session_state["consult_result"] = h["result"]
            st.session_state["applied_mods"] = set()
            st.session_state["chat_history"] = [("user", h["질문"])]
            st.rerun()
        if row_del.button("✕", key=f"hist_del_{hid}", help="이 기록 삭제"):
            st.session_state["history"] = [x for x in st.session_state["history"] if x["id"] != hid]
            st.rerun()

# ── 1. 입력 ──────────────────────────────────────────────────────
# ⚠️ key 없이 value=session_state.pop(...) 을 매번 새로 계산하면, 다음 rerun에서
#    value가 바뀌어(pop이라 두 번째부턴 "") Streamlit이 "다른 위젯"으로 취급해
#    입력을 리셋해버립니다 — 홈 화면 예시 클릭 후 '상담 시작'이 안 먹던 원인이었습니다.
#    고정 key로 위젯 정체성을 안정시키고, prefill은 session_state 초기화에만 반영합니다.
if "query_input" not in st.session_state:
    st.session_state["query_input"] = st.session_state.pop("prefill_query", "")

with st.container(border=True):
    query = st.text_area(
        "🚗 사고 상황을 설명해 주세요",
        key="query_input",
        placeholder="예) 신호 없는 교차로에서 직진하다 좌회전하던 차와 부딪혔어요",
        height=90,
        label_visibility="visible",
    )

    col_side, col_btn = st.columns([2, 1])
    with col_side:
        side_label = {"A": "A 쪽", "B": "B 쪽"}
        consultant_side = st.radio(
            "본인이 어느 쪽인지 아직 모르면 우선 A로 시작하세요 (검색 후 안내 문구로 다시 확인)",
            options=["A", "B"],
            format_func=lambda s: side_label[s],
            horizontal=True,
            key="consultant_side",
        )
    with col_btn:
        st.write("")
        st.write("")
        run = st.button("🔍 상담 시작", type="primary", use_container_width=True)

if run and query.strip():
    with st.spinner("근거를 찾는 중... (처음 실행이면 모델 준비로 조금 걸릴 수 있어요)"):
        new_result = consult(query.strip(), consultant_side)
        st.session_state["consult_result"] = new_result
        st.session_state["applied_mods"] = set()
        st.session_state["chat_history"] = [("user", query.strip())]
        if new_result.get("status") == "complete":
            st.session_state["history"].append(
                {
                    "id": str(uuid.uuid4()),
                    "질문": query.strip(),
                    "도표번호": new_result.get("도표번호", ""),
                    "result": new_result,
                }
            )
            st.session_state["history"] = st.session_state["history"][-15:]

result = st.session_state["consult_result"]

# ── 2. 결과 ──────────────────────────────────────────────────────
if result is None:
    st.info("👆 위에 사고 상황을 입력하고 '상담 시작'을 눌러주세요.")
    disclaimer()
    st.stop()

status = result.get("status", "complete")

if status == "not_found":
    st.error(f"⚠️ {result.get('경고', '해당 기준을 찾을 수 없습니다')}")
    clicked = follow_up_chips(result.get("되묻기", []), key_prefix="notfound")
    if clicked:
        with st.spinner("다시 찾는 중..."):
            st.session_state["consult_result"] = additional_info(result, clicked)
            st.session_state["applied_mods"] = set()
        st.rerun()
    disclaimer()
    st.stop()

if status == "needs_information":
    if result.get("도표번호"):
        st.info(f"🔎 지금까지 찾은 기준: **{result.get('도표번호')} {result.get('제목', '')}** — 조금만 더 알려주시면 정확히 계산해드려요.")
    else:
        st.info("🔎 조금만 더 알려주시면 정확히 계산해드려요.")
    clicked = follow_up_chips(result.get("되묻기", []), key_prefix="needinfo")
    if clicked:
        with st.spinner("반영해서 다시 계산하는 중..."):
            st.session_state["consult_result"] = additional_info(result, clicked)
            st.session_state["applied_mods"] = set()
        st.rerun()
    with st.expander("🔎 지금까지 찾은 비슷한 기준 더 보기"):
        for s in result.get("후보", []):
            st.markdown(f"- **{s.get('도표번호')}** {s.get('제목', '')}")
    disclaimer()
    st.stop()

기본과실 = result["기본과실"]
수정요소 = result["수정요소"]

# ── 2-1. 경로 · 표제 (KNIA 인정기준 페이지 스타일) ────────────────
top_title, top_reset = st.columns([5, 1])
with top_title:
    유형 = result.get("사고유형") or {}
    breadcrumb = " › ".join(
        p for p in [유형.get("대", ""), result.get("출처", ""), result.get("도표번호", "")] if p
    )
    st.caption(breadcrumb or "인정기준")
with top_reset:
    if st.button("🔄 처음부터", use_container_width=True):
        for k in ("consult_result", "applied_mods", "chat_history"):
            st.session_state.pop(k, None)
        st.rerun()

badge_html = confidence_badge(result.get("신뢰도", "낮음"))
st.markdown(
    f"### {result.get('도표번호', '')} — {result.get('제목', '')} {badge_html}",
    unsafe_allow_html=True,
)
guide_col, switch_col = st.columns([5, 1])
with guide_col:
    # ⚠️ 특히 차대차처럼 나_역할/상대_역할이 둘 다 같은 도표에서는 이 문구가
    # "내가 어느 쪽인지" 구분할 유일한 단서입니다 — 꼭 확인하도록 눈에 띄게 표시.
    st.info(f"**{result.get('안내문', '')}**", icon="🧭")
with switch_col:
    other_side = "B" if consultant_side == "A" else "A"
    if st.button(f"↔ 반대쪽({other_side})이에요", use_container_width=True):
        with st.spinner("다시 계산하는 중..."):
            st.session_state["consult_result"] = consult(result["질문"], other_side)
            st.session_state["applied_mods"] = set()
            st.session_state["_pending_side"] = other_side  # 다음 실행 맨 위에서 반영됨
        st.rerun()

if not result.get("백엔드_사용", False):
    st.caption("🔧 로컬 검색 모드 결과입니다 (백엔드 미연결)")

# ── 2-2. 탭: 사고 상황 / 적용요소 / 기본과실 해설 ─────────────────
tab_scene, tab_apply, tab_expl = st.tabs(["🖼 사고 상황", "✅ 적용요소", "📖 기본과실 해설"])

with tab_scene:
    with st.container(border=True):
        image_shown = False
        if result.get("image_path"):
            # 로컬 폴백: image_path는 hani/data/ 기준 상대경로 (예: images/MAIN2023-차15.png)
            img_path = Path(__file__).resolve().parent.parent.parent / "hani" / "data" / result["image_path"]
            if img_path.exists():
                st.image(
                    str(img_path), caption=f"{result.get('도표번호', '')} · p.{result.get('pdf_page', '?')}"
                )
                image_shown = True
        elif result.get("image_url"):
            # 실제 백엔드: StaticFiles가 /images 로 서빙하는 URL
            from woo.components.api import BACKEND_URL

            st.image(
                f"{BACKEND_URL}{result['image_url']}",
                caption=f"{result.get('도표번호', '')} · p.{result.get('pdf_page', '?')}",
            )
            image_shown = True
        if result.get("사고상황"):
            st.markdown(result["사고상황"])
        if not image_shown and not result.get("사고상황"):
            st.caption("이 기준에는 사고 상황 설명/이미지가 없습니다.")

with tab_apply:
    # KNIA 원본은 수정요소가 클릭 불가한 정적 테이블이지만,
    # 우리는 토글하면 바로 재계산되는 것이 이 프로젝트의 핵심 차별점입니다(README §3-②).
    #
    # ⚠️ 실행 순서와 화면(시각적) 순서가 다릅니다. 결과 요약(비율 박스+게이지)을
    # 화면에서는 맨 위에 보여달라는 요청이 있었지만, 그 값은 "이번 rerun에서 토글이
    # 전부 반영된 뒤" recalculate()로 계산해야 합니다(먼저 계산하면 방금 누른 토글이
    # 아니라 한 번 전 상태를 보여주는 버그가 남). 그래서 자리(container)만 위에 먼저
    # 잡아두고, 토글을 그린 뒤 recalculate() 결과로 그 자리를 채우는 순서로 씁니다.
    summary_placeholder = st.container()

    col_a, col_b = st.columns(2)
    with col_a, st.container(border=True):
        st.markdown(f"**🚙 나({result.get('나_역할', 'A')}) 가감요소**")
        target_a = [m for m in 수정요소 if m["대상"] == "A"]
        if not target_a:
            st.caption("해당 없음")
        for m in target_a:
            on = st.toggle(
                f"{m['조건']} ({'+' if m['값'] >= 0 else ''}{m['값']})",
                value=m["id"] in st.session_state["applied_mods"],
                key=f"mod_{m['id']}",
                help=m.get("근거") or None,
            )
            if on:
                st.session_state["applied_mods"].add(m["id"])
            else:
                st.session_state["applied_mods"].discard(m["id"])
    with col_b, st.container(border=True):
        st.markdown(f"**🚗 상대({result.get('상대_역할', 'B')}) 가감요소**")
        target_b = [m for m in 수정요소 if m["대상"] == "B"]
        if not target_b:
            st.caption("해당 없음")
        for m in target_b:
            on = st.toggle(
                f"{m['조건']} ({'+' if m['값'] >= 0 else ''}{m['값']})",
                value=m["id"] in st.session_state["applied_mods"],
                key=f"mod_{m['id']}",
                help=m.get("근거") or None,
            )
            if on:
                st.session_state["applied_mods"].add(m["id"])
            else:
                st.session_state["applied_mods"].discard(m["id"])

    # 토글이 전부 반영된 뒤에 딱 한 번 계산 — 이 값을 아래 화면 전체와 탭 밖(법규·판례 등)에서도 씁니다.
    최종과실, 계산_단계 = recalculate(result, st.session_state["applied_mods"])

    # 위에서 미리 잡아둔 자리(summary_placeholder)를 이제 채웁니다 — 화면에는 토글보다
    # "위"에 보이지만, 계산 자체는 토글이 다 반영된 뒤에 이뤄집니다.
    with summary_placeholder:
        with st.container(border=True):
            st.markdown(
                ratio_hero(
                    최종과실["A"], 최종과실["B"], result.get("나_역할", "나"), result.get("상대_역할", "상대")
                ),
                unsafe_allow_html=True,
            )
            st.caption("기본과실 → 아래 수정요소를 켜면 이 숫자가 즉시 바뀝니다 (재검색 없음)")

            applied_names = [m["조건"] for m in 수정요소 if m["id"] in st.session_state["applied_mods"]]
            report = consult_report_text(result, 최종과실, applied_names)
            st.download_button(
                "📥 이 결과 리포트 다운로드",
                data=report.encode("utf-8"),
                file_name=f"과실비율_{result.get('도표번호', 'result')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        st.write("")
        g_left, g_center, g_right = st.columns([1, 2, 1])
        with g_center:
            # plotly 워터폴은 제거 — 토글할 때마다 부드럽게 움직이는 이 게이지 하나로 충분하다는 피드백 반영.
            react_fault_gauge(
                최종과실["A"], 최종과실["B"], result.get("나_역할", "나"), result.get("상대_역할", "상대")
            )
        st.write("")

with tab_expl:
    with st.container(border=True):
        if result.get("해설"):
            st.markdown(f"**기본과실 해설**\n\n{result['해설']}")
        if result.get("수정요소_해설"):
            st.markdown(f"**수정요소 해설**\n\n{result['수정요소_해설']}")
        if not result.get("해설") and not result.get("수정요소_해설"):
            st.caption("해설 데이터가 없습니다.")

# 최종과실/계산_단계는 위 tab_apply 안에서 이미 (토글 반영 후) 계산해뒀습니다 — 여기선 재사용만.
# (with 블록은 파이썬에서 새 스코프를 안 만들어서 그대로 접근 가능. 백엔드 사용 시
# recalculate()를 또 부르면 왕복이 두 번 생겨서 일부러 다시 안 부릅니다.)

# ── 2-3. AI 설명 (백엔드가 있으면 LLM, 로컬이면 정형 문구) ────────
if result.get("답변"):
    st.write("")
    st.markdown('<div class="fr-section-title">🤖 AI 설명</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if result.get("warnings"):
            # AI가 직접 쓴 문장이 아니라 백엔드의 정형 대체 문구일 때는 그렇다고
            # 눈에 띄게 알려줍니다 — 안 그러면 AI가 잘 답한 것처럼 오해할 수 있어요.
            st.warning("⚠️ AI가 지금 답변을 만들지 못해서, 대신 정해진 문구를 보여드리고 있어요.")
        st.write(result["답변"])
        if result.get("warnings"):
            with st.expander("자세한 원인 (기술 정보)"):
                for w in result["warnings"]:
                    st.caption(w)

# ── 2-4. 관련 법규 · 유사사례(심의사례) ────────────────────────────
st.write("")
col_law, col_case = st.columns(2)

with col_law:
    st.markdown('<div class="fr-section-title">📜 관련 법규</div>', unsafe_allow_html=True)
    법조항 = result.get("법조항", [])
    if not 법조항:
        st.caption("관련 법령이 없습니다.")
    for law in 법조항:
        with st.expander(f"{law.get('조', '조문')} {law.get('제목', '')}"):
            st.write(law.get("내용", ""))
            if not law.get("시행중", True):
                st.caption("⚠️ 현재 시행 중이 아닌 조문입니다.")

with col_case:
    st.markdown(
        '<div class="fr-section-title">⚖️ 유사사례 (심의사례) '
        '<span class="fr-badge fr-badge-ref" style="margin-left:6px;font-size:0.78rem;">참고용 · 계산에 미사용</span></div>',
        unsafe_allow_html=True,
    )
    # 위 배지로 "참고용"임을 명확히 표시했으니, 각 항목 expander 안 '주의' 문구는 유지하되
    # 여기 섹션 타이틀에서부터 계산에 안 쓰인다는 걸 바로 알 수 있게 함.
    유사사례 = result.get("유사사례", [])
    if not 유사사례:
        st.caption("관련 심의사례가 없습니다.")
    for c in 유사사례:
        with st.expander(c.get("제목", "심의사례")):
            st.caption(f"청구인측: {c.get('A_당사자', '-')} · 피청구인측: {c.get('B_당사자', '-')}")
            기본 = c.get("기본비율")
            결정 = c.get("결정비율")
            if 기본:
                st.write(f"기본비율: A {기본['A']}% : B {기본['B']}%")
            if 결정:
                st.write(f"실제 결정비율: A {결정['A']}% : B {결정['B']}%")
            if c.get("비율_달라짐"):
                st.warning("⚠️ 이 사례는 기본비율과 실제 결정비율이 다릅니다 — 다른 사정이 반영됐을 수 있어요.")
            st.caption(c.get("주의", ""))

if result.get("판례"):
    st.caption("참조 판례: " + ", ".join(result["판례"]))

with st.expander("🔎 유사 사고유형 더 보기"):
    후보 = result.get("후보", [])
    if not 후보:
        st.caption("유사 사고유형이 없습니다.")
    for s in 후보:
        st.markdown(f"- **{s.get('도표번호')}** {s.get('제목', '')} (관련도 {s.get('검색점수', 0):.2f})")

with st.expander("🔬 처리 과정 (trace)"):
    for t in result.get("trace", []):
        결과 = t.get("결과", t.get("result"))
        소요 = t.get("소요ms", t.get("elapsed_ms"))
        st.markdown(f"- `step {t.get('step')}` **{t.get('tool')}** → {결과} ({소요}ms)")

# ── 3. 대화형 후속 질문·반박 ─────────────────────────────────────
st.divider()
st.markdown('<div class="fr-section-title">🗨️ 추가로 물어보거나 반박하기</div>', unsafe_allow_html=True)
if result.get("백엔드_사용"):
    st.caption("실제 LLM이 답변합니다.")
else:
    st.caption("🔧 로컬 검색 모드에서는 정형 안내만 드려요 — 백엔드가 붙으면 실제 LLM이 답합니다.")

for entry in st.session_state["chat_history"]:
    role, msg = entry[0], entry[1]
    warned = entry[2] if len(entry) > 2 else False
    avatar = "🙋" if role == "user" else "🤖"
    with st.chat_message("user" if role == "user" else "assistant", avatar=avatar):
        if warned:
            st.caption("⚠️ AI가 직접 쓴 답이 아니라 정해진 문구입니다")
        st.write(msg)

follow_up = st.chat_input("예) 저는 신호가 있었다고 생각해요 / 상대가 과속했어요")
if follow_up:
    st.session_state["chat_history"].append(("user", follow_up))
    with st.spinner("답변을 준비하는 중..."):
        answer, chat_warnings = follow_up_chat(result, follow_up)
    st.session_state["chat_history"].append(("assistant", answer, bool(chat_warnings)))
    st.rerun()

disclaimer()
