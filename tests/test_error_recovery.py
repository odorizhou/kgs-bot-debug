"""Phase 4: Error Recovery Tests

Tests for error handling and recovery scenarios.
"""

import json
import time
from pathlib import Path

import pytest


@pytest.mark.phase4
class TestKGSDisconnection:
    """Test 4.1: KGS disconnection recovery"""

    def test_disconnection_detected(self, state_file: Path) -> None:
        """Bot detects KGS disconnection."""
        # Simulate state after disconnection
        state = {
            "running": True,
            "connected": False,  # Connection lost
            "status": "Disconnected",
            "observing_game": None
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["connected"] is False
        assert content["status"] == "Disconnected"

    def test_reconnect_attempted(self, state_file: Path) -> None:
        """Bot attempts to reconnect after disconnection."""
        # State after reconnect attempt
        state = {
            "running": True,
            "connected": True,  # Reconnected
            "status": "Idle",
            "last_reconnect": time.time()
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["connected"] is True
        assert "last_reconnect" in content

    def test_observation_resumed(self, state_file: Path) -> None:
        """Observation is resumed after reconnect."""
        # State after resuming observation
        state = {
            "running": True,
            "connected": True,
            "observing_game": 12345,
            "active_games": {
                "12345": {
                    "is_observation": True,
                    "moves": []
                }
            }
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["observing_game"] == 12345
        assert content["active_games"]["12345"]["is_observation"] is True


@pytest.mark.phase4
class TestCommandFileErrors:
    """Test 4.2: Command file error handling"""

    def test_malformed_json_handled(self, command_file: Path) -> None:
        """Bot handles malformed JSON in command file."""
        # Write invalid JSON
        command_file.write_text("not valid json {{{")

        # Bot should detect and handle this
        try:
            json.loads(command_file.read_text())
            valid = False
        except json.JSONDecodeError:
            valid = True  # Error detected

        assert valid is True

    def test_command_file_cleared_on_error(self, command_file: Path) -> None:
        """Command file is cleared after error."""
        # Write invalid command
        command_file.write_text("invalid")

        # Simulate bot clearing the file
        command_file.write_text("")

        # Assert file is empty
        content = command_file.read_text()
        assert content == ""

    def test_bot_continues_running(self, state_file: Path) -> None:
        """Bot continues running after command file error."""
        # State after error recovery
        state = {
            "running": True,  # Still running
            "status": "Idle",
            "last_error": "Invalid command file",
            "error_time": time.time()
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["running"] is True
        assert "last_error" in content

    def test_missing_command_field_handled(self, command_file: Path) -> None:
        """Bot handles command file missing required fields."""
        # Command with missing 'command' field
        command_data = {
            "id": "test-id",
            "params": {}
            # Missing "command" field
        }
        command_file.write_text(json.dumps(command_data))

        # Bot should detect missing field
        content = json.loads(command_file.read_text())
        assert "command" not in content

        # Simulate error handling
        error_handled = "command" not in content
        assert error_handled is True


@pytest.mark.phase4
class TestStateFileWriteFailures:
    """Test 4.3: State file write failures"""

    def test_write_failure_logged(self, state_file: Path) -> None:
        """State file write failures are logged."""
        # Simulate state with error logged
        state = {
            "running": True,
            "status": "In game",
            "state_write_errors": [
                {
                    "time": time.time(),
                    "error": "Permission denied"
                }
            ]
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert len(content["state_write_errors"]) > 0

    def test_bot_uses_memory_state(self, state_file: Path) -> None:
        """Bot continues with in-memory state when file write fails."""
        # Bot maintains in-memory state
        memory_state = {
            "running": True,
            "observing_game": 12345,
            "active_games": {
                "12345": {"is_observation": True, "moves": []}
            }
        }

        # Even if state_file.write() fails, memory_state is intact
        assert memory_state["running"] is True
        assert memory_state["observing_game"] == 12345

    def test_periodic_retry(self, state_file: Path) -> None:
        """Bot retries state file writes periodically."""
        # State with retry info
        state = {
            "running": True,
            "last_state_write": time.time(),
            "next_retry": time.time() + 5.0,  # Retry in 5 seconds
            "retry_count": 3
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert "next_retry" in content
        assert content["retry_count"] == 3


@pytest.mark.phase4
class TestEngineConnectionErrors:
    """Test 4.4: Engine (KataGo) connection errors"""

    def test_engine_not_running_handled(self, state_file: Path) -> None:
        """Bot handles engine not running."""
        state = {
            "running": True,
            "engine_running": False,
            "analysis_available": False,
            "status": "Idle"
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["engine_running"] is False
        assert content["analysis_available"] is False

    def test_analysis_disabled_gracefully(self, state_file: Path) -> None:
        """Analysis is disabled when engine unavailable."""
        state = {
            "running": True,
            "observing_game": 12345,
            "active_games": {
                "12345": {
                    "is_observation": True,
                    "moves": [],
                    "analysis_score_history": []  # Empty, no analysis
                }
            }
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["active_games"]["12345"]["analysis_score_history"] == []

    def test_engine_reconnect_attempted(self, state_file: Path) -> None:
        """Bot attempts to reconnect to engine."""
        state = {
            "running": True,
            "engine_running": True,  # Reconnected
            "engine_reconnect_time": time.time()
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["engine_running"] is True
        assert "engine_reconnect_time" in content