#!/usr/bin/env python3
"""Compare Lua define overrides to supplied vanilla data; never execute Lua.

Understands literal tables and numeric constant arithmetic. Dynamic expressions,
functions and unrecognised statements are errors. This is a source comparison,
not a test of the HOI4 engine or proof that supplied files belong to a version.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    kind: str


@dataclass
class Value:
    kind: str
    data: object
    line: int


@dataclass(frozen=True)
class Issue:
    level: str
    path: Path
    line: int
    message: str

    def __str__(self):
        return f"{self.level}: {self.path}:{self.line}: {self.message}"


TOKEN = re.compile(
    r'(?P<space>\s+)|(?P<comment>--[^\n]*)|'
    r'(?P<string>"(?:\\.|[^"\\\r\n])*"|\'(?:\\.|[^\'\\\r\n])*\')|'
    r'(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|'
    r'(?P<id>[A-Za-z_][A-Za-z_0-9]*)|(?P<punct>[{}\[\]().,;=+*/%^\-])', re.S)


def tokenize(text: str) -> list[Token]:
    tokens = []
    pos = 0
    line = 1
    while pos < len(text):
        # Lua long comments require separate handling from -- line comments.
        long = re.match(r'--\[(=*)\[', text[pos:])
        if long:
            closing = ']' + long[1] + ']'
            end = text.find(closing, pos + long.end())
            if end < 0:
                raise ParseError(f"line {line}: unterminated long comment")
            end += len(closing)
            line += text[pos:end].count('\n')
            pos = end
            continue
        match = TOKEN.match(text, pos)
        if not match:
            raise ParseError(f"line {line}: unsupported Lua token {text[pos:pos+30]!r}")
        kind = match.lastgroup
        if kind not in ('space', 'comment'):
            tokens.append(Token(match[0], line, kind))
        line += match[0].count('\n')
        pos = match.end()
    tokens.append(Token('<EOF>', line, 'eof'))
    return tokens


class Parser:
    def __init__(self, text: str, path: Path):
        self.tokens = tokenize(text.lstrip('\ufeff'))
        self.index = 0
        self.path = path
        self.issues: list[Issue] = []

    @property
    def token(self):
        return self.tokens[self.index]

    def take(self, expected=None):
        result = self.token
        if expected is not None and result.text != expected:
            raise ParseError(f"line {result.line}: expected {expected!r}, got {result.text!r}")
        self.index += 1
        return result

    def identifier(self):
        if self.token.kind != 'id':
            raise ParseError(f"line {self.token.line}: expected identifier, got {self.token.text!r}")
        return self.take().text

    def numeric(self, minimum=0):
        """Validate numeric constant expressions without evaluating them."""
        start = self.index
        if self.token.text in ('+', '-'):
            self.take()
            self.numeric(25)
        elif self.token.text == '(':
            self.take('(')
            self.numeric()
            self.take(')')
        elif self.token.kind == 'number':
            self.take()
        else:
            raise ParseError(f"line {self.token.line}: expected numeric constant")
        precedence = {'+': 10, '-': 10, '*': 20, '/': 20, '%': 20, '^': 30}
        while self.token.text in precedence and precedence[self.token.text] >= minimum:
            op = self.take().text
            self.numeric(precedence[op] + (0 if op == '^' else 1))
        return Value('number', ''.join(t.text for t in self.tokens[start:self.index]), self.tokens[start].line)

    def value(self):
        token = self.token
        if token.text == '{':
            self.take('{')
            values = {}
            next_index = 1
            while self.token.text != '}':
                if self.token.kind == 'id' and self.tokens[self.index + 1].text == '=':
                    key = self.identifier()
                    self.take('=')
                elif self.token.text == '[':
                    self.take('[')
                    key_token = self.take()
                    if key_token.kind == 'string':
                        key = key_token.text[1:-1]
                    elif key_token.kind == 'number' and key_token.text.isdigit():
                        key = int(key_token.text)
                    else:
                        raise ParseError(f"line {key_token.line}: table keys must be literal strings or integer indices")
                    self.take(']')
                    self.take('=')
                else:
                    key = next_index
                    next_index += 1
                value = self.value()
                if key in values:
                    self.issues.append(Issue('WARN', self.path, value.line, f'duplicate table key {key!r}'))
                values[key] = value
                if self.token.text in (',', ';'):
                    self.take()
                elif self.token.text != '}':
                    raise ParseError(f"line {self.token.line}: expected table separator or closing brace")
            self.take('}')
            return Value('table', values, token.line)
        if token.kind == 'string':
            return Value('string', self.take().text[1:-1], token.line)
        if token.text in ('true', 'false'):
            return Value('boolean', self.take().text, token.line)
        return self.numeric()

    def overrides(self):
        result = []
        while self.token.kind != 'eof':
            line = self.token.line
            parts = [self.identifier()]
            while self.token.text == '.':
                self.take('.')
                parts.append(self.identifier())
            if parts[0] != 'NDefines':
                raise ParseError(f"line {line}: expected NDefines override")
            self.take('=')
            result.append((tuple(parts[1:]), self.value(), line))
            if self.token.text == ';':
                self.take(';')
        return result

    def vanilla(self, expected_name):
        self.take(expected_name)
        self.take('=')
        value = self.value()
        if value.kind != 'table':
            raise ParseError('vanilla root must be a literal table')
        if self.token.text == ';':
            self.take(';')
        if expected_name != 'NDefines':
            # The only supported non-data statement: the supplied graphics/profile
            # table is merged into NDefines. Match every token; never run the loop.
            expected = f'for k , v in pairs ( {expected_name} ) do NDefines [ k ] = v end'.split()
            for word in expected:
                self.take(word)
        self.take('<EOF>')
        return value


VANILLA_FILES = {'00_defines.lua': 'NDefines', '00_graphics.lua': 'NDefines_Graphics',
                 '01_career_profile.lua': 'NDefines_CareerProfile'}


def load_vanilla(directory: Path):
    values = {}
    issues = []
    for filename, table_name in VANILLA_FILES.items():
        path = directory / filename
        if not path.is_file():
            raise ParseError(f'missing vanilla reference file: {path}')
        parser = Parser(path.read_text(encoding='utf-8-sig'), path)
        root = parser.vanilla(table_name)
        issues.extend(parser.issues)
        # These are shallow merges, matching the exact source loops.
        values.update(root.data)
    return Value('table', values, 1), issues


def array_length(value):
    if value.kind != 'table':
        return None
    keys = list(value.data)
    if keys and all(type(k) is int for k in keys) and set(keys) == set(range(1, len(keys) + 1)):
        return len(keys)
    return None


def compare_value(base, override, path, line, name):
    issues = []
    if base.kind != override.kind:
        return [Issue('ERROR', path, line, f'{name}: type changed from {base.kind} to {override.kind}')]
    if base.kind != 'table':
        return issues
    a, b = array_length(base), array_length(override)
    if a is not None:
        if b != a:
            issues.append(Issue('WARN', path, line, f'{name}: array length {a} -> {b if b is not None else "non-array table"}; requires semantic review'))
        for key in base.data.keys() & override.data.keys():
            issues.extend(compare_value(base.data[key], override.data[key], path, line, f'{name}[{key}]'))
    else:
        issues.append(Issue('WARN', path, line, f'{name}: whole named table replacement; omitted vanilla fields will be lost'))
        for key in override.data:
            if key not in base.data:
                issues.append(Issue('ERROR', path, line, f'{name}.{key}: unknown table field'))
            else:
                issues.extend(compare_value(base.data[key], override.data[key], path, line, f'{name}.{key}'))
    return issues


def compare_overrides(base: Value, paths: list[Path]):
    issues = []
    seen = {}
    effective = {}
    count = 0
    for path in sorted(paths):
        parser = Parser(path.read_text(encoding='utf-8-sig'), path)
        assignments = parser.overrides()
        issues.extend(parser.issues)
        for parts, value, line in assignments:
            count += 1
            name = '.'.join(('NDefines',) + parts)
            if parts in seen:
                issues.append(Issue('WARN', path, line, f'{name}: duplicate override; previous {seen[parts]}'))
            seen[parts] = f'{path}:{line}'
            effective[parts] = (value, path, line)
            current = base
            missing = False
            for part in parts:
                if current.kind != 'table' or part not in current.data:
                    issues.append(Issue('ERROR', path, line, f'{name}: unknown symbol or namespace in supplied vanilla data'))
                    missing = True
                    break
                current = current.data[part]
            if not missing:
                issues.extend(compare_value(current, value, path, line, name))
    issues.extend(check_naval_piercing(base, effective))
    return issues, count


def check_naval_piercing(base, overrides):
    """The three parallel naval piercing arrays must keep matching lengths.

    This invariant is explicitly described by the supplied vanilla comments.
    Unrelated arrays can legitimately change length and only produce warnings.
    """
    names = ('NAVY_PIERCING_THRESHOLDS', 'NAVY_PIERCING_THRESHOLD_CRITICAL_VALUES',
             'NAVY_PIERCING_THRESHOLD_DAMAGE_VALUES')
    keys = [('NNavy', name) for name in names]
    changed = [overrides[key] for key in keys if key in overrides]
    if not changed:
        return []
    navy = base.data.get('NNavy')
    if navy is None or navy.kind != 'table' or any(name not in navy.data for name in names):
        # Unknown symbols are already reported; do not invent missing defaults.
        return []
    lengths = [array_length(overrides[key][0] if key in overrides else navy.data[key[1]])
               for key in keys]
    if len(set(lengths)) == 1 and lengths[0] is not None and lengths[0] >= 2:
        return []
    _, path, line = changed[-1]
    details = ', '.join(f'{name}={length}' for name, length in zip(names, lengths))
    return [Issue('ERROR', path, line, f'naval piercing parallel arrays must have equal lengths >= 2: {details}')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vanilla-dir', required=True, type=Path,
                        help='directory with all three supplied vanilla Lua files')
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        base, issues = load_vanilla(args.vanilla_dir)
        files = sorted((args.root / 'common/defines').glob('*.lua'))
        if not files:
            raise ParseError(f'no mod define files under {args.root / "common/defines"}')
        findings, count = compare_overrides(base, files)
        issues.extend(findings)
    except (ParseError, UnicodeDecodeError, OSError) as exc:
        print(f'ERROR: {exc}')
        return 1
    for issue in issues:
        print(issue)
    errors = sum(i.level == 'ERROR' for i in issues)
    warnings = sum(i.level == 'WARN' for i in issues)
    print(f'Compared {count} overrides in {len(files)} files: {errors} error(s), {warnings} warning(s).')
    print('Static comparison only. Supplied game version and engine compatibility are not verified.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
