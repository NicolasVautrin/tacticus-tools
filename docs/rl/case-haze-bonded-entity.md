# case-haze-bonded — l'entité BONDÉE de `HazeOfCorruption_DamageTransfer` (1077) et la chaîne à 2 relais

**Question binaire** — le prédicat de report compare-t-il l'entité **réellement bondée**, comme le
natif, et le verdict tient-il sur la chaîne à **deux relais** (`k = 2`) ?

**Verdict** : **oui, porté et validé**. Le champ `bonded` est désormais stocké sur l'instance
d'effet (mirror du champ `+0x10` du composant de bond) et les trois usages natifs le lisent. Le
montage `k = 2` est monté, joué live et confronté : **7/7 montages bit-exacts** (dégât par unité
*et* nombre de `genrand_int32`), dont **4 exercent la chaîne** (le 1er relais meurt du report). Un
**résidu d'ORDONNANCEMENT** subsiste, distinct et nommé au §5.

---

## 1. Ce que le natif stocke, et où

`IdunBattleLogic.Entities.DSLFactory$$AddBondEffect(effectType, abilityState, source, targets,
**bondedEntity**, options)` range son 5ᵉ argument — un `ITargetsSelector` — dans les
`AddEffectBehaviourOptions` qu'il passe à `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor`.

`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` itère ses cibles, écrit la cible
courante dans le contexte, puis appelle
`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$GetEffectBuilder(this, entities)`, qui :

1. évalue le sélecteur `bondedEntity` (`this+0x70`) en **`SelectSingle` → `EntityId`** ;
2. si l'id est **non nul**, construit l'`EffectBuilder` sur
   `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder` (sinon sur le
   builder d'effet **ordinaire** — un bonded nul ⇒ **aucun bond**).

`…$$DefaultBondEffectBuilder(id, abilityState, bondedEntityId)` crée le blueprint
`IdunBattle.Entities.Blueprints$$BondEffect(id)`, y recopie l'`AbilityStateReference`, puis écrit
`bondedEntityId` dans le champ **`+0x10`** du composant de bond de l'entité-effet. C'est **ce champ
exact** que relit `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId(effect)`, source du nœud
`IdunBattleLogic.Entities.DSLFactory$$BondedEntityFromEffect` /
`IdunBattle.Entities.Effects.ABondEffect$$BondedEntitySelector`.

Côté `HazeOfCorruption`, les **deux** poses du target-finder passent le **même** bondedEntity :

```
IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour
    if Count(units) > 0 : AddBondEffect(0x435, absRef, Target@0x178, Get(units,0), Self@0x148, One)
    if Count(units) > 1 : AddBondEffect(0x435, absRef, Get(units,0), Get(units,1), Self@0x148, One)
```

seule la **source** change (`Target@0x178` puis `Get(units,0)`) : la chaîne relie *cible initiale →
relais 1 → relais 2*, mais les deux maillons sont bondés **au porteur du passif**.

Le bonded a **trois** consommateurs, tous dans l'effet 1077 :

```
IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger
    ( OnDeath(1,1) & ( TriggeringAbilityIs(AbilityOrEffect(0x435)) | AreEqual(Actor@0x158, bonded) )
      | On(0x2e) | On(0x35) ) & IsAlive(bonded) & AreEqual(Target@0x178, EffectSource(Effect@0x150))
IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour
    Attack(bonded, Owner@0x148, RemoveEffect + N x AttackDamage(bonded, Owner@0x148, ...))
```

— `AreEqual(Actor, bonded)`, `IsAlive(bonded)`, et **l'attaquant** du report.

## 2. Ce que le port faisait, et pourquoi ça a survécu

Le 5ᵉ argument n'était pas transporté : l'instance d'effet ne portait pas le bonded, et les trois
usages étaient rabattus sur `ev.killer_id` — le gate d'égalité devenant l'**inférence** « le tueur
porte `HazeOfCorruption` ».

Elle coïncide dans tout montage réel **parce qu'il n'existe qu'UN porteur non-npc** :
`deathBlightlord` (les quatre autres — `deathBossBlightlord`, `deathBossBlightlordLHE`,
`deathNpc4BlightlordTerminator`, `deathNpcBlightlord` — sont `npc`, donc hors jeu). Et dans la
chaîne, l'auteur du coup fatal du 1er relais **est** le bonded, puisque le natif fait attaquer le
bonded (`Attack(bonded, …)`). ⇒ **aucun montage live ne peut discriminer les deux lectures.**

C'est donc un **test offline** qui tranche
(`test_haze_bonded_chain_live.py::test_le_bonded_discrimine_deux_porteurs_du_meme_passif`) : effet
bondé à Maladus A, coup fatal porté par Maladus B (même passif).

| lecture | `matches` |
|---|---|
| bonded **lu sur l'instance** (`AreEqual` natif) | `False` |
| bonded **inféré du kit du tueur** (avant case-haze-bonded) | `True` — faux positif |

## 3. Le port

* `BaseEffect.bonded` — attribut de classe (pas un field dataclass : la factory reste intacte),
  documenté comme le mirror de `+0x10`. Distinct de `source` (`EffectComponent.SourceUnit @+0x10`)
  et de `target` (`@+0x14`) : sur 1077 les **trois** sont trois unités différentes.
* `AddEffectOperation.execute(..., bonded=)` — écrit le champ à la création de l'entité-effet,
  exactement là où le builder natif le fait. `None` ⇒ builder ordinaire.
* feuille `AddBondEffect(..., bonded_ref=)` — le 5ᵉ argument natif, évalué à l'exécution
  (`resolve_unit`, mirror de `SelectSingle` → `EntityId`).
* `HazeOfCorruptionTargetFinderAbility` passe `bonded_ref=Caster()` (`Self@0x148`) sur les **deux**
  poses ; `HazeOfCorruptionDamageTransferTrigger` lit `_bonded_id()` pour les trois usages.

**Écart nommé (contexte du sélecteur `bondedEntity`)** : le natif a déjà écrit la cible courante
dans le slot `Target` du contexte (`param_3[4] = lVar7`) quand il appelle `GetEffectBuilder` ; le
port évalue le sélecteur au contexte d'entrée. Sans effet pour tout `bondedEntity` qui ne dépend pas
de la cible courante — c'est le cas du seul call-site renseigné (`Self@0x148`).

**Repli assumé (canal de SEED, pas approximation de port)** : `decisionView.effects` **ne publie
pas** le `BondedEntityId` (vérifié : aucun champ `bonded` dans `frida/`). Un effet 1077 *seedé*
retombe donc sur l'ancienne inférence. Le chemin de production ne passe jamais par là : le
target-finder tire et bonde dans la **même action** que le coup fatal.

## 4. Deux corrections que le montage `k = 2` a rendues nécessaires

### 4.1 Le gate anti-chaîne lisait un canal que le vecteur mort ne porte pas

`IdunBattleLogic.Entities.DSLFactory$$TriggeringEffectIs` et
`IdunBattleLogic.Entities.DSLFactory$$TriggeringAbilityIs` sont **le même code** : même slot
`AbilityEntities+0x138`, même `DirectAbilitySelector(AbilityOrEffect(x))`, même ctor de trigger. Le
port en a **deux** canaux — `ev.triggering_effect` (posé par les vecteurs qui le portent) et
`state.triggering_ability` (le foyer unique de l'écriture de
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute`, tenu par
`triggers/dispatch/core.py::evaluate_trigger_operation`). Le vecteur **mort** ne porte que le second.

⇒ `HazeOfCorruptionDamageTransferTrigger.TRIGGERED_ABILITY_ID = 0x435`, et les deux gates Haze
lisent `_triggering_ability_or_effect(state, ev)`. Sans ça, `NOT TriggeringEffectIs(0x435)` était
**permissif** et le port tirait un coup bonus Toxic à **chaque** mort causée par un report.

### 4.2 `OnDeath` ne vise pas `PreUnitDeath`

`IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent(eventId, allowOverkill, allowShield)`, relu
verbatim :

```
OnPreDeath(a, b) -> OnDeathEvent(**1** = PreUnitDeath, a, b)      [HazeCorruption_BonusHitAbility]
OnDeath(a, b)    -> OnDeathEvent(**0** = UnitDeath,    a, b)      [le report 1077]

allowOverkill == 0 -> AND  NOT HasFlagAbilityTrigger(Target@0x178, 8 = Overkilled)
allowShield   == 0 -> AND  NOT CurrentShieldAmountFormula(Target@0x178, 0x1b)
```

Les deux volets Haze partageaient `PreUnitDeath` côté port. L'ordre natif de
`IdunBattle.Operations.KillUnitOperation$$Execute` étant `On(1) → On(2) → On(0) → On(0x37) →
On(0x36)`, le coup **bonus** précède structurellement le **report**, au lieu de dépendre de l'ordre
d'itération du registre. `event_id = UnitDeath` ; les 44 tests LIVE des quatre fichiers Haze restent
verts après la bascule, et l'attendu offline qui figeait la lecture fautive est corrigé.

Corollaire de lecture : `OnPreDeath(1, 0)` du coup bonus **n'a aucun gate d'overkill** (a = 1) mais
exige une cible **sans bouclier** (b = 0) ; `OnDeath(1, 1)` du report n'a ni l'un ni l'autre.

## 5. Mesures — `k = 2`, board `MC1_67`

Montage (`probe_220_haze_bonded_chain.py`, réutilise `_drive_pool` de
`probe_207_haze_pool_ladder.py`) : `deathBlightlord` (C) attaque `astraBullgryn` (T) ; les **deux**
voisins communs de C et T portent `astraDreir` et `astraOrdnance`. Positions **pilotées**, caster
jamais déplacé, `--crit 0,0 --block-target 0,0`.

### 5.1 Témoin direct du champ

Le flux natif publie `BondEffect_BondedId` sur chaque pose. Sur **6 seeds**, les deux bonds ont des
**sources distinctes** et un **bonded identique = le caster**, et le port stocke exactement la même
paire :

```
BONDS natifs (effectId, source, bonded, rem) = [[107, 77, 83, 1], [108, 81, 83, 1]]
BONDS port   (source, target, bonded, pose)  = [[77, 81, 83, true], [81, 79, 83, true]]
```

### 5.2 Confrontation live, PV cible 5000

| seed | chaîne | `genrand` natif / port | dégât par unité (live vs port) |
|---|---|---|---|
| 777 | oui (2 reports) | 11 / **11** | 5000 / 234 / 5000 — **3/3** |
| 5   | oui | 11 / **11** | 5000 / 950 / 5000 — 3/3 |
| 21  | oui | 12 / **12** | 5000 / 1402 / 5000 — 3/3 |
| 42  | oui | 11 / **11** | 5000 / 1160 / 5000 — 3/3 |
| 88  | non (relais 1 survit) | 10 / **10** | 5000 / 4299 / 0 — 3/3 |
| 13  | non | 9 / **9** | 5000 / 3042 / 0 — 3/3 |
| 99  | non | 9 / **9** | 5000 / 3438 / 0 — 3/3 |

**7/7** sur les deux axes ; **4/7** exercent la chaîne (le 1er relais meurt du report, le 2ᵉ encaisse).
Les 3 montages « sans chaîne » sont le contrôle : les deux bonds sont posés, un seul report part.

### 5.3 Contrefactuel — le correctif est-il porteur ?

Rejeu du **même état figé** avec les deux lectures d'avant case-haze-bonded (`probe_220 --cf`) :

| seed | `genrand` natif | port | contrefactuel | PV du 2ᵉ relais (natif = port) | contrefactuel |
|---|---|---|---|---|---|
| 777 | 11 | 11 | **14** | 4766 | **2670** (−2096) |
| 21  | 12 | 12 | **15** | 3598 | **1502** (−2096) |

Trois tirages et 2096 PV de trop, à chaque fois : le coup bonus Toxic que le natif refuse partait à
la mort de chaque relais.

### 5.4 Ce que le régime OVERKILL révèle — résidu d'ORDONNANCEMENT (CLOS, `case-haze-ord.md`)

> **CLOS le 2026-07-29.** Le résidu décrit ci-dessous est porté et validé :
> `RecordKillOperation$$Execute` ENQUEUE, `InputMessageProcessor$$VerifyDeaths` DRAINE (boucle
> **non ré-entrante**, `killTrigger` transporté dans l'entrée de file), et le **site (A)**
> d'`ApplyDamageOperation$$Execute` `return`e sans rien émettre. Mesure du même montage :
> **natif 14 == port 14**, dégât par unité 3/3, sur 3 seeds. Détail, rayon de souffle chiffré et
> non-couvert : **`docs/rl/case-haze-ord.md`**. Le texte d'origine est conservé ci-dessous parce
> qu'il porte la mesure AVANT correctif.


À PV cible **1200**, la cible meurt **en overkill dès le 1er coup**. Le flag `Overkilled` bascule
alors `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` sur son **site (A)** : la
`LeftOverDamage` est poussée **sans appliquer ni émettre** — d'où l'absence d'événement pour les
coups 2, 3 et le coup bonus (à PV 5000, la mort n'est pas un overkill et ces mêmes coups émettent
bien un `Amount 0`).

Mesure seed 777 / PV 1200 : **natif 14 tirages, port 12**. Décomposition du natif :
`2` (target-finder) + `3` (arme) + `1` (bonus) + `4` (reports vers le relais 1) + `4` (reports vers
le relais 2). Le port n'en émet **qu'un** vers le 2ᵉ relais.

Cause : **le port draine la mort immédiatement**. `AttackDamageOperation._apply_damage_pipeline`
appelle `_fire_death_if_killed` à chaque `AttackDamage`, donc dès que le relais 1 tombe — au **milieu**
de sa série de reports. Le natif, lui, ENQUEUE la mort (`IdunBattle.Operations.RecordKillOperation$$Execute`
→ `MatchState.AddDeath`) et ne la DRAINE que par `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`
→ `KillUnitOperation$$Execute` : les **N** `AttackDamage` du `Attack(bonded, Owner@0x148, beh)` unique
sont **tous** partis quand le trigger du bond suivant lit les `LeftOverDamage`.

⇒ **résidu structurel du pipeline de mort, pas de `HazeOfCorruption`** : il concerne tout behaviour
dont plusieurs coups suivent la mort de leur cible. Le régime PV 5000 l'évite par construction (le
relais 1 meurt sur le **dernier** report), et la garde `k = 2` s'y tient volontairement — c'est
pourquoi les 45 gardes Haze n'ont bougé d'aucun chiffre après le correctif.

## 6. Gardes

`tests/engine/runner/test_haze_bonded_chain_live.py` — 18 tests :

* 6 offline de structure, dont le **discriminant** de l'égalité d'entité (§2), le champ sur
  `BaseEffect` / `AddEffectOperation`, le 5ᵉ argument de la feuille, `bonded_ref=Caster()` sur les
  deux poses, et `TRIGGERED_ABILITY_ID == 0x435` ;
* 4 seeds × chaîne bit-exacte (RNG + dégât par unité) ;
* 6 seeds × témoin `BondEffect_BondedId` natif == bonded porté ;
* 2 seeds de contrôle sans chaîne.

Non-régression `k = 1` : `test_haze_of_corruption_transfer_live.py`, `test_haze_rng_flow_live.py`,
`test_haze_of_corruption_rng_live.py` — **27/27**. Gardes de pose d'effet :
`test_anvil_shield_stun_live.py`, `test_effect_duration_rounds_live.py`,
`test_chain_after_refused_addeffect_live.py` — **12/12**.

## 7. Non couvert

* ~~Le **régime overkill** du `k = 2` (§5.4)~~ — **CLOS** (`case-haze-ord.md`), et désormais
  GARDÉ par `tests/engine/runner/test_death_queue_ordering_live.py` (3 seeds × PV 1200).
* Le `bonded` des **autres** call-sites d'`AddBondEffect` (Taunt de `GetEmRuntz`/`CrushingClaws`,
  `ValkyrieStrike`, `AnvilShield`, `HolyDuel`, `MalleusRocketLauncher`, `DevastatingRefrain`…) :
  le paramètre est optionnel, ces feuilles le laissent `None` ⇒ comportement **inchangé**. À
  renseigner au fil de leurs cas respectifs — le canal existe désormais.
* Le **seed** d'un effet 1077 depuis `decisionView` (le canal ne publie pas le bonded) : point
  d'ancrage à hooker = le champ `+0x10` du composant de bond, exposé par
  `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`. Aucun rebuild/reinject n'a été fait
  pour ce cas.
* Le repli `GetPersistentData` de `…$$GetLeftOverDamages` (résidu pré-existant, inchangé).
