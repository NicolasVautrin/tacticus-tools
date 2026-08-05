# #429-r1-r3 — Le gate cible-morte a DEUX rangs, et le second n'avait jamais été lu

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`.

`GreatFrostAxe` (1089) était la dernière divergence de la famille : unique porteur du bit 38
`AllowDeadTarget`, il échappe **correctement** au gate d'opération posé par `#429-r1`, et le natif
le refuse quand même. Le port, lui, exécutait — il posait 6 tuiles de glace sur un cadavre et
consommait le tour du caster.

## 1. La piste première était FAUSSE, et c'est mesuré

La fiche parente supposait la **PORTÉE** : « le natif retire l'unité morte du board (`GetTiles`
vide), le port lui garde son `PositionComponent` ». Deux mesures indépendantes la réfutent :

* `abilityReason(caster=spaceWulfen, ability=1089, target=<cadavre>)` rend
  **`NoBrokenTargetingRule`** — la cascade de ciblage native ne rompt **aucune** règle sur ce
  cadavre, ni la portée ni une autre ;
* le cadavre **garde ses tuiles**. `decisionView` publie encore `pos = (2,3)` pour lui, et le hook
  y arrive en marchant `UnitFoot -> Tile` par `UnitFootComponent.TileId` (+0x14) — exactement le
  champ que `IdunBattle.Entities.EntityExtensions$$GetMainTileId` lit. Ce que la mort efface, c'est
  l'**occupation de la TUILE**, pas la tuile du pied : `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute`
  a **deux** boucles, et seule la seconde (gatée par `removeTileFromUnit`) remet `TileId` à 0.
  Vérifié en live : une autre unité peut se **déplacer sur la tuile du cadavre**, les deux y
  coexistant dans les vues.

## 2. Le vrai gate, et il est un RANG plus haut

```
IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)
    caster = state.GetEntity(message.CasterId@0x10)
    target = state.GetEntity(message.TargetId@0x14)
    abilityType = message.ActiveAbilityType@0x18
    if (!UnitExtensions.IsAliveAndNotFled(caster) || !IsAliveAndNotFled(target)) {
        AddBattleReporterDataForRejectedActiveAbilityMessage(...)    // INLINE ; ne loggue QUE
        return;                                                     // le cas caster MORT
    }
    RunPhase(6, () => { OpenGroup(0xc User_UseAbility); OperationProcessor.ActiveAbility(...) })
```

**Il ne lit ni l'ability ni ses `TargetingOptions` : aucune dérogation n'est possible.** C'est
pourquoi 1089 y tombe comme les 103 autres, tout en échappant légitimement au gate d'opération.

`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` **n'est pas la négation** d'`IsDead` — trois
écarts, tous lus :

| entrée | `IsAliveAndNotFled` | `IsDead` |
|---|---|---|
| `null` | **false** | false |
| vivante | true | false |
| morte | false | **true** |
| `UnitFlag.Fled` (9), hp 0 **ou** hp > 0 | **false** | **false** |
| entité **sans** `HealthComponent` (une TUILE) | **true** | false |

La dernière ligne n'est pas cosmétique : le natif **saute** le test de mort quand
`TryGetComponent<HealthComponent>` échoue. C'est ce qui laisse passer les abilities tile-target —
mesuré, cf. §3.

> Le symbole `AddBattleReporterDataForRejectedActiveAbilityMessage` n'a que 2 xrefs **DATA** parce
> qu'il est **inliné** dans ce `Visit`. `search_code` en mode littéral rend `0` sur ce binaire
> (déjà mesuré par `#429-r1`) : c'est la lecture du corps qui l'a établi.

## 3. L'étage est MESURÉ, pas déduit

Le groupe de stream `User_UseAbility` (12) est ouvert par la **lambda** du `Visit`, donc **après**
ce gate et **avant** l'opération. Le compte d'événements sépare donc les deux rangs, et le bras
témoin est ce qui rend « 0 événement » interprétable :

| bras (même montage, même caster) | événements | groupes |
|---|---|---|
| 1089 sur cible **vivante adjacente** | 43 | exécution complète |
| 1089 sur cible **vivante hors portée** (refus au rang OPÉRATION) | **2** | `[12]` |
| 1089 sur **cadavre** | **0** | `[]` |
| attaque **normale** sur cadavre | **0** | `[]` |
| 1003 `DeathFromAbove` sur cadavre | **0** | `[]` |
| 1089 sur la **TUILE** du cadavre | **2** | `[12]` |

Les deux dernières lignes tranchent deux questions d'un coup : le gate vaut pour **toute** ability
(1003 n'est donc pas refusé en live par le gate d'opération de `#429-r1`, mais par celui-ci), et il
ne mord **pas** sur une cible-tuile.

## 4. Le fix

Un foyer + une pose, au rang natif :

* `engine/runner/components.py::is_alive_and_not_fled` — mirror 1:1, quatre branches ;
* `engine/runner/abilities/handler.py::visit_ActiveAbilityMessage` — le gate en tête, sur le caster
  puis la cible, puis délégation à `_active_ability_operation` (le corps existant, extrait).

**L'extraction n'est pas cosmétique** : `ExecuteForReplacedTarget` re-entre côté natif dans
`ActiveAbilityOperation$$Execute` **sans** repasser par le `Visit`. La ré-entrée du port appelle
donc `_active_ability_operation`, pas le visiteur. L'écart serait inerte (`resolve_replaced_target`
ne rend qu'un occupant vivant), mais un gate posé au mauvais rang est un fork — celui-là même que
`#120` avait fermé sur cet étage.

**Convention permissive**, comme le reste du module : `target_id is None` (le port modélise ainsi
« pas de cible », le natif n'a que des ids) et entité absente de l'état ⇒ aucun refus.

## 5. Les chiffres

**L'observable n'est PAS le RNG**, et c'est le piège de cette tranche : l'arbre de 1089 est
`op_and(AddEffect(Ice), If(IsAlive(target), attaque))` — sur un cadavre la garde `IsAlive` éteint
déjà l'attaque, donc **0 tirage des deux côtés, gate ou pas**. Ce qui mord est la GLACE et les
FLAGS DE TOUR.

| | glace | flags de tour | événements |
|---|---|---|---|
| NATIF | — | action **non** consommée | 0 |
| PORT pré-fix | **6 tuiles** | posés | — |
| PORT post-fix | 0 | aucun | — |
| PORT, gate neutralisé (contre-épreuve) | **6 tuiles** | posés | — |

**L'oracle de sortie, joué pour de vrai** (un `Runner.apply` complet par ability, pas un compte de
prédicats) sur un état où la cible est un cadavre :

* chaîne complète → **104 / 104** refusées ;
* gate de MESSAGE débranché → **103 / 104**, unique rescapée **`1089`**.

C'est cette seconde ligne qui **attribue** le passage : un 104/104 obtenu par un mécanisme faux
donnerait un bras muté identique au témoin, ou en raterait plusieurs.

## 6. La garde

`tests/engine/runner/test_429r1r3_dead_target_message_gate_live.py` — **12 tests, ~57 s** :
l'attribution d'étage avec son témoin, le bras tuile, le natif, le port, la contre-épreuve au
FOYER, l'oracle 104/104 et son attribution, la généralisation (seed 31337), la non-régression du
gate d'opération, et les quatre branches offline du mirror.

`test_429r1_dead_target_gate_live.py` est **décomposé par étage** plutôt qu'affaibli : les deux
gates sont désormais débranchés **un à un** (message seul → le gate d'opération refuse `1003` et
**déroge** pour `1089`, qui exécute sa behaviour ; les deux → le port exécute). La dérogation du
bit 38 passe ainsi d'assertion sur un prédicat à **mesure observable**.

Non régressé (re-joué) : `test_429r1r1_normal_attack_dead_target_live` (7),
`test_429r1r1r1_ability_attack_dead_target_live` (9), `test_sworn_protector_kell_live` (7),
`test_great_frost_axe_live` (1), `test_ability_target_gate_live` (13),
`test_summon_ability_ports_live` (2), `test_summon_automatic_live` (8).

## 7. Ce qui n'est PAS couvert

* **Le volet CASTER du gate n'est pas confronté.** Il est porté (mirror du même `||`), mais aucun
  montage n'a fait caster une unité morte ou enfuie par la voie message.
* **Le flag `Fled` n'est confronté nulle part**, ni sur le caster ni sur la cible : aucun montage
  n'a produit d'unité enfuie. Les quatre branches du prédicat sont gardées **offline**.
* **Un seul board** (`MC1_67`), deux seeds. Le discriminant est structurel (la glace part ou ne
  part pas), pas un scalaire à ajuster.
* **Les gates 9 et 10 du `Visit`** (deux appels d'interface non résolus par Ghidra, postérieurs au
  gate cible-morte) ne sont ni lus ni portés. Ils ne peuvent pas expliquer les mesures ci-dessus
  (ils sont sur le chemin d'ACCEPTATION), mais ils existent.

## 8. Résidu nommé

* **`#429-r1-r3-r1` — le gate de MESSAGE n'est pas posé sur la voie `AttackUnitMessage`, et l'écart
  porte sur `Fled`.** Côté natif l'attaque normale EST un `ActiveAbilityMessage` et traverse le même
  `Visit` ; côté port elle a son propre visiteur, où seul le gate d'OPÉRATION est posé. Sur la MORT
  les deux convergent (`is_dead_unit_and_not_allowed_by_ability(None, ...)` refuse tout cadavre) ;
  sur `UnitFlag.Fled` **non**, puisque `IsDead` exclut expressément ce flag. NON MESURÉ.

## 9. Re-dériver

```
python scripts/python/probe_429r1r3_dead_target_message_gate.py --volet offline
python scripts/python/probe_429r1r3_dead_target_message_gate.py --volet signature  --state-file <ABSOLU>
python scripts/python/probe_429r1r3_dead_target_message_gate.py --volet port       --state-file <ABSOLU>
python scripts/python/probe_429r1r3_dead_target_message_gate.py --volet couverture --state-file <ABSOLU>
python -m pytest tests/engine/runner/test_429r1r3_dead_target_message_gate_live.py -q
python -m pytest tests/engine/runner/test_429r1_dead_target_gate_live.py -q
```

⚠ `104` est `len(ABILITY_CLASSES)` : il bouge à chaque tranche portée, et le probe comme le test le
**dérivent** au lieu de le citer.
