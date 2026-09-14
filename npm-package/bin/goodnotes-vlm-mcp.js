#!/usr/bin/env node

const { spawn } = require("node:child_process");

const image =
  process.env.GOODNOTES_VLM_IMAGE ||
  "ghcr.io/your-github-user/goodnotes-vlm-mcp:latest";

const envKeys = [
  "OLLAMA_MODEL",
  "OUTPUT_DIR",
  "BROWSER_TIMEOUT_MS",
  "BROWSER_SETTLE_MS",
  "VIEWPORT_WIDTH",
  "VIEWPORT_HEIGHT",
  "MAX_PROBE_PAGE",
  "PDF_DPI",
  "VLM_TIMEOUT_SECONDS",
];

const ollamaUrl =
  process.env.DOCKER_OLLAMA_URL ||
  process.env.OLLAMA_URL ||
  "http://host.docker.internal:11434";

const dockerArgs = [
  "run",
  "--rm",
  "-i",
  "--add-host",
  "host.docker.internal:host-gateway",
  "-e",
  `OLLAMA_URL=${ollamaUrl}`,
];

for (const key of envKeys) {
  if (process.env[key]) {
    dockerArgs.push("-e", `${key}=${process.env[key]}`);
  }
}

dockerArgs.push(image);

const child = spawn("docker", dockerArgs, {
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(`Failed to start Docker: ${error.message}`);
  console.error("Install Docker and make sure the Docker daemon is running.");
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
