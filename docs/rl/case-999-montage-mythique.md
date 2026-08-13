# #999 — La mythique de MoW n'a pas de voie à elle : c'est la voie TERTIAIRE de la relique

**Verdict** : le montage mythique est ÉCRIT, et il MORD (mesuré, avec contre-bras).
`catalog_inject.equip_mythic` / `write_mythic_seed_bc` / `rl_duel build --equip-mythic`.
Il débloque les **11** mythiques d'un coup — elles partagent toutes le même montage.

---

## 1. Ce qui n'était écrit nulle part, et ce qui le tranche

Le dépôt documentait le montage d'une **relique** (`case-237`) et recensait `mythicAbilities`
comme une **voie d'attribution** (`case-323` §2, `unit_map.py`) — mais aucune recette ne disait
comment en amener une en bataille. Mesure : **0** occurrence de `equip_mythic` / `graft_mythic` /
`MythicAbility` dans `scripts/**` et `frida/**` ; dans `frida/`, `Mythic` ne désignait que la
**rareté** (`UnitRarity` 5).

La réponse tient en une phrase : **il n'y a pas de voie mythique côté BATAILLE.**

### Le foyer META qui branche — `IdunMetaLogic.UserProgress.TertiaryAbilities$$GetTertiaryAbility`

C'est lui qui REMPLIT `BC.Units[].TertiaryAbility`. Il branche sur un unique test « ce porteur
est-il une Machine of War ? » :

```
if (<test MoW>)  ->  GetMythicAbilityForMachineOfWar(progression, unitId, progressionData)
else             ->  <chemin RELIQUE : lit l'item équipé, progressionData+0x18>
```

et **les DEUX branches écrivent le MÊME `Nullable` de retour**. Le pendant du niveau,
`IdunMetaLogic.UserProgress.TertiaryAbilities$$GetTertiaryAbilityLevelFromProgressionData`, a
exactement la même forme : même test, `Idun.Shared.Level$$.ctor(1)` côté mythique,
`GetAbilityLevel(<item>)` côté relique.

### Le foyer BATAILLE qui monte — `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`

Il ne connaît que **TROIS** voies, et il n'y a **aucune quatrième** :

| voie | champ de `UnitConfiguration` | inscription |
|---|---|---|
| actives | `+0xa0` (`List`) | `UnitFactory$$AddActiveAbility` |
| passives | `+0xa8` (`Dictionary`) | `TriggeredAbilityComponent$$TryAdd(id, passiveState, 2)` |
| **tertiaire** | `+0xb0` (`Nullable`) | `TriggeredAbilityComponent$$TryAdd(id, tertiaryState, **3**)` |

⇒ **le natif de combat ne sait pas, et n'a aucun moyen de savoir, si la tertiaire qu'il monte
vient d'une relique ou d'une mythique.** Les trois écritures de `case-237` s'appliquent telles
quelles.

---

## 2. Le montage — trois écritures, dont DEUX échouent en silence

Identiques à la relique. Ce qui change, ce sont les **chiffres**, et ils changent le montage :

| # | écriture | mythique | relique |
|---|---|---|---|
| 1 | `BC.Units[].TertiaryAbility` = id `TriggeredAbilityType` | 11/11 en sont | idem |
| 2 | `BC.Abilities.PassiveAbilities[<nom>]` = config synthétisée | **11/11 ABSENTES du seed** | 29/32 |
| 3 | `BC.Units[].TertiaryAbilityLevel >= 1` | **4 paliers** | jusqu'à 10 |

- **L'écriture 2 n'est JAMAIS optionnelle** pour une mythique — contrairement aux 3 reliques déjà
  équipées au seed, aucune mythique n'a sa config dans le BC capturé
  (`BC.Abilities.PassiveAbilities` = 194 entrées, 0 mythique). Sans elle,
  `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` ne trouve aucun tableau et
  `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` l'appelle avec `fallbackToDefault = false`
  → **lève** → « system error » au cast.
- **L'écriture 3** : `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
  convertit par `Idun.Shared.Level$$ToZeroBasedIndex`, qui **lève sur `<= 0`** — et `0` est
  exactement ce que porte toute entrée non débloquée. Pas de borne haute : le même foyer clampe
  (`idx >= len` → `len - 1`), donc le `50` qu'écrit `buildNormalizedBC` rend le **palier 4**.
- **ORDRE** : `buildNormalizedBC` réécrit `TertiaryAbilityLevel = targetAbilityLevel` (50)
  **seulement si `TertiaryAbility` est déjà non nul**. Poser après la normalisation
  (`rl_duel build --equip-mythic`) donne le niveau EXACT ; poser dans le seed
  (`write_mythic_seed_bc`) donne 50, clampé au palier 4 — le maximum, donc le régime le plus
  lisible.

### La GARDE, et pourquoi ce n'est pas un `allow_unlisted=True` sur `equip_relic`

`relic_carriers` dérive de `items[*].allowedUnits` et rend **`[]` pour les 11 mythiques**. Or
`equip_relic` teste `if carriers and unit_id not in carriers` : sur une liste vide, la garde est
**désarmée par sa propre condition** — `equip_relic` accepterait n'importe quel couple sans rien
vérifier. La mythique a sa propre source d'attribution, `units.<kind>.<id>.mythicAbilities`, et
c'est elle qui doit refuser. **Une garde qui ne garde rien est pire que pas de garde.**

### Le porteur

**11 abilities, 22 porteurs** — un couple (MoW `lineup`, MoW `npc`) chacune, 1 ability par unité.
**8 des 11** porteurs `lineup` sont au pool du seed ; **3** (`necroReanimator`,
`thousDaemonPrince`, `darkaStormSpeeder`) sont hors seed et exigent `augment` — d'où l'injection
catalogue **intégrée** à `--equip-mythic`, que `--equip-relic` ne fait pas.

---

## 3. La mesure — le montage MORD, et le contre-bras l'établit nécessaire

`probe_999_mythic_monte.py` ne relit pas le JSON qu'on vient d'écrire (ce qui ne prouverait rien :
les deux verrous échouent en silence). Il lit ce que **le natif a monté**, par `unitAbilityStates`
— le capteur y dumpe le `TriggeredAbilityComponent+0x18` instance par instance, `raw[0]` =
`AbilityName`, `raw[10]` = **hiérarchie**. La preuve cherchée est une entrée de hiérarchie **3**.

`necroReanimator` / `GuardianConstruct` (1530), board `MC1_67`, seed 777 :

| bras | hiérarchies vues | verdict |
|---|---|---|
| `--equip-mythic` | `{0: 6, 2: 4, **3: 1**}` — entité 81, `id=1530 level=1 mult=100` | **MONTÉ** |
| `--sans-montage` | `{0: 6, 2: 4}` — aucune hiérarchie 3 | **CONTRE-BRAS VERT** |

Le contre-bras n'est pas « le même build sans l'option » : il injecte le porteur par `augment`
**nu** — la primitive que `write_mythic_seed_bc` appelle AVANT `equip_mythic`, donc exactement le
même arbre moins les trois écritures tertiaires. Sans cela il aurait mesuré l'absence du
**PORTEUR** (`necroReanimator` est hors pool) et non celle du **MONTAGE**, et serait passé vert
pour la mauvaise raison. Son verdict est **INVERSÉ** : une inscription trouvée le rendrait ROUGE.

---

## 4. Recette

```powershell
# recensement (ids, paliers, porteurs, présence de la config au BC)
python catalog_inject.py --list-mythics

# montage live, niveau EXACT (posé APRÈS la normalisation)
python rl_duel.py build --seed 777 --board MC1_67 `
  --p-units necroDestroyer,necroWarden --a-units tyranParasite,tyranTyrantGuard `
  --p-mow necroReanimator --equip-mythic "necroReanimator:GuardianConstruct:1" `
  --state-file <ABSOLU>

# vérifier que ça a mordu
python probe_999_mythic_monte.py --unit necroReanimator --level 1
python probe_999_mythic_monte.py --unit necroReanimator --sans-montage
```

L'ability est **dérivable** du porteur : `--equip-mythic necroReanimator` suffit (chaque MoW n'en
porte qu'une — mesuré sur les 22).

Depuis un test : `catalog_inject.write_mythic_seed_bc(<out hors data/>, ["necroReanimator"])`,
puis `build --seed-bc <out>`.

---

## 5. Ce que le port en fait — le rail existe déjà

`collect_triggered_abilities` (`engine/runner/operations/triggers/dispatch/core.py`) lit la voie
tertiaire depuis **#357** : `UnitContext.tertiary_ability`, seedé par
`snapshot._load_tertiary_abilities` depuis le RPC `unitAbilityStates`, puis résolu contre
`RELIC_ABILITY_TRIGGERS` — registre **indexé par NOM**, donc il sert la mythique sans duplication.
Une mythique portée n'a qu'à y entrer.

⚠ `equip_mythic` appelle `declare_graft("mythic", …)`, comme `equip_relic` : le gameconfig ne dit
pas qu'une mythique est **débloquée**, donc sans le canal `unitAbilityStates` le port ne monterait
rien et toute assertion négative passerait à vide, en vert (`snapshot._refuse_if_grafted`).

---

## 6. Ce qui N'EST PAS couvert

- **Le CAST** n'est pas confronté ici : ce probe établit que l'ability est **MONTÉE**, pas que son
  behaviour produit le bon effet. Les six RE de §7 disent ce qu'il faudrait mesurer.
- Le **piège « system error »** (écriture 2 omise) n'a pas été joué en contre-épreuve — il est
  établi par le décompilé et par `case-237`, pas re-mesuré ici.
- Les **8 autres** mythiques ne sont pas montées en live ; rien ne les en distingue au montage
  (mêmes 3 écritures, mêmes 4 paliers), mais ce n'est pas mesuré.

---

## 7. RE des six abilities de la tranche — la catégorie annoncée était FAUSSE

**Aucune des six n'est une ability ACTIVE.** Ce sont des
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.<X>Ability` — `CreateBehaviour` /
`CreateTrigger` / `GetEffectType`, jamais `ExecuteBehaviour`. Elles **n'entrent donc pas dans
`ABILITY_CLASSES`** et ne portent ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` : ce sont des
**passifs déclenchés**, et leur registre est `RELIC_ABILITY_TRIGGERS`. C'est cohérent avec la voie
tertiaire, qui inscrit dans le `TriggeredAbilityComponent`.

| ability | `TriggeredAbilityType` | `EffectType` posé |
|---|---|---|
| `BlightedLand` | 1447 | 1442 `BlightedLand_ExtraDamagePct` |
| `ContemptuousDisregard` | 1450 | 1443 `ContemptuousDisregard_DamageReduction` |
| `HyperCorrosiveAcid` | 1455 | 1448 `HyperCorrosiveAcid_ExtraDamagePct` |
| `CabalOfSorcerers` | 1496 | 1494 `CabalOfSorcerers_ExtraDamagePct` |
| `MastersOfManoeuvre` | 1508 | 1510 `MastersOfManoeuvre` |
| `GuardianConstruct` | 1530 | 1548 `GuardianConstruct_ExtraDamagePct` |

**Trois n'exposent que `GetEffectType`** (`BlightedLand` → `0x5a2`, `ContemptuousDisregard` →
`0x5a3`, `GuardianConstruct` → `0x60c`) : leurs `CreateBehaviour`/`CreateTrigger` sont hérités
d'une base dont le corps est **dédupliqué** — l'absence dans les tables ne prouve rien.

### `CabalOfSorcerersAbility` (1496)

```
CreateTrigger   : DSLTriggers.OnOwnerSpecificAbilityInit(1496 = TriggeredAbilityType.CabalOfSorcerers)
CreateBehaviour : DSLBehaviors.AddEffect(1494 = EffectType.CabalOfSorcerers_ExtraDamagePct,
                                         AbilityStateReference,
                                         cfg+0x30 (Caster), cfg+0x30 (Caster), <durée par défaut>)
```
Passif permanent posé sur le caster à l'init de sa propre ability. Le plus simple des six.
⚠ L'argument d'`OnOwnerSpecificAbilityInit` n'est PAS qualifié : `1496` est un
`TriggeredAbilityType` valide (`CabalOfSorcerers`) **et** un ordinal partagé — lire le type
DÉCLARÉ dans `frida/methods.tsv` avant de l'écrire au site.

### `HyperCorrosiveAcidAbility` (1455)

```
CreateTrigger   : On(EventTriggerType.DamageTaken, true)
                  & AreEnemies(cfg+0x30, cfg+0x60) & IsAlive(cfg+0x60)
                  & ( AreFriends(cfg+0x30, cfg+0x40)
                      & IsUnitWithVisualId(cfg+0x40,
                            VisualUnitIdFromUnitId(GetStringConstant(AbilityConstantType.unitId))) )
CreateBehaviour : If( HasEffect(cfg+0x60, EffectType.HyperCorrosiveAcid_ExtraDamagePct, null, 6),
                      ChangeEffectTurns(cfg+0x60, EffectType.HyperCorrosiveAcid_ExtraDamagePct,
                                        TurnsFromRounds(GetNumberConstant(
                                            AbilityConstantType.nrOfRounds)), 1),
                      AddEffect(EffectType.HyperCorrosiveAcid_ExtraDamagePct,
                                AbilityStateReference, cfg+0x30, cfg+0x60,
                                TurnsFromRounds(GetNumberConstant(
                                    AbilityConstantType.nrOfRounds))) )
```
Le gate `IsUnitWithVisualId(acteur, VisualUnitIdFromUnitId(GetStringConstant(unitId)))` restreint le
déclenchement à un **acteur ami dont l'id visuel est celui nommé par la constante `unitId` du
gameconfig** — donc pas au caster. Refresh-or-add : la durée est **prolongée** si l'effet est déjà
là, posée sinon. Le vecteur est `DamageTaken` sur un **ennemi vivant**.

### `MastersOfManoeuvreAbility` (1508)

```
CreateBehaviour : AddEffect(EffectType.MastersOfManoeuvre, AbilityStateReference,
                            cfg+0x30, cfg+0x40,
                            TurnsFromRounds(GetNumberConstant(AbilityConstantType.nrOfRounds)))
CreateTrigger   : <A> | <B>,  avec  COMMUN = AreFriends(cfg+0x40, cfg+0x30)
                                            & HasRarity(cfg+0x40, 5)
                                            & !HasEffect(cfg+0x40, EffectType.MastersOfManoeuvre,
                                                         null, 6)
  <A> = On(EventTriggerType.UnitAfterMove, true) & COMMUN
        & AmountIsEqualOrGreater(TilesMovedThisTurn(cfg+0x40),
                                 Get(GetNumberConstant(AbilityConstantType.tilesTraversed)))
  <B> = On(EventTriggerType.UnitFinishedTurn, true) & COMMUN
        & AmountIsGreaterThanZero(
             Filter(AdjacentFriends(cfg+0x40, true, 3),
                    HasRarity(cfg+0x68, 5) & HasFaction(cfg+0x68, 0xa, 3)) )
```
Deux vecteurs OU : **avoir traversé assez de tuiles ce tour** (`tilesTraversed`), ou **finir son
tour adjacent à au moins un ami** du bon profil. `!HasEffect(…)` empêche le re-déclenchement tant
que l'effet tient.

⚠ **Trois littéraux NON qualifiés**, à ne pas écrire au site sans les lire :
`HasRarity(x, **5**)` — aucun enum `UnitRarity` n'a été trouvé dans
`data/symbols/<build>/frida/enums.tsv` (la seule piste, `StarType 3=Mythic`, est une **autre**
échelle) ; `HasFaction(x, **0xa**, **3**)` — ni la faction ni son second argument ne sont
qualifiés. Les qualifier fait partie de #999-r1.

⚠ **`MastersOfManoeuvreNonOwnerPlaybook` existe** (`IdunBattle.AI.Playbook.Loki`) : l'ability porte
un terme d'utilité de tuile sur les **voisins** du porteur, pas sur lui. Le porter sans ce playbook
laisserait la face DÉCISION muette.

### Les trois `GetEffectType`-only

`BlightedLandEffect` expose `CreateEffectDamageBonusForAttack` + `CreateTargetSelector` ;
`ContemptuousDisregard_DamageReductionEffect` et `MastersOfManoeuvreEffect` exposent
`CreateEffectDamageMalusForDefense` ; `GuardianConstruct_ExtraDamagePctEffect` et
`CabalOfSorcerers_ExtraDamagePctEffect` exposent `CreateEffectDamageBonusForAttack` +
`CreateTargetSelector` (+ `GetRefreshTriggers` pour le premier, `ValidCharacter` pour le second).
Le patron est donc **bonus/malus de dégât en pourcentage sous sélecteur**, à porter comme les
`*_ExtraDamagePct` déjà au registre.

---

### Carte de FAISABILITÉ du port — mesurée contre le vocabulaire DSL réellement porté

Les primitives ont été confrontées une par une au port. **12 des 16 existent** sous leur nom natif
exact ; **4 manquent**, et une seule est un vrai blocage :

| primitive native | état du port |
|---|---|
| `AreFriends`, `AreEnemies`, `IsAlive`, `HasEffect`, `HasFaction`, `IsUnitWithVisualId`, `AmountIsEqualOrGreater`, `AmountIsGreaterThanZero` | portées (`engine/entities/triggers.py`) |
| `AddEffect`, `ChangeEffectTurns`, `If` | portées |
| `TurnsFromRounds`, `Get`, `VisualUnitIdFromUnitId` | portées (`engine/entities/formulas.py`) |
| `AdjacentFriends`, `Filter` | portées (`engine/entities/selectors/units.py`) |
| `On` | pas un nœud — **collapsé** en `event_id` + `EventTriggerType` (rien à porter) |
| `OnOwnerSpecificAbilityInit` | pas un nœud — couvert par le registre de DONNÉES `ABILITY_INIT_OWNER_EFFECTS` (`engine/entities/effects/factory.py`), ou `event_id = AbilityInit` + gate `OwnerIsActor` |
| `TilesMovedThisTurn` | pas un nœud, mais la **valeur** est portée et mesurée (4 fonctions, dont `entities/effects/base.py::tiles_moved_this_turn`) |
| **`HasRarity`** | **ABSENTE, sans substitut — BLOCAGE CAPTEUR** : aucun canal `rarity` n'existe côté port (`BaseUnitComponent+0x74` non exposé) |

⇒ **ventilation des six** :

| ability | portable aujourd'hui ? |
|---|---|
| `CabalOfSorcerers` | **OUI**, et c'est la plus simple : `AbilityInit` + `AddEffect` permanent sur le caster. Ne demande que la classe d'effet 1494. |
| `HyperCorrosiveAcid` | **OUI** : toutes ses primitives sont portées (refresh-or-add sur `DamageTaken`). |
| `BlightedLand`, `ContemptuousDisregard`, `GuardianConstruct` | **à établir** — leur `CreateBehaviour`/`CreateTrigger` est hérité d'une base dont le corps est dédupliqué ; il faut d'abord identifier la base (slot de vtable, cf. `case-170`). |
| `MastersOfManoeuvre` | **BLOQUÉ — capteur** : son gate commun est `HasRarity(x, 5)`, et le port n'a aucun canal de rareté. S'y ajoute le `MastersOfManoeuvreNonOwnerPlaybook`, face DÉCISION non portée. |

Le patron d'effet, lui, est **déjà porté trois fois** (`DespoiledGround_ExtraDamagePct` 1478,
`DaughterOfTheAbyss_ExtraDamagePct` 1417, `EnmityForTheUnworthy_ExtraDamagePct` 1399) : une classe
`BaseEffect` qui surcharge `create_effect_damage_bonus_for_attack` et rend
`for_percent_increase(...)`, inscrite dans `EFFECT_CLASSES` (`engine/entities/effects/factory.py`)
sous le **nom d'`EffectType`**. Les cinq effets `*_ExtraDamagePct`/`_DamageReduction` de la tranche
s'y coulent sans invention.

⚠ **DEUX registres, pas un.** L'ABILITY (triggered) entre dans `RELIC_ABILITY_TRIGGERS`
(`engine/runner/operations/triggers/dispatch/registry.py`, indexé par NOM — il sert la voie
tertiaire, donc la mythique, sans duplication) ; l'EFFET qu'elle pose entre dans `EFFECT_CLASSES`.
Les deux sont nécessaires : inscrire l'effet seul laisse l'ability jamais déclenchée, inscrire
l'ability seule pose un `BaseEffect` nu qui n'agit pas.

---

## 8. Résidus ouverts

- **#999-r1** — porter les six abilities (aucune n'est portée). Le montage ne bloque plus ;
  ce qui reste est le travail d'effet + DSL + registre + playbook non-owner pour
  `MastersOfManoeuvre`.
- **#999-r2** — les 8 autres mythiques (`ShieldOfFaith`, `OnMyPosition`, `MoreGitzOverEre`,
  `ElectrochaffBackups`, `WisdomOfTheAncients` + les 3 déjà citées) : montage acquis, RE et port
  à faire.
