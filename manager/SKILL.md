---
name: tmux-agent-manager
description: tmux-agent-manager v3 — 薄编排契约
---

# tmux-agent-manager v3 — 薄编排契约

> Worker 规则：`skill://tmux-agent-worker/` | 操作指南：`skill://tmux-agent-manager/OPERATIONS.md` | 速查：`CHEATSHEET.md`

## 1. 职责边界

本 skill **只编排**，不做领域研究或证据判断。Manager 可读 `workers.toml`、Worker 产物、`_mailbox/<session>/<agent>/status.json` 与自己的 session manager inbox；禁止用 `capture-pane` 判断状态。`status.json` 是当前状态快照，正式结论以 Worker 发往 Manager inbox 的 `REPORT` 为准。

## 2. 当前通信模型

| Direction | Primary path | Purpose |
|---|---|---|
| Manager→Worker | v2 mailbox direct inbox | 正式 TASK、补充材料、需留痕的指令 |
| Manager→Worker | `tmux send-keys` | 只发本地 Worker 的 `MAILBOX_PENDING` 或短 steering；不承载正式任务正文 |
| Worker→Manager | v2 mailbox direct inbox | `REPORT`、`PROGRESS`、`QUESTION`、`NOTICE` |
| Worker→Worker | v2 mailbox direct inbox | peer 问答、证据与复核请求；Syncthing 直接同步 |
| Worker→all observers | `_mailbox/<session>/<agent>/status.json` | `IDLE/BUSY/DONE/BLOCKED`、当前任务、最后结论 |

通知策略按部署位置区分：本地 Worker（ios-re、ios-shader、ohos-bin）可收到 `send-keys` 作为辅助唤醒，但 mailbox 才是可靠 payload；远程 SSH Worker（aosp、hyperos、ohos）无法可靠接收 Manager 的 send-keys，若没有 runner adapter，必须在 task start/end、阶段边界和长工具返回后主动轮询自己的 inbox。启用 framework-neutral adapter 时由 standalone CLI 完成 watch/peek→inject/status_update。Manager 对所有 Worker 都轮询 `status.json` 与 inbox 计数；send-keys 成功不代表远程送达。

## v2 Direct Inbox

目录是共享仓库根下的 `_mailbox/`，session 隔离：

```text
_mailbox/<session_id>/
  session.json   # {manager, agents, created_at}
  manager/
    inbox/        # 其他参与者直接写入
    processing/   # read 后自动声明，finalize 后移到 archive
    archive/      # 已处理消息
    _corrupt/     # 解析或自校验失败消息
  <agent>/
    inbox/
    processing/
    archive/
    _corrupt/
    status.json   # Agent 自报状态
```

```bash
# 先用 workers.toml 真源确认收件人；禁止猜 ID
scripts/tmux_worker.py mailbox-roster --config workers.toml

# Manager 正式派 TASK；正文必须完整、可独立执行
scripts/tmux_worker.py mailbox send \
  --session <session-id> --from manager --to <agent-id> --kind TASK \
  --subject "<short task>" --body "<full task and acceptance criteria>"

# send-keys 仅唤醒本地 Worker；远程 Worker 完全依赖主动轮询
tmux send-keys -t <target> -l -- "MAILBOX_PENDING; check v2 inbox"
tmux send-keys -t <target> C-m

# Manager 读取自己的 inbox：read (inbox→processing, auto-claim) → 处理 → finalize (processing→archive)
scripts/tmux_worker.py mailbox read \
  --session <session-id> --agent manager --owner manager [--json]
scripts/tmux_worker.py mailbox finalize \
  --session <session-id> --agent manager --msg-id <id> --owner manager

# 非消费查看、统计与清理
scripts/tmux_worker.py mailbox peek --session <session-id> --agent manager [--json]
scripts/tmux_worker.py mailbox stats --session <session-id> --agent manager  # shows all4 dirs: inbox/processing/archive/_corrupt
scripts/tmux_worker.py mailbox clear --session <session-id> --agent manager

# 崩溃恢复：将过期 processing 消息放回 inbox
scripts/tmux_worker.py mailbox recover-stale --session <session-id> --agent manager
```

远程 SSH Worker 的可靠通知路径只有共享 inbox + Worker 主动轮询；不要假设 Manager 能把 send-keys 注入远程 agent。

## Plugin and runner integration (preferred, framework-neutral)

The mailbox behavior is implemented by standalone CLI functions (`mailbox send`, `mailbox read`, `mailbox finalize`, `mailbox peek`, `mailbox stats`, `mailbox status`, `mailbox clear`, `mailbox recover-stale`). A tmux/oh-my-pi plugin, opencode adapter, or another runner MAY invoke `mailbox peek` at safe boundaries for notification; the **plugin only notifies — never consumes**. The agent reads via `mailbox read`. No skill depends on private runner hooks.

Manager still polls each `status.json` and inbox statistics for observability. Adapter injection is not a substitute for final REPORT or artifact verification. If no adapter is available, the runner calls the standalone CLI at the documented boundaries. Remote SSH Workers use the plugin/direct Syncthing path only; Manager send-keys remains local-only.

v2 消息固定 8 个必填字段：`session_id`、`from`、`to`、`subject`、`body`、`kind`、`msg_id`、`created_at`。3 个可选关联字段：`reply_to`、`run_id`、`request_id`。7 种 kind：`TASK`、`REPORT`、`PROGRESS`、`EVIDENCE`、`QUESTION`、`RESPONSE`、`NOTICE`。文件名与 `msg_id` 一致；消息不可原地修改，纠正内容必须发新消息并用 `--reply-to <msg_id>` 回链。

消费流程：`mailbox read`（inbox→processing，按 owner+lease 自动声明）→ agent 处理 → `mailbox finalize`（processing→archive，校验 owner）；`mailbox release` 可放回 inbox；`mailbox recover-stale` 将过期 processing（300s lease）自动恢复到 inbox。

## 3. status.json 状态快照

每个 Agent 只写自己的 `_mailbox/<session>/<agent>/status.json`，且文件最多四个字段：

```json
{
  "state": "BUSY",
  "current_task": "verify shadow paths",
  "last_conclusion": "traditional and SDF paths are separate",
  "updated_at": "2026-07-22T15:30:00Z"
}
```

- `state`: `IDLE | BUSY | DONE | BLOCKED`。
- `current_task`: 一句话任务摘要；不得塞任务全文。
- `last_conclusion`: 一句话最新结论或阻断原因。
- `updated_at`: UTC，仅用于新鲜度诊断，不用于跨机器消息排序。

Manager 派发前必须读取目标 status：只有 `IDLE/DONE/BLOCKED` 且已处理上一条 REPORT 才可派新任务。`BUSY` 禁止并发派发。状态过旧时先检查 inbox、Syncthing 与 Worker 可达性，不能凭旧值宣告空闲。

## 4. 派发、轮询与收件

1. 用 `mailbox-roster` 验证收件人并读其 `status.json`。
2. 用 `mailbox send --session <id> --kind TASK` 直写目标 inbox。仅对本地 Worker 可额外发短 `send-keys` 唤醒；远程 Worker 不依赖该提示。
3. 每 5 秒轮询目标 `status.json` 和 `mailbox stats` 的 inbox 数量；值由 `BUSY` 转为 `DONE/BLOCKED` 后，轮询 Manager inbox 收取对应 `REPORT`。
4. Worker 无论本地还是远程都在 task start/end、阶段边界和长工具返回后主动 `mailbox read`。Manager 自己在派发前、等待期间每个检查周期、处理完一封消息后再次 `mailbox read` Manager inbox，直到为空。
5. 读完 artifact/REPORT、安排后续后，再 `mailbox finalize` 归档，最后 `mailbox clear`；不得在消息尚未处理时 clear。

状态快照与 REPORT 不一致时：以 REPORT 作为结论内容，以最新可验证的 `status.json.updated_at` 作为活跃度快照；保留冲突并要求 Worker 发纠正消息，禁止静默覆盖。

## 5. 工作模式

工作模式仍由 TASK 头部 `# Mode` / `# Mode-Role` 决定。candidate/pilot/mentor 等所有协作信息均走 v2 direct inbox。Reviewer/verifier 必须等目标 `status.json` 终态且收到 REPORT/产物后再开始；不能只看到 `DONE` 字样就越过报告验收。

## 6. 错误处理与恢复

- **Corrupt message**：`mailbox read` 将坏 JSON 或 `msg_id`/文件名不一致的文件移到 `_corrupt/`。Manager 看到 `corrupt > 0` 必须记录文件名、通知发送方重发新消息；不得手改原 JSON。
- **Syncthing conflict**：任何 `.sync-conflict-*` 文件都不是有效消息。保留原件，比较双方内容，由发送方通过 CLI 发一封新消息；不得 rename 成正常消息伪造投递。
- **Clock skew**：处理顺序以 inbox 文件 mtime/实际可见顺序为准，`created_at` 和文件名时间只做诊断。明显偏差时记录 `CLOCK_SKEW`，不要重写时间戳。
- **Stale status / pending inbox**：`updated_at` 超过预期 SLA 时状态为 `STALE` 诊断，不等同 `IDLE` 或 `BLOCKED`。Manager 先检查 inbox count、Syncthing 和 pane liveness；本地可再发 wake，远程只能等待 Worker 的下一次主动 poll。
- **Missing recipient**：发送失败即重新运行 `mailbox-roster`/检查 `_mailbox/<session>/<agent>/inbox`，不创建拼错的目录。
- **Crash recovery**：发现 `processing/` 中有过期消息（超过 300s lease），运行 `mailbox recover-stale --session <id> --agent <id>` 自动放回 inbox；不手移文件。

## 7. 预防规则

- **永远不要手写 JSON**；只能用 `mailbox send` 和 `mailbox status`，二者负责原子写入。
- 每次发送前验证 `--to` 在 roster 中且与目标 inbox owner 一致。
- 不复用、覆盖或编辑已发送消息；更正用新消息 + `--reply-to`。
- 不用文件名时间排序业务优先级，不用 capture-pane 推断状态。
- 不把大产物塞进 body；body 只放摘要和可定位的 artifact 引用。
- `mailbox clear` 只清 archive，且只在任务/收件处理完整结束后执行。
- 远程 Worker 的可见性以 status/inbox 轮询为准；send-keys 成功返回不代表消息已被 agent 看到。

## 8. 启动与故障边界

Marker 与 pane liveness 仍用于启动：`PANE_ALIVE → SHELL_READY → CWD_VERIFIED → AGENT_STARTED`。启动完成后 Worker 通过 status 写 `IDLE`。Manager 失联、同步失败或工具不可用时，Worker 保存产物、发送 `REPORT/NOTICE`，并将 status 更新为 `BLOCKED`；禁止硬 kill。

## Legacy (v1)

v1 架构使用以下已废弃概念，全部由 v2 `status.json` + direct inbox 取代：

- **control envelope**（A-plane）：旧 control/steering 下行指令封装
- **B-plane**：旧 event-emit 生命周期事件（ACK/DONE/BLOCKED/WORKING），曾是 Manager 获取 Worker 状态的唯一来源
- **C-plane**：旧消息通道，被 v2 direct inbox 取代
- **mailbox/outbox → relay → mailbox/inbox**：旧消息中继路径
- **cursor / unread / mark-read**：旧消息消费状态跟踪

下列命令仅供尚未迁移的 Worker 过渡使用，不得用于新的 v2 工作流：`request`、`request-role`、`batch-request`、`event-emit`、`event-wait`、`mailbox-send`、`mailbox-check`、`mailbox-relay`、`manager-poll`。

兼容期若 v1 Worker 仍发事件，Manager 可审计事件并读取其旧 outbox，但不得把 v1 relay daemon 当成 v2 前提；迁移完成后由 v2 `status.json` + direct inbox 接管。
---

- 操作指南：`skill://tmux-agent-manager/OPERATIONS.md`
- Worker 协议：`skill://tmux-agent-worker/`
- 速查：`CHEATSHEET.md`
