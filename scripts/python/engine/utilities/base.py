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


class Fix64Sentinel(float):
    """Une des valeurs SENTINELLES de `IdunBattle.AI.Utilities.BaseUtility` — un `float` (donc
    utilisable partout ou une utilite l'est) que l'on distingue par son **IDENTITE**.

    POURQUOI l'identite et pas la valeur. Le natif ecrit ces sentinelles dans des CHAMPS STATIQUES
    et les teste par egalite contre ces memes champs
    (`IdunBattleLogic.AI.Utilities.UtilityDecider.u003CCalculateUtilityInStepsu003Ed__9u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`,
    puis `...u003CCalculateUtilitiesForCasesEnumeratedu003Ed__7u003Cobjectu003E$$MoveNext`) : ce
    qui circule est bien une valeur DESIGNEE, pas un intervalle numerique. Deux d'entre elles sont
    des DIVISIONS `Fix64` (`op_Division`) dont le port ne mirrore pas l'arithmetique Q32.32 --
    leur valeur flottante ci-dessous est donc **APPROCHEE**, et une comparaison `==` contre un
    resultat de calcul serait une coincidence, jamais une lecture.

    ⇒ **Tester par `is`** (`r is OUT_OF_RUNNING`), jamais par `==`.

    `IdunBattle.AI.Utilities.BaseUtility$$.cctor`, LU verbatim :

        statics+0x00 = Fix64.op_Implicit(0)                                  # NEUTRE, pas sentinelle
        statics+0x08 = Fix64.op_Implicit(0x186a0)                            # 100000
        statics+0x10 = Fix64.statics+0x10                                    # MaxValue
        statics+0x18 = Fix64.MinValue / Fix64.FromIntFraction(0xf4241, 0xf4240)
        statics+0x20 = Fix64.statics+0x18                                    # MinValue
        statics+0x28 = Fix64.MinValue / Fix64.FromIntFraction(0xf4242, 0xf4240)
        statics+0x30 = Fix64.op_Implicit(0xffffcfc7)                         # -12345

    `FixMath.NET.Fix64$$.cctor` : `Fix64.statics+0x10` = raw `0x7fffffffffffffff` (MaxValue),
    `+0x18` = raw `0x8000000000000000` (MinValue)."""

    def __new__(cls, valeur: float, nom: str) -> "Fix64Sentinel":
        obj = super().__new__(cls, valeur)
        obj._nom = nom
        return obj

    def __repr__(self) -> str:
        return "<Fix64Sentinel %s = %r>" % (self._nom, float(self))


# Les valeurs que `BaseUtility$$.cctor` publie et que le decideur teste. Les deux EXACTES
# (`Fix64.MaxValue` / `Fix64.MinValue`) sont lues au bit ; les deux DIVISIONS sont approchees
# (cf. la docstring de `Fix64Sentinel`) -- d'ou l'obligation de tester par `is`.
NEUTRAL = 0.0                                                      # statics+0x00 : score NUL, concourt
MUST_DO = Fix64Sentinel(2147483648.0, "MUST_DO")                   # statics+0x10 : Fix64.MaxValue
OUT_OF_RUNNING = Fix64Sentinel(-2147481500.5, "OUT_OF_RUNNING")    # statics+0x18 : HORS COURSE pour CE bucket
HARD_VETO = Fix64Sentinel(-2147483648.0, "HARD_VETO")              # statics+0x20 : Fix64.MinValue
CONDITIONAL_VETO = Fix64Sentinel(-2147479353.0, "CONDITIONAL_VETO")  # statics+0x28
STEP_MARKER = Fix64Sentinel(-12345.0, "STEP_MARKER")               # statics+0x30 : le `yield` de TRAVAIL

#: ⚠ `HARD_VETO` est la MEME valeur que `engine.utilities.move.NO_PATH_UTILITY`, ecrite la-bas en
#: float NU (`-2147483648.0`) avant que ce foyer existe. Les deux disent `statics+0x20` ; on ne
#: touche pas a `move.py` ici (hors perimetre #10022-r3), mais un futur #10022-r2 qui rendra le
#: decideur sensible aux sentinelles devra les CONFONDRE volontairement : le float nu de `move.py`
#: ne passerait AUCUN test `is`.
SENTINELLES = (MUST_DO, OUT_OF_RUNNING, HARD_VETO, CONDITIONAL_VETO)


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
