"""Sites the watcher checks.

Each source is a dict:
  name     – short id, used with --only / --skip
  label    – shown in notifications and the HTML page
  kind     – "retailer" (new / ex-demo) or "marketplace" (used)
  url      – search page; {q} is replaced with the URL-encoded search phrase
  prepare  – optional JavaScript run on the page before listings are read
             (e.g. to switch a filter to UK only)
  wait_ms  – how long to let the page's JavaScript render results

Listings are read with a generic extractor (any link whose text mentions
"Silver 100", with the nearest price), so most sites need no selectors.
"""

# Marketplaces are searched with every phrase (sellers make typos like "1007G");
# shops use only the first one. Add phrases here if you spot another miss.
SEARCHES = ["monitor audio silver 100", "monitor audio silver 1007g",
            "monitor audio silver 100 limited edition", "monitor audio silver 50"]
SEARCH = SEARCHES[0]
SHOP_SEARCHES = [SEARCH, "monitor audio silver 50"]

# What to look for: (model, generation, new price in £ per pair).
# None = any price. Otherwise only listings cheaper than new are kept.
# Titles that don't say which generation count as a possible Silver 100 7G.
TARGETS = [
    ("100", 7, None),
    ("100", 8, 1499),  # new £1,499-£1,500
    ("50", 8, 799),    # new £799-£800
]

SOURCES = [
    # ---- Marketplaces (used) -------------------------------------------
    {
        "name": "facebook",
        "searches": [SEARCHES[0], SEARCHES[1], SEARCHES[3]],  # 100, 1007g typo, 50
        "label": "Facebook Marketplace",
        "kind": "marketplace",
        # Marketplace searches around a city, so we search from several
        # cities to cover the whole UK. Remove any you don't need.
        "urls": [
            "https://www.facebook.com/marketplace/%s/search?query={q}" % city
            for city in ["london", "birmingham", "manchester", "leeds", "bristol", "glasgow", "edinburgh", "cardiff", "belfast"]
        ],
        "wait_ms": 6000,
        # scroll a couple of times so more results load
        "prepare": "async () => { for (let i=0;i<3;i++){ window.scrollBy(0, 2500); await new Promise(r=>setTimeout(r,1500)); } }",
    },
    {
        "name": "gumtree",
        "label": "Gumtree",
        "kind": "marketplace",
        "url": "https://www.gumtree.com/search?q={q}",
    },
    {
        "name": "preloved",
        "label": "Preloved",
        "kind": "marketplace",
        "url": "https://www.preloved.co.uk/search?keyword={q}",
    },
    {
        "name": "vinted",
        "label": "Vinted",
        "kind": "marketplace",
        "url": "https://www.vinted.co.uk/catalog?search_text={q}",
        "wait_ms": 6000,
    },
    {
        "name": "cashconverters",
        "label": "Cash Converters",
        "kind": "marketplace",
        "url": "https://www.cashconverters.co.uk/search-results?query={q}",
        "wait_ms": 6000,
    },
    {
        "name": "shpock",
        "label": "Shpock",
        "kind": "marketplace",
        "url": "https://www.shpock.com/en-gb/results?q={q}",
        "wait_ms": 8000,
    },
    # ---- Retailers (new / ex-demo) --------------------------------------
    {
        # Product pages for the Carbon Black Limited Edition. Both say "no
        # longer available" at the moment; you get an alert if either comes back.
        "name": "richersounds_le",
        "label": "Richer Sounds (LE product pages)",
        "kind": "stockpage",
        "searches": [SEARCH],
        "urls": [
            "https://www.richersounds.com/monitor-audio-silver-100-7g-le-carbon-black-metallic/",
            "https://www.richersounds.com/monitor-audio-silver-100-7g-le-carbon-black-metallic-in-store-clearance/",
        ],
        "unavailable": "no longer available",
    },
    {
        "name": "richersounds",
        "searches": SHOP_SEARCHES,
        "label": "Richer Sounds",
        "kind": "retailer",
        # Their shop search also lists clearance stock (in-store and online)
        "url": "https://www.richersounds.com/search.php?search_query={q}",
        "wait_ms": 8000,
    },
    {
        "name": "premiumsound",
        "searches": SHOP_SEARCHES,
        "label": "Premium Sound",
        "kind": "retailer",
        "url": "https://premiumsound.co.uk/?s={q}&post_type=product",
    },
    {
        "name": "petertyson",
        "searches": SHOP_SEARCHES,
        "label": "Peter Tyson",
        "kind": "retailer",
        "url": "https://petertyson.co.uk/catalogsearch/result/?q={q}",
        "wait_ms": 9000,  # results sometimes load late
    },
    # UK dealers with ex-demo / open-box / sale stock that HiFi Shark doesn't
    # collect. They're searched for "monitor audio silver" (their result lists
    # are short) and the filter keeps only Silver 100 7G.
    {
        # Their search sometimes leaves clearance items out, so read the
        # clearance speaker pages directly too (about 5 pages).
        "name": "petertyson_clearance",
        "label": "Peter Tyson",
        "kind": "retailer",
        "searches": [SEARCH],
        "urls": ["https://petertyson.co.uk/clearance/all-clearance/speakers?p=%d" % n for n in range(1, 8)],
        "wait_ms": 5000,
    },
    {
        "name": "hifix",
        "label": "Hifix",
        "kind": "retailer",
        "searches": ["monitor audio silver"],
        "url": "https://www.hifix.co.uk/?s={q}&post_type=product",
    },
    {
        "name": "audiovenue",
        "label": "Audio Venue",
        "kind": "retailer",
        "searches": ["monitor audio silver"],
        "url": "https://www.audiovenue.co.uk/?s={q}&post_type=product",
    },
    {
        "name": "dougbrady",
        "label": "Doug Brady Hi-Fi",
        "kind": "retailer",
        "searches": ["monitor audio silver"],
        "url": "https://www.dougbradyhifi.com/search?q={q}",
    },
    {
        "name": "hifisound",
        "label": "Hi-Fi Sound",
        "kind": "retailer",
        "searches": ["monitor audio silver"],
        "url": "https://www.hifisound.co.uk/search?q={q}",
    },
    {
        # Their search also lists Outlet stock ("Clearance - <store>", ex-display etc.)
        "name": "sevenoaks",
        "label": "Sevenoaks Sound & Vision",
        "kind": "retailer",
        "searches": SHOP_SEARCHES,
        "url": "https://www.sevenoakssoundandvision.co.uk/cssearch.aspx?searchterm={q}",
        "wait_ms": 6000,
    },
    {
        # Vickers Hi-Fi (York). Also sells used / ex-demo on eBay (shop
        # "vickershifi"), which reaches us through HiFi Shark / the eBay API.
        "name": "vickers",
        "label": "Vickers Hi-Fi",
        "kind": "retailer",
        "searches": SHOP_SEARCHES,
        "url": "https://www.vickershifi.com/Search?SearchString={q}",
        "wait_ms": 6000,
    },
    {
        "name": "vickers_sale",
        "label": "Vickers Hi-Fi",
        "kind": "retailer",
        "searches": [SEARCH],
        "urls": ["https://www.vickershifi.com/sale/sale-ex-dem", "https://www.vickershifi.com/sale/sale-offers"],
        "wait_ms": 6000,
    },
    {
        # Search includes "Warehouse deal" / graded stock
        "name": "quantumav",
        "label": "Quantum AV",
        "kind": "retailer",
        "searches": SHOP_SEARCHES,
        "url": "https://www.quantumav.co.uk/search?q={q}",
        "wait_ms": 6000,
    },
    {
        "name": "quantumav_clearance",
        "label": "Quantum AV",
        "kind": "retailer",
        "searches": [SEARCH],
        "urls": ["https://www.quantumav.co.uk/clearance/speakers?page=%d" % n for n in range(1, 5)],
        "wait_ms": 5000,
    },
    {
        "name": "weybridge",
        "label": "Weybridge Audio",
        "kind": "retailer",
        "searches": SHOP_SEARCHES,
        "url": "https://www.weybridge-audio.co.uk/search?q={q}",
    },
    {
        "name": "referenceaudio",
        "label": "Reference Audio",
        "kind": "retailer",
        "searches": SHOP_SEARCHES,
        "url": "https://www.referenceaudio.co.uk/search?q={q}",
    },
    {
        # Search results include Ex Demo and Pre Owned stock
        "name": "analogueseduction",
        "label": "Analogue Seduction",
        "kind": "retailer",
        "searches": SHOP_SEARCHES,
        "url": "https://www.analogueseduction.net/search/for/{q}/",
        "wait_ms": 6000,
    },
    {
        "name": "amazon",
        "searches": SHOP_SEARCHES,
        "label": "Amazon UK",
        "kind": "retailer",
        "url": "https://www.amazon.co.uk/s?k={q}",
    },
    {
        # HiFi Shark collects second-hand listings from eBay, Gumtree, hi-fi
        # dealers and forums. We switch its country filter to the UK.
        "name": "hifishark",
        "label": "HiFi Shark (eBay UK, dealers, forums)",
        "kind": "marketplace",
        "url": "https://www.hifishark.com/search?q={q}",
        "prepare": """async () => {
            const s = document.querySelector('#countrySelect');
            if (!s || ![...s.options].some(o => o.value === 'GB')) return 'no-uk';
            s.value = 'GB';
            s.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) jQuery(s).trigger('change');
            // wait (up to 20 s) for the UK results to load
            for (let i = 0; i < 40; i++) {
                await new Promise(r => setTimeout(r, 500));
                if (i > 3 && document.querySelectorAll('a.search-product').length) break;
            }
        }""",
        # UK sites show prices in £; anything in € or US$ is from abroad
        "gbp_only": True,
    },
]
