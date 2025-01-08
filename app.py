import streamlit as st
import os
import json
import logging
import time
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips, TextClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import tempfile
import requests
from io import BytesIO

logging.basicConfig(level=logging.INFO)

# Other constants and configurations remain the same

def create_text_video(text, font_size=DEFAULT_FONT_SIZE, text_color="white", background_video=None):
    """Creates a video clip with the specified text and background video."""
    video_clip = VideoFileClip(background_video).subclip(0, 10)  # Use the first 10 seconds of the video
    txt_clip = (TextClip(text, fontsize=font_size, color=text_color, font=FONT_PATH)
                .set_position('center')
                .set_duration(video_clip.duration))
    return CompositeVideoClip([video_clip, txt_clip])

def create_simple_video_with_video_bg(texto, nombre_salida, voz, logo_url, font_size, text_color, background_video):
    archivos_temp = []
    clips_audio = []
    clips_finales = []
    
    try:
        logging.info("Iniciando proceso de creación de video...")
        frases = [f.strip() + "." for f in texto.split('.') if f.strip()]
        client = texttospeech.TextToSpeechClient()
        
        tiempo_acumulado = 0
        
        # Agrupamos frases en segmentos (same as original)
        segmentos_texto = []
        segmento_actual = ""
        for frase in frases:
            if len(segmento_actual) + len(frase) < 300:
                segmento_actual += " " + frase
            else:
                segmentos_texto.append(segmento_actual.strip())
                segmento_actual = frase
        segmentos_texto.append(segmento_actual.strip())
        
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
                        retry_count += 1
                        time.sleep(2**retry_count)
                    else:
                        raise
            
            if retry_count > max_retries:
                raise Exception("Máximos intentos de reintento alcanzado")
            
            temp_filename = f"temp_audio_{i}.mp3"
            archivos_temp.append(temp_filename)
            with open(temp_filename, "wb") as out:
                out.write(response.audio_content)
            
            audio_clip = AudioFileClip(temp_filename)
            clips_audio.append(audio_clip)
            duracion = audio_clip.duration
            
            text_video = create_text_video(segmento, font_size=font_size, text_color=text_color, background_video=background_video)
            text_video = text_video.set_duration(duracion).set_start(tiempo_acumulado)
            
            video_segment = text_video.set_audio(audio_clip.set_start(tiempo_acumulado))
            clips_finales.append(video_segment)
            
            tiempo_acumulado += duracion
            time.sleep(0.2)
        
        # Añadir clip de suscripción (same as original)
        subscribe_img = create_subscription_image(logo_url)
        duracion_subscribe = 5

        subscribe_clip = (ImageClip(subscribe_img)
                        .set_start(tiempo_acumulado)
                        .set_duration(duracion_subscribe)
                        .set_position('center'))

        clips_finales.append(subscribe_clip)
        
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

# Update the Streamlit UI to accept video background files
def main():
    st.title("Creador de Videos Automático")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    
    with st.sidebar:
        st.header("Configuración del Video")
        voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
        font_size = st.slider("Tamaño de la fuente", min_value=10, max_value=100, value=DEFAULT_FONT_SIZE)
        text_color = st.color_picker("Color de texto", value="#ffffff")
        background_video = st.file_uploader("Video de fondo (opcional)", type=["mp4", "mov", "avi"])
    
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
                
                success, message = create_simple_video_with_video_bg(texto, nombre_salida_completo, voz_seleccionada, logo_url,
                                                                     font_size, text_color, video_path)
                if success:
                    st.success(message)
                    st.video(nombre_salida_completo)
                    with open(nombre_salida_completo, 'rb') as file:
                        st.download_button(label="Descargar video", data=file, file_name=nombre_salida_completo)
                    
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
