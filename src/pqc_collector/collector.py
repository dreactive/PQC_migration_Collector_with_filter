from pqc_collector.keys import repository_key


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
