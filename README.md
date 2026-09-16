# ghush.site public report collection

Downloads the ~19,000 publicly visible reports from https://www.ghush.site/ and
turns them into an analysis-ready dataset.

> **The records are unverified, anonymous, user-submitted allegations.** Nothing
> here is a confirmed fact, and nothing here identifies an individual. See
> [DATA_DICTIONARY.md](DATA_DICTIONARY.md) before analysing anything.

## Read this first: robots.txt

The site's `robots.txt` **disallows the `/api/` path** that this scraper uses:

```
User-Agent: *
Allow: /
Disallow: /api/
```

There is no robots-permitted route to the data — the sitemap lists only two
pages (`/` and `/press`) and the site publishes no per-report page, so the
records exist nowhere a compliant crawler may go. **This collection was run at
the explicit direction of the project owner, overriding that directive.** It is
not sanctioned by the site operator. Anyone re-running it should make that
decision knowingly, and the courteous path remains asking the operator for a
bulk export via their press page or https://ghushsite.userjot.com/.

No authentication, CAPTCHA or access control was bypassed: the endpoint is
unauthenticated and the data is already public in the browser.

## Usage

Requires Python 3.9+ and **no third-party packages**.

```bash
python scraper.py      # downloads everything to data/raw/
python clean.py        # builds the cleaned CSV (+ Parquet if available)
```

Optional, to also emit Parquet:

```bash
pip install pyarrow
```

Useful flags:

```bash
python scraper.py --max-records 200    # small trial slice
python scraper.py --delay 2.0          # gentler on the server
python scraper.py --limit 20           # page size (server caps at 20 anyway)
```

## Topping up with new reports

Re-running later only adds records that are not already on disk, so the safe
default is simply:

```bash
python scraper.py && python clean.py
```

That re-walks all 951 pages (~22 min) and is the thorough option. For a quick
top-up, `--incremental` stops once it hits 3 consecutive pages containing
nothing new — a few seconds instead of 22 minutes:

```bash
python scraper.py --incremental && python clean.py
```

**Use the full run periodically anyway.** Incremental mode relies on new reports
appearing at the front under `sort=newest`. A report that clears moderation late
is published with its original `created_at` and therefore lands *mid-ledger*,
where an early-stopping run will never see it. A monthly full run closes that
gap; the id-based de-duplication means nothing is ever written twice.

`clean.py` always rebuilds the cleaned outputs from the whole raw file, so it
does not need an incremental mode of its own.

## The endpoint

| | |
|---|---|
| Reports | `GET https://www.ghush.site/api/reports?offset=0&limit=20&sort=newest` |
| Summary | `GET https://www.ghush.site/api/reports/summary` |
| Auth | None |
| Response | `{"reports": [...], "total": 19016}` |
| Pagination | Offset/limit |
| **Page size** | **Server caps `limit` at 20**, silently, however much you ask for |
| `sort` | `newest` (also popular / most-confirmed / highest-amount in the UI) |
| Rate limits | **None documented and none advertised in headers.** The 1s default delay is a courtesy, not a measured limit. |

A full run is **951 requests, roughly 18 minutes** at the default delay.

## How it works

`scraper.py`

- Saves `/api/reports/summary` first, as an independent check on the row count.
- Pages with offset/limit, **advancing by the number of records actually
  returned** rather than the number requested, so the undocumented server-side
  cap on `limit` cannot silently skip rows.
- Writes newline-delimited JSON, appending and flushing per page, so a killed
  run loses nothing.
- **Resumes** by reading the ids already on disk; re-running never duplicates.
- **Retries** with exponential backoff and jitter, honouring `Retry-After`.
  Gives up immediately on 400/401/403/404, which will not fix themselves.
- Runs up to 3 reconciliation passes. Under `sort=newest`, a report published
  mid-run shifts every offset and can cause a skip; re-walking closes the gap
  and the id set absorbs the overlap.

`clean.py`

- De-duplicates by `report_id`, tolerating malformed lines.
- Renames fields to the target schema, **notably `district` to `division`** —
  see the dictionary for why that rename matters.
- Adds `month`, `year`, `amount_bucket`, `is_high_amount`.
- Strips emails and Bangladeshi phone numbers from the narrative text and flags
  affected rows in `contact_redacted`.
- Stamps every row `is_verified = False`.

## Output

```
data/raw/reports_raw.jsonl              one JSON record per line, as served
data/raw/summary.json                   site-published aggregate totals
data/processed/ghush_reports_clean.csv  cleaned, utf-8-sig for Excel
data/processed/ghush_reports_clean.parquet   if pyarrow installed
logs/scraper.log                        full run log
```

## Limitations

- **Selection bias makes rates uncomputable.** These are self-selected reports
  from people who chose to use a website. They do not describe the population.
- **`date` is submission time, not incident time.** The ledger spans roughly 26
  days, so this is a snapshot of a young dataset. Trends read into it will be
  artefacts of the site's own launch and publicity.
- **Amounts are claimed, not audited**, and span 1 to 100,000,000 BDT. Use the
  median or the buckets, not the mean.
- **`confirmation_count` is not verification** — it is an anonymous click count.
- **`location` and `service` are unnormalised** free text in two scripts, so
  naive grouping fragments them.
- **The dataset is a moving target.** New reports arrive hourly and moderation
  can remove them, so two runs will not match. `scraped_at` records when each
  row was taken.
- **`district` is always empty.** The API has no true district level.

## What is in this repository

The collection code, the documentation and **the full dataset**.

- `data/processed/ghush_reports_clean.csv` - all 19,016 cleaned rows
- `data/processed/ghush_reports_clean.parquet` - same, columnar
- `data/raw/reports_raw.jsonl` - untouched API responses, one record per line
- `data/raw/summary.json` - the site's own published aggregate totals
- `data/sample/ghush_reports_sample_200.csv` - 200 rows, for a quick look

The data is the site's content, not ours, and is republished here for coursework
under the caveats in DATA_DICTIONARY.md. It remains unverified, anonymous,
user-submitted allegations. See the robots.txt note above.

### Provenance

Collected 2026-09-16. The run captured all 19,016 records then published, and the
totals matched the site's own `/api/reports/summary` exactly: 19,016 records,
5,517,599,701 BDT, 6,680 records above 10,000 BDT.

## License

**The MIT License covers the code in this repository only** - `scraper.py`,
`clean.py` and the documentation.

**It does not cover the data under `data/`.** Those records were submitted by
members of the public to ghush.site and collected from it; they are not ours to
license, and nothing here grants rights over them. Anyone wanting to reuse the
dataset should look to the source site's own terms.
