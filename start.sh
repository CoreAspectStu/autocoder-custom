#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  Autonomous Coding Agent"
echo "========================================"
echo ""

# Check if Claude CLI is installed
if ! command -v claude &> /dev/null; then
    echo "[ERROR] Claude CLI not found"
    echo ""
    echo "Please install Claude CLI first:"
    echo "  curl -fsSL https://claude.ai/install.sh | bash"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "[OK] Claude CLI found"

# Check if user has credentials
CLAUDE_CREDS="$HOME/.claude/.credentials.json"
if [ -f "$CLAUDE_CREDS" ]; then
    echo "[OK] Claude credentials found"
else
    echo "[!] Not authenticated with Claude"
    echo ""
    echo "You need to run 'claude login' to authenticate."
    echo "This will open a browser window to sign in."
    echo ""
    read -p "Would you like to run 'claude login' now? (y/n): " LOGIN_CHOICE

    if [[ "$LOGIN_CHOICE" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Running 'claude login'..."
        echo "Complete the login in your browser, then return here."
        echo ""
        claude login

        # Check if login succeeded
        if [ -f "$CLAUDE_CREDS" ]; then
            echo ""
            echo "[OK] Login successful!"
        else
            echo ""
            echo "[ERROR] Login failed or was cancelled."
            echo "Please try again."
            exit 1
        fi
    else
        echo ""
        echo "Please run 'claude login' manually, then try again."
        exit 1
    fi
fi

echo ""

# Check if venv exists with correct structure for this platform
# Windows venvs have Scripts/, Linux/macOS have bin/
if [ ! -f "venv/bin/activate" ]; then
    if [ -d "venv" ]; then
        echo "[INFO] Detected incompatible virtual environment (possibly created on Windows)"
        echo "[INFO] Recreating virtual environment for this platform..."
        rm -rf venv
        if [ -d "venv" ]; then
            echo "[ERROR] Failed to remove existing virtual environment"
            echo "Please manually delete the 'venv' directory and try again:"
            echo "  rm -rf venv"
            exit 1
        fi
    else
        echo "Creating virtual environment..."
    fi
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment"
        echo "Please ensure the venv module is installed:"
        echo "  Ubuntu/Debian: sudo apt install python3-venv"
        echo "  Or try: python3 -m ensurepip"
        exit 1
    fi
fi

# Activate the virtual environment
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to activate virtual environment"
    echo "The venv may be corrupted. Try: rm -rf venv && ./start.sh"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Run the app
python start.py
