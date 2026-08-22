"""GREFFER UN CALENDRIER DE VAGUES PAR **MUTATION** DE LA BC QUE LA SOURCE PRODUIT.

    python scripts/python/machine_hunt_patch.py --poser
    python scripts/python/machine_hunt_patch.py --etat
    python scripts/python/machine_hunt_patch.py --retirer

⛔ CE N'EST PAS UNE SUBSTITUTION, ET C'EST TOUT LE SUJET. On ne fabrique aucun JSON de BC, on
n'en monte aucun a la place d'un autre. Le patch est applique par le hook
`CampaignGameModeSource$$LoadBattle.onLeave` **a la BC que la source vient de construire**, en
memoire, avant que quiconque la consomme. La sandbox delegue le montage de la BC a cette
source : c'est donc cet objet-la qui est mute.

(!)C'EST LE DERNIER MOMENT OU LE CALENDRIER EST MODIFIABLE.
`OperationProcessor$$AddPlayer(playerId, teamId, name, draftings, spawnsPerTurn, ...)` le
transcrit dans le `PlayerComponent` au SETUP et ne le relit JAMAIS. Muter apres le START n'a
aucun effet -- pas une opinion : c'est ce que fait `AddPlayer`.

LES VALEURS SE LISENT SUR UNE BC PRODUITE PAR LE JEU, ELLES NE SE DEVINENT PAS. Mesure du
2026-08-22 sur un onslaught (`sandbox_mode.py bc --mode waves`), qui en porte six :

    cle joueur       "12"            <- `BC.Player.Players`, celui de `PlayerType == 1`
    SpawnPointTag    "defaultGroup"
    Index            0,1,2,3,4,5     <- INCREMENTE d'une vague a l'autre, jamais remis a zero
    SpawnSource      3

⚠ `SpawnPointTag` NE S'APPARIE A AUCUN `Tag` DU BOARD. Les 17 points de `Waves_Imperial_22`
portent tous la chaine vide, et l'onslaught tourne quand meme. C'est une cle de CONVENTION du
moteur, pas une reference au plateau -- << deriver le tag du board >> etait un raisonnement faux
qui se donnait l'air rigoureux, et il a produit un calendrier inerte.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"

ap = argparse.ArgumentParser()
ap.add_argument("--poser", action="store_true", help="armer le patch pour le prochain LoadBattle")
ap.add_argument("--retirer", action="store_true", help="desarmer le patch")
ap.add_argument("--etat", action="store_true", help="lire le patch en attente et la derniere pose")
ap.add_argument("--unite", default="necroNpc4Destroyer:19",
                help="unite a faire apparaitre (`<unitId>:<niveau>`) -- MECANIQUE, non-summon")
ap.add_argument("--par-tour", type=int, default=2)
ap.add_argument("--tours", type=int, default=5, help="nombre de vagues, une par tour a partir de 1")
ap.add_argument("--joueur", default="12", help="cle de `BC.Player.Players` visee (l'ENNEMI)")
ap.add_argument("--tag", default="defaultGroup", help="SpawnPointTag -- celui que le NATIF ecrit")
args = ap.parse_args()

if not (args.poser or args.retirer or args.etat):
    print("REFUS : choisir --poser, --retirer ou --etat.")
    sys.exit(2)

sid = session_vivante(HOTE)
if sid is None:
    print("REFUS : aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
    sys.exit(2)
j = Jeu(HOTE, sid)
print("session %d" % sid)

if args.etat:
    r = j.rpc("getBattleConfigPatchStatus", [], 60000) or {}
    print(json.dumps(r, ensure_ascii=False, indent=1)[:2500])
    sys.exit(0)

if args.retirer:
    r = j.rpc("clearBattleConfigPatch", [], 60000) or {}
    print("patch RETIRE : %s" % json.dumps(r, ensure_ascii=False)[:200])
    sys.exit(0 if r.get("ok") else 1)

# LE CALENDRIER. Une vague par tour, `Index` INCREMENTE -- c'est ce que le natif ecrit, et
# `SetWaveIndex(turn, index)` pose exactement ce champ (`wave[+0x10]`).
tiers = {}
for i in range(args.tours):
    tour = i + 1
    tiers[str(tour)] = {
        args.joueur: {
            "Index": i,
            "ToSpawn": [{"SpawnPointTag": args.tag, "UnitId": args.unite,
                         "SpawnSource": 3, "IsClone": False}
                        for _ in range(args.par_tour)],
            "ToSpawnOnComplete": [],
            "UpgradeToRarity": None,
            "IsCloneAllUnits": False,
            "CloneAllUnitsHealthPct": None,
        }
    }

# (!)`consumeOnce: False` -- ET C'EST UN CHOIX, PAS UN OUBLI. Le montage traverse plusieurs
# `LoadBattle` (la lecture de la source, puis le montage lui-meme) ; un patch consomme au premier
# passage ne serait plus la au bon. On le RETIRE explicitement apres coup (`--retirer`), ce qui
# est verifiable, alors qu'une consommation automatique ne se voit pas.
patch = {"unitSpawningOverTime": tiers, "consumeOnce": False}
r = j.rpc("setBattleConfigPatch", [patch], 60000) or {}
if not r.get("ok"):
    print("REFUS : %s" % json.dumps(r, ensure_ascii=False)[:400])
    sys.exit(1)

print("patch ARME : %d tour(s) x %d %s -> joueur %s, tag %r"
      % (args.tours, args.par_tour, args.unite, args.joueur, args.tag))
print("  Index : %s" % ", ".join(str(i) for i in range(args.tours)))
print()
print("Il sera applique au PROCHAIN `CampaignGameModeSource$$LoadBattle`, PAR MUTATION de la BC")
print("que la source produit. Monter ensuite le noeud, puis VERIFIER par `--etat` : `lastApply`")
print("dit ce qui a REELLEMENT ete ecrit -- l'armement, lui, ne prouve rien.")
