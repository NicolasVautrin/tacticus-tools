# #577 — `AdaptiveStrategy` (active 1005, `necroWarden` « Makhotep »)

**Verdict : PORTE et CONFRONTE LIVE.** L'ability est entrée dans `ABILITY_CLASSES`
(`engine/runner/abilities/necrons.py::AdaptiveStrategyAbility`), avec son masque, son
`AbilityAttackType` et sa règle dynamique **migrés** des tables `*_UNPORTED` vers la classe
(contrat de disjonction). Garde live : `tests/engine/runner/test_577_adaptive_strategy_live.py`,
montage : `scripts/python/probe_577_adaptive_strategy.py`.

## 1. La CATÉGORIE de l'audit était fausse, et le nombre de mécaniques aussi

`combat-ability-coverage.md` classait 1005 en **EFFECT/BUFF** — colonne dérivée du `damageProfile`
de l'ARME du porteur, pas du behaviour. La lecture du décompilé donne autre chose : **1005 est un
ORDONNANCEUR**. Le cast ne frappe personne ; il override l'Attack d'un set d'alliés, les fait AGIR,
puis retire l'override. Le dégât du tooltip (« dealing 873-1164 Damage per hit **if they attack** »)
vient de l'attaque des unités activées, sous override — et « if they attack » est une **condition**,
pas une garantie : `PerformAIAction` joue une passe de décision complète, qui peut ne produire qu'un
déplacement (c'est ce qui est arrivé dans la mesure live).

**QUATRE mécaniques**, comptées sur les quatre nœuds de l'`op_Addition` final :

1. re-déclenchement **conditionnel** du passif `RelentlessMarch` du caster ;
2. **override de stat ATTACK** sur les alliés adjacents NON-Character ;
3. **action IA forcée**, une par unité, sans consommer leur tour ;
4. **retrait de l'override** — sur **tous** les alliés non-Character du plateau, pas les seuls
   adjacents.

## 2. RE — `...Loki.AdaptiveStrategyAbility$$ExecuteBehaviour` (build `rnca9r7q6c`)

```
amount   = AActiveAbility.MinMaxDamage(this, abilityState, isPrediction: FALSE)
targets  = GetNonCharacterFriendsSelector( DSLSelectors.AdjacentUnits(Caster@DSLSelectors+0x48,
                                                                     unique: 1, selType: 3) )
everyone = GetNonCharacterFriendsSelector( AllAliveUnits@DSLSelectors+0x20 )

Execute(   DSLBehaviors.If( DSLTriggers.ActorHasTriggeredAbility(Caster@0x48, 0x3ec),
                            DSLBehaviors.TriggerAbility(Caster@0x48, 0x3ec, actor: null,
                                caster: null, target: null, unitFeetTiles: null,
                                selectionType: 3, ignoreUnitHavingAbility: 0),
                            else: null )
         + DSLBehaviors.AddStatOverrideEffect(targets, 0x3f4, statType: 0, amount,
                                              turns: Nullable<int> VIDE, flag: 1)
         + DSLBehaviors.PerformAIAction(targets, asGroup: 0, resetTurnFlags: 1)
         + DSLBehaviors.RemoveEffect(everyone, Nullable<EffectType>(0x3f4),
                                     replaceableEffectType: null) )
```

`...$$GetNonCharacterFriendsSelector(units)` = `Friends(of: Owner@0x30, entities: units, selType: 3)
op_Subtraction HeroUnits(units, selType: 3)`. « Non-Character » = « pas le trait `Hero` » :
`DSLSelectors$$HeroUnits` délègue littéralement à `UnitsWithTrait(src, 0x10, selType)`.

`AActiveAbility$$MinMaxDamage(..., isPrediction: FALSE)` = `DSLFormulas.RandomAmount(
GetVariableForLevel(cfg@+0x60, 0xc = minDmg), GetVariableForLevel(cfg@+0x60, 0xd = maxDmg) )` — un
nœud à PLAGE, donc un **tirage par cible** (la feuille `AddStatOverrideEffect` évalue le montant une
fois par unité, sujet lié).

**Les trois overloads homonymes ont été tranchés par l'ADRESSE du `call`**, pas par leur signature
affichée (`DSLBehaviors$$If` a trois corps, `$$TriggerAbility` deux, `$$RemoveEffect` deux) : la
xref entrante depuis `...AdaptiveStrategyAbility$$ExecuteBehaviour` désigne un seul corps à chaque
fois.

### Qualification d'enum

| littéral | enum retenu | ce que l'ordinal nomme AILLEURS |
|---|---|---|
| `0x3ec` = 1004 | `TriggeredAbilityType.RelentlessMarch` | `ActiveAbilityType.MortisRound` (`ultraEliminatorSgt`) |
| `0x3f4` = 1012 | `EffectType.AdaptiveStrategy_DmgOverride` | `ActiveAbilityType.PrecisionShot_Aim` ; `TriggeredAbilityType.HeavyWeaponExtraDamage` |
| `0x3f3` = 1011 | `EffectType.RelentlessMarch_Effect` | `ActiveAbilityType.TunnelingHorror` (`necroSmnDestroyer`) |
| `statType: 0` | `StatType.ATTACK` | — |

### Masque et attack-type

`...AdaptiveStrategyAbility$$.ctor` :

```
range = <TargetingRange statics+0x30> = RANGE_ADJACENT           (copie de 0x18 octets)
TargetingOptions..ctor(&opts, isSelfCasting=1, &range, forceMeleeTarget=1, rules=0x402, 0, 0)
AActiveAbility..ctor(this, &opts, 2)                             # AbilityAttackType.Others
```

Surcharge à **7 arguments** `(isSelfCasting, range, forceMeleeTarget, rules,
getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)` : le littéral **EST** le masque
effectif — ni preset, ni `|` de flags additionnels. `0x402 = TargetMatchesDynamicRule |
TargetIsFriendly`, somme exacte, 0 bit résiduel. Les deux derniers arguments sont **nuls** : la règle
dynamique ne vient pas du délégué `options+0x38` mais du **slot virtuel** de la sous-classe, d'où une
surcharge de méthode et non une entrée de table.

## 3. Ce que ce port FERME

`relentless_march.py` §3 nommait un résidu depuis #328 : la branche `triggerType ==
EventTriggerType.Custom` de `...RelentlessMarchAbility$$CreateBehaviour` était **portée mais sans
appelant**. Le nœud (1) EST cet appelant —
`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` appelle
`ITriggeredAbility.ExecuteBy(ability, &abilityState, entities, 0x20)` avec le `0x20` **en dur**.
D'où l'entrée `TRIGGERED_ABILITY_BEHAVIOURS[RelentlessMarch]` (`necrons.py`). Le résidu est **clos**,
et il est confronté live (cf. §5, canal `hp`).

## 4. Confrontabilité — le gate REFUSE tout, sauf un allié NON-Hero

`...$$GetDynamicInvalidTargetReason` tient en une ligne : `HasTrait(target, 0x10 Hero) ? 2 : 0`. En
bataille de lineup **toute unité déployée porte `Hero`** ⇒ aucune cible légale. Le porteur d'un allié
non-Hero est un **SUMMON**, et le pool en produit un sans aucune greffe : `necroOverlord` caste
`ResurrectionOrb` (1009, déjà portée), qui spawne des `necroSmnWarrior`.

Montage (`probe_577`) : build `necroWarden` + `necroOverlord` (tous deux au pool rank 17, board
`MC1_67`, seed 777) → l'Overlord caste 1009 → le Warden se **déplace** adjacent au summon → capture →
rejeu offline par la voie complète (`Runner.apply(ActiveAbilityMessage)`) → cast live → rechargement
→ comparaison.

⚠ **Le summon a déjà fini son tour** quand il apparaît (`SpawnUnitBehaviour$$
TriggerSpawnedUnitBehaviours` → `FinishUnitTurn(spawned, isTerminated: true)`). C'est ce qui rend le
nœud (3) discriminant : `resetTurnFlags: 1` sauvegarde, efface, puis restaure ses flags.

## 5. MESURES live (board `MC1_67`, seed 777)

| étage | natif | port |
|---|---|---|
| cibles légales de 1005 (Warden adjacent à l'Overlord **HERO**) | `[81]` (le caster seul) — l'Overlord **exclu** | idem |
| cibles légales (Warden adjacent au **summon**) | `[81, 100]` | idem |
| le summon a AGI | oui, `(0,1) -> (0,4)` | oui, `(0,1) -> (3,3)` |
| `hp` du summon après | **5983** | **5983** |
| porteurs de `1012` après | `[]` | `[]` |
| porteurs de `1011` avant / après | `[83]` / `[]` | `[83]` / `[83, 100]` |

* Le `hp` **concorde à l'unité près** (+1197, plafonné au max) : c'est le `Repair` du re-trigger
  `RelentlessMarch` en mode `Custom`, donc le nœud (1) est confronté sur un canal indépendant.
* Le **net-zéro de 1012** vaut des deux côtés : le nœud (4) retire ce que le nœud (2) a posé.
* Le caster **lui-même** figure dans les cibles légales, et ce n'est pas un défaut du gate :
  `isSelfCasting = 1` fait rabattre le rôle `target` sur le caster par
  `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` (branche self-cast, en tête de ses
  quatre).

### ⚠ Le canal d'effets : un `[]` qui ne prouvait RIEN

La première version du probe interrogeait `decisionView.effects` — **un champ qui n'existe pas** (le
canal est `decisionView.units[].effects`). Toute question posée à ce canal rendait `[]`, et ce `[]`
se lisait comme « aucun porteur » : l'accord port/natif sur 1012 était un **accord en régime
dégénéré**. C'est le **témoin non nul** (`native_effect_census`, qui compte les lignes et vérifie
qu'un `EffectType` y est lisible) qui l'a fait rougir. Il tourne toujours.

### ⚠ L'imputation d'un écart se MESURE

Deux écarts subsistent, et aucun des deux n'a été imputé « à l'IA » sur parole :

* **la TUILE choisie** — natif `(0,4)`, port `(3,3)`. Une première contre-épreuve (« l'étage IA
  joué seul sous override doit rendre la tuile du port ») a **rougi**, à raison : elle ne rejouait
  pas le nœud (1), qui a déjà posé `RelentlessMarch_Effect` (+1 Mouvement) et réparé la cible.
  Reconstituer l'état d'entrée exact du nœud (3) reviendrait à rejouer le cast : la contre-épreuve
  serait **tautologique**. Le probe imprime donc les trois tuiles et la sensibilité au montant comme
  des **faits de décomposition**, et le verdict sur le nœud (1) est porté par un observable
  **persistant** (§ suivant), pas par la tuile.
* **`RelentlessMarch_Effect` (1011)** — le natif rend `[]` après le cast alors qu'il portait `[83]`
  avant. ⚠ **L'IMPUTATION ÉCRITE ICI — « il a expiré les instances à durée 1 tour »,
  `AiControl$$ApplyAiMessages` → `FinishUnitTurn` — EST FAUSSE, et elle l'est deux fois** (2026-08-18,
  tranche #10035). `FinishUnitTurnOperation$$Execute` n'expire rien (déjà relevé par #577-r1) ; et
  **le mécanisme n'est pas une expiration du tout, c'est un RE-CIBLAGE**.
  L'ability pose `AddEffect(0x3f3, …, targets = UnitsWithoutTrait(Friends(AdjacentUnits(Owner)),
  0x418), turns = 1)` — les cibles sont un **sélecteur géométrique**, que
  `RefreshEffectsOperation` matérialise dans `EffectComponent.Targets @+0x48` et **différencie** à
  chaque refresh (`$$GetTargetsToRemove` → `$$RemoveTargetsFromEffect`).
  La géométrie du montage suffit : l'instance sur `83` a été posée quand le Warden `81` était en
  `(1,0)` (`dist = 1`) ; le montage le déplace en `(0,2)` (`dist((0,2),(0,0)) = 2`) ; le natif déplace
  le summon en `(0,4)` (`dist((0,2),(0,4)) = 2`). **Les deux porteurs sont sortis du sélecteur** — le
  `[]` est complet sans invoquer aucune durée.
  **La contre-épreuve qui réfute l'expiration est déjà dans le tableau ci-dessus** : le natif *pose*
  1011 sur le summon pendant ce cast même, puis le retire dans la même cascade. Un effet posé à
  l'instant ne peut pas avoir expiré — `EffectComponent$$RemoveOneTurn` n'est enfilé que par
  `EndTurnOperation$$RefreshEffects`, dont l'appelant **unique** est `EndTurnOperation$$Execute`.
  Le foyer de `#577-r1` n'est donc **ni `summon_ai.py` ni le trigger de 1011**, mais le retrait des
  porteurs sortis du sélecteur (`runner/operations/refresh_effects.py`). Et la divergence est
  **observable sur la stat** : `RelentlessMarchExtraMoveEffect` ne surcharge ni `is_active` ni aucun
  sélecteur, donc côté port `83` garde le **+1 Mouvement** que le natif lui a retiré.

Autre limite **nommée** : `state.rng is None` sur un état rechargé (`load_state` ne restitue pas
l'état interne du Mersenne Twister), donc `RandomAmount` prend sa dégradation documentée — la borne
**MIN** (1197 dans `[1197, 1595]`). Le natif, lui, a tiré. Le probe l'assertionne explicitement
plutôt que de le laisser passer pour un accord.

## 6. Gardes vues ROUGES par mutation (appliquée, passe rejouée, source restaurée)

| mutation | ce qui rougit |
|---|---|
| `ADAPTIVE_STRATEGY_RESET_TURN_FLAGS = False` | `E0 PerformAIAction(asGroup=False, resetTurnFlags=False)` |
| nœud (4) `RemoveEffect` supprimé | `test_the_stat_override_is_net_zero_on_both_sides` (« le PORT garde 1012 sur `[100]` ») **et** `E0 FORME de l'arbre` |
| `TRIGGERED_ABILITY_BEHAVIOURS[1004]` retiré | `E2 u100.hp : natif=5983 port=4786` (**confronté au natif**), `E7 le PORT n'a posé AUCUN 1011`, `E0`, et `dispatched: False` |

La deuxième et la troisième rougissent sur le **comportement**, pas seulement sur la structure ; la
troisième est couplée à la valeur du **natif**.

⚠ `resetTurnFlags` n'est PAS discriminant dans ce montage : le summon offline n'y porte pas le flag
`NoActionAvailable` que le natif lui pose au spawn, donc il agit même sans reset. La garde qui le
tient est donc la **transcription** (E0), qui est le bon cran pour un booléen lu au décompilé.

## 7. Résidus NOMMÉS

* **#577-r1** — le port n'expire pas les effets à durée 1 tour quand une unité joue sous
  `ComputerActionOperation` (le natif le fait via `ApplyAiMessages` → `FinishUnitTurn`). Mesuré
  disjointement de 1005 : l'écart préexiste. Foyer : `engine/runner/operations/summon_ai.py`.
* **#577-r2** — face **DÉCISION** (`IdunBattle.AI.Playbook.Loki.AdaptiveStrategyPlaybook`) non
  portée. La RE est faite (cf. §8) ; ce qui bloque est un point **structurel** non tranchable
  offline.
* `unitSelectionType = 3` (`OnlyAliveAndTargetable`) : le port n'honore que le volet ALIVE (même
  résidu que `relentless_march.py`).
* `unique = true` d'`AdjacentUnits` : sans effet observable (une unité = une position).
* La tuile choisie par l'IA sous 1005 diverge du natif — argmax de `decide_and_apply`, chantier
  agreement, hors de cette tranche.

## 8. Face DÉCISION — RE faite, port NON livré (résidu #577-r2)

`IdunBattle.AI.Playbook.Loki.AdaptiveStrategyPlaybook$$EvaluateNonComparable(caster, casterPosition,
abilityState)`, lu :

```
bucket  = new Bucket<...>(<type token>)              # ctor a UN argument -> pas de MIN_UTILITY
targets = BasePlaybook.GetEligibleTargetsSelectable(this, caster, casterPosition.MainTile)
foreach t in targets:
    sel   = DSLSelectors.Friends( of: Caster@DSLSelectors+0x48,
                                  entities: DSLSelectors.UnitsWithoutTrait(
                                      DSLSelectors.AdjacentUnits(Target@DSLSelectors+0x60,
                                                                 unique: 1, selType: 3),
                                      0x10 Hero, selType: 3),
                                  selType: 3 )
    count = sel.<vslot 0x2b8>(entities_for_t)
    if (count > 1):
        bucket.AddAction( BasePlaybook.GenerateAction(this, casterPosition, t, (Fix64)count) )
return bucket
```

Utilité = **le compte d'alliés non-Hero adjacents à la cible**, retenue seulement si `count >= 2`.
`AdaptiveStrategyPlaybook$$.ctor` = `<Playbook base>..ctor(this, 0x3ed = 1005)`. Aucun `.cctor`,
aucun `ShouldEvaluate` propre.

⚠ **La composition de sélecteur DIFFÈRE de celle de l'exécution** et ce n'est pas une coquille :
`ExecuteBehaviour` fait `Friends(AdjacentUnits(**Caster**)) - HeroUnits(...)` (soustraction), le
playbook `Friends(UnitsWithoutTrait(AdjacentUnits(**Target**), Hero))` (filtre imbriqué). Les deux
coïncident ici parce qu'`isSelfCasting = 1` rabat `Target` sur le caster ; le port doit **mirrorer
chaque site tel quel**, pas les unifier.

**CE QUI BLOQUE.** `AdaptiveStrategyPlaybook` doit entrer soit dans le registre NonComparable, soit
dans la voie Comparable — et le discriminant, `get_IsComparable` (slot 1 de `IPlaybook`), **n'est pas
lisible offline** : les ctors gshared `NonComparablePlaybook<T>` / `ComparablePlaybook<T>` ont la
même structure `(this, abilityType, typeToken)` et Ghidra les mislabelle. La mesure existe et est
outillée — `pbGate(slot=1)` (cf. `probe_170_playbook_priority.py`) — mais elle exige un runner. Un
playbook branché au mauvais tier ordonnancerait l'ability à côté de sa place native : c'est une
dégradation **silencieuse**, du même genre que celles que ce dépôt traque. **Le port est donc
refusé tant que la mesure n'est pas prise** — un port refusé avec sa raison écrite vaut mieux qu'un
port inerte ou mal câblé.
