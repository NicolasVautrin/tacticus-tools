# case-ischarging-hits — l'inventaire REEL des consommateurs d'`IsCharging`, et le port du canal COUPS

> **Build** `gqfc5mff6c`. Suite de `case-231` (socle) et `case-r32` (retrofit du canal DEGAT).
> Ici on ne retrofite RIEN : on **re-enumere** les consommateurs, et on constate que le tas
> « deja porte, gate faux » est **VIDE**. Le travail utile est ailleurs — un canal entier
> (`CreateEffectHitsBonusForAttack`) n'etait porte sur AUCUN de ses consommateurs de charge.

---

## 1. La question, et sa reponse

> Parmi les consommateurs natifs du noeud `IdunBattleLogic.Entities.DSLFactory$$IsCharging` qui ne
> sont pas les trois effets extra-degat de `case-r32`, lesquels sont portes cote offline avec un
> gate FAUX ou ABSENT ?

**AUCUN.** Le tas (a) — « consommateur deja porte, gate faux ou absent » — est **VIDE**, et c'est un
resultat, pas une absence de mesure : les **onze** autres xrefs ne sont portees sur **aucun** de
leurs canaux. Il n'y a donc nulle part ou un proxy `has_moved` pourrait sur-accorder : le canal
n'existe pas du tout.

La seule trace du proxy qui restait etait **documentaire** : la docstring d'`entities/triggers.py::
IsCharging` affirmait encore (⚠, l.652-656) que « les effets extra-degat du lot
SmashaEad/AvalancheOfMuscle/FeederTendrils modelisent ce meme noeud par `has_moved` ». C'etait vrai
la veille, faux depuis `case-r32` — et c'est exactement la classe d'affirmation perimee qui produit
la prochaine fausse conclusion. Corrigee dans le meme commit.

---

## 2. Le compte herite etait FAUX — et sa ventilation aussi

`case-r32` §7 annonce « **les 12 autres xrefs** d'`IsCharging` (canaux hits / crit / percage /
triggers) ». Re-enumeration a la source (`list_xrefs` sur
`IdunBattleLogic.Entities.DSLFactory$$IsCharging`) :

* **18** references au total, dont **2 DATA** (table de methodes) et **16 CALL** ;
* les 16 CALL moins les 3 du canal DEGAT (`case-r32`) moins les 2 de `TacticalPrecision`
  (`case-231`) font **11**, pas 12.

La ventilation est elle aussi incomplete : elle nomme quatre canaux, il y en a **huit**. Manquaient
(a) la face **DEFENSEUR** du canal COUPS (`ObeisanceGenerators`, un hit *reduction* gate
`OwnerIsTarget`, pas un bonus), (b) le canal **COUPS ADDITIONNELS** (`FragLance`, qui n'est pas un
bonus de coups mais une **attaque separee** avec son propre profil de degat), (c) la face
**ABILITY ACTIVE** (`FeederTendrils_NormalAttackAbility`, ou le predicat n'est meme pas un noeud
d'arbre : il est **evalue imperativement** dans le corps), et (d) `TacticalPrecision$$GetIsChargingTrigger`,
qui est une xref a part entiere. « percage » designe en realite une **ActiveCondition**
(`BloodChalice_ExtraPiercing`), pas un canal de percage.

### Les 16 xrefs, par canal

| # | Symbole natif appelant | Canal | Effet / ability | Porte ? | Gate |
|---|---|---|---|---|---|
| 1 | `IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack` | DEGAT | effet 1025 | **oui** | **juste** (`case-r32`) |
| 2 | `IdunBattle.Entities.Effects.Loki.FeederTendrils_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` | DEGAT | effet 1243 | **oui** | **juste** (`case-r32`) |
| 3 | `IdunBattle.Entities.Effects.Loki.BlackRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` | DEGAT | effet 1343 | **non** (canal degat) | — bloque `N10` |
| 4 | `IdunBattleLogic.Entities.Abilities.Active.Loki.TacticalPrecisionAbility$$ExecuteBehaviour` | ABILITY (branche) | 1154 | **oui** | **juste** (`case-231`) |
| 5 | `IdunBattleLogic.Entities.Abilities.Active.Loki.TacticalPrecisionAbility$$GetIsChargingTrigger` | ABILITY (helper) | 1154 | **oui** | **juste** (`case-231`) |
| 6 | `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateEffectHitsBonusForAttack` | COUPS attaquant | effet 1223 | **PORTE PAR CE CAS** | juste |
| 7 | `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus` | CRIT | effet 1223 | **oui** | **juste** (`case-ischarging-crit-channel`, `N14` ferme) |
| 8 | `IdunBattle.Entities.Effects.Loki.RedThirst_ExtraDamageAndHitEffect$$CreateEffectHitsBonusForAttack` | COUPS attaquant | effet 1322 | non | absent (canal absent) |
| 9 | `IdunBattle.Entities.Effects.Loki.UnstoppableFerocityOwnerEffect$$CreateEffectHitsBonusForAttack` | COUPS attaquant | effet 1032 | non | absent (canal absent) |
| 10 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ObeisanceGenerators_HitReductionEffect$$CreateEffectHitsBonusForAttack` | COUPS **defenseur** | effet 1128 | non | **NON PERTINENT** (§4) |
| 11 | `IdunBattle.Entities.Effects.Loki.FragLanceEffect$$CreateAdditionalHits` | COUPS ADDITIONNELS (attaque separee) | effet 1475 | non | absent (canal absent) |
| 12 | `IdunBattle.Entities.Effects.Loki.BloodChalice_ExtraPiercingEffect$$CreateActiveCondition` | ACTIVE-CONDITION | effet 1369 | non | absent (effet absent) |
| 13 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AggressiveOnslaught_PrepareAbility$$CreateBehaviour` | TRIGGER (SetPersistentData) | 1248 | non | absent (face COMBAT non portee) |
| 14 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AggressiveOnslaught_SummonAbility$$CreateTrigger` | TRIGGER | 1248 | non | absent (face COMBAT non portee) |
| 15 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateTrigger` | TRIGGER | 1478 | non | **NON PERTINENT** (§4) |
| 16 | `IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour` | ABILITY normale (imperatif) | 1120 | **partiel** | §5 |

⚠ **Deux corrections a la fiche `case-r32`** :

* elle dit « les trois effets extra-degat **deja recables** ». Seuls **DEUX** le sont (1025, 1197
  alias `FeederTendrils_ExtraDamage`) ; le canal degat de `BlackRage` (1343) n'est porte sur
  **aucun** etage — `N10` le dit deja, mais le libelle « trois recables » le contredit.
* l'id d'effet de `FeederTendrils_ExtraDamage` est **1243** dans `entities/effect_type.py`, pas 1197
  (1197 = `MasterOfTheTutelaries`). Les commentaires du port citent 1197 partout. Non touche ici
  (le registre de la factory est indexe par NOM, pas par id, donc le port n'en depend pas) —
  mais l'ecart est reel et signale.

### Ce que chaque arbre non porte contient EXACTEMENT (decompile = verite)

```
SagaOfTheWarriorBorn_OwnerEffect$$CreateEffectHitsBonusForAttack
    EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(owner@0x148, target@0x178),
                             ConfigVar(0x13 = extraHits, GetAbilityState(effect), config@+0x60),
                             <AbilityOrEffect recopie de effect+0x14..+0x2c> )

SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus
    EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(owner@0x148, target@0x178),
                             ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect), config@+0x60),
                             <meme AbilityOrEffect> )

RedThirst_ExtraDamageAndHitEffect$$CreateEffectHitsBonusForAttack
    EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(owner@0x148, target@0x178),
                             ConfigConst(0x4e1 = RedThirst 1249, owner@0x148, 0x2b = extraHit) )

UnstoppableFerocityOwnerEffect$$CreateEffectHitsBonusForAttack
    EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(caster@0x160, target@0x178),
                             Direct( AbilityConfiguration.GetNumberConstant(config@+0x60,
                                                                           0x2b = extraHit) ) )

ObeisanceGenerators_HitReductionEffect$$CreateEffectHitsBonusForAttack
    EffectBonus.ForAdditionWithMinimum(
        get_OwnerIsTarget & IsCharging(caster@0x160, owner@0x148) & IsMeleeAttack,
        ConditionalAmount( HasTrait(caster@0x160, 2),
                           Get(-GetNumberConstant(0x4b)), Get(-GetNumberConstant(0x2c)) ),
        Get(1), AbilityOrEffect(0x461 = 1121) )

FragLanceEffect$$CreateAdditionalHits
    EffectAdditionalHits.Create(
        get_OwnerIsCaster & IsNormalAttack & IsCharging(caster@0x160, target@0x178),
        GetMinMaxDamage(0), 1, GetDamageProfile(config).Value,
        ConfigConst(0x2f), 0, GetMinMaxDamage(1), 0 )

BloodChalice_ExtraPiercingEffect$$CreateActiveCondition
    IsCharging(owner@0x148, target@0x178)          # noeud UNIQUE, rien d'autre

AggressiveOnslaught_PrepareAbility$$CreateTrigger    = On(5) & get_OwnerIsCaster
AggressiveOnslaught_PrepareAbility$$CreateBehaviour  =
    SetPersistentData( AbilityOrEffect(this.Id), owner@0x148, Get(<cle statique>),
                       IsCharging(caster@0x160, target@0x178) )
AggressiveOnslaught_SummonAbility$$CreateTrigger =
    ( On(0xb) & get_OwnerIsCaster )
    & ( IsPersistentData(AbilityOrEffect(this.Id), owner@0x148, Get(<cle statique>))
        | IsCharging(caster@0x160, target@0x178) )

SabreOfSacrificeAbility$$CreateTrigger =
    On(9)
    & ( IsCharging(caster@0x160, target@0x178)
        & ( get_OwnerIsCaster
            | ( ( AreEqual(Parent(caster@0x160), owner@0x148)
                  & IsUnitWithVisualId(caster@0x160, GetStringConstant(config, 0)) )
                & IsAdjacent(owner@0x148, caster@0x160, 3) ) ) )
```

---

## 3. Porteurs — ventiles hero / MoW / summon / npc

Derives des **669** unites du gameconfig (`lineup` 123 + `npc` 481 + `summons` 65), pas d'un
`kind == lineup`.

| Item | hero / MoW | summon (et son summoner) | npc | Confrontable ? |
|---|---|---|---|---|
| 1223 `SagaOfTheWarriorBorn_Owner` | **`spaceBlackmane`** (Ragnar) — **DANS LE POOL** | — | — | **OUI, directement** |
| 1322 `RedThirst_ExtraDamageAndHit` | — | `bloodSmnIntercessor` ← `bloodIntercessor` (Mataneo, `AggressiveOnslaught`) — **pool** | `bloodNpc1Intercessor` | oui, via summon |
| 1032 `UnstoppableFerocity_OwnerEffect` | — | `blackSmnBloodletter` / `…HSE` ← `blackPossession` (Archimatos, `Possession`/`Incursion`) — **pool** | `blackNpc1Bloodletter` | oui, via summon |
| 1475 `FragLance` | — | `astraSmnDeathRider` ← `astraDreir` (`LeadingTheCharge`) — **pool** | `astraNpc5DeathRider` | oui, via summon |
| 1369 `BloodChalice_ExtraPiercing` | **`bloodSanguinary`** (Nicodemus) — **pool** | — | — | oui, mais le poseur (ability 1175) n'a pas de face COMBAT portee |
| 1248 `AggressiveOnslaught` | **`bloodIntercessor`** (Mataneo) — **pool** | — | — | oui |
| 1120 `FeederTendrils_NormalAttack` | **`tyranDeathleaper`** — **pool** | — | 6 variantes npc | oui |
| 1128 `ObeisanceGenerators_HitReduction` | — | — | — | **NON — aucun porteur** (§4) |
| 1478 `SabreOfSacrifice` | — | — | `astraNpcDreir` (relicAbility) | **NON — npc + relique** (§4) |

---

## 4. Deux items sont NON PERTINENTS, et pour deux raisons DIFFERENTES

**`ObeisanceGenerators` (1121, effet 1128) n'a AUCUN porteur.** Balayage des 669 unites :
zero `activeAbilities`/`passiveAbilities`, zero `traits`, zero `relicAbilities`. Le nom
n'apparait que **deux fois** dans tout le gameconfig, aux deux emplacements de definition :
`/units/abilities/ObeisanceGenerators` et `/units/abilityPowerModifiers/ObeisanceGenerators`.
Aucun item ne le reference non plus. C'est de la **donnee enregistree mais morte** : le canal
existe cote natif, personne ne le porte en bataille. Ne pas y depenser d'agent.

**`SabreOfSacrifice` (1478) est une RELIQUE portee par un npc.** Il apparait a
`/units/npc/astraNpcDreir/relicAbilities[0]` et `/items/R_Crit_SabreOfSacrifice/abilityId`.
`astraDreir` (le hero du pool) ne l'a **pas** — et `rl_duel.py` ne monte aucun equipement
(`relic` : 0 occurrence dans le fichier). L'item n'est donc pas « bloque », il est **hors du
domaine confrontable du runner**.

---

## 5. `FeederTendrils_NormalAttackAbility` — le seul cas ou le predicat n'est PAS un noeud d'arbre

`IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour`
construit `IsCharging(owner@0x148, target@0x178)` puis **appelle son slot `Evaluate` (`+0x188`)
directement**, dans le corps imperatif de l'ability :

```
weapon = ALoki_NormalAttackAbility$$FindAttackWeapon(entities)      # null -> return
charging = IsCharging(owner@0x148, target@0x178).Evaluate(entities, 0x20, <sel @+0x190>)
if ( charging & WeaponProfile.get_IsMelee(weapon) ) {
    ALoki_NormalAttackAbility$$ExecuteInformWeapon(weapon, entities, 1)
    ExecuteAtomic( Heal( owner@0x148, owner@0x148, ConfigVar(0x20 = hpToHeal, ...) )
                 + AddEffect( 0x429 = 1065 Pinned, AbilityStateReference, target@0x178 ) )
    ALoki_NormalAttackAbility$$ExecuteNormalAttack(entities, weapon)
    ALoki_NormalAttackAbility$$ExecuteTriggerAbilities(entities, weapon)
} else {
    ALoki_NormalAttackAbility$$ExecuteBehaviour(entities)           # attaque normale nue
}
```

Ce que le port a deja : le **second** terme (`get_IsMelee`), recopie comme gate `is_ranged` de
`FeederTendrilsExtraDamageEffect`. Ce qu'il n'a pas : **le heal `hpToHeal` et la pose de `Pinned`
(1065) sur la cible quand Deathleaper charge en melee**. Deux operations observables, sur un
porteur du pool, jamais executees offline. Residu **`N15`**.

---

## 6. Ce que ce cas PORTE — `SagaOfTheWarriorBorn_Owner` (1223), face COUPS

Choisi comme l'unique port du tas (b) parce qu'il cumule les trois criteres : porteur **hero
directement dans le pool** (aucune chaine de summon a monter), magnitude **massive et
discretisee** (i2 : « When charging, Ragnar scores **3 additional hits** »), et canal offline
**deja existant** (`create_effect_hits_bonus_for_attack`, agrege par `hits_bonus_from_effects`
dans `AttackHitsWithModifiersFormula`).

Detail du portage, du gate a la magnitude, dans la docstring de la classe
(`engine/entities/effects/loki/hits.py::SagaOfTheWarriorBornOwnerEffect`).

**Le gate reutilise le FOYER, il ne le duplique pas** : `effects/base.py::is_not_charging(att_ctx)`,
alimente par le meme `engine/battle_query.py::is_charging` que le canal degat — cote COMBAT via
`components.charged_unit_ids`, cote PREDICTION via `scene.charged()` union
`battle_query.newly_adjacent_ids` (le pas CANDIDAT). Aucun nouveau predicat n'est ecrit.

Ce qui a du etre ouvert pour ca : le contexte du canal COUPS (`att_hits_ctx` de
`services/attack_hits_formula.py`) ne portait pas la charge. Il la porte desormais, par la
**meme cle** `is_charging` que le contexte du canal degat, threade **en DEUX lignes seulement** :

| face | ou | ce qu'elle passe | couvre |
|---|---|---|---|
| COMBAT | `runner/damage_model.py::build_hits_board` | `battle_query_is_charging(state, att, tgt)` | **les DEUX vecteurs** — `damage_ops/normal.py` ET `damage_ops/ability.py` appellent cette meme facade |
| PREDICTION | `playbook/prediction/normal_attack.py` | la valeur DEJA calculee pour le canal degat (`_att_ctx["is_charging"]`) | attaque normale predite |

Le gate lui-meme est `effects/base.py::is_charging_attack(att_ctx)` — forme POSITIVE du foyer
existant (`is_not_charging`), alignee en polarite sur `is_melee_attack` / `is_ranged_attack` : VRAI
seulement si la charge est PROUVEE. Choix delibere, et le plus fidele ici : le natif commence par
`AreEntitiesAdjacent`, donc sans positions il rend FAUX — jamais VRAI. Un contexte non threade ne
peut donc pas accorder le bonus.

### Mesure COMBAT — la garde vue ROUGE, verbatim

`probe_ischarging_saga_hits.py`, `MC1_67` / seed 777, Ragnar rank 17 (`extraHits[50] = 3`, non scale par
le multiplier — seule `extraCritDmg` est dans `variablesAffectedByRarityBonus`) :

| regime | live | offline AVANT | offline APRES |
|---|---|---|---|
| **CHARGE** | **n=10** `[1879, 1411, 1917, 1681, 2101, 1998, 1761, 1658, 1853, 2090]` | **n=7** `[1879, 1411, 1917, 1681, 2101, 1998, 1761]` — **ROUGE** | n=10, bit-exact |
| **STEP_ADJACENT** | n=7 | n=7 (deja d'accord) | n=7, bit-exact |
| **NO_STEP** | n=7 | n=7 (deja d'accord) | n=7, bit-exact |

Les **7 premiers coups etaient deja bit-exacts avant le fix** : la divergence etait localisee au
NOMBRE de coups, pas a leur valeur — decomposition par etage, aucun scalaire fitte.

### Mesure PREDICTION — 4 regimes, bornes forcees distinctes partout

`probe_ischarging_saga_prediction.py` (`aiPlaybookPredict`, l'oracle de DECISION — pas le preview
`aiPredict`). `off+chg` / `off-chg` = gate FORCE : leur ecart rend chaque MATCH probant.

| cas | montage | natif | offline | `off+chg` | `off-chg` |
|---|---|---|---|---|---|
| **A** CHARGE_CANDIDAT | distance 2, tour NEUF, tuile candidate adjacente | **14080** | 14080 | 14080 | 9856 |
| **B** CHARGE_ACQUISE | le pas est JOUE, prediction depuis la tuile courante | **14080** | 14080 | 14080 | 9856 |
| **C1** NOCHG | adjacent, tour NEUF, tuile courante | **9856** | 9856 | 14080 | 9856 |
| **C2** ADJ_NOCHG | adjacent, tour NEUF, decalage vers une AUTRE tuile adjacente | **9856** | 9856 | 14080 | 9856 |

`14080 / 9856 = 10 / 7` exactement — le rapport des nombres de coups. **Les DEUX termes sont
necessaires** : A tombe sans le terme CANDIDAT (la prediction native SIMULE le pas), B tombe sans le
terme REEL. **C2 est le regime discriminant** : le natif rend 9856, un gate `has_moved` aurait rendu
14080.

### Epreuve du fix par MUTATION adversariale

Le gate est remplace par le proxy — `build_hits_board` pose `unit_has_moved(state, att_id)` a la
place de `battle_query_is_charging(...)`, tout le reste inchange. Resultat : **exactement** les deux
tests `STEP_ADJACENT` tombent (les deux boards), `CHARGE` et `NO_STEP` restent VERTS.

```
AssertionError: STEP_ADJACENT : le port sur-applique le +extraHits (gate `has_moved` ?) --
live n=7 [1197, 1522, 1567, 1471, 1326, 1305, 1653]
offline n=10 [1197, 1522, 1567, 1471, 1326, 1305, 1653, 1453, 1587, 1676]

AssertionError: STEP_ADJACENT (C1_25/31337) : live n=7 [1204, 1220, 1126, 1403, 979, 1156, 1289]
offline n=10 [1204, 1220, 1126, 1403, 979, 1156, 1289, 1038, 1121, 1038]
```

La garde discrimine donc le GATE, et rien d'autre : ni la magnitude, ni le canal, ni le niveau.
Mutation revertee (`git diff` vide apres coup).

---

## 6bis. Le harnais mentait — et il aurait fait conclure a un port faux

Le montage `STEP_ADJACENT` de `_charge_regime.py` a produit une divergence de **+3 coups**
(`C1_25` / 31337 : live n=10, offline n=7) **avec un port correct**. Reproduit deux fois a
l'identique, donc pas un alea. Cause, lue dans la trace des poses :

    trace = [(49, (0,1) -> (0,0)), (51, ...), (53, (0,2) -> (0,1)), (53, (0,1) -> (1,1))]
                                               ^^^^^^^^^^^^^^^^^^^ le PAS DE MONTAGE du caster

Un `place()` est un `MoveUnitOperation` natif COMPLET : il appelle `UpdateCharging`, qui ecrit dans
la liste **de l'unite qui bouge**. Amener le caster (u53) d'une tuile a distance 2 vers une tuile
adjacente a la cible (u49) **CHARGE la cible avant le pas du regime**. Cote offline la charge est
INVISIBLE — `load_state` ne seede pas `UnitComponent+0x190` (aucun RPC ne l'expose, `case-r32` §7).
Le montage etait donc `CHARGE` deguise en `STEP_ADJACENT`.

**Aucun `endturn` ne repare** : la purge est `FinishUnitTurnOperation$$Execute`, PAR UNITE et sur
son activation — une fin de tour d'EQUIPE ne l'appelle pas. Un premier essai de correction par
cycle force a echoue pour exactement cette raison, et c'est la trace qui l'a montre.

Correctif retenu — **l'ordre des poses** : (1) GARER la cible a distance >= 4 de l'ancre, (2) ecarter
les autres ennemis, (3) poser le CASTER (la cible est hors adjacence, sa liste reste vide),
(4) AMENER la cible sur l'ancre — c'est ELLE qui bouge, donc c'est SA liste qui s'ecrit, et
`IsCharging(caster, target)` ne lit que celle du CASTER. Plus une **garde de regime** dans `run()` :
la geometrie effective doit valoir `(d_depart, d_arrivee) == (2,1)` pour `CHARGE` et `(1,1)` pour
`STEP_ADJACENT` / `NO_STEP`, sinon le scenario est refuse au lieu d'etre mesure de travers.

Le harnais expose desormais `plan["trace"]` (chaque pose avec sa position de depart) et
`plan["endturns"]` : c'est ce qui a permis de trancher, et ce qui permettra de trancher la prochaine
fois. `test_ischarging_extra_damage_live.py` (5 tests) a ete rejoue sur le montage corrige : vert.

---

## 7. Ce qui n'est PAS couvert

* ~~**La face CRIT de 1223**~~ — **FERMEE** (`case-ischarging-crit-channel.md`, `N14`). La premisse
  « le canal offline n'a aucun parametre de contexte » etait juste **sur le port** et fausse **sur
  le natif** : `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` passe
  l'attaquant ET la cible a `GetCritDamageBonusFromEffects`, qui batit lui-meme son
  `AbilityEntities`. Le canal etait donc a INSTRUMENTER, pas a contourner — fait en UN point
  (`AttackDamageOperation._crit_params`, la facade CRIT partagee des 3 vecteurs, exactement ce que
  `build_hits_board` est a l'axe COUPS). S'arreter etait la bonne decision : poser la face sur le
  canal muet l'aurait rendue inconditionnelle.
* **La face ability-attack du canal COUPS** : `damage_ops/ability.py` (tenu par un autre agent) ne
  thread pas `is_charging`. Sans porteur qui l'exerce aujourd'hui — l'active de Ragnar (`WarHowl`
  1106) est un buff, son unique vecteur d'attaque est son arme normale (7 coups Chain) — l'ecart
  est **structurel, pas observable**. A cabler avec le meme une-ligne que le vecteur normal.
* **1224 `SagaOfTheWarriorBorn_OtherSpaceWolves`** : effet SEPARE, pose par
  `SagaOfTheWarriorBorn_KillAbility$$CreateBehaviour` =
  `AddEffect(0x4c8, AbilityStateReference, source = owner@0x148, targets = UnitsFromFaction(Friends(owner@0x148, <radius @+0x80>, 1) - owner@0x148, 0xd, 1))`
  sur trigger `OnDeath(1) & get_OwnerIsActor & HasTrait(target@0x178, 0x10)`. RE faite, port non fait.
* **Les 4 items confrontables restants du canal COUPS / ADDITIONNELS / ActiveCondition** (1322,
  1032, 1475, 1369) — residu **`N13`** : RE faite (§2), porteurs identifies (§3), aucun porte.
  Chacun est une tranche a part entiere.
* **Les deux faces TRIGGER d'`AggressiveOnslaught`** (`SetPersistentData` + `On(0xb)`) : la face
  COMBAT du summon n'existe pas offline (seule sa face DECISION est portee,
  `playbook/aggressive_onslaught.py`), donc le gate n'a rien a garder.
