# tmux-agent-skills

OMP skills + standalone CLI for **tmux-agent-manager v3** — thin orchestration contract for multi-agent file-system IPC via Syncthing.

```
Manager:   poll status.json → dispatch TASK → monitor
Workers:   mailbox send/peek/check → self-report status
Syncthing: cross-machine delivery (no relay daemon)
```

## Contents

| Path | Purpose |
|---|---|
| `manager/SKILL.md` | Full Manager protocol (v2 mailbox, dispatch, monitoring) |
| `manager/OPERATIONS.md` | Operations guide (launch, reconcile, recovery) |
| `manager/CHEATSHEET.md` | Quick command reference |
| `worker/SKILL.md` | Worker protocol (INIT/TASK, mailbox, status lifecycle) |
| `tools/mailbox` | Standalone CLI — send/peek/check/claim/release/status/clear/stats (Python, zero deps) |
| `tools/mailbox-hook` | Runner integration — pending detection |

## Mailbox CLI

```
mailbox send    --from <id> --to <id> --subject "..." --body "..." --kind TASK [--reply-to <msg_id>]
mailbox peek    --worker <id>              # non-consuming: pending count + message previews
mailbox check   --worker <id>              # validate, archive (--json for machine output)
mailbox claim   --worker <id> --msg-id <id> # atomic claim → processing/ (exclusive)
mailbox release --worker <id> --msg-id <id> # release claim back to inbox
mailbox status  --worker <id> --state BUSY --current-task "..."
mailbox clear   --worker <id> --prune-corrupt --older-than-days 30
mailbox stats   --worker <id>              # inbox/archive/processing/_corrupt counts
```

**Message kinds:** TASK, REPORT, PROGRESS, EVIDENCE, QUESTION, RESPONSE, NOTICE.
**7 required fields:** `from`, `to`, `subject`, `body`, `kind`, `msg_id`, `created_at`.

Validation rules (enforced by `mailbox check`):
- All 7 fields present + kinds valid
- `msg_id` matches filename
- Recipient matches inbox owner (cross-write detection)
- No path separators in `msg_id`
- Malformed/corrupt → `_corrupt/` with stderr diagnostic

Configuration: `$MAILBOX_ROOT` env (defaults to `~/Dropbox/logseq/pages/mi-docs/_mailbox`).

## Installation

    git clone https://github.com/comicchang/tmux-agent-skills.git
    export PATH="$PATH:$(pwd)/tmux-agent-skills/tools"

## Notification Strategy

| Worker Type | Mechanism |
|---|---|
| Local (tmux pane) | OMP `agent_end` + 30s idle poll + optional send-keys wake |
| Remote (SSH) | OMP hook + periodic polling only (no send-keys) |
| All | Runner calls `mailbox peek` at task boundaries, `mailbox check` for consumption |

## Plugin Integration

The `omp-mailbox-plugin` provides zero-latency Bun.watch notification with a 30s timer fallback. It calls `mailbox peek` (non-consuming), deduplicates via `msg_id`, and injects summaries at safe agent boundaries.

## Directory Layout

```
$MAILBOX_ROOT/
  {worker_id}/
    inbox/        ← Others write here (Syncthing)
    archive/      ← Read + validated messages
    processing/   ← Claimed by consumer (exclusive, claim/release)
    _corrupt/     ← Unparseable messages
    status.json   ← {"state":"BUSY","current_task":"...","last_conclusion":"..."}
```

## License

MIT
