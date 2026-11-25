#!/bin/bash
# Mac only: send this Mac's results (Facebook, Peter Tyson clearance, Quantum AV)
# to the GitHub repo, then copy back the combined page, so listings.html here
# shows everything the cloud found too. Runs after each scheduled Mac check.
cd "$(dirname "$0")"
REPO="$PWD/repo"
MAC_ONLY="facebook petertyson_clearance quantumav quantumav_clearance"
export PATH="$HOME/.local/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
if [[ ! -d "$REPO/.git" ]]; then
  git clone -q https://github.com/dhanush-jason/speaker-watch.git "$REPO" || exit 1
fi
[[ -f git-identity ]] && read -r NAME EMAIL < git-identity && git -C "$REPO" config user.name "$NAME" && git -C "$REPO" config user.email "$EMAIL"
for attempt in 1 2 3 4 5; do
  git -C "$REPO" fetch -q origin main && git -C "$REPO" reset -q --hard origin/main || { sleep 10; continue; }
  if [[ -s seen.json ]]; then
    WATCH_DATA_DIR="$REPO/data" MERGE_ONLY="$MAC_ONLY" ./.venv/bin/python merge_state.py seen.json watch.log >/dev/null
  fi
  git -C "$REPO" add data/seen.json data/listings.html data/watch.log
  git -C "$REPO" diff --cached --quiet && break
  git -C "$REPO" commit -q -m "Update listings (Mac)" && git -C "$REPO" push -q origin HEAD:main && break
  sleep $((attempt * 5))
done
cp "$REPO/data/listings.html" listings.html
echo "$(date '+%Y-%m-%d %H:%M:%S')  synced with GitHub"
