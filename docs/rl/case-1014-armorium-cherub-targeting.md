# Case 1014 — `ArmoriumCherub` : le masque de ciblage d'une ability à **preset statique copié**

`ArmoriumCherubAbility` (1014, `adeptRetributor` « Vindicta », Sisterhood) entrait dans
`ABILITY_CLASSES` **sans** `TARGETING_OPTIONS`. Or `get_invalid_target_reason` /
`get_invalid_caster_reason` (`engine/runner/abilities/targeting.py`) commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent **0 immédiatement** quand c'est
`None` : aucun gate. Le moteur acceptait donc des casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` **refuse** — sur un allié, sur
soi-même, hors portée. Dégradation **permissive** : ni erreur ni crash, invisible en self-play,
exactement le trou qu'un entraînement irait exploiter.

## 1. La forme de ctor : **PRESET STATIQUE COPIÉ** (la 3ᵉ des trois)

C'est le point qui décide de tout, et il faut l'établir avant de recopier le moindre littéral.

`IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$.ctor` **n'appelle aucun**
`IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les **0x40 octets** du champ
**statique** de `TargetingOptions` situé à l'offset **`+0x140`** du bloc `<class>+0xb8`, puis :

```
AActiveAbility..ctor(this, &opts, 0, 0)
```

Aucun littéral de masque n'est donc visible dans le ctor de l'ability. Le masque **effectif** est la
constante qu'écrit `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`, soit
`*(statics+0x168)` = **`0x4002`**.

Ce n'est **ni** la forme 1 (flags directs — `TargetingOptions..ctor(&opts, 0, &<TargetingRange
statics+0x..>, 1, <littéral>, 0, 0, 0)`, où le littéral **est** le masque, cas de `BlackRage` 1163),
**ni** la forme 2 (preset + flags — `TargetingOptions..ctor(&opts, &preset, <flags>, 0)`, où
`Rules <- preset.Rules | flags` et le littéral visible n'est **pas** le masque effectif, cas de
`TheQuickening`). Ici la copie est **intégrale** : il n'y a aucun flag à OR-er.

### Le preset lu en entier (pas seulement son champ `Rules`)

`TargetingOptions$$.cctor`, bloc `statics+0x140` :

| champ | offset | valeur lue | signification |
|---|---|---|---|
| `isSelfCasting` | `<preset>+0x00` = `statics+0x140` | `0` | pas de self-cast |
| `range` (`TargetingRange`) | `<preset>+0x08` = `statics+0x148` | copie de `TargetingRange statics+0x18` | `useRangeFromConfig` |
| `forceMeleeTarget` (`RangedBool`) | `<preset>+0x20` = `statics+0x160` | `0` = **`RangedBool.True`** | clamp mêlée armé |
| `rules` (`TargetingRule`) | `<preset>+0x28` = `statics+0x168` | **`0x4002`** | les deux bits ci-dessous |
| les 2 règles-délégués | `+0x30` / `+0x38` | `0` | écrasées par `AActiveAbility$$.ctor` |

`TargetingRange$$.cctor`, bloc `statics+0x18` : `onlyAdjacent = 1 (False)`,
`useRangeFromConfig = true`, `useWholeBoard = false`, `overrideRange` vide, `overrideRangeFunc` nul
— c'est le `RANGE_FROM_CONFIG` du port.

**Les presets ne sont pas interchangeables** : `statics+0x40` (rules `0x4000`, `forceMeleeTarget =
False`, `TargetingRange statics+0x30` = adjacent) et `statics+0x180` (rules `0x4002` mais
`forceMeleeTarget = False`) sont voisins et donnent des verdicts différents. C'est pourquoi le champ
`forceMeleeTarget` est mesuré à part au §3.

### Décomposition du masque `0x4002`

| bit | nom (`IdunBattle.Core.Services.TargetingRule`) | effet |
|---|---|---|
| `0x2` | `TargetMatchesDynamicRule` | consulte `GetDynamicInvalidTargetReason` |
| `0x4000` | `TargetIsEnemy` | refus sur soi-même / un allié |

`ArmoriumCherubAbility` **ne fournit aucun corps propre** pour `GetDynamicInvalidTargetReason` : ses
seules méthodes sont `...$$.ctor`, `...$$ExecuteBehaviour` et le `...$$GetHits` gshared (corps
dédupliqué, partagé avec une douzaine d'autres abilities). Le bit `0x2` retombe donc sur le défaut
`AActiveAbility` = `0` = aucun refus, ce que le port reproduit par le défaut de `ActiveAbility`.

## 2. Le volet PORTÉE, qui vient du **même** preset

`useRangeFromConfig` ⇒ `AActiveAbility$$SetConfigValuesInTargetingOptions` pose
`OverrideRange = AbilityConfiguration.GetNumberConstant(0x16 range)` =
`ArmoriumCherub.constants.range` = **2** (gameconfig ; i2 « to a target within range {[range]} »).

`forceMeleeTarget = RangedBool.True` ⇒ dans
`IdunBattle.Core.Services.TargetingQuery$$GetRange`, la garde
`RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)` est **toujours vraie**, donc dès que
`AttackQuery$$ShouldApplyRangedInMelee(caster, casterTiles, ignoreTrait = 1)` rend vrai — un ennemi
**vivant, ciblable, non-`Steppable`, à `|dElevation| < 2`, au contact du caster** — la portée est
clampée à `Math.Min(1, 2)` et `onlyAdjacent` est posé. Vindicta engagée au corps à corps ne porte
plus qu'à 1.

Le port n'a donc **pas** un gate « `hexDistance <= 2` » : il a le `GetRange` complet.

## 3. Validation — `scripts/python/probe_222_armorium_cherub_targeting.py`

Oracle = le **live** : `abilityReason(casterId, abilityType, targetId)` rend le `TargetingRule`
natif. Le probe rejoue ensuite le gate **offline sur le même état figé**, en deux versions : `APRÈS`
(l'ability du registre) et `AVANT` (la même classe avec `TARGETING_OPTIONS = None`, c'est-à-dire
l'état de `master`).

Trois états figés, chacun avec sa capture (`decisionView` / `observeBattle` / `combatSnapshot`), la
géométrie **conduite** et jamais subie (`_seek` déplace Vindicta jusqu'à satisfaire un prédicat de
position) :

| cas | natif | port APRÈS | port AVANT |
|---|---|---|---|
| S1 cible **AMIE** (`adeptCanoness`) | `0x4000` `TargetIsEnemy` | `0x4000` | `0x0` |
| S1 cible = **LE CASTER** | `0x4000` `TargetIsEnemy` | `0x4000` | `0x0` |
| S1 ennemi **loin** (`d=11`) | `0x8000000` `TargetIsInRange` | `0x8000000` | `0x0` |
| S2 ennemi `d=2`, **aucun au contact** | `0x0` | `0x0` | `0x0` |
| S3 ennemi **au contact** `d=1` | `0x0` | `0x0` | `0x0` |
| S3 ennemi `d=2` **sous clamp mêlée** | `0x8000000` `TargetIsInRange` | `0x8000000` | `0x0` |

**6/6 d'accord natif/port ; 4 cas où le natif REFUSE alors que `master` rendait 0** — quatre casts
illégaux que le moteur acceptait.

**S2 vs S3 est le cas discriminant** : *la même distance 2*, deux verdicts natifs opposés. Ce qui les
sépare n'est pas la distance mais la présence d'un ennemi **au contact du caster**, c'est-à-dire
`forceMeleeTarget`. Un port qui aurait recopié `Rules` en négligeant le reste du preset passerait
S1 et S2 et se ferait prendre ici.

### Contrefactuels (sur le même état figé, ligne S3 `d=2`, natif `0x8000000`)

| variante | verdict du port |
|---|---|
| `force_melee_target = RangedBool.False` | `0x0` — **faux accept** |
| `range = None` (`TargetingRange` non relu) | `0x0` — **faux accept** |

Les deux champs du preset sont donc **porteurs**, pas décoratifs : chacun, retiré, sépare le port du
natif sur une ligne mesurée.

### Généralisation

- **2 couples board/seed** : `MC1_67`/777 et `C4_09`/31337 — les 6 lignes vertes dans les deux, les
  deux contrefactuels divergents dans les deux.
- **Sweep** (`--sweep 8`, `MC1_67`/777) : **24 points, 0 désaccord** natif/port, distances 1 à 11.
  Le sweep marche vers l'ennemi le plus proche, donc il n'atteint jamais le régime « `d=2` sans
  ennemi au contact » — c'est S2 qui le couvre. Le rapport croise désormais `(d, dmin)` pour rendre
  cette séparation lisible quand un montage l'atteint.

### Zéro-régression

`test_ability_registry_ratchet` (8), `test_armorium_cherub_migration_live` (1),
`test_targeting_options_masks_live` + `test_targeting_masks_live` (17),
`test_targeting_adjacency_rules_live` (22), `test_fire_of_absolution_migration_live` +
`test_act_of_faith_ability_reset_live` + `test_on_fire_damage_migration_live` (4) — tous verts.
`probe_120_pre_unit_ability_fork` étape 0 : « littéral de ctor manquant: aucun ».

Cliquet : 1014 retiré de `SANS_TARGETING_OPTIONS` (le test l'exigeait).
`ABILITY_ATTACK_TYPE[1014]` était **déjà** posé, et le décompilé le confirme :
`AActiveAbility..ctor(this, &opts, 0, 0)` → 3ᵉ argument `0` = `DirectTargetAttack`.

## 4. Confrontabilité des porteurs

`unit_map find --ability ArmoriumCherub` : 4 porteurs, tous « Vindicta » —
`adeptBossRetributor` (npc), `adeptBossRetributorLHE` (npc), `adeptNpcRetributor` (npc), et
**`adeptRetributor`**, présent dans `rl_duel.py build --list-pool` (rank 17, 97 unités). Le gate de
confrontabilité passe par ce dernier : **HERO spawnable**, aucun besoin de `catalog_inject` ni de
summoner.

## 5. Ce qui n'est PAS couvert

- **La règle dynamique** : le bit `0x2` est porté, mais le prédicat retombe sur le défaut `0`. C'est
  le verdict natif lu (aucun corps propre dans la classe) et non une lacune du port — mais il
  repose sur l'absence de surcharge, que les tables de symboles **ne peuvent pas prouver** (corps
  triviaux dédupliqués). Un `xor eax,eax ; ret` dédupliqué rendrait de toute façon `0`, donc les
  deux lectures convergent ; une surcharge à logique réelle aurait, elle, sa propre adresse.
- **Les règles du filtre statique laissées permissives** (inventaire en tête de `targeting.py`) —
  inchangées ici, notamment la ligne de vue (`GetTilesObscuringTerrain`), évaluée par le natif juste
  après la portée.
- **Le volet CASTER** : `0x4002` ne pose pas `CasterHasNotMoved` (contraste avec BlackRage), donc
  Vindicta peut caster après s'être déplacée — mesuré indirectement (aucune ligne du probe ne rend
  de `casterReason`), pas isolé par un cas dédié.
- **L'élévation dans `ShouldApplyRangedInMelee`** (`CanMeleeAttackOverElevationDifference`,
  `|dElev| < 2`) : le port l'écrit, aucune des géométries mesurées ne l'exerce (les boards
  `MC1_67`/`C4_09` n'ont pas placé d'ennemi adjacent à 2 niveaux d'écart).
