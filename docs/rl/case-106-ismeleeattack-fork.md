# case-106 — fork de port sur `IsMeleeAttack` : un fait natif, deux représentations divergentes

**Verdict : le fork était RÉEL, et l'axe DÉGÂT était du mauvais côté.** Corrigé à la source (la façade
qui omettait de threader la nature du coup) + foyer unique pour le prédicat. Confronté live sur les
deux faces, deux couples (board, seed), avec contre-cas et vérification de discriminance.

---

## 1. Le constat de départ

Le natif pose la MÊME condition sur deux canaux jumeaux du même effet :

```
IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack
IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack
    -> les DEUX : IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster
```

Le port représentait ce même fait de deux façons, au comportement DIFFÉRENT quand la nature du coup
n'était pas renseignée :

| axe | code | `is_ranged=None` (nature non threadée) |
|---|---|---|
| DÉGÂT (`create_effect_damage_bonus_for_attack`) | `if is_ranged: return None` | `None` est FALSY -> **la contribution S'APPLIQUE** |
| COUPS (`create_effect_hits_bonus_for_attack`) | `if att_ctx.get("is_melee") is not True: return None` | **la contribution NE s'applique PAS** |

Même classe structurelle que #101 (un fait natif, deux stores).

## 2. RE — ce que le natif fait exactement (décompilé = vérité)

`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` et
`IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` (consommés par
`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` /
`IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger`, qui matérialisent les nœuds
`IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack` / `$$IsRangedAttack`) partent tous deux de
`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(ability du coup)` :

| `GetAbilityAttackRangeType` | `IsMeleeAttack` | `IsRangedAttack` |
|---|---|---|
| `Nullable<AbilityOrEffect>` VIDE (pas d'ability dans le contexte) -> retourne 0 | FALSE | FALSE |
| `0` = None | FALSE | FALSE |
| `1` = Melee | **TRUE** | FALSE |
| `2` = Ranged | FALSE | **TRUE** |
| `3` = Both | `HasFlag(unit, 0x15)` ? FALSE : `AreUnitsInMelee(attPos, tgtPos)` | `HasFlag(unit, 0x15)` ? TRUE : `!AreUnitsInMelee(...)` |

Trois conséquences, toutes lues :

1. **Le natif rend un BOOL**, jamais un tri-état. Il n'a pas d'état « inconnu ».
2. **Les deux prédicats ne sont PAS complémentaires** : sur `rangeType = 0/None` (et sur ability
   absente du contexte) ils sont **tous les deux FAUX**. Il existe donc bien un état « ni mêlée ni
   distance » — mais dans cet état le natif ne se rabat JAMAIS sur mêlée.
3. Seul `rangeType = 3 (Both)` est **position-based** (`AreUnitsInMelee`) ; les autres sont **déclarés
   par l'ability**.

=> Côté port, `is_ranged=None` doit donc faire **taire les DEUX familles de gates**. C'est déjà ce que
font l'axe COUPS (`att_ctx["is_melee"] is not True`) et les auras (`ctx["is_melee"]`, cf.
`damage_model._apply_ally_attack_damage_auras` qui dérive `is_melee = (not is_ranged) if is_ranged is
not None else None`). **Seul l'axe DÉGÂT direct penchait du mauvais côté.**

## 3. Le fork est-il RÉEL ? — oui, et il est localisé sur UNE façade

Recensement complet des façades qui peuplent `is_ranged` jusqu'à
`entities.effects._attacker_effect_bonuses` :

| face | façade | nature threadée ? |
|---|---|---|
| COMBAT | `AttackDamageOperation.execute` (attaque normale) | oui — `_ranged` de `select_weapon_pierce` |
| COMBAT | `AttackDamageOperation.execute_ability_attack` | oui — `(not is_melee)`, **gaté famille ATTACK** (#45f) |
| COMBAT | `AttackDamageOperation.execute_normal_like` | **NON — c'était le trou** |
| COMBAT | `runner/operations/triggers/loki/final_justice.py` | oui — `is_ranged=False` |
| PRÉDICTION | `playbook/prediction/normal_attack.py` | oui — `_weapon_pierce` |
| PRÉDICTION | `playbook/prediction/abilities.py` | oui — `not is_melee` |
| PRÉDICTION | `playbook/psyker.py` (splash) | oui — `is_ranged=True` |
| PRÉDICTION | `playbook/fury_of_the_ancients.py` | oui — `not is_melee` |

`entities/unit_context.py::attacker_modifiers` et `damage_model.normal_attack_per_hit_range`
n'ont **aucun consommateur** (vérifié par grep) — ce ne sont pas des vecteurs.

**`execute_normal_like` RECEVAIT déjà `is_melee`** : elle le passait à `defender_modifiers` (#59) et le
caller s'en sert pour le perçage de profil. Elle ne le threadait simplement pas à l'axe ATTAQUANT. Ce
n'était donc pas une limite d'infrastructure mais un oubli de câblage — exactement la question posée.

Ses trois consommateurs passent tous un booléen (jamais None) :

- `runner/operations/triggers/loki/psyker.py::psyker_smite_tree` -> `is_melee=False` (splash « Smite ») ;
- `runner/abilities/behaviours/combat.py::AttackWithAttackDamage` mode `amount` -> `self.is_melee` ;
- `runner/abilities/loki/summon.py::_summon_on_appearance_attack` -> `ctx.is_melee`.

**Conséquence mesurable** : sur le splash Psyker (RANGED), le port appliquait les bonus MÊLÉE-only
(`Waaagh_ExtraDamage`, `CrushingStrike`) et PERDAIT les bonus RANGED-only (`RangedSpecialist`,
`HeavyWeapon_ExtraDmg`, `TerrifyingCrescendo`) — alors que la face PRÉDICTION du **même coup**
(`PsykerPlaybook._predict_amount_vs_target`, `is_ranged=True`) les appliquait. Les deux faces du port
divergeaient donc entre elles.

## 4. Le fix

**(a) La source** — `AttackDamageOperation.execute_normal_like` threade la nature :

```python
_ranged = (not is_melee) if is_melee is not None else None
mods, active = attacker_modifiers(..., is_ranged=_ranged)
```

**(b) Un foyer unique pour le prédicat** — `engine/entities/effects/base.py` :

```python
def is_melee_attack(is_ranged):  return is_ranged is False   # BattleQuery$$IsMeleeAttack
def is_ranged_attack(is_ranged): return is_ranged is True    # BattleQuery$$IsRangedAttack
```

Câblés sur les 6 gates de nature de l'axe DÉGÂT : `CrushingStrikeEffect`, `BeastSlayerExtraDmgEffect`,
`WaaaghExtraDamageEffect` (côté mêlée — **changement de comportement** sur nature inconnue) ;
`HeavyWeaponExtraDmgEffect`, `RangedSpecialistEffect`, `TerrifyingCrescendo_ExtraDmgEffect` (côté
distance — **no-op strict**, `not is_ranged` ≡ `not is_ranged_attack(is_ranged)` pour `bool|None`).

**Volontairement PAS touchés** : `FeederTendrilsExtraDamageEffect` et `AvalancheOfMuscleExtraDamageEffect`.
Leur `if is_ranged:` n'est PAS le nœud `IsMeleeAttack` — c'est le `get_IsMelee` de
`IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour`
(l'ability elle-même est mêlée), recopié en calque sur AvalancheOfMuscle dont le décompilé n'a
**aucun** nœud de nature. Les durcir aurait été un durcissement à l'aveugle.

Après (a), le durcissement (b) côté mêlée est **sans effet mesurable** sur les vecteurs existants — il
sert de filet contre le prochain vecteur qui oublierait de threader :

- famille ABILITY d'`execute_ability_attack` (`is_attack_damage_op=False`, où `is_ranged=None` est
  INTENTIONNEL, gate #45f) : `is_normal_attack=False` y est passé, donc CrushingStrike et Waaagh
  rendaient déjà `None` ; BeastSlayer n'y reçoit pas `target_traits`, donc `None` aussi ;
- les deux lecteurs sans consommateur cités en §3.

## 5. Confrontation LIVE (session 78, build `gqfc5mff6c`)

**Porteur discriminant** : `tyranNeurothrope` cumule **Psyker** (le splash passe par
`execute_normal_like(is_melee=False)`) et **RangedSpecialist** (+33 % gate `IsRangedAttack`), avec une
arme ranged portée 3 / profil Psychic / pierce 100 qui déclenche le splash.

Protocole : conduire le Neurothrope à d>=2 d'une cible ayant exactement 1 ennemi adjacent (pas
d'ambiguïté sur le `PickRandomly(1)` du splash), capturer `decisionView`/`observeBattle`/
`combatSnapshot` + `dumpRng`, tirer LIVE, puis rejouer offline **le même état, le même RNG**.
`probe_106_splash_nature.py`.

| couple (seed, board) | coup | LIVE | port **après** #106 | port **avant** #106 (nature non threadée) | contre-cas nature MÊLÉE forcée |
|---|---|---|---|---|---|
| 777, `MC1_67` | primaire | 2353 | 2353 | 2353 | — |
| 777, `MC1_67` | **splash** | **2003** | **2003** | 1506 | 1506 |
| 31337, `C3_01` | primaire | 3624 | 3624 | 3624 | — |
| 31337, `C3_01` | **splash** | **2003** | **2003** | 1506 | 1506 |

`2003 / 1506 = 1.33` = `traitVariables.rangedSpecialistDmgPct` exactement. Coups propres
(`DidCrit/DidBlock/DidEvade = 0` sur les deux cibles).

**Les DEUX faces confrontées sur le même coup** (seed 777) :

| face | valeur |
|---|---|
| PRÉDICTION (`PsykerPlaybook._predict_amount_vs_target`, amount=1004) | `[2003, 2003]` |
| COMBAT LIVE | 2003 |
| COMBAT port après #106 | 2003 |
| COMBAT port avant #106 | 1506 — **la face COMBAT divergeait de sa propre face PRÉDICTION de 497 (−24,8 %)** |

**Ce que la mesure prouve sur l'autre moitié du fork.** Le natif évalue `IsRangedAttack = TRUE` sur ce
coup (il applique RangedSpecialist). Or les deux prédicats sortent du MÊME
`GetAbilityAttackRangeType` (§2) : `IsRangedAttack = TRUE` implique `rangeType = 2 (Ranged)` ou
`rangeType = 3 (Both)` hors-mêlée, et dans les DEUX cas `IsMeleeAttack = FALSE`. La moitié
« mêlée-only appliqué à tort » est donc close par la table de vérité native, à partir de la même
mesure — pas par extrapolation.

**Contre-cas exécuté** : rejouer le même état en forçant `is_melee=True` sur la feuille du splash rend
1506 (le gate ranged se tait) — la nature est bien la variable causale, et la seule valeur qui matche
le live est RANGED.

**Discriminance du test vérifiée** : le fix retiré temporairement,
`test_normal_like_vector_threads_attack_nature[777-MC1_67]` échoue exactement sur l'assertion splash
(`[1506] != [2003]`), puis repasse une fois le fix remis.

## 6. Tests

- `tests/engine/entities/test_attack_nature_gates_offline.py` (offline pur, 11 cas) — table de vérité
  des deux prédicats + **accord des deux axes Waaagh** (dégât 1100 vs coups 1101) nature par nature,
  c'est-à-dire le verrou du fork lui-même.
- `tests/engine/runner/test_attack_nature_normal_like_live.py` (2 couples board/seed) — replay-diff du
  splash, avec **garde de discriminance** intégrée : si aucun effet gate-nature n'est actif sur le
  caster (mods `is_ranged=True` == mods `is_ranged=None`), le test SKIP explicitement au lieu de
  passer pour rien.

Non-régression rejouée (ciblée) : `test_psyker_splash_live`, `test_heavy_weapon_moved_gate_live`,
`test_beast_slayer_extradmg_live`, `test_damage_roll_live`, `test_scarab_summon_migration_live`
(2ᵉ consommateur d'`execute_normal_like`), `test_damage_ability_live` — 11 passed, 0 skip.

## 7. Ce qui n'est PAS couvert

- **Le mode `Both` (`rangeType = 3`) n'est pas modélisé.** Le port déclare la nature du coup (`is_melee`
  du behaviour) ; le natif, pour `Both`, la calcule par `AreUnitsInMelee(attPos, tgtPos)`. Aucune
  divergence observée sur les vecteurs mesurés (le splash Psyker et l'attaque normale sont hors-mêlée
  au moment mesuré, les deux modèles coïncident), mais un coup `Both` résolu **au contact** ferait
  diverger un `is_melee` déclaré. Non exercé — résidu nommé, pas un port spéculatif.
- **Famille ABILITY d'`execute_ability_attack`** : la mesure #45f dit que
  `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` reçoit des modifiers ATTAQUANT
  **VIDES** (struct zéroée). Le port ne les vide pas — il se contente de ne pas threader `is_ranged` /
  `trigger_ability_type`. Après #106, les gates de nature s'y taisent bien, mais les bonus **sans**
  gate de nature (ex. `DecoysAndMisdirection`, `RapidAssault`) y passent encore. Chantier séparé.
- ~~**Contre-cas melee-only monté live avec Waaagh** : abandonné, le cast de 1058 est inerte dans le
  runner isolé.~~ **LEVÉ (case-111)** : le cast n'était pas inerte, la CIBLE était illégale — le probe
  castait `targetId = <le Warboss lui-même>`, que
  `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason` refuse,
  d'où le no-op moteur en amont de tout étage. Cible relue dans `abilityTargets(...).fromHere` +
  boucle d'approche qui exige aussi une cible légale pour le Warboss : `probe_106_waaagh_splash.py`
  converge et **le contre-cas est CONFIRMÉ live** (MC1_67 / seed 777, session 78) — splash RANGED du
  Neurothrope, porteur du buff melee-only 1100 : `live = 1335`, `port (is_melee=False) = 1335`,
  `legacy (nature non threadée) = 1004` → discriminant. Détail : `case-111-waaagh-cast-gate`.
