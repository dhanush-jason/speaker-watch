#!/usr/bin/env python3
"""Watch UK shops and marketplaces for Monitor Audio Silver 100 7G listings.

  python watch.py                 check every site once
  python watch.py --skip facebook check everything except Facebook
  python watch.py --only facebook check Facebook only
  python watch.py --show          use a visible browser (debugging)
  python watch.py --login         open a visible browser to sign in to Facebook (optional)
  python watch.py --no-notify     don't send Mac notifications

New listings trigger a macOS notification. Everything found is kept in
seen.json and shown in listings.html.
"""
import argparse
import base64
import fcntl
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from sources import SEARCH, SEARCHES, SOURCES, TARGETS

HERE = Path(__file__).resolve().parent
# Results live next to the script on the Mac, and in data/ on GitHub
DATA = Path(os.environ["WATCH_DATA_DIR"]).resolve() if os.environ.get("WATCH_DATA_DIR") else HERE
DATA.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA / "seen.json"
HTML_FILE = DATA / "listings.html"
PROFILE_DIR = DATA / "browser-profile"
LOG_FILE = DATA / "watch.log"
CHANNEL = os.environ.get("WATCH_BROWSER_CHANNEL", "chrome" if sys.platform == "darwin" else "") or None
EXTRACT_JS = (HERE / "extract.js").read_text()

# "Silver 100", "Silver Series 100", "Silver 7G 100" (generation first, as Doug
# Brady writes it) and typos like "Silver 1007G" (no space). Same for the 50.
MODEL = re.compile(r"silver[^a-z0-9]{0,6}(?:series[^a-z0-9]{0,3})?(?:(\d{1,2})\s*g[^a-z0-9]{1,3})?(50|100)(?!\d)", re.I)
GLUED = re.compile(r"silver[^a-z0-9]{0,6}(50|100)(\d{1,2})\s*g\b", re.I)
GEN = re.compile(r"(?<![a-z0-9])(?:(\d{1,2})\s*(?:g|gen|th\s*gen)|gen(?:eration)?\s*(\d{1,2}))(?![a-z])", re.I)
GBP = re.compile(r"£\s?(\d[\d,]*(?:\.\d+)?)")
# Parts are dropped unless the title is clearly about the speakers themselves
PARTS = re.compile(r"\b(grilles?|cables?|spikes?|tweeters?|woofers?|drivers?|crossovers?|replacement|spares?)\b", re.I)
# Stands are dropped only when the listing *is* the stands ("Speaker stands for ..."),
# not when speakers come "with stands"
STANDS_ONLY = re.compile(r"^\W*(\w+\W+){0,2}(stands?|brackets?|mounts?|covers?|protectors?)\b|\b(stands?|brackets?|mounts?|covers?|protectors?)\b[^,]{0,40}\b(for|to fit|suits?)\b", re.I)
SPEAKERS = re.compile(r"\b(pair|speakers?|bookshelf)\b", re.I)
# The two limited editions: Heritage Green (2022, 50th anniversary, ~720 pairs)
# and Carbon Black Metallic (2025)
GREEN = re.compile(r"\b(green|heritage|50th|anniversary)\b", re.I)
CARBON = re.compile(r"\b(carbon|black\s*metallic|metallic\s*black)\b", re.I)
LIMITED = re.compile(r"\b(limited|l\.?e\.?|numbered)\b|\b\d{1,3}\s*/\s*999\b", re.I)
JUNK = re.compile(r"search results|you searched|results for", re.I)
# people looking to buy, not sell
WANTED = re.compile(r"\b(wanted|wtb|want to buy|looking for|iso|in search of)\b", re.I)
PRICE = re.compile(r"(£|€|US\$|\$)\s?\d[\d,]*(?:\.\d{2})?")
BROKEN_AFTER = 3  # failed loads in a row before warning
SHOW_DAYS = 14  # listings.html shows items seen in this many days
# Marketplaces list everything for sale each time, so a listing missing from
# this many checks in a row has almost certainly sold or ended. (Shops' own
# searches skip items now and then, so those wait a day instead.)
GONE_AFTER = 3
FAST_GONE = {"hifishark", "ebay", "gumtree", "preloved", "vinted", "cashconverters", "shpock"}
LISTED = re.compile(r"\s*(\d{1,2} [A-Z][a-z]{2} \d{4})\s*$")


def log(msg):
    line = "%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- filtering
def model_of(title):
    """('100', {7}) for 'Silver 100 7G'; (None, set()) if no Silver 50/100."""
    g = GLUED.search(title)
    m = MODEL.search(title)
    if g and (not m or g.start() <= m.start()):
        model, gens = g.group(1), {int(g.group(2))}
    elif m:
        model, gens = m.group(2), ({int(m.group(1))} if m.group(1) else set())
    else:
        return None, set()
    gens |= {int(a or b) for a, b in GEN.findall(title)}
    return model, gens


def gbp(price):
    m = GBP.search(price or "")
    return float(m.group(1).replace(",", "")) if m else None


def classify(title, price=None):
    """Return (keep, label) e.g. (True, 'Silver 100 7G'). Targets and their
    price limits are set in sources.py. price=None skips the price check."""
    if JUNK.search(title) or WANTED.search(title) or STANDS_ONLY.search(title) or (PARTS.search(title) and not SPEAKERS.search(title)):
        return False, None
    model, gens = model_of(title)
    if not model:
        return False, None
    for t_model, t_gen, new_price in TARGETS:
        if t_model != model:
            continue
        if gens and t_gen not in gens:
            continue
        # no generation in the title: only the any-price target (the 100 7G) takes it
        if not gens and new_price is not None:
            continue
        if new_price is not None and price is not None:
            p = gbp(price)
            if p is None or p >= new_price:
                continue
        return True, "Silver %s %s" % (model, "%dG" % t_gen if gens else "?")
    return False, None


def is_100_7g(label):
    return label in ("7G", "?", "Silver 100 7G", "Silver 100 ?")


def edition(title):
    """'Heritage Green LE', 'Carbon Black LE', 'Limited Edition' or ''."""
    if GREEN.search(title):
        return "Heritage Green LE"
    if CARBON.search(title):
        return "Carbon Black LE"
    if LIMITED.search(title):
        return "Limited Edition"
    return ""


def normalise_url(url):
    # HiFi Shark links carry a per-visit id; eBay ones map straight to the item
    m = re.search(r"hifishark\.com/goto/ebay_(\d+)", url)
    if m:
        return "https://www.ebay.co.uk/itm/" + m.group(1)
    m = re.search(r"(https://www\.hifishark\.com/goto/[^/?#]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"ebay\.[a-z.]+/itm/(?:[^/?#]+/)?(\d{9,})", url)
    if m:
        return "https://www.ebay.co.uk/itm/" + m.group(1)
    u = urllib.parse.urlsplit(url)
    path = u.path
    m = re.search(r"(/dp/[A-Z0-9]{10})", path)  # Amazon
    if m:
        path = m.group(1)
    return urllib.parse.urlunsplit((u.scheme, u.netloc.lower(), path.rstrip("/"), "", ""))


# ---------------------------------------------------------------- scraping
def scrape_page(ctx, src, url):
    page = ctx.new_page()
    try:
        resp = page.goto(url, timeout=45000, wait_until="domcontentloaded")
        status = resp.status if resp else 0
        if status >= 400:
            raise RuntimeError("HTTP %s" % status)
        page.wait_for_timeout(src.get("wait_ms", 5000))
        for attempt in (1, 2):
            try:
                if src.get("prepare"):
                    page.evaluate(src["prepare"])
                return page.evaluate(EXTRACT_JS)
            except Exception as e:
                if attempt == 2 or "context was destroyed" not in str(e):
                    raise
                page.wait_for_load_state("domcontentloaded")  # the page redirected; read it again
                page.wait_for_timeout(3000)
    finally:
        page.close()


def scrape_stockpages(ctx, src):
    """A listing appears when a product page stops saying it's unavailable."""
    out, errors = [], []
    for url in src["urls"]:
        page = ctx.new_page()
        try:
            resp = page.goto(url, timeout=45000, wait_until="domcontentloaded")
            if resp and resp.status >= 400:
                raise RuntimeError("HTTP %s" % resp.status)
            page.wait_for_timeout(src.get("wait_ms", 6000))
            text = page.evaluate("() => document.body.innerText")
            title = page.evaluate("() => (document.querySelector('h1') || {}).innerText || document.title").strip()
            if src["unavailable"].lower() in text.lower():
                log("  %-12s unavailable  %s" % (src["name"], url))
                continue
            m = PRICE.search(text[text.find(title):] if title in text else text)
            out.append({"title": "IN STOCK: " + title, "url": url, "price": m.group(0) if m else "", "gen": "Silver 100 7G"})
        except Exception as e:
            errors.append(str(e).splitlines()[0][:150])
        finally:
            page.close()
    if errors and len(errors) == len(src["urls"]):
        raise RuntimeError(errors[0])
    return out


def scrape(ctx, src):
    if src.get("kind") == "stockpage":
        return scrape_stockpages(ctx, src)
    urls = [u.format(q=urllib.parse.quote_plus(phrase))
            for phrase in src.get("searches", SEARCHES)
            for u in src.get("urls", [src.get("url")])]
    raw, errors = [], []
    for url in urls:
        try:
            got = scrape_page(ctx, src, url)
            raw += got
            if len(urls) > 1:
                log("  %-12s %3d link(s) mentioning Silver 100  %s" % (src["name"], len(got), urllib.parse.unquote_plus(url)[:110]))
        except Exception as e:
            errors.append(str(e).splitlines()[0][:150])
            log("  %-12s page failed: %s  %s" % (src["name"], errors[-1][:80], urllib.parse.unquote_plus(url)[:90]))
        if len(urls) > 1:
            time.sleep(3)
    if errors and len(errors) == len(urls):
        raise RuntimeError(errors[0])
    out, seen = [], set()
    for it in raw:
        title = it["title"]
        keep, gen = classify(title)
        if not keep or normalise_url(it["url"]) in seen:
            continue
        seen.add(normalise_url(it["url"]))
        # Richer Sounds marks clearance stock as "IN-STORE CLEARANCE" or "ONLINE CLEARANCE"
        tag = re.search(r"(IN-STORE|ONLINE) CLEARANCE", it.get("card") or it.get("ctx") or "")
        if tag and "clearance" not in title.lower():
            title += " - %s clearance" % tag.group(1).title()
        elif tag and tag.group(1) == "ONLINE":
            title = title.replace("- In-Store Clearance", "- Online Clearance")
        # Sevenoaks Outlet: "Clearance - Manchester ... Ex-Display ..."
        so = re.search(r"Clearance - ([A-Za-z ]+?)(?: Ex|\s+Brand|\s+B-?Stock|\s+Graded|\s+For More|$)", it.get("card") or "")
        if so and "clearance" not in title.lower():
            cond = re.search(r"(Ex[- ]?Display|Ex[- ]?Demo|Brand New and Boxed|B-?Stock|Graded|Open Box)", it.get("card") or "", re.I)
            title += " - Clearance (%s%s)" % (so.group(1).strip(), ", " + cond.group(1) if cond else "")
        price = it.get("price")
        if not price:
            m = PRICE.search(title)
            price = m.group(0) if m else ""
        if src.get("gbp_only") and not (price or "").startswith("£"):
            continue
        keep, gen = classify(title, price)
        if not keep:
            continue
        out.append({"title": title, "url": it["url"], "price": price, "gen": gen})
    return out


def ebay_api():
    """eBay blocks automated browsers, so it uses eBay's free official API.
    Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET (see README) to enable it."""
    cid, secret = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
    if not (cid and secret):
        cfg = HERE / "ebay.json"
        if cfg.exists():
            c = json.loads(cfg.read_text())
            cid, secret = c.get("client_id"), c.get("client_secret")
    if not (cid and secret):
        return None
    cid, secret = cid.strip(), secret.strip()

    def call(req, step):
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:  # eBay's reply says what's wrong (no keys in it)
            raise RuntimeError("%s: HTTP %s %s" % (step, e.code, e.read()[:300].decode("utf-8", "replace")))
    auth = base64.b64encode(("%s:%s" % (cid, secret)).encode()).decode()
    req = urllib.request.Request(
        "https://api.ebay.com/identity/v1/oauth2/token",
        data=urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }).encode(),
        headers={"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"},
    )
    token = call(req, "eBay sign-in")["access_token"]
    summaries = {}
    for phrase in SEARCHES:
        q = urllib.parse.urlencode({
            "q": phrase,
            "filter": "itemLocationCountry:GB",
            "limit": "100",
        })
        req = urllib.request.Request(
            "https://api.ebay.com/buy/browse/v1/item_summary/search?" + q,
            headers={"Authorization": "Bearer " + token, "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"},
        )
        for it in call(req, "eBay search").get("itemSummaries", []):
            summaries[it["itemId"]] = it
    out = []
    for it in summaries.values():
        p = it.get("price") or it.get("currentBidPrice") or {}
        price = ("£%s" % p["value"]) if p.get("currency") == "GBP" else ("%s %s" % (p.get("currency", ""), p.get("value", ""))).strip()
        keep, gen = classify(it.get("title", ""), price)
        if not keep:
            continue
        if "AUCTION" in it.get("buyingOptions", []):
            price += " (auction)"
        out.append({"title": it["title"], "url": it["itemWebUrl"], "price": price, "gen": gen})
    return out


# ---------------------------------------------------------------- alerts
def ntfy_topic():
    t = os.environ.get("NTFY_TOPIC")
    cfg = HERE / "ntfy.json"
    if not t and cfg.exists():
        t = json.loads(cfg.read_text()).get("topic")
    return t


def push(title, message, url=None, priority=4, tags=None):
    """Phone push via ntfy.sh (free app). The topic name works like a password."""
    topic = ntfy_topic()
    if not topic:
        return
    body = {"topic": topic, "title": title, "message": message, "priority": priority}
    if url:
        body["click"] = url
        body["actions"] = [{"action": "view", "label": "Open listing", "url": url}]
    if tags:
        body["tags"] = tags
    try:
        req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        log("push failed: %s" % e)


def notify(title, message, enabled=True, url=None, priority=4, tags=None):
    if not enabled:
        return
    push(title, message, url, priority, tags)
    if sys.platform != "darwin":
        return
    if subprocess.run(["which", "terminal-notifier"], capture_output=True).returncode == 0:
        subprocess.run(["terminal-notifier", "-title", title, "-message", message,
                        "-open", HTML_FILE.as_uri(), "-sound", "default"])
    else:
        subprocess.run(["osascript",
                        "-e", "on run argv",
                        "-e", 'display notification (item 1 of argv) with title (item 2 of argv) sound name "Glass"',
                        "-e", "end run", message, title])


def write_html(state):
    cutoff = (datetime.now() - timedelta(days=SHOW_DAYS)).isoformat()
    items = [dict(v, key=k) for k, v in state["listings"].items() if v["last_seen"] >= cutoff]
    last_ok = {}
    for src in SOURCES + [{"name": "ebay", "label": "eBay UK"}]:
        t = state["sources"].get(src["name"], {}).get("last_ok", "")
        last_ok[src["label"]] = max(last_ok.get(src["label"], ""), t)
    for v in items:
        # not seen for a day although the site has been checked since:
        # probably sold or ended (sites' searches can skip items now and then)
        v["gone"] = v.get("missed", 0) >= GONE_AFTER or (
            v["last_seen"] < last_ok.get(v["source"], "")
            and v["last_seen"] < (datetime.now() - timedelta(hours=24)).isoformat())
        m = LISTED.search(v["title"])  # HiFi Shark titles end with the date it was listed
        v["listed"] = datetime.strptime(m.group(1), "%d %b %Y").strftime("%d %b") if m else ""
        v["shown_title"] = re.sub(r"\s*(US\$|[£€$])[\d,.]+\s*$", "", LISTED.sub("", v["title"])) if m else v["title"]
        if v["gen"] in ("7G", "?"):  # entries saved before the 50 / 8G were added
            v["gen"] = "Silver 100 " + v["gen"]
        v.setdefault("edition", edition(v["title"]) if is_100_7g(v["gen"]) else "")
    items.sort(key=lambda v: (not v["gone"], bool(v["edition"]), v["first_seen"]), reverse=True)
    newest = max((v["first_seen"] for v in items), default="")
    rows = []
    for v in items:
        new = v["first_seen"] >= (datetime.now() - timedelta(hours=24)).isoformat()
        rows.append(
            "<tr class='%s'><td>%s</td><td class='num'>%s</td><td>%s</td><td>%s<a href='%s' target='_blank' rel='noopener'>%s</a></td>"
            "<td class='num'>%s</td><td>%s</td><td>%s</td></tr>" % (
                " ".join(c for c in ["new" if new and not v["gone"] else "", "le" if v["edition"] else "", "gone" if v["gone"] else ""] if c),
                html.escape(v["first_seen"][:16].replace("T", " ")),
                html.escape(v["listed"] or "–"),
                html.escape(v["source"]),
                ("<span class='badge %s'>%s</span> " % ("green" if "Green" in v["edition"] else "carbon" if "Carbon" in v["edition"] else "",
                                                      html.escape(v["edition"]))) if v["edition"] else "",
                html.escape(v["url"]), html.escape(v["shown_title"]),
                html.escape(v["price"] or "?"), html.escape(v["gen"]), "sold / gone" if v["gone"] else "NEW" if new else ""))
    sources = state.get("sources", {})
    status = " · ".join(
        "%s: %s" % (html.escape(s["label"]), "⚠️ failing" if sources.get(s["name"], {}).get("fails", 0) >= BROKEN_AFTER
                    else str(sources.get(s["name"], {}).get("count", "–")))
        for s in SOURCES + [{"name": "ebay", "label": "eBay API"}])
    HTML_FILE.write_text("""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Silver 100 7G watch</title>
<style>
:root{--bg:#fafaf9;--fg:#1c1917;--mute:#78716c;--line:#e7e5e4;--new:#ecfccb;--link:#1d4ed8}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f5f4;--mute:#a8a29e;--line:#44403c;--new:#284010;--link:#93c5fd}}
body{background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,system-ui,sans-serif;margin:0;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px} p{color:var(--mute);margin:0 0 16px}
.wrap{overflow-x:auto} table{border-collapse:collapse;width:100%%;min-width:640px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{cursor:pointer;color:var(--mute);font-weight:600;font-size:13px;user-select:none}
tr.new td{background:var(--new)} tr.gone td{opacity:.45} tr.gone a{text-decoration:line-through} tr.le td{border-left:0}
.badge{display:inline-block;font-size:12px;font-weight:600;padding:1px 7px;border-radius:999px;background:#fde68a;color:#422006;margin-right:4px}
.badge.green{background:#166534;color:#fff}.badge.carbon{background:#27272a;color:#fff;border:1px solid #71717a} a{color:var(--link)} .num{white-space:nowrap;font-variant-numeric:tabular-nums}
</style>
<h1>Monitor Audio Silver watch</h1>
<p>Updated %s · %d listings seen in the last %d days · newest %s<br>%s</p>
<div class=wrap><table id=t><thead><tr><th>First seen</th><th>Listed</th><th>Site</th><th>Listing</th><th>Price</th><th>Model</th><th></th></tr></thead>
<tbody>%s</tbody></table></div>
<script>
document.querySelectorAll('th').forEach((th,i)=>th.onclick=()=>{const tb=document.querySelector('tbody');
const rows=[...tb.rows];const asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
const val=r=>{const t=r.cells[i].innerText;const n=parseFloat(t.replace(/[^0-9.]/g,''));return i===4&&!isNaN(n)?n:t.toLowerCase()};
rows.sort((a,b)=>(val(a)>val(b)?1:val(a)<val(b)?-1:0)*(asc?1:-1));rows.forEach(r=>tb.appendChild(r))});
</script>""" % (datetime.now().strftime("%d %b %Y %H:%M"), len(items), SHOW_DAYS,
                 html.escape(newest[:16].replace("T", " ")), status, "\n".join(rows)))


# ---------------------------------------------------------------- main
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"listings": {}, "sources": {}}


def title_key(title):
    t = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return t[:60]


def already_listed(state, title):
    """HiFi Shark titles start with the shop's own title, then site/price/date."""
    k = title_key(title)
    return any(not v["source"].startswith("HiFi Shark") and k.startswith(title_key(v["title"])[:50])
               for v in state["listings"].values())


def record(state, name, label, result, error, now, new_items, alerts):
    s = state["sources"].setdefault(name, {"fails": 0})
    if error:
        s["fails"] = s.get("fails", 0) + 1
        log("%-14s FAILED (%d in a row): %s" % (name, s["fails"], error))
        if s["fails"] == BROKEN_AFTER:
            alerts.append(("Speaker watch: %s may be broken" % label,
                           "It failed %d runs in a row. Check watch.log." % BROKEN_AFTER))
        return
    s["fails"], s["count"], s["last_ok"] = 0, len(result), now
    log("%-14s %d matching listing(s)" % (name, len(result)))
    for it in result:
        key = normalise_url(it["url"])
        if name == "hifishark" and key not in state["listings"] and already_listed(state, it["title"]):
            continue  # a shop we search directly (e.g. Peter Tyson) already has it
        prev = state["listings"].get(key)
        if prev:
            prev.update(last_seen=now, price=it["price"], title=it["title"])
        else:
            state["listings"][key] = dict(it, url=key if "ebay.co.uk/itm/" in key else it["url"],
                                          source=label, first_seen=now, last_seen=now,
                                          edition=edition(it["title"]) if is_100_7g(it["gen"]) else "")
            new_items.append(state["listings"][key])
        state["listings"][key]["missed"] = 0
    if name in FAST_GONE:
        for v in state["listings"].values():
            if v["source"] == label and v["last_seen"] != now:
                v["missed"] = v.get("missed", 0) + 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", default=None, help="source names to check")
    ap.add_argument("--skip", nargs="*", default=[], help="source names to skip")
    ap.add_argument("--show", action="store_true", help="visible browser")
    ap.add_argument("--login", action="store_true", help="sign in to Facebook in the watcher's browser")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--if-due", type=int, metavar="MIN",
                    help="only run if these sites haven't been checked in MIN minutes")
    ap.add_argument("--no-wait", action="store_true",
                    help="skip this run (instead of waiting) if another check is running")
    args = ap.parse_args()

    if args.login:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(str(PROFILE_DIR), channel=CHANNEL, headless=False, locale="en-GB")
            page = ctx.new_page()
            page.goto("https://www.facebook.com/login")
            input("Sign in in the browser window, then press Enter here to save and close… ")
            ctx.close()
        return

    # only one run at a time (the sites and Facebook jobs can overlap)
    lock = open(DATA / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        if args.no_wait:
            return 0
        log("another check is running; waiting for it to finish")
        fcntl.flock(lock, fcntl.LOCK_EX)

    wanted = [s for s in SOURCES
              if (args.only is None or s["name"] in args.only) and s["name"] not in args.skip]
    check_ebay = (args.only is None or "ebay" in args.only) and "ebay" not in args.skip

    state = load_state()
    if args.if_due:
        # launchd doesn't count sleep time, so jobs fire often and decide here
        cutoff = (datetime.now() - timedelta(minutes=args.if_due)).isoformat()
        names = [s["name"] for s in wanted] + (["ebay"] if check_ebay and (HERE / "ebay.json").exists() else [])
        if all(state["sources"].get(n, {}).get("last_ok", "") > cutoff for n in names):
            return 0
    first_run = not state["listings"]
    now = datetime.now().isoformat(timespec="seconds")
    new_items, alerts = [], []

    if wanted:
        with sync_playwright() as pw:
            ctx = None
            for attempt in (1, 2):
                try:
                    ctx = pw.chromium.launch_persistent_context(
                        str(PROFILE_DIR), channel=CHANNEL, headless=not args.show,
                        locale="en-GB", viewport={"width": 1366, "height": 900}, timeout=90000)
                    break
                except Exception as e:
                    log("couldn't start Chrome (attempt %d): %s" % (attempt, str(e).splitlines()[0][:150]))
                    time.sleep(30)
            if ctx is None:
                log("giving up this run; the next scheduled run will try again")
                return 1
            for src in wanted:
                try:
                    result, err = scrape(ctx, src), None
                except Exception as e:  # one site failing never stops the run
                    result, err = [], str(e).splitlines()[0][:200]
                record(state, src["name"], src["label"], result, err, now, new_items, alerts)
                time.sleep(2)
            ctx.close()

    if check_ebay:
        try:
            result = ebay_api()
            if result is None:
                log("ebay           skipped (no API key; HiFi Shark still covers eBay UK)")
            else:
                record(state, "ebay", "eBay UK", result, None, now, new_items, alerts)
        except Exception as e:
            record(state, "ebay", "eBay UK", [], str(e)[:200], now, new_items, alerts)

    STATE_FILE.write_text(json.dumps(state, indent=1))
    write_html(state)

    notify_on = not args.no_notify
    special = [it for it in new_items if it.get("edition")]
    for it in special:
        dot = {"Heritage Green LE": "🟢", "Carbon Black LE": "⚫"}.get(it["edition"], "⭐")
        notify("%s %s found! %s" % (dot, it["edition"], it["price"] or ""), "%s · %s" % (it["source"], it["title"][:110]), notify_on,
               url=it["url"], priority=5, tags=["rotating_light"])
    new_items = [it for it in new_items if not it.get("edition")]
    if first_run and new_items:
        notify("Speaker watch is running",
               "Found %d Silver 100 7G listing(s) to start with. Click to see them." % len(new_items), notify_on)
    else:
        for it in new_items[:5]:
            notify("New %s: %s · %s" % (it["gen"].replace(" ?", ""), it["price"] or "price?", it["source"]), it["title"][:120], notify_on,
                   url=it["url"], priority=4, tags=["speaker"])
        if len(new_items) > 5:
            notify("Speaker watch", "…and %d more new listings" % (len(new_items) - 5), notify_on)
    for t, m in alerts:
        notify(t, m, notify_on, priority=2, tags=["warning"])
    log("done: %d new, %d total tracked → %s" % (len(new_items), len(state["listings"]), HTML_FILE.name))


if __name__ == "__main__":
    sys.exit(main())
