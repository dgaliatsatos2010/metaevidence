from .base import AdapterResult, BaseAdapter
from .pubmed import PubMedAdapter
from .openalex import OpenAlexAdapter
from .openalex_oql import OpenAlexOQLAdapter
from .crossref import CrossrefAdapter
from .europe_pmc import EuropePMCAdapter
from .core import COREAdapter
from .scopus import ScopusAdapter
from .web_of_science import WebOfScienceStarterAdapter
from .web_of_science_expanded import WebOfScienceExpandedAdapter

__all__ = [
    "AdapterResult",
    "BaseAdapter",
    "PubMedAdapter",
    "OpenAlexAdapter",
    "OpenAlexOQLAdapter",
    "CrossrefAdapter",
    "EuropePMCAdapter",
    "COREAdapter",
    "ScopusAdapter",
    "WebOfScienceStarterAdapter",
    "WebOfScienceExpandedAdapter",
]
