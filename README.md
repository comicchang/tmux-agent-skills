# tmux-agent-skills

OMP skills + standalone CLI for **tmux-agent-manager v3** — thin orchestration contract for multi-agent file-system IPC via Syncthing.

```
Manager:   poll status.json → dispatch TASK → monitor
Workers:   mailbox send/check → self-report status
Syncthing: cross-machine delivery (no relay daemon)
```

## Contents

| Path | Purpose |
|---|---|
| `manager/SKILL.md` | Full Manager protocol (v2 mailbox, dispatch, monitoring) |
| `manager/OPERATIONS.md` | Operations guide (launch, reconcile, recovery) |
| `manager/CHEATSHEET.md` | Quick command reference |
| `worker/SKILL.md` | Worker protocol (INIT/TASK, mailbox, status lifecycle) |
| `tools/mailbox` | Standalone CLI — send/check/clear/stats (Python, zero deps) |
| `tools/mailbox-hook` | Runner integration — pending detection |

## Mailbox CLI

```
mailbox send   --from <id> --to <id> --subject "..." --body "..."
mailbox check  --worker <id>              # read oldest, validate, archive
mailbox status --worker <id> --state BUSY --current-task "..."
mailbox clear  --worker <id> --prune-corrupt --older-than-days 30
mailbox stats  --worker <id>              # inbox/archive/corrupt counts
```

## Installation

    git clone https://github.com/comicchang/tmux-agent-skills.git
    export PATH="$PATH:$(pwd)/tmux-agent-skills/tools"

## Notification Strategy

| Worker Type | Mechanism |
|---|---|
| Local (tmux pane) | OMP `agent_end` + 30s idle poll + optional send-keys wake |
| Remote (SSH) | OMP hook + periodic polling only (no send-keys) |
| All | Runner calls `mailbox check` at task boundaries |

## Directory Layout

```
$MAILBOX_ROOT/
  {worker_id}/
    inbox/        ← Others write here (Syncthing)
    archive/      ← Read messages
    _corrupt/     ← Unparseable messages
    status.json   ← {"state":"BUSY","current_task":"...","last_conclusion":"..."}
```

## License

MIT
