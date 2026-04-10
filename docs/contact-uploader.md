# Contact Uploader

Upload contacts from a CSV file into the `api_contacts` table (the master contacts list).

**File:** `tools/contact_uploader.py`  
**DB:** Connects directly to `206.189.130.26:3306 → sabkiapp_asterisk`

---

## Before You Run

The CSV must have a phone number column. Column names are flexible:

| Purpose | Accepted column names |
|---------|----------------------|
| Phone (required) | `phone_number`, `phone`, `mobile`, `mobile_number`, `number`, `contact` |
| Name (optional) | `name`, `contact_name`, `full_name` |
| Categories (optional) | `category_1` or `category1`, `category_2` or `category2`, … through `category_5` or `category5` |

Missing categories default to `Others`.

**Minimum valid CSV:**
```
phone_number
9876543210
8765432109
```

**Full CSV example:**
```
phone_number,name,category_1,category_2,category_3,category_4,category_5
9876543210,Ramesh Kumar,Maharashtra,Mumbai,Worli,Ward01,Booth001
8765432109,Priya Singh,Delhi,South Delhi,Saket,Ward12,Booth045
```

---

## Usage

```bash
python3 tools/contact_uploader.py <csv_file> (--user-id <id> | --mobile <number>) [options]
```

### Required arguments

| Argument | Description |
|----------|-------------|
| `csv` | Path to the CSV file |
| `--user-id 7` | User ID to upload contacts for |
| `--mobile 9876543210` | Alternative: identify user by mobile number |

Only one of `--user-id` or `--mobile` is needed.

### Optional arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--dry-run` | off | Simulate only — show full analytics, make zero DB changes |
| `--batch-size 500` | 500 | How many rows to insert per DB batch |
| `-y` / `--yes` | off | Skip the confirmation prompt before writing |

---

## Examples

```bash
# Always start with a dry run first
python3 tools/contact_uploader.py data.csv --user-id 7 --dry-run

# Same but identify user by mobile
python3 tools/contact_uploader.py data.csv --mobile 9876543210 --dry-run

# Upload after reviewing the dry run output
python3 tools/contact_uploader.py data.csv --user-id 7

# Upload with no confirmation prompt (useful for scripting)
python3 tools/contact_uploader.py data.csv --user-id 7 -y
```

---

## What the tool shows

Every run (including dry run) prints a full analysis before writing anything:

```
Contact Upload Analysis
───────────────────────────────────────────────────────
Category                        Count   Action
Total rows (valid phone col)    10,000
Empty phone (skipped at read)       12  Skip
Invalid phone numbers               45  Skip
Duplicates within CSV               30  Skip (first occurrence kept)
────────────────────────────────────────────────────────
NEW contacts                     9,800  INSERT
RESTORE (was soft-deleted)          50  DELETE old + INSERT fresh
UPDATE (data changed)               40  UPDATE existing row
UNCHANGED (identical)               23  Skip
```

It also shows:
- **Category 1 breakdown** of contacts about to be inserted
- **Sample of invalid phone numbers** with the reason for each
- **Sample of what's changing** for updated contacts (old vs new)

---

## How contacts are classified

| Status | Condition | Action |
|--------|-----------|--------|
| **NEW** | Phone not in DB for this user | Insert fresh |
| **RESTORE** | Phone exists but was soft-deleted (`status=0`) | Delete old record, insert fresh |
| **UPDATE** | Phone exists (`status=1`) but name or any category changed | Update existing row |
| **UNCHANGED** | Phone exists (`status=1`), all data identical | Skip |
| **Invalid** | Not 10 digits / non-numeric / starts with 0-5 | Skip |
| **CSV duplicate** | Same phone appears more than once in the CSV | Keep first occurrence, skip rest |

---

## Phone number cleaning

The tool automatically cleans phone numbers before validation:

- `+919876543210` → `9876543210` (strip `+91`)
- `919876543210` → `9876543210` (strip `91`)
- `09876543210` → `9876543210` (strip leading `0`)

---

## Next step after uploading

Once contacts are in `api_contacts`, use the **Campaign Contact Loader** to add them to a campaign.  
See [`campaign-contact-loader.md`](./campaign-contact-loader.md).
