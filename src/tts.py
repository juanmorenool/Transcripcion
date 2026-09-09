"""
Texto a voz usando edge-tts (motor de Microsoft Edge, gratuito, sin API key).

edge-tts es async por diseño, así que exponemos una función síncrona
que internamente corre el event loop — para que sea fácil de llamar
desde Streamlit.
"""

import asyncio

import edge_tts

# Voces neuronales recomendadas para español (podés agregar más).
SPANISH_VOICES = {
    "Elvira (España, mujer)": "es-ES-ElviraNeural",
    "Álvaro (España, hombre)": "es-ES-AlvaroNeural",
    "Dalia (México, mujer)": "es-MX-DaliaNeural",
    "Jorge (México, hombre)": "es-MX-JorgeNeural",
}


def text_to_speech(text: str, voice: str = "es-ES-ElviraNeural", rate: str = "+0%") -> bytes:
    """
    Convierte texto en audio (mp3) y devuelve los bytes.

    rate: velocidad relativa, ej. "-10%", "+15%".
    """
    if not text.strip():
        raise ValueError("El texto está vacío.")

    return asyncio.run(_synthesize(text, voice, rate))


async def _synthesize(text: str, voice: str, rate: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)
