# case-10046 (volet POWER-UP) — le bouclier dont la DURÉE est RÉGLABLE

> Pendant du volet BOUCLIER D'ENVIRONNEMENT, où la durée est un **mur** :
> `EnvStartProtection (1280)` passe `DSLFormulas+0x20` (la constante `1`) en `turns`, **câblée
> dans l'arbre DSL**. Le power-up, lui, lit sa durée **dans la config d'ability**. C'est la seule
> voie mesurée qui produise un bouclier de plus d'un tour.

Mesuré le 2026-08-23, build `t6dpr4k06g`, sur runner isolé (aucune bataille réelle consommée).

## 1. Le foyer

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.APowerUpAbility$$AddShield`, lu au décompilé :

```
TryGetNumberConstant(config, AbilityConstantType.shieldPct)   -- 80 / 0x50
  ABSENT  -> DSLBehaviors$$Nothing()            <- aucun bouclier, et AUCUNE erreur
  PRESENT ->
    amount = DSLFormulas$$Direct(shieldPct)
    rounds = DSLFormulas$$ConfigConst(AbilityConstantType.nrOfRounds, config)   -- 69 / 0x45
    turns  = DSLFormulas$$TurnsFromRounds(rounds)
    base   = DSLFormulas$$StatAmount(target, StatType.health, ...)
    shield = DSLFormulas$$PercentageOf(base, amount)
    If(DSLTriggers$$AmountIsGreaterThanZero(amount),
       DSLBehaviors$$CreateShield(target, shield, source, turns, null, stackable: true))
```

Deux conséquences, toutes deux **confirmées par dose-réponse** :

| constante de la BC | effet mesuré |
|---|---|
| `shieldPct` 100 -> 500 | `Shields_InitialAmount` 8533 -> **42665** (x5, = % des PV MAX de la CIBLE) |
| `nrOfRounds` 1 -> 9 | `Shields_TurnsLeft` 2 -> **18** (`TurnsFromRounds` = x2) |

Le montant se lit sur la **cible**, pas sur le power-up : trois marcheurs, trois montants
distincts (`adeptCanoness` 8533, `adeptHospitaller` 8533, `adeptRetributor` 7530, `adeptCelestine`
6025), chacun = ses propres PV max.

## 2. ⚠ LE DÉCLENCHEUR EST `Is_Last_Tile`, PAS L'OCCUPATION DE LA TUILE

Trois régimes, trois résultats — le seul qui tire est celui où l'unité **TERMINE** son
déplacement sur la tuile :

| régime | événement | power-up | bouclier |
|---|---|---|---|
| l'unité **spawne** sur la tuile (`applyAddUnit` sur la même case) | aucun | **survit** | **AUCUN** |
| l'unité **traverse** la tuile | `ChangePosition ... Is_Last_Tile=0` | **survit** | **AUCUN** |
| l'unité **s'arrête** sur la tuile | `ChangePosition ... Is_Last_Tile=1` | consommé (`DirectlyKillUnit`) | **OUI** |

Le témoin qui tranche : tuile **id 69** = `(6,2)` sur `C1_74`. `u116` la traverse
(`Is_Last_Tile=0`) -> le power-up `u118` est **toujours vivant** au tour suivant ; `u112` s'y
arrête -> `Ability_Power e=118` puis `AddOrUpdateShield e=112`. Même tuile, même power-up, deux
résultats.

⇒ **Semer les power-ups SUR les tuiles de spawn ne donne rien.** Il faut les semer **à côté**,
et dépenser le premier déplacement pour s'y poser.

## 3. Le montage, en trois gestes

1. **Rien à injecter** : les **20** power-ups sont **déjà** dans `BC.Units` du seed BC (717
   entrées), et leurs configs dans `BC.Abilities.PassiveAbilities`.
2. **Poser** : `applyAddUnit({runnerId, unitId, playerId: 12, col, row})` sur le runner. C'est la
   voie native des objets — le seed BC place ses 40+ `LootObj_*` par `BC.PredefinedUnits[].Id = 12`.
3. **Régler** (facultatif) : patcher `BC.Abilities.PassiveAbilities["<ability>"].Constants` dans
   un seed BC custom, **puis ÉPINGLER**.

## 4. ⚠ SANS L'ÉPINGLE, LE PATCH EST EFFACÉ EN SILENCE — ET LA MESURE MENT

`refresh_ability_configs` re-synthétise depuis le gameconfig toute config qui en diffère : un
`nrOfRounds` patché sur disque revient à sa valeur d'origine **avant** d'atteindre le runner. La
première mesure a ainsi rendu `TurnsLeft=2` / `8533` — soit exactement le régime NON patché — et
se lisait comme « la constante n'est pas lue ». Le tell est dans la sortie du build :

```
[seed-bc] configs d'ability re-synthetisees ... : 1 rafraichies ['PowerUp_Armor']   <- EFFACÉ
[seed-bc] configs d'ability EPINGLEES (patch delibere, #375) : ['PassiveAbilities/PowerUp_Armor']
[seed-bc] configs d'ability re-synthetisees ... : 0 rafraichies []                  <- TENU
```

```python
import catalog_inject as C
C.write_pins("logs/seed-bc-powup.json", ["PassiveAbilities/PowerUp_Armor"])
```

C'est le mécanisme d'épinglage #375, écrit pour cette faute exacte. **Toujours vérifier le
compte `rafraichies` avant de conclure quoi que ce soit d'un patch de constante.**

## 5. Qui porte un `shieldPct`

**Neuf** des 20 power-ups, tous à `shieldPct: 100` / `nrOfRounds: 1` sauf le dernier :

`powupArmor` (+`healthPct` en armure fixe) · `powupDamage` · `powupHealing` · `powupHealth`
(+PV max x2) · `powupHits` (+2 coups) · `powupMeleeHits` (+4) · `powupReactivateAbility` ·
et `powupReinforcementShield` (`shieldPct: 10`, **sans** `nrOfRounds`).

⚠ **`powupReinforcementShield` n'est PAS ce qu'il paraît** : il émet `AddReinforcementShield` sur
l'entité **3** — pas une unité — et **aucune** unité ne gagne de bouclier (`shields: []` sur les
deux camps). Son nom désigne les renforts, pas le marcheur. Le power-up qui protège le marcheur
est n'importe lequel des huit autres.

Les onze restants n'ont pas de `shieldPct` : par la branche `Nothing()` du §1, ils ne posent
**aucun** bouclier — et sans lever.

## 6. Résidus

- La voie LIVE n'est pas outillée : le patch de `frida/hooks/features/battle-config.ts` sait
  écrire `turnOrder`, `environmentAbilities`, `playerTeamIds`, `templateOverrides` — **pas** les
  `Constants` d'une ability de `BC.Abilities.PassiveAbilities`. Sans ce levier, un power-up posé
  en bataille réelle donne le régime d'usine (100 % des PV, `TurnsLeft=2`), ce qui **ne demande
  aucun reinject**. Le régime réglé, lui, en demande un.
- `eventCount: 0` en retour d'`applyAddUnit` **n'est pas un refus** — les trois poses de ce banc
  ont toutes rendu `0` et toutes abouti. La vérité terrain est la carte, ou la sonde
  `setupSpawnTrace` (`addUnitFires` / `executeNull`).
- La carte ASCII de `rl_duel view` **ne dessine qu'un glyphe par tuile** : une unité posée sous un
  power-up y est INVISIBLE. Ne jamais lire son absence comme un refus de pose — croiser avec les
  positions `@(col,row)`.
