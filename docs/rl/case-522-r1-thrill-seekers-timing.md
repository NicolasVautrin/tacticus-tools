# #522-r1 — `ThrillSeekers` : le +15 de crit ne mord pas sur le coup qui l'a déclenché

Trouvé en portant `1198 EuphoricStrikes` (#522) : à `--crit 0,700`, le port consommait **un tirage
`genrand_int32` de plus** que le natif, à dégât identique. Deux agents y sont arrivés par des
chemins indépendants — l'autre par `#524-r2` (`1196 LashOfTorment`, natif 3360 / port 6581,
divergence localisée au canal crit). **Une correction ferme les deux.**

## 1. La loi — lue au décompilé, pas déduite de l'écart

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` boucle **par coup**
(`while (compteur < numHits) { … ExecuteHit(…) … compteur++ }`), et dans
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` l'ordre est :

```
1. slot 0xad d'IBattleQuery                  -> DamageProfile du coup
2. AttackHit..ctor(damage, abilityOrEffect)  -> ecrit dans <comp>+0x98
3. slot 0xa d'IDamagePrediction = RollCritical      <-- LE CRIT EST TIRE ICI
4. AbilityEntities..ctor(...)
5. EnqueueOperation(..., 6, entities)  = On(PreAttackHit)        <-- L'EVENT EST EMIS ICI
6. EnqueueOperation(..., 7, entities)  = On(PreAttackDamageHit)
7. IsAttackMaxOutDamage, slot 0xb (GetHitDamage)
8. sub-operation 0x42 (application du degat)
9. ADamageOperation$$EvaluateAfterHitTriggers
```

et `IdunBattle.Core.Services.DamagePrediction$$RollCritical(this, attacker, defender,
abilityOrEffect, hitIndex)`, terme à terme :

```
cc = UnitExtensions.GetStat(attacker, 0x9 = CritChance, 0 = Current, 0)   <-- RELU A CHAQUE COUP
   + DamagePrediction.GetCritChanceBonusFromEffects(attacker, defender, ..., hitIndex)
if (cc < 1)   return false        # AUCUN tirage
if (cc > 100) cc = 100
return NextBool(cc)               # 1 tirage
```

**Deux faits, et c'est leur conjonction qui fait la loi** : (a) `GetStat(9)` est relu **par coup** ;
(b) `On(PreAttackHit)` est émis **après** le `RollCritical` du coup courant.

⇒ le stat-mod « Thrilled » (`EffectType` 0x59a = 1434, +15 CRIT_CHANCE) posé par
`...ThrillSeekersAbility$$CreateBehaviour` sur `On(PreAttackHit) & IsFirstHitInSeries`
**n'affecte jamais le coup qui l'a déclenché**, et **affecte tous les coups suivants**, ceux de la
même salve compris.

### Le cran qui borne tout : l'extinction du crit

`ExecuteHits` éteint `isCriticalDamageAllowed` (`hitGroup+0x3c`) dès qu'un coup **ne crite pas**, et
le propage à l'attaque (`attack[+0x40] &= hitGroup[+0x3c]`). Un coup 0 qui ne crite pas prive donc
**tous** les coups suivants de leur `RollCritical`.

**Conséquence pratique, et elle est contre-intuitive** : le +15 de `ThrillSeekers` ne peut mordre
que si le coup 0 a **déjà crité** avec la crit chance de **base**. Le régime `cc=0 / cc_after=100`
rend `[False, False, False]` — il ne mesure rien. C'est `cc=100 / cc_after=0` qui discrimine, et
c'est ce que le test garde (avec le régime aveugle vérifié **explicitement**, pour que la
contrainte soit mesurée et non affirmée).

## 2. Ce que le port faisait, et d'où venait le faux

Les trois vecteurs (`damage_ops/{normal,normal_like,ability}.py`) émettaient
`pre_attack_hit_triggers(...)` **avant** `AttackDamageOperation._crit_params(...)`, appelé **une
fois par attaque**. Le +15 entrait donc dans la crit chance de **tous** les coups, coup 0 compris.

Deux docstrings affirmaient l'inverse du natif. Elles sont corrigées, et l'origine du faux est
nommée — c'est ce qui dit si le même vice se trouve ailleurs :

| docstring | ce qu'elle affirmait | origine du faux |
|---|---|---|
| `triggers/loki/thrill_seekers.py` | « `ExecuteHit` émet `On(6)` **en TÊTE**, avant le calcul du crit de CE coup ⇒ le buff s'applique bien à l'attaque déclenchante » | elle décrivait la place du vecteur **côté PORT** (où l'event précédait bien `_crit_params`) et la présentait comme « la place NATIVE ». Une **justification de l'existant**, jamais confrontée au décompilé. |
| `operations/damage.py::_crit_params` (#74) | « crit-chance constante sur les coups d'UNE attaque ⇒ `_crit_params` une fois == valeur re-lue par coup. **Rien à porter.** » | son argument était une recherche gameconfig sur **559 ABILITIES** (« aucune clé per-hit »). `ThrillSeekers` est un **TRAIT** : structurellement **hors du corpus fouillé**. Un recenseur ne peut pas rendre zéro sur ce qu'il ne visite pas — et la ligne citait même « ThrillSeekers = re-trigger PAR TOUR », en le classant sans avoir lu son `CreateTrigger`. |

## 3. Le correctif — un foyer, deux paramètres, no-op par défaut

`damage_hits.py::_run_hits` prend `crit_chance_after` / `crit_enabled_after` (défaut `None` =
inchangé). `_roll_crit(idx)` **recevait déjà l'index** et ne s'en servait pas ; `idx` est l'index
**continu** de l'attaque (`hit_index0 + i`), donc `idx == 0` est exactement l'`IsFirstHitInSeries`
natif — un groupe de coups additionnels (`hit_index0 > 0`) est déjà au-delà.

Les trois vecteurs mesurent la crit chance **avant** d'émettre l'event (coup 0), émettent, puis la
**relisent** (coups 1+). `additional_hits.py` passe `crit_chance=0, crit_enabled=False` en dur : il
n'est pas concerné.

## 4. Rayon de souffle — mesuré, pas estimé

* **Écouteurs de `On(PreAttackHit)` / `On(PreAttackDamageHit)` dans tout le registre du port :
  UN SEUL** — `ThrillSeekersFullHealthTargetAbility` (`TRAIT_TRIGGERS["ThrillSeekers"]`). Hors de
  lui, le correctif est un strict no-op (les deux `_crit_params` rendent la même valeur).
* **Porteurs du trait `UnitTrait.ThrillSeekers` (1056) : 5**, tous `lineup` Emperor's Children —
  balayés sur `unit_map.all_kits()` (683 kits) :

| unité | nom | coups d'arme |
|---|---|---|
| `emperExultant` | Laviscus | 1 |
| `emperFlawlessBlade` | Hascule | 3 |
| `emperKakophonist` | Adamatar | 3 |
| `emperLucius` | Lucius | 6 |
| `emperNoiseMarine` | Shiron | 9 |

Aucun autre trait ne partage ce foyer.

## 5. Mesures

**Avant / après**, board `MC1_67`, `emperNoiseMarine`, `--crit "0,700"`, cible à pleine vie
(`probe_522r1_thrill_seekers_timing.py`) :

| | dégât natif | dégât port | tirages natif | tirages port |
|---|---|---|---|---|
| avant | 2737 | **2724** | 3 | **4** |
| après | 2737 | **2737** | 3 | **3** |

L'écart n'est pas qu'un compteur : le tirage excédentaire du coup 0 **décale tout le flux RNG** de
la salve, donc les montants divergent. C'est une divergence de **dégât**, déterministe.

**`#524-r2` est FERMÉ par le même correctif** — contre-épreuve indépendante, sur une autre ability,
avec le probe déjà dans `master` (`probe_524_lash_of_torment.py --amorce ability --vecteur ability
--dmin 2`) :

```
cast#0  deltas HP  live={79: 4874}  port={79: 4874}  ACCORD   MT 14 = 14
cast#1  deltas HP  live={77: 3360}  port={77: 3360}  ACCORD   MT 28 = 28
```

Le cast#1 était **3360 natif / 6581 port**. Et la question qui restait ouverte chez l'autre agent
(« pourquoi 0 crit sur 6 coups, p ≈ 4,2 % à 41 % ? ») tombe : la crit chance effective du coup 0
est **26** et non 41, et un coup 0 non-crité **éteint** le crit de toute la salve — `0/6` n'était
pas improbable, c'était la loi.

## 6. Ce qui n'est PAS couvert

* le régime « le coup 0 **crite** avec la cc de base, puis les coups 1+ profitent du +15 » n'est pas
  confronté **live** : le montage à `--crit 0,700` ne peut pas faire criter le coup 0. Il est gardé
  **offline** et déterministe (`test_roll_crit_coup0_offline`), et exercé **indirectement** en live
  par `probe_524` cast#0 (`crits = [True, False, …]`, accord bit-exact) ;
* **`#522-r3`** (ouvert ici) — les triggers **AFTER-HIT** sont appliqués **post-attaque** par le
  port, là où `ADamageOperation$$EvaluateAfterHitTriggers` court en fin de **chaque** coup. Même
  forme d'écart que celui corrigé ici, sur l'autre bord d'`ExecuteHit`. Aucun consommateur crit
  connu aujourd'hui (le registre n'a qu'un écouteur de `On(6)/On(7)`), donc non observé — mais
  c'est exactement ce qu'on disait de `On(6)` avant cette tranche ;
* **`#522-r2`** reste ouvert et intact (passif `RefusalToBeOutdone` 1441 non porté).
