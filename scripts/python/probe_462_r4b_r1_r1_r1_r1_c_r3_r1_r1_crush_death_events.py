"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r1 / -r2 / -r3 -- le crush d'un `Steppable` PUBLIE ses evenements
de mort, avec sa RAISON, et la mine Haywire les CONSOMME.

La tranche precedente (`-c-r3-r1`) avait porte le RETRAIT des effets et laisse l'EMISSION dehors,
blast radius mesure a l'appui. Ce probe MESURE ce que l'emission change, dans les trois volets que
la tranche ferme :

  --step emission      : les QUATRE evenements que le port n'emettait pas (`On(1)`, `On(2)`, `On(0)`,
                         `On(0x36)`) partent desormais au crush, et `UnitComponent.death_source`
                         porte `(mover, DamageReason.Steppable, None)`. Contre-epreuve
                         `--mutate sans-emission` = l'etat d'AVANT la tranche.
  --step consommateurs : le BLAST RADIUS, joue plutot qu'inventorie -- deux montages CIBLES ou le
                         MOVER porte le trait/passif concerne (`ActOfFaith`, `TheBetrayer`), chacun
                         avec son TEMOIN (meme montage, AUCUN crush).
  --step haywire       : `HaywireMineSteppableAbility` (`-r3`) -- l'ability qui n'existe QUE pour ce
                         regime. Trois bras : ennemi NON-mecanique (1 attaque), ennemi MECANIQUE
                         (2 attaques : le `If(HasTrait(Actor, Mechanical))` du behaviour), ALLIE
                         (aucune -- gate `AreEnemies`).
  --step blast         : l'inventaire derive des registres (inchange, garde de non-regression).

Sortie ASCII (console cp1252). Aucun runner, aucun RPC : 100 % offline.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.entities.damage_reason import DamageReason                   # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,   # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.triggers.base import EffectTrigger, TriggerEvent   # noqa: E402
from engine.runner.operations.triggers.dispatch import registry as REG   # noqa: E402
from engine.runner.state import State                                    # noqa: E402

# Les CINQ evenements de `IdunBattle.Operations.KillUnitOperation$$Execute`, dans l'ordre du
# decompile (`+0x7cc`, `+0x979`, `+0xe49`, `+0xefc`, `+0x10ac` -- adresses de RETOUR relatives).
EVENTS_MORT = (int(EventTriggerType.PreUnitDeath), int(EventTriggerType.PreUnitDeath_2),
               int(EventTriggerType.UnitDeath), int(EventTriggerType.UnitDefeated),
               int(EventTriggerType.PostUnitKill))
# Le 5e a REJOINT la sequence en #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 : il etait publie par
# `after_move_triggers` (chemin MOVE seul, apres coup) -- ecart d'ORDRE et de COUVERTURE, ferme.
# La constante reste, a `None`, parce que les libelles ci-dessous en derivent ; `None` = plus
# aucun des cinq n'est hors sequence.
EVENT_HORS_SEQUENCE = None


def _nom(e: int) -> str:
    try:
        return EventTriggerType(int(e)).name
    except Exception:
        return "?"


# --------------------------------------------------------------------------- montages

def _mk_unit(st, visual, col, row, team, player=None, traits=None, hp=100, alive=True,
             passives=None, level=None, mult=100):
    from engine.entities.unit_context import UnitContext
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id=visual, alive=alive))
    e.add_component(PositionComponent(col, row))
    e.add_component(HealthComponent(hp=hp, hp_max=max(1, hp)))
    e.add_component(OwnerComponent(team=team, player=player if player is not None else team))
    ctx = UnitContext(entity_id=int(e.id), visual_id=visual)
    ctx.traits = list(traits or [])
    if passives is not None:
        ctx.passive_abilities = list(passives)
    if level is not None:
        ctx.passive_ability_level = int(level)
    ctx.ability_variables_multiplier = int(mult)
    e.add_component(StatsComponent(ctx))
    return int(e.id)


def _mk_crush(mover_traits=None, mover_passives=None, decoy_team=1, mover_team=1,
              mover_visual="mover"):
    """Un mover et un `Steppable` CO-LOCALISES : appeler `_kill_steppable_units` ecrase le second."""
    from engine.entities.effects_state import EffectsState
    st = State()
    st.effects = EffectsState()
    mover = _mk_unit(st, mover_visual, 1, 1, mover_team, traits=mover_traits,
                     passives=mover_passives, hp=1000)
    decoy = _mk_unit(st, "genesSmnDecoy", 1, 1, decoy_team,
                     traits=[UnitTrait.Steppable.name, UnitTrait.Decoy.name], hp=1)
    return st, mover, decoy


class _SondeEvents(EffectTrigger):
    """Effet-trigger NU qui NOTE les evenements vus, sans muter. Porte par le MOVER (VIVANT)."""
    event_id = EVENTS_MORT[0]
    event_ids: tuple = EVENTS_MORT
    fire_on_death = False
    vus: list = []

    def matches(self, state, ev) -> bool:
        _SondeEvents.vus.append(int(ev.event_id))
        return False

    def execute_behaviour(self, state, ev):
        return None


def _effect_type_libre(base: int = 950001) -> int:
    et = base
    while et in REG.EFFECT_TRIGGERS:
        et += 1
    return et


# --------------------------------------------------------------------------- emission

def step_emission(mutate: str | None = None) -> int:
    """Les QUATRE evenements de mort partent-ils, et la RAISON est-elle gravee ?

    `--mutate sans-emission` remet `_kill_steppable_kill_unit` a l'etat d'AVANT la tranche (les
    trois `RemoveEffects` SEULS, aucun evenement, aucune `RecordDeathReason`) : il DOIT rendre
    `vus=[]` et `death_source=None`, sinon la mesure ne discrimine rien."""
    from engine.entities.effects.factory import EffectFactory
    from engine.runner.operations import movement as MV
    if mutate == "sans-emission":
        def _retrait_seul(state, dead_id, killer_id):
            from engine.runner.operations.damage import _kill_unit_remove_effects
            from engine.entities.kill_unit_step import KillUnitStep
            return [_kill_unit_remove_effects(state, dead_id, s)
                    for s in (KillUnitStep.PreUnitRemove, KillUnitStep.AfterUnitRemove,
                              KillUnitStep.AfterDeathTrigger)]
        MV._kill_steppable_kill_unit = _retrait_seul
        print("[emission] MUTATION `sans-emission` ACTIVE (etat d'AVANT -r1/-r2)")

    et = _effect_type_libre()
    REG.EFFECT_TRIGGERS[et] = [_SondeEvents]
    try:
        st, mover, decoy = _mk_crush()
        st.effects.add_effect(mover, EffectFactory.create(
            {"name": "SondeEvents", "effectType": int(et), "remaining": 0}, 100, None, None))
        _SondeEvents.vus = []
        tues = MV._kill_steppable_units(st, (1, 1), mover)
        vus = sorted(set(_SondeEvents.vus))
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)

    uc = st.get_entity(decoy).get_component(UnitComponent)
    print("[emission] crushes=%s" % (tues,))
    print("[emission] evenements publies par la sequence de mort : %s"
          % ([("%d %s" % (e, _nom(e))) for e in vus],))
    print("[emission] death_source du crushe : %s (attendu (mover=%d, %d Steppable, None))"
          % (uc.death_source, mover, int(DamageReason.Steppable)))
    attendus = [e for e in EVENTS_MORT
                if EVENT_HORS_SEQUENCE is None or e != EVENT_HORS_SEQUENCE]
    print("[emission] LECTURE : attendus %s -- les CINQ depuis"
          % (sorted(attendus),))
    print("[emission]           #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 (`On(0x35)` a rejoint la sequence).")
    return 0


# --------------------------------------------------------------------------- consommateurs

def _fire_actofaith(crush: bool):
    """MOVER porteur du trait `ActOfFaith` : son accumulation ecoute `On(1)` et teste
    `AreFriends(killer|dying, owner) & HasTrait(Imperial)`. Le TUEUR d'un crush est le mover
    lui-meme -> le trigger fire des que l'evenement part.

    ⚠ Le `HasTrait(26 = Imperial)` du natif se lit cote port sur la FACTION gameconfig
    (`act_of_faith._faction_id` / `IMPERIAL_FACTIONS`), pas sur la liste de traits : le montage
    doit donc porter un `visualId` REEL de faction imperiale, pas un nom synthetique."""
    from engine.entities.stats import StatType
    from engine.runner.operations import movement as MV
    st, mover, _decoy = _mk_crush(mover_traits=[UnitTrait.ActOfFaith.name],
                                  mover_visual="ultraTitus")
    sc = st.get_entity(mover).get_component(StatsComponent)
    sc.ctx.stats.set_stat_override(int(StatType.CRIT_DAMAGE), 150)   # `NOT(crit_damage == 0)`
    vus = []
    from engine.runner.operations.triggers.loki import act_of_faith as AOF
    orig = AOF.ActOfFaithAccumulateAbility.execute_behaviour
    AOF.ActOfFaithAccumulateAbility.execute_behaviour = \
        lambda self, state, ev: vus.append(int(ev.event_id))
    try:
        if crush:
            MV._kill_steppable_units(st, (1, 1), mover)
    finally:
        AOF.ActOfFaithAccumulateAbility.execute_behaviour = orig
    return len(vus)


def _fire_betrayer(crush: bool):
    """MOVER porteur du passif `TheBetrayer` : `On(1) & OwnerIsActor & NOT HasEffect(owner, 0x4f3)`."""
    from engine.runner.operations import movement as MV
    st, mover, _decoy = _mk_crush(mover_passives=["TheBetrayer"])
    vus = []
    from engine.runner.operations.triggers.loki import betrayer as B
    orig = B.TheBetrayerAddEffectAbility.execute_behaviour
    B.TheBetrayerAddEffectAbility.execute_behaviour = \
        lambda self, state, ev: vus.append(int(ev.event_id))
    try:
        if crush:
            MV._kill_steppable_units(st, (1, 1), mover)
    finally:
        B.TheBetrayerAddEffectAbility.execute_behaviour = orig
    return len(vus)


def step_consommateurs() -> int:
    """Le BLAST RADIUS **JOUE**, pas inventorie.

    Deux voies « owner = le MOVER » que la fiche `-c-r3-r1` avait nommees comme atteignables des le
    premier decoy ecrase. Chaque bras a son TEMOIN (meme montage, AUCUN crush) : sans lui, un zero
    ne distingue pas << le trigger ne fire pas >> de << le montage ne monte rien >>."""
    for nom, fn in (("ActOfFaith_Accumulate", _fire_actofaith),
                    ("TheBetrayer_AddEffect", _fire_betrayer)):
        temoin = fn(crush=False)
        avec = fn(crush=True)
        print("[consommateurs] %-24s TEMOIN(sans crush)=%d  AVEC crush=%d" % (nom, temoin, avec))
    print("[consommateurs] LECTURE : TEMOIN == 0 et AVEC > 0 => le crush REVEILLE ce consommateur.")
    print("[consommateurs] NON COUVERT ici : les 25 autres classes du blast radius -- verdict")
    print("[consommateurs]                   ANALYTIQUE par classe dans la case-doc (gate lu).")
    return 0


# --------------------------------------------------------------------------- haywire (-r3)

def _mk_mine_scene(stepper_traits, meme_equipe: bool):
    """Une mine `astarSmnHaywireMine` (equipe 1) et un stepper co-localise (equipe 1 ou 2)."""
    from engine.entities.effects_state import EffectsState
    st = State()
    st.effects = EffectsState()
    stepper = _mk_unit(st, "necroWarden", 1, 1, 1 if meme_equipe else 2,
                       traits=list(stepper_traits), hp=100000)
    mine = _mk_unit(st, "astarSmnHaywireMine", 1, 1, 1,
                    traits=[UnitTrait.Steppable.name], hp=0,
                    passives=["HaywireMineSteppable"], level=50, mult=180)
    return st, mine, stepper


def step_haywire() -> int:
    """`HaywireMineSteppableAbility` -- l'arbre `If(HasTrait(Actor, Mechanical), atk1 + atk2, atk1)`.

    On appelle le trigger DIRECTEMENT sur l'evenement `On(1)` du crush (le montage synthetique n'a
    pas de board, donc pas de vrai pipeline de move) : `matches` lit `death_source`, qu'on grave
    comme le fait `_kill_steppable_kill_unit`."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.loki.haywire_mine import HaywireMineSteppableAbility
    from engine.runner.prng import IntBasedMersenneTwister
    bras = (("ennemi NON-mecanique", ["Hero"], False),
            ("ennemi MECANIQUE    ", ["Hero", UnitTrait.Mechanical.name], False),
            ("ALLIE               ", ["Hero", UnitTrait.Mechanical.name], True))
    for nom, traits, ami in bras:
        st, mine, stepper = _mk_mine_scene(traits, ami)
        st.rng = IntBasedMersenneTwister(777)
        st.get_entity(mine).get_component(UnitComponent).alive = False
        AttackDamageOperation._record_death_reason(
            st, mine, stepper, None, damage_reason=int(DamageReason.Steppable))
        ev = TriggerEvent(int(EventTriggerType.PreUnitDeath), stepper, mine, ranged=False,
                          profile=None, killer_id=stepper, dying_id=mine)
        trig = HaywireMineSteppableAbility(mine)
        ok = trig.matches(st, ev)
        res = trig.execute_behaviour(st, ev) if ok else None
        hits = (res or {}).get("hits") or []
        print("[haywire] %s matches=%-5s attaques=%d profils=%s total=%s"
              % (nom, ok, len(hits), [h.get("profile") for h in hits],
                 (res or {}).get("total")))
    print("[haywire] LECTURE : NON-mecanique = 1 attaque (Blast) ; MECANIQUE = 2 (Blast + Energy) ;")
    print("[haywire]           ALLIE = matches FAUX (gate `AreEnemies`). Mesure LIVE de reference :")
    print("[haywire]           natif 1x18 Blast=1403 (ork) et 1x18 + 2x16 = 4473 (necroWarden).")
    return 0


# --------------------------------------------------------------------------- blast (inventaire)

def step_blast() -> int:
    """Inventaire DERIVE des registres -- garde de non-regression du compte."""
    import probe_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable as PR
    return PR.step_blast()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--step", required=True,
                   choices=["emission", "consommateurs", "haywire", "blast"])
    p.add_argument("--mutate", choices=["sans-emission"], default=None,
                   help="contre-epreuve (--step emission) : etat d'AVANT -r1/-r2")
    a = p.parse_args()
    if a.step == "emission":
        return step_emission(a.mutate)
    return {"consommateurs": step_consommateurs, "haywire": step_haywire,
            "blast": step_blast}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
