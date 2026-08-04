# `#419-r1-tr14-r5-r2-r1-r1-r1` — le gate `ShouldExecute` « l'attaque normale tue déjà »

**Critère binaire** : le moteur émet-il des actions que le natif refuse, parce que leur playbook a un
`ShouldExecute` propre que le port ignore ? **Non, pour 15 des 43 classes**, depuis cette tranche.
Deux corps natifs portés, confrontés live sur un carré apparié, avec sa contre-épreuve mordante.
Un troisième corps (2 classes) a été **lu, porté, puis RETIRÉ sur mesure** — §2.1.

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
UNE primitive, `BasePlaybook$$WillNormalAttackKill`, déjà portée côté NonComparable. **Livré : 15** —
le corps `FragBomb` (2 classes) est ressorti du port sur mesure (§2.1).

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

`engine/playbook/normal_attack_kill_gate.py` — deux classes, **héritant de
`DefaultActiveAbilityPlaybook`** : les ids retombaient sur elle jusqu'ici, donc
`make_damage_predictions`, `calculate_custom_utility` et `make_effect_predictions` restent
EXACTEMENT ce qu'ils étaient. Le seul delta est `should_execute`. Une instance par identité
(`ability_id` d'instance) — c'est le mirror des quatorze classes natives, toutes concrètes.

`1004 MortisRound` était **déjà au registre** (`loki_custom.MortisRoundPlaybook`, pour son
`CalculateCustomUtility`) : elle délègue au même corps plutôt que d'être réinscrite.

### 2.1 Une BORNE de portée essayée, puis RÉFUTÉE par la mesure

Le premier jet du port a produit une divergence, dans le sens le plus grave — *le port REFUSE une
action que le natif CHOISIT*. Mesuré : `astraOrdnance` en `(1,0)` bombarde (`1026 BasiliskBarrage`)
deux `adeptRetributor` à **1 PV** en `(6,7)`/`(6,8)`, et le natif propose le cast. Le port rendait
`killSure = True` avec `healthDmgMin = 1` — le **plancher** de dégât — parce que
`engine.playbook.prediction.make_normal_attack_predictions` calcule une prédiction HYPOTHÉTIQUE sans
regarder la portée ; le canal natif du preview, interrogé sur la même paire depuis la même tuile,
rend `dictCount: 0` / `pred: null`.

**L'hypothèse « le natif désarme le gate hors portée » a été codée, puis RÉFUTÉE.** Une borne
`normal_attack_reaches` (substrat `ctx.plans` : un eval d'attaque normale sur CETTE cible dont les
`ranked` contiennent la tuile de cast) a été posée dans le gate, puis le carré rejoué. Résultat :

| bras `kill` | avant borne | **après borne** | natif |
|---|---|---|---|
| `orksKillaKan` 1171 | port refuse | **port accepte** | **refuse** |
| `astraPrimarisPsy` 1027 | port refuse | **port accepte** | **refuse** |
| `necroDestroyer` 1006 | port refuse | port refuse | refuse |
| `ultraEliminatorSgt` 1004 | port refuse | **port accepte** | **refuse** |

La borne **désarme le gate là où le natif le maintient** : elle est fausse, et retirée. Le natif
prédit donc l'attaque normale HORS PORTÉE, exactement comme le port. C'est aussi ce qui **disqualifie
`ctx.plans` comme proxy de « la prédiction existe »** : les tuiles `ranked` encodent la LÉGALITÉ du
cast, pas l'existence d'une prédiction hypothétique.

### 2.2 Ce qui restait à expliquer — et pourquoi `1017`/`1026` sortent du port

La borne écartée, la divergence `astraOrdnance` demande une autre cause. Elle est **lue, pas
supposée** : le RPC `abilityTargets` rend pour `1017`/`1026` des cibles `kind: "tile"` (mesuré —
`astraOrdnance`/1026 : deux TUILES, `(6,7)` et `(6,8)`, celles qu'occupent les cibles), et le natif
propose bien `ActiveAbilityMessage(1026, <entité tuile>)`. C'est exactement pour cela que le corps
natif commence par `GetUnit(target, state)` : **sa cible n'est pas une unité**. Le générateur
Comparable du port, lui, énumère des unités — domaine de ciblage différent.

Porter ce gate sur `target` = unité est donc une approximation, et la seule confrontation disponible
montre qu'elle **retire une action que le natif choisit**. Les deux ids sortent du port : résidu
`#419-r1-tr14-r5-r2-r1-r1-r1-r1`, pas de port spéculatif.

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

### 3.3 Le volet RÉSIDU

Cibles à 1 PV, `astraOrdnance` (1026) et `astraBullgryn` (1017) qui bombardent **depuis leur spawn**,
plus le témoin. Il ATTESTE que le résidu du §2.2 est bien un résidu : ces ids n'étant pas au
registre, le port ne peut pas retirer l'action que le natif propose (critère A), et la contre-épreuve
`gate_cut` y est **inerte** — si elle mordait, c'est qu'ils seraient gate-és par une autre voie.

### 3.4 La contre-épreuve

`gate_cut` remet `should_execute` au défaut de la base — **strictement le port d'avant cette
tranche**. Elle doit MORDRE sur les gate-ées du bras `kill`, et **là seulement** : l'inertie des
autres lignes (les deux bras `nokill`, le témoin, tout le volet résidu) est la réciproque — un port
qui déborderait les ferait bouger. On mute la MÉTHODE, jamais le code livré.

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

* **`-r1-r1` — `FragBombPlaybook$$ShouldExecute` (1017, 1026) : cible native = TUILE.** Lu et
  compris (§2.2), délibérément NON porté. Ce qui le rendrait portable : que la route Comparable du
  port énumère pour ces abilities le même domaine que le natif (des tuiles — la route
  `nonattack.py` en a déjà un, ex. 1169/1148), ou qu'on établisse la correspondance
  tuile ↔ occupant au rang du gate. Il faudrait aussi un montage sur tuile **VIDE**, où `GetUnit`
  rend `null` et où le natif passe le gate inconditionnellement — régime jamais exercé.
* **`-r1-r2` — la divergence `astraOrdnance` n'est pas expliquée jusqu'au bout.** Le §2.2 en donne
  la cause structurelle (domaine de ciblage), mais on n'a pas vérifié que `GetUnit(<entité 74>)`
  rend bien l'unité qu'on croit : `dumpEntityComponents` refuse une entité non-unité
  (`"pass entityId"`), donc l'identité exacte de `74` n'a pas été lue. Ce qui le trancherait : un
  hook sur `WillNormalAttackKill` — capteur à écrire, donc **fenêtre de reinject**.
* **`-r1-r3` — le port prédit un dégât PLANCHER hors portée.** Mesuré : `healthDmgMin = 1` et
  `killSure = True` pour `astraOrdnance` sur une cible à 5-6 tuiles, là où le canal natif du preview
  rend `dictCount: 0`. Le natif gate quand même dans ce régime (§2.1), donc **cela ne se voit pas
  sur le gate** ; mais c'est le même plancher qui alimente toutes les prédictions d'attaque normale
  du port, et il n'a pas été confronté hors portée ailleurs.

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
