"""Contrôle réseau facultatif : deux profils publics connus.

Une réponse 403/429/délai ne signifie pas l'absence de profil et ne
constitue pas une régression de l'algorithme. Résultats imprimés dans le CI.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from public_presence import check_platform

SAMPLES = [
    ("GitHub", "octocat"),
    ("Chess.com", "hikaru"),
]

def main() -> int:
    successes = 0
    for platform, handle in SAMPLES:
        result = check_platform(platform, handle)
        print(
            f"API={platform} handle={handle} resultat={result.state} "
            f"HTTP={result.http_status} source={result.source_url}",
            flush=True,
        )
        if result.state == "found":
            successes += 1
    print(f"RESEAU: {successes}/{len(SAMPLES)} confirmations exactes", flush=True)
    return 0 if successes > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
