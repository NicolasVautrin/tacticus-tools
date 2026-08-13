"""#1001 OFFLINE -- les DEUX reliques LEAGUES OF VOTANN : `BladeOfTheAncestors` (1491,
`votanUthar`) et `VolummsMasterArtifice` (1488, `votanIronmaster`).

Ce fichier GARDE ce que le decompile a dit, sans session : les ordinaux ECRITS AUX SITES, le
cablage des TROIS registres, et le comportement de chaque GATE. La confrontation au natif vit dans
`tests/engine/runner/test_1001_votann_relics_live.py` (via `probe_1001_votann_relics.py`).

Pourquoi FIGER les ordinaux ici alors que `probe_313` garde deja les mirrors : `probe_313` compare
le MIRROR au BUILD, donc il redevient vert des qu'on regenere le mirror apres un renumerotage --
alors que la valeur ECRITE au site, elle, a change (meme cran que `test_959_votann_auras_offline`).
"""
from __future__ import annotations

#: Perimetre : les deux modules de trigger, la classe d'effet, les registres qui les font exister,
#: l'accesseur de magnitude, et TOUS les mirrors d'enum dont un ordinal est fige ci-dessous.
#: `gameconfig.json` entre au perimetre parce que les QUATRE variables de niveau en sortent.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/blade_of_the_ancestors.py",
        "scripts/python/engine/runner/operations/triggers/loki/volumms_master_artifice.py",
        "scripts/python/engine/entities/effects/loki/votann.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/pending.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/repair.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les ordinaux ECRITS AUX SITES (que `probe_313` ne voit pas -- il "
              "compare le mirror au build, pas le site), le cablage des TROIS registres "
              "(`RELIC_ABILITY_TRIGGERS`, `CUSTOM_TRIGGERED_ABILITIES`, `EFFECT_CLASSES`) et les "
              "gates des deux `CreateTrigger` : les DEUX branches de `BladeOfTheAncestors` "
              "(mort d'un HERO allie / kill par un HERO allie d'une unite NORMALE) et les DEUX "
              "voies de `VolummsMasterArtifice` (`OwnerIsCaster` / `Parent(Caster) == Owner`). "
              "Il garde aussi le SENS du seuil -- `compteur >= nrOfRepairs` sur le compteur DEJA "
              "incremente, l'INVERSE de `DaemonfleshPlate` -- et le fait que le reset du buff "
              "crit passe par la FILE des differees, pas par un retrait immediat.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine.dsl.event_trigger_type import EventTriggerType                    # noqa: E402
from engine.entities.effect_type import EffectType
from engine.entities.effects import factory as F
from engine.entities.effects.loki import votann as V
from engine.entities.effects_state import EffectsState
from engine.entities.stats import StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_context import UnitContext
from engine.runner.components import (HealthComponent, OwnerComponent, StatsComponent,
                                      UnitComponent)
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.operations.triggers.dispatch.move_death import unit_death_triggers
from engine.runner.operations.triggers.dispatch.pending import process_pending_triggered_abilities
from engine.runner.operations.triggers.dispatch.repair import unit_repaired_triggers
from engine.runner.operations.triggers.loki import blade_of_the_ancestors as BA
from engine.runner.operations.triggers.loki import volumms_master_artifice as VA
from engine.runner.state import State

UTHAR, VYNN = "votanUthar", "votanIronmaster"


# --------------------------------------------------------------------------- 1. les ORDINAUX LUS
def test_ordinaux_ecrits_aux_sites():
    """Les litteraux du decompile, figes AU SITE (cf. l'en-tete du fichier)."""
    assert int(TriggeredAbilityType.BladeOfTheAncestors) == 1491        # 0x5d3
    assert int(TriggeredAbilityType.VolummsMasterArtifice) == 1488      # 0x5d0
    assert int(EffectType.BladeOfTheAncestors_Effect) == 1489           # 0x5d1
    assert BA.BLADE_OF_THE_ANCESTORS == 1491 and BA.BUFF_EFFECT == 1489
    assert VA.VOLUMMS_MASTER_ARTIFICE == 1488
    # les VECTEURS
    assert BA.BladeOfTheAncestorsAbility.event_id == int(EventTriggerType.UnitDeath) == 0
    assert BA.BladeOfTheAncestorsRemoveEffectAbility.event_id == int(EventTriggerType.Attack) == 9
    assert (BA.BladeOfTheAncestorsCustomRemoveEffectAbility.event_id
            == int(EventTriggerType.Custom) == 0x20)
    assert VA.VolummsMasterArtificeAbility.event_id == int(EventTriggerType.UnitRepaired) == 48
    # les TRAITS des gates
    assert int(BA.HERO_TRAIT) == int(UnitTrait.Hero) == 0x10
    assert tuple(int(t) for t in BA.NON_NORMAL_TRAITS) == (0xd, 0x1b)   # Object / Steppable
    # les VARIABLES de config (noms gameconfig, ordinaux `AbilityVariableType` en commentaire)
    assert V.BladeOfTheAncestorsBuffEffect.EXTRA_CRIT_CHANCE_KEY == "extraCritChance"   # 0x41
    assert V.BladeOfTheAncestorsBuffEffect.EXTRA_CRIT_DMG_KEY == "extraCritDmg"         # 0x42
    assert VA.NR_OF_REPAIRS_KEY == "nrOfRepairs" and VA.HP_TO_HEAL_KEY == "hpToHeal"    # 0x9b / 0x20


def test_les_stats_du_changestat_sont_crit_chance_et_crit_damage():
    """`Stat(9, 5 = Modification)` et `Stat(10, 5)` d'`ApplyModification` ; `StatPart` 6 au revert."""
    assert int(StatType.CRIT_CHANCE) == 9 and int(StatType.CRIT_DAMAGE) == 10
    eff = V.BladeOfTheAncestorsBuffEffect(EffectType.BladeOfTheAncestors_Effect.name,
                                          effect_type=int(EffectType.BladeOfTheAncestors_Effect))
    assert eff.reverted_stats() == [StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE]


# --------------------------------------------------------------------------- 2. le CABLAGE
def test_les_trois_registres_portent_les_bonnes_classes():
    """Mesure #1004 : quand c'est un trigger il en faut DEUX -- l'ABILITY au registre de reliques ET
    l'EFFET dans `EFFECT_CLASSES`. L'effet seul = ability jamais declenchee ; l'ability seule = un
    `BaseEffect` NU qui ne change aucune stat."""
    assert REG.RELIC_ABILITY_TRIGGERS.get("BladeOfTheAncestors") == [
        BA.BladeOfTheAncestorsAbility, BA.BladeOfTheAncestorsRemoveEffectAbility]
    assert REG.RELIC_ABILITY_TRIGGERS.get("VolummsMasterArtifice") == [
        VA.VolummsMasterArtificeAbility]
    assert REG.CUSTOM_TRIGGERED_ABILITIES.get(1491) == [
        BA.BladeOfTheAncestorsCustomRemoveEffectAbility]
    assert F.EFFECT_CLASSES.get("BladeOfTheAncestors_Effect") is V.BladeOfTheAncestorsBuffEffect


def test_ce_ne_sont_PAS_des_ability_triggers():
    """Le registre des RELIQUES est SEPARE d'`ABILITY_TRIGGERS` a dessein (montage natif distinct :
    `TertiaryAbility` / `relicAbilities`). Une entree dans le mauvais registre ferait porter
    l'ability par un chemin que le natif n'emprunte pas."""
    for nm in ("BladeOfTheAncestors", "VolummsMasterArtifice"):
        assert nm not in REG.ABILITY_TRIGGERS
        assert nm not in REG.PASSIVE_HELPER_ABILITY_TRIGGERS


def test_la_branche_custom_de_l_ability_principale_n_est_PAS_inscrite():
    """`BladeOfTheAncestorsAbility$$CreateBehaviour` vaut `DSLBehaviors$$Nothing()` quand
    `triggerType == 0x20` : le natif l'appelle au drain et elle ne fait RIEN. L'inscrire au registre
    des differees serait un mensonge de couverture (une classe de no-op)."""
    assert BA.BladeOfTheAncestorsAbility not in REG.CUSTOM_TRIGGERED_ABILITIES.get(1491, [])


# --------------------------------------------------------------------------- 3. le MONTAGE offline
def _unit(state, vis, team, traits=(), *, alive=True, hp=None, hp_max=None,
          tertiary=None, tertiary_level=0, parent=None, passive_level=50):
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vis, alive=alive,
                                  parent_id=None if parent is None else int(parent)))
    e.add_component(OwnerComponent(team=team))
    ctx = UnitContext(entity_id=e.id, visual_id=vis)
    ctx.traits = list(traits)
    ctx.passive_ability_level = passive_level
    if tertiary is not None:
        ctx.tertiary_ability = tertiary
        ctx.tertiary_ability_level = tertiary_level
        ctx.tertiary_ability_variables_multiplier = 100
    e.add_component(StatsComponent(ctx=ctx))
    if hp is not None:
        e.add_component(HealthComponent(hp=hp, hp_max=hp_max if hp_max is not None else hp))
    return e.id


def _blade_state(level=3, killer_traits=(UnitTrait.Hero.name,),
                 victim_traits=(), killer_team=1, victim_team=2, owner_alive=True):
    st = State()
    st.effects = EffectsState()          # `AddEffectOperation` ne materialise RIEN sans elle
    uthar = _unit(st, UTHAR, 1, (UnitTrait.Hero.name,), alive=owner_alive,
                  tertiary="BladeOfTheAncestors", tertiary_level=level)
    killer = _unit(st, "alliedHero", killer_team, killer_traits)
    victim = _unit(st, "victim", victim_team, victim_traits, alive=False, hp=0, hp_max=1000)
    return st, uthar, killer, victim


def _crit(st, uid):
    ctx = st.get_entity(uid).get_component(StatsComponent).ctx
    return (ctx.stat(int(StatType.CRIT_CHANCE)), ctx.stat(int(StatType.CRIT_DAMAGE)))


# --------------------------------------------------------------------------- 4. BLADE : les gates
def test_branche_2_un_hero_allie_tue_une_unite_normale():
    """`On(0 = UnitDeath) & AreFriends(Actor@+0x40, Owner) & HasTrait(Actor, Hero)
    & IsNormalUnit(Targets@+0x60)` -- la branche CONFRONTEE LIVE (probe #1001, volet `blade`)."""
    from engine.entities.effects.magnitude import ability_var
    st, uthar, killer, victim = _blade_state(level=3)
    before = _crit(st, uthar)
    out = unit_death_triggers(st, victim, killer) or []
    ev = [e for e in out if isinstance(e, dict) and e.get("relic") == "BladeOfTheAncestors"]
    assert len(ev) == 1 and ev[0]["stacks_added"] == 1
    after = _crit(st, uthar)
    exp_cc = int(ability_var("BladeOfTheAncestors", "extraCritChance", 3, multiplier_pct=100))
    exp_cd = int(ability_var("BladeOfTheAncestors", "extraCritDmg", 3, multiplier_pct=100))
    assert (after[0] - before[0], after[1] - before[1]) == (exp_cc, exp_cd)


def test_branche_1_la_mort_d_un_hero_allie_suffit():
    """`On(0) & AreFriends(Targets@+0x60, Owner) & HasTrait(Targets@+0x60, Hero)` -- le MOURANT est
    un Hero allie. Aucun gate `IsNormalUnit` sur cette branche, et aucun gate sur le TUEUR : c'est
    ce que le decompile dit, et c'est ce qui distingue les deux branches."""
    st = State()
    st.effects = EffectsState()
    uthar = _unit(st, UTHAR, 1, (UnitTrait.Hero.name,),
                  tertiary="BladeOfTheAncestors", tertiary_level=3)
    ennemi = _unit(st, "foe", 2, ())                       # le TUEUR est un ENNEMI, sans trait Hero
    mort = _unit(st, "alliedHero", 1, (UnitTrait.Hero.name,), alive=False, hp=0, hp_max=1000)
    before = _crit(st, uthar)
    out = unit_death_triggers(st, mort, ennemi) or []
    assert [e for e in out if isinstance(e, dict) and e.get("relic") == "BladeOfTheAncestors"]
    assert _crit(st, uthar) != before


@pytest.mark.parametrize("cas,kw", [
    ("le tueur n'est pas un Hero", {"killer_traits": ()}),
    ("le tueur est un ENNEMI", {"killer_team": 2}),
    ("la victime n'est PAS une unite normale (Object)",
     {"victim_traits": (UnitTrait.Object.name,)}),
    ("la victime n'est PAS une unite normale (Steppable)",
     {"victim_traits": (UnitTrait.Steppable.name,)}),
    ("le porteur est MORT (ownerNeedsToBeAlive)", {"owner_alive": False}),
])
def test_les_negatifs_de_la_branche_2(cas, kw):
    """L'autre facon de se tromper, et la plus dangereuse : une degradation PERMISSIVE, que rien du
    regime nominal ne verrait. Chacun de ces cas doit rendre ZERO stack."""
    st, uthar, killer, victim = _blade_state(level=3, **kw)
    before = _crit(st, uthar)
    out = unit_death_triggers(st, victim, killer) or []
    assert not [e for e in out if isinstance(e, dict) and e.get("relic") == "BladeOfTheAncestors"], cas
    assert _crit(st, uthar) == before, cas


def test_l_empilement_est_ADDITIF():
    """`UpdateInternal` = `ApplyModification` NU et `RefreshValueInternal` = `ApplyModification`
    x `GetTimesApplied` : l'effet EMPILE, il ne se rafraichit pas. Cote port c'est
    `stacks_stat_mod_on_add = True` qui le porte -- sans lui, la 2e pose serait un no-op."""
    from engine.entities.effects.magnitude import ability_var
    assert V.BladeOfTheAncestorsBuffEffect.stacks_stat_mod_on_add is True
    st, uthar, killer, victim = _blade_state(level=3)
    before = _crit(st, uthar)
    unit_death_triggers(st, victim, killer)
    unit_death_triggers(st, victim, killer)
    exp_cd = int(ability_var("BladeOfTheAncestors", "extraCritDmg", 3, multiplier_pct=100))
    assert _crit(st, uthar)[1] - before[1] == 2 * exp_cd


def test_le_reset_passe_par_la_FILE_des_differees_et_retire_TOUTES_les_piles():
    """`On(9) & OwnerIsCaster & WasCrit & HasEffect(Owner, 0x5d1)` -> `TriggerAbilityDelayed(Owner,
    0x5d3, 3)` ; le retrait n'a lieu qu'au DRAIN, branche `Custom`. Un `RemoveEffect` immediat
    serait un collapse inline : le buff tomberait AU MILIEU de la salve au lieu d'a sa fin."""
    from engine.runner.operations.triggers.dispatch.attack import finish_attack_triggers
    st, uthar, killer, victim = _blade_state(level=3)
    base = _crit(st, uthar)
    unit_death_triggers(st, victim, killer)
    unit_death_triggers(st, victim, killer)
    assert _crit(st, uthar) != base
    q = finish_attack_triggers(st, uthar, victim, ranged=False, is_crit=True) or []
    mine = [e for e in q if isinstance(e, dict) and e.get("relic") == "BladeOfTheAncestors"]
    assert mine and mine[0]["queued"] and mine[0]["dispatched"], (
        "le crit doit ENFILER le re-declenchement, pas retirer sur place : %s" % (q,))
    assert _crit(st, uthar) != base, "le buff ne doit PAS tomber avant le drain"
    drained = process_pending_triggered_abilities(st) or []
    assert [d for d in drained if isinstance(d, dict) and d.get("relic") == "BladeOfTheAncestors"]
    assert _crit(st, uthar) == base, "le drain doit retirer les DEUX piles et rendre les stats"


def test_le_reset_ne_fire_pas_sans_crit_ni_pour_un_autre_attaquant():
    """`WasCrit` et `get_OwnerIsCaster` mordent tous les deux."""
    from engine.runner.operations.triggers.dispatch.attack import finish_attack_triggers
    st, uthar, killer, victim = _blade_state(level=3)
    unit_death_triggers(st, victim, killer)
    buffed = _crit(st, uthar)
    finish_attack_triggers(st, uthar, victim, ranged=False, is_crit=False)   # pas de crit
    process_pending_triggered_abilities(st)
    assert _crit(st, uthar) == buffed
    finish_attack_triggers(st, killer, victim, ranged=False, is_crit=True)   # pas le porteur
    process_pending_triggered_abilities(st)
    assert _crit(st, uthar) == buffed


def test_la_magnitude_lit_le_niveau_TERTIAIRE_et_non_celui_des_passifs():
    """`passive_ability_level` vaut 50 sur tout runner normalise et
    `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE au dernier palier : lire le mauvais
    slot rendrait TOUJOURS `extraCritDmg[10]`. Le bras mute doit DIVERGER -- sinon le montage ne
    separe pas les deux champs."""
    from engine.entities.effects.magnitude import ability_var
    exp = int(ability_var("BladeOfTheAncestors", "extraCritDmg", 3, multiplier_pct=100))
    clamped = int(ability_var("BladeOfTheAncestors", "extraCritDmg", 50, multiplier_pct=100))
    assert clamped != exp, "ce niveau ne separe RIEN -- changer de bras"
    st, uthar, killer, victim = _blade_state(level=3)
    before = _crit(st, uthar)
    unit_death_triggers(st, victim, killer)
    assert _crit(st, uthar)[1] - before[1] == exp

    st2, uthar2, killer2, victim2 = _blade_state(level=3)
    saved = V._relic_ability_state
    try:
        V._relic_ability_state = lambda ctx, nm: (getattr(ctx, "passive_ability_level", None), 100)
        b2 = _crit(st2, uthar2)
        unit_death_triggers(st2, victim2, killer2)
        assert _crit(st2, uthar2)[1] - b2[1] == clamped
    finally:
        V._relic_ability_state = saved


# --------------------------------------------------------------------------- 5. VOLUMM : les gates
#: Les traits REELS de Vynn (`gameconfig.units.lineup.votanIronmaster.traits`). `Mechanic` = il
#: REPARE ; ce n'est PAS `Mechanical` (= il EST une machine), qui fermerait le gate
#: `UnitExtensions$$IsAffectedByHealType(unit, 0)` de `HealUnitOperation` -- une machine se REPARE,
#: elle ne se SOIGNE pas. Or le natif construit bien un `DSLBehaviors$$Heal` ici (mesure live
#: #1001 : Vynn gagne `hpToHeal` PV), donc le porteur DOIT etre soignable.
VYNN_TRAITS = ("Hero", "PrioritisedEfficiency", "Mechanic")


def _volumm_state(level=3, vynn_hp=1000, vynn_max=60000):
    st = State()
    st.effects = EffectsState()
    vynn = _unit(st, VYNN, 1, VYNN_TRAITS, hp=vynn_hp, hp_max=vynn_max,
                 tertiary="VolummsMasterArtifice", tertiary_level=level)
    ally = _unit(st, "ally", 1, (UnitTrait.Mechanical.name,), hp=1000, hp_max=900000)
    ecog = _unit(st, "votanSmnEcog", 1, (UnitTrait.Mechanical.name,), hp=100, hp_max=100,
                 parent=vynn)
    autre = _unit(st, "autre", 1, (UnitTrait.Mechanical.name,), hp=100, hp_max=100)
    return st, vynn, ally, ecog, autre


def _nr_hp(level):
    from engine.entities.effects.magnitude import ability_var
    return (int(ability_var("VolummsMasterArtifice", "nrOfRepairs", level, multiplier_pct=100)),
            int(ability_var("VolummsMasterArtifice", "hpToHeal", level, multiplier_pct=100)))


def test_le_seuil_est_sur_le_compteur_DEJA_incremente():
    """`AddPersistentData(+1) & If(compteur >= nrOfRepairs, ...)` : l'increment est le terme de
    GAUCHE du dernier `op_BitwiseAnd`, donc il s'execute AVANT que le `If` ne relise le compteur.
    Le soin tombe a la N-ieme reparation, `N = nrOfRepairs` -- et c'est l'INVERSE de
    `DaemonfleshPlate`, qui teste AVANT d'incrementer et compare a `nrOfAttacks - 1`."""
    st, vynn, ally, _ecog, _autre = _volumm_state(level=3)
    nr, hp = _nr_hp(3)
    hc = st.get_entity(vynn).get_component(HealthComponent)
    rangs = []
    for i in range(nr + 1):
        out = unit_repaired_triggers(st, vynn, ally) or []
        ev = [e for e in out if isinstance(e, dict) and e.get("relic") == "VolummsMasterArtifice"]
        assert len(ev) == 1
        if ev[0]["healed"]:
            rangs.append((i + 1, ev[0]["healed"], ev[0]["counter"]))
    assert [r[0] for r in rangs] == [nr], (
        "le soin doit tomber a la %d-ieme reparation EXACTEMENT, il tombe a %s" % (nr, rangs))
    assert rangs[0][1] == hp, "montant soigne %s, attendu hpToHeal[3] = %d" % (rangs[0][1], hp)
    assert int(hc.hp) == 1000 + hp


def test_le_compteur_repart_a_ZERO_donc_le_cycle_RECOMMENCE():
    """`SetPersistentData(..., Direct(0))`, PAS un `ClearPersistentData` : la cle reste posee a 0.
    Observable : un SECOND soin au rang `2 x nrOfRepairs` (mesure live #1001 : trois soins en une
    partie quand les E-COGs reparent aussi)."""
    st, vynn, ally, _ecog, _autre = _volumm_state(level=3)
    nr, hp = _nr_hp(3)
    soins = []
    for i in range(2 * nr):
        out = unit_repaired_triggers(st, vynn, ally) or []
        ev = [e for e in out if isinstance(e, dict) and e.get("relic") == "VolummsMasterArtifice"]
        if ev and ev[0]["healed"]:
            soins.append(i + 1)
    assert soins == [nr, 2 * nr], "rangs des soins = %s, attendu [%d, %d]" % (soins, nr, 2 * nr)


def test_la_voie_PARENT_compte_et_un_reparateur_etranger_NON():
    """`AreEqual(Parent(Caster@+0x48, root = false), Owner@+0x30) | get_OwnerIsCaster` : un E-COG
    de Vynn fait monter le compteur, une autre unite mecanique alliee NON."""
    nr, _hp = _nr_hp(3)
    st, vynn, ally, ecog, autre = _volumm_state(level=3)
    for _ in range(nr):
        out = unit_repaired_triggers(st, ecog, ally) or []
        ev = [e for e in out if isinstance(e, dict) and e.get("relic") == "VolummsMasterArtifice"]
        assert len(ev) == 1, "la voie Parent(Caster) == Owner ne compte pas"
    assert ev[0]["healed"], "le seuil doit etre franchi par les seules reparations de l'E-COG"

    st2, vynn2, ally2, _e2, autre2 = _volumm_state(level=3)
    for _ in range(nr + 3):
        out = unit_repaired_triggers(st2, autre2, ally2) or []
        assert not [e for e in out
                    if isinstance(e, dict) and e.get("relic") == "VolummsMasterArtifice"], (
            "un reparateur sans lien de parente avec Vynn ne doit RIEN compter")


def test_le_porteur_mort_ne_compte_plus():
    """`On(0x30, ownerNeedsToBeAlive = 1)`."""
    st, vynn, ally, _e, _a = _volumm_state(level=3)
    st.get_entity(vynn).get_component(UnitComponent).alive = False
    out = unit_repaired_triggers(st, vynn, ally) or []
    assert not [e for e in out if isinstance(e, dict) and e.get("relic") == "VolummsMasterArtifice"]


def test_volumm_lit_le_niveau_TERTIAIRE():
    """Meme cran que pour `BladeOfTheAncestors` : au niveau 3, `nrOfRepairs` vaut 8 et `hpToHeal`
    6509 ; une lecture du niveau des PASSIFS (50, CLAMPE) donnerait 7 et 8729."""
    nr3, hp3 = _nr_hp(3)
    nr50, hp50 = _nr_hp(50)
    assert (nr3, hp3) != (nr50, hp50), "ce niveau ne separe RIEN -- changer de bras"
    st, vynn, ally, _e, _a = _volumm_state(level=3)
    assert VA.relic_vars(st, vynn) == (nr3, hp3)
    saved = VA.triggered_ability_state
    try:
        VA.triggered_ability_state = lambda s, u, n: (50, 100)
        assert VA.relic_vars(st, vynn) == (nr50, hp50)
    finally:
        VA.triggered_ability_state = saved


def test_sans_relique_montee_aucun_des_deux_ne_fire():
    """Le rail #357 est ce qui inscrit une relique EQUIPEE : sans `UnitContext.tertiary_ability`,
    ni Uthar ni Vynn ne portent quoi que ce soit (leur kit gameconfig ne contient PAS ces
    abilities -- elles n'existent que comme item)."""
    st = State()
    st.effects = EffectsState()
    uthar = _unit(st, UTHAR, 1, (UnitTrait.Hero.name,))
    vynn = _unit(st, VYNN, 1, VYNN_TRAITS, hp=1000, hp_max=60000)
    killer = _unit(st, "alliedHero", 1, (UnitTrait.Hero.name,))
    victim = _unit(st, "victim", 2, (), alive=False, hp=0, hp_max=10)
    ally = _unit(st, "ally", 1, (UnitTrait.Mechanical.name,), hp=1, hp_max=900000)
    assert not [e for e in (unit_death_triggers(st, victim, killer) or [])
                if isinstance(e, dict) and e.get("relic")]
    assert not [e for e in (unit_repaired_triggers(st, vynn, ally) or [])
                if isinstance(e, dict) and e.get("relic")]
    assert _crit(st, uthar) == _crit(st, uthar)
