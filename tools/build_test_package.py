#!/usr/bin/env python3
"""Build a separate local test mod; never publish or modify the source descriptor."""

import argparse
from pathlib import Path
import re
import zipfile


TEST_FOLDER = "great_bruh_1194_test"
TEST_NAME = "Great Bruh V2 - 1.19.4 TEST"
GAME_DIRECTORIES = ("common", "events", "gfx", "history", "interface",
                    "localisation", "map", "music", "tutorial")


def test_descriptor(source):
    """Preserve replace_path declarations, separating the test from Workshop."""
    if not re.search(r'^name\s*=', source, re.M):
        raise ValueError("Source descriptor must contain a name")
    kept = [line for line in source.splitlines()
            if not re.match(r'^\s*(?:name|supported_version|remote_file_id|path)\s*=', line)]
    return ("\n".join(kept) + f'\nname="{TEST_NAME}"\n'
            'supported_version="1.19.*"\n')


def build(root, output):
    root, output = root.resolve(), output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Write the archive outside the source checkout")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    descriptor = test_descriptor((root / "descriptor.mod").read_text(encoding="utf-8-sig"))
    readme = '''ТЕСТОВА КОПІЯ ДЛЯ HOI4 1.19.4

Це експериментальний порт. Запуск у грі ще не підтверджено.
Потрібна нова кампанія; старі збереження не перевірені.

1. Закрий гру та лаунчер.
2. Відкрий Documents/Paradox Interactive/Hearts of Iron IV/mod.
   Папка Documents може бути в OneDrive. Якщо папки mod немає, створи її.
3. Із ZIP скопіюй САМЕ great_bruh_1194_test.mod та папку
   great_bruh_1194_test безпосередньо у mod. Вони мають лежати поруч.
   Якщо така тестова копія вже є, спочатку збережи її окремо.
4. Відкрий лаунчер. Додай Great Bruh V2 - 1.19.4 TEST до окремого набору.
   Для першого тесту увімкни лише його, без оригіналу й інших модів.
   Мова гри: English.
5. У Steam у параметрах запуску HOI4 вкажи -debug. Запусти гру.
   Спробуй нову кампанію з 1911 року. Якщо завантажилась — пограй
   кілька ігрових днів, перевір дослідження, виробництво й фокуси.
6. Закрий гру. Одразу збережи error.log і game.log із
   Documents/Paradox Interactive/Hearts of Iron IV/logs та надішли їх у чат.
   Наступний запуск може перезаписати журнали. Напиши, до якого етапу
   дійшла гра, та які DLC увімкнені. Якщо є — також надішли exceptions.log
   із каталогу останнього збою в crashes.

Оригінальний Workshop-мод і GitHub-копію цей пакет не змінює.
supported_version=1.19.* тут означає ціль тесту, а не доведену сумісність.

НЕОБОВ'ЯЗКОВИЙ ПЕРЕКЛАД: після окремого тесту моду скопіюй вміст
optional_uk/localisation у great_bruh_1194_test/localisation, тоді увімкни
ванільний українізатор. Це лише 33 українські записи; решта ще англійською.
Для скасування прибери тільки zzzz_great_bruh_uk_l_english.yml із replace.
'''
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for directory in GAME_DIRECTORIES:
            for path in sorted((root / directory).rglob("*")):
                if path.is_file():
                    archive.write(path, f"{TEST_FOLDER}/{path.relative_to(root).as_posix()}")
        for path in sorted(root.glob("*.png")):
            archive.write(path, f"{TEST_FOLDER}/{path.name}")
        archive.writestr(f"{TEST_FOLDER}/descriptor.mod", descriptor)
        archive.writestr(f"{TEST_FOLDER}.mod", descriptor + f'path="mod/{TEST_FOLDER}"\n')
        archive.writestr("READ_ME_FIRST.txt", readme.encode("utf-8-sig"))
        overlay = root / "translations/uk/overlay"
        for path in sorted(overlay.rglob("*.yml")):
            archive.write(path, f"optional_uk/{path.relative_to(overlay).as_posix()}")
    with zipfile.ZipFile(output) as archive:
        if (bad := archive.testzip()) is not None:
            raise ValueError(f"Archive checksum failed: {bad}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = build(args.root, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(f"Built {output} ({output.stat().st_size:,} bytes); ZIP checksums verified.")
    print("This is a separate TEST build; HOI4 runtime compatibility is unverified.")


if __name__ == "__main__":
    main()
