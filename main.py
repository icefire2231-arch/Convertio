import os
import re
import uuid
import glob
import time
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "/app/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "a2bd111429msh83c883553856e13p183aedjsn7b31c244645b")
RAPIDAPI_HOST = "youtube-mp3-audio-video-downloader.p.rapidapi.com"

class ConvertRequest(BaseModel):
    url: str
    format: str = "mp4"
    quality: str = "1080p"

def extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
        r"youtu\.be\/([0-9A-Za-z_-]{11})"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""

def cleanup_old_files():
    now = time.time()
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        if os.path.isfile(f) and (now - os.path.getmtime(f) > 7200):
            try:
                os.remove(f)
            except Exception:
                pass

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/convert")
def convert(req: ConvertRequest):
    cleanup_old_files()
    video_id = extract_video_id(req.url)
    
    if not video_id:
        raise HTTPException(status_code=400, detail="Lien YouTube invalide.")
    
    file_id = str(uuid.uuid4())[:8]
    is_audio = req.format.lower() in ["mp3", "wav"]
    
    # 1. Conversion Audio via votre API RapidAPI
    if is_audio:
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": RAPIDAPI_HOST,
            "User-Agent": "Mozilla/5.0"
        }
        
        # Récupérer les informations du titre
        title = "audio"
        try:
            info_res = requests.get(
                f"https://{RAPIDAPI_HOST}/get-video-info/{video_id}",
                headers=headers,
                timeout=15
            )
            if info_res.status_code == 200:
                title = info_res.json().get("title", "audio")
        except Exception:
            pass
        
        safe_title = "".join(c for c in title if c.isalnum() or c in " ._-").strip()
        final_filename = f"{safe_title}.mp3"
        dest_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp3")
        
        try:
            # Téléchargement du flux audio
            with requests.get(
                f"https://{RAPIDAPI_HOST}/download-mp3/{video_id}",
                headers=headers,
                stream=True,
                timeout=120
            ) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            
            return {
                "success": True,
                "filename": final_filename,
                "downloadUrl": f"https://convertio-av9n.onrender.com/downloads/{file_id}.mp3"
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erreur téléchargement audio : {str(e)}")

    # 2. Conversion Vidéo (MP4 / WEBM)
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    max_height = 720 if req.quality == "720p" else (1440 if req.quality in ["2k", "1440p"] else 1080)
    
    ydl_opts = {
        "outtmpl": output_template,
        "format": f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={max_height}][ext=mp4]/best",
        "merge_output_format": req.format.lower(),
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios"]
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            title = info.get("title", "video")
            safe_title = "".join(c for c in title if c.isalnum() or c in " ._-").strip()
            final_filename = f"{safe_title}.{req.format.lower()}"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de conversion vidéo : {str(e)}")
        
    generated = glob.glob(os.path.join(DOWNLOAD_DIR, f"{file_id}.*"))
    if not generated:
        raise HTTPException(status_code=500, detail="Fichier non trouvé.")
        
    actual = os.path.basename(generated[0])
    return {
        "success": True,
        "filename": final_filename,
        "downloadUrl": f"https://convertio-av9n.onrender.com/downloads/{actual}"
    }
