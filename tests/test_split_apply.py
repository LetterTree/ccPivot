import unittest
from unittest.mock import Mock

from config_switcher import ConfigSwitcher


class SplitApplyDetectionTests(unittest.TestCase):
    def setUp(self):
        self.switcher = ConfigSwitcher.__new__(ConfigSwitcher)
        self.switcher.codex_runtime_provider_alias = "cc_session_shared"
        self.switcher.codex_providers = {
            "alpha": {
                "name": "alpha",
                "base_url": "https://alpha.example.com",
                "model": "alpha-model",
                "api_key": "sk-alpha",
            },
            "beta": {
                "name": "beta",
                "base_url": "https://beta.example.com",
                "model": "beta-model",
                "api_key": "sk-beta",
            },
        }
        self.switcher.claude_profiles = {
            "work": {
                "api_key": "tok-work",
                "base_url": "https://work.example.com",
                "model": "claude-work",
            },
            "home": {
                "api_key": "tok-home",
                "base_url": "",
                "model": "",
            },
        }
        self.switcher.CLAUDE_ENV_KEYS = (
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL",
        )

    def test_detect_codex_active_from_runtime_alias_matches_provider(self):
        data = {
            "model_provider": "cc_session_shared",
            "model": "alpha-model",
            "model_providers": {
                "cc_session_shared": {
                    "name": "alpha",
                    "base_url": "https://alpha.example.com",
                    "model": "alpha-model",
                }
            },
        }
        self.assertEqual("alpha", self.switcher._detect_codex_active_provider_from_config(data))

    def test_detect_codex_active_from_direct_provider(self):
        data = {
            "model_provider": "beta",
            "model_providers": {"beta": {"name": "beta", "base_url": "https://beta.example.com", "model": "beta-model"}},
        }
        self.assertEqual("beta", self.switcher._detect_codex_active_provider_from_config(data))

    def test_detect_codex_active_returns_none_when_no_provider(self):
        self.assertIsNone(self.switcher._detect_codex_active_provider_from_config({}))
        self.assertIsNone(self.switcher._detect_codex_active_provider_from_config({"model_provider": ""}))

    def test_match_claude_profile_exact_match(self):
        env = {
            "ANTHROPIC_AUTH_TOKEN": "tok-work",
            "ANTHROPIC_BASE_URL": "https://work.example.com",
            "ANTHROPIC_MODEL": "claude-work",
        }
        self.assertEqual("work", self.switcher._match_claude_profile_from_env(env))

    def test_match_claude_profile_mismatched_returns_none(self):
        env = {
            "ANTHROPIC_AUTH_TOKEN": "tok-work",
            "ANTHROPIC_BASE_URL": "https://diff.example.com",
            "ANTHROPIC_MODEL": "claude-work",
        }
        self.assertIsNone(self.switcher._match_claude_profile_from_env(env))

    def test_match_claude_profile_partial_fields(self):
        env = {"ANTHROPIC_AUTH_TOKEN": "tok-home"}
        self.assertEqual("home", self.switcher._match_claude_profile_from_env(env))

    def test_match_claude_profile_empty_env_returns_none(self):
        self.assertIsNone(self.switcher._match_claude_profile_from_env({}))

    def test_detect_codex_active_provider_wsl_returns_none_without_wsl_home(self):
        self.switcher.wsl_home = None
        self.assertIsNone(self.switcher._detect_codex_active_provider_wsl())

    def test_detect_codex_active_provider_wsl_reads_and_parses(self):
        self.switcher.wsl_home = "/home/tester"
        wsl_data = {
            "model_provider": "cc_session_shared",
            "model_providers": {
                "cc_session_shared": {
                    "name": "beta",
                    "base_url": "https://beta.example.com",
                    "model": "beta-model",
                }
            },
        }
        self.switcher._read_wsl_toml = Mock(return_value=wsl_data)
        self.assertEqual("beta", self.switcher._detect_codex_active_provider_wsl())
        self.switcher._read_wsl_toml.assert_called_once_with("/home/tester/.codex/config.toml")

    def test_detect_claude_active_profile_wsl_reads_env_block(self):
        self.switcher.wsl_home = "/home/tester"
        self.switcher._read_wsl_json = Mock(
            return_value={
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "tok-home",
                }
            }
        )
        result = self.switcher._detect_claude_active_profile_wsl()
        self.assertEqual(("home", True), result)

    def test_detect_claude_active_profile_wsl_returns_none_without_wsl(self):
        self.switcher.wsl_home = None
        self.assertIsNone(self.switcher._detect_claude_active_profile_wsl())

    def test_detect_claude_active_profile_windows_no_env_block(self):
        self.switcher.claude_settings_path = Mock()
        self.switcher.claude_settings_path.exists.return_value = True
        self.switcher._read_json_file = Mock(return_value={"permissions": {"allow": []}})
        result = self.switcher._detect_claude_active_profile_windows()
        self.assertEqual((None, False), result)

    def test_apply_codex_provider_to_wsl_no_op_without_wsl(self):
        self.switcher.wsl_home = None
        self.switcher.sync_codex_config_to_wsl_for_apply = Mock()
        self.switcher.sync_codex_auth_to_wsl = Mock()
        self.switcher._apply_codex_provider_to_wsl(
            "alpha", self.switcher.codex_providers["alpha"]
        )
        self.switcher.sync_codex_config_to_wsl_for_apply.assert_not_called()
        self.switcher.sync_codex_auth_to_wsl.assert_not_called()

    def test_apply_codex_provider_to_wsl_calls_sync(self):
        self.switcher.wsl_home = "/home/tester"
        self.switcher.sync_codex_config_to_wsl_for_apply = Mock()
        self.switcher.sync_codex_auth_to_wsl = Mock()
        provider = self.switcher.codex_providers["alpha"]
        self.switcher._apply_codex_provider_to_wsl("alpha", provider)
        self.switcher.sync_codex_config_to_wsl_for_apply.assert_called_once_with("alpha", provider)
        self.switcher.sync_codex_auth_to_wsl.assert_called_once_with("sk-alpha")

    def test_apply_claude_profile_to_wsl_no_op_without_wsl(self):
        self.switcher.wsl_home = None
        self.switcher.sync_claude_to_wsl = Mock()
        self.switcher._apply_claude_profile_to_wsl("k", "u", "m")
        self.switcher.sync_claude_to_wsl.assert_not_called()

    def test_apply_claude_profile_to_wsl_calls_sync(self):
        self.switcher.wsl_home = "/home/tester"
        self.switcher.sync_claude_to_wsl = Mock()
        self.switcher._apply_claude_profile_to_wsl("k", "u", "m")
        self.switcher.sync_claude_to_wsl.assert_called_once_with(api_key="k", base_url="u", model="m")


if __name__ == "__main__":
    unittest.main()
