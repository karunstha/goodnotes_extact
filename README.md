# GoodNotes VLM Extractor

Dockerized Python service for extracting pages from GoodNotes shared notebooks
or PDFs, sending each rendered page image to an Ollama vision model, and
returning JSON.

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

## Run

Configuration is read from `.env`. A working default is included:

```env
OLLAMA_URL=http://localhost:11434
DOCKER_OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2-vision
OUTPUT_DIR=output
```

For Docker, Compose reads `.env` and maps `OLLAMA_URL` inside the container to
`DOCKER_OLLAMA_URL`, because `localhost` inside a container is not your host
machine.

```bash
docker compose up --build
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
    "prompt": "Extract the date and every todo item. Return {\"date\": string|null, \"todos\": string[]}."
  }'
```

Analyze the last page without knowing the page count:

```bash
curl -s http://localhost:${API_PORT}/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
    "pages": "last",
    "prompt": "Extract the date and every todo item. Return {\"date\": string|null, \"todos\": string[]}."
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
    "prompt": "Return {\"summary\": string, \"action_items\": string[]} for this page."
  }'
```

Response shape:

```json
[
  {
    "source_url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
    "page": 44,
    "page_count": 45,
    "image_path": "output/page-44.png",
    "model": "llama3.2-vision",
    "result": {
      "date": "September 12, 2026",
      "todos": []
    }
  }
]
```

The `result` field is the JSON parsed from the model response. If the model
does not return valid JSON, the service still returns JSON with `raw_response`
and `parse_error`.

## CLI In Docker

The same pipeline can run as a one-off command:

```bash
docker compose run --rm goodnotes-vlm \
  python main.py "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z" \
  --pages 44 \
  --prompt 'Extract the date and todos. Return {"date": string|null, "todos": string[]}.'
```

Multiple pages:

```bash
docker compose run --rm goodnotes-vlm \
  python main.py "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z" \
  --pages "1,3-5" \
  --prompt 'Return {"page_title": string|null, "notes": string[]}.'
```

Image only:

```bash
docker compose run --rm goodnotes-vlm \
  python main.py "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z" \
  --pages last \
  --just_image
```

## MCP Server

There are two MCP modes:

- **stdio**: Hermes starts the container/process directly.
- **HTTP**: you run the container as a server and Hermes connects to a URL like
  `http://127.0.0.1:5455/mcp`.

For on-demand Docker usage, use stdio. Hermes starts the container when it
starts the MCP server, and `--rm` removes the container when the session closes:

```yaml
mcp_servers:
  goodnotes-vlm:
    command: docker
    args:
      - run
      - --rm
      - -i
      - -e
      - MCP_TRANSPORT=stdio
      - ghcr.io/karunstha/goodnotes-vlm-mcp:latest
    enabled: true
    timeout: 120
    trust: untrusted
    resources: false
    prompts: false
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

```yaml
mcp_servers:
  goodnotes-vlm:
    command: docker
    args:
      - run
      - --rm
      - -i
      - -e
      - MCP_TRANSPORT=stdio
      - -e
      - OLLAMA_URL=http://host.docker.internal:11434
      - -e
      - OLLAMA_MODEL=llama3.2-vision
      - ghcr.io/karunstha/goodnotes-vlm-mcp:latest
```

To use an env file instead:

```yaml
mcp_servers:
  goodnotes-vlm:
    command: docker
    args:
      - run
      - --rm
      - -i
      - --env-file
      - /absolute/path/to/goodnotes.env
      - ghcr.io/karunstha/goodnotes-vlm-mcp:latest
```

Example `goodnotes.env`:

```env
MCP_TRANSPORT=stdio
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2-vision
OUTPUT_DIR=/app/output
BROWSER_TIMEOUT_MS=60000
BROWSER_SETTLE_MS=2000
```

To keep extracted images on the host, mount an output directory:

```yaml
      - -v
      - /absolute/path/to/output:/app/output
```

Use absolute paths in Hermes configs because Docker is launched by Hermes, not
from this project directory.

For your URL-style Hermes config, run the MCP server with Docker:

```bash
docker run --rm \
  -p 5455:5455 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=5455 \
  -e MCP_PATH=/mcp \
  goodnotes-vlm
```

Then use:

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

With Compose, the `goodnotes-mcp` service exposes the same endpoint:

```bash
docker compose up goodnotes-mcp
```

For distribution, the intended flow is an npm launcher that starts the
published Docker image. That lets users configure the MCP server like this:

```yaml
mcp_servers:
  goodnotes-vlm:
    command: npx
    args:
      - -y
      - '@karunstha/goodnotes-vlm-mcp@latest'
    env:
      DOCKER_OLLAMA_URL: http://host.docker.internal:11434
      OLLAMA_MODEL: llama3.2-vision
```

The publish workflow in [.github/workflows/publish.yml](.github/workflows/publish.yml)
builds/pushes the Docker image to GHCR and publishes the npm launcher when you
push a version tag such as `v0.1.0`.

By default, the workflow always publishes the Docker image. The npm launcher is
opt-in: run the workflow manually with `publish_npm=true`, or set a repository
variable named `PUBLISH_NPM` to `true`. Npm publishing needs an `NPM_TOKEN`
repository secret with permission to publish `@karunstha/goodnotes-vlm-mcp`.

Run the MCP server locally:

```bash
workon test
PYTHONPATH=src python -m goodnotes_ocr.mcp_server
```

Example MCP client config:

```json
{
  "mcpServers": {
    "goodnotes-vlm": {
      "command": "python",
      "args": ["-m", "goodnotes_ocr.mcp_server"],
      "env": {
        "PYTHONPATH": "/Users/karskit/Developer/Personal/goodnotes_scrape/src"
      }
    }
  }
}
```

Tools:

- `extract_goodnotes`: VLM extraction, or MCP image content with `just_image: true`
- `extract_goodnotes_image`: always returns MCP `Image` content
- `extract_goodnotes_image_metadata`: returns image path metadata as JSON

Example MCP tool arguments for a direct MCP image:

```json
{
  "url": "https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z",
  "pages": "last"
}
```

## Configuration

Configuration lives in `.env`:

- `OLLAMA_URL`: Ollama base URL, default `http://host.docker.internal:11434`
- `DOCKER_OLLAMA_URL`: Ollama URL used by Docker Compose, default `http://host.docker.internal:11434`
- `OLLAMA_MODEL`: vision model, default `llama3.2-vision`
- `API_PORT`: host port exposed by Docker Compose, default `8000`
- `MCP_TRANSPORT`: `stdio`, `sse`, or `streamable-http`; default in `.env` is `streamable-http`
- `MCP_HOST`: MCP HTTP bind host, default `0.0.0.0`
- `MCP_PORT`: MCP HTTP port, default `5455`
- `MCP_PATH`: streamable HTTP endpoint path, default `/mcp`
- `OUTPUT_DIR`: extracted image directory, default `output`
- `BROWSER_TIMEOUT_MS`: page load timeout, default `60000`
- `BROWSER_SETTLE_MS`: render settle delay, default `2000`
- `MAX_PROBE_PAGE`: fallback page-count probe limit, default `2000`
- `PDF_DPI`: direct PDF render DPI, default `300`
- `VLM_TIMEOUT_SECONDS`: Ollama request timeout, default `120`

Per-request API overrides:

- `model`
- `ollama_url`

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
  --prompt 'Extract the date and todos. Return {"date": string|null, "todos": string[]}.'
```

## Notes

- Pages are 1-based.
- `pages` accepts an integer, a list, `last`, or a string like `1,3-5,last`.
- `just_image` skips the VLM call and extracts page image(s) only.
- Direct PDF URLs are supported and rendered through Poppler.
- GoodNotes can change its web app internals. The page renderer uses broad DOM
  heuristics rather than relying on one private API.
- Shared GoodNotes links are public to anyone with the link. Avoid processing
  sensitive notebooks unless you control the runtime and storage.
