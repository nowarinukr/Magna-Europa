"""Fixtures for checks which detect actual malformed mod source."""

from pathlib import Path
import tempfile
import unittest

from tools.validate_mod import check_localisation, check_states, check_strategic_regions, scan_structure


class StructureTests(unittest.TestCase):
    def test_comments_strings_and_escaped_quotes_do_not_count_as_braces(self):
        text = 'root = { text = "} # \\" {" # }\n nested = {} }'
        self.assertEqual(scan_structure(text, Path("sample.txt")), [])

    def test_unclosed_and_extra_braces_are_errors(self):
        self.assertEqual(len(scan_structure("root = {\nchild = {}", Path("sample.txt"))), 1)
        self.assertEqual(len(scan_structure("}", Path("sample.txt"))), 1)

    def test_unterminated_string_is_error(self):
        self.assertTrue(any("quoted string" in i.message for i in scan_structure('name = "oops', Path("sample.txt"))))


class LocalisationTests(unittest.TestCase):
    def run_check(self, text, bom=True):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_l_english.yml"
            path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
            return check_localisation(path)

    def test_valid_escaped_quotes_and_comment(self):
        self.assertEqual(self.run_check('l_english:\n KEY:0 "A \\"quoted\\" text # {" # comment\n'), [])

    def test_missing_closing_quote_and_unescaped_quotes(self):
        for value in (' KEY:0 "unfinished', ' KEY:0 "a "bad" quote"'):
            with self.subTest(value=value):
                self.assertTrue(any(i.level == "ERROR" for i in self.run_check("l_english:\n" + value)))

    def test_bom_and_language_header_required(self):
        self.assertTrue(any("BOM" in i.message for i in self.run_check('l_english:\n', bom=False)))
        self.assertTrue(any("header" in i.message for i in self.run_check(' KEY:0 "Text"\n')))

    def test_duplicate_key_warns_without_error(self):
        issues = self.run_check('l_english:\n KEY:0 "A"\n KEY:0 "B"\n')
        self.assertEqual([i.level for i in issues], ["WARN"])


class StateTests(unittest.TestCase):
    def check(self, states):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "map").mkdir()
            (root / "map/definition.csv").write_text("1;0;0;0;land\n2;1;1;1;land\n", encoding="utf-8")
            (root / "history/states").mkdir(parents=True)
            for index, text in enumerate(states):
                (root / f"history/states/{index}.txt").write_text(text, encoding="utf-8")
            return check_states(root)

    def test_disjoint_defined_provinces_pass(self):
        issues, states, provinces = self.check(['state={id=1 provinces={1}}', 'state={id=2 provinces={2}}'])
        self.assertEqual((issues, states, provinces), ([], 2, 2))

    def test_duplicate_state_province_and_undefined_province_detected(self):
        issues, _, _ = self.check(['state={id=1 provinces={1}}', 'state={id=1 provinces={1 99}}'])
        self.assertEqual(len(issues), 3)
        self.assertTrue(all(i.level == "ERROR" for i in issues))


class StrategicRegionTests(unittest.TestCase):
    def check(self, regions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "map/strategicregions").mkdir(parents=True)
            (root / "map/definition.csv").write_text("0;0;0;0;land\n1;1;1;1;land\n2;2;2;2;sea\n", encoding="utf-8")
            for index, text in enumerate(regions):
                (root / f"map/strategicregions/{index}.txt").write_text(text, encoding="utf-8")
            return check_strategic_regions(root)

    def test_land_and_sea_coverage_pass_excluding_sentinel(self):
        issues, regions, provinces = self.check(['strategic_region={id=1 provinces={1 2}}'])
        self.assertEqual((issues, regions, provinces), ([], 1, 2))

    def test_duplicate_ids_and_province_membership_detected(self):
        issues, _, _ = self.check(['strategic_region={id=1 provinces={1 2}}', 'strategic_region={id=1 provinces={1}}'])
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("duplicate strategic region ID" in i.message for i in issues))
        self.assertTrue(any("more than once" in i.message for i in issues))

    def test_unknown_and_uncovered_provinces_detected(self):
        issues, _, _ = self.check(['strategic_region={id=1 provinces={1 99}}'])
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("99" in i.message for i in issues))
        self.assertTrue(any("missing strategic regions" in i.message for i in issues))


if __name__ == "__main__":
    unittest.main()
