# #231 — `AnvilShield_FrozenAttackerAdvantage` (1201) : le gate `IsActive` du rail TARGETS

Residu de `case-229-effect-triggers-active-inventory.md` (§4, voie 1). **UN SEUL item : 1201.**
Les autres ecarts nommes par #229 sont hors perimetre de cette fiche : 1077 et 1197 ont ete
resorbes en parallele (`0ad036f`, `738ca5a`) ; **1502, 1547 et 1186 restent ouverts** — compte
re-derivable par `python scripts/python/probe_229_effect_triggers_active.py`, jamais cite d'ici.

**Verdict : ECART REEL, gate POSE.** Le `matches` d'`AnvilShieldFrozenAdvantageExpire` ne
consultait pas `BaseEffect.active` ; il le fait desormais, en mirror du `if (+0x5c)` que
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique par cible.

## 1. Qualification de l'item — quel 1201 ?

`1201` est ambigu **entre trois enums** ; l'item porte sur l'**EffectType** :

| enum | 1201 | rapport avec cette fiche |
|---|---|---|
| `EffectType` | `AnvilShield_FrozenAttackerAdvantage` (0x4b1) | **c'est lui** |
| `ActiveAbilityType` | `SquigMine` (`orksRukkatrukk`) | sans rapport |
| `TriggeredAbilityType` | `DoctrinaImperatives_SetStart` | sans rapport |

**Porteur** : `spaceRockfist` (Arjac Rockfist, Space Wolves) — passif `AnvilShield`. i2 :
« ... **or if his attacker is on a hex covered in Ice**, he gains +20 % Block chance ... ».
L'effet est pose par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour`
(`AddStaticStatModifierEffect(Self@0x148, 0x4b1, statType 7 = BLOCK_CHANCE, GetVariableForLevel(0x15))`)
et consomme par son propre trigger d'effet a `On(UnitPostAbility)`.

**Confrontabilite** : HERO, present dans `rl_duel.py --list-pool` (`spaceRockfist`, rank 1..3).
Le harnais live existe deja : `tests/engine/runner/test_anvil_shield_stun_live.py` monte Arjac
`--block-target 100,500` face a un melee et fait poser 1201 par le vrai vecteur `On(0x2b)`.

## 2. RE — la semantique EXACTE du gate

### 2.1 Le rail : `CreateTargetTrigger`, donc rail TARGETS

`IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger`
(decompile lu, pas deduit) :

    On(0xe = UnitPostAbility, 1) & AreEqual(target@0x178, EffectSource(this@0x150))

C'est le slot `CreateTargetTrigger` (0x26 de la def d'effet) — donc l'evaluateur natif est
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`, **le rail qui gate**.
Ce n'est PAS `EvaluateEffectTriggerEffectAbilities` (rail `ArraySet`), qui n'accede jamais a `+0x5c`
et qu'il ne faut surtout pas gater (#229 §1).

### 2.2 Les DEUX lectures de `IsActive @+0x5c` dans `EvaluateEffectTriggerTargets`

Signature (`data/symbols/gqfc5mff6c/frida/methods.tsv`) :
`EvaluateEffectTriggerTargets(trigger, effect: IEntity, effectComponent: EffectComponent,
effectAction: IEffect, createAbilityEntities: Func<AbilityEntities>, abilityState: AbilityState)`.

**Lecture n°1 — a l'entree, sur `effectComponent` (param 3)** : ce n'est PAS le gate.

    if (effectComponent.IsActive@+0x5c != 0) {
        if (effectComponent.Targets@+0x50.Count == 0) return;      // sortie ANTICIPEE
    }
    ArraySet<int>.ctor(&copy, effectComponent.Targets@+0x50, -1);  // snapshot des cibles

Elle ne conditionne qu'un court-circuit d'allocation : « effet actif ET aucune cible -> rien a
faire ». Un effet INACTIF n'a de toute facon plus de cibles
(`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ecrit `+0x5c = 0` **puis**
`UpdateEffectTargets` avec une liste VIDE -> `RemoveTargetsFromEffect`), donc la boucle ne tourne
pas non plus dans ce cas.

**Lecture n°2 — DANS la boucle, PAR CIBLE, sur le component RECHARGE depuis l'entite-effet** :
c'est **LE** gate.

    foreach (targetId in copy) {
        entities = createAbilityEntities();   // + entities.Target = GetEntity(targetId)
        entities.Effect@+0x58 = effect;
        comp = effect.Get<EffectComponent>();                      // param 2 (l'ENTITE-EFFET)
        if (comp.IsActive@+0x5c != 0) {                            // <-- GATE
            if (trigger.ShouldTrigger(entities)) {                 // slot 0x13
                ... TargetsSelector.SelectFirst / event group ...
                behaviour.Execute(entities);                       // slot 0x14
            }
        }
    }

Deux consequences de sa position :

1. il porte sur **l'effet SOURCE lui-meme** (l'`EffectComponent` de l'entite-effet dont le
   `CreateTargetTrigger` est evalue), pas sur un effet de la cible ;
2. il est **RE-LU a chaque cible** : une desactivation survenue pendant le drain (le behaviour
   d'une cible precedente) stoppe les cibles suivantes. Le natif ne se contente pas du test
   d'entree.

### 2.3 N'importe quel effet peut devenir inerte — `ShouldBeActive` decompile (complement a #229 §5)

#229 laissait `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` non decompile. Lu ici :

    ShouldBeActive(trigger, kind, effectAction, comp, ...) :
        if (kind == 1) return true;                    // toujours actif
        if (kind == 2) return false;                   // jamais actif
        if (kind  > 2) throw ArgumentOutOfRangeException;
        if (comp.@+0x5e != 0) return false;            // <-- flag generique, NON caracterise
        if (!effectAction.HasActiveCondition(trigger)) return comp.IsActive@+0x5c;
        return effectAction.<slot 0xb>(entities);       // = CreateActiveCondition().ShouldTrigger

et `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` en fait
`ShouldBeActive == false -> DeactivateEffect`. Confirmation directe du corollaire doctrinal de
#229 : **le pilotage du flag n'est pas reserve aux effets a `CreateActiveCondition` propre**. Pour
1201, `HasActiveCondition` est faux (son `.ctor` appelle
`IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$.ctor(this, AbilityOrEffect(0x493), 0, 0, 1, 0, 0)`
sans condition) -> `ShouldBeActive` renvoie le flag inchange, et le vecteur d'extinction restant
est `comp+0x5e` (residu nomme, cf. §6).

## 3. Ce que le port faisait — et ce qu'il fait maintenant

AVANT (`engine/runner/operations/triggers/loki/anvil_shield.py`) :

    def matches(self, state, ev):
        return ev.target_id == self.owner_id        # AreEqual(target, EffectSource) SEUL

Une instance 1201 INERTE declenchait donc la consommation (`RemoveEffect(1201, Caster())`, qui
reverte aussi le `ChangeStat` stat 7 par-source) alors que le natif **n'evalue meme pas le
trigger**. Degradation PERMISSIVE : ni erreur ni crash.

APRES : le gate `_frozen_advantage_flag_is_set` precede `AreEqual`, sur le modele deja porte de
`_ranged_auto_attack_flag_is_set` (1009, `effect_triggers.py`) — meme convention de degradation
(aucune instance trouvee -> permissif, on ne fabrique pas un refus ; c'est
`collect_effect_triggers` qui n'aura alors instancie aucun trigger).

## 4. Canal d'atteignabilite

Cote port, le vecteur qui materialise une instance 1201 inerte est le **SEED** :
`engine/entities/effects/factory.py` lit la cle `active` du capte, et
`decisionView { includeInactive: true }` la publie a `false` (#229 §3 : 1201 est bien dans le
rayon de souffle « canal unite »). Cote natif, l'extinction passe par `RefreshEffect ->
ShouldBeActive`, dont la branche restante pour 1201 est le flag `comp+0x5e` (§2.3).

**Ce que cela n'est PAS** : aucun scenario de bataille connu n'eteint 1201 (pas
d'`ActiveCondition`, aucun `DeactivateEffect(1201)` dans le binaire). Le gate est donc pose pour
FIDELITE et pour rendre le canal `includeInactive` exploitable — pas pour corriger un symptome
observe en bataille. La garde le dit explicitement (§5).

## 5. Validation

- **Cliquet structurel** : `python scripts/python/probe_229_effect_triggers_active.py` — 1201 passe
  a `direct` et `AnvilShieldFrozenAdvantageExpire` sort de `EXPECTED_GAPS` (6 -> 5 ecarts) ;
  `RESULT: OK`. Le probe ECHOUE si le gate disparait, et ECHOUE aussi si un trigger du rail
  ARRAYSET se met a lire le flag.
- **Garde live** (`tests/engine/runner/test_anvil_shield_stun_live.py`,
  `test_anvil_shield_frozen_advantage_inactive_instance_is_inert_live`) : le montage LIVE reel
  (Arjac + attaquant sur tuile glacee) pose 1201 par le vrai vecteur `On(0x2b)`, puis l'instance
  est ETEINTE (`e.active = False`, mirror de `RefreshEffectsOperation$$DeactivateEffect`) et
  `On(UnitPostAbility)` est emis. Attendu : l'effet SURVIT et le block ne bouge pas. La phase B
  rallume l'instance et exige la consommation nominale (controle POSITIF : un gate trop large
  echouerait la).
  **CONTRE-EPREUVE JOUEE** contre le code d'avant (gate court-circuite) : `1 failed` —
  `assert None is AnvilShieldFrozenAttackerAdvantageEffect(... consumed=True, active=False)`,
  c'est-a-dire l'instance INERTE consommee. Gate restaure : `1 passed`.
- **Generalisation** : `python scripts/python/probe_231_frozen_advantage_active_gate.py` —
  table de verite (2 montages x 5 cas) = **10/10**, `RESULT: OK`. Deux geometries (`MC1_67`/92231
  et `C4_09`/92232), et un `--block-target 60` (au lieu de 100) pour que le canal stat 7 ne SATURE
  pas le clamp : le +15 y est OBSERVABLE (`bc 60 -> 75 -> 60` quand le trigger fire,
  `60 -> 75 -> 75` quand il est inerte). Les cinq cas : `active_owner` (fire), `inactive_owner`
  (inerte — le gate), `active_other` / `inactive_other` (inerte — `AreEqual`), et
  `inactive_owner_lowhp` (Arjac sous le seuil `healthPct`, donc **1200 ACTIF** : le gate de 1201
  ne se confond pas avec le canal 1200).
- **Non-regression** : les 4 tests live d'AnvilShield verts (`4 passed`), dont les 3 preexistants
  qui gardent le chemin nominal (instance ACTIVE consommee a la fin de l'ability, stun, canal 1200).

## 6. Ce qui n'est PAS couvert

- **Les ecarts de #229 encore ouverts** (`1502 RitesOfMorkai`, `1547 ReanimationBeam_Revive`,
  `1186 GhostEffectRevive` — ce dernier hors canal `includeInactive`, il passe par `tileMeta`) :
  hors perimetre de cette fiche.
- **`EffectComponent+0x5e`** : flag lu par `ShouldBeActive` (`return false` immediat), dont
  l'ECRIVAIN n'est pas identifie. Il n'apparait ni dans
  `IdunBattle.Entities.Components.EffectComponent$$GetPropertiesString` (qui expose 0x58, 0x5c,
  0x5f, 0x14, 0x48, 0x5d, 0x64) ni dans `$$.ctor`. C'est le seul vecteur natif connu capable
  d'eteindre un effet SANS `ActiveCondition` — donc le seul chemin par lequel ce gate pourrait
  devenir observable en bataille.
- **La granularite PAR INSTANCE.** Le natif evalue le trigger d'UNE entite-effet ; le port
  instancie ses `EffectTrigger` par `(owner, effectType)`. Le gate porte donc sur « au moins une
  instance 1201 active du porteur », pas sur l'instance precise. Sans consequence tant que
  `AddEffectOperation` no-ope sur un meme-type deja present (1201 : `stacking` non demande), mais
  ce n'est pas un mirror exact de la cardinalite native.
- **La re-lecture PAR CIBLE** (§2.2, point 2) : le port n'a pas de liste de cibles par effet, le
  gate est donc evalue une fois par evenement. Meme limite que le port de 1009.
- **RESIDU NOMME — `_has_active_block_bonus` (meme module) lit l'`ActiveCondition`, pas le FLAG.**
  Le gate `HasEffect(target, 0x4b0|0x4b1, activeOnly=1, 6)` d'`AnvilShieldAbility_ApplyStun` et
  d'`AnvilShieldAbility_FrozenAttackerAdvantage` lit `EffectComponent+0x5c`
  (`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` : `if (param_4 != 0) { if (effect+0x5c
  == 0) continue; }`). Le port y teste `e.is_active(ustate)` = l'ActiveCondition. Pour **1200**
  c'est un proxy fidele (le flag natif suit l'ActiveCondition via `RefreshEffect`) ; pour **1201**
  (sans ActiveCondition) `is_active` rend toujours `True`, donc une instance 1201 INERTE y compte
  comme presente. Le mirror complet serait `e.active and e.is_active(ustate)`. NON CORRIGE ICI :
  ce gate est sur le rail `ABILITY_TRIGGERS` (hors perimetre de l'inventaire #229, qui ne porte que
  sur `EFFECT_TRIGGERS`) et toucherait AUSSI 1200 — c'est le gisement « autres consommateurs de
  `by_unit` » nomme en #229 §5.
