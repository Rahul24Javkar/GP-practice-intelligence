
import csv
import hashlib
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
URLS_FILE = BASE_DIR / "urls.csv"
RAW_DIR = BASE_DIR / "data" / "raw"

USER_AGENT = "GPPracticeIntelligenceBot/1.0 (educational project)"
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 2
MAX_REDIRECTS = 6

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def is_allowed(url: str) -> bool:
    """Check robots.txt before requesting a page."""
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        logging.warning("Skipping invalid URL: %s", url)
        return False

    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    try:
        response = session.get(robots_url, timeout=REQUEST_TIMEOUT)

        # Fail closed if access policy cannot be verified.
        if response.status_code != 200:
            logging.warning(
                "Cannot verify robots.txt for %s (HTTP %s). Skipping.",
                url,
                response.status_code,
            )
            return False

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())

        if not parser.can_fetch(USER_AGENT, url):
            logging.warning("robots.txt disallows access: %s", url)
            return False

        return True

    except requests.RequestException as exc:
        logging.warning("Could not check robots.txt for %s: %s", url, exc)
        return False


def clean_html(html: str) -> str:
    """Extract readable text from an HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    for element in soup(
        ["script", "style", "noscript", "svg", "iframe", "template"]
    ):
        element.decompose()

    return soup.get_text(separator=" ", strip=True)


def safe_filename(url: str) -> str:
    """
    Generate a filename using the host and page path.
    Different pages on the same domain won't overwrite one another.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "unknown").lower()
    path = parsed.path.strip("/")

    host_part = re.sub(r"[^a-zA-Z0-9_-]", "_", host)

    if not path:
        return f"{host_part}.txt"

    path_part = re.sub(r"[^a-zA-Z0-9_-]+", "_", path).strip("_")
    path_part = path_part[:90] or "page"

    # Hash the path to avoid collisions from filename sanitization.
    path_hash = hashlib.sha256(parsed.path.encode("utf-8")).hexdigest()[:8]

    return f"{host_part}__{path_part}_{path_hash}.txt"


def fetch_page(url: str) -> bool:
    """Fetch a page while checking permissions at every redirect."""
    current_url = url

    for _ in range(MAX_REDIRECTS + 1):
        if not is_allowed(current_url):
            logging.warning(
                "Access not permitted or unverified: %s",
                current_url,
            )
            return False

        try:
            response = session.get(
                current_url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            )

            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")

                if not location:
                    logging.warning("Redirect without Location: %s", current_url)
                    return False

                next_url = urljoin(current_url, location)
                old = urlparse(current_url)
                new = urlparse(next_url)

                if new.scheme not in {"http", "https"} or not new.hostname:
                    logging.warning("Unsafe redirect target: %s", next_url)
                    return False

                # Clear cookies when the redirect changes host.
                if old.netloc.lower() != new.netloc.lower():
                    session.cookies.clear()

                logging.info("Redirect: %s -> %s", current_url, next_url)
                current_url = next_url
                continue

            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                logging.warning(
                    "Skipping non-HTML response from %s: %s",
                    current_url,
                    content_type,
                )
                return False

            text = clean_html(response.text)

            # Do not replace a usable file with an error or empty page.
            if len(text) < 200:
                logging.warning(
                    "Page text too short (%s characters); not saving: %s",
                    len(text),
                    current_url,
                )
                return False

            RAW_DIR.mkdir(parents=True, exist_ok=True)
            output_file = RAW_DIR / safe_filename(current_url)

            # Write only after a successful response and text extraction.
            output_file.write_text(text, encoding="utf-8")

            logging.info(
                "Saved %s (%s characters) from %s",
                output_file.name,
                len(text),
                current_url,
            )
            return True

        except requests.RequestException as exc:
            logging.warning("Fetch failed for %s: %s", current_url, exc)
            return False

    logging.warning("Too many redirects for %s", url)
    return False


def main() -> None:
    if not URLS_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {URLS_FILE}")

    with URLS_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames or "url" not in reader.fieldnames:
            raise ValueError("urls.csv must contain a 'url' column.")

        urls = [
            row["url"].strip()
            for row in reader
            if row.get("url") and row["url"].strip()
        ]

    if not urls:
        logging.warning("No URLs found in urls.csv")
        return

    successes = 0

    for index, url in enumerate(urls):
        if index:
            time.sleep(REQUEST_DELAY)

        logging.info("[%s/%s] Fetching %s", index + 1, len(urls), url)

        if fetch_page(url):
            successes += 1

    logging.info(
        "Finished: %s/%s requested pages saved.",
        successes,
        len(urls),
    )


if __name__ == "__main__":
    main()
