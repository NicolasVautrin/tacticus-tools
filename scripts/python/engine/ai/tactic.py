"""DefaultAiUnitTactic — orchestration de la décision par-unité (namespace `IdunBattle.AI`).

`DefaultAiUnitTactic..IdunBattle.AI.Tactics.DefaultAiUnitTactic$$.ctor` construit une LISTE ORDONNÉE de générateurs (@tactic+0x60) ;
`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext` itère la liste et renvoie la PREMIÈRE action
NON-NULLE (`if (action != 0) break`). Pas d'argmax inter-générateurs — premier-non-null par tier,
`MovementActionGenerator` EN DERNIER (fallback).

Ordre natif (RE confirmé, cf. action_generators.py) : le flag `slot1` sépare NonComparable (slot1=FALSE)
-> `dict[get_Priority]` de Comparable (slot1=TRUE, attaque normale incluse) -> OrderedSet `special`.
`IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` construit :
  `[ NC(1000), NC(100), NC(0), NC(-100), NC(-1000), Comparable(special), Movement ]`.
Notre port MIRRORE cet ordre exact. **22 des 257 ActiveAbilityType ont un tier `get_Priority` ≠ 0**
(interface slot-0, dispatch `FUN_180002560(0,...)` IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists) — table
`engine.playbook.noncomparable.NATIVE_PRIORITY`, mesurée par sweep exhaustif (#170). Trois sont
portées : NovaBoost 1192 = 1000, ThriceBlessedConflagration 1187 = 100, NovaShield 1194 = -1000 ;
les autres playbooks portés héritent du défaut 0. Les 5 tiers sont donc RÉELLEMENT exercés dès
qu'une unité porte l'une des 22 ; à l'intérieur d'un tier, deux NonComparable d'une même unité se
départagent par UTILITÉ (argmax `choose_action`).

⚠ L'affirmation antérieure « AUCUN playbook n'override `get_Priority` » (#115) était un FAUX NÉGATIF
de méthode : les corps `mov eax,imm32 ; ret` sont dédupliqués par IL2CPP, donc invisibles à une
recherche de symboles Ghidra et réduits à un seul propriétaire dans `methods.tsv` (indexé par RVA).
Cf. la note complète en tête de `engine/playbook/noncomparable/_base.py`."""
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


class DefaultMachineTactic:
    """Le tactic des MACHINES OF WAR — `IdunBattle.AI.Tactics.DefaultMachineTactic`.

    C'est le CHEMIN NATIF DÉDIÉ au caster `EntityType.Machine` : `IdunBattle.Core.Services.AiQuery$$GetUnitTacticForUnit`
    route sur lui dès `IdunBattle.Entities.EntityExtensions$$IsMachine(actor)` (avant les branches
    Boss / NonAttacking / défaut). Une MoW y arrive parce que
    `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$CalculateNextActionForPlayer` AJOUTE
    l'entité `PlayerComponent+0x78` (= l'id de machine, écrit par
    `IdunBattle.Operations.AddMachineOperation$$Execute`) à la liste des entités du joueur.
    REACHABILITY MESURÉE (session 4, runner MoW `adeptExorcist`) : `aiStepDryRun` rend
    `ActiveAbilityMessage{casterId=<machineId>, abilityType=1188}`, `mutated:false`.

    TROIS différences STRUCTURELLES avec `DefaultAiUnitTactic`, toutes lues au décompilé :

    1. **Pas de `MovementActionGenerator`.** `DefaultMachineTactic$$.ctor` pose
       `@tactic+0x60 = GetDefaultActiveAbilityActionGenerators(this)` DIRECTEMENT ; le ctor unité, lui,
       construit en plus un `MovementActionGenerator` (@+0x58) et l'`Add`-e en queue. Corollaire lu :
       `DefaultMachineTactic.<CalculateMovementForUnit>d__8$$MoveNext` renvoie une liste VIDE,
       toujours — **une MoW ne bouge JAMAIS** (elle est hors-plateau).
    2. **Position du caster = `IdunBattle.Core.UnitPosition$$NullPosition`** et **tuiles candidates =
       `OrderedSet` VIDE** : `<CalculateNextActionForUnit>d__5$$MoveNext` appelle
       `gen.GenerateActions(machine, NullPosition(), new OrderedSet())` là où le tactic unité passe
       `GetUnitPosition(unit)` et `ABaseAiUnitTactic$$GenerateActionTiles(unit)`. Il ne fait NI le gate
       `UnitExtensions.IsAlive`, NI `GetMainTile`. Côté générateur, un ensemble de positions VIDE fait
       tomber `ActiveAbilityActionGenerator.<GenerateActions>d__7` dans sa branche `Count == 0` : UNE
       seule évaluation, avec `NullPosition()`, et SANS le gate `HasValidTargets` (slot 0x3f) que la
       branche par-tuile applique.
    3. **Émission dédiée** : `DefaultMachineTactic$$GenerateInputMessagesFromUnitAction` (et non
       `InputBuilder$$GenerateInputMessagesFromUnitAction`) — elle n'émet JAMAIS de `MoveUnitMessage` :
       soit un `ActiveAbilityMessage{casterId=machine, targetId, abilityType}`, soit, si l'action est
       nulle, le message de FIN d'activation de la machine.

    Le port ne fabrique donc AUCUNE origine pour la MoW : `ctx.origin is None`, `ctx.move_tiles == []`,
    `ctx.reach_nc == []` — c'est le mirror de `NullPosition` + tuiles vides, pas une dégradation."""

    def __init__(self):
        # `DefaultMachineTactic$$.ctor` : @tactic+0x60 = `GetDefaultActiveAbilityActionGenerators`
        # SEUL — la MÊME liste [NC(1000), NC(100), NC(0), NC(-100), NC(-1000), Comparable(special)]
        # que le tactic unité, **sans** le `MovementActionGenerator` terminal.
        self.generators = [NonComparableGenerator(p) for p in NC_PRIORITY_TIERS] + [
            ComparableAbilityGenerator(),
        ]

    def calculate_next_action(self, ctx) -> dict:
        """`DefaultMachineTactic.<CalculateNextActionForUnit>d__5$$MoveNext` — PREMIÈRE action
        non-nulle des générateurs ordonnés ; aucune ne sort -> `GenerateInputMessagesFromUnitAction`
        est appelée avec une action NULLE et n'émet que le message de fin d'activation, d'où
        `{kind: "finish"}` (JAMAIS `{kind:"move"}` : ce tactic n'a pas de générateur de mouvement)."""
        for gen in self.generators:
            action = gen.generate(ctx)
            if action is not None:
                return action
        return {"kind": "finish", "to": None}
