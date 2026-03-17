"""E2E test fixtures for real bot integration."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Generator, Optional

import pytest


# Real bot configuration from ddos.env
KGS_USERNAME = "DDOS"
KGS_PASSWORD = "khzge8"
KGS_ROOM_ID = 354

# Paths
KGS_BOT_PATH = Path("/workspace/Kgs-bot")
MONITOR_PATH = Path("/workspace/kgs-bot-monitor")
TEST_RUN_DIR = Path("/workspace/kgs-bot-debug/run")
TEST_LOGS_DIR = Path("/workspace/kgs-bot-debug/logs")


class BotProcess:
    """Manages a real bot process for E2E testing."""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.process: Optional[subprocess.Popen] = None
        self.run_dir = TEST_RUN_DIR
        self.logs_dir = TEST_LOGS_DIR / bot_id

    def start(self) -> bool:
        """Start the bot process."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Create env file for test
        env_file = self.run_dir / f"{self.bot_id}.env"
        env_content = f"""
BOT_MODE=main
BOT_AUTO_START=false
KGS_USERNAME={KGS_USERNAME}
KGS_PASSWORD={KGS_PASSWORD}
KGS_BOT_BASEDIR=/workspace
KGS_ROOM_ID={KGS_ROOM_ID}
KGS_PRIVATE_MODE=false
"""
        env_file.write_text(env_content)

        # Start bot
        cmd = [
            "python3",
            str(KGS_BOT_PATH / "run_bot.py"),
            self.bot_id
        ]

        self.process = subprocess.Popen(
            cmd,
            stdout=open(self.logs_dir / "stdout.log", "a"),
            stderr=open(self.logs_dir / "stderr.log", "a"),
            cwd=str(KGS_BOT_PATH)
        )

        # Wait for bot to start
        time.sleep(2)
        return self.is_running()

    def is_running(self) -> bool:
        """Check if bot process is running."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def stop(self):
        """Stop the bot process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def __enter__(self) -> "BotProcess":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class MonitorProcess:
    """Manages a real monitor process for E2E testing."""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None

    def start(self) -> bool:
        """Start the monitor process."""
        cmd = ["node", "backend/src/app.js"]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(MONITOR_PATH / "backend")
        )

        time.sleep(2)
        return self.is_running()

    def is_running(self) -> bool:
        """Check if monitor process is running."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def stop(self):
        """Stop the monitor process."""
        if self.process:
            self.process.terminate()
            self.process = None


@pytest.fixture(scope="session")
def test_bot_id() -> str:
    """Return test bot ID."""
    return "e2e_test_bot"


@pytest.fixture(scope="session")
def bot_process(test_bot_id: str) -> Generator[BotProcess, None, None]:
    """Start and stop real bot process."""
    bot = BotProcess(test_bot_id)
    bot.start()
    yield bot
    bot.stop()


@pytest.fixture(scope="session")
def monitor_process() -> Generator[MonitorProcess, None, None]:
    """Start and stop real monitor process."""
    monitor = MonitorProcess()
    monitor.start()
    yield monitor
    monitor.stop()


@pytest.fixture
def command_file(test_bot_id: str) -> Path:
    """Return path to command file."""
    return TEST_RUN_DIR / f"{test_bot_id}_command.json"


@pytest.fixture
def result_file(test_bot_id: str) -> Path:
    """Return path to result file."""
    return TEST_RUN_DIR / f"{test_bot_id}_command_result.json"


@pytest.fixture
def state_file(test_bot_id: str) -> Path:
    """Return path to state file."""
    return TEST_RUN_DIR / f"{test_bot_id}_state.json"


def send_command(command_file: Path, command: str, params: dict = None) -> str:
    """Send a command to the bot."""
    import uuid

    cmd_data = {
        "id": str(uuid.uuid4()),
        "command": command,
        "params": params or {}
    }
    command_file.write_text(json.dumps(cmd_data))
    return cmd_data["id"]


def wait_for_result(result_file: Path, timeout: float = 30.0) -> Optional[dict]:
    """Wait for command result."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if result_file.exists():
            content = result_file.read_text()
            if content:
                return json.loads(content)
        time.sleep(0.5)
    return None


def wait_for_state(state_file: Path, condition, timeout: float = 30.0) -> bool:
    """Wait for state to match condition."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if state_file.exists():
            content = json.loads(state_file.read_text())
            if condition(content):
                return True
        time.sleep(0.5)
    return False


@pytest.fixture
def send_cmd(send_command):
    """Convenience fixture for sending commands."""
    return send_command


@pytest.fixture
def wait_result(wait_for_result):
    """Convenience fixture for waiting for results."""
    return wait_result


@pytest.fixture
def wait_state(wait_for_state):
    """Convenience fixture for waiting for state."""
    return wait_state