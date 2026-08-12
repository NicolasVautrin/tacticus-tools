# #986 — le reliquat du pipeline de DÉGÂT : six résidus, une seule lecture

Build `rnca9r7q6c`. **Décompilé = vérité, live = confirmation.**

Une passe de RE sur `AttackDamageOperation$$ExecuteHit` → `DamagePrediction$$PredictAttackRaw`
→ `GetBaseDamageFix64` sert **trois** des six résidus. Les lectures sont verbatim.

## 1. L'étage qui les commande : `request+0x58`, le dégât COURANT

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, dans l'ordre du décompilé :

```
D0      = IdunBattle.Core.HitDamage$$GetDamage(options.damage, rng, ignoreSpread)
profil  = BattleQuery.slot 0xad (damageProfileType)
AttackHit..ctor(D0, abilityOrEffect)                     -> Nullable<AttackHit> sur l'attaquant
isCrit  = slot 0xa  RollCritical(...)                    (gate: options[+0x2b] == 0)
AbilityEntities..ctor(...) ; EnqueueOperation(6) ; EnqueueOperation(7)
relecture de l'AttackHit -> `discard` ? -> retour ; isCrit ?
   NON  : D = D0
   OUI  : D = slot 0xb CalculateCriticalDamage(attaquant, defenseur, D0, options)
                        = ApplyCritDamage(critDamage, D0)  =  critDamage + D0   (#954-r2)
request+0x58 = Nullable<int>(D)          <- LE point de composition
request+0x6a = options[+0x2f]            <- le drapeau « appliquer le SPREAD »
slot 4  PredictAttack -> PredictAttackRaw(request)
slot 8  RandomlyResolveMinMaxDamage
sub-op 0x42 ; EvaluateAfterHitTriggers
```

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` lit ce champ, **puis** branche :

```
D = Math.Max(0, Nullable.GetValueOrDefault(request+0x58))
(si le Nullable<Fix64> du slot 0xd de l'interface a une valeur -> D = (int)Fix64(cette valeur))

if (request+0x6a == 0 || request+0x10 -> [+0x31] != 0)
        bornes = MinMaxDamageFix64(D, D)                       # AUCUN spread, bornes dégénérées
else    bornes = GetBaseDamageFix64(D, IsAttackMaxOutDamage(...), GetStat(0x19))
```

et `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`, corps relu **verbatim** :

```
if (!isMaxOut) { min = calc.slot8(D) ;            max = calc.slot9(D) }
else           { min = calc.slot9(D) + Fix64(extraMax) ; max = calc.slot9(D) }
max = max + Fix64(extraMax)
return MinMaxDamageFix64(min, max)
```

**Le spread est appliqué à `D`, un scalaire UNIQUE, et `D` contient DÉJÀ le crit.**

## 2. #954-r3 — NON-BUG : les deux vecteurs sont FIDÈLES, et la divergence est native

Le résidu demandait : « relire où `AttackData` compose `attack + critDamage` pour une attaque
NORMALE — **avant ou après** `GetBaseDamageFix64` ». Réponse LUE : **AVANT**, à `request+0x58`,
et c'est le **même** point de composition pour les deux familles. Ce qui les sépare n'est pas la
place du crit, c'est le **drapeau `options[+0x2f]`** :

| vecteur | `options.damage` (HitDamage) | `D0` | `options[+0x2f]` | bornes |
|---|---|---|---|---|
| NORMALE | dégénérée (`min == max`) | la stat d'attaque, **sans tirage** | ≠ 0 | `GetBaseDamageFix64(attack + cd)` — **spread** |
| ABILITY | plage de config (`min != max`) | **tirée** dans la plage | 0 | `(roll + cd, roll + cd)` — **pas de spread** |

`IdunBattle.Core.HitDamage$$GetDamage`, corps relu verbatim :

```
if (min == max)     return min ;                  # dégénéré -> AUCUN tirage
if (ignoreSpread)   return (max + min) / 2 ;      # division ENTIÈRE C#
return random.Next(min, max + 1) ;
```

Le `min == max -> return min` est ce qui rend l'attaque normale « struct dégénéré, 1 tirage/coup »
et l'ability « struct non dégénéré, 2 tirages/coup » — les deux régimes déjà validés bit-exact.

**Conséquence** : le « shift 974 contre 779 » n'est pas une divergence de fidélité, c'est
l'ombre du spread. Sur le vecteur NORMALE le crit est **dans** la multiplication du spread
(`(3000+974) × 0,80 − 3000 × 0,80 = 779,2`) ; sur le vecteur ABILITY **il n'y a pas de spread du
tout**, donc le shift est plein (`974`). Les deux mirrors du port sont conformes :

* `damage_ops/normal.py` : `eff_attack = stat(ATTACK) + crit_damage` puis `get_base_damage_fix64` ;
* `damage_ops/ability.py` : `hit_cr = bornes brutes + crit_damage` puis `_reduce` (post-roll).

Corroboré, sans être déduit de lui, par le témoin live déjà au dépôt (`necroDestroyer`,
`attack = 906`, `cd = 500`, 6 coups) : les coups critiques mesurés `[932, 882, 967, 867, 961, 955]`
tombent dans `[675, 1012]` = spread sur `906 + 500`. Le modèle « crit ajouté APRÈS le spread »
prédirait `[935, 1152]` — **réfuté par 867** ; le modèle « crit hors spread » prédirait
`[735, 952]` — **réfuté par 967**.

**Verdict : NON-BUG, fermé par la LECTURE.** Aucune correction de code.

### La confrontation LIVE : un discriminant SANS PARAMÈTRE — la LARGEUR

Le témoin `necroDestroyer` cité par la docstring du port ne vit **nulle part ailleurs dans le
dépôt** — exactement le défaut qui a fait tomber `#920-r1` (témoin ORPHELIN). Il n'est donc **pas
réutilisé** : la confrontation est **refaite**, et rendue reproductible par
`scripts/python/probe_986_crit_place_vs_spread.py`.

Le discriminant retenu ne demande de connaître **ni l'attaque, ni l'armure, ni le perçage, ni les
modificateurs** : si le crit entre **avant** le spread, la plage critique est **élargie** dans le
rapport `(A + cd) / A` ; s'il est ajouté **après** les bornes, la largeur est **conservée**.

Montage unique, une seule variable (la **famille** de l'attaque) : `necroDestroyer`
`CritChance = 100` + `CritDamage = 5000`, cible `necroWarden` `--armor-target 2000
--hp-target 400000` (aucun coup écrêté), board `MC1_67`, seed 777, unités **posées** par
`--place`/`--a-place`. Mesure du 2026-08-12, build `rnca9r7q6c`, session 70 :

| bras | non-crit (par coup) | coups CRITIQUES observés | étendue |
|---|---|---|---|
| **NORMALE** (`Loki_NormalAttack` 69) | largeur **217** | 3092 · 3949 · 3155 · 3087 · 4829 · 3453 | **1742** |
| **ABILITY** (`MultiThreatEliminator` 1006) | largeur **154** | 4804 · 4776 · 4812 · 4855 · 4798 · 4704 | **151** |

12 coups, `Attack_DidCrit=1` sur les 12. L'étendue d'un échantillon de 6 tirages **minore** la
vraie largeur, donc `1742 > 217` est une réfutation **sûre**, et `151 <= 154` est compatible avec
la conservation tout en étant incompatible avec un élargissement d'un facteur 8.

**Ce que le bras NORMALE réfute** (aucun de ces deux modèles ne demande de paramètre — tous deux
**conservent** la largeur, or elle a été multipliée par 8) :

* « le crit s'ajoute à plat **après toute la réduction** » — la lecture naïve d'`ApplyCritDamage` ;
* « le crit s'ajoute aux bornes **après le spread**, avant le perçage ».

**Ce que le bras ABILITY confirme** : largeur conservée ⇒ décalage **plat** des bornes de config,
ce qui est le mirror actuel — et la conséquence directe de `AttackDamageOptions[+0x2f] == 0`.

Les deux vecteurs sont donc **fidèles chacun à son chemin natif**, et les « harmoniser » serait la
régression. C'est ce que verrouille `tests/engine/test_986_crit_place_vs_spread_offline.py`
(7 tests) : shifts `779`/`1169` figés côté normale, `974`/`974` côté ability, non-dégénérescence
assertionnée, et deux contrôles **AST** (pas un grep de texte) sur la composition écrite au site.
Les quatre mutations correspondantes ont été vérifiées **mordantes**.

### Ce qui reste NON LU, et qui ne change pas le verdict

Le `slot 0xd` de l'interface `DAT_18334a0c8` (celle qui porte aussi `slot 8`/`slot 9` =
min/max du spread, et `slot 0x12` = type de profil) rend un `Nullable<Fix64>` qui **écrase `D`**
quand il a une valeur. Il est **null dans les deux régimes mesurés** (sans quoi le crit
disparaîtrait de l'attaque normale, ce que le live réfute, et les bornes d'ability seraient
fausses, ce que `ThunderousAssault`/`VigilanceEternal` réfutent bit-exact). Il est en amont du
branchement, donc il ne déplace le crit sur aucun des deux vecteurs. Nommé ici plutôt que
supposé nul.

## 3. #920-r3 — AVANCÉ par la lecture, PAS fermé

L'énoncé demandait si le port a raison de passer un centre `(lo + hi) / 2.0` **fractionnaire** à
`capped_reduction_flat`, là où le natif reçoit `finalAmount` en `int32`. Lecture décisive :

```
IdunBattle.Entities.Formulas.CurrentDamageFormula$$Calculate(this, entities, result)
    -> Nullable<int>.GetValueOrDefault(entities + 0xe8)
```

**`CurrentDamage` est un champ `Nullable<int>` de l'`AbilityEntities`** — le natif ne voit donc
**JAMAIS** un `.5`. La question change de nature : elle n'est plus « fractionnaire ou entier ? »
(**tranché : entier**) mais « **quel** entier ? ».

Ce qui reste à lire, et c'est le point d'entrée exact : **le WRITER de `AbilityEntities+0xe8`**
dans la branche qui construit `defenseModifiers`, c'est-à-dire l'appelant de
`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction(state,
entities)` (deux surcharges, celle à refcount 3 appelant celle à refcount 2 ; aucune n'évalue le
`CurrentDamage`, elles le **transportent**). Tant que ce site n'est pas lu, l'arrondi reste
indéterminé — et l'hypothèse « c'est le CENTRE des bornes réduites » est elle-même un **FIT** de
`#91` (« D ≈ centre »), jamais une lecture.

⚠ **Piste ÉCARTÉE, et il faut le dire** : `IdunBattle.Core.HitDamage$$GetDamage` porte bien un
`(max + min) / 2` en division **entière** — mais son `ignoreSpread` est un **drapeau statique
global** (`FUN_180002590(0, <statics>)`), pas le centre des bornes réduites, et ses appelants sont
`AttackDamageOperation$$GetHitDamage` / `AbilityDamageOperation$$GetHitDamage` /
`FirstHitInCurrentAttackDamageRange$$Calculate`. Le rapprocher des trois call-sites de `#920-r3`
aurait été recopier le **voisin de forme**. Ce `//` -là est déjà porté, correctement, par
`damage_hits.py` (étape D de `test_344_ability_damage_average_offline`).

## 4. #889-r2 — AVANCÉ : la chaîne d'offsets est complète, la SÉMANTIQUE ne l'est pas

Le résidu disait « `AttackDamageBehaviourOptions+0x08` (une `List<int>{1}`) est LU mais NON
RÉSOLU ». Le trajet est désormais **complet**, lu dans
`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` :

```
AttackDamageBehaviourOptions+0x08  ->  AttackDamageBehaviour.this+0xa0  ->  AttackDamageOptions+0x40
```

Le champ est recopié dans la struct d'options passée à l'opération (slot `0x3c`), à l'offset
`0x40`. Contrôle de cohérence du mapping, sur deux offsets **déjà établis par le port** : le nœud
`hits` (`behaviour+0x80`) atterrit à `options+0x18` — c'est bien ce que lit
`AttackDamageOperation$$GetAttackHits` (#61/#411) — et les octets de drapeaux
(`behaviour+0x98..0x9e`) à `options+0x28`, l'emplacement du `skip hit count` de #411.

**Ce qui manque toujours** : aucun **lecteur** de `AttackDamageOptions+0x40` n'a été trouvé sur le
chemin `ExecuteHit` (le champ y est recopié par les copies de struct, jamais consommé). Le port ne
lui prête donc toujours aucun effet, et c'est **cohérent avec ce qui est lu** — mais ce n'est pas
une preuve d'inertie : le lecteur peut vivre dans `AttackDamageOperation$$Execute` /
`ExecuteHits`, non dépouillés. Prochain geste : chercher `+0x40` dans ces deux corps.

## 5. Non traités par cette tranche

`#924-r2`, `#925-r1` et `#965-r2` n'ont **pas** été traités (budget). Rien n'a été modifié les
concernant ; leurs énoncés restent à **re-mesurer** avant toute réparation — deux des six énoncés
du lot précédent se sont révélés faux.

⚠ Pour `#924-r2` en particulier : la face dégât est **DÉSARMÉE** et gardée par un cliquet inverse.
La livrer au mauvais étage donne **+45 %** de dégât par tir d'overwatch. La lecture de §1 lui est
directement utile — le natif n'offre **qu'un seul** point d'insertion scalaire avant les bornes
(`request+0x58`), et `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
consomme ensuite, dans cet ordre : `GetBaseDamageWithFixedPiercedArmor` (perçage/armure) → slot
`0x11` (modificateurs capés, attaquant puis défenseur) → slot `0x10` (multiplicateur, attaquant
puis défenseur) → override défenseur. C'est cette séquence qu'il faut confronter à
`attacker_additive_pre`, pas un scalaire ajusté.
