#!/bin/bash
# Install context-probe skill from GitHub

REPO="hachimi02/context_probe"
VERSION="${1:-main}"
BASE_URL="https://raw.githubusercontent.com/$REPO/$VERSION"

echo "Installing context-probe skill from GitHub..."
echo "Version: $VERSION"
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

# Create directory
mkdir -p "$SKILL_DIR"

# Download files
echo ""
echo "Downloading files..."

FILES=("SKILL.md" "context_probe.py" "context_config.jsonc.template")

for file in "${FILES[@]}"; do
    echo "  - $file"
    if command -v curl &> /dev/null; then
        curl -fsSL "$BASE_URL/$file" -o "$SKILL_DIR/$file"
    elif command -v wget &> /dev/null; then
        wget -q "$BASE_URL/$file" -O "$SKILL_DIR/$file"
    else
        echo "Error: curl or wget required"
        exit 1
    fi

    if [ $? -ne 0 ]; then
        echo "Error downloading $file"
        exit 1
    fi
done

echo ""
echo "✓ Skill installed to: $SKILL_DIR"
echo ""
echo "Usage: Type '/context-probe' in your AI client"
