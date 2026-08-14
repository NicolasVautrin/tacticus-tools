"""#1050-r1 -- CONFRONTATION LIVE de l'ELARGISSEMENT MULTI-CIBLE de l'attaque normale d'`AncientFury`.

`AncientFury_NormalAttackAbility$$GetTarget` (vslot `0x4a8`) rend `Target op_Addition
ConditionalSelector(IsMeleeAttack, <adjacents des DEUX>, <adjacents de la cible ET anneau EXACT
autour du caster>)`, et `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` donne a CHAQUE
cible du selecteur l'attaque d'ARME COMPLETE. Le port n'avait AUCUN chemin multi-cible sur
l'attaque normale.

## Ce que ce probe MESURE, et pourquoi il ne peut pas se fitter

Un REPLAY-DIFF d'attaque normale (meme etat, meme MT cale par `dumpRng`), lu **DELTA DE PV PAR
UNITE** -- jamais un total. Deux etages separes :

    etage 1 -- QUI est frappe ?      -> le SET des unites qui perdent des PV
    etage 2 -- COMBIEN sur chacune ? -> le delta, unite par unite

Et le montage porte sa propre CONTRE-EPREUVE dans le meme plan : `A_OUT` est adjacente a la cible
primaire **exactement comme** `A_IN`, mais elle est a distance 1 du caster la ou `A_IN` est a
distance 2. L'anneau (`Surrounding(d) - Surrounding(d-1)`) doit donc frapper `A_IN` et **PAS**
`A_OUT`. Un port qui aurait lu un DISQUE au lieu d'un anneau frapperait les deux ; un port qui
n'aurait rien elargi n'en frapperait aucune. Les trois verdicts sont distincts.

## Le montage -- et ce qui echoue EN SILENCE si on l'oublie

* la greffe passe par `catalog_inject.write_grafted_seed_bc`, pas par `--unit-stat
  "X:PassiveAbilities=[...]"` : ce dernier n'ecrit QUE `BC.Units[].PassiveAbilities`, et une config
  d'ability absente de `BC.Abilities.PassiveAbilities` fait faillir le cast en « system error »
  (meme verrou que #226/#237/#478) ;
* `unitAbilityStates` est OBLIGATOIRE au chargement offline : sans lui
  `UnitContext.passive_abilities` reste `None` et `engine.services.custom_normal_attack` retombe
  sur le KIT gameconfig, qui ne connait PAS la greffe -- le port conclurait « aucune substitution »
  et le probe lirait un faux zero (vice #419-r1-tr14-r5) ;
* une unite alliee INERTE garde le tour OUVERT : sans elle le cast termine le tour, l'IA joue, et
  la regeneration necron rend les PV que l'elargissement vient de prendre (garde du #478) ;
* le porteur greffe est `necroWarden` : arme RANGED de portee 3, donc a distance 2 de la cible
  `FindAttackWeapon` choisit bien l'arme a distance, ce qui exerce la branche FAUSSE du
  `ConditionalSelector` (l'anneau). C'est la branche que l'i2 decrit par << exactly 2 hexes away >>.

⚠ CE QUE LA GREFFE NE COUVRE PAS, et qu'il faut lire dans tout verdict : les stats, traits et armes
du VRAI porteur (`ultraSmnDreadnought` << Galatian >>, summon UNIQUE, trait `BigTarget`). Ce probe
juge le CIBLAGE et la STRUCTURE (une attaque d'arme complete par cible), qui ne lisent ni stats ni
traits du caster -- les deux cotes utilisent la MEME arme du MEME greffon. Il ne juge pas ce que
l'empreinte multi-hex de Galatian ferait de l'ecart `CasterTile`/`CasterTiles` (#478-r1).

Usage :
    python scripts/python/probe_1050r1_ancient_fury_widened.py --state-file <ABSOLU>.json
        [--board MC1_67] [--seed 4463111] [--runner N]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine.entities.pathfinding.board import Board              # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent      # noqa: E402
from engine.runner.messages import AttackUnitMessage              # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister            # noqa: E402
from engine.runner.runner import Runner                           # noqa: E402
from engine.runner.snapshot import load_state                     # noqa: E402

import probe_446_r3b_fealty_talon_asymetrie as R3B                # noqa: E402

MontageError = R3B.MontageError
BOARD = R3B.BOARD
SEED = R3B.SEED
HP = 90000            # personne ne meurt : l'anneau frappe avec l'ARME COMPLETE, plusieurs fois

CASTER = "necroWarden"        # le porteur GREFFE -- arme RANGED portee 3
WITNESS = "eldarRanger"       # TEMOIN : arme RANGED portee 3, attaque normale NON substituee
INERT = "astraBullgryn"       # allie INERTE : garde le tour ouvert apres le cast
TARGET = "necroDestroyer"     # la cible PRIMAIRE (adverse)
A_IN = "necroSpyder"          # adjacente a la cible, a distance 2 du caster -> DANS l'anneau
A_OUT = "astraCreed"          # adjacente a la cible, a distance 1 du caster -> HORS (soustraite)

PASSIVE = "AncientFury"
PASSIVE_ID = int(TriggeredAbilityType.AncientFury)                      # 1256
NORMAL_ATTACK_ID = int(ActiveAbilityType.AncientFury_NormalAttack)      # 1162


# --------------------------------------------------------------------------- geometrie OFFLINE

def find_layout_melee(elev: dict, playable: set) -> "dict | None":
    """Le plan de la branche VRAIE du `ConditionalSelector` -- `AdjacentEnemies(Caster@0x48) &
    AdjacentUnits(Target@0x60)`, l'i2 << adjacent to both the target and Galatian >>.

    Contraintes, au sens NATIF (`bq.is_adjacent`, porte d'elevation) :

        C      adjacent T                       -> `FindAttackWeapon` choisit l'arme de MELEE
        A_IN   adjacent T  ET  adjacent C       -> DANS  l'intersection
        A_OUT  adjacent T  ET  PAS adjacent C   -> HORS  (c'est la CONJONCTION qui l'ecarte)

    Ce plan porte donc sa contre-epreuve : `A_OUT` est adjacente a la cible EXACTEMENT comme
    `A_IN`, et seule l'ancre CASTER les separe. Un port qui aurait lu `AdjacentUnits(Target)` seul
    frapperait les deux ; un port sans elargissement n'en frapperait aucune.

    ⚠ Ce regime n'a AUCUNE ligne de tir a satisfaire -- tout est au contact. C'est ce qui le rend
    montable la ou le regime RANGED ne l'est pas (cf. `find_layout_ranged`)."""
    cells = sorted(playable)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    ordered = sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    for t in ordered:
        e0 = elev.get(t)
        ring = [q for q in hexgeo.neighbors(t[0], t[1])
                if q in playable and elev.get(q) == e0 and bq.is_adjacent(t, q, elev)]
        if len(ring) < 3:
            continue
        for c in ring:
            ins = [q for q in ring if q != c and bq.is_adjacent(q, c, elev)]
            outs = [q for q in ring if q != c and not bq.is_adjacent(q, c, elev)]
            if not ins or not outs:
                continue
            used = {t, c, ins[0], outs[0]}
            wit = next((q for q in ordered
                        if q not in used and elev.get(q) == e0
                        and hexgeo.distance(q, t) == 2 and hexgeo.distance(q, c) > 1), None)
            inert = next((q for q in ordered
                          if q not in used and q != wit
                          and hexgeo.distance(q, t) > 3 and hexgeo.distance(q, c) > 3), None)
            if wit is None or inert is None:
                continue
            return {"C": c, "T": t, "A_IN": ins[0], "A_OUT": outs[0], "WITNESS": wit,
                    "INERT": inert, "elev": e0, "regime": "melee"}
    return None


def find_layout_ranged(elev: dict, playable: set) -> "dict | None":
    """Le plan qui SEPARE l'anneau du disque, purement geometrique (aucune constante de board).

    Contraintes, toutes verifiees au sens NATIF (`bq.is_adjacent`, porte d'elevation) ET en
    distance hex NUE (celle que lit `DSLFormulas$$MinDistance` -> `PositionComponent$$Distance` ->
    `CubeCoordinate$$Distance`, sans porte) :

        hexdist(C, T)     == 2      -> `FindAttackWeapon` choisit l'arme A DISTANCE (portee 3)
        A_IN  adjacent T  et hexdist(C, A_IN)  == 2   -> DANS  `Surrounding(2) - Surrounding(1)`
        A_OUT adjacent T  et hexdist(C, A_OUT) == 1   -> HORS  (c'est la SOUSTRACTION qui l'ecarte)

    On exige en plus une ELEVATION UNIFORME sur les quatre tuiles : la porte d'elevation de
    l'adjacence native et la distance hex nue de `MinDistance` sont deux regles DIFFERENTES, et un
    plan a relief melangerait les deux causes dans un seul verdict."""
    cells = sorted(playable)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    ordered = sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    for c in ordered:
        e0 = elev.get(c)
        for t in ordered:
            if elev.get(t) != e0 or hexgeo.distance(c, t) != 2:
                continue
            ring = [q for q in hexgeo.neighbors(t[0], t[1])
                    if q in playable and elev.get(q) == e0 and bq.is_adjacent(t, q, elev)]
            ins = [q for q in ring if hexgeo.distance(c, q) == 2 and q != c]
            outs = [q for q in ring if hexgeo.distance(c, q) == 1 and q != c]
            # ⚠ MESURE, pas precaution : au premier plan retenu, `C=(3,4)` et `T=(1,4)` etaient
            # ALIGNES, donc l'UNIQUE tuile a distance 1 des deux etait `(2,4)` -- exactement la ou ce
            # plan pose `A_OUT`. Le tireur n'avait plus de ligne, `FindAttackWeapon` rendait `null`,
            # et `ALoki_NormalAttackAbility$$ExecuteBehaviour` NO-OPAIT (`ok: true, mutated: false`,
            # un seul evenement `group 12` sans le moindre coup). On exige donc DEUX tuiles
            # intermediaires : `A_OUT` en occupe une, l'autre reste libre pour la ligne de tir.
            if not ins or len(outs) < 2:
                continue
            # LIGNE DE TIR, verifiee OFFLINE sur le meme service que le port
            # (`BattleQuery$$IsTargetTileObscured`) : l'elevation uniforme des QUATRE tuiles du plan
            # ne dit RIEN des tuiles INTERMEDIAIRES, et une seule tuile haute entre le tireur et sa
            # cible suffit a faire rendre `null` a `FindAttackWeapon` -- donc a faire NO-OPER
            # l'ability sans erreur.
            ins = [q for q in ins if not bq.is_target_tile_obscured(c, q, elev)]
            if not ins or bq.is_target_tile_obscured(c, t, elev):
                continue
            # LE TEMOIN : une unite ALLIEE, RANGED, NON greffee, a la MEME distance de la cible que
            # le porteur. Il repond a la question que le porteur seul ne peut pas trancher -- << le
            # natif refuse-t-il de tirer parce que l'attaque normale SUBSTITUEE est melee-only, ou
            # parce que la geometrie de ce plan ne le permet pas ? >>. Sans lui, un `fromHere` vide
            # se lirait comme un fait sur `AncientFury`, alors qu'il peut n'etre qu'un fait sur le
            # plan.
            wit = next((q for q in ordered
                        if q not in (c, t, ins[0], outs[0])
                        and elev.get(q) == e0
                        and hexgeo.distance(q, t) == 2 and hexgeo.distance(q, c) > 1
                        and not bq.is_target_tile_obscured(q, t, elev)), None)
            inert = next((q for q in ordered
                          if q not in (c, t, ins[0], outs[0], wit)
                          and hexgeo.distance(q, t) > 3 and hexgeo.distance(q, c) > 3), None)
            if wit is None or inert is None:
                continue
            return {"C": c, "T": t, "A_IN": ins[0], "A_OUT": outs[0], "WITNESS": wit,
                    "INERT": inert, "elev": e0, "regime": "ranged"}
    return None


# --------------------------------------------------------------------------- montage

def write_seed_bc(out_path: str) -> str:
    """La GREFFE d'`AncientFury` sur `necroWarden`, par le foyer `catalog_inject` (DEUX ecritures :
    `BC.Units[].PassiveAbilities` **et** la config dans `BC.Abilities.PassiveAbilities`)."""
    import catalog_inject
    import probe_380_seed_bc_patch_survival as P380
    p, reports = catalog_inject.write_grafted_seed_bc(out_path, [f"{CASTER}:{PASSIVE}"])
    for r in reports:
        if not r.get("unitsPatched"):
            raise MontageError(f"greffe NON INSTALLEE : {r}")
    P380.assert_survives(str(p))
    return str(p)


def build(state_file: str, board: str, seed: str, lay: dict) -> int:
    bc_path = os.path.splitext(state_file)[0] + ".seedbc.json"
    write_seed_bc(bc_path)
    hp = [f"{v}:Health={HP},RemainingHealth={HP}"
          for v in (CASTER, WITNESS, INERT, TARGET, A_IN, A_OUT)]
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            "--board", board, "--seed-bc", bc_path,
            "--p-units", f"{CASTER},{WITNESS},{INERT}",
            "--a-units", f"{TARGET},{A_IN},{A_OUT}",
            "--place", f"{CASTER}:{lay['C'][0]},{lay['C'][1]}",
            "--place", f"{WITNESS}:{lay['WITNESS'][0]},{lay['WITNESS'][1]}",
            "--place", f"{INERT}:{lay['INERT'][0]},{lay['INERT'][1]}",
            "--a-place", f"{TARGET}:{lay['T'][0]},{lay['T'][1]}",
            "--a-place", f"{A_IN}:{lay['A_IN'][0]},{lay['A_IN'][1]}",
            "--a-place", f"{A_OUT}:{lay['A_OUT'][0]},{lay['A_OUT'][1]}",
            "--unit-stat", ";".join(hp)]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-1200:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def stage(rpc, rid: int, lay: dict) -> dict:
    """Installe et ATTESTE tout ce dont la mesure depend -- toute attestation manquante LEVE.

    L'attestation qui compte le plus est la SUBSTITUTION : si le natif n'a pas monte
    `AncientFury_NormalAttack` sur le greffon, ce probe mesurerait une attaque normale ordinaire et
    lirait << aucune cible additionnelle >> des DEUX cotes -- un accord en regime DEGENERE, qui ne
    prouve rien."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    player = mine[0].get("owner")
    uid, pos = {}, {}
    for v in (CASTER, WITNESS, INERT):
        u = next((x for x in mine if x.get("visualId") == v), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {v} absent du roster controle")
        uid[v] = u["id"]
        pos[v] = ((u["pos"]["col"], u["pos"]["row"]) if u.get("pos") else (None, None))
    for v in (TARGET, A_IN, A_OUT):
        u = next((x for x in units if x.get("owner") != player and x.get("visualId") == v), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {v} absent du roster adverse")
        uid[v] = u["id"]
        pos[v] = ((u["pos"]["col"], u["pos"]["row"]) if u.get("pos") else (None, None))
    want = {CASTER: lay["C"], WITNESS: lay["WITNESS"], INERT: lay["INERT"], TARGET: lay["T"],
            A_IN: lay["A_IN"], A_OUT: lay["A_OUT"]}
    for v, w in want.items():
        if tuple(pos[v]) != tuple(w):
            raise MontageError(f"placement NON INSTALLE : {v} en {pos[v]}, attendu {tuple(w)} -- "
                               f"la geometrie de la mesure serait FAUSSE, pas approximative")
    # LA SUBSTITUTION, attestee par le natif lui-meme.
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 90)
    rows = (ab or {}).get("units") or []
    if not rows:
        raise MontageError("unitAbilityStates ne rend aucune unite -- le canal des passifs MESURES "
                           "serait muet et le port retomberait sur le KIT gameconfig")
    me = next((r for r in rows if int(r.get("entityId") or -1) == uid[CASTER]), None)
    if me is None:
        raise MontageError(f"{CASTER} absent d'unitAbilityStates "
                           f"(entityIds = {[r.get('entityId') for r in rows]})")
    # ⚠ L'ATTESTATION PORTE SUR L'ATTAQUE NORMALE MONTEE, pas sur la liste des passifs -- c'est le
    # SEUL canal qui prouve que la cascade `UnitFactory$$AddNormalAttackAbility` a bel et bien
    # substitue. Un porteur dont `PassiveAbilities` contiendrait `AncientFury` sans que la cascade
    # ait monte `1162` mesurerait une attaque normale ORDINAIRE, et les deux cotes rendraient
    # << aucune cible additionnelle >> : un accord en regime DEGENERE, qui ne prouve rien.
    actives = [int(a.get("type")) for a in (me.get("actives") or []) if a.get("type") is not None]
    if NORMAL_ATTACK_ID not in actives:
        raise MontageError(f"SUBSTITUTION NON INSTALLEE : les actives de {CASTER} sont {actives}, "
                           f"attendu {NORMAL_ATTACK_ID} (`AncientFury_NormalAttack`). La greffe de "
                           f"{PASSIVE} ({PASSIVE_ID}) n'a pas ete lue par la cascade "
                           f"`UnitFactory$$AddNormalAttackAbility`")
    # LE CAST EST-IL LEGAL D'ICI ? Cette attestation manquait, et son absence a coute une mesure :
    # le natif rendait `ok: true, mutated: false` -- l'ability DEMARRE (`group 12`, source
    # `AncientFury_NormalAttack`) puis `FindAttackWeapon` rend `null` et
    # `ALoki_NormalAttackAbility$$ExecuteBehaviour` NO-OPE, sans erreur. Un probe qui ne verifie que
    # `ok` lit alors << le natif n'elargit pas >>, ce qui est FAUX.
    at = rpc("abilityTargets", {"runnerId": rid, "casterId": uid[CASTER],
                                "abilityType": NORMAL_ATTACK_ID}, 90) or {}
    row = next((u for u in (at.get("units") or []) if int(u.get("unitId") or -1) == uid[CASTER]),
               None)
    ent = next((a for a in ((row or {}).get("abilities") or [])
                if int(a.get("abilityId") or -1) == NORMAL_ATTACK_ID), None)
    here = {int(t.get("targetId")) for t in ((ent or {}).get("fromHere") or [])
            if t.get("targetId") is not None}
    if uid[TARGET] not in here:
        tous = {int(t.get("targetId")) for t in ((ent or {}).get("targets") or [])
                if t.get("targetId") is not None}
        # LE TEMOIN TRANCHE LA CAUSE : meme distance, meme cible, arme ranged EQUIVALENTE, mais
        # attaque normale NON substituee. S'il tire, c'est la SUBSTITUTION qui restreint ; s'il ne
        # tire pas non plus, c'est le PLAN.
        wt = rpc("abilityTargets", {"runnerId": rid, "casterId": uid[WITNESS],
                                    "abilityType": int(ActiveAbilityType.Loki_NormalAttack)},
                 90) or {}
        wrow = next((u for u in (wt.get("units") or [])
                     if int(u.get("unitId") or -1) == uid[WITNESS]), None)
        wh = sorted({int(t.get("targetId"))
                     for a in ((wrow or {}).get("abilities") or [])
                     for t in (a.get("fromHere") or []) if t.get("targetId") is not None})
        raise MontageError(
            f"CAST ILLEGAL D'ICI : {TARGET} (id {uid[TARGET]}) n'est pas dans `fromHere` "
            f"({sorted(here)}) ; `targets` = {sorted(tous)}. Le cast rendrait `ok: true` et "
            f"NO-OPERAIT -- la mesure serait un faux zero. TEMOIN {WITNESS} (ranged NON substitue, "
            f"a distance 2 de la cible) : fromHere = {wh} -> "
            + ("le PLAN est en cause (le temoin ne tire pas non plus)" if uid[TARGET] not in wh
               else "la SUBSTITUTION est en cause : le temoin, lui, tire"))
    return {"rid": rid, "uid": uid, "pos": pos, "player": player, "ab": ab,
            "regime": lay.get("regime")}


# --------------------------------------------------------------------------- replay-diff

def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _hp_by_id(dv) -> dict:
    return {u["id"]: int(u.get("hp") or 0)
            for u in (dv.get("units") or []) if u.get("id") is not None}


def _native_hits(a0) -> dict:
    """`{targetId: [Amount, ...]}` -- les coups NATIFS, dans l'ORDRE d'emission. Le delta de PV dit
    COMBIEN, cette ventilation dit COMMENT (et sur QUI le natif a tire en premier)."""
    out = {}
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" not in td:
            continue
        out.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return out


def _native_order(a0) -> list:
    """L'ORDRE dans lequel le natif ouvre les attaques -- la suite des `Target_Id` porteurs d'un
    `Amount`, dedupliquee en conservant la premiere apparition.

    C'est ce qui mesure le residu `#1076` : le natif trie la cible PRIMAIRE **avec** les
    additionnelles (`OrderBy` d'`AttackBehaviour$$Execute`), le port la frappe toujours en tete."""
    seen, order = set(), []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" not in td:
            continue
        t = td.get("Target_Id")
        if t not in seen:
            seen.add(t)
            order.append(t)
    return order


def replay(rpc, st: dict) -> dict:
    rid, uid = st["rid"], st["uid"]
    cid, tid = uid[CASTER], uid[TARGET]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        raise MontageError("boardGraph indisponible -- l'etat offline serait sans geometrie")
    ast = st["ab"]
    board = Board(bg["tiles"], adjacency="native_sym")
    state = load_state(dv, ob, snap, board=board, ability_states=ast)
    ae = state.get_entity(cid)
    if ae is None or ae.get_component(StatsComponent) is None:
        raise MontageError(f"{CASTER} sans StatsComponent offline -- etat non chargeable")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        raise MontageError(f"dumpRng indisponible : {str(s0)[:200]}")
    state.rng = _seed_rng(s0)

    before = _hp_by_id(dv)
    off_before = {i: (state.get_entity(i).get_component(HealthComponent).hp
                      if state.get_entity(i) is not None
                      and state.get_entity(i).get_component(HealthComponent) is not None else None)
                  for i in before}

    res = rpc("applyAction", {"runnerId": rid, "captureEvents": True,
                              "action": {"kind": "ability", "casterId": cid, "targetId": tid,
                                         "abilityType": NORMAL_ATTACK_ID}}, 120) or {}
    a0 = (res.get("actions") or [{}])[0]
    if res.get("ok") is False or a0.get("ok") is False or a0.get("error"):
        raise MontageError(f"cast live REFUSE : {str(res)[:500]}")
    if res.get("currentPlayer") is not None and res["currentPlayer"] != st["player"]:
        raise MontageError("LE TOUR A BASCULE apres le cast : le delta de PV mesurerait AUSSI le "
                           "tour adverse (regeneration, overwatch) et pas seulement le cast")
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    after = _hp_by_id(dv2)

    def _port_run(sans_registre: bool):
        """Rejoue le port sur l'etat PRE-CAST (recharge, meme MT). `sans_registre` = la
        CONTRE-EPREUVE : on vide `WIDENED_NORMAL_ATTACKS`, ce qui restaure EXACTEMENT le port
        d'AVANT cette tranche. Elle doit DIVERGER du natif -- sans quoi l'accord ci-dessus ne
        prouverait rien (il pourrait venir d'un plan sans cible additionnelle)."""
        import engine.runner.abilities.loki.ancient_fury as _AF
        st2 = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"),
                         ability_states=ast)
        st2.rng = _seed_rng(s0)
        b0 = {i: (st2.get_entity(i).get_component(HealthComponent).hp
                  if st2.get_entity(i) is not None
                  and st2.get_entity(i).get_component(HealthComponent) is not None else None)
              for i in before}
        old = _AF.WIDENED_NORMAL_ATTACKS
        if sans_registre:
            _AF.WIDENED_NORMAL_ATTACKS = {}
        try:
            rn = Runner(st2).install_default_handlers(20)
            rn.apply(AttackUnitMessage(cid, tid))
            last = rn.damage_handler.last or {}
        finally:
            _AF.WIDENED_NORMAL_ATTACKS = old
        b1 = {i: (st2.get_entity(i).get_component(HealthComponent).hp
                  if st2.get_entity(i) is not None
                  and st2.get_entity(i).get_component(HealthComponent) is not None else None)
              for i in before}
        return last, b0, b1

    rr, off_before, off_after = _port_run(False)
    _rr0, ce_before, ce_after = _port_run(True)

    def _deltas(b, a):
        return {i: int(b[i]) - int(a[i]) for i in b
                if b.get(i) is not None and a.get(i) is not None and int(b[i]) != int(a[i])}

    by_vis = {v: k for k, v in uid.items()}
    nat, off = _deltas(before, after), _deltas(off_before, off_after)
    ce = _deltas(ce_before, ce_after)
    return {"caster": cid, "target": tid,
            "nat": {by_vis.get(i, i): d for i, d in nat.items()},
            "off": {by_vis.get(i, i): d for i, d in off.items()},
            "ce": {by_vis.get(i, i): d for i, d in ce.items()},
            "nat_hits": {by_vis.get(i, i): v for i, v in _native_hits(a0).items()},
            "nat_order": [by_vis.get(i, i) for i in _native_order(a0)],
            "off_widened": [(by_vis.get(e.get("target"), e.get("target")),
                             (e.get("attack") or {}).get("per_hit"))
                            for e in (rr.get("widened_targets") or [])],
            "off_primaire_hits": (list(rr.get("per_hit") or [])
                                  + list((rr.get("additional_hits") or {}).get("per_hit") or [])),
            "off_ranged": rr.get("ranged"), "regime": st.get("regime")}


def verdict(r: dict) -> list:
    """Les CINQ crans, chacun sur une propriete DIFFERENTE. Un total juste ne peut pas les passer
    tous : le set des frappes, l'exclusion de `A_OUT`, l'accord par unite et l'ordre sont
    independants."""
    out = []
    nat_set = {v for v, d in r["nat"].items() if d > 0}
    off_set = {v for v, d in r["off"].items() if d > 0}
    out.append(("1. le natif ELARGIT bien (A_IN frappe)",
                A_IN in nat_set,
                f"nat={sorted(nat_set)}"))
    out.append(("2. le natif n'ecarte PAS l'anneau (A_OUT epargne)",
                A_OUT not in nat_set,
                f"nat={sorted(nat_set)} -- si A_OUT est frappe, c'est un DISQUE, pas un anneau"))
    out.append(("3. le PORT frappe le MEME ensemble",
                nat_set == off_set,
                f"nat={sorted(nat_set)} off={sorted(off_set)}"))
    same = all(r["nat"].get(v) == r["off"].get(v) for v in nat_set | off_set)
    out.append(("4. et les MEMES montants, unite par unite",
                same, f"nat={r['nat']} off={r['off']}"))
    ce_set = {v for v, d in (r.get("ce") or {}).items() if d > 0}
    out.append(("4bis. CONTRE-EPREUVE : le port SANS registre DIVERGE du natif",
                ce_set != nat_set,
                f"nat={sorted(nat_set)} sans_registre={sorted(ce_set)} -- s'ils coincident, "
                f"l'accord de l'etage 3 ne vient PAS de l'elargissement porte"))
    want_ranged = (r.get("regime") == "ranged")
    out.append((f"5. le port a bien pris l'arme attendue par le regime {r.get('regime')}",
                bool(r.get("off_ranged")) is want_ranged,
                f"off_ranged={r.get('off_ranged')} attendu={want_ranged} -- sinon la branche du "
                f"`ConditionalSelector` reellement mesuree n'est pas celle qu'on croit"))
    return out


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--regime", choices=("melee", "ranged"), default="melee",
                    help="branche du `ConditionalSelector` a exercer (defaut melee)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = R3B.board_geometry(args.board)
    lay = (find_layout_melee if args.regime == "melee" else find_layout_ranged)(elev, playable)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucun plan {args.regime} sur {args.board}")
    rid = args.runner or build(args.state_file, args.board, args.seed, lay)
    st = stage(rpc, rid, lay)
    print(f"runner {rid} | board {args.board} seed {args.seed}")
    print(f"  plan C={lay['C']} T={lay['T']} A_IN={lay['A_IN']} A_OUT={lay['A_OUT']} "
          f"(elevation uniforme {lay['elev']})")
    print(f"  greffe {CASTER} <- {PASSIVE} ({PASSIVE_ID}) -> attaque normale {NORMAL_ATTACK_ID}")

    r = replay(rpc, st)
    print("  --- DELTAS DE PV PAR UNITE ---")
    print(f"      NAT ={json.dumps(r['nat'])}")
    print(f"      PORT={json.dumps(r['off'])}")
    print(f"      PORT sans registre (contre-epreuve) ={json.dumps(r.get('ce'))}")
    print(f"      coups natifs        : {json.dumps(r['nat_hits'])}")
    print(f"      ordre natif         : {r['nat_order']}")
    print(f"      port primaire       : {r['off_primaire_hits']}")
    print(f"      port elargissement  : {r['off_widened']}")
    rc = 0
    print("  --- VERDICTS ---")
    for label, ok, detail in verdict(r):
        print(f"      [{'OK ' if ok else 'X  '}] {label}")
        if not ok:
            print(f"             {detail}")
            rc = 1
    # #1076 -- le rang de la primaire, MESURE et non suppose.
    ordre = r["nat_order"]
    if ordre and ordre[0] != TARGET:
        print(f"      [note] #1076 EXERCE : le natif ouvre sur {ordre[0]}, pas sur la primaire "
              f"({TARGET}) -- l'ordre des tirages differe du port, qui frappe la primaire en tete")
    elif ordre:
        print(f"      [note] #1076 NON exerce sur ce plan : le natif ouvre bien sur la primaire")
    return rc


if __name__ == "__main__":
    sys.exit(main())
