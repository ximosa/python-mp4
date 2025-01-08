import streamlit as st
import os
import logging
import re
import json
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip, ColorClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import requests
from io import BytesIO
import concurrent.futures
import gc

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constantes
TEMP_DIR = "temp"
FONT_PATH = "arial.ttf"  # Asegúrate de que la fuente esté disponible o súbela a tu proyecto
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
VIDEO_SIZE = (1280, 720)
TEXT_COLOR = "white"
BG_ALPHA = 0.7
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

# Configuración de las credenciales de Google Cloud
# Cargar credenciales de GCP desde secrets
credentials = dict(st.secrets.gcp_service_account)
with open("google_credentials.json", "w") as f:
    json.dump(credentials, f)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_credentials.json"

def create_text_overlay(text, size=IMAGE_SIZE_TEXT, font_size=DEFAULT_FONT_SIZE, line_height=LINE_HEIGHT,
                        text_color=TEXT_COLOR, background_video=None,
                        stretch_background=False, full_size_background=False,
                        bg_alpha=BG_ALPHA):
    """Crea una imagen de texto con el texto y estilos especificados."""
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
                new_img = Image.new('RGB', size, (0, 0, 0))
                new_img.paste(bg_image, ((size[0] - bg_image.width) // 2, (size[1] - bg_image.height) // 2))
                bg_image = new_img
        else:
            bg_image = Image.new('RGB', size, (0, 0, 0))
    except Exception as e:
        logging.error(f"Error al cargar el video de fondo o crear el fondo negro: {str(e)}")
        bg_image = Image.new('RGB', size, "black")
    
    img = bg_image.copy()
    draw = ImageDraw.Draw(img, 'RGBA')

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
    bg_y1 = (size[1] - text_height) // 2 - line_height // 2
    bg_y2 = (size[1] + text_height) // 2 + line_height // 2
    bg_x1 = 0
    bg_x2 = size[0]
    bg_color_rgba = (0, 0, 0, int(255 * bg_alpha))
    draw.rectangle(((bg_x1, bg_y1), (bg_x2, bg_y2)), fill=bg_color_rgba)

    y = (size[1] - text_height) // 2
    for line in lines:
        left, top, right, bottom = draw.textbbox((0, 0), line, font=font)
        x = (size[0] - (right - left)) // 2
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_height
    return np.array(img)

def create_subscription_image(logo_url, size=IMAGE_SIZE_SUBSCRIPTION, font_size=60):
    """Crea una imagen para el mensaje de suscripción."""
    img = Image.new('RGB', size, (255, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
        font2 = ImageFont.truetype(FONT_PATH, font_size // 2)
    except:
        font = ImageFont.load_default()
        font2 = ImageFont.load_default()

    try:
        response = requests.get(logo_url, stream=True)
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
    """Divide el texto en segmentos de hasta max_segment_length caracteres."""
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
    """Elimina caracteres inválidos de un nombre de archivo."""
    return re.sub(r'[<>:"/\\|?*]', '', filename).strip()

class VideoGenerator:
    """Genera un video a partir de texto, audio e imágenes."""
    def __init__(self, text, output_filename, voice, logo_url, font_size,
                 background_video_path, stretch_background):
        """Inicializa el generador de video."""
        self.text = text
        self.output_filename = output_filename
        self.voice = voice
        self.logo_url = logo_url
        self.temp_files = []
        self.audio_clips = []
        self.video_clips = []
        self.client = texttospeech.TextToSpeechClient()
        self.font_size = font_size
        self.stretch_background = stretch_background
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.video_final = None
        self.background_video = None
        if background_video_path:
            try:
                self.background_video = VideoFileClip(background_video_path)
            except Exception as e:
                logging.error(f"Error al cargar el video de fondo: {str(e)}")

    def generate_video(self):
        """Método principal para iniciar el proceso de creación de video."""
        try:
            logging.info("Iniciando proceso de creación de video...")
            self._create_temp_dir()
            segments = split_text_into_segments(self.text)
            total_segments = len(segments)
            st.session_state['total_segments'] = total_segments

            futures = []
            tiempo_acumulado = 0
            for i, segment in enumerate(segments):
                logging.info(f"Encolando segmento {i + 1} de {total_segments}")
                future = self.executor.submit(self._process_segment, segment, i, tiempo_acumulado)
                futures.append(future)
                tiempo_acumulado += self._calculate_audio_duration(segment)

            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                audio_clip, video_segment = future.result()
                self.audio_clips.append(audio_clip)
                self.video_clips.append(video_segment)
                st.session_state['progress'] = i + 1

            subscribe_clip = self._create_subscription_clip(tiempo_acumulado)
            self.video_clips.append(subscribe_clip)
            self.video_final = concatenate_videoclips(self.video_clips, method="compose")

            self._write_video_file(self.video_final)
            st.success("Video generado exitosamente")
        except Exception as e:
            logging.error(f"Error en la creación de video: {str(e)}")
            st.error(f"Error en la creación de video: {str(e)}")
        finally:
            self._cleanup(self.video_final)
            self.executor.shutdown()

    def _process_segment(self, segment, index, tiempo_acumulado):
        """Procesa un segmento, creando clips de audio y video."""
        audio_clip, duracion = self._process_audio(segment, index)
        text_clip = self._create_text_clip(segment, tiempo_acumulado, duracion)
        video_segment = text_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
        return audio_clip, video_segment

    def _process_audio(self, segment, index):
        """Genera audio para un segmento de texto dado."""
        try:
            synthesis_input = texttospeech.SynthesisInput(text=segment)
            voice = texttospeech.VoiceSelectionParams(
                language_code="es-ES",
                name=self.voice,
                ssml_gender=VOCES_DISPONIBLES[self.voice]
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            temp_filename = os.path.join(TEMP_DIR, f"temp_audio_{index}.mp3")
            self.temp_files.append(temp_filename)

            with open(temp_filename, "wb") as out:
                out.write(response.audio_content)

            audio_clip = AudioFileClip(temp_filename)
            return audio_clip, audio_clip.duration
        except Exception as e:
            logging.error(f"Error al procesar audio: {str(e)}")
            raise

    def _calculate_audio_duration(self, segment):
        """Calcula la duración del audio para un segmento de texto dado."""
        synthesis_input = texttospeech.SynthesisInput(text=segment)
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-ES",
            name=self.voice,
            ssml_gender=VOCES_DISPONIBLES[self.voice]
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        response = self.client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        temp_filename = os.path.join(TEMP_DIR, f"temp_duration_check.mp3")
        self.temp_files.append(temp_filename)
        with open(temp_filename, "wb") as out:
            out.write(response.audio_content)

        audio_clip = AudioFileClip(temp_filename)
        duration = audio_clip.duration
        audio_clip.close()
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return duration

    def _create_text_clip(self, segment, start_time, duration):
      """Crea un clip de video con el texto superpuesto y el video de fondo."""
      if self.background_video:
          video_clip = self.background_video.subclip(0, duration).set_position('center').set_audio(None)
      else:
          video_clip = ColorClip(VIDEO_SIZE, color="black", duration=duration).set_audio(None)

      text_img = create_text_overlay(
          segment,
          font_size=self.font_size,
          text_color=TEXT_COLOR,
          stretch_background=self.stretch_background,
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

    def _create_subscription_clip(self, start_time):
        """Crea el clip de suscripción."""
        subscribe_img = create_subscription_image(self.logo_url)
        subscribe_clip = (ImageClip(subscribe_img)
                          .set_start(start_time)
                          .set_duration(SUBSCRIPTION_DURATION)
                          .set_position('center'))
        return subscribe_clip

    def _create_temp_dir(self):
        """Crea el directorio temporal si no existe."""
        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)

    def _write_video_file(self, video_final):
        """Escribe el archivo de video final."""
        try:
            video_final.write_videofile(
                self.output_filename,
                fps=VIDEO_FPS,
                codec=VIDEO_CODEC,
                audio_codec=AUDIO_CODEC,
                preset=VIDEO_PRESET,
                threads=VIDEO_THREADS
            )
            logging.info(f"Video guardado en: {self.output_filename}")
        except Exception as e:
            logging.error(f"Error al escribir el video: {str(e)}")
            raise

    def _cleanup(self, video_final=None):
        """Cierra y limpia los recursos."""
        logging.info("Limpiando recursos...")
        for clip in self.audio_clips + self.video_clips:
            try:
                if clip:
                    clip.close()
            except Exception as e:
                logging.error(f"Error al cerrar clip: {str(e)}")
        
        if video_final:
            try:
                video_final.close()
            except Exception as e:
                logging.error(f"Error al cerrar video_final: {str(e)}")

        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logging.error(f"Error al eliminar archivo temporal {temp_file}: {str(e)}")
        
        gc.collect()
        logging.info("Recursos limpiados")

def main():
    st.title("Creación Automática de Videos")

    # Inicializar el estado de la sesión si es la primera vez
    if 'initialized' not in st.session_state:
        st.session_state['initialized'] = True
        st.session_state['progress'] = 0
        st.session_state['total_segments'] = 0
        st.session_state['font_size'] = DEFAULT_FONT_SIZE
        st.session_state['stretch_background'] = False
        st.session_state['bg_video_path'] = ""

    # Selección de archivo de texto
    uploaded_file = st.file_uploader("Selecciona un archivo de texto", type="txt")
    if uploaded_file is not None:
        texto = uploaded_file.read().decode('utf-8')
    else:
        texto = ""

    # Selección de voz
    selected_voice = st.selectbox("Selecciona una voz:", list(VOCES_DISPONIBLES.keys()))

    # Carpeta de destino
    output_folder = "videos"  # Carpeta fija para Streamlit

    # Nombre del video
    video_name = st.text_input("Nombre del video (sin extensión):", "video_generado")

    # Opciones de Personalización
    st.session_state['font_size'] = st.number_input("Tamaño de fuente:", min_value=10, max_value=100, value=st.session_state['font_size'])
    st.session_state['stretch_background'] = st.checkbox("Estirar fondo", value=st.session_state['stretch_background'])

    # Crear la carpeta temp si no existe.
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    # Selección de video de fondo (opcional)
    uploaded_video = st.file_uploader("Selecciona un video de fondo (opcional)", type=["mp4", "avi", "mov", "mkv"])
    if uploaded_video is not None:
        video_bytes = uploaded_video.read()
        print(f"Tamaño del video subido: {len(video_bytes)} bytes")
        # Guardar el video temporalmente
        temp_video_path = os.path.join(TEMP_DIR, uploaded_video.name)

        print(f"Intentando guardar el video en: {temp_video_path}")
        with open(temp_video_path, "wb") as f:
            f.write(video_bytes)
        st.session_state['bg_video_path'] = temp_video_path
    else:
        st.session_state['bg_video_path'] = ""

    # Previsualización
    if texto:
        try:
            if st.session_state['bg_video_path']:
                bg_video = VideoFileClip(st.session_state['bg_video_path'])
            else:
                bg_video = None

            image_data = create_text_overlay(
                text=texto,
                font_size=st.session_state['font_size'],
                text_color=TEXT_COLOR,
                background_video=bg_video,
                stretch_background=st.session_state['stretch_background'],
                full_size_background=True,
                bg_alpha=BG_ALPHA
            )
            st.image(image_data, caption="Previsualización del texto", use_column_width=True)

            if bg_video:
                bg_video.close()
        except Exception as e:
            st.error(f"Error al generar la previsualización: {str(e)}")

    # Generar video
    if st.button("Generar Video"):
        if not texto:
            st.warning("Por favor selecciona un archivo de texto.")
            return

        # Sanitiza el nombre del archivo
        nombre_archivo_sanitizado = sanitize_filename(video_name)
        # Construye la ruta de salida completa
        nombre_salida = os.path.join(output_folder, f"{nombre_archivo_sanitizado}.mp4")

        logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"

        video_generator = VideoGenerator(
            texto,
            nombre_salida,
            selected_voice,
            logo_url,
            st.session_state['font_size'],
            st.session_state['bg_video_path'],
            st.session_state['stretch_background']
        )

        st.session_state['progress'] = 0
        video_generator.generate_video()

    # Barra de progreso
    if st.session_state['progress'] > 0:
        progress_bar = st.progress(0)
        progress_bar.progress(st.session_state['progress'] / st.session_state['total_segments'])

if __name__ == '__main__':
    main()
