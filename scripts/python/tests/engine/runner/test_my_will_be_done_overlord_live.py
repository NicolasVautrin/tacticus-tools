"""GARDE #354-r1 -- `MyWillBeDoneOverlordAbility` (passif `MyWillBeDoneOverlord`,
`TriggeredAbilityType` 0x614 = 1556, de `necroOverlord` << Anuphet >>), face COMBAT.

Artefacts natifs portes (RE ghidra + DESASSEMBLAGE, build `rnca9r7q6c` -- lecture in extenso dans
l'en-tete de `engine/runner/operations/triggers/loki/my_will_be_done_overlord.py`) :
  - `...MyWillBeDoneOverlordAbility$$CreateTrigger` =
        `On(0x12 TurnStart_EffectActivation) & AmountIsGreaterThanZero(<liste persistante>)`
      | `On(0x29 UnitFinishedTurnNormally) & get_OwnerIsActor`
  - `...$$CreateBehaviour` = `If(GetTargetFriend, <override + attaque libre + reset + memorisation>,
        AddDynamicStatModifierEffectToOwner(0x62d = 1581))`, et `ClearAllPersistentData` sur 0x12 ;
  - `...$$GetTargetFriend` = quatre groupes Necron/Hero chaines par `Otherwise`, tries par Attaque
    COURANTE DESCENDANTE, `First(1)`.

CE QUE LA GARDE PROUVE :
  (A) STRUCTURE de l'arbre-cible, offline : les QUATRE groupes dans le BON ordre, le tri DESCENDANT,
      les trois gates du predicat de base, et le fait que les quatre `Filter` de groupe partagent le
      MEME sous-arbre `pool` (le natif reprend le meme `pvVar4`) ;
  (B) STRUCTURE de l'arbre-behaviour, offline : le triptyque override / attaque-libre / retrait
      encadre bien l'attaque, la memorisation vient APRES, et les CINQ consommateurs du selecteur
      recoivent LE MEME OBJET (aucun `Cache` -- quirk natif, section 6 de l'en-tete du module) ;
  (C) SUBSTRAT persistant, offline : `AddToPersistentDataList` empile SANS dedup, le predicat
      `IsInPersistentDataList` mord, et `ClearAllPersistentData(abilityId)` n'emporte QUE les cles
      de cette ability ;
  (D) VECTEUR : `On(0x29 = UnitFinishedTurnNormally)` est bien celui du registre, et `FinishUnitTurnOperation.execute` ne
      l'emet QUE quand le flag TurnFinished est NOUVELLEMENT pose ET que la terminaison n'est pas
      forcee (les deux gates du decompile) ;
  (E) LIVE -- AGREEMENT : au `finish` du porteur, MEME victime et MEME delta de PV par unite entre
      le natif et le port (donc meme allie elu, meme cible, meme plafond d'attaque) ;
  (F) LIVE -- PREFERENCE DE GROUPE : l'allie Necron-Hero est elu alors qu'un allie Hero non-Necron
      adjacent a une Attaque BIEN PLUS GROSSE ;
  (G) LIVE -- PURGE : au tour SUIVANT le MEME allie re-attaque (sans le volet `On(0x12)` il serait
      memorise a vie) ;
  (I) LIVE -- MAGNITUDE du self-buff 1581 (#358) : le stat-mod ATTACK qu'il pose vaut
      `extraDmg[passiveAbilityLevel] x multiplier`, MEME montant live et port, sur trois canaux
      (`combatSnapshot`, `statModSources` avec `residual = 0`, gameconfig re-lu), plus DEUX regimes
      de scaling supplementaires, une GENERALISATION (montage M7 : la branche ELSE atteinte parce
      qu'un PREDICAT tombe, allie adjacent AVEC cible mais non-`Mechanical`) et la symetrie
      apply/revert. Le consommateur natif de cette
      magnitude n'est PAS dans la classe d'ability : c'est le corps GENERIQUE
      `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` de l'instance construite par
      `EffectsDatabase.<>c$$<InitializeEffects>b__14_574`.
  (H) CONTREFACTUELS : quatre mutations de MON PROPRE mecanisme doivent changer l'election. Sans
      elles, le vert des tests (E)/(F) ne prouverait pas que ces etages sont testes.
      ⚠ CHAQUE mutation exige le montage qui l'EXERCE -- mesure du 2026-07-31, ou trois des quatre
      echouaient sur M1 : `ascending` est inerte tant qu'un groupe ne contient qu'UNE unite,
      `notargets` tant que tous les allies ont une cible, `nomechanical` tant qu'un Necron est
      eligible (ils sont TOUS `Mechanical`). D'ou M5 (trois Necrons du groupe A, dont un melee pure
      hors de portee) et M6 (aucun Necron allie).

ASCII-only. Skip si pas de session live / montage non montable.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
import probe_354_my_will_be_done_overlord as MW                     # noqa: E402

SEED, BOARD, TURNS = "777", "MC1_67", 2


@pytest.fixture(scope="session")
def mwbd(rpc, live_session):
    """Monte le montage M1/M2/M3 UNE fois (destructif : il joue 2 activations du porteur)."""
    from rl_collect_batch import _resolve_session
    out = MW.measure(_resolve_session(), SEED, BOARD, TURNS, verbose=True)
    if out is None or not out["rows"]:
        pytest.skip("montage MyWillBeDoneOverlord non montable (board/pool/placement/DRAIN)")
    return out


@pytest.fixture(scope="session")
def mwbd_solo(rpc, live_session):
    """Montage M4 (branche ELSE) : aucun allie ADJACENT eligible, allie-tampon EXILE."""
    from rl_collect_batch import _resolve_session
    out = MW.measure_solo(_resolve_session(), SEED, BOARD, verbose=True)
    if out is None:
        pytest.skip("montage solo MyWillBeDoneOverlord non montable (DRAIN)")
    return out


@pytest.fixture(scope="session")
def mwbd_solo_scaling(rpc, live_session):
    """#358 -- DEUX cas discriminants de plus sur la MAGNITUDE du self-buff 1581, chacun sur son
    propre runner (monte puis dispose sequentiellement, jamais deux a la fois) :

      * `mult100`   : `AbilityVariablesMultiplierPercentage = 100` -> le multiplier de rarete ne
                      s'applique plus (`extraDmg` est pourtant dans `variablesAffectedByRarityBonus`) ;
      * `passive20` : `PassiveAbilityLevel = 20` alors que `ActiveAbilityLevel` reste a 50 -> SEUL le
                      niveau de PASSIF doit bouger la magnitude.

    Sans eux, le montant du cas nominal ne serait qu'UN scalaire qui colle."""
    from rl_collect_batch import _resolve_session
    sid = _resolve_session()
    out = {}
    for key, spec in (("mult100", "%s:AbilityVariablesMultiplierPercentage=100" % MW.CARRIER),
                      ("passive20", "%s:PassiveAbilityLevel=20" % MW.CARRIER)):
        r = MW.measure_solo(sid, SEED, BOARD, verbose=True, carrier_specs=[spec])
        if r is None:
            pytest.skip("montage solo #358 (%s) non montable (DRAIN)" % key)
        out[key] = r
    return out


@pytest.fixture(scope="session")
def mwbd_solo_ineligible(rpc, live_session):
    """Montage M7 (#358) -- GENERALISATION : la branche ELSE atteinte parce qu'un PREDICAT TOMBE
    (`astraCreed`, `Hero` NU, est ADJACENT au porteur et a une cible : seul `HasTrait(Mechanical)`
    l'ecarte), et non parce qu'il n'y a personne autour. Le self-buff doit y etre IDENTIQUE."""
    from rl_collect_batch import _resolve_session
    out = MW.measure_solo_ineligible(_resolve_session(), SEED, BOARD, verbose=True)
    if out is None:
        pytest.skip("montage M7 (allie adjacent ineligible) non montable (board/pool/DRAIN)")
    return out


@pytest.fixture(scope="session")
def mwbd_cf(rpc, live_session):
    """Montage M5 -- TROIS Necrons du groupe A : deux avec cible (Attaques differentes) et un
    MELEE PURE hors de portee. C'est le seul montage qui exerce `ascending` et `notargets`."""
    from rl_collect_batch import _resolve_session
    out = MW.measure_counterfactual(_resolve_session(), SEED, BOARD, verbose=True)
    if out is None:
        pytest.skip("montage M5 (contrefactuels) non montable (board/pool/placement/DRAIN)")
    return out


@pytest.fixture(scope="session")
def mwbd_nomech(rpc, live_session):
    """Montage M6 -- AUCUN allie Necron (groupe A vide) : un `Mechanical` et un `Hero` NU. C'est le
    seul montage qui exerce `nomechanical`."""
    from rl_collect_batch import _resolve_session
    out = MW.measure_nomech(_resolve_session(), SEED, BOARD, verbose=True)
    if out is None:
        pytest.skip("montage M6 (nomechanical) non montable (board/pool/placement/DRAIN)")
    return out


def _elected(cap, carrier_id, mutate):
    """L'allie elu par le port quand on neutralise l'etage `mutate` (None = l'ability reste inerte)."""
    _st, out = MW.offline_finish(cap, carrier_id, patch=MW._patched_tree(mutate))
    return out[0]["friend"] if out else None


# ------------------------------------------------------------------------------------------------
# (A) STRUCTURE de l'arbre-cible -- offline, aucun live requis.
# ------------------------------------------------------------------------------------------------
def test_mwbd_target_tree_groups_and_sort():
    """(A) `GetTargetFriend` : `First(SortByFormula(A.Otherwise(B).Otherwise(C).Otherwise(D),
    StatAmount(it, ATTACK, CURRENT), ascending = 0))`.

    Le sens du tri est le LITTERAL `xor r9d, r9d` du call-site (`ascending = 0` -> DESCENDANT) : un
    `ascending=True` eluerait l'allie le plus FAIBLE du groupe."""
    from engine.entities.formulas import StatAmount
    from engine.entities.selectors.geometry import Otherwise
    from engine.entities.selectors.units import Filter, First, SortByFormula
    from engine.entities.stats import StatPart, StatType
    from engine.runner.operations.triggers.loki.my_will_be_done_overlord import (
        my_will_be_done_target_friend)
    tree = my_will_be_done_target_friend()
    # ⚠ CETTE ASSERTION LISAIT `tree.index == 0` alors que sa propre etiquette disait
    # « First(chain, amount = 1) » : le noeud `First` du port prenait un INDICE, et AUCUNE
    # surcharge de `IdunBattleLogic.Entities.DSLSelectors$$First` ne le fait (#1032-r2). Elle lit
    # desormais l'`amount` NATIF -- et `ignoreForcedTargets`, le 4e argument, dont le litteral
    # `xor r9d, r9d` de ce call-site vaut 0 (donc les cibles FORCEES priment).
    assert isinstance(tree, First), "First(chain, amount = 1, ignoreForcedTargets = 0)"
    assert tree.amount == 1 and tree.ignore_forced_targets is False
    srt = tree.source
    assert isinstance(srt, SortByFormula)
    assert srt.ascending is False, "ascending = 0 (lu au desassemblage) -> tri DESCENDANT"
    assert isinstance(srt.formula, StatAmount)
    assert int(srt.formula.stat_type) == int(StatType.ATTACK) == 0
    assert int(srt.formula.variant) == int(StatPart.CURRENT) == 0
    # A.Otherwise(B).Otherwise(C).Otherwise(D) -- l'imbrication GAUCHE du decompile.
    o3 = srt.source
    assert isinstance(o3, Otherwise)
    o2 = o3.primary
    assert isinstance(o2, Otherwise)
    o1 = o2.primary
    assert isinstance(o1, Otherwise)
    groups = [o1.primary, o1.fallback, o2.fallback, o3.fallback]
    assert all(isinstance(g, Filter) for g in groups), "les QUATRE groupes sont des Filter(pool, ...)"
    # ... et les quatre partagent le MEME sous-arbre `pool` (le natif reprend le meme `pvVar4`).
    assert all(g.source is groups[0].source for g in groups)


def test_mwbd_target_tree_group_predicates():
    """(A bis) L'ORDRE de preference : (Necron & Hero) > (!Necron & Hero) > (Necron & !Hero) >
    (!Necron & !Hero). C'est la lecture des quatre `op_BitwiseAnd`/`op_LogicalNot` du desassemblage
    -- l'inverser changerait l'allie elu des que deux groupes sont peuples."""
    from engine.entities.triggers import HasFaction, HasTrait, Not, TriggerAnd
    from engine.runner.operations.triggers.loki.my_will_be_done_overlord import (
        HERO, NECRONS, my_will_be_done_target_friend)
    tree = my_will_be_done_target_friend()
    o3 = tree.source.source
    o2, o1 = o3.primary, o3.primary.primary
    groups = [o1.primary, o1.fallback, o2.fallback, o3.fallback]

    def shape(pred):
        """(necron_positif, hero_positif) du `TriggerAnd(<HasFaction|Not>, <HasTrait|Not>)`."""
        assert isinstance(pred, TriggerAnd)
        a, b = pred.a, pred.b
        na = isinstance(a, HasFaction)
        nb = isinstance(b, HasTrait)
        fa = a if na else a.a
        fb = b if nb else b.a
        assert isinstance(fa, HasFaction) and int(fa.faction) == NECRONS == 7
        assert isinstance(fb, HasTrait) and int(fb.trait) == HERO == 0x10
        return (na, nb)

    assert [shape(g.predicate) for g in groups] == [
        (True, True), (False, True), (True, False), (False, False)]
    assert all(isinstance(g.predicate.a, (HasFaction, Not)) for g in groups)


def test_mwbd_base_predicate_gates():
    """(A ter) Le predicat de base du `pool` : `HasTrait(it, 0x05 Mechanical)` &
    `AmountIsGreaterThanZero(Count(ValidNormalAttackTargets(it, Tiles(it))))` &
    `NOT IsInPersistentDataList(1556, Owner, dataKey, EntityId(it))`.

    ⚠ Le trait est `0x05 = Mechanical` NU -- pas le `IsMechanical` a trois traits que
    `ResurrectionOrb` emploie sur la MEME unite : recopier ce voisin aurait elargi le pool aux
    porteurs de `LivingMetal`/`Vehicle` sans trait 5."""
    from engine.entities.formulas import Count, EntityId
    from engine.entities.selectors.units import AdjacentFriends, Tiles, ValidNormalAttackTargets
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggers import (AmountIsGreaterThanZero, HasTrait,
                                          IsInPersistentDataList, Not, TriggerAnd)
    from engine.runner.operations.triggers.loki.my_will_be_done_overlord import (
        ABILITY_ID, MECHANICAL, MY_WILL_BE_DONE_OVERLORD, my_will_be_done_target_friend)
    pool = my_will_be_done_target_friend().source.source.primary.primary.primary.source
    assert isinstance(pool.source, AdjacentFriends), "pool = Filter(AdjacentFriends(Caster()), base)"
    base = pool.predicate
    assert isinstance(base, TriggerAnd)
    left, mem = base.a, base.b
    assert isinstance(left, TriggerAnd)
    mech, tgts = left.a, left.b
    assert isinstance(mech, HasTrait) and int(mech.trait) == MECHANICAL == int(UnitTrait.Mechanical)
    assert isinstance(tgts, AmountIsGreaterThanZero) and isinstance(tgts.a, Count)
    assert isinstance(tgts.a.selector, ValidNormalAttackTargets)
    assert isinstance(tgts.a.selector.unit_tile, Tiles), "ValidNormalAttackTargets(it, Tiles(it))"
    assert isinstance(mem, Not) and isinstance(mem.a, IsInPersistentDataList)
    assert mem.a.ability_or_effect == MY_WILL_BE_DONE_OVERLORD == 1556
    assert mem.a.data_key == ABILITY_ID
    assert isinstance(mem.a.value, EntityId)


# ------------------------------------------------------------------------------------------------
# (B) STRUCTURE de l'arbre-behaviour -- offline.
# ------------------------------------------------------------------------------------------------
def test_mwbd_behaviour_tree_shape():
    """(B) `If(target, ((override & attaque) & reset) & memorisation, selfBuff)` -- l'imbrication
    GAUCHE des trois `AbilityBehaviour.op_BitwiseAnd`, et les littéraux du decompile.

    Le point NON EVIDENT et VOULU : les CINQ consommateurs du selecteur (le `If` + les quatre
    feuilles) recoivent LE MEME OBJET, sans `Cache` -- le natif re-resout donc l'arbre a chaque
    etage, contre l'etat DEJA MUTE (cf. section 6 de l'en-tete du module). `ExemplarOfHate`, lui,
    enveloppe son selecteur d'attaquant dans un `Cache(..., 1)` explicite : l'ABSENCE ici est une
    lecture, pas un oubli."""
    from engine.entities.behaviours import Seq
    from engine.entities.stats import StatType
    from engine.runner.abilities.behaviours.effects import (
        AddDynamicStatModifierEffect, RemoveEffect
    )
    from engine.runner.abilities.behaviours.persistent_data import AddToPersistentDataList
    from engine.runner.abilities.behaviours.stats import AddStatOverrideEffect
    from engine.runner.abilities.behaviours.summon import PerformAIAttack
    from engine.runner.operations.triggers.loki.my_will_be_done_overlord import (
        EXTRA_DAMAGE_EFFECT, MY_WILL_BE_DONE_OVERLORD, TEMPORARY_STAT_OVERRIDE,
        my_will_be_done_attack_tree, my_will_be_done_target_friend)
    target = my_will_be_done_target_friend()
    node = my_will_be_done_attack_tree(target, 1234, 90, 3)
    assert node.condition is target, "la condition du `If` EST le selecteur GetTargetFriend"
    then, els = node.then, node.otherwise
    assert isinstance(then, Seq) and isinstance(then.left, Seq) and isinstance(then.left.left, Seq)
    override, free_attack = then.left.left.left, then.left.left.right
    clear, remember = then.left.right, then.right
    assert isinstance(override, AddStatOverrideEffect)
    assert override.effect_type == TEMPORARY_STAT_OVERRIDE == 0x510
    assert override.stat_type == int(StatType.ATTACK) == 0
    assert isinstance(free_attack, PerformAIAttack)
    assert free_attack.allow_move_action is False and free_attack.move_amount == 0, \
        "PerformAIAttackFromCurrentPosition : overrideMovement = <DSLFormulas+0x18 = Direct(0)>"
    assert isinstance(clear, RemoveEffect) and clear.effect_type == TEMPORARY_STAT_OVERRIDE
    assert isinstance(remember, AddToPersistentDataList)
    assert remember.ability_or_effect == MY_WILL_BE_DONE_OVERLORD
    assert isinstance(els, AddDynamicStatModifierEffect)
    assert els.effect_type == EXTRA_DAMAGE_EFFECT == 0x62d
    assert els.stat_type == int(StatType.ATTACK)
    assert els.duration_turns == 3 and els.duration_rounds is None, \
        "turns = Sum(TurnsFromRounds(1), Direct(1)) -- deja en TOURS"
    # LE MEME OBJET dans les cinq consommateurs (aucun `Cache`).
    assert override.unit_sel is target and free_attack.tile_selector is target
    assert clear.target_sel is target and remember.value.ref is target


# ------------------------------------------------------------------------------------------------
# (C) SUBSTRAT persistant -- offline.
# ------------------------------------------------------------------------------------------------
def _state_with(owner_id=1):
    from engine.runner.state import State
    st = State()
    e = st.add_entity()
    return st, e


def test_persistent_data_list_append_contains_clear():
    """(C) Le sac LISTE, mirror des trois primitives natives :
      * `AddToPersistentDataListBehaviour$$Execute` -> `list.Add(value)` INCONDITIONNEL (le natif ne
        deduplique PAS -- c'est le predicat en amont qui evite le doublon) ;
      * `IsInPersistentDataListTrigger$$ShouldTrigger` -> `(list ?? new List()).Contains(value)` ;
      * `PersistentDataComponent$$ClearAllPersistentData(abilityId)` = `Dictionary.Remove(abilityId)`
        -> emporte TOUTES les dataKeys de CETTE ability, et RIEN des autres."""
    from engine.runner.components import PersistentDataComponent, persistent_data_list
    st, e = _state_with()
    c = PersistentDataComponent()
    e.add_component(c)
    k_mine, k_other = (1556, "MyWillBeDoneOverlord"), (1004, "RelentlessMarch")
    assert persistent_data_list(e, k_mine) == [], "cle absente -> liste VIDE (le natif fait `?? new`)"
    c.persist_data_list(k_mine, [7])
    c.persist_data_list(k_other, [9])
    c.persist_data(("scalaire", "x"), 1)
    assert persistent_data_list(e, k_mine) == [7]
    lst = list(c.try_get_persist_data_list(k_mine))
    lst.append(7)                                     # `List.Add` : PAS de dedup
    c.persist_data_list(k_mine, lst)
    assert persistent_data_list(e, k_mine) == [7, 7]
    c.clear_all_persistent_data(1556)
    assert persistent_data_list(e, k_mine) == [], "Remove(abilityId) emporte les cles de 1556"
    assert persistent_data_list(e, k_other) == [9], "... et RIEN des autres abilities"
    assert c.try_get_persist_data_list(("scalaire", "x")) is None, \
        "un scalaire n'est pas une liste (les deux familles coexistent dans le meme dict)"
    c.clear_all_persistent_data()                     # overload SANS argument (resurrection)
    assert c.data == {}


# ------------------------------------------------------------------------------------------------
# (D) VECTEUR -- offline.
# ------------------------------------------------------------------------------------------------
def test_mwbd_registered_on_unit_finished_turn_normally():
    """(D) Les DEUX branches du `CreateTrigger` sont au registre `ABILITY_TRIGGERS`, sur les DEUX
    events LUS (`0x29` pour l'attaque, `0x12` pour la purge)."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.my_will_be_done_overlord import (
        MyWillBeDoneOverlordAttackAbility, MyWillBeDoneOverlordClearAbility)
    entries = ABILITY_TRIGGERS["MyWillBeDoneOverlord"]
    assert entries == [MyWillBeDoneOverlordAttackAbility, MyWillBeDoneOverlordClearAbility]
    assert MyWillBeDoneOverlordAttackAbility.event_id == int(
        EventTriggerType.UnitFinishedTurnNormally) == 41
    assert MyWillBeDoneOverlordClearAbility.event_id == int(
        EventTriggerType.TurnStart_EffectActivation) == 18
    assert MyWillBeDoneOverlordAttackAbility.TRIGGERED_ABILITY_ID == 1556


def test_finish_unit_turn_emits_only_when_newly_finished_and_not_forced():
    """(D bis) Les DEUX gates natifs du `publish On(0x29 = UnitFinishedTurnNormally)` :

        if (flags.Add(0x03 = TurnFinished)) { publish On(0x28 = UnitFinishedTurn) ;
                                              if (!isTerminated) publish On(0x29 = UnitFinishedTurnNormally) }

    -> un `finish` FORCE (le `FinishUnitTurn(spawned, isTerminated: true)` des summons, #291) et un
    second `finish` sur une unite deja close n'emettent RIEN. Le test appelle l'Operation sur un etat
    NU (aucun trigger enregistre) : ce qu'il verifie est la PRESENCE de la cle, donc l'emission."""
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    st, e = _state_with()
    e.add_component(UnitFlagsComponent())
    out = FinishUnitTurnOperation.execute(st, e.id, forced=False)
    assert out["newly_finished"] is True and "finished_normally_triggers" in out
    again = FinishUnitTurnOperation.execute(st, e.id, forced=False)
    assert again["newly_finished"] is False and "finished_normally_triggers" not in again, \
        "le flag TurnFinished etait deja pose -> le natif ne republie pas"
    st2, e2 = _state_with()
    e2.add_component(UnitFlagsComponent())
    forced = FinishUnitTurnOperation.execute(st2, e2.id, forced=True)
    assert forced["newly_finished"] is True and "finished_normally_triggers" not in forced, \
        "isTerminated = true -> On(0x28 = UnitFinishedTurn) seul, JAMAIS On(0x29 = UnitFinishedTurnNormally)"


# ------------------------------------------------------------------------------------------------
# (E)-(H) -- confrontation LIVE.
# ------------------------------------------------------------------------------------------------
def test_mwbd_agreement_damage_deltas(mwbd):
    """(E) A chaque activation du porteur : MEME delta de PV par unite live et port. C'est
    l'assertion qui couvre les TROIS termes de la question binaire -- meme allie elu (une autre
    unite frapperait une autre victime), meme cible, meme plafond d'attaque (`min(maxDmg[lvl],
    round(Attaque x dmgPct%))` : un cap ou un pourcentage faux donnerait un autre degat)."""
    vis = mwbd["vis_by_id"]
    for row in mwbd["rows"]:
        for uid in row["hp_before"]:
            assert row["d_live"].get(uid, 0) == row["d_port"].get(uid, 0), (
                "activation #%d : %s live=%d port=%d"
                % (row["k"], vis.get(uid), row["d_live"].get(uid, 0), row["d_port"].get(uid, 0)))


def test_mwbd_group_preference_beats_attack_sort(mwbd):
    """(F) LE DISCRIMINANT : `necroWarden` (Necron + Hero, groupe A) est elu alors qu'`admecDominus`
    (Hero non-Necron, groupe B) est adjacent, eligible, et porte une Attaque BIEN PLUS GROSSE. Un
    tri global par Attaque (sans la chaine `Otherwise`) eluerait le Dominus.

    L'identite de l'attaquant est lue par la VICTIME : le montage donne a chaque allie SA propre
    cible adjacente, hors de portee de l'autre (`setup_positions` REFUSE toute autre geometrie)."""
    vis, ids = mwbd["vis_by_id"], mwbd["ids"]
    row = mwbd["rows"][0]
    hurt = [uid for uid, d in row["d_live"].items() if d < 0]
    assert hurt, "aucune victime live : le trigger natif n'a pas fire (montage a revoir)"
    assert [vis[u] for u in hurt] == [MW.ENEMY_A], (
        "la victime doit etre la cible du groupe A (%s), pas %s"
        % (MW.ENEMY_A, [vis[u] for u in hurt]))
    assert row["port_out"], "le port doit avoir fire aussi"
    assert row["port_out"][0]["friend"] == ids[MW.ALLY_A], (
        "l'allie elu par le port doit etre %s, pas %s"
        % (MW.ALLY_A, vis.get(row["port_out"][0]["friend"])))


def test_mwbd_persistent_list_is_purged_between_turns(mwbd):
    """(G) PURGE : a l'activation SUIVANTE, le MEME allie re-attaque. Sans le volet
    `On(0x12) -> ClearAllPersistentData`, il resterait memorise et un AUTRE allie (ou personne)
    agirait -- c'est la seule confrontation LIVE possible de la purge, puisqu'il y a toujours au
    moins un turn-start entre deux activations du porteur."""
    if len(mwbd["rows"]) < 2:
        pytest.skip("il faut >= 2 activations du porteur pour observer la purge")
    ids, vis = mwbd["ids"], mwbd["vis_by_id"]
    for row in mwbd["rows"]:
        hurt = [uid for uid, d in row["d_live"].items() if d < 0]
        assert [vis[u] for u in hurt] == [MW.ENEMY_A], (
            "activation #%d : victime %s (le meme allie doit rejouer apres la purge)"
            % (row["k"], [vis[u] for u in hurt]))
        assert row["port_out"] and row["port_out"][0]["friend"] == ids[MW.ALLY_A]


def test_mwbd_counterfactual_nogroups(mwbd):
    """(H.1) `nogroups` -- supprimer la chaine `A.Otherwise(B).Otherwise(C).Otherwise(D)` rabat le
    choix sur un tri GLOBAL par Attaque. Sur M1 (`necroWarden` 400 groupe A vs `admecDominus` 3000
    groupe B) cela elit le Dominus : c'est le pendant exact du discriminant (F)."""
    diverged = False
    for row in mwbd["rows"]:
        want = row["port_out"][0]["friend"] if row["port_out"] else None
        if _elected(row["cap"], mwbd["ids"][MW.CARRIER], "nogroups") != want:
            diverged = True
            break
    assert diverged, "la chaine Otherwise n'est pas exercee par M1"


@pytest.mark.parametrize("mutate", ["ascending", "notargets"])
def test_mwbd_counterfactuals_m5(mwbd_cf, mutate):
    """(H.2) Les DEUX etages que M1 N'EXERCE PAS, sur le montage M5 taille pour eux :

      * `ascending` -- M1 n'oppose qu'UNE unite par groupe, donc le sens du tri y est INERTE. M5 met
        `necroDestroyer` (400) et `necroWarden` (3000) dans le MEME groupe A : le tri DESCENDANT elit
        le Warden, l'ascendant elirait le Destroyer.
      * `notargets` -- les deux allies de M1 ont une cible, donc le gate y est INERTE. M5 ajoute
        `necroSpyder` (Attaque MAXIMALE, MELEE PURE) hors de portee : le gate l'ecarte ; sans lui il
        est elu et l'ability devient INERTE (il ne peut pas frapper).

    MESURE 2026-07-31 : ces deux mutations echouaient sur M1 -- a juste titre. Un contrefactuel qui
    ne bouge pas dit que l'etage n'est pas teste, pas que le port est bon."""
    base = mwbd_cf["port_out"][0]["friend"] if mwbd_cf["port_out"] else None
    got = _elected(mwbd_cf["cap"], mwbd_cf["ids"][MW.CARRIER], mutate)
    assert got != base, (
        "la mutation '%s' n'a change AUCUNE election (base=%s) : cet etage n'est pas exerce"
        % (mutate, mwbd_cf["vis_by_id"].get(base)))


def test_mwbd_counterfactual_nomechanical(mwbd_nomech):
    """(H.3) `nomechanical` sur M6. Il n'existe AUCUN Necron non-`Mechanical` (recon gameconfig
    2026-07-31) : des qu'un Necron est eligible, le groupe A gagne et retirer le gate ne deplace
    rien -- ce pourquoi M1 et M5 laissent cette mutation inerte. M6 vide donc le groupe A :
    `admecDominus` (`Mechanical`, 400) est le seul elu possible, alors qu'`astraCreed` (`Hero` NU,
    3000) le devancerait au tri sans le gate."""
    base = mwbd_nomech["port_out"][0]["friend"] if mwbd_nomech["port_out"] else None
    got = _elected(mwbd_nomech["cap"], mwbd_nomech["ids"][MW.CARRIER], "nomechanical")
    assert base == mwbd_nomech["ids"][MW.ALLY_B], (
        "l'elu de base doit etre le seul Mechanical (%s), pas %s"
        % (MW.ALLY_B, mwbd_nomech["vis_by_id"].get(base)))
    assert got == mwbd_nomech["ids"][MW.ALLY_NM], (
        "sans le gate Mechanical, %s (Attaque plus grosse) doit etre elu, pas %s"
        % (MW.ALLY_NM, mwbd_nomech["vis_by_id"].get(got)))


def test_mwbd_else_branch_self_buff(mwbd_solo):
    """(E bis) BRANCHE ELSE : aucun allie ADJACENT eligible -> le porteur n'attaque personne, et
    l'effet 1581 `MyWillBeDoneOverlord_ExtraDamage` apparait SUR LUI -- avec la MEME DUREE live et
    port.

    ⚠ La duree est comparee en VALEUR, pas seulement par les porteurs : `AddDynamicStatModifier
    EffectToOwner(0x62d, ATTACK, turns = Sum(TurnsFromRounds(1), <DSLFormulas+0x20 = Direct(1)>))`
    est le SEUL etage de cette branche qui produise un observable, et un `set(...)` sur les cles le
    laissait passer en silence. MESURE du 2026-07-31 : sur l'ancien montage (porteur SEUL de son
    camp) le live rendait `remaining = 2` contre `3` au port -- non pas parce que la duree etait
    fausse, mais parce que le `finish` du porteur faisait BASCULER le tour et qu'un TICK s'appliquait
    avant l'observation. Le montage exile donc un allie-tampon (`setup_solo_positions`) pour que le
    tour NE bascule PAS, et les deux cotes rendent alors 3."""
    assert not any(d for d in mwbd_solo["d_live"].values()), \
        "aucun allie eligible -> aucune attaque"
    assert mwbd_solo["port_out"] and mwbd_solo["port_out"][0]["self_buff"] is True
    assert mwbd_solo["turn_before"] == mwbd_solo["turn_after"], (
        "le tour a BASCULE (%s -> %s) : un tick a decremente la duree et la comparaison ne porterait "
        "plus sur le meme instant" % (mwbd_solo["turn_before"], mwbd_solo["turn_after"]))
    assert mwbd_solo["live_eff"] == mwbd_solo["port_eff"], (
        "1581 (porteur ET duree) live=%s port=%s" % (mwbd_solo["live_eff"], mwbd_solo["port_eff"]))
    assert set(mwbd_solo["live_eff"].values()) == {3}, (
        "turns = Sum(TurnsFromRounds(1) = 2, Direct(1)) = 3 en duel ; observe %s"
        % mwbd_solo["live_eff"])


# ------------------------------------------------------------------------------------------------
# (I) #358 -- LA MAGNITUDE du self-buff 1581. Consommateur natif : le corps GENERIQUE
#     `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount`
#     de l'instance construite par `EffectsDatabase.<>c$$<InitializeEffects>b__14_574`
#     (`AbilityType(1556)`, variableType 8 = extraDmg, isNegative = 0). Il n'est PAS dans la classe
#     d'ability -- c'est pourquoi #354-r1 ne l'avait pas trouve et avait, a raison, refuse d'inventer.
# ------------------------------------------------------------------------------------------------
EXTRA_DMG_ABILITY = "MyWillBeDoneOverlord"


def _extra_dmg(level, mult):
    from engine.entities.effects.magnitude import ability_var
    return ability_var(EXTRA_DMG_ABILITY, "extraDmg", level, multiplier_pct=mult)


def test_mwbd_extra_damage_effect_is_registered():
    """(I a) OFFLINE -- l'`EffectType` 1581 a bien une CLASSE cote port, keyee par le nom de membre
    d'enum que la pose (et `decisionView`) publie. Sans cette entree, l'effet retombe sur `BaseEffect`
    nu : present mais SANS stat-mod -- exactement l'etat que #354-r1 avait laisse en residu."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.my_will_be_done_overlord import (
        MyWillBeDoneOverlordExtraDamageEffect
    )
    assert EFFECT_CLASSES["MyWillBeDoneOverlord_ExtraDamage"] is \
        MyWillBeDoneOverlordExtraDamageEffect


def test_mwbd_extra_damage_magnitude_live(mwbd_solo):
    """(I b) LIVE -- le self-buff pose bien un stat-mod ATTAQUE, du MEME montant que le port, et ce
    montant EST `ConfigVar(extraDmg)` re-lu du gameconfig (jamais fitte).

    TROIS canaux independants : la stat ATTAQUE courante (`combatSnapshot`, `GetStat(0, Current)`),
    sa decomposition PAR SOURCE (`statModSources`, la `ValueModification` que
    `AStatModifierEffect$$ApplyModification` attribue a `Entity(effect)`), et le gameconfig.
    `residual == 0` verifie qu'AUCUNE autre source ne contribue -- sans quoi l'egalite des deltas
    pourrait etre une compensation."""
    exp = mwbd_solo["expected_extra_dmg"]
    assert exp and exp > 0, "extraDmg introuvable au gameconfig -> le montage ne mesure rien"
    assert mwbd_solo["sm_before"] == {}, (
        "l'ATTAQUE du porteur portait DEJA une modification avant le finish (%s) : le delta ne serait "
        "pas imputable au seul 1581" % mwbd_solo["sm_before"])
    assert mwbd_solo["d_atk_live"] == mwbd_solo["d_atk_port"] == exp, (
        "d(ATTACK) live=%s port=%s attendu extraDmg=%s"
        % (mwbd_solo["d_atk_live"], mwbd_solo["d_atk_port"], exp))
    mods = mwbd_solo["sm_after"]
    assert int(mods.get("total") or 0) == exp and int(mods.get("residual") or 0) == 0, (
        "statModSources(attack) = %s (attendu total=%s, residual=0)" % (mods, exp))
    by = [s for s in (mods.get("bySource") or []) if int(s.get("amount") or 0)]
    assert len(by) == 1, "une SEULE source doit contribuer, vu %s" % by
    assert by[0]["self"] is False and by[0]["sourceIsUnit"] is False, (
        "la source du ChangeStat est l'ENTITE-EFFET (`Entity(effect)`), pas l'unite : %s" % by[0])


def test_mwbd_extra_damage_revert_symmetry(mwbd_solo):
    """(I c) La contribution SORT quand l'instance part -- mirror
    `AStatModifierEffect$$RevertModification` (`ChangeStat`, part 6 = ResetModification), joue cote
    port par `revert_stat_mods_of_removed_effects`, dont le discriminant est `reverted_stats()`.
    Un `reverted_stats()` qui nommerait une AUTRE stat laisserait le buff a vie, en silence."""
    assert mwbd_solo["atk_port_reverted"] == mwbd_solo["atk_before"], (
        "apres retrait de 1581 l'ATTAQUE doit revenir a %s, observe %s"
        % (mwbd_solo["atk_before"], mwbd_solo["atk_port_reverted"]))


def test_mwbd_extra_damage_scales_with_rarity_and_passive_level(mwbd_solo, mwbd_solo_scaling):
    """(I d) DEUX cas discriminants de plus, live-vs-port, pour que le montant du cas nominal ne
    puisse pas etre un scalaire qui colle :

      * multiplier 100 -> la magnitude DESCEND (donc `extraDmg` est bien scale par la rarete, ce que
        `variablesAffectedByRarityBonus` annonce et que `ability_var` gate) ;
      * `PassiveAbilityLevel = 20` avec `ActiveAbilityLevel` INCHANGE a 50 -> la magnitude descend
        AUSSI : le `ConfigVar` s'indexe sur le niveau de PASSIF. Si le port lisait le niveau ACTIF il
        rendrait ici la valeur du cas nominal.

    Les trois montants doivent etre DEUX A DEUX DISTINCTS, sinon aucun etage n'est departage."""
    cases = {"nominal": mwbd_solo,
             "mult100": mwbd_solo_scaling["mult100"],
             "passive20": mwbd_solo_scaling["passive20"]}
    for key, out in cases.items():
        exp = out["expected_extra_dmg"]
        assert out["d_atk_live"] == out["d_atk_port"] == exp, (
            "%s : d(ATTACK) live=%s port=%s attendu=%s"
            % (key, out["d_atk_live"], out["d_atk_port"], exp))
    got = {k: out["d_atk_live"] for k, out in cases.items()}
    assert len(set(got.values())) == 3, (
        "les trois regimes doivent rendre trois montants DISTINCTS, vu %s" % got)
    assert got["mult100"] < got["nominal"] and got["passive20"] < got["mult100"], (
        "ordre attendu passive20 < mult100 < nominal, vu %s" % got)


def test_mwbd_extra_damage_on_ineligible_neighbour(mwbd_solo_ineligible, mwbd_solo):
    """(I f) GENERALISATION -- le self-buff ne depend pas du montage qui l'a produit.

    Ici la branche ELSE est prise parce qu'un PREDICAT de `GetTargetFriend` tombe : l'unique allie
    (`astraCreed`, `Hero` NU) est bien ADJACENT au porteur (donc dans `AdjacentFriends(Caster())`) et
    a bien une cible d'attaque normale a portee (donc
    `AmountIsGreaterThanZero(ValidNormalAttackTargets)` est VRAI) -- seul `HasTrait(it, Mechanical)`
    l'ecarte. C'est une VOIE D'ENTREE differente de M4 (ou le pool etait vide faute de voisin), et le
    buff doit y etre bit-identique. Les deux distances sont assertees : sans elles, ce montage
    retomberait silencieusement sur M4."""
    out = mwbd_solo_ineligible
    assert out["dist_carrier_ally"] == 1, (
        "l'allie doit etre ADJACENT au porteur (sinon on retombe sur M4), d=%s"
        % out["dist_carrier_ally"])
    assert out["dist_ally_enemy"] == 1, (
        "l'allie doit avoir une cible d'attaque normale a portee, d=%s" % out["dist_ally_enemy"])
    assert not any(d for d in out["d_live"].values()), \
        "aucun allie ELIGIBLE -> aucune attaque libre"
    assert out["port_out"] and out["port_out"][0]["self_buff"] is True
    assert out["turn_before"] == out["turn_after"], "le tour ne doit pas basculer"
    assert out["live_eff"] == out["port_eff"] and set(out["live_eff"].values()) == {3}
    exp = out["expected_extra_dmg"]
    assert out["d_atk_live"] == out["d_atk_port"] == exp, (
        "M7 : d(ATTACK) live=%s port=%s attendu=%s" % (out["d_atk_live"], out["d_atk_port"], exp))
    assert exp == mwbd_solo["expected_extra_dmg"], (
        "meme porteur, meme niveau -> meme magnitude que M4 (%s vs %s)"
        % (exp, mwbd_solo["expected_extra_dmg"]))


def test_mwbd_extra_damage_counterfactuals_offline():
    """(I e) CONTREFACTUELS sur MON PROPRE etage de magnitude : chaque mutation d'un littéral LU au
    decompile doit DIVERGER du montant porte. Sans eux, le vert de (I b)/(I d) ne prouverait pas que
    ces littéraux sont ceux qui pilotent le calcul.

      * `variableType`  : 8 = extraDmg -- la lambda passe `mov r8d,8` ; `maxDmg` (13) est la variable
        VOISINE que la MEME ability consomme dans sa branche THEN, donc la confusion la plus probable ;
      * niveau           : PASSIF (l'ability 1556 est un `TriggeredAbilityType`), pas ACTIF ;
      * multiplier       : applique (variable listee dans `variablesAffectedByRarityBonus`) ;
      * `isNegative = 0` : le montant est POSITIF (un `1` en ferait un malus, cf.
        `AugmentedAssault_ReduceArmor`, qui partage la MEME classe native)."""
    from engine.entities.stats import StatType
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.magnitude import ability_var
    cls = EFFECT_CLASSES["MyWillBeDoneOverlord_ExtraDamage"]
    eff = cls(effect_type=1581, name="MyWillBeDoneOverlord_ExtraDamage")
    eff.ability_level, eff.active_ability_level = 20, 50      # passif 20 / actif 50 : ils DIFFERENT
    eff.ability_variables_multiplier = 180
    got = eff.applied_stat_mods(None)
    assert len(got) == 1 and int(got[0][0]) == int(StatType.ATTACK), (
        "le stat-mod porte sur ATTACK (statType 0 du behaviour), vu %s" % (got,))
    amount = int(got[0][1])
    assert amount == _extra_dmg(20, 180) > 0, "extraDmg[passif] x mult, signe POSITIF"
    for label, other in (
            ("maxDmg au lieu d'extraDmg",
             ability_var(EXTRA_DMG_ABILITY, "maxDmg", 20, multiplier_pct=180)),
            ("niveau ACTIF au lieu du PASSIF", _extra_dmg(50, 180)),
            ("multiplier de rarete non applique", _extra_dmg(20, 100))):
        assert other != amount, "mutation inerte (%s) : cet etage n'est pas teste" % label
