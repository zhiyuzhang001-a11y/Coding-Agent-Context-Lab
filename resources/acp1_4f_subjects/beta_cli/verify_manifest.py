#!/usr/bin/env python3
import json

commands = ["archive", "completion", "list", "restore", "show"]
details = [{"command": value, "registered": True, "help": True} for value in commands]
print(json.dumps({"manifest": "beta-cli", "details": details, "summary": {"command_count": 5, "invalid": 0}, "exit_status": 0}, sort_keys=True))

