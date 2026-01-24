#!/usr/bin/env bash
set -euo pipefail

# Mission Control UI - Installation Script
# Copies React components to ui/src/components/ and guides App.tsx integration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
UI_COMPONENTS="$PROJECT_ROOT/ui/src/components"

echo "================================"
echo "Mission Control UI - Installer"
echo "================================"
echo ""

# Check we're in the right place
if [[ ! -d "$PROJECT_ROOT/ui/src" ]]; then
    echo "❌ ERROR: Cannot find ui/src directory"
    echo "   Expected: $PROJECT_ROOT/ui/src"
    echo "   Are you running this from the correct location?"
    exit 1
fi

echo "📁 Project root: $PROJECT_ROOT"
echo "📂 UI components: $UI_COMPONENTS"
echo ""

# Step 1: Copy components
echo "STEP 1: Copying React components..."
echo "-----------------------------------"

COMPONENTS=(
    "TabLayout.tsx"
    "ChatTab.tsx"
    "IssuesTab.tsx"
    "StatusTab.tsx"
)

for component in "${COMPONENTS[@]}"; do
    src="$SCRIPT_DIR/components/$component"
    dest="$UI_COMPONENTS/$component"

    if [[ ! -f "$src" ]]; then
        echo "❌ ERROR: Source component not found: $src"
        exit 1
    fi

    if [[ -f "$dest" ]]; then
        echo "⚠️  $component already exists - will overwrite"
    else
        echo "✅ Copying $component"
    fi

    cp "$src" "$dest"
done

echo ""
echo "✅ All components copied successfully!"
echo ""

# Step 2: Show App.tsx patch instructions
echo "STEP 2: App.tsx integration"
echo "-----------------------------------"
echo ""
echo "The following changes need to be made to ui/src/App.tsx:"
echo ""
echo "1️⃣  Add import (around line 27):"
echo ""
echo "    import { TabLayout } from './components/TabLayout'"
echo ""
echo "2️⃣  Modify main content section (around line 365-380):"
echo ""
echo "    Replace the conditional that renders KanbanBoard/DependencyGraph with:"
echo ""
cat << 'EOF'
    {devLayerMode ? (
      <TabLayout
        selectedProject={selectedProject}
        features={features}
        onFeatureClick={handleFeatureClick}
        onAddFeature={() => setShowAddFeature(true)}
        onExpandProject={() => setShowExpandProject(true)}
        hasSpec={hasSpec}
        onCreateSpec={() => setShowSpecChat(true)}
        debugOpen={debugOpen}
        debugPanelHeight={debugPanelHeight}
        debugActiveTab={debugActiveTab}
        onDebugHeightChange={setDebugPanelHeight}
        onDebugTabChange={setDebugActiveTab}
      />
    ) : viewMode === 'kanban' ? (
      <KanbanBoard ... />
    ) : (
      <DependencyGraph ... />
    )}
EOF
echo ""
echo "-----------------------------------"
echo ""

# Ask if user wants to apply the patch automatically
echo "Would you like me to attempt automatic patching of App.tsx? (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    APP_TSX="$PROJECT_ROOT/ui/src/App.tsx"

    if [[ ! -f "$APP_TSX" ]]; then
        echo "❌ ERROR: App.tsx not found at $APP_TSX"
        exit 1
    fi

    # Backup first
    cp "$APP_TSX" "$APP_TSX.backup-$(date +%Y%m%d-%H%M%S)"
    echo "📦 Created backup: $APP_TSX.backup-*"

    # Check if TabLayout import already exists
    if grep -q "import { TabLayout }" "$APP_TSX"; then
        echo "✅ TabLayout import already present"
    else
        # Add import after the DevLayer import (line 27)
        sed -i "/import { DevLayer } from/a import { TabLayout } from './components/TabLayout'" "$APP_TSX"
        echo "✅ Added TabLayout import"
    fi

    echo "⚠️  Note: Automatic content replacement is complex."
    echo "    Please manually verify the main content section."
    echo "    See INSTALLATION.md for detailed instructions."
else
    echo "ℹ️  Skipping automatic patch. Please apply changes manually."
    echo "   See INSTALLATION.md for detailed instructions."
fi

echo ""
echo "STEP 3: Rebuild UI"
echo "-----------------------------------"
echo ""
echo "Would you like to rebuild the UI now? (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "🔨 Building UI..."
    cd "$PROJECT_ROOT/ui"
    npm run build
    echo "✅ UI rebuilt successfully!"
else
    echo "ℹ️  Skipping UI rebuild. Run manually with:"
    echo "   cd $PROJECT_ROOT/ui && npm run build"
fi

echo ""
echo "================================"
echo "Installation Complete!"
echo "================================"
echo ""
echo "✅ Components copied"
echo "✅ App.tsx patched (verify manually)"
echo "✅ UI rebuilt"
echo ""
echo "Next steps:"
echo "1. Restart AutoCoder UI: autocoder ui"
echo "2. Open http://localhost:4001"
echo "3. Press 'L' key to toggle tabbed interface"
echo "4. Press '1-5' to switch between tabs"
echo ""
echo "Troubleshooting: See custom/mission_control_ui/INSTALLATION.md"
echo ""
