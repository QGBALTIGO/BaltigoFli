import ipaddress
import shutil
import socket
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .database import SessionLocal, init_db
from .media import normalize_for_stream, probe
from .models import Destination, MediaAsset, Playlist, PlaylistItem, StreamJob
from .schemas import DestinationCreate, DestinationUpdate, PlaylistCreate, StreamCreate, StreamUpdate
from .security import encrypt_secret, require_api_key


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Baltigo Live Cloud API", version="0.2.0", lifespan=lifespan)
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


def orientation_for(width: int | None, height: int | None) -> str:
    return "vertical" if width and height and height > width else "horizontal"


def is_stream_ready(item: MediaAsset) -> bool:
    dimensions = {(720, 1280), (1280, 720)}
    return (
        item.video_codec == "h264"
        and item.audio_codec == "aac"
        and (item.width, item.height) in dimensions
        and item.fps is not None
        and 29 <= item.fps <= 31
    )


def worker_online() -> bool:
    heartbeat = settings.log_dir / "worker.heartbeat"
    if not heartbeat.exists():
        return False
    try:
        return time.time() - heartbeat.stat().st_mtime <= max(15, settings.worker_poll_seconds * 4)
    except OSError:
        return False


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
        "orientation": orientation_for(item.width, item.height),
        "stream_ready": is_stream_ready(item),
        "created_at": item.created_at,
    }


def destination_dict(item: Destination) -> dict:
    parsed = urlparse(item.rtmp_url)
    return {
        "id": item.id,
        "name": item.name,
        "platform": item.platform,
        "rtmp_url": item.rtmp_url,
        "host": parsed.hostname,
        "stream_key_masked": "••••••••",
        "enabled": item.enabled,
        "created_at": item.created_at,
    }


def playlist_dict(item: Playlist) -> dict:
    items = sorted(item.items, key=lambda v: v.position)
    total_duration = sum((x.media.duration_seconds or 0) for x in items)
    orientation = orientation_for(items[0].media.width, items[0].media.height) if items else None
    return {
        "id": item.id,
        "name": item.name,
        "created_at": item.created_at,
        "orientation": orientation,
        "duration_seconds": round(total_duration, 3),
        "items": [
            {"position": x.position, "media": media_dict(x.media)}
            for x in items
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


def stream_query():
    return select(StreamJob).options(
        selectinload(StreamJob.destination),
        selectinload(StreamJob.media),
        selectinload(StreamJob.playlist),
    )


def _validate_rtmp_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"rtmp", "rtmps"} or not parsed.hostname:
        raise HTTPException(400, "Informe uma URL RTMP/RTMPS válida")
    return value


def _resolve_public_addresses(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(400, "Não foi possível resolver o servidor RTMP") from exc
    addresses = sorted({info[4][0] for info in infos})
    for value in addresses:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, "Por segurança, destinos RTMP em redes privadas não são permitidos")
    return addresses


@app.get("/health")
def health():
    return {"ok": True, "service": "baltigo-live-cloud", "worker_online": worker_online()}


@app.get("/system", dependencies=[Depends(require_api_key)])
def system_status():
    usage = shutil.disk_usage(settings.media_dir)
    return {
        "worker_online": worker_online(),
        "worker_id": settings.worker_id,
        "storage_persistent": settings.storage_persistent,
        "disk_total_bytes": usage.total,
        "disk_used_bytes": usage.used,
        "disk_free_bytes": usage.free,
        "max_upload_bytes": settings.max_upload_bytes,
        "normalize_uploads": settings.normalize_uploads,
    }


@app.get("/dashboard", dependencies=[Depends(require_api_key)])
def dashboard(db: Session = Depends(db_session)):
    return {
        "media": db.scalar(select(func.count()).select_from(MediaAsset)) or 0,
        "destinations": db.scalar(select(func.count()).select_from(Destination)) or 0,
        "playlists": db.scalar(select(func.count()).select_from(Playlist)) or 0,
        "streams": db.scalar(select(func.count()).select_from(StreamJob)) or 0,
        "live": db.scalar(select(func.count()).select_from(StreamJob).where(StreamJob.status == "live")) or 0,
        "starting": db.scalar(select(func.count()).select_from(StreamJob).where(StreamJob.status == "starting")) or 0,
        "recovering": db.scalar(select(func.count()).select_from(StreamJob).where(StreamJob.status == "recovering")) or 0,
        "scheduled": db.scalar(select(func.count()).select_from(StreamJob).where(StreamJob.status == "scheduled")) or 0,
    }


@app.get("/media", dependencies=[Depends(require_api_key)])
def list_media(db: Session = Depends(db_session)):
    return [media_dict(x) for x in db.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())).all()]


@app.post("/media", dependencies=[Depends(require_api_key)])
def upload_media(file: UploadFile = File(...), name: str | None = Form(default=None), db: Session = Depends(db_session)):
    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}:
        raise HTTPException(400, "Formato não suportado. Envie MP4, MOV, MKV, M4V, WEBM ou AVI")

    upload_id = str(uuid.uuid4())
    raw = settings.media_dir / f".{upload_id}.upload{suffix}"
    target = settings.media_dir / f"{upload_id}.mp4"
    total = 0
    try:
        with raw.open("wb") as output:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(413, f"Arquivo maior que o limite de {settings.max_upload_bytes // 1_000_000} MB")
                output.write(chunk)
        if total == 0:
            raise HTTPException(400, "O arquivo enviado está vazio")

        metadata = probe(raw)
        if not metadata.get("width") or not metadata.get("height"):
            raise HTTPException(400, "O arquivo não contém uma faixa de vídeo válida")

        if settings.normalize_uploads:
            normalized = normalize_for_stream(raw, target, metadata)
            raw.unlink(missing_ok=True)
            metadata = normalized
        else:
            raw.replace(target)

        item = MediaAsset(
            name=(name or Path(file.filename or "Vídeo").stem)[:255],
            original_filename=(file.filename or target.name)[:255],
            storage_path=str(target),
            mime_type="video/mp4",
            size_bytes=target.stat().st_size,
            duration_seconds=metadata.get("duration_seconds"),
            width=metadata.get("width"),
            height=metadata.get("height"),
            fps=metadata.get("fps"),
            video_codec=metadata.get("video_codec"),
            audio_codec=metadata.get("audio_codec"),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return media_dict(item)
    except HTTPException:
        raw.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        raw.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"Não foi possível preparar o vídeo para transmissão: {str(exc)[-1200:]}") from exc


@app.get("/media/{media_id}/file", dependencies=[Depends(require_api_key)])
def media_file(media_id: str, db: Session = Depends(db_session)):
    item = db.get(MediaAsset, media_id)
    if not item:
        raise HTTPException(404, "Vídeo não encontrado")
    path = Path(item.storage_path)
    if not path.exists():
        raise HTTPException(410, "O arquivo de vídeo não existe mais no armazenamento")
    return FileResponse(path, media_type="video/mp4", filename=f"{item.name}.mp4")


@app.delete("/media/{media_id}", dependencies=[Depends(require_api_key)])
def delete_media(media_id: str, db: Session = Depends(db_session)):
    item = db.get(MediaAsset, media_id)
    if not item:
        raise HTTPException(404, "Vídeo não encontrado")
    path = Path(item.storage_path)
    try:
        db.delete(item)
        db.commit()
        path.unlink(missing_ok=True)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Este vídeo está sendo usado por uma playlist ou transmissão") from exc
    return {"ok": True}


@app.get("/destinations", dependencies=[Depends(require_api_key)])
def list_destinations(db: Session = Depends(db_session)):
    return [destination_dict(x) for x in db.scalars(select(Destination).order_by(Destination.created_at.desc())).all()]


@app.post("/destinations", dependencies=[Depends(require_api_key)])
def create_destination(payload: DestinationCreate, db: Session = Depends(db_session)):
    url = _validate_rtmp_url(payload.rtmp_url)
    item = Destination(
        name=payload.name.strip(),
        platform=payload.platform.lower().strip(),
        rtmp_url=url,
        encrypted_stream_key=encrypt_secret(payload.stream_key.strip()),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return destination_dict(item)


@app.patch("/destinations/{destination_id}", dependencies=[Depends(require_api_key)])
def update_destination(destination_id: str, payload: DestinationUpdate, db: Session = Depends(db_session)):
    item = db.get(Destination, destination_id)
    if not item:
        raise HTTPException(404, "Destino não encontrado")
    values = payload.model_dump(exclude_unset=True)
    if "name" in values:
        item.name = values["name"].strip()
    if "platform" in values:
        item.platform = values["platform"].lower().strip()
    if "rtmp_url" in values:
        item.rtmp_url = _validate_rtmp_url(values["rtmp_url"])
    if "stream_key" in values and values["stream_key"] is not None:
        item.encrypted_stream_key = encrypt_secret(values["stream_key"].strip())
    if "enabled" in values:
        item.enabled = values["enabled"]
    db.commit()
    db.refresh(item)
    return destination_dict(item)


@app.post("/destinations/{destination_id}/check", dependencies=[Depends(require_api_key)])
def check_destination(destination_id: str, db: Session = Depends(db_session)):
    item = db.get(Destination, destination_id)
    if not item:
        raise HTTPException(404, "Destino não encontrado")
    parsed = urlparse(item.rtmp_url)
    host = parsed.hostname
    if not host:
        raise HTTPException(400, "Servidor RTMP inválido")
    port = parsed.port or (443 if parsed.scheme == "rtmps" else 1935)
    _resolve_public_addresses(host, port)
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=4):
            pass
    except OSError as exc:
        raise HTTPException(502, "O servidor RTMP não respondeu. Confira a URL e tente novamente") from exc
    latency = round((time.perf_counter() - started) * 1000)
    return {"ok": True, "host": host, "port": port, "latency_ms": latency, "note": "Servidor alcançável. A chave só é validada ao iniciar a transmissão."}


@app.delete("/destinations/{destination_id}", dependencies=[Depends(require_api_key)])
def delete_destination(destination_id: str, db: Session = Depends(db_session)):
    item = db.get(Destination, destination_id)
    if not item:
        raise HTTPException(404, "Destino não encontrado")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Este destino está sendo usado por uma transmissão") from exc
    return {"ok": True}


@app.get("/playlists", dependencies=[Depends(require_api_key)])
def list_playlists(db: Session = Depends(db_session)):
    query = select(Playlist).options(selectinload(Playlist.items).selectinload(PlaylistItem.media)).order_by(Playlist.created_at.desc())
    return [playlist_dict(x) for x in db.scalars(query).all()]


@app.post("/playlists", dependencies=[Depends(require_api_key)])
def create_playlist(payload: PlaylistCreate, db: Session = Depends(db_session)):
    rows = db.scalars(select(MediaAsset).where(MediaAsset.id.in_(payload.media_ids))).all()
    media = {x.id: x for x in rows}
    missing = [media_id for media_id in payload.media_ids if media_id not in media]
    if missing:
        raise HTTPException(400, "Um ou mais vídeos da playlist não existem")
    orientations = {orientation_for(media[x].width, media[x].height) for x in payload.media_ids}
    if len(orientations) > 1:
        raise HTTPException(400, "Use vídeos da mesma orientação na playlist (todos verticais ou todos horizontais)")
    if not all(is_stream_ready(media[x]) for x in payload.media_ids):
        raise HTTPException(400, "Um ou mais vídeos ainda não estão prontos para streaming")

    item = Playlist(name=payload.name.strip())
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
        raise HTTPException(404, "Playlist não encontrada")
    try:
        db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Esta playlist está sendo usada por uma transmissão") from exc
    return {"ok": True}


@app.get("/streams", dependencies=[Depends(require_api_key)])
def list_streams(db: Session = Depends(db_session)):
    return [stream_dict(x) for x in db.scalars(stream_query().order_by(StreamJob.created_at.desc())).all()]


@app.post("/streams", dependencies=[Depends(require_api_key)])
def create_stream(payload: StreamCreate, db: Session = Depends(db_session)):
    destination = db.get(Destination, payload.destination_id)
    if not destination:
        raise HTTPException(400, "Destino não encontrado")
    if not destination.enabled:
        raise HTTPException(400, "O destino está desativado")
    if payload.media_id:
        media = db.get(MediaAsset, payload.media_id)
        if not media:
            raise HTTPException(400, "Vídeo não encontrado")
        if not is_stream_ready(media):
            raise HTTPException(400, "Este vídeo não está pronto para streaming")
    if payload.playlist_id and not db.get(Playlist, payload.playlist_id):
        raise HTTPException(400, "Playlist não encontrada")

    scheduled = payload.scheduled_at
    if scheduled:
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        if scheduled <= now_utc():
            raise HTTPException(400, "O horário agendado precisa estar no futuro")

    desired = "running" if payload.start_now or scheduled else "stopped"
    status = "starting" if payload.start_now else ("scheduled" if scheduled else "stopped")
    item = StreamJob(
        name=payload.name.strip(),
        destination_id=payload.destination_id,
        media_id=payload.media_id,
        playlist_id=payload.playlist_id,
        loop=payload.loop,
        scheduled_at=scheduled,
        desired_state=desired,
        status=status,
    )
    db.add(item)
    db.commit()
    item = db.scalar(stream_query().where(StreamJob.id == item.id))
    return stream_dict(item)


@app.patch("/streams/{stream_id}", dependencies=[Depends(require_api_key)])
def update_stream(stream_id: str, payload: StreamUpdate, db: Session = Depends(db_session)):
    item = db.get(StreamJob, stream_id)
    if not item:
        raise HTTPException(404, "Transmissão não encontrada")
    if item.desired_state == "running" or item.status in {"live", "starting", "recovering"}:
        raise HTTPException(409, "Pare a transmissão antes de editar")
    values = payload.model_dump(exclude_unset=True)
    if "name" in values:
        item.name = values["name"].strip()
    if "loop" in values:
        item.loop = values["loop"]
    if "scheduled_at" in values:
        item.scheduled_at = values["scheduled_at"]
        item.desired_state = "running" if item.scheduled_at else "stopped"
        item.status = "scheduled" if item.scheduled_at else "stopped"
    db.commit()
    item = db.scalar(stream_query().where(StreamJob.id == item.id))
    return stream_dict(item)


@app.post("/streams/{stream_id}/start", dependencies=[Depends(require_api_key)])
def start_stream(stream_id: str, db: Session = Depends(db_session)):
    item = db.get(StreamJob, stream_id)
    if not item:
        raise HTTPException(404, "Transmissão não encontrada")
    item.desired_state = "running"
    item.scheduled_at = None
    if item.status != "live":
        item.status = "starting"
        item.started_at = None
        item.stopped_at = None
        item.restart_count = 0
    item.last_error = None
    db.commit()
    return {"ok": True}


@app.post("/streams/{stream_id}/stop", dependencies=[Depends(require_api_key)])
def stop_stream(stream_id: str, db: Session = Depends(db_session)):
    item = db.get(StreamJob, stream_id)
    if not item:
        raise HTTPException(404, "Transmissão não encontrada")
    item.desired_state = "stopped"
    item.status = "stopping" if item.status in {"live", "starting", "recovering"} else "stopped"
    db.commit()
    return {"ok": True}


@app.delete("/streams/{stream_id}", dependencies=[Depends(require_api_key)])
def delete_stream(stream_id: str, db: Session = Depends(db_session)):
    item = db.get(StreamJob, stream_id)
    if not item:
        raise HTTPException(404, "Transmissão não encontrada")
    if item.desired_state == "running" or item.status in {"live", "starting", "recovering"}:
        raise HTTPException(409, "Pare a transmissão antes de excluir")
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
