"""Base des utilites d'IA natives `IdunBattle.AI.Utilities` (une CLASSE par `*Utility`).

Situe dans `engine.utilities` (et non `engine.ai.utilities`) POUR EVITER LES CYCLES D'IMPORT :
`engine.playbook.base` importe `engine.utilities.tile` (composite Tile) tres tot ; si la base tirait
`engine.ai` (-> context -> scene), on aurait un cycle. `engine.ai.utilities` (UtilitiesDatabase +
GetMovementUtility) reference ces classes sans les heberger.

Hierarchie native : `BaseUtility -> {feuille situationnelle, ComposedUtility}`. Chaque feuille porte son
`*Utility.<Evaluate*InSteps>d__N.MoveNext` (VA citee dans la sous-classe) ; un `ComposedUtility` (Tile=7,
Damage=34, …) = SOMME de ses enfants (`ComposedUtility.EvaluateMovement`/`EvaluateAttack` IdunBattle.AI.Utilities.ComposedUtility$$.ctor).

SIGNATURE : `evaluate(self, *args)` est GENERIQUE — chaque SOUS-SYSTEME fixe sa propre signature d'appel
(tile : `(tile, meta, ctx, wt)` ; damage : `(pred, target_max_hp, wt)` ; mouvement `(ctx, pos)`) et son
`ComposedUtility` somme ses enfants avec CES memes args. Le natif unifie via la query ; le port garde la
signature deja portee de chaque feuille (relocalisee telle quelle) -> pas de reecriture des corps."""
from __future__ import annotations


class BaseUtility:
    """`IdunBattle.AI.Utilities.BaseUtility` — racine. `UTILITY_TYPE` = valeur d'enum `UtilityType`
    (cle de `UtilitiesDatabase`). `evaluate(*args)` = `Evaluate*InSteps` de la feuille (override)."""
    UTILITY_TYPE: int = -1

    def evaluate(self, *args) -> float:
        raise NotImplementedError

    def has_utility_value(self, weights: dict, name: str) -> bool:
        """`IdunBattle.AI.Utilities.BaseUtility$$HasUtilityValue` : la cle `name` est presente dans le dict de poids
        de categorie (natif : `Dict<string,int>` @this+0x58, ici passe en argument `weights`)."""
        return name in weights

    def get_utility_value(self, weights: dict, name: str) -> int:
        """`IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue` : `Fix64.FromInt(weights[name])` via TryGetValue ;
        cle absente -> 0 (le natif logge un warning dev, ici muet)."""
        return int(weights.get(name, 0))


class ComposedUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.ComposedUtility` IdunBattle.AI.Utilities.ComposedUtility$$.ctor — utilite agregeant une liste d'enfants ;
    `evaluate = Σ enfant.evaluate(*args)` (la membership exacte est LUE runtime, cf. utilities/tile.py
    et docs/rl/playbook-engine.md §13.8). Les enfants partagent la signature d'appel du sous-systeme.

    Il n'y a PAS de classe dediee par composite (Tile=7, Damage=35, … ne sont PAS des classes natives) :
    ce sont des INSTANCES `ComposedUtility` enregistrees au bon `UtilityType`. D'ou le `utility_type`
    d'instance (l'enum de registration), et non un attribut de classe."""
    UTILITY_TYPE: int = -1

    def __init__(self, children: "list[BaseUtility]", utility_type: int = -1):
        self.children = children
        self.UTILITY_TYPE = utility_type   # type d'instance (Tile=7, Damage=35, …) ; PAS une sous-classe

    def evaluate(self, *args) -> float:
        total = 0.0
        for child in self.children:
            total += child.evaluate(*args)
        return total
