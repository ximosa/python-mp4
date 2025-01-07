import streamlit as st
import os
import json
import logging
import time
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips, VideoFileClip, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import tempfile
import requests
from io import BytesIO
from moviepy.video.fx.all import colorx

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
        video_clip = VideoFileClip(video_path)
        # Oscurecer el video
        video_clip = colorx(video_clip, 0.5)

        # Redimensionar usando PIL para evitar problemas de ANTIALIAS
        def resize_frame(frame):
            img = Image.fromarray(frame)
            img.thumbnail(VIDEO_SIZE, Image.Resampling.LANCZOS)
            new_img = Image.new('RGB', VIDEO_SIZE, (0,0,0))
            new_img.paste(img, ((VIDEO_SIZE[0]-img.width)//2, (VIDEO_SIZE[1]-img.height)//2))
            return np.array(new_img)
        
        video_clip = video_clip.fl_image(resize_frame)
        
        
        if video_clip.duration < duration:
          video_clip = video_clip.loop(duration = duration)
          
        
        return video_clip
    except Exception as e:
        logging.error(f"Error al cargar o procesar video de fondo: {str(e)}")
        return None
    

def create_text_image(text, size=IMAGE_SIZE_TEXT, font_size=DEFAULT_FONT_SIZE,
                      bg_color="black", text_color="white",
                      full_size_background=False):
    """Creates a text image with the specified text and styles."""
    if full_size_background:
        size = VIDEO_SIZE

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
    
def create_final_clips(texto, voz, logo_url, font_size, bg_color, text_color,
                 background_video):
    archivos_temp = []
    clips_audio = []
    clips_finales = []
    
    tiempo_acumulado = 0
    
    try:
      logging.info("Iniciando proceso de creación de video...")
      frases = [f.strip() + "." for f in texto.split('.') if f.strip()]
      client = texttospeech.TextToSpeechClient()
        
        # Agrupamos frases en segmentos
      segmentos_texto = []
      segmento_actual = ""
      for frase in frases:
        if len(segmento_actual) + len(frase) < 300:
          segmento_actual += " " + frase
        else:
          segmentos_texto.append(segmento_actual.strip())
          segmento_actual = frase
      segmentos_texto.append(segmento_actual.strip())
        
        # Cargar clip de video de fondo, si se especifica
      if background_video:
          
          
          
          # Calcular la duracion total del video
          total_duration = 0
          for segmento in segmentos_texto:
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
                  break
                except Exception as e:
                    logging.error(f"Error al solicitar audio (intento {retry_count + 1}): {str(e)}")
                    if "429" in str(e):
                      retry_count +=1
                      time.sleep(2**retry_count)
                    else:
                      raise
                
              if retry_count > max_retries:
                  raise Exception("Maximos intentos de reintento alcanzado")
                    
              temp_filename = f"temp_audio_duration_calc_{len(archivos_temp)}.mp3"
              archivos_temp.append(temp_filename)
              with open(temp_filename, "wb") as out:
                  out.write(response.audio_content)
                
              audio_clip_duration = AudioFileClip(temp_filename)
              total_duration += audio_clip_duration.duration
              audio_clip_duration.close()
              time.sleep(0.2)
                
          total_duration += SUBSCRIPTION_DURATION

          background_video_clip = create_video_background_clip(background_video, total_duration)  # Duración máxima del clip de fondo
          if not background_video_clip:
              return False, "Error al cargar el clip de video de fondo."
          clips_finales.append(background_video_clip.set_start(0))
        
      for i, segmento in enumerate(segmentos_texto):
        logging.info(f"Procesando segmento {i+1} de {len(segmentos_texto)}")
            
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
            break
          except Exception as e:
              logging.error(f"Error al solicitar audio (intento {retry_count + 1}): {str(e)}")
              if "429" in str(e):
                retry_count +=1
                time.sleep(2**retry_count)
              else:
                raise
            
        if retry_count > max_retries:
            raise Exception("Maximos intentos de reintento alcanzado")
            
        temp_filename = f"temp_audio_{i}.mp3"
        archivos_temp.append(temp_filename)
        with open(temp_filename, "wb") as out:
            out.write(response.audio_content)
            
        audio_clip = AudioFileClip(temp_filename)
        clips_audio.append(audio_clip)
        duracion = audio_clip.duration
            
        text_img = create_text_image(segmento, font_size=font_size,
                                  bg_color=bg_color, text_color=text_color,
                                  full_size_background=True)
        txt_clip = (ImageClip(text_img)
                  .set_start(tiempo_acumulado)
                  .set_duration(duracion)
                  .set_position('center'))
        
        txt_clip = txt_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
            
        clips_finales.append(txt_clip)
        tiempo_acumulado += duracion
        time.sleep(0.2)

        # Añadir clip de suscripción
      subscribe_img = create_subscription_image(logo_url) # Usamos la función creada
        
      subscribe_clip = (ImageClip(subscribe_img)
                      .set_start(tiempo_acumulado)
                      .set_duration(SUBSCRIPTION_DURATION)
                      .set_position('center'))
        
      clips_finales.append(subscribe_clip)
      
      return clips_finales, archivos_temp, clips_audio, background_video_clip if background_video else None
      
    except Exception as e:
      logging.error(f"Error: {str(e)}")
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
      return False, str(e) ,None, None


def create_simple_video(texto, nombre_salida, voz, logo_url, font_size, bg_color, text_color,
                 background_video):
    
    try:
      clips_finales, archivos_temp, clips_audio, background_video_clip  = create_final_clips(texto, voz, logo_url, font_size, bg_color, text_color,
                  background_video)
      if not clips_finales:
        return False, archivos_temp
      
      video_final = concatenate_videoclips(clips_finales, method="compose")
      
      video_final.write_videofile(
          nombre_salida,
          fps=24,
          codec='libx264',
          audio_codec='aac',
          preset='ultrafast',
          threads=4
      )
        
      video_final.close()
      
      if background_video_clip:
        background_video_clip.close()
      
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
