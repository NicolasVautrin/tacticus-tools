"""CLIQUET `FloatingDeath` (#1065) -- la DETONATION du Spore Mine, et les gates de ses trois faces.

Le passif `FloatingDeath` (`TriggeredAbilityType` 0x4db = 1243) des deux Spore Mines tyranides
(`tyranSmnSporeMine`, `tyranNpc6SporeMine`) etait classe **ZONE-GRISE** : son nom est reference en
code, mais `1243` n'etait dans AUCUN des sept registres de `dispatch/registry.py`. Ce qui etait
porte, c'etait sa CINQUIEME face -- l'ACTIVE `FloatingDeath_NormalAttack` (1146), substituee par
`services/custom_normal_attack.py`. La MECANIQUE, elle, ne s'executait pas.

FACE MESUREE ICI -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_AttackAbility` :

    $$CreateTrigger   = On(0x2 = PreUnitDeath_2, ownerNeedsToBeAlive = 0)
                        op_BitwiseAnd get_OwnerIsTarget
                        op_BitwiseAnd op_LogicalNot(TargetIsOverkilled)
    $$CreateBehaviour = DSLBehaviors$$AttackWithAbilityDamage(
                            Owner@DSLSelectors+0x30,
                            DSLSelectors$$AdjacentEnemies(Owner, unique = 1, selectionType = 3),
                            BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                            DSLSelectors$$DamageProfileFromConfig(config),
                            DSLFormulas$$Direct(GetNumberConstant(config, 0x2f = nrOfHits)),
                            AbilityOrEffect(this), 2)

MONTAGE -- porteur SUMMON, donc GREFFE (case-92 SS5bis) : `tyranSmnSporeMine` est spawne par
`SporeMineLauncher` / `BioMinefield` / `HyperCorrosiveAcid` et **ne se COMMANDE pas** (#291) ; or il
faut ici choisir QUI le tue et QUAND (la detonation doit partir hors overkill, sur une cible
adjacente OBSERVABLE). `FloatingDeath` se greffe : sa magnitude vient de la config de l'ability, son
selecteur ne lit ni stat ni trait du caster.

    greffon = `necroDestroyer` (a-units, HERO du pool), `replace = True` -> passifs natifs ecartes ;
    tueur   = `astraBullgryn` (p-units, HERO MELEE du pool), AU CONTACT.

C'est donc le TUEUR qui encaisse la detonation : il est le seul ennemi adjacent au porteur au moment
de sa mort. `--hp-target` calibre la mort SANS overkill -- `IsOverkill` compare
`(maxHP - curHP) + dmg` a `2 x maxHP`, donc des PV LARGEMENT superieurs au coup fatal suffisent a
rester sous la borne, alors que la SERIE de coups d'une attaque normale tue quand meme.

CE QUE CE FICHIER NE COUVRE PAS, et c'est ecrit plutot que tu : les faces CHAINE
(`FloatingDeath_ChainAbility`, qui exige DEUX porteurs adjacents de meme `visualId`) et MOUVEMENT
(`FloatingDeath_ExtraMovementAbility`, qui exige une bulle `Synapse` d'equipe) ne sont gardees ici
que par leurs GATES offline. Residu `#1065-r1`.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # LE PORT lui-meme : les trois classes du cluster et le registre qui les monte.
        "scripts/python/engine/runner/operations/triggers/loki/floating_death.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        # LES VECTEURS D'EVENEMENT des trois faces : mort (`On(0)`/`On(2)`) et turn-start
        # (`On(0x13)`), plus le pipeline de degat qui les emet.
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
        "scripts/python/engine/runner/operations/damage.py",
        # LES FEUILLES DSL consommees par les behaviours.
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/effects/aura.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/services/battle_query.py",
        # LE MONTAGE : harnais, greffe catalogue, build de runner.
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/rl_duel.py",
        # La magnitude vient du gameconfig (minDmg/maxDmg/nrOfHits/damageProfile de `FloatingDeath`).
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": True,
    "raison": "Confrontation AU NATIF : les PV du tueur apres detonation sortent du jeu, pas du "
              "depot, et le porteur est monte par GREFFE catalogue. Se rejoue a chaque passe live.",
}

import os        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import sys       # noqa: E402

import pytest    # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import NO_STEP, charge_regime                 # noqa: E402,F401  (fixture)

from engine.dsl.event_trigger_type import EventTriggerType        # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.runner.components import HealthComponent, UnitComponent        # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent   # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS   # noqa: E402
from engine.runner.operations.triggers.loki.floating_death import (          # noqa: E402
    FLOATING_DEATH, FLOATING_DEATH_ID, FloatingDeathAttackAbility,
    FloatingDeathChainAbility, FloatingDeathExtraMovementAbility)

GRAFT = "necroDestroyer"        # a-units : le PORTEUR greffe, celui qui meurt et detone
KILLER = "astraBullgryn"        # p-units : HERO MELEE du pool, le seul ennemi adjacent au porteur
#: PV du porteur : tres au-dessus du coup fatal (donc mort HORS overkill), assez bas pour qu'UNE
#: serie de coups d'attaque normale suffise a tuer. `--hp-target` met aussi Armor/FixedArmor a 0.
TARGET_HP = "9000"


@pytest.fixture(scope="module")
def grafted_bc(tmp_path_factory):
    """Seed BC ou `FloatingDeath` est GREFFE sur `necroDestroyer`. DEUX ecritures obligatoires
    (`BC.Units[].PassiveAbilities` + `BC.Abilities.PassiveAbilities[<nom>]`). Un montage rate doit
    ASSERTER, jamais skipper."""
    import catalog_inject as CI
    out = tmp_path_factory.mktemp("floatingdeath") / "grafted-bc.json"
    p, reports = CI.write_grafted_seed_bc(str(out), ["%s:%s" % (GRAFT, FLOATING_DEATH)])
    assert reports[0]["abilityId"] == FLOATING_DEATH_ID, reports
    assert reports[0]["passiveAbilitiesAfter"] == [FLOATING_DEATH_ID], reports
    return str(p)


@pytest.fixture(scope="module")
def mine(charge_regime, grafted_bc):
    return charge_regime(p_units=KILLER, a_units="%s,necroWarden" % GRAFT,
                         extra=["--seed-bc", grafted_bc, "--hp-target", TARGET_HP])


def _hp_live(h, uid):
    dv = h.dview()
    for u in h.alive(dv):
        if u["id"] == uid:
            return int(u.get("health") or u.get("hp") or 0)
    return 0            # absent des vivants = mort


def _hp_off(st, uid):
    e = st.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return int(hc.hp) if hc is not None else 0


def _alive_off(st, uid):
    e = st.get_entity(uid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return bool(uc is not None and uc.alive)


# ------------------------------------------------------------------ gardes STRUCTURELLES (offline)

def test_le_passif_est_au_registre():
    """`1243` est desormais dans un registre EXECUTABLE -- c'est CE fait qui fait basculer le
    verdict d'audit de ZONE-GRISE a PORTE. Les TROIS faces mecaniques y sont ; la QUATRIEME
    (`FloatingDeath_InitAbility`) est volontairement absente (son `AddTrait(PermaDeath)` est
    idempotent : le trait est deja dans le kit statique des deux porteurs)."""
    got = ABILITY_TRIGGERS.get(FLOATING_DEATH)
    assert got == [FloatingDeathAttackAbility, FloatingDeathChainAbility,
                   FloatingDeathExtraMovementAbility], got
    assert FLOATING_DEATH_ID == int(TriggeredAbilityType.FloatingDeath) == 1243


def test_gates_des_trois_faces_offline():
    """Chaque face ecoute SON evenement et porte SON gate. Le cran discriminant est l'OVERKILL :
    `FloatingDeath_AttackAbility` construit son `On(2)` a la main et ajoute
    `op_LogicalNot(TargetIsOverkilled)`, la ou les deux novas de `loki/death_nova.py` passent par
    `OnDeathEvent(a = 1)` et partent MEME en overkill. Confondre les deux aurait ete invisible."""
    a = FloatingDeathAttackAbility(owner_id=5)
    assert int(a.event_id) == int(EventTriggerType.PreUnitDeath_2) == 2
    assert a.fire_on_death is True, "l'owner EST le mourant -> bypass du gate `owner vivant`"
    ev = TriggerEvent(int(EventTriggerType.PreUnitDeath_2), 9, 5, ranged=False, profile=None,
                      dying_id=5, killer_id=9, overkill=False)
    assert a.matches(None, ev) is True
    ev_ovk = TriggerEvent(int(EventTriggerType.PreUnitDeath_2), 9, 5, ranged=False, profile=None,
                          dying_id=5, killer_id=9, overkill=True)
    assert a.matches(None, ev_ovk) is False, "NOT TargetIsOverkilled : un overkill ETEINT la detonation"
    ev_autre = TriggerEvent(int(EventTriggerType.PreUnitDeath_2), 9, 6, ranged=False, profile=None,
                            dying_id=6, killer_id=9, overkill=False)
    assert a.matches(None, ev_autre) is False, "get_OwnerIsTarget : c'est LE PORTEUR qui doit mourir"

    c = FloatingDeathChainAbility(owner_id=5)
    assert int(c.event_id) == int(EventTriggerType.UnitDeath) == 0
    assert c.fire_on_death is False, "`ownerNeedsToBeAlive = 1` -- la mine qui reagit est VIVANTE"

    m = FloatingDeathExtraMovementAbility(owner_id=5)
    assert int(m.event_id) == int(EventTriggerType.TurnStart_Other) == 19


# ------------------------------------------------------------------ confrontation LIVE

def test_detonation_frappe_le_tueur_adjacent(mine):
    """CAS PRINCIPAL -- la mort du porteur (hors overkill) declenche l'attaque AoE sur ses ennemis
    ADJACENTS, ici le tueur au contact. On confronte les PV du TUEUR, pas ceux de la victime : la
    detonation est le SEUL canal qui puisse les faire baisser pendant SA propre attaque."""
    rec = mine.run(caster_visual=KILLER, regime=NO_STEP)
    if rec is None:
        pytest.skip("geometrie NO_STEP non realisable sur ce board")
    if not rec["live_ok"]:
        pytest.skip("attaque normale live refusee")
    killer_hp_live = _hp_live(mine, rec["caster"])
    off = mine.replay_offline(rec)
    st = off["state"]
    assert not _alive_off(st, rec["target"]), (
        "le porteur doit MOURIR de l'attaque (sinon le trigger n'est pas exerce) -- "
        "PV offline restants %d, coups %s" % (_hp_off(st, rec["target"]), off["per_hit_all"]))
    assert killer_hp_live > 0, (
        "le tueur ne doit pas mourir de la detonation, sinon les PV live ne sont plus lisibles")
    assert _hp_off(st, rec["caster"]) == killer_hp_live, (
        "DETONATION : PV du tueur -- live %d, offline %d (delta %d). Un offline EGAL aux PV pleins "
        "signifie que la detonation n'est pas jouee ; un ecart signifie une magnitude fausse."
        % (killer_hp_live, _hp_off(st, rec["caster"]),
           _hp_off(st, rec["caster"]) - killer_hp_live))


def test_le_natif_detone_vraiment(mine):
    """CONTRE-EPREUVE du montage : le tueur DOIT avoir perdu des PV cote LIVE. Sans ce cran, le
    test ci-dessus passerait pour une raison triviale (aucune detonation nulle part, deux zeros
    egaux). On compare deux mesures LIVE, jamais le port."""
    rec = mine.run(caster_visual=KILLER, regime=NO_STEP)
    if rec is None or not rec["live_ok"]:
        pytest.skip("montage NO_STEP indisponible")
    off = mine.replay_offline(rec)
    if _alive_off(off["state"], rec["target"]):
        pytest.skip("le porteur n'est pas mort sur cette passe -- rien a mesurer")
    hp_apres = _hp_live(mine, rec["caster"])
    hp_plein = _hp_off(mine.offline_state(rec), rec["caster"])
    assert hp_apres < hp_plein, (
        "le natif DOIT infliger la detonation au tueur adjacent -- PV avant %d, apres %d "
        "(si egal, le montage n'exerce pas la face)" % (hp_plein, hp_apres))
