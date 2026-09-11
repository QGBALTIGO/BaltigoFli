import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .database import SessionLocal, init_db
from .media import probe
from .models import Destination, MediaAsset, Playlist, PlaylistItem, StreamJob
from .schemas import DestinationCreate, PlaylistCreate, StreamCreate
from .security import encrypt_secret, require_api_key


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Baltigo Live Cloud API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def media_dict(item: MediaAsset) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "original_filename": item.original_filename,
        "size_bytes": item.size_bytes,
        "duration_seconds": item.duration_seconds,
        "width": item.width,
        "height": item.height,
        "fps": item.fps,
        "video_codec": item.video_codec,
        "audio_codec": item.audio_codec,
        "created_at": item.created_at,
    }


def destination_dict(item: Destination) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "platform": item.platform,
        "rtmp_url": item.rtmp_url,
        "stream_key_masked": "••••••••",
        "enabled": item.enabled,
        "created_at": item.created_at,
    }


def playlist_dict(item: Playlist) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "created_at": item.created_at,
        "items": [
            {"position": x.position, "media": media_dict(x.media)}
            for x in sorted(item.items, key=lambda v: v.position)
        ],
    }


def stream_dict(item: StreamJob) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "destination_id": item.destination_id,
        "destination_name": item.destination.name if item.destination else None,
        "platform": item.destination.platform if item.destination else None,
        "media_id": item.media_id,
        "media_name": item.media.name if item.media else None,
        "playlist_id": item.playlist_id,
        "playlist_name": item.playlist.name if item.playlist else None,
        "loop": item.loop,
        "desired_state": item.desired_state,
        "status": item.status,
        "scheduled_at": item.scheduled_at,
        "started_at": item.started_at,
        "stopped_at": item.stopped_at,
        "heartbeat_at": item.heartbeat_at,
        "worker_id": item.worker_id,
        "restart_count": item.restart_count,
        "last_error": item.last_error,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@app.get("/health")
def health():
    return {"ok": True, "service": "baltigo-live-cloud"}


@app.get("/dashboard", dependencies=[Depends(require_api_key)])
def dashboard(db: Session = Depends(db_session)):
    return {
        "media": db.scalar(select(func.count()).select_from(MediaAsset)),
        "destinations": db.scalar(select(func.count()).select_from(Destination)),
        "playlists": db.scalar(select(func.count()).select_from(Playlist)),
        "streams": db.scalar(select(func.count()).select_from(StreamJob)),
        "live": db.scalar(select(func.count()).select_from(StreamJob).where(StreamJob.status == "live")),
        "recovering": db.scalar(select(func.count()).select_from(StreamJob).where(StreamJob.status == "recovering")),
    }


@app.get("/media", dependencies=[Depends(require_api_key)])
def list_media(db: Session = Depends(db_session)):
    return [media_dict(x) for x in db.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())).all()]


@app.post("/media", dependencies=[Depends(require_api_key)])
def upload_media(file: UploadFile = File(...), name: str | None = Form(default=None), db: Session = Depends(db_session)):
    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".mkv", ".m4v", ".webm"}:
        raise HTTPException(400, "Unsupported file extension")
    target = settings.media_dir / f"{uuid.uuid4()}{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "Empty upload")
    try:
        metadata = probe(target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"ffprobe could not read this video: {exc}") from exc
    item = MediaAsset(
        name=(name or Path(file.filename or "Video").stem)[:255],
        original_filename=(file.filename or target.name)[:255],
        storage_path=str(target),
        mime_type=file.content_type,
        size_bytes=target.stat().st_size,
        **metadata,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return media_dict(item)


@app.delete("/media/{media_id}", dependencies=[Depends(require_api_key)])
def delete_media(media_id: str, db: Session = Depends(db_session)):
    item = db.get(MediaAsset, media_id)
    if not item:
        raise HTTPException(404, "Media not found")
    path = Path(item.storage_path)
    try:
        db.delete(item)
        db.commit()
        path.unlink(missing_ok=True)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Media is in use by a playlist or stream") from exc
    return {"ok": True}


@app.get("/destinations", dependencies=[Depends(require_api_key)])
def list_destinations(db: Session = Depends(db_session)):
    return [destination_dict(x) for x in db.scalars(select(Destination).order_by(Destination.created_at.desc())).all()]


@app.post("/destinations", dependencies=[Depends(require_api_key)])
def create_destination(payload: DestinationCreate, db: Session = Depends(db_session)):
    if not payload.rtmp_url.lower().startswith(("rtmp://", "rtmps://")):
        raise HTTPException(400, "Server URL must start with rtmp:// or rtmps://")
    item = Destination(
        name=payload.name,
        platform=payload.platform.lower(),
        rtmp_url=payload.rtmp_url.strip(),
        encrypted_stream_key=encrypt_secret(payload.stream_key.strip()),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return destination_dict(item)


@app.delete("/destinations/{destination_id}", dependencies=[Depends(require_api_key)])
def delete_destination(destination_id: str, db: Session = Depends(db_session)):
    item = db.get(Destination, destination_id)
    if not item:
        raise HTTPException(404, "Destination not found")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Destination is in use by a stream") from exc
    return {"ok": True}


@app.get("/playlists", dependencies=[Depends(require_api_key)])
def list_playlists(db: Session = Depends(db_session)):
    query = select(Playlist).options(selectinload(Playlist.items).selectinload(PlaylistItem.media)).order_by(Playlist.created_at.desc())
    return [playlist_dict(x) for x in db.scalars(query).all()]


@app.post("/playlists", dependencies=[Depends(require_api_key)])
def create_playlist(payload: PlaylistCreate, db: Session = Depends(db_session)):
    media = {x.id: x for x in db.scalars(select(MediaAsset).where(MediaAsset.id.in_(payload.media_ids))).all()}
    missing = [media_id for media_id in payload.media_ids if media_id not in media]
    if missing:
        raise HTTPException(400, f"Unknown media IDs: {', '.join(missing)}")
    item = Playlist(name=payload.name)
    db.add(item)
    db.flush()
    for position, media_id in enumerate(payload.media_ids):
        db.add(PlaylistItem(playlist_id=item.id, media_id=media_id, position=position))
    db.commit()
    query = select(Playlist).where(Playlist.id == item.id).options(selectinload(Playlist.items).selectinload(PlaylistItem.media))
    return playlist_dict(db.scalar(query))


@app.delete("/playlists/{playlist_id}", dependencies=[Depends(require_api_key)])
def delete_playlist(playlist_id: str, db: Session = Depends(db_session)):
    item = db.get(Playlist, playlist_id)
    if not item:
        raise HTTPException(404, "Playlist not found")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Playlist is in use by a stream") from exc
    return {"ok": True}


def stream_query():
    return select(StreamJob).options(
        selectinload(StreamJob.destination),
        selectinload(StreamJob.media),
        selectinload(StreamJob.playlist),
    )


@app.get("/streams", dependencies=[Depends(require_api_key)])
def list_streams(db: Session = Depends(db_session)):
    return [stream_dict(x) for x in db.scalars(stream_query().order_by(StreamJob.created_at.desc())).all()]


@app.post("/streams", dependencies=[Depends(require_api_key)])
def create_stream(payload: StreamCreate, db: Session = Depends(db_session)):
    if not db.get(Destination, payload.destination_id):
        raise HTTPException(400, "Destination not found")
    if payload.media_id and not db.get(MediaAsset, payload.media_id):
        raise HTTPException(400, "Media not found")
    if payload.playlist_id and not db.get(Playlist, payload.playlist_id):
        raise HTTPException(400, "Playlist not found")
    status = "scheduled" if payload.scheduled_at else "stopped"
    desired = "running" if payload.scheduled_at else "stopped"
    item = StreamJob(
        name=payload.name,
        destination_id=payload.destination_id,
        media_id=payload.media_id,
        playlist_id=payload.playlist_id,
        loop=payload.loop,
        scheduled_at=payload.scheduled_at,
        desired_state=desired,
        status=status,
    )
    db.add(item)
    db.commit()
    item = db.scalar(stream_query().where(StreamJob.id == item.id))
    return stream_dict(item)


@app.post("/streams/{stream_id}/start", dependencies=[Depends(require_api_key)])
def start_stream(stream_id: str, db: Session = Depends(db_session)):
    item = db.get(StreamJob, stream_id)
    if not item:
        raise HTTPException(404, "Stream not found")
    item.desired_state = "running"
    item.scheduled_at = None
    item.status = "starting" if item.status != "live" else item.status
    item.last_error = None
    db.commit()
    return {"ok": True}


@app.post("/streams/{stream_id}/stop", dependencies=[Depends(require_api_key)])
def stop_stream(stream_id: str, db: Session = Depends(db_session)):
    item = db.get(StreamJob, stream_id)
    if not item:
        raise HTTPException(404, "Stream not found")
    item.desired_state = "stopped"
    item.status = "stopping" if item.status in {"live", "starting", "recovering"} else "stopped"
    db.commit()
    return {"ok": True}


@app.delete("/streams/{stream_id}", dependencies=[Depends(require_api_key)])
def delete_stream(stream_id: str, db: Session = Depends(db_session)):
    item = db.get(StreamJob, stream_id)
    if not item:
        raise HTTPException(404, "Stream not found")
    if item.desired_state == "running" or item.status in {"live", "starting", "recovering"}:
        raise HTTPException(409, "Stop the stream before deleting it")
    db.delete(item)
    db.commit()
    Path(settings.log_dir / f"{stream_id}.log").unlink(missing_ok=True)
    Path(settings.log_dir / f"{stream_id}.concat.txt").unlink(missing_ok=True)
    return {"ok": True}


@app.get("/streams/{stream_id}/logs", dependencies=[Depends(require_api_key)])
def stream_logs(stream_id: str, lines: int = 120):
    lines = max(10, min(lines, 500))
    path = settings.log_dir / f"{stream_id}.log"
    if not path.exists():
        return {"lines": []}
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": content[-lines:]}
