"""Frozen Beta CLI command registry fixture."""

COMMANDS = {
    "list": {"category": "query", "color": "auto"},
    "show": {"category": "query", "color": "always"},
    "archive": {"category": "mutation", "color": "never"},
    "restore": {"category": "mutation", "color": "never"},
    "completion": {"category": "shell", "color": "auto"},
}


def public_commands() -> tuple[str, ...]:
    return tuple(sorted(COMMANDS))

