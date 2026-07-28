# case O4a — `Maybe(chance)` : un gate non déterministe consomme UN tirage, à SA place dans le flux

**Critère (binaire)** : un trigger gaté par `Maybe(chance)` consomme-t-il exactement UN tirage RNG,
au bon moment dans le flux, comme le natif ? — **OUI**, confronté live bit-exact sur le compteur de
`genrand_int32`.

---

## 1. La vérité native

### 1.a `IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger`

```
chance = <formule V @+0x20>.Calculate(entities)          // ici ConfigConst / Difference-Multiply
if (!IdunBattle.DSL.ANonDeterministicAbilityTrigger$$CanUseRandom(this))
    return 99 < chance;                                   // 0 tirage
return IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$NextBool(this@+0x18, chance);   // 1 tirage
```

Layout lu au ctor (`IdunBattle.Entities.Triggers.MaybeTrigger$$.ctor(state, random, chance)`) :
`state@+0x10`, `rng@+0x18`, `chance@+0x20`. Le RNG est un **champ de l'instance**, pas une entrée du
contexte — le port le prend au constructeur, comme le natif.

### 1.b `CanUseRandom` — quand le tirage N'A PAS lieu

```
IdunBattle.DSL.ANonDeterministicAbilityTrigger$$CanUseRandom :
    return state@+0x10.IsRandomAllowed && rng@+0x18.IsAllowed@+0x20;
```

Les deux facteurs, lus un par un :

- `IdunBattle.Core.IMatchState$$get_IsRandomAllowed` est une **implémentation d'interface par défaut**
  qui rend `!<slot 0xb>` — le state en simulation la met à faux.
- `DisallowablePseudoRNG+0x20` est le flag `IsAllowed` : posé à **1** par
  `IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$.ctor`, abaissé par
  `IdunBattleLogic.Entities.DSLFactory$$SetDisallowRandom` et relevé par
  `IdunBattleLogic.Entities.DSLFactory$$SetAllowRandom`. **Les xrefs des deux setters ne donnent qu'un
  seul call-site : `IdunBattle.AI.Playbook.BasePlaybook$$Evaluate`.** C'est aussi ce flag que
  `IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$CheckAllowed` teste pour émettre son `LogError`.

Donc **`!CanUseRandom` == on est du côté DÉCISION / PRÉDICTION**, et le natif y substitue au tirage le
prédicat déterministe `99 < chance` — vrai SSI `chance >= 100`. C'est exactement la règle déjà
ground-truthée côté formule de coups (`entities/traits/combat.py` : « `Maybe(chance)` en PRÉDICTION :
compté SSI `chance == 100` », GROUND TRUTH step-13) : ce n'était pas une convention du port, c'est
cette branche du natif.

Côté port, l'absence de PRNG (`rng is None`) **EST** cette situation : aucun flux de tirages n'est
calé, on est hors exécution de bataille. Le nœud rend donc `99 < chance` — et non plus `False`, la
dégradation d'avant, qui divergeait précisément sur les `chance >= 100`.

### 1.c L'ordre dans une conjonction

`IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger` évalue `left@+0x10`, et **n'évalue
`right@+0x18` que si le gauche est vrai**. Un `Maybe` placé à gauche d'un gate déterministe consomme
donc son tirage **même quand le gate de droite rendra le résultat inutile**.

---

## 2. Ce qui manquait (et ce qui ne manquait pas)

Le nœud `MaybeTrigger` **existait déjà** dans `engine/entities/triggers.py` — posé par `case-1203`
(`OnToxicDamageAbility`). Ce qui manquait :

| Site | État d'avant | Après |
|---|---|---|
| nœud, branche `!CanUseRandom` | `return False` (dégradation) | `return 99 < chance` (mirror) |
| `PileInAbility` | gate **DÉTERMINISTE** : 0 tirage, fire si `chance > 0` | 1 `next_bool` par grot candidat |
| `LetTheGalaxyBurnAbility` | gate de tuile évalué **avant** le `Maybe` ; primitive `next_internal(0,100) < pct` | ordre natif ; primitive `NextBool(chance)` |

---

## 3. PileIn — le point de RE qui rendait le comptage faux

`IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour`, lu 1:1 :

```
cnt   = Count( Friends( UnitsWithSameVisualId(Self@0x148, 1), 3 ) )
amt   = Difference( Direct(GetNumberConstant(0x2a)=chance=75),
                    Multiply(cnt, Direct(GetNumberConstant(0x33)=chance_2=5)) )
opts  = SpawnUnitOptions.WithStatsFromConfig(config, …)
sortF = If( HasTrait(Subject@0x180, 0x1b), <formula@0xb8>, <formula@0xc0> )
tile  = First( SortByFormula( Randomize( CanAddUnit( AdjacentTiles(Self@0x148) ) ), sortF ), 1 )
If( Maybe(amt), Spawn(Self@0x148, tile, GetStringConstant(0x46), opts), Nothing() )
```

`Maybe(amt)` est la surcharge à **UN** argument → `MaybeTrigger` (le PRÉDICAT), pas le nœud EFFET
homonyme `MaybeBehaviour`.

**Le point décisif** : `tile` est un ARGUMENT du `Spawn`, donc de la branche THEN du `If`.
`IdunBattle.Entities.Behaviours.IfBehaviour$$Execute` ne l'évalue **que si** le `Maybe` a réussi. Le
`Randomize` (= `PickRandomAmountSelector(amount = 0x7fffffff)`, `len(pool)` tirages, loi mesurée par
`case-130`) n'est donc **pas** payé sur un échec.

Compte natif par grot candidat :

```
1 next_bool(chance)   +   len(pool) tirages de Randomize   SI le gate a réussi
1 next_bool(chance)                                        SI le gate a échoué
```

Le port d'avant faisait l'inverse exact : **0** tirage de gate, `len(pool)` **toujours**, et un spawn
inconditionnel.

Le gate `chance <= 0` (cap naturel à n >= 15 grots) est conservé implicitement : `next_bool(<=0)` est
toujours faux, et le natif tire quand même — le port laisse donc le tirage se faire et c'est son
verdict qui tranche.

---

## 4. LetTheGalaxyBurn (résidu O6) — ordre + primitive

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` :

```
((On(5=PreAttack, 1) & get_OwnerIsCaster) & Maybe(ConfigConst(0x2a, config)))
                                          & !HasTileStatusEffect(Targets@0x190)
```

Deux corrections, toutes deux mesurables :

1. **Ordre** — le tirage est maintenant consommé sur les DEUX branches (1 tirage tuile nue, 1 tirage
   tuile à status-effect). Le port d'avant en consommait **0** sur la branche bloquée.
2. **Primitive** — `NextBool(chance)` vaut `next_internal(1, 100) <= chance` (borne **99**), pas
   `next_internal(0, 100) < chance` (borne 100). Ce n'est pas un écart seulement statistique : sur un
   même état MT, `r % 99` et `r % 100` sont décorrélés et les verdicts **divergent sur 90 graines
   / 199** à `chance = 33`.

O6 est donc fermé **côté port**. Ce qui reste hors de portée ici : la confrontation bit-exacte LIVE de
ce vecteur précis, bloquée par un fait antérieur — l'attaque du porteur n'est elle-même pas bit-exacte
(cf. `test_bringer_of_despair_live.py`).

---

## 5. Validation

### 5.a Ancrage LIVE, bit-exact (PileIn)

Vecteur : `orksRuntherd` attaque → son passif `SquigHound` spawne un `orksNpc1Grot` (porteur de
`PileIn`, `kind = summons`, hors `--list-pool` : entrée par le summoner, gate SUMMON) ; on laisse le
grot vieillir puis on mesure UN `endturn`. Compte de `genrand_int32` = re-simulation du Mersenne
Twister entre deux `dumpRng` (le nombre de pas EST le nombre de tirages). Board MC1_67.

| seed | live genrand | live spawn | port (M1) | M1 spawn | port d'avant (M0) | M0 spawn |
|---|---|---|---|---|---|---|
| 777 | 5 | 1 | **5** | 1 | 4 | 1 |
| 5   | 5 | 1 | **5** | 1 | 4 | 1 |
| 55  | 5 | 1 | **5** | 1 | 4 | 1 |
| 144 | **1** | **0** | **1** | **0** | 4 | **1** |

**Port 4/4** sur le compte de tirages ET sur le nombre de spawns ; **port d'avant 0/4**. Le seed 144
est le datapoint discriminant : le gate échoue, le natif ne tire qu'une fois et ne spawne rien —
l'ancien port payait 4 tirages **et fabriquait un grot que le jeu n'a pas créé**.

Outil : `scripts/python/probe_o4a_maybe_trigger_rng.py --case pilein --seed <liste>`.

### 5.b Garde (vue ROUGE avant d'être verte)

`scripts/python/tests/engine/runner/test_maybe_trigger_rng_live.py` — **17 tests ROUGES** sur l'arbre
d'avant, 28 verts après :

- consommation et verdict du nœud (`== NextBool(chance)`), 6 valeurs de `chance` ;
- branche `!CanUseRandom` : `99 < chance`, 0 tirage (ROUGE sur `chance >= 100`) ;
- PileIn : 1 tirage par candidat (1, 2, 3 grots) + le tirage consommé EST `NextBool(chance)` ;
- LTGB : 1 tirage sur les deux branches du gate de tuile + primitive native sur 10 graines
  divergentes ;
- LIVE : compte de tirages et spawns d'un `endturn` PileIn (skip propre si la configuration à un seul
  porteur éligible ne se présente pas en 12 tours).

### 5.c Non-régression rejouée

`test_let_the_galaxy_burn_live.py` + `test_on_toxic_damage_live.py` (9 passed),
`test_placement_sort_rng_live.py` (16 passed), `test_turnflow_live.py` +
`test_turnflow_endturn_flags.py` + `test_rad_saturation_live.py` (16 passed).

---

## 6. Ce qui N'EST PAS couvert (découvert par la mesure)

Deux gaps **distincts de ce cas** ont été mis au jour en montant la confrontation. Ils ont été
tranchés depuis, dans `case-n8-owner-has-finished-min-turns.md` :

1. **`OwnerHasFinishedMinTurns` est PER-UNITÉ, et sur `turnsFinished`** —
   `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` résout son
   sélecteur en UNE entité puis compare `min <= IdunBattle.Entities.UnitExtensions$$
   GetTurnsFinished(unit)` (`BaseUnitComponent + 0x5c`). **PORTÉ** : `UnitComponent.turns_finished`
   + `turnflow._bump_turns_finished` (mirror de la boucle d'`EndTurnOperation$$Execute`, exécutée
   AVANT `On(0x17)`).
2. **`load_state` ne seede pas `state.turn_counts`** — exact, mais **sans conséquence** : plus aucun
   consommateur ne dépend de sa valeur absolue (l'unique lecteur restant, `EnvAmbushResurrectAbility`,
   en prend une DIFFÉRENCE avec `turn_defeated`, lui-même écrit depuis ce compteur). Le gap de seed
   réel est le compteur PER-UNITÉ, et c'est un gap de **hooks** : `BaseUnitComponent + 0x5c` n'est
   pas un `StatType`, donc `combatSnapshot`/`GetStat` ne peut pas l'atteindre (résidu **N11**).

Le probe et le test live posent donc `turns_finished` à la main, depuis l'âge OBSERVÉ du grot, et le
disent. C'est aussi pourquoi la mesure de ce cas-ci ne compare que des configurations à **un seul**
porteur assez âgé : elle garde le nombre de candidats constant pendant la mesure.

Également hors périmètre, et inchangé :

- le reste du behaviour PileIn demeure **impératif** (`Count`/`Difference`/`Multiply`, sélecteur de
  tuile dans `operations/spawn.py`) ; seul le gate est un nœud DSL. Migration = chantier
  `dsl-effect-nodes.md`, pas ce cas.
- les autres gates `Maybe` du port utilisaient déjà la bonne primitive et n'ont pas été touchés :
  nœud EFFET `entities/behaviours.py::Maybe` (`MaybeBehaviour$$Execute`), `ReviveEffect`
  (Narthecium / TaintedNarthecium), `BattleFatigue` (`operations/behaviour.py`, dont la *chance*
  reste un résidu de sourcing distinct).
- la branche `!CanUseRandom` est portée par la seule absence de PRNG ; le port ne modélise ni
  `IMatchState.IsRandomAllowed` ni le flag `IsAllowed` du PRNG, faute d'un mode simulation offline
  qui les distinguerait.
