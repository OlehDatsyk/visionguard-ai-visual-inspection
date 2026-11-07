#!/usr/bin/env python3
"""Cross-platform launcher for local use. Standard library only, so it runs before setup.

    python scripts/start.py            set up if needed, then run the backend and frontend
    python scripts/start.py --check    report prerequisites and configuration, change nothing
    python scripts/start.py --setup    set up without starting the servers

It never deletes data. Existing .env files, databases and uploads are left alone.
"""
import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
VENV = BACKEND / ".venv"
IS_WINDOWS = os.name == "nt"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
MIN_PYTHON = (3, 11)
MIN_NODE = 20


def info(text: str) -> None:
    print(f"[VisionGuard] {text}", flush=True)


def fail(text: str) -> "None":
    print(f"\n[VisionGuard] SETUP PROBLEM\n{text}\n", file=sys.stderr, flush=True)
    raise SystemExit(1)


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    return values


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def node_version() -> int | None:
    node = shutil.which("node")
    if not node:
        return None
    try:
        output = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=20).stdout
        return int(output.strip().lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def check_prerequisites() -> list[str]:
    problems = []
    if sys.version_info[:2] < MIN_PYTHON:
        problems.append(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required (found {sys.version.split()[0]}). https://www.python.org/downloads/")
    if sys.version_info[:2] >= (3, 13):
        info(f"Note: tested on Python 3.12. You have {sys.version.split()[0]}; if a package fails to install, use 3.12.")
    version = node_version()
    if version is None:
        problems.append(f"Node.js {MIN_NODE} or newer is required but was not found. https://nodejs.org/")
    elif version < MIN_NODE:
        problems.append(f"Node.js {MIN_NODE} or newer is required (found {version}). https://nodejs.org/")
    if not shutil.which("npm"):
        problems.append("npm was not found. It is normally installed with Node.js.")
    if IS_WINDOWS and len(str(VENV)) > 160:
        problems.append(
            f"This folder's path is very long ({len(str(VENV))} characters), which stops OpenCV from loading on Windows.\n"
            "Move the project somewhere shorter, for example C:\\Projects\\visionguard."
        )
    return problems


def ensure_env() -> None:
    if ENV_FILE.exists():
        return
    if not ENV_EXAMPLE.is_file():
        fail(".env.example is missing, so .env cannot be created.")
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    text = text.replace("SECRET_KEY=change-me-to-a-long-random-value", f"SECRET_KEY={secrets.token_urlsafe(48)}")
    ENV_FILE.write_text(text, encoding="utf-8")
    info("Created .env with a new random SECRET_KEY. External AI is off by default; edit .env to change settings.")


def run(command: list[str], cwd: Path, what: str, env: dict | None = None) -> None:
    info(what)
    result = subprocess.run(command, cwd=cwd, env=env)
    if result.returncode != 0:
        fail(f"This step failed: {what}\nCommand: {' '.join(str(c) for c in command)}\nRead the messages above for the cause.")


def setup() -> None:
    ensure_env()
    if not VENV_PY.exists():
        info("Creating the Python virtual environment in backend/.venv")
        venv.EnvBuilder(with_pip=True).create(VENV)
    marker = VENV / ".requirements-installed"
    requirements = BACKEND / "requirements.txt"
    if not marker.exists() or marker.read_text() != requirements.read_text():
        run([str(VENV_PY), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", str(requirements)], BACKEND, "Installing backend packages (a few minutes the first time)")
        marker.write_text(requirements.read_text())
    probe = subprocess.run([str(VENV_PY), "-c", "import cv2, onnxruntime"], capture_output=True, text=True)
    if probe.returncode != 0:
        fail(f"OpenCV or ONNX Runtime could not be loaded:\n{probe.stderr.strip()[-400:]}\nIf this mentions a long filename, move the project to a shorter path.")
    download = subprocess.run([str(VENV_PY), "scripts/download_models.py"], cwd=BACKEND)
    if download.returncode != 0:
        info("WARNING: the object detector could not be downloaded. The app still works, and shows detection as unavailable until you re-run this.")
    run([str(VENV_PY), "-m", "alembic", "upgrade", "head"], BACKEND, "Updating the database schema")
    npm = shutil.which("npm") or "npm"
    if not (FRONTEND / "node_modules").is_dir():
        run([npm, "ci", "--no-fund", "--no-audit"], FRONTEND, "Installing frontend packages")


def wait_for(url: str, process: subprocess.Popen, seconds: int = 60) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def start(open_browser: bool) -> int:
    values = read_env_file()
    backend_port = int(os.environ.get("BACKEND_PORT") or values.get("BACKEND_PORT") or 8010)
    frontend_port = int(os.environ.get("FRONTEND_PORT") or values.get("FRONTEND_PORT") or 5173)
    for port, name in ((backend_port, "BACKEND_PORT"), (frontend_port, "FRONTEND_PORT")):
        if not port_free(port):
            fail(f"Port {port} is already used by another program.\nStop that program, or set a different {name} in .env, then try again.")
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    origins = values.get("CORS_ORIGINS", "")
    env["CORS_ORIGINS"] = ",".join(filter(None, [origins, f"http://localhost:{frontend_port}", f"http://127.0.0.1:{frontend_port}"]))
    frontend_env = {**os.environ, "VITE_API_BASE_URL": f"http://127.0.0.1:{backend_port}"}
    npm = shutil.which("npm") or "npm"
    info(f"Starting the backend on port {backend_port}")
    api = subprocess.Popen([str(VENV_PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port)], cwd=BACKEND, env=env)
    processes = [api]
    try:
        if not wait_for(f"http://127.0.0.1:{backend_port}/health/ready", api):
            fail("The backend did not become ready. Read the messages above. Common causes are an invalid .env value or an unreachable DATABASE_URL.")
        info(f"Starting the frontend on port {frontend_port}")
        web = subprocess.Popen([npm, "run", "dev", "--", "--port", str(frontend_port)], cwd=FRONTEND, env=frontend_env)
        processes.append(web)
        if not wait_for(f"http://127.0.0.1:{frontend_port}/", web):
            fail("The frontend did not start. Read the messages above.")
        url = f"http://127.0.0.1:{frontend_port}"
        print(f"\n  VisionGuard AI is running: {url}\n  API documentation:         http://127.0.0.1:{backend_port}/docs\n  Press Ctrl+C here to stop.\n", flush=True)
        if open_browser:
            webbrowser.open(url)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        info("A server stopped unexpectedly. Read the messages above.")
        return 1
    except KeyboardInterrupt:
        info("Stopping")
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up and run VisionGuard AI locally.")
    parser.add_argument("--check", action="store_true", help="report problems without changing anything")
    parser.add_argument("--setup", action="store_true", help="set up without starting the servers")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = parser.parse_args()
    problems = check_prerequisites()
    if args.check:
        values = read_env_file()
        print(f"Python:        {sys.version.split()[0]}")
        print(f"Node.js:       {node_version() or 'not found'}")
        print(f".env:          {'present' if ENV_FILE.exists() else 'missing (it will be created on first start)'}")
        print(f"Virtual env:   {'present' if VENV_PY.exists() else 'missing (it will be created on first start)'}")
        print(f"Model weights: {'present' if (BACKEND / 'model_weights' / 'yolox_tiny.onnx').is_file() else 'missing (they will be downloaded on first start)'}")
        print(f"External AI:   {values.get('AI_PROVIDER') or 'none'}")
        for problem in problems:
            print(f"PROBLEM: {problem}")
        return 1 if problems else 0
    if problems:
        fail("\n".join(problems))
    setup()
    if args.setup:
        info("Setup complete.")
        return 0
    return start(not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
