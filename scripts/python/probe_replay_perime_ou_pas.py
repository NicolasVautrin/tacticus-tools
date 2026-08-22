"""LE ROSTER A BOUGE -- EST-CE QUE CA CASSE LE REPLAY, OU SEULEMENT LE DIFF ?

    python scripts/python/probe_replay_perime_ou_pas.py --replay data/replays/campaign/<x>.json

Le cran 3 de `campagne_rejeu_reel.py` compare la BC ENTIERE, catalogue d'unites compris. Une
unite qui entre au roster fait donc diverger les 27 replays d'un coup -- mesure du 2026-08-22 --
alors qu'elle n'entre dans AUCUNE bataille.

Ce probe repond a la seule question qui compte pour du farming : **les entites que le replay
manipule sont-elles restees les memes ?**

  - si l'unite neuve est AJOUTEE EN FIN de `BC.Units`, les indices des autres ne bougent pas,
    donc les ids que portent les messages enregistres designent toujours les memes unites : le
    replay est REJOUABLE et le cran 3 est trop strict ;
  - si elle est INSEREE AU MILIEU, tout ce qui suit se decale, et les coups frapperaient
    d'autres unites -- le refus du cran 3 est alors JUSTE.

⛔ ON NE CONCLUT PAS DE LA LONGUEUR. 175 -> 176 ne dit pas OU. C'est la position qui tranche, et
elle se lit en comparant les listes element par element jusqu'au premier desaccord.
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay_format import charger as charger_replay          # noqa: E402
from replay_rejouer import Jeu, session_vivante              # noqa: E402
from campagne_rejeu import resoudre_hors_ligne, forger_bc    # noqa: E402


def cle(u):
    """L'IDENTITE D'UNE ENTREE DE ROSTER, telle qu'un message enregistre la designerait."""
    if not isinstance(u, dict):
        return repr(u)[:40]
    for k in ("Id", "UnitId", "unitId", "id"):
        if u.get(k) is not None:
            return str(u[k])
    return json.dumps(u, sort_keys=True)[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    args = ap.parse_args()

    chemin = Path(args.replay)
    if not chemin.is_absolute():
        chemin = (RACINE / chemin).resolve()
    d, _ = charger_replay(chemin)
    bcr = d.get("BattleConfiguration") or {}
    campagne, type_, noeud = resoudre_hors_ligne(d, bcr.get("Id"))

    sid = session_vivante(args.hote)
    if sid is None:
        print("REFUS : aucune session vivante -- la BC du noeud ne peut pas etre forgee.")
        return 2
    jeu = Jeu(args.hote, sid)
    # ⚠ `forger_bc` rend un COUPLE `(bc, motif)`, et prend un `locationIndex` 0-BASE. Les deux
    #   se sont trompes ici a la premiere version -- d'ou un << forge NON MESUREE >> qui accusait
    #   le harnais alors que l'appel etait faux.
    bcn, motif = forger_bc(jeu, campagne, type_, noeud - 1)
    if not isinstance(bcn, dict):
        print("REFUS : forge de la BC NON MESUREE -- %s" % motif)
        return 2

    ur, un = bcr.get("Units") or [], bcn.get("Units") or []
    print("BC.Units : replay=%d  noeud=%d  (ecart %+d)" % (len(ur), len(un), len(un) - len(ur)))

    kr, kn = [cle(u) for u in ur], [cle(u) for u in un]
    prefixe = 0
    for a, b in zip(kr, kn):
        if a != b:
            break
        prefixe += 1
    print("prefixe COMMUN : %d entree(s) identiques depuis le debut" % prefixe)

    if prefixe == len(kr):
        print()
        print("=> AJOUT EN FIN. Les %d entrees du replay gardent leur INDICE ; les %d ajoutee(s) "
              "sont apres." % (len(kr), len(kn) - len(kr)))
        print("   Les ids que portent les messages enregistres designent donc les MEMES unites.")
        print("   Le refus du cran 3 est TROP STRICT pour ce cas.")
        for u in kn[len(kr):]:
            print("      ajoutee : %s" % u)
    else:
        print()
        print("=> INSERTION AU RANG %d -- tout ce qui suit est DECALE." % prefixe)
        print("   replay[%d] = %s" % (prefixe, kr[prefixe] if prefixe < len(kr) else "(fin)"))
        print("   noeud [%d] = %s" % (prefixe, kn[prefixe] if prefixe < len(kn) else "(fin)"))
        print("   Le refus du cran 3 est JUSTE : les coups frapperaient d'autres unites.")

    # Et LES UNITES REELLEMENT EN JEU, qui sont le seul substrat que le replay touche.
    pr = (bcr.get("PredefinedUnits") or [])
    pn = (bcn.get("PredefinedUnits") or [])
    memes = json.dumps(pr, sort_keys=True) == json.dumps(pn, sort_keys=True)
    print()
    print("PredefinedUnits (la team affrontee) : %s"
          % ("IDENTIQUES" if memes else "DIFFERENTES -- refus JUSTE"))
    br = (bcr.get("Board") or {}).get("Id")
    bn = (bcn.get("Board") or {}).get("Id")
    print("Board : replay=%s  noeud=%s  %s" % (br, bn, "identique" if br == bn else "DIFFERENT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
