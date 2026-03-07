# Agent Installation Guide for context-probe Skill

This document provides instructions for AI agents (Claude Code, Cursor, etc.) to install the context-probe skill.

## Installation Task

Install the context-probe skill to enable context window testing functionality.

## Required Files

Download these files from the repository:
1. `SKILL.md` - Skill definition and instructions
2. `context_probe.py` - Main testing script
3. `context_config.jsonc.template` - Configuration template (optional)

## Installation Steps

### 1. Choose Installation Location

Ask the user to choose one of:
- **Project-level**: `.claude/skills/context-probe/` (current project only)
- **User-level**: `~/.claude/skills/context-probe/` (all projects)
- **Custom path**: User-specified directory

### 2. Create Directory Structure

```bash
mkdir -p <chosen-path>/context-probe
```

### 3. Download and Save Files

For each required file:
- Fetch from: `https://raw.githubusercontent.com/hachimi02/context_probe/main/<filename>`
- Save to: `<chosen-path>/context-probe/<filename>`

Example commands:
```bash
cd <chosen-path>/context-probe
curl -O https://raw.githubusercontent.com/hachimi02/context_probe/main/SKILL.md
curl -O https://raw.githubusercontent.com/hachimi02/context_probe/main/context_probe.py
curl -O https://raw.githubusercontent.com/hachimi02/context_probe/main/context_config.jsonc.template
```

### 4. Verify Installation

Check that these files exist:
- `<chosen-path>/context-probe/SKILL.md`
- `<chosen-path>/context-probe/context_probe.py`

### 5. Confirm to User

Report installation location and version:
```
✓ context-probe skill installed successfully
  Location: <chosen-path>/context-probe
  Version: <extract from SKILL.md>

You can now use it by asking me to test context windows.
```

## Usage After Installation

The skill can be triggered by user requests like:
- "test my context window"
- "probe context limit"
- "/context-probe"

## Dependencies

The skill requires Python packages (installed on first use):
- `anthropic` - For Anthropic models
- `openai` or `requests` - For OpenAI-compatible providers

## Troubleshooting

If installation fails:
1. Check network connectivity to GitHub
2. Verify write permissions to installation directory
3. Suggest manual installation via `install_skill.sh` script
