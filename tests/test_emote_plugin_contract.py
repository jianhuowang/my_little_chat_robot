import ast
import json
import re
import sys
from pathlib import Path

import pytest


PLUGIN_DIR = Path(__file__).parents[1] / "plugins" / "chihaya_emotes"
MAIN_PATH = PLUGIN_DIR / "main.py"
SCHEMA_PATH = PLUGIN_DIR / "_conf_schema.json"
METADATA_PATH = PLUGIN_DIR / "metadata.yaml"
SUPPORTED_PLATFORMS = {"aiocqhttp", "webchat"}


def _tree() -> ast.Module:
    return ast.parse(MAIN_PATH.read_text(encoding="utf-8"))


def _method(name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing async handler: {name}")


def _source(node: ast.AST) -> str:
    return ast.unparse(node)


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    target: ast.expr = node.func
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))


def _fixed_log_call(handler: ast.ExceptHandler, message: str) -> ast.Call:
    call = next(
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call) and _call_name(node) == "logger.exception"
    )
    assert len(call.args) == 1
    assert isinstance(call.args[0], ast.Constant) and call.args[0].value == message
    assert len(call.keywords) == 1
    assert call.keywords[0].arg == "exc_info"
    assert isinstance(call.keywords[0].value, ast.Constant)
    assert call.keywords[0].value.value is False
    return call


@pytest.mark.parametrize("path", [MAIN_PATH, SCHEMA_PATH, METADATA_PATH])
def test_plugin_file_exists(path: Path) -> None:
    assert path.is_file(), f"missing plugin file: {path.name}"


def test_configuration_schema_has_only_approved_numeric_defaults() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema == {
        "chat_probability": {
            "description": "普通 LLM 回复附图概率",
            "type": "float",
            "default": 0.2,
        },
        "session_cooldown_seconds": {
            "description": "同一会话发图冷却秒数",
            "type": "int",
            "default": 300,
        },
        "session_hourly_limit": {
            "description": "滚动窗口内每会话图片上限",
            "type": "int",
            "default": 3,
        },
        "global_hourly_limit": {
            "description": "滚动窗口内全局图片上限",
            "type": "int",
            "default": 10,
        },
        "window_seconds": {
            "description": "滚动额度窗口秒数",
            "type": "int",
            "default": 3600,
        },
    }


def test_metadata_declares_identity_version_floor_and_supported_platforms() -> None:
    text = METADATA_PATH.read_text(encoding="utf-8")

    assert re.search(r"(?m)^name: chihaya_emotes$", text)
    assert re.search(r"(?m)^version: 0\.1\.0$", text)
    assert re.search(r'(?m)^astrbot_version: ">=4\.27\.2"$', text)
    platforms = set(re.findall(r"(?m)^  - ([a-z0-9_]+)$", text))
    assert platforms == SUPPORTED_PLATFORMS


def test_main_imports_only_astrbot_plugin_and_standard_library_modules() -> None:
    tree = _tree()
    allowed_roots = set(sys.stdlib_module_names) | {"astrbot", "plugins"}

    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".", 1)[0] in allowed_roots for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module is not None
            assert node.module.split(".", 1)[0] in allowed_roots


def test_constructor_validates_config_and_wires_local_controller_state() -> None:
    tree = _tree()
    plugin_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ChihayaEmotes"
    )
    assert any(
        isinstance(base, ast.Name) and base.id == "Star"
        for base in plugin_class.bases
    )
    constructor = next(
        node
        for node in plugin_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    source = _source(constructor)

    assert "super().__init__(context)" in source
    assert "isinstance(config, AstrBotConfig)" in source
    assert 'Path(__file__).resolve().parent / "emotes"' in MAIN_PATH.read_text(
        encoding="utf-8"
    )
    assert any(
        isinstance(node, ast.Constant) and node.value == "quota-state.json"
        for node in ast.walk(constructor)
    )
    for dependency in (
        "EmoteSettings",
        "ImagePool",
        "RollingQuota",
        "EmoteController",
    ):
        assert dependency in source


def test_direct_handler_stops_llm_before_controller_and_never_requests_llm() -> None:
    method = _method("on_message")
    source = _source(method)
    decorators = [_source(node) for node in method.decorator_list]
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)]
    disable_calls = [
        node for node in calls if _call_name(node) == "event.should_call_llm"
    ]
    awaits = [node for node in ast.walk(method) if isinstance(node, ast.Await)]

    assert (
        "filter.event_message_type(filter.EventMessageType.ALL, priority=1000)"
        in decorators
    )
    assert SUPPORTED_PLATFORMS <= set(
        re.findall(r"['\"](aiocqhttp|webchat)['\"]", source)
    )
    assert "matches_request" in source
    assert len(disable_calls) == 1
    assert ast.literal_eval(disable_calls[0].args[0]) is False
    assert awaits and disable_calls[0].lineno < min(node.lineno for node in awaits)
    assert "controller.direct" in source
    assert "request_llm" not in source
    assert source.count(".stop_event()") >= 4


def test_direct_failure_is_fixed_safe_local_reply_and_cannot_fall_through() -> None:
    method = _method("on_message")
    handlers = [
        node for node in ast.walk(method) if isinstance(node, ast.ExceptHandler)
    ]
    exception_handler = next(
        node
        for node in handlers
        if isinstance(node.type, ast.Name) and node.type.id == "Exception"
    )
    source = _source(exception_handler)

    assert exception_handler.name is None
    _fixed_log_call(exception_handler, "Chihaya emote direct request failed")
    assert "今天的爱音好像卡在门口了，晚点再来" in source
    assert ".stop_event()" in source
    assert isinstance(exception_handler.body[-1], ast.Return)


def test_decorator_only_appends_local_image_to_final_non_streaming_llm_result() -> None:
    method = _method("decorate_result")
    source = _source(method)
    decorators = [_source(node) for node in method.decorator_list]

    assert "filter.on_decorating_result()" in decorators
    assert SUPPORTED_PLATFORMS <= set(
        re.findall(r"['\"](aiocqhttp|webchat)['\"]", source)
    )
    assert "result is None" in source
    assert "not result.chain" in source
    assert "not result.is_llm_result()" in source
    assert "result.async_stream is not None" in source
    assert "await self.controller.passive(event.unified_msg_origin)" in source
    assert "Comp.Image.fromFileSystem(str(image))" in source
    assert source.index("await self.controller.passive") < source.index(
        "result.chain.append"
    )


def test_passive_failure_logs_fixed_message_and_preserves_result_chain() -> None:
    method = _method("decorate_result")
    handler = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "Exception"
    )
    source = _source(handler)

    assert handler.name is None
    _fixed_log_call(handler, "Chihaya emote decoration failed")
    assert isinstance(handler.body[-1], ast.Return)
    assert "result.chain" not in source
