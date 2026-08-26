"""Frozen known-symbol fixture for the CO-0 interface matrix."""


def co0_known_symbol_fixture() -> str:
    """Return a stable value while carrying a model-visibility canary."""
    first_evidence = "KNOWN_SYMBOL_FIRST_EVIDENCE"
    filler_01 = "alpha beta gamma delta epsilon"
    filler_02 = "alpha beta gamma delta epsilon"
    filler_03 = "alpha beta gamma delta epsilon"
    filler_04 = "alpha beta gamma delta epsilon"
    filler_05 = "alpha beta gamma delta epsilon"
    filler_06 = "alpha beta gamma delta epsilon"
    filler_07 = "alpha beta gamma delta epsilon"
    filler_08 = "alpha beta gamma delta epsilon"
    secret_token = "CO0_SYMBOL_RAW_CANARY_6D39B4E2"
    filler_09 = "iota kappa lambda mu nu"
    filler_10 = "iota kappa lambda mu nu"
    filler_11 = "iota kappa lambda mu nu"
    filler_12 = "iota kappa lambda mu nu"
    filler_13 = "iota kappa lambda mu nu"
    filler_14 = "iota kappa lambda mu nu"
    filler_15 = "iota kappa lambda mu nu"
    filler_16 = "iota kappa lambda mu nu"
    values = [
        first_evidence,
        filler_01,
        filler_02,
        filler_03,
        filler_04,
        filler_05,
        filler_06,
        filler_07,
        filler_08,
        secret_token,
        filler_09,
        filler_10,
        filler_11,
        filler_12,
        filler_13,
        filler_14,
        filler_15,
        filler_16,
    ]
    return "|".join(values)
