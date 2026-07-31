# case-366-r1 — `1175 HatefulAssault_AlreadyAttacked` : un marqueur dont l'enjeu est l'EXPIRATION

**Question.** `1175` est classé G3 (« porteur confrontable, non porté ») par `case-366` §3.3.
Qu'est-ce qui le pose, qui le lit, et **quand se retire-t-il** ? Un marqueur qu'aucun consommateur
n'interroge est INERTE et il faut le dire ; un marqueur qui ne se retire pas est pire qu'absent.

**Livré** : la classe `UntilOfEndTurnEffect`, son trigger de retrait, et — parce que 1175 n'a de sens
qu'avec lui — le port EXÉCUTION de son poseur/lecteur `1038 HatefulAssault` (`blackTerminator`
« Angrax », HERO, dans `rl_duel build --list-pool`), qui était absent de TOUS les registres de
trigger. Face DÉCISION déjà portée depuis #193c (`HatefulAssaultPlaybook`).

Probes : `scripts/python/probe_1175_hateful_assault_marker.py` (offline, tout re-dérivé du binaire)
et `scripts/python/probe_1175_live_marker.py` (live). Garde :
`scripts/python/tests/engine/runner/test_hateful_assault_live.py`.

## 1. L'arbre natif, relu au décompilé (build `rnca9r7q6c`)

```csharp
// IdunBattleLogic.Entities.Abilities.Active.Loki.HatefulAssaultAbility$$CreateTrigger
  DSLTriggers.On(EventTriggerType.PreUnitMove = 0x1f, ownerNeedsToBeAlive: true)
& ( DSLTriggers.AreEnemies(Owner@DSLSelectors+0x30, Actor@+0x40, UnitTeamSelectionType.ByCurrentTeam)
  & DSLTriggers.IsAdjacent(Owner@+0x30, Actor@+0x40, UnitSelectionType.OnlyAliveAndTargetable) )
& NOT DSLTriggers.HasEffect(Actor@+0x40, EffectType.HatefulAssault_AlreadyAttacked = 0x497,
                            onlyActive: false, EffectTargetType.Both)
& NOT DSLTriggers.AreEqual(DSLSelectors.Tiles(Actor@+0x40), <sélecteur de tuiles @+0x78>)

// IdunBattleLogic.Entities.Abilities.Active.Loki.HatefulAssaultAbility$$CreateBehaviour
  DSLBehaviors.AttackWithAttackDamage(Owner@+0x30, Target@+0x60,
        BaseTriggeredAbility.MinMaxDamage(abilityState),
        Nullable(DamageProfileType.Power = 0xe),
        AbilityConfiguration.GetNumberConstant(AbilityConstantType.nrOfHits = 0x2f),
        AbilityOrEffect(this), options: null, UnitSelectionType.OnlyTargetable)
& DSLBehaviors.AddEffect(0x497, AbilityStateReference, targets: Target@+0x60, turns: Nullable<int> VIDE)
```

Tous les littéraux d'enum sont résolus depuis `data/symbols/<build>/frida/enums.tsv`, jamais devinés
(`0x2f = nrOfHits`, ce que confirme le gameconfig `HatefulAssault.nrOfHits = 2` ; `0xe = Power`, ce
que confirme l'i2 « Power Damage »).

**Les surcharges sont tranchées par l'ADRESSE de la cible d'appel**, pas à l'œil : `AddEffect` a
QUATRE formes, `AttackWithAttackDamage` CINQ, toutes homonymes dans le décompilé.
`probe_1175 --step 3` désassemble les deux `Create*` et rend l'adresse résolue de chaque `call`.

* `AddEffect` → la forme `(effectType, abilityState, targets, turns: Nullable<int>)`, **sans
  sélecteur `source`**. Le corps de cette surcharge passe littéralement `0` en 5ᵉ argument
  d'`AddEffectBehaviour..ctor`, et `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` fait
  alors, par cible, `source = (sélecteur source ?? la cible)` → **la source de 1175 est le MOVER**,
  pas Angrax. Sans magnitude ça ne change aucun chiffre, mais c'est observable — et « source =
  caster » aurait été une invention que rien n'aurait fait rougir.
* `AttackWithAttackDamage` → la forme à `hits: System.Int32` (constante de config, pas une formule).

## 2. L'expiration : un TRIGGER, pas un timer

La fabrique de 1175 construit `IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect`, dont **tout**
le contenu est :

```csharp
UntilOfEndTurnEffect$$.ctor(sourceAbility)
    -> BaseEffect$$.ctor(hasAutomaticActivation: true, unitEffectType: null, sourceAbility)
UntilOfEndTurnEffect$$CreateRemoveEffectTrigger()
    -> DSLTriggers$$On(EventTriggerType.TurnEnd = 0x17, ownerNeedsToBeAlive: false)
```

Aucun autre override : ni bonus d'attaque, ni malus de défense, ni stat-mod, ni `CreateActiveCondition`.
Le trigger est câblé non par l'ability mais par `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities`,
qui en fait `Triggered(<trigger>, BaseEffect$$GetRemoveEffectBehaviour())` où le behaviour est
`DSLBehaviors.RemoveEffect(Effect@DSLSelectors+0x38)`.

**Et il n'y a AUCUN timer** — les deux branches de la cascade de durée d'`AddEffectOperation$$Execute`
sont vides : le poseur passe un `turns` `Nullable<int>` VIDE, et
`idun.…StaticBattleRules.Effect$$DefaultAmountOfRounds` est un switch sur DIX valeurs
(`0x5 0x11 0x12 0x3a 0x4f 0x429 0x48a 0x4dc 0x5c4` + défaut) où **1175 n'est pas**.
⇒ `remaining = 0` = PERMANENT tant que le trigger de retrait ne tourne pas. `probe_1175 --step 4`
re-exécute ce switch depuis le désassemblage au lieu de recopier une transcription.

**Conséquence sur la faute possible.** Oublier le trigger ne donne pas « une durée approximative » :
ça donne un marqueur À VIE, donc une ability qui **cesse définitivement** de frapper toute unité déjà
touchée une fois. Ni erreur, ni test de dégât rouge — exactement le profil de régression que ce cas
devait chasser.

## 3. Qui le LIT — et la preuve que ce n'est pas inerte

`probe_1175 --step 2` balaie **tout le segment de code** à la recherche de l'immédiat 1175 (encodages
32 et 16 bits, chaque occurrence re-décodée en instruction valide). Le marqueur est lu par le
`CreateTrigger` de sa propre ability, et par lui seul. Il n'est donc pas décoratif : **il EST le gate
d'unicité** « une attaque d'opportunité par ennemi et par tour ». Sans lui, une unité qui bougerait
plusieurs fois dans le même tour se ferait frapper à chaque fois.

⚠ Le `onlyActive: false` du `HasEffect` n'est pas décoratif non plus, et il explique §4 :
`IdunBattle.Operations.AddEffectOperation$$AddNewEffect` écrit `EffectComponent` +0x10 (source),
+0x14 (owner), +0x6c (level = 1), et +0x5d/+0x60/+0x64 si `turns` a une valeur — mais **n'écrit
jamais `IsActive @+0x5c`**. Un effet frais naît INACTIF (c'est
`RefreshEffectsOperation$$RefreshEffect` qui l'active). Un gate `onlyActive: true` ne verrait pas le
marqueur qu'on vient de poser ; le natif a mis `false` pour cette raison.

## 4. Le piège de CAPTEUR, mesuré

Première mesure live (runner 634, `MC1_67`/777) : l'unité qui s'écarte d'un hex adjacent à Angrax
encaisse **1872** (2 coups Power) — le trigger fire — **et 1175 n'apparaît PAS** dans
`decisionView.units[].effects`.

Ce n'est pas une absence : `readEffectsByUnit` (`frida/hooks/game/effects.ts`) filtre
`if (info && !info.active && !includeInactive) continue`, et l'effet vient de naître inactif (§3).
Même signature que `1197` (case-231, « le capteur ne publie 1197 sur AUCUN canal »). Le capteur qui
voit la pose est le **compte d'entités-effet du plateau** (`observeBattle.counts.effects`), qui ne
filtre rien — c'est lui l'arbitre dans le probe et dans la garde.

**Lire le zéro de `decisionView` comme une absence aurait conclu « le marqueur n'est pas posé ».**

## 5. Ce qui reste OUVERT, et pourquoi ce n'est pas un aveu

**L'identité exacte de la classe n'est pas résolue statiquement.** Le slot `Il2CppClass*` de 1175 est
UNIQUE (aucun autre `EffectType` ne le partage — `probe_1175 --step 1`), mais le NOM derrière ce slot
ne se lit pas : les slots ne sont référencés que par leur propre lambda de fabrique, sans xref
discriminant. Or le corps de `.ctor` appelé est partagé par DEUX classes sœurs du binaire :

| classe | `CreateRemoveEffectTrigger` | l'`EffectType` de son slot |
|---|---|---|
| `IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect` | `On(0x17 TurnEnd)` | 1175 **ou** 1407 |
| `IdunBattle.Entities.Effects.Loki.UntilOfEndPhaseEffect` | `On(0x3a PhaseEnd)` | l'autre |

(l'autre fabrique au même nom de ctor est `1407 HypersensoryAbilities_HasBeenAttacked`, dont l'i2 dit
« **the first time each enemy turn** that Judh is attacked »).

C'est une **identité RUNTIME derrière la métadonnée IL2CPP** : le protocole dit de MESURER, pas de
deviner (`tacticus-re-port` §1.2 C.4). Le port retient `TurnEnd` (le nom du ctor appelé) et la garde
live est écrite pour **échantillonner l'état après chaque `endturn`** : disparition au premier ⇒
`TurnEnd`, survie à un tour adverse complet ⇒ `PhaseEnd`. **NON CONFRONTÉ à ce jour — fenêtre DRAIN**
(le montage était prêt et le build a été refusé `runner creation paused`).

⚠ Portée réelle de l'écart si c'était `PhaseEnd` : dans un tour de jeu ordinaire une unité ne bouge
qu'une fois, donc les deux dates produisent le **même** comportement observable ; l'écart n'apparaît
que sur une unité qui obtient un déplacement supplémentaire APRÈS la fin de son tour d'équipe. Le
verdict reste à figer, mais ce n'est pas un trou béant.

**Résidu NOMMÉ** : la classe derrière `DSLSelectors+0x78` (le second opérande de l'`AreEqual`) n'est
pas résolue — même raison (instanciée uniquement dans `InitializeShared`). Elle n'est pas
load-bearing ici : `MoveUnitOperation$$EvaluatePreMoveTriggers` construit son `AbilityEntities` avec
la MÊME liste `position` en `casterTiles` (7ᵉ arg du ctor nommé) **et** en `targetTiles` (10ᵉ), donc
les deux candidats donnent la même valeur — la destination. La sémantique du gate est donc établie :
**« la destination diffère de la tuile courante » = un vrai déplacement.** Elle le deviendrait sur un
vecteur où `CasterTiles != TargetTiles`.

## 6. Le port

| fichier | rôle |
|---|---|
| `engine/entities/effects/loki/until_of_end_turn.py` | `UntilOfEndTurnEffect` — mirror NU (zéro override, c'est fidèle) |
| `engine/runner/operations/triggers/loki/until_of_end_turn.py` | `UntilOfEndTurnRemove` (base générique) + `HatefulAssaultAlreadyAttackedRemove` |
| `engine/runner/operations/triggers/loki/hateful_assault.py` | `HatefulAssaultAttackAbility` : `matches` (collapse du `CreateTrigger`) + arbre DSL `Seq(AttackWithAttackDamage, AddEffect)` |
| `…/triggers/dispatch/registry.py` | `ABILITY_TRIGGERS["HatefulAssault"]`, `EFFECT_TRIGGERS[1175]` |
| `…/triggers/base.py`, `…/dispatch/move_death.py`, `…/operations/movement.py` | canal **`TriggerEvent.dest_tile`** |

**`dest_tile` est le seul ajout d'infrastructure.** Le vecteur `On(PreUnitMove)` du port ne portait
pas la destination ; sans elle le terme `NOT AreEqual(Tiles(Actor), <@+0x78>)` n'a rien à comparer.
Le champ mirror `casterTiles`/`targetTiles` de l'`AbilityEntities` natif, il est renseigné par
`MoveUnitOperation.execute` (seul émetteur du vecteur) et vaut `None` partout ailleurs — un
consommateur qui le lit doit DIRE ce qu'il fait de l'absence.

Écart assumé, sans effet observable : le port pose l'effet ACTIF (`AddEffectOperation(active=True)`,
raccourci historique) là où le natif le crée inactif. Le gate est `onlyActive: false` des deux côtés,
et `EffectsState.has_effect` ne filtre pas l'activité → même verdict.

`ABILITY_CLASSES` n'est pas touché (`HatefulAssault` est une triggered, pas une active castable),
donc ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` à poser. Cliquets re-joués : `probe_181` **98/98,
0 manquante** ; `probe_120 --step 0` « littéral de ctor manquant : aucun » ; `probe_273 --only-scan`
OK ; `probe_365` OK.

## 7. Compte du gisement — RE-DÉRIVÉ

Croisement des 28 ids G3 × `EffectFactory.registry` (jamais recopié) : **10 inscrits**
(`1107 1171 1175 1181 1183 1224 1251 1256 1345 1346`) ⇒ **18 restants**.
Re-dériver avant de dispatcher — deux PR parallèles ont déjà chacune écrit un compte plausible et
faux (#372/#373).
