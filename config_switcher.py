#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置切换工具 - 管理 Codex 和 Claude 配置文件
支持 Windows 和 WSL 配置同步
"""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import simpledialog
import json
import toml
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import shutil


class ConfigSwitcher:
    def __init__(self, root):
        self.root = root
        self.root.title("cc-config-sync")
        self.root.geometry("1000x760")
        self.root.minsize(760, 560)
        # 供应商/配置档案（profiles）存储（Codex 与 Claude 分开）
        self.app_dir = Path.home() / ".config_switcher"
        self.profiles_path = self.app_dir / "providers.json"
        self.codex_providers: Dict[str, Dict[str, Any]] = {}
        self.codex_active_provider: Optional[str] = None
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
        # 状态栏（固定在底部）
        self.status_label = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side='bottom', fill='x', padx=10, pady=(0, 6))

        # 底部按钮区域（固定在状态栏上方）
        button_frame = ttk.Frame(self.root)
        button_frame.pack(side='bottom', fill='x', padx=10, pady=(4, 2))
        ttk.Button(button_frame, text="刷新配置", command=self.load_configs).pack(side='left', padx=5)

        # 创建 Notebook (标签页)
        notebook = ttk.Notebook(self.root)
        notebook.pack(side='top', fill='both', expand=True, padx=10, pady=10)

        # Codex 配置标签页
        codex_frame = ttk.Frame(notebook)
        notebook.add(codex_frame, text='Codex 配置')
        self.setup_codex_tab(codex_frame)

        # Claude 配置标签页
        claude_frame = ttk.Frame(notebook)
        notebook.add(claude_frame, text='Claude 配置')
        self.setup_claude_tab(claude_frame)

    def _normalize_codex_provider(self, provider: Dict[str, Any]) -> Dict[str, Any]:
        """规范化 Codex 供应商配置"""
        return {
            'name': provider.get('name', ''),
            'base_url': provider.get('base_url', ''),
            'model': provider.get('model', ''),
            'api_key': provider.get('api_key', ''),
        }

    def _normalize_claude_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'api_key': profile.get('api_key', ''),
            'base_url': profile.get('base_url', ''),
            'model': profile.get('model', ''),
        }

    def _load_codex_providers_from_toml(self):
        """从 config.toml 读取所有 [model_providers.xxx] 定义"""
        if not self.codex_config_path.exists():
            return

        try:
            data = toml.load(self.codex_config_path)

            # 读取顶层的 model（作为默认值）
            top_level_model = data.get('model', '')

            # 读取 model_providers 段落
            if 'model_providers' in data:
                for provider_name, provider_config in data['model_providers'].items():
                    # 如果供应商配置中没有 model，使用顶层的 model
                    provider_model = provider_config.get('model', '') or top_level_model

                    self.codex_providers[provider_name] = self._normalize_codex_provider({
                        'name': provider_config.get('name', provider_name),
                        'base_url': provider_config.get('base_url', ''),
                        'model': provider_model,
                        'api_key': '',  # API key 从 auth.json 加载
                    })

            # 读取当前激活的供应商
            current_provider = data.get('model_provider', '')
            if current_provider and current_provider in self.codex_providers:
                self.codex_active_provider = current_provider

            # 从 auth.json 加载 API key
            if self.codex_auth_path.exists():
                try:
                    with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                        auth_data = json.load(f)
                        api_key = auth_data.get('OPENAI_API_KEY', '') or auth_data.get('api_key', '')
                        # 将 API key 设置到所有供应商（因为 auth.json 是全局的）
                        if api_key:
                            for provider in self.codex_providers.values():
                                provider['api_key'] = api_key
                except Exception as e:
                    print(f"加载 auth.json 失败: {e}")

        except Exception as e:
            print(f"从 config.toml 加载 Codex 供应商失败: {e}")

    def load_profiles(self):
        """从磁盘加载供应商/配置档案列表（v3：使用原生 model_providers）"""
        # 首先从 config.toml 加载 Codex 原生供应商定义
        self.codex_providers = {}
        self.codex_active_provider = None
        self._load_codex_providers_from_toml()

        # Claude 配置
        self.claude_profiles = {}
        self.claude_active_profile = None

        if self.profiles_path.exists():
            try:
                with open(self.profiles_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                version = int(data.get('version', 1))
                if version >= 2:
                    codex = data.get('codex', {}) or {}
                    claude = data.get('claude', {}) or {}

                    # 从 providers.json 中补充 API key 到已加载的供应商
                    for name, p in (codex.get('providers', {}) or {}).items():
                        if name in self.codex_providers:
                            # 供应商已从 config.toml 加载，只补充 API key
                            if p and p.get('api_key'):
                                self.codex_providers[name]['api_key'] = p['api_key']
                        else:
                            # 供应商不在 config.toml 中，从 providers.json 加载（向后兼容）
                            self.codex_providers[name] = self._normalize_codex_provider(p or {})

                    for name, p in (claude.get('profiles', {}) or {}).items():
                        self.claude_profiles[name] = self._normalize_claude_profile(p or {})

                    if codex.get('last_active') in self.codex_providers:
                        self.codex_active_provider = codex.get('last_active')
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

                        self.codex_providers[name] = self._normalize_codex_provider({
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

                    if last_active in self.codex_providers:
                        self.codex_active_provider = last_active
                    if last_active in self.claude_profiles:
                        self.claude_active_profile = last_active
            except Exception as e:
                self.set_status(f'加载供应商失败: {e}', 'error')

        # 若为空则初始化默认
        if not self.codex_providers:
            self.codex_providers['默认'] = self._normalize_codex_provider(self._capture_current_codex_provider())
            self.codex_active_provider = '默认'

        if not self.claude_profiles:
            self.claude_profiles['默认'] = self._normalize_claude_profile(self._capture_current_claude_profile())
            self.claude_active_profile = '默认'

        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

        self._refresh_profiles_ui()

        if self.codex_active_provider in self.codex_providers:
            self.codex_provider_var.set(self.codex_active_provider)
            self._load_codex_provider_to_ui(self.codex_active_provider)

        if self.claude_active_profile in self.claude_profiles:
            self.claude_profile_var.set(self.claude_active_profile)
            self._load_claude_profile_to_ui(self.claude_active_profile)

    def _persist_profiles(self):
        """保存 profiles 到磁盘（v3）"""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': 3,
            'codex': {
                'last_active': self.codex_active_provider,
                'profiles': self.codex_providers,
            },
            'claude': {
                'last_active': self.claude_active_profile,
                'profiles': self.claude_profiles,
            },
        }
        with open(self.profiles_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _refresh_profiles_ui(self):
        codex_names = sorted(self.codex_providers.keys())
        self.codex_provider_combo['values'] = codex_names
        if not self.codex_active_provider and codex_names:
            self.codex_active_provider = codex_names[0]

        claude_names = sorted(self.claude_profiles.keys())
        self.claude_profile_combo['values'] = claude_names
        if not self.claude_active_profile and claude_names:
            self.claude_active_profile = claude_names[0]

    def _capture_current_codex_provider(self) -> Dict[str, Any]:
        """从 UI 捕获当前 Codex 供应商配置"""
        return {
            'name': self.codex_provider_var.get().strip(),
            'base_url': self.codex_baseurl.get().strip(),
            'model': self.codex_model.get().strip(),
            'api_key': self.codex_apikey.get().strip(),
        }

    def _capture_current_claude_profile(self) -> Dict[str, Any]:
        return {
            'api_key': self.claude_apikey.get().strip(),
            'base_url': self.claude_baseurl.get().strip(),
            'model': self.claude_model.get().strip(),
        }

    def _load_codex_provider_to_ui(self, name: str):
        """从供应商配置加载到 UI"""
        provider = self.codex_providers.get(name)
        if not provider:
            return

        self.codex_baseurl.delete(0, tk.END)
        self.codex_baseurl.insert(0, provider.get('base_url', ''))

        self.codex_model.delete(0, tk.END)
        self.codex_model.insert(0, provider.get('model', ''))

        self.codex_apikey.delete(0, tk.END)
        self.codex_apikey.insert(0, provider.get('api_key', ''))

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

    def on_codex_provider_selected(self, _event=None):
        name = self.codex_provider_var.get().strip()
        if not name or name not in self.codex_providers:
            return
        self.codex_active_provider = name
        self._load_codex_provider_to_ui(name)
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

    def create_codex_provider(self):
        """创建新的 Codex 供应商"""
        name = simpledialog.askstring('新增 Codex 供应商', '请输入 Codex 供应商名称（英文，如 openai, anthropic）：')
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.codex_providers:
            messagebox.showwarning('警告', f'供应商"{name}"已存在，请使用"保存"按钮更新。')
            return

        # 创建默认配置
        self.codex_providers[name] = self._normalize_codex_provider({
            'name': name,
            'base_url': '',
            'model': '',
            'api_key': '',
        })

        self.codex_active_provider = name
        self._refresh_profiles_ui()
        self.codex_provider_var.set(name)
        self._load_codex_provider_to_ui(name)

        try:
            self._persist_profiles()
            messagebox.showinfo('提示', f'供应商"{name}"已创建，请填写配置后点击"保存到 config.toml"。')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

    def save_codex_provider(self):
        """保存当前供应商配置到 config.toml 的 [model_providers.xxx] 段落"""
        provider_name = self.codex_provider_var.get().strip()
        if not provider_name:
            messagebox.showerror('错误', '请先选择或创建一个供应商。')
            return

        # 从 UI 捕获配置
        provider_config = self._capture_current_codex_provider()

        try:
            # 1. 读取现有 config.toml
            if self.codex_config_path.exists():
                data = toml.load(self.codex_config_path)
            else:
                self.codex_dir.mkdir(parents=True, exist_ok=True)
                data = {}

            # 2. 确保 model_providers 段落存在
            if 'model_providers' not in data:
                data['model_providers'] = {}

            # 3. 更新供应商定义（不包含 API key）
            existing_provider = data['model_providers'].get(provider_name, {})
            provider_entry = {
                'name': provider_config.get('name', provider_name),
                'base_url': provider_config.get('base_url', ''),
                'wire_api': 'responses',
                'requires_openai_auth': True,
            }
            if isinstance(existing_provider, dict):
                if 'wire_api' in existing_provider:
                    provider_entry['wire_api'] = existing_provider['wire_api']
                if 'requires_openai_auth' in existing_provider:
                    provider_entry['requires_openai_auth'] = existing_provider['requires_openai_auth']
            data['model_providers'][provider_name] = provider_entry

            # 4. 备份并保存
            if self.codex_config_path.exists():
                shutil.copy(self.codex_config_path, str(self.codex_config_path) + '.backup')
            with open(self.codex_config_path, 'w', encoding='utf-8') as f:
                toml.dump(data, f)

            # 5. 更新 auth.json 中的 API Key
            if provider_config.get('api_key'):
                self._update_codex_auth_basic(provider_config['api_key'])

            # 6. 同步到 WSL
            self.sync_file_to_wsl(self.codex_config_path, 'config.toml')
            if self.codex_auth_path.exists():
                self.sync_file_to_wsl(self.codex_auth_path, 'auth.json')

            # 7. 更新内存中的供应商列表
            self.codex_providers[provider_name] = provider_config
            self.codex_active_provider = provider_name

            # 8. 保存到 providers.json
            self._persist_profiles()

            messagebox.showinfo('成功', f'供应商"{provider_name}"已保存到 config.toml')
            self.set_status(f'已保存 Codex 供应商: {provider_name}')

        except Exception as e:
            messagebox.showerror('错误', f'保存供应商失败:\n{e}')
            self.set_status(f'保存供应商失败: {e}', 'error')


    def _update_codex_auth_basic(self, api_key: str):
        """更新 auth.json 中的 API key"""
        if not api_key:
            return

        if self.codex_auth_path.exists():
            with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}
        else:
            data = {}

        data['OPENAI_API_KEY'] = api_key
        data.pop('api_key', None)

        self.codex_dir.mkdir(parents=True, exist_ok=True)
        if self.codex_auth_path.exists():
            shutil.copy(self.codex_auth_path, str(self.codex_auth_path) + '.backup')

        with open(self.codex_auth_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def delete_codex_provider(self):
        """从 config.toml 删除供应商定义"""
        provider_name = self.codex_provider_var.get().strip()
        if not provider_name:
            messagebox.showerror('错误', '请先选择一个供应商。')
            return

        if not messagebox.askyesno('确认删除', f'确定要删除供应商"{provider_name}"？\n这将从 config.toml 中移除该供应商定义。'):
            return

        try:
            # 1. 从 config.toml 删除
            if self.codex_config_path.exists():
                data = toml.load(self.codex_config_path)
                if 'model_providers' in data and provider_name in data['model_providers']:
                    del data['model_providers'][provider_name]

                    shutil.copy(self.codex_config_path, str(self.codex_config_path) + '.backup')
                    with open(self.codex_config_path, 'w', encoding='utf-8') as f:
                        toml.dump(data, f)

                    self.sync_file_to_wsl(self.codex_config_path, 'config.toml')

            # 2. 从内存删除
            if provider_name in self.codex_providers:
                del self.codex_providers[provider_name]

            # 3. 选择新的激活供应商
            if self.codex_active_provider == provider_name:
                self.codex_active_provider = None

            self._refresh_profiles_ui()
            values = list(self.codex_provider_combo['values'])
            if values:
                self.codex_active_provider = values[0]
                self.codex_provider_var.set(self.codex_active_provider)
                self._load_codex_provider_to_ui(self.codex_active_provider)
            else:
                self.codex_provider_var.set('')

            self._persist_profiles()
            messagebox.showinfo('成功', f'供应商"{provider_name}"已删除')
            self.set_status(f'已删除 Codex 供应商: {provider_name}')

        except Exception as e:
            messagebox.showerror('错误', f'删除供应商失败:\n{e}')
            self.set_status(f'删除供应商失败: {e}', 'error')

    def switch_codex_provider(self):
        """切换 Codex 供应商（修改 model_provider 字段）"""
        provider_name = self.codex_provider_var.get().strip()
        if not provider_name or provider_name not in self.codex_providers:
            messagebox.showerror('错误', '请先选择一个 Codex 供应商。')
            return

        if not messagebox.askyesno('确认切换', f'切换到 Codex 供应商"{provider_name}"？\n这将修改 config.toml 中的 model_provider 字段。'):
            return

        try:
            # 1. 读取现有 config.toml
            if self.codex_config_path.exists():
                data = toml.load(self.codex_config_path)
            else:
                self.codex_dir.mkdir(parents=True, exist_ok=True)
                data = {}

            # 2. 修改 model_provider 字段
            data['model_provider'] = provider_name

            # 3. 从供应商配置更新顶层字段
            provider = self.codex_providers[provider_name]
            if provider.get('base_url'):
                data['base_url'] = provider['base_url']
            if provider.get('model'):
                data['model'] = provider['model']

            # 4. 备份并保存
            if self.codex_config_path.exists():
                shutil.copy(self.codex_config_path, str(self.codex_config_path) + '.backup')
            with open(self.codex_config_path, 'w', encoding='utf-8') as f:
                toml.dump(data, f)

            # 5. 更新 auth.json 中的 API Key
            if provider.get('api_key'):
                self._update_codex_auth_basic(provider['api_key'])

            # 6. 同步到 WSL
            self.sync_file_to_wsl(self.codex_config_path, 'config.toml')
            if self.codex_auth_path.exists():
                self.sync_file_to_wsl(self.codex_auth_path, 'auth.json')

            self.codex_active_provider = provider_name
            self._persist_profiles()

            messagebox.showinfo('成功', f'已切换到 Codex 供应商"{provider_name}"')
            self.set_status(f'已切换到 Codex 供应商: {provider_name}')
            self.load_configs()  # 刷新 UI

        except Exception as e:
            messagebox.showerror('错误', f'切换供应商失败:\n{e}')
            self.set_status(f'切换供应商失败: {e}', 'error')

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
        # 供应商管理
        provider_frame = ttk.LabelFrame(parent, text="Codex 供应商管理", padding=10)
        provider_frame.pack(fill='x', padx=10, pady=(10, 6))

        ttk.Label(provider_frame, text="供应商：").pack(side='left')
        self.codex_provider_var = tk.StringVar()
        self.codex_provider_combo = ttk.Combobox(provider_frame, textvariable=self.codex_provider_var, width=28, state="readonly")
        self.codex_provider_combo.pack(side='left', padx=8)
        self.codex_provider_combo.bind("<<ComboboxSelected>>", self.on_codex_provider_selected)

        ttk.Button(provider_frame, text="新增", command=self.create_codex_provider).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="保存", command=self.save_codex_provider).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="删除", command=self.delete_codex_provider).pack(side='left', padx=4)
        ttk.Button(provider_frame, text="应用该供应商", command=self.switch_codex_provider).pack(side='left', padx=12)

        # 说明文字
        info_label = ttk.Label(parent, text="修改 Codex 配置文件 (~/.codex/config.toml 与 ~/.codex/auth.json)", foreground="blue")
        info_label.pack(pady=5)

        # 配置表单
        form_frame = ttk.LabelFrame(parent, text="供应商配置", padding=12)
        form_frame.pack(fill='x', padx=10, pady=6)

        ttk.Label(form_frame, text="Base URL:").grid(row=0, column=0, sticky='w', pady=10)
        self.codex_baseurl = ttk.Entry(form_frame, width=60)
        self.codex_baseurl.grid(row=0, column=1, sticky='we', padx=10, pady=10)

        ttk.Label(form_frame, text="Model:").grid(row=1, column=0, sticky='w', pady=10)
        self.codex_model = ttk.Entry(form_frame, width=60)
        self.codex_model.grid(row=1, column=1, sticky='we', padx=10, pady=10)

        ttk.Label(form_frame, text="API Key:").grid(row=2, column=0, sticky='w', pady=10)
        self.codex_apikey = ttk.Entry(form_frame, width=60, show="*")
        self.codex_apikey.grid(row=2, column=1, sticky='we', padx=10, pady=10)

        show_key_var = tk.BooleanVar(value=False)

        def toggle_key():
            self.codex_apikey.config(show="" if show_key_var.get() else "*")

        ttk.Checkbutton(form_frame, text="显示", variable=show_key_var, command=toggle_key).grid(row=2, column=2, sticky='w')

        form_frame.columnconfigure(1, weight=1)

        note_frame = ttk.LabelFrame(parent, text="说明", padding=10)
        note_frame.pack(fill='x', padx=10, pady=10)

        note_text = """配置项说明：
• Base URL - 写入 ~/.codex/config.toml 的 model_providers.<供应商>.base_url
• Model - 写入 ~/.codex/config.toml 的 model
• API Key - 写入 ~/.codex/auth.json 的 OPENAI_API_KEY

应用“供应商”会切换 config.toml 中的 model_provider 并同步到 WSL（如可用）。
新建供应商默认会带有 wire_api=\"responses\" 与 requires_openai_auth=true。"""

        ttk.Label(note_frame, text=note_text, justify=tk.LEFT).pack(anchor='w')

    def setup_claude_tab(self, parent):
        """设置 Claude 配置标签页"""
        # 供应商管理
        provider_frame = ttk.LabelFrame(parent, text="Claude 供应商管理", padding=10)
        provider_frame.pack(fill='x', padx=10, pady=(10, 6))

        ttk.Label(provider_frame, text="供应商：").pack(side='left')
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
        form_frame = ttk.LabelFrame(parent, text="供应商配置", padding=12)
        form_frame.pack(fill='x', padx=10, pady=6)

        # Base URL
        ttk.Label(form_frame, text="Base URL:").grid(row=0, column=0, sticky='w', pady=10)
        self.claude_baseurl = ttk.Entry(form_frame, width=60)
        self.claude_baseurl.grid(row=0, column=1, sticky='we', pady=10, padx=10)

        # Model
        ttk.Label(form_frame, text="Model:").grid(row=1, column=0, sticky='w', pady=10)
        self.claude_model = ttk.Entry(form_frame, width=60)
        self.claude_model.grid(row=1, column=1, sticky='we', pady=10, padx=10)

        # API Key
        ttk.Label(form_frame, text="API Key:").grid(row=2, column=0, sticky='w', pady=10)
        self.claude_apikey = ttk.Entry(form_frame, width=60, show="*")
        self.claude_apikey.grid(row=2, column=1, sticky='we', pady=10, padx=10)

        show_key_var = tk.BooleanVar(value=False)

        def toggle_key():
            self.claude_apikey.config(show="" if show_key_var.get() else "*")

        ttk.Checkbutton(form_frame, text="显示", variable=show_key_var, command=toggle_key).grid(row=2, column=2, sticky='w')
        form_frame.columnconfigure(1, weight=1)

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
        # 加载 Codex 基础配置
        if self.codex_config_path.exists():
            try:
                data = toml.load(self.codex_config_path)

                # 提取基础字段
                base_url = data.get('base_url', '')
                model = data.get('model', '')

                if base_url:
                    self.codex_baseurl.delete(0, tk.END)
                    self.codex_baseurl.insert(0, base_url)
                if model:
                    self.codex_model.delete(0, tk.END)
                    self.codex_model.insert(0, model)
            except Exception as e:
                print(f"加载 Codex config.toml 失败: {e}")

        # 加载 Codex auth.json
        if self.codex_auth_path.exists():
            try:
                    with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    api_key = data.get('OPENAI_API_KEY', '') or data.get('api_key', '')
                    if api_key:
                        self.codex_apikey.delete(0, tk.END)
                        self.codex_apikey.insert(0, api_key)
            except Exception as e:
                print(f"加载 Codex auth.json 失败: {e}")

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

        for key in ['OPENAI_API_KEY', 'api_key', 'openai_api_key', 'token', 'access_token']:
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










