# #924 — `InescapableDeath` (passif de `necroDestroyer` / Imospekh)

**Verdict** : **3 faces**, pas 1. Deux portées et confrontées live, une RE-solue mais **non portée**
(son étage d'injection est invalidé par la mesure → `#924-r2`). Un quatrième point est tombé en
chemin : la sœur de forme `EarlyWarningOverride` (1145) a la **même** face DÉGÂT, vivante et non
portée → `#924-r1`.

`kit-coverage` annonçait `manque 1`. Le décompilé en donne trois.

## 1. La hiérarchie — lue dans `frida/classes.tsv`, jamais déduite d'un nom

    IdunBattleLogic.Entities.Abilities.Active.Loki.InescapableDeathAbility
      : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility

    IdunBattle.Entities.Effects.Loki.InescapableDeathEffect
      : IdunBattle.Entities.Effects.AReactivateOverwatchEffect
          : IdunBattle.Entities.Effects.DamageModifierAbilityEffect
              : IdunBattle.Entities.Effects.BaseEffect

Le namespace `…Abilities.Active…` **ment** : `InescapableDeath` est une `passiveAbilities`
(`TriggeredAbilityType` 0x3ed = 1005).

## 2. Ce que le natif dit et qu'aucune table ne disait

`frida/methods.tsv` liste **4** méthodes pour `InescapableDeathEffect` et **3** pour sa sœur 1145.
Ce dump est indexé par **adresse** et l'ICF fusionne les corps identiques : une méthode surchargée
y **disparaît** si son corps est partagé. Le comptage qui tranche est celui du bloc
`methodPointers` du PE, où **chaque propriétaire a sa propre entrée** :

| bloc | entrées | conclusion |
|---|---|---|
| `18326e540…e558` (1018) | `.ctor`, `GetHitReductionEffectType`, `GetOverwatchExtraDamage`, `GetAdditionalExtraDamageTrigger` | **4** — donc **PAS** de `LegitDeathReasons` |
| `18326d838…d850` (1145) | `.ctor`, `GetHitReductionEffectType`, `GetOverwatchExtraDamage`, `LegitDeathReasons` | **4**, pas 3 |

Le corps `GetOverwatchExtraDamage` porte **deux** entrées (`18326d848` **et** `18326e550`) : un seul
corps, deux propriétaires — toute la variabilité passe par `this` (`config@0x60`).

⇒ **Trois faits qu'aucune table ne donnait** :
1. `InescapableDeathEffect` **n'override pas** `LegitDeathReasons` → il prend celui de la base,
   **un** terme, là où 1145 en a **deux**. Recopier le voisin aurait ré-armé l'overwatch sur des
   morts que le natif refuse ici.
2. **1145 override `GetOverwatchExtraDamage`** — la docstring de `reactivate_overwatch.py`
   affirmait le contraire, sur la foi du seul dump Frida. Corrigé ; sa face DÉGÂT est vivante
   (`extraDmg` non nul dans le gameconfig) et non portée → `#924-r1`.
3. `IsOverwatchAttack()` = `TriggeringAbilityIs(AbilityOrEffect{Effect = 0x3f1})` — immédiat lu
   **aux octets** (`mov edx,0x3f1`), surcharge `op_Implicit` @`18166a080` dont le corps est
   `set_Effect`. Il construit donc **exactement** le même prédicat que le `TriggeringEffectIs(0x3f1)`
   qui le précède dans la conjonction, et les deux lisent le **même** champ
   (`DSLTriggers+0x10 → +0x90 → +0x90`) : la conjonction native est **strictement redondante**.

`LegitDeathReasons` de la base, relu aux octets (`mov edx,0x3f1` avant `op_Implicit`) :
`HasDeathReason(query@0x178, DamageReason.Ability, AbilityOrEffect{Effect = 1009})`.

## 3. Les trois faces

| face | artefact natif | état |
|---|---|---|
| **A — DÉCISION owner** | `AOwnerEffectTriggeredAbility$$CreateTrigger` = `OnOwnerSpecificAbilityInit` ; `$$CreateBehaviour` = `If(cond, AddEffect(GetEffectType() = 0x3fa, …, owner, owner))` | **PORTÉE** — `ABILITY_INIT_OWNER_EFFECTS["InescapableDeath"]` |
| **B — COMBAT, 2 `Triggered()`** | `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` (hérité) : re-entrée en overwatch + `AddStaticStatModifierEffect(1019, EXTRA_HITS, −hitsReduction)` ; purge quand 1009 n'est plus actif | **PORTÉE** — `EFFECT_TRIGGERS[1018]` |
| **C — COMBAT, dégât** | `AReactivateOverwatchEffect$$CreateDamageModifier`, allumé par l'override `GetOverwatchExtraDamage` = `ConfigVar(AbilityVariableType.extraDmg)` | **NON PORTÉE** — `#924-r2` |

**Aucune face n'est dead-code** : il n'y a ici ni playbook ni `yield return Fix64.op_Implicit(0)`.
La recherche `InescapableDeath` sur tout le binaire ne rend, hors des six symboles de logique, que
`View.AbilityConfigs.Loki.OverwatchEffectVisuals$$HasInescapableDeath` — du **visuel**.

## 4. Ce que le décompilé n'a PAS, et que le voisin de forme aurait fait recopier

- **aucun `IsRangedAttack`** dans le trigger de la face C. L'i2 dit pourtant « **ranged** attacks
  now deal +extraDmg … » : la restriction au tir tient au fait que l'overwatch **est** un tir, pas
  à un nœud. L'écrire serait une invention, et elle serait invisible tant qu'on ne teste que
  l'overwatch (test de garde posé).
- **aucun** filtre `Immune`, **aucun** `IsNormalAttack`, **aucun** `has_moved`.
- `HitReductionValue()` lit la constante `hitsReduction` de **sa propre** ability source
  (`config@0x60`, l'argument du `.ctor`). Les deux sous-classes valent 1 aujourd'hui — le port
  paramètre donc la **source**, jamais la valeur.

## 5. `#924-r2` — la face DÉGÂT : pourquoi elle n'est pas livrée

Le natif **applique bien** ce bonus. Mesure live, même run, même attaquant, même cible, armure 0
des deux côtés (`--hp-target 60000`, board `MC1_67`) :

    attaque NORMALE   coups = [569, 625, 647, 697, 728, 506]        moyenne   628,7
    tir  OVERWATCH    coups = [1328, 1114, 1329, 1206, 1279, 1220]  moyenne  1246,0     (x1,98)

Mais l'écart que le **port** produirait n'est pas celui du natif :

| | écart par coup |
|---|---|
| natif (overwatch − normale) | **617,3** |
| port (nominal − mutant, mutant = même salve, face neutralisée) | **898,0 exactement** (5388 / 6) |

`617,3 / 898 = 0,687`. Or le rapport `dégât normal / stat Attack` vaut, **mesuré indépendamment**,
`628,7 / 906 = 0,694`. **Les deux rapports coïncident** : le bonus subit exactement la même
transformation que la base ⇒ le natif l'ajoute **avant** la résolution des bornes, le port
**après** (`_reduced_bounds`, `attacker_additive_pre` = « bornes (base ± spread) + additif »,
position pourtant validée bit-exact par #75 pour une autre famille).

Livrer à cet étage donnerait **+45 %** de dégât sur chaque tir d'overwatch d'Imospekh — pire que
l'absence, qui est le comportement de `master`. La méthode est donc **retirée**, pas écrite « en
attendant ». Restent en place : la RE complète (module `inescapable_death.py` §6), la classe au
registre (pour que le résidu soit visible), et un **cliquet inversé** qui rougit si quelqu'un
ré-arme la face sans traiter l'étage.

Première étape du fix : `damage_ops/normal.py` ne threade **pas** `trigger_ability_type` vers
`attacker_modifiers` (seul l'axe COUPS le reçoit, via `build_hits_board`). Non fait ici : sans
consommateur porté, l'ajout serait un élargissement **non validable** d'un foyer partagé.

## 6. Deux pièges de mesure traversés (à ne pas re-payer)

- **`decisionView` droppe les instances INACTIVES.** Au spawn — donc pendant le tour du porteur —
  `RangedAutoAttackEffect` **désactive** l'overwatch : le canal par défaut rend `[1011]` seul, et
  y lire une absence conclurait « le natif ne pose ni 1009 ni 1018 ». C'est **faux** : le canal
  `includeInactive: true` publie les deux. Les tests lisent les **deux** canaux et assertionnent
  qu'ils **diffèrent**, sinon ils ne mesurent plus ce qu'ils croient.
- **Un effet à durée `TurnsUntilUnitOwnerTurn` peut EXPIRER avant qu'on relise l'état** : le tour
  bascule seul dès que la dernière unité adverse a agi. Lire l'état d'après rendait `1019` absent
  alors que le natif l'avait bien posé. On tranche par le **retour** du `applyAction` (ses events),
  jamais par l'état ultérieur — c'est « l'absence ne prouve rien », dans sa version temporelle.
- Corollaire outillage : `applyAction{"kind": "attack"}` **n'existe pas** ; une attaque normale se
  joue par son ability **concrète** (`Loki_NormalAttack`).

## 7. Résidus ouverts

- **`#924-r1`** — face DÉGÂT d'`EarlyWarningOverride_ReactivateOverwatchEffect` (1145) : le corps
  `GetOverwatchExtraDamage` lui appartient aussi (2 entrées `methodPointers`), sa variable
  `extraDmg` est non nulle. Montage distinct (`tauCrisis`), donc hors périmètre de #924. Dépend du
  même étage que `#924-r2`.
- **`#924-r2`** — l'étage d'injection de l'additif `ForAddition` attaquant pour cette famille.
