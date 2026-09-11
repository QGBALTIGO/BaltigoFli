import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import ShopCommand, ShopNode
from .security import require_api_key


router = APIRouter(prefix="/shop", tags=["Shop Cloud"])

# Intentionally narrow. These commands operate OBS / the official LIVE Manager surface.
# There are no commands for anti-detection, fake engagement or bypassing platform policy.
ALLOWED_ACTIONS = {
    "obs_status",
    "virtual_camera_start",
    "virtual_camera_stop",
    "scene_set",
    "live_manager_open",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def node_online(node: ShopNode) -> bool:
    last_seen = aware(node.last_seen)
    return bool(last_seen and now_utc() - last_seen <= timedelta(seconds=20))


def safe_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def node_dict(node: ShopNode) -> dict:
    return {
        "id": node.id,
        "name": node.name,
        "enabled": node.enabled,
        "online": node_online(node),
        "hostname": node.hostname,
        "agent_version": node.agent_version,
        "last_seen": node.last_seen,
        "obs_connected": node.obs_connected,
        "virtual_camera_active": node.virtual_camera_active,
        "current_scene": node.current_scene,
        "capabilities": safe_json(node.capabilities_json, {}),
        "created_at": node.created_at,
        "updated_at": node.updated_at,
    }


def command_dict(command: ShopCommand) -> dict:
    return {
        "id": command.id,
        "node_id": command.node_id,
        "action": command.action,
        "payload": safe_json(command.payload_json, {}),
        "status": command.status,
        "result": safe_json(command.result_json, None),
        "error": command.error,
        "created_at": command.created_at,
        "sent_at": command.sent_at,
        "finished_at": command.finished_at,
    }


class NodeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CommandCreate(BaseModel):
    action: str = Field(min_length=2, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentHeartbeat(BaseModel):
    hostname: str | None = Field(default=None, max_length=255)
    agent_version: str | None = Field(default=None, max_length=40)
    obs_connected: bool = False
    virtual_camera_active: bool = False
    current_scene: str | None = Field(default=None, max_length=255)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=4000)


def require_node(
    authorization: str | None = Header(default=None),
    db: Session = Depends(db_session),
) -> ShopNode:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Node token ausente")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(401, "Node token ausente")
    node = db.scalar(select(ShopNode).where(ShopNode.token_hash == hash_token(token)))
    if not node or not node.enabled:
        raise HTTPException(401, "Node token inválido")
    return node


@router.post("/nodes", dependencies=[Depends(require_api_key)])
def create_node(payload: NodeCreate, db: Session = Depends(db_session)):
    token = secrets.token_urlsafe(40)
    node = ShopNode(name=payload.name.strip(), token_hash=hash_token(token))
    db.add(node)
    db.commit()
    db.refresh(node)
    # The raw token is returned exactly once. Only its SHA-256 hash is stored.
    return {"node": node_dict(node), "pairing_token": token}


@router.get("/nodes", dependencies=[Depends(require_api_key)])
def list_nodes(db: Session = Depends(db_session)):
    nodes = db.scalars(select(ShopNode).order_by(ShopNode.created_at.desc())).all()
    return [node_dict(node) for node in nodes]


@router.get("/nodes/{node_id}", dependencies=[Depends(require_api_key)])
def get_node(node_id: str, db: Session = Depends(db_session)):
    node = db.get(ShopNode, node_id)
    if not node:
        raise HTTPException(404, "Nó não encontrado")
    return node_dict(node)


@router.post("/nodes/{node_id}/rotate-token", dependencies=[Depends(require_api_key)])
def rotate_node_token(node_id: str, db: Session = Depends(db_session)):
    node = db.get(ShopNode, node_id)
    if not node:
        raise HTTPException(404, "Nó não encontrado")
    token = secrets.token_urlsafe(40)
    node.token_hash = hash_token(token)
    db.commit()
    return {"node": node_dict(node), "pairing_token": token}


@router.post("/nodes/{node_id}/commands", dependencies=[Depends(require_api_key)])
def enqueue_command(node_id: str, payload: CommandCreate, db: Session = Depends(db_session)):
    node = db.get(ShopNode, node_id)
    if not node:
        raise HTTPException(404, "Nó não encontrado")
    if payload.action not in ALLOWED_ACTIONS:
        raise HTTPException(400, "Ação não permitida para Shop Cloud")
    if payload.action == "scene_set" and not str(payload.payload.get("name", "")).strip():
        raise HTTPException(400, "scene_set exige payload.name")
    command = ShopCommand(
        node_id=node.id,
        action=payload.action,
        payload_json=json.dumps(payload.payload, ensure_ascii=False),
    )
    db.add(command)
    db.commit()
    db.refresh(command)
    return command_dict(command)


@router.get("/nodes/{node_id}/commands", dependencies=[Depends(require_api_key)])
def list_commands(node_id: str, limit: int = 50, db: Session = Depends(db_session)):
    if not db.get(ShopNode, node_id):
        raise HTTPException(404, "Nó não encontrado")
    limit = max(1, min(limit, 200))
    rows = db.scalars(
        select(ShopCommand)
        .where(ShopCommand.node_id == node_id)
        .order_by(ShopCommand.created_at.desc())
        .limit(limit)
    ).all()
    return [command_dict(row) for row in rows]


@router.post("/agent/heartbeat")
def agent_heartbeat(
    payload: AgentHeartbeat,
    node: ShopNode = Depends(require_node),
    db: Session = Depends(db_session),
):
    # require_node and this endpoint share the same request-scoped db dependency.
    managed = db.get(ShopNode, node.id)
    if not managed or not managed.enabled:
        raise HTTPException(401, "Nó desativado")
    managed.hostname = payload.hostname
    managed.agent_version = payload.agent_version
    managed.obs_connected = payload.obs_connected
    managed.virtual_camera_active = payload.virtual_camera_active
    managed.current_scene = payload.current_scene
    managed.capabilities_json = json.dumps(payload.capabilities, ensure_ascii=False)
    managed.last_seen = now_utc()

    retry_before = now_utc() - timedelta(seconds=30)
    commands = db.scalars(
        select(ShopCommand)
        .where(
            ShopCommand.node_id == managed.id,
            or_(
                ShopCommand.status == "queued",
                and_(ShopCommand.status == "sent", ShopCommand.sent_at < retry_before),
            ),
        )
        .order_by(ShopCommand.created_at.asc())
        .limit(10)
    ).all()
    now = now_utc()
    for command in commands:
        command.status = "sent"
        command.sent_at = now
    db.commit()
    return {
        "ok": True,
        "node_id": managed.id,
        "commands": [command_dict(command) for command in commands],
        "poll_after_seconds": 3,
    }


@router.post("/agent/commands/{command_id}/result")
def agent_command_result(
    command_id: str,
    payload: CommandResult,
    node: ShopNode = Depends(require_node),
    db: Session = Depends(db_session),
):
    command = db.get(ShopCommand, command_id)
    if not command or command.node_id != node.id:
        raise HTTPException(404, "Comando não encontrado")
    command.status = "completed" if payload.ok else "failed"
    command.result_json = json.dumps(payload.result, ensure_ascii=False) if payload.result is not None else None
    command.error = payload.error[-4000:] if payload.error else None
    command.finished_at = now_utc()
    db.commit()
    return {"ok": True}
