# case-1065 — deux passifs de SUMMON : un GAP franc, et une ZONE-GRISE qui n'en était une que par sa 5ᵉ face

> Build `rnca9r7q6c`. Les deux items viennent de `docs/rl/passive-ability-coverage.md`
> (« GAPS confrontables » et « ZONE-GRISE confrontable »). Ils sont appariés par la FORME de leur
> verdict, pas par leur faction — et c'est précisément le tri qui coûte le plus.

---

## 1. `FragLance` (astraSmnDeathRider) — GAP-ABSENT confirmé, PORTÉ

Deux étages natifs, **séparés côté port comme côté natif** :

| étage | symbole natif | port |
|---|---|---|
| la POSE | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FragLanceAbility` (parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` ; son SEUL corps propre est `$$GetEffectType`, corps ENTIER `return 0x5c3`) | `ABILITY_INIT_OWNER_EFFECTS["FragLance"] = ["FragLance"]` |
| le CANAL | `IdunBattle.Entities.Effects.Loki.FragLanceEffect$$CreateAdditionalHits` | `EFFECT_CLASSES["FragLance"] = FragLanceEffect` (`entities/effects/loki/hits.py`) |

⚠ **HOMONYMIE À DEUX FACES, et l'ordinal ne discrimine pas** : la CLÉ du premier registre est un
nom de `TriggeredAbilityType` (**1481**), celle du second un nom d'`EffectType` (**1475**). Même
chaîne, deux enums, deux ordinaux. Un appariement par ordinal aurait été FAUX en silence — c'est le
cran que garde `test_registres_portent_les_deux_faces`.

Le trigger a **TROIS** conjoints, lus au décompilé :

```
EffectAdditionalHits.Create(
    trigger = get_OwnerIsCaster & IsNormalAttack & IsCharging(Caster@+0x60, Target@+0x78),
    roll    = GetMinMaxDamage(this, 0) = RandomAmount(minDmg, maxDmg),
    type    = 1,
    profile = GetDamageProfile(config).Value            = Blast,
    hits    = ConfigConst(0x2f = nrOfHits, config)      = 1,
    forceOverkill = 0,
    display = GetMinMaxDamage(this, 1) = Average(minDmg, maxDmg) )
```

C'était le **dernier** des trois descripteurs `Average` non portés du résidu `#884-r2`, et le
dernier item du canal COUPS ADDITIONNELS de `case-ischarging-hits-channel.md` §2 (ligne 11). Il
publie le **bi-canal ROLL/DISPLAY dès son premier commit**, comme `#884` l'exigeait.

### Le ctx du canal #179 gagne DEUX clés, et aucune n'existait

`get_OwnerIsCaster` était déjà servi (`owner_id`/`att_id`, #1006). Les deux autres conjoints ne
l'étaient pas : `is_normal_attack` et `is_charging` ont été **threadés par les DEUX façades COMBAT**
(`damage_ops/normal.py` = `(True, _charging)` — le `_charging` DÉJÀ calculé par le foyer unique
`battle_query_is_charging`, aucun prédicat re-dérivé ; `damage_ops/ability.py` = `(False, non
mesuré)`) et par la **façade PRÉDICTION** de l'attaque normale (`_att_ctx["is_charging"]`, déjà
calculée pour le canal DÉGÂT). Tri-état partout : `None` ⇒ le gate rend FAUX, jamais permissif.

Le chemin DRONE de la prédiction (`MV71SniperDroneSquad`) ne les thread PAS, et c'est **écrit au
site** : aucun descripteur gaté sur ces clés n'a de porteur qui l'emprunte.

### Mesure live — greffe, 3 régimes, 2 boards

Porteur SUMMON ⇒ **greffe** (`case-92` §5bis) : le régime discriminant EXIGE de piloter le pas du
caster, or un summon ne se commande pas (#291). Greffon `astraBullgryn` (HERO mêlée du pool),
`replace=True`.

| régime | live | offline AVANT | offline APRÈS |
|---|---|---|---|
| **CHARGE** (MC1_67/777) | n=5 `[4682, 2533, 3411, 3417, 2401]` | n=4 `[4682, 2533, 3411, 3417]` — **ROUGE** | n=5, bit-exact |
| **STEP_ADJACENT** | n=4 | n=4 (déjà d'accord) | n=4, bit-exact |
| **NO_STEP** | n=4 | n=4 | n=4, bit-exact |
| **CHARGE** (C1_25/31337) | n=5 `[1645, 2369, 2268, 2356, 1871]` | n=4 | n=5, bit-exact |

Les 4 coups d'ARME étaient DÉJÀ bit-exacts : la divergence était localisée au **nombre** de coups.
Le natif SÉPARE les deux régimes (5 contre 4), donc le vert n'est pas trivial.

**Épreuve par MUTATION** : gate `IsCharging` retiré ⇒ tombent **exactement** `STEP_ADJACENT`,
`NO_STEP` et la garde offline ; `CHARGE` reste vert. Le test discrimine donc le GATE, et rien
d'autre.

### Le HARNAIS mentait, et il aurait fait conclure à un port faux

Première mesure après le port : live n=5, offline n=4 — **avec un port correct**. Cause :
`_charge_regime.replay_offline` ne lisait que `per_hit`, qui ne porte QUE les coups d'ARME. Le canal
#179 est une sous-opération SÉPARÉE côté port (`additional_hits`) comme côté natif
(`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`, frère du groupe d'arme), alors que
le LIVE ne distingue pas : le harnais compte TOUT événement caster → cible. Le helper publie
désormais `per_hit_all` (arme puis canal #179, l'ordre natif) ; `per_hit` est inchangé pour ses
appelants existants.

---

## 2. `FloatingDeath` (tyranSmnSporeMine) — ZONE-GRISE TRANCHÉE : 1 face sur 5 était portée

**Une** entrée de `passiveAbilities`, **CINQ** classes natives (lues dans `frida/classes.tsv`) :

| classe native | ce qu'elle fait | avant | après |
|---|---|---|---|
| `FloatingDeath_InitAbility` | `AddTrait(Owner, 0x41a = PermaDeath, isTemporary = 0)` sur `<DSLTriggers+0x30>` | — | **non recâblée, MESURÉ** (§2bis) |
| `FloatingDeath_AttackAbility` | LA DÉTONATION | non | **PORTÉE** |
| `FloatingDeath_ChainAbility` | la RÉACTION EN CHAÎNE | non | **PORTÉE** |
| `FloatingDeath_ExtraMovementAbility` | +1 MOUVEMENT sous bulle synapse | non | **PORTÉE** |
| `FloatingDeath_NormalAttackAbility` (ACTIVE 1146) | substitution d'attaque normale | **oui** | oui |

**C'est la 5ᵉ qui faisait la zone grise.** `services/custom_normal_attack.py` porte
`CUSTOM_NORMAL_ATTACK_BY_PASSIVE["FloatingDeath"] = "FloatingDeath_NormalAttack"` — un câblage
RÉEL, keyé sur le nom gameconfig — et `1146` porte son `TARGETING_OPTIONS` et son appartenance à
`REGULAR_ATTACK_ABILITY_TYPES`. Mais l'audit range ce site en zone `services`, pas `runner`, donc
hors du canal **B**. Vérifié par exécution : `1243` n'était dans **aucun** des sept registres de
`dispatch/registry.py` (`ABILITY_TRIGGERS`, `TRAIT_TRIGGERS`, `ACTIVE_ABILITY_TRIGGERS`,
`PASSIVE_HELPER_ABILITY_TRIGGERS`, `RELIC_ABILITY_TRIGGERS`, `CUSTOM_TRIGGERED_ABILITIES`,
`EFFECT_TRIGGERS`) ni dans `TRIGGERED_ABILITY_BEHAVIOURS`, et `EffectType` 1314 n'avait aucune
classe. **Une référence en code n'est pas un câblage — mais un lookup keyé sur le nom en est un :
les deux coexistaient ici, sur deux faces différentes.**

### 2bis. Pourquoi `FloatingDeath_InitAbility` n'entre PAS au registre

Ce n'est pas un renoncement, c'est une mesure. **(a)** `PermaDeath` est DÉJÀ dans les traits
STATIQUES du kit des DEUX porteurs (`tyranSmnSporeMine` : `['Summon','InstinctiveBehaviour',
'Flying','PermaDeath']` ; `tyranNpc6SporeMine` : les trois derniers) ⇒ l'`AddTrait` natif est
IDEMPOTENT sur tout porteur réel, observable **NUL**. **(b)** Le runner ne rejoue pas
`On(0x21 = AbilityInit)` : il charge un état où le natif l'a déjà joué (même doctrine que
`runner/abilities/genestealer.py` et `runner/abilities/loki/healing_balms.py`). Une classe de port
n'ajouterait aucun observable et exigerait un vecteur d'événement inexistant. Résidu `#1065-r2`.

### Le cran qui SÉPARE cette détonation des deux novas de mort déjà portées

Les deux clusters écoutent le **MÊME** événement `On(2 = PreUnitDeath_2)`. `Explodes` et
`PutridExplosion` (`loki/death_nova.py`) passent par le helper `OnDeathEvent(a = 1, …)`, donc
**SANS** gate overkill — elles partent même en overkill. `FloatingDeath_AttackAbility`, lui,
construit son `On(2)` **à la main** et ajoute explicitement `op_LogicalNot(TargetIsOverkilled)` :
un overkill **ÉTEINT** la détonation. Recopier le voisin de forme aurait été faux, et invisible.

Autres lectures qui ne se devinent pas :
* `AdjacentEnemies(Owner, unique = 1, selectionType = 3)` est la surcharge **A** — le 3ᵉ argument
  est un `CONCAT71(., 1)`, donc un BOOLÉEN, pas une entité (la surcharge B prend une ancre) ;
* `IsInTeamSynapseRange` passe `0x41c` à `IsInAuraRangeTrigger`, et ce paramètre est un
  **`EffectType`** (1052 `Synapse_Effect`) — la signature est LUE (`IsInAuraRangeTrigger.cs`). Le
  même ordinal 1052 nomme `Ambush` dans `UnitTrait` : la confusion aurait été silencieuse ;
* `<DSLTriggers+0x28>` est `IsTurnOfUnitTrigger(Owner, state)` — c'est le SEUL trigger du binaire
  dont le ctor ait la forme `(ITargetsSelector, IMatchState)`, et `InitializeShared` le construit
  avec exactement ce couple.

### Mesure live — greffe adverse, détonation sur le tueur

Porteur SUMMON ⇒ greffe, pour la même raison qu'au §1 (il faut choisir QUI tue et QUAND).
`FloatingDeath` greffé sur `necroDestroyer` (a-units, `--hp-target 9000` ⇒ mort **hors overkill** :
`IsOverkill` compare `(maxHP − curHP) + dmg` à `2 × maxHP`), tué au contact par `astraBullgryn`,
qui est donc le seul ennemi adjacent au moment de la mort.

| | live | offline |
|---|---|---|
| PV du tueur après l'attaque (MC1_67/777) | **113572** | **113572** (bit-exact) |
| avec le port MUTÉ (`matches` → `return False`) | 113572 | **120000** (PV pleins) |

Le delta du mutant, **6428**, EST la détonation. Le vert n'est donc pas trivial.

---

## 3. Ce qui n'est PAS couvert

* **Les faces CHAÎNE et MOUVEMENT ne sont gardées que par leurs GATES offline** — la première
  exige DEUX porteurs adjacents de même `visualId`, la seconde une bulle `Synapse` d'équipe
  (`tyranNeurothrope` est au pool, donc c'est un montage à écrire, pas un mur). Résidu `#1065-r1`.
* **Le porteur NATUREL n'est confronté ni pour l'un ni pour l'autre item** : les deux mesures
  passent par une GREFFE sur une unité du pool. C'est le seul chemin qui rende le régime
  PILOTABLE ; la chaîne summoner → summon (`LeadingTheCharge` d'`astraDreir`,
  `SporeMineLauncher` de `tyranBiovore`) reste à observer par les `changes` d'un `endturn`.
* **La face PRÉDICTION de `FragLance`** est threadée (`_ah_ctx` de `normal_attack.py`) mais **non
  mesurée** : aucun oracle `aiPlaybookPredict` n'a été joué sur le porteur greffé.
* **`forceOverkill`** du descripteur `FragLance` vaut `0` — rien à porter ; le pendant `1` de
  `FearOfTheUnseen` reste le résidu déjà nommé dans sa propre docstring.
