from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .main import app as api_app


app = FastAPI(title="Baltigo Live Cloud")
app.mount("/api", api_app)

web_dir = Path("/app/web")
if web_dir.exists():
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
