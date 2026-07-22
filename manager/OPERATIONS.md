# tmux-agent-manager v3 — Operations

> 协议核心: `skill://tmux-agent-manager/` | Worker: `skill://tmux-agent-worker/` | 速查: `CHEATSHEET.md`

## 1. 配置与目录

`workers.toml` 仍是 worker id、target、role、domain 和 capability 的唯一真源。路径使用 `$HOME` 或 `~`，禁止硬编码个人主目录。

v2 mailbox 位于共享仓库：

```text
_mailbox/
  manager/{inbox,archive,_corrupt}/
  <worker-id>/{inbox,archive,_corrupt}/
  <worker-id>/status.json
```

Syncthing 同步共享根。所有参与者直接写**收件人** inbox；没有 outbox、relay daemon、cursor 或已读 ACK 文件。`~/.drafts/tmux-workers/<id>/ipc` 与事件文件仅保留给启动诊断和 v1 兼容。

```bash
scripts/tmux_worker.py validate --config workers.toml
scripts/tmux_worker.py register --config workers.toml
scripts/tmux_worker.py mailbox-roster --config workers.toml
```

注册失败、收件人不在 roster 或 `_mailbox/<id>/inbox` 不存在时停止发送，禁止自行创建一个“看起来正确”的 worker id。

## 2. 启动链

启动仍使用 marker，不用 capture-pane 或固定 sleep 判定 readiness：

1. `PANE_ALIVE`：只验证 pane 进程存活。
2. `SHELL_READY`：launch marker 校验 hostname。
3. `CWD_VERIFIED`：launch marker 校验物理 cwd。
4. `AGENT_STARTED`：仅 liveness。
5. Worker 初始化后写 `_mailbox/<id>/status.json` 为 `IDLE`；这才是 v2 可调度快照。

```bash
scripts/tmux_worker.py launch --worker <id> --config workers.toml --timeout 120
scripts/tmux_worker.py init --worker <id> --config workers.toml --timeout 60 --attempts 2
```

INIT 的旧 ACK 文件可以作为兼容诊断，但 Manager 不得用 terminal 文本补认 ready，也不得用 capture-pane 判断 IDLE/BUSY。

## v2 Direct Inbox

### 发送

```bash
scripts/tmux_worker.py mailbox-v2-send \
  --from manager --to aosp --kind TASK \
  --subject "Verify occlusion path" \
  --body "# Role: SourceAnalysis
# Domain: aosp
# Requires: source-analysis
# Anchors: visibleRegion, occlusion

Trace the current source and return a REPORT with artifact references."
```

`--from` 与 `--to` 必须是 roster 中的准确 ID（`manager` 除外）；`--subject` 简短，`--body` 必须自包含任务和验收标准。正式 TASK 发送后，仅对本地 Worker 可用 `send-keys` 唤醒：

```bash
tmux send-keys -t <target> -l -- "MAILBOX_PENDING; check v2 inbox"
tmux send-keys -t <target> C-m
```

远程 SSH Worker（aosp、hyperos、ohos）无法使用 Manager 或 peer 的 send-keys（无本地 tmux socket）；它们的全部通信依赖共享 inbox 的 mailbox-v2-send 与 status.json 轮询。send-keys 只做本地 Worker 的辅助 wake/steering，不承载正式任务、不作为送达或状态证据。

### 接收

```bash
scripts/tmux_worker.py mailbox-v2-check --worker manager --json
scripts/tmux_worker.py mailbox-v2-stats --worker manager
scripts/tmux_worker.py mailbox-v2-clear --worker manager
```

`mailbox-v2-check` 每次读取最早一封、验证 `msg_id` 与文件名并原子移动到 archive；无消息时无输出。处理完成后继续 check，直到 inbox 为空。archive 是当前收件周期的回看区，只能在 REPORT/artifact 已读并安排后续后 clear。

### 消息格式与 kind

7 个必填字段：`from`、`to`、`subject`、`body`、`created_at`、`kind`、`msg_id`。常用 kind：`TASK`、`REPORT`、`PROGRESS`、`EVIDENCE`、`QUESTION`、`RESPONSE`、`NOTICE`。`priority`、`reply_to`、`refs` 可选。消息不可变；补充或纠错必须发新消息并回链原 `msg_id`。

## Runner adapter integration (preferred, framework-neutral)

The standalone CLI is the protocol boundary. A tmux/oh-my-pi plugin, opencode adapter, or another runner MAY watch inboxes and invoke `mailbox-v2-check`/`mailbox-v2-status` at task start/end, idle, and checkpoints. It must not depend on private runner hooks, must not run concurrently with a manual consumer, and must use the same validation and atomic read→archive path.

Manager responsibilities remain: poll every Worker `status.json` and `mailbox-v2-stats` for observability, verify reports/artifacts, and resolve `_corrupt/` or `.sync-conflict-*`. Adapter injection is not proof of report acceptance. For remote SSH Workers, adapter/direct inbox is the complete notification path; they have no local tmux socket and must not use send-keys. Local Workers may receive `MAILBOX_PENDING` as an optional wake.

## 4. status.json 监控

Worker 使用：

```bash
scripts/tmux_worker.py mailbox-v2-status --worker <id> \
  --state BUSY \
  --current-task "verify occlusion path" \
  --last-conclusion "previous task complete"
```

文件固定四字段：`state`、`current_task`、`last_conclusion`、`updated_at`。state 仅允许 `IDLE/BUSY/DONE/BLOCKED`。Worker 在 TASK 开始写 BUSY，在 final REPORT 后写 DONE/BLOCKED。Manager 与 peer 只读，不修改。

Manager 监控循环：

1. 每 5 秒读取每个 `_mailbox/<id>/status.json`，同时读取 `mailbox-v2-stats` 的 inbox/archive/corrupt 计数；计数是 pending 诊断，不写进四字段 status。
2. 若 plugin 健康，plugin 负责 read→archive、边界注入和 BUSY/DONE/BLOCKED 更新；Manager 仍核对 status 与 REPORT。若 plugin 不健康，inbox count 增长时本地可发 wake，远程不依赖 send-keys，等待 Worker 的 manual fallback poll。
3. DONE/BLOCKED：立即 drain Manager inbox，读取 final REPORT 和 artifact；收件后才能派下一任务。
4. IDLE：可派发，但若有未处理 REPORT/archive，先完成收件。
5. `updated_at` 超过同步 SLA：标记 `STALE` 诊断，检查 Syncthing、mailbox stats 与 pane liveness；STALE 不等于 IDLE。

`last_conclusion` 是快速摘要，不替代 REPORT。状态与 REPORT 矛盾时保留两者并请求 Worker 发纠正消息；禁止根据 capture-pane 猜谁更新。

## 5. 稳定轮询

- Worker 在 plugin 模式下由 plugin 在安全边界 watch/inject/archive/status-update；Worker 仍审阅注入内容。manual fallback 才需要在任务开始、主要阶段、final REPORT 前、终态后检查 inbox；本地看到 `MAILBOX_PENDING` 可立即检查，远程必须完全依赖 mailbox + status.json，不能使用 send-keys。
- Manager 在派发前、等待循环、看到状态终态、处理每封消息后检查自己的 inbox；inbox count 只作 pending 提示，不改 status schema。
- 一次只处理一封，处理完成后再 check；这样不需要 cursor，也不会因一次巨大 JSON 数组漏掉中间消息。
- 外部工具不可中断时，在调用前后轮询；不要用固定 sleep 替代检查。
- 业务顺序不依赖文件名或发送方时钟；按 inbox mtime/实际到达读取。

## 6. 完成、阻塞与验收

成功顺序：artifact 完成并校验 → Worker final REPORT → Worker status DONE → Manager 收件与 review → 清 archive → 下一 TASK。

阻塞顺序：保存已有 artifact → Worker REPORT/NOTICE 写明 reason 与缺失前提 → status BLOCKED → Manager 收件并决定恢复/重派。

Manager 不把 status DONE 当作 artifact 已验证；必须读取 REPORT、验证引用路径/size/hash，并完成技术 review。也不把缺失/过期 status 自动当 BLOCKED。

## 7. 错误处理

### Corrupt message

解析失败、必填字段错误或 `msg_id` 与文件名不一致的消息移到 `_corrupt/`。运行 `mailbox-v2-stats` 发现 `corrupt > 0` 后：记录原文件名 → 通知 sender 用 CLI 发新消息 → 保留坏文件供审计。禁止直接修 JSON 后放回 inbox。

### Syncthing conflict

`.sync-conflict-*` 永远不作为正常消息处理。比较原件与冲突件，确定 sender 后要求新发；不通过改名“选胜者”。同一结论的重复新消息按应用层幂等处理。

### Clock skew

`created_at`/文件名时间是诊断字段。顺序以 inbox mtime 与实际到达为准；偏差明显时记录 `CLOCK_SKEW` 并修主机时间，绝不改已发送消息时间。

### Missing recipient / sync failure

先 `mailbox-roster`，再确认目标 inbox 已同步。发送失败不 fallback 到相似 worker、手写目录或旧 relay。Worker 无法写 status/REPORT 时保存 artifact，并使用短 send-keys 通知 `MAILBOX_SYNC_FAILED`，随后停止扩展。

## 8. 重新初始化与恢复

Worker 不遵守 v2（手写 JSON、未 poll、未维护 status）时先轻量 `init --worker <id>`，随后发送一个 v2 mailbox 验证 TASK。验证标准：status `BUSY→DONE|BLOCKED`、Manager 收到 schema-valid REPORT、Worker inbox/archive 行为正确。

轻量无效才 `/new` 后重启。恢复时先检查 `_corrupt/`、archive、inbox 和 status 新鲜度；不得以 capture-pane 输出补认任何状态。

## 9. 预防清单

- CLI 原子写入；永远不手写 mailbox/status JSON。
- `mailbox-roster` 验证收件人；不猜、不 swap。
- formal TASK 走 mailbox；send-keys 只 wake/steering。
- Worker/Manager 都按边界轮询；不用 relay daemon、cursor 或 capture-pane。
- 不覆盖消息；纠正发新消息 + `reply_to`。
- archive 只在确认处理完成后 clear；`_corrupt/` 不自动删除。
- status 只四字段；完整结论只放 REPORT/artifact。

## Legacy (v1)

以下命令保留给尚未迁移的 Worker：

```bash
scripts/tmux_worker.py request --worker <id> --task-file task.txt
scripts/tmux_worker.py request-role --role <role> --task-file task.txt
scripts/tmux_worker.py batch-request --batch-file batch.json
scripts/tmux_worker.py event-emit ...
scripts/tmux_worker.py event-wait ...
scripts/tmux_worker.py mailbox-send ...
scripts/tmux_worker.py mailbox-check ...
scripts/tmux_worker.py mailbox-relay ...
```

v1 使用 control envelope、B-plane ACK/DONE/BLOCKED、`mailbox/outbox`→relay→`mailbox/inbox`、cursor/unread/mark-read。兼容期可读取这些记录做审计，但新的 v2 消息和 TASK 不得经过 v1 relay，也不得把 B-plane 恢复为唯一状态源。
