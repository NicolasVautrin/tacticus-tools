"""#1023 OFFLINE -- le passif `OmnissiahsBlessing` (`TriggeredAbilityType` 0x513 = 1299,
`admecSmnTechpriest` << Tech-Priest Enginseer >>).

Ce fichier GARDE ce que le decompile a dit, sans session : les ordinaux ECRITS AUX SITES, le
cablage du registre, les QUATRE conjoints du `CreateTrigger`, et -- surtout -- l'ORDRE des deux
behaviours, qui est le seul endroit ou une inversion serait SILENCIEUSE.

Pourquoi FIGER les ordinaux ici alors que `probe_313` garde deja les mirrors : `probe_313` compare
le MIRROR au BUILD, donc il redevient vert des qu'on regenere le mirror apres un renumerotage --
alors que la valeur ECRITE au site, elle, a change (meme cran que `test_1001_votann_relics_offline`).

CE QUE CE FICHIER NE COUVRE PAS, et c'est ECRIT :
  * le canal DEGAT de `1365 MachineVengeance` (`MachineVengeanceEffect$$
    CreateEffectDamageBonusForAttack`) n'est PAS porte -- l'effet n'a aucune classe dans
    `EFFECT_CLASSES`. Le transfert est donc observable par le NIVEAU, pas par un degat. Residu
    #1023-r1, garde a l'etage 6 ci-dessous (le test AFFIRME l'absence, pour qu'un port futur le
    fasse rougir au lieu de passer inapercu) ;
  * le conjoint `onlyActive = 0` : le montage ne le SEPARE pas, faute d'`ActiveCondition` sur 1365.
    C'est ecrit comme une NON-MORSURE MESUREE (etage 5), jamais tu.
"""
from __future__ import annotations

#: Perimetre : le module de trigger, le registre qui le fait exister, l'emetteur du vecteur, les
#: feuilles DSL qu'il compose, et TOUS les mirrors d'enum dont un ordinal est fige ci-dessous.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/omnissiahs_blessing.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/repair.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les ordinaux ECRITS AU SITE (0x513 = 1299 la triggered, 0x555 = 1365 "
              "l'effet, 0x30 = 48 le vecteur), le cablage d'`ABILITY_TRIGGERS`, les QUATRE "
              "conjoints du `CreateTrigger` (`get_OwnerIsCaster`, `HasEffect(Owner, 1365, "
              "onlyActive: 0, 6)`, `NOT get_OwnerIsTarget`, `ownerNeedsToBeAlive`) et l'ORDRE des "
              "deux behaviours du `CreateBehaviour` -- `AddEffectOrIncreaseLevel` PUIS "
              "`RemoveEffect`, la seule inversion qui serait silencieuse (le transfert lirait 0 et "
              "la pile disparaitrait quand meme). Il grave aussi le `maxLevel = NULL` (aucun cap) "
              "et l'absence, ASSUMEE, de classe d'effet pour 1365.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine.dsl.event_trigger_type import EventTriggerType                       # noqa: E402
from engine.entities.effect_type import EffectType
from engine.entities.effects import factory as F
from engine.entities.effects_state import EffectsState
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_context import UnitContext
from engine.runner.components import (HealthComponent, OwnerComponent, StatsComponent,
                                      UnitComponent)
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.operations.triggers.dispatch.repair import unit_repaired_triggers
from engine.runner.operations.triggers.loki import omnissiahs_blessing as OB
from engine.runner.state import State

TECHPRIEST = "admecSmnTechpriest"
#: Les traits REELS du porteur (`gameconfig.units.summons.admecSmnTechpriest.traits`). `Mechanic` =
#: il REPARE (c'est ce trait qui lui derive l'active `28 Repair`, donc qui rend le vecteur
#: `On(0x30 = UnitRepaired)` atteignable pour lui) ; `Mechanical` = il EST une machine.
TECHPRIEST_TRAITS = ("Summon", "Mechanical", "Mechanic")


# --------------------------------------------------------------------------- 1. les ORDINAUX LUS
def test_ordinaux_ecrits_aux_sites():
    """Les litteraux du decompile, figes AU SITE (cf. l'en-tete du fichier)."""
    assert int(TriggeredAbilityType.OmnissiahsBlessing) == 1299 == 0x513
    assert int(EffectType.MachineVengeance) == 1365 == 0x555
    assert int(EventTriggerType.UnitRepaired) == 48 == 0x30
    assert OB.OMNISSIAHS_BLESSING_ID == 1299
    assert OB.MACHINE_VENGEANCE == 1365
    assert OB.MACHINE_VENGEANCE_NAME == "MachineVengeance"
    #: ⚠ LE MEMBRE EST SUR LA LIGNE, PAS QUATRE LIGNES PLUS HAUT (#1031). La ligne 82 fige bien
    #: `UnitRepaired == 48`, mais ce site-ci ecrivait `== 48` NU : rien sur la ligne ne disait
    #: QUEL membre ce 48 designe, et un renumerotage l'aurait laisse pointer ailleurs pendant
    #: que la ligne 82, elle, rougissait. Patron canonique du depot (cf. `test_1008`).
    assert OB.OmnissiahsBlessingAbility.event_id == 48 == int(EventTriggerType.UnitRepaired)
    assert OB.OmnissiahsBlessingAbility.TRIGGERED_ABILITY_ID == 1299
    # La cle du registre EST le nom gameconfig de la `passiveAbilities`, pas un id.
    assert OB.OMNISSIAHS_BLESSING == "OmnissiahsBlessing"


def test_l_effet_transfere_est_LE_MEME_que_la_pile_d_ArcScourge():
    """`ArcScourgeAbility` empile `0x555` sur son caster ; `OmnissiahsBlessing` transfere CETTE
    pile-la. Si les deux constantes divergeaient, le transfert porterait sur un effet que personne
    n'empile -- une panne SILENCIEUSE des deux cotes."""
    from engine.runner.abilities.admec import AS_MACHINE_VENGEANCE
    assert OB.MACHINE_VENGEANCE == AS_MACHINE_VENGEANCE == 1365


# --------------------------------------------------------------------------- 2. le CABLAGE
def test_le_registre_porte_la_classe():
    assert REG.ABILITY_TRIGGERS.get("OmnissiahsBlessing") == [OB.OmnissiahsBlessingAbility]


def test_ce_n_est_PAS_une_relique_ni_une_helper_d_active():
    """C'est une `passiveAbilities` de kit : elle entre par `ABILITY_TRIGGERS` et par LUI SEUL.
    Une entree dans un autre registre la ferait porter par un chemin de montage que le natif
    n'emprunte pas (`TertiaryAbility` / `relicAbilities` / `GetPassiveHelperAbility`)."""
    assert "OmnissiahsBlessing" not in REG.RELIC_ABILITY_TRIGGERS
    assert "OmnissiahsBlessing" not in REG.PASSIVE_HELPER_ABILITY_TRIGGERS
    assert "OmnissiahsBlessing" not in REG.ACTIVE_ABILITY_TRIGGERS


def test_le_porteur_gameconfig_porte_bien_ce_passif():
    """La cle du registre doit etre EXACTEMENT le nom que `collect_triggered_abilities` lira dans
    `gameconfig.units.summons.<id>.passiveAbilities` -- sinon l'inscription est un no-op."""
    import gameconfig as GC
    u = GC.unit(TECHPRIEST) or {}
    assert "OmnissiahsBlessing" in (u.get("passiveAbilities") or [])
    assert set(TECHPRIEST_TRAITS) <= set(u.get("traits") or [])


def test_l_emetteur_du_vecteur_existe_et_passe_le_reparateur_en_ACTOR():
    """`On(0x30)` serait un registered-but-dead sans `unit_repaired_triggers` -- et le gate
    `get_OwnerIsCaster` du passif se lit sur `ev.actor_id`, donc l'emetteur DOIT y mettre le
    reparateur (`processor.<slot 0x51>(caster, caster, target, 0x30, ...)`)."""
    import inspect
    from engine.runner.operations.triggers.dispatch import repair as RD
    from engine.runner.operations import repair as ROP
    assert callable(RD.unit_repaired_triggers)
    assert "unit_repaired_triggers" in inspect.getsource(ROP)
    src = inspect.getsource(RD.unit_repaired_triggers)
    assert "EventTriggerType.UnitRepaired" in src
    assert "int(caster_id)" in src and "int(target_id)" in src


# --------------------------------------------------------------------------- 3. le MONTAGE offline
def _unit(state, vis, team, traits=(), *, alive=True, hp=1000, hp_max=1000, passives=None):
    """Une unite du montage. `passives` non nul alimente `UnitContext.passive_abilities`, LE canal
    MESURE que `collect_triggered_abilities` prefere au kit gameconfig -- c'est aussi le canal
    exact d'une GREFFE (`catalog_inject`), donc le montage offline et le montage live passent par
    la MEME porte."""
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vis, alive=alive))
    e.add_component(OwnerComponent(team=team))
    ctx = UnitContext(entity_id=e.id, visual_id=vis)
    ctx.traits = list(traits)
    ctx.passive_ability_level = 50
    if passives is not None:
        ctx.passive_abilities = list(passives)
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    return e.id


def _stack(state, uid, level, source=None):
    """Pose UNE instance de `1365 MachineVengeance` de niveau `level` sur `uid`. `source` = le
    `EffectComponent.SourceUnit` ; il n'entre dans AUCUN gate de ce passif (le natif lit
    `GetOwnedEffect(owner, ...)`, keye sur le PORTEUR), on le renseigne pour rester realiste."""
    return AddEffectOperation.execute(state, source=(uid if source is None else source), target=uid,
                                      effect_type=OB.MACHINE_VENGEANCE,
                                      name=OB.MACHINE_VENGEANCE_NAME, level=int(level))


def _level(state, uid) -> int:
    """Le niveau LU comme le lit `EffectLevelFormula$$Calculate` : la SOMME des instances non
    consommees. Volontairement un second chemin de lecture, pour ne pas s'auto-tester avec
    `machine_vengeance_level`."""
    return sum(int(getattr(e, "level", 0) or 0)
               for e in state.effects.by_unit.get(int(uid), [])
               if not getattr(e, "consumed", False)
               and int(getattr(e, "effect_type", -1)) == OB.MACHINE_VENGEANCE)


def _blessing_state(owner_level=4, ally_level=None, owner_alive=True, ally_team=1,
                    owner_passives=("OmnissiahsBlessing",)):
    """FIXTURE NOMMEE, reutilisee par tous les etages : un Tech-Priest (porteur du passif) et un
    allie MECANIQUE reparable, plus un TIERS mecanicien qui sert aux contre-epreuves de caster."""
    st = State()
    st.effects = EffectsState()          # `AddEffectOperation` ne materialise RIEN sans elle
    owner = _unit(st, TECHPRIEST, 1, TECHPRIEST_TRAITS, alive=owner_alive,
                  passives=list(owner_passives))
    ally = _unit(st, "ally", ally_team, (UnitTrait.Mechanical.name,), hp=500, hp_max=1000)
    autre = _unit(st, "autreMecano", 1, (UnitTrait.Mechanical.name, "Mechanic"), passives=[])
    if owner_level:
        _stack(st, owner, owner_level)
    if ally_level:
        _stack(st, ally, ally_level)
    return st, owner, ally, autre


def _fire(st, caster, target):
    """Joue le vecteur et rend la (les) sortie(s) de CE passif."""
    out = unit_repaired_triggers(st, caster, target) or []
    return [e for e in out if isinstance(e, dict) and e.get("passive") == "OmnissiahsBlessing"]


# --------------------------------------------------------------------- 4. le TRANSFERT et son ORDRE
def test_le_transfert_nominal_vide_le_porteur_et_remplit_la_cible():
    """`AddEffectOrIncreaseLevel(0x555, ..., Target@+0x60, lvl) & RemoveEffect(Owner@+0x30, 0x555)`
    -- << it transfers ALL levels of Machine Vengeance it has to the repaired unit >>."""
    st, owner, ally, _autre = _blessing_state(owner_level=4)
    assert (_level(st, owner), _level(st, ally)) == (4, 0)
    ev = _fire(st, owner, ally)
    assert len(ev) == 1 and ev[0]["level"] == 4 and ev[0]["target"] == ally
    assert _level(st, ally) == 4, "la pile n'a pas ete transferee"
    assert _level(st, owner) == 0, "la pile du porteur n'a pas ete retiree"


def test_le_transfert_CUMULE_sur_une_cible_qui_en_porte_deja_et_SANS_cap():
    """`maxLevel = NULL` : `IncreaseEffectLevelOperation$$Execute` ne clampe rien. La branche prise
    est `IncreaseEffectLevel` (l'effet est deja present sur la cible), pas `AddEffect`."""
    st, owner, ally, _autre = _blessing_state(owner_level=5, ally_level=3)
    ev = _fire(st, owner, ally)
    assert len(ev) == 1
    assert _level(st, ally) == 8, "3 + 5 attendus, cumul SANS cap"
    assert _level(st, owner) == 0


def test_le_niveau_lu_est_une_SOMME_pas_un_premier():
    """`EffectLevelFormula$$Calculate` part de 0 et ACCUMULE `EffectComponent+0x68` sur TOUTES les
    entites-effet rendues. Deux instances de 1365 sur le porteur -> 2 + 3 = 5 transferes."""
    import copy
    st, owner, ally, _autre = _blessing_state(owner_level=2)
    seconde = copy.copy(st.effects.by_unit[int(owner)][0])
    seconde.level = 3
    st.effects.by_unit[int(owner)].append(seconde)
    assert len(st.effects.by_unit[int(owner)]) == 2, "le montage doit porter DEUX instances"
    assert OB.machine_vengeance_level(st, owner) == 5
    ev = _fire(st, owner, ally)
    assert len(ev) == 1 and ev[0]["level"] == 5
    assert _level(st, ally) == 5 and _level(st, owner) == 0


def test_le_niveau_transfere_est_un_NOEUD_PARESSEUX_pas_un_scalaire():
    """Le COLLAPSE V habituel (`talons_used_abilities_level`, `_remaining_turns_of_extra_movement`)
    est INTERDIT ici : le `RemoveEffect` qui suit REECRIT ce que le transfert lit. Sous un scalaire,
    le mutant << ordre inverse >> reste VERT -- MESURE, cf. l'en-tete du module.

    Ce test garde la FORME (le noeud) et sa VALEUR (la lecture au moment de l'evaluation), pour
    qu'un retour au scalaire desarme visiblement le test d'ordre ci-dessous."""
    from engine.dsl.base import AAmountFormula
    from engine.runner.abilities.behaviours.context import entities_from_state
    st, owner, ally, _autre = _blessing_state(owner_level=6)
    node = OB.MachineVengeanceLevelOfOwner(st)
    assert isinstance(node, AAmountFormula)
    ents = entities_from_state(st, owner, ally)
    assert int(node.evaluate(ents)) == 6
    # la lecture est bien PARESSEUSE : elle suit la mutation de l'etat.
    OB.omnissiahs_blessing_clear_tree().execute(ents, __import__(
        "engine.dsl.effects", fromlist=["ExecutionContext"]).ExecutionContext(state=st, rng=st.rng))
    assert int(node.evaluate(ents)) == 0, "le noeud a fige sa lecture -- il n'est PAS paresseux"


def test_MUTANT_ordre_inverse_le_transfert_devient_NUL():
    """CONTRE-EPREUVE CENTRALE. `op_BitwiseAnd(b1, b2)` = `CombinedBehaviour` gauche->droite : si on
    vide la pile AVANT de la lire, le transfert vaut 0 et la pile disparait quand meme -- aucune
    erreur, aucun compte global ne bouge. C'est la seule inversion silencieuse de ce port ; ce test
    la rend BRUYANTE.

    TEMOIN d'abord (l'arbre NATIF sur le meme montage rend 4), mutant ensuite (0) : deux hypotheses
    qui rendraient le meme nombre ne concluraient rien."""
    from engine.entities.behaviours import Seq
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    st_t, owner_t, ally_t, _at = _blessing_state(owner_level=4)
    OB.omnissiahs_blessing_tree(st_t).execute(
        entities_from_state(st_t, owner_t, ally_t), ExecutionContext(state=st_t, rng=st_t.rng))
    assert (_level(st_t, owner_t), _level(st_t, ally_t)) == (0, 4), "le TEMOIN doit transferer 4"

    st, owner, ally, _autre = _blessing_state(owner_level=4)
    mutant = Seq(OB.omnissiahs_blessing_clear_tree(), OB.omnissiahs_blessing_transfer_tree(st))
    mutant.execute(entities_from_state(st, owner, ally), ExecutionContext(state=st, rng=st.rng))
    assert _level(st, owner) == 0
    assert _level(st, ally) == 0, "l'ordre inverse doit rendre un transfert NUL"


def test_MUTANT_cible_le_porteur_au_lieu_de_la_cible():
    """`targets = Target@+0x60`. Le remplacer par `Owner@+0x30` ferait poser puis retirer la pile
    sur le MEME porteur -- net-zero, cible jamais servie."""
    from engine.entities.selectors.accessors import Owner
    from engine.entities.behaviours import Seq
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.behaviours.effects import add_effect_or_increase_level
    st, owner, ally, _autre = _blessing_state(owner_level=4)
    entities = entities_from_state(st, owner, ally)
    ectx = ExecutionContext(state=st, rng=st.rng)
    mutant = Seq(add_effect_or_increase_level(
                     OB.MACHINE_VENGEANCE, OB.MACHINE_VENGEANCE_NAME, Owner(),
                     amount=OB.MachineVengeanceLevelOfOwner(st), max_level=None),
                 OB.omnissiahs_blessing_clear_tree())
    mutant.execute(entities, ectx)
    assert _level(st, ally) == 0, "le mutant ne doit RIEN donner a la cible"
    assert _level(st, owner) == 0


# --------------------------------------------------------------------------- 5. les QUATRE conjoints
def test_gate_HasEffect_un_porteur_SANS_pile_ne_fire_pas():
    """`HasEffect(Owner@+0x30, 0x555, onlyActive: 0, 6)`. Sans lui, chaque reparation poserait un
    `MachineVengeance` de niveau 0 sur la cible."""
    st, owner, ally, _autre = _blessing_state(owner_level=0)
    assert _fire(st, owner, ally) == []
    assert _level(st, ally) == 0


def test_gate_NOT_OwnerIsTarget_une_AUTO_reparation_ne_fire_pas():
    """`NOT get_OwnerIsTarget` -- le << another unit >> de l'i2. Ce gate n'est PAS redondant avec
    `get_OwnerIsCaster` : `RepairAbility` porte `TargetingRule.CasterIsPossibleTarget` (masque
    0x8002), donc un mecanicien PEUT se cibler. Sans ce conjoint, la pile serait posee puis retiree
    sur le meme porteur -- perte seche."""
    st, owner, _ally, _autre = _blessing_state(owner_level=4)
    assert _fire(st, owner, owner) == []
    assert _level(st, owner) == 4, "la pile du porteur doit rester INTACTE"


def test_gate_OwnerIsCaster_un_AUTRE_reparateur_ne_fire_pas():
    """`get_OwnerIsCaster` = le porteur EST le reparateur (`ev.actor_id`)."""
    st, owner, ally, autre = _blessing_state(owner_level=4)
    assert _fire(st, autre, ally) == []
    assert (_level(st, owner), _level(st, ally)) == (4, 0)


def test_gate_ownerNeedsToBeAlive_un_porteur_MORT_ne_fire_pas():
    """`On(0x30, ownerNeedsToBeAlive: 1)`."""
    st, owner, ally, _autre = _blessing_state(owner_level=4, owner_alive=False)
    assert _fire(st, owner, ally) == []
    assert _level(st, ally) == 0


def test_la_cible_ENNEMIE_fire_AUSSI_et_c_est_LU():
    """AUCUN conjoint de camp dans le `CreateTrigger` : ni `AreFriends`, ni `AreEnemies`. Le filtre
    de camp vit en amont, dans le gate de cible de `RepairAbility` (`GetDynamicInvalidTargetReason`
    rend `TargetIsFriendly` sur un ennemi), pas ici. Un port qui AJOUTERAIT un test d'equipe ferait
    donc du zele -- ce test le montre en jouant le vecteur sur une cible d'equipe 2."""
    st, owner, ally, _autre = _blessing_state(owner_level=4, ally_team=2)
    ev = _fire(st, owner, ally)
    assert len(ev) == 1 and _level(st, ally) == 4


def test_NON_MORSURE_MESUREE_le_flag_onlyActive_n_est_pas_separe_par_ce_montage():
    """`onlyActive = 0` est le LITTERAL du call-site, et le port l'ecrit (`active_only=False`).
    Mais `1365` n'a AUCUNE classe dans `EFFECT_CLASSES`, donc son instance n'a pas
    d'`ActiveCondition` et `is_active` rend vrai quoi qu'il arrive : basculer le flag ne change
    RIEN dans ce montage. Ecrit comme un RESULTAT -- un lecteur futur ne doit pas le prendre pour
    un oubli. Ce qui EST garde : la valeur ecrite au site."""
    node = OB._OWNER_HAS_MACHINE_VENGEANCE
    assert node.active_only is False
    assert int(node.effect_type) == OB.MACHINE_VENGEANCE
    st, owner, ally, _autre = _blessing_state(owner_level=4)
    from engine.entities.triggers import HasEffect
    from engine.entities.selectors.accessors import Owner
    from engine.runner.abilities.behaviours.context import entities_from_state
    ents = entities_from_state(st, owner, ally)
    strict = HasEffect(Owner(), OB.MACHINE_VENGEANCE, active_only=True)
    assert strict.should_trigger(ents) == node.should_trigger(ents) is True, (
        "si les deux divergeaient, ce montage separerait le flag -- alors il faudrait le GARDER "
        "par un test de comportement, pas seulement par la valeur ecrite")


# ------------------------------------------------------- 6. CONTRE-EPREUVE : le rail lui-meme
def test_SANS_l_entree_de_registre_le_passif_est_SILENCIEUX():
    """Le mode de panne que ce port ferme : `ABILITY_TRIGGERS.get(pa, ())` rend un tuple vide et le
    moteur continue -- aucune erreur, aucun accumulateur `unported` de ce cote. La contre-epreuve
    doit donc montrer le SILENCE, pas un crash."""
    st, owner, ally, _autre = _blessing_state(owner_level=4)
    saved = REG.ABILITY_TRIGGERS.pop("OmnissiahsBlessing")
    try:
        assert _fire(st, owner, ally) == []
        assert (_level(st, owner), _level(st, ally)) == (4, 0), (
            "sans le rail, RIEN ne bouge -- et c'est exactement l'invisibilite du gisement")
    finally:
        REG.ABILITY_TRIGGERS["OmnissiahsBlessing"] = saved
    # TEMOIN : le rail remis, le MEME montage fire -- sans quoi ce test passerait aussi si le port
    # etait cassé pour une tout autre raison.
    st2, owner2, ally2, _a2 = _blessing_state(owner_level=4)
    assert len(_fire(st2, owner2, ally2)) == 1
    assert _level(st2, ally2) == 4


def test_le_porteur_SANS_ce_passif_ne_fire_pas():
    """Contre-epreuve d'ATTRIBUTION : c'est bien `passiveAbilities` qui inscrit l'ability, pas le
    fait d'etre un mecanicien porteur de 1365."""
    st, owner, ally, _autre = _blessing_state(owner_level=4, owner_passives=())
    assert _fire(st, owner, ally) == []
    assert (_level(st, owner), _level(st, ally)) == (4, 0)


def test_l_effet_1365_n_a_PAS_de_classe_et_c_est_le_residu_1023r1():
    """`MachineVengeanceEffect$$CreateEffectDamageBonusForAttack` =
    `EffectBonus.ForPercentIncrease(get_OwnerIsCaster, Multiply(Get(GetNumberConstant(7)),
    EffectLevel(Effect@+0x38)))` -- un bonus de degat en POURCENTAGE par niveau. Il n'est PAS porte.
    Ce test AFFIRME l'absence pour qu'un port futur le fasse rougir ICI (et mette a jour le residu)
    au lieu de le laisser passer inapercu."""
    assert "MachineVengeance" not in F.EFFECT_CLASSES, (
        "1365 a desormais une classe d'effet : fermer #1023-r1 et retirer cette assertion")
    assert not any(str(k).startswith("MachineVengeance_") for k in F.EFFECT_CLASSES)
