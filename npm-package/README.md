# GoodNotes VLM MCP

Thin npm launcher for the GoodNotes VLM MCP server Docker image.

It starts the published Docker image as a streamable HTTP MCP server. Users
only need Node/npm, Docker, and an Ollama server.

## Start The Server

```bash
npx -y @karunstha/goodnotes-vlm-mcp@latest
```

The default endpoint is:

```text
http://127.0.0.1:5455/mcp
```

Use that URL in your MCP client config:

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

Optional environment:

```bash
DOCKER_OLLAMA_URL=http://host.docker.internal:11434 \
OLLAMA_MODEL=llama3.2-vision \
MCP_HOST_PORT=5455 \
npx -y @karunstha/goodnotes-vlm-mcp@latest
```

Override the Docker image:

```bash
GOODNOTES_VLM_IMAGE=ghcr.io/karunstha/goodnotes-vlm-mcp:latest \
npx -y @karunstha/goodnotes-vlm-mcp@latest
```
