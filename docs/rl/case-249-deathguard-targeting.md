# Case 249 — les cinq masques de ciblage du module `deathguard`, et l'oracle qui ment pour une MoW

`RevitalizingMalignancy` (1037), `SpawnPoxwalkers` (1040), `FlailSwing` (1042),
`EntropyCannons` (1168) et `PlagueburstMortar` (1169) entraient dans `ABILITY_CLASSES` **sans**
`TARGETING_OPTIONS`. `get_invalid_target_reason` / `get_invalid_caster_reason`
(`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en self-play.

## 1. Les cinq masques, lus un par un

Aucun n'a été déduit d'une voisine, et c'était nécessaire : **les cinq abilities du module se
répartissent sur deux formes de ctor différentes, avec quatre `TargetingRange` distincts et cinq
masques sans rapport.**

| id | forme de ctor | `isSelfCasting` | `TargetingRange` | `forceMeleeTarget` | `rules` | `AbilityAttackType` |
|---|---|---|---|---|---|---|
| 1037 | 1 — flags directs | **1** | `TargetingRange statics+0x30` = `RANGE_ADJACENT` | `1` = `RangedBool.False` | **`0x8500`** | `2` Others |
| 1040 | 1 — flags directs | **1** | `TargetingRange$$CustomRange(GetRange)` — **délégué** | `1` | **`0x8000000004`** | `1` SummonAndAttackTarget |
| 1042 | **3 — preset statique copié, aucun ctor** | 0 | `RANGE_ADJACENT` (via le preset) | `1` | **`0x4000`** | `0` DirectTargetAttack |
| 1168 | 1 — flags directs | 0 | `TargetingRange statics+0x48` = `RANGE_WHOLE_BOARD` | `1` | **`0x40004002`** | `0` |
| 1169 | 1 — flags directs | 0 | `RANGE_WHOLE_BOARD` | `1` | **`0x40000042`** | `0` |

Symboles : `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$.ctor`,
`...Loki.SpawnPoxwalkersAbility$$.ctor`, `...Loki.FlailSwingAbility$$.ctor`,
`IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$.ctor`,
`...Active.PlagueburstMortarAbility$$.ctor`.

### Décompositions — exhaustives, aucun bit résiduel

| id | bits | somme |
|---|---|---|
| 1037 | `0x100` `TargetIsHealable` (8) + `0x400` `TargetIsFriendly` (10) + `0x8000` `CasterIsPossibleTarget` (15) | `0x8500` ✔ |
| 1040 | `0x4` `CasterMatchesDynamicRule` (2) + `0x8000000000` `TargetIsCaster` (39) | `0x8000000004` ✔ |
| 1042 | `0x4000` `TargetIsEnemy` (14) | `0x4000` ✔ |
| 1168 | `0x2` `TargetMatchesDynamicRule` (1) + `0x4000` `TargetIsEnemy` (14) + `0x40000000` `AllowNullCasterTile` (30) | `0x40004002` ✔ |
| 1169 | `0x2` + `0x40` `TargetIsTile` (6) + `0x40000000` | `0x40000042` ✔ |

Un test **offline** verrouille cette arithmétique
(`test_les_cinq_masques_sont_poses_et_portent_leur_range`) : si un bit manque ou est en trop, la
somme ne retombe plus sur le littéral du ctor.

`AllowNullCasterTile` est la **signature d'une ability de Machine of War** : le caster est
hors-plateau et n'a pas de tuile. C'est un ALLOW du volet CASTER, jamais une règle de refus du
filtre cible — le compter comme telle inventerait un refus.

### 1042 et 1043 : le même preset, deux masques

`FlailSwingAbility$$.ctor` n'appelle **aucun** `TargetingOptions$$.ctor` : il recopie les 0x40 octets
du champ statique `TargetingOptions statics+0x40` puis passe directement à
`AActiveAbility..ctor(this, &opts, 0, 0)`. Le masque effectif est donc `*(statics+0x68)` = `0x4000`,
constante écrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor`.

C'est **exactement le preset de `ThunderousAssault` (1043, case-246)** — mais 1043 le passe à la
surcharge **PRESET + FLAGS**, qui OR-e `0x10000000`, et vaut donc `0x10004000`. Deux abilities, un
seul preset, deux masques. Le preset ne suffit jamais : il faut lire **quelle forme** l'ability
emploie.

### 1040 : le seul `TargetingRange` du registre qui ne soit pas un statique

`SpawnPoxwalkersAbility$$.ctor` construit un délégué `IdunBattle.Core.Services.GetRange`
(cible **nulle** ⇒ méthode statique) et le passe à la surcharge **délégué** de
`IdunBattle.Core.Services.TargetingRange$$CustomRange` — celle qui écrit
`{onlyAdjacent = RangedBool.False, overrideRange = <vide>, overrideRangeFunc = <le délégué>}`, à
distinguer de la surcharge `int` déjà portée (`custom_range`).

`IdunBattle.Core.Services.TargetingQuery$$GetRange` **écrase** la portée par ce délégué,
immédiatement après le `GetValueOrDefault` de `OverrideRange` et **avant** les deux clamps de mêlée :

```c
System_Nullable...GetValueOrDefault(param_4 + 0x10, &local_res18, &local_78);   // v = override ?? arme
uVar7 = local_78;
if (*(longlong *)(param_4 + 0x18) != 0) {                                       // overrideRangeFunc
    lVar9 = *(longlong *)(param_4 + 0x18);
    uVar7 = (**(code **)(lVar9 + 0x18))(*(undefined8 *)(lVar9 + 0x40), param_2, ...);
}
```

Une ability qui pose ce délégué n'a donc **aucune portée dérivable de ses autres champs**. Le port
enregistre la **présence** du délégué (`TargetingRange.override_range_func`, factory
`custom_range_func`) et `get_range` rend `None` — aucun gate de portée, la dégradation permissive du
module. C'est différent de `range = None`, qui veut dire « `TargetingRange` pas encore RE-lu ».

**Résidu nommé** : la méthode cible du délégué n'est pas résolue. C'est un *metadata usage*
(`FUN_1801f2030(&DAT_...)` puis lecture du slot au runtime), invisible à ghidra — aucune xref ne
part vers un corps. Le seul candidat de signature `int(IEntity)` dans le voisinage est
`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange`, que
`...SpawnPoxwalkersAbility$$ExecuteBehaviour` **et**
`...SpawnPoxwalkersAbility$$GetDynamicInvalidCasterReason` appellent tous deux, et dont le corps
(`GetStat(0xc TurnsStarted)` → 1 / 2 / 3) est déjà mirroré par `contagions_of_nurgle_range`. **C'est
une hypothèse, pas une lecture** — donc elle n'est pas portée.

Et c'est **mesuré sans conséquence** : la cascade refuse sur `TargetIsCaster` (2ᵉ règle) bien avant
d'atteindre le volet portée, et l'aiguillage self-cast court-circuite pour la seule cible légale.
Le test 1040 l'exige explicitement (`cf["sansRange"] == 0`) au lieu de le supposer — si un jour
neutraliser ce `TargetingRange` déplaçait un verdict, le test rougirait et le résidu deviendrait
réel.

### 1040, volet CASTER

`CasterMatchesDynamicRule` (bit 2) arme la règle-déléguée `options+0x30` =
`IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$GetDynamicInvalidCasterReason`,
dont le décompilé rend **`4`** s'il n'existe aucune tuile posable dans le disque
`CalculateRange(caster)` autour d'une des tuiles du caster, `0` sinon. Le port ne porte **aucune**
règle-déléguée CASTER (`get_invalid_caster_reason` ne porte que `CasterHasNotMoved`) : le seul écart
possible est permissif.

### 1169 : le bit qui transforme une déduction en lecture

`TargetIsTile` (bit 6) **confirme au décompilé** le cast tile-target que le port avait déduit d'une
mesure live `abilityTargets` (`kind="tile"`, cf. `plagueburst_damage_targets`). Corollaire de ce même
masque : `TargetIsEnemy` est **absent** — le gate de ciblage n'objecte sur le camp d'aucun occupant.
Ce qui filtre les cibles est le prédicat du behaviour
(`...PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger`), à l'**exécution**, pas au ciblage.

## 2. L'oracle `abilityReason` **ment** pour un caster MoW en domaine unité

Mesure décisive (runner 1221, board `C1_02`, seed 4242) :

| oracle | 1168, cible `ultraTitus` u49, aura Contagion **montée** |
|---|---|
| `abilityTargets` | `[49]` — **LÉGALE** |
| `abilityReason` | **`0x1`** |

La même cible est simultanément déclarée légale et refusée, par deux oracles du même moteur. La cause
est le court-circuit en tête de la surcharge 4 arguments d'
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (déjà relevé en case-245) :

```
ability = ActiveAbilityComponent.GetOrNull(<composant du caster>, abilityType);
if (ability == null || !ability.CanCurrentlyBeUsed || ability.<+0x44> == 0)
    return GenericBrokenTargetingRule(1);      // ValidRequest, cascade JAMAIS evaluee
```

Les abilities d'une **Machine of War** ne vivent pas dans un `ActiveAbilityComponent` d'unité :
`GetOrNull` rend `null` et l'oracle rend `0x1` **sans avoir regardé le masque**. Vérifié par
balayage de 14 tours : `abilityState.usable` reste `true` et `cooldown` `null` tout du long — donc ce
n'est **ni** un cooldown **ni** la jauge de munitions (`case-mow-ammo-gauge`), et `usable` ne le
signale pas, conformément à son contrat (`CanStillBeUsed@0x28` seul).

⇒ Pour 1168, l'oracle est **`abilityTargets`**
(`TargetingQuery$$GetPossibleTargetsForOptions` + la cascade), lu en **ensembliste**. Un « oracle »
lu dans `abilityReason` n'aurait rien mesuré du masque — et aurait affiché 0/4 d'accord en donnant
l'impression d'un port faux.

Le même caster MoW en domaine **TUILE** (1169) n'est pas concerné : `abilityReason` y discrimine
parfaitement (`0x0` sur marchable, `0x1` sur non marchable), sur les deux boards.

## 3. Validation — `scripts/python/probe_249_deathguard_targeting.py`

Deux montages, **deux couples (board, seed) chacun**, géométrie **drivée** (jamais subie) : le trio
`deathRotbone` / `deathBlightlord` / un necron mutuellement au contact, `deathBlightbringer` à
l'écart, au moins un necron hors contact — le seul arrangement qui sépare, pour 1037, le refus de
CAMP du refus de PORTÉE, et symétriquement pour 1042.

| ability | `MC1_67`/777 (`C1_02`/4242 pour les MoW) | `C4_09`/31337 (`C2_02`/31337) | casts illégaux que `master` acceptait |
|---|---|---|---|
| 1037 | **6/6** (2 lignes GAP) | **6/6** (2 GAP) | 4 + 4 |
| 1040 | **6/6** | **6/6** | 5 + 5 |
| 1042 | **6/6** | **6/6** | 5 + 6 |
| 1168 | 0 faux-refus ; accord **exact** après aura | idem | 2 + 2 |
| 1169 | **8/8** | **12/12** | 2 + 6 |

**Le compte des casts illégaux : 4+5+5+2+2 = 18 sur le premier couple, 4+5+6+2+6 = 23 sur le
second** — autant de lignes où le natif REFUSE et où `master` rendait `0`.

### 1168 : les deux phases, et ce qu'elles prouvent

* **sans aura** — le natif refuse *toutes* les cibles (`abilityTargets` = `[]`), le port accepte les
  deux ennemis : **sur-ensemble permissif de 2**, imputable à la règle dynamique non portée ;
* **aura montée** (`deathTyphus`, porteur de `ContagionsOfNurgle`, amené au contact) — le natif
  accepte `[49, 51]`, le port accepte exactement `[49, 51]` : **accord exact, sur-ensemble 0**.

C'est cette bascule qui *prouve* que l'écart de la phase 1 vient de la règle dynamique et **de rien
d'autre**. Dans les deux phases, le port ne refuse jamais une cible que le natif accepte : le sens
strict — le seul interdit — n'est jamais pris.

### Contrefactuels par champ

| ability | bit du masque | `range` | `force_melee_target` |
|---|---|---|---|
| 1037 | `TargetIsFriendly` : **3** lignes déplacées | **1** | **0 — INERTE** |
| 1040 | `TargetIsCaster` : **5** | **0 — INERTE** (attendu, cf. §1) | **0 — INERTE** |
| 1042 | `TargetIsEnemy` : **3** | **2** (puis 3) | **0 — INERTE** |
| 1168 | `TargetIsEnemy` : **2** | **0 — INERTE** (`useWholeBoard`) | **0 — INERTE** |
| 1169 | `TargetIsTile` : **2** (puis 6) | **0 — INERTE** (`useWholeBoard`) | **0 — INERTE** |

**Ce que ces mesures ne valident PAS**, et il faut le dire : `force_melee_target` est `RangedBool.
False` pour les cinq, et le forcer à `True` ne déplace **aucun** verdict — le champ est transcrit du
décompilé mais **non validé par cette mesure**. Idem pour les `range` marqués INERTE : `useWholeBoard`
fait sauter le volet portée (1168/1169) et la cascade refuse avant lui (1040). Seuls les
`RANGE_ADJACENT` de 1037 et 1042 sont exercés.

## 4. Règles non portées, nommées plutôt qu'absoutes

Le probe compte à part — et **imprime le symbole responsable** — les lignes où le natif refuse par une
règle que la cascade portée ne sait pas rendre, à condition que le port y rende `0` (permissif) :

| code | règle | porteurs du registre |
|---|---|---|
| `0x2` | la règle-déléguée `<X>Ability$$GetDynamicInvalidTargetReason` | 1168, 1169 (+ 5 autres) |
| ~~`0x100`~~ | ~~`TargetIsHealable` (bit 8)~~ — **PORTÉE depuis #245** | 1002, 1037 |
| `0x800` | `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` | tout self-cast |

Les deux écarts de 1037 étaient exactement ceux-là, et ils étaient **liés** : l'allié adjacent est à PV
pleins, donc le natif le refuse sur `TargetIsHealable` ; il ne reste alors **aucune** cible valide, et
le self-cast rend `0x800 AddCasterIfAtLeastOneTarget`. **#245 a porté la première** : la ligne
`deathBlightlord d=1` est passée de `GAP-permissif` à `OK`, et le contrefactuel
`sans_TargetIsHealable` la déplace. Il ne reste que `0x800` — le résidu générique.

Pourquoi 1168 n'est **pas** porté : la règle native accepte une cible sous aura Contagion **ou** à
`FixedArmor` négativement modifiée, et la branche AURA n'est pas matérialisable offline
(`entities/triggers.py::IsInTeamAura` est inerte). Porter la seule branche ARMURE **refuserait des
cibles légales** — une dégradation STRICTE, le seul sens que ce module interdit.

Pour 1169, aucun `PlagueburstMortarAbility$$GetDynamicInvalidTargetReason` n'est nommé dans les
tables — ce qui **ne prouve rien** (corps triviaux dédupliqués). Le défaut `0` est permissif dans les
deux hypothèses, et la mesure 12/12 montre qu'aucune ligne n'en dépend sur ces boards.

## 5. Artefacts

* masques : `scripts/python/engine/runner/abilities/deathguard.py` (les cinq classes) ;
* module générique : `scripts/python/engine/runner/abilities/targeting.py`
  (`TargetingRange.override_range_func`, `custom_range_func`, branche de `get_range`) ;
* probe (MESURE) : `scripts/python/probe_249_deathguard_targeting.py` ;
* test (GARDE) : `scripts/python/tests/engine/runner/test_deathguard_targeting_live.py` ;
* cliquet : `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py` (les 5 retirées de
  `SANS_TARGETING_OPTIONS`, 31 restantes).

`ABILITY_ATTACK_TYPE` : les cinq littéraux du port (`2`, `1`, `0`, `0`, `0`) **coïncident** avec le 3ᵉ
argument d'`AActiveAbility..ctor` relu au décompilé. Aucun changement.

Compte re-dérivé (`probe_181_targeting_gaps.py`) : **94** au registre, **63** avec masque (58 avant),
**31** manquantes — le module `deathguard` disparaît de la ventilation.

## 6. Ce qui n'est PAS couvert

* **La méthode cible du délégué `GetRange` de 1040** (§1) — hypothèse `CalculateRange` non lue, non
  portée ; sans effet mesurable, et le test rougirait si ça changeait.
* ~~**`TargetIsHealable` (bit 8)**~~ — **FERMÉ par #245** (`docs/rl/case-245-target-is-healable.md`).
  La vérification demandée ici a d'ailleurs répondu **non** : le prédicat de cette règle **n'est pas**
  `healable_heal_type_0` (la garde de mutation, 2 termes) mais
  `AttackQuery$$EntityCanBeHealed` (6 termes), déjà mirroré dans `abilities/attack_query.py`.
* **`GetCasterNotAddedReason`** — non porté (il dépend de `TargetingQuery$$GetValidTargets`, qui
  énumère tout le plateau) ; résidu générique déjà documenté, pas propre à ce cas.
* **`force_melee_target` des cinq** — transcrit, jamais exercé (§3).
* **Le volet portée de 1040, 1168, 1169** — jamais atteint (délégué non résolu / `useWholeBoard`).
* **La face COMBAT** des cinq abilities — hors périmètre : ce cas ne traite que le gate de CIBLAGE.
