import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import settings
from .database import SessionLocal, init_db
from .models import Playlist, PlaylistItem, StreamJob
from .security import decrypt_secret
from .streaming import build_ffmpeg_command, output_url, redacted_command, write_concat_file


@dataclass
class RunningProcess:
    process: subprocess.Popen
    log_handle: object
    started_monotonic: float


processes: dict[str, RunningProcess] = {}
shutdown = False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stream_query():
    return select(StreamJob).options(
        selectinload(StreamJob.destination),
        selectinload(StreamJob.media),
        selectinload(StreamJob.playlist).selectinload(Playlist.items).selectinload(PlaylistItem.media),
    )


def due(job: StreamJob) -> bool:
    if job.desired_state != "running":
        return False
    if not job.scheduled_at:
        return True
    value = job.scheduled_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= now_utc()


def source_for(job: StreamJob) -> tuple[Path, bool]:
    if job.media:
        return Path(job.media.storage_path), False
    if not job.playlist or not job.playlist.items:
        raise RuntimeError("Playlist is empty")
    paths = [Path(item.media.storage_path) for item in sorted(job.playlist.items, key=lambda x: x.position)]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing media files: {', '.join(missing)}")
    return write_concat_file(job.id, paths, settings.log_dir), True


def start_job(job: StreamJob) -> None:
    if job.id in processes:
        return
    source, concat = source_for(job)
    if not source.exists():
        raise RuntimeError(f"Source does not exist: {source}")
    if not job.destination.enabled:
        raise RuntimeError("Destination is disabled")

    key = decrypt_secret(job.destination.encrypted_stream_key)
    url = output_url(job.destination.rtmp_url, key)
    command = build_ffmpeg_command(source, url, job.loop, concat=concat)
    log_path = settings.log_dir / f"{job.id}.log"
    log_handle = log_path.open("a", encoding="utf-8")
    log_handle.write(f"\n[{now_utc().isoformat()}] starting: {redacted_command(command)}\n")
    log_handle.flush()
    process = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True)
    processes[job.id] = RunningProcess(process, log_handle, time.monotonic())


def stop_job(stream_id: str) -> None:
    running = processes.pop(stream_id, None)
    if not running:
        return
    try:
        running.process.terminate()
        running.process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        running.process.kill()
        running.process.wait(timeout=3)
    finally:
        running.log_handle.close()


def mark_failure(job: StreamJob, message: str) -> None:
    job.status = "recovering"
    job.last_error = message[-2000:]
    job.restart_count += 1
    job.worker_id = settings.worker_id
    job.heartbeat_at = now_utc()


def reconcile() -> None:
    with SessionLocal() as db:
        jobs = db.scalars(stream_query()).all()
        current_ids = {job.id for job in jobs}

        for orphan in set(processes) - current_ids:
            stop_job(orphan)

        for job in jobs:
            running = processes.get(job.id)

            if job.desired_state != "running":
                if running:
                    stop_job(job.id)
                if job.status != "stopped":
                    job.status = "stopped"
                    job.stopped_at = now_utc()
                    job.worker_id = settings.worker_id
                    job.heartbeat_at = now_utc()
                continue

            if not due(job):
                job.status = "scheduled"
                continue

            if running and running.process.poll() is None:
                job.status = "live"
                job.worker_id = settings.worker_id
                job.heartbeat_at = now_utc()
                if not job.started_at:
                    job.started_at = now_utc()
                job.last_error = None
                continue

            if running:
                exit_code = running.process.returncode
                running.log_handle.close()
                processes.pop(job.id, None)
                mark_failure(job, f"FFmpeg exited with code {exit_code}")

            delay = min(settings.restart_max_seconds, settings.restart_base_seconds * (2 ** min(job.restart_count, 5)))
            if job.heartbeat_at:
                heartbeat = job.heartbeat_at
                if heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=timezone.utc)
                elapsed = (now_utc() - heartbeat).total_seconds()
                if job.status == "recovering" and elapsed < delay:
                    continue

            try:
                job.status = "starting"
                job.worker_id = settings.worker_id
                job.heartbeat_at = now_utc()
                db.commit()
                start_job(job)
                job.status = "live"
                job.started_at = job.started_at or now_utc()
                job.heartbeat_at = now_utc()
                job.last_error = None
            except Exception as exc:
                mark_failure(job, str(exc))

        db.commit()


def handle_signal(*_):
    global shutdown
    shutdown = True


def main() -> None:
    init_db()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    print(f"Baltigo Live worker started as {settings.worker_id}", flush=True)
    while not shutdown:
        try:
            reconcile()
        except Exception as exc:
            print(f"worker reconcile error: {exc}", flush=True)
        time.sleep(settings.worker_poll_seconds)
    for stream_id in list(processes):
        stop_job(stream_id)
    print("Baltigo Live worker stopped", flush=True)


if __name__ == "__main__":
    main()
