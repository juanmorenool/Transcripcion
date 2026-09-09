import re
import math
from typing import Dict, List

from rapidfuzz import fuzz


def split_into_sentences(text: str) -> List[str]:
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
    sentences: List[str],
    max_window: int = 8,
) -> Dict:
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


def _tokens(text: str) -> set[str]:
    """Return normalized lexical tokens used by the structured matcher."""
    return set(normalize(text).split())


def _structured_term_weights(segments: List[dict]) -> Dict[str, float]:
    """
    Give more weight to terms that distinguish one structured segment from
    the others. Generic words such as 'serie', 'modelo' or 'resultado' tend
    to occur across many segments and therefore receive less weight, while
    technical terms such as 'adf', 'estacionariedad' or 'sarimax' become
    strong matching signals when they are concentrated in a few segments.
    """
    document_frequency: Dict[str, int] = {}
    total_segments = len(segments)

    for segment in segments:
        for token in _tokens(segment["text"]):
            document_frequency[token] = document_frequency.get(token, 0) + 1

    weights: Dict[str, float] = {}
    for token, frequency in document_frequency.items():
        # Smoothed IDF. A term present in every segment gets weight 1; a term
        # present in only one segment gets a substantially larger weight.
        weights[token] = 1.0 + math.log(
            (total_segments + 1) / (frequency + 1)
        )

    return weights


def _structured_score(
    transcription: str,
    candidate: str,
    term_weights: Dict[str, float],
) -> float:
    """Score a structured segment using both fuzzy similarity and distinctive terms."""
    base = _score(transcription, candidate)

    transcription_tokens = _tokens(transcription)
    candidate_tokens = _tokens(candidate)
    if not transcription_tokens or not candidate_tokens:
        return base

    overlap = transcription_tokens & candidate_tokens

    # Weighted recall asks: how many of the informative words from the audio
    # are actually explained by this segment?
    transcription_weight = sum(
        term_weights.get(token, 1.0) for token in transcription_tokens
    )
    candidate_weight = sum(
        term_weights.get(token, 1.0) for token in candidate_tokens
    )
    overlap_weight = sum(
        term_weights.get(token, 1.0) for token in overlap
    )

    weighted_recall = overlap_weight / transcription_weight if transcription_weight else 0.0
    weighted_precision = overlap_weight / candidate_weight if candidate_weight else 0.0

    if weighted_recall + weighted_precision:
        weighted_f1 = (
            2 * weighted_recall * weighted_precision
            / (weighted_recall + weighted_precision)
        )
    else:
        weighted_f1 = 0.0

    # Exact matches of distinctive terms deserve an additional signal. This
    # prevents a long generic segment from beating a shorter segment that
    # contains the key technical concept being narrated.
    distinctive_overlap = sum(
        term_weights.get(token, 1.0)
        for token in overlap
        if term_weights.get(token, 1.0) >= 1.75
    )
    distinctive_total = sum(
        term_weights.get(token, 1.0)
        for token in transcription_tokens
        if term_weights.get(token, 1.0) >= 1.75
    )
    distinctive_recall = (
        distinctive_overlap / distinctive_total
        if distinctive_total
        else weighted_recall
    )

    return (
        0.45 * base
        + 0.35 * weighted_f1
        + 0.20 * distinctive_recall
    )


def match_audios_to_segments(
    transcriptions: dict,
    segments: list[dict],
) -> list[dict]:
    """
    Match each audio against the complete text of every structured segment.

    Structured matching gives additional weight to distinctive terms based on
    how frequently they occur across the script. This keeps generic domain
    vocabulary from dominating the match while strongly rewarding technical
    terms that identify the intended segment.

    Unlike the legacy matcher, the segment is already the intended unit, so no
    sentence windows are generated. Final ordering is based exclusively on the
    segment's global order_index, which correctly interleaves demos/intros with
    numbered segments.
    """
    if not segments:
        raise ValueError("El guion estructurado no contiene segmentos con texto.")

    term_weights = _structured_term_weights(segments)
    candidates = []

    for item in transcriptions.values():
        best_segment = max(
            segments,
            key=lambda segment: _structured_score(
                item["text"],
                segment["text"],
                term_weights,
            ),
        )
        score = _structured_score(
            item["text"],
            best_segment["text"],
            term_weights,
        )
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
