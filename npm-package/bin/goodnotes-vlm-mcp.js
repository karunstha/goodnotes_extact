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
const mcpTransport = process.env.MCP_TRANSPORT || "streamable-http";
const mcpHost = process.env.MCP_HOST || "0.0.0.0";
const mcpPort = process.env.MCP_PORT || "5455";
const mcpPath = process.env.MCP_PATH || "/mcp";
const hostPort = process.env.MCP_HOST_PORT || mcpPort;

const dockerArgs = [
  "run",
  "--rm",
  "--stop-timeout",
  "5",
  "--add-host",
  "host.docker.internal:host-gateway",
];

if (mcpTransport === "stdio") {
  dockerArgs.push("-i");
} else {
  dockerArgs.push("-p", `${hostPort}:${mcpPort}`);
}

dockerArgs.push(
  "-e",
  `MCP_TRANSPORT=${mcpTransport}`,
  "-e",
  `MCP_HOST=${mcpHost}`,
  "-e",
  `MCP_PORT=${mcpPort}`,
  "-e",
  `MCP_PATH=${mcpPath}`,
  "-e",
  `OLLAMA_URL=${ollamaUrl}`,
);

for (const key of envKeys) {
  if (process.env[key]) {
    dockerArgs.push("-e", `${key}=${process.env[key]}`);
  }
}

dockerArgs.push(image);

const child = spawn("docker", dockerArgs, {
  stdio: mcpTransport === "stdio" ? ["pipe", "inherit", "inherit"] : "inherit",
});

if (mcpTransport === "stdio" && child.stdin) {
  process.stdin.pipe(child.stdin);

  child.stdin.on("error", (error) => {
    if (error.code !== "EPIPE") {
      console.error(`Docker stdin error: ${error.message}`);
    }
  });
}

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

if (mcpTransport === "stdio") {
  process.stdin.on("end", () => {
    if (child.stdin && !child.stdin.destroyed) {
      child.stdin.end();
    }
    forwardSignal("SIGTERM");
  });

  process.stdin.on("close", () => {
    forwardSignal("SIGTERM");
  });
} else {
  console.error(`GoodNotes MCP listening at http://127.0.0.1:${hostPort}${mcpPath}`);
  if (process.stdin.isTTY) {
    process.stdin.resume();
  }
}
