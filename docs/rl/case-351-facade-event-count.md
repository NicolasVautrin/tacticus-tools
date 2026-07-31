# case-351 — SorcerousFacade (1100) : `AddRange` AJOUTE, il ne SUBSTITUE pas

Résidu `#350-r1`. **Statut : FERMÉ**, porté et confronté live (accord bit-exact sur les deux bras,
deux A/B causaux). Le symptôme mesuré par #350 — « le natif émet DEUX events de dégât, le port un
seul » — n'était **pas** une propriété du natif à découvrir : c'était un **fork de port**.

---

## 1. Le décompilé — un seul artefact, deux termes

`IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions`, fin du corps, mirror
verbatim :

```
sel = TargetsSelector.SelectFirst(SorcerousFacadeAbility.GetTarget(ability),
                                  entities{Caster, CasterTile = casterPosition.MainTile,
                                           CasterTiles = casterPosition});
if (sel == null) return <liste VIDE statique>;
list = TExtensions.ToList([ new ProbableDamageEvent(sel, battleQuery.<slot 0x22>(caster, sel,
                                                                                 casterPosition)) ]);
list.AddRange( ComparablePlaybook<T>.GenerateMultiHitAttackPredictions(
                   caster, casterPosition, sel,
                   targets = DSLSelectors.Get(sel),                     // mono-cible
                   damage  = DSLFormulas.Half(DSLFormulas.Sum(Get(GetVariableForLevel(0xc = minDmg)),
                                                              Get(GetVariableForLevel(0xd = maxDmg))), 0),
                   hits    = GetNumberConstant(0x2f = nrOfHits),
                   profil  = <vide>) );
return list;
```

Trois faits, tous lus et tous mesurés :

1. **`AddRange` AJOUTE.** La liste rendue a **deux** éléments — l'attaque normale en tête, le batch
   propre de l'ability ensuite.
2. **Les deux events portent sur `sel`**, le *même* ennemi. Ce n'est donc pas un volet AoE : c'est
   deux prédictions sur une seule cible. Une lecture « le premier event de la cible principale »
   n'en voit qu'une.
3. **La cible passée (l'ALLIÉ Psyker) n'entre pas dans la prédiction** : le playbook la remplace par
   `sel`. Mesuré en interrogeant l'oracle sur les deux cibles — même réponse.

## 2. Ce qui était faux, et où

Le port avait **deux implémentations du même artefact natif** :

| chemin | ce qu'il rendait | verdict |
|---|---|---|
| `loki_custom.SorcerousFacadePlaybook.make_damage_predictions` | 2 events, reconstruits à la main | juste, mais dupliqué |
| `prediction.abilities.make_damage_predictions` (`_PREDICT_VIA_NORMAL_ATTACK`) | **1 event** — il *substituait* l'attaque normale au batch | **faux** |

Le second est celui qu'interroge le harnais de #344/#350. D'où son bras muet : l'attaque normale ne
lit aucune moyenne `minDmg`/`maxDmg`, donc les quatre variantes d'arrondi y coïncidaient — bras
**non discriminant**, échec qui n'accusait pas la bonne chose.

**Le nom mentait sur la structure**, et c'est la cause racine. `_PREDICT_VIA_NORMAL_ATTACK` se lit
« la prédiction *est* l'attaque normale ». Le natif dit « l'attaque normale *précède* ». Renommé
`_PREPEND_NORMAL_ATTACK_EVENT`.

Deuxième héritage réfuté, plus coûteux : `case-171` affirmait « l'oracle ne remonte PAS l'event #2
(dedup aval par cible + règle) ». **Faux** — `aiPlaybookPredict` rend `count = 2`, les deux events
sur le même `targetId`, et le décodeur `playbook-predict.ts` lit la `List<T>` entière sans
dédoublonner quoi que ce soit. L'affirmation a survécu quatre mois à une première lecture qui, elle,
était juste (`AddRange` était écrit noir sur blanc dans la fiche même).

## 3. Le port

| pièce | où | note |
|---|---|---|
| `_PREPEND_NORMAL_ATTACK_EVENT` | `playbook/prediction/abilities.py` | le terme en tête, hors du gate `main is None` (le natif ne le conditionne à rien) |
| `_PLAYBOOK_PROFILE_OVERRIDE[1100] = "None"` | idem | le `param_8` VIDE du call-site — **plus inerte**, l'ancienne note disait le contraire |
| `SorcerousFacadePlaybook.make_damage_predictions` | `playbook/loki_custom.py` | **DÉLÈGUE** : ne garde que la substitution de cible, seule chose que le natif y écrit de spécial |
| `_PROFILE_NONE` | *supprimé* de `loki_custom.py` | le profil se lit désormais là où se lisent les onze autres |

Pour toute ability hors du registre, le comportement est **strictement inchangé** (`events = [main]`
devenu `events.append(main)`).

## 4. Mesure LIVE

Porteur `thousTzaangor` « Yazaghor » (**HERO**, voie `active`, **dans le pool**) ; allié Psyker
`thousSorcerer` (pool). Aucun `catalog_inject`. Board `MC1_67`, centre `(3,4)`, niveau 8
(`minDmg 25 + maxDmg 50 = 75 = 3 mod 4` — la classe où l'arrondi se sépare de la troncature).

`probe_351_facade_event_count.py`, séquence `(healthDmgMin, healthDmgMax, appliedHits)` sur `sel` :

| bras | natif | port PLAYBOOK | port GÉNÉRIQUE |
|---|---|---|---|
| `noarmor` (`--armor-target 0`) | `((3935,5903,1), (30,46,1))` | identique | identique |
| `armor` (armure native) | `((1623,3591,1), (1,1,1))` | identique | identique |

`count = 2` côté natif dans les deux bras, les deux events sur le **même** `targetId`. Interroger
l'oracle sur l'ALLIÉ ou sur l'ENNEMI rend la même séquence.

**A/B causaux** — sans eux, l'accord ne distinguerait pas « porté » de « juste par ailleurs » :

* `_PREPEND_NORMAL_ATTACK_EVENT` vidé → le port retombe à **un** event (`((30,46,1),)` /
  `((1,1,1),)`) : l'état d'avant #351 ;
* `_PLAYBOOK_PROFILE_OVERRIDE[1100]` retiré, **sur cible blindée** → `(1,1,1)` devient `(30,46,1)`
  (le profil `Psychic` perce 100 là où le natif subit l'armure pleine). Contre-épreuve : **sans**
  armure, le retrait ne change rien, et le probe l'exige dans ce sens.

`probe_344` sur 1100, les deux bras enfin discriminants :

| bras | `minDmg+maxDmg` | natif | ce que rendait la troncature |
|---|---|---|---|
| A (lvl 8) | `75 = 3 mod 4` | `((3935,5903,1), (30,46,1))` | `(30,44,1)` ✗ |
| B (lvl 9) | `81 = 1 mod 4` | `((3935,5903,1), (32,48,1))` | — (`half_up`/`ceil` : `(33,49,1)` ✗) |

`to_even` est seule nulle sur les deux bras, conforme au registre `(a4)` de #350 — dont
l'inscription passe donc de **lue** à **confrontée**.

## 5. Le piège de montage, mesuré

Premier montage : les deux ennemis sur le ring du caster, donc **à distance égale**. Le natif a
désigné `ultraCalgar`, le port `ultraTitus` — c'est le résidu **nommé** de `case-287` §7.4 (le natif
énumère `GetPossibleTargetsForOptions → GetUnitsInRange`, le port énumère `state.entities` ; à
distance égale le `First(1)` derrière `SortByDistance` ne tranche plus que par cet ordre). Le second
ennemi est donc **relégué loin** : ce probe mesure le compte d'events, pas ce résidu-là.

Second piège, silencieux : **le caster doit bouger EN DERNIER**. Chaque `applyAction move` fait
avancer le tour, et une fois le caster passé le natif ne publie plus d'`attackPlans` pour lui — or
c'est de là que le port tire `ValidNormalAttackTargets`. Avec l'ordre inverse, `sel` est nul et le
montage ne mesure rien, alors que les *positions*, elles, sont bien celles voulues.

## 6. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_351_facade_event_count_live.py` (7) | le COMPTE (2) et la SÉQUENCE ; les DEUX chemins du port == natif (le fork ne peut pas revenir) ; la cible passée ignorée ; les deux A/B causaux + la contre-épreuve sans armure ; les deux bras mesurent des régimes distincts |
| `tests/engine/test_350_prediction_average_forms_offline.py` (test D, réécrit) | 1100 est ACTIF : le terme en tête ET le profil VIDE sont exigés, avec le chiffre que leur retrait produirait |
| `probe_344` (harnais) | compare la SÉQUENCE des events de la cible principale — c'est ce qui RETIENT le compte |

Non-régression rejouée : `test_sorcerous_facade_decision_live` **8/8** (dont `u_pred` == natif à
1e-6 — le chiffre qui attrapait le doublon), `test_sorcerous_facade_combat_live` **9/9**,
`test_350_..._live` **5/5**, `test_344_..._live` + `test_mass_driver_splash_prediction_live`
**12/12**, `test_savage_echoes_prediction_live` + `test_plagueburst_mortar_prediction_live`
**10/10**. Cliquets : `probe_181` (98 abilities, **0** masque manquant), `probe_120` étape 0 (**0**
littéral manquant), `probe_273 --only-scan`.

## 7. Résidus NOMMÉS (non couverts)

1. **L'ordre d'énumération de `ValidNormalAttackTargets`** — inchangé, toujours ouvert (`case-287`
   §7.4). Ce cas l'a **re-mesuré** au lieu de le supposer : natif `ultraCalgar` / port `ultraTitus`
   à distance égale. C'est la première mesure directe de ce résidu.
2. **Le `probability1` du terme en tête** : le natif construit son `ProbableDamageEvent` sans poids
   explicite ; le port ne lui en applique aucun non plus. Non exercé (aucun montage ne fait varier
   le poids du premier event).
3. **Les autres membres possibles de `_PREPEND_NORMAL_ATTACK_EVENT`** : l'ensemble n'a qu'un membre,
   et la structure « attaque normale en tête + `AddRange` » est lue **sur 1100 seule**. Un futur
   membre doit être lu, pas inscrit par analogie.
