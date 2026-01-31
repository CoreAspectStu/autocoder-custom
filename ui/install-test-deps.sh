#!/bin/bash
# Script to install testing dependencies and run tests for ChatTab component
# Feature #151: Unit Test ChatTab 404 Error Handling

set -e

echo "=========================================="
echo "Feature #151: ChatTab 404 Error Handling Tests"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "Error: package.json not found. Please run this script from the ui/ directory."
    exit 1
fi

echo "Step 1: Installing testing dependencies..."
echo "-------------------------------------------"
npm install --save-dev \
  @testing-library/react@^16.1.0 \
  @testing-library/jest-dom@^6.6.3 \
  @testing-library/user-event@^14.5.2 \
  vitest@^2.1.8 \
  @vitest/ui@^2.1.8 \
  jsdom@^25.0.1 \
  @vitest/coverage-v8@^2.1.8

echo ""
echo "Step 2: Running ChatTab tests..."
echo "-------------------------------------------"
npm test -- --run --reporter=verbose

echo ""
echo "=========================================="
echo "Test run complete!"
echo "=========================================="
echo ""
echo "To run tests with UI:"
echo "  npm run test:ui"
echo ""
echo "To run tests with coverage:"
echo "  npm run test:coverage"
echo ""
echo "To run tests in watch mode:"
echo "  npm test"
