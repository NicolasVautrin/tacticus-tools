"""VALIDATION du seed des OWNER-EFFECTS de trait au spawn d'un summon (gap traits-des-summons).

RE : `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute (boucle TRAITS) ajoute au porteur les effets de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait (dict `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor +0x30,
4 entrées LUES). `SpawnUnitOperation` mirror ce seed dans `EffectsState`. Ici on spawn des summons PORTEURS
d'un trait de la dict et on vérifie (1) l'effet seedé, (2) qu'il s'applique aux MODIFIERS d'attaque du summon
(ce que le gap ratait), + un CONTRÔLE sans trait.

State seedé depuis un build live (gameconfig réel). NON committe.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.spawn import SpawnUnitOperation, _free_tiles_adjacent
from engine.runner.damage_model import attacker_modifiers
from engine.runner.components import OwnerComponent, StatsComponent


def _load(rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq") if isinstance(bg, dict) and bg.get("tiles") else None
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dec, ob, snap, board=board)
    return state, dec


def _spawn(state, dec, visual):
    """Spawn 1 summon `visual` avec un caster réel (pour level/mult). Renvoie l'entityId.

    #455 -- LA CIBLE N'EST PAS INDIFFERENTE, et la croire l'etait a rendu ce fichier INTEGRALEMENT
    INERTE (8 skipped / 0 passed, rc 0, lu comme un succes). Le montage d'origine posait
    `target_id = caster_id` en commentant « placement indifferent (on teste les effets, pas la
    tuile) ». Il l'etait tant que le port creait l'entite PUIS lui cherchait une place ; il a cesse
    de l'etre avec `case-spawn-requires-tile` (#251), qui mirrore `IdunBattle.Entities.Behaviours.
    SpawnUnitBehaviour$$Execute` : l'entite NAIT DE L'ITERATION du tile-selecteur
    `CanAddUnit(AdjacentTiles(target))` -- zero tuile libre, zero appel a
    `IdunBattle.Operations.AddUnitOperation$$Execute`, donc **zero entite**. Le skip de secours a
    alors avale les huit tests, en silence.

    MESURE (#455, board MC1_67 / seed 777, la configuration par defaut de `build_runner`) : la
    premiere unite de `decisionView` (u77) occupe une tuile a **2 voisins**, tous deux tenus par ses
    allies -- `free = []` sur les CINQ visuals. Six des dix unites de cette bataille, elles, ont au
    moins une tuile libre au contact.

    On DERIVE donc la cible du MEME selecteur que l'operation (`_free_tiles_adjacent`, le mirror de
    `CanAddUnit(AdjacentTiles(...))`) au lieu de la supposer. Le caster, lui, reste `units[0]` : il
    ne fournit que le couple (`active_ability_level`, `ability_variables_multiplier`) qui dimensionne
    les stats du summon, et sa position n'entre que dans le `SortByDistance` aval.

    Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : aucune cible spawnable ->
    `pytest.fail`. C'est un etat qui ne se produit que si le board est sature ou si le mirror du
    selecteur rend vide -- deux vraies fautes, pas une indisponibilite du harnais."""
    units = list(dec.get("units") or [])
    if not units:
        pytest.fail("montage NON INSTALLE : decisionView ne rend aucune unite", pytrace=False)
    caster_id = units[0]["id"]
    caster = state.get_entity(caster_id)
    if caster is None or caster.get_component(StatsComponent) is None:
        pytest.fail(f"montage NON INSTALLE : caster u{caster_id} absent du state ou sans "
                    f"StatsComponent (level/mult du summon non resolvables)", pytrace=False)
    # Cible = premiere unite dont l'anneau-1 offre une tuile libre, lue par le mirror du selecteur
    # natif lui-meme. `_free_tiles_adjacent(..., native_order=True)` = `CanAddUnit(AdjacentTiles(t))`
    # dans l'ordre d'enumeration natif -- exactement ce que `SpawnUnitOperation.execute` iterera.
    ring = [(u["id"], _free_tiles_adjacent(state, u["id"], set(), native_order=True))
            for u in units if state.get_entity(u["id"]) is not None]
    target_id = next((uid for uid, free in ring if free), None)
    if target_id is None:
        pytest.fail("montage NON INSTALLE : aucune unite de la bataille n'a de tuile LIBRE au "
                    "contact -- `CanAddUnit(AdjacentTiles(target))` rend vide partout, donc "
                    f"aucun spawn n'est possible (anneaux lus : {[(u, len(f)) for u, f in ring]})",
                    pytrace=False)
    before = set(state.entities.keys())
    SpawnUnitOperation.execute(state, caster_id, target_id, "ScarabHive", visual, 1)
    new = [i for i in state.entities.keys() if i not in before]
    if not new:
        pytest.fail(f"spawn {visual} KO : `SpawnUnitOperation.execute` n'a cree aucune entite "
                    f"alors que la cible u{target_id} avait des tuiles libres au contact "
                    f"({dict(ring).get(target_id)})", pytrace=False)
    return new[0]


def _eff_names(state, uid):
    return [getattr(e, "name", None) for e in state.effects.active_effects(uid, {"hp": 1})] \
        if state.effects is not None else []


def _has_pct_bonus(state, uid, is_ranged):
    mods, _ = attacker_modifiers(state, uid, 1, is_ranged=is_ranged)
    return bool(mods is not None and getattr(mods, "pct_list", None))


def test_ranged_specialist_summon_seeds_and_applies(rpc, build_runner):
    """tauSmnStealthSuit (trait RangedSpecialist) : effet seedé + +% appliqué SEULEMENT en RANGED."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "tauSmnStealthSuit")
    names = _eff_names(state, sid)
    print(f"\n[RANGED-SPEC] summon effects={names} "
          f"ranged_bonus={_has_pct_bonus(state, sid, True)} melee_bonus={_has_pct_bonus(state, sid, False)}")
    assert "RangedSpecialist" in names, f"effet RangedSpecialist NON seedé au spawn : {names}"
    assert _has_pct_bonus(state, sid, True) is True, "bonus RANGED du trait non appliqué (gap NON corrigé)"
    assert _has_pct_bonus(state, sid, False) is False, "bonus appliqué en MELEE (gate IsRangedAttack cassée)"


def test_heavy_weapon_summon_seeds(rpc, build_runner):
    """necroSmnDeathmark (trait HeavyWeapon) : effet HeavyWeapon_ExtraDmg seedé au spawn."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "necroSmnDeathmark")
    names = _eff_names(state, sid)
    print(f"\n[HEAVY-WPN] summon effects={names}")
    assert "HeavyWeapon_ExtraDmg" in names, f"effet HeavyWeapon_ExtraDmg NON seedé : {names}"


def test_control_summon_without_trait_effect(rpc, build_runner):
    """necroSmnSwarm (Summon/LivingMetal/Mechanical/Swarm/Flying — AUCUN trait de la dict) : aucun owner-effect."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "necroSmnSwarm")
    names = _eff_names(state, sid)
    print(f"\n[CONTROL] necroSmnSwarm effects={names}")
    assert "RangedSpecialist" not in names and "HeavyWeapon_ExtraDmg" not in names, \
        f"owner-effect seedé à tort sur un summon sans trait de la dict : {names}"


def test_bigtarget_summon_seeds_via_derived_ability(rpc, build_runner):
    """tyranSmnWarrior (trait BigTarget) : BigTarget_AdjacentEffect seedé via le chemin trait->ability dérivée
    (BigTarget 0x406)->`IdunBattleLogic.Entities.Abilities.Active.Loki.BigTargetAbility$$CreateBehaviour` AddEffect(0x402). Matérialisé en CLASSE
    aura (pas un BaseEffect no-op)."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "tyranSmnWarrior")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    bt = next((e for e in effs if getattr(e, "name", None) == "BigTarget_AdjacentEffect"), None)
    print(f"\n[BIGTARGET] summon effects={names} class={type(bt).__name__ if bt else None}")
    assert bt is not None, f"BigTarget_AdjacentEffect NON seedé au spawn : {names}"
    assert type(bt).__name__ == "BigTargetAdjacentEffect", \
        f"effet materialise en {type(bt).__name__} (attendu BigTargetAdjacentEffect, pas un no-op)"
    assert hasattr(bt, "create_aura_hits_malus_for_defense"), "methode aura absente"


def test_diminutive_summon_seeds_via_derived_ability(rpc, build_runner):
    """#75 — orksGrot (trait Diminutive 0x408=1032) : `Diminutive_HitReduction` seede via le chemin
    trait->ability derivee (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility` -> TriggeredAbilityType.Diminutive
    0x43f=1087 -> `DiminutiveAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.DiminutiveAbility$$.ctor = `AOwnerEffectSpecificTriggeredAbility(0x43f)`
    IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$.ctor, `IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger` = OnOwnerSpecificAbilityInit -> AddEffect(owner)).

    GROUND TRUTH LIVE (runner 1155, orksRuntherd GetEmRuntz) : les grots spawnes portent
    `UnitStats_TriggeredAbility_Id=1087` ET l'effet `Diminutive_HitReduction` (decisionView).
    Materialise en CLASSE (pas un BaseEffect no-op) sinon la reduction de coups serait perdue."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "orksGrot")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    dim = next((e for e in effs if getattr(e, "name", None) == "Diminutive_HitReduction"), None)
    print(f"\n[DIMINUTIVE] summon effects={names} class={type(dim).__name__ if dim else None}")
    assert dim is not None, f"Diminutive_HitReduction NON seede au spawn : {names}"
    assert type(dim).__name__ == "DiminutiveHitReductionEffect", \
        f"effet materialise en {type(dim).__name__} (attendu DiminutiveHitReductionEffect, pas un no-op)"


def test_diminutive_reduces_hits_melee_and_ranged(rpc, build_runner, monkeypatch):
    """#75 — le trigger natif IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack est `OwnerIsTarget` SEUL (aucun noeud IsMelee/IsRanged, aucun
    gate de profil) : la reduction s'applique aux DEUX axes. C'est ce qui DISCRIMINE Diminutive de
    Parry (melee-only IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack) et Camouflage (ranged-only IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack) — un port qui recopierait
    l'un de ces deux jumeaux echouerait ici.

    ORACLE DE MAGNITUDE — aucune valeur figee dans ce test. Le decompile de
    `IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack`
    donne `ForAdditionWithMinimum(get_OwnerIsTarget, Direct(-AbilityConfiguration.GetNumberConstant(
    0x2c)), min=Direct(1))` : la magnitude n'est ni per-niveau ni derivee d'une stat, c'est la
    CONSTANTE de config 0x2c de l'ability Diminutive (TriggeredAbilityType 0x43f=1087) — slot seede
    depuis `globalValues.traitVariables.diminutiveHitReduction`, l'ability Diminutive n'existant pas
    dans `units.abilities`. Le test LIT cet oracle gameconfig et compare : un re-equilibrage de la
    constante deplace l'attendu AVEC le jeu, au lieu de verrouiller le port sur une mesure datee.

    DERIVATION PROUVEE : le meme calcul est rejoue avec l'oracle FORCE a une autre valeur, et le port
    doit SUIVRE. C'est ce qui separe « le port lit la config » de « le port rend 1 par coincidence » :
    les slots 0x2c voisins (`parryHitReduction`, `camouflageHitReduction_1`) valent 1 eux aussi, donc
    l'egalite numerique seule ne prouverait pas que la bonne cle est lue.

    ANCRAGE LIVE (mesure #75, runner 1155, A/B meme attaquant u83 orksBigMek arme 4 coups, ability 69,
    Attack_Weapon_IsMelee=1) : vs u77 orksRuntherd (sans Diminutive) = 4 coups ; vs u120 Grot
    (Diminutive) = 3 coups. Cette mesure etablit le SENS (le natif retranche des coups, y compris en
    melee) ; la VALEUR attendue, elle, vient de l'oracle ci-dessus."""
    import gameconfig as GC
    from engine.entities.effects import hits_malus_from_defender_effects
    red = (GC.trait("Diminutive").get("variables") or {}).get("diminutiveHitReduction")
    assert red is not None, ("oracle introuvable : globalValues.traitVariables.diminutiveHitReduction "
                             "absent de gameconfig (GetNumberConstant(0x2c) non resolvable offline)")
    red = int(red)
    assert red > 0, (f"oracle incoherent : diminutiveHitReduction={red}, or le natif construit "
                     f"Direct(-GetNumberConstant(0x2c)) -- une constante positive est attendue")
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "orksGrot")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    melee = hits_malus_from_defender_effects(effs, is_melee=True)
    ranged = hits_malus_from_defender_effects(effs, is_melee=False)
    print(f"\n[DIMINUTIVE-HITS] oracle diminutiveHitReduction={red} melee={melee} ranged={ranged}")
    assert melee == -red, f"malus MELEE attendu -{red} (oracle gameconfig), obtenu {melee}"
    assert ranged == -red, (f"malus RANGED attendu -{red} (trigger OwnerIsTarget SEUL, aucun gate "
                            f"IsMelee/IsRanged), obtenu {ranged}")
    # La magnitude doit etre DERIVEE de la config, pas gelee : on decale l'oracle, le port suit.
    bumped = red + 2
    orig_trait = GC.trait
    monkeypatch.setattr(GC, "trait", lambda tid: (
        {"id": tid, "variables": {"diminutiveHitReduction": bumped}} if tid == "Diminutive"
        else orig_trait(tid)))
    melee_b = hits_malus_from_defender_effects(effs, is_melee=True)
    ranged_b = hits_malus_from_defender_effects(effs, is_melee=False)
    print(f"[DIMINUTIVE-HITS] oracle force a {bumped} -> melee={melee_b} ranged={ranged_b}")
    assert (melee_b, ranged_b) == (-bumped, -bumped), (
        f"magnitude NON derivee de l'oracle : diminutiveHitReduction force a {bumped} rend "
        f"melee={melee_b} ranged={ranged_b} (attendu {-bumped}) -> le port lit une autre cle "
        f"(parry/camouflage ?) ou porte sa valeur en dur")


def test_control_summon_without_diminutive_keeps_hits(rpc, build_runner):
    """#75 CONTROLE — un summon SANS le trait Diminutive n'ecope d'aucun malus de coups (garde contre
    un seed pose a tort sur tout summon)."""
    from engine.entities.effects import hits_malus_from_defender_effects
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "necroSmnSwarm")     # Summon/LivingMetal/Mechanical/Swarm/Flying
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    assert "Diminutive_HitReduction" not in names, f"Diminutive seede a tort : {names}"
    for melee in (True, False):
        assert hits_malus_from_defender_effects(effs, is_melee=melee) == 0, \
            f"malus de coups non nul sur un summon sans Diminutive : {names}"


def test_shadow_in_the_warp_summon_seeds_via_derived_ability(rpc, build_runner):
    """tyranSmnWarrior (trait ShadowInTheWarp) : ShadowInTheWarp_LessDmg_Effect seede via trait->ability
    derivee (ShadowInTheWarp_AddEffectAbility)->AddEffect, materialise en classe aura de reduction
    Psychique, pas un BaseEffect no-op.

    ORACLE (magnitude ET portee lues de gameconfig, rien de fige). Decompile :
      - `IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateEffectDamageBonusForAttack`
        = `ForPercentIncrease(get_OwnerIsActor & DamageProfileIs(0xd=Psychic), ConfigConst(0x3b))`
        -> magnitude = ConfigConst 0x3b = `traitVariables.shadowInTheWarpDmgModifier` (NEGATIF : c'est
        un PercentIncrease d'une valeur negative, que le port expose en PercentDecrease de sa valeur
        absolue) ;
      - `IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateTargetSelector`
        = `SurroundingEnemies(self, ConfigConst(0x16)) & UnitsWithTrait(0x3ea) & UnitsNotFromFaction(0xc)`
        -> portee = ConfigConst 0x16 = `traitVariables.shadowInTheWarpRange`.
    Le test derive ses DEUX attendus de ces cles : l'aura est exigee a `range` et exigee ABSENTE a
    `range + 1` — ce second point est ce qui rend l'oracle discriminant (un port a portee gelee passe
    le premier volet et tombe sur le second des que la config bouge)."""
    import gameconfig as GC

    import hexgeo
    tv = GC.trait("ShadowInTheWarp").get("variables") or {}
    red_pct, rng = tv.get("shadowInTheWarpDmgModifier"), tv.get("shadowInTheWarpRange")
    assert red_pct is not None and rng is not None, (
        "oracle introuvable : traitVariables.shadowInTheWarpDmgModifier / shadowInTheWarpRange "
        f"absents de gameconfig (lu: {tv})")
    red_pct, rng = int(red_pct), int(rng)
    assert red_pct < 0, (f"oracle incoherent : shadowInTheWarpDmgModifier={red_pct} >= 0, or le natif "
                         f"construit ForPercentIncrease(ConfigConst(0x3b)) et l'effet est une "
                         f"REDUCTION -- le port l'expose en PercentDecrease(abs) et inverserait le sens")
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "tyranSmnWarrior")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    sw = next((e for e in effs if getattr(e, "name", None) == "ShadowInTheWarp_LessDmg_Effect"), None)
    print(f"\n[SHADOW-WARP] summon effects={names} class={type(sw).__name__ if sw else None} "
          f"oracle dmgModifier={red_pct} range={rng}")
    assert sw is not None, f"ShadowInTheWarp_LessDmg_Effect NON seede au spawn : {names}"
    assert type(sw).__name__ == "ShadowInTheWarpLessDmgEffect", \
        f"effet materialise en {type(sw).__name__} (attendu ShadowInTheWarpLessDmgEffect, pas un no-op)"
    owner = (5, 5)

    def _at(dist):
        """Position d'attaquant a distance hex EXACTE `dist` du porteur (scan hexgeo, pas de coord figee)."""
        return next((c, r) for c in range(0, 16) for r in range(0, 16)
                    if hexgeo.distance(owner, (c, r)) == dist)

    def _aura(dist):
        return sw.create_aura_attack_damage_malus_for_enemy(
            {"owner_pos": owner, "owner_team": 2, "att_pos": _at(dist), "att_team": 1,
             "damage_profile": "Psychic"})

    aura = _aura(rng)                       # SurroundingEnemies(range) : DEDANS a distance = range
    print(f"[SHADOW-WARP] aura@dist{rng}={aura} aura@dist{rng + 1}={_aura(rng + 1)}")
    assert aura is not None and aura.kind == "PercentDecrease" and aura.value == abs(red_pct), (
        f"aura Psychique attendue PercentDecrease({abs(red_pct)}) a dist {rng} "
        f"(oracle shadowInTheWarpDmgModifier={red_pct}), obtenu {aura}")
    assert _aura(rng + 1) is None, (
        f"aura encore active a dist {rng + 1} > shadowInTheWarpRange={rng} : la portee du port ne suit "
        f"pas ConfigConst(0x16) du selecteur SurroundingEnemies")
