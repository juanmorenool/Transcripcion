
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from src.script_parser import extract_script_text
from src.transcription_local import LocalWhisperTranscriber
from src.matcher import match_audios_to_script
from src.utils import file_sha256


st.set_page_config(
    page_title="Organizador de Narraciones",
    page_icon=None,
    layout="wide",
)

st.title("Organizador de Narraciones")
st.caption("Transcribe tus audios y los ordena automáticamente según el guion.")

# -----------------------------
# Session state
# -----------------------------
for key, default in {
    "transcriptions": {},
    "matches": None,
    "script_text": "",
    "script_units": [],
    "audio_files": {},
    "transcriber": None,
    "transcriber_model_size": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Configuración")
    language = st.selectbox(
        "Idioma de los audios",
        ["Español", "Detectar automáticamente"],
        index=0,
    )
    language_code = "es" if language == "Español" else None

    max_window = st.slider(
        "Máximo de frases por fragmento",
        min_value=3,
        max_value=15,
        value=8,
        help="Aumenta este valor si cada audio contiene fragmentos largos del guion.",
    )

    st.divider()
    st.markdown("**Modelo de transcripción (local, sin API)**")
    model_size = st.selectbox(
        "Tamaño del modelo Whisper",
        ["tiny", "base", "small", "medium"],
        index=2,
        help=(
            "Modelos más grandes son más precisos pero más lentos y "
            "requieren más memoria. En Streamlit Community Cloud (free tier) "
            "se recomienda no pasar de 'small'."
        ),
    )
    st.caption(
        "La primera vez que uses un tamaño de modelo, se descargará "
        "automáticamente (puede tardar un poco)."
    )


# -----------------------------
# Inputs
# -----------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Guion")
    script_file = st.file_uploader(
        "Sube el guion",
        type=["txt", "docx", "pdf"],
        accept_multiple_files=False,
        help="Se aceptan TXT, DOCX y PDF.",
    )

with col2:
    st.subheader("2. Audios")
    audio_files = st.file_uploader(
        "Sube uno o varios audios",
        type=["mp3", "wav", "m4a", "mp4", "aac", "ogg", "flac"],
        accept_multiple_files=True,
        help="Puedes seleccionar todos los fragmentos de una vez.",
    )


# -----------------------------
# Read script
# -----------------------------
if script_file:
    try:
        script_text = extract_script_text(
            script_file.name,
            script_file.getvalue(),
        )
        st.session_state.script_text = script_text
        st.session_state.script_units = None
        st.success(f"Guion cargado: {len(script_text.split())} palabras.")
        with st.expander("Ver guion"):
            st.text_area(
                "Contenido",
                script_text,
                height=250,
                label_visibility="collapsed",
            )
    except Exception as exc:
        st.error(f"No pude leer el guion: {exc}")


# -----------------------------
# Store uploaded audio bytes
# -----------------------------
if audio_files:
    st.session_state.audio_files = {
        file_sha256(f.getvalue()): {
            "name": f.name,
            "bytes": f.getvalue(),
            "type": f.type or "audio/mpeg",
        }
        for f in audio_files
    }

    st.info(f"{len(audio_files)} archivo(s) de audio cargado(s).")


# -----------------------------
# Transcription
# -----------------------------
st.divider()
st.subheader("Transcripción")

if st.button(
    "Transcribir audios",
    type="primary",
    disabled=not audio_files,
    use_container_width=True,
):
    # Reutilizamos el modelo cargado si ya se pidió ese mismo tamaño antes,
    # para no volver a cargarlo en cada clic.
    if (
        st.session_state.transcriber is None
        or st.session_state.transcriber_model_size != model_size
    ):
        with st.spinner(f"Cargando modelo Whisper ({model_size})..."):
            st.session_state.transcriber = LocalWhisperTranscriber(
                model_size=model_size
            )
            st.session_state.transcriber_model_size = model_size

    transcriber = st.session_state.transcriber

    progress = st.progress(0)
    status = st.empty()

    total = len(audio_files)
    for i, uploaded in enumerate(audio_files, start=1):
        file_hash = file_sha256(uploaded.getvalue())

        if file_hash in st.session_state.transcriptions:
            status.write(f"Ya transcrito: {uploaded.name}")
            progress.progress(i / total)
            continue

        status.write(
            f"Transcribiendo {uploaded.name} ({i}/{total})..."
        )

        try:
            result = transcriber.transcribe(
                uploaded.getvalue(),
                filename=uploaded.name,
                language_code=language_code,
            )

            st.session_state.transcriptions[file_hash] = {
                "file_hash": file_hash,
                "filename": uploaded.name,
                "text": result["text"],
                "language_code": result.get("language_code"),
                "language_probability": result.get("language_probability"),
                "words": result.get("words", []),
            }

        except Exception as exc:
            st.error(f"Error en {uploaded.name}: {exc}")

        progress.progress(i / total)

    status.success("Transcripción terminada.")


# -----------------------------
# Transcription results
# -----------------------------
if st.session_state.transcriptions:
    rows = []

    for item in st.session_state.transcriptions.values():
        rows.append(
            {
                "Archivo": item["filename"],
                "Palabras": len(item["text"].split()),
                "Idioma": item.get("language_code") or "",
                "Transcripción": item["text"],
            }
        )

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )


# -----------------------------
# Matching
# -----------------------------
st.divider()
st.subheader("Organización según el guion")

if st.button(
    "Identificar y ordenar audios",
    type="primary",
    disabled=not (
        bool(st.session_state.script_text)
        and bool(st.session_state.transcriptions)
    ),
    use_container_width=True,
):
    with st.spinner("Comparando las transcripciones con el guion..."):
        st.session_state.matches = match_audios_to_script(
            st.session_state.transcriptions,
            st.session_state.script_text,
            max_window=max_window,
        )


if st.session_state.matches:
    matches = st.session_state.matches

    high = sum(m["confidence"] >= 0.85 for m in matches)
    medium = sum(
        0.65 <= m["confidence"] < 0.85
        for m in matches
    )
    low = sum(
        m["confidence"] < 0.65
        for m in matches
    )

    a, b, c = st.columns(3)

    a.metric("Alta confianza", high)
    b.metric("Revisar", medium)
    c.metric("Baja", low)

    st.markdown("### Resultado")

    display_rows = []

    for m in matches:
        display_rows.append(
            {
                "Orden": m["order"],
                "Audio": m["filename"],
                "Confianza": f'{m["confidence"]:.0%}',
                "Frases": (
                    f'{m["start_sentence"] + 1}–'
                    f'{m["end_sentence"] + 1}'
                ),
                "Coincidencia": m["matched_text"],
                "Transcripción": m["transcription"],
            }
        )

    df = pd.DataFrame(display_rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Revisión")

    for m in matches:
        with st.expander(
            f'{m["order"]:02d} · '
            f'{m["filename"]} · '
            f'{m["confidence"]:.0%}'
        ):
            audio = st.session_state.audio_files.get(
                m["file_hash"]
            )

            if audio:
                st.audio(
                    audio["bytes"],
                    format=audio["type"],
                )

            st.markdown("**Transcripción**")
            st.write(m["transcription"])

            st.markdown("**Fragmento del guion detectado**")
            st.info(m["matched_text"])

            st.caption(
                f'Posición estimada en el guion: frases '
                f'{m["start_sentence"] + 1}–'
                f'{m["end_sentence"] + 1}.'
            )

    # Downloads
    export_df = pd.DataFrame(
        [
            {
                "orden": m["order"],
                "archivo": m["filename"],
                "confianza": m["confidence"],
                "frase_inicio": m["start_sentence"] + 1,
                "frase_fin": m["end_sentence"] + 1,
                "fragmento_guion": m["matched_text"],
                "transcripcion": m["transcription"],
            }
            for m in matches
        ]
    )

    csv_bytes = export_df.to_csv(
        index=False
    ).encode("utf-8-sig")

    json_bytes = json.dumps(
        matches,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    st.download_button(
        "Descargar resultados CSV",
        csv_bytes,
        "resultado_narraciones.csv",
        "text/csv",
    )

    st.download_button(
        "Descargar resultados JSON",
        json_bytes,
        "resultado_narraciones.json",
        "application/json",
    )

    # ZIP with renamed/copy-ordered audios
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zf:

        for m in matches:
            audio = st.session_state.audio_files.get(
                m["file_hash"]
            )

            if audio:
                suffix = Path(audio["name"]).suffix

                safe_name = (
                    Path(audio["name"])
                    .stem
                    .replace("/", "_")
                    .replace("\\", "_")
                )

                archive_name = (
                    f'{m["order"]:03d}_'
                    f'{safe_name}'
                    f'{suffix}'
                )

                zf.writestr(
                    archive_name,
                    audio["bytes"],
                )

    st.download_button(
        "Descargar audios ordenados (ZIP)",
        zip_buffer.getvalue(),
        "audios_ordenados.zip",
        "application/zip",
    )


st.divider()

st.caption(
    "MVP: Whisper local (faster-whisper) para transcripción "
    "+ matching local contra el guion."
)

