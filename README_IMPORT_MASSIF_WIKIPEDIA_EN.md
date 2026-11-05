# Import massif hors ligne — Wikipédia EN → Médiathèque Références

**Paquet additif pour l'instance privée uniquement.** Ne l'extrais pas dans `mediatheque` (moteur partagé) ni dans `EncyKlopedia` (serveur web).

## Installation

Extraire le ZIP à la racine :

`C:\mycode\EncyKlopedia\mediatheque-references`

Les fichiers ajoutés sont : `LANCER_WIKIPEDIA_DUMPS.cmd`, `tools/wiki/dump_import/{import_dumps.py,Wikipedia_Dumps_UI.pyw}`, ce README et des tests. Aucun fichier existant n'est remplacé, aucune base n'est réinitialisée.

## Démarrage (sans administrateur)

Double-cliquer sur `LANCER_WIKIPEDIA_DUMPS.cmd`, puis :

1. **Vérifier les 7 fichiers** ; les archives suivantes doivent exister dans `D:\EncyKlopedia\10_sources\wikipedia\enwiki\2026-10` : `page`, `page_props`, `linktarget`, `externallinks`, `pagelinks`, `categorylinks` (SQL `.gz`) et `pages-articles-multistream.xml.bz2` (XML).
2. **IMPORTER TOUT** : import dans une base séparée située sur `D:`. Confirmer l'import ; il est long, parfois très long.
3. En cas de pause ou d'interruption : **IMPORTER TOUT** à nouveau, pour reprendre au dernier groupe SQL engagé. L'archive déjà terminée n'est pas réimportée.

L'interface affiche le progrès, vérifie l'espace libre régulièrement et conserve les originaux. Les sous-étapes et les empreintes SHA-256 sont écrites dans le registre d'import. Un rapport ZIP léger est produit dans `Téléchargements` à la fin de l'import, sans copier la base gigantesque.

## Emplacements de sortie

- **Base d'index massive** : `D:\EncyKlopedia\80_search_indexes\mediatheque-references\wikipedia_en.sqlite` (créée automatiquement ; fichiers auxiliaires SQLite sur D:).
- **Rapport d'état** : `C:\mycode\EncyKlopedia\mediatheque-references\04_EXPORTS\wikipedia\dump_index_status.json`.
- **Catalogue XML et empreinte SHA-256** : `C:\mycode\EncyKlopedia\mediatheque-references\03_IMPORTS\wikipedia\dumps\archive_catalog.json`.
- **Support ZIP** : `%USERPROFILE%\Downloads\Wikipedia_EN_Import_*.zip`.
- **Base centrale préexistante** : `01_DB\koa_mediatheque.sqlite` reste intacte. On ne crée pas une seconde instance de moteur ; l'index massif est un entrepôt local distinct pour éviter de remplir `C:`.

## Ce qui est vraiment automatisé

- Import SQL par flux gzip, sans extraction préalable des fichiers géants.
- `page_id`, titre, namespace, dernière révision, liens officiels `wikibase_item → QID`.
- Répertoire `linktarget`, arcs `pagelinks`, catégories et occurrences de liens externes.
- Reconstruction des URLs externes à partir de `el_to_domain_index` et `el_to_path` (schéma MediaWiki moderne).
- Indexation des URL, permettant `SELECT DISTINCT target_url` sans perdre quelles pages les ont citées.
- Reprise via `ingest_state` aux frontières transactionnelles des instructions `INSERT`, contrôle de changement des fichiers (taille + mtime) et vérification CRC gzip jusqu'à la fin de chaque archive ; SHA-256 calculé en même temps.
- Enregistrement et empreinte SHA-256 du XML compressé **sans** l'extraire ni dupliquer les textes ; l'archive est conservée pour la future extraction des articles pertinents.
- **Pas de réseau, pas de téléchargement des domaines externes, pas de connexion Wikimedia, pas de publication et pas de modification du moteur**.

## Ce qui n'est PAS encore fait

- Le XML n'est pas transformé en millions d'articles canoniques ; nous indexons sa présence et son empreinte, tandis que la table `page` possède les IDs de révisions courantes. L'extraction du corps des articles viendra à la demande avec un index multistream approprié.
- Un lien listé dans `externallinks` n'est **pas automatiquement une référence bibliographique**. Les tables SQL ne contiennent pas le contexte des citations. Aucun URL n'est marqué « vérifié ».
- Aucune source n'est promue automatiquement dans `source_registry`, et aucun KS/KA ou article Kristal n'est approuvé.
- Les SHA-256 locaux permettent de suivre la provenance et la modification des copies ; **ils ne remplacent pas** une comparaison aux empreintes officielles publiées par Wikimedia.
- Les fichiers SQL `latest` et le XML peuvent provenir de générations différentes. La provenance de chaque archive est conservée individuellement, sans supposer qu'ils ont tous le même instantané.

## Taille et prudence

L'index peut occuper **des centaines de Go** (plus les temporaires, les index secondaires et le journal SQLite). Prévoir une grosse marge d'espace libre sur `D:`. Si l'espace libre passe sous 10 GiB, l'import s'interrompt à un point de reprise : **ne pas supprimer le gros fichier SQLite en cours** pour essayer de récupérer de l'espace. Si tu veux stopper, utilise le bouton Arrêter, puis relance plus tard.

Les dumps contiennent énormément d'arcs (potentiellement des centaines de millions) : la vitesse dépend du disque. Ce système a été validé sur des archives miniatures reproduisant les schémas MediaWiki, **pas sur les 7 archives complètes de ta machine**, auxquelles je n'ai pas accès.

## Exemples pour PowerShell 7

Pour afficher l'état :

```powershell
python "C:\mycode\EncyKlopedia\mediatheque-references\tools\wiki\dump_import\import_dumps.py" status
```

Pour vérifier un QID importé :

```powershell
python "C:\mycode\EncyKlopedia\mediatheque-references\tools\wiki\dump_import\import_dumps.py" lookup --qid Q69370
```

Pour exécuter l'import **sans interface graphique** :

```powershell
python -u "C:\mycode\EncyKlopedia\mediatheque-references\tools\wiki\dump_import\import_dumps.py" run
```

Le programme fonctionne avec Python 3.11+ et les bibliothèques standard. Il n'a pas besoin de droits administrateur.

## Sécurité et propriété des données

Les tables de travail sont privées ; les liens sont des observations **non vérifiées**. Pour réutiliser la rédaction d'une page Wikipédia, documenter titre, URL, numéro de révision, licence et attribution. Vérifier séparément les documents externes avant de les présenter comme preuves.
