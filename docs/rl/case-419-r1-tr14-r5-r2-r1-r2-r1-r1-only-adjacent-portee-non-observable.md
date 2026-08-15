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

* ~~**`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1`**~~ — **MIRRORE (2026-08-15), et la RE a rendu mieux
  qu'une equivalence de comportement.** `Range` porte son troisieme champ, et `get_range` ne rabat
  plus `UseWholeBoard` sur un `None` : il rend le litteral natif `0x10000000001` =
  `{1, false, true}`. Ce qui rend le mirror sur n'est pas l'inventaire des consommateurs — c'est
  que le champ est un **ALIAS EXACT** d'`options.Range.UseWholeBoard`, les TROIS sorties du corps
  natif l'ecrivant depuis cette meme source : (1) `casterTiles` vide le RECOPIE
  (`((*(ulonglong *)(options + 8) >> 0x28) & 0xff) << 0x28`) ; (2) le court-circuit n'est atteint
  que s'il vaut vrai ; (3) la sortie complete laisse les bits 40..47 a zero et n'est atteinte que
  s'il vaut faux. MESURE : **364** couples (182 abilities x 2 regimes), **0** ecart. L'ancienne
  justification, elle, se serait perimee au premier consommateur neuf.
  Le gate `UseWholeBoard` de `GetInvalidTargetReason` devient explicite dans
  `get_range_broken_rule`, a sa position native — DANS la branche `!OnlyAdjacent`, et il lit les
  **OPTIONS**. Un cran MUTANT le verifie (`Range` a `true`, options a `false` : le port doit quand
  meme poser son gate).
* ~~**`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r2`**~~ — **MIRRORE, et son PORTEUR EXISTE : la MACHINE OF
  WAR.** La fiche ecrivait « NON CONFRONTE — aucun montage du lot n'a de caster sans tuile » :
  **refute**. `MachineFactory$$Build` ne pose aucune tuile a une MoW — d'ou le bit
  `AllowNullCasterTile` sur ses masques — et **8 MoW sont au pool spawnable**. MESURE live
  (`--step mow_sans_tuile`, deux MoW distinctes) : `decisionView.mows[]` rend `pos: null`,
  `feet: []`, `platformTiles: []`.
  Le natif rend alors `Range(0, false, options.Range.UseWholeBoard)`, et
  `IdunBattle.Core.Services.MovementQuery$$GetDistance` sur une liste VIDE rend `int.MaxValue` (son
  minimum est initialise a `0x7fffffff` et la boucle externe n'est pas entree) — donc un refus
  `TargetIsInRange` systematique **hors `UseWholeBoard`**. Le regime d'ECART est neanmoins VIDE, et
  c'est MESURE : **22/22** masques `AllowNullCasterTile` portent `use_whole_board`, et les **22**
  unites `MachineOfWar` du gameconfig (11 hero + 11 npc) n'ont QUE ces deux actives-la, plus aucune
  attaque normale. Le mirror est donc exact ET sans effet observable — ce qui est exactement ce qui
  le rend sur a poser.
  **Reste NON MIRRORE, et c'est nomme** : `get_range_broken_rule` garde son rabat permissif sur
  `src_feet`/`dst_feet` vides. `entity_tiles` rend `[]` aussi bien pour « cette entite n'a pas de
  tuile » que pour « le port ne sait pas la resoudre » ; refuser sur le second inventerait une
  mesure. Le mirror exact du court-circuit vit donc un etage plus haut, dans `get_range`, la ou il
  est DECIDABLE.
* **`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r3` — FERME, mirror structurel.** Voir §10.
* **`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4` — les deux clamps de melee sur une valeur `None` : FERME,
  CONFRONTE sur le bras `ForceMeleeTarget`.** Voir §9. Le bras `ForcedInMelee` reste NON CONFRONTE,
  avec preuve d'impossibilite chiffree (§9.4).

---

## 9. `-r4` — les CLAMPS DE MELEE sur une valeur `None`, CONFRONTES

**Critere binaire** : quand la portee numerique n'est pas observable, un clamp arme-t-il quand meme
`onlyAdjacent` — et la valeur qu'il clampe est-elle consommee ?

**Verdict** : il l'ARME (D1 mesure), et la valeur clampee n'est **PAS** consommee (D2 mesure, pas
lu). Le port est confirme tel quel.

### 9.1 Pourquoi le regime n'avait jamais ete atteint, et comment on l'ouvre

`value is None` exige un caster SANS ARME. Or le clamp `(c)` de l'attaque normale generique teste
`ForceMeleeTarget = IfRangedCaster`, c.-a-d.
`IdunBattle.Entities.UnitExtensions$$IsRanged` = `HasTrait(0xb Ranged) || HasRangedWeapon`. Sans
arme le 2e terme est faux — et le 1er l'est **pour toute la population** (le trait `Ranged` n'est
porte par aucune des 683 unites, constat #161). Les deux conditions s'excluaient par la seule
structure du catalogue.

On les DISSOCIE en **posant le trait** : `catalog_inject.add_unit_trait` /
`write_trait_seed_bc` (#-r4) ecrivent `BC.Units[].Traits`, que `buildNormalizedBC` LIT (detection
MoW) mais n'ECRIT jamais. Le natif le lit par `HasTrait`, le port par
`combatSnapshot.units[].traits` — lu sur cette MEME entite native : **substrat UNIQUE**, donc pas de
divergence de substrat a la `-r2`.

**Effet de bord VOULU** : `RANGE_ADJACENT_IF_MELEE_CASTER` (`onlyAdjacent = IfNotRangedCaster`)
devient FAUX avec le trait. Le gate d'adjacence n'est donc plus arme par la BASE — **seul le clamp
peut l'armer**. C'est la sortie du regime degenere de la tranche precedente.

### 9.2 La mesure (`probe_419r1tr14r5r2r1r2r1r1r4_melee_clamp_live.py`, seed 4192, MC1_67)

Montage de §6 reutilise, + trait `Ranged` sur `genesSmnDecoy`. Traits publies par le NATIF sur les
4 decoys : `['Decoy', 'Ranged', 'Steppable', 'Xenos']` — et identiques cote port.

```
CASTER CLAMPE  u160 (type 69, masque 0x4002)   [un ennemi a d=1 -> ShouldApplyRangedInMelee vrai]
  u81 necroSpyder  d=1   natif 0x2         port 0x2         B1 0x2   B2 0x2
  u77 tauCrisis    d=2   natif 0x8000000   port 0x8000000   B1 0x2   B2 0x2   <- D1
  u79 tauMarksman  d=2   natif 0x8000000   port 0x8000000   B1 0x2   B2 0x2   <- D1
TEMOINS NON CLAMPES  u124/u137/u155 (d = 2..10)  natif 0x8000000 partout, port 0x2
SONDE  u160 (type 1126, masque 0x4000, forceMeleeTarget = False)
  u81 d=1  natif 0x8000000   port 0x0        <- `GetStat(Range) = 0`
```

**CODE : port 3/3, B1 1/3, B2 1/3 (2 gagnees, 0 perdue). VERDICT : port 3/3.**

⚠ **CETTE TABLE EST L'ETAT D'AVANT `-r4-r1`, ET DEUX DE SES COLONNES ONT BOUGE DEPUIS** (2026-08-15).
La ligne SONDE y montre `port 0x0` — l'ecart PERMISSIF que le residu `-r4-r1` nommait ; `get_range`
lit desormais `GetStat(caster, StatType.Range = 2)`, donc le port y rend `0x8000000` comme le natif.
Et la baseline **B2** a du etre RE-DEFINIE : gardee par `rr.value is None`, elle etait devenue
VACANTE (la valeur vaut `0`, plus `None`) et le cran D1 tombait en regime degenere. Elle enonce
maintenant directement « les deux clamps n'arment PAS `onlyAdjacent` », ce qui est la question de la
tranche ; son discriminant s'est deplace de `d >= 2` vers **`d = 1`**, ou le clamp decide encore.
Les crans correspondants gardent l'ACCORD la ou ils figeaient l'ECART.

### 9.3 Ce que chaque etage prouve

* **D1 — le clamp ARME `onlyAdjacent` sur une valeur inconnue.** A `d = 2` le natif rompt
  `TargetIsInRange` ; B2 (« le clamp abandonne sur `None` ») n'arme aucun gate. Le regime n'est
  donc pas degenere, et l'accord du port est probant.
* **D2 — la valeur clampee n'est PAS consommee, MESURE.** La SONDE etablit
  `GetStat(caster, StatType.Range = 2) = 0` : sur `1126` (`forceMeleeTarget = RangedBool.False`,
  masque `0x4000` sans regle dynamique pour rattraper), le natif rompt `TargetIsInRange` des `d = 1`.
  Le clamp poserait donc `min(1, 0) = 0`, avec quoi la branche DISTANCE refuserait TOUTE cible
  (`d >= 1 > 0`). Or sur le caster CLAMPE le natif ACCEPTE le volet portee a `d = 1`. C'est la
  branche `OnlyAdjacent` qui a repondu.
  ⚠ Le bras 1 SEUL ne pouvait pas conclure : ses temoins n'ont, par construction, aucune cible a
  `d = 1`, donc il ne rendait que la BORNE `Value <= 1` — et avec `Value == 1` les deux branches
  coincident (accord DEGENERE). La sonde est ce qui leve l'ambiguite.
* **B3 (« le clamp pose `value = 1` ») est INDISTINGUABLE, et c'est mesure** : 0 ecart sur 384
  couples sous `only_adjacent`, sur un balayage qui rend 2 codes distincts et 172 ecarts HORS
  `only_adjacent` (la, la valeur EST lue). Mais `None` reste le seul choix qui ne MENTE pas : la
  valeur native est `0`, pas `1`.
* **L'axe VERDICT est SATURE** sur ce jeu d'options, et c'est structurel : le masque `0x4002` porte
  `TargetMatchesDynamicRule`, et `ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason` refuse
  toute cible d'un caster sans arme. Seul le CODE discrimine — le probe le DIT plutot que de compter
  un accord.

**CONTRE-EPREUVE JOUEE** : les deux clamps remplaces par B2 (mutation verifiee au `git diff`) —
`test_d1_le_clamp_arme_only_adjacent_sur_une_valeur_inconnue` rougit (2 lignes de CODE). Port
restaure, 0 diff.

### 9.3bis GENERALISATION — trois configurations, meme conclusion

| board / seed | verdict | `GetStat(Range)` | gagnees/B2 sur le CODE |
|---|---|---|---|
| `MC1_67` / 4192 | PASS | 0 | 2 sur 3 lignes |
| `MC1_67` / 777  | PASS | 0 | 2 sur 3 lignes |
| `C2_01` / 4192  | PASS | 0 | 1 sur 4 lignes |
| `C4_09` / 31337 | **MONTAGE NON POSE** | — | — |

Le 4e cas n'est PAS un desaccord : les summons y apparaissent loin de tout ennemi et le seul
rapprochement possible passerait par des `endturn` — or les `genesSmnDecoy` sont EPHEMERES et n'y
survivent pas (MESURE : apres 3 rapprochements via `_step_toward`, plus AUCUN decoy vivant).
`forcer_contact` PILOTE donc la geometrie sans jamais consommer de tour (il ne bouge que ce qui est
deja activable) et s'ARRETE en nommant la cause, plutot que de defaire le montage en silence.

**D3 est couvert par le bras 2**, et non par un cran separe : la ventilation `clampe / non clampe`
est calculee par le PORT, mais la sonde donne un caster ADJACENT que le port classe non clampe
(`forceMeleeTarget = False`) — et le natif l'y refuse a `d = 1`, tandis qu'il ACCEPTE le caster
clampe a la meme distance. Les deux modeles s'accordent donc sur le DECLENCHEMENT, sur deux casters
que seule cette condition separe.

### 9.4 Le bras `ForcedInMelee` — NON CONFRONTE, impossibilite chiffree

Poseur LU : `TheQuickeningAbility$$GetTriggerAttackBehaviour` =
`If(HasFaction(unit, 0xe BloodAngels), AddEffect(0x529, AbilityStateReference, unit, Nullable(1))
& ... & RemoveEffect(unit, 0x529))`. Trois verrous independants :

1. **gate de faction** — **0** des **81** unites sans arme est `BloodAngels` : le regime « effet pose
   ET portee non observable » est VIDE dans la population ;
2. **gate `Attackable`** du swap (`UnitsWithoutTrait(0x1b Steppable)`) — **27** des 81 portent
   `Steppable`, dont `genesSmnDecoy`, le seul porteur amenable du montage ;
3. **fenetre atomique** — `AddEffect` et `RemoveEffect` vivent dans la MEME chaine `op_BitwiseAnd` :
   aucun oracle synchrone (`abilityReason`) ne peut observer l'effet entre les deux.

⚠ **Reserve** : l'UNICITE du poseur n'est PAS etablie. L'index de recherche litterale de ghidra est
demontre incomplet ici — interroge sur `0x529` il rend `GetRange` (le LECTEUR) et RATE
`GetTriggerAttackBehaviour`, pourtant decompile. L'argument porte sur le poseur LU.

Les deux clamps sont **structurellement identiques** (meme `Math.Min(1, v)`, meme `onlyAdjacent = 1`,
meme bloc), donc confronter `(c)` confronte la lecture partagee — mais cela ne vaut pas mesure de
`(b)`, et on ne l'ecrit pas comme telle.

### 9.5 Residu ouvert par cette tranche

* ~~**`#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1`**~~ — **FERME (2026-08-15) : la valeur n'est pas
  « non observable », LE CANAL EXISTAIT.** La docstring du port declarait `StatType.Range` (2) hors
  du catalogue de `combatSnapshot` : **perime**. Le RPC publie `stats.range`, et son catalogue
  `statTypes` l'apparie explicitement a l'index **2** — verifie a chaque passe, sans quoi on
  mesurerait une cle homonyme.
  `get_range` lit donc desormais `GetStat(caster, StatType.Range = 2)` dans la branche
  `!HasAnyWeapon`, **des que le `StatsComponent` est la** ; sans canal (face DECISION) il rend
  toujours `None`. L'ecart PERMISSIF est ferme : hors `only_adjacent`, le natif refusait TOUTE
  cible (`d > 0`) la ou le port desarmait le gate.
  **Ce qui rend le correctif independant de la valeur** : le port LIT la stat, il ne la suppose pas
  nulle. Si un build lui donnait 3, le port rendrait 3. La « generalisation aux 81 unites » que ce
  residu exigeait cesse donc d'etre une CONDITION du fix — elle reste une mesure, faite par etage :
  **CATALOGUE** `UnitConfiguration.Range` = **175/175 a 0** ; **MODIFICATION** aucun champ
  `statType`/`stat` du gameconfig ne nomme `range` (seules valeurs : `hp`, `dmg`, `fixedArmor`) ;
  **RESOLU** 24 observations, 12 unites distinctes dont **8 SANS ARME** (les 8 MoW du pool, contre
  **une** seule unite dans la mesure d'origine), toutes a `0`, `statDelta` vide.
  ⚠ `engine.runner.operations.triggers.base._max_attack_range` garde son arbitrage (substitution de
  **1** quand `unit_weapon_range` rend `None`) : un `0` y fermerait l'overwatch d'une MoW. Le mirror
  est pose chez `get_range`, PAS dans le helper partage, precisement pour ne pas le deplacer sous
  les pieds d'un consommateur hors perimetre.

## 10. `-r3` — l'ORDRE des deux tests de `GetTilesInRange`

`GetTilesInRange` teste `(int)range == 0` **AVANT** `OnlyAdjacent` (cascade relue a l'octet en §3) et
rend alors `casterTiles` (rayon 0), pas les adjacentes (rayon 1). `tiles_in_range_reach` testait dans
l'autre ordre — corrige.

**MIRROR STRUCTUREL, non confronte live** (`probe_419r1tr14r5r2r1r2r1r1r3_tiles_in_range_order.py`) :
**134** abilities a `TargetingRange` RE-lu x **683** unites = **67 895** couples resolus, dont
**8 196** a portee NULLE — et **0** couple deplace. Le gisement est vide parce qu'aucun des cinq
`TargetingRange` statiques ne combine les deux : `RANGE_SELF` (`ov = 0`) et `RANGE_FROM_CONFIG`
portent `onlyAdjacent = False`, et les deux qui l'arment (`RANGE_ADJACENT` `ov = 1`,
`RANGE_ADJACENT_IF_MELEE_CASTER` `ov = <arme> >= 1`) ont une portee non nulle.

Le cran qui peut ROUGIR est donc un `TargetingRange` **SYNTHETIQUE** : un balayage seul, sur un
gisement vide, serait un inventaire deguise en garde-fou. **CONTRE-EPREUVE JOUEE** : test d'ordre
retire (mutation verifiee au `git diff`) -> `test_portee_nulle_lemporte_sur_only_adjacent` rougit
(`le port rend 1`). Port restaure, 0 diff.

**NON traite, et nomme** : le natif teste aussi `(int)range < 0` (-> set VIDE) **avant**
`UseWholeBoard`, et la branche `== 0` a un sous-gate (bit 15 de `rules` : `casterTiles` ou VIDE).
Le port ne modelise ni l'un ni l'autre — hors mandat de cette tranche, et sans porteur connu
(`ov < 0` exigerait un `override_range`/`config.range` negatif).
