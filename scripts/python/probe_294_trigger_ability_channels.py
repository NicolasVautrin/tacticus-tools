"""#294 -- MONTAGE NOMME qui SEPARE les deux canaux `AbilityEntities` du port.

    `CurrentAbility`    = `AbilityEntities+0x60` -> `state.triggering_ability`   (nom historique)
    `TriggeringAbility` = `AbilityEntities+0x98` -> `state.trigger_ability_type` (#294)

`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit la MEME
`AbilityOrEffect(this.Id)` dans les deux, mais a deux MOMENTS differents :

    1. op_Implicit(this) -> Nullable<>..ctor -> ecrit entities+0x60          [CurrentAbility]
    2. copie de `entities` -> local
    3. behaviour.Execute(<la copie>)                                    <-- LE BEHAVIOUR
    4. op_Implicit(this) -> Nullable<>..ctor -> ecrit entities+0x98       [TriggeringAbility]
    5. copie de `entities` -> local
    6. <processor>.Publish(..., 0xd, <la copie>)   On(0xd = UnitTriggeredAbility)

Un montage qui n'exerce QU'UNE triggered-ability ne peut donc PAS distinguer les deux champs : ils
finissent tous deux a `this.Id`. La separation exige une CHAINE -- une triggered qui en engendre une
autre. C'est ce que ce montage construit, et c'est le seul livrable qui donne une valeur au canal.

--------------------------------------------------------------------------- LE MONTAGE (`chain`)

Trois triggered-abilities espionnes, montees dans un `State` nu (OFFLINE, deterministe, zero RNG,
zero runner) :

    A  On(9 = Attack)                 id = A_ID   -- gate : les DEUX canaux vierges (donc une seule
                                                    fois : c'est ce qui borne la recursion)
    B  On(0xd = UnitTriggeredAbility) id = B_ID   -- gate : mirror de `TriggeringAbilityIs(A_ID)`,
                                                    donc lecture de `+0x98`
    C  On(9 = Attack)                 id = None   -- pur observateur ; B emet un On(9) depuis son
                                                    behaviour, ce qui amene C sous la chaine

Deroule NATIF attendu, et ce que chaque etage etablit :

  | site                  | +0x60 (`triggering_ability`) | +0x98 (`trigger_ability_type`) | etablit                       |
  |-----------------------|------------------------------|--------------------------------|-------------------------------|
  | A.matches             | None                         | None                           | contexte vierge               |
  | A.execute_behaviour   | A_ID                         | **None**                       | +0x98 n'est PAS encore ecrit  |
  | B.matches             | None                         | **A_ID**                       | SEPARATION (None vs A_ID)     |
  | B.execute_behaviour   | **B_ID**                     | **A_ID**                       | SEPARATION, DEUX NON-NULS     |
  | C.matches (sous B)    | B_ID                         | A_ID                           | +0x60 herite, +0x98 NON       |
  | apres tout            | None                         | None                           | les deux restaures            |

La ligne `B.execute_behaviour` est LE livrable : c'est le seul point ou les deux canaux portent deux
valeurs NON NULLES DIFFERENTES. Tant qu'un montage ne l'atteint pas, un canal `+0x98` pose "en
aveugle" est indiscernable d'un alias de `+0x60`.

--------------------------------------------------------------- CONTRE-EPREUVES (`--mutate`)

Chacune neutralise UNE moitie du port et doit faire ROUGIR le montage :

  `before`  ecrit `+0x98` AVANT le behaviour au lieu d'apres  -> B voit `+0x98 = B_ID` : la
            separation disparait, les deux canaux redeviennent egaux
  `alias`   branche `+0x98` sur le MEME slot que `+0x60` (le piege que `case-292` nomme
            explicitement : "une ability future NE DOIT PAS reutiliser `State.triggering_ability`")
            -> le gate `TriggeringAbilityIs(A_ID)` de B lit `None` : B ne fire jamais
  `persist` supprime la restauration de `+0x98`                 -> l'id fuit d'une evaluation a la
            suivante (etat final non vierge)
  `noevent` supprime l'emission d'`On(0xd)`                     -> B ne fire jamais

Reproduire :

    cd scripts/python
    python probe_294_trigger_ability_channels.py
    python probe_294_trigger_ability_channels.py --mutate before
    python probe_294_trigger_ability_channels.py --mutate alias
    python probe_294_trigger_ability_channels.py --mutate persist
    python probe_294_trigger_ability_channels.py --mutate noevent
"""
from __future__ import annotations

import argparse
from typing import Optional

A_ID = 4242                 # ids ARBITRAIRES : le montage teste le CANAL, pas une ability reelle.
B_ID = 4343                 # Deux valeurs distinctes non nulles -- c'est tout ce qu'il leur faut.

MUTATIONS = ("before", "alias", "persist", "noevent")


def _snapshot(state) -> tuple:
    """(`+0x60`, `+0x98`) tels que les verrait un noeud DSL evalue ICI."""
    return (getattr(state, "triggering_ability", None),
            getattr(state, "trigger_ability_type", None))


def run(mutate: Optional[str] = None, verbose: bool = False) -> dict:
    """Monte la chaine A -> On(0xd) -> B -> On(9) -> C et rend la TRACE ordonnee des observations.

    Retour :
      `obs`      liste de `(site, plus0x60, plus0x98)` dans l'ordre d'evaluation
      `fires`    nb de passages par site (`A.exec`, `B.exec`, `C.matches`)
      `final`    (`+0x60`, `+0x98`) apres retour complet du dispatch
      `separated` True si AU MOINS un site voit deux valeurs NON NULLES DIFFERENTES
    """
    assert mutate in (None,) + MUTATIONS, f"mutation inconnue : {mutate}"
    from engine.runner.state import State
    from engine.runner.components import UnitComponent
    from engine.runner.operations.triggers.base import TriggeredAbility, TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    import engine.runner.operations.triggers.dispatch.core as CORE

    obs: list[tuple] = []
    fires: dict[str, int] = {}

    def _note(site: str, state) -> None:
        obs.append((site,) + _snapshot(state))
        fires[site] = fires.get(site, 0) + 1

    class _A(TriggeredAbility):
        """La triggered SOURCE. `On(9)`, id = A_ID."""
        event_id = EventTriggerType.Attack
        TRIGGERED_ABILITY_ID = A_ID

        def matches(self, state, ev):
            _note("A.matches", state)
            # Contexte vierge SEULEMENT : borne la recursion (le On(9) que B emet depuis son
            # behaviour porte `+0x60 = B_ID`, donc A n'y re-matche pas). Le natif s'en remet au cap
            # de phase (`GetTimesTriggeredThisPhase < 0x33`) ; ici on veut une trace COURTE et lisible.
            return _snapshot(state) == (None, None)

        def execute_behaviour(self, state, ev):
            _note("A.exec", state)
            return {"who": "A"}

    class _B(TriggeredAbility):
        """La triggered CHAINEE : elle ecoute l'evenement que A publie en sortant, et son gate est
        le mirror d'un `IdunBattleLogic.Entities.DSLTriggers$$TriggeringAbilityIs(A_ID)` -- donc une
        lecture de `AbilityEntities+0x98`, JAMAIS de `+0x60`."""
        event_id = EventTriggerType.UnitTriggeredAbility
        TRIGGERED_ABILITY_ID = B_ID

        def matches(self, state, ev):
            _note("B.matches", state)
            return getattr(state, "trigger_ability_type", None) == A_ID

        def execute_behaviour(self, state, ev):
            _note("B.exec", state)
            # Le behaviour ENGENDRE un evenement : c'est ce que le natif fait de son `+0x60` (il est
            # herite par l'attaque / le degat / la mort produits ici).
            CORE.evaluate_trigger_operation(state, TriggerEvent(
                EventTriggerType.Attack, ev.actor_id, ev.target_id, ranged=False, profile=None))
            return {"who": "B"}

    class _C(TriggeredAbility):
        """Pur observateur, SANS id : il ne pose aucun canal et ne republie donc rien."""
        event_id = EventTriggerType.Attack
        TRIGGERED_ABILITY_ID = None

        def matches(self, state, ev):
            _note("C.matches", state)
            return False

    state = State()
    e = state.add_entity(1)
    e.add_component(UnitComponent("spy", True))

    # `_publish_unit_triggered_ability` peut ne PAS exister : c'est l'etat du port AVANT #294, et le
    # probe doit pouvoir s'y executer pour rendre un ROUGE de MESURE (la chaine ne monte pas) plutot
    # qu'un crash d'attribut, qui n'apprendrait rien.
    _HAS_PUB = hasattr(CORE, "_publish_unit_triggered_ability")
    saved = (CORE.collect_triggered_abilities, CORE.collect_global_triggers,
             CORE.collect_effect_triggers,
             getattr(CORE, "_publish_unit_triggered_ability", None))
    CORE.collect_triggered_abilities = lambda s: [_A(1), _B(1), _C(1)]
    CORE.collect_global_triggers = lambda: []
    CORE.collect_effect_triggers = lambda s: []

    if mutate == "noevent":
        CORE._publish_unit_triggered_ability = lambda s, ev, entry: None
    elif mutate == "alias":
        # Le piege NOMME : reutiliser le canal `+0x60` pour `+0x98`.
        def _aliased(s, ev, entry):
            if entry.TRIGGERED_ABILITY_ID is None:
                return
            prev = s.triggering_ability
            s.triggering_ability = int(entry.TRIGGERED_ABILITY_ID)
            try:
                CORE.evaluate_trigger_operation(s, TriggerEvent(
                    EventTriggerType.UnitTriggeredAbility, ev.actor_id, ev.target_id,
                    ranged=ev.ranged, profile=ev.profile))
            finally:
                s.triggering_ability = prev
        CORE._publish_unit_triggered_ability = _aliased
    elif mutate == "persist":
        def _leaky(s, ev, entry):
            if entry.TRIGGERED_ABILITY_ID is None:
                return
            s.trigger_ability_type = int(entry.TRIGGERED_ABILITY_ID)   # jamais restaure
            CORE.evaluate_trigger_operation(s, TriggerEvent(
                EventTriggerType.UnitTriggeredAbility, ev.actor_id, ev.target_id,
                ranged=ev.ranged, profile=ev.profile))
        CORE._publish_unit_triggered_ability = _leaky

    try:
        if mutate == "before":
            # `+0x98` pose AVANT le behaviour : on ne peut pas le simuler depuis le seul publieur, il
            # faut envelopper `execute_behaviour` de chaque entree -- exactement l'erreur de moment.
            for cls in (_A, _B):
                _orig = cls.execute_behaviour

                def _wrapped(self, s, ev, _orig=_orig):
                    s.trigger_ability_type = int(type(self).TRIGGERED_ABILITY_ID)
                    return _orig(self, s, ev)
                cls.execute_behaviour = _wrapped
        CORE.evaluate_trigger_operation(state, TriggerEvent(
            EventTriggerType.Attack, 1, 2, ranged=False, profile=None))
    finally:
        (CORE.collect_triggered_abilities, CORE.collect_global_triggers,
         CORE.collect_effect_triggers, _pub) = saved
        if _HAS_PUB:
            CORE._publish_unit_triggered_ability = _pub
        else:
            CORE.__dict__.pop("_publish_unit_triggered_ability", None)
        # `_A`/`_B`/`_C` sont LOCALES a `run()` : la mutation `before`, qui enveloppe leur
        # `execute_behaviour`, meurt avec elles -- rien a restaurer.

    separated = [o for o in obs if o[1] is not None and o[2] is not None and o[1] != o[2]]
    r = {"mutate": mutate, "obs": obs, "fires": fires, "final": _snapshot(state),
         "separated": bool(separated), "separating_sites": [o[0] for o in separated],
         "a_id": A_ID, "b_id": B_ID}
    if verbose:
        print(f"[probe294] mutate={mutate or 'none'}")
        for site, cur, trg in obs:
            print(f"  {site:<12} +0x60={cur!s:<6} +0x98={trg!s:<6}")
        print(f"  final       +0x60={r['final'][0]!s:<6} +0x98={r['final'][1]!s:<6}")
        print(f"  separated={r['separated']} sites={r['separating_sites']}")
    return r


def site(r: dict, name: str, nth: int = 0) -> tuple:
    """La `nth`-ieme observation du site `name`, sous forme (`+0x60`, `+0x98`).

    Leve si le site n'a pas ete atteint -- un site MANQUANT est une mesure, pas un vide a ignorer
    (c'est exactement ce que rendent les mutations `alias` et `noevent`)."""
    hits = [o for o in r["obs"] if o[0] == name]
    assert len(hits) > nth, (
        f"site '{name}' non atteint (occurrence {nth}) -- la chaine n'est pas montee ; "
        f"sites observes = {[o[0] for o in r['obs']]}")
    return (hits[nth][1], hits[nth][2])


def assert_channels_separated(r: dict) -> None:
    """LA garde du montage : les cinq faits que le decompile impose, chacun tue au moins une
    contre-epreuve. Reutilisable telle quelle par un test (`tests/engine/runner/
    test_trigger_ability_channels.py`) et par un futur consommateur d'`On(0xd)`."""
    a, b = r["a_id"], r["b_id"]
    assert site(r, "A.exec") == (a, None), (
        f"+0x98 est deja ecrit PENDANT le behaviour de A : {site(r, 'A.exec')} != ({a}, None). "
        "Le natif ne l'ecrit qu'APRES le retour du behaviour "
        "(IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute, etape 4 sur 6).")
    assert site(r, "B.matches") == (None, a), (
        f"le gate TriggeringAbilityIs(A) ne lit pas +0x98 : {site(r, 'B.matches')} != (None, {a}). "
        "Canal attendu = state.trigger_ability_type ; state.triggering_ability est +0x60.")
    assert site(r, "B.exec") == (b, a), (
        f"les deux canaux ne sont PAS separes dans le behaviour chaine : {site(r, 'B.exec')} "
        f"!= ({b}, {a}). C'est LE seul point ou ils portent deux valeurs non nulles differentes.")
    assert site(r, "C.matches") == (b, a), (
        f"l'heritage differe du natif sous la chaine : {site(r, 'C.matches')} != ({b}, {a}). "
        "+0x60 est herite par tout ce que le behaviour engendre, +0x98 ne l'est pas.")
    assert r["final"] == (None, None), (
        f"un canal FUIT hors de son evaluation : final={r['final']} != (None, None). "
        "Chaque IdunBattle.Operations.EvaluateTriggerOperation batit son propre AbilityEntities.")
    assert r["separated"] is True


def main() -> None:
    ap = argparse.ArgumentParser(description="#294 -- separation des canaux +0x60 / +0x98")
    ap.add_argument("--mutate", choices=MUTATIONS, default=None)
    a = ap.parse_args()
    r = run(mutate=a.mutate, verbose=True)
    try:
        assert_channels_separated(r)
        print("  garde: VERT")
    except AssertionError as exc:
        print(f"  garde: ROUGE -- {exc}")


if __name__ == "__main__":
    main()
