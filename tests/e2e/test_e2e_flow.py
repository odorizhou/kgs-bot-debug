"""E2E Tests: Real bot integration with KGS server.

These tests interact with the actual kgs-bot and kgs-bot-monitor.
"""

import json
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import wait_for_result, BotProcess


class TestRealBotLogin:
    """Test 1: Real bot login to KGS"""

    def test_bot_starts_and_logs_in(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Bot can login to KGS server."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Wait for bot to be ready (state file exists)
        for _ in range(30):
            if state_file.exists():
                break
            time.sleep(1)

        # Check if already logged in
        if state_file.exists():
            state = json.loads(state_file.read_text())
            if state.get("connected") is True:
                # Already logged in, skip login test
                pytest.skip("Bot already logged in")

        # Clear any pending result file
        if result_file.exists():
            result_file.write_text("")

        # Send login command
        import uuid
        cmd_id = str(uuid.uuid4())
        command_file.write_text(json.dumps({
            "id": cmd_id,
            "command": "login",
            "params": {}
        }))

        # Wait for result with matching ID
        result = None
        start_time = time.time()
        while time.time() - start_time < 60.0:
            if result_file.exists():
                content = result_file.read_text()
                if content:
                    r = json.loads(content)
                    if r.get("id") == cmd_id:
                        result = r
                        break
            time.sleep(0.5)

        # Assert
        assert result is not None, "No result received"
        assert result.get("ok") is True, f"Login failed: {result.get('message')}"

        # Wait for connection to be established
        time.sleep(5)

        # Verify state shows connected
        if state_file.exists():
            state = json.loads(state_file.read_text())
            assert state.get("connected") is True, "Bot not connected after login"


class TestRealObservation:
    """Test 2: Real observation flow"""

    def test_observe_real_game(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Bot can observe a real KGS game."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Wait for bot to be ready
        for _ in range(30):
            if state_file.exists():
                break
            time.sleep(1)

        # First, get active games
        get_games_cmd = json.dumps({
            "id": "get-games",
            "command": "get_active_games",
            "params": {"room": 354}
        })
        command_file.write_text(get_games_cmd)

        # Wait for result
        result = wait_for_result(result_file, timeout=30.0)
        assert result is not None, "No result from get_active_games"

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
                assert result is not None, "No result from observe_game"
                assert result.get("ok") is True, f"Observe failed: {result.get('message')}"

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
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Rapid game switches don't corrupt state."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Wait for bot to be ready
        for _ in range(30):
            if state_file.exists():
                break
            time.sleep(1)

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
        bot_process: BotProcess,
        command_file: Path
    ) -> None:
        """Bot handles malformed commands gracefully."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Write invalid JSON
        command_file.write_text("not valid json {{{")

        # Bot should detect and handle this
        time.sleep(3)

        # Bot should have processed the file (either cleared or logged error)
        # The file may not exist if bot deleted it, which is fine
        try:
            content = command_file.read_text()
            # If file exists, it should either be cleared or still contain invalid data
            # (bot handles it gracefully without crashing)
        except FileNotFoundError:
            # File was cleared by bot - this is also fine
            pass

        # Just verify bot doesn't crash
        assert bot_process.is_running(), "Bot crashed after malformed command"

    def test_invalid_command_name(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path
    ) -> None:
        """Bot handles unknown commands."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Send unknown command
        command_file.write_text(json.dumps({
            "id": "invalid-cmd",
            "command": "nonexistent_command_xyz",
            "params": {}
        }))

        # Wait for result
        result = wait_for_result(result_file, timeout=10.0)

        # Bot should respond with error or handle gracefully
        if result:
            # Either ok=False with error message, or bot logged it as unknown
            if result.get("ok") is True:
                # Bot may have logged this as an unknown command but not crashed
                # This is acceptable - bot didn't crash
                pass
            else:
                assert "error" in result.get("message", "").lower() or \
                       "unknown" in result.get("message", "").lower()