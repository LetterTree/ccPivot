#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置切换工具 - 管理 Codex 和 Claude 配置文件
支持 Windows 和 WSL 配置同步
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import toml
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import shutil


class ConfigSwitcher:
    def __init__(self, root):
        self.root = root
        self.root.title("配置切换工具")
        self.root.geometry("900x700")

        # 配置文件路径
        self.home = Path.home()
        self.codex_dir = self.home / ".codex"
        self.codex_config_path = self.codex_dir / "config.toml"
        self.codex_auth_path = self.codex_dir / "auth.json"

        # Claude 配置路径
        self.claude_dir = self.home / ".claude"
        self.claude_settings_path = self.claude_dir / "settings.json"

        # WSL 路径
        self.wsl_home = self.get_wsl_home()

        self.setup_ui()
        self.load_configs()

    def get_wsl_home(self) -> Optional[str]:
        """获取 WSL 用户主目录路径"""
        try:
            result = subprocess.run(
                ["wsl", "echo", "$HOME"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            print(f"无法获取 WSL 路径: {e}")
        return None

    def setup_ui(self):
        """设置用户界面"""
        # 创建 Notebook (标签页)
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Codex 配置标签页
        codex_frame = ttk.Frame(notebook)
        notebook.add(codex_frame, text='Codex 配置')
        self.setup_codex_tab(codex_frame)

        # Claude 配置标签页
        claude_frame = ttk.Frame(notebook)
        notebook.add(claude_frame, text='Claude 配置')
        self.setup_claude_tab(claude_frame)

        # 底部按钮区域
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill='x', padx=10, pady=5)

        ttk.Button(button_frame, text="刷新配置", command=self.load_configs).pack(side='left', padx=5)

        # 状态栏
        self.status_label = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(fill='x', side='bottom', padx=10, pady=5)

    def setup_codex_tab(self, parent):
        """设置 Codex 配置标签页"""
        # 说明文字
        info_label = ttk.Label(parent, text="粘贴 Codex 配置项，程序会自动识别并替换对应配置",
                               foreground="blue")
        info_label.pack(pady=5)

        # config.toml 区域
        toml_frame = ttk.LabelFrame(parent, text="config.toml", padding=10)
        toml_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.codex_toml_text = scrolledtext.ScrolledText(toml_frame, height=12, wrap=tk.WORD)
        self.codex_toml_text.pack(fill='both', expand=True)

        ttk.Button(toml_frame, text="应用 config.toml",
                  command=self.apply_codex_toml).pack(pady=5)

        # auth.json 区域
        auth_frame = ttk.LabelFrame(parent, text="auth.json", padding=10)
        auth_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.codex_auth_text = scrolledtext.ScrolledText(auth_frame, height=12, wrap=tk.WORD)
        self.codex_auth_text.pack(fill='both', expand=True)

        ttk.Button(auth_frame, text="应用 auth.json",
                  command=self.apply_codex_auth).pack(pady=5)

    def setup_claude_tab(self, parent):
        """设置 Claude 配置标签页"""
        # 说明文字
        info_label = ttk.Label(parent, text="修改 Claude 配置文件 (~/.claude/settings.json)", foreground="blue")
        info_label.pack(pady=5)

        # 配置表单
        form_frame = ttk.Frame(parent, padding=20)
        form_frame.pack(fill='both', expand=True)

        # API Key
        ttk.Label(form_frame, text="API Key:").grid(row=0, column=0, sticky='w', pady=10)
        self.claude_apikey = ttk.Entry(form_frame, width=60, show="*")
        self.claude_apikey.grid(row=0, column=1, pady=10, padx=10)

        show_key_var = tk.BooleanVar()
        def toggle_key():
            self.claude_apikey.config(show="" if show_key_var.get() else "*")
        ttk.Checkbutton(form_frame, text="显示", variable=show_key_var,
                       command=toggle_key).grid(row=0, column=2)

        # Base URL
        ttk.Label(form_frame, text="Base URL:").grid(row=1, column=0, sticky='w', pady=10)
        self.claude_baseurl = ttk.Entry(form_frame, width=60)
        self.claude_baseurl.grid(row=1, column=1, pady=10, padx=10)

        # Model
        ttk.Label(form_frame, text="Model:").grid(row=2, column=0, sticky='w', pady=10)
        self.claude_model = ttk.Entry(form_frame, width=60)
        self.claude_model.grid(row=2, column=1, pady=10, padx=10)

        # 应用按钮
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=20)
        ttk.Button(button_frame, text="应用 Claude 配置",
                  command=self.apply_claude_config).pack()

        # 说明文字
        note_frame = ttk.LabelFrame(parent, text="说明", padding=10)
        note_frame.pack(fill='x', padx=10, pady=10)

        note_text = """配置方式：通过 ~/.claude/settings.json 文件配置 Claude

Windows 侧：C:\\Users\\77396\\.claude\\settings.json
WSL 侧：$HOME/.claude/settings.json

配置项说明：
• API Key - 存储在 env.ANTHROPIC_AUTH_TOKEN
• Base URL - 存储在 env.ANTHROPIC_BASE_URL（可选）
• Model - 存储在顶层 model 字段（可选）

应用后会自动同步到 WSL"""

        ttk.Label(note_frame, text=note_text, justify=tk.LEFT).pack()

    def load_configs(self):
        """加载所有配置文件"""
        # 加载 Codex config.toml
        if self.codex_config_path.exists():
            with open(self.codex_config_path, 'r', encoding='utf-8') as f:
                self.codex_toml_text.delete('1.0', tk.END)
                self.codex_toml_text.insert('1.0', f.read())

        # 加载 Codex auth.json
        if self.codex_auth_path.exists():
            with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.codex_auth_text.delete('1.0', tk.END)
                # 格式化 JSON
                try:
                    data = json.loads(content)
                    formatted = json.dumps(data, indent=2, ensure_ascii=False)
                    self.codex_auth_text.insert('1.0', formatted)
                except:
                    self.codex_auth_text.insert('1.0', content)

        # 加载 Claude 配置
        if self.claude_settings_path.exists():
            with open(self.claude_settings_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)

                    # 从 env 对象中读取配置
                    env = data.get('env', {})

                    self.claude_apikey.delete(0, tk.END)
                    self.claude_apikey.insert(0, env.get('ANTHROPIC_AUTH_TOKEN', ''))

                    self.claude_baseurl.delete(0, tk.END)
                    self.claude_baseurl.insert(0, env.get('ANTHROPIC_BASE_URL', ''))

                    self.claude_model.delete(0, tk.END)
                    self.claude_model.insert(0, env.get('ANTHROPIC_MODEL', ''))
                except Exception as e:
                    self.set_status(f"加载 Claude 配置失败: {e}", "error")
        else:
            # 文件不存在，清空输入框
            self.claude_apikey.delete(0, tk.END)
            self.claude_baseurl.delete(0, tk.END)
            self.claude_model.delete(0, tk.END)

        self.set_status("配置已加载")

    def apply_codex_toml(self):
        """应用 Codex config.toml 配置"""
        try:
            content = self.codex_toml_text.get('1.0', tk.END).strip()

            # 解析用户输入的 TOML
            new_data = toml.loads(content)

            # 读取现有配置
            if self.codex_config_path.exists():
                with open(self.codex_config_path, 'r', encoding='utf-8') as f:
                    existing_data = toml.load(f)
            else:
                existing_data = {}

            # 深度合并配置
            self.deep_merge(existing_data, new_data)

            # 备份原文件
            if self.codex_config_path.exists():
                shutil.copy(self.codex_config_path,
                           str(self.codex_config_path) + '.backup')

            # 写入新配置
            with open(self.codex_config_path, 'w', encoding='utf-8') as f:
                toml.dump(existing_data, f)

            # 自动同步到 WSL
            self.sync_file_to_wsl(self.codex_config_path, "config.toml")

            self.set_status("config.toml 已更新并同步到 WSL")
            messagebox.showinfo("成功", "config.toml 配置已应用并同步到 WSL")

        except Exception as e:
            self.set_status(f"应用失败: {e}", "error")
            messagebox.showerror("错误", f"应用配置失败:\n{e}")

    def apply_codex_auth(self):
        """应用 Codex auth.json 配置"""
        try:
            content = self.codex_auth_text.get('1.0', tk.END).strip()

            # 解析用户输入的 JSON
            new_data = json.loads(content)

            # 读取现有配置
            if self.codex_auth_path.exists():
                with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            else:
                existing_data = {}

            # 深度合并配置
            self.deep_merge(existing_data, new_data)

            # 备份原文件
            if self.codex_auth_path.exists():
                shutil.copy(self.codex_auth_path,
                           str(self.codex_auth_path) + '.backup')

            # 写入新配置
            with open(self.codex_auth_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)

            # 更新显示
            formatted = json.dumps(existing_data, indent=2, ensure_ascii=False)
            self.codex_auth_text.delete('1.0', tk.END)
            self.codex_auth_text.insert('1.0', formatted)

            # 自动同步到 WSL
            self.sync_file_to_wsl(self.codex_auth_path, "auth.json")

            self.set_status("auth.json 已更新并同步到 WSL")
            messagebox.showinfo("成功", "auth.json 配置已应用并同步到 WSL")

        except Exception as e:
            self.set_status(f"应用失败: {e}", "error")
            messagebox.showerror("错误", f"应用配置失败:\n{e}")

    def apply_claude_config(self):
        """应用 Claude 配置 - 写入 settings.json"""
        try:
            api_key = self.claude_apikey.get()
            base_url = self.claude_baseurl.get()
            model = self.claude_model.get()

            # 读取现有配置（如果存在）
            if self.claude_settings_path.exists():
                with open(self.claude_settings_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {}

            # 确保 env 对象存在
            if 'env' not in data:
                data['env'] = {}

            # 更新配置 - 全部放在 env 对象中
            if api_key:
                data['env']['ANTHROPIC_AUTH_TOKEN'] = api_key
            elif 'ANTHROPIC_AUTH_TOKEN' in data['env'] and not api_key:
                del data['env']['ANTHROPIC_AUTH_TOKEN']

            if base_url:
                data['env']['ANTHROPIC_BASE_URL'] = base_url
            elif 'ANTHROPIC_BASE_URL' in data['env'] and not base_url:
                del data['env']['ANTHROPIC_BASE_URL']

            if model:
                data['env']['ANTHROPIC_MODEL'] = model
            elif 'ANTHROPIC_MODEL' in data['env'] and not model:
                del data['env']['ANTHROPIC_MODEL']

            # 同时清理旧的顶层 model 字段（如果存在）
            data.pop('model', None)

            # 确保目录存在
            self.claude_dir.mkdir(parents=True, exist_ok=True)

            # 备份原文件
            if self.claude_settings_path.exists():
                shutil.copy(self.claude_settings_path,
                           str(self.claude_settings_path) + '.backup')

            # 写入 Windows 侧配置
            with open(self.claude_settings_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # 同步到 WSL
            self.sync_claude_to_wsl()

            self.set_status("Claude 配置已更新并同步到 WSL")
            messagebox.showinfo("成功", "Claude 配置已应用并同步到 WSL")

        except Exception as e:
            self.set_status(f"应用失败: {e}", "error")
            messagebox.showerror("错误", f"应用配置失败:\n{e}")

    def sync_claude_to_wsl(self):
        """同步 Claude 配置到 WSL"""
        if not self.wsl_home:
            return

        try:
            if self.claude_settings_path.exists():
                # 创建 WSL 侧的 .claude 目录
                wsl_claude_dir = f"{self.wsl_home}/.claude"
                subprocess.run(['wsl', 'mkdir', '-p', wsl_claude_dir], capture_output=True)

                # 复制文件
                win_path_str = str(self.claude_settings_path).replace('\\', '/')
                wsl_win_path = f"/mnt/{win_path_str[0].lower()}/{win_path_str[3:]}"
                wsl_target = f"{wsl_claude_dir}/settings.json"

                cmd = f'wsl cp "{wsl_win_path}" "{wsl_target}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if result.returncode != 0:
                    raise Exception(f"同步失败: {result.stderr}")
        except Exception as e:
            print(f"同步 Claude 配置到 WSL 失败: {e}")

    def deep_merge(self, base: Dict, update: Dict):
        """深度合并字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self.deep_merge(base[key], value)
            else:
                base[key] = value

    def sync_file_to_wsl(self, win_path: Path, filename: str):
        """同步单个文件到 WSL"""
        if not self.wsl_home:
            return

        try:
            if win_path.exists():
                win_path_str = str(win_path).replace('\\', '/')
                # 转换为 WSL 路径格式
                wsl_win_path = f"/mnt/{win_path_str[0].lower()}/{win_path_str[3:]}"

                # WSL 侧也创建 .codex 目录
                wsl_codex_dir = f"{self.wsl_home}/.codex"
                subprocess.run(['wsl', 'mkdir', '-p', wsl_codex_dir], capture_output=True)

                wsl_target = f"{wsl_codex_dir}/{filename}"

                cmd = f'wsl cp "{wsl_win_path}" "{wsl_target}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if result.returncode != 0:
                    raise Exception(f"同步失败: {result.stderr}")
        except Exception as e:
            print(f"同步 {filename} 到 WSL 失败: {e}")

    def sync_to_wsl(self):
        """手动同步所有配置到 WSL（已移除，功能已集成到应用按钮中）"""
        pass

    def set_status(self, message: str, level: str = "info"):
        """设置状态栏消息"""
        self.status_label.config(text=message)
        if level == "error":
            self.status_label.config(foreground="red")
        else:
            self.status_label.config(foreground="black")


def main():
    root = tk.Tk()
    app = ConfigSwitcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
