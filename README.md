# 💸 AWS SA Expenses Combiner

A fully serverless monthly expense tracker built on **AWS Lambda** and **Amazon S3**. Upload a monthly CSV expenses file and Lambda automatically merges it into a running yearly master file — complete with category subtotals and a grand total in South African Rand (ZAR).

No servers. No databases. No manual combining. Just upload and go.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [AWS Services Used](#aws-services-used)
- [Project Structure](#project-structure)
- [S3 Bucket Structure](#s3-bucket-structure)
- [Lambda Configuration](#lambda-configuration)
- [Sample Data](#sample-data)
- [How It Works](#how-it-works)
- [Master File Format](#master-file-format)
- [Merge Report](#merge-report)
- [Setup Guide](#setup-guide)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Key Variables](#key-variables)
- [What I Learned](#what-i-learned)

---

## 📘 Project Overview

This project was built as part of a hands-on AWS serverless learning journey. The idea came from a real personal need: combining monthly expense CSV files without manually copying and pasting rows every month.

**The problem it solves:**
Every month you export your expenses as a CSV from your bank or budgeting app. You want a single running master file for the year — sorted by date, deduplicated, with category totals and a grand total in Rand — without doing any manual work.

**The solution:**
Upload your monthly CSV to an S3 folder. Lambda does the rest automatically.

---

## 🏗️ Architecture

```

User uploads expenses_jan_2026.csv
            │
            ▼
  S3 Bucket: my-expenses-2026-5546543
  └── Monthly-Upload/              ← trigger watches this folder
            │
            │  S3 Event Notification (ObjectCreated)
            ▼
  Lambda Function: My-Expenses-Combiner
  │   1. Read new CSV from Monthly-Upload/
  │   2. Read existing Master-File/master_2026.csv (if exists)
  │   3. Merge rows + sort by date
  │   4. Deduplicate exact rows
  │   5. Recalculate category totals + grand total (ZAR)
  │   6. Write new master_2026.csv → Master-File/
  │   7. Append entry to merge_report.json → Master-File/
            │
            ▼
  S3 Bucket: my-expenses-2026-5546543
  └── Master-File/
        ├── master_2026.csv        ← updated YTD master
        └── merge_report.json      ← audit log of every merge
```

---

## ☁️ AWS Services Used

| Service | Purpose |
|---|---|
| **Amazon S3** | Stores all CSV files (uploads and master), triggers Lambda on upload |
| **AWS Lambda** | Runs the Python merge logic serverlessly on every upload |
| **AWS IAM** | `lambda-execution-role` grants Lambda permission to read/write S3 |
| **Amazon CloudWatch** | Automatically logs all Lambda print statements for debugging |

**Cost:** This project runs entirely within the AWS Free Tier for normal personal use (Lambda: 1M free requests/month, S3: 5GB free storage).

---

## 🗂️ Project Structure

```
aws-sa-expenses-combiner/
│
├── README.md                        ← you are here
│
├── src/
│   └── lambda_function.py           ← Lambda function (Python 3.12)
│
├── sample-data/
│   ├── expenses_jan_2026.csv        ← January test data (15 transactions)
│   ├── expenses_feb_2026.csv        ← February test data (17 transactions)
│   └── expenses_mar_2026.csv        ← March test data (18 transactions)
│
└── docs/
    └── architecture.svg             ← Architecture diagram
```

---

## 🪣 S3 Bucket Structure

```
my-expenses-2026-5546543/
│
├── Monthly-Upload/                  ← Upload your monthly CSVs here
│   ├── expenses_jan_2026.csv
│   ├── expenses_feb_2026.csv
│   └── expenses_mar_2026.csv
│
└── Master-File/                     ← Lambda writes here automatically
    ├── master_2026.csv              ← Running YTD master (grows each month)
    └── merge_report.json            ← Audit log of every merge
```

> ⚠️ **Important:** Never upload files directly to `Master-File/`. Lambda manages that folder entirely. Only upload to `Monthly-Upload/`.

---

## ⚙️ Lambda Configuration

| Setting | Value |
|---|---|
| Function name | `My-Expenses-Combiner` |
| Runtime | Python 3.12 |
| Handler | `lambda_function.handler` |
| Memory | 256 MB |
| Timeout | 30 seconds |
| Execution role | `lambda-execution-role` |
| Trigger | S3 — ObjectCreated — Prefix: `Monthly-Upload/` |

> 🚨 **Critical:** The trigger prefix `Monthly-Upload/` is what prevents Lambda from triggering on its own output in `Master-File/`. Without this prefix, Lambda would loop infinitely.

---

## 🧪 Sample Data

Three months of realistic South African expenses are included in `sample-data/`. Stores include:

| Store | Category |
|---|---|
| Woolworths, Spar, Shoprite, Pick n Pay, Checkers, Food Lovers Market | Groceries |
| Shell, ENGEN | Fuel |
| City of Joburg Electricity, Rand Water | Utilities |
| Steers, Nando's, KFC | Eating Out |
| Dis-Chem | Health |
| Virgin Active | Health |
| Netflix | Entertainment |
| Mr Price Home, Builders Warehouse, Game Store | Home |

Each file uses the naming convention `expenses_MMM_YYYY.csv` so Lambda can auto-detect the month from the filename.

### CSV format

```csv
date,description,category,amount
2026-01-02,Woolworths Food,Groceries,R563.54
2026-01-03,Shell Garage Sandton,Fuel,R2,300.42
2026-01-05,Electricity - City of Joburg,Utilities,R1,000.00
...
```

---

## 🔄 How It Works

### Step-by-step flow

**1. Upload trigger**
When you upload a CSV to `Monthly-Upload/`, S3 fires an `ObjectCreated` event to Lambda carrying the bucket name and file key.

**2. File validation**
Lambda checks the file starts with `Monthly-Upload/` and ends with `.csv`. Anything else is skipped silently — this protects against accidental triggers.

**3. Month tagging**
Lambda reads the filename (e.g. `expenses_jan_2026.csv`) and tags every row with `January`. Supported: jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec.

**4. Master check**
Lambda calls `head_object` on `Master-File/master_2026.csv`. If it exists, it reads the existing rows. If not (first upload), it starts fresh with an empty list.

**5. Merge**
New rows are appended to existing rows and the combined list is sorted by date ascending.

**6. Deduplication**
Exact duplicates are removed using a signature of `date|description|amount`. This means uploading the same file twice will not create duplicate rows.

**7. Summary calculation**
Lambda loops through all merged rows, strips the `R` and commas from amounts, and calculates:
- A subtotal per category (Groceries, Fuel, Utilities, etc.)
- A grand total for the year to date

**8. Write master**
The full dataset (data rows + category totals + grand total) is written back to `Master-File/master_2026.csv` with all amounts formatted as `R1,234.56`.

**9. Merge report**
An entry is appended to `Master-File/merge_report.json` recording the source file, row counts, duplicates removed, and the grand total at that point in time.

---

## 🧾 Master File Format

After all three months are uploaded, `master_2026.csv` looks like this:

```
month,date,description,category,amount
January,2026-01-02,Woolworths Food,Groceries,R563.54
January,2026-01-03,Shell Garage Sandton,Fuel,R2,300.42
...
March,2026-03-30,Game Store,Home,R780.00
,,,,
,,── CATEGORY TOTALS ──,,
,,  Groceries,Groceries,R17,234.68
,,  Fuel,Fuel,R11,161.14
,,  Utilities,Utilities,R4,519.65
,,  Health,Health,R3,417.00
,,  Eating Out,Eating Out,R1,125.50
,,  Clothing,Clothing,R1,230.00
,,  Home,Home,R2,575.00
,,  Entertainment,Entertainment,R597.00
,,,,
,,── GRAND TOTAL (YTD 2026) ──,,R41,859.97
```

### YTD totals after each upload

| After uploading | Data rows | Grand total |
|---|---|---|
| January | 15 | R9,289.33 |
| February | 32 | R25,155.95 |
| March | 50 | R41,859.97 |

---

## 📊 Merge Report

`Master-File/merge_report.json` keeps a full audit trail of every merge:

```json
[
  {
    "merged_at": "2026-03-20T10:23:41Z",
    "source_file": "Monthly-Upload/expenses_jan_2026.csv",
    "rows_in_upload": 15,
    "rows_before_merge": 0,
    "duplicates_removed": 0,
    "total_rows_after": 15,
    "grand_total_ytd": "R9,289.33",
    "category_totals": {
      "Groceries": "R4,920.41",
      "Fuel": "R2,860.84",
      "Utilities": "R1,506.55",
      "Health": "R1,129.00",
      "Eating Out": "R335.00",
      "Clothing": "R340.00",
      "Entertainment": "R199.00"
    }
  }
]
```

---

## 🛠️ Setup Guide

### ✅ Prerequisites

- An active AWS account (Free Tier works)
- Access to AWS Management Console
- The sample CSV files from `sample-data/`

### Step 1 — Create the S3 bucket

1. Go to **S3** → Create bucket
2. Bucket name: `my-expenses-2026-<your-unique-number>`
3. Region: **US West (Oregon)**
4. Leave all defaults → Create bucket
5. Open the bucket → Create folder → `Monthly-Upload`
6. Create another folder → `Master-File`

### Step 2 — Create the Lambda function

1. Go to **Lambda** → Create function
2. Author from scratch
3. Function name: `My-Expenses-Combiner`
4. Runtime: **Python 3.12**
5. Execution role: Use existing → `lambda-execution-role`
6. Create function

### Step 3 — Add the S3 trigger

1. Click **Add trigger** → S3
2. Bucket: your bucket
3. Event type: **All object create events**
4. Prefix: `Monthly-Upload/`
5. Check the recursive invocation acknowledgement → Add

### Step 4 — Deploy the code

1. Click the **Code** tab
2. Replace all content in `lambda_function.py` with the code from `src/lambda_function.py`
3. Update line 12: `BUCKET = 'my-expenses-2026-<your-number>'`
4. Click **Deploy**

### Step 5 — Configure runtime settings

1. Scroll to **Runtime settings** → Edit
2. Handler: `lambda_function.handler`
3. Save

### Step 6 — Configure general settings

1. **Configuration** tab → General configuration → Edit
2. Memory: `256 MB`
3. Timeout: `30 seconds`
4. Save

---

## 🧪 Testing

Upload the sample files one at a time to `Monthly-Upload/`, waiting a few seconds between each:

```
1. expenses_jan_2026.csv  →  check Master-File/ appears with master_2026.csv
2. expenses_feb_2026.csv  →  open master_2026.csv, verify 32 data rows
3. expenses_mar_2026.csv  →  open master_2026.csv, verify 50 data rows + R41,859.97 grand total
```

To check Lambda ran successfully:
- Lambda → `My-Expenses-Combiner` → **Monitor** tab → **View CloudWatch logs**
- You should see log entries showing rows processed and grand total

---

## 🩺 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Master-File/` stays empty after upload | Lambda not triggering | Check trigger prefix is exactly `Monthly-Upload/` |
| Lambda loops infinitely | Missing trigger prefix | Edit trigger → add prefix `Monthly-Upload/` |
| Amounts show as `R0.00` | Amount format unexpected | Ensure CSV uses `R1,234.56` format |
| Duplicate rows in master | Rows differ by whitespace | Check CSV for trailing spaces in description or amount |
| `AccessDenied` error | IAM role missing permissions | Confirm `lambda-execution-role` has S3 read/write |
| `NoSuchKey` on first upload | Master doesn't exist yet | Expected — Lambda creates it on first run |
| `Task timed out after 3 seconds` | Default timeout too low | Configuration → General → set Timeout to 30s |

---

## 🔑 Key Variables

All configuration lives at the top of `lambda_function.py`:

```python
BUCKET         = 'my-expenses-2026-5546543'      # Your S3 bucket name
MASTER_KEY     = 'Master-File/master_2026.csv'   # Path to master file
REPORT_KEY     = 'Master-File/merge_report.json' # Path to audit log
FIELDNAMES     = ['month','date','description','category','amount']
CATEGORY_ORDER = ['Groceries','Fuel','Utilities','Health',
                  'Eating Out','Clothing','Home','Entertainment']
```

To use for a different year, update `MASTER_KEY` to `Master-File/master_2027.csv`.

---

## 🎓 What I Learned

This project was built as part of the **AWS Becoming a Cloud Practitioner** lab series. Key concepts practised:

- **Event-driven architecture** — S3 events triggering Lambda without polling
- **Serverless compute** — running Python logic with zero server management
- **S3 as a state store** — using object storage to persist a running master file between Lambda invocations
- **Trigger prefix configuration** — preventing recursive Lambda invocation loops
- **IAM execution roles** — granting least-privilege access for Lambda to read/write S3
- **CloudWatch logging** — using `print()` statements for Lambda observability
- **Python CSV processing** — reading, merging, deduplicating, and writing CSV data in memory using `io.StringIO`
- **South African Rand formatting** — handling `R1,234.56` currency strings in data pipelines

---

## ✍️ Author

**Limani**

---

*Built with 💙 AWS Lambda + Amazon S3 · 2026*
