# 实现边界

- 基于已有 Python 派单器，保留选号、续跑、记录搬运、重试和八个命令。
- 安装器使用私有 uv 工具目录安装 `claude-swap==0.26.0`，不替换全局工具；仓库不包含其源码。
- 安装只写带标记的规则块、独立 skill、命令入口和 launchd 服务。已有文件先备份，卸载保留安装后的用户编辑。
- 账号登录交给官方 Claude CLI，凭据存储和运行档案初始化交给 claude-swap。项目代码不解析凭据。
- 上游 0.26.0 的 `_sync_sharing` 默认还会完整镜像 MCP、接管共享链接；薄适配替换这一回调为本项目带备份的同步，避免覆盖账号自己的 MCP，并统一卸载责任。版本不匹配立即拒绝，升级时需重新核对接口。
- 默认任务目录 `~/.claude-pro-pool/jobs`，`CLAUDE_PRO_POOL_JOBS` 可覆盖。
- 权限默认 `bypassPermissions`，对齐后台无人值守行为；用户可改为 `default` 或 `acceptEdits`。
- 首版安装支持 macOS；Linux 的服务注册和卸载路径未验证，暂不支持。Windows 不支持。
- 不自动退回主号、换模型或重做已完成任务。无可用账号明确返回状态。

外部接口依据：[claude-swap v0.26.0](https://github.com/realiti4/claude-swap/tree/v0.26.0)、[uv 官方安装方法](https://docs.astral.sh/uv/getting-started/installation/)。
