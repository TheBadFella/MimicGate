"""
Helpers for expanding multi-page attachments into ordered page images.

This keeps the browser-upload path simple while ensuring ChatGPT sees every page
of a PDF or multi-frame image instead of only the first page/frame.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.config import Config
from src.log import setup_logging

log = setup_logging("attachment_expander")


@dataclass
class AttachmentExpansionResult:
    """Expanded attachment paths plus prompt notes for page ordering/failures."""

    image_paths: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    page_descriptors: list["AttachmentPageDescriptor"] = field(default_factory=list)
    total_rendered_pages: int = 0


@dataclass
class AttachmentPageDescriptor:
    """Metadata describing one logical page/item the model should extract."""

    source_name: str
    page_number: int
    page_index: int = 0
    upload_kind: str = "image"
    source_kind: str = "image"


def expand_attachments_for_chatgpt(
    image_paths: list[str] | None,
    file_paths: list[str] | None,
) -> AttachmentExpansionResult:
    """
    Expand multi-page PDFs and multi-frame images into individual page images.

    Rendering is done sequentially and page failures are isolated so one bad page
    does not abort the whole job.
    """
    result = AttachmentExpansionResult()
    if not Config.ATTACHMENT_EXPAND_MULTIPAGE:
        result.image_paths = list(image_paths or [])
        result.file_paths = list(file_paths or [])
        for image_path in result.image_paths:
            result.page_descriptors.append(
                _build_page_descriptor(image_path, page_number=1, upload_kind="image", source_kind="image")
            )
        for file_path in result.file_paths:
            result.page_descriptors.append(
                _build_page_descriptor(file_path, page_number=1, upload_kind="file", source_kind=_source_kind_for_file(file_path))
            )
        _assign_page_indexes(result.page_descriptors)
        return result

    for image_path in image_paths or []:
        expansion = _expand_multiframe_image(image_path)
        if expansion is None:
            result.image_paths.append(image_path)
            result.page_descriptors.append(
                _build_page_descriptor(image_path, page_number=1, upload_kind="image", source_kind="image")
            )
            continue

        result.image_paths.extend(expansion["image_paths"])
        result.image_paths.extend(expansion["fallback_image_paths"])
        result.notes.extend(expansion["notes"])
        result.page_descriptors.extend(expansion["page_descriptors"])
        result.total_rendered_pages += expansion["rendered_pages"]

    for file_path in file_paths or []:
        if Path(file_path).suffix.lower() != ".pdf":
            result.file_paths.append(file_path)
            result.page_descriptors.append(
                _build_page_descriptor(file_path, page_number=1, upload_kind="file", source_kind=_source_kind_for_file(file_path))
            )
            continue

        expansion = _expand_pdf(file_path)
        if expansion is None:
            result.file_paths.append(file_path)
            result.page_descriptors.append(
                _build_page_descriptor(file_path, page_number=1, upload_kind="file", source_kind="pdf")
            )
            continue

        result.image_paths.extend(expansion["image_paths"])
        result.file_paths.extend(expansion["fallback_file_paths"])
        result.notes.extend(expansion["notes"])
        result.page_descriptors.extend(expansion["page_descriptors"])
        result.total_rendered_pages += expansion["rendered_pages"]

    _assign_page_indexes(result.page_descriptors)
    return result


def build_attachment_context_note(notes: list[str]) -> str:
    """Build a compact prompt preface describing rendered page ordering."""
    if not notes:
        return ""

    lines = ["[Attachment processing]"]
    lines.extend(f"- {note}" for note in notes)
    lines.append("- Treat rendered page images as ordered pages of the same source document.")
    return "\n".join(lines) + "\n\n"


def _expand_pdf(path: str) -> dict | None:
    """Render a PDF to page images. Returns None if the file should pass through unchanged."""
    try:
        import fitz  # type: ignore
    except ImportError:
        log.warning("PyMuPDF is not installed; passing PDF through unchanged: %s", path)
        return None

    pdf_path = Path(path)
    output_dir = str(pdf_path.parent)
    rendered_paths: list[str] = []
    failed_pages: list[int] = []
    page_descriptors: list[AttachmentPageDescriptor] = []

    try:
        doc = fitz.open(path)
    except Exception as e:
        log.warning("Failed to open PDF for page expansion (%s): %s", path, e)
        return None
    try:
        page_count = doc.page_count
        if page_count <= 1:
            return None

        max_pages = max(1, min(page_count, Config.ATTACHMENT_MAX_PAGES))
        scale = max(1.0, Config.ATTACHMENT_RENDER_DPI / 72.0)
        matrix = fitz.Matrix(scale, scale)

        for page_index in range(max_pages):
            page_number = page_index + 1
            try:
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                output_path = _page_output_path(pdf_path, output_dir, page_number)
                pix.save(output_path)
                rendered_paths.append(output_path)
                page_descriptors.append(
                    AttachmentPageDescriptor(
                        source_name=pdf_path.name,
                        page_number=page_number,
                        upload_kind="image",
                        source_kind="pdf",
                    )
                )
            except Exception as e:
                log.warning("Failed to render PDF page %s from %s: %s", page_number, path, e)
                failed_pages.append(page_number)
    finally:
        doc.close()

    if not rendered_paths:
        return None

    notes = [_build_render_note(pdf_path.name, "page", len(rendered_paths), failed_pages, page_count)]
    fallback_files: list[str] = []
    if failed_pages:
        fallback_files.append(path)
        notes.append(f"Kept original PDF '{pdf_path.name}' as a fallback because some pages failed to render.")

    return {
        "image_paths": rendered_paths,
        "fallback_file_paths": fallback_files,
        "notes": notes,
        "page_descriptors": page_descriptors,
        "rendered_pages": len(rendered_paths),
    }


def _expand_multiframe_image(path: str) -> dict | None:
    """Expand a multi-frame image (TIFF/GIF/WebP) into ordered PNG page images."""
    try:
        from PIL import Image, ImageSequence, UnidentifiedImageError  # type: ignore
    except ImportError:
        log.debug("Pillow is not installed; skipping multi-frame expansion for %s", path)
        return None

    image_path = Path(path)
    output_dir = str(image_path.parent)
    rendered_paths: list[str] = []
    failed_pages: list[int] = []
    page_descriptors: list[AttachmentPageDescriptor] = []

    try:
        with Image.open(path) as image:
            frame_count = getattr(image, "n_frames", 1)
            if frame_count <= 1:
                return None

            max_pages = max(1, min(frame_count, Config.ATTACHMENT_MAX_PAGES))
            for frame_index, frame in enumerate(ImageSequence.Iterator(image), start=1):
                if frame_index > max_pages:
                    break
                try:
                    output_path = _page_output_path(image_path, output_dir, frame_index)
                    frame.convert("RGB").save(output_path, format="PNG")
                    rendered_paths.append(output_path)
                    page_descriptors.append(
                        AttachmentPageDescriptor(
                            source_name=image_path.name,
                            page_number=frame_index,
                            upload_kind="image",
                            source_kind="image",
                        )
                    )
                except Exception as e:
                    log.warning("Failed to render image frame %s from %s: %s", frame_index, path, e)
                    failed_pages.append(frame_index)
    except UnidentifiedImageError:
        return None
    except Exception as e:
        log.warning("Failed to open image for frame expansion (%s): %s", path, e)
        return None

    if not rendered_paths:
        return None

    notes = [_build_render_note(image_path.name, "frame", len(rendered_paths), failed_pages, frame_count)]
    fallback_images: list[str] = []
    if failed_pages:
        fallback_images.append(path)
        notes.append(f"Kept original image '{image_path.name}' as a fallback because some frames failed to render.")

    return {
        "image_paths": rendered_paths,
        "fallback_image_paths": fallback_images,
        "notes": notes,
        "page_descriptors": page_descriptors,
        "rendered_pages": len(rendered_paths),
    }


def _page_output_path(source_path: Path, output_dir: str, page_number: int) -> str:
    """Build a stable page-image output path next to the downloaded source file."""
    stem = re.sub(r"[^\w.\-]", "_", source_path.stem)
    return os.path.join(output_dir, f"{stem}_page_{page_number:03d}.png")


def _build_page_descriptor(
    path: str,
    page_number: int,
    upload_kind: str,
    source_kind: str,
) -> AttachmentPageDescriptor:
    """Build a logical page descriptor for a passthrough attachment."""
    source_name = Path(path).name or "attachment"
    return AttachmentPageDescriptor(
        source_name=source_name,
        page_number=page_number,
        upload_kind=upload_kind,
        source_kind=source_kind,
    )


def _assign_page_indexes(page_descriptors: list[AttachmentPageDescriptor]) -> None:
    """Assign stable 1-based indexes matching the page-map order exposed to the model."""
    for index, descriptor in enumerate(page_descriptors, start=1):
        descriptor.page_index = index


def _source_kind_for_file(path: str) -> str:
    """Infer a coarse source kind from the file extension."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".gif", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}:
        return "image"
    return "file"


def _build_render_note(
    source_name: str,
    unit_name: str,
    rendered_count: int,
    failed_pages: list[int],
    total_count: int,
) -> str:
    """Describe rendered page/frame coverage for the prompt prefix."""
    note = f"Expanded '{source_name}' into {rendered_count} ordered {unit_name} image(s)."
    if total_count > Config.ATTACHMENT_MAX_PAGES:
        note += f" Limited to the first {Config.ATTACHMENT_MAX_PAGES} of {total_count} {unit_name}s."
    if failed_pages:
        joined = ", ".join(str(page) for page in failed_pages)
        note += f" Skipped {unit_name}(s): {joined}."
    return note
