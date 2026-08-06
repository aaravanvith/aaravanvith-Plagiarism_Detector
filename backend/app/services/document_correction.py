"""Creation of corrected document copies using extraction-text offsets."""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from docx import Document

from .extract import extract_text


class CorrectionValidationError(ValueError):
    """Raised when a client submits offsets that do not describe its upload."""


def parse_corrections(raw_corrections: str) -> list[dict]:
    try:
        corrections = json.loads(raw_corrections)
    except json.JSONDecodeError as exc:
        raise CorrectionValidationError("Corrections must be valid JSON.") from exc
    if not isinstance(corrections, list) or not corrections:
        raise CorrectionValidationError("No corrections available.")
    return corrections


def apply_offset_corrections(text: str, corrections: list[dict]) -> str:
    """Apply non-overlapping corrections right-to-left without string replace.

    Descending offsets protect every earlier span when a later rewrite changes
    length.  Validation also makes a stale preview or tampered request safe.
    """
    normalized: list[tuple[int, int, str]] = []
    for correction in corrections:
        try:
            start = int(correction["start_offset"])
            end = int(correction["end_offset"])
            original = str(correction["original"])
            corrected = str(correction["corrected"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CorrectionValidationError("Each correction requires original, corrected, start_offset, and end_offset.") from exc
        if start < 0 or end <= start or end > len(text) or not corrected.strip():
            raise CorrectionValidationError("One or more correction offsets are invalid.")
        # Extraction may contain line wrapping that was normalized for display.
        if " ".join(text[start:end].split()) != " ".join(original.split()):
            raise CorrectionValidationError("A correction does not match the uploaded document at its offsets.")
        normalized.append((start, end, corrected))

    ordered = sorted(normalized, key=lambda item: item[0], reverse=True)
    previous_start = len(text) + 1
    for start, end, corrected in ordered:
        if end > previous_start:
            raise CorrectionValidationError("Correction offsets overlap.")
        text = text[:start] + corrected + text[end:]
        previous_start = start
    return text


def create_corrected_file(filename: str, content: bytes, corrections: list[dict]) -> tuple[Path, str, str, dict]:
    """Write a new corrected TXT, DOCX, or simple text PDF; source bytes stay untouched."""
    lower = filename.lower()
    try:
        extracted = extract_text(filename, content)
    except Exception as exc:
        raise RuntimeError("The uploaded file could not be processed.") from exc
    if not extracted.strip():
        raise RuntimeError("The uploaded file could not be processed.")

    output_dir = Path(tempfile.mkdtemp(prefix="plagiarism-corrected-"))
    if lower.endswith(".docx"):
        output = output_dir / "Corrected_Report.docx"
        summary = _correct_docx(content, extracted, corrections, output)
        return output, output.name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", summary

    corrected = apply_offset_corrections(extracted, corrections)
    if lower.endswith(".pdf"):
        output = output_dir / "Corrected_Report.pdf"
        _write_text_pdf(corrected, output)
        return output, output.name, "application/pdf", {"applied": len(corrections), "skipped": []}
    if lower.endswith((".txt", ".md", ".markdown")):
        output = output_dir / "Corrected_Report.txt"
        output.write_text(corrected, encoding="utf-8")
        return output, output.name, "text/plain; charset=utf-8", {"applied": len(corrections), "skipped": []}
    raise RuntimeError("Unsupported file type. Use PDF, DOCX, or TXT.")


def _paragraph_ranges(paragraphs) -> list[tuple[int, int]]:
    """Return offsets matching ``extract_text``'s newline-separated DOCX text."""
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for paragraph in paragraphs:
        end = cursor + len(paragraph.text)
        ranges.append((cursor, end))
        cursor = end + 1
    return ranges


def find_paragraph_range(paragraph_ranges: list[tuple[int, int]], start: int, end: int) -> tuple[int, int] | None:
    """Find the inclusive paragraph indexes containing an extracted-text span."""
    first = next((i for i, (p_start, p_end) in enumerate(paragraph_ranges) if p_start <= start <= p_end), None)
    # ``end`` is exclusive, so an edit ending at a paragraph boundary belongs
    # to that paragraph instead of the following newline/paragraph.
    last = next((i for i, (p_start, p_end) in enumerate(paragraph_ranges) if p_start <= end <= p_end), None)
    if first is None or last is None or last < first:
        return None
    return first, last


def extract_multi_paragraph_text(paragraphs, first: int, last: int) -> str:
    return "\n".join(paragraph.text for paragraph in paragraphs[first:last + 1])


def _replace_run_text(paragraph, start: int, end: int, replacement: str) -> None:
    """Replace a character span without resetting paragraph or run formatting."""
    if start < 0 or end < start or end > len(paragraph.text):
        raise CorrectionValidationError("A correction does not match the uploaded document at its offsets.")

    runs = list(paragraph.runs)
    if not runs:
        if start != 0 or end != 0:
            raise CorrectionValidationError("A correction does not match the uploaded document at its offsets.")
        paragraph.add_run(replacement)
        return

    cursor = 0
    start_run = end_run = None
    start_local = end_local = 0
    for index, run in enumerate(runs):
        run_end = cursor + len(run.text)
        if start_run is None and cursor <= start <= run_end:
            start_run, start_local = index, start - cursor
        if cursor <= end <= run_end:
            end_run, end_local = index, end - cursor
            break
        cursor = run_end

    if start_run is None or end_run is None:
        raise CorrectionValidationError("A correction does not match the uploaded document at its offsets.")
    if start_run == end_run:
        run = runs[start_run]
        run.text = run.text[:start_local] + replacement + run.text[end_local:]
        return

    runs[start_run].text = runs[start_run].text[:start_local] + replacement
    for index in range(start_run + 1, end_run):
        runs[index].text = ""
    runs[end_run].text = runs[end_run].text[end_local:]


def replace_single_paragraph(paragraph, start: int, end: int, replacement: str) -> None:
    _replace_run_text(paragraph, start, end, replacement)


def replace_multi_paragraph(paragraphs, first: int, last: int, start: int, end: int, replacement: str) -> None:
    """Replace across paragraphs while retaining every paragraph and its style."""
    replace_single_paragraph(paragraphs[first], start, len(paragraphs[first].text), replacement)
    for index in range(first + 1, last):
        replace_single_paragraph(paragraphs[index], 0, len(paragraphs[index].text), "")
    replace_single_paragraph(paragraphs[last], 0, end, "")


def _correction_values(correction: dict) -> tuple[int, int, str, str]:
    try:
        return (
            int(correction["start_offset"]),
            int(correction["end_offset"]),
            str(correction["original"]),
            str(correction["corrected"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CorrectionValidationError("Each correction requires original, corrected, start_offset, and end_offset.") from exc


def _correct_docx(content: bytes, extracted: str, corrections: list[dict], output: Path) -> dict:
    document = Document(io.BytesIO(content))
    paragraphs = document.paragraphs
    paragraph_ranges = _paragraph_ranges(paragraphs)
    candidates: list[tuple[int, int, int, int, str]] = []
    skipped: list[dict] = []

    # Validate and index once against the untouched source document. Applying
    # from right to left keeps those original offsets valid for every edit.
    for correction in corrections:
        try:
            start, end, original, replacement = _correction_values(correction)
            if start < 0 or end <= start or end > len(extracted) or not replacement.strip():
                raise CorrectionValidationError("One or more correction offsets are invalid.")
            if " ".join(extracted[start:end].split()) != " ".join(original.split()):
                raise CorrectionValidationError("A correction does not match the uploaded document at its offsets.")
            paragraph_span = find_paragraph_range(paragraph_ranges, start, end)
            if paragraph_span is None:
                raise CorrectionValidationError("A correction does not map to document paragraphs.")
            first, last = paragraph_span
            candidates.append((start, end, first, last, replacement))
        except CorrectionValidationError as exc:
            skipped.append({"reason": str(exc)})

    previous_start = len(extracted) + 1
    for start, end, first, last, replacement in sorted(candidates, reverse=True):
        if end > previous_start:
            skipped.append({"reason": "Correction offsets overlap."})
            continue
        try:
            first_start = start - paragraph_ranges[first][0]
            last_end = end - paragraph_ranges[last][0]
            if first == last:
                replace_single_paragraph(paragraphs[first], first_start, last_end, replacement)
            else:
                replace_multi_paragraph(paragraphs, first, last, first_start, last_end, replacement)
            previous_start = start
        except Exception as exc:
            skipped.append({"reason": f"Could not apply correction: {exc}"})

    document.save(output)
    return {"applied": len(corrections) - len(skipped), "skipped": skipped}


def _write_text_pdf(text: str, output: Path) -> None:
    """Create a standards-compliant, text-only PDF without a new dependency."""
    lines = []
    for source_line in text.splitlines() or [""]:
        remaining = source_line
        while len(remaining) > 95:
            lines.append(remaining[:95])
            remaining = remaining[95:]
        lines.append(remaining)
    pages = [lines[index:index + 46] for index in range(0, len(lines), 46)] or [[]]
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    page_ids: list[int] = []
    for page in pages:
        stream_lines = ["BT", "/F1 10 Tf", "50 780 Td", "12 TL"]
        for line in page:
            safe = line.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"({safe}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines)
        content_id = len(objects) + 2
        page_id = content_id + 1
        objects.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {content_id} 0 R >>")
        page_ids.append(page_id)
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>"
    payload = "%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(payload.encode("latin-1")))
        payload += f"{number} 0 obj\n{obj}\nendobj\n"
    xref = len(payload.encode("latin-1"))
    payload += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    payload += "".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
    payload += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    output.write_bytes(payload.encode("latin-1"))
