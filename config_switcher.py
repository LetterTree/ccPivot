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
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import shutil
import sys
import urllib.request
import urllib.error
import threading
import time

try:
    import ttkbootstrap as tb
except Exception:
    tb = None


class ConfigSwitcher:
    CLAUDE_ENV_KEYS = (
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
    )

    def __init__(self, root):
        try:
            print("初始化开始...")
            self.root = root
            self.root.title("ccPivot")
            self.root.geometry("960x560")
            self.root.minsize(900, 500)
            self._set_app_icon()
            self.theme_available = tb is not None

            print("初始化变量...")
            self.app_dir = Path.home() / ".config_switcher"
            self.profiles_path = self.app_dir / "providers.json"
            self.codex_runtime_provider_alias = "cc_session_shared"
            self.codex_providers: Dict[str, Dict[str, Any]] = {}
            self.codex_active_provider: Optional[str] = None
            self.codex_selected_provider: Optional[str] = None
            self.claude_profiles: Dict[str, Dict[str, Any]] = {}
            self.claude_active_profile: Optional[str] = None

            self.home = Path.home()
            self.codex_dir = self.home / ".codex"
            self.codex_config_path = self.codex_dir / "config.toml"
            self.codex_auth_path = self.codex_dir / "auth.json"

            self.claude_dir = self.home / ".claude"
            self.claude_settings_path = self.claude_dir / "settings.json"

            print("获取 WSL 路径...")
            self.wsl_distro = self.get_wsl_distro()
            self.wsl_home = self.get_wsl_home()

            print("设置 UI...")
            self.setup_ui()
            print("初始化完成，延迟加载配置...")
            # 延迟加载配置，避免阻塞 UI
            self.root.after(100, self._delayed_load)
        except Exception as e:
            print(f"初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def get_wsl_home(self) -> Optional[str]:
        """获取 WSL 用户主目录路径"""
        try:
            result = subprocess.run(
                ["wsl", "sh", "-lc", "echo $HOME"],
                capture_output=True,
                text=False,
                timeout=5,
                creationflags=0x08000000,
            )
            if result.returncode == 0:
                return self._decode_wsl_text(result.stdout).strip()
        except Exception as e:
            print(f"无法获取 WSL 路径: {e}")
        return None

    def _decode_wsl_text(self, raw: bytes) -> str:
        raw = raw or b""
        if b"\x00" in raw:
            return raw.decode("utf-16le").replace("\ufeff", "")
        return raw.decode("utf-8")

    def get_wsl_distro(self) -> Optional[str]:
        """获取默认 WSL 发行版名称"""
        try:
            result = subprocess.run(
                ["wsl", "-l", "-q"],
                capture_output=True,
                text=False,
                timeout=5,
                creationflags=0x08000000,
            )
            if result.returncode != 0:
                return None
            output = self._decode_wsl_text(result.stdout)
            for line in output.splitlines():
                line = line.strip().replace("\x00", "")
                if line:
                    return line
        except Exception as e:
            print(f"无法获取 WSL 发行版: {e}")
        return None

    def _normalize_project_key(self, key: str) -> str:
        if not isinstance(key, str):
            return key
        if re.match(r"^[A-Za-z]:\\+", key):
            return re.sub(r"\\+", r"\\", key)
        return key

    def _format_toml_scalar(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if value is None:
            return '""'
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _read_json_file(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_json_file(self, path: Path, data: Dict[str, Any]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _read_toml_file(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        return toml.load(path)

    def _write_toml_file(self, path: Path, data: Dict[str, Any]):
        path.parent.mkdir(parents=True, exist_ok=True)
        text = toml.dumps(data).rstrip()
        text = (text.rstrip() + "\n") if text else ""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def _extract_managed_claude_env(self, data: Dict[str, Any]) -> Dict[str, str]:
        env = data.get('env', {}) if isinstance(data, dict) else {}
        if not isinstance(env, dict):
            env = {}
        managed_env: Dict[str, str] = {}
        for key in self.CLAUDE_ENV_KEYS:
            value = env.get(key)
            if value:
                managed_env[key] = value
        return managed_env

    def _match_claude_profile_from_env(self, managed_env: Dict[str, str]) -> Optional[str]:
        if not isinstance(managed_env, dict):
            return None
        api_key = (managed_env.get('ANTHROPIC_AUTH_TOKEN') or '').strip()
        base_url = (managed_env.get('ANTHROPIC_BASE_URL') or '').strip()
        model = (managed_env.get('ANTHROPIC_MODEL') or '').strip()
        if not api_key and not base_url and not model:
            return None
        for name, profile in self.claude_profiles.items():
            if not isinstance(profile, dict):
                continue
            if (
                (profile.get('api_key') or '').strip() == api_key
                and (profile.get('base_url') or '').strip() == base_url
                and (profile.get('model') or '').strip() == model
            ):
                return name
        return None

    def _detect_claude_active_profile_windows(self) -> Optional[Tuple[Optional[str], bool]]:
        try:
            if not self.claude_settings_path.exists():
                return (None, False)
            data = self._read_json_file(self.claude_settings_path)
            managed_env = self._extract_managed_claude_env(data)
            if not managed_env:
                return (None, False)
            return (self._match_claude_profile_from_env(managed_env), True)
        except Exception as e:
            print(f"检测 Windows 侧 Claude profile 失败: {e}")
            return (None, False)

    def _detect_claude_active_profile_wsl(self) -> Optional[Tuple[Optional[str], bool]]:
        if not self.wsl_home:
            return None
        try:
            data = self._read_wsl_json(f"{self.wsl_home}/.claude/settings.json")
            managed_env = self._extract_managed_claude_env(data)
            if not managed_env:
                return (None, False)
            return (self._match_claude_profile_from_env(managed_env), True)
        except Exception as e:
            print(f"检测 WSL 侧 Claude profile 失败: {e}")
            return (None, False)

    def _build_managed_claude_env(self, api_key: str, base_url: str, model: str) -> Dict[str, str]:
        return {
            'ANTHROPIC_AUTH_TOKEN': api_key,
            'ANTHROPIC_BASE_URL': base_url,
            'ANTHROPIC_MODEL': model,
            'ANTHROPIC_DEFAULT_HAIKU_MODEL': model,
            'ANTHROPIC_DEFAULT_SONNET_MODEL': model,
            'ANTHROPIC_DEFAULT_OPUS_MODEL': model,
        }

    def _merge_claude_env_into_settings(
        self,
        target_data: Dict[str, Any],
        source_env: Dict[str, str],
        remove_missing: bool = True,
        clear_legacy_model: bool = True,
    ) -> Dict[str, Any]:
        data = dict(target_data or {})
        env = data.get('env', {})
        if not isinstance(env, dict):
            env = {}
        env = dict(env)

        for key in self.CLAUDE_ENV_KEYS:
            has_key = key in source_env
            value = source_env.get(key)
            if value:
                env[key] = value
            elif remove_missing and has_key:
                env.pop(key, None)
            elif remove_missing and not has_key:
                env.pop(key, None)

        data['env'] = env
        if clear_legacy_model:
            data.pop('model', None)
        return data

    def _quote_sh_value(self, value: str) -> str:
        return "'" + value.replace("'", "'\"'\"'") + "'"

    def _get_wsl_windows_path(self, wsl_path: str) -> Optional[Path]:
        if not self.wsl_distro or not isinstance(wsl_path, str) or not wsl_path.startswith("/"):
            return None
        unc_path = f"\\\\wsl.localhost\\{self.wsl_distro}{wsl_path.replace('/', '\\')}"
        return Path(unc_path)

    def _run_wsl_shell(self, command: str, input_text: Optional[str] = None) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ['wsl', 'sh', '-lc', command],
            input=input_text,
            capture_output=True,
            text=True,
            encoding='utf-8',
            creationflags=0x08000000,
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip() or f"WSL 命令执行失败: {command}")
        return result

    def _read_wsl_json(self, wsl_path: str) -> Dict[str, Any]:
        win_path = self._get_wsl_windows_path(wsl_path)
        if win_path is not None:
            return self._read_json_file(win_path)
        quoted_path = self._quote_sh_value(wsl_path)
        result = self._run_wsl_shell(f'if [ -f {quoted_path} ]; then cat {quoted_path}; else printf "{{}}"; fi')
        text = (result.stdout or '').strip() or '{}'
        return json.loads(text)

    def _write_wsl_json(self, wsl_path: str, data: Dict[str, Any]):
        win_path = self._get_wsl_windows_path(wsl_path)
        if win_path is not None:
            self._write_json_file(win_path, data)
            return
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        quoted_path = self._quote_sh_value(wsl_path)
        self._run_wsl_shell(f'cat > {quoted_path}', input_text=payload)

    def _read_wsl_toml(self, wsl_path: str) -> Dict[str, Any]:
        win_path = self._get_wsl_windows_path(wsl_path)
        if win_path is not None:
            return self._read_toml_file(win_path)
        quoted_path = self._quote_sh_value(wsl_path)
        result = self._run_wsl_shell(f'if [ -f {quoted_path} ]; then cat {quoted_path}; else printf \"\"; fi')
        text = result.stdout or ''
        return toml.loads(text) if text.strip() else {}

    def _write_wsl_toml(self, wsl_path: str, data: Dict[str, Any]):
        win_path = self._get_wsl_windows_path(wsl_path)
        if win_path is not None:
            self._write_toml_file(win_path, data)
            return
        text = toml.dumps(data).rstrip()
        text = (text.rstrip() + "\n") if text else ""
        quoted_path = self._quote_sh_value(wsl_path)
        self._run_wsl_shell(f'cat > {quoted_path}', input_text=text)

    def _render_projects_section(self, projects: Dict[str, Any]) -> str:
        lines = []
        normalized_projects: Dict[str, Dict[str, Any]] = {}
        for key, value in projects.items():
            normalized_key = self._normalize_project_key(key)
            normalized_projects[normalized_key] = value if isinstance(value, dict) else {}

        for key, value in normalized_projects.items():
            literal_key = key.replace("'", "''")
            lines.append(f"[projects.'{literal_key}']")
            for item_key, item_value in value.items():
                if isinstance(item_value, dict):
                    continue
                lines.append(f"{item_key} = {self._format_toml_scalar(item_value)}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _write_codex_config(self, data: Dict[str, Any]):
        data_to_dump = dict(data)
        projects = data_to_dump.pop('projects', None)

        text = toml.dumps(data_to_dump).rstrip()
        if projects:
            projects_text = self._render_projects_section(projects)
            text = f"{text}\n\n{projects_text}" if text else projects_text
        text = (text.rstrip() + "\n") if text else ""

        with open(self.codex_config_path, 'w', encoding='utf-8') as f:
            f.write(text)

    def sync_codex_config_to_wsl_for_apply(self, provider_name: str, provider: Dict[str, Any]):
        if not self.wsl_home:
            return

        wsl_target = f"{self.wsl_home}/.codex/config.toml"
        wsl_data = self._read_wsl_toml(wsl_target)
        if 'model_providers' not in wsl_data:
            wsl_data['model_providers'] = {}

        existing_provider = wsl_data['model_providers'].get(provider_name, {})
        wsl_data['model_providers'][provider_name] = self._build_codex_provider_entry(
            provider_name,
            provider,
            existing_provider,
        )
        self._apply_codex_runtime_provider(wsl_data, provider_name, provider)
        self._write_wsl_toml(wsl_target, wsl_data)

    def sync_codex_auth_to_wsl(self, api_key: str):
        if not self.wsl_home:
            return

        wsl_target = f"{self.wsl_home}/.codex/auth.json"
        data = self._read_wsl_json(wsl_target)
        if api_key:
            data['OPENAI_API_KEY'] = api_key
        else:
            data.pop('OPENAI_API_KEY', None)
        data.pop('api_key', None)
        self._write_wsl_json(wsl_target, data)

    def _delayed_load(self):
        """延迟加载配置，避免阻塞 UI"""
        try:
            self.set_status("加载配置...")
            self.load_configs()
            self.set_status("加载档案...")
            self.load_profiles()
            self.set_status("就绪")
        except Exception as e:
            print(f"加载配置失败: {e}")
            self.set_status(f"加载失败: {e}", "error")

    def reload_all_configs(self):
        """同时刷新系统配置与工具内部供应商列表"""
        self.load_configs()
        self.load_profiles()

    def setup_ui(self):
        """设置用户界面"""
        self._setup_theme()

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # 顶部标题区
        header = ttk.Frame(self.root, style='Header.TFrame', padding=(22, 18, 22, 12))
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="ccPivot", style='Title.TLabel')
        title.grid(row=0, column=0, sticky='w')
        subtitle = ttk.Label(
            header,
            text="统一管理 Codex / Claude 供应商配置，并按需同步 Windows 与 WSL",
            style='Muted.TLabel',
        )
        subtitle.grid(row=1, column=0, sticky='w', pady=(4, 0))

        ttk.Button(header, text="刷新配置", command=self.reload_all_configs).grid(row=0, column=1, rowspan=2, sticky='e')

        # 创建 Notebook (标签页)
        notebook = ttk.Notebook(self.root)
        notebook.grid(row=1, column=0, sticky='nsew', padx=18, pady=(0, 12))

        # Codex 配置标签页
        codex_frame = ttk.Frame(notebook)
        notebook.add(codex_frame, text='Codex 配置')
        self.setup_codex_tab(codex_frame)

        # Claude 配置标签页
        claude_frame = ttk.Frame(notebook)
        notebook.add(claude_frame, text='Claude 配置')
        self.setup_claude_tab(claude_frame)

        # 状态栏（固定在底部）
        status_bar = ttk.Frame(self.root, style='Status.TFrame', padding=(18, 0, 18, 10))
        status_bar.grid(row=2, column=0, sticky='ew')
        status_bar.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_bar, text="就绪", anchor=tk.W, style='Status.TLabel')
        self.status_label.grid(row=0, column=0, sticky='ew')

    def _set_app_icon(self):
        """Set window/taskbar icon, works both in dev and PyInstaller bundle."""
        try:
            if getattr(sys, 'frozen', False):
                import os as _os
                base = _os.path.join(sys._MEIPASS, '')
            else:
                base = str(Path(__file__).parent) + '\\'
            # iconbitmap for Windows title bar (most reliable)
            self.root.iconbitmap(base + 'ccPivot.ico')
            # iconphoto for taskbar
            img = tk.PhotoImage(file=base + 'ccPivot.png')
            self.root.iconphoto(True, img)
            self._icon_img = img
        except Exception:
            pass

    def _setup_theme(self):
        style = ttk.Style()
        if not self.theme_available:
            try:
                style.theme_use('clam')
            except tk.TclError:
                pass

        self.root.configure(bg='#f6f8fb')
        font_family = 'Microsoft YaHei UI'
        self.root.option_add('*Font', (font_family, 10))

        style.configure('Header.TFrame', background='#f6f8fb')
        style.configure('Status.TFrame', background='#f6f8fb')
        style.configure('Title.TLabel', background='#f6f8fb', foreground='#1f2937', font=(font_family, 18, 'bold'))
        style.configure('SectionTitle.TLabel', foreground='#334155', font=(font_family, 11, 'bold'))
        style.configure('Muted.TLabel', background='#f6f8fb', foreground='#64748b')
        style.configure('Status.TLabel', background='#f6f8fb', foreground='#475569')
        style.configure('Applied.TLabel', foreground='#047857')
        style.configure('Danger.TButton', foreground='#b91c1c')
        style.configure('TLabelframe', borderwidth=1, relief='solid')
        style.configure('TLabelframe.Label', foreground='#334155', font=(font_family, 10, 'bold'))
        style.configure('TNotebook', background='#f6f8fb', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(16, 8))

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

    def _is_codex_runtime_provider_alias(self, provider_name: str) -> bool:
        return provider_name == self.codex_runtime_provider_alias

    def _build_codex_provider_entry(
        self,
        provider_name: str,
        provider_config: Dict[str, Any],
        existing_provider: Optional[Dict[str, Any]] = None,
        entry_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        provider_entry = {
            'name': entry_name or provider_config.get('name', provider_name),
            'base_url': provider_config.get('base_url', ''),
            'model': provider_config.get('model', ''),
            'wire_api': 'responses',
            'requires_openai_auth': True,
        }
        if isinstance(existing_provider, dict):
            if 'wire_api' in existing_provider:
                provider_entry['wire_api'] = existing_provider['wire_api']
            if 'requires_openai_auth' in existing_provider:
                provider_entry['requires_openai_auth'] = existing_provider['requires_openai_auth']
        return provider_entry

    def _match_codex_active_provider_from_runtime(
        self,
        runtime_config: Dict[str, Any],
        top_level_model: str,
    ) -> Optional[str]:
        if not isinstance(runtime_config, dict):
            return None

        runtime_name = (runtime_config.get('name') or '').strip()
        if runtime_name in self.codex_providers:
            return runtime_name

        runtime_base_url = (runtime_config.get('base_url') or '').strip()
        runtime_model = (runtime_config.get('model') or top_level_model or '').strip()
        for name, provider in self.codex_providers.items():
            if (
                (provider.get('base_url') or '').strip() == runtime_base_url
                and (provider.get('model') or '').strip() == runtime_model
            ):
                return name
        return None

    def _detect_codex_active_provider_from_config(self, data: Dict[str, Any]) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        current_provider = data.get('model_provider', '')
        if not current_provider:
            return None
        top_level_model = data.get('model', '') if isinstance(data.get('model', ''), str) else ''
        if current_provider == self.codex_runtime_provider_alias:
            runtime_config = (data.get('model_providers') or {}).get(self.codex_runtime_provider_alias, {})
            return self._match_codex_active_provider_from_runtime(runtime_config, top_level_model)
        return current_provider if isinstance(current_provider, str) else None

    def _detect_codex_active_provider_windows(self) -> Optional[str]:
        try:
            if not self.codex_config_path.exists():
                return None
            data = toml.load(self.codex_config_path)
            return self._detect_codex_active_provider_from_config(data)
        except Exception as e:
            print(f"检测 Windows 侧 Codex 供应商失败: {e}")
            return None

    def _detect_codex_active_provider_wsl(self) -> Optional[str]:
        if not self.wsl_home:
            return None
        try:
            data = self._read_wsl_toml(f"{self.wsl_home}/.codex/config.toml")
            if not data:
                return None
            return self._detect_codex_active_provider_from_config(data)
        except Exception as e:
            print(f"检测 WSL 侧 Codex 供应商失败: {e}")
            return None

    def _apply_codex_runtime_provider(
        self,
        data: Dict[str, Any],
        provider_name: str,
        provider: Dict[str, Any],
    ):
        if 'model_providers' not in data:
            data['model_providers'] = {}

        model_providers = data['model_providers']
        model_providers[self.codex_runtime_provider_alias] = self._build_codex_provider_entry(
            self.codex_runtime_provider_alias,
            provider,
            model_providers.get(self.codex_runtime_provider_alias, {}),
            entry_name=provider_name,
        )
        data['model_provider'] = self.codex_runtime_provider_alias

        if provider.get('base_url'):
            data['base_url'] = provider['base_url']
        else:
            data.pop('base_url', None)
        if provider.get('model'):
            data['model'] = provider['model']
        else:
            data.pop('model', None)

    def _clear_codex_runtime_provider(self, data: Dict[str, Any]):
        model_providers = data.get('model_providers')
        if isinstance(model_providers, dict):
            model_providers.pop(self.codex_runtime_provider_alias, None)
            if not model_providers:
                data.pop('model_providers', None)

        if data.get('model_provider') == self.codex_runtime_provider_alias:
            data.pop('model_provider', None)
            data.pop('base_url', None)
            data.pop('model', None)

    def _load_codex_providers_from_toml(self):
        """从 config.toml 读取所有 [model_providers.xxx] 定义"""
        if not self.codex_config_path.exists():
            return

        # 检查文件大小，防止加载损坏的巨大文件
        file_size = self.codex_config_path.stat().st_size
        if file_size > 1024 * 1024:  # 超过1MB
            print(f"警告: config.toml 文件异常大 ({file_size} 字节)，跳过加载")
            self.set_status(f"config.toml 文件异常 ({file_size // 1024}KB)，已跳过", "error")
            return

        try:
            data = toml.load(self.codex_config_path)

            # 读取顶层的 model（作为默认值）
            top_level_model = data.get('model', '')

            # 读取 model_providers 段落
            if 'model_providers' in data:
                for provider_name, provider_config in data['model_providers'].items():
                    if self._is_codex_runtime_provider_alias(provider_name):
                        continue

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
            if current_provider == self.codex_runtime_provider_alias:
                runtime_config = (data.get('model_providers') or {}).get(self.codex_runtime_provider_alias, {})
                self.codex_active_provider = self._match_codex_active_provider_from_runtime(runtime_config, top_level_model)
            elif current_provider and current_provider in self.codex_providers:
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
        self.codex_selected_provider = None
        self._load_codex_providers_from_toml()

        # Claude 配置
        self.claude_profiles = {}
        self.claude_active_profile = None
        self.claude_selected_profile = None

        if self.profiles_path.exists():
            try:
                with open(self.profiles_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                version = int(data.get('version', 1))
                if version >= 2:
                    codex = data.get('codex', {}) or {}
                    claude = data.get('claude', {}) or {}

                    # 从 providers.json 中补充 API key 到已加载的供应商
                    codex_saved_providers = (
                        codex.get('providers')
                        if isinstance(codex.get('providers'), dict)
                        else codex.get('profiles', {})
                    ) or {}
                    for name, p in codex_saved_providers.items():
                        if self._is_codex_runtime_provider_alias(name):
                            continue
                        if name in self.codex_providers:
                            # 供应商已从 config.toml 加载，只补充 API key
                            if p and p.get('api_key'):
                                self.codex_providers[name]['api_key'] = p['api_key']
                        else:
                            # 供应商不在 config.toml 中，从 providers.json 加载（向后兼容）
                            self.codex_providers[name] = self._normalize_codex_provider(p or {})

                    for name, p in (claude.get('profiles', {}) or {}).items():
                        self.claude_profiles[name] = self._normalize_claude_profile(p or {})

                    stored_active = codex.get('last_active')
                    if not self.codex_active_provider and stored_active in self.codex_providers:
                        self.codex_active_provider = stored_active

                    stored_selected = codex.get('last_selected')
                    if stored_selected in self.codex_providers:
                        self.codex_selected_provider = stored_selected
                    elif stored_active in self.codex_providers:
                        # 兼容旧版本：last_active 过去同时承担"当前选中项"的含义
                        self.codex_selected_provider = stored_active
                    stored_claude_active = claude.get('last_active')
                    if stored_claude_active in self.claude_profiles:
                        self.claude_active_profile = stored_claude_active
                    stored_claude_selected = claude.get('last_selected')
                    if stored_claude_selected in self.claude_profiles:
                        self.claude_selected_profile = stored_claude_selected
                    elif stored_claude_active in self.claude_profiles:
                        self.claude_selected_profile = stored_claude_active
                else:
                    # v1 -> v2
                    raw_profiles = data.get('profiles', {}) or {}
                    last_active = data.get('last_active')
                    for name, p in raw_profiles.items():
                        if self._is_codex_runtime_provider_alias(name):
                            continue
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
                        self.codex_selected_provider = last_active
                    if last_active in self.claude_profiles:
                        self.claude_active_profile = last_active
                        self.claude_selected_profile = last_active
            except Exception as e:
                self.set_status(f'加载供应商失败: {e}', 'error')

        # 若为空则初始化默认
        if not self.codex_providers:
            self.codex_providers['默认'] = self._normalize_codex_provider(self._capture_current_codex_provider())
            self.codex_active_provider = '默认'
            self.codex_selected_provider = '默认'

        if not self.claude_profiles:
            self.claude_profiles['默认'] = self._normalize_claude_profile(self._capture_current_claude_profile())
            self.claude_active_profile = '默认'
            self.claude_selected_profile = '默认'

        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')

        self._refresh_profiles_ui()

        if self.codex_selected_provider in self.codex_providers:
            if hasattr(self, 'codex_provider_var'):
                self.codex_provider_var.set(self.codex_selected_provider)
            if hasattr(self, 'codex_provider_list_frame'):
                self._load_codex_provider_to_ui(self.codex_selected_provider)
        if self.claude_selected_profile in self.claude_profiles:
            if hasattr(self, 'claude_profile_var'):
                self.claude_profile_var.set(self.claude_selected_profile)
            if hasattr(self, 'claude_provider_list_frame'):
                self._load_claude_profile_to_ui(self.claude_selected_profile)

        self._update_codex_applied_label()

    def _persist_profiles(self):
        """保存 profiles 到磁盘（v3）"""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': 3,
            'codex': {
                'last_active': self.codex_active_provider,
                'last_selected': self.codex_selected_provider,
                'providers': {
                    name: provider
                    for name, provider in self.codex_providers.items()
                    if not self._is_codex_runtime_provider_alias(name)
                },
            },
            'claude': {
                'last_active': self.claude_active_profile,
                'last_selected': self.claude_selected_profile,
                'profiles': self.claude_profiles,
            },
        }
        with open(self.profiles_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _refresh_profiles_ui(self):
        codex_names = sorted(self.codex_providers.keys())
        if hasattr(self, 'codex_provider_list_frame'):
            self._rebuild_codex_provider_list()
        if codex_names and self.codex_selected_provider not in codex_names:
            if self.codex_active_provider in codex_names:
                self.codex_selected_provider = self.codex_active_provider
            else:
                self.codex_selected_provider = codex_names[0]

        claude_names = sorted(self.claude_profiles.keys())
        if hasattr(self, 'claude_provider_list_frame'):
            self._rebuild_claude_provider_list()
        if claude_names and self.claude_selected_profile not in claude_names:
            if self.claude_active_profile in claude_names:
                self.claude_selected_profile = self.claude_active_profile
            else:
                self.claude_selected_profile = claude_names[0]

        self._update_codex_applied_label()
        self._update_claude_applied_label()

    def _update_codex_applied_label(self):
        """刷新 Codex 状态卡片"""
        if not hasattr(self, 'codex_win_name_lbl'):
            return

        windows_name = self._detect_codex_active_provider_windows()
        if windows_name:
            self.codex_win_name_lbl.config(text=windows_name, fg='#1e293b')
            self.codex_win_status_lbl.config(text='已同步', fg='#047857')
        else:
            self.codex_win_name_lbl.config(text='—', fg='#94a3b8')
            self.codex_win_status_lbl.config(text='未应用', fg='#94a3b8')

        if not self.wsl_home:
            self.codex_wsl_name_lbl.config(text='—', fg='#94a3b8')
            self.codex_wsl_status_lbl.config(text='不可用', fg='#94a3b8')
        else:
            wsl_name = self._detect_codex_active_provider_wsl()
            if wsl_name:
                self.codex_wsl_name_lbl.config(text=wsl_name, fg='#1e293b')
                self.codex_wsl_status_lbl.config(text='已同步', fg='#047857')
            else:
                self.codex_wsl_name_lbl.config(text='—', fg='#94a3b8')
                self.codex_wsl_status_lbl.config(text='未应用', fg='#94a3b8')

        if windows_name and windows_name in self.codex_providers:
            self.codex_active_provider = windows_name

    def _update_claude_applied_label(self):
        """刷新 Claude 状态卡片"""
        if not hasattr(self, 'claude_win_name_lbl'):
            return

        win_result = self._detect_claude_active_profile_windows()
        if win_result is None:
            windows_name, windows_ok = None, False
        else:
            matched, has_env = win_result
            windows_name, windows_ok = (matched, True) if matched and has_env else (None, bool(has_env))

        if windows_ok and windows_name:
            self.claude_win_name_lbl.config(text=windows_name, fg='#1e293b')
            self.claude_win_status_lbl.config(text='已同步', fg='#047857')
        elif windows_ok:
            self.claude_win_name_lbl.config(text='—', fg='#94a3b8')
            self.claude_win_status_lbl.config(text='未匹配', fg='#94a3b8')
        else:
            self.claude_win_name_lbl.config(text='—', fg='#94a3b8')
            self.claude_win_status_lbl.config(text='未应用', fg='#94a3b8')

        if not self.wsl_home:
            self.claude_wsl_name_lbl.config(text='—', fg='#94a3b8')
            self.claude_wsl_status_lbl.config(text='不可用', fg='#94a3b8')
        else:
            wsl_result = self._detect_claude_active_profile_wsl()
            if wsl_result is None:
                wsl_name, wsl_ok = None, False
            else:
                matched, has_env = wsl_result
                wsl_name, wsl_ok = (matched, True) if matched and has_env else (None, bool(has_env))

            if wsl_ok and wsl_name:
                self.claude_wsl_name_lbl.config(text=wsl_name, fg='#1e293b')
                self.claude_wsl_status_lbl.config(text='已同步', fg='#047857')
            elif wsl_ok:
                self.claude_wsl_name_lbl.config(text='—', fg='#94a3b8')
                self.claude_wsl_status_lbl.config(text='未匹配', fg='#94a3b8')
            else:
                self.claude_wsl_name_lbl.config(text='—', fg='#94a3b8')
                self.claude_wsl_status_lbl.config(text='未应用', fg='#94a3b8')

        if windows_name and windows_name in self.claude_profiles:
            self.claude_active_profile = windows_name

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
            print(f"警告: 供应商 '{name}' 不存在于 codex_providers 中")
            return

        print(f"加载 Codex 供应商 '{name}': base_url={provider.get('base_url', '')}, model={provider.get('model', '')}, api_key={'***' if provider.get('api_key') else '(空)'}")

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
        self.codex_selected_provider = name
        self._load_codex_provider_to_ui(name)
        self._update_codex_applied_label()
        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商状态失败: {e}', 'error')

    def on_claude_profile_selected(self, _event=None):
        name = self.claude_profile_var.get().strip()
        if not name or name not in self.claude_profiles:
            return
        self.claude_selected_profile = name
        self._load_claude_profile_to_ui(name)
        self._update_claude_applied_label()
        self._highlight_claude_provider_list()
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
        if self._is_codex_runtime_provider_alias(name):
            messagebox.showerror('错误', f'供应商名称"{name}"为内部保留名称，请更换一个名称。')
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

        self.codex_selected_provider = name
        self._refresh_profiles_ui()
        self.codex_provider_var.set(name)
        self._load_codex_provider_to_ui(name)
        self._update_codex_applied_label()

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
        if self._is_codex_runtime_provider_alias(provider_name):
            messagebox.showerror('错误', f'供应商名称"{provider_name}"为内部保留名称，不能直接保存。')
            return

        # 从 UI 捕获配置
        provider_config = self._normalize_codex_provider(self._capture_current_codex_provider())

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
            data['model_providers'][provider_name] = self._build_codex_provider_entry(
                provider_name,
                provider_config,
                existing_provider,
            )

            # 4. 备份并保存
            if self.codex_config_path.exists():
                shutil.copy(self.codex_config_path, str(self.codex_config_path) + '.backup')
            self._write_codex_config(data)

            # 5. 同步到 WSL（只合并 provider 定义，不覆盖整个文件）
            if self.wsl_home:
                wsl_target = f"{self.wsl_home}/.codex/config.toml"
                wsl_data = self._read_wsl_toml(wsl_target)
                if 'model_providers' not in wsl_data:
                    wsl_data['model_providers'] = {}
                existing_wsl = wsl_data['model_providers'].get(provider_name, {})
                wsl_data['model_providers'][provider_name] = self._build_codex_provider_entry(
                    provider_name,
                    provider_config,
                    existing_wsl,
                )
                self._write_wsl_toml(wsl_target, wsl_data)

            # 6. 更新内存中的供应商列表
            self.codex_providers[provider_name] = provider_config
            self.codex_selected_provider = provider_name

            # 7. 保存到 providers.json
            self._persist_profiles()
            self._update_codex_applied_label()

            messagebox.showinfo('成功', f'供应商"{provider_name}"已保存到 config.toml。\n当前运行配置未切换，如需生效请点击"应用该供应商"。')
            self.set_status(f'已保存 Codex 供应商定义: {provider_name}')

        except Exception as e:
            messagebox.showerror('错误', f'保存供应商失败:\n{e}')
            self.set_status(f'保存供应商失败: {e}', 'error')


    def _update_codex_auth_basic(self, api_key: str):
        """更新 auth.json 中的 API key"""
        if self.codex_auth_path.exists():
            with open(self.codex_auth_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}
        else:
            data = {}

        if api_key:
            data['OPENAI_API_KEY'] = api_key
        else:
            data.pop('OPENAI_API_KEY', None)
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
        if self._is_codex_runtime_provider_alias(provider_name):
            messagebox.showerror('错误', '该内部运行供应商不能直接删除。')
            return

        if not messagebox.askyesno('确认删除', f'确定要删除供应商"{provider_name}"？\n这将从 config.toml 中移除该供应商定义。'):
            return

        try:
            # 1. 从 config.toml 删除
            if self.codex_config_path.exists():
                data = toml.load(self.codex_config_path)
                config_changed = False
                if 'model_providers' in data and provider_name in data['model_providers']:
                    del data['model_providers'][provider_name]
                    config_changed = True

                if self.codex_active_provider == provider_name:
                    runtime_exists = (
                        data.get('model_provider') == self.codex_runtime_provider_alias
                        or (
                            isinstance(data.get('model_providers'), dict)
                            and self.codex_runtime_provider_alias in data['model_providers']
                        )
                    )
                    self._clear_codex_runtime_provider(data)
                    config_changed = config_changed or runtime_exists

                if config_changed:
                    shutil.copy(self.codex_config_path, str(self.codex_config_path) + '.backup')
                    self._write_codex_config(data)

                    if self.wsl_home:
                        wsl_target = f"{self.wsl_home}/.codex/config.toml"
                        wsl_data = self._read_wsl_toml(wsl_target)
                        if 'model_providers' in wsl_data and provider_name in wsl_data['model_providers']:
                            del wsl_data['model_providers'][provider_name]
                            if not wsl_data['model_providers']:
                                wsl_data.pop('model_providers', None)
                        self._clear_codex_runtime_provider(wsl_data)
                        self._write_wsl_toml(wsl_target, wsl_data)

            # 2. 从内存删除
            if provider_name in self.codex_providers:
                del self.codex_providers[provider_name]

            # 3. 处理当前编辑项/已应用项
            if self.codex_selected_provider == provider_name:
                self.codex_selected_provider = None
            if self.codex_active_provider == provider_name:
                self.codex_active_provider = None

            self._refresh_profiles_ui()
            values = sorted(self.codex_providers.keys())
            if values:
                if self.codex_selected_provider not in self.codex_providers:
                    self.codex_selected_provider = values[0]
                self.codex_provider_var.set(self.codex_selected_provider)
                self._load_codex_provider_to_ui(self.codex_selected_provider)
            else:
                self.codex_provider_var.set('')

            self._persist_profiles()
            self._update_codex_applied_label()
            messagebox.showinfo('成功', f'供应商"{provider_name}"已删除')
            self.set_status(f'已删除 Codex 供应商: {provider_name}')

        except Exception as e:
            messagebox.showerror('错误', f'删除供应商失败:\n{e}')
            self.set_status(f'删除供应商失败: {e}', 'error')

    def _apply_codex_provider_to_windows(self, provider_name: str, provider: Dict[str, Any]):
        if self.codex_config_path.exists():
            data = toml.load(self.codex_config_path)
        else:
            self.codex_dir.mkdir(parents=True, exist_ok=True)
            data = {}

        if 'model_providers' not in data:
            data['model_providers'] = {}

        existing_provider = data['model_providers'].get(provider_name, {})
        data['model_providers'][provider_name] = self._build_codex_provider_entry(
            provider_name,
            provider,
            existing_provider,
        )

        self._apply_codex_runtime_provider(data, provider_name, provider)

        if self.codex_config_path.exists():
            shutil.copy(self.codex_config_path, str(self.codex_config_path) + '.backup')
        self._write_codex_config(data)

        self._update_codex_auth_basic(provider.get('api_key', ''))

    def _apply_codex_provider_to_wsl(self, provider_name: str, provider: Dict[str, Any]):
        if not self.wsl_home:
            return
        self.sync_codex_config_to_wsl_for_apply(provider_name, provider)
        self.sync_codex_auth_to_wsl(provider.get('api_key', ''))

    def switch_codex_provider(self):
        """切换 Codex 供应商（修改 model_provider 字段）"""
        provider_name = self.codex_provider_var.get().strip()
        if not provider_name or provider_name not in self.codex_providers:
            messagebox.showerror('错误', '请先选择一个 Codex 供应商。')
            return
        if self._is_codex_runtime_provider_alias(provider_name):
            messagebox.showerror('错误', '该内部运行供应商不能直接应用。')
            return

        if not messagebox.askyesno('确认切换', f'切换到 Codex 供应商"{provider_name}"？\n这会先保存当前输入，并使用固定运行别名以共享 Codex 会话列表。'):
            return

        provider = self._normalize_codex_provider(self._capture_current_codex_provider())

        try:
            self._apply_codex_provider_to_windows(provider_name, provider)
            self._apply_codex_provider_to_wsl(provider_name, provider)

            self.codex_providers[provider_name] = provider
            self.codex_active_provider = provider_name
            self.codex_selected_provider = provider_name
            self._persist_profiles()
            self._load_codex_provider_to_ui(provider_name)
            self._update_codex_applied_label()

            messagebox.showinfo('成功', f'已保存并切换到 Codex 供应商"{provider_name}"，当前已启用共享会话模式。')
            self.set_status(f'已保存并切换到 Codex 供应商（共享会话）: {provider_name}')
            self.load_configs()  # 刷新 UI
            self._update_codex_applied_label()

        except Exception as e:
            messagebox.showerror('错误', f'切换供应商失败:\n{e}')
            self.set_status(f'切换供应商失败: {e}', 'error')

    def switch_codex_provider_windows_only(self):
        provider_name = self.codex_provider_var.get().strip()
        if not provider_name or provider_name not in self.codex_providers:
            messagebox.showerror('错误', '请先选择一个 Codex 供应商。')
            return
        if self._is_codex_runtime_provider_alias(provider_name):
            messagebox.showerror('错误', '该内部运行供应商不能直接应用。')
            return
        if not messagebox.askyesno('确认', f'仅将 Codex 供应商"{provider_name}"应用到 Windows 侧？\n此操作不会修改 WSL 配置。'):
            return

        provider = self._normalize_codex_provider(self._capture_current_codex_provider())
        try:
            self._apply_codex_provider_to_windows(provider_name, provider)
            self.codex_providers[provider_name] = provider
            self.codex_active_provider = provider_name
            self.codex_selected_provider = provider_name
            self._persist_profiles()
            self._load_codex_provider_to_ui(provider_name)
            self._update_codex_applied_label()

            messagebox.showinfo('成功', f'已仅将 Codex 供应商"{provider_name}"应用到 Windows 侧。')
            self.set_status(f'已仅应用到 Windows 侧 Codex 供应商: {provider_name}')
            self.load_configs()
            self._update_codex_applied_label()
        except Exception as e:
            messagebox.showerror('错误', f'应用到 Windows 失败:\n{e}')
            self.set_status(f'应用到 Windows 失败: {e}', 'error')

    def switch_codex_provider_wsl_only(self):
        provider_name = self.codex_provider_var.get().strip()
        if not provider_name or provider_name not in self.codex_providers:
            messagebox.showerror('错误', '请先选择一个 Codex 供应商。')
            return
        if self._is_codex_runtime_provider_alias(provider_name):
            messagebox.showerror('错误', '该内部运行供应商不能直接应用。')
            return
        if not self.wsl_home:
            messagebox.showwarning('提示', '未检测到 WSL 环境，无法仅应用到 WSL。')
            return
        if not messagebox.askyesno('确认', f'仅将 Codex 供应商"{provider_name}"应用到 WSL 侧？\n此操作不会修改 Windows 配置。'):
            return

        provider = self._normalize_codex_provider(self._capture_current_codex_provider())
        try:
            self.codex_providers[provider_name] = provider
            self._persist_profiles()
            self._apply_codex_provider_to_wsl(provider_name, provider)
            self._update_codex_applied_label()

            messagebox.showinfo('成功', f'已仅将 Codex 供应商"{provider_name}"应用到 WSL 侧。')
            self.set_status(f'已仅应用到 WSL 侧 Codex 供应商: {provider_name}')
        except Exception as e:
            messagebox.showerror('错误', f'应用到 WSL 失败:\n{e}')
            self.set_status(f'应用到 WSL 失败: {e}', 'error')

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
        self.claude_selected_profile = name
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
            messagebox.showerror('错误', '请先选择一个 Claude 供应商，或点击"新增"。')
            return

        profile = self._normalize_claude_profile(self._capture_current_claude_profile())
        self.claude_profiles[name] = profile
        self.claude_active_profile = name
        self.claude_selected_profile = name
        try:
            self._persist_profiles()
            self.set_status(f'已保存 Claude 供应商: {name}')
            messagebox.showinfo('成功', f'Claude 供应商"{name}"已保存。')
        except Exception as e:
            self.set_status(f'保存供应商失败: {e}', 'error')
            messagebox.showerror('错误', f'保存 Claude 供应商失败:\n{e}')

    def delete_claude_profile(self):
        name = self.claude_profile_var.get().strip()
        if not name or name not in self.claude_profiles:
            return
        if not messagebox.askyesno('确认删除', f'确定要删除 Claude 供应商"{name}"吗？'):
            return

        del self.claude_profiles[name]
        if self.claude_active_profile == name:
            self.claude_active_profile = None
        if self.claude_selected_profile == name:
            self.claude_selected_profile = None

        self._refresh_profiles_ui()
        values = sorted(self.claude_profiles.keys())
        if values:
            self.claude_selected_profile = values[0]
            self.claude_profile_var.set(self.claude_selected_profile)
            self._load_claude_profile_to_ui(self.claude_selected_profile)
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
        if not messagebox.askyesno('确认应用', f'将当前输入保存到 Claude 供应商"{name}"并写入系统配置文件？'):
            return

        profile = self._normalize_claude_profile(self._capture_current_claude_profile())

        try:
            self.claude_profiles[name] = profile
            self.claude_active_profile = name
            self.claude_selected_profile = name
            self._persist_profiles()
            self._write_claude_settings(
                api_key=(profile.get('api_key') or '').strip(),
                base_url=(profile.get('base_url') or '').strip(),
                model=(profile.get('model') or '').strip(),
            )
            self._update_claude_applied_label()
            self.set_status(f'已应用 Claude 供应商: {name}')
            messagebox.showinfo('成功', f'Claude 供应商"{name}"已保存并应用，且已同步到 WSL（如可用）。')
        except Exception as e:
            self.set_status(f'应用 Claude 供应商失败: {e}', 'error')
            messagebox.showerror('错误', f'应用 Claude 供应商失败:\n{e}')

    def apply_claude_profile_windows_only(self):
        name = self.claude_profile_var.get().strip()
        if not name or name not in self.claude_profiles:
            messagebox.showerror('错误', '请先选择一个 Claude 供应商。')
            return
        if not messagebox.askyesno('确认', f'仅将 Claude 供应商"{name}"应用到 Windows 侧？\n此操作不会修改 WSL 配置。'):
            return

        profile = self._normalize_claude_profile(self._capture_current_claude_profile())
        try:
            self.claude_profiles[name] = profile
            self.claude_active_profile = name
            self.claude_selected_profile = name
            self._persist_profiles()
            self._apply_claude_profile_to_windows(
                api_key=(profile.get('api_key') or '').strip(),
                base_url=(profile.get('base_url') or '').strip(),
                model=(profile.get('model') or '').strip(),
            )
            self._update_claude_applied_label()
            self.set_status(f'已仅应用到 Windows 侧 Claude 供应商: {name}')
            messagebox.showinfo('成功', f'已仅将 Claude 供应商"{name}"应用到 Windows 侧。')
        except Exception as e:
            self.set_status(f'应用到 Windows 失败: {e}', 'error')
            messagebox.showerror('错误', f'应用到 Windows 失败:\n{e}')

    def apply_claude_profile_wsl_only(self):
        name = self.claude_profile_var.get().strip()
        if not name or name not in self.claude_profiles:
            messagebox.showerror('错误', '请先选择一个 Claude 供应商。')
            return
        if not self.wsl_home:
            messagebox.showwarning('提示', '未检测到 WSL 环境，无法仅应用到 WSL。')
            return
        if not messagebox.askyesno('确认', f'仅将 Claude 供应商"{name}"应用到 WSL 侧？\n此操作不会修改 Windows 配置。'):
            return

        profile = self._normalize_claude_profile(self._capture_current_claude_profile())
        try:
            self.claude_profiles[name] = profile
            self._persist_profiles()
            self._apply_claude_profile_to_wsl(
                api_key=(profile.get('api_key') or '').strip(),
                base_url=(profile.get('base_url') or '').strip(),
                model=(profile.get('model') or '').strip(),
            )
            self._update_claude_applied_label()
            self.set_status(f'已仅应用到 WSL 侧 Claude 供应商: {name}')
            messagebox.showinfo('成功', f'已仅将 Claude 供应商"{name}"应用到 WSL 侧。')
        except Exception as e:
            self.set_status(f'应用到 WSL 失败: {e}', 'error')
            messagebox.showerror('错误', f'应用到 WSL 失败:\n{e}')

    def setup_codex_tab(self, parent):
        """设置 Codex 配置标签页 — 左右分栏布局"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        main_frame = ttk.Frame(parent, padding=(16, 14, 16, 14))
        main_frame.grid(row=0, column=0, sticky='nsew')
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # === 左侧面板 — 供应商列表 ===
        left_panel = ttk.Frame(main_frame, width=210)
        left_panel.grid(row=0, column=0, sticky='ns', padx=(0, 16))
        left_panel.grid_propagate(False)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)

        title_row = ttk.Frame(left_panel)
        title_row.grid(row=0, column=0, sticky='ew')
        ttk.Label(title_row, text="供应商", style='SectionTitle.TLabel').pack(side='left')
        self.codex_provider_count_var = tk.StringVar(value='0 个')
        ttk.Label(title_row, textvariable=self.codex_provider_count_var, foreground='#94a3b8').pack(side='right')

        # Canvas + Scrollbar 列表容器
        list_container = ttk.Frame(left_panel)
        list_container.grid(row=1, column=0, sticky='nsew', pady=(8, 8))
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)

        self.codex_provider_canvas = tk.Canvas(list_container, bg='#ffffff', highlightthickness=1,
                                               highlightbackground='#d1d5db', width=188)
        self.codex_provider_canvas.grid(row=0, column=0, sticky='nsew')

        codex_scrollbar = ttk.Scrollbar(list_container, orient='vertical',
                                        command=self.codex_provider_canvas.yview)
        codex_scrollbar.grid(row=0, column=1, sticky='ns')
        self.codex_provider_canvas.configure(yscrollcommand=codex_scrollbar.set)
        self._codex_scrollbar = codex_scrollbar

        self.codex_provider_list_frame = tk.Frame(self.codex_provider_canvas, bg='#ffffff')
        self._codex_canvas_window = self.codex_provider_canvas.create_window(
            (0, 0), window=self.codex_provider_list_frame, anchor='nw')

        def _update_codex_scroll_vis():
            try:
                fh = self.codex_provider_list_frame.winfo_height()
                ch = self.codex_provider_canvas.winfo_height()
                if fh <= ch:
                    self._codex_scrollbar.grid_remove()
                    self.codex_provider_canvas.yview_moveto(0)
                else:
                    self._codex_scrollbar.grid()
            except Exception:
                pass

        def _on_codex_list_configure(event):
            self.codex_provider_canvas.configure(
                scrollregion=(0, 0, event.width, event.height))
            self.root.after_idle(_update_codex_scroll_vis)

        def _on_codex_canvas_configure(event):
            self.codex_provider_canvas.itemconfig(self._codex_canvas_window, width=event.width)
            self.root.after_idle(_update_codex_scroll_vis)

        self.codex_provider_list_frame.bind('<Configure>', _on_codex_list_configure)
        self.codex_provider_canvas.bind('<Configure>', _on_codex_canvas_configure)

        def _on_codex_mousewheel(event):
            self.codex_provider_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        def _bind_codex_wheel(_e):
            self.codex_provider_canvas.bind_all('<MouseWheel>', _on_codex_mousewheel)

        def _unbind_codex_wheel(_e):
            self.codex_provider_canvas.unbind_all('<MouseWheel>')

        self.codex_provider_canvas.bind('<Enter>', _bind_codex_wheel)
        self.codex_provider_canvas.bind('<Leave>', _unbind_codex_wheel)

        self.codex_list_items = {}

        btn_row = ttk.Frame(left_panel)
        btn_row.grid(row=2, column=0, sticky='ew')
        ttk.Button(btn_row, text="＋ 新增", command=self.create_codex_provider).pack(side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(btn_row, text="删除", command=self.delete_codex_provider, style='Danger.TButton').pack(side='left', fill='x', expand=True, padx=(4, 0))

        # === 右侧面板 ===
        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=0, column=1, sticky='nsew')
        right_panel.columnconfigure(0, weight=1)

        # 连接配置区
        form_frame = ttk.LabelFrame(right_panel, text="连接配置", padding=(14, 12))
        form_frame.pack(fill='x')
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Base URL").grid(row=0, column=0, sticky='w', pady=7, padx=(0, 14))
        self.codex_baseurl = ttk.Entry(form_frame)
        self.codex_baseurl.grid(row=0, column=1, sticky='we', pady=7)

        ttk.Label(form_frame, text="Model").grid(row=1, column=0, sticky='w', pady=7, padx=(0, 14))
        self.codex_model = ttk.Entry(form_frame)
        self.codex_model.grid(row=1, column=1, sticky='we', pady=7)

        ttk.Label(form_frame, text="API Key").grid(row=2, column=0, sticky='w', pady=7, padx=(0, 14))
        self.codex_apikey = ttk.Entry(form_frame, show="*")
        self.codex_apikey.grid(row=2, column=1, sticky='we', pady=7)

        show_key_var = tk.BooleanVar(value=False)

        def toggle_key():
            self.codex_apikey.config(show="" if show_key_var.get() else "*")

        ttk.Checkbutton(form_frame, text="显示", variable=show_key_var, command=toggle_key).grid(
            row=2, column=2, sticky='w', padx=(12, 0))

        form_actions = ttk.Frame(form_frame)
        form_actions.grid(row=3, column=0, columnspan=3, sticky='w', pady=(12, 0))

        def show_codex_help():
            help_text = """配置项说明：
• Base URL — 保存到 ~/.codex/config.toml 的 model_providers.<供应商>.base_url
• Model — 保存到 ~/.codex/config.toml 的 model_providers.<供应商>.model
• API Key — 保存到工具内部供应商列表；"同步"后才写入 ~/.codex/auth.json

"两端同步"：先保存当前输入，再以固定运行别名改写 config.toml / auth.json，同步到 WSL
"仅 Windows"：只修改 Windows 侧，不动 WSL
"仅 WSL"：只修改 WSL 侧，不动 Windows
新建供应商默认包含 wire_api="responses" 与 requires_openai_auth=true。"""
            messagebox.showinfo("Codex 帮助", help_text)

        ttk.Button(form_actions, text="? 帮助", width=7, command=show_codex_help).pack(side='left', padx=(0, 8))
        ttk.Button(form_actions, text="保存", command=self.save_codex_provider).pack(side='left')
        self.codex_probe_btn = ttk.Button(form_actions, text="探针", command=self.probe_codex_provider)
        self.codex_probe_btn.pack(side='left', padx=(8, 0))

        ttk.Separator(right_panel, orient='horizontal').pack(fill='x', pady=(14, 14))

        # 同步操作区
        sync_frame = ttk.LabelFrame(right_panel, text="同步到配置文件", padding=(14, 12))
        sync_frame.pack(fill='x')

        sync_buttons = ttk.Frame(sync_frame)
        sync_buttons.pack(fill='x')
        ttk.Button(sync_buttons, text="两端同步", command=self.switch_codex_provider).pack(side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(sync_buttons, text="仅 Windows", command=self.switch_codex_provider_windows_only).pack(side='left', fill='x', expand=True, padx=(4, 4))
        ttk.Button(sync_buttons, text="仅 WSL", command=self.switch_codex_provider_wsl_only).pack(side='left', fill='x', expand=True, padx=(4, 0))

        # 状态卡片
        font_family = 'Microsoft YaHei UI'
        status_container = tk.Frame(sync_frame, bg='#f8fafc')
        status_container.pack(fill='x', pady=(10, 0))

        win_card = tk.Frame(status_container, bg='#ffffff', highlightthickness=1, highlightbackground='#e2e8f0')
        win_card.pack(side='left', fill='x', expand=True, padx=(0, 4))
        tk.Label(win_card, text='Windows', bg='#f8fafc', fg='#64748b',
                 font=(font_family, 9)).pack(fill='x', padx=10, pady=(6, 0))
        self.codex_win_name_lbl = tk.Label(win_card, text='—', bg='#ffffff', fg='#94a3b8',
                                           font=(font_family, 12, 'bold'))
        self.codex_win_name_lbl.pack(padx=10, pady=(2, 0))
        self.codex_win_status_lbl = tk.Label(win_card, text='未应用', bg='#ffffff', fg='#94a3b8',
                                             font=(font_family, 9))
        self.codex_win_status_lbl.pack(padx=10, pady=(0, 6))

        wsl_card = tk.Frame(status_container, bg='#ffffff', highlightthickness=1, highlightbackground='#e2e8f0')
        wsl_card.pack(side='left', fill='x', expand=True, padx=(4, 0))
        tk.Label(wsl_card, text='WSL', bg='#f8fafc', fg='#64748b',
                 font=(font_family, 9)).pack(fill='x', padx=10, pady=(6, 0))
        self.codex_wsl_name_lbl = tk.Label(wsl_card, text='—', bg='#ffffff', fg='#94a3b8',
                                           font=(font_family, 12, 'bold'))
        self.codex_wsl_name_lbl.pack(padx=10, pady=(2, 0))
        self.codex_wsl_status_lbl = tk.Label(wsl_card, text='未应用', bg='#ffffff', fg='#94a3b8',
                                             font=(font_family, 9))
        self.codex_wsl_status_lbl.pack(padx=10, pady=(0, 6))

        self.codex_provider_var = tk.StringVar()

    def _rebuild_codex_provider_list(self):
        """重建 Codex 供应商左侧列表（结构变化时调用）"""
        for widget in self.codex_provider_list_frame.winfo_children():
            widget.destroy()
        self.codex_list_items.clear()

        names = sorted(self.codex_providers.keys())
        self.codex_provider_count_var.set(f'{len(names)} 个')

        if not names:
            tk.Label(self.codex_provider_list_frame, text='(空)', bg='#ffffff', fg='#94a3b8',
                     font=('Microsoft YaHei UI', 10)).pack(pady=24)
            return

        font_family = 'Microsoft YaHei UI'

        for name in names:
            if self._is_codex_runtime_provider_alias(name):
                continue

            is_selected = (name == self.codex_selected_provider)
            is_applied = (name in self.codex_providers
                          and name == self.codex_active_provider)
            bg = '#e0f2fe' if is_selected else '#ffffff'

            row = tk.Frame(self.codex_provider_list_frame, bg=bg, cursor='hand2')
            row.pack(fill='x')

            inner = tk.Frame(row, bg=bg)
            inner.pack(fill='x', padx=12, pady=7)

            name_lbl = tk.Label(inner, text=name, bg=bg, anchor='w',
                                fg='#0369a1' if is_selected else '#1e293b',
                                font=(font_family, 10, 'bold' if is_selected else 'normal'))
            name_lbl.pack(side='left')

            arrow_lbl = tk.Label(inner, text='▶', bg=bg, fg='#0369a1',
                                 font=(font_family, 8))
            applied_lbl = tk.Label(inner, text='已应用', bg='#dcfce7', fg='#047857',
                                   font=(font_family, 8))

            if is_selected:
                arrow_lbl.pack(side='right', padx=(4, 0))
            if is_applied:
                applied_lbl.pack(side='right', padx=(4, 0))

            # separator
            if not is_selected:
                tk.Frame(self.codex_provider_list_frame, bg='#f1f5f9', height=1).pack(fill='x')

            for w in (row, inner, name_lbl):
                w.bind('<Button-1>', lambda _e, n=name: self._on_codex_list_item_click(n))

            self.codex_list_items[name] = {
                'row': row, 'inner': inner, 'name_lbl': name_lbl,
                'arrow_lbl': arrow_lbl, 'applied_lbl': applied_lbl,
            }

    def _highlight_codex_provider_list(self):
        """仅更新列表项高亮状态，不重建 widget"""
        for name, w in self.codex_list_items.items():
            is_selected = (name == self.codex_selected_provider)
            is_applied = (name in self.codex_providers
                          and name == self.codex_active_provider)
            bg = '#e0f2fe' if is_selected else '#ffffff'

            w['row'].configure(bg=bg)
            w['inner'].configure(bg=bg)
            w['name_lbl'].configure(bg=bg, fg='#0369a1' if is_selected else '#1e293b',
                                    font=('Microsoft YaHei UI', 10,
                                          'bold' if is_selected else 'normal'))
            w['arrow_lbl'].configure(bg=bg)

            if is_selected:
                w['arrow_lbl'].pack(side='right', padx=(4, 0))
            else:
                w['arrow_lbl'].pack_forget()

            if is_applied:
                w['applied_lbl'].pack(side='right', padx=(4, 0))
            else:
                w['applied_lbl'].pack_forget()

    def _on_codex_list_item_click(self, name: str):
        """点击左侧列表项切换到对应供应商"""
        if name not in self.codex_providers:
            return
        self.codex_provider_var.set(name)
        self.codex_selected_provider = name
        self._load_codex_provider_to_ui(name)
        self._update_codex_applied_label()
        self._highlight_codex_provider_list()
        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商状态失败: {e}', 'error')

    def setup_claude_tab(self, parent):
        """设置 Claude 配置标签页 — 左右分栏布局"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        main_frame = ttk.Frame(parent, padding=(16, 14, 16, 14))
        main_frame.grid(row=0, column=0, sticky='nsew')
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # === 左侧面板 — 供应商列表 ===
        left_panel = ttk.Frame(main_frame, width=210)
        left_panel.grid(row=0, column=0, sticky='ns', padx=(0, 16))
        left_panel.grid_propagate(False)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)

        title_row = ttk.Frame(left_panel)
        title_row.grid(row=0, column=0, sticky='ew')
        ttk.Label(title_row, text="供应商", style='SectionTitle.TLabel').pack(side='left')
        self.claude_provider_count_var = tk.StringVar(value='0 个')
        ttk.Label(title_row, textvariable=self.claude_provider_count_var, foreground='#94a3b8').pack(side='right')

        # Canvas + Scrollbar 列表容器
        list_container = ttk.Frame(left_panel)
        list_container.grid(row=1, column=0, sticky='nsew', pady=(8, 8))
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)

        self.claude_provider_canvas = tk.Canvas(list_container, bg='#ffffff', highlightthickness=1,
                                                 highlightbackground='#d1d5db', width=188)
        self.claude_provider_canvas.grid(row=0, column=0, sticky='nsew')

        claude_scrollbar = ttk.Scrollbar(list_container, orient='vertical',
                                         command=self.claude_provider_canvas.yview)
        claude_scrollbar.grid(row=0, column=1, sticky='ns')
        self.claude_provider_canvas.configure(yscrollcommand=claude_scrollbar.set)
        self._claude_scrollbar = claude_scrollbar

        self.claude_provider_list_frame = tk.Frame(self.claude_provider_canvas, bg='#ffffff')
        self._claude_canvas_window = self.claude_provider_canvas.create_window(
            (0, 0), window=self.claude_provider_list_frame, anchor='nw')

        def _update_claude_scroll_vis():
            try:
                fh = self.claude_provider_list_frame.winfo_height()
                ch = self.claude_provider_canvas.winfo_height()
                if fh <= ch:
                    self._claude_scrollbar.grid_remove()
                    self.claude_provider_canvas.yview_moveto(0)
                else:
                    self._claude_scrollbar.grid()
            except Exception:
                pass

        def _on_claude_list_configure(event):
            self.claude_provider_canvas.configure(
                scrollregion=(0, 0, event.width, event.height))
            self.root.after_idle(_update_claude_scroll_vis)

        def _on_claude_canvas_configure(event):
            self.claude_provider_canvas.itemconfig(self._claude_canvas_window, width=event.width)
            self.root.after_idle(_update_claude_scroll_vis)

        self.claude_provider_list_frame.bind('<Configure>', _on_claude_list_configure)
        self.claude_provider_canvas.bind('<Configure>', _on_claude_canvas_configure)

        def _on_claude_mousewheel(event):
            self.claude_provider_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        def _bind_claude_wheel(_e):
            self.claude_provider_canvas.bind_all('<MouseWheel>', _on_claude_mousewheel)

        def _unbind_claude_wheel(_e):
            self.claude_provider_canvas.unbind_all('<MouseWheel>')

        self.claude_provider_canvas.bind('<Enter>', _bind_claude_wheel)
        self.claude_provider_canvas.bind('<Leave>', _unbind_claude_wheel)

        self.claude_list_items = {}

        btn_row = ttk.Frame(left_panel)
        btn_row.grid(row=2, column=0, sticky='ew')
        ttk.Button(btn_row, text="＋ 新增", command=self.create_claude_profile).pack(side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(btn_row, text="删除", command=self.delete_claude_profile, style='Danger.TButton').pack(side='left', fill='x', expand=True, padx=(4, 0))

        # === 右侧面板 ===
        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=0, column=1, sticky='nsew')
        right_panel.columnconfigure(0, weight=1)

        # 连接配置区
        form_frame = ttk.LabelFrame(right_panel, text="连接配置", padding=(14, 12))
        form_frame.pack(fill='x')
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Base URL").grid(row=0, column=0, sticky='w', pady=7, padx=(0, 14))
        self.claude_baseurl = ttk.Entry(form_frame)
        self.claude_baseurl.grid(row=0, column=1, sticky='we', pady=7)

        ttk.Label(form_frame, text="Model").grid(row=1, column=0, sticky='w', pady=7, padx=(0, 14))
        self.claude_model = ttk.Entry(form_frame)
        self.claude_model.grid(row=1, column=1, sticky='we', pady=7)

        ttk.Label(form_frame, text="API Key").grid(row=2, column=0, sticky='w', pady=7, padx=(0, 14))
        self.claude_apikey = ttk.Entry(form_frame, show="*")
        self.claude_apikey.grid(row=2, column=1, sticky='we', pady=7)

        show_key_var = tk.BooleanVar(value=False)

        def toggle_key():
            self.claude_apikey.config(show="" if show_key_var.get() else "*")

        ttk.Checkbutton(form_frame, text="显示", variable=show_key_var, command=toggle_key).grid(
            row=2, column=2, sticky='w', padx=(12, 0))

        form_actions = ttk.Frame(form_frame)
        form_actions.grid(row=3, column=0, columnspan=3, sticky='w', pady=(12, 0))

        def show_claude_help():
            help_text = """配置方式：通过 ~/.claude/settings.json 文件配置 Claude

配置项说明：
• API Key — 存储在 env.ANTHROPIC_AUTH_TOKEN
• Base URL — 存储在 env.ANTHROPIC_BASE_URL（可选）
• Model — 存储在 env.ANTHROPIC_MODEL（可选）

"两端同步"：先保存当前输入，再写入 settings.json，同步到 WSL
"仅 Windows"：只修改 Windows 侧，不动 WSL
"仅 WSL"：只修改 WSL 侧，不动 Windows"""
            messagebox.showinfo("Claude 帮助", help_text)

        ttk.Button(form_actions, text="? 帮助", width=7, command=show_claude_help).pack(side='left', padx=(0, 8))
        ttk.Button(form_actions, text="保存", command=self.save_claude_profile).pack(side='left')
        self.claude_probe_btn = ttk.Button(form_actions, text="探针", command=self.probe_claude_profile)
        self.claude_probe_btn.pack(side='left', padx=(8, 0))

        ttk.Separator(right_panel, orient='horizontal').pack(fill='x', pady=(14, 14))

        # 同步操作区
        sync_frame = ttk.LabelFrame(right_panel, text="同步到配置文件", padding=(14, 12))
        sync_frame.pack(fill='x')

        sync_buttons = ttk.Frame(sync_frame)
        sync_buttons.pack(fill='x')
        ttk.Button(sync_buttons, text="两端同步", command=self.apply_claude_profile).pack(side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(sync_buttons, text="仅 Windows", command=self.apply_claude_profile_windows_only).pack(side='left', fill='x', expand=True, padx=(4, 4))
        ttk.Button(sync_buttons, text="仅 WSL", command=self.apply_claude_profile_wsl_only).pack(side='left', fill='x', expand=True, padx=(4, 0))

        # 状态卡片
        font_family = 'Microsoft YaHei UI'
        status_container = tk.Frame(sync_frame, bg='#f8fafc')
        status_container.pack(fill='x', pady=(10, 0))

        win_card = tk.Frame(status_container, bg='#ffffff', highlightthickness=1, highlightbackground='#e2e8f0')
        win_card.pack(side='left', fill='x', expand=True, padx=(0, 4))
        tk.Label(win_card, text='Windows', bg='#f8fafc', fg='#64748b',
                 font=(font_family, 9)).pack(fill='x', padx=10, pady=(6, 0))
        self.claude_win_name_lbl = tk.Label(win_card, text='—', bg='#ffffff', fg='#94a3b8',
                                            font=(font_family, 12, 'bold'))
        self.claude_win_name_lbl.pack(padx=10, pady=(2, 0))
        self.claude_win_status_lbl = tk.Label(win_card, text='未应用', bg='#ffffff', fg='#94a3b8',
                                              font=(font_family, 9))
        self.claude_win_status_lbl.pack(padx=10, pady=(0, 6))

        wsl_card = tk.Frame(status_container, bg='#ffffff', highlightthickness=1, highlightbackground='#e2e8f0')
        wsl_card.pack(side='left', fill='x', expand=True, padx=(4, 0))
        tk.Label(wsl_card, text='WSL', bg='#f8fafc', fg='#64748b',
                 font=(font_family, 9)).pack(fill='x', padx=10, pady=(6, 0))
        self.claude_wsl_name_lbl = tk.Label(wsl_card, text='—', bg='#ffffff', fg='#94a3b8',
                                            font=(font_family, 12, 'bold'))
        self.claude_wsl_name_lbl.pack(padx=10, pady=(2, 0))
        self.claude_wsl_status_lbl = tk.Label(wsl_card, text='未应用', bg='#ffffff', fg='#94a3b8',
                                              font=(font_family, 9))
        self.claude_wsl_status_lbl.pack(padx=10, pady=(0, 6))

        self.claude_profile_var = tk.StringVar()

    def _rebuild_claude_provider_list(self):
        """重建 Claude 供应商左侧列表（结构变化时调用）"""
        for widget in self.claude_provider_list_frame.winfo_children():
            widget.destroy()
        self.claude_list_items.clear()

        names = sorted(self.claude_profiles.keys())
        self.claude_provider_count_var.set(f'{len(names)} 个')

        if not names:
            tk.Label(self.claude_provider_list_frame, text='(空)', bg='#ffffff', fg='#94a3b8',
                     font=('Microsoft YaHei UI', 10)).pack(pady=24)
            return

        font_family = 'Microsoft YaHei UI'

        for name in names:
            is_selected = (name == self.claude_selected_profile)
            is_applied = (name == self.claude_active_profile)
            bg = '#e0f2fe' if is_selected else '#ffffff'

            row = tk.Frame(self.claude_provider_list_frame, bg=bg, cursor='hand2')
            row.pack(fill='x')

            inner = tk.Frame(row, bg=bg)
            inner.pack(fill='x', padx=12, pady=7)

            name_lbl = tk.Label(inner, text=name, bg=bg, anchor='w',
                                fg='#0369a1' if is_selected else '#1e293b',
                                font=(font_family, 10, 'bold' if is_selected else 'normal'))
            name_lbl.pack(side='left')

            arrow_lbl = tk.Label(inner, text='▶', bg=bg, fg='#0369a1',
                                 font=(font_family, 8))
            applied_lbl = tk.Label(inner, text='已应用', bg='#dcfce7', fg='#047857',
                                   font=(font_family, 8))

            if is_selected:
                arrow_lbl.pack(side='right', padx=(4, 0))
            if is_applied:
                applied_lbl.pack(side='right', padx=(4, 0))

            if not is_selected:
                tk.Frame(self.claude_provider_list_frame, bg='#f1f5f9', height=1).pack(fill='x')

            for w in (row, inner, name_lbl):
                w.bind('<Button-1>', lambda _e, n=name: self._on_claude_list_item_click(n))

            self.claude_list_items[name] = {
                'row': row, 'inner': inner, 'name_lbl': name_lbl,
                'arrow_lbl': arrow_lbl, 'applied_lbl': applied_lbl,
            }

    def _highlight_claude_provider_list(self):
        """仅更新列表项高亮状态，不重建 widget"""
        for name, w in self.claude_list_items.items():
            is_selected = (name == self.claude_selected_profile)
            is_applied = (name == self.claude_active_profile)
            bg = '#e0f2fe' if is_selected else '#ffffff'

            w['row'].configure(bg=bg)
            w['inner'].configure(bg=bg)
            w['name_lbl'].configure(bg=bg, fg='#0369a1' if is_selected else '#1e293b',
                                    font=('Microsoft YaHei UI', 10,
                                          'bold' if is_selected else 'normal'))
            w['arrow_lbl'].configure(bg=bg)

            if is_selected:
                w['arrow_lbl'].pack(side='right', padx=(4, 0))
            else:
                w['arrow_lbl'].pack_forget()

            if is_applied:
                w['applied_lbl'].pack(side='right', padx=(4, 0))
            else:
                w['applied_lbl'].pack_forget()

    def _on_claude_list_item_click(self, name: str):
        """点击左侧列表项切换到对应 Claude 供应商"""
        if name not in self.claude_profiles:
            return
        self.claude_profile_var.set(name)
        self.claude_selected_profile = name
        self._load_claude_profile_to_ui(name)
        self._update_claude_applied_label()
        self._highlight_claude_provider_list()
        try:
            self._persist_profiles()
        except Exception as e:
            self.set_status(f'保存供应商状态失败: {e}', 'error')

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

    def _apply_claude_profile_to_windows(self, api_key: str, base_url: str, model: str):
        data = self._read_json_file(self.claude_settings_path)
        data = self._merge_claude_env_into_settings(
            data,
            self._build_managed_claude_env(api_key, base_url, model),
        )
        self.claude_dir.mkdir(parents=True, exist_ok=True)
        if self.claude_settings_path.exists():
            shutil.copy(self.claude_settings_path, str(self.claude_settings_path) + '.backup')
        self._write_json_file(self.claude_settings_path, data)

    def _apply_claude_profile_to_wsl(self, api_key: str, base_url: str, model: str):
        if not self.wsl_home:
            return
        self.sync_claude_to_wsl(api_key=api_key, base_url=base_url, model=model)

    def _write_claude_settings(self, api_key: str, base_url: str, model: str):
        """写入 Claude settings.json（抛出异常，由上层决定是否弹窗）"""
        self._apply_claude_profile_to_windows(api_key, base_url, model)
        self._apply_claude_profile_to_wsl(api_key, base_url, model)

    def sync_claude_to_wsl(self, api_key: str, base_url: str, model: str):
        """同步 Claude 配置到 WSL"""
        if not self.wsl_home:
            return

        try:
            # 创建 WSL 侧的 .claude 目录
            wsl_claude_dir = f"{self.wsl_home}/.claude"
            subprocess.run(['wsl', 'mkdir', '-p', wsl_claude_dir], capture_output=True, creationflags=0x08000000)
            wsl_target = f"{wsl_claude_dir}/settings.json"
            wsl_data = self._read_wsl_json(wsl_target)
            merged_data = self._merge_claude_env_into_settings(
                wsl_data,
                self._build_managed_claude_env(api_key, base_url, model),
            )
            self._write_wsl_json(wsl_target, merged_data)
        except Exception as e:
            print(f"同步 Claude 配置到 WSL 失败: {e}")

    def sync_file_to_wsl(self, win_path: Path, filename: str):
        """同步单个文件到 WSL"""
        if not self.wsl_home:
            return

        try:
            if win_path.exists():
                wsl_codex_dir = f"{self.wsl_home}/.codex"
                wsl_target = f"{wsl_codex_dir}/{filename}"
                win_target = self._get_wsl_windows_path(wsl_target)
                if win_target is not None:
                    win_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(win_path, win_target)
                    return

                win_path_str = str(win_path).replace('\\', '/')
                # 转换为 WSL 路径格式
                wsl_win_path = f"/mnt/{win_path_str[0].lower()}/{win_path_str[3:]}"

                # WSL 侧也创建 .codex 目录
                subprocess.run(['wsl', 'mkdir', '-p', wsl_codex_dir], capture_output=True, creationflags=0x08000000)

                cmd = f'wsl cp "{wsl_win_path}" "{wsl_target}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, creationflags=0x08000000)

                if result.returncode != 0:
                    raise Exception(f"同步失败: {result.stderr}")
        except Exception as e:
            print(f"同步 {filename} 到 WSL 失败: {e}")

    def _probe_endpoint(self, base_url: str, model: str, api_key: str, format_type: str, callback):
        """在后台线程中探测 API 端点可用性

        format_type: 'claude' 使用 Anthropic Messages API, 'openai' 使用 OpenAI Responses API
        callback 会在主线程中被调用，参数为 (success: bool, message: str)
        """
        model = (model or '').strip()
        api_key = (api_key or '').strip()

        # 规范化 base_url: 去掉末尾 /v1 避免重复，然后统一拼接 /v1/messages 或 /v1/responses
        base_url = (base_url or '').strip().rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-3]

        if not base_url:
            callback(False, 'Base URL 为空，无法探测')
            return
        if not model:
            callback(False, 'Model 为空，无法探测')
            return
        if not api_key:
            callback(False, 'API Key 为空，无法探测')

        def _do_probe():
            try:
                if format_type == 'openai':
                    url = f'{base_url}/v1/responses'
                    payload = json.dumps({
                        'model': model,
                        'input': 'just say hi, nothing else',
                    }).encode('utf-8')
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {api_key}',
                        'User-Agent': 'ccPivot/1.0',
                    }
                else:
                    url = f'{base_url}/v1/messages'
                    payload = json.dumps({
                        'model': model,
                        'max_tokens': 64,
                        'metadata': {
                            'user_id': '{"device_id":"ccPivot-probe"}',
                        },
                        'messages': [
                            {'role': 'user', 'content': 'just say hi, nothing else'},
                        ],
                    }).encode('utf-8')
                    headers = {
                        'Content-Type': 'application/json',
                        'x-api-key': api_key,
                        'anthropic-version': '2023-06-01',
                        'anthropic-dangerous-direct-browser-access': 'true',
                        'User-Agent': 'ccPivot/1.0',
                    }

                req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
                start = time.time()
                resp = urllib.request.urlopen(req, timeout=15)
                elapsed_ms = int((time.time() - start) * 1000)

                raw = resp.read().decode('utf-8', errors='replace')
                body = json.loads(raw) if raw else {}

                status_code = resp.getcode()
                if 200 <= status_code < 300:
                    info_parts = [f'状态码: {status_code}', f'耗时: {elapsed_ms}ms']

                    if format_type == 'openai':
                        reply = ''
                        if isinstance(body, dict):
                            outputs = body.get('output', [])
                            if outputs and isinstance(outputs, list):
                                first = outputs[0]
                                if isinstance(first, dict):
                                    for item in first.get('content', []):
                                        if isinstance(item, dict) and item.get('type') == 'output_text':
                                            reply = item.get('text', '')
                                            break
                        if reply:
                            info_parts.append(f'回复: {reply}')
                        info_parts.append(f'Model: {body.get("model", model) if isinstance(body, dict) else model}')
                    else:
                        reply = ''
                        if isinstance(body, dict):
                            for msg in body.get('content', []):
                                if isinstance(msg, dict) and msg.get('type') == 'text':
                                    reply = msg.get('text', '')
                                    break
                        if reply:
                            info_parts.append(f'回复: {reply}')
                        info_parts.append(f'Model: {body.get("model", model) if isinstance(body, dict) else model}')

                    callback(True, ' | '.join(info_parts))
                else:
                    callback(False, f'状态码: {status_code}')

            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read().decode('utf-8', errors='replace')[:200]
                except Exception:
                    err_body = ''
                callback(False, f'HTTP {e.code}: {err_body}')
            except urllib.error.URLError as e:
                callback(False, f'网络错误: {e.reason}')
            except Exception as e:
                callback(False, f'异常: {e}')

        thread = threading.Thread(target=_do_probe, daemon=True)
        thread.start()

    def _on_probe_codex_result(self, success: bool, message: str):
        """Codex 探针回调（主线程）"""
        self.root.after(0, lambda: self._show_probe_result(success, message, self.codex_probe_btn, 'Codex'))

    def _on_probe_claude_result(self, success: bool, message: str):
        """Claude 探针回调（主线程）"""
        self.root.after(0, lambda: self._show_probe_result(success, message, self.claude_probe_btn, 'Claude'))

    def _show_probe_result(self, success: bool, message: str, probe_btn, label: str):
        """在主线程中显示探针结果（状态栏）"""
        probe_btn.config(text='探针', state='normal')
        if success:
            self.set_status(f'[{label} 探针] ✓ {message}')
        else:
            self.set_status(f'[{label} 探针] ✗ {message}', 'error')

    def probe_codex_provider(self):
        """探测当前 Codex 供应商的 API 可用性"""
        provider_name = self.codex_provider_var.get().strip()
        if not provider_name:
            self.set_status('请先选择或创建一个 Codex 供应商', 'error')
            return

        base_url = self.codex_baseurl.get().strip()
        model = self.codex_model.get().strip()
        api_key = self.codex_apikey.get().strip()

        if not api_key and provider_name in self.codex_providers:
            api_key = self.codex_providers[provider_name].get('api_key', '')

        # 判断格式: wire_api='messages' → Claude 格式, 否则 OpenAI 格式
        provider_config = self.codex_providers.get(provider_name, {})
        wire_api = provider_config.get('wire_api', 'responses')
        format_type = 'claude' if wire_api == 'messages' else 'openai'

        self.codex_probe_btn.config(text='探测中...', state='disabled')
        self.set_status(f'正在探测 Codex 供应商 "{provider_name}" ...')
        self._probe_endpoint(base_url, model, api_key, format_type, self._on_probe_codex_result)

    def probe_claude_profile(self):
        """探测当前 Claude 供应商的 API 可用性"""
        name = self.claude_profile_var.get().strip()
        if not name:
            self.set_status('请先选择或创建一个 Claude 供应商', 'error')
            return

        base_url = self.claude_baseurl.get().strip()
        model = self.claude_model.get().strip()
        api_key = self.claude_apikey.get().strip()

        if not api_key and name in self.claude_profiles:
            api_key = self.claude_profiles[name].get('api_key', '')

        self.claude_probe_btn.config(text='探测中...', state='disabled')
        self.set_status(f'正在探测 Claude 供应商 "{name}" ...')
        self._probe_endpoint(base_url, model, api_key, 'claude', self._on_probe_claude_result)

    def set_status(self, message: str, level: str = "info"):
        """设置状态栏消息"""
        self.status_label.config(text=message)
        if level == "error":
            self.status_label.config(foreground="red")
        else:
            self.status_label.config(foreground="black")


def main():
    try:
        print("创建窗口...")
        if tb is not None:
            root = tb.Window(themename="flatly")
        else:
            root = tk.Tk()
        print("初始化应用...")
        app = ConfigSwitcher(root)
        print("启动主循环...")
        root.mainloop()
    except Exception as e:
        print(f"程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")


if __name__ == "__main__":
    main()










