# Blank 0.5.1 — alignement sur le moteur Médiathèque 0.5.1

## Périmètre

- Moteur commun réutilisé tel quel, dans un dossier frère `../mediatheque`.
- Template sans aucun octet de base, preuve, source ou document utilisateur.
- Instance locale privée SQLite avec configuration explicite et contrôle en lecture seule.
- Import EncyK `encyk.source-evidence-handoff/2.0.0` **par le moteur**, jamais par un récepteur copié dans Blank.

## Corrections

1. Avant : `Initialize.ps1` et `Start.ps1` utilisaient directement le moteur voisin, sans
   inspection de la version ni protection de toutes les variables `KOA_*` héritées.
   Après : contrôle `instance_guard.py` et chemins explicites par instance.
2. Avant : aucun `.gitignore`; `GitSink.bat` lançait `git add --all` sans borne.
   Après : données ignorées et contrôle de l'index avant **et après** l'ajout.
3. Avant : aucun chemin ergonomique d'import Skope/EncyK depuis le modèle.
   Après : `Import-EncyK.ps1`, PLAN par défaut, acceptation explicite et reçu local privé.
4. `Initialize.ps1` ne remplace plus une base existante; `Start.ps1` lie l'UI à
   `127.0.0.1` et exige un schéma source SQLite existant.

## Ce qui reste hors qualification

- Pas de test réel PowerShell 7/Windows ni d'installation Streamlit dans la CI Linux.
- Pas d'ingestion des véritables preuves situées sur `D:`.
- Pas d'audit exhaustif de stockage, authentification ou publication.
- Aucun autre moteur que `koa-mediatheque` `0.5.1` n'est autorisé par ce template.
- Le moteur 0.5.1 conserve sa propre logique d'importation et ses limites.

## Critère de compatibilité

Une instance Blank ne doit pas se lancer si le moteur voisin est absent ou si
son `pyproject.toml` déclare une autre version que `0.5.1`. Un import accepté
utilise exclusivement `--instance-root` de l'instance explicitement lancée.
