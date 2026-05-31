"""Read Native Instruments Kontakt favorites as deterministic LivePilot data."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


LOCAL_NI_DIR = Path.home() / "AppData" / "Local" / "Native Instruments"
DEFAULT_FAVORITES_DB = LOCAL_NI_DIR / "Shared" / "favorites.db3"
DEFAULT_KONTAKT8_DB = LOCAL_NI_DIR / "Kontakt 8" / "komplete.db3"
DEFAULT_KOMPLETE_KONTROL_DB = LOCAL_NI_DIR / "Komplete Kontrol" / "Browser Data" / "komplete.db3"

LOAD_CANDIDATE_EXTENSIONS = {"nki", "nkm", "nksn"}
KONTAKT_ROLE_RULES = {
    "piano": ("piano", "grand", "upright", "maverick", "grandeur", "giant", "una corda", "gentleman"),
    "keys": ("piano", "keys", "electric piano", "clavinet", "scarbee", "rhodes", "wurly"),
    "strings": ("bowed strings", "session strings", "string", "violin", "cello", "ensemble"),
    "pads": ("pad", "soundscape", "drone", "evolving"),
    "bass": ("bass", "upright", "synth bass"),
}


@dataclass(frozen=True)
class KontaktFavorite:
    source: str
    sound_id: int
    favorite_id: str
    name: str
    vendor: str | None
    product: str | None
    bank: str | None
    subbank: str | None
    content_alias: str | None
    content_path: str | None
    file_name: str | None
    file_ext: str | None
    categories: list[str]
    modes: list[str]
    roles: list[str]
    load_candidate: bool
    path_exists: bool | None

    def to_dict(self) -> dict:
        return asdict(self)


def list_kontakt_favorites(
    favorites_db: str | Path = DEFAULT_FAVORITES_DB,
    kontakt_db: str | Path = DEFAULT_KONTAKT8_DB,
    include_komplete_kontrol: bool = False,
    komplete_kontrol_db: str | Path = DEFAULT_KOMPLETE_KONTROL_DB,
) -> dict:
    """Return Native Instruments favorites that resolve to Kontakt sound records.

    Kontakt and Komplete Kontrol store the sound metadata in SQLite databases,
    while starred/favorited sounds live in a shared ``favorites.db3``. Matching
    ``favorites.id`` against ``k_sound_info.favorite_id`` gives us the actual
    instrument/snapshot names and paths without guessing from the plugin UI.
    """
    favorites_path = Path(favorites_db)
    kontakt_path = Path(kontakt_db)
    favorite_ids = _read_favorite_ids(favorites_path)

    sources: list[tuple[str, Path]] = [("kontakt8", kontakt_path)]
    if include_komplete_kontrol:
        sources.append(("komplete_kontrol", Path(komplete_kontrol_db)))

    favorites: list[KontaktFavorite] = []
    for source, db_path in sources:
        favorites.extend(_query_favorite_rows(source, db_path, favorite_ids))

    return {
        "success": True,
        "generatedAt": datetime.now().isoformat(),
        "sourceDatabases": {
            "favorites": str(favorites_path),
            "kontakt8": str(kontakt_path),
            "kompleteKontrol": str(Path(komplete_kontrol_db)) if include_komplete_kontrol else None,
        },
        "favoriteIdCount": len(favorite_ids),
        "favorites": [favorite.to_dict() for favorite in favorites],
        "roleGroups": _role_groups(favorites),
    }


def filter_favorites(
    favorites: Sequence[KontaktFavorite] | Sequence[dict],
    role: str | None = None,
    text: str | None = None,
) -> list[dict]:
    """Filter favorite records by musical role and/or text search."""
    role_norm = (role or "").strip().lower()
    text_norm = (text or "").strip().lower()
    matches: list[dict] = []

    for item in favorites:
        data = item.to_dict() if isinstance(item, KontaktFavorite) else dict(item)
        haystack = " ".join(
            str(value or "")
            for value in [
                data.get("name"),
                data.get("product"),
                data.get("bank"),
                data.get("subbank"),
                data.get("content_alias"),
                " ".join(data.get("categories") or []),
                " ".join(data.get("modes") or []),
            ]
        ).lower()
        if role_norm and role_norm not in {str(r).lower() for r in data.get("roles", [])}:
            continue
        if text_norm and text_norm not in haystack:
            continue
        matches.append(data)
    return matches


def export_kontakt_favorites(
    output_path: str | Path,
    favorites_db: str | Path = DEFAULT_FAVORITES_DB,
    kontakt_db: str | Path = DEFAULT_KONTAKT8_DB,
    include_komplete_kontrol: bool = False,
    komplete_kontrol_db: str | Path = DEFAULT_KOMPLETE_KONTROL_DB,
) -> dict:
    """Write the current Kontakt favorites snapshot to JSON and return it."""
    data = list_kontakt_favorites(
        favorites_db=favorites_db,
        kontakt_db=kontakt_db,
        include_komplete_kontrol=include_komplete_kontrol,
        komplete_kontrol_db=komplete_kontrol_db,
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return data


def _read_favorite_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    con = _connect_readonly(path)
    try:
        return [str(row[0]) for row in con.execute("select id from favorites order by id").fetchall()]
    finally:
        con.close()


def _query_favorite_rows(source: str, db_path: Path, favorite_ids: Sequence[str]) -> list[KontaktFavorite]:
    if not favorite_ids or not db_path.exists():
        return []

    placeholders = ",".join("?" for _ in favorite_ids)
    query = f"""
        select
            s.id,
            s.name,
            s.vendor,
            s.file_name,
            s.file_ext,
            s.favorite_id,
            bc.entry1 as product,
            bc.entry2 as bank,
            bc.entry3 as subbank,
            cp.alias as content_alias,
            cp.path as content_path,
            group_concat(distinct c.category || coalesce(' > ' || c.subcategory, '') || coalesce(' > ' || c.subsubcategory, '')) as categories,
            group_concat(distinct m.name) as modes
        from k_sound_info s
        left join k_bank_chain bc on bc.id = s.bank_chain_id
        left join k_content_path cp on cp.id = s.content_path_id
        left join k_sound_info_category sc on sc.sound_info_id = s.id
        left join k_category c on c.id = sc.category_id
        left join k_sound_info_mode sm on sm.sound_info_id = s.id
        left join k_mode m on m.id = sm.mode_id
        where s.favorite_id in ({placeholders})
        group by s.id
        order by coalesce(bc.entry1, ''), coalesce(bc.entry2, ''), s.name
    """

    con = _connect_readonly(db_path)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, list(favorite_ids)).fetchall()
    finally:
        con.close()

    return [_row_to_favorite(source, row) for row in rows]


def _row_to_favorite(source: str, row: sqlite3.Row) -> KontaktFavorite:
    file_name = _clean_text(row["file_name"], collapse_spaces=False)
    file_ext = _clean_text(row["file_ext"])
    categories = _split_aggregate(row["categories"])
    modes = _split_aggregate(row["modes"])
    role_inputs = [
        row["name"],
        row["product"],
        row["bank"],
        row["subbank"],
        row["content_alias"],
        " ".join(categories),
        " ".join(modes),
    ]
    roles = _infer_roles(role_inputs)
    path_exists = Path(file_name).exists() if file_name else None
    load_candidate = bool(file_ext and file_ext.lower() in LOAD_CANDIDATE_EXTENSIONS)
    return KontaktFavorite(
        source=source,
        sound_id=int(row["id"]),
        favorite_id=str(row["favorite_id"]),
        name=_clean_text(row["name"]) or "",
        vendor=_clean_text(row["vendor"]),
        product=_clean_text(row["product"]),
        bank=_clean_text(row["bank"]),
        subbank=_clean_text(row["subbank"]),
        content_alias=_clean_text(row["content_alias"]),
        content_path=_clean_text(row["content_path"]),
        file_name=file_name,
        file_ext=file_ext.lower() if file_ext else None,
        categories=categories,
        modes=modes,
        roles=roles,
        load_candidate=load_candidate,
        path_exists=path_exists,
    )


def _infer_roles(values: Iterable[str | None]) -> list[str]:
    haystack = " ".join(value or "" for value in values).lower()
    haystack = haystack.replace("fortepianocresc", "").replace("fortepiano", "")
    roles = [
        role
        for role, needles in KONTAKT_ROLE_RULES.items()
        if any(needle in haystack for needle in needles)
    ]
    return roles or ["instrument"]


def _role_groups(favorites: Sequence[KontaktFavorite]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for favorite in favorites:
        label = _favorite_label(favorite)
        for role in favorite.roles:
            groups.setdefault(role, []).append(label)
    return {role: sorted(set(labels)) for role, labels in sorted(groups.items())}


def _favorite_label(favorite: KontaktFavorite) -> str:
    product = f"{favorite.product}: " if favorite.product else ""
    return f"{product}{favorite.name}"


def _split_aggregate(value: str | None) -> list[str]:
    if not value:
        return []
    return sorted({part.strip() for part in str(value).split(",") if part and part.strip()})


def _clean_text(value: object, collapse_spaces: bool = True) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if collapse_spaces:
        while "  " in text:
            text = text.replace("  ", " ")
    return text or None


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
