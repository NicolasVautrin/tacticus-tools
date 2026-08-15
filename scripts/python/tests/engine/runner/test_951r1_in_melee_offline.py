"""#951-r1 / #955-r1 / #508-r2 -- l'`AttackRangeType` de la mort, et les DEUX canaux qu'il ouvre.

CE QUE CETTE TRANCHE A LEVE, ET CE QUE CE FICHIER GARDE
=======================================================

Trois residus de ce foyer declaraient un blocage `etage` ou `seeding`. Les trois etaient FAUX pour
la meme raison : **un seul etage natif manquait au port**, le slot **4** d'`IBattleQuery`
(`IdunBattle.Core.Services.BattleQuery$$GetAttackRangeType`, arite 4, LU dans
`data/symbols/<build>/metadata/interface_slots.tsv`) -- le frere des slots 2 (`IsMeleeAttack`) et 3
(`IsRangedAttack`), deja portes tous les deux.

    #951-r1  << l'ECRIVAIN de `KillUnitOptions.inMelee` n'est pas localise >>   -> REFUTE
    #508-r2  << le call-site du slot 74 `RegisterAttack` n'est pas localise >>  -> REFUTE
    #955-r1  << le vecteur MORT ne seede aucune ability declenchante >>         -> REFUTE

La chaine de l'`inMelee`, LUE de bout en bout :

    IdunBattle.Operations.ApplyDamageOperation$$Execute
        rt = BattleQuery.<slot 4>(ability = DamageAppliedResult+0x40, caster = source du degat,
                                  casterPosition = GetUnitPosition(source), target = victime)
        -> KillUnitContext+0x38
    IdunBattle.Operations.RecordKillOperation$$Execute
        -> IdunBattle.Core.MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger, rt)
    lambda `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass49_0$$
            u003CVerifyDeathsu003Eb__0`
        -> `KillUnitOperationOptions$$ForDefault()` puis recopie de l'entree -> KillUnitOptions+0x3c
    IdunBattle.Operations.KillUnitOperation$$Execute
        local_378[0] = (rangeType.GetValueOrDefault() == Melee(1)) & rangeType.HasValue
        *(byte *)(victime.UnitComponent + 0x178) = local_378[0]        # DefeatedByMeleeAttack
        ... RegisterDefeatedUnit(stats_du_tueur, id_victime, inMelee: local_378[0])

TOUS LES TESTS DE CE FICHIER SONT OFFLINE (aucun runner) : ils portent sur des mirrors purs et sur
le cablage du port. La confrontation LIVE du couple victime/tueur est celle de #951-r3, deja en
place (`decisionView.units[].defeatedByMelee`).
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.entities.active_ability_type import ActiveAbilityType
from engine.runner.components import UnitComponent, register_defeated_unit
from engine.runner.operations.damage import AttackDamageOperation
from engine.services.battle_query import get_attack_range_type, is_ranged_attack

#: #486-r15 -- perimetre = exactement les foyers que ce fichier lit. Aucun runner ; le gameconfig du
#: build est lu (l'`attackRangeType` des abilities temoins est DERIVE, jamais code en dur) ->
#: `build: True`.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        # l'ETAGE porte par cette tranche, et ses deux freres avec qui la coherence est gardee
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/battle_query.py",
        # le CABLAGE : la file de morts, les deux ecritures de l'octet, et le lecteur du marqueur
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/revive.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/triggers/loki/possession.py",
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # les enums CITES au site
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/gameconfig.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige le SWITCH du slot 4 d'IBattleQuery (ses quatre branches, dont la "
              "TROISIEME valeur que ses freres n'ont pas), sa coherence avec le slot 3, et le "
              "cablage de l'`inMelee` -- de l'enqueue (`MatchState$$AddDeath`, 5e argument) aux "
              "DEUX ecritures du meme octet (`UnitComponent+0x178` sur la victime, "
              "`RegisterDefeatedUnit` sur le tueur). La confrontation LIVE du couple est celle de "
              "#951-r3 (`decisionView.units[].defeatedByMelee`), deja en place.",
}


# --------------------------------------------------------------------------------------------
# Etage 1 -- le mirror du slot 4, et ce qui le distingue de ses DEUX freres
# --------------------------------------------------------------------------------------------

def test_le_slot_4_rend_le_membre_Ranged_SANS_lire_la_position():
    """`case 2: return 2;` -- INCONDITIONNEL dans le decompile. Une ability declaree
    `attackRangeType: Ranged` est une attaque a distance MEME au contact ; c'est exactement ce que
    `#1025-r2` avait mesure sur le slot 3, et le slot 4 partage la meme cascade."""
    nom = GC.ability_name(int(ActiveAbilityType.TwinSmartMissileSystem))
    assert (GC.ability(nom) or {}).get("attackRangeType") == "Ranged", (
        "montage PERIME : l'ability temoin n'est plus declaree `Ranged` au gameconfig")
    assert get_attack_range_type(nom, (4, 3), (4, 4)) == "Ranged"      # positions ADJACENTES
    assert get_attack_range_type(nom, (0, 0), (9, 9)) == "Ranged"      # positions LOINTAINES
    assert get_attack_range_type(nom, None, None) == "Ranged"          # aucune position


def test_le_slot_4_a_une_TROISIEME_valeur_que_ses_deux_freres_n_ont_pas(monkeypatch):
    """LE POINT DE LA FONCTION. Les slots 2 et 3 rendent tous deux FAUX sur `AttackRangeType.None`
    (`case 0`), donc un booleen ne peut pas distinguer << pas de nature >> de << melee >> ni de
    << distance >>. Le slot 4, lui, rend le MEMBRE : c'est cette troisieme valeur que
    `RegisterAttackMade` (`@+0x28` / `@+0x2c`) et `KillUnitOperation` (`inMelee`) consomment, et
    la confondre incrementerait un compteur que le natif laisse a zero.

    L'ETAGE est substitue (et non pioche au gameconfig) parce que ce build ne porte AUCUNE ability
    dont `attackRangeType` vaut la chaine `"None"` : le SWITCH du slot 4 est ce qu'on teste, pas la
    distribution des donnees. Un `skip` ici ferait passer la branche `case 0` pour gardee."""
    import engine.services.battle_query as SBQ
    monkeypatch.setattr(SBQ, "attack_range_type", lambda _n: "None")
    assert SBQ.get_attack_range_type("peu-importe", (4, 3), (4, 4)) == "None"
    assert SBQ.get_attack_range_type("peu-importe", (0, 0), (9, 9)) == "None"
    # les deux freres, EUX, s'effondrent sur FAUX -- c'est la perte d'information a documenter
    assert SBQ.is_melee_attack("peu-importe", (4, 3), (4, 4)) is False
    assert SBQ.is_ranged_attack("peu-importe", (4, 3), (4, 4)) is False


@pytest.mark.parametrize("adjacent,attendu", [(True, "Melee"), (False, "Ranged")])
def test_la_branche_Normal_retombe_sur_l_adjacence(adjacent, attendu):
    """`case 3:` -- `Melee` ssi (pas de `ForceRangedAttack`) ET `AreEntitiesAdjacent`. C'est la
    branche que prend une attaque NORMALE concrete (pas d'entree nommee au gameconfig), et c'est
    elle qui rend le canal utile : sans elle, tout kill d'attaque normale serait classe `None`."""
    a, b = ((4, 3), (4, 4)) if adjacent else ((0, 0), (9, 9))
    assert get_attack_range_type(None, a, b) == attendu


def test_le_slot_4_est_COHERENT_avec_le_slot_3_sur_les_quatre_branches():
    """Controle de non-contradiction entre deux mirrors du MEME etage
    (`GetAbilityAttackRangeType`) : `is_ranged_attack(x) == (get_attack_range_type(x) == 'Ranged')`
    doit valoir sur les QUATRE branches. Ce n'est pas une tautologie -- les deux fonctions sont
    ecrites separement, comme les deux slots natifs, et une divergence signalerait qu'un des deux
    mirrors a derive."""
    cas = [(None, (4, 3), (4, 4)), (None, (0, 0), (9, 9))]
    for membre in ("Ranged", "Melee", "None"):
        nom = next((m.name for m in ActiveAbilityType
                    if (GC.ability(m.name) or {}).get("attackRangeType") == membre), None)
        if nom is not None:
            cas.append((nom, (4, 3), (4, 4)))
            cas.append((nom, (0, 0), (9, 9)))
    assert len(cas) >= 6, "balayage AMPUTE : moins de branches que prevu, il ne garde rien"
    for nom, a, b in cas:
        assert is_ranged_attack(nom, a, b) == (get_attack_range_type(nom, a, b) == "Ranged"), (
            "divergence slot 3 / slot 4 sur %r depuis %r vers %r" % (nom, a, b))


# --------------------------------------------------------------------------------------------
# Etage 2 -- le CABLAGE : de la file de morts jusqu'aux deux ecritures
# --------------------------------------------------------------------------------------------

class _Ent:
    def __init__(self, comps):
        self._c = dict(comps)

    def get_component(self, cls):
        return self._c.get(cls)


class _St:
    """Le strict minimum que `register_defeated_unit` consulte."""
    def __init__(self, ents):
        self.entities = ents

    def get_entity(self, uid):
        return self.entities.get(int(uid))


def _duo():
    tueur, victime = UnitComponent("A", True), UnitComponent("B", False)
    return _St({1: _Ent({UnitComponent: tueur}), 2: _Ent({UnitComponent: victime})}), tueur


def test_register_defeated_unit_partitionne_sur_in_melee():
    """`ActorStatisticsComponent$$RegisterDefeatedUnit(id, inMelee)`, LU aux octets :

        if ((char)inMelee == '\\0') lst = *(this + 0xb0);   # les AUTRES
        else                        lst = *(this + 0xa8);   # la MELEE
        *(int *)(this + 0xa0) += 1;                          # le compteur, INCONDITIONNEL

    Les trois etats du canal doivent aller dans la bonne liste, et le compteur doit les compter
    TOUS -- c'est ce dernier point qui distingue le compteur natif de `len(defeated_units)`."""
    st, tueur = _duo()
    assert register_defeated_unit(st, 1, 2, in_melee=True) is True
    assert tueur.defeated_units_melee == [2] and tueur.defeated_units_other == []

    st, tueur = _duo()
    assert register_defeated_unit(st, 1, 2, in_melee=False) is True
    assert tueur.defeated_units_melee == [] and tueur.defeated_units_other == [2]

    st, tueur = _duo()
    assert register_defeated_unit(st, 1, 2) is True                 # NON MESURE -> branche defaut
    assert tueur.defeated_units_melee == [] and tueur.defeated_units_other == [2]
    assert tueur.total_defeated_units == 1


def test_la_vue_union_est_inchangee_quelle_que_soit_la_partition():
    """LE CRAN DE NON-REGRESSION de #951-r1. `UnitsDefeatedBySelector$$Select` appelle `AddUnits`
    sur les DEUX listes : l'UNION ne bouge pas quand la partition change. Ses six lecteurs portes
    ne doivent donc RIEN voir de ce commit -- si cette egalite tombe, c'est que la vue derivee a
    ete remplacee par un champ."""
    st_m, tueur_m = _duo()
    register_defeated_unit(st_m, 1, 2, in_melee=True)
    st_o, tueur_o = _duo()
    register_defeated_unit(st_o, 1, 2, in_melee=False)
    assert tueur_m.defeated_units == tueur_o.defeated_units == [2]


def _kill_unit_operation_isole(monkeypatch, st, **kwargs):
    """Joue `_kill_unit_operation` en NEUTRALISANT tout ce qui n'est pas les deux ecritures d'
    `inMelee` (les cinq vecteurs d'evenement, la garde revive, les trois `RemoveEffects`).

    Les substitutions portent sur les modules REELLEMENT resolus a l'appel : `move_death` et
    `revive` sont importes en forme MODULE **dans** la fonction, donc un `setattr` sur le module
    mord ; `_kill_unit_remove_effects` est une fonction de module de `damage.py`."""
    from engine.runner.operations import damage as DM
    from engine.runner.operations.triggers.dispatch import move_death
    from engine.runner.operations import revive as _revive
    for nom in ("after_death_triggers", "pre_unit_death_2_triggers", "unit_death_triggers",
                "unit_defeated_triggers", "post_unit_kill_triggers"):
        monkeypatch.setattr(move_death, nom, lambda *a, **k: [])
    monkeypatch.setattr(_revive, "kill_unit_revive_gate", lambda *a, **k: None)
    monkeypatch.setattr(DM, "_kill_unit_remove_effects", lambda *a, **k: [])
    return AttackDamageOperation._kill_unit_operation(st, 2, 1, False, **kwargs)


def test_kill_unit_operation_ecrit_les_DEUX_faces_du_meme_octet(monkeypatch):
    """`KillUnitOperation$$Execute` calcule `inMelee` UNE fois et l'ecrit DEUX fois : sur la VICTIME
    (`UnitComponent+0x178`) et sur le TUEUR (`RegisterDefeatedUnit`). Le port doit faire pareil --
    poser l'un sans l'autre laisserait `PossessionAbility` et `TrophyTakerAbility` en desaccord sur
    la meme mort.

    ⚠ La place du marqueur est LOAD-BEARING et differe de celle de l'inscription : le natif ecrit
    `+0x178` **avant** la garde revive (pile d'accolades), et `RegisterDefeatedUnit` **apres**. Ce
    test ne garde que le couple ; la place relative est gardee par le decompile cite au site."""
    st, tueur = _duo()
    victime = st.get_entity(2).get_component(UnitComponent)
    assert victime.defeated_by_melee is None, "etat de depart : le canal n'est pas mesure"
    _kill_unit_operation_isole(monkeypatch, st, attack_range_type="Melee")
    assert victime.defeated_by_melee is True, "le marqueur `+0x178` de la VICTIME n'est pas ecrit"
    assert tueur.defeated_units_melee == [2], "le TUEUR n'a pas recu le MEME octet en `inMelee`"


def test_un_kill_a_DISTANCE_ecrit_False_des_deux_cotes(monkeypatch):
    """Bras NEGATIF du couple ci-dessus -- sans lui, une implementation qui poserait `True` en dur
    passerait. `rangeType == Ranged(2)` != `Melee(1)` -> `inMelee` FAUX, et le marqueur vaut
    `False` (MESURE), pas `None` (NON MESURE)."""
    st, tueur = _duo()
    _kill_unit_operation_isole(monkeypatch, st, attack_range_type="Ranged")
    assert st.get_entity(2).get_component(UnitComponent).defeated_by_melee is False
    assert tueur.defeated_units_other == [2] and tueur.defeated_units_melee == []


def test_une_voie_sans_AttackRangeType_ne_fabrique_pas_un_faux(monkeypatch):
    """`$$ForSteppable` (crush) et `$$ForDefault` (feuille DSL `Kill`) laissent `+0x3c` a ZERO ->
    `Nullable` VIDE -> `inMelee` FAUX cote natif. Cote port le canal reste `None` : l'inscription
    tombe dans la meme liste que le natif, et le marqueur n'est PAS pose -- pour que ses lecteurs
    sachent qu'ils n'ont pas mesure, au lieu de lire un `False` fabrique."""
    st, tueur = _duo()
    _kill_unit_operation_isole(monkeypatch, st)
    assert st.get_entity(2).get_component(UnitComponent).defeated_by_melee is None
    assert tueur.defeated_units_other == [2] and tueur.defeated_units_melee == []


def test_possession_lit_le_marqueur_et_retombe_sur_l_adjacence_sans_lui(monkeypatch):
    """#955-r1 (volet marqueur) -- `If(NOT IsDefeatedByMeleeAttack(Target), Spawn(unitId_2),
    Spawn(unitId))`. Le port approximait le marqueur POSITIONNELLEMENT ; il le LIT desormais quand
    il est mesure, et ne retombe sur l'approximation que sur `None`.

    Le montage neutralise `_is_ranged_position` en le forcant a VRAI : si le marqueur etait ignore,
    un kill de MELEE serait classe << a distance >> et donnerait le mauvais summon."""
    from engine.runner.operations.triggers.loki import possession as P

    monkeypatch.setattr(P, "_is_ranged_position", lambda *a, **k: True)
    victime = UnitComponent("B", False)
    st = _St({1: _Ent({UnitComponent: UnitComponent("A", True)}),
              2: _Ent({UnitComponent: victime})})
    st.rng = None

    vus: list = []
    monkeypatch.setattr(P, "possession_spawn_tree",
                        lambda _s, ranged_kill: vus.append(ranged_kill) or _Arbre())
    monkeypatch.setattr(P, "entities_from_state", lambda *a, **k: object())
    monkeypatch.setattr(P, "triggered_ability_state", lambda *a, **k: (50, 100))
    monkeypatch.setattr(P, "ExecutionContext", lambda **k: _Ctx())

    ab = P.PossessionSummonOnKillAbility(1)
    ev = P.TriggerEvent(int(P.EventTriggerType.PostUnitKill), 1, 2, ranged=False, profile=None,
                        dying_id=2)
    victime.defeated_by_melee = True                       # MESURE : kill de MELEE
    ab.execute_behaviour(st, ev)
    victime.defeated_by_melee = False                      # MESURE : kill a DISTANCE
    ab.execute_behaviour(st, ev)
    victime.defeated_by_melee = None                       # NON MESURE -> repli positionnel (True)
    ab.execute_behaviour(st, ev)
    assert vus == [False, True, True], (
        "le marqueur `+0x178` n'est pas lu, ou le repli a disparu -- vus %s" % (vus,))


class _Arbre:
    def execute(self, entities, ectx):
        return None


class _Ctx:
    def __init__(self):
        self.emitted = []
        self.state = None
        self.rng = None
