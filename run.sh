#!/bin/bash
# Mac scheduled job: check the Mac's sites (if due), then sync with GitHub.
cd "$(dirname "$0")"
./.venv/bin/python watch.py "$@"
./sync.sh
