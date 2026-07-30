#!/usr/bin/env python
"""probe #316 -- la PREDICTION d'une ability lit-elle les TRAITS DE LA CIBLE, comme la normale ?

QUESTION BINAIRE : contre une cible portant `BigTarget`, la prediction portee de `MartialInspiration`
(1191) applique-t-elle le meme multiplicateur d'attaquant que l'attaque NORMALE du meme caster ?

## Le natif -- UN SEUL builder, aucun aiguillage par ability

`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction(state,
entities, activeEffects)` est appele via le slot de vtable 0xd depuis
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` -- le MEME corps pour l'attaque normale
et pour une ability. Il ne recoit AUCUN identifiant d'ability : il itere les effets ACTIFS et evalue
leurs arbres DSL contre l'`AbilityEntities` qu'on lui passe. Les gates de trait de la CIBLE y sont
donc des noeuds `IdunBattle.Entities.Triggers.HasTraitTrigger$$Evaluate` qui resolvent l'entite du
selecteur `Target` (`factory+0x178`) puis appellent `IdunBattle.Entities.UnitExtensions$$HasTrait`.

Deux de ces gates sont portes par le MEME caster de ce montage, `custoBladeChampion` <<Kariyan>> :

  * `IdunBattle.Entities.Effects.Loki.BeastSlayer_ExtraDmgEffect$$CreateDamageModifier`
    = `ForPercentIncrease(OwnerIsCaster & IsMeleeAttack
                          & (HasTrait(target, 0x3f9 = BigTarget) | HasTrait(target, 0x405 = Vehicle)),
                          ConfigConst(0xf = beastSlayerExtraDmgPct))` ;
  * `IdunBattle.Entities.Effects.Loki.MartialKatah_DmgBonusEffect$$CreateEffectDamageBonusForAttack`
    = `ForPercentIncrease(OwnerIsCaster & HasTrait(target, 2 = Summon),
                          Direct(GetNumberConstant(0xf = martialKatahExtraDmgPct)))`.

Les deux pourcentages sont LUS de gameconfig (`trait_variable`), jamais ecrits en dur ici.

## Le port -- le gap, et ou il est

`engine/playbook/prediction/normal_attack.py::make_normal_attack_predictions` threade
`target_traits=_entity_traits(scene, tgt_id)` vers `calculate_attacker_modifiers_for_prediction`.
`engine/playbook/prediction/abilities.py::generate_multi_hit_attack_prediction` -- le per-cible de
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
par ou passent TOUTES les abilities a degat -- ne le threadait PAS. Le defaut `None` de
`BaseEffect.create_effect_damage_bonus_for_attack` signifie " cible inconnue ", donc AUCUN bonus :
la degradation est SILENCIEUSE et UNILATERALE (le port sous-estime).

C'est un FORK prediction<->combat : la face COMBAT du meme vecteur ability passe deja
`target_traits` (`engine/runner/operations/damage_ops/ability.py`). Le port ANNONCAIT donc moins que
ce qu'il EXECUTE.

## Le montage (fixture nommee `TARGET_TRAIT_ABILITY_FIXTURE`)

Un SEUL couple caster/cible, une SEULE variable : la ligne `Traits` de la CIBLE, posee au build par
`--unit-stat <cible>:Traits=<json>`. Le champ `BC.Units[].Traits` est le substrat que
`BaseUnitComponent+0x40` recoit au deploiement -- c'est donc le trait REEL de l'entite en bataille,
pas une substitution de canal cote port : le NATIF le voit aussi, et c'est ce qui rend la
confrontation possible.

  bras `none`      -> Traits []            : aucun gate ouvert          -> facteur 1.00 (temoin)
  bras `BigTarget` -> Traits ["BigTarget"] : BeastSlayer, 1re branche   -> facteur 1.20
  bras `Vehicle`   -> Traits ["Vehicle"]   : BeastSlayer, 2de branche   -> facteur 1.20
  bras `Summon`    -> Traits ["Summon"]    : MartialKatah               -> facteur 2.00

Les DEUX facteurs sont differents PAR CONSTRUCTION : un correctif qui " recollerait " un x1.2
constant tomberait sur le bras `Summon`, et un correctif qui recollerait x2 tomberait sur les deux
autres. C'est le second cas discriminant -- le meme etage, sur la meme unite, predit une valeur
DIFFERENTE selon le bras.

Deux controles de MONTAGE, pas des modifications du mecanisme sous test :
  * `PassiveAbilities=[]` des deux cotes -- un passif porte parfois un terme que le port n'a pas
    (`ModifiedExoarmour_LikesMovingPerTile`, #27-r1), ce qui ferait diverger natif et port pour une
    raison ETRANGERE au gate teste ;
  * `--crit 0,0 --block-target 0,0` -- la prediction reste sur son scenario deterministe.

## Ce qui est mesure par bras

  * `aiPlaybookPredict(1191)`  = `<Ability>Playbook.MakeDamagePredictions` NATIF invoque en direct
    (l'oracle per-ability, PAS `aiPredict` qui est Attack-based quel que soit l'abilityType) ;
  * la meme prediction OFFLINE (`make_damage_predictions`) ;
  * les MEMES deux mesures pour l'attaque NORMALE -- TEMOIN DE CONTRASTE : elle traverse deja le
    gate, donc elle prouve, bras par bras, que le trait est bien pose et bien VU par le natif. Sans
    ce temoin, un bras ou rien ne bouge serait indiscernable d'un trait mal pose ;
  * `pairUtility(1191)` natif -- la consequence a l'etage utilite (informative, non assertee ici).

## Verdicts

  V1 MONTAGE      : la ligne `traits` MESUREE de la cible == le bras demande, dans les 4 bras ;
  V2 CONTRASTE    : l'attaque NORMALE portee == oracle natif dans les 4 bras (elle traversait deja) ;
  V3 LA MESURE    : la prediction 1191 portee == oracle natif dans les 4 bras ;
  V4 DISCRIMINANT : les facteurs NATIFS mesures sur 1191 valent bien {1.00, 1.20, 1.20, 2.00} --
                    donc DEUX magnitudes distinctes. Un port plat (l'AVANT) rend 1.00 partout.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_316_ability_prediction_target_traits.py
    python probe_316_ability_prediction_target_traits.py --board C3_01 --seed 777 --target ultraCalgar

ASCII only (cp1252). Sorties sous `logs/` (relatif au checkout). Dispose SES runners.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

CARRIER = "custoBladeChampion"    # Kariyan -- BeastSlayer ET MartialKatah, normale melee + 1191
TARGET = "necroWarden"            # mannequin : ses `Traits` sont LE curseur du montage
BOARD = "MC1_67"
SEED = 3081
RANK = 17
MARTIAL_INSPIRATION = 1191
ABILITY_NAME = "MartialInspiration"

STATE = ROOT / "logs" / "runners" / "probe_316_target_traits.json"

# Les 4 regimes. `traits` va VERBATIM dans `BC.Units[].Traits` de la cible ; `gate` nomme l'effet
# d'attaquant que le bras ouvre (documentation, pas un parametre). Le facteur ATTENDU n'est PAS
# ecrit ici : il est derive de gameconfig par `expected_factors()` -- un litteral serait un hardcode
# qui survivrait a un rebalancement du jeu.
#
# !! `--unit-stat` separe les CHAMPS par une virgule : une valeur JSON ne peut donc pas en contenir.
#    D'ou un seul trait par bras -- ce qui est exactement ce qu'on veut (un gate a la fois).
ARMS = (
    ("none", [], None),
    ("BigTarget", ["BigTarget"], "BeastSlayer_ExtraDmg"),
    ("Vehicle", ["Vehicle"], "BeastSlayer_ExtraDmg"),
    ("Summon", ["Summon"], "MartialKatah_DmgBonus"),
)

# TROISIEME volet -- un AUTRE caster, une AUTRE ability, et surtout un AUTRE CANAL.
#
# Les deux gates de la fixture principale sont des `ForPercentIncrease` : ils entrent dans le
# `%-list` des `DamageModifiers`. Valider le threading sur ce seul canal laisserait ouverte la
# possibilite qu'on ait generalise a tort un mecanisme MULTIPLICATIF. `CondemnorStake_ExtraDmg`
# (`IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
# = `ForAddition(OwnerIsActor & HasTrait(target, 0x3ea = Psyker), ConfigVar(8 = extraDmg,
# GetAbilityState, EffectSource))`) est un ADDITIF -- slot `DamageModifiers+0x10`, ajoute a la base
# AVANT percage puis scale une fois par le `%-list` (`attacker_additive_pre`). Un canal, une
# arithmetique et un placement DIFFERENTS.
#
# Porteur : `adeptCanoness` <<Roswitha>>, passif `CondemnorStake` ; ability testee
# `BrazierOfHolyFire` (1041, RANGED 2 coups, profil Flame) -- donc AUSSI une nature de coup
# differente (l'ability de la fixture principale est MELEE).
#
# !! Ici les passifs du caster NE SONT PAS retires : c'est le passif qui POSE l'effet. Le controle
#    de montage de la fixture principale (`PassiveAbilities=[]`) supprimerait le mecanisme teste.
ADDITIVE_CARRIER = "adeptCanoness"
ADDITIVE_ABILITY = (1041, "BrazierOfHolyFire")
ADDITIVE_ARMS = (
    ("none", [], None),
    ("Psyker", ["Psyker"], "CondemnorStake_ExtraDmg"),
)
# PV du mannequin sur ce volet -- assez hauts pour que la prediction ne soit JAMAIS plafonnee par
# les PV restants (cf. `scenario_additive`). Ce n'est pas une valeur de gameplay.
ADDITIVE_HP = 400000


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def expected_factors() -> dict:
    """Facteur de degat attendu par bras, DERIVE de gameconfig (`trait_variable`), jamais ecrit en
    dur. `beastSlayerExtraDmgPct` et `martialKatahExtraDmgPct` sont les deux `ConfigConst 0xf` lus
    par les deux `Create*ForAttack` cites en tete."""
    from engine.entities.effects.magnitude import trait_var
    bs = trait_var("BeastSlayer", "beastSlayerExtraDmgPct")
    mk = trait_var("MartialKatah", "martialKatahExtraDmgPct")
    if bs is None or mk is None:
        raise RuntimeError("gameconfig muet : beastSlayerExtraDmgPct=%r martialKatahExtraDmgPct=%r"
                           % (bs, mk))
    return {"none": 1.0, "BigTarget": 1.0 + bs / 100.0, "Vehicle": 1.0 + bs / 100.0,
            "Summon": 1.0 + mk / 100.0}


# ---------------------------------------------------------------- harnais runner
def _build(sid, traits, board: str, seed: int, state_file: Path, target: str,
           carrier: str = CARRIER, strip_carrier_passives: bool = True,
           extra_stats=()) -> int:
    """Monte le runner d'UN bras. `traits=None` -> AUCUN patch de `Traits` : la cible garde ceux de
    son kit (c'est le volet "cible REELLE", cf. `scenario_real`). Chaque build REMPLACE le scope de
    CE `--state-file` : le runner enregistre dans ce fichier est dispose par `rl_duel build`
    lui-meme, les freres des autres agents sont intouches.

    `strip_carrier_passives=False` GARDE les passifs du caster : indispensable quand le gate teste
    est POSE par un passif (volet `CondemnorStake` / `adeptCanoness`), ou le controle de montage de
    la fixture principale supprimerait le mecanisme meme qu'on mesure.

    NE PAS effacer le state-file avant le build (lecon #308) : l'effacer prive `rl_duel build` du
    runnerId a remplacer, donc chaque bras FUIRAIT un runner et saturerait `MAX_RUNNERS`. On verifie
    a la place que le runnerId a bien CHANGE -- ce qui detecte aussi un state-file perime."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    prev = None
    if state_file.exists():
        try:
            prev = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
        except Exception:                                   # noqa: BLE001  (fichier illisible)
            state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", str(RANK),
           "--p-units", carrier, "--a-units", target,
           "--crit", "0,0", "--block-target", "0,0",
           "--unit-stat", "%s:PassiveAbilities=[]" % target]
    if strip_carrier_passives:
        cmd += ["--unit-stat", "%s:PassiveAbilities=[]" % carrier]
    if traits is not None:
        cmd += ["--unit-stat",
                "%s:Traits=%s" % (target, json.dumps(traits, separators=(",", ":")))]
    for spec in extra_stats:
        cmd += ["--unit-stat", spec]
    proc = subprocess.run(
        cmd, cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO (traits=%r) : %s"
                           % (traits, (proc.stderr or proc.stdout or "")[-600:]))
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    if prev is not None and rid == prev:
        raise RuntimeError("build KO (traits=%r) : le state-file rend encore le runner %d : %s"
                           % (traits, prev, (proc.stderr or proc.stdout or "")[-600:]))
    return rid


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _by_visual(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis:
            return u
    return None


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _normal_attack_id(dv, uid):
    """Id CONCRET de l'attaque normale du caster (`kind == "normal"` de `decisionView`) -- PER-UNITE,
    jamais le 17 generique (cf. `NormalAttackType@0x28`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    for a in ((u or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return a.get("id")
    return None


def _adjacent_free(brd, center, occupied):
    """Une tuile libre VOISINE au sens NATIF (`boardGraph.neighbours`), pas au sens hexgeo."""
    for tid in brd.neighbours(brd.id_at(*center)):
        c = brd.coord(tid)
        t = brd.by_id.get(tid) or {}
        if c and c not in occupied and t.get("walkable") and not t.get("isWall"):
            return c
    return None


def place(sid, rid, target: str, carrier: str = CARRIER):
    """Pose la GEOMETRIE : la cible est amenee AU CONTACT du caster, qui ne bouge pas. C'est requis
    par la fixture principale (1191 et l'attaque normale sont toutes deux MELEE) et compatible avec
    le volet additif (`BrazierOfHolyFire` a une portee de 2, donc le contact la satisfait aussi). Un
    placement REFUSE est CONSTATE et leve : on ne degrade pas silencieusement le montage."""
    from engine.entities.pathfinding.board import Board
    dv = _view(sid, rid)
    car, tgt = _by_visual(dv, carrier), _by_visual(dv, target)
    if car is None or tgt is None:
        raise RuntimeError("roster incomplet : carrier=%s target=%s" % (car, tgt))
    cid, tid = car["id"], tgt["id"]
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    brd = Board(bg["tiles"], adjacency="native_sym")
    occupied = {p for p in (_pos(u) for u in (dv.get("units") or [])) if p}
    cpos = _pos(car)
    spot = _adjacent_free(brd, cpos, occupied - {_pos(tgt)})
    if spot is None:
        raise RuntimeError("aucune tuile libre voisine du caster @%s" % (cpos,))
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(tid), "to": {"col": int(spot[0]), "row": int(spot[1])}}}, 90)
    dv = _view(sid, rid)
    cpos, tpos = _pos(_by_visual(dv, carrier)), _pos(_by_visual(dv, target))
    if cpos is None or tpos is None or hexgeo.distance(cpos, tpos) != 1:
        raise RuntimeError("contact NON etabli : caster @%s cible @%s" % (cpos, tpos))
    na = _normal_attack_id(dv, cid)
    if na is None:
        raise RuntimeError("aucune attaque normale (`kind == normal`) sur u%d" % cid)
    return {"caster": cid, "target": tid, "normal": na, "caster_pos": cpos}


# ---------------------------------------------------------------- mesures
def native_pred(sid, rid, cid, tid, ability):
    """ORACLE per-ability : `<Ability>Playbook.MakeDamagePredictions` natif invoque en direct.
    Rend `(min, max)` de l'event porte par la CIBLE, ou None."""
    r = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                      "abilityType": int(ability)}, 150)
    evs = [e for e in (r.get("events") or []) if e.get("targetId") == tid]
    if not evs:
        return None
    return (int(evs[0].get("healthDmgMin") or 0), int(evs[0].get("healthDmgMax") or 0))


def native_pair(sid, rid, cid, tid, ability, tile):
    r = _r(sid, "pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                "abilityType": int(ability),
                                "col": tile[0], "row": tile[1]}, 90)
    return r.get("utility")


def _scene_and_pos(sid, rid, cid):
    """`(Scene, tuile courante du caster)` -- monte comme le spine de decision (`engine.ai.context`),
    donc avec le MEME `combatSnapshot` (substrat de traits MESURE) que le moteur en decision."""
    from engine import weights as W
    from engine.ai import context as AICTX
    from engine.playbook import scene as _scene

    rpc = (lambda m, b, t=90: _r(sid, m, b, t))                   # noqa: E731
    dv = _view(sid, rid)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    pred = _scene.build_predictor(rpc, rid)
    if pred is None:
        raise RuntimeError("build_predictor KO (combatSnapshot indisponible)")
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, cid, W.load(), pred)
    mp = ctx.me.get("pos") or {}
    return ctx.scene, (mp.get("col"), mp.get("row"))


def ported_ability_pred(scene, cid, tid, here, ability=(MARTIAL_INSPIRATION, ABILITY_NAME)):
    """Prediction PORTEE de l'ability pour la cible principale (`make_damage_predictions`)."""
    from engine.playbook.prediction import abilities as PA
    evs = PA.make_damage_predictions(scene, cid, tid, ability[0], ability[1], attack_pos=here)
    for e in evs:
        if e.target == tid:
            r = e.prediction.raw_health_damage
            return (int(r.min), int(r.max))
    return None


def ported_normal_pred(scene, cid, tid, here):
    """Prediction PORTEE de l'attaque NORMALE -- le TEMOIN de contraste (elle threade deja
    `target_traits`)."""
    from engine.playbook.prediction import make_normal_attack_predictions
    ev = make_normal_attack_predictions(scene, cid, tid, here)
    if ev is None:
        return None
    r = ev.prediction.raw_health_damage
    return (int(r.min), int(r.max))


def measured_traits(sid, rid, tid) -> list:
    """La ligne `traits` de la cible telle que le CANAL la mesure (`combatSnapshot.units[].traits`,
    ids IL2CPP) -- traduite en noms. C'est ce que lisent le natif ET le port ; sans cette
    verification, un bras dont le trait n'a pas ete pose passerait pour un bras 'sans effet'."""
    from engine.entities.traits.unit_trait import trait_names_from_ids
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 150)
    for u in (snap.get("units") or []):
        if u.get("entityId") == tid and isinstance(u.get("traits"), list):
            return sorted(trait_names_from_ids(u["traits"]))
    return []


# ---------------------------------------------------------------- cellule + scenario
def measure(sid, arm, board: str, seed: int, state_file: Path, target: str,
            verbose=True, carrier: str = CARRIER,
            ability=(MARTIAL_INSPIRATION, ABILITY_NAME),
            strip_carrier_passives: bool = True, extra_stats=()) -> dict:
    """UNE cellule : monte le bras, pose la geometrie, et rend natif vs port sur les DEUX vecteurs
    -- l'ABILITY testee et l'attaque NORMALE du meme caster (le temoin de contraste)."""
    name, traits, gate = arm
    rid = _build(sid, traits, board, seed, state_file, target, carrier=carrier,
                 strip_carrier_passives=strip_carrier_passives, extra_stats=extra_stats)
    g = place(sid, rid, target, carrier=carrier)
    cid, tid, na, here = g["caster"], g["target"], g["normal"], g["caster_pos"]
    scene, spos = _scene_and_pos(sid, rid, cid)
    if spos != here:
        raise RuntimeError("tuile du caster incoherente entre decisionView %r et Scene %r"
                           % (here, spos))
    row = {"arm": name, "traits": traits, "gate": gate, "runner": rid,
           "carrier": carrier, "ability": ability[0], "ability_name": ability[1],
           "caster": cid, "target": tid, "normal": na, "caster_pos": here,
           "measured_traits": measured_traits(sid, rid, tid),
           "nat_ability": native_pred(sid, rid, cid, tid, ability[0]),
           "port_ability": ported_ability_pred(scene, cid, tid, here, ability=ability),
           "nat_normal": native_pred(sid, rid, cid, tid, na),
           "port_normal": ported_normal_pred(scene, cid, tid, here),
           "pair_ability": native_pair(sid, rid, cid, tid, ability[0], here)}
    if verbose:
        print("   bras %-10s r%-4d traits=%-22s | %-18s nat=%-14s port=%-14s | normale nat=%-14s "
              "port=%-14s | pair=%s"
              % (name, rid, ",".join(row["measured_traits"]) or "-", ability[1],
                 _p(row["nat_ability"]), _p(row["port_ability"]),
                 _p(row["nat_normal"]), _p(row["port_normal"]), _f(row["pair_ability"])))
    return row


def _p(v):
    return "None" if v is None else "[%d,%d]" % v


def _f(v):
    return "None" if v is None else ("%.4f" % v)


def scenario(board: str = BOARD, seed: int = SEED, target: str = TARGET, state_file=None,
             arms=ARMS, verbose: bool = True) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else STATE
    if verbose:
        print("=== fixture TARGET_TRAIT_ABILITY (board=%s seed=%s caster=%s cible=%s) ==="
              % (board, seed, CARRIER, target))
    rows = {}
    for arm in arms:
        rows[arm[0]] = measure(sid, arm, board, seed, sf, target, verbose=verbose)
    return {"board": board, "seed": seed, "target": target, "rows": rows,
            "arms": [a[0] for a in arms], "expected": expected_factors(),
            "state_file": str(sf)}


# CIBLES REELLES -- aucun patch de `Traits`, l'unite arrive avec ceux de son kit. Ce volet ferme le
# seul doute que le montage synthetique laisse ouvert : que patcher `BC.Units[].Traits` fabrique un
# regime artificiel. `tauCrisis` <<Re'vas>> est le porteur `BigTarget` du datapoint qui a NOMME ce
# residu (#308 / `port-residuals-inventory.md` N16) ; `necroWarden` est le temoin sans gate.
REAL_TARGETS = ("necroWarden", "tauCrisis")


def scenario_real(board: str = "C3_01", seed: int = 777, targets=REAL_TARGETS, state_file=None,
                  verbose: bool = True) -> dict:
    """Volet CIBLES REELLES : un bras par visualId, `Traits` NON patche, sur un AUTRE couple
    (board, seed) que la fixture synthetique -- donc une autre geometrie et un autre roster."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else STATE
    if verbose:
        print("=== volet CIBLES REELLES (board=%s seed=%s, Traits NON patches) ===" % (board, seed))
    rows = {}
    for t in targets:
        rows[t] = measure(sid, (t, None, "kit"), board, seed, sf, t, verbose=verbose)
    return {"board": board, "seed": seed, "target": "<real>", "rows": rows,
            "arms": list(targets), "expected": None, "state_file": str(sf)}


def scenario_additive(board: str = "C4_09", seed: int = 909, target: str = TARGET,
                      state_file=None, verbose: bool = True) -> dict:
    """Volet CANAL ADDITIF -- autre caster, autre ability, autre canal, autre nature de coup.

    `adeptCanoness` (passif `CondemnorStake`) caste `BrazierOfHolyFire` (1041, RANGED) sur un
    mannequin dont on ouvre/ferme le gate `HasTrait(target, 0x3ea = Psyker)`. Le bonus est un
    `ForAddition` (`DamageModifiers+0x10`, `attacker_additive_pre`), pas un `ForPercentIncrease` :
    ce volet interdit de conclure que le threading n'aurait ete valide que sur le canal `%-list`.

    Les passifs du caster sont CONSERVES ici (c'est le passif qui pose l'effet).

    !! Le mannequin recoit `Health`/`RemainingHealth` TRES eleves. Ce n'est pas un confort : sans
    cela le bonus tue la cible, et l'oracle natif `aiPlaybookPredict` rend alors le degat SANTE
    PLAFONNE aux PV restants (mesure : [8536, 8536] sur les DEUX vecteurs, ability ET attaque
    normale) tandis que le port rend le RAW. On comparerait deux etages differents, et le TEMOIN
    tomberait pour une raison etrangere au gate. On passe par `--unit-stat` et NON par
    `--hp-target`, qui remettrait aussi `Armor`/`FixedArmor` a 0 (piege documente, residu R8)."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else STATE
    if verbose:
        print("=== volet CANAL ADDITIF (board=%s seed=%s caster=%s ability=%s) ==="
              % (board, seed, ADDITIVE_CARRIER, ADDITIVE_ABILITY[1]))
    rows = {}
    hp = ["%s:Health=%d,RemainingHealth=%d" % (target, ADDITIVE_HP, ADDITIVE_HP)]
    for arm in ADDITIVE_ARMS:
        rows[arm[0]] = measure(sid, arm, board, seed, sf, target, verbose=verbose,
                               carrier=ADDITIVE_CARRIER, ability=ADDITIVE_ABILITY,
                               strip_carrier_passives=False, extra_stats=hp)
    return {"board": board, "seed": seed, "target": target, "rows": rows,
            "arms": [a[0] for a in ADDITIVE_ARMS], "expected": None, "state_file": str(sf)}


def verdicts_additive(res) -> int:
    """port == natif sur les deux bras, ET le natif DOIT bouger entre eux (sinon le gate n'est pas
    exerce et l'accord ne prouve rien)."""
    ok = True
    rows = res["rows"]
    print("\n=== VERDICTS (canal additif) ===")
    bad = [n for n in res["arms"] if rows[n]["port_ability"] != rows[n]["nat_ability"]]
    ok = ok and not bad
    print("  A1 prediction %s port == natif sur %d/%d bras%s"
          % (ADDITIVE_ABILITY[1], len(res["arms"]) - len(bad), len(res["arms"]),
             "" if not bad else " -- ECART sur %s"
             % {n: (rows[n]["port_ability"], rows[n]["nat_ability"]) for n in bad}))
    a2 = rows["none"]["nat_ability"] != rows["Psyker"]["nat_ability"]
    ok = ok and a2
    print("  A2 le gate EST exerce (le natif bouge entre les deux bras) : %s -> %s"
          % ({n: _p(rows[n]["nat_ability"]) for n in res["arms"]},
             "exerce" if a2 else "INERTE -- l'accord ne prouve rien sur ce volet"))
    bad = [n for n in res["arms"] if rows[n]["port_normal"] != rows[n]["nat_normal"]]
    ok = ok and not bad
    print("  A3 temoin attaque NORMALE port == natif sur %d/%d bras%s"
          % (len(res["arms"]) - len(bad), len(res["arms"]),
             "" if not bad else " -- ECART sur %s"
             % {n: (rows[n]["port_normal"], rows[n]["nat_normal"]) for n in bad}))
    print("\n%s" % ("VOLET ADDITIF OK" if ok else "VOLET ADDITIF KO -- voir les lignes ci-dessus"))
    return 0 if ok else 1


def verdicts_real(res) -> int:
    """port == natif sur les DEUX vecteurs, et le bras `BigTarget` reel n'est PAS confondu avec le
    temoin (sinon le volet ne discriminerait rien)."""
    ok = True
    rows = res["rows"]
    print("\n=== VERDICTS (cibles reelles) ===")
    bad = [n for n in res["arms"] if rows[n]["port_ability"] != rows[n]["nat_ability"]]
    ok = ok and not bad
    print("  R1 prediction 1191 port == natif sur %d/%d cibles%s"
          % (len(res["arms"]) - len(bad), len(res["arms"]),
             "" if not bad else " -- ECART sur %s"
             % {n: (rows[n]["port_ability"], rows[n]["nat_ability"]) for n in bad}))
    bad = [n for n in res["arms"] if rows[n]["port_normal"] != rows[n]["nat_normal"]]
    ok = ok and not bad
    print("  R2 temoin attaque NORMALE port == natif sur %d/%d cibles%s"
          % (len(res["arms"]) - len(bad), len(res["arms"]),
             "" if not bad else " -- ECART sur %s"
             % {n: (rows[n]["port_normal"], rows[n]["nat_normal"]) for n in bad}))
    gated = [n for n in res["arms"]
             if {"BigTarget", "Vehicle", "Summon"} & set(rows[n]["measured_traits"])]
    r3 = bool(gated) and len(gated) < len(res["arms"])
    ok = ok and r3
    print("  R3 le volet contient bien un porteur de gate ET un temoin : %s -> %s"
          % ({n: sorted(set(rows[n]["measured_traits"])
                        & {"BigTarget", "Vehicle", "Summon"}) for n in res["arms"]},
             "discriminant" if r3 else "NON DISCRIMINANT -- aucun contraste dans ce volet"))
    print("\n%s" % ("VOLET REEL OK" if ok else "VOLET REEL KO -- voir les lignes ci-dessus"))
    return 0 if ok else 1


# Les SIX effets d'attaquant dont le `create_effect_damage_bonus_for_attack` / `create_damage_
# modifier` consulte REELLEMENT `target_traits` dans son corps (les autres ne l'ont qu'en
# signature). `kind` dit par quoi le porteur l'obtient : un TRAIT du kit, ou une ABILITY.
_TARGET_TRAIT_GATES = {"BeastSlayer": "trait", "MartialKatah": "trait", "CondemnorStake": "ability",
                       "HeavyGravCannon": "ability", "DestroyTheWitch": "both",
                       "DespoiledGround": "ability"}


def inert_call_sites_report() -> dict:
    """OFFLINE, aucun runner. Re-DERIVE la confrontabilite des DEUX call-sites de prediction qui ne
    threadent toujours PAS `target_traits` -- `engine/playbook/psyker.py` (splash Psyker) et
    `engine/playbook/fury_of_the_ancients.py` (`bloodMephiston`).

    Ils sont HORS du perimetre de #316. Les laisser en l'etat n'est defendable que s'ils sont
    INERTES, c.-a-d. qu'aucun porteur d'un des six gates n'emprunte ces chemins. Cette fonction le
    MESURE au lieu de l'affirmer : le jour ou une unite Psyker gagne `BeastSlayer` (ou ou
    `bloodMephiston` gagne un de ces passifs), le compte cesse d'etre nul et le residu doit etre
    rouvert.

    Rend `{gate: {"carriers": n, "psyker_carriers": [...]}}` + la ligne `bloodMephiston`."""
    import unit_map as UM
    kits = UM.all_kits()
    out = {}
    for gate, kind in _TARGET_TRAIT_GATES.items():
        holders = []
        for k in kits:
            tr, ab = set(k.get("traits") or ()), set(k.get("abilities") or ())
            if (kind in ("trait", "both") and gate in tr) or (kind in ("ability", "both")
                                                              and gate in ab):
                holders.append(k)
        out[gate] = {"carriers": len(holders),
                     "psyker_carriers": sorted(h["id"] for h in holders
                                               if "Psyker" in (h.get("traits") or ()))}
    meph = next((k for k in kits if k["id"] == "bloodMephiston"), None)
    out["_bloodMephiston"] = {
        "gates_held": sorted(g for g, kind in _TARGET_TRAIT_GATES.items()
                             if meph is not None
                             and ((kind in ("trait", "both") and g in (meph.get("traits") or ()))
                                  or (kind in ("ability", "both")
                                      and g in (meph.get("abilities") or ()))))}
    return out


def print_inert_call_sites() -> int:
    rep = inert_call_sites_report()
    print("=== call-sites de prediction NON threades (hors perimetre #316) -- confrontabilite ===")
    tot = 0
    for gate in sorted(_TARGET_TRAIT_GATES):
        r = rep[gate]
        tot += len(r["psyker_carriers"])
        print("  %-18s porteurs=%-3d dont Psyker=%d %s"
              % (gate, r["carriers"], len(r["psyker_carriers"]), r["psyker_carriers"] or ""))
    meph = rep["_bloodMephiston"]["gates_held"]
    print("  bloodMephiston (FuryOfTheAncients) porte : %s" % (meph or "aucun de ces gates"))
    inert = (tot == 0 and not meph)
    print("\n%s" % ("psyker.py et fury_of_the_ancients.py sont INERTES sur ces gates -- les cabler "
                    "serait speculatif" if inert else
                    "UN PORTEUR EXISTE DESORMAIS -- le residu doit etre rouvert et confronte live"))
    return 0 if inert else 1


def dispose(res) -> None:
    """Dispose les runners DE CE PROBE (les bras anterieurs ont deja ete remplaces par le scope de
    CE state-file). Jamais ceux des autres."""
    sid = _resolve_session()
    for rid in sorted({r["runner"] for r in res["rows"].values()}):
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)


# ---------------------------------------------------------------- verdicts
def verdicts(res) -> int:
    ok = True
    rows, exp = res["rows"], res["expected"]
    print("\n=== VERDICTS ===")

    # V1 -- le montage pose bien le trait demande, et LUI SEUL parmi les trois gates.
    #
    # !! On ne compare PAS la mesure au litteral demande : le jeu AJOUTE des traits que
    # `BC.Units[].Traits` ne porte pas (mesure -- `Hero` apparait sur les bras `none`/`BigTarget`/
    # `Vehicle`, et disparait sur le bras `Summon`). Exiger l'egalite ferait rougir V1 pour une
    # raison etrangere au gate. Ce qui doit tenir, c'est la SEPARATION des bras : le trait demande
    # est present, et aucun des DEUX AUTRES gates ne l'est -- sinon deux bras se confondraient.
    gates = {t for _n, ts, _g in ARMS for t in ts}
    bad = []
    for n in res["arms"]:
        mes, want = set(rows[n]["measured_traits"]), set(rows[n]["traits"])
        if not want.issubset(mes) or (mes & gates) != want:
            bad.append(n)
    ok = ok and not bad
    print("  V1 montage : le bras demande est pose SEUL (parmi %s) sur %d/%d bras%s"
          % (sorted(gates), len(res["arms"]) - len(bad), len(res["arms"]),
             "" if not bad else " -- RATE sur %s (%s)"
             % (bad, {n: rows[n]["measured_traits"] for n in bad})))

    # V2 -- TEMOIN DE CONTRASTE : l'attaque normale traverse deja le gate, donc elle doit etre
    # bit-exacte partout. C'est elle qui prouve que le trait est VU par le NATIF.
    bad = [n for n in res["arms"] if rows[n]["port_normal"] != rows[n]["nat_normal"]]
    ok = ok and not bad
    print("  V2 temoin attaque NORMALE port == natif sur %d/%d bras%s"
          % (len(res["arms"]) - len(bad), len(res["arms"]),
             "" if not bad else " -- ECART sur %s"
             % {n: (rows[n]["port_normal"], rows[n]["nat_normal"]) for n in bad}))

    # V3 -- LA MESURE.
    bad = [n for n in res["arms"] if rows[n]["port_ability"] != rows[n]["nat_ability"]]
    ok = ok and not bad
    print("  V3 prediction 1191 port == natif sur %d/%d bras%s"
          % (len(res["arms"]) - len(bad), len(res["arms"]),
             "" if not bad else " -- ECART sur %s"
             % {n: (rows[n]["port_ability"], rows[n]["nat_ability"]) for n in bad}))

    # V4 -- DISCRIMINANT : le natif applique bien DEUX magnitudes distinctes sur 1191, et la
    # reference (bras `none`) est non nulle. Un port plat rendrait 1.00 partout.
    base = rows["none"]["nat_ability"]
    v4 = base is not None and base[1] > 0
    facs = {}
    if v4:
        for n in res["arms"]:
            cur = rows[n]["nat_ability"]
            v4 = v4 and cur is not None
            facs[n] = None if cur is None else cur[1] / base[1]
        for n, f in facs.items():
            v4 = v4 and f is not None and abs(f - exp[n]) <= 0.01
        v4 = v4 and len({round(v, 3) for v in facs.values()}) >= 2
    ok = ok and v4
    print("  V4 discriminant : facteurs NATIFS sur 1191 = %s (attendus %s) -> %s"
          % ({n: _f(v) for n, v in facs.items()}, {n: _f(v) for n, v in exp.items()},
             "DEUX magnitudes distinctes, derivees de gameconfig" if v4
             else "HORS REGIME -- le montage ne discrimine rien"))

    # V5 -- le port porte le MEME contraste que le natif (et pas un plat).
    pbase = rows["none"]["port_ability"]
    v5 = (pbase is not None and pbase[1] > 0
          and len({round(rows[n]["port_ability"][1] / pbase[1], 3)
                   for n in res["arms"] if rows[n]["port_ability"] is not None}) >= 2)
    ok = ok and v5
    print("  V5 le PORT porte le meme contraste : %s -> %s"
          % ({n: _p(rows[n]["port_ability"]) for n in res["arms"]},
             "non plat" if v5 else "PLAT -- la branche ability ne lit pas les traits de la cible"))

    print("\n%s" % ("PROBE OK -- la prediction d'ability lit les traits de la CIBLE, comme la normale"
                    if ok else "PROBE KO -- voir les lignes ci-dessus"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--target", default=TARGET, help="visualId du mannequin (ses Traits = curseur)")
    ap.add_argument("--real", action="store_true",
                    help="volet CIBLES REELLES (Traits NON patches) au lieu de la fixture synthetique")
    ap.add_argument("--additive", action="store_true",
                    help="volet CANAL ADDITIF (adeptCanoness / BrazierOfHolyFire vs Psyker)")
    ap.add_argument("--inert-call-sites", action="store_true",
                    help="OFFLINE : re-derive la confrontabilite des call-sites non threades")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.inert_call_sites:
        return print_inert_call_sites()
    res = None
    try:
        if a.additive:
            res = scenario_additive(board=(a.board if a.board != BOARD else "C4_09"),
                                    seed=(a.seed if a.seed != SEED else 909), target=a.target)
            return verdicts_additive(res)
        if a.real:
            res = scenario_real(board=(a.board if a.board != BOARD else "C3_01"),
                                seed=(a.seed if a.seed != SEED else 777))
            return verdicts_real(res)
        res = scenario(board=a.board, seed=a.seed, target=a.target)
        return verdicts(res)
    finally:
        if res is not None and not a.keep:
            dispose(res)
            print("(runners du probe disposes)")


if __name__ == "__main__":
    sys.exit(main())
