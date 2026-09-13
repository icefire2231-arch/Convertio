import os
import uuid
import glob
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="GRAB.IO Converter API")

# Autoriser les requêtes CORS depuis le frontend Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Nettoyage des fichiers datant de plus de 30 minutes
def cleanup_old_files():
    now = time.time()
    for f in glob.glob(os.path.join(DOWNLOADS_DIR, "*")):
        if os.stat(f).st_mtime < now - 1800:
            try:
                os.remove(f)
            except OSError:
                pass

class ConvertRequest(BaseModel):
    url: str
    format: str = "mp4"
    quality: str = "1080p"

@app.post("/convert")
async def convert(req: ConvertRequest, request: Request):
    cleanup_old_files()

    file_id = str(uuid.uuid4())[:8]
    ext = req.format.lower()
    is_audio = ext in ["mp3", "wav"]
    out_tmpl = os.path.join(DOWNLOADS_DIR, f"{file_id}.%(ext)s")

    # Options de qualité vidéo
    height_map = {"720p": 720, "1080p": 1080, "2k": 1440}
    max_height = height_map.get(req.quality, 1080)

      ydl_opts = {
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "mweb"]
            }
        },
    }


    if is_audio:
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": ext,
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts.update({
            "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
            "merge_output_format": ext,
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            original_title = info.get("title", "media")
            safe_title = "".join(c for c in original_title if c.isalnum() or c in (' ', '-', '_')).strip()
            final_filename = f"{safe_title or 'media'}.{ext}"

        # Détection du fichier produit sur le disque
        matching_files = glob.glob(os.path.join(DOWNLOADS_DIR, f"{file_id}.*"))
        if not matching_files:
            raise HTTPException(status_code=500, detail="Fichier non généré.")

        actual_file = os.path.basename(matching_files[0])
        base_url = str(request.base_url).rstrip("/")
        download_url = f"{base_url}/downloads/{actual_file}"

        return {
            "success": True,
            "filename": final_filename,
            "downloadUrl": download_url
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de conversion : {str(e)}")

# Servir les fichiers convertis
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

@app.get("/health")
def health():
    return {"status": "ok"}
