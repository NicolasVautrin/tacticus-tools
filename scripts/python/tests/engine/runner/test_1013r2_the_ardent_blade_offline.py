"""#1013-r2 -- CONTRE-EPREUVE 100 % OFFLINE de la relique `TheArdentBlade` (1468, `adeptCelestine`) :
le JETON pose a l'init, les CINQ conjoints du trigger, les DEUX branches du behaviour, et
l'extinction du jeton.

Chaque etage est un COUPLE (un bras qui DOIT rendre le comportement, un bras qui DOIT le refuser).

  0. les ids, l'entree de registre et les constantes gameconfig sont LUS, pas devines ;
  1. le JETON 1462 est seede par la voie TERTIAIRE (`ctx.tertiary_ability`) et par elle SEULE ;
  2. le trigger : les CINQ conjoints, un bras negatif chacun -- dont le jeton ABSENT et le jeton
     DESACTIVE, qui sont DEUX etats distincts et doivent tous deux fermer (`onlyActive = 1`) ;
  3. branche RESURRECTION : une Geminae morte + une tuile libre -> `Resurrect(healType = 2 = Any)`.
     Le literal `2` est FIGE au site ; sa SEPARATION d'avec le defaut `0 = NonMechanical` est
     demontree sur un temoin MECANIQUE (sur `adeptSmnGeminaeSuperia`, qui n'est PAS mecanique, les
     deux valeurs coincident -- le dire est le resultat, pas l'omettre) ;
  4. branche ALTERNATIVE : pas de morte -> une Geminae VIVANTE **a portee `range`** agit ; une
     Geminae hors portee est ecartee (`IsInRange`), une Geminae MORTE aussi (`IsAlive`) ;
  5. le jeton est ETEINT et **PAS RETIRE**, et il l'est dans les DEUX branches (le
     `DeactivateEffect` est HORS du `If`).

TEMOIN NON DEGENERE : l'etage 4 assertionne qu'AU MOINS une Geminae est dans le pool avant de
verifier qu'une autre en est ecartee ; l'etage 3 assertionne que le montage rend bien la morte
ressuscitable AVANT d'opposer les deux `healType`. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest                                                               # noqa: E402,F401

import hexgeo                                                               # noqa: E402
from engine.dsl.effects import ExecutionContext                             # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                  # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType       # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType       # noqa: E402
from engine.entities.effect_target_type import EffectTargetType             # noqa: E402
from engine.entities.effect_type import EffectType                          # noqa: E402
from engine.entities.effects_state import EffectsState                      # noqa: E402
from engine.entities.heal_type import HealType                              # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.entities.unit_context import UnitContext                        # noqa: E402
from engine.entities.unit_selection_type import UnitSelectionType           # noqa: E402
from engine.entities.unit_team_selection_type import UnitTeamSelectionType  # noqa: E402
from engine.runner.abilities.attack_query import can_be_resurrected         # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state  # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,      # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.spawn import _seed_ability_owner_effects      # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent             # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import RELIC_ABILITY_TRIGGERS  # noqa: E402
from engine.entities.selectors.accessors import Target                      # noqa: E402
from engine.entities.selectors.tiles import Caster                          # noqa: E402
from engine.entities.triggers import AreEnemies                             # noqa: E402
from engine.runner.operations.triggers.loki.the_ardent_blade import (       # noqa: E402
    ABILITY_ID, GEMINAE_SELECTION, HP_VARIABLE, RANGE_CONSTANT, RESURRECT_HEAL_TYPE,
    THE_ARDENT_BLADE, THE_ARDENT_BLADE_EFFECT, TheArdentBladeTriggerAbility,
    _summon_unit_id, ardent_blade_behaviour_tree, ardent_blade_reachable_geminae,
    ardent_blade_geminae, ardent_blade_trigger_tree)
from engine.runner.prng import IntBasedMersenneTwister                      # noqa: E402
from engine.runner.state import State                                       # noqa: E402
from engine.streams.group_type import GroupType                             # noqa: E402
from engine.utilities.utility_type import UtilityType                       # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/the_ardent_blade.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/spawn.py",
        # Les primitives MIRRORS que les etages traversent.
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/abilities/attack_query.py",
        "scripts/python/engine/runner/operations/resurrect.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site par l'etage 0.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/heal_type.py",
        "scripts/python/engine/entities/effect_target_type.py",
        "scripts/python/engine/entities/unit_team_selection_type.py",
        "scripts/python/engine/streams/group_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Trois etages lisent le GAMECONFIG (`TheArdentBlade.constants.unitId`, `.range`, "
              "`variables.hp`), qui se perime SEPAREMENT du build ; l'etage 0 fige des ORDINAUX au "
              "site (1468 / 1462 / 0x36 / 0x16 / 0x1d / 2 / 6 / 1 / 0x28 / 0x20), qu'un "
              "renumerotage rendrait faux sans toucher aucun des chemins ci-dessus.",
}

COLS, ROWS = 8, 8
OWNER_ID, G_DEAD, G_NEAR, G_FAR, ENEMY_ID, FRIEND_ID, DECOY_ID = 10, 20, 30, 40, 50, 60, 70
HP = 40000
GEMINAE = "adeptSmnGeminaeSuperia"
LVL_TERTIAIRE, LVL_PASSIF = 2, 10


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board():
    from engine.entities.pathfinding.board import Board
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _ctx(uid, visual, *, traits=(), tertiary=None):
    c = UnitContext(entity_id=int(uid), visual_id=visual, traits=list(traits),
                    active_ability_level=LVL_PASSIF, passive_ability_level=LVL_PASSIF,
                    ability_variables_multiplier=100)
    c.traits_measured = True
    c.tertiary_ability = tertiary
    c.tertiary_ability_level = LVL_TERTIAIRE
    c.tertiary_ability_variables_multiplier = 100
    return c


def _unite(st, uid, visual, *, team=1, alive=True, pos=(0, 0), parent=None, traits=None,
           tertiary=None):
    import gameconfig as GC
    tr = list(traits) if traits is not None else list((GC.unit(visual) or {}).get("traits") or [])
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual, alive, parent_id=parent))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(HP if alive else 0, HP))
    e.add_component(StatsComponent(ctx=_ctx(uid, visual, traits=tr, tertiary=tertiary)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


def _state(*, dead_geminae=False, near_geminae=False, far_geminae=False, jeton=True,
           jeton_actif=True, entoure=False):
    """Etat synthetique.

    `adeptCelestine` (team 1) en (2,2) porte la relique en TERTIAIRE ; un ennemi normal ; un allie ;
    un decoy `Steppable` (pour le bras negatif d'`IsNormalUnit`) ; et, a la demande, une Geminae
    MORTE (loin), une Geminae VIVANTE A PORTEE, une Geminae VIVANTE HORS PORTEE.

    `entoure` bouche les six voisins du porteur -> `CanAddUnit(AdjacentTiles(Owner))` rend VIDE,
    donc la condition du `If` tombe MEME avec une morte : c'est le second conjoint."""
    st = State()
    st.board = _board()
    st.effects = EffectsState.seed({})
    st.rng = IntBasedMersenneTwister(31337)
    _unite(st, OWNER_ID, "adeptCelestine", team=1, pos=(2, 2), tertiary=ABILITY_ID)
    _unite(st, ENEMY_ID, "orksRuntherd", team=2, pos=(7, 7))
    _unite(st, FRIEND_ID, "adeptCanoness", team=1, pos=(0, 7))
    # `Steppable` -> `IsNormalUnit` FAUX (`!HasTrait(Object) && !HasTrait(Steppable)`).
    _unite(st, DECOY_ID, "orksRuntherd", team=2, pos=(7, 0), traits=["Steppable"])
    if dead_geminae:
        _unite(st, G_DEAD, GEMINAE, team=1, alive=False, pos=(6, 6), parent=OWNER_ID)
    if near_geminae:
        _unite(st, G_NEAR, GEMINAE, team=1, pos=(2, 4), parent=OWNER_ID)      # d = 2 <= range 3
    if far_geminae:
        _unite(st, G_FAR, GEMINAE, team=1, pos=(7, 2), parent=OWNER_ID)       # d = 5 > range 3
    if entoure:
        for i, (c, r) in enumerate(hexgeo.neighbors(2, 2)):
            _unite(st, 200 + i, "orksRuntherd", team=2, pos=(c, r))
    if jeton:
        _seed_ability_owner_effects(st, OWNER_ID, "adeptCelestine", 100, ability_level=LVL_PASSIF)
        if not jeton_actif:
            for e in st.effects.by_unit.get(OWNER_ID, []):
                if int(e.effect_type) == THE_ARDENT_BLADE_EFFECT:
                    e.active = False
    return st


def _ev(target_id=ENEMY_ID, actor_id=OWNER_ID):
    """`On(0x36 = UnitDefeated)` -- `dispatch/move_death.unit_defeated_triggers` publie
    `actor = le TUEUR`, `target = la VICTIME`."""
    return TriggerEvent(int(EventTriggerType.UnitDefeated), actor_id, target_id,
                        ranged=False, profile=None)


def _feuilles(noeud, out=None):
    """Parcours des conjoints d'un arbre de trigger (`TriggerAnd` porte `a`/`b`) -- meme forme que
    l'helper homonyme de `test_963r1_unit_team_selection_offline.py`."""
    out = [] if out is None else out
    out.append(noeud)
    for attr in ("a", "b"):
        v = getattr(noeud, attr, None)
        if hasattr(v, "evaluate"):
            _feuilles(v, out)
    return out


def _jeton(state, uid=OWNER_ID):
    return [e for e in state.effects.by_unit.get(int(uid), [])
            if int(e.effect_type) == THE_ARDENT_BLADE_EFFECT and not e.consumed]


# --------------------------------------------------------------------------------------------
# Etage 0 -- ids, registre et constantes gameconfig, LUS
# --------------------------------------------------------------------------------------------

def test_ids_registre_et_constantes_sont_lus_au_decompile():
    assert int(THE_ARDENT_BLADE) == 0x5bc == 1468
    assert int(TriggeredAbilityType.TheArdentBlade) == THE_ARDENT_BLADE
    assert THE_ARDENT_BLADE_EFFECT == 0x5b6 == 1462
    assert int(EffectType.TheArdentBlade) == THE_ARDENT_BLADE_EFFECT
    assert TheArdentBladeTriggerAbility.event_id == 0x36 == 54 == int(
        EventTriggerType.UnitDefeated)
    assert int(AbilityConstantType.unitId) == 0x0
    assert int(RANGE_CONSTANT) == 0x16 == 22 == int(AbilityConstantType.range)
    assert int(HP_VARIABLE) == 0x1d == 29 == int(AbilityVariableType.hp)
    assert int(RESURRECT_HEAL_TYPE) == 2 == int(HealType.Any)
    assert int(EffectTargetType.Both) == 6
    assert int(UnitTeamSelectionType.ByOriginalTeam) == 1
    assert int(GEMINAE_SELECTION) == 0 == int(UnitSelectionType.Any)
    assert int(GroupType.Ability_Other) == 0x28 == 40
    assert int(GroupType.Ability_Attack) == 0x20 == 32
    assert int(UtilityType.Tile) == 7
    assert RELIC_ABILITY_TRIGGERS.get(ABILITY_ID) == [TheArdentBladeTriggerAbility]


def test_le_meme_ordinal_22_nomme_AUTRE_CHOSE_dans_l_autre_enum():
    """`AbilityConstantType.range` = 22 et `AbilityVariableType.blockDmg_2` = 22 : confondre
    `GetNumberConstant` et `GetVariableForLevel` ne leverait AUCUNE erreur -- il lirait juste la
    mauvaise cle du gameconfig. C'est le NOM qui discrimine, jamais l'ordinal."""
    autre = AbilityVariableType(int(RANGE_CONSTANT))
    assert autre.name != RANGE_CONSTANT.name, (
        "TEMOIN DEGENERE : les deux enums nomment pareil a l'ordinal 22, la confusion serait "
        "indetectable et cette assertion ne dirait rien")


def test_les_trois_constantes_sont_lues_au_gameconfig():
    """`case-1013r2` sec.5 les disait « non lisibles hors ligne » : c'est vrai du SEED BC, faux du
    GAMECONFIG. Le `'adeptSmnGeminaeSuperia'` de l'enonce etait juste -- il est desormais MESURE."""
    import gameconfig as GC
    a = GC.ability(ABILITY_ID) or {}
    assert _summon_unit_id() == GEMINAE
    assert (a.get("constants") or {}).get(RANGE_CONSTANT.name) is not None
    paliers = (a.get("variables") or {}).get(HP_VARIABLE.name)
    assert paliers and len(paliers) >= LVL_TERTIAIRE


# --------------------------------------------------------------------------------------------
# Etage 1 -- le JETON, seede par la voie TERTIAIRE et par elle SEULE
# --------------------------------------------------------------------------------------------

def test_le_jeton_est_seede_par_la_voie_tertiaire():
    st = _state()
    assert len(_jeton(st)) == 1, (
        "`ABILITY_INIT_OWNER_EFFECTS['TheArdentBlade']` n'a pas seede 1462 : "
        "`_seed_ability_owner_effects` ne lit pas `ctx.tertiary_ability`")
    assert _jeton(st)[0].active is True, "le jeton seede n'est pas ACTIF (`ActivateEffect`)"


def test_sans_relique_equipee_aucun_jeton():
    """CONTRE-EPREUVE : le kit d'`adeptCelestine` ne porte PAS `TheArdentBlade` -- sans
    `ctx.tertiary_ability`, rien ne doit etre seede."""
    st = State()
    st.board = _board()
    st.effects = EffectsState.seed({})
    _unite(st, OWNER_ID, "adeptCelestine", team=1, pos=(2, 2), tertiary=None)
    _seed_ability_owner_effects(st, OWNER_ID, "adeptCelestine", 100, ability_level=LVL_PASSIF)
    assert _jeton(st) == []


# --------------------------------------------------------------------------------------------
# Etage 2 -- le trigger : CINQ conjoints, un bras negatif chacun
# --------------------------------------------------------------------------------------------

def test_le_trigger_MORD_quand_les_cinq_conjoints_sont_vrais():
    """Le bras POSITIF -- sans lui, les cinq bras negatifs passeraient sur un arbre mort."""
    assert TheArdentBladeTriggerAbility(OWNER_ID).matches(_state(), _ev()) is True


def test_un_ACTEUR_qui_n_est_pas_le_porteur_ferme():
    assert TheArdentBladeTriggerAbility(OWNER_ID).matches(
        _state(), _ev(actor_id=FRIEND_ID)) is False


def test_une_victime_STEPPABLE_ferme():
    """`IsNormalUnit(Target@+0x60)` = `!HasTrait(Object) && !HasTrait(Steppable)`."""
    assert TheArdentBladeTriggerAbility(OWNER_ID).matches(
        _state(), _ev(target_id=DECOY_ID)) is False


def test_une_victime_AMIE_ferme():
    """`AreEnemies(Owner, Target, 1 = ByOriginalTeam)`.

    ⚠ Ce bras est DEGENERE sur l'axe du 3e argument, et c'est dit : `FRIEND_ID` est allie par son
    equipe COURANTE **et** par son ORIGINE, donc il fermerait avec l'un ou l'autre litteral. Le
    regime discriminant est celui du test suivant."""
    assert TheArdentBladeTriggerAbility(OWNER_ID).matches(
        _state(), _ev(target_id=FRIEND_ID)) is False


def test_le_litteral_ByOriginalTeam_est_PASSE_au_noeud_de_l_arbre():
    """Le 3e argument d'`AreEnemies` est `1 = ByOriginalTeam` (type DECLARE
    `IdunBattle.Entities.Enum.UnitTeamSelectionType` dans `frida/methods.tsv`), et le DEFAUT du
    noeud porte est `ByCurrentTeam` : une constante nommee dans le module mais non PASSEE serait un
    faux temoin de fidelite -- exactement ce que #963-r1 a du corriger sur `RedRampage`.

    ⚠ C'est le SECOND des deux sites `ByOriginalTeam` d'`AreEnemies` du build ; l'autre est
    `...RedRampage_BuffAbility$$CreateTrigger`. Le recensement EXHAUSTIF vit dans
    `test_963r1_unit_team_selection_offline.py`, qui verifie AUSSI ce littéral -- ici on le garde au
    plus pres du port."""
    noeuds = [n for n in _feuilles(ardent_blade_trigger_tree()) if isinstance(n, AreEnemies)]
    assert len(noeuds) == 1, "l'arbre du trigger porte exactement un `AreEnemies`"
    assert noeuds[0].selection_type == int(UnitTeamSelectionType.ByOriginalTeam)
    assert int(UnitTeamSelectionType.ByOriginalTeam) != int(UnitTeamSelectionType.ByCurrentTeam), \
        "TEMOIN DEGENERE : les deux membres coincident, l'assertion ci-dessus ne dirait rien"


def test_une_victime_POSSEDEE_reste_une_ENNEMIE_par_son_ORIGINE():
    """LE regime discriminant du 3e argument -- le SEUL ou `ByCurrentTeam` et `ByOriginalTeam`
    repondent differemment.

    Une unite passee sous MON controle par `IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute`
    (l'unique producteur natif du regime, declenche par l'effet `1209`) est ALLIEE au courant et
    ENNEMIE a l'origine. Le natif lisant l'ORIGINE, la relique doit MORDRE quand Celestine l'abat --
    avec le defaut `ByCurrentTeam` le trigger fermerait, silencieusement.

    Le couple `(team, originalTeam)` n'est PAS ecrit a la main : l'Operation le produit."""
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    st = _state()
    assert ChangeUnitOwnerOperation.execute(st, ENEMY_ID, OWNER_ID) is True, \
        "l'owner-swap doit AVOIR LIEU, sinon le regime discriminant n'existe pas"
    entities = entities_from_state(st, OWNER_ID, ENEMY_ID, actor_id=OWNER_ID)
    victime = next(u for u in entities.units if u.get("id") == ENEMY_ID)
    # TEMOIN NON DEGENERE : sans cet ecart, les deux litteraux rendraient le meme verdict.
    assert victime.get("team") != victime.get("originalTeam"), (
        "regime DEGENERE : le substrat ne publie pas `originalTeam` distinct de `team` apres "
        "l'owner-swap -- lu (%r, %r)" % (victime.get("team"), victime.get("originalTeam")))
    assert AreEnemies(Caster(), Target(),
                      int(UnitTeamSelectionType.ByCurrentTeam)).evaluate(entities) is False, \
        "equipe COURANTE : la victime possedee est une ALLIEE (le bras que le DEFAUT prendrait)"
    assert TheArdentBladeTriggerAbility(OWNER_ID).matches(st, _ev()) is True, (
        "la relique n'a pas mordu sur une victime possedee : le noeud lit l'equipe COURANTE au lieu "
        "de l'ORIGINE")


def test_sans_jeton_le_trigger_ferme():
    assert TheArdentBladeTriggerAbility(OWNER_ID).matches(_state(jeton=False), _ev()) is False


def test_un_jeton_DESACTIVE_ferme_aussi():
    """LE cran du cycle. `onlyActive = 1` : une instance PRESENTE mais eteinte doit fermer le
    trigger EXACTEMENT comme une instance absente. C'est ce qui fait de la relique un jeton A UN
    COUP -- si le port lisait la seule PRESENCE, elle se redeclencherait a chaque kill."""
    st = _state(jeton_actif=False)
    assert len(_jeton(st)) == 1, "montage : l'instance a disparu au lieu d'etre eteinte"
    assert TheArdentBladeTriggerAbility(OWNER_ID).matches(st, _ev()) is False


# --------------------------------------------------------------------------------------------
# Etage 3 -- branche RESURRECTION
# --------------------------------------------------------------------------------------------

def test_une_geminae_morte_et_une_tuile_libre_declenchent_la_RESURRECTION():
    st = _state(dead_geminae=True)
    assert can_be_resurrected(st, G_DEAD, int(RESURRECT_HEAL_TYPE)) is True, \
        "montage : la Geminae morte n'est pas ressuscitable, l'etage ne prouverait rien"
    r = TheArdentBladeTriggerAbility(OWNER_ID).execute_behaviour(st, _ev())
    assert r["resurrections"], "la branche THEN n'a ressuscite personne"
    assert [x["resurrected"] for x in r["resurrections"]] == [G_DEAD]
    assert r["attacks"] is None, "la branche ELSE a AUSSI joue : le `If` n'est pas exclusif"
    assert r["hp"] > 0, "le montant `Get(GetVariableForLevel(hp))` est nul"


def test_sans_tuile_libre_la_condition_TOMBE_malgre_la_morte():
    """Le SECOND conjoint de la condition. Le porteur entoure -> `CanAddUnit(AdjacentTiles(Owner))`
    rend VIDE -> `AmountIsGreaterThanZero(tile)` faux -> branche ELSE, meme avec une morte."""
    st = _state(dead_geminae=True, near_geminae=True, entoure=True)
    r = TheArdentBladeTriggerAbility(OWNER_ID).execute_behaviour(st, _ev())
    assert not r["resurrections"], "resurrection sans tuile libre : le 2e conjoint ne mord pas"
    assert r["attacks"] is not None, "la branche ELSE n'a pas ete prise"


def test_le_healType_est_ANY_et_la_valeur_2_SEPARE_bien_deux_regimes():
    """Le literal `2 = HealType.Any` est FIGE au site. Sa SEPARATION d'avec le defaut du noeud
    (`0 = NonMechanical`) est demontree sur un temoin MECANIQUE.

    ⚠ MESURE, et elle nuance l'enonce du residu : `adeptSmnGeminaeSuperia` a pour traits
    `['Summon', 'Flying']` -- il n'est PAS mecanique, donc sur le porteur REEL les deux valeurs
    coincident et le defaut n'aurait rien casse. Ecrire `Any` reste le mirror FIDELE (c'est le
    litteral), et la separation reste REELLE pour toute cible mecanique."""
    import gameconfig as GC
    assert "Mechanical" not in ((GC.unit(GEMINAE) or {}).get("traits") or []), (
        "le gameconfig a change : la Geminae est devenue mecanique, cette docstring est perimee")
    st = _state(dead_geminae=True)
    assert can_be_resurrected(st, G_DEAD, 0) is True and can_be_resurrected(st, G_DEAD, 2) is True
    # TEMOIN NON DEGENERE : une cible MECANIQUE separe les deux `healType`.
    _unite(st, 99, "necroSmnWarrior", team=1, alive=False, pos=(0, 0), parent=OWNER_ID)
    assert can_be_resurrected(st, 99, 0) is False, (
        "TEMOIN DEGENERE : `healType = 0` accepte une cible mecanique, la distinction ne mord pas")
    assert can_be_resurrected(st, 99, int(RESURRECT_HEAL_TYPE)) is True


# --------------------------------------------------------------------------------------------
# Etage 4 -- branche ALTERNATIVE (`PerformAIAttack`), et son filtre a DEUX conjoints
# --------------------------------------------------------------------------------------------

def _pool(state, range_value=3):
    entities = entities_from_state(state, OWNER_ID, ENEMY_ID, actor_id=OWNER_ID)
    return sorted(u["id"] for u in
                  ardent_blade_reachable_geminae(ardent_blade_geminae(),
                                                 range_value).source.evaluate(entities))


def test_le_filtre_garde_la_geminae_A_PORTEE_et_ecarte_celle_qui_est_LOIN():
    st = _state(near_geminae=True, far_geminae=True)
    assert ardent_blade_geminae().evaluate(
        entities_from_state(st, OWNER_ID, ENEMY_ID, actor_id=OWNER_ID)), \
        "montage : `UnitsWithId(Children(Owner), unitId, Any)` rend VIDE -- rien a filtrer"
    assert _pool(st) == [G_NEAR], "le filtre `IsInRange(Owner, It, Get(range))` ne mord pas"


def test_le_filtre_ecarte_une_geminae_MORTE_meme_a_portee():
    """`IsAlive(It@+0x68)` : le `Filter` porte sur l'ensemble COMPLET (`Any`), c'est le predicat
    qui trie."""
    st = _state(near_geminae=True)
    from engine.runner.components import UnitComponent as _UC
    st.get_entity(G_NEAR).get_component(_UC).alive = False
    assert _pool(st) == []


def test_sans_morte_une_geminae_vivante_a_portee_AGIT():
    st = _state(near_geminae=True)
    r = TheArdentBladeTriggerAbility(OWNER_ID).execute_behaviour(st, _ev())
    assert not r["resurrections"]
    assert r["attacks"] is not None, "la feuille `PerformAIAttack` n'a pas ete atteinte"


# --------------------------------------------------------------------------------------------
# Etage 5 -- le jeton est ETEINT, pas RETIRE, et dans les DEUX branches
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("montage", ({"dead_geminae": True}, {"near_geminae": True}, {}))
def test_le_jeton_tombe_dans_TOUTES_les_branches(montage):
    """`op_BitwiseAnd` a la racine : le `DeactivateEffect` est HORS du `If`. Meme le montage VIDE
    (ni morte, ni vivante a portee) doit consommer le jeton."""
    st = _state(**montage)
    r = TheArdentBladeTriggerAbility(OWNER_ID).execute_behaviour(st, _ev())
    assert r["token_deactivated"] is True, "le jeton n'a pas ete eteint"
    assert _jeton(st) and _jeton(st)[0].active is False


def test_le_jeton_SURVIT_a_son_extinction():
    """`DeactivateEffect` DESACTIVE, il ne RETIRE PAS (`RemoveEffect` = slot DISTINCT, jamais
    emprunte). Un port qui supprimerait l'instance passerait l'assertion `active is False`
    ci-dessus par ACCIDENT -- c'est cette ligne-ci qui separe les deux."""
    st = _state(dead_geminae=True)
    TheArdentBladeTriggerAbility(OWNER_ID).execute_behaviour(st, _ev())
    assert len(_jeton(st)) == 1, "l'instance 1462 a ete RETIREE au lieu d'etre eteinte"


def test_le_second_kill_ne_redeclenche_PAS():
    """La consequence OBSERVABLE du jeton : une fois eteint, le 5e conjoint du trigger ferme."""
    st = _state(dead_geminae=True)
    ab = TheArdentBladeTriggerAbility(OWNER_ID)
    assert ab.matches(st, _ev()) is True
    ab.execute_behaviour(st, _ev())
    assert ab.matches(st, _ev()) is False, (
        "la relique se redeclenche : le cycle `HasEffect(onlyActive)` / `DeactivateEffect` est rompu")


# --------------------------------------------------------------------------------------------
# Etage 6 -- le QUIRK du selecteur PARTAGE (le `PickRandomly` est evalue DEUX fois)
# --------------------------------------------------------------------------------------------

def test_le_selecteur_du_groupe_est_le_MEME_objet_que_celui_du_PerformAIAttack():
    """`Group(PerformAIAttack(chosen, ...), chosen, 0x20)` : le natif passe le MEME
    `PickRandomAmountSelector` aux deux places, et `GroupBehaviour$$Execute` l'EVALUE avant le child
    (#504). Le port doit donc partager l'objet -- sinon les deux tirages PRNG du natif deviendraient
    un seul, et TOUT le flux aval divergerait."""
    tree = ardent_blade_behaviour_tree(1000, 3)
    branche_else = tree.left.otherwise           # `Seq(If(cond, then, else), deact)`
    assert branche_else.targets_sel is branche_else.child.tile_selector, (
        "le selecteur de groupe et celui du `PerformAIAttack` ne sont pas le MEME objet")
    assert tree.right.effect_type == THE_ARDENT_BLADE_EFFECT
