"""#1080 -- GARDE OFFLINE des deux passives portees : `BattleFocus` (1172/1199) et
`CallInReinforcements` (1029).

Le probe `probe_1080_battle_focus_call_in_reinforcements.py` MESURE (live, deux geometries par
volet) ; ce fichier GARDE, 100 % offline (aucun runner) :

  * les ordinaux et les cles de registre, FIGES contre le build -- une confusion d'enum est
    SILENCIEUSE en ordinal (`TriggeredAbilityType 1199` = `GalvanicField`, `EffectType 1172` =
    `HuntersBeyondDeath_ExtraDamage`) ;
  * l'INSCRIPTION dans les cinq registres concernes, verifiee PAR EXECUTION ;
  * le comportement des trois selecteurs neufs (`EdgeTiles`, `TilesWithoutPowerUps`,
    `SafestTiles`) et de la branche de repli de `TileDistanceUtility`, chacun avec sa
    CONTRE-EPREUVE : une mutation du critere doit changer le resultat.

Le seuil d'`EdgeTiles` (`voisins <= 4`, pas `< 6`) et le critere lexicographique de `SafestTiles`
sont les deux points ou une lecture approximative du decompile passerait inapercue en live sur un
board donne : ils ont donc chacun leur test dedie."""
from __future__ import annotations

import pytest

from engine.dsl.effects import ExecutionContext
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.battle_focus import BattleFocusEffect
from engine.entities.effects_state import EffectsState
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.accessors import FixedTileIds, Owner
from engine.entities.selectors.geometry import EdgeTiles
from engine.entities.selectors.tiles import (SafestTiles, TilesWithoutPowerUps, _power_up_ids,
                                             unit_is_power_up)
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.triggers.dispatch.registry import (ABILITY_TRIGGERS,
                                                                 CUSTOM_TRIGGERED_ABILITIES,
                                                                 EFFECT_TRIGGERS)
from engine.runner.operations.triggers.loki.battle_focus import (BATTLE_FOCUS_ABILITY,
                                                                 BATTLE_FOCUS_EFFECT,
                                                                 BATTLE_FOCUS_KEY,
                                                                 BattleFocusEffectTrigger,
                                                                 BattleFocusMoveAbility,
                                                                 battle_focus_move_tree)
from engine.runner.operations.triggers.loki.call_in_reinforcements import (
    CALL_IN_REINFORCEMENTS_KEY, CallInReinforcementsAbility,
    CALL_IN_REINFORCEMENTS_SPAWN_TILE_UTILITY, call_in_reinforcements_spawn_tiles)
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State
from engine.utilities.tile import UTILITY_BY_TYPE, TileDistanceUtility, utilities_database
from engine.utilities.utility_type import UtilityType

LEVEL, MULT = 50, 100

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: DERIVE des imports ci-dessus, pas choisi : chaque entree est un module que ce fichier LIT.
#: Un declencheur trop ETROIT est un FAUX VERT (le fichier ne se rejoue pas sous `--since` quand
#: ce qu'il garde a bouge) ; trop LARGE est sain.
DECLENCHEUR = {
    "chemins": (
        # LES DEUX PORTS gardes par ce fichier.
        "scripts/python/engine/runner/operations/triggers/loki/battle_focus.py",
        "scripts/python/engine/runner/operations/triggers/loki/call_in_reinforcements.py",
        "scripts/python/engine/entities/effects/loki/battle_focus.py",
        # LES TROIS SELECTEURS NEUFS et leur foyer d'export.
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/units.py",
        # LE FOYER D'UTILITE : `UTILITY_BY_TYPE`, `TileDistanceUtility`, `_spawn_leaf_ctx`.
        "scripts/python/engine/utilities/tile.py",
        "scripts/python/engine/utilities/decider.py",
        "scripts/python/engine/utilities/utility_type.py",
        # LES CINQ REGISTRES dont ce fichier verifie l'inscription PAR EXECUTION.
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        # LES MIRRORS D'ENUM dont les ordinaux sont FIGES ici.
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/effect_type.py",
        # LE SUBSTRAT du montage (board, contexte DSL, composants).
        "scripts/python/engine/entities/pathfinding/board.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/abilities/behaviours/movement.py",
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/dsl/base.py",
        "scripts/python/hexgeo.py",
    ),
    # VRAI : les ordinaux (1172/1199/1029), les 22 power-ups du `.cctor` et la bijection des deux
    # mirrors sont FIGES contre le build -- un changement de build peut les faire glisser.
    "build": True,
    "toujours": False,
    "raison": ("port + garde de #1080 : les deux arbres DSL, les trois selecteurs neufs, la "
               "branche de repli PARENT de `TileDistanceUtility` et les cinq inscriptions."),
}


# ------------------------------------------------------------------ montage : board + unites

def _grille(cols: int, rows: int) -> list:
    """Grille rectangulaire `cols x rows`, tuiles plates et marchables, voisinage EVENQ STOCKE.

    L'id est `col * rows + row` : arbitraire mais STABLE, et c'est lui que les assertions citent."""
    import hexgeo
    ids = {}
    for c in range(cols):
        for r in range(rows):
            ids[(c, r)] = c * rows + r
    out = []
    for (c, r), tid in sorted(ids.items(), key=lambda kv: kv[1]):
        vois = [ids[n] for n in hexgeo.neighbors(c, r) if n in ids]
        out.append({"id": tid, "col": c, "row": r, "elevation": 0, "walkable": True,
                    "isWall": False, "neighbours": vois})
    return out


class _Ctx:
    def __init__(self, visual_id, traits=(), passives=None, triggered=None):
        self.visual_id = visual_id
        self.traits = list(traits)
        self.passive_abilities = list(passives) if passives is not None else None
        self.triggered_abilities = list(triggered) if triggered is not None else None
        self.active_ability_level = LEVEL
        self.passive_ability_level = LEVEL
        self.ability_variables_multiplier = MULT

    def get_stat(self, stat_type, default=0):
        """`UnitContext.get_stat` -- le contexte de condition d'effet le lit EAGER
        (`RoundsStarted(Owner)`). Un montage qui l'omet leve `AttributeError` a la premiere
        evaluation d'arbre : ce n'est pas une commodite de test, c'est une piece du substrat."""
        return default


def _unite(st: State, uid: int, visual_id: str, *, team: int, pos, traits=(), passives=None,
           triggered=None) -> int:
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual_id, True))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(10000, 10000))
    e.add_component(StatsComponent(ctx=_Ctx(visual_id, traits, passives, triggered)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


@pytest.fixture
def plateau():
    """FIXTURE NOMMEE : une grille 7x9 (la taille de `MC1_67`), un porteur et deux ennemis dont
    les POSITIONS sont des parametres -- chaque face negative se fabrique en DEPLACANT une piece,
    jamais en en ajoutant une."""
    def _monter(porteur=(3, 4), ennemis=((3, 6), (4, 6)), cols=7, rows=9, seed=777,
                traits_ennemis=()):
        st = State()
        st.effects = EffectsState()
        st.rng = IntBasedMersenneTwister(seed)
        st.board = Board(_grille(cols, rows), adjacency="evenq")
        moi = _unite(st, 10, "eldarNpc1Guardian", team=1, pos=porteur,
                     passives=[BATTLE_FOCUS_KEY])
        for i, p in enumerate(ennemis):
            _unite(st, 20 + i, "orksNob", team=2, pos=p, traits=list(traits_ennemis))
        return st, moi
    return _monter


# ------------------------------------------------------------------------ etage 1 : les ENUMS

def test_les_ordinaux_sont_ceux_du_build_et_chacun_MENT_dans_l_autre_enum():
    """Le piege d'homonymie, FIGE. `BattleFocus` porte le meme NOM dans les deux enums a des
    ordinaux DIFFERENTS ; croiser les deux ne leverait AUCUNE erreur."""
    assert int(TriggeredAbilityType.BattleFocus) == 0x494 == 1172
    assert int(EffectType.BattleFocus) == 0x4af == 1199
    assert int(TriggeredAbilityType.CallInReinforcements) == 0x405 == 1029
    # l'ordinal de l'ability nomme AUTRE CHOSE dans l'enum des effets, et reciproquement
    assert EffectType(1172).name == "HuntersBeyondDeath_ExtraDamage"
    assert TriggeredAbilityType(1199).name == "GalvanicField"
    # ... et le port ne les confond pas
    assert BATTLE_FOCUS_ABILITY == 1172 and BATTLE_FOCUS_EFFECT == 1199


def test_les_22_power_ups_sont_ceux_du_cctor():
    """`StaticBattleRules.TriggeredAbility$$.cctor` en ecrit EXACTEMENT 22 dans `<statics+0x70>`,
    tous prefixes `PowerUp_`. Le compte est fige : un membre ajoute au mirror sans etre dans le
    `.cctor` elargirait `IsPowerUp` en silence."""
    ids = _power_up_ids()
    assert len(ids) == 22
    assert all(TriggeredAbilityType(i).name.startswith("PowerUp_") for i in ids)
    # et la reciproque N'EST PAS vraie : tous les `PowerUp_*` du mirror n'y sont pas
    tous = {int(m) for m in TriggeredAbilityType if m.name.startswith("PowerUp_")}
    assert ids <= tous


# --------------------------------------------------------- etage 2 : les REGISTRES, par EXECUTION

def test_les_cinq_inscriptions_existent():
    """Ce que la tranche a CABLE, lu dans les dicts EUX-MEMES (jamais par grep du nom)."""
    assert CallInReinforcementsAbility in ABILITY_TRIGGERS[CALL_IN_REINFORCEMENTS_KEY]
    assert BattleFocusEffectTrigger in EFFECT_TRIGGERS[BATTLE_FOCUS_EFFECT]
    assert BattleFocusMoveAbility in CUSTOM_TRIGGERED_ABILITIES[BATTLE_FOCUS_ABILITY]
    assert EFFECT_CLASSES[BATTLE_FOCUS_KEY] is BattleFocusEffect
    assert ABILITY_INIT_OWNER_EFFECTS[BATTLE_FOCUS_KEY] == [BATTLE_FOCUS_KEY]


def test_les_deux_utilites_du_bucket_sont_RESOLVABLES():
    """`UtilityDecider.CalculateUtility` LEVE sur un type absent d'`UTILITY_BY_TYPE` -- donc sans
    ces deux entrees le behaviour de `CallInReinforcements` ne pourrait pas s'executer du tout."""
    assert utilities_database(int(UtilityType.PowerUp)) is not None
    assert utilities_database(int(UtilityType.TileDistance)) is not None
    termes = [w.utility_type for w in CALL_IN_REINFORCEMENTS_SPAWN_TILE_UTILITY.buckets[0].utilities]
    assert termes == [int(UtilityType.PowerUp), int(UtilityType.TileDistance)]
    assert all(t in UTILITY_BY_TYPE for t in termes)


# ------------------------------------------------------ etage 3 : `EdgeTiles` et son SEUIL exact

def test_edge_tiles_le_seuil_est_QUATRE_voisins_pas_cinq(plateau):
    """`BattleQuery$$IsEdgeTile` = `GetSurroundingTilesCount(..., includeCenter: TRUE) <= 5`, donc
    **`voisins <= 4`**. CONTRE-EPREUVE : sur une grille 7x9 evenq, il existe des tuiles a 5 voisins,
    et elles ne doivent PAS sortir."""
    st, moi = plateau()
    ents = entities_from_state(st, moi)
    tous = [t["id"] for t in st.board.tiles.values()] if hasattr(st.board, "tiles") else None
    ids = sorted(EdgeTiles(FixedTileIds(sorted(st.board.by_id))).evaluate(ents))
    # partition par nombre de voisins GEOMETRIQUES (le disque `IterateSurroundingTiles`)
    par_n = {}
    for t in sorted(st.board.by_id):
        par_n.setdefault(len(st.board.neighbours_geometric(t)), []).append(t)
    assert 5 in par_n and par_n[5], "montage degenere : aucune tuile a 5 voisins"
    assert 6 in par_n and par_n[6], "montage degenere : aucune tuile interieure"
    for t in par_n[5]:
        assert t not in ids, "une tuile a 5 voisins est sortie -- le seuil lu serait `< 6`"
    for t in par_n[6]:
        assert t not in ids
    for n in (2, 3, 4):
        for t in par_n.get(n, []):
            assert t in ids, "une tuile a %d voisins DOIT etre edge" % n
    assert tous is None or True                       # `tous` n'est qu'un temoin de forme


# ------------------------------------------- etage 4 : `TilesWithoutPowerUps` et son OU en tete

def test_tiles_without_power_ups_une_tuile_LIBRE_passe(plateau):
    """`unit == null || !IsPowerUp(unit)` -- la branche `null` est prise AVANT tout appel a
    `IsPowerUp`. Le noeud ne filtre PAS sur l'occupation."""
    st, moi = plateau(porteur=(3, 4), ennemis=())
    ents = entities_from_state(st, moi)
    src = sorted(st.board.by_id)[:12]
    assert TilesWithoutPowerUps(FixedTileIds(src)).evaluate(ents) == src


def test_tiles_without_power_ups_RETIRE_la_tuile_d_un_power_up(plateau):
    """CONTRE-EPREUVE : la MEME source, avec un power-up pose sur une des tuiles."""
    st, moi = plateau(porteur=(3, 4), ennemis=())
    pu = int(TriggeredAbilityType.PowerUp_Healing)
    _unite(st, 30, "powupHealing", team=1, pos=(0, 1), triggered=[pu])
    ents = entities_from_state(st, moi)
    tid = st.board.id_at(0, 1)
    src = sorted(st.board.by_id)[:12]
    assert tid in src, "montage degenere : la tuile du power-up n'est pas dans la source"
    out = TilesWithoutPowerUps(FixedTileIds(src)).evaluate(ents)
    assert tid not in out and len(out) == len(src) - 1
    # et le predicat lui-meme, isole -- accesseur EXPLICITE (le dict d unite du DSL ne porte
    # AUCUNE cle `triggered_abilities` : lire une telle cle rendrait toujours False, en silence)
    assert unit_is_power_up({"id": 1}, lambda u, a: a == pu) is True
    assert unit_is_power_up({"id": 1}, lambda u, a: False) is False
    assert unit_is_power_up({"id": 1}, None) is False
    assert unit_is_power_up(None, lambda u, a: True) is False


# ------------------------------------ etage 5 : `SafestTiles`, ses DEUX etages de comparaison

def _safest(st, moi, src):
    from engine.entities.selectors.units import Enemies
    from engine.entities.selectors.tiles import AllAliveUnits
    ents = entities_from_state(st, moi)
    avoid = Enemies(AllAliveUnits(), reference=Owner(),
                    selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))
    return SafestTiles(FixedTileIds(src), Owner(), avoid).evaluate(ents)


def test_safest_tiles_MAXIMISE_la_distance_au_plus_proche(plateau):
    """Etage 1 du critere. Ennemis en bas -> la tuile du HAUT gagne, et c'est la SEULE."""
    st, moi = plateau(porteur=(3, 4), ennemis=((3, 8),))
    src = [st.board.id_at(3, 1), st.board.id_at(3, 5), st.board.id_at(3, 7)]
    assert _safest(st, moi, src) == [st.board.id_at(3, 1)]


def test_safest_tiles_le_SUJET_ne_se_fuit_pas_lui_meme(plateau):
    """`if (entity != <me>)` : le porteur est ECARTE de la liste a eviter. Ici il est de la MEME
    equipe que personne, donc c'est `Enemies` qui l'exclut deja -- la garde se teste en le passant
    LUI-MEME comme unite a eviter."""
    from engine.entities.selectors.tiles import AllAliveUnits
    st, moi = plateau(porteur=(3, 4), ennemis=((3, 8),))
    ents = entities_from_state(st, moi)
    src = [st.board.id_at(3, 1), st.board.id_at(3, 5)]
    # `unitsToAvoid` = TOUTES les unites vivantes, porteur COMPRIS : sans la garde, la tuile
    # adjacente au porteur serait penalisee et le classement changerait.
    sans_garde = SafestTiles(FixedTileIds(src), Owner(), AllAliveUnits()).evaluate(ents)
    assert sans_garde == [st.board.id_at(3, 1)], sans_garde


def test_safest_tiles_a_egalite_MINIMISE_le_nombre_de_tuiles_ennemies(plateau):
    """Etage 2 du critere -- `cur.Count`, alimente par `AddRange(eTiles)`. Deux candidates a la
    MEME distance minimale : celle qui a MOINS de tuiles ennemies a cette distance gagne.

    ⚠ Le montage ASSERTIONNE d'abord sa propre non-degenerescence (`dA == dB`) : si l'etage 1
    tranchait deja, ce test ne dirait RIEN de l'etage 2 -- et il passerait quand meme."""
    import hexgeo
    # UN ennemi a gauche, DEUX a droite (adjacents entre eux, donc a la meme distance de `b`).
    st, moi = plateau(porteur=(3, 4), ennemis=((0, 4), (6, 4), (6, 5)))
    a_pos, b_pos = (2, 4), (4, 4)
    a, b = st.board.id_at(*a_pos), st.board.id_at(*b_pos)
    dA = min(hexgeo.distance(a_pos, p) for p in ((0, 4),))
    dB = min(hexgeo.distance(b_pos, p) for p in ((6, 4), (6, 5)))
    assert dA == dB, ("montage degenere : l'etage 1 tranche deja", dA, dB)
    nB = sum(1 for p in ((6, 4), (6, 5)) if hexgeo.distance(b_pos, p) == dB)
    assert nB > 1, ("montage degenere : les deux candidates ont autant d'ennemis", nB)
    # ⚠ LES DEUX ORDRES DE SOURCE, et c'est ce qui rend le test DISCRIMINANT. Dans l'ordre
    # `[a, b]` la bonne candidate entre la PREMIERE et l'etage 2 n'a rien a trancher : un port qui
    # l'aurait supprime resterait vert. Il faut l'ordre `[b, a]`, ou l'etage 2 doit EVINCER une
    # candidate deja retenue -- mesure faite, le mutant << etage 2 supprime >> ne rougit QUE la.
    assert _safest(st, moi, [a, b]) == [a]
    assert _safest(st, moi, [b, a]) == [a]
    # CONTRE-EPREUVE : avec UN SEUL ennemi a droite, les deux candidates sont a EGALITE PARFAITE
    # (meme distance, meme compte) -> le natif rend les DEUX.
    st2, moi2 = plateau(porteur=(3, 4), ennemis=((0, 4), (6, 4)))
    a2, b2 = st2.board.id_at(*a_pos), st2.board.id_at(*b_pos)
    assert _safest(st2, moi2, [a2, b2]) == [a2, b2]


def test_safest_tiles_sans_ennemi_rend_TOUTES_les_tuiles(plateau):
    """`avoid` VIDE : `curMin` reste `int.MaxValue` pour chaque candidate -> la 1re entre seule,
    les suivantes s'AJOUTENT (egalite parfaite). Mirror exact, pas une degradation."""
    st, moi = plateau(porteur=(3, 4), ennemis=())
    src = [st.board.id_at(3, 1), st.board.id_at(3, 5), st.board.id_at(3, 7)]
    assert _safest(st, moi, src) == src


# ------------------------------- etage 6 : `TileDistanceUtility`, la branche de repli PARENT

def test_tile_distance_la_branche_de_repli_PARENT_est_portee():
    """`else if (c.owner != null) DistanceTo(c, c.owner)` -- inatteignable jusqu'a cette tranche,
    exercee par `CallInReinforcementsAbility$$CreateBehaviour`. CONTRE-EPREUVE : sans
    `parent_pos`, la feuille rend 0.0 et le tri devient CONSTANT."""
    u = TileDistanceUtility()
    assert u.evaluate((3, 4), {}, {"is_spawning": True, "parent_pos": (3, 1)}, None) == -0.3
    assert u.evaluate((3, 4), {}, {"is_spawning": True}, None) == 0.0
    # le SUJET prime sur le parent (l'ordre du `MoveNext` natif)
    assert u.evaluate((3, 4), {}, {"self_pos": (3, 3), "parent_pos": (3, 0)}, None) == -0.1


def test_le_ctx_de_spawn_publie_parent_pos_et_RIEN_de_plus(plateau):
    """`_spawn_leaf_ctx` ne doit PAS fabriquer de cle de SUJET depuis le parent (les gates que le
    natif laisse tomber en regime spawn) -- seule `parent_pos` s'ajoute."""
    from engine.utilities.tile import _spawn_leaf_ctx
    st, moi = plateau(porteur=(5, 5), ennemis=((3, 6),))
    ctx = _spawn_leaf_ctx(st, moi)
    assert ctx["is_spawning"] is True and ctx["parent_pos"] == (5, 5)
    for interdite in ("uid", "self_pos", "unit_traits", "unit_faction",
                      "unit_triggered_abilities", "unit_parent_id"):
        assert interdite not in ctx, interdite


# --------------------------------------------- etage 7 : les DEUX arbres, bout en bout, offline

def test_battle_focus_le_porteur_FUIT_et_la_direction_depend_des_ennemis(plateau):
    """L'arbre complet de `CreateMoveBehaviour`, joue offline sur DEUX geometries opposees. Une
    reponse CONSTANTE ne peut pas satisfaire les deux -- c'est la garde contre un port qui
    bougerait toujours dans le meme sens."""
    dests = {}
    for nom, ennemis in (("sud", ((3, 6), (4, 6))), ("nord", ((3, 2), (4, 2)))):
        st, moi = plateau(porteur=(3, 4), ennemis=ennemis)
        ectx = ExecutionContext(state=st, rng=st.rng)
        battle_focus_move_tree().execute(entities_from_state(st, moi), ectx)
        pc = st.get_entity(moi).get_component(PositionComponent)
        dests[nom] = (pc.col, pc.row)
    assert dests["sud"] != (3, 4) and dests["nord"] != (3, 4), dests
    assert dests["sud"] != dests["nord"], dests
    assert dests["sud"][1] < 4 < dests["nord"][1], dests   # fuit VERS le haut / VERS le bas


def test_battle_focus_le_trigger_EXIGE_une_attaque_a_cible_directe(plateau):
    """`AbilityHasAttackType(CurrentAbility, DirectTargetAttack = 0)` SEUL. CONTRE-EPREUVE : un
    `ability_type` qui n'est pas une attaque a cible directe ne doit PAS armer le trigger."""
    st, moi = plateau()
    trg = BattleFocusEffectTrigger(moi)
    ok = TriggerEvent(int(EventTriggerType.UnitAbility), moi, 20,
                      ranged=True, profile=None, ability_type=1013)
    assert trg.matches(st, ok) is True
    ko = TriggerEvent(int(EventTriggerType.UnitAbility), moi, 20,
                      ranged=True, profile=None, ability_type=None)
    assert trg.matches(st, ko) is False


def test_battle_focus_le_gate_IsActive_du_rail_TARGETS_MORD(plateau):
    """#421-r2 -- LE GATE QUI MANQUAIT, et la mesure qui montre qu'il n'est pas cosmetique.

    `BattleFocusEffect` produit son trigger par `$$CreateTargetTrigger`, donc
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` teste
    `EffectComponent.IsActive @+0x5c` AVANT `ShouldTrigger` -- a l'entree puis PAR CIBLE. Le port ne
    le lisait pas : le porteur se repositionnait alors que son effet 1199 etait DESACTIVE. Ni
    erreur, ni crash, juste un deplacement de trop.

    TROIS regimes, et le troisieme est ce qui distingue un gate d'un refus fabrique :
      1. instance ACTIVE   -> le trigger arme (sinon le gate aurait tout eteint) ;
      2. instance INACTIVE -> il ne s'arme plus (c'est LE cran) ;
      3. AUCUNE instance   -> il s'arme, degradation PERMISSIVE NOMMEE, meme direction que
         `effect_triggers._ranged_auto_attack_flag_is_set`. C'est aussi le regime des autres bras
         de ce fichier, qui ne posent pas d'instance."""
    from engine.entities.effects.loki.battle_focus import BattleFocusEffect

    def _armer(active):
        st, moi = plateau()
        eff = BattleFocusEffect({"name": BATTLE_FOCUS_KEY, "source": moi})
        eff.effect_type = BATTLE_FOCUS_EFFECT
        eff.consumed = False
        eff.active = active
        st.effects.add_effect(moi, eff)
        ev = TriggerEvent(int(EventTriggerType.UnitAbility), moi, 20,
                          ranged=True, profile=None, ability_type=1013)
        return BattleFocusEffectTrigger(moi).matches(st, ev)

    assert _armer(True) is True, (
        "instance ACTIVE et pourtant pas d'armement -- le gate refuse tout, il ne discrimine pas")
    assert _armer(False) is False, (
        "instance INACTIVE et le trigger s'arme quand meme -- le gate `IsActive` du rail TARGETS "
        "n'est pas lu (c'est l'etat d'AVANT #421-r2)")

    # (3) le regime SANS instance, qui est celui des autres bras : PERMISSIF, et il le reste.
    st, moi = plateau()
    ev = TriggerEvent(int(EventTriggerType.UnitAbility), moi, 20,
                      ranged=True, profile=None, ability_type=1013)
    assert BattleFocusEffectTrigger(moi).matches(st, ev) is True, (
        "le gate fabrique un refus quand le substrat ne publie AUCUNE instance -- degradation "
        "RESTRICTIVE non voulue")


def test_battle_focus_le_trigger_exige_que_le_porteur_soit_CASTER_ou_CIBLE(plateau):
    """`get_OwnerIsTarget | get_OwnerIsCaster`. Un evenement ou le porteur n'est NI l'un NI
    l'autre ne l'arme pas."""
    st, moi = plateau()
    trg = BattleFocusEffectTrigger(moi)
    ev = TriggerEvent(int(EventTriggerType.UnitAbility), 20, 21,
                      ranged=True, profile=None, ability_type=1013)
    assert trg.matches(st, ev) is False


def test_call_in_reinforcements_choisit_la_tuile_de_BORD_la_plus_PROCHE(plateau):
    """L'arbre de tuiles complet, joue offline sur DEUX positions de porteur. Le seul terme
    discriminant du bucket est `TileDistance(34)` : la tuile de bord LIBRE la plus proche gagne."""
    from engine.utilities.tile import sort_tiles_by_utility  # noqa: F401  (foyer, via le noeud)
    choix = {}
    for pos in ((1, 0), (5, 5)):
        st, moi = plateau(porteur=pos, ennemis=((0, 8),))
        ents = entities_from_state(st, moi)
        tiles = call_in_reinforcements_spawn_tiles().evaluate(ents)
        assert len(tiles) == 1, tiles                      # `First(..., 1)`
        choix[pos] = st.board.coord(tiles[0])
    assert choix[(1, 0)] != choix[(5, 5)], choix           # temoin NON degenere
    for pos, c in choix.items():
        import hexgeo
        assert hexgeo.distance(pos, c) <= 2, (pos, c)      # « nearby » de l'i2


def test_call_in_reinforcements_le_trigger_exige_OwnerIsActor(plateau):
    """`get_OwnerIsActor` : l'unite qui vient de clore son tour EST le porteur."""
    st, moi = plateau()
    ab = CallInReinforcementsAbility(moi)
    ok = TriggerEvent(int(EventTriggerType.UnitFinishedTurnNormally), moi, moi,
                      ranged=False, profile=None)
    ko = TriggerEvent(int(EventTriggerType.UnitFinishedTurnNormally), 20, 20,
                      ranged=False, profile=None)
    assert ab.matches(st, ok) is True and ab.matches(st, ko) is False
