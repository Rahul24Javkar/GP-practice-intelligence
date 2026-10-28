
import csv
import logging
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "data" / "outreach_drafts.csv"
OUTPUT_FILE = BASE_DIR / "data" / "compliance_report.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

GUARANTEE_PATTERNS = [
    r"\bguarantee(?:d|s)?\b",
    r"\b100\s*%\b",
    r"\beliminate all\b",
    r"\bzero errors?\b",
    r"\bdouble your\b",
    r"\bcut costs by\b",
    r"\bsave \d+\s*(?:hours?|minutes?|percent|%)\b",
]

CLINICAL_PATTERNS = [
    r"\bdiagnos(?:e|es|ed|ing|is)\b",
    r"\btreatment recommendations?\b",
    r"\bclinical decisions?\b",
    r"\bmedical advice\b",
    r"\bprescrib(?:e|es|ed|ing)\b",
]

PRIVACY_PATTERNS = [
    r"\bpatient name\b",
    r"\bpatient record\b",
    r"\bmedical record\b",
    r"\bdate of birth\b",
    r"\bmedicare number\b",
    r"\bhealth information\b",
]

REVIEW_REQUIRED_PATTERNS = [
    r"\bfully compliant\b",
    r"\bcompliant with australian privacy principles\b",
    r"\bcertified\b",
    r"\bapproved by\b",
    r"\bseamlessly integrates?\b",
    r"\bworks with your existing systems\b",
]


def find_matches(text, patterns):
    """Return patterns found in the supplied text."""
    return [
        pattern
        for pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def review_draft(record):
    """Run local rule-based checks on one outreach draft."""
    subject = str(record.get("subject") or "")
    body = str(record.get("draft_body") or "")
    email = str(record.get("recipient_email") or "").strip()

    full_text = f"{subject}\n{body}"
    flags = []
    categories = []

    # Check for unsupported guarantees and quantified claims.
    if find_matches(full_text, GUARANTEE_PATTERNS):
        categories.append(
            "Unsupported guarantee or quantified claim"
        )
        flags.append(
            "Review promises, guarantees, and numerical outcome claims."
        )

    # Check for clinical claims. Explicit scope limitations in the
    # current draft should not trigger a flag by themselves.
    clinical_matches = find_matches(
        full_text, CLINICAL_PATTERNS
    )

    safe_scope_statements = [
    "not make clinical decisions",
    "not replace staff or make clinical decisions",
    "not provide medical advice",
    "not make treatment recommendations",
]

    lower_text = full_text.lower()
    has_scope_limitation = any(
        phrase in lower_text
        for phrase in safe_scope_statements
    )

    if clinical_matches and not has_scope_limitation:
        categories.append("Potential clinical claim")
        flags.append(
            "Review wording that may imply clinical decision-making "
            "or medical advice."
        )

    # Check references to patient or health information.
    if find_matches(full_text, PRIVACY_PATTERNS):
        categories.append(
            "Potential patient or health information reference"
        )
        flags.append(
            "Check that no identifiable or sensitive patient "
            "information is included or requested inappropriately."
        )

    # Check claims about certification, compliance, and integrations.
    if find_matches(full_text, REVIEW_REQUIRED_PATTERNS):
        categories.append(
            "Unverified compliance or capability claim"
        )
        flags.append(
            "Verify certification, compliance, integration, or "
            "capability claims before using the draft."
        )

    # Validate recipient information.
    if not email:
        categories.append("Missing recipient email")
        flags.append(
            "Find and verify an appropriate publicly listed business "
            "contact before considering outreach."
        )
    elif not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", email
    ):
        categories.append("Invalid email format")
        flags.append(
            "Check the recipient email address manually."
        )

    if not subject.strip():
        categories.append("Missing subject")
        flags.append("Add and review an email subject.")

    if not body.strip():
        categories.append("Missing email body")
        flags.append("Add and review the email body.")

    # Every draft still requires human approval.
    flags.append(
        "Human approval required. This automated check is not legal "
        "advice and does not certify compliance."
    )

    revision_categories = {
        "Potential clinical claim",
        "Potential patient or health information reference",
        "Unsupported guarantee or quantified claim",
        "Unverified compliance or capability claim",
    }

    information_categories = {
        "Missing recipient email",
        "Invalid email format",
        "Missing subject",
        "Missing email body",
    }

    if any(category in revision_categories for category in categories):
        status = "Needs revision"
    elif any(
        category in information_categories
        for category in categories
    ):
        status = "Needs information"
    else:
        status = "Human review required"

    return {
        "practice_name": record.get("practice_name", ""),
        "recipient_email": email,
        "subject": subject,
        "lead_score": record.get("lead_score", ""),
        "lead_tier": record.get("lead_tier", ""),
        "draft_status": record.get("draft_status", "Unknown"),
        "compliance_status": status,
        "flag_count": len(categories),
        "flag_categories": " | ".join(categories),
        "compliance_flags": " | ".join(flags),
        "review_scope": (
            "Rule-based text screening only; not a legal compliance "
            "assessment."
        ),
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Draft file not found: {INPUT_FILE}\n"
            "Run 'python outreach.py' first."
        )

    with INPUT_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        drafts = list(csv.DictReader(file))

    if not drafts:
        logging.warning("No outreach drafts found to review.")
        return

    reports = [review_draft(draft) for draft in drafts]

    OUTPUT_FILE.parent.mkdir(
        parents=True, exist_ok=True
    )

    fieldnames = list(reports[0].keys())

    with OUTPUT_FILE.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=fieldnames
        )
        writer.writeheader()
        writer.writerows(reports)

    logging.info("Reviewed %s drafts.", len(reports))

    for report in reports:
        logging.info(
            "%s | Status: %s | Flags: %s",
            report["practice_name"] or "Unknown practice",
            report["compliance_status"],
            report["flag_count"],
        )

    logging.info("No emails were sent.")
    logging.info("Saved report to: %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
