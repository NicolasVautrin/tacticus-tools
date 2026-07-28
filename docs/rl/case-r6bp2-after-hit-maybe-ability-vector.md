# R6-b'' — le `Maybe` after-hit est évalué sur les coups d'une attaque d'ABILITY

**Question binaire.** Le trigger after-hit `On(8)` (type `GetStuckIn`, behaviour
`Maybe(AddBonusHits, GetBonusHitChance)`) se déclenche-t-il sur les coups d'une attaque
d'**ABILITY**, comme il le fait sur ceux d'une attaque NORMALE ?

**Réponse : OUI**, pour les **deux** familles de factory, avec un index de coup qui **repart de 0
à chaque cible**. Le port ne roulait ce `Maybe` que sur le vecteur NORMAL : le flux RNG de tout le
vecteur ability était décalé d'autant.

---

## 1. L'énoncé natif, établi au décompilé (`gqfc5mff6c`)

### 1.1 `EvaluateAfterHitTriggers` a TROIS appelants — dont les deux du vecteur ability

`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` est le seul émetteur de
`On(8)`. Ses xrefs sont **exhaustives** et toutes en `UNCONDITIONAL_CALL`, en **dernière
instruction** de leur `ExecuteHit` :

```
IdunBattle.Operations.AttackDamageOperation$$ExecuteHit    # famille ATTACK
IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit   # famille ABILITY
IdunBattle.Operations.MachineDamageOperation$$ExecuteHit
```

Or le vecteur ability du port (`damage_ops/ability.py`) emprunte **les deux premières** selon
`is_attack_damage_op` — la famille ATTACK est *littéralement la même fonction* que l'attaque
normale. ⇒ **aucun gate de famille** sur ce canal (contraste avec les mods attaquant, le crit et
le canal #179, qui eux sont bien gatés par `is_attack_damage_op`).

Lu verbatim dans `AbilityDamageOperation$$ExecuteHit` :

```
EvaluateAfterHitTriggers(this, &hitInfo, attacker, target,
                         local_res20 /* = param_4 = *(currentAttack + 0x30) */,
                         isCrit, dmg, damageProfile);
```

### 1.2 L'index vient du même `OngoingAttack`, incrémenté après chaque coup

`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` fait, dans sa boucle :

```
ExecuteHit(&ret, this, *(currentAttack + 0x34) /* série */,
                       *(currentAttack + 0x30) /* INDEX DE COUP */, ...)
...
*(int*)(currentAttack + 0x30) += 1        # mirror INLINE d'ADamageOperation$$UpdateCurrentAttackAfterHit
List.AddRange(hitGroup + 0x58, attacker + 0xf0) ; attacker+0xf0.Clear()   # = UpdateHitGroupAfterHit
...
*(int*)(currentAttack + 0x34) += 1        # fin de SÉRIE
```

— strictement la structure d'`AttackDamageOperation$$ExecuteHits`. Et
`IdunBattle.Operations.AbilityDamageOperation$$Execute` re-boucle sur une **COPIE** de
`hitGroup + 0x58` après la série principale : **les coups bonus déférés existent aussi côté
famille ABILITY**.

`currentAttack` est obtenu par `IdunBattle.Operations.ADamageOperation$$GetCurrentAttackOrDefault`
(slot 199 / 200 d'`IBattleQuery` selon un flag du message) →
`IdunBattle.Core.Services.BattleQuery$$GetCurrentAttackOrDefault` → `HasCurrentAttack` ?
`MatchState$$GetCurrentAttack` (= `Peek` sur `MatchState+0x60`) : `new OngoingAttack()`.

### 1.3 L'index repart de 0 **par cible** — les deux factories passent par `AttackBehaviour`

Les deux `DSLFactory` finissent par le **même** emballage (lu verbatim) :

```
IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage
    inner = new AttackDamageBehaviour(...)
    return  new AttackBehaviour(caster, targets, inner, options)

IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage
    inner = new AbilityDamageBehaviour(...)
    return  new AttackBehaviour(caster, targets, inner, options)
```

et `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` encadre **chaque cible** :

```
foreach (i, target in targets) {
    if (prev == null || prev != target)  slot 0x3a  # Core.Services.OperationProcessor$$StartAttack
    <behaviour de cible>.ExecuteTarget(...)         # AttackDamageBehaviour | AbilityDamageBehaviour
    if (next == null || next != target)  slot 0x3b  # Core.Services.OperationProcessor$$FinishAttack
    prev = target
}
```

`Core.Services.OperationProcessor$$StartAttack` appelle `IdunBattle.Operations.
StartAttackOperation$$Execute`, qui **construit un `OngoingAttack` neuf** (`+0x30 = +0x34 = 0`)
et le pousse sur `MatchState+0x60` — et qui, au passage, est **l'émetteur de `On(PreAttack = 5)`**
(`FUN_180026490(0x50, .., 5, ..)`), ce qui reconstruit d'où venait l'événement 5 déjà porté sur ce
vecteur (#84/#61).

⇒ côté port, `hit_index0` reste **0** pour la phase d'arme d'une attaque d'ability, exactement
comme le vecteur normal. Une ability multi-cibles (splash) = un `execute_ability_attack` par cible
= un `OngoingAttack` par cible : rien à threader entre cibles.

### 1.4 Le trigger n'a aucun gate de vecteur

```
IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger
    On(8, 1)
      & AmountIsOdd(CurrentHitIndex())
      & get_OwnerIsCaster
      & !AmountIsGreater(MinDistance(owner@0x160, target@0x178), Direct(2))
```

Ni `IsNormalAttack`, ni `CurrentAbilityIs`. **Le seul gate structurel est la DISTANCE** — et c'est
lui qui fournit le second montage de validation (§3.b).

---

## 2. Le port

Deux éditions, **un seul site d'évaluation du `Maybe`** (`damage_hits._run_hits`, inchangé) :

* `engine/runner/operations/damage_ops/ability.py` — calcule `_gsi = getstuckin_combat_chance(...)`
  (le **même** foyer que `damage_ops/normal.py`) aux positions déjà résolues `_ap_h`/`_tp_h`, puis
  le passe :
  - à `_run_hits(bonus_hit_chance=_gsi, ...)` — **sans gate de famille** (§1.1) ;
  - à `execute_additional_hits(bonus_hit_chance=_gsi, hit_index0=r["next_hit_index"])` —
    strictement le câblage R6-b' du vecteur normal (les sous-opérations de groupe partagent
    l'`OngoingAttack` par `Peek`).
* `engine/runner/operations/additional_hits.py` — le résidu « VECTEUR ABILITY » de la docstring est
  fermé et renvoie ici.

`bonus_hit_chance is None` (attaquant sans `GetStuckIn`, ou cible à plus de 2 hex) ⇒ **strict
no-op**, aucun tirage supplémentaire nulle part. Aucun deuxième site d'évaluation n'a été créé.

---

## 3. Mesure — `probe_r6bp2_after_hit_maybe_ability.py`

### 3.0 Le porteur — gate de confrontabilité (constat RE-DÉRIVÉ, pas hérité)

Le compte hérité « `orksRuntherd` est le seul héros portant `GetStuckIn` » est **faux**. Balayage
de `gameconfig` : **cinq** héros (`kind == lineup`) le portent, tous dans le pool spawnable
(`rl_duel.py build --list-pool`, rank 17) :

| héros | active | offensive ? | coups |
|---|---|---|---|
| `orksBigMek` | GrotTank (1057) | non (summon) | — |
| `orksKillaKan` | **DakkaDakkaDakka (1171)** | **oui** | **6** |
| `orksNob` | UnstoppableMomentumReworked (1152) | oui | 1 → index 0 PAIR, ne déclenche jamais |
| `orksRuntherd` | GetEmRuntz (1045) | non (summon) | — |
| `orksWarboss` | Waaagh (1058) | attaque NORMALE (phase 4) | vecteur normal, déjà couvert |

⇒ **un seul montage confrontable** : `orksKillaKan` / `DakkaDakkaDakka` (famille ATTACK,
6 coups Projectile, portée 3). Six coups = index 0..5 = **trois index IMPAIRS** (1, 3, 5).

`DakkaDakkaDakka` n'est **pas** au registre `ABILITY_CLASSES` : le rejeu offline appelle
`AttackDamageOperation.execute_ability_attack` **directement**, avec les paramètres que sa feuille
`AttackWithAttackDamage` lui passe (lus au décompilé : `AActiveAbility$$MinMaxDamage`,
`DakkaDakkaDakkaAbility$$GetNumHits` = `Min(nrOfHits + TimesRepaired × extraHits, maxNrOfHits)`,
`AbilityConfiguration$$GetDamageProfile`). C'est la décomposition par étage : on mesure l'étage
porté (le vecteur de dégât d'ability), pas l'arbre DSL de l'ability — et le **ratchet** (les coups
doivent reproduire le live) refuse tout paramètre faux. Mesuré : bornes `[1996, 2493]`, `hits = 6`,
profil `Projectile`, perçage `15`, niveau 50, multiplieur 180.

Régime PERÇAGE-DOMINANT (`--armor-target 6000`, fixture `_pierce_floor_regime`), crit et block
neutralisés, board `MC1_67`, 1v1. **Quatre modèles** rejoués sur le **même état** et le **même flux
RNG** : `shipped` (le port livré), `no_maybe` (`bonus_hit_chance` forcé à `None` = le port
d'AVANT), `parity` (`hit_index0` décalé de 1 : *même* nombre de tirages, rangs différents),
`always` (canal forcé **sans le gate de distance**).

### 3.a — cible ADJACENTE : gate du trigger OUVERT

| seed | live | bonus GetStuckIn live | shipped | no_maybe | parity |
|---|---|---|---|---|---|
| 777 | `[300, 305, 302, 367, 347, 347]` | 0 | **=live** | `[300, 305, 332, 314, 311, 347]` | `[300, 372, 302, 311, 347, 328, 369, 339]` |
| 31337 | `[323, 348, 307, 323, 353, 302, 331]` | 1 | **=live** | `[323, 348, 306, 373, 327, 353]` | `[323, 313, 307, 327, 353, 357, 331]` |
| 12345 | `[338, 359, 340, 318, 336, 307, 344]` | 1 | **=live** | `[338, 359, 350, 310, 302, 336]` | `[338, 307, 340, 302, 336, 306, 344]` |
| 314159 | `[308, 353, 361, 364, 367, 337]` | 0 | **=live** | `[308, 353, 306, 344, 357, 367]` | `[308, 331, 361, 357, 367, 323]` |
| 88 | `[307, 304, 366, 338, 337, 312, 340]` | 1 | **=live** | `[307, 304, 316, 338, 323, 337]` | `[307, 307, 366, 323, 337, 304, 340]` |
| 2468 | `[323, 301, 311, 314, 327, 365, 321]` | 1 | **=live** | `[323, 301, 356, 325, 317, 327]` | `[323, 306, 311, 317, 327, 363, 321, 308]` |
| 4242 | `[330, 370, 356, 340, 314, 311, 342]` | 1 | **=live** | `[330, 370, 361, 329, 367, 314]` | `[330, 325, 356, 367, 314, 370, 342]` |
| 20202 | `[339, 372, 322, 340, 364, 343, 335]` | 1 | **=live** | `[339, 372, 304, 365, 351, 364]` | `[339, 304, 322, 351, 364, 334, 335]` |

⇒ **port 8/8, `no_maybe` 0/8, `parity` 0/8, 8/8 montages discriminants.** Régimes : {0 bonus : 2,
1 bonus : 6}. (`always` ≡ `shipped` sur ce montage — le gate de distance y est déjà ouvert.)

**Preuve côté JEU, indépendante du port** : sur les six seeds à un coup bonus, le 7ᵉ événement de
dégât porte `Additional_Hit_TriggeredAbility_Source: 1234` = `0x4d2` — le littéral **exact** que
`GetStuckInAbility$$CreateBehaviour` passe à `AddBonusHitsToCurrentHitGroup` :

```
sources = [None, None, None, None, None, None, 'trig:1234']
           <----------- 6 coups de l'ABILITY ----------->  <- bonus GetStuckIn
```

C'est la réponse au critère binaire sans passer par le port : **le jeu émet bien un coup bonus
GetStuckIn pendant une attaque d'ability.**

### 3.b — cible à 3 hex : gate du trigger FERMÉ (second discriminant)

Même porteur, même ability, cible à la portée MAXIMALE (3 hex — `_want_far` exige les 3 hex sur la
métrique d'anneaux **et** cheby ≥ 3, pour que le montage porte sur le gate et non sur l'écart entre
les deux métriques). `!AmountIsGreater(MinDistance, Direct(2))` est faux ⇒ **aucun tirage**.

| seed | live | shipped | no_maybe / parity | always (sans gate distance) |
|---|---|---|---|---|
| 777 | `[300, 305, 332, 314, 311, 347]` | **=live** | =live | `[300, 305, 302, 367, 347, 347]` |
| 31337 | `[323, 348, 306, 373, 327, 353]` | **=live** | =live | `[323, 348, 307, 323, 353, 302, 331]` |
| 12345 | `[338, 359, 350, 310, 302, 336]` | **=live** | =live | `[338, 359, 340, 318, 336, 307, 344]` |
| 314159 | `[308, 353, 306, 344, 357, 367]` | **=live** | =live | `[308, 353, 361, 364, 367, 337]` |

⇒ **port 4/4, `always` 0/4, 4/4 discriminants.** Zéro coup `trig:1234` dans le live sur les quatre.

**Pourquoi ces deux montages ensemble** : un modèle « on roule le `Maybe` sur toute attaque
d'ability, sans regarder la distance » passe 3.a et **tombe** sur 3.b ; un modèle « on ne roule
jamais » (le port d'avant) passe 3.b et **tombe** sur 3.a ; un modèle « +k tirages » ajusté tombe
sur `parity`, qui consomme le *même* nombre de tirages à des rangs différents. Le seul énoncé qui
passe les trois est celui du §1.

Recoupement croisé qui n'était pas cherché : le live de 3.b (`far`, seed 777)
`[300, 305, 332, 314, 311, 347]` est **exactement** le contrefactuel `no_maybe` de 3.a — le même
flux RNG privé de ses tirages `Maybe`. Les deux montages se valident mutuellement.

### 3.c — TÉMOIN sans trigger after-hit : `admecRuststalker` / `CordClaw` (1122)

Ability **registrée** ⇒ rejeu par `ActiveAbilityMessage` COMPLET (pas d'appel direct).

| seed | live | shipped / no_maybe / parity | always (canal forcé) |
|---|---|---|---|
| 777 | `[1368, 1504, 1539, 1424]` | **=live** | `≠` |
| 12345 | `[1342, 1430, 1330, 1581]` | **=live** | `[1342, 1430, 1333, 1610, 1376]` |
| 314159 | `[1498, 1441, 1411, 1617]` | **=live** | `≠` |
| 88 | `[1619, 1504, 1539, 1491]` | **=live** | `≠` |

⇒ **4/4 bit-exact, les trois modèles non forcés IDENTIQUES** : le fix n'ajoute de tirage nulle part
ailleurs. Et `always` **échoue** : le témoin n'est pas un cliquet aveugle — il **détecterait** un
tirage surnuméraire.

---

## 4. Gardes

`tests/engine/runner/test_ability_after_hit_maybe_live.py` — trois tests, tous montés sur la
fixture nommée `_ability_after_hit_regime` (qui documente pourquoi ce montage est le seul
possible) au-dessus de `_pierce_floor_regime` :

1. `test_ability_vector_rolls_after_hit_maybe_live` (4 seeds) — RATCHET du port livré contre le
   live, **exact en nombre**, + DISCRIMINATION contre `no_maybe` et `parity` ;
2. `test_ability_vector_after_hit_maybe_distance_gate_live` (3 seeds) — le gate de distance :
   RATCHET + DISCRIMINATION contre `always`, et assertion que le live ne porte **aucun**
   `trig:1234` à 3 hex ;
3. `test_ability_vector_without_after_hit_trigger_bit_exact_live` (2 seeds) — TÉMOIN
   `admecRuststalker`/`CordClaw`, bit-exact sur les trois modèles non forcés **et** `always ≠ live`.

**Vue ROUGE avant le fix**, verbatim (moteur `damage_ops/ability.py` remis à `HEAD` par
`git stash`, garde inchangée) :

```
AssertionError: [close seed 31337] le port LIVRE ne reproduit pas l'attaque d'ability :
shipped=[323, 348, 306, 373, 327, 353] live=[323, 348, 307, 323, 353, 302, 331]
(sans `Maybe`=[323, 348, 306, 373, 327, 353]) -- `damage_ops/ability.py` thread-il encore
`bonus_hit_chance=_gsi` (`getstuckin_combat_chance`) a `_run_hits` et a
`execute_additional_hits` ?
assert [323, 348, 306, 373, 327, 353] == [323, 348, 30...353, 302, ...]

  At index 2 diff: 306 != 307
  Right contains one more item: 331
```

Sur ce run ROUGE, `shipped == no_maybe == parity` et **seul `always` reproduisait le live** — c'est
la signature exacte d'un canal non branché.

---

## 5. Ce qui n'est PAS couvert

* **Famille ABILITY (`AttackWithAbilityDamage`)** — le port passe `bonus_hit_chance` **sans gate de
  famille**, ce qui est l'énoncé natif lu (§1.1, `AbilityDamageOperation$$ExecuteHit` appelle bien
  `EvaluateAfterHitTriggers`) ; mais la mesure live porte sur la famille **ATTACK** seulement.
  Aucun héros `GetStuckIn` n'a d'ability de la famille ABILITY : ce volet est **mirror-offline
  fidèle, non confronté**. Le confronter exigerait un porteur qui n'existe pas au roster.
* **Coups additionnels (canal #179) sur le vecteur ability** — le threading
  `bonus_hit_chance` + `hit_index0` y est posé (même câblage que R6-b'), mais **non exercé** :
  `orksKillaKan` ne porte aucun effet à coups additionnels. La face groupes reste validée par
  R6-b' sur le vecteur normal, qui partage `execute_additional_hits` à l'identique.
* **Coups bonus d'index IMPAIR** — avec 6 coups d'arme, le premier coup bonus a l'index 6 (PAIR) et
  ne re-tire donc pas. Le re-tirage « consommé mais succès ignoré » (anti-récursion) n'est exercé
  que par le vecteur normal (R6-b', porteurs à 3 coups d'arme).
* **Branche `chance_2 = 100` de `GetBonusHitChance`** — inchangée : le port n'évalue que
  `amis_adj(caster) >= 4` ; la branche « 2+ Orks adjacents à la cible » reste non portée (gap
  documenté dans `getstuckin_combat_chance`).
* **Métrique de distance** — `getstuckin_combat_chance` utilise un proxy `cheby` là où le natif
  utilise `MinDistance` (anneaux). Gap PRÉ-EXISTANT, hors périmètre : les deux montages exigent
  l'accord des deux métriques pour ne pas le mesurer par accident.
* **Ré-évaluation per-coup de la chance** — `_gsi` est calculé une fois avant la phase d'arme
  (identique au vecteur normal ; le natif ré-évalue `GetBonusHitChance()` à chaque passage, ce qui
  ne peut changer que si l'adjacence alliée bouge PENDANT l'attaque).

---

## 6. Reproduire

```
# cible ADJACENTE (gate ouvert)
python probe_r6bp2_after_hit_maybe_ability.py --case dakka \
    --seeds 777,31337,12345,314159,88,2468,4242,20202

# cible a 3 hex (gate ferme)
python probe_r6bp2_after_hit_maybe_ability.py --case far --seeds 777,31337,12345,314159

# temoin sans trigger after-hit
python probe_r6bp2_after_hit_maybe_ability.py --case temoin --seeds 777,12345,314159,88

# gardes
python -m pytest tests/engine/runner/test_ability_after_hit_maybe_live.py -q
python -m pytest tests/engine/runner/test_additional_hits_after_hit_maybe_live.py -q
```
