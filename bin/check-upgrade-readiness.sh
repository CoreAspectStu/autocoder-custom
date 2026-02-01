#!/usr/bin/env bash
#
# check-upgrade-readiness.sh
#
# Pre-upgrade validation for AutoCoder.
# Run this before any upstream merge to catch potential issues.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

echo "🔍 AutoCoder Upgrade Readiness Check"
echo "====================================="
echo ""

# 1. Check for uncommitted changes
echo "📋 Checking for uncommitted changes..."
if [ -n "$(git status --porcelain)" ]; then
    echo -e "${RED}❌ FAIL: Uncommitted changes detected${NC}"
    echo "   Commit or stash your changes before upgrading:"
    echo "   git stash push -m 'pre-upgrade stash'"
    git status --short
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ PASS: Working directory clean${NC}"
fi
echo ""

# 2. Check for pending migrations
echo "📋 Checking for pending database migrations..."
if [ -f "server/services/assistant_db_add_mode_column.py" ]; then
    # Check if any project databases are missing the mode column
    MISSING_MODE=0
    for db in ~/projects/autocoder-projects/*/assistant.db; do
        if [ -f "$db" ]; then
            # Check if mode column exists
            if ! sqlite3 "$db" "PRAGMA table_info(conversations);" | grep -q "mode"; then
                MISSING_MODE=$((MISSING_MODE + 1))
            fi
        fi
    done

    if [ $MISSING_MODE -gt 0 ]; then
        echo -e "${YELLOW}⚠️  WARNING: $MISSING_MODE database(s) missing 'mode' column${NC}"
        echo "   Run migrations before or after upgrade:"
        echo "   source ~/projects/autocoder/venv/bin/activate"
        echo "   for db in ~/projects/autocoder-projects/*/assistant.db; do"
        echo "     python server/services/assistant_db_add_mode_column.py \"\$(dirname \"\$db\")\""
        echo "   done"
        WARNINGS=$((WARNINGS + 1))
    else
        echo -e "${GREEN}✅ PASS: All databases up to date${NC}"
    fi
else
    echo -e "${GREEN}✅ PASS: No pending migrations${NC}"
fi
echo ""

# 3. Check service status
echo "📋 Checking AutoCoder service status..."
if systemctl --user is-active --quiet autocoder-ui.service; then
    echo -e "${GREEN}✅ PASS: Service is running${NC}"
else
    echo -e "${YELLOW}⚠️  WARNING: Service is not running${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 4. Check for backup branches
echo "📋 Checking for backup..."
BACKUP_BRANCH="backup-$(date +%Y-%m-%d)"
if git rev-parse --verify "$BACKUP_BRANCH" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ PASS: Backup branch exists ($BACKUP_BRANCH)${NC}"
else
    echo -e "${YELLOW}⚠️  WARNING: No backup branch for today${NC}"
    echo "   Create one before upgrading: git branch $BACKUP_BRANCH"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 5. Check Python venv
echo "📋 Checking Python environment..."
if [ -f "venv/bin/activate" ]; then
    echo -e "${GREEN}✅ PASS: Python venv exists${NC}"
else
    echo -e "${RED}❌ FAIL: Python venv not found${NC}"
    echo "   Run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Summary
echo "====================================="
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}❌ UPGRADE NOT RECOMMENDED${NC}"
    echo "   Fix the errors above before proceeding."
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  UPGRADE WITH CAUTION${NC}"
    echo "   Review warnings above. You may proceed."
    exit 0
else
    echo -e "${GREEN}✅ ALL CHECKS PASSED${NC}"
    echo "   Safe to proceed with upgrade."
    exit 0
fi
