# case-115 — GATE DE CIBLE d'une ability active : le maillon générique + son point d'extension

**Livré : le refus de cible d'`ActiveAbilityOperation.ExecuteInternal` existe désormais offline.**
Un cast que le natif refuse est un no-op moteur complet dans le port — pas de behaviour, pas de
flags de tour — et il est refusé **avec le même code `TargetingRule` que le natif**.

Le découpage suit celui du natif, pas une commodité de port : **une** cascade générique pilotée par
les `TargetingOptions` du ctor, **un** point d'extension par ability. Waaagh (1058) en est la
première instanciation.

---

## 1. La chaîne native

```
IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal
  -> IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget
       construit un délégué sur l'ability et teste
       IdunBattle.Core.Services.IBrokenTargetingRuleExtensions$$IsInvalid du résultat ; deux lambdas :
         ...ActiveAbilityOperation.u003Cu003Ec__DisplayClass9_0$$u003CIsInvalidTargetu003Eb__0  (slot 7)
            -> IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidTargetReason        (cast top-level)
         ...ActiveAbilityOperation.u003Cu003Ec__DisplayClass9_0$$u003CIsInvalidTargetu003Eb__1  (slot 0xe)
            -> AActiveAbility$$GetInvalidTargetReasonForContinue   (2e jeu d'options @+0xb0)
  -> AActiveAbility$$GetInvalidTargetReason
       -> AActiveAbility$$SetConfigValuesInTargetingOptions
            options.Range <- AbilityConfiguration.GetNumberConstant(config, 0x16)
       -> AActiveAbility$$GetInvalidTargetReasonWithRules   (slot iface +3 de this+0x58)
            -> IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason  (5 args)
                 range  = TargetingQuery$$GetRange(caster, casterTiles, options)
                 reason = TargetingQuery$$GetInvalidCasterReason(...)  ; si rompue -> RENDUE TELLE QUELLE
                 sinon    TargetingQuery$$GetInvalidTargetReason (7 args)  = LE FILTRE STATIQUE
```

Le filtre statique est une cascade de ~25 règles, **chacune gatée par un bit** du masque
`IdunBattle.Core.Services.TargetingRule` (flags 64 bits, `TargetingOptions+0x28`). La première règle
rompue rend un `IBrokenTargetingRule` via
`IdunBattle.Core.Services.TargetingRuleExtensions$$GenericBrokenTargetingRule`.

## 2. Le critère de découpage — et où entre le `GetDynamicInvalidTargetReason` d'une ability

`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` copie les `TargetingOptions` de la sous-classe
dans `this+0x70..0xaf`, **puis écrase les deux derniers qwords** :

```
param_1[0x14]  (= options+0x30)  <- délégué lié au slot vtable this+0x470
param_1[0x15]  (= options+0x38)  <- IdunBattle.Core.Services.TargetingOptions.DynamicTargetingTargetRule
                                    liée au slot vtable this+0x480 = GetDynamicInvalidTargetReason
```

et le filtre statique n'invoque cette règle-délégué **que si le bit `TargetMatchesDynamicRule`
(0x2) est posé** :

```
if ((options.Rules & 0x2) != 0) {
    long reason = options[0x38].Invoke(caster, casterTiles, target, ...);
    if (reason != 0) return GenericBrokenTargetingRule(reason);
}
```

D'où la réponse au critère :

| | quoi | où | combien de fois |
|---|---|---|---|
| **GÉNÉRIQUE** | la cascade + les `TargetingOptions` | `engine/runner/abilities/targeting.py` | **1** maillon, consommé par toutes |
| **PROPRE à une ability** | `GetDynamicInvalidTargetReason` | `ActiveAbility.get_dynamic_invalid_target_reason` | **1 par ability** qui pose le bit `0x2` |

Instancier une 2ᵉ ability coûte donc : lire son ctor décompilé → poser
`TARGETING_OPTIONS = TargetingOptions(rules=<masque>)` (1 ligne), et — seulement si le masque porte
`0x2` — écrire son `get_dynamic_invalid_target_reason`.

> **Piège du ctor** : `TargetingOptions` a plusieurs surcharges. Celle « préset + flags »
> (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`, ex.
> `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor` = préset statique
> `+0x200` + `0x806000000`) fait que **le littéral visible n'est pas le masque effectif**. Ne
> renseigner `TARGETING_OPTIONS` qu'après avoir lu le masque EFFECTIF.

## 3. Règles portées — et ce qui ne l'est pas

L'inventaire **exhaustif** des ~25 règles du filtre statique, dans l'ordre natif, avec le motif de
chaque non-port, vit en tête de `engine/runner/abilities/targeting.py`. Résumé :

| masque | nom (`TargetingRule`) | porté | prédicat offline |
|---|---|---|---|
| `0x10` | `CasterHasNotMoved` | **oui** (volet caster) | `unit_has_moved` = `UnitFlagsComponent.Has(Moved=0)` |
| `0x8000000000` | (bit 39, self-only) | **oui** | `caster == GetUnit(target)` |
| `0x400` | `TargetIsFriendly` | **oui** | même `team` (+ inversion `FriendlyFire`) |
| `0x4000` | `TargetIsEnemy` | **oui** | `UnitsCanAttackEachOther` |
| `0x20000000` | `TargetIsTargetable` (sauf bit 41) | **oui** | `!HasFlag(unit, 0x11)` |
| `0x2` | `TargetMatchesDynamicRule` | **oui** | délègue à l'ability |
| — | **portée** (`GetRange`) | **oui** (#241) | non gaté par un bit mais par `TargetingOptions.Range` ; cf. `case-241-range-gate.md` |
| — | ligne de vue (`GetTilesObscuringTerrain`) | non | même emplacement de cascade que la portée, non porté |
| `0x40`/`0x1000`/`0x20000`/`0x80000` | domaine TILE | non | la cible-tuile n'est pas une entité du `State` |
| `0x800000` | `TargetIsAllowedForCaster` (Taunt) | non | `GetOnlyTargets` non porté |
| … | 15 autres | non | cf. le tableau du module |

**Une règle non portée ne refuse jamais** (dégradation permissive — même convention que « ability
non portée ⇒ behaviour no-op »). C'est ce qui rend le contrat de fidélité vérifiable :

```
natif == 0   =>  port == 0                          (STRICT : le port n'invente aucun refus)
natif != 0   =>  port == natif  (règle portée)
             ou  port == 0      (règle non portée)
jamais       :   port != 0 et port != natif         (refus pour la MAUVAISE raison)
```

Une ability dont les `TARGETING_OPTIONS` valent `None` (masque non RE-lu) n'est **pas gatée du
tout**. À la livraison de `#115`, 60 des 61 abilities du registre étaient dans ce cas.

> **État au 2026-07-28** (re-dérivé, `probe_181_targeting_gaps.py`) : **51 des 91** entrées portent
> leur masque, **40** ne l'ont pas. L'instanciation est devenue la voie normale (lots `89518da`,
> `ff66741`, `#181`), et un **cliquet** l'entretient :
> `tests/engine/runner/test_ability_registry_ratchet.py` refuse à la fois une entrée neuve sans
> masque et une exemption devenue caduque. Ces chiffres se périment — les re-dériver.

### `UnitsCanAttackEachOther` — détail qui n'est pas « équipes différentes »

`IdunBattle.Core.Services.TargetingQuery$$UnitsCanAttackEachOther` (mirror du décompilé) :

```
if (!IsActor(a) || !IsActor(b)) return false;
friendly = UnitsAreFriendly(a, b);
if (battleQuery.<slot 0x91>(a, b)) return true;
if (HasEffect(a, state, 0x67, activeOnly)) return friendly;     // 0x67 = EffectType.FriendlyFire
return !friendly;
```

Le porteur de `FriendlyFire` (103) **inverse** la relation : il ne peut attaquer que ses amis. Porté
et testé. Le slot 0x91 (override inconditionnel « oui ») n'est pas porté — il ne peut qu'AJOUTER des
cibles légales, donc son absence est le seul résidu qui va dans le sens strict ; aucune divergence
observée en validation.

## 4. Le volet CASTER — pris parce qu'il tombait gratuitement, et MESURÉ

`TargetingQuery$$GetInvalidCasterReason` tourne avant le volet cible. **Une seule** de ses règles est
portée, `CasterHasNotMoved` (0x10), parce que le bit est déjà dans les `TARGETING_OPTIONS` et que le
prédicat existait déjà (`unit_has_moved` = mirror de
`IdunBattle.Entities.UnitExtensions$$DidMove` = `UnitFlagsComponent.Has(unit, Moved=0)`).

Mesure (`probe_115_ability_reason.py`, board MC1_67, seed 777, même Warboss, même cible légale) :

| | `casterReason` natif |
|---|---|
| avant le `move` | `{ruleClass: NoBrokenTargetingRule, hex: 0x0}` |
| après un `move` d'une tuile | `{ruleClass: GenericBrokenTargetingRule, hex: 0x10, reasons: ["CasterHasNotMoved"]}` |

Le natif renvoie la raison caster **telle quelle**, d'où le même `0x10` dans `targetReason`.

> Le flag `Moved` n'est pas exposé par les RPC : `load_state` ne le seede pas ⇒ la règle est
> **inerte sur tout état chargé** (aucun risque de régression), et mord sur le chemin
> replay/self-play offline, où c'est `MoveUnitOperation` → `set_moved_flag` qui pose le flag.

## 5. Waaagh (1058) — première instanciation

`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$.ctor` :
`TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x106004012, 0, 0, 0)` (surcharge « flags
directs » ⇒ le littéral EST le masque). Décomposition :

| bit | nom | effet |
|---|---|---|
| `0x2` | `TargetMatchesDynamicRule` | consulte `GetDynamicInvalidTargetReason` |
| `0x10` | `CasterHasNotMoved` | le Warboss ne peut pas caster après s'être déplacé |
| `0x4000` | `TargetIsEnemy` | refus sur soi-même / un allié |
| `0x6000000` | `AllowObscuredTarget` | permissif (aucune contrainte de ligne de vue) |
| `0x100000000` | (bit 32, nom hors dump 32 bits) | prédicat `battleQuery` slot 0x61, non porté |

`WaaaghAbility$$GetDynamicInvalidTargetReason` (mirror) :

```
Count( GetPossibleMovementTiles(target) ) > 0 ? 0 : 0x8000000   // TargetIsInRange
```

**C'est un arbre DSL, porté comme un arbre.** `WaaaghAbility$$GetPossibleMovementTiles` =
`IdunBattleLogic.Entities.DSLFactory$$TilesUnitCanMoveToChargeTarget(caster@0x160, casterTile@0x168,
target, UnitMovementRangeWithBonus(caster, 1099, Direct(extraMovement)), canReachOnly=0)`, dont le
décompilé n'assemble que deux nœuds :

```
CanAddUnit(AdjacentTiles(target))  op_BitwiseAnd  MovableTilesInRange(caster, casterTile, range, 0)
```

Deux nœuds ajoutés en conséquence (`engine/entities/selectors.py`) :

* `MovableTilesInRange` — feuille DSL qui appelle le pathfinder impératif
  (`IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select` → slot 0xc de la
  `PathfindingQuery` ; `canReachOnly=0` ⇒ le `visited` du BFS, `=1` ⇒ le `stop_set`) ;
* `tiles_unit_can_move_to_charge_target` — helper de factory qui assemble les deux nœuds.

**Les deux consommateurs natifs partagent désormais le même arbre**, exactement comme le natif :
l'étage MOVE de `WaaaghAbility$$ExecuteBehaviour` (qui trie et prend la première tuile) et le gate de
ciblage (qui n'en prend que le `Count`). Le collapse `SortTilesByUtility(0x20)` reste au-dessus, dans
`waaagh_charge_tile`, inchangé.

## 6. Validation

Oracle = **`abilityReason(casterId, abilityType, targetId)`**, qui rend le masque `TargetingRule`
natif (`targetReason.hex` + noms de flags). Bien plus fort qu'un booléen accepté/refusé : il permet
d'asserter que le port refuse **pour la même raison**.

### Mesure (board MC1_67, seed 777, runner 666)

| cible | `fromHere` natif | `abilityReason` natif | port |
|---|---|---|---|
| ennemi hors portée de charge | non | `0x0000000008000000` `TargetIsInRange` | `0x8000000` |
| ennemi chargeable ×2 | oui | `0x0` | `0x0` |
| le Warboss lui-même | non | `0x0000000000004000` `TargetIsEnemy` | `0x4000` |
| allié Ork | non | `0x0000000000004000` `TargetIsEnemy` | `0x4000` |
| 3ᵉ unité alliée | non | `0x0000000000004000` `TargetIsEnemy` | `0x4000` |

Agrément **bit à bit** sur toutes les unités vivantes. C'est la décomposition A/B (statique) vs C
(dynamique) de `case-111` §3, désormais reproduite offline avec les bons codes.

### Tests

`tests/engine/runner/test_ability_target_gate_live.py` (13 tests) :

- agrément port ↔ `abilityReason` sur **toutes** les unités vivantes (contrat de fidélité du §3) ;
- « le port ne refuse jamais ce que le natif accepte » (la propriété zéro-régression) ;
- séparation statique / dynamique, avec précondition sur la raison NATIVE ;
- refus ⇒ no-op offline **complet** (pas de behaviour, pas de flags, pas de spawn) et signature live
  à 2 événements / groupe `User_UseAbility` seul ;
- cible légale ⇒ behaviour intégral offline (spawn + buffs + flags) et `mutated`/`actionConsumed`
  live ;
- volet caster : `CasterHasNotMoved` avant/après `move`, précondition lue sur le natif ;
- inversion `FriendlyFire` (branche du décompilé qu'aucun seed n'exerce) ;
- « une ability sans `TARGETING_OPTIONS` n'est pas gatée » (garde des 60 autres).

Généralisation : 4 couples board/seed (`MC1_67`/777, `MC1_67`/4242, `C1_25`/31337, `C2_19`/909) —
tous verts. Sur `C1_25`/31337 la géométrie n'offre aucun ennemi hors portée de charge : les 3 tests
qui exigent ce cas skippent explicitement, l'agrément global tourne quand même sur toutes les unités.

Non-régression (`AbilityHandler` est un point de passage de toutes les abilities) : 63 tests verts
sur 14 fichiers — Waaagh (#111, #95), gate acteur-mort (#70), flags de tour (#139), cibles-TUILE
(AberrantHypermorph, SporeMineLauncher, TheQuickening), summons, dégâts d'ability, MoW, et les
consommateurs de sélecteurs de charge (HeroicFusillade, VigilanceEternal, SkyStrike, TheBetrayer).

## 7. Ce qui n'est PAS couvert

- **38 des 94 abilities du registre n'ont pas de `TARGETING_OPTIONS`** (compte du 2026-07-29,
  à re-dériver) ⇒ pas de gate pour elles. C'est le travail d'instanciation restant (1 ligne par
  ability + son prédicat dynamique quand le bit `0x2` est posé), pas un défaut du maillon.
  Ventilation à jour : `docs/rl/port-residuals-inventory.md` §3.
- **Poser un masque peut RÉVÉLER un défaut ailleurs**, et c'est arrivé (#181) : la fixture de
  `test_combat_restoratives_live.py` téléportait le caster **sur** une tuile déjà occupée par un
  ennemi. Tant que 1002 n'était pas gatée, la re-résolution de cible #120bis remplaçait
  silencieusement la cible du self-cast sans conséquence visible (l'arbre vise `Caster()`) ; le
  masque posé, le cast tombait sur `TargetIsFriendly`. Le gate n'avait pas tort — l'état de test
  était impossible. Symptôme à reconnaître : `handler.last` porte `replaced_from`/`replaced_target`
  en plus d'`invalid_target`.
- **Les règles du filtre statique laissées permissives** (inventaire en tête de `targeting.py`). Le
  gros morceau restant est le **domaine TILE** (une cible-tuile n'est pas une entité du `State`).
  La **portée**, elle, est portée depuis #241 (`case-241-range-gate.md`) ; il reste à ses côtés la
  **ligne de vue** (`GetTilesObscuringTerrain`), testée au même endroit de la cascade.
- **`ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`** : le natif refuse une cible-unité
  MORTE sauf si l'ability l'autorise (virtuel slot 0x11). L'inventaire des overrides n'a pas été
  relevé ; le porter avec un défaut « refuse » casserait les abilities de résurrection. Conséquence
  actuelle : offline, un cast sur un cadavre passe le gate.
- **`IsValidCaster`, `IsAbilityBlocked`, cooldown, mode atomique** : hors périmètre, même observable
  live à 2 événements, non décomposés.
- **`battleQuery` slot 0x91** de `UnitsCanAttackEachOther` (override « oui » inconditionnel) et
  **slot 0x90** de `UnitsAreFriendly` (rabattu sur l'égalité de `team`).
- **Le bit 32 (`0x100000000`) de Waaagh** : prédicat `battleQuery` slot 0x61 sur les tuiles, nom hors
  du dump 32 bits, non porté. Il n'a jamais discriminé sur les 4 géométries mesurées (agrément
  bit-à-bit avec le natif).
