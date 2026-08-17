# case-489r1 — foyer `behaviours/combat.py` : quatre résidus, **deux prémisses fausses et deux périmées**

Tranche du 2026-08-15, build `t6dpr4k06g`. Items : `#1030-r4`, `#489-r1`, `#512-r3`, `#889-r2`.
Foyers édités : `runner/abilities/behaviours/combat.py`, `runner/operations/damage_hits.py`,
`runner/operations/damage_ops/ability.py`, plus deux fichiers de **câblage** hors surface
(`runner/abilities/darkangels.py`, `runner/operations/triggers/loki/lions_wrath_attack.py`) et le
jumeau offline d'un probe (`probe_523_heavy_warp_flamer.py`).

**Aucun des quatre énoncés n'était exact.** Deux étaient FAUX (le port était déjà fidèle), deux
étaient PÉRIMÉS (l'étage existait, seul le câblage manquait). Le tableau des verdicts est en §6.

---

## 1. `#889-r2` — RÉSOLU. Le lecteur d'`options+0x40` est dans `ExecuteHit**s**`, pas `ExecuteHit`

La fiche (MAJ #986, 2026-08-12) écrit : *« SEMANTIQUE toujours NON lue : aucun LECTEUR de
`options+0x40` sur le chemin `ExecuteHit` [...] Prochain geste : chercher `+0x40` dans
`AttackDamageOperation$$Execute` et `$$ExecuteHits`. »* Le constat est exact — `$$Execute` et
`$$GetAttackHits` ne font que **recopier** le champ. Le lecteur est un étage au-dessus, dans
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`, en fin de chaque coup **non critique** :

```
hitGroup.<+0x3c isCriticalDamageAllowed> =
    options[+0x40] != null && options[+0x40].Any(hitIndex => hitIndex == i + 1)
```

et le prédicat est le corps **entier** de
`IdunBattle.Operations.AttackDamageOperation.u003Cu003Ec__DisplayClass4_0$$u003CExecuteHitsu003Eb__0` :

```
return hitIndex == this.<+0x10 = i> + 1;
```

`i` est remis à **0** en tête de chaque `ExecuteHits` ⇒ c'est le rang du coup **dans le groupe**,
et la liste porte donc des numéros de coup **1-BASED**. `IdunBattle.Operations.
AttackDamageOperation$$Execute` propage ensuite par `attack[+0x40] &= hitGroup[+0x3c]`.

⇒ **`AttackDamageBehaviourOptions+0x08` est la liste des coups après lesquels le crit reste
AUTORISÉ.** Avec `{1}` — la valeur que posent les **deux** phases de `1217 TheLionsWrath` — et
`nrOfHits = nrOfHits_2 = 2`, les deux coups peuvent criter ; sans elle (`Any(null)` faux, cas des
douze autres call-sites du dépôt et de l'attaque normale) seul le premier le pourrait. C'est
exactement ce que dit l'effet compagnon `1522 TheLionsWrath_ExtraCritChance`, gaté par
`AmountIsEqual(CurrentHitIndex(), 1)` — l'hypothèse que `#889-r2` refusait de coder faute de
lecture est donc **confirmée par le prédicat**, pas devinée.

⚠ **La sous-partie « le crit s'éteint au premier coup non-critique » était déjà portée** et
documentée dans `damage_hits.py` depuis le **2026-08-01** (`b761ab26`, #366-r1-crit-multihit) —
onze jours avant la MAJ qui déclare la sémantique non lue. La fiche était périmée sur son point
central.

**Porté** : canal `crit_allowed_hits` (`combat.py::AttackWithAttackDamage` →
`damage_ops/ability.py::execute_ability_attack` → `damage_hits.py::_run_hits`), posé à `[1]` sur
les deux phases de `1217`. **Gate de famille** : `IdunBattle.Operations.
AbilityDamageOperation$$ExecuteHits` a une boucle PLATE et n'écrit jamais `hitGroup+0x3c` — le
canal est donc inerte hors famille ATTACK, et le cliquet le figé.

---

## 2. `#1030-r4` — PRÉMISSE FAUSSE. La famille ABILITY **zéroise** ses modificateurs d'attaquant

La fiche : *« `AttackWithAbilityDamage` ne thread PAS le `pierce_effect_bonus` des effets du
caster, là où son jumeau `AttackWithAttackDamage` le fait. »* Le constat est exact ; **c'est le
natif**.

`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` passe à
`$$CalculateBaseDamageWithAllModifiers` un `attackModifiers` **memset à 0**
(`local_498..uStack_460 = 0` juste avant l'appel) — il n'appelle **jamais** le slot 13
`CalculateAttackerModifiersForPrediction`, seulement le slot 15 (défenseur). Et
`$$CalculateBaseDamageWithAllModifiers` fait, verbatim :

```
additionalPiercing = attackModifiers.HasValue ? attackModifiers.Value.<+0x20> : Fix64.Zero
defenderPiercing   = defenseModifiers.HasValue ? defenseModifiers.Value.<+0x20> : Fix64.Zero
... GetBaseDamageWithFixedPiercedArmor(baseDamage, additionalPiercing, defenderPiercing, ...)
```

où `$$GetBaseDamageWithFixedPiercedArmor` calcule
`Min(100, Max(0, GetStat(0x1a) + GetStat(0x15|0x16) + additionalPiercing + defenderPiercing +
GetPiercingRatio(profil)))`.

⇒ **La famille ABILITY n'a aucun terme de perçage venant des effets du caster.** Y ajouter le
bonus aurait fait diverger le port sur tout porteur d'effet de perçage. Le résidu est **fermé sur
une réfutation**, et le cliquet interdit la « réparation ».

**Le vrai manque était chez le voisin** : `ChainLeftOverHitsAttackDamage` route la famille ATTACK
pour ses trois porteurs (`1006`, `1048`, `1129`) — donc `PredictAttackRaw` →
`CalculateBaseDamageWithAllModifiers` avec un `attackModifiers` **renseigné** — et n'appelait pas
`ability_pierce_effect_bonus`. **Réparé**, avec un re-calcul **par maillon** : les gates de
`BaseEffect$$PiercingBonusForAttack` lisent la CIBLE (`HasTrait(target, …)` de
`GravitonRifle_ExtraPierce` / `RelicBoltPistol_ExtraPierce`), et un maillon change de cible.

---

## 3. `#512-r3` — PRÉMISSE FAUSSE. `On(Attack = 9)` **est** émis par la voie ability

La fiche : *« `On(Attack = 9)` n'est émis par AUCUNE ability côté port — seulement par l'attaque
NORMALE. »* Ce qui est vrai, c'est que la **fonction** `finish_attack_triggers` n'a qu'un
call-site (`damage_ops/normal.py`). L'**événement**, lui, part aussi de
`dispatch/attack.py::after_hit_ability_attack` (ligne du `TriggerEvent(EventTriggerType.Attack,
…)`), appelée par `damage_ops/ability.py` à **chaque** attaque d'ability. `probe_437_on9_blast_radius.py`
étape 3 liste d'ailleurs **deux** sites d'émission, pas un.

Confondre le nom de la fonction et l'événement aurait fait ajouter un **second** émetteur, donc
**doubler** `On(9)` sur les **37** classes-triggers qui l'écoutent (mesure re-dérivée le
2026-08-15) — l'inverse exact du but. Le cliquet garde les deux moitiés : l'événement PART, et
`finish_attack_triggers` n'a QU'UN call-site.

**Correction de RE au passage** : le port recense **quatre** émetteurs de `StartAttack` (slot 58)
/ `FinishAttack` (slot 59). Il y en a **cinq** —
`IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` les pousse
lui-même autour de **chaque maillon**, et construit une feuille `AttackDamageBehaviour` **nue**
(aucun `AttackBehaviour`).

**Ce qui reste ouvert** (`#512-r4`) : la GRANULARITÉ. Le natif pousse `FinishAttack` **par cible
distincte** au niveau du nœud (`AttackBehaviour$$Execute` : `if (next == null || next != cur)`) ;
le port émet `On(9)` **par feuille**, depuis `execute_ability_attack`. Pour `1088
HellfyreMissileRack` (deux feuilles nues sur la même cible via `SortedAttackSeries`), le port
émettrait donc `On(9)` **deux fois** là où le natif l'émet une. Corriger exige de séparer, dans
`after_hit_ability_attack`, le vecteur `On(9)` (clôture, par cible) des vecteurs `On(0x3d)`/`On(8)`
(after-hit, par coup) — foyer partagé, rayon de 37 consommateurs à mesurer.

---

## 4. `#489-r1` — le bloquant déclaré n'existait plus ; la loi, elle, RÉSISTE (`#489-r2`)

### 4.1 Volet (a) — « aucun flag d'overkill exposé » : PÉRIMÉ

L'étage existait : `damage_hits.py::overkill_flag_posted_by_hit` est le mirror
d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`, porté par **#462-r4e-o-r1**, et
`_run_hits` rend déjà `overkilled` (tri-état) / `overkill_at_hit` (index 0-based du coup poseur) /
`hits_executed`. Seul le **câblage** manquait : `execute_ability_attack` ne les remontait pas.
**Fait**, et repris dans chaque maillon de `chain` — sans quoi un probe qui veut fermer la loi ne
peut pas lire l'index d'overkill.

### 4.2 Volet (a) — la LOI : les DEUX correctifs sont réfutés, chacun par une mesure LIVE

La loi portée est `max(0, H - k - 1) + extraHits`. Elle est **incomplète**, et ce qui est acquis
est la LECTURE : le gate du call-site (a) d'`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit`
— le SEUL des trois à pousser un flag **littéral `1`**, donc le seul que
`ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` compte
(`if (lod.<+0x78 wasAlreadyDead>) { if (lod.<+0x18 abilityOrEffect>.HasValue && == this.<+0x70>) count++ }`)
— est `UnitExtensions.HasFlag(target, UnitFlag.Overkilled = 8)`, **pas** `IsDead`. Le compte se lit
donc sur l'index d'**OVERKILL**, et `IsOverkill` étant un SEUIL, cet index vaut `k` ou `k+1` selon
la magnitude du coup fatal.

| forme | origine | verdict |
|---|---|---|
| `max(0, H-k-1) + extra` | port actuel (`master`) | VERT 13/13 sur `test_chain_leftover_hits_live.py` + `test_523_heavy_warp_flamer_live.py` ; **1/4** sur `1129 BloodyFury` (#505) |
| `(H-k) - (1 si overkill) + extra` | proposée par `#489-r1` | **RÉFUTÉE** : rend `2` là où #505 mesure `3` (le coup fatal de `1129` écrase, donc `IsOverkill` VRAI) |
| `max(0, H-k) + extra` | déduite de la lecture (« coups joués après la mort ») | **RÉFUTÉE LIVE le 2026-08-15** : 3 rouges sur `test_523_…` (dont `test_r3` : chaîne offline `[79, 83, 81]` contre live `[79, 83]` — un **maillon entier** en trop) et 2 sur `test_chain_…` (maillon `u81` : port `[1970, 1030, 0]` contre live `[1946]`) |

⚠ **La première mesure que le câblage permet contredit déjà le modèle simple.** Sur `1006`,
maillon `u79` : `H = 6`, `k = 2`, report NATIF `= 4` (extra = 1), et le port mesure
**`overkill_at_hit = 3`**, soit un index 1-based `o = 4`. `H - o + extra` rendrait **3**,
`H - o + 1 + extra` rendrait **4**. Un seul point ne peut pas trancher entre les deux.

**Ce qui manque, et c'est `#489-r2`** : la même lecture sur `1129 BloodyFury`, dont #505 prédit un
palier d'overkill DIFFÉRENT. Montage déjà écrit :
`probe_505_bloody_fury.py --only report --attackers 0,1,3 --attacks 3 --main-hp 3000,10000,15000,21000`,
auquel il suffit d'ajouter la lecture de `overkill_at_hit` du 1er maillon — champ que cette tranche
vient de publier.

### 4.3 Volet (b) — « chaque maillon repart d'une attaque NEUVE » : PRÉMISSE FAUSSE

La fiche en fait un défaut, via le canal `#419-r3` (`isOutsideAttack`). **C'est le natif.**
`IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` pousse
lui-même `processor.<0x3a = StartAttack>(caster, target, options)` **avant chaque maillon**, et
`IdunBattle.Operations.StartAttackOperation$$Execute` fait, verbatim :

```
EvaluateAbilitiesImmediately(5 = PreAttack, entities)
unit      = UnitExtensions.GetUnit(target, state)
blockIds  = (unit == null) ? new List<int>() : unit.<+0x10>.ToList()
attack    = new OngoingAttack(<...>, blockIds)          # <-- NEUVE
<battleQuery slot 0x1e>(attack)                          # <-- EMPILEE
```

⇒ `hit_index0 = 0` / `crit_allowed0 = True` par maillon **est** le comportement natif. L'écart
mesuré par `#489` (« `hits=3` demandés au 2e maillon → port en applique 2, natif 3 ») a donc une
autre cause, non tranchée ici : le candidat lisible est la formule de coups partagée
(`AttackHitsWithModifiersFormula`, `applied_hits` ≠ `hits` dès que la cible porte
`LightCover`/`Parry`/`Camouflage`).

---

## 5. Ce que la validation a coûté, et ce qu'elle a sauvé

La loi `max(0, H-k)` **a été écrite, commitée, puis retirée**. Elle passait le cliquet offline
qu'elle s'était donné (un balayage exhaustif confronté à un re-jeu écrit dans le même mouvement) et
elle réconciliait deux fiches. Ce sont les **deux tests live** qui l'ont tuée — et il a fallu, pour
l'établir, monter un worktree détaché sur `origin/master` et y rejouer les mêmes fichiers : sans
cette baseline, « 3 rouges » se lisait aussi bien comme « le montage est cassé » que comme « ma loi
est fausse ». `master` était vert **13/13**.

Corollaire d'outillage : `probe_523_heavy_warp_flamer.py::left_over_attendu` **ré-implémentait** la
loi. Un jumeau de formule compare le port à une formule, pas au natif — exactement la tautologie
que `#489-r1` reprochait au VERDICT-4 de `probe_489`. Il **délègue** désormais au foyer.

---

## 6. Verdicts

| item | énoncé de la fiche | verdict |
|---|---|---|
| `#889-r2` | « sémantique NON lue, aucun lecteur de `options+0x40` » | **PÉRIMÉ + RÉSOLU** — lecteur trouvé dans `ExecuteHits`, prédicat lu verbatim, canal porté et câblé sur les 2 phases de `1217` |
| `#1030-r4` | « `AttackWithAbilityDamage` ne thread pas le bonus de perçage » | **PRÉMISSE FAUSSE** — le natif zéroise `attackModifiers` sur cette famille. Écart RÉEL trouvé et réparé chez `ChainLeftOverHitsAttackDamage` (famille ATTACK) |
| `#512-r3` | « `On(9)` n'est émis par AUCUNE ability » | **PRÉMISSE FAUSSE** — émis par `after_hit_ability_attack`. Reste la GRANULARITÉ → `#512-r4`. Correction de RE : **cinq** émetteurs de `FinishAttack`, pas quatre |
| `#489-r1` (a) | « bloquant : aucun flag d'overkill exposé » | **PÉRIMÉ** — étage porté depuis #462-r4e-o-r1, câblage fait |
| `#489-r1` (a) | « la loi `(H-k) - (1 si overkill)` reproduit 6/6 » | **FAUX** (réfutée par #505). Le correctif déduit de la lecture est réfuté LIVE à son tour → `#489-r2` |
| `#489-r1` (b) | « le port monte chaque maillon en attaque NEUVE » | **PRÉMISSE FAUSSE** — `StartAttackOperation$$Execute` crée et empile une `OngoingAttack` neuve à chaque maillon |

## 7. Résidus ouverts

* **`#489-r2`** — la loi de `GetLeftOverHits` se lit sur l'index d'OVERKILL, pas de MORT ; il manque
  le point qui sépare `H-o` de `H-o+1`. Montage écrit, entrée désormais publiée.
  → **SUITE (2026-08-18) : cette prémisse est RÉFUTÉE**, et le montage proposé ici était une
  tautologie. Le site (b) d'`AddLeftoverHit` pousse lui aussi un flag VRAI, donc `o` n'entre pas
  dans le compte. Détail, dix points natifs et le verrou restant :
  `case-512r4-489r2-cardinalite-on9-et-loi-du-report.md` §2.
* **`#512-r4`** — `On(9)` par FEUILLE au lieu de par CIBLE ; mord sur `1088 HellfyreMissileRack`.
  → **RÉSOLU (2026-08-18)**, et l'écart avait **trois** porteurs, pas un (s'y ajoutent le FOLD de
  l'attaque normale et les N transferts d'`HazeOfCorruption`) :
  `case-512r4-489r2-cardinalite-on9-et-loi-du-report.md` §1.
