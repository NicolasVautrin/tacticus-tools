#!/usr/bin/env python
"""Les replays que LE JEU ecrit tout seul -- les lister, les decoder, les rendre rejouables.

    python scripts/python/importer_replay_du_jeu.py                    # lister
    python scripts/python/importer_replay_du_jeu.py --importer <nom>   # decoder UN fichier
    python scripts/python/importer_replay_du_jeu.py --importer <nom> --out <chemin.json>

(!)IL EXISTE UNE SECONDE SOURCE DE REPLAYS, INDEPENDANTE DE `replayFinAuto`, ET ELLE COUVRE
TOUT. Tacticus depose un replay par bataille dans

    %USERPROFILE%\\AppData\\LocalLow\\Snowprint\\Warhammer 40,000_ Tacticus\\replays\\
    <Mode>-<j.m.aaaa>-<hhmm UTC>.replay.txt

encode en **base64(gzip(json))**. Une fois decode, le document est **identique au notre, cle
pour cle** (12 cles racine, 5 par message) : il se rejoue tel quel.

⚠ CE QUE CA REPARE, ET C'EST MESURE. Le 2026-08-24, `replayFinAuto` etait reste desarme
apres une reinjection : la tentative reelle de boss de guilde de l'utilisateur -- une
tentative CONSOMMEE, non renouvelable -- a ete rapportee comme << perdue, aucun replay
capture >>. Elle ne l'etait pas : le jeu l'avait ecrite. **Avant de declarer un replay
perdu, regarder ici.** Notre capteur n'est pas la seule source, seulement la plus rapide.

⚠ LE MEME REPERTOIRE CONTIENT DES INSTANTANES QUI NE SONT PAS DES REPLAYS. Certains
`.replay.txt` sont du JSON nu commencant par `{"_pendingDeaths":...}` -- un vidage d'etat.
On essaie les trois encodages et on sort en `PAS UN REPLAY`, jamais en silence.

⛔ LA SORTIE NE VA PAS DANS `data/`. `data/` ne porte que des ENTREES versionnees ; un
artefact produit par un run va dans `logs/`, qui meurt avec le worktree. Pour le ranger
ensuite sous `data/replays/<mode>/`, c'est `classer_replay.py` qui le fait -- il lit
l'identite DANS le fichier (`BattleConfiguration.Id`), jamais dans son nom.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_JEU = (Path(os.environ.get("USERPROFILE", Path.home())) / "AppData" / "LocalLow"
               / "Snowprint" / "Warhammer 40,000_ Tacticus" / "replays")
SORTIE_DEFAUT = RACINE / "logs" / "replays-du-jeu"

CLES_ATTENDUES = {"RngSeed", "BattleConfiguration", "Messages", "BattleResult", "MetaData"}


def decoder(chemin: Path):
    """Rend `(document, motif)` -- `document` a `None` quand ce n'est pas un replay."""
    try:
        brut = chemin.read_bytes()
    except OSError as e:
        return None, "illisible (%s)" % type(e).__name__
    for essai in ("b64gz", "gz", "json"):
        try:
            if essai == "b64gz":
                d = json.loads(gzip.decompress(base64.b64decode(brut)))
            elif essai == "gz":
                d = json.loads(gzip.decompress(brut))
            else:
                d = json.loads(brut.decode("utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and CLES_ATTENDUES <= set(d):
            return d, essai
        return None, "PAS UN REPLAY (%s, cles=%s)" % (
            essai, ",".join(sorted(list(d)[:4])) if isinstance(d, dict) else type(d).__name__)
    return None, "aucun encodage connu (ni base64+gzip, ni gzip, ni json)"


def resume(d: dict) -> str:
    bc = d.get("BattleConfiguration") or {}
    fin = ((d.get("BattleResult") or {}).get("EndReason"))
    meta = d.get("MetaData") or {}
    return ("Id=%-34s seed=%-12s coups=%-4d fin=%-12s triche=%s version=%s"
            % (bc.get("Id"), d.get("RngSeed"), len(d.get("Messages") or []),
               fin, d.get("UsedDebugCheat"), meta.get("GameVersion")))


def lister() -> int:
    if not DOSSIER_JEU.is_dir():
        print("[replays-du-jeu] NON MESURE -- repertoire absent : %s" % DOSSIER_JEU)
        return 2
    fichiers = sorted(DOSSIER_JEU.iterdir(), key=lambda p: p.stat().st_mtime)
    if not fichiers:
        print("[replays-du-jeu] repertoire VIDE : %s" % DOSSIER_JEU)
        return 0
    print("[replays-du-jeu] %s" % DOSSIER_JEU)
    lisibles = 0
    for f in fichiers:
        d, motif = decoder(f)
        if d is None:
            print("   --  %-42s %s" % (f.name, motif))
            continue
        lisibles += 1
        print("   OK  %-42s %s" % (f.name, resume(d)))
    print("\n   %d replay(s) rejouable(s) sur %d fichier(s)." % (lisibles, len(fichiers)))
    print("   (!) l'heure du NOM est en UTC, celle du fichier est locale -- ne pas les confondre.")
    return 0


def importer(nom: str, out: Path | None) -> int:
    src = Path(nom)
    if not src.is_file():
        src = DOSSIER_JEU / nom
    if not src.is_file():
        print("[replays-du-jeu] introuvable : %s" % nom)
        return 2
    d, motif = decoder(src)
    if d is None:
        print("[replays-du-jeu] REFUS -- %s : %s" % (src.name, motif))
        return 1
    if out is None:
        mode = (d.get("MetaData") or {}).get("Mode") or "Inconnu"
        SORTIE_DEFAUT.mkdir(parents=True, exist_ok=True)
        out = SORTIE_DEFAUT / ("%s-%s-jeu.json" % (mode, d.get("RngSeed")))
    if out.exists():
        # N'ECRASE JAMAIS : deux batailles distinctes ont des seeds distincts, donc une
        # collision de nom signale un vrai probleme, pas un doublon anodin.
        print("[replays-du-jeu] REFUS -- existe deja : %s" % out)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print("[replays-du-jeu] %s\n   -> %s\n   %s" % (src.name, out, resume(d)))
    print("\n   pour le ranger sous data/replays/<mode>/ :")
    print("   python scripts/python/classer_replay.py %s" % out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--importer", metavar="NOM", help="nom du fichier (ou chemin complet)")
    ap.add_argument("--out", type=Path, help="chemin de sortie (defaut : logs/replays-du-jeu/)")
    a = ap.parse_args()
    return importer(a.importer, a.out) if a.importer else lister()


if __name__ == "__main__":
    sys.exit(main())
