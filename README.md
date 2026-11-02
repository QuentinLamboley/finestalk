# Finestalk

**Finestalk** est une application Streamlit de **conservation, organisation et vérification de preuves de cyberharcèlement**. Elle permet de documenter des faits avec des messages exacts, des captures, des dates, des URLs et des annotations, puis d'exporter un dossier autonome.

L'application ne cherche pas à désanonymiser des personnes et ne propose **ni liste de suspects ni probabilités d'identification**. Le nom affiché par un compte est traité comme une déclaration non vérifiée. Le score sur 100 indique uniquement la **complétude documentaire** du dossier, et non la fiabilité d'une identité, la gravité ou une culpabilité.

## Étape 1 — Fiche de profil Instagram

L'écran **Inspection Instagram** constitue un journal chronologique d'informations **explicitement affichées** sur un profil : pseudonyme, URL canonique, nom affiché, date de consultation et captures fournies par l'utilisateur. Chaque observation crée une pièce associée au dossier, conservée avec son empreinte SHA-256 et son journal d'audit. L'historique permet de repérer les changements de nom affiché au fil des observations. Les captures peuvent figurer dans le ZIP/PDF du dossier.

Ce module fonctionne **sans connexion Instagram, sans scrapping ni requête automatique vers le compte** : il prend les observations et pièces apportées par l'utilisateur. Il ne calcule aucune identité supposée, ne recoupe pas les pseudonymes avec des personnes et ne recherche pas de coordonnées privées. Le nom affiché par un profil ne permet pas à lui seul de connaître l'identité civile du titulaire.

Pour utiliser cette étape : créez un dossier, ouvrez **Inspection Instagram**, saisissez le pseudonyme ou l'URL du profil, indiquez le nom *exactement tel qu'affiché* s'il existe, puis joignez une capture non retouchée. Les différentes versions sont conservées dans l'historique.

## Fonctionnalités

- Tableau de bord des faits, des profils observés et de la complétude.
- Gestion de plusieurs dossiers et statuts de suivi.
- Enregistrement de pseudonymes, URLs et noms publics tels qu'affichés, sans corrélation automatique entre plateformes.
- Archivage de messages et de fichiers (images, documents, vidéos, archives) sans modification du contenu original.
- Analyse lexicale explicable de quelques catégories : insultes, menaces explicites, intimidation, chantage, divulgation annoncée. Le résultat exige une relecture humaine.
- Chronologie filtrable, annotations ajoutées sans écraser l'original, journal des opérations.
- Import contrôlé de fichiers CSV UTF-8, 500 lignes maximum par import.
- Calcul d'empreintes SHA-256, contrôle d'intégrité et journal d'audit chaîné.
- Exports PDF, JSON et ZIP incluant les pièces et un manifeste SHA-256.

## Installation locale (Windows PowerShell)

Nécessite Python 3.11 ou supérieur.

```powershell
git clone https://github.com/QuentinLamboley/finestalk.git
cd finestalk
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:FINESTALK_ACCESS_PASSWORD = "remplacez-par-une-phrase-secrete-longue-et-unique"
streamlit run app.py
```

Le serveur se lie par défaut à `127.0.0.1`. Ouvrir l'URL locale fournie par Streamlit.

### Installation Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FINESTALK_ACCESS_PASSWORD='remplacez-par-une-phrase-secrete-longue-et-unique'
streamlit run app.py
```

### Configuration

| Variable | Valeur | Description |
|---|---|---|
| `FINESTALK_ACCESS_PASSWORD` | Obligatoire | Mot de passe d'accès à l'instance ; peut aussi être placé dans les secrets Streamlit |
| `FINESTALK_DATA_DIR` | `.finestalk_data` | Dossier local contenant la base SQLite et les pièces |

Le mot de passe n'est pas un chiffrement des fichiers. Protégez le disque par le chiffrement de votre système et faites des sauvegardes chiffrées. Le répertoire de preuves est ignoré par Git.

**Déploiement :** l'architecture est **mono-espace privé**, pas multiutilisateur. Ne publiez pas cette instance sur Streamlit Community Cloud ou un domaine public en pensant que le mot de passe partagé fournit une séparation entre usagers. Pour un service public, prévoir avant déploiement une authentification individuelle, une isolation des données par utilisateur, un stockage durable chiffré, une politique de rétention et une revue de sécurité. Sur un hébergement éphémère, les dossiers peuvent disparaître au redémarrage.

## Format d'import CSV

La colonne `texte` est obligatoire. Autres colonnes possibles : `date`, `source`, `auteur`, `url`, `contexte`, `pseudo`. Le pseudo n'est associé à un profil que s'il figure déjà exactement dans le dossier.

```csv
texte,date,source,auteur,url,contexte,pseudo
"Message exact à conserver",2026-10-31T20:15:00+01:00,Instagram - message privé,compte_exemple,https://www.instagram.com/,Message reçu,compte_exemple
```

Les dates importées sont conservées telles quelles ; contrôlez les fuseaux horaires avant d'importer. Les importations ne sont pas réversibles dans l'interface pour préserver la traçabilité.

## Intégrité et limites

Les pièces sont copiées dans un répertoire local avec un nom technique distinct, et leur empreinte SHA-256 est enregistrée. Le vérificateur recalcule ces empreintes. Un journal SQL chaîné enregistre les actions ; une personne ayant le contrôle complet du stockage pourrait néanmoins réécrire la base et la chaîne. Sauvegardez régulièrement le ZIP et son manifeste auprès d'un tiers de confiance si une traçabilité forte est requise.

Une empreinte de fichier **ne démontre pas qu'une capture était authentique avant son import**. Il est recommandé de conserver aussi les fichiers et les messages à leur source, les dates et les URLs. Ne recadrez pas les captures originales ; ajoutez des annotations séparées.

Les règles lexicales sont volontairement simples et transparentes. Elles ne reconnaissent ni toutes les insultes, ni le contexte, ni les images, ni les messages codés. Elles peuvent produire des faux positifs. Aucun score juridique, psychologique ou d'identité n'est généré.

## Tests

```bash
python -m pip install pytest
python -m pytest -q
```

## En cas de harcèlement

Conserver les messages et les captures, signaler les faits à la plateforme et, selon la situation, déposer plainte contre X. En France : **3018** pour le cyberharcèlement ; **17/112** en cas de danger immédiat.

## Licence

CC0 1.0 (voir `LICENSE`).
