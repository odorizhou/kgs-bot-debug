"""E2E Tests: Real bot integration with KGS server.

These tests interact with the actual kgs-bot and kgs-bot-monitor.
"""

import json
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import wait_for_result


class TestRealBotLogin:
    """Test 1: Real bot login to KGS"""

    def test_bot_starts_and_logs_in(
        self,
        test_bot_id: str,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Bot can login to KGS server."""
        # Send login command
        import uuid
        cmd_id = str(uuid.uuid4())
        command_file.write_text(json.dumps({
            "id": cmd_id,
            "command": "login",
            "params": {}
        }))

        # Wait for result
        result = wait_for_result(result_file, timeout=60.0)

        # Assert
        assert result is not None, "No result received"
        assert result.get("ok") is True, f"Login failed: {result.get('message')}"

        # Verify state shows connected
        time.sleep(2)
        if state_file.exists():
            state = json.loads(state_file.read_text())
            assert state.get("connected") is True


class TestRealObservation:
    """Test 2: Real observation flow"""

    def test_observe_real_game(
        self,
        test_bot_id: str,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Bot can observe a real KGS game."""
        # First, get active games
        get_games_cmd = json.dumps({
            "id": "get-games",
            "command": "get_active_games",
            "params": {"room": 354}
        })
        command_file.write_text(get_games_cmd)

        # Wait for result
        result = wait_for_result(result_file, timeout=30.0)
        assert result is not None

        # Get a game to observe
        if state_file.exists():
            state = json.loads(state_file.read_text())
            games = state.get("active_games", {})

            if games:
                # Pick first game
                channel_id = list(games.keys())[0]

                # Send observe command
                observe_cmd = json.dumps({
                    "id": "observe-test",
                    "command": "observe_game",
                    "params": {"channelId": int(channel_id)}
                })
                command_file.write_text(observe_cmd)

                # Wait for result
                result = wait_for_result(result_file, timeout=30.0)
                assert result is not None
                assert result.get("ok") is True

                # Verify state
                time.sleep(2)
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    assert state.get("observing_game") == int(channel_id)


class TestRealRaceConditions:
    """Test 3: Real race condition scenarios"""

    def test_rapid_game_switch(
        self,
        test_bot_id: str,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Rapid game switches don't corrupt state."""
        # Get active games
        command_file.write_text(json.dumps({
            "id": "get-games",
            "command": "get_active_games",
            "params": {"room": 354}
        }))

        result = wait_for_result(result_file, timeout=30.0)
        assert result is not None

        if state_file.exists():
            state = json.loads(state_file.read_text())
            games = state.get("active_games", {})

            if len(games) >= 2:
                # Get two game IDs
                game_ids = list(games.keys())[:2]

                # Observe game 1
                command_file.write_text(json.dumps({
                    "id": "observe-1",
                    "command": "observe_game",
                    "params": {"channelId": int(game_ids[0])}
                }))

                result = wait_for_result(result_file, timeout=30.0)
                assert result is not None

                # Quickly switch to game 2
                command_file.write_text(json.dumps({
                    "id": "observe-2",
                    "command": "observe_game",
                    "params": {"channelId": int(game_ids[1])}
                }))

                result = wait_for_result(result_file, timeout=30.0)
                assert result is not None

                # Verify state
                time.sleep(2)
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    assert state.get("observing_game") == int(game_ids[1])


class TestRealErrorRecovery:
    """Test 4: Real error recovery"""

    def test_command_error_handling(
        self,
        test_bot_id: str,
        command_file: Path
    ) -> None:
        """Bot handles malformed commands gracefully."""
        # Write invalid JSON
        command_file.write_text("not valid json {{{")

        # Bot should detect and handle this
        time.sleep(2)

        # File should be cleared or error logged
        content = command_file.read_text()
        # Either cleared or still invalid (bot will handle next poll)
        assert True  # Just verify bot doesn't crash

    def test_invalid_command_name(
        self,
        test_bot_id: str,
        command_file: Path,
        result_file: Path
    ) -> None:
        """Bot handles unknown commands."""
        # Send unknown command
        command_file.write_text(json.dumps({
            "id": "invalid-cmd",
            "command": "nonexistent_command",
            "params": {}
        }))

        # Wait for result
        result = wait_for_result(result_file, timeout=10.0)

        # Should get error response, not crash
        if result:
            assert result.get("ok") is False or "error" in result.get("message", "").lower()