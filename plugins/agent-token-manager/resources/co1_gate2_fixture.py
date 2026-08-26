"""Frozen CO-1 Gate 2 fixture. Do not use as production code."""

# CASE function_answer START
# CO1_CANARY_FUNCTION_91A7
# Unrelated navigation note 01: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 02: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 03: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 04: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 05: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 06: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 07: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 08: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 09: this text must be visible to Native and omitted by CO.
# Unrelated navigation note 10: this text must be visible to Native and omitted by CO.
def normalize_name(value: str) -> str:
    """Normalize a display name into a stable slug."""
    return "-".join(value.strip().lower().split())


# Unrelated tail 01: omitted context makes the raw range intentionally expensive.
# Unrelated tail 02: omitted context makes the raw range intentionally expensive.
# Unrelated tail 03: omitted context makes the raw range intentionally expensive.
# Unrelated tail 04: omitted context makes the raw range intentionally expensive.
# Unrelated tail 05: omitted context makes the raw range intentionally expensive.
# Unrelated tail 06: omitted context makes the raw range intentionally expensive.
# Unrelated tail 07: omitted context makes the raw range intentionally expensive.
# Unrelated tail 08: omitted context makes the raw range intentionally expensive.
# Unrelated tail 09: omitted context makes the raw range intentionally expensive.
# Unrelated tail 10: omitted context makes the raw range intentionally expensive.
# CASE function_answer END


# CASE method_answer START
class Router:
    route_canary = "CO1_CANARY_METHOD_B204"

    # Unrelated class note 01: excluded because it follows a real class field.
    # Unrelated class note 02: excluded because it follows a real class field.
    # Unrelated class note 03: excluded because it follows a real class field.
    # Unrelated class note 04: excluded because it follows a real class field.
    # Unrelated class note 05: excluded because it follows a real class field.
    # Unrelated class note 06: excluded because it follows a real class field.
    # Unrelated class note 07: excluded because it follows a real class field.
    # Unrelated class note 08: excluded because it follows a real class field.
    def route(self, path: str) -> str:
        """Create a route key without consulting sibling state."""
        return f"route:{path.strip('/').lower()}"


# Unrelated method tail 01: raw-only context.
# Unrelated method tail 02: raw-only context.
# Unrelated method tail 03: raw-only context.
# Unrelated method tail 04: raw-only context.
# Unrelated method tail 05: raw-only context.
# Unrelated method tail 06: raw-only context.
# Unrelated method tail 07: raw-only context.
# Unrelated method tail 08: raw-only context.
# CASE method_answer END


# CASE global_context START
CO1_CANARY_GLOBAL_C31F = "raw-only"
CO1_MULTIPLIER = 7
# Global context padding 01: the method slice deliberately omits the constant definition.
# Global context padding 02: the method slice deliberately omits the constant definition.
# Global context padding 03: the method slice deliberately omits the constant definition.
# Global context padding 04: the method slice deliberately omits the constant definition.
# Global context padding 05: the method slice deliberately omits the constant definition.
# Global context padding 06: the method slice deliberately omits the constant definition.
class Calculator:
    marker = "class-body-start"

    def compute(self, value: int) -> int:
        """Use the module policy multiplier."""
        return value * CO1_MULTIPLIER


# Global context tail 01: raw-only context.
# Global context tail 02: raw-only context.
# Global context tail 03: raw-only context.
# Global context tail 04: raw-only context.
# Global context tail 05: raw-only context.
# Global context tail 06: raw-only context.
# CASE global_context END


# CASE local_edit START
# CO1_CANARY_EDIT_D482
# Edit padding 01: unrelated text outside the target syntax unit.
# Edit padding 02: unrelated text outside the target syntax unit.
# Edit padding 03: unrelated text outside the target syntax unit.
# Edit padding 04: unrelated text outside the target syntax unit.
# Edit padding 05: unrelated text outside the target syntax unit.
# Edit padding 06: unrelated text outside the target syntax unit.
# Edit padding 07: unrelated text outside the target syntax unit.
# Edit padding 08: unrelated text outside the target syntax unit.
def format_label(value: str) -> str:
    """Return the label in the required external representation."""
    return value.strip().lower()


# Edit tail 01: unrelated text outside the target syntax unit.
# Edit tail 02: unrelated text outside the target syntax unit.
# Edit tail 03: unrelated text outside the target syntax unit.
# Edit tail 04: unrelated text outside the target syntax unit.
# Edit tail 05: unrelated text outside the target syntax unit.
# Edit tail 06: unrelated text outside the target syntax unit.
# Edit tail 07: unrelated text outside the target syntax unit.
# Edit tail 08: unrelated text outside the target syntax unit.
# CASE local_edit END


# CASE ambiguous_range START
# CO1_CANARY_AMBIGUOUS_E593
# Ambiguous padding 01: this entire range must fail open.
# Ambiguous padding 02: this entire range must fail open.
# Ambiguous padding 03: this entire range must fail open.
# Ambiguous padding 04: this entire range must fail open.
def left_value() -> int:
    return 2


def right_value() -> int:
    return 3


# Ambiguous tail 01: this entire range must fail open.
# Ambiguous tail 02: this entire range must fail open.
# Ambiguous tail 03: this entire range must fail open.
# Ambiguous tail 04: this entire range must fail open.
# CASE ambiguous_range END


# CASE over_budget START
# CO1_CANARY_BUDGET_F6A4
# Budget padding 01: the complete function is intentionally indivisible.
# Budget padding 02: the complete function is intentionally indivisible.
def large_total() -> int:
    """Stay larger than the frozen Gate 2 syntax budget."""
    value_01 = 1
    value_02 = 2
    value_03 = 3
    value_04 = 4
    value_05 = 5
    value_06 = 6
    value_07 = 7
    value_08 = 8
    value_09 = 9
    value_10 = 10
    value_11 = 11
    value_12 = 12
    value_13 = 13
    value_14 = 14
    value_15 = 15
    value_16 = 16
    value_17 = 17
    value_18 = 18
    value_19 = 19
    value_20 = 20
    value_21 = 21
    value_22 = 22
    value_23 = 23
    value_24 = 24
    value_25 = 25
    value_26 = 26
    value_27 = 27
    value_28 = 28
    value_29 = 29
    value_30 = 30
    value_31 = 31
    value_32 = 32
    value_33 = 33
    value_34 = 34
    value_35 = 35
    value_36 = 36
    value_37 = 37
    value_38 = 38
    value_39 = 39
    value_40 = 40
    return sum(
        (
            value_01, value_02, value_03, value_04, value_05,
            value_06, value_07, value_08, value_09, value_10,
            value_11, value_12, value_13, value_14, value_15,
            value_16, value_17, value_18, value_19, value_20,
            value_21, value_22, value_23, value_24, value_25,
            value_26, value_27, value_28, value_29, value_30,
            value_31, value_32, value_33, value_34, value_35,
            value_36, value_37, value_38, value_39, value_40,
        )
    )


# Budget tail 01: fail-open must preserve this raw text.
# Budget tail 02: fail-open must preserve this raw text.
# CASE over_budget END
