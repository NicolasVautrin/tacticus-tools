# #287-r14 — `TargetingQuery$$GetActualTarget` : le port avait **deux régimes de cible**, le natif n'en a **qu'un**

Le port recevait tantôt une **UNITÉ** (tous les tests live : `_ringed_cast.cast_and_confront` envoie
`targetId: <unité>`), tantôt une **TUILE** (la face DÉCISION portée : `abilityTargets` rend
`kind: "tile"`, l'action porte le `tileEntityId`). Le natif accepte les deux **parce qu'il transforme
lui-même**. Le port, lui, propageait l'argument tel quel.

## 1. La chaîne native — relue, pas héritée

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` transforme sa cible **AVANT ses deux
gates**, et l'ordre est celui-là (lu au décompilé, build `rnca9r7q6c`) :

    ability     = AbilitiesDatabase.Get(abilityType);
    casterTiles = EntityExtensions.GetTiles(caster, state);
    finalTarget = IActiveAbility.GetActualTarget(ability, caster, target);   // slot IActiveAbility 16
    if (finalTarget == null) return;
    if (IsDeadUnitAndNotAllowedByAbility(abilityType, finalTarget)) return;
    if (IsInvalidTarget(caster, casterTiles, finalTarget, ...)) return;
    ... GetAbilityEntities(this, caster, casterTiles, finalTarget, abilityType);   // +0x10 <- finalTarget

`IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget` recopie les 0x40 octets de **ses**
`TargetingOptions` (`this+0xb0`) et délègue au slot `ITargetingQuery` 6 =
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` :

    if (options.isSelfCasting == 0) {                      // byte @options+0x00
        if (options.rules & 0x40)          return EntityExtensions.GetMainTile(target, state);
        if (options.rules & (1<<44))       return UnitExtensions.GetMachine(target, state);
        if (options.rules & (1<<46)) { u = UnitExtensions.GetUnit(target, state);
                                       return u != null ? u : GetMachine(target, state); }
        return UnitExtensions.GetUnit(target, state);
    }
    return caster;

Les deux numéros de slot sont **lus** dans `data/symbols/<build>/metadata/interface_slots.tsv`
(`ITargetingQuery 6 GetActualTarget`, `IActiveAbility 16 GetActualTarget`).

⚠ **La branche MACHINE n'essaie PAS `GetUnit` d'abord** — seule la branche ACTOR enchaîne les deux.
Écrire « unit puis machine » partout serait un masque faux.

⚠ **La surcharge de `GetUnit` se tranche par les XREFS, pas par le nom** : le binaire en porte
**trois** (tuile→unité, pied→unité, et le dispatch domaine mixte). Les deux call-sites de
`GetActualTarget` visent la troisième, dont le corps teste `Unit` → l'entité elle-même, `Tile` →
l'occupant via `TileContentComponent` **avec récursion**, `UnitFoot` → son unité, sinon `null`.

## 2. Le rayon — mesuré dans DEUX voies, parce qu'elles ne couvrent pas le même ensemble

`probe_287r14_get_actual_target.py` joue **tout** `ABILITY_CLASSES` dans les deux régimes sur un
substrat identique et compare une **empreinte d'ÉTAT** (effets posés + PV + positions + morts), pas
le diagnostic rendu.

⚠ **Le critère par le RETOUR aurait rendu « rayon 0 »** : `1018` rend `deferred_effect: 1022` dans
les deux régimes — c'est le **porteur** de l'effet qui diffère, pas le diagnostic.

| voie | avant | après |
|---|---|---|
| `execute_behaviour` en direct — `TargetIsTile` | **14 divergentes** sur 23 | **0** |
| `AbilityHandler.visit_ActiveAbilityMessage` — **toutes** | **0** (la mesure n'existait pas ; le trou était en amont) | **0**, 44 témoins non nuls |

Le témoin non nul est obligatoire : **85 des 129** casts sont inertes sur le montage générique (les
gates de ciblage refusent la cible), et un accord entre deux no-op ne prouve rien.

## 3. Les deux branchements, et pourquoi le second n'est pas un fork

* **`AbilityHandler._active_ability_operation`** — la place NATIVE : la résolution y précède
  `IsDeadUnitAndNotAllowedByAbility`, `IsInvalidTarget`, le snapshot `GetTiles(finalTarget)`, la
  re-résolution `ExecuteForReplacedTarget` et `execute_behaviour`. C'est ce branchement-là qui couvre
  le moteur (`applyAction`, RL, tests live).
* **La tête des 23 `execute_behaviour` `TargetIsTile`** — le port **fusionne** dans
  `execute_behaviour` deux étages natifs (`GetAbilityEntities` + `AActiveAbility$$ExecuteBehaviour`) ;
  la résolution est l'étage immédiatement amont du premier, donc son ancrage le plus proche côté
  port. Elle y est **inerte** quand le handler a déjà résolu.

**L'idempotence est ce qui autorise les deux** : chaque branche est un projecteur
(`GetMainTile(<tuile>)` rend la tuile, `GetUnit(<unité>)` l'unité, `GetMachine(<MoW>)` la MoW,
self-cast rend `caster`). Elle est gardée (étage [2] du cliquet), pas supposée.

## 4. Les deux non-mesures qui ne doivent PAS devenir des refus

* **`TARGETING_OPTIONS is None`** (masque non RE-lu) → `target_id` rendu tel quel. Même doctrine que
  le gate de cible : sans masque le port ne devine pas.
* **`state.board is None`** (boardGraph non chargé — `load_state(dv, ob, snap)` sans `board=`) →
  `target_id` rendu tel quel. Ce n'est pas « la cible n'a pas de tuile ».
  **MESURE** : sans ce repli, `test_valkyrie_strike_migration_live` passait de « l'arbre DSL pose
  1022 » à `execute_behaviour -> None`, un no-op complet — une non-mesure rabattue en REFUS.

⚠ **Une MoW n'est pas une `Unit`.** Le natif la classe `Machine` ; le port lui pose un
`UnitComponent` pour la rendre exerçable (`snapshot._load_machines`). Le discriminant retenu est le
`MachineComponent` : sans lui, `GetUnit(<MoW>)` rendrait la MoW là où le natif rend `null`.

## 5. La confrontation LIVE — `probe_287r14_confront_live.py` (`MC1_67`, seed 777)

Cast de `1018 ValkyrieStrike` avec `targetId` = **l'id d'UNITÉ** (le régime que le port empruntait) :

| | porteur de l'effet `1022` |
|---|---|
| **NATIF** | **TUILE 74** (`tileMeta.tiles[].effects`) ; `decisionView.units[].effects` **inchangé** |
| **PORT** après la tranche | **74** — accord |
| **TÉMOIN** (résolution neutralisée) | **77**, l'unité — la divergence que la tranche ferme |

Le témoin est obligatoire : sans lui, un accord natif/port ne distingue pas « la résolution porte le
résultat » de « il vient d'ailleurs ».

⚠ Le champ du canal est `effectType`, **pas** `type`, et `tileMeta.tiles[]` n'a **pas** de champ
`id` (indexé par `(col,row)`) : les confondre rend deux dicts vides, donc « le natif ne pose RIEN »
— la conclusion inverse de la vérité (faute commise et corrigée dans #287-r12 ; ce probe réutilise
ses deux lecteurs plutôt que d'en écrire de nouveaux).

## 6. La garde

`tests/engine/runner/test_287r14_get_actual_target_offline.py`, **11 étages** : les quatre branches +
self-cast ; la contre-épreuve d'ordre (MACHINE ne passe pas par `GetUnit`) ; l'idempotence ; les deux
non-mesures ; le **cliquet de registre voie behaviour** (le critère de la tranche) ; le **cliquet de
registre voie handler** (toutes les abilities) ; le **témoin non nul** ; le **balayage STATIQUE** du
geste au registre ; la MoW ; le porteur TUILE de `1022` (valeur mesurée live) ; et l'**atteignabilité
du gate `finalTarget == null`**.

Vue rouge sur l'arbre témoin (`git archive` du commit d'avant la tranche) : **11 failed / 1 passed**.
Le seul vert est `etage8b`, qui assertionne le **non-vide** du balayage statique — un invariant que la
tranche ne change pas, et sans lequel l'étage [8] serait vert sur un ensemble vide.

⚠ **L'import des trois symboles NEUFS est LOCAL** (`_foyer()`), et la raison n'est pas un cycle : au
niveau module ils feraient échouer la **collecte** sur l'arbre témoin, et un fichier non collecté ne
montre **aucun** de ses autres étages. Même parade que `test_287r12_role_target_tuile_offline` pour
`main_tile_id`.

⚠ **L'étage [11] existe parce que le gate `finalTarget == null` n'est exercé par AUCUN des 258 casts
du balayage** (mesuré) : ce sont ces branches-là qui dérivent en silence. Il l'exerce explicitement
— une ability UNIT-TARGET dont la cible est une **tuile vide**.

## 7. Ce qui n'est PAS couvert

* **`#287-r14-r1` — la voie `execute_behaviour` ne résout que les `TargetIsTile`.** Mesuré après la
  tranche : **73** abilities divergent encore entre les deux régimes par appel DIRECT (72
  `GetUnit (défaut)` + 1 `TargetIsActor`), parce que la ligne de résolution n'est posée que sur les
  23 tile-target. Ce régime — passer un id de TUILE en direct à une ability unit-target — n'est
  emprunté par **aucun appelant réel** (la face décision n'émet un `tileEntityId` que pour les
  tile-target, et le moteur passe par le handler, qui résout), mais un futur probe pourrait
  l'emprunter, exactement comme `test_valkyrie_strike_migration_live` a gravé le régime U.
* **`#287-r14-r2` — `TileExtensions$$GetMachinePlatformContent` n'est pas porté** : c'est la branche
  TUILE de `UnitExtensions$$GetMachine`. Le port ne modélise pas les plateformes de MoW comme contenu
  de tuile (une MoW n'a ni `PositionComponent` ni tuile — `snapshot._load_machines`, « hors-plateau »),
  donc il n'existe aucun substrat d'où la tirer. `machine_id` rend `None` sur une tuile, ce qui est la
  dégradation fidèle à ce que le port sait — mais une ability `TargetIsMachine` ciblant la
  **plateforme** plutôt que la machine résoudrait `None` là où le natif rend la MoW.
* **La branche `UnitFoot` de `GetUnit`** n'a pas de contrepartie : les pieds n'ont pas d'entité propre
  côté port (`get_unit_feet` rend des **positions**). Aucun appelant du port ne tient d'id de pied.
* **`test_valkyrie_strike_migration_live` grave toujours le régime U** — et c'est correct : il charge
  `load_state(dv, ob, snap)` **sans board**, donc la résolution y est inerte par le repli du §4. Il
  reste juste **en tant que test de migration** (il confronte DSL vs impératif, pas le porteur au
  natif) ; c'est `probe_287r14_confront_live.py` qui confronte le porteur.
* **L'espace d'ids partagé tuile/entité** reste le résidu déjà nommé dans
  `operations/active_ability.py` : un id ambigu est tranché par l'ordre de `main_tile_id` (unité
  d'abord, tuile en repli — l'ordre natif), ce n'est pas une séparation des espaces.
