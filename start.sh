#!/bin/bash
# Start the HK Stock Panel
# Usage: ./start.sh

set -e
cd "$(dirname "$0")"

# Check Python deps
echo "Installing Python dependencies..."
pip3 install -q -r backend/requirements.txt

# Check if frontend is built
if [ ! -d "frontend/dist" ]; then
  echo "Building frontend..."
  cd frontend
  npm install
  npm run build
  cd ..
fi

# Start backend (serves API + frontend)
echo "Starting server on http://localhost:3003"
cd backend
python3 -m uvicorn app:app --host 0.0.0.0 --port 3003
