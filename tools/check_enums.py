#!/usr/bin/env python3
"""Check flat enum/category lists against supplied game files, without executing code.

Membership in a script enum does not establish that an equipment, technology or
other referenced database object exists. This is not an engine compatibility test.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re


IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
TOKEN = re.compile(r"\s+|#[^\n]*|[A-Za-z_][A-Za-z_0-9]*|[{}=]")


def parse_lists(text: str) -> dict[str, list[str]]:
    """Accept only named top-level lists of identifiers, not arbitrary script."""
    text = text.lstrip("\ufeff")
    tokens = []
    position = 0
    while position < len(text):
        match = TOKEN.match(text, position)
        if match is None:
            raise ValueError(f"Unsupported list syntax near {text[position:position + 35]!r}")
        if not match[0].isspace() and not match[0].startswith("#"):
            tokens.append(match[0])
        position = match.end()
    groups = {}
    index = 0
    while index < len(tokens):
        if index + 2 >= len(tokens) or not IDENTIFIER.fullmatch(tokens[index]):
            raise ValueError("Expected a named list")
        name = tokens[index]
        if name in groups:
            raise ValueError(f"Duplicate list group: {name}")
        if tokens[index + 1:index + 3] != ["=", "{"]:
            raise ValueError(f"Expected '{{' after {name}")
        index += 3
        values = []
        while index < len(tokens) and tokens[index] != "}":
            if not IDENTIFIER.fullmatch(tokens[index]):
                raise ValueError(f"Only identifier values are supported inside {name}")
            values.append(tokens[index])
            index += 1
        if index == len(tokens):
            raise ValueError(f"Unclosed list: {name}")
        groups[name] = values
        index += 1
    return groups


def compare_groups(actual: dict[str, list[str]], reference: dict[str, list[str]]) -> list[str]:
    issues = []
    for name, values in actual.items():
        duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
        if duplicates:
            issues.append(f"{name}: duplicate members {', '.join(duplicates)}")
    for name, values in reference.items():
        if name not in actual:
            issues.append(f"missing reference group {name}")
            continue
        missing = sorted(set(values) - set(actual[name]))
        if missing:
            issues.append(f"{name}: missing reference members {', '.join(missing)}")
    return issues


def check_unit_categories(root: Path, known: set[str]) -> tuple[list[str], int]:
    """Check category lists in the mod's subunit files, excluding equipment."""
    issues = []
    count = 0
    for path in sorted((root / "common/units").glob("*.txt")):
        text = path.read_text(encoding="utf-8-sig")
        text = re.sub(r'"(?:\\.|[^"\\])*"|#[^\n]*',
                      lambda match: "" if match[0].startswith("#") else match[0], text)
        for match in re.finditer(r"\bcategories\s*=\s*\{([^{}]*)\}", text):
            members = parse_lists("categories = {" + match[1] + "}")["categories"]
            count += len(members)
            for member in members:
                if member not in known:
                    issues.append(f"{path.relative_to(root)}: undefined subunit category {member}")
    return issues, count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vanilla-categories", required=True, type=Path)
    parser.add_argument("--vanilla-enums", required=True, type=Path)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    issues = []
    try:
        data = []
        for name, relative, reference_path in (
                ("categories", "common/unit_tags/00_categories.txt", args.vanilla_categories),
                ("enums", "common/script_enums.txt", args.vanilla_enums)):
            actual = parse_lists((root / relative).read_text(encoding="utf-8-sig"))
            reference = parse_lists(reference_path.read_text(encoding="utf-8-sig"))
            issues.extend(f"{relative}: {issue}" for issue in compare_groups(actual, reference))
            data.append(actual)
            print(f"{name}: {len(actual)} groups, {sum(len(v) for v in actual.values())} members; "
                  f"reference {sum(len(v) for v in reference.values())} members")
        known = set(data[0].get("sub_unit_categories", []))
        if not known:
            issues.append("No sub_unit_categories members found")
        category_issues, count = check_unit_categories(root, known)
        issues.extend(category_issues)
        print(f"Checked {count} subunit category references in mod unit files.")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for issue in issues:
        print(f"ERROR: {issue}")
    print(f"Enum/category checks: {len(issues)} error(s). Database objects and engine behavior are not validated.")
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
