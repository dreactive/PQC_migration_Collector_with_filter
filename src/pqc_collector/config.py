import json

from pqc_collector.util import project_paths


CONFIG_FILE_NAMES = {
    "collection_queries": "collection_queries.json",
    "path_rules": "path_rules.json",
    "target_libraries": "target_libraries.json",
    "pqc_patterns": "pqc_patterns.json",
    "legacy_patterns": "legacy_patterns.json",
    "migration_rules": "migration_rules.json",
}


def config_paths(root=None):
    """Return the canonical collector/filter config file paths."""
    config_dir = project_paths(root)["config"]
    return {name: config_dir / file_name for name, file_name in CONFIG_FILE_NAMES.items()}


def load_config(name, root=None):
    """Load one named JSON config file."""
    paths = config_paths(root)
    config_path = paths.get(name)
    if config_path is None:
        valid_names = ", ".join(sorted(paths))
        raise KeyError(f"unknown config: {name}. valid names: {valid_names}")

    with config_path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError(f"config must be a JSON object: {config_path}")

    return loaded


def load_all_configs(root=None):
    """Load every registered JSON config file."""
    return {name: load_config(name, root) for name in CONFIG_FILE_NAMES}
