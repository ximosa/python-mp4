import streamlit as st
import os
import json
import logging
import time
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, VideoFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import tempfile
import requests
from io import BytesIO

logging.basicConfig(level=logging.INFO)

# Cargar credenciales de GCP desde secrets
credentials = dict(st.secrets.gcp_service_account)
with open("google_credentials.json", "w") as f:
    json.dump(credentials, f)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_credentials.json"

# Constantes
TEMP_DIR = "temp"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # Ajusta la ruta si es necesario
DEFAULT_FONT_SIZE = 30
VIDEO_FPS = 24
VIDEO_CODEC = 'libx264'
AUDIO_CODEC = 'aac'
VIDEO_PRESET = 'ultrafast'
VIDEO_THREADS = 4
VIDEO_SIZE = (1280, 720)

# Configuración de voces
VOCES_DISPONIBLES = {
    'es-ES-Standard-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-B': texttospeech.SsmlVoiceGender.MALE,
    # Puedes agregar más voces según lo necesites
}

def create_text_overlay(text, font_size=DEFAULT_FONT_SIZE, bg_color="black", text_color="white"):
    """Crea una superposición de texto para un video."""
    img = Image.new('RGB', VIDEO_SIZE, bg_color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception as e:
        logging.error(f"Error al cargar la fuente, usando la fuente predeterminada: {str(e)}")
        font = ImageFont.load_default()

    text_width, text_height = draw.textsize(text, font=font)
    x = (VIDEO_SIZE[0] - text_width) // 2
    y = (VIDEO_SIZE[1] - text_height) // 2
    draw.text((x, y), text, font=font, fill=text_color)
    return np.array(img)

def create_video_with_background(texto, nombre_salida, voz, video_background):
    archivos_temp = []
    clips_audio = []
    clips_finales = []

    try:
        logging.info("Iniciando proceso de creación de video...")
        frases = [f.strip() + "." for f in texto.split('.') if f.strip()]
        client = texttospeech.TextToSpeechClient()

        tiempo_acumulado = 0
        for i, frase in enumerate(frases):
            synthesis_input = texttospeech.SynthesisInput(text=frase)
            voice = texttospeech.VoiceSelectionParams(
                language_code="es-ES",
                name=voz,
                ssml_gender=VOCES_DISPONIBLES[voz]
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

            temp_filename = f"temp_audio_{i}.mp3"
            archivos_temp.append(temp_filename)
            with open(temp_filename, "wb") as out:
                out.write(response.audio_content)

            audio_clip = AudioFileClip(temp_filename)
            clips_audio.append(audio_clip)
            duracion = audio_clip.duration

            video_clip = (VideoFileClip(video_background)
                          .subclip(0, duracion)
                          .set_duration(duracion)
                          .resize(VIDEO_SIZE)
                          .set_audio(audio_clip))

            clips_finales.append(video_clip)
            tiempo_acumulado += duracion

        video_final = concatenate_videoclips(clips_finales, method="compose")
        video_final.write_videofile(
            nombre_salida,
            fps=VIDEO_FPS,
            codec=VIDEO_CODEC,
            audio_codec=AUDIO_CODEC,
            preset=VIDEO_PRESET,
            threads=VIDEO_THREADS
        )

        for temp_file in archivos_temp:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return True, "Video generado exitosamente"

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return False, str(e)

def main():
    st.title("Creador de Videos Automático")

    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    video_background = st.file_uploader("Carga un video de fondo", type=["mp4", "mov"])

    with st.sidebar:
        st.header("Configuración del Video")
        voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))

    if uploaded_file and video_background:
        texto = uploaded_file.read().decode("utf-8")
        nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")

        if st.button("Generar Video"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_video:
                tmp_video.write(video_background.read())
                background_path = tmp_video.name

            success, message = create_video_with_background(texto, f"{nombre_salida}.mp4", voz_seleccionada, background_path)
            if success:
                st.success(message)
                st.video(f"{nombre_salida}.mp4")
            else:
                st.error(f"Error al generar video: {message}")

if __name__ == "__main__":
    main()
