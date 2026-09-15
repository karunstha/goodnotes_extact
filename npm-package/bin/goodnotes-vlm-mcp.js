#!/usr/bin/env node

const { spawn } = require("node:child_process");

const image =
  process.env.GOODNOTES_VLM_IMAGE ||
  "ghcr.io/karunstha/goodnotes-vlm-mcp:latest";

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
const mcpTransport = process.env.MCP_TRANSPORT || "stdio";

const dockerArgs = [
  "run",
  "--rm",
  "-i",
  "--stop-timeout",
  "5",
  "--add-host",
  "host.docker.internal:host-gateway",
  "-e",
  `MCP_TRANSPORT=${mcpTransport}`,
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

let shuttingDown = false;

function forwardSignal(signal) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  if (!child.killed) {
    child.kill(signal);
  }
  setTimeout(() => {
    if (!child.killed) {
      child.kill("SIGKILL");
    }
  }, 5000).unref();
}

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

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => forwardSignal(signal));
}
