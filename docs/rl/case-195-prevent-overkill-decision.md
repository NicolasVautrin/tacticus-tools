# case-195 — `PreventOverkill` sur la face DÉCISION

**Statut** : CÂBLÉ et MESURÉ (2026-07-28). Ferme la réserve explicite sous laquelle #190 avait été
livré (« critère FAIBLE assumé : la valeur n'a pas été fait VARIER »).

## Le natif — deux portes, un seul argument

Le 5e argument de la surcharge PRIVÉE 8-args d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`
s'appelle `isPreventOverkill` (`methods.tsv`). Il entre par **deux** chemins distincts, et le port
passait `0` EN DUR aux deux.

### Étage 1 — `ApplyTraitDamageLimitsToDamage` (cap Resilient)

Signature native (`methods.tsv`, noms verbatim) :

```
ApplyTraitDamageLimitsToDamage(damageClass, minDamageFix64&, maxDamageFix64&, damageProfile,
                               defender:IEntity, attacker:IEntity, isCrit, currentHealth,
                               currentArmor, initialHealth, previousHitsDeniedDamage,
                               isForcedOverkill, minimumHealth)
```

Corps, lecture verbatim du décompilé :

```c
uVar1 = UnitExtensions.HasFlag(defender, 0x13);                 // <- il le calcule LUI-MEME
uVar1 = IsOverkill(initialHealth, accum, isCrit, isForcedOverkill, uVar1,
                   cfg@+0x30 /*allowOverkill*/, cfg@+0x34 /*pct*/, minimumHealth);
ApplyResilientTraitDamageLimit(min, ..., uVar1);
ApplyResilientTraitDamageLimit(max, ..., uVar1);
```

C'est le `suppress` de `compute_prediction_overkill`. Consommateur unique : le cap Resilient.

### Étage 2 — `WillBeOverkill` / `MightBeOverkill` (utilité `OverkillUnit` 37)

```
IsOverkill(result@+0x00, <borne>, <0 | MightCrit@+0xb1>, ForceOverkill@+0xb2,
           **result@+0xb3**, HasValue(result@+0xb4), Value(result@+0xb4), null)
```

⚠ **L'asymétrie native de #R34 porte sur le 3e argument, PAS sur le 5e.** `WillBeOverkill` passe
`isCritical = 0` en dur mais lit `result@+0xb3` comme sa jumelle. Une « harmonisation » qui
retirerait la clé de la borne garantie en croyant préserver #R34 serait fausse.

Le corps privé ne teste `pct` que `if (!isPreventOverkill && targetInitialHealth <= healthDamage)` :
flag posé ⇒ retour 0, quelle que soit la sur-frappe.

## Le poseur du flag

`UnitFlag.PreventOverkill = 19` (=0x13, `enums.tsv`). Écrivain UNIQUE dans le binaire :
`IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal`
→ `UnitFlagsComponent.Add(target, 0x13)`, retiré par son `$$RevertInternal`. Porteur mesuré (#178) :
`ultraTitus`, dès le déploiement.

## La mesure

`python scripts/python/probe_195_prevent_overkill_decision.py --part all`

**A. CANAL** — même runner, même attaquant, deux cibles :

```
ultraTitus       preventOverkill=1
genesPrimus      preventOverkill=0
```

DEUX valeurs distinctes ⇒ le champ est un fait de la CIBLE, pas une constante. C'est ce qui rend le
canal discernable d'un canal mort — l'acceptation que #190 n'avait pas.

**B. UTILITÉ** — formule ISOLÉE (les deux côtés nourris des MÊMES prédictions natives, le natif
étant `pairUtility` invoqué en direct), régime létal-sous-le-seuil + crit forcé :

```
cible          bornes RAW     natif      port AVEC   port SANS
ultraTitus     [4812,7224]    133.2826   133.2826    148.2826   <- ecart 15.0000 = PossibleOverkill
genesPrimus    [4812,7224]    148.2826   148.2826    148.2826   <- temoin : rien ne bouge
```

Les deux cibles ont des bornes RAW **identiques** : la seule variable est le flag. La variante
« SANS » reproduit le port d'avant #195 (clé retirée du dict), donc la garde reste capable de rougir
sans revenir en arrière dans le code.

Régime obligatoire : `PV <= rawMax < 2 x PV`. Au-dessus, l'overkill est NATUREL et les deux
variantes coïncideraient — un montage hors régime rendrait VERT sans rien mesurer.

## Le câblage

- `Scene.prevents_overkill(uid)` — accesseur, rempli par `from_state` depuis l'ECS
  (`unit_prevents_overkill` : composant de flags d'abord, effet 1354 ensuite) ; côté
  `from_predictor_sctx` la table est VIDE et l'accesseur retombe sur la dérivation par l'effet actif.
  **Ce n'est pas une approximation** : c'est le même invariant (le couple
  `ApplyInternal`/`RevertInternal` encadre exactement la durée de vie de l'effet), et c'est la seule
  source disponible — aucun RPC n'expose `UnitFlagsComponent` (gap d'outillage nommé, tâche O5).
  Foyer unique de la dérivation : `runner/components.effects_prevent_overkill`.
- `predict_attack_raw(target_prevents_overkill=)` → publie `DamagePredictionResult.prevent_overkill`
  (@0xB3) ET passe `suppress=` à `compute_prediction_overkill`. Threadé par les 7 sites de
  prédiction (normale, abilities, splash Psyker, Fury).
- `will_be_overkill` / `might_be_overkill` lisent `pred["preventOverkill"]`.
- Producteurs de la clé : `ProbableDamageEvent.composite_fields()` (offline) et
  `engine_agreement_stages._fields_from_native_event` (décodeur natif, event+0xBB).
- Face COMBAT : `_run_hits(prevent_overkill=)` → les deux `compute_prediction_overkill` de
  `damage_hits.py`, threadé par les 4 call-sites.

## Ce qui reste NON CONFRONTÉ — et pourquoi c'est structurel

**L'étage 1 est QUIESCENT**, et c'est une mesure, pas une supposition. `overkill` n'est consommé que
par `ApplyResilientTraitDamageLimit` ; il faudrait donc une cible portant À LA FOIS le trait
`Resilient` ET `UnitFlag.PreventOverkill`. Le seul poseur du flag est `FuelledByFury_BlockOverkill`
(`ultraTitus`), dont les traits sont `Hero`, `BeastSlayer`, `FinalJustice` — pas `Resilient`. Aucun
scénario ne peut donc distinguer ce gate, ni en prédiction ni en combat. Il est porté pour la
fidélité (un seul côté câblé recréerait un fork prédiction/combat), pas parce qu'il a été confronté.

Seul **l'étage 2 est mesuré**, et il l'est exactement : 15.0000.

## Détail de montage

`--block-target 0,0` : `ultraTitus` porte `BeastSlayer`, et le scénario de block `list[0]@0x50`
n'est pas exposé par le décodeur (`_fields_from_native_event` le recalcule depuis un `block_amount`
qui vaut 0 par défaut). Sans ça, `killSure` divergerait pour une raison ÉTRANGÈRE au terme mesuré.

Attaquant `ultraInceptorSgt` : SANS le trait `ThrillSeekers` (1056), dont le rider « defeats an
enemy with a Crit → always overkilled » forcerait `isForceOverkill` et rendrait l'observation
ambiguë — le confond que #R33 avait dû lever côté COMBAT.

Garde : `scripts/python/tests/engine/runner/test_prevent_overkill_decision_live.py` (4 tests).
