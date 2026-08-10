"""FireAndRepositionPlaybook (1063, `eldarRanger` << Calandis >>) -- face DECISION, #567-r1.

LA CATEGORIE, MESUREE ET NON DEDUITE DU CTOR
---------------------------------------------
`IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook$$.ctor` appelle
`ComparablePlaybook<T>$$.ctor(this, 0x427)` -- et ce N'EST PAS un indice de categorie. Mesure :
`VexillaMagnificaPlaybook$$.ctor` (0x49f), `HammerOfWrathPlaybook$$.ctor` (0x481),
`StormcallerPlaybook$$.ctor` (0x459) et `UnbreakableDutyPlaybook$$.ctor` (0x425) appellent
**exactement le meme corps**, alors que les quatre sont des NonComparable averes.
`NonComparablePlaybook<T>$$.ctor` est un corps TRIVIAL (`base(id)`) que IL2CPP DEDUPLIQUE avec
celui de `ComparablePlaybook<T>` -- le faux negatif de methode que decrit le CLAUDE.md.

La HIERARCHIE, elle, se lit directement dans `data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1

-- comme `HammerOfWrath`, `VexillaMagnifica`, `UnbreakableDuty` et `GravitonRifle`. C'est la MEME
correction que #487-r1 avait deja du apporter a la fiche `case-487` §7, pour la MEME raison : le
piege se rejoue a chaque tranche qui lit le ctor plutot que la table des classes.

Le second discriminant est la SIGNATURE, lue dans les metadonnees (`frida/methods.tsv`) :

    IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook.EvaluateNonComparable
      -> IdunBattle.AI.BucketSystem.Bucket<IdunBattle.AI.ActionGenerators.UnitAction>
         (caster: IEntity, casterPosition: UnitPosition, abilityState: AbilityState)

soit la MEME que `UnbreakableDutyPlaybook.EvaluateNonComparable`. Et la structure du corps est le
patron NonComparable exact : `Bucket(0, Nullable(MIN))` + `foreach GetEligibleTargetsSelectable` +
`AddAction(GenerateAction(...))`, sans aucune prediction de degat.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                  casterPosition.get_MainTile()):
        u    = Fix64.FromIntFraction(3, 2)                           # 1.5
        pool = TargetsSelector.SelectUniqueUnits(
                   DSLSelectors.Enemies(Caster@+0x48, AllAliveUnits@+0x20, 3), entities, 3)
        u   += Fix64.op_Implicit(GetAverageDistance(entities@+0x40, pool) * 0x14)   # * 20
        u   += GetTileUtility(entities)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, u))

Les DEUX offsets d'`AbilityEntities` sont LUS, pas devines :
`BasePlaybook$$GetEligibleTargetsSelectable` (surcharge `possibleCasterTile`) construit le struct
champ par champ -- `+0x08` et `+0x18` = `caster`, `+0x10` = **l'entite CIBLE**, `+0x30` =
`GetMainTile(cible)`, `+0x38` = `GetTiles(cible)`, `+0x40` = **`possibleCasterTile`**, `+0x48` =
`ToList(possibleCasterTile)`.

⚠ Le parametre de `GetAverageDistance` s'appelle `targetTile` cote natif, mais l'ARGUMENT passe
est `+0x40` = la tuile du **CASTER**, pas celle de la cible. Le nom du parametre ne dit pas ce que
l'appelant y met -- c'est le call-site qui tranche. Consequence de fond : le terme de distance ne
depend PAS de la cible, seulement de la POSITION de cast. Sur une unite dont plusieurs cibles sont
eligibles depuis la meme tuile, l'argmax se joue donc entierement sur l'ordre d'enumeration
(`Bucket$$AddAction` garde le PREMIER au tie) -- exactement comme `BloodyFury`.

`FireAndRepositionPlaybook$$GetAverageDistance(targetTile, otherUnit)` -> `System.Int32` :

    sum = 0
    foreach u in otherUnit:  sum += battleQuery<this+0x28>.<slot 0x6c>(targetTile, u.GetEntity())
    return sum / otherUnit.Count            # division ENTIERE (le type de retour est Int32)

Le slot `0x6c` = **108** = `IBattleQuery.GetDistance` (arite 2), LU dans
`data/symbols/<build>/metadata/interface_slots.tsv` -- 108/109/110 sont trois surcharges homonymes,
c'est le TYPE des arguments qui fixe celle-ci. Toutes deleguent a
`IdunBattle.Core.Services.MovementQuery$$GetDistance` = distance HEXAGONALE minimale entre deux
ENSEMBLES de tuiles, sans pathfinding (foyer du port : `battle_query.get_distance`).

`FireAndRepositionPlaybook$$GetTileUtility(entities)` -> `Fix64` :

    util = utilitiesDatabase<this+0x40>.Get(7 = UtilityType.Tile)
    case = UtilityAttackCase.Base(entities@+0x08 = caster, entities@+0x40 = casterTile,
                                  entities@+0x10 = cible,
                                  Nullable(AbilityOrEffect(UnitExtensions.GetNormalAttackType(...))))
    return util.<slot 5>(case)

C'est le composite **Tile(7)** evalue sur la tuile de CAST -- le meme terme partage que le sweep
MOVE et que les playbooks Comparable, dont le port a deja le foyer UNIQUE
(`engine.playbook.base.tile_utility`). Le recopier ici serait un fork.

BORNES DE PORT, toutes nommees
-------------------------------
* `otherUnit.Count == 0` ferait DIVISER PAR ZERO le natif. Ce regime n'existe pas en pratique (une
  cible eligible EST un ennemi vivant, donc le pool est non vide) ; le port rend `None` plutot que
  de lever -- il n'a pas a reproduire une exception que le natif ne peut pas atteindre.
* `GetDistance` collapse chaque unite sur sa tuile PRINCIPALE (le port ne modelise pas les
  empreintes multi-tuiles) : ecart possible de 1 sur une unite de grande empreinte, borne SUP.
* `GetTileUtility` construit un `UtilityAttackCase` complet (caster, cible, attaque normale) ;
  `tile_utility` ne lui passe que la POSITION. Les feuilles Tile(7) portees lisent la tuile et le
  kit du caster, jamais la cible -- mais si une feuille future lisait `case.Target`, ce port
  divergerait. Ecart NOMME, pas ignore.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.playbook.base import tile_utility

from ._base import _PlanTargetPlaybook, NCContext


class FireAndRepositionPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook$$EvaluateNonComparable` (1063).

    utilite(position) = `3/2` + `20 * (Sigma_e GetDistance(position, e) // #ennemis)`
                        + `Tile(7)(position)`, sur `e` = TOUS les ennemis VIVANTS du caster.

    Le terme dominant recompense la DISTANCE moyenne aux ennemis : Calandis est une tireuse, et
    l'ability lui RENDIT son deplacement (`ResetMovement`) -- le natif la pousse donc a tirer depuis
    la position la plus RECULEE d'ou la cible reste legale. C'est un contraste net avec les
    NonComparable de contact (`BloodyFury` +10 par ennemi ADJACENT), et c'est ce qui rend le port
    falsifiable : sur un banc a plusieurs positions eligibles, inverser le signe deplace l'argmax.
    """
    ABILITY_ID = int(ActiveAbilityType.FireAndReposition)   # 0x427 = 1063
    MIN_UTILITY = 1.0     # `FireAndRepositionPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> statics+0x00
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)
    #: `Fix64.FromIntFraction(3, 2)` -- terme constant, identique pour toute paire.
    _BASE_UTILITY = 1.5
    #: `* 0x14` applique a la distance MOYENNE avant la conversion `Fix64.op_Implicit`.
    _DISTANCE_WEIGHT = 20

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        if tile is None:
            return None
        d = self._average_distance_to_enemies(tile, ctx)
        if d is None:
            return None                      # pool VIDE : le natif diviserait par zero (cf. bornes)
        return self._BASE_UTILITY + float(d * self._DISTANCE_WEIGHT) + tile_utility(ctx, tile)

    @staticmethod
    def _average_distance_to_enemies(tile: tuple, ctx: NCContext):
        """`FireAndRepositionPlaybook$$GetAverageDistance(casterTile, SelectUniqueUnits(Enemies(...)))`
        -- somme des `GetDistance` puis division ENTIERE par le `Count` du pool.

        Le pool est `DSLSelectors$$Enemies(Caster@+0x48, AllAliveUnits@+0x20, 3)` : TOUS les ennemis
        VIVANTS du caster, pas seulement les adjacents et pas seulement la cible. `ctx.epos` en est
        le mirror (`engine.ai.context._enemies` : `not ctrl and alive and pos`), une entree par
        unite -- donc `SelectUniqueUnits` est deja satisfait, il n'y a aucun doublon a retirer.

        ⚠ La division est ENTIERE (`System.Int32` en type de RETOUR natif, et
        `(longlong)sum / (longlong)count` dans le corps) : `//`, jamais `/`. Sur 3 ennemis a
        distances 2/3/3, le natif rend **2**, pas 2.67 -- et le terme vaut donc 40, pas 53.3."""
        pool = list(ctx.epos or [])
        if not pool:
            return None
        total = sum(bq.get_distance([tile], [p]) for p in pool)
        return total // len(pool)
