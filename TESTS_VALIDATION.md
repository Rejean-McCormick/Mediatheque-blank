# Validation de l'overlay Wikimedia EN — instance Médiathèque Références

- Suite : `python -m unittest discover -s tests -v`
- 8 tests automatisés sur des fichiers gzip SQL **synthétiques**, représentatifs des schémas MediaWiki récents.
- Vérifiés : parsing SQL/échappements, correspondance QID, import des six tables, liens externes, provenance, index de recherche, arrêt/reprise sans doublons, protection contre une archive changée, rejet d'un gzip tronqué, conservation de l'archive XML et création du rapport ZIP.
- **Non vérifié** : test sur les dumps EN complets de dizaines de Go ; Windows réel ; débit soutenu et espace nécessaire ; connexion au modèle GUI officiel de Médiathèque (le moteur est volontairement non modifié).
- Le champ `sha256` des tables SQL est calculé pendant la décompression ; il est local et n'authentifie pas une origine Wikimedia sans comparaison aux sommes officielles.
- Provenance : les dumps SQL restent des observations du site Wikimedia ; aucun lien externe n'est promu comme source vérifiée.
