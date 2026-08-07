# #498-r4-r1 — la fuite était réelle, et un second écart la rendait INOBSERVABLE

Le résidu demandait si `abilities/loki/momentum.py::_set_charge_flag` reproduit la fuite de
`UnitFlag.Undisplaceable` (0x19) hors de la charge de `1152`. Réponse : **non**, il retirait
toujours. Mais en montant le régime, le port s'est révélé ne **jamais poser** le flag — donc
l'écart demandé était masqué par un écart de substrat en amont.

## 1. Le chemin de sortie, lu verbatim

`IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableMomentumReworkedAbility$$ExecuteBehaviour` :

    Execute( AddFlag(Caster@0x48, 0x19) )
    cache = Cache( First( TilesBehindInLine(...), amount: this+0xf0 = 10 ), true )
    for (index = 0; index < this+0xf0; index++) {
        tile = SelectTile( AtIndex(cache, index) );
        if (tile == null) return;                      // <<< SORTIE SANS RemoveFlag
        if (!ExecuteBehaviourStep(...)) break;
    }
    Execute( RemoveFlag(Caster@0x48, 0x19) )

**La boucle INDEXE, elle n'itère pas.** Le port itérait sur le cache (`for index, tile_id in
enumerate(tiles)`), ce qui rend le `return` STRUCTURELLEMENT inatteignable, et un `try/finally`
retirait le flag sur tous les chemins. Deux écritures, une seule faute : la sortie par indexation
hors cache — ligne plus **courte** que 10 tuiles **et** traversée **intégralement** — laisse
`0x19` posé **pour le reste de la bataille**. Rien ne le lève : `UnitFlagsComponent$$RemoveTurnFlags`
ne retire que `0, 1, 2, 3, 4, 0xc, 0x1b`, et #498-r4 a établi que cette ability est le **seul**
écrivain de `0x19` (10 appelants de `DSLBehaviors$$AddFlag`, 40 sites d'`UnitFlagsComponent$$Add`).

Direction de l'écart : **PERMISSIVE** — le port rendait déplaçable un caster que le natif verrouille.
Six lecteurs portés en dépendent, dont la tête de `IdunBattle.Operations.DisplaceUnitOperation$$Execute`
(tout push, pull, déplacement direct, échange de position) et `DamagePrediction$$GetKnockback`.

## 2. Le second écart, trouvé par la mesure — le port ne posait RIEN

`AddFlagBehaviour$$Execute` accède au `UnitFlagsComponent` de chaque unité sélectionnée et **LÈVE**
s'il est absent. Natif, le cas n'arrive jamais (`UnitFactory` monte le composant sur toute unité).
Côté port, `snapshot._load_unit_flags` ne le matérialise que si la ligne du snapshot porte une liste
**non vide** — donc une unité sans aucun flag n'en a pas, et le `if fc is None: return` de
`_set_charge_flag` faisait de la pose un **no-op silencieux**.

Mesuré au premier run du probe : natif `unitFlags = [1, 2, 3, 4, 25]` après le cast, port `False`.
`_set_charge_flag` crée désormais le composant absent — même geste que
`turnflow.FinishUnitTurnOperation.execute`, qui le faisait déjà. **Le foyer reste ouvert** :
`_load_unit_flags` devrait matérialiser un composant VIDE sur toute ligne MESURÉE, ce qui vaudrait
pour les neuf autres appelants d'`AddFlag` — résidu **`#545`**.

## 3. La confrontation LIVE — deux bras, une seule variable

`probe_498r4r1_fuite_flag_undisplaceable_live.py`, `orksNob` sur `MC1_67`. Les montages sont LUS de
leur source unique (`probe_498_unstoppable_momentum.montages()`), aucun argument recopié. Canal de
mesure : `combatSnapshot.units[].unitFlags` — le capteur invoque
`IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` par valeur d'enum, il ne lit aucun set en
mémoire.

| bras | ligne portée | pas joués | `unitFlags` natif après cast | port | témoin (`try/finally`) |
|---|---|---|---|---|---|
| `fuite` (`switch`, cible au coin) | **1** tuile | 1 | `[1, 2, 3, 4, **25**]` | `True` | **`False`** |
| `retrait` (`bigtarget`) | 6 tuiles | 1 (break) | `[1, 2, 3, 4]` | `False` | `False` |

**Les deux verdicts natifs sont exercés** (garde ET retire) : un seul bras serait compatible avec
« le port ne retire jamais » ou « le port retire toujours ». La **vue rouge** est le `False` du
témoin sur le bras `fuite` — le port d'avant perdait le flag là où le natif le garde.

⚠ Le régime n'est pas un cas de coin. `TilesBehindInLine(checkWalkable: 1)` s'arrête à la première
tuile non marchable, donc **toute** ligne bornée par un bord ou un obstacle produit la fuite dès que
la charge la traverse. Le bras `retrait` a fallu le **construire** (un BigTarget adjacent) ; c'est la
sortie par `RemoveFlag` qui est le cas particulier, pas la fuite.

## 4. Les cliquets

`tests/engine/test_498r4r1_fuite_flag_undisplaceable_offline.py`, **8 tests / cinq étages** : la
ligne courte traversée (le `return`) ; les DEUX chemins qui atteignent le `RemoveFlag` (ligne
saturant `First(line, 10)`, et `break`) ; le MUTANT `try/finally`, qui doit effacer l'écart **sans
changer le chemin** (`flag_leaked` reste `True` — c'est l'état final qui bascule) ; le substrat
(`_set_charge_flag` doit mordre sans composant préalable, par le helper ET par le chemin réel) ; et
le LECTEUR, sur ses deux bras (`unit_extensions_is_displaceable` bascule avec le flag).

Vue rouge sur l'arbre témoin (`git archive origin/master`, arbre complet) : **6 failed** pour ce
fichier ; **8 passed** après.

## 5. Ce qui n'est PAS couvert

* **La CONSÉQUENCE de la fuite n'est pas confrontée live** : on mesure que le flag reste posé, pas
  qu'un push ultérieur sur le caster échoue des deux côtés. Le chaînage est porté
  (`unit_extensions_is_displaceable` est le foyer unique, six lecteurs) et gardé offline, mais le
  montage « charger, puis se faire pousser » n'a pas été joué.
* **Le foyer du substrat** (`_load_unit_flags`) reste ouvert — résidu `#545`. Les neuf autres
  appelants de `DSLBehaviors$$AddFlag` portent la même forme et n'ont pas été relus.
* **L'exception** laisse aussi le flag posé (il n'y a plus de `finally`) : c'est le comportement
  natif (le `throw` du décompilé ne retire rien), mais aucun montage ne l'exerce.
