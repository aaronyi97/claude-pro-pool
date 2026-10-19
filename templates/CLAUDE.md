## 主对话派单（claude-pro-pool）

- 主对话负责拆任务、定标准、派单、验收、判断和沟通。用户当前的任务、权限与项目规则优先。
- 读长文件/日志、翻代码找入口、批量盘点、跑测量与测试、写脚本和整理资料等重活，默认用 `dispatch-claude` 派到其他有额度的订阅账号。三步内的小事直接做。
- 先写任务单，说明目的和下游用法、硬约束、产物绝对路径、验收办法。长任务每完成一份产物就落盘。最后回报限一页：结论、关键数字、产物路径、未完成与不确定项。
- 用 Bash 工具后台执行 `dispatch-claude run --prompt-file /absolute/path/task.md --name short-name`，开启工具的后台模式；保留默认等待，不加 `--no-wait`。任务完成后 Bash 工具会通知，期间继续统筹，不轮询。
- 不传 `--model`/`--effort` 时继承当前主对话；指定 `--agent` 时由 agent 定义决定模型。模型读取失败会明确提示，可显式传参。
- 追问用 `dispatch-claude ask JOB --prompt "…"`；中断后用 `dispatch-claude continue JOB`。先检查原任务状态和已落盘成果，沿原记录续跑。
- 用 `accounts` 看余量，`status`/`logs` 查具体故障，`cancel` 停止任务。只有返回“没有可用账号”后才考虑内置子 Agent，并告知用户会使用主号额度。
- 按产物和证据验收，不把执行者自述当验收。项目要求主对话亲自判断的内容仍由主对话判断。
- 如果设置了 `DISPATCH_CLAUDE_DEPTH`，你是执行子任务；直接完成任务单，不再派单。
