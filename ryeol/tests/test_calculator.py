from ryeol.app.calculator import apply_modifiers
from ryeol.app.schemas import Modifier, Ratio

def test_apply_a_modifier():
    result, applied, skipped, steps = apply_modifiers(
        Ratio(A=30, B=70), [Modifier(조건="야간", 대상="A", 값=10)], ["야간"])
    assert result == Ratio(A=40, B=60)
    assert len(applied) == 1 and not skipped
    assert steps[-1].값 == 40

def test_apply_b_modifier_changes_a_inverse():
    result, *_ = apply_modifiers(
        Ratio(A=30, B=70), [Modifier(조건="상대 과속", 대상="B", 값=10)], ["상대 과속"])
    assert result == Ratio(A=20, B=80)

def test_duplicate_condition_is_applied_once():
    modifiers = [Modifier(조건="야간", 대상="A", 값=10), Modifier(조건="야간", 대상="A", 값=10)]
    result, applied, skipped, _ = apply_modifiers(Ratio(A=30, B=70), modifiers, ["야간"])
    assert result == Ratio(A=40, B=60)
    assert len(applied) == 1 and len(skipped) == 1

def test_clamps_and_preserves_sum():
    result, *_ = apply_modifiers(
        Ratio(A=95, B=5), [Modifier(조건="중과실", 대상="A", 값=20)], ["중과실"])
    assert result == Ratio(A=100, B=0)
