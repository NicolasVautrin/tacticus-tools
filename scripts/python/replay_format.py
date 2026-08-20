"""LE FORMAT D'UN REPLAY -- foyer unique du decodage.

Un replay existe sous DEUX formes et le NOM NE LES DISTINGUE PAS : JSON brut, ou base64+gzip.
Mesure du 2026-08-20 : `belisarius-reel.json` etait du gzip malgre son extension. On SNIFFE
donc le contenu, jamais l'extension.

(!)POURQUOI CE MODULE EXISTE PLUTOT QU'UN IMPORT DEPUIS `replay_lire.py`. Ce dernier construit
son `argparse` AU NIVEAU MODULE : l'importer EXECUTE son analyseur, qui avale les arguments de
l'appelant. Mesure du 2026-08-20 -- `campagne_rejeu.py --campagne elite4` sortait sur
`unrecognized arguments`, avec l'usage de `replay_lire` affiche. Un module dont le corps
s'execute a l'import n'est pas reutilisable ; on extrait donc ce qui doit l'etre, sans
re-indenter un script qui marche.
"""
import base64
import gzip
import json
from pathlib import Path


def charger(chemin):
    """Rend (donnees, format). LEVE si illisible -- un replay muet ne se rabat pas sur du vide."""
    brut = Path(chemin).read_text(encoding="utf-8").strip()
    if brut.startswith("{"):
        return json.loads(brut), "JSON brut"
    octets = gzip.decompress(base64.b64decode(brut))
    return json.loads(octets.decode("utf-8")), "base64+gzip (%d octets decompresses)" % len(octets)
