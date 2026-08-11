"""GARDE des DEUX actives du `necroReanimator` (MACHINE OF WAR Necrons) portees par #902 :
`1223 ReanimationBeam` et `1224 NanoscarabRepairProtocols`.

Le PROBE (`probe_902_reanimator.py`) MESURE (quatre phases, oracle natif
`abilityTargets(...).fromHere` + replay-diff offline/live) ; ces tests GARDENT ce que le port ne doit
plus jamais reperdre, en interrogeant un ORACLE (gameconfig, litteraux du ctor RELUS), jamais un
scalaire fige :

  * REGISTRE  : les deux entrees portent leur `TARGETING_OPTIONS` **et** leur `ABILITY_ATTACK_TYPE`
    (les deux cliquets a 0 manquant que notre propre cadence de portage est seule a rouvrir), avec
    les masques EXACTS lus sur chaque ctor -- `0x200040000402` / `0x40000402`, tranches par les
    XREFS entrantes vers la surcharge SEPT arguments (« flags directs »).
  * 1224      : marque UN allie mecanique NON deja marque -- effet `1545` PERMANENT + `1546` +
    `hp[level]` PV COURANTS ; le montant est RECALCULE ici depuis `gameconfig` x le multiplicateur
    de rarete de l'`AbilityState`, jamais fige.
  * 1223      : repare **toutes** les machines alliees marquees, PAS la cible du cast -- l'invariant
    qui distingue `Repairable(carriers)` de `Target()` ; et pose `1547` sur l'ACTEUR.
  * SEEDING   : `hp_max` vient de `combatSnapshot.healthMax` (max COURANT) et non d'
    `observeBattle.hpMax` (max INITIAL). Sans ce cran, une unite dont le maximum a ete releve passe
    pour PLEINE et le `Repair` de 1223 ne mord sur RIEN.

MONTAGE : porteur `lineup` HORS pool -> injection catalogue + `--p-mow`, board a slot MoW (`C1_02`).
Etat live REEL (board + stats + rng du runner), cast par le CHEMIN REEL
(`AbilityHandler.visit_ActiveAbilityMessage`). ASCII only.
"""
from __future__ import annotations

import pytest

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15). Perimetre pris
#: LARGE a dessein : les deux abilities traversent le registre, le gate de ciblage, le seeding, les
#: feuilles DSL et les Operations -- trop etroit serait un faux vert, trop large est sain.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",            # le MONTAGE : porteur hors pool
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        # PROPRE A CE FICHIER : l'arbre porte (`abilities/necrons.py`), les trois registres, le
        # SEEDING (`runner/snapshot.py` -- le cran `healthMax`), les feuilles DSL (`Repair`,
        # `ChangeStat`, `AddEffect`, `AddDynamicStatModifierEffect`, `AddStatOverrideEffect`,
        # `PerformAIAction`), les selecteurs (`Friends`, `MechanicalUnits`, `EntitiesWithAnyEffect`,
        # `Repairable`, `UnitsWithTrait`) et les Operations en dessous. Tout cela vit sous
        # `engine/**` : on prend le paquet ENTIER plutot qu'une liste qui se perimerait.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Les montants (`hp`, `hpToRepair`, `maxDmg`, `dmgPct`) et les ordinaux d'enum viennent du
        # gameconfig et du dump du build.
        "data/seed-bc.json",
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : les DEUX masques LUS sur leur ctor (0x200040000402 / 0x40000402, "
              "surcharge FLAGS DIRECTS tranchee par xrefs), les deux `AbilityAttackType.Others`, "
              "l'existence des quatre variables de config sur la BONNE ability (le `hpToRepair` de "
              "1224 appartient a l'EFFET 1545), le montant `hp[level] x multiplier` du marquage, "
              "l'invariant `Repairable(carriers)` != `Target()` (on repare une machine marquee qui "
              "n'est PAS la cible du cast, et PAS la machine non marquee meme endommagee), le cap "
              "`MaxFillUp`, l'effet 1547 sur l'ACTEUR, et le cran de seeding `combatSnapshot."
              "healthMax` (max COURANT) contre `observeBattle.hpMax` (max INITIAL).",
}

import catalog_inject
import gameconfig as GC
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.base import active_ability_state
from engine.runner.abilities.handler import ABILITY_CLASSES, AbilityHandler
from engine.runner.abilities.targeting import (RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE,
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import HealthComponent, UnitComponent
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state
from engine.entities.active_ability_type import ActiveAbilityType

REANIMATION_BEAM = int(ActiveAbilityType.ReanimationBeam)                  # 1223
NANOSCARAB = int(ActiveAbilityType.NanoscarabRepairProtocols)              # 1224
MARKER = int(EffectType.NanoscarabRepairProtocols)                         # 1545
EXTRA_HP = int(EffectType.NanoscarabRepairProtocols_ExtraHp)               # 1546
REVIVE = int(EffectType.ReanimationBeam_Revive)                            # 1547

MOW = "necroReanimator"
ALLIES = "necroOverlord,necroSpyder,necroWarden"
FOES = "ultraTitus,ultraApothecary"
BOARD = "C1_02"


def _seed_bc(tmp_path_factory):
    out = tmp_path_factory.mktemp("nrp902") / "seed-bc.json"
    path, units, abils = catalog_inject.write_augmented_seed_bc(out, [MOW])
    assert MOW in units, (units, abils)
    return str(path)


def _mk(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indispensable au montage"
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, dec


def _mow_id(dec):
    return next((int(m.get("casterId") or m.get("machineId"))
                 for m in (dec.get("mows") or []) if m.get("visualId") == MOW), None)


def _by_visual(dec, visual):
    return next((int(u["id"]) for u in (dec.get("units") or [])
                 if u.get("alive") and u.get("visualId") == visual), None)


def _cast(st, caster, target, ability):
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(caster), target_id=None if target is None else int(target),
        ability_type=int(ability)))
    return h.last or {}


def _hp(st):
    out = {}
    for eid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        hc = e.get_component(HealthComponent)
        if uc is not None and uc.alive and hc is not None and hc.hp is not None:
            out[int(eid)] = int(hc.hp)
    return out


def _porteurs(st, effect_type):
    if st.effects is None:
        return set()
    return {int(uid) for uid, effs in st.effects.by_unit.items()
            if any(int(e.effect_type) == int(effect_type) for e in effs)}


# ------------------------------------------------------------------ REGISTRE (offline pur)

def test_reanimator_registry_masks_and_attack_types_offline():
    """Les DEUX regles de registre, dans le meme test parce qu'elles se posent dans le meme commit.

    Les masques sont ecrits ICI EN CLAIR parce qu'ils sont le LITTERAL du ctor natif, pas une
    derivation : `...ReanimationBeamAbility$$.ctor` passe `0x200040000402` et
    `...NanoscarabRepairProtocolsAbility$$.ctor` `0x40000402` a la surcharge SEPT arguments de
    `IdunBattle.Core.Services.TargetingOptions$$.ctor` -- celle dont le corps ECRIT `rules` TEL QUEL
    a `options+0x28` (ni preset combine, ni copie statique). Un renumerotage de `TargetingRule`
    ferait diverger la somme des membres du litteral : c'est exactement ce que ce test garde."""
    for aid in (REANIMATION_BEAM, NANOSCARAB):
        assert ABILITY_CLASSES.get(aid) is not None, "%d doit etre dans ABILITY_CLASSES" % aid
        opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
        assert opts is not None, "%d entre au registre SANS son masque" % aid
        assert opts.range is RANGE_WHOLE_BOARD, (aid, opts.range)
        assert int(opts.force_melee_target) == RANGED_BOOL_FALSE, (aid, opts.force_melee_target)
    beam = ABILITY_CLASSES[REANIMATION_BEAM].TARGETING_OPTIONS
    nrp = ABILITY_CLASSES[NANOSCARAB].TARGETING_OPTIONS
    assert int(beam.rules) == 0x200040000402, hex(int(beam.rules))
    assert int(nrp.rules) == 0x40000402, hex(int(nrp.rules))
    # Le bit qui les SEPARE, nomme : 1223 porte `TargetIsUnit`, 1224 non ; et 1223 est SELF-CASTING.
    assert int(beam.rules) & int(TR.TargetIsUnit)
    assert not (int(nrp.rules) & int(TR.TargetIsUnit))
    assert beam.self_cast is True and nrp.self_cast is False
    # `AActiveAbility..ctor(this, &opts, 2)` sur les DEUX ctors -> 2 = Others.
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.ReanimationBeam] == AbilityAttackType.Others
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.NanoscarabRepairProtocols] == AbilityAttackType.Others


def test_reanimator_config_variables_exist_offline():
    """ORACLE gameconfig : les QUATRE `ConfigVar`/`GetVariableForLevel` lus au decompile existent, et
    chacune est bien sur l'ability que le natif interroge. `1224` lit `hp` (0x1d) -- son `hpToRepair`
    appartient a l'EFFET 1545, pas au cast, et c'est la colonne « REPAIR » de l'audit qui s'y trompe."""
    beam = (GC.ability("ReanimationBeam") or {}).get("variables") or {}
    nrp = (GC.ability("NanoscarabRepairProtocols") or {}).get("variables") or {}
    assert {"hpToRepair", "maxDmg", "dmgPct"} <= set(beam), sorted(beam)
    assert "hp" in nrp, sorted(nrp)


# ------------------------------------------------------------------ 1224 NanoscarabRepairProtocols

def test_nanoscarab_marks_and_fills_health_live(rpc, build_runner, tmp_path_factory):
    """`(statMod + hpFill) + addMarker` : l'effet 1545 PERMANENT et 1546 sur la CIBLE, et `hp[level]`
    PV COURANTS ajoutes. Le montant est l'ORACLE `gameconfig`, recalcule au niveau/multiplicateur de
    l'`AbilityState` de CETTE active sur CE caster -- jamais un scalaire."""
    rid = build_runner("777", extra=["--board", BOARD, "--seed-bc", _seed_bc(tmp_path_factory),
                                     "--p-mow", MOW, "--p-units", ALLIES, "--a-units", FOES,
                                     "--unit-stat", "necroSpyder:RemainingHealth=2000", "--no-ai"])["rid"]
    mkstate, dec = _mk(rpc, rid)
    cid, tgt = _mow_id(dec), _by_visual(dec, "necroSpyder")
    assert cid is not None, "la MoW injectee doit etre en bataille"
    assert tgt is not None, "necroSpyder doit etre en bataille"
    st = mkstate()
    level, mult = active_ability_state(st, cid, NANOSCARAB)
    from engine.entities.effects.magnitude import ability_var
    attendu = int(ability_var("NanoscarabRepairProtocols", "hp", level, multiplier_pct=mult) or 0)
    assert attendu > 0, (level, mult)

    avant = _hp(st)
    diag = _cast(st, cid, tgt, NANOSCARAB)
    apres = _hp(st)
    assert diag.get("extra_hp") == attendu, (diag.get("extra_hp"), attendu, level, mult)
    assert apres[tgt] - avant[tgt] == attendu, (apres[tgt], avant[tgt], attendu)
    assert MARKER in {e.effect_type for e in st.effects.by_unit.get(tgt, [])}
    assert EXTRA_HP in {e.effect_type for e in st.effects.by_unit.get(tgt, [])}
    # Le gate REFUSE une re-pose (`IsOwnerOfEffect ? 2 : 0`) -- et il ACCEPTE encore les autres.
    cls = ABILITY_CLASSES[NANOSCARAB]
    assert get_invalid_target_reason(st, cid, tgt, cls()) == int(TR.TargetMatchesDynamicRule)
    autre = _by_visual(dec, "necroWarden")
    if autre is not None:
        assert get_invalid_target_reason(st, cid, autre, cls()) == 0


# ------------------------------------------------------------------ 1223 ReanimationBeam

def test_reanimation_beam_repairs_marked_machines_not_the_target_live(rpc, build_runner,
                                                                     tmp_path_factory):
    """L'INVARIANT STRUCTUREL de 1223 : la reparation porte sur **`Repairable(carriers)`**, c'est-a-dire
    sur toutes les machines alliees marquees `1545`, et pas sur la cible du cast. On marque une
    machine ENDOMMAGEE et on cible une AUTRE unite : un port qui aurait lu `Target()` ne reparerait
    rien. On garde aussi les DEUX autres volets : le gate exige le marqueur, et `1547` va sur l'ACTEUR.

    ⚠ Aucun `pytest.skip` de confort : si le montage ne produit pas la configuration voulue, le test
    ECHOUE -- un skip de montage est invisible du garde #77 et rend le fichier vert a vide (#455)."""
    rid = build_runner("777", extra=["--board", BOARD, "--seed-bc", _seed_bc(tmp_path_factory),
                                     "--p-mow", MOW, "--p-units", ALLIES, "--a-units", FOES,
                                     "--unit-stat",
                                     "necroWarden:RemainingHealth=2000;necroSpyder:RemainingHealth=2000",
                                     "--no-ai"])["rid"]
    mkstate, dec = _mk(rpc, rid)
    cid = _mow_id(dec)
    marque = _by_visual(dec, "necroWarden")
    autre = _by_visual(dec, "necroSpyder")
    assert cid is not None and marque is not None and autre is not None

    st = mkstate()
    cls_beam = ABILITY_CLASSES[REANIMATION_BEAM]
    # AVANT tout marquage : AUCUNE cible n'est valide pour 1223 (le gate exige le marqueur 1545).
    for u in (dec.get("units") or []):
        if u.get("alive"):
            assert get_invalid_target_reason(st, cid, int(u["id"]), cls_beam()) != 0, u.get("visualId")

    _cast(st, cid, marque, NANOSCARAB)                 # marque `necroWarden`, PAS `necroSpyder`
    assert MARKER in {e.effect_type for e in st.effects.by_unit.get(marque, [])}
    assert get_invalid_target_reason(st, cid, marque, cls_beam()) == 0
    assert get_invalid_target_reason(st, cid, autre, cls_beam()) != 0

    avant = _hp(st)
    revive_avant = _porteurs(st, REVIVE)
    diag = _cast(st, cid, marque, REANIMATION_BEAM)
    apres = _hp(st)

    level, mult = active_ability_state(st, cid, REANIMATION_BEAM)
    from engine.entities.effects.magnitude import ability_var
    montant = int(ability_var("ReanimationBeam", "hpToRepair", level, multiplier_pct=mult) or 0)
    assert diag.get("amount") == montant, (diag.get("amount"), montant, level, mult)

    repares = {int(r["target"]) for r in (diag.get("repairs") or []) if r.get("repaired")}
    assert marque in repares, (repares, diag)
    # `EntitiesWithAnyEffect([1545])` MORD : la machine alliee NON marquee reste intacte, meme
    # endommagee -- c'est ce qui distingue le selecteur du natif d'un simple « tous les allies ».
    assert autre not in repares, (repares, "necroSpyder n'est PAS marque")
    assert apres.get(autre) == avant.get(autre)
    # Cap `FillUpStatComponent$$MaxFillUp` : on ne rend jamais plus que ce qui manque.
    hc = st.get_entity(marque).get_component(HealthComponent)
    assert apres[marque] - avant[marque] == min(montant, int(hc.hp_max) - avant[marque])
    # Volet [C] : `AddEffect(1547, targets = Actor@+0x40)` -- l'ACTEUR, ici la MoW casteuse.
    assert _porteurs(st, REVIVE) - revive_avant == {int(cid)}, (
        _porteurs(st, REVIVE), revive_avant, cid)


def test_seeding_uses_current_health_max_not_initial_live(rpc, build_runner, tmp_path_factory):
    """Le cran de SEEDING sans lequel 1223 est inerte : apres un marquage LIVE, `HealthComponent.hp_max`
    doit valoir le maximum COURANT (`combatSnapshot.healthMax`), jamais le maximum INITIAL
    (`observeBattle.hpMax`). L'ecart se mesure en CONFRONTANT les deux canaux -- on n'ecrit pas de
    valeur attendue en dur."""
    rid = build_runner("777", extra=["--board", BOARD, "--seed-bc", _seed_bc(tmp_path_factory),
                                     "--p-mow", MOW, "--p-units", ALLIES, "--a-units", FOES,
                                     "--no-ai"])["rid"]
    _mk0, dec = _mk(rpc, rid)
    cid, tgt = _mow_id(dec), _by_visual(dec, "necroSpyder")
    assert cid is not None and tgt is not None
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tgt, "abilityType": NANOSCARAB}}, 120)
    assert res.get("ok"), res

    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    initial = next((u.get("hpMax") for u in (ob.get("units") or [])
                    if int(u.get("squadId") or -1) == tgt), None)
    courant = next((u.get("healthMax") for u in (snap.get("units") or [])
                    if int(u.get("entityId") or -1) == tgt), None)
    assert initial and courant, (initial, courant)
    assert courant > initial, ("le marquage doit RELEVER le maximum, sinon le test ne discrimine "
                              "rien", initial, courant)

    mkstate, _dec2 = _mk(rpc, rid)
    st = mkstate()
    hc = st.get_entity(tgt).get_component(HealthComponent)
    assert int(hc.hp_max) == int(courant), (hc.hp_max, courant, initial)
    assert int(hc.hp) <= int(hc.hp_max), (hc.hp, hc.hp_max)
