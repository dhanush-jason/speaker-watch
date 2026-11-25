#!/usr/bin/env python3
"""Merge this run's results into the latest results from the repo.

  python merge_state.py OURS_SEEN OURS_LOG

Reads data/seen.json and data/watch.log (the latest committed versions),
merges in ours, writes them back and rebuilds data/listings.html. Used by the
GitHub workflow so two runs that finish close together don't clash.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("WATCH_DATA_DIR", "data")
import watch  # noqa: E402  (uses WATCH_DATA_DIR)

ours_seen, ours_log = Path(sys.argv[1]), Path(sys.argv[2])
theirs = json.loads(watch.STATE_FILE.read_text()) if watch.STATE_FILE.exists() else {"listings": {}, "sources": {}}
ours = json.loads(ours_seen.read_text())

# The Mac passes MERGE_ONLY (its own site names) so its out-of-date copies of
# the cloud's sites don't get merged in.
only = os.environ.get("MERGE_ONLY", "").split()
if only:
    labels = {s["label"] for s in watch.SOURCES if s["name"] in only}
    ours["listings"] = {k: v for k, v in ours["listings"].items() if v["source"] in labels}
    ours["sources"] = {k: v for k, v in ours["sources"].items() if k in only}

for key, v in ours["listings"].items():
    t = theirs["listings"].get(key)
    if not t or v["last_seen"] >= t["last_seen"]:
        if t:
            v["first_seen"] = min(v["first_seen"], t["first_seen"])
        theirs["listings"][key] = v
for name, s in ours["sources"].items():
    t = theirs["sources"].get(name)
    if not t or s.get("last_ok", "") >= t.get("last_ok", ""):
        theirs["sources"][name] = s

watch.STATE_FILE.write_text(json.dumps(theirs, indent=1))
watch.write_html(theirs)

# logs: keep every line once, in time order, last 3000
lines = set()
for f in ((watch.LOG_FILE,) if only else (watch.LOG_FILE, ours_log)):
    if f.exists():
        lines.update(l for l in f.read_text().splitlines() if l.strip())
watch.LOG_FILE.write_text("\n".join(sorted(lines)[-3000:]) + "\n")
print("merged: %d listings" % len(theirs["listings"]))
