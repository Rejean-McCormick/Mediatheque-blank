"""Preflight en lecture seule du modèle d'instance Médiathèque kOA.

Utilise Python 3.11+ standard (tomllib, sqlite3). Ne crée AUCUN fichier.
Les instances privées et le moteur partagé demeurent séparés.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tomllib
from pathlib import Path

EXPECTED_VERSION = "0.5.1"
PRIVATE_AREAS = (
    "01_DB", "02_STORAGE", "03_IMPORTS", "04_EXPORTS", "07_BACKUPS",
    "08_LOGS", "documents", "kristals",
)


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _require_plain_inside(instance: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError(f"Chemin d'instance non autorisé : {relative!r}")
    current = instance
    for bit in rel.parts:
        current = current / bit
        if _is_link(current):
            raise ValueError(f"Lien symbolique / jonction non autorisé dans l'instance : {relative}")
    resolved = current.resolve()
    if not resolved.is_relative_to(instance):
        raise ValueError(f"Chemin sortant de l'instance : {relative}")
    return resolved


def _fields(data: dict, section: str, expected: dict[str, object]) -> None:
    item = data.get(section)
    if not isinstance(item, dict):
        raise ValueError(f"Section [{section}] absente")
    for name, value in expected.items():
        if item.get(name) != value:
            raise ValueError(f"[{section}].{name} attendu {value!r}")


def check(instance_root: str | Path, *, require_db: bool = False) -> dict:
    source_root = Path(instance_root).expanduser().absolute()
    if not source_root.is_dir() or _is_link(source_root):
        raise ValueError("Le dossier de l'instance doit exister et ne pas être un lien")
    instance = source_root.resolve()
    manifest = instance / "mediatheque.instance.toml"
    if not manifest.is_file() or _is_link(manifest):
        raise ValueError("Manifeste d'instance introuvable ou lié")
    with manifest.open("rb") as fh:
        data = tomllib.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Manifeste d'instance invalide")
    identity = data.get("mediatheque", {})
    if not isinstance(identity, dict) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", str(identity.get("id", ""))):
        raise ValueError("ID d'instance invalide")
    if not isinstance(identity.get("name"), str) or not identity["name"].strip():
        raise ValueError("Nom d'instance absent")
    _fields(data, "mediatheque", {"backend": "sqlite", "visibility": "private"})
    _fields(data, "content", {"root": ".", "database": "01_DB/koa_mediatheque.sqlite", "storage": "02_STORAGE"})
    engine_value = identity.get("engine")
    if not isinstance(engine_value, str) or not engine_value.strip():
        raise ValueError("Chemin moteur manquant")
    engine = (instance / engine_value).resolve()
    # L'instance générique consomme seulement le moteur commun voisin, jamais un
    # moteur embarqué dans les données ou une copie arbitraire sur un autre disque.
    if engine != (instance.parent / "mediatheque").resolve():
        raise ValueError("Le moteur commun doit être le dossier frère ../mediatheque")
    for path in ("pyproject.toml", "Start-KoaGui.ps1", "05_TOOLS/Initialize-KoaMediathequeDb.ps1",
                 "05_TOOLS/ImportEncyKHandoff.py", "schemas/sqlite/007_source_authority.sql"):
        if not (engine / path).is_file():
            raise ValueError(f"Moteur commun incomplet : {path}")
    with (engine / "pyproject.toml").open("rb") as fh:
        version = tomllib.load(fh).get("project", {}).get("version")
    if version != EXPECTED_VERSION:
        raise ValueError(f"Moteur non qualifié pour Blank : {version!r}; attendu {EXPECTED_VERSION}")
    for area in PRIVATE_AREAS:
        _require_plain_inside(instance, area)
    db = _require_plain_inside(instance, "01_DB/koa_mediatheque.sqlite")
    storage = _require_plain_inside(instance, "02_STORAGE")
    if not storage.is_dir():
        raise ValueError("02_STORAGE absent de cette instance")
    if require_db:
        if not db.is_file():
            raise ValueError("La base SQLite n'existe pas. Initialiser l'instance avant import.")
        # Connexion strictement en lecture seule : ne crée jamais une base vide.
        connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        try:
            names = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"source_registry", "source_snapshots", "source_representations"}.issubset(names):
                raise ValueError("Base sans schéma d'autorité des sources du moteur 0.5.1")
        finally:
            connection.close()
    return {
        "status": "ready" if db.is_file() else "template_not_initialized",
        "instance_id": identity["id"],
        "instance_name": identity["name"],
        "visibility": "private",
        "engine_version": version,
        "instance_root": str(instance),
        "engine_root": str(engine),
        "database": str(db),
        "storage": str(storage),
        "initialized": db.is_file(),
        "no_writes": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Médiathèque Blank : preflight strict, sans écriture")
    parser.add_argument("--instance-root", required=True)
    parser.add_argument("--require-db", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = check(args.instance_root, require_db=args.require_db)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, tomllib.TOMLDecodeError, sqlite3.Error) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc), "no_writes": True}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
