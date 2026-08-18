"""#419-r1-tr9-r4-r3 -- LA FACE COMBAT DU FOLD `Boltstorm` : L'ENONCE DU RESIDU EST **REFUTE**.

La fiche disait : « la face COMBAT du fold additional-damage n'est pas portee -- `engine/runner` ne
connait de `1128` que son entree `ABILITY_ATTACK_TYPE` ; aucun mirror de
`Boltstorm_NormalAttackAbility$$GetAdditionalDamageBehaviour` / `$$ExecuteBoltstorm` ».

Au commit courant c'est FAUX, et de trois facons :
  * `engine/runner/abilities/loki/additional_targets.py::_attack_damage_leaf` **EST** le mirror de
    `...Boltstorm_NormalAttackAbility$$GetAdditionalDamageBehaviour` (sa docstring le cite) ;
  * `::primary_fold_tree` **EST** le mirror de `$$GetCustomNormalAttackBehaviour` (le `b2` du
    `Attack(...)` de `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`) ;
  * `::execute_additional_targets_attacks` **EST** le mirror de `$$ExecuteBoltstorm` : il joue le
    FOLD puis le CLEAVE, dans l'ordre natif, chacun sous SA gate.
Le foyer que la fiche nommait (`operations/additional_hits.py`) est celui du canal #179
(`ExecuteAdditionalHitsWithDamageProfileType`), qui est le **`b3`** -- un TROISIEME volet, frere du
fold, pas son foyer.

CE FICHIER NE PORTE DONC RIEN : il FIGE, par mesure, les invariants que la RE re-conduite au build
`t6dpr4k06g` etablit, pour qu'un futur refactor ne les perde pas en silence.

RE (decompile = verite), les pieces qui commandent chaque assertion :

    Boltstorm_NormalAttackAbility$$GetAdditionalDamageBehaviour(abilityState, target) =
        DSLBehaviors$$AttackDamage(
            caster          = <DSLSelectors+0x48>,
            target          = target,
            amount          = DSLFormulas$$RandomAmount( GetVariableForLevel(0xc = minDmg),
                                                         GetVariableForLevel(0xd = maxDmg) ),
            damageProfile   = Direct(Nullable(GetEnumConstant(0x2e = damageProfile))),
            hits            = DSLFormulas$$Direct( GetNumberConstant(0x2f = nrOfHits) ),
            abilityOrEffect = AbilityOrEffect$$op_Implicit(this),
            options         = default(Nullable<AttackDamageBehaviourOptions>) )   # 0x28 octets a ZERO

    Boltstorm_NormalAttackAbility$$ExecuteBoltstorm(abilityState, entities, attackWeapon) :
        targets = BoltstormAbility$$GetAdditionalTargets(<dsl>, Direct(attackWeapon.Range))
        ExecuteInformWeapon ; ExecuteNormalAttack           # <- la primaire, dont le `b2` EST le fold
        ExecuteAtomic( Foreach(targets, t => Attack(Caster, t, GetAdditionalDamageBehaviour(., t))) )
        ExecuteTriggerAbilities

=> LE FOLD PART **DEUX** FOIS, et pas sous la meme gate : une fois sur la cible PRIMAIRE, sous
`If(DSLTriggers$$IsRangedPosition)` (le `b2`), et une fois par cible ADDITIONNELLE, **sans aucune
gate de position** (le `Foreach`, gate seulement par `WeaponProfile$$get_IsMelee == 0` en amont).

=> LE NOMBRE DE COUPS DU FOLD **REPASSE PAR LES MODIFICATEURS**. `options` etant un `Nullable` VIDE,
son octet +3 (`BypassHitModifiers`) est `false`, donc
`IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` ne rend PAS la base telle quelle : il
appelle `IBattleQuery` slot **182** (`GetAttackHits`, overload `context`). C'est le point que la RE
signale comme la regression silencieuse la plus probable d'un port naif.

ASCII only. OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

# Le garde `declencheur_guard` (#486-r15) exige de dire ce qui doit changer pour que ce fichier
# change de verdict. Ici la reponse n'est PAS vide : le fichier LIT le gameconfig
# (`nrOfHits`/`damageProfile` de `Boltstorm`), donc une regeneration du gameconfig peut le faire
# bouger sans qu'aucun import n'ait change.
DECLENCHEUR = {
    "chemins": ("data/gameconfig.json",),
    "build": False,
    "toujours": False,
    "raison": (
        "Ce fichier confronte le port au NATIF par deux canaux : sa STRUCTURE (les feuilles montees "
        "par `additional_targets.py`, couverte par la cascade d'imports) et les LITTERAUX de la "
        "config d'ability `Boltstorm` (`nrOfHits`, `damageProfile`), qui vivent dans le gameconfig "
        "et qu'aucun import ne revele. Le `build` reste False : rien ici ne lit `data/symbols/**` "
        "ni le binaire -- la RE est CITEE en docstring, pas relue a l'execution."
    ),
}

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest                                                              # noqa: E402

import gameconfig as GC                                                    # noqa: E402
from engine.entities.unit_context import UnitContext                       # noqa: E402
from engine.runner.abilities.loki import additional_targets as AT          # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,     # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.prng import IntBasedMersenneTwister                     # noqa: E402
from engine.runner.state import State                                      # noqa: E402

PASSIF = "Boltstorm"


def _entree():
    e = AT.NORMAL_ATTACK_CLEAVES.get(PASSIF)
    assert e is not None, ("`Boltstorm` doit etre dans NORMAL_ATTACK_CLEAVES -- sans lui ce fichier "
                           "ne mesure RIEN : %r" % (sorted(AT.NORMAL_ATTACK_CLEAVES),))
    return e


def test_les_deux_gates_de_Boltstorm_sont_les_INVERSES_de_la_famille():
    """`Boltstorm_NormalAttackAbility$$ExecuteBehaviour` route vers `$$ExecuteBoltstorm` sur
    `WeaponProfile$$get_IsMelee == 0` (sa branche MELEE ne folde ni ne cleave), et son
    `$$GetCustomNormalAttackBehaviour` gate sur `DSLTriggers$$IsRangedPosition`. Les TROIS autres
    membres de la famille sont a l'endroit -- c'est cette asymetrie qu'un refactor efface."""
    e = _entree()
    assert e.cleaves_when_melee is False, e.cleaves_when_melee
    assert e.primary_fold_when_melee_position is False, e.primary_fold_when_melee_position
    assert e.needs_weapon_range is True, e.needs_weapon_range
    # TEMOIN de discrimination : un membre a l'endroit, sinon l'assertion ci-dessus passerait sur
    # une table ou TOUT vaudrait False.
    autre = AT.NORMAL_ATTACK_CLEAVES.get("RighteousRepugnance")
    assert autre is not None and autre.cleaves_when_melee is True, autre
    assert autre.primary_fold_when_melee_position is True, autre


def test_le_fold_lit_nrOfHits_et_damageProfile_de_la_config_du_PASSIF():
    """`GetNumberConstant(0x2f = nrOfHits)` et `GetEnumConstant(0x2e = damageProfile)` sur
    `this+0x60` = la `AbilityConfiguration` de l'ability. Le gameconfig ne porte QU'UNE config
    nommee `Boltstorm` (cote passif) -- il n'existe aucune `Boltstorm_NormalAttack`."""
    cfg = GC.ability(PASSIF) or {}
    cst = cfg.get("constants") or {}
    assert str(cst.get("nrOfHits")) == "3", cst
    assert cst.get("damageProfile") == "Bolter", cst
    assert GC.ability("Boltstorm_NormalAttack") in (None, {}), (
        "le gameconfig ne doit porter QUE la config du passif : si une config d'attaque normale "
        "apparait, la source du fold change et cette tranche est a rejouer")
    # les DEUX variables du `RandomAmount`
    var = cfg.get("variables") or {}
    assert "minDmg" in var and "maxDmg" in var, sorted(var)


@pytest.mark.parametrize("volet", ("fold", "cleave"))
def test_la_feuille_du_fold_porte_les_options_ZEROEES_et_traverse_GetAttackHits(volet):
    """`options = default(Nullable<AttackDamageBehaviourOptions>)` -- les 0x28 octets a ZERO. Les
    quatre drapeaux que le port exprime doivent donc etre FAUX, et surtout `BypassHitModifiers`
    (octet +3, `skip_hits_modifiers` cote port) : c'est LUI qui deciderait que les 3 coups sont
    DEJA FINAUX. Il ne l'est pas -> le fold repasse par le slot 182 d'`IBattleQuery`, comme la base.

    Le seul champ qui DIFFERE entre les deux volets est `isOutsideAttack` (octet +0), et c'est
    structurel : le fold est une feuille NUE dans le `Attack(...)` de la primaire, le cleave a son
    PROPRE `DSLBehaviors$$Attack` par cible."""
    e = _entree()
    if volet == "fold":
        f = AT.primary_fold_tree(e, is_melee=False)
        attendu_outside = False
    else:
        arbre = AT.cleave_tree(e, is_melee=False, weapon_range=2)
        f = _feuille_du_cleave(arbre)
        attendu_outside = True
    assert f.skip_hits_modifiers is False, "BypassHitModifiers doit rester FAUX"
    assert f.force_crit is False and f.force_overkill is False, (f.force_crit, f.force_overkill)
    assert int(f.amount_spread_pct) == 0, f.amount_spread_pct
    assert f.is_outside_attack is attendu_outside, (volet, f.is_outside_attack)
    # la SOURCE des coups : la config, par la cle `nrOfHits` -- jamais un litteral au site.
    assert f.hits is None and f.hits_override is None, (f.hits, f.hits_override)
    assert f.hits_key == "nrOfHits", f.hits_key
    # le NIVEAU vient du slot PASSIF (l'attaque normale substituee est montee avec l'`AbilityState`
    # du passif : `ActiveAbilityComponent$$Add(entity, abilityType, triggeredAbilityState, null)`).
    assert f.level_slot == "passive", f.level_slot
    assert f.profile == "Bolter", f.profile
    assert f.native_factory == "attack", f.native_factory


def _feuille_du_cleave(arbre):
    """La feuille `AttackWithAttackDamage` sous `AtomicGroup(Foreach(sel, <feuille>))`. On la
    RETROUVE par balayage des attributs plutot que par un chemin en dur : la forme de l'arbre est ce
    que le test veut mesurer, pas ce qu'il veut supposer."""
    vu, pile = set(), [arbre]
    while pile:
        n = pile.pop()
        if id(n) in vu:
            continue
        vu.add(id(n))
        if type(n).__name__ == "AttackWithAttackDamage":
            return n
        for slot in (getattr(type(n), "__slots__", ()) or ()):
            pile.append(getattr(n, slot, None))
    raise AssertionError("aucune feuille AttackWithAttackDamage sous le cleave -- l'arbre a change")


def _etat_boltstorm(adjacent: bool):
    """Deux unites : `templAggressor` (le porteur lineup de `Boltstorm`) et une cible. `adjacent`
    pilote `IsMeleePosition`, c'est-a-dire la gate du fold PRIMAIRE."""
    st = State()
    st.rng = IntBasedMersenneTwister(4463111)
    ids = []
    for i, vis in enumerate(("templAggressor", "ultraEliminatorSgt")):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(HealthComponent(hp=100000, hp_max=100000))
        e.add_component(OwnerComponent(team=i, player=i))
        e.add_component(PositionComponent(0 if i == 0 else (1 if adjacent else 6), 0))
        e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id=vis)))
        ids.append(e.id)
    return st, ids[0], ids[1]


def test_le_fold_primaire_part_A_DISTANCE_et_PAS_au_contact():
    """LA GATE, MESUREE SUR L'EXECUTION REELLE (pas sur la table) : `If(IsRangedPosition, <fold>)`.
    `IsRangedPosition = op_LogicalNot(IsMeleePosition)`, et `IsMeleePosition` invoque le slot 9
    d'`IBattleQuery` (`BattleQuery$$AreUnitsInMelee`) -> l'adjacence HEX.

    Les deux regimes sont joues, et le CONTRE-CAS (au contact) doit rendre `None` : sans lui,
    l'assertion « le fold part » passerait sur un port qui folderait TOUJOURS."""
    e = _entree()
    rendus = {}
    for adjacent in (False, True):
        st, att, tgt = _etat_boltstorm(adjacent)
        assert AT.is_melee_position(st, att, tgt) is adjacent, (
            "le montage doit vraiment produire les deux positions, sinon la mesure est VIDE")
        out = AT.execute_additional_targets_attacks(st, att, tgt, e, is_melee=False, weapon_range=2)
        rendus[adjacent] = out["primary_fold"]
    assert rendus[False] is not None, ("a DISTANCE le fold doit partir : %r" % (rendus,))
    assert rendus[True] is None, ("AU CONTACT le fold ne doit PAS partir : %r" % (rendus,))
    atk = rendus[False].get("attack") or {}
    assert int(atk.get("hits") or 0) >= 3, (
        "le fold porte `nrOfHits = 3` AVANT modificateurs de coups -- un compte inferieur veut dire "
        "que la cle de config n'est plus lue : %r" % (atk,))


def test_le_fold_est_le_MEME_artefact_que_celui_du_cleave():
    """`$$GetAdditionalDamageBehaviour` est appele par les DEUX volets -- un seul artefact natif,
    un seul port. Ce qui les distingue tient en DEUX champs, et ce test le figent : la CIBLE
    (`Target@0x60` contre le `Subject()` du `Foreach`) et `isOutsideAttack`."""
    e = _entree()
    fold = AT.primary_fold_tree(e, is_melee=False)
    cleave = _feuille_du_cleave(AT.cleave_tree(e, is_melee=False, weapon_range=2))
    communs = ("ability_id", "profile", "is_melee", "min_key", "max_key", "hits_key",
               "level_slot", "native_factory", "force_crit", "force_overkill",
               "amount_spread_pct", "skip_hits_modifiers", "ability_type", "multi")
    ecarts = [c for c in communs if getattr(fold, c) != getattr(cleave, c)]
    assert not ecarts, ("les deux volets doivent partager l'artefact : %r" % (ecarts,))
    assert type(fold.target_sel).__name__ != type(cleave.target_sel).__name__, (
        type(fold.target_sel).__name__, type(cleave.target_sel).__name__)
    assert fold.is_outside_attack is False and cleave.is_outside_attack is True
