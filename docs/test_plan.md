# E2E Testing Plan

This document outlines the test cases for validating kgs-bot and kgs-bot-monitor integration against the **real KGS server**.

---

## Test Strategy

We'll test the actual integration points where bugs have occurred:

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Command/Response Protocol                        │
│  - Monitor → Bot commands work                              │
│  - Bot → Monitor responses work                            │
│  - State file synchronization                              │
├─────────────────────────────────────────────────────────────┤
│  Phase 2: Observation Flow (Real KGS)                      │
│  - Login and room join                                      │
│  - Observe game command                                     │
│  - GAME_JOIN/GAME_UPDATE handling                           │
│  - Real-time UI updates                                     │
├─────────────────────────────────────────────────────────────┤
│  Phase 3: Race Conditions                                  │
│  - GAME_UPDATE before GAME_JOIN                            │
│  - Rapid rejoin after leave                                │
│  - Concurrent game switches                                │
├─────────────────────────────────────────────────────────────┤
│  Phase 4: Error Recovery                                   │
│  - KGS disconnection                                        │
│  - Command file errors                                      │
│  - State file write failures                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Command/Response Protocol

### Test 1.1: Command File Write/Read

**Purpose:** Verify monitor can send commands to bot

```python
# tests/test_command_protocol.py
def test_command_file_created():
    """Monitor writes command file correctly"""
    # Arrange: Bot is running
    # Act: Monitor writes observe_game command
    # Assert: File exists at run/<bot_id>_command.json
    # Assert: JSON is valid with id, command, params
```

### Test 1.2: Bot Processes Command

**Purpose:** Verify bot picks up and executes commands

```python
def test_bot_executes_command():
    """Bot reads and processes command file"""
    # Arrange: Bot running, command file exists
    # Act: Wait for bot to poll (or trigger poll)
    # Assert: Command executed
    # Assert: Result written to command_result.json
    # Assert: result.ok == True
```

### Test 1.3: State File Updates

**Purpose:** Verify state changes are persisted

```python
def test_state_file_updated():
    """State file reflects current bot state"""
    # Arrange: Bot executing command
    # Act: Wait for state update
    # Assert: state.json updated
    # Assert: observing_game field present
```

---

## Phase 2: Observation Flow (Real KGS)

### Test 2.1: Login and Startup

**Purpose:** Verify bot connects to KGS and caches games

```python
# tests/test_observation_flow.py
def test_login_and_startup():
    """Bot logs in and joins rooms"""
    # Arrange: Bot configured with KGS credentials
    # Act: Send login command
    # Assert: LOGIN_SUCCESS received
    # Assert: ROOM_JOIN received for room 354
    # Assert: room_games_cache populated
```

### Test 2.2: Observe Game Command

**Purpose:** Verify bot joins game as observer

```python
def test_observe_game():
    """Bot can observe a real KGS game"""
    # Arrange: Bot logged in, game exists in room 354
    # Act: Send observe_game command with channelId
    # Assert: Bot sends JOIN_REQUEST to KGS
    # Assert: observing_game = channelId
    # Assert: is_observation = True
```

### Test 2.3: GAME_JOIN History Sync

**Purpose:** Verify complete move history received

```python
def test_game_join_history():
    """GAME_JOIN contains complete move history"""
    # Arrange: Bot joined game
    # Act: Wait for GAME_JOIN
    # Assert: sgfEvents received
    # Assert: moves parsed from sgfEvents
    # Assert: processed_node_ids tracked
```

### Test 2.4: GAME_UPDATE Real-time

**Purpose:** Verify new moves received incrementally

```python
def test_game_update_realtime():
    """GAME_UPDATE delivers new moves"""
    # Arrange: Bot observing game
    # Act: Wait for next move in game
    # Assert: GAME_UPDATE received
    # Assert: New move appended to game.moves
    # Assert: state.json updated
```

### Test 2.5: SSE to UI

**Purpose:** Verify UI receives real-time updates

```python
def test_sse_updates_ui():
    """UI receives game updates via SSE"""
    # Arrange: UI connected to SSE stream
    # Act: New move arrives
    # Assert: SSE event 'game_update' sent
    # Assert: UI board updates
```

---

## Phase 3: Race Conditions

### Test 3.1: GAME_UPDATE Before GAME_JOIN

**Purpose:** Verify race condition is handled

```python
# tests/test_race_conditions.py
def test_update_before_join():
    """GAME_UPDATE during join doesn't crash"""
    # Arrange: Bot just sent JOIN_REQUEST
    # Act: KGS sends GAME_UPDATE before GAME_JOIN
    # Assert: Bot recognizes observation mode
    # Assert: No crash
    # Assert: Moves eventually synced
```

### Test 3.2: Rapid Rejoin Cooldown

**Purpose:** Verify rejoin cooldown works

```python
def test_rapid_rejoin():
    """Quick leave/rejoin doesn't corrupt state"""
    # Arrange: Bot observing game
    # Act: Send leave_observation, then observe_game (< 1s)
    # Assert: Bot reuses existing state
    # Assert: No duplicate JOIN_REQUEST
```

### Test 3.3: Game Switch

**Purpose:** Verify switching games works

```python
def test_switch_games():
    """Switching observation targets works"""
    # Arrange: Bot observing game A
    # Act: Send observe_game for game B
    # Assert: Game A cleaned up
    # Assert: Game B observation starts
```

---

## Phase 4: Error Recovery

### Test 4.1: KGS Disconnection

**Purpose:** Verify bot recovers from network issues

```python
# tests/test_error_recovery.py
def test_kgs_disconnect():
    """Bot recovers from KGS disconnection"""
    # Arrange: Bot observing game
    # Act: Simulate network drop (kill connection)
    # Assert: Bot detects error
    # Assert: Reconnect attempt
```

### Test 4.2: Command File Errors

**Purpose:** Verify bot handles malformed commands

```python
def test_malformed_command():
    """Bot handles invalid command file"""
    # Arrange: Write invalid JSON to command file
    # Act: Bot polls for commands
    # Assert: Error logged
    # Assert: Bot continues running
```

---

## Test Infrastructure

### Test Bot Instance

```python
# tests/conftest.py
@pytest.fixture
def test_bot():
    """Create isolated bot instance for testing"""
    bot_id = "test_bot"
    # Start bot with test config
    yield bot_id
    # Cleanup
```

### KGS Test Account

```python
# Use dedicated test account on KGS
# config/test.cfg
username = "kgs_test_bot"
password = "..."
room_id = 354  # Computer Go Room
```

### Test Commands

```bash
# Run all tests
pytest tests/ -v

# Run specific phase
pytest tests/test_command_protocol.py  # Phase 1
pytest tests/test_observation_flow.py  # Phase 2
pytest tests/test_race_conditions.py  # Phase 3

# Run with logging
pytest tests/ -s --log-cli-level=INFO
```

---

## Related Documentation
- [Architecture Summary](./architecture_summary.md)