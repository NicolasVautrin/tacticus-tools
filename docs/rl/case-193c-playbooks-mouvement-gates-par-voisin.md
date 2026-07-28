# case-193c — la face PORTEUR du gisement « playbooks de MOUVEMENT », et les deux premiers concrets dont le poids DÉPEND DU VOISIN

Résidu de #193. Deux livrables : le gisement enfin **croisé avec `--list-pool`** (la seule porte
valable), et **deux** playbooks portés — choisis pour ce qu'ils cassent, pas pour leur poids.

---

## 1. Question 1 — combien des 45 ont un porteur réellement spawnable ?

**34 sur 45**, nominativement, et le recroisement se re-dérive :

```bash
cd scripts/python && python probe_193b_carrier_pool_crosscheck.py
```

Le probe lit le pool **EN LIVE** (`rl_duel build --list-pool`, rank 17 : **97 unités régulières +
8 MoW**) et le croise item par item avec les porteurs du gameconfig, en traçant le chemin SUMMON
jusqu'à son summoner.

| verdict | n | ce que ça veut dire | chemin en bataille |
|---|---|---|---|
| `POOL-HERO` | **31** | un porteur `lineup` est DANS le pool | `--p-units <porteur>` |
| `SUMMON-HERO` | **3** | porteur `summons`, son summoner est dans le pool | spawner le summoner |
| `INJECT` | 5 | porteur `lineup` du gameconfig, HORS pool rank 17 | `catalog_inject.py` |
| `SUMMON-INJECT` | 3 | summoner connu mais hors pool | `catalog_inject` du summoner, puis summon |
| `SUMMON-ENV` | 2 | pas de summoner héros : portail **Environment** | board portant `EnvFactionSummons:<faction>` |
| `SUMMON-ORPHAN` | 1 | aucune ability du gameconfig ne cite ce summon | non établi |

**Spawnable TEL QUEL = 31 + 3 = 34.** Les 11 autres ne sont pas « bloqués » : 8 ont un chemin
d'octroi nommé (injection de catalogue, éventuellement suivie d'une invocation), 2 dépendent du
board, 1 seul reste non tracé.

### 1.1 La gate offline de #193 s'est révélée EXACTE — et c'est un résultat, pas un non-événement

Zéro désaccord entre `lineup-direct` (offline : présent dans `BC.Units` du seed) et `POOL-HERO`
(live) : **31/31**. Et zéro faux positif dans l'autre sens : les **5** classés `lineup-inject`
offline sont bien **hors pool** en live (`votanIronmaster`, `votanUthar`, `emperFlawlessBlade`,
`bloodTerminator`, `necroChronomancer`). Le seed BC et le pool du rank 17 coïncident **sur cette
face**. La réserve de #193 était donc justifiée à écrire (« devrait » n'est pas « est ») et se
solde par une confirmation — ce qui la ferme, au lieu de la laisser peser sur chaque dispatch.

### 1.2 Le chemin SUMMON n'est PAS dans l'unité, il est dans la config d'ability

`units.abilities[<nom>].constants.unitId` porte l'id du summon ; on remonte ensuite les unités qui
portent cette ability. C'est ce lien qui distingue trois situations qu'un simple `kind == summons`
écrase :

* **summoner dans le pool** — `admecSmnVanguard` <- `admecMarshall` (`ControlEdict`) ;
  `tauSmnDroneCommandLink` <- `tauShadowsun` (`ExemplarOfTheKauyon`) ; `astraSmnKell` <-
  `astraCreed` (`SwornProtector`). Ce sont les 3 `SUMMON-HERO`.
* **summoner hors pool** — `adeptSmnGeminaeSuperia` <- `adeptCelestine` ; `admecSmnTechpriest` <-
  `admecBossBelisarius` ; `darkaSmnTerminator` <- `darkaBossLion`. Atteignables, en deux temps.
* **portail Environment** — `votanSmnSteeljack` et `blackSmnTerminator` ne sont invoqués que par
  `EnvFactionSummons:<faction>`, l'invocation du 3e joueur permanent : leur confrontabilité est
  **board-dépendante**, pas roster-dépendante.

`darkaSmnWatcher` (porteur de `WatchedOver` 1524) n'est cité par **aucune** `constants.unitId` du
gameconfig : son chemin d'octroi reste à établir (résidu §7).

---

## 2. Question 2 — le choix des deux, et le critère

Plafond DUR : deux playbooks. Le critère appliqué, dans cet ordre :

1. **`POOL-HERO`** — porteur spawnable tel quel, sans injection ni invocation : c'est ce qui rend
   le port validable en live sans dépendance annexe.
2. **Porteur MONO-PLAYBOOK et MELEE** — `blackTerminator` n'a que `HatefulAssault` au kit déclenché,
   `darkaAsmodai` que `FearedInterrogator`, et aucun des deux n'a d'arme à portée. Le résidu
   `X = Tile(7) − Elevation − TileEffects` se réduit donc au terme mesuré (`RangedAdjacentEnemy`
   muette, aucun autre playbook dans le kit) : la mesure ISOLE l'étage au lieu de le déduire.
3. **Aucune feuille DÉDIÉE concurrente** — écarte `DefenderOfTheGreaterGood` (1155),
   `SaviorProtocols` (1120) et `KustomForceField*` (1102/1547), qui ont **en plus** leur propre
   feuille dans les 29 du composite : sur eux, `X` mélangerait deux canaux.
4. **Ce que le port ne sait PAS encore exprimer.** C'est le critère décisif, et il a fait passer
   devant deux items qui ne sont pas les plus gros poids du gisement.

Sur le point 4 : le port hissait le poids **hors** de la boucle des voisins
(`wf = self.get_adjacent_friend_utility(wt)` une fois, puis `val += wf` par voisin). C'était exact
pour les 4 concrets portés jusqu'ici — leurs accesseurs sont des lookups PLATS — et **inexact en
structure**. `FearedInterrogator` et `HatefulAssault` sont les deux premiers concrets qui **lisent
leur argument `unit`**, et ils le lisent de deux façons différentes. Les porter oblige à réparer la
signature, et les valide toutes les deux.

---

## 3. Ce que dit le décompilé

La signature native est `GetAdjacent{Friend,Enemy}Utility(unit, ctx)`, appelée **une fois par
voisin retenu** par le corps commun
`IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
(`val += virt_0x208(this, u_i, ctx)`). Trois formes coexistent, relues une par une :

| forme | concrets | argument `unit` |
|---|---|---|
| lookup PLAT | `GuardianOrganism` 1181, `RitesOfBattle` 1014, `MartialApotheosis` 1045, `FabricatorClawArray` 1006 | **non lu** (aucune instruction ne le touche) |
| gate sur le voisin, UN poids | **`FearedInterrogator` 1235**, `Deathwing` 1245, `TaintedNarthecium` 1067 | lu |
| DEUX poids selon le voisin | **`HatefulAssault` 1038**, `ExplosiveMaladies` 1068 | lu |

### 3.1 `FearedInterrogatorPlaybook` (1235, `darkaAsmodai`)

`IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$.ctor` passe `0x4d3 = 1235` à
`IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`.

```csharp
// IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$GetAdjacentFriendUtility
if (!UnitExtensions.HasFaction(unit, 10))          // UnitFaction.DarkAngels
    return 0;
return ctx.GetUtilityValue("FearedInterrogator_AdjacentDAFriend");   // 30 (BC)
```

Le gate est **dans l'accesseur de poids**, pas dans un `FilterAdjacentFriends` — le natif n'en
override aucun. Le port le mirror au même endroit : déplacer le gate dans le filtre donnerait le
même nombre et une structure fausse.

`IdunBattle.Entities.UnitExtensions$$HasFaction` ne compare **pas** un entier : il fait
`System.Enum.ToString(UnitFaction)` puis `String.Equals` contre le champ `FactionComponent+0x30`.
La faction est une CHAÎNE, dont le pendant offline est `FactionId` du gameconfig — `10` <->
`"DarkAngels"` (`IdunBattle.Entities.Enum.UnitFaction`, `data/symbols/<build>/frida/enums.tsv`).

### 3.2 `HatefulAssaultPlaybook` (1038, `blackTerminator`)

`IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$.ctor` passe `0x40e = 1038`.

```csharp
// IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$GetAdjacentEnemyUtility
return UnitExtensions.HasRangedWeapon(unit)
     ? ctx.GetUtilityValue("HATEFULASSAULT_AdjacentEnemyRanged")     // 20 (BC)
     : ctx.GetUtilityValue("HATEFULASSAULT_AdjacentEnemyDefault");   // 10 (BC)
```

**Aucun filtre ne peut exprimer ça** : un filtre garde ou jette, il ne module pas. C'est ce concret
qui impose l'argument `unit` sur l'accesseur.

`IdunBattle.Entities.UnitExtensions$$HasRangedWeapon(u, minRange)` délègue à
`IdunBattle.Entities.Components.WeaponsComponent$$HasRangedWeapon` = « au moins une arme dont
`IsMelee` est faux » ; le `minRange` **nul** (ce que passe le playbook) court-circuite la
comparaison de portée. Et `IdunShared.Battle.WeaponProfile$$get_IsMelee` =
`!Range.HasValue || Range.Value < 2` : **le seuil est `>= 2`, pas « `Range` présent »**. Les deux
formulations coïncident sur ce gameconfig (**0 arme à `Range == 1`**, compté), mais c'est le
décompilé qui est écrit dans le port — pas la coïncidence.

---

## 4. Ce qui a été porté

| Fichier | Contenu |
|---|---|
| `engine/playbook/adjacent_unit_preference.py` | signature `get_adjacent_{friend,enemy}_utility(unit, wt)` + appel **DANS** la boucle des voisins (forme du corps commun) ; `FearedInterrogatorPlaybook` (1235) et `HatefulAssaultPlaybook` (1038) ; helpers `_unit_faction` / `_has_ranged_weapon` (mirrors de `HasFaction` / `HasRangedWeapon`, résolus par le `vis` que `friend_units`/`enemy_units` portent déjà) ; registre `TRIGGERED_MOVE_PLAYBOOKS` 8 -> 10 |
| `scripts/python/probe_193b_carrier_pool_crosscheck.py` (**neuf**) | recroisement du gisement avec `--list-pool` + index summoner |
| `scripts/python/probe_193c_move_playbook_terms.py` (**neuf**) | confrontation par TUILE d'un playbook porté contre le natif, **avec recherche automatique du pas discriminant** |
| `tests/engine/test_tile_term_unit_gated_playbooks_live.py` (**neuf**) | 5 gardes × 4 montages (2 porteurs × 2 boards) |

Les 4 concrets déjà portés gardent un corps **identique** : leur argument `unit` est ignoré, comme
au natif — la signature change, pas leur valeur.

---

## 5. Validation

### 5.1 Le régime discriminant se CHERCHE — le montage par défaut ne discrimine pas

Premier montage `MC1_67`/777 sans réglage : la bataille se termine **au pas 17**, les rosters ne se
mélangent jamais, et le terme de `HatefulAssault` vaut **20 sur les 3 tuiles** évaluées. Une mesure
qui ne peut pas contredire le port ne le valide pas.

Le levier est `--hp-target 100000 --hp-player 100000` : les unités ne meurent plus, la bataille dure,
les deux camps s'imbriquent. Et `probe_193c` **cherche** le pas utile au lieu de le supposer — à
chaque activation du porteur il évalue le terme du port (gratuit : `aiStepDryRun` ne mute pas),
n'arme les hooks que si le terme varie, et **continue de marcher** si le terme s'avère plat sur le
sous-ensemble de tuiles que les hooks voient réellement (les tuiles du tier Comparable, pas toutes
les `action_tiles` — piège rencontré au 1er essai).

### 5.2 Arithmétique par tuile, contre la mesure native

Décomposition par étage (hooks EXISTANTS de `scorer-damage-trace`, armés pour UN `aiStepDryRun`,
désarmés en `finally` ; aucune réinjection) :

    X = Tile(7) − Elevation − TileEffects        (natif : scorerTileTermTrace / Elev / Leaf)

comparée au **même résidu calculé côté port** (composite `Tile(7)` du port ouvert feuille par
feuille, moins ses propres Elevation et TileEffects).

`HatefulAssault` 1038 — `MC1_67`/777 pas 34, u87 `blackTerminator` :

| tuile | Tile(7) nat | Elev | TileEff | **X nat** | X port | terme | voisins R1 |
|---|---|---|---|---|---|---|---|
| (5,6) | 25 | 5 | 0 | **20** | 20 | 20 | 1 ennemi **à portée** (T'au) |
| (6,5) | 49 | 20 | +9 | **20** | 20 | 20 | 1 ennemi **à portée** (T'au) |
| (4,4) | 30 | 20 | 0 | **10** | 10 | 10 | 1 ennemi **melee** (Black Templars) |
| (5,7) | 45 | 5 | 0 | **40** | 40 | 40 | 2 ennemis à portée (Dark Angels + T'au) |
| (3,4) | 40 | 30 | 0 | **10** | 10 | 10 | 1 ennemi **melee** |

**5/5 exact.** (5,6) et (4,4) ont le MÊME nombre d'ennemis adjacents — **1** — et des termes
différents, **20 vs 10** : aucun poids unique ne produit cette table.

`FearedInterrogator` 1235 — `MC1_67`/777 pas 28, u87 `darkaAsmodai` :

| tuile | Tile(7) nat | Elev | TileEff | **X nat** | X port | terme | amis R1 |
|---|---|---|---|---|---|---|---|
| (3,3) | 60 | 30 | 0 | **30** | 30 | 30 | 1 ami **DarkAngels** |
| (3,4) | 30 | 30 | 0 | **0** | 0 | 0 | 1 ami **SpaceWolves** |
| (4,4) | −5 | 20 | −25 | **0** | 0 | 0 | 0 ami |

**3/3 exact**, et là encore (3,3) et (3,4) portent le MÊME nombre d'amis adjacents pour des termes
30 vs 0 — c'est le gate de faction, seul, qui les sépare. Le natif joue (3,3).

**Généralisation, autre board, autres voisins** : `C4_09`/31337 pas 31 (`HatefulAssault`) **5/5**,
`C4_09`/999 pas 26 (`FearedInterrogator`) **4/4**. Sur `C4_09`/31337 la tuile (2,7) montre au
passage que la mesure ne suppose pas la pureté du montage : `X = 5` alors que le terme vaut 10 (une
autre feuille portée retire 5) — et `X nat == X port` quand même.

Total : **17 tuiles / 17**, 2 porteurs, 2 boards. Aucune constante n'a été cherchée : les trois
poids (30, 20, 10) sortent de la BC, lus AVANT la mesure.

### 5.3 Gardes vues ROUGES avant le fix

`tests/engine/test_tile_term_unit_gated_playbooks_live.py` — **20 passed** en l'état. Mutation
adversariale = retirer les deux entrées du registre (le comportement d'avant ce commit) :
**7 failed / 13 passed**. Les trois messages d'AGREEMENT, verbatim :

```
AssertionError: pas 34 (blackTerminator) : le port retient (3, 4), le natif joue (6, 5).
AssertionError: pas 31 (blackTerminator) : le port retient (2, 6), le natif joue (2, 8).
AssertionError: pas 28 (darkaAsmodai)    : le port retient (3, 4), le natif joue (3, 3).
```

⚠ **Le 4e montage (`C4_09`/999, `FearedInterrogator`) garde la même tuile sans le port** : son
agrément passe même muté. Il n'est pas décoratif pour autant — c'est lui qui prouve la *formule*
(4/4 tuiles au §5.2) et sa garde structurelle tombe bien rouge. On le dit plutôt que de laisser
croire que les 4 montages flippent.

La garde `test_weight_really_depends_on_WHICH_neighbour` mérite d'être lue : elle n'assère aucune
valeur gelée, elle vérifie que **le rapport `terme / nombre de voisins` prend au moins deux valeurs
distinctes** sur les tuiles candidates. Un accesseur à lookup plat rendrait `w × n`, donc un rapport
CONSTANT. Si une trajectoire dérive un jour vers une géométrie où tous les voisins se valent, ce
test tombe — au lieu de laisser les gardes suivantes passer à vide.

### 5.4 Non-régression

| suite | résultat |
|---|---|
| `test_tile_term_triggered_playbooks_live.py` (N13, les 4 concrets à lookup plat + AstartesBanner/Kardiocore) | **15 passed** avec `test_ah_master_annihilator_astartes_banner_live.py` |
| `test_move_tile_sweep_order_live.py` + `test_playbook_live.py` + `test_stay_in_place_live.py` | **8 passed / 3 skipped** — mêmes skips que ceux documentés par le case-N13 §5.3 (montages sans tie), inchangés |

La restructuration de la boucle est **value-preserving** pour les 4 concrets plats : leur accesseur
ignore l'argument, donc `Σ w` vaut ce que valait `w × n`. Le seul changement de comportement
observable est celui des deux abilities entrées au registre.

---

## 6. Le compte, après

```
NATIF     108
PORTE      10   (8 + FearedInterrogator 1235 + HatefulAssault 1038)
GISEMENT   43   (etait 45)  dont SPAWNABLE TEL QUEL 32 (29 POOL-HERO + 3 SUMMON-HERO)
```

Les deux items portés étaient tous deux `POOL-HERO` : le reste du rang A confrontable garde ses
plus gros poids intacts (`CursedPlagueBell` 20+10, `MedicusMinistorum` 15, `Deathwing` 10, …).

---

## 7. Ce que ce cas n'établit PAS

* **Le régime des 41 autres items du gisement** — l'inventaire de #193 §5 reste la carte ; ce cas
  n'en lit que deux corps de plus (`Deathwing` 1245 et `TaintedNarthecium` 1067, relus au passage
  pour classer les trois formes du §3, mais **non portés**).
* **`CursedPlagueBellPlaybook` (1071) n'est PAS un simple 3-lignes**, contrairement à ce que son
  rang A laissait supposer. Sa branche AMIS l'est (`HasTrait(u, 0x7ea)` -> `_AdjacentChaosFriend`),
  mais `IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$GetAdjacentEnemyUtility` lit le
  `WeaponsComponent` du voisin, appelle
  `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$GetDamageProfile`
  et filtre par `System.Linq.Enumerable.Any` sur un lambda
  (`u003CGetAdjacentEnemyUtilityu003Eb__4_0` : profil d'arme == profil de l'ability **et**
  `WeaponProfile.get_IsMelee`). À porter avec sa propre RE, pas dans un lot de 3-lignes.
* **`SpiritualLeader` (1275) et `ExplosiveMaladies` (1068)**, que #193 §5 listait « à trancher au
  décompilé » : tranché ici pour la STRUCTURE, pas pour la valeur. `SpiritualLeader` override bien
  un `FilterAdjacentFriends` (garde les amis à `HasTrait(u, 0x41d)`) et son accesseur est un lookup
  plat ; `ExplosiveMaladies` est de la 3e forme (`HasRangedWeapon` -> clé A, sinon `HasTrait(0x7ea)`
  -> clé B, sinon 0). **Aucune de leurs clés BC n'existe** sous un préfixe qui matche leur nom : le
  terme est donc vraisemblablement 0, mais la clé EFFECTIVE (les littéraux `DAT_*`) n'a pas été
  résolue — ne pas conclure « 0 » sans l'avoir lue.
* **`darkaSmnWatcher`** (porteur de `WatchedOver` 1524) n'est cité par aucune
  `units.abilities[*].constants.unitId` : chemin d'octroi non établi.
* **La résolution `vis` -> gameconfig pour un voisin SUMMON.** `_unit_faction` / `_has_ranged_weapon`
  résolvent le voisin par le `vis` que `friend_units`/`enemy_units` portent déjà — le même substrat
  que les `traits` consommés depuis #57i. Aucun des 4 montages n'a de summon dans le voisinage : le
  cas « le `visualId` d'un summon ne retombe pas sur son unitId gameconfig » n'est **pas** exercé.
* **Les caps `vtbl+0x228/0x238`** du corps commun — inchangés, toujours non répliqués (aucun montage
  ne les montre saturer ; max mesuré ici : 2 voisins qualifiants).
* **La face `TriggeredAbilitiesNonOwner(4)`** des deux abilities portées : ni 1038 ni 1235 n'a de clé
  dans `Utilities.Default.TriggeredAbilitiesNonOwner` (vérifié), donc rien à porter de ce côté —
  mais la feuille (4) reste globalement non portée.

---

## 8. Reproduire

```bash
cd scripts/python
python probe_193b_carrier_pool_crosscheck.py                       # face porteur (live --list-pool)
python probe_193c_move_playbook_terms.py --carrier blackTerminator --ability 1038 \
    --board MC1_67 --seed 777 --max-steps 60 --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "blackTerminator,spaceWulfen,orksNob,templSwordBrother,bloodIntercessor" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
python probe_193c_move_playbook_terms.py --carrier darkaAsmodai --ability 1235 \
    --board MC1_67 --seed 777 --max-steps 60 --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "darkaAsmodai,darkaTerminator,darkaCompanion,orksNob,spaceWulfen" \
    --a-units "worldKharn,templChampion,eldarJainZar,tyranDeathleaper,custoTrajann"
python -m pytest tests/engine/test_tile_term_unit_gated_playbooks_live.py \
                 tests/engine/test_tile_term_triggered_playbooks_live.py
```

⚠ `probe_193c` arme des hooks **RVA build-spécifiques** (`gqfc5mff6c`) : il vérifie le hash, arme
pour un `aiStepDryRun`, et désarme en `finally`.
