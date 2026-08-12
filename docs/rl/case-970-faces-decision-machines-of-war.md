# #970 — six faces DÉCISION `NonComparable`, et le refus « MoW » qui les bloquait toutes

## 1. Le fait qui commande tout le lot : les trois porteurs sont des MACHINES OF WAR

| porteur | `traits` | actives |
|---|---|---|
| `tauBroadside` | `['MachineOfWar']` | `1160 HeavyRailRifle`, `1161 TwinSmartMissileSystem` |
| `orksRukkatrukk` | `['MachineOfWar']` | `1200 SquigLaunchas`, `1201 SquigMine` |
| `ultraDreadnought` | `['MachineOfWar']` | `1158 DutyEternal`, `1159 MacroPlasmaIncinerator` |

La tranche a été ouverte avec, en tête, un refus écrit dans `engine/playbook/nonattack.py` :
`DutyEternalPlaybook$$GetUseProbability` n'est pas câblé parce que « son porteur est une Machine of
War, hors face DÉCISION », et « un crochet sans porteur serait du code spéculatif ». Ce refus
s'appliquait de fait aux **six**.

**Il est PÉRIMÉ, et c'est mesuré, pas argumenté** :

1. `IdunBattle.AI.Tactics.DefaultMachineTactic$$.ctor` pose `@tactic+0x60 =
   GetDefaultActiveAbilityActionGenerators(this)` — les **mêmes** cinq `NonComparableGenerator` par
   tier que le tactic unité, seulement privés du `MovementActionGenerator`. Le mirror
   (`engine/ai/tactic.py`) le porte déjà : `[NonComparableGenerator(p) for p in NC_PRIORITY_TIERS]`.
2. `1187 ThriceBlessedConflagration` (`adeptExorcist`, MoW) est une face DÉCISION `NonComparable`
   **déjà portée et confrontée** par cette voie.
3. `probe_970` fait sortir `1161` du chemin MoW **réel** (`build_machine` +
   `DefaultMachineTactic`), avec une contre-épreuve qui mord.

Ce qui subsiste comme raison de ne pas câbler le crochet de 1158 est donc « **pas de
consommateur** » (1158 n'est pas portée), pas « pas de porteur ». La docstring de `nonattack.py`
est corrigée en ce sens.

## 2. La contrainte structurelle qu'une MoW impose au port

Lue au décompilé, **confirmée live** (`reach_nc=0, origin=None` sur les deux porteurs mesurés) :

- `DefaultMachineTactic.<CalculateNextActionForUnit>d__5$$MoveNext` appelle
  `gen.GenerateActions(machine, NullPosition(), new OrderedSet())` — position **nulle**, ensemble
  de tuiles **vide** ;
- une MoW ne bouge JAMAIS (`<CalculateMovementForUnit>d__8$$MoveNext` rend toujours une liste vide).

⇒ **aucun playbook de MoW ne peut hériter `_PlanTargetPlaybook`** : son `generate_candidates`
boucle sur `ctx.reach_nc`, vide ici, donc la feuille serait morte — enregistrée et inerte. Le
patron est celui de `ThriceBlessedConflagrationPlaybook` : dériver `NonComparablePlaybook`, lire
`fromHere` (`ctx.ability_targets`), émettre `to = None`. Le premier jet de cette tranche avait
écrit 1161 sur `_PlanTargetPlaybook` ; la lecture de `tactic.py` l'a corrigé avant tout test.

## 3. RE des six — table

| id | `MIN_UTILITY` | utilité | domaine | gate propre |
|---|---|---|---|---|
| `1158 DutyEternal` | 1 (`.cctor`) | `1 + Σ_{t ∈ ThreeTileUnitSpawnShape(T)} Σ_{u ∈ GetSurroundingUnits(t,2)} (10 si GetDistance(u,t) < 2 sinon 1)` | tuile | slot 5, rampe `((turnsFinished − initialCooldownTurns + 1)·33)/100` |
| `1159 MacroPlasmaIncinerator` | 1 (`.cctor`) | `1 + |zone| + Σ_{t ∈ zone, libre} |GetAdjacentEnemies(t, caster)|` | tuile | — |
| `1160 HeavyRailRifle` | 1 (`.cctor`) | `IsMachine(T) ? (NextBool(50) ? Fix64(int.MaxValue) : 1) : CalculateUtilityFromDamageEvent(T, avg(GetDamage@1260), profile, hits)` | unité | — |
| `1161 TwinSmartMissileSystem` | **aucune** | `Fix64(1)`, cible tirée par `NextElement` | unité | — |
| `1200 SquigLaunchas` | 1 (`.cctor`) | `Fix64(rng.Next(1, 10))` | tuile | `FulfillsSummonCriteria` (arbre DSL) |
| `1201 SquigMine` | 1 (`.cctor`) | `1 + |GetAdjacentEnemies(T, caster)|` | tuile | `IsFreeTile(T)` |

Les six sont des `NonComparablePlaybook\`1` — **base LUE dans `frida/classes.tsv`**. Leur `.ctor`
est nommé `ComparablePlaybook<...>$$.ctor` par ghidra (corps gshared dédupliqué) : le piège de
#487-r1 / #945 / #957, qui se reproduit à l'identique sur les six.

Recensement fait **au bloc d'adresses** (`ghidra/functions.tsv`), jamais par grep : chaque classe
a ses corps **contigus** — 4 pour `HeavyRailRifle` (avec `ShouldPreferMachine`) et `DutyEternal`
(avec `GetUseProbability`), 3 pour les quatre autres. Rien n'y est fondu.

### 3.1 Le champ `this+0x30` est l'`IPseudoRNG` — établi par recoupement

Trois call-sites, **même champ et même `Il2CppClass*`** :

- `BasePlaybook$$ShouldEvaluate` → `<slot 4 = NextBool>(prob)` ;
- `HeavyRailRiflePlaybook$$ShouldPreferMachine` → `<slot 5 = NextBool>(50)` ;
- `SquigLaunchasPlaybook` → `<slot 2 = Next>(1, 10)` ; `TwinSmartMissileSystemPlaybook` →
  `<slot 6 = NextElement>(targets)`.

C'est ce recoupement, et non le nom du champ, qui autorise à lire `ShouldPreferMachine` comme
**un tirage à 50 %** plutôt que comme un prédicat d'état.

### 3.2 Trois slots qu'un nom ne donne pas

`interface_slots.tsv`, jamais déduit : `0x7f = 127 GetAdjacentEnemies` (arité 3 — les slots
125/126/128 sont trois autres surcharges) ; `0x75 = 117 GetSurroundingUnits` (arité 4) ;
`0x6c = 108 GetDistance`. ⚠ Le commentaire de `_base._get_num_attack_targets_in_position` lit
`0x7f` comme `GetNumAttackTargetsInPosition` : c'est un **autre** call-site, d'une **autre** arité
(celui de `TheQuickeningPlaybook`). Recopier cette lecture ici aurait donné une utilité fausse.

## 4. Ce qui est LIVRÉ, et ce qui ne l'est pas

**Porté et confronté — `1161`.** `probe_970` : 2 cibles `fromHere`, le port rend
`{kind: ability, target: 77, ability: 1161, to: None, util: 1.0}` ; **contre-épreuve** (playbook
retiré du registre) → `{kind: finish}`. Elle **mord** : avant ce port, l'ability n'était proposée
par aucun chemin. Deux quirks transcrits : le `Bucket` construit **sans borne** (surcharge à deux
arguments — le `Fix64(1)` du `.cctor` n'est pas lu, `MIN_UTILITY = 0`), et le sélecteur
`GetEligibleTargetsEntities` (domaine unité) là où les cinq autres appellent `…Selectable`.

**Porté, feuille confrontée, driver NON atteint — `1201`.** La feuille rend `pred = 3.0`
(= `1 + 2` ennemis adjacents) sur 58 tuiles candidates : le mirror calcule, et non trivialement.
Le driver ne la voit pas, et la cause est **localisée par étage, pas supposée** :
`dv.mows[casterId].abilities` publie bien `[1200, 1201]`, mais `build_machine` ne retient que les
abilities **utilisables**. Le partage est exactement celui des `initialCooldownTurns` du
gameconfig — `1161` = 0 (retenue, `usable: True, cooldown: 0`), `1160`/`1200`/`1201` = 1
(écartées). C'est `AActionGenerator$$CanAbilityBeUsed` côté natif : comportement fidèle, pas un
trou du port. Résidu `#970-r1` (avancer d'un round avant de mesurer).

**RE-solues, NON portées, et dites telles quelles** : `1158` (`#970-r5`), `1159` (`#970-r4`),
`1160` (`#970-r2`), `1200` (`#970-r3`). Aucune n'est cochée : les inscrire aurait fait bouger un
compteur d'audit sans changer un comportement.

Le blocage de `1160` mérite d'être nommé ici parce qu'il n'était pas prévisible : le playbook
n'évalue **pas** son ability, il va chercher le TRIGGERED `1260 HeavyRailRifle_Attack`
(`GetAbility<T>(this, 0x4ec)`) — et **`HeavyRailRifle_Attack` est absente du gameconfig** (572
abilities indexées ; seul `HeavyRailRifle` y figure). Ni `minDmg`/`maxDmg` ni `nrOfHits` du
triggered ne sont donc lisibles hors ligne, alors que c'est cette config-là que la formule
consomme. La ligne du call-site existait déjà dans `TRIGGERED_PREDICTION_AVERAGE_FORM`
(`(GetDamage, 4)`) **sans consommateur** : ce port en aurait été le premier, et il ne peut pas
l'être tant que la source des variables manque.

## 5. Un piège de méthode, rencontré deux fois

**Une contre-épreuve muette n'est pas toujours un échec — mais elle ne doit jamais passer pour un
succès.** `probe_970` distingue les deux : si `me.abilities` porte l'ability, un port silencieux
est un **échec** (`rc = 1`) ; s'il ne la porte pas, le probe écrit `NON CONFRONTÉ AU DRIVER` et
n'invente pas de rouge. Sans ce discriminant, `1201` aurait rendu le même `finish` que `1161`
avant portage, et rien n'aurait dit lequel des deux était un bug.

**Le côté du plateau n'est pas un détail de montage.** Premier jet avec `--a-mow` : **0 cible**
`fromHere` et `aiStepDryRun` vide, sur les deux porteurs. Ce n'est ni un « porteur non
confrontable » ni un « régime inatteignable » — c'est que le tour courant au build est celui du
joueur. `--p-mow` rend 2 et 58 cibles. La conclusion « non confrontable » était à portée de main
et aurait été fausse.
