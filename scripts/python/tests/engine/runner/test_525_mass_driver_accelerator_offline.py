"""#525 -- CLIQUET du port de `1222 MassDriverAccelerator` (`votanChampion` « Kimm »).

Ce que ce fichier garde, et que le probe live (`probe_525_mass_driver_accelerator.py`) ne garde
pas : le probe MESURE (il a besoin d'une session Frida chaude ET d'une injection catalogue -- le
porteur est hors pool) ; ce test GARDE, hors ligne, les proprietes dont la perte serait
SILENCIEUSE.

  [1] CONTRAT DE DISJONCTION -- 1222 est dans `ABILITY_CLASSES` et porte son masque, donc elle doit
      etre ABSENTE des tables « non portee » (`TARGETING_OPTIONS_UNPORTED`,
      `DYNAMIC_TARGET_RULE_UNPORTED`). La faute inverse ne casse rien a l'execution : elle donne
      DEUX sources au masque.

  [2] ORDINAUX MESURES AU SITE -- `probe_313` compare le MIRROR au build et redevient vert des
      qu'on regenere le mirror apres un renumerotage, alors que la valeur ECRITE au site, elle, a
      change. On fige donc ici les entiers LUS au decompile : `rules = 0x102004032` (preset
      `TargetingOptions statics+0x240`, RELU au `.cctor`),
      `MassDriverAccelerator_ExtraMovement = 0x606`, `StatType.MOVEMENT = 0x1`,
      `UtilityType.MovementSuggestion = 0x21`, `GroupType.Ability_Attack = 0x20` /
      `Ability_Attack_2 = 0x21`, `AbilityConstantType.extraMovement = 0xe`, `AbilityAttackType = 0`.

  [3] LES DEUX PROFILS DE DEGAT -- `damageProfile = DirectDamage` (perc,age 100) et
      `damageProfile_2 = Physical` (perc,age 1). C'est ce qui rend le volet SPLASH observable : un
      port qui recopierait le 1er profil sur le 2e rendrait un degat FAUX sans changer ni le
      nombre de cibles ni le nombre de coups. Le test fige aussi le fait que les DEUX jeux de cles
      (`minDmg`/`minDmg_2`) sont passes SEPAREMENT -- ils sont egaux sur ce build, donc l'erreur y
      serait invisible, et c'est exactement pourquoi il faut la garder ici.

  [4] LE SELECTEUR DE BUFF -- `owner@0x30 + AdjacentFriends(owner@0x30)`. Deux fautes possibles et
      toutes deux SILENCIEUSES : collapser sur le seul caster (l'allie adjacent perd son
      +movement), ou ancrer l'`AdjacentFriends` sur la CIBLE (le buff part sur le camp adverse).

  [5] LE SELECTEUR DE SPLASH -- `Enemies(caster@0x48, AdjacentUnits(target@0x60))`. Sans le filtre
      `Enemies`, le port frapperait ses PROPRES allies adjacents a la cible ; le probe ne le voit
      qu'en regime R4 (un allie pose au contact de la cible), ce test le voit toujours.

  [6] L'ANTI-DOUBLE-COMPTE de `UnitMovementRangeWithBonus` -- `If(HasEffect(caster, 0x606),
      Movement, Movement + bonus)`. Le port DOIT prendre la branche NUE quand l'effet est deja
      pose (c'est le cas a l'etage MOVE, apres le `AddStaticStatModifierEffect`), sinon la portee
      de charge est SURESTIMEE de `extraMovement` et la tuile d'atterrissage devient fausse.

  [7] STRUCTURE DE L'ARBRE -- `(buff & move) & IfAlive(caster, AtomicGroup((SetCache & Group(atk1))
      & Group(atk2)))`. L'ORDRE EST la mecanique : le buff AVANT le move (la portee de charge le
      lit), le `SetCache` AVANT la 1re attaque (il FIGE les ennemis adjacents), et l'attaque
      principale AVANT le splash.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre DECLARE LARGE, et c'est mesure : charger une ability tire le registre, le vocabulaire
#: DSL, les Operations, l'IA, le pathfinding et les utilites, plus la cascade des `conftest.py`.
#: Une liste feuille a feuille rougirait au premier import ajoute. `**/` exige un SEGMENT, d'ou les
#: deux globs ET les quatre conftest ecrits un par un.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1222 et TOUT ce que sa fermeture d'imports traverse : registre "
              "d'abilities, tables de ciblage, vocabulaire DSL, selecteurs d'unites, base "
              "d'utilites de tuile. `build: True` parce que les ordinaux figes ici (masque, "
              "EffectType, StatType, UtilityType, GroupType, AbilityConstantType, "
              "AbilityAttackType) sont LUS dans le binaire du build -- un changement de build peut "
              "les renumeroter, et c'est precisement ce que ce fichier doit faire rougir.",
}

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import gameconfig as GC                                                    # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.behaviours import AtomicGroup, Group, If, Seq, SetCache   # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.selectors.accessors import Owner, Target              # noqa: E402
from engine.entities.selectors.units import (AdjacentFriends, AdjacentUnits,   # noqa: E402
                                             Alive, Enemies, Union)
from engine.entities.selectors.geometry import Cache                       # noqa: E402
from engine.entities.stats import StatType                                 # noqa: E402
from engine.entities.triggers import IsAlive                               # noqa: E402
from engine.runner.abilities.attack_type import (ABILITY_ATTACK_TYPE,      # noqa: E402
                                                 AbilityAttackType)
from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage   # noqa: E402
from engine.runner.abilities.behaviours.effects import AddStaticStatModifierEffect   # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,   # noqa: E402
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.abilities.votann import (                               # noqa: E402
    MASS_DRIVER_ACCELERATOR_ID, MASS_DRIVER_CONST_EXTRA_MOVEMENT, MASS_DRIVER_EXTRA_MOVEMENT,
    MassDriverAcceleratorAbility, mass_driver_adjacent_attack_targets_selector,
    mass_driver_attack_tree, mass_driver_buff_targets_selector, mass_driver_buff_tree,
    mass_driver_move_range)
from engine.streams.group_type import GroupType                            # noqa: E402
from engine.utilities.utility_type import UtilityType                      # noqa: E402

ABILITY = int(ActiveAbilityType.MassDriverAccelerator)     # 1222


# ---------------------------------------------------------------- [1] disjonction

def test_1222_est_au_registre_et_a_UNE_seule_source_de_masque():
    """Le CONTRAT : une ability a UNE source de masque, jamais deux."""
    assert ABILITY in ABILITY_CLASSES, "1222 absente d'ABILITY_CLASSES -- le no-op n'est pas leve"
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, "deux sources de masque pour 1222"
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED, (
        "1222 encore dans DYNAMIC_TARGET_RULE_UNPORTED alors que la classe SURCHARGE "
        "get_dynamic_invalid_target_reason")
    assert not (set(ABILITY_CLASSES) & set(TARGETING_OPTIONS_UNPORTED)), (
        "la disjonction globale est rompue")


def test_la_classe_surcharge_bien_la_regle_dynamique():
    """`TargetMatchesDynamicRule` est POSE dans le masque : sans surcharge, la base rend 0 et le
    gate qui donne sa FORME a la zone de ciblage serait DESARME (degradation permissive)."""
    from engine.runner.abilities.base import ActiveAbility
    assert (MassDriverAcceleratorAbility.get_dynamic_invalid_target_reason
            is not ActiveAbility.get_dynamic_invalid_target_reason)


# ---------------------------------------------------------------- [2] ordinaux mesures au site

def test_ordinaux_lus_au_decompile():
    """Ce que `probe_313` ne peut PAS garder : la valeur ECRITE AU SITE au moment de la lecture."""
    opts = MassDriverAcceleratorAbility.TARGETING_OPTIONS
    assert int(opts.rules) == 0x102004032, (
        "masque de 1222 : le preset `TargetingOptions statics+0x240` porte "
        "`*(statics + 0x268) = 0x102004032`")
    assert opts.self_cast is False, "`*(statics + 0x240) = 0` -> isSelfCasting = False"
    assert MASS_DRIVER_EXTRA_MOVEMENT == 0x606 == int(
        EffectType.MassDriverAccelerator_ExtraMovement)
    assert int(StatType.MOVEMENT) == 0x1, "3e argument d'`AddStaticStatModifierEffect`"
    assert int(UtilityType.MovementSuggestion) == 0x21, (
        "4e argument de `SortTilesByUtility` dans `GetMoveTile` -- 0x21 = 33 sur ce build "
        "(32 y est `EnvEndBombardment`)")
    assert int(GroupType.Ability_Attack) == 0x20
    assert int(GroupType.Ability_Attack_2) == 0x21
    assert int(MASS_DRIVER_CONST_EXTRA_MOVEMENT) == 0xe == int(AbilityConstantType.extraMovement)
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack, (
        "3e argument d'`AActiveAbility$$.ctor` = 0 = DirectTargetAttack")


def test_le_masque_se_decompose_EXHAUSTIVEMENT_en_six_flags():
    """`0x102004032` n'est pas un scalaire : c'est la reunion de SIX bits, et le reste doit etre
    NUL. Un bit oublie serait un gate desarme ; un bit invente, un refus fabrique."""
    attendus = (TR.TargetMatchesDynamicRule | TR.CasterHasNotMoved | TR.TargetHasFreeAdjacentTile
                | TR.TargetIsEnemy | TR.AllowObscuredTargetByElevation | TR.TargetIsNotAdjacent)
    assert int(attendus) == 0x102004032
    assert int(MassDriverAcceleratorAbility.TARGETING_OPTIONS.rules) == int(attendus)


# ---------------------------------------------------------------- [3] les deux profils de degat

def test_les_deux_volets_ont_des_profils_DISTINCTS():
    """`GetDamageProfile()` vs `GetDamageProfile2()` : `DirectDamage` (perc,age 100) contre
    `Physical` (perc,age 1). C'est le SEUL etage qui rend le volet splash observable au degat."""
    consts = (GC.ability(MASS_DRIVER_ACCELERATOR_ID) or {}).get("constants") or {}
    assert consts.get("damageProfile") == "DirectDamage"
    assert consts.get("damageProfile_2") == "Physical"
    assert int(consts.get("nrOfHits")) == 1
    assert int(consts.get("nrOfHits_2")) == 1
    assert int(consts.get(MASS_DRIVER_CONST_EXTRA_MOVEMENT.name)) == 1


def test_les_deux_attaques_lisent_des_CLES_SEPAREES():
    """`MinMaxDamage` contre `MinMaxDamage2` -- les valeurs sont EGALES sur ce build, donc la faute
    y serait invisible en mesure. C'est exactement ce qui rend ce cliquet necessaire."""
    arbre = mass_driver_attack_tree()
    atk1 = arbre.child.left.right.child      # Group(atk1).child
    atk2 = arbre.child.right.child           # Group(atk2).child
    assert isinstance(atk1, AttackWithAttackDamage) and isinstance(atk2, AttackWithAttackDamage)
    assert (atk1.min_key, atk1.max_key, atk1.hits_key) == ("minDmg", "maxDmg", "nrOfHits")
    assert (atk2.min_key, atk2.max_key, atk2.hits_key) == ("minDmg_2", "maxDmg_2", "nrOfHits_2")
    assert atk1.profile == "DirectDamage" and atk2.profile == "Physical"
    assert atk1.multi is False, "la cible principale est MONO-cible (target@0x60)"
    assert atk2.multi is True, "le splash resout une LISTE (`Alive(cache)`) -- une attaque PAR cible"


# ---------------------------------------------------------------- [4] le selecteur de BUFF

def test_le_buff_vise_owner_ET_ses_amis_adjacents():
    """`...MassDriverAcceleratorAbility$$GetBuffTargets` = `op_Addition(owner@0x30,
    AdjacentFriends(owner@0x30, unique: 1, selectionType: 3))`."""
    sel = mass_driver_buff_targets_selector()
    assert isinstance(sel, Union)
    assert isinstance(sel.a, Owner), "1er operande = `owner@0x30`, pas le caster generique"
    assert isinstance(sel.b, AdjacentFriends)
    assert isinstance(sel.b.center, Owner), "l'ANCRE de l'anneau est l'owner"
    assert isinstance(sel.b.reference, Owner), (
        "la REFERENCE d'equipe est le 1er argument natif d'`AdjacentFriends`, pas le caster -- "
        "ancrer sur la cible enverrait le buff au camp ADVERSE")


def test_le_buff_est_un_stat_mod_MOVEMENT_de_UN_tour():
    """`AddStaticStatModifierEffect(targets, 0x606, 0x1, Get(GetNumberConstant(0xe)),
    <DSLFormulas+0x20>, isHidden: 0)` -- `+0x20` = `Direct(1)`, LU dans `DSLFormulas$$.ctor`
    (`+0x18 Direct(0) . +0x20 Direct(1) . +0x28 Direct(2) . +0x30 Direct(100) . +0x38 Direct(-1)`).
    Un `duration_rounds` a la place ferait DURER le buff au-dela du cast."""
    b = mass_driver_buff_tree(1)
    assert isinstance(b, AddStaticStatModifierEffect)
    assert b.effect_type == MASS_DRIVER_EXTRA_MOVEMENT
    assert b.stat_type == int(StatType.MOVEMENT)
    assert b.duration_turns == 1 and b.duration_rounds is None, (
        "`DSLFormulas+0x20` = Direct(1) = UN TOUR, pas un round")


# ---------------------------------------------------------------- [5] le selecteur de SPLASH

def test_le_splash_est_filtre_ENEMIES_et_ancre_sur_la_CIBLE():
    """`...MassDriverAcceleratorAbility$$GetAdjacentAttackTargets` = `Enemies(of: caster@0x48,
    entities: AdjacentUnits(target@0x60, unique: 1, selectionType: 3), selectionType: 3)`.

    Sans le `Enemies`, le port frapperait ses PROPRES allies adjacents a la cible (friendly fire) ;
    sans l'ancrage sur `Target`, il frapperait les voisins du CASTER."""
    sel = mass_driver_adjacent_attack_targets_selector()
    assert isinstance(sel, Enemies), "le filtre d'equipe est le noeud EXTERIEUR"
    assert isinstance(sel.inner, AdjacentUnits)
    assert isinstance(sel.inner.center, Target), "l'anneau est ancre sur la CIBLE, pas le caster"


def test_le_splash_relit_un_CACHE_fige_par_SetCache():
    """`SetCache(Cache(GetAdjacentAttackTargets()))` puis `Alive(<le MEME cache>)` : c'est la MEME
    instance de noeud des deux cotes, sinon la memoisation ne sert a rien et la 2e attaque
    re-deriverait la geometrie APRES que la 1re a mute l'etat."""
    arbre = mass_driver_attack_tree()
    set_cache = arbre.child.left.left
    atk2 = arbre.child.right.child
    assert isinstance(set_cache, SetCache)
    assert isinstance(set_cache.node, Cache)
    assert isinstance(atk2.target_sel, Alive)
    assert atk2.target_sel.source is set_cache.node, (
        "le `Alive` de la 2e attaque doit relire l'INSTANCE de `Cache` que `SetCache` a figee")


def test_l_arbre_est_reconstruit_a_CHAQUE_cast():
    """Le noeud `Cache` est STATEFUL (memoisation par instance) : un arbre garde en attribut de
    classe rendrait au 2e cast l'ensemble d'ennemis du PREMIER."""
    a, b = mass_driver_attack_tree(), mass_driver_attack_tree()
    assert a.child.left.left.node is not b.child.left.left.node


# ---------------------------------------------------------------- [6] anti-double-compte de portee

class _Stub:
    """Etat MINIMAL pour exercer `mass_driver_move_range` : la fonction ne lit que la stat
    MOVEMENT du caster et la presence de l'effet 0x606."""

    class _Stats:
        def __init__(self, mv):
            self._mv = mv

        def get_stat(self, _stat, _default=0):
            return self._mv

    class _Ctx:
        def __init__(self, mv):
            self.stats = _Stub._Stats(mv)

    class _StatsComponent:
        def __init__(self, mv):
            self.ctx = _Stub._Ctx(mv)

    class _Entity:
        def __init__(self, mv):
            self._c = _Stub._StatsComponent(mv)

        def get_component(self, _cls):
            return self._c

    class _Effects:
        def __init__(self, present):
            self._present = present

        def has_effect(self, _uid, effect_type=None, name=None):
            return self._present and effect_type == MASS_DRIVER_EXTRA_MOVEMENT

    def __init__(self, mv, effet_pose):
        self._e = _Stub._Entity(mv)
        self.effects = _Stub._Effects(effet_pose)

    def get_entity(self, _eid):
        return self._e


def test_la_portee_ne_compte_le_bonus_QU_UNE_FOIS():
    """`UnitMovementRangeWithBonus(caster@0x48, 0x606, Get(GetNumberConstant(0xe)))` =
    `If(HasEffect(caster, 0x606), StatAmount(MOVEMENT), Sum(StatAmount(MOVEMENT), bonus))`.

    Regime GATE (effet PAS encore pose, `GetDynamicInvalidTargetReason` avant tout cast) ->
    `MOVEMENT + extraMovement`. Regime MOVE (effet pose par l'etage precedent, stat DEJA bonifiee)
    -> `MOVEMENT` nu. Prendre la mauvaise branche a l'etage MOVE SURESTIME la portee de charge de
    `extraMovement` et change la tuile d'atterrissage."""
    bonus = int(((GC.ability(MASS_DRIVER_ACCELERATOR_ID) or {}).get("constants") or {})
                .get(MASS_DRIVER_CONST_EXTRA_MOVEMENT.name) or 0)
    assert bonus == 1
    # GATE : stat de base 3, effet absent -> 3 + 1 = 4
    assert mass_driver_move_range(_Stub(3, False), 1) == 3 + bonus
    # MOVE : stat DEJA bonifiee a 4, effet present -> 4 (et surtout PAS 5)
    assert mass_driver_move_range(_Stub(3 + bonus, True), 1) == 3 + bonus


# ---------------------------------------------------------------- [7] structure de l'arbre

def _feuilles(node, out=None):
    """Aplati un arbre de behaviours en la LISTE de ses feuilles, dans l'ordre d'execution."""
    out = [] if out is None else out
    if isinstance(node, Seq):
        _feuilles(node.left, out)
        _feuilles(node.right, out)
    elif isinstance(node, (AtomicGroup, Group)):
        out.append(type(node).__name__)
        _feuilles(node.child, out)
    elif isinstance(node, If):
        out.append(("If", type(node.cond).__name__))
        _feuilles(node.then, out)
    else:
        out.append(type(node).__name__)
    return out


def test_l_ordre_des_etages_est_celui_du_decompile():
    """`AtomicGroup( (SetCache & Group(atk1, caster, 0x20)) & Group(atk2, caster, 0x21) )`.

    L'ORDRE EST la mecanique : `SetCache` FIGE les ennemis adjacents AVANT la 1re attaque, et
    l'attaque principale precede le splash. Un `SetCache` place apres la 1re attaque relirait un
    plateau deja mute."""
    arbre = mass_driver_attack_tree()
    assert isinstance(arbre, AtomicGroup)
    assert _feuilles(arbre) == ["AtomicGroup", "SetCache",
                                "Group", "AttackWithAttackDamage",
                                "Group", "AttackWithAttackDamage"]
    assert arbre.child.left.right.group_id == int(GroupType.Ability_Attack)
    assert arbre.child.right.group_id == int(GroupType.Ability_Attack_2)


def test_le_volet_attaque_est_gate_par_IsAlive_du_caster():
    """`IfAlive(caster@0x48, <AtomicGroup>)` = `If(IsAlive(caster), ...)` -- le natif ne fait que
    composer les deux noeuds. Regime ou il mord : le caster MEURT pendant la charge."""
    import inspect
    from engine.runner.abilities import votann as V
    src = inspect.getsource(V.MassDriverAcceleratorAbility.execute_behaviour)
    assert "IsAlive(Caster())" in src, (
        "le gate `IfAlive(caster@0x48, ...)` a disparu : le splash et l'attaque partiraient meme "
        "si Kimm est mort pendant la charge")
    assert isinstance(IsAlive(Owner()), IsAlive)      # le noeud existe bien dans le vocabulaire


def test_le_buff_precede_le_move_qui_precede_l_attaque():
    """`(buff & move) & IfAlive(...)` : la portee de charge LIT le buff (cf. [6]), donc l'inverser
    changerait la tuile d'atterrissage sans rien changer au degat -- un ecart qu'aucun total ne
    montre."""
    import inspect
    from engine.runner.abilities import votann as V
    src = inspect.getsource(V.MassDriverAcceleratorAbility.execute_behaviour)
    i_buff = src.index("mass_driver_buff_tree")
    i_range = src.index("mass_driver_move_range")
    i_move = src.index("MoveUnit(Caster()")
    i_atk = src.index("mass_driver_attack_tree")
    assert i_buff < i_range < i_move < i_atk, (
        "ordre des etages rompu : buff -> portee -> move -> attaque")
