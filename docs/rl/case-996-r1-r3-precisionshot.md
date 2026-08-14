# #996-r1-r3 — `1015 PrecisionShot` PORTÉE, et le triptyque dont elle est la FAÇADE

**Build** : `rnca9r7q6c`. **Source** : `mcp__ghidra__decompile_function` — décompilé = vérité, live
= confirmation. Amont : `docs/rl/case-996-r1-precisionshot-devoutpush.md` §3, qui REFUSAIT ce port
et nommait les cinq pièces manquantes.

## 0. Ce que la tranche établit

| item | verdict |
|---|---|
| `1015 PrecisionShot` | **PORTÉE et CONFRONTÉE LIVE** — gate 3/3 en régime discriminant, exécution en accord |
| `1012 PrecisionShot_Aim` | **PORTÉE et CONFRONTÉE LIVE** — effet + sous-effet + charge consommée, accord exact |
| `UseActiveAbility(activeAbilityType NON-NORMAL)` | **PORTÉ** — 1er call-site du dépôt |
| `DSLBehaviors$$SetActiveAbilityUsed` + son Operation | **PORTÉS** |
| effet `1015 PrecisionShot_Aim` | **POSE + SOUS-EFFET portés** ; ses trois retraits → résidu `#996-r1-r3-r3` |
| `1013 PrecisionShot_Attack` | **NON PORTÉE** — trou permissif MESURÉ (`casterReason 0x4` que le port rend `0x0`) → résidu `#996-r1-r3-r2` |

Les cinq pièces que `case-996-r1` §3 déclarait manquantes ont été relues une à une ; **quatre sont
portées par cette tranche**, la cinquième (1013) est nommée en résidu. La prémisse « le couple est
INDIVISIBLE » est **confirmée** : la règle dynamique de caster ne se pose que sur la CLASSE, donc
son inscription arme `execute_behaviour`.

## 1. Le triptyque, relu

Le gameconfig ne déclare que `activeAbilities: ["PrecisionShot"]`, et le seed BC ne porte qu'une
entrée `BC.Abilities.ActiveAbilities["PrecisionShot"]` (`variables: {dmg}`, `constants: {nrOfHits:
1, damageProfile: Energy}`). **La bataille monte pourtant les trois sœurs** — mesuré, pas déduit :
`[69 Loki_NormalAttack, 1015 PrecisionShot, 1012 PrecisionShot_Aim, 1013 PrecisionShot_Attack]`.

Ce qui les articule, ce sont leurs trois `GetDynamicInvalidCasterReason`, qui s'excluent deux à
deux :

| ability | corps décompilé | verdict |
|---|---|---|
| `1015 PrecisionShot` | `HasEffect(caster, 0x3f7) ? 0 : 2` | valide **seulement EN visée** |
| `1012 PrecisionShot_Aim` | `-(uint)(HasEffect(...) != 0) & 2` | valide **seulement HORS visée** |
| `1013 PrecisionShot_Attack` | `HasEffect(...) ? 0 : 4` | valide **seulement EN visée** |

`2` = `TargetingRule.TargetMatchesDynamicRule`, `4` = `CasterMatchesDynamicRule`. ⚠ Le littéral de
1015/1012 est bien `2` — un code de règle CIBLE rendu par une règle CASTER. Le port le TRANSCRIT au
lieu de le « corriger ».

**Les arbres**, mirror :

```
PrecisionShotAbility$$ExecuteBehaviour
    Execute( UseActiveAbility( caster = Caster@DSLSelectors+0x48,
                               target = Caster@+0x48,            # le CASTER, pas la cible
                               activeAbilityType = 0x3f4 = 1012,
                               parentAbility = Nullable(AbilityOrEffect(this+0x10)),
                               <opts ZERO>, <opts ZERO> ) )

PrecisionShot_AimAbility$$ExecuteBehaviour
    Execute( AddEffect( 0x3f7 = 1015 EffectType.PrecisionShot_Aim,
                        get_AbilityStateReference(this), Owner@+0x30, Nullable(3) )
             op_BitwiseAnd
             SetActiveAbilityUsed( Owner@+0x30, 0x3f7 = 1015 ActiveAbilityType.PrecisionShot ) )
```

⚠ **`0x3f7` désigne DEUX choses dans le même arbre** — l'EFFET `EffectType.PrecisionShot_Aim` (1er
terme) et l'ABILITY `ActiveAbilityType.PrecisionShot` (2e). Le port nomme les deux.

⚠ **La surcharge d'`UseActiveAbility` se tranche AUX XREFS ENTRANTES** : `180ea6b30` (à
`ActiveAbilityType` entier → `DirectAbilitySelector`) contre `180ea6a20` (à sélecteur). Les deux ont
sept paramètres et le même nom affiché. Sur les **3** call-sites de la première, deux passent
`0x45 = Loki_NormalAttack` (`UnbreakableDuty`, `RedemptionOfTheRisen`) : **`PrecisionShot` est le
SEUL call-site NON-NORMAL du binaire**, et c'est lui qui exigeait l'étage.

⚠ La surcharge d'`AddEffect` est celle à **quatre** arguments (`180e9eca0`, xref confirmée), dont le
corps passe littéralement `source = 0` → la source de l'effet est la CIBLE, pas le caster
(`source_from_target=True`). Ici les deux coïncident.

## 2. L'étage qui manquait : `UseActiveAbility` à type NON-NORMAL

`IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute`, relu : le champ `+0x50` n'est
pas un entier mais un `IAbilityTypeSelector`, résolu PAR CASTER (`processor[+0x20] = caster` PUIS
`(+0x50).Select(entities)`), et le dispatch n'a lieu que si le `Nullable` rendu a `HasValue`. Le
dispatch est ensuite `processor.<slot 2>(caster, targets, abilityType, options)` =
`Core.Services.OperationProcessor$$ActiveAbility` → `ActiveAbilityOperation$$Execute` →
`$$ExecuteInternal` — **pas** `AttackDamage`.

Le port entre donc au MÊME rang, par `AbilityHandler.active_ability_operation` (foyer neuf, mirror
du slot 2) : sans le gate de message d'`InputMessageProcessor$$Visit` (le natif ne repasse pas par
le visiteur, #429-r1-r3), et AVEC les gates de l'opération. Un sous-cast refusé est un no-op
complet, et il reste **lisible** : son diagnostic part dans `sub_cast` de l'événement émis.

`is_regular_attack` sépare les deux chemins — c'est LUI le discriminant, pas une liste écrite au
site.

## 3. `SetActiveAbilityUsed` — le behaviour et son Operation

```
SetActiveAbilityUsedBehaviour$$Execute
    foreach unit in (this+0x58 units).<slot 4 = SelectUniqueUnits>(entities, 3) :
        proc.<slot 0x74>(unit, this+0x50 /* activeAbilityType */)

SetActiveAbilityUsedOperation$$Execute(unit, activeAbilityType)
    if (!UnitExtensions.HasUnusedAbility(unit, activeAbilityType)) return
    foreach ab in unit.ActiveAbilityComponent.Collection :
        if (IsRegularAttack(ab.AbilityName@0x44) || ab.AbilityName@0x44 != activeAbilityType) continue
        ab.<+0x10> += 1 ; ab.<+0x18> = ab.<+0x20> = Nullable(turnsEnded) ; ab.CanStillBeUsed@0x28 = false
```

`HasUnusedAbility` = `GetOrNull(type) != null && CanStillBeUsed@0x28` — **pas** `CanCurrentlyBeUsed`
(ni cooldown, ni `IsDisabled`, ni munitions). Porté avec le TRI-ÉTAT du canal : `gate is None` quand
l'unité n'a aucun `ActiveAbilitiesComponent` (`allAbilities` non demandé), jamais un `False`
fabriqué.

NON MODÉLISÉS : `+0x10` (compteur d'usages), `+0x18`/`+0x20` (deux `Nullable<int>` de tour), et
l'événement `0xd` — aucun composant du port ne les représente. Le cooldown `+0x2c` n'est PAS touché
par cette Operation.

## 4. Confrontation LIVE — `probe_996r1r3_precision_shot_port.py`

Montage : board `MC1_67`, seed 999, porteur NPC **réel** `necroNpc3Deathmark:45`
(`--explicit-stats`, aucune greffe).

### [B] GATE avant visée — le trou PERMISSIF fermé

| ability | natif `casterReason` | port |
|---|---|---|
| `1015` | `0x2` | `0x2` **ACCORD** |
| `1012` | `0x0` | `0x0` **ACCORD** |
| `1013` | `0x4` | `0x0` — **1013 non portée**, trou nommé |

Avant la tranche, le port rendait `0` pour 1015 : il ACCEPTAIT un cast que le natif REFUSE
(`actionConsumed = False`).

### [C] VISÉE — cast de 1012, rejeu offline du même cast

| | effets du caster après | `usable(1015)` |
|---|---|---|
| natif | `PrecisionShot_Aim` (3) · `PrecisionShot_BlockMovement` (3) | `False` |
| port | `PrecisionShot_Aim` (3) · `PrecisionShot_BlockMovement` (3) | `False` |

**Accord exact**, noms ET durées. Le sous-effet `1016` vient de
`PrecisionShot_AimEffect$$BlockMovement` → `AddSubEffectWithSameTurns` ; sans lui le port aurait
posé un effet sur deux. `usable(1015) = False` est la morsure de `SetActiveAbilityUsed`.

### [E] LA FACE EXÉCUTION, atteinte pour de vrai — scénario CRAFTÉ

Les volets [A]-[D] établissent que **1015 n'est jamais exécutable dans son régime naturel** : hors
visée sa règle la refuse, et le seul cast qui pose la visée (`1012`) CONSOMME sa charge dans le même
arbre. Sa `ExecuteBehaviour` serait restée NON CONFRONTÉE.

Le levier est dans le jeu : `1204 InspiredToGreatness` (`tauAunShi`, **dans le pool**) porte
`ResetActiveAbility`, qui ré-arme les charges sans toucher aux effets. Montage : Deathmark vise →
Aun'Shi le RESET → tour suivant, 1015 est en visée ET rechargée.

| | natif | port |
|---|---|---|
| gate `1015` | `0x0` | `0x0` **ACCORD** |
| gate `1012` | `0x2` | `0x2` **ACCORD** |
| `applyAction 1015` | `ok=True, actionConsumed=True, n_changes=0` | `ported=True`, `sub_cast.invalid_target = 2`, flags posés |
| effets après | inchangés (hors retrait de 1180) | **identiques** |

⇒ Le natif EXÉCUTE l'arbre de 1015 et **ne change rien** : son sous-cast 1012 est refusé par la
règle inverse. Le port dit exactement la même chose. **La face EXÉCUTION est confrontée, et elle est
en accord.**

### Mutants — 8 sur 8 mordent

`ability_type` → attaque normale · règle de 1015 INVERSÉE · sous-effet 1016 retiré · durée 3 TOURS →
1 ROUND · `SetActiveAbilityUsed` sur 1012 au lieu de 1015 · `ABILITY_ATTACK_TYPE` retiré · bit
`CasterMatchesDynamicRule` retiré du masque · aiguillage du dispatch désarmé.

### Deux pièges de MESURE, tous deux rencontrés dans ce probe

* **`decisionView.effects` ne publie PAS de champ `type`** (il vaut `None` sur toutes les lignes).
  Comparer par ordinal rendait un ensemble natif VIDE face à un ensemble port plein — DÉSACCORD
  affiché sur un accord parfait. Comparer par NOM.
* **`EffectsState.by_unit` garde les entrées CONSOMMÉES** ; le canal natif est ACTIF-ONLY. Lire
  `by_unit` brut faisait apparaître `InspiredToGreatness_OverrideLevel` comme non retiré alors que
  le port le retire bien (registre `ITG_OVERRIDE_LEVEL`, `On(0xc) & OwnerIsCaster`). Passer par
  `active_effects`.

## 5. Le masque, relu au `.cctor` (forme PRESET + FLAGS)

`PrecisionShotAbility$$.ctor` recopie les 0x40 octets de `<TargetingOptions statics>+0x280` puis
appelle `TargetingOptions..ctor(&opts, &preset, 0x10)`, dont le corps fait
`this+0x28 <- additionalRules | template+0x28`. Le `.cctor` a été RELU champ par champ :

```
+0x280 isSelfCasting    = 1
+0x288 range           <- `TargetingRange statics+0x60`   (`.cctor` : onlyAdjacent = 1,
                                                            overrideRange = Nullable(0)) = RANGE_SELF
+0x2a0 forceMeleeTarget = 1 = RangedBool.False
+0x2a8 rules            = 0x8004
```

⇒ masque effectif `0x10 | 0x8004 = 0x8014` = `CasterHasNotMoved` | `CasterMatchesDynamicRule` |
`CasterIsPossibleTarget`. Aucun bit de cible : c'est un self-cast. `1012` porte le MÊME ctor,
instruction pour instruction. `AActiveAbility..ctor(this, &opts, 2)` dans les deux corps →
`AbilityAttackType.Others`.

⚠ Leur sœur `1013` porte `0 DirectTargetAttack` alors que c'est la SEULE des trois qui attaque : le
littéral ne se déduit ni du nom ni du triptyque.

## 6. Ce que cette fiche ne tranche PAS

* **`1013 PrecisionShot_Attack`** — sa config d'ability n'est ni au gameconfig ni au seed BC (seul
  `PrecisionShot` y figure), donc le `GetDamageProfile(this+0x60)` / `GetNumberConstant(0x2f)` de son
  `ExecuteBehaviour` lit une config qu'aucune source offline ne nomme. Le gate mesuré (`0x4`) est
  un trou permissif réel. Résidu `#996-r1-r3-r2`.
* **Les trois retraits de l'effet de visée** —
  `PrecisionShot_AimEffect$$CreateHandleTriggerAbilitiesInternal` :
  `On(0x12) & <DSLTriggers+0x28> & AmountIsEqualOrGreater(Enemies(AdjacentUnits(Owner)), Direct(1))`,
  `On(0x23) & OwnerIsTarget`, `On(0x0b) & OwnerIsActor & !OwnerIsTarget`. L'effet se comporte donc
  côté port comme un timer pur (3 tours) : PERMISSIF sur « un ennemi arrive au contact ». Résidu
  `#996-r1-r3-r3`.
* **L'entrée d'ability n'est pas mise à jour par le port au rang de l'opération** — écart NOMMÉ,
  **pré-existant et hors périmètre** : `ActiveAbilityOperation$$ExecuteInternal` réécrit
  `CanStillBeUsed@0x28`, incrémente `+0x10`/`+0x14` et pose `+0x18`/`+0x20`/`+0x2c` à chaque cast
  qui aboutit, alors que le port ne pose que le FLAG D'UNITÉ `ActiveAbilityUsed` (ce qui est le
  mirror EXACT d'`AddFlagsAfterAbilityExecution`, relu : il ne fait que `UnitFlagsComponent.Add(2)`
  + le slot `0x23 FinishUnitTurn`). L'écart vaut pour TOUTE ability du registre. Mesuré en [E] :
  `usable(1015)` natif `False` / port `True`. Résidu `#996-r4` (numéro alloué par
  `probe_468 --suggere 996` : il n'est PAS propre à 1015).
  ⚠ **Et il n'y a AUCUN gate de disponibilité dans `ExecuteInternal`** : `CanCurrentlyBeUsed`,
  `HasUnusedAbility` et `CanStillBeUsed` y ont **0 occurrence** (relecture intégrale du décompilé).
  Le seul gate d'ability y est `ActiveAbilityComponent$$GetOrNull` (l'entrée EXISTE-t-elle) suivi
  d'`UnitExtensions$$IsAbilityBlocked`. Le refus mesuré en [D] (`actionConsumed = False` sur une
  charge consommée) vient donc d'un étage **AMONT** du visiteur, pas de l'opération.
* **La face DÉCISION**, et elle est VENTILÉE — le cliquet `#1021` l'exige de toute entrée neuve au
  registre COMBAT, et il a rougi sur les deux (trouvé **au re-jeu après rebase**) :
  * **`1015 PrecisionShot` → `RIEN_A_PORTER`, attesté au ledger `#951-r2`.** Le dict `+0x68` d'
    `IdunBattle.AI.PlaybookDatabase` (peuplé par `$$InitializePlaybookBuilders`) l'apparie à
    `IdunBattle.AI.Playbook.Common.DefaultActiveAbilityPlaybook` — le playbook GÉNÉRIQUE. C'est
    une mesure POSITIVE, pas une absence, et elle est **remarquable** : 1015 est la **SEULE des
    233 actives du dict** à retomber sur ce playbook commun ; les 232 autres ont une classe propre.
    Parfaitement cohérent avec la RE de sa face COMBAT — une façade jamais exécutée n'a rien à
    faire évaluer.
  * **`1012 PrecisionShot_Aim` → DETTE `SANS_VERDICT`** (registre de `probe_1021`) : son playbook
    propre déclare `EvaluateNonComparable` (utilité CONSTANTE `Fix64(3/2)` = 1,5 par cible de
    `GetEligibleTargetsSelectable`) **et** un `ShouldEvaluate` substantiel (gate `WillBeKill` sur
    une prédiction, seuil de HP `> 0x3c`, valeurs `0x50` / `0x14`) — c'est LUI qui porte la
    décision de viser. Résidu `#996-r1-r3-r5`.
  * `1013 PrecisionShot_AttackPlaybook` porte les deux mêmes méthodes ; il suivra le port de sa
    face COMBAT (`#996-r1-r3-r2`).
* **TROIS gardes à PLANCHER DE POPULATION, une seule cause.** `TARGETING_OPTIONS_UNPORTED` est
  tombée à **0 entrée** le 2026-08-14, par deux migrations légitimes et indépendantes
  (`1215 InstrumentsOfVengeance` #889-r6, puis `1015 PrecisionShot` — cette tranche). Trois
  cliquets ont lu ce drainage comme une panne, chacun sous une forme différente :

  | garde | forme du plancher | remplacé par |
  |---|---|---|
  | `test_519_..._la_derivation_mesure_quelque_chose` | `assert total > 0` | égalité `total == len(TABLE)` |
  | `test_996_no_op_silencieuses::test_contrat_de_disjonction` | `assert unported` | non-vide du **périmètre** (les 3 ids au registre) + disjonction **globale** |
  | `test_270r1_volet2::test_cardinalites_du_volet` | `assert dans_le_dict` **par table** | total confronté `== 109` + non-vide de l'**UNION** des 10 tables |

  Les deux premières étaient **déjà rouges sur `origin/master`** avant cette tranche (mesuré au
  stash). La troisième est bien la mienne, attribuée par l'orchestrateur (worktree frais sur
  `2e9b37dd` : 7 passed ; après merge de ma branche : 1 failed).

  ⚠ **Ce qui peut se dire UNE FOIS se dit une fois.** Sur le volet 270-r1, désarmer table par
  table aurait laissé les **9** tables sans résolveur porter une assertion **redondante** (sans
  seconde source, `res is not None or not ailleurs` force déjà `ailleurs` vide). L'assertion juste
  porte sur l'**union**.

  ⚠ **Et une assertion TAUTOLOGIQUE aurait été le même vice, sous l'autre face.** Ma première
  rédaction écrivait `len(dans_le_dict) + len(ailleurs) == len(snap)` : `o in vivant` et
  `o not in vivant` partitionnent **toujours** — cette ligne ne pouvait jamais rougir. Remplacer
  un plancher qui rougit à tort par une assertion qui ne rougit jamais n'aurait pas réparé le
  volet, ça l'aurait **vidé en le faisant paraître plus riche**. Corrigé en un invariant qui dit
  le **COMBIEN** (les 109 couples restent confrontés, dict ou résolveur) — contre-épreuves : rendre
  un couple introuvable des deux côtés, ou retirer une entrée d'une table sans résolveur, font
  rougir ce test dans les deux cas.
* **Le troisième cliquet de registre trouvé au rebase** : `DYNAMIC_CASTER_GATE_BY_ABILITY`
  (`engine/services/ability_caster_gates.py`) — toute ability dont le masque pose
  `CasterMatchesDynamicRule` doit y inscrire sa ligne de régime, sous peine d'être traitée comme
  « pas de règle » côté DÉCISION. `1015` y était déjà (via `TARGETING_OPTIONS_UNPORTED`) ; `1012`
  y est entrée avec cette tranche. Le cliquet
  (`test_433_..._caster_reason_offline::test_la_table_de_regime_couvre_EXACTEMENT_les_porteurs_du_bit`)
  a rougi et est revenu vert. ⚠ Son diff pytest affichait DEUX écarts ; re-dérivé par ENSEMBLES il
  n'y en avait qu'**UN** (`1012`) — le second est l'artefact d'affichage d'une liste désalignée,
  exactement le piège que `bb461b50` décrit.
