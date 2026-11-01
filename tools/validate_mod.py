#!/usr/bin/env python3
"""Static source checks only; this does not validate the HOI4 engine or 1.19.4."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Issue:
    level: str
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.path}:{self.line}: {self.message}"


def scan_structure(text: str, path: Path) -> list[Issue]:
    """Balance braces, ignoring quoted strings, escaped quotes, and # comments."""
    issues = []
    stack = []
    quoted = False
    escaped = False
    comment = False
    quote_line = 1
    line = 1
    for char in text:
        if char == "\n":
            line += 1
            comment = False
        if comment:
            continue
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == "#":
            comment = True
        elif char == '"':
            quoted = True
            quote_line = line
        elif char == "{":
            stack.append(line)
        elif char == "}":
            if stack:
                stack.pop()
            else:
                issues.append(Issue("ERROR", path, line, "unmatched closing brace"))
    if quoted:
        issues.append(Issue("ERROR", path, quote_line, "unterminated quoted string"))
    for opened in stack:
        issues.append(Issue("ERROR", path, opened, "unclosed opening brace"))
    return issues


ENTRY = re.compile(r'^\s*([^\s:#]+):\d*\s+"(?:[^"\\]|\\.)*"\s*(?:#.*)?$')
HEADER = re.compile(r"^\s*(l_[a-z_]+):\s*(?:#.*)?$")


def check_localisation(path: Path) -> list[Issue]:
    issues = []
    raw = path.read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        issues.append(Issue("ERROR", path, 1, "localisation requires UTF-8 BOM"))
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return issues + [Issue("ERROR", path, 1, f"invalid UTF-8: {exc.reason}")]
    header = None
    keys = {}
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if header is None:
            match = HEADER.fullmatch(line)
            if not match:
                issues.append(Issue("ERROR", path, line_no, "expected language header"))
                return issues
            header = match[1]
            if not path.stem.endswith("_" + header):
                issues.append(Issue("ERROR", path, line_no, "language header differs from filename suffix"))
            continue
        match = ENTRY.fullmatch(line)
        if not match:
            issues.append(Issue("ERROR", path, line_no, "malformed localisation entry (check closing/escaped quotes)"))
            continue
        key = match[1]
        if key in keys:
            issues.append(Issue("WARN", path, line_no, f"duplicate key {key!r}; first on line {keys[key]}"))
        else:
            keys[key] = line_no
    if header is None:
        issues.append(Issue("ERROR", path, 1, "missing language header"))
    return issues


def uncomment(text: str) -> str:
    # Preserve strings and newlines; regex alternatives consume strings before comments.
    return re.sub(r'"(?:\\.|[^"\\])*"|#[^\n]*',
                  lambda m: "" if m[0].startswith("#") else m[0], text)


def check_states(root: Path) -> tuple[list[Issue], int, int]:
    issues = []
    definitions = root / "map/definition.csv"
    if not definitions.is_file():
        return [Issue("ERROR", definitions, 1, "missing province definition file")], 0, 0
    defined = set()
    for line in definitions.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"(\d+);", line)
        if match:
            defined.add(int(match[1]))
    states = {}
    provinces = {}
    files = sorted((root / "history/states").glob("*.txt"))
    if not files:
        issues.append(Issue("ERROR", root / "history/states", 1, "no state files found"))
    for path in files:
        text = uncomment(path.read_text(encoding="utf-8-sig"))
        match = re.search(r"\bid\s*=\s*(\d+)", text)
        if not match:
            issues.append(Issue("ERROR", path, 1, "missing state ID"))
        else:
            state = int(match[1])
            if state in states:
                issues.append(Issue("ERROR", path, 1, f"duplicate state ID {state}; also in {states[state]}"))
            states[state] = path
        match = re.search(r"\bprovinces\s*=\s*\{([^}]*)\}", text, re.S)
        if not match:
            issues.append(Issue("ERROR", path, 1, "missing provinces block"))
            continue
        for province in map(int, re.findall(r"\b\d+\b", match[1])):
            if province not in defined:
                issues.append(Issue("ERROR", path, 1, f"province {province} absent from definition.csv"))
            if province in provinces:
                issues.append(Issue("ERROR", path, 1, f"province {province} assigned more than once; also in {provinces[province]}"))
            provinces[province] = path
    return issues, len(states), len(provinces)


def check_strategic_regions(root: Path) -> tuple[list[Issue], int, int]:
    """Every nonzero defined province must belong to exactly one strategic region."""
    issues = []
    definition = root / "map/definition.csv"
    if not definition.is_file():
        return [Issue("ERROR", definition, 1, "missing province definition file")], 0, 0
    defined = {int(match[1]) for line in definition.read_text(encoding="utf-8-sig").splitlines()
               if (match := re.match(r"(\d+);", line)) and int(match[1]) != 0}
    ids = {}
    provinces = {}
    paths = sorted((root / "map/strategicregions").glob("*.txt"))
    if not paths:
        issues.append(Issue("ERROR", root / "map/strategicregions", 1, "no strategic region files found"))
    for path in paths:
        text = uncomment(path.read_text(encoding="utf-8-sig"))
        match = re.search(r"\bid\s*=\s*(\d+)", text)
        if not match:
            issues.append(Issue("ERROR", path, 1, "missing strategic region ID"))
        else:
            region = int(match[1])
            if region in ids:
                issues.append(Issue("ERROR", path, 1, f"duplicate strategic region ID {region}; also in {ids[region]}"))
            ids[region] = path
        match = re.search(r"\bprovinces\s*=\s*\{([^}]*)\}", text, re.S)
        if not match:
            issues.append(Issue("ERROR", path, 1, "missing strategic region provinces block"))
            continue
        for province in map(int, re.findall(r"\b\d+\b", match[1])):
            if province not in defined:
                issues.append(Issue("ERROR", path, 1, f"strategic region province {province} absent from nonzero definition.csv IDs"))
            if province in provinces:
                issues.append(Issue("ERROR", path, 1, f"province {province} assigned to strategic regions more than once; also in {provinces[province]}"))
            provinces[province] = path
    missing = sorted(defined - provinces.keys())
    if missing:
        issues.append(Issue("ERROR", root / "map/strategicregions", 1,
                            f"{len(missing)} defined provinces missing strategic regions: {missing[:20]}"))
    return issues, len(ids), len(provinces)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    issues = []
    source_count = 0
    for directory in ("common", "events", "history", "interface", "gfx", "map", "tutorial"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in {".txt", ".gui", ".gfx", ".mod"}:
                source_count += 1
                try:
                    issues.extend(scan_structure(path.read_text(encoding="utf-8-sig"), path.relative_to(root)))
                except UnicodeDecodeError:
                    issues.append(Issue("ERROR", path.relative_to(root), 1, "invalid UTF-8"))
    for path in sorted(root.glob("*.mod")):
        source_count += 1
        issues.extend(scan_structure(path.read_text(encoding="utf-8-sig"), path.relative_to(root)))
    loc_files = sorted((root / "localisation").rglob("*.yml"))
    if not loc_files:
        issues.append(Issue("ERROR", root / "localisation", 1, "no localisation files found"))
    for path in loc_files:
        issues.extend(check_localisation(path))
    state_issues, state_count, province_count = check_states(root)
    issues.extend(state_issues)
    region_issues, region_count, region_province_count = check_strategic_regions(root)
    issues.extend(region_issues)
    for issue in issues:
        print(issue)
    errors = sum(i.level == "ERROR" for i in issues)
    warnings = sum(i.level == "WARN" for i in issues)
    print(f"Checked {source_count} script/interface/map files, {len(loc_files)} localisation files, "
          f"{state_count} states and {province_count} state provinces.")
    print(f"Checked {region_count} strategic regions covering {region_province_count} provinces.")
    print(f"Static checks: {errors} error(s), {warnings} warning(s). Engine/HOI4 1.19.4 compatibility is NOT validated.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
