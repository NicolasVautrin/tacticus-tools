"""#965 -- garde OFFLINE du passif `RefusalToBeOutdone` (1441, `emperExultant`) et des deux noeuds
DSL neufs qu'il a exiges.

Ce fichier GARDE ce que la RE a etabli (`docs/rl/case-965-whispering-web-refusal-to-be-outdone.md`) ;
il ne le re-decouvre pas. Chaque etage cite le symbole natif dont il fige la lecture.

Les cinq etages, et pourquoi chacun existe :
  0. les ORDINAUX ecrits au site (le cran que `probe_313` ne tient pas : il compare le mirror au
     build, donc il redevient vert apres un renumerotage alors que la valeur du site a change) ;
  1. `GetAllPersistentDataCombined` = une SOMME qui EXCLUT -- sans l'exclusion, le compteur d'amis
     Chaos entrerait dans l'Outrage ;
  2. `AddOrUpdateStaticStatModifierEffect` = un `If` GARDE, et un remove-PUIS-add quand il ouvre ;
  3. la STRUCTURE des trois arbres (les usines sont inspectables exprès) ;
  4. le cablage au registre, et l'ABSENCE assumee de la branche morte `UnitTransformed`.
"""
from __future__ import annotations

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.effect_type import EffectType
from engine.entities.stats import StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.components import PersistentDataComponent
from engine.runner.operations.triggers.loki import refusal_to_be_outdone as RTBO


# --- Etage 0 : les ordinaux ECRITS AU SITE ------------------------------------------------------
# Mesures a la conversion (#965). `probe_313` garde la bijection mirror<->build ; ce cran-ci garde
# la valeur que le PORT ecrit, qui ne bouge pas toute seule quand le build renumerote.
def test_etage0_ordinaux_du_site():
    assert int(TriggeredAbilityType.RefusalToBeOutdone) == 1441          # 0x5a1
    assert int(EffectType.RefusalToBeOutdone_ExtraDamage) == 1430        # 0x596
    assert int(EffectType.RefusalToBeOutdone_ExtraCritDamage) == 1511    # 0x5e7
    assert int(AbilityVariableType.extraDmgPct) == 10                    # 0xa
    assert int(AbilityVariableType.extraCritDmg) == 66                   # 0x42
    assert int(UnitTrait.Hero) == 16                                     # 0x10
    assert int(UnitTrait.Chaos) == 2026                                  # 0x7ea
    assert int(StatType.ATTACK) == 0                                     # StatType.Attack
    assert int(StatType.CRIT_DAMAGE) == 10                               # StatType.CriticalDamage
    assert int(EventTriggerType.AttackHit) == 8                          # 0x8
    assert int(EventTriggerType.TurnEnd) == 23                           # 0x17
    assert int(EventTriggerType.NormalAttack) == 38                      # 0x26
    assert int(EventTriggerType.UnitTransformed) == 75                   # 0x4b
    # L'`AbilityOrEffect` du sac EST le `TriggeredAbilityType` de la classe qui ECRIT.
    assert RTBO.REFUSAL_TO_BE_OUTDONE == 1441


# --- Etage 1 : `GetAllPersistentDataCombined$$SumAbilityData` -----------------------------------
def _sac(entries: dict) -> PersistentDataComponent:
    c = PersistentDataComponent()
    for k, v in entries.items():
        c.persist_data(k, v)
    return c


def test_etage1_somme_les_entiers_de_la_bonne_ability():
    """`SumAbilityData` somme les valeurs ENTIERES rangees sous `abilityId`, et RIEN d'autre."""
    aid = RTBO.REFUSAL_TO_BE_OUTDONE
    c = _sac({(aid, 11): 300, (aid, 12): 120, (999, 13): 5000})
    assert c.sum_ability_data(aid) == 420          # l'autre ability n'entre pas
    assert c.sum_ability_data(999) == 5000


def test_etage1_l_exclusion_est_load_bearing():
    """Sans `excludedKeys`, le COMPTEUR d'amis Chaos serait somme dans l'Outrage.

    C'est la raison d'etre du tableau a un element alloue par `...$$GetCurrentExtraDmg` : le test
    exige que les deux comptes DIFFERENT, sans quoi il ne prouverait rien."""
    aid = RTBO.REFUSAL_TO_BE_OUTDONE
    c = _sac({(aid, 11): 300, (aid, 12): 120, (aid, RTBO.CHAOS_FRIENDS_KEY): 2})
    sans = c.sum_ability_data(aid)
    avec = c.sum_ability_data(aid, (RTBO.CHAOS_FRIENDS_KEY,))
    assert sans == 422 and avec == 420
    assert sans != avec, "l'exclusion doit MORDRE, sinon cet etage est vide"


def test_etage1_saute_les_valeurs_non_entieres():
    """Le natif teste la classe de l'objet boxe et SAUTE ce qui n'est pas un `Int32`. Cote port, la
    variante LISTE range ses `list` dans le MEME sac -- les compter leverait un TypeError ou, pire,
    fausserait la somme."""
    aid = RTBO.REFUSAL_TO_BE_OUTDONE
    c = PersistentDataComponent()
    c.persist_data((aid, 11), 300)
    c.persist_data_list((aid, "liste"), [1, 2, 3])
    c.persist_data((aid, "texte"), "nope")
    assert c.sum_ability_data(aid) == 300


def test_etage1_cle_absente_rend_zero():
    """`TryGetValue(abilityId)` en echec -> 0. Le tri-etat ne se distingue pas d'un sac vide, et
    c'est FIDELE : le natif rend 0 dans les deux cas."""
    assert PersistentDataComponent().sum_ability_data(RTBO.REFUSAL_TO_BE_OUTDONE) == 0


# --- Etage 2 : la garde d'idempotence d'`AddOrUpdateStaticStatModifierEffect` --------------------
def test_etage2_le_noeud_est_un_if_garde_par_l_ecart_de_montant():
    """`If( NOT AmountIsEqual(amount, CurrentStatModifierAmount(...)), Remove & AddStatic )`.

    On ne monte pas de bataille ici : on verifie que le MIRROR porte bien la garde, par sa
    docstring citee et par le fait qu'il expose les memes parametres que la feuille `Add` qu'il
    enveloppe. La confrontation du comportement est live (cf. rapport de tranche)."""
    from engine.runner.abilities.behaviours.effects import (AddOrUpdateStaticStatModifierEffect,
                                                            AddStaticStatModifierEffect)
    import inspect
    p_upd = list(inspect.signature(AddOrUpdateStaticStatModifierEffect.__init__).parameters)
    p_add = list(inspect.signature(AddStaticStatModifierEffect.__init__).parameters)
    assert p_upd == p_add, "le noeud OrUpdate enveloppe la feuille Add : memes parametres"
    doc = AddOrUpdateStaticStatModifierEffect.__doc__ or ""
    assert "AmountIsEqual" in doc and "op_LogicalNot" in doc
    # Le mislabel ICF doit rester ECRIT : c'est ce qui empeche un relecteur de « corriger » le nom.
    assert "PerformAIMovementBehaviour" in doc


# --- Etage 3 : la STRUCTURE des trois arbres ----------------------------------------------------
def test_etage3_arbre_attack_stat():
    """`GetUpdateAttackStatBehaviour` = `AddOrUpdate(Owner, 0x596, StatType.Attack, PercentageOf(...))`."""
    n = RTBO.update_attack_stat_tree()
    assert n.effect_type == int(EffectType.RefusalToBeOutdone_ExtraDamage)
    assert n.stat_type == int(StatType.ATTACK)
    # La BASE du pourcentage est la somme EXCLUANT la cle compteur -- l'etage 1 a montre que
    # l'exclusion change le resultat, celui-ci montre qu'elle est bien CABLEE.
    base = n.amount.base
    assert type(base).__name__ == "GetAllPersistentDataCombined"
    assert base.excluded_keys == (RTBO.CHAOS_FRIENDS_KEY,)
    assert base.ability_or_effect == RTBO.REFUSAL_TO_BE_OUTDONE


def test_etage3_arbre_crit_stat():
    """`GetUpdateCritStatBehaviour` = `AddOrUpdate(Owner, 0x5e7, StatType.CriticalDamage,
    Multiply(GetPersistentData(<cle compteur>), ConfigVar(extraCritDmg)))` -- donc `extraCritDmg`
    PAR AMI CHAOS, pas un forfait."""
    n = RTBO.update_crit_stat_tree()
    assert n.effect_type == int(EffectType.RefusalToBeOutdone_ExtraCritDamage)
    assert n.stat_type == int(StatType.CRIT_DAMAGE)
    assert type(n.amount).__name__ == "Multiply"
    gp = n.amount.a
    assert type(gp).__name__ == "GetPersistentData"
    assert gp.data_key == RTBO.CHAOS_FRIENDS_KEY      # la cle COMPTEUR, pas une cle per-ami


def test_etage3_arbre_reset():
    """`ClearAllPersistentData` en TETE, puis les DEUX `RemoveEffect` -- l'ordre du `op_Addition`."""
    nodes = RTBO.reset_tree()
    assert [type(n).__name__ for n in nodes] == \
        ["ClearAllPersistentData", "RemoveEffect", "RemoveEffect"]
    assert nodes[0].ability_or_effect == RTBO.REFUSAL_TO_BE_OUTDONE
    assert {nodes[1].effect_type, nodes[2].effect_type} == {
        int(EffectType.RefusalToBeOutdone_ExtraDamage),
        int(EffectType.RefusalToBeOutdone_ExtraCritDamage)}


def test_etage3_la_cle_compteur_ne_collisionne_pas_avec_un_entityid():
    """Les cles per-ami sont des `EntityId` (entiers) ; la cle compteur DOIT etre d'un autre type,
    sinon un ami dont l'id vaudrait cette valeur ecraserait le compteur."""
    assert isinstance(RTBO.CHAOS_FRIENDS_KEY, str)


# --- Etage 4 : le cablage, et l'ABSENCE assumee -------------------------------------------------
def test_etage4_registre():
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    classes = ABILITY_TRIGGERS.get("RefusalToBeOutdone")
    assert classes, "le passif doit etre cable sous son nom gameconfig"
    events = sorted(c.event_id for c in classes)
    assert events == [int(EventTriggerType.AttackHit),
                      int(EventTriggerType.TurnEnd),
                      int(EventTriggerType.NormalAttack)]
    assert all(c.TRIGGERED_ABILITY_ID == RTBO.REFUSAL_TO_BE_OUTDONE for c in classes)


def test_etage4_la_branche_unittransformed_n_est_pas_cablee_et_c_est_MESURE():
    """`On(0x4b = UnitTransformed) & OwnerIsTarget` est un vecteur MORT cote port : aucun emetteur.

    Ce test garde les DEUX faces du constat -- (a) la branche n'est pas cablee, (b) la raison tient
    toujours. Si un emetteur `UnitTransformed` apparait un jour, (b) rougit et la branche doit
    entrer (residu #965-r1). Un test qui ne garderait que (a) se contenterait d'entériner un trou."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    classes = ABILITY_TRIGGERS["RefusalToBeOutdone"]
    assert int(EventTriggerType.UnitTransformed) not in {c.event_id for c in classes}

    # (b) la raison : aucun site n'EMET cet event. On derive le fait du code, on ne le recopie pas.
    import pathlib
    racine = pathlib.Path(RTBO.__file__).resolve().parents[5]      # .../scripts/python
    emetteurs = []
    for p in (racine / "engine").rglob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        # un EMETTEUR construit un TriggerEvent sur cet event ; le mirror d'enum ne compte pas.
        if "TriggerEvent(EventTriggerType.UnitTransformed" in txt:
            emetteurs.append(p.name)
    assert emetteurs == [], (
        "un emetteur UnitTransformed existe desormais -> cabler la branche B (residu #965-r1) : "
        + ", ".join(emetteurs))


if __name__ == "__main__":                      # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
