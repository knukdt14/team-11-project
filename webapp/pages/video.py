"""블랙박스 사고 영상 업로드 → 검출·추적·충돌지점 시각화 + AI 과실비율 판정.

실제 계산(YOLO 검출·추적·사고판단, Gemini+RAG 과실판정)은 services/cv(hani 담당)를
그대로 호출만 합니다 — `webapp/services/cv_pipeline.py` 참고.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from nicegui import run, ui

from webapp import auth, theme
from webapp.services.cv_pipeline import (
    analyze_video_evidence,
    assess_fault_from_evidence,
    make_annotated_video_bytes,
)


@ui.page("/video")
async def video_page() -> None:
    if not await auth.require_login():
        return
    theme.inject_head()

    state = {"video_path": None, "result": None, "annotated_video": None}

    with theme.page_frame("video"):
        theme.hero(
            "블랙박스 영상 분석",
            "블랙박스 사고 영상을 올리면 차량 검출·추적·궤적·충돌 지점을 화면에 그려서 보여드립니다.",
        )

        mascot_box = ui.column().classes("w-full")
        with mascot_box:
            theme.mascot_say(
                "안녕하세요! 저는 사고 조사관이에요 🔍 블랙박스 영상을 올려주시면 "
                "제가 차량을 하나하나 추적해서 충돌 순간을 찾아드릴게요."
            )

        result_area = ui.column().classes("w-full")

        async def handle_upload(e) -> None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(e.file.name).suffix) as tmp:
                video_path = tmp.name
            await e.file.save(video_path)
            state["video_path"] = video_path

            result_area.clear()
            mascot_box.clear()
            with result_area:
                ui.spinner(size="lg")
                status = ui.label("영상 분석 중입니다 (차량 검출·추적)... 영상 길이에 따라 시간이 걸릴 수 있어요").classes(
                    "text-gray-500"
                )

            out_dir = tempfile.mkdtemp()
            result = await run.io_bound(analyze_video_evidence, video_path, out_dir)
            state["result"] = result

            annotated_bytes = None
            if result["is_accident"]:
                result_area.clear()
                with result_area:
                    ui.spinner(size="lg")
                    ui.label("영상 전체에 박스 추적 그리는 중... (조금 더 걸립니다)").classes(
                        "text-gray-500"
                    )
                annotated_bytes = await run.io_bound(make_annotated_video_bytes, video_path)
            state["annotated_video"] = annotated_bytes

            render_result()

        with ui.element("div").classes("fr-card w-full"):
            ui.upload(
                label="사고 영상 업로드",
                on_upload=handle_upload,
                auto_upload=True,
                max_file_size=500_000_000,
            ).props('accept=".mp4,.avi,.mov"').classes("w-full")

        def render_result() -> None:
            result_area.clear()
            mascot_box.clear()
            result = state["result"]
            if result is None:
                return

            if not result["is_accident"]:
                with mascot_box:
                    theme.mascot_say(
                        "음... 이 영상에서는 사고 신호를 찾지 못했어요 🤔 다른 영상으로 시도해보시겠어요?"
                    )
                with result_area:
                    ui.label("이 영상에서는 사고 신호가 감지되지 않았습니다.").classes(
                        "text-orange-600"
                    )
                return

            impact = result["impact_frame"]
            with mascot_box:
                theme.mascot_say(
                    f"찾았어요! <b>{impact}번째 프레임</b>에서 부딪힌 것 같아요 ⚡ "
                    "아래에서 추적 영상과 근거 프레임을 직접 확인해보세요."
                )

            with result_area:
                ui.label(f"✅ 사고 감지됨 — 충돌 순간: {impact}프레임").classes(
                    "text-green-700 font-bold"
                )

                ui.markdown("**🎬 YOLO 추적 영상**")
                if state["annotated_video"]:
                    b64 = base64.b64encode(state["annotated_video"]).decode("ascii")
                    ui.html(
                        f'<video controls style="width:100%;max-width:720px;border-radius:12px;">'
                        f'<source src="data:video/mp4;base64,{b64}" type="video/mp4"></video>'
                    )
                    ui.label("차량에 박스가 따라다니며, 빨간 테두리가 충돌 순간입니다.").classes(
                        "text-xs text-gray-400"
                    )
                else:
                    ui.label("⚠️ 추적 영상을 브라우저 재생용으로 변환하지 못했습니다.").classes(
                        "text-xs text-gray-400"
                    )

                ui.markdown("**📸 사고 근거 프레임**")
                with ui.row().classes("w-full"):
                    for p in result["frame_paths"]:
                        is_impact = "impact" in Path(p).name
                        with ui.column().classes("items-center").style("width:23%;min-width:160px;"):
                            ui.image(p).classes("w-full rounded")
                            if is_impact:
                                ui.label("⚡ 충돌 순간").classes("text-xs font-bold text-red-600")
                            else:
                                ui.label(Path(p).stem).classes("text-xs text-gray-400")

                ui.markdown("**⚖️ AI 과실비율 판정**")
                fault_area = ui.column().classes("w-full")

                async def judge():
                    judge_btn.props("loading")
                    fault_area.clear()
                    try:
                        fault = await run.io_bound(assess_fault_from_evidence, result["frame_paths"])
                    except RuntimeError as exc:
                        with fault_area:
                            ui.label(f"⚠️ AI 과실 판정을 실행할 수 없습니다: {exc}").classes(
                                "text-red-600"
                            )
                            ui.label(
                                "webapp/.env 파일에 GEMINI_API_KEY=발급받은키 한 줄을 추가하면 됩니다 "
                                "(Google AI Studio에서 무료 발급)."
                            ).classes("text-xs text-gray-400")
                        return
                    except Exception as exc:  # noqa: BLE001 — Gemini API/파싱 오류도 화면에 보여줘야 함
                        with fault_area:
                            ui.label(f"⚠️ AI 과실 판정 중 오류가 발생했습니다: {exc}").classes(
                                "text-red-600"
                            )
                        return
                    finally:
                        judge_btn.props(remove="loading")

                    if "error" in fault:
                        with fault_area:
                            ui.label(fault["error"]).classes("text-orange-600")
                        return

                    본인 = fault.get("과실", {}).get("본인", 0)
                    상대 = fault.get("과실", {}).get("상대", 0)
                    with fault_area:
                        theme.mascot_say(
                            f"영상이랑 인정기준을 같이 살펴보니, 본인 {본인}% : 상대 {상대}%로 보여요. "
                            "자세한 이유는 아래에 적어뒀어요 👇"
                        )
                        ui.html(theme.ratio_hero_html(본인, 상대, "본인", "상대"))
                        ui.markdown(f"**상황**: {fault.get('상황', '')}")
                        ui.markdown(f"**근거 도표**: {fault.get('근거도표', '')}")
                        ui.markdown(f"**설명**: {fault.get('설명', '')}")
                        ui.label(fault.get("주의", "")).classes("text-xs text-gray-400")
                        if fault.get("후보기준"):
                            with ui.expansion("검색된 인정기준 후보"):
                                for label in fault["후보기준"]:
                                    ui.label(f"• {label}")

                judge_btn = ui.button("🧠 AI로 과실비율까지 판정하기", on_click=judge).props(
                    "outline"
                ).classes("w-full")
                fault_area  # noqa: B018 (참조 유지용)
