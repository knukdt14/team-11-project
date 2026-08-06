"""지식베이스 탐색 — 상담 흐름과 별개로 전체 KB를 자유 검색/필터링합니다."""

from __future__ import annotations

import threading
from pathlib import Path

from nicegui import run, ui

from webapp import auth, theme
from webapp.services.kb_data import SOURCE_LABELS, source_label

_KIND_MAP = {"기준 도표": "standard", "심의사례": "case", "법령": "law"}
_HANI_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "hani" / "data"

_searcher_lock = threading.Lock()
_searcher_instance = None


def _searcher():
    global _searcher_instance
    if _searcher_instance is None:
        with _searcher_lock:
            if _searcher_instance is None:
                from taek.search import Searcher

                _searcher_instance = Searcher()
    return _searcher_instance


@ui.page("/kb")
async def kb_page() -> None:
    if not await auth.require_login():
        return
    theme.inject_head()
    with theme.page_frame("kb"):
        theme.hero("지식베이스 탐색", "상담 없이 도표·판례·법령을 직접 검색해볼 수 있습니다.")

        results_box = ui.column().classes("w-full")

        async def do_search() -> None:
            q = query.value.strip()
            results_box.clear()
            if not q:
                with results_box:
                    ui.label("검색어를 입력해주세요.").classes("text-orange-600")
                return
            with results_box:
                ui.spinner(size="lg")
            # ⚠️ 검색(임베딩+정렬)이 수백ms~초 단위로 걸릴 수 있어서, 동기 호출을 그대로
            # 쓰면 그동안 서버 전체(다른 접속자 포함)가 멈춥니다 — run.io_bound로 별도
            # 스레드에 넘겨서 이벤트 루프가 막히지 않게 합니다.
            hits = await run.io_bound(
                _searcher().search,
                q,
                top_k=15,
                kind=_KIND_MAP[kind.value],
                source_id=None if source_sel.value == "전체" else source_sel.value,
                mode="hybrid",
                expand=True,
            )
            results_box.clear()
            with results_box:
                ui.label(f"{len(hits)}건 검색됨").classes("font-bold")
                if not hits:
                    ui.label("검색 결과가 없습니다. 다른 표현으로 다시 시도해보세요.").classes(
                        "text-gray-500"
                    )
                for h in hits:
                    p = h.payload
                    label = h.label if h.kind != "case" else p.get("title", h.text[:40])
                    with ui.element("div").classes("fr-kb-card w-full"):
                        with ui.row().classes("w-full items-start justify-between no-wrap"):
                            with ui.column().classes("min-w-0"):
                                ui.label(label).classes("fr-kb-title")
                                ui.label(
                                    f"{source_label(p.get('source_id', ''))} · p.{p.get('source_page', '?')}"
                                ).classes("fr-kb-meta")
                            ui.label(f"관련도 {h.score:.2f}").classes("fr-kb-meta")
                        snippet = h.text.strip().replace("\n", " ")
                        ui.label(snippet[:200] + ("…" if len(snippet) > 200 else "")).classes(
                            "text-sm mt-1"
                        )
                        with ui.expansion("자세히 보기").classes("w-full mt-1"):
                            if p.get("image_path"):
                                img_path = _HANI_DATA_DIR / p["image_path"]
                                if img_path.exists():
                                    ui.image(str(img_path)).classes("w-full rounded").style(
                                        "max-width:480px;"
                                    )
                            if p.get("base_ratio"):
                                ui.markdown(
                                    f"기본과실: A {p['base_ratio']['a']}% : B {p['base_ratio']['b']}%"
                                )
                            if p.get("modifiers"):
                                ui.markdown("**수정요소**")
                                for m in p["modifiers"]:
                                    sign = "+" if m["adjustment"] >= 0 else ""
                                    ui.label(
                                        f"- {m['name']} ({sign}{m['adjustment']}, {m['target']})"
                                    ).classes("text-xs text-gray-500")
                            if p.get("laws"):
                                ui.label("관련 법령: " + ", ".join(p["laws"])).classes(
                                    "text-xs text-gray-500"
                                )

        with ui.element("div").classes("fr-card w-full"):
            with ui.row().classes("w-full no-wrap items-end").style("gap:12px"):
                query = ui.input("검색어", placeholder="예) 후방추돌, 회전교차로, 전동킥보드 …").classes(
                    "flex-1"
                ).on("keydown.enter", do_search)
                source_sel = ui.select(
                    ["전체", *SOURCE_LABELS.keys()],
                    value="전체",
                    label="문서",
                ).classes("w-48")
            kind = ui.radio(["기준 도표", "심의사례", "법령"], value="기준 도표").props("inline")
            ui.button("🔎 검색", on_click=do_search).classes("fr-btn-primary mt-2").props("unelevated")

        with results_box:
            ui.label("검색어를 입력하고 검색 버튼을 누르면 결과가 여기 표시됩니다.").classes(
                "text-gray-500"
            )

        ui.separator().classes("my-4")
        ui.link("💬 특정 사고 상황으로 상담받기", "/consult").classes("fr-nav-link").style(
            "display:inline-flex; width:auto;"
        )
