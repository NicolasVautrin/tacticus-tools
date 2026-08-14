"""#1071 LIVE -- `VengeanceForTheOmnissiah` (passif triggered 0x512 = 1298) confronte au natif.

LE PROBLEME DE PORTEUR, ET SA SOLUTION (a lire avant de toucher au montage)
==========================================================================
Les DEUX porteurs sont hors pool : `admecSmnTechpriest` (SUMMON dont l'unique invocateur est
`InvocationOfMachineVengeance` 1172, portee par le seul `admecBossBelisarius`, npc) et
`admecNpc2Techpriest` (npc). L'audit `passive-ability-coverage.md` les rend `S?=1 N=1`.

Le montage n'est PAS une greffe : c'est un MIRROR par le JUMEAU NPC, apparie par son `visualId`
(`gameconfig.units.summons.admecSmnTechpriest.visualId == "admecNpc2Techpriest"`), amene par
`--explicit-stats admecNpc2Techpriest:45`. Le jumeau porte le MEME kit
(`passiveAbilities = [VengeanceForTheOmnissiah, OmnissiahsBlessing]`) et ses PROPRES stats, traits
et armes -- donc rien n'est substitue. MESURE au montage : le port lit
`ctx.passive_abilities == ['VengeanceForTheOmnissiah', 'OmnissiahsBlessing']` et
`traits == ['Imperial', 'Mechanic', 'Mechanical', 'NPC']`.

⚠ L'unite entre au pool sous son nom SUFFIXE DU PALIER (`admecNpc2Techpriest:45`) : c'est ce nom-la
qu'attend `--a-units`, et le nom NU y est refuse (`hors pool / non spawnables`).

POURQUOI CET ITEM EST CONFRONTABLE MALGRE #1049-r1
==================================================
Le defaut connu d'`--explicit-stats` (`AbilityState` annonce `(niveau 1, mult 100)` contre
`(65, 200)` sur le canal `unitAbilityStates`) fausse toute lecture PER-NIVEAU. Il ne mord PAS ici,
et c'est LU au decompile, pas suppose : `CreateBehaviour` appelle la surcharge
`IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(this, constantType, config)` (TROIS arguments),
qui alloue `IdunBattle.Entities.Formulas.ConfigAmount$$.ctor(this, config, constantType)` --
l'unique surcharge a trois parametres, qui renseigne `Nullable(constantType)@+0x38` et laisse
`+0x30` VIDE. `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` bifurque exactement dessus et
prend la branche `AbilityConfiguration$$GetNumberConstant` -- le niveau d'ability n'entre JAMAIS
dans la lecture. Le montage CONFIRME le regime : ce probe imprime `plvl/mult` mesures (65 / 200) a
cote de la magnitude attendue (1), pour que l'independance soit VISIBLE et non affirmee.

LE MONTAGE, PAS A PAS
=====================
Trois unites, board `MC1_67` (7x9), seed 777 :

  * `admecNpc2Techpriest:45` -- le PORTEUR, equipe ADVERSE, a son spawn `(6,8)` ;
  * `admecDestroyer`         -- la VICTIME, equipe ADVERSE (donc ALLIEE du porteur), trait
                                `Mechanical`, mise a **1 PV** ;
  * `admecManipulus`         -- le TUEUR, MON equipe, place par `--place`.

Deux regimes, et la SEULE piece qui bouge entre eux est une POSITION -- jamais un gate, jamais un
trait :

  * NOMINAL       : victime a son spawn `(6,7)`, donc ADJACENTE au porteur ; tueur place `(6,6)`,
                    adjacent a la victime et a distance 2 du porteur.
  * CONTRE-EPREUVE: victime deplacee en `(1,6)` (distance 5 du porteur) ; tueur place `(1,7)`.
                    `IsAdjacent(Owner@+0x30, Target@+0x60, 2)` doit alors REFUSER des deux cotes.

⚠ La geometrie est ASSERTIONNEE par BFS sur le `boardGraph`, jamais esperee : un montage ou la
distance ne serait pas celle qu'on croit rendrait un accord DEGENERE (les deux cotes a zero pour la
mauvaise raison).

CE QUE CE PROBE NE COUVRE PAS, et c'est ECRIT
=============================================
  * le canal DEGAT de `1365 MachineVengeance` n'est pas porte (residu #1023-r1) : le gain est
    observable par le NIVEAU de l'instance, pas par un degat ;
  * le volet `Untargetable` du `selectionType = 2` : aucune des unites du montage ne porte le flag
    `0x11`, donc ce filtre-la n'est pas SEPARE. Le choix de la valeur 2 est garde offline
    (`test_1071_...::test_MUTANT_un_gate_IsAlive_sur_la_victime_eteindrait_TOUT`).

Reproduire (depuis scripts/python, session Frida chaude) :

    python probe_1071_vengeance_for_the_omnissiah.py --state-file <ABSOLU>.json [--regime nominal]

Sorties dans `logs/` (jamais `data/`). ASCII only (cp1252). Discipline runner : `--state-file`
absolu, UN runner par regime, dispose en sortie.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PYDIR))

from rl_collect_batch import _rpc, _resolve_session                      # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.pathfinding.board import Board
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.components import StatsComponent, UnitComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import bind_live_rpc, load_state

#: Le PORTEUR : le JUMEAU NPC du summon, apparie par `visualId`. Le suffixe `:45` est le PALIER, et
#: il fait partie du nom sous lequel l'unite entre au pool.
PORTEUR = "admecNpc2Techpriest:45"
PORTEUR_VIS = "admecNpc2Techpriest"
#: La VICTIME : allie MECANIQUE du porteur (meme equipe), a 1 PV.
VICTIME = "admecDestroyer"
#: Le TUEUR : HERO du pool, MON equipe. Il n'entre dans AUCUN conjoint du passif -- le
#: `CreateTrigger` ne lit ni `OwnerIsActor` ni `OwnerIsTarget`.
TUEUR = "admecManipulus"

VENGEANCE_ID = int(TriggeredAbilityType.VengeanceForTheOmnissiah)        # 0x512 = 1298
MACHINE_VENGEANCE = int(EffectType.MachineVengeance)                     # 0x555 = 1365

BOARD, SEED = "MC1_67", "777"
#: NOMINAL : le tueur adjacent a la victime (spawn `(6,7)`) et a distance 2 du porteur (spawn `(6,8)`).
PLACE_NOMINAL = {"tueur": (6, 6)}
#: CONTRE-EPREUVE : on DEPLACE la victime loin du porteur (d = 5), tueur a cote d'elle.
PLACE_LOIN = {"victime": (1, 6), "tueur": (1, 7)}


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _bfs(board, src):
    d, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in d and (n == src or board.walkable(n)):
                d[n] = d[x] + 1
                q.append(n)
    return d


def _tile(board, u):
    p = u.get("pos") or {}
    return board.id_at(p.get("col"), p.get("row"))


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def build(state_file: Path, regime: str) -> int:
    """Monte le runner. Le SEUL ecart entre les deux regimes est une POSITION."""
    args = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
            "--state-file", str(state_file),
            "--p-units", TUEUR, "--a-units", "%s,%s" % (PORTEUR, VICTIME),
            "--explicit-stats", PORTEUR,
            # La victime DOIT mourir du premier coup : 1 PV, et aucun aleatoire de crit/block qui
            # pourrait faire diverger le replay.
            "--unit-stat", "%s:Health=1,RemainingHealth=1" % VICTIME,
            "--crit", "0,0", "--crit-target", "0,0",
            "--block-target", "0,0", "--block-player", "0,0"]
    plan = PLACE_NOMINAL if regime == "nominal" else PLACE_LOIN
    if "victime" in plan:
        args += ["--a-place", "%s:%d,%d" % (VICTIME, plan["victime"][0], plan["victime"][1])]
    args += ["--place", "%s:%d,%d" % (TUEUR, plan["tueur"][0], plan["tueur"][1])]
    p = subprocess.run(args, cwd=str(_PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        print("BUILD KO rc=%d" % p.returncode)
        print((p.stderr or "")[-1200:])
        return p.returncode
    return 0


def _effets_1365(dv, uid):
    """Les instances de `1365` LUES cote NATIF, et leur niveau. `decisionView` publie `effectLevel`
    (le champ `EffectComponent+0x68` que lit `EffectLevelFormula$$Calculate`)."""
    row = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    out = []
    for e in ((row or {}).get("effects") or []):
        if int(e.get("effectType", -1)) == MACHINE_VENGEANCE:
            out.append(int(e.get("effectLevel") or e.get("level") or 0))
    return out


def _niveau_port(state, uid) -> int:
    """La SOMME des instances non consommees -- exactement `EffectLevelFormula$$Calculate`."""
    return sum(int(getattr(e, "level", 0) or 0)
               for e in (state.effects.by_unit.get(int(uid)) or [])
               if not getattr(e, "consumed", False)
               and int(getattr(e, "effect_type", -1)) == MACHINE_VENGEANCE)


def mesurer(rid: int, rpc, regime: str) -> dict:
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return {"erreur": "boardGraph indisponible -- AUCUNE mesure n'a eu lieu"}
    board = Board(bg["tiles"], adjacency="native_sym")

    for _ in range(6):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        tu = _alive(dv, TUEUR)
        if tu is not None and dv.get("currentPlayer") == tu.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    por, vic, tue = _alive(dv, PORTEUR_VIS), _alive(dv, VICTIME), _alive(dv, TUEUR)
    if por is None or vic is None or tue is None:
        return {"erreur": "unite manquante avant la mesure -- AUCUNE mesure n'a eu lieu"}

    # GEOMETRIE ASSERTIONNEE, jamais esperee : un accord obtenu sur la mauvaise distance ne
    # prouverait rien (regime degenere).
    dpv = _bfs(board, _tile(board, por)).get(_tile(board, vic))
    dtv = _bfs(board, _tile(board, tue)).get(_tile(board, vic))
    if dtv != 1:
        return {"erreur": "geometrie: tueur/victime = %s != 1" % dtv}
    if regime == "nominal" and dpv != 1:
        return {"erreur": "geometrie NOMINALE: porteur/victime = %s != 1" % dpv}
    if regime != "nominal" and (dpv is None or dpv < 2):
        return {"erreur": "geometrie CONTRE-EPREUVE: porteur/victime = %s, attendu >= 2" % dpv}

    norm = next((x for x in (tue.get("abilities") or []) if x.get("kind") == "normal"), None)
    if norm is None:
        return {"erreur": "pas d'attaque normale sur le tueur"}

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    if getattr(state, "effects", None) is None:
        return {"erreur": "pas d'EffectsState -- le niveau serait indecidable"}

    sc = state.get_entity(por["id"]).get_component(StatsComponent)
    ctx = sc.ctx if sc is not None else None
    passifs = list(getattr(ctx, "passive_abilities", None) or [])
    if "VengeanceForTheOmnissiah" not in passifs:
        return {"erreur": "le passif n'est PAS monte cote port (passifs = %s)" % passifs}
    uc = next((u.get("unitConfig") or {} for u in (snap.get("units") or [])
               if u.get("entityId") == por["id"]), {})

    avant_nat = _effets_1365(dv, por["id"])
    avant_port = _niveau_port(state, por["id"])

    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        return {"erreur": "dumpRng KO -- pas de replay possible"}
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    state.rng = rng
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(tue["id"], vic["id"]))
    apres_port = _niveau_port(state, por["id"])
    vic_ent = state.get_entity(vic["id"])
    vuc = vic_ent.get_component(UnitComponent) if vic_ent is not None else None

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": tue["id"], "targetId": vic["id"],
        "abilityType": norm["id"]}}, 90)
    if not (isinstance(res, dict) and res.get("ok")):
        return {"erreur": "kill live KO: %s" % str(res)[:200]}
    dvi = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                               "includeInactive": True}, 90)
    vic2 = next((u for u in (dvi.get("units") or []) if u.get("id") == vic["id"]), None)
    apres_nat = _effets_1365(dvi, por["id"])

    return {"regime": regime, "d_porteur_victime": dpv, "d_tueur_victime": dtv,
            "porteur": por["id"], "victime": vic["id"], "tueur": tue["id"],
            "passifs_port": passifs,
            "plvl": uc.get("passiveAbilityLevel"), "mult": uc.get("abilityVariablesMultiplier"),
            "victime_morte_natif": bool(vic2 is not None and not vic2.get("alive")),
            "victime_morte_port": (None if vuc is None else (not vuc.alive)),
            "natif_avant": avant_nat, "natif_apres": apres_nat,
            "natif_niveau": sum(apres_nat),
            "port_avant": avant_port, "port_apres": apres_port}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--regime", default="nominal", choices=("nominal", "loin"))
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    a = ap.parse_args()

    sf = Path(a.state_file)
    if not a.no_build:
        rc = build(sf, a.regime)
        if rc:
            return rc
    if not sf.exists():
        print("ABSENT: %s" % sf)
        return 2
    rid = int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"])
    sess = _resolve_session()

    def rpc(name, params, to=90):
        return _unwrap(_rpc(sess, name, params, to))

    # CANAL AMBIANT `unitAbilityStates` (#363) : sans lui le port retomberait sur l'etat PASSIF.
    bind_live_rpc(lambda m, b=None, t=60: rpc(m, b if b is not None else {}, int(t)))

    print("runner=%d session=%s regime=%s" % (rid, sess, a.regime))
    out = mesurer(rid, rpc, a.regime)
    for k in ("erreur", "regime", "d_porteur_victime", "d_tueur_victime", "passifs_port",
              "plvl", "mult", "victime_morte_natif", "victime_morte_port",
              "natif_avant", "natif_apres", "natif_niveau", "port_avant", "port_apres"):
        if k in out:
            print("  %-22s %s" % (k, out[k]))
    rc = 3 if "erreur" in out else 0
    if rc == 0:
        attendu = 1 if a.regime == "nominal" else 0
        gain_nat = out["natif_niveau"] - sum(out["natif_avant"])
        gain_port = out["port_apres"] - out["port_avant"]
        print("  GAIN natif=%d port=%d attendu=%d" % (gain_nat, gain_port, attendu))
        if not out["victime_morte_natif"]:
            print("  VERDICT: INDECIDABLE -- la victime n'est pas morte cote natif")
            rc = 4
        elif gain_nat == gain_port == attendu:
            print("  VERDICT: ACCORD")
        else:
            print("  VERDICT: DIVERGENCE")
            rc = 1
    if not a.keep:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
            print("  runner %d dispose" % rid)
        except Exception as e:                      # noqa: BLE001 -- on DIT l'echec, on ne le tait pas
            print("  dispose KO: %s" % str(e)[:160])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
