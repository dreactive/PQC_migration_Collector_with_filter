import hashlib


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
