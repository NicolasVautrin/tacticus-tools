# Case #231 — l'effet-marqueur 1197 inactif doit ETEINDRE la triggered 1173 (Screamer d'Abraxas)

Residu de #229 (inventaire des effet-triggers lisant `EffectComponent.IsActive @+0x5c`).
Perimetre : **UN item** — `EffectType.MasterOfTheTutelaries` = **1197** (0x4ad).

> QUALIFICATION D'ENUM (obligatoire ici) : `1197` vaut TROIS choses distinctes dans le jeu —
> `EffectType.MasterOfTheTutelaries` (ce cas), `ActiveAbilityType.ExcruciatingFrequencies`
> (playbook Loki, ligne-AoE sur tuile) et `TriggeredAbilityType.FeederTendrils` (Deathleaper).
> Rien de ce qui suit ne concerne les deux derniers.

## 1. Verdict

**Le gate n'etait PAS pose.** `MasterOfTheTutelariesSummonAbility.matches` ne lisait pas
`e.active` ; son commentaire affirmait que le gate etait « implicite par la collecte
`EFFECT_TRIGGERS` (l'effet est actif) ». **C'est faux** : `collect_effect_triggers`
(`triggers/dispatch/core.py`) ne filtre QUE sur `e.consumed`, jamais sur `e.active` — et c'est
volontaire (le rail ARRAYSET doit pouvoir RE-ACTIVER un effet eteint, cf. #127/#229).

Consequence : sur un etat portant une instance 1197 **inerte**, le port faisait apparaitre un
Screamer que le natif ne peut pas produire. Degradation **permissive**, ni erreur ni crash.

⚠ PORTEE HONNETE, mesuree (S 4) : un tel etat n'est **pas produit aujourd'hui** — le capteur ne
publie jamais 1197, donc aucun seed ne peut le faire naitre inerte, et la pose offline le cree
actif. Le gate ne deplace donc **aucun nombre** : c'est un cliquet de fidelite qui ferme une
affirmation FAUSSE du code (« implicite par la collecte »), pas une correction de divergence
observable. Il est verrouille par contre-epreuve deterministe sur etat LIVE.

## 2. Le rail natif : APPLY_REVERT, pas TARGETS

L'inventaire #229 avait deja range 1197 en `APPLY_REVERT` ; la RE le CONFIRME et en donne la
mecanique exacte. La triggered 1173 n'est pas un effet-trigger evalue par
`EvaluateEffectTriggerTargets` — c'est une **triggered-ability portee par l'UNITE** :

    IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal
        -> IdunBattleLogic.Entities.DSLFactory$$AddTriggeredAbility(Entity(target), 0x495 = 1173, abilityState)
    IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal
        -> IdunBattleLogic.Entities.DSLFactory$$RemoveTriggeredAbility(Entity(target), 0x495)

### 2.1 L'arbre du trigger ne teste PAS l'activite — littéral `onlyActive = 0`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger` :

    On(9 = Attack, 1)
      & HasEffect(owner@0x148, 0x4ad, onlyActive = 0, relation = 6)
      & AreEnemies(owner@0x148, target@0x178)
      & Not(IsObjectOrSteppable(target@0x178))
      & CurrentAttackDamageProfilesContain(0xd = Psychic)

Le 4e argument de `IdunBattleLogic.Entities.DSLFactory$$HasEffect` est **`onlyActive`**, et il
vaut **0** ici. Preuve de sa semantique, lue et non deduite —
`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` :

    foreach (effectEntity in entity.<effects>@0x10)
        if (onlyActive != 0 && effectEntity.<EffectComponent>@0x20.IsActive@0x5c == 0)
            continue;                                   // les INACTIFS sont sautes
        if (effectEntity.<EffectComponent>@0x20.EffectType@0x58 == id) return true;

Le 5e argument (`6`) est un masque de relation, decode par
`IdunBattle.Entities.EntityExtensions$$HasOneOfEffects` : `& 2` -> `IsOwnerOfOneOfEffects`,
`& 4` -> `IsTargetOfOneOfEffects`. `6 = 2|4` = **Both** (owner OU cible).

=> Le noeud `HasEffect` de l'arbre est un test de **PRESENCE**, pas d'activite. Copier un
`onlyActive=1` ici serait une INFIDELITE au littéral.

### 2.2 Le couplage a l'activite est STRUCTUREL (Deactivate -> Revert)

C'est `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` qui fait le lien :

    if (effectComp.IsActive@0x5c == 0) return new List<>();          // no-op « deja inactif »
    effectComp.IsActive@0x5c = 0;
    return UpdateEffectTargets(op, /* nouvelles cibles */ new List<>(), effectComp, ...);

La liste de nouvelles cibles est **VIDE**, donc dans
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` :
`GetTargetsToRemove(current, {})` = **toutes** les cibles courantes ->
`IdunBattle.Operations.RefreshEffectsOperation$$RemoveTargetsFromEffect` -> `Revert` par cible
-> `RevertInternal` -> `RemoveTriggeredAbility(0x495)`.

**Donc : effet 1197 inactif <=> triggered 1173 RETIREE de l'unite <=> aucun Screamer.**
Le gate offline est le mirror de CE couplage, pas d'un `onlyActive` inexistant.

La desactivation elle-meme vient de
`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`, qui appelle
`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` et, sur faux, `DeactivateEffect`.

## 3. Ce qui est porte

`MasterOfTheTutelariesSummonAbility.matches` ouvre desormais sur le gate, en tete, avant tout
autre conjoint — helper `_master_effect_is_active` (module
`runner/operations/triggers/loki/master_of_the_tutelaries.py`), qui exprime les DEUX faits
natifs distincts sur la meme liste d'instances :

1. **presence** — `HasEffect(owner, 0x4ad, onlyActive=0, Both)` : aucune instance 1197 -> False ;
2. **portage** — mirror `ApplyInternal`/`RevertInternal` pilotes par
   `ActivateEffect`/`DeactivateEffect` : au moins une instance doit etre **ACTIVE**.

Le rail ARRAYSET n'est PAS touche : `collect_effect_triggers` continue de ne filtrer que sur
`consumed`. Gater la collecte eteindrait les `Triggered()` d'activation (dont les trois de
`IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`),
qui sont precisement ceux qui RALLUMENT un effet eteint.

## 4. Confrontation live — ce qui est mesure, et ce qui ne l'est PAS

Porteur : **Abraxas `thousInfernalMaster`** — HERO present dans `rl_duel.py build --list-pool`
(rank 17), donc confrontable directement. Runner 5v5 reduit `[thousInfernalMaster]` vs
`[blackAbaddon, necroWarden]`, board MC1_67, cast LIVE de 1096 sur une tuile legale
(`abilityTargets` rend `{kind:'tile', tile:{col,row}}` -> `applyAction` avec `to:{col,row}`,
jamais un `targetId` : 1096 vise une TUILE).

**Chemin NOMINAL, confronte (2026-07-29)** : le cast reussit (`ok:true, mutated:true`), le
plateau passe de **3 a 8 unites** — 1 `thousNpc1PinkHorror` + **4 `thousNpc2Screamer`**. La
chaine 1173 est donc bien ARMEE et se re-declenche en cascade cote natif (Horror -> Screamer ->
Screamer, via le bonus Psychic `InfernalPacts_AdditionalHits` 1198 porte par Abraxas).

**Chemin INACTIF, NON confrontable aujourd'hui — et c'est une MESURE, pas une supposition** :
apres ce meme cast, l'effet 1197 n'apparait sur **AUCUNE unite, dans AUCUN des deux canaux**
(`decisionView` par defaut ET `includeInactive`). Seuls 1198 sur Abraxas et 1034
`Daemon_ExtraBlock` sur les summons sont publies. `readEffectsByUnit`
(`frida/hooks/game/effects.ts`) n'itere que `EffectsOwnedComponent.ActiveEffectIds @0x10` et ne
droppe que `removed`/`!active` — l'entite-effet 1197 n'est donc deja plus dans cette liste au
moment de la lecture, alors meme que la triggered a fire.

Consequences a assumer, plutot qu'a maquiller :

- aucune instance 1197 ne peut arriver offline **par le seed** (le capteur ne la publie pas) ;
- la pose OFFLINE (`AddEffectOperation`, le chemin qu'emprunte le port pour 1096) cree l'effet
  **ACTIF** ; aucun trigger offline n'ecrit `active` pour 1197 ;
- => **le gate est aujourd'hui INERTE** : il ne deplace aucun nombre et ne peut produire aucun
  faux refus. C'est un **cliquet de fidelite**, pas un changement de comportement.

Il est verrouille par CONSTRUCTION D'ETAT sur un etat LIVE (on ecrit le flag exactement comme
`DeactivateEffect`), ce qui est la contre-epreuve exigee — cf. section 6.

## 5. Garde

`scripts/python/tests/engine/runner/test_master_tutelaries_active_gate_live.py` (5 tests) :

1. `test_live_cast_arms_the_chain` — PREMISSE live : Horror + Screamers apparaissent.
2. `test_the_marker_is_not_published_by_any_capture_channel` — la BORNE ci-dessus, verrouillee :
   si un jour le capteur publie 1197, ce test tombe et signale que le gate devient confrontable
   live (bonne nouvelle a instruire, pas regression a etouffer).
3. `test_an_active_marker_lets_the_summon_trigger_match` — non-regression du chemin nominal.
4. `test_deactivating_the_marker_disarms_the_summon` — **LE CRITERE**.
5. `test_the_collect_rail_still_ignores_the_flag` — non-regression #229 : la COLLECTE ne filtre
   toujours pas sur `active`.

Cliquet `probe_229_effect_triggers_active.py` mis a jour : `MasterOfTheTutelariesSummonAbility`
sort de `EXPECTED_GAPS` (6 -> 5 gaps restants).

## 6. Chiffres de la contre-epreuve

Fichier de garde rejoue contre le port **d'avant** le fix (`git checkout HEAD --` du seul module
`master_of_the_tutelaries.py`) : **1 failed / 4 passed**, l'echec etant exactement
`test_deactivating_the_marker_disarms_the_summon` (« le trigger 1173 matche encore »). Avec le
fix : **5 passed**. Cibles + dependances rejouees ensemble : **23 passed** (garde #231 +
`test_load_state_inactive_effects_live.py` + `test_ability_registry_ratchet.py`) ;
`probe_229` OK ; `probe_120` OK (94 abilities, 0 litteral de ctor manquant).

## 7. Residus (NON traites ici)

- **1197 n'est publie par AUCUN canal de capture** alors que la triggered fire (mesure S 4). Deux
  lectures possibles, non tranchees : l'effet est retire tres tot (duree portee par le dernier
  argument d'`AddEffect`, `ctx@0xc0`, non decodee ici), ou il vit hors de
  `EffectsOwnedComponent.ActiveEffectIds`. Tant que ce point n'est pas tranche, la PERSISTANCE du
  marqueur cote port (le trigger 1173 reste collecte tour apres tour) n'est confrontee par rien.
  C'est le residu le plus interessant du cas — et il demande un point d'ancrage natif a hooker
  (`RefreshEffectsOperation$$RefreshEffect` ou l'`AddEffect` de 1096), donc pas faisable sans
  reinjection.
- **`Both` (owner|target) non distingue offline.** Le port lit `state.effects.by_unit` (les
  CIBLES). Sans effet observable pour 1197 — `MasterOfTheTutelariesAbility$$ExecuteBehaviour`
  pose l'effet sur SOI (`AddEffect(0x4ad, ..., caster@0x160, caster@0x160, ctx@0xc0)`), donc
  owner == target.
- **`RefreshEffectsOperation$$ShouldBeActive` non porte.** C'est LUI qui decide la desactivation
  (`RefreshEffect` : sur faux -> `DeactivateEffect`). Sa structure est lue — `param_2 == 1` ->
  toujours actif, `== 2` -> jamais, sinon `if (!effect.<slot 0xc>) return effectComp.IsActive`
  (conservation de l'etat) puis `effect.<slot 0xb>` (la condition d'activite) — mais on ignore si
  `MasterOfTheTutelariesEffect` porte une condition non triviale (corps potentiellement
  deduplique : l'absence du symbole ne prouve rien).
- Les 4 autres effectTypes nommes par #229 dont le `matches` ne lit pas le flag — **1077**
  (`HazeOfCorruptionDamageTransferTrigger`), **1201** (`AnvilShieldFrozenAdvantageExpire`),
  **1502** (`RitesOfMorkaiReviveTrigger`), **1547** (`ReanimationBeamReviveTrigger`) — plus
  **1186** (`GhostEffectRevive`), restent ouverts : un item par fiche. Attention, ils sont du
  rail **TARGETS** (`CreateTargetTrigger`), qui se gate autrement que 1197 : la, le gate NATIF est
  la double lecture d'`IsActive` par
  `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` (a l'entree, puis
  RELUE PAR CIBLE dans la boucle de drain), pas un couplage Apply/Revert.
