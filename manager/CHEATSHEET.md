# tmux-agent-manager v2 Direct Inbox 速查
> Manager → `skill://tmux-agent-manager/` | Worker → `skill://tmux-agent-worker/`

## v2 Direct Inbox

```bash
# 先验证 ID
python3 scripts/tmux_worker.py mailbox-roster --config workers.toml

# Manager → Worker 正式 TASK（直写目标 inbox）
python3 scripts/tmux_worker.py mailbox-v2-send \
  --from manager --to <worker-id> --kind TASK \
  --subject "<task>" --body "<full task + acceptance>"

# 或直接用 standalone CLI（zero-dependency）
MAILBOX_ROOT=_mailbox/tools mailbox send \
  --from manager --to <worker-id> --kind TASK \
  --subject "<task>" --body "<full task>"
mailbox peek --worker <worker-id>       # 非消费查询
mailbox check --worker <worker-id> --json  # 消费一消息
mailbox claim --worker <worker-id> --msg-id <id>   # 独占认领
mailbox release --worker <worker-id> --msg-id <id> # 释放认领

# send-keys 只唤醒/steering
tmux send-keys -t <target> -l -- "MAILBOX_PENDING; check v2 inbox"
tmux send-keys -t <target> C-m

# 收件：每次一封，inbox → archive
python3 scripts/tmux_worker.py mailbox-v2-check --worker <id|manager> --json
python3 scripts/tmux_worker.py mailbox-v2-stats --worker <id|manager>
python3 scripts/tmux_worker.py mailbox-v2-clear --worker <id|manager>
```

目录：`_mailbox/<id>/{inbox,archive,processing,_corrupt}/`。Worker→Manager、Worker→Worker、Manager→Worker 正式内容全部 direct inbox；无 relay daemon、outbox、cursor。
7 种 kind：TASK, REPORT, PROGRESS, EVIDENCE, QUESTION, RESPONSE, NOTICE。
竞态保护：`mailbox claim` → `processing/` → `mailbox check`；`mailbox release` 回放。

## Notification reachability

- Local Worker (`ios-re`, `ios-shader`, `ohos-bin`): direct inbox is authoritative; `send-keys MAILBOX_PENDING` is an optional wake-up.
- Remote SSH Worker (`aosp`, `hyperos`, `ohos`): no local tmux socket; never use `send-keys` for Manager or peer communication. Mailbox-v2 + status.json polling is the complete communication path.
- Manager polls each `status.json` plus `mailbox-v2-stats` inbox count every 5 seconds. A growing count is pending work, not a new status field. `BUSY` remains busy until the Worker updates status.
- A successful local `send-keys` call proves neither delivery nor reading; only the mailbox file and later status/REPORT prove progress.

## Plugin integration

- `$OMP_WORKER_ID` must be set by the Worker launcher before OMP starts.
- `omp-mailbox-plugin` uses `mailbox peek` + Bun.watch (30s timer fallback), dedups via `msg_id`.
- Plugin is wake-only notification; Worker agent must still `mailbox claim → check` for consumption.

## Runner adapter mode

- Standalone CLI is authoritative; tmux/oh-my-pi, opencode, or another runner MAY invoke it at task start/end/idle/checkpoint without private hook coupling.
- Adapter may watch, validate, read→archive, inject, and call `status_update`; never run a second manual archive consumer.
- If no adapter is available, use one-message `mailbox-v2-check` plus `mailbox-v2-status`. Remote SSH uses mailbox/status only; local send-keys is optional wake.

## status.json

```bash
# TASK 开始
python3 scripts/tmux_worker.py mailbox-v2-status --worker <id> \
  --state BUSY --current-task "<one-line task>" --last-conclusion "<previous>"

# TASK 成功/阻塞结束（先发 REPORT）
python3 scripts/tmux_worker.py mailbox-v2-status --worker <id> \
  --state DONE --current-task "<task>" --last-conclusion "<brief result>"
python3 scripts/tmux_worker.py mailbox-v2-status --worker <id> \
  --state BLOCKED --current-task "<task>" --last-conclusion "<brief reason>"
```

`_mailbox/<id>/status.json` **恰好四字段**：`state`、`current_task`、`last_conclusion`、`updated_at`。Manager 每 5 秒读 status；`BUSY` 不派新任务，`DONE/BLOCKED` 立即收取 Manager inbox 的 REPORT。`STALE` 只做诊断，不等于 IDLE。

## Task headers

```text
# Role: SourceAnalysis
# Domain: aosp
# Requires: source-analysis
# Anchors: visibleRegion, occlusion
# Mode: cooperative

<task body and acceptance criteria>
```

## Polling

- Worker：任务前、主要阶段后、final REPORT 前、终态后；本地看到 `MAILBOX_PENDING` 可立即检查，远程即使无提示也必须主动 poll。
- Manager：派发前、等待循环、状态终态、每封消息处理后；同时看 status 和 inbox count。
- 每次处理一封，直到 inbox 为空；处理完成才 clear archive。

## Errors / Prevention

- `_corrupt/` 非空：记录并要求 sender 用 CLI 重发；不修 JSON。
- `.sync-conflict-*`：跳过并人工审计；不改名成正常消息。
- clock skew：按 mtime/实际到达处理；不信文件名时间排序。
- 永远用 CLI，永远先校验收件人，永远不覆盖已发送消息。
- capture-pane 不用于状态；status 是快照，REPORT 是完整结论。

## Legacy (v1)

```bash
python3 scripts/tmux_worker.py request --worker <id> --task-file t.txt --yes
python3 scripts/tmux_worker.py request-role --role <role> --task-file t.txt --yes
python3 scripts/tmux_worker.py batch-request --batch b.json --yes
python3 scripts/tmux_worker.py event-emit ...
python3 scripts/tmux_worker.py event-wait ...
python3 scripts/tmux_worker.py mailbox-send ...
python3 scripts/tmux_worker.py mailbox-check ...
python3 scripts/tmux_worker.py mailbox-relay ...
```

仅供尚未迁移 Worker。v1 outbox/relay/inbox、cursor 与 B-plane-only 状态不得用于新任务。
