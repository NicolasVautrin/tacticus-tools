"""#996-r1 -- GARDE du port de `1053 DevoutPush` et des DEUX etages de mouvement qu'il a reveilles.

Le probe (`probe_996r1_devout_push.py`) MESURE contre le natif ; ce fichier GARDE, hors ligne, ce
que la mesure a etabli. Cinq etages, et chacun rougit sur une MUTATION differente :

  1. REGISTRE      -- 1053 au registre COMBAT, avec son masque ET son litteral d'AbilityAttackType,
                      et RETIREE de `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction).
  2. ARBRE         -- les TROIS noeuds, dans l'ORDRE `(atk + kill) + move`, et le budget `Direct(1)`
                      + l'utilite 53 IMPOSEE au `PerformAIMovement`.
  3. FEUILLE 53    -- `-10` sur la tuile COURANTE, `50` par ennemi RANGED adjacent, `30` par MELEE,
                      `0` sans sujet. Les valeurs viennent du BC, la garde verifie la FORMULE.
  4. DISPATCHER    -- `get_movement_utility` route bien 53, et le RAYON DE SOUFFLE mesure tient :
                      62 (BioMinefield) reste a `0.0`, comme avant la tranche.
  5. OVERRIDE      -- `_move_tiles(override_range=N)` est une PROFONDEUR, pas un interrupteur :
                      `0` -> aucune tuile, `1` -> le ring-1 marchable, `None` -> la portee Movement.

100 % OFFLINE : aucun runner, aucun RPC.
"""
from __future__ import annotations

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.behaviours import Seq
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
from engine.runner.abilities.blacktemplars import (DEVOUT_PUSH_ID, DEVOUT_PUSH_MOVE_RANGE,
                                                   DEVOUT_PUSH_MOVE_UTILITY, DevoutPushAbility,
                                                   devout_push_tree)
from engine.runner.abilities.behaviours.ai_control import PerformAIMovement
from engine.runner.abilities.behaviours.combat import UseActiveAbility
from engine.runner.abilities.behaviours.lifecycle import Kill
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (RANGE_ADJACENT, RANGED_BOOL_FALSE,
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.utilities.devout_push import (DEVOUT_PUSH_ADJACENT_RANGED_ENEMIES, STAY_PUT_PENALTY)
from engine.utilities.tile import UTILITY_BY_TYPE, utilities_database
from engine.utilities.utility_type import UtilityType
from engine.weights import load as load_weights

#: #486-r15 -- ce que ce fichier LIT, donc ce qui peut changer son verdict. Volontairement LARGE sur
#: les trois foyers PARTAGES que la tranche a touches (`engine/ai/`, `engine/utilities/`,
#: `engine/runner/abilities/`) : trop large est sain, trop etroit est un faux vert.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/engine/entities/",
        "scripts/python/engine/runner/abilities/",
        "scripts/python/engine/ai/",
        "scripts/python/engine/utilities/",
        "scripts/python/engine/weights.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "cliquet OFFLINE du port 1053 -- registre + masque + AbilityAttackType, structure de "
              "l'arbre, formule de la feuille 53, route du dispatcher de mouvement et propagation "
              "de l'override de portee. Il lit des REGISTRES en memoire (`ABILITY_CLASSES`, "
              "`ABILITY_ATTACK_TYPE`, `TARGETING_OPTIONS_UNPORTED`, `UTILITY_BY_TYPE`) et la SOURCE "
              "de deux fonctions (`PerformAIMovement.execute`, `build_from_state`), donc son "
              "declencheur est la fermeture d'import de `engine.runner.abilities.handler`, de "
              "`engine.ai.*` et de `engine.utilities.*` -- prise au REPERTOIRE, un import indirect "
              "pouvant atteindre n'importe quel module. `build: False` : aucune valeur du dump n'y "
              "entre (les poids viennent du BC, les ordinaux des mirrors d'enum).",
}

ID = int(ActiveAbilityType.DevoutPush)          # 1053
U53 = int(UtilityType.DevoutPush_AdjacentRangedEnemies)


# --------------------------------------------------------------------------- 1. REGISTRE

def test_etage1_1053_au_registre_avec_masque_et_attack_type():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son `TARGETING_OPTIONS` **et** son
    `ABILITY_ATTACK_TYPE` dans le MEME commit (CLAUDE.md), et sort de
    `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : `test_targeting_options_sources`)."""
    assert ID in ABILITY_CLASSES, "1053 DevoutPush absente d'ABILITY_CLASSES"
    klass = ABILITY_CLASSES[ID]
    assert klass is DevoutPushAbility
    assert klass.ABILITY_ID == DEVOUT_PUSH_ID
    opts = klass.TARGETING_OPTIONS
    assert opts is not None, "masque ABSENT -> get_invalid_target_reason rend 0 = PERMISSIF"
    # Preset STATIC-COPY `<TargetingOptions statics>+0x40` : rules 0x4000, forceMeleeTarget 1,
    # range = `<TargetingRange statics>+0x30`, isSelfCasting 0. Chaque champ est LU au ctor.
    assert int(opts.rules) == int(TR.TargetIsEnemy), (
        "masque 1053 : le preset `+0x40` ecrit `TargetIsEnemy` SEUL (0x4000), aucun bit residuel")
    assert opts.self_cast is False
    assert opts.range == RANGE_ADJACENT
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    assert ABILITY_ATTACK_TYPE.get(ID) == 0, (
        "AbilityAttackType 1053 = le litteral `0` DirectTargetAttack du `AActiveAbility..ctor` "
        "(`xor r8d, r8d`), TRANSCRIT et non deduit du profil de l'arbre")
    assert ID not in TARGETING_OPTIONS_UNPORTED, (
        "1053 est PORTEE : son masque vit sur SA classe. Le laisser aussi dans "
        "TARGETING_OPTIONS_UNPORTED est la DOUBLE declaration que `probe_181` ne voit pas")


# ------------------------------------------------------------------------------ 2. ARBRE

def _noeuds(n, out=None):
    """Aplatit les `Seq` (le `op_Addition`/`op_BitwiseAnd` natif) en liste de feuilles."""
    out = [] if out is None else out
    if isinstance(n, Seq):
        _noeuds(n.left, out)
        _noeuds(n.right, out)
    else:
        out.append(n)
    return out


def test_etage2_arbre_trois_noeuds_dans_l_ordre_natif():
    """`Execute( (UseActiveAbility + Kill) + PerformAIMovement )` -- l'ORDRE est LOAD-BEARING :
    la cible doit etre morte ET finalisee pour que sa tuile soit libre au moment du deplacement."""
    n = _noeuds(devout_push_tree())
    assert [type(x).__name__ for x in n] == ["UseActiveAbility", "Kill", "PerformAIMovement"], (
        "arbre 1053 : ordre natif `(atk op_Addition kill) op_Addition move`, cf. le decompile")
    assert isinstance(n[0], UseActiveAbility) and isinstance(n[1], Kill)
    move = n[2]
    assert isinstance(move, PerformAIMovement)
    assert tuple(move.override_utility or ()) == tuple(DEVOUT_PUSH_MOVE_UTILITY) == (U53,), (
        "le `UtilityDefinition` du ctor porte UN bucket, UtilityType 0x35 = 53 -- sans lui le "
        "scoring est plat et le caster ne bouge PAS (le demi-port refuse par #907)")
    assert int(move.range.evaluate(None)) == DEVOUT_PUSH_MOVE_RANGE == 1, (
        "budget de deplacement = `DSLFormulas$$Direct(1)` = UNE tuile")


def test_etage2b_perform_ai_movement_normalise_un_selecteur_unit_domain_NU():
    """`PerformAIMovementBehaviour$$Execute` fait `this.unit.Select(entities, 3)`, dont le type de
    RETOUR est une LISTE quel que soit le selecteur. Cote port, `Caster()` rend un dict NU
    (`ctx.caster`) : l'iterer rendait ses CLES -- des chaines -- que le filtre `isinstance(u, dict)`
    jetait, donc `units = []` et AUCUN `ComputerMovementAction`, sans erreur.

    ⚠ GARDE PAR LA SOURCE, et c'est un ECART NOMME : un test comportemental exigerait un `State`
    complet (le `execute` appelle `ComputerMovementActionOperation`). Le comportement, lui, est
    confronte LIVE par `probe_996r1_devout_push.py` (`move.units == [<caster>]`)."""
    import inspect
    src = inspect.getsource(PerformAIMovement.execute)
    assert "_units_of(self.selector" in src, (
        "PerformAIMovement doit normaliser son selecteur par `_units_of` (le meme normaliseur que "
        "`Kill` et `UseActiveAbility`) : `self.selector.evaluate(...)` NU rend un dict pour tout "
        "accesseur unit-domain, et le filtre aval le jette en silence")
    assert "self.selector.evaluate(entities) or []" not in src, (
        "l'ancienne evaluation NUE est REVENUE dans PerformAIMovement.execute")


# ------------------------------------------------------------------------- 3. FEUILLE 53

def _ctx(self_pos, enemies, neigh):
    return {"uid": 1, "self_pos": self_pos, "enemy_units": enemies,
            "elev_by_pos": {}, "neigh_by_pos": neigh}


#: Voisinage SYNTHETIQUE minimal : `A` et `B` sont voisines de `S` (la tuile du sujet), `R` est
#: voisine de `A` SEULE et `M` de `B` SEULE. Aucun board reel n'est necessaire pour garder la
#: FORMULE -- c'est le probe qui garde la geometrie.
_S, _A, _B, _R, _M = (0, 0), (1, 0), (0, 1), (2, 0), (0, 2)
_NEIGH = {_S: [_A, _B], _A: [_S, _R], _B: [_S, _M], _R: [_A], _M: [_B]}


def test_etage3_feuille53_formule():
    wt = load_weights()
    f = DEVOUT_PUSH_ADJACENT_RANGED_ENEMIES
    ennemis = [{"pos": _R, "vis": "eldarRanger"},        # arme RANGED -> 50
               {"pos": _M, "vis": "astraBullgryn"}]      # MELEE seul  -> 30
    c = _ctx(_S, ennemis, _NEIGH)
    assert f.evaluate(_S, None, c, wt) == STAY_PUT_PENALTY == -10.0, (
        "la tuile COURANTE vaut le LITTERAL -10 (`Fix64.op_Implicit(0xfffffff6)`), et le corps "
        "natif `yield break` juste apres -- aucun ennemi n'est compte sur ce bras")
    ranged = f.evaluate(_A, None, c, wt)
    melee = f.evaluate(_B, None, c, wt)
    assert ranged > melee > 0, (
        "poids POSITIFS et RANGED > MELEE : `DEVOUTPUSH_AdjacentRangedEnemy` (50) contre "
        "`DEVOUTPUSH_AdjacentMeleeEnemy` (30) -- c'est le << push >> du nom")
    assert ranged == wt.sub("DevoutPush_AdjacentRangedEnemies", "DEVOUTPUSH_AdjacentRangedEnemy")
    assert melee == wt.sub("DevoutPush_AdjacentRangedEnemies", "DEVOUTPUSH_AdjacentMeleeEnemy")
    # Pas de sujet (`case.unit == null`, regime SPAWN) -> 0.0, degradation NOMMEE.
    sans = dict(c)
    sans["uid"] = None
    assert f.evaluate(_A, None, sans, wt) == 0.0
    assert f.evaluate(None, None, c, wt) == 0.0


def test_etage3b_feuille53_au_registre_utilities_database():
    assert utilities_database(U53) is DEVOUT_PUSH_ADJACENT_RANGED_ENEMIES
    assert UTILITY_BY_TYPE.get(U53) is DEVOUT_PUSH_ADJACENT_RANGED_ENEMIES


# --------------------------------------------------------------------- 4. DISPATCHER MOUVEMENT

class _Ctx:
    """`AiDecisionContext` MINIMAL pour `get_movement_utility` -- il ne lit que `wt` et ce que
    `tile_leaf_ctx` sait deriver d'un contexte pauvre."""
    def __init__(self, wt):
        self.wt = wt
        self.units = []
        self.fpos = []
        self.uid = None
        self.elev_by_pos = {}
        self.is_temporary_by_pos = {}
        self.effects_by_pos = {}


def test_etage4_dispatcher_route_53_et_le_rayon_de_souffle_tient():
    """`get_movement_utility` ne dispatchait QUE `Tile(7)` et `DislikeStartingTiles(28)` : toute
    feuille de `UtilityMovementCase` a signature TILE rendait `0.0`, donc inscrire 53 au registre
    n'aurait RIEN change. La branche generique passe par `utilities_database`.

    RAYON DE SOUFFLE, garde : `62 BioMinefield_MoveTowardsTarget` n'est PAS dans `UTILITY_BY_TYPE`,
    donc le dispatcher continue de rendre `0.0` pour elle -- le comportement mesure de #939 est
    inchange au bit pres."""
    import engine.ai.utilities as AU
    ctx = _Ctx(load_weights())
    assert AU.get_movement_utility(ctx, (0, 0), U53) == 0.0, (
        "ctx sans ennemi -> 0.0 : la route existe, elle n'invente rien")
    assert utilities_database(int(UtilityType.BioMinefield_MoveTowardsTarget)) is None
    assert AU.get_movement_utility(ctx, (0, 0),
                                   int(UtilityType.BioMinefield_MoveTowardsTarget)) == 0.0
    # Un type ABSENT du registre reste a 0.0 -- la branche ne peut pas fabriquer un score.
    assert AU.get_movement_utility(ctx, (0, 0), 9999) == 0.0


def test_etage4b_dispatcher_rend_bien_le_score_de_la_feuille():
    """La route doit RENDRE le score, pas seulement exister. On substitue `tile_leaf_ctx` par le
    contexte synthetique de l'etage 3 : c'est le seul etage qui separe << route branchee >> de
    << route branchee ET lue >>."""
    import engine.ai.utilities as AU
    import engine.utilities.tile as TT
    wt = load_weights()
    ctx = _Ctx(wt)
    ennemis = [{"pos": _R, "vis": "eldarRanger"}, {"pos": _M, "vis": "astraBullgryn"}]
    ancien = TT.tile_leaf_ctx
    try:
        TT.tile_leaf_ctx = lambda _c: _ctx(_S, ennemis, _NEIGH)
        assert AU.get_movement_utility(ctx, _S, U53) == STAY_PUT_PENALTY
        assert AU.get_movement_utility(ctx, _A, U53) == wt.sub(
            "DevoutPush_AdjacentRangedEnemies", "DEVOUTPUSH_AdjacentRangedEnemy")
        assert AU.get_movement_utility(ctx, _B, U53) == wt.sub(
            "DevoutPush_AdjacentRangedEnemies", "DEVOUTPUSH_AdjacentMeleeEnemy")
    finally:
        TT.tile_leaf_ctx = ancien


# ------------------------------------------------------------------ 5. OVERRIDE DE PORTEE

def test_etage5_override_range_est_une_profondeur_pas_un_interrupteur():
    """`MovementQuery$$FindAnyOrAllMoveableTiles` :
    `range = overrideRange.HasValue ? .Value : Movement.CurrentValue`.

    `_move_tiles` etait appele avec `override_range=None` OU pas du tout, et
    `build_from_state` rendait `[]` pour TOUTE valeur non nulle -- `1` compris, alors que les DEUX
    call-sites portes de `PerformAIMovement` passent `Direct(1)`. La garde exerce la SIGNATURE :
    un `override_range` positif doit atteindre le pathfinder comme profondeur."""
    import inspect
    from engine.ai import state_bridge as SB
    sig = inspect.signature(SB._move_tiles)
    assert "override_range" in sig.parameters, (
        "_move_tiles doit accepter l'override : sans lui, build_from_state ne peut que rendre [] "
        "ou la portee Movement -- jamais la profondeur N du natif")
    src = inspect.getsource(SB.build_from_state)
    assert "override_range=max_distance" in src, (
        "build_from_state doit PROPAGER `max_distance` comme override_range ; le rabattre sur [] "
        "pour tout N non nul est le defaut que #996-r1 a mesure (1144 et 1053 passent Direct(1))")
    assert "[] if max_distance is not None" not in src, (
        "l'ancien rabattement (`[] if max_distance is not None`) est REVENU")


@pytest.mark.parametrize("profondeur,attendu", [(0, True), (-1, True)])
def test_etage5b_override_nul_ou_negatif_ne_rend_aucune_tuile(profondeur, attendu):
    """`0` reste le cas `FromCurrentPosition` : l'ensemble se reduit a la graine de l'`OrderedSet`.
    C'est un CAS PARTICULIER de la formule, et il doit le rester."""
    from engine.ai import state_bridge as SB

    class _B:
        def id_at(self, c, r):
            return 1

    class _E:
        def get_component(self, _c):
            return None

    class _S2:
        board = _B()
        effects = None

        def get_entity(self, _u):
            return _E()

    assert (SB._move_tiles(_S2(), 1, "", 1, (0, 0), override_range=profondeur) == []) is attendu
