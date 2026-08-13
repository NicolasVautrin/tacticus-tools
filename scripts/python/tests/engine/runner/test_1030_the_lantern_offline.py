"""`1094 TheLantern` (`deathBossMortarion`) -- la GARDE du port des DEUX phases. #1030.

Ce fichier ne mesure rien : il FIGE ce que la RE a lu, et chaque etage porte sa CONTRE-EPREUVE
(la mutation qui doit le faire rougir). Le decompile est cite dans `runner/abilities/deathguard.py`
(phase 1), `runner/operations/triggers/loki/the_lantern_attack.py` (phase 2) et
`playbook/noncomparable/the_lantern.py` (face DECISION).

Board SYNTHETIQUE et plat : la geometrie de la zone est le sujet, pas le terrain. ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/hexgeo.py",
        # PRIS LARGE, et non feuille a feuille : le cast passe par le visiteur de message, donc par
        # le registre d'abilities, le vocabulaire DSL (selecteurs de tuiles ET d'unites), la pose
        # d'effet, le dispatch de trigger et le modele de degat. Une liste choisie ne pourrait pas
        # montrer le module qu'elle a oublie.
        "scripts/python/engine/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE du port de `1094 TheLantern` : zone, trois poses, attaquant de la "
              "phase 2, relecture de la marque au TIR, et face DECISION. Aucun runner, aucun RPC.",
}

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import hexgeo                                                            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType        # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects_state import EffectsState                   # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.messages import ActiveAbilityMessage                  # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

TL = int(ActiveAbilityType.TheLantern)                        # 1094
PENDING_TARGET = int(EffectType.TheLantern_PendingTarget)     # 1195
PINNED = int(EffectType.Pinned)                               # 1065
PENDING_ATTACK = int(EffectType.TheLantern_PendingAttack)     # 1194
TL_ATTACK = int(TriggeredAbilityType.TheLantern_Attack)       # 1167

COLS = ROWS = 9
CASTER, PLAYER_MOI, PLAYER_ADV = 10, 3, 4
#: Le caster en (2,4) ; la tuile ciblee a distance EXACTEMENT 2 -- la portee du masque est
#: `CustomRange(2)`, et une cible a 3 est REFUSEE par le gate (mesure : `invalid_target =
#: 0x8000000`, ce qu'a rendu le premier montage). A d = 2 le « pont » `ring2(T) & adj(caster)` est
#: un ensemble PROPRE (ni vide, ni tout `ring2`), ce que l'etage 2 assertionne.
CASTER_POS = (2, 4)
TARGET_POS = (4, 4)


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _state(foes: dict = None, caster_pos=CASTER_POS):
    """Etat runner minimal : le caster (joueur `PLAYER_MOI`) et `foes` = {uid: (col,row)}."""
    units = [{"id": CASTER, "visualId": "deathBossMortarion", "alive": True, "team": 1,
              "owner": PLAYER_MOI, "pos": {"col": caster_pos[0], "row": caster_pos[1]},
              "effects": []}]
    for uid, p in sorted((foes or {}).items()):
        units.append({"id": uid, "visualId": "necroWarden", "alive": True, "team": 2,
                      "owner": PLAYER_ADV, "pos": {"col": p[0], "row": p[1]}, "effects": []})
    decision = {"currentPlayer": PLAYER_MOI, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": 500000, "hpMax": 500000} for u in units]}
    # `combatSnapshot` MINIMAL : sans lui aucune unite n'a de `StatsComponent`, donc le niveau
    # d'ability de la phase 2 serait lu sur un repli et l'armure resterait indefinie.
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 500000, "movement": 3, "armour": 0,
                                     "turnsStarted": 0},
                           "healthMax": 500000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in units]}
    st = load_state(decision, observe, snapshot,
                    board=Board(_tiles(), adjacency="evenq"), ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    # LE CANAL `unitAbilityStates`, POSE A LA MAIN -- et il est INDISPENSABLE. Le noeud
    # `TriggerAbility` porte le gate `GetAbilityState` de
    # `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` : l'unite declenchee
    # doit PORTER l'ability triggered. `1167 TheLantern_Attack` est une ability DERIVEE
    # (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`, dictionnaire peuple au
    # RUNTIME), donc INVISIBLE du kit gameconfig : sans ce seed, le trigger fire et le noeud rend
    # `dispatched: True, notCarrying: [caster]` -- zero degat, aucune erreur. C'est exactement le
    # regime que le champ `notCarrying` a rendu visible sur 1069 (#513 Sec.5).
    from engine.runner.components import StatsComponent
    sc = st.get_entity(CASTER).get_component(StatsComponent)
    if sc is not None and getattr(sc, "ctx", None) is not None:
        sc.ctx.triggered_abilities = [TL_ATTACK]
    return st


def _zone_attendue(caster_pos=CASTER_POS, target=TARGET_POS) -> set:
    """La zone RE-DERIVEE a la main depuis le decompile, en positions -- volontairement ecrite
    autrement que le port (ensembles Python purs, aucun noeud DSL), pour qu'une faute du port ne
    puisse pas se recopier dans son oracle."""
    d = hexgeo.distance
    ring1 = {p for p in hexgeo.disk(target[0], target[1], 1) if p != target}
    ring2 = {p for p in hexgeo.disk(target[0], target[1], 2) if p != target}
    cring = {p for p in hexgeo.disk(caster_pos[0], caster_pos[1], 1) if p != caster_pos}
    dans = lambda s: {p for p in s if 0 <= p[0] < COLS and 0 <= p[1] < ROWS}   # noqa: E731
    assert d(caster_pos, target) == 2, "le montage n'a plus la distance qu'il documente"
    return dans({target} | ring1 | (ring2 & cring))


# =================================================================================================
# ETAGE 1 -- LES TROIS REGISTRES, DANS LE MEME COMMIT
# =================================================================================================

def test_e1_registre_masque_et_attack_type():
    """`ABILITY_CLASSES` + `TARGETING_OPTIONS` + `ABILITY_ATTACK_TYPE` : la regle de
    non-regression du CLAUDE.md, verifiee sur CETTE entree.

    Les quatre bits sont ceux du litteral `0x2000100042` du
    `IdunBattle.Core.Services.TargetingOptions$$.ctor` a 6 parametres, et leur SOMME doit RENDRE le
    litteral : un test qui ne verifierait que la presence de chaque bit passerait sur un masque
    portant en plus un cinquieme."""
    assert TL in ABILITY_CLASSES, "1094 absente d'ABILITY_CLASSES -> NO-OP SILENCIEUX"
    opts = ABILITY_CLASSES[TL].TARGETING_OPTIONS
    attendu = int(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.AllowSteppableUnit
                  | TR.CasterHas7Tiles)
    assert int(opts.rules) == attendu == 0x2000100042, hex(int(opts.rules))
    assert opts.self_cast is False
    # `CustomRange(2)` -- surcharge INT (XREF entrante) et litteral relu aux octets du call-site.
    assert opts.range.override_range == 2, opts.range
    assert opts.range.use_whole_board is False and opts.range.use_range_from_config is False
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.TheLantern] == AbilityAttackType.Others == 2


# =================================================================================================
# ETAGE 2 -- LA ZONE, ET LA MUTATION QUI LA CASSE
# =================================================================================================

def test_e2_zone_est_le_disque_plus_le_pont():
    """`Unique((Target + SurroundingTiles(Target,1)) + (SurroundingTiles(Target,2) &
    SurroundingTiles(CasterTiles,1)))`.

    L'oracle est RE-DERIVE (`_zone_attendue`), pas recopie du port. On assertionne aussi que le
    « pont » est NON VIDE et STRICTEMENT inclus dans `ring2` : sans ces deux crans, un port qui
    rendrait `ring2` entier -- ou rien -- passerait le test d'egalite sur un montage degenere."""
    from engine.runner.abilities.deathguard import the_lantern_area_selector
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = _state()
    sel = the_lantern_area_selector(_tid(*TARGET_POS))
    ids = set(sel.evaluate(entities_from_state(st, CASTER, _tid(*TARGET_POS))))
    got = {st.board.coord(t) for t in ids}
    attendu = _zone_attendue()
    assert got == attendu, "zone port %s != zone re-derivee %s" % (sorted(got), sorted(attendu))
    pont = attendu - ({TARGET_POS} | {p for p in hexgeo.disk(*TARGET_POS, 1)})
    ring2 = {p for p in hexgeo.disk(*TARGET_POS, 2) if p != TARGET_POS}
    assert pont, "le PONT est vide -- ce montage ne discrimine pas l'intersection"
    assert pont < ring2, "le pont vaut TOUT ring2 -- l'intersection ne mord pas ici"


def test_e2_contre_epreuve_union_au_lieu_d_intersection():
    """CONTRE-EPREUVE : l'`op_BitwiseAnd` du decompile remplace par un `op_Addition`.

    Vu ROUGE : la zone mutee est STRICTEMENT plus grande. Sans ce cran, l'egalite de l'etage
    ci-dessus ne prouverait pas que c'est bien une INTERSECTION qui est portee."""
    from engine.entities.selectors.accessors import FixedTileIds, SurroundingTiles, CasterTile
    from engine.entities.selectors.tiles import TileUnion, TileUnique
    from engine.dsl.base import Const
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = _state()
    tgt = FixedTileIds([_tid(*TARGET_POS)])
    r1 = SurroundingTiles(tgt, Const(1), include_center=False, include_non_walkable=False)
    r2 = SurroundingTiles(tgt, Const(2), include_center=False, include_non_walkable=False)
    cr = SurroundingTiles(CasterTile(as_ids=True), Const(1),
                          include_center=False, include_non_walkable=False)
    mute = TileUnique(TileUnion(TileUnion(tgt, r1), TileUnion(r2, cr)))       # `&` -> `+`
    ids = set(mute.evaluate(entities_from_state(st, CASTER, _tid(*TARGET_POS))))
    got = {st.board.coord(t) for t in ids}
    assert got != _zone_attendue(), "la mutation `&` -> `+` ne change RIEN : l'etage 2 est inerte"
    assert got > _zone_attendue()


# =================================================================================================
# ETAGE 3 -- LA PHASE 1 : TROIS POSES, ZERO DEGAT
# =================================================================================================

def _cast(st, target_tile):
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=CASTER, target_id=int(target_tile),
                                      ability_type=TL))
    return runner.ability_handler.last or {}


def test_e3_trois_poses_et_aucun_degat():
    """La marque sur TOUTE la zone, `Pinned` sur les seuls ENNEMIS qui s'y trouvent, l'armement sur
    le CASTER -- et pas un point de degat au cast.

    Le montage place UN ennemi DANS la zone et UN HORS zone : sans le second, un port qui poserait
    `Pinned` sur tous les ennemis du plateau passerait."""
    zone = _zone_attendue()
    dedans = sorted(zone - {TARGET_POS})[0]
    dehors = (8, 8)
    assert dehors not in zone
    st = _state({20: dedans, 21: dehors})
    last = _cast(st, _tid(*TARGET_POS))
    assert last.get("dsl") is True and last.get("ability") == "TheLantern"
    marquees = {st.board.coord(t) for t in st.effects.by_unit
                if any(not e.consumed and int(e.effect_type) == PENDING_TARGET
                       for e in st.effects.by_unit[t]) and t in st.board.by_id}
    assert marquees == zone, "marque %s != zone %s" % (sorted(marquees), sorted(zone))
    pinned = {u for u in (20, 21)
              if any(not e.consumed and int(e.effect_type) == PINNED
                     for e in st.effects.by_unit.get(u, []))}
    assert pinned == {20}, "Pinned pose sur %s (attendu : le seul ennemi DANS la zone)" % pinned
    assert any(not e.consumed and int(e.effect_type) == PENDING_ATTACK
               for e in st.effects.by_unit.get(CASTER, [])), "1194 absent du CASTER"
    # ZERO DEGAT au cast : c'est tout l'enjeu du patron 2-phases.
    from engine.runner.components import HealthComponent
    for u in (20, 21):
        assert st.get_entity(u).get_component(HealthComponent).hp == 500000


def test_e3_contre_epreuve_enemies_sans_resolution_de_tuile():
    """CONTRE-EPREUVE de la reparation d'`Enemies` : sans la resolution
    `IdunBattle.Entities.UnitExtensions$$GetUnitOrMachine(entity, state)` que
    `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` applique a CHAQUE entite
    iteree, le `Pinned` ne se pose sur PERSONNE.

    Vu ROUGE avant la reparation. C'est la faute qui rendait le port MUET sur ce volet : `[]`, sans
    erreur.

    ⚠ **LE DOMAINE DE RETOUR N'EST PAS CELUI QUE CETTE TRANCHE AVAIT ECRIT, et le decompile
    tranche pour l'AUTRE lecture.** `CountOrAdd` fait `System.Collections.Generic.List<T>.Add(
    result, entity)` -- **l'ENTITE ITEREE** (`enumerator.get_Current()`), pas l'unite resolue ;
    `other = GetUnitOrMachine(entity, this+0x10)` ne sert qu'au `IsFriend(unit, other, state)` dont
    le resultat est compare au flag `this+0x28` (0 = `Enemies`, 1 = `Friends`). Le premier jet de
    #1030 rendait l'unite resolue : meme bug ferme, domaine de retour FAUX. La forme gardee est
    celle de `master`, et ce test la garde."""
    from engine.entities.selectors import units as U
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    ancien = U.unit_or_machine
    try:
        # Le comportement d'AVANT : aucune resolution -- une entite-TUILE (id `int`) ne rendait
        # aucune unite, donc l'ensemble sortait VIDE, sans erreur.
        U.unit_or_machine = lambda e, ctx: (e if isinstance(e, dict) else None)
        st2 = _state({20: sorted(zone - {TARGET_POS})[0]})
        _cast(st2, _tid(*TARGET_POS))
        pinned_mute = [e for e in st2.effects.by_unit.get(20, [])
                       if not e.consumed and int(e.effect_type) == PINNED]
    finally:
        U.unit_or_machine = ancien
    _cast(st, _tid(*TARGET_POS))
    pinned_ok = [e for e in st.effects.by_unit.get(20, [])
                 if not e.consumed and int(e.effect_type) == PINNED]
    assert not pinned_mute, "la mutation ne mord pas -- l'etage 3 ne prouve rien de la reparation"
    assert pinned_ok, "avec la reparation, `Pinned` doit etre pose"


# =================================================================================================
# ETAGE 4 -- L'ATTAQUANT DE LA PHASE 2 : `EffectSource`, PAS `BondedEntity`
# =================================================================================================

def _turn_start(st, player_id):
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers
    return delayed_attack_triggers(st, int(player_id))


def test_e4_attaquant_est_la_source_de_l_effet():
    """`<klass+0x758> GetAttackingUnitSelector` SURCHARGEE en `DSLSelectors$$EffectSource(Effect)`.

    L'effet 1194 est pose par `AddEffect`, donc SANS composant de bond : la table doit le declarer
    `ATTACKER_EFFECT_SOURCE`, et l'instance posee doit effectivement porter `bonded is None` (sans
    quoi ce test ne mesurerait pas ce qu'il croit)."""
    from engine.runner.operations.triggers import pending_attack as PA
    spec = PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK]
    assert spec.attacker == PA.ATTACKER_EFFECT_SOURCE
    assert spec.triggered_ability == TL_ATTACK
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    _cast(st, _tid(*TARGET_POS))
    inst = [e for e in st.effects.by_unit.get(CASTER, [])
            if not e.consumed and int(e.effect_type) == PENDING_ATTACK][0]
    assert getattr(inst, "bonded", None) is None, (
        "l'instance porte un bond : le regime que ce test discrimine n'existe plus")
    assert int(inst.source) == CASTER
    assert PA._attacking_unit(inst) == CASTER


def test_e4_contre_epreuve_lecture_bonded():
    """CONTRE-EPREUVE : la table declaree `ATTACKER_BONDED` (le corps HERITE) -- l'attaquant devient
    introuvable et la phase 2 ne part JAMAIS.

    Vu ROUGE : c'est exactement le regime silencieux qu'aurait produit un port qui aurait recopie
    le corps que `ghidra/functions.tsv` attribue a `ValkyrieStrikeEffect`."""
    from engine.runner.operations.triggers import pending_attack as PA
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    _cast(st, _tid(*TARGET_POS))
    inst = [e for e in st.effects.by_unit.get(CASTER, [])
            if not e.consumed and int(e.effect_type) == PENDING_ATTACK][0]
    vrai = PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK]
    try:
        PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK] = vrai._replace(
            attacker=PA.ATTACKER_BONDED)
        assert PA._attacking_unit(inst) is None, (
            "la mutation ne mord pas -- l'etage 4 ne prouve rien")
    finally:
        PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK] = vrai


# =================================================================================================
# ETAGE 5 -- LA MARQUE EST RELUE AU TIR (le volet qui exige DEUX tours)
# =================================================================================================

def test_e5_le_tir_frappe_les_occupants_courants():
    """La zone marquee vit sur des TUILES : l'unite qui SORT y echappe, celle qui ENTRE la prend.

    Le montage bouge DEUX unites entre le cast et le tir -- une dans chaque sens -- sur un etat par
    ailleurs identique. Un port qui figerait la liste des cibles AU CAST frapperait exactement
    l'inverse."""
    from engine.runner.components import HealthComponent, PositionComponent
    zone = _zone_attendue()
    dedans = sorted(zone - {TARGET_POS})[0]
    dehors = (8, 8)
    st = _state({20: dedans, 21: dehors})
    _cast(st, _tid(*TARGET_POS))
    # 20 SORT de la zone, 21 y ENTRE -- apres le cast, avant le tir.
    st.get_entity(20).get_component(PositionComponent).col = dehors[0]
    st.get_entity(20).get_component(PositionComponent).row = dehors[1]
    st.get_entity(21).get_component(PositionComponent).col = dedans[0]
    st.get_entity(21).get_component(PositionComponent).row = dedans[1]
    hp0 = {u: st.get_entity(u).get_component(HealthComponent).hp for u in (20, 21)}
    fired = _turn_start(st, PLAYER_MOI)
    assert fired, "le `Triggered()` d'APendingAttackEffect n'a pas fire au tour du caster"
    hp1 = {u: st.get_entity(u).get_component(HealthComponent).hp for u in (20, 21)}
    assert hp1[20] == hp0[20], "l'unite SORTIE de la zone a ete frappee"
    assert hp1[21] < hp0[21], "l'unite ENTREE dans la zone n'a PAS ete frappee"
    # La marque est retiree par le meme arbre (`RemoveEffect(cache, 1195)`), et l'armement 1194 par
    # le `RemoveEffect(Effect)` du `Triggered()` de la base.
    restant = [t for t in st.effects.by_unit
               if any(not e.consumed and int(e.effect_type) == PENDING_TARGET
                      for e in st.effects.by_unit[t])]
    assert not restant, "la marque 1195 survit au tir : %s" % restant
    assert not [e for e in st.effects.by_unit.get(CASTER, [])
                if not e.consumed and int(e.effect_type) == PENDING_ATTACK]


def test_e5_ne_fire_pas_au_tour_adverse():
    """TEMOIN NEGATIF : `IsTurnOf(GetAttackingUnitSelector())`. Au tour de l'ADVERSE, rien ne part
    et la marque reste. Sans ce cran, l'etage 5 ne distinguerait pas « fire au bon tour » de
    « fire a tous les tours »."""
    from engine.runner.components import HealthComponent
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    _cast(st, _tid(*TARGET_POS))
    hp0 = st.get_entity(20).get_component(HealthComponent).hp
    _turn_start(st, PLAYER_ADV)
    assert st.get_entity(20).get_component(HealthComponent).hp == hp0
    assert any(not e.consumed and int(e.effect_type) == PENDING_ATTACK
               for e in st.effects.by_unit.get(CASTER, []))


# =================================================================================================
# ETAGE 6 -- LA FACE DECISION
# =================================================================================================

def test_e6_utilite_poids_et_gate_de_sept_tuiles():
    """`n1 * 1 + n2 * 0,1` sous le gate `|zone| >= 7`, avec `n2` compte sur les ENNEMIS DEJA
    filtres (l'ordre des deux `FilterInPlace` est load-bearing).

    Le montage met dans la zone : un ennemi ordinaire, un ennemi PSYKER, et un ALLIE psyker. Le
    troisieme est le discriminant : un port qui compterait les psykers de la zone (et non les
    ennemis psykers) rendrait `2 + 0,2` au lieu de `2 + 0,1`."""
    from engine.playbook.noncomparable.the_lantern import TheLanternPlaybook
    zone = sorted(_zone_attendue() - {TARGET_POS})
    pb = TheLanternPlaybook()

    class _Ctx:
        uid = CASTER
        origin = CASTER_POS
        obs_units = [
            {"id": CASTER, "teamId": 1, "visualId": "deathBossMortarion",
             "pos": {"col": CASTER_POS[0], "row": CASTER_POS[1]}},
            {"id": 20, "teamId": 2, "visualId": "necroWarden",
             "pos": {"col": zone[0][0], "row": zone[0][1]}},
            {"id": 21, "teamId": 2, "visualId": "eldarFarseer",
             "pos": {"col": zone[1][0], "row": zone[1][1]}},
            {"id": 22, "teamId": 1, "visualId": "eldarFarseer",
             "pos": {"col": zone[2][0], "row": zone[2][1]}},
        ]
        elev_by_pos = {(c, r): 0 for c in range(COLS) for r in range(ROWS)}
        is_wall_by_pos = {}
        walkable_by_pos = {}
        scene = None

    from engine.entities.traits.unit_trait import entity_trait_names, has_any_trait
    psyker = has_any_trait(entity_trait_names(None, "eldarFarseer"), ("Psyker",))
    if not psyker:
        pytest.skip("`eldarFarseer` n'est plus Psyker au gameconfig -- montage a refaire")
    area = pb.target_area(_Ctx(), CASTER_POS, TARGET_POS)
    assert area == _zone_attendue(), "la zone de la face DECISION diverge de celle du COMBAT"
    assert len(area) >= 7, "le montage ne passe pas le gate qu'il pretend exercer"
    u = pb._enemies_hit_utility(_Ctx(), area)
    assert abs(u - (2 * 1.0 + 1 * 0.1)) < 1e-9, u


def test_e6_gate_sept_tuiles_mord():
    """Le gate `|zone| >= 7` : sur une zone TRONQUEE (cible dans un coin du board), l'ability n'est
    pas proposee. TEMOIN : la meme mesure au centre la propose."""
    from engine.playbook.noncomparable.the_lantern import TheLanternPlaybook, _MIN_TILES_HIT
    pb = TheLanternPlaybook()

    class _Ctx:
        uid = CASTER
        origin = (0, 0)
        obs_units = [{"id": CASTER, "teamId": 1, "visualId": "deathBossMortarion",
                      "pos": {"col": 0, "row": 0}}]
        elev_by_pos = {(c, r): 0 for c in range(COLS) for r in range(ROWS)}
        is_wall_by_pos = {}
        walkable_by_pos = {}
        scene = None

    coin = pb.target_area(_Ctx(), (0, 0), (0, 0))
    centre = pb.target_area(_Ctx(), (4, 4), (4, 4))
    assert len(coin) < _MIN_TILES_HIT <= len(centre), (len(coin), len(centre))


if os.environ.get("TACTICUS_1030_SELFTEST"):        # pragma: no cover - aide au diagnostic
    print("zone:", sorted(_zone_attendue()))
