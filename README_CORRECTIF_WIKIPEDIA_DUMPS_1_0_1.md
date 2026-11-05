# Correctif v1.0.1 — Import Wikimedia EN / Médiathèque Références

Ce correctif remplace **un seul fichier de code** dans l'instance privée `mediatheque-references` :

`tools\wiki\dump_import\import_dumps.py`

Il ajoute des tests `tests\test_multiline_fix.py`. Il ne modifie ni le moteur partagé `mediatheque`, ni la base centrale de l'instance, ni les archives téléchargées dans `D:\EncyKlopedia\10_sources\wikipedia\enwiki\2026-10`.

## Le bogue constaté

La version 1.0.0 n'analysait que les tuples SQL sur la **même ligne** que `INSERT INTO ... VALUES`. Le journal Windows indique qu'elle a reconnu des instructions mais traversé plus de 51 millions de lignes du dump `page` sans importer une seule ligne utilisable. La disposition exacte du dump devra être confirmée sur le poste Windows, mais le correctif prend maintenant en charge les instructions `INSERT` réparties sur plusieurs lignes, y compris les tuples partiellement coupés.

## Appliquer et relancer

1. **Fermer** la fenêtre `Wikipedia Dumps` si elle est encore ouverte.
2. Extraire ce ZIP dans `C:\mycode\EncyKlopedia\mediatheque-references`, **en remplaçant** `tools\wiki\dump_import\import_dumps.py`.
3. Double-cliquer sur `C:\mycode\EncyKlopedia\mediatheque-references\LANCER_WIKIPEDIA_DUMPS.cmd`.
4. Cliquer sur **IMPORTER TOUT**. Aucun nouveau téléchargement ni aucune réinitialisation ne sont nécessaires.

La nouvelle version reconnaît le point de reprise **v1 vide** (`committed_line` > 0, `rows_imported` = 0) et le réinitialise automatiquement, uniquement si la table du stade concerné est réellement vide. Le journal indiquera `rewind_empty_v1_checkpoint`, puis `stage_start`. Il n'est pas nécessaire de supprimer `wikipedia_en.sqlite`.

La reprise avec des données déjà insérées utilise maintenant des checkpoints à frontières de tuples complets, y compris lorsque l'instruction SQL s'étend sur plusieurs milliers de lignes.

En cas de nouveau message `error`, **arrêter** plutôt que relancer en boucle. Transmettre les 20 dernières lignes du journal. Les fichiers originaux restent en place.

## Validations

- 15 tests de régression Python sur des archives simulées, dont lecture SQL multilignes, tuples coupés, anciens checkpoints v1, migration du schéma SQLite, lecture complète, reprise et contrôle d'archives tronquées.
- **Aucune validation sur les archives complètes du disque D:** : elles ne sont pas fournies ici.
- Attention à l'espace libre : le précontrôle indiquait 201 GiB; l'index intégral des liens peut nécessiter davantage. L'outil continuera à surveiller l'espace disponible et pourra s'arrêter avant l'indexation complète.

Aucun fait Wikipédia n'est approuvé comme source ou assertion Kristal du seul fait de cet import.
