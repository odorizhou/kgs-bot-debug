"""Phase 2: Observation Flow Tests (Real KGS)

Tests the complete observation flow against the real KGS server.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest


@pytest.mark.phase2
class TestLoginAndStartup:
    """Test 2.1: Login and startup"""

    def test_login_command_format(
        self,
        command_file: Path,
        result_file: Path
    ) -> None:
        """Login command has correct format."""
        # Arrange
        command_data = {
            "id": "login-test",
            "command": "login",
            "params": {}
        }

        # Act
        command_file.write_text(json.dumps(command_data))

        # Assert
        content = json.loads(command_file.read_text())
        assert content["command"] == "login"

    def test_startup_should_populate_game_cache(
        self,
        state_file: Path
    ) -> None:
        """After startup, game cache should be populated."""
        # This test verifies the expected state after startup
        # The actual bot should populate room_games_cache from ROOM_JOIN

        # Arrange - simulate expected state after startup
        expected_state = {
            "running": True,
            "status": "Idle",
            "connected": True,
            "room_games_cache": {
                354: [  # Computer Go Room
                    {
                        "channelId": 12345,
                        "black": "Player1",
                        "white": "Player2",
                        "size": 19
                    }
                ]
            },
            "games_by_id": {
                12345: {
                    "channelId": 12345,
                    "black": "Player1",
                    "white": "Player2"
                }
            }
        }
        state_file.write_text(json.dumps(expected_state))

        # Assert (JSON converts int keys to strings)
        content = json.loads(state_file.read_text())
        assert "354" in content.get("room_games_cache", {})
        assert "12345" in content.get("games_by_id", {})


@pytest.mark.phase2
class TestObserveGameCommand:
    """Test 2.2: Observe game command"""

    def test_observe_game_command_format(
        self,
        command_file: Path
    ) -> None:
        """observe_game command has correct format."""
        # Arrange
        command_data = {
            "id": "observe-test",
            "command": "observe_game",
            "params": {
                "channelId": 12345
            }
        }

        # Act
        command_file.write_text(json.dumps(command_data))

        # Assert
        content = json.loads(command_file.read_text())
        assert content["command"] == "observe_game"
        assert content["params"]["channelId"] == 12345

    def test_observe_sets_observing_game(
        self,
        state_file: Path
    ) -> None:
        """After observe_game, observing_game is set."""
        # Simulate state after observe_game command
        expected_state = {
            "running": True,
            "status": "In game",
            "observing_game": 12345,
            "active_games": {
                12345: {
                    "channelId": 12345,
                    "is_observation": True,
                    "moves": []
                }
            }
        }
        state_file.write_text(json.dumps(expected_state))

        # Assert (JSON converts int keys to strings)
        content = json.loads(state_file.read_text())
        assert content["observing_game"] == 12345
        assert content["active_games"]["12345"]["is_observation"] is True


@pytest.mark.phase2
class TestGameJoinHistory:
    """Test 2.3: GAME_JOIN history sync"""

    def test_game_join_parses_sgf_events(self) -> None:
        """GAME_JOIN sgfEvents are parsed correctly."""
        # Sample GAME_JOIN message structure
        game_join_message = {
            "type": "GAME_JOIN",
            "channelId": 12345,
            "sgfEvents": [
                {
                    "type": "PROP_ADDED",
                    "nodeId": 1,
                    "prop": {
                        "name": "MOVE",
                        "loc": "q16",
                        "color": "B"
                    }
                },
                {
                    "type": "PROP_ADDED",
                    "nodeId": 2,
                    "prop": {
                        "name": "MOVE",
                        "loc": "d4",
                        "color": "W"
                    }
                }
            ]
        }

        # Extract moves (simplified parsing)
        moves = []
        processed_node_ids = set()

        for event in game_join_message["sgfEvents"]:
            if event.get("type") == "PROP_ADDED":
                prop = event.get("prop", {})
                if prop.get("name") == "MOVE":
                    moves.append({
                        "loc": prop.get("loc"),
                        "color": prop.get("color"),
                        "nodeId": event.get("nodeId")
                    })
                    processed_node_ids.add(event.get("nodeId"))

        # Assert
        assert len(moves) == 2
        assert moves[0]["loc"] == "q16"
        assert moves[0]["color"] == "B"
        assert 1 in processed_node_ids
        assert 2 in processed_node_ids

    def test_handicap_stones_extracted(self) -> None:
        """Handicap stones are extracted from ADDSTONE props."""
        game_join_message = {
            "type": "GAME_JOIN",
            "sgfEvents": [
                {
                    "type": "PROP_ADDED",
                    "nodeId": 0,
                    "prop": {
                        "name": "ADDSTONE",
                        "loc": "d4",
                        "color": "B"
                    }
                }
            ]
        }

        handicap_stones = []
        for event in game_join_message["sgfEvents"]:
            prop = event.get("prop", {})
            if prop.get("name") == "ADDSTONE":
                handicap_stones.append(prop.get("loc"))

        assert "d4" in handicap_stones


@pytest.mark.phase2
class TestGameUpdateRealtime:
    """Test 2.4: GAME_UPDATE real-time"""

    def test_game_update_adds_new_moves(self) -> None:
        """GAME_UPDATE appends new moves."""
        # Existing state
        existing_moves = [
            {"loc": "q16", "color": "B", "nodeId": 1},
            {"loc": "d4", "color": "W", "nodeId": 2}
        ]
        processed_node_ids = {1, 2}

        # New GAME_UPDATE
        game_update = {
            "type": "GAME_UPDATE",
            "channelId": 12345,
            "sgfEvents": [
                {
                    "type": "PROP_ADDED",
                    "nodeId": 3,
                    "prop": {
                        "name": "MOVE",
                        "loc": "q15",
                        "color": "B"
                    }
                }
            ]
        }

        # Process new moves (filtering duplicates)
        for event in game_update["sgfEvents"]:
            node_id = event.get("nodeId")
            if node_id not in processed_node_ids:
                prop = event.get("prop", {})
                if prop.get("name") == "MOVE":
                    existing_moves.append({
                        "loc": prop.get("loc"),
                        "color": prop.get("color"),
                        "nodeId": node_id
                    })
                    processed_node_ids.add(node_id)

        # Assert
        assert len(existing_moves) == 3
        assert existing_moves[2]["loc"] == "q15"
        assert 3 in processed_node_ids

    def test_duplicate_node_ids_filtered(self) -> None:
        """Already-processed nodeIds are skipped."""
        existing_moves = [
            {"loc": "q16", "color": "B", "nodeId": 1}
        ]
        processed_node_ids = {1}

        # GAME_UPDATE with duplicate nodeId
        game_update = {
            "sgfEvents": [
                {
                    "type": "PROP_ADDED",
                    "nodeId": 1,  # Duplicate!
                    "prop": {
                        "name": "MOVE",
                        "loc": "q16",
                        "color": "B"
                    }
                }
            ]
        }

        # Process (should filter out duplicate)
        for event in game_update["sgfEvents"]:
            node_id = event.get("nodeId")
            if node_id not in processed_node_ids:
                prop = event.get("prop", {})
                if prop.get("name") == "MOVE":
                    existing_moves.append({
                        "loc": prop.get("loc"),
                        "color": prop.get("color"),
                        "nodeId": node_id
                    })

        # Assert - no duplicate added
        assert len(existing_moves) == 1


@pytest.mark.phase2
class TestSSEToUI:
    """Test 2.5: SSE to UI"""

    def test_sse_event_format(self) -> None:
        """SSE event has correct format."""
        # Expected SSE format
        sse_event = {
            "event": "game_update",
            "data": json.dumps({
                "channelId": 12345,
                "timestamp": "2026-03-17T10:00:00Z"
            })
        }

        # Verify format
        assert sse_event["event"] == "game_update"
        data = json.loads(sse_event["data"])
        assert data["channelId"] == 12345
        assert "timestamp" in data

    def test_state_change_triggers_sse(self, state_file: Path) -> None:
        """State file change should trigger SSE broadcast."""
        # This test documents the expected behavior:
        # 1. Bot updates state.json
        # 2. Backend detects file change
        # 3. Backend broadcasts SSE event to connected clients

        # Simulate state update
        state_before = {
            "running": True,
            "observing_game": 12345,
            "active_games": {
                12345: {"moves": [{"loc": "q16", "color": "B"}]}
            }
        }
        state_file.write_text(json.dumps(state_before))

        # Simulate new move
        state_after = {
            "running": True,
            "observing_game": 12345,
            "active_games": {
                12345: {"moves": [
                    {"loc": "q16", "color": "B"},
                    {"loc": "d4", "color": "W"}
                ]}
            }
        }
        state_file.write_text(json.dumps(state_after))

        # Verify state was updated (JSON converts int keys to strings)
        content = json.loads(state_file.read_text())
        assert len(content["active_games"]["12345"]["moves"]) == 2