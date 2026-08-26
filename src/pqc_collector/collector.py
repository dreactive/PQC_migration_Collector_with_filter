from datetime import datetime, timezone

from pqc_collector.keys import normalize_path, query_page_key, repository_key, search_item_key


def upsert_query_page(
    conn,
    batch_id,
    query,
    page,
    payload,
    raw_path,
    new_unique_item_count=0,
    duplicate_item_count=0,
    fetched_at=None,
):
    """Insert one query page row, or return the existing row without overwriting it."""
    page_size = int(query["page_size"])
    page_key = query_page_key(query["query_text"], page, page_size)
    existing = conn.execute(
        "SELECT * FROM query_pages WHERE query_page_key = ?",
        (page_key,),
    ).fetchone()
    if existing:
        row = dict(existing)
        row["status"] = "existing"
        return row

    item_count = len(payload.get("items", []))
    duplicate_ratio = duplicate_item_count / item_count if item_count else 0.0
    checked_at = fetched_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    row = {
        "query_page_key": page_key,
        "batch_id": batch_id,
        "query_key": query["query_key"],
        "query_group": query["query_group"],
        "page": int(page),
        "page_size": page_size,
        "total_count": int(payload.get("total_count", item_count)),
        "item_count": item_count,
        "new_unique_item_count": int(new_unique_item_count),
        "duplicate_item_count": int(duplicate_item_count),
        "duplicate_ratio": duplicate_ratio,
        "raw_path": str(raw_path),
        "fetched_at": checked_at,
    }
    conn.execute(
        """
        INSERT INTO query_pages (
            query_page_key,
            batch_id,
            query_key,
            query_group,
            page,
            page_size,
            total_count,
            item_count,
            new_unique_item_count,
            duplicate_item_count,
            duplicate_ratio,
            raw_path,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(row.values()),
    )
    conn.commit()
    row["status"] = "new"
    return row


def upsert_repository(conn, batch_id, repository):
    """Insert or update one GitHub repository metadata row."""
    repo_id = int(repository["id"])
    repo_key = repository_key(repo_id)
    full_name = repository["full_name"]
    html_url = repository.get("html_url") or repository.get("url")

    existing = conn.execute(
        "SELECT first_seen_batch_id FROM repositories WHERE repository_key = ?",
        (repo_key,),
    ).fetchone()
    status = "existing" if existing else "new"
    first_seen_batch_id = existing["first_seen_batch_id"] if existing else batch_id

    conn.execute(
        """
        INSERT INTO repositories (
            repository_key,
            repository_id,
            full_name,
            html_url,
            first_seen_batch_id,
            last_seen_batch_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(repository_key) DO UPDATE SET
            full_name = excluded.full_name,
            html_url = excluded.html_url,
            last_seen_batch_id = excluded.last_seen_batch_id
        """,
        (repo_key, repo_id, full_name, html_url, first_seen_batch_id, batch_id),
    )
    conn.commit()

    return {
        "repository_key": repo_key,
        "repository_id": repo_id,
        "full_name": full_name,
        "html_url": html_url,
        "status": status,
        "first_seen_batch_id": first_seen_batch_id,
        "last_seen_batch_id": batch_id,
    }


def upsert_raw_search_item(conn, batch_id, query_key, query_page_key, item, raw_query_page_path):
    """Insert or update one raw GitHub code search item row."""
    repository = item["repository"]
    repo_row = upsert_repository(conn, batch_id, repository)
    normalized_path = normalize_path(item["path"])
    item_key = search_item_key(repository["id"], normalized_path, item["sha"])

    existing = conn.execute(
        "SELECT first_seen_batch_id FROM raw_search_items WHERE search_item_key = ?",
        (item_key,),
    ).fetchone()
    status = "existing" if existing else "new"
    first_seen_batch_id = existing["first_seen_batch_id"] if existing else batch_id
    repository_url = repository.get("html_url") or repository.get("url")

    conn.execute(
        """
        INSERT INTO raw_search_items (
            search_item_key,
            batch_id,
            query_key,
            query_page_key,
            repository_key,
            repository_id,
            repository_full_name,
            repository_url,
            path,
            normalized_path,
            blob_sha,
            file_api_url,
            html_url,
            status,
            first_seen_batch_id,
            last_seen_batch_id,
            raw_query_page_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(search_item_key) DO UPDATE SET
            batch_id = excluded.batch_id,
            query_key = excluded.query_key,
            query_page_key = excluded.query_page_key,
            status = excluded.status,
            last_seen_batch_id = excluded.last_seen_batch_id,
            raw_query_page_path = excluded.raw_query_page_path
        """,
        (
            item_key,
            batch_id,
            query_key,
            query_page_key,
            repo_row["repository_key"],
            int(repository["id"]),
            repository["full_name"],
            repository_url,
            item["path"],
            normalized_path,
            item["sha"],
            item["url"],
            item["html_url"],
            status,
            first_seen_batch_id,
            batch_id,
            str(raw_query_page_path),
        ),
    )
    conn.commit()

    return {
        "search_item_key": item_key,
        "repository_key": repo_row["repository_key"],
        "repository_full_name": repository["full_name"],
        "path": item["path"],
        "normalized_path": normalized_path,
        "blob_sha": item["sha"],
        "status": status,
        "first_seen_batch_id": first_seen_batch_id,
        "last_seen_batch_id": batch_id,
        "raw_query_page_path": str(raw_query_page_path),
    }
