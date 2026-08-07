# #505 — `1129 BloodyFury` (`worldTerminator` « Wrask », WorldEaters), face EXÉCUTION

**État : PORTÉ ET CONFRONTÉ LIVE.** L'ability était un **no-op silencieux** (absente
d'`ABILITY_CLASSES` → `ported: False`, 0 dégât, 0 effet, aucune erreur). RE relue sur
`rnca9r7q6c`, port dans `engine/runner/abilities/worldeaters.py`.

Résidu ouvert et numéroté : **#505-r1** (loi de report de la feuille partagée — §5).

---

## 1. Ce que le natif construit

`IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$ExecuteBehaviour` — **un seul
nœud terminal** passé à `AActiveAbility$$Execute` :

```
dmg   = DSLFormulas$$Cache( AActiveAbility$$MinMaxDamage(this, abilityState) )
other = DSLSelectors$$Damageable(
            DSLSelectors$$AdjacentEnemies(unit = Owner@DSLSelectors+0x30, unique: 1,
                                          unitSelectionType: 3)
            op_Subtraction Target@DSLSelectors+0x60 )              # == $$GetOtherTargets
chain = DSLSelectors$$SortTargetsByDamagePredictionSelector(
            attacker = Owner@+0x30, units = other,
            ability  = DSLSelectors$$Direct(AbilityOrEffect(this+0x10)),
            damage   = dmg,
            hits     = <DSLFormulas+0x20>,                          # = Direct(1)  <-- §3
            damageProfileType = DSLSelectors$$Direct(Nullable(GetDamageProfile(config))),
            attackerSelectionType = 3)
DSLBehaviors$$ChainLeftOverHitsAttackDamage(
            caster = Owner@+0x30, firstTarget = Target@+0x60, dmgAmount = dmg,
            damageProfileType = Direct(Nullable(GetDamageProfile(config))),
            hits = <GetNumTotalHits(this)>, abilityType = this+0x10,
            otherTargetSelector = chain,
            extraHitsAfterTargetKilled = **null**)
```

`$$GetNumTotalHits` / `$$GetNumExtraHits`, mirror 1:1 :

```
Sum( Direct(GetNumberConstant(0x2f = nrOfHits)),
     Min( Multiply( Direct(GetNumberConstant(0x2b = extraHit)),
                    DSLFormulas$$TotalTimesAttacked(Owner@DSLSelectors+0x30) ),
          Subtract( Direct(GetNumberConstant(0x48 = maxNrOfHits)),
                    Direct(GetNumberConstant(0x2f = nrOfHits)) ) ) )
```

Config 1129 : `nrOfHits=1`, `extraHit=1`, `maxNrOfHits=8`, `damageProfile=Chain`,
`attackRangeType=Melee`. → coups = `1 + min(attaques reçues, 7)`.

**La colonne `DAMAGE(Chain)` de l'audit désignait le PROFIL D'ARME** (`damageProfile = Chain`),
et il se trouve qu'il y a AUSSI une chaîne — mais de **report de coups gaspillés**
(`ChainLeftOverHitsAttackDamage`), pas la chaîne à cibles accumulées de `1019 StormOfWrath`.

---

## 2. Le compteur : `+0x34` (BATAILLE), jamais `+0x38` (TOUR)

`IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate` rend
`*(uint *)(ActorStatisticsComponent + 0x34)`. Les trois lectures qui ferment la question :

| fonction native | ce qu'elle écrit |
|---|---|
| `ActorStatisticsComponent$$RegisterAttackReceived` | `+0x34 += 1` **et** `+0x38 += 1` (et `+0x3c` si `totalCrits > 0`) |
| `ActorStatisticsComponent$$ResetAttacksReceivedThisTurn` | `*(ulong*)(this+0x38) = 0` — **`+0x34` intact** |
| les deux `$$ResetThisTurn` + `$$ResetReceivedDamageThisTurn` | relus : **aucun** n'écrit `+0x34` |

L'i2 le dit avec les mêmes mots (« each time Wrask was attacked **in this battle** »), mais c'est
l'offset qui l'établit. Le port existant ne tenait que le per-tour
(`UnitComponent.times_attacked_this_turn`, gate du HP-floor) et sa docstring l'attribuait à tort à
`+0x34` : **le champ `total_times_attacked` est NEUF**, incrémenté au **même site**
(`operations/minimal_health.py::record_attacked`, mirror de `RegisterAttackReceived`).

**Confronté live, régime discriminant** : `k` attaques encaissées, puis **un tour ennemi BLANC**
(`+0x38` remis à 0, `+0x34` non), puis le cast. Le natif rend `1 + k` ; une lecture du per-tour
rendrait `1`. Mesure : `k=3` → live **4 coups**, per-coup **bit-exact** `[8006, 4775, 5049, 4390]`
des deux côtés. Témoin dégénéré `k=0` → **1 coup**, `[4366]` des deux côtés.

### Le grain du compteur n'est PAS « une commande d'attaque »

Calibrage per-attaquant (une attaque, `hits − nrOfHits` = contribution réelle) :

| attaquant | events de dégât sur Wrask | coups du cast suivant | contribution à `+0x34` |
|---|---|---|---|
| `eldarRanger` | 1 | 2 | **1** |
| `astraBullgryn` | 4 | 2 | **1** |
| `tauCrisis` | 9 | **4** | **3** |
| `necroWarden` | 1 | 2 | **1** |

`RegisterAttack` est appelée **une fois par `AttackDamageOperation`**, pas par commande : une unité
multi-armes en émet plusieurs. Compter les `applyAction` prédisait **5** coups là où le natif en
faisait **7**. Le port compte au même grain (`record_attacked` est appelé une fois par
`AttackDamageOperation._apply_damage_pipeline`) — mais son **attaque normale ne modélise pas** le
découpage multi-armes : rejeu offline des mêmes 4 commandes → `+0x34 = 4` contre **6** en natif.
**Résidu nommé**, hors périmètre #505 (il porte sur l'attaque normale, pas sur 1129) ; les régimes
de validation utilisent donc les trois attaquants dont la contribution mesurée est 1.

---

## 3. Les trois écarts LUS avec le voisin `1048 FragstormGrenadeLauncher`

1048 monte **la même feuille**. Rien n'a été recopié :

| | 1048 Fragstorm | 1129 BloodyFury |
|---|---|---|
| pool de report | `SurroundingEnemies(Owner, range)` puis `SortByFormula(PV croissants)` | `AdjacentEnemies(Owner)` **sans** tri par PV |
| `hits` du sélecteur de tri | `Direct(GetNumberConstant(0x2f = nrOfHits))` | **`<DSLFormulas+0x20>` = `Direct(1)`** |
| `hits` de la chaîne | constante `nrOfHits` | **formule** `GetNumTotalHits` |
| `extraHitsAfterTargetKilled` | null | null (identique) |

Le `hits = 1` du sélecteur ne se devine pas : le natif passe un **champ** de l'instance
`DSLFormulas`, et `IdunBattleLogic.Entities.DSLFormulas$$.ctor` écrit cinq formules-constantes
mémoïsées — `+0x18 = 0`, **`+0x20 = 1`**, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1` — avec la même
classe et le même ctor `(valeur, 0)` que `DSLFormulas$$Direct`.

---

## 4. Masque de ciblage et `AbilityAttackType`

`$$.ctor` recopie les 0x40 octets du **PRESET STATIQUE** `TargetingOptions` statics `+0x40` puis
appelle la surcharge **COPIE PURE à DEUX arguments** — dont le corps, relu, recopie les 8 qwords
verbatim **sans ajouter aucun flag**. Le décompilé ressemble à un PRESET+FLAGS dont le littéral
aurait disparu : ce sont les **XREFS ENTRANTES** qui tranchent (1129 figure chez les appelants de
la surcharge à 2 arguments, et dans **aucun** de ceux de la surcharge PRESET+FLAGS) — le piège
exact de `1029 Drachnyen` (#336).

`TargetingOptions$$.cctor` pour ce preset : `isSelfCasting = 0`, `range` ← `TargetingRange` statics
`+0x30` = `RANGE_ADJACENT`, `forceMeleeTarget = 1` (`RangedBool.False`), **`rules = 0x4000`**
(`TargetIsEnemy`, et rien d'autre — donc pas de `TargetMatchesDynamicRule`, et 1129 n'a
effectivement aucun `GetDynamicInvalidTargetReason` : **vérifié**, absent du dump *et* de
`DYNAMIC_TARGET_RULE_UNPORTED`). Concordant avec la mesure indépendante de
`docs/rl/case-302-4/tile-target-population.tsv` (ligne 1129, `state=measured`, `form=preset`).

`AbilityAttackType` = 3ᵉ argument d'`AActiveAbility$$.ctor` = **`0` = `DirectTargetAttack`**,
transcrit tel quel.

**Contrat de disjonction payé aux cinq endroits** : sortie de `TARGETING_OPTIONS_UNPORTED` (le bloc
« surcharge C, PRESET SEUL » passe de 1 à **0** entrée — **compte re-dérivé du code** : la table
tombe de 35 à **34**), `DYNAMIC_TARGET_RULE_UNPORTED` (vérifié, aucune entrée),
`SNAP_TARGETING_UNPORTED` + cardinalités (`test_270r1_volet2_dict_keys_enum_offline.py`,
`[34, …]`, somme **118**), `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` + sa ligne-journal
(`test_433_r4_r2_r1_r2_ability_range_offline.py`), et les probes qui indexent la table — **aucun ne
code un compte en dur** (vérifié : `probe_217`, `probe_287r4`, `probe_302_4`, `probe_419r1…`).

---

## 5. #505-r1 — la loi de REPORT de la feuille partagée n'est pas uniforme

`ChainLeftOverHitsAttackDamage._left_over_hits` porte `max(0, H − k − 1) + extraHits`. **Réfutée
pour 1129** par lecture DIRECTE du live — un seul ennemi fragile, les autres immortels, donc le 2ᵉ
maillon **survit** et son nombre d'events **est** son nombre de coups :

```
python scripts/python/probe_505_bloody_fury.py --only report --attackers 0,1,3 --attacks 3 \
       --main-hp 3000,10000,15000,21000
```

| PV cible | k | report LIVE | `max(0,H−k−1)+0` | `max(0,H−k)` |
|---|---|---|---|---|
| 3000 | 1 | **3** | 2 ✗ | 3 ✓ |
| 10000 | 2 | **2** | 1 ✗ | 2 ✓ |
| 15000 | 3 | **1** | 0 ✗ | 1 ✓ |
| 21000 | 4 | **0** | 0 ✓ | 0 ✓ |

Et `max(0, H−k)` fait **aussi** passer `test_chain_leftover_hits_live.py` (1006, seeds 4242 **et**
777) — parce que pour 1006 `extra = 1` et que `max(0,H−k−1)+1 == max(0,H−k)` dès que `H−k ≥ 1`.
La **seule** mesure qui les sépare est le régime `H == k` de
`probe_125_leftover_hits.py --mode sweep --hp-target 10000`, où le live frappe un 2ᵉ maillon
(report ≥ 1) alors que `max(0,H−k)` rendrait 0. **Aucune des deux formes ne couvre les six points.**

**La cause, LUE** — `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` est un **SEUIL**, pas un
index :

```
if (!allowOverkill) return false
if (minimumHealth.HasValue && minimumHealth.Value > 0) return false
if (healthDamage >= targetInitialHealth && isForceOverkill) return true
if (!isPreventOverkill && healthDamage >= targetInitialHealth) {
    pct = (healthDamage - targetInitialHealth) / targetInitialHealth * 100    # Fix64
    return (pct < overkillDmgPctOfHealth) ? isCritical : true
}
return false
```

→ le coup **fatal** pose lui-même `UnitFlag.Overkilled` quand son **excédent** dépasse
`overkillDmgPctOfHealth` (ou qu'il est critique) ; sinon c'est le coup **suivant**. L'indice du
premier coup « déjà overkill » vaut donc `k` **ou** `k+1` **selon la magnitude** — exactement
l'unité d'écart : 1129 écrase sa cible à **+167 %** (→ `k`), 1006 la dépasse de **+24 %** (→ `k+1`).

**Non fermé ici, et c'est délibéré** : fermer demande de porter `IsOverkill` (constante
`overkillDmgPctOfHealth` des battle-rules, `deniedDamage` cumulé, `CanBeOverkilled`,
`HasFlag(0x13)`, `minimumHealth`), sur une feuille **partagée par 1006 / 1048 / 1129**. Changer la
loi sur une compréhension partielle est pire qu'une divergence bornée et documentée. **Ce qui est
acquis** : la forme actuelle **sous-estime le report d'exactement 1** quand le coup fatal écrase la
cible, et est **juste** quand il l'effleure.

⚠ **`probe_489_fragstorm_grenade_launcher.py` VERDICT-4 ne pouvait pas le voir** : il compare
`off_chain[1]["hits"]` à la formule qui l'a produit — une **tautologie**, pas une confrontation.
Le verdict qui mord est celui qui lit le report **dans le live**, sur un maillon **survivant**.

---

## 6. Ce que le montage a coûté (et pourquoi il est figé au build)

Deux causes **mesurées**, toutes deux fatales à la mesure du compteur, ont fait passer le montage
de « déplacer les unités » à `--place` / `--a-place` :

* un déplacement du **caster** attire l'**overwatch** des ennemis ranged → `+0x34` monte sans que le
  probe le sache. Le régime témoin, censé valoir `hits = 1`, a rendu **3** ;
* dans ce runner, `applyAction move` **consomme l'activation** de l'unité déplacée (`hasAction`
  passe à False) → un ennemi qui vient d'avancer ne peut plus attaquer le même tour.

Wrask est donc posé en `(3,4)` sur `MC1_67` — la tuile a **ses six voisins jouables**, vérifié sur
le dump du board — et les ennemis sur l'anneau. Un audit d'events (`_events_on`) fait **échouer le
montage** si Wrask encaisse quoi que ce soit de non driveé. Troisième piège : `decisionView.ctrl`
désigne « unité du camp qui joue **en ce moment** » et s'**inverse** à chaque `endturn` — le dériver
rendait « aucun ennemi adjacent » une fois sur deux, alors que trois l'étaient.

---

## 7. Livrables

* Port : `engine/runner/abilities/worldeaters.py` (`BloodyFuryAbility`,
  `bloody_fury_tree`, `bloody_fury_hits_formula`, `bloody_fury_other_targets`).
* Substrat : `runner/components.py` (`UnitComponent.total_times_attacked`),
  `runner/operations/minimal_health.py` (`record_attacked`),
  `runner/abilities/behaviours/context.py` (clé `totalTimesAttacked`),
  `entities/formulas.py` (`TotalTimesAttacked(unit)`).
* Registres : `abilities/handler.py`, `abilities/attack_type.py`, `abilities/targeting.py`.
* Garde offline : `tests/engine/runner/test_505_bloody_fury_offline.py` (8 tests).
* Mesure live : `probe_505_bloody_fury.py` (régimes `temoin` / `snowball` / `chaine` /
  `calibrage` / `report`).
