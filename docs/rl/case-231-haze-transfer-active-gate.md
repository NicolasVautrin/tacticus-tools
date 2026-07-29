# #231 — Le report 1077 lit le flag `EffectComponent.IsActive`

Résidu de #229 (inventaire). Question binaire posée : **le `matches` du rail TARGETS de l'effectType
1077 (`HazeOfCorruption_DamageTransfer`) teste-t-il, côté port, que l'effet source est ACTIF, comme
le fait le natif ?**

**Réponse à l'ouverture : NON.** `HazeOfCorruptionDamageTransferTrigger.matches` cherchait son
instance via `_instance()`, qui ne filtrait que `consumed`. **Réponse après ce commit : OUI.**

## 1. Le natif — le gate est PAR CIBLE, dans la boucle

`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger` appelle DEUX évaluateurs sur
le même effet, avec des rôles distincts (décompilé lu, build `gqfc5mff6c`) :

    def = EffectsDatabase.Get(effectComponent.Type @+0x58)     # la définition d'effet
    trg = def.<slot 0x26>(effectEntity)                        # = <Effect>$$CreateTargetTrigger
    EvaluateEffectTriggerEffectAbilities(..., effectEntity, def, ...)   # rail ArraySet
    EvaluateEffectTriggerTargets       (..., effectEntity, effectComponent, def, ..., trg)

Dans `...$$EvaluateEffectTriggerTargets`, la boucle sur les cibles de l'effet RECHARGE
l'`EffectComponent` depuis l'entité-effet à CHAQUE itération, et c'est ce composant rechargé qui
porte le gate :

    <component> = GetComponent<EffectComponent>(<effectEntity>)
    if (*(char *)(<component> + 0x5c) != '\0') {          # <-- LE GATE
        if (<def>.<slot 0x13>(trg, entities, evt)) {      # ShouldTrigger
            ... <def>.<slot 0x15> -> TargetsSelector.SelectFirst ... (log d'événement)
            <def>.<slot 0x14>(trg, ..., entities, evt)    # Execute
        }
    }

Deux conséquences lues, pas déduites :

1. **une instance INERTE n'est pas évaluée du tout** — ni `ShouldTrigger`, ni `Execute` ;
2. **une désactivation survenue EN COURS DE DRAIN stoppe les cibles suivantes** (le composant est
   rechargé par itération, pas capturé une fois).

Un second accès à `+0x5c` existe à l'entrée de la fonction, sur l'`EffectComponent` reçu en
paramètre, mais il n'encadre qu'un court-circuit (`Targets.Count == 0 -> return`) : quand le flag
est faux, le flot passe quand même à la boucle — où le gate ci-dessus tue chaque itération. C'est
donc **le gate par-cible qui porte la sémantique**, et c'est lui qu'on mirroire.

`IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger`
existe : 1077 est bien sur le rail gaté.

### Ce qu'il ne faut SURTOUT pas gater

`...$$EvaluateEffectTriggerEffectAbilities` — le rail des `Triggered()` de
`<Effect>$$CreateHandleTriggerAbilitiesInternal` — **n'accède JAMAIS à `+0x5c`**. C'est nécessaire :
ce rail porte les `ActivateEffect` qui RALLUMENT un effet éteint. Le gate se pose donc dans le
`matches` de la classe du rail TARGETS, **jamais** dans `collect_effect_triggers`, qui collecte les
deux rails (17 triggers ArraySet aujourd'hui). Une garde le verrouille désormais
(`test_le_gate_ne_vaut_que_pour_le_rail_targets`).

## 2. Le port

`engine/runner/operations/triggers/loki/haze_of_corruption.py` —
`HazeOfCorruptionDamageTransferTrigger.matches`, juste après la résolution de l'instance :

    if not inst.active:
        return False

`BaseEffect.active` est le mirror du flag (`+0x5c`), distinct de la MÉTHODE `is_active()` qui
mirroire `<Effect>.CreateActiveCondition`. Le collecteur reste inchangé (`e.consumed` seul).

## 3. Portée RÉELLE du correctif — mesurée, pas supposée

Trois canaux peuvent écrire `active = False` sur une instance côté port. Aucun ne concerne 1077
aujourd'hui, et il faut le dire :

| canal | écrit `active=False` ? | atteint 1077 ? |
|---|---|---|
| pose offline (`AddEffectOperation`, donc `AddBondEffect`) | non — `captured` n'a pas la clé, défaut `True` | — |
| `RemoveEffect` (le `GetRemoveEffectBehaviour` du report) | non — écrit `consumed = True` | — |
| seed `decisionView { includeInactive: true }` → `EffectFactory.create` | **oui** | **non** (§3.1) |

### 3.1 MESURE LIVE — 1077 est HORS du canal de seed (réfute #229 §3)

`probe_231_haze_transfer_active_gate.py`, montage k=1 de case-207, `--hp-target 90000` (la cible
SURVIT, donc le bond posé reste en place au lieu d'être consommé dans la même action), seed 777,
board MC1_67. Décomposition par étage :

- **étage 0 — le bond est POSÉ** (témoin exigé avant toute lecture de canal) : le flux natif publie
  `{BondEffect_BondedId: 83, Effect_SourceId: 77, Effect_SourceTriggeredAbility: 1076,
  Effect_RemainingTurns: 1, Effect_CurrentLevel: 1, Effect_Id: 107}` — 83 = Maladus (le bonded),
  77 = la cible initiale (l'`EffectSource`).
- **étage 1 — le canal SAIT publier un inerte** : `decisionView { includeInactive: true }` rend
  **4 entrées `active: false`** sur ce même état (`ContagionsOfNurgle_ArmorReduction2` sur 77/79/81,
  `ContagionsOfNurgle_ArmorReduction1` sur 81), absentes du canal par défaut. Le vecteur
  d'exposition du gate est donc RÉEL et vérifié live.
- **étage 2 — 1077 n'est publié par AUCUN des deux canaux** : 0 entrée au canal par défaut, **0
  aussi avec `includeInactive`**. Ce n'est donc pas « inactif et filtré » : le bond n'entre pas dans
  ce que `readEffectsByUnit` publie.

**Conséquence** : la ligne « 1077 → canal unité → OUI dans le rayon de souffle » de
`case-229-effect-triggers-active-inventory.md` §3 est **fausse**. Basculer `includeInactive` en
défaut au seed ne peut pas seeder un 1077 inerte — il n'y a rien à seeder. Le compte des
effectTypes qui bloquent réellement cette bascule tombe de 5 à 4.

Le gate reste néanmoins posé, et pour deux raisons qui ne dépendent pas de ce canal : c'est le
mirror 1:1 du natif (le port ne choisit pas ses gates en fonction de ce qu'il sait déjà atteindre),
et il rend le port correct par construction si un futur canal publie le bond, ou si un chemin
offline vient à éteindre l'instance.

**RÉSIDU NOMMÉ** : pourquoi le bond échappe-t-il à `readEffectsByUnit` ? Deux hypothèses non
départagées — (a) l'entité-effet de bond n'est pas inscrite dans l'`EffectsOwnedComponent
.ActiveEffectIds` du relais, (b) elle y est mais `indexEffects` ne la décode pas. Trancher demande
un hook côté `frida/hooks/game/effects.ts`, hors périmètre de cette fiche.

## 4. Validation

- **Contre-épreuve du cliquet** (le moteur restauré à HEAD, gardes à jour) :
  `test_le_report_n_est_pas_evalue_quand_l_instance_est_inerte` **ÉCHOUE** (`assert True is False`)
  et `probe_229_effect_triggers_active.py` **ÉCHOUE** (`nouveaux : ['HazeOfCorruption
  DamageTransferTrigger']`). Après correctif : les deux passent.
- **Gardes ajoutées** (`tests/engine/runner/test_haze_of_corruption_transfer_live.py`, section
  OFFLINE) : le gate lui-même AVEC son témoin actif, la contre-garde d'infidélité sur le
  collecteur, et le transport du flag par `EffectFactory.create`.
- **Non-régression LIVE du chemin nominal** — le fix est sur le `matches` de production :
  `test_haze_of_corruption_transfer_live.py` **9/9** (dont 4 live, régimes PV 6000/5000/8000 et le
  discriminant deux-seeds), `test_haze_bonded_chain_live.py` **18/18** (chaîne k=2, 4 seeds
  chaînants + 2 non-chaînants, bit-exactitude RNG et dégâts). Total **27/27**.
- **Confrontabilité** : `deathBlightlord` (Maladus, porteur du passif `HazeOfCorruption` qui pose le
  bond) est HERO et présent dans `rl_duel.py build --list-pool`, comme les trois unités du montage
  (`astraBullgryn`, `astraDreir`, `astraOrdnance`).

### Ce qui n'est PAS couvert

- Aucun scénario LIVE ne fait exister un 1077 INERTE : rien dans le kit ne l'éteint (pas de
  `CreateHandleTriggerAbilitiesInternal` porteur d'un `DeactivateEffect` sur 1077), et le canal de
  seed ne le publie pas (§3.1). Le gate est donc validé par le décompilé + les gardes
  déterministes, pas par un différentiel d'observable live — et c'est dit ici plutôt que maquillé.
- `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` n'est toujours pas décompilé : on
  sait qu'il pilote le flag pour TOUT effet, pas quelles conjonctions il porte (résidu #229 §5).
- L'existence d'un `HazeOfCorruption_DamageTransferEffect$$CreateActiveCondition` propre n'est pas
  tranchée : absent de la table de symboles, ce qui **ne prouve rien** (corps triviaux dédupliqués).
- Les **quatre** gaps restants du rail à gate natif (1197 `MasterOfTheTutelaries`, 1201
  `AnvilShield_FrozenAttackerAdvantage`, 1502 `RitesOfMorkai`, 1547 `ReanimationBeam_Revive`) plus
  1186 `GhostEffectRevive` (rail tuile, hors canal) : hors périmètre, une fiche chacun.
