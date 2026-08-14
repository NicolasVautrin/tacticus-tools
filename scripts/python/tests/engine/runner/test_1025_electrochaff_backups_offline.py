"""#1025 -- CONTRE-EPREUVE 100 % OFFLINE des deux MYTHIQUES de MACHINE OF WAR portees par la
tranche : `ElectrochaffBackups` (1454, `tauBroadside`) et `MoreGitzOverEre` (1456,
`orksRukkatrukk`).

Ce que ces cliquets verrouillent -- CHAQUE etage est un COUPLE (un bras qui DOIT rendre le
comportement, un bras qui DOIT le refuser), parce qu'un test qui n'a qu'un bras peut passer pour
une raison qui n'a rien a voir avec ce qu'il croit mesurer :

  1. branche A `On(0x3e = EffectAdded) & TriggeringEffectIs(0x462 = Markerlight)` -- pose 1446 ;
     bras negatif : un AUTRE effet declencheur, et `triggering_effect` NON threade ;
  2. branche B `On(0x0f = DamageTaken) & IsRangedAttack()` -- pose 1446 a distance ; bras negatif :
     cible ADJACENTE (le gate ranged du port sur ce vecteur est `!AreEntitiesAdjacent`) ;
  3. le tronc COMMUN `AreEnemies(Owner, Target) & IsNormalUnit(Target)` -- bras negatif : cible
     AMIE, et cible `Steppable` ;
  4. **`ChangeType.Set`, PAS `Add`** -- le seul endroit ou une confusion serait numerique et
     SILENCIEUSE. Le natif emet `On(0x0f)` PAR COUP (mesure live #1025 : **5** blocs
     `[Ability_Power e=81 <<ElectrochaffBackups>>]` pour UNE attaque de 5 coups, et la duree
     observee reste `r2`). Avec `Add`, cinq declenchements donneraient `5 x 2 = 10` tours ;
  5. `MoreGitzOverEre` : l'entree `ABILITY_INIT_OWNER_EFFECTS` nomme l'effet que le natif nomme
     (`$$GetEffectType` = `return 0x5a9`), pas un nom devine ;
  6. **le VERROU DE RARETE est fige avec sa raison** : les deux effets 1446 et 1449 sont HORS
     d'`EFFECT_CLASSES`, parce que leur canal de degat ouvre sur `HasRarity(..., 5 = Mythic)` et
     qu'aucun canal `rarity` n'existe cote port (residu `#1025-r1`). Ce cliquet n'interdit pas de
     les inscrire -- il oblige a le faire EN CONNAISSANCE, en relisant le decompile plutot qu'en
     copiant un voisin de forme.

TEMOIN NON DEGENERE -- l'etage 4 serait vide si `convert_rounds_to_turns` rendait 0 : la duree est
donc ASSERTIONNEE > 0 avant d'etre comparee. Meme discipline que le << test vide qui passe pour
vert >> du CLAUDE.md. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest                                                              # noqa: E402

import hexgeo                                                              # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.runner.abilities.base import convert_rounds_to_turns           # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent            # noqa: E402
from engine.runner.operations.effects import ChangeEffectTurnsOperation    # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.runner.operations.triggers.loki.electrochaff_backups import (  # noqa: E402
    ElectrochaffBackupsOnMarkerlightAbility, ElectrochaffBackupsOnRangedDamageAbility,
    ELECTROCHAFF_BACKUPS, ELECTROCHAFF_BACKUPS_ID, ELECTROCHAFF_EFFECT, MARKERLIGHT,
    electrochaff_rounds)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Les deux faces portees par #1025 et leurs registres.
        "scripts/python/engine/runner/operations/triggers/loki/electrochaff_backups.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/spawn.py",
        # #1025-r1 -- la face DEGAT (1446) et les DEUX canaux qui l'alimentent : `tgt_rarity`
        # (rarete de la CIBLE) et `team_by_id` (resolution de l'`EffectSource`), threades sur les
        # deux faces. Un ctx qui perdrait l'une des deux cles rendrait l'effet muet SANS ERREUR.
        "scripts/python/engine/entities/effects/loki/damage_reduction.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        "scripts/python/engine/playbook/prediction/abilities.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/entities/rarity.py",
        # Les primitives MIRRORS que les etages lisent : la duree, le refresh, les gates.
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/abilities/base.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site par l'etage 0.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        # Le VERROU que l'etage 6 garde : le jour ou ce champ apparait, il faut relire.
        "scripts/python/engine/entities/unit_context.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Un etage lit le GAMECONFIG (`ElectrochaffBackups.constants.nrOfRounds`), qui se "
              "perime SEPAREMENT du build ; trois etages figent des ORDINAUX au site (1454 / 1446 "
              "/ 1122 / 1449 / 1456), qu'un renumerotage rendrait faux sans toucher aucun des "
              "chemins ci-dessus ; et l'etage 6 garde une ABSENCE (`UnitContext.rarity`), donc un "
              "ajout n'importe ou dans le port peut le concerner.",
}

COLS, ROWS = 6, 6
OWNER_ID, ENEMY_FAR_ID, ENEMY_NEAR_ID, FRIEND_ID, STEPPABLE_ID = 10, 20, 30, 40, 50
HP = 50000
#: 2 joueurs dans le `turnOrder` -> `ConvertRoundsToTurns(1) = 2`, la valeur MESUREE live (`r2`).
PLAYER_COUNT = 2


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _state():
    """Etat synthetique : le PORTEUR (team 1) + trois cibles (team 2 loin, team 2 adjacente,
    team 1 amie) + une entite `Steppable` ennemie. Les positions sont CHOISIES pour que le gate
    `!AreEntitiesAdjacent` du vecteur `DamageTaken` separe (loin d>=2, pres d==1)."""
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
        {"id": OWNER_ID, "visualId": "tauBroadside", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        # `ENEMY_FAR` est a d>=2 de `ENEMY_NEAR` (l'attaquant du vecteur DamageTaken) ;
        # `ENEMY_NEAR` lui est ADJACENT -> les deux bras du gate ranged.
        {"id": ENEMY_FAR_ID, "visualId": "orksRuntherd", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 4, "row": 4}, "effects": []},
        {"id": ENEMY_NEAR_ID, "visualId": "tauCrisis", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 4, "row": 3}, "effects": []},
        {"id": FRIEND_ID, "visualId": "tauCrisis", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 2, "row": 1}, "effects": []},
    ]
    decision = {"currentPlayer": 1, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": HP, "hpMax": HP} for u in units],
               "counts": {"player": PLAYER_COUNT + 1}}
    st = load_state(decision, observe, board=Board(tiles, adjacency="evenq"))
    if st.effects is None:                      # aucun effet au seed -> `load_state` laisse None
        from engine.entities.effects_state import EffectsState
        st.effects = EffectsState.seed({})
    assert st.effects is not None, "montage : EffectsState absent -> aucune pose possible"
    return st


def _ev_markerlight(target_id, effect_type=None, source_id=OWNER_ID):
    """Le `TriggerEvent` que publie `dispatch/move_death.effect_added_triggers` : `actor` = la
    SOURCE de l'effet, `target` = la cible de la pose, `triggering_effect` = le type pose."""
    return TriggerEvent(int(EventTriggerType.EffectAdded), source_id, target_id,
                        ranged=False, profile=None,
                        triggering_effect=(MARKERLIGHT if effect_type is None else effect_type))


def _ev_damage(target_id, source_id=ENEMY_NEAR_ID):
    """Le `TriggerEvent` que publie `dispatch/attack.damage_taken_triggers` : `actor` = la source
    du degat, `target` = la VICTIME. `ability_type` n'y est PAS threade (cf. `#1025-r2`)."""
    return TriggerEvent(int(EventTriggerType.DamageTaken), source_id, target_id,
                        ranged=False, profile=None)


def _has_1446(state, uid):
    return any(e.effect_type == ELECTROCHAFF_EFFECT and not e.consumed
               for e in state.effects.by_unit.get(int(uid), []))


def _turns_1446(state, uid):
    e = next((x for x in state.effects.by_unit.get(int(uid), [])
              if x.effect_type == ELECTROCHAFF_EFFECT and not x.consumed), None)
    return None if e is None else e.remaining_turns


# --------------------------------------------------------------------------------------------
# Etage 0 -- l'appariement ability <-> effet, et la voie de registration, sont LUS
# --------------------------------------------------------------------------------------------

def test_ids_et_registre_sont_lus_au_decompile():
    """`ElectrochaffBackupsAbility` = `TriggeredAbilityType` 0x5ae ; l'effet pose par son
    `$$CreateBehaviour` = `EffectType` 0x5a6 ; le declencheur de la branche A = 0x462.
    Ces trois ordinaux sont ECRITS ICI pour qu'un renumerotage du build les fasse ROUGIR au SITE
    (le mirror d'enum, lui, redeviendrait vert apres regeneration -- cf. CLAUDE.md)."""
    assert int(ELECTROCHAFF_BACKUPS) == 0x5ae == 1454
    assert ELECTROCHAFF_EFFECT == 0x5a6 == 1446
    assert MARKERLIGHT == 0x462 == 1122
    assert int(EffectType.ElectrochaffBackups_DamageReductionPct) == ELECTROCHAFF_EFFECT
    assert int(TriggeredAbilityType.ElectrochaffBackups) == int(ELECTROCHAFF_BACKUPS)
    from engine.runner.operations.triggers.dispatch.registry import RELIC_ABILITY_TRIGGERS
    # La voie de registration COTE COMBAT d'une mythique EST celle de la relique (meme champ
    # `BC.Units[].TertiaryAbility`, meme `TryAdd(..., 3)`) -- cf. le commentaire du registre.
    inscrites = RELIC_ABILITY_TRIGGERS.get(ELECTROCHAFF_BACKUPS_ID) or []
    assert set(inscrites) == {ElectrochaffBackupsOnMarkerlightAbility,
                              ElectrochaffBackupsOnRangedDamageAbility}, inscrites


def test_more_gitz_over_ere_nomme_l_effet_du_decompile():
    """`MoreGitzOverEreAbility$$GetEffectType` a pour corps ENTIER `return 0x5a9`. L'entree
    `ABILITY_INIT_OWNER_EFFECTS` doit nommer CET effet-la, pas un homonyme devine."""
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS
    assert int(EffectType.MoreGitzOverEre_ExtraDamagePct) == 0x5a9 == 1449
    assert int(TriggeredAbilityType.MoreGitzOverEre) == 0x5b0 == 1456
    assert (ABILITY_INIT_OWNER_EFFECTS.get("MoreGitzOverEre")
            == [EffectType.MoreGitzOverEre_ExtraDamagePct.name])


def test_le_seed_offline_pose_l_owner_effect_de_more_gitz():
    """L'entree `ABILITY_INIT_OWNER_EFFECTS` doit MORDRE sur la voie TERTIAIRE.

    ⚠ POURQUOI CE CLIQUET EXISTE, et c'est une MESURE : l'etage live
    (`test_1025_more_gitz_over_ere_live.py::test_le_port_voit_l_owner_effect_live_offline`) passe
    **AUSSI SANS cette entree** -- l'effet 1449 arrive par la CAPTURE (`decisionView.mows[]
    .effects`), sa `CreateActiveCondition` heritee etant la constante VRAIE. L'entree n'est donc un
    FILET que pour les chemins PUREMENT offline, et seul un test offline peut le montrer. Retirer
    l'entree et ne garder que le live serait un VERT qui ment."""
    from engine.runner.components import StatsComponent
    from engine.entities.unit_context import UnitContext
    from engine.runner.operations.spawn import _seed_ability_owner_effects
    st = _state()
    ctx = UnitContext(entity_id=OWNER_ID, visual_id="orksRukkatrukk",
                      tertiary_ability="MoreGitzOverEre", tertiary_ability_level=1,
                      tertiary_ability_variables_multiplier=100)
    st.get_entity(OWNER_ID).add_component(StatsComponent(ctx))
    poses = _seed_ability_owner_effects(st, OWNER_ID, "orksRukkatrukk", 100, ability_level=1)
    assert EffectType.MoreGitzOverEre_ExtraDamagePct.name in poses, poses
    assert any(e.effect_type == int(EffectType.MoreGitzOverEre_ExtraDamagePct)
               for e in st.effects.by_unit.get(OWNER_ID, []))


def test_verrou_de_rarete_fige_avec_sa_raison():
    """REQUALIFIE UNE SECONDE FOIS, PAR #1025-r1 -- il a ROUGI, et il a eu RAISON.

    Ce cran a deja ete requalifie une fois (#999-r3) : il gardait alors l'ABSENCE de
    `UnitContext.rarity`, et il a rougi le jour ou le canal est arrive. Il vient de rougir a
    nouveau, sur `ElectrochaffBackups_DamageReductionPct not in EFFECT_CLASSES` -- exactement ce
    qu'il etait ecrit pour faire, et exactement au bon moment : l'inscription de 1446 devait
    forcer la relecture de ce fichier.

    Etat d'AUJOURD'HUI, et ce que ce cran garde maintenant :
      * **1446 EST INSCRIT** (#1025-r1). Son verrou n'etait PAS un `CreateTargetSelector` (la
        ligne de backlog se trompait : `search_symbols_by_name` rend `.ctor` + `$$CreateDamage
        Modifier`, aucun selecteur) mais le canal `att_ctx["tgt_rarity"]`, threade depuis les
        NEUF sites de construction du ctx du canal ATTAQUE, sur les DEUX faces ;
      * **1449 restait dehors, et pour une AUTRE cause** : `MoreGitzOverEre_ExtraDamagePctEffect`,
        lui, a bien un `$$CreateTargetSelector` -- c'est donc une AURA, et son porteur est la MoW
        `orksRukkatrukk`. Le blocage etait `#999-r3-r1-r1` (une MoW n'entrait dans l'univers de
        porteurs d'AUCUN des deux agregateurs d'aura, sur AUCUNE des deux faces), pas la rarete ;
      * le CANAL de rarete repond toujours -- `UnitContext.rarity`, `triggers.HasRarity`,
        `selectors.units.UnitsWithRarity`. C'est assertionne ici pour que son retrait rougisse.

    REQUALIFIE UNE TROISIEME FOIS, PAR #1025-r1 (volet PORT) -- il a ROUGI une troisieme fois, au
    moment prevu. `#999-r3-r1-r1` est REPARE (le filtre positionnel des quatre sites etait un
    ARTEFACT du port : le natif itere l'ETAT board-wide), donc **1449 EST INSCRIT**. Son canal est
    `create_aura_defense_damage_malus_for_ally` avec
    `AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"` -- le beneficiaire du selecteur est la CIBLE DU
    COUP (`get_OwnerIsTarget`), pas l'attaquant. Le port, ses deux branches de selecteur et ses
    contre-bras : `test_1035r2_1025r1_auras_mow_offline.py`.

    Ce que ce cran garde MAINTENANT : que l'inscription n'a pas coute son gate de RARETE. Un 1449
    inscrit sans `HasRarity(Caster, Mythic)` serait d'accord avec le natif dans TOUT le regime par
    defaut du harnais (`targetRarity = 5` partout) et faux des qu'une unite ne l'est pas."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.damage_reduction import (
        ElectrochaffBackupsDamageReductionPctEffect)
    from engine.entities.rarity import Rarity
    from engine.entities.selectors.units import UnitsWithRarity        # noqa: F401 (existence)
    from engine.entities.triggers import HasRarity                      # noqa: F401 (existence)
    from engine.entities.unit_context import UnitContext
    assert (EFFECT_CLASSES.get(EffectType.ElectrochaffBackups_DamageReductionPct.name)
            is ElectrochaffBackupsDamageReductionPctEffect), (
        "1446 a QUITTE le registre : la face DEGAT d'ElectrochaffBackups redevient muette. "
        "Relire docs/rl/case-1025-mythiques-mow-verrou-rarete.md.")
    assert EffectType.MoreGitzOverEre_ExtraDamagePct.name in EFFECT_CLASSES, (
        "1449 a QUITTE le registre : son canal AURA DEFENSE est porte depuis #1025-r1 (volet "
        "PORT), et son blocage #999-r3-r1-r1 est REPARE sur les DEUX faces. L'en lever le "
        "retire, ca ne le corrige pas.")
    # ⚠ L'INSCRIPTION NE DOIT PAS AVOIR COUTE LE GATE. Contre-bras MINIMAL (les autres sont dans
    # `test_1035r2_1025r1_auras_mow_offline.py`) : un attaquant NON Mythic, puis un attaquant dont
    # la rarete n'est pas mesuree. Les deux doivent rendre `None`.
    _mg = EFFECT_CLASSES[EffectType.MoreGitzOverEre_ExtraDamagePct.name](
        name=EffectType.MoreGitzOverEre_ExtraDamagePct.name,
        effect_type=int(EffectType.MoreGitzOverEre_ExtraDamagePct), ability_level=1)
    _c = {"owner_id": 90, "owner_team": 1, "tgt_id": 20, "tgt_team": 2, "att_id": 11,
          "att_team": 1, "is_melee": True, "is_normal_attack": True,
          # #1024-r2 : le profil porte un 5e champ `is_hero` (`HeroUnits` = `UnitsWithTrait(0x10)`,
          # branche B de 1444). 1449 ne le lit pas, mais le tuple suit le contrat du PRODUCTEUR
          # (`damage_model._adjacent_unit_profiles`) -- un temoin qui MIME le producteur doit le
          # mimer en entier.
          "tgt_adjacent_unit_profiles": ((12, 1, "orksNob", Rarity.Mythic, True),
                                         (13, 1, "orksNob", Rarity.Mythic, True))}
    assert _mg.create_aura_defense_damage_malus_for_ally(
        dict(_c, att_rarity=Rarity.Mythic)) is not None, "montage degenere : le bras vrai est muet"
    assert _mg.create_aura_defense_damage_malus_for_ally(
        dict(_c, att_rarity=Rarity.Epic)) is None, (
        "le gate `HasRarity(Caster, Mythic)` de 1449 a disparu : terme PERMISSIF, et INVISIBLE "
        "dans le regime par defaut du harnais (`targetRarity = 5` partout).")
    assert _mg.create_aura_defense_damage_malus_for_ally(
        dict(_c, att_rarity=None)) is None, "non mesure -> le gate doit se FERMER"
    # Le canal, TRI-ETAT : `None` = pas mesure, jamais `Rarity.Common`.
    assert hasattr(UnitContext, "rarity"), (
        "`UnitContext.rarity` a DISPARU : le canal de rarete (#999-r3) est retire, et les deux "
        "effets redeviennent inevaluables pour la RAISON D'ORIGINE. Relire case-999r3-canal-rarete.")
    assert UnitContext(entity_id=1).rarity is None
    assert int(Rarity.Mythic) == 5


# --------------------------------------------------------------------------------------------
# Etage 1 -- branche A : `On(EffectAdded) & TriggeringEffectIs(Markerlight)`
# --------------------------------------------------------------------------------------------

def test_branche_markerlight_pose_l_effet():
    st = _state()
    ab = ElectrochaffBackupsOnMarkerlightAbility(OWNER_ID)
    assert ab.event_id == int(EventTriggerType.EffectAdded) == 62
    ev = _ev_markerlight(ENEMY_FAR_ID)
    assert ab.matches(st, ev) is True
    out = ab.execute_behaviour(st, ev)
    assert out and out["placed"] is True and out["refreshed"] is False
    assert _has_1446(st, ENEMY_FAR_ID)


@pytest.mark.parametrize("effet", [int(EffectType.Pinned), int(EffectType.Fire), None])
def test_branche_markerlight_refuse_un_autre_declencheur(effet):
    """`TriggeringEffectIs(0x462)` : un AUTRE effet pose ne declenche rien, et un
    `triggering_effect` NON threade non plus (on ne fabrique pas un declencheur)."""
    st = _state()
    ab = ElectrochaffBackupsOnMarkerlightAbility(OWNER_ID)
    ev = TriggerEvent(int(EventTriggerType.EffectAdded), OWNER_ID, ENEMY_FAR_ID,
                      ranged=False, profile=None, triggering_effect=effet)
    assert ab.matches(st, ev) is False
    assert not _has_1446(st, ENEMY_FAR_ID)


def test_tronc_commun_refuse_une_cible_amie():
    """`AreEnemies(Owner@+0x30, Target@+0x60)` -- un ALLIE qui recoit un Markerlight n'ecope
    de rien. Le bras POSITIF du meme etat est `test_branche_markerlight_pose_l_effet`."""
    st = _state()
    ab = ElectrochaffBackupsOnMarkerlightAbility(OWNER_ID)
    assert ab.matches(st, _ev_markerlight(FRIEND_ID)) is False


def test_tronc_commun_refuse_une_entite_non_normale():
    """`IsNormalUnit(Target@+0x60)` = `!HasTrait(0xd = Object) && !HasTrait(0x1b = Steppable)`.
    On pose le trait sur le `UnitContext` de la cible -- le MEME substrat que lit
    `BaseUnitComponent$$HasTrait` cote port (`entity_trait_names`)."""
    from engine.runner.components import StatsComponent
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.unit_context import UnitContext
    st = _state()
    ab = ElectrochaffBackupsOnMarkerlightAbility(OWNER_ID)
    ev = _ev_markerlight(ENEMY_FAR_ID)
    # Bras POSITIF : sans `StatsComponent`, `entity_trait_names(None)` rend l'ensemble VIDE et le
    # gate OUVRE -- ce qui est deja le comportement natif (`GetBaseUnitComponent` nul -> `true`).
    assert ab.matches(st, ev) is True, "bras POSITIF : sans le trait, le gate doit OUVRIR"
    ent = st.get_entity(ENEMY_FAR_ID)
    ctx = UnitContext(entity_id=ENEMY_FAR_ID, visual_id="orksRuntherd",
                      traits=[UnitTrait.Steppable.name], traits_measured=True)
    ent.add_component(StatsComponent(ctx))
    assert ab.matches(st, ev) is False


# --------------------------------------------------------------------------------------------
# Etage 2 -- branche B : `On(DamageTaken) & IsRangedAttack()`
# --------------------------------------------------------------------------------------------

def test_branche_degat_ranged_pose_l_effet():
    st = _state()
    ab = ElectrochaffBackupsOnRangedDamageAbility(OWNER_ID)
    assert ab.event_id == int(EventTriggerType.DamageTaken) == 15
    ev = _ev_damage(ENEMY_FAR_ID, source_id=FRIEND_ID)      # FRIEND est a d>=2 de ENEMY_FAR
    assert ab.matches(st, ev) is True
    out = ab.execute_behaviour(st, ev)
    assert out and out["placed"] is True
    assert _has_1446(st, ENEMY_FAR_ID)


def test_branche_degat_refuse_le_corps_a_corps():
    """`IsRangedAttack()` -- sur ce vecteur le port lit la branche << attaque normale concrete >>
    du slot 3 (`!AreEntitiesAdjacent`), faute d'`ability_type` threade (`#1025-r2`). Cible
    ADJACENTE de son agresseur -> refus. Bras POSITIF juste au-dessus."""
    st = _state()
    ab = ElectrochaffBackupsOnRangedDamageAbility(OWNER_ID)
    # ENEMY_NEAR (4,3) frappe ENEMY_FAR (4,4) : ils sont hex-adjacents.
    assert hexgeo.distance((4, 3), (4, 4)) == 1, "montage : les deux tuiles doivent etre adjacentes"
    assert ab.matches(st, _ev_damage(ENEMY_FAR_ID, source_id=ENEMY_NEAR_ID)) is False


def test_branche_degat_ne_lit_pas_le_declencheur_d_effet():
    """Symetrique de l'etage 1 : `IsRangedAttack` appartient a la branche `DamageTaken`, pas
    `TriggeringEffectIs`. Un event `DamageTaken` SANS `triggering_effect` doit passer -- sinon
    les deux conjoints propres auraient ete intervertis."""
    st = _state()
    ab = ElectrochaffBackupsOnRangedDamageAbility(OWNER_ID)
    ev = _ev_damage(ENEMY_FAR_ID, source_id=FRIEND_ID)
    assert ev.triggering_effect is None
    assert ab.matches(st, ev) is True


# --------------------------------------------------------------------------------------------
# Etage 3 -- `ChangeType.Set`, PAS `Add` (le seul ecart SILENCIEUX du behaviour)
# --------------------------------------------------------------------------------------------

def test_duree_est_turns_from_rounds_du_gameconfig():
    st = _state()
    rounds = electrochaff_rounds()
    assert rounds == 1, f"gameconfig ElectrochaffBackups.constants.nrOfRounds = {rounds}"
    turns = convert_rounds_to_turns(st, rounds)
    assert turns > 0, "TEMOIN DEGENERE : ConvertRoundsToTurns rend 0, l'etage Set/Add ne prouverait rien"
    assert turns == PLAYER_COUNT, f"ConvertRoundsToTurns(1) attendu {PLAYER_COUNT}, obtenu {turns}"
    ab = ElectrochaffBackupsOnMarkerlightAbility(OWNER_ID)
    ev = _ev_markerlight(ENEMY_FAR_ID)
    ab.execute_behaviour(st, ev)
    assert _turns_1446(st, ENEMY_FAR_ID) == turns


def test_re_declenchement_remet_la_duree_au_lieu_de_l_accumuler():
    """`ChangeEffectTurns(..., changeType = 1 = ChangeType.Set)`.

    GROUND TRUTH LIVE (#1025) : une attaque normale de 5 coups emet **5** blocs
    `[Ability_Power e=81 <<ElectrochaffBackups>>]`, et la duree observee sur la victime reste
    `r2`. Avec `Add`, elle vaudrait 10. Ici on rejoue les 5 declenchements."""
    st = _state()
    turns = convert_rounds_to_turns(st, electrochaff_rounds())
    assert turns > 0
    ab = ElectrochaffBackupsOnRangedDamageAbility(OWNER_ID)
    ev = _ev_damage(ENEMY_FAR_ID, source_id=FRIEND_ID)
    first = ab.execute_behaviour(st, ev)
    assert first["placed"] is True and first["refreshed"] is False
    for _ in range(4):
        again = ab.execute_behaviour(st, ev)
        assert again["placed"] is False and again["refreshed"] is True
    assert _turns_1446(st, ENEMY_FAR_ID) == turns, (
        "5 declenchements ont accumule la duree : le behaviour utilise Add au lieu de Set")
    # Contre-epreuve du MIROIR lui-meme : `Add` DONNERAIT bien un autre resultat sur ce cas --
    # sans quoi l'assertion ci-dessus passerait pour une raison degeneree.
    assert (ChangeEffectTurnsOperation.get_amount(turns, turns, ChangeEffectTurnsOperation.CHANGE_ADD)
            != ChangeEffectTurnsOperation.get_amount(turns, turns,
                                                     ChangeEffectTurnsOperation.CHANGE_SET))


def test_le_refresh_ne_pose_pas_une_seconde_instance():
    """`If(HasEffect(...), ChangeEffectTurns, AddEffect)` -- la branche `then` ne pose RIEN.
    Un `AddEffect` inconditionnel laisserait deux instances (ou un no-op silencieux)."""
    st = _state()
    ab = ElectrochaffBackupsOnMarkerlightAbility(OWNER_ID)
    ev = _ev_markerlight(ENEMY_FAR_ID)
    ab.execute_behaviour(st, ev)
    ab.execute_behaviour(st, ev)
    n = sum(1 for e in st.effects.by_unit.get(ENEMY_FAR_ID, [])
            if e.effect_type == ELECTROCHAFF_EFFECT and not e.consumed)
    assert n == 1, f"{n} instances de 1446 sur la cible"


# --------------------------------------------------------------------------------------------
# Etage 7 (#1025-r1) -- la face DEGAT : `$$CreateDamageModifier`, terme a terme
#
#   ForPercentDecrease( get_OwnerIsCaster
#                       & HasRarity(  Target@<DSLSelectors+0x60>, idun.meta.Rarity.Mythic = 5 )
#                       & AreFriends( Target@<DSLSelectors+0x60>,
#                                     EffectSource(Effect@<DSLSelectors+0x38>), 0, false ),
#                       ConfigVar( 0x46 = dmgReductionPct, GetAbilityState(effet), effet@+0x60 ) )
#
# ⚠ CHAQUE conjoint est teste par un COUPLE accorde/refuse : un etage qui ne montrerait que le
# bras positif ne separerait rien, et le regime par defaut du harnais est justement DEGENERE sur
# la rarete (`rl_duel build` impose `targetRarity = 5` a toute unite normalisee).
# --------------------------------------------------------------------------------------------

def _effet_1446(source_id=OWNER_ID, ability_level=None, level=1):
    from engine.entities.effects.factory import EffectFactory
    return EffectFactory.create(
        {"name": EffectType.ElectrochaffBackups_DamageReductionPct.name,
         "effectType": ELECTROCHAFF_EFFECT, "level": level, "remaining": 2,
         "source": source_id, "active": True}, 100, ability_level, None)


def _ctx_1446(tgt_rarity, tgt_team=1, source_team=1, niveau=None):
    """`att_ctx` du canal ATTAQUE. `tgt_team == source_team` => `AreFriends(Target, EffectSource)`.
    `niveau` non nul -> le canal `tertiary_ability_state_of` (mirror de `GetAbilityState(effet)`)."""
    ctx = {"tgt_rarity": tgt_rarity, "tgt_team": tgt_team,
           "team_by_id": {OWNER_ID: source_team, ENEMY_FAR_ID: 2}}
    if niveau is not None:
        ctx["tertiary_ability_state_of"] = lambda oid, ab: (
            (niveau, 100) if (oid == OWNER_ID and ab == ELECTROCHAFF_BACKUPS_ID) else (None, 100))
    return ctx


def test_face_degat_le_gate_de_rarete_separe():
    """`HasRarity(Target@+0x60, Mythic)` -- COUPLE accorde/refuse sur la MEME instance.

    C'est LE conjoint qui tenait 1446 hors du registre : sans lui, toute attaque du porteur marque
    serait reduite, quelle que soit sa cible (terme PERMISSIF)."""
    from engine.entities.rarity import Rarity
    eff = _effet_1446()
    accorde = eff.create_effect_damage_bonus_for_attack(att_ctx=_ctx_1446(Rarity.Mythic))
    assert accorde is not None and accorde.kind == "PercentDecrease" and accorde.value > 0
    assert accorde.owner_is_caster is True, "get_OwnerIsCaster : owner = l'ATTAQUANT"
    for autre in (Rarity.Common, Rarity.Rare, Rarity.Epic, Rarity.Legendary):
        assert eff.create_effect_damage_bonus_for_attack(att_ctx=_ctx_1446(autre)) is None, (
            "rarete %s acceptee : le gate HasRarity(Target, Mythic) est ouvert" % autre.name)


def test_face_degat_rarete_non_mesuree_ferme_le_gate():
    """TRI-ETAT : `None` = NON MESURE -> le gate se FERME. Un repli sur `Rarity.Common` serait
    faux dans l'autre sens, mais surtout un repli sur `Mythic` accorderait a tout le monde."""
    eff = _effet_1446()
    assert eff.create_effect_damage_bonus_for_attack(att_ctx=_ctx_1446(None)) is None
    assert eff.create_effect_damage_bonus_for_attack(att_ctx={}) is None
    assert eff.create_effect_damage_bonus_for_attack(att_ctx=None) is None


def test_face_degat_le_gate_arefriends_porte_sur_la_source_pas_sur_le_porteur():
    """`AreFriends(Target@+0x60, EffectSource(Effect@+0x38), 0, false)`.

    ⚠ NON redondant avec le `AreEnemies(Owner, Target)` du trigger de POSE : celui-la contraint le
    PORTEUR de l'effet, celui-ci contraint la CIBLE DE SON COUP. Un porteur marque qui frappe une
    unite qui n'est PAS alliee du Broadside n'ecope de rien."""
    from engine.entities.rarity import Rarity
    eff = _effet_1446()
    assert eff.create_effect_damage_bonus_for_attack(
        att_ctx=_ctx_1446(Rarity.Mythic, tgt_team=1, source_team=1)) is not None
    assert eff.create_effect_damage_bonus_for_attack(
        att_ctx=_ctx_1446(Rarity.Mythic, tgt_team=2, source_team=1)) is None, (
        "cible NON alliee de l'EffectSource acceptee : le gate AreFriends est ouvert")
    # `team_by_id` absent -> source non resolue -> gate MUET (jamais accorde par defaut).
    assert eff.create_effect_damage_bonus_for_attack(
        att_ctx={"tgt_rarity": Rarity.Mythic, "tgt_team": 1}) is None


def test_face_degat_la_magnitude_suit_l_etat_d_ability_de_la_SOURCE():
    """`ConfigVar(0x46 = dmgReductionPct, GetAbilityState(effet), ...)`.

    Le natif bake l'`AbilityStateReference` du POSEUR (2e argument d'`AddEffect` =
    `BaseTriggeredAbility$$get_AbilityStateReference(this)`) : la magnitude suit le niveau de la
    MoW, pas celui du porteur. Le canal port est `tertiary_ability_state_of`, interroge avec
    `self.source`. Les quatre paliers sont LUS au gameconfig, jamais ecrits en dur ici."""
    from engine.entities.rarity import Rarity
    from engine.entities.effects.magnitude import ability_var
    eff = _effet_1446()
    paliers = [ability_var(ELECTROCHAFF_BACKUPS_ID, "dmgReductionPct", n, multiplier_pct=100)
               for n in (1, 2, 3, 4)]
    assert len(set(paliers)) == len(paliers), (
        "TEMOIN DEGENERE : les quatre paliers du gameconfig sont egaux, l'etage ne separerait rien")
    for niveau, attendu in zip((1, 2, 3, 4), paliers):
        b = eff.create_effect_damage_bonus_for_attack(
            att_ctx=_ctx_1446(Rarity.Mythic, niveau=niveau))
        assert b is not None and b.value == attendu, (
            "niveau %d : %r attendu %r" % (niveau, b, attendu))
    # Canal absent -> repli NOMME sur les niveaux de l'instance (ici `level = 1`), jamais un no-op
    # silencieux ni une valeur devinee.
    repli = eff.create_effect_damage_bonus_for_attack(att_ctx=_ctx_1446(Rarity.Mythic))
    assert repli is not None and repli.value == paliers[0]


def test_face_degat_aucun_gate_de_nature_de_coup():
    """Le decompile ne porte NI `IsMeleeAttack`, NI `IsRangedAttack`, NI `IsNormalAttack`, NI
    `DamageProfileIs` : l'effet mord sur TOUT vecteur. C'est ce qui a impose le threading des deux
    cles sur les NEUF sites d'`att_ctx`, et pas seulement sur l'attaque normale."""
    from engine.entities.rarity import Rarity
    eff = _effet_1446()
    ctx = _ctx_1446(Rarity.Mythic)
    for kwargs in ({"is_ranged": True}, {"is_ranged": False}, {"is_normal_attack": False},
                   {"is_normal_attack": True}, {"has_moved": True}, {"is_prediction": True}):
        assert eff.create_effect_damage_bonus_for_attack(att_ctx=ctx, **kwargs) is not None, (
            "le port a introduit un gate de nature de coup : %r" % (kwargs,))


def test_face_degat_le_ctx_du_canal_attaque_porte_les_deux_cles_sur_les_deux_faces():
    """Les DEUX cles doivent EXISTER dans le ctx que construisent les foyers de chaque face --
    sinon l'effet est muet SANS ERREUR, et c'est exactement la degradation que ce port supprime.

    On lit le SOURCE des foyers plutot que d'executer une bataille : ce qui est garde ici est le
    contrat << la cle est posee >>, pas sa valeur (la valeur, elle, est confrontee live en regime
    SEPARANT -- le regime par defaut du harnais est DEGENERE sur la rarete)."""
    import inspect
    from engine.runner import damage_model
    from engine.playbook.prediction import normal_attack, abilities as pred_abilities
    for mod, nom in ((damage_model, "runner.damage_model"),
                     (normal_attack, "prediction.normal_attack"),
                     (pred_abilities, "prediction.abilities")):
        src = inspect.getsource(mod)
        for cle in ('"tgt_rarity"', '"team_by_id"'):
            assert cle in src, "%s ne pose plus %s dans l'att_ctx du canal ATTAQUE" % (nom, cle)
