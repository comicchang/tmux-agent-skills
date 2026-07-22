# tmux-agent-skills

OMP skills + standalone CLI for **tmux-agent-manager v3** — a thin orchestration contract for multi-agent file-system IPC via Syncthing.

## Contents

```
manager/
  SKILL.md         # Full protocol reference (v2 mailbox, status.json, polling)
  OPERATIONS.md    # Manager operations (dispatch, monitor, recovery)
  CHEATSHEET.md    # Quick command reference
worker/
  SKILL.md         # Agent protocol (mailbox, status, notification rules)
tools/
  mailbox          # Standalone CLI — send/check/clear/stats (Python, zero deps)
  mailbox-hook     # Runner integration hook — pending detection
```

## Mailbox CLI

```bash
# Send to peer
./tools/mailbox send --from ios-re --to ios-shader --subject "..." --body "..."

# Check inbox (reads oldest, validates, moves to archive)
./tools/mailbox check --worker ios-shader

# Update status (visible to all peers)
./tools/mailbox status --worker ios-shader --state BUSY --current-task "glass shader"

# Clear archive + prune corrupt messages
./tools/mailbox clear --worker ios-shader --prune-corrupt --older-than-days 30

# Show inbox/archive/corrupt counts
./tools/mailbox stats --worker ios-shader
```

## Architecture

```
Message flow (v2 direct inbox):
  Worker A → mailbox send → $MAILBOX_ROOT/{to}/inbox/{from}_{ts}.json
                                ↓ Syncthing
  Worker B → agent_end hook → auto check inbox → inject context

Status monitoring:
  Worker → mailbox status → $MAILBOX_ROOT/{worker}/status.json
  Manager → periodic poll → detect idle/stale workers
```

## Notification Strategy

| Worker | Mechanism |
|---|---|
| **Local (tmux pane)** | OMP `agent_end` hook + 30s `ctx.setInterval` idle polling + optional `send-keys` wake |
| **Remote (SSH)** | OMP hook + periodic polling only (no send-keys) |
| **All** | Runner calls `mailbox check` at task start/end boundaries |

## Configuration

| Env | Description |
|---|---|
| `MAILBOX_ROOT` | Path to shared mailbox root (Syncthing-synced) |
| `OMP_WORKER_ID` | This worker's ID |

## License

MIT
