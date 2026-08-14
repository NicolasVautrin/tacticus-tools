# #999-r3 — le canal `rarity` côté PORT : deux nœuds, un foyer, et le régime qui sépare

Le capteur #1039 publiait `combatSnapshot.units[].rarity` ; **rien ne le lisait**. Tout gate
`HasRarity` / `UnitsWithRarity` restait inévaluable, et le rabattre sur « toujours vrai » aurait été
une dégradation **permissive** silencieuse. Cette tranche le consomme, porte les deux nœuds, et
livre le **montage qui sépare** — sans lequel aucune validation de rareté ne prouve quoi que ce soit.

## 1. Ce que le natif lit (relu au décompilé, build `rnca9r7q6c`)

| symbole | corps |
|---|---|
| `IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger` | `e = sel.Select(entities, 8)` ; `e == null → 0` ; `GetBaseUnitComponent(e)->[+0x74] == this->[+0x18]` |
| `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` | `src = inner.Select(entities, this->[+0x24])` puis garde `GetBaseUnitComponent(x)->[+0x74] == this->[+0x20]` |
| `IdunBattleLogic.Entities.DSLTriggers$$HasRarity(actor, rarity)` | `<ctor>(actor, rarity, 0)` → champs `+0x10` / `+0x18` |
| `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithRarity(units, rarity, unitSelectionType)` | `UnitsWithRaritySelector..ctor(state, units, rarity, selType)` → `+0x18` / `+0x20` / `+0x24` |

⚠ **`UnitsWithRaritySelector` ne filtre PAS par `UnitSelectionType` élément par élément** : il ne
fait qu'en **transmettre** la valeur au sélecteur intérieur (`inner.Select(entities, selType)`), sa
propre boucle ne comparant que la rareté. Le port n'a donc **pas** de paramètre `selection_type`
(un paramètre inerte se recopierait en croyant filtrer) — c'est le nœud `source` qui porte le sien.
Le ctor du trigger porte le nom ghidra `UnityEngine.Timeline.SupportsChildTracksAttribute$$.ctor`
(corps dédupliqué) : structure lue, jamais le nom.

## 2. Le port — un foyer, deux nœuds, tri-état strict

- `engine/entities/rarity.py` : `measured_rarity(row)` (tri-état ; un **ordinal hors mirror LÈVE**
  au lieu de rendre `None`, sinon tous les gates basculeraient en restrictif en silence) et
  `assert_rarity_channel(snapshot)`, qui confronte `rarityEnum` au nom **PLEIN** `idun.meta.Rarity`.
- `UnitContext.rarity`, seedé par le **foyer unique** `from_snapshot` — donc les DEUX faces
  (COMBAT via `snapshot._load_stats_and_effects` / `_load_machine_stats`, DÉCISION via
  `playbook.scene._hydrate_static_unit`). Le garde `assert_rarity_channel` est posé une fois par
  face, **avant** tout seed.
- `entities/triggers.py::HasRarity`, `entities/selectors/units.py::UnitsWithRarity`, et la clé
  `rarity` du dict d'unité DSL (`entities_from_state`) — `None` sur une entité-TUILE, comme
  `_traits` y est vide.

**Dégradation NOMMÉE** : rareté non mesurée ⇒ les deux nœuds rendent **FAUX / excluent**. C'est le
côté restrictif, et il est choisi : ces nœuds n'apparaissent qu'en conjoint d'un bonus (1442, 1446,
1448, 1449, 1494, 1548) ou d'un gate de trigger, donc un FAUX laisse l'état inchangé là où un VRAI
inventé accorderait un bonus que le natif refuse. Le natif, lui, **lève** quand le composant manque :
il ne connaît pas le cas « pas mesuré », qui n'existe que côté port.

## 3. Le régime SÉPARANT — l'unité de valeur de la tranche

`rl_duel build` impose `targetRarity = 5` : **par défaut, les dix unités rendent `5`** et un port
sans gate est d'accord avec le natif partout. Sortie : `--unit-stat "<vis>:Rarity=N"`, écrit APRÈS
la normalisation.

`scripts/python/probe_999r3_regime_separant_rarete.py` + fixture `rarity_separating_case`
(`tests/engine/conftest.py`). Deux bras, et le couple seul vaut mesure :

| bras | capteur | port | `UnitsWithRarity(Mythic)` | `UnitsWithRarity(Epic)` |
|---|---|---|---|---|
| dégénéré (témoin) | `[5]`, 10/10 lignes | `[5]` | toutes | `[]` |
| séparant (`orksKillaKan → Epic`) | `[3, 5]`, 10/10 | `[3, 5]` | 8 | les 2 KillaKan |
| séparant `+ --p-mow adeptExorcist` | `[3, 5]`, **11/11** | `[3, 5]` | 9, **MoW incluse** | les 2 KillaKan |

Le probe **refuse** de rendre un bras séparant qui ne sépare pas, et refuse un bras dégénéré qui
sépare (la prémisse `targetRarity = 5` ne tiendrait plus). Le bras MoW n'est pas un ornement :
`readUnitConfig` filtre sur la classe `UnitComponent` et est **aveugle aux Machines** — c'est
précisément ce qui a fait choisir `GetBaseUnitComponent` (`case-1039` §4) ; un montage sans MoW
laisserait non couvert ce qui a motivé le choix. Mesuré : la MoW (entité 87) rend `rarity = 5`
pendant que sa ligne `by_visual` reste `None`.

## 4. Les gardes, et ce qu'elles ont vu ROUGE

`tests/engine/test_999r3_canal_rarete_offline.py` (7 étages, 12 tests) et
`tests/engine/runner/test_999r3_canal_rarete_live.py` (6 tests, tous tirés du bras séparant).

**Sept mutations du code de PRODUCTION, sept rouges** : `measured_rarity` rendant `Rarity.Common`
au lieu de `None` (2 rouges) · `assert_rarity_channel` acceptant n'importe quel nom · `HasRarity`
permissif sur une rareté non mesurée · `UnitsWithRarity` gardant les non mesurées · `_unit_dict`
cessant de publier la clé · mirror renuméroté `Mythic = 6` (5 rouges) · `from_snapshot` ne lisant
plus la rareté.

Deux crans que le reste n'aurait pas attrapés : l'étage 6 fige les **ordinaux écrits au SITE**
(`probe_313` compare le mirror au *build*, donc il redevient vert dès qu'on régénère le mirror après
un renumérotage), et l'étage 7 **re-dérive** d'`enums.tsv` les enums homonymes en assertionnant son
propre non-vide — sans quoi « aucun homonyme ne diffère » serait vert sur un ensemble vide.
⚠ Son premier jet a été rouge par **fork du parsing** d'`enums.tsv` : un lecteur faux rend un dict
vide, donc une assertion « absent du build » qui accuse le build au lieu du lecteur. Il passe
désormais par le foyer `probe_1039_canal_rarete.lire_enums`.

## 5. Ce qui N'EST PAS couvert

- **Aucun des six effets de rareté n'est porté** (1442, 1446, 1448, 1449, 1494, 1548). Leur blocage
  n'est plus le capteur : il manque le **threading d'`att_rarity` / `tgt_rarity`** dans les ctx des
  agrégateurs d'aura (`aura_attack_damage_bonus_from_allies`,
  `aura_defense_damage_malus_from_units`), foyer partagé → `#999-r3-r1`.
- **La rareté d'une unité MORTE ou en FUITE** : le capteur la publie sous `unitsNotAlive[].rarity`,
  aucun `UnitContext` n'est bâti depuis ces lignes → tout `UnitsWithRarity(AllDeadUnits(…))` les
  exclut → `#999-r3-r2`.
- **Les faces DÉCISION** `MastersOfManoeuvre` (`#999-r1`, `#433-r4-r3-r1-r1`) et
  `CabalOfSorcersPlaybook` (`#1036-r3`) : le canal les débloque, elles ne sont pas portées ici.
- **Le seul régime séparant joué** est `(MC1_67, 777, orksKillaKan → Epic)`. Les six raretés ne sont
  pas balayées ; `Rarity.Common` n'a jamais été monté en bataille.
