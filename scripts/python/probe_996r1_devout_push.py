"""#996-r1 -- `1053 DevoutPush` : confrontation LIVE de la face COMBAT (attaque NORMALE + MOUVEMENT).

MONTAGE, et pourquoi CE chemin-la. Les deux porteurs de 1053 sont `templNpc1Initiate` (NPC) et
`templInitiate` (SUMMON d'ENVIRONNEMENT, invoque par `EnvFactionSummons:BlackTemplars` /
`:SpaceWolves`). Le NPC arrive par le CHEMIN DE STATS EXPLICITE (`--explicit-stats`,
#419-r1-tr12-r2) : SES stats (`units.npc[id].stats[]`), SES traits, SES armes. AUCUNE greffe.
Meme montage que `1044 IncendiaryShells` (#907), meme faction, meme fichier de port.

TROIS volets, et chacun dit ce qu'il DISCRIMINE :

  * `spawn` -- lecture des positions de spawn (sert a caler les `--a-place` des geometries).
  * `gate`  -- le masque `0x4000 TargetIsEnemy` SEUL / RANGE_ADJACENT / `RangedBool.False`,
    confronte cible par cible a l'ORACLE natif `abilityReason`
    (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`). Contrefactuels : chaque
    champ bascule doit changer au moins une ligne, sinon il est AVEUGLE et le probe le NOMME.
  * `cast`  -- UN cast, et DEUX observables independants confrontes natif/port depuis le MEME
    instantane : (1) la SEQUENCE de degat de l'attaque NORMALE, (2) la TUILE D'ARRIVEE du caster
    (le `PerformAIMovement(Caster, Direct(1), <utilite 53>)`). Puis des MUTANTS du port, chacun
    sur un `State` RECHARGE du meme instantane.

⚠ LE MOUVEMENT EST L'OBSERVABLE QUI DISCRIMINE LE PORT DE #907. Sans l'utilite 53
(`engine/utilities/devout_push.py`) ET sans la branche generique de
`engine.ai.utilities.get_movement_utility`, le scoring de tuile est PLAT, l'argmax keep-first garde
la position courante, et le caster NE BOUGE PAS -- c'est exactement le << demi-port >> que #907
refusait de livrer. Le mutant `sans_utilite` rejoue ce regime et DOIT ecarter la tuile d'arrivee.

Usage (depuis `scripts/python`) :
    python probe_996r1_devout_push.py --state-file <ABSOLU propre>            # tout
    python probe_996r1_devout_push.py --state-file <...> --volet gate
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

import hexgeo
import stream_events as SE

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.blacktemplars import DEVOUT_PUSH_ID, DevoutPushAbility
from engine.runner.components import PositionComponent
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state
from engine.utilities.utility_type import UtilityType

PYDIR = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:8765"

ABILITY = int(ActiveAbilityType.DevoutPush)                # 1053
PORTEUR = "templNpc1Initiate:45"                           # forme `<unitId>:<palier>`, VERBATIM
PORTEUR_VIS = "templNpc1Initiate"
ALLIE = "ultraTitus"
#: `eldarRanger` porte une arme RANGED (poids 50), `astraBullgryn` et `darkaCompanion` non (30) --
#: c'est ce qui rend la ventilation de l'utilite 53 NON DEGENEREE.
ENNEMIS = ("eldarRanger", "astraBullgryn", "darkaCompanion")
BOARD = "MC1_67"
SEED = "999"

#: La tuile du CASTER, DRIVEE (`--place`) : son spawn naturel `(1, 0)` de `MC1_67` est un COIN a
#: TROIS voisins, dont un occupe par l'allie -- deux candidates libres, donc un mouvement qu'aucun
#: montage ne peut rendre discriminant. `(3, 4)` a SIX voisins (mesure `probe_996r1_geometry_scout`).
#: << bloque par la geometrie de spawn >> n'est pas un verdict : on DEPLACE (runner.md).
CASTER_TILE = (3, 4)

#: GEOMETRIE, calee sur les voisinages MESURES de `(3, 4)` :
#:   (3,3) `astraBullgryn`  MELEE, ADJACENT au caster -> c'est la CIBLE du cast
#:   (5,5) `eldarRanger`    RANGED, adjacent a la SEULE candidate `(4,4)`
#:   (1,5) `darkaCompanion` MELEE,  adjacent a la SEULE candidate `(2,4)`
#: Utilite 53 attendue par candidate : (3,4) courante -10 ; (4,4) 50 (ranged) ; (4,3) 30, (2,3) 30
#: (bullgryn), (2,4) 30 (companion) ; (3,5) 0 ; (3,3) OCCUPEE. Argmax = (4,4).
#: C'est ce SPECTRE qui rend le montage non degenere : il discrimine (a) bouger vs rester,
#: (b) 50 RANGED vs 30 MELEE, (c) un comptage EN BLOC (utilite 54) qui egaliserait tout a 20.
GEOMETRIE = {"astraBullgryn": (3, 3), "eldarRanger": (5, 5), "darkaCompanion": (1, 5)}


# ------------------------------------------------------------------------------- transport

def _sid():
    return requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post("%s/api/scripts/%s/rpc" % (HOST, sid),
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(sid, state_file: str, places: dict | None, hp_target: int = 400000,
           p_places: dict | None = None) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
           "--state-file", state_file, "--explicit-stats", PORTEUR,
           "--p-units", "%s,%s" % (PORTEUR, ALLIE),
           "--a-units", ",".join(ENNEMIS),
           "--block-target", "0,0", "--crit-target", "0,0", "--crit", "0,0",
           "--hp-target", str(int(hp_target))]
    for vis, (c, r) in (places or {}).items():
        cmd += ["--a-place", "%s:%d,%d" % (vis, c, r)]
    for vis, (c, r) in (p_places or {}).items():
        cmd += ["--place", "%s:%d,%d" % (vis, c, r)]
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0 or not Path(state_file).exists():
        raise RuntimeError("build KO rc=%d : %s" % (p.returncode, (p.stderr or p.stdout)[-1500:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def _dispose(sid, rid):
    try:
        _rpc(sid, "disposeRunner", {"runnerId": int(rid)}, 60)
    except Exception as ex:                                # pragma: no cover (diagnostic)
        print("[996-r1] dispose KO : %r" % (ex,))


# ------------------------------------------------------------------------------- lecture

def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _dist(a, b):
    pa, pb = _pos(a), _pos(b)
    if None in pa or None in pb:
        return None
    return hexgeo.distance(pa, pb)


def _capture(sid, rid):
    """Instantane COMPLET : vue + etat porte + MT cale sur `dumpRng`. Le `State` est reconstruit a
    chaque appel -- c'est ce qui permet de rejouer N mutants depuis le MEME point."""
    return {"dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
            "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 60),
            "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90),
            "ab": _rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60),
            "bg": _rpc(sid, "boardGraph", {"runnerId": rid}, 60),
            "mt": _rpc(sid, "dumpRng", {"runnerId": rid}, 30)}


def _state(cap):
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, ability_states=cap["ab"])
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["mt"]["mt"])
    rng.mti = cap["mt"]["mti"]
    st.rng = rng
    return st


def _units(cap):
    return [u for u in ((cap["dv"] or {}).get("units") or []) if u.get("alive")]


def _by_vis(cap, vis):
    return next((u for u in _units(cap) if (u.get("visualId") or "") == vis), None)


def _hexi(h):
    try:
        return int(str(h), 16) if h else 0
    except ValueError:
        return 0


def _port_pos(st, uid):
    e = st.get_entity(int(uid))
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


# ------------------------------------------------------------------------------ volet SPAWN

def volet_spawn(sid, rid) -> int:
    cap = _capture(sid, rid)
    for u in sorted(_units(cap), key=lambda x: (x.get("team"), int(x["id"]))):
        print("[996-r1/spawn] id=%-4s team=%s vis=%-20s pos=%s" %
              (u["id"], u.get("team"), u.get("visualId"), _pos(u)))
    return 0


# ------------------------------------------------------------------------------- volet GATE

def _oracle(sid, rid, caster_id, cible_id):
    """`abilityReason.targetReason.hex` = `IdunBattle.Core.Services.TargetingQuery$$
    GetInvalidTargetReason` cote NATIF. `0x1 ValidRequest` = refus EN AMONT du filtre de cible
    (l'oracle n'a pas evalue le masque) -> la ligne est ECARTEE, jamais comptee en accord."""
    r = _rpc(sid, "abilityReason", {"runnerId": rid, "casterId": int(caster_id),
                                    "abilityType": ABILITY, "targetId": int(cible_id)}, 60)
    return _hexi(((r or {}).get("targetReason") or {}).get("hex"))


def volet_gate(sid, rid, geometrie: str, options=None) -> int:
    """`options` != None -> CONTREFACTUEL : le masque de la classe est remplace le temps de la
    mesure. Un champ bascule qui ne change AUCUNE ligne est un temoin AVEUGLE, et il est NOMME."""
    from engine.runner.abilities import targeting as T
    cap = _capture(sid, rid)
    caster = _by_vis(cap, PORTEUR_VIS)
    st = _state(cap)
    ability = DevoutPushAbility()
    ancien = DevoutPushAbility.TARGETING_OPTIONS
    if options is not None:
        DevoutPushAbility.TARGETING_OPTIONS = options
    lignes, ko = [], 0
    try:
        for u in sorted(_units(cap), key=lambda x: int(x["id"])):
            uid = int(u["id"])
            nat = _oracle(sid, rid, caster["id"], uid)
            if nat == 0x1:
                continue
            prt = int(T.get_invalid_target_reason(st, int(caster["id"]), uid, ability) or 0)
            ok = (nat == prt)
            ko += 0 if ok else 1
            lignes.append((u.get("visualId"),
                           "ALLIE" if u.get("team") == caster.get("team") else "ENNEMI",
                           _dist(caster, u), nat, prt, ok))
    finally:
        DevoutPushAbility.TARGETING_OPTIONS = ancien
    for vis, side, d, nat, prt, ok in lignes:
        print("[996-r1/gate/%s] %-18s %-6s d=%-3s natif=%-12s port=%-12s %s"
              % (geometrie, vis, side, d, hex(nat), hex(prt), "OK" if ok else "DIVERGE"))
    print("[996-r1/gate/%s] accord %d/%d" % (geometrie, len(lignes) - ko, len(lignes)))
    return ko


# ------------------------------------------------------------------------------- volet CAST

def _montants_natifs(res, ability_ids=None):
    """SEQUENCE coup par coup du NATIF, resolue PAR NOM (`SE.step_id`). L'attaque de 1053 est une
    attaque NORMALE dispatchee : ses `UnitDamaged` NE portent PAS `Active_Ability_Type = 1053`,
    donc on ne filtre PAS dessus -- on prend tous les `UnitDamaged` du cast."""
    out = []
    for act in ((res or {}).get("actions") or []):
        for e in (act.get("events") or []):
            if e.get("step") != SE.step_id("UnitDamaged"):
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if "Amount" in t:
                out.append((int(t["Amount"]), int(t.get("Target_Id", -1)),
                            t.get("Active_Ability_Type")))
    return out


def _port_cast(cap, caster, cible, patch=None):
    """Rejoue le port sur un `State` RECHARGE de `cap`. `patch` = un callable (mutant) applique sur
    le module d'ability, restaure ensuite."""
    import engine.runner.abilities.blacktemplars as BT
    st = _state(cap)
    runner = Runner(st).install_default_handlers(20)
    ancien = BT.devout_push_tree
    if patch is not None:
        BT.devout_push_tree = patch
    try:
        runner.apply(ActiveAbilityMessage(int(caster), int(cible), ABILITY))
    finally:
        BT.devout_push_tree = ancien
    diag = runner.ability_handler.last or {}
    atk = (diag.get("attack") or {}).get("attack") or {}
    # `extras` = tout ce que le cast declenche HORS de l'arbre de 1053 : les `after_hit` du vecteur
    # `On(0x26 = NormalAttack)` (passifs du caster) et les `after_move` (overwatch de l'ennemi que
    # le deplacement reveille). Ils ne sont PAS l'observable du port de 1053 -- ils sont VENTILES
    # pour que la comparaison ne mette jamais un total agrege en face d'un total agrege.
    extras = []
    for e in ((diag.get("attack") or {}).get("after_hit") or []):
        extras.append(("after_hit", e))
    for m in ((diag.get("move") or {}).get("moved") or []):
        for e in (m.get("after_move") or []):
            extras.append(("after_move", e))
    return {"per_hit": [int(x) for x in (atk.get("per_hit") or [])],
            "pos": _port_pos(st, caster),
            "move": diag.get("move"),
            "extras": extras}


def _mutants():
    """MUTANTS du port. Chacun change UNE grandeur LUE au decompile ; celui qui n'ecarte pas
    l'observable est un temoin AVEUGLE, et il est NOMME."""
    from engine.entities.behaviours import op_add
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.dsl.base import Const
    from engine.runner.abilities.behaviours.ai_control import PerformAIMovement
    from engine.runner.abilities.behaviours.combat import UseActiveAbility
    from engine.runner.abilities.behaviours.lifecycle import Kill
    from engine.runner.abilities.blacktemplars import (DEVOUT_PUSH_MOVE_RANGE,
                                                       DEVOUT_PUSH_MOVE_UTILITY,
                                                       devout_push_dead_units_on_target_tiles)

    def _t(utilite=DEVOUT_PUSH_MOVE_UTILITY, portee=DEVOUT_PUSH_MOVE_RANGE, avec_move=True):
        def build():
            atk = UseActiveAbility(Caster(), Target())
            kill = Kill(Caster(), devout_push_dead_units_on_target_tiles())
            if not avec_move:
                return op_add(atk, kill)
            return op_add(op_add(atk, kill),
                          PerformAIMovement(Caster(), Const(portee), override_utility=utilite))
        return build

    return [
        # LE mutant qui separe ce port du << demi-port >> refuse par #907.
        ("sans_utilite (override_utility=None -> scoring PLAT)", _t(utilite=None)),
        ("sans_move (noeud [C] retire -- l'arbre de #907)", _t(avec_move=False)),
        ("utilite=54 RammingSpeed (comptage EN BLOC, pas par armement)",
         _t(utilite=(int(UtilityType.RammingSpeed_MostAdjacentEnemies),))),
        ("range=0 (budget de deplacement nul)", _t(portee=0)),
    ]


def _mutants_utilite():
    """MUTANTS de la FEUILLE 53 elle-meme (et non de l'arbre) : ils basculent UN champ LU
    (les deux poids, le litteral -10) et doivent ecarter la tuile d'arrivee. Chacun est pose par
    substitution d'attribut de CLASSE, donc restaure a la fin."""
    from engine.utilities.devout_push import DevoutPush_AdjacentRangedEnemies as U

    def _swap():
        return {"WEIGHT_KEY_RANGED": U.WEIGHT_KEY_MELEE, "WEIGHT_KEY_MELEE": U.WEIGHT_KEY_RANGED}

    return [
        ("poids INVERSES (ranged<->melee)", _swap()),
        ("cle RANGED inconnue (TryGetValue -> 0)", {"WEIGHT_KEY_RANGED": "__ABSENTE__"}),
        ("cle MELEE inconnue (TryGetValue -> 0)", {"WEIGHT_KEY_MELEE": "__ABSENTE__"}),
    ]


def volet_cast(sid, rid, regime: str) -> int:
    cap = _capture(sid, rid)
    caster = _by_vis(cap, PORTEUR_VIS)
    cibles = [u for u in _units(cap) if u.get("team") != caster.get("team")]
    cibles.sort(key=lambda u: (_dist(caster, u) or 99, int(u["id"])))
    cible = cibles[0]
    p0 = _pos(caster)
    print("[996-r1/cast/%s] caster=%s pos=%s cible=%s(%s) d=%s"
          % (regime, caster["id"], p0, cible["id"], cible.get("visualId"), _dist(caster, cible)))
    for u in cibles:
        print("[996-r1/cast/%s]    ennemi %-18s id=%-4s pos=%s d=%s"
              % (regime, u.get("visualId"), u["id"], _pos(u), _dist(caster, u)))

    port = _port_cast(cap, caster["id"], cible["id"])
    res = _rpc(sid, "applyAction", {"runnerId": rid,
                                    "action": {"kind": "ability", "casterId": int(caster["id"]),
                                               "targetId": int(cible["id"]),
                                               "abilityType": ABILITY}}, 240)
    a0 = ((res or {}).get("actions") or [{}])[0]
    dmg = _montants_natifs(res)
    apres = _capture(sid, rid)
    caster2 = _by_vis(apres, PORTEUR_VIS)
    p1 = _pos(caster2) if caster2 is not None else None

    print("[996-r1/cast/%s] natif ok=%r mutated=%r actionConsumed=%r"
          % (regime, a0.get("ok"), a0.get("mutated"), a0.get("actionConsumed")))
    # VENTILATION, jamais un total agrege : l'arbre de 1053 ne produit QUE l'attaque NORMALE
    # dispatchee (`Active_Ability_Type` = le type d'attaque normale du porteur). Les autres
    # `UnitDamaged` du cast viennent d'AUTRES mecanismes (`Passive_Ability_Type` = un passif du
    # caster reveille par `On(NormalAttack)` ; `Effect_Type` = un overwatch reveille par le
    # DEPLACEMENT) -- ils sont HORS de ce port, et les confondre ferait fitter un scalaire.
    attaque = [d[0] for d in dmg if d[2] is not None]
    autres = [d for d in dmg if d[2] is None]
    print("[996-r1/cast/%s] natif attaque normale = %r" % (regime, attaque))
    print("[996-r1/cast/%s] port  attaque normale = %r" % (regime, port["per_hit"]))
    for m, t, _k in autres:
        print("[996-r1/cast/%s] natif HORS ARBRE     : %d -> cible %s (tags %s)"
              % (regime, m, t, "cf. probe_996r1_events_diag"))
    for src, e in port["extras"]:
        r = (e or {}).get("result") or {}
        print("[996-r1/cast/%s] port  HORS ARBRE     : %s %r -> %r"
              % (regime, src, (e or {}).get("effect") or (e or {}).get("ability"),
                 r.get("per_hit")))
    print("[996-r1/cast/%s] natif position %s -> %s" % (regime, p0, p1))
    print("[996-r1/cast/%s] port  position %s -> %s" % (regime, p0, port["pos"]))

    ko = 0
    if attaque != port["per_hit"]:
        print("[996-r1/cast/%s] DIVERGE ATTAQUE : natif=%r port=%r" % (regime, attaque,
                                                                       port["per_hit"]))
        ko += 1
    if p1 != port["pos"]:
        print("[996-r1/cast/%s] DIVERGE MOUVEMENT : natif=%s port=%s" % (regime, p1, port["pos"]))
        ko += 1
    if p1 == p0:
        print("[996-r1/cast/%s] ATTENTION : le NATIF n'a pas bouge -- le montage ne discrimine "
              "PAS le mouvement (regime DEGENERE, cf. runner.md)." % regime)

    print("[996-r1/cast/%s] -- MUTANTS DE L'ARBRE (State RECHARGE du MEME instantane) --" % regime)
    for nom, fabrique in _mutants():
        m = _port_cast(cap, caster["id"], cible["id"], patch=fabrique)
        mord = (m["per_hit"] != port["per_hit"]) or (m["pos"] != port["pos"])
        print("[996-r1/cast/%s]   %-52s pos=%s degats=%r -> %s"
              % (regime, nom, m["pos"], m["per_hit"], "MORD" if mord else "AVEUGLE"))

    print("[996-r1/cast/%s] -- MUTANTS DE LA FEUILLE 53 --" % regime)
    from engine.utilities.devout_push import DevoutPush_AdjacentRangedEnemies as U
    for nom, champs in _mutants_utilite():
        anciens = {k: getattr(U, k) for k in champs}
        try:
            for k, v in champs.items():
                setattr(U, k, v)
            m = _port_cast(cap, caster["id"], cible["id"])
        finally:
            for k, v in anciens.items():
                setattr(U, k, v)
        mord = (m["pos"] != port["pos"])
        print("[996-r1/cast/%s]   %-52s pos=%s -> %s"
              % (regime, nom, m["pos"], "MORD" if mord else "AVEUGLE"))
    return ko


# ------------------------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--volet", choices=("spawn", "gate", "cast", "tout"), default="tout")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner a la fin")
    a = ap.parse_args()
    sid = _sid()
    ko = 0
    if a.volet in ("spawn", "tout"):
        rid = _build(sid, a.state_file, GEOMETRIE, p_places={PORTEUR: CASTER_TILE})
        try:
            ko += volet_spawn(sid, rid)
        finally:
            if not a.keep:
                _dispose(sid, rid)
    if a.volet in ("gate", "tout"):
        from dataclasses import replace
        from engine.runner.abilities.targeting import (RANGE_FROM_CONFIG, RANGED_BOOL_TRUE,
                                                       TargetingOptions)
        from engine.runner.abilities.targeting_rule import TargetingRule as TR
        rid = _build(sid, a.state_file, GEOMETRIE, p_places={PORTEUR: CASTER_TILE})
        try:
            ko += volet_gate(sid, rid, "REEL")
            base = DevoutPushAbility.TARGETING_OPTIONS
            # CONTREFACTUELS : chacun bascule UN champ LU au ctor. Un champ dont la bascule ne
            # change AUCUNE ligne est AVEUGLE sur cette geometrie -- imprime, jamais tu.
            for nom, opt in (("range=RANGE_FROM_CONFIG", replace(base, range=RANGE_FROM_CONFIG)),
                             ("force_melee=RangedBool.True",
                              replace(base, force_melee_target=RANGED_BOOL_TRUE)),
                             ("rules sans TargetIsEnemy",
                              replace(base, rules=TR.None_)),
                             ("rules + TargetIsFriendly",
                              replace(base, rules=base.rules | TR.TargetIsFriendly)),
                             ("TARGETING_OPTIONS = None", None)):
                n = volet_gate(sid, rid, "CF:" + nom, options=opt)
                print("[996-r1/gate] contrefactuel %-32s -> %s"
                      % (nom, ("%d ligne(s) ecartee(s)" % n) if n else "AVEUGLE"))
        finally:
            if not a.keep:
                _dispose(sid, rid)
    if a.volet in ("cast", "tout"):
        rid = _build(sid, a.state_file, GEOMETRIE, p_places={PORTEUR: CASTER_TILE})
        try:
            ko += volet_cast(sid, rid, "hp400000")
        finally:
            if not a.keep:
                _dispose(sid, rid)
    print("PROBE %s" % ("OK" if ko == 0 else "KO (%d ecart(s))" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
