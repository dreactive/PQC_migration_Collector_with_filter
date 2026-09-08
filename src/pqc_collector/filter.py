"""Static filter and classifier functions for later pipeline phases.

This module intentionally starts without pipeline logic. F0/F1/D0/F2 functions
will be added here one minimum feature at a time.
"""

import re
from datetime import datetime, timezone

from pqc_collector.core import diff_file_key, normalize_path


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
NEAR_CONTEXT_CHARS = 120
DEFAULT_STRONG_PQC_DIRECT_SIGNALS = {
    "BouncyCastlePQCProvider": "pqc_api",
    "MLKEMParameterSpec": "pqc_api",
    "MLDSAParameterSpec": "pqc_api",
    "wc_MlKemKey_": "pqc_api",
    "WC_ML_KEM": "pqc_api",
    "OQS_KEM_new": "pqc_api",
    "OQS_KEM_encaps": "pqc_api",
    "OQS_KEM_decaps": "pqc_api",
    "OQS_SIG_new": "pqc_api",
    "OQS_SIG_sign": "pqc_api",
    "OQS_SIG_verify": "pqc_api",
    "X25519MLKEM768": "pqc_group",
    "SecP256r1MLKEM768": "pqc_group",
}
DEFAULT_STRONG_PQC_NEAR_RULES = [
    {
        "signal": "EVP_PKEY_CTX_new_from_name",
        "near": ["ML-KEM", "MLKEM", "ML-DSA", "MLDSA"],
        "signal_type": "pqc_api",
    },
    {
        "signal": "EVP_PKEY_encapsulate",
        "near": ["ML-KEM", "MLKEM", "KEM"],
        "signal_type": "pqc_api",
    },
    {
        "signal": "EVP_PKEY_decapsulate",
        "near": ["ML-KEM", "MLKEM", "KEM"],
        "signal_type": "pqc_api",
    },
    {
        "signal": "SSL_CTX_set1_groups",
        "near": ["X25519MLKEM768", "SecP256r1MLKEM768", "MLKEM"],
        "signal_type": "pqc_group",
    },
    {
        "signal": "SSL_set1_groups",
        "near": ["X25519MLKEM768", "SecP256r1MLKEM768", "MLKEM"],
        "signal_type": "pqc_group",
    },
    {
        "signal": "OSSL_PROVIDER_load",
        "near": ["oqsprovider", "oqs-provider", "oqs"],
        "signal_type": "provider",
    },
]
DEFAULT_LEGACY_REMOVED_SIGNALS = {
    "X25519": "legacy_removed",
    "SecP256r1": "legacy_removed",
    "P-256": "legacy_removed",
    "prime256v1": "legacy_removed",
    "ECDH": "legacy_removed",
    "ECDSA": "legacy_removed",
    "RSA": "legacy_removed",
}
DEFAULT_HYBRID_TERMS = [
    "hybrid",
    "classical + post-quantum",
    "classical and post-quantum",
    "ECDH + ML-KEM",
    "RSA + ML-KEM",
    "X25519MLKEM768",
    "SecP256r1MLKEM768",
]
DEFAULT_HYBRID_MESSAGE_TERMS = [
    "hybrid key exchange",
    "hybrid KEM",
    "hybrid signature",
]
DEFAULT_MIGRATION_INTENT_TERMS = [
    "migrate",
    "migration",
    "replace",
    "switch",
    "enable",
    "add support",
    "introduce",
    "for client",
    "for tls",
    "for provider",
]
DEFAULT_CRYPTO_ROLE_TERMS = [
    "tls",
    "ssl",
    "crypto",
    "key exchange",
    "signature",
    "cipher",
    "provider",
    "group",
    "handshake",
]
DEFAULT_PARTIAL_SCOPE_TERMS = [
    "client",
    "server",
    "provider",
    "profile",
    "platform",
    "tls",
    "config",
]
DEFAULT_PARTIAL_FEATURE_TERMS = [
    "feature flag",
    "optional",
    "experimental",
    "disabled by default",
    "enable_",
    "with_",
    "use_",
]


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


def strip_code_comments(content):
    """Remove common code comments while preserving string literals."""
    text = str(content or "")
    output = []
    index = 0
    quote = None
    escaped = False

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if quote:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            output.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        if char == "#":
            index += 1
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            output.append(" ")
            index += 2
            while index < len(text) - 1:
                if text[index] == "*" and text[index + 1] == "/":
                    index += 2
                    break
                if text[index] in "\r\n":
                    output.append(text[index])
                index += 1
            output.append(" ")
            continue

        output.append(char)
        index += 1

    return "".join(output)


def _signal_context(content, index, size=NEAR_CONTEXT_CHARS):
    start = max(0, index - size)
    end = min(len(content), index + size)
    return content[start:end].strip()


def _line_number_at(content, index):
    if index < 0:
        return None
    return str(content or "").count("\n", 0, index) + 1


def _line_context_at(content, index):
    text = str(content or "")
    if index < 0:
        return ""
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end].strip()


def _find_signal_index(content, signal):
    return content.lower().find(signal.lower())


def _strong_pqc_rules(config=None):
    if not config:
        return DEFAULT_STRONG_PQC_DIRECT_SIGNALS, DEFAULT_STRONG_PQC_NEAR_RULES
    rules = config.get("strong_pqc_signals", config)
    direct = rules.get("direct", DEFAULT_STRONG_PQC_DIRECT_SIGNALS)
    near = rules.get("near", DEFAULT_STRONG_PQC_NEAR_RULES)
    return direct, near


def _unique_values(values):
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _config_section(configs, name):
    if not configs:
        return None
    return configs.get(name, configs)


def find_target_library_signals(path, content, config=None):
    """Return target legacy library signal matches for one fetched file."""
    language = detect_language(path, content)
    content = content or ""
    matches = []
    seen = set()
    for library, signal, languages in _iter_library_signal_rules(config):
        if languages and language not in languages:
            continue
        index = _find_signal_index(content, signal)
        if index < 0:
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
                "source_field": "content_text",
                "line_number": _line_number_at(content, index),
                "context": _line_context_at(content, index),
            }
        )
    return matches


def find_strong_pqc_signals(content, config=None):
    """Return strong PQC API/provider signal matches from file content."""
    content = strip_code_comments(content)
    direct_rules, near_rules = _strong_pqc_rules(config)
    matches = []
    seen = set()

    for signal, signal_type in direct_rules.items():
        index = _find_signal_index(content, signal)
        if index < 0:
            continue
        key = (signal.lower(), signal_type, None)
        seen.add(key)
        matches.append(
            {
                "signal": signal,
                "matched_text": signal,
                "signal_type": signal_type,
                "near": None,
                "line_number": _line_number_at(content, index),
                "context": _signal_context(content, index),
                "source_field": "content_text",
            }
        )

    for rule in near_rules:
        signal = rule["signal"]
        signal_index = _find_signal_index(content, signal)
        if signal_index < 0:
            continue
        context = _signal_context(content, signal_index)
        near_matches = [
            near_signal
            for near_signal in rule.get("near", [])
            if _contains_signal(context, near_signal)
        ]
        if not near_matches:
            continue
        near_signal = sorted(near_matches, key=len, reverse=True)[0]
        signal_type = rule.get("signal_type", "pqc_api")
        key = (signal.lower(), signal_type)
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "signal": signal,
                "matched_text": signal,
                "signal_type": signal_type,
                "near": near_signal,
                "line_number": _line_number_at(content, signal_index),
                "context": context,
                "source_field": "content_text",
            }
        )
    return matches


def _with_raw_path(evidence, raw_path):
    return [{**item, "raw_path": raw_path} for item in evidence]


def _f0_passed(file_row, f0_result=None):
    if f0_result is not None and "passed" in f0_result:
        return bool(f0_result["passed"])
    source_kind = _item_value(file_row, "source_kind")
    return bool(source_kind and source_kind not in DROP_SOURCE_KINDS and source_kind != "unknown")


def _quality_summary(file_row, f0_result=None):
    source_kind = _item_value(f0_result, "source_kind", _item_value(file_row, "source_kind"))
    return {
        "source_kind": source_kind,
        "is_docs": source_kind == "docs",
        "is_vendor_or_generated": source_kind == "vendor_or_generated",
        "is_test": source_kind == "test",
        "is_example": source_kind == "example",
        "is_fuzz_or_benchmark": source_kind == "fuzz_or_benchmark",
    }


def run_f1(file_row, f0_result=None, configs=None, checked_at=None):
    """Build one F1 static candidate result row from a fetched file snapshot."""
    path = _item_value(file_row, "path", "")
    content = _item_value(file_row, "content_text", "")
    language = detect_language(path, content)
    f0_passed = _f0_passed(file_row, f0_result)
    if f0_passed and language:
        library_matches = find_target_library_signals(
            path,
            content,
            _config_section(configs, "target_libraries"),
        )
        strong_matches = find_strong_pqc_signals(
            content,
            _config_section(configs, "strong_pqc_signals"),
        )
    else:
        library_matches = []
        strong_matches = []
    pqc_api_signals = [
        match["signal"]
        for match in strong_matches
        if match.get("signal_type") != "provider"
    ]
    provider_signals = [
        match["near"] or match["signal"]
        for match in strong_matches
        if match.get("signal_type") == "provider"
    ]
    reason_codes = []

    if not f0_passed:
        reason_codes.append("drop_f0_failed")
    if language is None:
        reason_codes.append("drop_unsupported_language")
    if library_matches:
        reason_codes.append("target_library_signal_detected")
    else:
        reason_codes.append("drop_no_target_library_signal")
    if strong_matches:
        reason_codes.append("strong_pqc_api_signal_detected")
    else:
        reason_codes.append("drop_no_strong_pqc_signal")
    if provider_signals:
        reason_codes.append("provider_signal_detected")

    passed = f0_passed and bool(language) and bool(library_matches) and bool(strong_matches)
    reason_codes.append("f1_pass" if passed else "f1_drop")
    timestamp = checked_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    raw_file_path = _item_value(file_row, "raw_file_path")
    return {
        "batch_id": _item_value(file_row, "batch_id"),
        "search_item_key": _item_value(file_row, "search_item_key"),
        "file_key": _item_value(file_row, "file_key"),
        "path": path,
        "language": language,
        "passed": passed,
        "target_libraries": _unique_values(
            match["target_library"] for match in library_matches
        ),
        "matched_library_signals": _unique_values(match["signal"] for match in library_matches),
        "matched_pqc_api_signals": _unique_values(pqc_api_signals),
        "matched_provider_signals": _unique_values(provider_signals),
        "library_evidence": _with_raw_path(library_matches, raw_file_path),
        "strong_signal_evidence": _with_raw_path(strong_matches, raw_file_path),
        "quality": _quality_summary(file_row, f0_result),
        "reason_codes": reason_codes,
        "raw_file_path": raw_file_path,
        "checked_at": timestamp,
    }


HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<section>.*)$"
)


def _parse_hunk_header(header):
    match = HUNK_HEADER_RE.match(header)
    if not match:
        return None
    return {
        "old_start": int(match.group("old_start")),
        "old_count": int(match.group("old_count") or 1),
        "new_start": int(match.group("new_start")),
        "new_count": int(match.group("new_count") or 1),
        "section": match.group("section").strip(),
    }


def parse_patch(patch_text):
    """Parse unified diff text into hunks with old/new file line numbers."""
    hunks = []
    current = None
    old_line = None
    new_line = None

    for patch_line_no, raw_line in enumerate(str(patch_text or "").splitlines(), start=1):
        header = _parse_hunk_header(raw_line)
        if header is not None:
            current = {
                "hunk_index": len(hunks) + 1,
                "header": raw_line,
                **header,
                "lines": [],
            }
            hunks.append(current)
            old_line = header["old_start"]
            new_line = header["new_start"]
            continue

        if current is None:
            continue

        if raw_line.startswith("\\ No newline at end of file"):
            current["lines"].append(
                {
                    "kind": "metadata",
                    "patch_line_no": patch_line_no,
                    "old_file_line": None,
                    "new_file_line": None,
                    "content": raw_line,
                    "raw_line": raw_line,
                    "context": raw_line,
                }
            )
            continue

        prefix = raw_line[:1]
        content = raw_line[1:] if prefix in {" ", "+", "-"} else raw_line
        if prefix == "+":
            line = {
                "kind": "added",
                "old_file_line": None,
                "new_file_line": new_line,
            }
            new_line += 1
        elif prefix == "-":
            line = {
                "kind": "removed",
                "old_file_line": old_line,
                "new_file_line": None,
            }
            old_line += 1
        else:
            line = {
                "kind": "context",
                "old_file_line": old_line,
                "new_file_line": new_line,
            }
            old_line += 1
            new_line += 1

        line.update(
            {
                "patch_line_no": patch_line_no,
                "content": content,
                "raw_line": raw_line,
                "context": raw_line,
            }
        )
        current["lines"].append(line)

    return hunks


def iter_patch_lines(hunks):
    """Yield parsed patch lines from parsed hunks in file order."""
    for hunk in hunks or []:
        for line in hunk.get("lines", []):
            yield {**line, "hunk_index": hunk.get("hunk_index"), "hunk_header": hunk.get("header")}


def extract_added_lines(hunks):
    """Return parsed added lines from parsed hunks."""
    return [line for line in iter_patch_lines(hunks) if line.get("kind") == "added"]


def extract_removed_lines(hunks):
    """Return parsed removed lines from parsed hunks."""
    return [line for line in iter_patch_lines(hunks) if line.get("kind") == "removed"]


def _match_terms(match):
    terms = []
    for key in ("terms", "matched_terms", "signals"):
        value = match.get(key)
        if isinstance(value, str):
            terms.append(value)
        elif value:
            terms.extend(str(term) for term in value)
    signal = match.get("signal")
    if signal:
        terms.append(str(signal))
    return _unique_values(term for term in terms if term)


def _match_kinds(match):
    kinds = match.get("kinds") or match.get("line_kinds")
    if isinstance(kinds, str):
        return {kinds}
    if kinds:
        return {str(kind) for kind in kinds}
    kind = match.get("kind")
    if isinstance(kind, str) and kind.startswith("patch_") and kind.endswith("_line"):
        return {kind.removeprefix("patch_").removesuffix("_line")}
    return None


def build_line_evidence(patch_lines, matches):
    """Build F2 review evidence rows from parsed patch lines and term matches."""
    evidence_rows = []
    counter = 1
    for line in patch_lines or []:
        line_kind = line.get("kind")
        line_text = line.get("content") or line.get("context") or ""
        for match in matches or []:
            line_numbers = match.get("line_numbers")
            if line_numbers and line.get("patch_line_no") not in line_numbers:
                continue
            allowed_kinds = _match_kinds(match)
            if allowed_kinds and line_kind not in allowed_kinds:
                continue
            matched_terms = [
                term for term in _match_terms(match) if _contains_signal(line_text, term)
            ]
            if not matched_terms:
                continue

            raw_path = match.get("raw_path") or match.get("patch_path")
            evidence_rows.append(
                {
                    "evidence_id": f"ev:{counter:03d}",
                    "supports": list(match.get("supports", [])),
                    "kind": match.get("kind") or f"patch_{line_kind}_line",
                    "repository_full_name": match.get("repository_full_name"),
                    "commit_sha": match.get("commit_sha"),
                    "commit_url": match.get("commit_url"),
                    "file_path": match.get("file_path"),
                    "patch_path": match.get("patch_path") or raw_path,
                    "patch_hunk_header": line.get("hunk_header"),
                    "patch_line_no": line.get("patch_line_no"),
                    "new_file_line": line.get("new_file_line"),
                    "old_file_line": line.get("old_file_line"),
                    "line_number": line.get("patch_line_no"),
                    "signal": match.get("signal") or matched_terms[0],
                    "signal_type": match.get("signal_type"),
                    "near": match.get("near"),
                    "source_field": match.get("source_field", "patch"),
                    "raw_path": raw_path,
                    "context": line.get("context") or line_text,
                    "matched_terms": matched_terms,
                    "snippet": line.get("context") or line_text,
                }
            )
            counter += 1
    return evidence_rows


def _line_hunk_text(line, patch_lines):
    hunk_index = line.get("hunk_index")
    return "\n".join(
        other.get("content") or ""
        for other in patch_lines
        if other.get("hunk_index") == hunk_index
    )


def _pqc_added_matches(patch_lines, config=None):
    direct_rules, near_rules = _strong_pqc_rules(config)
    matches = []
    seen = set()
    for line in patch_lines:
        if line.get("kind") != "added":
            continue
        line_text = line.get("content") or ""
        hunk_text = _line_hunk_text(line, patch_lines)

        for signal, signal_type in direct_rules.items():
            if not _contains_signal(line_text, signal):
                continue
            key = (line.get("patch_line_no"), signal, signal_type, None)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                {
                    "line_kinds": ["added"],
                    "line_numbers": [line.get("patch_line_no")],
                    "supports": ["pqc_added_in_diff"],
                    "kind": "patch_added_line",
                    "signal": signal,
                    "signal_type": signal_type,
                    "terms": [signal],
                    "source_field": "patch",
                }
            )

        for rule in near_rules:
            signal = rule["signal"]
            if not _contains_signal(line_text, signal):
                continue
            near_terms = [
                near for near in rule.get("near", []) if _contains_signal(hunk_text, near)
            ]
            if not near_terms:
                continue
            near = sorted(near_terms, key=len, reverse=True)[0]
            signal_type = rule.get("signal_type", "pqc_api")
            key = (line.get("patch_line_no"), signal, signal_type, near)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                {
                    "line_kinds": ["added"],
                    "line_numbers": [line.get("patch_line_no")],
                    "supports": ["pqc_added_in_diff"],
                    "kind": "patch_added_line",
                    "signal": signal,
                    "signal_type": signal_type,
                    "near": near,
                    "terms": [signal, near],
                    "source_field": "patch",
                }
            )
    return matches


def detect_pqc_added(parsed_patch, config=None):
    """Detect strong PQC additions from added patch lines only."""
    patch_lines = list(iter_patch_lines(parsed_patch))
    matches = _pqc_added_matches(patch_lines, config)
    evidence = build_line_evidence(patch_lines, matches)
    matched_terms = []
    for row in evidence:
        matched_terms.extend(row.get("matched_terms", []))
    pqc_added = bool(evidence)
    return {
        "pqc_added": pqc_added,
        "matched_terms": _unique_values(matched_terms),
        "review_evidence": evidence,
        "reason_codes": ["pqc_added_in_diff"] if pqc_added else ["drop_no_pqc_added_in_diff"],
    }


def _legacy_removed_signals(config=None):
    if not config:
        return DEFAULT_LEGACY_REMOVED_SIGNALS
    rules = config.get("legacy_removed_signals", config.get("legacy_signals"))
    if rules is None:
        return DEFAULT_LEGACY_REMOVED_SIGNALS
    if isinstance(rules, dict):
        return rules
    return {str(signal): "legacy_removed" for signal in rules or []}


def _legacy_removed_matches(patch_lines, config=None):
    matches = []
    seen = set()
    for line in patch_lines:
        if line.get("kind") != "removed":
            continue
        line_text = line.get("content") or ""
        for signal, signal_type in _legacy_removed_signals(config).items():
            if not _contains_signal(line_text, signal):
                continue
            key = (line.get("patch_line_no"), signal)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                {
                    "line_kinds": ["removed"],
                    "line_numbers": [line.get("patch_line_no")],
                    "supports": ["legacy_removed_in_diff"],
                    "kind": "patch_removed_line",
                    "signal": signal,
                    "signal_type": signal_type,
                    "terms": [signal],
                    "source_field": "patch",
                }
            )
    return matches


def detect_legacy_removed(parsed_patch, config=None):
    """Detect legacy crypto removals from removed patch lines only."""
    patch_lines = list(iter_patch_lines(parsed_patch))
    matches = _legacy_removed_matches(patch_lines, config)
    evidence = build_line_evidence(patch_lines, matches)
    matched_terms = []
    for row in evidence:
        matched_terms.extend(row.get("matched_terms", []))
    legacy_removed = bool(evidence)
    return {
        "legacy_removed": legacy_removed,
        "matched_terms": _unique_values(matched_terms),
        "review_evidence": evidence,
        "reason_codes": (
            ["legacy_removed_in_diff"] if legacy_removed else ["no_legacy_removed_in_diff"]
        ),
    }


def _hybrid_terms(config=None):
    if not config:
        return DEFAULT_HYBRID_TERMS
    return list(config.get("hybrid_terms", DEFAULT_HYBRID_TERMS))


def _hybrid_message_terms(config=None):
    if not config:
        return DEFAULT_HYBRID_MESSAGE_TERMS
    return list(config.get("hybrid_message_terms", DEFAULT_HYBRID_MESSAGE_TERMS))


def _pqc_family_terms(config=None):
    direct_rules, near_rules = _strong_pqc_rules(config)
    terms = list(direct_rules.keys())
    for rule in near_rules:
        terms.extend(rule.get("near", []))
    return _unique_values(terms)


def _line_match(line, terms):
    text = line.get("content") or ""
    return [term for term in terms if _contains_signal(text, term)]


def _message_evidence(message, matched_terms):
    return [
        {
            "evidence_id": f"ev:msg:{index:03d}",
            "supports": ["hybrid_signal_detected"],
            "kind": "commit_message",
            "repository_full_name": None,
            "commit_sha": None,
            "commit_url": None,
            "file_path": None,
            "patch_path": None,
            "patch_hunk_header": None,
            "patch_line_no": None,
            "new_file_line": None,
            "old_file_line": None,
            "line_number": None,
            "signal": term,
            "signal_type": "hybrid",
            "near": None,
            "source_field": "commit_message",
            "raw_path": None,
            "context": str(message or "").strip(),
            "matched_terms": [term],
            "snippet": str(message or "").strip(),
        }
        for index, term in enumerate(matched_terms, start=1)
    ]


def detect_hybrid_signal(parsed_patch, message=None, config=None):
    """Detect direct hybrid migration signals from added diff lines and message text."""
    patch_lines = list(iter_patch_lines(parsed_patch))
    added_lines = [line for line in patch_lines if line.get("kind") == "added"]
    hybrid_terms = _hybrid_terms(config)
    pqc_terms = _pqc_family_terms(config)
    legacy_terms = list(_legacy_removed_signals(config).keys())
    matches = []

    for line in added_lines:
        direct_terms = _line_match(line, hybrid_terms)
        if direct_terms:
            matches.append(
                {
                    "line_kinds": ["added"],
                    "line_numbers": [line.get("patch_line_no")],
                    "supports": ["hybrid_signal_detected"],
                    "kind": "patch_added_line",
                    "signal": direct_terms[0],
                    "signal_type": "hybrid",
                    "terms": direct_terms,
                    "source_field": "patch",
                }
            )
            continue

        hunk_text = _line_hunk_text(line, patch_lines)
        line_pqc_terms = _line_match(line, pqc_terms)
        line_legacy_terms = _line_match(line, legacy_terms)
        hunk_has_pqc = line_pqc_terms or any(_contains_signal(hunk_text, term) for term in pqc_terms)
        hunk_has_legacy = line_legacy_terms or any(
            _contains_signal(hunk_text, term) for term in legacy_terms
        )
        line_terms = line_pqc_terms or line_legacy_terms
        if hunk_has_pqc and hunk_has_legacy and line_terms:
            matches.append(
                {
                    "line_kinds": ["added"],
                    "line_numbers": [line.get("patch_line_no")],
                    "supports": ["hybrid_signal_detected"],
                    "kind": "patch_added_line",
                    "signal": "same_added_hunk_legacy_and_pqc",
                    "signal_type": "hybrid",
                    "terms": line_terms,
                    "source_field": "patch",
                }
            )

    evidence = build_line_evidence(patch_lines, matches)
    message_terms = [term for term in _hybrid_message_terms(config) if _contains_signal(message or "", term)]
    evidence.extend(_message_evidence(message, message_terms))
    matched_terms = []
    for row in evidence:
        matched_terms.extend(row.get("matched_terms", []))
    hybrid = bool(evidence)
    return {
        "hybrid_signal": hybrid,
        "matched_terms": _unique_values(matched_terms),
        "review_evidence": evidence,
        "reason_codes": ["hybrid_signal_detected"] if hybrid else ["no_hybrid_signal"],
    }


def _migration_intent_terms(config=None):
    if not config:
        return DEFAULT_MIGRATION_INTENT_TERMS
    return list(config.get("migration_intent_terms", DEFAULT_MIGRATION_INTENT_TERMS))


def _crypto_role_terms(config=None):
    if not config:
        return DEFAULT_CRYPTO_ROLE_TERMS
    return list(config.get("crypto_role_terms", DEFAULT_CRYPTO_ROLE_TERMS))


def _text_evidence(kind, source_field, signal_type, supports, text, terms):
    text = str(text or "").strip()
    return [
        {
            "evidence_id": f"ev:{kind}:{index:03d}",
            "supports": list(supports),
            "kind": kind,
            "repository_full_name": None,
            "commit_sha": None,
            "commit_url": None,
            "file_path": None,
            "patch_path": None,
            "patch_hunk_header": None,
            "patch_line_no": None,
            "new_file_line": None,
            "old_file_line": None,
            "line_number": None,
            "signal": term,
            "signal_type": signal_type,
            "near": None,
            "source_field": source_field,
            "raw_path": None,
            "context": text,
            "matched_terms": [term],
            "snippet": text,
        }
        for index, term in enumerate(terms, start=1)
    ]


def _patch_role_evidence(patch_lines, terms):
    matches = []
    for line in patch_lines:
        if line.get("kind") not in {"added", "removed"}:
            continue
        matched_terms = _line_match(line, terms)
        if not matched_terms:
            continue
        matches.append(
            {
                "line_kinds": [line.get("kind")],
                "line_numbers": [line.get("patch_line_no")],
                "supports": ["migration_context"],
                "kind": f"patch_{line.get('kind')}_line",
                "signal": matched_terms[0],
                "signal_type": "crypto_role",
                "terms": matched_terms,
                "source_field": "patch",
            }
        )
    return build_line_evidence(patch_lines, matches)


def _renumber_evidence(evidence):
    return [
        {
            **row,
            "evidence_id": f"ev:{index:03d}",
        }
        for index, row in enumerate(evidence, start=1)
    ]


def detect_migration_context(parsed_patch, message=None, path=None, config=None):
    """Detect whether a diff has enough migration context for F2 classification."""
    patch_lines = list(iter_patch_lines(parsed_patch))
    evidence = []
    matched_terms = []
    reason_codes = []

    legacy = detect_legacy_removed(parsed_patch, config)
    if legacy["legacy_removed"]:
        evidence.extend(legacy["review_evidence"])
        matched_terms.extend(legacy["matched_terms"])
        reason_codes.append("legacy_removed_in_diff")

    hybrid = detect_hybrid_signal(parsed_patch, message, config)
    if hybrid["hybrid_signal"]:
        evidence.extend(hybrid["review_evidence"])
        matched_terms.extend(hybrid["matched_terms"])
        reason_codes.append("hybrid_signal_detected")

    message_terms = [
        term for term in _migration_intent_terms(config) if _contains_signal(message or "", term)
    ]
    if message_terms:
        evidence.extend(
            _text_evidence(
                "commit_message",
                "commit_message",
                "intent",
                ["migration_context"],
                message,
                message_terms,
            )
        )
        matched_terms.extend(message_terms)
        reason_codes.append("matched_intent_terms")

    normalized_path = normalize_path(path)
    path_terms = [term for term in _crypto_role_terms(config) if _contains_signal(normalized_path, term)]
    if path_terms:
        evidence.extend(
            _text_evidence(
                "changed_path",
                "changed_path",
                "crypto_role_path",
                ["migration_context"],
                normalized_path,
                path_terms,
            )
        )
        matched_terms.extend(path_terms)
        reason_codes.append("crypto_role_path")

    role_evidence = _patch_role_evidence(patch_lines, _crypto_role_terms(config))
    if role_evidence:
        evidence.extend(role_evidence)
        for row in role_evidence:
            matched_terms.extend(row.get("matched_terms", []))
        reason_codes.append("crypto_role_term_in_diff")

    migration_context = bool(evidence)
    evidence = _renumber_evidence(evidence)
    return {
        "migration_context": migration_context,
        "matched_terms": _unique_values(matched_terms),
        "review_evidence": evidence,
        "reason_codes": _unique_values(reason_codes)
        if migration_context
        else ["no_migration_context"],
    }


def _patch_evidence_rows(result, kind):
    return [
        row
        for row in result.get("review_evidence", [])
        if row.get("kind") == kind and row.get("patch_hunk_header")
    ]


def _replacement_strength(pqc_rows, legacy_rows):
    pqc_hunks = {row.get("patch_hunk_header") for row in pqc_rows}
    legacy_hunks = {row.get("patch_hunk_header") for row in legacy_rows}
    if pqc_hunks.intersection(legacy_hunks):
        return "same_hunk"
    if pqc_rows and legacy_rows:
        return "same_file"
    return None


def _replacement_evidence(rows, reason_code):
    return [
        {
            **row,
            "supports": _unique_values([*row.get("supports", []), reason_code, "replacement_signal"]),
        }
        for row in rows
    ]


def detect_replacement_signal(parsed_patch, pqc_result=None, legacy_result=None, config=None):
    """Detect internal replacement signal from PQC additions and legacy removals."""
    pqc = pqc_result or detect_pqc_added(parsed_patch, config)
    legacy = legacy_result or detect_legacy_removed(parsed_patch, config)
    pqc_rows = _patch_evidence_rows(pqc, "patch_added_line")
    legacy_rows = _patch_evidence_rows(legacy, "patch_removed_line")
    strength = _replacement_strength(pqc_rows, legacy_rows)

    if not strength:
        return {
            "replacement_signal": False,
            "replacement_strength": None,
            "matched_terms": [],
            "review_evidence": [],
            "reason_codes": ["no_replacement_signal"],
        }

    reason_code = "legacy_removed_same_hunk" if strength == "same_hunk" else "legacy_removed_same_file"
    evidence = _replacement_evidence([*legacy_rows, *pqc_rows], reason_code)
    matched_terms = []
    for row in evidence:
        matched_terms.extend(row.get("matched_terms", []))
    return {
        "replacement_signal": True,
        "replacement_strength": strength,
        "matched_terms": _unique_values(matched_terms),
        "review_evidence": _renumber_evidence(evidence),
        "reason_codes": [reason_code, "replacement_signal"],
    }


def _partial_scope_terms(config=None):
    if not config:
        return DEFAULT_PARTIAL_SCOPE_TERMS
    return list(config.get("partial_scope_terms", DEFAULT_PARTIAL_SCOPE_TERMS))


def _partial_feature_terms(config=None):
    if not config:
        return DEFAULT_PARTIAL_FEATURE_TERMS
    return list(config.get("partial_feature_terms", DEFAULT_PARTIAL_FEATURE_TERMS))


def _partial_patch_evidence(parsed_patch, config=None):
    patch_lines = list(iter_patch_lines(parsed_patch))
    matches = []
    for line in patch_lines:
        if line.get("kind") != "added":
            continue
        matched_terms = _line_match(line, _partial_feature_terms(config))
        if not matched_terms:
            continue
        matches.append(
            {
                "line_kinds": ["added"],
                "line_numbers": [line.get("patch_line_no")],
                "supports": ["partial_feature_flag"],
                "kind": "patch_added_line",
                "signal": matched_terms[0],
                "signal_type": "partial_scope",
                "terms": matched_terms,
                "source_field": "patch",
            }
        )
    return build_line_evidence(patch_lines, matches)


def detect_partial_scope_signal(parsed_patch, message=None, path=None, config=None):
    """Detect partial migration scope hints from path, message, and added diff lines."""
    evidence = []
    matched_terms = []
    reason_codes = []

    normalized_path = normalize_path(path)
    path_terms = [
        term for term in _partial_scope_terms(config) if _contains_signal(normalized_path, term)
    ]
    if path_terms:
        evidence.extend(
            _text_evidence(
                "changed_path",
                "changed_path",
                "partial_scope_path",
                ["partial_scope_module_only"],
                normalized_path,
                path_terms,
            )
        )
        matched_terms.extend(path_terms)
        reason_codes.append("partial_scope_module_only")

    message_scope_terms = [
        term for term in _partial_scope_terms(config) if _contains_signal(message or "", term)
    ]
    message_intent_terms = [
        term for term in _migration_intent_terms(config) if _contains_signal(message or "", term)
    ]
    if message_scope_terms or message_intent_terms:
        terms = _unique_values([*message_scope_terms, *message_intent_terms])
        evidence.extend(
            _text_evidence(
                "commit_message",
                "commit_message",
                "partial_scope",
                ["partial_scope_module_only"],
                message,
                terms,
            )
        )
        matched_terms.extend(terms)
        reason_codes.append("partial_scope_module_only")

    feature_evidence = _partial_patch_evidence(parsed_patch, config)
    if feature_evidence:
        evidence.extend(feature_evidence)
        for row in feature_evidence:
            matched_terms.extend(row.get("matched_terms", []))
        reason_codes.append("partial_feature_flag")

    partial_scope = bool(evidence)
    return {
        "partial_scope_signal": partial_scope,
        "matched_terms": _unique_values(matched_terms),
        "review_evidence": _renumber_evidence(evidence),
        "reason_codes": _unique_values(reason_codes)
        if partial_scope
        else ["no_partial_scope_signal"],
    }


def _changed_file_current_path(changed_file):
    if not isinstance(changed_file, dict):
        return ""
    return changed_file.get("filename") or changed_file.get("path") or ""


def find_exact_changed_file(search_path, changed_files):
    """Return the changed file whose current path exactly matches search_path."""
    normalized_search_path = normalize_path(search_path)
    if not normalized_search_path:
        return None

    for index, changed_file in enumerate(changed_files or []):
        if not isinstance(changed_file, dict):
            continue
        changed_path = _changed_file_current_path(changed_file)
        normalized_changed_path = normalize_path(changed_path)
        if normalized_changed_path != normalized_search_path:
            continue

        patch = changed_file.get("patch")
        return {
            "search_path": search_path,
            "normalized_search_path": normalized_search_path,
            "changed_file_index": index,
            "changed_path": changed_path,
            "normalized_changed_path": normalized_changed_path,
            "status": changed_file.get("status"),
            "sha": changed_file.get("sha"),
            "additions": int(changed_file.get("additions") or 0),
            "deletions": int(changed_file.get("deletions") or 0),
            "changes": int(changed_file.get("changes") or 0),
            "patch": patch,
            "patch_available": bool(patch),
            "blob_url": changed_file.get("blob_url"),
            "raw_url": changed_file.get("raw_url"),
            "contents_url": changed_file.get("contents_url"),
        }
    return None


def _commit_payload(commit_or_pr_payload):
    if isinstance(commit_or_pr_payload, dict) and "payload" in commit_or_pr_payload:
        return commit_or_pr_payload["payload"]
    return commit_or_pr_payload or {}


def _commit_sha(payload):
    return payload.get("sha") or payload.get("commit_sha") or payload.get("head", {}).get("sha")


def _commit_url(payload, repository_full_name=None, commit_sha=None):
    return (
        payload.get("html_url")
        or payload.get("commit_url")
        or (
            f"https://github.com/{repository_full_name}/commit/{commit_sha}"
            if repository_full_name and commit_sha
            else None
        )
    )


def _changed_file_paths(changed_files):
    return [
        normalize_path(_changed_file_current_path(changed_file))
        for changed_file in changed_files or []
        if _changed_file_current_path(changed_file)
    ]


def _exact_path_evidence(item, matched_file, raw_commit_path):
    search_path = item.get("normalized_path") or item.get("search_item_path") or item.get("path")
    matched_path = matched_file["normalized_changed_path"]
    return {
        "supports": ["exact_changed_file_found"],
        "signal": matched_path,
        "signal_type": "exact_path",
        "line_number": None,
        "context": "changed_files.path exactly matched search item normalized_path",
        "source_field": "changed_files.path",
        "raw_path": raw_commit_path,
        "patch_hunk_header": None,
        "patch_line_no": None,
        "new_file_line": None,
        "old_file_line": None,
        "search_item_path": normalize_path(search_path),
        "changed_path": matched_path,
    }


def _patch_available_evidence(matched_file, patch_path):
    first_line = next(iter_patch_lines(parse_patch(matched_file.get("patch"))), None)
    return {
        "supports": ["patch_available"],
        "signal": "patch",
        "signal_type": "patch_hunk",
        "line_number": first_line.get("patch_line_no") if first_line else None,
        "context": first_line.get("context") if first_line else "patch is present",
        "source_field": "patch",
        "raw_path": patch_path,
        "patch_hunk_header": first_line.get("hunk_header") if first_line else None,
        "patch_line_no": first_line.get("patch_line_no") if first_line else None,
        "new_file_line": first_line.get("new_file_line") if first_line else None,
        "old_file_line": first_line.get("old_file_line") if first_line else None,
    }


def _missing_exact_path_evidence(search_path, changed_files, raw_commit_path):
    changed_paths = _changed_file_paths(changed_files)
    return {
        "supports": ["drop_no_exact_changed_file"],
        "signal": normalize_path(search_path),
        "signal_type": "exact_path",
        "line_number": None,
        "context": (
            "no changed_files.path exactly matched search item path; "
            f"changed_paths={changed_paths[:10]}"
        ),
        "source_field": "changed_files.path",
        "raw_path": raw_commit_path,
        "patch_hunk_header": None,
        "patch_line_no": None,
        "new_file_line": None,
        "old_file_line": None,
    }


def run_d0_for_item(item, commit_or_pr_payload, raw_commit_path=None, patch_path=None, checked_at=None):
    """Build one D0 exact diff evidence result row for one commit payload."""
    payload = _commit_payload(commit_or_pr_payload)
    changed_files = payload.get("files") or payload.get("changed_files") or []
    search_path = item.get("normalized_path") or item.get("search_item_path") or item.get("path")
    matched_file = find_exact_changed_file(search_path, changed_files)
    repository_id = item.get("repository_id")
    repository_full_name = item.get("repository_full_name")
    commit_sha = _commit_sha(payload)
    commit_url = _commit_url(payload, repository_full_name, commit_sha)
    reason_codes = []
    review_evidence = []

    if matched_file:
        reason_codes.append("exact_changed_file_found")
        review_evidence.append(_exact_path_evidence(item, matched_file, raw_commit_path))
    else:
        reason_codes.append("drop_no_exact_changed_file")
        review_evidence.append(_missing_exact_path_evidence(search_path, changed_files, raw_commit_path))

    patch_available = bool(matched_file and matched_file.get("patch_available"))
    if patch_available:
        reason_codes.append("patch_available")
        review_evidence.append(_patch_available_evidence(matched_file, patch_path))
    else:
        reason_codes.append("drop_no_patch")

    passed = bool(matched_file) and patch_available
    reason_codes.append("d0_pass" if passed else "d0_drop")
    matched_path = matched_file["normalized_changed_path"] if matched_file else None
    return {
        "batch_id": item.get("batch_id"),
        "search_item_key": item["search_item_key"],
        "file_key": item["file_key"],
        "repository_id": repository_id,
        "diff_file_key": (
            diff_file_key(repository_id, commit_sha, matched_path)
            if repository_id is not None and commit_sha and matched_path
            else None
        ),
        "repository_full_name": repository_full_name,
        "search_item_path": normalize_path(search_path),
        "commit_sha": commit_sha,
        "commit_url": commit_url,
        "matched_changed_path": matched_path,
        "exact_path_match": bool(matched_file),
        "patch_available": patch_available,
        "passed": passed,
        "changed_files": _changed_file_paths(changed_files),
        "review_evidence": review_evidence,
        "reason_codes": reason_codes,
        "raw_commit_path": raw_commit_path,
        "patch_path": patch_path if patch_available else None,
        "checked_at": checked_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


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
