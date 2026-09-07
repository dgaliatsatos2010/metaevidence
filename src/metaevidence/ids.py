from __future__ import annotations

from hashlib import sha256
import re

from .models import EvidenceRecord


def _norm(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def stable_record_id(record: EvidenceRecord) -> str:
    """Return a stable citation-level identifier without leaking source credentials.

    Strong bibliographic identifiers are preferred.  The fallback fingerprint is
    deterministic and intended for local workflow identity, not as a globally
    authoritative publication identifier.
    """
    if record.doi:
        return f"DOI:{record.doi.lower()}"
    if record.pmid:
        return f"PMID:{record.pmid}"
    if record.wos_ut:
        return f"WOS:{record.wos_ut}"
    if record.scopus_eid:
        return f"SCOPUS:{record.scopus_eid}"
    if record.openalex_id:
        return f"OPENALEX:{record.openalex_id}"

    first_author = record.authors[0] if record.authors else ""
    payload = "|".join((_norm(record.title), str(record.year or ""), _norm(first_author)))
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20].upper()
    return f"META:{digest}"
