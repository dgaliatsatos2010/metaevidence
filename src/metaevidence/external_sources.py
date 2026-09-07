from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable
from urllib.request import Request, urlopen


ASySD_OSF_NODE = "2b8uq"
ASySD_VALIDATION_FILENAMES: tuple[str, ...] = (
    "Diabetes_duplicates_labelled.csv",
    "NeuroImaging_duplicates_labelled.csv",
    "Cardiac_duplicates_labelled.csv",
    "Depression_duplicates_labelled.csv",
    "SRSR_duplicates_labelled.csv",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class ExternalSourceFile:
    name: str
    path: str
    sha256: str
    size_bytes: int
    source_url: str
    osf_file_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class OSFPublicFileFetcher:
    """Retrieve named public OSF files without bundling them into MetaEvidence.

    The implementation walks OSF's public JSON:API file tree, follows pagination,
    downloads only explicitly requested filenames and writes an integrity manifest.
    It intentionally does not require an OSF token for public validation artifacts.
    """

    def __init__(
        self,
        *,
        timeout: float = 60.0,
        user_agent: str = "MetaEvidence-external-validation/0.9.7",
        urlopen_fn: Callable[..., object] | None = None,
    ) -> None:
        self.timeout = float(timeout)
        self.user_agent = user_agent
        self._urlopen = urlopen_fn or urlopen

    def _request(self, url: str):
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        return self._urlopen(request, timeout=self.timeout)

    def _json(self, url: str) -> dict[str, object]:
        with self._request(url) as response:
            payload = response.read()
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _next_url(payload: dict[str, object]) -> str | None:
        links = payload.get("links")
        if not isinstance(links, dict):
            return None
        nxt = links.get("next")
        if isinstance(nxt, str):
            return nxt or None
        if isinstance(nxt, dict):
            href = nxt.get("href")
            return str(href) if href else None
        return None

    @staticmethod
    def _children_url(item: dict[str, object]) -> str | None:
        relationships = item.get("relationships")
        if not isinstance(relationships, dict):
            return None
        files = relationships.get("files")
        if not isinstance(files, dict):
            return None
        links = files.get("links")
        if not isinstance(links, dict):
            return None
        related = links.get("related")
        if isinstance(related, str):
            return related
        if isinstance(related, dict):
            href = related.get("href")
            return str(href) if href else None
        return None

    @staticmethod
    def _download_url(item: dict[str, object]) -> str | None:
        links = item.get("links")
        if not isinstance(links, dict):
            return None
        direct = links.get("download")
        if isinstance(direct, str):
            return direct
        if isinstance(direct, dict):
            href = direct.get("href")
            if href:
                return str(href)
        return None

    def discover(self, node_id: str, filenames: Iterable[str]) -> dict[str, dict[str, object]]:
        wanted = {str(name) for name in filenames}
        found: dict[str, dict[str, object]] = {}
        root = f"https://api.osf.io/v2/nodes/{node_id}/files/osfstorage/?page%5Bsize%5D=100"
        queue = [root]
        visited: set[str] = set()

        while queue and wanted - found.keys():
            url = queue.pop(0)
            if not url or url in visited:
                continue
            visited.add(url)
            payload = self._json(url)
            data = payload.get("data", [])
            if not isinstance(data, list):
                raise ValueError(f"Unexpected OSF file response at {url!r}: data is not a list")
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                attrs = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
                name = str(attrs.get("name") or "")
                kind = str(attrs.get("kind") or "").lower()
                if name in wanted and kind != "folder":
                    if name in found:
                        raise ValueError(f"OSF contains more than one requested file named {name!r}")
                    found[name] = raw
                if kind == "folder":
                    child = self._children_url(raw)
                    if child:
                        queue.append(child)
            nxt = self._next_url(payload)
            if nxt:
                queue.append(nxt)

        missing = sorted(wanted - found.keys())
        if missing:
            raise FileNotFoundError(
                f"Requested OSF validation file(s) not found under node {node_id}: {', '.join(missing)}"
            )
        return found

    def fetch(
        self,
        node_id: str,
        filenames: Iterable[str],
        destination: str | Path,
        *,
        overwrite: bool = False,
    ) -> list[ExternalSourceFile]:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        found = self.discover(node_id, filenames)
        outputs: list[ExternalSourceFile] = []

        for name in filenames:
            item = found[str(name)]
            url = self._download_url(item)
            if not url:
                raise ValueError(f"OSF file {name!r} did not provide a download link")
            path = destination / str(name)
            if path.exists() and not overwrite:
                raise FileExistsError(f"Refusing to overwrite existing external file: {path}")
            request = Request(url, headers={"User-Agent": self.user_agent})
            with self._urlopen(request, timeout=self.timeout) as response, path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            outputs.append(ExternalSourceFile(
                name=str(name),
                path=str(path),
                sha256=_sha256(path),
                size_bytes=path.stat().st_size,
                source_url=url,
                osf_file_id=(str(item.get("id")) if item.get("id") is not None else None),
            ))

        manifest = {
            "schema_version": "1.0",
            "source": "Open Science Framework",
            "node_id": node_id,
            "files": [row.to_dict() for row in outputs],
            "redistribution_policy": "Third-party source files are kept outside the MetaEvidence package/repository.",
        }
        (destination / "external_source_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return outputs


def fetch_asysd_validation_files(
    destination: str | Path,
    *,
    overwrite: bool = False,
    fetcher: OSFPublicFileFetcher | None = None,
) -> list[ExternalSourceFile]:
    """Fetch the five ASySD 2023 labelled validation files from official OSF node 2b8uq."""
    return (fetcher or OSFPublicFileFetcher()).fetch(
        ASySD_OSF_NODE,
        ASySD_VALIDATION_FILENAMES,
        destination,
        overwrite=overwrite,
    )


BELLER_ENDNOTE_REPOSITORY = "IEBH/dedupe-sweep"
BELLER_ENDNOTE_COMMIT = "66a7ed5f5ea95cafc5f76ba6ec60bb4eb3cd381a"
# Pinned Git object identifiers and sizes observed at the frozen repository commit.
# These are integrity guards, not performance labels.
BELLER_ENDNOTE_FILES: dict[str, dict[str, object]] = {
    "blue-light.xml": {
        "git_blob_sha": "3519573f712c7e39ec6996fe9baf5863706ae369",
        "size_bytes": 5750648,
    },
    "copper.xml": {
        "git_blob_sha": "b0989ffeaae69a1f83e590acec00d8f2b64a62e5",
        "size_bytes": 3636797,
    },
    "diabetes.xml": {
        "git_blob_sha": "a1e3d4895859b08f99dfe4499ea012ee42ce4487",
        "size_bytes": 50566737,
    },
    "tafenoquine.xml": {
        "git_blob_sha": "b4e83e63ce40089150f4ab0c0eedd0c0f7c4551d",
        "size_bytes": 1292166,
    },
    "uti.xml": {
        "git_blob_sha": "b32281245621546bbc135da25bb7ca4d8486ef64",
        "size_bytes": 7065172,
    },
}


def _git_blob_sha1(path: Path) -> str:
    """Return the Git blob SHA-1 for a file, including the canonical blob header."""
    size = path.stat().st_size
    h = hashlib.sha1()
    h.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class GitHubPinnedFileFetcher:
    """Fetch immutable public GitHub raw files with size/blob integrity checks."""

    def __init__(
        self,
        *,
        timeout: float = 120.0,
        user_agent: str = "MetaEvidence-external-validation/0.9.7",
        urlopen_fn: Callable[..., object] | None = None,
    ) -> None:
        self.timeout = float(timeout)
        self.user_agent = user_agent
        self._urlopen = urlopen_fn or urlopen

    def fetch_pinned(
        self,
        *,
        repository: str,
        commit: str,
        files: dict[str, dict[str, object]],
        repository_prefix: str,
        destination: str | Path,
        overwrite: bool = False,
    ) -> list[ExternalSourceFile]:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        outputs: list[ExternalSourceFile] = []

        for name, expected in files.items():
            url = (
                f"https://raw.githubusercontent.com/{repository}/{commit}/"
                f"{repository_prefix.rstrip('/')}/{name}"
            )
            path = destination / name
            if path.exists() and not overwrite:
                raise FileExistsError(f"Refusing to overwrite existing external file: {path}")
            request = Request(url, headers={"User-Agent": self.user_agent})
            try:
                with self._urlopen(request, timeout=self.timeout) as response, path.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
            except Exception:
                # Never leave a partial benchmark file that could be mistaken for a
                # complete gold corpus on the next run.
                path.unlink(missing_ok=True)
                raise

            observed_size = path.stat().st_size
            expected_size = int(expected["size_bytes"])
            if observed_size != expected_size:
                path.unlink(missing_ok=True)
                raise ValueError(
                    f"Size mismatch for {name}: observed={observed_size}, expected={expected_size}"
                )
            observed_blob = _git_blob_sha1(path)
            expected_blob = str(expected["git_blob_sha"])
            if observed_blob != expected_blob:
                path.unlink(missing_ok=True)
                raise ValueError(
                    f"Git blob SHA mismatch for {name}: observed={observed_blob}, expected={expected_blob}"
                )
            outputs.append(ExternalSourceFile(
                name=name,
                path=str(path),
                sha256=_sha256(path),
                size_bytes=observed_size,
                source_url=url,
                osf_file_id=None,
            ))

        manifest = {
            "schema_version": "1.0",
            "source": "GitHub public repository",
            "repository": repository,
            "commit": commit,
            "repository_prefix": repository_prefix,
            "files": [row.to_dict() for row in outputs],
            "git_blob_integrity_verified": True,
            "redistribution_policy": (
                "Third-party source XML files are downloaded at validation time and are not bundled "
                "inside the MetaEvidence source distribution or wheel."
            ),
        }
        (destination / "external_source_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return outputs


def _select_beller_files(names: Iterable[str] | None = None) -> dict[str, dict[str, object]]:
    """Return a validated subset of the frozen Beller/IEBH benchmark manifest."""
    if names is None:
        return dict(BELLER_ENDNOTE_FILES)
    selected: dict[str, dict[str, object]] = {}
    for raw in names:
        name = str(raw)
        if name not in BELLER_ENDNOTE_FILES:
            allowed = ", ".join(BELLER_ENDNOTE_FILES)
            raise ValueError(f"Unknown pinned EndNote benchmark file {name!r}; allowed: {allowed}")
        selected[name] = BELLER_ENDNOTE_FILES[name]
    if not selected:
        raise ValueError("At least one pinned EndNote benchmark filename is required")
    return selected


def fetch_beller_endnote_validation_files(
    destination: str | Path,
    *,
    overwrite: bool = False,
    names: Iterable[str] | None = None,
    fetcher: GitHubPinnedFileFetcher | None = None,
) -> list[ExternalSourceFile]:
    """Fetch one or more verified EndNote XML benchmark libraries from the frozen commit."""
    return (fetcher or GitHubPinnedFileFetcher()).fetch_pinned(
        repository=BELLER_ENDNOTE_REPOSITORY,
        commit=BELLER_ENDNOTE_COMMIT,
        files=_select_beller_files(names),
        repository_prefix="test/data",
        destination=destination,
        overwrite=overwrite,
    )


def verify_beller_endnote_validation_files(
    directory: str | Path, *, names: Iterable[str] | None = None
) -> list[ExternalSourceFile]:
    """Verify local secondary benchmark XML files against the pinned Git tree.

    Validation refuses to run if a local file has the expected name but different
    bytes. This prevents silent benchmark drift when upstream data change.
    """
    directory = Path(directory)
    outputs: list[ExternalSourceFile] = []
    for name, expected in _select_beller_files(names).items():
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError(f"Pinned EndNote validation file not found: {path}")
        observed_size = path.stat().st_size
        expected_size = int(expected["size_bytes"])
        if observed_size != expected_size:
            raise ValueError(
                f"Pinned benchmark size mismatch for {name}: observed={observed_size}, expected={expected_size}"
            )
        observed_blob = _git_blob_sha1(path)
        expected_blob = str(expected["git_blob_sha"])
        if observed_blob != expected_blob:
            raise ValueError(
                f"Pinned benchmark Git blob SHA mismatch for {name}: "
                f"observed={observed_blob}, expected={expected_blob}"
            )
        outputs.append(ExternalSourceFile(
            name=name,
            path=str(path),
            sha256=_sha256(path),
            size_bytes=observed_size,
            source_url=(
                f"https://raw.githubusercontent.com/{BELLER_ENDNOTE_REPOSITORY}/"
                f"{BELLER_ENDNOTE_COMMIT}/test/data/{name}"
            ),
            osf_file_id=None,
        ))
    return outputs
