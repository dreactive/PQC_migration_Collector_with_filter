import hashlib
from pathlib import Path


def project_paths(root=None):
    """Return standard project paths rooted at the collector workspace."""
    project_root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    project_root = project_root.resolve()
    return {
        "root": project_root,
        "config": project_root / "config",
        "data": project_root / "data",
        "raw_github": project_root / "data" / "raw" / "github",
        "exports": project_root / "data" / "exports",
        "reports": project_root / "reports",
        "report_batches": project_root / "reports" / "batches",
        "src": project_root / "src",
        "tests": project_root / "tests",
        "samples": project_root / "tests" / "samples",
        "runner": project_root / "runner",
        "temp": project_root / "temp",
        "view": project_root / "view",
    }


def ensure_dirs(root=None):
    """Create the standard workspace directories and return a status summary."""
    paths = project_paths(root)
    directory_keys = (
        "config",
        "data",
        "raw_github",
        "exports",
        "reports",
        "report_batches",
        "src",
        "tests",
        "samples",
        "runner",
        "temp",
        "view",
    )
    created = []
    existing = []
    for key in directory_keys:
        path = paths[key]
        if path.exists():
            existing.append(key)
        else:
            path.mkdir(parents=True, exist_ok=True)
            created.append(key)
    return {
        "root": str(paths["root"]),
        "created": created,
        "existing": existing,
        "directories": {key: str(paths[key]) for key in directory_keys},
    }


def normalize_path(path):
    """Return a stable slash-separated repository path."""
    return "/".join(part for part in str(path).replace("\\", "/").split("/") if part)


def query_page_key(query_text, page, page_size):
    """Return the stable dedupe key for one GitHub search query page."""
    key_material = f"{query_text}\n{int(page)}\n{int(page_size)}"
    return hashlib.sha256(key_material.encode("utf-8")).hexdigest()


def repository_key(repository_id):
    """Return the stable dedupe key for one GitHub repository."""
    return f"github_repo:{int(repository_id)}"


def search_item_key(repository_id, path, blob_sha):
    """Return the stable dedupe key for one GitHub code search item."""
    return f"github_code:{int(repository_id)}:{normalize_path(path)}:{str(blob_sha)}"


def file_key(repository_id, path, blob_sha):
    """Return the stable dedupe key for one fetched GitHub file snapshot."""
    return f"github_file:{int(repository_id)}:{normalize_path(path)}:{str(blob_sha)}"
