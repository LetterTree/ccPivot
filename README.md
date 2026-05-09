配置切换工具使用说明
===================

功能介绍
--------
这是一个 Windows GUI 工具，用于方便地管理和切换 Codex 和 Claude 的配置文件。

主要功能：
1. 管理 Codex 配置（config.toml 和 auth.json）
2. 管理 Claude 配置（通过环境变量）
3. 支持配置项的智能合并和替换
4. 自动同步配置到 WSL 环境

使用方法
--------

启动程序：
  双击 启动.bat 或直接运行：
  python config_switcher.py

API 供应商（多套配置，Codex/Claude 分离）
----------------
新版 GUI 将供应商配置拆分为两套：

- Codex 供应商：在“Codex 配置”标签页内管理，只影响 `~/.codex/config.toml` 与 `~/.codex/auth.json`
- Claude 供应商：在“Claude 配置”标签页内管理，只影响 `~/.claude/settings.json`

每个标签页都提供：选择 / 新增 / 保存 / 删除 / 应用该供应商。

供应商配置保存位置：
- Windows：`%USERPROFILE%\.config_switcher\providers.json`

Codex 配置标签页：
  - 默认只展示基础字段：Base URL / Model / API Key
  - 点击“应用基础配置”会写入 Codex 配置文件（并自动备份为 `.backup`，同时同步到 WSL 如可用）
  - 点击“编辑完整 TOML/JSON…”可展开完整编辑器：
    * `config.toml（完整）`：可直接编辑并点击“应用完整 config.toml（合并）”写入
    * `auth.json（完整）`：可直接编辑并点击“应用完整 auth.json（合并）”写入
  - “应用该供应商”（Codex）默认只应用基础字段；完整文件需在高级编辑器中点击对应按钮

Claude 配置标签页：
  - 直接在表单中修改三个配置项：
    * API Key - 存储在 env.ANTHROPIC_AUTH_TOKEN
    * Base URL - 存储在 env.ANTHROPIC_BASE_URL（可选）
    * Model - 存储在 env.ANTHROPIC_MODEL（可选）
  - API Key 默认隐藏显示，可勾选"显示"查看
  - 点击"应用 Claude 配置"会同时更新 Windows 和 WSL 的配置文件
  - 配置立即生效，无需重启

底部按钮：
  - 刷新配置：重新加载所有配置文件

配置文件路径
------------
Windows 侧：
  - Codex config: C:\Users\77396\.codex\config.toml
  - Codex auth: C:\Users\77396\.codex\auth.json
  - Claude settings: C:\Users\77396\.claude\settings.json

WSL 侧（自动检测）：
  - Codex config: $HOME/.codex/config.toml
  - Codex auth: $HOME/.codex/auth.json
  - Claude settings: $HOME/.claude/settings.json

注意事项
--------
1. 每次修改 Codex 和 Claude 配置前会自动备份原文件
2. 配置合并采用深度合并策略，不会丢失现有配置
3. Codex 和 Claude 配置应用后会自动同步到 WSL
4. Claude 配置立即生效，无需重启终端
5. 确保 WSL 已安装并可以正常访问

依赖要求
--------
- Python 3.6+
- toml 库（pip install toml）
- tkinter（Python 自带）

故障排除
--------
如果遇到问题：
1. 检查 Python 是否正确安装
2. 运行 pip install toml 安装依赖
3. 确认配置文件路径是否正确
4. 查看备份文件恢复配置
5. 检查 WSL 是否正常运行（wsl echo test）



