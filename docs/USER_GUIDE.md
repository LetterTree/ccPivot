# Codex 供应商管理 - 使用指南

## 🎯 功能概述

通过图形界面管理 Codex 的多个 API 供应商配置，支持快速切换。所有配置保存在 `~/.codex/config.toml` 中，使用 Codex 原生的 `[model_providers.xxx]` 机制。

## 🚀 启动程序

```bash
python config_switcher.py
```

## 📋 主要功能

### 1. 创建新供应商

1. 点击 **"新增"** 按钮
2. 输入供应商名称（建议使用英文，如：openai, anthropic, deepseek）
3. 填写配置信息：
   - **Base URL**: API 端点地址
   - **Model**: 模型名称（可选）
   - **API Key**: API 密钥
   - **Wire API**: 选择 API 协议类型
     - `responses` - 通用响应格式
     - `openai` - OpenAI 兼容格式
     - `anthropic` - Anthropic 格式
   - **Requires OpenAI Auth**: 是否需要 OpenAI 认证
4. 点击 **"保存到 config.toml"**

### 2. 切换供应商

1. 从下拉列表选择要使用的供应商
2. 点击 **"切换到此供应商"**
3. 确认后，系统会：
   - 更新 `config.toml` 中的 `model_provider` 字段
   - 更新顶层的 `base_url` 和 `model` 字段
   - 更新 `auth.json` 中的 API key
   - 自动同步到 WSL（如果可用）

### 3. 编辑供应商

1. 从下拉列表选择供应商
2. 修改配置信息
3. 点击 **"保存到 config.toml"**

### 4. 删除供应商

1. 从下拉列表选择要删除的供应商
2. 点击 **"删除"**
3. 确认后，供应商定义将从 `config.toml` 中移除

## 📁 配置文件结构

### ~/.codex/config.toml
```toml
# 当前激活的供应商
model_provider = "openai"

# 顶层配置（从当前供应商复制）
base_url = "https://api.openai.com/v1"
model = "gpt-4"

# 供应商定义
[model_providers.openai]
name = "openai"
base_url = "https://api.openai.com/v1"
wire_api = "openai"
requires_openai_auth = true

[model_providers.anthropic]
name = "anthropic"
base_url = "https://api.anthropic.com"
wire_api = "anthropic"
requires_openai_auth = false

[model_providers.deepseek]
name = "deepseek"
base_url = "https://api.deepseek.com/v1"
wire_api = "openai"
requires_openai_auth = true
```

### ~/.codex/auth.json
```json
{
  "api_key": "sk-..."
}
```

## 💡 使用场景

### 场景 1：在多个 API 提供商之间切换
```
OpenAI → Anthropic → DeepSeek → 自定义 API
```
只需在下拉列表中选择，点击"切换"即可。

### 场景 2：测试不同的 API 端点
创建多个配置（如 openai-prod, openai-test），快速切换测试。

### 场景 3：使用代理或中转服务
创建自定义供应商，配置代理地址。

## ⚙️ Wire API 说明

- **responses**: 通用格式，适用于大多数兼容 API
- **openai**: OpenAI 官方格式，适用于 OpenAI 和兼容服务
- **anthropic**: Anthropic 官方格式，适用于 Claude API

## 🔒 安全提示

- API Key 存储在 `~/.codex/auth.json` 中
- 建议设置文件权限：`chmod 600 ~/.codex/auth.json`
- 不要将配置文件提交到版本控制系统

## 🔄 WSL 同步

程序会自动将配置同步到 WSL 环境（如果可用）：
- Windows: `C:\Users\<用户>\.codex\`
- WSL: `~/.codex/`

## 🧪 测试

运行测试脚本验证功能：
```bash
python test_provider_management.py
```

## ❓ 常见问题

**Q: 切换供应商后需要重启 Codex 吗？**
A: 是的，需要重启 Codex 才能使新配置生效。

**Q: 可以同时使用多个供应商吗？**
A: 不可以，同一时间只能激活一个供应商。但可以快速切换。

**Q: 删除供应商会影响其他配置吗？**
A: 不会，只删除该供应商的定义，不影响其他配置。

**Q: Wire API 应该选择哪个？**
A: 如果不确定，选择 `responses`。如果使用 OpenAI 兼容 API，选择 `openai`。

## 📝 更新日志

### v3.0 (当前版本)
- ✅ 使用 Codex 原生 `[model_providers.xxx]` 机制
- ✅ 支持 Wire API 配置
- ✅ 支持 Requires OpenAI Auth 配置
- ✅ 简化 UI，移除高级编辑器
- ✅ 改进供应商切换流程

### v2.0
- 支持 Codex 和 Claude 独立配置
- 完整配置文件替换方式

## 🎉 完成

所有功能已集成到 GUI 中，无需使用命令行工具！
