# Baltigo Shop Live Cloud

## Objective

Keep a TikTok Shop LIVE operating from cloud infrastructure without requiring the seller's local computer to remain on, while using the official TikTok Shop LIVE Manager/desktop surface and avoiding password/cookie harvesting or moderation-evasion features.

This is a different execution mode from the existing RTMP worker. RTMP remains useful for platforms/accounts that expose a Stream URL and Stream Key, but TikTok Shop Brazil also documents a desktop flow using **OBS Virtual Camera** in LIVE Manager without requiring a Stream Key.

## What public evidence says about Hero

Public Hero material describes the product as an automation tool for TikTok Shop LIVE and says it processes:

- uploaded media used as "Lives Gravadas";
- API tokens;
- temporary connection credentials;
- product-catalog data;
- data needed to configure and transmit a Shop LIVE on the user's behalf.

Source: `https://herostream.site/politicas-de-privacidade.html`

The same public page uses the support address `trendlysuporteapp@gmail.com`, which also appears in public Trendly material. An older Hero address was hosted on Vercel. These facts establish a public web/control layer and an operational relationship, but **do not prove the private transmission mechanism**.

### What we cannot establish from public evidence

We found public TikTok Shop APIs for OAuth/data access and LIVE analytics, including Shop LIVE Performance APIs, but did not find a public documented endpoint whose purpose is "create a LIVE and return a stream key" or "start the seller's LIVE".

Relevant public docs:

- `https://partner.tiktokshop.com/docv2/page/sv0xa2r6` — LIVE analytics APIs
- `https://partner.tiktokshop.com/docv2/page/get-shop-live-performance-list-202509` — LIVE performance list
- `https://seller-br.tiktok.com/university/essay?default_language=pt-BR&knowledge_id=6821109446412048` — Brazil LIVE Manager and OBS Virtual Camera

Therefore, Hero's exact private implementation cannot be inferred as a public Open API integration. Plausible classes of implementation include a remote browser/desktop session, private/non-public integration, or a combination. We do not claim which one Hero uses.

## Chosen Baltigo architecture

```text
Baltigo control plane (Railway)
          |
          | outbound HTTPS polling
          v
Windows Shop Node (persistent desktop)
  - Chrome/Edge, user logs in directly
  - TikTok Shop LIVE Manager
  - OBS Studio + obs-websocket
  - OBS Virtual Camera
  - optional virtual audio device
```

The Windows node initiates all communication outbound to Railway. No inbound agent port needs to be exposed to the public internet.

### Control plane

New API namespace: `/api/shop`.

- `POST /api/shop/nodes` — create/pair a Windows node; returns a one-time token.
- `GET /api/shop/nodes` — node status.
- `POST /api/shop/nodes/{id}/rotate-token` — rotate a compromised/lost node token.
- `POST /api/shop/nodes/{id}/commands` — queue an allow-listed command.
- `GET /api/shop/nodes/{id}/commands` — inspect command history.
- `POST /api/shop/agent/heartbeat` — node heartbeat and command poll.
- `POST /api/shop/agent/commands/{id}/result` — result acknowledgement.

Node tokens are not stored in plaintext; only SHA-256 hashes are stored in the control-plane database.

### Allow-listed commands

The first agent only supports:

- `obs_status`
- `virtual_camera_start`
- `virtual_camera_stop`
- `scene_set`
- `live_manager_open`

There is intentionally no generic shell command endpoint, no browser-cookie export, no fake engagement command and no anti-detection command.

## Why OBS Virtual Camera

OBS officially describes Virtual Camera as a way to expose the OBS scene output as a webcam to applications that accept cameras. TikTok Shop Brazil documents selecting OBS Virtual Camera as a source inside LIVE Manager.

OBS source: `https://obsproject.com/kb/virtual-camera-guide`

TikTok Shop Brazil source: `https://seller-br.tiktok.com/university/essay?default_language=pt-BR&knowledge_id=6821109446412048`

## Important policy boundary

Moving the desktop to the cloud changes **where the software runs**, not what TikTok considers compliant content. This architecture must not be represented as an anti-ban mechanism, and it does not make prerecorded-loop content compliant if TikTok Shop policy requires real-time/interactive content.

The control plane therefore focuses on availability, remote operation, OBS state and official LIVE Manager access—not on defeating platform detection.

## Production requirements for a Windows node

A production Shop node needs:

1. persistent Windows disk;
2. a persistent interactive desktop session;
3. OBS Studio configured with WebSocket authentication;
4. OBS Virtual Camera;
5. Chrome or Edge with a dedicated persistent profile directory;
6. a reliable display/GPU path even when the operator disconnects remotely;
7. optional virtual audio device where required by the LIVE Manager source setup;
8. the Baltigo Windows agent scheduled at user logon.

Plain RDP must be tested carefully because disconnecting an RDP session can change display/audio availability on some Windows cloud hosts. A persistent display/GPU configuration is preferable.

## Implementation phases

### Phase A — implemented now

- Shop node database model;
- secure one-time pairing token;
- heartbeat/online status;
- command queue with retry and result acknowledgement;
- Windows agent;
- OBS WebSocket status;
- start/stop Virtual Camera;
- switch OBS scene;
- open official LIVE Manager;
- logged-in browser session remains owned by the user's Windows profile.

### Phase B — next validation

- provision one Windows cloud VM;
- install OBS/Chrome/agent;
- user logs into TikTok directly;
- select OBS Virtual Camera in LIVE Manager;
- validate with TikTok's Practice Mode where available;
- test display/audio persistence after remote disconnect/reboot;
- expose Shop-node status in the simple Baltigo web UI.

### Phase C — official Shop integrations

- register a TikTok Shop Partner app;
- OAuth for seller-authorized data access;
- product/catalog data where scopes allow;
- LIVE analytics and product performance in the Baltigo panel;
- alerts/health checks around the remote desktop node.
