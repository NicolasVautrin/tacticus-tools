# #514 — `AllUnits` du port n'était pas `AllUnits` : c'était `AllAliveUnits`

Résidu `#508-r1`, volet `AllUnits`. #508 avait constaté que le nœud partagé filtrait les mortes
alors que `LeadingTheCharge$$GetExtraPierceRatio` a besoin de l'inverse, et avait **refusé d'y
toucher** faute de mesure du rayon de souffle. Mesure faite ; la réponse n'était ni « le port est
faux » ni « le port est juste » : le nœud portait le **mauvais nom**.

## 1. Ce que le natif fait — TROIS primitives, un seul littéral d'écart

Les corps de `IdunBattle.Core.Services.BattleQuery$$GetAllUnits`, `$$GetAllAliveUnits` et
`$$GetAllAliveMachines` sont **identiques à l'ordinal d'`EntityPool` près**, et **aucun** ne porte
de prédicat de vie — le filtre EST le pool :

| primitive DSL | sélecteur | slot `IBattleQuery` | pool |
|---|---|---|---|
| `IdunBattleLogic.Entities.DSLSelectors$$AllUnits` | `AllUnitsSelector$$Select` | **136** `GetAllUnits` | `EntityPool.AllUnits` (8) — **morts inclus** |
| le champ **partagé** `<DSLSelectors>+0x20` (posé par `DSLSelectors$$InitializeShared`) | `AllAliveUnitsSelector$$Select` | **137** `GetAllAliveUnits` | `EntityPool.AliveUnits` (0) |
| `IdunBattleLogic.Entities.DSLSelectors$$AllAliveMachines` | `AllAliveMachinesSelector$$Select` | **151** `GetAllAliveMachines` | `EntityPool.AliveMachines` (6) |

`EntityPool` est LU dans `data/symbols/<build>/frida/enums.tsv`
(`0=AliveUnits,1=DefeatedUnits,…,6=AliveMachines,8=AllUnits,9=DestroyedMachines`). Le pendant
`$$GetAllDeadUnits` (slot 139) est le seul des quatre à porter un prédicat : pool `1` **puis**
`UnitExtensions$$IsDead`.

**Identité du champ `+0x20`**, établie deux fois indépendamment (aucun nom n'y est lisible) :
*(a)* élimination structurelle — il est alloué avec le ctor **trivial à 4 arguments**
`(this, state, battleQuery, 0)`, celui de `AllUnitsSelector` et d'`AllAliveMachinesSelector`, dont
les globales de classe sont différentes (une globale de classe n'a qu'**un** site d'allocation :
vérifié par `list_xrefs`) ; les `AllDead*`/`AllDefeated*` passent, eux, par
`AllDefeatedUnitsSelector$$.ctor` (3 arguments, corps distinct) ; ne reste dans `frida/classes.tsv`
qu'une classe de cette famille sans fabrique — `AllAliveUnitsSelector`. *(b)* la mesure LIVE de
#202 sur `GetEmRuntzAbility$$GetSpawnTileSelector`, qui écrit littéralement
`Enemies(<dsl>+0x48 = Caster, <dsl>+0x20, 3)` et dont les morts sont exclus **sans aucun
`Damageable`**.

⚠ **Les offsets `@0x80`/`@0x160`/`@0x148` que citait le port sont d'un build antérieur** (la classe
s'appelait `DSLFactory`). Carte re-lue sur `rnca9r7q6c` : `+0x18` AllTiles · **`+0x20` AllAliveUnits**
· `+0x30` Owner · `+0x48` Caster · `+0x60` Target · `+0x68` ActiveTarget.

## 2. Le SECOND étage : `selectionType`, qui peut re-filtrer une source pool-8

`IdunBattle.Entities.Enum.UnitSelectionType` = `0=Any, 1=OnlyAlive, 2=OnlyTargetable,
3=OnlyAliveAndTargetable`, et `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`
n'appelle `IsAlive` que sur `1` et `3`. Une source pool-8 sous `Enemies(..., 3)` redevient donc
vivante — c'est le cas de `DevastatingRefrain_AttackAbility$$CreateBehaviour` (`Friends(Owner,
AllUnits(), 3)`) et de `HeavyRailRifle_AttackAbility$$CreateBehaviour` (`Enemies(Owner, …, 1)`).
**Conclure « morts inclus » du seul pool est donc faux** ; il faut lire les deux littéraux.
Le port ne modélise `UnitSelectionType` nulle part — résidu **#433-r3-r2**, préexistant.

## 3. Rayon de souffle — MESURÉ avant toute édition

`probe_514_allunits_rayon_de_souffle.py` : inventaire **AST** (un grep comptait 5× trop, il voyait
les docstrings), puis walker sur les arbres **réellement construits** (`__slots__` **et**
`__dict__`) et évaluation **contrefactuelle** sur un plateau **à cadavres**.

**8 sites exécutables** dans `engine/**`. Chacun confronté au décompilé du call-site natif :
**7 passent `<dsl>+0x20`** (`TwinSmartMissileSystem$$GetAttackTargets`,
`GetEmRuntz$$GetSpawnTileSelector`, `RadBombardment$$AffectedTileAmount`,
`Waaagh$$GetBuffedUnitsSelector`, `Stormcaller$$ExecuteBehaviour`, `HellfyreMissileRack`,
`SilentDeath`) ; **1 seul** passe `DSLSelectors$$AllUnits` (`Waaagh$$GetAttackBehaviour`,
`KillDeadUnits(Killer(+0x68), AllUnits())` — dont le volet `downed` était donc **structurellement
vide**).

Le probe imprime, pour chaque site, ce que rend le **consommateur immédiat** sous les deux
contrefactuels : les **7** sites `+0x20` sont **SENSIBLES** à la suppression du filtre (un cadavre
entrerait dans leur `Enemies`/`Friends`). Retirer le filtre du foyer partagé aurait donc cassé 7
sites pour en réparer 1.

⇒ **Réparation = SCINDER, pas basculer.** `AllAliveUnits` (le nœud existant, renommé et
re-documenté sur `+0x20`) et `AllUnits` **neuf** (pool 8, sans filtre) ; chaque site re-pointé sur
ce que son natif passe.

## 4. Deuxième divergence, trouvée par la même mesure : `WeaverOfFate`

Parmi les **24** call-sites natifs de `DSLSelectors$$AllUnits`, `WeaverOfFateAbility$$GetTrigger`
écrit `Enemies(<dsl>+0x30 = Owner, AllUnits(), 0 = Any)` — **pool 8 ET `selectionType` `Any`**, deux
signaux indépendants, là où tous les autres call-sites passent `+0x20` avec `3`. Le port filtrait
`alive`, sur une hypothèse écrite (« les morts sont retirés du board natif ») que le décompilé
réfute. Dégradation **restrictive et silencieuse** : le gate « ≥ 3 ennemis ont reçu du Psychic ce
tour » ratait le déclenchement dès qu'une des trois cibles mourait du même dégât.
`RealityUnboundAbility$$CreateTrigger` appelle **littéralement** `WeaverOfFateAbility$$GetTrigger`
(seul appelant hors table, `list_xrefs`) — même corps, même correction.

## 5. Confrontation LIVE — il fallait des cadavres

`probe_514_extra_pierce_cadavres.py`, board `MC1_67`, seed 514. Le cadavre est **produit** : allié
NORMAL à `Health` **et** `RemainingHealth` rabaissés, au contact d'un tueur, puis `act endturn` +
`aiturn`.

| | témoin (personne ne meurt) | cadavre (un allié mort) |
|---|---|---|
| `Count(Filter(AllUnits, IsNormalUnit & AreFriends & HasBeenDefeated))` | `0` | `1` |
| `ExtraPierce` port / natif | `0` / `0` | **`10` / `10`** (`UnitStats_ExtraPierce_Modification=10`) |
| séquence coup par coup | `[1011, 911, 901]` == natif | `[1212, 1399, 1125]` == natif |
| tuile d'atterrissage | `(5,7)` == natif | `(3,5)` == natif |
| tirages `genrand_int32` | `10` == `10` | `13` == `13` |

**Contre-épreuve, même montage** : le port d'AVANT #514 (`AllUnits` filtrant) rend `pierce = 0` et
`[970, 1119, 900]` — soit **−20 %** sur la charge. C'est le coût **mesuré** de la confusion.
C'est aussi la preuve directe que `EntityPool.AllUnits` **contient les morts** : le natif compte
bien `1`.

⚠ **Deux pièges de montage, tous deux trouvés en mesurant** :
* **armure** — sans `--armor-target`, `Damage$$GetDamageWithPiercing` vaut
  `max(0, d − armure, d × pierce%)` et, armure à `0` (ce que pose `--hp-target`), c'est toujours `d`
  qui l'emporte : le port d'avant #514 rendait alors **la même séquence** que le natif. Un accord y
  aurait été **dégénéré**. Le probe rougit désormais tout seul dans ce cas ;
* **mort** — `decisionView` **conserve** les unités mortes et son `isDead` n'était pas posé : le
  cadavre à 0 PV se lisait « vivant » et le montage était déclaré RATÉ à tort.

## 6. Cliquets

`probe_514_allunits_rayon_de_souffle.py` (étape 3) refuse tout site `AllUnits(` non **déclaré** avec
le symbole natif pool-8 qui le justifie ; étape 4 fige les deux sémantiques.
`tests/engine/runner/test_514_allunits_pool8_offline.py` garde les deux, l'attribution site par site
(inventaire **dérivé** par AST, jamais une liste écrite à la main) et le fait que le sélecteur
d'`extraPierceRatio` compte un cadavre allié.

## 7. Ce qui n'est PAS couvert

* **`WeaverOfFate` / `RealityUnbound` ne sont pas confrontés live dans le régime qui les
  distingue** (3 ennemis touchés en Psychic dont un meurt). La correction repose sur le décompilé
  (source pool-8 **et** `selectionType = Any`) + la preuve live que le pool 8 contient les morts ;
  le montage qui le fermerait : `thousInfernalMaster` + 3 ennemis, une salve Psychic qui en tue un,
  puis lire la pose de `1185 WeaverOfFate_MaxOutDamage`. Résidu **#514-r1**.
* **22 des 24 call-sites natifs pool-8 ne sont pas portés ou pas vérifiés un par un.** Vérifiés :
  `Waaagh$$GetAttackBehaviour` (porté, corrigé), `LeadingTheCharge$$GetExtraPierceRatio` (porté,
  corrigé), `WeaverOfFate$$GetTrigger` (porté, corrigé), `HeavyRailRifle_Attack$$CreateBehaviour`
  (phase 2 **non portée**, et `selectionType 1` y re-filtre de toute façon),
  `DevastatingRefrain_Attack$$CreateBehaviour` (**non porté**, `selectionType 3`),
  `TheQuickening$$ExecuteBehaviour` (porté, mais son `Cache(AllUnits())` est l'argument
  d'**utilité** de `PerformAIAttackFromCurrentPosition`, que le port ne matérialise pas). Les 18
  autres restent à trancher. Résidu **#514-r2**.
* **`UnitSelectionType` reste non porté** (#433-r3-r2) : le port ne peut pas exprimer
  `Enemies(source, 3)` sur une source pool-8. Aucun site porté n'en a besoin aujourd'hui.
