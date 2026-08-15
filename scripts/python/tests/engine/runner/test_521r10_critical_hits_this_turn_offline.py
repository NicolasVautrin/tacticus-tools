"""#521-r10 / #521-r4 -- le compteur de CRITS PAR TOUR et les deux classes de `1244`.

GARDE OFFLINE, six etages. Chacun a ete VU ROUGE par mutation avant d'etre livre (une garde
jamais vue rouge ne garde rien) :

  1. `test_..._substrat_+0x54`         -- ecriture / reset / non-contamination des voisins ;
  2. `test_..._lecteur_et_noeud_dsl`   -- `unit_critical_hits_this_turn` + `CriticalHitsThisTurn`,
                                          et la cle est LIVE (le vice qui rendrait le gate muet) ;
  3. `test_..._cablage_du_chokepoint`  -- le 4e argument natif est THREADE (derive de l'AST) ;
  4. `test_..._arbre_remove_le_seuil`  -- le gate `>= nrOfHits_2` des DEUX cotes ;
  5. `test_..._config_lue_de_1148`     -- `1244` n'a AUCUNE config propre ;
  6. `test_..._registre_les_deux_volets` -- livrer la POSE sans le RETRAIT ferait cumuler.

⚠ Ce que ce fichier NE garde PAS : la MAGNITUDE du crit-chance. Elle vit dans l'etage [4] de
l'ACTIVE 1148 (`runner/abilities/blacklegion.py`), deja porte et hors de cette tranche.
"""
from __future__ import annotations

import ast
import json
import os

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/triggers/loki/daemonic_ordnance.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/abilities/blacklegion.py",
        "data/seed-bc.json",
    ),
    "build": True,            # les enums et le gameconfig sont per-build
    "toujours": False,
    "raison": ("garde le compteur `ActorStatisticsComponent+0x54` (ecriture, reset, lecture, "
               "noeud DSL, cablage du chokepoint) et le port des DEUX classes natives de 1244 : "
               "le seuil `nrOfHits_2`, la config lue de l'ACTIVE 1148, et l'inscription CONJOINTE "
               "des volets POSE et RETRAIT"),
}

import pytest                                                                    # noqa: E402

from engine.dsl.base import Const                                                # noqa: E402
from engine.dsl.effects import ExecutionContext                                  # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                       # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402
from engine.entities.effect_type import EffectType                               # noqa: E402
from engine.entities.effects_state import EffectsState                           # noqa: E402
from engine.entities.formulas import CriticalHitsThisTurn                        # noqa: E402
from engine.entities.selectors.accessors import Owner                            # noqa: E402
from engine.entities.stats import StatType                                       # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType          # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state       # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,           # noqa: E402
                                      PositionComponent, UnitComponent,
                                      register_attack_made,
                                      reset_units_attacked_this_turn,
                                      unit_attacks_made_this_turn,
                                      unit_critical_hits_this_turn,
                                      unit_total_attacks_made,
                                      unit_turns_with_attacks_made)
from engine.runner.operations.triggers.loki import daemonic_ordnance as DO       # noqa: E402
from engine.runner.state import State                                            # noqa: E402

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))                       # .../scripts/python
_ROOT = os.path.dirname(os.path.dirname(_PY))           # racine du depot
_DAMAGE = os.path.join(_PY, "engine", "runner", "operations", "damage.py")

DO_ACTIVE = ActiveAbilityType.DaemonicOrdnance.name                    # 0x47c = 1148
DO_EFFECT = int(EffectType.DaemonicOrdnance_ExtraCritChance)           # 0x524 = 1316


def _state(n: int = 4) -> State:
    st = State()
    st.effects = EffectsState()          # `AddEffectOperation` ne materialise RIEN sans elle
    for i in range(1, n + 1):
        e = st.add_entity(i)
        e.add_component(UnitComponent(visual_id="blackForgefiend", alive=True))
        e.add_component(OwnerComponent(team=1 if i == 1 else 2, player=1 if i == 1 else 2))
        e.add_component(PositionComponent(col=i, row=1))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    return st


# ------------------------------- [1] LE SUBSTRAT `+0x54` --------------------------------------
def test_521r10_substrat_ecriture_reset_et_voisins():
    """`ActorStatisticsComponent$$RegisterAttackMade` fait `this[0x54] += totalCrits` ;
    `...$$ResetUnitsAttackedThisTurn` fait `this[0x54] = 0`.

    Les VOISINS sont dans le meme test a dessein : le decompile ecrit `+0x20` (cumul de bataille),
    `+0x54` et `+0x24` (per-tour) dans le MEME bloc, et seuls les DEUX derniers sont effaces par le
    reset (`*(long long*)(this + 0x24) = 0` ne couvre PAS `+0x20`). Un port qui rangerait le
    compteur de crits du mauvais cote du reset serait INVISIBLE sans cette confrontation."""
    st = _state()
    assert unit_critical_hits_this_turn(st, 1) == 0

    register_attack_made(st, 1, 2, total_crits=2)
    register_attack_made(st, 1, 3, total_crits=0)      # une attaque SANS crit : compteur inchange
    register_attack_made(st, 1, 2, total_crits=1)      # MEME cible : `+0x54` avance quand meme
    assert unit_critical_hits_this_turn(st, 1) == 3
    assert unit_attacks_made_this_turn(st, 1) == 3     # `+0x24` -- trois appels, trois increments
    assert unit_total_attacks_made(st, 1) == 3         # `+0x20`
    assert unit_turns_with_attacks_made(st, 1) == 1    # `+0x30` -- UNE fois par tour

    reset_units_attacked_this_turn(st, 1)
    assert unit_critical_hits_this_turn(st, 1) == 0, "`this[0x54] = 0` au turn-start"
    assert unit_attacks_made_this_turn(st, 1) == 0
    assert unit_total_attacks_made(st, 1) == 3, "`+0x20` est un CUMUL DE BATAILLE, aucun reset"
    assert unit_turns_with_attacks_made(st, 1) == 1, "`+0x30` compte des TOURS, aucun reset"


def test_521r10_defaut_par_omission_est_zero_jamais_un_crit_invente():
    """L'appelant qui ne mesure pas les crits passe `0` (defaut). Un port qui compterait `1` par
    attaque -- l'erreur naturelle quand on confond `totalCrits` avec `did_crit` -- rendrait le gate
    de `RemoveCritChance` vrai des la premiere attaque du tour."""
    st = _state()
    for t in (2, 3, 4):
        register_attack_made(st, 1, t)                 # aucun `total_crits`
    assert unit_critical_hits_this_turn(st, 1) == 0
    assert unit_attacks_made_this_turn(st, 1) == 3


def test_521r10_lecteur_sur_entite_sans_composant():
    """`unit_critical_hits_this_turn` rend 0 sur une entite non-unite / inconnue -- le rabattement
    documente de la branche qui LEVE cote natif."""
    st = _state()
    assert unit_critical_hits_this_turn(st, 999) == 0


# ---------------------- [2] LE LECTEUR DSL, ET SA CLE EST **LIVE** ----------------------------
def test_521r10_noeud_dsl_lit_le_compteur():
    """`CriticalHitsThisTurn(Owner)` = `CriticalHitsThisTurnFormula$$Calculate` sur le porteur."""
    st = _state()
    ent = entities_from_state(st, 1, 2)
    assert CriticalHitsThisTurn(Owner()).calculate(ent) == 0
    register_attack_made(st, 1, 2, total_crits=2)
    assert CriticalHitsThisTurn(Owner()).calculate(ent) == 2


def test_521r10_la_cle_est_live_pas_figee_au_seed():
    """LE VICE QUE CE TEST GARDE : `criticalHitsThisTurn` doit etre dans `_LIVE_KEYS`.

    L'increment natif PRECEDE l'emission du vecteur qui fait relire le nombre
    (`RegisterAttackOperation` pendant la behaviour, `On(0xe = UnitPostAbility)` a la cloture). Un
    dict d'entite FIGE a sa construction rendrait la valeur d'AVANT l'attaque -- donc `0` au tour ou
    les crits tombent, et le gate de `RemoveCritChance` ne matcherait JAMAIS.

    On construit le contexte AVANT la mutation, exactement comme le fait le runner."""
    st = _state()
    ent = entities_from_state(st, 1, 2)                # <- contexte construit AVANT
    register_attack_made(st, 1, 2, total_crits=3)      # <- mutation POSTERIEURE a la capture
    assert CriticalHitsThisTurn(Owner()).calculate(ent) == 3, \
        "cle figee au seed -> le gate de 1244 serait structurellement muet"

    from engine.runner.abilities.behaviours.context import _LIVE_KEYS
    assert "criticalHitsThisTurn" in _LIVE_KEYS


# ------------------- [3] LE CABLAGE DU CHOKEPOINT (derive de l'AST) ---------------------------
def test_521r10_le_chokepoint_threade_le_4e_argument():
    """`_apply_damage_pipeline` doit passer `total_crits` a `register_attack_made`, et le tirer de
    `hits_result["crits"]`.

    DERIVE de l'arbre, jamais recopie : un appel a 3 arguments repasserait au defaut `0` en
    SILENCE, et le compteur resterait a zero pour toujours -- exactement la forme de degradation
    permissive que cette tranche existe pour fermer."""
    with open(_DAMAGE, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    appels = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "register_attack_made"]
    assert appels, "aucun appel a `register_attack_made` dans le chokepoint -- balayage VIDE"
    for call in appels:
        kw = {k.arg for k in call.keywords}
        assert "total_crits" in kw or len(call.args) >= 4, \
            "`register_attack_made` appele SANS `total_crits` -> le compteur reste a 0 en silence"
        src = ast.dump(call)
        assert "'crits'" in src, "`total_crits` ne vient pas de `hits_result['crits']`"


# --------------------- [4] L'ARBRE `RemoveCritChance` ET SON SEUIL ----------------------------
def _pose_le_marqueur(st) -> list:
    """Joue l'arbre `AddCritChance` (`AddStaticStatModifierEffectToOwner(1316, 9, Direct(0))`)."""
    ectx = ExecutionContext(state=st, rng=st.rng)
    DO.daemonic_ordnance_add_crit_chance_tree().execute(entities_from_state(st, 1, 1), ectx)
    return [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]


def _porte_le_marqueur(st, uid: int = 1) -> bool:
    return any(e.effect_type == DO_EFFECT and not e.consumed
               for e in st.effects.by_unit.get(int(uid), []))


def test_521r4_pose_le_marqueur_a_magnitude_zero():
    """`Direct(0)` : l'effet 1316 est un MARQUEUR. S'il portait `extraCritChance`, le bonus serait
    compte DEUX fois (l'etage [4] de l'active 1148 fait deja l'`AddOrUpdate`)."""
    st = _state()
    assert not _porte_le_marqueur(st)
    emis = _pose_le_marqueur(st)
    assert _porte_le_marqueur(st), "le marqueur 1316 doit etre pose"
    assert len(emis) == 1
    # `<DSLFormulas+0x18> = Direct(0)` -- la CONTRIBUTION posee sur CRIT_CHANCE est NULLE. C'est le
    # montant que la feuille passe a `apply_change_stat`, donc ce que l'unite gagne.
    assert emis[0]["amount"] == 0, "magnitude non nulle -> le bonus serait compte DEUX fois"
    assert emis[0]["stat"] == int(StatType.CRIT_CHANCE)
    assert emis[0]["effect_type"] == DO_EFFECT
    # et l'entite-effet materialisee porte bien cette valeur (canal que relit l'etage [4] de 1148).
    eff = [e for e in st.effects.by_unit.get(1, []) if e.effect_type == DO_EFFECT][0]
    assert int(getattr(eff, "value", 0) or 0) == 0


@pytest.mark.parametrize("crits,doit_partir", [
    (0, False), (1, False), (2, False),           # sous le seuil : le marqueur RESTE
    (3, True), (4, True), (99, True),             # `>=` : au seuil ET au-dela
])
def test_521r4_le_seuil_du_retrait(crits, doit_partir):
    """`If(AmountIsEqualOrGreater(CriticalHitsThisTurn(Owner), Direct(GetHits2())), RemoveEffect)`.

    `nrOfHits_2` vaut 3 sur la config de l'ACTIVE 1148. Les DEUX cotes du seuil sont exerces : un
    test qui ne verrait que la branche « ca part » passerait avec un gate cable a l'envers."""
    st = _state()
    _pose_le_marqueur(st)
    if crits:
        register_attack_made(st, 1, 2, total_crits=crits)
    ectx = ExecutionContext(state=st, rng=st.rng)
    DO.daemonic_ordnance_remove_crit_chance_tree().execute(entities_from_state(st, 1, 1), ectx)
    assert _porte_le_marqueur(st) is (not doit_partir)


def test_521r4_le_retrait_ne_touche_pas_un_porteur_sans_marqueur():
    """`RemoveEffect` sur une unite qui n'a pas 1316 : no-op, aucune exception."""
    st = _state()
    register_attack_made(st, 1, 2, total_crits=5)
    ectx = ExecutionContext(state=st, rng=st.rng)
    DO.daemonic_ordnance_remove_crit_chance_tree().execute(entities_from_state(st, 1, 1), ectx)
    assert not _porte_le_marqueur(st)


# ------------------- [5] LA CONFIG LUE EST CELLE DE L'ACTIVE 1148 -----------------------------
def test_521r4_1244_n_a_aucune_config_propre():
    """MEME mesure que pour `1316` (#521-r7) : ni gameconfig, ni `BattleConfiguration.Abilities`.
    La seule configuration atteignable par `GetHits2` est donc celle de l'ACTIVE 1148."""
    import gameconfig as GC
    assert GC.ability(TriggeredAbilityType.DaemonicOrdnance_Crit.name) in (None, {}), \
        "1244 aurait une config propre -- la lecture `config de l'ACTIVE` serait a refaire"
    with open(os.path.join(_ROOT, "data", "seed-bc.json"), encoding="utf-8") as fh:
        ab = (json.load(fh).get("Abilities") or {})
    for sec in ("ActiveAbilities", "PassiveAbilities"):
        assert TriggeredAbilityType.DaemonicOrdnance_Crit.name not in (ab.get(sec) or {})
    assert DO_ACTIVE in (ab.get("ActiveAbilities") or {}), "l'ACTIVE 1148, elle, est dans la BC"
    # `GetNumberConstant(config, 0x32 = nrOfHits_2)` -- la constante EXISTE sur l'active, et
    # l'`ExecuteBehaviour` de 1148 ne la lit PAS (il lit `nrOfHits`) : signature d'une constante
    # posee POUR le helper.
    assert DO.daemonic_ordnance_hits2() == 3
    assert int(AbilityConstantType.nrOfHits_2) == 0x32


# ------------------- [6] LE REGISTRE PORTE LES **DEUX** VOLETS --------------------------------
def test_521r4_registre_les_deux_volets_ensemble():
    """LE VICE QUE CE TEST GARDE : livrer la POSE sans le RETRAIT ferait CUMULER le crit-chance
    indefiniment (l'etage [4] de 1148 rafraichit a `(nbUsages + 1) x extraCritChance` a chaque
    cast, et rien ne retirerait jamais le marqueur). Les deux classes partent ensemble."""
    from engine.runner.operations.triggers.dispatch.registry import (
        PASSIVE_HELPER_ABILITY_TRIGGERS as P)
    classes = P.get(DO_ACTIVE) or []
    noms = [c.__name__ for c in classes]
    assert "DaemonicOrdnanceAddCritChanceAbility" in noms
    assert "DaemonicOrdnanceRemoveCritChanceAbility" in noms, \
        "la POSE sans le RETRAIT = crit-chance cumulatif sans borne"
    # Les DEUX portent le MEME `TriggeredAbilityType` (un id, deux classes) et des vecteurs
    # DISTINCTS -- si les deux ecoutaient le meme event, l'une des deux serait morte.
    assert {int(c.TRIGGERED_ABILITY_ID) for c in classes} == {1244}
    assert {int(c.event_id) for c in classes} == {int(EventTriggerType.AbilityInit),
                                                  int(EventTriggerType.UnitPostAbility)}


@pytest.mark.parametrize("membre,attendu,ou", [
    (int(ActiveAbilityType.DaemonicOrdnance), 1148, "cle du dict `GetPassiveHelperAbility`"),
    (int(TriggeredAbilityType.DaemonicOrdnance_Crit), 1244, "valeur du meme dict (`0x47c -> 0x4dc`)"),
    (int(EffectType.DaemonicOrdnance_ExtraCritChance), 1316,
     "`AddStaticStatModifierEffectToOwner(this, 0x524, ...)`"),
    (int(StatType.CRIT_CHANCE), 9, "2e argument du meme appel (`0x9`)"),
    (int(EventTriggerType.UnitPostAbility), 14, "`DSLTriggers$$On(this, 0xe, 1)`"),
    (int(EventTriggerType.AbilityInit), 33, "`<DSLTriggers+0x30>` (`0x21`)"),
])
def test_521r4_ordinaux_ecrits_au_site(membre, attendu, ou):
    """Fige l'ordinal MESURE a la conversion. ⚠ `0x524` est un `EffectType` ICI mais un
    `TriggeredAbilityType` ailleurs (`CalibaniteGreatsword_NormalAttackAdditionalDamage`), et
    `0x4dc` est un `TriggeredAbilityType` ICI mais un `EffectType` ailleurs (`Contaminated`) : le
    NOM est le seul canal ou la confusion serait visible."""
    assert membre == attendu, "ordinal glisse -- lu au site %s" % (ou,)


def test_521r4_les_deux_confusions_d_enum_sont_reelles():
    """Le piege n'est pas theorique -- il est MESURE dans les deux sens, sur les deux ordinaux que
    ce module ecrit. Assertionner son propre non-vide : si les ordinaux devenaient invalides dans
    l'autre enum, ce test passerait pour vert sans rien montrer."""
    assert TriggeredAbilityType(1316).name == \
        "CalibaniteGreatsword_NormalAttackAdditionalDamage"    # meme dict, AUTRE entree
    assert EffectType(1316).name == "DaemonicOrdnance_ExtraCritChance"
    assert EffectType(1244).name == "Contaminated"
    assert TriggeredAbilityType(1244).name == "DaemonicOrdnance_Crit"
