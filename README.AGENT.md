# Agent Installation Guide for context-probe Skill

This document provides instructions for AI agents (Claude Code, Cursor, etc.) to install the context-probe skill.

## Quick Installation (Recommended)

The easiest way is using the remote installation script:

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/hachimi02/context_probe/main/install_from_github.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/hachimi02/context_probe/main/install_from_github.bat | iex
```

**Note**: These scripts require interactive input to choose installation location. If you cannot handle interactive prompts, use the manual method below.

## Manual Installation for Agents

### Step 1: Ask User for Installation Location

Present these options:
1. **Project-level**: `.claude/skills/context-probe` (current project only)
2. **User-level**: `~/.claude/skills/context-probe` (available in all projects)
3. **Custom path**: User specifies a directory

**Important**: The path should end with `/context-probe`, not `/context-probe/context-probe`.

### Step 2: Create Directory

**Linux/macOS:**
```bash
mkdir -p <installation-path>
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force -Path <installation-path>
```

Examples:
- Project: `mkdir -p .claude/skills/context-probe` (Linux/macOS) or `New-Item -ItemType Directory -Force -Path .claude\skills\context-probe` (Windows)
- User: `mkdir -p ~/.claude/skills/context-probe` (Linux/macOS) or `New-Item -ItemType Directory -Force -Path $env:USERPROFILE\.claude\skills\context-probe` (Windows)

### Step 3: Download Required Files

Download these files to the installation directory:

**Required files:**
1. `SKILL.md` - Skill definition and instructions
2. `context_probe.py` - Main testing script

**Optional file:**
3. `context_config.jsonc.template` - Configuration template

**Download commands:**

**Linux/macOS:**
```bash
cd <installation-path>
curl -fsSL https://raw.githubusercontent.com/hachimi02/context_probe/main/SKILL.md -o SKILL.md
curl -fsSL https://raw.githubusercontent.com/hachimi02/context_probe/main/context_probe.py -o context_probe.py
curl -fsSL https://raw.githubusercontent.com/hachimi02/context_probe/main/context_config.jsonc.template -o context_config.jsonc.template
```

**Windows (PowerShell):**
```powershell
cd <installation-path>
Invoke-WebRequest -Uri https://raw.githubusercontent.com/hachimi02/context_probe/main/SKILL.md -OutFile SKILL.md
Invoke-WebRequest -Uri https://raw.githubusercontent.com/hachimi02/context_probe/main/context_probe.py -OutFile context_probe.py
Invoke-WebRequest -Uri https://raw.githubusercontent.com/hachimi02/context_probe/main/context_config.jsonc.template -OutFile context_config.jsonc.template
```

### Step 4: Verify Installation

Check that required files exist:

**Linux/macOS:**
```bash
test -f <installation-path>/SKILL.md && test -f <installation-path>/context_probe.py && echo "✓ Installation successful"
```

**Windows (PowerShell):**
```powershell
if ((Test-Path <installation-path>\SKILL.md) -and (Test-Path <installation-path>\context_probe.py)) { Write-Host "✓ Installation successful" }
```

### Step 5: Confirm to User

Extract version from SKILL.md and report:
```
✓ context-probe skill installed successfully
  Location: <installation-path>
  Version: <extract from SKILL.md frontmatter>

You can now use it by asking me to test context windows.
```

## Usage After Installation

The skill can be triggered by:
- "test my context window"
- "probe context limit"
- "/context-probe"

## Dependencies

Python packages (auto-installed on first use):
- `anthropic` - For Anthropic models
- `openai` or `requests` - For OpenAI-compatible providers

## Troubleshooting

If installation fails:
1. Check network connectivity to GitHub
2. Verify write permissions to installation directory
3. Try the interactive script: `curl -fsSL https://raw.githubusercontent.com/hachimi02/context_probe/main/install_from_github.sh | bash`

