# Codex 供应商切换功能改进 - 实施摘要

## 改进目标

将当前的"完整配置文件替换"方式改为利用 Codex 原生的 `[model_providers.xxx]` 机制。

## 核心变更

### 1. 数据结构变更

**文件位置**: 第 28-29 行

```python
# 旧代码
self.codex_profiles: Dict[str, Dict[str, Any]] = {}
self.codex_active_profile: Optional[str] = None

# 新代码
self.codex_providers: Dict[str, Dict[str, Any]] = {}
self.codex_active_provider: Optional[str] = None
```

### 2. 规范化方法变更

**文件位置**: 第 90-97 行

```python
# 旧方法名和实现
def _normalize_codex_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'base_url': profile.get('base_url', ''),
        'model': profile.get('model', ''),
        'api_key': profile.get('api_key', ''),
        'config_toml': profile.get('config_toml', ''),
        'auth_json': profile.get('auth_json', ''),
    }

# 新方法名和实现
def _normalize_codex_provider(self, provider: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'name': provider.get('name', ''),
        'base_url': provider.get('base_url', ''),
        'model': provider.get('model', ''),
        'api_key': provider.get('api_key', ''),
        'wire_api': provider.get('wire_api', 'responses'),
        'requires_openai_auth': provider.get('requires_openai_auth', True),
    }
```

### 3. 新增方法：从 config.toml 加载供应商

**插入位置**: 第 106 行之前（load_profiles 方法之前）

```python
def _load_codex_providers_from_toml(self):
    """从 config.toml 读取所有 [model_providers.xxx] 定义"""
    if not self.codex_config_path.exists():
        return

    try:
        data = toml.load(self.codex_config_path)

        # 读取 model_providers 段落
        if 'model_providers' in data:
            for provider_name, provider_config in data['model_providers'].items():
                self.codex_providers[provider_name] = self._normalize_codex_provider({
                    'name': provider_config.get('name', provider_name),
                    'base_url': provider_config.get('base_url', ''),
                    'model': provider_config.get('model', ''),
                    'wire_api': provider_config.get('wire_api', 'responses'),
                    'requires_openai_auth': provider_config.get('requires_openai_auth', True),
                    'api_key': '',  # API key 从 providers.json 加载
                })

        # 读取当前激活的供应商
        current_provider = data.get('model_provider', '')
        if current_provider and current_provider in self.codex_providers:
            self.codex_active_provider = current_provider

    except Exception as e:
        print(f"从 config.toml 加载 Codex 供应商失败: {e}")
```

### 4. 修改 load_profiles 方法

**文件位置**: 第 108-189 行

需要：
1. 在开头调用 `self._load_codex_providers_from_toml()`
2. 添加 v3 版本支持
3. 添加 v2 -> v3 迁移逻辑
4. 将所有 `codex_profiles` 改为 `codex_providers`
5. 将所有 `codex_active_profile` 改为 `codex_active_provider`
6. 将所有 `_normalize_codex_profile` 改为 `_normalize_codex_provider`
7. 将所有 `_capture_current_codex_profile` 改为 `_capture_current_codex_provider`
8. 将所有 `codex_profile_var` 改为 `codex_provider_var`
9. 将所有 `_load_codex_profile_to_ui` 改为 `_load_codex_provider_to_ui`

### 5. 修改 _persist_profiles 方法

**文件位置**: 第 191-204 行

```python
def _persist_profiles(self):
    """保存 profiles 到磁盘（v3）"""
    self.app_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        'version': 3,  # 升级到 v3
        'codex': {
            'last_active': self.codex_active_provider,
            'providers': self.codex_providers,
        },
        'claude': {
            'last_active': self.claude_active_profile,
            'profiles': self.claude_profiles,
        },
    }
    with open(self.profiles_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
```

### 6. 修改 _refresh_providers_ui 方法

**文件位置**: 第 206-215 行

将所有 `codex_profiles` 改为 `codex_providers`，`codex_active_profile` 改为 `codex_active_provider`。

### 7. 修改 _capture_current_codex_profile 方法

**文件位置**: 第 281-288 行

重命名为 `_capture_current_codex_provider`，并修改实现以支持新字段。

### 8. 修改 _load_codex_profile_to_ui 方法

**文件位置**: 第 297-326 行

重命名为 `_load_codex_provider_to_ui`，移除 TOML/JSON 编辑器相关代码，添加新字段支持。

### 9. 修改事件处理方法

**文件位置**: 第 342-347 行

将 `on_codex_profile_selected` 重命名为 `on_codex_provider_selected`。

### 10. 重写供应商管理方法

需要重写以下方法：
- `create_codex_profile` -> `create_codex_provider` (第 364-380 行)
- `save_codex_profile` -> `save_codex_provider` (第 382-408 行)
- `delete_codex_profile` -> `delete_codex_provider` (第 410-476 行)
- `apply_codex_profile` -> `switch_codex_provider` (第 427-519 行)

### 11. 修改 UI 设置

**文件位置**: 第 637-702 行 (setup_codex_tab 方法)

主要变更：
1. 将 `codex_profile_var` 改为 `codex_provider_var`
2. 将 `codex_profile_combo` 改为 `codex_provider_combo`
3. 更新按钮绑定
4. 添加 Wire API 和 Requires OpenAI Auth 字段
5. 移除高级编辑器相关代码

### 12. 废弃的方法

以下方法不再需要，可以注释掉：
- `toggle_codex_advanced` (第 825-832 行)
- `apply_codex_basic_from_ui` (第 890-908 行)
- `_apply_codex_basic_values` (第 910-960 行)
- `apply_codex_toml` (第 1025-1061 行)
- `apply_codex_auth` (第 1062-1098 行)

## 全局替换列表

在整个文件中需要进行以下替换：
1. `self.codex_profiles` -> `self.codex_providers`
2. `self.codex_active_profile` -> `self.codex_active_provider`
3. `codex_profile_var` -> `codex_provider_var`
4. `codex_profile_combo` -> `codex_provider_combo`
5. `_normalize_codex_profile` -> `_normalize_codex_provider`
6. `_capture_current_codex_profile` -> `_capture_current_codex_provider`
7. `_load_codex_profile_to_ui` -> `_load_codex_provider_to_ui`
8. `on_codex_profile_selected` -> `on_codex_provider_selected`
9. `create_codex_profile` -> `create_codex_provider`
10. `save_codex_profile` -> `save_codex_provider`
11. `delete_codex_profile` -> `delete_codex_provider`
12. `apply_codex_profile` -> `switch_codex_provider`

## 实施建议

由于这是一个大规模重构，建议：
1. 使用 IDE 的重构功能进行方法重命名
2. 分步骤进行，每次修改后测试
3. 保持备份文件
4. 先在测试环境验证

## 测试清单

完成修改后需要测试：
1. 启动程序，检查是否能正常加载
2. 查看供应商列表是否正确显示
3. 创建新供应商
4. 保存供应商到 config.toml
5. 切换供应商
6. 删除供应商
7. 重启程序，检查状态是否保持
8. 检查 WSL 同步功能
