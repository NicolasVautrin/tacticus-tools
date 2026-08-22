"""TIRER LA BC D'UN NOEUD DE CAMPAGNE, ET Y GREFFER DES VAGUES MECANIQUES.

    python scripts/python/machine_hunt_bc.py --campagne campaign1 --noeud 6
    python scripts/python/machine_hunt_bc.py --campagne campaign1 --noeud 6 --greffer

Deux etages, separes A DESSEIN :

  LIRE     `campaignSourceForger` + `campaignSourceBc` -> la BC du noeud, ECRITE dans `logs/`.
           Aucune energie n'est engagee (`StartCampaignMatch` n'est jamais appele) et rien
           n'est monte a l'ecran.
  GREFFER  `--greffer` pose `UnitSpawningOverTime` dans la BC lue, et ECRIT LA VARIANTE A COTE.
           Le montage, lui, est le travail de `sandbox_campagne.py` -- ce script-ci ne monte
           RIEN. Un fichier sur disque se relit ; un montage ne se rejoue pas.

(!)LE NOEUD EST 1-BASE A L'ECRAN, 0-BASE DANS LA CONFIG -- comme `sandbox_campagne.py`, et les
deux sont imprimes pour que la confusion se VOIE.

(!)LA VAGUE SE POSE SUR LE `PlayerId` DE L'ADVERSAIRE, ET IL SE LIT DANS `BC.Player.Players` --
la seule structure qui le porte. Les `BC.Units` sont des GABARITS de catalogue : mesure du
2026-08-22 sur `Campaign1_06`, **175 unites, AUCUNE ne porte de `PlayerId`**. Une derivation
batie sur elles rend zero candidat, et un `"12"` recopie du premier montage serait une devinette
qui tombe juste par convention -- pas une lecture.

(!)LE NOM DES CLES SE DERIVE, IL NE SE DEVINE PAS -- ce fichier a rate TROIS fois de suite en
ecrivant `SpawnPoints` a la racine du `Board`, puis dans le set. La vraie voie est
`Board.SpawnPointSets[SpawnPointSetIndex].SpawnPointGroups[].SpawnPoints`, et les points de
`C1_01` portent tous `Tag: ""` -- pas `"0"`.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"

ap = argparse.ArgumentParser()
ap.add_argument("--campagne", default="campaign1")
ap.add_argument("--type", type=int, default=0,
                help="0=Standard 1=Elite 2=Mirror 3=EliteMirror 4=Event")
ap.add_argument("--noeud", type=int, required=True, help="numero AFFICHE (1-base)")
ap.add_argument("--greffer", action="store_true",
                help="produire aussi la variante porteuse de `UnitSpawningOverTime`")
ap.add_argument("--unite", default="necroNpc4Destroyer:19",
                help="unite a faire apparaitre (forme `<unitId>:<niveau>`)")
ap.add_argument("--par-tour", type=int, default=2, help="combien d'unites par tour")
ap.add_argument("--tours", type=int, default=5, help="jusqu'a quel tour (inclus) poser une vague")
# (!)LE TAG PAR DEFAUT EST CELUI QUE LE BOARD DECLARE, pas celui du premier montage. Les points
# de `C1_01` portent `Tag: ""`. Le `"0"` qui a marche sur le runner venait d'un AUTRE board ; le
# reprendre ici serait recopier une valeur au lieu de lire celle qui vaut.
ap.add_argument("--tag", default=None,
                help="SpawnPointTag ; par defaut celui que le board porte (souvent la chaine vide)")
args = ap.parse_args()

idx = args.noeud - 1
if idx < 0:
    print("REFUS : `--noeud` est 1-BASE, il ne peut pas valoir moins de 1.")
    sys.exit(2)

sid = session_vivante(HOTE)
if sid is None:
    print("REFUS : aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
    sys.exit(2)
j = Jeu(HOTE, sid)
print("session %d" % sid)
print("cible : type=%d campagne=%s noeud=%d (index %d)" % (args.type, args.campagne,
                                                           args.noeud, idx))

cible = {"campaignType": args.type, "campaignId": args.campagne, "locationIndex": idx,
         "enemyIsAiControlled": True}

f = j.rpc("campaignSourceForger", [dict(cible, confirmer=True)], 240000) or {}
if not f.get("ok"):
    print("REFUS au forgeage : %s" % json.dumps(f, ensure_ascii=False)[:400])
    sys.exit(1)
print("source forgee : %s" % f.get("instance"))

b = j.rpc("campaignSourceBc", [{"confirmer": True}], 300000) or {}
if not b.get("json"):
    print("REFUS : la BC n'a pas ete produite : %s"
          % str(b.get("error") or b.get("jsonRefus"))[:300])
    sys.exit(1)
bc = b["json"]
d = json.loads(bc)

sortie = RACINE / "logs"
sortie.mkdir(parents=True, exist_ok=True)
base = "%s-n%02d" % (args.campagne, args.noeud)
p_brut = sortie / ("bc-%s.json" % base)
p_brut.write_text(bc, encoding="utf-8")

print("BC : Id=%s GameMode=%s board=%s  (%d octets) -> %s"
      % (d.get("Id"), d.get("GameMode"), (d.get("Board") or {}).get("Id"), len(bc), p_brut))

# ---- CE QUE LA BC PORTE DEJA, ET QUI DECIDE DE LA GREFFE ---------------------------------
unites = d.get("Units") or []
avec_pid = Counter(str(u.get("PlayerId")) for u in unites if u.get("PlayerId") is not None)
print("Units : %d gabarit(s), dont %d portant un PlayerId %s"
      % (len(unites), sum(avec_pid.values()), dict(avec_pid) or ""))

# LES POINTS D'APPARITION -- PAR LA VOIE QUI LES PORTE.
board = d.get("Board") or {}
sets = board.get("SpawnPointSets") or []
i_set = int(d.get("SpawnPointSetIndex") or 0)
groupes = (sets[i_set].get("SpawnPointGroups") or []) if i_set < len(sets) else []
tags = Counter()
total_pts = 0
for grp in groupes:
    pts = grp.get("SpawnPoints") or []
    total_pts += len(pts)
    for p in pts:
        tags[str(p.get("Tag"))] += 1
    print("  groupe TeamWithPlayerIndex=%s : %d point(s)" % (grp.get("TeamWithPlayerIndex"),
                                                             len(pts)))
print("SpawnPoints : %d au total sur le set %d/%d ; tags = %s"
      % (total_pts, i_set, len(sets), dict(tags)))

uso = d.get("UnitSpawningOverTime") or {}
tiers = uso.get("Tiers") or {}
print("UnitSpawningOverTime : cle %s, Tiers = %d entree(s) %s"
      % ("PRESENTE" if "UnitSpawningOverTime" in d else "absente", len(tiers),
         "(VIDE -- aucune vague active)" if not tiers else ""))

if not args.greffer:
    print()
    print("LECTURE SEULE. `--greffer` pour produire la variante avec vagues.")
    sys.exit(0)

# LE JOUEUR VISE SE LIT DANS `Player.Players` -- LA SEULE STRUCTURE QUI LE PORTE.
#
# (!)`PlayerType` vaut 0 pour le joueur, 1 pour l'ennemi (mesure sur `Campaign1_06` :
# `"11"` = player/TeamId 1, `"12"` = enemy_1/TeamId 2). On ne se sert PAS des `Units`, qui sont
# des gabarits de catalogue sans `PlayerId`.
joueurs = ((d.get("Player") or {}).get("Players") or {})
if not joueurs:
    print("REFUS : `BC.Player.Players` ABSENT ou vide -- rien a quoi rattacher une vague.")
    sys.exit(3)
for pid, pl in joueurs.items():
    print("  joueur %-4s Name=%-10s PlayerType=%s TeamId=%s"
          % (pid, pl.get("Name"), pl.get("PlayerType"), pl.get("TeamId")))
ennemis = [pid for pid, pl in joueurs.items() if pl.get("PlayerType") == 1]
if len(ennemis) != 1:
    print("REFUS : %d joueur(s) de `PlayerType == 1` -- la cible ne se tranche pas toute seule."
          % len(ennemis))
    sys.exit(3)
adverse = ennemis[0]
print("PlayerId adverse LU : %s (%s)" % (adverse, joueurs[adverse].get("Name")))

# LE TAG : celui que le board porte, sauf demande explicite.
if args.tag is not None:
    tag = args.tag
    print("SpawnPointTag IMPOSE par `--tag` : %r" % tag)
elif len(tags) == 1:
    tag = next(iter(tags))
    print("SpawnPointTag DERIVE du board : %r (%d point(s) le portent)" % (tag, tags[tag]))
else:
    print("REFUS : %d tags distincts sur le board (%s) -- lequel viser ne se derive pas. "
          "Utiliser `--tag`." % (len(tags), dict(tags)))
    sys.exit(3)

vague = {
    "Index": 0,
    "ToSpawn": [{"SpawnPointTag": tag, "UnitId": args.unite,
                 "SpawnSource": 3, "IsClone": False} for _ in range(args.par_tour)],
    "ToSpawnOnComplete": [],
    "UpgradeToRarity": None,
    "IsCloneAllUnits": False,
    "CloneAllUnitsHealthPct": None,
}
# (!)ON CONSERVE LES CHAMPS FRERES DE `Tiers`. La BC de campagne porte `UseAtomicGroup` et
# `UseSpawnPointFromUnitIndex` a cote ; ecraser le noeud ENTIER les perdrait en silence, et
# c'est exactement la forme de degat que `#380-r1` documente sur `BC.Utilities`.
uso_greffe = dict(uso)
uso_greffe["Tiers"] = {str(t): {adverse: json.loads(json.dumps(vague))}
                       for t in range(1, args.tours + 1)}
d["UnitSpawningOverTime"] = uso_greffe

p_greffe = sortie / ("bc-%s-vagues.json" % base)
p_greffe.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print()
print("GREFFE : %d tour(s) x %d %s sur le PlayerId %s -> %s"
      % (args.tours, args.par_tour, args.unite, adverse, p_greffe))
print("MONTER : sandbox_campagne.py ne lit pas ce fichier -- utiliser `--bc %s`." % p_greffe.name)
