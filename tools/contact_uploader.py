#!/usr/bin/env python3
"""
Contact Uploader — External CLI tool to upload contacts into api_contacts.

Connects directly to the MySQL database.
Mirrors the webapp's upload_contacts logic exactly.

Analytics shown (always, before any writes):
  - Total rows in CSV
  - Invalid phone numbers (with samples)
  - Source-level duplicates (deduped away)
  - NEW contacts to insert
  - RESTORE contacts (previously soft-deleted, status=0 → re-add)
  - UPDATE contacts (exist & active but data changed)
  - UNCHANGED contacts (exist, no difference → skip)

Simulation mode (--dry-run): full analytics, zero DB writes.
"""

import argparse
import csv
import sys
from collections import Counter

import mysql.connector
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm
from rich import box

# ── DB config ────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "206.189.130.26",
    "port": 3306,
    "user": "sabkiapp_asterisk",
    "password": "@O5[mxJD_k3bsAAk",
    "database": "sabkiapp_asterisk",
}

console = Console()

CATEGORY_FIELDS = ["category_1", "category_2", "category_3", "category_4", "category_5"]


# ── DB helpers ───────────────────────────────────────────────────────────────

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def fetch_user(conn, user_id=None, mobile=None):
    cur = conn.cursor(dictionary=True)
    if user_id:
        cur.execute("SELECT id, name, mobile_number, status FROM api_users WHERE id = %s", (user_id,))
    else:
        cur.execute("SELECT id, name, mobile_number, status FROM api_users WHERE mobile_number = %s", (mobile,))
    row = cur.fetchone()
    cur.close()
    return row


def fetch_existing_contacts(conn, user_id, phone_numbers):
    """
    Fetch existing contacts for a user, keyed by phone_number.
    Returns dict: phone_number -> {id, name, status, category_1..5}
    """
    if not phone_numbers:
        return {}
    placeholders = ",".join(["%s"] * len(phone_numbers))
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"SELECT id, phone_number, name, status, category_1, category_2, category_3, category_4, category_5 "
        f"FROM api_contacts WHERE user_id = %s AND phone_number IN ({placeholders})",
        [user_id] + list(phone_numbers),
    )
    rows = cur.fetchall()
    cur.close()
    return {r["phone_number"]: r for r in rows}


def delete_contact(conn, contact_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM api_contacts WHERE id = %s", (contact_id,))
    conn.commit()
    cur.close()


def insert_contacts_batch(conn, rows, user_id):
    """rows: list of dicts with phone_number, name, category_1..5"""
    cur = conn.cursor()
    sql = (
        "INSERT INTO api_contacts (phone_number, name, user_id, category_1, category_2, category_3, category_4, category_5, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)"
    )
    batch = [
        (r["phone_number"], r["name"] or "", user_id,
         r["category_1"], r["category_2"], r["category_3"], r["category_4"], r["category_5"])
        for r in rows
    ]
    cur.executemany(sql, batch)
    conn.commit()
    inserted = cur.rowcount
    cur.close()
    return inserted


def update_contact(conn, contact_id, data, cat_cols):
    cur = conn.cursor()
    set_parts = ["name=%s"]
    values = [data["name"] or ""]
    for f in CATEGORY_FIELDS:
        if cat_cols.get(f):
            set_parts.append(f"{f}=%s")
            values.append(data[f])
    values.append(contact_id)
    cur.execute(
        f"UPDATE api_contacts SET {', '.join(set_parts)} WHERE id = %s",
        values,
    )
    conn.commit()
    cur.close()


# ── Phone helpers ────────────────────────────────────────────────────────────

def clean_phone(raw):
    phone = str(raw).strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if len(phone) == 13 and phone.startswith("91"):
        phone = phone[2:]
    elif len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    elif len(phone) > 10 and phone.startswith("0"):
        phone = phone[1:]
    return phone


def validate_phone(phone):
    if len(phone) != 10:
        return False, "not 10 digits"
    if not phone.isdigit():
        return False, "non-numeric"
    if int(phone[0]) <= 5:
        return False, f"starts with {phone[0]} (must be 6-9)"
    return True, None


def normalize_category(val):
    v = (val or "").strip()
    return v if v else "Others"


# ── CSV loader ───────────────────────────────────────────────────────────────

PHONE_ALIASES = {"phone_number", "phone", "mobile", "mobile_number", "number", "contact"}
NAME_ALIASES = {"name", "contact_name", "full_name"}

def load_csv(filepath):
    rows = []
    errors = []
    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = [h.strip().lower() for h in (reader.fieldnames or [])]
            # Map header aliases
            phone_col = next((h for h in headers if h in PHONE_ALIASES or h.replace(" ", "_") in PHONE_ALIASES), None)
            name_col = next((h for h in headers if h in NAME_ALIASES), None)
            cat_cols = {}
            for i in range(1, 6):
                key = f"category_{i}"
                alt_key = f"category{i}"
                space_key = f"category {i}"
                if key in headers:
                    cat_cols[key] = key
                elif alt_key in headers:
                    cat_cols[key] = alt_key
                elif space_key in headers:
                    cat_cols[key] = space_key
                else:
                    cat_cols[key] = None

            if not phone_col:
                console.print(f"[bold red]CSV Error: No phone number column found.[/bold red]")
                console.print(f"  Headers found: {headers}")
                console.print(f"  Expected one of: {sorted(PHONE_ALIASES)}")
                sys.exit(1)

            for lineno, row in enumerate(reader, start=2):
                normed = {k.strip().lower(): v for k, v in row.items()}
                raw_phone = normed.get(phone_col, "").strip()
                if not raw_phone:
                    errors.append((lineno, raw_phone, "empty phone"))
                    continue
                rows.append({
                    "phone_number": clean_phone(raw_phone),
                    "name": normed.get(name_col, "").strip() if name_col else "",
                    "category_1": normalize_category(normed.get(cat_cols["category_1"], "")) if cat_cols["category_1"] else "",
                    "category_2": normalize_category(normed.get(cat_cols["category_2"], "")) if cat_cols["category_2"] else "",
                    "category_3": normalize_category(normed.get(cat_cols["category_3"], "")) if cat_cols["category_3"] else "",
                    "category_4": normalize_category(normed.get(cat_cols["category_4"], "")) if cat_cols["category_4"] else "",
                    "category_5": normalize_category(normed.get(cat_cols["category_5"], "")) if cat_cols["category_5"] else "",
                    "_line": lineno,
                    "_raw_phone": raw_phone,
                })
    except FileNotFoundError:
        console.print(f"[bold red]File not found: {filepath}[/bold red]")
        sys.exit(1)
    return rows, errors, headers, cat_cols


# ── Analysis ─────────────────────────────────────────────────────────────────

def analyse(csv_rows, csv_errors, existing_map):
    """
    Categorise every CSV row into one of:
      invalid, source_duplicate, new, restore, update, unchanged
    """
    results = {
        "invalid": [],        # (phone, reason)
        "source_duplicate": [],
        "new": [],            # contact dicts ready to insert
        "restore": [],        # contact dicts for re-insert after delete of status=0
        "update": [],         # (existing_id, new_data_dict)
        "unchanged": [],      # phone numbers
    }
    seen = set()

    for row in csv_rows:
        phone = row["phone_number"]
        ok, reason = validate_phone(phone)
        if not ok:
            results["invalid"].append((row["_raw_phone"], reason))
            continue
        if phone in seen:
            results["source_duplicate"].append(phone)
            continue
        seen.add(phone)

        contact_data = {k: row[k] for k in ["phone_number", "name", "category_1", "category_2", "category_3", "category_4", "category_5"]}

        existing = existing_map.get(phone)
        if existing is None:
            results["new"].append(contact_data)
        elif existing["status"] == 0:
            results["restore"].append(contact_data)
        else:
            # status == 1
            name_changed = (contact_data["name"] and contact_data["name"] != existing["name"])
            cats_changed = any(contact_data[f] != existing[f] for f in CATEGORY_FIELDS)
            if name_changed or cats_changed:
                results["update"].append((existing["id"], contact_data))
            else:
                results["unchanged"].append(phone)

    return results


# ── Display ──────────────────────────────────────────────────────────────────

def show_user_info(user):
    console.print()
    table = Table(title="User", box=box.ROUNDED, show_header=False, title_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("ID", str(user["id"]))
    table.add_row("Name", user.get("name") or "-")
    table.add_row("Mobile", user.get("mobile_number") or "-")
    table.add_row("Status", "Active" if user.get("status") == 1 else str(user.get("status")))
    console.print(table)
    console.print()


def show_csv_header_info(headers, phone_col, filepath):
    console.print(f"[bold]CSV file:[/bold] {filepath}")
    console.print(f"  Columns detected: {', '.join(headers)}")
    console.print(f"  Phone column: [bold cyan]{phone_col}[/bold cyan]")
    console.print()


def show_analysis(results, csv_errors, dry_run):
    mode = "[bold yellow]SIMULATION[/bold yellow]" if dry_run else "[bold green]LIVE[/bold green]"
    console.print(Panel(f"Mode: {mode}", expand=False))
    console.print()

    summary = Table(title="Contact Upload Analysis", box=box.ROUNDED, title_style="bold cyan")
    summary.add_column("Category", style="bold")
    summary.add_column("Count", justify="right")
    summary.add_column("Action")

    total = (len(results["invalid"]) + len(results["source_duplicate"]) +
             len(results["new"]) + len(results["restore"]) +
             len(results["update"]) + len(results["unchanged"]))
    summary.add_row("Total rows (valid phone col)", str(total), "")
    summary.add_row("Empty phone (skipped at read)", str(len(csv_errors)), "Skip", style="dim")
    summary.add_row("Invalid phone numbers", str(len(results["invalid"])),
                    "Skip", style="red" if results["invalid"] else "")
    summary.add_row("Duplicates within CSV", str(len(results["source_duplicate"])),
                    "Skip (first occurrence kept)", style="yellow" if results["source_duplicate"] else "")
    summary.add_row("─" * 30, "─" * 5, "", style="dim")
    summary.add_row("NEW contacts", str(len(results["new"])),
                    "INSERT", style="bold green" if results["new"] else "")
    summary.add_row("RESTORE (was soft-deleted)", str(len(results["restore"])),
                    "DELETE old + INSERT fresh", style="bold cyan" if results["restore"] else "")
    summary.add_row("UPDATE (data changed)", str(len(results["update"])),
                    "UPDATE existing row", style="bold yellow" if results["update"] else "")
    summary.add_row("UNCHANGED (identical)", str(len(results["unchanged"])),
                    "Skip", style="dim")
    console.print(summary)

    # Category distribution of new contacts
    if results["new"] or results["restore"]:
        all_to_insert = results["new"] + results["restore"]
        cat1_counts = Counter(r["category_1"] for r in all_to_insert)
        if len(cat1_counts) <= 20:
            cat_table = Table(title=f"Category 1 breakdown of contacts to insert ({len(all_to_insert)} total)",
                              box=box.SIMPLE, title_style="bold magenta")
            cat_table.add_column("Category 1", style="bold")
            cat_table.add_column("Count", justify="right")
            for cat, count in sorted(cat1_counts.items(), key=lambda x: -x[1]):
                cat_table.add_row(cat, str(count))
            console.print(cat_table)

    # Sample invalid numbers
    if results["invalid"]:
        console.print()
        inv_table = Table(title=f"Sample Invalid Phone Numbers (showing up to 15 of {len(results['invalid'])})",
                          box=box.SIMPLE)
        inv_table.add_column("Raw Value")
        inv_table.add_column("Reason")
        for raw, reason in results["invalid"][:15]:
            inv_table.add_row(raw, reason)
        console.print(inv_table)

    # Sample updates (show what's changing)
    if results["update"]:
        console.print()
        upd_table = Table(title=f"Sample Updates (showing up to 10 of {len(results['update'])})",
                          box=box.SIMPLE)
        upd_table.add_column("Phone")
        upd_table.add_column("New Name")
        upd_table.add_column("cat1")
        upd_table.add_column("cat2")
        for _, data in results["update"][:10]:
            upd_table.add_row(data["phone_number"], data["name"] or "-",
                              data["category_1"], data["category_2"])
        console.print(upd_table)


def show_final(write_stats):
    console.print()
    done = Table(title="Write Results", box=box.ROUNDED, title_style="bold green")
    done.add_column("Operation", style="bold")
    done.add_column("Count", justify="right")
    done.add_row("Inserted (new)", str(write_stats["inserted"]))
    done.add_row("Restored (delete+insert)", str(write_stats["restored"]))
    done.add_row("Updated", str(write_stats["updated"]))
    done.add_row("Skipped (unchanged)", str(write_stats["skipped"]))
    console.print(done)


# ── Main ─────────────────────────────────────────────────────────────────────

def run(args):
    conn = get_connection()

    # 1. Resolve user
    with console.status("[bold cyan]Looking up user..."):
        if args.user_id:
            user = fetch_user(conn, user_id=args.user_id)
        else:
            user = fetch_user(conn, mobile=args.mobile)

    if not user:
        console.print("[bold red]User not found![/bold red]")
        sys.exit(1)

    user_id = user["id"]
    show_user_info(user)

    # 2. Load CSV
    console.print(f"[bold]Loading CSV:[/bold] {args.csv}")
    csv_rows, csv_errors, headers, cat_cols = load_csv(args.csv)

    # Detect phone col for display
    phone_col = next((h for h in [h.strip().lower() for h in headers] if h in PHONE_ALIASES), "phone_number")
    show_csv_header_info(headers, phone_col, args.csv)
    console.print(f"  {len(csv_rows)} data rows loaded, {len(csv_errors)} rows skipped (empty phone)")
    console.print()

    # 3. Fetch existing contacts in bulk
    all_phones = {r["phone_number"] for r in csv_rows if validate_phone(r["phone_number"])[0]}
    with console.status(f"[bold cyan]Fetching existing contacts from DB ({len(all_phones)} phones to check)..."):
        existing_map = fetch_existing_contacts(conn, user_id, all_phones)
    console.print(f"  {len(existing_map)} already exist in database for this user")
    console.print()

    # 4. Analyse
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analysing contacts", total=len(csv_rows))
        results = {"invalid": [], "source_duplicate": [], "new": [], "restore": [], "update": [], "unchanged": []}
        seen = set()
        for row in csv_rows:
            phone = row["phone_number"]
            ok, reason = validate_phone(phone)
            if not ok:
                results["invalid"].append((row["_raw_phone"], reason))
                progress.advance(task)
                continue
            if phone in seen:
                results["source_duplicate"].append(phone)
                progress.advance(task)
                continue
            seen.add(phone)
            contact_data = {k: row[k] for k in ["phone_number", "name", "category_1", "category_2", "category_3", "category_4", "category_5"]}
            existing = existing_map.get(phone)
            if existing is None:
                results["new"].append(contact_data)
            elif existing["status"] == 0:
                results["restore"].append(contact_data)
            else:
                # For categories not in CSV, keep existing DB value (no overwrite)
                for f in CATEGORY_FIELDS:
                    if not cat_cols.get(f):
                        contact_data[f] = existing[f]
                name_changed = (contact_data["name"] and contact_data["name"] != existing["name"])
                cats_changed = any(contact_data[f] != existing[f] for f in CATEGORY_FIELDS if cat_cols.get(f))
                if name_changed or cats_changed:
                    results["update"].append((existing["id"], contact_data))
                else:
                    results["unchanged"].append(phone)
            progress.advance(task)

    show_analysis(results, csv_errors, dry_run=True)

    total_writes = len(results["new"]) + len(results["restore"]) + len(results["update"])

    if args.dry_run:
        console.print()
        console.print("[bold yellow]DRY RUN complete. No changes made.[/bold yellow]")
        conn.close()
        return

    if total_writes == 0:
        console.print()
        console.print("[bold yellow]Nothing to write. Exiting.[/bold yellow]")
        conn.close()
        return

    console.print()
    if not args.yes:
        proceed = Confirm.ask(
            f"[bold]Proceed? "
            f"Insert {len(results['new'])} new, "
            f"restore {len(results['restore'])}, "
            f"update {len(results['update'])}[/bold]"
        )
        if not proceed:
            console.print("[yellow]Aborted.[/yellow]")
            conn.close()
            return

    write_stats = {"inserted": 0, "restored": 0, "updated": 0, "skipped": len(results["unchanged"])}

    # 5. Restore (delete status=0 + re-insert)
    if results["restore"]:
        restore_phones = [r["phone_number"] for r in results["restore"]]
        restore_existing = fetch_existing_contacts(conn, user_id, restore_phones)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console,
        ) as progress:
            task = progress.add_task("Restoring (delete+insert)", total=len(results["restore"]))
            restore_batch = []
            for data in results["restore"]:
                phone = data["phone_number"]
                if phone in restore_existing:
                    delete_contact(conn, restore_existing[phone]["id"])
                restore_batch.append(data)
                progress.advance(task)

        restored = insert_contacts_batch(conn, restore_batch, user_id)
        write_stats["restored"] = restored

    # 6. Insert new (in batches)
    if results["new"]:
        batch_size = args.batch_size
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console,
        ) as progress:
            task = progress.add_task("Inserting new contacts", total=len(results["new"]))
            for i in range(0, len(results["new"]), batch_size):
                batch = results["new"][i: i + batch_size]
                inserted = insert_contacts_batch(conn, batch, user_id)
                write_stats["inserted"] += inserted
                progress.advance(task, advance=len(batch))

    # 7. Update changed contacts
    if results["update"]:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console,
        ) as progress:
            task = progress.add_task("Updating changed contacts", total=len(results["update"]))
            for contact_id, data in results["update"]:
                update_contact(conn, contact_id, data, cat_cols)
                write_stats["updated"] += 1
                progress.advance(task)

    show_final(write_stats)
    console.print()
    console.print("[bold green]Done![/bold green]")
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Upload contacts from CSV into api_contacts (direct DB)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
CSV column names recognised:
  Phone  : phone_number, phone, mobile, mobile_number, number, contact
  Name   : name, contact_name, full_name
  Cats   : category_1, category_2, category_3, category_4, category_5

Examples:
  # Simulation — full analytics, no DB changes
  %(prog)s contacts.csv --user-id 7 --dry-run

  # Identify user by mobile number instead
  %(prog)s contacts.csv --mobile 9876543210 --dry-run

  # Actually upload
  %(prog)s contacts.csv --user-id 7

  # Upload with no confirmation prompt
  %(prog)s contacts.csv --user-id 7 -y
""",
    )
    parser.add_argument("csv", help="Path to the CSV file")
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--user-id", type=int, help="User ID to upload contacts for")
    id_group.add_argument("--mobile", type=str, help="User's mobile number (alternative to --user-id)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate only — show analytics, no writes")
    parser.add_argument("--batch-size", type=int, default=500, help="Insert batch size (default: 500)")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
