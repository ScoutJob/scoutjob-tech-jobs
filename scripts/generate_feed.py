"""Refresh ScoutJob's delayed public GitHub job feed.

The ScoutJob website remains the source of truth. This script downloads only
jobs that have already passed ScoutJob's public/free visibility delay and
writes JSON, CSV, a README preview, and a copy of the feed for GitHub Pages.

Safety properties:
- understands the API envelope: { "total": ..., "jobs": [...] }
- follows pagination so the feed keeps working above the server page limit
- deduplicates jobs before publishing
- refuses to replace a healthy feed with an unexpectedly empty response
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import csv
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DATA_DIR = ROOT / "docs" / "data"
README_PATH = ROOT / "README.md"
DEFAULT_ENDPOINT = "https://www.scoutjob.me/api/public/jobs"
DEFAULT_PAGE_SIZE = 5000

FIELDS = [
    "id",
    "company",
    "companySlug",
    "title",
    "roleCategory",
    "country",
    "location",
    "isRemote",
    "isInternship",
    "firstDiscoveredAtUtc",
    "lastVerifiedAtUtc",
    "scoutJobUrl",
    "sourceUrl",
]


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return parsed


def with_page_query(endpoint: str, offset: int, limit: int) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["offset"] = [str(offset)]
    query["limit"] = [str(limit)]
    encoded = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, encoded, parsed.fragment))


def fetch_payload(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ScoutJob-GitHub-Public-Feed/2.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise RuntimeError(f"ScoutJob API returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"ScoutJob API returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach ScoutJob API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("ScoutJob API returned invalid JSON") from exc


def extract_jobs(payload: Any) -> tuple[list[dict[str, Any]], int | None, int | None]:
    """Return jobs, server total, and public delay from either supported shape."""
    if isinstance(payload, list):
        jobs = [item for item in payload if isinstance(item, dict)]
        return jobs, len(jobs), None

    if not isinstance(payload, dict):
        raise RuntimeError("ScoutJob API response must be a JSON object or array")

    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list):
        raise RuntimeError("ScoutJob API response does not contain a jobs array")

    jobs = [item for item in raw_jobs if isinstance(item, dict)]
    total = payload.get("total")
    total_value = total if isinstance(total, int) and total >= 0 else None
    delay = payload.get("publicDelayMinutes")
    delay_value = delay if isinstance(delay, int) and delay >= 0 else None
    return jobs, total_value, delay_value


def fetch_all_jobs(endpoint: str, page_size: int) -> tuple[list[dict[str, Any]], int | None]:
    offset = 0
    all_jobs: list[dict[str, Any]] = []
    public_delay: int | None = None
    expected_total: int | None = None

    while True:
        url = with_page_query(endpoint, offset=offset, limit=page_size)
        payload = fetch_payload(url)
        batch, total, delay = extract_jobs(payload)

        if expected_total is None and total is not None:
            expected_total = total
        if public_delay is None and delay is not None:
            public_delay = delay

        all_jobs.extend(batch)
        print(f"Fetched {len(batch)} jobs at offset={offset}; accumulated={len(all_jobs)}")

        if not batch:
            break
        if expected_total is not None and len(all_jobs) >= expected_total:
            break
        if len(batch) < page_size:
            break

        offset += len(batch)

    return all_jobs, public_delay


def clean_job(raw: dict[str, Any]) -> dict[str, Any]:
    cleaned = {field: raw.get(field, "") for field in FIELDS}
    cleaned["isRemote"] = bool(raw.get("isRemote", False))
    cleaned["isInternship"] = bool(raw.get("isInternship", False))
    return cleaned


def dedupe_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []

    for job in jobs:
        key = str(job.get("id") or job.get("scoutJobUrl") or job.get("sourceUrl") or "").strip()
        if not key:
            key = "|".join(
                str(job.get(field) or "").strip().lower()
                for field in ("company", "title", "location")
            )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(job)

    return deduped


def write_json(path: Path, generated_at: str, public_delay: int | None, jobs: list[dict[str, Any]]) -> None:
    exported = {
        "generatedAtUtc": generated_at,
        "publicDelayMinutes": public_delay,
        "total": len(jobs),
        "jobs": jobs,
    }
    path.write_text(json.dumps(exported, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, jobs: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(jobs)


def markdown_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def write_readme(jobs: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    for job in jobs[:75]:
        title = markdown_escape(job.get("title")) or "Untitled role"
        company = markdown_escape(job.get("company")) or "Unknown company"
        category = markdown_escape(job.get("roleCategory"))
        location = markdown_escape(job.get("location") or job.get("country"))
        url = str(job.get("scoutJobUrl") or job.get("sourceUrl") or "").strip()
        linked_title = f"[{title}]({url})" if url else title
        rows.append(f"| {company} | {linked_title} | {category} | {location} |")

    table = "\n".join(rows) if rows else "| — | No delayed public jobs are available yet. | — | — |"
    README_PATH.write_text(
        """# Fresh Tech Jobs Found by ScoutJob

ScoutJob continuously checks company career pages directly and finds newly posted tech jobs earlier.

This repository publishes a delayed public feed of engineering, data, AI, and internship roles. The delayed feed is refreshed automatically every hour. ScoutJob members can use the website for earlier visibility and additional tracking tools.

Try ScoutJob: https://www.scoutjob.me/

## Browse and filter jobs

- Interactive public job browser: https://scoutjob.github.io/scoutjob-tech-jobs/
- JSON feed: [`data/jobs.json`](data/jobs.json)
- CSV feed: [`data/jobs.csv`](data/jobs.csv)

## Recent delayed public jobs

| Company | Job | Category | Location |
|---|---|---|---|
"""
        + table
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    endpoint = os.environ.get("SCOUTJOB_PUBLIC_JOBS_URL", DEFAULT_ENDPOINT).strip()
    if not endpoint:
        raise RuntimeError("SCOUTJOB_PUBLIC_JOBS_URL cannot be empty")

    page_size = int_env("SCOUTJOB_PUBLIC_JOBS_PAGE_SIZE", DEFAULT_PAGE_SIZE)
    allow_empty = bool_env("SCOUTJOB_ALLOW_EMPTY_FEED", default=False)

    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    raw_jobs, public_delay = fetch_all_jobs(endpoint, page_size=page_size)
    jobs = dedupe_jobs([clean_job(item) for item in raw_jobs])

    if not jobs and not allow_empty:
        raise RuntimeError(
            "ScoutJob API returned zero publishable jobs. Refusing to overwrite the existing feed. "
            "Set SCOUTJOB_ALLOW_EMPTY_FEED=true only for an intentional empty publication."
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    write_json(DATA_DIR / "jobs.json", generated_at, public_delay, jobs)
    write_csv(DATA_DIR / "jobs.csv", jobs)
    shutil.copy2(DATA_DIR / "jobs.json", DOCS_DATA_DIR / "jobs.json")
    shutil.copy2(DATA_DIR / "jobs.csv", DOCS_DATA_DIR / "jobs.csv")
    write_readme(jobs)

    print(f"Generated delayed public feed with {len(jobs)} unique jobs from {endpoint}")


if __name__ == "__main__":
    main()
