# #911 — `1203 DaemonicPatrons` (`emperFlawlessBlade` « Hascule »), face COMBAT

**Verdict : PORTÉ et CONFRONTÉ LIVE.** Avant cette tranche, 1203 était absente d'`ABILITY_CLASSES` :
le cast partait, l'`AbilityHandler` rendait `ported=False`, et **rien** ne se passait — 0 taunt,
0 buff, aucune erreur.

## 1. La prémisse `EFFECT/BUFF` de l'audit ne décrit qu'une mécanique sur deux

`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicPatronsAbility$$ExecuteBehaviour`, tel que LU
(build `rnca9r7q6c`) :

```
turns = Sum( TurnsFromRounds( GetNumberConstant(0x45 = nrOfRounds) ), Const(1)@DSLFormulas+0x20 )
bond  = AddBondEffect( 27 Taunted_OnlySpecificTargets, AbilityStateReference,
                       source = caster@0x48, targets = target@0x60, bondedEntity = caster@0x48, turns )
extra = AddEffect( 1464 DaemonicPatrons_ExtraDamage,  AbilityStateReference, owner@0x30, owner@0x30, turns )
reduc = AddEffect( 1465 DaemonicPatrons_DmgReduction, AbilityStateReference, owner@0x30, owner@0x30, turns )
AActiveAbility.Execute( bond & (extra & reduc) )
```

**L'arbre pose d'abord un TAUNT**, sur la CIBLE — 1203 n'est pas un self-buff. Et ce n'est pas
décoratif : le compte d'ennemis adjacents **TAUNTÉS** est exactement ce qui module les deux buffs.
L'i2 le dit dans cet ordre (« Taunts an adjacent enemy, **and** Hascule gets *watched* … »).

Aucune attaque, aucun `If`, aucun `AtomicGroup` — la callee finale est
`IdunBattle.Entities.Abilities.AActiveAbility$$Execute` à DEUX arguments.

## 2. L'étage qui rend les deux effets dynamiques

`IdunBattle.Entities.Effects.Loki.ADaemonicPatronsEffect$$GetNumAdjacentTauntedEnemies` — la BASE
native commune ; aucune des deux sous-classes ne la surcharge.

```
n = Count( Filter( AdjacentEnemies(Owner@0x30, unique: 1, selectionType: 3),
                   HasEffect(It@0x68, 27, onlyActive: 0, targetType: 6) ) )
```

- `ADaemonicPatronsEffect$$CreateActiveCondition` = `AmountIsGreaterThanZero(n)` ;
- `DaemonicPatrons_ExtraDamageEffect$$GetCurrentExtraDamage` = `Multiply(ConfigVar(0x8 = extraDmg), n)`
  → **`ForAddition`** (slot `+0x10`), trigger `get_OwnerIsCaster` ;
- `DaemonicPatrons_DmgReductionEffect$$GetCurrentDamageReduction` =
  `Min(Const(100)@DSLFormulas+0x30, Multiply(ConfigVar(0x46 = dmgReductionPct), n))`, puis
  `CreateEffectDamageMalusForDefense` = `Multiply(Const(-1)@+0x38, .)` → **`ForPercentIncrease` à
  montant NÉGATIF** (slot `+0x08`), trigger `get_OwnerIsTarget`.

⚠ **Le natif n'appelle PAS `ForPercentDecrease`** : il écrit au slot de `ForPercentIncrease` un
montant négatif. Le mirror est `for_percent_increase(False, -reduction)`.
⚠ **Le cap porte sur le PRODUIT**, pas sur le facteur : `Min(100, pct × n)`.
⚠ Les cinq constantes `+0x18/+0x20/+0x28/+0x30/+0x38` (`0/1/2/100/-1`) sont LUES dans
`IdunBattleLogic.Entities.DSLFormulas$$.ctor`, jamais devinées d'un offset opaque.

## 3. Masque — forme PRESET + FLAGS, surcharge tranchée par les XREFS ENTRANTES

`DaemonicPatronsAbility$$.ctor` recopie les 0x40 octets de `<TargetingOptions statics>+0x40`, puis
appelle `TargetingOptions..ctor(&opts, &preset, 0x200000000)`. **Critère réellement employé** : les
xrefs entrantes du call-site — il vise l'entrée que `VexillaMagnificaAbility$$.ctor` (1183) et
`HolyDuelAbility$$.ctor` (1050) visent aussi, dont le corps RELU est
`rules = additionalRules | template.rules`.

Preset relu dans `TargetingOptions$$.cctor` : `+0x00 = 0` (`isSelfCasting`), `+0x08` = copie de
`<TargetingRange statics>+0x30` (RANGE_ADJACENT), `+0x20 = 1` (`RangedBool.False`), `+0x28 = 0x4000`.

⇒ masque EFFECTIF **`0x200004000`** = `TargetIsEnemy | TargetIsNotAnObject`. `AbilityAttackType` = le
littéral **0** du 3ᵉ argument d'`AActiveAbility..ctor` — TRANSCRIT, alors que l'arbre ne frappe pas.

## 4. Ce que la confrontation mesure

Montage : `emperFlawlessBlade` est **hors pool ET hors catalogue** → `catalog_inject` (§6 de
`case-92`). Board `MC1_67`, positions FORCÉES : caster (3,4), **deux** ennemis adjacents (3,5) et
(2,4), **un seul sera taunté** — c'est ce second ennemi qui rend le `Filter` discriminant.

`probe_911_daemonic_patrons.py`, six étages, tous verts :

| étage | mesure | natif | port |
|---|---|---|---|
| témoin (sans buff, attaque du caster) | dégât total | 3731 | **3731** |
| témoin (sans buff, dégât reçu) | dégât total | 5991 | **5991** |
| E1 pose + durée POSÉE | (cible, 3) / (caster, 3) / (caster, 3) | idem | **idem** |
| E2 compteur | tauntés / adjacents | — | **1 / 2** |
| E2b magnitudes par `n` | — | — | `+499·n` ; `-30·n` capé **-100** |
| E3 extra-damage | dégât total | 4585 | **4585** |
| E4 réduction | dégât total | 3724 | **3724** |

E3 et E4 exigent en plus que le montant DIFFÈRE du témoin (`4585 ≠ 3731`, `3724 ≠ 5991`) : un accord
obtenu en régime dégénéré ne prouverait rien.

⚠ **La durée POSÉE se lit dans les events du cast** (`Effect_RemainingTurns=3`), jamais dans
`decisionView` : ce dernier est capturé APRÈS le `[EndTurn]` que le cast déclenche, et son
`remaining` vaut déjà **2**. Comparer ce champ au port ferait rougir un port juste, et le
« corriger » d'un `+1` serait un fit.

## 5. Mutants — les cinq MORDENT (`probe_911_mutants.py`)

| # | mutation | tué par |
|---|---|---|
| M1 | `Filter(…, HasEffect(It, 27))` collapsé | E2 (1→2), E3 (6829 vs 4585), E4 (2236 vs 3724) |
| M2 | signe de la réduction inversé | E2b, E4 (7184 vs 3724) |
| M3 | `Min(Const(100), …)` retiré | E2b (`-120` à `n = 4`) |
| M4 | `duration_rounds` au lieu de `duration_turns` | E1 (durée 6 au lieu de 3) |
| M5 | facteur `× n` retiré de l'extra-damage | **E2b seul** — AVEUGLE aux quatre étages live |

M5 est la raison d'être d'E2b : le cast ne taunte qu'UNE cible, donc le live ne dépasse jamais
`n = 1`, où `v × 1 == v`.

## 6. Ce qui n'est PAS couvert

- **Résidu `#911-r1`** — la triggered `1473 DaemonicPatrons_Finale`, qui porte les deux dernières
  phrases de l'i2. RE **déjà lue** (citée dans `engine/runner/abilities/emperorschildren.py`) ;
  ce qui manque est le CANAL d'inscription : 1473 n'est ni dans `activeAbilities` ni dans
  `passiveAbilities` du kit, et le `CreateBehaviour` de la face SUCCESS n'a aucun symbole propre
  (corps dédupliqué) — il reste à lire par le slot de vtable.
- **La face DÉCISION** : la clé `adjacent_taunted_enemies` est posée dans `Scene.unit_state` et dans
  les deux ctx de prédiction, mais aucun étage ne la confronte à `attackPlans`. Côté prédiction
  d'attaque normale elle est évaluée à la position COURANTE, pas à la tuile CANDIDATE (contraste
  assumé avec `tiles_moved_this_turn`, dit au site).
- **`selectionType: 3`** (`OnlyAliveAndTargetable`) n'est pas consommé par la couche sélecteur
  (résidu PARTAGÉ `#433-r3-r2`) : un cadavre encore posé et toujours taunté serait compté par le
  port, pas par le natif.
- **`TargetIsNotAnObject`** est au registre ; le gate `HasTrait(cible, Object)` reste le résidu
  partagé de tous les porteurs de ce bit.
