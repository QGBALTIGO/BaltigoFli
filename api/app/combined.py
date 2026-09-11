from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .main import app as api_app
from .shop_cloud import router as shop_cloud_router


api_app.include_router(shop_cloud_router)

app = FastAPI(title="Baltigo Live Cloud")
app.mount("/api", api_app)

web_dir = Path("/app/web")
if web_dir.exists():
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
