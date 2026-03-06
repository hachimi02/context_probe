#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型上下文窗口测试工具

对每个模型用 API 接口做二分查找，确定实际可用的上下文窗口大小。
支持 Anthropic 和 OpenAI 兼容的服务商（OpenAI、DeepSeek、Kimi 等）。
"""

import os
import argparse
import json
import time
import threading
import unicodedata
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

try:
    import commentjson
    HAS_COMMENTJSON = True
except ImportError:
    commentjson = None
    HAS_COMMENTJSON = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── 条件导入 SDK ─────────────────────────────────────────────────────────────

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    openai = None
    HAS_OPENAI = False

try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    tiktoken = None
    HAS_TIKTOKEN = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    requests = None
    HAS_REQUESTS = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    tqdm = None
    HAS_TQDM = False


# ── 终端表格辅助 ─────────────────────────────────────────────────────────────

def str_width(s):
    """计算字符串显示宽度（CJK 字符算 2 列）。"""
    width = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ('W', 'F') else 1
    return width


def ljust_w(s, width):
    """按显示宽度左对齐，补空格。"""
    return s + " " * max(0, width - str_width(s))


# ── 配置加载 ──────────────────────────────────────────────────────────────────

def load_config(config_path):
    try:
        with open(config_path, encoding='utf-8') as f:
            if HAS_COMMENTJSON:
                return commentjson.load(f)
            else:
                return json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, ValueError) as e:
        print(f"配置文件格式错误: {e}")
        sys.exit(1)


def get_api_key(args, config):
    key = args.api_key or config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or ""
    if not key:
        key = input("请输入 API Key: ").strip()
    return key


def get_base_url(args, config):
    url = args.base_url or config.get("base_url") or ""
    if not url:
        print("请选择 Base URL：")
        print("  1. 官方默认 (https://api.anthropic.com)")
        print("  2. 自定义")
        choice = input("请输入选项 (1/2): ").strip()
        if choice == "2":
            url = input("请输入 Base URL: ").strip()
        else:
            url = ""
    return url or None


def load_providers(args, config):
    """从配置加载 provider 列表。

    新格式: config["providers"] 字典。
    旧格式兼容: 检测到扁平 models 列表时，包装为单个 anthropic provider。
    返回: dict  {provider_name: {type, api_key, base_url, models}}
    """
    if "providers" in config:
        return config["providers"]

    # 旧格式 → 包装为单个 anthropic provider
    api_key = get_api_key(args, config)
    base_url = get_base_url(args, config)
    models = config.get("models", [
        {"name": "claude-haiku-4-5-20251001", "expected_context": 200000},
        {"name": "claude-sonnet-4-6",         "expected_context": 1000000},
    ])
    return {
        "anthropic": {
            "type": "anthropic",
            "api_key": api_key,
            "base_url": base_url,
            "models": models,
        }
    }


# ── 错误判断 ──────────────────────────────────────────────────────────────────

def is_context_error(e):
    """判断是否为上下文长度超限错误。"""
    err_str = str(e).lower()
    keywords = ["too long", "context_length", "prompt is too long",
                "maximum context length", "exceeds the maximum", "context window",
                "max_tokens", "maximum number of tokens"]
    if any(kw in err_str for kw in keywords):
        return True
    if hasattr(e, 'body') and isinstance(e.body, dict):
        msg = e.body.get('error', {}).get('message', '').lower()
        return any(kw in msg for kw in keywords)
    return False


# ── API 调用封装 ───────────────────────────────────────────────────────────────

def _classify_exception_anthropic(e):
    """将 Anthropic 异常分类为 error_type 字符串。"""
    if isinstance(e, anthropic.NotFoundError):
        return "unsupported"
    if isinstance(e, anthropic.BadRequestError):
        return "context" if is_context_error(e) else "unknown"
    if isinstance(e, anthropic.InternalServerError):
        return "overload"
    if isinstance(e, anthropic.APIStatusError):
        if e.status_code == 529:
            return "overload"
        return "proxy"
    if isinstance(e, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return "proxy"
    return "unknown"


def _classify_exception_openai(e):
    """将 OpenAI 兼容 SDK 异常分类为 error_type 字符串。"""
    if isinstance(e, openai.NotFoundError):
        return "unsupported"
    if isinstance(e, openai.BadRequestError):
        return "context" if is_context_error(e) else "unknown"
    if isinstance(e, openai.InternalServerError):
        return "overload"
    if isinstance(e, openai.RateLimitError):
        return "overload"
    if isinstance(e, openai.APIStatusError):
        if e.status_code in (429, 529):
            return "overload"
        if e.status_code in (502, 503, 520, 521):
            return "proxy"
        if e.status_code == 408:
            return "context"
        return "unknown"
    if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
        return "proxy"
    return "unknown"


def make_count_tokens_call(client, model_name):
    """返回 count_tokens 接口的调用函数（Anthropic 专用）。"""
    def call(text):
        try:
            resp = client.messages.count_tokens(
                model=model_name,
                messages=[{"role": "user", "content": text}]
            )
            total = resp.input_tokens
            if hasattr(resp, 'cache_creation_input_tokens'):
                total += resp.cache_creation_input_tokens
            if hasattr(resp, 'cache_read_input_tokens'):
                total += resp.cache_read_input_tokens
            return True, total, None
        except Exception as e:
            return False, None, _classify_exception_anthropic(e)
    return call


def make_messages_create_call(client, model_name):
    """返回 messages.create 接口的调用函数（Anthropic 专用）。"""
    def call(text):
        try:
            resp = client.messages.create(
                model=model_name,
                max_tokens=1,
                messages=[{"role": "user", "content": text}]
            )
            total = resp.usage.input_tokens
            if hasattr(resp.usage, 'cache_creation_input_tokens'):
                total += resp.usage.cache_creation_input_tokens
            if hasattr(resp.usage, 'cache_read_input_tokens'):
                total += resp.usage.cache_read_input_tokens
            return True, total, None
        except Exception as e:
            return False, None, _classify_exception_anthropic(e)
    return call


def make_openai_chat_call(client, model_name):
    """返回 OpenAI chat.completions 接口的调用函数。"""
    def call(text):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                max_tokens=1,
                messages=[{"role": "user", "content": text}]
            )
            return True, resp.usage.prompt_tokens, None
        except Exception as e:
            err_type = _classify_exception_openai(e)
            if err_type == "unknown":
                print(f"    [DEBUG] OpenAI API 异常: {type(e).__name__}: {e}")
            return False, None, err_type
    return call


def make_openai_responses_call(client, model_name):
    """返回 OpenAI responses 接口的调用函数。"""
    def call(text):
        try:
            resp = client.responses.create(
                model=model_name,
                input=[{"role": "user", "content": text}],
                stream=False
            )
            # 调试：打印响应内容
            print(f"    [DEBUG] Response type: {type(resp)}")
            print(f"    [DEBUG] Response content (first 500 chars): {str(resp)[:500]}")

            # 如果响应是字符串，尝试解析为 JSON
            if isinstance(resp, str):
                import json
                try:
                    resp_data = json.loads(resp)
                    print(f"    [DEBUG] Parsed JSON keys: {resp_data.keys() if isinstance(resp_data, dict) else 'not a dict'}")
                    # 尝试从 JSON 中提取 token 信息
                    if isinstance(resp_data, dict) and 'usage' in resp_data:
                        usage = resp_data['usage']
                        if 'input_tokens' in usage:
                            return True, usage['input_tokens'], None
                        elif 'prompt_tokens' in usage:
                            return True, usage['prompt_tokens'], None
                except json.JSONDecodeError as je:
                    print(f"    [DEBUG] JSON decode error: {je}")

            # 标准 SDK 响应格式
            if hasattr(resp, 'usage'):
                if hasattr(resp.usage, 'input_tokens'):
                    return True, resp.usage.input_tokens, None
                elif hasattr(resp.usage, 'prompt_tokens'):
                    return True, resp.usage.prompt_tokens, None

            print(f"    [DEBUG] 无法提取 token 信息")
            return False, None, "unknown"
        except Exception as e:
            err_type = _classify_exception_openai(e)
            print(f"    [DEBUG] OpenAI Responses API 异常: {type(e).__name__}: {e}")
            return False, None, err_type
    return call


def make_openai_count_tokens_call(model_name):
    """返回 OpenAI 本地 token 计数函数（使用 tiktoken）。"""
    if not HAS_TIKTOKEN:
        return None

    def call(text):
        try:
            encoding = tiktoken.encoding_for_model(model_name)
            tokens = len(encoding.encode(text))
            return True, tokens, None
        except Exception:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                tokens = len(encoding.encode(text))
                return True, tokens, None
            except Exception as e:
                return False, None, "tiktoken_error"
    return call


def make_openai_http_chat_call(base_url, api_key, model_name, headers=None):
    """返回 HTTP 方式调用 chat.completions 的函数。"""
    if not HAS_REQUESTS:
        return None

    url = f"{base_url.rstrip('/')}/chat/completions"
    req_headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    def call(text):
        try:
            resp = requests.post(url, json={
                "model": model_name,
                "messages": [{"role": "user", "content": text}],
                "max_tokens": 1,
                "stream": False
            }, headers=req_headers, timeout=120)

            if resp.status_code == 200:
                # 优先尝试 JSON 解析（非流式）
                try:
                    data = resp.json()
                    tokens = data.get("usage", {}).get("prompt_tokens")
                    return True, tokens, None
                except:
                    # JSON 解析失败，尝试 SSE 解析（流式）
                    lines = resp.text.split('\n')
                    for i, line in enumerate(lines):
                        if line.strip() == "event: response.completed" and i + 1 < len(lines):
                            data_line = lines[i + 1]
                            if data_line.startswith("data:"):
                                try:
                                    data = json.loads(data_line[5:].strip())
                                    usage = data.get("response", {}).get("usage", {})
                                    tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
                                    if tokens:
                                        return True, tokens, None
                                except:
                                    pass
                    return False, None, "unknown"
            elif resp.status_code == 400:
                err_msg = resp.text.lower()
                return False, None, "context" if any(kw in err_msg for kw in ["too long", "context", "maximum"]) else "unknown"
            elif resp.status_code in (429, 529):
                return False, None, "overload"
            elif resp.status_code == 404:
                return False, None, "unsupported"
            else:
                return False, None, "proxy"
        except requests.Timeout:
            return False, None, "context"
        except Exception as e:
            return False, None, "proxy"
    return call


def make_openai_http_responses_call(base_url, api_key, model_name, headers=None):
    """返回 HTTP 方式调用 responses 的函数。"""
    if not HAS_REQUESTS:
        return None

    url = f"{base_url.rstrip('/')}/responses"
    req_headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    def call(text):
        try:
            resp = requests.post(url, json={
                "model": model_name,
                "input": [{"role": "user", "content": text}],
                "stream": False
            }, headers=req_headers, timeout=120)

            if resp.status_code == 200:
                # Responses API 只支持 SSE 流式输出
                lines = resp.text.split('\n')
                for i, line in enumerate(lines):
                    if line.strip() == "event: response.completed" and i + 1 < len(lines):
                        data_line = lines[i + 1]
                        if data_line.startswith("data:"):
                            try:
                                data = json.loads(data_line[5:].strip())
                                usage = data.get("response", {}).get("usage", {})
                                tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
                                if tokens:
                                    return True, tokens, None
                            except:
                                pass
                return False, None, "unknown"
            elif resp.status_code == 400:
                err_msg = resp.text.lower()
                return False, None, "context" if any(kw in err_msg for kw in ["too long", "context", "maximum"]) else "unknown"
            elif resp.status_code in (429, 529):
                return False, None, "overload"
            elif resp.status_code == 404:
                return False, None, "unsupported"
            else:
                return False, None, "proxy"
        except requests.Timeout:
            return False, None, "context"
        except Exception as e:
            return False, None, "proxy"
    return call


# ── 客户端工厂 ────────────────────────────────────────────────────────────────

def create_client(provider_type, provider_cfg):
    """根据 provider type 创建对应的 SDK 客户端。"""
    api_key = provider_cfg.get("api_key", "")
    base_url = provider_cfg.get("base_url", "") or None
    headers = provider_cfg.get("headers", {})

    if provider_type == "anthropic":
        if not HAS_ANTHROPIC:
            print("错误: 需要 anthropic SDK。请运行: pip install anthropic")
            sys.exit(1)
        return anthropic.Anthropic(api_key=api_key, base_url=base_url, default_headers=headers if headers else None)

    if provider_type == "openai":
        if not HAS_OPENAI:
            print("错误: 需要 openai SDK。请运行: pip install openai")
            sys.exit(1)
        return openai.OpenAI(api_key=api_key, base_url=base_url, default_headers=headers if headers else None)

    print(f"错误: 不支持的 provider 类型 '{provider_type}'")
    sys.exit(1)


# ── 二分查找 ───────────────────────────────────────────────────────────────────

def _binary_search_phase(api_name, call_fn, content, low_chars, high_chars, threshold, calls, limit_type, last_success_tokens, log, pbar=None):
    """
    单阶段二分查找，在 [low_chars, high_chars] 内收敛到 threshold。

    返回: (low_chars, high_chars, last_success_tokens, limit_type, calls, early_return)
    early_return 不为 None 时表示应直接返回该结果。
    """
    if pbar is None:
        log(f"  [{api_name}] 二分范围: {low_chars:,} – {high_chars:,} 字符（阈值 {threshold} chars）")

    iteration = 0
    while high_chars - low_chars > threshold:
        mid = (low_chars + high_chars) // 2
        iteration += 1

        for attempt in range(1, 4):  # 最多重试 3 次（用于过载）
            calls += 1
            if pbar is not None:
                print(f"     第{iteration}次: 测试 {mid:,} chars", file=sys.stderr, end='', flush=True)
            success, tokens, err_type = call_fn(content[:mid])

            if success:
                last_success_tokens = tokens
                low_chars = mid
                if pbar is not None:
                    print(f" → ✓ {tokens:,} tokens", file=sys.stderr)
                elif pbar is None:
                    log(f"  [{api_name}] {mid:,} chars -> {tokens:,} tokens OK")
                break

            elif err_type == "context":
                high_chars = mid
                if pbar is not None:
                    print(f" → ✗ 超出上下文", file=sys.stderr)
                elif pbar is None:
                    log(f"  [{api_name}] {mid:,} chars -> 超出上下文 FAIL")
                break

            elif err_type == "proxy":
                if pbar is None:
                    log(f"  [{api_name}] {mid:,} chars -> 代理错误，停止")
                early = {"max_tokens": last_success_tokens, "limit_type": "proxy", "calls": calls, "incomplete": True}
                return low_chars, high_chars, last_success_tokens, limit_type, calls, early

            elif err_type == "unsupported":
                if pbar is None:
                    log(f"  [{api_name}] 接口不支持 (404)")
                early = {"max_tokens": None, "limit_type": "unsupported", "calls": calls}
                return low_chars, high_chars, last_success_tokens, limit_type, calls, early

            elif err_type == "overload":
                if attempt < 3:
                    wait = attempt * 10
                    if pbar is None:
                        log(f"  [{api_name}] 服务过载，{wait}s 后重试（第 {attempt} 次）...")
                    time.sleep(wait)
                else:
                    if pbar is None:
                        log(f"  [{api_name}] 过载重试 3 次均失败，停止")
                    early = {"max_tokens": last_success_tokens, "limit_type": limit_type, "calls": calls, "incomplete": True}
                    return low_chars, high_chars, last_success_tokens, limit_type, calls, early

            else:  # unknown
                if pbar is None:
                    log(f"  [{api_name}] 未知错误，停止")
                early = {"max_tokens": last_success_tokens, "limit_type": limit_type, "calls": calls, "incomplete": True}
                return low_chars, high_chars, last_success_tokens, limit_type, calls, early

    return low_chars, high_chars, last_success_tokens, limit_type, calls, None


def do_binary_search(api_name, call_fn, content, expected_context, log, pbar=None, initial_high_chars=None):
    """
    两阶段二分查找。

    call_fn(text) -> (success: bool, tokens: int | None, err_type: str | None)
    err_type: 'context' | 'proxy' | 'overload' | 'unsupported' | 'unknown'

    返回: {"max_tokens": int | None, "limit_type": str, "calls": int}
    """
    high_chars = initial_high_chars if initial_high_chars else len(content)
    low_chars = 0
    last_success_tokens = None
    limit_type = "model"
    calls = 0

    # 第一阶段：粗搜，快速定位大致边界
    low_chars, high_chars, last_success_tokens, limit_type, calls, early = _binary_search_phase(
        api_name, call_fn, content, low_chars, high_chars,
        threshold=5000, calls=calls, limit_type=limit_type,
        last_success_tokens=last_success_tokens, log=log, pbar=pbar
    )
    if early is not None:
        return early

    # 第二阶段：精搜，在粗搜收敛的区间内继续缩小，误差约 10 tokens
    if pbar is None:
        log(f"  [{api_name}] 粗搜完成，进入精搜...")
    low_chars, high_chars, last_success_tokens, limit_type, calls, early = _binary_search_phase(
        api_name, call_fn, content, low_chars, high_chars,
        threshold=40, calls=calls, limit_type=limit_type,
        last_success_tokens=last_success_tokens, log=log, pbar=pbar
    )
    if early is not None:
        return early

    return {"max_tokens": last_success_tokens, "limit_type": limit_type, "calls": calls}


# ── 提供商特定的探测实现 ──────────────────────────────────────────────────────

def probe_anthropic_context(client, model_name, content, expected_context, log, pbar=None):
    """Anthropic 提供商的上下文探测实现（指数搜索策略）。"""
    result = {}

    # count_tokens: 验证测试内容的 token 数
    verify_size = min(len(content), expected_context * 6)
    if pbar is None:
        log(f"  [count_tokens] 验证测试内容 token 数（样本: {verify_size:,} 字符）...")
    else:
        print(f"\n⏺ 验证token阶段", file=sys.stderr)
        print(f"  ⎿ 样本大小: {verify_size:,} chars", file=sys.stderr)

    ct_call = make_count_tokens_call(client, model_name)
    success, tokens, err_type = ct_call(content[:verify_size])

    if success:
        if pbar is not None:
            print(f"     ✓ 验证成功: {tokens:,} tokens", file=sys.stderr)
        else:
            log(f"  [count_tokens] 样本共 {tokens:,} tokens，测试内容足够")
        result["count_tokens"] = {"sample_tokens": tokens, "sample_size": verify_size, "verified": True}
    else:
        if pbar is not None:
            print(f"     ✗ 验证失败: {err_type}", file=sys.stderr)
        else:
            log(f"  [count_tokens] 验证失败: {err_type}")
        result["count_tokens"] = {"sample_tokens": None, "verified": False, "error": err_type}

    # 指数探测（Exponential/Galloping Search）
    call_fn = make_messages_create_call(client, model_name)
    probe_ratios = [0.25, 0.5, 0.75, 1.0]
    last_success_size = 0
    last_success_tokens = None
    calls = 0

    if pbar is not None:
        print(f"\n⏺ 指数探测阶段", file=sys.stderr)
    else:
        log(f"  [messages.create] 指数探测阶段...")

    for ratio in probe_ratios:
        probe_size = min(len(content), int(expected_context * ratio * 4))
        calls += 1
        if pbar is not None:
            print(f"  ⎿ 测试 {int(ratio*100)}%: {probe_size:,} chars", file=sys.stderr, end='', flush=True)
        success, tokens, err_type = call_fn(content[:probe_size])

        if success:
            last_success_size = probe_size
            last_success_tokens = tokens
            if pbar is not None:
                print(f" → ✓ {tokens:,} tokens", file=sys.stderr)
            else:
                log(f"  [messages.create] {probe_size:,} chars ({ratio:.2f}×) -> {tokens:,} tokens OK")
        else:
            if pbar is not None:
                print(f" → ✗ {err_type}", file=sys.stderr)
                if last_success_tokens:
                    print(f"     找到范围上限: ~{last_success_tokens:,} tokens", file=sys.stderr)
            else:
                log(f"  [messages.create] {probe_size:,} chars ({ratio:.2f}×) -> FAIL ({err_type})")
            if err_type not in ("context", "overload"):
                result["messages_create"] = {"max_tokens": last_success_tokens, "limit_type": err_type, "calls": calls}
                return result
            break

    # 二分查找阶段
    if last_success_size > 0:
        if pbar is not None:
            print(f"\n⏺ 二分搜索阶段", file=sys.stderr)
            print(f"  ⎿ 搜索范围: {last_success_size:,} – {len(content):,} chars", file=sys.stderr)
        else:
            log(f"  [messages.create] 二分查找阶段: {last_success_size:,} – {len(content):,} 字符")

        mc_result = do_binary_search(
            "messages.create",
            call_fn,
            content, expected_context, log, pbar
        )
        if pbar is not None:
            print(f"     ✓ 完成: {mc_result.get('max_tokens', 0):,} tokens", file=sys.stderr)
        mc_result["calls"] += calls
        result["messages_create"] = mc_result
    else:
        result["messages_create"] = {"max_tokens": None, "limit_type": "context", "calls": calls}

    return result


def probe_openai_context(client, model_name, content, expected_context, log, provider_cfg=None, pbar=None):
    """OpenAI 提供商的上下文探测实现（指数搜索策略）。"""
    result = {}

    if pbar is not None:
        pbar.set_description("测试OpenAI模型")

    # 获取配置参数
    api_type = provider_cfg.get("api_type", "chat_completions") if provider_cfg else "chat_completions"
    client_type = provider_cfg.get("client_type", "http") if provider_cfg else "http"

    # tiktoken: 本地 token 计数验证
    ct_call = make_openai_count_tokens_call(model_name)
    if ct_call:
        verify_size = min(len(content), expected_context * 6)
        log(f"  [tiktoken] 验证测试内容 token 数（样本: {verify_size:,} 字符）...")
        success, tokens, err_type = ct_call(content[:verify_size])
        if success:
            log(f"  [tiktoken] 样本共 {tokens:,} tokens，测试内容足够")
            result["count_tokens"] = {"sample_tokens": tokens, "sample_size": verify_size, "verified": True}
        else:
            log(f"  [tiktoken] 验证失败: {err_type}")
            result["count_tokens"] = {"sample_tokens": None, "verified": False, "error": err_type}
    else:
        result["count_tokens"] = None

    # 根据 client_type 和 api_type 选择调用函数
    if client_type == "http":
        base_url = provider_cfg.get("base_url", "https://api.openai.com/v1") if provider_cfg else "https://api.openai.com/v1"
        api_key = provider_cfg.get("api_key", "") if provider_cfg else ""
        headers = provider_cfg.get("headers", {}) if provider_cfg else {}

        if api_type == "responses":
            call_fn = make_openai_http_responses_call(base_url, api_key, model_name, headers)
            api_name = "responses"
        else:
            call_fn = make_openai_http_chat_call(base_url, api_key, model_name, headers)
            api_name = "chat.completions"
    else:  # SDK mode
        if api_type == "responses":
            call_fn = make_openai_responses_call(client, model_name)
            api_name = "responses"
        else:
            call_fn = make_openai_chat_call(client, model_name)
            api_name = "chat.completions"

    # 指数探测（Exponential/Galloping Search）：快速确定范围
    if pbar is not None:
        pbar.set_description("指数探测阶段")
    probe_ratios = [0.25, 0.5, 0.75, 1.0]
    last_success_size = 0
    last_success_tokens = None
    calls = 0

    log(f"  [{api_name}] 指数探测阶段...")
    for ratio in probe_ratios:
        probe_size = min(len(content), int(expected_context * ratio * 4))
        calls += 1
        success, tokens, err_type = call_fn(content[:probe_size])

        if success:
            last_success_size = probe_size
            last_success_tokens = tokens
            log(f"  [{api_name}] {probe_size:,} chars ({ratio:.2f}×) -> {tokens:,} tokens OK")
        else:
            log(f"  [{api_name}] {probe_size:,} chars ({ratio:.2f}×) -> FAIL ({err_type})")
            if err_type not in ("context", "overload"):
                result["messages_create"] = {"max_tokens": last_success_tokens, "limit_type": err_type, "calls": calls}
                return result
            break

    # 二分查找阶段：在确定的范围内精确搜索
    if last_success_size > 0:
        if pbar is not None:
            pbar.set_description("二分搜索阶段")
        if pbar is None:
            log(f"  [{api_name}] 二分查找阶段: {last_success_size:,} – {min(len(content), expected_context * 5):,} 字符")
        chat_result = do_binary_search(
            api_name,
            call_fn,
            content, expected_context, log, pbar,
            initial_high_chars=min(len(content), expected_context * 5)
        )
        chat_result["calls"] += calls
        result["messages_create"] = chat_result
    else:
        result["messages_create"] = {"max_tokens": None, "limit_type": "context", "calls": calls}

    return result


# ── 模型测试 ──────────────────────────────────────────────────────────────────

def test_model(client, provider_type, provider_name, model_cfg, content, lock, provider_cfg=None, pbar=None):
    model_name = model_cfg["name"]
    display_name = f"{provider_name}/{model_name}"
    expected_context = model_cfg.get("expected_context", 200000)

    def log(msg):
        with lock:
            if pbar is not None:
                tqdm.write(msg, file=sys.stderr)
            else:
                print(msg, flush=True)

    if pbar is not None:
        pbar.set_description(f"测试 {display_name}")

    log(f"\n[{display_name}] 开始测试（expected_context={expected_context:,}）")

    result = {
        "model": model_name,
        "provider": provider_name,
        "display_name": display_name,
    }

    if provider_type == "anthropic":
        result.update(probe_anthropic_context(client, model_name, content, expected_context, log, pbar))
    elif provider_type == "openai":
        result.update(probe_openai_context(client, model_name, content, expected_context, log, provider_cfg, pbar))

    log(f"[{display_name}] 测试完成")
    return result


# ── 报告格式化 ────────────────────────────────────────────────────────────────

def format_result(result):
    if result is None:
        return "—"

    # count_tokens 验证结果
    if "sample_tokens" in result:
        if result.get("verified"):
            return f"{result['sample_tokens']:,} tokens (样本)"
        else:
            return f"验证失败 ({result.get('error', 'unknown')})"

    # messages.create 测试结果
    limit_type = result.get("limit_type", "unknown")
    if limit_type == "unsupported":
        return "不支持 (404)"
    max_tokens = result.get("max_tokens")
    if max_tokens is None:
        return "超时/过载，未完成"
    s = f"{max_tokens:,} tokens"
    if result.get("incomplete"):
        s += " (可能偏低，未完成)"
    if limit_type == "proxy":
        s += " (proxy limit)"
    return s


def print_table(results):
    col1_label = "模型"
    col2_label = "测试内容 (count_tokens)"
    col3_label = "实际上下文窗口 (messages.create)"

    all_c1 = [col1_label] + [r["display_name"] for r in results]
    all_c2 = [col2_label] + [format_result(r.get("count_tokens")) for r in results]
    all_c3 = [col3_label] + [format_result(r.get("messages_create")) for r in results]

    w1 = max(str_width(s) for s in all_c1) + 2
    w2 = max(str_width(s) for s in all_c2) + 2
    w3 = max(str_width(s) for s in all_c3) + 2

    def hline(left, mid_ch, right):
        return left + "─" * (w1 + 1) + mid_ch + "─" * (w2 + 1) + mid_ch + "─" * (w3 + 1) + right

    def data_row(c1, c2, c3):
        return "│ " + ljust_w(c1, w1 - 1) + "│ " + ljust_w(c2, w2 - 1) + "│ " + ljust_w(c3, w3 - 1) + "│"

    print("\n" + hline("┌", "┬", "┐"))
    print(data_row(col1_label, col2_label, col3_label))
    print(hline("├", "┼", "┤"))
    for r in results:
        print(data_row(r["display_name"], format_result(r.get("count_tokens")), format_result(r.get("messages_create"))))
    print(hline("└", "┴", "┘"))
    print()


def save_report(results, providers_summary, report_file):
    clean_results = []
    for r in results:
        cr = {"provider": r["provider"], "model": r["model"]}
        for key in ("count_tokens", "messages_create"):
            val = r.get(key)
            if val is not None:
                cr[key] = {k: v for k, v in val.items() if k != "incomplete"}
            else:
                cr[key] = None
        clean_results.append(cr)

    report = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "providers": providers_summary,
        "results": clean_results,
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"报告已保存至 {report_file}")


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="模型上下文窗口测试工具")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--api-key", help="API Key（覆盖配置文件，仅旧格式生效）")
    parser.add_argument("--base-url", help="Base URL（覆盖配置文件，仅旧格式生效）")
    args = parser.parse_args()

    # 智能查找配置文件
    if args.config:
        config_path = args.config
    else:
        # 优先使用 .jsonc，不存在则使用 .json
        if os.path.exists("context_config.jsonc"):
            config_path = "context_config.jsonc"
        else:
            config_path = "context_config.json"

    config = load_config(config_path)
    providers = load_providers(args, config)
    report_file = config.get("report_file", "context_report.json")

    # 如果指定了配置文件，报告文件相对于配置文件目录
    if args.config:
        config_dir = os.path.dirname(os.path.abspath(config_path))
        if not os.path.isabs(report_file):
            report_file = os.path.join(config_dir, report_file)

    # 收集所有 models
    all_models = []
    for prov_cfg in providers.values():
        all_models.extend(prov_cfg.get("models", []))

    if not all_models:
        print("错误: 未配置任何模型。")
        sys.exit(1)

    # 动态生成测试内容（根据最大 expected_context 计算）
    print("\n生成测试内容...")
    max_expected = max(m.get("expected_context", 200000) for m in all_models)
    # 约 6 chars = 1 token，生成 3 倍的余量以探测真实上限
    content_size = int(max_expected * 6 * 3.0)
    content = "hello world\n" * (content_size // 12 + 1)
    content = content[:content_size]  # 精确截断
    print(f"已生成 {len(content):,} 字符（基于最大 expected_context {max_expected:,} tokens）")

    # 创建各 provider 客户端并收集任务
    tasks = []  # (client, provider_type, provider_name, model_cfg, provider_cfg)
    providers_summary = {}
    for prov_name, prov_cfg in providers.items():
        prov_type = prov_cfg.get("type", "anthropic")
        client = create_client(prov_type, prov_cfg)
        providers_summary[prov_name] = {
            "type": prov_type,
            "base_url": prov_cfg.get("base_url") or "(default)",
            "models": [m["name"] for m in prov_cfg.get("models", [])],
        }
        for model_cfg in prov_cfg.get("models", []):
            tasks.append((client, prov_type, prov_name, model_cfg, prov_cfg))

    print(f"\n开始并发测试 {len(tasks)} 个模型（来自 {len(providers)} 个 provider）...\n")
    lock = threading.Lock()
    results = []
    task_order = {(t[2], t[3]["name"]): i for i, t in enumerate(tasks)}

    # 为单个模型创建进度条（spinner 旋转字符样式）
    single_model_pbar = None
    if HAS_TQDM and len(tasks) == 1:
        single_model_pbar = tqdm(
            total=0,
            desc="准备测试",
            bar_format='{desc} {postfix}',
            disable=False,
            file=sys.stderr
        )

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(test_model, client, prov_type, prov_name, model_cfg, content, lock, prov_cfg, single_model_pbar): (prov_name, model_cfg)
            for client, prov_type, prov_name, model_cfg, prov_cfg in tasks
        }

        # 使用进度条显示测试进度（仅在多个模型时）
        iterator = as_completed(futures)
        if HAS_TQDM and len(futures) > 1:
            iterator = tqdm(iterator, total=len(futures), desc="测试进度", unit="模型")

        for future in iterator:
            prov_name, model_cfg = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                display = f"{prov_name}/{model_cfg['name']}"
                print(f"[{display}] 线程异常: {e}")
                results.append({
                    "model": model_cfg["name"],
                    "provider": prov_name,
                    "display_name": display,
                    "count_tokens": None,
                    "messages_create": None,
                })

    # 关闭单个模型进度条
    if single_model_pbar is not None:
        single_model_pbar.close()

    results.sort(key=lambda r: task_order.get((r["provider"], r["model"]), 999))
    print_table(results)
    save_report(results, providers_summary, report_file)


if __name__ == "__main__":
    main()
