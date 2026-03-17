# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

E2E testing infrastructure for debugging `kgs-bot` (Python) and `kgs-bot-monitor` (Node.js) integration. Tests validate the file-based command/response protocol and observation flow against the real KGS (Kifu Server) Go server.

## Commands

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test phase
pytest tests/ -m phase1      # Command/response protocol
pytest tests/ -m phase2      # Observation flow
pytest tests/ -m phase3      # Race conditions
pytest tests/ -m phase4      # Error recovery

# Run single test file
pytest tests/test_command_protocol.py -v

# Run specific test
pytest tests/test_race_conditions.py::TestRapidRejoinCooldown::test_rapid_rejoin_reuses_state -v

# With logging
pytest tests/ -s --log-cli-level=INFO
```

## Architecture

### System Components

```
kgs-bot (Python) ◄──file protocol──► kgs-bot-monitor (Node.js) ──SSE──► React UI
      │
      └──────────────────────────────► KGS Server (Go protocol)
```

### File-Based Communication Protocol

| File | Writer | Reader | Purpose |
|------|--------|--------|---------|
| `run/<bot_id>_command.json` | Monitor | Bot | Send commands |
| `run/<bot_id>_command_result.json` | Bot | Monitor | Command results |
| `run/<bot_id>_state.json` | Bot | Monitor | Current state |

**Command format:**
```json
{"id": "unique-request-id", "command": "observe_game", "params": {"channelId": 12345}}
```

**Result format:**
```json
{"id": "unique-request-id", "ok": true, "message": "success"}
```

### Critical Data Structures

**Cache structures (kgs_bot.py):**
- `room_games_cache`: roomId → list of games
- `global_games_cache`: channelId → game
- `games_by_id`: channelId → game (unified view)

**KgsGame fields:**
- `channel_id`, `is_observation`, `moves`, `move_number`
- `processed_node_ids`: Set for deduplication
- `handicap_stones`, `board_size`, `komi`, `rules`
- `analysis_score_history`: KataGo analysis data

### Observation Flow

1. **Startup:** Bot LOGINs to KGS, joins GLOBAL_LIST and room 354 (Computer Go Room), caches games
2. **User initiates:** UI fetches active games via `GET /api/bots/:id/active-games`
3. **User selects game:** Monitor writes `observe_game` command to file with channelId
4. **Bot executes:** Reads command, sends JOIN_REQUEST to KGS, sets `observing_game` and `is_observation=True`
5. **KGS responds:** GAME_JOIN (full history) + GAME_UPDATE (real-time moves)
6. **State propagation:** Bot updates state.json → Monitor detects change → SSE to UI

### Critical Race Conditions

1. **GAME_UPDATE before GAME_JOIN:** During join, KGS may send GAME_UPDATE before GAME_JOIN. Fix: Set `observing_game` and `is_observation=True` IMMEDIATELY when sending JOIN_REQUEST.

2. **Duplicate GAME_JOIN messages:** KGS may resend. Fix: Track `processed_node_ids` per game, skip already-processed nodes.

3. **Rapid UNJOIN/Rejoin:** Quick leave/rejoin corrupts state. Fix: Per-game rejoin cooldown (1 second) using `_last_observation_leave` timestamp.

### Test Infrastructure

- **Test bot ID:** `test_bot`
- **Run directory:** `/workspace/kgs-bot-debug/run/`
- **kgs-bot path:** `/workspace/Kgs-bot/`
- **Monitor path:** `/workspace/kgs-bot-monitor/`

### pytest Fixtures (conftest.py)

- `test_run_dir`: Path to run/ directory
- `bot_id`: Test bot identifier
- `command_file`: Path to `<bot_id>_command.json`
- `result_file`: Path to `<bot_id>_command_result.json`
- `state_file`: Path to `<bot_id>_state.json`
- `logs_dir`: Path to logs directory
- `kgs_bot_path` / `monitor_path`: Paths to actual installations

### Test Phases

| Phase | File | Focus |
|-------|------|-------|
| Phase 1 | `test_command_protocol.py` | Command file format, bot execution, state updates |
| Phase 2 | `test_observation_flow.py` | Login, observe command, GAME_JOIN/GAME_UPDATE, SSE |
| Phase 3 | `test_race_conditions.py` | Update-before-join, rapid rejoin, game switches |
| Phase 4 | `test_error_recovery.py` | KGS disconnect, malformed commands, state write failures |

### Key Implementation Notes

- Tests use **real KGS server** (not mocks) for integration testing
- JSON converts integer keys to strings (e.g., `{"12345": ...}` not `{12345: ...}`)
- State file changes trigger SSE broadcasts to UI
- Bot polls command file; monitor watches state file for updates