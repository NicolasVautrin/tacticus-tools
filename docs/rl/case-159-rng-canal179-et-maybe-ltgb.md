# case-159 — canal #179 : les DEUX nœuds de dégât d'un descripteur, et le vrai canal de `LetTheGalaxyBurn`

Deux items, deux critères binaires, deux réponses **distinctes** :

| item | critère | réponse |
|---|---|---|
| **(a)** conso RNG du canal #179 non bit-exacte | à tirage calé, la séquence offline est-elle celle du natif — même nombre, même ordre, **mêmes bornes** ? | **NON** — l'ordre et le compte étaient justes, les **bornes** étaient fausses. **PORTÉ**, live 8/8. |
| **(b)** verdict `Maybe` de `LetTheGalaxyBurn` divergent | à tirage identique, offline et natif rendent-ils le **même verdict** ? | **OUI, identique 6/6** → le constat hérité est **PÉRIMÉ**. La divergence résiduelle est ailleurs, et elle est ici **localisée et chiffrée**. |

---

## 0. Fraîcheur — ce que l'héritage disait, et ce qu'il en reste

| constat hérité | état réel (arbre `f26e1ee`) |
|---|---|
| (b) « port : `state.rng.next_internal(0, 100) < LetTheGalaxyBurnChancePct` » | **ce code n'existe plus** : `case-o4a` l'a remplacé par `MaybeTrigger` → `NextBool(chance)` (`next_internal(1,100) <= chance`, borne 99). Le diagnostic du backlog décrivait un arbre périmé. |
| (a) « port `[2735, 2553]` vs natif `[2481, 2754]` » | chiffres **caducs** : `R6-b` a basculé le canal en roll-then-reduce (2 tirages/coup) et `R6-b''` y a threadé `bonus_hit_chance`/`hit_index0`. Re-mesuré de zéro. |
| « ordre relatif `ExecuteAdditionalHitsWithoutDamageProfileType` vs `EvaluateAfterHitTriggers` » | **tranché depuis** (`R6-b''`) : `EvaluateAfterHitTriggers` est la **dernière instruction de chaque `ExecuteHit`**, donc *dans* la boucle de coups, en amont du canal. Pas un suspect. |

---

## 1. (a) — la RE : un descripteur porte DEUX nœuds de dégât, et la face lue dépend d'un booléen

### 1.1 L'évaluateur — `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits`

Signature `(this, entities, useDisplay)`, lu verbatim (`gqfc5mff6c`) :

```
if (!d.condition.ShouldTrigger(entities))  return default              # slot 5
count  = d.countNode != null ? d.countNode.Calculate(entities) : 1     # +0x18, slot 1
amount = d.minNode.<slot 4>(entities)                                  # +0x10  noeud DISPLAY
min = max = amount
if (!useDisplay) {                                                     # <- FACE COMBAT
    min = d.amountNode.<slot 2>(entities)                              # +0x08  noeud ROLL
    max = d.amountNode.<slot 3>(entities)
}
profile = d.profileTypeNullable.HasValue ? value : -1
-> AdditionalHitsInfo{ MinMax = MinMaxDamage(min, max), amount, count, profile, ... }
```

`IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` bâtit ensuite l'AttackData
de chaque groupe par `IdunBattle.Core.HitDamage$$.ctor(min, Nullable(max))` **depuis ce
`MinMaxDamage`** — c'est donc lui, et lui seul, qui fixe les bornes du tirage de combat.

### 1.2 Les deux nœuds viennent d'un helper unique

`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, useAverage, keyMin, keyMax)`,
verbatim :

```
a = ConfigVar(keyMin, AbilityStateFromEffect(...))
b = ConfigVar(keyMax, AbilityStateFromEffect(...))
return useAverage ? DSLFactory.Average(a, b) : DSLFactory.RandomAmount(a, b)
```

et `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` l'appelle
**deux fois** — `GetMinMaxDamage(this, 0, keyMin, keyMax)` en `param_3` (nœud ROLL) et
`GetMinMaxDamage(this, 1, keyMin, keyMax)` en `param_8` (nœud DISPLAY, qui devient le `minNode`
`+0x10` : `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` pose
`param_1[2] = param_8 != 0 ? param_8 : param_3`).

### 1.3 Qui passe `useDisplay = false`

- **COMBAT** : `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamage
  ProfileType` appelle `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFrom
  EffectsInternal` avec l'octet **explicitement mis à zéro** (`in_stack & 0xffffff00`) — c'est
  l'instruction qui tranche. Le booléen redescend jusqu'au slot 0x23 de l'effet, c'est-à-dire
  jusqu'à `BaseEffect$$AdditionalHits`.
- **PRÉDICTION** : `IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditionalHitsFromEffects
  ForPrediction` → `…$$GetAdditionalHitsFromEffects` → cellule **dégénérée** `(amount, amount)`,
  que le pipeline de prédiction étale ensuite (`DamageCalculations$$CalculateDamageSpread`, ±20 %).

⇒ **la face COMBAT tire dans `[ConfigVar(keyMin), ConfigVar(keyMax)]`**, jamais dans
`Average ± 20 %`.

### 1.4 Le fork de port

`_BaseFleshmetalGunsEffect.additional_hit_groups` ne rendait que `{"count", "amount", "profile"}`
avec `amount = (minDmg + maxDmg)/2`. `execute_additional_hits` retombait donc sur son repli
`get_base_damage_fix64(amount, spread_pct=20)` : **une face native (le nœud ROLL) purement
absente du port**. Le résidu (a) n'était donc ni un décalage de flux ni un ordre — c'était
**l'étage BORNES**.

Contrat désormais explicite (`BaseEffect.additional_hit_groups`) : `min`/`max` = nœud ROLL
(lu par le COMBAT), `amount` = nœud DISPLAY (lu par la PRÉDICTION). Les deux clés **coexistent** ;
la précédence de `execute_additional_hits` (`min`/`max` d'abord) **est** le mirror du gate
`useDisplay`.

---

## 2. (a) — la mesure

Montage : `blackObliterator` (Volk, passif `FleshmetalGuns`) attaque **à distance** (le trigger du
canal est `IsRangedAttack`) un témoin `necroWarden` (aucun trait mordant le canal de coups), board
`MC1_67`, `--crit 0,0 --block-target 0,0 --hp-target 90000`, caster **jamais déplacé au tour de
l'attaque** (un `move` poserait `UnitFlag.Moved` → ×1,25 `HeavyWeapon_ExtraDmg` de mesure — défaut
qui a fait échouer la première passe). `state.rng` calé par `dumpRng` juste avant le cast.

La variante active du cycle est pilotée par `UnitTurnsStarted(Self) mod 3`
(`IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour`) : le
probe `endturn` jusqu'à ce que Volk porte l'effet voulu.

**Pourquoi WarpHail** : c'est la seule variante dont la paire `[minDmg, maxDmg]` n'est **pas** une
paire ±20 % exacte autour de sa moyenne — donc la seule où les deux modèles s'écartent franchement.

| variante (mult 180) | natif = nœud ROLL | port = `amount ± 20 %` | largeur |
|---|---|---|---|
| Melta | `[997, 1496]` | `[997, 1495]` | 500 vs 499 |
| WarpHail | `[698, 1096]` | `[718, 1076]` | **399 vs 359** |

### 2.a — WarpHail (axe discriminant)

| seed | groupe live | port LIVRÉ (nœud ROLL) | contrefactuel `amount ± 20 %` |
|---|---|---|---|
| 777 | `[950, 1179]` | **=live** | `[1035, 1335]` |
| 12345 | `[990, 1316]` | **=live** | `[1265, 1140]` |
| 314159 | `[923, 1025]` | **=live** | `[1043, 1135]` |
| 88 | `[1246, 1135]` | **=live** | `[1039, 951]` |
| 2468 | `[913, 985]` | **=live** | `[953, 1271]` |
| 31337 | `[1198, 1321]` | **=live** | `[1236, 1339]` |

⇒ **port 6/6, contrefactuel 0/6, 6/6 montages discriminants.**

### 2.b — Melta (2ᵉ variante, écart FAIBLE)

| seed | groupe live | port LIVRÉ | contrefactuel |
|---|---|---|---|
| 777 | `[1488, 1492]` | **=live** | `[1063, 1392]` |
| 12345 | `[1076, 1122]` | **=live** | `[1205, 1458]` |

⇒ **2/2 vs 0/2.** Ce second montage compte : une largeur de 500 vs 499 suffit à décorréler
totalement les valeurs tirées (le modulo n'est pas le même), donc un fix « ajusté au scalaire » sur
WarpHail s'y serait trahi. **Total 8/8 contre 0/8.**

### 2.c — le budget de tirages, mesuré (décomposition par étage)

Compte de `genrand_int32` natif = re-simulation du Mersenne Twister entre deux `dumpRng` (le
nombre de pas EST le nombre de tirages) ; côté port, compteur sur `genrand_int32`.

| régime | natif | offline | décomposition offline |
|---|---|---|---|
| `Maybe` armé (777, 314159, 88, 2468) | **13** | **12** | 1 `Maybe` + 7 coups d'arme + 4 groupe (2 coups × 2) |
| `Maybe` non armé (12345, 31337) | **12** | **11** | 1 `Maybe` + 6 coups d'arme + 4 groupe |

L'écart est **constant à +1, indépendant du régime** : c'est le tirage de dégât de
`DespoiledGround` (effet 1476), le **volet 2 non porté** du kit (déjà documenté dans
`runner/operations/triggers/loki/let_the_galaxy_burn.py`). Il tombe **après** le groupe (dernier
event live, `Effect_Type: 1476`, profil 15) — d'où un flux parfaitement aligné en amont, ce qui est
précisément ce qui rend la mesure des bornes valide.

---

## 3. (b) — le verdict `Maybe` NE diverge PAS ; c'est le CANAL de matérialisation qui diffère

### 3.1 Le verdict, mesuré

Sur les 6 montages ci-dessus, le nombre d'événements de dégât avant le groupe est **7 quand le port
arme et 6 quand il n'arme pas — et le natif fait exactement le même partage** (7/7 sur 777, 314159,
88, 2468 ; 6/6 sur 12345, 31337). Le `Maybe(33)` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` rend
donc **le même booléen des deux côtés, 6/6**, sur un flux RNG calé. Le budget de tirages le
confirme indépendamment (1 tirage de `Maybe` des deux côtés, cf. §2.c).

**Le constat hérité (« le verdict diverge ») est PÉRIMÉ** : il datait d'avant `case-o4a`, qui a
remplacé `next_internal(0,100) < pct` (borne 100) par la primitive native `NextBool(chance)`
(`next_internal(1,100) <= chance`, borne 99).

### 3.2 Ce qui diverge réellement — RÉSIDU NEUF, localisé et chiffré

`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`, lu verbatim :

```
cond   = get_OwnerIsCaster & ( LetTheGalaxyBurnAbility$$TargetHasTileEffect
                             | IsPersistentData(0x5ca, Self@0x148, Get(<statique>)) )
EffectAdditionalHits$$Create(
    condition   = cond,
    amountNode  = FirstHitInCurrentAttackDamageRange(),     # +0x08  ROLL
    tag         = 0,                                        # +0x34
    profileType = -1                (Nullable NULL),        # +0x28
    countNode   = 0                 (-> defaut 1),          # +0x18
    minNode     = FirstHitInCurrentAttackDamageRange(),     # +0x10  DISPLAY (2e appel)
    profileNode = 0)
```

⇒ le « +1 coup » de `LetTheGalaxyBurn` est **un groupe du canal #179**, pas un `+1` de la formule
de coups. Le port, lui, l'implémente en `create_effect_hits_bonus_for_attack` (un coup d'**ARME**
de plus, tiré dans la cellule d'arme) : **un fork de port** — une face native, deux façades
offline.

**Signature mesurée, sur deux cellules d'arme différentes** :

| variante | cellule d'ARME réduite | `round((min+max)/2)` | 7ᵉ event LIVE |
|---|---|---|---|
| WarpHail | `(906, 1359)` | **1133** | **1133** sur 777, 314159, 88, 2468 |
| Melta | `(725, 1087)` | **906** | **906** sur 777 |

Le coup surnuméraire natif est donc une **constante déterministe** — la **moyenne exacte** de la
cellule d'arme (`Fix64.Round`, AwayFromZero : 1132,5 → 1133) — là où le port tire une valeur
aléatoire dans cette même cellule (906 / 908 / 967 / 1265 / 851 selon la seed). Le port consomme
le **bon nombre** de tirages (1), ce qui explique que le flux reste aligné et que le groupe #179
aval reste bit-exact : l'erreur est **purement de valeur**, bornée à un coup par attaque.

Mécanique native cohérente avec ce chiffre : `FirstHitInCurrentAttackDamageRange` rend le
`HitDamage` du **premier coup de l'attaque courante**, lequel est **dégénéré** pour une attaque
normale (documenté : « attaque normale → struct dégénéré → 1 tirage/coup »). D'où, dans
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` : `HitDamage$$GetDamage` **gate
`min == max` → 0 tirage**, la réduction produit une cellule dégénérée, et le seul tirage consommé
est le `RandomlyResolveMinMaxDamage` (slot 8) **gaspillé** — 1 tirage, valeur déterministe. Le
compte de §2.c (13 = 1 + 6 + **1** + 4 + 1) ne ferme qu'avec ce modèle.

**Non porté ici** : le corriger déplace `LetTheGalaxyBurn` de la formule de coups vers le canal
#179 **sur les DEUX faces** (la prédiction native le reçoit aussi comme groupe, via
`AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction`) et touche `attack_hits_formula`,
`hits_bonus_from_effects` et `playbook/prediction/normal_attack.py` — c'est un cas à part entière,
pas l'item (b) tel que soumis (dont le critère est tranché : verdict identique). Le résidu est
inscrit au backlog avec ce chiffrage.

### 3.3 ⚠ Tension à lever avant de porter — un 2ᵉ datapoint dit l'INVERSE sur l'autre vecteur

`case-bl-1029-1020` §5.4 rapporte `blackHaarken` (lui aussi porteur du trait 1058)
**bit-exact per-coup dans le régime où le `Maybe` ARME** (`{77:[1738,1979,1846]}`), c'est-à-dire
avec le modèle « +1 coup d'ARME » du port — mais sur le vecteur **ABILITY**
(`HeraldOfTheApocalypse`), là où §3.2 mesure le vecteur **NORMAL**.

Les deux ne sont pas nécessairement contradictoires : `FirstHitInCurrentAttackDamageRange` rend la
`HitDamage` **du premier coup de l'attaque courante**, et cette `HitDamage` n'est pas la même selon
le vecteur — **dégénérée** pour l'attaque normale (reduce-then-roll), **non dégénérée** pour
l'ability bounds-mode famille ATTACK (roll-then-reduce). Le groupe LTGB serait donc déterministe
sur l'un et rouleur sur l'autre, ce qui rendrait le port fortuitement juste côté ability.

**C'est une HYPOTHÈSE, non mesurée.** Quiconque porte (b) doit monter le montage **croisé** (les
deux vecteurs, le même porteur si possible) et re-jouer les DEUX gardes ; ne pas porter sur la
seule mesure du vecteur normal.

---

## 4. Ce qui n'est PAS couvert

- **R6-c — les descripteurs `amount` restants.** Le même étage est encore faux pour les
  descripteurs dont le nœud ROLL n'a pas été câblé. RE **lue** ici, prescription exacte :
  - `CyclicIonBlaster_AdditionalHitsEffect$$CreateAdditionalHits` (verbatim) —
    `rollNode = ConditionalAmount(cond, RandomAmount(Sum(minDmg, extraDmg), Sum(maxDmg, extraDmg)),
    RandomAmount(minDmg, maxDmg))`, `displayNode = ConditionalAmount(cond, Sum(minDmg, extraDmg),
    minDmg)`, `cond = HasEffect(target@0x178, 0x462 Markerlight, 1, 6) | HasTrait(target@0x178,
    5 Mechanical)`. ⇒ bornes COMBAT = `[minDmg(+extraDmg), maxDmg(+extraDmg)]` ; le port rend
    `amount = minDmg` seul, donc étale ±20 % **autour du minimum** (à mult 180 : `[479, 719]` au
    lieu de `[599, 898]`) — exactement la signature R6-c « groupe live au-dessus de la borne haute
    du port », mesurée sur `tauCrisis`.
  - `FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits` et
    `ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits` (verbatim) : leur `param_8`
    est **0**, donc `minNode` retombe sur `amountNode`, et celui-ci est un **scalaire**
    (`ConfigVar(0xb)` / `ConfigVar(8)`) — pas un `RandomAmount`. Leurs bornes COMBAT sont donc
    **dégénérées** `[v, v]`, ce qui change **aussi la consommation** (`GetDamage` gate `min == max`
    → 0 tirage). Correction plus lourde que les deux précédentes, et non mesurée.

  Aucune de ces trois n'a été portée : pas de confrontation live montée sur leur porteur → pas de
  port spéculatif.
- **Le volet `DespoiledGround`** (effet 1476 + `DespoiledGround_ExtraDamagePct` 1478) reste non
  porté ; il coûte **1 tirage** au natif, en fin d'attaque (mesuré, §2.c). Inchangé par ce cas,
  mais désormais chiffré.
- **Les groupes `predefined`** (SquigHound, CordClaw, FearOfTheUnseen, InfernalPacts,
  MasterAnnihilator) : leur face PRÉDICTION passe par `predefined MinMaxDamage(min, max)` alors que
  le natif y rendrait une cellule dégénérée `(slot4(minNode), slot4(minNode))` étalée ensuite à
  ±20 %. Numériquement indistinguable **parce que leurs paires sont des paires ±20 % exactes autour
  de leur moyenne** (constat déjà écrit dans `_BaseFleshmetalGunsEffect`). Non touché : le changer
  sans montage discriminant serait spéculatif.
- **La variante Flame du cycle** n'a pas été mesurée (Melta et WarpHail suffisent à encadrer les
  deux régimes : paire quasi symétrique et paire asymétrique).

---

## 5. Reproduire

```
# mesure (a) -- variante ASYMETRIQUE, l'axe discriminant
python probe_159_ah_bounds.py --seeds 777,12345,314159,88,2468,31337

# 2e variante (ecart FAIBLE : largeur 500 vs 499)
python probe_159_ah_bounds.py --seeds 777,12345 --variant Melta

# gardes
python -m pytest tests/engine/runner/test_additional_hits_amount_bounds_live.py -q
```

Vue **ROUGE** obtenue en remettant `engine/entities/effects/loki/hits.py` à `HEAD`
(`git stash push -- <fichier>`) : **4 tests rouges** sur 5 (le 5ᵉ est la garde de FLUX, verte des
deux côtés par construction), verbatim :

```
AssertionError: variante Melta : shipped=[1205, 1458] live=[1076, 1122] (display=[1205, 1458])
```

Non-régression rejouée : `test_additional_hits_roll_order_live.py` +
`test_additional_hits_rounding_live.py` + `test_additional_hits_after_hit_maybe_live.py`
(15 passed), `test_ability_hits_channel_live.py` + `test_let_the_galaxy_burn_live.py` (8 passed).
