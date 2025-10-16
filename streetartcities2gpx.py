#!/usr/bin/env python3
# json2gpx.py
# Merge one or more JSON sources (files and/or URLs) into a single GPX 1.1.

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from html import escape as xmlesc
from urllib.parse import urlparse

def esc(s: str) -> str:
    return xmlesc("" if s is None else str(s), quote=True)

def load_input(src: str) -> dict:
    if src.lower().startswith(("http://", "https://")):
        with urllib.request.urlopen(src) as r:
            return json.loads(r.read().decode("utf-8", errors="strict"))
    p = Path(src)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def build_wpt(item: dict) -> str | None:
    loc = item.get("location") or {}
    lat = loc.get("lat")
    lon = loc.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None

    title = item.get("title") or ""
    href = item.get("href") or ""
    marker = item.get("marker") or ""
    addr = loc.get("address") or ""
    typ = item.get("type") or ""
    status = item.get("status") or ""
    site_id = item.get("siteId") or ""
    iid = item.get("id") or ""

    desc_parts = []
    if addr:
        desc_parts.append(addr)
    if marker:
        desc_parts.append(f"marker: {marker}")
    desc = "\n".join(desc_parts)

    link_block = (
        f'\n    <link href="{esc(href)}"><text>{esc(title or iid or href)}</text></link>'
        if href else ""
    )

    ext_fields = []
    if iid:     ext_fields.append(f"<sa:id>{esc(iid)}</sa:id>")
    if site_id: ext_fields.append(f"<sa:siteId>{esc(site_id)}</sa:siteId>")
    if status:  ext_fields.append(f"<sa:status>{esc(status)}</sa:status>")
    if marker:  ext_fields.append(f"<sa:marker>{esc(marker)}</sa:marker>")
    extensions_block = (
        "\n    <extensions>\n      " + "".join(ext_fields) + "\n    </extensions>"
        if ext_fields else ""
    )

    type_block = f"\n    <type>{esc(typ)}</type>" if typ else ""

    return (
        f'  <wpt lat="{lat}" lon="{lon}">\n'
        f"    <name>{esc(title or iid or 'Untitled')}</name>"
        f"{link_block}\n"
        f"    <desc>{esc(desc)}</desc>"
        f"{type_block}"
        f"{extensions_block}\n"
        f"  </wpt>"
    )

def build_gpx(items: list, meta_any: dict | None) -> str:
    now_iso = datetime.now(timezone.utc).astimezone().isoformat()
    gen = (meta_any or {}).get("generator") or "json2gpx"
    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1"\n'
        f'     creator="{esc(gen)}"\n'
        '     xmlns="http://www.topografix.com/GPX/1/1"\n'
        '     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '     xmlns:sa="https://streetart.media/ns/1.0"\n'
        '     xsi:schemaLocation="http://www.topografix.com/GPX/1/1\n'
        '                         http://www.topografix.com/GPX/1/1/gpx.xsd">\n'
        "  <metadata>\n"
        f"    <time>{esc(now_iso)}</time>\n"
        "  </metadata>\n"
    )
    wpts = [w for w in (build_wpt(x) for x in items) if w]
    tail = "\n</gpx>\n"
    return head + "\n".join(wpts) + tail

def derive_output_path(sources: list[str], explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    first = sources[0]
    if first.lower().startswith(("http://", "https://")):
        parsed = urlparse(first)
        stem = Path(parsed.path).stem or "merged"
        return Path(f"{stem}_merged.gpx") if len(sources) > 1 else Path(f"{stem}.gpx")
    else:
        p = Path(first)
        return (p.with_name(p.stem + "_merged.gpx") if len(sources) > 1
                else p.with_suffix(".gpx"))

def item_dedup_key(item: dict):
    # Prefer stable 'id' if present; fall back to (lat, lng, title).
    iid = item.get("id")
    if iid is not None:
        return ("id", str(iid))
    loc = item.get("location") or {}
    lat = loc.get("lat"); lon = loc.get("lng")
    title = item.get("title") or ""
    return ("geo", f"{lat:.7f}" if isinstance(lat,(int,float)) else None,
                  f"{lon:.7f}" if isinstance(lon,(int,float)) else None,
                  title)

def main():
    ap = argparse.ArgumentParser(
        description="Merge JSON sources (items[]) into a single GPX 1.1 of waypoints."
    )
    ap.add_argument("sources", nargs="+", help="One or more URLs and/or local JSON file paths")
    ap.add_argument("-o", "--output", help="Output GPX file path (default: derived from first source)")
    ap.add_argument("--no-dedup", action="store_true", help="Disable deduplication of items")
    args = ap.parse_args()

    all_items = []
    any_meta = None
    for src in args.sources:
        try:
            data = load_input(src)
        except Exception as e:
            print(f"Error reading {src}: {e}", file=sys.stderr)
            sys.exit(1)
        items = data.get("items") or []
        if not isinstance(items, list):
            print(f"{src}: items[] missing or not a list", file=sys.stderr)
            sys.exit(2)
        if any_meta is None:
            any_meta = data.get("@meta")
        all_items.extend(items)

    if not args.no_dedup:
        seen = set()
        deduped = []
        for it in all_items:
            k = item_dedup_key(it)
            if k in seen:
                continue
            seen.add(k)
            deduped.append(it)
        all_items = deduped

    gpx = build_gpx(all_items, any_meta)
    out_path = derive_output_path(args.sources, args.output)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(gpx)
    print(f"✅ Saved GPX to {out_path.resolve()}  (waypoints: {gpx.count('<wpt ')})")

if __name__ == "__main__":
    main()
