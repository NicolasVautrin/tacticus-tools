# case-122 — canal de REDUCTION DE COUPS du defenseur sur le vecteur ABILITY (residu #116-c)

> Build `gqfc5mff6c`. Probe : `scripts/python/probe_116_necrons.py --phase mte`
> (decompose desormais chaque maillon : base / coups APPLIQUES / per-coup offline vs LIVE).

## 1. La question, et la reponse

**Question.** Quand une attaque d'ABILITY (`execute_ability_attack`) frappe un defenseur portant
`Camouflage_HitReduction`, le natif soustrait-il le malus au nombre de coups ? Et a quel etage ?

**Reponse : OUI, a l'etage PARTAGE**, exactement le meme que l'attaque normale — il n'existe pas
d'etage propre au vecteur ability :

```
AttackDamageOperation$$Execute
  -> IdunBattle.Operations.AttackDamageOperation$$GetAttackHits        (famille ATTACK)
       base = Nullable<int> de l'AttackData (+0x18), defaut 1
       court-circuit si l'octet +0x28 de l'AttackData est vrai
       -> slot d'interface 0xb5 -> IdunBattle.Core.Services.DamagePrediction$$GetAttackHits
            hits = base + GetStat(0x11 ExtraHits) + (IsMeleeAttack ? GetStat(0x17 ExtraHitsMelee))
            hits = Math.Max(hits, 0)
            -> boucle GLOBALE des effets (IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal,
               slot 0x23 par effet) : bonus positifs, malus negatifs, clamps Max(hits, Min(base, min)),
               override absolu, retour-a-la-base ; Math.Max(hits, 0)
```

Le port TRAVERSE deja cet etage sur le vecteur ability depuis [case-61](case-61-ability-hits-channel.md)
(gate famille ATTACK). Le canal n'etait donc PAS le probleme.

## 2. Ce que le decompile a reellement tranche : `IsMeleeAttack` est DECLARE, pas positionnel

C'est le point que [case-61](case-61-ability-hits-channel.md) §1.2 enonce a l'envers (« `IsMeleeAttack`
y est **positionnel** ») et que la lecture refute.

`IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack` ne calcule rien : il resout le slot
d'interface **2** de la `BattleQuery` et delegue a `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`,
en lui passant la tranche `+0x10..+0x28` de l'AttackData — c'est-a-dire le `Nullable<AbilityOrEffect>`
**de l'attaque en cours** (que `AttackDamageOperation$$GetAttackHits` vient d'y ecrire depuis son
`param_5`).

`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` / `$$IsRangedAttack` partent tous deux de
`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(ability)` :

| `attackRangeType` (gameconfig) | valeur | `IsMeleeAttack` | `IsRangedAttack` |
|---|---|---|---|
| absent | 0 (`None`) | **FALSE** | **FALSE** |
| `Melee` | 1 | **TRUE** | FALSE |
| `Ranged` | 2 | FALSE | **TRUE** |
| `Normal` | 3 | `HasFlag(unit, 0x15)` ? FALSE : `AreUnitsInMelee(...)` | `HasFlag(unit, 0x15)` ? TRUE : `!AreUnitsInMelee(...)` |

(`rangeType > 3` leve `NotImplementedException` — les 4 valeurs ci-dessus sont exhaustives.)

Seule la valeur `Normal` (3) est **position-based**. Les autres sont **declarees par l'ability**. Et les
deux predicats ne sont pas complementaires : sur `rangeType = 0` ils sont **tous les deux faux** — c'est
exactement la table de verite deja etablie cote DEGAT par [case-106](case-106-ismeleeattack-fork.md) §2,
la meme paire de fonctions natives.

Distribution mesuree sur `gameconfig.abilities` (559 entrees) : `None` 396 · `Ranged` 84 · `Melee` 69 ·
`Normal` 10 (`CrusadeOfWrath`, `HolyDuel`, `Waaagh`, `FireAndReposition`, `FightingRetreat`,
`ExemplarOfTheKauyon`, `SorcerousFacade`, `WarHowl`, `ExemplarOfHate`, `SternguardFocus` — aucune n'est
une feuille d'attaque du port, cf. §6).

`MultiThreatEliminator` (1006) : `attackRangeType = Ranged` -> `IsRangedAttack = TRUE` **quelle que soit
la distance**, donc le trigger `OwnerIsTarget & IsRangedAttack` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack`
est arme sur CHAQUE maillon de la chaine, y compris un maillon adjacent au caster.

### Le fork du port

`AttackDamageOperation.execute_ability_attack` recevait deja la nature DECLAREE du coup (parametre
`is_melee`, pose par chaque feuille d'attaque depuis l'`attackRangeType` lu au decompile) et s'en servait
pour l'axe DEGAT (#47/#45f). Mais pour l'axe COUPS il **recalculait** la nature POSITIONNELLEMENT
(`_is_ranged_position` = adjacence) — un troisieme fork de `IsMeleeAttack` apres #101 et #106, sur la
meme fonction native.

Consequences, toutes du meme signe (le port se croit en melee sur une ability declaree `Ranged` des que
la cible est adjacente) :

- les malus defenseur gates `IsRangedAttack` (`Camouflage_HitReduction`, aura `BigTarget_AdjacentEffect`)
  sont **tus** ;
- `LightCover` (gate `!IsMeleeAttack`) est **tu** ;
- `Parry` (gate `IsMeleeAttack`) est **sur-applique** ;
- `GetStat(0x17 ExtraHitsMelee)` est **ajoute a tort** a la base.

Symetriquement, une ability declaree `Melee` castee a distance >= 2 perdait `Parry` et gagnait
`Camouflage`/`LightCover`.

## 3. Le triage des gates de la formule (decompile, verbatim)

| effet | trigger natif | consequence sur `rangeType = 0` |
|---|---|---|
| `IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack` | `AreEqual(Tiles(coverPatch@0x148), Tiles(Target@0x178)) & !IsMeleeAttack` | **s'applique** (`!false`) |
| `IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack` | `OwnerIsTarget & IsMeleeAttack` | ne s'applique pas |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack` | `OwnerIsTarget & IsRangedAttack` | **ne s'applique pas** |
| `IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack` | `OwnerIsTarget & IsRangedAttack` | **ne s'applique pas** |
| `IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack` | `OwnerIsTarget` seul | s'applique |

Le port representait `IsRangedAttack` par la truthiness de `is_melee` (`if is_melee: return None`), ce qui
rend `None` (nature inconnue = `rangeType 0`) equivalent a « ranged ». Tant que la facade ability passait
un booleen positionnel, l'ecart etait invisible ; il devient reel des que la nature DECLAREE (tri-etat)
remonte jusqu'a la formule. Les deux gates `IsRangedAttack` sont donc durcis en `is_melee is False`
(mirror `BattleQuery$$IsRangedAttack`, meme foyer que #106). `LightCover` **n'est pas touche** : son
trigger est `!IsMeleeAttack`, pas `IsRangedAttack` — la truthiness y est le mirror exact.

## 4. Le fix

`engine/runner/operations/damage_ops.py::execute_ability_attack` — la facade combat du vecteur ability
alimente desormais `attack_hits_with_modifiers` avec la nature **declaree** (`is_melee`, le parametre
qu'elle recoit deja), et non plus avec `_is_ranged_position`. Un seul point de calcul, la ou le natif en
a un seul.

`engine/entities/effects/loki/hits.py` — `CamouflageHitReductionEffect` et `BigTargetAdjacentEffect`
gatent sur `is_melee is False` (`IsRangedAttack`) au lieu de la truthiness. **No-op strict** pour tout
appelant qui passe un booleen (attaque normale, prediction) ; ne mord que sur le tri-etat `None`.

## 5. Mesure LIVE (session 78, board `MC1_67`, `--crit 0,0`)

### 5.1 Le cas DISCRIMINANT : cible Camouflage ADJACENTE au caster

`tests/engine/runner/test_ability_hits_attack_nature_live.py` — `necroDestroyer` caste 1006 sur un
`tauMarksman` **drive sur un voisin du caster** (dist 1), les autres ennemis parques a >6 hexes,
`--hp-target 90000` (aucun kill -> chaine d'UN maillon). Meme etat, meme RNG ; SEULE variable = le
predicat de nature.

| couple (seed, board) | LIVE (natif) | port, nature **DECLAREE** | port, nature **POSITIONNELLE** (avant #122) |
|---|---|---|---|
| 4242, `MC1_67` | **5** — `[1940, 1943, 1852, 1947, 1968]` | **5** — **bit-exact** | **6** — contredit le live |
| 777, `C3_01` | **5** — `[1804, 1904, 1786, 1812, 1942]` | **5** — **bit-exact** | **6** — contredit le live |

`6 - 5 = 1 = traitVariables.camouflageHitReduction_1` (branche `dist <= 2`). Le natif soustrait donc
bien le malus **au contact**, parce que `attackRangeType = Ranged` est DECLARE. Le contre-cas est
INTEGRE au test (assertions `legacy != applied` et `live != legacy`) : si un jour les deux modeles
convergeaient, le test le dit au lieu de passer pour rien.

### 5.2 Le residu #116-c re-mesure : ce n'est PAS un ecart de COUPS

`probe_116_necrons.py --phase mte` expose desormais, PAR MAILLON, la BASE (`hits`) **et** les coups
REELLEMENT appliques (`applied_hits`) — les confondre est ce qui avait fait lire « offline 2 coups »
la ou le port n'en appliquait qu'un. Ajouts au probe : `--hp-player` (le caster mourait de la reaction
adverse pendant la chaine — confond #70), `--counterfactual`, per-coup LIVE via `captureEvents`.

Regime `--hp-target 8000 --hp-player 60000`, seed 4242 (aucun clamp parasite) :

| maillon | cible | dist | base | port `applied` / per-coup | LIVE per-coup |
|---|---|---|---|---|---|
| 1 | u79 `astraBullgryn` | 1 | 6 | 6 — `[1700, 1839, 1840, 1903, 1837, 1667]` | `[1700, 1839, 1840, 1903, 718, 0]` (clamp PV puis cadavre) |
| 2 | u77 `eldarRanger` (`LightCover`) | 2 | 2 | **1** — `[2987]` | **`[2987]`** — **bit-exact** |

Le maillon 2 confronte precisement le canal : base 2, `LightCover` -2, clamp
`Max(hits, Min(base, minimum))` -> **1 coup**, port == natif.

Regime `--hp-target 2500 --hp-player 60000` (celui qui avait ouvert #116-c) :

| maillon | cible | dist | base | port `applied` / per-coup | LIVE per-coup |
|---|---|---|---|---|---|
| 1 | u79 | 1 | 6 | 6 — `[1700, 1839, 1840, 1903, 1837, 1667]` | `[1700, 800, 0]` |
| 2 | u77 (`LightCover`) | 2 | 2 | 1 — `[2987]` | `[2500, 0]` |
| 3 | u81 `tauMarksman` (`Camouflage`) | 2 | 2 | **1** — `[2613]` | **1** — `[2423]` |

**Le nombre de coups CONCORDE sur le maillon Camouflage (1 = 1).** Le « offline 2 coups (2613) / live
1 coup (2423) » de [case-116](case-116-necrons-lot1.md) §3 comparait la BASE de la chaine au nombre de
coups live : le port appliquait deja UN coup. Ce qui reste est un ecart de **DEGAT per-coup**
(2613 vs 2423, +7,84 %) — axe DEGAT, cf. §6.

### 5.3 Non-regression rejouee (41 passed, 0 skip, 0 fail)

`test_necrons_lot1_live`, `test_ability_hits_channel_live` (le canal lui-meme, case-61),
`test_lightcover_gate_live` -> 7 ; `test_damage_roll_live`, `test_runner_attack_live`,
`test_flail_swing_live` (ability famille ATTACK **declaree Melee** castee au contact : nature declaree
et nature positionnelle coincident -> per-coup bit-exact inchange), `test_summon_trait_effects_live`
(gates `BigTarget`/`Diminutive`), `test_attack_nature_gates_offline` -> 32 ; guard #122 -> 2.

## 6. Ce qui n'est PAS couvert

- **RESIDU ADJACENT — RESOLU par [case-125](case-125-rng-wasted-hits.md)** : maillon 3 du regime
  `--hp-target 2500`, port `[2613]` vs live `[2423]`.

  > **La piste avancee ici etait FAUSSE.** « Le natif execute UN coup de plus que le port ... ce coup
  > supplementaire consomme du `state.rng` que le port ne consomme pas » : non. Le port `_run_hits`
  > boucle sur `hits` **sans aucun gate de mort**, exactement comme
  > `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` (`while (i < hits)`, sans sortie sur la
  > mort ; tirages consommes dans `ExecuteHit`, en amont de la sous-op `0x42`). Les deux cotes roulent
  > tous leurs coups.
  >
  > L'inference « un event de degat == un coup » est elle aussi fausse : des que la cible porte
  > `UnitFlag.Overkilled` (cumul demande >= 2 x PV), `ApplyDamageOperation$$Execute` retourne AVANT
  > d'emettre — les coups suivants existent mais sont MUETS. C'est pour cela que le regime 2500 ne
  > montre que 3 events pour 6 coups.

  Cause reelle : le **report** de `ChainLeftOverHitsAttackDamage` (`GetLeftOverHits`), fige a
  `1 + extraHit` par #116 alors qu'il vaut `max(0, H - k - 1) + extraHit`. Le maillon 2 recevait 2
  coups au lieu de 4 -> 4 tirages de moins -> le maillon 3 tirait faux. Le regime `8000` restait
  bit-exact parce que `k = 5` y rend les deux formules egales ET que `LightCover` (-2, plancher 1)
  ecrase 1 et 2 sur la meme valeur appliquee. Corrige : port `[2423]` = live, bit-exact aussi sur
  seeds 31337 / 777.
- **`attackRangeType = Normal` (3)** : le mode position-based du natif n'est pas modelise (le port ne
  porte que le tri-etat declare). Aucune des 10 abilities concernees n'est une feuille d'attaque du
  port — residu nomme, pas un port speculatif. Idem `HasFlag(unit, 0x15)`, jamais lu.
- **Face PREDICTION du vecteur ability** : elle reste sur la base seule (verdict natif de case-61,
  `GenerateMultiHitAttackPredictions` n'interpose pas la formule) — inchangee ici.
- **`AverageDistance(Caster, Target)`** de Camouflage : toujours approxime par `hexgeo.distance`
  mono-tuile (flag herite de case-59).
- **Branche `-2` (dist > 2) et `-3` (Tall Grass) de Camouflage sur le vecteur ABILITY** : non
  confrontees live ici (le cas discriminant exige dist 1). Elles partagent le meme code que le vecteur
  normal, valide 4/4 en case-59.
