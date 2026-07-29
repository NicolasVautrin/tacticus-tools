# case-226-r — `SkyStrike` (1025) : le coup suit le **pipeline d'ARME**, pas un `StatAmount` dégénéré

**Verdict : quirk porté.** Build `gqfc5mff6c`. Code : `engine/runner/abilities/sisterhood.py`,
`engine/runner/abilities/behaviours/combat.py`. Mesure : `scripts/python/probe_226r_skystrike_spread.py`.
Garde : `tests/engine/runner/test_sky_strike_live.py`.

---

## 1. Le symptôme

Le cast live de `SkyStrike` (1025, `adeptCelestine`) n'a été confrontable que depuis #226 (avant, il levait
`system error` faute de `BC.Abilities` dans le seed BC injecté). Dès qu'il l'a été, les trois coups sont
sortis **inégaux** — `hits = [3334, 3156, 2477]` — alors que le port émettait une valeur **fixe**.

Ce n'était ni crit, ni block, ni evade : `Attack_DidCrit=0 Attack_DidBlock=0 Attack_DidEvade=0`,
`UnitStats_RemainingArmor=0` sur les trois coups.

## 2. Ce que dit le décompilé (la RE, avant tout chiffre)

### 2.1 Le nœud de dégât n'est PAS ce qui décide

`IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` construit

```
AttackWithAttackDamage( caster@0x160, target@0x178,
    Sum( NormalAttackDamage(caster), Direct(GetVariableForLevel(8 = extraDmg)) ),
    NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster),
    AbilityOrEffect(this+0x10 = 1025), <options> )
```

et `IdunBattleLogic.Entities.DSLFactory$$NormalAttackDamage` n'est qu'un
`IdunBattle.Entities.Formulas.StatAmountFormula(unitSelector, statType=0, statPart=0, …)`.

Deux faits qui ferment la piste « le nœud porte la plage » :

* `IdunBattle.DSL.ASimpleAmountFormula$$CalculateMin` **est** un appel virtuel de `Calculate` (le corps est
  DÉDUPLIQUÉ avec `CalculateMax` — ghidra le nomme `CalculateMin`, la table frida `CalculateMax`). Pour une
  formule simple, `min == max == Calculate` : aucune plage.
* Cette même factory est celle de l'**attaque NORMALE** :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$AttackAmount` appelle
  `DSLFactory$$NormalAttackDamage` (xrefs). Or l'attaque normale, elle, **a** le spread ±20 %. Le nœud ne
  peut donc pas être le discriminant.

### 2.2 Le commutateur : l'octet **+6** des `AttackDamageBehaviourOptions`

Le 8ᵉ argument d'`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` est un
`System.Nullable<IdunBattle.Entities.Behaviours.AttackDamageBehaviourOptions>` (struct de 32 octets). Deux de
ses octets étaient déjà portés :

| octet | sémantique | porteur connu |
|---|---|---|
| +4 | `alwaysOverkilled` | `FlailSwingAbility$$ExecuteBehaviour` (`local_1e8 = 0x100000000`) |
| +5 | `alwaysCrit` | `TacticalPrecision` (1154), branche CHARGE |
| **+6** | **« calcul de dégât d'ARME »** | **`SkyStrikeAbility$$ExecuteBehaviour`** (`uStack_1e2 = 1`) |

La sémantique du +6 se lit sur l'attaque normale elle-même :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` écrit
**ce même octet** depuis un getter booléen de l'ability
(`local_1d8._0_7_ = CONCAT16(<vtable+0x4b8>, (undefined6)local_1d8)`), juste avant de passer la struct au
`Nullable`. SkyStrike, lui, l'écrit **à 1 en dur** — et c'est le **seul** octet non nul de sa struct.

Chemin du flag, lu bout à bout :

```
options+6                                   (SkyStrikeAbility$$ExecuteBehaviour)
  -> AttackDamageBehaviour+0x9e             (.ctor : Nullable.GetValueOrDefault -> +0x98..+0xb7)
  -> AttackDamageOptions+0x2f               (AttackDamageBehaviour$$ExecuteTarget repack, CONCAT11(+0x9e,+0x98))
  -> AttackPredictionRequest+0x6a           (AttackDamageOperation$$ExecuteHit, uStack_300 octet 2)
  -> slot 4 IDamagePrediction = DamagePrediction$$PredictAttack -> PredictAttackRaw
       -> DamagePrediction$$GetBaseDamageFix64  (bornes = base ± DamageSpreadPercentage)
```

### 2.3 Le contraste qui écarte l'explication « famille de factory »

Le smite Psyker (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour`)
est de la **même famille ATTACK** (même overload `AttackWithAttackDamage`, même `AttackDamageBehaviour`), avec
un nœud scalaire lui aussi (`PercentageOf(StatAmount(Attack), pct)`) — et il n'a **aucune** variance (mesuré
live de longue date). Son 8ᵉ argument est un `Nullable` **VIDE** (`local_78..local_58 = 0`, HasValue = 0).
`MartialExemplarAbility$$ExecuteBehaviour` : options ZÉRO également.

⇒ La famille de factory ne distingue pas les deux cas ; l'octet +6, si.

## 3. La mesure (décomposition par étage, aucun scalaire fitté)

`probe_226r_skystrike_spread.py` monte un runner isolé (`adeptCelestine` injectée par
`catalog_inject.write_augmented_seed_bc`), colle une cible au caster (gate `Not(IsAdjacent)` faux ⇒ aucun
move ⇒ l'ATTAQUE est isolée), **dumpe le RNG juste avant le cast**, caste, puis rejoue l'état pré-cast sous
le même RNG selon trois modèles :

| modèle | pipeline | tirages/coup |
|---|---|---|
| **A** | le port | — |
| **B** | `execute_normal_like(V, spread_pct=20)` — reduce-then-roll (attaque normale) | 1 |
| **C** | bornes brutes `[V−20 %, V+20 %]` en roll-then-reduce (mode bornes) | 2 |

`V = Attack(caster) + extraDmg[level] = 2510 + 499 = 3009`.

Résultats (chaque cast = 3 coups) :

| scénario | live | A (port AVANT) | A (port APRÈS) | B | C |
|---|---|---|---|---|---|
| seed 777, adjacent | `[3334, 3156, 2477]` | `[3009, 3009, 3009]` | == live | == live | `[3334, 2477, 3409]` |
| seed 31337, adjacent | `[2982, 2580, 3346]` | — | == live | == live | `[2982, 3346, 2530]` |
| seed 4242, adjacent | `[3380, 3132, 2771]` | — | == live | == live | `[3380, 2771, 3457]` |
| seed 99, adjacent | `[2722, 3391, 2457]` | — | == live | == live | `[2722, 2457, 2832]` |
| seed 777, armure 4000 | `[1408, 1230, 1274]` | — | == live | == live | `[1334, 991, 1364]` |
| seed 31337, armure 4000 | `[1056, 1136, 1420]` | — | == live | == live | `[1193, 1338, 1012]` |
| seed 777, charge dist 2 | `[3334, 3156, 2477]` | — | == live | == live | `[3334, 2477, 3409]` |
| seed 4242, charge dist 2 | `[3380, 3132, 2771]` | — | == live | == live | `[3380, 2771, 3457]` |

**Bilan : 24 coups, port == live 24/24.** Contre-modèle dégénéré **0/24** ; contre-modèle roll-then-reduce
**4/24** (seul le 1er coup coïncide, et **0/6** dès que la cible est armurée — la largeur des bornes réduites
diffère de celle des bornes brutes, ce qui décale l'offset RNG *dès* le premier tirage).

Trois coups tirés dans une plage de ~1200 valeurs : l'égalité bit-exacte **identifie** le pipeline (et son
nombre de tirages), elle ne l'ajuste pas.

Le scénario `--armor-target 4000` (branche perçage dominante) et le scénario `--charge` (le `MoveUnit` ne
consomme aucun tirage) sont les deux généralisations craftées : elles changent l'observable sans changer le
verdict.

## 4. Le port

`sky_strike_tree()` passe désormais par le **mode `amount`** de la feuille DSL :

```
AttackWithAttackDamage(Target(), "SkyStrike", profile, is_melee=True,
                       amount=Sum(StatAmount(Caster(), Attack), Const(extraDmg)),
                       hits=MeleeWeaponHits, amount_spread_pct=20,
                       native_factory="attack", ability_type=1025)
```

* le nœud de dégât devient un **arbre DSL** (il était collapsé dans un `damage_override` impératif) : la stat
  Attack est relue à l'exécution contre l'`entities` du behaviour, donc POST-move, comme le natif ;
* `amount_spread_pct` est le port de l'octet +6. **Défaut `0`** ⇒ strict no-op pour les deux autres
  call-sites du mode `amount` (smite Psyker, transfert `HazeOfCorruption`), qui passent le `Nullable` vide ;
* `hits_override` n'est plus utilisé par SkyStrike (le mode `amount` a son `hits` explicite) ; le paramètre
  reste pour les autres porteurs.

## 5. Ce qui n'est PAS couvert

* **Le nom exact du champ +6** n'est pas lisible (struct sans ctor ni propriété dans les tables ; le getter
  de l'ability est un slot de vtable `+0x4b8` non nommé). La **sémantique** est établie par deux sources
  indépendantes — l'attaque normale l'alimente depuis un getter, et SkyStrike qui le pose à 1 suit le
  pipeline d'arme bit-exact — mais le libellé C# reste inconnu.
* **Le recensement des autres porteurs de l'octet +6** n'a pas été fait (hors périmètre du cas). Les
  appelants de l'overload `AttackWithAttackDamage` @180dea6b0 vérifiés ici — `FlailSwing` (+4),
  `MartialExemplar` (options zéro), `Psyker` (Nullable vide) — ne le posent pas. Une ability qui le poserait
  et serait portée en mode bornes aurait le même écart que celui corrigé ici.
* **`is_normal_attack`** : `execute_normal_like` force `is_normal_attack=False` pour les malus défenseur
  gatés (#112). La mesure ne discrimine pas ce point (la cible `necroWarden` ne porte aucun effet de défense
  gaté sur la nature du coup) — le comportement est laissé INCHANGÉ, et c'est un résidu nommé, pas un choix
  validé.
* **La face PRÉDICTION** (playbook `SkyStrikePlaybook$$MakeDamagePredictions`) n'est pas portée ; ce cas ne
  traite que la face COMBAT.
