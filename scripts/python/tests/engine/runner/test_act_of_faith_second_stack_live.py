"""2e stack CONDITIONNEL ActOfFaith (RighteousRepugnance / Morvenn Vahl) - replay MOTEUR offline (slice-20).

`IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour` (branche gshared param_3 != 0x20) =
    op_Addition(
        AddEffect(0x3f9, source=AbilityStateReference, target=Self@0x148),                    # [1] GARANTI
        If( HasTrait(killer@0x158, Imperial=0x1a) & AreFriends(killer@0x158, owner@0x148)
              & AreEqual(UnitNormalAttackType(killer@0x158), RighteousRepugnance_NormalAttack=1182)
              & IsMeleeAttack(...),
            Maybe( AddEffect(0x3f9), chance=ConfigVar(RighteousRepugnance=1107, killer, chance=0x3a=58) ) ) )  # [2]

Ce test valide le 2e stack CONDITIONNEL. Equipe : Morvenn Vahl (`adeptMorvenn`, passive RighteousRepugnance
-> normal-attack CONCRET 1182) + Canoness (`adeptCanoness`, porteuse du trait ActOfFaith). Morvenn (allie
Imperial) TUE un ennemi en MELEE -> la Canoness gagne un 2e stack ActOfFaith SSI le roll `chance` reussit.

Deterministe : le behaviour n'utilise le RNG QUE pour le `Maybe` du 2e stack -> le stub `_ForceRoll` force
le tirage (True/False) et enregistre la chance recue. La CHANCE elle-meme (ability_var `RighteousRepugnance.
chance` au niveau PASSIF de Morvenn, 40-60% selon niveau) est assertee separement (resolution
`ConfigVarForEntity` = mirror `ConfigVar(1107,killer,58)`, independante du RNG). Version- et seed-independant.

On confronte le LIVE via l'etat seede (`load_state` de la bataille reelle : team/faction/kit/niveaux) puis
on rejoue le behaviour MOTEUR (comme `test_act_of_faith_ability_reset_live`). Le behaviour est PUR stat-mod
(pas de board requis). VA: IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour (behaviour), IdunBattleLogic.Entities.DSLFormulas$$ConfigVar (ConfigVar), IdunBattleLogic.Entities.DSLSelectors$$UnitNormalAttackType (UnitNormalAttackType).
"""
from __future__ import annotations

import pytest

from engine.entities.stats import StatType
from engine.entities.effects.magnitude import ability_var
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.formulas import UnitNormalAttackType, ConfigVarForEntity
from engine.entities.selectors.accessors import Actor
from engine.entities.selectors.tiles import Caster
from engine.entities.triggers import HasGrandAlliance, AreFriends
from engine.runner.snapshot import load_state
from engine.runner.components import StatsComponent
from engine.dsl.event_trigger_type import EventTriggerType
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.loki import (
    ActOfFaithAccumulateAbility, IMPERIAL_FACTIONS)
from engine.runner.abilities.behaviours.context import entities_from_state

MORVENN_VIS = "adeptMorvenn"        # passive RighteousRepugnance -> normal-attack concret 1182
SISTER_VIS = "adeptCanoness"        # porteuse ActOfFaith ; --crit -> cd != 0 (gate accumulate)
ENEMY_VIS = "necroDestroyer"
ENEMY2_VIS = "necroOverlord"        # 2e ennemi : la bataille survit (snapshot lisible)
# --crit patche TOUS les p-units -> la Canoness a CritDamage=250 (gate ActOfFaith satisfait).
BUILD = ["--roster", "1", "--p-units", f"{MORVENN_VIS},{SISTER_VIS}",
         "--a-units", f"{ENEMY_VIS},{ENEMY2_VIS}", "--crit", "100,250", "--hp-target", "800"]


class _ForceRoll:
    """rng stub : FORCE le tirage `next_bool` du `Maybe` (result True=roll reussit / False=echoue) et
    enregistre les chances recues. Le behaviour ActOfFaith accumulate n'appelle le rng QUE pour le Maybe
    du 2e stack -> ce stub suffit a rendre la branche deterministe (independante du seed)."""
    def __init__(self, result: bool):
        self.result = result
        self.chances: list[int] = []

    def next_bool(self, chance: int) -> bool:
        self.chances.append(int(chance))
        return self.result


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def test_act_of_faith_second_stack_righteous_repugnance(live_session, rpc, build_runner):
    """Morvenn (Imperial, normal-attack 1182) tue en melee -> 2e stack ActOfFaith sur la Canoness si roll OK."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not _ok(dec0):
        pytest.skip("decisionView KO")
    units0 = dec0.get("units") or []
    morvenn = next((u for u in units0 if u.get("visualId") == MORVENN_VIS and u.get("alive")), None)
    sister = next((u for u in units0 if u.get("visualId") == SISTER_VIS and u.get("alive")), None)
    if morvenn is None or sister is None:
        pytest.skip("Morvenn / Canoness absent(e) du deploiement")
    my_team = sister.get("team")
    enemy = next((u for u in units0 if u.get("team") != my_team and u.get("alive")), None)
    if enemy is None:
        pytest.skip("aucun ennemi vivant")
    morvenn_id, sister_id, enemy_id = morvenn["id"], sister["id"], enemy["id"]
    assert morvenn.get("team") == my_team, "Morvenn et Canoness pas dans la meme equipe (AreFriends KO)"

    def _fresh_state():
        st = load_state(dec0, ob0, snap0)
        si = st.get_entity(sister_id)
        mo = st.get_entity(morvenn_id)
        if (si is None or si.get_component(StatsComponent) is None
                or mo is None or mo.get_component(StatsComponent) is None):
            pytest.skip("Canoness/Morvenn sans StatsComponent offline (combatSnapshot ne couvre pas)")
        return st

    # === (0) La Canoness porte bien ActOfFaith (crit de base != 0, gate accumulate) ===
    st = _fresh_state()
    ctx_sis = st.get_entity(sister_id).get_component(StatsComponent).ctx
    base_cd = ctx_sis.stat(StatType.CRIT_DAMAGE)
    if not base_cd:
        pytest.skip(f"Canoness sans crit de base (cd={base_cd}) - gate ActOfFaith")

    # === (1) NOEUDS du 2e stack : resolution offline correcte (kit / faction / equipe / chance) ===
    ent = entities_from_state(st, sister_id, enemy_id, actor_id=morvenn_id)   # caster=sister, actor=morvenn, target=enemy
    na = UnitNormalAttackType(Actor()).evaluate(ent)
    assert na == int(ActiveAbilityType.RighteousRepugnance_NormalAttack), (
        f"UnitNormalAttackType(Morvenn)={na}, attendu 1182 (porteur RighteousRepugnance)")
    assert HasGrandAlliance(Actor(), IMPERIAL_FACTIONS).evaluate(ent), "Morvenn non-Imperial (faction)"
    assert AreFriends(Actor(), Caster()).evaluate(ent), "Morvenn/Canoness non allies (AreFriends)"

    mv_passive = getattr(st.get_entity(morvenn_id).get_component(StatsComponent).ctx,
                         "passive_ability_level", None)
    exp_chance = int(ability_var("RighteousRepugnance", "chance", mv_passive) or 0)
    if exp_chance <= 0:
        pytest.skip(f"chance non resoluble offline (passive_ability_level Morvenn={mv_passive}) - "
                    f"gap tierce-niveau, cf. tache #1")
    got_chance = int(ConfigVarForEntity("RighteousRepugnance", "chance", Actor(), slot="passive")
                     .evaluate(ent) or 0)
    assert got_chance == exp_chance, (
        f"ConfigVarForEntity chance={got_chance} != ability_var {exp_chance} (passive_lvl={mv_passive})")

    # Death event MELEE : killer=Morvenn (slot 0x158), dying=ennemi (slot 0x178), ranged=False.
    ev_melee = TriggerEvent(EventTriggerType.PreUnitDeath, morvenn_id, enemy_id, ranged=False,
                            profile=None, killer_id=morvenn_id, dying_id=enemy_id)

    # === (2) ROLL OK + kill MELEE -> 2 stacks (base [1] + conditionnel [2]) ===
    st_ok = _fresh_state()
    st_ok.rng = _ForceRoll(True)
    res_ok = ActOfFaithAccumulateAbility(sister_id).execute_behaviour(st_ok, ev_melee)
    assert res_ok and res_ok.get("stacks_added") == 2, (
        f"roll OK + melee : attendu 2 stacks, obtenu {res_ok and res_ok.get('stacks_added')}")
    assert st_ok.rng.chances == [exp_chance], (
        f"Maybe atteint avec la mauvaise chance : {st_ok.rng.chances} != [{exp_chance}]")
    cd_delta_2 = res_ok.get("cd_delta")

    # === (3) ROLL KO + kill MELEE -> 1 stack (base seul ; la condition reste vraie -> Maybe atteint) ===
    st_ko = _fresh_state()
    st_ko.rng = _ForceRoll(False)
    res_ko = ActOfFaithAccumulateAbility(sister_id).execute_behaviour(st_ko, ev_melee)
    assert res_ko and res_ko.get("stacks_added") == 1, (
        f"roll KO + melee : attendu 1 stack, obtenu {res_ko and res_ko.get('stacks_added')}")
    assert st_ko.rng.chances == [exp_chance], (
        f"cond vraie -> Maybe DOIT etre atteint meme si roll KO : {st_ko.rng.chances}")
    # stat-mod ADDITIF par stack : 2 stacks -> boost crit-damage = 2x celui d'1 stack.
    assert cd_delta_2 == 2 * res_ko.get("cd_delta"), (
        f"cd_delta 2-stacks {cd_delta_2} != 2x 1-stack {res_ko.get('cd_delta')} (stat-mod non additif)")

    # === (4) kill RANGED -> IsMeleeAttack False -> cond False (court-circuit) -> 1 stack, Maybe NON atteint ===
    ev_ranged = TriggerEvent(EventTriggerType.PreUnitDeath, morvenn_id, enemy_id, ranged=True,
                             profile=None, killer_id=morvenn_id, dying_id=enemy_id)
    st_rng = _fresh_state()
    st_rng.rng = _ForceRoll(True)   # roll force TRUE mais ne DOIT PAS etre consomme (cond False)
    res_rng = ActOfFaithAccumulateAbility(sister_id).execute_behaviour(st_rng, ev_ranged)
    assert res_rng and res_rng.get("stacks_added") == 1, (
        f"kill RANGED : attendu 1 stack (2e branche inerte), obtenu {res_rng and res_rng.get('stacks_added')}")
    assert st_rng.rng.chances == [], (
        f"kill RANGED : cond False -> le Maybe ne doit PAS etre atteint, chances={st_rng.rng.chances}")
