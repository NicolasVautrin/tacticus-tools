# Case #971 — les faces DÉCISION de catégorie SUMMON

**Statut** : LIVRÉ. Confronté live `rnca9r7q6c`, session 69, boards `MC1_67` / `C1_02`.
Correctif **100 % Python** — aucun changement `frida/hooks`, aucun rebuild, aucun reinject.

| item | verdict |
|---|---|
| `Waaagh` 1058 (`orksWarboss`) | **PORTÉ**, live 0 écart (2 boards + contre-épreuve de roster) |
| `SporeMineLauncher` 1145 (`tyranBiovore`, MoW) | **PORTÉ**, live 0 écart (2 boards) |
| `IronkinSteeljack` 1219 (`votanMemnyr`) | **PORTÉ**, live 0 écart (2 boards, 26 positions) |
| `CultDemagogue` 1179 (`genesPrimus`) | **DÉJÀ PORTÉ ET JUSTE** — c'est **l'AUDIT** qui était faux |

---

## 1. `1179` n'était pas un item — l'audit lisait 3 registres de décision sur 4

`audit_kit_coverage.py` croisait `noncomparable.PLAYBOOKS`, `playbook.REGISTRY` et
`_SPECIAL_ABILITY_CLASSES`, **pas** `playbook.bespoke.BESPOKE_SELFCAST`. Une COMPARABLE qui
override `EvaluateInternal` EN ENTIER n'entre ni dans l'un ni dans l'autre : elle est dispatchée
par `ai.action_generators._bespoke_candidates`.

Mesure du 2026-08-12 : **les 3 ids** de `BESPOKE_SELFCAST` — `1175 BloodChalice`,
`1179 CultDemagogue`, `1184 MomentShackle` — étaient invisibles des trois autres registres, donc
listés « face DÉCISION non portée ». `1179` a été **redispatchée sur cette foi**, alors que #957
l'avait déjà portée *et corrigée*.

Corrigé. La section « faces DÉCISION non portées dans des kits COMPLETS » passe de **43 à 40**
(6 retirées : les 3 faux GAP + les 3 portées ici ; 3 ajoutées : `1232`/`1198`/`1211`, dont les kits
deviennent COMPLETS grâce à des tranches mergées entre-temps).

---

## 2. RE — les trois corps, terme à terme

Base `NonComparablePlaybook`1` pour les trois, **LUE** dans `frida/classes.tsv` : le `.ctor` est le
corps gshared que Ghidra nomme `ComparablePlaybook<...>$$.ctor` pour les DEUX hiérarchies (piège
#487-r1 / #945). Reachability **LUE** dans `metadata/active_playbook_builders.tsv` (`active 1058 /
1145 / 1219`).

### 1058 `WaaaghPlaybook$$EvaluateNonComparable`

```
u = GetNumExistingUnitsBuffed(caster) + GetNumSummons(caster, casterPosition)
```

* `GetNumExistingUnitsBuffed(unit)` = `|Unique(Caster + AdjacentFriends(Caster,1,3)
  + UnitsFromFaction(Friends(Caster, AllAliveUnits, 3), 5 = Orks, 3))|`. Son `AbilityEntities` ne
  renseigne **que** `+0x08 = Caster` ⇒ `CasterTileSelector$$Select` descend jusqu'à
  `GetTiles(entities.Caster)` = l'ORIGINE. **Terme CONSTANT sur le sweep.**
* `GetNumSummons(caster, casterPosition)` = `Math.Min(GetNumberConstant(0x10) = nrOfSummons,
  |CanAddUnit(AdjacentTiles(casterPosition.MainTile))|)`. Son `AbilityEntities` pose
  `casterTile = MainTile(<position candidate>)` ⇒ **terme POSITION-dépendant.**

**Aucun des deux ne lit la cible** : l'utilité est constante sur les cibles d'une position, donc
`Bucket$$AddAction` (keep-first) fait que **la cible EST le premier élément du sélecteur**.

`GetUseProbability` est **surchargée** : `0.05 * GetStat(unit, 0xc = TurnsStarted) * nBuffed`.
`BasePlaybook$$ShouldEvaluate` : `p >= 1 -> True`, `p <= 0 -> False`, sinon **tirage RNG**. Les
deux branches déterministes sont portées ; la troisième est l'écart « porte aléatoire non
modélisée » déjà assumé (BlackRage 0.4, ItItches) — mais bien plus **mordant** ici (résidu
`#971-r2`).

### 1145 `SporeMineLauncherPlaybook$$EvaluateNonComparable`

```
u = 1 + |{ u in GetUnitsAtDistance(entities@+0x30 = TargetTile, 2) : IsEnemy(u, entities@+0x08) }|
```

Le slot `0x73` est **LU** (`interface_slots.tsv` : `IBattleQuery 115 GetUnitsAtDistance 2`) et c'est
un **RING EXACT**, pas un disque (`GetTilesAtDistance` filtre `dist == R`) — même slot et même
rayon que le terme `nE2` de `MasterOfTheTutelariesPlaybook`.

**Position-INDÉPENDANTE, et c'est démontré** : aucun terme ne lit `casterPosition`, et le masque
(`RANGE_WHOLE_BOARD`, pas de `CasterHasNotMoved`) ne porte aucune règle qui en dépende ⇒ l'argmax
est toujours atteint à l'origine ⇒ `to = None`.

### 1219 `IronkinSteeljackPlaybook$$EvaluateNonComparable` / `$$GetUtility`

```
u(ST) = nearest == null ? Fix64.Zero : -GetDistance(GetMainTile(nearest), ST)
        avec nearest = GetNearestEnemy(caster, position: UnitPosition(ST))   # slot 0x4a
```

⇒ **la tuile de spawn la plus PROCHE d'un ennemi**. Slots `0x4a`/`0x6c` LUS dans
`interface_slots.tsv`.

⚠ **SEUL playbook du registre SANS borne d'utilité.** Deux signaux INDÉPENDANTS, tous deux LUS :
le ctor du Bucket est la surcharge à **DEUX** arguments (aucun `Nullable`, là où 1058 et 1145
appellent celle à quatre), et la classe **n'a pas de `.cctor`**. Le gate (`Bucket$$AddAction` ->
`FUN_18004ed00`, lu) rend `true` dès que `minUtility.HasValue == false`. L'utilité étant **négative
par construction** (`-d`, `d >= 1`), le `MIN_UTILITY = 0.0` par défaut de la base aurait rejeté
**tous** les candidats, en silence ⇒ `MIN_UTILITY = -inf`.

Au passage, `AddAction` est confirmé **inclusif** (`utility >= min`) et son remplacement
**strict** (`op_GreaterThan`) — d'où keep-first au tie.

---

## 3. LE BUG QUE LA CONFRONTATION A TROUVÉ — l'ORDRE, pas la formule

Sur 1219, l'utilité était **exacte à 13/13 positions dès le premier jet**. Ce qui divergeait est la
**CIBLE** : `11` classes natives contre `10` portées. Les positions `(0,1)` et `(1,1)` retenaient la
MÊME tuile côté port et **deux tuiles distinctes** côté natif — toutes deux à utilité `-8`, donc un
**tie que seul l'ORDRE tranche**.

Cause : pour une position `T != origine`, le port énumérait l'**UNION** du RPC `abilityTargets`,
dont l'ordre n'est celui d'**aucune** position. L'ordre natif par position est **dérivable** : c'est
la liste d'adjacence **STOCKÉE** (`ctx.neigh_by_pos[T]`), celle que parcourt
`TargetingQuery$$GetTilesInRange` (`onlyAdjacent`) -> slot `GetAdjacentTiles` ->
`BattleQuery$$IterateAdjacentTiles`, et dont `TargetingQuery$$GetValidTargets` préserve l'ordre dans
son `OrderedSet`. Même substrat que `AdjacentTilesSelector$$Select` côté COMBAT.

Après correction : **13/13 étages, 11/11 classes, argmax identique**.

⚠ `GrotTankPlaybook` et `MasterOfTheTutelariesPlaybook` portent **la même approximation** (union
au lieu du voisinage stocké) — résidu `#971-r4`.

---

## 4. Confrontation — oracles, mesures, et ce qui n'est PAS couvert

| face | oracle | mesure |
|---|---|---|
| 1219 | `ncEvaluate` (leaf native invoquée PAR POSITION, Bucket décodé) | `MC1_67`/4242 : 13 positions, 13/13 utilités exactes, 11/11 classes ; `C1_02`/31337 : 13/13 et 13/13 |
| 1058 | `ncEvaluate` | natif `6` / port `6.0` (`MC1_67`) et `6` / `6.0` (`C1_02`) |
| 1058 | contre-épreuve de **roster** | Warboss SEUL : natif **3** / port `3.0`. Écart natif `6 - 3 = 3` = exactement les 3 alliés Orks retirés |
| 1145 | `aiStepDryRun` + `engine_decide` (routage caster Machine) | `MC1_67` : natif `{1145, target 55}` == port ; `C1_02` : `{1145, target 44}` == port ; `util 3.0`, `to None` |

`pbSlots`/`pbGate` (la SEULE voie qui tranche un slot 4 fondu par ICF) : pour **1058 et 1219**,
`slot0 get_Priority = 0` et `slot4 ShouldEvaluate = true` ⇒ `PRIORITY = 0` et le `should_evaluate`
par défaut sont justes.

**Le montage est PILOTÉ, pas subi.** Aux positions de spawn, `Waaagh` n'a aucune cible légale (il
exige un ennemi NON adjacent + une tuile de charge atteignable) : un accord port/natif sur ce vide
ne prouve rien. Les ennemis sont donc **immobilisés** (`--unit-stat <id>:Movement=0`) et le porteur
avance vers une tuile à **stand-off** de l'ennemi, l'éligibilité étant re-testée **avant** chaque
`endturn` — sans quoi la géométrie saute de « trop loin » à « au contact » sans jamais traverser le
régime.

**Ce qui n'est PAS couvert** :

* **1058, le sweep de POSITION** : une seule position rend un bucket (les tuiles de move rendent
  toutes un bucket VIDE — le port le retrouve indépendamment par `castFromTiles`, donc `to = None`
  des deux côtés). L'argmax inter-positions n'est donc pas exercé, et le probe le **dit**
  (`ARGMAX NON EXERCE`) au lieu de le taire.
* **1058, le terme `min(nrOfSummons, |tuiles libres adjacentes|)`** : il vaut `2` (saturé) dans les
  deux montages. Une position exiguë (`freeAdj < 2`) l'exercerait — non atteinte.
* **1058, la porte ALÉATOIRE** de `GetUseProbability` (résidu `#971-r2`).
* **1145, l'oracle par position** : `ncEvaluate` **et** `aiDryRunAllUnits` résolvent tous deux leur
  unité parmi les `EntityType.Unit`, et une MoW n'en est pas une — mesuré : `unit 83 not found`, et
  `aiDryRunAllUnits` ne couvre que les 2 unités de l'équipe. La confrontation passe donc par
  `aiStepDryRun`, qui rend l'action RETENUE, pas l'utilité par position (résidu `#971-r3`).
* **1219, `IsIrrelevantObject`** de `GetNearestEnemy` (`ctx.epos` ne publie pas le trait `Object`)
  et la comparaison d'EMPREINTES — écarts nommés, partagés avec les deux mirrors frères.

---

## 5. Fichiers

| fichier | rôle |
|---|---|
| `engine/playbook/noncomparable/waaagh.py` | 1058 |
| `engine/playbook/noncomparable/spore_mine_launcher.py` | 1145 |
| `engine/playbook/noncomparable/ironkin_steeljack.py` | 1219 |
| `engine/playbook/noncomparable/__init__.py` | registre (ajout minimal) |
| `audit_kit_coverage.py` | 4ᵉ registre de décision |
| `probe_971_summon_decision_faces.py` | MESURE |
| `tests/engine/test_971_summon_decision_live.py` | GARDE (5 tests, 5 verts) |
