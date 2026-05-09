# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 Windows GUI 工具，用于管理和切换 Codex 和 Claude 的配置文件。主要功能包括：
- 管理 Codex 配置（config.toml 和 auth.json）
- 管理 Claude 配置（通过 settings.json）
- 支持配置项的智能合并和替换
- 自动同步配置到 WSL 环境

## 核心架构

### 主要文件
- `config_switcher.py` - 主程序，包含完整的 GUI 和配置管理逻辑
- `config_switcher.py.bak_before_profiles_refactor.py` - 重构前的备份版本

### 配置文件结构
程序管理两套独立的配置系统：

**Codex 配置**（在"Codex 配置"标签页管理）：
- `~/.codex/config.toml` - Codex 主配置文件
- `~/.codex/auth.json` - Codex 认证信息

**Claude 配置**（在"Claude 配置"标签页管理）：
- `~/.claude/settings.json` - Claude 配置文件，包含：
  - `env.ANTHROPIC_AUTH_TOKEN` - API Key
  - `env.ANTHROPIC_BASE_URL` - Base URL（可选）
  - `env.ANTHROPIC_MODEL` - Model（可选）

**供应商配置存储**：
- `%USERPROFILE%\.config_switcher\providers.json` - 保存所有供应商配置档案

### WSL 同步机制
程序会自动检测 WSL 环境并同步配置到：
- WSL: `$HOME/.codex/config.toml`
- WSL: `$HOME/.codex/auth.json`
- WSL: `$HOME/.claude/settings.json`

每次应用配置时会自动创建 `.backup` 备份文件。

## 开发命令

### 安装依赖
```bash
pip install toml
```
或运行：
```bash
install_dependencies.bat
```

### 启动程序
```bash
python config_switcher.py
```
或双击 `启动.bat`（使用 pythonw 无窗口启动）

### 运行环境
- Python 3.6+
- tkinter（Python 自带）
- toml 库

## 关键设计决策

1. **配置分离**：Codex 和 Claude 配置完全分离，各自独立管理供应商档案
2. **深度合并策略**：应用配置时采用深度合并，不会覆盖未修改的字段
3. **自动备份**：每次修改前自动备份为 `.backup` 文件
4. **跨平台同步**：Windows 配置自动同步到 WSL，保持环境一致性
5. **GUI 设计**：使用 tkinter 实现双标签页界面，Codex 和 Claude 配置分开管理

## 配置应用逻辑

### Codex 配置
- 基础字段（Base URL/Model/API Key）可直接应用
- 完整 TOML/JSON 需在高级编辑器中单独应用
- 支持合并模式，保留现有配置

### Claude 配置
- 直接修改三个字段即可
- 应用后立即生效，无需重启
- 同时更新 Windows 和 WSL 配置

## WSL 集成
程序通过 `wsl sh -lc` 命令与 WSL 交互，自动检测 WSL 可用性并同步配置文件。
