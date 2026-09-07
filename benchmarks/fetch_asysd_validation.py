#!/usr/bin/env python3
"""Fetch ASySD external validation records into a local, non-versioned directory."""
from __future__ import annotations

import argparse
from pathlib import Path
from metaevidence.external_sources import fetch_asysd_validation_files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destination",
        default="external_validation_data/asysd_2023",
        help="Local destination kept outside version control",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    rows = fetch_asysd_validation_files(Path(args.destination), overwrite=args.overwrite)
    for row in rows:
        print(f"{row.name}\t{row.size_bytes}\t{row.sha256}")


if __name__ == "__main__":
    main()
