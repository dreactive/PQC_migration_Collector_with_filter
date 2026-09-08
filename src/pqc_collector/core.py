import hashlib
import json
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


def diff_file_key(repository_id, commit_sha, path):
    """Return the stable dedupe key for one exact changed file patch."""
    return f"github_diff_file:{int(repository_id)}:{str(commit_sha)}:{normalize_path(path)}"


def _row_value(row, *names):
    for name in names:
        if isinstance(row, dict) and name in row:
            return row.get(name)
        if hasattr(row, "keys") and name in row.keys():
            return row[name]
    return None


def candidate_key_components(row):
    """Return stable export candidate identity components from an F2/export row."""
    repository = _row_value(row, "repository") or {}
    source = _row_value(row, "source") or {}
    repository_id = _row_value(row, "repository_id") or repository.get("id")
    repository_full_name = (
        _row_value(row, "repository_full_name")
        or repository.get("full_name")
        or repository.get("name")
    )
    commit_sha = _row_value(row, "commit_sha") or source.get("commit_sha")
    pr_number = _row_value(row, "pr_number") or source.get("pr_number")
    primary_path = (
        _row_value(row, "matched_changed_path", "search_item_path", "path")
        or source.get("primary_path")
    )
    return {
        "provider": "github",
        "repository_id": int(repository_id) if repository_id is not None else None,
        "repository_full_name": repository_full_name,
        "commit_sha": str(commit_sha) if commit_sha else None,
        "pr_number": int(pr_number) if pr_number is not None else None,
        "primary_path": normalize_path(primary_path or ""),
    }


def candidate_key(components):
    """Return a stable dedupe key for one export candidate."""
    normalized = {
        key: value
        for key, value in dict(components).items()
        if value not in (None, "")
    }
    if normalized.get("repository_id") is not None:
        normalized.pop("repository_full_name", None)
    key_material = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"candidate:{hashlib.sha256(key_material.encode('utf-8')).hexdigest()}"
