"""Regression checks for safe enum parsing and actual reference coverage."""

from pathlib import Path
import tempfile
import unittest

from tools.check_enums import check_unit_categories, compare_groups, parse_lists


class EnumTests(unittest.TestCase):
    def test_comments_and_bom_are_not_members(self):
        self.assertEqual(parse_lists("\ufeff# preface\nlist = { A # B\n C }"),
                         {"list": ["A", "C"]})

    def test_rejects_non_list_script_and_malformed_groups(self):
        for source in ["list={ A nested={ B } }", "list={ A=1 }", "list={ A",
                       "list={ A } list={ B }", "list={ A } unexpected", "list={\"A\"}"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_lists(source)

    def test_missing_group_and_member_are_reported(self):
        issues = compare_groups({"A": ["old"]}, {"A": ["old", "new"], "B": ["x"]})
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("new" in issue for issue in issues))
        self.assertTrue(any("group B" in issue for issue in issues))

    def test_mod_extensions_allowed_but_duplicates_detected(self):
        self.assertEqual(compare_groups({"A": ["base", "custom"]}, {"A": ["base"]}), [])
        self.assertTrue(compare_groups({"A": ["base", "base"]}, {"A": ["base"]}))

    def test_unit_references_checked_without_equipment_or_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "common/units"
            (units / "equipment").mkdir(parents=True)
            (units / "infantry.txt").write_text(
                "sub_units={x={categories={category_valid category_missing}}} "
                "# categories={comment_only}\n")
            (units / "equipment/weapon.txt").write_text("x={categories={equipment_category}}")
            issues, count = check_unit_categories(root, {"category_valid"})
            self.assertEqual(count, 2)
            self.assertEqual(len(issues), 1)
            self.assertIn("category_missing", issues[0])


if __name__ == "__main__":
    unittest.main()
