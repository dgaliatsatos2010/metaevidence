from __future__ import annotations

import os
import re
from typing import Any
from xml.etree import ElementTree as ET

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery


class PubMedAdapter(BaseAdapter):
    source = "pubmed"
    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    HARD_UID_LIMIT = 10_000

    def __init__(self, *, api_key: str | None = None, email: str | None = None, tool: str = "metaevidence", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("NCBI_API_KEY")
        self.email = email or os.getenv("NCBI_EMAIL")
        self.tool = tool

    def _common(self) -> dict[str, str]:
        params = {"tool": self.tool}
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    @staticmethod
    def _text(elem: ET.Element | None) -> str | None:
        if elem is None:
            return None
        value = "".join(elem.itertext()).strip()
        return re.sub(r"\s+", " ", value) or None

    @staticmethod
    def _year(article: ET.Element) -> int | None:
        for path in (
            ".//Article/ArticleDate/Year",
            ".//Journal/JournalIssue/PubDate/Year",
            ".//DateCompleted/Year",
            ".//DateRevised/Year",
        ):
            text = article.findtext(path)
            if text and text.isdigit():
                return int(text)
        medline = article.findtext(".//Journal/JournalIssue/PubDate/MedlineDate") or ""
        match = re.search(r"\b(18|19|20|21)\d{2}\b", medline)
        return int(match.group(0)) if match else None

    @classmethod
    def _parse_articles(cls, xml_bytes: bytes, *, query: str, retrieved_at: str) -> list[EvidenceRecord]:
        root = ET.fromstring(xml_bytes)
        records: list[EvidenceRecord] = []
        for rank, article in enumerate(root.findall(".//PubmedArticle"), start=1):
            pmid = article.findtext(".//MedlineCitation/PMID")
            title = cls._text(article.find(".//Article/ArticleTitle")) or "[Untitled PubMed record]"
            authors: list[str] = []
            for author in article.findall(".//Article/AuthorList/Author"):
                collective = author.findtext("CollectiveName")
                if collective:
                    authors.append(collective.strip())
                    continue
                family = (author.findtext("LastName") or "").strip()
                given = (author.findtext("ForeName") or author.findtext("Initials") or "").strip()
                name = " ".join(x for x in (family, given) if x)
                if name:
                    authors.append(name)
            abstract_parts: list[str] = []
            for part in article.findall(".//Article/Abstract/AbstractText"):
                txt = cls._text(part)
                if not txt:
                    continue
                label = part.attrib.get("Label") or part.attrib.get("NlmCategory")
                abstract_parts.append(f"{label}: {txt}" if label else txt)
            doi = None
            pmcid = None
            for ident in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
                kind = (ident.attrib.get("IdType") or "").lower()
                if kind == "doi":
                    doi = (ident.text or "").strip() or None
                elif kind == "pmc":
                    pmcid = (ident.text or "").strip() or None
            journal = cls._text(article.find(".//Article/Journal/Title"))
            language = article.findtext(".//Article/Language")
            publication_types = [x.text.strip() for x in article.findall(".//Article/PublicationTypeList/PublicationType") if x.text]
            records.append(EvidenceRecord(
                title=title,
                authors=authors,
                year=cls._year(article),
                journal=journal,
                abstract="\n".join(abstract_parts) or None,
                doi=doi,
                pmid=pmid,
                source_hits=[SourceHit("pubmed", source_id=pmid, query=query, retrieved_at=retrieved_at, rank=rank)],
                metadata={
                    "pmcid": pmcid,
                    "language": language,
                    "publication_types": publication_types,
                    "source_record_type": "PubmedArticle",
                },
            ))
        return records

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 200), 500)
        esearch_params: dict[str, Any] = {
            "db": "pubmed", "term": translation.translated, "retmode": "json",
            "retmax": 0, "usehistory": "y", **self._common(),
        }
        response = self.http.get(self.ESEARCH, params=esearch_params, cacheable=True)
        payload = response.json().get("esearchresult", {})
        total = int(payload.get("count", 0))
        webenv = payload.get("webenv")
        query_key = payload.get("querykey")
        query_translation = payload.get("querytranslation")
        warnings: list[str] = []
        if not self.email:
            warnings.append("NCBI recommends including a valid email and tool identifier in E-utility requests; set NCBI_EMAIL for production use.")

        if total > self.HARD_UID_LIMIT:
            warnings.append(
                "PubMed ESearch exposes at most the first 10,000 matching UIDs. "
                "MetaEvidence therefore caps this execution at 10,000 and marks it truncated; "
                "date-segmented retrieval/EDirect should be used for exhaustive larger searches."
            )
        available_via_api = min(total, self.HARD_UID_LIMIT)
        target = available_via_api if max_records is None else min(available_via_api, max_records)
        records: list[EvidenceRecord] = []
        pages = 0
        if target and webenv and query_key:
            for start in range(0, target, page_size):
                take = min(page_size, target - start)
                params: dict[str, Any] = {
                    "db": "pubmed", "query_key": query_key, "WebEnv": webenv,
                    "retstart": start, "retmax": take, "rettype": "abstract", "retmode": "xml",
                    **self._common(),
                }
                fetched = self.http.get(self.EFETCH, params=params, cacheable=True)
                retrieved_at = utcnow()
                batch = self._parse_articles(fetched.content, query=translation.translated, retrieved_at=retrieved_at)
                for offset, record in enumerate(batch, start=start + 1):
                    for hit in record.source_hits:
                        hit.rank = offset
                records.extend(batch)
                pages += 1
                if len(batch) < take:
                    warnings.append("PubMed returned fewer records than requested on a fetch page; execution stopped early.")
                    break

        truncated = target < total or total > self.HARD_UID_LIMIT
        return AdapterResult(
            source=self.source, translation=translation, records=records, total_available=total,
            pages_retrieved=pages, request_log=list(self.http.logs), warnings=warnings,
            truncated=truncated, started_at_utc=started, finished_at_utc=utcnow(),
            metadata={"query_translation": query_translation, "pubmed_uid_limit": self.HARD_UID_LIMIT},
        )
