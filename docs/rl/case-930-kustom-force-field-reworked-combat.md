# #930 — `KustomForceFieldReworked` (`orksBigMek`) : la face COMBAT, et le porteur qui est dans sa propre aura

**Livré.** Le passif comptait **trois** faces, pas une. Les deux faces DÉCISION étaient déjà
portées (#271) ; la face COMBAT ne l'était pas et **se scinde en deux**, parce que le natif pose
DEUX effets qui partitionnent leurs cibles par faction.

## 1. Les faces, et laquelle manquait

| face | artefact natif | état |
|---|---|---|
| DÉCISION owner | `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedPlaybook$$GetAdjacentFriendUtility` | **portée** (#271), relue au décompilé, conforme |
| DÉCISION non-owner | `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` | **portée** (#271), relue, conforme |
| COMBAT-a (non-Orks) | `IdunBattle.Entities.Effects.Loki.KustomForceFieldEffectReworked` — `EffectType` 0x61e = 1566 | **LIVRÉE ici** |
| COMBAT-b (Orks) | `IdunBattle.Entities.Effects.Loki.KustomForceFieldEffect_Orks` — `EffectType` 0x61f = 1567 | **LIVRÉE ici** |

**Aucune face DEAD** : aucun des quatre corps ne rend `Fix64.op_Implicit(0)`.

`docs/rl/kit-coverage.md` annonçait `missing = 1` pour `orksBigMek`. Le compte des FACES était
donc sous-crédité **d'un facteur 2** sur la seule face manquante — quatrième occurrence du même
biais. Après livraison : `orksBigMek` est un **kit COMPLET** (85 → 86 kits complets, 43 → 42
items).

## 2. Ce que le natif dit, et qu'aucune table ne disait

### 2.1 `CreateBehaviour` — deux effets, joints par `op_BitwiseAnd`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.KustomForceFieldReworkedAbility$$CreateBehaviour` :

```
  AddDynamicStatModifierEffectToOwner( 0x61e = 1566, statType = 0x10 = FixedArmor, turns = null, isHidden = false )
& AddDynamicStatModifierEffectToOwner( 0x61f = 1567, statType = 0x10 = FixedArmor, turns = null, isHidden = false )
```

Le joint est `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` — **pas** `op_Addition`, celui de
`LionHelmAbility$$CreateBehaviour`. Deux classes DSL distinctes, même structure
`{+0x50 left, +0x58 right}` ; sans branche conditionnelle entre les deux, l'observable est le
même. Écrit pour que le prochain lecteur n'aille pas chercher un `op_Addition` absent.

`IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner` met
`Owner@DSLSelectors+0x30` en **source ET en cible** : les deux effets-entités vivent sur le Big
Mek, et c'est leur `CreateTargetSelector` qui projette. Confirmé live sur un runner frais — le Big
Mek liste `KustomForceFieldReworked` et `KustomForceFieldReworked_Orks`, ses alliés n'en listent
aucun.

**Trigger** : la classe ne déclare **que** `CreateBehaviour` (`frida/methods.tsv`) ; son parent est
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` et le trigger hérité est le corps dédupliqué
`On(0x21 = AbilityInit) & get_OwnerIsActor` — le même que LionHelm / AnvilShield /
PropheticSentinel. Canal : `ABILITY_INIT_OWNER_EFFECTS` + `EFFECT_CLASSES`, **jamais**
`ABILITY_TRIGGERS` ni `ABILITY_CLASSES`. L'absence dans la table ne prouvant rien, c'est la
**mesure live** qui tranche : les deux effets sont là avant toute action.

### 2.2 Le PORTEUR est DANS sa propre aura — le quirk central

```
KustomForceFieldEffectReworked$$CreateTargetSelector :
    Filter( Owner@+0x30 + AdjacentFriends(Owner, unique = 1, unitSelectionType = 3),
            !HasFaction(Subject@DSLSelectors+0x68, UnitFaction.Orks = 5, 3) )

KustomForceFieldEffect_Orks$$CreateTargetSelector : LE MEME corps, SANS le `op_LogicalNot`.
```

`IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends`, surcharge `(unit, unique, selectionType)`
— tranchée par le **TYPE** des arguments du call-site (le 3ᵉ est le littéral booléen `1`, pas un
`TargetsSelector*` ; la surcharge `(unit, unitTile, unique)` est donc exclue) :

```
Friends( unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType )
```

Le `op_Subtraction` **exclut** le porteur — puis le `IdunBattle.DSL.TargetsSelector$$op_Addition`
du `CreateTargetSelector` le **RE-AJOUTE**. Le Big Mek étant lui-même Ork, il porte donc sur lui
l'effet `_Orks`.

**Ni l'i2 ni le voisin de forme ne le disent** : l'i2 de la version non reworked écrit « All
friendly **adjacent** units », et `IconOfObstinacy` — qui porte le MÊME `AdjacentFriends(Owner,
unique, OnlyAliveAndTargetable)` — n'a **pas** l'`op_Addition`. Recopier l'un ou l'autre aurait
retiré au porteur son propre buff, silencieusement.

`Subject@DSLSelectors+0x68` = l'élément courant du filtre (`DSLSelectors$$Filter` délègue
littéralement à `FromTrigger(entities, trigger, 0)`) — même slot que
`entities/effects/loki/daemonic_patrons.py`.
`IdunBattle.Entities.Triggers.HasFactionTrigger$$ShouldTrigger` résout son sélecteur par **UNE**
unité puis appelle `IdunBattle.Entities.UnitExtensions$$HasFaction`, qui compare
`System.Enum.ToString(UnitFaction)` à une **chaîne** — d'où la comparaison par NOM côté port.

### 2.3 Deux variables distinctes, pas un facteur

```
KustomForceFieldEffectReworked$$GetDynamicStatModificationAmount :
    ConfigVar( TriggeredAbilityType.KustomForceFieldReworked = 0x60b,
               unit = EffectSource(Get(effect)), AbilityVariableType.extraArmor = 0x1b = 27 )
KustomForceFieldEffect_Orks$$GetDynamicStatModificationAmount :
    ... AbilityVariableType.extraArmor_2 = 0x9d = 157
```

`unit = EffectSource(...)` ⇒ la magnitude s'indexe sur l'`AbilityState` de la **SOURCE** (le Big
Mek), jamais sur celle du buffé. Les deux variables sont dans `variablesAffectedByRarityBonus`.

**Qualification d'enum** : `27` et `157` sont des `AbilityVariableType` — le type **déclaré** du
1ᵉʳ paramètre de la surcharge `DSLFormulas$$ConfigVar(abilityType, unit, variableType)`, celle dont
le 3ᵉ argument est un sélecteur d'unité (lu au call-site). L'ability 1547 n'a **aucune** constante.

**Le nom de classe ment, le décompilé non** : `KustomForceFieldEffect_Orks` ne porte pas
« Reworked », mais son `ConfigVar` lit `0x60b` = 1547 `KustomForceFieldReworked`. La version non
reworked (`KustomForceFieldAbility`, 0x44e = 1102) pose, elle, l'unique `KustomForceFieldEffect`
(0x448 = 1096) qui lit `ConfigVar(0x44e, ..., extraArmor)`. L'appartenance se lit au décompilé.

## 3. Ground truth live (`probe_930_kustom_force_field_reworked.py`)

Runner `MC1_67` / seed 777, `statModSources` statType 16, `orksBigMek` (rank 17 → ability level
50, multiplier 180) + 3 alliés + 1 ennemi :

```
seed        u79 orksBigMek     Orks           (1,0)  fixedArmor +1197  source = effet 98
            u81 orksNob        Orks           (0,0)  fixedArmor +1197  source = effet 98
            u83 ultraApothecary Ultramarines  (1,1)  fixedArmor  +797  source = effet 97
            u85 astraBullgryn  AstraMilitarum (0,1)  fixedArmor  ABSENT
            u77 necroWarden    ENNEMI         (6,8)  fixedArmor  ABSENT
far_in      u85 deplace en (2,0)  ->  fixedArmor  +797  source = effet 97
other_out   u83 deplace en (1,3)  ->  fixedArmor  ABSENT
```

```
extraArmor[50]   = 443 x 1.8 =  797   (effet 1566, cibles NON-Orks)
extraArmor_2[50] = 665 x 1.8 = 1197   (effet 1567, cibles Orks — porteur COMPRIS)
```

Les DEUX points de câblage du driver d'aura (`snapshot.load_state` au seed,
`MoveUnitOperation.execute` au mouvement) étaient **déjà génériques** : le port n'a eu qu'à porter
l'interface `aura_stat_modification_*`.

## 4. Le foyer partagé, et ce que j'y ai déplacé

`engine/entities/effects/aura_selectors.py` est le FOYER déclaré des primitives de sélecteur
d'aura. J'y ai **ajouté** `adjacent_friends_including_owner` (le nœud de tête, commun aux deux
`CreateTargetSelector`) et **hissé** `faction_of`, qui vivait en privé dans
`loki/dark_angels_passives.py` — un second porteur du même accesseur aurait été un fork.
L'appel y reste en **forme B** (`ASel.faction_of`), pour ne pas geler le binding.

**Rayon de souffle mesuré** : 17 fichiers sources et 3 fichiers de test importent
`aura_selectors` ; 9 fichiers citent `dark_angels_passives`. Régression rejouée sur les quatre
consommateurs live du foyer (LionHelm block + overwatch, FearedInterrogator, PathOfCommand crit) —
cf. §6.

**Résidu hérité, non touché** : l'adjacence reste `hexgeo.distance == 1`, alors que le voisinage
natif de `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` porte en plus un gate
`|elev(a) − elev(b)| < 2`. Résidu déjà nommé (#271), commun à toute la famille ; le corriger dans
mon seul module aurait été un fork.

## 5. Mutants — 14, tous mordants

**Offline** (`test_930_kustom_force_field_reworked_offline.py`, 20 tests, 2 s) :

| mutant | verdict |
|---|---|
| filtre de faction inversé | MORD (7 rouges) |
| variables swappées | MORD (6) |
| le porteur n'est plus dans son aura (`op_Addition` perdu) | MORD (4) |
| rayon élargi à 2 | MORD (3) |
| stat écrite = BlockDamage | MORD (5) |
| multiplier de rareté ignoré | MORD (5) |
| faction inconnue rabattue sur « non-Ork » | MORD (1) |
| volet `Friends` perdu | MORD (1) |
| magnitude non indexée sur la source | MORD (6) |

**Live** (`test_930_kustom_force_field_reworked_live.py`, 5 tests, ~25 s) : porteur hors aura,
filtre inversé, multiplier ignoré, aucun revert au mouvement, rayon élargi — **5/5 MORDENT**.

**Deux faux verts trouvés et réparés en cours de route** — les deux méritent d'être connus :

1. **Le mutant « rayon élargi à 2 » était INERTE offline** : le montage n'avait *aucune* unité à
   distance exactement 2 (une à 1, une à 1, une à 6). Un montage dont toutes les unités sont à
   distance 1 ou ≥ 3 ne peut structurellement pas voir le rayon. Corrigé en **peuplant le ring-2**
   (`orksKillaKan` à distance 2), et le montage assertionne désormais **sa propre** distribution de
   distances.
2. **Le mutant « le porteur n'est plus dans son aura » était INERTE live** : le test comparait
   (a) la stat TOTALE offline vs live et (b) `statModSources` **live contre lui-même**. Or retirer
   le porteur du sélecteur laisse le total INCHANGÉ au seed — la part reste dans le résidu opaque
   `CAPTURED_SOURCE`, que `attribute_aura_stat_modifiers` n'a alors rien à ré-attribuer. Le test
   confronte maintenant la **contribution de la famille AURA côté port**
   (`UnitStats.components[stat].modification.per_source`, clés `("aura_statmod", …)`) à
   `statModSources.bySource` côté natif. C'est le cran du dessous : un total juste ne prouve pas
   que le port a **attribué** quoi que ce soit.

## 6. Régression du foyer partagé, et un ROUGE de `master`

| fichier | verdict |
|---|---|
| `test_lion_helm_overwatch_aura_live.py` | 3 passed |
| `test_feared_interrogator_live.py` | 6 passed |
| `test_path_of_command_crit_aura_live.py` | 5 passed |
| `test_lion_helm_block_aura_live.py` | **1 failed, 1 passed** |

⚠ **Le rouge est ANTÉRIEUR à cette tranche.** Attribué sur un arbre témoin
(`git worktree add --detach <tmp> be6245f6`) : il tombe **à l'identique** sur `origin/master`, avec
le même message. Cause **mesurée** : le test assertionne `seed[azrael] == (0, 0)` sur la stat
**TOTALE** de block, alors que le régime **BiS items** par défaut (#419-r5/-r6) donne à Azrael
`(36, 2349)` de base. Contre-épreuve : `TACTICUS_BIS_ITEMS=0` → **2 passed** sur le même témoin.

C'est la cinquième victime connue de cette bascule. Le remède est celui appliqué ici : assertionner
la **contribution par entité-effet** (`statModSources`) et non la stat totale. Résidu **#930-r1**.

## 7. Ce qui n'est PAS couvert

- **L'élévation dans l'adjacence** — résidu #271 hérité, commun à toute la famille de sélecteurs
  d'aura (`surrounding_friends`, `_adjacent_friends`, et désormais
  `adjacent_friends_including_owner`).
- **Le volet `Targetable` du `unitSelectionType = 3`** est porté (`is_targetable`, domaine
  `UNTARGETABLE_EFFECT_TYPES`) mais **non confronté live pour ce passif** : aucune unité en Deep
  Strike dans le montage. Le mécanisme est celui déjà confronté par LionHelm (`darkaTerminator` en
  teleport-in ne reçoit rien).
- **Le volet `alive`/`hp > 0`** du nœud de tête n'est pas confronté live (aucune mort dans le
  montage) ; il est porté par mirror du `Units(..., selectionType)` natif.
- **La version NON reworked** (`KustomForceField`, ability 1102, effet 1096) reste hors périmètre :
  son `CreateTargetSelector` est absent de `methods.tsv` (ICF), donc son sélecteur n'est pas établi.
  `KustomForceFieldUtility` (face DÉCISION de 1102) est, elle, déjà portée
  (`engine/utilities/tile.py`).
- **`op_BitwiseAnd` vs `op_Addition`** : les deux classes DSL ne sont pas distinguées par le port
  (les deux behaviours sont posés inconditionnellement). Aucune différence observable ici ; à
  rouvrir si un `CreateBehaviour` conditionne un côté à l'autre.
