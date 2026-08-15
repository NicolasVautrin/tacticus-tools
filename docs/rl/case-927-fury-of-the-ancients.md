# #927 — `FuryOfTheAncients` (1247, `bloodMephiston`) : la face COMBAT

`kit-coverage` annonçait `manque 1`. Au décompilé il y a **trois faces**, et une seule manquait.

| face | artefact natif | verdict |
|---|---|---|
| DÉCISION / mouvement | `FuryOfTheAncientsPlaybook.<CalculateMovementUtilityInStepsInternal>d__1$$MoveNext` | **déjà portée** (#32, `engine/playbook/fury_of_the_ancients.py`) |
| DÉCISION / attaque | aucune surcharge — le corps de base rend `yield Fix64.op_Implicit(0)` dès qu'`IsRegularAttack` est faux (#375) | **DEAD**, gravé (`test_927_fury_offline` étape 5) |
| COMBAT | `FuryOfTheAncientsAbility$$CreateTrigger` + `$$CreateBehaviour` | **portée ici** |

## Ce que le natif dit et qu'aucune table ne disait

**L'effet 1320 n'est PAS un `DeathwingEffect`.** Le pseudo-C de `FuryOfTheAncientsEffect$$.ctor`
appelle un corps que ghidra nomme `DeathwingEffect$$.ctor` — laquelle porte quatre overrides de
DÉGÂT. `frida/classes.tsv` tranche : le parent est `IdunBattle.Entities.Effects.HealBlockingEffect`
(corps ICF-fondu, trois `.ctor` de même forme). Suivre le pseudo-C aurait donné un effet de dégât
là où l'i2 annonce « Can neither get their Health restored nor be revived ».

**Le choix de cible est un TRI, pas un tirage** — contrairement à ses deux voisins d'`On(0x1c)`
(`FabricatorClawArray`, `ChampionOfTheFeast`), qui piquent par `PickRandomly` :
`Cache(First(SortByFormula(pool, Sum(pred(ActiveTarget), pred(second(ActiveTarget))), DESC), 1))`.

**Mais le tri consomme le PRNG.** `DamagePredictionFormula$$Calculate` évalue son `damage`
(`MinMaxDamage` = `RandomAmount`) par le slot **1**, pas le slot 4 : **2 tirages par candidat**, et
**avant** ses trois null-guards — donc même quand le second maillon n'existe pas.

**`SortByFormula` lie `ActiveTarget@+0x20`, pas `subject`.** Lu dans
`SortByFormulaSelector.<>c__DisplayClass4_0$$<Select>b__0` (`closure+0x30 = s`, soit
`<copie d'AbilityEntities>+0x20`). Le port l'avait déduit « par analogie avec Filter ».

**`GetSecondTargetSelector` prend la CIBLE pour référent** : `Damageable(Friends(of = lastTarget,
AdjacentUnits(lastTarget), 3))` — les alliés de la cible, c.-à-d. les autres ennemis du caster.

## Le conflit d'offset, non résolu et assumé (résidu #927-r1)

Deux call-sites lisent `<DSLFormulas + 0x20>` et leurs comportements **mesurés** sont incompatibles :

* `CreateBehaviour` en fait `maxTargets` → mesure : **1** (2 cibles frappées sur 3 montages ; le
  mutant à 0 mord partout) ;
* `DSLTriggers$$AmountIsZero(x)` en fait le `minAmount` de
  `AmountIsGreaterAbilityTrigger$$ShouldTrigger`, qui rend `minAmount < count(x)` → si `minAmount`
  valait 1, le gate serait `count > 1`. Mesure `probe_927 --solo` (tuile adjacente à **exactement
  un** ennemi) : **le natif frappe**. Donc `minAmount = 0`.

Le port suit la mesure des deux côtés. Ce qu'il faut relire, c'est le `.ctor` de `DSLFormulas`, pas
les call-sites — le port de `fabricator_claw_array.py` (`count <= 0`) est juste côté gate.

## Validation

`probe_927_fury_of_the_ancients.py`, trois montages, accord **bit-exact** sur trois observables
(cibles de la chaîne, PV, porteurs de l'effet 1320) :

| montage | adjacents | natif | port |
|---|---|---|---|
| MC1_67 / 777 | 2 | −958 (sq 77), −1834 (sq 81) | identique |
| MC1_63 / 38704 | 2 | −826 (sq 49), −805 (sq 51) | identique |
| MC1_67 / 777 `--solo` | **1** | −903 (sq 77), −1672 (sq 81) | identique |

Sept mutants, chacun mordant sur l'**union** des régimes (`--mutants`). Deux sont inertes sur un
régime et mordent sur l'autre, et la cause est **mesurée** : `nrOfHits = 1` est inerte sur MC1_63
parce que `AttackHitsWithModifiers` y rabat déjà les coups à 1 (`hits demandés=2 → coups JOUÉS=1`,
des deux côtés) ; `SortByFormula lie subject seul` et `null-guard avant le tirage` sont inertes sur
MC1_67, où l'argmax du tri coïncide avec le premier de l'ordre source.

⚠ **Une exception du harnais n'est pas une morsure.** Un `NameError` d'instrumentation a fait passer
7/7 mutants pendant un tour, dont les deux qui étaient inertes juste avant. `_measure` rend
désormais `mord = None` = verdict **indisponible**, et le test le refuse.

## Ce qui n'est PAS couvert

* `MischiefMakers` (1469), second porteur de `HealBlockingEffect`, n'est pas inscrit au registre
  d'effets : un porteur de 1469 reste soignable côté port (dégradation **permissive**, identique à
  l'état antérieur, bornée à cet id).
* ~~`Cache(matchAbilityEntities = 1)` : le nœud porté n'implémente que la branche slot unique.~~
  **PORTÉ** (#927-r3), puis **CONFRONTÉ SITE PAR SITE** (#927-r4) : les **44** call-sites Python du
  nœud `Cache` sont appariés un à un au littéral que pousse *leur* call-site natif — **44/44
  concordants, 0 divergent** — et un cliquet les re-confronte à la table versionnée
  `data/symbols/<build>/metadata/dsl_cache_call_sites.tsv`.
  ⚠ **Ce call-site-ci était le trou du census de #927-r3** : `...FuryOfTheAncientsAbility$$GetTarget`
  finit par `mov r8b, 1 ; jmp <DSLSelectors$$Cache>` — un **TAIL CALL**, que le scan (qui ne
  cherchait que l'opcode `call`) ne voyait pas. Le census annonçait donc **119** call-sites
  ; il y en a **121** (114 DICT / 7 SLOT). Contre-contrôle Ghidra : 125 xrefs = 121
  `UNCONDITIONAL_CALL` + 4 `DATA`. Ironie utile : c'est précisément le call-site que #927 déclare
  avoir ajouté qui manquait à sa propre mesure.
* La **clé** du mode DICT ne couvre que **6** des **32** champs d'`AbilityEntities` (#927-r5 —
  l'énoncé disait 9 sur 33 : le compte des champs venait d'un dump Il2CppDumper d'un *autre* build,
  et trois des neuf slots ne sont pas des champs mais deux propriétés dérivées plus un doublon).
  La faute **sous-distingue** — HIT là où le natif re-calcule, jamais l'inverse — et n'est pas
  atteinte : les `Cache` portés vivent au-dessus de la boucle de coups.
* `attackerPosition = Tiles(Caster)` et `ability = <DSLSelectors+0x88>` ne sont pas matérialisés :
  le foyer de prédiction porté lit la position courante et dérive les gates du profil — mêmes
  valeurs par un autre chemin.
* Le rabattement des coups par `AttackHitsWithModifiers` est **reproduit** mais sa cause n'a pas été
  attribuée (étage partagé, déjà validé ailleurs).
