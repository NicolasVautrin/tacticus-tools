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

import gameconfig as _gc
import hexgeo

from .common import DefaultActiveAbilityPlaybook
from .base import register
from .nonattack import NonAttackComparablePlaybook, register_nonattack
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


class HeavyWarpFlamerPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.HeavyWarpFlamerPlaybook$$CalculateCustomUtility` :

        n = Enumerable.Count(battleQuery.<slot 0x7f>(target, caster, ignoreSteppables: false));
        return GetUtilityValue("HeavyWarpFlamer_LikesAdjacentEnemies") * Fix64.FromInt(n);

    Le slot d'INTERFACE 0x7f est `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(IEntity
    from, TUnit unit, bool ignoreSteppables)` — l'overload qui DERIVE le joueur de
    `OwnerComponent.CurrentPlayerEntityId(unit)`, puis
    `GetUnitsOnTiles(IterateAdjacentTiles(from, onlyEmptyOrSteppable: false, onlyWalkableTiles: true,
    allowTemporary: true), friendsOf: null, enemiesOf: <ennemis du joueur du caster>,
    ignoreSteppables: false)`. `IterateAdjacentTiles(from)` part de
    `IdunBattle.Entities.EntityExtensions$$IterateTiles(from)` : `from` peut donc etre une UNITE (ses
    propres tuiles ne sont jamais dans ses tuiles adjacentes -> la cible ne se compte pas elle-meme).
    Ancre du slot : l'interface `IBattleQuery` est a l'`interfaceOffset` 4 dans la vtable de
    `IdunBattle.Core.Services.BattleQuery` (`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger`
    appelle le slot d'interface 2, et l'index 6 de la vtable est `BattleQuery$$IsMeleeAttack`) ->
    slot 0x7f == index de vtable 0x83.

    => c'est le MEME ensemble que le second terme de `DoomSirenPlaybook` (ennemis du caster adjacents
    a la tuile de la CIBLE), mais LINEAIRE : DoomSiren teste `> 0`, Drachnyen teste `>= 2`, celui-ci
    MULTIPLIE par le compte. Terme INDEPENDANT de la tuile d'attaque, DEPENDANT de la cible :
    il arbitre l'argmax par CIBLE (et l'ability contre les autres actions), pas l'argmax par tuile.
    Mirror : `battle_query.count_adjacent` (meme `IterateAdjacentTiles` + porte d'elevation) sur
    `ctx.epos`.

    Poids `aiUtilities.Default.ActiveAbilities.HeavyWarpFlamer_LikesAdjacentEnemies` = 10.
    Porteur thousSekhetar `Sekhetar Robot` [lineup, ThousandSons] — ABSENT du catalogue de la seed BC
    (unite ajoutee par le build `rnca9r7q6c`), amene en runner par
    `catalog_inject.py --units thousSekhetar` (#92).

    La prediction de degat reste celle du `DefaultActiveAbilityPlaybook` (heritee). Ecart CONNU, hors
    #27 : `IdunBattle.AI.Playbook.Loki.HeavyWarpFlamerPlaybook$$MakeDamagePredictions` passe a
    `GenerateMultiHitAttackPredictions` un nombre de coups DYNAMIQUE
    (`HeavyWarpFlamerAbility$$GetNumTotalHits` = `Sum(Direct(nrOfHits=4),
    Min(GetPersistentData(...), Direct(maxNrOfHits=9) - Direct(nrOfHits=4)))`), la ou le chemin
    generique lit `nrOfHits` seul. Le compteur persistant vaut 0 tant que le stack n'est pas
    alimente -> les deux coincident au debut de bataille, et il ne depend PAS de l'adjacence
    (donc pas de confond avec le levier de l'A/B)."""
    ability_id = int(ActiveAbilityType.HeavyWarpFlamer)  # 1227
    W_KEY = "HeavyWarpFlamer_LikesAdjacentEnemies"

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        tpos = _main_tile_of(ctx, target)
        if tpos is None:
            return 0.0
        n = bq.count_adjacent(tpos, ctx.epos, ctx.elev_by_pos)
        return float(n) * ctx.wt.sub("ActiveAbilities", self.W_KEY)   # 10


class SavageEchoesPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.SavageEchoesPlaybook$$CalculateCustomUtility` :

        cond = SavageEchoesAbility.GetRegenerateCondition(this.ability);   // slot 5 = Evaluate
        return cond.Evaluate(entities) ? Fix64(0)
                                       : GetUtilityValue("SavageEchoes_DislikesAboveHealthPct");

    `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetRegenerateCondition`
    = `DSLFactory.HealthPctIsBelowOrEqual(caster@0x160, ConfigConst(0x4f))`
    = `new IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger(caster, 5, thr)`
    (`IdunBattleLogic.Entities.DSLFactory$$HealthPctIsBelowOrEqual` — le `5` est le `StatType.Health`).
    `0x4f` = `IdunBattle.Configuration.AbilityConstantType.healthPct` -> gameconfig `SavageEchoes.
    constants.healthPct` = 50 (l'enum est resolue depuis `data/symbols/<build>/frida/enums.tsv`,
    aucune valeur codee en dur ici : le seuil est relu du gameconfig).

    C'est la MEME condition DSL que le `If(...)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour`, qui gate le
    `Heal(caster, caster, ConfigVar(0x1d), HealBehaviourOptions.ForRegenerate)` : au-dessus du seuil le
    cast GASPILLE la regeneration -> l'IA la DEPRECIE de `W` (negatif). Terme CONSTANT sur (tuile,
    cible) : il arbitre SavageEchoes CONTRE les autres actions, pas l'argmax intra-ability.

    COMPARAISON EXACTE (`…StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger`) : le natif ne
    passe PAS par `GetStat(Health, part=1)` (le pourcentage ARRONDI qu'utilisent BloodChalice et
    LightOfSanguinius) — il compare le RATIO Fix64 `GetStat(u, stat, 0) / GetStat(u, stat, 2)` au
    seuil `Fix64.Round(thr/100 * 100)/100` (= `thr/100`, normalise a 2 decimales). Mirror : `cur/max
    <= thr/100`, avec `cur` = `ctx.hp_cur_by_id` (part 0 = courant) et `max` = `ctx.hpmax_by_id`
    (part 2 = max EFFECTIF, overlay combatSnapshot). La distinction est MESUREE, pas supposee (cf.
    ci-dessous 1675/3337 = 50.19 %).

    Poids seed-bc : `SavageEchoes_DislikesAboveHealthPct` = -10.
    Porteur bloodTerminator `Cezare` [lineup] — ABSENT du catalogue de la seed BC (unite non encore
    possedee) mais amene en runner par `catalog_inject.py --units bloodTerminator` (#92).

    Live (#27 tranche 3, `probe_27_3_savage_ab.py`, board MC1_67, `--hp-target 60000`) : caster en
    (4,8) et cible tauCrisis en (5,8) FIGES, seul le PV% du CASTER varie.

      | PV% caster | pairUtility(69) natif | pairUtility(1230) natif | choix natif |
      |---|---|---|---|
      | 100 % (3300/3300) | 15.892803575843573 | 24.10252990666777 | **69** |
      | 51.1 % (1738/3400) | 15.892803575843573 | 24.10252990666777 | **69** |
      | 50.68 % (1708/3370) | 15.892803575843573 | 24.10252990666777 | **69** |
      | 50.19 % (1675/3337) | 15.892803575843573 | 24.10252990666777 | **69** |
      | 49.64 % (1638/3300) | 15.892803575843573 | 24.10252990666777 | **1230** |

    Les DEUX utilites de paire natives sont BIT-IDENTIQUES dans tous les bras -> le heal
    `ForRegenerate` n'entre PAS dans la prediction du playbook, le confond est MESURE et NUL. Le
    basculement s'explique donc uniquement par le custom. Encadrement (custom(69) = +1 constant,
    meme tuile donc terme Tile identique) : `15.8928 + 1 > 24.1025 + C_haut` => **C_haut < -7.2097** ;
    `24.1025 + C_bas > 15.8928 + 1` => **C_bas > -7.2097**. Le port rend -10 et 0.
    Le couple 50.19 % (natif = W) / 49.64 % (natif = 0) EXCLUT un pourcentage arrondi
    (`round(50.19) = 50 <= 50` aurait bascule) : c'est bien le ratio exact."""
    ability_id = int(ActiveAbilityType.SavageEchoes)  # 1230
    W_KEY = "SavageEchoes_DislikesAboveHealthPct"
    CONFIG_ID = "SavageEchoes"          # entree gameconfig portant `constants.healthPct`

    def _regenerate_condition(self, ctx) -> bool | None:
        """`SavageEchoesAbility.GetRegenerateCondition(...).Evaluate(entities)` = ratio PV du CASTER
        <= `constants.healthPct` / 100. None = stats du caster illisibles (condition non evaluable)."""
        cur = ctx.hp_cur_by_id.get(ctx.uid)
        mx = ctx.hpmax_by_id.get(ctx.uid)
        if cur is None or not mx:
            return None
        thr = (_gc.ability(self.CONFIG_ID) or {}).get("constants") or {}
        pct = thr.get("healthPct")
        if pct is None:
            return None
        return (float(cur) / float(mx)) <= (float(pct) / 100.0)

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        cond = self._regenerate_condition(ctx)
        if cond is None or cond:
            return 0.0                                        # Fix64(0)
        return ctx.wt.sub("ActiveAbilities", self.W_KEY)       # -10


class ChronometronPlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ChronometronPlaybook$$CalculateCustomUtility` :

        entities = new AbilityEntities(owner: caster, caster: caster, target: target,
                                       <tous les slots de POSITION zero-initialises>);
        sel = ChronometronAbility.GetAffectedEnemies(this.ability);      // slot d'interface 0x18 = Count
        n   = sel.Count(entities);
        return GetUtilityValue("Chronometron_AffectedEnemies") * Fix64.FromInt(n);

    et `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$GetAffectedEnemies` :

        DSLSelectors.SurroundingEnemies( <selecteur d'UNITE>,
                                         AbilityConfiguration.GetNumberConstant(0x16 = range),
                                         unique: 1, unitSelectionType: 3 )

    C'est **le MEME artefact natif que la face COMBAT** : `...ChronometronAbility$$ExecuteBehaviour`
    re-inline exactement le meme appel (memes 5 arguments) pour alimenter son `Foreach`. Un seul
    artefact, un seul port — le mirror decision `battle_query.surrounding_enemies_in_range` et le
    mirror combat `necrons.chronometron_affected_enemies` decrivent le meme ensemble.

    SURCHARGE EXACTE — c'est la 5-args, dont le 2e parametre est nomme `unit` (une ENTITE), PAS la
    6-args `(unit, unitTile, range, ...)`. Consequence : le centre est la MainTile REELLE du caster
    (`EntityExtensions.IterateTiles`), **pas** la tuile candidate du balayage IA — et l'`AbilityEntities`
    construit ici le confirme, ses slots de position sont ZERO-INITIALISES. Le terme est donc CONSTANT
    sur (tuile, cible) : il arbitre Chronometron CONTRE les autres actions, jamais l'argmax intra-ability.
    (Meme quirk que `SavageEchoesAbility$$GetDamage`, confronte live en #216 : le bonus photographie
    l'etat AVANT le deplacement.)

    Pas de `Unobscured` dans cette surcharge -> ne PAS reutiliser `battle_query.surrounding_enemies`
    (qui, lui, mirroir le `Unobscured(SurroundingEnemies(...))` de GauntletsOfUltramar).

    ROUTE : l'ability n'a **pas de `damageProfile`** (`constants` = `{range, nrOfRounds}`) — elle
    n'atteint donc jamais `_best_attack`. Elle passe par `playbook/nonattack.py` (verrou 2 de #27),
    ou `u = custom` et `u_full = u + Tile(7)`. `ShouldExecute` (slot +0x328) rend `true` : MESURE au
    slot de vtable (`probe_27_4b_chronometron_vtable.py`), pas suppose.

    Poids `aiUtilities.Default.ActiveAbilities.Chronometron_AffectedEnemies` = 10 (resolu a
    l'execution depuis la BC, jamais code en dur). `range` = `Chronometron.constants.range` = 2.
    Porteur necroChronomancer « Thothmek » [lineup, Necrons] — hors du catalogue de la seed BC, amene
    par `catalog_inject.py --units necroChronomancer` (#92), comme le fait deja `probe_116_necrons.py`.
    La face COMBAT est portee et validee (`engine/runner/abilities/necrons.py::ChronometronAbility`,
    #116) : ce port-ci ne couvre que la face DECISION."""

    ability_id = int(ActiveAbilityType.Chronometron)  # 1226
    W_KEY = "Chronometron_AffectedEnemies"
    CONFIG_ID = "Chronometron"

    def _range(self) -> int:
        """`AbilityConfiguration.GetNumberConstant(0x16)` = `Chronometron.constants.range` — la MEME
        constante que celle lue par la face COMBAT (`ChronometronAbility._params`) et que le
        `TargetingRange` `useRangeFromConfig` du masque de ciblage."""
        c = (_gc.ability(self.CONFIG_ID) or {}).get("constants") or {}
        r = c.get("range")
        return int(r) if r is not None else 1

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        if ctx.origin is None:
            return 0.0                       # pas de MainTile lisible -> selecteur non evaluable
        n = len(bq.surrounding_enemies_in_range(ctx.origin, ctx.epos, self._range()))
        return float(n) * ctx.wt.sub("ActiveAbilities", self.W_KEY)     # 10

    def is_caster_added(self, ctx, caster_tile) -> bool:
        """`TargetingQuery$$GetCasterNotAddedReason` pour le masque de
        `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$.ctor` (RE-lu et deja
        porte dans `runner/abilities/necrons.py` : `isSelfCasting = 1`, `Rules = TargetIsEnemy |
        AllowObscured*`, `TargetingRange` = `useRangeFromConfig`). Branche self-cast du natif :
        `GetValidTargets(caster, casterTile, options, true, true)` vide -> refus `0x800`, le caster
        n'entre pas dans `GetEligibleTargetsEntities` et aucune action n'est generee DEPUIS CETTE
        TUILE. Mirror : au moins un ennemi vivant a `<= range` de la tuile candidate.

        Les regles fines de la cascade (`GetInvalidTargetReason`) ne sont pas rejouees ici — le masque
        est permissif (`AllowObscuredTargetBy*`) et le port reste un SUR-ENSEMBLE, degradation
        assumee et bornee a cette ability."""
        r = self._range()
        return any(hexgeo.distance(caster_tile, e) <= r for e in (ctx.epos or []))


# --- Registry : dispatch par ability_id via get_playbook_or_default (base.REGISTRY) ---
#
# SorcerousFacade (1100) N'EST PAS ENREGISTREE, et c'est DELIBERE (#27 tranche 3).
# `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$CalculateCustomUtility` vaut
# `EvaluateMovement(UtilityMovementCase(unit, GetMainTile(TARGET), null, ...))` moins la meme chose sur
# la tuile d'attaque — soit, apres reduction du composite a sa feuille Tile(7) (RE relue en tranche 2 :
# `UtilityMovementCase.ClosestEnemy == null` desarme `MinDistanceToClosestEnemyUtility`),
# `tile_utility(tuile de la CIBLE) - tile_utility(tuile d'attaque)`. Mais le natif ne l'evalue JAMAIS
# sur un ennemi : `SorcerousFacadeAbility` cible un ALLIE Psyker (echange de positions). MESURE live
# (#27-3, runner arene, thousTzaangor + thousSorcerer + 3 ennemis) : `abilityTargets` natif rend pour
# 1100 exactement UNE cible legale, l'ALLIE (`targetId` = le Psyker ami), jamais un ennemi. Cote
# moteur, `state_bridge._is_attack_ability` route 1100 vers `_best_attack` avec des cibles ENNEMIES
# (`constants.damageProfile = Psychic`), et le terme y prenait des valeurs NON NULLES et NON
# CONSTANTES (-10.0 / -25.0 / +20.0 sur les 3 ennemis du meme montage) : un biais de +-45 applique a
# une action que le natif refuse. Le verrou reel est la ROUTE DE CIBLAGE ALLIE de 1100, pas la
# formule ; tant qu'elle n'existe pas, le terme reste NON VALIDABLE et donc non porte (le custom
# retombe sur la base `ComparablePlaybook<T>` = Fix64(0)). cf. docs/rl/case-27-custom-utility.md.
def _register_all() -> None:
    for cls in (ArmoriumCherubPlaybook, LightOfSanguiniusPlaybook,
                HeraldOfTheApocalypsePlaybook, DrachnyenPlaybook,
                DoomSirenPlaybook, SavageEchoesPlaybook,
                HeavyWarpFlamerPlaybook):
        register(cls())
    # Route NON-ATTAQUE (verrou 2, #27-4b) : l'ability n'a pas de `damageProfile`, elle n'atteint
    # jamais `_best_attack` -> registre + route dedies (`playbook/nonattack.py`).
    for cls in (ChronometronPlaybook,):
        register_nonattack(cls())


_register_all()
