# case-207 — les DEUX `genrand` en trop de `deathBlightlord` : `HazeOfCorruption_TargetFinder`

**Critère (binaire)** : quels sont les deux tirages supplémentaires que le natif effectue à l'entrée
d'une attaque de mêlée de `deathBlightlord`, et à quel étage nommé appartiennent-ils ?

**Réponse** : les deux tirages sont **deux exécutions** du `PickRandomly` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`
— une par émission de `On(0x2b = PreUnitAbility)`. Il y en a **deux** sur ce montage parce que
`SwornProtector` fait re-entrer `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget`
(#120bis), et la ré-entrée ré-émet le vecteur. À chaque émission le pool ne contient **qu'un** candidat,
d'où **1 + 1** tirages, pas un forfait de 2.

| | genrand natif | genrand port | coups d'arme |
|---|---|---|---|
| avant | **5** | 3 | port ≠ live |
| après | **5** | **5** | **bit-exact 4/4 seeds** |

---

## 0. Étape 0 — la mesure re-dérivée (l'écart se reproduisait)

Montage `case-dpw` §6.b : `deathBlightlord` attaque `astraCreed` en mêlée NUE, board `MC1_67`,
`--crit 0,0 --block-target 0,0 --hp-target 90000 --armor-target 6000`.

Seed 777, flux brut `genrand_int32` = `[655685735, 2776480559, 1298611771, 862112678, 266444375, …]`,
cellule d'arme `[890, 1934]` (largeur 1045) :

```
raw[0] -> 1132     raw[1] -> 1514     raw[2] -> 1250     raw[3] -> 999     raw[4] -> 1252
port   = [1132, 1514, 1250]                     (3 tirages : raw[0..2])
live   = [1250,  999, 1252]                     (natif 5 : raw[2..4] pour les coups)
```

Les 3 valeurs LIVE sortent de la **même cellule** que le port, sur `raw[2], raw[3], raw[4]` : **la
cellule et l'ordre du port étaient JUSTES**, il manquait exactement **2 tirages EN AMONT**.

## 1. Localisation par contraste — ce que ce n'est PAS

Trois montages, même drive, même board, même seed :

| montage | genrand natif | port | conclusion |
|---|---|---|---|
| `deathPutrifier` → `astraCreed` (mêlée nue) | 2 | 2 | le spawn `SwornProtector` coûte **0** tirage |
| `deathBlightlord` → `astraBullgryn` (1v1) | 3 | 3 | 3 coups, kit complet du porteur, **0** surplus |
| `deathBlightlord` → `astraCreed` | **5** | 3 | le surplus exige **le kit ET une 2ᵉ unité ennemie** |

Le montage `deathPutrifier` invoque Kell exactement pareil (même géométrie finale : `(6,8)` Kell,
`(6,7)` Creed, `(5,8)` porteur — les trois mutuellement adjacents) et son **premier** tirage EST son
coup d'arme. Le spawn est donc hors de cause, contrairement à ce que suggérait la piste « effets
`1375` / `1147` » de `case-dpw` §7 : `1375` = `TerminatorArmour_Visual`, `1147` =
`TerminatorArmour_ReduceDmg`, deux effets **défensifs** du porteur, sans rapport.

## 2. L'artefact natif

### 2.1 `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateTrigger`

```
On(0x2b = PreUnitAbility, 1) & get_OwnerIsCaster
```

**Aucun autre terme** : ni `IsNormalAttack`, ni `AbilityHasAttackType`, ni `AreEnemies`. Le volet se
réveille pour n'importe quelle ability du porteur.

### 2.2 `…HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`

```
sel   = Damageable( AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3) )
pick  = PickRandomly(sel, 2, allowRepeat = 0, maxRepeat = 0x7fffffff, ignoreForcedTargets = false)
units = TargetsSelector.SelectAllUnits(pick, entities, 3)          <-- LES TIRAGES ONT LIEU ICI
beh   = Nothing()
if Count(units) > 0 : beh += AddBondEffect(0x435, AbilityStateReference,
                                           Target@0x178, Get(units,0), Self@0x148, One@0xc0)
if Count(units) > 1 : beh += AddBondEffect(0x435, AbilityStateReference,
                                           Get(units,0), Get(units,1), Self@0x148, One@0xc0)
beh  += SetPersistentData( AbilityOrEffect(this.Id), Self@0x148, Get(<clé statique>),
                           EntityId(Target@0x178) )
```

`SelectAllUnits` est appelé **DANS** `CreateBehaviour` (la FORME de l'arbre — 0, 1 ou 2 nœuds
`AddBondEffect` — dépend du cardinal résolu) : le tirage est payé à **chaque** déclenchement, avant
tout coup. C'est ce qui rend ce volet observable même quand rien ne meurt.

Chaînes lues, verbatim :

* `IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(X, p3, p4)` (surcharge 4-args) =
  `Enemies(reference = X, Units(AdjacentTiles(X), p3, p4) op_Subtraction X, p4)` ; idem
  `IdunBattleLogic.Entities.DSLFactory$$AdjacentFriends` avec `Friends`.
  **La référence d'équipe EST le centre** — `AdjacentFriends(Target)` = les alliés DE LA CIBLE.
* `IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd` et `$$op_Addition` construisent la MÊME classe, qui
  ne diffère que par le champ mode `+0x28` (`0` pour `&`, `1` pour `+`) → `&` = **intersection**.
* `IdunBattleLogic.Entities.DSLFactory$$Damageable(x)` = `UnitsWithoutTrait(x, 0x40e, 3)`.
* `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(source, amount, allowRepeat, maxRepeat,
  ignoreForcedTargets)` → `IdunBattle.Entities.Selectors.PickRandomAmountSelector` : `min(len(pool),
  amount)` tirages, bornes **décroissantes**, même quand le pool tient dans `amount` (loi `case-130`).
  Le mapping des arguments est lu dans `…PickRandomAmountSelector$$.ctor` : `allowRepeat` = **0** ici
  (le pool rétrécit à chaque pick).
* `0x435` = `EffectType.HazeOfCorruption_DamageTransfer` = 1077.

### 2.3 Pourquoi DEUX émissions, et pas un pool de 2

Le port modélise déjà la ré-entrée #120bis (`operations/active_ability.py`, appelée par
`damage_ops.execute`) : après `On(0x2b)`, si le switch `SwornProtector` a fait entrer Kell sur la tuile
visée, `ExecuteForReplacedTarget` ré-entre dans un `AttackDamageOperation.execute` NEUF — donc un
`On(0x2b)` NEUF. Le pool, lui, ne contient qu'un candidat à chaque fois :

| émission | `Target@0x178` | `AdjacentEnemies(Self)` | `AdjacentFriends(Target)` | pool | tirages |
|---|---|---|---|---|---|
| 1 | Creed (77) | {Creed, Kell} | {Kell} | **{Kell}** | 1 |
| 2 | Kell (94) | {Creed, Kell} | {Creed} | **{Creed}** | 1 |

**Témoin direct** (`probe_207_haze_target_finder.py --dump-events`) — les deux bonds, avant le premier
coup d'arme :

```
Effect_Id 100 : BondEffect_BondedId 79, Effect_SourceId 77, Effect_SourceTriggeredAbility 1076
Effect_Id 101 : BondEffect_BondedId 79, Effect_SourceId 94, Effect_SourceTriggeredAbility 1076
```

`Effect_SourceId` = le `Target@0x178` de l'émission (77 = Creed puis 94 = Kell) ;
`BondEffect_BondedId` = `Self@0x148` (79 = le porteur) ; `Effect_RemainingTurns` = 1 aux deux.

C'est cette paire qui a fait TRANCHER entre les deux lectures possibles d'`op_BitwiseAnd` : une UNION
donnerait un pool de 2 sur l'émission 1 (et **1 tirage** sur le contrôle 1v1, où l'on en mesure **0**) ;
une intersection sur une émission UNIQUE ne donnerait qu'un seul bond, alors qu'il y en a deux.

## 3. Le port

* `engine/runner/operations/triggers/loki/haze_of_corruption.py` —
  `HazeOfCorruptionTargetFinderAbility` : `matches` = `get_OwnerIsCaster` seul (un pool VIDE donne un
  behaviour à 0 tirage, PAS un trigger qui ne fire pas) ; `execute_behaviour` = l'arbre de pool
  verbatim + `_pick_randomly_n(state, pool, 2)` (foyer UNIQUE de la loi `case-130`, on délègue) + la
  CHAÎNE de bonds `(Target, units[0])` puis `(units[0], units[1])`.
* `engine/runner/operations/triggers/dispatch/registry.py` — `"HazeOfCorruption"` →
  le trigger (clé = `passiveAbilities` du gameconfig, comme `SwornProtector`).
* `engine/entities/selectors/units.py` — `AdjacentFriends` gagne le paramètre `reference`
  (même rôle, même défaut que `SurroundingEnemies.reference`). Le collapse historique
  « `team == ctx.caster.team` » n'est exact que lorsque le centre EST le caster ; ici le centre est la
  CIBLE, et le collapse rendrait le **camp inverse**. Tous les call-sites existants passent le caster →
  défaut inchangé, zéro régression.

### Ce qui n'est PAS porté, et pourquoi

* ~~**La charge utile de l'effet `0x435` = 1077 `HazeOfCorruption_DamageTransfer`**~~ — **PORTÉE
  DEPUIS, cf. `docs/rl/case-209-haze-of-corruption-damage-transfer.md`** : le report vaut
  `demandé − appliqué` pour le coup fatal et la BASE nominale pour tout coup tombant ensuite sur le
  cadavre (coup Toxic bonus de `HazeCorruption_BonusHitAbility` compris — orthographe native **sans le
  « Of »**, ce qui l'avait fait manquer ici). Bit-exact 6/6 montages.
* `SetPersistentData(AbilityOrEffect(Id), Self, Get(<clé>), EntityId(Target))` : pas de couche
  « persistent data » d'ability côté port → no-op documenté (c'est le repli de `GetLeftOverDamages`
  quand le contexte n'a pas de leftovers ; sur un montage à un relais la source de l'effet EST déjà la
  cible initiale, cf. case-209 §3).
* `Damageable` = `UnitsWithoutTrait(0x40e, 3)` côté natif ; le port garde son collapse PRÉ-EXISTANT
  « vivant et PV > 0 » (nœud partagé, hors périmètre de ce cas).
* ORDRE du pool quand `len(pool) > 2` : résidu #215 standing. Le port rend l'ordre `AdjacentTiles`
  natif (`Board.neighbours_native`) pour le terme GAUCHE de l'intersection, ce qui est le bon
  itérateur ; la CONSOMMATION, elle, est exacte à tout cardinal.

## 4. La mesure

```
python probe_207_haze_target_finder.py --seeds 777,12345,88,314159          # montage d'origine
python probe_207_haze_target_finder.py --seeds 777 --dump-events            # les bonds natifs
python probe_207_haze_target_finder.py --seeds 777,12345,88 --target astraBullgryn   # contrôle 1v1
python probe_207_haze_pool_ladder.py  --seeds 777 --k 0,1,2                 # l'échelle min(k,2)
python -m pytest tests/engine/runner/test_haze_of_corruption_rng_live.py -q
```

### 4.a Montage d'origine — `deathBlightlord` → `astraCreed`, 4 seeds

| seed | genrand natif | port (après) | port (avant) | live | port (après) |
|---|---|---|---|---|---|
| 777 | 5 | **5** | 3 | `[1250, 999, 1252]` | **`[1250, 999, 1252]`** |
| 12345 | 5 | **5** | 3 | `[1302, 1486, 1602]` | **`[1302, 1486, 1602]`** |
| 88 | 5 | **5** | 3 | `[1725, 1174, 1834]` | **`[1725, 1174, 1834]`** |
| 314159 | 5 | **5** | 3 | `[1607, 1746, 1763]` | **`[1607, 1746, 1763]`** |

Séquence du port, seed 777 : `NextInternal(0,1)`, `NextInternal(0,1)`, puis les trois coups sur
`[890, 1935)` — **compte ET ordre**, pas seulement le total.
Les valeurs du seed 88 sont exactement celles que `case-dpw` §6.b avait relevées comme non alignées.

### 4.b Contrôle 1v1 — `astraBullgryn` (aucun allié adjacent à la cible), 3 seeds

`natif 3 = port 3`, per-coup bit-exact 3/3, **0 bond natif**. Le trigger fire (le porteur EST le
caster) mais son pool est vide → 0 tirage. C'est la garde anti-sur-tir.

### 4.c Généralisation CRAFTÉE — l'échelle `k = |pool|` sur UNE SEULE émission

Géométrie pilotée (`applyAction move` sur les ennemis) : cible SANS `SwornProtector` adjacente au
porteur, et `k` ennemis sur les **voisins communs** du porteur et de la cible (sur une grille hex,
deux hexes adjacents en ont exactement 2).

| k | genrand natif | port | bonds natifs | bornes des tirages | per-coup |
|---|---|---|---|---|---|
| 0 | 3 | **3** | 0 | — | bit-exact |
| 1 | 4 | **4** | 1 | `(0,1)` | bit-exact |
| 2 | 5 | **5** | 2 | `(0,2)` puis `(0,1)` | bit-exact |

Cette échelle est le vrai discriminant : elle **réfute** le modèle « forfait 2 tirages par attaque du
porteur » (qui prédirait 5, 5, 5) ET le modèle « pas de tirage quand le pool tient dans `amount` »
(3, 3, 3), et elle confirme les **bornes décroissantes** de `PickRandomAmountSelector`.

### 4.d Garde et contrôle adversarial

`scripts/python/tests/engine/runner/test_haze_of_corruption_rng_live.py` (11 tests) :

* OFFLINE — le nœud de pool prend les alliés DE LA CIBLE (montage où les deux camps sont à portée),
  l'intersection n'est pas une union, la CHAÎNE des bonds, les littéraux lus (`amount = 2`, `0x435`) ;
* LIVE — l'échelle `k = 0/1/2` (comptage, per-coup, `bonds == min(k,2)`), avec l'exigence que les
  trois comptes natifs DIFFÈRENT (sinon le scénario ne discrimine plus, et le test le DIT) ;
* LIVE anti-tautologie — le port d'AVANT (trigger neutralisé) est vérifié **incapable** de rendre le
  compte ET les coups dès `k >= 1` ;
* LIVE — le montage d'origine (2 émissions) : `bonds == 2`, `port == natif`, écart au contrefactuel
  == 2 tirages, per-coup bit-exact.

Vérifié en conditions adversariales : trigger dé-enregistré → **3 tests rouges** ; `reference` retiré
d'`AdjacentFriends` (retour au collapse caster) → le test de pool rougit.

### 4.e Non-régression rejouée

`test_flail_swing_live.py` + `test_sworn_protector_kell_live.py` (10 passed) ;
`test_contagions_of_nurgle_new_unit_live.py` + `test_pick_randomly_one_rng_live.py` (18 passed) ;
`test_pick_randomly_rng_live.py` + `test_damage_roll_live.py` (11 passed) ;
`probe_dpw_weapon_cell.py --seeds 777,12345,314159,88` → **arme alignée 4/4, contrefactuel 0/4**
(inchangé).

## 5. Ce qui n'est PAS couvert

* ~~Le **transfert de dégât** lui-même~~ — **RÉSOLU par case-209** (`docs/rl/case-209-haze-of-corruption-damage-transfer.md`).
  Le montage qui manquait ici : mêmes unités, `--hp-target` abaissé pour que la cible tombe sous le
  coup. Reste ouvert de ce volet : le flux RNG du report (natif 8 vs port 6) et la chaîne à 2 relais.
* Le régime `len(pool) > 2` (3 candidats ou plus) : la CONSOMMATION est exacte par construction
  (`min(k, 2)`), mais **QUI** est piqué dépend de l'ordre source — résidu #215, non mesuré ici.
* Le déclenchement sur une ability **non-attaque** du porteur (le trigger n'a aucun gate d'attaque) :
  `deathBlightlord` n'a qu'une active offensive (`FlailSwing` 1042), donc le régime « le porteur cible
  un ALLIÉ » n'existe pas sur ce kit et n'a pas de montage. Le port suit le décompilé (pas de gate),
  ce qui est le comportement conservateur.
* La variante `allowRepeat` : lue à **0** au call-site, donc le pool rétrécit — non confrontée
  séparément (elle ne se distingue de `1` qu'à `k = 1` et `amount = 2`, régime où le natif ne tire
  qu'une fois, ce qui est exactement ce que l'échelle `k = 1` mesure).
