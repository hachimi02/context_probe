---
name: context-probe
version: 1.0.0
description: Test the actual context window size of AI models configured in your current client (Claude Code, Cursor, Continue). Use when the user wants to verify model context limits, validate client configuration, or compare declared vs actual context sizes.
---

# Context Probe

Test the real context window limits of AI models in your current client configuration.

## Instructions

### 1. Ask User to Choose Mode

Present two options:
1. **Use current client configuration** - Auto-discover from Claude Code/Cursor/Continue
2. **Custom configuration** - Manually specify API details

### 2A. Current Client Mode

**Discover configuration files (priority order):**
- Search priority: `~/.claude/settings.json`, `~/.claude/config.json`, `./.claude/`, `~/.cursor/`, `./.cursor/`, `~/.continue/`, `./.continue/`
- Read JSON/JSONC files (config.json, settings.json, etc.)

**Extract information:**
- API key: `env.ANTHROPIC_AUTH_TOKEN`, `apiKey`, `api_key`, `ANTHROPIC_AUTH_TOKEN`
- Base URL: `env.ANTHROPIC_BASE_URL`, `baseURL`, `base_url`, `ANTHROPIC_BASE_URL`
- Provider: `provider`, `type` (anthropic/openai)
- Model: `model`, `models` (e.g., "claude-sonnet-4-6", "sonnet[1m]", "opus[1m]")

**Show extracted config to user and ask for confirmation.**

### 2B. Custom Configuration Mode

**Ask user to provide:**
1. Provider type (anthropic/openai)
2. API key
3. Base URL (type 'default' for https://api.anthropic.com, or provide custom URL)
4. Model name(s) to test
5. Expected context size (type 'default' for 200000, or provide custom value)
6. Client name (e.g., claude-code, cursor, or type 'skip' to omit headers)
7. Client version (if client name provided)

### 3. Convert to Test Configuration

Create a configuration file for `context_probe.py`:

```json
{
  "test_file": "test.txt",
  "report_file": "context_report.json",
  "providers": {
    "<provider_name>": {
      "type": "anthropic",
      "api_key": "<extracted_key>",
      "base_url": "<extracted_url_or_empty>",
      "headers": {
        "x-anthropic-billing-header": "cc_version=<version>; cc_entrypoint=cli; cch=<hash>;",
        "User-Agent": "<Client-Name>/<version>"
      },
      "models": [
        {"name": "<model_name>", "expected_context": <tokens>}
      ]
    }
  }
}
```

**Client identification (REQUIRED for current client mode):**

Always detect the client type and add headers:

- **Claude Code**: Extract version from config, use format:
  - `x-anthropic-billing-header: "cc_version=<version>; cc_entrypoint=cli; cch=<hash>;"`
  - `User-Agent: "Claude-Code/<version>"`
- **Cursor/Continue**: Use similar format with appropriate client name
- **Custom mode**: Default to adding headers; only skip if user explicitly leaves client name empty

**1M context support:**

If model name contains `[1m]` or expected_context >= 1000000, add:
- `"anthropic-beta": "context-1m-2025-08-07"`

**Model name normalization:**
- `sonnet[1m]` → `claude-sonnet-4-6`
- `opus[1m]` → `claude-opus-4-6`
- Use defaults for expected_context: 200000 for Claude models, 128000 for GPT-4

**Ask the user:**
- Which models to test (if multiple found)
- Confirm before running (tests consume API credits)

### 4. Run Test

Execute: `python context_probe.py --config <generated_config.json>`

Monitor progress and report errors (API key invalid, network issues, etc.).

**If initial probe fails with context error:**
- The expected_context may be too high
- Automatically retry with conservative default (200K for Claude, 128K for others)
- This ensures finding the actual limit even when expected value is incorrect

### 5. Analyze Results

Read `context_report.json` and display results in a table:

```
Provider/Model          | Expected   | Actual     | Diff    | Status
------------------------|------------|------------|---------|-------
anthropic/claude-4-6    | 200K       | 195K       | -2.5%   | ✓
```

**Status indicators:**
- ✓ Actual ≥ 95% expected
- ⚠️ Actual < 95% expected (suggest checking config)
- ❌ Test failed (show error)

## Error Handling

- No config found → Ask user to specify config path
- Invalid API key → Prompt to check configuration
- Network error → Suggest checking proxy/connection
- Model unsupported → Mark as unsupported, continue with others

## Dependencies

Check before running:
- `anthropic` SDK (for Anthropic models)
- `openai` or `requests` (for OpenAI-compatible models)

If missing: `pip install anthropic openai requests`
