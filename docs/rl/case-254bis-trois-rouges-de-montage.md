# case-254bis — Trois rouges qui n'atteignaient pas le régime qu'ils prétendaient tester

Suite directe de `case-254` §7, qui déposait trois échecs **pré-existants** au backlog. La question
posée était binaire : **le rouge accuse-t-il le MONTAGE ou le PORT ?** Réponse mesurée : **les trois
accusent le montage** — port et natif sont d'accord sur chacun. Mais **le diagnostic hérité était
faux sur deux des trois**, et les trois causes sont **indépendantes**.

| test | diagnostic hérité (#254) | cause RÉELLE, mesurée |
|---|---|---|
| `test_1082_inspired_to_greatness` | « aucune cible alliée hors contact dans la mesure » | la cible **existe** (d=2) ; c'est le **contrefactuel** que #247 a rendu muet |
| `test_dynamic_rules_bite_and_flip` | « l'ennemi au contact n'inflige aucun dégât » | **aucune attaque n'a eu lieu** : `{"kind": "attack"}` n'existe pas dans le harnais |
| `test_forward_spotter_...` | « tuile de spawn introuvable » (sans cause) | **littéral d'enum décalé** par la MAJ de build : `StepType.AddUnit` 10 → **9** |

Le point commun n'est pas la cause, c'est la **signature** : les trois échouent *après* le point où
le régime aurait dû s'installer, donc leur message accuse une conséquence et pas l'origine.

## 1. `test_1082_inspired_to_greatness` — un contrefactuel devenu muet

`cf_range` compte les lignes GAIN où **neutraliser le `TargetingRange` fait accepter** ce que le
natif refuse. Pour 1082 (`0x402`, `RANGE_ADJACENT`), la seule ligne candidate est l'allié **hors
contact**. Mesure du 2026-07-29, montage `C4_09`/777 **avant** correction :

```
ALLIE tauCrisis  d=2   natif 0x8000000 TargetIsInRange | APRES 0x8000000 | sansRange 0x1
```

La cible était donc bien là, à la bonne distance, en accord parfait avec le natif. Ce qui manquait,
c'est le **faux-accept** : depuis que #247 porte
`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason`,
un allié hors contact **à pleins PV** est refusé **deux fois** —

* par le volet PORTÉE, qui **précède** dans la cascade (d'où le `TargetIsInRange` natif) ;
* par la règle dynamique, dont les trois disjuncts sont faux (`0x1`, le littéral `ValidRequest`
  réutilisé comme code de refus).

Neutraliser la portée laisse donc la règle dynamique refuser : `sansRange = 0x1 != 0`, `cf_range = 0`.
**#247 a fermé un résidu et, ce faisant, éteint le contrefactuel du volet voisin** — sans qu'aucun
verdict de port ne bouge.

**Correction : on pilote les PV, pas l'assertion.** `probe_250.measure_all` amène désormais l'allié
lointain au régime **BLESSÉ** avant de figer l'état. Le disjunct `IsDamagedUnit` d'
`IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed` (slot `0x11` d'`IAttackQuery`) devient
vrai, la règle dynamique **accepte**, et le volet portée redevient le **seul** refus de la ligne :

```
ALLIE tauCrisis  d=2  hp 10526/10542   natif 0x8000000 | APRES 0x8000000 | sansRange 0x0   -> cf_range = 1
```

Le test **garde le régime** et pas seulement le compteur : il exige d'abord qu'une cible alliée hors
contact existe, puis qu'elle soit blessée, **avant** d'asserter `cf_range > 0`. Un montage qui
retomberait dans le cas non-discriminant dirait alors *pourquoi*.

## 2. `test_dynamic_rules_bite_and_flip` — l'action qui n'existe pas

Le montage T2 de #247 « amenait un ennemi au contact et le faisait attaquer » par
`applyAction{"kind": "attack", "unitId": …, "targetId": …}`. Cette action **n'existe pas** :
`applyOneAction` (`frida/hooks/features/ai-step/internals.ts`) connaît `move | ability | finish |
endturn` et retombe sur `buildErr = "unknown kind: " + action.kind`. Mesuré en live :

```
[kind=attack] ok=False  error="unknown kind: attack"  mutated=False
```

Le retour n'étant pas lu, le montage enchaînait sans rien signaler — d'où `7530 -> 7530`. Le
verdict `t2_1081` basculait quand même (`GetAdjacentEnemies` lit la seule **présence** de l'ennemi),
mais `t2_1082` restait à `0x1` **avec port et natif d'accord** : un rouge de montage déguisé en
demi-basculement.

**Correction** : l'attaque normale est une **ability**, et son `ActiveAbilityType` est **concret et
per-unité** (`ActiveAbilityComponent.NormalAttackType` — ici `69 Loki_NormalAttack`), lu dans
`decisionView.units[].abilities` où `kind == "normal"`. Surtout pas le `17` **synthétique** que
`engine/ai/state_bridge.py` emploie offline : `ActiveAbilityMessage` exige l'id que porte l'unité.
Le helper `probe_250._wound` caste, **relit les PV** et rend `(avant, après)` ; l'appelant échoue si
le régime n'est pas atteint. Sur `C4_09`/777 : `hp 7530 -> 7412`, les deux verdicts basculent.

### 2bis. Ce que la généralisation a cassé — et qui n'aurait pas été vu sur un seul board

Rejoué sur `C3_26`/31337, ce même correctif **échouait**. Deux faits distincts, tous deux mesurés,
et aucun n'était devinable depuis `C4_09` :

**(a) La distance hex n'est pas l'adjacence du jeu.** La première version conduisait l'attaquant à
`hexgeo.distance == 1` puis castait. Mesure : d=1, `hasAction=True`, son camp a la main — et le cast
rend `ok=true, error=null, mutated=FALSE`, **sept fois de suite**. `MovementUtil$$AreTilesAdjacent`
porte une **porte d'élévation** : deux tuiles voisines séparées par une marche ne sont pas au
contact. Ni la distance, ni `hasAction`, ni le tour n'expliquaient le refus — seul le fait de
**demander au jeu** l'explique. Le canal qui répond exactement à la question est **`castFromTiles`**
(`GetInvalidTargetReason` évalué **par tuile**) : `currentValid` = frappable d'ici, `moveTiles` = les
tuiles d'où ce le serait après déplacement. `_wound` l'interroge désormais au lieu de déduire, et il
trouve la tuile **en un round** là où la version « à vol d'oiseau » tournait 14 rounds à vide.

**(b) Blesser et mettre au contact sont DEUX régimes.** Les `necroWarden` sont **ranged** :
`castFromTiles` leur trouve une tuile de tir à **d=3**. La victime est bien blessée — 1082 bascule à
`0x0` — mais `GetAdjacentEnemies(caster)` reste **vide** et **1081 continue de rendre `0x2`**. Le
montage pose donc les deux séparément : `_wound` (PV), puis `_bring_to_contact` (adjacence, par
intersection des tuiles légales d'`aiMovableTiles` avec le voisinage de la victime), dans cet ordre
— le cast de `_wound` peut déplacer son tireur.

**(c) Le cul-de-sac se défait, il ne se constate pas.** Sur `C3_26` le hub tombe en `(0,5)`, colonne
de **bord** : voisins hors plateau, un pris par Aun'Shi, relief pour le reste. `_unstick_pair` sort
le couple (le hub avance de deux pas vers l'assaillant, l'allié **recolle** à d=1) — ce qui préserve
les deux invariants de T2 : `d_foe == 1` pour 1081, `d_ally == 1` pour la portée `RANGE_ADJACENT` de
1082. Il a fallu **deux** déblocages avant que le contact devienne atteignable.

Les trois conditions de T2 sont maintenant **assertées séparément** (`d_foe_t2`, `d_ally_t2`, PV),
pour qu'un échec dise **laquelle** manque au lieu d'accuser le verdict.

## 3. `test_forward_spotter_spawn_tile_follows_tile_utility` — un littéral d'enum décalé

Le test lisait la tuile de spawn dans l'event `kind == "action"` **et `step == 10`**. `step` est le
1er argument de `IdunBattle.Streams.StreamDispatcher$$Action(StepType, BEntityId,
Dictionary<TagKey,int>)`. Diff de l'enum entre les deux builds (`data/symbols/<build>/frida/enums.tsv`,
recoupé par `frida/data/meta/1.41.128/enums.json`) :

| membre | `gqfc5mff6c` | `rnca9r7q6c` |
|---|---|---|
| `RestoreArmorInfo` | **7** | **RETIRÉ** |
| `AddUnit` | 10 | **9** |
| `RemoveUnit` | 12 | **11** |
| `ChangeStats` | 13 | **12** |
| `ChangeAbility` | 14 | **13** |
| `ReceiveEffect` | 16 | **15** |

Un membre supprimé, **tout ce qui suit décalé de −1**. Le filtre `step == 10` désignait `AddUnit`
sur l'ancien build et désigne `AddMachine` sur le nouveau : plus aucun event ne matchait.
Confirmation par le dump live du cast 1143 — l'event d'apparition est bien là, en **step 9** :

```
kind=action step=9  tags={"Unit_Owner_Id":3,"Unit_IsSummoned":1,"Unit_SpawnSource":2,
                          "Unit_Parent_Id":79,"Unit_Foot_Tile_Id_1":13}
```

C'est **la même faute que le `TILE_LEAVES` décalé de `case-254` §3** : un littéral d'enum figé,
invalidé en silence par une migration de build.

**Correction : on ne re-pose pas `9`.** Le discriminant sémantique est le **tag** `Unit_IsSummoned`
— un NOM, qui a survécu à la migration. Le test passe par `_summon_tiles`, la lecture par tags déjà
présente **dans le même fichier** pour Waaagh : c'est précisément parce qu'elle ignore `step` que
ce test-là n'est pas tombé. Le port, lui, était juste — l'assertion finale
(`spawn_tile == port2[0]`, sur une géométrie assertée discriminante) passe sans y toucher.

## 4. Validation

| mesure | résultat |
|---|---|
| `test_tau_targeting_live.py` | **6 passed** (était : 2 failed) |
| `test_charge_tile_utility_live.py -k forward_spotter` | **1 passed** (était : 1 failed) |
| `test_charge_tile_utility_live.py -k "waaagh or black_rage"` | **2 passed** (garde : ils partagent `_summon_tiles`) |
| `probe_250_tau_targeting.py` (`C4_09`/777) | **PASS** — accord **40/40**, 0 mismatch, 0 résidu ; 1082 `cf_range 0 -> 1`, `cf_dyn 2`, `cf_rules 3` |
| `probe_250_tau_targeting.py --seed 31337 --board C3_26` | **PASS** — **39/40 + 1 résidu nommé**, 0 mismatch ; 1082 `cf_range 1`, `cf_dyn 2` |
| `probe_250_tau_targeting.py --bites` (`C4_09`/777) | **PASS** — T1 `(0x2, 0x1)`, T2 `(0x0, 0x0)`, hp `7530 -> 6528` |
| `probe_250_tau_targeting.py --bites --seed 31337 --board C3_26` | **PASS** — T1 `(0x2, 0x1)`, T2 `(0x0, 0x0)`, hp `7530 -> 7041` |

Le « reste à mesurer » de `case-250` §10.5 est **fermé** : les deux `GetDynamicInvalidTargetReason`
de #247 sont désormais confrontées LIVE sur `rnca9r7q6c` — elles ne l'étaient pas (RE faite sur
`gqfc5mff6c`, port validé structurellement hors ligne).

### 4bis. Un résidu que la généralisation a fait MORDRE — `AddCasterIfAtLeastOneTarget`

Le 40ᵉ point de `C3_26` n'est pas un désaccord : c'est le résidu **`AddCasterIfAtLeastOneTarget`**
(bit 11 du masque `0x802` de 1081), lu par
`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` et **non porté**
(`get_caster_not_added_reason` rend 0). `case-250` §4 le donnait « natif = 0 sur la ligne self des
deux couples » — vrai de **leur géométrie**, pas de la règle. Dans une géométrie où Darkstrider n'a
aucun ennemi adjacent, **toutes** ses cibles sont refusées par sa propre règle dynamique ; il ne
reste « au moins une cible » nulle part, et le natif rend `0x800` sur **sa propre ligne** :

```
1081  CASTER tauDarkstrider  d=0   natif 0x800 AddCasterIfAtLeastOneTarget | port 0x0
```

Le port dégrade du côté **permissif**, comme tout le module. La ligne est donc déclarée `RESIDU`
nommé dans `probe_250.CASES` — jamais comptée en `agree`, jamais confondue avec un mismatch. Ce
n'est pas une régression du port : c'est une règle **connue non portée** dont on sait maintenant
qu'elle **peut** mordre, et sous quelle condition exacte.

**Aucun fichier `engine/**` n'a été modifié** : les trois corrections vivent dans le probe et les
tests. C'est la conséquence directe du verdict — le port n'était en cause dans aucun des trois.

## 5. Ce qui n'est PAS couvert

* **`stream_events.py` est cassé par le même décalage, et personne ne le voit.**
  → **FERMÉ** : `case-254b-a-worktree-frais-enums.md`. Les deux premiers défauts l'ont été par
  `da556fbb` ; le troisième — la note d'infrastructure ci-dessous, qui rendait les deux autres
  **invisibles** en worktree — l'a été en repointant la source sur
  `data/symbols/<CURRENT>/frida/enums.tsv`. Le constat d'origine, conservé :
  Deux défauts distincts, tous deux **mesurés** :
  * `analyze()` teste `step == 12` (commenté `RemoveUnit`, qui vaut **11** ; 12 = `ChangeStats`) et
    `step == 16` (commenté `ReceiveEffect`, qui vaut **15** ; 16 = `LoseEffect`) ⇒ ses sorties
    `deaths` et `effects` sont **fausses** sur `rnca9r7q6c`. `step == 4` `UnitDamaged` reste juste
    (il précède le membre retiré), donc `damage`/`dealt`/`received` sont intacts — ce qui explique
    que rien n'ait rougi. Consommateurs : `rl_duel.py`, `rl_probe_step.py`, `probe_202b`, `probe_204`.
  * `step_name`/`group_name` lisent `enums.json` **à l'envers** (`values` y est `{NOM: ordinal}`,
    le code fait `get(str(ordinal))`) ⇒ ils rendent toujours `Step#N`. Le `__main__` du module le
    détecte (`AssertionError: Step#4`) mais n'est joué par aucun test.
  * Note d'infrastructure : `frida/data/` est **gitignoré**, donc dans un worktree frais la table
    est **vide** — une correction qui passerait par `step_name` y serait muette. La source
    versionnée est `data/symbols/<build>/frida/enums.tsv`.
* **`probe_202c_tutelaries.py`** filtre `step == 10 / 13 / 14 / 16 / 30`, tous décalés de −1 : son
  bloc `spawn_meta` ne se remplit plus. Non rejoué ici.
* **Le régime blessé est obtenu par une attaque réelle**, donc son amplitude dépend du roster
  (16 PV sur `tauCrisis`, 118 sur `tauDarkstrider`) : le test n'exige que `hp < hp_max`, jamais un
  seuil. La voie « seed BC `RemainingHealth < Health` » a été **essayée et REFUSÉE par la mesure** —
  le déploiement rend les PV pleins (`RemainingHealth 1223` posé, `hp 7530` observé).
* **Les autres volets non confrontés de `case-250` §9** (le `force_melee_target` de 1081/1082/1160/
  1161, le `range` de 1160/1161, la ligne de vue, `CasterHas2TurnsLeft`) restent tels quels : ce cas
  n'a rien mesuré de plus sur eux.
