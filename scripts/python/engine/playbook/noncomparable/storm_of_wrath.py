"""StormOfWrathPlaybook (1019, `ultraTigurius`) -- face DECISION (#945).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv` (le `.ctor`
NOMME `ComparablePlaybook<...>$$.ctor`, corps trivial DEDUPLIQUE : meme piege que #487-r1).

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.StormOfWrathPlaybook$$EvaluateNonComparable` (0x3fb = 1019) :

    bucket = new Bucket<UnitAction>(0, Nullable(Fix64.op_Implicit(2)))     # minUtility INLINE = 2
    foreach e in BasePlaybook.GetEligibleTargetsEntities(caster, casterPosition.get_MainTile()):
        n = battleQuery.<slot itf 16>(e, onlyFriends: true, additionalCondition: null).Count
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, e, Fix64.op_Implicit(n)))

Deux lectures qui ne se devinent pas :

1. **Le `minUtility` est INLINE dans la methode, pas dans un `.cctor`.** La classe native n'a que
   deux methodes (`..ctor` + `EvaluateNonComparable`, `frida/methods.tsv`) : le `Fix64(2)` est
   construit a chaque appel et emballe dans le `Nullable<Fix64>` passe a la surcharge 3-ARG de
   `IdunBattle.AI.BucketSystem.Bucket<T>$$.ctor`. `MIN_UTILITY = 2` est donc LU, pas suppose --
   et il est LOAD-BEARING : une chaine d'UNE seule unite (la cible seule) vaut 1 et n'est JAMAIS
   proposee.
2. **Le slot 16 d'`IBattleQuery` est `GetChainedUnits`** (`metadata/interface_slots.tsv` :
   `IBattleQuery 16 GetChainedUnits 3`), et son `onlyFriends` vaut `true` -- le litteral `1` du
   call-site. Ce n'est donc PAS un comptage d'ennemis autour de la cible : c'est la taille de la
   COMPOSANTE CONNEXE d'unites AMIES DE PROCHE EN PROCHE a partir de la cible, exactement ce que
   propage un eclair en chaine.

`IdunBattle.Core.Services.BattleQuery$$GetChainedUnits` = `GetChainedUnitsInternal(unit,
new OrderedSet(), onlyFriends, additionalCondition)`, et l'interne, VERBATIM :

    tile = EntityExtensions.GetMainTileEntity(unit, state)
    adj  = GetAdjacentTiles(tile, null, onlyWalkable: true, allowTemporary: true)
    adj.Add(tile)                              # <- LA TUILE DE `unit` EST DANS L'ENUMERATION
    foreach t in adj:
        u = UnitExtensions.GetUnit(t, state);  if (u == null) continue
        if (alreadyChained.Contains(u)) continue
        if (onlyFriends && !UnitExtensions.IsFriend(u, unit, state)) continue
        if (additionalCondition != null && !additionalCondition(t)) continue
        alreadyChained.Add(u)
        GetChainedUnitsInternal(u, alreadyChained, onlyFriends, additionalCondition)   # RECURSION
    return alreadyChained

⚠ `adj.Add(tile)` fait que la CIBLE ELLE-MEME entre dans le set des le premier niveau
(`IsFriend(cible, cible)` est vrai). Le compte inclut donc la cible : une cible isolee vaut **1**,
pas 0 -- et c'est ce qui donne son sens au seuil 2 (« il faut au moins un rebond »).

BORNES DE PORT, nommees
------------------------
* `IsFriend` compare le joueur COURANT : le substrat est `ctx.obs_units[].teamId` (l'equipe
  courante, celle que suit un controle mental), jamais `playerId` -- meme discriminant que
  `_base.occupant_team_by_pos`, dont la docstring porte l'avertissement.
* L'adjacence passe par `battle_query.is_adjacent` (liste STOCKEE de voisins + porte d'elevation
  d'`IterateAdjacentTiles`), foyer partage : aucun fork.
* `additionalCondition` est `null` au call-site -- rien a porter.
* Les ecarts du canal `obs_units` sont ceux deja nommes dans `_base.occupant_team_by_pos` : les
  MACHINES OF WAR n'y figurent pas, et le bridge OFFLINE ne publie que la tuile PRINCIPALE. Les
  deux SOUS-declarent l'occupation, donc bornent le compte par en dessous.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, occupant_ids_by_pos

#: `Bucket<T>$$.ctor(0, Nullable(Fix64.op_Implicit(2)))` -- litteral LU dans
#: `StormOfWrathPlaybook$$EvaluateNonComparable`, pas un `.cctor` (la classe n'en a pas).
_MIN_CHAINED = 2


class StormOfWrathPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.StormOfWrathPlaybook$$EvaluateNonComparable` --
    utilite = |chaine d'unites amies de la cible, cible COMPRISE| ; MIN_UTILITY = 2."""
    ABILITY_ID = int(ActiveAbilityType.StormOfWrath)   # 0x3fb = 1019
    MIN_UTILITY = float(_MIN_CHAINED)
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(GetChainedUnits(target, onlyFriends: true, additionalCondition: null).Count)`.

        Terme position-INDEPENDANT (le `tile` candidat du caster n'entre pas dans la formule) :
        `Bucket$$AddAction` ne remplacant que sur amelioration STRICTE, le caster reste donc en
        place des qu'une cible atteignable depuis l'origine atteint le maximum."""
        return float(self._chained_count(ctx, target))

    @staticmethod
    def _chained_count(ctx: NCContext, target) -> int:
        """`BattleQuery$$GetChainedUnitsInternal` -- parcours en profondeur, `alreadyChained` en
        guise de marqueur, la tuile de l'unite courante FAISANT PARTIE de son propre voisinage.

        Le corps vit dans `engine.battle_query.get_chained_units` (FOYER PARTAGE) depuis que
        `KissOfDeathPlaybook` (1108) a ete lu : son `EvaluateNonComparable` invoque le MEME slot
        16 d'`IBattleQuery` avec les MEMES litteraux `(cible, 1, 0)`, et le natif n'a qu'un corps
        pour les deux. Cible absente du canal -> 0 (borne INF assumee : le port ne fabrique pas
        une chaine)."""
        occ, team_by_id = occupant_ids_by_pos(ctx)
        return len(bq.get_chained_units(target, occ, team_by_id,
                                        elev_by_pos=ctx.elev_by_pos, neigh_by_pos=bq.neigh_map(ctx),
                                        only_friends=True))   # `onlyFriends` = litteral `1`

    def damage_predictions(self, tile, target, ctx: NCContext) -> list:
        """AUCUNE prediction de degat n'est construite : `StormOfWrathPlaybook` ne declare que
        `..ctor` et `EvaluateNonComparable` (`frida/methods.tsv`), donc ni `MakeDamagePredictions`
        ni gate `WillNormalAttackKill`. La sequence que l'oracle `ncPlaybookPredict` voit est
        VIDE -- ce qui est un resultat, pas un defaut d'implementation."""
        return []
