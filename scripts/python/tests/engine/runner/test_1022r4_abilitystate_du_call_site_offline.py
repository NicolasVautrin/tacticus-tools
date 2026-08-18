"""#1022-r4 -- LE CALL-SITE DE 1208 LIT L'`AbilityState` DE L'ABILITY, PAS LE SCALAIRE DE L'UNITE.

CE QUE CE FICHIER GARDE, ET POURQUOI IL EST OFFLINE. Le natif
`IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$ExecuteBehaviour(this,
abilityState, entities)` transmet son 2e parametre VERBATIM a
`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig(config, abilityState,
abilitiesLevel: null, variableMultiplierPercentage: null)` -- premiere instruction de son corps. Les
sept `SetStatFromConfig(this, config, abilityState, <baseVariableType>, ordinal, <StatType>)` qui
suivent indexent donc `summonHp`/`summonDmg`/`summonArmor` SOUS CET ETAT-LA.

Le port a DEUX lectures possibles, et elles COINCIDENT sur tout runner qu'on sait monter :
  * le SCALAIRE `UnitContext.active_ability_level` (le defaut de la feuille `Spawn`) ;
  * l'`AbilityState` PAR ABILITY (`UnitContext.active_ability_levels[1208]`, canal
    `unitAbilityStates`, foyer `engine.runner.abilities.base.active_ability_state`, #890).

⚠ LEUR SEPARATION N'EST PAS CONSTRUCTIBLE LIVE, ET C'EST MESURE : sur `test_1022_aether_stride_live`
le mutant `ability_state=None` laisse les 10 tests VERTS, parce que `snapshot._load_machine_stats`
remplit le scalaire d'une MoW depuis `_machine_ability_state`, c'est-a-dire depuis le MEME canal
(`decisionView.mows[].abilities[]`) ; et dans un runner normalise toutes les actives d'une meme
unite partagent leur couple `(level, multiplier)`. La confrontation LIVE de la SEMANTIQUE
per-ability, elle, est deja faite par #890 (`test_890_hive_tyrant_live` : `ultraCalgar` porte
`1000@50` et son attaque normale `69@1`). Ce fichier ne re-demontre donc PAS cette semantique : il
verrouille UNIQUEMENT que CE call-site consomme ce canal-la, sur un etat ou les deux divergent --
etat qu'on FABRIQUE ici, faute de pouvoir le monter.

ASCII only.
"""
from __future__ import annotations

import pytest

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (contrat `declencheur_cliquet`).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/thousandsons.py",       # le call-site garde
        "scripts/python/engine/runner/abilities/base.py",               # active_ability_state (#890)
        "scripts/python/engine/runner/abilities/behaviours/summon.py",  # la feuille Spawn
        "scripts/python/engine/runner/operations/spawn.py",             # build_summon_context
        "scripts/python/engine/entities/effects/magnitude.py",          # ability_var (indexation)
        "scripts/python/engine/services/spawn_tile_shape.py",           # ThreeTileUnitSpawnShape
    ),
    "build": True,      # `ability_var` relit `summonHp`/`summonDmg` au gameconfig INSTALLE
    "toujours": False,
    "raison": ("le couple (niveau, multiplicateur) transmis par le call-site de 1208 a "
               "`WithStatsFromConfig` traverse ces six modules ; les valeurs attendues sont "
               "RECALCULEES depuis le gameconfig du build, jamais ecrites en dur."),
}

AETHER_STRIDE = 1208
SUMMON = "thousSmnDaemonPrince"
#: L'etat FABRIQUE : le scalaire d'unite et l'`AbilityState` de 1208 DIVERGENT. Le premier est le
#: neutre (niveau 1, x100) ; le second est celui qu'une MoW normalisee expose reellement (mesure
#: live `decisionView.mows[].abilities[]` : `level 50 / multiplier 180`).
SCALAIRE = (1, 100)
ETAT_1208 = (50, 180)


def _board_plat(largeur: int = 7, hauteur: int = 7):
    """Un board hexagonal PLAT et VIDE -- il suffit a `ThreeUnitSpawnTileShapeSelector$$GetArea`,
    qui cherche un triangle de 3 tuiles libres MUTUELLEMENT ADJACENTES autour de l'ancre.

    ⚠ Le champ `neighbours` est EXPLICITE, et il le doit : `Board` est construit en mode
    `native_sym` par defaut, c'est-a-dire qu'il LIT l'adjacence stockee sur la tuile (comme le
    `boardGraph` natif) au lieu de la deriver de la geometrie. Sans lui, `correct_area` echoue sur
    `correct_relationship_in_area` et le cast serait un no-op -- un VERT SUR RIEN. La geometrie
    vient de `hexgeo.neighbors`, foyer unique de la parite odd-q du depot."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    ids = {}
    tid = 1
    for col in range(largeur):
        for row in range(hauteur):
            ids[(col, row)] = tid
            tid += 1
    tiles = [{"id": t, "col": c, "row": r, "walkable": True, "elevation": 0,
              "neighbours": [ids[n] for n in hexgeo.neighbors(c, r) if n in ids]}
             for (c, r), t in ids.items()]
    return Board(tiles)


def _etat_avec_caster(scalaire, table):
    """`State` minimal : un board plat, une MoW caster dont le SCALAIRE et la TABLE per-ability
    divergent. `table` = `{ability_type: (level, mult)}` ou `None` (canal non mesure)."""
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import (MachineComponent, OwnerComponent, StatsComponent,
                                          UnitComponent)
    from engine.runner.state import State
    st = State()
    st.board = _board_plat()
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="ultraDreadnought", alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    e.add_component(MachineComponent(slot=1))
    ctx = UnitContext(entity_id=e.id, visual_id="ultraDreadnought",
                      active_ability_level=scalaire[0], ability_variables_multiplier=scalaire[1])
    ctx.active_ability_levels = table
    e.add_component(StatsComponent(ctx=ctx))
    return st, e.id


def _attendu(cle, level, mult):
    from engine.runner.abilities.base import ability_var
    return int(ability_var("AetherStride", cle, level, multiplier_pct=mult))


def _summon_ctx(st, diag):
    from engine.runner.components import StatsComponent
    sid = (diag.get("spawned") or [None])[0]
    assert sid is not None, "aucun summon pose -- le montage offline ne confronte rien"
    return getattr(st.get_entity(sid).get_component(StatsComponent), "ctx", None)


def _ancre(st):
    """Une tuile dont l'empreinte a 3 pieds existe -- sinon le cast est un no-op et le test serait
    VERT SUR RIEN."""
    from engine.services import spawn_tile_shape as STS
    for tid in sorted(st.board.by_id):
        if len(STS.get_area(st.board, set(), st.board.coord(tid))) == 3:
            return tid
    pytest.fail("aucune ancre a 3 pieds sur le board synthetique -- montage a revoir", pytrace=False)
    return None


def test_le_temoin_separe_vraiment_les_deux_lectures():
    """CONTRE-EPREUVE DU TEMOIN, avant tout le reste : les deux couples doivent donner des
    valeurs DIFFERENTES au gameconfig installe. Sans ce cran, les assertions ci-dessous seraient
    vraies pour les deux lectures et le fichier serait un VERT SUR RIEN."""
    assert SCALAIRE != ETAT_1208
    for cle in ("summonHp", "summonDmg", "summonArmor"):
        a, b = _attendu(cle, *SCALAIRE), _attendu(cle, *ETAT_1208)
        assert a != b, ("`%s` rend la MEME valeur sous %s et sous %s (%s) -- le temoin ne separe "
                        "rien" % (cle, SCALAIRE, ETAT_1208, a))


def test_le_call_site_indexe_sous_l_AbilityState_de_1208():
    """LE CRAN. `active_ability_levels[1208] = (50, 180)` et le scalaire vaut `(1, 100)` : les stats
    du summon doivent sortir sous le PREMIER couple, sur les TROIS variables `summon*` que
    `WithStatsFromConfig` alimente (`0x29 -> StatType 5 Health`, `0x2a -> 0 Attack`,
    `0x2b -> 0x10 FixedArmor`).

    Le mutant qui le fait rougir est exactement le retour au defaut de la feuille
    (`aether_stride_tree(tile, None)`)."""
    from engine.runner.abilities.thousandsons import AetherStrideAbility
    st, caster = _etat_avec_caster(SCALAIRE, {AETHER_STRIDE: ETAT_1208})
    diag = AetherStrideAbility().execute_behaviour(st, caster, _ancre(st))
    ctx = _summon_ctx(st, diag)
    assert ctx.visual_id == SUMMON
    assert (ctx.active_ability_level, ctx.ability_variables_multiplier) == ETAT_1208, (
        "le call-site a transmis %s au lieu de l'`AbilityState` de 1208 %s"
        % ((ctx.active_ability_level, ctx.ability_variables_multiplier), ETAT_1208))
    for cle, lu in (("summonHp", ctx.health), ("summonDmg", ctx.attack),
                    ("summonArmor", ctx.fixed_armor)):
        assert int(lu) == _attendu(cle, *ETAT_1208), (
            "`%s` du summon = %s ; attendu %s sous l'`AbilityState` de 1208, %s sous le scalaire"
            % (cle, lu, _attendu(cle, *ETAT_1208), _attendu(cle, *SCALAIRE)))


def test_sans_le_canal_le_call_site_RETOMBE_sur_le_scalaire():
    """L'AUTRE MOITIE, et elle n'est pas decorative : `active_ability_state` est ecrite pour
    RETOMBER sur le scalaire quand `unitAbilityStates` est muet (`active_ability_levels is None`).
    C'est ce qui garantit qu'aucun regime anterieur ne change de valeur -- sans ce test, une
    regression du repli passerait inapercue puisque le test precedent, lui, fournit le canal."""
    from engine.runner.abilities.thousandsons import AetherStrideAbility
    st, caster = _etat_avec_caster(ETAT_1208, None)
    diag = AetherStrideAbility().execute_behaviour(st, caster, _ancre(st))
    ctx = _summon_ctx(st, diag)
    assert (ctx.active_ability_level, ctx.ability_variables_multiplier) == ETAT_1208
    assert int(ctx.health) == _attendu("summonHp", *ETAT_1208)
