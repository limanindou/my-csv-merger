import boto3
import csv
import io
import json
from collections import defaultdict
from datetime import datetime

s3 = boto3.client('s3')

BUCKET      = 'my-expenses-2026-5546543'
MASTER_KEY  = 'Master-File/master_2026.csv'
REPORT_KEY  = 'Master-File/merge_report.json'

FIELDNAMES  = ['month', 'date', 'description', 'category', 'amount']

CATEGORY_ORDER = [
    'Groceries', 'Fuel', 'Utilities', 'Health',
    'Eating Out', 'Clothing', 'Home', 'Entertainment'
]


# ── Currency helpers ──────────────────────────────────────────────────────────

def parse_amount(value: str) -> float:
    """Convert 'R1,234.56' or '1234.56' to a float."""
    return float(value.replace('R', '').replace(',', '').strip())


def format_amount(value: float) -> str:
    """Format a float as 'R1,234.56' South African Rand."""
    return f"R{value:,.2f}"


# ── S3 helpers ────────────────────────────────────────────────────────────────

def read_csv_from_s3(bucket: str, key: str) -> list[dict]:
    """Download a CSV from S3, return list of row dicts. Skips summary/blank rows."""
    obj = s3.get_object(Bucket=bucket, Key=key)
    content = obj['Body'].read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        if not row.get('date', '').strip():
            continue
        rows.append(row)
    return rows


def master_exists() -> bool:
    """Return True if master_2026.csv already exists in the bucket."""
    try:
        s3.head_object(Bucket=BUCKET, Key=MASTER_KEY)
        return True
    except Exception:
        return False


def load_report() -> list[dict]:
    """Load the existing merge report JSON, or return empty list."""
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=REPORT_KEY)
        return json.loads(obj['Body'].read().decode('utf-8'))
    except Exception:
        return []


# ── Merge helpers ─────────────────────────────────────────────────────────────

def tag_month_from_key(key: str, rows: list[dict]) -> list[dict]:
    """Infer month name from filename and tag each row."""
    month_map = {
        'jan': 'January',  'feb': 'February', 'mar': 'March',
        'apr': 'April',    'may': 'May',       'jun': 'June',
        'jul': 'July',     'aug': 'August',    'sep': 'September',
        'oct': 'October',  'nov': 'November',  'dec': 'December',
    }
    filename = key.lower().split('/')[-1]
    detected_month = ''
    for abbr, full in month_map.items():
        if abbr in filename:
            detected_month = full
            break

    for row in rows:
        if not row.get('month', '').strip():
            row['month'] = detected_month or row.get('date', '')[:7]
    return rows


def dedup_rows(rows: list[dict]) -> tuple[list[dict], int]:
    """Remove exact duplicate rows."""
    seen = set()
    unique = []
    for row in rows:
        sig = f"{row.get('date','')}|{row.get('description','')}|{row.get('amount','')}"
        if sig not in seen:
            seen.add(sig)
            unique.append(row)
    return unique, len(rows) - len(unique)


def build_summary_rows(data_rows: list[dict]):
    """Build category subtotal rows and a grand total row."""
    cat_totals = defaultdict(float)
    grand_total = 0.0

    for row in data_rows:
        try:
            amt = parse_amount(row.get('amount', '0'))
            cat = row.get('category', 'Other')
            cat_totals[cat] += amt
            grand_total += amt
        except ValueError:
            pass

    summary = []
    summary.append({f: '' for f in FIELDNAMES})
    summary.append({
        'month': '', 'date': '',
        'description': '── CATEGORY TOTALS ──',
        'category': '', 'amount': ''
    })

    ordered_cats = [c for c in CATEGORY_ORDER if c in cat_totals]
    ordered_cats += sorted(c for c in cat_totals if c not in CATEGORY_ORDER)

    for cat in ordered_cats:
        summary.append({
            'month': '', 'date': '',
            'description': f'  {cat}',
            'category': cat,
            'amount': format_amount(cat_totals[cat])
        })

    summary.append({f: '' for f in FIELDNAMES})
    summary.append({
        'month': '', 'date': '',
        'description': '── GRAND TOTAL (YTD 2026) ──',
        'category': '',
        'amount': format_amount(grand_total)
    })

    return summary, grand_total, dict(cat_totals)


def write_master(data_rows: list[dict], summary_rows: list[dict]):
    """Write data rows + summary rows to master_2026.csv in S3."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, extrasaction='ignore')
    writer.writeheader()

    for row in data_rows:
        try:
            row['amount'] = format_amount(parse_amount(row['amount']))
        except (ValueError, KeyError):
            pass
        writer.writerow(row)

    for row in summary_rows:
        writer.writerow(row)

    s3.put_object(
        Bucket=BUCKET,
        Key=MASTER_KEY,
        Body=output.getvalue().encode('utf-8'),
        ContentType='text/csv',
    )


# ── Handler ───────────────────────────────────────────────────────────────────

def handler(event, context):
    bucket     = event['Records'][0]['s3']['bucket']['name']
    upload_key = event['Records'][0]['s3']['object']['key']

    # Only process CSVs in Monthly-Upload/ folder
    if not upload_key.startswith('Monthly-Upload/') or not upload_key.lower().endswith('.csv'):
        print(f'Skipped: {upload_key}')
        return {'statusCode': 200, 'body': 'Skipped: not a CSV in Monthly-Upload/'}

    print(f'Processing: {upload_key}')

    # Step 1: Read the newly uploaded CSV
    new_rows = read_csv_from_s3(bucket, upload_key)
    if not new_rows:
        return {'statusCode': 200, 'body': 'Skipped: uploaded CSV is empty'}

    new_rows = tag_month_from_key(upload_key, new_rows)
    incoming_count = len(new_rows)

    # Step 2: Read existing master if it exists
    if master_exists():
        print('master_2026.csv found — reading existing rows')
        master_rows = read_csv_from_s3(BUCKET, MASTER_KEY)
    else:
        print('No master yet — this upload becomes the first master')
        master_rows = []

    existing_count = len(master_rows)

    # Step 3: Merge and deduplicate
    combined = master_rows + new_rows
    combined.sort(key=lambda r: r.get('date', ''))
    deduped, dupes_removed = dedup_rows(combined)

    # Step 4: Build category totals and grand total
    summary_rows, grand_total, cat_totals = build_summary_rows(deduped)

    # Step 5: Write new master_2026.csv to Master-File/
    print(f'Writing master — {len(deduped)} rows, grand total: {format_amount(grand_total)}')
    write_master(deduped, summary_rows)

    # Step 6: Update merge report
    report_log = load_report()
    entry = {
        'merged_at':           datetime.utcnow().isoformat() + 'Z',
        'source_file':         upload_key,
        'rows_in_upload':      incoming_count,
        'rows_before_merge':   existing_count,
        'duplicates_removed':  dupes_removed,
        'total_rows_after':    len(deduped),
        'grand_total_ytd':     format_amount(grand_total),
        'category_totals':     {k: format_amount(v) for k, v in cat_totals.items()},
    }
    report_log.append(entry)

    s3.put_object(
        Bucket=BUCKET,
        Key=REPORT_KEY,
        Body=json.dumps(report_log, indent=2).encode('utf-8'),
        ContentType='application/json',
    )

    print(json.dumps(entry, indent=2))
    return {'statusCode': 200, 'body': json.dumps(entry)}