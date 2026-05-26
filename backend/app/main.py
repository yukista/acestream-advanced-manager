from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator
from urllib.parse import urlparse

import httpx
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base

# ── Config ───────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL", "mysql+pymysql://acestream:acestream@localhost/acestream"
)
_checker_urls_env = os.getenv(
    "HEALTH_CHECKER_URLS",
    os.getenv("HEALTH_CHECKER_URL", "http://localhost:8000"),
)
HEALTH_CHECKER_URLS = [u.strip().rstrip("/") for u in _checker_urls_env.split(",") if u.strip()]
if not HEALTH_CHECKER_URLS:
    HEALTH_CHECKER_URLS = ["http://localhost:8000"]
ENGINE_BASE_URL = os.getenv("ACESTREAM_ENGINE_URL", "http://127.0.0.1:6878").rstrip("/")
SEGMENTS_DIR = Path(os.getenv("SEGMENTS_DIR", "/segments"))
HEALTH_CHECK_INTERVAL_DEFAULT = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))
HEALTH_PROBE_TIMEOUT_SECONDS_DEFAULT = int(os.getenv("HEALTH_PROBE_TIMEOUT_SECONDS", "35"))
HEALTH_CHANNEL_GAP_SECONDS_DEFAULT = int(os.getenv("HEALTH_CHANNEL_GAP_SECONDS", "2"))
CHECKS_ENABLED_DEFAULT = os.getenv("CHECKS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
CHECKER_INSTANCES_DEFAULT = int(os.getenv("CHECKER_INSTANCES", "1"))
MAX_SEGMENTS_DEFAULT = int(os.getenv("MAX_SEGMENTS", "30"))
HLS_SEGMENT_TIME_DEFAULT = int(os.getenv("HLS_SEGMENT_TIME", "6"))
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Database ─────────────────────────────────────────────────────────────────
Base = declarative_base()


class ChannelModel(Base):
    __tablename__ = "channels"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    title = sa.Column(sa.String(255), nullable=False)
    hash = sa.Column(sa.String(40), nullable=False, unique=True)
    enabled = sa.Column(sa.Boolean, nullable=False, default=True)
    status = sa.Column(sa.String(20), default="unknown")  # unknown | ok | error
    last_checked = sa.Column(sa.BigInteger, nullable=True)
    connect_time_ms = sa.Column(sa.Integer, nullable=True)
    resolution = sa.Column(sa.String(20), nullable=True)
    clip_id = sa.Column(sa.String(64), nullable=True)
    clip_url = sa.Column(sa.String(1024), nullable=True)
    error_message = sa.Column(sa.Text, nullable=True)
    created_at = sa.Column(sa.BigInteger, default=lambda: int(time.time()))
    updated_at = sa.Column(sa.BigInteger, default=lambda: int(time.time()))


class AppSettingModel(Base):
    __tablename__ = "app_settings"

    key = sa.Column(sa.String(100), primary_key=True)
    value = sa.Column(sa.String(255), nullable=False)
    updated_at = sa.Column(sa.BigInteger, nullable=False, default=lambda: int(time.time()))


db_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

# ── Active stream state ───────────────────────────────────────────────────────
@dataclass
class ActiveStream:
    channel_id: int
    content_hash: str
    player_id: str
    command_url: str | None = None
    ffmpeg_process: asyncio.subprocess.Process | None = None
    started_at: float = field(default_factory=time.time)


active_stream: ActiveStream | None = None
active_stream_lock = asyncio.Lock()
checker_rr_index = 0
checker_rr_lock = asyncio.Lock()

# ── SSE broadcasting ──────────────────────────────────────────────────────────
_sse_queues: list[asyncio.Queue[str]] = []

SETTING_SCHEMA: dict[str, dict[str, Any]] = {
    "checks_enabled": {"type": "bool", "default": CHECKS_ENABLED_DEFAULT},
    "checker_instances": {
        "type": "int",
        "default": max(1, min(CHECKER_INSTANCES_DEFAULT, len(HEALTH_CHECKER_URLS))),
        "min": 1,
        "max": max(1, len(HEALTH_CHECKER_URLS)),
    },
    "health_check_interval": {"type": "int", "default": HEALTH_CHECK_INTERVAL_DEFAULT, "min": 10, "max": 3600},
    "health_probe_timeout_seconds": {"type": "int", "default": HEALTH_PROBE_TIMEOUT_SECONDS_DEFAULT, "min": 5, "max": 300},
    "health_channel_gap_seconds": {"type": "int", "default": HEALTH_CHANNEL_GAP_SECONDS_DEFAULT, "min": 0, "max": 60},
    "max_segments": {"type": "int", "default": MAX_SEGMENTS_DEFAULT, "min": 5, "max": 300},
    "hls_segment_time": {"type": "int", "default": HLS_SEGMENT_TIME_DEFAULT, "min": 1, "max": 20},
}

runtime_settings: dict[str, Any] = {
    key: meta["default"] for key, meta in SETTING_SCHEMA.items()
}

health_check_status: dict[str, Any] = {
    "running": False,
    "cycle_id": 0,
    "checks_enabled": CHECKS_ENABLED_DEFAULT,
    "interval_seconds": HEALTH_CHECK_INTERVAL_DEFAULT,
    "active_checker_instances": 1,
    "available_checker_instances": len(HEALTH_CHECKER_URLS),
    "last_cycle_started": None,
    "last_cycle_finished": None,
    "current_channel_id": None,
    "current_channel_title": None,
    "current_checker_url": None,
    "current_checker_name": None,
    "checker_workers": {},
    "checked_in_cycle": 0,
    "total_channels_in_cycle": 0,
    "last_result": None,
    "recent_results": [],
}


def _setting_to_db_value(key: str, value: Any) -> str:
    if SETTING_SCHEMA[key]["type"] == "bool":
        return "1" if bool(value) else "0"
    return str(int(value))


def _setting_from_db_value(key: str, value: str) -> Any:
    t = SETTING_SCHEMA[key]["type"]
    if t == "bool":
        return value.lower() in {"1", "true", "yes", "on"}
    return int(value)


def _coerce_setting_value(key: str, value: Any) -> Any:
    meta = SETTING_SCHEMA[key]
    t = meta["type"]
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        raise HTTPException(400, f"Invalid value for {key}")

    try:
        iv = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"Invalid numeric value for {key}") from exc

    if "min" in meta and iv < meta["min"]:
        raise HTTPException(400, f"{key} must be >= {meta['min']}")
    if "max" in meta and iv > meta["max"]:
        raise HTTPException(400, f"{key} must be <= {meta['max']}")
    return iv


def _settings_snapshot() -> dict[str, Any]:
    return {
        "values": copy.deepcopy(runtime_settings),
        "schema": copy.deepcopy(SETTING_SCHEMA),
    }


def _checker_name_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.hostname or url
    except Exception:
        return url


def _active_checker_urls() -> list[str]:
    configured = int(runtime_settings.get("checker_instances", 1))
    count = max(1, min(configured, len(HEALTH_CHECKER_URLS)))
    return HEALTH_CHECKER_URLS[:count]


async def _pick_checker_url(urls: list[str] | None = None) -> str:
    global checker_rr_index
    active_urls = urls or _active_checker_urls()
    async with checker_rr_lock:
        url = active_urls[checker_rr_index % len(active_urls)]
        checker_rr_index = (checker_rr_index + 1) % max(1, len(active_urls))
        return url


def _refresh_health_status_from_settings(active_urls: list[str] | None = None) -> None:
    health_check_status["checks_enabled"] = bool(runtime_settings.get("checks_enabled", CHECKS_ENABLED_DEFAULT))
    health_check_status["interval_seconds"] = int(runtime_settings.get("health_check_interval", HEALTH_CHECK_INTERVAL_DEFAULT))
    urls = active_urls or _active_checker_urls()
    health_check_status["active_checker_instances"] = len(urls)
    health_check_status["available_checker_instances"] = len(HEALTH_CHECKER_URLS)


def _refresh_checker_workers_status(active_urls: list[str] | None = None) -> None:
    active_set = set(active_urls or _active_checker_urls())
    workers: dict[str, Any] = {}
    for url in HEALTH_CHECKER_URLS:
        previous = health_check_status.get("checker_workers", {}).get(url, {})
        workers[url] = {
            "checker_url": url,
            "checker_name": _checker_name_from_url(url),
            "enabled": url in active_set,
            "busy": bool(previous.get("busy", False)) if url in active_set else False,
            "current_channel_id": previous.get("current_channel_id") if url in active_set else None,
            "current_channel_title": previous.get("current_channel_title") if url in active_set else None,
            "last_started": previous.get("last_started"),
            "last_finished": previous.get("last_finished"),
            "busy_since": previous.get("busy_since"),
            "last_result": previous.get("last_result"),
        }
    health_check_status["checker_workers"] = workers


def _load_runtime_settings_from_db() -> None:
    with Session(db_engine) as session:
        for key, meta in SETTING_SCHEMA.items():
            row = session.get(AppSettingModel, key)
            if row is None:
                row = AppSettingModel(
                    key=key,
                    value=_setting_to_db_value(key, meta["default"]),
                    updated_at=_now_ts(),
                )
                session.add(row)
                runtime_settings[key] = meta["default"]
            else:
                try:
                    runtime_settings[key] = _coerce_setting_value(
                        key, _setting_from_db_value(key, row.value)
                    )
                except HTTPException:
                    runtime_settings[key] = meta["default"]
                    row.value = _setting_to_db_value(key, meta["default"])
                    row.updated_at = _now_ts()
        session.commit()


def _status_snapshot() -> dict[str, Any]:
    return copy.deepcopy(health_check_status)


async def _broadcast_health_status() -> None:
    await broadcast("health_check_status", _status_snapshot())


def _now_ts() -> int:
    return int(time.time())


def _run_schema_migrations() -> None:
    # Existing DBs were created with FLOAT timestamps, causing severe precision loss
    # (all channels appeared checked at exactly the same second).
    statements = [
        "ALTER TABLE channels ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1",
        "ALTER TABLE channels MODIFY COLUMN last_checked BIGINT NULL",
        "ALTER TABLE channels MODIFY COLUMN created_at BIGINT NULL",
        "ALTER TABLE channels MODIFY COLUMN updated_at BIGINT NULL",
        "ALTER TABLE channels ADD COLUMN clip_url VARCHAR(1024) NULL",
        "UPDATE channels SET enabled = 1 WHERE enabled IS NULL",
    ]
    with db_engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                # Best-effort migration for first run / non-MySQL variants.
                pass


async def broadcast(event: str, data: Any) -> None:
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    for q in _sse_queues:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass


# ── Ace Stream helpers ────────────────────────────────────────────────────────
async def ace_open_session(content_hash: str, player_id: str) -> tuple[str, str | None]:
    params = {
        "id": content_hash,
        "format": "json",
        "use_api_events": "1",
        "pid": player_id,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{ENGINE_BASE_URL}/ace/manifest.m3u8", params=params)
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    r = payload.get("response", {})
    playback_url = r.get("playback_url")
    command_url = r.get("command_url")
    if not playback_url:
        raise RuntimeError("Engine returned no playback_url")
    return playback_url, command_url


async def ace_stop_session(command_url: str | None) -> None:
    if not command_url:
        return
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.get(command_url, params={"method": "stop"})
    except Exception:
        pass


# ── HLS segmentation ──────────────────────────────────────────────────────────
def _clear_segments() -> None:
    for f in SEGMENTS_DIR.glob("stream*"):
        try:
            f.unlink()
        except OSError:
            pass


async def _start_ffmpeg(playback_url: str) -> asyncio.subprocess.Process:
    _clear_segments()
    hls_segment_time = int(runtime_settings.get("hls_segment_time", HLS_SEGMENT_TIME_DEFAULT))
    max_segments = int(runtime_settings.get("max_segments", MAX_SEGMENTS_DEFAULT))
    cmd = [
        FFMPEG_BIN,
        "-hide_banner", "-loglevel", "warning",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "3",
        "-i", playback_url,
        "-c", "copy",
        "-f", "hls",
        "-hls_time", str(hls_segment_time),
        "-hls_list_size", str(max_segments),
        "-hls_flags", "delete_segments+append_list+independent_segments",
        "-hls_segment_filename", str(SEGMENTS_DIR / "stream%05d.ts"),
        str(SEGMENTS_DIR / "stream.m3u8"),
    ]
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )


# ── Switch stream ─────────────────────────────────────────────────────────────
async def switch_stream(channel_id: int, content_hash: str) -> None:
    global active_stream
    async with active_stream_lock:
        # Tear down previous stream
        if active_stream:
            if active_stream.ffmpeg_process:
                try:
                    active_stream.ffmpeg_process.terminate()
                    await asyncio.wait_for(active_stream.ffmpeg_process.wait(), timeout=5)
                except Exception:
                    try:
                        active_stream.ffmpeg_process.kill()
                    except Exception:
                        pass
            await ace_stop_session(active_stream.command_url)
            _clear_segments()
            active_stream = None

        # Open new session
        player_id = uuid.uuid4().hex
        playback_url, command_url = await ace_open_session(content_hash, player_id)
        proc = await _start_ffmpeg(playback_url)
        active_stream = ActiveStream(
            channel_id=channel_id,
            content_hash=content_hash,
            player_id=player_id,
            command_url=command_url,
            ffmpeg_process=proc,
        )

    await broadcast("stream_changed", {"channel_id": channel_id})


# ── Health check helpers ──────────────────────────────────────────────────────
async def _probe_channel(channel_id: int, content_hash: str, checker_url: str | None = None) -> dict[str, Any]:
    checked_at = _now_ts()
    probe_timeout = int(runtime_settings.get("health_probe_timeout_seconds", HEALTH_PROBE_TIMEOUT_SECONDS_DEFAULT))
    selected_checker_url = checker_url or await _pick_checker_url()
    try:
        async with httpx.AsyncClient(timeout=probe_timeout) as client:
            resp = await client.post(
                f"{selected_checker_url}/probe",
                json={
                    "hash": content_hash,
                    "timeout_seconds": probe_timeout,
                },
            )
        with Session(db_engine) as session:
            ch = session.get(ChannelModel, channel_id)
            if ch is None:
                return {
                    "channel_id": channel_id,
                    "status": "error",
                    "checked_at": checked_at,
                    "error_message": "Channel not found during probe",
                }
            if resp.status_code == 200:
                data = resp.json()
                ch.status = "ok"
                ch.connect_time_ms = data.get("connect_time_ms")
                res = data.get("resolution")
                ch.resolution = res.get("label") if res else None
                video_url: str | None = data.get("video_url")
                if video_url:
                    clip_id = video_url.rstrip("/").split("/")[-1]
                    ch.clip_id = clip_id
                    ch.clip_url = f"{selected_checker_url}/clips/{clip_id}"
                else:
                    ch.clip_id = None
                    ch.clip_url = None
                ch.error_message = None
            else:
                detail = resp.json().get("detail", {})
                err = (
                    detail.get("error", "Unknown error")
                    if isinstance(detail, dict)
                    else str(detail)
                )
                ch.status = "error"
                ch.error_message = err
            ch.last_checked = checked_at
            ch.updated_at = checked_at
            session.commit()
            result = {
                "channel_id": channel_id,
                "status": ch.status,
                "checker_url": selected_checker_url,
                "checker_name": _checker_name_from_url(selected_checker_url),
                "checked_at": checked_at,
                "error_message": ch.error_message,
            }
    except Exception as exc:
        with Session(db_engine) as session:
            ch = session.get(ChannelModel, channel_id)
            if ch:
                ch.status = "error"
                ch.error_message = str(exc)
                ch.last_checked = checked_at
                ch.updated_at = checked_at
                session.commit()
        result = {
            "channel_id": channel_id,
            "status": "error",
            "checker_url": selected_checker_url,
            "checker_name": _checker_name_from_url(selected_checker_url),
            "checked_at": checked_at,
            "error_message": str(exc),
        }
    await broadcast("channel_updated", {"channel_id": channel_id})
    return result


async def _health_check_loop() -> None:
    # Initial delay so startup completes first
    await asyncio.sleep(10)
    while True:
        checks_enabled = bool(runtime_settings.get("checks_enabled", True))
        interval_seconds = int(runtime_settings.get("health_check_interval", HEALTH_CHECK_INTERVAL_DEFAULT))
        gap_seconds = int(runtime_settings.get("health_channel_gap_seconds", HEALTH_CHANNEL_GAP_SECONDS_DEFAULT))
        cycle_checker_urls = _active_checker_urls()
        _refresh_health_status_from_settings(cycle_checker_urls)
        _refresh_checker_workers_status(cycle_checker_urls)

        if not checks_enabled:
            health_check_status["running"] = False
            health_check_status["current_channel_id"] = None
            health_check_status["current_channel_title"] = None
            health_check_status["current_checker_url"] = None
            health_check_status["current_checker_name"] = None
            await _broadcast_health_status()
            await asyncio.sleep(2)
            continue

        try:
            with Session(db_engine) as session:
                channels = session.execute(
                    sa.select(ChannelModel)
                    .where(ChannelModel.enabled.is_(True))
                    .order_by(ChannelModel.id)
                ).scalars().all()
                rows = [(ch.id, ch.hash, ch.title) for ch in channels]

            health_check_status["running"] = True
            health_check_status["cycle_id"] += 1
            health_check_status["last_cycle_started"] = _now_ts()
            health_check_status["last_cycle_finished"] = None
            health_check_status["checked_in_cycle"] = 0
            health_check_status["total_channels_in_cycle"] = len(rows)
            health_check_status["current_channel_id"] = None
            health_check_status["current_channel_title"] = None
            health_check_status["current_checker_url"] = None
            health_check_status["current_checker_name"] = None
            await _broadcast_health_status()

            worker_count = len(cycle_checker_urls)
            progress_lock = asyncio.Lock()
            sem = asyncio.Semaphore(worker_count)

            async def run_one(ch_id: int, ch_hash: str, ch_title: str) -> None:
                async with sem:
                    checker_url = await _pick_checker_url(cycle_checker_urls)

                    async with progress_lock:
                        health_check_status["current_channel_id"] = ch_id
                        health_check_status["current_channel_title"] = ch_title
                        health_check_status["current_checker_url"] = checker_url
                        health_check_status["current_checker_name"] = _checker_name_from_url(checker_url)
                        worker = health_check_status["checker_workers"].get(checker_url)
                        if worker is not None:
                            worker["busy"] = True
                            worker["current_channel_id"] = ch_id
                            worker["current_channel_title"] = ch_title
                            worker["last_started"] = _now_ts()
                            worker["busy_since"] = _now_ts()
                    await _broadcast_health_status()

                    result = await _probe_channel(ch_id, ch_hash, checker_url)
                    result["channel_title"] = ch_title

                    async with progress_lock:
                        health_check_status["checked_in_cycle"] += 1
                        health_check_status["last_result"] = result
                        health_check_status["recent_results"].insert(0, result)
                        health_check_status["recent_results"] = health_check_status["recent_results"][:30]
                        worker = health_check_status["checker_workers"].get(checker_url)
                        if worker is not None:
                            worker["busy"] = False
                            worker["current_channel_id"] = None
                            worker["current_channel_title"] = None
                            worker["last_finished"] = _now_ts()
                            worker["busy_since"] = None
                            worker["last_result"] = {
                                "channel_id": result.get("channel_id"),
                                "channel_title": result.get("channel_title"),
                                "status": result.get("status"),
                                "checked_at": result.get("checked_at"),
                                "error_message": result.get("error_message"),
                            }
                    await _broadcast_health_status()

                    if gap_seconds > 0:
                        await asyncio.sleep(gap_seconds)

            await asyncio.gather(*(run_one(ch_id, ch_hash, ch_title) for ch_id, ch_hash, ch_title in rows))
        except Exception as exc:
            health_check_status["last_result"] = {
                "channel_id": None,
                "channel_title": "internal",
                "status": "error",
                "checked_at": _now_ts(),
                "error_message": f"health loop error: {exc}",
            }
            health_check_status["recent_results"].insert(0, health_check_status["last_result"])
            health_check_status["recent_results"] = health_check_status["recent_results"][:30]
            await _broadcast_health_status()
        finally:
            health_check_status["running"] = False
            health_check_status["current_channel_id"] = None
            health_check_status["current_channel_title"] = None
            health_check_status["current_checker_url"] = None
            health_check_status["current_checker_name"] = None
            health_check_status["last_cycle_finished"] = _now_ts()
            await _broadcast_health_status()

        await asyncio.sleep(interval_seconds)


# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wait for DB
    for _ in range(30):
        try:
            with db_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception:
            await asyncio.sleep(2)
    Base.metadata.create_all(db_engine)
    _run_schema_migrations()
    _load_runtime_settings_from_db()
    startup_urls = _active_checker_urls()
    _refresh_health_status_from_settings(startup_urls)
    _refresh_checker_workers_status(startup_urls)

    bg_task = asyncio.create_task(_health_check_loop())
    yield
    bg_task.cancel()

    # Cleanup active stream on shutdown
    if active_stream:
        if active_stream.ffmpeg_process:
            active_stream.ffmpeg_process.terminate()
        await ace_stop_session(active_stream.command_url)


app = FastAPI(title="Ace Stream Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────
class ChannelCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    hash: str = Field(..., min_length=40, max_length=40)


class ChannelUpdate(BaseModel):
    title: str | None = None
    enabled: bool | None = None


class SettingsUpdate(BaseModel):
    checks_enabled: bool | None = None
    checker_instances: int | None = None
    health_check_interval: int | None = None
    health_probe_timeout_seconds: int | None = None
    health_channel_gap_seconds: int | None = None
    max_segments: int | None = None
    hls_segment_time: int | None = None


def _ch_dict(ch: ChannelModel) -> dict:
    return {
        "id": ch.id,
        "title": ch.title,
        "hash": ch.hash,
        "enabled": bool(ch.enabled),
        "status": ch.status,
        "last_checked": ch.last_checked,
        "connect_time_ms": ch.connect_time_ms,
        "resolution": ch.resolution,
        "clip_id": ch.clip_id,
        "clip_url": ch.clip_url,
        "error_message": ch.error_message,
        "created_at": ch.created_at,
    }


# ── Channel endpoints ─────────────────────────────────────────────────────────
@app.get("/channels")
async def list_channels(include_disabled: bool = False):
    with Session(db_engine) as session:
        query = sa.select(ChannelModel)
        if not include_disabled:
            query = query.where(ChannelModel.enabled.is_(True))
        rows = session.execute(query.order_by(ChannelModel.id)).scalars().all()
        return [_ch_dict(ch) for ch in rows]


@app.post("/channels", status_code=201)
async def create_channel(data: ChannelCreate):
    if not re.fullmatch(r"[0-9a-fA-F]{40}", data.hash):
        raise HTTPException(400, "Invalid hash: must be 40 hex characters")
    with Session(db_engine) as session:
        existing = session.execute(
            sa.select(ChannelModel).where(ChannelModel.hash == data.hash.lower())
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(409, "A channel with this hash already exists")
        ch = ChannelModel(
            title=data.title,
            hash=data.hash.lower(),
            enabled=True,
            created_at=_now_ts(),
            updated_at=_now_ts(),
        )
        session.add(ch)
        session.commit()
        session.refresh(ch)
        result = _ch_dict(ch)
    asyncio.create_task(_probe_channel(result["id"], data.hash.lower()))
    return result


@app.get("/channels/{channel_id}")
async def get_channel(channel_id: int):
    with Session(db_engine) as session:
        ch = session.get(ChannelModel, channel_id)
        if not ch:
            raise HTTPException(404, "Channel not found")
        return _ch_dict(ch)


@app.get("/channels/{channel_id}/clip")
async def get_channel_clip(channel_id: int):
    with Session(db_engine) as session:
        ch = session.get(ChannelModel, channel_id)
        if not ch:
            raise HTTPException(404, "Channel not found")
        clip_url = ch.clip_url
        if not clip_url and ch.clip_id:
            clip_url = f"{_active_checker_urls()[0]}/clips/{ch.clip_id}"

    if not clip_url:
        raise HTTPException(404, "No clip available")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(clip_url)
    except Exception as exc:
        raise HTTPException(502, f"Clip fetch failed: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(resp.status_code, "Clip unavailable")

    content_type = resp.headers.get("content-type", "video/mp4")
    return Response(
        content=resp.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=15"},
    )


@app.put("/channels/{channel_id}")
async def update_channel(channel_id: int, data: ChannelUpdate):
    should_stop_stream = False
    with Session(db_engine) as session:
        ch = session.get(ChannelModel, channel_id)
        if not ch:
            raise HTTPException(404, "Channel not found")
        if data.title is not None:
            ch.title = data.title
        if data.enabled is not None:
            ch.enabled = data.enabled
            if data.enabled is False and active_stream and active_stream.channel_id == channel_id:
                should_stop_stream = True
        ch.updated_at = _now_ts()
        session.commit()
        result = _ch_dict(ch)

    if should_stop_stream:
        asyncio.create_task(_stop_active_stream_internal())

    return result


@app.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: int):
    with Session(db_engine) as session:
        ch = session.get(ChannelModel, channel_id)
        if not ch:
            raise HTTPException(404, "Channel not found")
        session.delete(ch)
        session.commit()
    return Response(status_code=204)


@app.post("/channels/{channel_id}/check")
async def manual_check(channel_id: int):
    with Session(db_engine) as session:
        ch = session.get(ChannelModel, channel_id)
        if not ch:
            raise HTTPException(404, "Channel not found")
        if not ch.enabled:
            raise HTTPException(409, "Channel is disabled")
        content_hash = ch.hash
    asyncio.create_task(_probe_channel(channel_id, content_hash))
    return {"message": "Health check started", "channel_id": channel_id}


@app.get("/health-check/status")
async def get_health_check_status():
    return _status_snapshot()


@app.get("/settings")
async def get_settings():
    return _settings_snapshot()


@app.put("/settings")
async def update_settings(payload: SettingsUpdate):
    data = payload.model_dump(exclude_none=True)
    if not data:
        return _settings_snapshot()

    unknown = [k for k in data.keys() if k not in SETTING_SCHEMA]
    if unknown:
        raise HTTPException(400, f"Unknown setting(s): {', '.join(unknown)}")

    with Session(db_engine) as session:
        for key, raw_value in data.items():
            value = _coerce_setting_value(key, raw_value)
            runtime_settings[key] = value

            row = session.get(AppSettingModel, key)
            if row is None:
                row = AppSettingModel(key=key, value=_setting_to_db_value(key, value), updated_at=_now_ts())
                session.add(row)
            else:
                row.value = _setting_to_db_value(key, value)
                row.updated_at = _now_ts()

        session.commit()

    if health_check_status.get("running"):
        cycle_urls = [
            url
            for url, worker in health_check_status.get("checker_workers", {}).items()
            if worker.get("enabled")
        ]
        _refresh_health_status_from_settings(cycle_urls or _active_checker_urls())
    else:
        new_urls = _active_checker_urls()
        _refresh_health_status_from_settings(new_urls)
        _refresh_checker_workers_status(new_urls)
    await broadcast("settings_updated", _settings_snapshot())
    await _broadcast_health_status()
    return _settings_snapshot()


@app.post("/settings/reset")
async def reset_settings():
    with Session(db_engine) as session:
        for key, meta in SETTING_SCHEMA.items():
            value = meta["default"]
            runtime_settings[key] = value
            row = session.get(AppSettingModel, key)
            if row is None:
                row = AppSettingModel(key=key, value=_setting_to_db_value(key, value), updated_at=_now_ts())
                session.add(row)
            else:
                row.value = _setting_to_db_value(key, value)
                row.updated_at = _now_ts()
        session.commit()

    if health_check_status.get("running"):
        cycle_urls = [
            url
            for url, worker in health_check_status.get("checker_workers", {}).items()
            if worker.get("enabled")
        ]
        _refresh_health_status_from_settings(cycle_urls or _active_checker_urls())
    else:
        new_urls = _active_checker_urls()
        _refresh_health_status_from_settings(new_urls)
        _refresh_checker_workers_status(new_urls)
    await broadcast("settings_updated", _settings_snapshot())
    await _broadcast_health_status()
    return _settings_snapshot()


# ── Stream endpoints ──────────────────────────────────────────────────────────
@app.get("/stream")
async def get_stream_info():
    if not active_stream:
        return {"active": False}
    return {
        "active": True,
        "channel_id": active_stream.channel_id,
        "hash": active_stream.content_hash,
        "started_at": active_stream.started_at,
    }


@app.post("/stream/switch/{channel_id}")
async def switch_to(channel_id: int):
    with Session(db_engine) as session:
        ch = session.get(ChannelModel, channel_id)
        if not ch:
            raise HTTPException(404, "Channel not found")
        if not ch.enabled:
            raise HTTPException(409, "Channel is disabled")
        content_hash = ch.hash
    try:
        await switch_stream(channel_id, content_hash)
    except Exception as exc:
        raise HTTPException(502, f"Stream switch failed: {exc}") from exc
    return {"message": "Switched", "channel_id": channel_id}


async def _stop_active_stream_internal() -> dict[str, str]:
    global active_stream
    async with active_stream_lock:
        if not active_stream:
            return {"message": "No active stream"}
        if active_stream.ffmpeg_process:
            try:
                active_stream.ffmpeg_process.terminate()
                await asyncio.wait_for(active_stream.ffmpeg_process.wait(), timeout=5)
            except Exception:
                try:
                    active_stream.ffmpeg_process.kill()
                except Exception:
                    pass
        await ace_stop_session(active_stream.command_url)
        _clear_segments()
        active_stream = None
    await broadcast("stream_stopped", {})
    return {"message": "Stream stopped"}


@app.delete("/stream")
async def stop_active_stream():
    return await _stop_active_stream_internal()


@app.get("/stream/playlist.m3u8")
async def get_playlist():
    playlist_path = SEGMENTS_DIR / "stream.m3u8"
    if not playlist_path.exists():
        raise HTTPException(404, "No active stream — start a stream first")
    content = playlist_path.read_text()
    # Segment files are relative; hls.js resolves them relative to this endpoint.
    # Return as-is; the nginx proxy ensures /api/stream/streamXXXXX.ts routes work.
    return Response(
        content=content,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/stream/{filename}")
async def get_segment(filename: str):
    if not re.fullmatch(r"stream\d+\.ts", filename):
        raise HTTPException(400, "Invalid segment filename")
    seg_path = SEGMENTS_DIR / filename
    if not seg_path.exists():
        raise HTTPException(404, "Segment not found or expired")
    return Response(
        content=seg_path.read_bytes(),
        media_type="video/mp2t",
        headers={"Cache-Control": "public, max-age=30"},
    )


# ── SSE endpoint ──────────────────────────────────────────────────────────────
@app.get("/events")
async def sse(request: Request):
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
    _sse_queues.append(queue)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            yield "event: connected\ndata: {}\n\n"
            yield f"event: health_check_status\ndata: {json.dumps(_status_snapshot())}\n\n"
            yield f"event: settings_updated\ndata: {json.dumps(_settings_snapshot())}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            try:
                _sse_queues.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_channel": active_stream.channel_id if active_stream else None,
    }
