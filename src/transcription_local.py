"""
Transcriptor local con faster-whisper (sin API, 100% gratuito).

Mantiene la MISMA interfaz que src/transcription.ElevenLabsTranscriber
para que app.py no necesite cambios, salvo la línea de importación
y la creación del objeto.
"""

import io
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel


class LocalWhisperTranscriber:
    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8"):
        """
        model_size: "tiny", "base", "small", "medium", "large-v3"
            - En Streamlit Cloud (free tier, ~1GB RAM): usa "small" como máximo.
            - En tu máquina local con más RAM: "medium" da mejor calidad.
        compute_type: "int8" es el más liviano en CPU (recomendado).
        """
        # El modelo se descarga una sola vez (~500MB para "small") y se
        # cachea en disco; en Streamlit Cloud puede tardar la primera vez.
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language_code: str | None = "es",
    ) -> dict:
        # faster-whisper necesita un archivo en disco (usa ffmpeg internamente
        # vía av/ctranslate2), así que escribimos un temporal.
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()

            # ElevenLabs usa códigos ISO 639-2 ("spa"); Whisper usa 639-1 ("es").
            whisper_lang = self._normalize_lang(language_code)

            segments, info = self.model.transcribe(
                tmp.name,
                language=whisper_lang,
                vad_filter=True,  # filtra silencios, mejora precisión de tiempos
                word_timestamps=True,
            )

            text_parts = []
            words = []
            for seg in segments:
                text_parts.append(seg.text.strip())
                for w in (seg.words or []):
                    words.append(
                        {
                            "text": w.word,
                            "start": w.start,
                            "end": w.end,
                            "type": "word",
                            "speaker_id": None,
                        }
                    )

            return {
                "text": " ".join(text_parts).strip(),
                "language_code": info.language,
                "language_probability": info.language_probability,
                "words": words,
            }

    @staticmethod
    def _normalize_lang(code: str | None) -> str | None:
        if not code:
            return None
        mapping = {"spa": "es", "eng": "en"}
        return mapping.get(code, code)
