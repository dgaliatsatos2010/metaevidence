"""Minimal M7 reporting example.

This example assumes `search_run`, `dedup`, `ledger`, and `linked` were created
by the M3-M6 workflow.
"""

from metaevidence import PrismaBuilder, PrismaSearchContext, write_prisma_bundle


def build_reporting_bundle(search_run, dedup, ledger, linked):
    flow = PrismaBuilder.build_flow(
        search=search_run,
        deduplication=dedup,
        ledger=ledger,
        records=dedup.records,
        linkage=linked,
    )
    report = PrismaBuilder.build_search_report(
        search_run,
        deduplication=dedup,
        context=PrismaSearchContext(
            study_registries=["ClinicalTrials.gov"],
            peer_review="Document the actual search peer-review process here, if performed.",
        ),
    )
    return write_prisma_bundle(
        "prisma_bundle",
        flow=flow,
        search_report=report,
        search=search_run,
    )
