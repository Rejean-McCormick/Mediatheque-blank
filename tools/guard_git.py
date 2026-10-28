"""Empêche GitSink de committer des données d'instance suivies par Git.

Ce contrôle inspecte l'index Git, y compris les chemins deja suivis (gitignore
ne retire PAS ces fichiers de l'index). Ne modifie rien.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PRIVATE_ROOTS = frozenset({
    '01_DB', '02_STORAGE', '03_IMPORTS', '04_EXPORTS', '07_BACKUPS',
    '08_LOGS', 'documents', 'kristals',
})
PRIVATE_EXT = ('.sqlite', '.db', '.db3', '.key', '.pem', '.p12', '.pfx', '.secret', '.token')


def is_private_gitpath(path: str) -> bool:
    parts = path.replace('\\', '/').split('/')
    if not parts or parts[0] in ('', '.', '..'):
        return True
    if parts[0] in PRIVATE_ROOTS and parts[-1] != '.gitkeep':
        return True
    name = parts[-1].lower()
    return name.startswith('.env') or name.endswith(PRIVATE_EXT) or name.endswith(('.sqlite-wal', '.sqlite-shm'))


def check(root: Path) -> list[str]:
    result = subprocess.run(
        ['git', 'ls-files', '--cached', '-z'], cwd=root,
        capture_output=True, check=True,
    )
    return sorted(p.decode('utf-8', 'replace') for p in result.stdout.split(b'\0')
                  if p and is_private_gitpath(p.decode('utf-8', 'replace')))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path.cwd())
    a = p.parse_args()
    try:
        files = check(a.root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'[GitSink] Vérification de confidentialité indisponible : {exc}', file=sys.stderr)
        return 2
    if files:
        print('[GitSink] REFUS : fichiers d’instance suivis par Git :', file=sys.stderr)
        for name in files[:30]:
            print(f' - {name}', file=sys.stderr)
        print('Retirer ces fichiers de l’index Git sans les supprimer du disque avant tout push.', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
