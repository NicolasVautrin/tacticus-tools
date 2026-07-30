# Case #48 — `UnitsDirectlyBehind` : comparateur `>` STRICT (AmountIsGreater), pas `>=`

## Verdict

**La suspicion initiale est CONFIRMEE.** Le selecteur `UnitsDirectlyBehind` (splash de PlasmaCannon /
darkaTerminator, `PickRandomly(UnitsDirectlyBehind, 2)`) utilisait offline `>=` la ou le natif utilise
`>` STRICT. Consequence : l'offline SUR-INCLUAIT les unites LATERALES a distance EGALE (candidat pile a
la meme distance du caster que la cible). Fix : `>=` -> `>` dans `engine/entities/selectors.py`.

## Le piege : gshared ctor FOLDE, mislabele par ghidra

Le decompile de `UnitsDirectlyBehind @180dff5e0` se termine par un appel dont ghidra affiche le nom
`AmountIsEqualOrGreaterAbilityTrigger___ctor(this, dist(caster,cand), dist(caster,target))`. **Ce nom
est FAUX** : ghidra FOLD les ctors dont le corps est identique (ceux qui stockent 2 champs : `+0x10/+0x18`
et `+0x20`), et attribue au corps partage UN seul nom de classe. Les triggers `AmountIsEqualOrGreater`,
`AmountIsGreater`, `AmountIsEqual`... partagent ce ctor -> le nom affiche ne dit rien de la vraie classe.

**Ancre fiable = le SINGLETON de classe (Il2CppClass*), pas le nom du ctor.** Dans `UnitsDirectlyBehind`,
le comparateur est instancie via `thunk_FUN_18021f8f0(DAT_1832482b0)`. Or :

- `DAT_1832482b0` est le singleton construit par **`DSLFactory.AmountIsGreater @180de89d0`** (et
  `AmountIsGreaterThanZero`) -> la classe reelle est **`AmountIsGreaterAbilityTrigger`** = `>` STRICT.
- `DAT_18324e3c0` (la formule des deux operandes) est le singleton construit par
  **`DSLFactory.MinDistance @180df6820`** -> **`MinDistanceFormula.Calculate @180f1d3b0`** = min sur
  toutes les paires de `PositionComponent.Distance` (distance de tuile HEX standard, `System.Math.Min` ;
  PAS pathfinding, PAS projection). Unites mono-tuile -> = `hexgeo.distance`.

(Meme piege sur les selecteurs internes : `SortReverseSelector.Select @180ef39a0` = `Reverse + ToList`,
et les autres ctors `HasUsedActiveAbilityThisTurnTrigger___ctor` sont eux aussi des corps foldes
mislabeles -- ne jamais se fier au nom, lire le singleton/la factory.)

**Ce piege a RECIDIVE DEUX FOIS depuis, dont une fois dans l'AUTRE SENS** -- le proprietaire que la
table donne au corps partage n'a rien de stable, il change de build en build :

- `MurderousSwing` (**#108**) : ctor etiquete `AmountIsEqualOrGreater...`, classe reelle
  `AmountIsGreater...` (meme sens qu'ici) ;
- `IsInUnitContagionsOfNurgleAura` (**#293**, `case-224-is-in-contagions-of-nurgle-range.md` §2.1) :
  ctor etiquete **`AmountIsGreater...`**, classe reelle **`AmountIsEqualOrGreater...`**. Le sens
  inverse, donc, et il a coute un aller-retour complet (une lecture STRICT publiee, puis renversee
  par une mesure live sans que l'etage fautif soit localise).

⇒ le controle est desormais MECANISABLE et re-derivable, sans ghidra :
`python scripts/python/probe_293_aura_predicate_comparator.py --inventory` lit le pointeur de classe
directement dans les octets de `GameAssembly.dll` (operandes RIP-relatives), corrobore par l'encodage
`setg` / `setge` des deux `ShouldTrigger`, et rend l'inventaire de **tous** les sites d'instanciation
par famille (STRICT / INCLUSIF). A passer avant de conclure sur un comparateur de cette famille.

## Preuve du comparateur `>` (ShouldTrigger des deux classes soeurs)

- `AmountIsGreaterAbilityTrigger$$ShouldTrigger @180ee11f0`
  -> `return iVar16 < iVar15;`  ==  `amount > threshold`  ==  **`>` STRICT**  <- utilisee ici
- `AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger @180ee0e00`
  -> `return iVar16 <= iVar15;` ==  `amount >= threshold` ==  `>=`  (classe voisine, NON utilisee)

`amount` = 1er arg ctor (`+0x10`/`+0x18`) = `MinDistance(caster, candidate)` ; `threshold` = 2e arg ctor
(`+0x20`) = `MinDistance(caster, target)`. Donc le predicat = `dist(caster, candidate) > dist(caster,
target)` (`>` STRICT).

## Construction native (mirror 1:1)

```
ring   = SurroundingTiles(target, 1, 1) - Tiles(target)      # anneau R1 de la CIBLE
cands  = Enemies(caster, Units(ring))                        # ennemis du caster sur l'anneau
sameEl = TilesOnSameElevationSelector(target, cands, maxDiff=1)  # meme elevation (+-1)
behind = FromTrigger(cands, AmountIsGreater(                 # `>` STRICT
             MinDistance(caster, candidate),                 # amount
             MinDistance(caster, target) ))                  # threshold
```

## Offline (corrige)

`engine/entities/selectors.py::UnitsDirectlyBehind.select` :

```python
if hexgeo.distance(cpos, p) > d_ct:   # STRICT (AmountIsGreater) -- etait `>=` (bug), corrige case #48
    out.append(u)
```

Second consommateur du meme selecteur : `engine/entities/abilities/active_ability.py::PlasmaCannonPlaybook`
(prediction des cibles secondaires, `GetValidSecondaryTargetsSelector @1811BB340`) -> le fix source-unique
corrige a la fois le runner (splash) ET le playbook (prediction).

## Table des cas frontiere (verifiee offline + live)

Geometrie hex : caster C, target T a d_ct=2 de C, candidats sur l'anneau R1 de T
(dist(T, candidate) == 1). Sur hex, dist(C, candidate) in {d_ct-1, d_ct, d_ct+1} :

| position  | delta = dist(C,cand) - d_ct | natif `>` | ancien offline `>=` (BUG) |
|-----------|-----------------------------|-----------|---------------------------|
| front     | -1 (plus pres de C)         | EXCLU     | EXCLU                     |
| lateral   |  0 (== d_ct, distance egale)| **EXCLU** | **INCLU** (sur-inclusion) |
| away      | +1 (plus loin de C)         | INCLU     | INCLU                     |

Le seul cas qui separe `>` de `>=` est le **lateral (delta 0)** : le natif l'EXCLUT.

## Confrontation LIVE (2 datapoints, mesures)

`probe_udb_case48.py` / `test_plasma_cannon_lateral_live.py`, PlasmaCannon (darkaTerminator), board plat
MC1_67, lateral (delta 0) + away (delta +1) sur l'anneau, reste parque loin :

- run 1 : lateral 79 d(caster)=2==d_ct -> EXCLU du splash ; away 81 d(caster)=3 -> INCLU. splash={main,81}.
- run 2 (probe) : idem, distances hex LIVE mesurees (79 a d(caster)=2, d(target)=1 ; 81 a d(caster)=3,
  d(target)=1). VERDICT: lateral EXCLUDED (`>` strict). L'ancien offline `>=` incluait 79 a tort.

## Validation

- **Offline deterministe** : `tests/engine/entities/test_units_directly_behind_offline.py` (synthetique,
  hexgeo) -- front exclu, lateral (delta 0) EXCLU, away inclus ; miroir exact du `>` STRICT.
- **Live discriminant** : `tests/engine/runner/test_plasma_cannon_lateral_live.py` -- lateral EXCLU du
  splash LIVE == exclu offline.
- **Zero-reg** : `tests/engine/runner/test_plasma_cannon_live.py` (geometrie stricte d=3, delta +1, ne
  discrimine pas `>`/`>=`) reste vert ; son commentaire "exclut les lateraux a distance egale" (deja
  correct dans l'intention) reflete desormais le comportement reel du code.

## VAs citees

- `IdunBattleLogic.Entities.DSLFactory$$UnitsDirectlyBehind @180dff5e0`
- `IdunBattleLogic.Entities.DSLFactory$$AmountIsGreater @180de89d0` -> singleton `DAT_1832482b0` (`>`)
- `IdunBattleLogic.Entities.DSLFactory$$MinDistance @180df6820` -> singleton `DAT_18324e3c0` (distance)
- `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate @180f1d3b0` (min `PositionComponent.Distance`, hex)
- `AmountIsGreaterAbilityTrigger$$ShouldTrigger @180ee11f0` (`>` STRICT, `iVar16 < iVar15`)
- `AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger @180ee0e00` (`>=`, voisine non utilisee)
- `SortReverseSelector$$Select @180ef39a0` (Reverse+ToList ; ctors gshared foldes = pieges)
- Consommateurs offline : `PlasmaCannonAbility$$ExecuteBehaviour @1811f95c0` (splash runner, id 1150) +
  `PlasmaCannonPlaybook` `GetValidSecondaryTargetsSelector @1811BB340` (prediction)
