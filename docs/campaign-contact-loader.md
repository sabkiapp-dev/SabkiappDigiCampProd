# Campaign Contact Loader

Add contacts from `api_contacts` (or a CSV file) into a campaign's dial queue (`api_phone_dialer`).

**File:** `tools/campaign_contact_loader.py`  
**DB:** Connects directly to `206.189.130.26:3306 → sabkiapp_asterisk`

---

## Before You Run

You need:
- The **campaign ID** (visible in the webapp URL or the `api_campaign` table)
- Contacts already uploaded into `api_contacts` for that user (see [`contact-uploader.md`](./contact-uploader.md))

---

## Usage

```bash
python3 tools/campaign_contact_loader.py <campaign_id> [options]
```

### Required arguments

| Argument | Description |
|----------|-------------|
| `campaign_id` | The numeric ID of the campaign |

### Optional arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--dry-run` | off | Simulate only — show full analytics, make zero DB changes |
| `--cat1 <value>` | (all) | Filter source contacts by `category_1` |
| `--cat2 <value>` | (all) | Filter source contacts by `category_2` |
| `--cat3 <value>` | (all) | Filter source contacts by `category_3` |
| `--cat4 <value>` | (all) | Filter source contacts by `category_4` |
| `--cat5 <value>` | (all) | Filter source contacts by `category_5` |
| `--csv <file>` | (DB) | Load source contacts from a CSV file instead of `api_contacts` |
| `--batch-size 500` | 500 | How many rows to insert per DB batch |
| `-y` / `--yes` | off | Skip the confirmation prompt before writing |

---

## Examples

```bash
# Always start with a dry run
python3 tools/campaign_contact_loader.py 42 --dry-run

# Filter by state (category_1) — dry run first
python3 tools/campaign_contact_loader.py 42 --cat1 Maharashtra --dry-run

# Filter by state + district
python3 tools/campaign_contact_loader.py 42 --cat1 Maharashtra --cat2 Mumbai --dry-run

# Add all contacts for this campaign's user
python3 tools/campaign_contact_loader.py 42

# Add filtered contacts after reviewing dry run
python3 tools/campaign_contact_loader.py 42 --cat1 Maharashtra

# Load from CSV instead of the contacts table
python3 tools/campaign_contact_loader.py 42 --csv new_contacts.csv --dry-run
python3 tools/campaign_contact_loader.py 42 --csv new_contacts.csv

# Skip confirmation (useful for scripting)
python3 tools/campaign_contact_loader.py 42 --cat1 Maharashtra -y
```

---

## What the tool shows

Every run always prints a simulation summary first, regardless of mode:

```
Campaign Details
─────────────────────────────────────────
ID              42
Name            June Survey Round 2
Status          Ready
Language        Hindi
Contacts Count  1,250
Allow Repeat    2
Owner           Ravi Sharma (9876543210)
Schedule        09:00:00 - 18:00:00
Date Range      2026-04-01 to 2026-06-30

Contact Addition Summary
─────────────────────────────────────────────────────
Metric                              Count
Total contacts in source            10,000
Invalid phone numbers                   23
Duplicate in source (deduped)           14
Already in campaign                  1,250
New to add                           8,713
```

For contacts already in the campaign, it also shows a **call status breakdown**:

```
Already-in-Campaign Contacts — Call Status Breakdown
─────────────────────────────────────────────────────
Call Status         Count
Queued                800
In Progress            12
Unanswered            300
Completed             138
Total               1,250
```

In **live mode**, after insertion it also shows:
- Actual inserted count
- Final campaign contacts total

---

## Call status meanings

| Code | Label | Meaning |
|------|-------|---------|
| 0 | Queued | Ready to be dialled |
| 1 | In Progress | Currently being called |
| 2 | Unanswered | No answer |
| 3 | Ongoing Call | Call is live |
| 4 | Cancelled | Cancelled |
| 5 | Completed | Call was completed |

All newly added contacts are inserted with `sent_status = 0` (Queued).

---

## How duplicates are handled

A contact is considered **already in the campaign** if its phone number already exists in `api_phone_dialer` for that campaign — regardless of call status. The tool **never overwrites** existing dialer entries.

---

## CSV mode (`--csv`)

When using `--csv`, contacts are loaded directly from the file and matched against the campaign. The tool does **not** write to `api_contacts` in this mode — it only creates `api_phone_dialer` entries.

CSV must have a `phone_number` column (or `phone`, `mobile`, `number`). A `name` column is optional.

---

## Campaign status after loading

If the campaign was in **Draft** status (`0`) before loading and contacts are successfully inserted, its status is automatically updated to **Ready** (`1`).

The campaign's `contacts_count` field is also updated to reflect the current total after insertion.

---

## Typical workflow

```bash
# Step 1: Upload contacts to the contacts table
python3 tools/contact_uploader.py data.csv --user-id 7 --dry-run
python3 tools/contact_uploader.py data.csv --user-id 7

# Step 2: Add those contacts to a campaign (filtered by category)
python3 tools/campaign_contact_loader.py 42 --cat1 Maharashtra --dry-run
python3 tools/campaign_contact_loader.py 42 --cat1 Maharashtra
```
