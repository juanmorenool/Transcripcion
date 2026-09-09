import io
from pathlib import Path
import re


# Labels accepted by the structured-script parser. They are deliberately
# tolerant to optional colons, spacing and the "Inicio" variant used by demos.
_SLIDE_RE = re.compile(r"^\s*Diapositiva\s+(\d+)\s*:?[ \t]*$", re.IGNORECASE)
_SEGMENT_RE = re.compile(
    r"^\s*Diapo\s*(\d+)\.(\d+)\s*:\s*(.*)$", re.IGNORECASE
)
_DEMO_START_RE = re.compile(
    r"^\s*(?:Inicio\s+)?Demo\s*/\s*Diapositiva\s+(\d+)\s*:?[ \t]*(.*)$",
    re.IGNORECASE,
)
_DEMO_END_RE = re.compile(
    r"^\s*Fin\s+Demo\s*/\s*Diapositiva\s+(\d+)\s*\.?\s*$",
    re.IGNORECASE,
)


def extract_script_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix == ".txt":
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return _clean_text(data.decode(encoding))
            except UnicodeDecodeError:
                continue
        raise ValueError("No pude identificar la codificación del TXT.")

    if suffix == ".docx":
        from docx import Document

        document = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
        return _clean_text(text)

    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        cleaned_text = _clean_text(text)
        if not cleaned_text.strip():
            raise ValueError(
                "El PDF no tiene texto extraíble (puede ser un escaneo); probá con TXT o DOCX."
            )
        return cleaned_text

    raise ValueError(f"Formato de guion no soportado: {suffix}")


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_segment_text(text: str) -> str:
    """Normalize whitespace inside a structured segment without changing words."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def parse_structured_script(text: str) -> list[dict] | None:
    """
    Parse a slide-structured script while preserving the exact global order.

    A segment is created for every labeled paragraph, every unlabeled paragraph
    inside a slide, and every demo block. The parser intentionally does not
    group demos separately: all segments share one monotonically increasing
    order_index based solely on their appearance in the source text.

    Returns None when no "Diapositiva N" header is found, allowing the caller
    to keep the legacy sentence/window matching path unchanged.
    """
    if not text or not text.strip():
        return None

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    # Per-line parsing lets us recognize labels even when extraction from DOCX
    # or PDF does not preserve exactly the same paragraph boundaries.
    slide_numbers = [
        int(match.group(1))
        for line in lines
        if (match := _SLIDE_RE.match(line))
    ]
    if not slide_numbers:
        return None

    segments: list[dict] = []
    current_slide: int | None = None
    pending: list[str] = []
    pending_label: str | None = None
    pending_demo = False
    demo_slide: int | None = None
    demo_parts: list[str] = []
    intro_counter: dict[int, int] = {}
    demo_counter: dict[int, int] = {}

    def append_segment(slide: int, label: str, content: str) -> None:
        content = _clean_segment_text(content)
        if not content:
            return
        segments.append(
            {
                "diapositiva": slide,
                "label": label,
                "order_index": len(segments),
                "text": content,
            }
        )

    def flush_pending() -> None:
        nonlocal pending, pending_label
        if current_slide is None:
            pending = []
            pending_label = None
            return
        content = "\n".join(pending)
        if content.strip():
            if pending_label:
                label = pending_label
            else:
                intro_counter[current_slide] = intro_counter.get(current_slide, 0) + 1
                label = f"{current_slide}-intro-{intro_counter[current_slide]}"
            append_segment(current_slide, label, content)
        pending = []
        pending_label = None

    def flush_demo() -> None:
        nonlocal demo_parts, pending_demo, demo_slide
        if demo_slide is not None:
            demo_counter[demo_slide] = demo_counter.get(demo_slide, 0) + 1
            # The first demo keeps the requested readable convention. A
            # second demo on the same slide gets a suffix so labels remain unique.
            label = (
                f"{demo_slide}-demo"
                if demo_counter[demo_slide] == 1
                else f"{demo_slide}-demo-{demo_counter[demo_slide]}"
            )
            append_segment(demo_slide, label, "\n".join(demo_parts))
        demo_parts = []
        pending_demo = False
        demo_slide = None

    for raw_line in lines:
        line = raw_line.strip()

        # A new slide header always wins over unfinished content. If a malformed
        # demo lacks its closing marker, close it at the next slide header.
        if match := _SLIDE_RE.match(raw_line):
            if pending_demo:
                flush_demo()
            else:
                flush_pending()
            current_slide = int(match.group(1))
            continue

        if pending_demo:
            if match := _DEMO_END_RE.match(raw_line):
                # Keep the demo attached to the slide declared by its opening
                # marker. The closing number is only a terminator.
                flush_demo()
            else:
                demo_parts.append(raw_line)
            continue

        if match := _DEMO_START_RE.match(raw_line):
            flush_pending()
            demo_slide = int(match.group(1))
            current_slide = demo_slide
            first_line_content = match.group(2).strip()
            demo_parts = [first_line_content] if first_line_content else []
            pending_demo = True
            continue

        if current_slide is None:
            # Ignore title material before the first recognized slide header.
            continue

        if not line:
            flush_pending()
            continue

        if match := _SEGMENT_RE.match(raw_line):
            slide = int(match.group(1))
            sub_index = match.group(2)
            current_slide = slide
            flush_pending()
            pending_label = f"{slide}.{sub_index}"
            remainder = match.group(3).strip()
            if remainder:
                pending.append(remainder)
            continue

        pending.append(raw_line)

    if pending_demo:
        flush_demo()
    else:
        flush_pending()

    return segments or None


# Alias kept explicit for callers that prefer a verb matching the app flow.
parse_script = parse_structured_script
