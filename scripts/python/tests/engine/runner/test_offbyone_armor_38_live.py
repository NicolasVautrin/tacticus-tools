"""#38 -- CLIQUET sur le montage EXACT du residu « off-by-one (+1) a armure > 0 » (rngcrit-1202).

CE QUE CE FICHIER VERROUILLE, et qui n'est verrouille NULLE PART AILLEURS : les DEUX vecteurs
d'attaque de `custoKyrus` (Tyrith) -- le montage d'ou le residu a ete extrait -- dans le MEME
regime perce-dominant, avec la MEME cible et le MEME pipeline.

  * vecteur ATTAQUE NORMALE  -> `damage_ops/normal.py::execute` (reduce-then-roll : les CELLULES
    sont materialisees, puis le tirage se fait dedans) ;
  * vecteur ABILITY 1202 `VigilanceEternal` -> `damage_ops/ability.py::execute_ability_attack`
    (roll-then-reduce : le tirage BRUT est materialise APRES reduction, coup par coup).

Les gardes existantes couvrent chacune UN SEUL de ces deux etages, et par un AUTRE canal :
`test_normal_attack_bounds_rounding_live.py` (darkaAzrael, armure NATURELLE) pour le vecteur
normal ; `test_heavy_grav_cannon_live.py` (garde 3) pour le vecteur ability, mais via le canal
`extraPierceRatio` de l'effet `HeavyGravCannon` -- si cet effet bouge, la garde se skippe et
l'etage n'est plus tenu. Ici le percage est celui du PROFIL (`Power` = 40 %), sans aucun effet :
c'est le chemin generique.

LA LOI NATIVE (lue au decompile, jamais deduite du live) -- dernier etage de
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, le
MULTIPLICATEUR (slot 0x10 ->
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) :

    v = Fix64.Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ;
    sinon `FixMath.NET.Fix64$$Round(v, AwayFromZero)`        <-- ARRONDI, pas troncature

Une TRONCATURE (`FixMath.NET.Fix64$$op_Explicit`) produit exactement `port = live - 1` sur tout
coup dont la fraction est >= .5 : c'est LA signature du symptome de la fiche (port `[918,903,1112]`
vs live `[919,904,1113]`). Chaque test verrouille donc les QUATRE points :
  (1) le regime EST discriminant (les deux materialisations donnent des per-coup DIFFERENTS) ;
  (2) ARRONDI == live ;
  (3) TRONCATURE != live (sinon la garde est aveugle) ;
  (4) le port TEL QU'IL EST LIVRE == live (le cliquet : une regression vers la troncature
      rougit ici, pas seulement dans la comparaison de lois).

MONTAGE : `--armor-target 6000` (levier R6) arme la branche PERCAGE du plancher
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
= le SEUL regime ou le degat reduit reste FRACTIONNAIRE. `--hp-target` est ajoute APRES pour que
la cible encaisse les 3 coups sans ecretage letal : dans `rl_duel.py` le bloc `--armor-target`
s'execute APRES celui de `--hp-target`, donc l'armure choisie SURVIT (l'assert `armor > 0` du
test l'attrape si cet ordre change). `--crit 0,0` / `--block-target 0,0` : une seule variable.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _pierce_floor_regime import (pierce_dominant_regime, drive,  # noqa: E402,F401
                                  live_amounts)

ATTACKER = "custoKyrus"          # Tyrith : 3 coups melee, profil Power (PiercingRatio 40), cc=0
TARGET = "necroWarden"           # cible du montage d'origine : mono-membre, ni block ni bouclier
ABILITY = 1202                   # VigilanceEternal (3 coups, MEME profil Power)
ARMOR = 6000                     # branche PERCAGE dominante (cf. en-tete)
BIG_HP = 300000                  # anti-ecretage letal (le dernier coup doit rester libre)


def _replay(dv, ob, snap, board, rng0, caster_id, target_id, ability_id, moved):
    """Rejoue le MEME coup TROIS fois sur le MEME etat et le MEME flux MT, en ne faisant varier
    QUE la materialisation finale : `floor` (troncature FORCEE), `round` (arrondi FORCE) et
    `shipped` (le port TEL QU'IL EST LIVRE, aucun forcage).

    Le patch vise les globals du MODULE PORTEUR du vecteur (#169 : `damage_ops` est un PACKAGE --
    patcher son `__init__` serait un NO-OP SILENCIEUX, les trois rejeux rendraient la meme chose ;
    c'est l'assert de discrimination qui l'attrape). Le vecteur ABILITY passe par le registre
    (`ActiveAbilityMessage` -> `VigilanceEternalAbility`), donc la garde tient la route REELLE du
    moteur, pas un appel fabrique."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.services.damage_modifiers import apply_all_modifiers as _aam
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability

    mod = _dnormal if ability_id is None else _dability

    def _one(force):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, caster_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        per_hit: list = []
        o_aam = mod.apply_all_modifiers
        o_eaa = AttackDamageOperation.execute_ability_attack
        if force is not None:
            mod.apply_all_modifiers = (
                lambda v, m, round_materialize=False: _aam(v, m, round_materialize=force))
        if ability_id is not None:
            def _rec(*a, **kw):
                out = o_eaa(*a, **kw)
                if out:
                    per_hit.extend(out.get("per_hit") or [])
                return out
            AttackDamageOperation.execute_ability_attack = staticmethod(_rec)
        try:
            runner = Runner(st).install_default_handlers(20)
            if ability_id is None:
                runner.apply(AttackUnitMessage(caster_id, target_id))
                last = getattr(getattr(runner, "damage_handler", None), "last", None)
                per_hit = list((last or {}).get("per_hit") or [])
            else:
                runner.apply(ActiveAbilityMessage(caster_id=caster_id, target_id=target_id,
                                                  ability_type=ability_id))
            return per_hit
        finally:
            mod.apply_all_modifiers = o_aam
            AttackDamageOperation.execute_ability_attack = o_eaa

    return {"floor": _one(False), "round": _one(True), "shipped": _one(None)}


def _run_discriminating(rpc, pierce_dominant_regime, seeds, ability_id):
    """Balaye `seeds` et rend le PREMIER cas DISCRIMINANT (troncature != arrondi).

    POURQUOI un balayage et pas un seed fige : le vecteur ABILITY est en roll-then-reduce -- ce
    qui tombe de part et d'autre de .5 est la fraction du TIRAGE BRUT, donc du flux MT, donc du
    seed. Figer un seed rendrait la garde VERTE-AVEUGLE le jour ou l'etat de depart change (c'est
    exactement ce qui est arrive au premier jet de ce fichier : seed 4242 -> 3 coups a fraction
    < .5, les deux lois coincident et la garde ne prouvait plus rien). Le vecteur NORMAL, lui,
    est reduce-then-roll : ses cellules ne dependent que de (base, pierce, armure), donc tout
    seed discrimine -- le balayage y est un simple filet."""
    tried = []
    for seed in seeds:
        live, models = _run(rpc, pierce_dominant_regime, seed, ability_id)
        tried.append((seed, models["floor"], models["round"]))
        if models["floor"] != models["round"]:
            print(f"\n[#38] seed discriminant = {seed} (essais: {tried})")
            return live, models
    pytest.skip(f"aucun seed discriminant parmi {seeds} : {tried} -- toutes les fractions "
                f"tombent < .5 sur ces flux MT ; elargir la liste ou monter --armor-target")


def _run(rpc, pierce_dominant_regime, seed, ability_id):
    """Montage commun aux deux vecteurs : build perce-dominant, DRIVE au contact (le gate
    `Not(IsAdjacent)` de 1202 est alors FERME -> le cast se reduit a l'attaque, comparable coup a
    coup avec le vecteur normal), capture, coup LIVE, puis rejeu offline des 3 materialisations."""
    reg = pierce_dominant_regime(seed, ATTACKER, TARGET, armor=ARMOR,
                                 extra=["--hp-target", str(BIG_HP)])
    rid, board = reg["rid"], reg["board"]
    caster_id, target_id, moved = drive(rpc, rid, board, ATTACKER, TARGET)
    if caster_id is None:
        pytest.skip(f"{ATTACKER} n'a pas atteint {TARGET} au contact")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cst = next((u for u in (dv.get("units") or []) if u.get("id") == caster_id), None)
    if ability_id is None:
        norm = next((a for a in ((cst or {}).get("abilities") or [])
                     if a.get("kind") == "normal"), None)
        if norm is None:
            pytest.skip("pas d'attaque normale")
        live_ability = norm["id"]
    else:
        live_ability = ability_id
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id,
        "abilityType": live_ability}}, 120)
    if not (isinstance(res, dict) and res.get("ok")):
        pytest.skip(f"coup live KO: {str(res)[:140]}")
    live, dirty = live_amounts(res, target_id)
    if not live:
        pytest.skip("aucun degat live attribue")
    if dirty:
        pytest.skip("coup non propre (crit/block/evade) -- l'etage materialise n'est pas isole")
    models = _replay(dv, ob, snap, board, rng0, caster_id, target_id, ability_id, moved)
    return live, models


def _assert_rounding(vector: str, live, models):
    """Les QUATRE verrous (cf. en-tete). Formule les messages en CHIFFRES : un echec doit dire
    quelle loi le natif suit desormais, pas seulement « ca ne matche pas »."""
    floor, rnd, shipped = models["floor"], models["round"], models["shipped"]
    print(f"\n[#38/{vector}] live={live}")
    print(f"[#38/{vector}] TRONCATURE={floor}  ARRONDI={rnd}  LIVRE={shipped}")
    assert floor != rnd, (
        f"regime NON discriminant ({floor}) : les deux materialisations coincident -- monter "
        f"l'armure (--armor-target) ou choisir un couple (base, pierce) dont la reduction tombe "
        f"sur une fraction >= .5, sinon la garde ne prouve rien")
    assert rnd == live, (
        f"ARRONDI {rnd} != live {live} : l'etage `Fix64.Round(Mul(v, multiplier), AwayFromZero)` "
        f"de `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` "
        f"a-t-il change de loi ?")
    assert floor != live, (
        f"la TRONCATURE reproduit AUSSI le live ({floor}) : la garde est AVEUGLE sur ce montage")
    assert shipped == live, (
        f"le port LIVRE {shipped} != live {live} (l'arrondi force, lui, matche : {rnd}) -- "
        f"REGRESSION : le vecteur {vector} a cesse de materialiser par arrondi. C'est EXACTEMENT "
        f"le residu #38 (port = live - 1 a armure > 0, ex. [918,903,1112] vs [919,904,1113])")


SEEDS = ("777", "4242", "31337", "555")     # cf. `_run_discriminating`


def test_normal_attack_materialization_is_round_live(live_session, rpc, pierce_dominant_regime):
    """Vecteur ATTAQUE NORMALE (reduce-then-roll) : les CELLULES reduites sont ARRONDIES."""
    live, models = _run_discriminating(rpc, pierce_dominant_regime, SEEDS, None)
    _assert_rounding("normal", live, models)


def test_vigilance_eternal_materialization_is_round_live(live_session, rpc,
                                                         pierce_dominant_regime):
    """Vecteur ABILITY bounds-mode (roll-then-reduce, famille ATTACK) : la valeur BRUTE tiree est
    reduite PUIS ARRONDIE, coup par coup. Route REELLE du moteur (registre 1202)."""
    live, models = _run_discriminating(rpc, pierce_dominant_regime, SEEDS, ABILITY)
    _assert_rounding("ability-1202", live, models)
