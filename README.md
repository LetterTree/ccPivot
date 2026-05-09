# cc-config-sync

`cc-config-sync` 是一个 Windows GUI 工具，用于统一管理 Codex / Claude 的多套供应商配置，并可自动同步到 WSL。

## 快速开始
1. 安装依赖（首次）
   - 运行 `install_dependencies.bat`
   - 或手动执行 `pip install toml`
2. 启动程序
   - 双击 `启动.bat`
   - 或执行 `python config_switcher.py`

## 主要能力
- Codex 与 Claude 分页管理，布局和操作方式一致
- 每页支持：`新增` / `保存` / `删除` / `应用该供应商`
- 保存前自动备份原配置（`.backup`）
- 自动同步配置到 WSL（如可用）

## 配置文件
- Windows
  - `%USERPROFILE%\\.codex\\config.toml`
  - `%USERPROFILE%\\.codex\\auth.json`
  - `%USERPROFILE%\\.claude\\settings.json`
  - `%USERPROFILE%\\.config_switcher\\providers.json`
- WSL（自动检测）
  - `$HOME/.codex/config.toml`
  - `$HOME/.codex/auth.json`
  - `$HOME/.claude/settings.json`

## 关键约定
- Codex API Key 字段：`OPENAI_API_KEY`（写入 `~/.codex/auth.json`）
- 新建 Codex 供应商默认包含：
  - `wire_api = "responses"`
  - `requires_openai_auth = true`
