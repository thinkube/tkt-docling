#!/bin/sh
# build.sh - Build backend Docker image using Kaniko

set -e

echo "Building backend Docker image..."

# Ensure we're in the backend directory
cd /workspace/backend

# The actual build is handled by Kaniko via args
# This script would contain any pre-build steps if needed

echo "Backend build prepared successfully!"

# 🤖 Generated with Claude