import io
from pathlib import Path
import re


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
