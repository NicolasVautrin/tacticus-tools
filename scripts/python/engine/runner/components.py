"""Composants ECS concrets — port FIDÈLE (noms 1:1 du natif, VA citée).

`IdunBattle.Entities.Components.*Component`. Tranche 0 : seuls les composants de
l'ÉTAT D'UNITÉ diffé (position/HP/owner/identité/effets) sont posés, avec les champs
qu'on peut peupler depuis la vérité live (decisionView/observeBattle, qui lisent
ces composants natifs). Les OFFSETS exacts (layout) seront RE'd quand une operation
les ÉCRIRA (tranche move/damage/effects) ; ici on porte la sémantique des champs.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Dict, Hashable, Iterator, List, Optional

from .state import Component
from ..entities.effect_type import EffectType   # #270-r1-r1 : `_TELEPORT_MOVE_EFFECTS`
from ..entities.unit_flag import UnitFlag   # #270-r1-r1-r3
from ..battle_query import get_in_range_aura_amount
from ..battle_query import is_adjacent
from ..entities.effect_targets import is_effect_target as _iet
from ..entities.effects.loki.amulet_of_the_voidwyrm import (
        adjacent_friendly_summons_and_decoys_selector)
from ..entities.effects.loki.deathwing import adjacent_dark_angels_friends_selector
from ..entities.effects.loki.hunter_of_souls import adjacent_psyker_friends_selector   # #1078-r3
from ..entities.effects.loki.intoxicating_elixir import debuffed_units_in_range_selector
from ..entities.effects.loki.kardiocore_galvanus import adjacent_mechanical_friends_selector
from ..entities.effects.loki.maw_claws_of_thyrax import adjacent_summons_selector
from ..entities.effects.loki.nether_realm_casket import adjacent_mechanical_units_selector
from ..entities.effects.loki.supa_cybork_body import adjacent_enemies_selector
from ..entities.effects.loki.obsessive_annunciation import (   # #954
    adjacent_enemies_selector as obsessive_annunciation_target_selector)
# #1025-r1 : MEME forme et MEME raison que la ligne ci-dessus -- l'ARBRE vit dans la classe d'effet
# (doctrine #149), ce module ne fait que lui donner son `AbilityEntities`. HISSE (pas differe) :
# mesure du 2026-08-14 -- charger `extra_damage_aura` SEUL ne fait PAS entrer `runner.components`
# dans `sys.modules`, donc le differe aurait ete GRATUIT.
from ..entities.effects.loki.extra_damage_aura import (
    more_gitz_adjacent_units_selector as more_gitz_adjacent_units_target_selector)
from ..entities.pathfinding.board import adjacent_neigh_by_pos, elevations_by_pos
from ..entities.stats import StatType
from ..entities.stats import StatPart   # #572-r1 : `FillUpStatComponent$$GetStatPart`
from ..entities.stats import ValueModification, ValueOverride   # #572-r1 : le max de `HealthComponent`
from ..entities.traits.unit_trait import UnitTrait as _UT, has_trait as _has_trait
from ..entities.traits.unit_trait import UnitTrait, has_trait
from ..entities.traits.unit_trait import entity_trait_names, has_any_trait   # #498-r2
from ..entities.stats import StatType as _ST
from ..entities.effects.loki.daemonic_patrons import adjacent_taunted_enemies_selector
# FORME B OBLIGATOIRE (#962) : `migrate_485r1_barils_reexport.py morsure` classe
# `adjacent_dark_angels_friends_selector` en `HISSAGE_DESARMERAIT` -- il est SUBSTITUE par
# `test_947_948_extra_damage_passives_offline.py:567` (`monkeypatch.setattr` sur le module SOURCE).
# Une liaison `from ... import <nom>` la gelerait au chargement et rendrait ce patch INERTE.
from ..entities.effects.loki import enmity_for_the_unworthy as _enmity
# #590-r6-r2 : la table des types de block-movement, lue par `unit_extensions_can_move`. Import de
# TETE, en FORME B (on lie le MODULE) : le differe qu'il portait dans `turnflow` etait GRATUIT ici,
# MESURE -- charger `instinctive_behaviour` SEUL dans un process frais ne tire pas ce module-ci.
from ..entities.effects.loki import instinctive_behaviour as _instinctive
from ..entities.effects import aura_selectors as _ASel              # FORME B (liaison de MODULE).
from ..entities.effects.loki import synaptic_insight as _si         # Aretes GRATUITES (#485) :
from ..entities.effects.loki import close_combat_weakness as _ccw   # charges SEULS, ces trois
#     modules ne tirent pas `engine.runner.components` -- rien a rompre, les differes qui vivaient
#     dans `faction`, `synaptic_insight_adjacent_tyranid` et
#     `close_combat_weakness_adjacent_enemies_count` etaient des scories.

if TYPE_CHECKING:
    from ..entities.unit_context import UnitContext


class UnitComponent(Component):
    """Identité d'unité — `UnitComponent` IdunBattle.Entities.Components.UnitComponent$$.ctor / `BaseUnitComponent` IdunBattle.Entities.Components.BaseUnitComponent$$.ctor.
    `visual_id` = id visuel (ex. 'necroNpc1Warrior'), `alive` = vivante.

    `ai_controlled` = l'unité est jouée par l'IA au turn-start de sa team, MÊME sur une team
    par ailleurs contrôlée par le joueur (cas des SUMMONS). Mirroir du flag per-unité runtime lu par
    `IdunBattle.View.Game.IdunGameViews$$IsPlayerAiControlled (SortedDictionary +0x18==1 → AI-contrôlé ; posé
    quand l'unité est invoquée). N'est PAS un trait gameconfig — c'est un état runtime posé au spawn
    (cf. `SpawnUnitOperation`). Une unité d'une team entièrement-IA est de toute façon jouée par l'IA
    (type player 2) ; ce flag cible le cas summon-sur-team-joueur.

    `turn_defeated` = valeur de `state.turn_counts[owner_player]` AU MOMENT de la mort (G3 Ambush) —
    mirror du `TurnDefeated` que `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$GetUnitsEligibleForResurrect` lit dans
    `AmountIsEqual(Difference(CurrentPlayerTurnsStarted, TurnDefeated(u)), @0xc0=1)`. None tant que
    l'unité n'est pas morte. Posé par `Ambush_SummonAbility` (trigger On(UnitDefeated)).
    ⚠ Le champ natif est `UnitComponent + 0x17c`, un ENTIER — lu par
    `IdunBattle.Entities.Formulas.TurnDefeatedFormula$$Calculate` (sous un gate
    `IdunBattle.Entities.UnitExtensions$$IsDefeated`) et recopié par
    `IdunBattle.Entities.Components.UnitComponent$$Copy`.

    ⚠ **SON ÉCRIVAIN EST `IdunBattle.Operations.RemoveUnitOperation$$Execute`, et il l'a TOUJOURS
    été — la phrase « écrivain non identifié » qui vivait ici était FAUSSE** (elle fondait le blocage
    `etage` de `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1`, désormais LEVÉ). Le décompilé de cette
    Operation écrit, juste après `UnitFlagsComponent$$Add(unit, 0x1a = Removed)` :

        uc->[0x17c] = TurnComponent$$GetAmountOfTurnsStartedByPlayer(GetMatchTurn(state), ownerPlayerId);
        uc->[0x180] = 1;

    — c'est-à-dire **le compteur de tours démarrés par le joueur PROPRIÉTAIRE, au moment où l'unité
    QUITTE le plateau**. C'est exactement ce que `runner/operations/remove_unit.py` documente déjà
    en étape 10 : la donnée était lue, seule la phrase de ce fichier ne l'était pas.

    ⚠ **CE QUI A FAIT ÉCHOUER LES RECHERCHES PRÉCÉDENTES**, et la parade : elles cherchaient dans
    l'index de code de ghidra-mcp (partiel, puis SUPPRIMÉ — `code_indexed: False` sur `t6dpr4k06g`),
    et une absence d'index se lisait comme une absence d'écrivain. Le balayage qui tranche ne
    cherche pas un TEXTE de pseudo-C mais l'ENCODAGE x86-64 : un `disp32` littéral `7c 01 00 00`
    précédé d'un ModRM `mod=10` (avec ou sans SIB, base `rsp`/`r12` écartée = variable locale), dans
    **les deux sections de code** (`.text` ET `il2cpp` — `.text` seul rend 0 sur un binaire IL2CPP).
    Résultat sur `t6dpr4k06g` : **220 accès, dont 66 écritures**, et parmi elles **3 seulement**
    touchent un `UnitComponent` — `$$.ctor+0x133` (init), `$$Copy+0x582` (recopie) et
    `RemoveUnitOperation$$Execute+0x4f6` (le seul écrivain sémantique). Aucun hit n'est tu : les
    opcodes non classés sont imprimés avec leur propriétaire (ce sont des flottants SSE de `View`).

    ⚠ **VALEUR INITIALE = `-1`, une SENTINELLE** : `UnitComponent$$.ctor+0x133` est
    `c7 87 7c 01 00 00 ff ff ff ff` = `mov dword ptr [rdi+0x17c], 0xffffffff`. Une unité jamais
    RETIRÉE ne peut donc satisfaire aucun `Difference(CurrentPlayerTurnsStarted, TurnDefeated) == 1`.

    ⚠ **CE PARAGRAPHE AFFIRMAIT L'INVERSE, ET IL EST RÉFUTÉ (#10015-r2, 2026-08-18).** Il écrivait
    que `IdunBattle.Operations.KillUnitOperation$$Execute` n'appelle **jamais**
    `IOperationProcessor` slot 6 = `RemoveUnit`, donc qu'une unité TUÉE ne passe pas par l'écrivain,
    donc que la pose côté port était une COMPENSATION. **Elle l'appelle** — à `+0xd34`,
    `(killed, removeEffects: 0, keepActive: 1)`, dans la branche non-revive.

    ⚠ **LA CAUSE DE L'ANGLE MORT SE RÉUTILISE** : un appel d'interface IL2CPP a **DEUX formes** dans
    le pseudo-C. La forme DISPATCHER porte le slot en **1ᵉʳ** argument — c'est elle que le
    recensement fautif balayait (il avait relu les slots 77, 80, 85, 99, 130, 143 « un par un »). La
    forme **WALK D'ITABLE INLINE** porte le slot en **3ᵉ** argument d'un helper, et son call-site
    final est anonyme : elle est invisible à un grep par slot. `FleeOperation` emploie les deux, donc
    le binaire fournit lui-même le contre-exemple. Un recensement qui ne visite qu'une forme ne peut
    pas rendre zéro sur l'autre.

    ⚠ Le dépôt portait DÉJÀ les deux affirmations contradictoires : `operations/damage.py` écrivait
    `+0xd34 processor.<slot 6>` (build précédent, même offset) pendant que ce paragraphe-ci écrivait
    « jamais ». La pose de `turn_defeated` n'est donc plus un ÉCART NOMMÉ — elle est sur le chemin
    natif. **Conséquence qui dépasse `turn_defeated`** : `On(0x25 = UnitRemoved)` est publié à CHAQUE
    mort, et il ne l'était sur aucune mort du port.

    `killed_this_turn` = mirror EXACT du BOOLÉEN `UnitComponent + 0x17a`, et il n'a rien à voir avec
    son voisin `turn_defeated` ci-dessus :
      * LECTEUR UNIQUE — `IdunBattle.Entities.Triggers.KilledThisTurnTrigger$$ShouldTrigger`, dont le
        corps entier est `unit = SelectSingle(entities); if (unit == null) return false;
        uc = GetComponent<UnitComponent>(unit); return uc != null && *(byte*)(uc + 0x17a)`. C'est ce
        trigger qu'alloue le nœud DSL `IdunBattleLogic.Entities.DSLTriggers$$IsKilledThisTurn`, dont
        l'unique call-site natif est
        `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ADecoysAndMisdirectionAbility$$GetValidDeadDecoys`.
      * ÉCRIVAIN — `IdunBattle.Operations.KillUnitOperation$$Execute+0x828` : `+0x17a = 1`, DANS la
        branche non-revive (juste après la garde `if (!unitComponent.PendingRevive@+0xa8.HasValue)`
        @+0x81c, et AVANT le `RegisterDefeatedUnit` @+0x8be).
      * RESET — `IdunBattle.Operations.StartTurnOperation$$ResetUnit`, dont la 2e instruction est
        `*(undefined2 *)(uc + 0x179) = 0` : un `short` qui efface `+0x179` ET `+0x17a` d'un coup. Ce
        `ResetUnit` est appelé sur `PlayerComponent.CurrentlyOwnedUnitIds` du joueur ENTRANT, dont
        `PlayerComponent$$get_CurrentlyOwnedUnitIds` retire les défaits ⇒ **le drapeau d'une unité
        MORTE n'est JAMAIS effacé tant qu'elle reste morte**. Sa sémantique exacte est donc « tuée,
        et n'a pas redémarré de tour depuis », pas « tuée pendant le tour courant ».
      * TRI-ÉTAT : `None` = NON MESURÉ. Aucun canal live ne publie `+0x17a` (`combatSnapshot` ne
        porte que `unitFlags`, un `OrderedSet<UnitFlag>` distinct), donc un cadavre-AU-CHARGEMENT
        arrive à `None` — et non à `False`, qui se lirait comme une mesure.

    `turns_finished` = mirror EXACT du champ `UnitComponent + 0x5c` — le compteur PER-UNITÉ des
    tours que CETTE unité a TERMINÉS. À ne pas confondre avec ses deux voisins :
      * `UnitComponent + 0x58` = `turnsStarted`, incrémenté par
        `IdunBattle.Operations.StartTurnOperation$$Execute`, EXPOSÉ comme `StatType` 12 (`GetStat(unit,
        0xc)` -> `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`) — porté dans le
        `StatsComponent`, PAS ici ;
      * `TurnComponent + 0x38` = le dictionnaire PAR JOUEUR (`GetAmountOfTurnsStartedByPlayer`) —
        porté par `State.turn_counts`, granularité JOUEUR.
    ÉCRITURE : `IdunBattle.Operations.EndTurnOperation$$Execute` fait `*(int *)(unitComp + 0x5c) += 1`
    pour chaque id de `PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui finit son tour (2 sites :
    les unités, puis la Machine of War du joueur — même offset, `GetTurnsFinished` a les DEUX branches
    d'`EntityType`, 1 = Unit et 6 = Machine). Les unités MORTES en sont exclues :
    `PlayerComponent$$get_CurrentlyOwnedUnitIds` termine par un `RemoveAll` du prédicat
    `PlayerComponent$$u003Cget_CurrentlyOwnedUnitIdsu003Eb__17_0` = « l'id est dans la liste
    @+0x40 (défaits) ».
    LECTURE : `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished` (rend `comp + 0x5c`).
    Consommateurs natifs : `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger`
    (le nœud `IdunBattleLogic.Entities.DSLTriggers$$OwnerHasFinishedMinTurns`, gate de PileIn),
    `IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$GetUseProbability` et
    `IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$GetUseProbability`.
    ⚠ `turns_finished` n'est PAS dérivable de `turnsStarted` : une unité APPARUE PENDANT le tour de
    son propriétaire (tout summon — grot de `GetEmRuntz`, réplique de `PileIn`) rate le bump de
    `StartTurn` mais prend celui d'`EndTurn`, et garde donc `turns_finished == turnsStarted + 1`
    pour le reste de la bataille.

    `times_attacked_this_turn` / `total_times_attacked` = les DEUX compteurs d'attaques REÇUES, que
    `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackReceived` incrémente
    D'UN SEUL GESTE (`+0x34 += 1 ; +0x38 += 1`, LU) et que seul le RESET distingue :
      * `@+0x38` — PER-TOUR, remis à 0 par
        `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetAttacksReceivedThisTurn`
        (`*(ulong*)(this+0x38) = 0`, donc +0x38 ET +0x3c d'un coup). C'est la source du prédicat DSL
        `IdunBattleLogic.Entities.DSLTriggers$$HasBeenAttackedAmountThisTurnIsEqualOrGreater` (G6
        HypersensoryAbilities) -> `times_attacked_this_turn` ici, remis à 0 au `start_turn`. Gate de
        l'ActiveCondition du HP-floor (`IsEnemyTurn & Not(attacked>=1)` = 1re attaque du tour ennemi)
        et du trigger MoveAndSpawnDecoy.
      * `@+0x34` — TOTAL DE LA BATAILLE, qu'AUCUN `Reset*` de ce composant ne touche (les deux
        `ResetThisTurn` et les trois `Reset*ThisTurn` ont été relus : aucun n'écrit +0x34). C'est ce
        que rend `IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate`
        (`return *(uint *)(comp + 0x34)`) -> `total_times_attacked` ici, JAMAIS remis à 0.
        Consommateur porté : le snowball de coups de `BloodyFury` (1129, `worldTerminator`),
        `IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$GetNumExtraHits` — l'i2 dit
        « each time Wrask was attacked **in this battle** », ce que la lecture d'offset confirme.
    ⚠ L'ancienne rédaction de ce bloc attribuait `@+0x34` à `times_attacked_this_turn` : c'était
    FAUX, et la faute était invisible tant qu'aucun nœud ne lisait le total. Les deux champs sont
    logés ici (comme `received_damage_this_turn`) alors que le foyer natif est
    l'`ActorStatisticsComponent` — même résidu structurel (case-202 §6).
    ⚠ RÉSIDU NOMMÉ : le foyer d'écriture porté (`operations/minimal_health.py::record_attacked`)
    est appelé depuis le pipeline post-résolution du dégât, là où le natif appelle
    `IdunBattle.Operations.RegisterAttackOperation$$Execute` (via l'interface
    `Core.Services.OperationProcessor$$RegisterAttack`, dont les xrefs entrantes sont toutes des
    slots DATA -> appelant non résolu au décompilé). Les deux compteurs partagent donc EXACTEMENT
    le même site : tout écart de placement les affecte ensemble, jamais l'un sans l'autre.

    `received_damage_this_turn` (#202) = Dictionary {profil de dégât (int DamageProfileType) → nb
    d'instances} des dégâts REÇUS pendant le tour COURANT — mirror du dict `receivedDamageThisTurn`
    de l'`ActorStatisticsComponent` natif @+0x80 (écrit par `IdunBattle.Operations.RegisterDamageOperation$$Execute`
    → `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage` : TryAdd(profil,1) sinon +1 ; reset par-unité du joueur
    ENTRANT par `IdunBattle.Operations.StartTurnOperation$$ResetUnit` → `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetReceivedDamageThisTurn`).
    Consommé par le sélecteur `UnitsThatTakenDamageThisTurn` (WeaverOfFate : ContainsKey(Psychic=13)).
    NB : logé ici (comme `times_attacked_this_turn`) alors que le foyer natif est un composant
    ActorStatistics dédié — résidu structurel documenté (case-202 §6).

    `last_hit_damage_taken_this_turn` / `last_hit_damage_taken_last_turn` = mirror des DEUX champs
    `ActorStatisticsComponent @+0x6c` et `@+0x70` (memes offsets, meme composant que le dict
    `received_damage_this_turn` @+0x80 ci-dessus).
      * ECRITURE, PAR COUP : `IdunBattle.Operations.ApplyDamageOperation$$Execute` ecrit
        `stats[0x68] = stats[0x6c] = (int)*param_1` sur la VICTIME, ou `(int)*param_1` = 1er champ du
        `DamageAppliedResult` = la SOMME des reductions REELLEMENT appliquees par CE coup
        (`FillUpStatComponent.Reduce` sante + 2e pool + `ApplyDamageOperation$$ReduceShield`).
        C'est donc le total du DERNIER COUP (PV + bouclier + armure-pool), PAS le total de l'attaque.
      * ROULEMENT, au turn-start du PROPRIETAIRE : `IdunBattle.Operations.StartTurnOperation$$ResetUnit`
        fait `stats[0x70] = stats[0x6c] ; stats[0x6c] = 0` JUSTE APRES
        `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetReceivedDamageThisTurn`.
        (`ActorStatisticsComponent$$ResetThisTurn` ne touche NI 0x6c NI 0x70.)
      * LECTURE : `IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula$$Calculate` rend
        `*(int *)(comp + 0x70)` -> noeud DSL `IdunBattleLogic.Entities.DSLFormulas$$LastHitDamageTakenLastTurn`.
        Consommateur porte : la regen `TimeFlux` de `thousTerminator` (« plus an additional amount
        equal to the Damage of the last hit he received in the last enemy turn »).

    `revive_used_this_turn` = gate ONCE-PER-TURN du passif revive-en-place (`ReviveEffect`, ex.
    TaintedNarthecium de deathRotbone / Narthecium de l'Apothicaire, case-66). Mirror de la
    DÉSACTIVATION de l'effet (`DeactivateEffect`, 2e volet du `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour`
    exécuté APRÈS un revive réussi) : une fois l'effet désactivé, son trigger ne fire plus jusqu'à
    RÉACTIVATION au début de tour. Posé à True par la feuille `ConsumeReviveGate` (revive.py), remis à
    False pour TOUTES les unités au turn-start (`reset_revive_gates`, comme `times_attacked_this_turn`).
    i2 « Can only be triggered once per turn ».

    `pending_revive` = mirror du champ `UnitComponent + 0xa8` = **`Nullable<ReviveData>`** (le champ
    IMMÉDIATEMENT après le `Nullable<AttackHit>` @+0x98, cf. `IdunBattle.Entities.Components.UnitComponent$$Copy` qui teste le
    `hasValue` du Nullable @+0x98 par le MÊME helper `thunk_FUN_1801f3000(ptr, fieldInfo)`). Trois
    fonctions natives le manipulent, et c'est LA pièce centrale du sous-système REVIVE :
      * ÉCRITURE  `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` — la feuille DSL `Revive` n'exécute AUCUNE mutation :
        elle POSE la `ReviveData` (amount/healType/sourceId/priority) sur `unitComponent + 0xa8..0xe8`,
        après le gate `IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive` ;
      * GARDE    `IdunBattle.Operations.KillUnitOperation$$Execute` @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e : `if (!pendingRevive.HasValue)` —
        tout le RESTE de la mort (`On(PreUnitDeath_2)`, `On(UnitDeath)`, `On(UnitDefeated)`, `On(PostUnitKill)`, Remove(flag 0xf)/Add(flag 6),
        `RemoveEffects`, `RegisterDefeatedUnit`) est SOUS cette garde. Un revive posé pendant `On(PreUnitDeath)`
        ANNULE donc la mort (cf. `damage.py::_fire_death_if_killed`) ;
      * LECTURE+PURGE `IdunBattle.Operations.ReviveUnitOperation$$Execute` : lit les 9 qwords @0xa8..0xe8, refuse
        (log d'erreur + return) si `!HasValue` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba, applique le revive, puis REMET LES 9 QWORDS
        À 0 @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+ (donc APRÈS l'émission de `On(UnitRevived=0x2d)`).
    Port : `None` = pas de revive en attente ; sinon un dict `{amount, heal_type, source, priority}`
    (cf. `operations/revive.py`).

    `current_turn_start_tile` = mirror du champ `UnitComponent + 0x18c` (un `int` d'id de TUILE).
    ECRIT par `IdunBattle.Operations.StartTurnOperation$$Execute`, dans la boucle sur
    `PlayerComponent.CurrentlyOwnedUnitIds` du joueur ENTRANT et juste apres le bump de
    `turnsStarted@+0x58` : `mainTile = EntityExtensions.GetMainTile(unit) ; comp[0x18c] =
    (mainTile != null) ? mainTile.Id : 0`. C'est donc la tuile ou l'unite se trouvait au DEBUT DE SON
    PROPRE TOUR -- PAS la tuile qu'elle vient de quitter. RELU par
    `IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select` (`IdunBattleLogic.Entities.
    IdunBattleLogic.Entities.DSLSelectors$$CurrentTurnStartTile`), qui rend une liste VIDE quand le champ vaut 0 -- ce que le
    port represente par `None`. Consommateur porte : `GhostReviveAbility`/`TimeFluxReviveAbility`
    (le time-ghost de `thousTerminator` est pose sur CETTE tuile, cf. `triggers/loki/ghost_revive.py`).

    `revived_by_abilities` = mirror du `HashSet<AbilityOrEffect>` @`ActorStatisticsComponent + 0xe0`.
    ECRIT par `IdunBattle.Operations.ReviveUnitOperation$$Execute` : si la `ReviveData` porte un
    `sourceId` (`Nullable<AbilityOrEffect>`), l'operation l'AJOUTE a ce set juste apres `SetHealth`
    et AVANT les flags. RELU par `Idun.Source.IdunBattle.Logic.Entities.Triggers.
    HasBeenRevivedAbilityTrigger$$ShouldTrigger` (`IdunBattleLogic.Entities.DSLFactory$$
    HasBeenRevivedByAbility(unit, source)`) = `set.Contains(source)`. AUCUN reset natif (ni
    turn-start, ni phase) -> c'est un registre de BATAILLE : le gate « une seule resurrection par
    ability » de `GhostEffect` et de `GhostReviveAbility`. Port : set d'ids `AbilityOrEffect`
    (l'`EffectType` 1186 pour le ghost).

    `parent_id` = mirror du lien enfant -> SUMMONER natif : `IdunBattle.Entities.Components.
    ChildComponent`, champ `ParentId` (`BEntityId` = int32 @+0x10 ; observable live `Unit_Parent_Id`
    emis au spawn d'un summon). C'est ce que lit `IdunBattle.Entities.UnitExtensions$$GetParent`
    (`TryGetComponent<ChildComponent>` puis `state.GetEntity(ParentId)` ; la recursion vers la
    RACINE n'a lieu que si son 3e argument `root` est vrai), foyer du selecteur
    `IdunBattle.Entities.Selectors.ParentSelector$$Select`, consomme par
    `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector` (`Parent(Self)`
    = le SUMMONER) et par le gate `IsFriendlyKell` du playbook SupremeCommander.
    ⚠ Ce n'est PAS `IdunBattle.Entities.Components.ParentComponent`, dont le `+0x10` est
    `ChildrenIds` (une `List`, sens parent -> enfants -- cf. son `$$.ctor` et son `$$ToString`) :
    c'est l'autre bout du lien, et l'ancrage que nommait le residu de #372.
    None = unite sans parent (toute unite du roster initial). Pose par `SpawnUnitOperation`
    (`_spawn_config_grot`, mirror `SpawnUnitOptions` -> `Unit_Parent_Id = casterId`) et, sur un etat
    HYDRATE, seede depuis `combatSnapshot.units[].parentId` par `snapshot._load_unit_parent` (#378).

    Le lien RECIPROQUE (parent -> enfants) n'est PAS materialise : le port le derive en balayant
    `state.entities` (cf. `children_of`), la ou le natif tient la liste `ParentComponent.ChildrenIds`
    (@+0x10, construite par `IdunBattle.Entities.Components.ParentComponent$$.ctor`).

    `death_source` = mirror du `Nullable<IdunBattle.Operations.DamageSource>` @`UnitComponent+0x108`,
    ECRIT par `IdunBattle.Operations.KillUnitOperation$$RecordDeathReason(killer, killed,
    killedUnitComponent, deathReason)` (call-site : `IdunBattle.Operations.KillUnitOperation$$Execute`,
    AVANT le `On(PreUnitDeath=1)` -- ordre LU au decompile) et RELU par
    `IdunBattle.Entities.Triggers.HasDeathReasonTrigger$$ShouldTrigger` (qui resout SON selecteur, prend
    le `UnitComponent` de chaque unite selectionnee, lit ce champ et delegue a
    `...$$IsMatchingDeathReason`). Structure de la `DamageSource` LUE au decompile :
    `+0x00 KillerId` · `+0x14 DamageReason` (0=Ability, 1=Knockback, 2=Steppable) ·
    `+0x18 Nullable<AbilityOrEffect>` (lu par `IdunBattle.Operations.DamageSource$$IsFromAbility`).
    Cote port : `(killer_id, damage_reason, ability_or_effect|None)`, None tant que l'unite est vivante.

    `damaged_units_this_phase` = mirror de la `List<BEntityId>` @`ActorStatisticsComponent + 0x48`
    (l'ATTAQUANT y accumule les unites auxquelles il a inflige des degats pendant la PHASE courante).
    C'est LA source du selecteur `IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select`
    (`IdunBattleLogic.Entities.DSLSelectors$$UnitsDamagedThisPhase(attacker)`), qui resout son selecteur
    `attacker`, prend ce composant sur chaque attaquant et rend les ENTITES correspondantes.
    Le champ 0x48 est REMIS A ZERO par `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase` --
    la MEME fonction, la MEME boucle d'entites, que le `TriggeredAbilityComponent$$ResetPhase` deja
    porte : le port mappe donc le boundary de phase au MEME endroit (`State.reset_trigger_phases`,
    appelee par `Runner.apply` sur chaque action top-level). Consommateur : le volet OVERKILL de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour`.
    NB : loge ici (comme `times_attacked_this_turn`/`received_damage_this_turn`) alors que le foyer
    natif est l'`ActorStatisticsComponent` -- MEME residu structurel documente (case-202 §6).

    `tiles_moved_this_battle` / `tiles_moved_this_turn` / `tiles_moved_last_turn` = mirror des TROIS
    champs `ActorStatisticsComponent @+0xec` / `@+0xf0` / `@+0xf4` (case-322-r1).
    ⚠ Le composant natif est bien l'`ActorStatisticsComponent`, PAS le `UnitComponent` : le getter
    de `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` et celui de
    `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` resolvent le MEME composant
    que `IdunBattle.Operations.StartTurnOperation$$ResetUnit` passe a
    `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetAttacksReceivedThisTurn`. Loges
    ici comme `received_damage_this_turn` / `last_hit_damage_taken_*` -- MEME residu structurel
    documente (case-202 SS6).
      * ECRITURE : `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state)` =
        `if (tiles < 1) return; comp[0xec] += tiles; comp[0xf0] += tiles;` -- un `+=`, PAS une
        affectation, et un no-op silencieux pour `tiles <= 0`. QUATRE call-sites natifs :
        les DEUX branches d'`IdunBattle.Operations.MoveUnitOperation$$Execute` (simulation et
        reelle), `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` et
        `IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved`.
      * ROULEMENT, a la FIN de CHAQUE tour :
        `IdunBattle.Operations.EndTurnOperation$$Execute` itere `GetAllUnits` et appelle
        `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(comp, wasOwnTurn)` =
        `if (wasOwnTurn) comp[0xf4] = comp[0xf0]; comp[0xf0] = 0;`. Le reset de `+0xf0` est donc
        INCONDITIONNEL et GLOBAL (toutes les unites, pas seulement celles du joueur finissant) ;
        `wasOwnTurn` = `PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui finit CONTIENT l'unite.
        ⚠ Ce n'est PAS `StartTurnOperation$$ResetUnit` (qui, lui, ne touche ni 0xf0 ni 0xf4).
      * LECTURE : `TilesMovedThisTurnFormula$$Calculate` rend `+0xf0`,
        `IdunBattle.Entities.Formulas.TilesMovedLastTurnFormula$$Calculate` rend `+0xf4`. Le noeud
        DSL `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn` a SIX consommateurs natifs :
        `ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` / `$$GetCurrentDamageBonus` /
        `$$GetExtraDamageMultiplier`, `IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$IsValidAttackForBuff`,
        `MastersOfManoeuvreAbility$$CreateTrigger` et `SmashaEadAbility$$CreateTrigger`.
        `tiles_moved_this_battle` (+0xec) n'a AUCUN lecteur porte : il est ecrit pour rester le
        mirror exact du `+=` double de `RecordTilesMoved`, jamais lu.

    `blocks_made_this_turn` (#366-r1) = mirror de `ActorStatisticsComponent @+0x8c`, le compteur de
    coups BLOQUES par cette unite depuis le debut de son tour. Loge ici comme
    `received_damage_this_turn` / `tiles_moved_*` -- MEME residu structurel documente (case-202 SS6 :
    le foyer natif est l'`ActorStatisticsComponent`).
      * ECRITURE : `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterBlockMade`
        (`+0x8c += 1`), atteinte par `IdunBattle.Operations.RegisterBlockOperation$$Execute` <- slot
        `IOperationProcessor` 0x4c <- `IdunBattle.Operations.ADamageOperation$$RegisterBlocks`, que
        `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` appelle **PAR COUP**, au retour
        d'`ExecuteHit` -- donc APRES l'emission de `On(UnitBlocked)` par
        `ADamageOperation$$EvaluateAfterHitTriggers`. Cet ORDRE est ce qui rend le gate
        `NOT HasBlockedThisTurn` vrai au premier coup bloque du tour.
      * RESET : `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetBlocksMadeThisTurn`
        (`+0x8c = 0`), appele par `IdunBattle.Operations.StartTurnOperation$$ResetUnit` dans la MEME
        sequence que `ResetAttacksReceivedThisTurn` / `ResetReceivedDamageThisTurn` -> portee = les
        unites du joueur ENTRANT (cf. `operations/turnflow.py`).
      * LECTURE : `IdunBattle.Entities.Triggers.TimesBlockedThisTurnFormula$$Calculate` rend `+0x8c` ;
        `IdunBattleLogic.Entities.DSLTriggers$$HasBlockedThisTurn` = `AmountIsGreaterThanZero` de
        cette formule. UNIQUE consommateur porte : le gate de
        `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility$$CreateTrigger`.

    `blocks_made_this_battle` (#393-r1) = mirror de `ActorStatisticsComponent @+0x88`. MEME forme que
    `tiles_moved_this_battle` : `RegisterBlockMade` pousse les DEUX compteurs (`+0x8c` ce tour,
    `+0x88` la bataille) et `ResetBlocksMadeThisTurn` n'en remet qu'UN a zero (`+0x8c`) -- verifie au
    decompile. AUCUN lecteur porte : le seul consommateur natif est
    `IdunBattle.Core.Services.BattleStatisticQuery$$GetTotalBlocksMadeByUnit` (statistiques de fin de
    bataille, recursif sur les unites ENFANTS quand `IncludeAttackerChildren`), sans pendant porte --
    donc aucun observable de COMBAT ne le distingue. Ecrit quand meme, pour rester le mirror exact du
    `+=` double, exactement comme `tiles_moved_this_battle`.

    `times_healed_this_turn` (#1037) = mirror de `ActorStatisticsComponent @+0xd4`, le compteur de
    fois ou cette unite a ETE SOIGNEE depuis le debut de son tour. Loge ici comme
    `blocks_made_this_turn` -- MEME residu structurel (le foyer natif est l'`ActorStatisticsComponent`,
    case-202 SS6).
      * ECRITURE : `IdunBattle.Operations.HealUnitOperation$$Execute` fait `*(int *)(stats + 0xd4) =
        *(int *)(stats + 0xd4) + 1` sur les statistiques de l'unite SOIGNEE, **une fois par soin** --
        et l'increment est INCONDITIONNEL une fois passe le gate de sortie anticipee (il tombe hors
        du `if (healed >= 1) { ... }` qui, lui, alimente `+0xc8` et `+0xe4`). Il PRECEDE l'emission
        des trois vecteurs `On(0x1e)` / `On(0x2b = UnitHealed)` / `On(0x2c =
        UnitHealedWithRemoveEffects)` : au premier soin d'un tour, un consommateur de ces vecteurs
        lit donc deja **1**.
      * RESET : `IdunBattle.Operations.StartTurnOperation$$ResetUnit` (`*(undefined4 *)(stats + 0xd4)
        = 0`), dans la MEME sequence que `ResetBlocksMadeThisTurn` / `ResetReceivedDamageThisTurn` et
        juste APRES le roulement `+0x70 = +0x6c` -> portee = les unites du joueur ENTRANT
        (cf. `operations/turnflow.py`). ⚠ Il n'est PAS touche par
        `ActorStatisticsComponent$$ResetThisTurn`, qui n'efface que `+0xf0`/`+0x78`/`+0xe4`/`+0x58`/
        `+0xa0` -- lu au decompile, pas suppose.
      * LECTURE : `IdunBattle.Entities.Formulas.TimesHealedThisTurnFormula$$Calculate` resout son
        selecteur, prend l'`ActorStatisticsComponent` de l'entite et rend `*(uint *)(comp + 0xd4)`.
        UNIQUE consommateur porte : le gate `AmountIsEqual(TimesHealedThisTurn(Target), Const(1))` de
        `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility$$CreateTrigger`
        (« gets healed for the FIRST time this turn »).

    `feet` (#R30) = mirror de `UnitComponent._feet` @+0x78 -- l'`OrderedSet<int>` des ids des
    ENTITES-PIEDS de l'unite (`Blueprints.UnitFoot`, chacune portant un `UnitFootComponent
    {UnitId@0x10, TileId@0x14}`), rempli par `IdunBattle.Operations.AddUnitOperation$$Execute`
    (`UnitComponent$$ClearFeet` puis un `UnitComponent$$AddFoot` PAR TUILE, dans l'ordre de la
    liste de tuiles recue). Le port n'ayant ni entite-tuile ni entite-pied, la chaine
    `pied -> UnitFootComponent.TileId -> tuile` est COLLAPSEE en un `(col,row)` (meme collapse
    que `PositionComponent`) : `feet` = la liste ORDONNEE des tuiles de l'empreinte.

      * `None` = unite a UN pied -- le cas NOMINAL de tout le moteur : l'empreinte est alors
        `[PositionComponent]` et rien ne change (cf. `get_unit_feet`). On ne materialise la liste
        que pour les unites MULTI-HEX, ce qui garde les ~200 sites qui lisent `PositionComponent`
        strictement inchanges.
      * `feet[0]` est la MAIN TILE (`IdunBattle.Entities.EntityExtensions$$GetMainTileId` prend
        `_feet[0]` puis lit le `TileId` de CE pied), et c'est l'INVARIANT que `set_unit_feet`
        maintient : `feet[0] == (PositionComponent.col, PositionComponent.row)`.
      * tailles supportees = **1, 3, 7**, declarees par l'enum `IdunBattle.Core.Services.
        TargetingRule` (`CasterHas1/3/7Tiles`, `TargetHas1/3/7Tiles`) et imposees par
        `IdunBattle.Core.Services.MovementQuery$$IsValidUnitFeetList`. Seul le **3** a un
        producteur dans ce build (`DSLFactory.ThreeTileUnitSpawnShape` <- `DutyEternalAbility` /
        `AetherStrideAbility`).
    """
    __slots__ = ("visual_id", "alive", "ai_controlled", "turn_defeated", "killed_this_turn",
                 "turns_finished",
                 "times_attacked_this_turn", "total_times_attacked",
                 "received_damage_this_turn", "revive_used_this_turn", "pending_revive", "parent_id",
                 "death_source", "last_hit_damage_taken_this_turn",
                 "last_hit_damage_taken_last_turn", "feet", "damaged_units_this_phase",
                 "charged_unit_ids", "current_turn_start_tile", "revived_by_abilities",
                 "tiles_moved_this_battle", "tiles_moved_this_turn", "tiles_moved_last_turn",
                 "blocks_made_this_turn", "blocks_made_this_battle",
                 "times_healed_this_turn",
                 "turns_with_attacks_made", "units_attacked_this_turn", "attacks_made_this_turn",
                 "critical_hits_this_turn",
                 "total_attacks_made", "defeated_units_melee", "defeated_units_other",
                 "total_defeated_units", "death_killer_id", "previous_position_this_turn",
                 "previous_position",
                 "movement_target_override", "rarity", "defeated_by_melee")

    def __init__(self, visual_id: Optional[str], alive: bool, ai_controlled: bool = False,
                 parent_id: Optional[int] = None):
        self.visual_id = visual_id
        self.alive = alive
        self.ai_controlled = ai_controlled
        self.feet: Optional[List[tuple]] = None      # `_feet` @+0x78 ; None = 1 pied (cf. docstring)
        self.turn_defeated = None
        # `UnitComponent + 0x17a` — le BOOLEEN que lit `IdunBattleLogic.Entities.DSLTriggers$$
        # IsKilledThisTurn`. TRI-ETAT : `None` = NON MESURE (aucun canal ne publie ce champ, cf. la
        # docstring de classe), `True`/`False` = mesure du run. Ne PAS le confondre avec son voisin
        # `turn_defeated` (`+0x17c`, un ENTIER) : ce sont deux champs distincts, aux lecteurs
        # distincts (`KilledThisTurnTrigger$$ShouldTrigger` vs
        # `IdunBattle.Entities.Formulas.TurnDefeatedFormula$$Calculate`).
        self.killed_this_turn = None
        # `UnitComponent + 0x178` = **`DefeatedByMeleeAttack`**, le byte que
        # `IdunBattle.Operations.KillUnitOperation$$Execute` ecrit sur la VICTIME juste apres
        # `On(PreUnitDeath)` et **avant la garde revive**, avec la valeur EXACTE qu'il passe ensuite
        # en `inMelee` a `ActorStatisticsComponent$$RegisterDefeatedUnit` sur le TUEUR (un seul
        # calcul : `rangeType.HasValue && rangeType.GetValueOrDefault() == Melee(1)`).
        # DEUX faces l'ecrivent, et elles doivent rester d'accord : la SIMULATION
        # (`damage.py::_kill_unit_operation`, via `KillUnitOptions+0x3c`) et le SEEDING
        # (`decisionView.units[].defeatedByMelee`, publie par `readUnitDeathMeta`).
        # TRI-ETAT : `None` = NON MESURE (voie de mort qui ne transporte pas d'`AttackRangeType` --
        # crush `ForSteppable`, feuille DSL `Kill` -- ou etat charge sans le champ). Un lecteur doit
        # DIRE ce qu'il fait de l'absence : `IsDefeatedByMeleeAttack` natif lit un byte d'un
        # composant `memset` a 0, donc l'absence se lit FAUX cote natif -- mais le port distingue
        # les deux pour que ses consommateurs puissent retomber sur leur approximation nommee.
        self.defeated_by_melee = None
        # `UnitComponent + 0x5c` — cf. la docstring de classe (bloc `turns_finished`). 0 a la
        # creation, exactement comme le champ natif d'une entite fraichement construite : une unite
        # deployee au setup comme un summon apparu en cours de partie partent tous les deux de 0,
        # et c'est `EndTurnOperation` qui les fait diverger.
        self.turns_finished = 0
        self.times_attacked_this_turn = 0
        # `ActorStatisticsComponent @+0x34` — cf. la docstring de classe. 0 a la creation, comme le
        # champ natif d'une entite fraichement construite ; JAMAIS remis a zero ensuite.
        self.total_times_attacked = 0
        self.received_damage_this_turn: dict = {}
        self.revive_used_this_turn = False
        # `ActorStatisticsComponent @+0x6c` / `@+0x70` — cf. la docstring de classe (bloc
        # `last_hit_damage_taken_*`). Loges ici comme `received_damage_this_turn` (meme residu
        # structurel : le foyer natif est l'ActorStatisticsComponent).
        self.last_hit_damage_taken_this_turn = 0
        self.last_hit_damage_taken_last_turn = 0
        self.pending_revive = None            # `Nullable<ReviveData>` @UnitComponent+0xa8
        self.parent_id = parent_id            # `ParentComponent` id @+0x10 (summoner)
        self.death_source = None              # `Nullable<DamageSource>` @UnitComponent+0x108
        self.damaged_units_this_phase: list = []   # `ActorStatisticsComponent+0x48` (cf. docstring)
        # `List<int>` @UnitComponent+0x190 — les unites que CETTE unite a CHARGEES (cf.
        # `update_charging` / `IdunBattle.Core.Services.BattleQuery$$IsCharging`). Videe par
        # `FinishUnitTurnOperation` (fin d'activation) -> semantique « charge CE TOUR ».
        self.charged_unit_ids: list = []
        # `int` @UnitComponent+0x18c — cf. la docstring de classe (bloc `current_turn_start_tile`).
        # None = aucun turn-start n'a encore tourne pour cette unite (mirror du 0 natif : le
        # selecteur `CurrentTurnStartTile` rend alors une liste VIDE).
        self.current_turn_start_tile: Optional[int] = None
        # `HashSet<AbilityOrEffect>` @ActorStatisticsComponent+0xe0 — cf. la docstring de classe
        # (bloc `revived_by_abilities`). Loge ici comme `last_hit_damage_taken_*` (meme residu
        # structurel : le foyer natif est l'ActorStatisticsComponent).
        self.revived_by_abilities: set = set()
        # `ActorStatisticsComponent @+0xec/+0xf0/+0xf4` — cf. la docstring de classe (bloc
        # `tiles_moved_*`). 0 a la creation, comme les champs `int` d'un composant natif frais.
        self.tiles_moved_this_battle = 0
        self.tiles_moved_this_turn = 0
        self.tiles_moved_last_turn = 0
        # `ActorStatisticsComponent @+0x8c` / `@+0x88` — cf. la docstring de classe (blocs
        # `blocks_made_this_turn` et `blocks_made_this_battle`).
        self.blocks_made_this_turn = 0
        self.blocks_made_this_battle = 0
        # `ActorStatisticsComponent @+0xd4` -- cf. la docstring de classe (bloc
        # `times_healed_this_turn`). 0 a la creation, comme un compteur `int` natif frais.
        self.times_healed_this_turn = 0
        # `ActorStatisticsComponent @+0x30` (`TotalTurnsWithAttacksMade`) et `@+0x40`
        # (`unitsAttackedThisTurn`) -- cf. `register_attack_made` / `unit_turns_with_attacks_made` /
        # `reset_units_attacked_this_turn`. Loges ici comme `blocks_made_*` et `tiles_moved_*`
        # (MEME residu structurel : le foyer natif est l'`ActorStatisticsComponent`, case-202 SS6).
        # 0 / vide a la creation, comme un composant natif frais.
        self.turns_with_attacks_made = 0
        # #940 : un `dict` et NON un `set` -- le champ natif `ActorStatisticsComponent+0x40` est un
        # `idun.shared.collections.OrderedSet`, et son ORDRE D'INSERTION est LU, pas seulement son
        # contenu : `IdunBattle.Entities.Selectors.UnitsAttackedThisTurnSelector$$Select` l'itere tel
        # quel, et `KissOfDeathAbility$$ExecuteBehaviour` en prend `Last(..., 1)` (la DERNIERE unite
        # frappee -- « reappears in a hex adjacent to the last target hit ») puis `AtIndex(..., 1)`.
        # Un `set` Python itere dans l'ordre du HASH : la « derniere » y aurait ete arbitraire, et
        # l'ecart aurait ete SILENCIEUX (une tuile d'atterrissage plausible, mais pas la bonne).
        # `dict` garde l'ordre d'insertion (garanti depuis 3.7) et sert `in`/`len`/verite/`clear`
        # exactement comme un `set` -- seul `.add(x)` devient `[x] = None` (un seul site : ci-dessous
        # dans `register_attack_made`).
        self.units_attacked_this_turn: dict = {}
        # `ActorStatisticsComponent+0x24` = ATTAQUES EMISES CE TOUR (#508-r1). ⚠ Ce n'est PAS
        # `times_attacked_this_turn` (+0x38, attaques RECUES) ni `turns_with_attacks_made` (+0x30,
        # compte de TOURS). Ecrit par `register_attack_made`, remis a 0 par
        # `reset_units_attacked_this_turn` -- ce dernier NOM ne le dit pas, l'assembleur si
        # (`*(undefined8*)(this + 0x24) = 0` : une ecriture 64 bits qui couvre +0x24 ET +0x28).
        self.attacks_made_this_turn = 0
        # `ActorStatisticsComponent+0x54` = les COUPS CRITIQUES portes CE TOUR (#521-r10). Le champ
        # est ecrit d'un `+= totalCrits` par `IdunBattle.Entities.Components.ActorStatisticsComponent$$
        # RegisterAttackMade` (LU : `*(int *)((longlong)this + 0x54) = *(int *)((longlong)this + 0x54)
        # + (int)totalCrits;`) et remis a 0 par `...$$ResetUnitsAttackedThisTurn` -- le MEME couple
        # ecrivain/reset qu'`attacks_made_this_turn` (+0x24), d'ou son voisinage ici. ⚠ Ce n'est PAS
        # un cumul de bataille : les deux `ActorStatisticsComponent$$ResetThisTurn` ne le touchent
        # pas, mais `ResetUnitsAttackedThisTurn` -- appele par `IdunBattle.Operations.
        # StartTurnOperation$$Execute` / `$$ResetUnit` / `$$ResetMachine` -- l'efface a chaque entree
        # de tour. LECTEUR UNIQUE cote natif : `IdunBattle.Entities.Formulas.
        # CriticalHitsThisTurnFormula$$Calculate` (`unit_critical_hits_this_turn` ici).
        self.critical_hits_this_turn = 0
        # `ActorStatisticsComponent+0x20` = `TotalAttacksMade` (#926). ⚠ Ce n'est NI
        # `turns_with_attacks_made` (+0x30, un compte de TOURS), NI `attacks_made_this_turn` (+0x24,
        # remis a 0 chaque tour) : c'est un CUMUL DE BATAILLE que RIEN ne remet a zero
        # (`reset_units_attacked_this_turn` ecrit `*(u64*)(this+0x24) = 0`, donc +0x24/+0x28 -- pas
        # +0x20). Ecrit par `register_attack_made`, lu par `unit_total_attacks_made`, seede par
        # `snapshot._apply_actor_stats` (le hook publie deja `totalAttacksMade`).
        self.total_attacks_made = 0
        # #951-r1 -- `ActorStatisticsComponent @+0xa8` (defaites en MELEE) et `@+0xb0` (les autres),
        # les DEUX listes d'ids qu'ecrit `IdunBattle.Entities.Components.ActorStatisticsComponent$$
        # RegisterDefeatedUnit(this, id, inMelee)`, LU verbatim :
        #
        #     *(int *)(this + 0xa0) += 1;                          # compteur TOTAL, inconditionnel
        #     if ((char)inMelee == '\0') lst = *(this + 0xb0);     # les AUTRES
        #     else                       lst = *(this + 0xa8);     # la MELEE
        #     if (lst != 0) Add(lst, id);
        #
        # La PARTITION est portee depuis #1082, et ce qui l'a debloquee n'est PAS un capteur neuf :
        # `inMelee` n'a jamais eu a etre DEVINE. `IdunBattle.Operations.KillUnitOperation$$Execute`
        # passe a `RegisterDefeatedUnit` **la valeur meme** qu'il vient d'ecrire dans
        # `UnitComponent+0x178` (`DefeatedByMeleeAttack`) sur la VICTIME -- un seul et meme
        # `local_378[0]` dans le decompile, ecrit en `+0x178` puis reencode en argument. Or ce byte
        # est publie depuis #185 sous `decisionView.units[].defeatedByMelee`. Le booleen du TUEUR se
        # LIT donc sur la VICTIME, ce qui rend la partition reconstructible d'un canal deja la.
        # ⚠ Ce n'est PAS `units_attacked_this_turn` (+0x40, remis a zero chaque tour) : c'est un
        # CUMUL DE BATAILLE, que rien ne remet a zero.
        self.defeated_units_melee: list = []       # `@+0xa8`
        self.defeated_units_other: list = []       # `@+0xb0`
        # `@+0xa0` -- le compteur que `RegisterDefeatedUnit` incremente AVANT le branchement, donc
        # sans regard pour `inMelee`. Distinct de `len(defeated_units)` : le natif compte les APPELS,
        # la liste ne garde pas les doublons a la lecture (`UnitsDefeatedBySelector` rend un
        # `OrderedSet`). Aucun lecteur porte a ce jour -- inscrit parce que l'ecrivain unique est
        # mirrore ici et qu'il l'ecrit ; ne pas cabler de consommateur sans son artefact natif.
        self.total_defeated_units = 0
        # (`defeated_units` n'est PAS un champ : c'est la VUE `@+0xa8` ++ `@+0xb0`, cf. la property
        # plus bas. Le natif n'a aucun champ fusionne -- en faire un ici serait un artefact du port.)
        # #1033-r3 -- le KillerId SEUL, seede depuis `decisionView.units[].killerId` par
        # `snapshot._load_death_sources`. TRI-ETAT : `None` = NON MESURE. Ce champ existe parce que
        # le canal ne publie QU'UNE des trois composantes de la `DamageSource` (@+0x108) : fabriquer
        # un `death_source` complet imposerait d'inventer `DamageReason` et le
        # `Nullable<AbilityOrEffect>`, que DEUX lecteurs portes consomment vraiment
        # (`reactivate_overwatch` lit les deux, `empyric_ambush` le second). Ne JAMAIS le lire en
        # direct : passer par `death_killer_id`, le foyer qui compose les deux sources.
        self.death_killer_id = None
        # #1082 -- `MovementComponent+0x98` (`PreviousPositionThisTurn`). Ecrit AVEC `+0x88` par
        # `save_previous_position`, mais efface EN PLUS par `StartTurnOperation$$Execute`. Loge ici
        # et non sur la `PositionComponent` parce qu'il doit survivre au retrait de plateau -- cf.
        # la docstring de `PositionComponent`, ou l'ecart de collapse est motive.
        self.previous_position_this_turn = None
        # #448-r7 -- `MovementComponent+0x88` (`PreviousTile`), le JUMEAU du champ ci-dessus. Les
        # DEUX sont ecrits ensemble par `save_previous_position`, avec la MEME valeur, et le
        # decompile de `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` montre qu'ils
        # vivent sur le MEME composant natif : les deux ecritures resolvent leur composant par le
        # MEME `GetComponent<...>` et ecrivent le MEME `UnitPositionId` a `+0x88` puis `+0x98`.
        #
        # Il vivait sur la `PositionComponent`, que `set_unit_feet(uid, [])` SUPPRIME au retrait de
        # plateau -- ce que le natif ne fait JAMAIS au `MovementComponent` (le retrait ne met a zero
        # que les `TileId` des pieds). Le champ etait donc DETRUIT par une sortie de plateau alors
        # que le natif le CONSERVE. C'etait un probleme d'EMPLACEMENT, pas d'ecriture : l'ecriture
        # etait juste, et aucun `write` n'etait fautif.
        #
        # ⚠ CE QUI LES SEPARE RESTE INCHANGE : `previous_position_this_turn` (`+0x98`) est en OUTRE
        # efface par `StartTurnOperation$$Execute` ; `previous_position` (`+0x88`) ne l'est pas --
        # son seul remetteur a zero est `ResetPreviousPositionBehaviour$$Execute`.
        self.previous_position = None
        # `Nullable<UnitPositionId>` a `+0xa8` du composant que `IdunBattle.Operations.
        # MoveUnitOperation$$Execute` ET `IdunBattle.Operations.OverrideMovementTargetOperation$$
        # Execute` recuperent tous DEUX par la MEME paire de caches (#448-r1) -- la DESTINATION
        # EFFECTIVE du mouvement en cours. Ce n'est PAS un champ « libre » : c'est un canal
        # in/out d'UNE SEULE Operation, et sa duree de vie tient dans un `MoveUnitOperation` :
        #
        #     MoveUnitOperation$$Execute :
        #         comp.MovementTargetOverride = Nullable(UnitPositionId(position))   # POSE
        #         SetReservation(unit, position)
        #         if (!options.skipPreMoveTriggers) {                                # +0x12
        #             publish On(0x1f = PreUnitMove)          <- un trigger peut ECRASER le champ
        #             if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }
        #         }
        #         ovr = comp.MovementTargetOverride ; comp.MovementTargetOverride = null  # CONSOMME
        #         if (!ovr.HasValue || IsDead(unit)) { RemoveReservation ; return }
        #         if (ovr.Value.ToUnitPosition() != position) {
        #             RemoveReservation(position) ; options.skipPreMoveTriggers = true
        #             return Execute(unit, <la nouvelle position>, trig, options)   # RECURSION
        #         }
        #         ... suite normale du mouvement ...
        #
        # SEUL ECRIVAIN EXTERNE : `OverrideMovementTargetOperation$$Execute`, elle-meme atteinte
        # par la SEULE feuille `IdunBattleLogic.Entities.DSLBehaviors$$OverrideUnitMovementTarget`
        # (`OverrideUnitMovementTargetBehaviour$$Execute`, vslot 0x49 du processor). Son unique
        # call-site du build est `...StormboyzStrike_MissAbility$$CreateBehaviour`.
        # `None` = aucun mouvement en cours (l'etat au repos) ; `(col, row)` = la destination.
        # ⚠ L'identite NOMMEE du composant natif porteur n'est PAS resolue : le `Copy` de
        # `IdunBattle.Entities.Components.UnitComponent` ne montre pas ce champ (il est value-type,
        # donc deja couvert par le `MemberwiseClone`), mais son `Nullable<AttackHit>` occupe
        # exactement `+0x98..+0xa7`, ce qui laisse `+0xa8` libre pour un `Nullable` de 16 octets.
        # Le port le loge ici comme il loge deja `ActorStatisticsComponent` (meme residu
        # structurel) ; `pending_revive` ci-dessus cite le MEME offset pour un AUTRE composant --
        # les deux paires de caches natives sont distinctes, il n'y a pas de collision.
        self.movement_target_override: Optional[tuple] = None
        # #999-r3-r2 -- `BaseUnitComponent.Rarity` (`+0x74`), le champ que lisent
        # `IdunBattle.Entities.UnitExtensions$$HasRarity` et
        # `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` apres
        # `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent(e)`.
        #
        # POURQUOI ICI et pas seulement dans `UnitContext` (ou #999-r3 l'avait pose). Le porteur
        # natif est `BaseUnitComponent`, la base COMMUNE de `UnitComponent` et `MachineComponent` :
        # toute entite d'unite en porte un, VIVANTE OU NON -- une unite qui a FUI garde sa rarete,
        # et un cadavre aussi. Le port, lui, ne batit un `UnitContext` que depuis
        # `combatSnapshot.units[]`, qui est ALIVE-ONLY : la rarete d'un mort etait donc
        # structurellement `None`, donc `HasRarity` FAUX et `UnitsWithRarity(AllDeadUnits(...))`
        # VIDE -- une degradation RESTRICTIVE. Le canal, lui, la porte deja
        # (`combatSnapshot.unitsNotAlive[].rarity`, #1039, pose exactement pour cette raison).
        # Seede par `snapshot._load_unit_rarity` depuis les DEUX blocs du meme canal ; lu par
        # `abilities/behaviours/context._unit_dict` en REPLI du ctx (meme forme que le repli
        # gameconfig des traits d'un cadavre, #226).
        #
        # TRI-ETAT : `None` = NON MESURE (canal muet, ou etat monte sans `combatSnapshot`).
        # JAMAIS `0` en repli -- `0` est `Rarity.Common`, une valeur parfaitement plausible
        # (meme discipline que `entities/rarity.py::measured_rarity`).
        self.rarity = None

    def add_foot(self, tile: tuple) -> None:
        """`IdunBattle.Entities.Components.UnitComponent$$AddFoot(footId)` = `_feet.Add(footId)`
        (`OrderedSet` -> pas de doublon, ORDRE d'insertion conserve) + invalidation du cache
        d'enumerateur @+0x80. Le port ajoute la TUILE du pied (collapse documente en tete)."""
        t = (int(tile[0]), int(tile[1]))
        if self.feet is None:
            self.feet = []
        if t not in self.feet:                       # OrderedSet.Add : idempotent
            self.feet.append(t)

    def clear_feet(self) -> None:
        """`IdunBattle.Entities.Components.UnitComponent$$ClearFeet` = `_feet.Clear()` +
        invalidation du cache @+0x80. Appele par `AddUnitOperation$$Execute` AVANT de reposer les
        pieds. Ici : liste VIDE (et non `None` -- `None` veut dire « un seul pied a la
        PositionComponent », ce qui n'est pas la meme chose qu'une unite sans pied)."""
        self.feet = []

    @property
    def defeated_units(self) -> list:
        """VUE `@+0xa8` ++ `@+0xb0`, dans l'ordre ou
        `IdunBattle.Entities.Selectors.UnitsDefeatedBySelector$$Select` les concatene. LECTURE SEULE.

        C'etait un CHAMP jusqu'a #1082, quand les deux listes natives etaient fusionnees faute de
        pouvoir alimenter `inMelee`. La derivation est le mirror plus fidele : le natif ne tient
        AUCUN champ fusionne, seulement deux listes qu'un lecteur unit a la lecture. La rendre
        derivee supprime aussi le risque qu'un ecrivain futur pousse dans la vue sans choisir sa
        liste -- il n'y a plus qu'un foyer d'ecriture, `register_defeated_unit`."""
        return defeated_units_union(self)


class OwnerComponent(Component):
    """Propriétaire — `OwnerComponent` IdunBattle.Entities.Components.OwnerComponent$$.ctor. `team` = équipe (1/2) ; `player` = id du player
    (≠ team : team 1 = player 3, team 2 = player 4 ; un summon hérite team ET player du caster via
    `SpawnUnitOptions.CopyOwner`, cf. project_summon_team_model). `player` None si non capté.

    `overridden_from` (#590) : l'OWNER-SWAP TEMPORAIRE de
    `IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute` /
    `IdunBattle.Operations.ResetUnitOwnerOperation$$Execute`. Le natif porte DEUX slots --
    `OwnerComponent+0x10 = OwnerPlayerEntityId` (l'origine) et `+0x14 =
    OverriddenPlayerEntityId` (0 = pas d'override) -- et
    `IdunBattle.Entities.Components.OwnerComponent$$get_CurrentPlayerEntityId` rend l'override
    quand il est posé.

    ⚠ **LE PORT INVERSE LEQUEL DES DEUX SLOTS PORTE LE COURANT, ET C'EST DÉLIBÉRÉ.** Ici
    `team`/`player` restent **le COURANT** (c'est ce que lisent les ~100 sites du moteur :
    `AreEnemies`, `Friends`, `UnitTeamSelectionType`, la décision, le rendu de `view`) et
    `overridden_from` conserve le couple `(team, player)` D'ORIGINE, `None` quand aucun override
    n'est actif. Mirrorer littéralement les deux slots natifs aurait exigé de router tous ces
    lecteurs vers un `current_*` -- rayon de souffle sans rapport avec la tranche, et une
    dégradation SILENCIEUSE (un seul lecteur oublié = swap inerte). L'observable est le même :
    `is_owner_overridden` <=> `+0x14 != 0`, et le couple restauré au revert est bit-identique.

    ⚠ Le natif ne stocke QUE le player entity id ; l'ÉQUIPE en est dérivée
    (`PlayerComponent.Team`). Le port n'a pas d'entité-player, donc il bascule `team` ET `player`
    -- même dérivation, matérialisée."""
    __slots__ = ("team", "player", "overridden_from")

    def __init__(self, team: Optional[int], player: Optional[int] = None):
        self.team = team
        self.player = player
        self.overridden_from = None      # `+0x14 == 0` : aucun override actif


class MachineComponent(Component):
    """MACHINE OF WAR — `IdunBattle.Entities.Components.MachineComponent` (entité `EntityType.Machine`
    = 6, créée par `IdunBattle.Operations.AddMachineOperation$$Execute`). Comme `UnitComponent`, dérive de
    `BaseUnitComponent IdunBattle.Entities.Components.BaseUnitComponent$$.ctor` (d'où `VisualId`@0x20 valide sur les deux) ; son champ propre est
    `Position` @0x78 = `MachineOfWarPosition` (enum None=0 / Top=1 / Bottom=2), le SLOT de déploiement
    hors-plateau (le board doit l'offrir : `IdunBattle.Configuration.BoardConfiguration$$HasMachineOfWarPosition`).

    C'est le DISCRIMINANT « cette entité est une MoW » : une MoW n'a **ni `PositionComponent` ni
    `HealthComponent`** (mesuré via `dumpEntityComponents` sur l'entité Machine vivante) — elle n'est
    pas sur la grille et n'a pas de PV. Ses plateformes (`EntityType.MachinePlatform` = 7) portent le
    lien retour `MachinePlatformComponent.MachineId` (Nullable @+0x14 hasValue / @+0x18 value).

    Le port n'a pas de type d'entité : `UnitComponent` porte l'identité (rôle `BaseUnitComponent`) et
    CE composant marque la nature Machine + le slot.

    `removed` (#91) = la MoW a été RETIRÉE de la bataille par
    `IdunBattle.Operations.RemoveMachineOperation$$Execute` (`RemoveMachineFromPlatform` + event
    `0x2e` + `RemoveEffects`). Le natif ne détruit pas l'entité : il la détache de sa plateforme, ce
    qui la rend indisponible pour le reste du combat (i2 `DutyEternal` : « Galatian can no longer be
    used as a Machine of War for the rest of the battle »). Le port matérialise ce détachement par
    ce drapeau — c'est le pendant `MachineComponent` du `alive=False` d'une unité."""
    __slots__ = ("slot", "removed")
    SLOT_NONE = 0
    SLOT_TOP = 1
    SLOT_BOTTOM = 2

    def __init__(self, slot: Optional[int] = None, removed: bool = False):
        self.slot = slot
        self.removed = bool(removed)


def is_machine_of_war(entity) -> bool:
    """True si l'entité est une MACHINE OF WAR (porte un `MachineComponent`). Mirror du test natif
    de type d'entité (`EntityType.Machine` = 6) — le port n'ayant pas de champ `type` sur l'entité,
    la PRÉSENCE du composant Machine joue ce rôle (le natif ne le pose que sur les Machines)."""
    return entity is not None and entity.get_component(MachineComponent) is not None


class PositionComponent(Component):
    """Position sur le board — `PositionComponent` IdunBattle.Entities.Components.PositionComponent$$.ctor (et `UnitFootComponent`
    IdunBattle.Entities.Components.UnitFootComponent$$.ctor : UnitId@0x10, TileId@0x14). Coordonnées hex (col,row).

    ⚠ **NI `+0x88` NI `+0x98` NE VIVENT ICI, et c'est MESURE (#1082 puis #448-r7).** Les deux slots
    de position precedente sont ecrits ENSEMBLE, avec la MEME valeur, par
    `IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition` -- LU verbatim :

        if (previousPosition == null || previousPosition.Count < 1) return;   // gate de garde
        id = new UnitPositionId(previousPosition);
        comp.<+0x88> = new Nullable<UnitPositionId>(id);    <- `PreviousTile`
        comp.<+0x98> = new Nullable<UnitPositionId>(id);    <- `GetPreviousPositionThisTurn`

    Cote port ils sont TOUS DEUX sur le `UnitComponent` (`previous_position` et
    `previous_position_this_turn`), et la raison est la MEME pour les deux : le port a COLLAPSE
    `MovementComponent` et `UnitFootComponent` dans cette classe-ci, or `set_unit_feet(uid, [])` la
    **SUPPRIME** au retrait du plateau -- ce que le natif ne fait JAMAIS au `MovementComponent`
    (`IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` ne met a zero que les `TileId`
    des pieds, et ses DEUX ecritures de position precedente resolvent leur composant par le MEME
    `GetComponent<...>`). Les loger ici les effacerait donc a chaque sortie de plateau, alors que le
    natif les CONSERVE. MEME residu structurel de collapse que `times_attacked_this_turn`
    (case-202 SS6).

    Ce qui SEPARE les deux slots ne tient pas a leur porteur mais a leurs remises a zero :
      * `UnitComponent.previous_position` (`+0x88`) = la position precedente TOUT COURT. Lue par
        `IdunBattle.Entities.Selectors.PreviousTileSelector$$Select`
        (`comp.<+0x88>.HasValue ? UnitPositionIdExtensions.ToTileList(value) : new List()`) ;
        remise a zero par le SEUL `ResetPreviousPositionBehaviour$$Execute`.
      * `UnitComponent.previous_position_this_turn` (`+0x98`, #1082) = la position precedente **CE
        TOUR**. Lue par `IdunBattle.Entities.EntityExtensions$$GetPreviousPositionThisTurn` ;
        effacee **en plus** par `IdunBattle.Operations.StartTurnOperation$$Execute`, qui ecrit
        `comp.<+0x98> = comp.<+0xa0> = 0` pour chaque unite du pool (seconde boucle) -- `+0x88` n'y
        est PAS touche. C'est cette remise a zero supplementaire qui les separe."""
    __slots__ = ("col", "row")

    def __init__(self, col: int, row: int):
        self.col = col
        self.row = row


class PendingDamage:
    """#1020 -- mirror des trois champs LUS d'`IdunBattle.Core.Services.DamageAppliedResult`, la
    valeur que `IdunBattle.Operations.ApplyDamageOperation$$Execute` depose dans
    `FillUpStatComponent+0x64` (`Nullable<DamageAppliedResult>`) AVANT d'emettre
    `On(0x39 = EventTriggerType.PreDamageTaken)`, et qu'il **RELIT** juste apres pour decider ce
    qu'il applique reellement.

    Champs (offsets LUS dans `IdunBattle.Core.Services.DamageAppliedResult$$.ctor`) :
    `+0x00 damageProfileType`, `+0x04 healthDamage`, `+0x08 shieldDamage`. Le port ne porte que
    ces trois-la : ce sont les seuls que le pipeline relit apres l'emission
    (`FillUpStatComponent$$Reduce(hp, pending.healthDamage)` et
    `ApplyDamageOperation$$ReduceShield(.., pending.shieldDamage)`), et le seul que consomme
    `IdunBattle.Operations.TransferDamageOperation$$GetDamage`
    (`DamageAppliedResult$$get_Damage` = `+0x08 + +0x04`, mirror `total()` ci-dessous).

    ⚠ **CE N'EST PAS UN BONUS, C'EST UNE CONSOMMATION.** Un consommateur de
    `On(0x39)` qui pose `HealthComponent.pending_damage = None` **retire** le degat a la victime :
    la relecture native est un `System.Nullable<T>$$GetValueOrDefault`, donc un pending vide rend
    la struct ZERO et `Reduce(0)` n'enleve rien. C'est ce qui fait de `SaviorProtocols` un
    DEPLACEMENT de degat et non une duplication."""

    __slots__ = ("profile", "health", "shield")

    def __init__(self, profile: Optional[str], health: int, shield: int = 0):
        self.profile = profile
        self.health = int(health or 0)
        self.shield = int(shield or 0)

    def total(self) -> int:
        """`IdunBattle.Core.Services.DamageAppliedResult$$get_Damage` -- LU VERBATIM :

            return *(int *)(this + 8) + *(int *)(this + 4);      // shieldDamage + healthDamage

        C'est le montant que `TransferDamageOperation$$GetDamage` empaquette dans le
        `IdunBattle.Core.Damage` rendu, donc **le montant transfere** : bouclier COMPRIS."""
        return int(self.health) + int(self.shield)


class HealthComponent(Component):
    """PV — `HealthComponent` IdunBattle.Entities.Components.HealthComponent$$.ctor. `hp` courant, `hp_max` plafond.

    `minimal_health` = **plancher de PV** courant (`Nullable<int>` natif @+0x1c ; None = pas de plancher).
    Posé/effacé par le HP-floor `HypersensoryAbilities_MinimalHealthEffect` (Apply IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal / Revert
    IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal) — quand présent, `reduce()` empêche les PV de descendre sous `min(hp, minimal_health)`
    (mirror du clamp de `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`).

    `over_reduce` = **l'accumulateur de sur-reduction** `FillUpStatComponent+0x24` (#462-r4e-o-r1) :
    `Reduce` y ajoute `Math.Max(0, damage - applied)` -- le degat qui n'a PAS pu etre retire faute de
    PV. Il n'est non nul que sur une unite deja tombee a 0 PV (tant qu'elle encaisse, `damage ==
    applied`).

    ⚠ **IL EST BIEN REMIS A ZERO, et #462-r4e-o-r1 se trompait en ecrivant le contraire** (#462-r4e-o-r2).
    L'erreur venait d'avoir pris `IdunBattle.Entities.Components.FillUpStatComponent$$ResetOverReduce`
    pour le SEUL ecrivain du zero : ce symbole n'a effectivement aucun xref de code (table de methodes
    seule, donc jamais appele), mais **DEUX autres methodes de la meme classe ecrivent `this+0x24 = 0`
    EN LIGNE**, sans passer par lui -- c'est exactement l'absence qui ne prouve rien :

      * `IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` -- en QUEUE, **inconditionnel**
        (meme quand `filled <= 0`). Appelants (xrefs EXHAUSTIFS, 3 sites) :
        `IdunBattle.Operations.HealUnitOperation$$Execute`,
        `IdunBattle.Operations.RepairUnitOperation$$Execute` et
        `IdunBattle.Operations.ResurrectUnitOperation$$SetHealth`.
        => **tout SOIN, toute REPARATION et toute RESURRECTION remettent l'accumulateur a zero.**
      * `IdunBattle.Entities.Components.FillUpStatComponent$$Initialize` -- appelants :
        `IdunBattle.Operations.AddUnitOperation$$Execute`, `IdunBattle.Entities.Factories.UnitFactory$$Build`
        et `IdunBattle.Entities.Factories.UnitFactory$$InitHealth` (l'etat initial du port l'a deja a 0).

    ⚠ **Le REVIVE, lui, ne le remet PAS a zero -- et c'est un QUIRK NATIF, pas un trou de port.**
    `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` n'appelle NI `FillUp` NI `Initialize` (il
    passe par le slot 0x66 = `TransformUnit` de l'`OperationProcessor`, qui pose des modificateurs de
    stat -- les deux autres call-sites de ce meme slot sont
    `IdunBattle.Operations.SetupGameOperation$$ApplyModifiers` et
    `IdunBattle.Operations.TransformActorToConfigIdOperation$$UpdateStats`). Une unite REVIVEE entre
    donc dans l'attaque suivante avec l'accumulateur de sa vie precedente, et peut franchir le seuil
    d'`IsOverkill` des son premier coup recu. `revive.py` le mirrore en NE reposant rien.

    Il est LOAD-BEARING, et c'est une MESURE : la surcharge d'instance d'
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` l'AJOUTE au degat compare
    (`accum += (targetHealthBeforeAttack - GetStat(Health)) + healthComponent@+0x24`). Sans lui, le
    port pose `UnitFlag.Overkilled` un coup TROP TARD -- mesure live MC1_67/31337 `--hp-target 4000` :
    natif `[3583, 417, 0]`, port `[3583, 417, 0, 0]`.

    ⚠ `Reduce` **saute** l'accumulation quand le plancher `Minimum` est pose ET `> 0` (branche
    `if (0 < minimum) goto LAB_18107e699`) -- le meme gate qui rend `IsOverkill` faux sous plancher.

    ⚠ **`hp_max` N'EST PAS UN CHAMP — c'est `get_CurrentMaximumValue()` (#572-r1).** Le natif
    n'a AUCUN `StatComponent` pour la sante : `IdunBattle.Entities.UnitExtensions$$ApplyStatModifier`
    dispatche `StatType.Health` (case 5) vers `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier`,
    donc une stat-modification sur HEALTH atterrit dans le `ValueModification` (+0x28) **de ce
    composant-ci**, et le maximum observable est recalcule a chaque lecture :

        get_CurrentMaximumValue() = override ?? ( Math.Min(int.MaxValue - initial,
                                                  Math.Max(-initial, modTotal)) + base )

    Les deux champs BRUTS du natif sont distincts et le port les porte tous les deux :
    `max_initial` (+0x10, part `StatPart.Initial`) et `max_base` (+0x14, ce que
    `IdunBattle.Entities.Components.FillUpStatComponent$$Initialize` pose = `+0x10 = +0x14 = +0x18`).
    Le port en portait UN SEUL, figE : le canal de seed `observeBattle.hpMax` lit le champ brut
    `+0x14` (`game/match-state.ts::COMP_FIELD.hpMax`), PAS `GetStat(Health, StatPart.Maximum)` --
    donc `hp_max` ratait AUSSI les modifications deja posees au chargement, pas seulement celles
    posees en cours de simulation.

    `hp_max` reste donc lisible et assignable (setter = `ApplyModifier case 2`, qui pose
    `+0x14 = +0x10 = value`), mais sa LECTURE traverse desormais les modifications."""

    __slots__ = ("hp", "max_initial", "max_base", "max_modification", "max_override",
                 "minimal_health", "over_reduce", "pending_damage")

    #: `Math.Min(0x7fffffff - initial, ...)` de `get_CurrentMaximumValue` -- borne `int.MaxValue`
    #: du natif, un vrai scalaire (elle ne designe rien).
    _INT32_MAX = 0x7fffffff

    def __init__(self, hp: Optional[int], hp_max: Optional[int], minimal_health: Optional[int] = None,
                 over_reduce: int = 0, max_initial: Optional[int] = None,
                 max_modification: Optional[ValueModification] = None,
                 max_override: Optional[ValueOverride] = None):
        self.hp = hp
        # #1020 : `FillUpStatComponent+0x64` -- le `Nullable<DamageAppliedResult>` PENDANT.
        # HORS du seed (jamais serialise) : il ne vit qu'entre l'ecriture et la relecture d'UN
        # coup, a l'interieur d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`. Cf.
        # `PendingDamage` ci-dessous.
        self.pending_damage: Optional["PendingDamage"] = None
        # `Initialize(v)` pose `+0x10 = +0x14 = v` : sans capture separee du `+0x10`, le seed les
        # egalise -- c'est l'etat de deploiement du natif, et le seul que le canal publie.
        self.max_base = hp_max
        self.max_initial = hp_max if max_initial is None else max_initial
        self.max_modification = (max_modification if max_modification is not None
                                 else ValueModification())
        self.max_override = max_override if max_override is not None else ValueOverride()
        self.minimal_health = minimal_health
        self.over_reduce = int(over_reduce or 0)

    def current_maximum_value(self) -> Optional[int]:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$get_CurrentMaximumValue` -- MIRROR 1:1 :

            var o = override.GetOverrideValueWithModification(modification);   // +0x38, +0x28
            if (o.HasValue) return o.Value;
            return Math.Min(int.MaxValue - initial, Math.Max(-initial, modTotal)) + base;

        `None` si le max n'est pas capte (le port tolere l'absence de composant natif : c'est le
        meme tri-etat que `hp`)."""
        if self.max_base is None:
            return None
        ovr = self.max_override.get_override_value_with_modification(self.max_modification.total)
        if ovr is not None:
            return int(ovr)
        initial = int(self.max_initial or 0)
        m = max(-initial, int(self.max_modification.total))          # Math.Max(-initial, modTotal)
        m = min(self._INT32_MAX - initial, m)                        # Math.Min(int.MaxValue - initial, .)
        return m + int(self.max_base)

    @property
    def hp_max(self) -> Optional[int]:
        """Le maximum EFFECTIF = `get_CurrentMaximumValue()`. C'est ce que lisent tous les natifs
        mirroires par ce composant (`FillUp`, `MaxFillUp`, `Missing`, `RemainingPercentage`) et ce
        que publie `combatSnapshot.healthMax` (= `GetStat(unit, StatType.Health, StatPart.Maximum)`),
        par opposition a `observeBattle.hpMax` qui est le champ brut `max_base`."""
        return self.current_maximum_value()

    @hp_max.setter
    def hp_max(self, value: Optional[int]) -> None:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` **case 2** :
        `+0x14 = +0x10 = value`. Les modifications par-source ne sont PAS purgees (le natif ne les
        touche pas dans cette branche) ; seule la base bouge."""
        self.max_base = value
        self.max_initial = value

    def modify_max(self, source: object, amount: int) -> None:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$ModifyMax` =
        `ValueModification.Modify(+0x28, entityId, modification, isMultiplier, initialValue = +0x10)`.
        C'est ici qu'atterrit un stat-mod `StatType.Health` (`ApplyModifier` part
        `StatPart.Modification`), PAS dans `UnitStats`."""
        self.max_modification.modify(source, int(amount))

    def reverse_max_modification(self, source: object) -> None:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$ReverseMaxModification` =
        `ValueModification.ReverseModification(+0x28, entityId)` (part `StatPart.RESET_MODIFICATION`)."""
        self.max_modification.reverse_modification(source)

    def override_max(self, value: int, is_modifiable: bool = True) -> None:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$OverrideMax` =
        `ValueOverride.SetOverride(+0x38, entityId, value, isModifiable)` (part `StatPart.OVERRIDE`)."""
        self.max_override.override = int(value)
        self.max_override.is_modifiable = bool(is_modifiable)

    def remove_max_override(self) -> None:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$RemoveMaxOverride` =
        `ValueOverride.RemoveOverride(+0x38, entityId)` (part `StatPart.REMOVE_OVERRIDE`)."""
        self.max_override.override = None

    def missing(self) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$Missing` = `CurrentMaximumValue - Current`.
        0 si `hp`/max non captes."""
        mx = self.current_maximum_value()
        if mx is None or self.hp is None:
            return 0
        return int(mx) - int(self.hp)

    def max_fill_up(self, amount: int) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp` =
        `Math.Min(amount, CurrentMaximumValue - Current)` -- `fill_up` PRIVE de sa mutation, exactement
        comme `max_reduce` l'est de `reduce`. 0 si `hp`/max non captes."""
        mx = self.current_maximum_value()
        if mx is None or self.hp is None:
            return 0
        return min(int(amount), int(mx) - int(self.hp))

    def get_stat_part(self, part: int, source: object = None) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` -- MIRROR 1:1, sur le
        composant qui porte REELLEMENT la sante (le natif ne consulte aucun `StatComponent` pour
        `StatType.Health`) :

            CURRENT(0)                -> +0x18                       (le PV courant)
            CURRENT_PCT(1)            -> round(Max(0, cur / CurrentMaximumValue) * 100)
            MAXIMUM(2)                -> get_CurrentMaximumValue()
            INITIAL(3)                -> +0x10
            MISSING(4)                -> CurrentMaximumValue - Current
            MODIFICATION/MULTIPLIER(5/9) -> modTotal (ou la contribution d'UNE source)
            OVERRIDE(7)               -> override ?? +0x14

        ⚠ La branche `OVERRIDE` retombe sur le champ BRUT `+0x14` quand aucun override n'est pose --
        c'est bien `max_base`, pas le maximum effectif."""
        p = int(part)
        cur = int(self.hp or 0)
        if p == StatPart.CURRENT:                                    # 0
            return cur
        if p == StatPart.CURRENT_PCT:                                # 1
            mx = self.current_maximum_value()
            if not mx:
                return 0
            return round(max(0.0, cur / int(mx)) * 100)
        if p == StatPart.MAXIMUM:                                    # 2
            return int(self.current_maximum_value() or 0)
        if p == StatPart.INITIAL:                                    # 3
            return int(self.max_initial or 0)
        if p == StatPart.MISSING:                                    # 4
            return self.missing()
        if p in (StatPart.MODIFICATION, StatPart.MULTIPLIER_MODIFICATION):   # 5 / 9
            if source is not None:
                return self.max_modification.get_modification_from_entity(source)
            return self.max_modification.total
        if p == StatPart.OVERRIDE:                                   # 7
            ovr = self.max_override.override
            return int(ovr) if ovr is not None else int(self.max_base or 0)
        raise ValueError(f"StatPart {p} non implemente (HealthComponent)")

    def reduce(self, amount: int, *, ignore_minimal: bool = False) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` — retire `amount` PV, borné : jamais > PV courant (pas de
        PV négatifs) et, si `minimal_health` est posé et `ignore_minimal` est faux (param_3 natif = flag de
        bypass), jamais sous `min(hp, minimal_health)` (le HP-floor Hypersensory). Renvoie la réduction RÉELLE
        appliquée (`iVar3`). No-op (0) si `hp` non capté. Mute `self.hp` — **et `self.over_reduce`**
        (#462-r4e-o-r1) : la queue de `Reduce` fait `this[0x24] += Math.Max(0, damage - applied)`,
        SAUF si le plancher `Minimum` est posé et `> 0` (le `goto LAB_18107e699` du décompilé)."""
        if self.hp is None:
            return 0
        amount = max(0, int(amount))                    # Max(0, param_2)
        red = min(amount, self.hp)                       # Min(iVar2, current) — pas de PV négatifs
        if not ignore_minimal and self.minimal_health is not None:
            floor = min(self.hp, int(self.minimal_health))   # Min(current, minimalHealth.Value)
            red = min(self.hp - floor, red)              # Min(current - floor, iVar3) — clamp au plancher
        self.hp -= red
        if not (self.minimal_health is not None and int(self.minimal_health) > 0):
            self.over_reduce = int(self.over_reduce or 0) + max(0, amount - red)
        return red

    def max_reduce(self, amount: int, *, ignore_minimal: bool = False) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$MaxReduce` -- MIRROR 1:1 (#520) :

            r = Math.Min(amount, Current)
            if (!ignoreMinimum && Minimum.HasValue)
                r = Math.Min(Current - Math.Min(Current, Minimum.Value), r)
            return r

        C'est `reduce` PRIVE DE SA MUTATION : le meme calcul de borne, sans le `Current -= r` ni la
        queue `this[0x24] += Max(0, damage - applied)`. Le natif a bien les deux (`MaxReduce` CALCULE,
        `Reduce` APPLIQUE), exactement comme `MaxFillUp` / `FillUp`.

        ⚠ PAS de `Math.Max(0, amount)` ici, alors que `Reduce` en a un : le decompile de `MaxReduce`
        attaque directement par `Math.Min(amount, Current)`. Un `amount` negatif y rend donc un
        negatif, la ou `Reduce` rendrait 0. Ecart LU, conserve tel quel -- l'unique appelant porte
        (`operations/heal.py::predict_heal`, branche `predicted < 0`) lui passe `-predicted > 0`.

        No-op (0) si `hp` non capte."""
        if self.hp is None:
            return 0
        red = min(int(amount), int(self.hp))                 # Min(amount, current)
        if not ignore_minimal and self.minimal_health is not None:
            floor = min(int(self.hp), int(self.minimal_health))   # Min(current, minimalHealth.Value)
            red = min(int(self.hp) - floor, red)              # Min(current - floor, r)
        return red

    def fill_up(self, amount: int) -> int:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` -- MIRROR 1:1 (#462-r4e-o-r2) :

            filled   = Math.Min(amount, CurrentMaximumValue - Current)   # PAS de Max(0, .) natif
            Current += filled
            this[0x24] = 0                                               # <- INCONDITIONNEL
            return filled

        C'est le PENDANT de `reduce` : `reduce` ALIMENTE `over_reduce`, `fill_up` le PURGE. FOYER
        UNIQUE de cette purge cote port -- les trois appelants natifs de `FillUp`
        (`IdunBattle.Operations.HealUnitOperation$$Execute`,
        `IdunBattle.Operations.RepairUnitOperation$$Execute`,
        `IdunBattle.Operations.ResurrectUnitOperation$$SetHealth`) passent tous par ici, pour qu'il
        n'existe pas TROIS ports d'une meme queue native.

        ⚠ La remise a zero est **en QUEUE et INCONDITIONNELLE** : les deux operations natives
        appellent `FillUp` AVANT leur early-return `filled < 1` (heal : `if (!wasWounded && healed < 1
        && shieldPart < 1 && !HasFlag(target, 0x17)) return;` ; repair : `if (filled < 1 && shieldPart
        < 1 && !HasFlag(target, 0x18)) return;`). Un soin de **0**, et meme un soin **annule par
        `EffectType.Cursed`** (le natif calcule `healAmount = cursed ? 0 : predicted` puis appelle
        `FillUp` quand meme), purgent donc l'accumulateur. Les appelants doivent appeler `fill_up`
        AVANT de decider de sortir.

        ⚠ Pas de `max(0, .)` : le natif prend `Math.Min` nu, donc un `Current` au-dessus du plafond
        (modificateur de max retire) fait DESCENDRE les PV. Mirror conserve tel quel.

        No-op (0) si `hp`/`hp_max` non captes -- l'absence de composant natif, pas une garde inventee."""
        if self.hp is None or self.hp_max is None:
            return 0
        filled = min(int(amount), int(self.hp_max) - int(self.hp))   # Min(amount, max - current)
        self.hp = int(self.hp) + filled                              # current += filled
        self.over_reduce = 0                                         # this[0x24] = 0 (queue, inconditionnel)
        return filled

    def apply_modifier_set_current(self, value: int) -> None:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier`, branche `case 0`
        (#462-r4e-o-r2-r1) -- le QUATRIEME ecrivain de `this[0x24] = 0`, celui que la table de
        `#462-r4e-o-r2` avait MANQUE, et par lequel passe le REVIVE :

            switch (modifier@+4) {                       // ModifierType
              case 0: this[0x18] = modifier@+8 ;                  this[0x24] = 0 ; break;  // Current
              case 2: this[0x14] = this[0x10] = modifier@+8 ;     this[0x24] = 0 ; break;  // Max
              case 3: this[0x10] = this[0x14] = this[0x18] = v ;  this[0x24] = 0 ;         // tout
                      ValueModification.UpdateInitialValue(this+0x28, v) ; break;
              case 5/6/9 : ValueModification.Modify / ReverseModification    -- PAS de purge
              case 7/8   : ValueOverride.SetOverride / RemoveOverride        -- PAS de purge
              default    : NotImplementedException
            }

        CHAINE qui l'atteint depuis le revive, lue de bout en bout :
        `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` construit le modificateur
        `{StatType.Health = 5, ModifierType = 0, Min(amount, GetStat(unit, Health, MAX)), 0}`,
        l'emballe dans une liste et le passe au slot 0x66 = `TransformUnit` de l'`OperationProcessor`
        (3 arguments : entity, statModifiers, isHidden)
        -> `IdunBattle.Operations.TransformUnitOperation$$Execute`
        -> `IdunBattle.Entities.UnitExtensions$$ApplyStatModifiers` ->
        `IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` (XREF **UNIQUE** d'`ApplyModifier`)
        -> `case 0`. Le revive n'appelle donc ni `FillUp` ni `Initialize` -- ce qui reste vrai -- et
        purge quand meme.

        ⚠ C'EST UNE CORRECTION DE VERDICT, PAS UN AJUSTEMENT. `#462-r4e-o-r2` concluait « le REVIVE
        ne purge PAS, c'est un QUIRK natif a ne pas corriger », sur une table de trois ecrivains
        (`FillUp`, `Initialize`, `ResetOverReduce`) reputee exhaustive. MESURE LIVE du 2026-08-06
        (`probe_462r4eor2r1_retour_a_la_vie_over_reduce.py --volet revive`, victime a 2000 PV,
        seuil d'overkill 4000, accumulateur porte 59 807 -- facteur 15) : apres un revive
        `TaintedNarthecium` NATIF, l'attaque suivante rend **5** events `Amount`
        `[213, 214, 281, 255, 227]` et non **1**. Le natif s'aligne exactement sur l'hypothese
        « accumulateur PURGE ». Le port, lui, rendait `[213]`.

        Le mirror est ABSOLU (`Current = value`), pas relatif comme `fill_up` : c'est la difference
        de forme entre `case 0` et `FillUp`, et elle est visible des que `Current != 0`."""
        self.hp = int(value)                                         # this[0x18] = modifier@+8
        self.over_reduce = 0                                         # this[0x24] = 0


class EffectsOwnedComponent(Component):
    """Effets actifs portés — `EffectsOwnedComponent` IdunBattle.Entities.Components.EffectsOwnedComponent$$.ctor (chaque effet =
    `EffectComponent` IdunBattle.Entities.Components.EffectComponent$$.ctor). Ici : liste des NOMS d'effets actifs (vue pour le
    diff structurel). Le détail STRUCTURÉ (type/durée/params, matérialisé + évoluable)
    vit dans `State.effects` (`EffectsState`), source des modifiers de dégât."""
    __slots__ = ("effects",)

    def __init__(self, effects: List[str]):
        self.effects = effects


class ShieldInstance:
    """Une instance de bouclier (élément de la liste d'un `ShieldComponent`). Offsets natifs (RE
    `ShieldComponent.*`) : `id`@+0x10, source `AbilityOrEffect`@+0x14, `amount`@+0x30, `remaining`
    Nullable<int>@+0x3c (**None = permanent** = pas de durée → non tické par `RemoveOneTurn`).
    `source` = identité de l'ability/effet source (nom ; sert au merge `AddOrUpdateShield` ; None pour les
    boucliers CAPTÉS dont la source n'est pas lue)."""
    __slots__ = ("shield_id", "amount", "remaining", "source")

    def __init__(self, shield_id: int, amount: int, remaining: Optional[int], source=None):
        self.shield_id = shield_id
        self.amount = int(amount)
        self.remaining = remaining        # None = permanent
        self.source = source


class ShieldComponent(Component):
    """`IdunBattle.Entities.Components.ShieldComponent` IdunBattle.Entities.Components.ShieldComponent$$.ctor — pool de boucliers de l'unité
    (liste d'instances @+0x10 + compteur d'id @+0x18). Un bouclier ABSORBE le dégât AVANT les PV
    (`CalculateDamageOperation` : shield-first, sur le coup déjà réduit par l'armure fixe), et perd 1
    tour à chaque `EndTurn` (`RemoveOneTurnOnShields` → `RemoveOneTurn`). `GetTotalShield` = somme des
    `amount` (>0)."""
    __slots__ = ("shields", "next_id")

    def __init__(self, shields: Optional[List["ShieldInstance"]] = None, next_id: int = 0):
        self.shields: List[ShieldInstance] = shields if shields is not None else []
        self.next_id = next_id

    def get_total_shield(self) -> int:
        """`IdunBattle.Entities.Components.ShieldComponent$$GetTotalShield = Σ des `amount` des instances."""
        return sum(int(s.amount) for s in self.shields if s.amount > 0)

    def remove_one_turn(self) -> dict:
        """`IdunBattle.Entities.Components.ShieldComponent$$RemoveOneTurn : pour chaque instance À DURÉE (remaining non-None ;
        les permanentes sont sautées, gate `HasValue` @+0x3c), décrémente `remaining` ; si 0 → l'instance
        EXPIRE (retirée). Renvoie {removed:[ids], decremented:[ids]} (= `ShieldChanges`)."""
        removed: List[int] = []
        decremented: List[int] = []
        for s in list(self.shields):
            if s.remaining is None:                  # permanent → non tické
                continue
            s.remaining -= 1
            if s.remaining <= 0:
                removed.append(s.shield_id)
                self.shields.remove(s)
            else:
                decremented.append(s.shield_id)
        return {"removed": removed, "decremented": decremented}

    def add_or_update_shield(self, amount: int, source=None,
                             remaining: Optional[int] = None) -> Optional["ShieldInstance"]:
        """`IdunBattle.Entities.Components.ShieldComponent$$AddOrUpdateShield : accorde un bouclier. Si une instance de MÊME
        source ET MÊME durée restante existe → **cumule** l'`amount` (stack, branche `+= param_2`) ; sinon
        crée une nouvelle instance (id auto-incrémenté @+0x18). No-op si `amount<=0`. Renvoie l'instance.
        (Le tri d'insertion par durée croissante + la branche replace sans-durée = raffinements ;
        l'essentiel — id unique, stack même-source, total — est porté.)"""
        amount = int(amount)
        if amount <= 0:
            return None
        for s in self.shields:
            if s.source == source and s.remaining == remaining:
                s.amount += amount
                return s
        inst = ShieldInstance(self.next_id, amount, remaining, source=source)
        self.shields.append(inst)
        self.next_id += 1
        return inst

    def deplete(self, amount: int) -> int:
        """Absorption : retire jusqu'à `amount` PV de bouclier des instances. Le TOTAL absorbé est exact
        (= `min(amount, GetTotalShield)`) ; l'ATTRIBUTION par instance = ordre de liste (le natif insère
        trié par durée croissante ; l'ordre de déplétion exact = `ApplyDamageOperation`, non RE → front,
        approximation documentée n'affectant que QUELLE instance expire la première). Renvoie l'absorbé."""
        left = int(amount)
        for s in self.shields:
            if left <= 0:
                break
            take = min(s.amount, left)
            s.amount -= take
            left -= take
        self.shields = [s for s in self.shields if s.amount > 0]
        return int(amount) - left


class ForcedAttackTargetsComponent(Component):
    """`IdunBattle.Entities.Components` — cibles d'attaque FORCÉES de l'unité (liste d'ids d'entité).

    Posé/maj par `IdunBattle.Entities.Behaviours.AddForcedAttackTargetBehaviour$$Execute / retiré par
    `IdunBattle.Entities.Behaviours.RemoveForcedAttackTargetBehaviour$$Execute (le natif stocke des entity-ids dans une liste
    de composant bond @+0x50/+0x58). LU par `IdunBattle.Entities.Selectors.UnitForcedAttackTargetsSelector$$Select
    et surtout par `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` — le lecteur qu'interrogent
    la RÈGLE DE CIBLAGE `TargetIsAllowedForCaster` (bit 23, cf.
    `engine/runner/abilities/targeting.py::get_only_targets`), `TargetingQuery$$GetPossibleTargetsForOptions`
    et `MovementActionGenerator.<FindClosestEnemy>d__8$$MoveNext` (l'IA **doit** cibler ces unités ;
    cf. `GetAttackTarget` priorité `ForcedAttackTargets > nearest-enemy`, triggers.py).

    QUATRE ÉCRIVAINS NATIFS, relus (#436) :
      1. `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` — **liste := [BondedEntityId]**
         (REMPLACE, ne fusionne pas). C'est le TAUNT (effet 27 `Taunted_OnlySpecificTargets`).
      2. `IdunBattle.Entities.Effects.TauntedEffect$$RevertInternal` — **liste := []** (vidée).
      3. `AddForcedAttackTargetBehaviour$$Execute` — `Add` incrémental (unique constructeur :
         `InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour`, non porté).
      4. `RemoveForcedAttackTargetBehaviour$$Execute` — `Remove` (porté : `RemoveAllForcedAttackTargets`).

    `written_by` = l'INSTANCE d'effet dont l'écriture (voie 1) a produit la liste courante. Le port
    matérialise ce lien parce que le NET natif « effet 27 retiré ⇒ liste vidée » (voies 1+2) est
    maintenu côté natif par `DeactivateEffect -> RevertInternal`, par où passe TOUT retrait ; côté
    port un effet peut disparaître par plusieurs chemins (`remove_effect_instance`, l'expiration de
    timer d'`EffectsState.on_turn_end`, une poignée de `consumed = True` ad hoc) dont un seul est un
    foyer. Une mutation posée au seul foyer serait DÉSYNCHRONISÉE, et une liste fantôme fait REFUSER
    un cast que le natif accepte — dégradation RESTRICTIVE, l'exact inverse de la convention
    permissive du gate de cible. `get()` honore donc `written_by.consumed`, ce qui rend le
    `RevertInternal` quel que soit le chemin de retrait.

    ⚠ ÉCART NOMMÉ : `RevertInternal` natif VIDE la liste entière (y compris ce qu'un `Add` de la
    voie 3 y aurait mis) ; ici seule l'écriture de CET effet est annulée. Aucun porteur — la voie 3
    n'a aucun écrivain porté (ses 23 porteurs sont les summons Tyranides à trait
    `InstinctiveBehaviour`), donc les deux voies ne coexistent nulle part offline.

    On clé par id d'UNITÉ (== ECS), comme le reste du runner."""
    __slots__ = ("targets", "written_by")

    def __init__(self, targets: Optional[List[int]] = None, written_by=None):
        self.targets: List[int] = list(targets) if targets else []
        self.written_by = written_by

    def add(self, target_id: int) -> bool:
        """Ajoute une cible forcée (idempotent). Renvoie True si ajoutée (absente avant).
        Mirror de la voie 3 (`AddForcedAttackTargetBehaviour`) : écriture INCRÉMENTALE, non liée à un
        effet -> `written_by` reste ce qu'il est (aucun écrivain-effet ne coexiste, cf. l'écart nommé)."""
        if target_id in self.targets:
            return False
        self.targets.append(int(target_id))
        return True

    def remove(self, target_id: int) -> bool:
        """Retire une cible forcée. Renvoie True si présente."""
        if target_id in self.targets:
            self.targets.remove(target_id)
            return True
        return False

    def set_only(self, target_ids: List[int]) -> dict:
        """Remplace l'ensemble des cibles forcées (mirror du net `Remove(old−new) + Add(new−old)` de
        `InstinctiveBehaviour_UpdateTargetAbility.CreateBehaviour`). Renvoie {added, removed}."""
        new = [int(t) for t in (target_ids or [])]
        added = [t for t in new if t not in self.targets]
        removed = [t for t in self.targets if t not in new]
        self.targets = new
        return {"added": added, "removed": removed}

    def set_from_effect(self, effect, target_ids: List[int]) -> None:
        """`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal`, queue VERBATIM :

            comp = target.GetComponent<ForcedAttackTargetsComponent>();
            list = new List<int>();
            list.Add(<displayClass+0x18> = ABondEffect.BondedEntityId(effect));
            comp.<+0x50> = list;                     // REMPLACE la liste

        `effect` = l'instance qui écrit (cf. `written_by`)."""
        self.targets = [int(t) for t in (target_ids or [])]
        self.written_by = effect

    def clear(self) -> List[int]:
        """Vide la liste ET délie l'écrivain-effet. Renvoie ce qui a été retiré.

        Deux call-sites natifs distincts convergent ici : `TauntedEffect$$RevertInternal`
        (`comp.<+0x50> = new List<int>()`) et le `Remove` de tous les ids par
        `RemoveForcedAttackTargetBehaviour$$Execute`. Délier `written_by` est LOAD-BEARING pour le
        second : après un `RemoveAllForcedAttackTargets`, l'effet 27 peut être ENCORE actif et sa
        liste ne doit PAS repousser (le natif n'a pas de re-écriture — `ApplyInternal` ne se rejoue
        pas)."""
        removed = list(self.targets)
        self.targets = []
        self.written_by = None
        return removed

    def get(self) -> List[int]:
        """La liste EFFECTIVE. Rend `[]` si l'effet écrivain a disparu (mirror de `RevertInternal`,
        cf. `written_by`)."""
        if self.written_by is not None and getattr(self.written_by, "consumed", False):
            return []
        return list(self.targets)


class UnitFlagsComponent(Component):
    """`IdunBattle.Entities.Components.UnitFlagsComponent` IdunBattle.Entities.Components.UnitFlagsComponent$$.ctor — drapeaux booléens de l'unité
    (un `OrderedSet<int>` @+0x10 ; `Add`/`Remove`/`Has`/`TurnEnded`/`RemoveTurnFlags`). Valeurs = enum
    `IdunBattle.Entities.Enum.UnitFlag` (dump symbols.json) ; on porte le set d'ints (sémantique 1:1).

    Flags de TOUR (mission #139 — cycle posé/appliqué/reset, VAs) :
      • `TURN_FINISHED (3)` : le tour de l'UNITE est fini — posé par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute (déclenché après une ability qui « termine le tour », cf. abilities/handler.py) ; lu par
        `IdunBattle.Entities.Components.UnitFlagsComponent$$TurnEnded (= Contains(3)) via `VerifyUnitsTurnFinishedOperation.
        IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded et `IdunBattle.Core.Services.AttackQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility+0xec.
      • `ACTIVE_ABILITY_USED (2)` : une ability active a été utilisée ce tour — posé par
        `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution ; base du trigger DSL
        `HasOwnersActiveAbilityBeenUsed` (DSLFactory+0x110).
      • `ARRIVED_AT_FINAL_TILE (1)` : posé avec TURN_FINISHED par FinishUnitTurnOperation.
      • `NO_ACTION_AVAILABLE (4)` : « cette unité n'a plus d'action » — posé par
        `IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute+0xdc` ; ré-ouvert par
        le même corps sous `reverse` (`MarkUnitAsActionAvailable`, slot 0x77), que
        `VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` appelle quand l'unité regagne des
        options. Ses LECTEURS, recensés par scan binaire (`probe_287r1_no_action_available.py`),
        VENTILÉS par ce qu'ils en font — c'est la ventilation, pas la liste, qui dit si l'absence
        du flag rendait le port PERMISSIF :
          - DÉCISION moteur : `IdunBattle.Entities.UnitExtensions$$HasActionLeft` (lu par
            `IdunBattle.AI.OperationalDeciders.AnAiGroupOperator$$GetValidUnits` et
            `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` — les deux boucles qui
            TERMINENT grâce à lui), `IdunBattle.Core.Services.BattleQuery$$GetUsableUnitsFor` (×2,
            l'unité marquée n'est plus « utilisable »), et les trois
            `VerifyUnitsTurnFinishedOperation$${Execute, VerifyUnitTurnEnded,
            VerifyMachineTurnEnded}` (qui arbitrent pose/retrait).
          - STREAM seulement (aucune décision) : `IdunBattle.Operations.ReAddMachineOperation
            $$Execute` et `IdunBattle.Operations.ResurrectUnitOperation$$SendStreamEvents`, qui le
            publient sous `TagKey.UnitStats_ActionsAvailable` (`HasFlag(u, 4) ^ 1`) ; plus 11
            sites `View.FSM` via `HasActionLeft` (sélection à la souris).
        La POSE est portée depuis #287-r1 (queue de `FinishUnitTurnOperation`) ; le RETRAIT l'est
        depuis #287-r1-r1 — `VerifyUnitsTurnFinishedOperation` (`operations/turnflow.py`), branchée
        dans `Runner.apply` comme `RunPhase` invoque le slot 0x21. C'est la SEULE voie native de
        retrait, et elle est load-bearing : `RemoveTurnFlags(includeNoAction: 0)` CONSERVE ce flag
        au changement de tour.
      • `FLED (9)` : « a fui » (FleeOperation ; re-testé NOT HasFlag(self,9) par BattleFatigue).
      • `TURN_FINISHED_FORCED (27 = 0x1b)` : posé par `IdunBattle.Operations.FinishUnitTurnOperation
        $$Execute` sous le gate `isTerminated`. ⚠ Le nom natif est **`UnitFlag.TurnTerminated`** et
        il EST dans l'enum du build (`data/symbols/<build>/frida/enums.tsv` : `27=TurnTerminated`) —
        la mention « hors enum du dump » qui vivait ici était PÉRIMÉE. Le port garde l'alias
        descriptif (renommage = résidu déjà nommé, cf. `entities/unit_flag.py`), mais l'attribut
        pointe le membre : `TURN_FINISHED_FORCED = UnitFlag.TurnTerminated`.
        **DEUXIÈME poseur, identifié par #564-r4** : `IdunBattle.Operations.ResurrectUnitOperation
        $$Execute` y arrive, dans son bras `!takesImmediateTurn`, en appelant
        `processor.<slot 35 = FinishUnitTurn>(unit, isTerminated: true)` — le slot avait été lu
        comme `MarkUnitAsNoActionAvailable` (qui est le slot 118), d'où un flag « sans poseur ».
        (#943 — l'incise `dans son bras ...` a été DÉPLACÉE devant l'appel : collé à lui,
        `$$Execute` se retrouvait à moins de 40 caractères de `slot 35`, et `probe_477r24r1`
        appariait `(slot 35, Execute)` — le nom de l'OPÉRATION, pas celui du slot. Le couple juste,
        `slot 35 = FinishUnitTurn`, est écrit au même endroit et n'a pas bougé.)"""
    __slots__ = ("flags",)
    MOVED = UnitFlag.Moved                   # UnitFlag.Moved (posé par IdunBattle.Entities.UnitExtensions$$SetMovedFlag)
    ARRIVED_AT_FINAL_TILE = UnitFlag.ArrivedAtFinalTile   # UnitFlag.ArrivedAtFinalTile
    ACTIVE_ABILITY_USED = UnitFlag.ActiveAbilityUsed     # UnitFlag.ActiveAbilityUsed
    TURN_FINISHED = UnitFlag.TurnFinished           # UnitFlag.TurnFinished
    NO_ACTION_AVAILABLE = UnitFlag.NoActionAvailable     # UnitFlag.NoActionAvailable
    DEAD = UnitFlag.Dead        # UnitFlag.Dead (`enums.tsv` : `6=Dead`) — la PREMIERE branche de
                                # `IdunBattle.Entities.UnitExtensions$$IsAlive`
                                # (`UnitFlagsComponent$$Has(flags, 6)` -> faux immediat), lue AVANT
                                # l'appartenance au pool et AVANT les PV. Cf. `unit_extensions_is_alive`.
    FLED = UnitFlag.Fled                    # UnitFlag.Fled — « a fui » ce tour
    OVERKILLED = UnitFlag.Overkilled              # UnitFlag.Overkilled — pose par `IdunBattle.Operations.ApplyDamageOperation$$Execute`
                                # +0x17d5 (`if (result.didOverkill) UnitFlagsComponent.Add(target, 8)` — le
                                # `mov edx,8` precede immediatement le call, lu au desassemblage) ; RETIRE par
                                # `IdunBattle.Operations.ReviveUnitOperation$$Execute+0x7e0` (Remove(8)).
                                # Lu par `IdunBattleLogic.Entities.DSLTriggers$$HasFlag(unit, 8)` — volet
                                # OVERKILL de `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour`.
    TELEPORTED = UnitFlag.Teleported             # UnitFlag.Teleported
    AMBUSH_CONSUMED = UnitFlag.Resurrected        # flag 0xe (UnitPostAbility) — G3 : Ambush ré-suscité UNE fois ; posé par
                                # `ResurrectUnitOperation` (Add 0xe), testé `Not(HasFlag 0xe)` par les 2 triggers
                                # Ambush → résurrection one-shot. PERMANENT : survit à `remove_turn_flags` (pas un
                                # flag de tour), donc re-mourir ne re-déclenche PAS une 2e résurrection.
    PREVENT_OVERKILL = UnitFlag.PreventOverkill       # flag 0x13 (`UnitFlag.PreventOverkill`, enums.tsv) — pose par
                                # `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$
                                # ApplyInternal` (`UnitFlagsComponent.Add(u, 0x13)`) et retire par son
                                # `$$RevertInternal`. Lu par la surcharge d'INSTANCE de
                                # `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (`suppress`) :
                                # tant qu'il est pose, la cible ne peut pas etre overkillee (ultraTitus,
                                # i2 « the first time each turn that Titus is defeated he cannot be
                                # Overkilled »). Offline il est DERIVE de l'effet porteur — cf.
                                # `unit_prevents_overkill`.
    REMOVED = UnitFlag.Removed                # flag 0x1a (`UnitFlag.Removed`, enums.tsv) — l'unite a ete RETIREE du
                                # plateau (despawn, PAS une mort : ni PV touches ni flag `Dead`).
                                # Pose par `IdunBattle.Operations.RemoveUnitOperation$$Execute` juste
                                # AVANT sa publication d'`On(0x25 = UnitRemoved)`, et relu en TETE de
                                # la meme fonction comme gate anti-double-retrait
                                # (`IdunBattle.Entities.UnitExtensions$$HasFlag(entity, 0x1a)`).
                                # RETIRE par `IdunBattle.Operations.ResurrectUnitOperation$$Execute`
                                # (`Remove(6)/Remove(0xf)/Remove(8)/**Remove(0x1a)**/Remove(9)`).
                                # Cf. `runner/operations/remove_unit.py`.
    REVIVED = UnitFlag.Revived                # flag 0x14 (`UnitFlag.Revived`) — pose par
                                # `IdunBattle.Operations.ReviveUnitOperation$$Execute`
                                # (`Remove(0xf)` / `Remove(8)` / **`Add(0x14)`**), la rafale de
                                # flags du revive. AUCUN LECTEUR PORTE a ce jour (recense
                                # #462-r4e-o-r2-r1 : les occurrences de « Revived » dans `engine/`
                                # designent toutes l'EVENEMENT `EventTriggerType.UnitRevived = 45`,
                                # pas ce flag) -- il est porte pour que l'etat de flags du port
                                # egale celui du natif, mesure a l'appui (live `[0, 1, 20]` contre
                                # port `[0, 1]` avant #462-r4e-o-r2-r1).
    TURN_FINISHED_FORCED = UnitFlag.TurnTerminated   # flag 0x1b = `UnitFlag.TurnTerminated`
                                # (`FinishUnitTurnOperation` sous `isTerminated`) — nom du PORT,
                                # membre du BUILD ; cf. la docstring de classe.
    PREVENT_REVIVE = UnitFlag.PreventRevive   # flag 0xd (`enums.tsv` : `13=PreventRevive`) — posé
                                # par `IdunBattle.Operations.KillUnitOperation$$Execute`, dont le
                                # gate est LU :
                                #     bool preventRevive = options.<+0x45> ? true
                                #                                         : UnitExtensions.IsSteppable(killed);
                                #     if (preventRevive) flags.Add(0x0d);
                                # `KillUnitOperationOptions$$ForSteppable` écrit
                                # `*(undefined2*)(opts+0x44) = 0x101`, donc `+0x45 = 1` : **tout
                                # CRUSHÉ le reçoit sans condition**, et hors crush (`ForDefault`,
                                # tout à zéro) c'est `IsSteppable(killed)` qui décide.
                                # SON LECTEUR : `IdunBattle.Core.Services.BattleQuery$$CanBeRevived`,
                                # dont le 3e étage est `!HasFlag(target, 0xd)`.
                                # ⚠ LE RANG EST CE QUI COMPTE, et il est LU aux adresses de retour :
                                # `Add(0x0d)` tombe AVANT `On(1 = PreUnitDeath)`, donc avant le
                                # vecteur qui porte les revives. La justification qui vivait dans
                                # `revive_effect.py::can_be_revived` — « flag 0xd pas encore posé à
                                # l'instant de l'OnPreDeath » — était donc FAUSSE, et rendait le port
                                # PERMISSIF : il ressuscitait un crushé que le natif refuse
                                # (#462-r4b-r1-r1-r1-r1-c-r3-r1-r6, mesuré par
                                # `probe_462r4br6_revive_apres_crush.py`).
    UNTARGETABLE = UnitFlag.Untargetable      # flag 0x11 (`enums.tsv` : `17=Untargetable`) — le seul
                                # etat que lit `IdunBattle.Entities.UnitExtensions$$IsTargetable`
                                # (`= !HasFlag(unit, 0x11)`), donc la regle de ciblage
                                # `TargetIsTargetable` d'`ActiveAbilityOperation$$IsInvalidTarget`.
                                # POSE par `IdunBattle.Entities.Effects.Common.UntargetableEffect
                                # $$ApplyInternal` -- et la pose est GARDEE, relue verbatim sur
                                # `t6dpr4k06g` :
                                #     if (!this.<vslot +0x728 IsUntargetableEnabled>(owner, target,
                                #                                                    effect)) return;
                                #     target.GetComponent<UnitFlagsComponent>().Add(0x11);
                                # RETIRE par `$$RevertInternal`, qui est un tail call NU vers
                                # `UnitFlagsComponent$$Remove(0x11)` -- aucun gate, et **aucun
                                # comptage de references** : deux effets untargetable simultanes
                                # partagent UN seul element d'`OrderedSet`, donc le premier retrait
                                # rend l'unite ciblable alors que le second effet vit encore. Quirk
                                # NATIF, porte tel quel (#433-r5 le nomme).
                                # TROIS AUTRES POSEURS, hors de tout effet (#433-r3-r2-r1-r1) :
                                # `ResurrectUnitOperation$$Execute` et `AddUnitOperation$$Execute`
                                # encadrent chacune leur propre corps d'un `Add(0x11)` ... `Remove(0x11)`
                                # -- fenetre TRANSITOIRE intra-operation. Cf. `operations/resurrect.py`.
                                # LES POSEURS PORTES : `AddEffectOperation._apply_untargetable_flag` /
                                # `remove_effects.remove_effect_instance` (#433-r3-r2-r1). Avant eux le
                                # flag n'etait pose par AUCUN chemin, ce qui rendait
                                # `abilities/targeting.py::is_targetable` -- et donc `TargetIsTargetable`,
                                # `HatefulAssault`, `SavageKiller`, `MV71` -- constamment vrais.

    def __init__(self, flags=None):
        self.flags = set(int(f) for f in flags) if flags else set()

    def add(self, flag: int) -> None:
        self.flags.add(int(flag))

    def remove(self, flag: int) -> None:
        self.flags.discard(int(flag))

    def has(self, flag: int) -> bool:
        return int(flag) in self.flags

    def turn_ended(self) -> bool:
        """`IdunBattle.Entities.Components.UnitFlagsComponent$$TurnEnded = Contains(TurnFinished=3). Lu par le turn-flow natif
        (IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded) et par l'AttackQuery pour exclure les unités finies."""
        return self.TURN_FINISHED in self.flags

    def remove_turn_flags(self, include_no_action: bool = False, new_activation: bool = True) -> set:
        """`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags : retire TOUJOURS {ActiveAbilityUsed(2),
        TurnFinished(3), 27} ; + {NoActionAvailable(4)} si `include_no_action` (param_3 natif) ;
        + {Moved(0), Teleported(12), ArrivedAtFinalTile(1)} si `new_activation` (param_4 natif).
        `IdunBattle.Operations.StartTurnOperation$$Execute l'appelle (0, 1) pour chaque unité du joueur entrant.

        RETOUR = les flags EFFECTIVEMENT retirés (ceux qui étaient présents). Le natif rend une STRUCT
        de 7 bools (`IdunBattle.Entities.Components.UnitFlagsComponent$$Remove rend « était présent » ; offsets +5=Moved(0), +0=Teleported(0xc),
        +6=ArrivedAtFinalTile(1), +1=NoActionAvailable(4), +2=ActiveAbilityUsed(2), +3=TurnFinished(3),
        +4=TurnFinishedForced(0x1b)) — struct consommée par `IdunBattle.Operations.ComputerActionOperation$$SetUnitTurnsFlags qui les RE-POSE une à une (restauration exacte du turn-state après une action AI
        forcée, cf. `runner/operations/summon_ai.py`). Le port rend le SET des flags retirés (la struct
        n'est qu'un bitset « était présent » ; l'ordre des `Add` de la restauration est indifférent).
        Les appelants historiques ignorent le retour (aucun changement de comportement)."""
        removed: set = set()

        def _rm(f):
            if f in self.flags:
                self.flags.discard(f)
                removed.add(f)

        if new_activation:
            for f in (self.MOVED, self.TELEPORTED, self.ARRIVED_AT_FINAL_TILE):
                _rm(f)
        if include_no_action:
            _rm(self.NO_ACTION_AVAILABLE)
        for f in (self.ACTIVE_ABILITY_USED, self.TURN_FINISHED, self.TURN_FINISHED_FORCED):
            _rm(f)
        return removed


class StatsComponent(Component):
    """Bloc de stats de combat RÉSOLUES de l'unité (Attack, FixedArmor, ExtraHits,
    ExtraPierce, crit/block, AbilityVariablesMultiplier, niveau d'ability…) + config
    d'arme de l'attaque normale. Porte le `UnitContext` validé (`engine.entities`),
    assemblé depuis `combatSnapshot` (stats one-shot) + gameconfig.

    C'est la SOURCE de la plage de tirage de dégât (`base = stat Attack`, spread BC),
    qui rend le runner autonome (calcul de la plage sans relecture live). Natif : les
    stats sont stockées sur l'unité (StatComponents) et lues par `BattleQuery`."""
    __slots__ = ("ctx",)

    def __init__(self, ctx: "UnitContext"):
        self.ctx = ctx


class TriggeredAbilityState:
    """Une entrée du `TriggeredAbilityComponent` (une ability/trigger de l'unité). Offsets natifs
    (RE `IdunBattle.Entities.Components.TriggeredAbilityComponent$$MarkAsTriggered / `IdunBattle.Entities.Components.TriggeredAbilityComponent$$GetTimesTriggeredThisPhase) :
    `has_triggered`@+0x2c (bool, `HasBeenTriggered`), `total`@+0x30 (compteur cumulé toutes phases),
    `times_this_phase`@+0x34 (compteur de la phase courante ; lu par le cap `<51`, remis à 0 par
    `ResetPhase`). (Le natif porte aussi la clé/config-id @+0x10.. et le niveau @+0x38 ; ici on ne modèle
    que les 3 compteurs — le seul état lu par le gate de trigger.)"""
    __slots__ = ("has_triggered", "total", "times_this_phase")

    def __init__(self):
        self.has_triggered = False
        self.total = 0
        self.times_this_phase = 0


class TriggeredAbilityComponent(Component):
    """`IdunBattle.Entities.Components.TriggeredAbilityComponent` IdunBattle.Entities.Components.TriggeredAbilityComponent$$.ctor — registre par-unité des
    ability-triggers, avec leur compteur de déclenchements. Native = `KeyedCollection` @+0x18 indexée par
    l'ability-type (config-id) ; chaque entrée porte `has_triggered`/`total`/`times_this_phase`
    (cf. `TriggeredAbilityState`).

    RÔLE : le natif GATE chaque déclenchement de trigger à `GetTimesTriggeredThisPhase(key) < 0x33`
    (=51) dans `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger (cap anti-emballement d'une
    PHASE = une activation d'unité) ; `MarkAsTriggered` incrémente au fire ; `ResetPhase` (via
    `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase, à la fin de chaque activation) remet
    `times_this_phase` à 0 (PAS `total`). Sans ce cap, une chaîne de triggers générateurs d'attaque
    (splash Psyker qui re-déclenche le splash Psyker via le vecteur after-hit) récurserait sans borne.

    Peuplé au build de l'unité pour CHAQUE ability (natif `UnitFactory.Add*Abilities` → `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd). Offline : clé = un identifiant stable d'ability-type (cf. Slice 2). Population +
    gate + reset = slices #142/#143/#144."""
    __slots__ = ("entries",)

    def __init__(self, entries: Optional[Dict[Hashable, "TriggeredAbilityState"]] = None):
        self.entries: Dict[Hashable, TriggeredAbilityState] = entries if entries is not None else {}

    def try_add(self, key: Hashable) -> bool:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd : enregistre l'ability `key` si absente (compteurs à 0). No-op (renvoie
        False) si déjà présente ; True si ajoutée."""
        if key in self.entries:
            return False
        self.entries[key] = TriggeredAbilityState()
        return True

    def get_times_triggered_this_phase(self, key: Hashable) -> int:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$GetTimesTriggeredThisPhase : compteur de la phase courante pour `key` ; **0 si
        la clé est absente** (TryGetValue échoue → 0)."""
        e = self.entries.get(key)
        return e.times_this_phase if e is not None else 0

    def mark_as_triggered(self, key: Hashable) -> None:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$MarkAsTriggered : `has_triggered=True`, `total += 1`, `times_this_phase += 1`.
        **No-op si la clé est absente** (le natif TryGetValue échoue et `return`)."""
        e = self.entries.get(key)
        if e is None:
            return
        e.has_triggered = True
        e.total += 1
        e.times_this_phase += 1

    def has_been_triggered(self, key: Hashable) -> bool:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$HasBeenTriggered : True si l'ability a déjà été déclenchée (any phase). False si
        clé absente."""
        e = self.entries.get(key)
        return bool(e.has_triggered) if e is not None else False

    def reset_phase(self) -> None:
        """`IdunBattle.Entities.Components.TriggeredAbilityComponent$$ResetPhase : remet `times_this_phase` à 0 pour TOUTES les entrées (le `total` et
        `has_triggered` sont conservés). Appelé au boundary d'activation (`EndPhaseOperation`)."""
        for e in self.entries.values():
            e.times_this_phase = 0


class ActiveAbility:
    """`IdunBattle.Entities.Components.ActiveAbility` -- UNE entree d'ability active de l'unite. Champs
    portes = ceux que le canal live expose (`readAbilityState`, `frida/hooks/features/ai-step/
    internals.ts`, offsets resolus PAR NOM sur la classe native) :

        CanStillBeUsed         @0x28  -> `can_still_be_used`   (l'ability a-t-elle encore une charge ?)
        RemainingCooldownTurns @0x2c  -> `remaining_cooldown`  (Nullable<int> ; None = pas de cooldown)
        IsDisabled             @0x35  -> `disabled`
        AmmoCost               @0x38  -> `ammo_cost`           (Nullable<int> ; None = pas de cout)
        HasEnoughAmmo          @0x40  -> `has_ammo`
        AbilityName            @0x44  -> `ability_type`        (ActiveAbilityType concret)
        _abilityState          @0x4c  -> `level` / `multiplier` (AbilityState PER-ABILITY, #100)

    `is_in_cooldown` = `IdunBattle.Entities.Components.ActiveAbility$$get_IsInCooldown` =
    `RemainingCooldownTurns.HasValue && Value > 0`."""
    __slots__ = ("ability_type", "kind", "can_still_be_used", "remaining_cooldown", "disabled",
                 "ammo_cost", "has_ammo", "level", "multiplier")

    def __init__(self, ability_type: int, kind: str = "active", can_still_be_used: bool = True,
                 remaining_cooldown=None, disabled: bool = False, level=None, multiplier=None,
                 ammo_cost=None, has_ammo: bool = True):
        self.ability_type = int(ability_type)
        self.kind = kind
        self.can_still_be_used = bool(can_still_be_used)
        self.remaining_cooldown = remaining_cooldown
        self.disabled = bool(disabled)
        self.ammo_cost = ammo_cost
        self.has_ammo = bool(has_ammo)
        self.level, self.multiplier = level, multiplier

    def is_in_cooldown(self) -> bool:
        """`IdunBattle.Entities.Components.ActiveAbility$$get_IsInCooldown` : `HasValue && Value > 0`."""
        return self.remaining_cooldown is not None and int(self.remaining_cooldown) > 0

    def can_currently_be_used(self) -> bool:
        """`IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` -- la propriete
        COMPOSITE que le generateur d'action natif teste (`<GenerateActions>d__7`), a NE PAS confondre
        avec `CanStillBeUsed`@0x28 (le seul champ que le canal live nomme `usable`) :

            CanStillBeUsed(@0x28) && !IsDisabled(@0x35)
              && (!RemainingCooldownTurns(@0x2c).HasValue || Value < 1)
              && (!AmmoCost(@0x38).HasValue || HasEnoughAmmo(@0x40))

        Le 4e terme (MUNITIONS) n'a de mordant que sur les MACHINES OF WAR : leurs abilities portent
        un `munitionsCost` et le stock vit dans `BC.Player.Players[].MachineOfWarAmmo` (0 dans le seed
        BC). Mesure live (runner MoW `adeptExorcist`, session 4) : `1187` = `usable:true, hasAmmo:false`
        -> le natif ne la propose PAS et caste `1188` a la place. Sans ce terme, le port proposerait
        1187.

        CONFIRME le 2026-07-29 (`docs/rl/case-mow-ammo-gauge.md`) -- et le gate est bien DECISION-ONLY :
        a `MachineOfWarAmmo = 0`, un cast force par `applyAction` s'execute quand meme et pose ses
        effets (`SpendAmmoOperation$$Execute` echoue silencieusement). Le stock vit dans
        `PlayerComponent+0x6c`, il est pose UNE fois par `AddPlayerOperation$$Execute` depuis la BC et
        **aucune operation native ne l'incremente** : il ne remonte jamais en cours de bataille. Pour
        un scenario qui a besoin de munitions, patcher `MachineOfWarAmmo` dans un seed BC ecrit hors
        `data/`. ⚠ `usable` = `CanStillBeUsed@0x28` SEUL : il vaut `true` alors meme que l'ability est
        en cooldown initial -- ne jamais s'en servir comme composite."""
        if not self.can_still_be_used or self.disabled:
            return False
        if self.remaining_cooldown is not None and int(self.remaining_cooldown) >= 1:
            return False
        if self.ammo_cost is not None and not self.has_ammo:
            return False
        return True

    def __repr__(self) -> str:                                        # pragma: no cover
        return (f"ActiveAbility({self.ability_type}, {self.kind}, usable={self.can_still_be_used}, "
                f"cd={self.remaining_cooldown}, ammo={self.ammo_cost}/{self.has_ammo})")


class ActiveAbilitiesComponent(Component):
    """`IdunBattle.Entities.Components.ActiveAbilityComponent` -- la COLLECTION d'abilities actives de
    l'unite (`KeyedCollection<ActiveAbilityType, ActiveAbility>` @+0x20, iteree par
    `IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` et par
    `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute`).

    SEEDE depuis `decisionView.units[].abilities` (canal `unitAbilityTypes` + `readAbilityState`, qui
    lit litteralement ces champs sur l'objet natif) -- les entrees `kind == "normal"` (l'attaque
    normale, poussee depuis `NormalAttackType` SANS objet `ActiveAbility`) sont EXCLUES : le natif les
    exclut aussi de la boucle de reset (`ActiveAbility.IsRegularAttack`). Le canal n'est peuple que si
    l'appelant demande `allAbilities: true` -> composant ABSENT sinon (degradation fidele et VISIBLE :
    les consommateurs rendent None plutot qu'un faux verdict, cf. `entity_can_have_active_ability_reset`)."""
    __slots__ = ("abilities",)

    def __init__(self, abilities=None):
        self.abilities: List["ActiveAbility"] = list(abilities or [])

    def get(self, ability_type: int) -> Optional["ActiveAbility"]:
        return next((a for a in self.abilities if a.ability_type == int(ability_type)), None)


class ActiveAbilityModificationsComponent(Component):
    """`IdunBattle.Entities.Components.ActiveAbilityModificationsComponent` IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$.ctor (.ctor) — registre
    par-unite des MODIFICATIONS de constantes/variables d'ability apportees par des sources TIERCES
    (`Dictionary<AbilityVarOrConst, ModificationConfig>` @+0x10).

      • `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Add(key, delta) : TryGetValue(key) -> `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent.ModificationConfig$$Add(delta)
        (`value += delta` puis CLAMP `if (cap.HasValue && cap < value) value = cap` -- `cap` = le
        `Nullable<int>` @+4 de la struct, JAMAIS pose par les sources lues dans ce build -> None) ;
        cle absente -> cree une entree ZERO (`set_Item(key, default)`) puis re-appelle `Add`.
      • `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Get(key) : `TryGetValue(key) ? config.value : 0` -- **0 quand la cle est absente**.

    SOURCE NATIVE unique lue dans ce build : `IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute` (= `Core.Services.OperationProcessor$$AddUnitActiveAbilityModification), appelee par
    `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$ApplyInternal (+ `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$RevertInternal, meme appel en
    `-value`) -- le passif de `astraSmnKell` qui buffe le SupremeCommander de son parent Creed.

    La chaine de POSE est desormais portee de bout en bout (#95-RESTE2) : `SwornProtector` (passif de
    `astraCreed`) fait apparaitre Kell -> `ListenUpMaggotsAbility` (`On(AbilityInit)`) pose l'effet
    0x426 sur Kell -> `ListenUpMaggotsEffect.ApplyInternal` ecrit les DEUX modifications sur
    `Parent(Kell)` = Creed. Le dict n'est donc plus condamne a rester vide.

    GROUND TRUTH LIVE (runner MC1_67, Creed attaque par `necroSpyder`, session 78) : Kell apparait
    VIVANT en portant `ListenUpMaggotsEffect`, et le cast SupremeCommander suivant spawne **3** gardes
    (= `nrOfSummons 2` + modification `+1`). L'ancienne note « meme avec Kell vivant le natif summon 2
    gardes » etait FAUSSE (les probes d'alors n'avaient pas de Kell survivant/effet applique).

    Les deux semantiques de CONSOMMATION restent distinctes (additive pour `nrOfSummons`, OVERRIDE si
    non nulle pour `range`, cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour)."""
    __slots__ = ("modifications",)

    def __init__(self, modifications=None):
        self.modifications: dict = dict(modifications or {})

    def add(self, key, delta: int, cap=None) -> int:
        """`IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Add + `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent.ModificationConfig$$Add."""
        value = int(self.modifications.get(key, 0)) + int(delta)
        if cap is not None and int(cap) < value:      # clamp `Nullable<int>` @+4 (jamais pose in-build)
            value = int(cap)
        self.modifications[key] = value
        return value

    def get(self, key) -> int:
        """`IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Get : valeur de la modification, 0 si absente."""
        return int(self.modifications.get(key, 0))


class PersistentDataComponent(Component):
    """`IdunBattle.Entities.Components.PersistentDataComponent` (.IdunBattle.Entities.Components.PersistentDataComponent$$.ctor) — sac de donnees
    persistantes PAR ENTITE, indexe par une cle composite. Natif = `Dictionary<key, value>` @+0x10 :
      • `PersistData<T>(key, value)` IdunBattle.Entities.Components.PersistentDataComponent$$PersistDatau003C__Il2CppFullySharedGenericStructTypeu003E / `TryGetPersistData<T>(key, out)` IdunBattle.Entities.Components.PersistentDataComponent$$TryGetPersistDatau003C__Il2CppFullySharedGenericStructTypeu003E ;
      • `IdunBattle.Entities.Components.PersistentDataComponent$$ClearPersistentData(key) = `Dictionary.Remove(key)` ;
      • `IdunBattle.Entities.Components.PersistentDataComponent$$ClearAllPersistentData() (appele par `IdunBattle.Operations.ResurrectUnitOperation$$ResetPersistentData+0x91 et `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$ExecuteClearAll+0x1d).

    Cote DSL, les noeuds qui l'adressent sont `DSLFactory.SetPersistentData` (IdunBattleLogic.Entities.DSLBehaviors$$SetPersistentData et overloads),
    `IdunBattleLogic.Entities.DSLTriggers$$IsPersistentData` (= `AmountIsEqualOrGreater(GetPersistentDataFormula(key,
    entity, dataKey) IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate, Direct(0)@0xb8)` -> « la cle est posee ») et
    `DSLFactory.ClearPersistentData` (IdunBattleLogic.Entities.DSLBehaviors$$ClearPersistentData/IdunBattleLogic.Entities.DSLBehaviors$$ClearPersistentData).

    Le port modelise le sac comme un dict `{cle: valeur}` sur l'unite. La CLE offline = le tuple
    `(abilityOrEffect, dataKey)` (mirror de la cle composite native : l'`AbilityOrEffect` passe a
    `SetPersistentData` + le `Get(<champ statique de l'ability>)` qui nomme la donnee).

    Consommateur porte : `LetTheGalaxyBurnAbility` (`runner/operations/triggers/loki/
    let_the_galaxy_burn.py`) — flag INTRA-ATTAQUE arme au `On(PreAttack=5)` et efface par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` en fin d'attaque."""
    __slots__ = ("data",)

    def __init__(self, data=None):
        self.data: dict = dict(data or {})

    def persist_data(self, key, value=1) -> None:
        """`PersistentDataComponent.PersistData<T>` IdunBattle.Entities.Components.PersistentDataComponent$$PersistDatau003C__Il2CppFullySharedGenericStructTypeu003E : pose/ecrase `key -> value`."""
        self.data[key] = value

    def try_get_persist_data(self, key):
        """`TryGetPersistData<T>` IdunBattle.Entities.Components.PersistentDataComponent$$TryGetPersistDatau003C__Il2CppFullySharedGenericStructTypeu003E : la valeur, ou None si la cle est absente."""
        return self.data.get(key)

    def clear_persistent_data(self, key) -> None:
        """`IdunBattle.Entities.Components.PersistentDataComponent$$ClearPersistentData(key) = `Dictionary.Remove(key)` (no-op si absente)."""
        self.data.pop(key, None)

    def clear_all_persistent_data(self, ability_or_effect=None) -> None:
        """Les DEUX overloads natifs de `ClearAllPersistentData` :
          * SANS argument (`IdunBattle.Entities.Components.PersistentDataComponent$$ClearAllPersistentData`,
            appele par `IdunBattle.Operations.ResurrectUnitOperation$$ResetPersistentData+0x91`) = vide
            TOUT le sac (resurrection) ;
          * AVEC un `abilityId` (l'autre overload, appele par
            `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$ExecuteClearAll`) =
            `Dictionary.Remove(abilityId)` sur le dict @+0x10.

        ⚠ MODELE : le sac natif est un dict a DEUX niveaux (`abilityId -> (dataKey -> valeur)`), d'ou
        un `Remove(abilityId)` qui emporte TOUTES les dataKeys de cette ability -- c'est ce que dit
        « ClearAll ». Le port APLATIT en cle composite `(abilityOrEffect, dataKey)` ; l'overload a un
        argument balaie donc toutes les cles dont le PREMIER membre vaut `ability_or_effect`, ce qui
        est le meme observable."""
        if ability_or_effect is None:
            self.data.clear()
            return
        aid = int(ability_or_effect)
        for k in [k for k in self.data
                  if isinstance(k, tuple) and k and k[0] == aid]:
            self.data.pop(k, None)

    def sum_ability_data(self, ability_or_effect, excluded_keys=None) -> int:
        """`IdunBattle.Entities.Triggers.GetAllPersistentDataCombined$$SumAbilityData(component,
        abilityId)` -- MIRROR du decompile (#965) :

            dict = component.<+0x10>.TryGetValue(abilityId)      # absent -> 0
            sum  = 0
            foreach kv in dict:
                if kv.Value n'est pas un `int` BOXE : continue    # test de type explicite
                if this.<+0x30 excludedKeys> != null
                   and excludedKeys.Any(k => String.op_Equality(k, kv.Key)) : continue
                sum += unbox<int>(kv.Value)
            return sum

        TROIS traits LUS, qui ne se devinent pas :
          * c'est une **SOMME**, pas un max ni un compte -- `local_res10[0] = (int)uVar8 + iVar1` ;
          * seules les valeurs **ENTIERES** comptent : le natif teste la classe de l'objet boxe
            (`*local_a0 == DAT_183651158`) et **saute** toute valeur d'un autre type. Cote port,
            la variante LISTE range ses `list` dans le MEME sac -> on les saute pareil ;
          * l'exclusion compare les cles par `System.String$$op_Equality`, et un `excludedKeys`
            NUL n'exclut rien (le `if (this+0x30 != 0)` garde l'appel a `Any`).

        Le natif somme sur DEUX composants (deux `GetComponent<T>` distincts, chacun garde par le
        `HasValue` de sa moitie de l'`AbilityOrEffect` union) et ADDITIONNE les deux. Le port n'a
        qu'UN `PersistentDataComponent` a cle composite aplatie, donc un seul balayage -- meme
        observable, cf. la note MODELE de `clear_all_persistent_data` ci-dessus.

        CONSOMMATEUR PORTE : `...RefusalToBeOutdoneAbility$$GetCurrentExtraDmg`, ou l'exclusion
        porte sur la cle COMPTEUR (sans elle, le nombre d'amis Chaos serait somme dans l'Outrage)."""
        aid = int(ability_or_effect)
        excl = tuple(excluded_keys or ())
        total = 0
        for k, v in self.data.items():
            if not (isinstance(k, tuple) and k and k[0] == aid):
                continue
            # `if (v is boxed int)` -- une `list` (variante LISTE) ou un `str` est SAUTEE.
            # `bool` est un `int` en Python mais jamais un `Int32` boxe cote natif.
            if isinstance(v, bool) or not isinstance(v, int):
                continue
            if len(k) > 1 and any(k[1] == e for e in excl):    # `String.op_Equality`
                continue
            total += int(v)
        return total

    # --- Variante LISTE (#354) : `PersistDataList<T>` / `TryGetPersistDataList<T>` -----------------
    # Le natif range SOUS LA MEME cle composite un `List<T>` au lieu d'un scalaire ; les deux familles
    # de methodes coexistent sur le MEME `Dictionary` @+0x10. Le port les distingue par le TYPE de la
    # valeur (list vs scalaire), pas par un second sac -- mirror direct.
    def persist_data_list(self, key, values) -> None:
        """`IdunBattle.Entities.Components.PersistentDataComponent$$PersistDataListu003C__Il2CppFullySharedGenericStructTypeu003E`
        : pose/ecrase `key -> List<T>`. Le natif range la MEME instance de liste qu'il vient de muter."""
        self.data[key] = list(values)

    def try_get_persist_data_list(self, key):
        """`IdunBattle.Entities.Components.PersistentDataComponent$$TryGetPersistDataListu003C__Il2CppFullySharedGenericStructTypeu003E`
        : la liste, ou None si la cle est absente. Les TROIS consommateurs natifs
        (`AddToPersistentDataListBehaviour$$Execute`, `IsInPersistentDataListTrigger$$ShouldTrigger`,
        `EntitiesFromPersistentDataListSelector$$Select`) enchainent tous sur `?? new List<T>()`."""
        v = self.data.get(key)
        return v if isinstance(v, list) else None


def persistent_data_list(entity, key) -> list:
    """`TryGetPersistDataList<T>(key) ?? new List<T>()` — la liste persistante rangee sous `key` sur
    `entity`. Entite/composant/cle absents -> `[]` (le natif materialise lui aussi une liste NEUVE
    dans ce cas, cf. les trois consommateurs). Lu par l'accesseur `ctx.persistent_data_list`."""
    if entity is None:
        return []
    comp = entity.get_component(PersistentDataComponent)
    if comp is None:
        return []
    return list(comp.try_get_persist_data_list(key) or ())


def persistent_data(entity, key):
    """`TryGetPersistData<T>(key)` -- la valeur SCALAIRE rangee sous `key`, `None` si absente.
    Pendant scalaire de `persistent_data_list`, lu par l'accesseur `ctx.persistent_data` (noeud
    `GetPersistentData`). Entite/composant/cle absents -> `None` ; c'est l'appelant qui decide de
    la valeur par defaut (`GetPersistentDataFormula$$Calculate` rend l'`out` par defaut = 0)."""
    if entity is None:
        return None
    comp = entity.get_component(PersistentDataComponent)
    return comp.try_get_persist_data(key) if comp is not None else None


def save_previous_position(state, unit_id, previous_tiles) -> bool:
    """`IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition(unit, previousPosition)`
    -- FOYER UNIQUE de l'ecriture de `UnitComponent.previous_position`. Mirror du decompile :

        if (previousPosition == null) throw
        if (previousPosition.Count < 1) return          <- gate LU : une empreinte VIDE n'ecrit rien
        pc.<+0x88> = pc.<+0x98> = new Nullable(new UnitPositionId(previousPosition))

    `previous_tiles` = la liste des coordonnees `(col,row)` que l'unite occupait AVANT (son
    empreinte, un seul element en mono-hex). Rend « l'ecriture a eu lieu ».

    #1082 : les DEUX slots sont ecrits, avec la MEME valeur, comme le decompile le montre. Ils ne
    divergent qu'aux remises a zero (cf. `PositionComponent`)."""
    if unit_id is None or not previous_tiles:
        return False                                    # `Count < 1` -> aucune ecriture
    e = state.get_entity(int(unit_id))
    if e is None:
        return False
    tiles = [(int(c), int(r)) for c, r in previous_tiles]
    # `<+0x88>` ET `<+0x98>` -- MEME valeur, MEMES instructions natives, deux copies cote port.
    # TOUS DEUX sur le `UnitComponent` parce qu'ils doivent SURVIVRE au retrait de plateau, comme
    # le `MovementComponent` natif qui les porte (#1082 pour `+0x98`, #448-r7 pour `+0x88` -- cf.
    # la docstring de `PositionComponent`, ou l'ecart de collapse est motive).
    uc = e.get_component(UnitComponent)
    if uc is None:
        return False
    uc.previous_position = tiles                        # `<+0x88>`
    uc.previous_position_this_turn = list(tiles)        # `<+0x98>`
    return True


def previous_tiles(entity) -> list:
    """`IdunBattle.Entities.Selectors.PreviousTileSelector$$Select`, remis en C# :

        comp = this.unitSelector.SelectSingle(entities)?.GetComponent<PositionComponent>()
        if (comp == null) return <throw>
        nullable = comp.<+0x88>
        return nullable.HasValue ? UnitPositionIdExtensions.ToTileList(nullable.Value, state)
                                 : new List<TileEntity>()

    Rend les coordonnees `(col,row)` de l'empreinte PRECEDENTE, `[]` si le `Nullable` est vide.
    Lu par l'accesseur `ctx.previous_tiles`.

    ⚠ #448-r7 -- LE CHAMP EST SUR LE `UnitComponent`, PAS SUR LA `PositionComponent`. Le natif le
    porte sur le `MovementComponent`, que le retrait de plateau ne touche pas ; cote port la
    `PositionComponent` est SUPPRIMEE par `set_unit_feet(uid, [])`, si bien que ce selecteur rendait
    `[]` sur toute unite sortie du plateau la ou le natif rend la tuile QUITTEE."""
    if entity is None:
        return []
    uc = entity.get_component(UnitComponent)
    # Composant absent -> `[]`. Le natif LEVE dans ce cas ; la degradation est celle qui existait
    # deja ici (elle est nommee dans `selectors/tiles.py::PreviousTile`), et elle est INCHANGEE par
    # le demenagement : seule la classe de composant consultee change.
    return list(uc.previous_position or ()) if uc is not None else []


def persistent_data_keys(entity) -> frozenset:
    """Cles persistantes POSEES sur l'entite (mirror de l'ensemble des cles du dict natif) — lu par le
    noeud `IsPersistentData` cote EFFET (`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`), qui
    n'a acces qu'a l'etat, pas au composant. Entite/composant absent -> frozenset() (= sac vide)."""
    if entity is None:
        return frozenset()
    comp = entity.get_component(PersistentDataComponent)
    return frozenset(comp.data.keys()) if comp is not None else frozenset()


def get_ability_stat_modification(entity, key) -> int:
    """`IdunBattle.Entities.UnitExtensions$$GetAbilityStatModification =
    `unit.GetComponent<ActiveAbilityModificationsComponent>().Get(key)`.

    `key` = un `AbilityVarOrConst` (natif : `AbilityVarOrConst.op_Implicit(Nullable<AbilityConstant>)`
    replie la constante en une cle 4 octets -- ex. `0x10` = nrOfSummons, `0x16` = range). Le port passe
    directement l'index de constante (int), MEME domaine de cle que `add`.

    Unite sans composant (cas NOMINAL offline : aucune source de modification portee) -> 0, identique au
    `Get` natif sur un dict vide. Consommateurs natifs (xrefs EXHAUSTIVES du build gqfc5mff6c) : les DEUX
    call-sites de `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour (IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x16b cle 0x10 nrOfSummons,
    IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x24a cle 0x16 range) -- AUCUN autre appelant."""
    if entity is None:
        return 0
    comp = entity.get_component(ActiveAbilityModificationsComponent)
    return comp.get(key) if comp is not None else 0


# --- EMPREINTE MULTI-HEX (`UnitComponent._feet` + `UnitFootComponent`) --------------------------- #
# Mirror des accesseurs natifs de l'empreinte. Ils sont la SEULE porte d'entree du port sur « quelles
# tuiles cette entite occupe » ; la geometrie qui les consomme (distance min-sur-les-pieds, validite
# d'une liste de pieds, positions de mouvement) vit dans `engine.services.movement_query`.

def get_unit_feet(state, unit_id) -> List[tuple]:
    """`IdunBattle.Entities.UnitExtensions$$GetUnitFeet(entity, state)` (== la liste que rend
    `IdunBattle.Entities.EntityExtensions$$GetTiles` / `$$IterateTiles`) : les TUILES des pieds de
    l'unite, DANS L'ORDRE des pieds.

    Natif : `GetUnitFeetIds` iterate `UnitComponent.GetFeetEnumerator()` (= `_feet` @+0x78) et rend
    l'id de chaque pied ; `GetUnitFeet` les resout en entites. `IterateTiles` fait le meme parcours
    et rend la TUILE de chaque pied (`UnitFootComponent.TileId`), en sautant les pieds sans tuile.

    Port :
      * `UnitComponent.feet` materialise (unite MULTI-HEX) -> la liste telle quelle ;
      * `feet is None` (cas NOMINAL, un pied) -> `[(col,row)]` du `PositionComponent` ;
      * ni l'un ni l'autre (entite sans position : MACHINE OF WAR hors plateau, entite non-unite)
        -> `[]`, exactement comme le natif (`GetUnitFeetIds` rend une liste vide si l'entite n'est
        pas une unite, et une MoW porte un `MachineComponent`, pas un `UnitComponent`).

    Accepte un id d'entite OU une `Entity` (le natif prend l'`IEntity`)."""
    e = state.get_entity(int(unit_id)) if isinstance(unit_id, int) else unit_id
    if e is None:
        return []
    uc = e.get_component(UnitComponent)
    feet = getattr(uc, "feet", None) if uc is not None else None
    if feet is not None:
        return list(feet)
    pc = e.get_component(PositionComponent)
    return [] if pc is None else [(pc.col, pc.row)]


def get_feet_count(state, unit_id) -> int:
    """`IdunBattle.Entities.UnitExtensions$$GetFeetCount(entity, state)` =
    `GetUnitFeetIds(entity, state).Count`. **C'est un compte COURANT** (le nombre de pieds
    reellement poses), pas une propriete de config : aucun champ de gameconfig ne porte la taille
    d'une unite -- elle est fixee au spawn par la liste de tuiles passee a `AddUnitOperation`.

    Lecteurs natifs (xrefs) : `MovementQuery$$GetMovablePositionsFor`,
    `TargetingQuery$$GetInvalidTargetReason` / `$$GetInvalidCasterReason` (les regles
    `CasterHas1/3/7Tiles` et `TargetHas1/3/7Tiles`), `BattleQuery$$IsTileInRangeOfAnyAbility`,
    `BasePlaybook$$GetEligibleTargetsEntities`, `DislikeStartingTilesUtility`,
    `ResurrectUnitOperation`, `TheQuickeningAbility$$GetDynamicInvalidTargetReason`."""
    return len(get_unit_feet(state, unit_id))


def get_main_tile(state, unit_id) -> Optional[tuple]:
    """`IdunBattle.Entities.EntityExtensions$$GetMainTileId(entity, state)` -> la tuile, mirror :

        if (entity == null) return 0;
        if (entity.TryGetComponent<UnitFootComponent>(out foot)) return foot.TileId;   // un PIED
        if (entity.TryGetComponent<UnitComponent>(out unit)) {
            if (unit._feet == null || unit._feet.Count == 0) return 0;
            return GetMainTileId(state.GetEntity(unit._feet[0]), state);               // recursion
        }
        if (EntityExtensions.IsTile(entity)) return entity.Id;                          // une TUILE
        return 0;

    => **la main tile est la tuile du PREMIER pied**. Le port lit `feet[0]` s'il existe, sinon la
    `PositionComponent` (identiques par construction, cf. `set_unit_feet`). `None` = pas de tuile
    (l'entite n'est pas sur le plateau)."""
    feet = get_unit_feet(state, unit_id)
    return feet[0] if feet else None


def set_unit_feet(state, unit_id: int, feet) -> List[tuple]:
    """Pose l'empreinte COMPLETE d'une unite — mirror de la boucle de pose de
    `IdunBattle.Operations.AddUnitOperation$$Execute` :

        unitComponent.ClearFeet();
        foreach (tile in tiles) {
            foot = Blueprints.UnitFoot(nextId); state.AddEntity(foot);
            unitComponent.AddFoot(foot.Id);
            foot.GetComponent<UnitFootComponent>().UnitId = unit.Id;
        }

    ECRIVAIN UNIQUE de l'empreinte cote port : il pose `UnitComponent.feet` **et** recale la
    `PositionComponent` sur `feet[0]` (la main tile), pour que les deux representations ne puissent
    pas diverger. Une liste d'UN element repose `feet = None` -> l'unite redevient exactement une
    unite mono-tuile (aucun etat multi-hex residuel apres, p.ex., un retrait de pieds).
    Renvoie l'empreinte posee.

    LISTE VIDE = « l'unite N'OCCUPE PLUS AUCUNE TUILE » (#366-r1). C'est le seul cas ou l'ecrivain
    RETIRE la `PositionComponent` au lieu de la recaler, et il materialise `feet = []` (surtout PAS
    `None`, qui veut dire « un pied, a la `PositionComponent` »). Mirror du collapse de
    `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` : le natif met a zero le `TileId`
    de CHAQUE `UnitFootComponent`, et `IdunBattle.Entities.EntityExtensions$$IterateTiles` saute les
    pieds sans tuile -> `GetUnitPosition` (= `$$GetTiles`) rend une liste VIDE. Cote port, la chaine
    `pied -> tuile` etant COLLAPSEE en un `(col,row)`, « pied sans tuile » n'a d'autre representation
    que l'absence du couple. L'etat « unite sans position » n'est PAS inedit : le chemin de
    CHARGEMENT le produit deja (`snapshot._load_units` ne pose la `PositionComponent` que si
    `pos.col is not None`, et `decisionView` rend `pos = null` pour l'unite sous terre) ; les 148
    call-sites `get_component(PositionComponent)` du moteur gardent tous le `None` (balayage AST du
    2026-08-01). Seul l'ECRIVAIN manquait."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return []
    tiles = [(int(t[0]), int(t[1])) for t in (feet or [])]
    uc = e.get_component(UnitComponent)
    if uc is None:
        uc = e.add_component(UnitComponent(visual_id=None, alive=True))
    uc.clear_feet()
    for t in tiles:
        uc.add_foot(t)
    if not tiles:
        # AUCUNE tuile : `feet = []` MATERIALISE (get_unit_feet rend [] sans retomber sur la
        # PositionComponent) + retrait de la position. Les deux vont ENSEMBLE : laisser l'un des
        # deux ferait diverger `get_unit_feet` et `PositionComponent`, exactement ce que cet
        # ecrivain unique existe pour empecher.
        # ⚠ `+0x98` N'EST PAS PERDU ICI (#1082) -- il vit sur le `UnitComponent`, pas sur celui-ci.
        # C'est ce qui rend atteignable le second bras de `movement._movement_start_position`
        # (unite hors plateau qui VIENT de quitter une tuile ce tour -> vrai chemin de VOL au lieu
        # de la branche degeneree `[endTile, endTile]`). Cf. `previous_position_this_turn`.
        e.remove_component(PositionComponent)
        return []
    if len(uc.feet) <= 1:
        uc.feet = None                       # un pied = cas NOMINAL, pas de liste materialisee
    pc = e.get_component(PositionComponent)
    if pc is None:
        e.add_component(PositionComponent(tiles[0][0], tiles[0][1]))
    else:
        pc.col, pc.row = tiles[0]            # main tile = feet[0] (`GetMainTileId`)
    return get_unit_feet(state, unit_id)


# --- Lien PARENT / ENFANTS (`ChildComponent.ParentId` / `ParentComponent.ChildrenIds`) ----------- #
def parent_of(state, unit_id):
    """`IdunBattle.Entities.UnitExtensions$$GetParent(unit, state, root = false)` (lu par
    `IdunBattle.Entities.Selectors.ParentSelector$$Select`) : l'entite PARENTE DIRECTE (le summoner),
    ou None. Le natif y lit `ChildComponent.ParentId` puis `state.GetEntity(...)` ; il ne remonte
    a la RACINE que si son 3e argument `root` est vrai, ce que ce port ne demande jamais.
    Le port lit `UnitComponent.parent_id` (pose au spawn, ou seede du live par
    `snapshot._load_unit_parent`)."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    pid = getattr(uc, "parent_id", None) if uc is not None else None
    return state.get_entity(pid) if pid is not None else None


def children_of(state, unit_id, alive_only: bool = True) -> list:
    """Enfants (summons) de `unit_id` — mirror de `ParentComponent.ChildrenIds` (la `List` @+0x10 que
    construit `IdunBattle.Entities.Components.ParentComponent$$.ctor`), DERIVE ici par
    balayage de `state.entities` (le port ne materialise que le lien enfant -> parent). `alive_only`
    reflete `IdunBattle.Entities.Selectors.AllAliveMachinesSelector` (le selecteur `DSLFactory.Children`
    ne rend que des unites VIVANTES) ; le gate `IsFriendlyKell` du playbook SupremeCommander, lui,
    accepte les MORTS (`baseSelector + AllDeadUnits()`) -> `alive_only=False`."""
    out = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or getattr(uc, "parent_id", None) != unit_id:
            continue
        if alive_only and not uc.alive:
            continue
        out.append(int(eid))
    return out


# --- Predicat de LIVENESS d'unite (#70) -------------------------------------------------------- #
# Mirror des primitives natives lues par le gate acteur-mort de `ActiveAbilityOperation.
# IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` : `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster))
# return 0;` — un caster MORT rend l'ability (attaque normale INCLUSE, #139) un NO-OP complet (0 tirage
# RNG, aucun effet, aucun flag) AVANT toute execution. Ces helpers portent la semantique de mort utilisee
# par CE gate (cf. engine/runner/operations/damage.py::visit_AttackUnitMessage et
# abilities/handler.py::visit_ActiveAbilityMessage).

def unit_is_alive(entity) -> bool:
    """`IdunBattle.Entities.Components.HealthComponent$$IsAlive` — MIRROR du decompile, TROIS branches
    et non une :

        if (RemainingValue@+0x18 >= 1)          return true;    // PV courants > 0 -> VIVANT
        if (get_CurrentMaximumValue() > 0)      return false;   // PV <= 0 mais un MAX -> MORT
        if (<+0x1c> is Nullable<int> HasValue)  return Value != -1;
        return true;                                            // PV <= 0 ET max <= 0 -> VIVANT

    Le champ `+0x1c` EST `minimal_health` (le plancher de PV du HP-floor, cf. la docstring de
    `HealthComponent`) : le port a donc de quoi ecrire ce mirror EXACTEMENT, pas par approximation.

    ⚠ **LA BRANCHE `hp <= 0 && max <= 0` EST EXERCEE, et la version precedente de cette docstring
    ecrivait le contraire** (<< non exercee : une unite a plancher de PV a hp>=1 >>). MESURE
    (#589-r1-r1-r2-r1-r8, `C3_14` seed 777) : `genesSmnDecoy`, un DECOY spawne au deploiement, porte
    `combatSnapshot.stats.health = 0` **et** `healthMax = 0`, avec `decisionView.alive = true`. Le
    natif la compte comme unite presente (elle allume
    `AmuletOfTheVoidwyrm_CritDamageReduction` sur un porteur adjacent, compteur natif LU DU DEGAT =
    1) ; le port, avec `hp >= 1` seul, la declarait MORTE et la retirait de tout selecteur
    d'occupation. Une unite SANS SANTE n'est pas un cadavre.

    hp INCONNU (None, ex. replay charge sans observeBattle) -> vivant (retro-compat : on ne gate
    jamais sur un etat de PV non capte). **MAXIMUM inconnu -> on garde MORT** : c'est le
    comportement d'avant ce mirror, conserve deliberement plutot que d'etendre la branche
    << sans sante >> a tout ce qui n'a pas publie son maximum. Degradation NOMMEE, pas un mirror."""
    if entity is None:
        return True
    hc = entity.get_component(HealthComponent)
    if hc is None or hc.hp is None:
        return True
    if hc.hp >= 1:
        return True                          # `RemainingValue >= 1`
    if hc.hp_max is None or hc.hp_max > 0:
        return False                         # `get_CurrentMaximumValue() > 0` (ou non capte)
    mh = getattr(hc, "minimal_health", None)
    if mh is not None:
        return int(mh) != -1                 # `Nullable<int>@+0x1c` : `Value != -1`
    return True                              # PV <= 0 ET maximum <= 0 : unite SANS SANTE


def unit_extensions_is_alive(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsAlive(entity, state)` — MIRROR du decompile, et ce
    n'est PAS `HealthComponent$$IsAlive` : le natif teste TROIS choses, dans cet ordre.

        unit = UnitExtensions.GetUnit(entity, state);
        if (unit == null)                                    // ni unite, ni tuile occupee, ni pied
            return EntityExtensions.GetEntityType(entity) == 6;   // EntityType.Machine
        if (UnitFlagsComponent.Has(unit.UnitFlags, 6))       return false;   // UnitFlag.Dead
        pool = state.GetPool(0);                             // EntityPool.AliveUnits
        if (!pool.Contains(unit))                            return false;
        return HealthComponent.IsAlive(unit.Health);

    Les deux constantes sont LUES dans `data/symbols/<build>/frida/enums.tsv`, pas devinees :
    `IdunBattle.Entities.Enum.UnitFlag` -> `6=Dead` ; `IdunBattle.Entities.Enum.EntityPool` ->
    `0=AliveUnits` (et `1=DefeatedUnits`, `8=AllUnits`, que lisent respectivement
    `IdunBattle.Core.Services.BattleQuery$$GetAllDeadUnits` et `$$GetAllUnits` par le MEME
    accesseur) ; `IdunBattle.Entities.Enum.EntityType` -> `6=Machine`.

    LES TROIS BRANCHES, ET LEUR PORTEUR OFFLINE :
      * `UnitFlag.Dead` -> `UnitFlagsComponent.has(DEAD)`, seede par `snapshot._load_unit_flags` ;
      * pool `AliveUnits` -> **`UnitComponent.alive`**. Ce n'est pas une approximation : le canal
        live qui seede ce champ EST cette fonction native -- `decisionView` publie
        `alive: invokeBool(isAliveMi, [e, statePtr])` (`frida/hooks/features/ai-step/projection.ts`),
        `isAliveMi` etant `UnitExtensions$$IsAlive`. Offline, les operations portees l'entretiennent
        comme le natif entretient le pool : `AttackDamageOperation`/`_fire_death_if_killed` et
        `MoveUnitOperation.KillSteppableUnits` posent `False`, `RemoveUnitOperation` aussi (etape 8),
        `ResurrectUnitOperation`/`ReviveUnitOperation`/les spawns posent `True` -- exactement les
        operations qui, en natif, appellent les slots `AddToPools`/`RemoveFromPools` du state ;
      * `HealthComponent.IsAlive` -> `unit_is_alive` ci-dessus (hp >= 1), inchange.

    LA BRANCHE MACHINE est portee telle quelle : `GetUnit` ne resout QUE les unites, les tuiles
    occupees et les pieds (`IdunBattle.Entities.UnitExtensions$$GetUnit`, 3 surcharges lues) -- une
    MACHINE OF WAR n'en est aucune, donc le natif retombe sur `EntityType == Machine` et la declare
    TOUJOURS vivante. Cote port, une MoW porte un `MachineComponent` et **aucun** `HealthComponent`
    (cf. `snapshot._load_machines`), donc ce retour anticipe preserve a l'identique le comportement
    d'avant cette fonction.

    POURQUOI CETTE FONCTION EXISTE (#429-r1-r3-r1-r2, divergence MESUREE). Le port n'avait AUCUN
    mirror de ce service : ses lecteurs appelaient `unit_is_alive` = `HealthComponent$$IsAlive`
    seul. Une unite ENFUIE (`UnitFlag.Fled`, posee par
    `IdunBattle.Operations.FleeOperation$$Execute`, seul ecrivain du flag) garde ses **PV PLEINS**
    et sort du pool `AliveUnits` : le natif la voit MORTE-AU-SENS-LARGE, le port la voyait vivante
    et INTACTE. Mesure du 2026-08-05 (`probe_429r1r3r1_message_gate_perimeter.py --volet fled`,
    seed 777 / board MC1_67) : cible enfuie a `hp = 1000/1000`, natif **0 evenement**, port
    **10 375 degats**.

    LECTEURS ROUTES PAR ELLE (les deux sites ou le decompile appelle litteralement ce service) :
      * `unit_is_dead` -- `IdunBattle.Entities.UnitExtensions$$IsDead` = `!IsAlive(u, state) &&
        !HasFlag(u, 9 Fled)` ;
      * `operations/active_ability.is_dead_unit_and_not_allowed_by_ability` --
        `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`, dont le
        2e gate est `if (UnitExtensions.IsAlive(target, state)) return false;`.
    `is_alive_and_not_fled` n'en fait PAS partie, et c'est LU : `IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled`
    appelle `HealthComponent$$IsDead` directement, jamais ce service."""
    if entity is None:
        return False                        # `GetUnit(null)` = null, puis `entity != null` faux
    if entity.get_component(MachineComponent) is not None:
        return True                         # `EntityType.Machine` (6) -> toujours vivante
    fl = entity.get_component(UnitFlagsComponent)
    if fl is not None and fl.has(UnitFlagsComponent.DEAD):
        return False                        # `UnitFlagsComponent.Has(flags, 6 Dead)`
    uc = entity.get_component(UnitComponent)
    if uc is not None and not uc.alive:
        return False                        # `state.GetPool(EntityPool.AliveUnits).Contains(unit)`
    return unit_is_alive(entity)            # `HealthComponent.IsAlive`


# --- Predicat de DEPLACABILITE (#498-r2) ------------------------------------------------------- #
# Les TROIS traits que `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` refuse, dans l'ordre du
# decompile : `BaseUnitComponent$$HasTrait(u, 0x11)`, `(u, 0x3)`, `(u, 0x3f9)`. Les trois ordinaux
# sont qualifies contre `data/symbols/<build>/frida/enums.tsv`, enum
# `IdunBattle.Entities.Enum.UnitTrait` (`3=Hulking, 17=Immovable, 1017=BigTarget`).
# ⚠ PUBLIC depuis #498-r4, et pour une raison MESUREE : ce tuple existait en TROIS exemplaires
# (`playbook/loki_custom.py::MortisRoundPlaybook._NOT_DISPLACEABLE` et
# `playbook/noncomparable/it_itches.py::_NOT_DISPLACEABLE`), c'est-a-dire exactement le gisement que
# #498-r3 a ferme cote RUNNER (« six copies libres de diverger, et elles avaient diverge »). Les
# deux miroirs de la face DECISION ne peuvent PAS appeler `unit_extensions_is_displaceable` (leur
# substrat est un `dict` de `decisionView`, pas une `Entity`), mais ils peuvent partager CETTE
# liste -- c'est la seule des cinq conditions qui MORDE aujourd'hui.
NOT_DISPLACEABLE_TRAITS = (UnitTrait.Immovable,   # 0x11
                           UnitTrait.Hulking,     # 0x3
                           UnitTrait.BigTarget)   # 0x3f9


def unit_extensions_is_displaceable(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsDisplaceable(unit)` — MIRROR du decompile, relu
    VERBATIM sur le build courant :

        if (unit == null)                                       return false;
        if (GetEntityType(unit) != EntityType.Unit)             return false;   // iface, slot 1
        if (GetBaseUnitComponent(unit) != null
            && BaseUnitComponent.HasTrait(unit, 0x11))          return false;   // Immovable
        if (GetBaseUnitComponent(unit) != null
            && BaseUnitComponent.HasTrait(unit, 0x3))           return false;   // Hulking
        big = GetBaseUnitComponent(unit) != null
              && BaseUnitComponent.HasTrait(unit, 0x3f9);                       // BigTarget
        return !UnitExtensions.HasFlag(unit, 0x19) && !big;              // UnitFlag.Undisplaceable

    ⚠ **Le natif ne teste AUCUNE LIVENESS ici.** Le gate `alive` que portaient les sites appelants
    n'est PAS dans cette fonction : il reste chez EUX, nomme, parce qu'il n'a pas le meme statut
    (cf. la docstring de `DisplaceUnitOperation` cote `operations/displace.py`).

    `EntityType` : les valeurs sont LUES dans `frida/enums.tsv`
    (`IdunBattle.Entities.Enum.EntityType` -> `1=Unit`, `6=Machine`). Cote port, le discriminant est
    `MachineComponent` — MEME choix que `unit_extensions_is_alive` ci-dessus, qui traite deja la
    branche `EntityType.Machine` par ce composant (une MoW est materialisee par `_load_machines`
    avec `MachineComponent`, et sans `PositionComponent`).

    Le substrat de traits est `entity_trait_names` (le FOYER : kit gameconfig + traits ACCORDES en
    bataille + pseudo-trait d'alliance), pas `sc.ctx.traits` brut — c'est ce que lit
    `BaseUnitComponent$$HasTrait`.

    SIX LECTEURS PORTES (les six sites qui, natifs, passent par cette fonction) :
    `DisplaceUnitOperation$$Execute` (tete, commune aux 7 cases du switch — donc pull, push, direct
    ET switch-position), `DamagePrediction$$GetKnockback`, et les deux gates de
    `UnstoppableMomentumReworkedAbility` (`$$Push` et le `CanBeDisplaced` de `$$SuppressOrStun`)."""
    if entity is None:
        return False
    if entity.get_component(MachineComponent) is not None:
        return False                        # `EntityType.Machine` (6) != `EntityType.Unit` (1)
    sc = entity.get_component(StatsComponent)
    uc = entity.get_component(UnitComponent)
    traits = entity_trait_names(sc.ctx if sc is not None else None,
                                getattr(uc, "visual_id", None) if uc is not None else None)
    if has_any_trait(traits, NOT_DISPLACEABLE_TRAITS):
        return False
    fl = entity.get_component(UnitFlagsComponent)
    # `UnitExtensions$$HasFlag(unit, 0x19)` -> `UnitFlagsComponent$$Has`. Le flag est POSE et RETIRE
    # par la charge de 1152 (`AddFlag`/`RemoveFlag` autour de `ExecuteBehaviour`), donc il est bien
    # ECRIT cote port (`abilities/loki/momentum.py::_set_charge_flag`).
    if fl is not None and fl.has(UnitFlag.Undisplaceable):
        return False
    return True


def register_defeated_unit(state, killer_id, killed_id, in_melee=None) -> bool:
    """#951 -- mirror d'`IdunBattle.Operations.KillUnitOperation$$Execute+0x8b9`, avec SES deux
    gates, lus a l'ENCODAGE (le pseudo-C les noyait dans la cascade de null-checks) :

        +0x833   if (!EntityExtensions.IsActor(killer))        goto skip;
        +0x845   if ( UnitExtensions.IsSteppable(killed))      goto skip;
        +0x88a   var stats = killer.GetComponent<ActorStatisticsComponent>();
        +0x89e   var id    = killed.Id;
        +0x8b9   if (stats != null) stats.RegisterDefeatedUnit(id, inMelee: options.inMelee);

    PLACE : entre `KilledThisTurn = true` (@+0x828) et `On(PreUnitDeath_2)` (@+0x9xx), donc AVANT
    les cinq publications d'evenement de la mort. CONSEQUENCE PORTEE, et elle DECIDE d'un resultat :
    un consommateur d'`On(UnitDefeated = 0x36)` -- `TrophyTakerAbility` -- compte la victime
    COURANTE dans son total. Poser cet appel apres l'evenement rendrait `n` au lieu de `n+1`.

    `in_melee` (#951-r1, FERME) : le troisieme argument natif. Il n'est PAS a deviner -- le decompile
    montre que `KillUnitOperation$$Execute` ecrit `local_378[0]` dans `UnitComponent+0x178`
    (`DefeatedByMeleeAttack`, sur la VICTIME) puis passe **ce meme `local_378[0]`** en `inMelee`.
    Les deux faces d'un unique booleen, et sa SOURCE est desormais lue de bout en bout :

        local_378[0] = (rangeType.GetValueOrDefault() == Melee(1)) & rangeType.HasValue
        rangeType    = KillUnitOptions+0x3c
                     <- IdunBattle.Core.MatchState$$AddDeath(..., AttackRangeType)
                     <- IdunBattle.Operations.RecordKillOperation$$Execute
                     <- KillUnitContext+0x38, pose par IdunBattle.Operations.ApplyDamageOperation$$
                        Execute via le slot 4 d'IBattleQuery (`GetAttackRangeType`)

    Les DEUX faces du port l'alimentent : SIMULATION (`damage.py::_kill_unit_operation`, qui
    calcule le `AttackRangeType` au foyer de degat) et SEEDING (`snapshot._load_death_sources`, qui
    lit `decisionView.units[].defeatedByMelee`). TRI-ETAT ici : `None` = l'appelant ne l'a pas
    mesure, et l'enregistrement tombe alors dans `@+0xb0` comme le fait le natif pour un `inMelee`
    faux -- c'est la branche par DEFAUT du decompile (`if ((char)inMelee == '\\0')`), et c'est aussi
    ce que le natif fait pour les voies dont les `KillUnitOptions` laissent `+0x3c` a zero
    (`$$ForSteppable` du crush, `$$ForDefault` de la feuille DSL `Kill`).

    Rend `True` si l'enregistrement a eu lieu."""
    if killer_id is None or killed_id is None:
        return False
    killer = state.get_entity(int(killer_id))
    killed = state.get_entity(int(killed_id))
    if killer is None or killed is None:
        return False
    # `EntityExtensions$$IsActor` -- cote port, une entite de `state.entities` porteuse d'un
    # `UnitComponent` EST un acteur (les tuiles vivent dans `state.board`/`EffectsState`, jamais
    # dans `state.entities`, cf. `abilities/behaviours/context._tile_entity`).
    if killer.get_component(UnitComponent) is None:
        return False
    if unit_extensions_is_steppable(killed):
        return False
    kc = killer.get_component(UnitComponent)
    # `*(int *)(this + 0xa0) += 1` -- AVANT le branchement, donc inconditionnel.
    kc.total_defeated_units += 1
    if in_melee:
        kc.defeated_units_melee.append(int(killed_id))
    else:
        kc.defeated_units_other.append(int(killed_id))
    return True


def defeated_units_union(uc) -> list:
    """L'UNION `@+0xa8` PUIS `@+0xb0`, dans l'ordre exact ou
    `IdunBattle.Entities.Selectors.UnitsDefeatedBySelector$$Select` les concatene
    (`AddUnits(result, <+0xa8>)` puis `AddUnits(result, <+0xb0>)`). Foyer UNIQUE de la lecture
    jointe des deux listes -- l'ordre COMPTE, le natif rendant un `OrderedSet` (ordre d'insertion).
    Rend une liste vide sur un composant absent, jamais `None`."""
    if uc is None:
        return []
    return list(uc.defeated_units_melee) + list(uc.defeated_units_other)


def death_killer_id(uc):
    """#1033-r3 -- QUI a tue cette unite, en composant les DEUX sources du port. Foyer unique.

    Le natif n'en a qu'une : `DamageSource.get_KillerId` sur le `Nullable<DamageSource>`
    @`UnitComponent+0x108`. Le port en a deux parce que ses deux regimes ne publient pas la meme
    chose -- la SIMULATION grave la `DamageSource` entiere (`death_source`, trois composantes),
    tandis qu'un etat CHARGE n'a du canal que le KillerId (`decisionView.units[].killerId`, seul
    champ que `readUnitDeathMeta` expose de la `DamageSource`).

    Ordre de priorite : `death_source[0]` d'abord (mesure la plus riche, gravee par le run), puis
    `death_killer_id` (le seed). TRI-ETAT preserve : `None` = tueur non imputable, ce qui recouvre
    exactement le zero du natif (`UnitKillerSelector$$Select` ne retient un tueur que si
    `KillerId != 0`, et le capteur rend `null` des que `kid <= 0`)."""
    if uc is None:
        return None
    ds = getattr(uc, "death_source", None)
    if ds is not None and len(ds) >= 1 and ds[0] is not None:
        return int(ds[0])
    k = getattr(uc, "death_killer_id", None)
    return None if k is None else int(k)


def units_defeated_by(state, unit_id) -> list:
    """#951 -- `IdunBattle.Entities.Selectors.UnitsDefeatedBySelector$$Select` restreint a UNE unite
    source : `AddUnits(result, stats.<+0xa8>)` puis `AddUnits(result, stats.<+0xb0>)`, chaque id
    etant RESOLU en entite et **ignore s'il ne resout pas** (`if (entity != null) result.Add(...)`).
    Le resultat natif est un `OrderedSet` : ordre d'insertion, sans doublon.

    Rend les IDS (la resolution en dicts d'unite est faite par le selecteur DSL, qui seul connait
    l'univers `ctx.units`). Liste VIDE si l'unite n'existe pas -- jamais `None` : le natif rend un
    `OrderedSet` vide, et un `None` remonterait en `TypeError` chez `Count`."""
    if unit_id is None:
        return []
    e = state.get_entity(int(unit_id))
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return []
    vus, out = set(), []
    for i in defeated_units_union(uc):             # `OrderedSet` : ordre d'insertion, sans doublon
        if i not in vus:
            vus.add(i)
            out.append(int(i))
    return out


def unit_extensions_is_steppable(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsSteppable(unit)` = `BaseUnitComponent$$HasTrait(unit,
    0x1b = Steppable)`. MEME substrat de traits qu'`unit_extensions_is_displaceable` ci-dessus
    (`entity_trait_names` : kit gameconfig + traits ACCORDES en bataille), pour la meme raison.

    Foyer de la BRANCHE ECRASEMENT du push, LUE en tete d'`IdunBattle.Operations.
    DisplaceUnitOperation$$Execute`, juste apres `IsDisplaceable` et AVANT le switch de direction :

        if (UnitExtensions.IsSteppable(target)) {
            processor.KillUnit(caster, target, KillUnitOperationOptions.ForSteppable());
            return;                        // <- l'unite STEPPABLE poussee est TUEE, jamais deplacee
        }

    Le meme predicat est relu plus bas sur l'OCCUPANT de la destination (`content.IsFilled() &&
    IsSteppable(occupant)` -> `KillUnit(target, occupant, ForSteppable())`), d'ou le foyer partage.

    Il existe deja un mirror TILE-domain de ce predicat, `runner/abilities/targeting.py::
    has_steppable_unit`, qui resout une TUILE en son occupant (`GetUnit`) puis teste le meme trait ;
    il vit la-bas parce que son argument natif y transite. Celui-ci prend l'ENTITE directement --
    c'est ce dont `operations/` a besoin, et importer `abilities/` depuis `operations/` fermerait un
    cycle."""
    if entity is None:
        return False
    sc = entity.get_component(StatsComponent)
    uc = entity.get_component(UnitComponent)
    traits = entity_trait_names(sc.ctx if sc is not None else None,
                                getattr(uc, "visual_id", None) if uc is not None else None)
    return has_any_trait(traits, (UnitTrait.Steppable,))


def unit_extensions_can_move(state, unit_id: int) -> Optional[bool]:
    """`IdunBattle.Entities.UnitExtensions$$CanMove(unit)` — MIRROR du decompile :

        if (unit == null)                                            return false
        if (EntityExtensions.GetEntityType(unit) != EntityType.Unit) return false
        base = UnitExtensions.GetBaseUnitComponent(unit)
        if (base != null && base.HasTrait(UnitTrait.Stationary))     return false
        if (!unit.TryGetComponent<MovementComponent>(out mc))        return false
        return mc.IsAllowedToMove()

    LES QUATRE ETAGES SONT LUS SUR LE SUBSTRAT DU RUNNER (#1015-r1).

    `IdunBattle.Entities.Components.MovementComponent$$IsAllowedToMove` est
    `this.<+0x50 : Dictionary>.Count == 0` -- un registre de BLOQUEURS par instance d'effet. Ce
    dictionnaire a exactement DEUX ecrivains, tous deux nommes et tous deux LUS --

        IdunBattle.Entities.Effects.BlockUnitMovementEffect$$ApplyInternal
            mc = target.GetComponent<MovementComponent>() ; mc.<+0x50>.Add(effect.Id, effect.Id)
        IdunBattle.Entities.Effects.BlockUnitMovementEffect$$RevertInternal
            mc.<+0x50>.Remove(effect.Id)

    (et leurs jumeaux `...BlockUnitMovementBondEffect$$ApplyInternal/RevertInternal`, qui ecrivent
    le MEME champ, avec en plus l'`OwnerComponent.CurrentPlayerEntityId` dans la CLE). L'entree
    existe donc exactement tant qu'une instance de block-movement est ACTIVE sur la cible -- le
    seul chemin de pose/retrait etant `RefreshEffectsOperation$$ActivateEffect` /
    `$$DeactivateEffect`. Le port n'a pas de dictionnaire materialise : il pose la MEME question a
    `EffectsState.active_effects`, qui reevalue `is_active` (= la `CreateActiveCondition`) a chaque
    lecture.

    ⚠ LE REGISTRE EST COMPLET DEPUIS #1015-r2, ET SON EXHAUSTIVITE EST MESUREE SUR DEUX AXES.
    `BLOCK_UNIT_MOVEMENT_EFFECT_TYPES` (`entities/effects/loki/instinctive_behaviour.py`) inscrit
    les QUATRE : `25 Taunted_BlockMovement`, `91 Vines_BlockMovement`,
    `1016 PrecisionShot_BlockMovement`, `1235 InstinctiveBehaviour_BlockMovement`.
      * EN AVAL, le `MethodInfo*` du `Dictionary<..>$$Add` de `MovementComponent+0x50` n'a que DEUX
        lecteurs dans TOUT le binaire (`BlockUnitMovementBondEffect$$ApplyInternal` et
        `BlockUnitMovementEffect$$ApplyInternal`) : aucun troisieme ecrivain n'existe.
      * EN AMONT, `probe_1015r2_effectsdb_slot_de_classe.py` lit le SLOT `Il2CppClass*` des 607
        fabriques d'`EffectsDatabase$$InitializeEffects` : `1235` est un groupe SINGLETON, et
        `25`/`91`/`1016` forment un groupe de taille EXACTEMENT 3.
    L'ecart PERMISSIF que ce paragraphe decrivait (le port croyait ces porteurs MOBILES, donc
    `has_tiles_to_move_to` sur-estimait et `NoActionAvailable` etait retire trop souvent) est donc
    FERME. Confronte live sur le taunt : `probe_1015r2_taunt_block_movement.py` (natif 17 tuiles ->
    0, port `True` -> `False`, temoin non taunte mobile des deux cotes).
    Reste ouvert et de MEME direction : le residu nomme par
    `entities/selectors/tiles.MovableTilesInRange`.

    ⚠ **IL VIT ICI, ET PAS DANS `operations/turnflow.py`, PARCE QUE LA MESURE LE DEMANDE**
    (#590-r6-r2). `turnflow` importe `..abilities.handler` en tete, donc tout lecteur situe sous
    `abilities/` devait passer par un import DIFFERE -- `attempted_possession` en portait un, classe
    PORTEUSE, avec sa mesure. Le levier 1 de la doctrine (DEPLACER le code partage) est ici
    disponible et MESURE : `import engine.runner.components` dans un process FRAIS ne fait atterrir
    dans `sys.modules` ni `abilities.handler`, ni `abilities.loki.attempted_possession`, ni
    `operations.turnflow` -- l'arete disparait, elle n'est pas contournee. Les deux dependances non
    triviales (`is_machine_of_war`, `unit_state_for_effects`) vivaient DEJA ici.
    ⚠ **AUCUN RE-EXPORT N'EST LAISSE DANS `turnflow`** : ce serait un baril de plus (#485-r1-r1),
    donc les quatre lecteurs visent ce foyer-ci par son chemin PLEIN.

    Rend `False` (certain), `True` (aux quatre etages lus), ou `None` si l'entite n'est pas lisible.
    """
    e = state.get_entity(int(unit_id))
    if e is None:
        return False                      # `unit == null` -> false
    uc = e.get_component(UnitComponent)
    if uc is None:
        return None                       # entite sans `UnitComponent` : type d'entite non lisible
    # `GetEntityType(unit) != EntityType.Unit(1)` — une MACHINE OF WAR (`EntityType.Machine` = 6) ne
    # passe JAMAIS ce gate. C'est ce qui rend `HasTilesToMoveTo` faux pour elle cote natif, et c'est
    # aussi pourquoi `VerifyMachineTurnEnded` ne l'appelle pas du tout.
    if is_machine_of_war(e):
        return False
    sc = e.get_component(StatsComponent)
    traits = (getattr(sc.ctx, "traits", None) if (sc is not None and getattr(sc, "ctx", None)
                                                  is not None) else None)
    if traits is not None and has_trait(traits, UnitTrait.Stationary):
        return False                      # `BaseUnitComponent$$HasTrait(unit, UnitTrait.Stationary)`
    # 4e etage : `MovementComponent$$IsAllowedToMove` = `<+0x50>.Count == 0` (cf. la docstring).
    # Le port pose la MEME question a la liste des effets ACTIFS du porteur.
    return not _has_active_movement_blocker(state, int(unit_id))


def _has_active_movement_blocker(state, unit_id: int) -> bool:
    """`MovementComponent+0x50` non vide -- c.-a-d. « une instance de block-movement est ACTIVE sur
    l'unite ». Les deux ecrivains natifs du dictionnaire (`BlockUnitMovementEffect$$ApplyInternal`
    et `...BondEffect$$ApplyInternal`) y mettent l'id de l'effet a son ACTIVATION et l'en retirent
    a sa DESACTIVATION ; l'appartenance est donc exactement cette question-la.

    `state.effects` absent -> `False` (aucun bloqueur mesurable). `active_effects` reevalue la
    `CreateActiveCondition` de chaque instance -- pour `1235`, l'arbre de
    `entities/effects/loki/instinctive_behaviour.py`.

    L'import de la table est HISSE en tete de module (forme B) : le differe qu'il portait dans
    `turnflow` etait GRATUIT ici, et c'est MESURE -- `import
    engine.entities.effects.loki.instinctive_behaviour` dans un process frais ne fait PAS atterrir
    `engine.runner.components` dans `sys.modules`."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return False
    wanted = set(int(t) for t in _instinctive.BLOCK_UNIT_MOVEMENT_EFFECT_TYPES)
    if not wanted:
        return False
    ustate = unit_state_for_effects(state, int(unit_id))
    return any(int(getattr(e, "effect_type", -1)) in wanted
               for e in eff.active_effects(int(unit_id), ustate))


# Effets dont la presence (owner OU target) fait qu'un move est un TELEPORT (cf. `set_moved_flag`) :
# TeleportStrike_TeleportingIn(0x40b=1035)/TeleportStrike_Moving(0x40c=1036) et
# FearOfTheUnseen_TeleportingIn(0x4d6=1238)/FearOfTheUnseen_Moving(0x4d9=1241).
# #270-r1-r1 : membres nommes -- les quatre noms etaient deja au site. L'ORDRE est celui des
# disjonctions du decompile (`IsTeleporting`), donc le tuple reste un tuple.
_TELEPORT_MOVE_EFFECTS = (EffectType.TeleportStrike_Moving,           # 0x40c = 1036
                          EffectType.TeleportStrike_TeleportingIn,    # 0x40b = 1035
                          EffectType.FearOfTheUnseen_Moving,          # 0x4d9 = 1241
                          EffectType.FearOfTheUnseen_TeleportingIn)   # 0x4d6 = 1238


def is_teleporting(state, unit_id: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsTeleporting(unit, state)` — mirror 1:1 :

        IsOwnerOfEffect (unit, state, 0x40c, 0) || IsTargetOfEffect(unit, state, 0x40c)
     || IsOwnerOfEffect (unit, state, 0x40b, 0) || IsTargetOfEffect(unit, state, 0x40b)
     || IsOwnerOfEffect (unit, state, 0x4d9, 0) || IsTargetOfEffect(unit, state, 0x4d9)
     || IsOwnerOfEffect (unit, state, 0x4d6, 0) || IsTargetOfEffect(unit, state, 0x4d6)

    C'est le predicat « l'unite est en DEEP STRIKE / en cours de teleportation ». Les quatre types,
    DANS CET ORDRE, sont exactement `_TELEPORT_MOVE_EFFECTS` : `IdunBattle.Entities.UnitExtensions$$SetMovedFlag`
    INLINE la meme chaine (verifie au decompile : memes quatre litteraux, meme ordre, memes deux
    roles), donc les deux lecteurs du port partagent UNE source -- une 2e liste divergerait au
    premier effet ajoute.

    `onlyActive = 0` sur la branche OWNER -> aucune lecture d'`EffectComponent.IsActive @+0x5c` :
    la simple PRESENCE suffit, ce que rend `EffectsState.has_effect` (meme convention que
    `set_moved_flag`, ou les roles owner/target sont confondus offline -- l'`EffectsState` du port
    stocke par-PORTEUR).

    CONSOMMATEURS : `set_moved_flag` (flag `Teleported`), et la regle-delegue CASTER de 1115
    `FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` (#447)."""
    if state is None or getattr(state, "effects", None) is None:
        return False
    return any(state.effects.has_effect(int(unit_id), effect_type=t)
               for t in _TELEPORT_MOVE_EFFECTS)


def set_moved_flag(state, unit_id: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$SetMovedFlag` — mirror 1:1, appele par
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (SEUL chemin de pose du flag avec
    `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile`) :

        added = UnitFlagsComponent.Add(unit, UnitFlag.Moved=0)
        if added and (IsOwnerOfEffect|IsTargetOfEffect (unit, 0x40c|0x40b|0x4d9|0x4d6)):
            UnitFlagsComponent.Add(unit, UnitFlag.Teleported=0xc)

    `Add` natif rend « etait ABSENT » -> le flag Teleported n'est pose qu'au PREMIER move du tour
    (fidele : un 2e move ne re-teste pas les effets de teleport). Roles owner/target confondus offline
    (l'`EffectsState` stocke par-porteur ; meme convention que `is_attack_max_out_damage`).
    Cree le `UnitFlagsComponent` au besoin (le natif le resout par `GetComponent` sur une entite qui
    l'a toujours). Renvoie « le flag Moved vient d'etre pose »."""
    e = state.get_entity(unit_id)
    if e is None:
        return False
    fl = e.get_component(UnitFlagsComponent)
    if fl is None:
        fl = e.add_component(UnitFlagsComponent())
    added = not fl.has(UnitFlagsComponent.MOVED)
    fl.add(UnitFlagsComponent.MOVED)
    if added and is_teleporting(state, unit_id):
        fl.add(UnitFlagsComponent.TELEPORTED)                 # Add(0xc) — le move etait un teleport
    return added


def unit_has_moved(state, unit_id: int) -> bool:
    """`HasFlag(unit, UnitFlag.Moved=0)` (`IdunBattleLogic.Entities.DSLTriggers$$HasFlag` ->
    `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` = `UnitFlagsComponent.Has`).
    LECTEUR UNIQUE du fait « a bouge ce tour » cote port : le natif n'a QU'UN store (le
    `UnitFlagsComponent`), pose par `set_moved_flag` et purge par `RemoveTurnFlags(new_activation=1)`
    du `StartTurnOperation` — PAR JOUEUR ENTRANT, pas globalement. Consommateurs : le gate no-move de
    `HeavyWeapon_ExtraDmg`/`CrushingStrike` (via `attacker_modifiers`), la branche fin-de-tour de
    `RadSaturation`, le `GetHits` d'HarvesterOfSouls. Composant absent = flag absent = n'a pas bouge.

    ⚠ FICHE CORRIGEE (2026-07-28, #210) : sur un etat CHARGE, `load_state` SEEDE desormais ce flag
    (`snapshot._load_unit_flags` <- `combatSnapshot.units[].unitFlags`, introduit par `f02e30f`) -- la
    mention anterieure « le RPC n'expose pas les UnitFlags -> une fixture qui SAIT que l'unite a bouge
    doit poser le flag » est PERIMEE. MESURE : `probe_210_blackrage_targeting.py` cas `S4a` (Lucien
    bouge live, capture, etat charge) -> le port rend `CasterHasNotMoved` en accord avec le natif,
    SANS pose manuelle. La pose manuelle (`set_moved_flag`) ne reste necessaire que sur un etat
    construit hors snapshot."""
    e = state.get_entity(unit_id)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlagsComponent.MOVED))


def is_turn_of_unit(state, unit_id: int) -> Optional[bool]:
    """`IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit(unit)` (slot **53** d'`IBattleQuery`,
    arite **1**, LU dans `data/symbols/<build>/metadata/interface_slots.tsv`) -- MIRROR du decompile,
    relu VERBATIM sur `rnca9r7q6c` :

        entity = UnitExtensions.GetUnit(unit, state);
        if (entity == null)  return false;
        turn   = StateExtensions.GetMatchTurn(state);
        owner  = EntityExtensions.GetOriginalOwnerEntity(entity, state);   // null -> NullReference
        return TurnComponent.get_CurrentPlayerId(turn) == owner.Id;

    C'est le PREFIXE de la clause 1 de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`
    (`CasterHasNotMoved`) : quand ce n'est PAS le tour du proprietaire d'ORIGINE, la regle est
    ENTIEREMENT sautee, quel que soit le flag `UnitFlag.Moved`. Le meme prefixe est porte cote
    DECISION par le champ `CasterSubstrate.is_turn_of_unit`
    (`engine.services.ability_caster_gates`) -- deux RESTRICTIONS d'un seul natif a deux substrats,
    la lecture etant la MEME fonction.

    LE SUBSTRAT DU PORT EST EXACT, ET C'EST UNE LECTURE, PAS UNE APPROXIMATION.
    `IdunBattle.Entities.EntityExtensions$$GetOriginalOwnerEntity` resout
    `state.GetEntity(OwnerComponent.<PlayerEntityId @+0x10>)` -- le MEME champ `+0x10` que le hook
    publie en `decisionView.units[].owner` (`frida/hooks/game/match-state.ts`, `ownerPlayerId: 0x10`),
    donc `OwnerComponent.player` cote port.
    ⚠ NE PAS le confondre avec `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`
    (`decisionView.units[].ctrl`), qui lit l'ACCESSEUR
    `IdunBattle.Entities.Components.OwnerComponent$$get_CurrentPlayerEntityId` =
    `(this+0x14 != 0) ? this+0x14 : this+0x10` : le champ `+0x14` est l'override de CONTROLE, et les
    deux divergent sous controle mental (`1164 MindControl`, non portee).

    ECART NOMME, sans substrat cote port : `TurnComponent$$get_CurrentPlayerId` deroute vers le
    joueur TEMPORAIRE quand le `Nullable` `TurnComponent+0x28` a une valeur, sinon rend le champ brut
    `+0x24`. `State.current_player_id` mirroir le champ BRUT (`decisionView.currentPlayer` <-
    `TurnComponent._currentPlayerId @+0x24`) ; aucun canal ne publie `+0x28`. Meme borne que celle
    deja nommee par `engine/streams/turn_phase.py::prepare_turn`.

    TRI-ETAT, et sa DIRECTION est le livrable :
      * `False` MESURE (proprietaire connu, joueur courant connu, differents) -> l'appelant SAUTE
        la clause `CasterHasNotMoved`, comme le natif ;
      * `True` MESURE -> la clause est evaluee ;
      * `None` = **pas mesure** (`OwnerComponent` absent, `player` a `None`, ou `State` sans
        `current_player_id` -- le cas de toute fixture construite hors `load_state`). L'appelant
        ne doit alors PAS alleger la clause : sauter sur une non-mesure FABRIQUERAIT une
        acceptation, alors que la garder rend exactement le verdict d'avant ce prefixe. C'est
        l'inverse de la convention du module DECISION (`invalid_caster_reason`), et pour la raison
        qui l'inverse : la-bas le tri-etat borne la ZONE par le HAUT, ici il garde un REFUS mesure.

    `entity is None` -> `False` : mirror du `if (entity == null) return false` natif. Le verdict
    n'a aucune portee pratique (`unit_has_moved` rend alors `False` de son cote), mais il est ecrit
    parce que le natif l'ecrit."""
    e = state.get_entity(unit_id) if state is not None else None
    if e is None:
        return False                        # `if (GetUnit(unit, state) == null) return false;`
    oc = e.get_component(OwnerComponent)
    if oc is None or oc.player is None:
        return None                         # proprietaire non capte -> PAS MESURE
    cur = getattr(state, "current_player_id", None)
    if cur is None:
        return None                         # `TurnComponent.CurrentPlayerId` non capte -> PAS MESURE
    return int(oc.player) == int(cur)


def record_tiles_moved(state, unit_id: int, tiles: int) -> int:
    """`IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state)` — mirror 1:1 :

        if ((int)tiles < 1) return;                 // no-op silencieux, 0 et negatifs compris
        comp = GetComponent<ActorStatisticsComponent>(unit);
        comp[0xec] += tiles;                        // cumul BATAILLE
        comp[0xf0] += tiles;                        // cumul CE TOUR

    Les DEUX champs prennent le MEME increment ; c'est un `+=`, jamais une affectation, ce qui est
    exactement ce qui permet a la face DECISION de voir « compteur reel + tuiles du pas simule »
    quand `SimulateEffectsOperation$$DoActionInSimulatedTile` rejoue un `MoveUnitOperation`
    (cf. `playbook/prediction/_shared.py::prediction_tiles_moved_this_turn`).

    Renvoie le nombre EFFECTIVEMENT enregistre (0 si le garde `< 1` a coupe) — diagnostic."""
    if tiles is None:
        return 0
    n = int(tiles)
    if n < 1:                                       # `if (iVar2 < 1) return;`
        return 0
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return 0
    uc.tiles_moved_this_battle = int(uc.tiles_moved_this_battle or 0) + n
    uc.tiles_moved_this_turn = int(uc.tiles_moved_this_turn or 0) + n
    return n


def unit_tiles_moved_this_turn(state, unit_id: int) -> int:
    """`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` = le champ
    `ActorStatisticsComponent + 0xf0` du porteur -- LECTEUR UNIQUE du canal cote COMBAT.

    C'est ce que resout le noeud DSL `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn`,
    dont le consommateur porte est `ModifiedExoarmour_ExtraDmgEffect` (magnitude `V x n` ET
    `CreateActiveCondition`). Composant absent = 0, comme un composant natif frais."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(uc.tiles_moved_this_turn or 0) if uc is not None else 0


def reset_tiles_moved_this_turn(state, unit_id: int, was_own_turn: bool) -> None:
    """Volet TUILES de `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(
    comp, wasOwnTurn)`, appele par `IdunBattle.Operations.EndTurnOperation$$Execute` sur CHAQUE
    unite de `GetAllUnits` :

        if (wasOwnTurn) comp[0xf4] = comp[0xf0];    // TilesMovedLastTurn
        comp[0xf0] = 0;                             // reset INCONDITIONNEL

    `was_own_turn` = l'unite appartient au joueur qui FINIT son tour (le natif le derive de
    `PlayerComponent.CurrentlyOwnedUnitIds` de ce joueur, teste par `List.Contains`).
    Les autres champs que `ResetThisTurn` roule (0x78/0x7c, 0xe4/0xe8, 0x58/0x5c, 0xa0/0xa4 et le
    dict par-entite) ne sont pas suivis offline -- residu DEJA documente en tete de `turnflow.py`."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return
    if was_own_turn:
        uc.tiles_moved_last_turn = int(uc.tiles_moved_this_turn or 0)
    uc.tiles_moved_this_turn = 0


def register_attack_made(state, attacker_id: int, target_id: int,
                         total_crits: int = 0) -> None:
    """`IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade(this, target,
    rangeType, totalCrits)` -- volet PORTE (les champs qu'un consommateur porte lit), lu a
    l'assembleur :

        this[0x50] = target.Id;                          // derniere unite attaquee (non porte)
        if (this[0x40] != null) {                        // HashSet<BEntityId> unitsAttackedThisTurn
            if (Count(this[0x40]) == 0) this[0x30] += 1; // <- TotalTurnsWithAttacksMade
            Add(this[0x40], target.Id);
            this[0x20] += 1;                             // <- TotalAttacksMade (#926)
            this[0x54] += totalCrits;                    // <- CriticalHitsThisTurn (#521-r10)
            this[0x24] += 1;                             // <- AmountOfAttacksMadeThisTurn (#508-r1)
            if (rangeType == 1) this[0x2c] += 1;         // variante Melee        (non portee)
            if (rangeType == 2) this[0x28] += 1;         // variante Ranged       (non portee)
        }

    `+0x30` n'avance donc **qu'une fois par tour**, au PREMIER coup porte -- c'est ce qui fait de
    lui un compte de TOURS et non d'attaques.

    **`+0x20` (`TotalAttacksMade`) EST PORTE DEPUIS #926** -- c'est ce que lit
    `IdunBattle.Entities.Formulas.TotalAttacksMadeFormula$$Calculate` (`return *(uint*)(comp +
    0x20)`), et donc le noeud DSL `IdunBattleLogic.Entities.DSLFormulas$$TotalAttacksMade`. Son
    premier consommateur COMBAT est `FirstAmongTraitors_ExtraDmgEffect`, dont la magnitude est
    `Min(Sum(ConfigVar(extraDmg), Multiply(TotalAttacksMade(EffectSource), ConfigVar(extraDmg_2))),
    ConfigVar(maxDmg))` : sans le compteur, le terme croissant serait fige a 0 cote combat alors
    que la face PREDICTION, elle, le lit deja (capteur live `actorStats.totalAttacksMade`,
    `playbook/scene.py`). Porter le champ est ce qui EMPECHE un fork prediction/combat.

    **`+0x24` EST PORTE DEPUIS #508-r1** -- c'est ce que lit
    `IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$Calculate` quand son
    `Nullable<rangeType>` n'a PAS de valeur, et c'est le cas des DEUX call-sites de
    `LeadingTheChargeAbility$$ExecuteBehaviour`. Le noeud DSL
    `IdunBattleLogic.Entities.DSLFormulas$$TimesAttackMadeThisTurn` a **QUATRE** call-sites natifs
    pour **TROIS** abilities -- `LeadingTheCharge` (x2), `IconOfObstinacy_AddArmourBuffAbility` et
    `LegacyOfCombat` : porter le compteur rend le noeud REUTILISABLE, c'est l'argument qui a
    tranche le rayon de souffle.

    ⚠ **`+0x28`/`+0x2c` restent NON PORTES -- MAIS LE BLOCAGE ANNONCE ETAIT FAUX (#508-r2,
    re-mesure 2026-08-15).** La RE disait « le call-site du slot `IOperationProcessor` **74**
    (`RegisterAttack`, arite 4) n'a pas ete localise, donc le `rangeType` serait devine ». Il est
    localise, et il est ENTIEREMENT lu :

        IdunBattle.Operations.FinishAttackOperation$$Execute
            currentAttack = <l'OngoingAttack courante>
            defender      = IdunBattle.Entities.UnitExtensions$$GetUnit(target, state)
            rt = BattleQuery.<slot 4 = GetAttackRangeType>(          # arite 4, interface_slots.tsv
                     ability        = AttackOptions+0x10,
                     caster         = attacker,
                     casterPosition = EntityExtensions$$GetUnitPosition(attacker),
                     target         = target)
            if (defender != null)
                processor.<slot 0x4a = RegisterAttack>(attacker, defender,
                                                       Nullable<AttackRangeType>(rt),
                                                       totalCrits = currentAttack+0x28)

    Le `Nullable` y est **TOUJOURS renseigne** (il est construit avec `rt`, jamais laisse vide) :
    les deux variantes sont donc alimentees a chaque attaque cote natif. Et l'ETAGE qui manquait au
    port est desormais LA : `services/battle_query.get_attack_range_type` (foyer, frere des slots 2
    et 3) + `triggers/base._attack_range_type` (domaine runner), poses par #951-r1 -- qui consomme
    la MEME fonction native pour l'`inMelee` du vecteur de mort.

    **PORT REFUSE, ET LE VERDICT EST SOUS CLIQUET DEPUIS #508-r2 (2026-08-18)** : aucun consommateur
    ne l'exige, et ce n'est plus une prose mais un test.
    `IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$.ctor` -- la SEULE porte par
    laquelle son `Nullable<AttackRangeType>` (`@+0x18`) puisse recevoir une valeur -- n'a qu'**UN**
    appelant, `IdunBattleLogic.Entities.DSLFormulas$$TimesAttackMadeThisTurn`, qui a lui-meme
    **QUATRE** call-sites pour **TROIS** abilities : `IconOfObstinacy_AddArmourBuffAbility` (#919),
    `LegacyOfCombat` (#928) et `LeadingTheChargeAbility$$ExecuteBehaviour` (x2). Les QUATRE passent
    litteralement `(void *)0x0` -- relus un par un le 2026-08-18 sur le build `t6dpr4k06g`. Et
    `ActorStatisticsComponent` n'expose AUCUN getter sur `@+0x28`/`@+0x2c` : hors de cette formule,
    rien ne peut les lire. Les deux compteurs sont donc du natif ECRIT-MAIS-JAMAIS-LU, et les porter
    serait un canal sans lecteur (patron #419) dont le premier test devrait FABRIQUER une demande
    que le jeu ne produit pas.
    Cote PORT, la bijection est exacte : `unit_attacks_made_this_turn` a **4** sites d'appel dans
    **3** modules, tous a DEUX arguments -- c'est-a-dire le bras `rangeType = null`.
    Garde : `tests/engine/runner/test_508r2_range_type_sans_lecteur_offline.py` (5 tests ; **3
    mutations, 3 rouges** : un lecteur qui reclame une portee, un compteur par portee pose sans
    lecteur, et le demenagement de l'ecrivain). Il ROUGIT le jour ou l'une de ces trois conditions
    change -- le port devient alors exigible AVEC son vecteur.
    Ce qu'il faudra trancher ce jour-la, et que le cliquet FIGE (etage 4) : le natif appelle
    `RegisterAttack` depuis `FinishAttackOperation` (une fois par CIBLE, a la cloture) alors que le
    port appelle cette fonction-ci depuis `_apply_damage_pipeline` -- les deux rangs devront etre
    reconcilies, pas seulement le `rangeType` threade.

    SEUL appelant natif : `IdunBattle.Operations.RegisterAttackOperation$$Execute` -- le MEME que
    `...$$RegisterAttackReceived`, dont le port place deja le mirror (`record_attacked`) dans le
    chokepoint post-resolution `AttackDamageOperation._apply_damage_pipeline`. Les deux compteurs
    bougent donc au meme instant, comme cote natif : **l'attaque qui declenche l'increment ne le
    voit PAS elle-meme** (elle a deja calcule son degat).

    **`+0x54` EST PORTE DEPUIS #521-r10** -- `total_crits` = le 4e argument natif, c'est-a-dire le
    nombre de coups CRITIQUES de l'attaque. Le rang differe et c'est DIT : le natif somme les crits
    de TOUTE l'attaque et appelle `RegisterAttack` une seule fois a la cloture
    (`FinishAttackOperation`, `totalCrits = currentAttack+0x28`), la ou ce mirror est appele PAR
    GROUPE de degat depuis `_apply_damage_pipeline` avec les crits de CE groupe. La SOMME par tour
    -- la seule chose que lise `CriticalHitsThisTurnFormula` -- coincide tant que chaque coup
    traverse le chokepoint ; c'est le meme ecart de rang que celui deja documente ci-dessus pour
    `+0x24`, et il porte sur les deux champs ENSEMBLE, jamais sur l'un sans l'autre.
    Un appelant qui ne mesure pas les crits passe `0` : le natif, lui, passe TOUJOURS une valeur
    (jamais un `Nullable` vide) -- mais un vecteur de degat SANS jet de crit (DoT, degat direct)
    n'appelle pas cette fonction du tout, le gate `is_attack` du chokepoint le tenant deja.

    LECTEURS PORTES : `MartialInspiration_ExtraDamageEffect` (#509), via
    `IdunBattle.Entities.Formulas.TotalTurnsWithAttacksMadeFormula$$Calculate` ;
    `unit_attacks_made_this_turn` ci-dessous (#508-r1) ; `unit_total_attacks_made` (#926) ; et
    `unit_critical_hits_this_turn` (#521-r10, noeud DSL `CriticalHitsThisTurn`)."""
    if attacker_id is None or target_id is None:
        return                                           # `attacker == null` -> le natif ne fait rien
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return                                           # attaquant NON-UNITE (tuile en feu) : pas de composant
    if not uc.units_attacked_this_turn:                   # `Count(this[0x40]) == 0`
        uc.turns_with_attacks_made = int(uc.turns_with_attacks_made or 0) + 1
    # `OrderedSet$$Add` : insertion en QUEUE, sans doublon (un re-hit de la meme cible NE la
    # remonte PAS en fin d'ordre -- `dict[k] = v` sur une cle deja presente laisse sa position).
    # C'est le contrat que lit `Last(UnitsAttackedThisTurn(caster), 1)` (#940).
    uc.units_attacked_this_turn[int(target_id)] = None
    uc.total_attacks_made = int(uc.total_attacks_made or 0) + 1           # `this[0x20] += 1`
    # `this[0x54] += totalCrits` -- ORDRE NATIF conserve : l'increment des crits est ENTRE `+0x20`
    # et `+0x24` dans le decompile. Aucun observable n'en depend (trois `+=` independants), mais on
    # ne reordonne pas un mirror.
    uc.critical_hits_this_turn = int(uc.critical_hits_this_turn or 0) + int(total_crits or 0)
    uc.attacks_made_this_turn = int(uc.attacks_made_this_turn or 0) + 1   # `this[0x24] += 1`


def unit_turns_with_attacks_made(state, unit_id: int) -> int:
    """`IdunBattle.Entities.Formulas.TotalTurnsWithAttacksMadeFormula$$Calculate` = le champ
    `ActorStatisticsComponent + 0x30` de l'unite selectionnee (`GetComponent` puis `*(int*)(c+0x30)`)
    -- LECTEUR UNIQUE du canal cote COMBAT.

    C'est ce que resout le noeud DSL `IdunBattleLogic.Entities.DSLFormulas$$TotalTurnsWithAttacksMade`,
    dont le consommateur porte est `MartialInspiration_ExtraDamageEffect` (magnitude
    `ConfigVar(extraDmgPct) x n`). Composant absent = 0, comme un composant natif frais.

    ⚠ Ce n'est PAS `TotalAttacksMade` (`+0x20`, `unit_total_attacks_made` ci-dessous, #926) : le
    natif fait diverger les deux faces de cette ability -- divergence prediction/combat NATIVE,
    portee telle quelle des deux cotes."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(uc.turns_with_attacks_made or 0) if uc is not None else 0


def unit_total_attacks_made(state, unit_id: int) -> int:
    """`IdunBattle.Entities.Formulas.TotalAttacksMadeFormula$$Calculate` = le champ
    `ActorStatisticsComponent + 0x20` de l'unite selectionnee (`GetComponent` puis
    `*(uint*)(c+0x20)`) -- LECTEUR UNIQUE du canal cote COMBAT (#926).

    C'est ce que resout le noeud DSL `IdunBattleLogic.Entities.DSLFormulas$$TotalAttacksMade`.
    Consommateur porte : `FirstAmongTraitors_ExtraDmgEffect` (magnitude `Min(extraDmg + n x
    extraDmg_2, maxDmg)`, `n` = ce compteur pris sur l'`EffectSource` = le PORTEUR de l'aura).
    Composant absent = 0, comme un composant natif frais.

    ⚠ CUMUL DE BATAILLE : contrairement a `attacks_made_this_turn` (+0x24),
    `reset_units_attacked_this_turn` ne le remet PAS a zero (son ecriture 64 bits part de +0x24).
    Pendant EXACT de la face PREDICTION `playbook/scene.py::total_attacks_made` (capteur live
    `actorStats.totalAttacksMade`) : MEME champ natif, MEME semantique, pas de fork."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(uc.total_attacks_made or 0) if uc is not None else 0


def unit_attacks_made_this_turn(state, unit_id: int) -> int:
    """`IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$Calculate` -- MIRROR du
    decompile, dans le regime `rangeType = null` :

        sum = 0
        foreach (unit in <selecteur this+0x10>.Select(entities)) {
            comp     = unit.GetComponent<ActorStatisticsComponent>()
            hasValue = (this+0x18 : Nullable<AttackRangeType>).HasValue
            value    = GetValueOrDefault(this+0x18)
            if      (hasValue && value == 1) sum += comp[0x2c];    // Melee
            else if (hasValue && value == 2) sum += comp[0x28];    // Ranged
            else                             sum += comp[0x24];    // TOUTES
        }
        return sum

    Le port n'expose ICI que la branche `else` -- le `Nullable` VIDE -- parce que c'est celle des
    DEUX call-sites de `LeadingTheChargeAbility$$ExecuteBehaviour` (relus 2026-08-15 : les deux
    passent litteralement `(void *)0x0`), et parce que les deux compteurs par `rangeType` ne sont
    pas alimentes (cf. `register_attack_made`). Un appelant qui aurait besoin d'une variante doit
    d'abord les alimenter : rendre un total la ou le natif rend un sous-compte serait un ecart
    SILENCIEUX et PERMISSIF. Ce n'est plus une RE a faire -- l'etage `GetAttackRangeType` est porte
    (#951-r1) et le call-site est localise (#508-r2) : c'est un CABLAGE, dont le rang reste a
    arbitrer.

    Le selecteur `this+0x10` est resolu par l'appelant (ici : le caster) -- comme
    `unit_turns_with_attacks_made`, ce mirror prend l'unite deja resolue. Composant absent = 0,
    comme un composant natif frais.

    ⚠ **PAS DE SEED LIVE** : `rpc-snapshot.ts` publie `totalTurnsWithAttacksMade` (`+0x30`) mais pas
    `+0x24` -- un etat RECHARGE repart donc de `0`, meme si l'unite avait deja frappe ce tour-la.
    Poser le capteur exige une REINJECTION. C'est INERTE pour le seul consommateur porte
    (`LeadingTheCharge`), qui compare le compteur A LUI-MEME (`SetCache` avant / `AmountIsGreater`
    apres, dans le MEME rejeu) : seule la DIFFERENCE compte, et elle est juste quel que soit le
    point de depart. Tout futur consommateur qui lirait la VALEUR ABSOLUE doit d'abord obtenir ce
    canal."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(uc.attacks_made_this_turn or 0) if uc is not None else 0


def reset_units_attacked_this_turn(state, unit_id: int) -> None:
    """`IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetUnitsAttackedThisTurn` --
    MIRROR du decompile, et son NOM ne dit PAS tout ce qu'il fait :

        if (this[0x40] == null) throw
        Clear(this[0x40])
        this[0x54] = 0                       // <- CriticalHitsThisTurn (#521-r10)
        *(long long*)(this + 0x24) = 0       // <- UNE ecriture 64 bits : +0x24 ET +0x28
        this[0x2c] = 0

    C'est donc ICI que les trois compteurs d'ATTAQUES EMISES sont remis a zero (#508-r1), et nulle
    part ailleurs : les deux `ActorStatisticsComponent$$ResetThisTurn` ne les touchent pas (le
    premier ecrit dans son parametre `data`, le second roule `+0xf0/+0x78/+0xe4/+0x58/+0xa0` et les
    champs des sous-structures de son dictionnaire).

    Appelants natifs (xrefs COMPLETES) :
    `IdunBattle.Operations.StartTurnOperation$$Execute` (x2), `$$ResetUnit`, `$$ResetMachine` --
    c'est donc l'ENTREE de tour qui rouvre la fenetre, PAS `EndTurnOperation` (qui, lui, roule les
    champs `+0xf0`/`+0x78`/`+0xe4`/`+0x58`/`+0xa0`, cf. `reset_tiles_moved_this_turn`).

    Consequence portee : une unite qui attaque DEUX fois dans le meme tour n'incremente
    `turns_with_attacks_made` qu'une fois ; une unite qui attaque a deux tours differents
    l'incremente deux fois."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is not None:
        uc.units_attacked_this_turn.clear()
        uc.critical_hits_this_turn = 0                   # `this[0x54] = 0`  (#521-r10)
        uc.attacks_made_this_turn = 0                    # `*(long long*)(this + 0x24) = 0`


def unit_critical_hits_this_turn(state, unit_id: int) -> int:
    """`IdunBattle.Entities.Formulas.CriticalHitsThisTurnFormula$$Calculate` -- MIRROR du decompile,
    l'unite du selecteur `this+0x10` etant deja resolue par l'appelant (meme convention que
    `unit_turns_with_attacks_made` / `unit_attacks_made_this_turn`) :

        unit = <selecteur this+0x10>.<slot 8 = SelectActor>(entities)
        if (unit == null) return 0
        comp = unit.GetComponent<ActorStatisticsComponent>()
        if (comp != null) return *(uint *)(comp + 0x54)
        <NullReference>                                  // le natif NE rend pas 0 ici

    C'est ce que resout le noeud DSL `IdunBattleLogic.Entities.DSLFormulas$$CriticalHitsThisTurn`
    (`entities/formulas.py::CriticalHitsThisTurn`).

    ⚠ **LES DEUX ABSENCES NE SE VALENT PAS COTE NATIF**, et le port les rabat pourtant toutes deux
    sur `0` : `unit == null` rend bien `0`, mais un composant MANQUANT leve. Le rabattement est
    volontaire et sans effet observable -- cote natif tout `Unit`/`Machine` porte un
    `ActorStatisticsComponent` (pose par la factory), donc la branche qui leve est inatteignable
    pour un selecteur qui a deja rendu une unite ; cote port l'absence de composant designe une
    entite NON-UNITE (tuile en feu), pour laquelle rendre 0 est le comportement de tous les mirrors
    voisins de ce module. Faire lever ici transformerait une entite non-unite en crash.

    SEUL consommateur natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    DaemonicOrdnance_RemoveCritChance$$CreateBehaviour` (#521-r4)."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(uc.critical_hits_this_turn or 0) if uc is not None else 0


def unit_has_teleported(state, unit_id: int) -> bool:
    """`HasFlag(unit, UnitFlag.Teleported = 0xc)` — pendant de `unit_has_moved`, pose par
    `set_moved_flag` quand le deplacement etait un TELEPORT (et par le capteur O5 de
    `combatSnapshot.unitFlags` sur un etat recharge, cf. `snapshot._load_unit_flags`).

    UNIQUE consommateur porte : la branche `| HasFlag(Self@0x148, 0xc)` du trigger de
    `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`, lue verbatim :

        OwnerIsCaster & IsRangedAttack
          & ((df@0xa0 & !HasFlag(Self, 3 = TurnFinished)) | !df@0xa0)
          & (!HasFlag(Self, 0 = Moved) | HasFlag(Self, 0xc = Teleported))

    -> un porteur `HeavyWeapon` qui s'est TELEPORTE garde son +25% ranged, alors qu'un deplacement
    ordinaire le lui retire. A NE PAS generaliser : la condition soeur
    `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition` est
    `!HasFlag(Self, 0)` **seul**, sans branche Teleported (decompile relu)."""
    e = state.get_entity(unit_id)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlagsComponent.TELEPORTED))


def unit_has_used_active_ability(state, unit_id: int) -> bool:
    """`HasFlag(unit, UnitFlag.ActiveAbilityUsed = 2)` — l'unite a consomme son ACTION ce tour.

    Meme store que `unit_has_moved` (le `UnitFlagsComponent` unique) : pose par la queue de cast
    (`AActiveAbility.SetsActiveAbilityUsedFlag` -> `UnitFlags.Add(2)`, cf.
    `runner/abilities/base.py`), purge a l'entree de tour par
    `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`, et seede depuis le live
    par `snapshot._load_unit_flags`.

    CONSOMMATEUR : le gate d'entree du generateur d'abilities de l'IA
    (`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`,
    1re instruction : `if (HasFlag(unit, 2)) return 0`). Composant absent = flag absent = n'a pas
    encore agi."""
    e = state.get_entity(unit_id)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED))


def update_charging(state, unit_id: int, old_pos, new_pos) -> list:
    """`IdunBattle.Operations.MoveUnitOperation$$UpdateCharging(this, unit, newPosition, oldPosition,
    unitComponent)` — MIRROR du decompile :

        before = query.GetAdjacentUnits(oldPosition, unit)      # vide si oldPosition n'a pas de MainTile
        after  = query.GetAdjacentUnits(newPosition, unit)
        foreach u in after:
            if (!before.Contains(u))                            # NOUVELLEMENT adjacente
                if (!unitComponent.ChargedUnitIds.Contains(u.Id))
                    unitComponent.ChargedUnitIds.Add(u.Id)      # +0x190

    => « charger » = arriver AU CONTACT d'une unite qui ne l'etait pas avant CE pas de deplacement.
    Le natif n'y filtre NI l'equipe NI la vie : la liste retient toute unite nouvellement adjacente
    (le filtre ennemi/vivant vit chez le consommateur). Appele DEUX fois dans
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (branche « no-automatic-turns » et branche
    normale), toujours AVANT `SetMovedFlag`.

    `old_pos`/`new_pos` = (col,row) ; `old_pos=None` (unite sans position avant le move, ex. spawn)
    -> `before` vide, mirror du `MainTile == null` natif. Renvoie les ids AJOUTES (diag).

    ⚠ « ADJACENT » Y EST `IterateAdjacentTiles`, PAS `hexgeo.distance == 1` (#433-r4-r1-r4-r2-r1).
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits(from, ...)` est LU comme
    `IterateAdjacentTiles(from, ...)` puis `GetUnitsOnTiles(...)`, et
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere la
    liste STOCKEE du `ConnectivityComponent` (`+0x10`) avant d'appliquer la porte `|dElev| < 2`.
    D'ou la delegation a `battle_query.is_adjacent`, foyer des DEUX etages : ce mirror ECS et son
    jumeau PREDICTION (`battle_query.newly_adjacent_ids`) portent le MEME natif et doivent voir le
    MEME graphe, sinon `IsCharging` diverge d'une face a l'autre alors que le natif n'a qu'un seul
    `IBattleQuery` -- meme exigence que `Board.walk_maps_by_pos` sur `TilesMovedThisTurn`.
    Canaux derives du board (tri-etat) : `state.board` absent -> repli GEOMETRIQUE nomme
    d'`is_adjacent`, c'est-a-dire exactement le comportement d'avant.

    La liste est videe par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (cf.
    `FinishUnitTurnOperation.execute`) -> sa duree de vie est L'ACTIVATION de l'unite, ce qui donne au
    predicat `IsCharging` sa semantique « a charge cette cible CE TOUR ». Aucun autre site natif
    n'ecrit ce champ (xrefs de `UpdateCharging` : les 2 call-sites de `Execute` ; le seul autre
    lecteur est `BattleQuery$$IsCharging`)."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or new_pos is None:
        return []
    board = getattr(state, "board", None)
    elev_by_pos = elevations_by_pos(board)
    neigh_by_pos = adjacent_neigh_by_pos(board)

    def _adjacent_ids(pos):
        if pos is None:
            return set()
        out = set()
        for oid, other in state.entities.items():
            if oid == unit_id:
                continue
            opc = other.get_component(PositionComponent)
            if opc is None:
                continue
            if is_adjacent(tuple(pos), (opc.col, opc.row), elev_by_pos, neigh_by_pos):
                out.add(int(oid))
        return out

    before = _adjacent_ids(old_pos)
    added = []
    for oid in sorted(_adjacent_ids(new_pos) - before):
        if oid not in uc.charged_unit_ids:
            uc.charged_unit_ids.append(oid)
            added.append(oid)
    return added


def charged_unit_ids(state, unit_id: int) -> set:
    """Les ids que `unit_id` a CHARGES (liste `UnitComponent + 0x190`). Composant absent -> vide."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return set(int(i) for i in (uc.charged_unit_ids or ())) if uc is not None else set()


def can_be_overkilled(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$CanBeOverkilled` = `!BaseUnitComponent.HasTrait(u, 0x1b)`
    (0x1b = 27 = `UnitTrait.Steppable`) ; unite SANS `BaseUnitComponent` -> True (le natif retourne 1
    quand `GetBaseUnitComponent` rend null). C'est le PREMIER gate de la surcharge d'instance de
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` : une unite Steppable n'est JAMAIS overkillee,
    quel que soit le degat.

    Porteurs Steppable ATTEIGNABLES en runner (donc gate vivant, pas du code mort) : les DEUX summons
    `astarSmnHaywireMine` (Cyrus) et `genesSmnDecoy` -- ce dernier est pose par `Ambush_SummonAbility`
    a la mort de tout porteur du trait `Ambush` (genesPrimus/genesKelermorph/genesMagus/genesBiophagus,
    tous dans le pool) --, plus les objets de terrain npc (loot/powerups).

    Les noms de traits viennent de `StatsComponent.ctx.traits` (NOMS gameconfig), meme convention que
    tous les `HasTrait(target, ...)` portes ; ctx absent -> pas de trait connu -> True (degradation
    fidele : le natif rend True quand le composant de base manque)."""
    if entity is None:
        return True
    sc = entity.get_component(StatsComponent)
    traits = getattr(getattr(sc, "ctx", None), "traits", None) if sc is not None else None
    return not has_trait(traits, UnitTrait.Steppable)


def unit_is_overkilled(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasFlag(target, 8 = UnitFlag.Overkilled)` -- la GARDE
    D'ENTREE du SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` :

        cVar15 = UnitExtensions__HasFlag(target, 8);
        if (cVar15 != '\\0') { RecordHitStatistics ; AddLeftoverHit(.., 1) ; return; }

    Un coup porte sur une cible DEJA marquee overkillee n'applique RIEN et **n'emet aucun
    evenement** -- ni `On(0x39)`, ni `On(0xf)`, ni `On(0x10)`, ni le `UnitDamaged` porteur du tag
    `Amount`. Le flag est pose par le MEME `Execute`, au coup ou `didOverkill` devient vrai
    (`IdunBattle.Entities.Components.UnitFlagsComponent$$Add(flags, 8)` sous
    `dar.didOverkill && UnitExtensions.CanBeOverkilled(target)`), et RETIRE par
    `IdunBattle.Operations.ReviveUnitOperation$$Execute`.

    Lecture PURE (aucune mutation) : le port pose le flag, lui, dans `_fire_death_if_killed`."""
    if entity is None:
        return False
    fl = entity.get_component(UnitFlagsComponent)
    return bool(fl is not None and fl.has(UnitFlagsComponent.OVERKILLED))


PREVENT_OVERKILL_EFFECT = EffectType.FuelledByFury_BlockOverkill      # `EffectType.FuelledByFury_BlockOverkill` (0x54a)


def effects_prevent_overkill(active_effects) -> bool:
    """Volet EFFET de `UnitExtensions.HasFlag(target, 0x13)` : une instance ACTIVE de l'effet 1354
    est-elle portee ? FOYER UNIQUE de cette derivation -- `unit_prevents_overkill` (face ECS,
    composant d'abord) et `Scene.prevents_overkill` (face PREDICTION, ou l'etat n'est pas un
    `State`) l'appellent tous deux, pour qu'il n'existe pas DEUX ports d'un meme flag natif.
    L'appelant fournit deja les effets ACTIFS (gate `EffectComponent.IsActive` + condition), qui
    est exactement l'invariant du couple `ApplyInternal`/`RevertInternal` -- cf.
    `unit_prevents_overkill` pour la demonstration."""
    return any(int(getattr(e, "effect_type", -1) or -1) == PREVENT_OVERKILL_EFFECT
               for e in (active_effects or []))


def unit_prevents_overkill(state, unit_id) -> bool:
    """`UnitExtensions.HasFlag(target, 0x13)` — le `suppress` de la surcharge d'instance de
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (`UnitFlag.PreventOverkill`, cf.
    `UnitFlagsComponent.PREVENT_OVERKILL`).

    Le flag est LU ici et DERIVE de l'effet qui le pose. Le binaire n'a qu'UN couple ecrivain, et il
    ENCADRE exactement la duree de vie de l'effet :
      * `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal`
        -> `UnitFlagsComponent.Add(target, 0x13)` ;
      * `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$RevertInternal`
        -> `UnitFlagsComponent.Remove(target, 0x13)`.
    (Recherche litterale au decompile : `UnitFlagsComponent__Add(...,0x13,0)` n'a QUE cette occurrence.)
    L'effet lui-meme est active/desactive par ses propres triggers
    (`...$$CreateHandleTriggerAbilitiesInternal` : `On(0x21)&OwnerIsActor -> ActivateEffect`,
    `On(0x12) -> ActivateEffect`, `On(0x2d = UnitRevived)&OwnerIsTarget -> DeactivateEffect`) -> le flag vaut
    exactement « une instance ACTIVE de l'effet 1354 est portee ». Offline, `EffectsState.active_effects`
    applique DEJA le meme couple flag `EffectComponent.IsActive` + `CreateActiveCondition` : la
    derivation est donc le MEME invariant, pas une approximation (meme schema que
    `group_unit_stat_part`, qui derive le champ « membres restants » de l'etat PV).

    Le composant reste interroge en PREMIER pour tout futur poseur imperatif du flag.

    MESURE LIVE (#178) : `ultraTitus` (i2 << The first time each turn that Titus is defeated he cannot
    be Overkilled >>) porte `FuelledByFury_BlockOverkill` des le deploiement ; un coup de 1452 sur
    400 PV le TUE sans le marquer overkill (le crescendo de son tueur ne monte pas), la ou la MEME
    attaque sur `genesPrimus` (400 PV) le marque."""
    entity = state.get_entity(int(unit_id)) if state is not None else None
    if entity is None:
        return False
    fl = entity.get_component(UnitFlagsComponent)
    if fl is not None and fl.has(UnitFlagsComponent.PREVENT_OVERKILL):
        return True
    eff = getattr(state, "effects", None)
    if eff is None:
        return False
    return effects_prevent_overkill(
        eff.active_effects(int(unit_id), unit_state_for_effects(state, int(unit_id))))


def unit_is_dead(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsDead` — mort SSI `!IsAlive(u) && !HasFlag(u, Fled=9)` : une unite
    RETIREE du board (flag 9, `UnitFlag.Fled`) n'est PAS « morte » au sens de ce predicat. Restreint aux
    UNITES (mirror du garde `EntityExtensions.IsUnit` d'ExecuteInternal) : une source non-unite (tuile/env,
    sans `HealthComponent`) est TOUJOURS vivante -> jamais gated. Inerte (False) sur tout attaquant/caster
    vivant -> le port du gate ne peut sur-immuniser aucune attaque legitime.

    #429-r1-r3-r1-r2 : le `IsAlive` du decompile est `UnitExtensions$$IsAlive` (3 branches), PAS
    `HealthComponent$$IsAlive` (hp >= 1) -- c'est `unit_extensions_is_alive` qui le porte. Avec
    l'ancien appel, une unite RETIREE du plateau a PV pleins (flag `Removed`, `RemoveUnitOperation`)
    restait « pas morte » pour ce predicat ; une ENFUIE le reste, mais par le flag 9, pas par ses PV."""
    if entity is None or unit_extensions_is_alive(entity):
        return False
    fl = entity.get_component(UnitFlagsComponent)
    if fl is not None and fl.has(UnitFlagsComponent.FLED):
        return False
    return True


def is_alive_and_not_fled(entity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled(unit)` — MIRROR 1:1 du decompile,
    et ce n'est PAS la negation d'`unit_is_dead` :

        if (unit == null)                                   return false;
        if (unit.TryGetComponent<HealthComponent>(out hc))  // slot d'iface, `TryGet`
            if (HealthComponent.IsDead(hc))                 return false;
        return !UnitExtensions.HasFlag(unit, 9 UnitFlag.Fled);

    TROIS ecarts avec `unit_is_dead`, tous LUS :
      * l'entite NULLE rend **false** ici (« pas vivante »), alors qu'`unit_is_dead(None)` rend
        false aussi (« pas morte ») -- les deux predicats ne sont pas complementaires ;
      * une unite **FLED** rend **false** ici (elle n'est ni vivante ni sur le plateau), alors
        qu'`unit_is_dead` l'exclut EXPRESSEMENT de la mort (`IsDead` = `!IsAlive && !Fled`) ;
      * l'entite SANS `HealthComponent` (une TUILE, une entite d'environnement) rend **true** :
        le natif SAUTE le test de mort quand `TryGetComponent` echoue, et ne juge plus que le
        flag. C'est ce qui laisse passer les abilities TILE-TARGET -- MESURE (#429-r1-r3) : un
        cast de `GreatFrostAxe` sur la TUILE d'un cadavre ouvre bien le groupe de stream
        `User_UseAbility` (2 evenements), la ou le meme cast sur le CADAVRE n'en produit aucun.

    LECTEUR NATIF, ET SON PERIMETRE (mesure par les XREFS, pas suppose) :
    `IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` n'a que **2 appelants** dans tout le
    binaire `rnca9r7q6c`, tous deux dans `IdunBattle.Messages.InputMessageProcessor$$
    Visit(ActiveAbilityMessage)` -- le CASTER puis la CIBLE, avant toute operation. Aucune autre
    des 37 surcharges de `Visit` ne le teste (`Visit(MoveUnitMessage)`, lue au decompile, n'a
    AUCUN gate de liveness). Le gate porte donc sur UN message, sur SES DEUX bouts.

    LECTEURS PORTES -- DEUX, parce que le port scinde cet unique message natif en deux :
    `abilities/handler.py::visit_ActiveAbilityMessage` (les abilities) et
    `operations/damage.py::visit_AttackUnitMessage` (l'attaque normale COMMANDEE, qui est un
    `ActiveAbilityMessage` en natif -- #139, #429-r1-r3-r1)."""
    if entity is None:
        return False
    if not unit_is_alive(entity):
        return False
    fl = entity.get_component(UnitFlagsComponent)
    return not (fl is not None and fl.has(UnitFlagsComponent.FLED))


# ── Contexte d'évaluation des `CreateActiveCondition` (#208) ──────────────────────────────────────
# `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` évalue l'arbre mémoïsé de l'effet
# (`BaseEffect$$CreateActiveConditionAndCache`, champ `+0x90`) contre un CONTEXTE de 0x130 octets,
# et rend le booléen qu'il écrit dans `EffectComponent.IsActive @+0x5c`. Côté port, la condition est
# ré-évaluée A LA LECTURE (`EffectsState.active_effects` -> `BaseEffect.is_active(unit_state)`) : le
# `unit_state` ci-dessous EST ce contexte. Il n'y a donc QU'UN constructeur — tout appelant d'
# `active_effects` passe par lui (doctrine anti-fork « 1 nœud natif -> 1 porte offline »).
#
# ⚠ POURQUOI CE FOYER EXISTE (#208, régression MESURÉE). Les appelants construisaient chacun un
# `{"hp": ...}` ad hoc : les clés MANQUANTES (`traits`, `max_hp`, `enemy_psykers_alive`) dégradent
# CHAQUE prédicat en VRAI, donc un effet dont la condition est FAUSSE contribuait quand même. C'est
# exactement ce qui obligeait `PinnedEffect` à collapser sa `CreateActiveCondition` dans le gate
# d'IMMUNITÉ (`entity_is_immune_to_effect`) — un mécanisme faux qui rendait le bon observable.


def enemy_psykers_alive(state, unit_id: int) -> Optional[int]:
    """`Enemies( Owner, UnitsWithTrait(AllUnits@0x80, 0x3ea = 1002 Psyker, 3) )` — le CARDINAL du
    sélecteur natif que `AmountIsEqualOrGreater(…, One@0xc0)` compare à 1 dans la
    `CreateActiveCondition` de `DestroyTheWitch_ExtraMove`/`_ExtraDamage` (corps FONDU, cf.
    `entities/effects/loki/destroy_the_witch.py`).

    `AllUnits@0x80` = le sélecteur battlefield-wide (`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` +0x80,
    identifié par `WarHowlAbility$$OtherBuffTargets` = `Friends(owner, @0x80 − owner)` = « tous les
    AUTRES alliés du plateau »). `Enemies(owner, …)` filtre `team != team(owner)` ; les unités
    MORTES ne sont plus sur le plateau. None si l'équipe du porteur est inconnue (clé alors ABSENTE
    du `unit_state` ⇒ prédicat dégradé en VRAI, cf. `_enemy_psyker_on_battlefield`)."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    if oc is None:
        return None
    n = 0
    for uid, e in state.entities.items():
        eoc = e.get_component(OwnerComponent)
        if eoc is None or eoc.team == oc.team:              # Enemies(owner, …)
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        sc = e.get_component(StatsComponent)
        traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
                  else None) or ()
        if "Psyker" in traits:                              # UnitsWithTrait(0x3ea)
            n += 1
    return n


def has_effect_of_type(state, unit_id: int, effect_type: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$HasEffect(sel, effectType, onlyActive, effectTargetType)`
    -> `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects(entity, query, [effectType],
    onlyActive, targetType)` -- la branche « l'entite PORTE cet effet ».

    ⚠ **`onlyActive = 0`** au call-site porte (`CamoCloak_DmgReductionEffect$$HasValidEffectTrigger`) :
    le natif ne consulte PAS `EffectComponent.IsActive @+0x5c`. Le mirror est donc
    `EffectsState.has_effect` (qui ne filtre que `consumed`) et **pas** `active_effects` -- ce
    dernier appelle `BaseEffect.is_active`, et l'appeler ICI bouclerait (ce lecteur alimente
    justement le `unit_state` des `is_active`).

    `targetType = 6` (= 2|4 = owned | targeted) : cote port les deux branches coincident, l'
    `EffectsState` etant indexee par ENTITE PORTEUSE (`by_unit`), qui est la cible de l'`AddEffect`."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return False
    return bool(eff.has_effect(int(unit_id), int(effect_type)))


def owned_effect_bonded_entity(state, unit_id: int, effect_type: int) -> Optional[int]:
    """`BondedEntityFromEffect( EffectFromOwner(<unit>, <effectType>) )` -- la COMPOSITION des deux
    selecteurs natifs, lue chacun au decompile :

      * `IdunBattleLogic.Entities.DSLSelectors$$EffectFromOwner(effectTarget, effectType)` construit
        un `IdunBattle.Entities.Selectors.EffectWithTypeSelector`, dont le `$$Select` appelle
        `IdunBattle.Entities.EntityExtensions$$GetOwnedEffect(entity, state, effectType)` par
        element du selecteur source. `GetOwnedEffect` itere `EffectsOwnedComponent.<+0x10>` (les ids
        possedes), resout chaque id en entite et rend la PREMIERE dont `EffectComponent.Type
        @+0x58` egale le type -- **AUCUN filtre sur `IsActive @+0x5c` ni sur `Removed @+0x5f`** ;
      * `IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$Select` prend le
        `Enumerable.First` du selecteur source, lit le composant de bond de cette entite-effet et
        rend `state.<slot 0x29 Get>(comp.<+0x10>)` -- c'est-a-dire l'entite BONDEE. Selecteur source
        VIDE, ou entite-effet SANS composant de bond => liste VIDE.

    Port : la liste possedee est `EffectsState.by_unit[unit_id]` (meme index, meme ordre d'insertion)
    et le champ `<+0x10>` du composant de bond est `BaseEffect.bonded` (ecrit par
    `AddEffectOperation` en mirror de `AddEffectBehaviour$$DefaultBondEffectBuilder`).

    `None` = aucun effet de ce type sur `unit_id`, OU cette instance n'a pas de bond (les deux sont
    la liste VIDE cote natif, donc le meme `null` en aval d'`AreEqual`). `None` aussi quand l'etat
    n'a pas d'`EffectsState` -- le lecteur ne fabrique pas d'entite."""
    st = getattr(state, "effects", None)
    if st is None:
        return None
    for e in st.by_unit.get(int(unit_id), []):
        if e.consumed:
            continue                       # retire de `EffectsOwnedComponent` -> plus dans la liste
        if int(e.effect_type) != int(effect_type):
            continue
        b = getattr(e, "bonded", None)
        return None if b is None else int(b)
    return None


class _RunnerEffectTargetWorld:
    """Substrat ECS de `entities.effect_targets.EffectTargetWorld` (le pendant DECISION est
    `playbook/scene.py::_SceneEffectTargetWorld`). Un noeud natif, deux substrats."""
    __slots__ = ("state",)

    def __init__(self, state):
        self.state = state

    def unit_ids(self):
        return list(self.state.entities.keys())

    def carries(self, uid: int, effect_type: int) -> bool:
        return has_effect_of_type(self.state, int(uid), int(effect_type))

    def _ent(self, uid: int):
        return self.state.get_entity(int(uid))

    def pos(self, uid: int):
        e = self._ent(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        if pc is None or pc.col is None or pc.row is None:
            return None
        return (pc.col, pc.row)

    def team(self, uid: int):
        e = self._ent(uid)
        oc = e.get_component(OwnerComponent) if e is not None else None
        return oc.team if oc is not None else None

    def alive(self, uid: int) -> bool:
        e = self._ent(uid)
        uc = e.get_component(UnitComponent) if e is not None else None
        return True if uc is None else bool(uc.alive)

    def traits(self, uid: int):
        e = self._ent(uid)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        return (getattr(ctx, "traits", None) or ()) if ctx is not None else ()

    def faction(self, uid: int):
        """`IdunBattleLogic.Entities.DSLSelectors$$UnitsFromFaction(entities, faction, selType)` --
        canal AJOUTE par #1015-r1 pour la geometrie de `SynapseEffect$$CreateTargetSelector`
        (3e disjoint : `UnitsFromFaction(..., UnitFaction.Tyranids = 0xc)`).

        OPTIONNEL du protocole, et c'est voulu : `entities/effect_targets.py` teste sa PRESENCE et
        rend `None` (NON MESURE) quand le substrat ne le publie pas -- jamais un ensemble PARTIEL.
        Le pendant DECISION (`playbook/scene.py::_SceneEffectTargetWorld`) ne l'implemente pas :
        aucun consommateur de la face decision ne lit `IsEffectTarget(_, Synapse_Effect)`.

        Foyer : `entities/effects/aura_selectors.faction_of` (#930, le seul port de cette lecture ;
        `dark_angels_passives._faction_of` y delegue deja). Rend le `FactionId` GAMECONFIG (chaine),
        que l'appelant confronte au NOM du membre d'enum (`entities/unit_faction.UNIT_FACTION_NAMES`)
        -- jamais a un ordinal."""
        return _ASel.faction_of(self.state, int(uid))

    def neigh_by_pos(self):
        """Canal de VOISINAGE NATIF du protocole (#943-r7), derive de l'ECS.

        MEMES foyers que `update_charging` juste au-dessus (`adjacent_neigh_by_pos` /
        `elevations_by_pos`), qui rendent `None` sur un board absent -> repli GEOMETRIQUE nomme
        d'`is_adjacent`, c.-a-d. exactement le comportement d'avant le cablage."""
        return adjacent_neigh_by_pos(getattr(self.state, "board", None))

    def elev_by_pos(self):
        """Second etage (`|dElev| < 2`) d'`IterateAdjacentTiles`, derive de l'ECS."""
        return elevations_by_pos(getattr(self.state, "board", None))


def is_effect_target(state, unit_id: int, effect_type: int) -> Optional[bool]:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget(sel, effectType)`, face COMBAT.

    Delegue au foyer unique `engine.entities.effect_targets.is_effect_target` : la geometrie de la
    liste `EffectComponent.Targets @+0x48` vient du `<Effect>$$CreateTargetSelector` de CHAQUE
    effectType, jamais d'un defaut. `None` = type non porte / substrat manquant -> l'appelant
    degrade explicitement (cf. la docstring du foyer)."""
    ent = state.get_entity(int(unit_id))
    pc = ent.get_component(PositionComponent) if ent is not None else None
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    if pc is None or pc.col is None or pc.row is None or oc is None:
        return None                                    # sujet hors plateau -> inconnu
    return _iet(_RunnerEffectTargetWorld(state), int(unit_id), int(effect_type))


def is_target_of_adjacent_friend_aura(state, unit_id: int, effect_type: int) -> Optional[bool]:
    """Alias HISTORIQUE de `is_effect_target` (case-366-r1 / `1014 CamoCloak` l'appelle avec `1026`).

    Le nom encodait la geometrie d'UN effet (`AdjacentFriends`) alors que le noeud natif n'en connait
    aucune : depuis case-418-r1 la geometrie est indexee PAR effectType dans
    `entities/effect_targets.py`. Conserve tel quel pour ses deux appelants ; tout NOUVEL appelant
    passe par `is_effect_target`."""
    return is_effect_target(state, unit_id, effect_type)


def contagions_of_nurgle_amount(state, unit_id: int, source_id) -> Optional[int]:
    """`IdunBattle.Entities.Triggers.ContagionsOfNurgleAmountFormula$$Calculate` — le nœud
    `IdunBattleLogic.Entities.DSLFormulas$$ContagionsOfNurgleAmount(team, unit)`, lu VERBATIM :

        entity = <selecteur team>.SelectSingle(entities) ;  if (entity == null) return 0
        teamId = EntityExtensions.GetCurrentTeamId(entity, state)
        target = <selecteur unit>.SelectSingle(entities) ;  if (target == null) return 0
        return battleQuery.<slot 0x95>(effectType /* fige a 0x42f par le ctor */, teamId, target,
                                       returnFirst: false)

    Le slot `0x95` d'`IBattleQuery` est `IdunBattle.Core.Services.BattleQuery$$GetTeamActiveAuraAmount`, qui delegue a `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount`
    (signature `(effectType, team, target, returnFirst)`, MEME ordre d'arguments) — DEJA porte par
    case-224 dans `engine/battle_query.py`. Ce foyer DELEGUE donc, il ne re-derive rien :

      * le comparateur est **INCLUSIF** (`dist <= GetCurrentRange(porteur)`), PAS le strict de
        `IsInUnitContagionsOfNurgleAura` — c'est la version d'EQUIPE du prédicat, et c'est elle que
        `CreateActiveCondition` consomme ;
      * le filtre d'appartenance est `GetCurrentTeamId(porteur) == team(<EffectSource>)` — donc
        « porteurs ALLIES DE LA SOURCE de l'effet », pas « ennemis du porteur de l'effet ». Les deux
        coincident sur tous les montages mesures, mais seule la premiere est ce que le natif ecrit.

    `source_id` = `EffectSource(Effect@0x150)` = `EffectComponent.SourceUnit @+0x10` = `eff.source`.
    `None` (source inconnue, entite disparue) => la clé est ABSENTE du `unit_state`, ce que la
    `CreateActiveCondition` consommatrice traite en dégradation (cf.
    `ContagionsOfNurgleArmorReductionEffect.is_active`) — jamais un 0 inventé, qui rendrait
    l'instance inactive et ferait remonter l'armure sans raison native."""
    src = state.get_entity(int(source_id)) if source_id is not None else None
    soc = src.get_component(OwnerComponent) if src is not None else None
    if soc is None or soc.team is None:
        return None                                   # `SelectSingle` null -> le natif rend 0 ; ici
                                                      # « inconnu » (cf. docstring)
    target = None
    units: List[dict] = []
    for uid, ent in state.entities.items():
        pc = ent.get_component(PositionComponent)
        if pc is None:
            continue
        oc = ent.get_component(OwnerComponent)
        uc = ent.get_component(UnitComponent)
        sc = ent.get_component(StatsComponent)
        hc = ent.get_component(HealthComponent)
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        us = getattr(ctx, "stats", None) if ctx is not None else None
        # `hp` est LU par le mirror (`GetSurroundingUnits` ne rend que des unites vivantes : une
        # unite morte est retiree du board par `KillUnit`) -> l'omettre exclurait TOUT le monde.
        d = {"id": int(uid), "pos": {"col": pc.col, "row": pc.row},
             "team": (None if oc is None else oc.team),
             "alive": True if uc is None else bool(uc.alive),
             "hp": (int(hc.hp) if hc is not None and hc.hp is not None else 1),
             "_traits": (getattr(ctx, "traits", None) or ()) if ctx is not None else (),
             "_turns_started": (int(us.get_stat(int(StatType.TURNS_STARTED), 0) or 0)
                                if us is not None else 0)}
        if int(uid) == int(unit_id):
            target = d
        units.append(d)
    if target is None:
        return None                                   # cible sans tuile -> aucun voisinage

    def _unit_has_trait(u, trait_id) -> bool:
        """`UnitExtensions.HasTrait(unit, aura.GetTrait())` — le trait natif est un ID d'enum, le
        substrat du port des NOMS gameconfig (même convention que tous les `HasTrait` portés)."""
        try:
            enum = _UT(int(trait_id))
        except ValueError:
            return False
        return _has_trait(u.get("_traits"), enum)

    return get_in_range_aura_amount(
        int(EffectType.ContagionsOfNurgle_ArmorReduction1),      # 0x42f, fige par le ctor du noeud
        int(soc.team), target, units, _unit_has_trait,
        lambda u: u.get("_turns_started"), return_first=False)


_STRUCTURAL_ANALYSER_TAU = "Tau"          # UnitFaction.Tau = 9 (`UnitsFromFaction(..., 9)`)


def structural_analyser_friends(state, unit_id: int) -> Optional[int]:
    """`Unique( AdjacentFriends(Owner) + UnitsFromFaction(SurroundingFriends(Owner, Direct(2)), 9) )`
    -- le CARDINAL du selecteur natif
    `IdunBattle.Entities.Effects.Loki.StructuralAnalyserAdjacentEffect$$CreateTargetSelector`, que
    `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreaterThanZero` compare a 0 dans
    `IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect$$CreateActiveCondition`
    (case-366-r1).

    DEUX tiers, et le second est filtre par FACTION :
      * `AdjacentFriends` : allie a distance 1, **toute faction** ;
      * `UnitsFromFaction(SurroundingFriends(range = Direct(2)), Tau)` : allie T'au a distance <= 2.
    Le PORTEUR n'y entre pas -- MESURE (case-366-r1) : Darkstrider seul, sans aucun allie proche,
    a `StructuralAnalyser_Visual.active == false`. C'est le meme selecteur d'aura que
    `DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` (partage x4 : StructuralAnalyser /
    SereneUnifier / DotGG / WayOfTheShortBlade, cf. `docs/rl/case-220/tau.md`), d'ou la meme forme
    `d == 1 or (d <= 2 and faction == Tau)` que `aura_selector_covers`.

    `None` si le porteur n'a ni equipe ni tuile (cle alors ABSENTE du `unit_state` => predicat
    degrade en VRAI, cf. `StructuralAnalyserVisualEffect.is_active`) -- jamais un 0 invente."""
    import hexgeo
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from ..ai.action_generators import _faction               # FactionId gameconfig par visualId
    here = (pc.col, pc.row)
    # ⚠ LES DEUX TIERS N'ONT PAS LE MEME SUBSTRAT NATIF (#433-r4-r1-r4-r2-r1-r1-r1-r1) :
    #   * `AdjacentFriends` -> `IdunBattleLogic.Entities.DSLSelectors$$AdjacentTiles` -> la liste
    #     STOCKEE du `ConnectivityComponent` + la porte `|dElev| < 2` de
    #     `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` ;
    #   * `SurroundingFriends(range = Direct(2))` -> `SurroundingTiles` ->
    #     `BattleQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`, qui balaie le CUBE sans
    #     liste ni porte -> la distance hex nue EST le mirror exact.
    # Le board est SOUS LA MAIN (`state.board`) : aucun seeding. Board absent -> le foyer retombe
    # sur son repli GEOMETRIQUE nomme, c.-a-d. le comportement d'avant le cablage.
    board = getattr(state, "board", None)
    elev_by_pos = elevations_by_pos(board)
    neigh_by_pos = adjacent_neigh_by_pos(board)
    n = 0
    for uid, e in state.entities.items():
        if int(uid) == int(unit_id):                          # le porteur n'est pas son propre ami
            continue
        eoc = e.get_component(OwnerComponent)
        if eoc is None or eoc.team != oc.team:                # Friends(owner, ...)
            continue
        euc = e.get_component(UnitComponent)
        if euc is None or not euc.alive:                      # une unite morte quitte le plateau
            continue
        epc = e.get_component(PositionComponent)
        if epc is None:
            continue
        there = (epc.col, epc.row)
        if is_adjacent(here, there, elev_by_pos, neigh_by_pos):   # AdjacentFriends (toute faction)
            n += 1
        elif (hexgeo.distance(here, there) <= 2
                and _faction(euc.visual_id) == _STRUCTURAL_ANALYSER_TAU):
            n += 1                                            # UnitsFromFaction(Surrounding(2), Tau)
    return n


def adjacent_friendly_summons_and_decoys_count(state, unit_id: int) -> Optional[int]:
    """`Count( UnitsWithTrait(AdjacentFriends(Owner, 1, 3), 0x2 = Summon)
    op_Addition UnitsWithTrait(AdjacentFriends(Owner, 1, 3), 0x41d = Decoy) )` -- le cardinal que
    `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
    GetAdjacentFriendlySummonsAndDecoysCount` calcule pour le PORTEUR de l'effet.

    DEUX consommateurs natifs, un seul foyer ici (le natif appelle LA MEME methode des deux cotes) :
      * `...$$CreateActiveCondition` = `AmountIsGreaterThanZero(<ce compteur>)` ;
      * `...$$GetCritDmgReductionAmount` = `Multiply(ConfigVar(0x97), <ce compteur>)`.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/amulet_of_the_voidwyrm.py::
    adjacent_friendly_summons_and_decoys_selector`, doctrine #149 : l'artefact natif est un
    SELECTEUR) ; ce qu'on fait ICI, c'est lui donner son `AbilityEntities` -- `entities_from_state(
    state, unit_id)` pose `caster = owner = le porteur`, `board = state.board` et `has_trait`.

    ⚠ SUBSTRAT D'ADJACENCE : la LISTE STOCKEE -- et **le paragraphe qui vivait ici disait
    l'inverse** (#589-r1-r1-r2-r1-r8). Il affirmait, sur la foi de `case-589-r1-r1-r2-r1` sec.6,
    que le natif comptait un voisin a `hexgeo.distance == 1` ABSENT de la liste stockee, donc que
    `AdjacentTilesSelector` et `BattleQuery$$IterateAdjacentTiles` ne lisaient pas le meme
    substrat. Les DEUX affirmations sont REFUTEES :

      * le chemin est UNIQUE -- `AdjacentTiles` -> `AdjacentTilesSelector$$Select` -> `IBattleQuery`
        **slot 80** = `IterateAdjacentTiles` (slot LU dans `metadata/interface_slots.tsv`), et
        `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere
        une LISTE STOCKEE (`tile.<+0x30>.<+0x10>`), sans aucune geometrie ;
      * le natif ne comptait PAS ce voisin. L'activite mesuree venait de `genesSmnDecoy` -- unite
        AMIE a trait `Decoy`, presente AU DEPLOIEMENT sur un voisin STOCKE du porteur, que le
        montage n'avait jamais inventoriee. Mesure differentielle (une seule unite bouge) et
        compteur lu du DEGAT : intrus seul = 1, intrus + compagnon hex-1 hors liste stockee =
        **1** aussi -- il n'ajoute rien.

    Le port suit donc la liste stockee (`dsl/base.py::_within`, `order='adjacent'`, #515), et c'est
    exact. Detail : `docs/rl/case-589-r1-r1-r2-r1-r8-unite-sans-sante.md`.

    `None` si le porteur n'a ni equipe ni tuile (cle alors ABSENTE du `unit_state` => la
    `CreateActiveCondition` degrade en VRAI, et le canal crit ne contribue RIEN) -- jamais un 0
    invente, qui annulerait le produit et ferait passer une reduction reelle pour une absence."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_friendly_summons_and_decoys_selector()
               .calculate(entities_from_state(state, int(unit_id))))


def adjacent_enemies_count(state, unit_id: int) -> Optional[int]:
    """`Count( AdjacentEnemies(Owner, unique: 1, selectionType: 3) )` -- le cardinal que
    `IdunBattle.Entities.Effects.Loki.SupaCyborkBody_CritDmgReductionEffect$$GetCalculateLevel`
    calcule pour le PORTEUR de l'effet.

    DEUX consommateurs natifs, un seul foyer ici -- et c'est le meme fait geometrique des deux
    cotes, donc la CONDITION et la MAGNITUDE ne peuvent pas diverger :
      * `...$$CreateActiveCondition` = `HasAdjacentEnemies(Owner, Tiles(Owner))` ;
      * `...$$GetCalculateLevel`     = `Count(<ce selecteur>)`, et c'est cette valeur que
        `RefreshEffectsOperation$$UpdateLevel` ECRIT dans `EffectComponent+0x68`, donc celle que
        `DSLFormulas.EffectLevel` relit dans `$$GetCritDamageReduction`.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/supa_cybork_body.py::
    adjacent_enemies_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = le porteur`,
    `board = state.board` et `has_trait`.

    `None` si le porteur n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par equipe) --
    jamais un 0 invente, qui annulerait le produit et ferait passer une reduction reelle pour une
    absence de reduction (meme tri-etat que le compteur d'`AmuletOfTheVoidwyrm` ci-dessus)."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_enemies_selector().calculate(entities_from_state(state, int(unit_id))))


def adjacent_enemy_ids(state, unit_id: int) -> "Optional[frozenset]":
    """`AdjacentEnemies( Owner@DSLSelectors+0x30, unique: true,
    UnitSelectionType.OnlyAliveAndTargetable = 3 )` -- les IDS, pas le cardinal (#954).

    C'est le `CreateTargetSelector` PARTAGE des deux effets d'`ObsessiveAnnunciation` (`1432` et
    `1433`, corps FONDU par l'ICF). Les DEUX canaux qui les consomment interrogent une APPARTENANCE
    (`get_OwnerIsTarget` = << la cible du coup est-elle l'une des cibles de l'effet ? >>), pas un
    compte -- d'ou cet accesseur distinct d'`adjacent_enemies_count` juste au-dessus, qui appelle
    un AUTRE arbre (celui de `supa_cybork_body`, `selection_type` non porte).

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/obsessive_annunciation.py::
    adjacent_enemies_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = le porteur`,
    `board = state.board` et `has_trait`.

    SUBSTRAT D'ADJACENCE : la LISTE STOCKEE (`dsl/base.py::_within`, `order='adjacent'`, #515), le
    MEME que tous les ring-1 du depot -- donc AVEC la porte d'elevation du natif
    (`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`), et non un
    `hexgeo.distance == 1` qui SUR-COMPTE au bord d'une marche (#271).

    `None` si le porteur n'a ni equipe ni tuile -- jamais un ensemble VIDE invente, qui ferait
    passer << non mesure >> pour << aucune cible >> et eteindrait le bonus en silence."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    ents = entities_from_state(state, int(unit_id))
    out = set()
    for u in (obsessive_annunciation_target_selector().select(ents) or ()):
        uid = u.get("id") if isinstance(u, dict) else None
        if uid is not None:
            out.add(int(uid))
    return frozenset(out)


def adjacent_unit_ids(state, unit_id: int) -> "Optional[frozenset]":
    """`AdjacentUnits( <unit_id>, unique: true, UnitSelectionType.OnlyAliveAndTargetable = 3 )`
    -- les IDS des unites voisines, SANS aucun filtre d'equipe (#1025-r1).

    C'est le noeud d'adjacence partage par les DEUX branches du `$$CreateTargetSelector` de
    `IdunBattle.Entities.Effects.Loki.MoreGitzOverEre_ExtraDamagePctEffect` ; le filtre `Friends(
    Owner, ...)` que le natif applique ENSUITE depend du PORTEUR de l'effet, donc il est rejoue par
    la classe d'effet (l'agregateur d'aura pose `owner_team` dans son ctx par-carrier), pas ici.
    Voisin exact d'`adjacent_enemy_ids` ci-dessus, moins le filtre d'equipe.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/extra_damage_aura.py::
    more_gitz_adjacent_units_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = unit_id`,
    `board = state.board` et `has_trait`. SUBSTRAT D'ADJACENCE : la LISTE STOCKEE
    (`dsl/base.py::_within`, `order='adjacent'`), donc AVEC la porte d'elevation du natif
    (`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`).

    `None` si l'unite n'a ni equipe ni tuile -- jamais un ensemble VIDE invente, qui ferait passer
    << non mesure >> pour << aucun voisin >> et rendrait le gate FAUX en silence."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    ents = entities_from_state(state, int(unit_id))
    out = set()
    for u in (more_gitz_adjacent_units_target_selector().select(ents) or ()):
        uid = u.get("id") if isinstance(u, dict) else None
        if uid is not None:
            out.add(int(uid))
    return frozenset(out)


def adjacent_mechanical_friends_count(state, unit_id: int) -> Optional[int]:
    """`Count( MechanicalUnits(AdjacentFriends(Owner, unique: 1, selectionType: 3), 3) )` -- le
    cardinal que `IdunBattle.Entities.Effects.Loki.KardiocoreGalvanus_ExtraCritDmgEffect$$
    GetCalculateLevel` calcule pour le PORTEUR de l'effet (#909).

    UN SEUL consommateur natif, contrairement a ses voisins de forme : la `CreateActiveCondition`
    de cet effet est `<DSLTriggers+0x70>` = `YesTrigger` (constante VRAIE), donc rien ne compare ce
    compteur a zero. Il ne sert qu'a la MAGNITUDE :
      * `...$$GetCalculateLevel` = `Count(<ce selecteur>)`, et c'est cette valeur que
        `RefreshEffectsOperation$$UpdateLevel` ECRIT dans `EffectComponent+0x68`, donc celle que
        `DSLFormulas.EffectLevel` relit dans `$$GetExtraCritAmount`.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/kardiocore_galvanus.py::
    adjacent_mechanical_friends_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = le porteur`,
    `board = state.board` et `has_trait`.

    `None` si le porteur n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par equipe) --
    jamais un 0 invente, qui annulerait le produit et ferait passer un bonus reel pour une absence
    de bonus (meme tri-etat que les autres compteurs de ce foyer)."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_mechanical_friends_selector()
               .calculate(entities_from_state(state, int(unit_id))))


def adjacent_summons_count(state, unit_id: int) -> Optional[int]:
    """`Count( Unique( UnitsWithTrait(AdjacentUnits(Owner, unique: 1, selectionType: 3),
    0x2 = Summon, selectionType: 3) ) )` -- le cardinal que
    `IdunBattle.Entities.Effects.Loki.MawClawsOfThyrax_ExtraCritDmgEffect$$GetCalculateLevel`
    calcule pour le PORTEUR de l'effet (#920).

    DEUX consommateurs natifs, un seul foyer ici (le natif appelle LE MEME slot virtuel `+0x5f8`
    des deux cotes, donc la CONDITION et la MAGNITUDE ne peuvent pas diverger) :
      * `...$$CreateActiveCondition` = `AmountIsGreaterThanZero(<vslot +0x5f8>)` ;
      * `...$$GetExtraCritAmount`    = `Multiply(ConfigVar(0x42), EffectLevel(Effect@+0x38))`, et
        c'est cette valeur que `RefreshEffectsOperation$$UpdateLevel` ECRIT dans
        `EffectComponent+0x68`, donc celle que `DSLFormulas.EffectLevel` relit.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/maw_claws_of_thyrax.py::
    adjacent_summons_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = le porteur`,
    `board = state.board` et `has_trait`.

    ⚠ GATE DE PRESENCE : la POSITION SEULE, pas l'equipe -- et c'est ce qui le distingue des trois
    compteurs ci-dessus. Le selecteur natif est `AdjacentUnits`, dont le corps est
    `op_Subtraction(Units(AdjacentTiles(origin), unique, sel), origin)` : aucun `Friends`, aucun
    `Enemies`, donc rien n'y depend de l'`OwnerComponent`. Exiger une equipe rendrait `None` la ou
    le natif compte, sur un porteur sans proprietaire connu.

    `None` si le porteur n'a pas de tuile (le selecteur est GEOMETRIQUE) -- jamais un 0 invente,
    qui annulerait le produit et ferait passer un bonus reel pour une absence de bonus (meme
    tri-etat que les autres compteurs de ce foyer)."""
    ent = state.get_entity(unit_id)
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_summons_selector()
               .calculate(entities_from_state(state, int(unit_id))))


def debuffed_units_in_range_count(state, unit_id: int) -> Optional[int]:
    """`Min( Count( EntitiesWithAnyEffect( SurroundingUnits(Tiles(Owner), range = 2, unique: 1,
    includeCenter: 1, selectionType: 3), [Pinned, Stunned, Taunted_OnlySpecificTargets,
    ThrillSeekers] ) ), Get(nrOfUnits = 6) )` -- le cardinal PLAFONNE que
    `IdunBattle.Entities.Effects.Loki.IntoxicatingElixir_ExtraCritDmgEffect$$GetCalculateLevel`
    calcule pour le PORTEUR de l'effet.

    DEUX consommateurs natifs, un seul foyer ici -- donc CONDITION et MAGNITUDE ne peuvent pas
    diverger (le natif appelle LITTERALEMENT la meme `$$GetLevelFormula`, avec le meme
    `Tiles(Owner)`) :
      * `...$$CreateActiveCondition` = `AmountIsGreaterThanZero(<ce compte>)` ;
      * `...$$GetCritAmount` = `Multiply(Multiply(ConfigVar(0x42), EffectLevel(Effect@+0x38)),
        ConditionalAmount(...))`, et c'est ce compte que `RefreshEffectsOperation$$UpdateLevel`
        ECRIT dans `EffectComponent+0x68`, donc celui que `DSLFormulas.EffectLevel` relit.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/intoxicating_elixir.py::
    debuffed_units_in_range_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = le porteur`,
    `board = state.board` et `has_effect`.

    ⚠ GATE DE PRESENCE : la POSITION SEULE, comme `adjacent_summons_count` juste au-dessus et
    contrairement aux TROIS autres compteurs de ce foyer. La raison est LUE et c'est la meme :
    `SurroundingUnits` n'a AUCUN filtre d'equipe (amis ET ennemis comptent), la ou
    `AdjacentFriends`/`AdjacentEnemies` en ont un. Exiger en plus une equipe rendrait `None` la ou
    le natif rend un compte.

    ⚠ Le predicat `HasOneOfEffects` du selecteur passe par `ctx.has_effect`, qui retombe sur
    `EffectsState.has_effect` (filtre `consumed` seulement) et NON sur `active_effects` : ce lecteur
    alimente justement le `unit_state` des `is_active`, donc l'appeler bouclerait -- meme arbitrage
    qu'`adjacent_taunted_enemies_count` ci-dessous.

    `None` si le porteur n'est pas SUR le plateau (le selecteur est GEOMETRIQUE) -- jamais un 0
    invente, qui annulerait le produit et ferait passer un bonus reel pour une absence de bonus."""
    ent = state.get_entity(unit_id)
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(debuffed_units_in_range_selector()
               .calculate(entities_from_state(state, int(unit_id))))


def adjacent_taunted_enemies_count(state, unit_id: int) -> Optional[int]:
    """`Count( Filter( AdjacentEnemies(Owner, unique: 1, selectionType: 3),
                       HasEffect(It, 27 Taunted_OnlySpecificTargets, onlyActive: 0) ) )` -- le
    cardinal que `IdunBattle.Entities.Effects.Loki.ADaemonicPatronsEffect$$
    GetNumAdjacentTauntedEnemies` calcule pour le PORTEUR de l'effet (#911).

    DEUX consommateurs natifs, un seul foyer ici -- donc CONDITION et MAGNITUDE ne peuvent pas
    diverger, exactement comme pour `adjacent_enemies_count` ci-dessus :
      * `ADaemonicPatronsEffect$$CreateActiveCondition` = `AmountIsGreaterThanZero(<ce compte>)` ;
      * `DaemonicPatrons_ExtraDamageEffect$$GetCurrentExtraDamage` = `ConfigVar(extraDmg) x <ce
        compte>`, et `DaemonicPatrons_DmgReductionEffect$$GetCurrentDamageReduction` =
        `Min(100, ConfigVar(dmgReductionPct) x <ce compte>)`.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/daemonic_patrons.py::
    adjacent_taunted_enemies_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = le porteur`.

    ⚠ Le predicat `HasEffect` du filtre passe par `ctx.has_effect`, qui retombe sur
    `EffectsState.has_effect` (filtre `consumed` seulement) et NON sur `active_effects` : c'est
    voulu et documente sur `has_effect_of_type` -- ce lecteur alimente justement le `unit_state` des
    `is_active`, donc l'appeler bouclerait. Ca colle par ailleurs au `onlyActive: 0` du natif.

    `None` si le porteur n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par equipe) --
    jamais un 0 invente, qui annulerait les deux produits et ferait passer un buff reel pour une
    absence de buff."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_taunted_enemies_selector()
               .calculate(entities_from_state(state, int(unit_id))))


def adjacent_friendly_mechanical_units_count(state, unit_id: int) -> Optional[int]:
    """`Count( MechanicalUnits( NormalUnits( AdjacentFriends(Owner, unique: 1, selectionType: 3),
    3 ), 3 ) )` -- le cardinal que `IdunBattle.Entities.Effects.Loki.
    NetherRealmCasket_CritDamageReductionEffect$$AdjacentMechanicalUnits` calcule pour le PORTEUR
    de l'effet (#908).

    TROIS consommateurs natifs, un seul foyer ici (le natif appelle LA MEME methode -- slot virtuel
    `+0x5f8` -- dans les trois cas), donc la CONDITION et la MAGNITUDE ne peuvent pas diverger :
      * `...$$CreateActiveCondition`  = `AmountIsGreaterThanZero(<ce compteur>)` ;
      * `...$$CreateCritDamageBonus`  = `ForSubtraction(get_OwnerIsTarget,
                                          Multiply(ConfigVar(0x97), <ce compteur>))` ;
      * `...$$GetCalculateLevel`      = `<ce compteur>` (niveau d'affichage, non porte).

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/nether_realm_casket.py::
    adjacent_mechanical_units_selector`, doctrine #149 : l'artefact natif est un SELECTEUR) ; ce
    qu'on fait ICI, c'est lui donner son `AbilityEntities` -- `entities_from_state(state, unit_id)`
    pose `caster = owner = le porteur`, `board = state.board` et `has_trait`.

    ⚠ `MechanicalUnits` delegue a `UnitExtensions$$IsMechanical` = `HasTrait(Mechanical 5) ||
    HasTrait(LivingMetal 1000) || HasTrait(Vehicle 1029)` -- et c'est load-bearing sur le camp de
    cette relique : tout le roster necron porte `LivingMetal`, plusieurs SANS `Mechanical`.

    `None` si le porteur n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par equipe) --
    jamais un 0 invente, qui annulerait le produit et ferait passer une reduction reelle pour une
    absence de reduction (meme tri-etat que les deux compteurs ci-dessus)."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_mechanical_units_selector()
               .calculate(entities_from_state(state, int(unit_id))))


def adjacent_dark_angels_friends_count(state, unit_id: int) -> Optional[int]:
    """`Count( UnitsFromFaction( AdjacentFriends(Owner, unique: 1, selectionType: 3),
    UnitFaction.DarkAngels = 0xa, selectionType: 3 ) )` -- le cardinal du SECOND disjoint de
    `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$GetDoubleEffectCondition`, calcule pour le
    PORTEUR de l'effet (#932).

    UN SEUL foyer pour les DEUX faces de degat (`CreateEffectDamageBonusForAttack` et
    `CreateEffectDamageMalusForDefense` appellent le MEME `GetDoubleEffectCondition`, a l'argument
    `isDefense` pres qui ne change QUE l'entite comparee -- jamais ce compteur) : la condition
    d'ATTAQUE et celle de DEFENSE ne peuvent donc pas diverger.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/deathwing.py::
    adjacent_dark_angels_friends_selector`, doctrine #149 : l'artefact natif est un SELECTEUR) ; ce
    qu'on fait ICI, c'est lui donner son `AbilityEntities` -- `entities_from_state(state, unit_id)`
    pose `caster = owner = le porteur`, `board = state.board` et `faction_of`.

    ⚠ `UnitsFromFaction` compare le `FactionId` gameconfig au NOM de la valeur d'enum : c'est ce que
    le natif fait (`System.Enum.ToString(UnitFaction)` puis `String.Equals` sur
    `FactionComponent+0x30`), pas une comparaison d'ordinal.

    `None` si le porteur n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par equipe) --
    jamais un 0 invente, qui fermerait le disjoint en silence et ferait passer un doublement reel
    pour son absence (meme tri-etat que les compteurs voisins)."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_dark_angels_friends_selector()
               .calculate(entities_from_state(state, int(unit_id))))


def synaptic_insight_adjacent_tyranid(state, owner_id: int, target_id) -> "Optional[bool]":
    """`Any( AdjacentFriends(unit = Owner@<DSLSelectors+0x30>, unitTile = Target@<DSLSelectors+0x60>,
    unique: true), HasFaction(ActiveTarget@<DSLSelectors+0x68>, UnitFaction.Tyranids = 0xc, 3) )` -- le PREMIER
    disjoint de `IdunBattle.Entities.Effects.Loki.SynapticInsight_ExtraHitsEffect$$
    CreateEffectHitsBonusForAttack`, evalue pour le couple (PORTEUR, CIBLE DU COUP) (#1073).

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/synaptic_insight.py::
    adjacent_tyranid_friend_trigger`, doctrine #149 : l'artefact natif est un SELECTEUR sous un
    trigger existentiel) ; ce qu'on fait ICI, c'est lui donner son `AbilityEntities` --
    `entities_from_state(state, owner_id, target_id)` pose `caster = owner = le porteur`
    (le repli documente d'`entities/selectors/accessors.Owner` est EXACT ici, le trigger natif
    portant `get_OwnerIsCaster`), `target = la cible du coup`, `board = state.board` et `faction_of`.

    ⚠ **L'ANCRE GEOMETRIQUE EST LA CIBLE**, pas le porteur -- c'est la variante B d'`AdjacentFriends`
    (`unit`, `unitTile`, `unique`), tranchee par la CIBLE du `call rel32` et non par l'arite (les
    deux surcharges en ont la meme). Ce contraste avec `adjacent_dark_angels_friends_count`
    ci-dessus, qui ancre sur le PORTEUR, est la raison d'etre du second parametre.

    ⚠ Le PORTEUR n'est pas exclu de l'ensemble : le natif ne soustrait que `unitTile` (la cible).
    Un porteur Tyranide adjacent a sa propre cible arme donc le disjoint tout seul -- LU, pas deduit.

    `None` si le porteur ou la cible n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par
    equipe) -- jamais un `False` invente, qui fermerait le disjoint en silence et ferait passer un
    bonus reel pour son absence (meme tri-etat que les compteurs voisins)."""
    if target_id is None:
        return None
    for uid in (owner_id, target_id):
        ent = state.get_entity(int(uid))
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        pc = ent.get_component(PositionComponent) if ent is not None else None
        if oc is None or oc.team is None or pc is None:
            return None
    from .abilities.behaviours.context import entities_from_state
    return bool(_si.adjacent_tyranid_friend_trigger()
                .evaluate(entities_from_state(state, int(owner_id), int(target_id))))


def enmity_adjacent_units_count(state, unit_id: int) -> Optional[int]:
    """`Count( NonSteppableOrObjectUnits( AdjacentUnits(Owner, unique: 1, selectionType: 3), 3 ) )`
    -- `IdunBattle.Entities.Effects.Loki.EnmityForTheUnworthy_ExtraDamagePctEffect$$
    AdjacentUnitsAmount`, calcule pour le PORTEUR de l'effet (#948).

    UN SEUL foyer pour la `CreateActiveCondition` ET la magnitude : le natif appelle le MEME
    `AdjacentUnitsAmount` depuis `CreateActiveCondition` et depuis `CurrentDamagePct`, donc les deux
    ne peuvent pas diverger.

    L'ARBRE est celui de la classe d'effet (`entities/effects/loki/enmity_for_the_unworthy.py::
    adjacent_units_selector`, doctrine #149 : l'artefact natif est un SELECTEUR) ; ce qu'on fait ICI,
    c'est lui donner son `AbilityEntities` -- `entities_from_state(state, unit_id)` pose
    `caster = owner = le porteur`, `board = state.board` et `has_trait`.

    ⚠ AUCUN filtre d'equipe : `AdjacentUnits` compte les AMIS **et** les ENNEMIS (le natif
    `op_Subtraction(Units(AdjacentTiles(origin), ...), origin)` ne retire que le porteur lui-meme).
    C'est ce qui le distingue de son jumeau `enmity_adjacent_dark_angels_friends_count` ci-dessous.

    `None` si le porteur n'a pas de tuile (le selecteur est GEOMETRIQUE) -- jamais un 0 invente, qui
    ferait passer un bonus reel pour son absence (meme tri-etat que les compteurs voisins)."""
    ent = state.get_entity(unit_id)
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(_enmity.adjacent_units_selector().calculate(
        entities_from_state(state, int(unit_id))))


def close_combat_weakness_adjacent_enemies_count(state, unit_id: int) -> Optional[int]:
    """`Count( UnitsWithoutTrait( UnitsWithoutTrait( Enemies(of: unit, AdjacentUnits(unitTile,
    unique: 1, 3), 3 ), Object = 0xd, 3 ), Steppable = 0x1b, 3 ) )` -- le corps de
    `IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies(unit, unitTile, includeObjects: false,
    includeSteppables: false)` SANS son etage terminal `AmountIsEqualOrGreater(..., Direct(1))`, que
    le consommateur applique (`>= 1`). Face COMBAT du canal
    `att_ctx["close_combat_weakness_adjacent_enemies"]` (#1015-r1).

    L'ARBRE vit dans la classe d'effet (`entities/effects/loki/close_combat_weakness.py::
    has_adjacent_enemies_selector`, doctrine #149) ; ce qu'on fait ICI, c'est lui donner son
    `AbilityEntities` -- `entities_from_state(state, unit_id)` pose `caster = owner = le porteur`,
    exactement ce que `NearbyEnemiesCondition` demande (`Caster@+0x48` et `CasterTile@+0x50`, qui
    sur ce canal designent tous deux l'attaquant).

    `None` si le porteur n'a pas de tuile (le selecteur est GEOMETRIQUE) ni d'equipe (l'etage
    `Enemies` en a besoin) -- jamais un 0 invente, qui ferait passer un malus reel pour son absence
    (meme tri-etat que les compteurs voisins)."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return len(_ccw.has_adjacent_enemies_selector().evaluate(
        entities_from_state(state, int(unit_id))) or ())


def enmity_adjacent_dark_angels_friends_count(state, unit_id: int) -> Optional[int]:
    """`Count( NonSteppableOrObjectUnits( UnitsFromFaction( AdjacentFriends(Owner, unique: 1, 3),
    UnitFaction.DarkAngels = 0xa, 3 ), 3 ) )` -- `IdunBattle.Entities.Effects.Loki.
    EnmityForTheUnworthy_ExtraDamageEffect$$AdjacentFriendlyDarkaUnitsAmount` (#948).

    ⚠ CE N'EST PAS `adjacent_dark_angels_friends_count` (#932, Deathwing), qui s'arrete a
    `UnitsFromFaction` : l'etage `NonSteppableOrObjectUnits` (= retirer les traits `Steppable` 0x1b
    et `Object` 0xd) est PROPRE a Enmity, il est LU dans son decompile. Deux arbres distincts, deux
    compteurs distincts -- les confondre porterait un ordinal juste sur un arbre faux.

    `None` si le porteur n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par equipe) --
    jamais un 0 invente."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(_enmity.adjacent_dark_angels_friends_selector().calculate(
        entities_from_state(state, int(unit_id))))


def hunter_of_souls_adjacent_psyker_friends_count(state, unit_id: int) -> Optional[int]:
    """`Count( UnitsWithTrait( AdjacentFriends(Owner@<DSLSelectors+0x30>, unique: 1, 3),
    UnitTrait.Psyker = 0x3ea, 3 ) )` -- `IdunBattle.Entities.Effects.Loki.
    HunterOfSouls_ExtraDamageEffect$$GetUnits` (#1078-r3).

    ⚠ CE N'EST PAS `enmity_adjacent_dark_angels_friends_count` (#948) : le compteur d'Enmity passe
    par `NonSteppableOrObjectUnits` et filtre par FACTION, celui-ci filtre par TRAIT et n'a AUCUN
    etage de retrait -- les deux absences sont LUES au decompile, pas supposees. Les confondre
    sous-compterait les amis Psyker `Steppable`/`Object`, que le natif COMPTE.

    `None` si le porteur n'a ni equipe ni tuile (le selecteur est GEOMETRIQUE **et** par equipe) --
    jamais un 0 invente, qui eteindrait le bonus en silence."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if oc is None or oc.team is None or pc is None:
        return None
    from .abilities.behaviours.context import entities_from_state
    return int(adjacent_psyker_friends_selector().calculate(
        entities_from_state(state, int(unit_id))))


class UnitEffectStateView(Mapping):
    """Le `unit_state` d'une unité — vue MAPPING PARESSEUSE sur l'ECS (`unit_state_for_effects`).

    Clés (chacune n'est PRÉSENTE que si l'ECS peut la renseigner — une clé ABSENTE = « donnée
    inconnue », et c'est ce que chaque `is_active` traite en dégradation fidèle) :

      * `hp` / `max_hp` — `HealthComponent` ; lus par les conditions `StatAmount(Self, HEALTH,
        CURRENT/CURRENT_PCT)` (`AnvilShield_BlockChanceBelowHealthCap`, `PowerTrip_FullHealth`) ;
      * `traits` — `StatsComponent.ctx.traits` (NOMS gameconfig, même convention que tous les
        `HasTrait(...)` portés) ; lus par les conditions de TRAIT
        (`PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, 0x40f = TerminatorArmour))`) ;
      * `enemy_psykers_alive` — cardinal battlefield-wide, PARESSEUX (O(entités), cf.
        `enemy_psykers_alive`) : il n'est calculé que si un effet le LIT réellement. La clé est
        présente dès que l'équipe du porteur est connue, absente sinon.
      * `tiles_moved_this_turn` — `ActorStatisticsComponent+0xf0` (`unit_tiles_moved_this_turn`) ;
        lu par `ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` =
        `AmountIsGreaterThanZero(TilesMovedThisTurn(Self))`. La cle n'est presente que si l'entite
        a un `UnitComponent` : cote COMBAT le compteur est DESORMAIS mesure (`record_tiles_moved`
        est appele par `MoveUnitOperation`), donc `is_active` rend le gate natif VERBATIM au lieu
        de la degradation « non mesure -> on ne ferme pas ». Cote DECISION la `Scene` ne pose PAS
        cette cle : elle evalue l'etat SIMULE et le compte y vient du `att_ctx`, pas du porteur.
      * `has_moved` — `HasFlag(Self, 0 = UnitFlag.Moved)` (`unit_has_moved`, LECTEUR UNIQUE du
        `UnitFlagsComponent`) ; lu par `InescapableAccuracy_ExtraCritChanceEffect$$
        CreateActiveCondition` = `op_LogicalNot(HasFlag(Owner, 0))`. La cle n'est presente que si
        l'entite existe ; le composant absent vaut « n'a pas bouge » (comme le natif, dont le
        `UnitFlagsComponent$$Has` sur un set vide rend faux).
      * `is_turn_of_owner` — `IsTurnOf(Owner)` = `<DSLTriggers+0x28>`, MEME noeud natif que le canal
        `att_ctx["is_turn_of_owner"]` (foyer `entities/effects/base.py::is_turn_of_owner`) : ici
        `OwnerComponent.player == State.current_player_id`, mirror de
        `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`. Lu par
        `MartialSuperiority_VisualEffect$$CreateActiveCondition` = `op_LogicalNot(...)`. La cle
        n'est presente que si le proprietaire ET le joueur courant sont connus ; absente = « non
        mesure » -> la condition degrade en VRAI.
      * `has_effect_light_cover` / `is_target_of_big_target_adjacent` — les DEUX membres du
        `op_BitwiseOr` de `IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$
        HasValidEffectTrigger` (`HasEffect(sel, 1013, onlyActive=0, 6)` /
        `IsEffectTarget(sel, 1026)`), lus par la `CreateActiveCondition` de `1014
        CamoCloak_DmgReduction`. PARESSEUX (chacun balaie : `EffectsState` pour le premier, les
        entites ring-1 pour le second). Le premier est present des que le state porte une
        `EffectsState`, le second des que l'unite est SUR le plateau (le selecteur natif est un
        `AdjacentFriends`, il n'a pas de sens hors position). Cle absente = donnee non threadee ->
        `camo_cloak_cover` degrade en VRAI (« present == actif »), jamais en FAUX.
      * `contagions_of_nurgle_amount` — **un CALLABLE** `(source_unit_id) -> int | None`, et non une
        valeur : le nœud natif `ContagionsOfNurgleAmount(team, unit)` prend l'EFFECT SOURCE en
        entrée, donc le cardinal dépend de l'INSTANCE d'effet qui l'interroge, pas seulement du
        porteur. Paresseux par construction (rien n'est calculé tant qu'aucune instance n'appelle),
        et présent dès que l'unité a une position.
      * `structural_analyser_friends` — cardinal battlefield-wide, PARESSEUX (O(entités), cf.
        `structural_analyser_friends`) : le sélecteur `AdjacentFriends + UnitsFromFaction(
        SurroundingFriends(2), Tau)` que `AmountIsGreaterThanZero` compare à 0 dans
        `IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect$$CreateActiveCondition`
        (case-366-r1). La clé est présente dès que le porteur a une équipe ET une tuile.
      * `adjacent_friendly_summons_and_decoys` — cardinal PARESSEUX (O(entités), cf.
        `adjacent_friendly_summons_and_decoys_count`) : l'arbre `Count(UnitsWithTrait(
        AdjacentFriends(Owner), Summon) + UnitsWithTrait(AdjacentFriends(Owner), Decoy))` que
        `AmountIsGreaterThanZero` compare à 0 dans
        `IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
        CreateActiveCondition` (#589-r1-r1-r2-r1). Le pendant `debuffed_units_in_range` porte
        l'arbre `Min(Count(EntitiesWithAnyEffect(SurroundingUnits(Tiles(Owner), 2, includeCenter:
        1, sel 3), [Pinned, Stunned, Taunted_OnlySpecificTargets, ThrillSeekers])), nrOfUnits)` de
        `IntoxicatingElixir_ExtraCritDmgEffect$$CreateActiveCondition` — MAIS son gate de présence
        est `_has_pos` SEUL, pas `_has_sa` : ce sélecteur-là n'a AUCUN filtre d'équipe.
        Le pendant `adjacent_friendly_mechanical_units`
        (#908) porte l'arbre `Count(MechanicalUnits(NormalUnits(AdjacentFriends(Owner, 1, 3), 3),
        3))` de `NetherRealmCasket_CritDamageReductionEffect$$CreateActiveCondition`, avec le MEME
        gate de presence. MÊME gate de présence que la clé ci-dessus
        (sélecteur géométrique ET par équipe) : présente dès que le porteur a une équipe ET une tuile.
      * `adjacent_summons` — cardinal PARESSEUX (O(entités), cf. `adjacent_summons_count`) :
        l'arbre `Count(Unique(UnitsWithTrait(AdjacentUnits(Owner, 1, 3), Summon, 3)))` que
        `AmountIsGreaterThanZero` compare à 0 dans
        `IdunBattle.Entities.Effects.Loki.MawClawsOfThyrax_ExtraCritDmgEffect$$CreateActiveCondition`
        (#920). ⚠ Son gate de présence est la **POSITION SEULE**, pas l'équipe : `AdjacentUnits` ne
        filtre AUCUN camp (cf. `adjacent_summons_count`), donc exiger une équipe rendrait la clé
        absente là où le natif compte.
      * `owner_id` — l'id du PORTEUR, mirror du noeud `Owner@DSLSelectors+0x30`. Ce n'est pas une
        commodite : `IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit litteralement
        `ctx+0x18`, et `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` y ECRIT
        l'owner -- c'est donc l'un des QUATRE champs que le contexte natif d'une
        `CreateActiveCondition` renseigne. Lu par les conditions qui COMPARENT une entite au
        porteur (`MindControl_TaunterEffect$$CreateActiveCondition` = `AreEqual(...,
        Owner@+0x30)`). EAGER, present des que l'entite existe.
      * `owned_effect_bonded_entity` — **un CALLABLE** `(unit_id, effect_type) -> int | None`
        (mirror `BondedEntityFromEffect(EffectFromOwner(...))`, cf. la fonction homonyme
        ci-dessus). Callable et non valeur pour la MEME raison que
        `contagions_of_nurgle_amount` : le noeud natif prend une ENTITE en entree, et cette entite
        vient de l'INSTANCE d'effet qui interroge (son `bonded`), pas du porteur. Present des que
        le state porte une `EffectsState`.
      * `has_effect_on` — **un CALLABLE** `(unit_id, effect_type) -> bool`, mirror de
        `HasEffect(sel, effectType, onlyActive: null, effectTargetType: 6)` porte sur une entite
        AUTRE que le porteur (la cle `has_effect_light_cover` ci-dessus est le meme noeud figé sur
        le porteur lui-meme). Meme gate de presence que la cle precedente.
      * `turns_started` — `RoundsStarted(Owner@DSLSelectors+0x30)` =
        `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` (somme de
        `UnitComponent.turnsStarted@+0x58` sur le sélecteur, ici mono-unité = le porteur), MÊME
        grandeur que `GetStat(unit, 0xc = TURNS_STARTED)` — le compteur qu'incrémente
        `StartTurnOperation` (`runner/operations/turnflow.py`). Lu par
        `IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraArmorEffect$$CreateActiveCondition`
        (corps FONDU avec celui d'`..._ExtraBlockEffect`) =
        `AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))`. EAGER (lecture de stat). La clé n'est
        présente que si l'entité porte un `StatsComponent` avec son `UnitContext`.

    La paresse n'est pas une optimisation gratuite : `active_effects` est appelé dans des boucles
    par-porteur des chemins de dégât (auras), donc un cardinal EAGER y serait quadratique."""

    __slots__ = ("_state", "_uid", "_eager", "_has_psy", "_psy", "_has_pos",
                 "_has_effstate", "_lc", "_bta", "_has_sa", "_sa", "_asd", "_ae", "_adt", "_afm",
                 "_asu", "_dbr", "_ibm", "_lwb")

    def __init__(self, state, unit_id: int) -> None:
        self._state = state
        self._uid = int(unit_id)
        ent = state.get_entity(self._uid) if state is not None else None
        eager: Dict[str, object] = {}
        # `Owner@DSLSelectors+0x30` -> `OwnerSelector$$Select` -> `ctx+0x18`, l'un des QUATRE champs
        # que `RefreshEffectsOperation$$ShouldBeActive` renseigne. EAGER : c'est l'id qu'on tient
        # deja. Cle ABSENTE si l'entite n'existe pas (la condition degrade alors en VRAI).
        if ent is not None:
            eager["owner_id"] = self._uid
        hc = ent.get_component(HealthComponent) if ent is not None else None
        if hc is not None:
            eager["hp"], eager["max_hp"] = hc.hp, hc.hp_max
        sc = ent.get_component(StatsComponent) if ent is not None else None
        traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
                  else None) or []
        if traits:
            eager["traits"] = traits
        # `TilesMovedThisTurn(Self)` = `ActorStatisticsComponent+0xf0` (cf. la docstring de classe).
        # EAGER : c'est un simple champ int deja materialise, aucun balayage.
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is not None:
            eager["tiles_moved_this_turn"] = int(uc.tiles_moved_this_turn or 0)
        # `HasFlag(Self, 0 = UnitFlag.Moved)` (cf. la docstring de classe). EAGER : `unit_has_moved`
        # est une lecture de set sur le `UnitFlagsComponent`, aucun balayage. C'est le MEME store
        # que le gate no-move deja porte sur l'axe DEGAT (`CrushingStrike`), donc les deux axes ne
        # peuvent pas diverger.
        if ent is not None:
            eager["has_moved"] = unit_has_moved(state, self._uid)
        # `RoundsStarted(Owner@DSLSelectors+0x30)` (cf. la docstring de classe). EAGER : simple
        # lecture du `StatComponent` deja materialise, aucun balayage.
        if sc is not None and getattr(sc, "ctx", None) is not None:
            eager["turns_started"] = int(sc.ctx.get_stat(int(_ST.TURNS_STARTED), 0) or 0)
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        # `IsTurnOf(Owner)` (`<DSLTriggers+0x28>`) — MEME noeud natif que le canal
        # `att_ctx["is_turn_of_owner"]` (foyer `entities/effects/base.py::is_turn_of_owner`), donc
        # MEME lecture : `OwnerComponent.player == State.current_player_id`, mirror de
        # `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`. Lu par la
        # `CreateActiveCondition` de `1255 MartialSuperiority_Visual`
        # (`op_LogicalNot(<DSLTriggers+0x28>)`). EAGER : deux lectures de champ, aucun balayage.
        # Cle ABSENTE si le proprietaire ou le joueur courant n'est pas connu = « non mesure » ->
        # la condition degrade en VRAI (on ne masque pas l'effet a tort).
        # ⚠ `oc.player` peut etre `None` MEME quand l'`OwnerComponent` existe : c'est le cas de
        # toute unite HORS PLATEAU sous un `ATeleportingEffect` (1035/1140/1238/1573), que
        # `decisionView` publie avec `visualId`, `team` ET `pos` a `null` (mesure #425/#448-r1) --
        # le seed n'a alors PAS de joueur a poser. C'est exactement le « proprietaire non connu »
        # que la ligne ci-dessus decrit : la cle doit rester ABSENTE, pas lever un `TypeError`
        # (trouve en portant `StormboyzStrike_FallbackAbility`, dont le porteur EST dans cet etat).
        cur = getattr(state, "current_player_id", None) if state is not None else None
        if oc is not None and oc.player is not None and cur is not None:
            eager["is_turn_of_owner"] = (int(oc.player) == int(cur))
        self._eager = eager
        self._has_psy = oc is not None            # `Enemies(Owner, …)` calculable
        self._psy: Optional[int] = None
        # `ContagionsOfNurgleAmount(team, unit)` : le natif `SelectSingle` la cible et sort a 0 si
        # elle n'a pas de tuile (`GetInRangeAuraAmount` deref `MainTile`) -> la cle n'existe que si
        # l'unite est SUR le plateau.
        self._has_pos = (ent is not None and ent.get_component(PositionComponent) is not None)
        # `HasEffect(sel, 1013 LightCover, onlyActive=0, 6)` : calculable des que le state porte une
        # `EffectsState` ; `IsEffectTarget(sel, 1026)` exige EN PLUS une position (selecteur ring-1).
        self._has_effstate = getattr(state, "effects", None) is not None
        self._lc: Optional[bool] = None
        self._bta: Optional[bool] = None
        # `AdjacentFriends + UnitsFromFaction(SurroundingFriends(2), Tau)` : selecteur GEOMETRIQUE
        # ET par equipe -> la cle n'existe que si le porteur a une tuile ET une equipe.
        self._has_sa = (self._has_pos and oc is not None and oc.team is not None)
        self._sa: Optional[int] = None
        # `AdjacentFriends(Owner) filtre Summon/Decoy` : MEME gate que ci-dessus (selecteur
        # geometrique ET par equipe) -> la cle n'existe que si le porteur a une tuile ET une equipe.
        self._asd: Optional[int] = None
        # `AdjacentEnemies(Owner)` : MEME gate (selecteur geometrique ET par equipe).
        self._ae: Optional[int] = None
        # `Filter(AdjacentEnemies(Owner), HasEffect(It, 27))` : MEME gate GEOMETRIQUE + EQUIPE que
        # ci-dessus. Le conjoint `EffectsState` n'est PAS ajoute au gate : le selecteur reste
        # calculable sans elle (le filtre rend alors l'ensemble VIDE, donc 0), et le natif ne
        # distingue pas les deux -- une absence d'effet EST un compte nul de tauntes.
        self._adt: Optional[int] = None
        # `MechanicalUnits(NormalUnits(AdjacentFriends(Owner)))` : MEME gate (selecteur geometrique
        # ET par equipe) -> la cle n'existe que si le porteur a une tuile ET une equipe. #908.
        self._afm: Optional[int] = None
        # `Unique(UnitsWithTrait(AdjacentUnits(Owner), Summon))` : gate GEOMETRIQUE SEUL (#920).
        # `AdjacentUnits` ne filtre AUCUN camp -> la cle existe des que le porteur a une tuile,
        # meme sans `OwnerComponent`. L'aligner sur les quatre `_has_sa` rendrait la cle absente la
        # ou le natif compte.
        self._asu: Optional[int] = None
        # `Min(Count(EntitiesWithAnyEffect(SurroundingUnits(Tiles(Owner), 2, includeCenter: 1))),
        # nrOfUnits)` : selecteur GEOMETRIQUE **SANS filtre d'equipe** -> gate `_has_pos` SEUL,
        # comme `_asu` juste au-dessus et contrairement aux quatre `_has_sa` (#922). Exiger une
        # equipe rendrait la cle ABSENTE (donc la condition VRAIE par degradation) sur une entite
        # sans `OwnerComponent.team`, la ou le natif, lui, sait compter.
        self._dbr: Optional[int] = None
        # #1015-r1 : verdict de la `CreateActiveCondition` de `1235 InstinctiveBehaviour_
        # BlockMovement`. Gate `_has_pos` SEUL (ancrage `Tiles(Owner)`, aucun filtre d'equipe).
        self._ibm: Optional[bool] = None
        self._lwb: Optional[bool] = None

    def __getitem__(self, key):
        if key in self._eager:
            return self._eager[key]
        if key == "enemy_psykers_alive" and self._has_psy:
            if self._psy is None:
                self._psy = enemy_psykers_alive(self._state, self._uid)
            return self._psy
        if key == "contagions_of_nurgle_amount" and self._has_pos:
            state, uid = self._state, self._uid
            return lambda source_id: contagions_of_nurgle_amount(state, uid, source_id)
        # `CamoCloak_DmgReductionEffect$$HasValidEffectTrigger` (case-366-r1) — les DEUX membres du
        # `op_BitwiseOr`, PARESSEUX (chacun balaie, on ne paie que si une instance 1014 les lit).
        if key == "has_effect_light_cover" and self._has_effstate:
            if self._lc is None:
                self._lc = has_effect_of_type(self._state, self._uid, int(EffectType.LightCover))
            return self._lc
        # `BondedEntityFromEffect(EffectFromOwner(<unit>, <type>))` et `HasEffect(<unit>, <type>,
        # onlyActive: null, 6)` sur une entite AUTRE que le porteur : CALLABLES, parce que l'entite
        # interrogee vient de l'INSTANCE d'effet (son `bonded`), pas du porteur (meme motif que
        # `contagions_of_nurgle_amount` ci-dessus).
        if key == "owned_effect_bonded_entity" and self._has_effstate:
            state = self._state
            return lambda uid, etype: owned_effect_bonded_entity(state, int(uid), int(etype))
        if key == "has_effect_on" and self._has_effstate:
            state = self._state
            return lambda uid, etype: has_effect_of_type(state, int(uid), int(etype))
        if key == "is_target_of_big_target_adjacent" and self._has_pos:
            if self._bta is None:
                self._bta = is_target_of_adjacent_friend_aura(
                    self._state, self._uid, int(EffectType.BigTarget_AdjacentEffect))
            return self._bta
        if key == "structural_analyser_friends" and self._has_sa:
            if self._sa is None:
                self._sa = structural_analyser_friends(self._state, self._uid)
            return self._sa
        if key == "adjacent_friendly_summons_and_decoys" and self._has_sa:
            if self._asd is None:
                self._asd = adjacent_friendly_summons_and_decoys_count(self._state, self._uid)
            return self._asd
        # `SupaCyborkBody_CritDmgReductionEffect$$CreateActiveCondition` = `HasAdjacentEnemies(
        # Owner, Tiles(Owner))` : MEME gate de presence que les deux cles ci-dessus (selecteur
        # geometrique ET par equipe) -> la cle n'existe que si le porteur a une tuile ET une equipe.
        if key == "adjacent_enemies" and self._has_sa:
            if self._ae is None:
                self._ae = adjacent_enemies_count(self._state, self._uid)
            return self._ae
        # `ADaemonicPatronsEffect$$CreateActiveCondition` = `AmountIsGreaterThanZero(Count(Filter(
        # AdjacentEnemies(Owner), HasEffect(It, 27 Taunted_OnlySpecificTargets, onlyActive: 0))))`
        # : MEME gate de presence que les trois cles ci-dessus (#911).
        if key == "adjacent_taunted_enemies" and self._has_sa:
            if self._adt is None:
                self._adt = adjacent_taunted_enemies_count(self._state, self._uid)
            return self._adt
        # `NetherRealmCasket_CritDamageReductionEffect$$CreateActiveCondition` =
        # `AmountIsGreaterThanZero(AdjacentMechanicalUnits())` : MEME gate de presence que les
        # quatre cles ci-dessus (selecteur geometrique ET par equipe). #908.
        if key == "adjacent_friendly_mechanical_units" and self._has_sa:
            if self._afm is None:
                self._afm = adjacent_friendly_mechanical_units_count(self._state, self._uid)
            return self._afm
        # `MawClawsOfThyrax_ExtraCritDmgEffect$$CreateActiveCondition` =
        # `AmountIsGreaterThanZero(<vslot +0x5f8> = Count(Unique(UnitsWithTrait(AdjacentUnits(
        # Owner, 1, 3), Summon, 3))))` : gate de presence GEOMETRIQUE SEUL (`_has_pos`), pas
        # `_has_sa` -- `AdjacentUnits` ne filtre aucun camp. #920.
        if key == "adjacent_summons" and self._has_pos:
            if self._asu is None:
                self._asu = adjacent_summons_count(self._state, self._uid)
            return self._asu
        # `IntoxicatingElixir_ExtraCritDmgEffect$$CreateActiveCondition` =
        # `AmountIsGreaterThanZero(GetLevelFormula(Tiles(Owner)))`. Gate `_has_pos` SEUL : le
        # selecteur `SurroundingUnits` n'a AUCUN filtre d'equipe (cf. le commentaire du `__init__`).
        if key == "debuffed_units_in_range" and self._has_pos:
            if self._dbr is None:
                self._dbr = debuffed_units_in_range_count(self._state, self._uid)
            return self._dbr
        # #1015-r1 -- `InstinctiveBehaviourBlockMovementEffect$$CreateActiveCondition` =
        # `IsTurnOf(Owner) & Any(Tiles(Owner), IsWalkable(It)) & AmountIsGreaterThanZero(
        #  ForcedAttackTargets(Owner)) & Any(ForcedAttackTargets(Owner),
        #  IsInAttackOrAbilityRange(Owner, It))`. L'arbre entier vit dans
        # `entities/effects/loki/instinctive_behaviour.py` (foyer de l'effet 1235) ; cette cle n'en
        # est que le POINT DE PUBLICATION, comme les six cardinaux paresseux ci-dessus.
        # Gate de presence : `_has_pos` SEUL -- la condition s'ancre sur `Tiles(Owner)` et sur les
        # cibles forcees, aucun filtre d'equipe. PARESSEUSE : l'arbre monte un `AbilityEntities`
        # complet, on ne le paie que si une instance de 1235 le lit.
        if key == "instinctive_behaviour_block_movement" and self._has_pos:
            if self._ibm is None:
                from ..entities.effects.loki.instinctive_behaviour_condition import (
                    evaluate_block_movement)
                self._ibm = bool(evaluate_block_movement(self._state, self._uid))
            return self._ibm
        # #963-r3 -- `LifewardsBondEffect$$CreateActiveCondition` = `IsAdjacent(Owner@+0x30,
        # Parent(Owner@+0x30), 3)`. Gate de presence : `_has_pos` SEUL -- la condition s'ancre sur
        # deux positions, aucun filtre d'equipe. PARESSEUSE : l'arbre monte un `AbilityEntities`
        # complet, on ne le paie que si une instance de 1060 le lit.
        if key == "lifewards_bond_adjacent_to_parent" and self._has_pos:
            if self._lwb is None:
                from ..entities.effects.loki.lifewards_condition import (
                    evaluate_lifewards_bond_adjacent)
                self._lwb = bool(evaluate_lifewards_bond_adjacent(self._state, self._uid))
            return self._lwb
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yield from self._eager
        if self._has_psy:
            yield "enemy_psykers_alive"
        if self._has_pos:
            yield "contagions_of_nurgle_amount"
            yield "is_target_of_big_target_adjacent"
            yield "adjacent_summons"                     # #920 : gate GEOMETRIQUE seul
            yield "debuffed_units_in_range"          # #922 : idem, gate GEOMETRIQUE seul
            yield "instinctive_behaviour_block_movement"  # #1015-r1 : idem, gate GEOMETRIQUE seul
            yield "lifewards_bond_adjacent_to_parent"     # #963-r3 : idem, gate GEOMETRIQUE seul
        if self._has_effstate:
            yield "has_effect_light_cover"
            yield "owned_effect_bonded_entity"
            yield "has_effect_on"
        if self._has_sa:
            yield "structural_analyser_friends"
            yield "adjacent_friendly_summons_and_decoys"
            yield "adjacent_enemies"
            yield "adjacent_taunted_enemies"
            yield "adjacent_friendly_mechanical_units"

    def __len__(self) -> int:
        # `_has_pos` en compte CINQ depuis #1015-r1 : `contagions_of_nurgle_amount`,
        # `is_target_of_big_target_adjacent`, `adjacent_summons` (#920),
        # `debuffed_units_in_range` (#922) et `instinctive_behaviour_block_movement` -- les trois
        # derniers ont un gate GEOMETRIQUE seul.
        return (len(self._eager) + (1 if self._has_psy else 0) + (5 if self._has_pos else 0)
                + (3 if self._has_effstate else 0) + (5 if self._has_sa else 0))

    def __repr__(self) -> str:                    # diagnostic (ASCII)
        return "UnitEffectStateView(u%d, %s)" % (self._uid, sorted(self))


def unit_state_for_effects(state, unit_id: int) -> UnitEffectStateView:
    """LE constructeur du `unit_state` passé à `EffectsState.active_effects` / `BaseEffect.is_active`
    (mirror du contexte d'évaluation de `RefreshEffectsOperation$$ShouldBeActive`). Tout appelant
    runner l'utilise — aucun `{"hp": ...}` ad hoc, sinon les conditions non-HP se dégradent en VRAI
    en silence (#208).

    LECTURE SEULE, et le périmètre est CLOS : `HealthComponent`, `StatsComponent.ctx.traits` (+ son
    `UnitStats`, pour la clé `turns_started` = `GetStat(., 0xc)`),
    `OwnerComponent`, `UnitComponent.alive`/`visual_id`, `PositionComponent` (les deux clés
    PARESSEUSES `contagions_of_nurgle_amount` et `structural_analyser_friends`, dont le corps ne
    s'exécute que si une instance d'effet les lit), et — depuis case-366-r1 — le
    `UnitFlagsComponent` en LECTURE SEULE via
    `unit_has_moved` (clé `has_moved`, exigée par la `CreateActiveCondition`
    `NOT HasFlag(Owner, Moved)` d'`InescapableAccuracy_extraCritChance`). Cette vue n'ÉCRIT rien :
    le seed de flags de `load_state` (`snapshot._load_unit_flags`, case-o10) reste le seul
    producteur, il n'y a donc ni double écriture ni contrainte d'ordre d'init.
    L'autre point de contact est `unit_prevents_overkill` ci-dessus, qui interroge le composant de
    flags d'ABORD et ne retombe sur la dérivation par l'effet 1354 qu'ensuite : le seed rend ce repli
    moins fréquent, il ne le rend pas faux — et il reste indispensable pour un effet posé OFFLINE en
    cours de bataille, que le snapshot n'a jamais vu."""
    return UnitEffectStateView(state, unit_id)
