import streamlit as st
import os
import json
import logging
import time
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips, VideoFileClip, CompositeVideoClip, ColorClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import tempfile
import requests
from io import BytesIO
from moviepy.video.fx.all import colorx
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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

def create_video_background_clip(video_path, duration):
    try:
        # Cargar el video original
        video_clip = VideoFileClip(video_path)
        original_duration = video_clip.duration

        # Redimensionar usando PIL para evitar problemas de ANTIALIAS
        def resize_frame(frame):
            try:
                img = Image.fromarray(frame)
                img.thumbnail(VIDEO_SIZE, Image.Resampling.LANCZOS)
                new_img = Image.new('RGB', VIDEO_SIZE, (0,0,0))
                new_img.paste(img, ((VIDEO_SIZE[0]-img.width)//2, (VIDEO_SIZE[1]-img.height)//2))
                return np.array(new_img)
            except Exception as e:
                logging.error(f"Error en resize_frame: {str(e)}")
                return np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8)

        # Procesar el video original primero
        video_clip = video_clip.fl_image(resize_frame)
        video_clip = colorx(video_clip, 0.5)  # Oscurecer el video

        if original_duration < duration:
            try:
                # Crear un clip negro de la duración total
                black_bg = ColorClip(size=VIDEO_SIZE, color=(0,0,0), duration=duration)
                
                # Calcular cuántas repeticiones completas necesitamos
                n_repeats = int(duration // original_duration) + 1
                
                # Crear una lista de clips con tiempos de inicio específicos
                final_clips = []
                for i in range(n_repeats):
                    start_time = i * original_duration
                    if start_time < duration:
                        clip_copy = video_clip.copy()
                        clip_copy = clip_copy.set_start(start_time)
                        # Asegurar que el clip no exceda la duración total
                        remaining_duration = duration - start_time
                        if remaining_duration < original_duration:
                            clip_copy = clip_copy.subclip(0, remaining_duration)
                        final_clips.append(clip_copy)

                # Combinar todos los clips usando CompositeVideoClip
                final_clips.insert(0, black_bg)  # Insertar el fondo negro como base
                final_video = CompositeVideoClip(final_clips)
                
                # Asegurar la duración correcta
                final_video = final_video.set_duration(duration)
                
                return final_video
            except Exception as e:
                logging.error(f"Error al crear video en loop: {str(e)}")
                # En caso de error, retornar un video negro
                return ColorClip(size=VIDEO_SIZE, color=(0,0,0), duration=duration)
        else:
            # Si el video es más largo que la duración necesaria, simplemente cortarlo
            return video_clip.subclip(0, duration)

    except Exception as e:
        logging.error(f"Error al cargar o procesar video de fondo: {str(e)}")
        # En caso de error, retornar un video negro
        return ColorClip(size=VIDEO_SIZE, color=(0,0,0), duration=duration)

@lru_cache(maxsize=32)
def create_text_image(text, size=IMAGE_SIZE_TEXT, font_size=DEFAULT_FONT_SIZE,
                      bg_color="black", text_color="white",
                      full_size_background=False):
    if full_size_background:
        size = VIDEO_SIZE

    # Crear imagen con canal alpha para transparencia
    img = Image.new('RGBA', size, (0, 0, 0, 0) if bg_color is None else bg_color)

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

@lru_cache(maxsize=1)
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

def synthesize_speech(client, segmento, voz):
    synthesis_input = texttospeech.SynthesisInput(text=segmento)
    voice = texttospeech.VoiceSelectionParams(
        language_code="es-ES",
        name=voz,
        ssml_gender=VOCES_DISPONIBLES[voz]
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
                voice=voice,
                audio_config=audio_config
            )
            return response
        except Exception as e:
            if "429" in str(e):
                retry_count += 1
                time.sleep(2**retry_count)
            else:
                raise
    
    raise Exception("Máximos intentos de reintento alcanzado")

def create_simple_video(texto, nombre_salida, voz, logo_url, font_size, bg_color, text_color,
                 background_video):
    archivos_temp = []
    clips_audio = []
    clips_finales = []
    
    try:
        st.info("1/6: Iniciando proceso de creación de video...")
        frases = [f.strip() + "." for f in texto.split('.') if f.strip()]
        client = texttospeech.TextToSpeechClient()
        
        # Agrupamos frases en segmentos
        st.info("2/6: Procesando texto...")
        segmentos_texto = []
        segmento_actual = ""
        for frase in frases:
            if len(segmento_actual) + len(frase) < 300:
                segmento_actual += " " + frase
            else:
                segmentos_texto.append(segmento_actual.strip())
                segmento_actual = frase
        segmentos_texto.append(segmento_actual.strip())
        
        st.info("3/6: Calculando duración total...")
        total_duration = 0
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for i, segmento in enumerate(segmentos_texto):
              
                future = executor.submit(synthesize_speech, client, segmento, voz)
                futures.append(future)
                
            for i, future in enumerate(futures):
                try:
                    st.text(f"Procesando segmento de audio {i+1}/{len(segmentos_texto)}")
                    response = future.result()
                
                    temp_filename = f"temp_audio_duration_calc_{len(archivos_temp)}.mp3"
                    archivos_temp.append(temp_filename)
                    with open(temp_filename, "wb") as out:
                        out.write(response.audio_content)
                    
                    with AudioFileClip(temp_filename) as audio_clip_duration:
                      total_duration += audio_clip_duration.duration
                    time.sleep(0.2)
                except Exception as e:
                    st.error(f"Error al generar audio: {str(e)}")
                    logging.error(f"Error detallado en generación de audio: {str(e)}")
                    return False, str(e)
                
        total_duration += SUBSCRIPTION_DURATION
        st.info(f"Duración total calculada: {total_duration:.2f} segundos")

        # Lista para mantener los clips en orden de capas
        layer_clips = []
        
        # Capa 1: Video de fondo (si existe)
        if background_video:
            st.info("4/6: Procesando video de fondo...")
            st.text("Cargando video...")
            background_video_clip = create_video_background_clip(background_video, total_duration)
            if not background_video_clip:
                return False, "Error al cargar el clip de video de fondo."
            layer_clips.append(background_video_clip.set_start(0))
            st.success("Video de fondo procesado")
        
        st.info("5/6: Generando clips de audio y texto...")
        tiempo_acumulado = 0
        
        for i, segmento in enumerate(segmentos_texto):
            try:
                st.text(f"Procesando segmento {i+1}/{len(segmentos_texto)}")
                response = synthesize_speech(client, segmento, voz)
            
                temp_filename = f"temp_audio_{i}.mp3"
                archivos_temp.append(temp_filename)
                with open(temp_filename, "wb") as out:
                    out.write(response.audio_content)
            
                audio_clip = AudioFileClip(temp_filename)
                clips_audio.append(audio_clip)
                duracion = audio_clip.duration
                
                # Crear clip de texto con fondo transparente
                text_img = create_text_image(segmento, font_size=font_size,
                                          bg_color=None,  # Fondo transparente
                                          text_color=text_color,
                                          full_size_background=True)
                txt_clip = (ImageClip(text_img)
                        .set_start(tiempo_acumulado)
                        .set_duration(duracion)
                        .set_position('center')
                        .set_audio(audio_clip))
                
                layer_clips.append(txt_clip)
                tiempo_acumulado += duracion
                time.sleep(0.2)
            except Exception as e:
                st.error(f"Error al generar audio: {str(e)}")
                logging.error(f"Error detallado en generación de audio: {str(e)}")
                return False, str(e)
          
        # Capa superior: Clip de suscripción
        subscribe_img = create_subscription_image(logo_url)
        subscribe_clip = (ImageClip(subscribe_img)
                          .set_start(tiempo_acumulado)  # Mostrar al final
                          .set_duration(SUBSCRIPTION_DURATION)
                          .set_position('center'))
        
        layer_clips.append(subscribe_clip)
        
        st.info("6/6: Renderizando video final...")
        video_final = CompositeVideoClip(layer_clips, size=VIDEO_SIZE)
        
        video_final.write_videofile(
            nombre_salida,
            fps=VIDEO_FPS,
            codec=VIDEO_CODEC,
            audio_codec=AUDIO_CODEC,
            preset=VIDEO_PRESET,
            threads=VIDEO_THREADS
        )
        
        video_final.close()
        
        if background_video:
            background_video_clip.close()
        
        for clip in clips_audio:
            clip.close()
        
        for clip in layer_clips:
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
        st.error(f"Error en el proceso: {str(e)}")
        logging.error(f"Error detallado: {str(e)}")
        for clip in clips_audio:
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

def main():
    st.title("Creador de Videos Automático")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    
    
    with st.sidebar:
        st.header("Configuración del Video")
        voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
        font_size = st.slider("Tamaño de la fuente", min_value=10, max_value=100, value=DEFAULT_FONT_SIZE)
        bg_color = st.color_picker("Color de fondo", value="#000000")
        text_color = st.color_picker("Color de texto", value="#ffffff")
        background_video = st.file_uploader("Video de fondo (opcional)", type=["mp4", "avi", "mov"])


    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    
    if uploaded_file:
        texto = uploaded_file.read().decode("utf-8")
        nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
        
        if st.button("Generar Video"):
            with st.spinner('Generando video...'):
                nombre_salida_completo = f"{nombre_salida}.mp4"
                
                video_path = None
                if background_video:
                  with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(background_video.name)[1]) as tmp_file:
                    tmp_file.write(background_video.read())
                    video_path = tmp_file.name
                
                success, message = create_simple_video(texto, nombre_salida_completo, voz_seleccionada, logo_url,
                                                        font_size, bg_color, text_color, video_path)
                if success:
                  st.success(message)
                  st.video(nombre_salida_completo)
                  with open(nombre_salida_completo, 'rb') as file:
                    st.download_button(label="Descargar video",data=file,file_name=nombre_salida_completo)
                    
                  st.session_state.video_path = nombre_salida_completo
                  if video_path:
                    os.remove(video_path)
                else:
                  st.error(f"Error al generar video: {message}")
                  if video_path:
                    os.remove(video_path)

        if st.session_state.get("video_path"):
            st.markdown(f'<a href="https://www.youtube.com/upload" target="_blank">Subir video a YouTube</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    # Inicializar session state
    if "video_path" not in st.session_state:
        st.session_state.video_path = None
    main()
