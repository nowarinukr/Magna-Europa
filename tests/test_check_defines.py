"""Safe data-parser fixtures, without shipping vanilla game files."""

from pathlib import Path
import tempfile
import unittest

from tools.check_defines import Parser, ParseError, compare_overrides, load_vanilla


class ParserTests(unittest.TestCase):
    def test_tables_comments_quoted_comment_and_arithmetic(self):
        parser = Parser('''--[[ ignored { -- ]]
NDefines = { NSample = { DAYS = 9*30, RATE = -(1e-2 + 2)^2,
 TITLE = "a -- { \\"word\\"", FLAG = false, LIST = {1, 2, 3,}, }, }
''', Path('base.lua'))
        base = parser.vanilla('NDefines')
        data = base.data['NSample'].data
        self.assertEqual(data['DAYS'].data, '9*30')
        self.assertEqual(data['RATE'].kind, 'number')
        self.assertEqual(data['FLAG'].kind, 'boolean')
        self.assertEqual(len(data['LIST'].data), 3)

    def test_reject_calls_and_trailing_code(self):
        for text in ['NDefines = { X = os.execute("bad") }',
                     'NDefines = {} print("bad")',
                     'NDefines.X.Y = 1; os.execute("bad")',
                     'NDefines.X.Y = 1 + dynamic',
                     'NDefines.X.Y = 1 .. 2',
                     'NDefines.X.Y = "raw\nnewline"']:
            with self.subTest(text=text), self.assertRaises(ParseError):
                parser = Parser(text, Path('sample.lua'))
                (parser.vanilla('NDefines') if text.startswith('NDefines =') else parser.overrides())

    def test_merge_loop_must_match_exact_supported_statement(self):
        good = 'NDefines_Graphics = { NX = {} } for k,v in pairs(NDefines_Graphics) do NDefines[k] = v end'
        Parser(good, Path('graphics.lua')).vanilla('NDefines_Graphics')
        with self.assertRaises(ParseError):
            Parser(good.replace('= v end', '= dangerous() end'), Path('graphics.lua')).vanilla('NDefines_Graphics')

    def test_duplicate_literal_key_warns(self):
        parser = Parser('NDefines={NX={VALUE=1,VALUE=2}}', Path('base.lua'))
        parser.vanilla('NDefines')
        self.assertEqual(len(parser.issues), 1)
        self.assertEqual(parser.issues[0].level, 'WARN')


class ComparisonTests(unittest.TestCase):
    def compare(self, override):
        base = Parser('NDefines={NX={NUM=1,ARR={1,2,3},GROUP={A=1,B=2}}}', Path('base.lua')).vanilla('NDefines')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'override.lua'
            path.write_text(override, encoding='utf-8')
            return compare_overrides(base, [path])

    def test_valid_scalar_and_array_override(self):
        issues, count = self.compare('NDefines.NX.NUM = 50\n NDefines.NX.ARR={4,5,6}')
        self.assertEqual((issues, count), ([], 2))

    def test_unknown_namespace_and_wrong_type_are_errors(self):
        issues, _ = self.compare('NDefines.NY.NUM=2\nNDefines.NX.NUM="wrong"')
        self.assertEqual([i.level for i in issues], ['ERROR','ERROR'])

    def test_array_arity_and_duplicate_override_warn(self):
        issues, _ = self.compare('NDefines.NX.ARR={1}\nNDefines.NX.NUM=2\nNDefines.NX.NUM=3')
        self.assertEqual([i.level for i in issues], ['WARN','WARN'])
        self.assertIn('array length', issues[0].message)
        self.assertIn('duplicate override', issues[1].message)

    def test_whole_named_table_replacement_warns_and_unknown_field_errors(self):
        issues, _ = self.compare('NDefines.NX.GROUP={A=5,C=8}')
        self.assertEqual([i.level for i in issues], ['WARN','ERROR'])

    def test_loader_merges_graphics_and_career_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'00_defines.lua').write_text('NDefines={NX={A=1}}')
            for filename, name, group in [('00_graphics.lua','NDefines_Graphics','NGraphics'),
                                           ('01_career_profile.lua','NDefines_CareerProfile','NCareer')]:
                (root/filename).write_text(f'{name}={{{group}={{A=1}}}} for k,v in pairs({name}) do NDefines[k]=v end')
            base, issues = load_vanilla(root)
            self.assertEqual(set(base.data), {'NX','NGraphics','NCareer'})
            self.assertEqual(issues, [])

    def test_naval_parallel_arrays_must_change_together(self):
        names = ['NAVY_PIERCING_THRESHOLDS', 'NAVY_PIERCING_THRESHOLD_CRITICAL_VALUES',
                 'NAVY_PIERCING_THRESHOLD_DAMAGE_VALUES']
        source = 'NDefines={NNavy={' + ','.join(name+'={1,2,3}' for name in names) + '}}'
        base = Parser(source, Path('base.lua')).vanilla('NDefines')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'navy.lua'
            path.write_text('NDefines.NNavy.NAVY_PIERCING_THRESHOLDS={1,2,3,4}')
            issues, _ = compare_overrides(base, [path])
            self.assertTrue(any(i.level == 'ERROR' and 'parallel arrays' in i.message for i in issues))
            path.write_text('\n'.join('NDefines.NNavy.'+name+'={1,2,3,4}' for name in names))
            issues, _ = compare_overrides(base, [path])
            self.assertFalse(any(i.level == 'ERROR' for i in issues))


if __name__ == '__main__':
    unittest.main()
