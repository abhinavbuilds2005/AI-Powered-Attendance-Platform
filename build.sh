#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "==> Step 1: Upgrading pip and wheel tools..."
pip install --upgrade pip setuptools wheel

echo "==> Step 2: Installing lightweight CPU-only PyTorch to save RAM..."
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

echo "==> Step 3: Limiting CMake parallel compile jobs to prevent RAM overflow..."
export CMAKE_BUILD_PARALLEL_LEVEL=1

echo "==> Step 4: Installing dependencies from requirements.txt..."
pip install --no-cache-dir -r requirements.txt

echo "==> Build completed successfully!"
