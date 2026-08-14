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

L'écart **existe** et reste ouvert. En revanche, l'attribution qui en était tirée — « le port pose
l'additif un étage trop bas » — est **RÉFUTÉE (2026-08-14, #1084)**, par deux voies indépendantes.

**1. Le décompilé place l'additif exactement où le port le place.**
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` calcule lui-même les deux jeux de
modificateurs — slots `0xd` (ATTAQUANT) et `0xe` (DÉFENSEUR) de `IDamageCalculations`,
c'est-à-dire `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`
et son jumeau DÉFENSE, dont la signature `(this, state, entities, activeEffects)` prend un
`IdunBattle.Entities.Abilities.AbilityEntities`. De **chacun** des deux structs rendus il lit le
champ `+0x10` (= `DamageModifiers.Addition`) et le **somme au `baseDamage`** passé à
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` — pour la borne
MIN **et** pour la borne MAX, avec les **mêmes deux termes** (seul le terme de spread diffère
entre les deux appels). La disposition du struct est confirmée au même endroit : `+0x00` est lu
comme un `Nullable` qui **écrase** le dégât de base (`Override`), et CBDWAM ne lit, lui, que
`+0x20` (`Piercing`), `+0x28` (`IgnoreArmor`), la liste `+0x18` et `+0x30` (`Multiplier`) —
**jamais `+0x10`**. L'additif entre donc **avant** le perçage et **avant** les %-mods : c'est la
position `attacker_additive_pre=True` du port, celle que #75 a validée bit-exact.

**2. Le montage ci-dessus ne pouvait pas séparer les deux positions.** L'écart est mesuré
« armure 0 des deux côtés ». Or à armure nulle,
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
rend `max(0, d − 0, d × p/100) = d` : c'est l'**identité**. Ajouter l'additif avant ou après elle
donne le même nombre — mesuré, pas raisonné : **+898,0 des deux côtés**. Le régime est **dégénéré**
pour la question posée. Le même couple joué dans le régime **séparant** (celui de #75 :
`pierce = 50`, armure `2208`) rend **+449** en position PRE contre **+898** en POST, un facteur 2
franc : c'est ce régime-là qu'il aurait fallu jouer. La coïncidence `617,3/898 = 0,687` avec
`628,7/906 = 0,694` est un rapport de deux **moyennes sur six tirages** ; elle ne désigne aucun
étage — c'est un scalaire fitté, ce que la doctrine interdit explicitement sur un foyer de dégât.

**Ce qui reste**, donc : une divergence de **magnitude** non localisée, pas un étage manquant. La
piste qu'ouvre cette relecture est la magnitude elle-même — le niveau et le multiplicateur de
l'`AbilityState` sous lequel `extraDmg` est lu (même famille de verrou que #1005 / #237) — et non
la position. La face dégât reste **désarmée** : rien ne s'arme sur une cause non localisée.
Cliquet : `tests/engine/test_924r2_place_additif_attaquant_offline.py` rougit si quelqu'un
« répare » #924-r2 en **déplaçant** l'additif, ce qui casserait la bit-exactness de #75.

⚠ La « première étape du fix » que cette fiche prescrivait — threader `trigger_ability_type` vers
`attacker_modifiers` — n'est **pas** une étape de ce résidu : elle découlait de l'attribution
réfutée. Le threading reste souhaitable en soi (le natif n'a qu'**un** contexte per-coup,
`AbilityEntities`, dont le champ `+0x98` est lu indifféremment par les canaux COUPS et DÉGÂT), mais
il ne débloque rien ici et reste sans consommateur porté.

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
