# Baltigo Shop Cloud — Windows Node

A Windows node keeps an **official TikTok Shop LIVE Manager desktop session** available in the cloud while the user's local PC can be offline. The node is controlled from the Baltigo control plane through an outbound HTTPS agent.

## What this node does

- reports whether OBS is connected;
- reports whether OBS Virtual Camera is active;
- can start/stop OBS Virtual Camera;
- can switch to a named OBS scene;
- can open the official TikTok Shop LIVE Manager in a persistent browser profile;
- receives commands only from the paired Baltigo control plane.

## What it deliberately does not do

- it does not collect TikTok passwords or copy browser cookies;
- it does not automate TikTok login;
- it does not click the TikTok "Go LIVE" button;
- it does not fabricate comments, viewers or interaction;
- it does not include anti-ban, anti-detection, replay obfuscation or moderation bypasses;
- it does not turn prerecorded-loop content into compliant TikTok Shop content.

## Requirements

- Windows 10/11 or Windows Server with Desktop Experience;
- an interactive desktop session that stays alive;
- OBS Studio with obs-websocket enabled (OBS 28+ includes it);
- OBS Virtual Camera installed;
- Chrome or Microsoft Edge;
- Python 3.11+;
- for audio in LIVE Manager, a separately configured virtual audio device may be required.

## Pairing

1. In the Baltigo control plane create a Shop Cloud node with `POST /api/shop/nodes` using the admin API key.
2. The response contains a `pairing_token` exactly once. Copy it to this machine; the server stores only a SHA-256 hash.
3. Copy `.env.example` to `.env` and place the token in `BALTIGO_NODE_TOKEN`.
4. Configure the OBS WebSocket password in both OBS and `.env`.

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe agent.py
```

When the node shows online in the control plane, install autostart in the logged-in desktop session:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-task.ps1
```

The agent is intentionally scheduled **at user logon**, not as a Windows service, because OBS, Virtual Camera and the browser need an interactive desktop.

## OBS preparation

1. Open OBS Studio.
2. Tools/Settings → WebSocket Server Settings → enable the server and set a password.
3. Create the scenes you want to expose through OBS Virtual Camera.
4. Use the Baltigo command `virtual_camera_start` to start the output.
5. In TikTok Shop LIVE Manager choose **OBS Virtual Camera** as the video source.

The user signs into TikTok directly in the remote browser. Keep `BROWSER_PROFILE_DIR` on the persistent Windows disk so that the browser's own signed-in session persists normally.

## Headless/cloud Windows caveat

A cloud machine still needs a stable graphical desktop. Plain RDP can change/remove display and audio devices when a session disconnects on some hosts. For a production node, use a VM/provider configuration with a persistent GPU/display, or a tested persistent virtual-display setup. Do not install an unknown display driver automatically on production nodes.
