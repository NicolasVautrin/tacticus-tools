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


def input_messages_from_unit_action(ctx, action: dict | None, options_first: int = 0) -> dict | None:
    """`IdunBattle.AI.ActionGenerators.InputBuilder$$GenerateInputMessagesFromUnitAction(action,
    unit, currentPosition, options)` — mirror 1:1, réduit à la FORME d'action du port.

    Corps natif (relu sur `rnca9r7q6c`) :

        msgs = new List<IInputMessage>()
        if (action != null) {
            if (UnitPosition.op_Inequality(action.Position, null)
                && !currentPosition.Equals(action.Position))
                msgs.Add(MoveUnitMessage{ unitId, positions })
            if (action.Target != null)
                msgs.Add(ActiveAbilityMessage{ unitId, targetId, abilityType })
        }
        if (options[0] != 0) return msgs
        if (msgs.Count != 0) return msgs
        msgs.Add(FinishUnitTurnMessage{ unitId })
        return msgs

    ⚠ **Ce n'est PAS un gate de générateur, et l'analogie avec l'axe ABILITY est FAUSSE.**
    `IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext`
    ne teste AUCUN flag d'unité — contrairement à
    `...ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`, dont la première
    instruction est `if (HasFlag(unit, 2)) return 0`. Ses seules sorties à zéro action sont
    `UnitPosition.op_Equality(startPosition, null)`, `UnitPosition.IsEmpty(startPosition)` et
    « le chooser d'utilité ne rend aucun `UtilityMovementCase` ». Or `positions` lui vient de
    `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` = `GetMovableTilesFor(unit,
    ignoreFlags: false, null)` étendu par les playbooks, et le natif y adjoint la position
    COURANTE : pour une unité vivante l'ensemble n'est jamais vide, donc le générateur natif rend
    TOUJOURS une action — exactement comme le port. **Le filtre est ici, un cran plus bas.**

    `options` vaut `{0, 0, 0}` sur ce chemin (`DefaultAiUnitTactic.<CalculateNextActionForUnit>d__5`
    passe un `&local_58` remis à zéro), donc le court-circuit `options[0] != 0` n'est jamais pris et
    le repli `FinishUnitTurnMessage` s'applique bien. `options_first` (défaut 0) EXPRIME ce littéral :
    l'AUTRE appelant, `DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`,
    construit `{1, d__6+0x31, d__6+0x32}` — premier octet = **1 littéral** -> le court-circuit EST pris,
    et une action qui n'émet aucun message ne devient PAS un `FinishUnitTurnMessage` (le behaviour
    `PerformAIAbilityUnitBehaviour` ne termine jamais le tour de son acteur). Rend alors `None`.

    Deux conséquences que le port doit refléter, et qu'il ignorait :

    1. `action == null` (aucun générateur n'a produit) -> action NULLE. Le natif passe quand même
       par `IdunBattle.AI.Tactics.ABaseAiActorTactic$$LogInvalidUnitAction(this, unit, action)`,
       puis `InputBuilder` rend le `FinishUnitTurnMessage` : le cas est PRÉVU, pas accidentel.
    2. `action != null` mais qui ne bouge pas (destination == tuile courante, ou absente) et ne
       cible rien -> action NULLE **aussi**. C'est le cas majoritaire, et celui qu'un gate posé à
       l'entrée du générateur aurait manqué.

    ROUTE À CIBLES TUILE (#302) : une action d'ability porte toujours `action.Target != null` —
    `IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)` prend un
    `IEntity` NON TYPÉ, et une entité-tuile circule dans ce même slot. Le repli ne peut donc pas la
    couvrir par accident. Ce n'est pas supposé : `probe_309_movement_null_action.py --noreg`
    INSTRUMENTE ce mirror et ventile PAR KIND ce qu'il intercepte — une seule interception de kind
    `ability` serait une régression, et la garde l'asserte à zéro.

    RÉSIDU NOMMÉ : le natif compare deux `UnitPosition` (ENSEMBLES de tuiles, `Equals` sur la
    collection) ; le port compare la MAIN tile. Pour une unité multi-tuiles dont seule une tuile
    secondaire changerait, le natif émettrait un `MoveUnitMessage` que ce mirror tairait. Les héros
    du pool sont mono-tuile — non exercé, donc non mesuré.

    Rend l'action telle quelle si elle produit au moins un message, sinon `{kind:"finish"}`."""
    if action is not None:
        to = action.get("to")
        origin = getattr(ctx, "origin", None)
        # `UnitPosition.op_Inequality(action.Position, null) && !currentPosition.Equals(...)` :
        # une destination ABSENTE, ou ÉGALE à la tuile courante, n'émet aucun `MoveUnitMessage`.
        # `origin is None` = position courante non mesurée -> on NE COUPE PAS (on ne supprime pas
        # un déplacement sur une non-mesure ; c'est la dégradation dangereuse).
        moves = to is not None and (origin is None or tuple(to) != tuple(origin))
        # `action.Target != null`. Le port ne pose `target` que sur une action d'ability.
        casts = action.get("target") is not None
        if moves or casts:
            return action
    if options_first:
        return None            # `if (options[0] != 0) return msgs` -> msgs VIDE : aucun message émis
    return {"kind": "finish", "to": None}


def calculate_ability_action_for_unit(ctx, ability_id: int, allow_only_move: bool = False,
                                      custom_utility=None) -> dict | None:
    """`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`
    — l'AUTRE entrée du tactic, celle qui joue UNE ability IMPOSÉE (et non « la meilleure action »).

    Corps natif (relu sur `rnca9r7q6c`), état 0 :

        if (state == null || !UnitExtensions.IsAlive(state, unit)) yield break;   // -> liste VIDE
        this.mainTile     = EntityExtensions.GetMainTile(state, unit);
        this.unitPosition = EntityExtensions.GetUnitPosition(state, unit);
        this.actionTiles  = ABaseAiUnitTactic$$GenerateActionTiles(tactic, state, true, this.maxDistance);
        var generators = new List<IActionGenerator>();
        var abilityIds = new OrderedSet<int>();  abilityIds.Add(this.abilityId);
        generators.Add(new ActiveAbilityActionGenerator(abilityIds, tactic+0x10, tactic.playbookDatabase,
                                                       tactic.random, tactic+0x30));
        if (this.allowOnlyMove) generators.Add(tactic.movementActionGenerator /*tactic+0x58*/);
        foreach (gen in generators)
            foreach (action in gen.GenerateActions(state, this.unitPosition, this.actionTiles,
                                                   this.customUtility /*d__6+0x40*/)) {
                ABaseAiActorTactic$$LogInvalidUnitAction(tactic, state, action);
                yield return InputBuilder$$GenerateInputMessagesFromUnitAction(
                    action, state, new UnitPosition(this.mainTile), { 1, this+0x31, this+0x32 });
            }

    TROIS différences STRUCTURELLES avec `calculate_next_action` (`d__5`), toutes lues :

    1. **UN SEUL générateur d'ability**, dont le set `abilityIds` ne contient QUE l'ability imposée —
       là où `d__5` en instancie SIX (5 tiers NonComparable + le tier Comparable `special`, cf.
       `GetDefaultActiveAbilityActionGenerators`). Il n'y a donc NI tier NI « première action non-nulle
       par tier » : le `Bucket` de l'unique générateur tranche seul.
    2. **`MovementActionGenerator` conditionnel** : ajouté SSI `allowOnlyMove` (`behaviour+0x70`),
       et en QUEUE ; `d__5` l'a toujours.
    3. **`options[0] = 1`** passé à `InputBuilder` -> pas de repli `FinishUnitTurnMessage` (cf.
       `input_messages_from_unit_action`). Aucun message == l'acteur ne fait RIEN.

    Appelant unique : `IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor(unit, abilityType,
    options)`, qui draine l'énumérateur et applique les messages (`AiControl$$ApplyAiMessages`).

    PÉRIMÈTRE PORTÉ : le générateur d'ability est ici `ComparableAbilityGenerator(ability_ids={id})`.
    C'est exact pour toute ability COMPARABLE — et les deux seuls nœuds `DSLBehaviors` qui atteignent
    ce chemin (`PerformAIAttack`, `PerformAIAttackFromCurrentPosition`) passent le `Func<IEntity,int>`
    dont le corps est `IdunBattle.Entities.UnitExtensions$$GetNormalAttackType(unit)`, c.-à-d.
    l'ATTAQUE NORMALE, qui est Comparable. La branche NonComparable de ce mirror (un `abilityId` dont
    le playbook serait NC) n'a AUCUN call-site : non portée, non spéculée.

    RÉSIDU NON PORTÉ : `customUtility` (`d__6+0x40`, issu de `behaviour+0x90`) n'est pas threadé jusqu'à
    `calculate_action_utility` — le paramètre est accepté et IGNORÉ, pour que le résidu soit LOCALISÉ ici
    (seul TheQuickening en pose un, cf. `abilities/loki/quickening.py`).

    Rend l'action (`{kind:"ability"|"move", target, ability, to, util}`) ou `None`."""
    from engine.ai.action_generators import ComparableAbilityGenerator, MovementActionGenerator

    generators = [ComparableAbilityGenerator(ability_ids=(int(ability_id),))]
    if allow_only_move:
        generators.append(MovementActionGenerator())
    for gen in generators:
        action = gen.generate(ctx)
        if action is None:
            continue
        msgs = input_messages_from_unit_action(ctx, action, options_first=1)
        if msgs is not None:
            return msgs
    return None


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
        """`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`
        — PREMIÈRE action non-nulle des générateurs ordonnés, PUIS traduction en messages.

        Le natif ne rend pas l'action : il sort de sa double boucle (`if (action != 0) break`) avec
        une action éventuellement NULLE, et appelle `InputBuilder$$GenerateInputMessagesFromUnitAction
        (action, unit, new UnitPosition(mainTile), &options)`. C'est CETTE traduction qui décide s'il
        y a un `MoveUnitMessage`, un `ActiveAbilityMessage`, ou — liste vide — un
        `FinishUnitTurnMessage`. Le port la mirrore désormais (#309) au lieu de rendre l'action brute :
        sans elle il proposait TOUJOURS quelque chose, y compris là où le natif finit le tour.

        Forme normalisée : `{kind:"move", to}`, `{kind:"ability", target, ability, to, util}`, ou
        `{kind:"finish", to:None}` (l'action NULLE)."""
        action = None
        for gen in self.generators:
            action = gen.generate(ctx)
            if action is not None:
                break
        # Résolution par le module (et non par une closure) : c'est ce qui rend le mirror
        # NEUTRALISABLE depuis un probe, donc la garde falsifiable.
        return input_messages_from_unit_action(ctx, action)


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
