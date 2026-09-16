"""Page-by-page downloader for the public report ledger on ghush.site.

Standard library only. Writes newline-delimited JSON so a run can be stopped
and resumed without losing or duplicating records.

    python scraper.py                 # full run
    python scraper.py --incremental   # top-up run: stop once records repeat
    python scraper.py --max-records 200   # try a slice first
"""

import argparse
import json
import logging
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.ghush.site"
REPORTS_URL = BASE + "/api/reports"
SUMMARY_URL = BASE + "/api/reports/summary"

RAW_DIR = os.path.join("data", "raw")
RAW_FILE = os.path.join(RAW_DIR, "reports_raw.jsonl")
SUMMARY_FILE = os.path.join(RAW_DIR, "summary.json")
LOG_FILE = os.path.join("logs", "scraper.log")

USER_AGENT = "ghush-public-data-collection/1.0 (research; contact via project owner)"

log = logging.getLogger("scraper")


def setup_logging():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    for handler in (logging.FileHandler(LOG_FILE, encoding="utf-8"),
                    logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        log.addHandler(handler)


def get_json(url, attempts=5):
    """GET with exponential backoff. Honours Retry-After when the server sends it."""
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 4xx other than rate limiting will not fix themselves.
            if exc.code in (400, 401, 403, 404):
                log.error("HTTP %s on %s - not retrying", exc.code, url)
                raise
            wait = float(exc.headers.get("Retry-After") or 0) or min(60, 2 ** attempt)
            log.warning("HTTP %s on attempt %d/%d, sleeping %.1fs",
                        exc.code, attempt, attempts, wait)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            wait = min(60, 2 ** attempt)
            log.warning("%s on attempt %d/%d, sleeping %.1fs",
                        type(exc).__name__, attempt, attempts, wait)
        if attempt < attempts:
            time.sleep(wait + random.uniform(0, 1))
    raise RuntimeError("giving up on %s after %d attempts" % (url, attempts))


def load_seen_ids():
    """Resume support: ids already on disk are never fetched or written twice."""
    seen = set()
    if not os.path.exists(RAW_FILE):
        return seen
    with open(RAW_FILE, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                log.warning("skipping malformed line %d in %s", line_no, RAW_FILE)
    return seen


def fetch_page(offset, limit, sort):
    query = urllib.parse.urlencode({"offset": offset, "limit": limit, "sort": sort})
    return get_json("%s?%s" % (REPORTS_URL, query))


def scrape(limit, sort, delay, max_records, max_passes, stop_after_known):
    os.makedirs(RAW_DIR, exist_ok=True)

    summary = get_json(SUMMARY_URL)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    expected = summary.get("totals", {}).get("count")
    log.info("summary saved; site reports %s published records", expected)

    seen = load_seen_ids()
    if seen:
        log.info("resuming: %d records already on disk", len(seen))

    scraped_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    added_total = 0

    with open(RAW_FILE, "a", encoding="utf-8") as out:
        # A pass walks the whole ledger. Because `sort=newest` shifts every
        # offset down when a new report is published mid-run, one pass can skip
        # records. Extra passes re-walk and the id set absorbs the overlap.
        for pass_no in range(1, max_passes + 1):
            offset, total, added_this_pass, known_streak = 0, None, 0, 0

            while True:
                page = fetch_page(offset, limit, sort)
                reports = page.get("reports", [])
                total = page.get("total", total)

                if not reports:
                    break

                added_this_page = 0
                for report in reports:
                    rid = report.get("id")
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    report["_scraped_at"] = scraped_at
                    out.write(json.dumps(report, ensure_ascii=False) + "\n")
                    added_this_page += 1
                    added_this_pass += 1
                    added_total += 1

                out.flush()
                known_streak = 0 if added_this_page else known_streak + 1
                # Advance by what the server actually returned, so a server-side
                # cap on `limit` cannot make us skip rows.
                offset += len(reports)
                log.info("pass %d | offset %d/%s | +%d new | %d unique total",
                         pass_no, offset, total, added_this_pass, len(seen))

                if max_records and len(seen) >= max_records:
                    log.info("reached --max-records %d, stopping", max_records)
                    return len(seen), total
                # Top-up mode. Under sort=newest, new reports sit at the front,
                # so a run of all-known pages means we are past them.
                if stop_after_known and known_streak >= stop_after_known:
                    log.info("%d consecutive pages with nothing new, stopping "
                             "(--incremental); %d new record(s) this run",
                             known_streak, added_total)
                    return len(seen), total
                if total is not None and offset >= total:
                    break

                time.sleep(delay + random.uniform(0, delay * 0.3))

            log.info("pass %d complete: %d new, %d unique of %s",
                     pass_no, added_this_pass, len(seen), total)

            if total is None or len(seen) >= total or added_this_pass == 0:
                break
            log.info("short by %d records, starting another pass", total - len(seen))

    return len(seen), total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50,
                        help="records per request (server may cap this; default 50)")
    parser.add_argument("--sort", default="newest")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds between requests (default 1.0)")
    parser.add_argument("--max-records", type=int, default=0,
                        help="stop after N unique records; 0 means no limit")
    parser.add_argument("--max-passes", type=int, default=3,
                        help="reconciliation passes to fill gaps (default 3)")
    parser.add_argument("--incremental", nargs="?", type=int, const=3, default=0,
                        metavar="PAGES",
                        help="top-up run: stop after PAGES consecutive pages "
                             "with no new records (default 3). Much faster than "
                             "a full re-walk, but see README on late-moderated "
                             "reports.")
    args = parser.parse_args()

    setup_logging()
    log.info("starting: limit=%d sort=%s delay=%.1fs", args.limit, args.sort, args.delay)
    started = time.time()

    try:
        collected, total = scrape(args.limit, args.sort, args.delay,
                                  args.max_records, args.max_passes,
                                  args.incremental)
    except Exception as exc:
        log.exception("run failed: %s", exc)
        return 1

    log.info("done in %.1fs: %d unique records of %s reported, written to %s",
             time.time() - started, collected, total, RAW_FILE)
    if total and collected < total and not args.incremental:
        log.warning("collected %d of %d - rerun to fill the gap", collected, total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
