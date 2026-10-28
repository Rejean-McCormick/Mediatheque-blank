# Médiathèque Blank — modèle d'instance locale isolée (0.5.1)

**Ce dépôt n'est PAS le moteur Médiathèque.** Il sert de modèle propre, sans données,
pour créer une bibliothèque SQLite locale indépendante, connectée au moteur partagé
`mediatheque` **0.5.1**, corrigé pour les handoffs Skope/EncyK 0.14.

## Organisation attendue sur Windows

```text
C:\mycode\
  mediatheque\                ← moteur commun v0.5.1 (un seul exemplaire)
  mediatheque-blank\          ← modèle ou instance autonome (ce dossier)
    mediatheque.instance.toml
    01_DB\                    ← base SQLite privée après initialisation
    02_STORAGE\               ← preuves privées après import
    03_IMPORTS\               ← reçus privés après acceptation
```

Ce modèle ne contient **aucune base SQLite, fichier source ou autorisation de
publication**. Il ne crée **aucun inventaire global des Kristals**. Le dossier
`kristals/` est une zone de contenu d'instance vide, et non Kristal Manager.

## Avant de démarrer

1. Installer / mettre à jour une seule fois le moteur **Médiathèque 0.5.1** dans
   le dossier frère `mediatheque` (ne jamais le copier dans l'instance).
2. Garder `mediatheque-blank` comme modèle, ou en copier **le contenu** dans un
   dossier frère nouvellement nommé, par exemple `mediatheque-test`.
3. Si tu crées une nouvelle instance, modifier `id` et `name` dans
   `mediatheque.instance.toml` (l'`id` doit être unique parmi tes instances).
4. Utiliser **PowerShell 7+** et Python 3.11+; le moteur Streamlit nécessite ses
   dépendances habituelles.

## Commandes PowerShell

Depuis le dossier de cette instance :

```powershell
# Prévol en lecture seule : version du moteur, manifeste, frontières locales
python .\tools\instance_guard.py --instance-root .

# Initialiser une NOUVELLE base dans ce dossier seulement (écrit la base)
.\Initialize.ps1

# Démarrer l'interface de CETTE bibliothèque, uniquement sur 127.0.0.1
.\Start.ps1 -Port 8501
```

L'initialisation refuse une base déjà existante : elle ne remplace pas une
migration. Le lanceur refuse de démarrer si la base n'est pas initialisée ou
si le moteur voisin n'est pas la version qualifiée 0.5.1. Chaque commande
passe **explicitement** les chemins de la base et du stockage propres à
l'instance, même si le terminal avait des variables `KOA_*` d'une autre
bibliothèque. Aucune publication ni synchronisation distante automatique.

## Import Skope / EncyK (facultatif)

L'import utilise **le script du moteur partagé**, sans dupliquer son code.
Le contrôle est en lecture seule par défaut et la destination n'est jamais
déduite implicitement.

```powershell
# 1. Vérifier le handoff, sans écrire, après avoir sélectionné les VRAIS chemins
.\Import-EncyK.ps1 -Handoff "D:\EncyKlopedia\...\handoff-XXX.json" -EvidenceRoot "D:\EncyKlopedia"

# 2. Uniquement après revue : accepter vers CETTE instance locale
.\Import-EncyK.ps1 -Handoff "D:\EncyKlopedia\...\handoff-XXX.json" -EvidenceRoot "D:\EncyKlopedia" -Accept
```

`-Accept` nécessite une base déjà initialisée. Le moteur doit confirmer la
validité, les droits, les empreintes et l'idempotence. Le reçu local est rangé
sous `03_IMPORTS/encyk_receipts/`, hors Git. L'appel ne publie rien, ne crée
aucun KQ/KP/KA/KS et ne modifie pas les données d'EncyK. Les chemins indiqués
ci-dessus sont des exemples; **aucun dump D: n'est manipulé automatiquement**.

## Protection des instances

- `.gitignore` et `.smartignore` excluent par défaut les bases, sources, exports,
  sauvegardes, documents et informations privées des commits/snapshots de code.
- `GitSink.bat` refuse un push si des fichiers privés sont déjà suivis par Git
  (un `.gitignore` seul ne peut pas les désindexer).
- Conserver `.git` si ce dossier est un dépôt existant. Ne pas extraire ce ZIP
  par-dessus des bases ou des bibliothèques réelles sans examiner les conflits.
- Le modèle n'est pas une garantie d'absence de fuite; ne jamais publier une
  instance contenant de véritables données privées sans vérification humaine.
- Le modèle ne remplace ni C1/C2/C3 ni l'autorisation d'exposer des sources.

## Vérifications

```powershell
python -m unittest discover -s tests -v
```

Les tests inclus vérifient le prévol, l'isolement des chemins et la protection
Git. Les lanceurs PowerShell et l'interface Streamlit doivent encore être
vérifiés sur la machine Windows cible. Voir `docs/VALIDATION_051.md`.
