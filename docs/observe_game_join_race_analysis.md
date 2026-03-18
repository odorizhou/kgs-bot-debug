# Observe flow: missing move history / GAME_JOIN not applied

**Status:** Fix implemented in `Kgs-bot` (2026-03-18)  
**Scope:** `kgs-bot` observation join; intermittent behavior with same bot version.

**Implementation:** `KgsClient` uses **`_long_poll_lock`** (mutex) around **`session.get`** only so at most one long-poll runs at a time (fixes split GAME_JOIN/GAME_UPDATE). **`_post_lock`** (`RLock`) wraps **`session.post`** in `_send_message` and `send_keepalive`. POSTs are not blocked for the entire long-poll, so monitor commands stay responsive. 5xx backoff sleeps stay outside the GET/POST critical sections where applicable.

## Problem description

After issuing `observe_game`, the bot sometimes ends up with **only incremental moves** (e.g. a single `GAME_UPDATE` at a high `nodeId` like 51) instead of the **full game tree** that normally arrives in a **`GAME_JOIN`** message with a large `sgfEvents` list.

Symptoms in logs:

- `👁️ Waiting for initial game state with moves...` appears.
- Next KGS traffic is **`GAME_UPDATE`** with few `sgfEvents`, not **`GAME_JOIN`** / `Joined game <channelId>`.
- UI/state shows **no history prior to join**.

A **success** case shows, on the first poll after `JOIN_REQUEST`: `Joined game <id>` and a full `🎮 GAME_JOIN message: {...}` with complete `sgfEvents`.

**Assumption for this write-up:** KGS **always** sends `GAME_JOIN` when joining as observer; when history is missing, the failure is in **how the bot receives or orders processing**, not in the server omitting the message.

## What the code does (relevant path)

1. **`JOIN_REQUEST`** is sent via POST. When the body is plain `OK`, the client returns `SESSION_ESTABLISHED` **without** processing embedded messages—full state is expected on a **subsequent GET** (long poll).

2. **`_join_as_observer`** (`kgs_bot.py`) sets `observing_game` / `is_observation`, POSTs join, then returns. Cached list entries often have **0 `sgfEvents`**.

3. **`observe_game` handler** logs **Waiting for initial game state…** and loops on **`poll_messages()`** until enough moves or timeout.

4. **`GAME_JOIN`** is handled in **`_handle_game_join`** (logs `Joined game …` and applies full `sgfEvents` to `moves` for observation).

So if logs never show `Joined game` for that channel around the join window, either **`GAME_JOIN` was not delivered to the handler** that the user is looking at, or it was **consumed elsewhere / lost in ordering**.

## Root cause (bot-side race)

The bot can run **two concurrent HTTP long-poll GETs** on the **same `requests.Session`**:

| Source | Where |
|--------|--------|
| **`polling_thread`** | `_poll_loop`: calls `poll_messages()` every iteration (long timeout when idle or with active games). |
| **Main thread (manual mode)** | `run_bot.py`: every ~2s calls `_process_monitor_command()`, which runs **`observe_game`** → nested **`poll_messages()`** while joining/waiting. |

`requests.Session` is **not thread-safe** for concurrent requests. With **two simultaneous long-poll GETs**, the server may **complete different waiters with different message batches**. One response may carry **`GAME_JOIN`**; another may carry only **`GAME_UPDATE`**. The observe path then sees **incremental updates only** and initializes analysis on the **`GAME_UPDATE` path**, matching the failure log pattern—even though **`GAME_JOIN` was sent on the other connection**.

This explains:

- **Intermittency** (which GET completes first).
- **Same codebase**, success vs failure (timing/thread scheduling).
- **Server “always sends GAME_JOIN”** still holding: the client may **apply** it on the wrong thread’s batch or **never merge** batches from two sockets.

## How to fix

### Option A — Serialize session I/O (recommended first step)

Add a **`threading.Lock`** (or equivalent) in **`KgsClient`** so **all** `GET` (poll) and `POST` (send) on that session are **mutually exclusive**. Only one in-flight HTTP request at a time per session.

- **Pros:** Small change; removes dual long-poll race; fixes observe and any other nested `poll_messages` vs main loop.
- **Cons:** Observe’s wait loop blocks the poll thread’s next poll until it finishes (acceptable if join wait is bounded).

**Files:** `Kgs-bot/src/kgs_client.py` (wrap `poll_messages`, `_send_message`, and any other session HTTP entry points).

### Option B — Single poller

Do not call **`poll_messages`** from command handlers for observe. Set state flags and let **`_poll_loop` only** drain KGS until `game_join_received` / move count predicate.

- **Pros:** Clear ownership of polling.
- **Cons:** Larger refactor; all command paths that poll must be audited.

### Option C — Manual mode only: one command processor

After polling threads start, **stop** calling `_process_monitor_command()` from the **main** manual loop so only **`_poll_loop`** processes commands.

- **Pros:** Reduces duplicate command entry.
- **Cons:** Does **not** fully fix races unless **no** nested `poll_messages` runs while `_poll_loop` could poll—so usually **pair with A** or B.

## Follow-up verification

1. Log **thread name/id** and **message types per poll** on each `poll_messages` return during observe.
2. After fix: confirm **no overlapping long-poll GETs** (timestamps / lock held).
3. Re-run observe stress / rapid observe to confirm stable full history.

## Related code references (Kgs-bot)

- `run_bot.py` — manual loop: `_process_monitor_command()` while `polling_thread` runs `_poll_loop`.
- `kgs_bot.py` — `_poll_loop` (~1114, ~1149); `observe_game` (~7994–8012); `_join_as_observer` (~5695+).
- `kgs_client.py` — `_send_message` (OK → no messages); `poll_messages` (GET).

## Related docs in this repo

- `docs/progress.md` — E2E move-history tests, timing (wait for state after observe).
- `CLAUDE.md` — `GAME_UPDATE` before `GAME_JOIN` handling, `processed_node_ids` (orthogonal to dual-poll race but same observation area).
