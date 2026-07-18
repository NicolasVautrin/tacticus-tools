# Substrat LIVE du contexte DSL (base du « S-chantier ») — RE prouvé (ghidra gqfc5mff6c)

> Fondation du **S-chantier** : replier une composition STRUCTURELLE (`If`/`&`/`Not` + prédicats en
> nœuds) en UN arbre DSL exige de savoir CE SUR QUOI le natif s'appuie pour qu'un même arbre reste
> correct **à travers une mutation intra-arbre**. Cas-témoin : `TheBetrayer_TakeTurn` (`MoveUnit` puis
> re-test `IsAdjacent`). Mon `DslContext` (`engine/dsl/base.py`) fige `pos:{col,row}` dans chaque dict
> d'unité (`entities_from_state`) → un arbre unique lirait des positions PÉRIMÉES post-move. Le natif, non.

## Réponse (prouvée 4×)

**Le natif tient des RÉFÉRENCES D'ENTITÉS VIVANTES et re-dérive la position À CHAQUE éval de prédicat ;
le `&` est une SÉQUENCE court-circuit (gauche exécutée — donc mutée — AVANT droite). Aucun snapshot de
position.** Le seul « gel » possible = une position VIRTUELLE explicite (override AI sweep), = mon `caster_pos`.

### Preuve 1 — un SEUL nœud `IsAdjacent`, évalué deux fois (`CreateBehaviour @1811a4f70`)

```
If( AmountIsGreaterThanZero(target),
      Inform(0xbf)
    & If( Not( IsAdjacent(Self@0x148, target, 3) ),  MoveUnit(Self -> bestTile) )   # gate PRE-move
    & If(      IsAdjacent(Self@0x148, target, 3),     Attack(target) ) )            # MEME noeud, POST-move
```

Dans le décompilé, `uVar4 = DSLFactory.IsAdjacent(Self, target, 3)` est réutilisé TEL QUEL dans
`op_LogicalNot(uVar4)` (branche move) ET dans `If(uVar4, attack)` (branche attaque). Deux évals du même
objet-nœud, verdicts DIVERGENTS requis (avant : non-adjacent → move ; après : adjacent → attack) ⇒ la
lecture de position DOIT être live, sinon les deux évals donneraient le même verdict et le jeu serait cassé.

### Preuve 2 — `CombinedBehaviour.Execute @180ffe730` = séquence court-circuit (déjà RE slice-2, dsl-effect-nodes §2)

`&` (`op_BitwiseAnd @180ffaae0`) et `+` (`op_Addition @180ffaa70`) construisent un `CombinedBehaviour`
(enfants `left@0x50` / `right@0x58`). `Execute` : exec left, `Combine` ; `if result.byte@+0x20 == 0` →
exec right, sinon STOP. Deux effets purs → flag 0 → les deux s'exécutent DANS L'ORDRE. Donc `MoveUnit`
(gauche) mute la position **avant** que le `IsAdjacent` (droite) re-teste.

### Preuve 3 — `AbilityEntities` tient une RÉF D'ENTITÉ, pas une position (`get_CasterPosition @180fb4f20`)

```c
if (*(ent+0x48) != 0) return *(ent+0x48);            // +0x48 = position VIRTUELLE explicite (override AI sweep)
UnitPosition..ctor(res, *(ent+0x40), 0); return res;  // sinon = DERIVEE de l'ENTITE @+0x40
```

`get_HasCasterPosition @180fb4f60` : vrai si `+0x48` OU `+0x40` non-nul. Donc **`+0x40` = réf entité caster
(toujours présente)**, **`+0x48` = override optionnel** (position hypothétique). En exécution réelle `+0x48`
est nul → CasterPosition dérivée de l'entité vivante à chaque appel.

### Preuve 4 — `UnitPosition..ctor @18102a070` n'encapsule AUCUN col/row

```c
lVar1 = new List<T>();
if (param_2 != 0) List.Add(lVar1, param_2);   // param_2 = *(ent+0x40) = la REF D'ENTITE
*param_1 = lVar1;
```

`UnitPosition` = wrapper autour d'une `List` contenant **la référence d'entité**. Le col/row est résolu
**en aval**, au test d'adjacence (`IsAdjacentAbilityTrigger.ShouldTrigger` → `FUN_1800051a0(0x5f, ...)`),
donc **live** depuis le `PositionComponent` courant.

## Le prédicat lui-même (`IsAdjacentAbilityTrigger$$ShouldTrigger @180f9f7b0`)

gshared (noms `FUN_` masqués, sémantique lue par la structure) : copie le contexte sur la pile, puis
**évalue le SÉLECTEUR caster (`node+0x20`) ET le SÉLECTEUR target (`node+0x28`) contre ce contexte**
(`FUN_180025220(3, ..., selecteur, contexte, range)`), enfin boucle sur les paires de positions et teste
l'adjacence via `FUN_1800051a0(0x5f, ..., adjSvc@node+0x10, casterPos, targetPos)`. La position provient de
l'**éval du sélecteur contre le contexte à chaque appel** — jamais d'un scalaire stocké dans le nœud.
`node+0x18` = arg range (le `3`), `node+0x10` = service/prédicat d'adjacence.

## Contexte by-value ≠ snapshot de position

`AbilityEntities` est passé **BY-VALUE (0x50 octets)** à chaque `Execute` (dsl-effect-nodes §1). Mais la
copie copie une **RÉF** (`+0x40`), pas des col/row → la dérivation reste live. Le natif reconstruit même
le contexte dans certains nœuds (`ForeachBehaviour.Execute @180fc6210` : `subject`=cible courante) — même
esprit que reconstruire un snapshot par étage.

## Le natif n'est PAS « tout live » — il fige SÉLECTIVEMENT (`Cache`)

Nuance capitale pour ne pas mal porter : le natif garde la POSITION live-par-réf **par défaut**, et fige
là où il veut de la stabilité, **explicitement**, via `DSLFactory.Cache @180deb0d0` :

- **Identité d'entité** → snapshot QUAND l'arbre le veut, via `Cache`. TheBetrayer : `uVar4 =
  Cache(GetAttackTarget(...), 1)` (@1811a4f70) fige QUELLE cible (on attaque celle vers qui on s'est
  déplacé, même si un ennemi plus proche apparaît) ; `uVar4` est ensuite réutilisé par
  `AmountIsGreaterThanZero`, `IsAdjacent` et l'attaque.
- **Position d'entité** → TOUJOURS live-par-réf, dérivée à la lecture. `Cache` fige *quelle* entité, **pas**
  *où* elle est : même la cible cachée a sa position relue live par `IsAdjacent`.
- **Position virtuelle** (`+0x48`) → override explicite, uniquement décision balayée AI.

**Mon port fait l'INVERSE** : `entities_from_state` fige TOUT par défaut (identité *et* position dans le
dict `{id,...,pos}`). « Faire pareil » ≠ dégeler les dicts, mais **inverser le défaut** : (1) position
live-par-réf (`DslContext` tient `state` + entity-ids, dérive `pos` à la lecture) ; (2) snapshots
EXPLICITES via un nœud `Cache` (absent du port) ; (3) override `+0x48` = `caster_pos` (déjà là), avec
**précédence sur la réf live** — sinon la prédiction/sweep (`predOptimistic`) lirait la vraie position au
lieu de la tuile hypothétique et casserait la décision balayée. C'est le modèle à **deux modes** à porter.

## Conséquence pour le port — les deux voies du S-chantier

Mon `entities_from_state` (`engine/runner/abilities/behaviours.py`) fige `pos:{col,row}` dans chaque dict
d'unité → un arbre DSL UNIQUE lirait périmé post-move. Pour unifier en arbre en PRÉSERVANT la dérivation live :

- **Voie A (mirror natif fidèle)** : le `DslContext` tient un handle `state` + les entity-ids et **dérive
  `pos` live par éval** (au lieu de figer). `IsAdjacent`/sélecteurs relisent `PositionComponent` à chaque
  `should_trigger`/`select`. Distinguer `+0x48` (override virtuel = `caster_pos`, décision balayée AI) de
  `+0x40` (réf live, exécution réelle).
- **Voie B (mirror du `Foreach`)** : reconstruire le contexte entre enfants séquentiels du `&`.

**Déjà en place FONCTIONNELLEMENT** (mais en impératif, pas en arbre unifié) : `_betrayer_take_turn`
(`operations/triggers/loki.py`) reconstruit `entities_from_state` PAR feuille ET relit
`_is_adjacent_units(state, ...)` **live** pour les prédicats d'adjacence pré/post-move → mirror exact du
comportement live natif. Le S-chantier ne change PAS le comportement — il **replie** cette logique
impérative en nœuds DSL (`If`/`&`/`Not` + `IsAdjacent`/`AmountIsGreaterThanZero`), ce qui n'est possible
qu'avec la voie A ou B. Le champ `caster_pos` (`dsl/base.py`) mirror DÉJÀ le `+0x48` natif.

Portée = **familles T (prédicats) + S (sélecteurs) en entier**, pas une ability : tout nœud lisant une
position est concerné → validation propre sur toute la surface. Recoupe le playbook (même question
live-vs-snapshot dans la décision balayée post-move, cf. `predOptimistic`/`caster_pos`) → **axe séparé de
#149** (qui portait les feuilles E, terminé).

## État : Voie A IMPLÉMENTÉE (fondation + 1er cas, PROUVÉ LIVE 2026-07-18)

- **Slice A1 — `LiveUnit`** (`engine/runner/abilities/behaviours.py`) : `entities_from_state` construit
  désormais `caster`/`target`/`units` comme des `LiveUnit(dict)` — sous-classe `dict` (reste reconnue par
  les `isinstance(v, dict)` du DSL) dont les champs MUTABLES (`_LIVE_KEYS` = pos/hp/alive) sont RE-LUS du
  `state` à chaque `get`/`[]` (mirror `AbilityEntities+0x40` : réf d'entité stable, position re-dérivée).
  Le chemin PRÉDICTION (`playbook/prediction.py`) garde ses dicts FIGÉS + `caster_pos` (mode `+0x48`,
  frozen-by-design). Validé : 4/4 (TheBetrayer + Fragstorm AoE) — représentation transparente, zéro régression.
- **Slice A2 — arbre DSL unifié TheBetrayer** (`operations/triggers/loki.py` `_betrayer_take_turn`) : la
  composition structurelle est repliée en NŒUDS (`Seq`=`CombinedBehaviour`, `If`, `Not` [NEW, `op_LogicalNot`],
  `IsAdjacent`, `Inform`) partageant UN contexte `entities_from_state`. Le MÊME nœud `is_adj =
  IsAdjacent(Caster(), Target())` est réutilisé sous `Not` (move-gate) ET direct (attack-gate) — comme le
  natif `uVar4` — et rend deux verdicts DIVERGENTS à travers le move (re-éval LIVE via `LiveUnit`). Plus
  aucun `_is_adjacent_units` impératif. Validé : 4/4 (2 migration + turnstart replay-diff + rage).
- **Frontière préservée** : les sélecteurs S LOURDS restent COLLAPSÉS (cible `_betrayer_target`, tuile
  `_betrayer_stop_tile`), fournis à l'arbre comme valeurs (`Target()`/`FixedTiles`). Le gate
  `AmountIsGreaterThanZero(target)` reste le gate S collapse (`if target is None`) — le folder exigerait
  d'un-collapser la cible en LISTE (contre la doctrine). L'`after_move_triggers` (overwatch du move forcé) est
  émis via un `Emit("BetrayerAfterMove")` DANS la branche move (ordre move→after→attack) — **FIDÈLE au natif**
  (task #4 RÉSOLU, cf. section « After-move overwatch » ci-dessous), PAS un over-trigger.
- **RESTE (généralisation)** : seul le contexte RUNNER est live ; la surface T/S entière le devient
  cas-par-cas (toute future ability mutate-then-predicate). `Cache` (identité) existe déjà (`selectors.py`).

## After-move overwatch : FIDÈLE (task #4 RÉSOLU, RE 2026-07-18)

Question tranchée : le MOVE FORCÉ de TheBetrayer (nœud `MoveUnit` à OPTIONS NULLES, comme ThunderousAssault)
déclenche-t-il l'after-move overwatch dans le natif ? **OUI — universel, le port est fidèle (garder l'`Emit`).**

Chaîne : `TheBetrayer_TakeTurn$$CreateBehaviour @1811a4f70` → `DSLFactory.MoveUnit @180df6ae0` →
`MoveUnitBehaviour$$.ctor @180fcad60` (stocke les 7 options en `+0x60..0x90`) → `MoveUnitBehaviour$$Execute
@180fca4f0` (évalue les options → bitfield) → `MoveUnitOperation$$Execute @180e79ff0` →
`MoveUnitOperation$$EvaluateAfterMoveTriggers @180e79770`.

`EvaluateAfterMoveTriggers @180e79770` émet l'overwatch after-move via `On(4)`, mais **gaté** :

```
FUN_180026490(0x4d, ..., 0x24, ...);   // On(0x24)
if (param_6 != '\0') { return; }        // GATE
FUN_180026490(0x4d, ..., 4,    ...);   // On(4) = after-move / overwatch
```

`param_6` = octet 4 du bitfield options (`plVar1[2] >> 0x20 & 0xff`) = `uVar15` dans `MoveUnitBehaviour.Execute`,
dérivé du champ **options[4]** (`behaviour +0x80` ; ctor `*(param_1+0x80)=param_4[4]`) :
`if (*(param_2+0x80)==0) uVar15=0`.

⇒ **options[4] est un flag SUPPRESS (opt-in au SKIP), défaut 0 = overwatch ACTIF.** Options nulles (Kharn ==
ThunderousAssault) ⇒ `param_6 = 0` ⇒ le gate `if (param_6 != 0) return` n'est PAS pris ⇒ `On(4)` ÉMIS. Il
n'existe PAS de flag « enable overwatch » à activer : l'overwatch est le DÉFAUT, désactivable seulement par une
option explicite (que ni Kharn ni ThunderousAssault ne passent). Sémantique des autres octets d'options nulles :
octet 5 (`+0x88`) gate un fast-path (défaut 0 = chemin normal, qui émet aussi `On(4)`) ; octets 0/1 (`+0x78`/
`+0x70`, XOR 0x0101) = SetMovedFlag/charge, sans lien avec l'overwatch.

**Émission UNIQUE côté port** : `MoveUnitOperation.execute` (port) est POSITION-SEULE (INCRÉMENT 1b
`EvaluateAfterMoveTriggers` non replié) ; le move NORMAL émet l'after-move dans
`MovementHandler.visit_MoveUnitMessage`, PAS l'Operation. Pour le move DSL de Kharn, l'`Emit("BetrayerAfterMove")`
explicite est donc le SEUL vecteur after-move → une émission, pas de double. ⚠ Si INCRÉMENT 1b replie un jour
`EvaluateAfterMoveTriggers` DANS `MoveUnitOperation.execute`, RETIRER cet `Emit` (sinon double-émission).

## VAs (référence)

- After-move overwatch : `MoveUnitBehaviour$$Execute @180fca4f0` ; `MoveUnitBehaviour$$.ctor @180fcad60`
  (options `+0x60..0x90`, options[4]=`+0x80`) ; `MoveUnitOperation$$Execute @180e79ff0` ;
  `MoveUnitOperation$$EvaluateAfterMoveTriggers @180e79770` (émet `On(4)` gaté par `param_6`=options[4]=flag SUPPRESS)
- Port : `engine/runner/operations/movement.py` (`MoveUnitOperation.execute` position-seule, INCRÉMENT 1b TODO ;
  `MovementHandler.visit_MoveUnitMessage` = after-move du move normal)
- Arbre : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$CreateBehaviour @1811a4f70`
- `DSLFactory$$IsAdjacent @180df2f00` → `IsAdjacentAbilityTrigger$$ShouldTrigger @180f9f7b0` (ctor `@180f9fc10`)
- `AbilityEntities$$.ctor @180fb4d50` / `@180fb3c30` ; `get_CasterPosition @180fb4f20` ;
  `get_HasCasterPosition @180fb4f60` ; `get_TargetPosition @180fb5320`
- `UnitPosition$$.ctor @18102a070`
- `CombinedBehaviour$$Execute @180ffe730` ; `op_BitwiseAnd @180ffaae0` ; `op_Addition @180ffaa70`
  (enfants `left@0x50` / `right@0x58`) ; `ForeachBehaviour$$Execute @180fc6210`
- Offsets `AbilityEntities` : `+0x40` = réf entité caster (live) ; `+0x48` = CasterPosition explicite (override virtuel)
- Port côté nous : `engine/dsl/base.py` (`DslContext`, champ `caster_pos`) ;
  `engine/runner/abilities/behaviours.py` (`entities_from_state`) ;
  `engine/runner/operations/triggers/loki.py` (`_betrayer_take_turn`, mirror live impératif actuel)
