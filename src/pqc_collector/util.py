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
