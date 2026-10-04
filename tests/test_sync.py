import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sync


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pdfs = self.root / "pdfs"
        self.notes = self.root / "notes"
        self.pdfs.mkdir()
        self.pdf = self.pdfs / "chemistry" / "redox.pdf"
        self.pdf.parent.mkdir()
        self.pdf.write_bytes(b"first PDF bytes")
        self.state = self.notes / sync.STATE_FILENAME

    def run_sync(self, dry_run=False, text="Study text", error=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch("sync.extract_text", return_value=text, side_effect=error) as extract:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                result = sync.sync_folder(self.pdfs, self.notes, dry_run)
        return result, output.getvalue(), errors.getvalue(), extract

    def test_hash_changes_with_bytes(self):
        first = sync.sha256_file(self.pdf)
        self.assertEqual(first, hashlib.sha256(b"first PDF bytes").hexdigest())
        self.pdf.write_bytes(b"different PDF bytes")
        self.assertNotEqual(first, sync.sha256_file(self.pdf))

    def test_missing_and_empty_state(self):
        self.assertEqual(sync.load_state(self.state), {"files": {}})
        self.notes.mkdir()
        for content in ('{}', '{"files": {}}'):
            self.state.write_text(content, encoding="utf-8")
            self.assertEqual(sync.load_state(self.state), {"files": {}})

    def test_state_round_trip(self):
        state = {"files": {"z.pdf": {"sha256": "z", "markdown": "z.md"},
                           "é.pdf": {"sha256": "a", "markdown": "é.md"}}}
        sync.save_state(self.state, state)
        self.assertEqual(sync.load_state(self.state), state)
        saved = self.state.read_text(encoding="utf-8")
        self.assertEqual(saved, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.assertFalse(self.state.with_name(self.state.name + ".tmp").exists())

    def test_new_pdf_writes_expected_note(self):
        result, output, errors, extract = self.run_sync(text="Oxidation\nReduction")
        self.assertEqual(result, 0)
        self.assertIn("NEW chemistry/redox.pdf", output)
        self.assertEqual(errors, "")
        extract.assert_called_once_with(self.pdf)
        note = (self.notes / "chemistry" / "redox.md").read_text(encoding="utf-8")
        self.assertIn("# redox\n", note)
        self.assertIn("Source: `chemistry/redox.pdf`", note)
        self.assertIn(f"SHA-256: `{sync.sha256_file(self.pdf)}`", note)
        self.assertIn("Oxidation\nReduction", note)
        entry = sync.load_state(self.state)["files"]["chemistry/redox.pdf"]
        self.assertEqual(entry["markdown"], "chemistry/redox.md")

    def test_unchanged_pdf_skips_extraction_and_note_write(self):
        self.run_sync()
        note = self.notes / "chemistry" / "redox.md"
        note.write_text("My edited note", encoding="utf-8")
        result, output, _, extract = self.run_sync()
        self.assertEqual(result, 0)
        self.assertIn("UNCHANGED chemistry/redox.pdf", output)
        extract.assert_not_called()
        self.assertEqual(note.read_text(encoding="utf-8"), "My edited note")

    def test_changed_pdf_is_processed_again(self):
        self.run_sync()
        self.pdf.write_bytes(b"changed PDF")
        result, output, _, extract = self.run_sync(text="Updated text")
        self.assertEqual(result, 0)
        self.assertIn("CHANGED chemistry/redox.pdf", output)
        extract.assert_called_once()
        note = self.notes / "chemistry" / "redox.md"
        self.assertIn("Updated text", note.read_text(encoding="utf-8"))
        entry = sync.load_state(self.state)["files"]["chemistry/redox.pdf"]
        self.assertEqual(entry["sha256"], sync.sha256_file(self.pdf))

    def test_dry_run_creates_nothing(self):
        before = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))
        output = io.StringIO()
        with patch("sync.extract_text") as extract, contextlib.redirect_stdout(output):
            result = sync.main([str(self.pdfs), str(self.notes), "--dry-run"])
        self.assertEqual(result, 0)
        self.assertIn("Would write chemistry/redox.md", output.getvalue())
        extract.assert_not_called()
        self.assertFalse(self.notes.exists())
        self.assertEqual(before, sorted(path.relative_to(self.root) for path in self.root.rglob("*")))

    def test_dry_run_preserves_existing_files(self):
        self.run_sync()
        self.pdf.write_bytes(b"new content")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result, output, _, extract = self.run_sync(dry_run=True)
        self.assertEqual(result, 0)
        self.assertIn("CHANGED chemistry/redox.pdf", output)
        extract.assert_not_called()
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_malformed_json_fails_clearly_without_writes(self):
        self.notes.mkdir()
        self.state.write_text("{bad JSON", encoding="utf-8")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            result = sync.main([str(self.pdfs), str(self.notes)])
        self.assertEqual(result, 1)
        self.assertIn("Invalid state file", errors.getvalue())
        self.assertEqual(self.state.read_text(encoding="utf-8"), "{bad JSON")
        self.assertFalse((self.notes / "chemistry").exists())

    def test_invalid_state_structure_fails_clearly(self):
        self.notes.mkdir()
        for content in ('[]', '{"files": []}', '{"files": {"x.pdf": null}}'):
            self.state.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid state file"):
                sync.load_state(self.state)

    def test_failed_new_pdf_is_not_recorded(self):
        result, _, errors, _ = self.run_sync(error=ValueError("broken PDF"))
        self.assertEqual(result, 1)
        self.assertIn("ERROR chemistry/redox.pdf: ValueError: broken PDF", errors)
        self.assertEqual(sync.load_state(self.state), {"files": {}})
        self.assertFalse((self.notes / "chemistry" / "redox.md").exists())

    def test_failed_changed_pdf_retains_old_hash_and_retries(self):
        self.run_sync()
        previous = sync.load_state(self.state)
        self.pdf.write_bytes(b"broken update")
        result, _, _, _ = self.run_sync(error=ValueError("broken update"))
        self.assertEqual(result, 1)
        self.assertEqual(sync.load_state(self.state), previous)
        result, output, _, extract = self.run_sync(text="Recovered")
        self.assertEqual(result, 0)
        self.assertIn("CHANGED chemistry/redox.pdf", output)
        extract.assert_called_once()

    def test_one_failure_does_not_block_other_pdfs(self):
        other = self.pdfs / "valid.pdf"
        other.write_bytes(b"valid bytes")
        def extract(path):
            if path == self.pdf:
                raise ValueError("broken PDF")
            return "Valid text"
        with patch("sync.extract_text", side_effect=extract):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = sync.sync_folder(self.pdfs, self.notes)
        self.assertEqual(result, 1)
        self.assertEqual(set(sync.load_state(self.state)["files"]), {"valid.pdf"})
        self.assertTrue((self.notes / "valid.md").exists())

    def test_hash_failure_is_not_recorded(self):
        with patch("sync.sha256_file", side_effect=PermissionError("cannot read PDF")):
            result, _, errors, extract = self.run_sync()
        self.assertEqual(result, 1)
        self.assertIn("cannot read PDF", errors)
        extract.assert_not_called()
        self.assertEqual(sync.load_state(self.state), {"files": {}})

    def test_missing_input_returns_error_without_output_directory(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            result = sync.main([str(self.root / "missing"), str(self.notes)])
        self.assertEqual(result, 1)
        self.assertIn("Input directory does not exist", errors.getvalue())
        self.assertFalse(self.notes.exists())

    def test_no_extractable_text_creates_warning(self):
        result, _, _, _ = self.run_sync(text=" \n ")
        self.assertEqual(result, 0)
        note = self.notes / "chemistry" / "redox.md"
        self.assertIn("> " + sync.NO_TEXT_WARNING, note.read_text(encoding="utf-8"))

    def test_deleted_pdf_leaves_note_but_removes_state_entry(self):
        self.run_sync()
        self.pdf.unlink()
        result, _, _, extract = self.run_sync()
        self.assertEqual(result, 0)
        extract.assert_not_called()
        self.assertEqual(sync.load_state(self.state), {"files": {}})
        self.assertTrue((self.notes / "chemistry" / "redox.md").exists())

    def test_discovery_is_sorted_recursive_and_case_insensitive(self):
        (self.pdfs / "z.PDF").write_bytes(b"z")
        (self.pdfs / "a.pdf").write_bytes(b"a")
        (self.pdfs / "ignored.txt").write_text("ignore", encoding="utf-8")
        self.assertEqual(
            [path.relative_to(self.pdfs).as_posix() for path in sync.find_pdfs(self.pdfs)],
            ["a.pdf", "chemistry/redox.pdf", "z.PDF"],
        )


if __name__ == "__main__":
    unittest.main()
