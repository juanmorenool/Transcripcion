from io import BytesIO
from elevenlabs.client import ElevenLabs


class ElevenLabsTranscriber:
    def __init__(self, api_key: str):
        self.client = ElevenLabs(api_key=api_key)

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language_code: str | None = "spa",
    ) -> dict:
        audio = BytesIO(audio_bytes)
        audio.name = filename

        response = self.client.speech_to_text.convert(
            file=audio,
            model_id="scribe_v2",
            language_code=language_code,
            diarize=False,
            tag_audio_events=False,
        )

        return {
            "text": getattr(response, "text", "") or "",
            "language_code": getattr(response, "language_code", None),
            "language_probability": getattr(
                response, "language_probability", None
            ),
            "words": self._serialize_words(getattr(response, "words", [])),
        }

    @staticmethod
    def _serialize_words(words):
        result = []
        for word in words or []:
            if hasattr(word, "model_dump"):
                result.append(word.model_dump())
            elif hasattr(word, "dict"):
                result.append(word.dict())
            elif isinstance(word, dict):
                result.append(word)
            else:
                result.append(
                    {
                        "text": getattr(word, "text", ""),
                        "start": getattr(word, "start", None),
                        "end": getattr(word, "end", None),
                        "type": getattr(word, "type", None),
                        "speaker_id": getattr(word, "speaker_id", None),
                    }
                )
        return result
