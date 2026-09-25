# GoodNotes VLM Extractor

Dockerized Python service for extracting pages from GoodNotes shared notebooks,
sending each rendered page image to an Ollama vision model, and returning JSON.

Example GoodNotes share URL:

```text
https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z#page-44
```

GoodNotes renders shared notebooks through its web app, so the service uses
Playwright to load the page, jump to requested pages, screenshot the rendered
page content, and pass those images to Ollama one by one.

## Requirements

- Docker
- An Ollama server with a vision-capable model, for example:

```bash
ollama pull llama3.2-vision
ollama serve
```

If Ollama is running on the host machine, the Docker defaults use:

```text
http://host.docker.internal:11434
```

## Local Docker Setup

Configuration is read from `.env`. A working default is included:

```env
OLLAMA_URL=http://localhost:11434
DOCKER_OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2-vision
MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=5455
MCP_PATH=/mcp
OUTPUT_DIR=output
```

For Docker, Compose reads `.env` and maps `OLLAMA_URL` inside the container to
`DOCKER_OLLAMA_URL`, because `localhost` inside a container is not your host
machine.

Start the streamable HTTP MCP server:

```bash
docker compose up --build goodnotes-mcp
```

Or run it in the background:

```bash
docker compose up -d --build goodnotes-mcp
```

Then point Hermes at:

```yaml
mcp_servers:
  goodnotes-vlm:
    url: http://127.0.0.1:5455/mcp
    enabled: true
    timeout: 120
    trust: untrusted
    tools: true
    resources: false
    prompts: false
```

Stop the MCP server:

```bash
docker compose down
```

To run the optional HTTP API service instead:

```bash
docker compose up --build goodnotes
```

The API will be available at:

```text
http://localhost:${API_PORT}
```

## API

Health check:

```bash
curl http://localhost:${API_PORT}/health
```

Analyze one page:

```bash
curl -s http://localhost:${API_PORT}/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
    "pages": 44,
    "prompt": "Read the contents of this page into text_content.",
    "response_schema": {
      "type": "object",
      "properties": {
        "text_content": {"type": "string"}
      },
      "required": ["text_content"]
    }
  }'
```

Analyze the last page without knowing the page count:

```bash
curl -s http://localhost:${API_PORT}/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
    "pages": "last",
    "prompt": "Read the contents of this page into text_content.",
    "response_schema": {
      "type": "object",
      "properties": {
        "text_content": {"type": "string"}
      },
      "required": ["text_content"]
    }
  }'
```

Return only the page image for a single page:

```bash
curl -o page-44.png -s http://localhost:${API_PORT}/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
    "pages": 44,
    "just_image": true
  }'
```

For multiple pages with `just_image`, the API returns a JSON list with image
paths because a single HTTP response cannot directly be multiple PNG files.

Analyze multiple pages:

```bash
curl -s http://localhost:${API_PORT}/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
    "pages": "1,3-5,44",
    "prompt": "Read the contents of this page into text_content.",
    "response_schema": {
      "type": "object",
      "properties": {
        "text_content": {"type": "string"}
      },
      "required": ["text_content"]
    }
  }'
```

Response shape:

```json
[
  {
    "source_url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
    "page": 44,
    "page_count": 45,
    "image_path": "output/requests/oXNpvq0N3CcdtJ9KPXkD4Z-pages-44-a1b2c3d4e5f6/page-44.png",
    "model": "llama3.2-vision",
    "result": {
      "text_content": "August 2 2026\nA Starbucks ?\n..."
    }
  }
]
```

The `result` field is the JSON parsed from the model response. Ollama is called
through `/api/chat` with `think: false`, `stream: false`, and the caller's
`response_schema` as the chat `format`. VLM extraction requires both `prompt`
and `response_schema`. If the model does not return valid JSON, the service
still returns JSON with `raw_response` and `parse_error`.

Each request writes page images into a unique `output/requests/...` directory,
so overlapping requests do not overwrite each other's screenshots.

## CLI In Docker

The same pipeline can run as a one-off command:

```bash
docker compose run --rm goodnotes \
  python main.py "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z" \
  --pages 44 \
  --prompt 'Read the contents of this page into text_content.' \
  --response-schema '{"type":"object","properties":{"text_content":{"type":"string"}},"required":["text_content"]}'
```

Multiple pages:

```bash
docker compose run --rm goodnotes \
  python main.py "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z" \
  --pages "1,3-5" \
  --prompt 'Read the contents of this page into text_content.' \
  --response-schema '{"type":"object","properties":{"text_content":{"type":"string"}},"required":["text_content"]}'
```

Image only:

```bash
docker compose run --rm goodnotes \
  python main.py "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z" \
  --pages last \
  --just_image
```

## MCP Server

The MCP server uses streamable HTTP by default. For the local `.env` setup, use
Compose:

```bash
docker compose up --build goodnotes-mcp
```

Hermes config:

```yaml
mcp_servers:
  goodnotes-vlm:
    url: http://127.0.0.1:5455/mcp
    enabled: true
    timeout: 120
    trust: untrusted
    tools: true
    resources: false
    prompts: false
```

The streamable HTTP container is expected to stay running while Hermes uses it.
Stop it with `Ctrl-C` or `docker compose down`.

If you prefer a one-off Docker command without this repo (`--init` runs tini as
PID 1 so it reaps the headless Chromium processes Playwright leaves as zombies
after each request — without it they accumulate until the container restarts):

```bash
docker run --rm --init \
  --name goodnotes-vlm-mcp \
  -p 5455:5455 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=5455 \
  -e MCP_PATH=/mcp \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=llama3.2-vision \
  ghcr.io/karunstha/goodnotes-vlm-mcp:latest
```

For image-only tools, no Ollama variables are required. Use
`extract_goodnotes_image` with arguments like:

```json
{
  "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
  "pages": "last"
}
```

To pass individual environment variables:

```bash
docker run --rm --init \
  --name goodnotes-vlm-mcp \
  -p 5455:5455 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=5455 \
  -e MCP_PATH=/mcp \
  -e OLLAMA_URL=http://100.119.229.86:11434 \
  -e OLLAMA_MODEL=gemma4:12b-64k \
  ghcr.io/karunstha/goodnotes-vlm-mcp:latest
```

To use an env file instead:

```bash
docker run --rm --init \
  --name goodnotes-vlm-mcp \
  -p 5455:5455 \
  --env-file /absolute/path/to/goodnotes.env \
  ghcr.io/karunstha/goodnotes-vlm-mcp:latest
```

Example `goodnotes.env`:

```env
MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=5455
MCP_PATH=/mcp
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2-vision
OUTPUT_DIR=/app/output
BROWSER_TIMEOUT_MS=60000
BROWSER_SETTLE_MS=6000
```

To keep extracted images on the host, mount an output directory:

```bash
-v /absolute/path/to/output:/app/output
```

Use absolute paths in Docker commands when the command is run outside this
project directory.

The publish workflow in [.github/workflows/publish.yml](.github/workflows/publish.yml)
builds/pushes the Docker image to GHCR when you push a version tag such as
`v0.1.0`.

Run the MCP server locally:

```bash
workon test
PYTHONPATH=src python -m goodnotes_ocr.mcp_server
```

Example MCP client config:

```yaml
mcp_servers:
  goodnotes-vlm:
    url: http://127.0.0.1:5455/mcp
    enabled: true
    timeout: 120
    trust: untrusted
    tools: true
    resources: false
    prompts: false
```

Tools:

- `extract_goodnotes`: VLM extraction, or MCP image content with `just_image: true`
- `extract_goodnotes_image`: always returns MCP `Image` content

Example MCP tool arguments for a direct MCP image:

```json
{
  "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
  "pages": "last"
}
```

Example MCP tool arguments for VLM extraction:

```json
{
  "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
  "pages": 3,
  "prompt": "Read the contents of this page into text_content.",
  "response_schema": {
    "type": "object",
    "properties": {
      "text_content": {"type": "string"}
    },
    "required": ["text_content"]
  }
}
```

## Configuration

Configuration lives in `.env`:

- `VLM_PROVIDER`: `ollama` (default) or `openai`. Set `openai` to use any
  OpenAI-compatible `/chat/completions` server instead of Ollama (llama.cpp's
  `llama-server`, vLLM, LM Studio, etc).
- `OLLAMA_URL`: Ollama base URL, default `http://host.docker.internal:11434`
- `DOCKER_OLLAMA_URL`: Ollama URL used by Docker Compose, default `http://host.docker.internal:11434`
- `OLLAMA_MODEL`: vision model, default `llama3.2-vision`
- `OPENAI_BASE_URL`: OpenAI-compatible base URL, used when `VLM_PROVIDER=openai`, default `http://localhost:8080/v1`
- `DOCKER_OPENAI_BASE_URL`: same, used by Docker Compose, default `http://host.docker.internal:8080/v1`
- `OPENAI_MODEL`: model name sent to the OpenAI-compatible server, default `default` (most local servers serve whatever's loaded regardless of this value)
- `OPENAI_API_KEY`: sent as a Bearer token; default `none` works with unauthenticated local servers
- `API_PORT`: host port exposed by Docker Compose, default `8000`
- `MCP_TRANSPORT`: `stdio`, `sse`, or `streamable-http`; default in `.env` is `streamable-http`
- `MCP_HOST`: MCP HTTP bind host, default `0.0.0.0`
- `MCP_PORT`: MCP HTTP port, default `5455`
- `MCP_PATH`: streamable HTTP endpoint path, default `/mcp`
- `OUTPUT_DIR`: extracted image directory, default `output`; each request writes to a unique subdirectory under `requests`
- `BROWSER_TIMEOUT_MS`: page load timeout, default `60000`
- `BROWSER_SETTLE_MS`: render settle delay, default `6000`
- `MAX_PROBE_PAGE`: fallback page-count probe limit, default `2000`
- `PDF_DPI`: direct PDF render DPI if you build a custom image with PDF tooling
- `VLM_TIMEOUT_SECONDS`: Ollama request timeout, default `120`
- `VLM_MAX_IMAGE_DIMENSION`: longest edge (px) the screenshot is downscaled to before base64-encoding for the VLM request, default `1600`; the saved screenshot on disk is unaffected. Lower this if your VLM backend has limited VRAM/context headroom for vision tokens.

Per-request API overrides:

- `model`
- `ollama_url` (deprecated alias for `base_url`, Ollama provider only)
- `provider`
- `base_url`
- `response_schema`

## Local Run

Local runs also load `.env` automatically:

```bash
workon test
PYTHONPATH=src uvicorn goodnotes_ocr.api:app --host 0.0.0.0 --port 8000
```

CLI:

```bash
workon test
PYTHONPATH=src python main.py "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z" \
  --pages 44 \
  --prompt 'Read the contents of this page into text_content.' \
  --response-schema '{"type":"object","properties":{"text_content":{"type":"string"}},"required":["text_content"]}'
```

## Notes

- Pages are 1-based.
- `pages` accepts an integer, a list, `last`, or a string like `1,3-5,last`.
- `just_image` skips the VLM call and extracts page image(s) only.
- The default Docker image is optimized for GoodNotes web links. Direct PDF URL
  rendering requires a custom image with `poppler-utils` and `pypdf` installed.
- GoodNotes can change its web app internals. The page renderer uses broad DOM
  heuristics rather than relying on one private API.
- Shared GoodNotes links are public to anyone with the link. Avoid processing
  sensitive notebooks unless you control the runtime and storage.
