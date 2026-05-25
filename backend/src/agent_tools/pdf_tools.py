import collections
import math
import re
from pathlib import Path
from typing import Iterable

import fitz
from langchain_core.tools import tool

from .applescript_tools.finder import _selected_finder_paths


MAX_TEXT_CHARS = 24000
MAX_RENDER_PAGES = 30
MAX_EXTRACTED_IMAGES = 80
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]{2,}")
STOP_WORDS = {
    "about",
    "after",
    "also",
    "because",
    "been",
    "being",
    "between",
    "could",
    "does",
    "from",
    "have",
    "into",
    "more",
    "other",
    "their",
    "there",
    "these",
    "this",
    "those",
    "through",
    "under",
    "using",
    "were",
    "where",
    "which",
    "while",
    "with",
    "would",
}


def _resolve_pdf_path(pdf_path: str = "") -> Path:
    if pdf_path.strip():
        path = Path(pdf_path).expanduser()
    else:
        paths = [Path(item) for item in _selected_finder_paths()]
        if not paths:
            raise ValueError("Provide a PDF path or select one PDF in Finder.")
        pdf_paths = [path for path in paths if path.suffix.lower() == ".pdf"]
        if len(pdf_paths) != 1:
            raise ValueError("Select exactly one PDF in Finder.")
        path = pdf_paths[0]

    if not path.exists():
        raise ValueError(f"PDF not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Path is not a PDF: {path}")
    return path


def _parse_page_selection(pages: str, page_count: int, limit: int | None = None) -> list[int]:
    if page_count < 1:
        return []

    if not pages.strip():
        selected = list(range(page_count))
    else:
        selected_set: set[int] = set()
        for raw_part in pages.split(","):
            part = raw_part.strip()
            if not part:
                continue
            if "-" in part:
                start_raw, end_raw = part.split("-", 1)
                start = int(start_raw.strip())
                end = int(end_raw.strip())
                if start > end:
                    start, end = end, start
                selected_set.update(range(start - 1, end))
            else:
                selected_set.add(int(part) - 1)

        selected = sorted(index for index in selected_set if 0 <= index < page_count)

    if limit is not None:
        selected = selected[:limit]
    return selected


def _metadata_lines(path: Path, doc: fitz.Document) -> list[str]:
    metadata = doc.metadata or {}
    encrypted = "yes" if doc.is_encrypted else "no"
    lines = [
        f"File: {path}",
        f"Pages: {doc.page_count}",
        f"Encrypted: {encrypted}",
        f"Size: {path.stat().st_size:,} bytes",
    ]
    for key in (
        "title",
        "author",
        "subject",
        "keywords",
        "creator",
        "producer",
        "creationDate",
        "modDate",
    ):
        value = metadata.get(key)
        if value:
            lines.append(f"{key}: {value}")
    return lines


def _extract_text_from_doc(
    doc: fitz.Document,
    page_indices: Iterable[int],
    max_chars: int,
) -> str:
    chunks: list[str] = []
    remaining = max(1, max_chars)
    for index in page_indices:
        page = doc.load_page(index)
        text = page.get_text("text").strip()
        if not text:
            text = "[No selectable text found on this page.]"
        page_chunk = f"--- Page {index + 1} ---\n{text}\n"
        chunks.append(page_chunk[:remaining])
        remaining -= len(page_chunk)
        if remaining <= 0:
            chunks.append("\n[Output truncated.]")
            break
    return "\n".join(chunks).strip()


def _extract_markdown_page(page: fitz.Page) -> str:
    try:
        return page.get_text("markdown").strip()
    except Exception:
        return page.get_text("text").strip()


def _sentence_score(sentence: str, frequencies: collections.Counter[str]) -> float:
    words = [word.lower() for word in WORD_RE.findall(sentence)]
    if not words:
        return 0.0
    score = sum(frequencies[word] for word in words if word not in STOP_WORDS)
    return score / math.sqrt(len(words))


def _summarize_text(text: str, max_sentences: int) -> str:
    clean_text = re.sub(r"\s+", " ", text).strip()
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_RE.split(clean_text)
        if len(sentence.strip()) > 30
    ]
    if not sentences:
        return clean_text[:1200] or "No text available to summarize."

    words = [
        word.lower()
        for word in WORD_RE.findall(clean_text)
        if word.lower() not in STOP_WORDS
    ]
    frequencies = collections.Counter(words)
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: _sentence_score(item[1], frequencies),
        reverse=True,
    )
    selected_indices = sorted(index for index, _ in ranked[: max(1, max_sentences)])
    return "\n".join(f"- {sentences[index]}" for index in selected_indices)


@tool
def get_pdf_metadata(pdf_path: str = "", include_outline: bool = True) -> str:
    """
    Returns metadata for a PDF. If pdf_path is empty, uses the selected Finder PDF.

    Args:
        pdf_path: Optional POSIX path to a PDF file.
        include_outline: Include table-of-contents entries when available.
    """
    try:
        path = _resolve_pdf_path(pdf_path)
        with fitz.open(path) as doc:
            lines = _metadata_lines(path, doc)
            if include_outline:
                toc = doc.get_toc(simple=True)
                if toc:
                    lines.append("Outline:")
                    for level, title, page in toc[:80]:
                        indent = "  " * max(0, level - 1)
                        lines.append(f"{indent}- p{page}: {title}")
                    if len(toc) > 80:
                        lines.append(f"... {len(toc) - 80} more outline entries.")
            return "\n".join(lines)
    except Exception as exc:
        return f"PDF metadata extraction failed: {exc}"


@tool
def extract_pdf_text(
    pdf_path: str = "",
    pages: str = "",
    max_chars: int = MAX_TEXT_CHARS,
) -> str:
    """
    Extracts selectable text from a PDF. If pdf_path is empty, uses the selected Finder PDF.

    Args:
        pdf_path: Optional POSIX path to a PDF file.
        pages: Optional 1-based page selection, for example "1,3-5". Empty means all pages.
        max_chars: Maximum characters returned to the agent.
    """
    try:
        path = _resolve_pdf_path(pdf_path)
        with fitz.open(path) as doc:
            page_indices = _parse_page_selection(pages, doc.page_count)
            if not page_indices:
                return "No matching PDF pages found."
            return _extract_text_from_doc(doc, page_indices, max_chars)
    except Exception as exc:
        return f"PDF text extraction failed: {exc}"


@tool
def convert_pdf_to_markdown(
    pdf_path: str = "",
    output_path: str = "",
    pages: str = "",
) -> str:
    """
    Converts a PDF to a Markdown file. If pdf_path is empty, uses the selected Finder PDF.

    Args:
        pdf_path: Optional POSIX path to a PDF file.
        output_path: Optional POSIX path for the Markdown file. Defaults next to the PDF.
        pages: Optional 1-based page selection, for example "1,3-5". Empty means all pages.
    """
    try:
        path = _resolve_pdf_path(pdf_path)
        target_path = (
            Path(output_path).expanduser() if output_path.strip() else path.with_suffix(".md")
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with fitz.open(path) as doc:
            page_indices = _parse_page_selection(pages, doc.page_count)
            if not page_indices:
                return "No matching PDF pages found."
            chunks = [f"# {path.stem}", ""]
            for index in page_indices:
                page = doc.load_page(index)
                chunks.append(f"## Page {index + 1}")
                chunks.append("")
                chunks.append(_extract_markdown_page(page) or "_No selectable text found._")
                chunks.append("")

        target_path.write_text("\n".join(chunks).strip() + "\n", encoding="utf-8")
        return f"Converted PDF to Markdown: {target_path}"
    except Exception as exc:
        return f"PDF to Markdown conversion failed: {exc}"


@tool
def summarize_pdf(
    pdf_path: str = "",
    pages: str = "",
    max_sentences: int = 8,
    max_source_chars: int = 50000,
) -> str:
    """
    Creates a concise extractive summary from PDF text. If pdf_path is empty, uses the selected Finder PDF.

    Args:
        pdf_path: Optional POSIX path to a PDF file.
        pages: Optional 1-based page selection, for example "1,3-5". Empty means all pages.
        max_sentences: Maximum bullet points in the summary.
        max_source_chars: Maximum extracted source characters used for summarization.
    """
    try:
        path = _resolve_pdf_path(pdf_path)
        with fitz.open(path) as doc:
            page_indices = _parse_page_selection(pages, doc.page_count)
            if not page_indices:
                return "No matching PDF pages found."
            text = _extract_text_from_doc(doc, page_indices, max_source_chars)
        summary = _summarize_text(text, max(1, min(20, max_sentences)))
        return f"Extractive summary of {path.name}:\n{summary}"
    except Exception as exc:
        return f"PDF summarization failed: {exc}"


@tool
def render_pdf_pages_to_images(
    pdf_path: str = "",
    output_dir: str = "",
    pages: str = "1",
    dpi: int = 150,
    image_format: str = "png",
) -> str:
    """
    Renders PDF pages to image files. If pdf_path is empty, uses the selected Finder PDF.

    Args:
        pdf_path: Optional POSIX path to a PDF file.
        output_dir: Optional output folder. Defaults to a folder next to the PDF.
        pages: 1-based page selection, for example "1,3-5". Empty means first pages up to the safety limit.
        dpi: Rendering DPI from 72 to 300.
        image_format: png, jpg, or jpeg.
    """
    try:
        path = _resolve_pdf_path(pdf_path)
        fmt = image_format.lower().strip(".")
        if fmt == "jpeg":
            fmt = "jpg"
        if fmt not in {"png", "jpg"}:
            return "Image format must be png, jpg, or jpeg."

        safe_dpi = max(72, min(300, int(dpi)))
        target_dir = (
            Path(output_dir).expanduser()
            if output_dir.strip()
            else path.with_suffix("").parent / f"{path.stem}-pages"
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        created_paths: list[Path] = []
        with fitz.open(path) as doc:
            page_indices = _parse_page_selection(pages, doc.page_count, MAX_RENDER_PAGES)
            if not page_indices:
                return "No matching PDF pages found."
            matrix = fitz.Matrix(safe_dpi / 72, safe_dpi / 72)
            for index in page_indices:
                page = doc.load_page(index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image_path = target_dir / f"{path.stem}-page-{index + 1:03d}.{fmt}"
                pixmap.save(image_path)
                created_paths.append(image_path)

        return "Rendered PDF pages:\n" + "\n".join(f"- {item}" for item in created_paths)
    except Exception as exc:
        return f"PDF page rendering failed: {exc}"


@tool
def search_pdf_text(
    query: str,
    pdf_path: str = "",
    pages: str = "",
    max_matches: int = 20,
) -> str:
    """
    Searches text inside a PDF and returns page numbers with snippets.

    Args:
        query: Search text or phrase.
        pdf_path: Optional POSIX path to a PDF file.
        pages: Optional 1-based page selection, for example "1,3-5". Empty means all pages.
        max_matches: Maximum matches returned.
    """
    if not query.strip():
        return "Search query cannot be empty."

    try:
        path = _resolve_pdf_path(pdf_path)
        needle = query.strip().lower()
        matches: list[str] = []
        with fitz.open(path) as doc:
            page_indices = _parse_page_selection(pages, doc.page_count)
            for index in page_indices:
                text = doc.load_page(index).get_text("text")
                lower_text = text.lower()
                start = 0
                while len(matches) < max(1, min(100, max_matches)):
                    found = lower_text.find(needle, start)
                    if found == -1:
                        break
                    snippet_start = max(0, found - 120)
                    snippet_end = min(len(text), found + len(query) + 120)
                    snippet = re.sub(r"\s+", " ", text[snippet_start:snippet_end]).strip()
                    matches.append(f"- Page {index + 1}: ...{snippet}...")
                    start = found + len(needle)
                if len(matches) >= max_matches:
                    break

        if not matches:
            return f"No matches found for {query!r} in {path.name}."
        return f"Matches for {query!r} in {path.name}:\n" + "\n".join(matches)
    except Exception as exc:
        return f"PDF search failed: {exc}"


@tool
def extract_pdf_images(
    pdf_path: str = "",
    output_dir: str = "",
    pages: str = "",
    max_images: int = MAX_EXTRACTED_IMAGES,
) -> str:
    """
    Extracts embedded raster images from a PDF. If pdf_path is empty, uses the selected Finder PDF.

    Args:
        pdf_path: Optional POSIX path to a PDF file.
        output_dir: Optional output folder. Defaults to a folder next to the PDF.
        pages: Optional 1-based page selection, for example "1,3-5". Empty means all pages.
        max_images: Maximum embedded images to extract.
    """
    try:
        path = _resolve_pdf_path(pdf_path)
        target_dir = (
            Path(output_dir).expanduser()
            if output_dir.strip()
            else path.with_suffix("").parent / f"{path.stem}-images"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        limit = max(1, min(MAX_EXTRACTED_IMAGES, max_images))

        created_paths: list[Path] = []
        with fitz.open(path) as doc:
            page_indices = _parse_page_selection(pages, doc.page_count)
            for index in page_indices:
                page = doc.load_page(index)
                for image_number, image in enumerate(page.get_images(full=True), start=1):
                    if len(created_paths) >= limit:
                        break
                    xref = image[0]
                    extracted = doc.extract_image(xref)
                    extension = extracted.get("ext", "png")
                    image_path = (
                        target_dir
                        / f"{path.stem}-page-{index + 1:03d}-image-{image_number:02d}.{extension}"
                    )
                    image_path.write_bytes(extracted["image"])
                    created_paths.append(image_path)
                if len(created_paths) >= limit:
                    break

        if not created_paths:
            return f"No embedded images found in {path.name}."
        return "Extracted PDF images:\n" + "\n".join(f"- {item}" for item in created_paths)
    except Exception as exc:
        return f"PDF image extraction failed: {exc}"


@tool
def split_pdf_pages(
    pdf_path: str = "",
    output_path: str = "",
    pages: str = "",
) -> str:
    """
    Saves selected PDF pages to a new PDF. If pdf_path is empty, uses the selected Finder PDF.

    Args:
        pdf_path: Optional POSIX path to a PDF file.
        output_path: Optional output PDF path. Defaults next to the source PDF.
        pages: 1-based page selection, for example "1,3-5". Empty means all pages.
    """
    try:
        path = _resolve_pdf_path(pdf_path)
        target_path = (
            Path(output_path).expanduser()
            if output_path.strip()
            else path.with_name(f"{path.stem}-selected-pages.pdf")
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open(path) as source_doc:
            page_indices = _parse_page_selection(pages, source_doc.page_count)
            if not page_indices:
                return "No matching PDF pages found."
            with fitz.open() as output_doc:
                for index in page_indices:
                    output_doc.insert_pdf(source_doc, from_page=index, to_page=index)
                output_doc.save(target_path)
        return f"Created PDF with selected pages: {target_path}"
    except Exception as exc:
        return f"PDF split failed: {exc}"


pdf_tools = [
    get_pdf_metadata,
    extract_pdf_text,
    convert_pdf_to_markdown,
    summarize_pdf,
    render_pdf_pages_to_images,
    search_pdf_text,
    extract_pdf_images,
    split_pdf_pages,
]


__all__ = [
    "convert_pdf_to_markdown",
    "extract_pdf_images",
    "extract_pdf_text",
    "get_pdf_metadata",
    "pdf_tools",
    "render_pdf_pages_to_images",
    "search_pdf_text",
    "split_pdf_pages",
    "summarize_pdf",
]
