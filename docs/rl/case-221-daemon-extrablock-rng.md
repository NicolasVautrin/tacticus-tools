# #221 — `Daemon_ExtraBlock` (1034) : le jet de block manquant, et l'ordre de la chaîne de block

**Question tranchée** : sur une même attaque, contre un défenseur portant le trait `Daemon`, le port
consomme-t-il exactement les mêmes tirages RNG que le natif, dans le même ordre ?

**Réponse : OUI.** Elle était NON, et l'écart n'était pas une valeur qui divergeait — c'était un
**tirage sauté**, donc tout l'aval décalé.

---

## 1. La chaîne native

Le trait `Daemon` est porté par une ability qui pose et **rafraîchit** une entrée de block sur son
propre porteur :

```
IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$CreateTrigger
  = OnOwnerSpecificAbilityInit(0x40c) | ( On(0x3b, 1) & GetUpdateEffectCondition )

IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$CreateUpdateEffectBehaviour
  = If( GetUpdateEffectCondition,
        RemoveEffect(Self@0x148, 0x40a)
      & AddExtraBlockEffectToOwner(0x40a,
            Direct(GetNumberConstant(0x2d = daemonBlockChance)),
            GetBlockDamage()) )

IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetBlockDamage
  = PercentageOf( StatAmount(Self@0x148, statType 0 = Attack, statPart 0 = Current),
                  Direct(GetNumberConstant(0x36 = daemonBlockDamagePercentage)) )

IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetUpdateEffectCondition
  = Not( AmountIsEqual( MultiStatValueFromEffect(Self@0x148, 0x40a, 8 = BLOCK_DAMAGE),
                        GetBlockDamage() ) )
```

`0x40a` = 1034 = `Daemon_ExtraBlock`. gameconfig `trait("Daemon").variables` :
`daemonBlockChance = 25`, `daemonBlockDamagePercentage = 50`.

La signature de `StatAmount` (`unit, statType, statPart, modificationEntity, selectionType`) fixe
sans ambiguïté les deux littéraux `0` lus au décompilé : **stat `Attack`, part `Current`**.

Le `GetUpdateEffectCondition` est ce qui autorise le **fold** du port : le natif fige l'amount dans le
composant à la pose, mais le re-pose dès que la valeur diffère (event `0x3b`). L'entrée vaut donc
toujours l'`Attack` courante — la recalculer à la lecture est équivalent, et c'est déjà le choix de la
face PRÉDICTION (`defender_prediction_block_amount`, #54A).

### Comment cette entrée devient un tirage

```
IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances(attacker, defender, failedBlockIds)
  entries = defender.GetMultiValueStat(7)          # IdunBattle.Entities.UnitExtensions$$GetMultiValueStat
                                                   #  -> MultiValueStatComponent$$GetAllValues
  pour chaque entry :
      si failedBlockIds != null et failedBlockIds.Contains(entry.entityId) : SKIP
      si entry.chance == 0 : SKIP
      amount = IdunBattle.Entities.UnitExtensions$$GetBlockDamageForBlockChance(defender, entry)
             = comp8.GetValueByEntity(entry.entityId) ?? comp8.GetDefaultEntry()
      result.Add( BlockChanceInfo{ entityId, chance, amount } )
  result.Sort( DamageCalculations.<>c.<CalculateBlockChances>b__15_0 )

IdunBattle.Core.Services.DamageCalculations$$ApplyRandomBlockDamage(blockChances, currentDamage)
  pour chaque src dans l'ordre :
      si src.chance > 0 et src.amount > 0 :
          si NextBool(src.chance) :  damage = ApplyBlockDamage(src.amount, damage) ; STOP
          sinon :                    BlockDamageInfo$$AddFailedBlockId(src.entityId)
```

Trois faits que le port ne lisait pas correctement, tous dans cette seule fonction :

| # | Fait natif | Où on le lit |
|---|---|---|
| A | l'entrée d'un effet ExtraBlock existe et **coûte un `NextBool`** | `GetAllValues` = entrée par défaut `{entityId 0, GetStatPart(comp7, Current)}` **puis** `AddRange(dict.Values)` |
| B | le failed-id est le **`BEntityId` de la source**, pas la chance | signature Frida `failedBlockIds: List<IdunBattle.Core.BEntityId>` ; `ApplyRandomBlockDamage` pousse `(undefined4)uVar1` = le champ `@+0x0` de `BlockChanceInfo`, tandis que la chance est en `@+0x4` et l'amount en `@+0x8` |
| C | la liste est **triée décroissant par amount** | `<>c.<CalculateBlockChances>b__15_0` : `mov eax,[r8+8] ; sub eax,[rdx+8] ; ret` = `b.blockDamage − a.blockDamage` |

---

## 2. Le défaut, et pourquoi il était invisible

`AttackDamageOperation._block_sources` appelait `defender_effect_block_sources(effets, armure)` **sans
l'`Attack` du défenseur**. `DaemonExtraBlockEffect.create_effect_block_source_for_defense` calcule
`amount = defender_attack × pct / 100` et rend `None` si l'amount est nul : avec `defender_attack = 0`,
la source **disparaissait**. Le port ne roulait donc aucun jet là où le natif en roule un.

Le port CHARGEAIT pourtant bien l'effet — c'est ce qui rendait le trou difficile à voir :

```
cible worldEightbound u77 effets LIVE   = [(1262, BlessingsOfKhorne), (1034, Daemon_ExtraBlock), (78, Terrifying_ExtraDefense)]
PORT effets ACTIFS offline              = [(1262, BlessingsOfKhorne), (1034, Daemon_ExtraBlock), (78, Terrifying_ExtraDefense)]
PORT defender_effect_block_sources      -> []                                    <-- AVANT
PORT defender_effect_block_sources      -> [BlockSource(chance=25, amount=1205, block_id=1034)]   <-- APRÈS
```

(`1205 = 2411 × 50 / 100`, `2411` = l'`Attack` courante de la cible.)

Symptôme : la divergence n'apparaît **pas** là où est la cause. Le coup 1 pouvait rester juste, et
c'est le coup 2 qui partait — le tirage manquant décale tout l'aval de l'attaque (et, si le block
réussit, la **valeur** du coup, pas seulement sa position dans la suite).

---

## 3. Le fix

`scripts/python/engine/runner/operations/damage.py` — `AttackDamageOperation._block_sources` :

- thread `defender_attack = ctx.attack` (= `GetStat(ATTACK, Current)`) à
  `defender_effect_block_sources` → **fait A** ;
- pose `block_id = 0` sur l'entrée de base (l'entityId 0 de `GetAllValues`) et, pour les effets,
  l'identité de la source via le nouvel helper `BaseEffect.block_source_id` (offline : `effect_type`)
  → **fait B** ;
- trie la liste par amount décroissant → **fait C**.

Le helper `block_source_id` est posé dans `entities/effects/base.py` et consommé par les trois
producteurs de `BlockSource` (`BeastSlayerExtraBlockEffect`, `DaemonExtraBlockEffect`,
`PsychicFortressExtraBlockEffect`, `entities/effects/loki/hits.py`). Il retombe sur la chance quand
un effet n'a pas d'`effect_type` seedé — jamais pire que l'ancien comportement.

Un seul foyer à corriger : les trois vecteurs de dégât (`execute`, `execute_ability_attack`,
`execute_normal_like`) passent par ce helper partagé, avec le même `tsc`.

---

## 4. Validation

Board `MC1_67`. « legacy » = la même attaque rejouée depuis le **même état MT**, avec
`DaemonExtraBlockEffect` neutralisé — c'est-à-dire l'état d'avant le fix, mesuré dans le même run.

### Vecteur ABILITY (BrazierOfHolyFire 1041, `probe_brazier_daemon_offset.py`)

| cible | seed | LIVE | PORT | LEGACY k=0 |
|---|---|---|---|---|
| `blackObliterator` (Daemon, 4 coups) | 777 | `[2702, 2593, 2531, 2867]` | **identique** | `[2702, 2402, 2617, 2713]` |
| `worldEightbound` (Daemon, 4 coups) | 777 | `[1899, 1790, 1728, 2064]` | **identique** | — |
| `necroWarden` (non-Daemon, 2 coups) | 777 | `[1899, 1599]` | **identique** | **identique** |

La variante legacy recolle sur les coups 2..4 avec `k=1` (un tirage pré-consommé) : c'est
littéralement la signature « +1 tirage au 1er coup ».

### Vecteur ATTAQUE NORMALE (`necroDestroyer`, 6 coups mêlée, `probe_221_daemon_normal_attack.py`)

| cible | seed | LIVE | PORT | LEGACY k=0 |
|---|---|---|---|---|
| `blackObliterator` | 777 | `[61, 514, 642, 603, 600, 585]` | **identique** | `[514, 582, 514, 578, 642, 603]` |
| `blackObliterator` | 31337 | `[512, 446, 541, 625, 638, 591]` | **identique** | `[512, 504, 446, 541, 625, 638]` |
| `worldEightbound` | 777 | `[0, 514, 642, 603, 600, 585]` | **identique** | `[514, 582, 514, 578, 642, 603]` |
| `necroWarden` (témoin) | 777 | `[514, 582, 514, 578, 642, 603]` | **identique** | **identique** |

Deux choses à lire ici :

1. sur ce vecteur, le block **réussit** au coup 1. Sur `blackObliterator` : `Attack = 906` →
   `amount = 906 × 50 / 100 = 453`, et le coup vaut `514 − 453 = 61` — la valeur live, à l'unité, donc
   c'est bien `ApplyBlockDamage` qui s'applique et pas seulement un tirage de plus. Sur
   `worldEightbound`, l'amount dépasse le dégât → `max(0, …) = 0` : le legacy **infligeait 514 PV
   fantômes** là où le natif en inflige 0 ;
2. la séquence du témoin non-Daemon est **exactement** la séquence legacy contre les Daemons — preuve
   directe que le port traitait un Daemon comme une unité sans source de block.

### Ce que le fix a déplacé ailleurs

Rejoué après le fix ; « inchangé » = même verdict qu'avant.

| test | verdict |
|---|---|
| `test_damage_block_live.py`, `test_beast_slayer_block_live.py` | 4 passed — inchangé |
| `test_lion_helm_block_aura_live.py`, `test_noblocking_bypass_live.py`, `test_noblocking_prediction_live.py` | 6 passed — inchangé |
| `test_damage_roll_live.py`, `test_damage_crit_live.py` | 4 passed — inchangé |
| `test_runner_attack_live.py`, `test_damage_ability_live.py` | 3 passed — inchangé |
| `test_damage_decomp_live.py` | 1 passed — inchangé |
| `test_brazier_of_holy_fire_live.py` | 3 passed — **resserré** : la géométrie Daemon confronte les 4 coups au lieu d'1 |
| `test_damage_catalog_live.py` | 4 failed — **préexistant, sans rapport** : `adeptSmnGeminaeSuperia` (summon) + 3 `admecBoss*` (npc) ne sont pas spawnables, le build est refusé avant toute assertion |

Le témoin non-Daemon reste bit-exact sur les DEUX vecteurs : le fix ne déborde pas de son périmètre.

### Gardes ajoutées

- `tests/engine/runner/test_daemon_extra_block_live.py` — cible Daemon : la source existe avec la
  chance et le montant de l'oracle gameconfig, l'attaque entière est bit-exacte, **et** la variante
  sans `Daemon_ExtraBlock` doit différer (sinon le scénario ne discrimine rien et le test le dit).
  Deuxième test : le témoin non-Daemon doit rester identique au legacy.
- `tests/engine/runner/test_block_chances_order_offline.py` — garde les faits B et C (ordre décroissant,
  ids distincts, un tirage par source tentée, source d'amount 0 sautée sans tirage).

---

## 5. Ce qui n'est PAS couvert

- **Deux sources de block simultanées sur un même défenseur, en LIVE.** Le pool ne le permet pas :
  `blackObliterator` et `worldEightbound` sont les deux seuls Daemon spawnables et aucun ne porte de
  `blockChance` de base ni de second ExtraBlock. Les faits B (identité) et C (tri) sont donc gardés
  **offline** contre le décompilé, pas discriminés en live.
- **Stabilité du tri à ≥ 3 sources de même amount.** Le port trie stable (Python), le natif utilise
  l'introsort non stable de `List.Sort`. Divergence possible seulement à ≥ 3 sources d'amount égal —
  jamais observé, et non montable avec le pool actuel.
- **Deux instances du MÊME `effect_type` ExtraBlock sur un porteur.** Le natif leur donnerait deux
  `BEntityId`, le port un seul `block_id` → un tirage d'écart à partir du coup 2. Non atteignable
  aujourd'hui : `DaemonAbility` fait `RemoveEffect(0x40a)` avant de re-poser, et les autres canaux
  ExtraBlock sont mono-instance.
- **La règle d'arrondi de `PercentageOf`.** Le port tronque (`int(attack × pct / 100)`) ; le
  `roundingRule` passé par `GetBlockDamage` vaut 0 et reste NON discriminé. Les deux `Attack`
  rencontrées tombent juste ou saturent : `906 × 50 / 100 = 453` exactement (le `514 − 453 = 61`
  ci-dessus valide l'amount, pas l'arrondi), et sur `worldEightbound` l'amount dépasse le dégât donc
  `453,5` comme `454` donneraient `0`. Il faudrait un défenseur Daemon à `Attack` IMPAIRE dont le
  block réussit sur un coup NON saturant.
- **La branche ÉVASION** de `CalculateDamageOperation` (slot 3, tentée AVANT le block quand le flag
  `metadata >> 0x28` est posé) reste non exercée — aucune cible évasive rencontrée.
