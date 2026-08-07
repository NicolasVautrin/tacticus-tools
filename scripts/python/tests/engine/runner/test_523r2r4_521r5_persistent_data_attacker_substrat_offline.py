"""GARDE (OFFLINE PURE) de TROIS lectures natives que rien n'observait -- #523-r2, #523-r4, #521-r5.

Les trois ont la MEME signature de panne : elles ne changent AUCUN observable des montages portes
aujourd'hui, donc aucun test existant ne peut les voir. C'est exactement pourquoi elles ont survecu.

  1. **#523-r2 -- `AddPersistentDataBehavior$$Execute` ACCUMULE.** Son corps appelle
     `PersistentDataComponent$$TryGetPersistData<T>` PUIS `Nullable<T>$$GetValueOrDefault` PUIS
     `add dword ptr [rbp+0x1e8], eax` avant `PersistData<T>` -- lu a l'assembleur. Le port ecrivait
     un ECRASEMENT et sa docstring l'AFFIRMAIT. Aucun observable ne diverge (l'unique consommateur
     porte, `HaywireMine`, ne relit la cle que par `AmountIsZero`, et un `Clear` s'intercale entre
     deux ecritures) -- ce test-ci exerce donc la feuille DIRECTEMENT, seule facon de le voir.
     Le jumeau `SetPersistentDataBehavior$$Execute` n'appelle NI `TryGetPersistData` NI d'`add` :
     la NON-accumulation de `SetPersistentData` est assertee ici aussi, parce que c'est elle qui
     empeche de double-compter le compteur de `1546 HeavyWarpFlamer_AttackTracking` (dont la valeur
     est deja un noeud `Sum(GetPersistentData, 1)`).

  2. **#523-r4 -- `DSLSelectors$$Attacker` est CONDITIONNEL.**
     `If(AreEqual(<+0x98>, DirectAbilitySelector(0x434)), ParentSelector(Caster), Caster)`. Le port
     collapsait sur `ev.actor_id` sans la branche. Le selecteur est PARTAGE : ses XREFS donnent
     QUATRE consommateurs natifs, dont UN SEUL est porte -- d'ou un FOYER
     (`triggers/base.py::attacker_of`) plutot qu'un collapse recopie. La branche MV71 est INERTE sur
     le consommateur porte (cf. la docstring du foyer) : elle n'est exercable qu'ICI.

  3. **#521-r5 -- les deux registres d'ACTIVE lisent le MEME champ natif.**
     `UnitFactory$$AddDerivedAbilities` ouvre sur `List<ActiveAbilityType>.GetEnumerator(config@+0xa0)`
     et `UnitFactory$$AddConfiguredAbilities` boucle sur ce MEME `config@+0xa0` pour appeler
     `AddActiveAbility` -> `GetPassiveHelperAbility`. `ACTIVE_ABILITY_TRIGGERS` lisait pourtant le
     seul kit gameconfig, donc il etait AVEUGLE a une active GREFFEE -- le seul chemin de
     confrontation d'une ability a porteur npc. Le regime discriminant (kit qui ne liste pas
     l'active, canal mesure qui la liste) est monte ici.

Aucun runner, aucune session Frida. RE : `docs/rl/case-523-r1-heavy-warp-flamer-attack-tracking.md`
et `docs/rl/case-521r1-talons-used-abilities-le-sixieme-chemin.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        # Elles portent des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest) -- donc aucun graphe d'imports ne les verrait.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Perimetre pris LARGE sur `engine/**`, et non feuille a feuille :
        # `collect_triggered_abilities` tire le registre COMPLET (`dispatch/registry.py` importe la
        # totalite des modules `loki/**`), donc la fermeture d'imports MESUREE depasse la centaine
        # de modules -- un declencheur plus etroit serait un FAUX VERT. Foyers vraiment
        # load-bearing, pour la relecture humaine : `abilities/behaviours/persistent_data.py` (les
        # deux feuilles), `operations/triggers/base.py` (le foyer `attacker_of`),
        # `operations/triggers/dispatch/core.py` (le substrat des deux registres),
        # `operations/triggers/loki/heavy_warp_flamer.py` et `.../haywire_mine.py` (les deux
        # consommateurs), `runner/components.py` (le sac persistant).
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul.
        # ⚠ PAS de `scripts/python/*.py` : ce joker retiendrait ce fichier a chaque edition d'un
        # des ~500 probes de la racine, dont aucun n'est dans sa fermeture. Le seul module RACINE
        # qu'il importe directement est `gameconfig`, deja enumere dans le socle.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Le regime NON greffe de #521-r5 lit les `activeAbilities` du gameconfig du BUILD.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : l'ACCUMULATION d'`AddPersistentData` et la NON-accumulation de "
              "`SetPersistentData` (la sequence d'appels qui separe les deux classes natives), la "
              "branche conditionnelle et le litteral 1076 du foyer `attacker_of` plus son usage "
              "par le seul consommateur porte, et le substrat COMMUN des deux registres d'active "
              "(regime GREFFE : kit gameconfig muet, canal mesure parlant). Aucun runner, aucune "
              "session Frida : le seul acces disque est le depot (gameconfig du build).",
}

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import pytest                                                                 # noqa: E402

import gameconfig as GC                                                       # noqa: E402
from engine.dsl.base import Const                                             # noqa: E402
from engine.dsl.effects import ExecutionContext                               # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType             # noqa: E402
from engine.entities.selectors.accessors import Owner                         # noqa: E402
from engine.entities.unit_context import UnitContext                          # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state    # noqa: E402
from engine.runner.abilities.behaviours.persistent_data import (              # noqa: E402
    AddPersistentData, SetPersistentData)
from engine.runner.components import (OwnerComponent, PersistentDataComponent,  # noqa: E402
                                      StatsComponent, UnitComponent)
from engine.runner.operations.triggers import base as TB                      # noqa: E402
from engine.runner.operations.triggers.base import (                          # noqa: E402
    ATTACKER_PARENT_ABILITY, TriggerEvent, attacker_of)
from engine.runner.operations.triggers.dispatch.core import (                 # noqa: E402
    collect_triggered_abilities)
from engine.runner.operations.triggers.loki import heavy_warp_flamer as HWF   # noqa: E402
from engine.runner.state import State                                         # noqa: E402

#: L'ability sous laquelle le sac est adresse ici -- n'importe laquelle ferait l'affaire : ces
#: tests portent sur la FEUILLE, pas sur un consommateur.
SAC = int(ActiveAbilityType.HeavyWarpFlamer)
CLE = "TEST_KEY"


def _unite(st, vid="thousSekhetar", team=1, player=3, parent_id=None,
           config_actives=None):
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id=vid, alive=True, parent_id=parent_id))
    e.add_component(OwnerComponent(team=team, player=player))
    ctx = UnitContext(entity_id=e.id, visual_id=vid)
    if config_actives is not None:
        ctx.config_active_abilities = list(config_actives)
    e.add_component(StatsComponent(ctx=ctx))
    return e.id


def _valeur(st, uid):
    c = st.get_entity(uid).get_component(PersistentDataComponent)
    return None if c is None else c.try_get_persist_data((SAC, CLE))


# ══════════════════════════════════════════════ #523-r2 : la feuille ADDITIONNE

def test_523r2_add_persistent_data_ACCUMULE_au_lieu_d_ecraser():
    """`AddPersistentDataBehavior$$Execute` : `TryGetPersistData<T>` -> `GetValueOrDefault()` ->
    `add dword` -> `PersistData<T>`. Trois poses de `Direct(1)` DOIVENT donner 1, 2, 3.

    Si le port ecrase (l'etat d'avant #523-r2), les trois rendent 1 et ce test tombe des la
    deuxieme -- c'est le SEUL endroit du depot ou la difference est observable."""
    st = State()
    uid = _unite(st)
    feuille = AddPersistentData(SAC, Owner(), CLE, Const(1))
    vus = []
    for _ in range(3):
        ectx = ExecutionContext(state=st, rng=st.rng)
        feuille.execute(entities_from_state(st, uid, uid, actor_id=uid), ectx)
        vus.append(_valeur(st, uid))
    assert vus == [1, 2, 3], (
        "AddPersistentData doit ACCUMULER (`add dword ptr [rbp+0x1e8], eax` entre "
        "`TryGetPersistData<T>` et `PersistData<T>`), pas ecraser : %r" % (vus,))


def test_523r2_le_defaut_sur_cle_absente_est_ZERO_pas_un_no_op():
    """`TryGetPersistData<T>` memset son `out` a 0 et n'appelle `System.Nullable<T>$$.ctor` que sur
    SUCCES ; le behaviour lit ensuite `GetValueOrDefault()`. Donc sur une cle ABSENTE l'ancien vaut
    `default(int) = 0` et la premiere pose ecrit la valeur NUE -- elle n'est ni sautee, ni doublee."""
    st = State()
    uid = _unite(st)
    ectx = ExecutionContext(state=st, rng=st.rng)
    AddPersistentData(SAC, Owner(), CLE, Const(7)).execute(
        entities_from_state(st, uid, uid, actor_id=uid), ectx)
    assert _valeur(st, uid) == 7
    posees = [p for n, p in ectx.emitted if n == "AddPersistentData"]
    assert posees and posees[-1]["posees"][0]["ancien"] == 0, (
        "l'ancien d'une cle absente doit etre 0 (`default(T)`), pas None : %r" % (posees,))


def test_523r2_set_persistent_data_N_ACCUMULE_PAS():
    """CONTRE-EPREUVE, et elle n'est pas decorative : c'est la NON-accumulation de
    `SetPersistentDataBehavior$$Execute` (aucun appel a `TryGetPersistData`, aucun `add`) qui
    empeche de double-compter `1546 HeavyWarpFlamer_AttackTracking`, dont la VALEUR est deja le
    noeud `Sum(GetPersistentData(...), Direct(1))`. Si cette feuille se mettait a accumuler, le
    compteur avancerait de `ancien + (ancien + 1)` au lieu de `ancien + 1`."""
    st = State()
    uid = _unite(st)
    feuille = SetPersistentData(SAC, Owner(), CLE, Const(1))
    vus = []
    for _ in range(3):
        ectx = ExecutionContext(state=st, rng=st.rng)
        feuille.execute(entities_from_state(st, uid, uid, actor_id=uid), ectx)
        vus.append(_valeur(st, uid))
    assert vus == [1, 1, 1], (
        "SetPersistentData doit ECRASER : son corps natif n'appelle pas `TryGetPersistData<T>` "
        "-- %r" % (vus,))


def test_523r2_haywire_mine_ne_change_PAS_d_observable():
    """Le consommateur porte reste au meme verdict, et la raison est STRUCTURELLE : son unique
    LECTEUR est `AmountIsZero(GetPersistentData)`, faux pour 1 comme pour 2. On l'exerce pour de
    vrai -- deux poses SANS `Clear` intercale donnent 2, et le gate reste ferme."""
    st = State()
    uid = _unite(st)
    feuille = AddPersistentData(SAC, Owner(), CLE, Const(1))
    for _ in range(2):
        feuille.execute(entities_from_state(st, uid, uid, actor_id=uid),
                        ExecutionContext(state=st, rng=st.rng))
    v = _valeur(st, uid)
    assert v == 2
    assert not (v == 0), "le gate `AmountIsZero` doit rester FERME que la valeur vaille 1 ou 2"
    # Et apres le `ClearPersistentData` de `HaywireMine_ResetAbility`, la cle est ABSENTE : la
    # pose suivante repart de `default = 0`, donc 1 -- identique a l'ecrasement.
    st.get_entity(uid).get_component(PersistentDataComponent).clear_persistent_data((SAC, CLE))
    feuille.execute(entities_from_state(st, uid, uid, actor_id=uid),
                    ExecutionContext(state=st, rng=st.rng))
    assert _valeur(st, uid) == 1


# ══════════════════════════════════════════════ #523-r4 : le selecteur CONDITIONNEL

def test_523r4_le_litteral_de_la_condition_est_1076():
    """`...DSLSelectors$$Attacker+0x38` : `mov edx,0x434`. L'ordinal est ecrit ICI pour qu'un
    renumerotage du build ne passe pas inapercu (`probe_313` compare le MIRROR au build, pas la
    valeur ecrite au site)."""
    assert ATTACKER_PARENT_ABILITY == 1076
    assert int(ActiveAbilityType.MV71SniperDroneSquadAttack) == ATTACKER_PARENT_ABILITY, (
        "le littéral 0x434 doit nommer MV71SniperDroneSquadAttack")


def test_523r4_branche_ELSE_rend_le_caster_inchange():
    """`else -> Caster@+0x48`, que ce vecteur expose en `ev.actor_id`. C'est le comportement
    D'AVANT : aucun montage live ne peut changer de verdict par ce fix."""
    st = State()
    a = _unite(st)
    p = _unite(st)
    enfant = _unite(st, parent_id=p)
    for abil in (None, int(ActiveAbilityType.HeavyWarpFlamer), 0):
        ev = TriggerEvent(EventTriggerType.Attack, a, a, ranged=False, profile=None,
                          ability_type=abil)
        assert attacker_of(st, ev) == a, "ability_type=%r doit rendre le caster" % (abil,)
    # Un enfant qui attaque avec une AUTRE ability reste lui-meme : la branche ne depend QUE de
    # l'ability, jamais de l'existence d'un parent.
    ev = TriggerEvent(EventTriggerType.Attack, enfant, a, ranged=False, profile=None,
                      ability_type=int(ActiveAbilityType.HeavyWarpFlamer))
    assert attacker_of(st, ev) == enfant


def test_523r4_branche_MV71_rend_le_PARENT():
    """`then -> ParentSelector(Caster@+0x48)` -> `UnitExtensions$$GetParent`, dont le port a le
    pendant `UnitComponent.parent_id`. C'est la branche que le collapse ignorait."""
    st = State()
    p = _unite(st)
    drone = _unite(st, parent_id=p)
    ev = TriggerEvent(EventTriggerType.Attack, drone, p, ranged=True, profile=None,
                      ability_type=ATTACKER_PARENT_ABILITY)
    assert attacker_of(st, ev) == p, "l'attaque du drone MV71 est creditee a son PARENT"


def test_523r4_parent_absent_rend_un_ensemble_VIDE():
    """`ParentSelector$$Select` n'ajoute a son `OrderedSet` que les parents NON NULS : un enfant
    sans parent rend un ensemble VIDE, PAS l'enfant. Le port rend `None`, et tout conjoint qui le
    consomme est alors faux -- degradation RESTRICTIVE, jamais permissive."""
    st = State()
    orphelin = _unite(st)
    ev = TriggerEvent(EventTriggerType.Attack, orphelin, orphelin, ranged=True, profile=None,
                      ability_type=ATTACKER_PARENT_ABILITY)
    assert attacker_of(st, ev) is None


def test_523r4_le_consommateur_porte_passe_par_le_FOYER():
    """Le selecteur est PARTAGE (4 consommateurs natifs, XREFS exhaustives) : le seul consommateur
    PORTE doit l'appeler, pas re-collapser. Substitution du foyer en FORME B
    (`TB.attacker_of`) -- un `from ... import attacker_of` fige au chargement NE MORDRAIT PAS."""
    st = State()
    porteur = _unite(st)
    allie = _unite(st)
    trig = HWF.HeavyWarpFlamerAttackTrackingAbility(porteur)
    ev = TriggerEvent(EventTriggerType.Attack, allie, porteur, ranged=True, profile="Psychic",
                      ability_type=None, profiles={"Psychic"}, player_id=3)
    assert trig.matches(st, ev) is True, "temoin nominal : le montage doit matcher SANS mutation"
    appels = []

    def _espion(state, event):
        appels.append(int(event.actor_id))
        return None                                   # ensemble VIDE -> le conjoint doit tomber

    ancien = TB.attacker_of
    try:
        TB.attacker_of = _espion
        assert trig.matches(st, ev) is False, (
            "le port doit consommer le FOYER `attacker_of` : un foyer qui rend un ensemble vide "
            "doit faire tomber `NOT AreEqual(Attacker, Owner)` / `AreFriends(Attacker, Owner)`")
    finally:
        TB.attacker_of = ancien
    assert appels == [allie], "le foyer doit etre appele UNE fois, avec l'acteur du vecteur"


# ══════════════════════════════════════════════ #521-r5 : le SUBSTRAT des deux registres

@pytest.mark.parametrize("greffe", [False, True])
def test_521r5_les_deux_registres_d_active_lisent_le_meme_substrat(greffe):
    """`UnitFactory$$AddDerivedAbilities` et `UnitFactory$$AddConfiguredAbilities` iterent le MEME
    `config@+0xa0` (`UnitConfiguration.ActiveAbilities`).

    Deux regimes, et c'est le SECOND qui discrimine :
      * `greffe = False` -- l'unite porte l'active dans son kit gameconfig, canal mesure MUET :
        les deux voies rendaient deja la meme chose AVANT le fix ;
      * `greffe = True`  -- kit gameconfig d'une unite qui n'a PAS l'active, canal mesure qui la
        porte (exactement ce que produit `catalog_inject.graft_active_ability`). Avant le fix,
        `ACTIVE_ABILITY_TRIGGERS` etait AVEUGLE ici et le registre rendait 0 entree, sans erreur.
    """
    st = State()
    if greffe:
        vid, actives = "necroWarden", ["HeavyWarpFlamer"]      # kit muet, mesure parlante
        assert "HeavyWarpFlamer" not in ((GC.unit(vid) or {}).get("activeAbilities") or []), (
            "le montage exige un kit gameconfig qui NE liste PAS l'active")
    else:
        vid, actives = "thousSekhetar", None                   # kit parlant, mesure muette
        assert "HeavyWarpFlamer" in ((GC.unit(vid) or {}).get("activeAbilities") or [])
    uid = _unite(st, vid=vid, config_actives=actives)
    portes = [type(t).__name__ for t in collect_triggered_abilities(st)
              if getattr(t, "owner_id", None) == uid]
    assert "HeavyWarpFlamerAttackTrackingAbility" in portes, (
        "regime greffe=%s : `ACTIVE_ABILITY_TRIGGERS` doit lire `config_active_abilities` (tri-etat "
        "avec repli gameconfig), comme `PASSIVE_HELPER_ABILITY_TRIGGERS` -- monte : %r"
        % (greffe, portes))
    assert "HeavyWarpFlamerAttackTrackingResetAbility" in portes


def test_521r5_le_tri_etat_ne_confond_pas_LISTE_VIDE_et_NON_MESURE():
    """`None` = canal non mesure -> repli gameconfig ; `[]` = MESURE et vide -> aucune active,
    donc AUCUNE inscription. Rabattre `[]` sur le repli ferait monter une triggered que le natif
    ne monte pas (`AddConfiguredAbilities` n'itererait rien)."""
    st = State()
    uid = _unite(st, vid="thousSekhetar", config_actives=[])
    portes = [type(t).__name__ for t in collect_triggered_abilities(st)
              if getattr(t, "owner_id", None) == uid]
    assert "HeavyWarpFlamerAttackTrackingAbility" not in portes, (
        "une liste MESUREE et VIDE doit rester vide, pas retomber sur le kit : %r" % (portes,))
