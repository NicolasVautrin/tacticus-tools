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
ap.add_argument("--unite", default="necroDestroyer",
                help="gabarit(s) a faire apparaitre, separes par des virgules. Ils TOURNENT "
                     "d'une pose a l'autre : deux exemplaires du meme heros a l'ecran, ca se "
                     "voit. Doivent etre MECANIQUES et non-summon (contrainte Machine Hunt).")
ap.add_argument("--par-tour", type=int, default=2)
ap.add_argument("--tours", type=int, default=5, help="nombre de vagues, une par tour a partir de 1")
ap.add_argument("--joueur", default="12", help="cle de `BC.Player.Players` visee (l'ENNEMI)")
ap.add_argument("--tag", default="", help="SpawnPointTag -- INDIFFERENT, cf. l'en-tete")
# LE CATALOGUE -- LA SEULE CONDITION QUI FAISAIT ECHOUER LE SPAWN, ET EN SILENCE.
ap.add_argument("--catalogue", default=None,
                help="BC JSON dont `Units` sert a VERIFIER que `--unite` existe. Sans lui, la "
                     "verification N'A PAS LIEU et le script le DIT.")
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

# ---- LE GABARIT DOIT EXISTER AU CATALOGUE, SINON LE SPAWN ECHOUE EN SILENCE --------------
#
# ⛔ C'EST LA CAUSE QUI A COUTE LA SEANCE DU 2026-08-22, ET ELLE NE LAISSE AUCUNE TRACE.
# `necroNpc4Destroyer:19` n'est pas dans `BC.Units` de `Campaign1_06` (175 gabarits, 11
# necrons) : la vague etait POSEE (`vaguesCount: 5` sur le PlayerComponent), l'operation
# TOURNAIT (91 passages dans `VerifyCompleteWaveOperation$$Execute`), et RIEN n'apparaissait.
# Ni erreur, ni evenement, ni log. Avec `necroDestroyer` -- present au catalogue -- 4 unites
# sortent en 3 tours.
#
# (!)LE SUFFIXE DE NIVEAU FAIT PARTIE DE L'ID. L'onslaught natif ecrit
# `tyranNpc3Termagant:6` et son catalogue porte exactement cette entree. Accoler `:19` a un
# nom qui n'en porte pas fabrique un identifiant INTROUVABLE.
#
# (!)TRI-ETAT : sans `--catalogue`, on ne VERIFIE PAS -- et on le DIT. Un << pas verifie >>
# annonce vaut mieux qu'un vert qui n'a rien mesure.
UNITES = [u.strip() for u in args.unite.split(",") if u.strip()]
if not UNITES:
    print("REFUS : `--unite` vide.")
    sys.exit(2)

if args.catalogue:
    _p = Path(args.catalogue)
    if not _p.is_absolute():
        _p = Path(__file__).resolve().parent.parent.parent / _p
    if not _p.exists():
        print("REFUS : `--catalogue %s` INTROUVABLE (%s)" % (args.catalogue, _p))
        sys.exit(2)
    _cat = json.loads(_p.read_text(encoding="utf-8")).get("Units") or []
    _ids = set(str(u.get("Id")) for u in _cat)
    # (!)ON VERIFIE TOUS LES GABARITS, PAS LE PREMIER. Un seul absent suffit a rendre sa vague
    # muette, et le reste du calendrier continuerait de marcher -- donc l'anomalie passerait
    # pour une simple irregularite de cadence.
    _absents = [u for u in UNITES if u not in _ids]
    if _absents:
        print("REFUS : %d gabarit(s) ABSENT(S) du catalogue (%d entrees dans %s) : %s"
              % (len(_absents), len(_ids), _p.name, ", ".join(_absents)))
        print("        Le spawn echouerait EN SILENCE -- ni erreur, ni evenement.")
        for _a in _absents:
            _proches = sorted(i for i in _ids if _a.split(":")[0][:8].lower() in i.lower())
            if _proches:
                print("        %r -> approchants : %s" % (_a, ", ".join(_proches[:6])))
        sys.exit(3)
    # LE TRAIT EST L'AUTRE CONDITION, ET ELLE EST PROPRE A MACHINE HUNT : l'evenement ne compte
    # que les MECHANICAL non-Summon. Un gabarit spawnable mais non mecanique produirait des
    # unites parfaitement visibles qui ne rapportent RIEN -- l'echec le plus couteux, parce
    # qu'il ressemble a un succes.
    _par_id = {str(u.get("Id")): u for u in _cat}
    for _u in UNITES:
        _tr = [str(t.get("Type") if isinstance(t, dict) else t)
               for t in (_par_id[_u].get("Traits") or [])]
        _meca = any("echanic" in t for t in _tr)
        _smn = any("ummon" in t for t in _tr)
        print("  %-32s catalogue OK | Mechanical=%s Summon=%s%s"
              % (_u, "OUI" if _meca else "NON", "OUI" if _smn else "non",
                 "" if (_meca and not _smn) else "   <-- NE COMPTE PAS pour Machine Hunt"))
else:
    print("(!) catalogue NON VERIFIE (`--catalogue <bc.json>` pour le faire) -- un `UnitId`")
    print("    absent de `BC.Units` fait echouer le spawn SANS AUCUNE trace.")

# LE CALENDRIER. Une vague par tour, `Index` INCREMENTE -- c'est ce que le natif ecrit, et
# `SetWaveIndex(turn, index)` pose exactement ce champ (`wave[+0x10]`).
tiers = {}
_k = 0
for i in range(args.tours):
    tour = i + 1
    _poses = []
    for _ in range(args.par_tour):
        _poses.append({"SpawnPointTag": args.tag, "UnitId": UNITES[_k % len(UNITES)],
                       "SpawnSource": 3, "IsClone": False})
        _k += 1
    tiers[str(tour)] = {
        args.joueur: {
            "Index": i,
            "ToSpawn": _poses,
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

print("patch ARME : %d tour(s) x %d unite(s) -> joueur %s, tag %r"
      % (args.tours, args.par_tour, args.joueur, args.tag))
for _t in sorted(tiers, key=int):
    _n = [p["UnitId"] for p in tiers[_t][args.joueur]["ToSpawn"]]
    print("  tour %-3s Index=%s  %s" % (_t, tiers[_t][args.joueur]["Index"], ", ".join(_n)))
print()
print("Il sera applique au PROCHAIN `CampaignGameModeSource$$LoadBattle`, PAR MUTATION de la BC")
print("que la source produit. Monter ensuite le noeud, puis VERIFIER par `--etat` : `lastApply`")
print("dit ce qui a REELLEMENT ete ecrit -- l'armement, lui, ne prouve rien.")
