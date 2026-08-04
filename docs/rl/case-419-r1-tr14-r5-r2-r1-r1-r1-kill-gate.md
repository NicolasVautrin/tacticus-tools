# `#419-r1-tr14-r5-r2-r1-r1-r1` — le gate `ShouldExecute` « l'attaque normale tue déjà »

**Critère binaire** : le moteur émet-il des actions que le natif refuse, parce que leur playbook a un
`ShouldExecute` propre que le port ignore ? **Non, pour 17 des 43 classes**, depuis cette tranche.
Trois corps natifs portés, confrontés live sur un carré apparié plus un volet de portée, avec deux
contre-épreuves mordantes.

---

## 1. L'inventaire, RE-DÉRIVÉ (et il corrige la fiche)

Le balayage de #573 a été **rejoué indépendamment**, même technique (énumération NIVEAU PAR NIVEAU
via le RPC `resolveMethodPtr`, la seule qui distingue « hérité » de « REDÉCLARÉ sur le même corps »),
mais sur un périmètre **dérivé de la table des classes** : les classes concrètes dont la chaîne
d'ancêtres passe par `ComparablePlaybook`1` — **94**, pas 363 (ce dernier compte inclut les
NonComparable, les bases génériques et les classes de fermeture).

| catégorie | compte | accord avec #573 |
|---|---|---|
| héritent le gate d'`ALoki_NormalAttackPlaybook`1` | **16** | oui, et **la même liste nominale** |
| déclarent le corps trivial `return true` | **35** | oui |
| déclarent un corps PROPRE | **43** (29 distincts) | oui |

Ce que le balayage AJOUTE, et que #573 n'avait pas nommé :

* la **2ᵉ classe** du corps `IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$ShouldExecute` est
  `BasiliskBarragePlaybook` (#573 comptait « 2 » sans la nommer) ;
* **« 43 non portés » est FAUX de deux** : `Loki_NormalBossAttackPlaybook` est dans les 43 et a été
  portée par #573 elle-même, et `SorcerousFacadePlaybook` l'était **avant** (`loki_custom.py`, son
  `should_execute` y vit depuis #27-4b). Avec `HealPlaybook` / `HealingBalms_HealPlaybook`, modélisées
  autrement, le gisement réel à l'ouverture était de **39**.

### Les trois corps de cette tranche — 17 classes

```csharp
// IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute            -- 14 classes
return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

// IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$ShouldExecute               --  2 classes
target = UnitExtensions.GetUnit(target, this.<+0x20 = state>);
return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

// IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$ShouldExecute  --  1 classe
if (!(attackHealUtility > Fix64(0))) return false;      // court-circuit : la prédiction ne se fait
return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);   //  que si le seuil passe
```

Les dix-sept `ability_id` sont lus **dans le `.ctor` de leur classe**
(`ComparablePlaybook<T>..ctor(this, <id>, klass)`), jamais déduits du nom :

| corps | ids |
|---|---|
| `SpiritLeechPlaybook$$ShouldExecute` | 1004 MortisRound, 1008 HarbingerOfDestruction, 1022 BringerOfDespair, 1025 SkyStrike, 1027 PsychicMaelstrom, 1044 IncendiaryShells, 1048 FragstormGrenadeLauncher, 1062 SanctorumMissile, 1078 Fragstorm, 1080 HellfireShells, 1089 GreatFrostAxe, 1104 SpiritLeech, 1105 CrushingClaws, 1171 DakkaDakkaDakka |
| `FragBombPlaybook$$ShouldExecute` | 1017 FragBomb, 1026 BasiliskBarrage |
| `MultiThreatEliminatorPlaybook$$ShouldExecute` | 1006 MultiThreatEliminator |

**Critère de tranche, énoncé avant de lire** : *le plus grand nombre de classes fermées par corps
mirroré, à primitive déjà disponible dans le port*. Ces trois corps ferment **17 des 43** (40 %) avec
UNE primitive, `BasePlaybook$$WillNormalAttackKill`, déjà portée côté NonComparable.

### La primitive, et les champs de `BasePlaybook`

`IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` (surcharge à 4 arguments) :

```csharp
if (target == null) return false;
pred = battleQuery.<slot d'interface 0x21>(caster, target, casterTile);   // this@+0x28
return new ProbableDamageEvent(target, pred, default, default)
           .<DamagePredictionResult @+0x8>.get_WillBeKill();
```

Les offsets sont **lus**, pas déduits : `IdunBattle.AI.Playbook.BasePlaybook$$Init` pose
`this+0x18 = dsl`, **`this+0x20 = state`**, **`this+0x28 = query`**, `this+0x30 = random`,
`this+0x40 = utilitiesDatabase`, `this+0x58 = abilitiesDatabase`, `this+0x60 = damageCalculations`.
La seconde surcharge, `(this, entities)`, n'est qu'un relais qui déplie `entities` (`+0x8` caster,
`+0x10` target, `+0x40` casterTile) sur celle-ci.

⚠ **Réfutation** : #573 écrivait que « la fabrique pose `this@+0x20` en repli, mesuré à `69` ». Sur
`BasePlaybook`, `+0x20` est le **`state`** — c'est ce que `FragBombPlaybook$$ShouldExecute` passe à
`GetUnit`. La phrase de #573 portait sur un autre objet ; ne pas la reporter sur le playbook.

La surcharge de `UnitExtensions$$GetUnit` employée par `FragBomb` est **tranchée par ses xrefs
entrantes** (les trois ont la même signature `(entity, state)`) : c'est l'aiguillage PAR TYPE — une
unité est rendue telle quelle, une TUILE rend son occupant (récursif), un PIED remonte à l'unité,
sinon `null`.

---

## 2. Le port

`engine/playbook/base.py` — `BasePlaybook.will_normal_attack_kill` + la fonction libre
`will_normal_attack_kill`, **foyer UNIQUE** : les deux forks qui existaient
(`noncomparable/_base.py::_will_normal_attack_kill`, `loki_custom.SorcerousFacadePlaybook`) y
délèguent désormais. Trois corps auraient été un fork.

`engine/playbook/normal_attack_kill_gate.py` — les trois classes, **héritant de
`DefaultActiveAbilityPlaybook`** : les 17 ids retombaient sur elle jusqu'ici, donc
`make_damage_predictions`, `calculate_custom_utility` et `make_effect_predictions` restent
EXACTEMENT ce qu'ils étaient. Le seul delta est `should_execute`. Une instance par identité
(`ability_id` d'instance) — c'est le mirror des quatorze classes natives, toutes concrètes.

`1004 MortisRound` était **déjà au registre** (`loki_custom.MortisRoundPlaybook`, pour son
`CalculateCustomUtility`) : elle délègue au même corps plutôt que d'être réinscrite.

### 2.1 La BORNE de portée — mesurée, pas supposée

`normal_attack_kill_gate.normal_attack_reaches(ctx, target, caster_tile)` désarme le gate quand
l'attaque normale du caster n'est pas légale sur `target` depuis `caster_tile`.

**Pourquoi elle existe** : le premier jet du port a produit une divergence, dans le sens le plus
grave — *le port REFUSE une action que le natif CHOISIT*. Mesuré : `astraOrdnance` en `(1,0)`
bombarde (`1026 BasiliskBarrage`) deux `adeptRetributor` à **1 PV** en `(6,7)`/`(6,8)`, et le natif
propose le cast. Le port, lui, rendait `killSure = True` avec `healthDmgMin = 1` — le **plancher** de
dégât — parce que `engine.playbook.prediction.make_normal_attack_predictions` calcule une prédiction
HYPOTHÉTIQUE sans regarder la portée. Le canal natif du preview, interrogé sur la même paire depuis
la même tuile, rend `dictCount: 0` / `pred: null` : il n'a **rien** pour elle.

Ce n'est PAS le mirror d'une clause native — `WillNormalAttackKill` n'en a pas — mais du chemin par
lequel le natif retombe sur `false` : `IdunBattle.Core.Services.BattleQuery$$GetNormalAttackPrediction`
délègue à un slot de service qui n'a rien à rendre hors portée. La borne est posée **dans le gate**,
pas dans la primitive partagée : `noncomparable/_base.py` sert des playbooks validés live dont aucun
n'exerce ce régime, et élargir leur comportement sortirait du périmètre.

Substrat : `ctx.plans` (les `attackPlans` natifs) — un eval d'attaque NORMALE du caster sur `target`
dont les tuiles `ranked` contiennent `caster_tile`. **Tri-état** : plans absents pour ce caster
(bridge offline, qui ne peuple que l'unité ACTIVE) ⇒ `True`, la borne ne s'applique pas.

---

## 3. La mesure

Board `MC1_67`, seed `4242`, `--no-ai` (l'adversaire ne joue jamais : la géométrie est **pilotée**).
Canal natif `aiDryRunAllUnits` (= `CalculateNextActionForUnit`, sans commit) ; canal port
`calculate_action_utility` depuis la tuile COURANTE (`None` = le `Nullable` vide natif).

### 3.1 Les deux critères, énoncés AVANT

Les deux canaux ne mesurent pas la même chose — `aiDryRunAllUnits` rend l'action **gagnante**,
`calculate_action_utility` rend « une action **existe** ». D'où deux critères distincts, et non un
accord naïf :

* **A (nécessité, symétrique)** : le port ne doit JAMAIS refuser une ability que le natif CHOISIT.
* **B (le gate mord côté natif)** : dans le bras `kill`, un caster gate-é **et à portée** ne doit pas
  proposer son ability, alors que le TÉMOIN — même bras, mêmes PV — la propose.

### 3.2 Le carré apparié (ability × PV de la cible)

Deux cibles `adeptRetributor`, PV **pleins** ou **1** ; cinq casters, dont un TÉMOIN dont le playbook
déclare le corps TRIVIAL `return true` (`FrenziedFiringPlaybook`, l'un des 35).

| caster | ability | corps | `nokill` natif / port | `kill` natif / port |
|---|---|---|---|---|
| `orksKillaKan` | 1171 | SpiritLeech ×14 | non / oui | **non / non** |
| `astraPrimarisPsy` | 1027 | SpiritLeech ×14 | **oui** / oui | **non / non** |
| `necroDestroyer` | 1006 | MultiThreatEliminator | non / oui | **non / non** |
| `ultraEliminatorSgt` | 1004 | SpiritLeech ×14 (via `loki_custom`) | non / oui | non / non |
| **`blackObliterator`** | **1036** | **trivial (TÉMOIN)** | non / oui | **OUI** / oui |

**A : 10/10. B : conforme** (les trois gate-ées à portée refusées par le natif ; le témoin proposé).

La ligne qui porte la preuve est `astraPrimarisPsy` : **même caster, même géométrie, seule la PV
change**, et `1027` passe de proposée à non proposée — pendant que le TÉMOIN fait le mouvement
**inverse** (non proposé à PV pleins, proposé à 1 PV). C'est ce qui exclut la lecture « à 1 PV les
abilities perdent l'argmax de toute façon » : à 1 PV une AoE devient au contraire plus attractive, et
c'est justement là que les gate-ées disparaissent.

⚠ Le témoin est ce qui rend le bras `kill` concluant. Sans lui, « plus aucune ability proposée à
1 PV » se lirait aussi bien comme « le gate mord » que comme un effet d'argmax.

### 3.3 Le volet PORTÉE

Cibles à 1 PV, casters qui bombardent **depuis leur spawn**, d'où leur attaque normale n'atteint pas
la cible — le régime qui a produit la divergence du §2.1. `astraOrdnance` (1026), `astraBullgryn`
(1017), plus le témoin.

### 3.4 Les contre-épreuves

| contre-épreuve | ce qu'elle coupe | où elle doit MORDRE |
|---|---|---|
| `gate_cut` | `should_execute` remis au défaut de la base = **le port d'avant** | les gate-ées du bras `kill`, et là seulement |
| `range_bound_cut` | la borne `normal_attack_reaches` | les gate-ées du volet PORTÉE, et là seulement |

L'inertie des autres lignes est la réciproque : un port qui déborderait les ferait bouger.

Probe : `scripts/python/probe_419r1tr14r5r2r1r1r1_normal_attack_kill_gate.py`.

---

## 4. Un résidu voisin RÉFUTÉ

**`#419-r1-tr14-r5-r2-r1-r1-r3` ne devient PAS mordant.** Sa fiche annonçait que le rang du terme
lifesteal de `1104 SpiritLeech` (sommé APRÈS `calculate_action_utility` côté port, AVANT côté natif)
« mordra dès que ce gate-là sera porté ». C'est faux : `SpiritLeechPlaybook$$ShouldExecute`
**n'utilise pas** son argument `attackHealUtility`. Le rang du lifesteal n'a donc aucun effet sur ce
gate. Le résidu reste ouvert et reste un rang faux — mais pour d'autres raisons que celle-là.

---

## 5. Résidus NOMMÉS — les 22 corps restants

22 classes, 22 corps distincts, tous 1:1 (43 − 17 portés ici − `Loki_NormalBossAttack` −
`SorcerousFacade` − `Heal` − `HealingBalms_Heal`). Trois familles, par ordre de coût :

### 5.1 `utility > <seuil statique de la classe>` — 5 corps, le gisement le moins cher

`AncestralFortunePlaybook`, `BlightGrenadesPlaybook`, `ExcruciatingFrequenciesPlaybook`,
`FlailSwingPlaybook`, `MomentShacklePlaybook`. Corps identiques en forme :

```csharp
return attackHealUtility > <premier champ statique de la classe>;
```

**Le seuil se lit dans le `.cctor` du playbook**, et il n'est PAS zéro :
`IdunBattle.AI.Playbook.BlightGrenadesPlaybook$$.cctor` écrit `Fix64.op_Implicit(1)` = **`Fix64(1)`**.
Ce qui rend cette famille confrontable : lire les cinq `.cctor`, puis un montage où l'utilité
d'action tombe entre `0` et le seuil. `RepairPlaybook` (`Common`) est la variante à seuil littéral
`Fix64(0)`, déjà au registre du port sans son gate.

### 5.2 Corps à logique propre — 4 lus, 13 non lus

Lus dans cette tranche, non portés :

* `ArmoriumCherubPlaybook$$ShouldExecute` — `< 2` unités dans une requête de zone ⇒
  `!CanKillTarget(...)`, sinon `true`. ⚠ `ArmoriumCherubPlaybook` (1014) est **déjà au registre**
  (`loki_custom.py`) pour son custom : y ajouter `should_execute` est le geste, comme pour 1004.
* `BloodChalicePlaybook$$ShouldExecute` — `Σ (GetNumberConstant(0x4f) − GetStat(allié, 5)) > 0` sur
  les unités d'une requête, en sautant les MÉCANIQUES.
* `HadesAutocannonsPlaybook$$ShouldExecute` — vrai ssi **au moins une** unité du même propriétaire
  porte `HasTrait(unit, 2)`.
* `HealPlaybook$$ShouldExecute` (`Common`) — `utility > 0` **et** (`!IsBoss(caster)` ou
  `caster != target`) ; le port ne modélise que la première moitié dans `HealPlaybook.score`.

Non lus (13) : `PlagueWindPlaybook`, `PlasmaCannonPlaybook`, `ReapingScythePlaybook`,
`Repair_GalvanicFieldPlaybook`, `ScytheOfDustPlaybook`, `ScythingTalonsPlaybook`,
`SeekerMissileFrequencyLockPlaybook`, `StaffOfStarsPlaybook`, `StormOfFlensingBladesPlaybook`,
`StranglethornCannonPlaybook`, `SuperchargePlaybook`, `TacticalPrecisionPlaybook`,
`TwistedScience_HealPlaybook`.

### 5.3 Le critère de confrontabilité, pour chacun

Le même que celui de cette tranche, et il tient en deux questions : *un porteur `lineup` est-il dans
`rl_duel build --list-pool` ?* et *existe-t-il un régime où la clause bascule alors que le TÉMOIN ne
bouge pas ?* Les cinq de §5.1 partagent le même montage (une utilité d'action entre `0` et le seuil) ;
les corps de §5.2 demandent chacun le leur.

### 5.4 Résidus de CETTE tranche

* **`-r1-r1` — le domaine de ciblage de `1017`/`1026` diverge.** `abilityTargets` rend pour elles
  `kind: "tile"` (mesuré : `astraOrdnance`/1026 ⇒ deux TUILES, celles qu'occupent les cibles), et le
  natif propose `ActiveAbilityMessage(1026, <entité tuile>)`. Le générateur Comparable du port, lui,
  énumère des **unités** — d'où le `GetUnit` du corps natif, qui est l'identité sur ce que le port
  passe. La confrontation disponible est conforme depuis la borne du §2.1, mais le gate de ces deux
  abilities n'a **jamais** été exercé sur une tuile VIDE, où `GetUnit` rend `null` et où le natif
  passe le gate inconditionnellement. Ce que le port ferait n'y est pas défini.
* **`-r1-r2` — la borne `normal_attack_reaches` est un mirror de l'EFFET, pas de la lettre.** Le
  chemin exact par lequel le natif obtient `WillBeKill == false` hors portée n'a pas été lu jusqu'au
  bout (le slot 9 du service derrière `GetNormalAttackPrediction`). Ce qui le trancherait : lire ce
  slot, ou hooker `WillNormalAttackKill` — capteur à écrire, donc fenêtre de reinject.

---

## 6. Ce qui n'est PAS couvert

* **Onze des dix-sept abilities ne sont pas confrontées individuellement.** Six le sont
  (1171, 1027, 1006, 1004 au carré ; 1026, 1017 au volet portée) ; les onze autres partagent le
  corps de `SpiritLeech` et sont portées par le MÊME objet Python — ce qui est confronté est le
  corps, pas chaque identité. Leur seule spécificité est l'`ability_id`, lu au `.ctor`.
* **Le seuil `utility > 0` de `MultiThreatEliminator` n'a pas de bras dédié.** Il est porté et lu au
  décompilé, mais le montage ne le rend pas discriminant : la clause de kill mord d'abord.
* **Un seul board et un seul seed.** Ni le gate ni la borne ne lisent le terrain ou le RNG.
* **La prédiction est celle du pas courant.** Un `killSure` qui basculerait en cours de tour (buff de
  dégât, armure retirée) n'est pas exercé.
* **`GetUnit` sur une tuile VIDE** — cf. `-r1-r1`.
