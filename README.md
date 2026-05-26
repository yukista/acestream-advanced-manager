# Ace Stream Channel Health

FastAPI app to probe an Ace Stream hash, measure connection time, detect resolution, and return a 10-second video clip through a separate endpoint.

The Docker image starts the Ace Stream engine inside the same container and then launches the API.

## API

- `POST /probe`
  - Body: `{ "hash": "<acestream_hash>" }`
  - Returns JSON with connection status, connection time, resolution, and a `video_url`
- `GET /clips/{clip_id}`
  - Returns the generated video clip
- `GET /docs`
  - Swagger UI

## Environment variables

- `ACESTREAM_ENGINE_URL` - Ace Stream engine base URL, default `http://127.0.0.1:6878`
- `ACESTREAM_CONNECT_TIMEOUT_SECONDS` - engine connect timeout, default `14`
- `ACESTREAM_DIRECT_RESOLVE_TIMEOUT_SECONDS` - timeout to resolve direct stream URL, default `9`
- `ACESTREAM_STREAM_READ_TIMEOUT_SECONDS` - timeout to receive first stream bytes, default `7`
- `ACESTREAM_CLIP_CAPTURE_TIMEOUT_SECONDS` - max timeout to generate clip, default `24`
- `ACESTREAM_SECOND_PHASE_CAPTURE_TIMEOUT_SECONDS` - retry timeout for borderline streams, default `40`
- `ACESTREAM_CLIP_SECONDS` - clip length, default `10`
- `ACESTREAM_CLIP_TTL_SECONDS` - in-memory clip TTL, default `3600`
- `ACESTREAM_MAX_STORED_CLIPS` - max clips kept in memory, default `20`
- `FFMPEG_BIN` - ffmpeg binary name/path, default `ffmpeg`
- `FFPROBE_BIN` - ffprobe binary name/path, default `ffprobe`

## Run locally

1. Ensure an Ace Stream engine is reachable at `ACESTREAM_ENGINE_URL`.
2. Install dependencies.
3. Run the app with Uvicorn.

## Docker

Build the image and run it. The container will start Ace Stream engine on port 6878 and the API on port 8000.

The API uses `http://127.0.0.1:6878` by default inside the container.
