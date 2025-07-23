#!/bin/bash

echo "Building local-synk executable..."

# Create deploy/linux directory if it doesn't exist
mkdir -p deploy/linux

# Change to deploy/linux directory
cd deploy/linux

# Clean up previous build artifacts
echo "Cleaning previous build..."
if [ -d "build" ]; then
    rm -rf build 2>/dev/null || echo "Warning: Could not remove build folder - continuing anyway"
fi
if [ -d "dist" ]; then
    rm -rf dist 2>/dev/null || echo "Warning: Could not remove dist folder - continuing anyway"
fi
rm -f *.spec 2>/dev/null

# Build the executable
echo "Building executable..."
nicegui-pack --name "local-synk" --onefile ../../main.py

echo "Build complete! Check deploy/linux/dist for the executable."
