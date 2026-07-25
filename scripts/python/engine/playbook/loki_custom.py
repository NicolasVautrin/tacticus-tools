"""Overrides `CalculateCustomUtility` par-ability (namespace `IdunBattle.AI.Playbook[.Loki]`) — #27.

Terme d'ACTION `ComparablePlaybook<T>.IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility` (base = `Fix64(0)`, base.py),
ajoute PAR-DESSUS `u_full` dans `_best_attack` (`u_action = u_full + calculate_custom_utility`,
action_generators.py). Chaque sous-classe ci-dessous OVERRIDE ce terme, mirror 1:1 du corps natif (VA
citee). La prediction de degat reste celle du `DefaultActiveAbilityPlaybook` (heritee) : #27 ne porte
QUE le terme custom, pas la prediction (deja assuree par `prediction.py`).

PERIMETRE (cf. docs/rl/case-27-custom-utility.md) : seuls les overrides dont l'ensemble compte se
calcule FIDELEMENT depuis les primitives `ctx` deja portees (adjacence `battle_query.count_adjacent` =
port du selecteur DSL `AdjacentTiles->Units`, cf. sa docstring ; iteration directe d'unites ; portee
d'arme depuis la tuile courante ; constante) sont portes ici. Les overrides dependant d'un SOUS-SYSTEME
non porte (evaluateur DSL de formes TilesInTriangleShape/UnitsWithTrait/chain ;
`GenerateMultiHitAttackPredictions` ; utilite de deplacement
`UtilityMovementCase`/`GetTargetUtilityDiffOnDisplace`) restent en residu (doc #27).

POSITION-DEPENDANCE : le natif somme le custom DANS `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`, donc AVANT
l'argmax par tuile de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal`. `ai/action_generators._best_attack` compare donc
`u_full + custom(tuile)` pendant le sweep de tuiles — sans quoi un terme par-tuile (Drachnyen) serait
inerte. Constant pour les autres overrides -> neutre.

Poids : resolus a l'execution via `ctx.wt.sub("ActiveAbilities", <key>)` (jamais hardcodes) — meme voie
que bespoke.py ; valeurs de la seed-bc citees en commentaire pour lecture.
"""
from __future__ import annotations

import hexgeo

from .common import DefaultActiveAbilityPlaybook
from .base import register, tile_utility
from .. import battle_query as bq
from ..entities.active_ability_type import ActiveAbilityType
from ..utilities.damage import will_be_overkill


class _CustomOnlyPlaybook(DefaultActiveAbilityPlaybook):
    """Base commune : HERITE la prediction de degat generique (`DefaultActiveAbilityPlaybook.
    make_damage_predictions` -> `prediction.make_damage_predictions`) et n'override QUE
    `calculate_custom_utility`. `ability_id` fixe la cle du registry (dispatch `get_playbook_or_default`)."""
    is_normal_attack = False


class ArmoriumCherubPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.ArmoriumCherubPlaybook$$CalculateCustomUtility`
    = `Fix64.FromInt(1)` CONSTANT (aucune garde, aucun poids). Porteur adeptRetributor 'Vindicta'
    [lineup]. Bonus d'action +1 identique au patron NormalAttack (common.py) : ArmoriumCherub bat
    tout actif Comparable a Delta(pair+tile) < 1, et EGALISE l'attaque normale (elle aussi +1)."""
    ability_id = int(ActiveAbilityType.ArmoriumCherub)  # 1014

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        return 1.0


class LightOfSanguiniusPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.LightOfSanguiniusPlaybook$$CalculateCustomUtility`
    = `count(units du JOUEUR-du-caster a 100% PV) * W`.
    Natif : `GetOriginalPlayer(caster)` -> ses units (`FUN_180004fd0(0x88,...)`), pour chacune
    `GetStat(Health=5, part=1)==100` (PV% == plein) -> +W. Mirror direct sur `ctx` : unites de la
    MEME equipe que le caster, VIVANTES, PV% (round(cur/max*100)) == 100. W =
    `Utilities.Default.ActiveAbilities.LightOfSanguinius_FullHealthFriendlyUnits` = -10 (NEGATIF :
    l'IA EVITE l'ability quand tous les allies sont pleins). Porteur bloodDante 'Dante' [lineup].
    Terme CONSTANT sur les cibles (depend du caster) -> biaise la magnitude de l'ability, pas l'argmax cible."""
    ability_id = int(ActiveAbilityType.LightOfSanguinius)  # 1177
    W_KEY = "LightOfSanguinius_FullHealthFriendlyUnits"

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        me = ctx.me
        if me is None:
            return 0.0
        team = me.get("team")
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        n = 0
        for u in ctx.units:
            if u.get("team") != team or not u.get("alive"):
                continue
            ob = obs_by_sq.get(u.get("id")) or {}
            mx = int(ob.get("hpMax") or 0)
            cur = int(ob.get("hp") or 0)
            if mx > 0 and round(cur / mx * 100) == 100:      # GetStat(Health,part1) == 100
                n += 1
        w = ctx.wt.sub("ActiveAbilities", self.W_KEY)        # -10
        return float(n) * w


def _all_normal_attack_targets(ctx, unit: dict) -> list:
    """`IdunBattle.AI.Playbook.BasePlaybook$$GetAllNormalAttackTargets` = `battleQuery.<0x44>(unit,
    GetNormalAttackType(unit))` -> `(List<TUnit> Targets, Dictionary<Tile, List<TUnit>> ByTile)` ;
    `Targets` (champ +0x10) = les ennemis attaquables a l'attaque NORMALE depuis les tuiles ou
    l'unite peut se tenir. Le jeu ne calcule les tuiles de deplacement QUE pour le joueur ACTIF,
    d'ou deux regimes MESURES live (probe #27 tranche 1, runner 1304) :

    - unite ACTIVE (le caster) -> tuiles de move incluses : mirror = les cibles rankees de
      l'attaque normale dans `ctx.plans` (`attackPlans`, deja movement-inclusives ; meme
      correspondance que `noncomparable.hammer_of_wrath._enemy_killed_by_normal_attack`) ;
    - unite NON active (un ennemi) -> depuis SA tuile courante seulement : mirror = unites de
      l'equipe adverse vivantes a distance <= portee d'arme (`state_bridge._max_attack_range`).
      Live : la bascule du terme Herald s'est produite EXACTEMENT a la portee d'arme de
      l'ennemi (astraOrdnance r3 -> d<=3 ; blackTerminator r1 -> d=1), pas au move+portee.

    NON MODELISE : les regles de ciblage fines (LOS/obscurcissement, taunt) — l'ensemble rendu
    est une borne SUPERIEURE sur terrain degage (le cas mesure)."""
    from ..ai.state_bridge import _max_attack_range        # lazy : evite un cycle d'import
    if unit.get("id") == ctx.uid:
        out = []
        for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or []):
            if ev.get("abilityId") in ctx.normal_ids and ev.get("rankCount"):
                tid = ev.get("targetId")
                if tid is not None and tid not in out:
                    out.append(tid)
        return out
    p = unit.get("pos") or {}
    if p.get("col") is None:
        return []
    rng = _max_attack_range(unit.get("visualId") or "")
    src = (p["col"], p["row"])
    out = []
    for u in (ctx.units or []):
        if not u.get("alive") or u.get("team") == unit.get("team"):
            continue
        q = u.get("pos") or {}
        if q.get("col") is None:
            continue
        if hexgeo.distance(src, (q["col"], q["row"])) <= rng:
            out.append(u.get("id"))
    return out


class HeraldOfTheApocalypsePlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$CalculateCustomUtility` :

        foreach (e in GetAllNormalAttackTargets(caster).Targets)
            if (EnemyCouldBeDamagedWithNormalAttack(e)) return Fix64(0);
        return GetUtilityValue("HeraldOfTheApocalypse_CannotKillEnemy");

    `IdunBattle.AI.Playbook.BasePlaybook$$EnemyCouldBeDamagedWithNormalAttack` = `GetAllNormalAttackTargets(e).Targets.Count > 0`
    (l'ennemi peut-il lui-meme frapper quelqu'un). La boucle rend W DES QUE la liste du caster est
    vide OU qu'aucun ennemi atteignable n'est lui-meme menacant. Terme CONSTANT sur (tuile, cible) :
    il ne biaise pas l'argmax intra-ability, il arbitre Herald CONTRE les autres actions.

    Porteur blackHaarken `Haarken` [hero, present dans `rl_duel --list-pool`].
    Live (#27 tranche 1) : A/B causal a geometrie Haarken/ennemi FIGEE, seul un appat allie bouge
    -> le natif bascule Herald (appat hors portee de l'ennemi) <-> attaque normale (appat a portee),
    utilites de PAIRE natives bit-identiques dans les deux bras (8.019551052711904 / 0.018102815374732018
    -> pas de confond de prediction). Borne mesuree du terme : C > 34.22 (runner 1304, delta d'action
    offline 34.2159 franchi par le natif) ; W = 50 dans la seed-bc."""
    ability_id = int(ActiveAbilityType.HeraldOfTheApocalypse)  # 1020
    W_KEY = "HeraldOfTheApocalypse_CannotKillEnemy"

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        by_id = {u.get("id"): u for u in (ctx.units or [])}
        for eid in _all_normal_attack_targets(ctx, ctx.me or {}):
            e = by_id.get(eid)
            if e is not None and _all_normal_attack_targets(ctx, e):
                return 0.0                                    # EnemyCouldBeDamagedWithNormalAttack
        return ctx.wt.sub("ActiveAbilities", self.W_KEY)       # 50


class DrachnyenPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.DrachnyenPlaybook$$CalculateCustomUtility` :

        n = Enumerable.Count(battleQuery.<0x7d>(casterPosition, GetCurrentOwnerEntityId(caster)), pred);
        return n < 2 ? Fix64(0) : GetUtilityValue("Drachnyen_MultipleAdjacentUnits");

    L'`ownerEntityId` passe a la requete la scope aux ENNEMIS du caster (`GetAdjacentEnemies`) ;
    la position passee est celle du `UnitPosition` de `CalculateActionUtility`, c.-a-d. la TUILE
    D'ATTAQUE candidate -> terme POSITION-DEPENDANT (il doit entrer dans l'argmax par tuile, cf.
    `ai/action_generators._best_attack`). Mirror : `battle_query.count_adjacent` (meme
    `IterateAdjacentTiles` + porte d'elevation) sur `ctx.epos` (positions ennemies completes).

    Porteur blackAbaddon `Abaddon` [hero, present dans `rl_duel --list-pool`].
    Live (#27 tranche 1), confond de PAIRE neutralise (Drachnyen fixe les PV du caster a 4729 ->
    `--hp-player 4729` rend le set-health neutre, paire native = 0) :
    - 1 ennemi adjacent a la tuile d'attaque -> natif = attaque NORMALE (runner 1373 : 54.139 vs 50.000+C)
    - 2 ennemis adjacents a la tuile d'attaque, caster LOIN (0 adjacent a sa tuile courante)
      -> natif = DRACHNYEN => le count porte bien sur la TUILE D'ATTAQUE, et C > 4.139
    - allie adjacent (au lieu d'un ennemi) -> natif reste sur la normale => les ALLIES NE COMPTENT PAS
    - encadrement de la magnitude : C > 5.547 (runner 1363) et C < 10.716 (runner 1335) -> W = 10."""
    ability_id = int(ActiveAbilityType.Drachnyen)  # 1029
    W_KEY = "Drachnyen_MultipleAdjacentUnits"

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        n = bq.count_adjacent(caster_tile, ctx.epos, ctx.elev_by_pos)
        if n < 2:
            return 0.0
        return ctx.wt.sub("ActiveAbilities", self.W_KEY)       # 10


def _main_tile_of(ctx, entity_id):
    """`IdunBattle.Entities.EntityExtensions$$GetMainTile` / `GetTiles(e).First()` de l'entite `entity_id`
    -> `(col, row)` ou None (entite absente/hors plateau). Unites mono-tuile : `GetTiles().First()`
    == `GetMainTile()` (les seules multi-tuiles sont les plateformes de MoW, jamais cibles ici)."""
    for u in (ctx.units or []):
        if u.get("id") == entity_id:
            p = u.get("pos") or {}
            if p.get("col") is None:
                return None
            return (p["col"], p["row"])
    return None


class DoomSirenPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.DoomSirenPlaybook$$CalculateCustomUtility` :

        u = Fix64(0);
        foreach (p in MakeDamagePredictions(unit, position, target))      // vtable +0x358
            if (p.Prediction.WillBeOverkill()) u += GetUtilityValue("DoomSiren_DefinitelyOverkill");
        if (Enumerable.Count(battleQuery.<0x7f>(GetTiles(target).First(), unit)) > 0)
            u += GetUtilityValue("DoomSiren_TargetHasAdjacentEnemy");
        return u;

    Le slot 0x7f est l'overload `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(Tile, TUnit)`
    (`OwnerComponent.CurrentPlayerEntityId(unit)` -> filtre ennemis, puis `GetAdjacentUnits(tile)`) :
    le compte des ENNEMIS DU CASTER adjacents a la TUILE DE LA CIBLE — c'est-a-dire « l'AoE va-t-elle
    toucher quelqu'un d'autre ? ». Mirror : `battle_query.count_adjacent` (meme `IterateAdjacentTiles`
    + porte d'elevation) sur `ctx.epos`. La cible elle-meme est a distance 0 -> jamais comptee.
    Terme INDEPENDANT de la tuile d'attaque, DEPENDANT de la cible.

    Le premier terme reutilise la MEME `MakeDamagePredictions` que `calculate_action_utility`
    (`IdunBattle.AI.Playbook.Loki.DoomSirenPlaybook$$MakeDamagePredictions` = cible principale +
    jusqu'a `GetNumberConstant(0x78)`=`nrOfUnits`=2 ennemis adjacents a la cible, puis
    `GenerateMultiHitAttackPredictions`) -> le compte d'overkills porte sur cible + AoE.
    `WillBeOverkill` = `engine.utilities.damage.will_be_overkill` (meme code que la feuille
    `OverkillUnitUtility`).

    Poids seed-bc : `DoomSiren_DefinitelyOverkill` = 40, `DoomSiren_TargetHasAdjacentEnemy` = 50.
    Porteur emperKakophonist `Adamatar` [hero, present dans `rl_duel --list-pool`]."""
    ability_id = int(ActiveAbilityType.DoomSiren)  # 1199
    W_OVERKILL = "DoomSiren_DefinitelyOverkill"
    W_ADJACENT = "DoomSiren_TargetHasAdjacentEnemy"

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        u = 0.0
        w_ok = ctx.wt.sub("ActiveAbilities", self.W_OVERKILL)          # 40
        for ev in (self.make_damage_predictions(ctx, caster_tile, target, ability_id) or []):
            if will_be_overkill(ev.composite_fields()):
                u += w_ok
        tpos = _main_tile_of(ctx, target)
        if tpos is not None and bq.count_adjacent(tpos, ctx.epos, ctx.elev_by_pos) > 0:
            u += ctx.wt.sub("ActiveAbilities", self.W_ADJACENT)        # 50
        return u


class SorcerousFacadePlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$CalculateCustomUtility` :

        u1 = services[7].EvaluateMovement(new UtilityMovementCase(unit, GetMainTile(target), null, null, null));
        u2 = services[7].EvaluateMovement(new UtilityMovementCase(unit, position,             null, null, null));
        return u1 - u2;

    SorcerousFacade ECHANGE le caster et sa cible : le terme note « combien il est bon d'etre LA OU
    EST LA CIBLE » moins « combien il est bon d'etre sur la tuile d'attaque ». Terme
    POSITION-DEPENDANT (il entre dans l'argmax par tuile de `_best_attack`).

    RE DECISIF — le `UtilityMovementCase` est construit avec **ClosestEnemy = null** (3e argument du
    ctor `IdunBattle.AI.Utilities.UtilityMovementCase$$.ctor`, champ @0x20 ; meme forme que
    `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility`).
    Or `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
    rend `Fix64(0)` des que `case.ClosestEnemy == null` (3e garde, avant tout `GetMinDistanceToEnemy`).
    => la feuille MinDistanceToClosestEnemy(16) du composite est INERTE sur ce chemin, et le composite
    de mouvement se REDUIT a sa feuille Tile(7). Mirror exact = `base.tile_utility` (le MEME
    `tile_composite` que le sweep move et que le terme Tile de `CalculateActionUtility`).

    Consequence : sur terrain PLAT et sans effets de tuile, le terme vaut 0 ; il devient decisif des
    que l'elevation / les effets de tuile / la feuille TriggeredAbilities(2) different entre la tuile
    de la cible et la tuile d'attaque. Aucun poids `ActiveAbilities` dedie (le terme est une DIFFERENCE
    d'utilites de tuile, ponderees par la categorie Tile de la BC).

    Porteur thousTzaangor `Tzaangor Shaman` [hero, present dans `rl_duel --list-pool`].
    (`IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$ShouldExecute` — gate supplementaire
    `!WillNormalAttackKill` + comparaison aux tuiles de deplacement — n'est PAS porte ici : #27 ne
    couvre que le terme custom.)"""
    ability_id = int(ActiveAbilityType.SorcerousFacade)  # 1100

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        tpos = _main_tile_of(ctx, target)
        if tpos is None:
            return 0.0
        return tile_utility(ctx, tpos) - tile_utility(ctx, caster_tile)


# --- Registry : dispatch par ability_id via get_playbook_or_default (base.REGISTRY) ---
def _register_all() -> None:
    for cls in (ArmoriumCherubPlaybook, LightOfSanguiniusPlaybook,
                HeraldOfTheApocalypsePlaybook, DrachnyenPlaybook,
                DoomSirenPlaybook, SorcerousFacadePlaybook):
        register(cls())


_register_all()
