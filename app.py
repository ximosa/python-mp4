import streamlit as st
import os
import json
import logging
import time
import re
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import requests
from io import BytesIO
import concurrent.futures
import gc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constantes
TEMP_DIR = "temp"
FONT_PATH = "arial.ttf"
DEFAULT_FONT_SIZE = 30
LINE_HEIGHT = 40
VIDEO_FPS = 24
VIDEO_CODEC = 'libx264'
AUDIO_CODEC = 'aac'
VIDEO_PRESET = 'ultrafast'
VIDEO_THREADS = 2
IMAGE_SIZE_TEXT = (1280, 360)
IMAGE_SIZE_SUBSCRIPTION = (1280, 720)
SUBSCRIPTION_DURATION = 5
LOGO_SIZE = (100, 100)
VIDEO_SIZE = (1280, 720)  # Tamaño estándar del video
TEXT_COLOR = "white" # Color de texto por defecto
BG_ALPHA = 0.7       # Transparencia del fondo del texto por defecto
VOCES_DISPONIBLES = {
    'es-ES-Journey-D': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Journey-F': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Journey-O': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Neural2-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-E': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Polyglot-1': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Standard-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Standard-C': texttospeech.SsmlVoiceGender.FEMALE
}

# Cargar credenciales de GCP desde secrets
credentials = dict(st.secrets.gcp_service_account)
with open("google_credentials.json", "w") as f:
    json.dump(credentials, f)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_credentials.json"

def create_text_overlay(text, size=(1280, 360), font_size=DEFAULT_FONT_SIZE, line_height=LINE_HEIGHT,
                      text_color=TEXT_COLOR, background_video=None,
                      stretch_background=False, full_size_background=False,
                      bg_alpha=BG_ALPHA):

    """Creates a text image with the specified text and styles."""

    if full_size_background:
        size = VIDEO_SIZE
    
    try:
         if background_video:
            bg_image = background_video.get_frame(0)
            bg_image = Image.fromarray(bg_image).convert("RGB")
            if stretch_background:
               bg_image = bg_image.resize(size)
            else:
                bg_image.thumbnail(size)
                new_img = Image.new('RGB', size, (0,0,0))
                new_img.paste(bg_image, ((size[0]-bg_image.width)//2, (size[1]-bg_image.height)//2))
                bg_image = new_img
         else:
             bg_image = Image.new('RGB', size, (0,0,0))
    except Exception as e:
        logging.error(f"Error al cargar el video de fondo o crear el fondo negro: {str(e)}")
        bg_image = Image.new('RGB', size, "black")
    
    img = bg_image.copy()
    draw = ImageDraw.Draw(img, 'RGBA')  # Usamos 'RGBA' para transparencia

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception as e:
        logging.error(f"Error al cargar la fuente, usando la fuente predeterminada: {str(e)}")
        font = ImageFont.load_default()
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

    text_height = len(lines) * line_height
    
    # Calcular el rectángulo del fondo con un margen vertical ligero
    bg_y1 = (size[1] - text_height) // 2 - line_height//2
    bg_y2 = (size[1] + text_height) // 2 + line_height//2
    bg_x1 = 0
    bg_x2 = size[0]
     # Dibujar el fondo del texto con transparencia
    bg_color_rgba = (0, 0, 0, int(255 * bg_alpha))  # Color negro con alfa
    draw.rectangle(((bg_x1, bg_y1), (bg_x2, bg_y2)), fill=bg_color_rgba)

    y = (size[1] - text_height) // 2

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


def split_text_into_segments(text, max_segment_length=300):
    """Splits text into segments of up to max_segment_length characters."""
    frases = [f.strip() + "." for f in text.split('.') if f.strip()]
    segments = []
    current_segment = ""
    for frase in frases:
        if len(current_segment) + len(frase) <= max_segment_length:
            current_segment += " " + frase
        else:
            segments.append(current_segment.strip())
            current_segment = frase
    if current_segment:
        segments.append(current_segment.strip())
    return segments


def sanitize_filename(filename):
    """Removes invalid characters from a filename."""
    return re.sub(r'[<>:"/\\|?*]', '', filename).strip()


def create_simple_video(text, output_filename, voice, logo_url, font_size,
                 background_media, stretch_background):
    archivos_temp = []
    clips_audio = []
    clips_finales = []
    temp_video_backgrounds = []
    
    try:
        logging.info("Iniciando proceso de creación de video...")
        
        segments = split_text_into_segments(text)
        total_segments = len(segments)
        logging.info(f"Total de segmentos: {total_segments}")

        client = texttospeech.TextToSpeechClient()
        tiempo_acumulado = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for i, segment in enumerate(segments):
                logging.info(f"Encolando segmento {i + 1} de {total_segments}")
                future = executor.submit(process_segment, segment, i, tiempo_acumulado, voice, client, archivos_temp, logo_url, font_size, background_media, stretch_background)
                futures.append(future)
                tiempo_acumulado += calculate_audio_duration(segment, voice, client, archivos_temp)

            for future in concurrent.futures.as_completed(futures):
                audio_clip, video_segment = future.result()
                clips_audio.append(audio_clip)
                clips_finales.append(video_segment)


        subscribe_clip = create_subscription_clip(logo_url, tiempo_acumulado)
        clips_finales.append(subscribe_clip)
        
        video_final = concatenate_videoclips(clips_finales, method="compose")
        
        video_final.write_videofile(
            output_filename,
            fps=VIDEO_FPS,
            codec=VIDEO_CODEC,
            audio_codec=AUDIO_CODEC,
            preset=VIDEO_PRESET,
            threads=VIDEO_THREADS
        )
        
        video_final.close()
        
        for clip in clips_audio:
            clip.close()
        
        for clip in clips_finales:
            clip.close()
            
        for temp_file in archivos_temp:
            try:
                if os.path.exists(temp_file):
                    os.close(os.open(temp_file, os.O_RDONLY))
                    os.remove(temp_file)
            except:
                pass
                
        return True, "Video generado exitosamente"
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        for clip in clips_audio:
            try:
                clip.close()
            except:
                pass
                
        for clip in clips_finales:
            try:
                clip.close()
            except:
                pass
                
        for temp_file in archivos_temp:
            try:
                if os.path.exists(temp_file):
                    os.close(os.open(temp_file, os.O_RDONLY))
                    os.remove(temp_file)
            except:
                pass
        
        return False, str(e)

def calculate_audio_duration(segment, voice, client, archivos_temp):
    """Calculates the audio duration for a given text segment."""
    synthesis_input = texttospeech.SynthesisInput(text=segment)
    voice_params = texttospeech.VoiceSelectionParams(
        language_code="es-ES",
        name=voice,
        ssml_gender=VOCES_DISPONIBLES[voice]
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config
    )
    temp_filename = os.path.join(TEMP_DIR, f"temp_duration_check.mp3")
    archivos_temp.append(temp_filename)
    with open(temp_filename, "wb") as out:
        out.write(response.audio_content)
    audio_clip = AudioFileClip(temp_filename)
    duration = audio_clip.duration
    audio_clip.close()
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
    return duration

def process_segment(segment, index, tiempo_acumulado, voice, client, archivos_temp, logo_url, font_size, background_media, stretch_background):
    """Processes a single segment, creating the audio and video clips."""
    audio_clip, duracion = process_audio(segment, index, voice, client, archivos_temp)
    text_clip = create_text_clip(segment, tiempo_acumulado, duracion, font_size, background_media, stretch_background)
    video_segment = text_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
    return audio_clip, video_segment


def process_audio(segment, index, voice, client, archivos_temp):
    """Generates audio for a given text segment."""
    try:
        synthesis_input = texttospeech.SynthesisInput(text=segment)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code="es-ES",
            name=voice,
            ssml_gender=VOCES_DISPONIBLES[voice]
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        retry_count = 0
        max_retries = 3
        while retry_count <= max_retries:
            try:
                response = client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=audio_config
                )
                break
            except Exception as e:
                logging.error(f"Error al solicitar audio (intento {retry_count + 1}): {str(e)}")
                if "429" in str(e):
                    retry_count += 1
                    time.sleep(2**retry_count)
                else:
                    raise

        temp_filename = os.path.join(TEMP_DIR, f"temp_audio_{index}.mp3")
        archivos_temp.append(temp_filename)
        with open(temp_filename, "wb") as out:
            out.write(response.audio_content)
        audio_clip = AudioFileClip(temp_filename)
        return audio_clip, audio_clip.duration
    except Exception as e:
        logging.error(f"Error al procesar audio: {str(e)}")
        raise

def create_text_clip(segment, start_time, duration, font_size, background_media, stretch_background):
        """
        Creates a video clip with the text overlay and the background video.
        """
        video_clip = None
        if background_media:
           with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(background_media.name)[1]) as tmp_file:
              tmp_file.write(background_media.read())
              media_path = tmp_file.name
              try:
                    if media_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                        video_clip = VideoFileClip(media_path)
                        video_clip = video_clip.resize(height=VIDEO_SIZE[1])
                        video_clip = video_clip.subclip(0, duration).set_position('center').set_audio(None)
                    else:
                      video_clip = ColorClip(VIDEO_SIZE, color="black", duration=duration).set_audio(None)
              except Exception as e:
                  logging.error(f"Error al procesar el video de fondo {str(e)}")
                  video_clip = ColorClip(VIDEO_SIZE, color="black", duration=duration).set_audio(None)
              try:
                 os.remove(media_path)
              except:
                pass
        else:
            video_clip = ColorClip(VIDEO_SIZE, color="black", duration=duration).set_audio(None)

        text_img = create_text_overlay(
            segment,
            font_size=font_size,
            text_color=TEXT_COLOR,
            background_video=video_clip,
            stretch_background=stretch_background,
            full_size_background=True,
            bg_alpha=BG_ALPHA
        )

        txt_clip = (
            ImageClip(text_img)
            .set_start(0)
            .set_duration(duration)
            .set_position('center')
        )
        final_clip = CompositeVideoClip([video_clip, txt_clip])
        final_clip = final_clip.set_start(start_time)

        return final_clip

def create_subscription_clip(logo_url, start_time):
    """
    Creates the subscription clip.
    """
    subscribe_img = create_subscription_image(logo_url)
    subscribe_clip = (ImageClip(subscribe_img)
                        .set_start(start_time)
                        .set_duration(SUBSCRIPTION_DURATION)
                        .set_position('center'))
    return subscribe_clip


def main():
    st.title("Creador de Videos Automático")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    
    
    with st.sidebar:
        st.header("Configuración del Video")
        voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
        background_media = st.file_uploader("Imagen o video de fondo (opcional)", type=["png", "jpg", "jpeg", "webp", "mp4", "mov", "avi", "mkv"])
        stretch_background = st.checkbox("Estirar fondo", value=False)

    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    
    if uploaded_file:
        texto = uploaded_file.read().decode("utf-8")
        nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
        
        if st.button("Generar Video"):
            with st.spinner('Generando video...'):
                nombre_salida_completo = f"{nombre_salida}.mp4"
                success, message = create_simple_video(texto, nombre_salida_completo, voz_seleccionada, logo_url, DEFAULT_FONT_SIZE, background_media, stretch_background)
                if success:
                    st.success(message)
                    st.video(nombre_salida_completo)
                    with open(nombre_salida_completo, 'rb') as file:
                        st.download_button(label="Descargar video",data=file,file_name=nombre_salida_completo)
                        
                    st.session_state.video_path = nombre_salida_completo
                else:
                    st.error(f"Error al generar video: {message}")

        if st.session_state.get("video_path"):
            st.markdown(f'<a href="https://www.youtube.com/upload" target="_blank">Subir video a YouTube</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    # Inicializar session state
    if "video_path" not in st.session_state:
        st.session_state.video_path = None
    main()
