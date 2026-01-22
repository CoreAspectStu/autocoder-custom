#!/bin/bash
#
# Apply Remote Access Patches
# ===========================
# Re-applies our customizations after upstream updates.
# Run this after `git pull` to restore custom functionality.
#
# Patches applied:
# 1. Status router integration (status.py)
# 2. Port assignment system (4000-4099 range)
#
# Usage: custom/patches/apply-remote-access.sh
#

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."  # Go to project root

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[SKIP]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

echo -e "${CYAN}Applying AutoCoder custom patches...${NC}"
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

# 6. Apply port assignment patch
log_step "Applying port assignment patch (4000-4099 range)..."
PATCH_FILE="custom/patches/port-assignment.patch"
if [ ! -f "$PATCH_FILE" ]; then
    log_error "Patch file not found: $PATCH_FILE"
    exit 1
fi

# Check if already applied by looking for the key changes
if grep -q "assigned_port" server/schemas.py 2>/dev/null && \
   grep -q "DEVSERVER_PORT_MIN = 4000" server/services/project_config.py 2>/dev/null; then
    log_warn "Port assignment patch already applied"
else
    # Apply the patch
    if git apply --check "$PATCH_FILE" 2>/dev/null; then
        git apply "$PATCH_FILE"
        log_info "Applied port assignment patch"
    else
        log_error "Patch failed to apply cleanly - manual merge required"
        log_error "Check: $PATCH_FILE"
        echo ""
        echo "Files that need manual review:"
        echo "  - server/services/project_config.py"
        echo "  - server/schemas.py"
        echo "  - server/routers/devserver.py"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}Done!${NC} Restart the server: ./remote-start.sh stop && ./remote-start.sh ui"
