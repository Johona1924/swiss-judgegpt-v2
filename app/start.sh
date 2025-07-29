#!/bin/sh

# cd into the parent directory of the script, 
# so that the script generates virtual environments always in the same path.
cd "${0%/*}" || exit 1

cd ../
echo 'Creating python virtual environment ".venv"'

# Prefer python3.11, then fall back to python, then python3
if command -v python3.11 >/dev/null 2>&1; then
    pythonCmd="python3.11"
elif command -v python3 >/dev/null 2>&1; then
    pythonCmd="python3"
elif command -v python >/dev/null 2>&1; then
    pythonCmd="python"
else
    echo "No suitable Python installation found (expected python3.11, python3, or python)"
    exit 1
fi

# Show the Python interpreter and version selected
echo "Using Python interpreter: $(command -v $pythonCmd)"
$pythonCmd -c "import sys; print('Python version:', sys.version)"

$pythonCmd -m venv .venv

echo ""
echo "Restoring backend python packages"
echo ""

./.venv/bin/python -m pip install -r app/backend/requirements.txt
out=$?
if [ $out -ne 0 ]; then
    echo "Failed to restore backend python packages"
    exit $out
fi

echo ""
echo "Restoring frontend npm packages"
echo ""

cd app/frontend
npm install
out=$?
if [ $out -ne 0 ]; then
    echo "Failed to restore frontend npm packages"
    exit $out
fi

echo ""
echo "Building frontend"
echo ""

npm run build
out=$?
if [ $out -ne 0 ]; then
    echo "Failed to build frontend"
    exit $out
fi

echo ""
echo "Starting backend"
echo ""

cd ../backend

port=50505
host=localhost
../../.venv/bin/python -m quart --app main:app run --port "$port" --host "$host" --reload
out=$?
if [ $out -ne 0 ]; then
    echo "Failed to start backend"
    exit $out
fi
