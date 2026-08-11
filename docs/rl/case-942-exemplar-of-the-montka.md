# case-942 — `1210 ExemplarOfTheMontka` (`tauFarsight`) : les quatre faces, et ce que l'audit ne disait pas

## 0. Le point de départ était FAUX sur la face, juste sur le symptôme

L'audit `combat-ability-coverage.md` classait 1210 en `EFFECT/BUFF` — colonne qui **dérive du KIT
gameconfig, jamais du behaviour**. Ici elle tombe juste, mais elle sous-compte : le cast a **une**
face, l'effet qu'il pose en a **deux**, et la décision une **quatrième**. Le symptôme, lui, était
exact : `ABILITY_CLASSES` ne connaissait pas 1210, donc l'IA la choisissait et l'exécution n'en
faisait **rien** — no-op silencieux, ni erreur ni crash.

## 1. Recensement EXHAUSTIF des faces — par le bloc `methodPointers`, pas par un grep de nom

`frida/methods.tsv` est indexée par ADRESSE et le bloc range **par classe**. Deux voisinages
tranchent la complétude mieux qu'une recherche de symbole (qui ne prouve rien : IL2CPP déduplique
les corps triviaux) :

| classe | slots contigus | ce qui n'y est PAS |
|---|---|---|
| `...Active.Loki.ExemplarOfTheMontkaAbility` | `ExecuteBehaviour`, `.ctor` | pas de `GetDynamicInvalid*TargetReason`, pas de `GetPossibleAdditionalTargetTilesForDangerZone`, pas de `GetTargets` — ses deux voisins immédiats (`ExemplarOfTheKauyonAbility`, `ExplosivePresentsAbility`) en ont, eux |
| `...Effects.Loki.ExemplarOfTheMontkaEffect` | `ApplyInternal`, `CreateEffectDamageBonusForAttack`, `RevertInternal`, `.ctor` | **pas de `CreateTargetSelector`** (donc AUCUNE aura : l'effet ne vit que sur ses porteurs), pas de `CreateCritChanceBonus`, pas de `GetRefreshTriggers` |
| `...AI.Playbook.Loki.ExemplarOfTheMontkaPlaybook` | `ShouldEvaluate`, `EvaluateNonComparable`, `HasNormalAttackTarget`, `.ctor`, `.cctor` | — |

S'y ajoute `IdunBattle.View.AbilityConfigs.Loki.ExemplarOfTheMontkaVisuals` (couche View, hors
moteur). **Aucune face 2-PHASES** : pas de `CreateTrigger`, aucune `TriggeredAbilityType` associée.

**Reachability, LUE** : `data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` porte
`active 1210 -> ...ExemplarOfTheMontkaPlaybook`, **une seule ligne**, dans le dict `active` (+0x68)
— rien en `triggered`/`nonowner`/`specific`. Ce n'est donc pas du registered-but-dead, et 1210 n'a
**pas** de face non-owner (celle-ci n'existe que pour `TriggeredAbilityNonOwnerPlaybook<T>`).

## 2. Le cast — UN seul nœud, et le CASTER entre par le FILTRE

`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheMontkaAbility$$ExecuteBehaviour` :

```
targets = UnitsWithRangedWeapons(
              UnitsWithTrait( Friends( of        = <DSLSelectors+0x48 = Caster>,
                                       entities  = <DSLSelectors+0x20 = AllAliveUnits>,
                                       selection = 3 ),
                              trait = 0x10 = UnitTrait.Hero, selection = 3 ) )

Execute( AddEffect( 0x5da = 1498, abilityState = get_AbilityStateReference,
                    source = Caster@+0x48, targets, turns = <DSLFormulas+0x20> ) )
```

**QUATRE écarts avec le jumeau de forme `WarHowl` (1106)**, et les recopier aurait été le neuvième
« voisin de forme » de la série :

1. **NI `op_Subtraction` NI `op_Addition`** — 1106 retire l'`Owner` du pool puis le ré-ajoute ;
   1210 passe le pool ENTIER. `UnitExtensions$$IsFriend` n'écarte pas l'égalité, donc le caster est
   son propre ami : il n'est buffé **que** parce qu'il passe les deux filtres. Farsight les passe
   (`traits: [Hero, BeastSlayer, BigTarget, Flying, Mechanical]`, arme `Plasma Range 2`) — mais
   par le filtre, pas par une exception. **Observable** : un porteur qui perdrait `Hero` ou son arme
   distante ne se bufferait pas, là où 1106 buffe son caster inconditionnellement.
2. **Filtres POSITIFS** : `UnitsWithTrait(Hero)` + `UnitsWithRangedWeapons`, contre
   `UnitsWithoutTrait(Summon)` + `UnitsWithoutRangedWeapons` chez 1106. Le « Characters » de l'i2
   est ici RÉEL (trait `Hero` lu), alors qu'il est décoratif chez 1106.
3. **Référent de `Friends`** = `Caster@+0x48`, pas `Owner@+0x30`.
4. **`get_AbilityStateReference`** (= `DSLSelectors$$AbilityState(Caster@+0x48, <l'active
   courante>)`, décompilé relu) au lieu de `CreateSnapshot`. Les deux désignent l'état du CASTER
   → même port (`scale_from_source=True`), mais on écrit ce que le natif écrit.

`turns = <DSLFormulas+0x20>` est un **champ posé par le ctor**, pas un appel : `DSLFormulas$$.ctor`
remplit un cache de constantes (`+0x18 <- 0`, **`+0x20 <- 1`**, `+0x28 <- 2`, `+0x30 <- 100`,
`+0x38 <- -1`). Donc **1 TOUR**, confirmé live (`remaining: 1`).

**Surcharge d'`AddEffect` tranchée par l'ADRESSE de la cible du `call`** (le binaire en porte
quatre du même nom) : `e8 0d 50 ba ff` depuis `...+0x9e` résout sur RVA `e9e9b0` =
`AddEffect(effectType, abilityState, source, targets, turns: IAmountFormula)`.

### Masque de ciblage — forme STATIC-COPY

`...$$.ctor` recopie les 0x40 octets de `<TargetingOptions statics>+0x280` et les passe TELS QUELS
à `AActiveAbility$$.ctor(this, &opts, 2)` : **aucune** surcharge de `TargetingOptions$$.ctor` n'est
appelée. Le masque effectif est la constante écrite par `TargetingOptions$$.cctor` en
`<preset>+0x28` :

    0x8004 = CasterIsPossibleTarget(0x8000) | CasterMatchesDynamicRule(0x4)

Décomposition exhaustive, aucun bit résiduel. C'est le **même preset** que `1215
InstrumentsOfVengeance`, et celui de `1216 MartialExemplar` / `1192 NovaBoost` **moins** leur
`additionalRules = 0x10` → **1210 n'a PAS `CasterHasNotMoved`** : elle reste castable après
déplacement. `isSelfCasting = <preset>+0x00 = 1` ; `forceMeleeTarget = <preset>+0x20 = 1` ;
portée = la copie de `<TargetingRange statics>+0x60` = **RANGE_SELF** (`overrideRange = 0`).

`CasterMatchesDynamicRule` délègue à `GetDynamicInvalidCasterReason` — **que la classe ne surcharge
pas** (deux slots seulement, cf. §1) : le délégué reste le défaut de `AActiveAbility`, qui ne refuse
rien.

`AbilityAttackType` = le littéral **`2` = `Others`**, 3ᵉ argument d'`AActiveAbility$$.ctor` —
TRANSCRIT, jamais déduit du fait que le cast ne frappe personne (sur cet axe, `WallOfMirrors` et
`StormOfWrath` se contredisent chacun dans un sens).

Turn-flags : 1210 était **déjà** dans `NO_END_TURN_ABILITY_TYPES` **et**
`NO_ABILITY_USED_FLAG_ABILITY_TYPES` (inventaire #139) — rien à écrire, et c'est ce qui rend le cast
répétable dans le tour (le kit 1210 ne déclare **aucune** constante, donc aucun `cooldownTurns`).

## 3. L'effet 1498 — deux artefacts, et le second n'a PAS le gate qu'on lui prêterait

`.ctor` (octets lus) : `mov edx, 0x4ba` → `AbilityOrEffect$$op_Implicit`, surcharge tranchée par
l'**adresse** de la cible du `call` (RVA `166a000` = celle qui prend un `ActiveAbilityType`) →
la config lue est `abilities.ExemplarOfTheMontka` et le niveau qui l'indexe est celui d'une ability
**ACTIVE**. `hasAutomaticActivation = 1`.

**TRAIT** — `ApplyInternal` / `RevertInternal` : `<IOperationProcessor @this+0x68>.<slot 0x26/0x27>
(target, 0x412, isTemporary: 1)`, signature d'`OperationProcessor$$AddTrait`/`$$RemoveTrait`.
`0x412 = 1042 = UnitTrait.Unstoppable`. Corps **strictement identique** à celui de
`WarHowl_ExtraDamage_UnstoppableEffect` — mais à une adresse distincte et avec son propre garde de
`class_init` : ce sont deux corps, pas un fold.

**DÉGÂT** — `CreateEffectDamageBonusForAttack` :

```
EffectBonus.ForAddition( get_OwnerIsCaster & IsNormalAttack,
                         If( HasTrait(Target@+0x60, 0x3f9 = BigTarget),
                             ConfigVar(0x09 = extraDmg_2),
                             ConfigVar(0x08 = extraDmg) ) )
```

**DEUX nœuds de trigger, et AUCUN gate de nature de coup** — c'est l'écart de fond avec 1222, dont
le trigger porte `IsMeleeAttack`. Le buff mord sur **toute** attaque normale, mêlée comme distance,
et l'i2 le dit mot pour mot (« all their normal attacks »). Ajouter `IsMeleeAttack` ici par
imitation aurait tué le buff des attaques distantes — c'est-à-dire de **tous** les buffés, puisque
le sélecteur ne retient que des porteurs d'arme distante.

L'ORDRE des branches est LU (`DSLFormulas$$If(trigger, ifAmount, elseAmount)`, `ifAmount =
ConfigVar(9)`), et concorde avec l'i2 (« When attacking a Big Target, they deal +946 Damage
instead » ; `extraDmg[64] = 437`, `extraDmg_2[64] = 946`).

`target_traits is None` (cible non mesurée) → branche `else`. Dégradation MINIMALE : le natif
accorde **toujours** une contribution (son `If` a deux branches non nulles), donc rendre `None` la
supprimerait ; accorder `extraDmg_2` l'inventerait.

## 4. La face DÉCISION — un gate dont le NOM ment

`ExemplarOfTheMontkaPlaybook` est un **NonComparable**. Le `.ctor` que Ghidra nomme
`ComparablePlaybook<...>$$.ctor(this, 0x4ba)` est un corps trivial DÉDUPLIQUÉ (même piège que
#487-r1) : le discriminant est la méthode surchargée, `EvaluateNonComparable`.

```
EvaluateNonComparable : bucket = Bucket<UnitAction>(0, Nullable(<statics+0x00>))   # cctor : Fix64(1)
                        foreach t in GetEligibleTargetsSelectable(caster, casterPosition):
                            bucket.AddAction(GenerateAction(casterPosition, t, Fix64(1)))
ShouldEvaluate         : return HasNormalAttackTarget(unit)      # surcharge DIRECTE du slot 4
HasNormalAttackTarget  : naType = GetNormalAttackType(unit)
                         res = <IBattleQuery 0x45 = GetAllValidTargetsFromAllPossibleMovementTiles>
                         foreach (kv in res.<+0x18>) foreach (target in kv.Value)
                             if (!WillNormalAttackKill(unit, target, kv.Key.MainTile)) return true
                         return false
```

⚠ **Le nom ment sur la sémantique** : ce n'est pas « ai-je une cible ? » mais « ai-je une cible que
mon attaque normale **ne tue pas** ? ». La négation est dans le corps. C'est le sens tactique des
quinze `ShouldExecute` de `normal_attack_kill_gate`, appliqué **en amont** (slot 4) et à un buff.

Contrairement à `UnbreakableDuty` (structure d'`EvaluateNonComparable` identique), le gate n'est
**pas** un `GetUseProbability` en pourcents : aucun tirage aléatoire à ne pas modéliser, donc le
port peut être EXACT.

## 5. Confrontation live — mesures, board `MC1_67`, seed 777, rank 17

`tauFarsight` est **absent** de `--list-pool` (97 régulières + 8 MoW) → injecté
(`catalog_inject --units tauFarsight` + `build --seed-bc`), recette `case-92` §6. Absent du pool
≠ non confrontable.

Montage : p = `tauFarsight`, `tauDarkstrider` (Hero + `Pulse` R2), `tauAunShi` (Hero, arme `Power`
**sans** Range) [+ `tauMarksman`] ; a = `tauCrisis` (BigTarget), `ultraTitus`.

| bras | natif | port | verdict |
|---|---|---|---|
| sélecteur | buffés `[81 tauFarsight, 83 tauDarkstrider]` (et `[81, 83, 87 tauMarksman]` avec le 4ᵉ allié) | identique | **OK** |
| témoin filtre RANGED | `tauAunShi` (Hero, mêlée seule) **non buffé** | idem | **OK** |
| trait `Unstoppable` | gagné par `[81, 83]` (resp. `[81, 83, 87]`) | idem, et **restitué** au tick de fin de tour | **OK** |
| durée | `remaining: 1` | `duration_turns=1` | **OK** |
| source de l'effet | `source: 81` (le caster) | `source_ref=Caster()` | **OK** |
| magnitude | niveau actif du caster = 50 | `extraDmg[49] = 333`, `extraDmg_2[49] = 721` | **OK** vs kit |

`probe_1210_exemplar_of_the_montka.py` — rc 0.

### Passe de mutants : 10/10 MORDENT

`probe_1210_mutants.py` déforme le code RÉEL, rejoue le cliquet offline, exige un rouge :
filtre RANGED oublié · filtre `Hero` oublié · `applied_traits` vide · branches du `If` inversées ·
gate `IsMeleeAttack` recopié de 1222 · `selectionType` oublié · masque `| 0x10` recopié de
1216/1192 · durée en rounds · `scale_from_source=False` · `op_Addition(Caster, …)` recopié de 1106.
Aucun mutant inerte.

## 6. Ce qui n'est PAS couvert

- **Le filtre `Hero` n'est pas confronté LIVE.** Balayage du pool : **0** unité `lineup` des 97
  spawnables n'est non-Hero, et les 8 MoW n'ont aucune arme au gameconfig (elles échouent au filtre
  RANGED, donc ne discriminent pas le HERO). Le seul porteur naturel est un **summon**
  (`tauSmnDroneSniper` : Summon/Flying/Mechanical/RangedSpecialist, `Piercing` R4) et son montage
  n'a pas abouti — `MV71SniperDroneSquadAttack` (1076) rend `ok:true, mutated:false` sur ce board,
  cible `fromHere` vide au tour 1. Le filtre est gardé **offline**, sur un contexte synthétique où
  les quatre combinaisons existent (`test_1210_…_offline.py`), et le mutant M2 **mord**. Résidu
  **#942-r1**.
- **La MAGNITUDE n'est pas confrontée au NATIF.** Le bras 4 oppose le port au **kit gameconfig**,
  pas au dégât d'une attaque normale réellement portée sous buff. Ce qui manque : deux attaques
  normales (cible BigTarget / non-BigTarget) avec et sans le buff, décomposées par étage. Résidu
  **#942-r2**.
- **La face DÉCISION n'est pas confrontée à un tour d'IA observé.** Le playbook est porté et son
  registre est gardé, mais aucune mesure n'oppose le choix du port au choix natif sur un état où
  `HasNormalAttackTarget` bascule. Résidu **#942-r3**.
- **La carte `{position: cibles}` du slot `0x45`** n'est publiée par aucun canal offline : le port
  itère l'UNION (`abilityTargets(...).targets`) et reconstruit les positions par `castFromTiles`
  quand la seam est câblée, sinon teste depuis l'origine. Borne INF nommée dans le module.
