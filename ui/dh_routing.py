"""Natural-language routing helpers for drillhole validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath


SUPPORTED_TABLES = {
    "collar",
    "survey",
    "lithology",
    "assay",
    "mineralization",
    "oxidation",
    "geotech",
    "rqd",
    "vein",
    "alteration",
    "density",
}

DATA_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".xls"}

DEFAULT_INTENT_ALIASES = (
    "validasi",
    "validate",
    "validator",
    "cek error",
    "cek data",
    "periksa data",
    "cek interval",
    "cek overlap",
    "cek gap",
    "drillhole",
)

DEFAULT_ROLE_ALIASES = {
    "collar": "collar",
    "site": "collar",
    "gb_site": "collar",
    "hole": "collar",
    "lubang": "collar",
    "lobang": "collar",
    "survey": "survey",
    "site_survey": "survey",
    "gb_site_survey": "survey",
    "downhole_survey": "survey",
    "gb_downhole_survey": "survey",
    "lithology": "lithology",
    "litologi": "lithology",
    "gb_lithology": "lithology",
    "assay": "assay",
    "gb_assay": "assay",
    "mineralization": "mineralization",
    "mineralisasi": "mineralization",
    "gb_mineralization": "mineralization",
    "oxidation": "oxidation",
    "oksidasi": "oxidation",
    "gb_oxidation": "oxidation",
    "geotech": "geotech",
    "gb_geotech": "geotech",
    "rqd": "rqd",
    "gb_rqd": "rqd",
    "vein": "vein",
    "gb_vein": "vein",
    "alteration": "alteration",
    "alterasi": "alteration",
    "gb_alteration": "alteration",
    "density": "density",
    "densitas": "density",
    "gb_density": "density",
}

DEFAULT_COMPANION_ROLES = {
    "survey": ("collar",),
    "lithology": ("collar",),
    "assay": ("collar",),
    "mineralization": ("collar",),
    "oxidation": ("collar",),
    "geotech": ("collar",),
    "rqd": ("collar",),
    "vein": ("collar",),
    "alteration": ("collar",),
    "density": ("collar",),
}


@dataclass(frozen=True)
class DrillholeRoutingGuidance:
    intent_aliases: tuple[str, ...]
    role_aliases: dict[str, str]
    companion_roles: dict[str, tuple[str, ...]]


def load_drillhole_routing_guidance(workspace: str) -> DrillholeRoutingGuidance:
    """Load user-editable natural-language validation guidance from the workspace."""

    from pathlib import Path

    path = Path(workspace) / "drillhole_validation" / "default.md"
    guidance = DrillholeRoutingGuidance(
        intent_aliases=tuple(DEFAULT_INTENT_ALIASES),
        role_aliases=dict(DEFAULT_ROLE_ALIASES),
        companion_roles=dict(DEFAULT_COMPANION_ROLES),
    )
    if not path.exists():
        return guidance

    text = path.read_text(encoding="utf-8")
    sections = _parse_markdown_sections(text)
    intents = list(guidance.intent_aliases)
    role_aliases = dict(guidance.role_aliases)
    companions = {role: list(required) for role, required in guidance.companion_roles.items()}

    for item in sections.get("intent aliases", []):
        alias, target = _split_mapping(item)
        if alias and (not target or target == "validate_drillhole"):
            intents.append(alias)

    for item in sections.get("file role aliases", []):
        alias, role = _split_mapping(item)
        if alias and role in SUPPORTED_TABLES:
            role_aliases[_normalize(alias)] = role

    for item in sections.get("required companion files", []):
        role, required = _split_companion(item)
        if role in SUPPORTED_TABLES and required in SUPPORTED_TABLES:
            companions.setdefault(role, [])
            if required not in companions[role]:
                companions[role].append(required)

    return DrillholeRoutingGuidance(
        intent_aliases=tuple(dict.fromkeys(_normalize_phrase(alias) for alias in intents if alias.strip())),
        role_aliases=role_aliases,
        companion_roles={role: tuple(required) for role, required in companions.items()},
    )


def infer_drillhole_validation_action(
    message: str,
    *,
    workspace: str,
    workspace_files: list[str],
) -> dict[str, object] | None:
    guidance = load_drillhole_routing_guidance(workspace)
    text = _normalize_phrase(message)
    if not _has_validation_intent(text, guidance.intent_aliases):
        return None

    data_files = [path for path in workspace_files if _is_data_file(path)]
    if not data_files:
        return None

    folders = _mentioned_folders(message)
    explicit_files = _mentioned_files(message, data_files)
    mentioned_roles = _mentioned_roles(text, guidance.role_aliases)
    scoped_files = _scope_files(data_files, folders, explicit_files)

    inputs: dict[str, str] = {}
    for path in scoped_files:
        role = _infer_role(path, guidance.role_aliases)
        if not role:
            continue
        if explicit_files and path not in explicit_files and role not in mentioned_roles:
            continue
        if mentioned_roles and role not in mentioned_roles and role != "collar":
            continue
        inputs.setdefault(role, path)

    if not inputs and mentioned_roles:
        for path in data_files:
            role = _infer_role(path, guidance.role_aliases)
            if role in mentioned_roles:
                inputs.setdefault(role, path)

    for role in list(inputs):
        for required_role in guidance.companion_roles.get(role, ()):
            if required_role not in inputs:
                companion = _find_companion(required_role, inputs[role], data_files, guidance.role_aliases)
                if companion:
                    inputs[required_role] = companion

    if not inputs:
        return None

    missing = _missing_required_companions(inputs, guidance.companion_roles)
    if missing:
        return {
            "tool": "validate_drillhole",
            "inputs": inputs,
            "_validation_error": _format_missing_companion_message(missing),
        }

    return {"tool": "validate_drillhole", "inputs": inputs}


def _parse_markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        if current and line.startswith("-"):
            sections.setdefault(current, []).append(line[1:].strip())
    return sections


def _split_mapping(item: str) -> tuple[str, str]:
    for separator in ("=>", "=", ":"):
        if separator in item:
            left, right = item.split(separator, 1)
            return left.strip(), _normalize(right)
    return item.strip(), ""


def _split_companion(item: str) -> tuple[str, str]:
    lowered = item.lower()
    for separator in (" requires ", " membutuhkan ", " perlu ", " needs ", "=>", "=", ":"):
        if separator in lowered:
            left, right = re.split(re.escape(separator), item, maxsplit=1, flags=re.IGNORECASE)
            return _normalize(left), _normalize(right)
    return "", ""


def _has_validation_intent(text: str, aliases: tuple[str, ...]) -> bool:
    for alias in aliases:
        if _phrase_in_text(alias, text):
            return True
    return False


def _mentioned_roles(text: str, aliases: dict[str, str]) -> set[str]:
    roles: set[str] = set()
    for alias, role in aliases.items():
        if role == "collar":
            continue
        if _phrase_in_text(alias, text) or _phrase_in_text(role, text):
            roles.add(role)
    return roles


def _mentioned_folders(message: str) -> list[str]:
    folders: list[str] = []
    patterns = (
        r"\b(?:folder|directory|direktori)\s+([A-Za-z0-9_.\\/-]+)",
        r"\b(?:di|dalam|from)\s+folder\s+([A-Za-z0-9_.\\/-]+)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, message, flags=re.IGNORECASE):
            folder = _to_posix(match.group(1).strip(" .,'\""))
            if folder and folder not in folders:
                folders.append(folder.rstrip("/"))
    return folders


def _mentioned_files(message: str, data_files: list[str]) -> set[str]:
    mentioned: set[str] = set()
    lower_message = _to_posix(message).lower()
    for path in data_files:
        normalized_path = path.lower()
        basename = PurePosixPath(path).name.lower()
        if normalized_path in lower_message or basename in lower_message:
            mentioned.add(path)
    return mentioned


def _scope_files(data_files: list[str], folders: list[str], explicit_files: set[str]) -> list[str]:
    if explicit_files:
        scoped = set(explicit_files)
        parent_folders = {str(PurePosixPath(path).parent) for path in explicit_files}
        scoped.update(
            path
            for path in data_files
            if str(PurePosixPath(path).parent) in parent_folders
        )
        return sorted(scoped)
    if folders:
        return [
            path
            for path in data_files
            if any(path == folder or path.startswith(f"{folder.rstrip('/')}/") for folder in folders)
        ]
    return data_files


def _infer_role(path: str, aliases: dict[str, str]) -> str | None:
    stem = _normalize(PurePosixPath(path).stem)
    best: tuple[int, int, str] | None = None
    for alias, role in aliases.items():
        alias_norm = _normalize(alias)
        if not alias_norm:
            continue
        score = _alias_match_score(alias_norm, stem)
        if score <= 0:
            continue
        candidate = (score, len(alias_norm), role)
        if best is None or candidate > best:
            best = candidate
    return best[2] if best else None


def _alias_match_score(alias: str, stem: str) -> int:
    if stem == alias:
        return 4
    if stem.startswith(f"{alias}_") or stem.endswith(f"_{alias}"):
        return 3
    if f"_{alias}_" in f"_{stem}_":
        return 2
    if alias in stem:
        return 1
    return 0


def _find_companion(
    required_role: str,
    source_path: str,
    data_files: list[str],
    aliases: dict[str, str],
) -> str | None:
    source_parent = str(PurePosixPath(source_path).parent)
    same_folder: list[str] = []
    anywhere: list[str] = []
    for path in data_files:
        if _infer_role(path, aliases) != required_role:
            continue
        if str(PurePosixPath(path).parent) == source_parent:
            same_folder.append(path)
        anywhere.append(path)
    return sorted(same_folder or anywhere)[0] if same_folder or anywhere else None


def _missing_required_companions(
    inputs: dict[str, str],
    companion_roles: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    missing: dict[str, tuple[str, ...]] = {}
    for role in inputs:
        required = tuple(required_role for required_role in companion_roles.get(role, ()) if required_role not in inputs)
        if required:
            missing[role] = required
    return missing


def _format_missing_companion_message(missing: dict[str, tuple[str, ...]]) -> str:
    lines = [
        "Saya mengenali ini sebagai permintaan validasi drillhole, tetapi file pendamping wajib belum ditemukan.",
        "",
        "File pendamping yang dibutuhkan:",
    ]
    for role, required in missing.items():
        lines.append(f"- {role}: membutuhkan {', '.join(required)}")
    lines.append("")
    lines.append("Tambahkan alias file di drillhole_validation/default.md atau sebutkan path file secara eksplisit.")
    return "\n".join(lines)


def _is_data_file(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in DATA_EXTENSIONS


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _phrase_in_text(phrase: str, text: str) -> bool:
    phrase = _normalize_phrase(phrase).replace("_", " ")
    normalized_text = _normalize_phrase(text).replace("_", " ")
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized_text) is not None


def _to_posix(value: str) -> str:
    return value.replace("\\", "/")
