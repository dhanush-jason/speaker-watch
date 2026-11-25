#!/bin/bash
# Installs two launchd jobs for the current user:
#   speakerwatch.sites    – the sites GitHub can't reach (Peter Tyson clearance, Quantum AV), every 3 hours
#   speakerwatch.facebook – Facebook only, at 10:00 and 20:00
# After each check, sync.sh sends the results to GitHub and copies back the
# combined listings.html, so the page here shows the cloud's finds too.
# (The old speakerwatch.quick job is removed: GitHub checks eBay every 15 minutes.)
# Run ./install-schedule.sh --remove to uninstall.
#
# macOS doesn't let background jobs read ~/Documents, so the scheduled copy
# runs from ~/Library/Application Support/SpeakerWatch. Run this script again
# after editing watch.py or sources.py here to update that copy.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/Library/Application Support/SpeakerWatch"
PY="$DIR/.venv/bin/python"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA"

for job in sites facebook quick; do
  launchctl unload "$LA/com.speakerwatch.$job.plist" 2>/dev/null || true
  rm -f "$LA/com.speakerwatch.$job.plist"
done
if [[ "${1:-}" == "--remove" ]]; then echo "Removed."; exit 0; fi

# copy the code, and (first time only) the history and browser sign-in
mkdir -p "$DIR"
cp "$SRC"/{watch.py,sources.py,extract.js,requirements.txt,merge_state.py,sync.sh,run.sh} "$DIR/"
# after each check the Mac syncs with GitHub (sync.sh), committing as you
echo "$(git -C "$SRC" config user.name) $(git -C "$SRC" config user.email)" > "$DIR/git-identity"
[[ -f "$SRC/ntfy.json" ]] && cp "$SRC/ntfy.json" "$DIR/"  # phone push
for f in seen.json ebay.json browser-profile; do
  if [[ -e "$SRC/$f" && ! -L "$SRC/$f" && ! -e "$DIR/$f" ]]; then cp -R "$SRC/$f" "$DIR/"; fi
done
[[ -x "$PY" ]] || python3 -m venv "$DIR/.venv"
"$PY" -m pip install -q -r "$DIR/requirements.txt" 2>&1 | grep -v -e WARNING -e upgrade || true

# links in this folder so the results are easy to open
for f in listings.html watch.log seen.json; do
  touch "$DIR/$f"; rm -rf "${SRC:?}/$f"; ln -s "$DIR/$f" "$SRC/$f"
done

write_plist() { # name, args xml, schedule xml
  cat > "$LA/com.speakerwatch.$1.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.speakerwatch.$1</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$DIR/run.sh</string>$2
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  $3
  <key>StandardOutPath</key><string>$DIR/launchd.log</string>
  <key>StandardErrorPath</key><string>$DIR/launchd.log</string>
</dict></plist>
EOF
  launchctl load "$LA/com.speakerwatch.$1.plist"
}

# macOS pauses these timers while the Mac sleeps, so the jobs fire often and
# watch.py --if-due decides whether a check is actually due.
# Everything else now runs on GitHub (github.com/dhanush-jason/speaker-watch).
# The Mac checks only the sites that block GitHub's servers: every 3 hours.
write_plist sites "<string>--only</string><string>petertyson_clearance</string><string>quantumav</string><string>quantumav_clearance</string><string>--if-due</string><string>175</string>" \
  "<key>StartInterval</key><integer>900</integer><key>RunAtLoad</key><true/>"
write_plist facebook "<string>--only</string><string>facebook</string>" \
  "<key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>"

echo "Installed to $DIR"
echo "Check with: launchctl list | grep speakerwatch"
echo "Sign in to Facebook (optional): \"$PY\" \"$DIR/watch.py\" --login"
