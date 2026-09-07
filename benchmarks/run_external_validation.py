#!/usr/bin/env python3
from __future__ import annotations
import argparse
from metaevidence.external_runner import run_external_validation_plan


def main() -> None:
    p=argparse.ArgumentParser(description='Run frozen MetaEvidence external validation roles')
    p.add_argument('--manifest', default='benchmarks/external_benchmark_manifest.json')
    p.add_argument('--data-dir', default='external_validation_data/asysd_2023')
    p.add_argument('--output-dir', default='external_results/asysd_2023')
    p.add_argument('--roles', default='development,calibration')
    p.add_argument('--allow-held-out', action='store_true')
    args=p.parse_args()
    roles=tuple(x.strip() for x in args.roles.split(',') if x.strip())
    rows=run_external_validation_plan(
        args.manifest, args.data_dir, args.output_dir,
        roles=roles, allow_held_out=args.allow_held_out)
    for row in rows:
        print(row.dataset_id, row.role, row.removed_singulars, row.missed_duplicates)


if __name__ == '__main__':
    main()
