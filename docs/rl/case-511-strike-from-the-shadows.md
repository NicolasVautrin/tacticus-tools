# #511 — `StrikeFromTheShadows` (1225, `astarCyrus`) : l'attaque part D'ABORD, le mouvement est rendu EN DERNIER

Face COMBAT portée. La face DÉCISION l'était déjà (famille `(b)` de
`entities/abilities/active_ability.py` ; `StrikeFromTheShadowsPlaybook$$MakeDamagePredictions` =
`GenerateMultiHitAttackPredictions`, avec un `GetDamage` dont le corps est **partagé** avec
`VigilanceEternalAbility$$GetDamage`).

Build `rnca9r7q6c`. Décompilé = vérité, live = confirmation.

## 1. L'artefact natif : un arbre DSL de trois volets

`IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$ExecuteBehaviour` :

```
atk   = DSLBehaviors$$AttackWithAttackDamage(Caster@DSLSelectors+0x48, Target@+0x60,
            AActiveAbility$$MinMaxDamage(this, abilityState, null),
            Nullable(GetDamageProfile()), Direct(GetHits()),
            AbilityOrEffect$$op_Implicit(this), <AttackOptions ZERO>, selectionType = 2)
eff   = DSLBehaviors$$AddEffect(0x60d, get_AbilityStateReference(this),
            source = Caster@+0x48, targets = Target@+0x60,
            DSLFormulas$$Sum(TurnsFromRounds(1), <DSLFormulas+0x20>))
reset = DSLBehaviors$$ResetMovement(Owner@DSLSelectors+0x30)
AActiveAbility$$Execute(entities, this, op_Addition(op_Addition(atk, eff), reset))
```

**L'ORDRE EST LU, PAS DEVINÉ.** Le nom évoque un déplacement *avant* la frappe ; les deux
`AbilityBehaviour$$op_Addition` du décompilé s'emboîtent `(atk + eff) + reset` — comme
`DiveAttackAbilityBase`, le déplacement vient **après**.

Pas d'`ExecuteAtomic`. Kit gameconfig : `attackRangeType = Ranged`, `damageProfile = Bolter`
(`PiercingRatio` 20), `nrOfHits = 3`, `range = 3`.

**La surcharge d'`AttackWithAttackDamage` est tranchée par ses XREFS ENTRANTES** (cinq surcharges
homonymes ; celle-ci sert aussi `StaffOfStars` / `Supercharge` / `TacticalPrecision`), jamais par sa
signature. Même méthode pour `AddEffect` (4 surcharges) et `Sum` (4).

### La durée vaut `TurnsUntilEndOfCurrentPlayersNextTurn`, pas `TurnsFromRounds(1)`

Le second terme du `Sum` est le champ `DSLFormulas+0x20`, et `DSLFormulas$$.ctor` dit sans ambiguïté
ce que valent ces champs — il alloue cinq nœuds constants et les range :
`+0x18 = 0`, **`+0x20 = 1`**, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`. La forme
`Sum(TurnsFromRounds(1), Direct(1))` est **exactement** celle qu'alloue
`DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn`. Seul le terme `TurnsFromRounds` traverse
`BattleQuery$$ConvertRoundsToTurns` (#98) ; le `Direct(1)` est déjà en TOURS.

**Confirmé live** : l'event natif porte `Effect_RemainingTurns = 3` — le port rend 3, la lecture
pressée aurait rendu 2. Un tour d'écart, silencieux.

## 2. `ResetMovement` : la feuille neuve

`IdunBattle.Entities.Behaviours.ResetMovementBehavior$$Execute`, corps entier :

```
foreach (e in this.<+0x50>.Select(entities, 2)) {
    f = e.GetComponent<UnitFlagsComponent>()
    f.Remove(UnitFlag.ArrivedAtFinalTile) ; f.Remove(UnitFlag.Moved)
    f.Remove(UnitFlag.TurnTerminated)
    if (f.Remove(UnitFlag.TurnFinished))            // le RETOUR est LU
        events.Publish(<groupe 0xc>, e, { <clé 0x70> : 0 })
}
```

**Ce n'est PAS `UnitFlagsComponent$$RemoveTurnFlags`** : celui-là retire *aussi*
`ActiveAbilityUsed(2)` et `Teleported(0xc)`. La différence est le cœur de la mécanique — Cyrus
retrouve son déplacement et son activation, **pas** son active. L'écrire avec `remove_turn_flags`
rendrait l'ability infiniment re-castable.

La classe n'override **ni** `SetsEndTurnFlags` **ni** `SetsActiveAbilityUsedFlag` : la clôture
re-pose `ArrivedAtFinalTile` + `TurnFinished` + `ActiveAbilityUsed` après le behaviour. Seul
`Moved` reste retiré — et c'est lui que lit `aiMovableTiles`.

Call-sites natifs de la feuille : cette ability, `FireAndRepositionAbility$$ExecuteBehaviour`,
`Maugetar_ResetMovementAbility$$CreateBehaviour`.

## 3. L'effet `0x60d` est numériquement INERTE — c'est une lecture, pas un renoncement

`StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense` construit son
`Nullable<EffectBonus>` **inline**, sans passer par aucune fabrique `EffectBonus$$For*` :

```
trigger = DSLTriggers$$IsRangedAttack & DSLTriggers$$get_OwnerIsTarget
buf[0x00] = trigger ;  buf[0x08 .. 0x4f] = 0 ;  return Nullable(buf)
```

La struct `EffectBonus` fait `0x50` octets (`frida/classes.tsv` : 96 boxés − `0x10` de header), et
ses six slots de magnitude sont cartographiés **par les fabriques elles-mêmes** : `+0x08` pct
(`ForPercentIncrease`/`ForPercentDecrease`), `+0x10` addition (`ForAddition`), `+0x18` soustraction
(`ForSubtraction`), `+0x20` minimum (`ForAdditionWithMinimum`), `+0x28` override (`ForOverride`),
`+0x30` drapeau reset (`ForReset`), puis `Nullable<AbilityOrEffect>` en `+0x34..0x4f`. **Tous à zéro
ici.**

Trois sources concordantes :

1. le **contraste** avec le jumeau `FireAndReposition_ReduceDmgEffect$$CreateEffectDamageMalusForDefense`,
   qui appelle bien `ForSubtraction(trigger, ConfigVar(0x12 = dmgReduction), …)` ;
2. la **config** : `StrikeFromTheShadows` ne porte que `nrOfHits`, `range`, `minDmg`, `maxDmg` — pas
   de `dmgReduction` ;
3. les **octets** : `movaps xmm0, [rsp+0x70]` où `rsp+0x70` = le trigger et `rsp+0x78` a été mis à
   zéro, puis `xmm6/7/8` (nuls) sur tout le reste du buffer.

**Confirmé live** : une attaque normale sur une cible **marquée** coûte `3934` côté natif et `3934`
côté port. Le port n'inscrit donc aucune classe d'effet — `EffectFactory` rend le `BaseEffect` par
défaut, dont `create_effect_damage_malus_for_defense` renvoie `None`, soit exactement la
contribution nulle du natif. Ce que l'effet fait réellement, c'est **exister** sur la cible (il est
lisible par un `HasEffect`), et c'est ce que la pose mirror.

### Le faux négatif de table, et comment il a failli coûter

`methods.tsv` ne liste que **2** méthodes pour `StrikeFromTheShadowsEffect` — mais l'absence ne
prouve rien (IL2CPP déduplique les corps). La classe en a **4** : les entrées d'une classe sont
**contiguës dans `g_MethodPointers`**, et lire les voisins des deux adresses connues rend
`CreateActiveCondition` (corps partagé avec `WisdomOfTheAncients_DamageReductionEffect`, `return
DSLTriggers+0x70`) et `CreateTargetSelector` (partagé avec `WhisperingWebEffect`, `return
DSLSelectors+0x30 = Owner`). Aucune des deux ne fabrique de magnitude — mais il fallait le **lire**.

⚠ La même lecture appliquée à `StrikeFromTheShadowsAbility` donne **4** méthodes (`.ctor`,
`ExecuteBehaviour`, `GetDamage` — corps partagé —, `GetTarget`) et **aucun** override de
`SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag`. ⚠ Cette voie a aussi produit un **faux positif** en
route : les entrées voisines *au-delà* du bloc appartiennent à la classe suivante
(`StandVigil_ExtraDmgEffect`, `StormboyzStrike_TeleportingInEffect`) — la contiguïté borne le bloc,
elle ne le nomme pas.

## 4. Registres — et le contrat de disjonction ne mordait PAS

`TARGETING_OPTIONS` : forme **STATIC-COPY** — le ctor n'appelle aucun `TargetingOptions$$.ctor`, il
recopie les `0x40` octets du preset `<TargetingOptions statics>+0x140`, dont le `.cctor` écrit
`+0x00 isSelfCasting = 0`, `+0x08 range <- TargetingRange statics+0x18` (= `RANGE_FROM_CONFIG`),
`+0x20 forceMeleeTarget = 0` (`RangedBool.True`), **`+0x28 rules = 0x4002`**
(`TargetMatchesDynamicRule | TargetIsEnemy`).

`ABILITY_ATTACK_TYPE` : 3ᵉ argument d'`AActiveAbility$$.ctor(this, &opts, 0)` = **0**
(`DirectTargetAttack`), transcrit tel quel.

**RE-COMPTÉ PAR LE CODE, jamais soustrait** : `1225` n'était dans **aucune** des quatre listes du
contrat (`TARGETING_OPTIONS_UNPORTED` 31 entrées, `DYNAMIC_TARGET_RULE_UNPORTED` 6,
`SNAP_TARGETING_UNPORTED`, `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` 19). C'est cohérent : son porteur
est **hors pool**, donc aucune de ces listes ne le recensait. Rien à retirer, aucun compteur à
décrémenter — et c'est un **résultat**, pas une omission.

## 5. La gate : franchie par injection catalogue

`astarCyrus` est un HERO `lineup` **absent de `--list-pool`**, et `data/unspawnable_rank*.json`
**n'existe pas** dans l'arbre — donc aucun refus légitime. La voie est celle qu'avait déjà ouverte
son passif `HaywireMine` (#462-r4b-…-r5) : `catalog_inject.write_augmented_seed_bc` +
`rl_duel build --seed-bc`, board `MC1_67`, seed `777`, `--rank 17 --no-ai`.

## 6. Validation live

| ce qui est mesuré | natif | port |
| --- | --- | --- |
| séquence coup par coup (crit au 1ᵉʳ) | `3507 / 615 / 480` | identique |
| autre montage, 2 coups | `4122` | identique |
| autre montage, `failed_block` | `1764` | identique |
| durée de l'effet `0x60d` | `Effect_RemainingTurns = 3` | `3` |
| `aiMovableTiles` avant → après cast | `0 → 19` | `Moved` retiré |
| second pas joué après le cast | accepté | appliqué |
| attaque normale sur cible **marquée** | `3934` | `3934` |

Trois fautes de **montage** ont été corrigées en route, chacune commentée à son site : `observeBattle`
indexe par `squadId` (lire `id` rendait `None` partout et fabriquait un accord en régime **dégénéré**,
deux dicts vides) ; `mti` est un index **cyclique** et ne compte aucun tirage ; les flags lus sur
l'objet **vivant** montraient l'état d'après le second pas.

## Résidus

* **`#511-r1` — divergence sur RE-CAST au tour suivant, NON RÉSOLUE.** En rejouant l'ability sur la
  **même** cible au tour d'après, le natif inflige plus que le port : `[1084, 1116, 976]` contre
  `[629, 636, 608]`, puis `[496, 914, 982]` contre `[496, 595, 609]` — 3 coups des deux côtés, aucun
  crit, aucun block, mêmes bornes (`2394..3191`), même armure (`2662`), mêmes effets sur le caster.
  Au second de ces casts le **premier coup est identique** et seuls les suivants divergent : c'est un
  décalage de **flux RNG en cours d'attaque**, pas un écart d'étage dégât.
  Ce qui est **éliminé** : l'effet `1549` (son inertie est confirmée bit-exact, §3) ; le
  `ResetMovement` (§2) ; les bornes, l'armure et les effets du caster (mesurés identiques).
  Ce qui **reste ouvert** : le natif consomme 7–8 tirages par cast, le port 10–13 — un écart
  systématique qui n'empêche pourtant pas l'accord bit-exact du régime nominal, ce qui suggère que
  `dumpRng` n'expose pas le seul consommateur. Le régime est **artificiel** : l'ability est à usage
  unique par bataille (`UnitStats_ActiveAbility_CanStillBeUsed` passe à 0), et seul un enchaînement
  de tours piloté à la main la ré-ouvre. Reproduction :
  `python probe_511_strike_from_the_shadows.py --step damage --casts 3` avec `SFTS_REPRENDRE=1`.
* La publication de stream de `ResetMovementBehavior` (`Publish(<0xc>, e, {<0x70>: 0})` quand le tour
  est rouvert) n'a pas de canal équivalent côté port ; l'état, lui, est intégralement mirroré. Le
  groupe et la clé ne sont **pas nommés** : le mirror `GROUP_TYPE` porte des noms faux en nombre
  (#270-a), et écrire un nom faux serait pire que l'ordinal.
* `NoActionAvailable(4)`, posé par le port après le cast, n'a pas été confronté au natif.
