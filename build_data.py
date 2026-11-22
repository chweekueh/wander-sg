#!/usr/bin/env python3
"""
wander.sg data pipeline (standard library only — no installs needed).

Builds site/data/places.json and site/data/events.json from:
  1. OpenStreetMap (Overpass API)            -> restaurants, cafes, bars, malls, markets,
                                                museums, attractions, parks, beaches, nature
  2. data.gov.sg — NEA hawker centres        -> every government hawker centre
  3. data.gov.sg — NEA cleaning closures     -> "closed for cleaning" dates
  4. data/manual_listings.csv                 -> your own listings and corrections (always win)
  5. data/events.csv                          -> events you add by hand (past ones drop off)

Google ratings / opening hours are NOT stored here: the site fetches them live (Google's terms).

Usage:
  python scripts/build_data.py                 # fetch everything live, then build
  python scripts/build_data.py --offline DIR   # use saved responses in DIR (for testing)
  python scripts/build_data.py --save DIR      # fetch live and also save raw responses to DIR
"""
import argparse, csv, datetime as dt, html, json, math, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "site", "data")
UA = "wander-sg-data-pipeline/1.0 (side project; contact via GitHub repo)"

OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
HAWKER_DATASET = "d_4a086da0a5553be1d89383cd90d07ecd"     # NEA Hawker Centres (GeoJSON)
CLOSURE_DATASET = "d_bda4baa634dd1cc7a6c7cad5f19e2d68"    # NEA Dates of Hawker Centres Closure

# Neighbourhood centres (same list as the site) — used to give every place an area + region.
AREAS = {
  'Orchard':(1.3040,103.8318,'Central'),'Marina Bay':(1.2830,103.8600,'Central'),'Chinatown':(1.2815,103.8445,'Central'),
  'Tiong Bahru':(1.2855,103.8300,'Central'),'River Valley':(1.2930,103.8380,'Central'),'Civic District':(1.2900,103.8510,'Central'),
  'Bugis & Kampong Glam':(1.3010,103.8570,'Central'),'Little India':(1.3065,103.8510,'Central'),'Bukit Timah':(1.3290,103.8000,'Central'),
  'Holland & Dempsey':(1.3080,103.8030,'Central'),'Novena & Balestier':(1.3230,103.8500,'Central'),'Thomson':(1.3420,103.8300,'Central'),
  'HarbourFront':(1.2650,103.8200,'Central'),'Sentosa':(1.2500,103.8250,'Central'),'Kallang & Dakota':(1.3080,103.8800,'Central'),
  'Katong & Joo Chiat':(1.3060,103.9030,'East'),'East Coast':(1.3030,103.9200,'East'),'Bedok':(1.3240,103.9300,'East'),
  'Tampines':(1.3530,103.9440,'East'),'Changi':(1.3890,103.9880,'East'),'Pasir Ris':(1.3730,103.9490,'East'),
  'Woodlands':(1.4360,103.7860,'North'),'Yishun':(1.4290,103.8350,'North'),'Mandai':(1.4040,103.7900,'North'),'Sembawang':(1.4490,103.8200,'North'),
  'Serangoon':(1.3550,103.8700,'North-East'),'Hougang & Kovan':(1.3600,103.8880,'North-East'),'Punggol':(1.4050,103.9100,'North-East'),
  'Ang Mo Kio & Bishan':(1.3620,103.8450,'North-East'),'Sengkang':(1.3920,103.8950,'North-East'),
  'Jurong':(1.3400,103.7200,'West'),'Clementi':(1.3150,103.7650,'West'),'Pasir Panjang & Queenstown':(1.2850,103.7950,'West'),
  'Bukit Batok':(1.3500,103.7600,'West'),'Choa Chu Kang':(1.3850,103.7450,'West'),
}

# ---------------------------------------------------------------- fetching
def http_get(url, data=None, tries=3, timeout=180):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # network hiccup, rate limit, etc.
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")

OVERPASS_QUERY = """
[out:json][timeout:240];
area["ISO3166-1"="SG"][admin_level=2]->.sg;
(
  nwr["amenity"~"^(restaurant|cafe|bar|pub|food_court|ice_cream)$"]["name"](area.sg);
  nwr["shop"~"^(mall|department_store)$"]["name"](area.sg);
  nwr["amenity"="marketplace"]["name"](area.sg);
  nwr["tourism"~"^(museum|gallery|attraction|viewpoint|zoo|theme_park|aquarium)$"]["name"](area.sg);
  nwr["leisure"~"^(park|nature_reserve|garden|beach_resort)$"]["name"](area.sg);
  nwr["natural"="beach"]["name"](area.sg);
  nwr["historic"="monument"]["name"](area.sg);
);
out center tags;
"""

def fetch_osm():
    body = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    err = None
    for u in OVERPASS_URLS:
        try:
            return json.loads(http_get(u, data=body))
        except Exception as e:
            err = e
    raise RuntimeError(f"Overpass unavailable: {err}")

def fetch_datagov(dataset_id):
    meta = json.loads(http_get(f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"))
    if meta.get("code") != 0:
        raise RuntimeError(f"data.gov.sg error for {dataset_id}: {meta.get('errMsg')}")
    raw = http_get(meta["data"]["url"])
    text = raw.decode("utf-8-sig")
    try:
        return json.loads(text)          # GeoJSON datasets
    except json.JSONDecodeError:
        return list(csv.DictReader(text.splitlines()))  # CSV datasets

# ---------------------------------------------------------------- helpers
def km(a_lat, a_lng, b_lat, b_lng):
    r = math.pi / 180
    d = math.sin((b_lat - a_lat) * r / 2) ** 2 + math.cos(a_lat * r) * math.cos(b_lat * r) * math.sin((b_lng - a_lng) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(d))

def nearest_area(lat, lng):
    name = min(AREAS, key=lambda k: km(lat, lng, AREAS[k][0], AREAS[k][1]))
    return name, AREAS[name][2]

def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\b(the|singapore|sg|pte|ltd|restaurant|cafe|café|food centre|food center|market|hawker centre)\b", " ", s)
    return " ".join(re.findall(r"[a-z0-9]+", s))

def match_score(a_name, a_lat, a_lng, b_name, b_lat, b_lng, max_km=0.2):
    """0 = different places. Higher = more likely the same place (name overlap, then closeness)."""
    d = km(a_lat, a_lng, b_lat, b_lng)
    if d > max_km:
        return 0
    a, b = set(norm(a_name).split()), set(norm(b_name).split())
    if not a or not b:
        return 0
    jac = len(a & b) / len(a | b)
    if jac >= 0.75 or (a == b):
        return jac + (max_km - d)
    return 0

def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:60]

TODAY = dt.date.today()

# ---------------------------------------------------------------- OpenStreetMap -> places
CUISINE_MAP = {"chinese":"chinese","cantonese":"chinese","hainanese":"chinese","teochew":"chinese","dim_sum":"chinese","sichuan":"chinese",
  "indian":"indian","north_indian":"indian","south_indian":"indian","malay":"malay","indonesian":"malay","japanese":"japanese","sushi":"japanese",
  "ramen":"japanese","peranakan":"peranakan","seafood":"seafood","western":"western","american":"western","italian":"western","pizza":"western",
  "burger":"western","french":"western","steak_house":"western","local":"local","singaporean":"local","coffee_shop":"cafe","coffee":"cafe",
  "korean":"korean","thai":"thai","vietnamese":"vietnamese"}

def classify(t):
    """Return (cat, sub, type_label) or None to skip."""
    a, sh, to, le, na, hi = t.get("amenity"), t.get("shop"), t.get("tourism"), t.get("leisure"), t.get("natural"), t.get("historic")
    if a == "restaurant": return ("eat", "restaurant", "Restaurant")
    if a == "cafe": return ("eat", "cafe", "Café")
    if a in ("bar", "pub"): return ("eat", "bar", "Bar")
    if a == "ice_cream": return ("eat", "cafe", "Dessert")
    if a == "food_court": return ("eat", "hawker", "Food court")
    if a == "marketplace": return ("shop", "market", "Market")
    if sh in ("mall", "department_store"): return ("shop", "mall", "Mall" if sh == "mall" else "Department store")
    if to in ("museum", "gallery"): return ("see", "museum", "Museum" if to == "museum" else "Gallery")
    if to in ("zoo", "theme_park", "aquarium"): return ("see", "attraction", {"zoo":"Zoo","theme_park":"Theme park","aquarium":"Aquarium"}[to])
    if to == "attraction": return ("see", "attraction", "Attraction")
    if to == "viewpoint": return ("see", "landmark", "Viewpoint")
    if hi == "monument": return ("see", "landmark", "Monument")
    if le == "nature_reserve": return ("do", "trail", "Nature reserve")
    if le in ("park", "garden"): return ("do", "park", "Park" if le == "park" else "Garden")
    if le == "beach_resort" or na == "beach": return ("do", "beach", "Beach")
    return None

def osm_attrs(t, cat, sub):
    """Attributes + where each came from (shown on the site)."""
    at = {}
    def put(k, why): at[k] = {"source": f"OpenStreetMap ({why})", "confidence": "Medium"}
    if t.get("dog") in ("yes", "leashed"): put("dog", f"dog={t['dog']}")
    if t.get("wheelchair") == "yes": put("access", "wheelchair=yes")
    if t.get("diet:vegetarian") in ("yes", "only") or t.get("diet:vegan") in ("yes", "only"): put("veg", "diet:vegetarian")
    if t.get("outdoor_seating") == "yes": put("outdoor", "outdoor_seating=yes")
    if t.get("opening_hours", "").strip() == "24/7": put("late", "opening_hours=24/7")
    if t.get("indoor") == "yes": put("indoor", "indoor=yes")
    if (sub in ("mall", "museum") or t.get("building")) and "indoor" not in at and cat in ("shop", "see") and sub != "landmark":
        at["indoor"] = {"source": "Inferred from place type", "confidence": "High"}
    if cat == "do" and "outdoor" not in at:
        at["outdoor"] = {"source": "Inferred from place type", "confidence": "High"}
    return at

def osm_price(t, cat):
    if t.get("fee") == "no" or (cat == "do" and t.get("fee") != "yes"): return 0
    return None   # unknown: OSM rarely has prices

def places_from_osm(data):
    out = []
    for el in data.get("elements", []):
        t = el.get("tags", {})
        name = t.get("name:en") or t.get("name")
        if not name: continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None: continue
        c = classify(t)
        if not c: continue
        cat, sub, label = c
        area, region = nearest_area(lat, lng)
        cu = sorted({CUISINE_MAP[x.strip()] for x in t.get("cuisine", "").split(";") if x.strip() in CUISINE_MAP})
        out.append({
            "id": f"osm-{el['type'][0]}{el['id']}", "name": name, "cat": cat, "sub": sub, "type": label,
            "area": area, "region": region, "lat": round(lat, 6), "lng": round(lng, 6),
            "price": osm_price(t, cat), "attrs": osm_attrs(t, cat, sub), "cuisine": cu,
            "website": t.get("website") or t.get("contact:website") or "", "rec": "", "desc": "",
            "sources": ["OpenStreetMap"], "checked": TODAY.isoformat(), "sample": False,
        })
    return out

# ---------------------------------------------------------------- data.gov.sg hawkers + closures
def _desc_field(desc_html, field):
    m = re.search(rf"<th>\s*{field}\s*</th>\s*<td>(.*?)</td>", desc_html or "", re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else ""

def places_from_hawkers(geo):
    out = []
    for f in geo.get("features", []):
        p, g = f.get("properties", {}), f.get("geometry", {})
        if g.get("type") != "Point": continue
        lng, lat = g["coordinates"][:2]
        desc = p.get("Description", "")
        name = p.get("NAME") or _desc_field(desc, "NAME")
        status = (p.get("STATUS") or _desc_field(desc, "STATUS") or "Existing").lower()
        if not name or "existing" not in status: continue   # skip proposed / under construction
        blurb = p.get("DESCRIPTION") or _desc_field(desc, "DESCRIPTION")
        area, region = nearest_area(lat, lng)
        out.append({
            "id": "nea-" + slug(name), "name": name, "cat": "eat", "sub": "hawker", "type": "Hawker centre",
            "area": area, "region": region, "lat": round(lat, 6), "lng": round(lng, 6), "price": 1,
            "attrs": {}, "cuisine": ["local"], "website": "https://www.nea.gov.sg", "rec": "",
            "desc": blurb if blurb and len(blurb) > 15 else "", "sources": ["NEA via data.gov.sg"],
            "checked": TODAY.isoformat(), "sample": False,
        })
    return out

def _parse_date(s):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try: return dt.datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None

def closures_by_name(rows):
    """Return {normalised name: (start, end)} for the next/current cleaning closure."""
    res = {}
    for r in rows:
        name = r.get("name") or r.get("Name") or ""
        best = None
        for q in ("q1", "q2", "q3", "q4"):
            s, e = _parse_date(r.get(f"{q}_cleaningstartdate")), _parse_date(r.get(f"{q}_cleaningenddate"))
            if s and e and e >= TODAY and (best is None or s < best[0]):
                best = (s, e)
        s, e = _parse_date(r.get("other_works_startdate")), _parse_date(r.get("other_works_enddate"))
        if s and e and e >= TODAY and (best is None or s < best[0]):
            best = (s, e)
        if name and best:
            res[norm(name)] = best
    return res

# ---------------------------------------------------------------- manual sheet
ATTR_LABELS = ["indoor","outdoor","family","dog","access","business","date","late","veg","groups"]
CAT_FROM_LABEL = {"eat":"eat","see":"see","shop":"shop","do & outdoors":"do","do":"do","outdoors":"do"}

def load_manual(path):
    if not os.path.exists(path): return []
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            name = (r.get("Name") or "").strip()
            if not name: continue
            try:
                lat, lng = float(r["Latitude"]), float(r["Longitude"])
            except (KeyError, ValueError):
                print(f"  ! skipped manual row without coordinates: {name}", file=sys.stderr); continue
            cat = CAT_FROM_LABEL.get((r.get("Category") or "").strip().lower())
            if not cat:
                print(f"  ! skipped manual row with unknown category: {name}", file=sys.stderr); continue
            pr = (r.get("Price") or "").strip().lstrip("'")
            price = 0 if pr.lower() == "free" else (len(pr) if pr and set(pr) == {"$"} else None)
            area = (r.get("Area") or "").strip()
            region = AREAS[area][2] if area in AREAS else nearest_area(lat, lng)[1]
            if area not in AREAS: area = nearest_area(lat, lng)[0]
            typ = (r.get("Type") or "").strip()
            status = (r.get("Status") or "").lower()
            attrs = {a: {"source": "Manual listing (to verify)", "confidence": "Sample" if "sample" in status or "real place" in status else "Medium"}
                     for a in (r.get("Attributes") or "").split() if a in ATTR_LABELS}
            out.append({
                "id": (r.get("ID") or "").strip() or slug(name), "name": name, "cat": cat, "sub": guess_sub(cat, typ),
                "type": typ or cat.title(), "area": area, "region": region, "lat": lat, "lng": lng, "price": price,
                "attrs": attrs, "cuisine": [c.strip() for c in (r.get("Cuisine") or "").split(",") if c.strip()],
                "website": (r.get("Website") or "").strip(), "rec": (r.get("Official designation") or "").strip(),
                "desc": (r.get("Description (AI-written)") or r.get("Description") or "").strip(),
                "sources": ["Manual listing"], "checked": TODAY.isoformat(), "sample": "fictional" in status,
            })
    return out

def guess_sub(cat, typ):
    t = typ.lower()
    rules = {"eat":[("hawker","hawker"),("food centre","hawker"),("food court","hawker"),("café","cafe"),("cafe","cafe"),("bakery","cafe"),("kopitiam","cafe"),("bar","bar")],
             "see":[("museum","museum"),("gallery","museum"),("temple","temple"),("mosque","temple"),("church","temple"),("landmark","landmark"),("observation","landmark"),("monument","landmark"),("arts centre","landmark")],
             "shop":[("market","market"),("street","street"),("lane","street"),("enclave","street")],
             "do":[("park","park"),("garden","park"),("trail","trail"),("reserve","trail"),("nature","trail"),("beach","beach"),("island","beach")]}
    for k, v in rules.get(cat, []):
        if k in t: return v
    return {"eat":"restaurant","see":"attraction","shop":"mall","do":"activity"}[cat]

# ---------------------------------------------------------------- events
def load_events(path, places_by_id):
    if not os.path.exists(path): return []
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            name = (r.get("Name") or "").strip()
            s, e = _parse_date(r.get("Start date")), _parse_date(r.get("End date") or r.get("Start date"))
            if not name or not s: continue
            if (e or s) < TODAY: continue                    # automatic expiry
            v = places_by_id.get((r.get("Venue ID") or "").strip())
            try:
                lat, lng = (v["lat"], v["lng"]) if v else (float(r["Latitude"]), float(r["Longitude"]))
            except (KeyError, ValueError, TypeError):
                print(f"  ! skipped event without venue or coordinates: {name}", file=sys.stderr); continue
            area, region = (v["area"], v["region"]) if v else nearest_area(lat, lng)
            pr = (r.get("Price") or "").strip().lstrip("'")
            out.append({"id": slug(name) + "-" + s.isoformat(), "name": name, "sub": (r.get("Type") or "market").strip().lower(),
                        "venue": v["id"] if v else "", "venueName": v["name"] if v else (r.get("Venue name") or "").strip(),
                        "area": area, "region": region, "lat": lat, "lng": lng, "start": s.isoformat(), "end": (e or s).isoformat(),
                        "time": (r.get("Time") or "").strip(), "price": 0 if pr.lower() == "free" else (len(pr) if pr and set(pr) == {"$"} else None),
                        "attrs": {a: {"source": "Event listing", "confidence": "Medium"} for a in (r.get("Attributes") or "").split() if a in ATTR_LABELS},
                        "desc": (r.get("Description") or "").strip(), "ticket": (r.get("Ticket link") or "").strip(),
                        "source": (r.get("Source link") or "").strip()})
    return out

# ---------------------------------------------------------------- merge
def merge(osm, hawkers, closures, manual):
    places = []
    # 1. NEA hawkers are authoritative for hawker centres; drop OSM food courts that duplicate them
    for h in hawkers:
        c = closures.get(norm(h["name"]))
        if c: h["closure"] = {"start": c[0].isoformat(), "end": c[1].isoformat()}
        places.append(h)
    for o in osm:
        if o["sub"] == "hawker" and any(km(o["lat"], o["lng"], h["lat"], h["lng"]) < 0.15 for h in hawkers):
            continue
        places.append(o)
    # 2. Manual listings win: merge into a matching place, or add as new
    taken = set()
    for m in manual:
        hit, best = None, 0
        if not m["sample"]:
            for p in places:
                if p["cat"] != m["cat"] or id(p) in taken: continue
                sc = match_score(p["name"], p["lat"], p["lng"], m["name"], m["lat"], m["lng"])
                if sc > best: hit, best = p, sc
        if hit:
            taken.add(id(hit))
            keep_id, keep_closure, attrs, srcs = hit["id"], hit.get("closure"), {**hit["attrs"], **m["attrs"]}, set(hit["sources"])
            hit.update({k: v for k, v in m.items() if v not in ("", None, [], {})})
            hit["id"], hit["attrs"], hit["sources"] = m["id"] or keep_id, attrs, sorted(srcs | set(m["sources"]))
            if keep_closure: hit["closure"] = keep_closure
        else:
            places.append(m)
    # 3. Unique ids
    seen = {}
    for p in places:
        if p["id"] in seen:
            seen[p["id"]] += 1; p["id"] = f"{p['id']}-{seen[p['id']]}"
        else:
            seen[p["id"]] = 0
    places.sort(key=lambda p: (p["cat"], p["name"].lower()))
    return places

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", help="folder with saved osm.json, hawkers.json, closures.json")
    ap.add_argument("--save", help="folder to save raw responses into")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    def get(name, fn):
        if args.offline:
            with open(os.path.join(args.offline, name), encoding="utf-8") as f: return json.load(f)
        data = fn()
        if args.save:
            os.makedirs(args.save, exist_ok=True)
            with open(os.path.join(args.save, name), "w", encoding="utf-8") as f: json.dump(data, f)
        return data

    print("Fetching OpenStreetMap…");  osm = places_from_osm(get("osm.json", fetch_osm))
    print("Fetching NEA hawker centres…"); hawkers = places_from_hawkers(get("hawkers.json", lambda: fetch_datagov(HAWKER_DATASET)))
    print("Fetching NEA closures…")
    try:
        closures = closures_by_name(get("closures.json", lambda: fetch_datagov(CLOSURE_DATASET)))
    except Exception as e:   # closures are nice-to-have; never block the build
        print(f"  ! closures unavailable ({e}); continuing without", file=sys.stderr); closures = {}
    manual = load_manual(os.path.join(ROOT, "data", "manual_listings.csv"))
    places = merge(osm, hawkers, closures, manual)
    events = load_events(os.path.join(ROOT, "data", "events.csv"), {p["id"]: p for p in places})

    # Sanity checks: refuse to publish a broken build (the old data stays live instead)
    if len(osm) < 200 or len(hawkers) < 50:
        sys.exit(f"Build refused: suspiciously little data (OSM {len(osm)}, hawkers {len(hawkers)}). Old data kept.")

    os.makedirs(args.out, exist_ok=True)
    meta = {"built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "counts": {"osm": len(osm), "hawkers": len(hawkers), "closures": len(closures), "manual": len(manual), "places": len(places), "events": len(events)}}
    with open(os.path.join(args.out, "places.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "places": places}, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(args.out, "events.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "events": events}, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    main()
