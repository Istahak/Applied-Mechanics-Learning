"""Turn the raw scrape into a cleaned, analysis-ready dataset.

    python clean.py

Reads  data/raw/reports_raw.jsonl
Writes data/processed/ghush_reports_clean.csv
       data/processed/ghush_reports_clean.parquet   (only if pyarrow is installed)

Every row is an unverified, user-submitted allegation. The `is_verified` column
is hard-coded False so that fact survives into any downstream analysis.
"""

import csv
import json
import os
import re
import sys

RAW_FILE = os.path.join("data", "raw", "reports_raw.jsonl")
OUT_DIR = os.path.join("data", "processed")
CSV_FILE = os.path.join(OUT_DIR, "ghush_reports_clean.csv")
PARQUET_FILE = os.path.join(OUT_DIR, "ghush_reports_clean.parquet")

SOURCE_URL = "https://www.ghush.site/"
HIGH_AMOUNT_THRESHOLD = 10000

COLUMNS = [
    "report_id", "date", "year", "month", "division", "district", "department",
    "service", "amount_bdt", "amount_bucket", "is_high_amount", "outcome",
    "location", "description", "confirmation_count", "is_verified",
    "contact_redacted", "source_url", "scraped_at",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Bangladeshi mobile numbers, in Western or Bengali digits, with optional +88.
PHONE_RE = re.compile(r"(?:\+?৮৮|\+?88)?[০0][১1][০-৯0-9]{9}")


def redact_contacts(text):
    """Drop direct contact details. The narrative is the point, not the phone number."""
    redacted = EMAIL_RE.sub("[email removed]", text)
    redacted = PHONE_RE.sub("[phone removed]", redacted)
    return redacted, redacted != text


def amount_bucket(amount):
    """Mirrors the bands the site itself publishes, so figures stay comparable."""
    if amount is None:
        return "unknown"
    if amount <= 1000:
        return "<=1000"
    if amount <= 5000:
        return "1001-5000"
    if amount <= 10000:
        return "5001-10000"
    return ">10000"


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def transform(record):
    date = clean_text(record.get("created_at"))
    amount = record.get("amount")
    if isinstance(amount, str):
        amount = int(amount) if amount.strip().isdigit() else None

    description, was_redacted = redact_contacts(clean_text(record.get("description")))

    return {
        "report_id": record.get("id"),
        "date": date,
        "year": date[:4] or None,
        "month": date[:7] or None,
        # The API's `district` field carries the division name (8 values);
        # `city` carries the finer locality. Named here as they actually are.
        "division": clean_text(record.get("district")),
        "district": "",
        "department": clean_text(record.get("department")),
        "service": clean_text(record.get("service")),
        "amount_bdt": amount,
        "amount_bucket": amount_bucket(amount),
        "is_high_amount": amount is not None and amount > HIGH_AMOUNT_THRESHOLD,
        "outcome": clean_text(record.get("outcome")),
        "location": clean_text(record.get("city")),
        "description": description,
        "confirmation_count": record.get("confirmation_count"),
        "is_verified": False,
        "contact_redacted": was_redacted,
        "source_url": SOURCE_URL,
        "scraped_at": record.get("_scraped_at"),
    }


def load_raw():
    if not os.path.exists(RAW_FILE):
        sys.exit("No raw data at %s - run scraper.py first." % RAW_FILE)

    rows, seen, skipped = [], set(), 0
    with open(RAW_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            rid = record.get("id")
            if not rid or rid in seen:
                skipped += 1
                continue
            seen.add(rid)
            rows.append(transform(record))
    return rows, skipped


def write_parquet(rows):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print("pyarrow not installed - skipping Parquet "
              "(pip install pyarrow to enable)")
        return
    table = pa.Table.from_pydict({col: [r[col] for r in rows] for col in COLUMNS})
    pq.write_table(table, PARQUET_FILE, compression="snappy")
    print("wrote %s" % PARQUET_FILE)


def main():
    rows, skipped = load_raw()
    if not rows:
        sys.exit("No usable records found in %s" % RAW_FILE)

    rows.sort(key=lambda r: r["date"], reverse=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    # utf-8-sig so the Bengali text opens correctly in Excel.
    with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print("wrote %s (%d rows, %d skipped as duplicate/malformed)"
          % (CSV_FILE, len(rows), skipped))

    write_parquet(rows)

    dated = [r for r in rows if r["date"]]
    amounts = [r["amount_bdt"] for r in rows if r["amount_bdt"] is not None]
    print("\nrows              : %d" % len(rows))
    print("date range        : %s -> %s"
          % (min(r["date"] for r in dated)[:10], max(r["date"] for r in dated)[:10])
          if dated else "date range        : n/a")
    print("divisions         : %d" % len({r["division"] for r in rows if r["division"]}))
    print("departments       : %d" % len({r["department"] for r in rows if r["department"]}))
    print("total amount (BDT): %s" % format(sum(amounts), ","))
    print("high-amount rows  : %d" % sum(1 for r in rows if r["is_high_amount"]))
    print("contacts redacted : %d" % sum(1 for r in rows if r["contact_redacted"]))


if __name__ == "__main__":
    main()
