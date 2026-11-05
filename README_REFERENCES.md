# Médiathèque Références — UNESCO/Wikipédia (English-first)

**Ce paquet cible uniquement l’instance privée créée à partir de `mediatheque-blank`.**
Il ne modifie **aucun fichier de** `C:\mycode\mediatheque` (moteur 0.5.1).

## Installation

1. Copier le dossier `C:\mycode\mediatheque-blank` vers `C:\mycode\mediatheque-references` (laisser le modèle intact), ou utiliser ta copie vierge déjà renommée.
2. Extraire ce ZIP à la **racine** de `C:\mycode\mediatheque-references` ; accepter le remplacement de **`mediatheque.instance.toml` seulement**. Ne pas extraire sur le moteur.
3. Si la base de l'instance est **neuve et absente**, exécuter `pwsh -NoProfile -File .\Initialize.ps1`. **Ne pas** réinitialiser une base existante.
4. Lancer `LANCER_WIKIPEDIA_REFERENCES.cmd`. Fournir un contact Wikimedia réel lors de la collecte.

### Workflow

- **Collecter** : six articles Wikipedia EN sélectionnés, captures API et manifeste dans `03_IMPORTS/wikipedia/` (aucune écriture DB).
- **Vérifier** : empreintes, provenance, révision, inventaire, sans écriture.
- **Importer** : confirmation explicite, sauvegarde sous `07_BACKUPS/`, tables `wikipedia_discovered_*` ajoutées **à la seule base SQLite de l’instance** ; utilisation des `source_registry` / `source_bindings` **déjà présents** dans cette base après son initialisation. Aucune extension du moteur partagé.
- **Exporter** : CSV sous `04_EXPORTS/wikipedia/` pour revue humaine.

Liens = découvertes **non vérifiées**, pas preuves validées. Pas de créations de KA/KS, pas de téléchargement de sites tiers, pas de publication, pas d'expansion automatique sur Wikipédia entier.

La licence Wikipédia peut imposer attribution et CC BY-SA pour la réutilisation de textes. Capturer la page et conserver le lien permanent de révision; vérifier les sources originales avant réutilisation factuelle.

## Chemins et tests

```text
C:\mycode\
  mediatheque\                # moteur partagé — inchangé
  mediatheque-blank\          # modèle intact
  mediatheque-references\     # instance privée
    mediatheque.instance.toml  # id = encyklopedia-references
    01_DB\koa_mediatheque.sqlite
    03_IMPORTS\wikipedia\
    04_EXPORTS\wikipedia\
    07_BACKUPS\
    tools\wiki\
    LANCER_WIKIPEDIA_REFERENCES.cmd
```

Depuis l'instance, `python -m unittest discover -s tests -p 'test_wikipedia_instance.py' -v`.

**Si tu as installé l'ancien overlay dans le moteur**, celui-ci ajoutait :
`05_TOOLS/WikipediaReferenceInventory.py`, `05_TOOLS/WikipediaReferences_UI.pyw`,
`05_TOOLS/Wikipedia_Educational_Policy_EN.txt`, `05_TOOLS/LANCER_WIKIPEDIA_REFERENCES.cmd`,
`schemas/sqlite/008_wikipedia_reference_inventory.sql`,
`tests/python/test_wikipedia_reference_inventory.py`,
`docs/WIKIPEDIA_EN_REFERENCE_INVENTORY.md`, et
`README_WIKIPEDIA_REFERENCES_OVERLAY.md` à la racine.
Ces **nouveaux fichiers précis** peuvent être retirés après sauvegarde si tu ne les as pas modifiés. Ne supprimer aucun autre fichier du moteur ni aucune base `01_DB`.
