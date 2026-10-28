
import csv
import json
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "data" / "practices.csv"
OUTPUT_FILE = BASE_DIR / "data" / "scored_practices.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)


def is_yes(value):
    return str(value or "").strip().lower() in {
        "yes", "true", "1"
    }


def parse_services(value):
    """Read services from the JSON array stored in the CSV."""
    if not value:
        return []

    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [
                str(item).strip()
                for item in parsed
                if str(item).strip()
            ]
    except (json.JSONDecodeError, TypeError):
        pass

    # Handle a plain-text services value if encountered.
    return [
        item.strip()
        for item in str(value).split(",")
        if item.strip()
    ]


def score_practice(record):
    """Calculate a rule-based lead score out of 100."""
    score = 0
    reasons = []

    # Digital access
    if is_yes(record.get("online_booking")):
        score += 20
        reasons.append("Online booking available (+20)")

    if is_yes(record.get("telehealth")):
        score += 15
        reasons.append("Telehealth available (+15)")

    # Breadth of services: up to 20 points
    services = parse_services(record.get("services"))
    service_points = min(len(services), 10) * 2
    score += service_points

    if service_points:
        reasons.append(
            f"{len(services)} listed services (+{service_points})"
        )

    # Practice size: up to 15 points
    try:
        doctor_count = int(record.get("doctor_count", ""))
    except (TypeError, ValueError):
        doctor_count = 0

    if doctor_count >= 11:
        size_points = 15
    elif doctor_count >= 6:
        size_points = 10
    elif doctor_count >= 1:
        size_points = 5
    else:
        size_points = 0

    score += size_points

    if size_points:
        reasons.append(
            f"Practice size: {doctor_count} doctors (+{size_points})"
        )

    # Contactability
    if str(record.get("phone") or "").strip():
        score += 10
        reasons.append("Phone number available (+10)")

    if str(record.get("email") or "").strip():
        score += 10
        reasons.append("Email available (+10)")

    # Extraction confidence
    confidence = str(
        record.get("confidence") or ""
    ).strip().lower()

    if confidence == "high":
        score += 10
        reasons.append("High extraction confidence (+10)")
    elif confidence == "medium":
        score += 5
        reasons.append("Medium extraction confidence (+5)")

    # Maximum possible score is 100.
    score = min(score, 100)

    if score >= 70:
        tier = "High"
    elif score >= 40:
        tier = "Medium"
    else:
        tier = "Low"

    result = record.copy()
    result["lead_score"] = score
    result["lead_tier"] = tier
    result["score_reasons"] = json.dumps(reasons)
    result["service_count"] = len(services)

    return result


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {INPUT_FILE}"
        )

    with INPUT_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        records = list(csv.DictReader(file))

    if not records:
        logging.warning(
            "No extracted practices found. Nothing to score."
        )
        return

    scored_records = [
        score_practice(record)
        for record in records
    ]

    # Sort highest-scoring practices first.
    scored_records.sort(
        key=lambda record: int(record["lead_score"]),
        reverse=True,
    )

    fieldnames = list(scored_records[0].keys())

    OUTPUT_FILE.parent.mkdir(
        parents=True, exist_ok=True
    )

    with OUTPUT_FILE.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=fieldnames
        )
        writer.writeheader()
        writer.writerows(scored_records)

    logging.info(
        "Scored %s practices.", len(scored_records)
    )
    logging.info("Saved results to %s", OUTPUT_FILE)

    for record in scored_records:
        logging.info(
            "%s | Score: %s/100 | Tier: %s",
            record.get("practice_name", "Unknown practice"),
            record["lead_score"],
            record["lead_tier"],
        )


if __name__ == "__main__":
    main()
