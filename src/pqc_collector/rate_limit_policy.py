from datetime import datetime, timezone


DEFAULT_SEARCH_REMAINING_FLOOR = 2
DEFAULT_CORE_REMAINING_FLOOR = 100
DEFAULT_RESUME_SAFETY_DELAY_SECONDS = 30


def _resource_snapshot(resources, name):
    resource = resources.get(name, {})
    return {
        "limit": resource.get("limit"),
        "remaining": resource.get("remaining"),
        "reset": resource.get("reset"),
    }


def _sleep_until(blocked_resources, safety_delay_seconds):
    reset_values = [
        resource["reset"]
        for resource in blocked_resources
        if isinstance(resource.get("reset"), int)
    ]
    if not reset_values:
        return None
    resume_at = max(reset_values) + int(safety_delay_seconds)
    return datetime.fromtimestamp(resume_at, timezone.utc).isoformat().replace("+00:00", "Z")


def evaluate_rate_limit_floor(
    rate_limit_payload,
    search_remaining_floor=DEFAULT_SEARCH_REMAINING_FLOOR,
    core_remaining_floor=DEFAULT_CORE_REMAINING_FLOOR,
    resume_safety_delay_seconds=DEFAULT_RESUME_SAFETY_DELAY_SECONDS,
):
    """Evaluate whether GitHub rate limit floors require sleeping."""
    resources = rate_limit_payload.get("resources", rate_limit_payload)
    search = _resource_snapshot(resources, "search")
    core = _resource_snapshot(resources, "core")
    floors = {
        "search": int(search_remaining_floor),
        "core": int(core_remaining_floor),
    }
    blocked_resources = []
    for name, snapshot in (("search", search), ("core", core)):
        remaining = snapshot.get("remaining")
        if remaining is not None and int(remaining) <= floors[name]:
            blocked_resources.append({"resource": name, **snapshot, "floor": floors[name]})

    blocked = bool(blocked_resources)
    return {
        "collector_status": "sleeping_rate_limit" if blocked else "idle",
        "blocked": blocked,
        "blocked_resources": blocked_resources,
        "search": {**search, "floor": floors["search"]},
        "core": {**core, "floor": floors["core"]},
        "sleep_until": _sleep_until(blocked_resources, resume_safety_delay_seconds),
        "resume_safety_delay_seconds": int(resume_safety_delay_seconds),
    }
