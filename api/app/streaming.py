import shlex
from pathlib import Path

from .config import settings


def output_url(rtmp_url: str, stream_key: str) -> str:
    if "{stream_key}" in rtmp_url:
        return rtmp_url.replace("{stream_key}", stream_key)
    return f"{rtmp_url.rstrip('/')}/{stream_key.lstrip('/')}"


def build_ffmpeg_command(input_path: Path, destination_url: str, loop: bool, concat: bool = False) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-re"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    if concat:
        cmd += ["-f", "concat", "-safe", "0", "-i", str(input_path)]
    else:
        cmd += ["-i", str(input_path)]

    if settings.stream_transcode:
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-r", str(settings.output_fps), "-b:v", settings.video_bitrate,
            "-maxrate", settings.video_bitrate, "-bufsize", "9000k",
            "-c:a", "aac", "-b:a", settings.audio_bitrate, "-ar", "44100",
        ]
    else:
        cmd += ["-c", "copy"]

    cmd += ["-f", "flv", destination_url]
    return cmd


def redacted_command(command: list[str]) -> str:
    safe = command[:-1] + ["<RTMP_REDACTED>"]
    return " ".join(shlex.quote(item) for item in safe)


def write_concat_file(stream_id: str, media_paths: list[Path], loop_dir: Path) -> Path:
    target = loop_dir / f"{stream_id}.concat.txt"
    lines = []
    for path in media_paths:
        escaped = str(path).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
