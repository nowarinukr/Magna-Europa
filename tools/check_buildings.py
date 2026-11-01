#!/usr/bin/env python3
"""Check building source structure and 1.19.4 level caps, without running HOI4."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class Entry:
    key: str
    value: str | list["Entry"] | None
    start: int
    end: int
    line: int


def parse(text: str) -> list[Entry]:
    """Read literal Clausewitz blocks; keep repeated fields and source offsets."""
    tokens = []
    pattern = re.compile(r'\s+|\#[^\n]*|"(?:\\.|[^"\\])*"|[{}=]|[^\s{}=#"]+')
    pos = 0
    for match in pattern.finditer(text.lstrip("\ufeff")):
        if match.start() != pos:
            raise ValueError(f"Unsupported source at offset {pos}")
        pos = match.end()
        token = match[0]
        if not token.isspace() and not token.startswith("#"):
            tokens.append((token, match.start(), match.end()))
    if pos != len(text.lstrip("\ufeff")):
        raise ValueError(f"Unsupported source at offset {pos}")
    index = 0

    def block(nested=False):
        nonlocal index
        result = []
        while index < len(tokens):
            key, start, end = tokens[index]
            if key == "}":
                if not nested:
                    raise ValueError("Unexpected closing brace")
                index += 1
                return result, end
            if key in ("{", "="):
                raise ValueError(f"Expected field or list value near {key}")
            index += 1
            value = None
            if index < len(tokens) and tokens[index][0] == "=":
                index += 1
                if index >= len(tokens):
                    raise ValueError(f"Missing value for {key}")
                token, _, end = tokens[index]
                if token == "{":
                    index += 1
                    value, end = block(True)
                elif token in ("}", "="):
                    raise ValueError(f"Missing value for {key}")
                else:
                    value = token
                    index += 1
            result.append(Entry(key, value, start, end, text.count("\n", 0, start) + 1))
        if nested:
            raise ValueError("Unclosed block")
        return result, len(text)

    return block()[0]


def fields(entry: Entry) -> dict[str, Entry]:
    if not isinstance(entry.value, list):
        raise ValueError(f"{entry.key} must be a block")
    return {field.key: field for field in entry.value}


LEGACY_FIELDS = {"max_level", "provincial", "shares_slots", "max_fuel_building",
                 "nuclear_production_factor"}


def check_buildings(text: str) -> tuple[list[str], int]:
    root = {entry.key: entry for entry in parse(text)}
    if "buildings" not in root:
        return ["missing buildings block"], 0
    buildings = fields(root["buildings"])
    spawns = fields(root["spawn_points"]) if "spawn_points" in root else {}
    issues = []
    for name, entry in buildings.items():
        data = fields(entry)
        for key in data:
            if key in LEGACY_FIELDS or key.startswith("country_resource_cost_"):
                issues.append(f"{name}: unsupported old top-level field {key}")
        if "level_cap" not in data:
            issues.append(f"{name}: missing level_cap")
        else:
            cap = fields(data["level_cap"])
            if not any(k in cap for k in ("state_max", "province_max", "shares_slots")):
                issues.append(f"{name}: level_cap has no capacity or shared-slot rule")
            for key in ("state_max", "province_max"):
                if key in cap:
                    value = cap[key].value
                    if not isinstance(value, str) or not value.isdigit() or int(value) < 1:
                        issues.append(f"{name}: {key} must be a positive integer")
            if "shares_slots" in cap and cap["shares_slots"].value not in ("yes", "no"):
                issues.append(f"{name}: shares_slots must be yes/no")
        if "spawn_point" in data:
            target = str(data["spawn_point"].value).strip('"')
            if target not in spawns:
                issues.append(f"{name}: undefined spawn_point {target}")
        if "country_modifiers" in data:
            modifiers = fields(data["country_modifiers"])
            if "modifiers" not in modifiers or not isinstance(modifiers["modifiers"].value, list):
                issues.append(f"{name}: country_modifiers requires a modifiers block")
    return issues, len(buildings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "common/buildings/00_buildings.txt")
    args = parser.parse_args()
    try:
        issues, count = check_buildings(args.path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    for issue in issues:
        print(f"ERROR: {issue}")
    print(f"Checked {count} building definitions: {len(issues)} source error(s). Engine behavior is unverified.")
    return bool(issues)


if __name__ == "__main__":
    raise SystemExit(main())
