import os
import uuid
import datetime
from typing import Dict
from pydantic import BaseModel
from pytubefix import YouTube
from moviepy import AudioFileClip
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from openai import OpenAI
from dotenv import load_dotenv
from pydub import AudioSegment
import math

# Load environment variables
load_dotenv()

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Create directories for storing files
os.makedirs("temp_audio", exist_ok=True)
os.makedirs("transcripts", exist_ok=True)

# OpenAI client initialization
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Maximum size in bytes (slightly under 25MB to be safe)
MAX_SIZE_BYTES = 25 * 1024 * 1024

# Request model
class YoutubeUrlRequest(BaseModel):
    youtubeUrl: str

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/convert")
async def convert_youtube(youtube_request: YoutubeUrlRequest):
    try:
        url = youtube_request.youtubeUrl
        
        # Validate YouTube URL
        if not ("youtube.com" in url or "youtu.be" in url):
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")
        
        # Generate unique ID for this conversion
        file_id = str(uuid.uuid4())
        
        # Download YouTube video and convert to MP3
        audio_path = download_youtube_as_mp3(url, file_id)
        
        # Get video information
        yt = YouTube(url)
        video_title = yt.title
        current_date = datetime.datetime.now().strftime("%d %B %Y")
        
        # Split audio if needed and transcribe
        transcript = transcribe_large_audio(audio_path)
        
        # Create formatted transcript
        formatted_transcript = (
            f'<CGSourcedDoc "source": "{url}">\n'
            f'Title: {video_title}\n'
            f'Date: {current_date}.\n'
            f'Speakers: [Speakers information not available]\n'
            f'Transcript: {transcript}'
        )
        
        # Save transcript to file
        transcript_path = os.path.join("transcripts", f"{file_id}.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(formatted_transcript)
        
        # Clean up audio file
        os.remove(audio_path)
        
        return {
            "fileId": file_id,
            "transcript": formatted_transcript
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{file_id}")
async def download_transcript(file_id: str):
    transcript_path = os.path.join("transcripts", f"{file_id}.txt")
    
    if not os.path.exists(transcript_path):
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    return FileResponse(
        transcript_path,
        media_type="text/plain",
        filename="transcript.txt"
    )

def download_youtube_as_mp3(url: str, file_id: str) -> str:
    try:
        # Create YouTube object
        yt = YouTube(url)
        
        # Get the highest quality audio stream
        audio_stream = yt.streams.filter(only_audio=True).first()
        
        if not audio_stream:
            raise Exception("No audio stream found for this video")
        
        # Download the audio
        audio_file = audio_stream.download(output_path="temp_audio", filename=f"{file_id}_temp")
        
        # Convert to MP3
        clip = AudioFileClip(audio_file)
        mp3_path = os.path.join("temp_audio", f"{file_id}.mp3")
        clip.write_audiofile(mp3_path, logger=None)
        
        # Close the audio clip
        clip.close()
        
        # Remove the original downloaded file
        os.remove(audio_file)
        
        return mp3_path
    
    except Exception as e:
        raise Exception(f"Error downloading YouTube video: {str(e)}")

def split_audio(file_path, max_size_bytes=MAX_SIZE_BYTES):
    """Split audio file into segments that are under the max size limit"""
    audio = AudioSegment.from_file(file_path)
    
    # Get file size in bytes
    file_size = os.path.getsize(file_path)
    
    if file_size <= max_size_bytes:
        return [file_path]  # No need to split
    
    # Calculate how many segments we need
    num_segments = math.ceil(file_size / max_size_bytes)
    
    # Calculate segment duration in milliseconds
    segment_duration = len(audio) / num_segments
    
    # Create segments
    segments_paths = []
    for i in range(num_segments):
        start_ms = int(i * segment_duration)
        end_ms = int((i + 1) * segment_duration)
        
        # Handle the last segment
        if end_ms > len(audio):
            end_ms = len(audio)
        
        # Extract segment
        segment = audio[start_ms:end_ms]
        
        # Generate segment file path
        segment_path = os.path.join("temp_audio", f"{os.path.splitext(os.path.basename(file_path))[0]}_segment_{i}.mp3")
        
        # Export segment
        segment.export(segment_path, format="mp3")
        
        segments_paths.append(segment_path)
    
    return segments_paths

def transcribe_large_audio(audio_path: str) -> str:
    try:
        # Split audio into segments if needed
        segment_paths = split_audio(audio_path)
        
        # Transcribe each segment
        transcriptions = []
        
        for i, segment_path in enumerate(segment_paths):
            print(f"Transcribing segment {i+1}/{len(segment_paths)}...")
            
            with open(segment_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            
            transcriptions.append(response.text)
            
            # Clean up segment file if it's not the original
            if segment_path != audio_path:
                os.remove(segment_path)
        
        # Combine all transcriptions
        full_transcript = " ".join(transcriptions)
        
        return full_transcript
    
    except Exception as e:
        raise Exception(f"Error transcribing audio: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
