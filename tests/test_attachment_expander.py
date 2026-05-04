from __future__ import annotations

import unittest
import uuid
import shutil
from pathlib import Path
from unittest.mock import patch

from src.api.attachment_expander import (
    build_attachment_context_note,
    expand_attachments_for_chatgpt,
)

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in test env
    fitz = None

try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in test env
    Image = None


@unittest.skipUnless(fitz is not None and Image is not None, "attachment expansion dependencies are unavailable")
class AttachmentExpanderTests(unittest.TestCase):
    def test_expand_pdf_renders_all_pages(self) -> None:
        tmpdir = self._make_scratch_dir()
        try:
            pdf_path = tmpdir / "sample.pdf"
            doc = fitz.open()
            for page_number in range(3):
                page = doc.new_page()
                page.insert_text((72, 72), f"Page {page_number + 1}")
            doc.save(pdf_path)
            doc.close()

            result = expand_attachments_for_chatgpt([], [str(pdf_path)])

            self.assertEqual(len(result.image_paths), 3)
            self.assertEqual(result.file_paths, [])
            self.assertEqual(result.total_rendered_pages, 3)
            self.assertEqual([page.page_number for page in result.page_descriptors], [1, 2, 3])
            self.assertEqual([page.page_index for page in result.page_descriptors], [1, 2, 3])
            self.assertTrue(any("sample.pdf" in note for note in result.notes))
            for image_path in result.image_paths:
                self.assertTrue(Path(image_path).exists())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_expand_multiframe_image_renders_all_frames(self) -> None:
        tmpdir = self._make_scratch_dir()
        try:
            image_path = tmpdir / "frames.tiff"
            frames = [
                Image.new("RGB", (20, 20), color)
                for color in ("red", "green", "blue")
            ]
            frames[0].save(image_path, save_all=True, append_images=frames[1:], format="TIFF")

            result = expand_attachments_for_chatgpt([str(image_path)], [])

            self.assertEqual(len(result.image_paths), 3)
            self.assertEqual(result.file_paths, [])
            self.assertEqual(result.total_rendered_pages, 3)
            self.assertEqual([page.page_number for page in result.page_descriptors], [1, 2, 3])
            self.assertTrue(any("frames.tiff" in note for note in result.notes))
            for page_path in result.image_paths:
                self.assertTrue(Path(page_path).exists())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_page_limit_is_applied(self) -> None:
        tmpdir = self._make_scratch_dir()
        try:
            with patch(
                "src.api.attachment_expander.Config.ATTACHMENT_MAX_PAGES",
                2,
            ):
                pdf_path = tmpdir / "limited.pdf"
                doc = fitz.open()
                for page_number in range(4):
                    page = doc.new_page()
                    page.insert_text((72, 72), f"Page {page_number + 1}")
                doc.save(pdf_path)
                doc.close()

                result = expand_attachments_for_chatgpt([], [str(pdf_path)])

                self.assertEqual(len(result.image_paths), 2)
                self.assertTrue(any("Limited to the first 2 of 4 pages." in note for note in result.notes))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_attachment_context_note_mentions_ordering(self) -> None:
        note = build_attachment_context_note(["Expanded 'doc.pdf' into 3 ordered page image(s)."])
        self.assertIn("[Attachment processing]", note)
        self.assertIn("ordered pages", note)

    def test_passthrough_file_still_gets_page_descriptor(self) -> None:
        tmpdir = self._make_scratch_dir()
        try:
            file_path = tmpdir / "notes.txt"
            file_path.write_text("hello", encoding="utf-8")

            result = expand_attachments_for_chatgpt([], [str(file_path)])

            self.assertEqual(result.image_paths, [])
            self.assertEqual(result.file_paths, [str(file_path)])
            self.assertEqual(len(result.page_descriptors), 1)
            self.assertEqual(result.page_descriptors[0].source_name, "notes.txt")
            self.assertEqual(result.page_descriptors[0].page_number, 1)
            self.assertEqual(result.page_descriptors[0].page_index, 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _make_scratch_dir(self) -> Path:
        root = Path.cwd() / "test_scratch"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"attachment-expander-{uuid.uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        return path


if __name__ == "__main__":
    unittest.main()
