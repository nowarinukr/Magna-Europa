"""Check the layout and isolation of the Windows local-test distribution."""

from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.build_test_package import build, test_descriptor


class TestPackageTests(unittest.TestCase):
    def test_descriptor_retains_replacements_but_not_workshop_identity(self):
        source = ('name="Original"\nremote_file_id="123"\n'
                  'supported_version="1.14.*"\nreplace_path="events"\n')
        result = test_descriptor(source)
        self.assertIn('replace_path="events"', result)
        self.assertNotIn('remote_file_id', result)
        self.assertNotIn('1.14.*', result)
        self.assertIn('1.19.*', result)
        self.assertIn('TEST', result)

    def test_package_has_matching_launcher_and_inner_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "source"
            (root / "common").mkdir(parents=True)
            (root / "common/test.txt").write_text("sample={}")
            (root / "descriptor.mod").write_text('name="Original"\nreplace_path="events"\n')
            (root / ".git").mkdir()
            (root / ".git/config").write_text("private local metadata")
            output = build(root, parent / "test.zip")
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertFalse(any(".git" in name for name in names))
                self.assertIn("great_bruh_1194_test/common/test.txt", names)
                inner = archive.read("great_bruh_1194_test/descriptor.mod").decode()
                outer = archive.read("great_bruh_1194_test.mod").decode()
                self.assertEqual(outer, inner + 'path="mod/great_bruh_1194_test"\n')
            self.assertEqual((root / "descriptor.mod").read_text(),
                             'name="Original"\nreplace_path="events"\n')
            with self.assertRaises(FileExistsError):
                build(root, output)

    def test_output_cannot_be_written_inside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                build(root, root / "test.zip")


if __name__ == "__main__":
    unittest.main()
