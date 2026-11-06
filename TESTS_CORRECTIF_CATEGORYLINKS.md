# Validation v1.0.2

- 8 tests d'import complet/portée/échappements/reprise/CRC issus de v1.
- 7 tests de lecture SQL multi-ligne, points de reprise v1, et retour des tuples de v1.0.1.
- 7 tests dédiés aux schémas `cl_target_id` (modernes) et `cl_to` (anciens), vue des catégories, conservation des index existants, reprise après `KeyError`, reprise sans doublons, validation stricte des colonnes, migration additive de la base.

Total : **22 tests OK**.

La base réelle de l'utilisateur et les archives réelles ne sont jamais modifiées par ces tests.
