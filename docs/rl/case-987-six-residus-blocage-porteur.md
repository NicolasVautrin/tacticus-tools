# #987 — les six résidus `BLOCAGE: porteur`, re-mesurés

Un champ `BLOCAGE:` s'écrit à la fermeture d'une tranche, et **rien ne le re-mesure ensuite**. Ce
lot rouvre les six résidus `BLOCAGE: porteur` du dépôt en commençant par la **prémisse**, pas par
le montage.

**Quatre des six prémisses étaient fausses.** Aucun des quatre ne butait sur un porteur.

## 0. Verdicts

| résidu | ce que la prémisse disait | ce que la mesure dit | issue |
|---|---|---|---|
| `#945-r1` | « la branche MoW est inatteignable, le port la nomme au lieu de la deviner » | **déjà portée ET confrontée live** depuis #967 | fermé |
| `#952-r2` | « aucun chemin de spawn ne produit le porteur » | **vrai, et exhaustivement** — le régime n'existe pas dans le build | fermé |
| `#950-r1` | « 28 porteurs `Immune`, aucun `lineup` ⇒ non falsifiable » | le trait se **GREFFE** ; plan 2×2, port = natif à l'unité | fermé |
| `#957-r2` | « atteignable seulement au tour où l'ability est en cooldown » | **les deux pistes proposées étaient fausses** ; le levier est la DISTANCE | fermé |
| `#977-r3` | « il faut un board dont l'élévation est plate autour des cibles » | `highest` **n'est pas une propriété du board** — c'est un max sur les tuiles de MOUVEMENT | non résolu, blocage REQUALIFIÉ |
| `#977-r4` | « il manque un régime à utilité `<= 0` » | l'utilité de la stratégie 2 est **structurellement `>= 0`** — le régime décisif est l'utilité EXACTEMENT `0` | non résolu, blocage REQUALIFIÉ |

Le patron commun aux quatre premiers : **le résidu décrivait la recherche qui avait échoué, pas
la contrainte du build**. Trois fois sur quatre, la piste écrite dans le résidu était elle-même
fausse — la suivre aurait coûté plus cher que de repartir du décompilé.

## 1. `#945-r1` — la branche MACHINE OF WAR du slot 195

**Prémisse** : « `AlphaWarriorPlaybook` (1112) est le seul consommateur porté et son porteur
`tyranWingedPrime` n'est pas une MoW ». Elle se réfute en une requête.

`IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$GetSummonId` est le corps
DÉDUPLIQUÉ que tout playbook de summon appelle, et ses **XREFS ENTRANTES** en donnent **deux** :
`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$EvaluateNonComparable` **et
`IdunBattle.AI.Playbook.Loki.ForwardSpotterPlaybook$$EvaluateNonComparable`**. Le second appelle
le même slot `0xc3 = 195`.

Le porteur de `1143 ForwardSpotter` est **`astraOrdnanceBattery`** (Malleus Rocket Launcher),
`kind: lineup`, **trait `MachineOfWar`** — lu au gameconfig. C'est donc la SEULE branche qu'il
emprunte : `EntityExtensions.IsMachine(parent)` est vrai à chaque évaluation.

⇒ La branche est portée depuis #967 (`engine/playbook/noncomparable/summon_attack_range.py`,
foyer des deux branches) **et confrontée live** (#967-r5 : seed 777 / MC1_67, step 11
`natif ab=1143 tgt=84`, MISS → MATCH). Le port est fidèle à
`IdunBattle.Core.Services.BattleQuery$$HasSummonTargetInAttackRangeAtTileWithMachineParent` :

```
player  = EntityExtensions.GetOriginalPlayer(machineParent, state)   ; null -> throw
enemies = GetAllEnemiesOf(player.Id)                                 ; null -> throw
foreach target in enemies:
    if (IsTargetInAttackRangeForSummon(machineParent, unitId, tile, target)) return true
return false
```

**Un écart subsiste, et il est nommé** : le port itère `ctx.enemies` (ennemis du point de vue du
caster) là où le natif passe par `GetOriginalPlayer(machineParent)` → `GetAllEnemiesOf(player.Id)`.
Les deux coïncident tant que la MoW n'a pas changé de camp ; sous une possession, le natif garderait
les ennemis du propriétaire **d'origine**. Aucune ability du build ne retourne une MoW.

## 2. `#952-r2` — `GalvanicField` sans filet de spawn

Ici la prémisse est **vraie**, et elle devient un verdict parce qu'elle est mesurable
exhaustivement plutôt que constatable.

**Porteurs de `GalvanicField`, toutes voies du gameconfig** : 6, dont **un seul `lineup`** —
`admecManipulus`, plus ses cinq variantes boss `npc` (`admecBossManipulus`, `…LEG`, `…LHE`, `…CE`,
`…Surv`).

**Les 117 `constants.unitId` du gameconfig qui désignent une unité connue** (balayage exhaustif de
`activeAbilities` ∪ `passiveAbilities`) : **aucun** ne désigne `admecManipulus` ni aucune de ses
cinq variantes. Aucune ability ne l'invoque.

**Trois `PowerUp_HeroSpawn_*` spawnent bien un héros de LINEUP** en cours de bataille
(`custoVexilusPraetor`, `custoBladeChampion`, `votanUthar`) — c'est le seul chemin du build qui
matérialise une unité de lineup après le seed, et `admecManipulus` n'en fait pas partie. Sur les
**779 boards** de `data/boards/`, **zéro** cite un `PowerUp_HeroSpawn_*` ou un
`PowerUp_SummonSpawn_*`.

**Le passif ne peut pas non plus se re-déclencher** :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GalvanicFieldAbility` porte **`CreateBehaviour`
et rien d'autre** — aucun `CreateTrigger`, donc aucune ré-application en cours de bataille. Ses
trois feuilles s'exécutent une fois, au `UnitFactory`, donc **toujours avant** la capture.

⇒ Le régime « `GalvanicField` appliqué hors capture » **n'existe pas dans ce build**. Écrire le
filet de spawn serait un port dont aucun chemin de jeu ne peut exercer la différence.

## 3. `#950-r1` — `NOT HasTrait(Caster, Immune)`, le conjoint propre à la moitié COUPS

**Prémisse** : « 28 porteurs du trait, aucun `lineup` : aucun attaquant du pool ne peut
l'exercer ». Le comptage est juste ; c'est l'inférence qui ne l'est pas — **on n'a pas besoin d'un
porteur, le trait se GREFFE**.

`catalog_inject.write_trait_seed_bc(out, ["templHelbrecht:Immune"])` écrit
`BC.Units[].Traits`, le canal que `IdunBattle.Entities.Factories.UnitFactory$$Build` lit
réellement. L'attaquant des bras `tl_aura` / `tl_away` déjà validés devient donc `Immune` **sans
que rien d'autre ne change** — même unité, même géométrie, même cible, même seed.

Plan factoriel complet (`probe_950`, board `MC1_67`, seed 777, quatre tuiles `Grass` à
l'élévation 3, `--crit 0,0`) :

| bras | Jain Zar | attaquant `Immune` | natif : coups / total | port |
|---|---|---|---|---|
| `tl_away` | loin (0,4) | non | 6 / 9090 | identique |
| `tl_immune_away` | loin (0,4) | **oui** | 6 / 9090 | identique |
| `tl_aura` | près (0,2) | non | **5** / 3750 | identique |
| `tl_immune` | près (0,2) | **oui** | **6** / 4308 | identique |

Le trait n'agit **que** en présence de l'aura, et **que** sur les coups : le 6ᵉ coup revient
(`[618, 822, 718, 992, 600, 558]`) alors que chaque coup reste réduit de `dmgReduction[50] × 180 %
= 797` — exactement ce que dit le décompilé, où le conjoint est sur `1120` et pas sur `1119`.

**Contre-épreuve CIBLÉE** (`--mutate-immune`, qui neutralise le seul conjoint et rien d'autre) :
sur `tl_immune` le port retombe à **5 coups / 3750** contre **6 / 4308** au natif. La mutation
MORD, donc le vert n'est pas un accident de non-lecture.

**Découverte annexe, et c'est un résidu neuf (`#987-r1`)** : la voie CORROBORANTE — un vrai
porteur `Immune` du build, `darkaBossLion:4` monté par `--explicit-stats` — donne bien la mesure
NATIVE attendue (**4 coups conservés**, `[7978, 1566, 2146, 1573]`), mais son **rejeu offline est
structurellement impossible**. `combatSnapshot.unitConfig` rend `{"error": "config null"}` pour
une unité montée ainsi : elle n'a **aucune `UnitConfiguration`** côté natif, exactement comme une
unité INVOQUÉE. `UnitContext.from_snapshot` lit alors `weapons = []`, donc pas de `DamageProfile`,
pas de `PiercingRatio`, et le port rend **zéro coup**. Les deux bras boss sont donc marqués
`native_only` dans le probe. **Tout montage BOSS est natif-seul côté rejeu**, ce que la recette
`--explicit-stats` ne disait pas.

## 4. `#957-r2` — le veto de `1115 FearOfTheUnseen`

Le veto natif (`…FearOfTheUnseenPlaybook$$EvaluateNonComparable`) : l'**union** des cibles
d'attaque normale, prise sur TOUTES les tuiles atteignables (`IBattleQuery` slot `0x45`), est
**vide** ⇒ l'ability est proposée SUR LE CASTER, utilité constante 10.

**Les deux pistes que le résidu proposait sont fausses, toutes les deux :**

* *« patcher le cooldown initial dans `BC.Units[].Abilities` »* — `initialCooldownTurns = "1"`
  n'est pas dans `BC.Units[]` : c'est une entrée de
  `BC.Abilities.ActiveAbilities.FearOfTheUnseen.Constants`. Et le patcher serait **inutile** :
  mesure live, `1115` passe de `cd=1` à **`cd=0` dès le tour suivant**. Le tour 1 n'était pas le
  seul tour disponible.
* *« trouver un board dont la tuile de deep-strike est hors de portée »* — la tuile d'arrivée ne
  compte pas, et surtout **`--place` MORD sur `tyranDeathleaper`** (mesuré : il se pose exactement
  où on le demande, y compris en (6,8)). Le résidu avait conclu l'inverse d'une mesure sur
  `Movement=0`, qui, elle, ne mord pas — parce que le trait `TeleportStrike` lui donne un
  pathfinder de téléportation : avec `Movement=0` en (6,8), le natif propose encore
  `MoveUnitMessage to (0,3)` avec `pathLen = 1`.

**Le levier réel est la DISTANCE, et il n'agit qu'à partir du tour 2** : le `TeleportStrike` est
consommé par le déploiement, donc au tour suivant les tuiles de move sont celles du mouvement
normal. Deux bras, seule la tuile du Deathleaper change (`probe_987_fear_of_the_unseen_veto.py`,
adjacence ASSERTIONNÉE contre le `boardGraph`) :

| bras | Deathleaper | T1 (`cd=1`) | T2 (`cd=0`) |
|---|---|---|---|
| `loin` | (6,8) | move — 1115 non proposée (elle est en cooldown) | **`ActiveAbilityMessage caster=77 target=77 ability=1115`** |
| `proche` | (1,1), adjacent à la proie | attaque normale | attaque normale — 1115 **non** proposée |

Le port est confronté par l'oracle standard (`engine_validate --runner`, 6 pas) :
**`step 2 u77: ABIL native(ab=1115,tgt=77) engine=ability(ab=1115,tgt=77) [MATCH]`**.

`ncEvaluate` n'est pas l'oracle ici : c'est `aiDryRunAllUnits`.

## 5. `#977-r3` / `#977-r4` — NON RÉSOLUS, mais le blocage change de nature

`GenerateStrategy2Action` n'est atteint que si la stratégie 1 rend `null`, et il faut ENCORE que
`r.Value >= highest`. Le résidu cherchait un **BOARD** (« élévation plate autour des cibles, mais
une tuile occupée dont l'utilité dépasse toutes les tuiles libres du caster »). **C'est le mauvais
axe** : `highest` n'est pas une propriété du board.

```
GetHighestTileUtilityUnitCanMoveTo(unit):
    best = Fix64(0)
    foreach (p in battleQuery.<slot itf 0xb>(unit, null))    # LES TUILES DE MOUVEMENT
        best = max(best, GetUtility(Tile).EvaluateAttack(Base(unit, p.MainTile, ...)))
    return best
```

C'est un **max sur l'ensemble des tuiles de MOUVEMENT du caster** — donc réductible en réduisant
cet ensemble. Et le gate est un `>=`, pas un `>` : **l'égalité suffit**.

Mesure (`probe_987_thunderous_assault_strategy2.py`, montage de `probe_977`, board `MC1_67`,
seed 777), les deux termes du gate lus séparément :

| bras | `highest` | meilleure cible poussable | stratégie 1 | stratégie 2 |
|---|---|---|---|---|
| `mobile` | 50.0 | `(92, 30.0)` | `(88, 15.0)` — **NON muette** | `null` |
| `immobile` (`Movement=0`) | 50.0 | `(92, 30.0)` | `(88, 15.0)` | `null` |

**`Movement=0` ne déplace pas `highest`, et la raison est mesurée** : le caster est DÉJÀ sur sa
meilleure tuile, donc réduire l'ensemble à `{sa tuile}` laisse le max inchangé. Il faut donc, en
plus, **le poser sur une mauvaise tuile tout en gardant une cible poussable à portée**.

Et il faut réunir les deux conditions **SIMULTANÉMENT** — ce que ni le résidu ni ce lot n'ont
fait : sur ce montage la stratégie 1 parle (`15.0 > 0`), donc la stratégie 2 n'est même pas
évaluée par le natif.

**`#977-r4` se déduit du même corps, et se REQUALIFIE** : `highest >= Fix64(0)` par construction
(plancher explicite), et l'action n'est émise que si `r.Value >= highest`. Donc **toute action de
la stratégie 2 porte une utilité `>= 0`**, et la stratégie 1 est gatée `> 0`. Le régime « utilité
`<= 0` » que le résidu cherchait **n'existe pas** ; le seul régime où le défaut `MIN_UTILITY = 0.0`
de la classe de base pourrait mordre est une action d'utilité **exactement `0`**, c'est-à-dire
`highest == 0` **et** `r.Value == 0`. C'est une contrainte beaucoup plus précise que « il manque
un régime à utilité négative », et elle est atteignable en principe.

⇒ Les deux résidus restent OUVERTS, mais leur `BLOCAGE` n'est plus `porteur` : le porteur
(`templSwordBrother`) est au pool et se monte sans difficulté. C'est un problème de **calibration
de l'utilité de tuile** — faire descendre `highest` sous `r.Value` tout en gardant la stratégie 1
muette.
