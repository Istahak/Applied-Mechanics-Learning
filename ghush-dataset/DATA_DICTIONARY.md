# Data Dictionary

Dataset: `data/processed/ghush_reports_clean.csv` (and `.parquet`)
Source: public report ledger at https://www.ghush.site/

> **Every row is an unverified allegation submitted anonymously by a member of the
> public.** No row has been confirmed by the site, by any authority, or by this
> pipeline. `confirmation_count` counts anonymous button clicks, not verification.
> Do not present any field here as established fact.

## Columns

| Column | Type | Source | Notes |
|---|---|---|---|
| `report_id` | string (UUID) | `id` | Stable primary key. Used for de-duplication. |
| `date` | ISO 8601 UTC | `created_at` | **Submission time, not incident time.** The site does not collect when the incident occurred. |
| `year` | string | derived | First 4 chars of `date`. |
| `month` | string `YYYY-MM` | derived | First 7 chars of `date`. |
| `division` | string | `district` | **Note the rename.** The API's `district` field holds one of Bangladesh's 8 administrative *divisions* (Dhaka, Chattogram, Rajshahi, Khulna, Rangpur, Mymensingh, Barishal, Sylhet). Always English. |
| `district` | string | — | **Always empty.** The API exposes no true district level. Kept as a column only so the schema matches the requested spec; do not analyse it. |
| `department` | string | `department` | 12 values, always English, e.g. `Land Office`, `Passport Office`, `Other public service`. Safe to group by. |
| `service` | string | `service` | Free text, **mixed Bengali and English**, user-written. High cardinality; needs normalisation before grouping. |
| `amount_bdt` | integer | `amount` | Bangladeshi taka, as claimed by the reporter. Observed range 1 to 100,000,000. |
| `amount_bucket` | string | derived | `<=1000`, `1001-5000`, `5001-10000`, `>10000`, `unknown`. Matches the bands the site publishes, so counts are comparable to its own figures. |
| `is_high_amount` | boolean | derived | `amount_bdt > 10000`. An arbitrary threshold chosen to match the site's top band, **not** a claim about severity. |
| `outcome` | string | `outcome` | `paid`, `refused`, `pending`. Self-reported. |
| `location` | string | `city` | Free text locality, **mixed Bengali and English** (`Dhaka` and `ঢাকা` both occur and are not deduplicated). Approximate by design. |
| `description` | string | `description` | The reporter's own narrative, mixed Bengali and English. Contact details are stripped (see `contact_redacted`). |
| `confirmation_count` | integer | `confirmation_count` | Anonymous "I've seen this too" clicks. **Not verification**, and trivially inflatable. |
| `is_verified` | boolean | constant | Hard-coded `False` for every row, by design, so the caveat survives into downstream files. |
| `contact_redacted` | boolean | derived | `True` if an email or phone number was removed from `description` by this pipeline. |
| `source_url` | string | constant | Always `https://www.ghush.site/`. **The site publishes no per-report page**, so no row-level URL exists. |
| `scraped_at` | ISO 8601 UTC | pipeline | When this record was downloaded. |

## Fields deliberately not collected

The API exposes no names, emails, phone numbers, IP addresses or device
identifiers, and none are collected here. The cleaning step additionally strips
emails and Bangladeshi phone numbers from `description`, since narrative free
text is the one place such details can leak.

## Known quality issues

1. **`location` and `service` are unnormalised free text** in two scripts. Any
   grouping on them will fragment (`Dhaka` vs `ঢাকা`).
2. **`date` is submission time.** The full ledger spans a short window (the site
   reports ~26 days at time of collection), so this is a snapshot of a young
   dataset, not a historical series. Do not read trends into it.
3. **Amounts are unverified and self-reported**, with extreme outliers. The
   site's own guidance is that distribution is more informative than the mean;
   use the median or `amount_bucket`.
4. **Selection bias is severe.** These are people who chose to report on a
   website. They are not a sample of bribery in Bangladesh, and rates cannot be
   computed from them.
