"""#963-r5 -- le seed d'owner-effect sait desormais ecrire `bonded`, donc un `AddBondEffect` pose a
l'INIT est portable. Garde OFFLINE du canal et de ses DEUX consequences chiffrees.

CE QUE CE FICHIER GARDE, et qu'aucun test d'appartenance a un registre ne verrait :

  * le 5e argument natif est RESOLU, pas devine -- `bondedEntity = Parent(Owner, root: 0)` passe par
    le foyer deja porte `runner/components.py::parent_of` (mirror d'`IdunBattle.Entities.
    UnitExtensions$$GetParent`), et un selecteur INCONNU du registre pose SANS lien plutot que de
    fabriquer une valeur ;
  * la DEGRADATION est celle du natif, lue verbatim dans `IdunBattle.Entities.Behaviours.
    AddEffectBehaviour$$GetEffectBuilder` : `method = (bondedEntityId != 0) ? <builder de BOND> :
    <builder ORDINAIRE>`. Un parent introuvable ne fait PAS echouer la pose -- refuser de poser
    serait RESTRICTIF, et ecrire `0` mentirait (l'entite 0 existe) ;
  * les DEUX consequences que #963-r5 opposait a l'inscription, et qui avaient la MEME cause
    (l'absence de `bonded`) : (1) l'instance sans lien satisfait le gate `NOT HasEffect(Owner,
    0x424)` du `CreateBehaviour` de combat et BLOQUE la pose correcte ; (2) `BOND_REMOVAL_GATES`
    gate (a) lit `BaseEffect.bonded`, donc le retrait a la mort du bonde ne mord pas. Les etages 5
    et 6 mesurent que les deux sont levees ;
  * la RETRO-COMPATIBILITE : `_materialize_owner_effect` sans `bonded` ni `source` doit rendre
    exactement ce qu'il rendait avant -- tous les call-sites anterieurs en dependent.

REGIME SEPARANT. Ces etages construisent l'etat SANS capture d'effets, c'est-a-dire le seul regime
ou le filet mord : sur le chemin live le natif a deja pose l'instance (avec son `bondedEntityId`
publie par `readBondLink`) et le gate `has_effect` du seed rend un no-op exact.
"""
from __future__ import annotations

import inspect

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.unit_context import UnitContext
from engine.runner.components import (HealthComponent, OwnerComponent, StatsComponent,
                                      UnitComponent)
from engine.runner.operations.spawn import _materialize_owner_effect, _seed_ability_owner_effects
from engine.runner.state import State

#: Ce que ce fichier LIT, donc ce qui doit changer pour qu'il puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/triggers/bond_removal.py",
        "data/gameconfig.json",
    ),
    "build": False,          # ne lit ni le binaire ni `data/symbols/**`
    "toujours": False,
    "raison": "le registre `ABILITY_INIT_OWNER_BOND_EFFECTS`, son unique consommateur "
              "(`_seed_ability_owner_effects`), le foyer du selecteur (`parent_of`), le gate de "
              "retrait qui lit `BaseEffect.bonded`, et le kit gameconfig du porteur.",
}

CARRIER = "adeptSmnGeminaeSuperia"     # `passiveAbilities = ["Lifewards"]`
SUMMONER = "adeptCelestine"            # le PARENT -- ce que `Parent(Owner)` doit rendre
WITNESS = "tauCrisis"                  # ne porte pas `Lifewards` -> TEMOIN
BOND_EFFECT = EffectType.Lifewards_BondEffect.name       # 0x424 = 1060


def _unit(state, vis, team=1, parent_id=None, passive_level=50):
    """Une entite MINIMALE, volontairement SANS `EffectsState` prealable : c'est le regime
    << etat construit sans capture d'effets >>, le seul ou le filet est separant."""
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vis, alive=True, parent_id=parent_id))
    e.add_component(OwnerComponent(team=team))
    ctx = UnitContext(entity_id=e.id, visual_id=vis)
    ctx.traits = []
    ctx.passive_ability_level = passive_level
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=9000, hp_max=9000))
    return e.id


def _inst(state, uid, name=BOND_EFFECT):
    for eff in (state.effects.by_unit.get(int(uid), []) if state.effects is not None else []):
        if eff.name == name:
            return eff
    return None


# ------------------------------------------------------- [1] le registre, sa forme, son selecteur
def test_1_le_registre_porte_l_effet_et_le_SELECTEUR_du_5e_argument():
    from engine.entities.effects.factory import (ABILITY_INIT_OWNER_BOND_EFFECTS,
                                                 BOND_PARENT_OF_OWNER,
                                                 BOND_SELECTORS_RESOLVABLE,
                                                 get_owner_bond_effects_added_on_ability_init)
    assert ABILITY_INIT_OWNER_BOND_EFFECTS["Lifewards"] == [(BOND_EFFECT, BOND_PARENT_OF_OWNER)]
    assert get_owner_bond_effects_added_on_ability_init("Lifewards") == [(BOND_EFFECT,
                                                                         BOND_PARENT_OF_OWNER)]
    assert get_owner_bond_effects_added_on_ability_init(WITNESS) == []
    # Le selecteur est un MOT du jeu declare, pas une chaine libre : un mot hors de cette table pose
    # SANS lien (etage 4), donc l'appartenance est load-bearing.
    assert BOND_PARENT_OF_OWNER in BOND_SELECTORS_RESOLVABLE
    # Le nom d'effet est resolu par l'ENUM, jamais ecrit en dur : c'est ce qui fait rougir un
    # renumerotage plutot que de lire silencieusement la mauvaise cle.
    assert int(EffectType[BOND_EFFECT]) == 0x424


def test_2_le_passif_est_bien_au_KIT_du_porteur():
    """Sans cette ligne du gameconfig, `_seed_ability_owner_effects` ne verrait jamais l'ability :
    il balaie `activeAbilities + passiveAbilities` du `visualId`."""
    import gameconfig as GC
    kit = list((GC.unit(CARRIER) or {}).get("passiveAbilities") or [])
    assert "Lifewards" in kit, f"{CARRIER} ne porte plus Lifewards au kit : {kit}"
    autre = list((GC.unit(WITNESS) or {}).get("passiveAbilities") or [])
    assert "Lifewards" not in autre                      # TEMOIN


# ------------------------------------------------------------ [3] le seed pose l'effet AVEC le lien
def test_3_le_seed_pose_le_bond_AVEC_son_lien_sur_un_etat_sans_capture():
    st = State()
    parent = _unit(st, SUMMONER)
    child = _unit(st, CARRIER, parent_id=parent)
    added = _seed_ability_owner_effects(st, child, CARRIER, 180, ability_level=50)
    assert BOND_EFFECT in added
    eff = _inst(st, child)
    assert eff is not None, "l'owner-effect de bond n'a pas ete materialise"
    # C'EST LA LIGNE QUI FERME #963-r5 : sans elle l'instance existait deja, mais MUETTE.
    assert eff.bonded == parent, f"bonded = {eff.bonded!r}, attendu le PARENT {parent}"
    assert eff.source == child                 # 3e argument natif `source = Owner`
    assert eff.target == child                 # 4e argument natif `targets = Owner`


def test_3b_le_TEMOIN_ne_recoit_rien():
    st = State()
    parent = _unit(st, SUMMONER)
    other = _unit(st, WITNESS, parent_id=parent)
    _seed_ability_owner_effects(st, other, WITNESS, 180, ability_level=50)
    assert _inst(st, other) is None


# --------------------------------------------- [4] pas de parent -> builder ORDINAIRE, jamais un 0
def test_4_sans_parent_l_effet_est_pose_SANS_lien_et_bonded_reste_None():
    """`AddEffectBehaviour$$GetEffectBuilder`, lu verbatim :
    `method = (bondedEntityId != 0) ? <builder de BOND> : <builder ORDINAIRE>`.
    Un `bondedEntity` non resolu ne fait donc PAS echouer la pose. Deux fautes symetriques sont
    gardees ici : ne PAS poser (restrictif) et ecrire `0` (l'entite 0 existe)."""
    st = State()
    orphelin = _unit(st, CARRIER, parent_id=None)
    added = _seed_ability_owner_effects(st, orphelin, CARRIER, 180, ability_level=50)
    assert BOND_EFFECT in added, "le natif POSE quand meme -- le port ne doit pas s'abstenir"
    eff = _inst(st, orphelin)
    assert eff is not None
    assert eff.bonded is None, f"bonded = {eff.bonded!r} -- un 0 se lirait << entite 0 >>"


# ------------------------------------------------ [5] la 1re consequence levee : le gate NOT HasEffect
def test_5_re_seeder_est_IDEMPOTENT_et_ne_perd_pas_le_lien():
    """La 1re objection de #963-r5 : une instance seedee satisfait le gate `NOT HasEffect(Owner,
    0x424)` et bloque la pose correcte. Elle tombe parce que l'instance seedee EST desormais la
    pose correcte -- et re-seeder ne doit ni dupliquer ni effacer le lien."""
    st = State()
    parent = _unit(st, SUMMONER)
    child = _unit(st, CARRIER, parent_id=parent)
    _seed_ability_owner_effects(st, child, CARRIER, 180, ability_level=50)
    avant = [e.name for e in st.effects.by_unit.get(child, [])]
    re_added = _seed_ability_owner_effects(st, child, CARRIER, 180, ability_level=50)
    assert BOND_EFFECT not in re_added                    # gate `has_effect` -> no-op
    assert [e.name for e in st.effects.by_unit.get(child, [])] == avant
    assert _inst(st, child).bonded == parent              # le lien a survecu


# ---------------------------------- [6] la 2e consequence levee : le gate (a) de retrait MORD enfin
def test_6_le_gate_de_retrait_sur_mort_du_BONDE_mord_sur_l_instance_seedee():
    """La 2e objection de #963-r5 : `BOND_REMOVAL_GATES[1060]` (gate (a),
    `get_RemoveOnBondedEntityDeath = True`, MESURE) lit `BaseEffect.bonded` ; sur une instance sans
    lien `matches` rend `False` et le retrait ne mord pas. On mesure les DEUX cotes -- avec lien il
    mord, sans lien il ne mord pas -- sinon l'accord serait trivial."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.bond_removal import (BOND_REMOVAL_GATES,
                                                                BondRemoveOnBondedEntityDeath)
    from engine.runner.operations.triggers.base import TriggerEvent

    gates = BOND_REMOVAL_GATES.get(int(EffectType.Lifewards_BondEffect))
    assert gates is not None and gates.remove_on_bonded_entity_death is True

    st = State()
    parent = _unit(st, SUMMONER)
    child = _unit(st, CARRIER, parent_id=parent)
    _seed_ability_owner_effects(st, child, CARRIER, 180, ability_level=50)

    trig = BondRemoveOnBondedEntityDeath(child)
    ev = TriggerEvent(event_id=int(EventTriggerType.PreUnitDeath_2), actor_id=parent,
                      target_id=parent, ranged=None, profile=None)
    assert trig.matches(st, ev) is True, "le retrait a la mort du bonde ne mord toujours pas"

    # CONTRE-EPREUVE : la meme instance PRIVEE de son lien ne doit plus mordre -- c'est ce qui
    # etablit que c'est bien `bonded` qui porte le verdict, et pas un accord de regime.
    _inst(st, child).bonded = None
    assert trig.matches(st, ev) is False


# --------------------------------------------------- [7] retro-compatibilite des call-sites anterieurs
def test_7_materialize_sans_bonded_ni_source_est_STRICTEMENT_inchange():
    st = State()
    uid = _unit(st, WITNESS)
    assert _materialize_owner_effect(st, uid, "HeavyWeapon_ExtraDmg", 180) is True
    eff = _inst(st, uid, name="HeavyWeapon_ExtraDmg")
    assert eff is not None
    assert eff.bonded is None and eff.source is None
    sig = inspect.signature(_materialize_owner_effect)
    for nom in ("bonded", "source"):
        assert sig.parameters[nom].default is None, f"{nom} doit valoir None par defaut"


# ------------------------------------------- [8] le seed CONSOMME bien le registre (pas une copie)
@pytest.mark.parametrize("symbole", ["get_owner_bond_effects_added_on_ability_init",
                                     "BOND_PARENT_OF_OWNER", "parent_of"])
def test_8_le_seed_lit_le_REGISTRE_et_le_FOYER_du_selecteur(symbole):
    """Un registre que le seed n'interroge pas serait un inventaire, pas un canal ; et un selecteur
    re-derive a la main au lieu de passer par `parent_of` divergerait en silence du natif."""
    src = inspect.getsource(_seed_ability_owner_effects)
    assert symbole in src, f"`{symbole}` n'est plus lu par le seed"


# ------------------------------ [9] un selecteur INCONNU ne recoit pas le parent par defaut
def test_9_un_selecteur_NON_DECLARE_pose_sans_lien_au_lieu_de_recevoir_le_parent(monkeypatch):
    """TROUVE PAR LA PASSE ADVERSARIALE, et c'etait le seul etage MUET des huit : remplacer le test
    `selector == BOND_PARENT_OF_OWNER` par un `if True:` laissait la garde VERTE, parce que le seul
    selecteur du registre EST `Parent(Owner)`. Un bond futur dont le `bondedEntity` serait un AUTRE
    noeud (`Caster@<DSLSelectors+0x48>`, `Target@+0x60`, `Self@0x148`...) recevrait alors le PARENT
    en silence -- un lien FAUX, pire que pas de lien.

    On injecte donc un selecteur que le seed ne connait pas et on exige la degradation NATIVE :
    l'effet est pose (builder ORDINAIRE), `bonded` reste `None`.

    Le monkeypatch vise l'ACCESSEUR tel que le seed le lit (`import X` + `X.foo()` -- forme B,
    la seule des trois qui morde, cf. le CLAUDE.md sur les imports differes)."""
    import engine.entities.effects.factory as FACT
    monkeypatch.setattr(FACT, "get_owner_bond_effects_added_on_ability_init",
                        lambda ab: ([(BOND_EFFECT, "Caster(Owner) -- selecteur NON declare")]
                                    if ab == "Lifewards" else []))
    st = State()
    parent = _unit(st, SUMMONER)
    child = _unit(st, CARRIER, parent_id=parent)
    added = _seed_ability_owner_effects(st, child, CARRIER, 180, ability_level=50)
    assert BOND_EFFECT in added, "le natif POSE quand meme -- seul le LIEN manque"
    eff = _inst(st, child)
    assert eff is not None and eff.bonded is None, (
        f"un selecteur non declare a recu bonded={eff.bonded!r} -- le seed a DEVINE")
