# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A tool that probes the actual context window limits of LLM models by binary-searching with real API calls. It supports Anthropic and OpenAI-compatible providers (OpenAI, DeepSeek, Kimi, etc.) and saves results to a JSON report.

## Running the Tool

```bash
# Run with interactive prompts (legacy flat config)
python context_probe.py

# Run with config file (default: context_config.json)
python context_probe.py --config context_config.json

# Override config values on the command line (legacy flat config only)
python context_probe.py --api-key sk-... --base-url https://api.anthropic.com
```

## Configuration

Copy `context_config.json.template` to `context_config.json` and fill in your API keys.

### New multi-provider format (recommended)

```json
{
  "test_file": "test.txt",
  "report_file": "context_report.json",
  "providers": {
    "anthropic": {
      "type": "anthropic",
      "api_key": "sk-ant-...",
      "base_url": "",
      "models": [
        { "name": "claude-sonnet-4-6", "expected_context": 1000000 }
      ]
    },
    "deepseek": {
      "type": "openai",
      "api_key": "sk-...",
      "base_url": "https://api.deepseek.com",
      "models": [
        { "name": "deepseek-chat", "expected_context": 128000 }
      ]
    }
  }
}
```

- `providers` — Dict of named providers. Each provider has:
  - `type` — `"anthropic"` or `"openai"` (OpenAI-compatible)
  - `api_key` — Provider API key
  - `base_url` — API endpoint (leave empty for default)
  - `client_type` — (OpenAI only) `"http"` (default) or `"sdk"`. HTTP mode uses direct requests for better proxy compatibility
  - `api_type` — (OpenAI only) `"chat_completions"` (default) or `"responses"`
  - `models` — List of `{"name": "<model-id>", "expected_context": <tokens>}` objects
- `test_file` — Path to the large text file used as filler content (auto-generated if missing)
- `report_file` — Where to write the JSON results (default: `context_report.json`)

### Legacy flat format (backward compatible)

The old flat format with top-level `api_key`, `base_url`, and `models` still works. It is treated as a single Anthropic provider. `--api-key` and `--base-url` CLI args only apply to this format.

## Architecture

The tool has one Python file (`context_probe.py`) with a clear layered structure:

1. **Conditional SDK imports** — `anthropic` and `openai` are imported via try/except; users only need the SDK for providers they use
2. **Config loading** (`load_config`, `load_providers`) — resolves settings from CLI args, JSON config, and environment; `load_providers` handles both new multi-provider format and legacy flat format
3. **Test file management** (`ensure_test_file`, `generate_test_file`) — auto-generates a large `test.txt` (~1.2× the largest `expected_context` in characters) if absent
4. **Error classification** (`_classify_exception_anthropic`, `_classify_exception_openai`) — map SDK exceptions to error_type strings (context/proxy/overload/unsupported/unknown)
5. **API call wrappers** (`make_count_tokens_call`, `make_messages_create_call`, `make_openai_chat_call`, `make_openai_http_chat_call`, `make_openai_http_responses_call`) — return closures that call the respective endpoints and normalize results to `(success, tokens, err_type)`. HTTP wrappers use requests library for better proxy compatibility
6. **Client factory** (`create_client`) — creates `anthropic.Anthropic` or `openai.OpenAI` based on provider type
7. **Binary search** (`do_binary_search`) — two-phase search: coarse (5000-char threshold) then fine (40-char threshold); handles retries on overload, stops on proxy/unknown errors
8. **Concurrent model testing** (`test_model`) — Anthropic providers run count_tokens + messages.create; OpenAI providers run only chat.completions; `main()` fans out across all providers and models using `ThreadPoolExecutor`
9. **Reporting** (`print_table`, `save_report`) — renders a Unicode box-drawing table to stdout (model column shows `provider/model`) and writes `context_report.json` with provider metadata

The `str_width`/`ljust_w` helpers account for CJK double-width characters in table alignment.

## Dependencies

Install SDKs for the providers you want to test:

```bash
pip install anthropic   # For Anthropic models
pip install openai      # For OpenAI-compatible providers (SDK mode)
pip install requests    # For HTTP client mode (default, recommended)
pip install tiktoken    # Optional: local token counting for OpenAI models
```

## Skill Development Workflow

This project includes a Claude Code skill (`SKILL.md`) that provides an interactive interface for testing context windows.

### Project Structure

```
context_probe/
├── SKILL.md              # Skill source file (tracked in git)
├── install_skill.sh      # Unix/Linux installation script
├── install_skill.bat     # Windows installation script
├── context_probe.py      # Main testing tool
└── .claude/
    └── skills/
        └── context-probe/  # Installed skill (gitignored)
```

### Development Process

1. **Edit source files**: Modify `SKILL.md` in project root (not in `.claude/`)
2. **Install for testing**: Run `./install_skill.sh` or `install_skill.bat`
3. **Test the skill**: Use Claude Code to invoke the skill
4. **Commit changes**: Only commit source files (SKILL.md, scripts)

### Testing the Skill

```bash
# Install skill locally
./install_skill.sh

# In Claude Code, trigger the skill by asking:
# "test my context window" or "probe context limit"
```

The skill will:
- Auto-discover configuration from `~/.claude/settings.json`
- Extract API key, base URL, and model settings
- Generate proper client identification headers
- Run context window tests
- Report results with status indicators
