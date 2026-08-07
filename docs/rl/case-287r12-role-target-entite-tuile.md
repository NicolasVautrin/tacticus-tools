# #287-r12 — le rôle `target` d'une entité TUILE : un gisement **armé et muet**, dont le rayon réel était **2** et non **5**

`entities_from_state` (`engine/runner/abilities/behaviours/context.py`) construit l'`AbilityEntities`
que lisent tous les arbres DSL du runner. Il matérialisait un **caster** minimal quand `caster_id`
désigne une tuile — sans quoi toute feuille lisant `entities.caster` devenait un no-op silencieux —
mais rendait **`None`** sur le rôle `target`, et `Target()` avec lui.

Trois parades locales avaient poussé autour de ce trou (`tyranids.AlphaWarriorAbility` #287-r8,
`targeting._dynamic_rule_excruciating_frequencies` #287-r11-r1, puis la fonction spécialisée
`entities_with_tile_target` #512). Le foyer les absorbe ; il n'en reste **aucune**.

## 1. Le sens natif — lu, pas supposé

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` ne passe **pas** son paramètre
`target` à la suite de la chaîne. Il le transforme, par **deux sauts de slot** :

    finalTarget = IActiveAbility.GetActualTarget(ability, caster, target)        # slot IActiveAbility 16
      -> IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget
      -> IdunBattle.Core.Services.TargetingQuery$$GetActualTarget                # slot ITargetingQuery 6

et le corps de ce dernier :

    if (!options.isSelfCasting) {
        if (options.rules & 0x40)             return EntityExtensions.GetMainTile(target, state);   // TargetIsTile
        if (options.rules & (1<<44)) { ... }                                                        // TargetIsMachine
        if (options.rules & (1<<46)) { ... }                                                        // TargetIsActor
        return UnitExtensions.GetUnit(target, state);
    }
    return caster;

`finalTarget` part en 5ᵉ argument de `IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities`,
qui écrit `AbilityEntities+0x10 = finalTarget` — offset **lu** dans
`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (32 arguments : `+0x00 actor · +0x08 caster ·
+0x10 target · +0x18 owner · +0x20 activeTarget · +0x30 targetTile · +0x38 targetTiles ·
+0x40 casterTile · +0x48 casterTiles`).

⇒ **Pour une ability portant `TargetIsTile`, le rôle `target` du natif est TOUJOURS l'entité-TUILE** :
ni `None`, ni l'unité occupante. Le ciblage (UI/IA) passe, lui, par une fonction **distincte**,
`IdunBattle.Core.Services.TargetingQuery$$GetActualTargetForTargeting` (même corps, sans le
court-circuit self-cast) — la transformation appartient donc au pipeline d'**exécution**.

## 2. Le rayon de souffle : **5 annoncés, 2 effectifs**

La ligne de backlog prescrivait de ne pas élargir « pendant qu'on y est » parce que **5** abilities
TILE-TARGET passaient leur `target_id` au foyer. Le critère « passe son `target_id` » n'est pas le bon :
ce qui change avec l'élargissement, c'est ce qu'un arbre **LIT**.

`probe_287r12_role_target_tuile.py --rayon` balaye les **129** entrées d'`ABILITY_CLASSES`,
**23** portent `TargetIsTile`, et le croisement avec « l'arbre lit l'entité-tuile matérialisée »
donne le **RAYON EFFECTIF = 2** : `1017 FragBomb` et `1018 ValkyrieStrike`.

⚠ **Le critère a menti deux fois avant de tenir**, et les deux erreurs sont instructives :

| critère | rend | pourquoi il ment |
|---|---|---|
| `Target()` rendu **NUL** | **0** après élargissement | après le fix `ctx.target` n'est plus jamais nul — le compte s'effondre et se lit « personne n'est touché ». Inutilisable APRÈS. |
| `Target()` **ÉVALUÉ** | **81** | compte les **sous-contextes** : `1096 MasterOfTheTutelaries` y entre alors qu'elle appelle `entities_from_state(state, caster_id)` **sans `target_id`** (le nœud est évalué dans l'attaque du summon à l'apparition). |
| `Target()` rend **l'entité-tuile de CE cast** | **2** | exactement ce que l'élargissement met, et rien d'autre. Une entité-tuile se reconnaît à `visualId is None`. |

## 3. Ce que chacun des cinq fait de son `Target()` — et comment c'est mesuré

Mesure : `probe_287r12_role_target_tuile.py` joue chaque `execute_behaviour` sur un substrat offline
identique, dans **deux régimes**, en instrumentant `Target.select` :

* **régime U** — `target_id` = id d'**UNITÉ** : ce que passent tous les tests live actuels
  (`_ringed_cast.cast_and_confront` envoie `targetId: <unité>`, et le natif l'accepte puisqu'il
  transforme lui-même la cible) ;
* **régime T** — `target_id` = id de **TUILE** : ce que produit la face DÉCISION portée
  (`probe_302_tile_target_route`, `probe_343_tile_target_emission` : `abilityTargets` rend
  `kind: "tile"`, l'action porte le `tileEntityId`).

| id | `Target()` en régime T, AVANT | ce que l'ability en faisait | dans le rayon ? |
|---|---|---|---|
| `1017` FragBomb | évalué **3×**, **3 NULS** | `Units(Target)` et `AdjacentUnits(Target) - Caster` vides → **0 coup**, aucune erreur | **OUI** |
| `1018` ValkyrieStrike | évalué **1×**, **1 NUL** | `AddBondEffect(1022, …, Target(), …)` → l'effet **n'est PAS posé** | **OUI** |
| `1026` BasiliskBarrage | **0** évaluation | l'arbre ne lit pas `Target()` — mais le **collapse impératif** `basilisk_shell_tiles` résolvait la tuile par un `get_entity(target_id)` → `[]` → **0 obus** | non (autre cause, réparée) |
| `1148` DaemonicOrdnance | **0** évaluation | normalisation locale `FixedTileIds` — régimes U et T déjà identiques | non |
| `1169` PlagueburstMortar | **0** évaluation | normalisation locale `plagueburst_target_tile` — idem | non |

## 4. L'élargissement

`_tile_entity(state, eid)` fabrique l'entité-tuile minimale, et **les deux rôles** (`caster`, `target`)
y passent — une seule forme, parce qu'il n'y en a qu'une côté natif. Le rôle `target` reste `None`
pour un `target_id` qui n'est ni une unité ni une tuile du board (substrat non mesuré, aucune tuile
inventée), et l'élargissement est **inerte** dès que `target_id` désigne une unité : la boucle sur
`state.entities` sert le rôle avant lui. C'est ce qui le rend sans risque pour les **127** autres
entrées du registre.

**Foyer secondaire** : `main_tile_id(state, entity_id)`, mirror de
`IdunBattle.Entities.EntityExtensions$$GetMainTileId` en domaine *id de tuile*, partagé par les deux
collapses impératifs (`astramilitarum.basilisk_shell_tiles`, `deathguard.plagueburst_target_tile`).

⚠ **Son ORDRE est lu, et ce n'est pas celui qu'on écrit d'instinct** : le natif essaie d'abord le
composant de **PIED** (`TryGetComponent` → `return *(uint*)(comp + 0x14)`), puis l'unité multi-pieds
(l'`OrderedSet` @+0x78, élément 0, **récursion**), et ne teste `EntityExtensions$$IsTile` qu'**en
dernier**, en repli. `plagueburst_target_tile` testait la tuile **d'abord** — l'ordre inverse. Ce
n'est pas académique : les deux espaces d'ids du port (unités de `state.entities`, tuiles de
`state.board`) se **chevauchent** (résidu nommé dans `operations/active_ability.py`), donc l'ordre
décide de ce que rend un id ambigu.

**Corollaire de ventilation** : `1017` rendait `main_attack: None` en régime T alors que ses **coups
étaient déjà exacts** — son diagnostic comparait les cibles émises à `target_id`, qui est une TUILE.
La cible principale se résout par le sélecteur natif du 1ᵉʳ groupe, `Units(Target@0x178, 1, 1)`.

## 5. Les confrontations LIVE (`probe_287r12_confront_live.py`, `MC1_67`, seed 777)

Protocole identique pour les trois : cast **avec `targetId` = l'id d'entité-TUILE**, état figé,
même MT, et un **TÉMOIN** = le port d'avant (foyer neutralisé) — sans lui, un accord ne distingue pas
« l'élargissement porte le résultat » de « il vient d'ailleurs ».

| id | natif | port APRÈS | port AVANT (témoin) |
|---|---|---|---|
| `1018` | `1022` inscrit sur la **TUILE 74** (`tileMeta.tiles[].effects`) ; `decisionView.units[].effects` **inchangé** | `[(74, [1022])]` — **accord** | `[]` |
| `1017` | 12 coups : `(77,2028) (77,290) (77,249) (77,313) (77,314) (77,307) (79,160) (79,180) (79,150) (81,175) (81,208) (81,176)` | **identique, coup par coup** | `[]` |
| `1026` | 6 coups : `(77,505) (77,459) (85,452) (85,475) (79,454) (79,452)` | **identique**, tuiles `[63,36,45,44,52]` | `tiles=[]`, `coups=[]` |

⚠ **Une erreur de MESURE a d'abord fait conclure l'inverse** : la première passe lisait
`effects[].type` là où le canal publie `effectType`, et `tileMeta.tiles[]` n'a **pas** de champ `id`
(les entrées sont indexées par `(col,row)`). Résultat : les deux canaux rendaient un dict **vide**,
donc « le natif n'inscrit **AUCUN** effet » — la conclusion exactement inverse de la vérité. C'est
le dump brut des évènements du cast (`{"Effect_Id": 100}`) qui a montré qu'un effet **avait** été posé.

## 6. La garde

`tests/engine/runner/test_287r12_role_target_tuile_offline.py`, **9 étages** : matérialisation ;
forme du dict (rien d'inventé) ; **inertie** sur une cible unité et sur un id inconnu ; le **rayon
effectif comme CLIQUET** (une ability qui entre dans le rayon doit avoir été confrontée) ; l'égalité
des deux régimes pour `1017` ; le porteur **TUILE** de `1022` (valeur mesurée live) ; l'ordre natif de
`main_tile_id` sur un id **volontairement ambigu** ; `1026` non muette ; et un balayage **statique**
qui interdit qu'une copie du dict-tuile minimal repousse hors du foyer.

Vue rouge sur l'arbre témoin (`git archive` du commit d'avant la tranche) : **8 failed / 1 passed** —
le seul vert est l'étage d'**inertie**, l'invariant que la tranche préserve. Le rouge de l'étage
statique nomme la copie : `runner/abilities/tyranids.py:434`.

⚠ L'import de `main_tile_id` est **local à son test**, et la raison n'est pas un cycle : c'est le seul
symbole du fichier qui n'existe pas dans l'arbre d'avant. Au niveau module, il ferait échouer la
**collecte** — et un fichier non collecté ne montre **aucun** de ses autres étages.

## 7. Ce qui n'est PAS couvert

* ~~**`GetActualTarget` n'est pas porté — résidu `#287-r14`.**~~ **FERMÉ** — porté par #287-r14
  (`case-287r14-get-actual-target.md`) : `actual_target` (foyer, `behaviours/context.py`) +
  `ActiveAbility.get_actual_target` (`base.py`), branchés dans `AbilityHandler` au rang natif ET en
  tête des 23 `execute_behaviour` tile-target. Confronté LIVE (`MC1_67`, seed 777) : cast de `1018`
  avec un `targetId` d'**UNITÉ** → le natif pose `1022` sur la **TUILE 74**, le port aussi, le témoin
  d'avant sur l'**unité 77**. `test_valkyrie_strike_migration_live.py` grave toujours le régime U —
  et c'est correct : il charge `load_state` **sans board**, donc la résolution y est inerte ; il
  reste juste **en tant que test de migration**. Pour `1017`, les deux régimes étaient déjà
  observationnellement équivalents (mesuré, étage 4 de la garde). Résidus ouverts : `#287-r14-r1`
  (la voie `execute_behaviour` ne résout que les tile-target) et `#287-r14-r2`
  (`GetMachinePlatformContent`).
* **L'espace d'ids partagé tuile/entité** reste un résidu (déjà nommé dans
  `operations/active_ability.py`) : un id ambigu est tranché par l'ordre de `main_tile_id`, qui est
  désormais celui du natif — ce n'est pas une séparation des espaces.
* **La face DÉCISION de `1017` et `1026` reste non routée** en domaine tuile (résidu
  `#419-r1-tr14-r5-r2-r1-r1-r1-r1`) : leur générateur `Comparable` énumère des **unités** alors que le
  natif propose `ActiveAbilityMessage(<entité tuile>)`. Le régime T de ces deux-là n'est donc pas
  encore atteint *par la décision portée* — il l'est par `applyAction` et par tout appelant qui
  passe un `tileEntityId`.
* **`1148` et `1169` gardent leur normalisation locale de la cible** (`FixedTileIds` /
  `plagueburst_target_tile`) : elle est désormais adossée au foyer pour `1169`, mais `1148` choisit
  encore entre `Target()` et `FixedTileIds` selon le type de l'id reçu. Rendu identique dans les deux
  régimes (mesuré), donc laissé tel quel.
