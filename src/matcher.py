import re
from rapidfuzz import fuzz


def split_into_sentences(text: str) -> list[str]:
    """
    Divide el guion en unidades comparables.
    Mantiene saltos de línea como posibles separadores y luego
    divide por puntuación final.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÜÑ0-9¿¡])", text)
    parts = [p.strip() for p in parts if p.strip()]
    return parts


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\wáéíóúüñ]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _score(transcription: str, candidate: str) -> float:
    """
    Combina varias métricas para tolerar pequeñas diferencias
    entre el guion escrito y lo que realmente se narró.
    """
    a = normalize(transcription)
    b = normalize(candidate)

    if not a or not b:
        return 0.0

    ratio = fuzz.ratio(a, b) / 100
    token_sort = fuzz.token_sort_ratio(a, b) / 100
    token_set = fuzz.token_set_ratio(a, b) / 100
    partial = fuzz.partial_ratio(a, b) / 100

    return (
        0.35 * ratio
        + 0.25 * token_sort
        + 0.25 * token_set
        + 0.15 * partial
    )


def _estimate_window_size(transcription: str, sentence_count: int) -> tuple[int, int]:
    words = len(normalize(transcription).split())
    estimated = max(1, round(words / 18))
    low = max(1, estimated - 2)
    high = min(sentence_count, estimated + 3)
    return low, high


def best_match(
    transcription: str,
    sentences: list[str],
    max_window: int = 8,
) -> dict:
    if not sentences:
        return {
            "start_sentence": 0,
            "end_sentence": 0,
            "matched_text": "",
            "confidence": 0.0,
        }

    low, high = _estimate_window_size(transcription, len(sentences))
    high = min(high, max_window)

    candidates = []

    for window in range(low, high + 1):
        for start in range(0, len(sentences) - window + 1):
            end = start + window
            candidate = " ".join(sentences[start:end])
            score = _score(transcription, candidate)
            candidates.append(
                {
                    "start_sentence": start,
                    "end_sentence": end - 1,
                    "matched_text": candidate,
                    "confidence": score,
                }
            )

    return max(candidates, key=lambda x: x["confidence"])


def match_audios_to_script(
    transcriptions: dict,
    script_text: str,
    max_window: int = 8,
) -> list[dict]:
    """Legacy sentence/window matcher. Kept unchanged for unstructured scripts."""
    sentences = split_into_sentences(script_text)

    if not sentences:
        raise ValueError("El guion no contiene texto suficiente para analizar.")

    candidates = []

    for item in transcriptions.values():
        result = best_match(
            item["text"],
            sentences,
            max_window=max_window,
        )
        candidates.append(
            {
                **result,
                "filename": item["filename"],
                "file_hash": item["file_hash"],
                "transcription": item["text"],
            }
        )

    candidates.sort(
        key=lambda x: (
            x["start_sentence"],
            -x["confidence"],
            x["filename"].lower(),
        )
    )

    for order, item in enumerate(candidates, start=1):
        item["order"] = order

    return candidates


def match_audios_to_segments(
    transcriptions: dict,
    segments: list[dict],
) -> list[dict]:
    """
    Match each audio against the complete text of every structured segment.

    Unlike the legacy matcher, the segment is already the intended unit, so no
    sentence windows are generated. Final ordering is based exclusively on the
    segment's global order_index, which correctly interleaves demos/intros with
    numbered segments.
    """
    if not segments:
        raise ValueError("El guion estructurado no contiene segmentos con texto.")

    candidates = []

    for item in transcriptions.values():
        best_segment = max(
            segments,
            key=lambda segment: _score(item["text"], segment["text"]),
        )
        score = _score(item["text"], best_segment["text"])
        candidates.append(
            {
                "diapositiva": best_segment["diapositiva"],
                "label": best_segment["label"],
                "order_index": best_segment["order_index"],
                "matched_text": best_segment["text"],
                "confidence": score,
                "filename": item["filename"],
                "file_hash": item["file_hash"],
                "transcription": item["text"],
            }
        )

    candidates.sort(
        key=lambda x: (
            x["order_index"],
            -x["confidence"],
            x["filename"].lower(),
        )
    )

    for order, item in enumerate(candidates, start=1):
        item["order"] = order

    return candidates
