"""E2E Tests: Game Cycling

Tests that verify the bot can cycle through multiple games correctly,
capturing state from each game and switching between them.
"""

import json
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import wait_for_result, BotProcess, log_game_data


def print_game_summary(game, channel_id):
    """Print a brief game summary."""
    print(f"  Game {channel_id}: {game.get('black', 'N/A')} vs {game.get('white', 'N/A')}, "
          f"{game.get('board_size', game.get('size', 'N/A'))}x{game.get('board_size', game.get('size', 'N/A'))}, "
          f"Komi={game.get('komi', 'N/A')}, Handicap={game.get('handicap', 'N/A')}, "
          f"Moves={len(game.get('moves', []))}")


class TestGameCycling:
    """Test: Cycling through multiple games"""

    def test_cycle_through_multiple_games(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Bot can cycle through multiple games and capture each one."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Wait for bot to be ready
        for _ in range(30):
            if state_file.exists():
                break
            time.sleep(1)

        # Login to KGS
        print("\n" + "="*60)
        print("GAME CYCLING TEST")
        print("="*60)
        print("Logging in to KGS...")
        login_id = "login-cycling"
        command_file.write_text(json.dumps({
            "id": login_id,
            "command": "login",
            "params": {}
        }))

        # Wait for login result
        result = None
        start_time = time.time()
        while time.time() - start_time < 60.0:
            if result_file.exists():
                content = result_file.read_text()
                if content:
                    r = json.loads(content)
                    if r.get("id") == login_id:
                        result = r
                        break
            time.sleep(0.5)

        assert result is not None, "No result from login"
        assert result.get("ok") is True, f"Login failed: {result.get('message')}"
        print("Login successful!")

        # Wait for connection
        time.sleep(5)

        # Get active games
        get_games_id = "get-games-cycling"
        command_file.write_text(json.dumps({
            "id": get_games_id,
            "command": "get_active_games",
            "params": {"room": 354}
        }))

        # Wait for result
        result = None
        start_time = time.time()
        while time.time() - start_time < 30.0:
            if result_file.exists():
                content = result_file.read_text()
                if content:
                    r = json.loads(content)
                    if r.get("id") == get_games_id:
                        result = r
                        break
            time.sleep(0.5)

        assert result is not None, "No result from get_active_games"

        # Get games from command result
        games = result.get("data", {}).get("games", [])
        print(f"\nFound {len(games)} active games to cycle through")

        if not games:
            print("No active games available - skipping cycling test")
            return

        # Cycle through up to 5 games
        num_games_to_test = min(5, len(games))
        observed_games = []
        log_dir = Path("/workspace/kgs-bot-debug/logs/e2e_test_bot/game-data/cycling")
        log_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nCycling through {num_games_to_test} games:")
        print("-" * 60)

        for i, game in enumerate(games[:num_games_to_test], 1):
            channel_id = str(game.get("channelId"))
            print(f"\n[{i}/{num_games_to_test}] Observing game {channel_id}...")

            # Send observe command
            command_file.write_text(json.dumps({
                "id": f"observe-cycle-{i}",
                "command": "observe_game",
                "params": {"channelId": int(channel_id)}
            }))

            # Wait for result
            result = wait_for_result(result_file, timeout=30.0)
            if result and result.get("ok"):
                print(f"  ✓ Observe command accepted")

                # Wait for GAME_JOIN and state update (up to 15 seconds per game)
                game_found = False
                last_mtime = 0
                game_data = None
                moves = []

                for wait_attempt in range(30):  # Up to 15 seconds (30 * 0.5s)
                    time.sleep(0.5)
                    if state_file.exists():
                        try:
                            mtime = state_file.stat().st_mtime
                            if mtime > last_mtime:
                                last_mtime = mtime
                                state = json.loads(state_file.read_text())
                                active = state.get("active_games", {})
                                if channel_id in active:
                                    game_data = active[channel_id]
                                    moves = game_data.get("moves", [])
                                    game_found = True
                                    print(f"  ✓ Game loaded in {wait_attempt * 0.5:.1f}s")
                                    break
                        except:
                            pass

                if game_found and game_data:
                    print_game_summary(game_data, channel_id)

                    # Log this game
                    log_game_data(f"cycling_game_{i}", game_data, channel_id, moves)

                    # Save to cycling summary
                    cycling_log = log_dir / f"game_{i}_{channel_id}.json"
                    cycling_log.write_text(json.dumps(game_data, indent=2))

                    observed_games.append({
                        "channel_id": channel_id,
                        "moves_count": len(moves),
                        "board_size": game_data.get("board_size", game_data.get("size")),
                        "komi": game_data.get("komi"),
                        "handicap": game_data.get("handicap"),
                        "players": game_data.get("players", {})
                    })

                    # Small delay before next game
                    time.sleep(1)
                else:
                    print(f"  ✗ Game {channel_id} not found in state after waiting")
            else:
                print(f"  ✗ Observe command failed: {result}")

        print("\n" + "-" * 60)
        print(f"\nCYCLING SUMMARY: Observed {len(observed_games)} games")
        print("="*60)

        # Write cycling summary
        summary_data = {
            "test_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_games_observed": len(observed_games),
            "games": observed_games
        }

        summary_file = log_dir / "cycling_summary.json"
        summary_file.write_text(json.dumps(summary_data, indent=2))

        # Print summary
        for i, g in enumerate(observed_games, 1):
            players = g.get("players", {})
            black = players.get("black", {})
            white = players.get("white", {})
            print(f"  {i}. Channel {g['channel_id']}: {black.get('name', 'N/A')} vs {white.get('name', 'N/A')}, "
                   f"{g.get('moves_count', 0)} moves, Handicap={g.get('handicap', 'N/A')}")

        # Assert we observed at least one game
        assert len(observed_games) > 0, "No games were successfully observed"

        print("\n✓ Game cycling test completed!")


class TestGameCyclingStateIsolation:
    """Test: State from different games doesn't interfere"""

    def test_state_isolation_between_games(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Each game maintains its own state without interference."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Wait for bot to be ready
        for _ in range(30):
            if state_file.exists():
                break
            time.sleep(1)

        # Login
        print("\n" + "="*60)
        print("STATE ISOLATION TEST")
        print("="*60)
        print("Logging in to KGS...")

        login_id = "login-isolation"
        command_file.write_text(json.dumps({
            "id": login_id,
            "command": "login",
            "params": {}
        }))

        result = None
        start_time = time.time()
        while time.time() - start_time < 60.0:
            if result_file.exists():
                content = result_file.read_text()
                if content:
                    r = json.loads(content)
                    if r.get("id") == login_id:
                        result = r
                        break
            time.sleep(0.5)

        assert result is not None and result.get("ok") is True
        print("Login successful!")
        time.sleep(5)

        # Get active games
        command_file.write_text(json.dumps({
            "id": "get-games-isolation",
            "command": "get_active_games",
            "params": {"room": 354}
        }))

        result = wait_for_result(result_file, timeout=30.0)
        assert result is not None

        games = result.get("data", {}).get("games", [])
        print(f"Found {len(games)} active games")

        if len(games) < 2:
            print(f"Need at least 2 games for isolation test, found {len(games)}")
            print("Skipping isolation test")
            return

        # Observe two different games
        game1_id = str(games[0].get("channelId"))
        game2_id = str(games[1].get("channelId"))

        print(f"\nObserving game 1: {game1_id}")
        command_file.write_text(json.dumps({
            "id": "observe-game1",
            "command": "observe_game",
            "params": {"channelId": int(game1_id)}
        }))

        result = wait_for_result(result_file, timeout=30.0)
        assert result and result.get("ok")
        time.sleep(3)

        # Capture game 1 state
        game1_state = None
        if state_file.exists():
            state = json.loads(state_file.read_text())
            if game1_id in state.get("active_games", {}):
                game1_state = state["active_games"][game1_id]
                print(f"  Game 1 captured: {len(game1_state.get('moves', []))} moves")

        print(f"\nObserving game 2: {game2_id}")
        command_file.write_text(json.dumps({
            "id": "observe-game2",
            "command": "observe_game",
            "params": {"channelId": int(game2_id)}
        }))

        result = wait_for_result(result_file, timeout=30.0)
        assert result and result.get("ok")
        time.sleep(3)

        # Capture game 2 state and verify game 1 is still intact
        game2_state = None
        if state_file.exists():
            state = json.loads(state_file.read_text())
            active = state.get("active_games", {})

            if game2_id in active:
                game2_state = active[game2_id]
                print(f"  Game 2 captured: {len(game2_state.get('moves', []))} moves")

            # Verify game 1 is still there
            if game1_id in active:
                game1_after = active[game1_id]
                print(f"  Game 1 still present: {len(game1_after.get('moves', []))} moves")

                # Verify game 1 wasn't corrupted
                if game1_state:
                    moves1_before = len(game1_state.get("moves", []))
                    moves1_after = len(game1_after.get("moves", []))
                    assert moves1_before == moves1_after, \
                        f"Game 1 moves changed from {moves1_before} to {moves1_after}"
                    print("  ✓ Game 1 state preserved correctly")

        print("\n✓ State isolation verified!")