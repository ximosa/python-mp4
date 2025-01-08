import streamlit as st
import os
import json
import logging
import time
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
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
#LINE_HEIGHT = 40 # Eliminamos LINE_HEIGHT como variable global
VIDEO_FPS = 24
VIDEO_CODEC = 'libx264'
AUDIO_CODEC = 'aac'
VIDEO_PRESET = 'ultrafast'
VIDEO_THREADS = 4
IMAGE_SIZE_TEXT = (1280, 360)
IMAGE_SIZE_SUBSCRIPTION = (1280, 720)
SUBSCRIPTION_DURATION = 5
LOGO_SIZE = (100, 100)
VIDEO_SIZE = (1280, 720)  # Tamaño estándar del video

# Configuración de voces
VOCES_DISPONIBLES = {
    'es-ES-Standard-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Standard-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-E': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Neural2-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Neural2-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-E': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Polyglot-1': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Studio-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Studio-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Wavenet-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Wavenet-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Wavenet-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Wavenet-E': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Wavenet-F': texttospeech.SsmlVoiceGender.FEMALE,
}

def create_text_image(text, size=IMAGE_SIZE_TEXT, font_size=DEFAULT_FONT_SIZE,
                      bg_color="black", text_color="white", background_image=None,
                      stretch_background=False, full_size_background=False):
    """Creates a text image with the specified text and styles."""
    if full_size_background:
      size = VIDEO_SIZE

    if background_image:
        try:
            img = Image.open(background_image).convert("RGB")
            if stretch_background:
                img = img.resize(size)
            else:
              img.thumbnail(size)
              new_img = Image.new('RGB', size, bg_color)
              new_img.paste(img, ((size[0]-img.width)//2, (size[1]-img.height)//2))
              img = new_img
        except Exception as e:
            logging.error(f"Error al cargar imagen de fondo: {str(e)}, usando fondo {bg_color}.")
            img = Image.new('RGB', size, bg_color)
    else:
        img = Image.new('RGB', size, bg_color)

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception as e:
        logging.error(f"Error al cargar la fuente, usando la fuente predeterminada: {str(e)}")
        font = ImageFont.load_default()
    
    # Calculamos la altura de línea en función del tamaño de la fuente.
    line_height = font_size * 1.5  # Aumentamos el factor a 1.5

    words = text.split()
    lines = []
    current_line = []

    for word in words:
        current_line.append(word)
        test_line = ' '.join(current_line)
        left, top, right, bottom = draw.textbbox((0, 0), test_line, font=font)
        if right > size[0] - 60:
            current_line.pop()
            lines.append(' '.join(current_line))
            current_line = [word]
    lines.append(' '.join(current_line))

    total_height = len(lines) * line_height
    y = (size[1] - total_height) // 2

    for line in lines:
        left, top, right, bottom = draw.textbbox((0, 0), line, font=font)
        x = (size[0] - (right - left)) // 2
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_height
    return np.array(img)


def create_subscription_image(logo_url, size=IMAGE_SIZE_SUBSCRIPTION, font_size=60):
    """Creates an image for the subscription message."""
    img = Image.new('RGB', size, (255, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
        font2 = ImageFont.truetype(FONT_PATH, font_size//2)
    except:
        font = ImageFont.load_default()
        font2 = ImageFont.load_default()

    try:
        response = requests.get(logo_url)
        response.raise_for_status()
        logo_img = Image.open(BytesIO(response.content)).convert("RGBA")
        logo_img = logo_img.resize(LOGO_SIZE)
        logo_position = (20, 20)
        img.paste(logo_img, logo_position, logo_img)
    except Exception as e:
        logging.error(f"Error al cargar el logo: {str(e)}")

    text1 = "¡SUSCRÍBETE A LECTOR DE SOMBRAS!"
    left1, top1, right1, bottom1 = draw.textbbox((0, 0), text1, font=font)
    x1 = (size[0] - (right1 - left1)) // 2
    y1 = (size[1] - (bottom1 - top1)) // 2 - (bottom1 - top1) // 2 - 20
    draw.text((x1, y1), text1, font=font, fill="white")

    text2 = "Dale like y activa la campana 🔔"
    left2, top2, right2, bottom2 = draw.textbbox((0, 0), text2, font=font2)
    x2 = (size[0] - (right2 - left2)) // 2
    y2 = (size[1] - (bottom2 - top2)) // 2 + (bottom1 - top1) // 2 + 20
    draw.text((x2, y2), text2, font=font2, fill="white")
    return np.array(img)
    
from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip

def create_simple_video_with_background_video(
    texto, nombre_salida, voz, logo_url, font_size, text_color, background_video
):
    archivos_temp = []
    clips_audio = []
    clips_finales = []
    
    try:
        logging.info("Iniciando proceso de creación de video con fondo...")
        frases = [f.strip() + "." for f in texto.split('.') if f.strip()]
        client = texttospeech.TextToSpeechClient()

        tiempo_acumulado = 0
        video_bg_clip = VideoFileClip(background_video).resize((1280, 720))
        
        for i, frase in enumerate(frases):
            logging.info(f"Procesando frase {i+1} de {len(frases)}")
            
            # Generar audio
            synthesis_input = texttospeech.SynthesisInput(text=frase)
            voice = texttospeech.VoiceSelectionParams(
                language_code="es-ES",
                name=voz,
                ssml_gender=VOCES_DISPONIBLES[voz]
            )
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            
            temp_audio_file = f"temp_audio_{i}.mp3"
            with open(temp_audio_file, "wb") as out:
                out.write(response.audio_content)
            archivos_temp.append(temp_audio_file)
            audio_clip = AudioFileClip(temp_audio_file)
            clips_audio.append(audio_clip)
            
            # Crear texto
            text_clip = TextClip(
                frase, fontsize=font_size, color=text_color, size=(1280, None), method="caption"
            ).set_duration(audio_clip.duration).set_position("center")
            
            # Combinar texto con fondo de video
            video_with_text = CompositeVideoClip([video_bg_clip, text_clip]).set_duration(audio_clip.duration)
            video_with_text = video_with_text.set_audio(audio_clip)
            clips_finales.append(video_with_text)
            
            tiempo_acumulado += audio_clip.duration
        
        # Crear video final
        final_video = concatenate_videoclips(clips_finales)
        final_video.write_videofile(
            nombre_salida, fps=VIDEO_FPS, codec=VIDEO_CODEC, audio_codec=AUDIO_CODEC
        )
        
        return True, "Video generado exitosamente"
    
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return False, str(e)
    finally:
        # Limpiar recursos temporales
        for temp_file in archivos_temp:
            if os.path.exists(temp_file):
                os.remove(temp_file)

def main():
    st.title("Creador de Videos Automático con Fondo de Video")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    background_video = st.file_uploader("Video de fondo (opcional)", type=["mp4", "avi", "mov"])
    
    if uploaded_file and background_video:
        texto = uploaded_file.read().decode("utf-8")
        nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
        
        voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
        font_size = st.slider("Tamaño de la fuente", min_value=10, max_value=100, value=30)
        text_color = st.color_picker("Color de texto", value="#FFFFFF")
        
        if st.button("Generar Video"):
            with st.spinner('Generando video...'):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_video:
                    tmp_video.write(background_video.read())
                    video_path = tmp_video.name
                
                success, message = create_simple_video_with_background_video(
                    texto, f"{nombre_salida}.mp4", voz_seleccionada, "", font_size, text_color, video_path
                )
                if success:
                    st.success(message)
                    st.video(f"{nombre_salida}.mp4")
                else:
                    st.error(f"Error: {message}")

if __name__ == "__main__":
    main()
