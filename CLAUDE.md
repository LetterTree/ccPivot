# CLAUDE.md

ccPivot — Windows GUI 工具，用于管理 Codex 和 Claude 的多供应商配置档案，支持一键切换和 WSL 同步。

## 项目结构

```
config_switcher.py          # 主程序（~2400 行），单文件，含 GUI + 全部业务逻辑
ccPivot.ico / ccPivot.png  # 应用图标（PyInstaller --add-data 打包进 exe）
ccPivot.spec                # PyInstaller 生成，随时可删除重生成
install_dependencies.bat    # 开发环境依赖安装（仅 pip install toml + ttkbootstrap）
```

## 两条配置体系

### Codex 体系（"Codex 配置"标签页）

| 文件 | 路径 | 格式 |
|------|------|------|
| 主配置 | `~/.codex/config.toml` | TOML |
| 认证 | `~/.codex/auth.json` | JSON (`{"OPENAI_API_KEY": "sk-..."}`) |

`config.toml` 中的供应商定义格式：

```toml
[model_providers.pengui]
name = "pengui"
base_url = "https://api.example.com/v1"
model = "gpt-5.5"
wire_api = "responses"          # "responses"=OpenAI格式, "messages"=Anthropic格式
requires_openai_auth = true     # true→Bearer Auth, false→x-api-key Auth
```

激活供应商时，程序会在 `config.toml` 中写入一个固定运行时别名 `cc_session_shared`，将其设为 `model_provider`，并同步 base_url/model 到顶层。这样不同供应商可共享 Codex 会话列表。

### Claude 体系（"Claude 配置"标签页）

| 文件 | 路径 | 格式 |
|------|------|------|
| 配置 | `~/.claude/settings.json` | JSON |

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-...",
    "ANTHROPIC_BASE_URL": "https://api.example.com",
    "ANTHROPIC_MODEL": "claude-opus-4-7"
  }
}
```

程序通过 `_merge_claude_env_into_settings` 做深度合并，只修改 `env.ANTHROPIC_*` 三个字段，不会破坏 settings.json 中的其他配置。

### 供应商档案存储（`providers.json`）

路径：`%USERPROFILE%\.config_switcher\providers.json`，v3 格式：

```json
{
  "version": 3,
  "codex": {
    "last_active": "pengui",
    "last_selected": "pengui",
    "providers": {
      "pengui": {"name": "pengui", "base_url": "...", "model": "...", "api_key": "sk-..."}
    }
  },
  "claude": {
    "last_active": "ds",
    "profiles": {
      "ds": {"api_key": "sk-...", "base_url": "...", "model": "deepseek-v4-pro"}
    }
  }
}
```

- Codex 供应商的 `api_key` 只存在 providers.json，**不写回** config.toml
- Codex 供应商的 `wire_api` 和 `requires_openai_auth` 保存在 config.toml 中，新建时默认 `responses` + `true`（OpenAI 兼容格式），已有供应商保留原值
- Claude 档案字段名是 `api_key`/`base_url`/`model`（与 UI 一致），Codex 用 `api_key`/`base_url`/`model`/`name`

## WSL 同步

### WSL 检测

通过 `wsl -l -q` 获取默认发行版，`wsl sh -lc "echo $HOME"` 获取 WSL 侧主目录。

### 编码陷阱

WSL 子进程回显 **可能** 是 UTF-16LE（带 BOM `﻿`）。所有读取 WSL 输出的代码必须走 `_decode_wsl_text(raw: bytes) -> str`：

```python
def _decode_wsl_text(self, raw: bytes) -> str:
    raw = raw or b""
    if b"\x00" in raw:
        return raw.decode("utf-16le").replace("﻿", "")
    return raw.decode("utf-8")
```

### 同步逻辑

- 每次"应用"操作在 Windows 侧写入后同步到 WSL
- WSL 侧也执行 `_apply_codex_runtime_provider`，确保两边 `model_provider` 一致
- `.backup` 文件在**写入前**创建（而非覆盖后），由 `shutil.copy`

### Windows API 标志

`subprocess.run` 调用 wsl 时必须加 `creationflags=0x08000000`（`CREATE_NO_WINDOW`），避免弹出控制台黑窗。

## API 可用性探针

"探针"按钮位于每个标签页的连接配置区"保存"按钮旁边。

### 探测流程
1. 从 UI 输入框读取 base_url、model、api_key（同时从 providers.json 兜底 api_key）
2. 规范化 base_url：去除末尾 `/v1`，然后统一拼接 `/v1/messages` 或 `/v1/responses`
3. 在后台线程（`threading.Thread`）中发起 HTTP POST，15s 超时
4. 结果通过 `self.root.after(0, ...)` 回到主线程，显示在底部状态栏（不弹窗）

### 格式判定

- **Codex 标签页**：读取供应商在 config.toml 中的 `wire_api` 字段 — `"messages"` → Claude/Anthropic 格式, 其他 → OpenAI 格式
- **Claude 标签页**：始终使用 Claude/Anthropic 格式

### 两种请求格式

**Claude/Anthropic 格式** (`/v1/messages`)：
```
POST {base_url}/v1/messages
Headers: x-api-key, anthropic-version: 2023-06-01, anthropic-dangerous-direct-browser-access: true
Body: {model, max_tokens: 64, messages: [{role:"user", content:"just say hi, nothing else"}]}
```

**OpenAI 格式** (`/v1/responses`)：
```
POST {base_url}/v1/responses
Headers: Authorization: Bearer {api_key}
Body: {model, input: "just say hi, nothing else"}
```

两种格式都带 `User-Agent: ccPivot/1.0`，防止 Cloudflare 等反爬拦截。

## 线程安全

- 探针 HTTP 请求在 daemon 线程中执行，不阻塞 UI
- 回调通过 `self.root.after(0, callback)` 回到 tkinter 主线程
- 探针运行期间按钮显示"探测中..."并 disabled，完成后恢复
- 其他所有 tkinter 操作都在主线程

## UI 布局

每个标签页采用**左右分栏**：

```
┌─ 标签页 ─────────────────────────────────────────────┐
│ ┌─ 左侧 (210px) ─┐  ┌─ 右侧 (stretch) ─────────────┐ │
│ │ 供应商列表      │  │ 连接配置 (Base URL/Model/Key) │ │
│ │ (Canvas+滚动条) │  │ [帮助] [保存] [探针]          │ │
│ │                │  │ ──────────────────────────── │ │
│ │ • pengui  ✓    │  │ 同步到配置文件               │ │
│ │ • anyrouter    │  │ [两端同步] [仅Win] [仅WSL]   │ │
│ │ • doro         │  │ ──────────────────────────── │ │
│ │                │  │ 当前生效状态卡片             │ │
│ └────────────────┘  └──────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

- 供应商列表使用 `tk.Canvas` + `create_window` 嵌入 `tk.Frame` 实现可滚动列表
- 每个列表项是独立的 `tk.Frame`，通过 bind `<Button-1>` 响应点击
- 当前激活的供应商高亮显示（勾号 + 背景色）
- 滚动条通过 `<MouseWheel>` 绑定，鼠标进入/离开时动态绑定/解绑
- 底部状态栏显示最近操作结果

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name=ccPivot \
  --add-data="ccPivot.ico;." --add-data="ccPivot.png;." \
  --icon=ccPivot.ico config_switcher.py
```

产物：`dist/ccPivot.exe`（~18MB，单文件，终端用户无需安装 Python）
打包前确保旧 exe 未被占用（关闭正在运行的 ccPivot）

**重要**：打包后必须将 `dist/ccPivot.exe` 复制到工程根目录替换旧 exe，再一起提交。根目录的 `ccPivot.exe` 是用户直接下载使用的分发版本。

## 变更注意事项

- **不要引入新的第三方依赖** — 只依赖标准库 + `toml` + `ttkbootstrap`(可选)。`ttkbootstrap` 缺失时自动降级到 `clam` 主题
- **不要改 providers.json 的顶层结构** — `version`/`codex`/`claude` 的 key 结构向后兼容 v1/v2，改动需同步更新 `load_profiles()` 和 `_persist_profiles()`
- **Codex 供应商的 `api_key` 不写入 config.toml** — 只存在 providers.json 和 auth.json（auth.json 只在"应用"时写入 `OPENAI_API_KEY`）
- **`cc_session_shared` 是内部保留名称** — `_is_codex_runtime_provider_alias()` 会拦截对此名称的直接保存/创建
- **Claude 配置修改后立即生效** — 无需重启 Claude Code，但需要新开终端窗口
- **WSL 路径中的目录创建** — WSL 侧 `~/.codex` 和 `~/.claude` 目录通过 `wsl mkdir -p` 创建，每次同步前确保目录存在
- **`.backup` 文件是每次写入前的快照** — 不会自动清理，用户可手动删除

## 启动命令

```bash
python config_switcher.py       # 开发调试（带控制台输出）
pythonw config_switcher.py      # 无控制台窗口
```
