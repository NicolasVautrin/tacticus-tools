# R6-b' — le `Maybe` after-hit est évalué sur les coups d'un GROUPE additionnel

**Question binaire.** Le `Maybe(chance)` d'un trigger after-hit (type `GetStuckIn`) est-il évalué
sur les coups d'un **groupe de coups additionnels** (#179/#202-B), comme il l'est sur les coups
d'**arme** ?

**Réponse : OUI.** Le compteur d'index n'est pas local à la série de coups — c'est un champ de
l'`OngoingAttack`, **continu à travers les sous-opérations** d'une même attaque. Le flux RNG des
groupes était donc décalé du nombre de tirages correspondant.

---

## 1. L'énoncé natif, établi au décompilé (`gqfc5mff6c`)

### 1.1 L'index de coup appartient à l'ATTAQUE, pas à la série

```
IdunBattle.Core.OngoingAttack$$.ctor
    *(uint64*)(this + 0x30) = 0        # +0x30 = index de COUP, +0x34 = compteur de SÉRIES
```

L'objet est créé et **poussé une seule fois par attaque** :

```
IdunBattle.Operations.StartAttackOperation$$Execute
    ongoing = new OngoingAttack(attackerId, damageProfiles)
    <slot 0x1e de IBattleState>(ongoing)        ->  IdunBattle.Core.MatchState$$StartAttack
                                                    = Stack<OngoingAttack>.Push(MatchState+0x60)
```

et **toute sous-opération le récupère par `Peek`** :

```
IdunBattle.Operations.ADamageOperation$$GetCurrentAttackOrDefault
  -> IdunBattle.Core.Services.BattleQuery$$GetCurrentAttackOrDefault
       if (!HasCurrentAttack) return new OngoingAttack();      # jamais atteint pendant une attaque
       return GetCurrentAttack();
  -> IdunBattle.Core.MatchState$$GetCurrentAttack = Stack<OngoingAttack>.Peek(MatchState+0x60)
```

`IdunBattle.Core.MatchState$$FinishAttack` = `Pop()`. Rien d'autre n'écrit `+0x30` que :

```
IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit
    *(int*)(currentAttack + 0x30) += 1          # APRÈS CHAQUE coup
    ...
```

et `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` **relit `currentAttack+0x30` FRAIS**
à chaque tour de boucle (le compteur de boucle, lui, est un objet séparé) :

```
while (loop.i < hits) {
    hitIndex = *(int*)(currentAttack + 0x30);              # relu à CHAQUE tour
    ExecuteHit(&ret, this, hitIndex, attacker, target, ...);
    UpdateHitGroupAfterHit(this, hitGroup);
    UpdateCurrentAttackAfterHit(this, currentAttack, ret);  # +0x30 += 1
    ...
    loop.i += 1;
}
*(int*)(currentAttack + 0x34) += 1;                        # fin de SÉRIE
```

### 1.2 Le trigger `On(8)` part de CHAQUE `ExecuteHit`, inconditionnellement

`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` est la **dernière** instruction
d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (xref `UNCONDITIONAL_CALL` ; les deux
autres appelants sont `AbilityDamageOperation$$ExecuteHit` et `MachineDamageOperation$$ExecuteHit`) :

```
EvaluateAfterHitTriggers(this, &hitInfo, attacker, target,
                         hitIndex /* = param_3 d'ExecuteHit */, isCrit, dmg, damageProfile);
return ret;
```

et son corps construit l'`AbilityEntities` du contexte de trigger :

```
Nullable<int>.ctor(&nHitIndex, &param_5)                 # param_5 = hitIndex
AbilityEntities..ctor(&ae, ..., /*param_29*/ nHitIndex, ...)
        # param_29 -> param_1[0x22]  ==  AbilityEntities + 0x110
FUN_180026490(0x50, ..., 0x3d, ae)   # On(0x3d) — seulement si isCrit
FUN_180026490(0x50, ..., 8,    ae)   # On(8)    — TOUJOURS
```

et `IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$Calculate` lit **exactement** ce champ :

```
Nullable<int>.GetValueOrDefault(param_2 + 0x110, &out) ; return out;
```

### 1.3 `GetStuckIn` : trigger et behaviour

```
IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger
    On(8, 1)
      & AmountIsOdd(CurrentHitIndex())
      & get_OwnerIsCaster
      & !AmountIsGreater(MinDistance(caster, target), Direct(2))

IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateBehaviour
    Maybe( AddBonusHitsToCurrentHitGroup(..., AbilityOrEffect(0x4d2)), GetBonusHitChance() )
```

Le `Maybe` (`IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`) consomme **1
`NextBool(chance)` à chaque passage du trigger** — donc à chaque coup d'index IMPAIR, quelle que
soit la sous-opération qui l'émet.

### 1.4 La voie GROUPES partage le même `OngoingAttack`

```
IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute
  -> AdditionalHitsFromEffects$$GetAdditionalHitsFromEffects / $$GetAdditionalHitsData
  -> pour chaque descripteur : slot 0x3c  Core.Services.OperationProcessor$$AttackDamage
       -> IdunBattle.Operations.AttackDamageOperation$$Execute
            currentAttack = GetCurrentAttackOrDefault(...)   # <- Peek : LE MÊME OBJET
            hitGroup      = SetupHitGroup(...)               # <- un hitGroup PAR sous-opération
            ExecuteHits(this, msg, currentAttack, hitGroup, hits, ...)
```

⇒ **l'index ne repart PAS de 0** pour un groupe. C'est la réponse au critère binaire.

### 1.5 Ce qu'un succès `Maybe` produit — la question laissée ouverte par R6-b

```
IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour$$Execute
    unit = <sélecteur>            # OwnerIsCaster -> le CASTER
    List.Add(unit + 0xf0, ValueTuple(abilityOrEffect, count))

IdunBattle.Operations.ADamageOperation$$UpdateHitGroupAfterHit    # après CHAQUE coup
    List.AddRange(hitGroup + 0x58, attacker + 0xf0) ; attacker+0xf0.Clear()

IdunBattle.Operations.AttackDamageOperation$$Execute              # fin de l'opération
    copy = new List(hitGroup + 0x58)                 # COPIE -> anti-récursion
    foreach (ability, count) in copy:  ExecuteHits(this, msg, currentAttack, hitGroup, count, ...)
```

Le hit-group est créé **par sous-opération** (`SetupHitGroup`) : un succès pendant un groupe défère
donc un coup bonus **dans ce groupe**, exécuté avant que la sous-opération ne rende la main.
Le gate `msg+0x50 == 0 && currentAttack+0x34 == 1` ne concerne PAS cette boucle — il ne garde que
`ExecuteAdditionalHitsWithoutDamageProfileType`, canal distinct.

**Confirmation live, côté jeu** : les events de dégât portent
`Additional_Hit_TriggeredAbility_Source: 1234` = `0x4d2`, le littéral EXACT passé par
`CreateBehaviour` — et on l'observe sur un coup émis **après** les deux coups
`Additional_Hit_Effect_Source: 1292` (SquigHound), sous le **même** `Attacker_Id` :

```
sources = [None, None, 'eff:1292', 'eff:1292', 'trig:1234']
           <-- arme -->  <-- groupe SquigHound -->  <-- bonus GetStuckIn DANS le groupe
```

---

## 2. Le port

Trois éditions, **un seul site d'évaluation du `Maybe`** (le fork de port avait déjà coûté #110) :

* `engine/runner/operations/damage_hits.py::_run_hits` — nouveau paramètre `hit_index0`
  (défaut 0) : la boucle de base indexe `hit_index0 + i`, les coups bonus continuent à
  `hit_index0 + hits + j`, et le retour porte
  `next_hit_index = hit_index0 + hits + base_bonus` (mirror : `UpdateCurrentAttackAfterHit`
  incrémente après CHAQUE `ExecuteHit`, coups bonus compris) ;
* `engine/runner/operations/additional_hits.py::execute_additional_hits` — nouveaux paramètres
  `bonus_hit_chance` / `hit_index0`, **threadés de groupe en groupe** (`hit_index = r["next_hit_index"]`) ;
* `engine/runner/operations/damage_ops/normal.py` — câblage :
  `bonus_hit_chance=_gsi, hit_index0=r["next_hit_index"]`, où `_gsi` est **le même**
  `getstuckin_combat_chance` que la phase d'arme et `r` le résultat de `_run_hits`.

`bonus_hit_chance is None` (attaquant sans `GetStuckIn`, ou cible à plus de 2 hex) ⇒ **strict
no-op**, aucun tirage supplémentaire nulle part.

---

## 3. Mesure — `probe_r6bp_after_hit_maybe_groups.py`

Régime PERÇAGE-DOMINANT (`--armor-target 6000`, fixture `_pierce_floor_regime`), crit et block
neutralisés, board `MC1_67`. Deux modèles rejoués sur le **même état** et le **même flux RNG** :
le port **livré**, et le contrefactuel `additional_hits_variant("roll_then_reduce", None)` — qui
ignore volontairement `bonus_hit_chance`, donc **EST** le port d'avant R6-b'.

La comparaison est **exacte en nombre** : les events live sont filtrés sur `Attacker_Id`, ce qui
écarte l'attaque du grot spawné par `SquigHound` (~500 de dégât, qui suit le groupe dans le même
flux).

### 3.a — 3 coups d'arme : `orksRuntherd` vs `ultraApothecary`

| seed | coups d'arme émis | groupe live | port livré | contrefactuel |
|---|---|---|---|---|
| 777 | 3 (0 bonus) | `[32, 37]` | **`[32, 37]`** | `[32, 39]` |
| 314159 | 3 (0 bonus) | `[27, 33]` | **`[27, 33]`** | `[27, 35]` |
| 12345 | 3 (0 bonus) | `[38, 35, 36]` | **`[38, 35, 36]`** | `[38, 35]` |
| 88 | 4 (1 bonus) | `[30, 37, 35]` | **`[30, 37, 35]`** | `[30, 37]` |
| 31337 | 4 (1 bonus) | `[30, 34]` | **`[30, 34]`** | `[30, 34]` |
| 2468 | 4 (1 bonus) | `[30, 38]` | **`[30, 38]`** | `[30, 38]` |
| 20202 | 3 (0 bonus) | `[38, 28]` | **`[38, 28]`** | `[38, 38]` |
| 4242 | 3 (0 bonus) | `[37, 34, 35]` | **`[37, 34, 35]`** | `[37, 30]` |

⇒ **port 8/8, contrefactuel 2/8, 6/8 montages discriminants.** Régimes de parité : {0 bonus: 5,
1 bonus: 3}.

### 3.b — 2 coups d'arme (parité INVERSÉE) : `orksRuntherd` vs `templSwordBrother` (trait `Parry`)

`Parry` retire 1 coup en mêlée (`create_effect_hits_malus_for_defense`) ⇒ 2 coups d'arme, donc la
**conclusion s'inverse** : sans coup bonus d'arme le groupe démarre à l'index **2 (PAIR)**, avec
coup bonus il démarre à **3 (IMPAIR)**.

| seed | coups d'arme émis | groupe live | port livré | contrefactuel |
|---|---|---|---|---|
| 777 | 2 (0 bonus) | `[32, 34, 28]` | **`[32, 34, 28]`** | `[32, 34]` |
| 314159 | 2 (0 bonus) | `[36, 36]` | **`[36, 36]`** | `[36, 36]` |
| 12345 | 2 (0 bonus) | `[30, 39, 35]` | **`[30, 39, 35]`** | `[30, 39]` |
| 88 | 3 (1 bonus) | `[39, 32, 29]` | **`[39, 32, 29]`** | `[39, 30]` |
| 31337 | 3 (1 bonus) | `[28, 37, 29]` | **`[28, 37, 29]`** | `[28, 30]` |
| 2468 | 3 (1 bonus) | `[29, 34]` | **`[29, 34]`** | `[29, 30]` |

⇒ **port 6/6, contrefactuel 1/6, 5/6 montages discriminants.** Régimes : {0 bonus: 3, 1 bonus: 3}.

**Pourquoi ces deux montages ensemble** : un modèle « +1 tirage avant le 2ᵉ coup du groupe » passe
3.a sur les seeds à 3 coups d'arme et **tombe** sur 3.b aux mêmes seeds. Le seul énoncé qui passe
les deux est celui du §1 — l'index CONTINU.

### 3.c — TÉMOIN sans trigger after-hit : `admecRuststalker` / `CordClaw`

| seed | groupe live | port livré | contrefactuel |
|---|---|---|---|
| 777 | `[1266, 1222]` | **=live** | **=live** |
| 12345 | `[961, 1294]` | **=live** | **=live** |
| 314159 | `[1007, 1092]` | **=live** | **=live** |
| 88 | `[977, 1256]` | **=live** | **=live** |

⇒ **4/4 bit-exact, les deux modèles IDENTIQUES** : le fix n'ajoute de tirage nulle part ailleurs.

### 3.d — Le modèle hérité était une PARAMÉTRISATION, pas l'énoncé

R6-b avait mesuré « k = 1 tirage de plus si le nombre de coups d'arme émis est IMPAIR », validé
5/5. Ce modèle est **numériquement correct sur le préfixe à 2 coups**, mais il est
**sous-déterminé** : il ne dit rien du 3ᵉ coup du groupe, que le natif émet quand le `Maybe` du
groupe RÉUSSIT (seeds 12345/88/4242 en 3.a, 777/12345/88/31337 en 3.b — le port livré le produit
avec la bonne valeur ET au bon rang, le contrefactuel ne le produit pas du tout). L'énoncé qui
couvre les deux est celui du §1, lu au décompilé, pas ajusté.

---

## 4. Gardes

`tests/engine/runner/test_additional_hits_after_hit_maybe_live.py` — deux tests à **parité
inversée** (4 seeds sur `ultraApothecary`, 3 sur `templSwordBrother`), chacun avec :
(1) RATCHET du port livré contre le live, **exact en nombre** ; (2) DISCRIMINATION — le
contrefactuel d'avant R6-b' doit ÉCHOUER, sinon la garde est aveugle.

**Vue ROUGE avant le fix**, verbatim (moteur remis à `HEAD`, garde inchangée) :

```
AssertionError: le port LIVRE ne reproduit pas le groupe : shipped=[32, 39] live=[32, 37]
(contrefactuel sans `Maybe` dans les groupes=[32, 39]) -- `execute_additional_hits`
d'`operations/additional_hits.py` roule-t-il encore le `Maybe` after-hit (`bonus_hit_chance`)
avec l'index CONTINU de l'attaque (`hit_index0`) ?
assert [32, 39] == [32, 37]
  At index 1 diff: 39 != 37
```

```
AssertionError: le port LIVRE ne reproduit pas le groupe : shipped=[32, 34] live=[32, 34, 28]
(contrefactuel sans `Maybe` dans les groupes=[32, 34]) -- ...
assert [32, 34] == [32, 34, 28]
  Right contains one more item: 28
```

Le témoin sans trigger est déjà gardé par
`test_additional_hits_roll_order_live.py::test_additional_hits_wasted_resolve_live`
(`admecRuststalker`), qui doit rester vert.

---

## 5. Ce qui n'est PAS couvert

* **Vecteur ABILITY** — `damage_ops/ability.py` ne passe `bonus_hit_chance` **ni** aux coups d'arme
  **ni** aux groupes, alors que `GetStuckInAbility$$CreateTrigger` n'a **aucun** gate
  `IsNormalAttack` : une ability de la famille ATTACK (`AttackWithAttackDamage`) castée par un
  porteur `GetStuckIn` à ≤ 2 hex roule le `Maybe` côté natif. Laissé ouvert **exprès** : porter la
  seule face groupes sans la face arme serait incohérent, et la face arme est un chantier distinct
  (le commentaire de `ability.py` l.362-365 l'annonce déjà comme un choix).
* **Branche `chance_2 = 100` de `GetBonusHitChance`** — le port n'évalue que
  `amis_adj(caster) >= 4` ; la branche i2 « 2+ Orks adjacents **à la cible** » reste non portée
  (gap déjà documenté dans `getstuckin_combat_chance`, hors périmètre).
* **Ré-évaluation per-coup de la chance** — `_gsi` est calculé une fois avant la phase d'arme et
  réutilisé pour les groupes. Le natif ré-évalue `GetBonusHitChance()` à chaque passage du trigger ;
  la valeur ne peut changer que si l'adjacence alliée change PENDANT l'attaque (aucun montage ne
  l'exerce).
* **`crit` sur les coups d'un groupe** — inchangé (`crit_chance=0, crit_enabled=False`).
* **R6-c** (bornes COMBAT des groupes `amount`) et les deux points « à confirmer live » de
  `case-202` §7 (gate `hp > 0`, `failed_block` per-attaque) restent ouverts, inchangés.

---

## 6. Reproduire

```
# 3 coups d'arme (parite normale)
python probe_r6bp_after_hit_maybe_groups.py --case squig \
    --seeds 777,314159,12345,88,31337,2468,20202,4242

# 2 coups d'arme (parite INVERSEE, cible Parry)
python probe_r6bp_after_hit_maybe_groups.py --case parry \
    --seeds 777,314159,12345,88,31337,2468

# temoin sans trigger after-hit
python probe_r6bp_after_hit_maybe_groups.py --case temoin --seeds 777,12345,314159,88

# gardes
python -m pytest tests/engine/runner/test_additional_hits_after_hit_maybe_live.py -q
python -m pytest tests/engine/runner/test_additional_hits_roll_order_live.py -q
```
