---
name: claude-pro-pool
description: 将耗时的 Claude Code 子任务派到其他个人 Pro/Max 订阅账号，后台执行、按额度选号、在原记录上追问与续跑。用于已安装 claude-pro-pool 的主对话。
---

主对话负责统筹和验收。尊重当前用户的范围、项目规则、权限与模型选择。
若存在 `DISPATCH_CLAUDE_DEPTH`，直接执行收到的任务，不再派子任务。

1. 为重活写独立任务单，列明目的、约束、产物绝对路径和验收条件。要求每份产物完成即落盘，最终回报不超过一页。
2. 在 Bash 工具中以后台模式运行：`dispatch-claude run --prompt-file /absolute/task.md --name short-name`。保留命令自身的等待，Bash 完成通知会送回回执。不要循环查询状态。
3. 默认继承主对话模型和思考档位；有明确选择时用 `--model`、`--effort`，或 `--agent` 指定现有 agent 定义。
4. 收到通知后核对关键产物。追问用 `ask JOB --prompt "…"`，出错或超时后用 `continue JOB`，均用 Bash 后台模式。沿原任务继续，避免重做。

选号会排除主号、默认号、忙于交互对话的号、停用号及额度不明的号；撞限额时搬记录自动换号。`--account N` 是显式强制选中，包含越过这些保护，仅在用户明确指定时使用。

诊断：`dispatch-claude accounts`、`status JOB`、`logs JOB -n 30`。取消：`cancel JOB`，再 `wait JOB` 确认结束。无可用号时告知用户；内置子 Agent 会消耗主号额度。
