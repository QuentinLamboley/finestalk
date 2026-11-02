# Finestalk

Application Streamlit de **recherche de présences publiques vérifiables**, avec une seule barre de recherche et une présentation sombre, minimaliste.

- Site : https://finestalk.streamlit.app/
- Dépôt : https://github.com/QuentinLamboley/finestalk
- Déploiement : branche `main`, fichier `app.py`

## Barre de recherche intelligente

Le même champ reconnaît automatiquement :

| Exemple | Mode | Traitement |
|---|---|---|
| `@octocat` | Pseudonyme | Recherche de comptes portant exactement ce pseudo via des API publiques |
| `https://instagram.com/octocat/` | Profil Instagram | Extraction du pseudonyme, puis mêmes vérifications publiques |
| `Marie Dupont` | Nom complet | Liens vers des recherches web exactes, à consulter et apprécier manuellement |
| `marie@example.org` | E-mail | Reconnaissance **locale du format uniquement** |
| `06 12 34 56 78` | Téléphone | Reconnaissance **locale du format uniquement** |

Les saisies e-mail et téléphone ne sont pas envoyées à des services externes, associées à des identités, conservées ou affichées dans des résultats publics. Aucun numéro n'est recherché dans des annuaires inversés ; aucun compte n'est découvert à partir d'une adresse privée.

La recherche par nom mène à des résultats publics des moteurs de recherche, sans attribution automatique : de nombreuses personnes peuvent porter le même nom.

## Mode pseudonyme : les sources interrogées

- **GitHub** : `GET /users/{username}`
- **GitLab** : `GET /api/v4/users?username=...`
- **DEV Community** : `GET /api/users/by_username?url=...`
- **Chess.com** : `GET /pub/player/{username}`
- **Hacker News** : `GET /v0/user/{id}.json`

L'application présente uniquement le statut d'existence d'une **fiche publique portant exactement le pseudonyme** et ses liens sources. Trois catégories documentaires restent séparées : compte confirmé, absence de fiche publique sur la source, et vérification indisponible (limitation, réseau, format).

Une URL Instagram ainsi que des liens de recherches exactes Google, Bing et DuckDuckGo complètent l'examen, mais ces pages ne sont pas automatiquement analysées. Une même chaîne de caractères sur deux services ne prouve **jamais** qu'il s'agit du même titulaire.

Il n'est pas scientifiquement fondé de calculer une probabilité d'identité civile à partir de simples occurrences de pseudonymes. Les indicateurs mesurent donc des confirmations **de comptes**, pas des personnes.

## Installation

Python 3.11 ou supérieur :

```powershell
git clone https://github.com/QuentinLamboley/finestalk.git
cd finestalk
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:FINESTALK_ACCESS_PASSWORD = "une-phrase-secrete-unique-et-longue"
streamlit run app.py
```

Pour Streamlit Community Cloud : application reliée à `main`, script `app.py`, variable `FINESTALK_ACCESS_PASSWORD` dans **Settings → Secrets**, jamais dans GitHub. Le mot de passe commun est réservé à un usage privé ou de démonstration.

## Vérifications

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
python -m compileall -q app.py query_types.py public_presence.py
python scripts/smoke_public_presence.py
```

Le scénario réseau vérifie deux comptes publics connus sur GitHub et Chess.com, et teste le vrai code. Les autres vérifications automatisées utilisent des réponses simulées (pour la robustesse et la reproductibilité). L'hébergement Streamlit Cloud peut rencontrer des restrictions différentes.

## Architecture évolutive

- `app.py` : interface, champ de recherche, états et protection d'accès.
- `query_types.py` : reconnaissance locale des types de saisie, indépendamment du réseau.
- `public_presence.py` : vérifications publiques strictes et URLs de sources.
- `instagram_lookup.py` : ancien moteur de profil, conservé mais inactif.
- `finestalk_core.py`, `profile_review.py` et `account_characteristics*.py` : anciens modules de dossiers, non utilisés dans cette interface.

Les requêtes API sont limitées en durée et en taille, les redirections désactivées, et l'application n'enregistre pas les recherches dans un fichier ou une base. L'hébergement et la disponibilité des API demeurent des limites externes.

## Licence

CC0 1.0. Voir `LICENSE`.
