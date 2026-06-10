"""
Timecard Management System - Flask Backend
==========================================
Flow:
  Monday AM: Each consultant gets notification with their project allocations (separate block per person).
             DM gets overview of all reportees grouped per employee.
  Friday AM: System generates timecards from Slack context per consultant.
             If no extra projects/hours => consultant sees prepared timecard, clicks OK to send to DM.
             If extra => flagged, consultant can still submit.
             DM approves => notification to consultant "timecard approved".
             DM rejects => sends back with comment, consultant modifies and resubmits.
"""

import csv
import io
import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__)

DATA_DIR = Path(__file__).parent / "data"

notifications_log = []
timecards = []  # Generated timecards pending approval
timecard_id_counter = [0]


INITIAL_CONSULTANTS = [
    {"employee_name": "Nafeesa Ali", "email": "nafeesa.ali@salesforce.com", "role": "Consultant", "dm_email": "skekare@salesforce.com", "project_id": "PRJ-101", "project_name": "Service Cloud Migration", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "20", "consumed_hours": "8"},
    {"employee_name": "Nafeesa Ali", "email": "nafeesa.ali@salesforce.com", "role": "Consultant", "dm_email": "skekare@salesforce.com", "project_id": "PRJ-103", "project_name": "Lightning Component Redesign", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "20", "consumed_hours": "14"},
    {"employee_name": "Anvith Hurakadli", "email": "ahurakadli@salesforce.com", "role": "Consultant", "dm_email": "skekare@salesforce.com", "project_id": "PRJ-102", "project_name": "Data Pipeline Optimization", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "24", "consumed_hours": "18"},
    {"employee_name": "Anvith Hurakadli", "email": "ahurakadli@salesforce.com", "role": "Consultant", "dm_email": "skekare@salesforce.com", "project_id": "PRJ-104", "project_name": "Einstein Analytics Dashboard", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "16", "consumed_hours": "10"},
    {"employee_name": "Puneeth Venkat Murali", "email": "puneethvenkat.murali@salesforce.com", "role": "Consultant", "dm_email": "skekare@salesforce.com", "project_id": "PRJ-101", "project_name": "Service Cloud Migration", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "16", "consumed_hours": "6"},
    {"employee_name": "Puneeth Venkat Murali", "email": "puneethvenkat.murali@salesforce.com", "role": "Consultant", "dm_email": "skekare@salesforce.com", "project_id": "PRJ-105", "project_name": "Apex Batch Processing", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "24", "consumed_hours": "16"},
]

INITIAL_PROJECTS = [
    {"project_id": "PRJ-101", "project_name": "Service Cloud Migration", "dm_name": "Shradha S Kekare", "dm_email": "skekare@salesforce.com", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "200", "consumed_hours": "14", "assigned_consultants": "Nafeesa Ali,Puneeth Venkat Murali", "status": "Active"},
    {"project_id": "PRJ-102", "project_name": "Data Pipeline Optimization", "dm_name": "Shradha S Kekare", "dm_email": "skekare@salesforce.com", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "160", "consumed_hours": "18", "assigned_consultants": "Anvith Hurakadli", "status": "Active"},
    {"project_id": "PRJ-103", "project_name": "Lightning Component Redesign", "dm_name": "Shradha S Kekare", "dm_email": "skekare@salesforce.com", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "180", "consumed_hours": "14", "assigned_consultants": "Nafeesa Ali", "status": "Active"},
    {"project_id": "PRJ-104", "project_name": "Einstein Analytics Dashboard", "dm_name": "Shradha S Kekare", "dm_email": "skekare@salesforce.com", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "120", "consumed_hours": "10", "assigned_consultants": "Anvith Hurakadli", "status": "Active"},
    {"project_id": "PRJ-105", "project_name": "Apex Batch Processing", "dm_name": "Shradha S Kekare", "dm_email": "skekare@salesforce.com", "start_date": "2026-06-08", "end_date": "2026-06-12", "allocated_hours": "150", "consumed_hours": "16", "assigned_consultants": "Puneeth Venkat Murali", "status": "Active"},
]


def read_csv_data(filename):
    filepath = DATA_DIR / filename
    rows = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def write_csv_data(filename, rows, fieldnames):
    filepath = DATA_DIR / filename
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def add_notification(to_email, to_name, message, notif_type="info"):
    notifications_log.append({
        "id": len(notifications_log) + 1,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "to_email": to_email,
        "to_name": to_name,
        "message": message,
        "type": notif_type,
        "read": False,
    })


def next_timecard_id():
    timecard_id_counter[0] += 1
    return timecard_id_counter[0]


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/team")
def get_team():
    team = [
        {"name": "Shradha S Kekare", "email": "skekare@salesforce.com", "role": "DM"},
        {"name": "Nafeesa Ali", "email": "nafeesa.ali@salesforce.com", "role": "Consultant"},
        {"name": "Anvith Hurakadli", "email": "ahurakadli@salesforce.com", "role": "Consultant"},
        {"name": "Puneeth Venkat Murali", "email": "puneethvenkat.murali@salesforce.com", "role": "Consultant"},
    ]
    return jsonify(team)


@app.route("/api/certinia/consultants")
def get_consultants_data():
    return jsonify(read_csv_data("certinia_consultants.csv"))


@app.route("/api/certinia/projects")
def get_projects_data():
    return jsonify(read_csv_data("certinia_projects.csv"))


@app.route("/api/slack/context")
def get_slack_context():
    return jsonify(read_csv_data("slack_context.csv"))


@app.route("/api/monday/trigger", methods=["POST"])
def monday_trigger():
    """
    Monday morning: Send separate notification block per consultant with their allocations.
    DM gets grouped view of all reportees.
    """
    consultants = read_csv_data("certinia_consultants.csv")

    # Group by employee
    groups = {}
    for row in consultants:
        name = row["employee_name"]
        if name not in groups:
            groups[name] = {"email": row["email"], "projects": []}
        groups[name]["projects"].append(row)

    # Send individual notification per consultant
    for name, info in groups.items():
        add_notification(
            info["email"], name,
            json.dumps({
                "block_type": "monday_allocation",
                "employee_name": name,
                "email": info["email"],
                "projects": info["projects"],
            }),
            "monday_allocation"
        )

    # DM gets all reportees as separate blocks
    reportee_blocks = []
    for name, info in sorted(groups.items()):
        reportee_blocks.append({
            "employee_name": name,
            "email": info["email"],
            "projects": info["projects"],
        })
    add_notification(
        "skekare@salesforce.com", "Shradha S Kekare",
        json.dumps({
            "block_type": "monday_dm_overview",
            "reportees": reportee_blocks,
        }),
        "monday_dm_overview"
    )

    return jsonify({"status": "ok", "message": "Monday notifications sent to all team members"})


@app.route("/api/friday/trigger", methods=["POST"])
def friday_trigger():
    """
    Friday morning: Generate timecards from Slack context.
    Each consultant gets their prepared timecard to review.
    If no discrepancy => just click OK to send to DM.
    If extra work detected => flagged but still submittable.
    """
    global timecards
    consultants = read_csv_data("certinia_consultants.csv")
    slack_data = read_csv_data("slack_context.csv")

    # Build allocation map
    alloc_map = {}
    for row in consultants:
        key = (row["email"], row["project_id"])
        alloc_map[key] = {
            "allocated_hours": float(row["allocated_hours"]),
            "project_name": row["project_name"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
        }

    # Build actual from slack
    actual_map = {}
    for row in slack_data:
        key = (row["email"], row["detected_project_id"])
        if key not in actual_map:
            actual_map[key] = {
                "email": row["email"],
                "employee_name": row["employee_name"],
                "project_id": row["detected_project_id"],
                "project_name": row["detected_project_name"],
                "consumed_hours": 0,
            }
        actual_map[key]["consumed_hours"] += float(row["inferred_hours"])

    # Generate timecard per consultant
    employee_timecards = {}
    all_emails = set()
    for row in consultants:
        all_emails.add(row["email"])
    for row in slack_data:
        all_emails.add(row["email"])

    for email in all_emails:
        # Get all projects this person worked on (union of allocated + actual)
        person_projects = {}
        for row in consultants:
            if row["email"] == email:
                person_projects[row["project_id"]] = {
                    "project_id": row["project_id"],
                    "project_name": row["project_name"],
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "allocated_hours": float(row["allocated_hours"]),
                    "consumed_hours": 0,
                    "is_extra": False,
                }

        for (e, pid), actual in actual_map.items():
            if e == email:
                if pid in person_projects:
                    person_projects[pid]["consumed_hours"] = actual["consumed_hours"]
                    if actual["consumed_hours"] > person_projects[pid]["allocated_hours"]:
                        person_projects[pid]["is_extra"] = True
                else:
                    person_projects[pid] = {
                        "project_id": pid,
                        "project_name": actual["project_name"],
                        "start_date": "2026-06-08",
                        "end_date": "2026-06-12",
                        "allocated_hours": 0,
                        "consumed_hours": actual["consumed_hours"],
                        "is_extra": True,
                    }

        # Find employee name
        emp_name = ""
        for row in consultants:
            if row["email"] == email:
                emp_name = row["employee_name"]
                break
        if not emp_name:
            for row in slack_data:
                if row["email"] == email:
                    emp_name = row["employee_name"]
                    break

        if person_projects:
            has_extra = any(p["is_extra"] for p in person_projects.values())
            tc = {
                "id": next_timecard_id(),
                "employee_name": emp_name,
                "email": email,
                "dm_email": "skekare@salesforce.com",
                "week_start": "2026-06-08",
                "week_end": "2026-06-12",
                "entries": list(person_projects.values()),
                "has_extra": has_extra,
                "status": "DRAFT",  # DRAFT -> SUBMITTED -> APPROVED / REJECTED -> RESUBMITTED
                "dm_comment": "",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "submitted_at": "",
                "resolved_at": "",
            }
            timecards.append(tc)
            employee_timecards[email] = tc

    # Notify each consultant with their prepared timecard INCLUDING full entries
    for email, tc in employee_timecards.items():
        extra_entries = [e for e in tc["entries"] if e["is_extra"]]
        if tc["has_extra"]:
            extra_details = []
            for e in extra_entries:
                if e["allocated_hours"] == 0:
                    extra_details.append(f"  - {e['project_id']} {e['project_name']}: {e['consumed_hours']}h worked (NOT in your allocation)")
                else:
                    extra_details.append(f"  - {e['project_id']} {e['project_name']}: {e['consumed_hours']}h worked vs {e['allocated_hours']}h allocated (+{e['consumed_hours'] - e['allocated_hours']}h extra)")
            add_notification(
                email, tc["employee_name"],
                json.dumps({
                    "block_type": "friday_timecard",
                    "timecard_id": tc["id"],
                    "message": "Your timecard has been prepared from Slack activity. Extra hours/projects detected:",
                    "extra_summary": extra_details,
                    "has_extra": True,
                    "entries": tc["entries"],
                }),
                "friday_timecard"
            )
        else:
            add_notification(
                email, tc["employee_name"],
                json.dumps({
                    "block_type": "friday_timecard",
                    "timecard_id": tc["id"],
                    "message": "Your timecard is ready! No discrepancies found. Review and click Submit to send to DM.",
                    "has_extra": False,
                    "entries": tc["entries"],
                }),
                "friday_timecard"
            )

    return jsonify({
        "status": "ok",
        "timecards_generated": len(employee_timecards),
        "message": f"Friday timecards generated for {len(employee_timecards)} consultants. They can now review and submit.",
    })


@app.route("/api/timecards")
def get_timecards():
    email_filter = request.args.get("email")
    if email_filter:
        filtered = [t for t in timecards if t["email"] == email_filter or t["dm_email"] == email_filter]
        return jsonify(filtered)
    return jsonify(timecards)


@app.route("/api/timecards/<int:tc_id>")
def get_timecard(tc_id):
    for tc in timecards:
        if tc["id"] == tc_id:
            return jsonify(tc)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/timecards/<int:tc_id>/submit", methods=["POST"])
def submit_timecard(tc_id):
    """Consultant clicks OK / submits timecard to DM."""
    for tc in timecards:
        if tc["id"] == tc_id and tc["status"] in ("DRAFT", "REJECTED"):
            tc["status"] = "SUBMITTED"
            tc["submitted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tc["dm_comment"] = ""

            # Notify DM
            add_notification(
                tc["dm_email"], "Shradha S Kekare",
                json.dumps({
                    "block_type": "dm_timecard_review",
                    "timecard_id": tc["id"],
                    "employee_name": tc["employee_name"],
                    "email": tc["email"],
                    "has_extra": tc["has_extra"],
                    "message": f"{tc['employee_name']} has submitted their timecard for approval.",
                }),
                "dm_timecard_review"
            )

            add_notification(
                tc["email"], tc["employee_name"],
                json.dumps({
                    "block_type": "timecard_status",
                    "timecard_id": tc["id"],
                    "status": "SUBMITTED",
                    "message": "Your timecard has been submitted to DM for approval.",
                }),
                "timecard_status"
            )

            return jsonify({"status": "ok", "message": "Timecard submitted to DM."})

    return jsonify({"error": "Timecard not found or cannot be submitted"}), 400


@app.route("/api/timecards/<int:tc_id>/modify", methods=["POST"])
def modify_timecard(tc_id):
    """Consultant modifies entries (DRAFT or REJECTED). Can adjust hours up/down."""
    data = request.json
    for tc in timecards:
        if tc["id"] == tc_id and tc["status"] in ("DRAFT", "REJECTED"):
            tc["entries"] = data.get("entries", tc["entries"])
            tc["has_extra"] = any(
                e.get("is_extra") or e.get("consumed_hours", 0) > e.get("allocated_hours", 0)
                for e in tc["entries"]
            )
            return jsonify({"status": "ok", "message": "Timecard updated. You can now resubmit."})
    return jsonify({"error": "Timecard not found or not in rejected state"}), 400


@app.route("/api/timecards/<int:tc_id>/approve", methods=["POST"])
def approve_timecard(tc_id):
    """DM approves timecard. Update Certinia."""
    for tc in timecards:
        if tc["id"] == tc_id and tc["status"] == "SUBMITTED":
            tc["status"] = "APPROVED"
            tc["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Update certinia data
            consultants = read_csv_data("certinia_consultants.csv")
            for entry in tc["entries"]:
                found = False
                for row in consultants:
                    if row["email"] == tc["email"] and row["project_id"] == entry["project_id"]:
                        row["consumed_hours"] = str(entry["consumed_hours"])
                        found = True
                        break
                if not found:
                    consultants.append({
                        "employee_name": tc["employee_name"],
                        "email": tc["email"],
                        "role": "Consultant",
                        "dm_email": tc["dm_email"],
                        "project_id": entry["project_id"],
                        "project_name": entry["project_name"],
                        "start_date": entry["start_date"],
                        "end_date": entry["end_date"],
                        "allocated_hours": str(entry["allocated_hours"]),
                        "consumed_hours": str(entry["consumed_hours"]),
                    })

            fieldnames = ["employee_name", "email", "role", "dm_email", "project_id",
                          "project_name", "start_date", "end_date", "allocated_hours", "consumed_hours"]
            write_csv_data("certinia_consultants.csv", consultants, fieldnames)

            # Update projects
            projects = read_csv_data("certinia_projects.csv")
            for entry in tc["entries"]:
                for p in projects:
                    if p["project_id"] == entry["project_id"]:
                        # Recalculate consumed from all consultants
                        total = sum(
                            float(c["consumed_hours"]) for c in consultants
                            if c["project_id"] == entry["project_id"]
                        )
                        p["consumed_hours"] = str(total)
                        if tc["employee_name"] not in p.get("assigned_consultants", ""):
                            p["assigned_consultants"] = p.get("assigned_consultants", "") + "," + tc["employee_name"]
                        break
            proj_fields = ["project_id", "project_name", "dm_name", "dm_email",
                           "start_date", "end_date", "allocated_hours", "consumed_hours",
                           "assigned_consultants", "status"]
            write_csv_data("certinia_projects.csv", projects, proj_fields)

            # Notify consultant
            add_notification(
                tc["email"], tc["employee_name"],
                json.dumps({
                    "block_type": "timecard_status",
                    "timecard_id": tc["id"],
                    "status": "APPROVED",
                    "message": "Your timecard has been approved! Certinia has been updated.",
                }),
                "timecard_approved"
            )

            return jsonify({"status": "ok", "message": f"Timecard approved for {tc['employee_name']}. Certinia updated."})

    return jsonify({"error": "Timecard not found or not in submitted state"}), 400


@app.route("/api/timecards/<int:tc_id>/reject", methods=["POST"])
def reject_timecard(tc_id):
    """DM rejects timecard with comment. Sends back to consultant."""
    comment = request.json.get("comment", "Please review and correct.")
    for tc in timecards:
        if tc["id"] == tc_id and tc["status"] == "SUBMITTED":
            tc["status"] = "REJECTED"
            tc["dm_comment"] = comment
            tc["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Notify consultant with comment
            add_notification(
                tc["email"], tc["employee_name"],
                json.dumps({
                    "block_type": "timecard_rejected",
                    "timecard_id": tc["id"],
                    "status": "REJECTED",
                    "dm_comment": comment,
                    "message": f"Your timecard was sent back by DM. Comment: {comment}. Please modify and resubmit.",
                }),
                "timecard_rejected"
            )

            return jsonify({"status": "ok", "message": f"Timecard rejected. Sent back to {tc['employee_name']} with comment."})

    return jsonify({"error": "Timecard not found or not in submitted state"}), 400


@app.route("/api/notifications")
def get_notifications():
    email_filter = request.args.get("email")
    if email_filter:
        filtered = [n for n in notifications_log if n["to_email"] == email_filter]
        return jsonify(filtered)
    return jsonify(notifications_log)


@app.route("/api/notifications/clear", methods=["POST"])
def clear_notifications():
    global notifications_log
    notifications_log = []
    return jsonify({"status": "ok"})


@app.route("/api/export/consultants")
def export_consultants():
    data = read_csv_data("certinia_consultants.csv")
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=certinia_consultants_export.csv"})


@app.route("/api/export/projects")
def export_projects():
    data = read_csv_data("certinia_projects.csv")
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=certinia_projects_export.csv"})


@app.route("/api/export/timecards")
def export_timecards():
    output = io.StringIO()
    fieldnames = ["employee_name", "email", "project_id", "project_name",
                  "start_date", "end_date", "allocated_hours", "consumed_hours",
                  "is_extra", "timecard_status"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for tc in timecards:
        for entry in tc["entries"]:
            writer.writerow({
                "employee_name": tc["employee_name"],
                "email": tc["email"],
                "project_id": entry["project_id"],
                "project_name": entry["project_name"],
                "start_date": entry["start_date"],
                "end_date": entry["end_date"],
                "allocated_hours": entry["allocated_hours"],
                "consumed_hours": entry["consumed_hours"],
                "is_extra": entry.get("is_extra", False),
                "timecard_status": tc["status"],
            })
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=timecards_export.csv"})


@app.route("/api/reset", methods=["POST"])
def reset_data():
    global notifications_log, timecards, timecard_id_counter
    notifications_log = []
    timecards = []
    timecard_id_counter[0] = 0

    fieldnames_c = ["employee_name", "email", "role", "dm_email", "project_id",
                    "project_name", "start_date", "end_date", "allocated_hours", "consumed_hours"]
    write_csv_data("certinia_consultants.csv", INITIAL_CONSULTANTS, fieldnames_c)

    fieldnames_p = ["project_id", "project_name", "dm_name", "dm_email",
                    "start_date", "end_date", "allocated_hours", "consumed_hours",
                    "assigned_consultants", "status"]
    write_csv_data("certinia_projects.csv", INITIAL_PROJECTS, fieldnames_p)

    return jsonify({"status": "ok", "message": "All data reset to initial state."})


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  TIMECARD MANAGEMENT SYSTEM")
    print("  http://localhost:5000")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000)
