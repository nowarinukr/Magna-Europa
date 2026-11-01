"""Detect malformed capacity rules and broken links before a game launch."""

import unittest

from tools.check_buildings import check_buildings, fields, parse


class BuildingsTests(unittest.TestCase):
    def test_parser_ignores_comment_braces_and_preserves_quoted_strings(self):
        root = parse('root={ # }\n name="a # { \\"quoted\\"" values={x y} }')
        self.assertEqual(fields(root[0])["name"].value, '"a # { \\"quoted\\""')
        self.assertEqual([e.key for e in fields(root[0])["values"].value], ["x", "y"])

    def test_parser_rejects_unclosed_block_and_missing_value(self):
        for text in ('root={ value=1', 'root={ value= }', 'root={}='):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)

    def test_old_capacity_and_country_fields_are_reported(self):
        issues, count = check_buildings('''buildings={
factory={max_level=20 shares_slots=yes country_resource_cost_aluminium=1}
port={max_level=10 provincial=yes}
}''')
        self.assertEqual(count, 2)
        self.assertTrue(any('max_level' in issue for issue in issues))
        self.assertTrue(any('shares_slots' in issue for issue in issues))
        self.assertTrue(any('provincial' in issue for issue in issues))
        self.assertTrue(any('country_resource_cost' in issue for issue in issues))
        self.assertEqual(sum('missing level_cap' in issue for issue in issues), 2)

    def test_state_province_and_shared_slot_rules_are_supported(self):
        text = '''buildings={
factory={level_cap={state_max=20 shares_slots=yes}}
port={spawn_point=port_spawn level_cap={province_max=10}}
silo={level_cap={shares_slots=yes}
 country_modifiers={modifiers={max_fuel_building=100.0}}}
} spawn_points={port_spawn={type=province max=1}}'''
        self.assertEqual(check_buildings(text), ([], 3))

    def test_invalid_capacity_values_are_errors(self):
        for capacity in ('province_max=0', 'state_max=-1', 'state_max=unlimited',
                         'shares_slots=maybe', 'group_by=anything'):
            with self.subTest(capacity=capacity):
                issues, _ = check_buildings('buildings={test={level_cap={' + capacity + '}}}')
                self.assertTrue(issues)

    def test_missing_spawn_target_and_malformed_modifier_container_are_errors(self):
        text = '''buildings={test={spawn_point=unknown level_cap={province_max=1}
country_modifiers={max_fuel_building=100}}}'''
        issues, _ = check_buildings(text)
        self.assertEqual(len(issues), 2)
        self.assertTrue(any('undefined spawn_point' in issue for issue in issues))
        self.assertTrue(any('requires a modifiers block' in issue for issue in issues))


if __name__ == '__main__':
    unittest.main()
