# 命令与配置

## 派单

```text
dispatch-claude accounts
dispatch-claude run (--prompt TEXT | --prompt-file FILE)
  [--name NAME] [--model MODEL] [--effort low|medium|high|xhigh|max]
  [--agent AGENT] [--account N] [--cwd DIR] [--timeout SECONDS] [--no-wait]
dispatch-claude ask JOB (--prompt TEXT | --prompt-file FILE) [--account N] [--no-wait]
dispatch-claude continue JOB [--account N] [--no-wait]
dispatch-claude wait JOB
dispatch-claude status [JOB]
dispatch-claude logs JOB [-n 30]
dispatch-claude cancel JOB
```

`--prompt-file -` 读取标准输入。默认超时为每轮 3 小时。`ask`/`continue` 沿用任务的模型、effort、权限、工作目录和超时；模型显式调整需新任务。它们在任务仍运行时拒绝重复启动。

| 退出码 | 含义 |
| --- | --- |
| 0 | 完成/命令成功；`--no-wait` 只代表已提交 |
| 2 | 参数、文件或配置错误 |
| 3 | 无可用账号或账号数据读取失败 |
| 4 | 执行失败 |
| 5 | 超时 |
| 6 | 取消 |

管理命令 `doctor`：0 表示检查正常，1 表示有待处理项，2 表示无法完成命令。已正常登录的主号被排除不计为错误，但至少需要一个可自动派单的其他号。

## 环境变量

| 变量 | 默认 / 用途 |
| --- | --- |
| `CLAUDE_PRO_POOL_JOBS` | `~/.claude-pro-pool/jobs`；任务目录，支持指向其他卷，所有命令须使用同一值 |
| `CLAUDE_PRO_POOL_HOME` | `~/.claude-pro-pool`；安装和状态目录，安装前设置；生成的命令入口固定到此目录 |
| `CLAUDE_PRO_POOL_PERMISSION_MODE` | 优先于 `config.json`；支持 `bypassPermissions/default/acceptEdits/plan/dontAsk` |
| `CLAUDE_PRO_POOL_SWAP` | 上游命令覆盖入口；默认工具私有版本，直接运行仓库派单器时兼容 PATH 中已有的 0.26.0 |
| `CLAUDE_CONFIG_DIR` | 主对话当前档案，用于识别调用账号与读取模型；选号查询则始终针对默认主号 |
| `CLAUDE_CODE_SESSION_ID` | 主对话 session ID，继承模型需要它 |
| `CLAUDE_EFFORT` | 继承思考档位（显式参数优先） |

例如，在启动 `claude` 前：

```bash
export CLAUDE_PRO_POOL_JOBS="$HOME/work/pooled-jobs"
claude
```

Claude Code 的环境变量可用性取决于版本。读取不到父模型时会告警，可用 `--model` 明确指定；不通过猜测模型名称伪装继承成功。

`~/.claude-pro-pool/config.json` 示例：

```json
{
  "permission_mode": "bypassPermissions",
  "desktop_notifications": true
}
```

## 文件布局与数据

```text
~/.claude-pro-pool/
  runtime/             已安装的项目代码与 skill
  deps/                私有 uv、Python、claude-swap
  config.json          权限与桌面通知
  managed.json         可撤销修改清单
  backups/             修改前备份
  enrollment/          官方 CLI 登录用的独立临时档案（卸载保留）
  sync.log             定时同步日志
  jobs/JOB/
    meta.json          状态、模型来源、session ID、轮次
    prompt-*.md        原任务与追问
    stream-*.jsonl     执行流
    stderr-*.log       错误输出
    result.md          最后成功结果
    completion.json    终态通知记录
```

任务目录可能含项目敏感数据，不应提交到 Git。账号存储沿用 macOS 的 `~/.claude-swap-backup/sessions/N-<slug>` 结构，不读取或改写其凭据文件；账号认证操作委托官方 CLI 和上游。`remove` 的删除行为由上游交互确认。
