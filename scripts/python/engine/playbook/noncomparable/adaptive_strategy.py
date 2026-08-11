"""AdaptiveStrategyPlaybook (1005, `necroWarden`) -- face DECISION (#945).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`, jamais deduite
du `.ctor` (qui NOMME `ComparablePlaybook<...>$$.ctor` : corps trivial DEDUPLIQUE). Meme piege,
meme correction que #487-r1 / #572-r2.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.AdaptiveStrategyPlaybook$$EvaluateNonComparable` (0x3ed = 1005) :

    bucket = new Bucket<UnitAction>()                       # ctor 2-ARG : AUCUN minUtility
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                 casterPosition.get_MainTile()):
        sel = DSLSelectors.Friends(
                  Caster@+0x48,
                  DSLSelectors.UnitsWithoutTrait(
                      DSLSelectors.AdjacentUnits(Target@+0x60, unique: 1, sel: 3),
                      0x10 = UnitTrait.Hero, 3),
                  3)
        n = sel.Count(entities)                             # ITargetsSelector slot 2 = `Count`
        if (n > 1)
            bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10,
                                                         Fix64.op_Implicit(n)))

Trois lectures qui ne se devinent pas :

1. **Le Bucket est construit par la surcharge SANS `minUtility`** (deux arguments : `this` + la
   metadata generique), contrairement a `StormOfWrath` / `AlphaWarrior` qui passent
   `(0, Nullable(Fix64(k)))`. Il n'y a donc PAS de `MIN_UTILITY` de `.cctor` -- la classe native
   n'a d'ailleurs aucun `.cctor` (`frida/methods.tsv` : `..ctor` + `EvaluateNonComparable`, deux
   entrees). Le seuil reel est le `if (1 < n)` ECRIT DANS LE CORPS, donc `n >= 2`. Poser
   `MIN_UTILITY = 2` le mirrore exactement (l'utilite EST `n`), et c'est ce que fait ce port ;
   ce qui serait faux serait d'inventer un minimum de `.cctor` inexistant.
2. **L'ancre du sous-selecteur est `Target`, pas `Caster`** -- et c'est un ECART NATIF avec la face
   COMBAT, pas une erreur de lecture. `...AdaptiveStrategyAbility$$ExecuteBehaviour` construit son
   set avec `AdjacentUnits(Caster@+0x48, 1, 3)` puis `GetNonCharacterFriendsSelector`, donc il
   BUFFE les allies adjacents au CASTER ; le playbook, lui, COMPTE les allies adjacents a la
   CIBLE. Les deux corps sont dans le meme binaire a quelques fonctions d'ecart et n'ancrent pas
   au meme champ (`+0x48` vs `+0x60`, le triplet Owner/Caster/Target etant `+0x30`/`+0x48`/`+0x60`
   -- cf. `loki_custom.MassDriverAcceleratorPlaybook`). On mirrore le code, pas l'intention.
3. **`UnitsWithoutTrait(..., 0x10)` = SANS `UnitTrait.Hero`** (0x10 = 16, LU dans
   `data/symbols/<build>/frida/enums.tsv`), ce que confirme le nom du selecteur jumeau de la face
   combat : `...AdaptiveStrategyAbility$$GetNonCharacterFriendsSelector` =
   `Friends(Owner, units) - HeroUnits(units)`. « NonCharacter » = non-heros.

VOIE D'ENUMERATION -- ALLY-TARGETED, donc PAS le plan
------------------------------------------------------
`...AdaptiveStrategyAbility$$.ctor` appelle la surcharge a 7 arguments de
`IdunBattle.Core.Services.TargetingOptions$$.ctor` -- celle ou le litteral EST le masque :
`0x402` = `TargetIsFriendly | TargetMatchesDynamicRule`. Le plan (`computeAttackPlans`) ne boucle
que sur les ENNEMIS, il rendrait donc `rankCount = 0` pour toute paire (1005, x) : un port branche
dessus serait MUET sans erreur. Voie employee, la MEME que `UnbreakableDutyPlaybook` et
`ThriceBlessedConflagrationPlaybook` : `abilityTargets(uid, 1005).fromHere`, mirror de
`GetEligibleTargetsSelectable(caster, casterPosition.MainTile)`.

ECART NOMME (identique a celui des deux playbooks ci-dessus) : `fromHere` n'enumere que depuis
l'ORIGINE, alors que le natif balaie aussi les tuiles de MOVE. L'utilite est ici
position-INDEPENDANTE (elle ne lit que la cible et le board), donc `Bucket$$AddAction`
(remplacement STRICT `>`) garde de toute facon la premiere position -- l'origine. L'ecart ne mord
que sur un caster dont AUCUN allie n'est ciblable sans bouger.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait

from ._base import NCContext, NonComparablePlaybook, _traits

#: `UnitsWithoutTrait(..., 0x10)` -- le trait EXCLU du comptage. Nom LU dans `frida/enums.tsv`
#: (`IdunBattle.Entities.Enum.UnitTrait` : `16=Hero`), jamais l'ordinal nu.
_EXCLUDED_TRAIT = UnitTrait.Hero.name          # 0x10 = 16

#: Le `if (1 < n)` du corps natif : l'action n'est generee que pour `n >= 2`. L'utilite ETANT `n`,
#: le mirror exact du gate est `MIN_UTILITY = 2` (il n'existe aucun `.cctor` sur cette classe).
_MIN_FRIENDS = 2


class AdaptiveStrategyPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.AdaptiveStrategyPlaybook$$EvaluateNonComparable` --
    utilite = nombre d'ALLIES DU CASTER, NON-HEROS, ADJACENTS A LA CIBLE ; gate `>= 2`."""
    ABILITY_ID = int(ActiveAbilityType.AdaptiveStrategy)   # 0x3ed = 1005
    MIN_UTILITY = float(_MIN_FRIENDS)   # `if (1 < n)` INLINE (pas de `.cctor` sur cette classe)
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def _friend_units_non_hero(self, ctx: NCContext) -> list:
        """Les unites que `Friends(Caster, UnitsWithoutTrait(<...>, Hero))` peut retenir, sous la
        forme attendue par `battle_query.count_adjacent_matching` (`{"pos": {"col","row"}}`).

        `Friends(Caster, ...)` filtre par joueur : ce sont les allies du CASTER. Le caster
        LUI-MEME en fait partie -- `AdjacentUnits(Target)` ne soustrait que la CIBLE, et un caster
        adjacent a sa cible est son propre ami -- donc il est re-ajoute a `ctx.fpos` (qui, lui,
        exclut self par construction), a sa position REELLE `ctx.origin` : le sweep de position est
        HYPOTHETIQUE, le board que lit le selecteur ne l'est pas (meme regle que
        `loki_custom.StikkbombPlaybook._adjacent_positions`).

        Substrat des traits : `ctx.obs_units` (`visualId` + `teamId` + `isDead` + `col`/`row`), le
        MEME canal que `UnbreakableDutyPlaybook._dead_imperial_heroes`. Une unite dont le camp ou
        la position n'est pas publie est ignoree -- borne INF nommee, jamais un comptage devine.
        ECARTS du canal, deja nommes dans `_base.occupant_team_by_pos` : les MACHINES OF WAR n'y
        sont pas, et le bridge OFFLINE ne publie que la tuile PRINCIPALE d'une unite."""
        obs = ctx.obs_units or []
        me = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        team = (me or {}).get("teamId")
        out: list = []
        for u in obs:
            if u.get("isDead") or u.get("teamId") is None or team is None:
                continue
            if int(u["teamId"]) != int(team):
                continue                                    # `Friends(Caster, ...)`
            if _EXCLUDED_TRAIT in _traits(u.get("visualId")):
                continue                                    # `UnitsWithoutTrait(..., Hero)`
            c, r = u.get("col"), u.get("row")
            if c is None or r is None:
                continue
            out.append({"pos": {"col": c, "row": r}, "squadId": u.get("squadId")})
        return out

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(Count(Friends(Caster, UnitsWithoutTrait(AdjacentUnits(Target, 1, 3), Hero, 3), 3)))`.

        `AdjacentUnits(T)` = `Units(AdjacentTiles(T), unique, sel) - T` : la cible ne se compte
        JAMAIS elle-meme (elle est a distance 0 de sa propre tuile), et l'enumeration passe par
        `IterateAdjacentTiles` -- donc la liste STOCKEE de voisins ET la porte d'elevation, ce que
        `battle_query.count_adjacent_matching` porte (foyer partage, aucun fork d'adjacence).

        `tile` (la position candidate du caster) N'ENTRE PAS dans la formule : l'ancre est la
        CIBLE. Terme position-INDEPENDANT -> le keep-first du Bucket retient l'origine."""
        tpos = self._pos_of(ctx, target)
        if tpos is None:
            return None
        friends = self._friend_units_non_hero(ctx)
        n = bq.count_adjacent_matching(tpos, friends,
                                       lambda u: u.get("squadId") != target,
                                       ctx.elev_by_pos, bq.neigh_map(ctx))
        return float(n)

    @staticmethod
    def _pos_of(ctx: NCContext, uid):
        u = next((x for x in (ctx.units or []) if x.get("id") == uid), None)
        p = (u or {}).get("pos") if u else None
        if p and p.get("col") is not None:
            return (p["col"], p["row"])
        return None

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour une ability ALLY-TARGETED
        (cf. l'en-tete : masque `0x402`, le plan ne porte aucune cible alliee).

        L'ordre d'enumeration de `fromHere` EST celui du selecteur natif ; `Bucket$$AddAction` ne
        remplace que sur amelioration STRICTE, donc a utilite egale la PREMIERE cible gagne. Le
        `max()` ci-dessous herite cette semantique (Python garde le premier maximum)."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        best = None
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    tid = t.get("targetId")
                    if tid is None:
                        continue
                    util = self.evaluate_non_comparable(ctx.origin, tid, ctx)
                    if util is None or util < self.MIN_UTILITY:
                        continue                      # `if (1 < n)` : rien n'est ajoute au bucket
                    if best is None or util > best[1]:   # STRICT -> keep-first au tie
                        best = (tid, util)
        if best is None:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] AdaptiveStrategy tgt=%s util=%s" % (ctx.uid, best[0], best[1]),
                  file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]
