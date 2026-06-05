"""Refresh ScoutJob's delayed public GitHub job feed.

The ScoutJob website remains the source of truth. This script downloads only
jobs that have already passed ScoutJob's public/free visibility delay and
writes:

- data/jobs.json
- data/jobs.csv
- docs/data/jobs.json
- docs/data/jobs.csv
- README.md

The /docs copies are required because GitHub Pages publishes the public browser
from the /docs folder.

Safety properties:
- understands the API envelope: { "total": ..., "jobs": [...] }
- follows pagination so the feed keeps working above the server page limit
- deduplicates jobs before publishing
- refuses to replace a healthy feed with an unexpectedly empty response
- copies the generated files into the GitHub Pages folder
- generates a README preview containing recent jobs
- includes a company-provided posting date when available
- falls back to ScoutJob's discovery date when the source posting date is absent
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
    "datePostedUtc",
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


def normalize_bool(value: Any) -> bool:
    """Safely normalize bool-like API values."""
    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value != 0

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}

    return False


def with_page_query(endpoint: str, offset: int, limit: int) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

    query["offset"] = [str(offset)]
    query["limit"] = [str(limit)]

    encoded = urllib.parse.urlencode(query, doseq=True)

    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            encoded,
            parsed.fragment,
        )
    )


def fetch_payload(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ScoutJob-GitHub-Public-Feed/3.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"ScoutJob API returned HTTP {response.status}"
                )

            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"ScoutJob API returned HTTP {exc.code}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Unable to reach ScoutJob API: {exc.reason}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "ScoutJob API returned invalid JSON"
        ) from exc


def extract_jobs(
    payload: Any,
) -> tuple[list[dict[str, Any]], int | None, int | None]:
    """Return jobs, server total, and public delay from either supported shape."""

    if isinstance(payload, list):
        jobs = [
            item
            for item in payload
            if isinstance(item, dict)
        ]

        return jobs, len(jobs), None

    if not isinstance(payload, dict):
        raise RuntimeError(
            "ScoutJob API response must be a JSON object or array"
        )

    raw_jobs = payload.get("jobs")

    if not isinstance(raw_jobs, list):
        raise RuntimeError(
            "ScoutJob API response does not contain a jobs array"
        )

    jobs = [
        item
        for item in raw_jobs
        if isinstance(item, dict)
    ]

    total = payload.get("total")
    total_value = (
        total
        if isinstance(total, int) and total >= 0
        else None
    )

    delay = payload.get("publicDelayMinutes")
    delay_value = (
        delay
        if isinstance(delay, int) and delay >= 0
        else None
    )

    return jobs, total_value, delay_value


def fetch_all_jobs(
    endpoint: str,
    page_size: int,
) -> tuple[list[dict[str, Any]], int | None]:
    offset = 0
    all_jobs: list[dict[str, Any]] = []
    public_delay: int | None = None
    expected_total: int | None = None
    previous_batch_signature: str | None = None

    while True:
        url = with_page_query(
            endpoint,
            offset=offset,
            limit=page_size,
        )

        payload = fetch_payload(url)
        batch, total, delay = extract_jobs(payload)

        if expected_total is None and total is not None:
            expected_total = total

        if public_delay is None and delay is not None:
            public_delay = delay

        batch_signature = "|".join(
            str(item.get("id") or item.get("sourceUrl") or "")
            for item in batch[:25]
        )

        if (
            previous_batch_signature is not None
            and batch_signature
            and batch_signature == previous_batch_signature
        ):
            raise RuntimeError(
                "ScoutJob API returned the same pagination page repeatedly. "
                "Stopping to avoid publishing duplicate data."
            )

        previous_batch_signature = batch_signature
        all_jobs.extend(batch)

        print(
            f"Fetched {len(batch)} jobs at offset={offset}; "
            f"accumulated={len(all_jobs)}"
        )

        if not batch:
            break

        if (
            expected_total is not None
            and len(all_jobs) >= expected_total
        ):
            break

        if len(batch) < page_size:
            break

        offset += len(batch)

    return all_jobs, public_delay


def first_non_empty(raw: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = raw.get(name)

        if value is not None and str(value).strip():
            return value

    return ""


def clean_job(raw: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        field: raw.get(field, "")
        for field in FIELDS
    }

    cleaned["isRemote"] = normalize_bool(
        raw.get("isRemote", False)
    )

    cleaned["isInternship"] = normalize_bool(
        raw.get("isInternship", False)
    )

    cleaned["datePostedUtc"] = first_non_empty(
        raw,
        "datePostedUtc",
        "postedAtUtc",
        "postedDateUtc",
        "datePosted",
        "postedAt",
        "postedDate",
    )

    cleaned["firstDiscoveredAtUtc"] = first_non_empty(
        raw,
        "firstDiscoveredAtUtc",
        "discoveredAtUtc",
    )

    cleaned["lastVerifiedAtUtc"] = first_non_empty(
        raw,
        "lastVerifiedAtUtc",
        "verifiedAtUtc",
    )

    return cleaned


def dedupe_jobs(
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []

    for job in jobs:
        key = str(
            job.get("id")
            or job.get("scoutJobUrl")
            or job.get("sourceUrl")
            or ""
        ).strip()

        if not key:
            key = "|".join(
                str(job.get(field) or "")
                .strip()
                .lower()
                for field in (
                    "company",
                    "title",
                    "location",
                )
            )

        if not key or key in seen:
            continue

        seen.add(key)
        deduped.append(job)

    return deduped


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def sort_jobs(
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def key(job: dict[str, Any]) -> datetime:
        return (
            parse_datetime(job.get("datePostedUtc"))
            or parse_datetime(job.get("firstDiscoveredAtUtc"))
            or datetime.min.replace(tzinfo=timezone.utc)
        )

    return sorted(
        jobs,
        key=key,
        reverse=True,
    )


def write_json(
    path: Path,
    generated_at: str,
    public_delay: int | None,
    jobs: list[dict[str, Any]],
) -> None:
    exported = {
        "generatedAtUtc": generated_at,
        "publicDelayMinutes": public_delay,
        "total": len(jobs),
        "jobs": jobs,
    }

    path.write_text(
        json.dumps(
            exported,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_csv(
    path: Path,
    jobs: list[dict[str, Any]],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS,
        )

        writer.writeheader()
        writer.writerows(jobs)


def markdown_escape(value: Any) -> str:
    return (
        str(value or "")
        .replace("|", "\\|")
        .replace("\n", " ")
        .strip()
    )


def display_date(value: Any) -> str:
    parsed = parse_datetime(value)

    if parsed is None:
        text = str(value or "").strip()
        return text or "—"

    return parsed.strftime("%b %d, %Y")


def write_readme(
    jobs: list[dict[str, Any]],
) -> None:
    rows: list[str] = []

    for job in jobs[:75]:
        title = (
            markdown_escape(job.get("title"))
            or "Untitled role"
        )

        company = (
            markdown_escape(job.get("company"))
            or "Unknown company"
        )

        category = markdown_escape(
            job.get("roleCategory")
        )

        location = markdown_escape(
            job.get("location")
            or job.get("country")
        )

        displayed_date = display_date(
            job.get("datePostedUtc")
            or job.get("firstDiscoveredAtUtc")
        )

        url = str(
            job.get("scoutJobUrl")
            or job.get("sourceUrl")
            or ""
        ).strip()

        linked_title = (
            f"[{title}]({url})"
            if url
            else title
        )

        rows.append(
            f"| {company} | {linked_title} | "
            f"{category} | {location} | {displayed_date} |"
        )

    table = (
        "\n".join(rows)
        if rows
        else "| — | No delayed public jobs are available yet. | — | — | — |"
    )

    README_PATH.write_text(
        """# Fresh Tech Jobs Found by ScoutJob

ScoutJob continuously monitors company career pages directly so you can discover newly posted tech jobs earlier. Instead of repeatedly checking multiple career sites or waiting for roles to appear elsewhere, use ScoutJob to find fresh opportunities sooner and apply while they are still new.

This repository publishes a delayed public feed of engineering, data, AI, and internship roles. The delayed feed refreshes automatically every hour.

For faster access, better filtering, and job-tracking tools, use ScoutJob:

**Try ScoutJob:** https://www.scoutjob.me/

## Browse and filter jobs

- Interactive public job browser: https://scoutjob.github.io/scoutjob-tech-jobs/
- JSON feed: [`data/jobs.json`](data/jobs.json)
- CSV feed: [`data/jobs.csv`](data/jobs.csv)

## Recent delayed public jobs

When a company-provided posting date is unavailable, the displayed date is the date ScoutJob first discovered the role.

| Company | Job | Category | Location | Date posted or discovered |
|---|---|---|---|---|
"""
        + table
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    endpoint = os.environ.get(
        "SCOUTJOB_PUBLIC_JOBS_URL",
        DEFAULT_ENDPOINT,
    ).strip()

    if not endpoint:
        raise RuntimeError(
            "SCOUTJOB_PUBLIC_JOBS_URL cannot be empty"
        )

    page_size = int_env(
        "SCOUTJOB_PUBLIC_JOBS_PAGE_SIZE",
        DEFAULT_PAGE_SIZE,
    )

    allow_empty = bool_env(
        "SCOUTJOB_ALLOW_EMPTY_FEED",
        default=False,
    )

    DATA_DIR.mkdir(
        exist_ok=True,
    )

    DOCS_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_jobs, public_delay = fetch_all_jobs(
        endpoint,
        page_size=page_size,
    )

    jobs = dedupe_jobs(
        [
            clean_job(item)
            for item in raw_jobs
        ]
    )

    jobs = sort_jobs(jobs)

    if not jobs and not allow_empty:
        raise RuntimeError(
            "ScoutJob API returned zero publishable jobs. "
            "Refusing to overwrite the existing feed. "
            "Set SCOUTJOB_ALLOW_EMPTY_FEED=true only for an "
            "intentional empty publication."
        )

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    write_json(
        DATA_DIR / "jobs.json",
        generated_at,
        public_delay,
        jobs,
    )

    write_csv(
        DATA_DIR / "jobs.csv",
        jobs,
    )

    shutil.copy2(
        DATA_DIR / "jobs.json",
        DOCS_DATA_DIR / "jobs.json",
    )

    shutil.copy2(
        DATA_DIR / "jobs.csv",
        DOCS_DATA_DIR / "jobs.csv",
    )

    write_readme(jobs)

    print(
        f"Generated delayed public feed with "
        f"{len(jobs)} unique jobs from {endpoint}"
    )


if __name__ == "__main__":
    main()
