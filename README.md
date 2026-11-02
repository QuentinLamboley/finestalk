# Finestalk

Une interface Streamlit minimale pour consulter les **informations explicitement affichées par un profil public Instagram** à partir d'un pseudonyme.

**Application :** https://finestalk.streamlit.app/  
**Branche de déploiement :** `main`  
**Point d'entrée :** `app.py`

## Interface actuelle

L'application présente une seule barre de recherche après déverrouillage par mot de passe.

- Saisir `@pseudo`, `pseudo` ou l'adresse HTTPS de son profil Instagram.
- Appuyer sur **Entrée** pour demander la prévisualisation.
- Voir le pseudonyme, le lien canonique, la date de consultation, le nom **tel qu'affiché** et la description publique **si Instagram les fournit réellement**.
- Ouvrir le compte directement sur Instagram.

Aucun dossier, formulaire de collecte, tableau de bord ou menu de gestion n'apparaît dans l'interface. Les anciens modules restent dans le dépôt pour permettre des évolutions ultérieures, sans être importés ni exécutés au démarrage.

## Ce qui est techniquement possible

Le code effectue **au maximum une requête HTTPS vers une URL Instagram construite à partir du pseudonyme** :

- Aucun identifiant Instagram n'est demandé.
- Les redirections HTTPS vers **le même profil** sur un hôte Instagram autorisé sont suivies (trois maximum) ; toute destination différente est refusée. Si Instagram redirige vers une connexion, la consultation s'arrête et l'application l'explique.
- Aucune URL libre transmise par l'utilisateur n'est interrogée.
- Le téléchargement de HTML est plafonné à 512 Kio, avec délais réseau.
- Aucun mécanisme de contournement des protections, recherche en masse ou collecte de données privées n'est prévu.
- Les données publiques ne sont pas inscrites dans la base de données.
- Une consultation identique peut être réutilisée durant deux minutes dans la même session pour éviter des requêtes répétées.

La disponibilité des métadonnées dépend de ce qu'Instagram renvoie publiquement à l'instant de la recherche. Si la plateforme affiche une page de connexion, une restriction ou un document générique, Finestalk indique la limite **sans inventer de résultat**.

Le nom affiché sur un compte peut être une marque, un alias, un nom choisi, une usurpation ou une donnée trompeuse. **Il ne constitue pas une identification civile.** L'application ne désanonymise pas les titulaires, ne recoupe pas des pseudos sur plusieurs plateformes, ne cherche pas d'adresse ni de téléphone personnel et n'attribue pas de probabilité nominative.

## Installation locale

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

Le mot de passe ne doit pas être placé dans le code. Pour Streamlit Community Cloud, configurer `FINESTALK_ACCESS_PASSWORD` dans **Settings → Secrets** (format TOML), et s'assurer que l'application pointe vers le dépôt `QuentinLamboley/finestalk`, branche `main`, fichier `app.py`.

L'authentification actuelle utilise un secret commun : elle convient à un prototype privé, **pas** à un service multiutilisateur. Pour un service public, prévoir une authentification individuelle et des contrôles d'accès plus solides.

## Tests

```bash
python -m pip install pytest
python -m pytest -q
python -m compileall -q app.py instagram_lookup.py profile_review.py
```

Les tests de consultation utilisent un transport simulé : ils valident le code sans lancer de requêtes vers Instagram. Ils ne garantissent pas que la plateforme autorisera la lecture réelle de ses pages.

## Évolutivité

`instagram_lookup.py` contient la logique de consultation ; `app.py` ne contient que la présentation et la protection par mot de passe. Les composants précédemment développés (`finestalk_core.py`, `profile_review.py`, `account_characteristics*.py`) sont conservés mais masqués pour les versions ultérieures.

## Licence

CC0 1.0, voir `LICENSE`.
