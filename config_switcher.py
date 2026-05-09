#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置切换工具 - 管理 Codex 和 Claude 配置文件
支持 Windows 和 WSL 配置同步
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from tkinter import simpledialog
import json
import toml
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import shutil


class ConfigSwitcher:
    def __init__(self, root):
        self.root = root
        self.root.title("配置切换工具")
        self.root.geometry("900x700")
        # 供应商/配置档案（profiles）存储（Codex 与 Claude 分开）
        self.app_dir = Path.home() / ".config_switcher"
        self.profiles_path = self.app_dir / "providers.json"
        self.codex_profiles: Dict[str, Dict[str, Any]] = {}
        self.codex_active_profile: Optional[str] = None
        self.claude_profiles: Dict[str, Dict[str, Any]] = {}
        self.claude_active_profile: Optional[str] = None

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
        self.load_profiles()

    def get_wsl_home(self) -> Optional[str]:
        """获取 WSL 用户主目录路径"""
        try:
            result = subprocess.run(
                ["wsl", "sh", "-lc", "echo $HOME"],
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
    def _normalize_codex_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'base_url': profile.get('base_url', ''),
            'model': profile.get('model', ''),
            'api_key': profile.get('api_key', ''),
            'config_toml': profile.get('config_toml', ''),
            'auth_json': profile.get('auth_json', ''),
        }

    def _normalize_claude_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'api_key': profile.get('api_key', ''),
            'base_url': profile.get('base_url', ''),
            'model': profile.get('model', ''),
        }

    def load_profiles(self):
        """从磁盘加载供应商/配置档案列表（v2：Codex/Claude 分离；兼容 v1 自动迁移）"""
        self.codex_profiles = {}
        self.claude_profiles = {}
        self.codex_active_profile = None
        self.claude_active_profile = None

        if self.profiles_path.exists():
            try:
                with open(self.profiles_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                version = int(data.get('version', 1))
                if version >= 2:
                    codex = data.get('codex', {}) or {}
                    claude = data.get('claude', {}) or {}

                    for name, p in (codex.get('profiles', {}) or {}).items():
                        self.codex_profiles[name] = self._normalize_codex_profile(p or {})
                    for name, p in (claude.get('profiles', {}) or {}).items():
                        self.claude_profiles[name] = self._normalize_claude_profile(p or {})

                    if codex.get('last_active') in self.codex_profiles:
                        self.codex_active_profile = codex.get('last_active')
                    if claude.get('last_active') in self.claude_profiles:
                        self.claude_active_profile = claude.get('last_active')
                else:
                    # v1 -> v2
                    raw_profiles = data.get('profiles', {}) or {}
                    last_active = data.get('last_active')
                    for name, p in raw_profiles.items():
                        p = p or {}

                        codex_toml = p.get('codex_config_toml', '')
                        codex_auth = p.get('codex_auth_json', '')
                        base_url, model = self._extract_codex_basic_from_toml_text(codex_toml)
                        api_key = self._extract_api_key_from_auth_json_text(codex_auth)

                        self.codex_profiles[name] = self._normalize_codex_profile({
                            'base_url': base_url,
                            'model': model,
                            'api_key': api_key,
                            'config_toml': codex_toml,
                            'auth_json': codex_auth,
                        })

                        self.claude_profiles[name] = self._normalize_claude_profile({
                            'api_key': p.get('claude_api_key', ''),
                            'base_url': p.get('claude_base_url', ''),
                            'model': p.get('claude_model', ''),
                        })

                    if last_active in self.codex_profiles:
                        self.codex_active_profile = last_active
                    if last_active in self.claude_profiles:
                        self.claude_active_profile = last_active
            except Exception as e:
                self.set_status(f'加载供应商失败: {e}', 'error')

        # 若为空则初始化默认
        if not self.codex_profiles:
            self.codex_profiles['默认'] = self._normalize_codex_profile(self._capture_current_codex_profile())
            self.codex_active_profile = '默认'

        if not self.claude_profiles:
            self.claude_profiles['默认'] = self._normalize_claude_profile(self._capture_current_claude_profile())
            self.claude_active_profile = '默认'

        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

        self._refresh_profiles_ui()

        if self.codex_active_profile in self.codex_profiles:
            self.codex_profile_var.set(self.codex_active_profile)
            self._load_codex_profile_to_ui(self.codex_active_profile)

        if self.claude_active_profile in self.claude_profiles:
            self.claude_profile_var.set(self.claude_active_profile)
            self._load_claude_profile_to_ui(self.claude_active_profile)

    def _persist_profiles(self):
        """保存 profiles 到磁盘（v2）"""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': 2,
            'codex': {
                'last_active': self.codex_active_profile,
                'profiles': self.codex_profiles,
            },
            'claude': {
                'last_active': self.claude_active_profile,
                'profiles': self.claude_profiles,
            },
        }
        with open(self.profiles_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _refresh_profiles_ui(self):
        codex_names = sorted(self.codex_profiles.keys())
        self.codex_profile_combo['values'] = codex_names
        if not self.codex_active_profile and codex_names:
            self.codex_active_profile = codex_names[0]

        claude_names = sorted(self.claude_profiles.keys())
        self.claude_profile_combo['values'] = claude_names
        if not self.claude_active_profile and claude_names:
            self.claude_active_profile = claude_names[0]

    def _capture_current_codex_profile(self) -> Dict[str, Any]:
        return {
            'base_url': self.codex_baseurl.get().strip(),
            'model': self.codex_model.get().strip(),
            'api_key': self.codex_apikey.get().strip(),
            'config_toml': self.codex_toml_text.get('1.0', tk.END).strip(),
            'auth_json': self.codex_auth_text.get('1.0', tk.END).strip(),
        }

    def _capture_current_claude_profile(self) -> Dict[str, Any]:
        return {
            'api_key': self.claude_apikey.get().strip(),
            'base_url': self.claude_baseurl.get().strip(),
            'model': self.claude_model.get().strip(),
        }

    def _load_codex_profile_to_ui(self, name: str):
        profile = self.codex_profiles.get(name)
        if not profile:
            return

        self.codex_baseurl.delete(0, tk.END)
        self.codex_baseurl.insert(0, profile.get('base_url', ''))

        self.codex_model.delete(0, tk.END)
        self.codex_model.insert(0, profile.get('model', ''))

        self.codex_apikey.delete(0, tk.END)
        self.codex_apikey.insert(0, profile.get('api_key', ''))

        self.codex_toml_text.delete('1.0', tk.END)
        if profile.get('config_toml'):
            self.codex_toml_text.insert('1.0', profile.get('config_toml'))

        self.codex_auth_text.delete('1.0', tk.END)
        auth_text = (profile.get('auth_json') or '').strip()
        if auth_text:
            try:
                auth_text = json.dumps(json.loads(auth_text), indent=2, ensure_ascii=False)
            except Exception:
                pass
            self.codex_auth_text.insert('1.0', auth_text)

        self.set_status(f'已加载 Codex 供应商: {name}')

    def _load_claude_profile_to_ui(self, name: str):
        profile = self.claude_profiles.get(name)
        if not profile:
            return

        self.claude_apikey.delete(0, tk.END)
        self.claude_apikey.insert(0, profile.get('api_key', ''))

        self.claude_baseurl.delete(0, tk.END)
        self.claude_baseurl.insert(0, profile.get('base_url', ''))

        self.claude_model.delete(0, tk.END)
        self.claude_model.insert(0, profile.get('model', ''))

        self.set_status(f'已加载 Claude 供应商: {name}')

    def on_codex_profile_selected(self, _event=None):
        name = self.codex_profile_var.get().strip()
        if not name or name not in self.codex_profiles:
            return
        self.codex_active_profile = name
        self._load_codex_profile_to_ui(name)
        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商状态失败: {e}', 'error')

    def on_claude_profile_selected(self, _event=None):
        name = self.claude_profile_var.get().strip()
        if not name or name not in self.claude_profiles:
            return
        self.claude_active_profile = name
        self._load_claude_profile_to_ui(name)
        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商状态失败: {e}', 'error')

    def create_codex_profile(self):
        name = simpledialog.askstring('新增 Codex 供应商', '请输入 Codex 供应商名称：')
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.codex_profiles:
            messagebox.showerror('错误', f'Codex 供应商已存在: {name}')
            return

        self.codex_profiles[name] = self._normalize_codex_profile(self._capture_current_codex_profile())
        self.codex_active_profile = name
        self._refresh_profiles_ui()
        self.codex_profile_var.set(name)
        try:
            self._persist_profiles()
            self.set_status(f'已新增 Codex 供应商: {name}')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

    def save_codex_profile(self):
        name = self.codex_profile_var.get().strip()
        if not name:
            messagebox.showerror('错误', '请先选择一个 Codex 供应商，或点击“新增”。')
            return

        self.codex_profiles[name] = self._normalize_codex_profile(self._capture_current_codex_profile())
        self.codex_active_profile = name
        try:
            self._persist_profiles()
            self.set_status(f'已保存 Codex 供应商: {name}')
            messagebox.showinfo('成功', f'Codex 供应商“{name}”已保存。')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')
            messagebox.showerror('错误', f'保存 Codex 供应商失败:\n{e}')

    def delete_codex_profile(self):
        name = self.codex_profile_var.get().strip()
        if not name or name not in self.codex_profiles:
            return
        if not messagebox.askyesno('确认删除', f'确定要删除 Codex 供应商“{name}”吗？'):
            return

        del self.codex_profiles[name]
        if self.codex_active_profile == name:
            self.codex_active_profile = None

        self._refresh_profiles_ui()
        values = list(self.codex_profile_combo['values'])
        if values:
            self.codex_active_profile = values[0]
            self.codex_profile_var.set(self.codex_active_profile)
            self._load_codex_profile_to_ui(self.codex_active_profile)
        else:
            self.codex_profile_var.set('')

        try:
            self._persist_profiles()
            self.set_status(f'已删除 Codex 供应商: {name}')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

    def apply_codex_profile(self):
        name = self.codex_profile_var.get().strip()
        if not name or name not in self.codex_profiles:
            messagebox.showerror('错误', '请先选择一个 Codex 供应商。')
            return
        profile = self.codex_profiles[name]
        if not messagebox.askyesno('确认应用', f'将 Codex 供应商“{name}”的基础配置写入到系统配置文件？'):
            return

        try:
            self._apply_codex_basic_values(
                base_url=(profile.get('base_url') or '').strip(),
                model=(profile.get('model') or '').strip(),
                api_key=(profile.get('api_key') or '').strip(),
            )
            self.set_status(f'已应用 Codex 供应商: {name}')
            messagebox.showinfo('成功', f'Codex 供应商“{name}”已应用并同步到 WSL（如可用）。')
        except Exception as e:
            self.set_status(f'应用 Codex 供应商失败: {e}', 'error')
            messagebox.showerror('错误', f'应用 Codex 供应商失败:\n{e}')

    def create_claude_profile(self):
        name = simpledialog.askstring('新增 Claude 供应商', '请输入 Claude 供应商名称：')
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.claude_profiles:
            messagebox.showerror('错误', f'Claude 供应商已存在: {name}')
            return

        self.claude_profiles[name] = self._normalize_claude_profile(self._capture_current_claude_profile())
        self.claude_active_profile = name
        self._refresh_profiles_ui()
        self.claude_profile_var.set(name)
        try:
            self._persist_profiles()
            self.set_status(f'已新增 Claude 供应商: {name}')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

    def save_claude_profile(self):
        name = self.claude_profile_var.get().strip()
        if not name:
            messagebox.showerror('错误', '请先选择一个 Claude 供应商，或点击“新增”。')
            return

        self.claude_profiles[name] = self._normalize_claude_profile(self._capture_current_claude_profile())
        self.claude_active_profile = name
        try:
            self._persist_profiles()
            self.set_status(f'已保存 Claude 供应商: {name}')
            messagebox.showinfo('成功', f'Claude 供应商“{name}”已保存。')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')
            messagebox.showerror('错误', f'保存 Claude 供应商失败:\n{e}')

    def delete_claude_profile(self):
        name = self.claude_profile_var.get().strip()
        if not name or name not in self.claude_profiles:
            return
        if not messagebox.askyesno('确认删除', f'确定要删除 Claude 供应商“{name}”吗？'):
            return

        del self.claude_profiles[name]
        if self.claude_active_profile == name:
            self.claude_active_profile = None

        self._refresh_profiles_ui()
        values = list(self.claude_profile_combo['values'])
        if values:
            self.claude_active_profile = values[0]
            self.claude_profile_var.set(self.claude_active_profile)
            self._load_claude_profile_to_ui(self.claude_active_profile)
        else:
            self.claude_profile_var.set('')

        try:
            self._persist_profiles()
            self.set_status(f'已删除 Claude 供应商: {name}')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

    def apply_claude_profile(self):
        name = self.claude_profile_var.get().strip()
        if not name or name not in self.claude_profiles:
            messagebox.showerror('错误', '请先选择一个 Claude 供应商。')
            return
        profile = self.claude_profiles[name]
        if not messagebox.askyesno('确认应用', f'将 Claude 供应商“{name}”配置写入到系统配置文件？'):
            return

        try:
            self._write_claude_settings(
                api_key=(profile.get('api_key') or '').strip(),
                base_url=(profile.get('base_url') or '').strip(),
                model=(profile.get('model') or '').strip(),
            )
            self.set_status(f'已应用 Claude 供应商: {name}')
            messagebox.showinfo('成功', f'Claude 供应商“{name}”已应用并同步到 WSL（如可用）。')
        except Exception as e:
            self.set_status(f'应用 Claude 供应商失败: {e}', 'error')
            messagebox.showerror('错误', f'应用 Claude 供应商失败:\n{e}')

    def setup_codex_tab(self, parent):
        """设置 Codex 配置标签页"""
        # 供应商（Codex 独立）
        provider_frame = ttk.LabelFrame(parent, text="Codex 供应商（独立配置）", padding=10)
        provider_frame.pack(fill='x', padx=10, pady=(10, 6))

        ttk.Label(provider_frame, text="供应商:").pack(side='left')
        self.codex_profile_var = tk.StringVar()
        self.codex_profile_combo = ttk.Combobox(provider_frame, textvariable=self.codex_profile_var, width=28, state="readonly")
        self.codex_profile_combo.pack(side='left', padx=8)
        self.codex_profile_combo.bind("<<ComboboxSelected>>", self.on_codex_profile_selected)

        ttk.Button(provider_frame, text="新增", command=self.create_codex_profile).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="保存", command=self.save_codex_profile).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="删除", command=self.delete_codex_profile).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="应用该供应商", command=self.apply_codex_profile).pack(side='left', padx=12)

        # 基础配置（默认展示）
        basic_frame = ttk.LabelFrame(parent, text="基础配置（默认）", padding=12)
        basic_frame.pack(fill='x', padx=10, pady=6)

        ttk.Label(basic_frame, text="Base URL:").grid(row=0, column=0, sticky='w', pady=8)
        self.codex_baseurl = ttk.Entry(basic_frame, width=70)
        self.codex_baseurl.grid(row=0, column=1, sticky='we', padx=10, pady=8)

        ttk.Label(basic_frame, text="Model:").grid(row=1, column=0, sticky='w', pady=8)
        self.codex_model = ttk.Entry(basic_frame, width=70)
        self.codex_model.grid(row=1, column=1, sticky='we', padx=10, pady=8)

        ttk.Label(basic_frame, text="API Key:").grid(row=2, column=0, sticky='w', pady=8)
        self.codex_apikey = ttk.Entry(basic_frame, width=70, show="*")
        self.codex_apikey.grid(row=2, column=1, sticky='we', padx=10, pady=8)

        show_key_var = tk.BooleanVar(value=False)

        def toggle_key():
            self.codex_apikey.config(show="" if show_key_var.get() else "*")

        ttk.Checkbutton(basic_frame, text="显示", variable=show_key_var, command=toggle_key).grid(row=2, column=2, sticky='w')

        btn_frame = ttk.Frame(basic_frame)
        btn_frame.grid(row=3, column=0, columnspan=3, sticky='w', pady=(8, 0))
        ttk.Button(btn_frame, text="应用基础配置", command=self.apply_codex_basic_from_ui).pack(side='left')
        ttk.Button(btn_frame, text="编辑完整 TOML/JSON…", command=self.toggle_codex_advanced).pack(side='left', padx=10)

        # 高级：完整配置编辑器（默认隐藏，但控件始终创建，便于加载/保存 profile）
        self.codex_advanced_visible = False
        self.codex_advanced_frame = ttk.LabelFrame(parent, text="完整配置（高级）", padding=10)

        # config.toml 区域
        toml_frame = ttk.LabelFrame(self.codex_advanced_frame, text="config.toml（完整）", padding=10)
        toml_frame.pack(fill='both', expand=True, padx=10, pady=(4, 6))

        self.codex_toml_text = scrolledtext.ScrolledText(toml_frame, height=10, wrap=tk.WORD)
        self.codex_toml_text.pack(fill='both', expand=True)

        ttk.Button(toml_frame, text="应用完整 config.toml（合并）", command=self.apply_codex_toml).pack(pady=5)

        # auth.json 区域
        auth_frame = ttk.LabelFrame(self.codex_advanced_frame, text="auth.json（完整）", padding=10)
        auth_frame.pack(fill='both', expand=True, padx=10, pady=(6, 4))

        self.codex_auth_text = scrolledtext.ScrolledText(auth_frame, height=10, wrap=tk.WORD)
        self.codex_auth_text.pack(fill='both', expand=True)

        ttk.Button(auth_frame, text="应用完整 auth.json（合并）", command=self.apply_codex_auth).pack(pady=5)
    def setup_claude_tab(self, parent):
        """设置 Claude 配置标签页"""
        # 供应商（Claude 独立）
        provider_frame = ttk.LabelFrame(parent, text="Claude 供应商（独立配置）", padding=10)
        provider_frame.pack(fill='x', padx=10, pady=(10, 6))

        ttk.Label(provider_frame, text="供应商:").pack(side='left')
        self.claude_profile_var = tk.StringVar()
        self.claude_profile_combo = ttk.Combobox(provider_frame, textvariable=self.claude_profile_var, width=28, state="readonly")
        self.claude_profile_combo.pack(side='left', padx=8)
        self.claude_profile_combo.bind("<<ComboboxSelected>>", self.on_claude_profile_selected)

        ttk.Button(provider_frame, text="新增", command=self.create_claude_profile).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="保存", command=self.save_claude_profile).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="删除", command=self.delete_claude_profile).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="应用该供应商", command=self.apply_claude_profile).pack(side='left', padx=12)

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

        show_key_var = tk.BooleanVar(value=False)

        def toggle_key():
            self.claude_apikey.config(show="" if show_key_var.get() else "*")

        ttk.Checkbutton(form_frame, text="显示", variable=show_key_var, command=toggle_key).grid(row=0, column=2)

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
        ttk.Button(button_frame, text="应用 Claude 配置", command=self.apply_claude_config).pack()

        # 说明文字
        note_frame = ttk.LabelFrame(parent, text="说明", padding=10)
        note_frame.pack(fill='x', padx=10, pady=10)

        note_text = """配置方式：通过 ~/.claude/settings.json 文件配置 Claude

配置项说明：
• API Key - 存储在 env.ANTHROPIC_AUTH_TOKEN
• Base URL - 存储在 env.ANTHROPIC_BASE_URL（可选）
• Model - 存储在 env.ANTHROPIC_MODEL（可选）

应用后会自动同步到 WSL（如可用）"""

        ttk.Label(note_frame, text=note_text, justify=tk.LEFT).pack(anchor='w')

    def load_configs(self):
        """加载所有配置文件"""
        # 加载 Codex config.toml（完整内容）
        codex_toml_text = ""
        if self.codex_config_path.exists():
            with open(self.codex_config_path, 'r', encoding='utf-8') as f:
                codex_toml_text = f.read()

        self.codex_toml_text.delete('1.0', tk.END)
        if codex_toml_text.strip():
            self.codex_toml_text.insert('1.0', codex_toml_text)

        # 基础字段（尽量从 toml 提取）
        base_url, model = self._extract_codex_basic_from_toml_text(codex_toml_text)
        if base_url:
            self.codex_baseurl.delete(0, tk.END)
            self.codex_baseurl.insert(0, base_url)
        if model:
            self.codex_model.delete(0, tk.END)
            self.codex_model.insert(0, model)

        # 加载 Codex auth.json（完整内容）
        auth_text = ""
        if self.codex_auth_path.exists():
            with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                auth_text = f.read()

        self.codex_auth_text.delete('1.0', tk.END)
        if auth_text.strip():
            try:
                data = json.loads(auth_text)
                formatted = json.dumps(data, indent=2, ensure_ascii=False)
                self.codex_auth_text.insert('1.0', formatted)
            except Exception:
                self.codex_auth_text.insert('1.0', auth_text)

        api_key = self._extract_api_key_from_auth_json_text(auth_text)
        if api_key:
            self.codex_apikey.delete(0, tk.END)
            self.codex_apikey.insert(0, api_key)

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
    def toggle_codex_advanced(self):
        """显示/隐藏 Codex 完整配置编辑器"""
        if getattr(self, 'codex_advanced_visible', False):
            self.codex_advanced_frame.pack_forget()
            self.codex_advanced_visible = False
        else:
            self.codex_advanced_frame.pack(fill='both', expand=True, padx=10, pady=6)
            self.codex_advanced_visible = True

    def _extract_codex_basic_from_toml_text(self, toml_text: str) -> Tuple[str, str]:
        """从 config.toml 文本中尽量提取 base_url/model（提取不到返回空字符串）"""
        toml_text = (toml_text or '').strip()
        if not toml_text:
            return '', ''
        try:
            data = toml.loads(toml_text)
        except Exception:
            return '', ''

        def pick_first(d: Dict[str, Any], keys) -> str:
            for k in keys:
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ''

        base_url = pick_first(data, ['base_url', 'api_base', 'endpoint', 'url'])
        model = pick_first(data, ['model'])

        for section in ['openai', 'llm', 'provider', 'api']:
            sub = data.get(section)
            if isinstance(sub, dict):
                if not base_url:
                    base_url = pick_first(sub, ['base_url', 'api_base', 'endpoint', 'url'])
                if not model:
                    model = pick_first(sub, ['model'])

        return base_url, model

    def _extract_api_key_from_auth_json_text(self, auth_text: str) -> str:
        """从 auth.json 文本中尽量提取 api key（提取不到返回空字符串）"""
        auth_text = (auth_text or '').strip()
        if not auth_text:
            return ''
        try:
            data = json.loads(auth_text)
        except Exception:
            return ''
        if not isinstance(data, dict):
            return ''

        for key in ['api_key', 'openai_api_key', 'OPENAI_API_KEY', 'token', 'access_token']:
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()

        for k, v in data.items():
            if not isinstance(v, str):
                continue
            lk = str(k).lower()
            if ('key' in lk or 'token' in lk) and v.strip():
                return v.strip()

        return ''

    def apply_codex_basic_from_ui(self):
        """应用 Codex 基础配置（Base URL / Model / API Key）"""
        base_url = self.codex_baseurl.get().strip()
        model = self.codex_model.get().strip()
        api_key = self.codex_apikey.get().strip()

        if not base_url and not model and not api_key:
            messagebox.showerror('错误', 'Codex 基础配置为空：请至少填写 Base URL / Model / API Key 中的一项。')
            return

        try:
            self._apply_codex_basic_values(base_url=base_url, model=model, api_key=api_key)
            self.set_status('Codex 基础配置已更新并同步到 WSL（如可用）')
            messagebox.showinfo('成功', 'Codex 基础配置已应用并同步到 WSL（如可用）')
        except Exception as e:
            self.set_status(f'应用失败: {e}', 'error')
            messagebox.showerror('错误', f'应用 Codex 基础配置失败:\n{e}')

    def _apply_codex_basic_values(self, base_url: str, model: str, api_key: str):
        """写入 Codex 的 config.toml / auth.json，并同步到 WSL"""
        self.codex_dir.mkdir(parents=True, exist_ok=True)

        # config.toml
        existing_toml: Dict[str, Any]
        if self.codex_config_path.exists():
            with open(self.codex_config_path, 'r', encoding='utf-8') as f:
                existing_toml = toml.load(f)
        else:
            existing_toml = {}

        changed_toml = self._update_codex_toml_basic(existing_toml, base_url=base_url, model=model)
        if changed_toml:
            if self.codex_config_path.exists():
                shutil.copy(self.codex_config_path, str(self.codex_config_path) + '.backup')
            with open(self.codex_config_path, 'w', encoding='utf-8') as f:
                toml.dump(existing_toml, f)
            self.sync_file_to_wsl(self.codex_config_path, 'config.toml')

        # auth.json
        existing_auth: Dict[str, Any]
        if self.codex_auth_path.exists():
            with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                try:
                    existing_auth = json.load(f)
                except Exception:
                    existing_auth = {}
        else:
            existing_auth = {}

        changed_auth = self._update_codex_auth_basic(existing_auth, api_key=api_key)
        if changed_auth:
            if self.codex_auth_path.exists():
                shutil.copy(self.codex_auth_path, str(self.codex_auth_path) + '.backup')
            with open(self.codex_auth_path, 'w', encoding='utf-8') as f:
                json.dump(existing_auth, f, indent=2, ensure_ascii=False)
            self.sync_file_to_wsl(self.codex_auth_path, 'auth.json')

        # 刷新高级编辑器内容
        if self.codex_config_path.exists():
            self.codex_toml_text.delete('1.0', tk.END)
            self.codex_toml_text.insert('1.0', self.codex_config_path.read_text(encoding='utf-8'))
        if self.codex_auth_path.exists():
            self.codex_auth_text.delete('1.0', tk.END)
            raw = self.codex_auth_path.read_text(encoding='utf-8')
            try:
                raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
            except Exception:
                pass
            self.codex_auth_text.insert('1.0', raw)

    def _update_codex_toml_basic(self, data: Dict[str, Any], base_url: str, model: str) -> bool:
        """尽量更新 base_url/model，优先覆盖已存在字段，否则写入顶层。"""
        changed = False

        def set_if(target: Dict[str, Any], key: str, value: str) -> bool:
            if not value:
                return False
            if target.get(key) != value:
                target[key] = value
                return True
            return False

        if base_url:
            for k in ['base_url', 'api_base', 'endpoint', 'url']:
                if k in data:
                    changed |= set_if(data, k, base_url)
                    base_url = ''
                    break

        if model and 'model' in data:
            changed |= set_if(data, 'model', model)
            model = ''

        # 常见段落
        for section in ['openai', 'llm', 'provider', 'api']:
            sub = data.get(section)
            if not isinstance(sub, dict):
                continue
            if base_url:
                for k in ['base_url', 'api_base', 'endpoint', 'url']:
                    if k in sub:
                        changed |= set_if(sub, k, base_url)
                        base_url = ''
                        break
            if model and 'model' in sub:
                changed |= set_if(sub, 'model', model)
                model = ''

        # 兜底：写入顶层
        if base_url:
            changed |= set_if(data, 'base_url', base_url)
        if model:
            changed |= set_if(data, 'model', model)

        return changed

    def _update_codex_auth_basic(self, data: Dict[str, Any], api_key: str) -> bool:
        if not api_key:
            return False
        if not isinstance(data, dict):
            return False

        candidates = ['api_key', 'openai_api_key', 'OPENAI_API_KEY', 'token', 'access_token']
        for k in candidates:
            if k in data and isinstance(data.get(k), str):
                if data.get(k) != api_key:
                    data[k] = api_key
                    return True
                return False

        if data.get('api_key') != api_key:
            data['api_key'] = api_key
            return True
        return False

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

            self._write_claude_settings(api_key=api_key, base_url=base_url, model=model)

            self.set_status("Claude 配置已更新并同步到 WSL")
            messagebox.showinfo("成功", "Claude 配置已应用并同步到 WSL")

        except Exception as e:
            self.set_status(f"应用失败: {e}", "error")
            messagebox.showerror("错误", f"应用配置失败:\n{e}")
    def _write_claude_settings(self, api_key: str, base_url: str, model: str):
        """写入 Claude settings.json（抛出异常，由上层决定是否弹窗）"""
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
            shutil.copy(self.claude_settings_path, str(self.claude_settings_path) + '.backup')

        # 写入 Windows 侧配置
        with open(self.claude_settings_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 同步到 WSL
        self.sync_claude_to_wsl()

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










