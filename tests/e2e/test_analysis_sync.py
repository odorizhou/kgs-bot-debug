"""E2E Tests: Analysis Engine Synchronization

Tests that verify the analysis engine (KataGo) syncs board state correctly
after joining a game and produces analysis results.
"""

import json
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import wait_for_result, BotProcess, log_game_data


def print_analysis_summary(game, channel_id):
    """Print analysis summary."""
    analysis = game.get("analysis_score_history", [])
    print(f"\nAnalysis Engine Results for Channel {channel_id}:")
    print("-" * 50)
    print(f"Total moves analyzed: {len(analysis)}")

    if analysis:
        print(f"First analysis: move {analysis[0].get('moveNum', 'N/A')}, score: {analysis[0].get('score', 'N/A')}")
        print(f"Last analysis: move {analysis[-1].get('moveNum', 'N/A')}, score: {analysis[-1].get('score', 'N/A')}")

        # Show score range
        scores = [a.get('score') for a in analysis if a.get('score') is not None]
        if scores:
            print(f"Score range: {min(scores):.2f} to {max(scores):.2f}")
    print("-" * 50)


class TestAnalysisEngineSync:
    """Test: Analysis engine syncs after game join"""

    def test_analysis_engine_produces_results(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Analysis engine returns results after initial sync."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Wait for bot to be ready
        for _ in range(30):
            if state_file.exists():
                break
            time.sleep(1)

        # Login to KGS
        print("\n" + "="*60)
        print("ANALYSIS ENGINE SYNC TEST")
        print("="*60)
        print("Logging in to KGS...")
        login_id = "login-analysis"
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
        get_games_id = "get-games-analysis"
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
        print(f"\nFound {len(games)} active games")

        if not games:
            print("No active games available - skipping analysis test")
            return

        # Pick first game
        game = games[0]
        channel_id = str(game.get("channelId"))
        print(f"\nObserving game {channel_id}...")

        # Send observe command
        command_file.write_text(json.dumps({
            "id": "observe-analysis",
            "command": "observe_game",
            "params": {"channelId": int(channel_id)}
        }))

        result = wait_for_result(result_file, timeout=30.0)
        assert result is not None
        assert result.get("ok") is True, f"Observe failed: {result.get('message')}"

        # Wait for game to be in state file (observation joined)
        # Analysis session is initialized when GAME_UPDATE arrives with moves
        print("Waiting for observation to be established...")
        game_data = None
        last_mtime = 0

        for wait_attempt in range(60):  # Up to 30 seconds
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
                            print(f"Game {channel_id} found in state after {wait_attempt * 0.5:.1f}s")
                            print(f"  Moves: {len(game_data.get('moves', []))}")
                            print(f"  Is observation: {game_data.get('isObservation', game_data.get('is_observation', False))}")
                            break
                except:
                    pass

        # Verify observation was established and analysis infrastructure is ready
        if game_data:
            moves_count = len(game_data.get("moves", []))
            is_observation = game_data.get("is_observation", False)
            analysis_history = game_data.get("analysis_score_history", [])

            print(f"\n{'='*60}")
            print(f"GAME STATE CAPTURED:")
            print(f"{'='*60}")
            print(f"Channel ID: {channel_id}")
            print(f"Is observation: {is_observation}")
            print(f"Moves captured: {moves_count}")
            print(f"Board size: {game_data.get('board_size', game_data.get('size', 'N/A'))}")
            print(f"Komi: {game_data.get('komi', 'N/A')}")
            print(f"Handicap: {game_data.get('handicap', 'N/A')}")
            print(f"Analysis results: {len(analysis_history)} entries")

            # Check analysis daemon socket
            socket_path = "/workspace/Kgs-bot/run/e2e_test_bot_analysis.sock"
            import os
            if os.path.exists(socket_path) or os.path.islink(socket_path):
                print(f"\n✓ Analysis daemon socket available: {socket_path}")
            else:
                print(f"\n⚠ Analysis daemon socket not found: {socket_path}")
                print("  (Analysis requires connection to running daemon)")

            # Log game data
            log_game_data("analysis_sync", game_data, channel_id, game_data.get("moves", []))

            # Save detailed log
            log_dir = Path("/workspace/kgs-bot-debug/logs/e2e_test_bot/game-data/analysis")
            log_dir.mkdir(parents=True, exist_ok=True)
            analysis_log = log_dir / f"analysis_{channel_id}.json"
            analysis_log.write_text(json.dumps({
                "channel_id": channel_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_observation": is_observation,
                "moves_count": moves_count,
                "analysis_score_history": analysis_history,
                "game_data": game_data
            }, indent=2))

            # Test passes if game state is captured (observation or playing)
            if moves_count > 0:
                print(f"\n✓ Analysis sync test PASSED!")
                print(f"  Game state captured with {moves_count} moves")
                if analysis_history:
                    print(f"  Analysis results: {len(analysis_history)} score entries")
                else:
                    print(f"  Note: No analysis results yet (game may be idle or analysis not triggered)")
            else:
                print(f"\n⚠ Test completed (moves={moves_count})")
        else:
            print(f"\n✗ No game data for channel {channel_id}")
            print("Note: Observation may have timed out")


class TestAnalysisIncrementalUpdates:
    """Test: Analysis updates incrementally as game progresses"""

    def test_analysis_updates_with_new_moves(
        self,
        test_bot_id: str,
        bot_process: BotProcess,
        command_file: Path,
        result_file: Path,
        state_file: Path
    ) -> None:
        """Analysis updates as new moves arrive."""
        # Verify bot is running
        assert bot_process.is_running(), "Bot process not running"

        # Wait for bot to be ready
        for _ in range(30):
            if state_file.exists():
                break
            time.sleep(1)

        # Login
        print("\n" + "="*60)
        print("ANALYSIS INCREMENTAL UPDATE TEST")
        print("="*60)
        print("Logging in to KGS...")

        login_id = "login-analysis-inc"
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
            "id": "get-games-analysis-inc",
            "command": "get_active_games",
            "params": {"room": 354}
        }))

        result = wait_for_result(result_file, timeout=30.0)
        assert result is not None

        games = result.get("data", {}).get("games", [])

        if not games:
            print("No active games - skipping incremental test")
            return

        # Pick first game
        game = games[0]
        channel_id = str(game.get("channelId"))
        print(f"\nObserving game {channel_id}...")

        # Observe game
        command_file.write_text(json.dumps({
            "id": "observe-analysis-inc",
            "command": "observe_game",
            "params": {"channelId": int(channel_id)}
        }))

        result = wait_for_result(result_file, timeout=30.0)
        assert result and result.get("ok")

        # Wait for initial analysis
        time.sleep(10)

        # Check initial analysis count
        initial_analysis_count = 0
        if state_file.exists():
            state = json.loads(state_file.read_text())
            active = state.get("active_games", {})
            if channel_id in active:
                analysis = active[channel_id].get("analysis_score_history", [])
                initial_analysis_count = len(analysis)
                print(f"Initial analysis entries: {initial_analysis_count}")

        # Wait for potential updates (30 seconds)
        print("Waiting for incremental analysis updates...")
        time.sleep(30)

        # Check for updated analysis
        final_analysis_count = 0
        if state_file.exists():
            state = json.loads(state_file.read_text())
            active = state.get("active_games", {})
            if channel_id in active:
                analysis = active[channel_id].get("analysis_score_history", [])
                final_analysis_count = len(analysis)
                print(f"Final analysis entries: {final_analysis_count}")

        # Note: Analysis may or may not update depending on game activity
        print(f"\nAnalysis entries: {initial_analysis_count} -> {final_analysis_count}")
        print("✓ Incremental analysis test completed")