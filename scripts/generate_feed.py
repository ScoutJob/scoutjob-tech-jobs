"""
Placeholder generator for ScoutJob's delayed public GitHub feed.

Step 2 will replace this with code that fetches only jobs that have already
passed ScoutJob's free-access delay and writes data/jobs.json and data/jobs.csv.
"""

from pathlib import Path
import csv
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

FIELDS = [
    "company",
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


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    jobs = []
    payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "jobs": jobs,
    }

    (DATA_DIR / "jobs.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    with (DATA_DIR / "jobs.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(jobs)

    print("Generated empty placeholder feed.")


if __name__ == "__main__":
    main()
