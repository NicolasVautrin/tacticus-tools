# case-366-r1 — `1116 InescapableAccuracy_extraCritDmg` : le jumeau qui ne partage PAS le canal

> Suite de `case-366-r1-inescapable-accuracy-crit-chance.md` (PR #411), qui portait `1115` et
> laissait `1116` explicitement non porté. **La structure annoncée par cette fiche a été RELUE au
> décompilé avant tout port** — c'est justement quand elle a l'air acquise qu'on se trompe (deux
> réfutations la même semaine : #404 sur `1181`, #411 sur `1115` lui-même).
>
> **Verdict de la relecture : la structure tient, ET elle porte une asymétrie que #411 n'avait pas
> vue** — `extraCritDmg` est la SEULE variable de cette ability scalée par la rareté (§4).

## 1. Identité — relue, pas héritée

Les **trois** classes du passif partagent un unique corps de `$$.ctor` et un unique corps de
`CreateActiveCondition` ; ce qui les distingue est **une** méthode chacune. Les trois tables de
méthodes ont été relues **byte à byte** (trois blocs consécutifs de pointeurs de fonction) :

| bloc | contenu | classe | id |
|---|---|---|---|
| 1 | `.ctor`, `CreateActiveCondition`, `ActiveCondition`, `CreateTargetSelector`, `CreateBlockHitReductionTrigger` | `…_OverridHitsEffect` | **1117** |
| 2 | `.ctor`, `CreateActiveCondition`, `CreateTargetSelector`, **`CreateCritChanceBonus`** | `…_ExtraCritChanceEffect` | **1115** |
| 3 | `.ctor`, `CreateActiveCondition`, `CreateTargetSelector`, **`CreateCritDamageBonus`** | `…_ExtraCritDamageEffect` | **1116** |

Et les trois fabriques allouent bien depuis **trois `Il2CppClass*` différents** avant d'appeler le
**même** corps de ctor (`EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_141/142/143`).
Le ctor relu à l'octet porte `mov edx, 0x45b` puis `mov r8b, 1` ⇒
`BaseEffect$$.ctor(this, op_Implicit(TriggeredAbilityType 1115), hasAutomaticActivation: 1)` —
donc **les trois lisent la config de l'ability `InescapableAccuracy`**, pas celle de leur propre
EffectType. La correspondance classe ↔ id est verrouillée par trois faits indépendants : le nom de
classe (`ExtraCritDamage` ↔ `1116 = InescapableAccuracy_extraCritDmg`), la méthode propre, et la
variable lue (`0x42`, §4).

## 2. Le CANAL — mêmes deux nœuds, autre variable, **autre consommateur**

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracy_ExtraCritDamageEffect$$CreateCritDamageBonus` :

```
EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                         ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect), config@+0x60) )
```

Structurellement identique à `1115` — même paire fusionnée par
`IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`, même `ForAddition`, **seule la variable change**
(`0x41` → `0x42` ; `AbilityVariableType` `65=extraCritChance` / `66=extraCritDmg`). Comme `1115`,
il n'hérite **rien** de `1222 WarHowl_ExtraDamage_Unstoppable` : ni `IsNormalAttack`, ni
`AmountIsGreaterThanZero`.

**Ce qui n'est PAS le même, et c'est tout l'intérêt** : le canal consommateur.

| | `1115` | `1116` |
|---|---|---|
| agrégateur natif | `DamagePrediction$$GetCritChanceBonusFromEffects` | `DamagePrediction$$GetCritDamageBonusFromEffects` |
| consommateur | `DamagePrediction$$RollCritical` = `clamp(GetStat(9) + Σ, 0, 100)` | `DamagePrediction$$CalculateCriticalDamage` = `max(0, GetStat(10) + Σ)` |
| décide | **SI** le coup crite | **DE COMBIEN** |

`GetCritDamageBonusFromEffects(this, attacker, defender, ability)` bâtit lui-même son
`IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner = l'attaquant, target = le
défenseur) puis accumule `addition − subtraction` — le canal natif n'est pas aveugle, et le port
lui thread le même contexte au foyer unique `runner/operations/damage.py::AttackDamageOperation._crit_params`.

Le canal côté port **existait déjà** (`create_effect_crit_damage_bonus_for_attack`, ouvert par
`SagaOfTheWarriorBorn_Owner`) : ce port n'ouvre aucune plomberie, il inscrit un second lecteur.

## 3. GATE — `NOT HasFlag(Owner, UnitFlag.Moved)`, corps PARTAGÉ

```
op_LogicalNot( HasFlag( <DSLSelectors+0x30> = Owner, flag = 0 ) )
```

Un seul corps natif, référencé par les **trois** tables. Le port le rend par une base commune
(`_InescapableAccuracyEffect`), ce qui est le mirror exact de ce fait — et interdit que les deux
volets dérivent l'un de l'autre. Rendu **deux fois**, comme pour `1115` : par `is_active` (la place
native de la condition) et par le gate du canal (`att_ctx["has_moved"]`) — l'agrégateur
`crit_damage_bonus_from_effects` ne filtre PAS sur `is_active`, donc le second est la garde
effective. Même store unique des deux côtés : `UnitFlagsComponent`.

## 4. MAGNITUDE — l'asymétrie que #411 n'avait pas vue

`gameconfig.ability("InescapableAccuracy")` :

```
variables.extraCritChance = [10 … 15]     (65 niveaux, 15 au niveau normalisé 50)
variables.extraCritDmg    = [10 … 728]    (65 niveaux, 554 au niveau normalisé 50)
variablesAffectedByRarityBonus = ["extraCritDmg"]        <-- EXACTEMENT une entrée
```

⇒ **`extraCritChance` n'est PAS scalée, `extraCritDmg` L'EST.** Au montage
(`AbilityVariablesMultiplierPercentage = 180`, rank 17 / niveau 50) la valeur effective est
`round(554 × 1.80) = 997`, pas `554`. Transposer la phrase « aucun scaling de rareté » de la fiche
`1115` aurait donné un port faux de **443 points de crit-damage** — écart qu'aucun test structurel
n'aurait vu, et que la mutation `NOSCALE` (§5) fait rougir LIVE.

`magnitude.ability_var` applique cette règle config-driven toute seule : rien de spécial à coder,
tout à ne pas transposer. Le résidu #382 (« le multiplicateur vient de la SOURCE, le port lit le
PORTEUR ») reste inerte : l'ability pose ses effets sur son propre porteur.

## 5. Le criterion, et les trois bras qui le tranchent

> « Le port ajoute-t-il — **et refuse-t-il d'ajouter après un mouvement, et au contact** — la
> contribution de `1116` comme le natif ? », mesuré là où l'effet MORD : le dégât per-coup d'un
> coup **critique**.

`probe_366_r1_inescapable_accuracy_crit_damage.py`, **trois bras × quatre mutations
adversariales**. Porteur `eldarMauganRa` (HERO, dans le pool), cible `necroWarden`.

**`--crit 100,700` — et c'est une contrainte, pas un confort.** `1116` ne modifie que le MONTANT
d'un crit : il faut donc que le coup crite dans **les deux** bras de mouvement, sinon le bras
`MOVED` ne traverserait même pas `CalculateCriticalDamage` et ne garderait rien. À `GetStat(9)=100`
le crit est certain des deux côtés, et la seule variable est le montant.

**Contournement du résidu `#366-r1-crit-multihit`** (l'étage CRIT diverge dès le 3ᵉ coup d'une
salve, indépendamment de toute ability — tagué `[fable]`, hors de ce cas) : **salve d'UN coup**,
imposée au natif par le seed BC (`Weapons[].Hits = 1` ; le bras MELEE patche les **deux** armes,
la frappe de contact utilisant `weapons[0]`, 5 coups au kit). C'est le même contournement que
#411, transposé au bras de contact.

Autres contraintes de montage, chacune payée par une mesure fausse évitée : géométrie
`2 <= d <= 3` avant ET après le pas pour les bras ranged (au contact l'attaque bascule sur l'arme
mêlée) ; `--block-target 0,0` (le canal BLOCK de la cible est celui du jumeau NON PORTÉ `1117`) ;
ennemis sans `Overwatch`.

⚠ **`extraCritDmg` n'est PLUS neutralisé dans le seed BC**, et le montage de `1115` a été corrigé
en conséquence. Tant que `1116` n'était pas porté, `extraCritDmg = 0` le rendait inerte **des deux
côtés**. Depuis ce port, le même geste **inverse** son effet : le patch vit dans le BC (donc le
NATIF le voit) alors que le port lit `gameconfig` — il ferait diverger tout coup critique. Le
paramètre existe encore (`--zero-crit-dmg`), documenté comme **désynchro volontaire de
diagnostic**.

### 5.1 Le carré, mesuré

MC1_67 / seed 777, puis C1_25 / seed 31337 (board à élévation — le crit traverse aussi l'étage
%-list). Toutes les cellules sont le **premier coup**, seul point où les deux modèles sont sur la
même case du flux PRNG (le port produit 5-6 coups, le natif 1 — résidu de SOURCE §7.2 de #411).

| bras | board/seed | LIVE | OFFLINE | mutation → rejeu |
|---|---|---|---|---|
| **NOMOVE** | MC1_67/777 | `[4548]` | `[4548]` | `NOCHANNEL` → `[3158]` ; `NOSCALE` → `[4530]` |
| **MOVED** | MC1_67/777 | `[2195]` | `[2195]` | `NOGATE` → `[4158]` |
| **MELEE** | MC1_67/777 | `[1349]` | `[1349]` | `NORANGEGATE` → `[3103]` |
| **NOMOVE** | C1_25/31337 | `[3834]` | `[3834]` | `NOCHANNEL` → `[2189]` ; `NOSCALE` → `[2963]` |
| **MOVED** | C1_25/31337 | `[1333]` | `[1333]` | `NOGATE` → `[2785]` |
| **MELEE** | C1_25/31337 | `[1333]` | `[1333]` | `NORANGEGATE` → `[2785]` |

Les six cellules sont **bit-exactes**, et les **huit** mutations changent toutes le rejeu :

* `NOCHANNEL` (inscription retirée d'`EFFECT_CLASSES`) — sans le canal le crit vaut `GetStat(10)`
  seul. `3158` est exactement la valeur que #411 mesurait pour son bras NOMOVE, quand `1116`
  n'était pas porté : les deux fiches se recoupent sur la même cellule ;
* `NOSCALE` (multiplicateur forcé à 100, soit `554` au lieu de `997`) — **le scaling de rareté est
  charge utile, prouvé en live**, pas une règle de config décorative ;
* `NOGATE` (les deux mirrors de l'`ActiveCondition` désarmés) — le port frapperait à `700 + 997`
  là où le natif, qui a vu `HasFlag(Moved)`, frappe à `700` ;
* `NORANGEGATE` (nœud `IsRangedAttack` désarmé) — le port appliquerait le bonus à une frappe de
  contact. **Ce bras est nouveau** : ni #411 ni ce canal n'avaient jamais confronté `IsRangedAttack`
  en live, seulement offline.

Cliquet `tests/engine/runner/test_inescapable_accuracy_crit_damage_live.py` : **11 passed**
(3 structurels offline + 8 live). Le cliquet de `1115`, re-joué avec le montage corrigé, reste à
**7 passed** — et il confronte désormais les DEUX volets à la fois.

## 6. Ce qui n'est PAS couvert

* **`1117 InescapableAccuracy_overrideHits`** (canal `BaseEffect$$BlockHitsReduction`, non porté
  côté moteur) : troisième canal, hors périmètre. Il reste neutralisé par `--block-target 0,0`.
* **La face PRÉDICTION.** `crit_damage_bonus_from_effects` **et** `crit_chance_bonus_from_effects`
  ne sont appelés que depuis `runner/operations/damage.py` (vérifié par balayage : 4 fichiers
  citent les deux noms, aucun sous `services/` ou `playbook/`). `services/damage_prediction.py`
  ne lit que `attacker_ctx.crit_damage` = `GetStat(10)` brut ⇒ le +extraCritDmg n'entre pas dans la
  prédiction. **Gap PRÉEXISTANT du canal**, partagé avec `SagaOfTheWarriorBorn_Owner` et `1222` —
  pas de ce port, et il ne se ferme pas ability par ability.
* **Le vecteur OVERWATCH** de Maugan Ra n'est pas exercé (il passe par `damage_ops/normal.py` avec
  `_ranged = True`, donc `IsRangedAttack` s'y ouvrirait ; l'`ActiveCondition` porte sur le
  `UnitFlag.Moved` de l'OWNER, purgé au `StartTurnOperation`). Non mesuré.
* **Le vecteur ABILITY.** Le natif ne porte **pas** de `IsNormalAttack` ⇒ le bonus vaut aussi pour
  une attaque d'ability à distance. Verrouillé **offline seulement**
  (`test_gates_are_tristate_offline`) : aucun montage live ne l'exerce ici.
* **`crit_damage_bonus_from_effects` ne balaie que les effets de l'ATTAQUANT** alors que le natif
  énumère les entités porteuses d'effets de tout l'état (l'axe DÉFENSEUR du canal —
  `AmuletOfTheVoidwyrm_CritDamageReductionEffect` — reste un gisement séparé). Sans conséquence
  pour `1116`, dont le trigger commence par `get_OwnerIsCaster`.
* **Les salves multi-coups à crit non nul**, non confrontables tant que `#366-r1-crit-multihit`
  est ouvert. Ce cas le CONTOURNE (salve d'un coup), il ne le corrige pas.

## 7. Résidus

### 7.1 `#366-r1-crit-multihit` — inchangé, contourné

Voir `case-366-r1-inescapable-accuracy-crit-chance.md` §7.1 : **CANDIDAT fable-solver**, mesuré et
attribué hors de ces deux cas (reproduit sur `necroDestroyer`, en mêlée, avec un étage de base
sain). Ce cas n'apporte aucune donnée nouvelle dessus — son montage l'évite par construction
(1 coup), et ses trois bras à `--crit 100,700` sont hors du régime où il a été observé
(`--crit 0,700` / `50,700`).

### 7.2 Le nombre de coups vient du GAMECONFIG côté port, du BC côté natif

Inchangé (#411 §7.2) : `battle_query.select_weapon_pierce` lit les armes du gameconfig par
`visualId`, le natif lit `BC.Units[].Weapons[].Hits`. C'est ce qui impose la confrontation sur le
préfixe `len(live)`. Résidu de SOURCE, non corrigé.

### 7.3 Le montage `--zero-crit-dmg` a changé de nature, pas de code

Le paramètre existe toujours dans `probe_366_r1_inescapable_accuracy_crit_chance.neutralized_seed_bc`,
mais son défaut est passé à `False` et sa docstring dit maintenant ce qu'il fait **depuis que 1116
est porté** : une désynchronisation délibérée BC ↔ gameconfig, qui doit faire diverger. C'est un
piège de montage générique — **tout patch de variable d'ability posé dans le seed BC est invisible
du port** — et il ne concerne pas que ce cas.
