# case-366-r1 — `1216 PsychicStalk_VisualEffect` : un prédicat RÉEL, un sélecteur RÉEL, et zéro canal de gameplay

**Question, binaire.** « Visual » dans le nom ne prouve rien. Cet effet a-t-il, oui ou non, une
sortie de gameplay — et le seul prédicat qu'il porte rend-il, côté port, exactement ce que rend le
natif ?

**Réponse : NON pour la sortie de gameplay, OUI pour le prédicat.** La contribution nulle est
**MESURÉE** (rejeu du même coup avec et sans l'effet, gates du kit OUVERTS, plus un témoin de
sensibilité qui bouge), pas déduite d'un silence. Porteur `thousAhriman`, HERO **au pool** ; voie
directe, ni greffe npc, ni injection catalogue, ni relique.

## 1. La classe native n'a AUCUN slot de sortie — c'est une lecture, pas une absence d'observable

`IdunBattle.Entities.Effects.Loki.PsychicStalk_VisualEffectEffect` surcharge **exactement quatre**
méthodes :

| méthode native | ce qu'elle est |
|---|---|
| `PsychicStalk_VisualEffectEffect$$.ctor` | `BaseEffect..ctor(this, <AbilityOrEffect>, hasAutomaticActivation)` |
| `PsychicStalk_VisualEffectEffect$$CreateActiveCondition` | prédicat — **porté** |
| `PsychicStalk_VisualEffectEffect$$CreateTargetSelector` | sélecteur d'entités — **porté** |
| `PsychicStalk_VisualEffectEffect$$GetRefreshTriggers` | `int[3]` — **non portable** (§7) |

Aucun `CreateEffectDamage*`, aucun `CreateDamageModifier`, aucun `GetStatModification*`, aucun
`ApplyModification`, aucun `CreateTrigger`, aucun `CreateAdditionalHits`, aucun
`GetArmorPenetration`. Ses deux frères, eux, en ont un chacun (`1215` → `ForPercentIncrease`
défenseur, `1435` → `ForAddition` attaquant).

⚠ **L'argument d'absence est ici LÉGITIME, contrairement au cas général** (`reference_symbol_table_absence_proves_nothing`) : la
déduplication IL2CPP n'efface que les corps **triviaux**, et un override trivial d'un slot de sortie
est sémantiquement identique au défaut de `BaseEffect`. Un override non trivial, lui, aurait son
propre corps et apparaîtrait.

⚠ **Et l'index de recherche de ghidra ne prouve, lui, RIEN** : une recherche littérale de `0x4c0` ne
ramène même pas `PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour`, qui le contient pourtant
(idem pour `0x59b`). Mesuré ici — à ne pas re-payer. Le seul balayage exhaustif réellement
disponible est la lecture **intégrale d'une fonction** ; c'est ce qui a été fait sur le `.cctor`
ci-dessous.

## 2. Les DEUX consommateurs sont NOMMÉS, et tous deux sont de la PRÉSENTATION

**(a) VFX + SFX.** `IdunBattle.View.AbilityConfigs.Loki.PsychicStalkEffectVisual.u003CReceiveEffectInternalu003Ed__2$$MoveNext`
appelle `IdunBattle.View.AbilityConfigs.AbilityVisualsUtils.InstantiateEffects$$InstantiateEffectAt`
puis `...AbilityVisualsUtils.SoundEffects$$PlaySfx`. Namespace `IdunBattle.View`.

**(b) ICÔNE DE STATUT.** `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$.cctor`
inscrit `0x4c0` dans le dictionnaire `<statics>+0x10` (EffectType → catégorie d'affichage) avec la
valeur **2**. Les accesseurs qui lisent CE dictionnaire donnent la lecture exacte :

| accesseur `StaticBattleRules.Effect$$…` | teste | `1216` |
|---|---|---|
| `IsUnitEffectHiddenFromGenericBuff` | `== 0` ou `== 3` | non |
| `IsUnitEffectShownAsGenericBuff` | `== 1` | non |
| **`IsUnitEffectShownAsGenericDebuff`** | **`== 2`** | **OUI** |
| `HasUniqueIcon` | `== 3` | non |
| `IsInvisible` | `== 5` | **non** — il s'AFFICHE |

Donc `1216` n'est pas « invisible » : c'est un **marqueur de statut affiché en debuff générique** sur
les cibles de son sélecteur. Son output est de l'UI, pas de la mécanique.

### Et la face DÉCISION est structurellement hors de portée

Le `.cctor` a été lu **intégralement** : `0x4c0` n'y apparaît **qu'une seule fois**, dans ce
dictionnaire d'affichage. Il n'est notamment **pas** dans le `HashSet` `<statics>+8` que lit
`StaticBattleRules.Effect$$ShouldRefreshDuringSimulation`. Or
`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` commence par :

    if (state.<IsSimulation>) { if (!ShouldRefreshDuringSimulation(ec.EffectType)) return; }

⇒ pendant une **simulation** — c'est-à-dire toute la face DÉCISION — le natif ne rafraîchit
**jamais** `1216` : ni sa condition d'activité, ni ses cibles.

## 3. Ce que dit `RefreshEffect`, et qui fixe le sens de `Owner`

Toujours dans `RefreshEffectsOperation$$RefreshEffect` :

    owner = state.GetEntity( EffectComponent.OwnerId @+0x14 )
    <AbilityEntities>+0x08 = owner ; +0x18 = owner ; +0x50 = activePlayer ; +0x58 = effectEntity
    if (ShouldBeActive(...))  { EffectComponent+0x5c = 1 ; targets = effect.<slot 0xd>(entities)
                                UpdateEffectTargets(targets, ...) }
    else                        DeactivateEffect(...)

`Owner@DSLSelectors+0x30` est donc le **PORTEUR** de l'effet (Ahriman), pas sa cible — et le
`unit_state` que le port passe à `is_active` est justement celui de l'unité qui porte l'effet :
même entité, aucune conversion.

## 4. Les deux méthodes portées, mirror 1:1

**`CreateActiveCondition`** :

    op_LogicalNot( DSLTriggers.IsDead( Owner@DSLSelectors+0x30 ) )

`IdunBattleLogic.Entities.DSLTriggers$$IsDead` est littéralement
`op_LogicalNot(DSLTriggers.IsAlive(u))`, et `IdunBattle.Entities.Conditions.IsAliveAbilityTrigger$$ShouldTrigger`
appelle `IdunBattle.Entities.UnitExtensions$$IsAlive` → `HealthComponent$$IsAlive` = `hp >= 1`.
Le double `NOT` se simplifie en **`IsAlive(Owner)`**, dont le port avait déjà le mirror exact
(`runner/components.py::unit_is_alive`). `hp` inconnu → vivant, comme le natif.

**`CreateTargetSelector`** :

    Units( EntitiesWithAnyEffect( Tiles( Enemies(of = Owner@0x30, entities = AllUnits@0x20,
                                                 onlyAlive = 1) ),
                                  Fire = 5, effectTarget = 6 ), unique = 1, selectionType = 3 )

= « les unités **ennemies vivantes** du porteur dont la **main tile** porte `Fire` ». Trois lectures
qui ne se devinent pas :

* les surcharges de `Enemies` et de `Units` sont tranchées par l'**adresse du `call`**, pas par le
  nom (`list_xrefs` sur les deux candidates) : `Enemies(this, of, entities, onlyAlive)`, qui
  ré-expédie sur `selectionType = onlyAlive + 2 = 3`, et `Units(this, entities, unique, selectionType)` ;
* `Tiles` = `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` → la MAIN TILE, pas l'empreinte —
  **même nœud** que `APsychicStalkEffect$$GetTargetIsOnFireTileCondition`, d'où la lecture par
  `t_pos` seule ;
* le `6` est `effectTarget`, **pas** un second `EffectType` (la surcharge à 4 arguments emballe
  elle-même le scalaire `5` dans un `int[1]`) — même piège que sur `1215`.

`DSLSelectors+0x20` est le slot `AllUnits` (alloué par `DSLSelectors$$InitializeShared` à côté de
`+0x18 = AllTilesSelector`), c'est-à-dire l'`AllAliveMachinesSelector` que le port mirrore déjà.

## 5. Pourquoi l'inscrire au registre plutôt que le laisser sur `BaseEffect`

Même motif que `WireweaveNet_CounterAttack` : **nommer la classe native**, et porter la seule chose
qui soit une LECTURE plutôt qu'un défaut. `BaseEffect.is_active` rend `True` **inconditionnellement**
— c'est une valeur par défaut, pas une lecture du natif, et le discriminant de
`runner/operations/refresh_effects.py` repose exactement là-dessus. En portant la condition, `1216`
entre dans la branche « re-évaluer et écrire le flag » : **15** classes sur les **148** du registre
(re-dérivé le 2026-08-01 ; le commentaire du driver en annonçait encore 13 alors qu'il en valait 14
— le compte est à re-dériver, jamais à citer).

## 6. Mesures live — 2 couples (board, seed), toutes concordantes

Montage : `probe_366_r1_psychic_stalk_visual.py` (`thousAhriman` + `astraPrimarisPsy` vs
`necroWarden` **et `necroDestroyer`**, pilotage des deux camps, feu posé par le natif, rejeu offline
sur le MÊME flux MT). `--crit 0,0 --crit-target 0,0 --block-target 0,0 --block-player 0,0` et
`PassiveAbilities=[]` sur l'allié et les deux cibles : une seule variable bouge.

| | `MC1_67` / 31337 | `C4_09` / 4242 |
|---|---|---|
| E1 — `1216` posé sur Ahriman, `IsActive @+0x5c` | présent, **`active: true`** | présent, **`active: true`** |
| kit complet `1215`/`1216`/`1435` sur le porteur | oui | oui |
| hex en feu (posé par le natif) | `(6,8)` | `(5,9)` |
| ennemi SUR le feu / ennemi HORS feu | `77` / **`79`** | `84` / **`86`** |
| E2 — sélecteur PORTÉ / ORACLE live | `[77]` / `[77]` | `[84]` / `[84]` |
| E3 — coup mesuré **live** / **port** | `[3589]` / `[3589]` | `[3411]` / `[3411]` |
| E3 — port **sans `1216`** | **`[3589]`** (identique) | **`[3411]`** (identique) |
| E3 — port **sans `1215`** (témoin de sensibilité) | `[2582]` | `[3288]` |
| E3 — étages `att_*` / `def_*` avec vs sans `1216` | **identiques** | **identiques** |
| E5 — `is_active` nominal / `hp = 0` | `True` / **`False`** | `True` / **`False`** |
| E5 — défaut `BaseEffect.is_active` à `hp = 0` | `True` (donc ça DISCRIMINE) | `True` |
| E5 — flag après `refresh_stat_modifier_effects` | `True` / **`False`** | `True` / **`False`** |

**Deux points de montage se sont révélés indispensables, et les deux ont d'abord ÉCHOUÉ :**

1. **L'ordre des tours.** Le `Fire` posé par `PsychicStalk_ApplyFireTile` a une **durée** : placer
   l'allié APRÈS le tir d'Ahriman consomme des fins de tour qui l'ÉTEIGNENT. Premier run :
   `fire_tiles = []`, cible en `(6,8)`. On place donc les deux unités **d'abord**, puis, dans un
   seul tour joueur : Ahriman tire → capture → l'allié frappe.
2. **Le second ennemi.** Le tir d'Ahriman **splashe** le feu (mesuré : `(6,7)` ET `(6,8)`), et les
   deux ennemis s'y sont retrouvés — l'ensemble « ennemis » et l'ensemble « ennemis sur le feu »
   coïncidaient, donc un port ayant OUBLIÉ le gate `Fire` serait passé. On **déplace** le second
   ennemi à distance 4 (doctrine : on fabrique la configuration, on ne la subit pas), et le probe
   **ASSERTE** qu'un ennemi hors feu existe — un montage non discriminant échoue, il ne rend pas un
   vert.

### La branche FAUSSE de la condition est LIVE-INATTEIGNABLE — et c'est mesuré

Bras `--kill-carrier` (`MC1_67`/31337) : le foe tue Ahriman →
`observeBattle.isDead = true`, `hp = 0`, `decisionView.alive = false`, et la liste d'effets du
porteur est **VIDE**. Le natif ne laisse pas `1216` inactif : il **retire les trois effets du kit**.
`IsAlive(Owner) == False` n'existe donc dans aucun état établi, et le port lit la même chose sur la
même capture (aucune instance non plus → parité). La condition portée n'est observable que dans le
régime **simulé** du contrefactuel E5.

## 7. Mutations adversariales — chacune vérifiée MORDANTE avant d'être interprétée

`git diff --stat` non vide exigé avant chaque interprétation (un patch multi-lignes qui ne matche
pas laisse le code intact et rend VERT) ; restauration par `git checkout -- <chemin>` nommé.

| mutation | résultat | ce qui rougit |
|---|---|---|
| **M1** entrée `EFFECT_CLASSES` retirée | ROUGE (4) | `1216` routé sur `BaseEffect` + `condition_ported` faux |
| **M2** `is_active` inversé (`hp >= 1` → `hp < 1`) | ROUGE (2) | E5 nominal : le port éteint un porteur vivant |
| **M3** gate `Fire` du sélecteur retiré | ROUGE (4) | l'ennemi HORS feu entre dans l'ensemble + `cov_no_fire` |
| **M4** gate `AreEnemies` retiré | ROUGE (2) | **seul `cov_owner_team_swapped` le voit** (§ ci-dessous) |
| **M5** gate `onlyAlive` retiré | ROUGE (2) | `cov_all_dead` non vide |
| **M6** canal de dégât INVENTÉ (hérite de `1215`) | ROUGE (2) | retirer `1216` change le dégât + les étages |

⚠ **M4 est la leçon de méthode.** Sur cette géométrie, l'oracle live seul **ne l'aurait pas
attrapée** : aucun allié ne se tient sur un hex en feu, donc retirer le gate d'équipe ne change pas
l'ensemble désigné. Ce sont les **contrefactuels par conjoint** — chaque nœud neutralisé SEUL sur
l'état live réel — qui rougissent. Un oracle global ne remplace pas la décomposition par étage.

## 8. Ce qui n'est PAS couvert

* **La sortie MATÉRIALISÉE du sélecteur n'est lue par AUCUN capteur.** Côté natif elle part dans
  `RefreshEffectsOperation$$UpdateEffectTargets` → `AddTargetsToEffect` →
  `IdunBattle.Entities.Components.EffectComponent$$AddTargetId` : la relation vit sur
  l'**entité-effet** (le champ que lit `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffectOfType`,
  `EffectComponent+0x48`), **pas** dans l'`EffectsOwnedComponent.ActiveEffectIds` de la cible — or
  c'est ce dernier, et lui seul, que publie `frida/hooks/game/effects.ts::readEffectsByUnit`. Le
  mirror est donc confronté sur ses **entrées** (positions + effets de tuile de l'état live), pas sur
  sa sortie native. **Point d'ancrage à hooker** pour lever le résidu : la liste de cibles de
  l'`EffectComponent` (`AddTargetsToEffect` / `EffectComponent$$AddTargetId`). Un hook y donnerait
  aussi, gratuitement, l'oracle de toutes les auras à `CreateTargetSelector`.
* **`GetRefreshTriggers` n'est pas porté** — le port n'a ni `RefreshEffectTrigger` ni
  `ShouldRefreshForTrigger`. Lecture faite : `BaseEffect$$ShouldRefreshForTrigger` rend VRAI pour
  tout trigger `in {0,1,2}`, et sinon VRAI ssi le trigger appartient au tableau (tableau vide/absent
  → VRAI). Une classe qui DÉCLARE `GetRefreshTriggers` **restreint** donc ses fenêtres de refresh ;
  elles sont **12** à le faire. Les 3 valeurs du tableau de `1216` vivent dans un blob
  `RuntimeHelpers.InitializeArray` non résolu statiquement — **non lues**. Résidu commun avec
  case-366-r1b §7bis.
* **Le prédicat porté n'a AUCUN consommateur de gameplay**, par construction : c'est le constat
  central. Il est exercé par les gardes, pas par le moteur.
* **La face DÉCISION n'est pas confrontée** — et le §2 montre qu'elle n'a pas à l'être : le natif ne
  rafraîchit pas `1216` en simulation.
* **`PsychicStalk_ApplyFireTile` (la pose du feu) n'est toujours pas portée** : l'état offline la
  reçoit par le seed `snapshot._load_tile_effects`. Résidu déjà nommé au backlog.
* **Aucune mesure de l'EXPIRATION du feu** ni du comportement d'un summon/MoW comme cible du
  sélecteur (les candidats mesurés sont tous des unités).

## 9. Artefacts

| quoi | où |
|---|---|
| classe d'effet | `scripts/python/engine/entities/effects/loki/extra_damage_aura.py` (`PsychicStalkVisualEffect`) |
| registre | `scripts/python/engine/entities/effects/factory.py` + `effects/loki/__init__.py` |
| driver du flag | `scripts/python/engine/runner/operations/refresh_effects.py` (compte re-dérivé) |
| montage live | `scripts/python/probe_366_r1_psychic_stalk_visual.py` |
| gardes | `scripts/python/tests/engine/runner/test_psychic_stalk_visual_effect_live.py` (11) |
| frères du kit | `case-366-r1-psychic-stalk-extra-attack-damage.md`, `case-366-r1-psychic-stalk-friendly-chaos.md` |
