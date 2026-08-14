# #1039 — le capteur `rarity` : deux structs, un `0x74`, et cinq enums indiscernables

Le port n'avait **aucun** canal de rareté : ni `observeBattle`, ni `combatSnapshot`, ni
`decisionView` ne la publiaient, et le gameconfig répond à une autre question (`BaseRarity` est
la rareté de BASE — `"Common"` pour des MoW qui sont Mythic en bataille). Tout gate `HasRarity` /
`UnitsWithRarity` était donc inévaluable, et le rabattre sur « toujours vrai » aurait été une
dégradation **permissive** silencieuse — d'autant plus invisible que `rl_duel build` impose
`targetRarity = 5` à toute unité normalisée : dans ce régime **DÉGÉNÉRÉ**, un port sans gate est
d'accord avec le natif partout (`case-1024` §4).

**Le capteur est ÉCRIT, il n'est pas ARMÉ.** `frida/hooks/*` vit dans le process du jeu : ce
livrable exige une **fenêtre de reinject**. Rien ici n'a été confronté en live *à la sortie du
capteur* ; ce qui l'a été est dit à chaque section.

---

## 1. Ce que le natif lit — quatre foyers, un seul champ

| symbole | lecture |
|---|---|
| `IdunBattle.Entities.UnitExtensions$$HasRarity` | `GetBaseUnitComponent(unit)->[+0x74] == rarity` |
| `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` | `GetBaseUnitComponent(entity)->[+0x74] == this->[+0x20]` |
| `IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger` | `GetBaseUnitComponent(entity)->[+0x74] == this->[+0x18]` |
| `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` | `GetBaseUnitComponent(entity)->[+0x74] = config->[+0x80]` |

Les trois premiers sont les **consommateurs**, le quatrième la **source** : la fabrique recopie
`UnitConfiguration.Rarity` dans le composant. Le canal publie les deux ; **le composant fait foi**.

## 2. Le piège : le même `0x74`, deux structs, deux sens

Mesuré au RPC `classFields` sur `rnca9r7q6c` (session 88, sans reinject) :

```
IdunBattle.Entities.Components.BaseUnitComponent.Rarity                    offset 116 (0x74)  type Rarity
IdunBattle.Configuration.UnitConfiguration.AbilityVariablesMultiplierPercentage  offset 116 (0x74)  type Int32
IdunBattle.Configuration.UnitConfiguration.Rarity                          offset 128 (0x80)  type Rarity
```

`rpc-snapshot.ts` lisait **déjà** `UnitConfiguration+0x74`, sous `UCFG.mult`. Une recopie
d'offset d'un struct vers l'autre rendrait donc **180** (valeur relevée en runner standard) là où
on attend `0..5` — sans lever. Tout passe par `rawFieldOffset(<classe>, "Rarity")` ; les deux
littéraux du module n'alimentent que le rapport de **dérive**.

## 3. L'enum : `idun.meta.Rarity`, et le nom PLEIN est le SEUL discriminant

**CINQ** enums du build portent exactement les six mêmes membres aux mêmes ordinaux —
`idun.meta.Rarity` et `IdunMetaLogic.UserProgress.Model.{Unit,Item,Upgrade,XpBook}Rarity`. Une
confusion d'appariement serait donc **silencieuse en ordinal**. Celui que le combat lit est
`idun.meta.Rarity` : **type DÉCLARÉ** du paramètre `rarity` dans `frida/methods.tsv`, **4/4
concordants** aux quatre foyers du §1.

Le résolveur ne cherche pas cet enum par son nom : il **dérive la classe du champ lui-même**
(`fieldTypeClass(BaseUnitComponent, "Rarity")`) et **REFUSE** le canal si son nom plein n'est pas
`idun.meta.Rarity`. C'est le seul cran qui rende la confusion visible.
`case-1024` §4 et `#999-r1`/`#999-r3` nommaient le mauvais — **corrigés dans cette tranche**.

## 4. Pourquoi PAS `readUnitConfig` — mesuré, pas argumenté

Le point d'ancrage que `case-1024` §4 nommait (`readUnitConfig`, qui tient déjà le pointeur
`UnitConfiguration`) aurait livré un capteur **aveugle aux Machines of War**, c'est-à-dire aveugle
aux porteurs mêmes des résidus qu'il débloque. `readUnitConfig` ne trouve sa `VisualId` qu'en
filtrant sur la classe `IdunBattle.Entities.Components.UnitComponent` ; une MoW porte un
`MachineComponent`. Mesuré en live (runner 1315, `ultraTitus` + `adeptExorcist` vs
`thousSorcerer`, board `MC1_67`) :

```
entityId=79 entityType=6 (Machine)  unitConfig={"error":"visualId introuvable"}
entityId=80 entityType=1 (Unit)     unitConfig={"visualId":"ultraTitus","abilityVariablesMultiplier":180,...}
```

`IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` sert les deux familles
(`MachineComponent` **dérive** de `BaseUnitComponent`), et c'est littéralement la fonction que les
trois gates appellent. S'y ajoute que `GetUnitConfig(visualId)` est une jointure **N→1** : deux
entités de même `VisualId` (la même unité dans les deux camps) partagent la configuration rendue
alors qu'elles portent chacune LEUR composant.

## 5. Le contrat publié

`combatSnapshot` (et `unitsNotAlive`, pour la même raison qu'au #429-r1-r3-r1 : une unité qui a
FUI garde sa rareté) :

| champ | sens |
|---|---|
| `units[].rarity` | ordinal `idun.meta.Rarity`, lu sur le COMPOSANT. `null` = **pas mesuré** |
| `units[].unitConfig.rarity` | la source recopiée par la fabrique — **témoin**, pas le canal |
| `rarityEnum` | nom PLEIN de l'enum, **à assertionner** côté consommateur |
| `rarityTypes` | `{nom: ordinal}` de CET enum-là, dérivé du champ |
| `rarityLayout` | offsets résolus + `errors` + `drift` : un `null` de PANNE ne doit pas se lire comme un `null` de mesure |

Tri-état strict : jamais `0` en repli — `0` est `Rarity.Common`, une valeur parfaitement plausible.
Sous-lecture gatée par `debugOnly: ["rarity"]` (elle invoque du natif).

## 6. Les gardes, et ce qu'elles ont vu ROUGE

Aucune n'exige Frida.

- `frida/tools/probe-1039-rarity-canal.ts` — étape 1 **live** (`classFields` + `dumpEnum`, aucun
  reinject) : les trois offsets du §2 confirmés, piège d'offset partagé confirmé, enum confirmé.
  Étape 2 **déterministe** : 6 refus nommés (champ renommé / enum homonyme / offset hors instance
  / type non résolu / classe absente / enum vide), 2 dégradations bornées (témoin de config perdu
  ou mal typé → canal conservé, `configOffset = -1`, dérive), 1 suivi-de-champ-déplacé, 1
  contre-épreuve **verte**.
- `scripts/python/probe_1039_canal_rarete.py` — appariement : 5 enums indiscernables par ordinal
  (avec assertion de son propre non-vide), bijection du mirror `engine/entities/rarity.py`, 4/4
  types déclarés, contrat du RPC, **0 lecture à offset constant** dans le module.

**Vues rouges par MUTATION du code de PRODUCTION**, avant de rendre :

```
ROUGE enum homonyme d'ordinaux (IdunMetaLogic.UserProgress.Model.UnitRarity) : canal RENDU (componentOffset=0x74) -- il aurait du etre refuse
ROUGE champ deplace : suivi=false signale=false
ROUGE : le mirror ne CITE pas `idun.meta.Rarity` -- lequel des 5 transcrit-il ?
```

⚠ La **contre-épreuve verte reste VERTE** quand on remplace la résolution par le littéral `0x74` :
sur le build courant les deux coïncident. C'est le cas « champ déplacé » qui discrimine — un
accord en régime non-discriminant ne prouve rien, exactement le vice que ce capteur vient lever.

## 7. Ce qui N'EST PAS couvert

- **Le capteur n'a jamais émis.** Il exige une fenêtre de reinject. `#1039-r1` porte le montage.
- **La consommation côté port** : `UnitContext.rarity` et le threading vers les ctx d'effet ne
  sont pas de cette tranche (`#1025-r1`, `#1036-r1`, `#1036-r2`, `#1036-r3`, `#999-r3`,
  `#1024-r1`, `#1024-r2`).
- **Le régime dégénéré n'est pas quitté ici** : `rl_duel build` pose toujours `targetRarity = 5`.
  La sortie est `--unit-stat "<vis>:Rarity=N"`, écrit **APRÈS** la normalisation.
