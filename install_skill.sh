#!/bin/bash
# Install context-probe skill to Claude Code

SOURCE_DIR="."
SOURCE_FILE="SKILL.md"

echo "Installing context-probe skill..."
echo ""
echo "Choose installation location:"
echo "  1) Current project (.claude/skills/)"
echo "  2) User home (~/.claude/skills/)"
echo "  3) Custom path"
echo ""
read -p "Enter choice [1-3]: " -n 1 -r
echo ""

case $REPLY in
    1)
        SKILL_DIR=".claude/skills/context-probe"
        ;;
    2)
        SKILL_DIR="$HOME/.claude/skills/context-probe"
        ;;
    3)
        read -p "Enter custom path: " CUSTOM_PATH
        SKILL_DIR="$CUSTOM_PATH/context-probe"
        ;;
    *)
        echo "Invalid choice. Installation cancelled."
        exit 1
        ;;
esac

TARGET_FILE="$SKILL_DIR/SKILL.md"

# Extract version from source
SOURCE_VERSION=$(grep "^version:" "$SOURCE_FILE" | sed 's/version: *//')

# Check if skill already exists
if [ -f "$TARGET_FILE" ]; then
    TARGET_VERSION=$(grep "^version:" "$TARGET_FILE" | sed 's/version: *//')
    echo ""
    echo "Skill already installed at: $SKILL_DIR"
    echo "Installed version: $TARGET_VERSION"
    echo "New version: $SOURCE_VERSION"
    echo ""
    read -p "Overwrite existing skill? [y/N] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        exit 0
    fi
fi

# Create skills directory
mkdir -p "$SKILL_DIR"

# Copy skill files
cp SKILL.md context_probe.py context_config.jsonc.template "$SKILL_DIR/"

echo ""
echo "✓ Skill installed to: $SKILL_DIR"
echo "  Version: $SOURCE_VERSION"
echo ""
echo "You can now use it by asking Claude to test context windows"
