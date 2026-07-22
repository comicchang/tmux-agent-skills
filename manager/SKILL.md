---
name: tmux-agent-manager
description: tmux-agent-manager v3 — 薄编排契约
---

# tmux-agent-manager v3 — 薄编排契约

> Worker 规则：`skill://tmux-agent-worker/` | 操作指南：`skill://tmux-agent-manager/OPERATIONS.md` | 速查：`CHEATSHEET.md`

## 1. 职责边界

本 skill **只编排**，不做领域研究或证据判断。Manager 可读 `workers.toml`、Worker 产物、`_mailbox/*/status.json` 与自己的 v2 inbox；禁止用 `capture-pane` 判断状态。`status.json` 是当前状态快照，正式结论以 Worker 发往 Manager inbox 的 `REPORT` 为准。

## 2. 当前通信模型

| Direction | Primary path | Purpose |
|---|---|---|
| Manager→Worker | v2 mailbox direct inbox | 正式 TASK、补充材料、需留痕的指令 |
| Manager→Worker | `tmux send-keys` | 只发本地 Worker 的 `MAILBOX_PENDING` 或短 steering；不承载正式任务正文 |
| Worker→Manager | v2 mailbox direct inbox | `REPORT`、`PROGRESS`、`QUESTION`、`NOTICE` |
| Worker→Worker | v2 mailbox direct inbox | peer 问答、证据与复核请求；Syncthing 直接同步，无 relay |
| Worker→all observers | `_mailbox/<id>/status.json` | `IDLE/BUSY/DONE/BLOCKED`、当前任务、最后结论 |

B-plane 事件仍可用于兼容旧 Worker、事件审计和启动诊断，但**不再是 Manager 获取 Worker 状态的唯一来源**。当前工作状态首先读 `status.json`，不得回退到 terminal 文本或 capture-pane。

历史兼容术语：A-plane 是旧 control/steering 下行，B-plane 是旧 event-emit 生命周期事件，C-plane 是消息通道；v2 direct inbox 取代 C-plane outbox/relay，但保留这些术语帮助审计旧记录。

通知策略按部署位置区分：本地 Worker（ios-re、ios-shader、ohos-bin）可收到 `send-keys` 作为辅助唤醒，但 mailbox 才是可靠 payload；远程 SSH Worker（aosp、hyperos、ohos）无法可靠接收 Manager 的 send-keys，若没有 runner adapter，必须在 task start/end、阶段边界和长工具返回后主动轮询自己的 inbox。启用 framework-neutral adapter 时由 standalone CLI 完成 watch/read→archive/inject/status_update。Manager 对所有 Worker 都轮询 `status.json` 与 inbox 计数；send-keys 成功不代表远程送达。

## v2 Direct Inbox

目录是共享仓库根下的 `_mailbox/`：

```text
_mailbox/<recipient>/
  inbox/        # 其他参与者直接写入
  archive/      # 本次任务已读消息
  _corrupt/     # 解析或自校验失败消息
  status.json   # Worker 自报状态
```

```bash
# 先用 workers.toml 真源确认收件人；禁止猜 ID
scripts/tmux_worker.py mailbox-roster --config workers.toml

# Manager 正式派 TASK；正文必须完整、可独立执行
scripts/tmux_worker.py mailbox-v2-send \
  --from manager --to <worker-id> --kind TASK \
  --subject "<short task>" --body "<full task and acceptance criteria>"

# send-keys 仅唤醒本地 Worker；远程 Worker 完全依赖主动轮询
tmux send-keys -t <target> -l -- "MAILBOX_PENDING; check v2 inbox"
tmux send-keys -t <target> C-m

# Manager 读取自己的 inbox；每次读取并归档最早一封
scripts/tmux_worker.py mailbox-v2-check --worker manager --json
scripts/tmux_worker.py mailbox-v2-stats --worker manager
scripts/tmux_worker.py mailbox-v2-clear --worker manager
```

远程 SSH Worker 的可靠通知路径只有共享 inbox + Worker 主动轮询；不要假设 Manager 能把 send-keys 注入远程 agent。

## Plugin and runner integration (preferred, framework-neutral)

The mailbox behavior is implemented by standalone CLI functions (`mailbox-v2-check`, `mailbox-v2-send`, `mailbox-v2-clear`, `mailbox-v2-stats`, `mailbox-v2-status`). A tmux/oh-my-pi plugin, opencode adapter, or another runner MAY invoke these tools at safe boundaries and optionally watch the inbox; no skill depends on private runner hooks. The adapter must validate, atomically read→archive, inject only at safe boundaries, and call `status_update` for `BUSY/DONE/BLOCKED`.

Manager still polls each `status.json` and inbox statistics for observability. Adapter injection is not a substitute for final REPORT or artifact verification. If no adapter is available, the runner calls the standalone CLI at the documented boundaries. Remote SSH Workers use the plugin/direct Syncthing path only; Manager send-keys remains local-only.

v2 消息固定 7 个必填字段：`from`、`to`、`subject`、`body`、`created_at`、`kind`、`msg_id`。文件名与 `msg_id` 一致；消息不可原地修改，纠正内容必须发新消息并用 `--reply-to` 回链。

## 3. status.json 状态快照

每个 Worker 只写自己的 `_mailbox/<worker-id>/status.json`，且文件最多四个字段：

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
2. 用 `mailbox-v2-send --kind TASK` 直写目标 inbox。仅对本地 Worker 可额外发短 `send-keys` 唤醒；远程 Worker 不依赖该提示。
3. 每 5 秒轮询目标 `status.json` 和 `mailbox-v2-stats` 的 inbox 数量；值由 `BUSY` 转为 `DONE/BLOCKED` 后，轮询 Manager inbox 收取对应 `REPORT`。
4. Worker 无论本地还是远程都在 task start/end、阶段边界和长工具返回后主动 `mailbox-v2-check`。Manager 自己在派发前、等待期间每个检查周期、处理完一封消息后再次检查 Manager inbox，直到为空。
5. 读完 artifact/REPORT、安排后续后，再清 archive；不得在消息尚未处理时 clear。

状态快照与 REPORT 不一致时：以 REPORT 作为结论内容，以最新可验证的 `status.json.updated_at` 作为活跃度快照；保留冲突并要求 Worker 发纠正消息，禁止静默覆盖。

## 5. 工作模式

工作模式仍由 TASK 头部 `# Mode` / `# Mode-Role` 决定。candidate/pilot/mentor 等所有协作信息均走 v2 direct inbox。Reviewer/verifier 必须等目标 `status.json` 终态且收到 REPORT/产物后再开始；不能只看到 `DONE` 字样就越过报告验收。

## 6. 错误处理与恢复

- **Corrupt message**：`mailbox-v2-check` 将坏 JSON或 `msg_id`/文件名不一致的文件移到 `_corrupt/`。Manager 看到 `corrupt > 0` 必须记录文件名、通知发送方重发新消息；不得手改原 JSON。
- **Syncthing conflict**：任何 `.sync-conflict-*` 文件都不是有效消息。保留原件，比较双方内容，由发送方通过 CLI 发一封新消息；不得 rename 成正常消息伪造投递。
- **Clock skew**：处理顺序以 inbox 文件 mtime/实际可见顺序为准，`created_at` 和文件名时间只做诊断。明显偏差时记录 `CLOCK_SKEW`，不要重写时间戳。
- **Stale status / pending inbox**：`updated_at` 超过预期 SLA 时状态为 `STALE` 诊断，不等同 `IDLE` 或 `BLOCKED`。Manager 先检查 inbox count、Syncthing 和 pane liveness；本地可再发 wake，远程只能等待 Worker 的下一次主动 poll。
- **Missing recipient**：发送失败即重新运行 `mailbox-roster`/检查 `_mailbox/<id>/inbox`，不创建拼错的目录。

## 7. 预防规则

- **永远不要手写 JSON**；只能用 `mailbox-v2-send` 和 `mailbox-v2-status`，二者负责原子写入。
- 每次发送前验证 `--to` 在 roster 中且与目标 inbox owner 一致。
- 不复用、覆盖或编辑已发送消息；更正用新消息 + `--reply-to`。
- 不用文件名时间排序业务优先级，不用 capture-pane 推断状态。
- 不把大产物塞进 body；body 只放摘要和可定位的 artifact 引用。
- `mailbox-v2-clear` 只清 archive，且只在任务/收件处理完整结束后执行。
- 远程 Worker 的可见性以 status/inbox 轮询为准；send-keys 成功返回不代表消息已被 agent 看到。

## 8. 启动与故障边界

Marker 与 pane liveness 仍用于启动：`PANE_ALIVE → SHELL_READY → CWD_VERIFIED → AGENT_STARTED`。启动完成后 Worker 通过 status 写 `IDLE`。Manager 失联、同步失败或工具不可用时，Worker 保存产物、发送 `REPORT/NOTICE`，并将 status 更新为 `BLOCKED`；禁止硬 kill。

## Legacy (v1)

下列命令仅供尚未迁移的 Worker 过渡使用：`request`、`request-role`、`batch-request`、`event-emit`、`event-wait`、`mailbox-send`、`mailbox-check`、`mailbox-relay`、`manager-poll`。v1 的 outbox→relay→inbox、cursor/unread/mark-read、B-plane 唯一状态源和 control-envelope TASK 均不得用于新的 v2 工作流。

兼容期若 v1 Worker 仍发事件，Manager 可审计事件并读取其旧 outbox，但不得把 v1 relay daemon 当成 v2 前提；迁移完成后由 v2 `status.json` + direct inbox 接管。

Legacy v1 boundary: Manager→Worker 禁止使用 mailbox；this prohibition applies only to v1 control-envelope compatibility. In v2, formal TASK delivery is explicitly `mailbox-v2-send` to the direct inbox.
---

- 操作指南：`skill://tmux-agent-manager/OPERATIONS.md`
- Worker 协议：`skill://tmux-agent-worker/`
- 速查：`CHEATSHEET.md`
