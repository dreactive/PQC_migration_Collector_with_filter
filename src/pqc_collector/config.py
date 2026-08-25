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
