"""Controle anti-PERTE sur `docs/rl/backlog.md` : compare LIGNE A LIGNE l'arbre de travail a
`origin/master`, par identifiant de residu.

Le vice a garder (incident mesure : la ligne `#521-r4` a perdu 2 255 caracteres pendant la
resolution d'un conflit portant sur une ligne VOISINE, et la perte a vecu 4 commits sur `master`) :
une ligne qui RACCOURCIT alors qu'on ne l'a pas editee volontairement.

Usage : python <ce fichier> [id volontairement edite]...
"""
import io
import pathlib
import re
import subprocess
import sys

#: Les identifiants qu'on a EDITES VOLONTAIREMENT dans cette tranche. Tout le reste doit etre
#: BIT POUR BIT celui d'`origin/master` : c'est la seule facon de voir une perte causee par la
#: resolution d'un conflit portant sur une ligne VOISINE.
EDITEES = set(sys.argv[1:])
#: `<racine>/scripts/python/<ce fichier>` -> DEUX remontees. Jamais un chemin en dur : ce cliquet
#: doit tourner depuis n'importe quel worktree d'agent.
RACINE = str(pathlib.Path(__file__).resolve().parents[2])


def par_id(texte):
    out = {}
    for l in texte.split("\n"):
        m = re.match(r"^\|\s*`?#([A-Za-z0-9\-]+)`?\s*\|", l)
        if m:
            out[m.group(1)] = l
    return out


amont = par_id(subprocess.run(["git", "show", "origin/master:docs/rl/backlog.md"],
                              cwd=RACINE, capture_output=True, text=True,
                              encoding="utf-8").stdout)
with io.open(str(pathlib.Path(RACINE) / "docs" / "rl" / "backlog.md"), encoding="utf-8") as f:
    local = par_id(f.read())

print("lignes de residu : amont=%d  local=%d" % (len(amont), len(local)))
perdues = sorted(set(amont) - set(local))
neuves = sorted(set(local) - set(amont))
print("RETIREES  :", perdues or "(aucune)")
print("AJOUTEES  :", neuves or "(aucune)")

raccourcies, allongees, modifiees_hors_perimetre = [], [], []
for rid in sorted(set(amont) & set(local)):
    a, b = amont[rid], local[rid]
    if a == b:
        continue
    if rid not in EDITEES:
        modifiees_hors_perimetre.append((rid, len(a), len(b)))
    if len(b) < len(a):
        raccourcies.append((rid, len(a), len(b), len(a) - len(b)))
    else:
        allongees.append((rid, len(a), len(b)))

print()
print("ALLONGEES (attendu sur mes lignes) :")
for rid, la, lb in allongees:
    print("   #%-18s %6d -> %6d  (+%d)%s" % (rid, la, lb, lb - la,
                                             "" if rid in EDITEES else "   <<< HORS PERIMETRE"))
print()
print("RACCOURCIES (=> PERTE presumee) :")
for rid, la, lb, d in raccourcies:
    print("   #%-18s %6d -> %6d  (-%d)   %s" % (rid, la, lb, d,
                                                "editee volontairement" if rid in EDITEES
                                                else "<<< PERTE NON VOULUE"))
if not raccourcies:
    print("   (aucune)")
print()
hp = [x for x in modifiees_hors_perimetre]
print("MODIFIEES HORS PERIMETRE :", hp or "(aucune)")
print()
mauvais = [r for r in raccourcies if r[0] not in EDITEES] + hp
print("VERDICT :", "PASS" if not mauvais else "FAIL -- %d ligne(s) suspecte(s)" % len(mauvais))
sys.exit(1 if mauvais else 0)
