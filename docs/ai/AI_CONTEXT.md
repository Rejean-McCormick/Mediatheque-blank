<!-- kOA Doc Server · Docs IA · lot 02 · rédaction dérivée d’une capture, à valider par le propriétaire -->
# Navigation IA — mediatheque-blank

**Rôle observé :** Gabarit isolé d'instance Médiathèque 0.5.1 sans données par défaut.

**Autorité :** Le moteur frère reste partagé; l'instance conserve ses propres bases privées et reçus.

**Provenance :** `SmartDump_20261120_221507.zip` → `mediatheque-blank_Code_snapshot.zip` (20 novembre 2026). Cette capture ne prouve ni la présence actuelle du dossier Windows, ni un déploiement, ni une qualification.

## Objet et état de cette fiche

La description ci-dessous est rattachée au `README.md` du snapshot; vérifier le code actif sur le poste. Cette fiche est un **guide de navigation**, non une spécification normative ni une validation de maturité.

## Processus conseillé

1. **Identifier la source et le profil.** Vérifier l'emplacement du moteur commun, configurer l'instance, initialiser sur données fictives et contrôler la séparation.
2. **Contrôler l’autorité.** Le moteur frère reste partagé; l'instance conserve ses propres bases privées et reçus.
3. **Préparer un environnement de test.** Utiliser les fichiers réels de la révision étudiée et des données fictives ou autorisées.
4. **Vérifier sans promouvoir.** Documenter commandes, périmètre, résultat, chemins et empreintes; ne jamais transformer une observation locale en preuve historique validée.
5. **Revue propriétaire.** Une publication, activation, import ou effet externe nécessite l’accord du propriétaire et les gates correspondants.

## Garde-fous particuliers

- Ne pas livrer de bases 01_DB, sources 02_STORAGE ou reçus privés dans la documentation IA.
- N’inclure aucun secret, donnée personnelle, sauvegarde privée ou sortie de diagnostic non autorisée dans les exports Doc Server.
- Préserver l’intégrité des sources et des états historiques; éviter toute réécriture automatique des références.

## Sources d’orientation vérifiables dans le snapshot

1. [`README.md`](../../README.md) — source propriétaire présente dans le snapshot.
2. [`docs/VALIDATION_051.md`](../../docs/VALIDATION_051.md) — source propriétaire présente dans le snapshot.
3. [`docs/BRANCH01_INSTANCE_HANDOFF.md`](../../docs/BRANCH01_INSTANCE_HANDOFF.md) — source propriétaire présente dans le snapshot.

## Compatibilité Framework

S’il y a une dépendance Kristal, lire la révision du Framework et le profil **effectivement adoptés** par ce dépôt. Les nouvelles conventions v11 (identités sémantiques, dictionnaires séparés, provenance) servent de référence lorsque compatibles; **ne pas bloquer** la navigation IA ni imposer la migration de données historiques pour cette seule raison.
