"""E2E Test Configuration and Fixtures."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

# Paths
E2E_DIR = Path(__file__).parent
COMPOSE_FILE = E2E_DIR / "docker-compose.yml"
ROOT_DIR = E2E_DIR.parent.parent


def run_command(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a shell command and check for success."""
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture(scope="session", autouse=True)
def docker_stack():
    """Start and stop the Docker Compose stack for E2E tests."""
    print("\n[E2E] Starting Docker Compose stack...")

    # Ensure a clean state
    run_command(["docker-compose", "-f", str(COMPOSE_FILE), "down", "-v"], cwd=ROOT_DIR)

    # Ensure images are built and services started
    run_command(["docker-compose", "-f", str(COMPOSE_FILE), "up", "-d", "--build"], cwd=ROOT_DIR)

    try:
        # Wait for services to be healthy
        wait_for_services()
        yield
    except Exception as e:
        print(f"\n[E2E] Error: {e}")
        # Skip teardown on failure to allow debugging if environment variable is set
        if os.environ.get("E2E_KEEP_CONTAINERS") == "1":
            print("[E2E] Keeping containers for debugging.")
            raise
        else:
            print("[E2E] Tearing down after error (use E2E_KEEP_CONTAINERS=1 to keep).")
            run_command(["docker-compose", "-f", str(COMPOSE_FILE), "down", "-v"], cwd=ROOT_DIR)
            raise
    finally:
        if os.environ.get("E2E_KEEP_CONTAINERS") != "1":
            print("\n[E2E] Tearing down Docker Compose stack...")
            run_command(["docker-compose", "-f", str(COMPOSE_FILE), "down", "-v"], cwd=ROOT_DIR)


def wait_for_services(timeout: int = 600):
    """Wait for all services to pass their health checks."""
    print(f"[E2E] Waiting for services to be healthy (timeout {timeout}s)...")
    start_time = time.time()

    # We'll check the main orchestrator (dolores-assistant) which aggregates health of others
    assistant_url = "http://localhost:8000/health"
    ollama_url = "http://localhost:11434/api/tags"

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        try:
            with httpx.Client() as client:
                # 1. Check if Ollama has the model
                try:
                    resp = client.get(ollama_url, timeout=2)
                    if resp.status_code == 200 and "llama3.2" in resp.text:
                        # 2. Check Assistant
                        resp = client.get(assistant_url, timeout=2)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("status") == "ok":
                                services = data.get("services", {})
                                if all(s == "healthy" for s in services.values()):
                                    print(f"[E2E] All services healthy after {elapsed}s!")
                                    return
                                else:
                                    print(f"[E2E] {elapsed}s: Services not healthy: {services}")
                            else:
                                print(f"[E2E] {elapsed}s: Assistant status: {data.get('status')}")
                        else:
                            print(f"[E2E] {elapsed}s: Assistant returned {resp.status_code}")
                    else:
                        print(f"[E2E] {elapsed}s: Waiting for Ollama model...")
                except Exception:
                    print(f"[E2E] {elapsed}s: Waiting for infrastructure...")
        except Exception:
            pass

        time.sleep(10)

    raise TimeoutError(f"Services failed to become healthy within {timeout}s")


@pytest.fixture
def client():
    """Returns a client to communicate with the dolores-assistant."""
    return httpx.Client(base_url="http://localhost:8000", timeout=120)
