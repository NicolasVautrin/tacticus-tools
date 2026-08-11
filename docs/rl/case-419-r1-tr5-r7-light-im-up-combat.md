# #419-r1-tr5-r7 — `LightImUp` (1103), face **COMBAT** : PORTÉE + CONFRONTÉE LIVE

Résidu de #419-r1-tr5, qui portait la face **DÉCISION** (playbook) et déclarait explicitement la
face COMBAT hors de son périmètre (`case-419-r1-tr5-light-im-up-playbook.md` §9). Elle était un
**no-op silencieux** : aucune entrée dans `ABILITY_TRIGGERS`, donc le passif d'`orksWarboss`
« Boss Gulgortz » ne frappait jamais offline — alors que le playbook, lui, en tenait compte pour
décider. **Décider ≠ exécuter, et l'existence de l'une ne dit rien de l'autre.**

## 0. Gate de confrontabilité

`orksWarboss` est **HERO** et présent dans `rl_duel build --list-pool` au rank 17 (97 unités) : il
se spawne directement, aucune injection catalogue. Il porte `LightImUp` par son kit gameconfig
(`passiveAbilities: ["LightImUp"]`). Les quatre autres porteurs sont npc — sans intérêt ici, le
HERO du pool exerce le même corps avec la même config.

**Piège du nom, hérité de #419-r1-tr5** : `1103` désigne trois artefacts (`TriggeredAbilityType.LightImUp`,
`ActiveAbilityType.Supercharge`, `EffectType.KanOpener_ReduceArmor`). Toute lecture de config passe
par le **nom** `"LightImUp"`.

## 1. Ce que dit le décompilé

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$CreateTrigger` :

```
On(0x26 = NormalAttack, ownerNeedsToBeAlive: 0) & get_OwnerIsActor
```

Le 2e argument d'`On` est le littéral **0** (là où `Drachnyen` passe 1). Aucun autre conjoint :
ni profil, ni type d'arme, ni adjacence.

`...LightImUpAbility$$CreateBehaviour` se termine par `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`
— une séquence de deux volets. L'arbre complet, terme à terme, vit dans l'en-tête de
`scripts/python/engine/runner/operations/triggers/loki/light_im_up.py` ; en voici la forme :

```
If( IsInAttackRange(Caster@+0x48, Target@+0x60, UnitSelectionType.OnlyTargetable),
    Attack(Caster, Cache(Target, matchAbilityEntities: 0),
           AttackDamage(Owner@+0x30, Target, Cache(MinMaxDamage(state)), Direct(profil),
                        AttackHitsWithModifiers(Caster, Target, Direct(GetHits())),
                        AbilityOrEffect(this.Id), <options: octet +3 = 1>)) )
&
If( IsDead(Cache(Target)),
    Attack(Caster, Cache(PickRandomly(Damageable(Unobscured(Owner,
                              SurroundingEnemies(Caster, CasterTile, range = GetNumberConstant(0x16),
                                                 unique: 1, OnlyAliveAndTargetable)) - Target), 1)),
           AttackDamage(Owner, Target, Cache(MinMaxDamage(state)), Direct(profil),
                        NumLeftOverHits(Cache(Target), AbilityOrEffect(this.Id)),
                        AbilityOrEffect(this.Id), <options: octet +3 = 1>)) )
```

### Les sept lectures qui ne se devinent pas

1. **Aucune gate de MÊLÉE côté combat.** Le playbook, lui, gate `IsMeleeAttack(case)`
   (`IBattleQuery` slot 2, #419-r1-tr5 lecture 1). Ici le seul gate de volet est
   `IsInAttackRange` — `IdunBattle.Entities.Triggers.IsInAttackRangeAbilityTrigger$$ShouldTrigger`
   = `BattleQuery.<slot 0x41>(unit, GetUnitPosition(unit), target, GetNormalAttackType(unit))`.
   **Les deux faces divergent, et c'est natif** : recopier la gate de la sœur — la tentation exacte
   que le voisin de forme inspire — annulerait 100 % du passif sur une attaque normale à distance.
   Mesuré : **12 933** de dégât qui disparaissent (§3).
2. **L'`unitSelectionType` d'`IsInAttackRange` n'est jamais LU.** Le ctor le range à `+0x30` et
   `$$ShouldTrigger` ne lit que `+0x10 state · +0x18 query · +0x20 rangedUnit · +0x28 target`.
   `OnlyTargetable(2)` est **inerte** — non porté, et c'est une lecture, pas un oubli.
3. **L'octet +3 du `Nullable<AttackDamageBehaviourOptions>` vaut 1 sur les DEUX volets, et il coupe
   la couche de modificateurs de coups.** Chaîne d'offsets lue de bout en bout :
   `AttackDamageBehaviour$$.ctor` copie les options en `this+0x98..0xb8` (donc `+3` → `+0x9b`) ;
   `AttackDamageBehaviour$$ExecuteTarget` recopie `+0x9b` en tête du bloc de drapeaux de
   l'`AttackDamageOptions` (donc `options+0x28` — le même bloc dont `+0x2f` porte le spread déjà
   documenté et `+0x2e` l'`isOutsideAttack`) ; et
   `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` fait, verbatim :

   ```
   hits = <Nullable<int> options+0x18>.GetValueOrDefault(1)
   if (options+0x28 != 0) return hits;              # <-- CE drapeau
   return BattleQuery.<slot 0xb6>(caster, target, hitGroupIndex, <requête hits = hits>)
   ```

   Sans lui, les modificateurs s'appliqueraient **deux fois** : le nombre de coups est déjà calculé
   par un nœud (`AttackHitsWithModifiers` au volet 1, `NumLeftOverHits` au volet 2).
   ⚠ Le champ n'a **aucun nom lisible** — `AttackDamageBehaviourOptions` est un `ValueType` sans
   méthode, `frida/methods.tsv` n'en indexe aucune. Le paramètre porté (`skip_hits_modifiers`)
   nomme donc son **effet LU**, pas un nom deviné.
4. **`NumLeftOverHits(unit, abilityOrEffect)` n'a PAS de terme `extraHits`.**
   `IdunBattle.Entities.Formulas.NumLeftOverHitsFormula$$Calculate` est le `count` **nu** des
   entrées `LeftOverDamages` de l'unité dont le drapeau est vrai et dont l'`AbilityOrEffect` égale
   le sien — là où `ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` ajoute `+ extraHits`
   dès que la liste est non vide. Le port partage donc le même foyer avec `extra = 0`.
5. **Le caster du `AttackDamage` est `Owner@+0x30`, pas `Caster@+0x48`** — la factory standard
   `DSLBehaviors$$AttackWithAttackDamage` prend `Caster@+0x48` en dur. Pour un triggered,
   `Owner == Caster`, donc observationnellement égal ; écrit parce que c'est ce que le décompilé
   porte.
6. **`Attack(...)` OUVRE une attaque** (`AttackBehaviour$$.ctor`, comme les deux
   `AttackWith*Damage`) → chaque volet pousse son propre `StartAttack`, donc son `On(PreAttack)`,
   et l'index de coup repart de 0. À ne pas confondre avec l'octet **+0** des options, qui vaut 0
   et commande le `GetCurrentAttackOrDefault` **du `AttackDamageBehaviour`** — lequel lit bien
   l'attaque que le `Attack(...)` englobant vient d'ouvrir. Les deux sont cohérents.
7. **Le disque secondaire est ancré sur `CasterTile@+0x50`**, pas sur `Caster@+0x48`. Sur la face
   DÉCISION cette distinction **tranche** (#419-r1-tr5 §6 : deux valeurs qui divergent, la tuile
   d'attaque candidate n'est pas la tuile réelle). Sur la face EXÉCUTION il n'y a pas de position
   candidate — `AbilityEntities.CasterPosition` est vide, donc `CasterTileSelector` retombe sur
   `GetTiles(Caster)`. Le port collapse donc sur `Caster()` **et le dit**.

## 2. Le nom qui manquait au foyer du report : `wasAlreadyDead`

`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit(this, target, damageRecord,
damageResult, wasAlreadyDead)` — **le 5ᵉ paramètre est NOMMÉ**, et c'est exactement le drapeau que
`NumLeftOverHitsFormula$$Calculate` et `GetLeftOverHits` testent. Le corps :

```
if (damageResult+0x11 != 0) return;                 # sortie anticipée, aucune entrée
liste = target.GetComponent<…>.LeftOverDamages
LeftOverDamage..ctor(&entry, &damageRecord, &<reste>, wasAlreadyDead)
liste.Add(entry)
```

⇒ le `count` compte les coups pour lesquels **la cible était déjà morte**, donc *tous ceux qui
suivent le coup fatal* : `max(0, H − k)`. Le coup fatal lui-même laisse une entrée, mais à drapeau
**faux** (il n'était pas déjà mort) — ce qui rend `list.Count > 0` vrai et déclenche le
`+ extraHits` de `GetLeftOverHits` même quand aucun coup n'est gaspillé.

**Ce nom n'est cité nulle part dans #505**, dont la loi portée est `max(0, H − k − 1) + extra`.
La mesure de cette tranche (§3, régime 6) lui ajoute un **7ᵉ point**, sur `extra = 0`, qui la
réfute : report live **2**, port **1**. Rien n'a été modifié dans le foyer partagé — voir §5.

## 3. Mesures (`probe_419r1tr5r7_light_im_up_combat.py`, runner `MC1_67`/`419503`, rank 17)

Réplique offline sur le **même** état et le **même** flux RNG (`dumpRng`). Les PV live sont lus
dans le dernier `UnitStats_RemainingHealth` que le natif écrit lui-même (cf. §5, résidu du
capteur). `T1` = cible de l'attaque normale ; `T2` = cible du report.

| # | régime | attaque normale | passif (1103) | verdict |
|---|---|---|---|---|
| 1 | d = 1, PV 900 k | 8 274 (3 coups) | 5 823 (3 coups sur T1) | **port == live** |
| 2 | #1, mutant `no-registry` | — | — | **DIFF 5 823** |
| 3 | d = 3 (**tir**), PV 900 k | 3 429 (1 coup) | 12 933 (3 coups sur T1) | **port == live** |
| 4 | #3, mutant `melee-gate` | — | — | **DIFF 12 933** |
| 5 | T1 2 000 PV, T2 900 k | 2 000 (T1 meurt) | 908 (3 coups sur T2, **survivante**) | **port == live** |
| 6 | T1 4 300 PV, T2 900 k | 4 017 | 283 + 0 sur T1, puis **2** coups sur T2 | **DIFF** (port : **1** coup) |

* Le régime **3** est le discriminant central : `orksWarboss` porte **deux armes** (mêlée
  `Eviscerate` 2 coups + `Projectile` **Range 3**, 1 coup — lu au gameconfig), donc à d = 3 son
  attaque normale est un tir. Le passif part **quand même**.
* Le régime **5** est le seul non saturé pour le report : T2 **survit** avec un montant non nul.
  Il confronte pour la **première fois** la branche « cible déjà morte à l'entrée » de
  `ChainLeftOverHitsAttackDamage._left_over_hits`, jusqu'ici « modélisée, non confrontée ».
* Le régime **6** est la divergence, et elle est **héritée**, pas introduite : cf. §5.

Le tag qui identifie les coups du passif est **`Passive_Ability_Type: 1103`** ; ces events ne
portent **pas** de `Active_Ability_Type` (l'`AbilityOrEffect` d'un triggered n'est pas un
`ActiveAbilityType`). Le premier jet du probe les cherchait sous `Active_Ability_Type == 1103` et
en trouvait **zéro** — il aurait conclu « le passif ne fire pas » sur un passif qui firait.

## 4. Contre-épreuves de mutation

| mutation | attrapée par |
|---|---|
| A — entrée retirée d'`ABILITY_TRIGGERS` | probe `rc = 1` (DIFF 5 823) **et** les 3 gardes live (3 failed) |
| B — gate d'adjacence ajoutée (le voisin de forme) | probe `rc = 1` à d = 3 (DIFF 12 933) |

Le mutant B n'était **pas** discriminant tant que le pilotage visait `d <= want_dist` : il rendait
toujours d = 1, où l'attaque est de mêlée et où la gate fausse est donc vraie. Viser la distance
**exacte** est ce qui l'a armé — un plafond aurait laissé passer B pour vert.

## 5. Résidus NOMMÉS

* **#505 (existant), confirmé et documenté par un 7ᵉ point** — `_left_over_hits`, foyer **partagé**
  par `1006` / `1048` / `1129` **et désormais `1103`**, porte `max(0, H − k − 1) + extra`. Le régime 6
  ci-dessus (H = 3, k = 1, extra = 0) donne live **2**, port **1**. Le nom natif `wasAlreadyDead`
  (§2) désigne `max(0, H − k)` comme le `count`. **Le foyer n'a PAS été modifié**, et c'est délibéré :
  `max(0, H − k) + extra` est réfuté par le point 1006-PV2500 de #505 (rendrait 5, live 4) tant que
  le `H` réellement appliqué de ce régime n'est pas re-mesuré, et `max(0, H − k)` sans `extra` est
  réfuté par 1006 à `H == k`. Changer une loi partagée par quatre consommateurs sur une forme
  qu'aucune mesure ne couvre entièrement serait exactement le fit que la doctrine interdit. Ce qui
  est **acquis** : le `count` vaut `H − k`, et le `+ extra` est conditionné à `list.Count > 0`
  (donc à la mort de la cible), pas à `count > 0`. Montage à rejouer pour fermer :
  `probe_419r1tr5r7_light_im_up_combat.py --no-hp-target --unit-stat "astraBullgryn:Health=4300,RemainingHealth=4300" --unit-stat "necroWarden:Health=900000,RemainingHealth=900000"`.
* **`#419-r1-tr5-r8`** — **le capteur de PV**. `decisionView` relu **après** l'action et
  `applyAction().units` rendent tous deux `hp` **inchangé** pour une unité qui n'est pas la cible de
  l'action : mesuré sur T2, frappée de 908 par le report, les deux capteurs rendent `900000` alors
  que les events du natif rendent `899092`. Un capteur qui ne voit pas la mutation qu'il doit juger
  **fabrique une fausse divergence** — c'est ce qui a failli faire accuser le port. Le probe et la
  garde lisent donc le dernier `UnitStats_RemainingHealth` des events. La cible **de l'action**, elle,
  est bien à jour dans les deux capteurs, et une unité **morte** l'est aussi : le trou porte sur le
  dégât **non létal** d'une unité **secondaire**.
* **Les entrées `LeftOverDamages` sont DÉRIVÉES**, pas matérialisées : le port les reconstruit du
  retour de l'attaque du volet 1 (`per_hit_health` / `hp_before`). Le filtre natif
  `AbilityOrEffect == 1103` est donc porté **par construction** (on ne lit que notre propre attaque)
  et non par un prédicat. Aucun vecteur porté ne produit d'entrée concurrente sur la même cible dans
  le même tour.

## 6. Non couvert

* La gate `IsInAttackRange` du volet 1 n'est **jamais falsifiée** par un montage : elle est évaluée
  juste après une attaque normale du même caster sur la même cible, depuis la même position — donc
  structurellement vraie. Il faudrait un déplacement de la cible ou un `ForcedInMelee` posé *pendant*
  l'attaque. **Portée, non exercée.**
* Le nœud `Unobscured` du sélecteur secondaire : inactif sur les tuiles retenues (aucun relief
  bloquant entre le caster et T2). Même limite que la face DÉCISION.
* Le drapeau `skip_hits_modifiers` du **volet 2** n'est discriminant que si la cible **secondaire**
  porte un malus de coups (`Parry` / `LightCover` / `Camouflage`). Aucun des six régimes ne l'exerce :
  le port est fidèle **par lecture**, pas par mesure, sur ce point.
* Les quatre porteurs **npc** (`orksBossWarboss`, `orksBossWarbossLHE`, `orksNpcWarboss`,
  `orksNpcWarbossSurv`) : hors-jeu, et sans intérêt — même corps, même config.

## 7. Livré

* `scripts/python/engine/runner/operations/triggers/loki/light_im_up.py` — l'ability (les deux
  volets, le sélecteur secondaire, le nœud `NumLeftOverHits`, le trigger `IsInAttackRange`).
* `scripts/python/engine/runner/operations/triggers/dispatch/registry.py` — entrée
  `ABILITY_TRIGGERS["LightImUp"]`.
* `scripts/python/engine/runner/operations/damage_ops/ability.py` +
  `scripts/python/engine/runner/abilities/behaviours/combat.py` — `skip_hits_modifiers`
  (octet +3 des options natives), défaut `False` = strict no-op pour les appelants existants.
* `scripts/python/probe_419r1tr5r7_light_im_up_combat.py` — montage, six régimes, deux mutants.
* `scripts/python/tests/engine/runner/test_419r1tr5r7_light_im_up_combat_live.py` — 3 gardes live.
