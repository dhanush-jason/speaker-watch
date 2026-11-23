# Silver 100 7G watcher

**Runs in the cloud:** GitHub Actions checks HiFi Shark (eBay UK) every 15 minutes and every other site every 3 hours, and sends phone alerts through the free **ntfy** app (topic in the `NTFY_TOPIC` secret). Results: `data/listings.html`. Run it by hand from the repo's *Actions* tab → *Speaker watch* → *Run workflow*.
**Runs on the Mac:** only sites that block GitHub's servers (Facebook at 10:00 and 20:00, Peter Tyson clearance and Quantum AV every 3 hours), via `install-schedule.sh`.
Optional eBay API: add `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` as repo secrets with `gh secret set`.

Checks UK shops and marketplaces for **Monitor Audio Silver 100 7G** and sends a Mac notification when a new listing appears. Everything found is listed in `listings.html`.

| Site | How often | Notes |
|---|---|---|
| Facebook Marketplace | 10:00 and 20:00 | Searches from 9 UK cities. Works signed out; signing in (below) usually shows more |
| Gumtree, Preloved, Vinted, Cash Converters, Shpock | every 3 h | |
| HiFi Shark | every 3 h | Filtered to the UK. Includes eBay UK, dealers' used stock and forum ads |
| Richer Sounds, Premium Sound, Peter Tyson, Amazon UK | every 3 h | Shops now sell the 8G, so 7G only shows up as ex-demo or clearance stock |
| Richer Sounds & Peter Tyson clearance, Hifix, Audio Venue, Doug Brady, Hi-Fi Sound, Sevenoaks, Vickers, Quantum AV, Weybridge Audio, Reference Audio, Analogue Seduction | every 3 h | Ex-demo, open-box, nearly-new and sale stock. HiFi Shark adds AV Forums, Pink Fish Media, UK Audio Mart, Sevenoaks, Emporium Hi-Fi and Wilkinsons |
| eBay UK (direct) | every 3 h | Optional, needs a free API key (below). eBay blocks automated browsers |

It keeps listings that say 7G, and listings that don't give a generation (shown as `?` so you can check them). It drops 5G, 6G, 8G, stands and parts.

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python watch.py            # one check now
./install-schedule.sh                # run on the schedule above
```
You need Google Chrome installed (it uses it in the background). Remove the schedule with `./install-schedule.sh --remove`.

macOS doesn't let background jobs read Documents, so the scheduled copy runs from `~/Library/Application Support/SpeakerWatch`. `listings.html`, `watch.log` and `seen.json` here are links to that copy. **After editing `watch.py` or `sources.py` here, run `./install-schedule.sh` again** to update it.

## Optional
- **Sign in to Facebook:** run the `--login` command that `install-schedule.sh` prints, sign in, press Enter. Facebook's terms don't allow automated browsing, so there's a small risk to that account; a spare account is safer. It only runs twice a day to keep that risk low.
- **eBay API:** make a free account at developer.ebay.com → *Application Keys* → create a **Production** keyset. Save `{"client_id": "...", "client_secret": "..."}` as `ebay.json` in this folder.
- **Clickable notifications:** `brew install terminal-notifier` makes clicking a notification open `listings.html`.
- **Missed a listing?** Sellers make typos (one wrote "Silver 1007G"). Add the spelling they used to `SEARCHES` in `sources.py`, then run `./install-schedule.sh`.
- **Add a site:** add an entry to `sources.py` (a search URL with `{q}` is usually enough).

## Files
`seen.json` listings found so far · `listings.html` sortable table · `watch.log` what each run found · a site that fails 3 runs in a row sends a warning.
