"""
지식베이스 스키마 — 파싱 결과의 계약.

파서(A)와 구조화(B)가 이 스키마로 대화합니다.
`validate_kb.py`가 이 스키마로 품질을 검증합니다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Ratio(BaseModel):
    """A = 앞 당사자, B = 뒤 당사자. 합은 항상 100."""

    a: int = Field(..., ge=0, le=100)
    b: int = Field(..., ge=0, le=100)

    @model_validator(mode="after")
    def _sum_100(self):
        if self.a + self.b != 100:
            raise ValueError(f"기본과실 합이 100이 아님: {self.a}+{self.b}")
        return self


class Modifier(BaseModel):
    """수정요소. adjustment는 target 차량의 과실에 가감되는 값."""

    name: str
    target: Literal["A", "B"]
    adjustment: int = Field(..., ge=-100, le=100)
    condition: str | None = Field(None, description="(가)/(나) 등 조건 분기")
    note_ref: str | None = Field(None, description="①②③ 해설 참조 번호")

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("수정요소 이름이 비었음")
        return v.strip()


class Standard(BaseModel):
    """기준 도표 1개."""

    standard_id: str = Field(..., description="MAIN2023-차15-1")
    source_id: Literal["MAIN2023", "PM2021", "ROUND2025"]
    diagram_no: str = Field(..., description="차15-1")
    section: str | None = Field(None, description="상위 절 제목 [차15]")
    title: str = ""
    party_a: str = Field("", description="(A) 직진")
    party_b: str = Field("", description="(B) 좌회전")
    base_ratio: Ratio | None = None
    base_ratio_variants: dict[str, Ratio] = Field(
        default_factory=dict, description="(가)/(나) 조건별 기본과실"
    )
    modifiers: list[Modifier] = Field(default_factory=list)
    accident_description: str = ""
    base_ratio_explanation: str = ""
    modifier_explanation: str = ""
    laws: list[str] = Field(default_factory=list)
    precedents: list[str] = Field(default_factory=list)
    legacy_nos: list[str] = Field(
        default_factory=list, description="※舊 214, 324 기준 → 심의사례 매핑 키"
    )
    source_page: int = Field(..., ge=1, description="PDF 물리 페이지")
    book_page: int | None = Field(None, description="책자 표시 페이지")
    page_span: int = 1
    diagram_image: str | None = None
    parse_flags: list[str] = Field(
        default_factory=list, description="파싱 이상 신호 — 수기 검수 대상 표시"
    )