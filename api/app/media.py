import json
import subprocess
from pathlib import Path


def _rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        a, b = value.split("/", 1)
        return round(float(a) / float(b), 3) if float(b) else None
    except (ValueError, ZeroDivisionError):
        return None


def probe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,sample_rate,channels",
        "-of", "json", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    duration = data.get("format", {}).get("duration")
    width = video.get("width")
    height = video.get("height")
    orientation = "vertical" if width and height and height > width else "horizontal"
    return {
        "duration_seconds": round(float(duration), 3) if duration else None,
        "width": width,
        "height": height,
        "fps": _rate(video.get("avg_frame_rate")),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "orientation": orientation,
        "has_audio": bool(audio),
    }


def normalize_for_stream(source: Path, target: Path, metadata: dict) -> dict:
    vertical = metadata.get("orientation") == "vertical"
    width, height = (720, 1280) if vertical else (1280, 720)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        "fps=30"
    )

    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", str(source)]
    if metadata.get("has_audio"):
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-map", "0:v:0", "-map", "1:a:0", "-shortest"]

    cmd += [
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60", "-keyint_min", "60",
        "-sc_threshold", "0", "-crf", "21", "-maxrate", "4500k", "-bufsize", "9000k",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", str(target),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 45, check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "FFmpeg normalization failed")[-4000:]
        raise RuntimeError(detail) from exc
    return probe(target)
