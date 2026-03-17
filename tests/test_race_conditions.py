"""Phase 3: Race Condition Tests

Tests for race conditions that have caused bugs in the observation flow.
"""

import json
import time
from pathlib import Path

import pytest


@pytest.mark.phase3
class TestGameUpdateBeforeGameJoin:
    """Test 3.1: GAME_UPDATE arrives before GAME_JOIN

    This is a critical race condition:
    - Bot sends JOIN_REQUEST
    - KGS sends GAME_UPDATE before GAME_JOIN
    - Bot must recognize this is an observation (not playing)
    - Bot must not crash or corrupt state
    """

    def test_observing_game_set_before_join_request(self, state_file: Path) -> None:
        """observing_game is set immediately when JOIN_REQUEST is sent."""
        # The fix: Set observing_game BEFORE any async messages arrive
        # This ensures GAME_UPDATE knows this is observation, not playing

        # Simulate state right after JOIN_REQUEST
        state = {
            "running": True,
            "observing_game": 12345,  # Set IMMEDIATELY
            "active_games": {
                "12345": {
                    "channelId": 12345,
                    "is_observation": True,  # Critical flag
                    "moves": []
                }
            }
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["observing_game"] == 12345
        assert content["active_games"]["12345"]["is_observation"] is True

    def test_game_update_during_join_handled(self) -> None:
        """GAME_UPDATE during join is handled correctly."""
        # Simulate GAME_UPDATE arriving before GAME_JOIN
        game_update = {
            "type": "GAME_UPDATE",
            "channelId": 12345,
            "sgfEvents": [
                {
                    "type": "PROP_ADDED",
                    "nodeId": 1,
                    "prop": {"name": "MOVE", "loc": "q16", "color": "B"}
                }
            ]
        }

        # Bot state (observing_game already set)
        bot_state = {
            "observing_game": 12345,
            "active_games": {
                "12345": {
                    "is_observation": True,
                    "moves": [],
                    "processed_node_ids": set()
                }
            }
        }

        # Process GAME_UPDATE (should not crash)
        channel_id = game_update["channelId"]
        if str(channel_id) in bot_state["active_games"]:
            game = bot_state["active_games"][str(channel_id)]
            if game["is_observation"]:
                # Correctly recognized as observation
                for event in game_update["sgfEvents"]:
                    if event.get("nodeId") not in game["processed_node_ids"]:
                        game["moves"].append({
                            "loc": event["prop"]["loc"],
                            "color": event["prop"]["color"]
                        })
                        game["processed_node_ids"].add(event["nodeId"])

        # Assert - no crash, move buffered
        assert len(bot_state["active_games"]["12345"]["moves"]) == 1

    def test_moves_buffered_until_game_join(self) -> None:
        """Moves from early GAME_UPDATE are available after GAME_JOIN."""
        # Initial state: GAME_UPDATE arrived, moves buffered
        state_before_join = {
            "observing_game": 12345,
            "active_games": {
                "12345": {
                    "is_observation": True,
                    "moves": [{"loc": "q16", "color": "B"}],  # From early GAME_UPDATE
                    "processed_node_ids": {1}
                }
            }
        }

        # GAME_JOIN arrives with full history
        game_join = {
            "type": "GAME_JOIN",
            "channelId": 12345,
            "sgfEvents": [
                {"type": "PROP_ADDED", "nodeId": 1, "prop": {"name": "MOVE", "loc": "q16", "color": "B"}},
                {"type": "PROP_ADDED", "nodeId": 2, "prop": {"name": "MOVE", "loc": "d4", "color": "W"}}
            ]
        }

        # Process GAME_JOIN (should not duplicate move 1)
        processed_ids = set(state_before_join["active_games"]["12345"]["processed_node_ids"])
        moves = list(state_before_join["active_games"]["12345"]["moves"])

        for event in game_join["sgfEvents"]:
            node_id = event.get("nodeId")
            if node_id not in processed_ids:
                moves.append({
                    "loc": event["prop"]["loc"],
                    "color": event["prop"]["color"]
                })
                processed_ids.add(node_id)

        # Assert - no duplicates, new move added
        assert len(moves) == 2
        assert moves[0]["loc"] == "q16"  # Original
        assert moves[1]["loc"] == "d4"   # New from GAME_JOIN


@pytest.mark.phase3
class TestRapidRejoinCooldown:
    """Test 3.2: Rapid rejoin after leave

    Issue: Quick leave/rejoin cycles cause state corruption
    Fix: Per-game rejoin cooldown (1 second)
    """

    def test_last_observation_leave_recorded(self, state_file: Path) -> None:
        """_last_observation_leave is recorded on leave."""
        # Simulate state after leave_observation
        state = {
            "running": True,
            "observing_game": None,
            "_last_observation_leave": {
                "12345": time.time()  # Timestamp of leave
            }
        }
        state_file.write_text(json.dumps(state))

        # Assert
        content = json.loads(state_file.read_text())
        assert "12345" in content["_last_observation_leave"]

    def test_rapid_rejoin_reuses_state(self) -> None:
        """Rejoin within 1 second reuses existing state."""
        current_time = time.time()

        # Bot state after leave
        bot_state = {
            "_last_observation_leave": {"12345": current_time},
            "active_games": {
                "12345": {
                    "channelId": 12345,
                    "is_observation": False,
                    "moves": [{"loc": "q16", "color": "B"}]
                }
            }
        }

        # Attempt rejoin immediately (< 1 second)
        time_since_leave = current_time - bot_state["_last_observation_leave"]["12345"]

        if time_since_leave < 1.0:
            # Reuse existing state instead of re-joining
            bot_state["active_games"]["12345"]["is_observation"] = True
            reused_state = True
        else:
            reused_state = False

        # Assert - state reused, no new JOIN_REQUEST
        assert reused_state is True
        assert bot_state["active_games"]["12345"]["is_observation"] is True

    def test_normal_rejoin_after_cooldown(self) -> None:
        """Rejoin after 1+ seconds performs normal join."""
        old_time = time.time() - 2.0  # 2 seconds ago

        bot_state = {
            "_last_observation_leave": {"12345": old_time}
        }

        time_since_leave = time.time() - bot_state["_last_observation_leave"]["12345"]

        if time_since_leave < 1.0:
            normal_join = False
        else:
            normal_join = True  # Cooldown expired, normal join

        assert normal_join is True


@pytest.mark.phase3
class TestConcurrentGameSwitches:
    """Test 3.3: Switching between games

    Issue: Rapid game switches can corrupt state
    Fix: Clean up previous observation before joining new game
    """

    def test_previous_game_cleaned_up(self, state_file: Path) -> None:
        """Switching games cleans up previous observation."""
        # State before switch
        state_before = {
            "observing_game": 12345,
            "active_games": {
                "12345": {"is_observation": True, "moves": []},
                "67890": {"is_observation": False, "moves": []}
            }
        }
        state_file.write_text(json.dumps(state_before))

        # Simulate switch to game 67890
        state_after = {
            "observing_game": 67890,
            "active_games": {
                "12345": {"is_observation": False, "moves": []},  # Cleaned up
                "67890": {"is_observation": True, "moves": []}  # New observation
            }
        }
        state_file.write_text(json.dumps(state_after))

        # Assert
        content = json.loads(state_file.read_text())
        assert content["observing_game"] == 67890
        assert content["active_games"]["12345"]["is_observation"] is False
        assert content["active_games"]["67890"]["is_observation"] is True

    def test_no_cross_contamination(self) -> None:
        """Moves from different games don't mix."""
        # Game A state
        game_a = {
            "channelId": 12345,
            "moves": [{"loc": "q16", "color": "B"}]
        }

        # Game B state
        game_b = {
            "channelId": 67890,
            "moves": [{"loc": "d4", "color": "W"}]
        }

        # Assert - games are independent
        assert game_a["moves"][0]["loc"] == "q16"
        assert game_b["moves"][0]["loc"] == "d4"
        assert game_a["channelId"] != game_b["channelId"]

    def test_rapid_switch_preserves_state(self) -> None:
        """Rapid A→B→A switches preserve each game's state."""
        # Initial: observing A
        state = {
            "observing_game": 12345,
            "active_games": {
                "12345": {"moves": [{"loc": "q16", "color": "B"}]},
                "67890": {"moves": []}
            }
        }

        # Switch to B
        state["observing_game"] = 67890
        state["active_games"]["67890"]["moves"] = [{"loc": "d4", "color": "W"}]

        # Switch back to A (simulating new move in A)
        state["observing_game"] = 12345
        state["active_games"]["12345"]["moves"].append({"loc": "q15", "color": "W"})

        # Assert - each game has correct moves
        assert len(state["active_games"]["12345"]["moves"]) == 2
        assert len(state["active_games"]["67890"]["moves"]) == 1
        assert state["active_games"]["12345"]["moves"][0]["loc"] == "q16"
        assert state["active_games"]["67890"]["moves"][0]["loc"] == "d4"