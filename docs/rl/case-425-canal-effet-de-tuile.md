# case-425 — `readEffectsByTile` rendait « aucune tuile marquée » : la cause était le MONTAGE

**Verdict : le canal est SAIN de bout en bout. Aucun fichier `engine/` ni `frida/hooks/*` à
corriger.** Le résidu de canal nommé par #448-r1 (« le −100 est inatteignable côté port », capteur
à poser, reinject requis) est **RÉFUTÉ par mesure**.

## 1. Ce qui était mesuré, et ce qu'on en avait conclu

#448-r1, montage `StormboyzStrike` greffé sur `orksNob` / `MC1_67` / seed 777 : après un
`applyAction {kind:"finish"}` sur le porteur, entités `EntityType.Effect` **17 → 18**, et **aucune**
tuile marquée dans `tileMeta`, même sous `includeInactive: true`. Le point était laissé NON TRANCHÉ,
faute de canal nominatif : le `+1` d'entité n'était pas identifié, donc « la tuile ne possède pas
l'effet » et « le capteur le filtre » restaient indiscernables.

## 2. Le canal nominatif qui tranche

`effectAbilityStates` (`frida/hooks/features/ai-step/rpc-snapshot.ts`) balaie **toutes** les entités
`EntityType.Effect` et publie `{effectId, effectType, name, source, active}` — **sans aucun filtre
d'appartenance**. Il était déjà embarqué. Mesure sur le montage d'origine :

    +id=98  type=1179  name=StormboyzStrike_AlreadyUsedTile  source=15  active=False

L'effet **existait**, nommément. Et `source` le rattache à une entité précise, parce que le natif le
garantit :

* `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)` — la
  surcharge à quatre arguments, celle qu'emploie `StormboyzStrike_FallbackAbility$$CreateBehaviour` —
  passe **`source = NULL`** au ctor d'`AddEffectBehaviour` ;
* `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor(logger, effectType, abilityState,
  source, targets, options)` range `source@+0x60` / `targets@+0x68` (noms de paramètres NATIFS) ;
* `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` itère `targets@+0x68` et appelle
  `AddEffect(source = <sel. source> ?? <cible itérée>, owner = <cible itérée>, …)` — avec
  `source = NULL`, **`SourceUnitId == OwnerId`**.

`dumpEntityComponents(15)` rend les huit composants de `IdunBattle.Entities.Blueprints$$Tile`
(`TileComponent`, `PositionComponent`, `ConnectivityComponent`, `TileContentComponent`,
`TileMovementComponent`, `EffectsOwnedComponent`, `TriggeredAbilityComponent`, `OwnerComponent`) et
`boardGraph` la situe en **(0,3)**. L'owner **est** une tuile, et elle est **publiée** par
`tileMeta` (`boardGraph` = 63 tuiles, `tileMeta` = 63) — mais sans l'effet.

## 3. La cause : la marque était consommée dans le même `applyAction`

`StormboyzStrike_FallbackAbility$$CreateBehaviour` pose
`AddEffect(0x49b, AbilityStateReference, targets: <tuile>, turns: Nullable<int>(1))` — **une durée
d'UN tour**. Le montage n'avait **qu'une seule unité alliée** (le porteur greffé), donc son `finish`
**clôturait le tour d'équipe** : la durée était décomptée aussitôt et l'effet quittait
l'`EffectsOwnedComponent.ActiveEffectIds` de la tuile avant toute lecture. `active=False` dans le
canal sans filtre, absence dans `tileMeta` — **absence CORRECTE**, pas un trou de capteur.

**Contre-épreuve, même seed / même board / même greffe, roster allié `orksNob,ultraTitus`** :

| | roster `[porteur]` | roster `[porteur, allié]` |
|---|---|---|
| entités `EntityType.Effect` | 17 → 18 | 20 → 21 |
| entité `1179` | `id=98`, `active=False` | `id=103`, **`active=True`** |
| owner (`SourceUnitId`) | 15 = tuile (0,3) | 15 = tuile (0,3) |
| `tileMeta` | **AUCUNE** tuile marquée | **(0,3) → `1179`, `remaining=1`** |

Les quatre étages du brief sont donc départagés : **capteur OK, décodeur OK, transport RPC OK,
ingestion OK — c'est le MONTAGE**.

## 4. Quirk natif trouvé au passage : la tuile marquée n'est PAS celle d'atterrissage

Le porteur atterrit en **(1,3)** (entité 24) ; la tuile marquée est **(0,3)** (entité 15).
`MoveUnitBehaviour` et `AddEffect` reçoivent le **même objet-nœud** sélecteur
(`First(SortTilesByUtility(CanAddUnit(<AllTilesSelector>), Caster, UtilityDefinition(6 =
UnitMovement), null), Direct(1))`, `local_78` dans le décompilé), mais l'opérateur `&` les exécute
**en séquence** : à la ré-évaluation, le caster occupe déjà la meilleure tuile, `CanAddUnit`
l'exclut, et `First` rend la **suivante** du classement.

⇒ **`case-448-r1` §5 B3 (« la tuile marquée est EXACTEMENT celle où il a atterri ») est FAUX** —
c'était une attente d'écriture, jamais confrontée (le tableau de mesure disait « aucune » des deux
côtés). Corrigé, et figé par un test.

## 5. Ce qui est livré

* **`scripts/python/tests/engine/runner/test_425_tile_effect_channel_live.py`** — 4 gardes live,
  1 runner : E1/E2 (accord des deux canaux INDÉPENDANTS `tileMeta` ↔ `effectAbilityStates`, owner
  == tuile marquée, NOM publié = clé de poids), E2b (le quirk du §4), E3 (`load_state(tiles=…)`
  matérialise la marque, empreinte offline == live, **témoin** `tiles=None` → vide), E4 (la feuille
  `TileEffectsUtility` du port rend **−100** sur la position marquée, **contre-bras** tuile propre
  → 0). Mutation **M1** (retrait de l'allié) → **4 rouges**.
* **`scripts/python/probe_425_tile_effect_channel.py`** — la mesure, étage par étage (E1..E6),
  jouable sur les deux bras (`--allies`).
* **`scripts/python/probe_448_r1_stormboyz_fallback_miss.py`** — montage corrigé (allié par défaut),
  et B3 ne dépend plus de `dumpEntityComponents` (qui ne rend que la STRUCTURE) mais de
  `effectAbilityStates`, qui donne l'owner.

## 6. Résidus NOMMÉS

* **`#425-r1` — le gate `IsActive` du port n'existe pas dans le natif.**
  `IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
  itère `EffectsOwnedComponent.ActiveEffectIds` et fait `Enum.ToString(EffectComponent+0x58)` →
  `HasUtilityValue` → `GetUtilityValue` **sans aucun gate sur `IsActive` ni `Removed`**. Or
  `engine/ai/context.py::build` demande `tileMeta` **sans** `includeInactive`, donc
  `readEffectsByTile` filtre `!active`. Un effet de tuile **posé-mais-inactif** serait compté par le
  natif et pas par le port. **Chiffré, pas supposé** (probe #425 étape E6, `MC1_67`) : la différence
  entre les deux appels est **VIDE** — le gisement est nul sur ce régime, donc non mordant *ici*.
  Fermer = un montage portant un effet de tuile dont l'`ActiveCondition` est fausse tout en restant
  dans la liste possédée (candidat : la zone NON MARCHABLE de `1148 DaemonicOrdnance`, #368).

  ⚠ **RE-MESURÉ le 2026-08-15 — le `BLOCAGE: porteur` était faux, et le volet PRÉDICTION est
  livré.** `blackForgefiend`, seul porteur non-npc de `1148`, est dans les **8 MoW spawnables** de
  `rl_duel build --list-pool` : ni injection catalogue ni greffe. Montage JOUÉ
  (`probe_425r1_daemonic_ordnance_inactif.py`, `MC1_67`/777, `--p-mow blackForgefiend` puis
  `act ability --caster <mow> --ability 1148 --to 3,4`) : l'ability part et pose `Fire` sur trois
  tuiles ; `tileMeta` défaut et `includeInactive` publient les MÊMES 8 tuiles à effet et les MÊMES
  noms ; **0** effet à `active == False`. Ce qui reste ouvert n'est donc pas un PORTEUR mais un
  ÉTAT — un effet de tuile dont l'`ActiveCondition` est fausse pendant qu'il reste possédé.
  ⚠ **Découverte de capteur** : le canal `tileMeta` DÉFAUT ne publie **pas** le champ `active`
  (12 effets sans la clé sur ce montage). `_tile_effect_names(only_active=True)` ne filtre donc
  RIEN sur ce canal ; le drapeau n'existe que sous `includeInactive`. L'absence est une absence de
  MESURE, jamais un `False` — et le port la traitait déjà ainsi.
  ⚠ **Volet PRÉDICTION livré** : `SceneTileState` lisait `Scene.tile_effects_by_pos` (ACTIF-ONLY)
  là où le natif n'a aucun gate. Le rayon de souffle, qui n'était « pas mesuré », l'est : ce champ
  a DEUX lecteurs de natures différentes — les bonus de dégât à magnitude POSITIONNELLE
  (`playbook/avalanche_of_muscle.py`, `entities/effects/base.py` via `att_ctx`, natif
  `HasTileStatusEffect`) et la feuille `TileEffects(10)`. La `Scene` porte désormais les DEUX
  tables (`tile_effects_owned_by_pos` NEUVE pour la seule feuille), donc **un seul lecteur change**
  et le rayon est nul par construction. Repli sur l'actif-only si la table possédée manque.
  Garde : `tests/engine/test_425r1_canal_possede_prediction_offline.py`.
* ~~**`#425-r2` — `readEffectsByTile` jette `removed` inconditionnellement**~~ — **FERMÉ
  (2026-08-05, `#425-r3`)**. Le natif retire **toujours** : `RemoveEffectOperation$$Execute` fait
  `List.Remove` sur `EffectsOwnedComponent.ActiveEffectIds` de l'entité `OwnerId` **avant** de
  poser `Removed`, dans le **même bloc** — la condition du filtre est donc **inatteignable** pour
  un id venu de cette liste, et il ne peut rien perdre. Seul écrivain de `Removed` sur le build
  (scan des 44,6 Mo de code : 40 sites à +0x5f, 21 fonctions, **1** sur un `EffectComponent`).
  ⚠ **Ne pas généraliser** : le filtre `removed` de `readRoundCapClock` est **LOAD-BEARING** —
  il itère les entités, pas une liste possédée, et le natif **ne détruit pas** l'entité retirée.
  Détail : `case-425-r3-filtre-removed-redondant.md`.
* Les résidus **#448-r1 §6** (les deux abilities restent NON PORTÉES : vecteur `On(0x28)`,
  `PerformAIMovementBehaviour$$Execute`, `OverrideMovementTargetOperation$$Execute`,
  `FullThrottle` 1134) sont **inchangés** — #425 ne portait rien, il tranchait un canal.

## 7. Reproduction

    python scripts/python/probe_425_tile_effect_channel.py --live --allies ultraTitus --foes tauCrisis
    python scripts/python/probe_425_tile_effect_channel.py --live --allies "" --foes tauCrisis   # le bras qui a trompe #448-r1
    python -m pytest scripts/python/tests/engine/runner/test_425_tile_effect_channel_live.py
