#!/usr/bin/env bash
set -o errexit

echo "==> Step 1: Upgrading pip..."
pip install --upgrade pip

echo "==> Step 2: Installing pre-compiled CPU PyTorch & all dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "==> Build finished successfully in seconds!"
