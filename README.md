# tmux-agent-skills

OMP skills + standalone CLI for **tmux-agent-manager v3** — session-based direct-inbox IPC via Syncthing.

```
Manager:   session-init → dispatch TASK → poll status → manager-wait → manager-ack
Workers:   mailbox send/peek/read/finalize/release/recover-stale → self-report status
Syncthing: cross-machine delivery (no relay daemon)
```

## Directory Layout

```
$MAILBOX_ROOT/
  <session_id>/
    session.json          # {manager, agents, created_at}
    manager/inbox|processing|archive/
    <agent>/inbox|processing|archive/status.json
```

`.drafts/` is for agent work artifacts; `.mailbox/` is for agent-to-agent communication.

## Contents

| Path | Purpose |
|---|---|
| `manager/SKILL.md` | Full Manager protocol |
| `manager/OPERATIONS.md` | Operations guide |
| `manager/CHEATSHEET.md` | Quick command reference |
| `worker/SKILL.md` | Worker protocol |
| `tools/mailbox` | Standalone CLI — all commands (Python, zero deps) |
| `tools/mailbox-hook` | Runner integration — pending detection |

## Mailbox CLI

```
mailbox session-init  --session <id> --manager <id> --agents <id,...>
mailbox send          --session <id> --from <id> --to <id> --subject "..." --body "..."
                      --kind TASK [--reply-to <id>] [--run-id <id>] [--request-id <id>]
mailbox peek          --session <id> --agent <id>              # non-consuming summary
mailbox read          --session <id> --agent <id> --owner <id>   # reads + auto-claims oldest
mailbox finalize      --session <id> --agent <id> --msg-id <id> --owner <id>
mailbox release       --session <id> --agent <id> --msg-id <id>
mailbox recover-stale --session <id> --agent <id>              # recover expired claims
mailbox check         --session <id> --agent <id>              # validate + archive (legacy)
mailbox status        --session <id> --agent <id> --state BUSY
mailbox clear         --session <id> --agent <id> [--prune-stale]
mailbox stats         --session <id> --agent <id>
```

**Message kinds**: TASK, REPORT, PROGRESS, EVIDENCE, QUESTION, RESPONSE, NOTICE.
**8 required fields**: `session_id`, `from`, `to`, `subject`, `body`, `kind`, `msg_id`, `created_at`.
**Optional correlation**: `reply_to`, `run_id`, `request_id`.

**Two-stage consumption**: `read` (inbox→processing, auto-claim) → `finalize` (processing→archive, validates ownership). `release` returns to inbox. `recover-stale` recovers expired claims (default 300s lease).

## Installation

    git clone https://github.com/comicchang/tmux-agent-skills.git ~/src/tmux-agent-skills
    ln -sf ~/src/tmux-agent-skills/tools/mailbox ~/.claude/bin/mailbox
    ln -sf ~/src/tmux-agent-skills/tools/mailbox-hook ~/.claude/bin/mailbox-hook

## Notification Strategy

| Role | Mechanism |
|---|---|
| Local Worker | OMP `agent_end` + 30s idle poll + optional send-keys wake |
| Remote Worker | OMP hook + periodic polling only (no send-keys) |
| Manager | `manager-poll --watch` + `manager-wait` + `manager-ack` |

## License

MIT
