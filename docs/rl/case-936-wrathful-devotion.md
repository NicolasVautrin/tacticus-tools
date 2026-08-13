# #936 — `WrathfulDevotion` : deux faces, un canal d'événement qui n'existait pas, une branche native MORTE

Passif de `worldTerminator` « Wrask », `TriggeredAbilityType` **1214** (`0x4be`).
i2 : « When Wrask arrives from Deep Strike **or** defeats an enemy in melee, he and adjacent
friendly Chaos units gain a Shield with 2910 Health for 1 round. »

Port : `engine/runner/operations/triggers/loki/wrathful_devotion.py` (RE complète en en-tête).
Mesure live : `scripts/python/probe_936_wrathful_devotion.py`.

---

## 1. Combien de faces — et l'audit en annonçait UNE

`docs/rl/kit-coverage.md` listait `WrathfulDevotion` comme « passif manquant », sans plus. La classe
native en porte **cinq corps**, lus dans le **bloc de `MethodInfo*` de la classe** (pas déduits d'une
recherche par nom) :

| corps | rôle | porté ? |
|---|---|---|
| `<.ctor>` | trivial, **fondu par l'ICF** (`xor edx,edx ; jmp Object..ctor`) | sans objet |
| `$$CreateTrigger` | les DEUX faces | oui |
| `$$CreateBehaviour` | le bouclier + un marqueur selon `triggerType` | oui, **sauf la branche morte** |
| `$$GetTargets` | le sélecteur complet | oui (foyer unique) |
| `$$GetOtherTargets` | le même, sans le porteur | oui (foyer unique) |

⚠ **Le `.ctor` n'appelle AUCUN `TargetingOptions$$.ctor`** — lu au désassemblage. C'est la forme
attendue d'une TRIGGERED : `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` sont des données
d'`ABILITY_CLASSES` (les ACTIVES), et cette ability n'y entre pas.

⚠ **Sa voisine immédiate dans le même bloc, `WraithcannonAbility`, surcharge
`$$CannotBeGuaranteedKilled` et `$$CreateSimulationBehaviour` — pas elle.** Lire le bloc, et pas
seulement les symboles voisins, est ce qui sépare les deux.

## 2. Le piège : un immédiat effacé, dans le troisième espace d'enum

```
$$CreateTrigger =
    ( On(EventTriggerType.UnitDefeated = 0x36, ownerNeedsToBeAlive: 1)
      & get_OwnerIsActor
      & IsDefeatedByMeleeAttack(Target@DSLSelectors+0x60, countRevived: 0, countResurrected: 1) )
  | ( On(EventTriggerType.UnitBecameTargetable = 0x3b, 1)
      & get_OwnerIsTarget
      & CurrentAbilityIs(AbilityOrEffect((EffectType)0x40b = TeleportStrike_TeleportingIn)) )
```

Le pseudo-C rend `CurrentAbilityIs(op_Implicit(local_28))` — **l'immédiat est effacé**. Au
désassemblage : `lea rcx,[rsp+0x50] ; mov edx, 0x40b ; call <op_Implicit>`, et la **cible du call**
tranche parmi les **quatre** homonymes (`frida/methods.tsv`, résolus à l'ADRESSE) :

| surcharge | argument |
|---|---|
| `op_Implicit(triggeredAbility: TriggeredAbilityType)` | ce que le voisin de forme écrirait |
| `op_Implicit(activeAbility: ActiveAbilityType)` | |
| **`op_Implicit(effect: EffectType)`** | **celle-ci** |
| `op_Implicit(abilityType: AbilityType)` | |

Et 1035 est **valide dans les trois espaces**, où il nomme trois choses sans rapport :
`EffectType.TeleportStrike_TeleportingIn`, `TriggeredAbilityType.UnstoppableFerocity`,
`ActiveAbilityType.PlagueWind`. Recopier le voisin (`MartialSuperiority`, `CursedPlagueBell`, qui
écrivent un `TriggeredAbilityType` sur **leur propre** ability) aurait posé un gate parfaitement
silencieux et parfaitement faux.

⚠ **Les DEUX `op_Implicit` de la même classe empruntent DEUX surcharges différentes** : celui du
`CreateShield` (le `source`) passe bien par `TriggeredAbilityType`, et son argument n'est pas un
immédiat mais `this.Id` — un getter trivial que Ghidra attribue à
`CenterSpace.Free.MersenneTwister$$get_Count` (ICF).

## 3. Le VERDICT DEAD, et il est structurel

```
$$CreateBehaviour(abilityState, triggerType) :
    targets = Owner@+0x30 op_Addition UnitsWithTrait(AdjacentFriends(Owner@+0x30, unique: 1, 3),
                                                     UnitTrait.Chaos = 0x7ea, 3)
    shield  = CreateShield(targets, Direct(GetVariableForLevel(shieldHp = 0x27)),
                           AbilityOrEffect((TriggeredAbilityType)this.Id),
                           TurnsFromRounds(1), createdByEffect: null, stackable: true)
    switch (triggerType) {
      case UnitDeath = 0:              return shield + Foreach(targets, b__0)   // <-- MORTE
      case UnitBecameTargetable = 0x3b: return shield + Foreach(targets, b__1)
      default:                          return shield                            // <-- la face A
    }
    b__0(t) = If(NOT HasEffect(t, 0x517 WrathfulDevotionKilled_Visual,     onlyActive: 0, Both), AddEffect(...))
    b__1(t) = If(NOT HasEffect(t, 0x518 WrathfulDevotionTeleported_Visual, onlyActive: 0, Both), AddEffect(...))
```

**La branche `triggerType == UnitDeath` est INATTEIGNABLE**, donc `b__0` et `0x517` avec elle.
Trois lectures, aucune n'est une absence :

1. `$$CreateTrigger` n'appelle `DSLTriggers$$On` que **deux** fois, avec `mov edx, 0x36` et
   `mov edx, 0x3b` — immédiats **lus au désassemblage** ;
2. `BaseTriggeredAbility$$GetEventTriggers` construit la liste des événements abonnés en **visitant
   cet arbre** (slot `IEventTriggersProvider` +0x198) et **journalise une erreur** si elle sort vide
   — c'est elle, et rien d'autre, qui décide de l'abonnement ;
3. `EvaluateTriggerOperation$$EvaluateAbilityTrigger` passe l'`EventTriggerType` **de l'événement
   courant** à `$$ExecuteBy`, qui le relaie tel quel au slot virtuel `$$CreateBehaviour` (+0x2e8).

⇒ `triggerType ∈ {UnitDefeated, UnitBecameTargetable}`, jamais `UnitDeath`. La face « kill en
mêlée » retombe donc en `default` : **bouclier seul, aucun marqueur**. C'est le résidu d'un
`On(UnitDeath)` remplacé par `On(UnitDefeated)` dans le trigger sans que le `switch` ait suivi —
le voisin `DawnBlade_HealAbility`, qui appelle le MÊME `IsDefeatedByMeleeAttack`, écoute bien
`On(UnitDeath = 0)`.

**Le jeu le confirme** : sur la face A, le NATIF ne pose aucun marqueur (mesure §5).

Gravé sur trois crans : les abonnements déclarés par le port, l'absence de tout poseur de 1303 dans
`engine/**` (avec assertion de non-vide sur 1304), et **deux étages binaires** qui re-dérivent les
immédiats `On(x)` et les comparaisons du `switch` depuis le PE — ils rougiront si un build futur
rebranche `On(UnitDeath)`.

## 4. Le canal `On(UnitBecameTargetable)` — AJOUTÉ par cette tranche

Le port **n'émettait ce vecteur nulle part**. C'est la raison exacte pour laquelle
`SavageKillerAbility` n'abonne pas sa 4ᵉ disjonction (résidu **#929-r1**, désormais **débloqué** :
le canal existe, son `NOT moved` reste à porter).

Point d'émission natif, en **queue** de `RemoveEffectOperation$$Execute`, après `On(0x40)` et son
`Inform(4)` :

```
if (EffectsDatabase.GetEffect(effectComponent.Type@+0x58) is UntargetableEffect) { On(0x3b) ; Inform(5) }
```

⚠ **La classe testée est LUE, pas déduite.** Le pseudo-C ne rend qu'un `DAT_<slot>` (un
`Il2CppClass**` à zéro sur disque). Le **même slot** est lu par **trois** fonctions :
`AddEffectOperation$$Execute` (gate symétrique d'`On(0x46 = UnitBecameUntargetable)`),
`RemoveEffectOperation$$Execute`, et
`EffectsDatabase.<>c$$<InitializeEffects>b__14_576` — **qui alloue ce type et appelle
`IdunBattle.Entities.Effects.Common.UntargetableEffect$$.ctor`**. C'est cette troisième xref qui
nomme la classe.

Côté port, le gate vit chez l'appelant (`remove_effects.py::remove_effect_instance`) et consulte le
foyer unique déjà existant du prédicat : `entities/effects/aura_selectors.py::UNTARGETABLE_EFFECT_TYPES`.

**Rayon de souffle du foyer** : `remove_effect_instance` a **trois** consommateurs exécutables — la
feuille DSL `RemoveEffect` (`behaviours/effects.py`), `remove_effects_operation` (la séquence de
mort, via `damage.py`) et sa propre récursion `_remove_sub_effects`. L'ajout est **conditionnel**
(3 `EffectType` sur 629) et **purement additif** : il publie un événement dont l'unique
consommateur est cette ability. Les quatre fichiers de régression de ces consommateurs sont verts
(§5).

## 5. Ce que le JEU a dit (2026-08-11, build `rnca9r7q6c`, rank 17, mult 180 %)

Montage : `worldTerminator + worldJakhal + orksNob` vs `ultraTitus`, board `MC1_67`, seed 777.
Chaque unité est un **témoin** : `worldJakhal` est Chaos (positif quand adjacent, négatif quand
loin) et `orksNob` est **Xenos et adjacent** — le seul qui sépare `UnitsWithTrait(Chaos)` d'un
« tous les alliés adjacents ».

| régime | boucliers live | boucliers port | `Teleported` live/port | `Killed` live/port |
|---|---|---|---|---|
| **B** — `finish` (sortie de Deep Strike) | `{79: 3989, 81: 3989, 83: 0}` | idem | `[79, 81]` / `[79, 81]` | `[]` / `[]` |
| **A** — kill en mêlée | `{79: 3989, 81: 0, 83: 0}` | idem | `[]` / `[]` | `[]` / `[]` |

`3989` = `shieldHp[49] × 180 %`, `remaining = 2` tours (= `TurnsFromRounds(1)` à deux joueurs).
Le canal `combatSnapshot.units[].traits` **porte bien** le pseudo-trait d'alliance : Wrask et
Jakhal ont `2026`, `orksNob` a `1006`.

**MUTANTS : 20 posés, 20 mordent** (17 offline, 3 live). Un seul avait dû être déplacé :
supprimer le gate `is UntargetableEffect` de l'émetteur restait **inerte** tant que la garde
regardait l'**aval** (le bouclier), parce que `CurrentAbilityIs(1035)` de l'ability refuse déjà
tout autre effet. Elle observe désormais l'**appel** par substitution — un vecteur sur-émis reste
une divergence, même invisible en aval.

## 6. Résidus

* ~~**`#936-r1`**~~ — **FERMÉ**. L'échéance route désormais par `remove_effect_instance` :
  `EffectsState.on_turn_end` reçoit le `state` et n'y pose plus `consumed` en direct. Détail et
  chaîne native re-lue : **§6bis** ci-dessous. Résidu restant : **`#936-r1-r2`** (les ENFANTS d'un
  composite expiré, encore pris par la cascade `parent_type`).
* **`stackable: true`** (7ᵉ argument de `CreateShield`) : non modélisé — la feuille du port appelle
  `ShieldComponent.add_or_update_shield`, qui cumule déjà à source et durée égales. Écart
  préexistant du foyer `CreateShield` (`ArcaneShield` est dans le même cas), pas de cette tranche.
* **`countRevived: 0` / `countResurrected: 1`** : les deux drapeaux d'
  `UnitsDefeatedByMeleeAttackSelector` ne sont pas modélisés — dans tout régime porté, une victime
  revivée n'atteint pas la séquence de mort. Même lecture, même mot, que `dawn_blade.py`.
* **le marqueur « défaite par attaque de MÊLÉE »** est approximé POSITIONNELLEMENT
  (`_is_ranged_position`), le champ natif n'ayant aucun canal sur ce vecteur. Même collapse et même
  foyer que `DawnBladeHealAbility`, l'autre consommateur porté du nœud. La dégradation est du bon
  côté : omettre le gate rendrait le trigger permissif.
* **`AddEffect(..., targets, ...)` et non `(..., target, ...)`** : le lambda reçoit un `target` mais
  ne s'en sert que pour son `HasEffect` ; l'`AddEffect` porte sur le sélecteur complet capturé par
  le `<>c__DisplayClass1_0`. Transcrit tel quel.

## 6bis. `#936-r1` — l'échéance et le retrait explicite convergent sur UN corps

**La prémisse du résidu a été re-mesurée au décompilé, et elle TIENT — avec une nuance de mécanisme
qu'elle n'écrivait pas.** Le résidu disait « le natif n'a qu'UN chemin, atteint aussi bien par
`RefreshEffectsOperation$$RefreshEffect` que par un retrait explicite ». `RefreshEffect` n'appelle en
fait **rien** : sur `EffectComponent$$ShouldBeRemoved` il fait `RefreshEffectsOperation$$DeactivateEffect`
(le revert, par `UpdateEffectTargets([])`) puis **enfile une `System.Action` différée** dans la liste
que `$$GenerateEventGroup` consommera. C'est la lecture de cette action qui ferme la question :

```
IdunBattle.Operations.RefreshEffectsOperation.<>c__DisplayClass9_0$$<RemoveEffect>b__0(this) =
    processor.<slot 0x11>(this.effectEntity@+0x18)          // corps ENTIER, tail-call
```

et le slot 0x11 est celui que `RemoveEffectsOperation$$Execute` appelle déjà — donc
`IdunBattle.Operations.RemoveEffectOperation$$Execute`. L'échéance publie bien les trois vecteurs.

Le décrément, lui, est **une autre Operation** : `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`
ne fait que `EffectComponent$$RemoveOneTurn` sous le gate `!Removed@+0x5f && HasTurns@+0x5d`, puis
appelle le slot 0x2f avec `RefreshEffectOptions(trigger = RefreshEffectTrigger.TurnChanged = 6)`.

**Ce que le port faisait, et ce qu'il fait maintenant.** `on_turn_end` posait `consumed = True` :
aucun des trois vecteurs, et le NOM restait collé à l'`EffectsOwnedComponent` du porteur (canal LU
par la couche DÉCISION). Il prend désormais un `state` et route la branche « échéance » par
`remove_effect_instance` — le foyer unique. `turnflow.EndTurnOperation` le lui passe.

* **REPLI `state is None`** = la marque seule, comportement strictement antérieur. Ce n'est pas une
  alternative : c'est le régime d'un `EffectsState` sans `OperationProcessor` (la face DÉCISION n'a
  pas de `runner.State`, et rien n'y appelle ce tick).
* **Écart d'ordre nommé** : le natif reverte AVANT `On(0x3f)` (le `DeactivateEffect` précède
  l'action) ; `remove_effect_instance` publie `On(0x3f)` puis reverte — c'est l'ordre du corps de
  `RemoveEffectOperation$$Execute`, où le revert est de toute façon éteint par `IsActive == 0`.
  Inobservable : aucun consommateur porté n'écoute `On(0x3f)`.
* **Rayon de souffle mesuré** : le tick balaye TOUTES les clés de `by_unit`, tuiles comprises.
  `unregister_name` est no-op sans `EffectsOwnedComponent`, et les trois vecteurs sont des dispatches
  par ability — une entité-tuile n'en porte aucune. 137 tests offline de régression rejoués verts
  (`test_448_r2c`, `test_231r1`, `test_seeded_eager_statmod_expiry`, `test_936`, `test_477r22`,
  `test_462r4eor2r1r1`, `test_287r11r1r1r1r1`, `test_static_statmod_g1_expiry`,
  `test_shock_assault_buff_expiry`, `test_overwatch_single_shot_per_activation`).

Garde : `tests/engine/runner/test_936r1_expiry_removal_offline.py` — étage binaire (le slot 0x11
re-dérivé du PE à chaque passe) + les deux contre-épreuves mordantes (avant échéance : le décrément
mord et rien ne sort ; sans `state` : la marque, et le nom reste collé).

## 7. Deux réparations de fichiers tiers, exigées par ce merge

`probe_457 --measure-missing` a gravé l'empreinte de trois fichiers qui n'en avaient aucune, et
`probe_486r15` est alors passé de « une source » à « deux sources » sur eux — révélant deux
déclencheurs **trop étroits**, tous deux **latents** jusque-là :

* `test_927_fury_offline.py` construisait `BUILD_DIR` par un `os.path.join` **non résolu** : le
  chemin ouvert portait des `..`, que le glob `data/symbols/**` du champ `build: True` ne matche
  pas. Corrigé par `os.path.realpath`.
* `test_929_savage_killer_offline.py` ne déclarait pas `data/i2_en.json`, que `gameconfig` ouvre.

Sans ces deux lignes, `master` serait devenu rouge **au merge** — le scénario exact que la doc de
`probe_486r15` décrit (PR #832, commit `18edd540`).

## 6ter. `#936-r1-r2` — prémisse RE-MESURÉE (2026-08-13), et elle est CONFIRMÉE en plus étroit

Le résidu se déclarait lui-même **INOBSERVABLE**. Re-mesuré sur l'arbre courant, il l'est —
mais deux de ses chiffres avaient bougé, et le second RÉTRÉCIT le résidu :

1. **`On(0x3b = UnitBecameTargetable)` a désormais DEUX consommateurs portés, pas un** :
   `SavageKillerAbility` (entré depuis) **et** `WrathfulDevotionAbility`. Le premier comptage
   ne voyait qu'un canal de souscription — la plomberie du dispatch teste `event_id` **puis**
   `event_ids`, et `SavageKiller` s'abonne par le second. `On(0x3f = PreEffectRemoved)` et
   `On(0x40 = EffectRemoved)` restent, eux, à **0** consommateur porté.
2. **Aucun parent porté ne déclare d'enfant PERMANENT.** Sur les **236** classes d'effet du
   registre, les `sub_effects_on_apply` déclarent **9** types ENFANTS ; **0** est `Untargetable`
   (les trois `*_TeleportingIn` d'`UNTARGETABLE_EFFECT_TYPES`) et **0** est posé sans
   `SAME_TURNS`. Or un enfant same-turns arrive à échéance dans la MÊME boucle que son parent et
   passe donc, lui, par le foyer.

⇒ le résidu ne porte plus que sur les enfants dont le lien parent est **reconstruit à
l'hydratation** (`snapshot._load_effect_parent_links`), ceux que `_remove_sub_effects` ne voit
pas. L'exercer demande un **seed** où un `*_TeleportingIn` est enfant d'un composite — d'où le
`BLOCAGE: seeding` désormais porté par la ligne du backlog (il n'en portait aucun de substantiel).

Re-dériver plutôt que citer : balayage du registre de `triggers/dispatch/registry.py` sur
`event_id` ∪ `event_ids`, et des `sub_effects_on_apply` de `EFFECT_CLASSES` croisés avec
`UNTARGETABLE_EFFECT_TYPES`.
