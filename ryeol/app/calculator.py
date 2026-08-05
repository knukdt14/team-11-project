from __future__ import annotations
from .schemas import CalculationStep, Modifier, Ratio

def apply_modifiers(base_ratio: Ratio, modifiers: list[Modifier], selected_conditions: list[str]):
    """LLM과 무관하게 최종 과실을 계산하는 유일한 함수."""
    selected, seen = set(selected_conditions), set()
    a = base_ratio.A
    steps = [CalculationStep(라벨="기본과실", 값=a)]
    applied, skipped = [], []
    for modifier in modifiers:
        current = modifier.model_copy(deep=True)
        key = current.id or current.조건
        chosen = key in selected or current.조건 in selected
        if not chosen or key in seen:
            current.적용됨 = False
            skipped.append(current)
            continue
        seen.add(key)
        a = min(100, max(0, a + (current.값 if current.대상 == "A" else -current.값)))
        current.적용됨 = True
        applied.append(current)
        sign = "+" if current.값 >= 0 else ""
        steps.append(CalculationStep(라벨=f"{current.조건} {sign}{current.값} ({current.대상})", 값=a))
    return Ratio(A=a, B=100-a), applied, skipped, steps
