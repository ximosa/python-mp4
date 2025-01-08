import streamlit as st
import os
import tempfile
import logging
import re
import json
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, TextClip, CompositeVideoClip, VideoFileClip, ColorClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import requests
from io import BytesIO

# --- Configuración ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TEMP_DIR = tempfile.mkdtemp()
FONT_PATH = "arial.ttf"
DEFAULT_FONT_SIZE = 60
VIDEO_SIZE = (1280, 720)
TEXT_COLOR = "white"
BG_ALPHA = 0.7
VIDEO_CODEC = 'libx264'
AUDIO_CODEC = 'aac'

VOCES_DISPONIBLES = {
    'es-ES-Neural2-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Neural2-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-E': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-F': texttospeech.SsmlVoiceGender.MALE
}

LOGO_URL = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"

# --- Funciones de utilidad ---
def split_text_into_segments(text, max_segment_length=250):
    """Divide el texto en segmentos de una longitud máxima."""
    text = text.replace(".", ". ")
    words = text.split()
    segments = []
    current_segment = []

    for word in words:
        if len(" ".join(current_segment + [word])) <= max_segment_length:
            current_segment.append(word)
        else:
            segments.append(" ".join(current_segment))
            current_segment = [word]
    if current_segment:
        segments.append(" ".join(current_segment))
    return segments

def create_text_image(text, size=VIDEO_SIZE, font_size=DEFAULT_FONT_SIZE, text_color=TEXT_COLOR, bg_alpha=BG_ALPHA):
    """Crea una imagen con el texto centrado y fondo semitransparente."""
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception as e:
        logging.error(f"Error al cargar la fuente, usando la fuente predeterminada: {str(e)}")
        font = ImageFont.load_default()

    text_bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    text_x = (size[0] - text_width) // 2
    text_y = (size[1] - text_height) // 2

    bg_x1 = text_x - 20
    bg_y1 = text_y - 20
    bg_x2 = text_x + text_width + 20
    bg_y2 = text_y + text_height + 20

    bg_color_rgba = (0, 0, 0, int(255 * bg_alpha))
    draw.rectangle(((bg_x1, bg_y1), (bg_x2, bg_y2)), fill=bg_color_rgba)

    draw.multiline_text((text_x, text_y), text, font=font, fill=text_color, align="center")

    return np.array(img)

def create_subscription_image(logo_url, size=VIDEO_SIZE, font_size=40):
    """Crea la imagen de suscripción con el logo."""
    try:
        response = requests.get(logo_url, stream=True)
        response.raise_for_status()
        logo_img = Image.open(BytesIO(response.content)).convert("RGBA")
        logo_img = logo_img.resize((80, 80))
    except Exception as e:
        logging.error(f"Error al cargar el logo: {str(e)}")
        logo_img = Image.new('RGBA', (80, 80), (0, 0, 0, 0))

    img = Image.new('RGBA', size, (255, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception as e:
        logging.error(f"Error al cargar la fuente, usando la fuente predeterminada: {str(e)}")
        font = ImageFont.load_default()

    text1 = "¡SUSCRÍBETE!"
    text2 = "Activa la 🔔"
    text1_bbox = draw.textbbox((0, 0), text1, font=font)
    text2_bbox = draw.textbbox((0, 0), text2, font=font)
    text1_width = text1_bbox[2] - text1_bbox[0]
    text2_width = text2_bbox[2] - text2_bbox[0]
    text_x1 = (size[0] - text1_width) // 2
    text_x2 = (size[0] - text2_width) // 2
    text_y = (size[1] - 80) // 2 + 10

    draw.text((text_x1, text_y - 60), text1, font=font, fill="white")
    draw.text((text_x2, text_y + 10), text2, font=font, fill="white")
    img.paste(logo_img, ((size[0] - 80) // 2, text_y - 160), logo_img)

    return np.array(img)

# --- Clase VideoGenerator ---
class VideoGenerator:
    def __init__(self, voice, background_video_path=None, stretch_background=False):
        self.voice = voice
        self.background_video_path = background_video_path
        self.stretch_background = stretch_background
        self.client = texttospeech.TextToSpeechClient()
        self.video_clips = []
        self.audio_clips = []

    def generate_video(self, text):
        """Genera el video a partir del texto."""
        segments = split_text_into_segments(text)
        st.session_state['total_segments'] = len(segments)
        st.session_state['progress'] = 0
        try:
            for i, segment in enumerate(segments):
                audio_path = self._generate_audio(segment)
                self.audio_clips.append(AudioFileClip(audio_path))
                
                # Crear el clip de texto
                text_image = create_text_image(segment)
                text_clip = ImageClip(text_image, duration=self.audio_clips[-1].duration)

                # Manejar el video de fondo o clip de color
                if self.background_video_path:
                    try:
                        video_clip = VideoFileClip(self.background_video_path)
                        video_clip = video_clip.resize(VIDEO_SIZE)

                        # Calcular el inicio para que el video de fondo comience al principio
                        start_time = sum([clip.duration for clip in self.video_clips])

                        # Ajustar el videoclip para que coincida con la duración del clip de texto
                        video_clip = video_clip.subclip(start_time, start_time + text_clip.duration)
                        video_clip = video_clip.set_position(("center", "center"))
                        video_clip = video_clip.set_duration(text_clip.duration)
                        video_clip = video_clip.set_opacity(1)  # Ajusta la opacidad del fondo

                        # Combinar el clip de texto con el video de fondo
                        composite_clip = CompositeVideoClip([video_clip, text_clip.set_position(("center", "center"))])

                        # Establecer el audio del segmento en el clip compuesto
                        composite_clip = composite_clip.set_audio(self.audio_clips[-1])

                        # Agregar el clip compuesto a la lista de clips de video
                        self.video_clips.append(composite_clip)

                    except Exception as e:
                        logging.error(f"Error al procesar el video de fondo: {str(e)}")
                else:
                    # Si no hay video de fondo, usa el clip de texto con fondo de color
                    text_clip = text_clip.set_audio(self.audio_clips[-1])
                    self.video_clips.append(text_clip)

                st.session_state['progress'] = i + 1
                
            # Añadir la imagen de suscripción al final
            subscribe_image = create_subscription_image(LOGO_URL)
            subscribe_clip = ImageClip(subscribe_image, duration=2).set_position(("center", "center"))
            
            # Agregar un clip de color negro al final de la lista de clips de audio
            self.audio_clips.append(ColorClip(size=VIDEO_SIZE, color=(0, 0, 0), duration=2).audio)
            
            # Establecer el audio del clip de suscripción
            subscribe_clip = subscribe_clip.set_audio(self.audio_clips[-1])

            self.video_clips.append(subscribe_clip)

            # Concatenar todos los clips
            final_video = concatenate_videoclips(self.video_clips, method="compose")

            # Escribir el video en un archivo temporal
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmpfile:
                logging.info(f"Escribiendo video temporal en: {tmpfile.name}") # Print para depurar
                final_video.write_videofile(tmpfile.name, fps=24, codec=VIDEO_CODEC, audio_codec=AUDIO_CODEC, preset="ultrafast", threads=4)
                st.success("Video generado exitosamente")
                return tmpfile.name
        
        except Exception as e:
            logging.error(f"Error en la creación de video: {str(e)}")
            st.error(f"Error en la creación de video: {str(e)}")
            return None

        finally:
            # self._cleanup()  # Comenta esta línea temporalmente para la depuración
            # self.executor.shutdown() # Comenta o descomenta según corresponda.
            pass

    def _generate_audio(self, text):
        """Genera el audio a partir del texto usando la API de Google."""
        synthesis_input = texttospeech.SynthesisInput(text=text)
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
        temp_filename = os.path.join(TEMP_DIR, f"temp_audio_{len(self.audio_clips)}.mp3")
        logging.info(f"Escribiendo audio temporal en: {temp_filename}") # Print para depurar
        with open(temp_filename, "wb") as out:
            out.write(response.audio_content)
        return temp_filename

    def _cleanup(self, video_final=None):
        """Limpia los archivos temporales y cierra los clips."""
        logging.info("Limpiando recursos...")

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

# --- Interfaz de Streamlit ---
def main():
    st.title("Creación Automática de Videos")

    # Inicializar el estado de la sesión si es la primera vez
    if 'initialized' not in st.session_state:
        st.session_state['initialized'] = True
        st.session_state['progress'] = 0
        st.session_state['total_segments'] = 0
        st.session_state['stretch_background'] = False
        st.session_state['bg_video_path'] = ""

    # Selección de archivo de texto
    uploaded_file = st.file_uploader("Selecciona un archivo de texto", type="txt")
    if uploaded_file is not None:
        texto = uploaded_file.read().decode('utf-8')
        st.text_area("Texto del archivo", texto, height=200)
    else:
        texto = ""

    # Selección de voz
    selected_voice = st.selectbox("Selecciona una voz:", list(VOCES_DISPONIBLES.keys()))
    
    # Selección de video de fondo (opcional)
    uploaded_video = st.file_uploader("Selecciona un video de fondo (opcional)", type=["mp4", "avi", "mov", "mkv"])
    if uploaded_video is not None:
        video_bytes = uploaded_video.read()
        temp_video_path = os.path.join(TEMP_DIR, uploaded_video.name)
        with open(temp_video_path, "wb") as f:
            f.write(video_bytes)
        st.session_state['bg_video_path'] = temp_video_path
        st.video(video_bytes)
    else:
        st.session_state['bg_video_path'] = ""

    # Opciones de Personalización
    st.session_state['stretch_background'] = st.checkbox("Estirar fondo", value=st.session_state['stretch_background'])

    # Generar video
    if st.button("Generar Video"):
        if not texto:
            st.warning("Por favor selecciona un archivo de texto.")
            return

        video_generator = VideoGenerator(
            selected_voice,
            st.session_state['bg_video_path'],
            st.session_state['stretch_background']
        )

        video_path = video_generator.generate_video(texto)

        if video_path:
             with open(video_path, "rb") as file:
                st.download_button(
                    label="Descargar Video",
                    data=file,
                    file_name="video_generado.mp4",
                    mime="video/mp4"
                )

    # Barra de progreso
    if st.session_state['progress'] > 0:
        progress_bar = st.progress(0)
        progress_bar.progress(st.session_state['progress'] / st.session_state['total_segments'])

if __name__ == '__main__':
    main()
