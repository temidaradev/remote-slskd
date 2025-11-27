#!/usr/bin/env bash

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v nix-shell >/dev/null 2>&1; then
	nix-shell -p python312Packages.requests --run "python3 \"$DIR/auto_download.py\" \"$@\""
	exit $?
fi

PYTHON=""
if command -v python3 >/dev/null 2>&1; then
	PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
	PYTHON="python"
elif command -v py >/dev/null 2>&1; then
	PYTHON="py -3"
fi

if [ -z "$PYTHON" ]; then
	echo "No Python 3 interpreter found. Please install Python 3."
	exit 1
fi

if ! $PYTHON -c "import sys
try:
		import requests
except Exception:
		sys.exit(2)
sys.exit(0)" >/dev/null 2>&1; then
	echo "requests not found. Creating virtualenv in .venv and installing dependencies..."
	$PYTHON -m venv .venv

	if [ -f ".venv/bin/activate" ]; then
		. .venv/bin/activate
		pip install --upgrade pip
		if [ -f "requirements.txt" ]; then
			pip install -r requirements.txt
		else
			pip install requests
		fi
		deactivate
	elif [ -f ".venv/Scripts/activate" ]; then
		. .venv/Scripts/activate
		pip install --upgrade pip
		if [ -f "requirements.txt" ]; then
			pip install -r requirements.txt
		else
			pip install requests
		fi
		deactivate
	else
		echo "Failed to activate .venv. Install 'requests' manually: pip install requests"
		exit 1
	fi

	if [ -x ".venv/bin/python" ]; then
		PYTHON=".venv/bin/python"
	elif [ -x ".venv/Scripts/python.exe" ]; then
		PYTHON=".venv/Scripts/python.exe"
	fi
fi

read -r -a PYTHON_CMD <<< "$PYTHON"


ensure_docker_running() {
	echo "Checking Docker availability..."

	if ! command -v docker >/dev/null 2>&1; then
		echo "Docker CLI not found. Skipping automatic Docker start."
		return 0
	fi

	if docker info >/dev/null 2>&1; then
		echo "Docker is already running."
		return 0
	fi

	echo "Docker not running — attempting to start (this may prompt for sudo or open the Docker app)..."

	uname_s=$(uname -s || echo "")

	if command -v systemctl >/dev/null 2>&1; then
		echo "Attempting: sudo systemctl start docker"
		sudo systemctl start docker || true
	elif command -v service >/dev/null 2>&1; then
		echo "Attempting: sudo service docker start"
		sudo service docker start || true
	fi

	if [ "$uname_s" = "Darwin" ]; then
		if command -v open >/dev/null 2>&1; then
			echo "Opening Docker Desktop app..."
			open -a Docker || true
		fi
	fi

	if command -v powershell.exe >/dev/null 2>&1; then
		echo "Trying to start Docker Desktop via PowerShell..."
		powershell.exe -NoProfile -Command "Start-Process 'Docker Desktop' -ErrorAction SilentlyContinue" 2>/dev/null || true
	fi

	echo -n "Waiting for Docker to start"
	for i in {1..30}; do
		if docker info >/dev/null 2>&1; then
			echo " ✓"
			return 0
		fi
		echo -n "."
		sleep 1
	done
	echo ""
	echo "Warning: Docker did not become available after 30s. Continuing without Docker."
	return 1
}

ensure_docker_running || true

exec "${PYTHON_CMD[@]}" "$DIR/auto_download.py" "$@"
