"""Baltigo Shop Cloud Windows agent.

This agent controls a paired OBS instance and opens the official TikTok Shop LIVE
Manager in a persistent desktop session. It deliberately does not automate TikTok
login, click the Go LIVE button, fabricate engagement, or implement anti-detection.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import webbrowser
from collections import OrderedDict
from pathlib import Path
from typing import Any

import obsws_python as obs
import requests
from dotenv import load_dotenv


VERSION = "0.1.0"
ALLOWED_ACTIONS = {
    "obs_status",
    "virtual_camera_start",
    "virtual_camera_stop",
    "scene_set",
    "live_manager_open",
}

load_dotenv(Path(__file__).with_name(".env"))

CONTROL_URL = os.getenv("BALTIGO_CONTROL_URL", "").rstrip("/")
NODE_TOKEN = os.getenv("BALTIGO_NODE_TOKEN", "").strip()
POLL_SECONDS = max(1.0, float(os.getenv("POLL_SECONDS", "3")))
OBS_HOST = os.getenv("OBS_WS_HOST", "127.0.0.1")
OBS_PORT = int(os.getenv("OBS_WS_PORT", "4455"))
OBS_PASSWORD = os.getenv("OBS_WS_PASSWORD", "")
LIVE_MANAGER_URL = os.getenv("LIVE_MANAGER_URL", "https://seller-br.tiktok.com/")
BROWSER_PATH = os.getenv("BROWSER_PATH", "").strip()
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "").strip()

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {NODE_TOKEN}", "User-Agent": f"BaltigoShopAgent/{VERSION}"})

# Prevent a retried command from being executed twice when only the result POST failed.
recent_results: OrderedDict[str, tuple[bool, dict[str, Any] | None, str | None]] = OrderedDict()


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def validate_config() -> None:
    missing = []
    if not CONTROL_URL:
        missing.append("BALTIGO_CONTROL_URL")
    if not NODE_TOKEN:
        missing.append("BALTIGO_NODE_TOKEN")
    if missing:
        raise SystemExit("Missing configuration: " + ", ".join(missing))


def obs_client() -> obs.ReqClient:
    return obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=3)


def obs_status() -> dict[str, Any]:
    try:
        client = obs_client()
        try:
            version = client.send("GetVersion", raw=True) or {}
            virtual = client.send("GetVirtualCamStatus", raw=True) or {}
            scene = client.send("GetCurrentProgramScene", raw=True) or {}
            return {
                "connected": True,
                "obs_version": version.get("obsVersion"),
                "websocket_version": version.get("obsWebSocketVersion"),
                "virtual_camera_active": bool(virtual.get("outputActive")),
                "current_scene": scene.get("currentProgramSceneName"),
            }
        finally:
            client.disconnect()
    except Exception:
        return {
            "connected": False,
            "obs_version": None,
            "websocket_version": None,
            "virtual_camera_active": False,
            "current_scene": None,
        }


def find_browser() -> str | None:
    if BROWSER_PATH and Path(BROWSER_PATH).exists():
        return BROWSER_PATH

    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    for name in ("chrome.exe", "msedge.exe", "chrome", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def open_live_manager(payload: dict[str, Any]) -> dict[str, Any]:
    url = str(payload.get("url") or LIVE_MANAGER_URL).strip()
    if not url.lower().startswith("https://"):
        raise RuntimeError("LIVE Manager URL must use HTTPS")

    browser = find_browser()
    if not browser:
        webbrowser.open(url, new=1)
        return {"opened": True, "url": url, "browser": "system-default"}

    args = [browser, "--new-window"]
    if BROWSER_PROFILE_DIR:
        Path(BROWSER_PROFILE_DIR).mkdir(parents=True, exist_ok=True)
        args.append(f"--user-data-dir={BROWSER_PROFILE_DIR}")
    args.append(url)
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"opened": True, "url": url, "browser": Path(browser).name}


def execute_command(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise RuntimeError("Command is not allowed by this agent")

    if action == "obs_status":
        return obs_status()

    if action == "live_manager_open":
        return open_live_manager(payload)

    client = obs_client()
    try:
        if action == "virtual_camera_start":
            client.send("StartVirtualCam")
            return {"virtual_camera_active": True}
        if action == "virtual_camera_stop":
            client.send("StopVirtualCam")
            return {"virtual_camera_active": False}
        if action == "scene_set":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise RuntimeError("scene_set requires payload.name")
            client.send("SetCurrentProgramScene", {"sceneName": name})
            return {"current_scene": name}
    finally:
        client.disconnect()

    raise RuntimeError("Unknown command")


def heartbeat_payload() -> dict[str, Any]:
    status = obs_status()
    return {
        "hostname": platform.node(),
        "agent_version": VERSION,
        "obs_connected": status["connected"],
        "virtual_camera_active": status["virtual_camera_active"],
        "current_scene": status["current_scene"],
        "capabilities": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "obs_version": status.get("obs_version"),
            "obs_websocket_version": status.get("websocket_version"),
            "browser_found": bool(find_browser()),
            "actions": sorted(ALLOWED_ACTIONS),
        },
    }


def report_result(command_id: str, ok: bool, result: dict[str, Any] | None, error: str | None) -> None:
    response = session.post(
        f"{CONTROL_URL}/shop/agent/commands/{command_id}/result",
        json={"ok": ok, "result": result, "error": error},
        timeout=15,
    )
    response.raise_for_status()


def remember_result(command_id: str, value: tuple[bool, dict[str, Any] | None, str | None]) -> None:
    recent_results[command_id] = value
    recent_results.move_to_end(command_id)
    while len(recent_results) > 200:
        recent_results.popitem(last=False)


def handle_command(command: dict[str, Any]) -> None:
    command_id = str(command.get("id") or "")
    action = str(command.get("action") or "")
    payload = command.get("payload") or {}
    if not command_id:
        return

    if command_id in recent_results:
        ok, result, error = recent_results[command_id]
        report_result(command_id, ok, result, error)
        return

    try:
        log(f"Executing allowed command: {action}")
        result = execute_command(action, payload)
        value = (True, result, None)
    except Exception as exc:
        value = (False, None, str(exc)[-4000:])
        log(f"Command {action} failed: {exc}")

    remember_result(command_id, value)
    report_result(command_id, *value)


def poll_once() -> float:
    response = session.post(
        f"{CONTROL_URL}/shop/agent/heartbeat",
        json=heartbeat_payload(),
        timeout=15,
    )
    if response.status_code == 401:
        raise RuntimeError("Node token rejected. Pair or rotate the Shop Cloud node token.")
    response.raise_for_status()
    body = response.json()
    for command in body.get("commands", []):
        try:
            handle_command(command)
        except Exception as exc:
            log(f"Could not report command result: {exc}")
    return max(1.0, float(body.get("poll_after_seconds", POLL_SECONDS)))


def main() -> int:
    validate_config()
    log(f"Baltigo Shop Cloud agent {VERSION} starting on {platform.node()}")
    delay = POLL_SECONDS
    while True:
        try:
            delay = poll_once()
        except KeyboardInterrupt:
            log("Agent stopped by user")
            return 0
        except Exception as exc:
            log(f"Control plane error: {exc}")
            if os.getenv("BALTIGO_AGENT_DEBUG") == "1":
                traceback.print_exc()
            delay = min(max(delay * 1.5, 3), 30)
        time.sleep(delay)


if __name__ == "__main__":
    sys.exit(main())
