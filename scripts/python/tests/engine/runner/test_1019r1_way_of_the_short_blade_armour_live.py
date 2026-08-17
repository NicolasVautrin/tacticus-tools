"""#1019-r1 -- la PENETRATION D'ARMURE de `WayOfTheShortBlade_DamageBuff` (1499), BIT-EXACT.

CE QUE #1019 A LAISSE. `WayOfTheShortBladeEffect$$IgnoreArmor` = `ConfigVar(0x40 = armorIgnored,
GetAbilityState(this), cfg@+0x60)` etait LU et EXPOSE (`ignore_armor()`) mais n'atteignait PAS le
calcul : cote port, `BaseEffect.get_armor_penetration` n'est lu que par `_attacker_effect_bonuses`
-- la boucle des effets de l'ATTAQUANT -- or cet effet vit sur FARSIGHT et n'entre que par
l'agregateur d'AURA, qui n'avait aucun axe armure. Le port rendait le `+extraDmgPct %` et PAS les
`armorIgnored` points.

CE QUE LE DECOMPILE DIT, ET QUI REFUTE LE `BLOCAGE: etage` DE LA FICHE. Rien n'etait a construire.
`IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` (le corps du slot 0x16, celui que la
boucle attaquant invoque) evalue, **SOUS le test du trigger de son `EffectBonus`** -- tout le corps
vit dans la branche `trigger == true`, lu au decompile :

    bonus = <formules de l'EffectBonus>
    pen   = this.IgnoreArmor()                      # appel virtuel <vtable +0x718>
    if (pen != null) DamageBonus[+0x38] = pen.Calculate(entities)

et `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` accumule
ce `+0x38` dans `DamageModifiers+0x28`, l'axe ARMURE (`armor_eff = max(FixedArmor - pen, 0)`). La
reparation est donc la MEME forme que celle de #1008-r2 cote defenseur : lire la penetration DANS
le bloc du bonus, sans dupliquer la gate.

LE MONTAGE, et pourquoi il est ce qu'il est -- les CINQ noeuds d'`IsValidAttackForBonus` plus le
selecteur doivent TOUS ouvrir en meme temps :

    tauFarsight (3,3)   porteur, HORS POOL -> injecte au catalogue ; ADJACENT a la cible
                        -> `AmountIsGreaterThanZero(UnitsWithTrait(Friends(Owner,
                           AdjacentUnits(Target)), Hero))` (le << Owner >> de ce noeud est le
                           BENEFICIAIRE, pas le porteur : la boucle native ecrit
                           `AbilityEntities+0x18 <- chaque cible du selecteur`)
    tauCrisis   (3,2)   beneficiaire : Hero, faction Tau, arme de portee, a distance 1 de Farsight
                        (<= `range` = 2 du `SurroundingFriends`) et a distance 2 de la cible
                        -> l'attaque est RANGED (`IsRangedAttack`), profil `Pulse` (pas `Psychic`)
    necroOverlord (3,4) la cible, PV montes par `--unit-stat` (PAS `--hp-player`, qui met
                        `FixedArmor` a 0 -- or c'est precisement l'etage qu'on mesure)

CE QUI REND LE TEMOIN NON DEGENERE, ET LE TEST L'ASSERTIONNE. Une penetration d'armure n'est
observable que si la branche ARMURE de `GetDamageWithPiercing` (`max(0, d - armure, d x p/100)`)
l'emporte : sous la branche PERCAGE, `armor_eff` ne sert a rien. D'ou la CONTRE-EPREUVE JOUEE en
fin de fichier -- la MEME salve rejouee avec le seul canal ARMURE neutralise doit rendre un AUTRE
degat.

⚠ Ce fichier monte un runner : il est LIVE.
"""
from __future__ import annotations

import json

import pytest

from engine.entities.effect_type import EffectType
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

CARRIER = "tauFarsight"          # HORS POOL -> injection catalogue
BENEF = "tauCrisis"              # le beneficiaire de l'aura (Hero, Tau, arme de portee)
TARGET = "necroOverlord"         # cible vanille, PV montes
TARGET_HP = 60000
DAMAGE_BUFF = int(EffectType.WayOfTheShortBlade_DamageBuff)                # 0x5db = 1499

#: TUILES EXACTES (`--place` / `--a-place`) -- MESUREES sur `MC1_67` : `dist(F,T) = 1`,
#: `dist(C,T) = 2`, `dist(F,C) = 1`. Toute la geometrie des gates tient dans ces trois tuiles.
PLACE_CARRIER, PLACE_BENEF, PLACE_TARGET = "3,3", "3,2", "3,4"

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/way_of_the_short_blade.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/services/damage_prediction.py",
        "scripts/python/engine/services/damage_modifiers.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation BIT-EXACT du canal ARMURE de l'aura `WayOfTheShortBlade` (#1019-r1) : "
              "elle rougit si la magnitude `armorIgnored`, l'un des cinq noeuds du gate, le "
              "selecteur d'aura ou le routage vers `DamageModifiers.armor_penetration` bougent.",
}


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


@pytest.fixture(scope="module")
def farsight_seed_bc(tmp_path_factory):
    """FIXTURE NOMMEE : seed BC augmente du porteur HORS POOL -- bloc `Units` **ET** configs
    `Abilities` (sans la seconde, le porteur se deploie puis FAUTE au cast)."""
    import catalog_inject as CI
    out = tmp_path_factory.mktemp("bc1019r1") / "seed-bc-farsight.json"
    p, ajoutees, configs = CI.write_augmented_seed_bc(str(out), [CARRIER])
    if not ajoutees:
        pytest.skip("%s deja dans le seed BC ou injection impossible (%s)" % (CARRIER, configs))
    return str(p)


@pytest.fixture(scope="module")
def wotsb_case(live_session, rpc, build_runner, farsight_seed_bc):
    """FIXTURE NOMMEE ET REUTILISABLE : monte la geometrie EXACTE, joue l'attaque a distance du
    beneficiaire et rend de quoi la rejouer offline (etat AVANT + MT cale)."""
    from engine.entities.pathfinding.board import Board
    import hexgeo

    rid = build_runner("777", extra=[
        "--seed-bc", farsight_seed_bc,
        "--p-units", "%s,%s" % (CARRIER, BENEF), "--a-units", TARGET,
        "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (TARGET, TARGET_HP, TARGET_HP),
        "--a-place", "%s:%s" % (TARGET, PLACE_TARGET),
        "--place", "%s:%s" % (CARRIER, PLACE_CARRIER),
        "--place", "%s:%s" % (BENEF, PLACE_BENEF)])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq") if (isinstance(bg, dict) and bg.get("tiles")) else None

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    by_vis = {u.get("visualId"): u for u in (dec.get("units") or []) if u.get("alive")}
    if not {CARRIER, BENEF, TARGET} <= set(by_vis):
        pytest.skip("unite absente : %s" % sorted(by_vis))
    car, ben, tgt = by_vis[CARRIER], by_vis[BENEF], by_vis[TARGET]
    pos = lambda u: (u["pos"]["col"], u["pos"]["row"])                       # noqa: E731
    geo = {"F_T": hexgeo.distance(pos(car), pos(tgt)),
           "C_T": hexgeo.distance(pos(ben), pos(tgt)),
           "F_C": hexgeo.distance(pos(car), pos(ben))}

    norm = next((ab for ab in (ben.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale exposee sur %s" % BENEF)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    hp_before = next((u.get("hp") for u in (ob.get("units") or [])
                      if u.get("squadId") == tgt["id"]), None)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ben["id"], "targetId": tgt["id"],
        "abilityType": norm["id"]}}, 60)
    if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
        pytest.skip("attaque refusee : %s" % (json.dumps(res)[:300],))
    hp_after = next((u.get("hp") for u in (res.get("units") or [])
                     if u.get("squadId") == tgt["id"]), None)
    if hp_before is None or hp_after is None:
        pytest.skip("PV de la cible non mesures")
    return {"dec": dec, "ob": ob, "snap": snap, "rng": s0, "board": board, "geo": geo,
            "carrier": car["id"], "att": ben["id"], "tgt": tgt["id"],
            "hp_before": hp_before, "hp_after": int(hp_after)}


def _rejouer(case):
    state = load_state(case["dec"], case["ob"], case["snap"], board=case["board"])
    state.rng = _seed_rng(case["rng"])
    runner = Runner(state).install_default_handlers()
    runner.apply(AttackUnitMessage(case["att"], case["tgt"]))
    return state.get_entity(case["tgt"]).get_component(HealthComponent).hp, runner.damage_handler.last


def test_1019r1_la_geometrie_ouvre_bien_les_cinq_noeuds(wotsb_case):
    """Le montage est-il celui qu'on croit ? `dist(F,T) = 1` (un Hero ami ADJACENT a la cible),
    `dist(C,T) = 2` (l'attaque est a DISTANCE, pas au contact), `dist(F,C) <= 2` (le
    `SurroundingFriends(range)` du selecteur). Sans ce controle, un board qui bouge rendrait le
    fichier vert en ne mesurant plus rien."""
    g = wotsb_case["geo"]
    assert g["F_T"] == 1, "le porteur n'est pas adjacent a la cible : le 5e noeud du gate est FERME (%s)" % g
    assert g["C_T"] == 2, "le beneficiaire n'est pas a distance 2 : l'attaque serait MELEE (%s)" % g
    assert g["F_C"] <= 2, "le beneficiaire est hors du `SurroundingFriends(range=2)` (%s)" % g
    state = load_state(wotsb_case["dec"], wotsb_case["ob"], wotsb_case["snap"],
                       board=wotsb_case["board"])
    effs = state.effects.by_unit.get(wotsb_case["carrier"]) or [] if state.effects else []
    types = {int(getattr(e, "effect_type", 0) or 0) for e in effs}
    assert DAMAGE_BUFF in types, (
        "1499 absent de l'etat offline du porteur (effets vus : %s)" % sorted(types))


def test_1019r1_le_degat_offline_reproduit_le_live_a_lunite(wotsb_case):
    """CONFRONTATION : meme etat, meme MT, meme attaque -- les PV de la cible doivent coincider."""
    hp, last = _rejouer(wotsb_case)
    print("\n[1019-r1] cible hp %s -> live %s | offline %s | pierce=%s armor=%s per_hit=%s"
          % (wotsb_case["hp_before"], wotsb_case["hp_after"], hp,
             (last or {}).get("pierce"), (last or {}).get("armor"), (last or {}).get("per_hit")))
    assert hp == wotsb_case["hp_after"], (
        "PV cible offline %s != live %s (live dmg=%s, offline dmg=%s). Le canal ARMURE de l'aura "
        "`WayOfTheShortBladeEffect$$IgnoreArmor` n'est pas -- ou mal -- porte."
        % (hp, wotsb_case["hp_after"], wotsb_case["hp_before"] - wotsb_case["hp_after"],
           wotsb_case["hp_before"] - hp))


def test_1019r1_le_canal_ARMURE_seul_change_le_degat_contre_epreuve_jouee(wotsb_case, monkeypatch):
    """CONTRE-EPREUVE JOUEE, et elle isole le canal ARMURE **seul** (le canal POURCENT, lui, etait
    deja porte) : on neutralise `aura_armor_penetration_for_ally` et le degat DOIT changer.

    Sans ce cran, le fichier serait vert dans un regime ou la branche PERCAGE de
    `GetDamageWithPiercing` domine -- l'armure effective n'y sert a rien, et la penetration non
    plus."""
    from engine.entities.effects.loki import way_of_the_short_blade as W
    nominal, last = _rejouer(wotsb_case)
    monkeypatch.setattr(W.WayOfTheShortBladeDamageBuffEffect, "aura_armor_penetration_for_ally",
                        lambda self, ctx=None: None)
    mutant, last_m = _rejouer(wotsb_case)
    print("[1019-r1] contre-epreuve : nominal hp=%s (armor=%s) | mutant hp=%s (armor=%s)"
          % (nominal, (last or {}).get("armor"), mutant, (last_m or {}).get("armor")))
    assert nominal != mutant, (
        "neutraliser le canal ARMURE ne change RIEN au degat : le regime est DEGENERE (branche "
        "PERCAGE dominante, ou la penetration ne remonte pas jusqu'au calcul). Ce test ne mesure "
        "alors pas ce qu'il croit.")
    assert nominal == wotsb_case["hp_after"], "le bras nominal doit rester celui qui matche le live"
