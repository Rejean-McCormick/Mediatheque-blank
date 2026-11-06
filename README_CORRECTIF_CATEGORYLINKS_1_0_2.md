# Correctif v1.0.2 — Médiathèque Références / Wikimedia EN

## Diagnostic du 6 novembre 2026

Après cinq stades SQL terminés, l'import v1.0.1 a échoué au début de `categorylinks` sur :

```
KeyError: 'cl_to'
```

Dans MediaWiki récent (>= 1.45), la colonne `cl_to` a disparu de `categorylinks`; elle est remplacée par `cl_target_id`, qui correspond à `linktarget.lt_id`.

Références : https://www.mediawiki.org/wiki/Manual:Categorylinks_table et annonce Wikimedia du 16 février 2026 concernant le retrait de `cl_to`.

## Ce que modifie ce paquet

**Un seul fichier de programme à remplacer :**

`tools\wiki\dump_import\import_dumps.py`

Le script conserve les mêmes chemins et commandes, et gère les deux schémas de catégories :
- Schéma moderne `cl_target_id` : importation dans une **nouvelle table** `wiki_categorylink_ids` (`source_page_id`, `target_id`, `type`) ;
- Schéma ancien `cl_to` : conservation dans la table historique `wiki_categorylinks` ;
- Vue commune de lecture `wiki_categorylinks_resolved` : le nom de catégorie est résolu par jointure vers `wiki_linktargets` (namespace 14), sans lookup coûteux pour chaque lien pendant l'import.

Le programme ne supprime ni ne réécrit les cinq stades terminés : `page`, `page_props`, `linktarget`, `externallinks`, `pagelinks`. Les stades déjà terminés sont détectés et ignorés automatiquement lors de la relance. Il conserve les fichiers sources compressés et n'écrit pas dans le moteur commun ni la base privée principale sur C:.

## Installation Windows

1. Fermer la fenêtre **Wikimedia Dumps** après l'erreur, si elle est encore ouverte.
2. **Ne supprimer ni la base SQLite ni les archives téléchargées.**
3. Extraire le contenu de ce ZIP à la racine de :

   `C:\mycode\EncyKlopedia\mediatheque-references`

   Autoriser le remplacement de `tools\wiki\dump_import\import_dumps.py`.
4. Ouvrir `LANCER_WIKIPEDIA_DUMPS.cmd` et cliquer sur **IMPORTER TOUT**.

La GUI appelle le même script, version **1.0.2**. Pas de nouveau téléchargement ni de redémarrage depuis le début.

## Résultat attendu du journal

```
"event":"already_complete", "stage":"page"          (et pour 4 autres étapes)
"event":"stage_start", "stage":"categorylinks"
"event":"categorylinks_schema_detected", "target_field":"cl_target_id"
"event":"progress", "stage":"categorylinks", "rows":...  (augmente)
"event":"stage_complete", "stage":"categorylinks"
"event":"creating_index", "stage":"categorylinks"
"event":"xml_registered"
"event":"finish", "status":"COMPLETE_SQL_INDEX"
```

**Attention :** les index de catégories peuvent être longs à créer. Surveillez l'espace libre de D:. Le code interrompt l'import quand l'espace libre passe sous son seuil de sécurité de 10 GiB. Si une nouvelle erreur s'affiche, ne pas lancer plusieurs imports simultanément : communiquer les 20 dernières lignes du journal.

Pour vérifier manuellement le statut une fois l'import terminé :

```powershell
python "C:\mycode\EncyKlopedia\mediatheque-references\tools\wiki\dump_import\import_dumps.py" status
```

Pour interroger la vue de catégories sans modifier les données, utiliser SQLite via une connexion en lecture seule et la vue `wiki_categorylinks_resolved`. La table `wiki_categorylinks` demeure réservée au format ancien; sur le format moderne, les données sont dans `wiki_categorylink_ids`.

## Tests et limites

- **22 tests automatisés réussis** sur des micro-dumps fictifs, dont 7 spécifiques à la correction `cl_target_id`, compatibilité ancienne base, reprise et absence de doublons.
- **Les véritables fichiers de 42 Go sur D: ne sont pas accessibles ici** : le journal de la prochaine exécution confirmera le fonctionnement sur ces archives.
- L'import est un inventaire de références. Aucun lien n'est approuvé automatiquement comme assertion encyclopédique Kristal.
