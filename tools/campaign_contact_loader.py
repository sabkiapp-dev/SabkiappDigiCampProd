#!/usr/bin/env python3
"""
Campaign Contact Loader — External CLI tool for adding contacts to a campaign.

Connects directly to the MySQL database.
Features:
  - Rich terminal UI with progress bars
  - Analytics: duplicates, already added, call status breakdown
  - Simulation mode (--dry-run): shows analytics without inserting
  - Category-based filtering
  - CSV file input support
"""

import argparse
import csv
import sys
import datetime
import pytz
from collections import Counter

import mysql.connector
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.prompt import Confirm
from rich import box

# ── DB config (same as Django settings) ─────────────────────────────────────
DB_CONFIG = {
    "host": "206.189.130.26",
    "port": 3306,
    "user": "sabkiapp_asterisk",
    "password": "@O5[mxJD_k3bsAAk",
    "database": "sabkiapp_asterisk",
}

IST = pytz.timezone("Asia/Kolkata")

SENT_STATUS_LABELS = {
    0: "Queued",
    1: "In Progress",
    2: "Unanswered",
    3: "Ongoing Call",
    4: "Cancelled",
    5: "Completed",
}

CAMPAIGN_STATUS_LABELS = {
    0: "Draft",
    1: "Ready",
    2: "Active",
    4: "Paused",
    5: "Completed",
}

console = Console()


# ── DB helpers ───────────────────────────────────────────────────────────────

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def fetch_campaign(conn, campaign_id):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT c.*, u.name AS user_name, u.mobile_number "
        "FROM api_campaign c JOIN api_users u ON c.user_id = u.id "
        "WHERE c.id = %s",
        (campaign_id,),
    )
    row = cur.fetchone()
    cur.close()
    return row


def fetch_contacts_by_categories(conn, user_id, filters):
    """Fetch contacts matching category filters. filters is a dict like {'category_1': 'X'}."""
    where = ["user_id = %s", "status = 1"]
    params = [user_id]
    for col, val in filters.items():
        where.append(f"{col} = %s")
        params.append(val)
    query = f"SELECT id, phone_number, name, category_1, category_2, category_3, category_4, category_5 FROM api_contacts WHERE {' AND '.join(where)}"
    cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_contacts_all(conn, user_id):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, phone_number, name, category_1, category_2, category_3, category_4, category_5 "
        "FROM api_contacts WHERE user_id = %s AND status = 1",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_existing_dialer_entries(conn, campaign_id):
    """Return dict of phone_number -> sent_status for all existing entries in the campaign."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT phone_number, sent_status, name, created_at FROM api_phone_dialer WHERE campaign_id = %s",
        (campaign_id,),
    )
    rows = cur.fetchall()
    cur.close()
    return {r["phone_number"]: r for r in rows}


def insert_dialer_entries(conn, entries, campaign_id, user_id, allow_repeat):
    """Insert PhoneDialer rows. entries is a list of dicts with phone_number, name."""
    now = datetime.datetime.now(IST).replace(tzinfo=None)
    cur = conn.cursor()
    sql = (
        "INSERT INTO api_phone_dialer "
        "(phone_number, user_id, campaign_id, sent_status, name, trials, block_trials, duration, created_at, updated_at) "
        "VALUES (%s, %s, %s, 0, %s, %s, 0, 0, %s, %s)"
    )
    batch = []
    for e in entries:
        batch.append((e["phone_number"], user_id, campaign_id, e["name"], allow_repeat, now, now))
    cur.executemany(sql, batch)
    conn.commit()
    inserted = cur.rowcount
    cur.close()
    return inserted


def update_campaign_contacts_count(conn, campaign_id):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM api_phone_dialer WHERE campaign_id = %s", (campaign_id,))
    count = cur.fetchone()[0]
    cur.execute("UPDATE api_campaign SET contacts_count = %s WHERE id = %s", (count, campaign_id))
    # If campaign was draft (0) and now has contacts, set to ready (1)
    cur.execute("UPDATE api_campaign SET status = 1 WHERE id = %s AND status = 0", (campaign_id,))
    conn.commit()
    cur.close()
    return count


def load_csv_contacts(filepath):
    """Load contacts from CSV. Expected columns: phone_number, name (optional)."""
    contacts = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Normalize header names
        for row in reader:
            normed = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items()}
            phone = normed.get("phone_number") or normed.get("phone") or normed.get("mobile") or normed.get("number") or ""
            name = normed.get("name") or normed.get("contact_name") or None
            if phone:
                contacts.append({"phone_number": clean_phone(phone), "name": name})
    return contacts


def clean_phone(phone):
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if len(phone) == 13 and phone.startswith("91"):
        phone = phone[2:]  # +91XXXXXXXXXX -> strip country code (already stripped +)
    elif len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    elif len(phone) > 10 and phone.startswith("0"):
        phone = phone[1:]
    return phone


def validate_phone(phone):
    if len(phone) != 10:
        return False
    if not phone.isdigit():
        return False
    if int(phone[0]) <= 5:
        return False
    return True


# ── Display helpers ──────────────────────────────────────────────────────────

def show_campaign_info(campaign):
    status_label = CAMPAIGN_STATUS_LABELS.get(campaign["status"], f"Unknown({campaign['status']})")
    table = Table(title="Campaign Details", box=box.ROUNDED, show_header=False, title_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("ID", str(campaign["id"]))
    table.add_row("Name", campaign["name"])
    table.add_row("Description", campaign.get("description") or "-")
    table.add_row("Status", status_label)
    table.add_row("Language", campaign.get("language", "-"))
    table.add_row("Contacts Count", str(campaign.get("contacts_count", 0)))
    table.add_row("Allow Repeat", str(campaign.get("allow_repeat", 0)))
    table.add_row("Owner", f"{campaign.get('user_name', '?')} ({campaign.get('mobile_number', '?')})")
    table.add_row("Schedule", f"{campaign.get('start_time', '?')} - {campaign.get('end_time', '?')}")
    table.add_row("Date Range", f"{campaign.get('start_date', '?')} to {campaign.get('end_date', '?')}")
    console.print(table)
    console.print()


def show_results(stats, existing_status_breakdown, dry_run):
    mode_label = "[bold yellow]SIMULATION[/bold yellow]" if dry_run else "[bold green]LIVE[/bold green]"
    console.print()
    console.print(Panel(f"Mode: {mode_label}", expand=False))

    # Summary table
    summary = Table(title="Contact Addition Summary", box=box.ROUNDED, title_style="bold cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Count", justify="right")
    summary.add_row("Total contacts in source", str(stats["total_source"]))
    summary.add_row("Invalid phone numbers", str(stats["invalid_phone"]), style="red" if stats["invalid_phone"] else "")
    summary.add_row("Duplicate in source (deduped)", str(stats["source_duplicates"]), style="yellow" if stats["source_duplicates"] else "")
    summary.add_row("Already in campaign", str(stats["already_in_campaign"]), style="yellow" if stats["already_in_campaign"] else "")
    summary.add_row("New to add", str(stats["to_add"]), style="bold green" if stats["to_add"] else "")
    if not dry_run:
        summary.add_row("Actually inserted", str(stats["inserted"]), style="bold green")
        summary.add_row("Final campaign contact count", str(stats["final_count"]), style="bold")
    console.print(summary)

    # Existing contacts call status breakdown
    if existing_status_breakdown:
        status_table = Table(title="Already-in-Campaign Contacts — Call Status Breakdown", box=box.ROUNDED, title_style="bold magenta")
        status_table.add_column("Call Status", style="bold")
        status_table.add_column("Count", justify="right")
        for status_code in sorted(existing_status_breakdown.keys()):
            label = SENT_STATUS_LABELS.get(status_code, f"Unknown({status_code})")
            count = existing_status_breakdown[status_code]
            style = ""
            if status_code == 0:
                style = "cyan"
            elif status_code == 5:
                style = "green"
            elif status_code == 2:
                style = "red"
            elif status_code == 4:
                style = "dim"
            status_table.add_row(label, str(count), style=style)
        status_table.add_row("─" * 20, "─" * 5, style="dim")
        status_table.add_row("Total already in campaign", str(sum(existing_status_breakdown.values())), style="bold")
        console.print(status_table)

    # Invalid numbers sample
    if stats.get("invalid_samples"):
        console.print()
        inv_table = Table(title="Sample Invalid Phone Numbers (up to 10)", box=box.SIMPLE)
        inv_table.add_column("Phone Number")
        inv_table.add_column("Reason")
        for phone, reason in stats["invalid_samples"][:10]:
            inv_table.add_row(phone, reason)
        console.print(inv_table)


# ── Main logic ───────────────────────────────────────────────────────────────

def run(args):
    conn = get_connection()

    # 1. Fetch and display campaign
    console.print()
    with console.status("[bold cyan]Fetching campaign info..."):
        campaign = fetch_campaign(conn, args.campaign_id)
    if not campaign:
        console.print(f"[bold red]Campaign ID {args.campaign_id} not found![/bold red]")
        sys.exit(1)

    user_id = campaign["user_id"]
    show_campaign_info(campaign)

    # 2. Gather source contacts
    if args.csv:
        console.print(f"[bold]Loading contacts from CSV:[/bold] {args.csv}")
        source_contacts = load_csv_contacts(args.csv)
        console.print(f"  Loaded {len(source_contacts)} rows from CSV")
    else:
        # Category-based filter from the contacts table
        filters = {}
        for i in range(1, 6):
            val = getattr(args, f"cat{i}", None)
            if val:
                filters[f"category_{i}"] = val

        console.print(f"[bold]Fetching contacts from database[/bold] (user_id={user_id})")
        if filters:
            console.print(f"  Filters: {filters}")
            source_contacts = fetch_contacts_by_categories(conn, user_id, filters)
        else:
            source_contacts = fetch_contacts_all(conn, user_id)
        # Convert to standard format
        source_contacts = [{"phone_number": c["phone_number"], "name": c.get("name")} for c in source_contacts]
        console.print(f"  Found {len(source_contacts)} contacts matching criteria")

    console.print()

    stats = {
        "total_source": len(source_contacts),
        "invalid_phone": 0,
        "source_duplicates": 0,
        "already_in_campaign": 0,
        "to_add": 0,
        "inserted": 0,
        "final_count": 0,
        "invalid_samples": [],
    }

    # 3. Validate and deduplicate
    valid_contacts = []
    seen_phones = set()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Validating contacts", total=len(source_contacts))

        for c in source_contacts:
            phone = c["phone_number"]
            if not validate_phone(phone):
                stats["invalid_phone"] += 1
                reason = "not 10 digits" if len(phone) != 10 else ("non-numeric" if not phone.isdigit() else "starts with 0-5")
                stats["invalid_samples"].append((phone, reason))
            elif phone in seen_phones:
                stats["source_duplicates"] += 1
            else:
                seen_phones.add(phone)
                valid_contacts.append(c)
            progress.advance(task)

    console.print(f"  Valid & unique contacts: [bold]{len(valid_contacts)}[/bold]")
    console.print()

    # 4. Check existing in campaign
    with console.status("[bold cyan]Checking existing entries in campaign..."):
        existing_map = fetch_existing_dialer_entries(conn, args.campaign_id)

    to_add = []
    existing_status_breakdown = Counter()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Checking duplicates against campaign", total=len(valid_contacts))

        for c in valid_contacts:
            phone = c["phone_number"]
            if phone in existing_map:
                stats["already_in_campaign"] += 1
                existing_status_breakdown[existing_map[phone]["sent_status"]] += 1
            else:
                to_add.append(c)
            progress.advance(task)

    stats["to_add"] = len(to_add)

    # 5. Show results / confirm / insert
    dry_run = args.dry_run
    show_results(stats, dict(existing_status_breakdown), dry_run=True)  # always show simulation first

    if dry_run:
        console.print()
        console.print("[bold yellow]DRY RUN complete. No changes made.[/bold yellow]")
        conn.close()
        return

    if not to_add:
        console.print()
        console.print("[bold yellow]Nothing new to add. Exiting.[/bold yellow]")
        conn.close()
        return

    console.print()
    if not args.yes:
        proceed = Confirm.ask(f"[bold]Proceed to insert {len(to_add)} contacts into campaign {args.campaign_id}?[/bold]")
        if not proceed:
            console.print("[yellow]Aborted.[/yellow]")
            conn.close()
            return

    # Insert in batches
    batch_size = args.batch_size
    allow_repeat = campaign.get("allow_repeat", 0)
    total_inserted = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Inserting contacts", total=len(to_add))

        for i in range(0, len(to_add), batch_size):
            batch = to_add[i : i + batch_size]
            inserted = insert_dialer_entries(conn, batch, args.campaign_id, user_id, allow_repeat)
            total_inserted += inserted
            progress.advance(task, advance=len(batch))

    stats["inserted"] = total_inserted

    # Update campaign contacts_count
    with console.status("[bold cyan]Updating campaign contacts count..."):
        stats["final_count"] = update_campaign_contacts_count(conn, args.campaign_id)

    console.print()
    show_results(stats, dict(existing_status_breakdown), dry_run=False)
    console.print()
    console.print("[bold green]Done![/bold green]")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Add contacts to a DigiCampServer campaign (direct DB)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Dry run — show what would happen, no changes
  %(prog)s 42 --dry-run

  # Add all user contacts to campaign 42
  %(prog)s 42

  # Filter by categories
  %(prog)s 42 --cat1 Maharashtra --cat2 Mumbai

  # From CSV file
  %(prog)s 42 --csv contacts.csv

  # From CSV, simulation only
  %(prog)s 42 --csv contacts.csv --dry-run
""",
    )
    parser.add_argument("campaign_id", type=int, help="Campaign ID to add contacts to")
    parser.add_argument("--dry-run", action="store_true", help="Simulate only — show analytics, don't insert")
    parser.add_argument("--csv", type=str, help="Load contacts from a CSV file instead of the database")
    parser.add_argument("--cat1", type=str, help="Filter by category_1")
    parser.add_argument("--cat2", type=str, help="Filter by category_2")
    parser.add_argument("--cat3", type=str, help="Filter by category_3")
    parser.add_argument("--cat4", type=str, help="Filter by category_4")
    parser.add_argument("--cat5", type=str, help="Filter by category_5")
    parser.add_argument("--batch-size", type=int, default=500, help="Insert batch size (default: 500)")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
