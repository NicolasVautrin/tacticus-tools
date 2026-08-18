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
from engine.runner.state import Entity, State
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
        # #10026 -- les DEUX foyers que ce fichier TRAVERSE depuis #10015-r3 et qu'il ne declarait
        # pas : le retrait de plateau raccorde DANS `_kill_unit_operation` (slot 6
        # @`KillUnitOperation$$Execute+0xd34`) et le substrat ECS que le montage instancie. C'est
        # exactement par la que ce fichier est devenu rouge sans que son verdict ait bouge.
        "scripts/python/engine/runner/operations/remove_unit.py",
        "scripts/python/engine/runner/state.py",
        # #462-...-r6-r2 -- le SEEDING du marqueur : c'est lui qui decide ou le tri-etat `None`
        # survit encore, et le fichier l'exerce desormais directement
        # (`test_le_tri_etat_survit_au_CHARGEMENT_donc_le_repli_n_est_pas_MORT`).
        "scripts/python/engine/runner/snapshot.py",
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

def _ent(uid: int, *comps):
    """L'entite REELLE du moteur, jamais un double maison (#10026).

    ⚠ CE FICHIER PORTAIT DEUX DOUBLES (`_Ent`, `_St`) dont la surface etait << le strict minimum
    que `register_defeated_unit` consulte >>. C'est precisement ce qui les a perimes : #10015-r3 a
    raccorde `RemoveUnitOperation.execute` DANS `_kill_unit_operation` (le slot 6 d'
    `IOperationProcessor` @`KillUnitOperation$$Execute+0xd34`), lequel appelle `add_component` --
    methode que le double n'avait pas. Les trois tests de cablage tombaient alors sur un
    `AttributeError` DANS LE MONTAGE, sans rien dire du port, qui etait juste.

    `Entity`/`State` suivent le moteur par construction : un etage raccorde en amont ne peut plus
    faire tomber ce fichier pour une raison qui n'est pas la sienne."""
    e = Entity(int(uid))
    for c in comps:
        e.add_component(c)
    return e


def _duo():
    """Le couple TUEUR (1) / VICTIME (2), sur un `State` nu."""
    st = State()
    tueur, victime = UnitComponent("A", True), UnitComponent("B", False)
    st.entities[1] = _ent(1, tueur)
    st.entities[2] = _ent(2, victime)
    return st, tueur


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


#: Les vecteurs d'evenement que `_kill_unit_operation` (et le retrait de plateau qu'il appelle)
#: publient, et dont ce fichier ne teste RIEN. Ils sont neutralises pour isoler les deux ecritures
#: de l'octet `inMelee`.
#: ⚠ **LA LISTE EST DERIVEE, PAS ECRITE** (#10026). Elle etait figee a CINQ noms ; #10015-r3 a
#: intercale `RemoveUnitOperation.execute` (slot 6 @`KillUnitOperation$$Execute+0xd34`), qui
#: publie un SIXIEME vecteur -- `On(0x25 = UnitRemoved)`, via `move_death.unit_removed_triggers`.
#: Une liste ecrite a la main ne peut pas montrer le vecteur qu'elle ignore : on neutralise donc
#: TOUT ce que `move_death` expose sous `*_triggers`, et on VERIFIE que les six connus y sont --
#: sans quoi un renommage viderait le montage en silence.
_VECTEURS_ATTENDUS = ("after_death_triggers", "pre_unit_death_2_triggers", "unit_death_triggers",
                      "unit_defeated_triggers", "post_unit_kill_triggers", "unit_removed_triggers")


def _kill_unit_operation_isole(monkeypatch, st, **kwargs):
    """Joue `_kill_unit_operation` en NEUTRALISANT tout ce qui n'est pas les deux ecritures d'
    `inMelee` (les vecteurs d'evenement, la garde revive, les trois `RemoveEffects`).

    Les substitutions portent sur les modules REELLEMENT resolus a l'appel : `move_death` et
    `revive` sont importes en forme MODULE **dans** la fonction, donc un `setattr` sur le module
    mord ; `_kill_unit_remove_effects` est une fonction de module de `damage.py`.

    ⚠ **`RemoveUnitOperation` N'EST PAS NEUTRALISE**, et c'est deliberatoire : il est desormais SUR
    le chemin natif de la mort, donc le neutraliser rendrait ce fichier vert sur un cablage qui
    n'existe plus. On le laisse muter (`alive`, flag `Removed`, `turn_defeated`) -- aucune de ces
    trois ecritures ne touche l'octet que ce fichier garde."""
    from engine.runner.operations import damage as DM
    from engine.runner.operations.triggers.dispatch import move_death
    from engine.runner.operations import revive as _revive
    vecteurs = [n for n in dir(move_death)
                if n.endswith("_triggers") and not n.startswith("_")
                and callable(getattr(move_death, n))]
    manquants = [n for n in _VECTEURS_ATTENDUS if n not in vecteurs]
    assert not manquants, (
        "vecteur(s) introuvable(s) dans `move_death` : %s -- le montage ne neutralise plus ce "
        "qu'il croit neutraliser (renommage ? deplacement ?)" % (manquants,))
    for nom in vecteurs:
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


def test_une_voie_sans_AttackRangeType_ecrit_False_et_non_None(monkeypatch):
    """`$$ForSteppable` (crush) et `$$ForDefault` (feuille DSL `Kill`) laissent `+0x3c` a ZERO ->
    `Nullable` VIDE -> `inMelee` FAUX cote natif. Les DEUX axes en decoulent, et ils sont
    DISTINCTS : l'INSCRIPTION tombe dans la liste `other`, et le MARQUEUR vaut **False**.

    ⚠ **RE-ETALONNE (#462-...-r6-r2) : ce test assertait `is None`, et son argument est REFUTE.**
    Il disait << le marqueur n'est PAS pose -- pour que ses lecteurs sachent qu'ils n'ont pas
    mesure, au lieu de lire un `False` fabrique >>. C'etait un argument de CONCEPTION (tri-etat),
    pas une lecture du natif, et trois sources le contredisent :

      1. **le decompile**, deja cite dans l'EN-TETE DE CE FICHIER (lignes 28-30) : le calcul
         `local_378[0] = (rangeType.GetValueOrDefault() == Melee(1)) & rangeType.HasValue` est
         **INCONDITIONNEL** -- aucune garde `if (HasValue)` ne l'entoure -- et l'ecriture
         `*(byte *)(victime.UnitComponent + 0x178) = local_378[0]` n'est gardee que par le
         null-check du composant. `HasValue` faux donne donc **0**, pas << rien >> ;
      2. **la mesure LIVE d'un crush** (`probe_462r4br6r2_crush_blast_radius_live.py`) :
         `decisionView.units[<crushe>].defeatedByMelee` vaut **`false`**, et non `null` -- le canal
         de capture voit bien un booleen POSE ;
      3. **la consequence observable** : avec `None`, `DawnBlade_HealAbility` retombait sur son
         approximation POSITIONNELLE, qui declare << melee >> apres un crush (le mover est SUR la
         tuile du crushe, distance 0) et faisait fire une reparation que le natif ne fait PAS
         (0 groupe `DawnBlade` cote natif, contre 1 et **+1997 PV** sur un vrai kill melee).

    Ce que le tri-etat garde ENCORE est teste juste en dessous : il n'a pas disparu, il a change de
    domaine -- il ne vit plus en SIMULATION, seulement au CHARGEMENT."""
    st, tueur = _duo()
    _kill_unit_operation_isole(monkeypatch, st)
    assert st.get_entity(2).get_component(UnitComponent).defeated_by_melee is False
    # L'axe INSCRIPTION est INCHANGE : `register_defeated_unit(in_melee=None)` et `in_melee=False`
    # prennent la MEME branche native (`if ((char)inMelee == '\0')`), donc la liste `other`.
    assert tueur.defeated_units_other == [2] and tueur.defeated_units_melee == []


def test_le_tri_etat_survit_au_CHARGEMENT_donc_le_repli_n_est_pas_MORT(monkeypatch):
    """Contre-partie du test ci-dessus, et reponse a << une branche morte qui se donne l'air d'un
    repli >>. Depuis que `_kill_unit_operation` ecrit le marqueur INCONDITIONNELLEMENT, `None` ne
    peut plus sortir d'une SIMULATION -- mais il sort encore d'un etat CHARGE, et le repli
    positionnel de `triggers/base.py::defeated_by_melee` garde donc un vecteur d'entree REEL.

    Le vecteur est LU dans `snapshot._load_death_sources` : la boucle `continue` sur toute unite
    VIVANTE **et** sur toute unite morte dont `killerId` est absent (<< tueur non imputable -> le
    natif ne compte rien non plus >>). Une victime chargee sans tueur imputable n'a donc AUCUNE
    ecriture du marqueur, et reste a `None`.

    Sans ce test, la suppression du repli passerait pour un nettoyage sans consequence."""
    from engine.runner import snapshot as SNAP
    st = State()
    st.entities[7] = _ent(7, UnitComponent("victime-sans-tueur", False))
    # Une unite MORTE dont `decisionView` ne publie AUCUN `killerId` -- la forme exacte que le
    # seeding ecarte par `continue`.
    SNAP._load_death_sources(st, {"units": [{"id": 7, "alive": False, "killerId": None,
                                             "defeatedByMelee": True}]})
    assert st.get_entity(7).get_component(UnitComponent).defeated_by_melee is None, (
        "le seeding a pose le marqueur sur une victime SANS tueur imputable -- le repli de "
        "`defeated_by_melee` n'aurait alors plus aucun vecteur, et il faudrait le retirer")


def test_possession_lit_le_marqueur_et_retombe_sur_l_adjacence_sans_lui(monkeypatch):
    """#955-r1 (volet marqueur) -- `If(NOT IsDefeatedByMeleeAttack(Target), Spawn(unitId_2),
    Spawn(unitId))`. Le port approximait le marqueur POSITIONNELLEMENT ; il le LIT desormais quand
    il est mesure, et ne retombe sur l'approximation que sur `None`.

    Le montage neutralise `_is_ranged_position` en le forcant a VRAI : si le marqueur etait ignore,
    un kill de MELEE serait classe << a distance >> et donnerait le mauvais summon.

    ⚠ **LE POINT DE MORSURE A BOUGE (#462-...-r6-r2), et il fallait le suivre.** La lecture du
    marqueur + son repli sont desormais un FOYER UNIQUE, `triggers/base.py::defeated_by_melee`,
    partage avec `DawnBladeHealAbility` (2e site). `possession.py` n'importe donc plus
    `_is_ranged_position` : patcher `P._is_ranged_position` levait `AttributeError`. On patche le
    module ou le nom est REELLEMENT resolu -- `base`, qui l'appelle depuis ses propres globals,
    donc la substitution MORD. C'est le piege FORME A du `CLAUDE.md`, pris dans le sens ou une
    factorisation deplace l'endroit qu'un patch doit viser."""
    from engine.runner.operations.triggers import base as BASE
    from engine.runner.operations.triggers.loki import possession as P

    monkeypatch.setattr(BASE, "_is_ranged_position", lambda *a, **k: True)
    victime = UnitComponent("B", False)
    st = State()
    st.entities[1] = _ent(1, UnitComponent("A", True))
    st.entities[2] = _ent(2, victime)
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
