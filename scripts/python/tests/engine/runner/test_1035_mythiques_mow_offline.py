"""#1035 -- CONTRE-EPREUVE 100 % OFFLINE des deux MYTHIQUES de MACHINE OF WAR portees par la
tranche : `HyperCorrosiveAcid` (1455, `tyranBiovore`) et `BlightedLand` (1447, `deathCrawler`).

Ce que ces cliquets verrouillent -- CHAQUE etage est un COUPLE (un bras qui DOIT rendre le
comportement, un bras qui DOIT le refuser), parce qu'un test qui n'a qu'un bras peut passer pour
une raison qui n'a rien a voir avec ce qu'il croit mesurer :

  0. les ids et l'appariement ability <-> effet sont LUS au decompile (1455/1448, 1447/1442) ;
  1. le trigger de `HyperCorrosiveAcid` MORD quand une **Spore Mine amie** blesse un ennemi
     VIVANT ; bras negatifs : l'acteur est le PORTEUR lui-meme, un allie quelconque, une mine
     ENNEMIE ; la cible est AMIE ; la cible est MORTE ;
  2. **le gate `IsUnitWithVisualId` COMPOSE avec `VisualUnitIdFromUnitId`** -- le noeud formule rend
     une COLLECTION, le natif compare une CHAINE ; la composition naive rendait FAUX
     SYSTEMATIQUEMENT, sans erreur. Contre-epreuve par MUTATION : l'implementation d'AVANT (`==`)
     est rejouee et doit RATER ce que la composition portee ATTRAPE ;
  3. **`ChangeType.Set`, PAS `Add`** -- meme piege silencieux qu'`ElectrochaffBackups` : une
     re-explosion REMET la duree, elle ne l'accumule pas, et ne pose pas une 2e instance ;
  4. `BlightedLand` : l'entree `ABILITY_INIT_OWNER_EFFECTS` nomme l'effet que le natif nomme
     (`$$GetEffectType` = `return 0x5a2`), et ce seed MORD sur la voie TERTIAIRE ;
  5. **le VERROU DE RARETE est fige avec sa raison** : les deux effets 1448 et 1442 restent HORS
     d'`EFFECT_CLASSES` parce que leurs canaux de degat ouvrent sur `HasRarity(., 5 = Mythic)` /
     `UnitsWithRarity(., 5)` et qu'aucun canal `rarity` n'existe cote port. Ce cliquet n'interdit
     pas de les inscrire -- il oblige a le faire EN CONNAISSANCE.

TEMOIN NON DEGENERE -- l'etage 3 serait vide si `convert_rounds_to_turns` rendait 0 : la duree est
donc ASSERTIONNEE > 0 avant d'etre comparee, et l'etage 2 assertionne que sa formule rend bien
PLUSIEURS formes (sinon la mutation ne separerait rien). ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest                                                              # noqa: E402

import hexgeo                                                              # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType      # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType      # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.formulas import VisualUnitIdFromUnitId                # noqa: E402
from engine.entities.selectors.accessors import Actor                      # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.entities.triggers import IsUnitWithVisualId                    # noqa: E402
from engine.runner.abilities.base import convert_rounds_to_turns           # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state  # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent            # noqa: E402
from engine.runner.operations.effects import ChangeEffectTurnsOperation    # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.runner.operations.triggers.loki.hyper_corrosive_acid import (  # noqa: E402
    HyperCorrosiveAcidAbility, HYPER_CORROSIVE_ACID, HYPER_CORROSIVE_ACID_ID,
    HYPER_CORROSIVE_ACID_EFFECT, hyper_corrosive_rounds, hyper_corrosive_unit_id,
    hyper_corrosive_actor_is_spore_mine)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Les deux faces portees par #1035 et leurs registres.
        "scripts/python/engine/runner/operations/triggers/loki/hyper_corrosive_acid.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/spawn.py",
        # Les primitives MIRRORS que les etages lisent : le gate visual-id, la duree, le refresh.
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/abilities/base.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site par l'etage 0.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        # Le VERROU que l'etage 5 garde : le jour ou ce champ apparait, il faut relire.
        "scripts/python/engine/entities/unit_context.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Deux etages lisent le GAMECONFIG (`HyperCorrosiveAcid.constants.nrOfRounds` et "
              "`.unitId`), qui se perime SEPAREMENT du build ; l'etage 0 fige des ORDINAUX au site "
              "(1455 / 1448 / 1447 / 1442 / 0x45 / 0x0 / 0xa), qu'un renumerotage rendrait faux "
              "sans toucher aucun des chemins ci-dessus ; et l'etage 5 garde une ABSENCE "
              "(`UnitContext.rarity`), donc un ajout n'importe ou dans le port peut le concerner.",
}

COLS, ROWS = 6, 6
OWNER_ID, MINE_ID, ENEMY_ID, FRIEND_ID, ENEMY_MINE_ID, DEAD_ID = 10, 20, 30, 40, 50, 60
HP = 50000
#: 2 joueurs dans le `turnOrder` -> `ConvertRoundsToTurns(1) = 2`.
PLAYER_COUNT = 2
#: L'id de config de la Spore Mine, tel que le gameconfig le porte (`constants.unitId`).
SPORE_MINE = "tyranSmnSporeMine"


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _state():
    """Etat synthetique : le PORTEUR `tyranBiovore` (team 1) + sa Spore Mine (team 1) + un ennemi
    vivant (team 2) + un allie NON-mine (team 1) + une Spore Mine ENNEMIE (team 2) + un ennemi
    MORT. Chaque unite existe pour separer UN conjoint du `CreateTrigger`."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    units = [
        {"id": OWNER_ID, "visualId": "tyranBiovore", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": MINE_ID, "visualId": SPORE_MINE, "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 2, "row": 1}, "effects": []},
        {"id": ENEMY_ID, "visualId": "orksRuntherd", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 4, "row": 4}, "effects": []},
        {"id": FRIEND_ID, "visualId": "tauCrisis", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 3}, "effects": []},
        {"id": ENEMY_MINE_ID, "visualId": SPORE_MINE, "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 5, "row": 4}, "effects": []},
        {"id": DEAD_ID, "visualId": "orksRuntherd", "alive": False, "team": 2, "owner": 2,
         "pos": {"col": 3, "row": 5}, "effects": []},
    ]
    decision = {"currentPlayer": 1, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": (HP if u["alive"] else 0), "hpMax": HP}
                         for u in units],
               "counts": {"player": PLAYER_COUNT + 1}}
    st = load_state(decision, observe, board=Board(tiles, adjacency="evenq"))
    if st.effects is None:                      # aucun effet au seed -> `load_state` laisse None
        from engine.entities.effects_state import EffectsState
        st.effects = EffectsState.seed({})
    assert st.effects is not None, "montage : EffectsState absent -> aucune pose possible"
    return st


def _ev(target_id, actor_id=MINE_ID):
    """Le `TriggerEvent` que publie `dispatch/attack.damage_taken_triggers` : `actor` = la source
    du degat, `target` = la VICTIME."""
    return TriggerEvent(int(EventTriggerType.DamageTaken), actor_id, target_id,
                        ranged=False, profile=None)


def _has_1448(state, uid):
    return any(e.effect_type == HYPER_CORROSIVE_ACID_EFFECT and not e.consumed
               for e in state.effects.by_unit.get(int(uid), []))


def _turns_1448(state, uid):
    e = next((x for x in state.effects.by_unit.get(int(uid), [])
              if x.effect_type == HYPER_CORROSIVE_ACID_EFFECT and not x.consumed), None)
    return None if e is None else e.remaining_turns


# --------------------------------------------------------------------------------------------
# Etage 0 -- les ids, l'appariement ability <-> effet et la voie de registration sont LUS
# --------------------------------------------------------------------------------------------

def test_ids_et_registres_sont_lus_au_decompile():
    """`HyperCorrosiveAcidAbility` = `TriggeredAbilityType` 0x5af ; l'effet pose par son
    `$$CreateBehaviour` = `EffectType` 0x5a8. `BlightedLandAbility$$GetEffectType` a pour corps
    ENTIER `return 0x5a2` (= 1442). Ces ordinaux sont ECRITS ICI pour qu'un renumerotage du build
    les fasse ROUGIR au SITE (le mirror d'enum, lui, redeviendrait vert apres regeneration)."""
    assert int(HYPER_CORROSIVE_ACID) == 0x5af == 1455
    assert HYPER_CORROSIVE_ACID_EFFECT == 0x5a8 == 1448
    assert int(EffectType.HyperCorrosiveAcid_ExtraDamagePct) == HYPER_CORROSIVE_ACID_EFFECT
    assert int(TriggeredAbilityType.BlightedLand) == 0x5a7 == 1447
    assert int(EffectType.BlightedLand_ExtraDamagePct) == 0x5a2 == 1442
    # Les trois cles de config LUES aux call-sites natifs (`GetStringConstant(0x0)`,
    # `GetNumberConstant(0x45)`, `ConfigVar(0xa)`).
    assert int(AbilityConstantType.unitId) == 0x0
    assert int(AbilityConstantType.nrOfRounds) == 0x45
    assert int(AbilityVariableType.extraDmgPct) == 0xa
    from engine.runner.operations.triggers.dispatch.registry import RELIC_ABILITY_TRIGGERS
    # La voie de registration COTE COMBAT d'une mythique EST celle de la relique (meme champ
    # `BC.Units[].TertiaryAbility`, meme `TryAdd(..., 3)`).
    assert (RELIC_ABILITY_TRIGGERS.get(HYPER_CORROSIVE_ACID_ID)
            == [HyperCorrosiveAcidAbility])


def test_les_constantes_gameconfig_sont_lues_pas_codees():
    """`GetStringConstant(0x0 = unitId)` = `"tyranSmnSporeMine"` et
    `GetNumberConstant(0x45 = nrOfRounds)` = `"1"` -- les deux LUS au gameconfig."""
    assert hyper_corrosive_unit_id() == SPORE_MINE
    assert hyper_corrosive_rounds() == 1, (
        f"gameconfig HyperCorrosiveAcid.constants.nrOfRounds = {hyper_corrosive_rounds()}")


# --------------------------------------------------------------------------------------------
# Etage 1 -- le trigger : les quatre conjoints, un bras negatif chacun
# --------------------------------------------------------------------------------------------

def test_une_spore_mine_amie_qui_blesse_un_ennemi_pose_l_effet():
    st = _state()
    ab = HyperCorrosiveAcidAbility(OWNER_ID)
    assert ab.event_id == int(EventTriggerType.DamageTaken) == 15
    ev = _ev(ENEMY_ID)
    assert ab.matches(st, ev) is True
    out = ab.execute_behaviour(st, ev)
    assert out and out["placed"] is True and out["refreshed"] is False
    assert _has_1448(st, ENEMY_ID)


@pytest.mark.parametrize("actor,pourquoi", [
    (OWNER_ID, "le PORTEUR lui-meme n'est pas une Spore Mine (IsUnitWithVisualId)"),
    (FRIEND_ID, "un allie quelconque n'est pas une Spore Mine (IsUnitWithVisualId)"),
    (ENEMY_MINE_ID, "une Spore Mine ENNEMIE echoue sur AreFriends(Owner, Actor)"),
])
def test_le_gate_sur_l_acteur_refuse_les_trois_autres_sources(actor, pourquoi):
    """`AreFriends(Owner@+0x30, Actor@+0x40)` & `IsUnitWithVisualId(Actor@+0x40, ...)`.
    Bras POSITIF : le test juste au-dessus."""
    st = _state()
    ab = HyperCorrosiveAcidAbility(OWNER_ID)
    assert ab.matches(st, _ev(ENEMY_ID, actor_id=actor)) is False, pourquoi
    assert not _has_1448(st, ENEMY_ID)


def test_le_gate_sur_la_cible_refuse_un_allie():
    """`AreEnemies(Owner@+0x30, Target@+0x60, 0)` -- une mine qui blesse un ami (friendly fire)
    ne pose rien."""
    st = _state()
    ab = HyperCorrosiveAcidAbility(OWNER_ID)
    assert ab.matches(st, _ev(FRIEND_ID)) is False


def test_le_gate_sur_la_cible_refuse_une_unite_morte():
    """`IsAlive(Target@+0x60)` -- le vecteur `On(0x0f)` est emis APRES la mutation des PV, donc une
    cible tuee par le coup y arrive deja `alive = False` et n'ecope de rien."""
    st = _state()
    ab = HyperCorrosiveAcidAbility(OWNER_ID)
    assert st.get_entity(DEAD_ID) is not None, "montage : l'entite morte doit exister"
    assert ab.matches(st, _ev(DEAD_ID)) is False


# --------------------------------------------------------------------------------------------
# Etage 2 -- la COMPOSITION `IsUnitWithVisualId(Actor, VisualUnitIdFromUnitId(unitId))`
# --------------------------------------------------------------------------------------------

def test_la_formule_visual_id_rend_bien_une_collection():
    """TEMOIN NON DEGENERE de l'etage suivant : si `VisualUnitIdFromUnitId` rendait un SCALAIRE,
    la mutation ci-dessous ne separerait rien et le cliquet passerait pour vert sans rien garder."""
    st = _state()
    entities = entities_from_state(st, OWNER_ID, ENEMY_ID, MINE_ID)
    valeur = VisualUnitIdFromUnitId(SPORE_MINE).calculate(entities)
    assert not isinstance(valeur, str), (
        "TEMOIN DEGENERE : la formule rend deja une chaine, la mutation ne prouverait rien")
    assert SPORE_MINE in valeur, valeur


def test_la_composition_native_mord_la_ou_l_egalite_brute_ratait():
    """MUTATION ADVERSARIALE. Le natif compare UNE chaine
    (`IsUnitWithVisualIdTrigger$$ShouldTrigger` = `String.op_Equality(GetVisualUnitId(unit),
    value.Value)`), mais le noeud PORTE qui l'alimente rend DEUX formes. L'implementation d'AVANT
    (`_visual_id_of(u) == vid`) est rejouee ici telle quelle : elle DOIT rater ce que la
    composition portee attrape -- sinon le fix de `IsUnitWithVisualId` ne gardait rien."""
    st = _state()
    entities = entities_from_state(st, OWNER_ID, ENEMY_ID, MINE_ID)
    noeud = hyper_corrosive_actor_is_spore_mine()
    assert noeud.should_trigger(entities) is True, "la composition portee doit MORDRE"
    # L'ancienne implementation, verbatim.
    vid = noeud.visual_id.calculate(entities)
    from engine.dsl.base import _units_of
    avant = any(IsUnitWithVisualId._visual_id_of(u) == vid for u in _units_of(Actor(), entities))
    assert avant is False, (
        "l'egalite brute mord aussi : le fix de IsUnitWithVisualId ne garde rien")


def test_le_gate_accepte_une_valeur_scalaire_comme_le_natif():
    """L'autre bras du meme fix : une valeur SCALAIRE reste une EGALITE (le comportement natif au
    bit pres). Sans ce bras, `_wanted` pourrait deplier une chaine en ses caracteres."""
    st = _state()
    entities = entities_from_state(st, OWNER_ID, ENEMY_ID, MINE_ID)
    assert IsUnitWithVisualId(Actor(), SPORE_MINE).should_trigger(entities) is True
    assert IsUnitWithVisualId(Actor(), "tyranBiovore").should_trigger(entities) is False
    # Une chaine ne doit PAS etre depliee en caracteres : un prefixe d'UN caractere ne matche pas.
    assert IsUnitWithVisualId(Actor(), SPORE_MINE[0]).should_trigger(entities) is False


# --------------------------------------------------------------------------------------------
# Etage 3 -- `ChangeType.Set`, PAS `Add` (le seul ecart SILENCIEUX du behaviour)
# --------------------------------------------------------------------------------------------

def test_duree_est_turns_from_rounds_du_gameconfig():
    st = _state()
    turns = convert_rounds_to_turns(st, hyper_corrosive_rounds())
    assert turns > 0, "TEMOIN DEGENERE : ConvertRoundsToTurns rend 0, l'etage Set/Add ne prouverait rien"
    assert turns == PLAYER_COUNT, f"ConvertRoundsToTurns(1) attendu {PLAYER_COUNT}, obtenu {turns}"
    ab = HyperCorrosiveAcidAbility(OWNER_ID)
    ab.execute_behaviour(st, _ev(ENEMY_ID))
    assert _turns_1448(st, ENEMY_ID) == turns


def test_re_declenchement_remet_la_duree_au_lieu_de_l_accumuler():
    """`ChangeEffectTurns(..., changeType = 1 = ChangeType.Set)` -- lu au 5e argument du call-site
    (`CONCAT44(hi, 1)`). Une mine qui explose plusieurs fois sur la meme victime (ou une salve de
    plusieurs coups) ne doit PAS empiler la duree."""
    st = _state()
    turns = convert_rounds_to_turns(st, hyper_corrosive_rounds())
    assert turns > 0
    ab = HyperCorrosiveAcidAbility(OWNER_ID)
    ev = _ev(ENEMY_ID)
    first = ab.execute_behaviour(st, ev)
    assert first["placed"] is True and first["refreshed"] is False
    for _ in range(4):
        again = ab.execute_behaviour(st, ev)
        assert again["placed"] is False and again["refreshed"] is True
    assert _turns_1448(st, ENEMY_ID) == turns, (
        "5 declenchements ont accumule la duree : le behaviour utilise Add au lieu de Set")
    # Contre-epreuve du MIROIR lui-meme : `Add` DONNERAIT bien un autre resultat sur ce cas.
    assert (ChangeEffectTurnsOperation.get_amount(turns, turns, ChangeEffectTurnsOperation.CHANGE_ADD)
            != ChangeEffectTurnsOperation.get_amount(turns, turns,
                                                     ChangeEffectTurnsOperation.CHANGE_SET))


def test_le_refresh_ne_pose_pas_une_seconde_instance():
    """`If(HasEffect(...), ChangeEffectTurns, AddEffect)` -- la branche `then` ne pose RIEN."""
    st = _state()
    ab = HyperCorrosiveAcidAbility(OWNER_ID)
    ev = _ev(ENEMY_ID)
    ab.execute_behaviour(st, ev)
    ab.execute_behaviour(st, ev)
    n = sum(1 for e in st.effects.by_unit.get(ENEMY_ID, [])
            if e.effect_type == HYPER_CORROSIVE_ACID_EFFECT and not e.consumed)
    assert n == 1, f"{n} instances de 1448 sur la cible"


# --------------------------------------------------------------------------------------------
# Etage 4 -- `BlightedLand` : owner-effect PERMANENT pose a l'init, par la voie TERTIAIRE
# --------------------------------------------------------------------------------------------

def test_blighted_land_nomme_l_effet_du_decompile():
    """`BlightedLandAbility$$GetEffectType` a pour corps ENTIER `return 0x5a2`. L'entree
    `ABILITY_INIT_OWNER_EFFECTS` doit nommer CET effet-la, pas un homonyme devine."""
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS
    assert (ABILITY_INIT_OWNER_EFFECTS.get("BlightedLand")
            == [EffectType.BlightedLand_ExtraDamagePct.name])


def test_le_seed_offline_pose_l_owner_effect_de_blighted_land():
    """L'entree `ABILITY_INIT_OWNER_EFFECTS` doit MORDRE sur la voie TERTIAIRE.

    ⚠ POURQUOI CE CLIQUET EXISTE : sur un runner live l'effet 1442 arrive par la CAPTURE
    (`decisionView.effects` / `mows[].effects`), sa `CreateActiveCondition` heritee etant le corps
    DEDUPLIQUE `return <DSLTriggers+0x70>` = `YesTrigger`. L'entree n'est donc un FILET que pour
    les chemins PUREMENT offline, et seul un test offline peut le montrer."""
    from engine.runner.components import StatsComponent
    from engine.entities.unit_context import UnitContext
    from engine.runner.operations.spawn import _seed_ability_owner_effects
    st = _state()
    ctx = UnitContext(entity_id=OWNER_ID, visual_id="deathCrawler",
                      tertiary_ability="BlightedLand", tertiary_ability_level=1,
                      tertiary_ability_variables_multiplier=100)
    st.get_entity(OWNER_ID).add_component(StatsComponent(ctx))
    poses = _seed_ability_owner_effects(st, OWNER_ID, "deathCrawler", 100, ability_level=1)
    assert EffectType.BlightedLand_ExtraDamagePct.name in poses, poses
    assert any(e.effect_type == int(EffectType.BlightedLand_ExtraDamagePct)
               for e in st.effects.by_unit.get(OWNER_ID, []))


# --------------------------------------------------------------------------------------------
# Etage 5 -- le VERROU DE RARETE, fige avec sa raison
# --------------------------------------------------------------------------------------------

def test_verrou_de_rarete_fige_avec_sa_raison():
    """Les DEUX effets restent HORS `EFFECT_CLASSES` tant qu'aucun canal `rarity` n'existe.

    RAISON, mesuree et deja ecrite (`docs/rl/case-1024-shield-of-faith-on-my-position.md` Sec.4) :
    `IdunBattle.Entities.UnitExtensions$$HasRarity` et
    `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` comparent tous deux
    `GetBaseUnitComponent(e)+0x74` au litteral `5 = Mythic` ; ni `combatSnapshot`, ni `UnitContext`,
    ni `decisionView` ne portent cette valeur. Pour 1448 le gate est `HasRarity(Caster, Mythic)
    & HasTrait(Caster, Hero)` ; pour 1442 c'est le SELECTEUR (`UnitsWithRarity(Friends(Owner), 5)`
    filtre par `UnitsOnTilesWithEffect(Contaminated)`). Les inscrire sans ces gates donnerait des
    termes PERMISSIFS.

    ⚠ ET LE REGIME PAR DEFAUT EST DEGENERE : `rl_duel build` pose `targetRarity = 5`, donc dans un
    runner standard toute unite est Mythic et `HasRarity(., Mythic)` est uniformement VRAI -- un
    port qui oublierait le gate serait d'accord avec le natif dans tous les bras par defaut. C'est
    exactement pourquoi ce verrou ne peut pas etre leve << au jugé >>.

    Ce test ROUGIRA le jour ou quelqu'un les inscrit : c'est voulu. Il faudra alors avoir threade
    `rarity` (residus `#1035-r1` / `#1035-r2`), et le retrait de ce cliquet fera partie du geste."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.unit_context import UnitContext
    assert EffectType.HyperCorrosiveAcid_ExtraDamagePct.name not in EFFECT_CLASSES
    assert EffectType.BlightedLand_ExtraDamagePct.name not in EFFECT_CLASSES
    # Le canal manquant, nomme : si ce champ APPARAIT, le verrou est leve et les deux canaux de
    # degat doivent etre portes (ce test devient alors le rappel a faire).
    assert not hasattr(UnitContext, "rarity"), (
        "UnitContext.rarity existe desormais : le verrou est leve, porter les canaux de degat de "
        "1448 et 1442 (HasRarity / UnitsWithRarity, Mythic) et retirer ce cliquet")
