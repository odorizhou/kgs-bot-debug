# Architecture Summary

This document summarizes the architecture and flows of kgs-bot and kgs-bot-monitor for e2e testing.

## System Overview

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   kgs-bot       │◄────────►│ kgs-bot-monitor │◄────────►│   React UI      │
│   (Python)      │  files   │  (Node.js)     │  HTTP/SSE │               │
└─────────────────┘         └─────────────────┘         └─────────────────┘
       │
       ▼
┌─────────────────┐
│   KGS Server    │
│   (Go Server)   │
└─────────────────┘
```

## Communication Protocol

### File-Based Command/Response

| File | Writer | Reader | Purpose |
|------|--------|--------|---------|
| `run/<bot_id>_command.json` | Monitor | Bot | Send commands |
| `run/<bot_id>_command_result.json` | Bot | Monitor | Command results |
| `run/<bot_id>_state.json` | Bot | Monitor | Current state |

### Command Format
```json
{
  "id": "unique-request-id",
  "command": "observe_game",
  "params": { "channelId": 12345 }
}
```

### Result Format
```json
{
  "id": "unique-request-id",
  "ok": true,
  "message": "success"
}
```

## Observation Flow

### 1. Startup Sequence (Before User Commands)
```
Bot → KGS: LOGIN
KGS → Bot: SESSION_ESTABLISHED (cookies)
Bot → KGS: GET (poll)
KGS → Bot: LOGIN_SUCCESS

Bot → KGS: JOIN_REQUEST (GLOBAL_LIST)
KGS → Bot: GLOBAL_LIST_JOIN (global games)

Bot → KGS: JOIN_REQUEST (roomId=354)
KGS → Bot: ROOM_JOIN + games[] ← Cached in room_games_cache
```

### 2. User Initiates Observation
```
User → UI: Click "Observe" button
UI → Backend: GET /api/bots/:id/active-games
Backend → Bot: get_active_games command
Bot → Backend: List of active games
Backend → UI: Game list for modal
```

### 3. User Selects Game
```
User → UI: Select game from dropdown
UI → Backend: POST /api/bots/:id/command { observe_game, channelId }
Backend → File: Write to run/<bot_id>_command.json
Bot → File: Read command, execute
Bot → KGS: JOIN_REQUEST (channelId)
Bot → File: Write result to command_result.json
```

### 4. KGS Sends Game Data
```
KGS → Bot: GAME_JOIN + sgfEvents[0..N] (complete history)
Bot: Parse moves, store in active_games[channelId]
Bot → File: Update state.json
Backend: Detect state change
Backend → UI: SSE game_update event
UI: Fetch new game data, render board
```

### 5. Real-time Updates
```
KGS → Bot: GAME_UPDATE + sgfEvents[N+1..M] (new moves)
Bot: Filter by processed_node_ids, append new moves
Bot → File: Update state.json
Backend → UI: SSE game_update event
UI: Update board display
```

## Key Data Structures

### Cache Structures (kgs_bot.py)
```python
room_games_cache = {}    # roomId -> [game1, game2, ...]
global_games_cache = {}  # channelId -> game
games_by_id = {}         # channelId -> game (unified view)
```

### KgsGame Object
```python
@dataclass
class KgsGame:
    channel_id: int
    is_observation: bool
    moves: List[Tuple[str, str]]  # (vertex, color)
    move_number: int
    processed_node_ids: Set[int]  # Deduplication
    handicap_stones: List[str]
    board_size: int
    komi: float
    rules: str
    analysis_score_history: List[Dict]
```

### Bot State (state.json)
```json
{
  "running": true,
  "status": "In game",
  "observing_game": 12345,
  "active_games": {
    "12345": {
      "channelId": 12345,
      "is_observation": true,
      "moves": [...],
      "analysis_score_history": [...]
    }
  }
}
```

## Critical Race Conditions

### 1. GAME_UPDATE Before GAME_JOIN
**Problem:** During join, GAME_UPDATE may arrive before GAME_JOIN
**Fix:** Set `observing_game` and `is_observation=True` IMMEDIATELY before sending JOIN_REQUEST

### 2. Duplicate GAME_JOIN Messages
**Problem:** KGS may resend GAME_JOIN messages
**Fix:** Track `processed_node_ids` per game, skip already-processed nodes

### 3. Rapid UNJOIN/Rejoin
**Problem:** Quick leave/rejoin cycles cause state corruption
**Fix:** Per-game rejoin cooldown (1 second) using `_last_observation_leave`

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/bots/:id/active-games` | List active games |
| POST | `/api/bots/:id/command` | Send command |
| GET | `/api/bots/:id/observe/:channelId` | Get observed game |
| GET | `/api/bots/:id/observe/:channelId/stream` | SSE stream |
| GET | `/api/bots/:id/observing` | Current observation state |
| GET | `/api/bots/:id/logs` | Bot logs |
| GET | `/api/bots/:id/engine-logs` | Engine logs |

## Log Files

| Log | Location | Purpose |
|-----|----------|---------|
| Bot logs | `logs/<bot_id>/<date>.log` | Main bot process |
| Analysis logs | `run/<bot_id>_analysis.log` | KataGo daemon |
| Backend logs | `backend.log` | Node.js server |
| Frontend logs | Browser console | React debug output |

## Related Documentation
- [observation_flow.md](../Kgs-bot/docs/observation_flow.md) - Detailed KGS protocol
- [OBSERVE_FEATURE_UI_FLOW.md](../kgs-bot-monitor/docs/OBSERVE_FEATURE_UI_FLOW.md) - UI flow
- [DEBUGGING_LOGS_REFERENCE.md](../kgs-bot-monitor/docs/DEBUGGING_LOGS_REFERENCE.md) - Debugging guide