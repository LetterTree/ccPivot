import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config_switcher import ConfigSwitcher


class ClaudeWslSyncTests(unittest.TestCase):
    def setUp(self):
        self.switcher = ConfigSwitcher.__new__(ConfigSwitcher)

    def test_merge_claude_env_keeps_unrelated_settings(self):
        source_env = {
            "ANTHROPIC_AUTH_TOKEN": "new-token",
            "ANTHROPIC_MODEL": "claude-sonnet",
        }
        target_data = {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "old-token",
                "ANTHROPIC_BASE_URL": "https://old.example.com",
                "UNRELATED_ENV": "keep-me",
            },
            "permissions": {"allow": ["Bash(ls:*)"]},
            "model": "legacy-top-level-model",
        }

        merged = self.switcher._merge_claude_env_into_settings(target_data, source_env)

        self.assertEqual("new-token", merged["env"]["ANTHROPIC_AUTH_TOKEN"])
        self.assertEqual("claude-sonnet", merged["env"]["ANTHROPIC_MODEL"])
        self.assertEqual("keep-me", merged["env"]["UNRELATED_ENV"])
        self.assertNotIn("ANTHROPIC_BASE_URL", merged["env"])
        self.assertEqual({"allow": ["Bash(ls:*)"]}, merged["permissions"])
        self.assertNotIn("model", merged)

    def test_merge_claude_env_creates_env_block_when_missing(self):
        source_env = {
            "ANTHROPIC_BASE_URL": "https://api.example.com",
        }

        merged = self.switcher._merge_claude_env_into_settings({}, source_env)

        self.assertEqual(
            {"ANTHROPIC_BASE_URL": "https://api.example.com"},
            merged["env"],
        )

    def test_decode_wsl_distro_output_from_utf16le(self):
        raw = b'U\x00b\x00u\x00n\x00t\x00u\x00-\x002\x000\x00.\x000\x004\x00\r\x00\n\x00'
        distro = self.switcher._decode_wsl_text(raw)
        self.assertEqual("Ubuntu-20.04", distro.strip())

    def test_get_wsl_windows_path_builds_unc_path(self):
        self.switcher.wsl_distro = "Ubuntu-20.04"
        wsl_path = "/home/letree/.claude/settings.json"
        win_path = self.switcher._get_wsl_windows_path(wsl_path)
        self.assertEqual(
            r"\\wsl.localhost\Ubuntu-20.04\home\letree\.claude\settings.json",
            str(win_path),
        )

    def test_read_wsl_json_prefers_unc_file(self):
        temp_path = Path("tests") / "_wsl_unc_settings.json"
        try:
            temp_path.write_text('{"language":"简体中文","env":{"UNRELATED_ENV":"keep-me"}}', encoding="utf-8")
            self.switcher._get_wsl_windows_path = Mock(return_value=temp_path)
            self.switcher._run_wsl_shell = Mock()

            data = self.switcher._read_wsl_json("/home/letree/.claude/settings.json")

            self.assertEqual("简体中文", data["language"])
            self.assertEqual("keep-me", data["env"]["UNRELATED_ENV"])
            self.switcher._run_wsl_shell.assert_not_called()
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_sync_file_to_wsl_prefers_unc_copy(self):
        source_path = Path("tests") / "_codex_sync_source.json"
        target_path = Path("tests") / "_codex_sync_target.json"
        try:
            source_path.write_text('{"OPENAI_API_KEY":"test"}', encoding="utf-8")
            self.switcher.wsl_home = "/home/tester"
            self.switcher._get_wsl_windows_path = Mock(return_value=target_path)

            with patch("config_switcher.subprocess.run") as run_mock:
                self.switcher.sync_file_to_wsl(source_path, "auth.json")

            self.assertEqual('{"OPENAI_API_KEY":"test"}', target_path.read_text(encoding="utf-8"))
            run_mock.assert_not_called()
        finally:
            if source_path.exists():
                try:
                    source_path.unlink()
                except PermissionError:
                    pass
            if target_path.exists():
                try:
                    target_path.unlink()
                except PermissionError:
                    pass

    def test_sync_codex_config_to_wsl_updates_runtime_fields_only(self):
        self.switcher.wsl_home = "/home/tester"
        self.switcher.codex_runtime_provider_alias = "cc_session_shared"
        wsl_data = {
            "model_provider": "old_provider",
            "base_url": "https://old.example.com",
            "model": "old-model",
            "features": {"keep": True},
            "model_providers": {
                "old_provider": {"name": "old_provider", "base_url": "https://old.example.com", "model": "old-model"},
                "cc_session_shared": {"name": "legacy", "base_url": "https://legacy.example.com", "model": "legacy-model", "wire_api": "chat_completions", "requires_openai_auth": False},
                "keep_provider": {"name": "keep_provider", "base_url": "https://keep.example.com", "model": "keep-model"},
            },
        }
        self.switcher._read_wsl_toml = Mock(return_value=wsl_data)
        self.switcher._write_wsl_toml = Mock()

        provider = {
            "name": "new_provider",
            "base_url": "https://new.example.com",
            "model": "new-model",
            "api_key": "sk-test",
        }

        self.switcher.sync_codex_config_to_wsl_for_apply("new_provider", provider)

        self.switcher._write_wsl_toml.assert_called_once_with(
            "/home/tester/.codex/config.toml",
            {
                "model_provider": "cc_session_shared",
                "base_url": "https://new.example.com",
                "model": "new-model",
                "features": {"keep": True},
                "model_providers": {
                    "old_provider": {"name": "old_provider", "base_url": "https://old.example.com", "model": "old-model"},
                    "cc_session_shared": {
                        "name": "new_provider",
                        "base_url": "https://new.example.com",
                        "model": "new-model",
                        "wire_api": "chat_completions",
                        "requires_openai_auth": False,
                    },
                    "keep_provider": {"name": "keep_provider", "base_url": "https://keep.example.com", "model": "keep-model"},
                    "new_provider": {
                        "name": "new_provider",
                        "base_url": "https://new.example.com",
                        "model": "new-model",
                        "wire_api": "responses",
                        "requires_openai_auth": True,
                    },
                },
            },
        )

    def test_sync_codex_auth_to_wsl_updates_api_key_only(self):
        self.switcher.wsl_home = "/home/tester"
        self.switcher._read_wsl_json = Mock(
            return_value={
                "OPENAI_API_KEY": "old-key",
                "session": {"keep": True},
                "api_key": "legacy-key",
            }
        )
        self.switcher._write_wsl_json = Mock()

        self.switcher.sync_codex_auth_to_wsl("new-key")

        self.switcher._write_wsl_json.assert_called_once_with(
            "/home/tester/.codex/auth.json",
            {
                "OPENAI_API_KEY": "new-key",
                "session": {"keep": True},
            },
        )

    def test_merge_claude_env_for_wsl_preserves_missing_managed_values(self):
        source_env = {
            "ANTHROPIC_AUTH_TOKEN": "new-token",
        }
        target_data = {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "old-token",
                "ANTHROPIC_BASE_URL": "https://keep.example.com",
                "ANTHROPIC_MODEL": "claude-keep",
                "UNRELATED_ENV": "keep-me",
            },
            "model": "legacy-top-level-model",
            "permissions": {"defaultMode": "auto"},
        }

        merged = self.switcher._merge_claude_env_into_settings(
            target_data,
            source_env,
            remove_missing=False,
            clear_legacy_model=False,
        )

        self.assertEqual("new-token", merged["env"]["ANTHROPIC_AUTH_TOKEN"])
        self.assertEqual("https://keep.example.com", merged["env"]["ANTHROPIC_BASE_URL"])
        self.assertEqual("claude-keep", merged["env"]["ANTHROPIC_MODEL"])
        self.assertEqual("keep-me", merged["env"]["UNRELATED_ENV"])
        self.assertEqual("legacy-top-level-model", merged["model"])
        self.assertEqual({"defaultMode": "auto"}, merged["permissions"])

    def test_sync_claude_to_wsl_updates_only_managed_fields(self):
        self.switcher.wsl_home = "/home/tester"
        self.switcher._read_wsl_json = Mock(
            return_value={
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "old-token",
                    "ANTHROPIC_BASE_URL": "https://old.example.com",
                    "ANTHROPIC_MODEL": "claude-old",
                    "UNRELATED_ENV": "keep-me",
                },
                "model": "legacy-top-level-model",
                "permissions": {"allow": ["Bash(ls:*)"]},
            }
        )
        self.switcher._write_wsl_json = Mock()

        with patch(
            "config_switcher.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0),
        ):
            self.switcher.sync_claude_to_wsl(
                api_key="new-token",
                base_url="https://new.example.com",
                model="claude-new",
            )

        self.switcher._write_wsl_json.assert_called_once_with(
            "/home/tester/.claude/settings.json",
            {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "new-token",
                    "ANTHROPIC_BASE_URL": "https://new.example.com",
                    "ANTHROPIC_MODEL": "claude-new",
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5-20251001",
                    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-6",
                    "UNRELATED_ENV": "keep-me",
                },
                "permissions": {"allow": ["Bash(ls:*)"]},
            },
        )

    def test_sync_claude_to_wsl_clears_managed_fields_like_windows(self):
        self.switcher.wsl_home = "/home/tester"
        self.switcher._read_wsl_json = Mock(
            return_value={
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "old-token",
                    "ANTHROPIC_BASE_URL": "https://old.example.com",
                    "ANTHROPIC_MODEL": "claude-old",
                    "UNRELATED_ENV": "keep-me",
                },
                "model": "legacy-top-level-model",
                "permissions": {"allow": ["Bash(ls:*)"]},
            }
        )
        self.switcher._write_wsl_json = Mock()

        with patch(
            "config_switcher.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0),
        ):
            self.switcher.sync_claude_to_wsl(
                api_key="new-token",
                base_url="",
                model="",
            )

        self.switcher._write_wsl_json.assert_called_once_with(
            "/home/tester/.claude/settings.json",
            {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "new-token",
                    "UNRELATED_ENV": "keep-me",
                },
                "permissions": {"allow": ["Bash(ls:*)"]},
            },
        )


if __name__ == "__main__":
    unittest.main()
