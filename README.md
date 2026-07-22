# tmux-agent-skills

OMP skills for tmux-agent-manager (v3) and tmux-agent-worker — a thin orchestration contract for multi-agent file-system IPC.

## Structure

```
manager/          # Manager skill (orchestrator)
  SKILL.md        # Full protocol reference
  CHEATSHEET.md   # Quick command reference
worker/           # Worker skill (agent)
  SKILL.md        # Agent protocol + mailbox usage
tools/            # Standalone CLI (no dependencies)
  mailbox         # v2 direct-inbox send/check/clear/stats
```

## Mailbox v2 — Direct Inbox

Workers communicate via a shared Syncthing-synchronized `_mailbox/` directory. No relay daemon needed.

```bash
# Send to peer
mailbox send --from ios-re --to ios-shader --subject "..." --body "..."

# Check inbox
mailbox check --worker ios-shader

# Update status (visible to all peers)
mailbox status --worker ios-shader --state BUSY --current-task "glass shader"

# Clear archive
mailbox clear --worker ios-shader
```

## Installation

```bash
# Register as OMP skill
ln -s $(pwd) ~/.omp/skills/tmux-agent-manager
ln -s $(pwd) ~/.omp/skills/tmux-agent-worker

# Make CLI available
export PATH="$PATH:$(pwd)/tools"
```

## License

MIT
