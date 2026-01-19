#!/bin/bash
#
# Apply Remote Access Patches
# ===========================
# Re-applies our customizations after upstream updates.
# Run this if `git pull` overwrites server/main.py or server/routers/__init__.py
#
# Usage: ./patches/apply-remote-access.sh
#

set -e
cd "$(dirname "$0")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[SKIP]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "Applying remote access patches..."
echo ""

# 1. Check if status.py exists
if [ ! -f "server/routers/status.py" ]; then
    log_error "server/routers/status.py not found!"
    log_error "Copy it from docs/remote-server-setup.md or restore from git"
    exit 1
fi
log_info "server/routers/status.py exists"

# 2. Patch server/routers/__init__.py
INIT_FILE="server/routers/__init__.py"
if grep -q "status_router" "$INIT_FILE"; then
    log_warn "status_router already in $INIT_FILE"
else
    # Add import after spec_creation import
    sed -i '/from .spec_creation import/a from .status import router as status_router' "$INIT_FILE"
    # Add to __all__ before terminal_router
    sed -i '/"terminal_router",/i\    "status_router",' "$INIT_FILE"
    log_info "Patched $INIT_FILE"
fi

# 3. Patch server/main.py
MAIN_FILE="server/main.py"
if grep -q "status_router" "$MAIN_FILE"; then
    log_warn "status_router already in $MAIN_FILE"
else
    # Add import (after spec_creation_router in import block)
    sed -i '/spec_creation_router,/a\    status_router,' "$MAIN_FILE"
    # Add include (after terminal_router include)
    sed -i '/app.include_router(terminal_router)/a app.include_router(status_router)' "$MAIN_FILE"
    log_info "Patched $MAIN_FILE"
fi

# 4. Check template (optional - just report)
TEMPLATE="\.claude/templates/app_spec.template.txt"
if grep -q "4000-4099" "$TEMPLATE" 2>/dev/null; then
    log_info "Template has port range note"
else
    log_warn "Template may need port range update (4000-4099)"
fi

# 5. Check remote-start.sh exists
if [ -x "remote-start.sh" ]; then
    log_info "remote-start.sh exists and is executable"
else
    log_warn "remote-start.sh missing or not executable"
fi

echo ""
echo -e "${GREEN}Done!${NC} Restart the server: ./remote-start.sh stop && ./remote-start.sh ui"
