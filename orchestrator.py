import subprocess
import json
import csv
import urllib.request
import urllib.error
import os
import time

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = "https://hooks.slack.com/triggers/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"
CSV_FILE = r"C:\Users\puneethvenkat.murali\Desktop\Hackathon\timecards_week_new.csv"
WATCH_MODE = True   # set to False to run once, True to watch for new file

# Maps employee email -> slack workflow variable name
# Add every person's email here
EMAIL_TO_VARIABLE = {
    "puneethvenkat.murali@salesforce.com": "text_puneeth",
    "skekare@salesforce.com":              "text_shradha",
    "nafeesa.ali@salesforce.com":          "text_nafeesa",
    "nafeesa.ali@salesforce.com":          "text_anvith",  # update when Anvith email known
}

# ─── READ CSV ────────────────────────────────────────────────────────────────
def read_timecards(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r.get('employee_name', '').strip()]
    return rows

# ─── GROUP BY PERSON ─────────────────────────────────────────────────────────
def group_by_person(rows):
    people = {}
    for r in rows:
        name = r['employee_name'].strip()
        email = r['email'].strip()
        key = email

        if key not in people:
            people[key] = {
                'name': name,
                'email': email,
                'projects': []
            }
        people[key]['projects'].append({
            'project_id':   r['project_id'].strip(),
            'project_name': r['project_name'].strip(),
            'start_date':   r['start_date'].strip(),
            'end_date':     r['end_date'].strip(),
            'allocated':    float(r['allocated_hours'] or 0),
            'consumed':     float(r['consumed_hours'] or 0),
            'remaining':    float(r['remaining_hours'] or 0),
        })
    return people

# ─── CALL CLAUDE CLI ─────────────────────────────────────────────────────────
def ask_claude(people):
    lines = []
    for email, person in people.items():
        lines.append(f"\n{person['name']} ({email}):")
        for p in person['projects']:
            pct = round((p['consumed'] / p['allocated'] * 100) if p['allocated'] > 0 else 0)
            lines.append(
                f"  - {p['project_name']} ({p['project_id']}): "
                f"{p['consumed']}h consumed / {p['allocated']}h allocated / "
                f"{p['remaining']}h remaining ({pct}% used) | "
                f"Week: {p['start_date']} to {p['end_date']}"
            )
    data_text = "\n".join(lines)

    # build the JSON keys dynamically from who is in the file
    json_keys = {email: f"message for {person['name']}" for email, person in people.items()}
    json_example = json.dumps(json_keys, indent=2)

    prompt = f"""You are a project coordination assistant reviewing weekly timecard data.

Here is this week's timecard data:

{data_text}

For each person, write a SHORT personalized Slack DM (2-3 sentences max) about:
- Their specific project hours this week
- Any concerns (0 hours consumed = not started, overrun, nearly exhausted)
- A clear action if needed

Rules:
- Only mention that person's own data
- Do NOT mention other people
- If consumed_hours is 0, flag it as not started yet
- Start each message with "Hi [FirstName],"

Return ONLY a valid JSON object keyed by email address, nothing else:
{json_example}"""

    print("Calling Claude CLI...")
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120
    )

    print(f"Claude exit code: {result.returncode}")
    if result.returncode != 0 or not result.stdout:
        print("Claude error:", result.stderr[:200])
        return None

    output = result.stdout.strip()
    start = output.find('{')
    end = output.rfind('}') + 1
    if start == -1 or end == 0:
        print("No JSON in Claude output:", output[:300])
        return None

    return json.loads(output[start:end])

# ─── SEND TO SLACK ────────────────────────────────────────────────────────────
def send_to_slack(messages_by_email):
    payload_dict = {}

    for email, message in messages_by_email.items():
        variable = EMAIL_TO_VARIABLE.get(email)
        if variable:
            payload_dict[variable] = message
            print(f"  Mapped: {email} -> {variable}")
        else:
            print(f"  WARNING: No Slack variable mapped for {email} — skipping")

    if not payload_dict:
        print("Nothing to send.")
        return False

    print(f"\nSending {len(payload_dict)} messages to Slack...")
    payload = json.dumps(payload_dict).encode('utf-8')
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as res:
            response = res.read().decode()
            print(f"Slack response: {response}")
            return True
    except urllib.error.HTTPError as e:
        print(f"Slack error HTTP {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        print(f"Slack error: {e}")
        return False

# ─── PROCESS FILE ─────────────────────────────────────────────────────────────
def process_file(filepath):
    print(f"\nProcessing: {filepath}")
    rows = read_timecards(filepath)

    if not rows:
        print("No data rows found.")
        return

    people = group_by_person(rows)
    print(f"Found {len(people)} people:")
    for email, p in people.items():
        total_allocated = sum(proj['allocated'] for proj in p['projects'])
        total_consumed  = sum(proj['consumed'] for proj in p['projects'])
        total_remaining = sum(proj['remaining'] for proj in p['projects'])
        print(f"  {p['name']:30} | {len(p['projects'])} project(s) | "
              f"Allocated: {total_allocated}h | Consumed: {total_consumed}h | Remaining: {total_remaining}h")

    messages = ask_claude(people)
    if not messages:
        print("Failed to get messages from Claude.")
        return

    print("\n=== MESSAGES ===")
    for email, msg in messages.items():
        name = people.get(email, {}).get('name', email)
        print(f"\n[{name}]")
        print(f"  {msg}")

    print("\n=== SENDING TO SLACK ===")
    send_to_slack(messages)

# ─── WATCH MODE: triggers when file is dropped/updated ───────────────────────
def watch_for_file(filepath):
    print(f"Watching for file: {filepath}")
    print("Drop the CSV file to trigger automatically. Press Ctrl+C to stop.\n")

    last_modified = None

    while True:
        if os.path.exists(filepath):
            modified = os.path.getmtime(filepath)
            if modified != last_modified:
                last_modified = modified
                print(f"File detected/updated!")
                process_file(filepath)
                print(f"\nWaiting for next update...")
        time.sleep(5)  # check every 5 seconds

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("Project Hours Orchestrator")
    print("=" * 50)

    if WATCH_MODE:
        watch_for_file(CSV_FILE)
    else:
        process_file(CSV_FILE)

if __name__ == "__main__":
    main()
