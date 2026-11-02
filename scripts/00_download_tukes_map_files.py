"""
00 — Download Tukes mining-register map files.

WHAT THIS DOES
    Tukes (the Finnish Safety and Chemicals Agency) publishes the mining-register
    cadastre as downloadable ZIP files (TAB / MIF / SHP) in ETRS-TM35FIN
    (EPSG:3067). This script:
        1. reads configs/config.yaml
        2. fetches the Tukes map-files ATOM feed (the machine-readable list)
        3. finds the ZIP links for the layers we care about (see layer_keywords)
        4. downloads them into data/raw/tukes_zip/
        5. extracts them into data/raw/tukes_extracted/<stem>/
        6. writes a manifest (CSV + JSON) recording name, URL, timestamps, paths
        7. skips files already downloaded (same name + size)

WHY THE FEED, NOT A FIXED URL
    The ZIP file names are dated (e.g. valtaus_2026-06-02.zip) and rotate, so we
    scrape the feed rather than hard-code brittle links.

FAIL-LOUD BEHAVIOUR
    If no ZIP links are found (e.g. Tukes changed their page structure), we DO NOT
    silently pass. We save the fetched HTML/feed to data/raw/debug/ and print the
    exact URL a human needs to check.

LEGAL NOTE
    These polygons show where exploration reservations, exploration permits, mining
    permits, mining concessions, claims and gold-panning permits already exist.
    They are the legal-availability backbone of Step 1. This is public cadastre
    data, not legal advice — always verify the live register before any outreach.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ensure_dir, get_logger, get_path, load_config  # noqa: E402

log = get_logger("00_download_tukes")

# Match .zip links anywhere in an href/loc, allowing a trailing ?query.
ZIP_HREF_RE = re.compile(r'(?:href|loc)\s*=\s*"([^"]+\.zip[^"]*)"', re.IGNORECASE)
# Also catch bare URLs inside ATOM <link href="..."> / <id> nodes.
ZIP_URL_RE = re.compile(r'https?://[^\s"<>]+\.zip[^\s"<>]*', re.IGNORECASE)


def _fetch(url: str, timeout: int) -> requests.Response:
    """GET a URL with a real User-Agent; raise on HTTP errors."""
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "GeoArb_Finland/0.1 (Step1 cadastre downloader)"},
    )
    resp.raise_for_status()
    return resp


def discover_zip_links(cfg: dict, debug_dir: Path) -> list[str]:
    """
    Return a de-duplicated list of absolute ZIP URLs found in the Tukes feed.

    Tries the ATOM feed first, then the fallback HTML page. Always saves whatever
    it fetched into data/raw/debug/ so a human can inspect on failure.
    """
    base_url = cfg["tukes"]["base_url"]
    timeout = int(cfg["tukes"].get("request_timeout_s", 60))
    candidates = [
        ("tukes_feed.xml", cfg["tukes"]["feed_url"]),
        ("tukes_page.html", cfg["tukes"]["fallback_page_url"]),
    ]

    found: list[str] = []
    for debug_name, url in candidates:
        try:
            log.info("Fetching %s", url)
            resp = _fetch(url, timeout)
        except Exception as exc:  # noqa: BLE001 — we want to keep trying / report
            log.warning("Could not fetch %s: %s", url, exc)
            continue

        # Persist exactly what we received for debugging.
        debug_path = debug_dir / debug_name
        debug_path.write_bytes(resp.content)
        log.info("Saved fetched content -> %s", debug_path)

        text = resp.text
        title = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        if title:
            log.info("Page title: %s", " ".join(title.group(1).split()))

        # Collect both quoted hrefs and bare URLs, make them absolute.
        raw_links = ZIP_HREF_RE.findall(text) + ZIP_URL_RE.findall(text)
        for link in raw_links:
            absolute = urljoin(base_url, link)
            if absolute not in found:
                found.append(absolute)

        if found:
            log.info("Found %d ZIP link(s) in %s", len(found), debug_name)
            break  # got what we need from the first working source

    return found


def _zip_filename(url: str) -> str:
    """Extract a clean .zip filename from a Tukes document URL."""
    # Tukes URLs look like /documents/.../valtaus_2026-06-02.zip/<uuid>?t=...
    # so the real filename is a MIDDLE path segment ending in .zip, not the last one.
    for part in urlparse(url).path.split("/"):
        if part.lower().endswith(".zip"):
            return part
    # Fallback: last path segment.
    return Path(urlparse(url).path).name or "download.zip"


def select_relevant_links(links: list[str], cfg: dict) -> list[str]:
    """Keep only ZIPs whose filename contains one of our layer keywords."""
    keywords = [k.lower() for k in cfg["tukes"]["layer_keywords"]]
    selected = []
    for link in links:
        fname = _zip_filename(link).lower()  # the .zip segment, not the trailing uuid
        if any(kw in fname for kw in keywords):
            selected.append(link)
    return selected


def download_zip(url: str, dest_dir: Path, timeout: int) -> tuple[Path, bool]:
    """
    Download a ZIP to dest_dir. Returns (path, downloaded_now).

    Skips the download if a same-named file already exists with the same size as
    the remote Content-Length (cheap idempotency check).
    """
    fname = _zip_filename(url)
    dest = dest_dir / fname

    # Cheap skip check via HEAD content-length.
    if dest.exists():
        try:
            head = requests.head(url, timeout=timeout, allow_redirects=True,
                                 headers={"User-Agent": "GeoArb_Finland/0.1"})
            remote_size = int(head.headers.get("Content-Length", -1))
        except Exception:  # noqa: BLE001
            remote_size = -1
        if remote_size == -1 or dest.stat().st_size == remote_size:
            log.info("Skip (already downloaded): %s", fname)
            return dest, False

    log.info("Downloading %s", fname)
    resp = _fetch(url, timeout)
    dest.write_bytes(resp.content)
    log.info("  -> %s (%d bytes)", dest, dest.stat().st_size)
    return dest, True


def extract_zip(zip_path: Path, extract_root: Path) -> Path:
    """Extract a ZIP into extract_root/<zip-stem>/ and return that folder."""
    out_dir = extract_root / zip_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        base = out_dir.resolve()
        for member in zf.infolist():
            if not (base / member.filename).resolve().is_relative_to(base):
                raise ValueError("Unsafe archive member path")
        zf.extractall(out_dir)
    log.info("Extracted %s -> %s", zip_path.name, out_dir)
    return out_dir


def write_manifest(records: list[dict], outputs_dir: Path) -> tuple[Path, Path]:
    """Write the download manifest as both JSON and CSV."""
    json_path = outputs_dir / "tukes_download_manifest.json"
    csv_path = outputs_dir / "tukes_download_manifest.csv"

    json_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    fields = ["filename", "url", "zip_path", "extracted_path",
              "size_bytes", "downloaded_now", "timestamp_utc"]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in fields})

    log.info("Manifest written: %s and %s", json_path.name, csv_path.name)
    return json_path, csv_path


def main() -> int:
    cfg = load_config()
    timeout = int(cfg["tukes"].get("request_timeout_s", 60))

    zip_dir = get_path(cfg, "tukes_zip", create=True)
    extract_dir = get_path(cfg, "tukes_extracted", create=True)
    debug_dir = get_path(cfg, "debug", create=True)
    outputs_dir = ensure_dir(cfg["paths"]["raw"])  # manifest lives under data/raw/

    # 1. Discover all ZIP links.
    all_links = discover_zip_links(cfg, debug_dir)
    if not all_links:
        log.error("=" * 70)
        log.error("NO ZIP LINKS FOUND on the Tukes map-files feed.")
        log.error("Tukes may have changed their page structure.")
        log.error("Saved what we fetched into: %s", debug_dir)
        log.error("Please open this URL in a browser and check for ZIP downloads:")
        log.error("  %s", cfg["tukes"]["fallback_page_url"])
        log.error("Human page: https://tukes.fi/en/mining-ore-prospecting-and-gold-panning/map-files")
        log.error("=" * 70)
        return 2  # fail loudly

    # 2. Keep only the layers we care about.
    selected = select_relevant_links(all_links, cfg)
    log.info("Selected %d of %d ZIP link(s) matching layer keywords.",
             len(selected), len(all_links))
    if not selected:
        log.error("Found %d ZIPs but none matched layer_keywords=%s",
                  len(all_links), cfg["tukes"]["layer_keywords"])
        log.error("Links found were:\n  %s", "\n  ".join(all_links))
        return 2

    # 3. Download + extract + record.
    records: list[dict] = []
    for url in selected:
        try:
            zip_path, downloaded_now = download_zip(url, zip_dir, timeout)
            extracted = extract_zip(zip_path, extract_dir)
            records.append({
                "filename": zip_path.name,
                "url": url,
                "zip_path": str(zip_path),
                "extracted_path": str(extracted),
                "size_bytes": zip_path.stat().st_size,
                "downloaded_now": downloaded_now,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:  # noqa: BLE001 — record the failure, keep going
            log.error("Failed on %s: %s", url, exc)
            records.append({
                "filename": _zip_filename(url),
                "url": url,
                "error": str(exc),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            })

    write_manifest(records, outputs_dir)

    ok = [r for r in records if "error" not in r]
    log.info("Done. %d/%d layers downloaded & extracted.", len(ok), len(records))
    # Fail loudly if nothing succeeded.
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
