import csv
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROMPT_FILE = BASE_DIR / "prompts" / "extraction.txt"
OUTPUT_FILE = BASE_DIR / "data" / "practices.csv"

MODEL_NAME = "gemini-3.8-flash"
MAX_ATTEMPTS = 2
REQUEST_PAUSE_SECONDS = 2
RETRY_WAIT_SECONDS = 15

FIELDS = [
    "practice_name",
    "address",
    "suburb",
    "phone",
    "email",
    "services",
    "bulk_billing",
    "online_booking",
    "telehealth",
    "doctor_count",
    "confidence",
    "evidence",
]

EVIDENCE_FIELDS = [
    "practice_name",
    "address",
    "phone",
    "email",
    "bulk_billing",
    "online_booking",
    "telehealth",
    "doctor_count",
]

YES_NO_UNKNOWN_FIELDS = ["bulk_billing", "online_booking", "telehealth"]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
load_dotenv(BASE_DIR / ".env")


class GeminiQuotaExceeded(RuntimeError):
    """Raised when Gemini indicates a quota or rate-limit error."""


def create_client():
    """Create a Gemini client with a finite request timeout."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60000),
    )


def load_prompt():
    """Load the extraction prompt template."""
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


def parse_and_validate(raw_text):
    """Parse JSON and validate the expected fields and basic types."""
    if not raw_text:
        raise ValueError("Gemini returned an empty response.")

    result = json.loads(raw_text)
    if not isinstance(result, dict):
        raise ValueError("Response must be a JSON object.")

    if set(result.keys()) != set(FIELDS):
        raise ValueError(
            f"Unexpected schema keys. Expected {FIELDS}; received {list(result.keys())}"
        )

    for field in ["practice_name", "address", "suburb", "phone", "email"]:
        value = result[field]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} must be a string or null.")

    if not isinstance(result["services"], list):
        raise ValueError("services must be a list.")
    if not all(isinstance(item, str) for item in result["services"]):
        raise ValueError("Every service must be a string.")

    for field in YES_NO_UNKNOWN_FIELDS:
        if result[field] not in {"yes", "no", "unknown"}:
            raise ValueError(f"Invalid value for {field}.")

    doctor_count = result["doctor_count"]
    if doctor_count is not None and (
        type(doctor_count) is not int or doctor_count < 0
    ):
        raise ValueError("doctor_count must be a non-negative integer or null.")

    if result["confidence"] not in {"high", "medium", "low"}:
        raise ValueError("confidence must be high, medium, or low.")

    evidence = result["evidence"]
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object.")
    if set(evidence.keys()) != set(EVIDENCE_FIELDS):
        raise ValueError("Evidence fields do not match the expected schema.")

    for field in EVIDENCE_FIELDS:
        value = evidence[field]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Evidence for {field} must be a string or null.")

    return result


def is_quota_error(exc):
    """Recognize quota/rate-limit responses that should stop the run."""
    message = str(exc).upper()
    return any(
        marker in message
        for marker in (
            "429",
            "RESOURCE_EXHAUSTED",
            "QUOTA EXCEEDED",
            "RATE LIMIT",
            "RATE_LIMIT_EXCEEDED",
        )
    )


def extract_record(client, prompt_template, page_text, filename):
    prompt = prompt_template.replace("{page_text}", page_text)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )

            record = parse_and_validate(response.text)

            # Keep evidence only when the exact quoted text appears in the source.
            evidence = record.get("evidence", {})
            for field, snippet in evidence.items():
                if snippet is not None and snippet not in page_text:
                    evidence[field] = None

            record["source_file"] = filename
            return record

        except Exception as exc:
            if is_quota_error(exc):
                logging.error(
                    "%s: Gemini quota/rate limit reached. "
                    "Stopping the entire run to avoid further requests.",
                    filename,
                )
                raise GeminiQuotaExceeded(str(exc)) from exc

            message = str(exc).upper()
            temporary_error = any(
                marker in message
                for marker in (
                    "503",
                    "UNAVAILABLE",
                    "500",
                    "INTERNAL",
                    "504",
                    "DEADLINE_EXCEEDED",
                    "TIMEOUT",
                )
            )

            if temporary_error and attempt < MAX_ATTEMPTS:
                logging.warning(
                    "%s: temporary error on attempt %s/%s. Retrying in %s seconds.",
                    filename,
                    attempt,
                    MAX_ATTEMPTS,
                    RETRY_WAIT_SECONDS,
                )
                time.sleep(RETRY_WAIT_SECONDS)
                continue

            logging.error(
                "%s: extraction failed on attempt %s/%s: %s",
                filename,
                attempt,
                MAX_ATTEMPTS,
                exc,
            )
            return None

    return None


def load_existing_records():
    """Load successful rows so reruns preserve them and skip their source files."""
    if not OUTPUT_FILE.exists():
        return []

    records = []
    with OUTPUT_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        for row in reader:
            source_file = (row.get("source_file") or "").strip()
            if not source_file:
                continue

            try:
                services = row.get("services", "")
                row["services"] = json.loads(services) if services else []
                evidence = row.get("evidence", "")
                row["evidence"] = json.loads(evidence) if evidence else {}
            except (json.JSONDecodeError, TypeError):
                logging.warning(
                    "Skipping existing row with invalid JSON fields: %s", source_file
                )
                continue

            # Ignore rows from an older/different schema instead of corrupting output.
            if not isinstance(row["services"], list) or not isinstance(row["evidence"], dict):
                logging.warning("Skipping malformed existing row: %s", source_file)
                continue

            records.append(row)

    return records


def save_records(records):
    """Write all successful records to CSV."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = OUTPUT_FILE.with_suffix(".csv.tmp")
    csv_fields = ["source_file"] + FIELDS

    with temp_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=csv_fields)
        writer.writeheader()

        for record in records:
            row = record.copy()
            row["services"] = json.dumps(row.get("services", []), ensure_ascii=False)
            row["evidence"] = json.dumps(row.get("evidence", {}), ensure_ascii=False)
            writer.writerow(row)

    temp_file.replace(OUTPUT_FILE)


def main():
    if not RAW_DIR.exists():
        raise FileNotFoundError(f"Raw data directory not found: {RAW_DIR}")

    source_files = sorted(RAW_DIR.glob("*.txt"))
    if not source_files:
        logging.warning("No .txt files found in data/raw.")
        return

    prompt_template = load_prompt()
    records = load_existing_records()
    completed_files = {
        record.get("source_file")
        for record in records
        if record.get("source_file")
    }

    pending_files = [path for path in source_files if path.name not in completed_files]

    # Preserve prior results even if the API is unavailable during this run.
    save_records(records)

    logging.info("Website files found: %s", len(source_files))
    logging.info("Existing successful records: %s", len(records))
    logging.info("Files still needing extraction: %s", len(pending_files))

    if not pending_files:
        logging.info("All source files already have saved records.")
        return

    client = create_client()
    failed_files = []
    quota_stopped = False

    for index, source_file in enumerate(pending_files, start=1):
        logging.info("[%s/%s pending] Processing %s", index, len(pending_files), source_file.name)

        try:
            page_text = source_file.read_text(encoding="utf-8").strip()

            if not page_text:
                logging.warning("Skipping empty file: %s", source_file.name)
                failed_files.append(source_file.name)
                continue

            if len(page_text) < 200:
                logging.warning(
                    "Skipping very short text (%s chars): %s",
                    len(page_text),
                    source_file.name,
                )
                failed_files.append(source_file.name)
                continue

            record = extract_record(client, prompt_template, page_text, source_file.name)

            if record is None:
                failed_files.append(source_file.name)
                continue

            records.append(record)
            save_records(records)
            logging.info(
                "Saved %s | confidence=%s | total records=%s",
                record.get("practice_name"),
                record.get("confidence"),
                len(records),
            )

        except GeminiQuotaExceeded:
            failed_files.append(source_file.name)
            quota_stopped = True
            break

        except KeyboardInterrupt:
            logging.warning("Interrupted by user. Saving progress...")
            save_records(records)
            raise

        except Exception:
            logging.exception("Unexpected error processing %s", source_file.name)
            failed_files.append(source_file.name)

        if index < len(pending_files):
            time.sleep(REQUEST_PAUSE_SECONDS)

    save_records(records)
    logging.info("Extraction run finished: %s successful records saved.", len(records))

    if quota_stopped:
        logging.warning(
            "Stopped early because Gemini quota/rate limits were reached. "
            "Successful records are preserved; rerun later when quota is available."
        )

    if failed_files:
        logging.warning(
            "Files needing another attempt (%s): %s",
            len(failed_files),
            ", ".join(failed_files),
        )


if __name__ == "__main__":
    main()
