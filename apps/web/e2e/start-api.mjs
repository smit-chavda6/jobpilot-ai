// Starts a throwaway API for Playwright: fresh SQLite DB, mock AI provider, inline tasks.
// Used by playwright.config.ts when E2E_API_URL is not set (CI and local runs).
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const apiDir = resolve(here, "../../api");
const varDir = join(apiDir, "var", "e2e");
rmSync(varDir, { recursive: true, force: true });
mkdirSync(varDir, { recursive: true });

const candidates = [join(apiDir, ".venv", "Scripts", "python.exe"), join(apiDir, ".venv", "bin", "python")];
const python = process.env.E2E_PYTHON ?? candidates.find(existsSync) ?? "python";
const port = process.env.E2E_API_PORT ?? "8001";
const env = {
  ...process.env,
  APP_ENV: "test",
  DATABASE_URL: `sqlite+aiosqlite:///${join(varDir, "e2e.db").replace(/\\/g, "/")}`,
  UPLOAD_DIR: join(varDir, "uploads"),
  JWT_SECRET: "e2e-secret-e2e-secret-e2e-secret-e2e-secret",
  ENCRYPTION_KEY: "0Q1xKk8m1z6mX3cF4C7xg0bQ7XcH9vR2y5k3oW8sJpU=",
  LLM_PROVIDER: "mock",
  INLINE_TASKS: "true",
  CORS_ORIGINS: "http://localhost:5174",
};

const migrate = spawnSync(python, ["-m", "alembic", "upgrade", "head"], { cwd: apiDir, env, stdio: "inherit" });
if (migrate.status !== 0) process.exit(migrate.status ?? 1);

const server = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port], { cwd: apiDir, env, stdio: "inherit" });
const stop = () => server.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
server.on("exit", (code) => process.exit(code ?? 0));
