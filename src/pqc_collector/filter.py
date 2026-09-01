"""Static filter and classifier functions for later pipeline phases.

This module intentionally starts without pipeline logic. F0/F1/D0/F2 functions
will be added here one minimum feature at a time.
"""

from datetime import datetime, timezone

from pqc_collector.core import normalize_path


DROP_SOURCE_KINDS = {
    "docs",
    "dependency",
    "vendor_or_generated",
    "test",
    "example",
    "fuzz_or_benchmark",
    "tooling_metadata",
}

DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".adoc"}
DOC_NAMES = {"readme", "changelog", "changes", "license", "notice", "copying"}
DEPENDENCY_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "cargo.lock",
    "go.sum",
    "go.mod",
    "poetry.lock",
    "pipfile.lock",
}
CONFIG_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".ini",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
}
SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".py",
    ".js",
    ".ts",
    ".cs",
}
LANGUAGE_BY_EXTENSION = {
    ".c": "C",
    ".h": "C",
    ".java": "Java",
    ".cs": "C#",
}
DEFAULT_TARGET_LIBRARY_SIGNALS = {
    "JCE/JCA": {
        "languages": {"Java"},
        "signals": [
            "Cipher.getInstance",
            "KeyPairGenerator.getInstance",
            "KeyAgreement.getInstance",
            "Signature.getInstance",
            "AlgorithmParameters.getInstance",
            "Security.addProvider",
            "Security.getProvider",
        ],
    },
    "Bouncy Castle": {
        "languages": {"Java", "C#"},
        "signals": [
            "BouncyCastleProvider",
            "BouncyCastlePQCProvider",
            "BCPQC",
            "org.bouncycastle",
            "Org.BouncyCastle",
            "KEMGenerateSpec",
            "KEMExtractSpec",
            "MLKEMParameterSpec",
            "MLDSAParameterSpec",
        ],
    },
    "wolfSSL": {
        "languages": {"C"},
        "signals": [
            "wolfSSL_",
            "wolfSSL_CTX_",
            "wc_",
            "wc_MlKemKey_",
            "WOLFSSL_HAVE_MLKEM",
            "HAVE_PQC",
        ],
    },
    "OpenSSL": {
        "languages": {"C"},
        "signals": [
            "EVP_PKEY_CTX_new_from_name",
            "EVP_PKEY_encapsulate",
            "EVP_PKEY_decapsulate",
            "SSL_CTX_set1_groups",
            "SSL_set1_groups",
            "OSSL_PROVIDER_load",
            "OPENSSL_init_ssl",
        ],
    },
}


def _path_parts(path):
    return [part.lower() for part in normalize_path(path).split("/") if part]


def _file_name(path):
    parts = _path_parts(path)
    return parts[-1] if parts else ""


def _extension(file_name):
    if "." not in file_name:
        return ""
    return "." + file_name.rsplit(".", 1)[1]


def detect_language(path, content=None):
    """Return a conservative language label from the file extension."""
    return LANGUAGE_BY_EXTENSION.get(_extension(_file_name(path)))


def _target_library_rules(config=None):
    if not config:
        return DEFAULT_TARGET_LIBRARY_SIGNALS
    return config.get("target_libraries", config)


def _iter_library_signal_rules(config=None):
    for library, rule in _target_library_rules(config).items():
        languages = set(rule.get("languages", []))
        for signal in rule.get("signals", []):
            yield library, signal, languages


def _contains_signal(content, signal):
    return signal.lower() in content.lower()


def find_target_library_signals(path, content, config=None):
    """Return target legacy library signal matches for one fetched file."""
    language = detect_language(path, content)
    matches = []
    seen = set()
    for library, signal, languages in _iter_library_signal_rules(config):
        if languages and language not in languages:
            continue
        if not _contains_signal(content or "", signal):
            continue
        key = (library, signal.lower())
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "target_library": library,
                "signal": signal,
                "matched_text": signal,
                "language": language,
                "source": "content",
            }
        )
    return matches


def is_documentation_path(path):
    """Return True for docs, README, changelog, license-like paths."""
    parts = _path_parts(path)
    name = _file_name(path)
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return (
        "docs" in parts
        or "doc" in parts
        or ".github" in parts
        or stem in DOC_NAMES
        or _extension(name) in DOC_EXTENSIONS
    )


def is_vendor_path(path):
    """Return True for vendored, external, generated, build, or dist paths."""
    parts = _path_parts(path)
    name = _file_name(path)
    vendor_parts = {
        "vendor",
        "vendors",
        "third_party",
        "third-party",
        "3rdparty",
        "3rd",
        "external",
        "generated",
        "build",
        "dist",
    }
    return bool(vendor_parts.intersection(parts)) or ".generated." in name


def is_generated_path(path):
    """Return True for generated paths not already covered by vendor helpers."""
    parts = _path_parts(path)
    name = _file_name(path)
    return "gen" in parts or name.endswith(".pb.c") or name.endswith(".pb.h")


def is_test_like_path(path):
    """Return True for test, spec, example, demo, fuzz, or benchmark paths."""
    parts = _path_parts(path)
    name = _file_name(path)
    test_parts = {"test", "tests", "spec", "specs"}
    example_parts = {"example", "examples", "sample", "samples", "demo", "demos"}
    fuzz_parts = {"fuzz", "fuzzer", "fuzzers", "benchmark", "bench", "benches"}
    return (
        bool(test_parts.intersection(parts))
        or name.startswith("test_")
        or "_test." in name
        or name.endswith("test.java")
        or bool(example_parts.intersection(parts))
        or bool(fuzz_parts.intersection(parts))
    )


def classify_path(path, rules=None):
    """Classify one repository path for the F0 path quality filter."""
    normalized_path = normalize_path(path)
    parts = _path_parts(normalized_path)
    name = _file_name(normalized_path)
    extension = _extension(name)

    if not normalized_path:
        source_kind = "unknown"
        reason_codes = ["drop_empty_path"]
    elif name in {".ctags"} or ".ctags.d" in parts:
        source_kind = "tooling_metadata"
        reason_codes = ["drop_tooling_metadata_path"]
    elif name in DEPENDENCY_FILES:
        source_kind = "dependency"
        reason_codes = ["drop_dependency_lock_path"]
    elif is_documentation_path(normalized_path):
        source_kind = "docs"
        reason_codes = ["drop_docs_path"]
    elif is_vendor_path(normalized_path) or is_generated_path(normalized_path):
        source_kind = "vendor_or_generated"
        reason_codes = ["drop_vendor_or_generated_path"]
    elif any(part in {"fuzz", "fuzzer", "fuzzers", "benchmark", "bench", "benches"} for part in parts):
        source_kind = "fuzz_or_benchmark"
        reason_codes = ["drop_fuzz_or_benchmark_path"]
    elif any(part in {"example", "examples", "sample", "samples", "demo", "demos"} for part in parts):
        source_kind = "example"
        reason_codes = ["drop_example_path"]
    elif is_test_like_path(normalized_path):
        source_kind = "test"
        reason_codes = ["drop_test_path"]
    elif extension in CONFIG_EXTENSIONS:
        source_kind = "config_code"
        reason_codes = ["f0_pass_config_path"]
    elif extension in SOURCE_EXTENSIONS:
        source_kind = "application_code"
        reason_codes = ["f0_pass_application_path"]
    else:
        source_kind = "unknown"
        reason_codes = ["drop_unknown_path_type"]

    passed = source_kind not in DROP_SOURCE_KINDS and source_kind != "unknown"
    return {
        "source_kind": source_kind,
        "passed": passed,
        "reason_codes": reason_codes,
    }


def _item_value(item, key, default=None):
    try:
        value = item[key]
    except (KeyError, TypeError, IndexError):
        value = default
    return default if value is None else value


def run_f0_for_item(item, rules=None, checked_at=None):
    """Build one F0 path quality result row from one raw search item."""
    path = _item_value(item, "path", "")
    normalized_path = _item_value(item, "normalized_path", normalize_path(path))
    classification = classify_path(normalized_path or path, rules)
    timestamp = checked_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "batch_id": _item_value(item, "batch_id"),
        "search_item_key": _item_value(item, "search_item_key"),
        "repository_full_name": _item_value(item, "repository_full_name"),
        "path": path,
        "normalized_path": normalized_path,
        "source_kind": classification["source_kind"],
        "passed": classification["passed"],
        "reason_codes": classification["reason_codes"],
        "checked_at": timestamp,
    }
