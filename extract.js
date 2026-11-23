() => {
  // Finds links to Silver 50 / 100 listings and the price belonging to each.
  const want = /silver[^a-z0-9]{0,6}(series[^a-z0-9]{0,3})?(\d{1,2}\s*g[^a-z0-9]{1,3})?(50|100)(?!\d)|silver[^a-z0-9]{0,6}(50|100)\d{1,2}\s*g/i;
  const money = /(£|€|US\$|\$)\s?\d[\d,]*(\.\d{2})?/;
  // The selling price: skip savings, RRPs, old prices and finance amounts
  // ("Save £300", "RRP/SRP £1699", "Original price was: £1,500", "£25 per month").
  const NOT_BEFORE = /(save|saving|rrp|srp|was|original price|off|deposit|from|up to|club price|member price|worth)[\s:\/a-z]{0,6}$/i;
  const NOT_AFTER = /^\s*(off|per month|a month|p\/?m|\/\s*mo|monthly|saving|deposit|free|gift|voucher|cashback|credit|bonus|worth|trade[- ]?in)/i;
  const sellingPrice = (text) => {
    const re = /(£|€|US\$|\$)\s?\d[\d,]*(\.\d{2})?/g;
    let m;
    while ((m = re.exec(text))) {
      const before = text.slice(Math.max(0, m.index - 20), m.index);
      const after = text.slice(m.index + m[0].length, m.index + m[0].length + 12);
      if (NOT_BEFORE.test(before) || NOT_AFTER.test(after)) continue;
      return m[0].replace(/\s/g, '');
    }
    return null;
  };
  const titleOf = (a) => {
    const img = a.querySelector('img[alt]');
    let t = (a.innerText || '').trim();
    if (!want.test(t)) t = a.getAttribute('aria-label') || a.title || (img && img.alt) || '';
    return t.replace(/\s+/g, ' ').replace(/\s*product image$/i, '').trim();
  };
  const links = [...document.querySelectorAll('a[href]')].filter(a => want.test(titleOf(a)));
  const out = [], seen = new Set();
  for (const a of links) {
    const title = titleOf(a);
    const href = a.href.split('#')[0];
    if (seen.has(href)) continue;
    seen.add(href);
    let price = null, ctx = '';
    // 1. a price in the link text itself (HiFi Shark, Facebook)
    const own = sellingPrice(a.innerText || '');
    if (own) {
      price = own;
      ctx = (a.innerText || '').replace(/\s+/g, ' ').slice(0, 300);
    } else {
      // 2. otherwise climb to the listing's card, but stop as soon as the
      //    container also holds a *different* listing: its price isn't ours.
      let el = a.parentElement;
      for (let i = 0; i < 7 && el; i++, el = el.parentElement) {
        const others = links.some(o => o.href.split('#')[0] !== href && el.contains(o));
        if (others) break;
        const t = el.innerText || '';
        if (t.length > 1500) break;
        const m = sellingPrice(t);
        if (m) { price = m; ctx = t.replace(/\s+/g, ' ').slice(0, 300); break; }
      }
    }
    // the whole card (largest container holding only this listing), for
    // labels like "Clearance - Manchester" or "IN-STORE CLEARANCE"
    let card = '', c = a.parentElement;
    for (let i = 0; i < 7 && c; i++, c = c.parentElement) {
      if (links.some(o => o.href.split('#')[0] !== href && c.contains(o))) break;
      const t = c.innerText || '';
      if (t.length > 1500) break;
      card = t.replace(/\s+/g, ' ').slice(0, 600);
    }
    out.push({title: title.slice(0, 200), url: href, price, ctx, card});
  }
  return out;
}
