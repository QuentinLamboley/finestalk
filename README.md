# Finestalk

**Finestalk** explore la présence publique d'un **pseudonyme Instagram** sur plusieurs plateformes, en restant une interface Streamlit simple : une seule barre de recherche et une fiche de résultats. Ce n'est pas un outil de désanonymisation de personnes.

- Application cible : https://finestalk.streamlit.app/
- Dépôt : https://github.com/QuentinLamboley/finestalk
- Branche : `main`
- Fichier d'entrée : `app.py`

## Comment fonctionne une recherche ?

Tapez un pseudonyme, par exemple `@octocat`, puis validez. L'application vérifie en parallèle, au plus trois requêtes à la fois, la présence **exacte du même pseudonyme** dans les interfaces publiques de :

1. **GitHub** — `GET /users/{username}`
2. **GitLab** — `GET /api/v4/users?username=...`
3. **DEV Community** — `GET /api/users/by_username?url=...`
4. **Chess.com** — `GET /pub/player/{username}`
5. **Hacker News** — `GET /v0/user/{id}.json`

Elle distingue explicitement :

- **Compte public trouvé** : une API a retourné une fiche portant ce pseudonyme exact.
- **Aucune fiche publique trouvée** : l'API a retourné un résultat vide ou un code 404. Cela n'établit pas que le pseudo est disponible.
- **Vérification indisponible** : réseau, limitation, authentification, réponse inattendue ou format de pseudo incompatible. Aucun résultat absent/positif n'est déduit dans ce cas.

Une recherche exacte peut aussi être ouverte manuellement sur Google, Bing et DuckDuckGo. **Finestalk ne collecte pas les résultats de ces moteurs.**

**Important :** deux comptes portant le même pseudonyme peuvent appartenir à deux personnes différentes. Une correspondance de nom d'utilisateur est une observation sur des comptes, pas une preuve d'identité. Aucun nom civil, contact privé, adresse, localisation ou pourcentage de probabilité d'identité n'est récupéré ni inféré.

Le module Instagram initial reste dans le dépôt mais n'est plus interrogé par l'interface : l'hébergement Streamlit recevait des redirections de connexion plutôt que les métadonnées du profil.

## Installation

Python 3.11 ou supérieur :

```powershell
git clone https://github.com/QuentinLamboley/finestalk.git
cd finestalk
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:FINESTALK_ACCESS_PASSWORD = "une-longue-phrase-secrete-unique"
streamlit run app.py
```

Sur Streamlit Community Cloud, configurez `FINESTALK_ACCESS_PASSWORD` dans les secrets privés de l'application (Settings → Secrets). **Ne l'inscrivez pas dans GitHub.** Le code lit ce secret, sans changer le design de la page de connexion.

## Limites et sécurités

- Les seules destinations contactées sont cinq **API publiques prédéfinies**, construites à partir d'un pseudonyme validé. Pas d'URL arbitraire, de connexion aux comptes, d'exploration en profondeur, ni de contournement de restriction.
- Une requête par plateforme, redirections HTTP désactivées, connexion limitée à 3,5 s, lecture à 7 s, corps JSON plafonné à 160 Ko.
- Au maximum trois consultations simultanées. Une recherche déjà effectuée est gardée pendant trois minutes dans la session Streamlit (pas de base de données de recherche ni de fichier exporté).
- Aucun nom, biographie, coordonnées ni données de profils tiers ne sont récupérés dans les réponses JSON : seuls le statut de présence du pseudonyme et les liens officiels vers les pages sont affichés.
- L'accès distant aux API peut être limité depuis certains hébergeurs. Le panneau de résultats indique alors **Indisponible**, sans inventer d'identité ni déclarer le profil absent.

Les anciens modules de gestion de dossiers restent dans le code pour une étape ultérieure, sans être chargés par `app.py`. L'instance Streamlit actuelle utilise un secret partagé et **n'est pas destinée à accueillir plusieurs utilisateurs indépendants**.

## Vérifications

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
python -m compileall -q app.py public_presence.py
python scripts/smoke_public_presence.py
```

Les tests automatisés hors réseau couvrent les réponses confirmées, absentes, invalides, bloquées, les formats propres aux plateformes et les échecs de connexion. Le script de vérification réseau tente deux comptes publics connus, imprime les statuts réellement obtenus et échoue si aucune réponse positive n'est reçue. Ce contrôle est **non bloquant** en CI afin qu'une panne ou une limitation d'une API externe n'empêche pas la livraison d'un correctif testé localement.

## Licence

CC0 1.0. Voir `LICENSE`.
