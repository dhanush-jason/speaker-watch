#!/bin/bash
# Installs two launchd jobs for the current user:
#   speakerwatch.sites    – every site except Facebook, every 3 hours
#   speakerwatch.quick    – HiFi Shark (eBay UK) and the eBay API, every 30 minutes
#   speakerwatch.facebook – Facebook only, at 10:00 and 20:00
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
cp "$SRC"/{watch.py,sources.py,extract.js,requirements.txt} "$DIR/"
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
    <string>$PY</string><string>$DIR/watch.py</string>$2
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
# All sites except Facebook: every 3 hours (checked every 15 min)
write_plist sites "<string>--skip</string><string>facebook</string><string>--if-due</string><string>175</string>" \
  "<key>StartInterval</key><integer>900</integer><key>RunAtLoad</key><true/>"
# HiFi Shark (our route to eBay UK) and the eBay API: every 30 minutes
write_plist quick "<string>--only</string><string>hifishark</string><string>ebay</string><string>--if-due</string><string>28</string><string>--no-wait</string>" \
  "<key>StartInterval</key><integer>600</integer>"
write_plist facebook "<string>--only</string><string>facebook</string>" \
  "<key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>"

echo "Installed to $DIR"
echo "Check with: launchctl list | grep speakerwatch"
echo "Sign in to Facebook (optional): \"$PY\" \"$DIR/watch.py\" --login"
