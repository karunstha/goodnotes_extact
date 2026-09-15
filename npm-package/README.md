# GoodNotes VLM MCP

Thin npm launcher for the GoodNotes VLM MCP server.

It runs the published Docker image and communicates with the MCP client over
stdio. Users only need Node/npm, Docker, and an Ollama server.

## MCP Config

```yaml
mcp_servers:
  goodnotes-vlm:
    command: npx
    args:
      - -y
      - '@karunstha/goodnotes-vlm-mcp@latest'
```

Optional environment:

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

Override the Docker image:

```yaml
env:
  GOODNOTES_VLM_IMAGE: ghcr.io/karunstha/goodnotes-vlm-mcp:latest
```
