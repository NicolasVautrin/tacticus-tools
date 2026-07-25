"""DefaultAiUnitTactic — orchestration de la décision par-unité (namespace `IdunBattle.AI`).

`DefaultAiUnitTactic..IdunBattle.AI.Tactics.DefaultAiUnitTactic$$.ctor` construit une LISTE ORDONNÉE de générateurs (@tactic+0x60) ;
`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext` itère la liste et renvoie la PREMIÈRE action
NON-NULLE (`if (action != 0) break`). Pas d'argmax inter-générateurs — premier-non-null par tier,
`MovementActionGenerator` EN DERNIER (fallback).

Ordre natif (RE confirmé, cf. action_generators.py) : le flag `slot1` sépare NonComparable (slot1=FALSE)
-> `dict[get_Priority]` de Comparable (slot1=TRUE, attaque normale incluse) -> OrderedSet `special`.
`IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` construit :
  `[ NC(1000), NC(100), NC(0), NC(-100), NC(-1000), Comparable(special), Movement ]`.
Notre port MIRRORE cet ordre exact. #115 (RE gqfc5mff6c) : AUCUN playbook n'override `get_Priority`
(interface slot-0, dispatch `FUN_180002560(0,...)` IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists) -> les 15 NonComparable portées
partagent TOUTES le tier de base = 0 -> seul `NC(0)` tire côté NC. Les 5 tiers restent présents
structurellement (mirror du natif), mais l'ordre inter-tier NC n'est jamais exercé (un seul tier peuplé) ;
à l'intérieur de `NC(0)`, deux NonComparable d'une même unité se départagent par UTILITÉ (argmax
`choose_action`), PAS par un tier fabriqué (l'ancien NovaBoost=1000/NovaShield=-1000 = idun.tests.TestLegendaryEventProgression$$GetLiveEventState+0x40 stale)."""
from __future__ import annotations

from engine.ai.action_generators import (
    NonComparableGenerator, ComparableAbilityGenerator, MovementActionGenerator,
)

# Tiers de priorité NonComparable (`get_Priority`), dans l'ordre d'évaluation natif.
NC_PRIORITY_TIERS = (1000, 100, 0, -100, -1000)


class DefaultAiUnitTactic:
    """Le tactic par-unité : liste ordonnée de générateurs, PREMIÈRE action non-nulle."""

    def __init__(self):
        # Liste ORDONNÉE (@tactic+0x60) : 5 générateurs NonComparable par tier de priorité, PUIS le
        # fallback Comparable (`special` : attaques normale/spéciales + soins), PUIS movement (terminal).
        self.generators = [NonComparableGenerator(p) for p in NC_PRIORITY_TIERS] + [
            ComparableAbilityGenerator(),
            MovementActionGenerator(),
        ]

    def calculate_next_action(self, ctx) -> dict:
        """`CalculateNextActionForUnit.MoveNext` — renvoie la PREMIÈRE action non-nulle des générateurs
        ordonnés. Forme normalisée : `{kind:"move", to}` ou `{kind:"ability", target, ability, to, util}`."""
        for gen in self.generators:
            action = gen.generate(ctx)
            if action is not None:
                return action
        # MovementActionGenerator renvoie TOUJOURS une action -> ce filet n'est atteint que si la liste
        # de générateurs était vide (jamais en pratique).
        return {"kind": "move", "to": None}
