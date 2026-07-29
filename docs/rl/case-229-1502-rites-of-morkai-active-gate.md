# 1502 `RitesOfMorkai` — gate `EffectComponent.IsActive @+0x5c` du rail TARGETS

Résidu de `case-229-effect-triggers-active-inventory.md` (voie 1, « par-classe »). **Un seul item :
l'effectType 1502.** Les autres écarts de l'inventaire ne sont pas touchés ici — 1077 et 1197 ont été
résorbés en parallèle par #231 (`case-231-haze-transfer-active-gate.md`,
`case-231-master-tutelaries-active-gate.md`, mergés pendant ce lot) ; **1186, 1201 et 1547 restent
ouverts**.

## 1. Question et verdict

> Le `matches` du rail TARGETS de l'effectType 1502 teste-t-il, côté port, que l'effet source est
> ACTIF (`e.active`), comme le fait le natif ?

**NON — le gate était ABSENT.** `RitesOfMorkaiReviveTrigger` hérite son `matches` de
`_ReviveEffectCore` (`triggers/revive_effect.py`), qui n'a jamais consulté le flag. Le gate est posé
dans ce lot, **dans le `matches` de la seule classe 1502**.

Mesure du cliquet `probe_229_effect_triggers_active.py`, avant → après :

    1502  RitesOfMorkaiReviveTrigger    TARGETS   lit e.active : no  ->  direct
    1547  ReanimationBeamReviveTrigger  TARGETS   lit e.active : no  ->  no      (INTACT, autre item)
    écarts TARGETS/APPLY_REVERT imputables à ce lot : -1 (1502)

(le compte absolu du cliquet a bougé deux fois pendant ce lot, #231 ayant résorbé 1077 puis 1197 ;
après rebase il vaut **3** — 1186, 1201, 1547.)

## 2. Ce qu'est 1502

`EffectType.RitesOfMorkai` = l'effet « Inspired », posé par l'**active** `RitesOfMorkai`
(`ActiveAbilityType` 1211) de `spaceWolfPriest` (« Baldr », Space Wolves / Imperial) sur lui-même et
ses alliés **non-mécaniques** adjacents. i2 : « The **first time** each inspired unit would be
defeated, it is instead revived with a maximum of {hp} Health, **unless Overkilled**. »

Classe native `IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect`, sous-classe de
`IdunBattle.Entities.Effects.ReviveEffect`. Le port vit dans
`engine/runner/operations/triggers/loki/rites_of_morkai.py`.

**Confrontabilité** : `spaceWolfPriest` est un HERO **hors pool runner** — `rl_duel.py build
--list-pool --rank 17` rend 97 unités régulières + 8 MoW, dont les seuls `space*` sont
`spaceBlackmane`, `spaceHound`, `spaceRockfist`, `spaceStormcaller`, `spaceWulfen` ; il n'est ni MoW
ni summon (`kind: lineup`, qui ne prouve rien, mais aucun summoner ne l'amène). C'est aussi le
**seul** porteur de l'active `RitesOfMorkai` dans gameconfig. L'effet 1502 n'est donc pas posable en
runner : la validation reste celle de #79 — état **capturé LIVE** (board / stats / traits réels via
`load_state` sur un runner isolé) + effet 1502 **injecté** dans `state.effects`, exactement ce que
produirait le canal de seed sur une bataille contenant Baldr.

## 3. RE — la chaîne native, et laquelle des deux lectures est le gate

`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger` résout la définition d'effet
depuis l'`EffectsDatabase` (clé = `EffectComponent.Type @+0x58`) puis appelle **deux** évaluateurs
sur le même effet, avec l'entité-effet et son composant :

| évaluateur | source des triggers | gate `+0x5c` |
|---|---|---|
| `...$$EvaluateEffectTriggerEffectAbilities` | `<Effect>$$CreateHandleTriggerAbilitiesInternal` | **aucun** |
| `...$$EvaluateEffectTriggerTargets` | `<Effect>$$CreateTargetTrigger` | **deux lectures** |

`ReviveEffect` expose `CreateTargetTrigger` / `CreateTargetTriggerBehaviour` et **aucun**
`CreateHandleTriggerAbilitiesInternal` : 1502 est donc **exclusivement** sur le rail TARGETS.

Les deux lectures de `EvaluateEffectTriggerTargets`, lues au décompilé (paramètres liés depuis le
call site de `EvaluateEffectTrigger` : `param_3` = **entité-effet**, `param_4` = **EffectComponent**) :

    // LECTURE 1 -- sur le composant RECU, a l'entree : fast-path, pas le gate
    if (effectComp == null) throw;
    if (effectComp.IsActive @+0x5c) {
        if (effectComp.Targets @+0x50 == null) throw;
        if (effectComp.Targets.Count == 0) return;        // actif mais sans cible -> rien a faire
    }

    foreach (target in ArraySet(effectComp.Targets, -1)) {
        <construit l'AbilityEntities de CETTE cible>      // vtable ctx+0x18
        comp2 = GetComponent<EffectComponent>(effectEntity);   // RE-FETCH depuis l'entite-effet
        if (comp2 == null) throw;
        // LECTURE 2 -- LE GATE, par cible
        if (comp2.IsActive @+0x5c) {
            if (effect.ShouldTrigger(ctx))                // virtuel slot 0x13 = CreateTargetTrigger
                ... SelectFirst(TargetsSelector) ; events 0x15 ; Execute (slot 0x14) ...
        }
    }

- **Lecture 1** porte sur l'effet source, mais n'est qu'un court-circuit : elle ne peut que sortir
  quand l'effet est ACTIF et sans cible — un effet INACTIF traverse ce test.
- **Lecture 2** porte elle aussi sur **l'effet SOURCE** (le composant est re-lu sur `effectEntity`,
  la même entité que `param_4` décrivait), **jamais sur la cible**. C'est elle qui empêche
  `ShouldTrigger` d'être appelé. Le re-fetch par itération est significatif : une désactivation
  survenue *pendant* le drain arrête les cibles suivantes.

Côté port, `matches` est ré-évalué **par item** du drain de `evaluate_trigger_operation` (le collapse
FIFO de #201) : lire le flag dans `matches` est donc le mirror exact de la lecture 2, re-lecture
par-item incluse.

### Le rail opposé ne doit PAS être gaté

`EvaluateEffectTriggerEffectAbilities` n'accède jamais à `+0x5c` — c'est ce rail qui porte les
`ActivateEffect` capables de **rallumer** un effet éteint. Aucun trigger ARRAYSET n'a été touché ici
(le cliquet le vérifie : « rail ARRAYSET qui lit le flag hors nœud d'arbre : 0 »).

### L'inertie est ATTEIGNABLE — ce n'est pas une précaution théorique

Deux faits, l'un natif, l'autre côté port :

1. `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` éteint **n'importe quel** effet
   (`!ShouldBeActive` → `...$$DeactivateEffect`, qui écrit `+0x5c = 0` puis vide la liste de cibles).
   `...$$ShouldBeActive` — non décompilé par #229, **lu ici** — a la forme :

       if (activation == 1) return true;              // toujours actif
       if (activation == 2) return false;             // jamais actif
       if (activation != 0) throw ArgumentOutOfRange;
       if (effectComp.@+0x5e != 0) return false;      // drapeau de retrait
       if (!effect.<virtuel 0xc>(eventType)) return effectComp.IsActive @+0x5c;   // inchange
       return effect.<virtuel 0xb>(entities);         // la condition d'activite, evaluee

   `RitesOfMorkaiEffect` passe `activationFrequency = 0` à `ReviveEffect..ctor` (champ `+0x480`) —
   soit la branche **conditionnelle**, pas `1` (« toujours actif »). Aucun
   `<Effect>$$CreateActiveCondition` propre n'apparaît dans la table de symboles pour `ReviveEffect`
   ni pour `RitesOfMorkaiEffect`, mais cette absence ne prouve rien (corps triviaux dédupliqués par
   IL2CPP) et n'a pas besoin d'être tranchée : le flag est piloté génériquement.
2. Le canal de seed `decisionView { includeInactive: true }` publie `active: false`, et
   `EffectFactory.create` recopie cette clé sur l'instance depuis **#219**. C'est le vecteur
   d'exposition côté port.

> ✅ **RÉSORBÉ le 2026-07-29** — tout ce que cette section déclare « non mesurable » (et la §2
> « l'effet 1502 n'est donc pas posable en runner ») a été MESURÉ depuis :
> `case-229-1502-rites-of-morkai-live-confrontation.md`. `spaceWolfPriest` entre au pool par
> `catalog_inject.write_augmented_seed_bc` (97 -> 98), le cast est natif, `readEffectsByUnit`
> publie bien 3 instances 1502, et le revive natif est en agrément avec le port. Les paragraphes
> ci-dessous sont conservés tels quels (trace du raisonnement du lot d'origine) mais leurs
> conclusions « personne ne l'a mesuré et personne ne le peut » sont PÉRIMÉES.

⚠ **Ce que ce lot ne peut PAS mesurer, et ne prétend pas.** `case-231-haze-transfer-active-gate.md`
a RÉFUTÉ live la colonne « dans le rayon de souffle » de `case-229` §3 pour 1077 : ce bond n'est
publié par `readEffectsByUnit` **ni** au canal par défaut **ni** sous `includeInactive`. Le même
doute vaut ici : **personne n'a mesuré que `readEffectsByUnit` publie une instance 1502**, et
personne ne le peut — le porteur est hors pool, il n'existe aucune bataille runner où l'effet soit
posé. La ligne « 1502 → canal unité → OUI » de `case-229` §3 reste donc **non confrontée** et ne doit
pas être citée comme mesure.

Deux nuances structurelles, qui ne remplacent pas la mesure : 1077 est une entité de **BOND**
(`AddBondEffect` / `DefaultBondEffectBuilder`), un chemin de pose distinct, alors que 1502 est un
effet d'unité ordinaire posé par `AddEffectOperation` sur des cibles-unités — le chemin qu'alimente
`EffectsOwnedComponent`. Et le gate ne dépend pas de ce canal pour être justifié : c'est le mirror
1:1 du natif, et le port ne choisit pas ses gates selon ce qu'il sait déjà atteindre.

## 4. Le port

`RitesOfMorkaiReviveTrigger` gagne un `matches` qui pose le gate **avant** de déléguer à
`_ReviveEffectCore.matches` (ordre natif : `IsActive` précède `ShouldTrigger`) :

- `_instance_is_active(state)` = mirror du `if (+0x5c)`, sur les instances 1502 **non consommées**
  portées par `owner_id` — même forme que `_ranged_auto_attack_flag_is_set` (1009), y compris sa
  dégradation **permissive** « aucune instance trouvée → True » (on ne fabrique pas un refus ; si
  l'effet était réellement absent, `collect_effect_triggers` n'aurait instancié aucun trigger).
- `matches` = `_instance_is_active(...)` **puis** `super().matches(...)`.

Placement délibéré **au niveau de la classe 1502**, pas de `ReviveEffectTrigger` : la base est
partagée avec `ReanimationBeamReviveTrigger` (1547), qui est un **item distinct**. Le gate n'a donc
aucun effet collatéral — le cliquet le montre (1547 reste `no`).

Ce que le port **ne** change **pas** : `collect_effect_triggers` continue de ne filtrer que
`e.consumed`. Filtrer `e.active` au collecteur éteindrait aussi les 17 triggers du rail ARRAYSET
(cf. `case-229` §4, voie 2).

## 5. Validation

Gardes ajoutées dans `tests/engine/runner/test_rites_of_morkai_revive_live.py` (état LIVE, effet
injecté) :

| garde | ce qu'elle verrouille |
|---|---|
| `test_inactive_instance_does_not_revive` | `active=False` → aucun revive **et** effet NON consommé (le natif n'évalue pas le trigger, donc n'exécute pas le `RemoveEffect` du 2e volet) |
| `test_reactivated_instance_revives` | face POSITIVE : flag remis à `True` → revive normal + effet consommé (prouve que le gate lit le FLAG) |
| `test_gate_is_per_instance` | deux porteurs, une instance active / une inerte → seul le premier revit ; aucune fuite d'instance à instance |
| `test_inactive_instance_does_not_revive_alt_board` | GÉNÉRALISATION : autre roster (`eldarFarseer,astraCreed` vs `orksNob`), autre board (`C3_01`), autre seed (4242) — verdict identique + contrôle positif dans le même état |

**Contre-épreuve** (le cliquet est réel) : les mêmes gardes rejouées contre le port **pré-fix** →
`3 failed, 1 passed` (les 3 négatives tombent ; la positive passe, comme attendu d'un contrôle).
Après fix : **9 passed** sur le fichier complet.

**Non-régression** (tests ciblés, pas la suite) :

- `probe_229_effect_triggers_active.py` → `RESULT: OK` (écarts 6 → 5, ARRAYSET toujours à 0) ;
- `test_revive_retrofit_offline_live.py` + `test_narthecium_revive_live.py` +
  `test_tainted_narthecium_revive_live.py` → **29 passed** (le rail PASSIF `ReviveEffectAbility`
  partage `_ReviveEffectCore.matches` et n'est pas touché) ;
- `test_revive_cancels_death_events_live.py` + `test_ghost_revive_live.py` +
  `test_fuelled_by_fury_revive_live.py` → **13 passed**.

**Effet de bord mesuré pendant la mise au point** (pas un bug) : un premier roster alternatif
`necroOverlord` faisait échouer le contrôle **positif** — `get_HealType` de RitesOfMorkai vaut 0
(Heal), et `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` refuse les mécaniques. C'est le
comportement CORRECT (i2 : « friendly **non-mechanical** units ») ; le roster alt est donc contraint
non-mécanique, et la contrainte est écrite dans le test.

## 6. Ce qui n'est PAS couvert

- **1547 `ReanimationBeamReviveTrigger`** — jumeau strict : même base `ReviveEffect`, même rail
  TARGETS, même absence de gate. **Non traité** (un item par tâche) ; il reste dans `EXPECTED_GAPS`.
  Le correctif est le même patron (gate dans son `matches`), et son porteur — la MoW
  `necroReanimator` — est lui aussi hors pool.
- **1186, 1201** — les deux autres écarts encore ouverts de `case-229`, hors périmètre (1077 et 1197
  ont été fermés par #231 pendant ce lot).
- **La pose native de 1502** reste non confrontable (porteur hors pool) : la validation atteste le
  GATE, pas la chaîne de pose de Baldr. Les autres volets de l'ability (effet `RitesOfMorkai_Extra
  Damage`, attaque mêlée de suivi) restent le résidu de `case-66-revive-in-place.md`.
- **Le `once-per-turn` du rail PASSIF** (`ouc.revive_used_this_turn`) reste un proxy PAR UNITÉ là où
  le natif écrit le flag de l'INSTANCE (`DeactivateEffect` du `CreateTargetTriggerBehaviour` quand
  `removeEffect = 0`). Sans incidence pour 1502 (`removeEffect = TRUE`) — résidu nommé par
  `case-229` §2, inchangé.
- **`ShouldBeActive`** est désormais lu (§3) mais son `activation` (`+0x480`) n'a pas été confronté
  à un dump d'enum : la lecture « 0 = conditionnel / 1 = toujours / 2 = jamais » vient des retours
  littéraux du décompilé, pas d'un nom.
- **Aucune mesure live d'un 1502 réellement inerte** — ✅ TRANCHÉ le 2026-07-29, et dans l'autre
  sens que « faute de porteur » : le porteur est confrontable, et c'est **l'état inerte lui-même
  qui n'existe pas** en bataille (RE + mesure :
  `case-229-1502-rites-of-morkai-live-confrontation.md` §4.3). La garde exerce donc le flag par le
  chemin de seed parce que c'est le SEUL qui le produise, pas par défaut d'outillage.
- **Le rayon de souffle de 1502 n'est PAS mesuré** — ✅ MESURÉ le 2026-07-29 : `readEffectsByUnit`
  publie bien l'effectType 1502 (3 instances, canal par défaut ET `includeInactive`). Ce lot reste
  néanmoins un écart de FIDÉLITÉ et non un point de blocage : l'instance n'a pas d'état inerte à
  publier.
