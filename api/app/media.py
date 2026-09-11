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
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    duration = data.get("format", {}).get("duration")
    return {
        "duration_seconds": round(float(duration), 3) if duration else None,
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": _rate(video.get("avg_frame_rate")),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
    }
