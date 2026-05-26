from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field


ENGINE_BASE_URL = os.getenv("ACESTREAM_ENGINE_URL", "http://127.0.0.1:6878").rstrip("/")
CONNECT_TIMEOUT_SECONDS = float(os.getenv("ACESTREAM_CONNECT_TIMEOUT_SECONDS", "14"))
DIRECT_RESOLVE_TIMEOUT_SECONDS = float(os.getenv("ACESTREAM_DIRECT_RESOLVE_TIMEOUT_SECONDS", "9"))
STREAM_READ_TIMEOUT_SECONDS = float(os.getenv("ACESTREAM_STREAM_READ_TIMEOUT_SECONDS", "20"))
CLIP_CAPTURE_TIMEOUT_SECONDS = float(os.getenv("ACESTREAM_CLIP_CAPTURE_TIMEOUT_SECONDS", "24"))
SECOND_PHASE_CAPTURE_TIMEOUT_SECONDS = float(os.getenv("ACESTREAM_SECOND_PHASE_CAPTURE_TIMEOUT_SECONDS", "40"))
CLIP_SECONDS = int(os.getenv("ACESTREAM_CLIP_SECONDS", "10"))
CLIP_TTL_SECONDS = int(os.getenv("ACESTREAM_CLIP_TTL_SECONDS", "3600"))
MAX_STORED_CLIPS = int(os.getenv("ACESTREAM_MAX_STORED_CLIPS", "20"))
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")


class ProbeRequest(BaseModel):
    hash: str = Field(..., min_length=1, description="Ace Stream content hash")
    timeout_seconds: float | None = Field(
        None,
        ge=5,
        le=300,
        description="Optional timeout override for this probe",
    )


class Resolution(BaseModel):
    width: int
    height: int
    label: str


class ProbeResponse(BaseModel):
    hash: str
    connected: bool
    connect_time_ms: int | None = None
    resolution: Resolution | None = None
    video_url: str | None = None
    error: str | None = None


@dataclass
class StoredClip:
    content: bytes
    media_type: str
    created_at: float


class ClipStore:
    def __init__(self, ttl_seconds: int, max_items: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._items: dict[str, StoredClip] = {}

    def put(self, content: bytes, media_type: str = "video/mp4") -> str:
        self._purge_expired()
        clip_id = uuid.uuid4().hex
        self._items[clip_id] = StoredClip(content=content, media_type=media_type, created_at=time.time())
        self._enforce_limit()
        return clip_id

    def get(self, clip_id: str) -> StoredClip | None:
        self._purge_expired()
        return self._items.get(clip_id)

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [clip_id for clip_id, clip in self._items.items() if now - clip.created_at > self._ttl_seconds]
        for clip_id in expired:
            self._items.pop(clip_id, None)

    def _enforce_limit(self) -> None:
        if len(self._items) <= self._max_items:
            return
        oldest = sorted(self._items.items(), key=lambda item: item[1].created_at)
        for clip_id, _ in oldest[: len(self._items) - self._max_items]:
            self._items.pop(clip_id, None)


class EngineError(RuntimeError):
    pass


class EngineClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._direct_resolve_timeout_seconds = DIRECT_RESOLVE_TIMEOUT_SECONDS
        self._stream_read_timeout_seconds = STREAM_READ_TIMEOUT_SECONDS
        self._clip_capture_timeout_seconds = CLIP_CAPTURE_TIMEOUT_SECONDS

    async def connect(self, content_hash: str, player_id: str) -> tuple[str, str | None, int]:
        params = {
            "id": content_hash,
            "format": "json",
            "use_api_events": "1",
            "use_stop_notifications": "1",
            "pid": player_id,
        }
        url = f"{self._base_url}/ace/manifest.m3u8"
        started = time.perf_counter()
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, params=params)
            except httpx.TimeoutException as exc:
                raise EngineError("Connection to Ace Stream engine timed out") from exc
            except httpx.HTTPError as exc:
                raise EngineError(f"Unable to contact Ace Stream engine: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        payload = self._parse_json(response.text)
        if response.status_code >= 400:
            detail = payload.get("error") or response.text.strip() or f"HTTP {response.status_code}"
            raise EngineError(detail)

        error = payload.get("error")
        if error:
            raise EngineError(str(error))

        response_data = payload.get("response") or {}
        playback_url = response_data.get("playback_url")
        command_url = response_data.get("command_url")
        if not playback_url:
            playback_url = f"{self._base_url}/ace/manifest.m3u8?id={content_hash}"
        return playback_url, command_url, elapsed_ms

    async def stop_session(self, command_url: str | None) -> None:
        if not command_url:
            return
        timeout = httpx.Timeout(2.5)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                await client.get(command_url, params={"method": "stop"})
            except httpx.HTTPError:
                # Best-effort cleanup.
                return

    async def probe_resolution(self, media_url: str) -> Resolution:
        command = [
            FFPROBE_BIN,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            media_url,
        ]
        stdout = await self._run_command(command)
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise EngineError("ffprobe returned invalid JSON") from exc

        streams = data.get("streams") or []
        if not streams:
            raise EngineError("Could not detect video resolution")

        stream = streams[0]
        width = int(stream["width"])
        height = int(stream["height"])
        return Resolution(width=width, height=height, label=f"{width}x{height}")

    async def probe_resolution_from_clip(self, clip_bytes: bytes) -> Resolution:
        command = [
            FFPROBE_BIN,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            "pipe:0",
        ]
        stdout = await self._run_command(
            command,
            capture_stdout=True,
            timeout_seconds=self._timeout_seconds,
            stdin_bytes=clip_bytes,
        )
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise EngineError("ffprobe returned invalid JSON") from exc

        streams = data.get("streams") or []
        if not streams:
            raise EngineError("Could not detect video resolution from clip")

        stream = streams[0]
        width = int(stream["width"])
        height = int(stream["height"])
        return Resolution(width=width, height=height, label=f"{width}x{height}")

    async def resolve_direct_stream_url(self, content_hash: str, player_id: str | None = None) -> str:
        params = f"id={content_hash}" + (f"&pid={player_id}" if player_id else "")
        direct_url = f"{self._base_url}/ace/getstream?{params}"
        timeout = httpx.Timeout(self._direct_resolve_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                async with client.stream("GET", direct_url) as response:
                    if response.status_code >= 400:
                        raise EngineError(f"Direct stream request failed with HTTP {response.status_code}")
                    return str(response.url)
            except httpx.TimeoutException as exc:
                raise EngineError("Direct stream URL resolution timed out") from exc
            except httpx.HTTPError as exc:
                raise EngineError(f"Direct stream URL resolution failed: {exc}") from exc

    async def verify_stream_readable(self, media_url: str) -> None:
        timeout = httpx.Timeout(self._stream_read_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                async with client.stream("GET", media_url) as response:
                    if response.status_code >= 400:
                        raise EngineError(f"Stream is not readable (HTTP {response.status_code})")
                    iterator = response.aiter_bytes()
                    try:
                        first_chunk = await asyncio.wait_for(anext(iterator), timeout=self._stream_read_timeout_seconds)
                    except asyncio.TimeoutError as exc:
                        raise EngineError("No stream data received in time") from exc
                    if not first_chunk:
                        raise EngineError("Empty stream response")
            except httpx.TimeoutException as exc:
                raise EngineError("Stream readability check timed out") from exc
            except httpx.HTTPError as exc:
                raise EngineError(f"Stream readability check failed: {exc}") from exc

    async def capture_clip(self, media_url: str, seconds: int, *, timeout_seconds_override: float | None = None) -> bytes:
        timeout_limit = timeout_seconds_override or self._clip_capture_timeout_seconds
        # Keep enough room for stream warmup and clip extraction.
        timeout_seconds = max(seconds + 6, timeout_limit)
        rw_timeout_seconds = max(self._timeout_seconds, timeout_seconds)
        command = [
            FFMPEG_BIN,
            "-hide_banner",
            "-loglevel",
            "error",
            "-analyzeduration",
            "3000000",
            "-probesize",
            "3000000",
            "-rw_timeout",
            str(int(rw_timeout_seconds * 1_000_000)),
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "2",
            "-i",
            media_url,
            "-t",
            str(seconds),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-f",
            "mp4",
            "pipe:1",
        ]
        return await self._run_command(command, capture_stdout=True, timeout_seconds=timeout_seconds)

    async def _run_command(
        self,
        command: list[str],
        *,
        capture_stdout: bool = True,
        timeout_seconds: float | None = None,
        stdin_bytes: bytes | None = None,
    ) -> str | bytes:
        stdout_pipe = asyncio.subprocess.PIPE if capture_stdout else asyncio.subprocess.DEVNULL
        stderr_pipe = asyncio.subprocess.PIPE
        stdin_pipe = asyncio.subprocess.PIPE if stdin_bytes is not None else None
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=stdin_pipe,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin_bytes),
                timeout=timeout_seconds or self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise EngineError(f"Command timed out: {' '.join(command[:2])}") from exc

        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip() or "Command failed"
            raise EngineError(message)

        if capture_stdout:
            return stdout
        return ""

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Some Ace Stream endpoints may return JSONP-like responses in older setups.
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError as exc:
                    raise EngineError(f"Invalid engine response: {text[:200]}") from exc
            raise EngineError(f"Invalid engine response: {text[:200]}")


store = ClipStore(ttl_seconds=CLIP_TTL_SECONDS, max_items=MAX_STORED_CLIPS)
engine = EngineClient(ENGINE_BASE_URL, CONNECT_TIMEOUT_SECONDS)
app = FastAPI(title="Ace Stream Channel Health", version="1.0.0")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Ace Stream Channel Health",
        "docs": "/docs",
        "probe": "/probe",
        "video": "/clips/{clip_id}",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/probe", response_model=ProbeResponse)
async def probe(request: Request, payload: ProbeRequest = Body(...)) -> ProbeResponse:
    command_url: str | None = None
    try:
        if len(payload.hash) != 40 or not all(c in "0123456789abcdefABCDEF" for c in payload.hash):
            raise EngineError("Invalid hash format: expected 40 hexadecimal chars")

        player_id = uuid.uuid4().hex
        probe_engine = engine if payload.timeout_seconds is None else EngineClient(ENGINE_BASE_URL, float(payload.timeout_seconds))
        playback_url, command_url, connect_time_ms = await probe_engine.connect(payload.hash, player_id)

        # The playback_url from the engine is the canonical URL for the already-open session.
        # Using /ace/getstream after opening a session via /ace/manifest.m3u8 tries to start
        # a second session with the same pid, which returns HTTP 500/403. So we only use
        # the playback_url (and the getstream URL as a last-resort fallback, not first).
        stream_candidates = [playback_url]

        # Preserve order while dropping duplicates.
        unique_stream_candidates = list(dict.fromkeys(stream_candidates))

        last_error: EngineError | None = None
        resolution: Resolution | None = None
        clip_bytes: bytes | None = None

        for stream_url in unique_stream_candidates:
            try:
                # Go directly to capture; ffmpeg handles stream availability internally.
                # verify_stream_readable caused false negatives because the engine needs
                # extra time to buffer P2P data before the HLS playlist is ready.
                try:
                    clip_bytes = await probe_engine.capture_clip(stream_url, CLIP_SECONDS, timeout_seconds_override=payload.timeout_seconds)
                except EngineError:
                    clip_bytes = await probe_engine.capture_clip(
                        stream_url,
                        CLIP_SECONDS,
                        timeout_seconds_override=(
                            payload.timeout_seconds
                            if payload.timeout_seconds is not None
                            else SECOND_PHASE_CAPTURE_TIMEOUT_SECONDS
                        ),
                    )
                resolution = await probe_engine.probe_resolution_from_clip(clip_bytes)
                break
            except EngineError as exc:
                last_error = exc

        if resolution is None or clip_bytes is None:
            raise last_error or EngineError("Failed to probe stream")

        clip_id = store.put(clip_bytes)
        video_url = str(request.url_for("get_clip", clip_id=clip_id))
        return ProbeResponse(
            hash=payload.hash,
            connected=True,
            connect_time_ms=connect_time_ms,
            resolution=resolution,
            video_url=video_url,
        )
    except EngineError as exc:
        raise HTTPException(status_code=502, detail={"hash": payload.hash, "error": str(exc)}) from exc
    finally:
        await engine.stop_session(command_url)


@app.get("/clips/{clip_id}", name="get_clip")
async def get_clip(clip_id: str) -> Response:
    clip = store.get(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found or expired")
    return Response(content=clip.content, media_type=clip.media_type, headers={"Content-Disposition": f'inline; filename="acestream-{clip_id}.mp4"'})
