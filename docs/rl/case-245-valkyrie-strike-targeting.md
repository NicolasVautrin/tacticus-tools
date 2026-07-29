# Case 245 — `ValkyrieStrike` (1018) : le masque de ciblage, et pourquoi le preset n'est pas celui du voisin

`ValkyrieStrikeAbility` (1018, porteur `astraSmnVoxcaster` « Cadian Vox-caster ») entrait dans
`ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`. `get_invalid_target_reason` /
`get_invalid_caster_reason` (`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Dégradation **permissive** — ni erreur ni crash, invisible en self-play.

## 1. La forme de ctor : **PRESET STATIQUE COPIÉ** (la 3ᵉ des trois)

`IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$.ctor` **n'appelle aucun**
`IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les **0x40 octets** du champ
**statique** de `TargetingOptions` situé à l'offset **`+0x1c0`** du bloc `<class>+0xb8`, puis :

```
AActiveAbility..ctor(this, &opts, 2, 0)
```

Aucun littéral de masque n'est visible dans le ctor. Le masque **effectif** est la constante
qu'écrit `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`, soit
`*(statics+0x1e8)` = **`0x6000040`**.

C'est **exactement la même forme** que `ArmoriumCherub` (1014, case-1014) — mais **un autre
preset**, et c'est tout l'intérêt du cas : `statics+0x140` vaut `0x4002`, `statics+0x1c0` vaut
`0x6000040`. Deux abilities voisines, même forme de ctor, masques sans rapport. **Généraliser
depuis la voisine aurait produit un masque faux.**

### Le preset lu en entier (pas seulement son champ `Rules`)

`TargetingOptions$$.cctor`, bloc `statics+0x1c0` :

| champ | offset | valeur lue | signification |
|---|---|---|---|
| `isSelfCasting` | `<preset>+0x00` = `statics+0x1c0` | `0` | pas de self-cast |
| `range` (`TargetingRange`) | `<preset>+0x08` = `statics+0x1c8` | copie de `TargetingRange statics+0x48` | **`useWholeBoard`** |
| `forceMeleeTarget` (`RangedBool`) | `<preset>+0x20` = `statics+0x1e0` | `1` = **`RangedBool.False`** | pas de clamp mêlée |
| `rules` (`TargetingRule`) | `<preset>+0x28` = `statics+0x1e8` | **`0x6000040`** | les trois bits ci-dessous |
| les 2 règles-délégués | `+0x30` / `+0x38` | `0` | écrasées par `AActiveAbility$$.ctor` |

`TargetingRange$$.cctor`, bloc `statics+0x48` : `onlyAdjacent = 1 (RangedBool.False)`,
`useRangeFromConfig = false`, `useWholeBoard = **true**`, `overrideRange` vide, `overrideRangeFunc`
nul — c'est le `RANGE_WHOLE_BOARD` du port. Les 5 statiques `TargetingRange` ont été relues à
l'occasion et **confirment ligne par ligne** la table du port (`+0x00` adjacent-si-mêlée, `+0x18`
from-config, `+0x30` adjacent, `+0x48` whole-board, `+0x60` self).

### Décomposition du masque `0x6000040` (exhaustive — aucun bit résiduel)

| bit | masque | nom (`IdunBattle.Core.Services.TargetingRule`) | effet |
|---|---|---|---|
| 6 | `0x40` | `TargetIsTile` | domaine **TUILE** ; refuse une tuile non marchable (rend le littéral `1` = `ValidRequest`) |
| 25 | `0x2000000` | `AllowObscuredTargetByElevation` | **lève** la ligne de vue par élévation |
| 26 | `0x4000000` | `AllowObscuredTargetByWalls` | **lève** la ligne de vue par murs |

Sémantiquement cohérent avec la mécanique : un **airstrike** se désigne sur une **tuile** et ne se
soucie ni des murs ni du relief.

Trois conséquences directes, toutes vérifiées dans le code du gate :

* **aucune règle de CAMP** (`TargetIsFriendly` / `TargetIsCaster` absents) ⇒
  `refuses_all_enemy_targets` = `False` ⇒ le veto de routage IA (`engine/ai/state_bridge.py`) est
  **inchangé** ; poser ce masque ne déplace aucune action.
* **`TargetMatchesDynamicRule` (0x2) ABSENT**, et les deux délégués du preset sont nuls ⇒ le natif ne
  consulte **aucune** règle dynamique pour cette ability.
* **`useWholeBoard`** ⇒ `TargetingQuery$$GetRange` court-circuite : **aucun** test de portée. La
  distance ne borne donc pas ce cast — et comme il n'y a pas non plus de règle dynamique, il n'y a
  nulle part ailleurs où une contrainte de distance pourrait vivre.

Le seul bit qui **mord** offline est donc `TargetIsTile` : `AllowUnwalkableTargetTile` (bit 43)
n'étant pas posé, une tuile-cible non marchable rompt.

## 2. La donnée jumelle — `AbilityAttackType`

`ABILITY_ATTACK_TYPE[1018]` était **déjà** posé à `2`, et le décompilé le confirme :
`AActiveAbility..ctor(this, &opts, 2, 0)` → 3ᵉ argument `2` = `AbilityAttackType.Others`
(`AActiveAbility$$HasAttackType` compare avec le champ `+0x68`, écrit par
`*(undefined4 *)(param_1 + 0xd) = param_3`). Aucun changement requis.

## 3. Confrontabilité du porteur — **aucun chemin de spawn**, et c'est un verdict, pas un aveu

`astraSmnVoxcaster` : `kind = "summons"`, traits `Summon` + `BattleFatigue`. Il n'est donc pas dans
`rl_duel.py build --list-pool` (attendu pour un summon), **et il n'a pas de summoner de héros** :
les seules entrées de gameconfig qui le posent en `constants.unitId` sont **quatre
`EnvFactionSummons:Armageddon{Astra,BA,BT,SW}`**, c'est-à-dire des summons de l'**Environnement**
(le 3ᵉ joueur), attachés à un contexte de bataille Armageddon — pas une ability castable par une
unité du pool. Le chemin « spawner son summoner » n'existe pas ici.

Ce n'est pas un détail de commodité, parce que l'oracle live **exige le vrai porteur**. Le
décompilé de `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (surcharge 4 arguments,
celle que le RPC `abilityReason` invoque) commence par :

```
ability = ActiveAbilityComponent.GetOrNull(<component du caster>, abilityType);
if (ability == null || !ability.CanCurrentlyBeUsed || ability.<+0x44> == 0)
    return GenericBrokenTargetingRule(1);      // ValidRequest, cascade JAMAIS évaluée
```

⇒ interroger `abilityReason` avec un caster qui **ne possède pas** 1018 rend `0x1` sans jamais
toucher aux `TargetingOptions`. Un « oracle » obtenu ainsi ne mesurerait rien du masque. C'est la
raison pour laquelle la validation de ce cas passe par le **catalogue injecté** (`catalog_inject.py`,
mirror de `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`), qui donne au
Vox-caster une entrée `BC.Units` **et** sa `AbilityConfiguration` — sans quoi le cast fauterait.

### Le montage, et pourquoi il reste un oracle fidèle

Le Vox-caster est **déjà** au catalogue `BC.Units` du seed BC (entrée produite par
`BattleConfigBuilder$$AddSummonUnitConfigs`), donc `initAndStart(playerUnits=[...])` le spawne
directement — le filtre de pool de `rl_duel build` est une commodité Python, pas une contrainte du
moteur. Deux champs de son entrée sont aménagés, et **seulement** deux :

| champ | valeur d'origine | valeur du montage | pourquoi |
|---|---|---|---|
| `Health` | `0` | `5000` | l'entrée d'un summon porte 0 (ses PV viennent des `summonHp` du summoner au spawn natif) ; spawné à la main il naîtrait à 1 PV |
| `Traits` | `Imperial, Summon, BattleFatigue` | `Imperial, BattleFatigue` | **mesuré** : `CanStillBeUsed` vaut `false` **ssi** le trait `Summon` est présent (balayage des 4 variantes de traits, même board/même seed) — et le court-circuit ci-dessus rend alors `0x1` partout |

Le second aménagement ne peut pas déplacer un verdict de la cascade **pour ce masque**, et ça se lit
au décompilé, pas à la mesure : les seules règles du filtre statique qui consultent un trait portent
sur la **cible** (`TargetIsSummon` 0x2000, `TargetIsHero` bit 50, `TargetIsNotAnObject` bit 33) et
aucune n'est dans `0x6000040` ; le trait du **caster** n'entre que par
`RangedBoolExtensions$$IsTrue(IfRangedCaster / IfNotRangedCaster)`, or ce preset pose
`forceMeleeTarget = RangedBool.False` et `onlyAdjacent = RangedBool.False` — deux constantes — et
`useWholeBoard` fait de toute façon sauter le volet portée. Le trait `Summon` gouverne le gate
d'**usage**, pas celui de **ciblage** ; la couche `TargetingRule` n'a aucun flag de cooldown/usage.

## 4. Validation — `scripts/python/probe_245_valkyrie_targeting.py`

Oracle = le **live** : `abilityReason(casterId, abilityType, targetId)` rend le `TargetingRule`
natif. Le probe rejoue le gate **offline sur le même état figé**, en trois versions : `APRÈS`
(l'ability du registre), `AVANT` (la même classe avec `TARGETING_OPTIONS = None`, c'est-à-dire l'état
de `master`) et `sansTile` (contrefactuel : le masque privé du seul bit qui mord).

**Le piège du code `0x1`** : il a deux causes natives sur ce chemin — l'ability non utilisable
(court-circuit) et `TargetIsTile` sur tuile non marchable (le natif *réutilise* le littéral 1). Le
probe exige donc, dans le même état, qu'au moins une tuile **marchable** rende `0x0` : sans quoi les
`0x1` ne prouveraient rien.

| montage | lignes | accord natif/APRÈS | natif REFUSE alors qu'`AVANT` rendait 0 | contrefactuel |
|---|---|---|---|---|
| `MC1_67` / 777 (1 tuile non marchable sur 63) | 10 | **10/10** | **1** | 1/1 |
| `C3_26` / 31337 (31 tuiles non marchables sur 63) | 19 | **19/19** | **8** | 8/8 |

Les unités (les deux `necroWarden` ennemis **et** le caster lui-même) sont acceptées `0x0` des deux
côtés : c'est le verdict natif, et il est cohérent avec la lecture du masque — aucune règle de camp,
aucune règle `TargetIsCaster`.

**Contrefactuel** : le masque privé de `TargetIsTile` faux-accepte **exactement** les lignes que le
natif refuse (1/1 puis 8/8). Le bit est donc porteur, pas décoratif.

**Contre-épreuve du test de garde** (`tests/engine/runner/test_valkyrie_strike_targeting_live.py`) :
avec `ValkyrieStrikeAbility.TARGETING_OPTIONS` forcé à `None`, le test **échoue** sur son assertion
de fond — 6 lignes `nowalk` où le natif rend `0x1` et le port `0x0`. Avec le masque, il passe.

### Zéro-régression

`test_ability_registry_ratchet` + `test_targeting_options_sources` + la garde 1018 (13), les tests
1018 existants `test_valkyrie_strike_migration_live` + `test_summon_ability_ports_live` (3),
`test_targeting_options_masks_live` + `test_targeting_masks_live` (17) — tous verts.
`probe_120_pre_unit_ability_fork` étape 0 : « littéral de ctor manquant: aucun ».
`probe_181_targeting_gaps` : 94 entrées au registre, **57** avec masque, **37** manquantes
(38 avant), `strike` passe de 4 à **3**.

Cliquet : 1018 retiré de `SANS_TARGETING_OPTIONS` (le test l'exigeait).

## 5. Ce qui n'est PAS couvert

- **La ligne de vue** (`GetTilesObscuringTerrain`) reste non portée dans le gate générique. Ici
  c'est sans conséquence *dans ce sens* : les deux bits `AllowObscured*` **désarment** justement
  cette règle côté natif, donc l'absence de port ne peut pas creuser d'écart pour 1018.
- **L'airstrike différé lui-même** (fire de l'effet 1022 au tour suivant) : hors périmètre de ce
  cas, qui ne traite que la face CIBLAGE du cast.
- **Le volet CASTER** : `0x6000040` ne pose pas `CasterHasNotMoved`, donc le Vox-caster peut caster
  après s'être déplacé ; propriété lue au masque, pas isolée par un cas dédié.
- ~~**Pourquoi le trait `Summon` désarme `CanStillBeUsed`**~~ — **EXPLIQUÉ par `case-250`**, et la
  chaîne candidate citée ici était fausse : le slot virtuel `+0x3d8` est `GetCooldownAfterUse`, il
  ne lit aucun trait. Le trait `Summon` (`UnitTrait` 2) rend l'unité **automatique**
  (`IdunBattle.Entities.UnitExtensions$$IsAutomatic`) ; le moteur la joue lui-même
  (`IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`), elle consomme sa charge, et
  `CanStillBeUsed` retombe à `false` par l'**usage**
  (`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` : `AmountOfTimesUsed++` puis
  ré-évaluation). Rien n'est donc « désarmé ». Corollaire pour 1018 : le faire caster **à la main**
  par son porteur réel avec son trait reste impossible (l'unité n'offre jamais d'action), mais le
  moteur, lui, le fait.
- **Les régimes de portée** : `useWholeBoard` fait sauter le volet portée, donc les lignes
  `TargetIsInRange` / `TargetIsAtRange` ne sont pas exercées par ce cas (elles le sont par
  `case-1014` et `case-241`).
