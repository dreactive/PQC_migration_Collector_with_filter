import hashlib


def query_page_key(query_text, page, page_size):
    """Return the stable dedupe key for one GitHub search query page."""
    key_material = f"{query_text}\n{int(page)}\n{int(page_size)}"
    return hashlib.sha256(key_material.encode("utf-8")).hexdigest()
