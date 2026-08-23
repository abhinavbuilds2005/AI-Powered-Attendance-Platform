#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "==> [Step 1/4] Upgrading pip and build tools..."
pip install --upgrade pip setuptools wheel

echo "==> [Step 2/4] Setting C++ build flags to prevent memory overflow..."
export CMAKE_BUILD_PARALLEL_LEVEL=1
export CMAKE_ARGS="-DDLIB_NO_GUI_SUPPORT=ON -DDLIB_USE_CUDA=OFF -DDLIB_GIF_SUPPORT=OFF -DDLIB_JPEG_SUPPORT=ON -DDLIB_PNG_SUPPORT=ON"

echo "==> [Step 3/4] Installing lightweight CPU-only PyTorch..."
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

echo "==> [Step 4/4] Installing remaining dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "==> Build finished successfully!"
