# ccPivot 使用说明

## 工具简介
`ccPivot` 是一个 Windows GUI 工具，用于统一管理 Codex 和 Claude 的多套供应商配置，并可自动同步到 WSL。

## 快速开始
1. 安装依赖（首次）
   - 运行 `install_dependencies.bat`
   - 或手动执行 `pip install toml`
2. 启动程序
   - 双击 `ccPivot.exe`
   - 或执行 `python config_switcher.py`

## 界面结构（Codex / Claude 两页统一）
每个页面都按同样结构组织：
- 供应商管理：`供应商选择 + 新增 + 保存 + 删除 + 应用该供应商`
- 蓝色说明行：提示实际写入的配置文件
- 供应商配置表单：`Base URL`、`Model`、`API Key`
- 说明区：字段映射和行为说明

底部固定：
- `刷新配置` 按钮
- 状态栏消息

## Codex 页面行为
- 保存供应商时写入 `~/.codex/config.toml` 的 `[model_providers.<name>]`
- 新建供应商默认包含：
  - `wire_api = "responses"`
  - `requires_openai_auth = true`
- API Key 写入 `~/.codex/auth.json` 字段：`OPENAI_API_KEY`
- 应用该供应商会切换 `model_provider` 到当前供应商
- 写入前会自动生成 `.backup` 备份，并尝试同步到 WSL

## Claude 页面行为
- 配置写入 `~/.claude/settings.json` 的 `env` 字段：
  - `ANTHROPIC_AUTH_TOKEN`
  - `ANTHROPIC_BASE_URL`
  - `ANTHROPIC_MODEL`
- 写入前自动备份，并尝试同步到 WSL

## 配置文件位置
Windows：
- `%USERPROFILE%\\.codex\\config.toml`
- `%USERPROFILE%\\.codex\\auth.json`
- `%USERPROFILE%\\.claude\\settings.json`
- `%USERPROFILE%\\.config_switcher\\providers.json`

WSL（自动检测）：
- `$HOME/.codex/config.toml`
- `$HOME/.codex/auth.json`
- `$HOME/.claude/settings.json`

## 常见问题
- 启动失败：确认 Python 可用，并已安装 `toml`
- WSL 不同步：先手动测试 `wsl echo test`
- 配置异常：优先使用同目录 `.backup` 文件回滚
