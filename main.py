import os
import uuid
import glob
import time
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

class ConvertRequest(BaseModel):
    url: str
    format: str = "mp4"
    quality: str = "1080p"

def cleanup_old_files():
    now = time.time()
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        # Supprime les fichiers créés il y a plus de 2 heures
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
    
    file_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    
    is_audio = req.format.lower() in ["mp3", "wav"]
    
       # Configuration multi-clients sans blocage de page
    extractor_args = {
        "youtube": {
            "player_client": ["android", "ios", "mweb"]
        }
    }

    
    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": extractor_args,
    }
    
    if is_audio:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": req.format.lower(),
            "preferredquality": "192",
        }]
    else:
        # Vidéo
        max_height = 1080
        if req.quality == "720p":
            max_height = 720
        elif req.quality in ["2k", "1440p"]:
            max_height = 1440

        ydl_opts["format"] = f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best"
        ydl_opts["merge_output_format"] = req.format.lower()
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            title = info.get("title", "video")
            # Nettoyer les caractères spéciaux pour le nom de fichier
            safe_title = "".join(c for c in title if c.isalnum() or c in " ._-").strip()
            final_filename = f"{safe_title}.{req.format.lower()}"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de conversion : {str(e)}")
    
    # Trouver le fichier généré
    generated_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{file_id}.*"))
    if not generated_files:
        raise HTTPException(status_code=500, detail="Fichier non trouvé après la conversion.")
    
    actual_file = os.path.basename(generated_files[0])
    download_url = f"https://convertio-av9n.onrender.com/downloads/{actual_file}"
    
    return {
        "success": True,
        "filename": final_filename,
        "downloadUrl": download_url
    }
