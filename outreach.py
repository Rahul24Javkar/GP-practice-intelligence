
import csv
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "data" / "scored_practices.csv"
OUTPUT_FILE = BASE_DIR / "data" / "outreach_drafts.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)


def clean(value):
    """Return a safe, trimmed string from a CSV value."""
    return str(value or "").strip()


def create_draft(practice):
    """Create an email draft without calling an AI API."""

    name = clean(practice.get("practice_name")) or "your practice"
    suburb = clean(practice.get("suburb"))
    email = clean(practice.get("email"))
    phone = clean(practice.get("phone"))

    greeting_name = name if name != "your practice" else "your team"

    subject = (
        f"An idea for front-desk administration at {name}"
        if name != "your practice"
        else "An idea for GP practice administration"
    )

    location_line = (
        f" serving the {suburb} area"
        if suburb
        else ""
    )

    body = f"""Hello {greeting_name} team,

I'm reaching out to introduce an AI front-desk automation service concept for GP practices{location_line}.

The idea is to help practice teams manage selected routine administrative tasks, such as:

- Sorting incoming enquiries into categories for staff review.
- Supporting appointment reminder workflows.
- Preparing draft replies to routine administrative questions for staff approval.

The intended approach is to support your existing team, not replace staff or make clinical decisions. Any implementation would need to be assessed against your practice's workflows, privacy requirements, and existing systems.

Would you be open to a brief conversation about whether these kinds of administrative workflows are relevant to your practice?

Kind regards,
GP Practice Automation Outreach
"""

    flags = []

    if not email:
        flags.append("Missing recipient email; verify an appropriate public business contact.")

    if not phone:
        flags.append("No phone number available in the extracted record.")

    if clean(practice.get("confidence")).lower() != "high":
        flags.append("Verify extracted practice details before using this draft.")

    if not clean(practice.get("suburb")):
        flags.append("Practice location is missing; review personalization.")

    flags.extend([
        "Human review required before use.",
        "Verify the offer, capabilities, pricing, and any proposed integrations before making commitments.",
        "Check applicable Australian privacy, healthcare, and electronic marketing requirements before outreach.",
    ])

    return {
        "practice_name": name,
        "suburb": suburb,
        "recipient_email": email,
        "phone": phone,
        "lead_score": clean(practice.get("lead_score")),
        "lead_tier": clean(practice.get("lead_tier")),
        "subject": subject,
        "draft_body": body,
        "draft_status": "Draft - not sent",
        "compliance_flags": " | ".join(flags),
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Scored practices file not found: {INPUT_FILE}\n"
            "Run 'python score.py' first."
        )

    with INPUT_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        practices = list(csv.DictReader(file))

    if not practices:
        logging.warning(
            "No practices found in scored_practices.csv."
        )
        return

    drafts = [create_draft(practice) for practice in practices]

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = list(drafts[0].keys())

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(drafts)

    missing_email_count = sum(
        1 for draft in drafts
        if not draft["recipient_email"]
    )

    logging.info("Created %s email drafts.", len(drafts))
    logging.info(
        "%s drafts have no recipient email address.",
        missing_email_count,
    )
    logging.info("No emails were sent.")
    logging.info("Saved drafts to: %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
