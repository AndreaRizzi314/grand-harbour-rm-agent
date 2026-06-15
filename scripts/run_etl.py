#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from otel_rm.etl.load import load_dataset
from otel_rm.etl.scraper import HackathonSiteScraper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-output",
        default="etl/SCRAPE_MANIFEST.json",
        help="Where to write the scrape manifest JSON.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Launch Chromium with a visible window for debugging.",
    )
    parser.add_argument(
        "--no-load",
        action="store_true",
        help="Scrape the site but do not load the database.",
    )
    args = parser.parse_args()

    dataset = HackathonSiteScraper(headless=not args.headful).scrape()

    manifest_path = Path(args.manifest_output)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(dataset.build_scrape_manifest(), handle, indent=2)
        handle.write("\n")

    if not args.no_load:
        load_dataset(dataset)

    print(f"Wrote {manifest_path}")
    print(
        "Scraped "
        f"{len(dataset.reservation_ids)} reservations / "
        f"{len(dataset.reservations)} stay rows across {dataset.pages_scraped} pages."
    )


if __name__ == "__main__":
    main()

