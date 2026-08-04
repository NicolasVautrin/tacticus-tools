# `#419-r1-tr14-r5-r2-r1-r2-r1-r1` — `get_range` desarmait `only_adjacent` sur une valeur NON LUE

**Critere binaire** : quand la portee NUMERIQUE n'est pas resoluble, le natif desarme-t-il son gate
d'adjacence, ou l'evalue-t-il quand meme ?

**Verdict** : il l'EVALUE — la question est tranchee au decompile, et dans le sens qui accuse le
port. `onlyAdjacent` y est calcule AVANT toute resolution d'arme et n'en depend jamais ; le
consommateur le teste EN PREMIER, dans une branche qui ne lit pas la valeur. Le port sortait en
`return None` global et abandonnait donc les DEUX gates. Ecart **PERMISSIF**, ferme et confronte :
**CODE 5/9 -> 9/9 (4 gagnees, 0 perdue), VERDICT 7/9 -> 9/9 (2 gagnees, 0 perdue)**.

---

## 1. La chaine, LUE

`IdunBattle.Core.Services.TargetingQuery$$GetRange(caster, casterTiles, options)` — les **trois
seules** ecritures de `onlyAdjacent` (`cVar2` du decompile), dans l'ordre du corps :

```
if (casterTiles == null || casterTiles.Count == 0) return new Range(0, false, UseWholeBoard);
if (!cap.HasValue && options.Range.UseWholeBoard)  return 0x10000000001;   /* {1, false, true} */

onlyAdjacent = RangedBoolExtensions.IsTrue(options.Range.OnlyAdjacent, caster);   // (a) AVANT tout

if      (!HasAnyWeapon(caster))    v = GetStat(caster, Range 2);
else if (!HasRangedWeapon(caster)) v = 1;
else                               v = GetStat(caster, ExtraRange 0x18) + longestRanged.Range;
v = options.Range.OverrideRange.GetValueOrDefault(v);
if (options.Range.OverrideRangeFunc != null) v = OverrideRangeFunc(caster);

if (HasEffect(caster, 0x529 ForcedInMelee))           { v = Math.Min(1, v); onlyAdjacent = 1; } // (b)
if (IsTrue(options.ForceMeleeTarget, caster)
    && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true))
                                                      { v = Math.Min(1, v); onlyAdjacent = 1; } // (c)
return new Range(Math.Min(v, cap ?? int.MaxValue), onlyAdjacent, options.Range.UseWholeBoard);
```

**Aucune des trois n'utilise `v`.** (a) precede la resolution d'arme ; (b) et (c) ne font que le
FORCER a vrai, sous des conditions (`HasEffect`, `IsTrue`, `ShouldApplyRangedInMelee`) qui ne lisent
pas davantage la valeur.

**Corollaire, LU et non deduit** : les deux `Math.Min(1, v)` vivent dans le MEME bloc que
`onlyAdjacent = 1`. Une valeur clampee n'est donc **jamais** consommee par la branche distance —
clamper un `None` est structurellement sans effet.

### La struct de retour fait TROIS champs

```
Range = { int Value @+0x00 ; bool OnlyAdjacent @+0x04 ; bool UseWholeBoard @+0x05 }
```

Etabli par `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`, qui teste les trois
separement (`(int)range < 0`, `range._5_1_`, `range._4_1_`), et recoupe par le litteral du
court-circuit de `GetRange` : `0x10000000001` = bit 0 + bit 40 = `{Value = 1, OnlyAdjacent = false,
UseWholeBoard = true}`. Le port ne modelise que les deux premiers ; le troisieme est court-circuite
en amont (voir §5, residu nomme).

## 2. Le consommateur — et l'ORDRE de ses tests

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments), volet
portee :

```
if (!ignoreRangeChecks) {
    if (range.OnlyAdjacent) {                                   // range._4_1_ -- TESTE EN PREMIER
        if (!AreEntitiesAdjacent(casterTiles, target)) return TargetIsInRange;   // `Value` NON LU
    } else if (!options.Range.UseWholeBoard) {
        d = movementQuery.GetDistance(casterTiles, target);
        (rules & TargetIsAtRange) ? (d != (int)range ? TargetIsAtRange : 0)      // `Value` lu ICI
                                  : (d >  (int)range ? TargetIsInRange : 0);     //   et ICI SEULEMENT
    }
}
```

Deux choses non cosmetiques :

* le gate `UseWholeBoard` porte sur **`options.Range.UseWholeBoard`**, pas sur le champ du `Range`
  rendu — et il vit **DANS** la branche `!OnlyAdjacent` ;
* `(int)range` n'est lu **que** dans cette seconde branche.

## 3. L'ETAGE JUMEAU, qu'il ne faut PAS aligner

`TargetingQuery$$GetTilesInRange` consomme le MEME `Range`, dans un ordre **different** :

```
if ((int)range < 0)          -> set VIDE
else if (range.UseWholeBoard)-> GetAllTiles()
else if ((int)range == 0)    -> casterTiles (ou vide)
else if (range.OnlyAdjacent) -> tuiles adjacentes
else                         -> GetTilesInRadius(casterTiles, (int)range, ...)
```

**La valeur y est lue AVANT `OnlyAdjacent`** : une portee non resoluble y empeche reellement de
decider. `engine/services/ability_range.py::tiles_in_range_reach` a donc **RAISON** de rendre `None`,
et l'aligner « par symetrie » aurait ete un faux. Un cran offline l'interdit desormais.

C'est la reponse au point 3 du mandat (« verifie TOUS les appelants ») : le seul appelant Python de
`get_range` est `get_range_broken_rule` ; l'etage jumeau ne passe pas par lui et garde sa forme.
Les autres consommateurs natifs de `GetRange` — `GetAllObscuredTiles`, `GetValidTargets`,
`GetObscuredTileReasons`, `GetPossibleTargetTiles`, `GetRangeValue`,
`IsGuaranteedToHaveNoValidTargetsOnBoard` (xrefs relevees) — passent tous par `GetTilesInRange`.

## 4. Le port

`engine/runner/abilities/targeting.py` :

* `Range.value` devient un **tri-etat** (`Optional[int]`) : `None` = « la portee NUMERIQUE n'est pas
  observable », `only_adjacent` restant exact. C'est la structure du natif, ou les deux champs sont
  independants ;
* `get_range` ne sort plus en `None` sur `unit_weapon_range is None` ni sur `override_range_func` :
  il pose `value = None` et poursuit. Les deux clamps propagent le `None` (sans consequence, cf. §1) ;
* `get_range_broken_rule` porte le desarmement **dans la branche DISTANCE seule**, apres le test
  `only_adjacent` — exactement l'ordre natif.

`get_range` rend encore `None` (aucun gate) dans les trois cas ou **rien** n'est decidable :
`TargetingRange` non RE-lu, caster sans tuile, `UseWholeBoard`.

## 5. Ce que le correctif DEPLACE, chiffre

`probe_419r1tr14r5r2r1r2r1r1_range_only_adjacent.py`, catalogue **683** unites x **124** jeux
d'options du port (registre `ABILITY_CLASSES`, `TARGETING_OPTIONS_UNPORTED`, les 18 jeux d'attaque
normale) :

| mesure | valeur |
|---|---|
| couples DECIDABLES balayes | **63 519** |
| gate d'adjacence ARME par le correctif | **1 620** couples, **20** jeux d'options, **81** unites |
| gates PERDUS | **0** |
| couples a portee OBSERVABLE **inchanges bit a bit** | **58 867** (bouges : **0**) |

Les **81** unites sont exactement celles sans arme au gameconfig — le meme gisement que
`#419-r1-tr14-r5-r2-r1-r2-r1`, re-derive independamment.

Le produit cartesien est un MAJORANT. **Rayon REEL** (porteur x SES abilities) : **57 unites**,
**toutes** sur l'attaque normale generique `69` — soit 81 moins les **22** porteuses du trait
`MachineOfWar` (elles n'ont aucune attaque normale : `MachineFactory$$Build` n'appelle jamais
`UnitFactory$$AddNormalAttackAbility`) et moins les **2** Spore Mines, dont le type `1146` porte
`RANGE_ADJACENT` (`overrideRange = 1`, donc valeur CONNUE). Aucune des 3 abilities du registre du
majorant (`1004`, `1016`, `1076`) n'a de porteur sans arme.

Parmi les 57 : `genesSmnDecoy` (le caster du montage live), `genesDecoy`,
`astarNpc1HaywireMine` / `astarSmnHaywireMine`, `darkaNpc4Watcher` / `darkaSmnWatcher`, 20 `powup*`
et 31 `LootObj_*`.

**Le gisement `OverrideRangeFunc` est INERTE aujourd'hui** : son unique porteur du registre,
`1040 SpawnPoxwalkers`, pose `onlyAdjacent = RangedBool.False` ET `forceMeleeTarget =
RangedBool.False`, donc rien ne force l'adjacence hors de l'effet `0x529 ForcedInMelee` (pose par le
seul `TheQuickening`, sur son propre caster, le temps d'un cast). Le port le traite malgre tout de
facon uniforme — c'est la structure native, pas un cas mesure.

⚠ Le chiffrage exclut les **clamps de melee** (ils dependent de l'etat de bataille). Comme les deux
ne peuvent que FORCER `only_adjacent`, ils ne peuvent qu'AGRANDIR le rayon : c'est un minorant.

## 6. La CONFRONTATION — deux bras

`probe_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py`. Oracle natif :
`abilityReason(casterId, abilityType, targetId)` -> `AttackQuery$$GetInvalidTargetReason`.

**Bras 1** — le montage de `#419-r1-tr14-r5-r2-r1-r2-r1` REUTILISE tel quel : `genesPrimus` amene au
contact, puis `CultDemagogue` (1179) invoque `genesSmnDecoy` (`weapons = []` au kit **et** dans
`BC.Units`) et `genesSmnNeophyte` (ARME, temoin). Attaque normale `69`, masque `0x4002`.

**Bras 2** — le MEME montage, `PoundThemToDust` greffee sur le summon sans arme
(`catalog_inject.graft_active_ability`, config SYNTHETISEE) : la cascade
`UnitFactory$$AddNormalAttackAbility` substitue alors `1126 RogalDorn_NormalAttack`, masque
**`0x4000`** — donc **sans** `TargetMatchesDynamicRule`. Rien ne rattrape le refus en aval : c'est ce
qui rend ce bras discriminant sur le VERDICT.

```
BRAS 1  CASTER SANS ARME  u160 genesSmnDecoy (type 69, masque 0x4002)
  u77 tauCrisis      d=2      natif 0x8000000   apres 0x8000000   avant 0x2         <- CAUSE
  u79 tauMarksman    d=2      natif 0x8000000   apres 0x8000000   avant 0x2         <- CAUSE
  u81 necroSpyder    d=1      natif 0x2         apres 0x2         avant 0x2
        TEMOIN ARME  u114 genesSmnNeophyte
  u77 tauCrisis      d=2      natif 0x8000000   apres 0x8000000   avant 0x8000000
  u79 tauMarksman    d=1      natif 0x0         apres 0x0         avant 0x0
  u81 necroSpyder    d=2      natif 0x8000000   apres 0x8000000   avant 0x8000000

BRAS 2  CASTER SANS ARME + GREFFE  u160 (type 1126, masque 0x4000)
  u77 tauCrisis      d=2      natif 0x8000000   apres 0x8000000   avant 0x0         <- VERDICT
  u79 tauMarksman    d=2      natif 0x8000000   apres 0x8000000   avant 0x0         <- VERDICT
  u81 necroSpyder    d=1      natif 0x0         apres 0x0         avant 0x0
```

**9 lignes. CODE : 5 -> 9 (4 gagnees, 0 perdue). VERDICT : 7 -> 9 (2 gagnees, 0 perdue).**

`0x8000000` = `TargetIsInRange`, `0x2` = `TargetMatchesDynamicRule`.

**Ce que le bras 2 ajoute, et pourquoi il fallait le monter** : sur `0x4002`, le verdict etait deja
juste depuis `#...-r1-r2-r1` — mais par la MAUVAISE regle, donc le bras 1 seul aurait laisse croire a
une simple erreur d'imputation. Sur `0x4000`, la baseline **ACCEPTE** ce que le natif REFUSE :
l'ecart etait bien PERMISSIF.

**La BASELINE est exacte par construction** : `None if rr.value is None else rr` par-dessus le
`get_range` corrige. L'ancien corps sortait en `return None` exactement dans les deux cas ou le
nouveau pose `value = None`, et rendait le MEME `Range` partout ailleurs.

⚠ La greffe porte sur `BC` (ce que lit le NATIF) ; le port tire son type d'attaque normale du KIT
gameconfig et dirait encore `69`. Le jeu d'options `1126` est donc passe **explicitement** aux deux
modeles, et l'oracle interroge `abilityReason(cid, 1126, tid)` — on mesure le MEME jeu des deux
cotes. C'est le residu `#419-r1-tr14-r5-r2-r1-r2-r1-r2` (divergence des substrats) qui l'impose.

## 7. Ce qui GARDE

`tests/engine/test_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py` — 5 crans OFFLINE + 6 crans LIVE :
le tri-etat porte sur la VALEUR (pas sur le `Range`), l'etage jumeau reste `None`, le chiffrage et
son rayon reel, **l'accord MODELE <-> CODE**, le montage, l'accord sur la CAUSE, l'accord sur le
VERDICT, la contre-epreuve (regime degenere), l'ecart permissif NOMME sur le bras greffe, et la
non-perte + temoin arme inchange.

**Le cran `test_le_chiffrage_decrit_bien_le_code` existe parce que les deux crans de chiffrage qui
l'encadrent ne pouvaient PAS rougir** : ils raisonnent sur un modele de `get_range`, pas sur son
code — un inventaire deguise en garde-fou. Il APPELLE `get_range` sur un `State` synthetique et
confronte 4 000+ couples.

**CONTRE-EPREUVE JOUEE** : le `return None` d'avant remis en place (mutation VERIFIEE au `git diff`),
**2 crans offline rougissent** — `test_le_tri_etat_porte_sur_la_valeur_pas_sur_le_range` et
`test_le_chiffrage_decrit_bien_le_code` (**1 seul** avant l'ajout du second, ce qui a justement
motive son ecriture). Port restaure et re-verifie identique a HEAD (0 diff).

## 8. Residus nommes

* **`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1` — `Range.UseWholeBoard` n'est pas modelise.** Le natif rend
  un troisieme champ, que `GetTilesInRange` lit ; le port court-circuite `use_whole_board` en amont
  (`get_range` rend `None`) et obtient le MEME comportement observable sur le seul consommateur
  porte — le gate `UseWholeBoard` de `GetInvalidTargetReason` porte de toute facon sur
  `options.Range.UseWholeBoard`, pas sur le champ du `Range`. Aucun ecart mesurable aujourd'hui ;
  a modeliser si un jour le port mirror `GetTilesInRange` a partir de `get_range`.
* **`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r2` — le court-circuit `casterTiles` vide n'est pas mirrore.**
  Le natif rend `Range(0, false, UseWholeBoard)` (donc un gate de DISTANCE a `d > 0`) ; le port rend
  `None`. Sans consequence : `get_range_broken_rule` sort deja sur `src_feet` vide. Non confronte
  (aucun montage n'a de caster sans tuile).
* **`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r3` — `tiles_in_range_reach` rend `1` sur `only_adjacent` meme
  quand `ov == 0`.** Le natif teste `(int)range == 0` AVANT `OnlyAdjacent` et rend alors
  `casterTiles`, pas les adjacentes. Aucune combinaison reelle (`RANGE_SELF` a `only_adjacent` faux),
  donc inerte — mais c'est un ecart de structure, releve en lisant `GetTilesInRange` pour §3.
* **NON CONFRONTE, nomme** : les deux **clamps de melee** sur une valeur `None`. Le raisonnement qui
  les rend inoffensifs est une LECTURE (les `Math.Min` cohabitent avec `onlyAdjacent = 1`), pas une
  mesure : aucun montage du lot n'a de caster sans arme sous `ForcedInMelee` ni sous
  `ForceMeleeTarget` vrai (les 57 porteurs reels ont tous `forceMeleeTarget = IfRangedCaster`, faux
  faute d'arme a `Range`).
