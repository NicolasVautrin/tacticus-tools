"""CLASSER les captures de `data/replays/_captures/` sous leur nom canonique.

    python scripts/python/classer_replay.py              # toutes les captures en attente
    python scripts/python/classer_replay.py <fichier>    # une seule

`replay-fin-auto` + `frida/host/replay-store.ts` deposent les replays sous
`data/replays/_captures/<GameMode>-<seed>-f<frame>.json` -- un nom qui porte le MODE et le SEED,
mais ni la campagne ni le noeud. Ce script les nomme.

(!)L'IDENTITE SE LIT DANS LE FICHIER, JAMAIS DANS SON NOM. Le prefixe du fichier de capture dit
`Campaign`, pas `campaign1` : c'est `BattleConfiguration.Id` (`Campaign1_19`) qui porte le numero
de campagne et le noeud. Classer sur le nom de fichier rangerait une bataille sous une campagne
qui n'est pas la sienne.

(!)ET L'IDENTIFIANT DE CAMPAGNE EST DERIVE, PAS ECRIT. `Campaign1_19` donne << type Standard,
campagne 1, noeud 19 >> ; l'identifiant `campaign1` vient du registre derive de
`data/i2_en.json` (cf. `raids_plan.py`), donc il suit le jeu et non une table qu'on aurait
recopiee.

⛔ N'ECRASE JAMAIS. Un nom canonique deja pris est un REFUS, pas un remplacement : deux passages
du meme noeud portent des seeds differents, donc une collision signale un vrai probleme.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from raids_plan import table_des_campagnes          # noqa: E402
from victoire_eclair import verdict                 # noqa: E402

CAPTURES = RACINE / "data" / "replays" / "_captures"
CAMPAGNE = RACINE / "data" / "replays" / "campaign"

# Le prefixe de `BC.Id` -> le type, tel que la localisation le nomme.
TYPE_DU_PREFIXE = {"Campaign": "Standard", "Elite": "Elite",
                   "Mirror": "Mirror", "EliteMirror": "EliteMirror"}


def classer(src, table):
    d = json.loads(src.read_text(encoding="utf-8"))
    bc = d.get("BattleConfiguration") or {}
    bcid, seed = bc.get("Id"), d.get("RngSeed")
    mode = bc.get("GameMode")
    if mode != "Campaign":
        return None, ("mode %r -- ce script ne classe que la CAMPAGNE (guerre de guilde et boss "
                      "ont leurs propres conventions)" % mode)
    if seed is None:
        return None, "`RngSeed` absent -- le nom canonique le porte, on ne l'invente pas"
    m = re.match(r"^([A-Za-z]+?)(\d+)_(\d+)$", str(bcid))
    if not m:
        return None, "`BC.Id` %r ne suit pas <Type><n>_<noeud>" % bcid
    prefixe, num, noeud = m.group(1), int(m.group(2)), int(m.group(3))
    typ = TYPE_DU_PREFIXE.get(prefixe)
    if typ is None:
        return None, "prefixe %r inconnu (connus : %s)" % (prefixe, ", ".join(TYPE_DU_PREFIXE))
    cands = sorted({ident for ident, t, _ in table.values()
                    if t == typ and re.search(r"%d$" % num, ident)})
    if len(cands) != 1:
        return None, ("%d identifiant(s) candidat(s) pour type=%s campagne#%d (%s) -- on ne "
                      "choisit pas a l'aveugle" % (len(cands), typ, num, ", ".join(cands) or "-"))
    dest = CAMPAGNE / ("%s_%d-%d.json" % (cands[0], noeud, seed))
    if dest.exists():
        return None, "%s existe DEJA -- on n'ecrase jamais un replay" % dest.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    # (!)LE VERDICT D'ECLAIR SE REND AU CLASSEMENT, pas plus tard. Une bataille rejouable est
    # une bataille dont on veut savoir TOUT DE SUITE si elle valait le double de pieces --
    # sinon on empile des replays sans savoir lesquels sont a refaire.
    v = verdict(d)
    if v.get("eclair") is True:
        etat = "ECLAIR (%s/%s rounds)" % (v.get("rounds"), v.get("seuil"))
    elif v.get("eclair") is False:
        etat = "eclair MANQUEE (%s rounds pour %s)" % (v.get("rounds"), v.get("seuil"))
    elif v.get("gagne") is False:
        etat = "PERDUE"
    else:
        etat = "eclair NON MESUREE (%s)" % (v.get("refus") or "?").strip(" ;")
    return dest, "%s  %d pas, %d Ko  --  %s" % (bcid, len(d.get("Messages") or []),
                                                dest.stat().st_size // 1024, etat)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fichier", nargs="?", default=None)
    args = ap.parse_args()

    table = table_des_campagnes()
    src = [Path(args.fichier)] if args.fichier else sorted(CAPTURES.glob("*.json"))
    if not src:
        print("aucune capture en attente dans %s" % CAPTURES)
        return 0
    classes = 0
    for p in src:
        if not p.exists():
            print("ABSENT  %s" % p)
            continue
        dest, note = classer(p, table)
        if dest is None:
            # Un refus LAISSE le fichier en place : il n'est pas perdu, il attend.
            print("GARDE   %-38s %s" % (p.name, note))
        else:
            print("CLASSE  %-38s -> %s   (%s)" % (p.name, dest.name, note))
            classes += 1
    print()
    print("%d classe(s), %d laisse(s) en attente" % (classes, len(src) - classes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
