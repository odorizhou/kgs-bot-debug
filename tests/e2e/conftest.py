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
TEST_RUN_DIR = KGS_BOT_PATH / "run"  # Bot writes to its own run dir
TEST_LOGS_DIR = KGS_BOT_PATH / "logs"


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

        # Create env file for test - must be in KGS_BOT_PATH/config/
        config_dir = KGS_BOT_PATH / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        env_file = config_dir / f"{self.bot_id}.env"
        env_content = f"""BOT_MODE=main
BOT_AUTO_START=false
KGS_USERNAME={KGS_USERNAME}
KGS_PASSWORD={KGS_PASSWORD}
KGS_BOT_BASEDIR=/workspace
KGS_ROOM_ID={KGS_ROOM_ID}
KGS_PRIVATE_MODE=false
# Use existing analysis daemon (connects to /run/ddos_analysis.sock)
ANALYSIS_DAEMON_ENABLED=true
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
        time.sleep(3)
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


@pytest.fixture(autouse=True)
def cleanup_command_files(test_bot_id: str):
    """Clean up command file before each test to prevent stale commands."""
    from pathlib import Path
    import time

    TEST_RUN_DIR = Path("/workspace/Kgs-bot/run")
    command_file = TEST_RUN_DIR / f"{test_bot_id}_command.json"
    result_file = TEST_RUN_DIR / f"{test_bot_id}_command_result.json"

    # Wait for any pending bot processing to complete
    time.sleep(0.5)

    # Only clear command file - let result file be handled by command ID matching
    if command_file.exists():
        command_file.write_text("")

    yield


def log_game_data(test_name: str, game_data: dict, channel_id: str, moves: list = None):
    """Log game data to a persistent file."""
    import datetime

    logs_dir = Path("/workspace/kgs-bot-debug/logs/e2e_test_bot/game-data")
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{test_name}_{timestamp}.json"

    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "test_name": test_name,
        "channel_id": channel_id,
        "game_data": game_data,
        "moves_count": len(moves) if moves else 0
    }

    if moves:
        log_entry["moves"] = moves

    log_file.write_text(json.dumps(log_entry, indent=2))
    print(f"\n[LOG] Game data saved to: {log_file}")

    # Also append to a summary file
    summary_file = logs_dir / "summary.txt"
    summary_line = f"\n{datetime.datetime.now().isoformat()} | {test_name} | Channel {channel_id} | Moves: {len(moves) if moves else 0}\n"

    # Read existing summary and append
    if summary_file.exists():
        summary_file.write_text(summary_file.read_text() + summary_line)
    else:
        summary_file.write_text("=" * 60 + summary_line)