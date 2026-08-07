"""GARDE #523-r1 (OFFLINE PURE) -- la triggered `1546 HeavyWarpFlamer_AttackTracking`, le COMPTEUR
de coups psychiques ALLIES que lit `1227 HeavyWarpFlamer`.

CE QU'ELLE PROTEGE. Le noeud de LECTURE existe depuis #523 (`HeavyWarpFlamerAbility$$
GetNumExtraHits`) ; ce qui manquait etait l'ECRITURE. Les cinq choses qui peuvent regresser ici sans
qu'aucun autre test ne rougisse :

  1. **LE CHEMIN DE REGISTRATION** -- `ACTIVE_ABILITY_TRIGGERS["HeavyWarpFlamer"]`, la voie
     `activeAbilities` -> triggered DERIVEE (`StaticBattleRules.ActiveAbility$$
     GetDerivedTriggeredAbilities`). 1546 n'a AUCUNE entree de gameconfig et `thousSekhetar` ne la
     liste ni en `passiveAbilities` ni ailleurs : par toute autre voie elle serait INTROUVABLE, et
     l'absence serait SILENCIEUSE (le compteur resterait a 0, exactement l'etat d'avant).
  2. **L'`AbilityOrEffect` DE LA CLE = 1227, PAS 1546.** C'est le litteral `mov edx, 0x4cb` de
     `...HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour+0x49`, INVISIBLE au decompile
     (ghidra perd le registre). Ecrire son propre id rendrait le mecanisme INERTE **sans erreur** :
     l'ecriture irait dans une cle que personne ne lit.
  3. **LA `dataKey`** -- `"PSYCHIC_ATTACKS_KEY"`, PARTAGEE avec le lecteur de `thousandsons.py`.
     Deux chaines differentes = meme panne muette qu'au point 2.
  4. **LA FEUILLE EST `SetPersistentData`, ET LA VALEUR EST UN NOEUD** -- `Sum(GetPersistentData(
     1227, Owner, KEY), Direct(1))`. `SetPersistentDataBehavior$$Execute` ECRASE (aucun appel a
     `TryGetPersistData`), donc c'est le noeud VALEUR qui porte l'increment ; le remplacer par un
     scalaire figerait le compteur a 1.
  5. **LES CINQ CONJOINTS DU TRIGGER**, chacun exerce SEUL : `On(9)`, `IsTurnOf(Owner)`,
     `NOT AreEqual(Attacker, Owner)`, `AreFriends(Attacker, Owner)`,
     `CurrentAttackDamageProfilesContain(Psychic)` -- plus le disjoint `On(TurnEnd)` qui VIDE.
     Chaque conjoint manquant rend le port PERMISSIF (il compterait des attaques que le natif ne
     compte pas), et un port permissif est vert partout ou l'on ne le cherche pas.

Confront LIVE de bout en bout (nombre de coups au tour 1 vs tour 2, delta, per-coup bit-exact) :
`python scripts/python/probe_523r1_heavy_warp_flamer_tracking.py` et sa garde
`test_523r1_heavy_warp_flamer_tracking_live.py`.
RE : `docs/rl/case-523-r1-heavy-warp-flamer-attack-tracking.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Perimetre pris LARGE, et non feuille a feuille : le dispatch de
        # trigger tire le registre COMPLET (`dispatch/registry.py` importe la totalite des modules
        # `loki/**`), le vocabulaire DSL et la couche d'effets -- un declencheur trop etroit est un
        # FAUX VERT. Foyers vraiment load-bearing, pour la relecture humaine :
        # `operations/triggers/loki/heavy_warp_flamer.py` (le port), `dispatch/registry.py` (le
        # cablage), `abilities/behaviours/persistent_data.py` (les feuilles), `runner/components.py`
        # (le sac), `entities/formulas.py` (`Sum`/`GetPersistentData`), `abilities/thousandsons.py`
        # (le LECTEUR du compteur).
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Le chemin de registration part des `activeAbilities` du gameconfig du BUILD, et les
        # constantes `nrOfHits`/`maxNrOfHits` de 1227 en viennent aussi.
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : la voie de registration `ACTIVE_ABILITY_TRIGGERS`, la cle "
              "composite `(1227, \"PSYCHIC_ATTACKS_KEY\")` (l'id de l'ACTIVE, pas celui de la "
              "triggered), la forme des deux arbres (`SetPersistentData` d'une valeur `Sum(Get, "
              "1)` / `ClearPersistentData`), les cinq conjoints du `CreateTrigger` exerces UN A UN "
              "et le disjoint `On(TurnEnd)`. Aucun runner, aucune session Frida : le seul acces "
              "disque est le depot (gameconfig du build pour `activeAbilities` et les constantes).",
}

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import gameconfig as GC                                                       # noqa: E402
from engine.dsl.base import Const                                             # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType             # noqa: E402
from engine.entities.damage_profile_type import DamageProfileType             # noqa: E402
from engine.entities.formulas import GetPersistentData, Sum                   # noqa: E402
from engine.entities.selectors.accessors import Owner                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType       # noqa: E402
from engine.entities.unit_context import UnitContext                          # noqa: E402
from engine.runner.abilities.behaviours.persistent_data import (              # noqa: E402
    ClearPersistentData, SetPersistentData)
from engine.runner.abilities.thousandsons import (                            # noqa: E402
    HEAVY_WARP_FLAMER_STACK_KEY, heavy_warp_flamer_num_total_hits)
from engine.runner.components import (OwnerComponent, StatsComponent,         # noqa: E402
                                      UnitComponent, persistent_data)
from engine.runner.operations.triggers.base import TriggerEvent               # noqa: E402
from engine.runner.operations.triggers.dispatch.core import (                 # noqa: E402
    collect_triggered_abilities, evaluate_trigger_operation)
from engine.runner.operations.triggers.dispatch.registry import (             # noqa: E402
    ACTIVE_ABILITY_TRIGGERS)
from engine.runner.operations.triggers.dispatch.turn import (                 # noqa: E402
    end_turn_summon_triggers)
from engine.runner.operations.triggers.loki.heavy_warp_flamer import (        # noqa: E402
    HeavyWarpFlamerAttackTrackingAbility, HeavyWarpFlamerAttackTrackingResetAbility,
    attack_tracking_clear_tree, attack_tracking_increment_tree,
    ATTACK_TRACKING_ID, HEAVY_WARP_FLAMER, INCREMENT, STACK_KEY)
from engine.runner.state import State                                         # noqa: E402

CARRIER = "thousSekhetar"
ACTIVE_KEY = "HeavyWarpFlamer"
#: (team, player) des deux camps -- `IsTurnOf(Owner)` compare le PLAYER, `AreFriends` la TEAM.
MOI, ADVERSE = (1, 3), (2, 4)
KEY = (int(ActiveAbilityType.HeavyWarpFlamer), "PSYCHIC_ATTACKS_KEY")


# --------------------------------------------------------------------------- montage synthetique

def _monte():
    """Trois entites : le PORTEUR (1), un ALLIE (2), un ENNEMI (3). Aucun plateau, aucun degat :
    ce fichier n'exerce QUE le trigger et ses deux behaviours."""
    st = State()
    st.current_player_id = MOI[1]
    ids = {}
    for nom, vid, (team, player) in (("porteur", CARRIER, MOI),
                                     ("allie", "thousSorcerer", MOI),
                                     ("ennemi", "necroWarden", ADVERSE)):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vid, alive=True))
        e.add_component(OwnerComponent(team=team, player=player))
        e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id=vid)))
        ids[nom] = e.id
    return st, ids


def _ev(actor, target, profils=("Psychic",)):
    """Le vecteur `On(9 = Attack)` tel que `finish_attack_triggers` / `after_hit_ability_attack` le
    construisent : `actor` = l'attaquant, `profiles` = le SET des profils de TOUTE l'attaque."""
    return TriggerEvent(EventTriggerType.Attack, actor, target, ranged=True, profile=profils[0],
                        profiles=set(profils))


def _compteur(st, owner):
    return persistent_data(st.get_entity(owner), KEY)


# --------------------------------------------------------------------------- 1. la REGISTRATION

def test_la_voie_de_registration_est_l_ability_ACTIVE():
    """`UnitFactory$$AddDerivedAbilities` : pour chaque ability ACTIVE de l'unite,
    `if (StaticBattleRules.ActiveAbility$$HasDerivedTriggeredAbilities(t))
        TriggeredAbilityComponent$$TryAdd(GetDerivedTriggeredAbilities(t))`.

    Le couple `1227 -> 1546` est LU verbatim dans le motif d'insertion du `.cctor` (valeur en
    `[rbp+0x18]`, cle en `[rbp+0x20]`), entre ses voisins DEJA portes `1507 <- 1214` (Hailstrike) et
    `1555 <- 1232` (EmpyricAmbush). Aucune autre voie ne pourrait la monter : 1546 n'a AUCUNE entree
    de gameconfig et le porteur ne la liste NULLE PART."""
    assert GC.ability("HeavyWarpFlamer_AttackTracking") is None, (
        "1546 aurait acquis une entree de gameconfig : re-lire la voie de registration")
    kit = GC.unit(CARRIER) or {}
    assert ACTIVE_KEY in (kit.get("activeAbilities") or []), (
        "la cle de `ACTIVE_ABILITY_TRIGGERS` est le NOM gameconfig de l'ability ACTIVE")
    assert ATTACK_TRACKING_ID not in [
        *(kit.get("passiveAbilities") or []), *(kit.get("relicAbilities") or [])], (
        "1546 n'arrive NI par passiveAbilities NI par relicAbilities")
    classes = ACTIVE_ABILITY_TRIGGERS.get(ACTIVE_KEY) or []
    assert HeavyWarpFlamerAttackTrackingAbility in classes
    assert HeavyWarpFlamerAttackTrackingResetAbility in classes


def test_le_porteur_recoit_les_DEUX_disjoints_et_l_allie_aucun():
    """Le natif a UNE classe dont le `CreateTrigger` est une DISJONCTION sur deux events ; le
    registre du port est indexe par `event_id`, d'ou DEUX entrees -- et elles n'appartiennent qu'au
    porteur de l'ACTIVE."""
    st, ids = _monte()
    par_owner = {}
    for t in collect_triggered_abilities(st):
        if isinstance(t, (HeavyWarpFlamerAttackTrackingAbility,
                          HeavyWarpFlamerAttackTrackingResetAbility)):
            par_owner.setdefault(int(t.owner_id), set()).add(int(t.event_id))
    assert par_owner == {ids["porteur"]: {int(EventTriggerType.Attack),
                                          int(EventTriggerType.TurnEnd)}}, par_owner


# --------------------------------------------------------------------------- 2/3/4. les ARBRES

def test_la_cle_est_celle_de_l_ACTIVE_1227_pas_celle_de_la_triggered_1546():
    """LE PIEGE CENTRAL. Le litteral `0x4cb` de `CreateBehaviour+0x49` est l'id de l'ACTIVE, et il
    est pose AVANT le `cmp edi, 0x17` -- donc PARTAGE par les deux branches. Ecrire 1546 rendrait le
    mecanisme inerte SANS ERREUR : les deux cotes n'adresseraient plus la meme cle."""
    assert HEAVY_WARP_FLAMER == int(ActiveAbilityType.HeavyWarpFlamer) == 1227
    assert ATTACK_TRACKING_ID == int(
        TriggeredAbilityType.HeavyWarpFlamer_AttackTrackingAbility) == 1546
    assert HEAVY_WARP_FLAMER != ATTACK_TRACKING_ID
    inc, clr = attack_tracking_increment_tree(), attack_tracking_clear_tree()
    assert inc.ability_or_effect == HEAVY_WARP_FLAMER
    assert clr.ability_or_effect == HEAVY_WARP_FLAMER
    # ... et c'est la MEME cle que celle du LECTEUR, cote `abilities/thousandsons.py`.
    assert STACK_KEY == HEAVY_WARP_FLAMER_STACK_KEY == "PSYCHIC_ATTACKS_KEY"
    assert inc.data_key == STACK_KEY and clr.data_key == STACK_KEY


def test_la_feuille_ECRASE_et_l_increment_vit_dans_le_noeud_VALEUR():
    """`DSLBehaviors$$SetPersistentData` -> `SetPersistentDataBehavior$$Execute`, qui n'appelle PAS
    `TryGetPersistData` : il ECRIT, point. L'increment est donc le noeud
    `Sum(GetPersistentData(1227, Owner, KEY), <DSLFormulas+0x20 = Direct(1)>)` -- un ARBRE, pas un
    scalaire calcule en Python (qui figerait le compteur a 1)."""
    inc = attack_tracking_increment_tree()
    assert isinstance(inc, SetPersistentData)
    assert isinstance(inc.unit_sel, Owner)
    assert isinstance(inc.value, Sum), "la valeur doit rester un NOEUD `Sum`"
    gauche, droite = inc.value.a, inc.value.b
    assert isinstance(gauche, GetPersistentData), "le 1er operande relit le compteur"
    assert gauche.ability_or_effect == HEAVY_WARP_FLAMER and gauche.data_key == STACK_KEY
    assert isinstance(gauche.unit, Owner)
    assert isinstance(droite, Const) and int(droite.value) == INCREMENT == 1
    clr = attack_tracking_clear_tree()
    assert isinstance(clr, ClearPersistentData) and isinstance(clr.unit_sel, Owner)


# --------------------------------------------------------------------------- 5. les CONJOINTS

def test_une_attaque_PSYCHIQUE_d_un_ALLIE_incremente_de_UN():
    st, ids = _monte()
    assert _compteur(st, ids["porteur"]) is None, "cle absente au depart (== 0 pour le natif)"
    evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
    assert _compteur(st, ids["porteur"]) == 1
    evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
    assert _compteur(st, ids["porteur"]) == 2, (
        "le 2e passage doit RELIRE puis ecrire 2 -- si la valeur etait un scalaire, il resterait 1")


def test_chaque_conjoint_du_trigger_MORD_seul():
    """Chacun est exerce en ne violant QUE lui : un conjoint oublie rend le port PERMISSIF, et un
    port permissif est vert partout ou l'on ne le cherche pas."""
    cas = {
        # `CurrentAttackDamageProfilesContain(0xd = Psychic, includeNotApplied = 0)`
        "profil non psychique": lambda st, i: _ev(i["allie"], i["ennemi"], ("Physical",)),
        # `NOT AreEqual(Attacker, Owner@+0x30)` -- le porteur ne se compte JAMAIS lui-meme
        "attaque du PORTEUR": lambda st, i: _ev(i["porteur"], i["ennemi"]),
        # `AreFriends(Attacker, Owner@+0x30, 0 = ByCurrentTeam, 0)`
        "attaque d'un ENNEMI": lambda st, i: _ev(i["ennemi"], i["porteur"]),
    }
    for nom, faire in cas.items():
        st, ids = _monte()
        evaluate_trigger_operation(st, faire(st, ids))
        assert _compteur(st, ids["porteur"]) is None, (
            "%s : le compteur a bouge -> le conjoint correspondant ne mord plus" % nom)
    # `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` : hors du tour de l'equipe du porteur, RIEN.
    st, ids = _monte()
    st.current_player_id = ADVERSE[1]
    evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
    assert _compteur(st, ids["porteur"]) is None, (
        "IsTurnOf(Owner) : une attaque alliee hors de notre tour ne doit RIEN compter")
    # `On(9)` : ce trigger n'ecoute QUE le vecteur `Attack`.
    st, ids = _monte()
    evaluate_trigger_operation(st, TriggerEvent(
        EventTriggerType.AttackHit, ids["allie"], ids["ennemi"], ranged=True, profile="Psychic",
        profiles={"Psychic"}))
    assert _compteur(st, ids["porteur"]) is None, "le trigger ecoute un event qui n'est pas On(9)"


def test_le_disjoint_On_TurnEnd_VIDE_la_cle():
    """`On(0x17 = TurnEnd, ownerNeedsToBeAlive = 1)`, SANS aucun predicat -> `ClearPersistentData`.
    `Dictionary.Remove` : la cle DISPARAIT (elle ne retombe pas a 0, ce qui serait indistinguable
    pour le lecteur mais pas pour ce test)."""
    st, ids = _monte()
    evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
    evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
    assert _compteur(st, ids["porteur"]) == 2
    end_turn_summon_triggers(st, MOI[1])
    assert _compteur(st, ids["porteur"]) is None, "On(TurnEnd) n'a pas vide la cle"


def test_le_disjoint_On_TurnEnd_n_a_AUCUN_predicat_d_owner():
    """Le `op_BitwiseOr` final n'agrege que `On(0x17)` : ni `get_OwnerIsActor`, ni
    `<DSLTriggers+0x28>` (ce dernier n'est conjoint qu'a la branche `On(9)`). La cle est donc videe
    a CHAQUE fin de tour, y compris celle du camp ADVERSE."""
    st, ids = _monte()
    evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
    assert _compteur(st, ids["porteur"]) == 1
    end_turn_summon_triggers(st, ADVERSE[1])           # la fin de tour de l'AUTRE camp
    assert _compteur(st, ids["porteur"]) is None


# --------------------------------------------------------------------------- le LECTEUR, en bout

def test_le_compteur_ecrit_ici_est_bien_celui_que_LIT_GetNumTotalHits():
    """LA JONCTION DES DEUX TRANCHES. `heavy_warp_flamer_num_total_hits` (#523) evalue
    `GetPersistentData(1227, Owner, "PSYCHIC_ATTACKS_KEY")` sur `ctx.persistent_data` -- le MEME sac
    et la MEME cle que ceux qu'ecrit ce module. Le test le montre EN BOUT DE CHAINE : on ecrit par
    le trigger, on lit par le noeud de l'ability."""
    nr = int(GC.ability("HeavyWarpFlamer")["constants"]["nrOfHits"])
    mx = int(GC.ability("HeavyWarpFlamer")["constants"]["maxNrOfHits"])
    noeud = heavy_warp_flamer_num_total_hits(nr, mx)
    st, ids = _monte()

    class _Ctx:
        """Le strict minimum que lit `GetPersistentData` : l'accesseur `persistent_data` et un
        selecteur `Owner` resolvable."""
        def __init__(self, unit):
            self.owner = self.caster = unit
            self.persistent_data = lambda u, key: persistent_data(
                st.get_entity(int(u["id"])), key)

    ctx = _Ctx({"id": ids["porteur"]})
    assert noeud.calculate(ctx) == nr, "compteur absent -> `nrOfHits`"
    for attendu in (nr + 1, nr + 2):
        evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
        assert noeud.calculate(ctx) == attendu
    # PLAFOND : le `Min(..., maxNrOfHits - nrOfHits)` est en LECTURE, jamais en ECRITURE -- ce
    # module ecrit un entier NON borne, comme le natif.
    for _ in range(20):
        evaluate_trigger_operation(st, _ev(ids["allie"], ids["ennemi"]))
    assert _compteur(st, ids["porteur"]) == 22, "l'ECRITURE ne doit PAS etre bornee"
    assert noeud.calculate(ctx) == mx, "la LECTURE, elle, plafonne a `maxNrOfHits`"
