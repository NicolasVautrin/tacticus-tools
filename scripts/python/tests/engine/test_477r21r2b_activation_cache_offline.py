"""#477-r21-r2 volet B -- cliquet OFFLINE du cache d'activation.

Il garde ce que le live NE PEUT PAS garder. Mesure a l'appui (`probe_477r21r2b_activation_cache.py`
sur `MC1_67` 2v2 et `C1_02` 5v5) : les priorites du corpus sont UNIFORMES, donc `AddSorted`
y degenere exactement en `append`, donc les deux mutants `comparaison_inversee` et `append_nu`
sont INERTES en live -- le probe les declare `a_morde=false` au lieu de les compter verts. Le TRI
lui-meme n'est donc exerce QU'ICI, avec des priorites HETEROGENES.

Sont gardes, dans l'ordre du decompile :
  1. `SortedTriggered$$CompareTo`      -- dont le `other == null` qui rend 1
  2. `AbilityAndEffectCache$$AddSortedu003Cobjectu003E` -- decroissant, STABLE, degenere en append
  3. le pre-peuplement du ctor          -- `get_Item` TOTAL sur les 76 valeurs de l'enum
  4. `$$GetActiveTriggeredAbilitiesAndEffects` -- la COPIE (`ListPool.GetDisposable`)
  5. l'appariement offset -> getter     -- `+0x38` = refreshing, `+0x40` = withBonuses
  6. `$$AddEntity`                      -- l'aiguillage effet / ability
  7. `$$AddAbility`                     -- la garde `checkIfAlreadyExist` a TROIS criteres
  8. `$$AddEffect`                      -- la garde d'unicite de la 1re boucle, ABSENTE de la 2e
  9. `$$RemoveEntity`                   -- FindIndex+RemoveAt (effet) vs RemoveAll (unite)
 10. `$$RemoveTriggered`                -- ne touche QUE `+0x20`
 11. le mirror `AbilityPriority`

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from engine.dsl.event_trigger_type import EventTriggerType            # noqa: E402
from engine.entities.ability_priority import AbilityPriority          # noqa: E402
from engine.runner.caches import (AbilityAndEffectCache, SortedEffect,  # noqa: E402
                                  SortedTriggered, SortedTriggeredAbility, add_sorted)

TRIGGER = int(EventTriggerType.MatchStart)
AUTRE = int(EventTriggerType.MatchInit)


# ---------------------------------------------------------------- doublures minimales
class _Ability:
    def __init__(self, triggers, priority=AbilityPriority.Normal):
        self.triggers = {int(t) for t in triggers}
        self.priority = int(priority)


class _Effect:
    def __init__(self, ability_triggers=(), own_triggers=(), refreshes=False,
                 has_bonuses=False, priority=AbilityPriority.Normal):
        self.ability_triggers = [int(t) for t in ability_triggers]
        self.own_triggers = [int(t) for t in own_triggers]
        self.refreshes = refreshes
        self.has_bonuses = has_bonuses
        self.priority = int(priority)


class _EffectComponent:
    def __init__(self, effect_type=1, has_turns=False):
        self.effect_type = effect_type
        self.has_turns = has_turns


class _ConfigId:
    def __init__(self, key, order):
        self.key = key
        self.order = int(order)


class _Comp:
    def __init__(self, config_ids):
        self.config_ids = list(config_ids)


class _Unite:
    def __init__(self, eid, config_ids=()):
        self.eid = eid
        self.is_unit = True
        self.triggered_ability_component = _Comp(config_ids)
        self.effect_component = None

    def __repr__(self):
        return "u%s" % self.eid


class _EntiteEffet:
    def __init__(self, eid, effect_component=None):
        self.eid = eid
        self.is_unit = False
        self.triggered_ability_component = None
        self.effect_component = effect_component or _EffectComponent()

    def __repr__(self):
        return "fx%s" % self.eid


def _cache(catalogue=None, effets=None):
    return AbilityAndEffectCache(
        effects_database=lambda t: (effets or {}).get(t),
        abilities_database=lambda c: (catalogue or {}).get(c.key, []))


def _sorted(priority, marque):
    """Un `SortedTriggered` nu dont la priorite est FIXEE -- ce que le live ne sait pas faire."""
    class _S(SortedTriggered):
        __slots__ = ("marque",)

        def __init__(self, m):
            self.marque = m

        def get_priority(self):
            return int(priority)

        def __repr__(self):
            return str(self.marque)
    return _S(marque)


# ---------------------------------------------------------------- 1. CompareTo
def test_compare_to_ordre_et_null():
    """`SortedTriggered$$CompareTo` : `this.Priority.CompareTo(other.Priority)`, et `null` -> 1."""
    haut = _sorted(AbilityPriority.First, "h")
    bas = _sorted(AbilityPriority.Last, "b")
    egal = _sorted(AbilityPriority.First, "h2")
    assert haut.compare_to(bas) == 1
    assert bas.compare_to(haut) == -1
    assert haut.compare_to(egal) == 0
    # `other == null` rend 1, PAS 0 : lu au decompile (`if (other == 0) return 1`).
    assert haut.compare_to(None) == 1
    assert bas.compare_to(None) == 1


def test_priorite_par_defaut_est_normal():
    """La base rend `AbilityPriority.Normal` -- le membre NOMME, pas le litteral 0."""
    class _Nu(SortedTriggered):
        __slots__ = ()
    assert _Nu().get_priority() == int(AbilityPriority.Normal)


# ---------------------------------------------------------------- 2. AddSorted
def test_add_sorted_decroissant_et_stable():
    """`AddSorted` : decroissant en priorite, STABLE a priorite egale (on passe APRES les egaux).

    C'EST LE TEST QUE LE LIVE NE PEUT PAS FAIRE : sur les deux boards mesures, toutes les
    priorites valent `Normal`, donc `AddSorted` y est indiscernable d'un `append`."""
    lst = []
    for p, m in ((AbilityPriority.Normal, "n1"), (AbilityPriority.Last, "z1"),
                 (AbilityPriority.First, "a1"), (AbilityPriority.Normal, "n2"),
                 (AbilityPriority.First, "a2"), (AbilityPriority.Early, "e1")):
        add_sorted(_sorted(p, m), lst)
    assert [s.marque for s in lst] == ["a1", "a2", "e1", "n1", "n2", "z1"]


def test_add_sorted_degenere_en_append_a_priorites_egales():
    """A priorites EGALES, `FindIndex` ne trouve rien et `idx = Count` -> append.

    C'est ce qui rend les mutants `append_nu` / `comparaison_inversee` INERTES en live, et
    pourquoi le probe publie `a_morde` separement du verdict."""
    lst = []
    for i in range(5):
        add_sorted(_sorted(AbilityPriority.Normal, i), lst)
    assert [s.marque for s in lst] == [0, 1, 2, 3, 4]


def test_add_sorted_insere_en_tete_quand_la_priorite_domine():
    lst = []
    add_sorted(_sorted(AbilityPriority.Normal, "n"), lst)
    add_sorted(_sorted(AbilityPriority.First, "a"), lst)
    assert [s.marque for s in lst] == ["a", "n"]


# ---------------------------------------------------------------- 3-4. le dictionnaire
def test_dictionnaires_pre_peuples_sur_toutes_les_valeurs_de_l_enum():
    """Le ctor fait `Enum.GetValues(typeof(EventTriggerType))` : `get_Item` est TOTAL.

    Un dictionnaire paresseux rendrait `KeyError` la ou le natif rend une liste VIDE -- et le
    mutant `sans_pre_peuplement` du probe mesure exactement cet ecart."""
    c = _cache()
    valeurs = {int(t) for t in EventTriggerType}
    assert valeurs, "le mirror `EventTriggerType` est VIDE -- ce test ne mesurerait rien"
    assert set(c.active) == valeurs
    assert set(c.simulated) == valeurs
    for t in valeurs:
        assert c.get_active_triggered_abilities_and_effects(t) == []


def test_le_getteur_rend_une_copie():
    """`ListPool<T>.GetDisposable(list)` -- muter le rendu ne doit pas muter le cache.

    Ce n'est pas cosmetique : le natif parcourt cette copie dans `ExecuteInternal`, donc un effet
    ajoute PENDANT l'evaluation n'entre pas dans CE parcours."""
    c = _cache()
    rendu = c.get_active_triggered_abilities_and_effects(TRIGGER)
    rendu.append(_sorted(AbilityPriority.Normal, "intrus"))
    assert c.get_active_triggered_abilities_and_effects(TRIGGER) == []
    assert c.get_effects() == [] and c.get_refreshing_effects() == []


# ---------------------------------------------------------------- 5. offset -> getter
def test_appariement_offset_vers_getter():
    """`+0x38` = `GetRefreshingEffects`, `+0x40` = `GetEffectsWithBonuses` -- lu UN PAR UN.

    L'ordre dans lequel `AddEffect` les alimente est l'INVERSE : deduire l'un de l'autre
    intervertit deux listes que plus rien ne distingue ensuite."""
    fx = _EntiteEffet(9, _EffectComponent(effect_type=7, has_turns=True))
    c = _cache(effets={7: _Effect(has_bonuses=False)})
    c.add_effect(fx, fx.effect_component)
    assert [s.entity for s in c.get_refreshing_effects()] == [fx]     # via `has_turns`
    assert c.get_effects_with_bonuses() == []
    assert [s.entity for s in c.get_effects()] == [fx]

    fx2 = _EntiteEffet(11, _EffectComponent(effect_type=8))
    c2 = _cache(effets={8: _Effect(has_bonuses=True)})
    c2.add_effect(fx2, fx2.effect_component)
    assert [s.entity for s in c2.get_effects_with_bonuses()] == [fx2]
    assert c2.get_refreshing_effects() == []


# ---------------------------------------------------------------- 6. AddEntity
def test_add_entity_aiguille_sur_le_type_d_entite():
    """`AddEntity` teste le TYPE (`EffectEntity`) AVANT tout composant : une entite d'effet ne
    passe jamais par la branche ability, meme si elle portait un `TriggeredAbilityComponent`."""
    cat = {("u", 0): [_Ability({TRIGGER})]}
    u = _Unite(1, [_ConfigId(("u", 0), 42)])
    c = _cache(catalogue=cat, effets={1: _Effect()})
    c.add_entity(u)
    assert [s.order for s in c.get_active_triggered_abilities_and_effects(TRIGGER)] == [42]

    fx = _EntiteEffet(2)
    fx.triggered_ability_component = _Comp([_ConfigId(("u", 0), 42)])   # piege
    c.add_entity(fx)
    rendus = c.get_active_triggered_abilities_and_effects(TRIGGER)
    assert len(rendus) == 1, "l'entite d'effet a pris la branche ABILITY"
    assert [s.entity for s in c.get_effects()] == [fx]


def test_add_entity_n_est_pas_idempotent():
    """`AddEntity` passe `checkIfAlreadyExist: false` -- appeler deux fois inscrit DEUX FOIS.
    Seul `RefreshEntity` deduplique."""
    cat = {("u", 0): [_Ability({TRIGGER})]}
    u = _Unite(1, [_ConfigId(("u", 0), 42)])
    c = _cache(catalogue=cat)
    c.add_entity(u)
    c.add_entity(u)
    assert len(c.get_active_triggered_abilities_and_effects(TRIGGER)) == 2


def test_refresh_entity_deduplique_et_ignore_les_effets():
    cat = {("u", 0): [_Ability({TRIGGER})]}
    u = _Unite(1, [_ConfigId(("u", 0), 42)])
    c = _cache(catalogue=cat)
    c.add_entity(u)
    c.refresh_entity(u)
    assert len(c.get_active_triggered_abilities_and_effects(TRIGGER)) == 1
    fx = _EntiteEffet(2)
    c.refresh_entity(fx)                       # aucune branche effet dans `RefreshEntity`
    assert c.get_effects() == []


# ---------------------------------------------------------------- 7. la garde a trois criteres
def test_check_if_already_exist_compare_les_trois_criteres():
    """`<AddAbility>b__0` : `s.entity == entity && s.order == order && s.ability is ability`.

    Ne comparer que l'entite dedupliquerait des abilities DISTINCTES du meme porteur."""
    a1, a2 = _Ability({TRIGGER}), _Ability({TRIGGER})
    cat = {("u", 0): [a1], ("u", 1): [a2]}
    u = _Unite(1, [_ConfigId(("u", 0), 42), _ConfigId(("u", 1), 43)])
    c = _cache(catalogue=cat)
    c.add_ability(u, False, u.triggered_ability_component)
    assert [s.order for s in c.get_active_triggered_abilities_and_effects(TRIGGER)] == [42, 43]
    c.add_ability(u, True, u.triggered_ability_component)
    assert [s.order for s in c.get_active_triggered_abilities_and_effects(TRIGGER)] == [42, 43]

    # Un ORDER different sur la meme entite n'est PAS un doublon.
    u2 = _Unite(1, [_ConfigId(("u", 0), 99)])
    c.add_ability(u2, True, u2.triggered_ability_component)
    assert [s.order for s in c.get_active_triggered_abilities_and_effects(TRIGGER)] == [42, 43, 99]


def test_une_ability_n_est_inscrite_que_sur_ses_propres_triggers():
    cat = {("u", 0): [_Ability({TRIGGER})]}
    u = _Unite(1, [_ConfigId(("u", 0), 42)])
    c = _cache(catalogue=cat)
    c.add_entity(u)
    assert len(c.get_active_triggered_abilities_and_effects(TRIGGER)) == 1
    assert c.get_active_triggered_abilities_and_effects(AUTRE) == []


# ---------------------------------------------------------------- 8. les deux gardes d'AddEffect
def test_add_effect_garde_la_premiere_boucle_mais_pas_la_seconde():
    """1re boucle : refuse un 2e `SortedEffect` de la MEME entite dans une liste qui en a deja un.
    2e boucle (`effect.<slot 0x2d>`) : AUCUNE garde. Uniformiser les deux ajoute -- ou supprime --
    des entrees."""
    fx = _EntiteEffet(9, _EffectComponent(effect_type=7))
    # `ability_triggers` porte DEUX fois le meme trigger : la garde ne doit en laisser passer qu'un.
    c = _cache(effets={7: _Effect(ability_triggers=(TRIGGER, TRIGGER))})
    c.add_effect(fx, fx.effect_component)
    assert len(c.get_active_triggered_abilities_and_effects(TRIGGER)) == 1

    # Meme montage sur la SECONDE boucle : deux entrees, parce qu'elle n'a pas de garde.
    fx2 = _EntiteEffet(10, _EffectComponent(effect_type=8))
    c2 = _cache(effets={8: _Effect(own_triggers=(TRIGGER, TRIGGER))})
    c2.add_effect(fx2, fx2.effect_component)
    assert len(c2.get_active_triggered_abilities_and_effects(TRIGGER)) == 2


def test_add_effect_alimente_toujours_la_liste_effects():
    fx = _EntiteEffet(9, _EffectComponent(effect_type=7))
    c = _cache(effets={7: _Effect()})
    c.add_effect(fx, fx.effect_component)
    assert [s.entity for s in c.get_effects()] == [fx]
    assert c.get_refreshing_effects() == [] and c.get_effects_with_bonuses() == []


# ---------------------------------------------------------------- 9. RemoveEntity
def test_remove_entity_effet_retire_UNE_SEULE_entree_par_liste():
    """Branche EFFET : `FindIndex` + `RemoveAt`, pas `RemoveAll`. L'asymetrie avec la branche
    UNITE est REELLE et le port la conserve : une entite d'effet ne peut avoir qu'UNE entree par
    liste (la 1re boucle d'`AddEffect` s'en assure), donc un `RemoveAll` serait sans effet
    aujourd'hui et masquerait toute rupture future de cet invariant."""
    fx = _EntiteEffet(9, _EffectComponent(effect_type=8))
    c = _cache(effets={8: _Effect(own_triggers=(TRIGGER, TRIGGER))})     # 2 entrees, sans garde
    c.add_effect(fx, fx.effect_component)
    assert len(c.get_active_triggered_abilities_and_effects(TRIGGER)) == 2
    c.remove_entity(fx)
    assert len(c.get_active_triggered_abilities_and_effects(TRIGGER)) == 1
    assert c.get_effects() == []                     # la liste homogene, elle, n'en avait qu'une


def test_remove_entity_unite_retire_TOUT_et_ne_touche_pas_aux_listes_d_effet():
    cat = {("u", 0): [_Ability({TRIGGER})], ("u", 1): [_Ability({TRIGGER})]}
    u = _Unite(1, [_ConfigId(("u", 0), 42), _ConfigId(("u", 1), 43)])
    fx = _EntiteEffet(9, _EffectComponent(effect_type=7))
    c = _cache(catalogue=cat, effets={7: _Effect(ability_triggers=(TRIGGER,))})
    c.add_entity(u)
    c.add_entity(fx)
    assert len(c.get_active_triggered_abilities_and_effects(TRIGGER)) == 3
    c.remove_entity(u)
    restants = c.get_active_triggered_abilities_and_effects(TRIGGER)
    assert [type(s).__name__ for s in restants] == ["SortedEffect"]
    # La branche UNITE ne purge PAS les quatre listes d'effet : c'est le `RemoveEntity` de
    # l'entite-effet qui les retire, pas celui de son porteur.
    assert [s.entity for s in c.get_effects()] == [fx]


def test_remove_entity_ignore_ce_qui_n_est_ni_effet_ni_unite():
    class _Autre:
        effect_component = None
        triggered_ability_component = None
        is_unit = False
    c = _cache()
    c.remove_entity(_Autre())                        # ne doit rien lever


# ---------------------------------------------------------------- 10. RemoveTriggered
def test_remove_triggered_ne_touche_que_le_dictionnaire_actif():
    """`RemoveTriggered` n'itere QUE `+0x20`. Ni `+0x28`, ni `+0x50`, ni les listes d'effet ne
    sont purges -- ce n'est pas un oubli qu'on corrige au portage."""
    cat = {("u", 0): [_Ability({TRIGGER})], ("u", 1): [_Ability({TRIGGER})]}
    u = _Unite(1, [_ConfigId(("u", 0), 42), _ConfigId(("u", 1), 43)])
    c = _cache(catalogue=cat)
    c.add_entity(u)
    c.simulated[TRIGGER].append(SortedTriggeredAbility(u, 42))
    c.triggered_ability_for_non_owner_playbook.append(SortedTriggeredAbility(u, 42))
    c.remove_triggered(u, 42)
    assert [s.order for s in c.get_active_triggered_abilities_and_effects(TRIGGER)] == [43]
    assert len(c.get_simulated_active_triggered_abilities(TRIGGER)) == 1
    assert len(c.get_triggered_ability_for_non_owner_playbook()) == 1


def test_remove_triggered_discrimine_l_entite_ET_l_order():
    cat = {("u", 0): [_Ability({TRIGGER})]}
    a, b = _Unite(1, [_ConfigId(("u", 0), 42)]), _Unite(2, [_ConfigId(("u", 0), 42)])
    c = _cache(catalogue=cat)
    c.add_entity(a)
    c.add_entity(b)
    c.remove_triggered(a, 42)
    assert [s.entity for s in c.get_active_triggered_abilities_and_effects(TRIGGER)] == [b]


# ---------------------------------------------------------------- 11. le mirror d'enum
def test_mirror_ability_priority():
    """Les cinq membres, verbatim `data/symbols/<build>/frida/enums.tsv`."""
    assert [(m.name, int(m)) for m in AbilityPriority] == [
        ("First", 1000), ("Early", 100), ("Normal", 0), ("Late", -100), ("Last", -1000)]


# ---------------------------------------------------------------- gardes de non-degradation
def test_les_resolveurs_absents_LEVENT_au_lieu_de_degrader():
    """Un peupleur sans sa base de donnees LEVE : le natif y deref un champ non nullable du ctor.

    Une entree jamais inscrite est EXACTEMENT le mode de panne silencieuse que ce cache existe
    pour rendre visible -- degrader en no-op le reproduirait."""
    c = AbilityAndEffectCache()
    with pytest.raises(ValueError):
        c.add_ability(_Unite(1, [_ConfigId(("u", 0), 42)]), False, _Comp([]))
    with pytest.raises(ValueError):
        c.add_effect(_EntiteEffet(2), _EffectComponent())


def test_get_priority_leve_quand_le_porteur_est_nul():
    with pytest.raises(ValueError):
        SortedEffect(entity=None).get_priority()
    with pytest.raises(ValueError):
        SortedTriggeredAbility(entity=None, order=1).get_priority()
