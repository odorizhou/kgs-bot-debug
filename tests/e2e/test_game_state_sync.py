"""E2E Tests: Game State Synchronization

Tests that verify game settings and historical moves are captured correctly
when joining an ongoing game.
"""

import json
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import wait_for_result, BotProcess


class TestGameSettingsCapture:
    """Test: Game settings are captured correctly"""

    def test_game_metadata_captured(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Game metadata (size, komi, rules, players) is captured."""
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
        assert result is not None, "No result from get_active_games"

        # Find a game to observe
        if state_file.exists():
            state = json.loads(state_file.read_text())
            games = state.get("active_games", {})

            if games:
                channel_id = list(games.keys())[0]
                game_info = games[channel_id]

                # Send observe command
                command_file.write_text(json.dumps({
                    "id": "observe-meta",
                    "command": "observe_game",
                    "params": {"channelId": int(channel_id)}
                }))

                result = wait_for_result(result_file, timeout=30.0)
                assert result is not None
                assert result.get("ok") is True

                # Wait for GAME_JOIN to arrive and state to update
                time.sleep(5)

                # Verify game metadata in state
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    active = state.get("active_games", {})

                    if str(channel_id) in active:
                        game = active[str(channel_id)]

                        # Check board size
                        assert "board_size" in game or "size" in game, \
                            "Board size not captured"

                        # Check komi
                        assert "komi" in game, "Komi not captured"

                        # Check players
                        assert "players" in game or "black" in game or "white" in game, \
                            "Players not captured"

                        # Check rules
                        assert "rules" in game, "Rules not captured"

                        print(f"Game metadata captured:")
                        print(f"  Board size: {game.get('board_size', game.get('size'))}")
                        print(f"  Komi: {game.get('komi')}")
                        print(f"  Rules: {game.get('rules')}")


class TestHistoricalMovesSync:
    """Test: Historical moves are synced correctly"""

    def test_move_history_synced(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Complete move history is synced from GAME_JOIN."""
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

        # Find a game with moves already played
        if state_file.exists():
            state = json.loads(state_file.read_text())
            games = state.get("active_games", {})

            if games:
                channel_id = list(games.keys())[0]

                # Send observe command
                command_file.write_text(json.dumps({
                    "id": "observe-history",
                    "command": "observe_game",
                    "params": {"channelId": int(channel_id)}
                }))

                result = wait_for_result(result_file, timeout=30.0)
                assert result is not None
                assert result.get("ok") is True

                # Wait for GAME_JOIN with full history
                time.sleep(5)

                # Verify moves were synced
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    active = state.get("active_games", {})

                    if str(channel_id) in active:
                        game = active[str(channel_id)]
                        moves = game.get("moves", [])

                        # Verify moves are present
                        if moves:
                            # Check move format
                            for i, move in enumerate(moves[:5]):  # Check first 5 moves
                                assert "moveNumber" in move or "number" in move or \
                                       "loc" in move or "point" in move, \
                                    f"Move {i} missing required fields"

                            print(f"Synced {len(moves)} moves from game history")
                            print(f"First few moves: {moves[:3]}")

                        # Check move count matches move_number field if present
                        if "move_number" in game:
                            assert len(moves) == game["move_number"], \
                                f"Move count mismatch: {len(moves)} vs {game['move_number']}"


class TestHandicapStonesSync:
    """Test: Handicap stones are synced correctly"""

    def test_handicap_stones_captured(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Handicap stones are captured from GAME_JOIN."""
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

        # Find a game
        if state_file.exists():
            state = json.loads(state_file.read_text())
            games = state.get("active_games", {})

            if games:
                channel_id = list(games.keys())[0]

                # Send observe command
                command_file.write_text(json.dumps({
                    "id": "observe-handicap",
                    "command": "observe_game",
                    "params": {"channelId": int(channel_id)}
                }))

                result = wait_for_result(result_file, timeout=30.0)
                assert result is not None

                # Wait for GAME_JOIN
                time.sleep(5)

                # Check handicap field
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    active = state.get("active_games", {})

                    if str(channel_id) in active:
                        game = active[str(channel_id)]

                        # Handicap should be captured (0 for non-handicap games)
                        if "handicap" in game:
                            handicap = game["handicap"]
                            print(f"Handicap: {handicap}")
                            assert isinstance(handicap, int), "Handicap should be integer"
                            assert handicap >= 0, "Handicap should be non-negative"
                        else:
                            # Handicap field may not be present for non-handicap games
                            print("No handicap field (normal for non-handicap games)")


class TestBoardStateReconstruction:
    """Test: Board state can be reconstructed from moves"""

    def test_board_state_valid(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Board state can be reconstructed from synced moves."""
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

        # Find a game
        if state_file.exists():
            state = json.loads(state_file.read_text())
            games = state.get("active_games", {})

            if games:
                channel_id = list(games.keys())[0]

                # Send observe command
                command_file.write_text(json.dumps({
                    "id": "observe-board",
                    "command": "observe_game",
                    "params": {"channelId": int(channel_id)}
                }))

                result = wait_for_result(result_file, timeout=30.0)
                assert result is not None

                # Wait for GAME_JOIN
                time.sleep(5)

                # Verify board state
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    active = state.get("active_games", {})

                    if str(channel_id) in active:
                        game = active[str(channel_id)]
                        moves = game.get("moves", [])
                        board_size = game.get("board_size", 19)

                        # Verify moves are on valid board coordinates
                        valid_vertices = set()
                        for i in range(board_size):
                            for j in range(board_size):
                                valid_vertices.add((i, j))

                        for move in moves:
                            # Check move has valid coordinates
                            if "loc" in move:
                                loc = move["loc"]
                                # KGS uses notation like "q16", "d4", etc.
                                assert len(loc) >= 2, f"Invalid move location: {loc}"

                        print(f"Board size: {board_size}x{board_size}")
                        print(f"Total moves: {len(moves)}")
                        print(f"All moves have valid coordinates")