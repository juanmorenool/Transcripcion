# 🎙️ Organizador de Narraciones

Aplicación Streamlit para:

1. Cargar un guion.
2. Cargar múltiples fragmentos de audio.
3. Transcribir los audios con ElevenLabs Scribe v2.
4. Comparar cada transcripción con el guion.
5. Estimar qué parte del guion corresponde a cada audio.
6. Ordenar los audios según su posición en el guion.
7. Revisar manualmente los resultados.
8. Descargar un CSV/JSON y un ZIP con los audios ordenados.

## 🔐 API de ElevenLabs — configuración segura

**La API key NO está incluida en este repositorio.** Esto es intencional: Streamlit recomienda mantener los secretos fuera del repositorio y Community Cloud permite configurarlos como Secrets. ElevenLabs también indica que las API keys deben tratarse como secretos.

### Streamlit Community Cloud

1. Sube esta carpeta a GitHub.
2. Crea/despliega la app en Streamlit Community Cloud.
3. En la configuración de la app, abre **Secrets**.
4. Pega exactamente:

```toml
ELEVENLABS_API_KEY = "TU_API_KEY"
```

5. Guarda y reinicia la app.

No subas `.streamlit/secrets.toml` a GitHub.

### Desarrollo local

Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml` y reemplaza el valor por tu API key. Ese archivo está incluido en `.gitignore` y no debe versionarse.

## Estructura

```text
organizador_narraciones/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── LICENSE
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── src/
    ├── __init__.py
    ├── transcription.py
    ├── matcher.py
    ├── script_parser.py
    └── utils.py
```
