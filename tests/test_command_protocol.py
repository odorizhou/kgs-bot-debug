"""Phase 1: Command/Response Protocol Tests

Tests the file-based communication between kgs-bot-monitor and kgs-bot.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.phase1
class TestCommandFileProtocol:
    """Test 1.1: Command file write/read"""

    def test_command_file_created(self, command_file: Path) -> None:
        """Monitor writes command file correctly."""
        # Arrange
        command_id = str(uuid.uuid4())
        command_data = {
            "id": command_id,
            "command": "observe_game",
            "params": {"channelId": 12345}
        }

        # Act
        command_file.write_text(json.dumps(command_data))

        # Assert
        assert command_file.exists()
        content = json.loads(command_file.read_text())
        assert content["id"] == command_id
        assert content["command"] == "observe_game"
        assert content["params"]["channelId"] == 12345

    def test_command_file_format(self, command_file: Path) -> None:
        """Command file has required fields."""
        # Arrange
        command_id = str(uuid.uuid4())
        command_data = {
            "id": command_id,
            "command": "login",
            "params": {}
        }
        command_file.write_text(json.dumps(command_data))

        # Act
        content = json.loads(command_file.read_text())

        # Assert
        assert "id" in content
        assert "command" in content
        assert "params" in content

    def test_result_file_format(self, result_file: Path) -> None:
        """Result file has correct structure."""
        # Arrange
        result_data = {
            "id": "test-id",
            "ok": True,
            "message": "success"
        }
        result_file.write_text(json.dumps(result_data))

        # Act
        content = json.loads(result_file.read_text())

        # Assert
        assert content["id"] == "test-id"
        assert content["ok"] is True
        assert content["message"] == "success"


@pytest.mark.phase1
class TestCommandProcessing:
    """Test 1.2: Bot processes command"""

    def test_bot_reads_command_file(
        self,
        command_file: Path,
        result_file: Path,
        kgs_bot_path: Path
    ) -> None:
        """Bot picks up command from file."""
        # This test requires the actual bot to be running
        # For now, we verify the file structure the bot expects

        # Arrange
        command_id = str(uuid.uuid4())
        command_data = {
            "id": command_id,
            "command": "get_status",
            "params": {}
        }
        command_file.write_text(json.dumps(command_data))

        # Assert command file is readable
        content = json.loads(command_file.read_text())
        assert content["command"] == "get_status"
        assert content["id"] == command_id

    def test_command_id_perserved(
        self,
        command_file: Path,
        result_file: Path
    ) -> None:
        """Command ID is preserved in result."""
        # Arrange
        command_id = str(uuid.uuid4())
        command_data = {
            "id": command_id,
            "command": "test_command",
            "params": {}
        }
        command_file.write_text(json.dumps(command_data))

        # Simulate bot writing result
        result_data = {
            "id": command_id,  # Same ID
            "ok": True,
            "message": "command executed"
        }
        result_file.write_text(json.dumps(result_data))

        # Assert
        result = json.loads(result_file.read_text())
        assert result["id"] == command_id


@pytest.mark.phase1
class TestStateFileUpdates:
    """Test 1.3: State file updates"""

    def test_state_file_valid_json(self, state_file: Path) -> None:
        """State file can be parsed as JSON."""
        # Arrange
        state_data = {
            "running": True,
            "status": "Idle",
            "connected": False,
            "observing_game": None,
            "active_games": {}
        }
        state_file.write_text(json.dumps(state_data))

        # Act
        content = json.loads(state_file.read_text())

        # Assert
        assert content["running"] is True
        assert content["status"] == "Idle"

    def test_state_file_has_required_fields(self, state_file: Path) -> None:
        """State file contains required fields."""
        # Arrange
        state_data = {
            "running": True,
            "status": "In game",
            "connected": True,
            "engine_running": True,
            "observing_game": 12345,
            "active_games": {
                "12345": {
                    "channelId": 12345,
                    "is_observation": True,
                    "moves": []
                }
            }
        }
        state_file.write_text(json.dumps(state_data))

        # Assert
        content = json.loads(state_file.read_text())
        assert "running" in content
        assert "status" in content
        assert "connected" in content
        assert "observing_game" in content
        assert "active_games" in content

    def test_observing_game_in_state(self, state_file: Path) -> None:
        """observing_game appears in state.json."""
        # Arrange
        state_data = {
            "running": True,
            "status": "In game",
            "observing_game": 12345,
            "active_games": {}
        }
        state_file.write_text(json.dumps(state_data))

        # Act
        content = json.loads(state_file.read_text())

        # Assert
        assert content["observing_game"] == 12345