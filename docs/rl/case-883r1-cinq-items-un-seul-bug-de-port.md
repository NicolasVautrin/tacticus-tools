# #883-r1 — Les rouges restants de `master` : deux bugs de port, un outil aveugle, un cliquet non entretenu, un test périmé

Suite directe de [`case-883`](case-883-quatre-rouges-de-master.md), même méthode : **avant tout
correctif, établir ce que chaque rouge ACCUSE**. Sur cinq items, deux seulement accusaient le port —
et l'un des deux était une régression de moins de six heures.

| Item | Verdict | Ce qui était en cause |
|---|---|---|
| `test_ctx_traits_substrat_ventilation` | **CLIQUET NON ENTRETENU** | 3 sites neufs + 2 entrées orphelines, apportés par #585 et #564 |
| `test_287r4r1_dynamic_target_rules` | **PÉRIMÉ** | le test citait un id que #577 a fait migrer de canal |
| `test_366_r1_bcpatch_port_blindspot` | **ACCUSE L'OUTIL** | le recenseur AST était aveugle à l'alias d'import |
| `test_ability_hits_channel_live::test_frenzied_firing_*` | **RÉEL** | `decisionView.units[].feet` ouvert le jour même, lecteurs non adaptés |
| `#883-r1` — `get_health_to_lose` | **RÉEL** | `// 100` là où le call-site natif passe `roundingRule: 0` |

---

## 1. `ctx.traits` — le cliquet faisait son travail, personne ne l'entretenait

`test_la_table_ventile_exactement_l_inventaire` exige la **coïncidence exacte** entre l'inventaire
AST des lectures/écritures de `traits` et la table de ventilation. Elle avait dérivé **des deux
côtés**, et le second écart était **masqué** par le premier (l'assertion `manquantes` précède
l'assertion `orphelines`) :

* **3 sites NEUFS**, dont aucun n'était ventilé par la tranche qui l'avait créé :
  * `runner/operations/traits.py::_traits_of` (`getattr(ctx)`, R) — #585, PR #863 ;
  * `runner/operations/traits.py::execute` (`ctx.traits`, W) — la même, et la clé est **partagée**
    par `AddTraitOperation` et `RemoveTraitOperation` (les deux méthodes s'appellent `execute`) ;
  * `runner/operations/resurrect.py::tiles_are_occupied` (`getattr(sc.ctx)`, R) — #564, PR #857.
* **2 entrées ORPHELINES** : `runner/abilities/behaviours/grants.py::execute`, dans ses deux rôles.
  La feuille DSL `AddTrait` n'écrit plus rien elle-même — elle **délègue** au foyer
  `AddTraitOperation.execute`, que le natif atteint aussi par `<Effect>.ApplyInternal`. C'est un
  **changement d'étage**, le troisième que la table enregistre (après #498-r3 et #448-…-r2-r2).

### Les verdicts, lus au site

`_traits_of` sort par `return None, None` dès que le `StatsComponent` manque, **deux lignes avant**
la lecture → `INERTE-AMONT`. Convertir ce site au foyer serait une **régression** : le foyer rendrait
le kit gameconfig d'un cadavre, or ces deux Operations **mutent** l'ensemble — elles écriraient sur
un substrat fabriqué. `tiles_are_occupied` porte le gate `uc is None or not uc.alive -> continue` en
tête de boucle, exactement comme `movement.py::_kill_steppable_units` → `INERTE-VIVANT` (et un
cadavre n'occupe rien : `KillUnitOperation` → `RemoveUnitFromTiles` vide le `TileContentComponent`).

## 2. `#287-r4-r1` — le test avait raison le jour où il a été écrit

Le test construisait `UnportedAbilityTargeting(1005 AdaptiveStrategy)` et exigeait
`TargetMatchesDynamicRule`. Il rendait `0`, **et `0` était la bonne réponse** : #577 (`4c5e4c88`,
2026-08-08) a **retiré** l'entrée `1005` de `DYNAMIC_TARGET_RULE_UNPORTED` parce que
`necrons.AdaptiveStrategyAbility` **surcharge** désormais `get_dynamic_invalid_target_reason`. Le
test datait du 2026-08-06 : son régime a changé sous lui en deux jours.

**Ce qui est livré n'est pas un re-ciblage cosmétique** :

* l'id testé est **dérivé de la table** (et le test rougit si la table est VIDE — ce serait alors du
  dead code à retirer, pas un vert) ;
* un test **neuf** garde la migration elle-même : les deux faces doivent bouger **ensemble** —
  l'entrée retirée **et** la surcharge présente. Sans lui, retirer la surcharge sans remettre
  l'entrée rendrait `1005` **permissif en silence**, la dégradation exacte de #287-r4-r1 ;
* `ForwardObservers` (1185) entre dans `P.CAS`. C'est la **seule entrée restante** de la table :
  les cinq autres bras étaient tous en surcharge, donc les étages BASCULE et MUTANTS ne mesuraient
  plus que **l'un des deux canaux**, et la table pouvait se vider sans qu'aucune bascule ne tombe.

Contre-épreuve : trois mutants (porteur qui ne consulte plus la table ; `1005` remis en table alors
qu'il surcharge ; surcharge retirée et table vide) — **3/3 MORDENT**.

## 3. `#366-r1` — un faux NÉGATIF que seule la seconde source voyait

Le recenseur AST identifie une lecture par le **nom écrit au call-site**. Or
`runner/operations/triggers/effect_triggers.py` écrit
`from ....entities.effects.magnitude import ability_var as _ability_var` — **l'unique alias du
corpus, sur 82 imports du lecteur** — et lit `("BloodChalice", "hpToHeal")`. Le couple était donc
**invisible** du recensement, et seule la contre-épreuve au grep le montrait : exactement le rôle
pour lequel elle a été écrite.

Le sens de l'erreur compte : c'est un **faux négatif**. Un patch de seed BC sur cette variable aurait
désynchronisé les deux faces **sans rougir**.

Réparé **des deux côtés** — lecture *et* patch : un
`from catalog_inject import patch_ability_variables as _pav` rendrait un patch invisible, et le
corpus n'en porte aucun aujourd'hui, ce qui est précisément le moment de couvrir la forme. Un bras
de self-test **fabriqué** fige la réparation : le contrôle « seconde source » ne la tenait que par un
site **accidentel** du corpus, qui peut disparaître.

**Limite assumée, et elle vaut pour les deux sources** : un alias posé par *affectation*
(`av = ability_var` puis `av("X","Y")`) échappe au grep comme à l'AST. Le corpus n'en porte aucun.

## 4. `feet` — une régression de six heures, sur trois lecteurs dont un seul normalisait

`a22c65ae` (#419-r1-tr10-r2, 2026-08-10 16:08) a ouvert le capteur multi-tuiles côté DÉCISION :
`projection.ts::readEntityFeet` = `IdunBattle.Entities.EntityExtensions$$GetTiles`, publié sous
`decisionView.units[].feet` **en dicts `{"col","row"}`** (la forme de `readTileCoord`). La face
COMBAT, elle, porte des **couples** `(col,row)`.

Trois lecteurs consomment cette clé ; **un seul** normalisait :

| lecteur | avant |
|---|---|
| `playbook/adjacency.py::iterate_tiles` | `_as_pos` — les deux formes, OK |
| `dsl/base.py::_feet` | `(int(f[0]), int(f[1]))` → `KeyError: 0` |
| `entities/selectors/tiles.py` | **recopie locale** de la règle → `KeyError: 0` |

Le second est le foyer que **tous** les sélecteurs DSL traversent (`accessors.py::TargetTile` →
`_feet(ctx.target)`), d'où deux rouges live immédiats sur FrenziedFiring. Le message du commit dit
« canal muet → repli sur la MainTile, c.-à-d. le comportement d'avant, EXACTEMENT » : vrai du canal
**muet**, et le canal ne l'est pas.

La normalisation est posée **au foyer**, et `tiles.py` cesse de recopier la règle. Effet de bord
**voulu** : la face DÉCISION lit désormais l'empreinte **réelle** là où elle retombait sur
`decisionView.units[].pos` — qui, pour une multi-hex, est le **dernier pied projeté**, pas la main
tile (cf. `runner/snapshot.py::_load_feet`). Le repli n'était donc pas seulement incomplet, il était
**faux d'un à deux hexes**.

## 5. `#883-r1` — `roundingRule: 0`, lu au 4ᵉ argument

`IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose` :

```
amount     = DSLFormulas.StatAmount(owner@+0x48, 5 = Health, 2)
percentage = DSLFormulas.ConfigConst(0x4f = AbilityConstantType.healthPct, this+0x60)
return       DSLFormulas.PercentageOf(amount, percentage, roundingRule: 0)
```

`IdunBattle.DSL.AAmountFormula$$RoundFix64Result` ventile `1` = `Fix64.Ceiling`, `2` = `Fix64.Floor`,
**tout le reste** = `Fix64.Round` — dont le corps (`FixMath.NET.Fix64$$Round`, `midpointRounding == 0`)
rend la partie entière si la fraction est `< 0.5`, `+1` si `> 0.5`, et **le pair** sur `0x80000000`
exact. Le port écrivait `(max_hp * pct) // 100`, un FLOOR : faux de 1 dès que la fraction atteint
0,5. Sur `healthPct = 15`, la divergence tombe quand `3·max_hp mod 20 >= 10` — `max_hp = 1237` →
natif **186**, ancien port **185**.

Les deux arrondis intermédiaires de `PercentageOf$$CalculateInternal` (le motif
`x/100 * 100 → Round → /100`, deux fois) sont **neutres** pour des opérandes entières : seul
l'arrondi final est observable.

### Le témoin, et pourquoi sa discriminance est ASSERTIONNÉE

C'est la leçon que #883 avait déjà payée : son floor tenait parce que la mesure qui l'attestait
(`probe_45f --case crit`, `cd = 700` → `175.0`) **n'avait aucune partie fractionnaire**. Le test
livré n'assertionne donc pas seulement la valeur : il exige que **son propre jeu de témoins sépare
les trois règles**, contre floor *et* contre half-up.

| `max_hp` | natif (half-even) | floor | half-up |
|---|---|---|---|
| 1000 | 150 | 150 | 150 |
| 1237 | **186** | 185 | 186 |
| 10 | **2** | 1 | 2 |
| 30 | **4** | 4 | **5** |
| 50 | **8** | 7 | 8 |
| 70 | **10** | 10 | **11** |

Le couple `(30, 70)` est le seul qui sépare **half-even de half-up** — sans lui, un port en
demi-vers-le-haut passerait pour juste. Contre-épreuve : trois mutants (floor d'avant, half-up,
valeur juste mais foyer contourné) — **3/3 MORDENT**.

### Périmètre refermé

Balayage `engine/**` après correctif : **0** `// 100` exécutable non confronté. Les quatre autres
occurrences sont de la prose (`formulas.py`, `stats.py`) ou des `Ceiling` explicitement documentés
(`status.py`, `displace.py`, `deathguard.py`, cohérents avec `roundingRule = 1`).

Deux formes voisines ont été lues plutôt que supposées :

* `runner/abilities/behaviours/stats.py::SetHealth` porte **déjà** son `pct_rounding` lu au
  call-site (#573) et passe par `Fraction` — les deux `// 100` du fichier sont des docstrings ;
* `services/trait_damage_limits.py:482` **n'est pas un `PercentageOf`** :
  `DamagePrediction$$ApplyTraitDamageLimitsToDamage` y calcule
  `Math.Max(currentHealth - (int)((float)(maxHealth * const) / 100.0), 0)` — un **cast d'un float**,
  donc une troncature vers zéro, qu'aucun `roundingRule` ne gouverne. Le `math.floor(... / 100.0)`
  du port lui est identique sur des valeurs positives.

---

## Validation

* **Offline** : `test_ctx_traits_substrat_ventilation` 14 ✓ · `test_287r4r1` 18 ✓ (dont 2 neufs) ·
  `test_366_r1_bcpatch` 14 ✓ + `probe_366_r1 --self-test` rc 0 (10 bras, dont un neuf) ·
  `test_883r1_health_to_lose_rounding` 13 ✓ · `test_419r1tr10r2_feet_deux_formes` 7 ✓.
* **Non-régression offline** : 153 tests des familles empreinte/adjacence
  (`#433-r3`, `#433-r4`, `#459`, `#515`, `multihex_substrate`, `ramming_speed`).
* **Live** : `test_ability_hits_channel_live` 5 ✓ (dont les 2 rouges) ·
  `test_433_r3_r1a_occupancy_live` 10 ✓ · `test_459_tile_accessors_live` 13 ✓.
* **Mutants** : 8 sur 8 mordent (3 pour #287-r4-r1, 3 pour #883-r1, 2 pour `feet`).
* **Cliquets** : `probe_486r15` rc 0 · `probe_433_r1` rc 0 · `probe_468` PASS ·
  `probe_547_ledger_sans_verdict_non_vert` PASS.

### Ce qui n'est PAS couvert

* **Empreinte #457 des deux fichiers de test neufs : NON gravée.** `--measure-missing` écrit dans
  `scripts/ratchets-457-footprints.json`, foyer d'une tranche en vol (#463-r1). Conséquence bornée
  et sans risque de faux vert : les deux déclencheurs portent `chemins: ()` + `toujours: True`
  (périmètre vide **mesuré** par `probe_486r15 --proposer`), donc les fichiers se rejouent
  **toujours** — aucun chemin ne peut leur manquer. Ils apparaîtront comme « offline non mesurés »
  dans `loop_status` jusqu'à la prochaine passe `--measure-missing`.
* Le fix `feet` n'a pas été confronté **live sur une unité multi-hex côté DÉCISION** : la
  discriminance de l'empreinte y est gardée offline (un ennemi adjacent au seul pied `(3,4)`, hors
  du `pos` publié, est sélectionné après correctif et invisible avant). Les trois fichiers live
  rejoués exercent l'empreinte côté COMBAT.
* `get_health_to_lose` n'est pas confronté à un oracle **live** : le verdict repose sur le
  décompilé, qui est la vérité de la doctrine. Le porteur (`DakkaDakkaDakka`) émet un
  `ProbableDamageEvent` SELF dont l'utilité est négée ; une confrontation par `aiPlaybookPredict`
  exigerait un régime où `max_hp` porte une fraction — atteignable par `--hp-target`, non joué ici.
