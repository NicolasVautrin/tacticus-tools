# Case 250 — pourquoi le trait `Summon` éteint `CanStillBeUsed` : **il ne l'éteint pas, il fait jouer l'unité**

Trois cas (`#245`, `#248`, `#243`) ont buté sur le même symptôme et l'ont contourné de la même
façon — retirer le trait `Summon` de l'entrée de catalogue — sans jamais en expliquer la cause :

> une unité portant le trait `Summon` rend `abilityState.usable == false` sur ses actives, donc
> `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` court-circuite à `0x1` et l'oracle
> de ciblage ne dit plus rien.

La chaîne candidate héritée — « le slot virtuel `+0x3d8` lu par
`IdunBattle.Entities.Abilities.AActiveAbility$$CanStillBeUsed` » — est un **cul-de-sac** : ce slot
est `GetCooldownAfterUse`, et il ne lit aucun trait.

## 1. Le champ, et ses trois seuls écrivains

Le champ mesuré est `IdunBattle.Entities.Components.ActiveAbility` `CanStillBeUsed` @0x28 (le canal
live le nomme `usable`). `IdunBattle.Entities.Components.ActiveAbility$$.ctor` le pose à `1`. Il
n'a que **trois** écrivains :

| écrivain | ce qu'il fait |
|---|---|
| `IdunBattle.Operations.AddUnitOperation$$InitializeAbilitiesStatus` | au spawn : `comp.CanStillBeUsed = ability.CanStillBeUsed(unit, comp.AmountOfTimesUsed@0x10)` — puis `RemainingCooldownTurns@0x2c <- GetInitialCooldown()` et `IsDisabled@0x35 <- ability.IsDisabled(unit)` |
| `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` | après un cast : `comp.AmountOfTimesUsed@0x10 += 1` ; `comp.<+0x14> += 1` ; `comp.CanStillBeUsed = ability.CanStillBeUsed(caster, comp.AmountOfTimesUsed)` |
| `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute` | ré-arme : `comp.<+0x18> = 0` ; `comp.AmountOfTimesUsed@0x10 = 0` ; `comp.CanStillBeUsed = 1` |

Et le prédicat lui-même :

```
AActiveAbility.CanStillBeUsed(caster, amountOfTimesAlreadyUsed):
    if (UnitExtensions.IsBoss(caster))     return true;          // un boss rejoue sans limite
    if (EntityExtensions.IsMachine(caster)) { ... ability primaire de machine ... }
    cd = GetCooldownAfterUse();                                  // slot virtuel +0x3d8, constante 0x27
    if (cd.HasValue && cd.Value > 0)      return true;           // le cooldown gère la réutilisation
    return amountOfTimesAlreadyUsed == 0;                        // sinon : UNE fois par bataille
```

**Aucune lecture de trait.** Une active sans `cooldownAfterUse` ne sert qu'une fois par bataille, et
c'est la seule façon d'éteindre le champ. Au spawn d'une unité fraîche, `AmountOfTimesUsed = 0` ⇒
`CanStillBeUsed = true`, trait `Summon` ou pas.

## 2. Ce que le trait `Summon` fait réellement

`IdunBattle.Entities.Enum.UnitTrait` : `2 = Summon`, `13 = Object`. Le trait est lu par

```
IdunBattle.Entities.UnitExtensions$$IsAutomatic(unit):
    return unit.BaseUnitComponent.HasTrait(2 Summon)
        || unit.BaseUnitComponent.HasTrait(13 Object);
```

dont le seul consommateur côté moteur est

```
IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute(player, skipAction):
    foreach (u in player.CurrentlyOwnedUnits
               where u.IsAlive(state) && !u.HasFlag(3 TurnFinished) && u.IsAutomatic())
        if (!skipAction)
            for (i = 0; i < 5; i++) if (u.HasActionLeft()) <ComputerAction>(u);
        <EndUnitTurn>(u);
```

appelé par `Core.Services.OperationProcessor$$PlayAutomaticUnits` et
`...$$FinishAutomaticUnitsTurn`.

⇒ **une unité `Summon` (ou `Object`) est AUTOMATIQUE : le moteur la joue lui-même au tour de son
propriétaire.** Elle caste, `ExecuteInternal` incrémente `AmountOfTimesUsed` et ré-évalue
`CanStillBeUsed`, qui retombe à `false`. Ce que trois cas ont pris pour un gate armé par le trait
est le **résidu d'un cast réel**.

## 3. Mesure — `probe_250_summon_automatic.py`

Porteur `tyranSmnWarrior` (`VisualId` `tyranNpc4Warrior`, active 1065 `ScythingTalons`), **déjà au
catalogue `data/seed-bc.json`** : aucun catalogue injecté n'est nécessaire, ce qui écarte au passage
la panne `initAndStart: system error` des rosters injectés. Deux variantes du même roster, même
board (`MC1_67`), même seed (777), l'entrée aménagée sur les mêmes champs qu'en case-243/245
(`Health` 0 → 5000). **La seule action émise sur le camp du porteur est `endturn`.**

Un allié contrôlable (`necroWarden`) est indispensable : quand **toutes** les unités du camp sont
automatiques, le camp n'a jamais la main et `endturn` cesse de faire avancer les tours — mesuré, le
porteur se fige après deux tours.

### 3.1 Maillon 1 — le trait rend l'unité automatique

| variante | traits | `hasAction` | positions successives |
|---|---|---|---|
| `keep` | `Xenos,Summon,Synapse,BigTarget,ShadowInTheWarp` | **jamais** | `(3,2) → (5,4) → (6,5)` |
| `strip` | les mêmes **sans** `Summon` | `True` dès que son camp a la main | `(1,0)` **inchangée** |

Le porteur avec son trait **change de position sans qu'aucun ordre ne lui soit donné**, et n'offre
jamais d'action au joueur — y compris sur les tours où son camp a la main. Sans le trait, la même
unité attend nos ordres et ne bouge pas d'un hex.

> `ctrl` désigne le **joueur courant**, pas la jouabilité de l'unité (piège déjà nommé par
> `probe_243`). Le discriminant est `hasAction` ; la ligne probante est `ctrl=True` **et**
> `hasAction=False` : le camp a la main, et pourtant le porteur n'offre rien.

### 3.2 Maillon 2 — l'usage éteint le champ

Variante `strip` (le porteur est contrôlable), un ennemi amené au contact, cast conduit à la main :

| | `1065.usable` | `hasAction` | PV de la cible |
|---|---|---|---|
| avant le cast | **`true`** | `true` | 8536 |
| après le cast | **`false`** | `false` | **8510** (−26) |

Les 26 points de dégât sont ce qui distingue « l'ability a **servi** » de « l'ability est
désarmée » : sans eux, `usable = false` ne prouverait rien.

## 4. Volet 2 — le masque de 1065, confronté sur son **porteur réel**

1065 était le seul item du module `splash` sans mesure live : son masque était validé par
**identité de preset** avec 1105 `CrushingClaws` (`statics+0x40`), ce qui n'est pas une mesure. La
voie ouverte ci-dessus le rend confrontable. Oracle = `abilityReason` →
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` ; le port est rejoué sur le **même
état figé**.

| cible | `d` | natif | port | flags natifs |
|---|---|---|---|---|
| ALLIÉ | 1 | `0x4000` | `0x4000` | `TargetIsEnemy` |
| CASTER | 0 | `0x4000` | `0x4000` | `TargetIsEnemy` |
| ENNEMI | **1** | **`0x0`** | `0x0` | — |
| ENNEMI | **2** | **`0x8000000`** | `0x8000000` | `TargetIsInRange` |
| ENNEMI | 10 (×2) | `0x8000000` | `0x8000000` | `TargetIsInRange` |

**6/6 d'accord natif/port**, seuil de portée encadré des **deux** côtés (`d = 1` accepté,
`d = 2` refusé), 5 casts illégaux fermés par le masque.

### Contrefactuels — chaque champ démontré porteur (lignes divergentes / 6)

| champ neutralisé | divergences | ce que ça prouve |
|---|---|---|
| `TARGETING_OPTIONS = None` | **5** | la dégradation permissive que le masque ferme |
| `rules = 0` | **2** | `TargetIsEnemy` porte le refus de l'allié et du self-cast |
| `range = None` | **3** | le volet portée porte les `TargetIsInRange` |
| `force_melee_target` basculé | **0** | **INERTE ici** — et c'est *lu*, pas supposé : `RANGE_ADJACENT` pose déjà `overrideRange = 1`, donc le clamp `v = Math.Min(1, v)` de `IdunBattle.Core.Services.TargetingQuery$$GetRange` est idempotent |

Le marqueur « validé par identité de preset » de 1065 est **levé**.

### Contre-épreuve — la garde mord

`range` de 1065 temporairement remplacé par `RANGE_FROM_CONFIG` (l'erreur plausible : « c'est un
splash comme les trois autres du module ») :

```
FAILED test_mask_1065_agrees_with_native
    desaccord natif/port sur 1065 : [{'side': 'ENNEMI', 'dist': 2, 'nat': 0x8000000, 'apres': 0x0}]
```

Une seule ligne diverge — celle du seuil, exactement celle que le montage a été construit pour
exercer. La garde échoue sur son **assertion de fond** (accord natif/port), pas sur un contrôle de
forme. Masque restauré, 8/8 de nouveau au vert.

## 5. Conséquences pour le port

- **Rien à mirrorer côté ciblage.** Il n'existe aucune règle « un summon ne rejoue pas ses
  actives ». Le port n'a donc **pas** de dégradation permissive sur cet axe, contrairement à ce que
  le symptôme laissait craindre.
- **Le retrait du trait dans les montages de case-243/245 reste légitime**, mais sa justification
  change : il ne lève pas un gate, il rend l'unité **contrôlable**, donc interrogeable *avant*
  qu'elle ait consommé sa charge. Les commentaires qui écrivaient « ce trait désarme
  `CanStillBeUsed` » ont été corrigés (`probe_243`, `probe_245`, `loki/splash.py`).
- **Faire caster un summon *avec* son trait n'est pas impossible** — c'est le moteur qui le fait,
  pas nous. Ce qui est impossible, c'est de le lui faire caster **à la main** : l'unité n'offre
  jamais d'action (`hasAction = false`). Pour observer un cast de summon avec son trait, il faut
  laisser `PlayAutomaticUnitsOperation` jouer et lire l'après-coup.

## 6. Ce qui n'est PAS couvert

- **`PlayAutomaticUnitsOperation` n'est pas porté** dans `engine/`. Le moteur Python offre au
  joueur (et à l'IA portée) le contrôle d'unités que le natif joue lui-même — un summon y est une
  unité ordinaire. Écart réel, non chiffré ici : il porte sur le **pilotage**, pas sur la légalité
  d'un cast. Résidu nommé (il faudrait porter `UnitExtensions$$IsAutomatic` + la boucle « jusqu'à 5
  actions puis fin de tour », et décider qui, du moteur ou du driver, l'exécute).
- **`AmountOfTimesUsed` / le once-per-battle ne sont pas recalculés offline.** Le port lit
  `can_still_be_used` du canal live (`engine/runner/snapshot.py`) et ne le décrémente pas lui-même
  après un cast : `ActiveAbilityOperation$$ExecuteInternal` n'est mirroré que partiellement sur ce
  point. Sans conséquence tant que l'état vient du live à chaque pas ; à porter si le moteur doit
  simuler plusieurs tours d'affilée.
- **Le cast *automatique* d'une active par un summon n'a pas été capté** : sur `MC1_67`/777 le
  porteur automatique s'arrête à `(6,5)` et n'atteint pas le contact, et amener un ennemi à lui
  entre deux `endturn` n'a pas suffi (le tour adverse n'est pas joué par `endturn` seul). Le
  maillon 2 a donc été mesuré sur la variante **contrôlable**, ce qui l'isole proprement mais ne
  ferme pas la boucle complète « le moteur joue → il caste → le champ s'éteint » en une seule
  observation.
- **La branche `IsBoss` et la branche machine-primaire** de `AActiveAbility$$CanStillBeUsed` sont
  lues au décompilé, non exercées live.
- **Un seul couple (board, seed)** : `MC1_67` / 777.
