# case-366-r1b — `1111 WireweaveNet_CounterAttack` : une riposte PRE-HIT, armée par le TOUR

**Question, binaire.** Le port fait-il partir la contre-attaque de Calandis exactement quand le
natif la fait partir, pour exactement le même montant — et se tait-il exactement quand le natif se
tait ?

**Réponse : OUI côté DÉCOMPILÉ et côté harnais déterministe ; la confrontation LIVE reste À JOUER**
(la session Frida était éteinte pendant tout ce cas — cf. §7). Porteur `eldarRanger` (Calandis),
HERO **au pool** ; voie directe, ni greffe npc, ni injection catalogue, ni relique.

i2 : « The first time Calandis is targeted by a normal melee attack during the enemy's turn, the
attacker immediately takes 2x 873-1310 Piercing Damage. If the attacker is eliminated, their melee
attack is not executed. »

## 1. Le canal, établi à SA PROPRE SOURCE — un EFFET, pas une triggered-ability

L'hypothèse « même canal que le voisin `1110` » est **fausse** : `1110` est une lecture par coup
côté défense (`EffectBonus.ForSubtraction`), `1111` n'a **aucun canal de bonus**. Sa chaîne, lue
dans `data/symbols/<build>/frida/classes.tsv` :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.WireweaveNetAbility
        : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility : BaseTriggeredAbility
    IdunBattle.Entities.Effects.Loki.WireweaveNet_CounterAttackEffect
        : IdunBattle.Entities.Effects.CounterAttackEffect
        : IdunBattle.Entities.Effects.PlayerTurnEffect : BaseEffect

Le comportement vit donc dans **trois `Triggered()` portés par l'entité-EFFET**, pas dans un
`CreateTrigger` d'ability. `1111` est aussi un cas d'école de **qualification d'enum** : le même
nombre est l'`EffectType` rendu par `WireweaveNetAbility$$GetEffectType` (`return 0x457`) **et** le
`TriggeredAbilityType` que le `.ctor` de l'effet bake — deux enums, une valeur.

## 2. Le `.ctor` : trois littéraux, tous lus à l'ASSEMBLEUR

`WireweaveNet_CounterAttackEffect$$.ctor` (le décompilateur masque l'immédiat) :

    mov edx, 0x457                              ; 1111
    call AbilityOrEffect$$op_Implicit           ; surcharge tranchée par SON CORPS
    mov edx, 1 ; mov r8d, 2
    call CounterAttackEffect$$.ctor             ; (turnsEnabled, activationFrequency, sourceAbility)

* La surcharge d'`op_Implicit` visée par le `call` appelle **`set_TriggeredAbility`** ; les trois
  homonymes écrivent `set_ActiveAbility` / `set_Effect` / un 4e champ. C'est la lecture qui qualifie
  le `0x457` en `TriggeredAbilityType` — jamais le nom de la fonction.
* `PlayerTurnEffect$$.ctor` écrit `+0x484 = turnsEnabled`, `+0x480 = activationFrequency`, et passe
  `hasAutomaticActivation = (activationFrequency == 0)` à `BaseEffect$$.ctor` ⇒ **FALSE** : l'effet
  ne s'arme PAS tout seul à la pose.

| littéral | consommateur | conséquence |
|---|---|---|
| `turnsEnabled = 1` | `PlayerTurnEffect$$IsEnabledTurnType` branche `else` | `NOT <DSLTriggers+0x28>` = **`NOT IsTurnOf(Owner)`** ⇒ fenêtre = tour ENNEMI |
| `activationFrequency = 2` | `$$CreateHandleTriggerAbilitiesInternal`, branche `== 2` | `On(0x12) & IsTurnOf(Owner) -> Deactivate` + `On(0x17) & IsTurnOf(Owner) -> Activate` |
| `hasAutomaticActivation = False` | `BaseEffect$$.ctor` | c'est le `If(NOT IsTurnOf(Owner), ActivateEffect)` de la pose qui arme, pas la pose elle-même |

(`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` : identification établie par `case-366-r1` §2 ;
`<DSLTriggers+0x70>` et `+0x40` = deux instances d'un trigger sans champ, `size 16` ⇒ `YesTrigger`,
et `+0x48 = NOT` de la même classe.)

## 3. La POSE, et pourquoi le seed est OBLIGATOIRE

    AOwnerEffectTriggeredAbility$$CreateTrigger = OnOwnerSpecificAbilityInit(this.Id@+0x10)
    WireweaveNetAbility$$CreateBehaviour        =
          AddEffect(0x457, <AbilityStateReference>, source=Owner@<Sel+0x30>,
                    targets=Owner@<Sel+0x30>, <durée ZÉROÉE>)
        + If( NOT <DSLTriggers+0x28>, ActivateEffect(Owner, 0x457) )

Le second terme est littéralement le corps de `WireweaveNetAbility$$ActivateEffectIfOwnerTurn`,
inliné. L'effet est donc un **owner-effect permanent posé à l'init**, et il est **INACTIF pendant le
tour de son porteur** — donc **absent du canal `decisionView` par DÉFAUT** (actifs seuls). D'où
l'entrée `factory.ABILITY_INIT_OWNER_EFFECTS["WireweaveNet"]`, même motif exact qu'`AnvilShield`,
`HammerOfWrath`, `ModifiedExoarmour`, `VisionsOfHeresy`. **Sans elle, un runner capturé pendant le
tour de Calandis n'a AUCUNE instance à armer et la riposte est morte** — et le zéro lu dans
`decisionView.units[].effects` ne l'aurait pas signalé.

## 4. La RIPOSTE

    CounterAttackEffect$$CreateTargetTrigger =
          GetCounterAttackTrigger()               # vtable +0x778 -> On(0x2a = PreUnitAbility, true)
        & <DSLTriggers+0x20>                      # conjoint SINGLETON non qualifié (§6)
        & GetCounterAttackCondition()             # vtable +0x788
        & AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)
        & IsAlive(Caster@<Sel+0x48>)

    WireweaveNet_CounterAttackEffect$$GetCounterAttackCondition =
          get_OwnerOrOwnerTileIsTarget & IsMeleeAttack & IsNormalAttack

    CounterAttackEffect$$CreateTargetTriggerBehaviour =
          GetCounterAttackBehaviour(effect) & DeactivateEffect(effect)     # gate vtable +0x738

`0x2a = 42 = PreUnitAbility` — **vérifié contre `frida/enums.tsv`**, pas déduit (`43 = UnitHealed` :
le commentaire `# On(0x2b = 43, 1)` de `martial_superiority.py` est une coquille, son code utilise
bien l'enum). La riposte part donc **AVANT** l'attaque entrante, et le « If the attacker is
eliminated, their melee attack is not executed » d'i2 est rendu par le **gate ACTEUR-MORT
post-`On(PreUnitAbility)`** d'`ActiveAbilityOperation$$ExecuteInternal`, déjà porté par #133 sur les
deux voies.

**`IsNormalAttack`, PAS `IsDirectTargetAttack`** — c'est le point qui sépare cette riposte de celle
de `MartialSuperiority`, dont le gate (`AbilityHasAttackType(DirectTargetAttack) | IsNormalAttack`)
est **strictement plus large**. Une ACTIVE de mêlée réveille Jaeger, pas Calandis. Recopier le
voisin aurait donné un port permissif.

**Le `& DeactivateEffect(effect)` porte le « the FIRST time »**, et son gate (`vtable +0x738`) est un
stub **`return 1`** : le PREMIER membre du groupe `CounterAttackEffect` dans la table
`methodPointers` (corps `mov eax,1 ; ret`, partagé — l'unique propriétaire nommé est
`UnityEngine.U2D.IK.Solver2D$$DoValidate`). Le 3e `Triggered()` de `PlayerTurnEffect`
(`On(0x2e = UnitResurrected) & OwnerIsTarget -> Activate`) est, lui, gaté par un stub `return 0`
⇒ **non bâti** (et sans observable : il ne concerne que la résurrection du porteur).

## 5. Le DÉGÂT

    GetCounterAttackBehaviour = AttackDamage(effect, GetDamageProfile(cfg), GetNumberConstant(cfg, 0x2f))
    CounterAttackEffect$$AttackDamage = AttackWithAttackDamage(
        caster  = Owner@<Sel+0x30>,            targets = GetCounterAttackTargets() = <Sel+0x48> (Caster),
        amount  = GetDamage() = GetMinMaxDamage(0),
        profile, hits,                          source = this.SourceAbility (= TriggeredAbility 1111))

gameconfig `WireweaveNet` : `attackRangeType = Melee`, `constants = {damageProfile: "Piercing",
nrOfHits: "2"}`, `variables = {minDmg, maxDmg}` (65 paliers) avec
`variablesAffectedByRarityBonus = ["minDmg","maxDmg"]`. Niveau 50 : **665-997** avant multiplicateur
de rareté ; niveau 65 : 873-1310 (= les chiffres i2). `WireweaveNet` est le **PASSIF** d'`eldarRanger`
(`unit_map kit`) ⇒ `level_slot="passive"` — pas le piège de `#366-r1`, où la magnitude était indexée
par le niveau de l'ACTIVE.

## 6. La face DÉCISION — et un conjoint natif DÉGÉNÉRÉ

`IdunBattle.AI.Utilities.WireweaveNet_FirstAttack` (`UtilityType` **55** sur ce build ; 54 sur
`gqfc5mff6c`, d'où l'écriture `key-0x36` des docs) est un terme de
`ComparablePlaybook<T>$$CalculateActionUtility`, par (tuile caster, cible).
`<EvaluateAttackInSteps>d__1$$MoveNext` :

    tile = case.CasterPosition.MainTile ; if (tile == null) yield break
    if (IsAdjacentTo(case.CasterPosition.MainTile, case.CasterPosition.MainTile))
        if (GetOwnedEffects(case.Target, state, (EffectType?)0x457).Any(e => e.IsActive))
            yield return GetUtilityValue("WIREWEAVENET_AdjacentActiveEffect")

**Les DEUX opérandes d'`IsAdjacentTo` sortent du MÊME champ** : à l'assembleur, les trois appels à
`UnitPosition$$get_MainTile` sont précédés du MÊME `add rcx, 0x18` sur l'objet `UtilityAttackCase`
(aucun `mov rcx,[...+0x20]`). Et `MovementUtil$$AreTilesAdjacent` court-circuite explicitement
`tile1 == tile2 -> true` (avec `|Δélévation| = 0 < 2`). ⇒ **le conjoint est VRAI dès que
`CasterPosition.MainTile` existe : ce n'est PAS un gate d'adjacence porteur/cible.** La lecture
« cible adjacente ET cible possédant l'effet 1111 » de `docs/rl/playbook/architecture.md` (faite sur
`gqfc5mff6c`) sur-lisait ce conjoint ; elle est corrigée là-bas. Conséquence pratique : le malus
s'applique **aussi** à une attaque à distance contre une Calandis armée — le nom de la clé BC dit
l'inverse, mais le nom n'est pas le code.

Poids : `BC.Utilities.Default.WireweaveNet_FirstAttack.WIREWEAVENET_AdjacentActiveEffect` = **-30**.
Le prédicat `Any` est `e => e.GetComponent<EffectComponent>().IsActive` (lambda `b__1_0`, corps
`return *(byte*)(comp + 0x5c)`) ⇒ côté port on lit `Scene.effects(uid)`
(= `EffectsState.active_effects`, qui conjugue présence ET flag), **surtout pas** `has_effect`.

## 7. Ce qui est VALIDÉ, et par quoi

**Harnais déterministe OFFLINE** — `probe_366_r1b_wireweave_gates.py`, **10 étapes, toutes vertes** :

| étape | ce qui est exercé | mesure |
|---|---|---|
| [0] | registre (3 `Triggered()`, classe, seed) | `EFFECT_TRIGGERS[1111]` = 3 classes |
| [1] | cas POSITIF | riposte **1542** sur l'attaquant, `per_hit=[703, 839]`, **2** coups |
| [2] | `& DeactivateEffect` | 2e attaque du MÊME tour → **0** |
| [3] | fenêtre `NOT IsTurnOf(Owner)` | tour du porteur → **0** |
| [4] | `IsMeleeAttack` (POSITIONNEL) | attaquant à 2 hexes → **0** |
| [5] | `IsNormalAttack` | ACTIVE `1131` DirectTargetAttack → **0** |
| [6] | `AreEnemies` | attaquant ALLIÉ → **0** |
| [7] | `get_OwnerOrOwnerTileIsTarget` | attaque visant un autre allié → instance de Calandis INTACTE |
| [8] | machine à états | `On(0x12)` → reste OFF ; `On(0x17)` du porteur → ON ; tour ennemi suivant → riposte **1633** ; `On(0x17)` de l'ENNEMI → reste OFF |
| [9] | face DÉCISION | `-30` ssi filet armé ; `0` sans filet ; `0` si `MainTile == null` |

**Cliquets** : `probe_181` (98/98, 0 manquante), `probe_120 --step 0` (98 abilities, 0 littéral
manquant, et ses 5 étapes du vecteur `On(PreUnitAbility)` restent vertes AVEC les nouveaux triggers
inscrits), `probe_273 --only-scan`, `probe_365`. **Non-régression offline** : 51 tests
(`test_effect_trigger_channels`, les deux `test_overwatch_*` — même famille `PlayerTurnEffect`,
même machine à états —, `test_ability_registry_ratchet`, `test_366_effects_registry_partition`,
`test_366r1_carrier_active_level`) + 48 tests playbook/prédiction offline.

**NON COUVERT — la confrontation LIVE.** La session Frida (host `:8787`) est restée **injoignable**
pendant tout ce cas (aucun process `node` ni `Tacticus`) ; ce n'est **pas** une fenêtre DRAIN, c'est
une plateforme éteinte. Le montage est **écrit et prêt** :

* `probe_366_r1b_wireweave_net.py` — replay-diff RNG-seedé, 5 cas (`pos`, `--neg-owner-turn`,
  `--neg-ranged`, `--two-attackers`, `--lethal`), garde d'ATTRIBUTION incluse ;
* `tests/engine/runner/test_wireweave_net_counter_live.py` — 5 tests (positif bit-exact des DEUX
  côtés, attribution, désarmement lu sur `includeInactive`, négatif ranged, fenêtre offline-pure).

La garde d'attribution est indispensable ici et le montage la porte : Calandis a le trait
`Overwatch`, dont l'auto-attaque frappe le MÊME adversaire sur un AUTRE vecteur (le voisin a mesuré
**4197** de dégât d'overwatch sur un autre board) — « dégât > 0 sur l'attaquant » serait donc VERT
pour n'importe quel canal. On exige : la classe d'effet portée, **exactement 2** coups, chacun sous
la borne `maxDmg[passif] × multiplicateur`, plus la contre-épreuve (effet retiré) et le
contrefactuel de tour.

## 8. Ce qui n'est PAS couvert (au-delà du live)

* **`<DSLTriggers+0x20>`** — conjoint SINGLETON de `CreateTargetTrigger` : classe instanciée
  UNIQUEMENT par `DSLTriggers$$InitializeShared` (2 xrefs, toutes deux là), qui ne reçoit que
  `factory@+0x10` (le service DSL) — aucun sélecteur d'owner/cible, donc condition GLOBALE. Même
  traitement que `ctx@0x90` de `MartialSuperiority` et `ctx@0x98` des `Triggered()` d'overwatch
  (case-127 §8.3) : **non qualifié, non porté**.
* **Le slot `Caster`** — le natif lit la cible de la riposte dans `<DSLSelectors+0x48>` (`Caster`),
  pas `Actor`. Sur le vecteur `On(PreUnitAbility)` publié par `ActiveAbilityOperation` les deux
  désignent l'attaquant, et c'est `TriggerEvent.actor_id` qui le porte côté port. Le port n'a pas de
  canal caster-de-l'événement distinct d'`actor`.
* **`source = AbilityOrEffect{TriggeredAbility = 1111}`** non threadé sur l'attaque de riposte (le
  canal `ability_type` du port est keyé sur l'espace `ActiveAbilityType`) — même choix que
  `MartialSuperiority` / `MartialApotheosis`.
* **`get_OwnerOrOwnerTileIsTarget`, 2e branche** (cible = la TUILE du porteur) : structurellement
  couverte par la 1re, aucun vecteur porté ne cible la tuile d'une unité occupée.
* **Quatre SŒURS de la même base `CounterAttackEffect` non portées** :
  `GrimRetribution_CounterAttack` (1213), `SmashaSquigJaws_CounterAttack` (1104),
  `UnwaveringSentinel_CounterAttack` (1439), `WarConstruct_CounterAttack` (1286). Leur i2 montre que
  la base sert des sémantiques différentes (« the first enemy » pour GrimRetribution, « **each**
  enemy » pour WarConstruct, qui override `CreateActiveCondition`) : **chacune demande sa propre
  lecture**, ce cas ne les préjuge pas.
* **`ActivationFrequency == 1`** (la branche symétrique de `CreateHandleTriggerAbilitiesInternal`,
  qui utilise `IsEnabledTurnType` au lieu d'`IsTurnOf`) n'est exercée par aucun effet porté.
* **La face DÉCISION n'est pas confrontée live** : le terme n'est non nul que face à une Calandis
  armée, régime qui n'apparaît que pendant le tour de l'adversaire de Calandis — là où le playbook
  du porteur ne calcule rien. Il faudrait faire jouer l'IA **du camp d'en face**.

## 9. Artefacts

| quoi | où |
|---|---|
| classe d'effet | `scripts/python/engine/entities/effects/loki/counter_attack.py` |
| triggers (riposte + armement) | `scripts/python/engine/runner/operations/triggers/loki/wireweave_net.py` |
| registres | `scripts/python/engine/entities/effects/factory.py` (`EFFECT_CLASSES`, `ABILITY_INIT_OWNER_EFFECTS`), `.../triggers/dispatch/registry.py` (`EFFECT_TRIGGERS[1111]`) |
| face DÉCISION | `scripts/python/engine/utilities/wireweave_net.py` + `engine/playbook/base.py` (`calculate_action_utility`) |
| harnais offline | `scripts/python/probe_366_r1b_wireweave_gates.py` |
| montage live | `scripts/python/probe_366_r1b_wireweave_net.py` |
| gardes live | `scripts/python/tests/engine/runner/test_wireweave_net_counter_live.py` |
