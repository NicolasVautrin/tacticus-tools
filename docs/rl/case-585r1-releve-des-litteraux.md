# #585-r1 — le relevé des `selectionType` : trois pièges, dont deux que la fiche n'annonçait pas

La fiche annonçait UN piège (« un `3` recopié partout serait un masque faux »). Il est **réel et
mesuré**. Mais le relevé en a fait apparaître **deux autres**, tous deux de la même famille —
*le littéral n'est pas là où on le lit* — et aucun des deux ne se voit dans le pseudo-C.

## 1. L'état, re-mesuré

`probe_585r1_selection_type_call_sites.py` (inventaire **AST**, jamais un grep : les docstrings de
ce port citent les signatures natives à longueur de ligne) dérive les factories **du source** de
`entities/selectors/**` — toute classe/fonction dont la signature porte `selection_type` — puis
compte leurs call-sites.

| | avant la tranche | après |
|---|---|---|
| call-sites sous `runner/abilities/**` | 122 | 122 |
| dont **MUETS** (`selection_type` absent) | 120 | **94** |
| renseignés | 2 | **28** |

⚠ **Le compte de la fiche (107) était SOUS-ESTIMÉ, et pour une raison de méthode.** Elle énumérait
neuf factories *nommées* ; le probe les **dérive** et en trouve **13** (les quatre de plus sont
`non_steppable_or_object_units`, `adjacent_units`, `MechanicalUnits`, et le helper `_selection_ok`).
L'écart est exactement `9 + 5 + 1 = 15`. Même vice que celui recensé pour `probe_270r1` : *un
recenseur ne peut pas rendre zéro sur ce qu'il ne visite pas*.

## 2. Piège 1 (annoncé) — le contre-exemple EXISTE, et il est à `Any`

`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleResurrectTargets` :

```
pvVar3 = DSLSelectors$$AllDeadUnits(gs)
pvVar4 = DSLSelectors$$Friends(gs, gs@0x48, pvVar3, 0)      # <- 0 = UnitSelectionType.Any
```

Ses cibles **sont mortes**. `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` teste
`IsAlive` pour `OnlyAlive` **comme** pour `OnlyAliveAndTargetable` : un `3` recopié par symétrie
aurait **vidé l'ensemble**, donc désarmé la résurrection — sans erreur, sans crash, et avec un
champ qui *a l'air renseigné*. C'est la définition même du masque faux.

Sur les **28** sites relevés, **27** valent `3` et **1** vaut `0`. Le rapport 27:1 est précisément
ce qui rend la faute tentante : la symétrie « marche » 27 fois sur 28.

## 3. Piège 2 (non annoncé) — `AdjacentFriends`/`AdjacentEnemies` : le littéral **implicite**

Ces deux factories ont **DEUX surcharges d'arité 4**, au même nom affiché, indiscernables dans le
pseudo-C. Elles ne diffèrent **ni par le nombre d'arguments ni par leur type apparent** :

| VA | signature | ce qu'elle fait du `selectionType` |
|---|---|---|
| `AdjacentFriends` (variante A) | `(this, unit, unique, selectionType)` | **propage** le littéral au `Units` interne ET au `Friends` final |
| `AdjacentFriends` (variante B) | `(this, unit, unitTile, unique)` | **`3` EN DUR** aux deux étages ; le 3ᵉ argument est une **entité** (l'ancre géométrique), pas un booléen |

Idem pour `AdjacentEnemies`. Conséquence pratique : pour les **16 fonctions natives** qui empruntent
la variante B, `selectionType = 3` **n'est écrit nulle part dans leur corps**. Le lire au pseudo-C
donne `AdjacentFriends(gs, X, Y, 1)` — dont la lecture naïve serait « selectionType = 1 =
`OnlyAlive` », c'est-à-dire **le mauvais filtre** (l'`Untargetable` ne serait pas écarté).

Le discriminant est la **cible du `call`**, donc les **XREFS ENTRANTES** — jamais le pseudo-C.
Emprunteurs de la variante B (lus, pas devinés) : `RitesOfRestorationAbility$$GetHealTargets`,
`TalonOfHorusAbility$$GetAdditionalTargets`, `TalonsOfTheEmperorAbility$$ExecuteBehaviour` et
`$$MeetSecondDamageProfileRequirement`, `DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector`,
`FealtyAbility$$GetAdditionalTargets`, `SynapticInsight_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`,
`UnitEffectsAdjacentUtility$$GetSourceUnits`, `BladeOfMagnusAbility$$GetAdjacentTargets` et
`$$ExecuteBehaviour`, `CrushingClawsAbility$$GetAdjacentDamageTargetsUnits` et `$$ExecuteBehaviour`,
`MightFromBelowAbility$$GetPossibleSpawnTiles` et `$$ExecuteBehaviour`,
`PropheticSentinel_OverwatchAbility$$CreateTrigger`.

C'est la **même leçon** que les six formes de `TargetingOptions..ctor`, transposée aux sélecteurs :
la surcharge se tranche par ses xrefs entrantes.

## 4. Piège 3 (non annoncé) — le sucre booléen est **RARE**, et sa rareté est le résultat

La tranche amont avait établi que `Enemies`/`Units` ont une surcharge SUCRE
(`(onlyAlive & 0xff) + 2`, donc jamais `Any` ni `OnlyAlive`). Le relevé mesure **combien** de
call-sites natifs l'empruntent — et la réponse change la façon de travailler :

| surcharge | fonctions natives appelantes |
|---|---|
| `Enemies` **sucre** | **4** (`PlasmaGrenadeAbility$$ExecuteBehaviour`, `$$GetOtherTargets`, `PsychicStalk_VisualEffectEffect$$CreateTargetSelector`, `WeakerRearArmourEffect$$CreateTargetSelector`) |
| `Units` **sucre** | **7** (`ArcaneShieldAbility` ×3, `EnvDespoiledGroundTileAbility`, `EnvFireTileAbility`, `UnstoppableMomentumReworkedAbility$$CanContinue`, `FragBombAbility$$ExecuteBehaviour`) |

⇒ **Hors de ces 11 fonctions, tout `Enemies(...)`/`Units(...)` visible dans un pseudo-C est la
surcharge à `selectionType` explicite.** La liste est courte et se dérive d'un seul `list_xrefs` :
c'est ce qui rend le relevé *lisible au décompilé* plutôt que *devinable*. Le régime que la fiche
espérait — « dériver une classe entière d'un coup par la voie du sucre » — existe donc, mais il est
**minoritaire** ; le gros du travail reste la lecture site par site.

Les **10 autres factories sont mono-surcharge** (vérifié par `search_symbols_by_name`, pas par
absence dans une table) : leur littéral visible EST le `selectionType`.

## 5. Ce que la tranche a livré

**28 call-sites**, chacun LU au décompilé du build `rnca9r7q6c` :

| fichier | sites | fonctions natives lues |
|---|---|---|
| `runner/abilities/darkangels.py` | 8 | `DarkTalonStrikeAbility$$ExecuteBehaviour` / `$$GetTilesInLine` / `$$GetTilesInBestLine`, `DeathOnTheWindAbility$$ExecuteBehaviour` / `$$GetMachineAttackTiles` |
| `runner/abilities/deathguard.py` | 7 | `RevitalizingMalignancyAbility$$ExecuteBehaviour` / `$$GetAllHealTargets`, `PlagueburstMortarAbility$$GetMainDamageTarget` / `$$GetAdjacentEnemies` |
| `runner/abilities/blacklegion.py` | 5 | `BringerOfDespairAbility$$ExecuteBehaviour`, `HadesAutocannonsAbility$$GetAllTargets`, `DaemonicOrdnanceAbility$$GetAllDamageableTargets` |
| `runner/abilities/necrons.py` | 2 | `ResurrectionOrbAbility$$GetPossibleResurrectTargets` (**Any**), `MultiThreatEliminatorAbility$$GetNextHitTargetSelector` |
| `runner/abilities/sisterhood.py` | 2 | `ThriceBlessedConflagrationAbility$$GetTilesInLine`, `RitesOfRestorationAbility$$GetHealTargets` (variante B) |
| `runner/abilities/orks.py` | 1 | `WaaaghAbility$$GetBuffedUnitsSelector` |

Cliquet : `tests/engine/runner/test_585r1_selection_type_releve_offline.py` — quatre étages
(littéraux figés ; non-dégénérescence du relevé ; **morsure** de chaque littéral ; compte par
fichier). Contre-épreuve : `probe_585r1_mutants.py`, **3/3 mutants mordent**.

## 6. Deux règles de relevé, écrites parce qu'elles ont été appliquées

**(a) Un nœud du port qui n'a PAS d'équivalent natif ne reçoit RIEN.** Deux sites en relèvent :
le `Units(target_sel)` de `plagueburst_main_damage_target` et le `Units(Tiles(summons))` de
`hades_autocannons_targets` sont des **matérialisations** documentées (résolution tuile → occupant
que le natif fait *dans* `UnitsByTeamSelector$$CountOrAdd`). Leur poser un `selectionType` serait
inventer. Sans conséquence : le sélecteur qui les enveloppe (`Enemies`/`Friends`), lui, filtre sa
sortie.

**(b) Quand l'étage manque, on le DIT au site.** Quatre mirrors du port ne portent pas encore le
paramètre : `AdjacentUnits` (classe), `AdjacentFriends`, `SurroundingUnits`, `UnitsFromFaction`.
Leur `selectionType` natif vaut `3` aux sites relevés, et il est **sans conséquence observable
là où on l'a rencontré** — un sélecteur enveloppant filtre toujours la sortie. Résidu ouvert.

## 7. Ce qui n'est PAS couvert

* **94 call-sites restent MUETS** sous `runner/abilities/**`. Le probe les liste, **groupés par
  symbole natif** (l'unité de travail : un décompilé = tous les call-sites du port qui le
  mirrorent) — **57 symboles**, dont **31 sites** dont la docstring englobante ne cite aucun
  symbole (sortis à `?`, à identifier à la main).
* **Les 6 sites de `runner/operations/triggers/loki/**` et `entities/effects/loki/amulet_of_the_voidwyrm.py`** :
  hors périmètre par consigne (territoire d'un autre agent).
* **`AdjacentFriends`/`AdjacentEnemis` du port** (classes de `units.py`) : le littéral y entre
  **deux fois** et exige un changement de **structure**, pas d'arité. Non traité.
* **Aucune confrontation LIVE des 28 littéraux eux-mêmes.** Le régime qui les discrimine exige une
  unité `Untargetable` (deep strike, `AmbushEffect`) **dans le champ du sélecteur** — c'est
  exactement ce que #585 avait dû monter pour `WarHowl`. Les tests live rejoués ici prouvent la
  **non-régression** (aucune cible perdue sur des boards sans deep strike), pas la morsure ; la
  morsure est prouvée OFFLINE, par construction du substrat.
