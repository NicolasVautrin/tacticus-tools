# #419-r1-tr9-r4-r1 — le contexte du fold est celui de l'ATTAQUE PORTEUSE (résidu RÉFUTÉ)

**Verdict : le résidu est RÉFUTÉ — au décompilé ET par mesure. Aucun changement de comportement à
livrer.** Le natif ne passe pas « l'`AbilityOrEffect` du passif » à `GetAttackHits` : il passe le
paramètre `abilityState` que `PredictAttack` a lui-même reçu, c'est-à-dire l'`AbilityState` de
l'**attaque porteuse**. Le port, qui réutilise les arguments de coups de l'attaque porteuse
(`is_normal_attack=True`), était déjà fidèle — et l'est **structurellement**, puisque base et fold
partagent le même objet. Coder le résidu aurait **cassé** le port de `−1` coup sur tout porteur
cumulant (mesuré : `(−295, −443, −1)`).

Ce qui change quand même : **deux affirmations du dépôt étaient fausses** et sont corrigées
(§3, §4), et le résidu jumeau `#419-r1-tr9-r4-r2` (`hitGroupIndex`) est **tranché** (§5).

## 1. Ce que le décompilé dit — et pourquoi la lecture d'origine s'est trompée

La cause racine est un **piège de nommage Ghidra**. La signature réelle, lue dans
`data/symbols/rnca9r7q6c/frida/methods.tsv` :

```
IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility.GetAdditionalDamagePrediction
  -> IdunBattle.Core.Services.DamagePredictionResult
     entities    : IdunBattle.Entities.Abilities.AbilityEntities     (0x128 octets)
     abilityState: IdunBattle.Configuration.AbilityState             (12 octets)
```

Méthode d'**instance** rendant un struct de 0xa0 : la convention est
`(retbuf, this, entities, abilityState, MethodInfo*)`. Ghidra, qui croit la méthode statique à trois
arguments, nomme donc `this` → « entities », `entities` → « abilityState », et **ne montre pas du
tout** le vrai `abilityState` (il n'apparaît que comme un `in_R9` non déclaré). Les trois lectures
faites sur `entities+0x60` (la `AbilityConfiguration`, celle du **passif**) portent donc en réalité
sur le `this` de l'ability — d'où la conclusion « le contexte vient du passif ». Elle ne suit pas :
le contexte ne vient pas de `this`, il vient du 4e argument.

**L'origine de ce 4e argument, lue à l'assembleur** (`Boltstorm_NormalAttackAbility$$PredictAttack`,
prologue) :

```
mov  rsi, r9                 ; RSI <- le parametre `abilityState` recu
...
mov  eax, [rsi+8]            ; ) copie des 12 octets
movsd xmm0, [rsi]            ; )
mov  [rsp+0x38], eax         ; ) vers le slot local [rsp+0x30]
movsd [rsp+0x30], xmm0       ; )
...
lea  r9, [rsp+0x30]          ; R9 <- CE MEME slot, au call de GetAdditionalDamagePrediction
```

Aucune autre écriture ne touche ce slot entre les deux points. **Le fold reçoit donc, bit pour bit,
l'`AbilityState` de l'attaque porteuse.** Le mold jumeau
`RighteousRepugnance_NormalAttackAbility$$GetAdditionalDamagePrediction` porte le corps identique et
la même signature.

## 2. La chaîne complète, du fold jusqu'au nœud DSL

Aucun maillon deviné — chacun lu :

1. `GetAdditionalDamagePrediction` : `AbilityOrEffect ao = op_Implicit(abilityState)`. L'overload est
   celui qui écrit `set_ActiveAbility` (résolu par le `call rel32` : `AbilityOrEffect$$op_Implicit`
   dont le corps appelle `IdunBattle.Core.AbilityOrEffect$$set_ActiveAbility`). Le **second**
   `op_Implicit` du corps, celui qui alimente le slot `0x28`, est **le même** overload.
2. Slot `0xb5` de l'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$GetAttackHits`, surcharge
   **`ability: IdunBattle.Core.AbilityOrEffect`** — et non la surcharge
   `context: IdunShared.AbilityExecutionContext` : les deux existent, et c'est l'argument construit
   (24 octets, `AbilityOrEffect` = taille boxée 40) qui tranche.
3. Cette surcharge **alloue** un `IdunShared.AbilityExecutionContext` (classe réf., 104 octets), y
   écrit à `+0x10..+0x28` un `Nullable<AbilityOrEffect>` bâti sur `ability`, laisse le reste à zéro,
   et délègue à `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits(attacker, defender,
   hitGroupIndex, context, weaponHits)`.
4. Celui-ci **synthétise un `AbilityEntities`** (`AbilityEntities$$.ctor(caster=attacker,
   actor=attacker, target=defender, …, currentAbilityOrEffect=<ctx+0x10>, …,
   hitGroupIndex=<Nullable(param)>)`) et l'évalue contre les descripteurs de bonus de coups.
5. `IdunBattle.Entities.Triggers.AbilityIsNormalAttackTrigger$$ShouldTrigger` lit ce
   `AbilityEntities`, en extrait l'`ActiveAbilityType` par un `IAbilityTypeSelector`, et rend
   `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`.

⇒ Le nœud `IsNormalAttack` est donc évalué **sur l'ability de l'attaque porteuse**. Puisque la base
et le fold passent le même objet, ce nœud vaut **la même chose aux deux étages** : le port ne peut
pas y diverger, quel que soit son modèle.

## 3. « Seul consommateur d'`IsNormalAttack` » — FAUX, re-balayé

Le résidu et le commentaire de `engine/services/attack_hits_formula.py` désignaient
`PowerTrip_FullHealthEffect` comme unique consommateur. Le balayage des xrefs des **deux** surcharges
de `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack` (2026-08-02, `rnca9r7q6c`) rend **31 + 7**
fonctions appelantes, dont **six** sur le canal COUPS :

| effet | trigger, lu au décompilé | porté ? |
|---|---|---|
| `PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack` | `IsNormalAttack & get_OwnerIsCaster` | oui |
| `Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack` | `IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster` | oui |
| `Dakka_ExtraHitsEffect$$CreateEffectHitsBonusForAttack` (1105) | `AmountIsEqual(MinDistance,·) & AmountIsEqualOrGreater(AttackWeaponRange,·) & get_OwnerIsActor & IsNormalAttack & IsRangedAttack` | **non** |
| `ShroudPsalmEffect$$CreateEffectHitsBonusForAttack` (1366) | `get_OwnerIsTarget & IsNormalAttack` (MALUS défenseur, `ForAdditionWithMinimum`) | **non** |
| `VoltagheistField_ExtraHitEffect$$CreateEffectHitsBonusForAttack` (1381) | `get_OwnerIsCaster & IsNormalAttack` | **non** |
| `LegendaryCommander_ExtraHitsEffect$$IsValidAttack` (1395) | en NÉGATION : `… & !IsNormalAttack(<sél.>) & !(TriggeringAbilityIsNormalAttack & IsPartialAttackAbility)` | **non** |

Les quatre non portés sont dans `engine/entities/effect_type.py` mais **absents** du registre
`engine/entities/effects/factory.py`. Le commentaire est corrigé et la liste y est désormais
explicite.

## 4. `IdunBattleLogic.Entities.DSLFactory$$Is*` n'existe pas

Le port citait `IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack`. Ce symbole n'existe **ni** dans
le dump Ghidra **ni** dans le dump Frida de `rnca9r7q6c` : le namespace réel est **`DSLTriggers`**
(`DSLTriggers$$IsNormalAttack`, `$$IsMeleeAttack`, `$$IsRangedAttack`,
`$$IsFirstHitGroupInAttack`). Corrigé dans `attack_hits_formula.py` ; les autres occurrences sont un
résidu nommé (§7).

## 5. `#419-r1-tr9-r4-r2` (`hitGroupIndex`) — TRANCHÉ

Le fold passe littéralement `0` (`xor r8d, r8d`). Ce n'est **pas** une constante de façade : c'est un
vrai paramètre, que `DamagePrediction$$GetAttackHits` pose en `Nullable<int>` dans l'`AbilityEntities`
synthétisé. Il n'atteint le DSL que par un chemin, et un seul :

```
AbilityEntities.hitGroupIndex
  -> IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHitGroup      (HasValue && Value == 0)
  -> Idun.Source.IdunBattle.Logic.Entities.Triggers.IsFirstHitGroupInAttackTrigger$$ShouldTrigger
  -> IdunBattleLogic.Entities.DSLTriggers$$IsFirstHitGroupInAttack
  -> UNIQUE appelant : IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$CreateEffectHitsBonusForAttack
```

Recoupé par une **seconde source indépendante** : balayage de `data/symbols/rnca9r7q6c/ghidra/functions.tsv`
— qui contient les génériques pleinement partagés, absents du dump Frida — sur `HitGroupIndex` :
**zéro** symbole hors les signatures de `GetAttackHits` / `AbilityEntities..ctor` / `ExecuteHit` /
`CalculateAbilityDamage`. Il n'existe donc **aucun getter ni sélecteur DSL** de ce champ.

**Ce que le port doit en faire : rien**, tant que `LegendaryCommander_ExtraHits` (1395) n'est pas au
registre. Le jour où il y entre, le fold vaut `IsFirstHitGroup == True` (le natif y passe `0`), et il
faudra une clé `is_first_hit_group` dans le board de la formule de coups.

## 6. La confrontation — le montage que la fiche d'origine disait impossible

La fiche `case-419-r1-tr9-r4` §5 écrivait « NON CONFRONTÉ : il faudrait un attaquant portant
`PowerTrip` **et** l'un des deux passifs de fold ». C'est exact comme constat de kit — `PowerTrip`
(1285) est le passif d'`orksKillaKan`, `Boltstorm` (1090) celui de `templAggressor`, aucune unité ne
les cumule — mais ce n'est **pas** un verdict de non-confrontabilité : la **greffe de passif**
(`case-92` §5bis, outillée par `catalog_inject.graft_passive_ability`) le monte.

`probe_419r1tr9_r4_r1_fold_context.py` — board `MC1_67`, seed `41904`, géométrie `plain` (3 cibles à
distance 2, même élévation, hors cover : **aucun** malus de coups en jeu, le `+1` de `PowerTrip` est
le seul terme qui bouge). Les **quatre bras partagent le même catalogue** (la config `PowerTrip` est
posée dans les quatre) et ne diffèrent **que** par `BC.Units[templAggressor].PassiveAbilities` :

| bras | `PassiveAbilities` | attaque normale concrète |
|---|---|---|
| `fold_pt` | `[1090, 1285]` | `1128` |
| `base_pt` | `[1285]` | `69` |
| `fold` | `[1090]` | `1128` |
| `base` | `[]` | `69` |

### Mesures (`appliedHits` ; bornes RAW entre parenthèses)

```
              fold_pt   base_pt   fold    base
astraBullgryn   h8        h4       h6      h3
tauAunShi       h8        h4       h6      h3
necroWarden     h8        h4       h6      h3

attestation : base_pt - base = +1 sur les 3 cibles   (PowerTrip MORD sur la base)
fold sans PowerTrip = fold  - base    = 3
fold avec PowerTrip = fold_pt - base_pt = 4          -> GAIN = +1
```

**Les quatre mesures sont NATIVES** : le port n'entre pas dans la définition du verdict. Le fold
gagne le coup gaté `IsNormalAttack` ⇒ le contexte qu'il passe rend `IsRegularAttack` **vrai** ⇒
**c'est l'attaque porteuse**. L'hypothèse « contexte du passif » prédisait `GAIN = 0` : elle est
réfutée par la mesure, pas par un argument.

### Accord port/natif et contre-épreuve

Port == natif **12/12**, champ à champ (bornes RAW + `appliedHits`), sur les 4 bras × 3 cibles.
Sur les bras `base*` le port est apparié à registre de fold vide (`port_fields(fold=False)`) : le
port dispatche le fold par le **kit gameconfig**, que retirer `Boltstorm` du BC ne touche pas — ce
n'est pas une divergence mais le protocole de mesure de #446-r1 §4.

Contre-épreuve `ctx_passive` (le port sous l'hypothèse du résidu, `is_normal_attack=False` injecté au
passage du fold) — critère = **déplacement par rapport au port non muté** :

| bras | déplacement |
|---|---|
| `fold_pt` | `(−295, −443, −1)` / `(−367, −1105, −1)` / `(−295, −705, −1)` — **MORD** |
| `base_pt` | idem — MORD (le port folde toujours, cf. dispatch gameconfig) |
| `fold` / `base` | `(0, 0, 0)` — **ne mord pas** (aucun porteur de gate) |

Le mutant est donc **discriminant** : il mord exactement là où un bonus gaté `IsNormalAttack` est en
jeu, et nulle part ailleurs.

## 7. Ce qui a été rejoué, et les résidus

Garde jumelle `scripts/python/tests/engine/test_419r1tr9_r4_r1_fold_context_live.py` : **5 tests,
0 skip**, 107 s, 4 runners construits et libérés au fil de l'eau.
**Contre-épreuve de la garde elle-même** : le comportement retiré du port (fold forcé en contexte
passif), elle rougit sur **3** tests (`test_port_matches_native_everywhere`,
`test_port_fold_gains_the_hit_too`, `test_counter_probe_bites`) — et les **2** tests purement natifs
(`test_montage_installed`, `test_fold_context_is_the_carrier_attack`) restent verts, ce qui atteste
que le verdict ne dépend pas du port.

Non-régression du foyer : `test_419r1tr9_r4_boltstorm_pred_live` (6), `test_446_r1_boltstorm_followup_live` (5),
`test_446_r3_repugnance_followup_live` (5), `test_419r1tr9_rapid_fire_live` (7) — **23 passés, 0 skip**.

### Résidus NOMMÉS

* **`#419-r1-tr9-r4-r1-r2`** — **quatre** effets natifs du canal COUPS portent le gate
  `IsNormalAttack` et ne sont **pas portés** : `Dakka_ExtraHits` (1105), `ShroudPsalm` (1366),
  `VoltagheistField_ExtraHit` (1381), `LegendaryCommander_ExtraHits` (1395). Ils ont leur entrée dans
  `entities/effect_type.py` mais aucune dans le registre `entities/effects/factory.py`. Chacun est un
  terme manquant de `AttackHitsWithModifiersFormula` chez son porteur ; `ShroudPsalm` est un **malus
  défenseur**, donc le port sur-compte les coups contre un porteur — la forme de dégradation la plus
  exploitable en entraînement.
* **`#419-r1-tr9-r4-r1-r3`** — le port cite `IdunBattleLogic.Entities.DSLFactory$$Is*` (`IsNormalAttack`,
  `IsMeleeAttack`, `IsCharging`, …), symboles qui **n'existent dans aucun des deux dumps** ; le
  namespace réel est `DSLTriggers`. Corrigé dans `attack_hits_formula.py` (périmètre de ce cas) ;
  les autres occurrences restent. Un `migrate_va_to_symbol`-like sur les *namespaces* fantômes serait
  le geste propre — aucun cliquet ne voit cette faute aujourd'hui.
* **`#419-r1-tr9-r4-r3` (hérité, inchangé)** — la face COMBAT du fold n'est pas portée. La question
  « le fold d'exécution passe-t-il le même contexte ? » ne se pose pas encore, et **ne se déduit pas**
  de ce cas : `AttackDamageOperation$$GetAttackHits` prend un `abilityOrEffect` ET des
  `AttackDamageOptions`, signature différente de la façade prédiction.

### Ce que ce cas n'établit PAS

* **Le régime `melee`.** La confrontation n'a été jouée que sur le mold RANGED (`Boltstorm` /
  `templAggressor`). Le mold jumeau `RighteousRepugnance` a un corps **identique**, vérifié ligne à
  ligne, mais n'a pas été confronté sur cet axe. `Waaagh_ExtraHits` (gate
  `IsNormalAttack & IsMeleeAttack`) en serait le porteur naturel, greffable de la même façon.
* **Le `hitGroupIndex` de la BASE.** Le fold passe `0` ; ce que passe la base n'a pas été lu (la
  façade prédiction est atteinte par slot d'interface, sans xref directe). Sans conséquence tant que
  `LegendaryCommander_ExtraHits` n'est pas porté — c'est son seul lecteur.
* **Le contexte sous un autre `AbilityState`.** La mesure ne couvre que l'attaque normale concrète
  `1128`. Que `IsRegularAttack` reste vrai pour toutes les attaques normales concrètes est une
  lecture du nom du prédicat, pas une mesure.
