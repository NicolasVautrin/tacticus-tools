"""#501 -- CLIQUET du port de `1165 MightFromBelow` (The Patermine `genesPatriarch`).

Ce que ce fichier garde, et que le probe live (`probe_501_might_from_below.py`) ne garde pas :
le probe MESURE (il a besoin d'une session Frida chaude) ; ce test GARDE, hors ligne, les quatre
proprietes dont la perte serait SILENCIEUSE.

  [1] CONTRAT DE DISJONCTION -- 1165 est dans `ABILITY_CLASSES` et porte son masque, donc elle doit
      avoir DISPARU des quatre tables « non portee ». La faute inverse ne casse rien a l'execution :
      elle donne DEUX sources au masque, et c'est ce qui a rendu `master` rouge trois commits
      d'affilee sur 1048 (#489).

  [2] ORDINAUX MESURES AU SITE -- `probe_313` compare le MIRROR au build et redevient vert des
      qu'on regenere le mirror apres un renumerotage, alors que la valeur ECRITE au site, elle, a
      change. On fige donc ici les entiers LUS au decompile : `rules = 0x4000`, `Decoy = 0x41d`,
      `Ability_Attack = 0x20`, `Ability_Summon = 0x22`, `AbilityAttackType = 0`.

  [3] STRUCTURE DES TROIS ARBRES -- le natif appelle `AActiveAbility$$Execute` TROIS fois
      (attaque / `KillDeadUnits` / `IfAlive(Spawn)`), et c'est l'ORDRE qui EST la mecanique
      kill -> decoy -> summon. On garde la forme de chaque arbre, feuille par feuille.

  [4] FRAICHEUR DE L'`AbilityEntities` -- le sous-arbre de tuiles est evalue au TROISIEME Execute,
      donc il voit le `genesSmnDecoy` que `CosmicHorror_OnKillAbility` a pose PENDANT le premier.
      Le figer (une seule construction d'`AbilityEntities`, ou pire une liste de tuiles resolue en
      amont) rendrait 0 summon SANS ERREUR -- exactement le no-op silencieux que #501 ferme.
      MESURE qui l'etablit : sur le cast qui tue, les steps natifs donnent
      `Ability_Attack@3 ... AddUnit(decoy)@28 ... Ability_Summon@42 ... AddUnit(genestealer)@48`.

  [5] LE CRUSH AU SPAWN -- `AddUnitOperation$$KillSteppableUnits` : poser une unite sur la tuile
      d'un `Steppable` le DETRUIT. Sans lui le port laissait un decoy VIVANT en trop (mesure du
      2026-08-07 : `decoys live=[(6,7) mort] offline=[(6,7) VIVANT]`).

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre DECLARE LARGE, et c'est mesure : charger une ability tire le registre, le vocabulaire
#: DSL, les Operations, l'IA et le pathfinding (~139 modules), plus la cascade des deux
#: `conftest.py`, qui tire elle-meme une vingtaine de probes de la racine. Une liste feuille a
#: feuille rougirait au premier import ajoute. `**/` exige un SEGMENT, d'ou les deux globs.
DECLENCHEUR = {
    "chemins": (
        # Les QUATRE `conftest.py` de la cascade pytest jusqu'a ce fichier -- il est dans
        # `tests/engine/runner/`, donc il y en a deux de plus que les deux du socle commun. Ils
        # sont ecrits un par un et non par un glob : `scripts/python/tests/**/conftest.py`
        # n'attraperait PAS `scripts/python/tests/conftest.py` (le `**/` exige un SEGMENT).
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1165 et TOUT ce que sa fermeture d'imports traverse : registre "
              "d'abilities, tables de ciblage, vocabulaire DSL, Operations de spawn et de mort. "
              "`build: True` parce que les ordinaux figes ici (masque, trait Decoy, GroupType, "
              "AbilityAttackType) sont LUS dans le binaire du build -- un changement de build peut "
              "les renumeroter, et c'est precisement ce que ce fichier doit faire rougir.",
}

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.behaviours import Group, If                           # noqa: E402
from engine.entities.selectors.accessors import ActiveTarget, Target       # noqa: E402
from engine.entities.selectors.tiles import Caster                         # noqa: E402
from engine.entities.selectors.units import (AdjacentFriends, Tiles,       # noqa: E402
                                             UnitsDamagedThisPhase, UnitsWithTrait)
from engine.entities.traits.unit_trait import UnitTrait                    # noqa: E402
from engine.entities.triggers import IsAlive                               # noqa: E402
from engine.streams.group_type import GroupType                            # noqa: E402
from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage   # noqa: E402
from engine.runner.abilities.behaviours.lifecycle import KillDeadUnits     # noqa: E402
from engine.runner.abilities.behaviours.summon import PerformAIAttack, Spawn   # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.attack_type import (AbilityAttackType,        # noqa: E402
                                                 ABILITY_ATTACK_TYPE)
from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,   # noqa: E402
                                               TARGETING_OPTIONS_UNPORTED)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.abilities.loki import might_from_below as MFB           # noqa: E402

ABILITY = int(ActiveAbilityType.MightFromBelow)     # 1165


# ------------------------------------------------------------------ [1] contrat de disjonction --

def test_1165_est_au_registre_et_sort_des_tables_non_portees():
    """Une ability qui ENTRE dans `ABILITY_CLASSES` SORT, dans le meme commit, de toutes les tables
    « face COMBAT non portee ». `probe_181` ne voit PAS cette faute : il verifie qu'un masque
    EXISTE, jamais qu'il n'est declare QU'UNE FOIS."""
    assert ABILITY in ABILITY_CLASSES, "1165 doit etre au registre COMBAT"
    assert ABILITY_CLASSES[ABILITY] is MFB.MightFromBelowAbility
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, (
        "1165 a DEUX sources de masque : la classe ET `TARGETING_OPTIONS_UNPORTED`")
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED, (
        "1165 n'a aucune regle dynamique (pas de bit `TargetMatchesDynamicRule`)")


def test_1165_hors_du_perimetre_pool_sans_classe_combat():
    """Le pendant, cote PERIMETRE : `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` (#433) exige qu'AUCUNE de
    ses entrees ne soit dans `ABILITY_CLASSES`. On le lit ici plutot que d'attendre que l'autre
    fichier rougisse -- les deux axes sont distincts et ont deja ete rates separement."""
    import importlib
    mod = importlib.import_module("tests.engine.test_433_r4_r2_r1_r2_ability_range_offline")
    assert ABILITY not in mod.POOL_ABILITIES_WITHOUT_COMBAT_CLASS


# ---------------------------------------------------------------- [2] ordinaux LUS au decompile --

def test_masque_de_ciblage_verbatim():
    """`MightFromBelowAbility$$.ctor` recopie les 0x40 octets du preset
    `<TargetingOptions statics>+0x40` (forme STATIC-COPY, aucun `TargetingOptions$$.ctor` appele) et
    le passe a `AActiveAbility$$.ctor(this, &opts, 0)`. Les valeurs sont celles ECRITES par
    `IdunBattle.Core.Services.TargetingOptions$$.cctor` a ce preset -- relues pour CETTE ability,
    jamais recopiees d'une voisine (le preset `+0x180` porte `0x4002` et `RANGE_FROM_CONFIG`)."""
    opts = MFB.MightFromBelowAbility.TARGETING_OPTIONS
    assert opts is not None
    assert int(opts.rules) == 0x4000, "<preset +0x40> +0x28 = 0x4000, et RIEN d'autre"
    assert int(opts.rules) == int(TR.TargetIsEnemy)
    assert opts.self_cast is False, "<preset> +0x00 isSelfCasting = 0"
    assert int(opts.force_melee_target) == 1, "<preset> +0x20 forceMeleeTarget = RangedBool.False"
    # `<preset> +0x08` = recopie de `<TargetingRange statics>+0x30` = RANGE_ADJACENT.
    assert int(opts.range.only_adjacent) == 0 and int(opts.range.override_range) == 1
    assert not opts.range.use_range_from_config and not opts.range.use_whole_board


def test_ability_attack_type_est_le_3e_argument_du_ctor():
    """`AActiveAbility$$.ctor(this, targetingOptions, abilityAttackType)` ecrit son 3e argument en
    `this+0x68`. Pour 1165 le litteral est `0` -- transcrit tel quel, JAMAIS deduit du fait que
    l'arbre summone (`1 = SummonAndAttackTarget` est ce que porte `IncursionAbility`)."""
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack
    assert int(AbilityAttackType.DirectTargetAttack) == 0


def test_ordinaux_du_site():
    """Les entiers LUS au decompile et ECRITS au site. `probe_313` garde le mirror contre le build ;
    ce test-ci garde la VALEUR ecrite, qui ne bouge pas quand on regenere le mirror."""
    assert int(MFB.DECOY_TRAIT) == 0x41d, "`UnitsWithTrait(..., 0x41d, 3)` = UnitTrait.Decoy"
    assert int(UnitTrait.Decoy) == 1053
    assert int(GroupType.Ability_Attack) == 0x20    # `Group(attack, caster, 0x20)`
    assert int(GroupType.Ability_Summon) == 0x22    # `Group(spawn,  caster, 0x22)`
    assert ABILITY == 1165


# ----------------------------------------------------------------- [3] structure des trois arbres

def test_arbre_1_attaque():
    """`Group( AttackWithAbilityDamage(Caster@0x48, Target@0x60, MinMaxDamage, Direct(profil),
    GetHits(), AbilityOrEffect(1165), 2), Caster@0x48, GroupType.Ability_Attack )`."""
    t = MFB.might_from_below_attack_tree("Psychic")
    assert isinstance(t, Group)
    assert t.group_id == int(GroupType.Ability_Attack)
    assert isinstance(t.targets_sel, Caster)
    leaf = t.child
    assert isinstance(leaf, AttackWithAttackDamage)
    assert isinstance(leaf.target_sel, Target), "cible = le singleton Target@0x60 (mono-cible)"
    assert leaf.ability_id == MFB.MIGHT_FROM_BELOW_ID
    assert leaf.profile == "Psychic"
    assert leaf.is_melee is True, "`attackRangeType = Melee` au kit"
    assert leaf.multi is False and leaf.pick_n is None
    # LE DISCRIMINANT DE FAMILLE : `list_xrefs` place l'appel de `MightFromBelowAbility$$
    # ExecuteBehaviour` sur `DSLBehaviors$$AttackWithAbilityDamage` -> `AbilityDamageBehaviour`
    # (un tirage de valeur par coup, AUCUN crit), pas sur `AttackWithAttackDamage`.
    assert leaf.native_factory == "ability"
    # LE DISCRIMINANT VS 1027 : le natif passe ici un `hits:System.Int32`
    # (`GetNumberConstant(0x2f)`), PAS un `IAmountFormula`. Un `hits_override` non nul serait le
    # signe qu'on a recopie la surcharge de `PsychicMaelstrom`.
    assert leaf.hits_override is None and leaf.hits is None
    assert leaf.hits_key == "nrOfHits"
    assert leaf.min_key == "minDmg" and leaf.max_key == "maxDmg", "`MinMaxDamage` = mode BORNES"
    assert leaf.ability_type == ABILITY


def test_arbre_2_kill_dead_units():
    """`KillDeadUnits( killer = Caster@0x48, targets = UnitsDamagedThisPhase(Caster@0x48) )` -- la
    phase qui SEPARE l'attaque du summon cote natif."""
    t = MFB.might_from_below_kill_tree()
    assert isinstance(t, KillDeadUnits)
    assert isinstance(t.subject_sel, Caster)
    assert isinstance(t.units_sel, UnitsDamagedThisPhase)
    assert isinstance(t.units_sel.attacker, Caster)


def test_arbre_3_summon():
    """`IfAlive(Caster@0x48, Group(Spawn(...), Caster@0x48, Ability_Summon), null)` -- `IfAlive` est
    LITTERALEMENT `If(IsAlive(sel), then, else)` (`DSLBehaviors$$IfAlive` appelle
    `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If`), donc la composition EST le mirror."""
    t = MFB.might_from_below_summon_tree()
    assert isinstance(t, If)
    assert isinstance(t.cond, IsAlive) and isinstance(t.cond.unit, Caster)
    assert t.otherwise is None, "le 4e argument natif de `If` est `null`"
    g = t.then
    assert isinstance(g, Group) and g.group_id == int(GroupType.Ability_Summon)
    sp = g.child
    assert isinstance(sp, Spawn)
    assert sp.summon_ability == MFB.MIGHT_FROM_BELOW_ID
    assert sp.unit_id_constant == "unitId", "`GetStringConstant(config, 0)`"
    assert sp.pick_n is None, "aucun `PickRandomly` natif : TOUS les decoys adjacents"
    assert sp.spawn_as_single_unit is False
    assert sp.ability_state is None, "`WithStatsFromConfig(config, abilityState)` d'une ACTIVE"
    # on-appearance = `PerformAIAttackFromCurrentPosition(ActiveTarget@0x68)` : le summon attaque
    # immediatement et NE BOUGE PAS (`+0x70 allowMoveAction = 0`, `+0x78 moveAmount = Direct(0)`).
    assert isinstance(sp.on_appearance, PerformAIAttack)
    assert isinstance(sp.on_appearance.tile_selector, ActiveTarget)
    assert sp.on_appearance.allow_move_action is False
    assert sp.on_appearance.move_amount == 0


def test_selecteur_de_tuiles_est_le_meme_que_get_possible_spawn_tiles():
    """`Tiles( UnitsWithTrait( AdjacentFriends(Caster@0x48, CasterTile@0x50, unique), Decoy, 3 ) )`
    -- et c'est le MEME sous-arbre que `MightFromBelowAbility$$GetPossibleSpawnTiles` : un seul
    artefact natif, un seul foyer porte."""
    sel = MFB.might_from_below_spawn_tiles()
    assert isinstance(sel, Tiles)
    # `as_ids=True` : la feuille `Spawn` consomme des IDS d'entite-tuile. Une liste de POSITIONS y
    # rendrait `None` a chaque `_spawn_config_grot` -> spawn silencieusement absent.
    assert sel.as_ids is True
    wt = sel.units
    assert isinstance(wt, UnitsWithTrait) and int(wt.trait) == int(UnitTrait.Decoy)
    assert isinstance(wt.source, AdjacentFriends)
    assert isinstance(wt.source.center, Caster)
    assert wt.source.reference is None, "la reference d'equipe EST le centre (= le caster)"
    # Le sous-arbre monte par la classe et celui de `GetPossibleSpawnTiles` sont produits par LA
    # MEME fonction : on l'atteste par la forme, pas par l'identite d'objet (une instance NEUVE par
    # cast, comme tous les arbres du port).
    sp = MFB.might_from_below_summon_tree().then.child
    assert type(sp.tile_selector) is type(sel)
    assert type(sp.tile_selector.units) is type(wt)


# ------------------------------------------------- [4] fraicheur de l'`AbilityEntities` par phase

def _etat_nu():
    """Un VRAI `State`, vide. On n'ecrit pas un faux : `entities_from_state` lit une dizaine de
    slots (`current_player_id`, `effects`, `board`, ...) et un double partiel casse sur le premier
    oubli -- ce qui ferait rougir ce test pour une raison qui n'a rien a voir avec 1165. Les trois
    arbres s'executent alors A VIDE, et ce qu'on mesure est la CADENCE des constructions
    d'`AbilityEntities`, pas un degat."""
    from engine.runner.state import State
    return State()


def test_les_trois_phases_construisent_chacune_leur_ability_entities(monkeypatch):
    """L'`AbilityEntities` natif porte une REF D'ETAT ; `entities_from_state` FIGE sa liste `units`
    a la construction. Reutiliser un seul contexte pour les trois phases rendrait le decoy pose
    PENDANT l'attaque INVISIBLE au selecteur du summon -> 0 summon, sans erreur.

    MESURE qui etablit que le natif, lui, le voit : sur le cast qui tue, les steps donnent
    `Ability_Attack` PUIS `AddUnit(genesSmnDecoy)` PUIS `Ability_Summon` PUIS
    `AddUnit(genesSmnGenestealer)` sur la MEME tuile."""
    appels = []
    vrai = MFB.entities_from_state

    def espion(state, caster_id, target_id=None, actor_id=None):
        appels.append((caster_id, target_id))
        return vrai(state, caster_id, target_id, actor_id)

    # Le patch porte sur le module CONSOMMATEUR (`might_from_below`), pas sur `behaviours.context` :
    # le module lie le nom au niveau module (forme A), donc c'est la seule liaison qui morde.
    monkeypatch.setattr(MFB, "entities_from_state", espion)
    out = MFB.MightFromBelowAbility().execute_behaviour(_etat_nu(), 1, 2)
    assert out is not None and out.get("dsl") is True
    assert len(appels) == 3, (
        "une construction d'`AbilityEntities` PAR PHASE (attaque / KillDeadUnits / summon) ; "
        "en compter moins fige l'etat et rend le summon aveugle au decoy : %r" % (appels,))
    assert appels == [(1, 2)] * 3, "meme caster et meme cible aux trois phases"


def test_cible_absente_ne_caste_rien():
    """`target_id is None` -> `None` : le natif n'a pas de cible a passer a `Target@0x60`, et le
    masque `TargetIsEnemy` sans `CasterIsPossibleTarget` interdit le cast sans cible."""
    assert MFB.MightFromBelowAbility().execute_behaviour(_etat_nu(), 1, None) is None


# --------------------------------------------------------------------- [5] le crush au spawn -----

def test_le_spawn_crushe_les_steppables_de_sa_tuile():
    """`AddUnitOperation$$Execute` appelle `$$KillSteppableUnits(killer, steppableUnits)` (xref
    UNIQUE) : poser une unite sur la tuile d'un `Steppable` le DETRUIT. Le port n'a qu'UNE
    implementation de ce crush -- celle du move -- et le foyer du spawn doit l'appeler.

    On l'atteste par le CODE du foyer plutot que par un montage : le regime ou il mord (spawn sur
    une tuile OCCUPEE) n'est atteignable que par un selecteur sans `CanAddUnit`, c'est-a-dire par
    1165 elle-meme, dont la mesure live est le probe."""
    import inspect
    from engine.runner.operations import spawn as spawn_ops
    src = inspect.getsource(spawn_ops._spawn_config_grot)
    assert "_kill_steppable_units(" in src, (
        "le foyer de spawn n'appelle plus `KillSteppableUnits` : un decoy VIVANT resterait sous "
        "le summon, et resservirait de tuile de summon au cast suivant")
    # Et le crush utilise bien LE foyer commun, pas une seconde implementation.
    from engine.runner.operations.movement import _kill_steppable_units as foyer
    assert spawn_ops._kill_steppable_units is foyer
