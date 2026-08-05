from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Side = Literal["A", "B"]

class Ratio(BaseModel):
    A: int = Field(ge=0, le=100)
    B: int = Field(ge=0, le=100)
    @model_validator(mode="after")
    def sum_is_100(self):
        if self.A + self.B != 100:
            raise ValueError("A와 B의 합은 100이어야 합니다")
        return self

class Modifier(BaseModel):
    id: str = ""
    조건: str
    대상: Side
    값: int = Field(ge=-100, le=100)
    적용됨: bool = False
    근거: str = ""

class CalculationStep(BaseModel):
    라벨: str
    값: int

class ConsultRequest(BaseModel):
    사고설명: str = Field(min_length=3, max_length=4000)
    상담자측: Side = "A"
    적용할_수정요소: list[str] = Field(default_factory=list)
    session_id: str | None = None

class RecalculateRequest(BaseModel):
    session_id: str
    적용할_수정요소: list[str] = Field(default_factory=list)

class FollowUpRequest(BaseModel):
    session_id: str
    질문: str = Field(min_length=1, max_length=2000)

class AdditionalInfoRequest(BaseModel):
    session_id: str
    추가정보: str = Field(min_length=2, max_length=2000)
    적용할_수정요소: list[str] = Field(default_factory=list)

class FollowUpResponse(BaseModel):
    session_id: str
    답변: str
    llm_mode: str
    warnings: list[str] = Field(default_factory=list)

class ConsultResponse(BaseModel):
    session_id: str
    status: Literal["complete", "needs_information", "not_found"]
    사고유형: dict | None = None
    도표번호: str | None = None
    제목: str = ""
    출처: str | None = None
    나_역할: str | None = None
    상대_역할: str | None = None
    기본과실: Ratio | None = None
    적용_수정요소: list[Modifier] = Field(default_factory=list)
    미적용_수정요소: list[Modifier] = Field(default_factory=list)
    최종과실: Ratio | None = None
    계산_단계: list[CalculationStep] = Field(default_factory=list)
    답변: str = ""
    유사사례: list[dict] = Field(default_factory=list)
    판례: list[str] = Field(default_factory=list)
    법조항: list[dict] = Field(default_factory=list)
    image_url: str | None = None
    pdf_page: int | None = None
    trace: list[dict] = Field(default_factory=list)
    신뢰도: str = "낮음"
    경고: str | None = None
    후보: list[dict] = Field(default_factory=list)
    되묻기: list[str] = Field(default_factory=list)
    llm_mode: str
    warnings: list[str] = Field(default_factory=list)

class RecalculateResponse(BaseModel):
    session_id: str
    기본과실: Ratio
    적용_수정요소: list[Modifier]
    미적용_수정요소: list[Modifier]
    최종과실: Ratio
    계산_단계: list[CalculationStep]
