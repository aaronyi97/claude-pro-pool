# 测试与验收

## 可复跑命令

所有测试数据放在 `CPP_TEST_ROOT` 下的临时假 HOME；请指定专用目录。测试进程只使用合成身份，系统服务、通知和 Claude CLI 均替换成测试实现，不调用真实账号或系统服务。

```bash
export CPP_TEST_ROOT="/path/to/isolated/test-homes"
bash tests/run.sh
```

额外测试官方 uv 引导、Python 下载与真实固定版依赖安装（需要网络）：

```bash
CPP_REAL_INSTALL=1 bash tests/run.sh
# 或只运行这一项：
CPP_REAL_INSTALL=1 python3 -B -m unittest discover -s tests -p test_install.py -k official -v
```

网络测试起始 PATH 中没有 uv 和 claude-swap，使用 README 的 `bash ./install.sh`；官方依赖真正下载，但登录、额度、模型调用和 launchctl 始终使用替身。安装后用包元数据验证 `0.26.0`，并执行薄适配的 `--version`；不触发上游账号或凭据操作。

管道安装使用本地仓库打包的归档作为下载替身，检验 `bash` 从标准输入执行时的下载、解包和安装流程。仓库公开后，已在全新 HOME 中用 README 的 curl 一行命令实际安装、体检并卸载成功（2026-10-19）。

## 覆盖范围

| 范围 | 验证内容 |
| --- | --- |
| 选号 | 主号、默认号、交互忙碌、停用、未知额度、80/95 门槛排除；负载/周重置/5h 排序 |
| 续跑 | 95/99 留号门槛；显式选号；限额、登录失效、条款未同意和 stderr 登录错误换号 |
| 会话 | 相同 session ID；JSONL、带签名内容及侧目录按字节复制；ask/continue 搬记录续跑 |
| 模型/权限 | 主模型含空格 JSON、最新切模提示、思考档位继承；配置权限；剥离主号与 API 覆盖环境 |
| 后台 | detach/wait、取消、超时、继续；持久化终态通知；日志与状态查询 |
| 新安装 | 干净 HOME；从已提交的本地 clone 安装；空号池 doctor；替身加号后正常 |
| 重装/卸载 | 规则不重复；已有 CLAUDE.md、shell 配置、settings、命令原样恢复；自定义目录含空格 |
| 用户修改 | 原文件无结尾换行、CRLF、符号链接、自建目录、安装后新增文字与替换链接均保留 |
| 同步 | settings、memory、MCP；记忆冲突不覆盖；账号 MCP 不覆盖；卸载保留后续编辑和新记忆 |
| doctor | 服务未加载、额度未知、登录身份不符均报问题，给出下一步 |
| 上游适配 | 0.26.0 共享回调替换；不同版本拒绝运行；不包含上游源码 |

## 本轮验收记录

验收日期：2026-10-19，macOS。先写派单和可撤销修改测试，确认缺少实现时失败，再实现并通过。审查时发现的用户替换链接被覆盖问题也先用失败用例复现，再修复。

最终结果：

| 命令 | 结果 |
| --- | --- |
| `bash tests/run.sh` | 34 项：33 通过、1 项网络安装按默认跳过；129.986 秒 |
| `CPP_REAL_INSTALL=1 python3 -B -m unittest discover -s tests -p test_install.py -k official -v` | 上述网络安装项单独通过；63.716 秒；官方 uv、Python、真实 0.26.0、替身加号、重装、卸载及安装收据无残留 |
| `python3 -B -m unittest discover -s tests -p test_sync.py -v` | 4 项通过，含缓存额度正常但登录身份错误的情况 |
| skill frontmatter 校验 | `Skill is valid!` |
| Shell 语法、`git diff --check`、隐私扫描 | 通过；隐私零命中 |

共 34 个不同用例通过。完整运行及补测日志保存在仓库外的验收目录，避免把本机路径和待排除的私有标识写入公开仓库。真实依赖下载单独执行，便于日常离线复跑其余测试。

```bash
bash -n install.sh uninstall.sh tests/run.sh
git diff --check
```

隐私检查使用 `rg --hidden`，排除 `.git`，扫描指定私有标识、私有绝对路径和邮箱正则。完整参数只记录在仓库外；不把禁止出现的标识写回本页。源材料中的个人规则没有复制，只有任务指定的主对话派单做法被泛化。

未在本轮执行：真实浏览器登录、真实订阅派单、真实系统 launchd 加载、真实桌面通知、Linux 和 Windows。前四项受本轮只读与隔离约束限制，需在另行授权的真实环境验收；后两项不声明支持。规则和 skill 不能保证模型每次自动选择派单，Bash 后台完成事件由宿主 Claude Code 提供。
