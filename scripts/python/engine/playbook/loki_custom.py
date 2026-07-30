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

from . import prediction
from .common import DefaultActiveAbilityPlaybook
from .base import register
from .nonattack import NonAttackComparablePlaybook, register_nonattack
from .probable_damage_event import ProbableDamageEvent
from .. import battle_query as bq
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.effect_type import EffectType
from ..utilities.damage import will_be_overkill

# `param_8` VIDE du call-site `GenerateMultiHitAttackPredictions` : le port encode un profil absent
# par la chaine "None" (`_PROFILE_INDEX` -> enum -1 : percage 0, armure PLEINE), meme convention que
# `engine.playbook.prediction.abilities._PLAYBOOK_PROFILE_OVERRIDE`.
_PROFILE_NONE = "None"


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


class ForwardObserversPlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ForwardObserversPlaybook$$CalculateCustomUtility` (1185), relu
    VERBATIM sur `rnca9r7q6c` :

        CheckIfAnyEnemyHasMarkerLight(caster);            // remplit le cache (this+0x70/+0x71)
        u = Fix64.Zero;                                   // <Fix64 statics>+0x28, ecrit a 0 par
                                                          // `FixMath.NET.Fix64$$.cctor`
        if (!this.<anyEnemyHasMarkerLight @+0x71>)
            u = Fix64.op_Addition(u, GetUtilityValue("ForwardObservers_EnemyHasNoMarkerlight"));
        if (target == null) throw;
        comp = <FillUpStatComponent de la CIBLE, StatType 5 = Health>;      // cf. ci-dessous
        if (comp == null) throw;
        return Fix64.op_Addition(u,
                   Fix64.op_Multiply(comp.RemainingPercentage(),
                                     GetUtilityValue("ForwardObservers_TargetHealthPercentage")));

    et `IdunBattle.AI.Playbook.Loki.ForwardObserversPlaybook$$CheckIfAnyEnemyHasMarkerLight` :

        if (this.<checked @+0x70>) return;                 // cache, remis a 0 par
        this.<checked @+0x70> = true;                      // `...ForwardObserversPlaybook$$ResetCaches`
        player = EntityExtensions.GetCurrentPlayer(caster, this.<state @+0x20>);
        foreach (e in this.<battleQuery @+0x28>.<slot itf 0x8e = GetAllEnemiesOf>(player))
            if (EntityExtensions.HasEffect(e, this.<state @+0x20>, 0x462, null)) {
                this.<anyEnemyHasMarkerLight @+0x71> = true; break;
            }

    DEUX TERMES, et ils n'ont pas la meme nature :

    * **`EnemyHasNoMarkerlight` (200) — BOOLEEN et GLOBAL** : il ne depend NI de la tuile candidate NI
      de la cible, seulement de l'etat du BOARD. C'est un bonus d'AMORCAGE : tant qu'aucun ennemi ne
      porte la marque, poser le premier Markerlight vaut tres cher ; des qu'un seul ennemi (n'importe
      lequel) l'a, le terme DISPARAIT. Le compte n'intervient pas -- le natif `break` au premier.
    * **`TargetHealthPercentage` (40) — LINEAIRE dans le RATIO de PV de la CIBLE** :
      `IdunBattle.Entities.Components.FillUpStatComponent$$RemainingPercentage` =
      `Fix64.Max(Fix64(0), Fix64(<valeur courante @+0x18>) / Fix64(get_CurrentMaximumValue()))`, donc
      un ratio dans [0,1] (PAS un pourcentage 0..100, PAS un arrondi -- meme piege que SavageEchoes,
      resolu dans l'autre sens : ici il n'y a aucun `GetStat(Health, part=1)`). Il arbitre la CIBLE :
      a poids egal, l'IA marque l'ennemi le PLUS SAIN.

    **La cible du `FillUpStatComponent` est bien la SANTE.** Le call-site est l'inline exact de la
    branche `statType == 5` de `IdunBattle.Entities.UnitExtensions$$GetFillUpStatComponent` (memes
    deux classes : le type du composant et la classe qui porte son id de composant en champ statique).

    ARTEFACT NATIF ET CLASSIFICATION (#149) : `CheckIfAnyEnemyHasMarkerLight` est une **methode
    IMPERATIVE du playbook** -- une boucle `foreach` + `HasEffect`, PAS un arbre `DSLFactory`. Il n'y
    a donc rien a faire emerger de noeuds DSL, et ce mirror est imperatif de bout en bout. C'est la
    difference STRUCTURELLE avec Chronometron (dont `GetAffectedEnemies` etait un arbre DSL PARTAGE
    avec sa face COMBAT) : ici la face COMBAT,
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$ExecuteBehaviour`, est un
    arbre `AddEffect(0x462 Markerlight, TurnsFromRounds(GetNumberConstant(0x45))) +
    AddEffect(0x575 ForwardObservers_DamageReduction, TurnsFromRounds(GetNumberConstant(0x77)))` qui
    n'evalue AUCUN selecteur d'ennemis. **Aucun artefact partage entre les deux faces** -> aucun
    evaluateur a reutiliser, et aucun risque de fork de port. Les seules primitives mutualisees sont
    `battle_query.all_enemies_of` (slot 0x8e) et `battle_query.entity_has_effect`
    (`EntityExtensions.HasEffect`), ecrites la ou vivent leurs homonymes natifs.

    ROUTE : `constants` = `{range: 3, dmgPctReduction: 50, nrOfRounds: 2, nrOfRounds_2: 1}` -- **pas de
    `damageProfile`** -> l'ability n'atteint jamais `_best_attack` ; elle passe par
    `playbook/nonattack.py` (verrou 2 de #27), ou `u = custom` et `u_full = u + Tile(7)`.
    `ShouldExecute` (slot de vtable +0x328) rend `true` : MESURE au slot sur CE playbook
    (`probe_27_4b_chronometron_vtable.py`), pas suppose.

    CIBLAGE (lu, non porte au registre COMBAT -- ce port ne couvre que la face DECISION) :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$.ctor` appelle la
    surcharge 7-args EXPLICITE `TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange
    statics>+0x18 = RANGE_FROM_CONFIG, forceMeleeTarget=0 = RangedBool.True, rules=0x200004002, 0, 0)`
    -- ce n'est PAS la forme preset+flags, le litteral EST donc le masque effectif :
    `TargetMatchesDynamicRule (0x2) | TargetIsEnemy (0x4000) | TargetIsNotAnObject (0x200000000)`.
    `AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType.Others`. La regle DYNAMIQUE est
    portante : `...ForwardObserversAbility$$GetDynamicInvalidTargetReason` refuse (raison 2) toute
    cible qui porte DEJA le Markerlight. Cote decision cette cascade est appliquee par le NATIF
    (`ctx.ability_targets` = RPC `abilityTargets`), donc le port en herite sans la rejouer.

    Poids resolus a l'execution depuis la BC (`aiUtilities.Default.ActiveAbilities`), jamais codes en
    dur : `ForwardObservers_EnemyHasNoMarkerlight` = 200, `ForwardObservers_TargetHealthPercentage`
    = 40. Porteurs de 1185 : `tauSmnStealthSuit` (SUMMON) et `tauNpc5StealthSuit` (npc), memes deux
    actives `[ForwardObservers, WallOfMirrors]`. Le summon est declare par
    `units.abilities.ATemptingTrap.constants.unitId`, mais **aucune unite du gameconfig ne porte
    `ATemptingTrap`** -> pas d'invocateur ; le porteur est amene au board par
    `catalog_inject.py --units tauSmnStealthSuit` (#92), comme SavageEchoes/Chronometron."""

    ability_id = int(ActiveAbilityType.ForwardObservers)   # 1185
    W_NO_MARKERLIGHT = "ForwardObservers_EnemyHasNoMarkerlight"     # 200
    W_TARGET_HP = "ForwardObservers_TargetHealthPercentage"         # 40
    MARKERLIGHT = int(EffectType.Markerlight)                       # 1122 = 0x462

    def any_enemy_has_markerlight(self, ctx) -> bool:
        """Mirror de `...ForwardObserversPlaybook$$CheckIfAnyEnemyHasMarkerLight` : « au moins UN
        ennemi du joueur du caster porte l'effet 0x462 ». Le natif `break` au premier -> predicat,
        pas un compte. Le cache natif (+0x70/+0x71, vide par `ResetCaches`) n'a pas d'equivalent ici :
        l'etat ne bouge pas pendant une evaluation, donc recalculer rend la MEME valeur."""
        return any(bq.entity_has_effect(e, self.MARKERLIGHT)
                   for e in bq.all_enemies_of(ctx.units))

    def remaining_health_percentage(self, ctx, target) -> float:
        """`IdunBattle.Entities.Components.FillUpStatComponent$$RemainingPercentage` sur le composant
        `Health` (StatType 5) de la CIBLE = `max(0, courant / CurrentMaximumValue)`.

        `courant` = `FillUpStatComponent+0x18` = ce que rend `GetStat(u, Health, part=0)` -> canal
        `ctx.hp_cur_by_id` ; `CurrentMaximumValue` = ce que rend `GetStat(u, Health, part=2)` ->
        `ctx.hpmax_by_id` (overlay `combatSnapshot.healthMax`, la MAX EFFECTIVE). Ce sont les deux
        memes canaux que `SavageEchoesPlaybook`.

        PV max illisible : le natif leverait (`comp == null` -> NRE). Ici la seule facon d'etre dans
        ce cas est un canal incomplet, jamais un etat de bataille : on rend 0.0 (le terme s'eteint,
        le terme booleen reste) plutot que de faire tomber tout le generateur d'actions."""
        cur = ctx.hp_cur_by_id.get(target)
        mx = ctx.hpmax_by_id.get(target)
        if cur is None or not mx:
            return 0.0
        return max(0.0, float(cur) / float(mx))

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        u = 0.0
        if not self.any_enemy_has_markerlight(ctx):
            u += ctx.wt.sub("ActiveAbilities", self.W_NO_MARKERLIGHT)          # 200
        return u + (self.remaining_health_percentage(ctx, target)
                    * ctx.wt.sub("ActiveAbilities", self.W_TARGET_HP))         # 40


class SorcerousFacadePlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook` (ability 1100) — le dernier verrou de #27,
    et il est DISTINCT des autres : sa cible native est un ALLIE.

    ## Le terme custom — `...SorcerousFacadePlaybook$$CalculateCustomUtility`

        u1 = IUtilitiesDatabase.GetUtility(7 = UtilityType.Tile)
                .EvaluateMovement(new UtilityMovementCase(caster, EntityExtensions.GetMainTile(target)))
        u2 = IUtilitiesDatabase.GetUtility(7)
                .EvaluateMovement(new UtilityMovementCase(caster, casterPosition))
        return Fix64.op_Subtraction(u1, u2)

    C'est le MEME artefact natif que `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility`
    — memes deux appels (slot 0 de `IUtilitiesDatabase` avec l'argument `7`, puis slot 8 de
    `IUtility`), au seul champ `AbilityType` pres (rempli la, NUL ici ; il n'entre pas dans le
    composite Tile). Le port n'ecrit donc AUCUN nouvel evaluateur : il APPELLE
    `engine.ai.utilities.get_movement_utility(ctx, pos, UtilityType.Tile)`.

    Les deux `UtilityMovementCase` sont construits par des surcharges DIFFERENTES, verifiees par
    xref : le 1er appel prend la surcharge `movementTile` (elle fait `new UnitPosition(tile)`), le 2e
    la surcharge `movementPosition`. Les autres champs (`ClosestEnemy`, `AbilityType`, `Parent`,
    `Target`) sont NULS dans les deux — d'ou la reduction du composite a sa feuille Tile(7) (les
    feuilles de mouvement se desarment sur `case.ClosestEnemy == null`).

    SENS : `custom = Tile(tuile de la CIBLE) - Tile(tuile candidate)`. Comme la route ajoute ensuite
    `u_full = u + Tile(tuile candidate)`, le terme de tuile candidate **s'annule exactement** et
    l'utilite d'action porte `Tile(tuile de la CIBLE)` : apres l'echange de positions, c'est la
    tuile de l'allie que le caster occupera. Terme POSITION-dependant (il entre dans l'argmax par
    tuile) et CIBLE-dependant.

    ## Le gate — `...SorcerousFacadePlaybook$$ShouldExecute` (OVERRIDE du slot +0x328)

        sel = TargetsSelector.SelectFirst(SorcerousFacadeAbility.GetTarget(ability),
                                          entities{Caster=caster, CasterTile=casterTile,
                                                   CasterTiles=[casterTile]});
        if (sel == null) {
            uTarget = GetUtility(7).EvaluateMovement(case(caster, GetMainTile(target)));
            foreach (t in battleQuery.<slot d'interface 0xa>(caster, false, null))
                if (GetUtility(7).EvaluateMovement(case(caster, t)) > uTarget) return false;
        }
        return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

    - `slot d'interface 0xa` : la collection est ITEREE et chaque element est passe a la surcharge
      `movementTile` du ctor -> ce sont des TUILES, et l'appel `(caster, 0, 0)` tolere un 3e argument
      NUL. La seule methode d'`IBattleQuery` qui satisfasse les trois contraintes est
      `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovableTilesOf(unit, ignoreFlags,
      overrideRange)` (son homologue `GetMovableTilesFor` deREFERENCE son 3e argument, donc
      crasherait sur `null` ; `GetCurrentAndMovablePositionsFor` est un AUTRE slot, 0xe, celui
      qu'appelle `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles`). Mirror :
      `ctx.reach_nc` (= `action_tiles`, ORIGINE + tuiles de move) — le meme ensemble.
    - `WillNormalAttackKill` (@ `IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill`, surcharge
      4-args) = `new ProbableDamageEvent(target, battleQuery.<slot 0x21>(caster, target, casterTile))
      .Prediction.WillBeKill`, avec `target == null -> false`. Le `target` est ici la cible de
      l'ABILITY, c'est-a-dire l'ALLIE : le natif refuse le cast quand l'attaque normale du caster
      TUERAIT l'allie vise. Ce n'est pas une paraphrase — c'est le 3e argument du call natif.

    ## Le selecteur `GetTarget` — MEME arbre que la face COMBAT

    `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$GetTarget` :

        Cache(First(SortByDistance(ValidNormalAttackTargets(Caster, CasterTiles, range: null,
                                                            ignoreRule, additionalRule),
                                   Caster),
                    1),
              true)

    `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$ExecuteBehaviour`
    RE-INLINE exactement le meme arbre (memes appels, memes arguments) pour alimenter son
    `UseActiveAbility(caster, sel, UnitNormalAttackType(caster))` : UN seul artefact natif.
    `IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` se resout en
    `TargetingQuery.GetValidTargets(caster, casterTiles, <options de l'attaque normale>)` -> le
    mirror OFFLINE/LIVE est `ctx.plans` (les `attackPlans` de l'attaque NORMALE portent deja la
    cascade de ciblage native), FILTRE sur la tuile candidate.
    `IdunBattle.Entities.Selectors.SortByDistanceSelector$$Select` trie par
    `PositionComponent.Distance(<reference>, GetMainTileId(s))` ou la reference est le selecteur
    `Caster` : la distance est prise a la position REELLE du caster, PAS a la tuile candidate (meme
    quirk d'ancrage que Chronometron/SavageEchoes). `OrderBy` LINQ est STABLE -> a distance egale,
    l'ordre d'enumeration decide.

    ## La prediction — `...SorcerousFacadePlaybook$$MakeDamagePredictions` (OVERRIDE)

        sel = SelectFirst(GetTarget(ability), entities{Caster, CasterTile=casterPosition.MainTile,
                                                      CasterTiles=casterPosition});
        if (sel == null) return <liste VIDE statique>;
        list = [ new ProbableDamageEvent(sel, battleQuery.<slot 0x22>(caster, sel, casterPosition)) ];
        list.AddRange(GenerateMultiHitAttackPredictions(
                          caster, casterPosition, sel,
                          targets = DSLSelectors.Get(sel),                       // mono-cible
                          damage  = Half(Sum(GetVariableForLevel(0xc = minDmg),
                                             GetVariableForLevel(0xd = maxDmg))),
                          hits    = GetNumberConstant(0x2f = nrOfHits),
                          profil  = <vide>));
        return list;

    Deux faits qui changent le port, et qu'aucun nom ne laissait deviner :

    1. **la prediction ne porte PAS sur la cible de l'ability** (l'allie) mais sur `sel`, l'ENNEMI
       le plus proche attaquable a l'attaque normale. L'utilite d'action de 1100 contient donc
       l'attaque normale COMPLETE plus le coup psychique — c'est ce qui la rend competitive, et
       c'est pourquoi un port qui rendrait `[]` (le regime « sans prediction ») divergerait
       systematiquement ;
    2. `Half(Sum(minDmg, maxDmg))` est **l'avg config GENERIQUE** — le meme
       `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(avgFlag)` que 1147/1148 (#172).
       Le chemin generique `prediction.make_damage_predictions` le produit deja ; l'ancienne note
       « base != avg -> gap BASE » de `prediction/abilities.py` etait un faux positif de lecture.
       Le SEUL ecart au generique est le profil de degat, passe VIDE par le playbook -> entree
       `_PLAYBOOK_PROFILE_OVERRIDE[1100] = "None"` (pierce 0, armure pleine), meme quirk que
       1020/1062/1147/1148.

    ## Route et masque

    Masque RELU sur le build courant (`...SorcerousFacadeAbility$$.ctor`) : surcharge FLAGS DIRECTS
    `TargetingOptions..ctor(&opts, isSelfCasting=0, range=<TargetingRange statics+0x48>,
    forceMeleeTarget=1, rules=0x402, 0, 0)` — le littéral `0x402` est passe EN CLAIR, ce n'est ni un
    preset statique ni la surcharge PRESET+flags. `0x402` = `TargetIsFriendly |
    TargetMatchesDynamicRule`, exactement ce que `TARGETING_OPTIONS_UNPORTED[1100]` porte deja (#217).

    Consequence : le VETO de #217 (`state_bridge._is_attack_ability`) refuse 1100 sur la route
    ENNEMIE, et ce port NE LE TOUCHE PAS. 1100 entre par la SECONDE route Comparable
    (`playbook/nonattack.py`), dont l'enumeration de cibles passe par `ctx.ability_targets` — le RPC
    natif `abilityTargets` en live, `state_bridge.ability_targets_offline` (kind `ally` depuis #217)
    sinon. `isSelfCasting = 0` -> `is_caster_added` reste le defaut `True`.

    Porteur thousTzaangor `Tzaangor Enlightened` [lineup, ThousandSons] ; l'allie vise doit porter le
    trait Psyker (`...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` : `HasTrait(target,
    0x3ea)` ET le caster doit pouvoir porter son attaque normale depuis les tuiles de cast). Cette
    regle DYNAMIQUE n'est pas portee (elle vit sur la classe d'ability, hors registre COMBAT) : en
    OFFLINE l'ensemble des cibles reste un SUR-ENSEMBLE des allies (degradation permissive documentee
    par #217) ; en LIVE le RPC rend l'ensemble natif EXACT."""

    ability_id = int(ActiveAbilityType.SorcerousFacade)   # 1100
    CONFIG_ID = "SorcerousFacade"

    # -- helpers de mirror -------------------------------------------------------------------
    @staticmethod
    def _tile_move_utility(ctx, pos) -> float:
        """`IUtilitiesDatabase.GetUtility(UtilityType.Tile).EvaluateMovement(UtilityMovementCase(
        caster, pos))` — l'appel PARTAGE avec `Playbook<T>.GetMovementUtility`, pas un evaluateur
        neuf. Import paresseux : `engine.ai.utilities` retire `engine.playbook.base` a la volee."""
        from ..ai.utilities import get_movement_utility
        from ..utilities.utility_type import UtilityType
        return get_movement_utility(ctx, pos, UtilityType.Tile)

    def _get_target(self, ctx, caster_tile):
        """`SorcerousFacadeAbility$$GetTarget` evalue puis `TargetsSelector.SelectFirst` : l'ENNEMI
        valide de l'attaque NORMALE le plus proche, depuis `caster_tile`. `None` si aucun.

        `ValidNormalAttackTargets(Caster, CasterTiles)` -> mirror `ctx.plans` (les `attackPlans` de
        l'attaque normale, qui portent la cascade de ciblage native) restreint aux evals dont
        `ranked` contient `caster_tile` — c'est bien « valide DEPUIS cette tuile ».
        `SortByDistance(..., Caster)` -> distance a `ctx.origin` (position REELLE du caster).
        `First(1)` -> le minimum, keep-first a egalite (`OrderBy` LINQ est stable)."""
        legal: list = []
        for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or []):
            if ev.get("abilityId") not in ctx.normal_ids or not ev.get("rankCount"):
                continue
            if any((rk.get("col"), rk.get("row")) == caster_tile
                   for rk in (ev.get("ranked") or [])):
                tid = ev.get("targetId")
                if tid is not None and tid not in legal:
                    legal.append(tid)
        if not legal:
            return None
        if ctx.origin is None:
            return legal[0]
        best, best_d = None, None
        for tid in legal:
            p = _main_tile_of(ctx, tid)
            if p is None:
                continue
            d = hexgeo.distance(ctx.origin, p)
            if best_d is None or d < best_d:                 # `<` STRICT = OrderBy stable
                best, best_d = tid, d
        return best if best is not None else legal[0]

    def _will_normal_attack_kill(self, ctx, target, caster_tile) -> bool:
        """`IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill(caster, target, casterTile)` :
        `target == null -> false` ; sinon `ProbableDamageEvent(target, PredictNormalAttack(caster,
        target, casterTile)).Prediction.WillBeKill` (= le champ `killSure` du port). La cible est
        l'ALLIE vise — le natif ne teste PAS le camp."""
        if target is None or ctx.scene is None:
            return False
        ev = prediction.make_normal_attack_predictions(ctx.scene, ctx.uid, target, caster_tile)
        if ev is None:
            return False
        return bool((ev.composite_fields() or {}).get("killSure"))

    # -- les trois overrides -----------------------------------------------------------------
    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        tpos = _main_tile_of(ctx, target)
        if tpos is None:
            return 0.0                       # cible hors plateau : GetMainTile non resoluble
        return self._tile_move_utility(ctx, tpos) - self._tile_move_utility(ctx, caster_tile)

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        if self._get_target(ctx, caster_tile) is None:
            tpos = _main_tile_of(ctx, target)
            if tpos is None:
                return False
            u_target = self._tile_move_utility(ctx, tpos)
            for T in (ctx.reach_nc or []):
                if self._tile_move_utility(ctx, T) > u_target:
                    return False
        return not self._will_normal_attack_kill(ctx, target, caster_tile)

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """Les DEUX events du natif, construits ICI et pas par le chemin generique.

        ⚠ NE PAS deleguer a `prediction.make_damage_predictions` : `SorcerousFacade` est dans
        `_PREDICT_VIA_NORMAL_ATTACK` (pose par #171), donc ce chemin-la rend l'attaque NORMALE et
        RIEN d'autre -- c'est voulu pour l'oracle `aiPlaybookPredict`, qui ne remonte que cet
        event-la (dedup aval, cf. `docs/rl/case-171-sorcerousfacade-normal-attack.md`). Le
        deleguer ici produirait DEUX fois l'attaque normale : mesure du 2026-07-30, `u_pred`
        moteur = 54.660 contre `pairUtility(1100)` natif = 27.340, soit exactement le double.

        Le second event, lui, existe bel et bien dans `CalculateUtilityFromPredictions` : c'est le
        `GenerateMultiHitAttackPredictions(base = Half(Sum(minDmg, maxDmg)), hits = nrOfHits,
        profil = <vide>)` du call-site. Son profil VIDE (`param_8` nul, meme quirk que 1020/1062/
        1147/1148) laisse l'armure PLEINE et le percage a 0 : sur une cible blindee il vaut ~1 point
        de degat, d'ou les +0.0105 d'utilite que le natif ajoute a l'attaque normale."""
        if ctx.scene is None:
            return []
        sel = self._get_target(ctx, caster_tile)
        if sel is None:
            return []                        # la liste VIDE statique du natif
        out = []
        # event #1 -- `ProbableDamageEvent(sel, battleQuery.<slot 0x22>(caster, sel, casterPosition))`
        ev = prediction.make_normal_attack_predictions(ctx.scene, ctx.uid, sel, caster_tile)
        if ev is not None:
            out.append(ev)
        # event #2 -- le batch `GenerateMultiHitAttackPredictions` propre a l'ability.
        dp = prediction.generate_multi_hit_attack_prediction(
            ctx.scene, ctx.uid, sel, self.ability_id, ctx.ab_name_by_id.get(self.ability_id),
            attack_pos=caster_tile, profile_override=_PROFILE_NONE)
        if dp is not None:
            out.append(ProbableDamageEvent(target=sel, prediction=dp))
        return out


# --- Registry : dispatch par ability_id via get_playbook_or_default (base.REGISTRY) ---
#
# HISTORIQUE (#27 tranche 3) — pourquoi 1100 en avait ete RETIREE, et ce qui a change :
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
# formule ; tant qu'elle n'existe pas, le terme reste NON VALIDABLE et donc non porte.
#
# CE VERROU EST LEVE (#27 tranche 4c) — et sans toucher au veto : 1100 n'entre PAS par
# `_best_attack` (elle reste ABSENTE de `ctx.plans`, exactement comme #217 l'a mesure), mais par la
# SECONDE route Comparable (`playbook/nonattack.py`), dont l'enumeration de cibles vient de
# `ctx.ability_targets` -> les ALLIES. Le terme custom n'est donc plus jamais evalue sur un ennemi.
# cf. docs/rl/case-27-custom-utility.md et docs/rl/case-217-phantom-action-routing.md.
def _register_all() -> None:
    for cls in (ArmoriumCherubPlaybook, LightOfSanguiniusPlaybook,
                HeraldOfTheApocalypsePlaybook, DrachnyenPlaybook,
                DoomSirenPlaybook, SavageEchoesPlaybook,
                HeavyWarpFlamerPlaybook):
        register(cls())
    # SECONDE route Comparable (#27-4b/4c/4d) : l'ability est absente de `ctx.plans` -- soit parce
    # qu'elle n'a pas de `damageProfile` (Chronometron, ForwardObservers), soit parce que son masque
    # de ciblage refuse toute cible ennemie (SorcerousFacade, veto #217). Registre + route dedies
    # (`playbook/nonattack.py`).
    for cls in (ChronometronPlaybook, ForwardObserversPlaybook, SorcerousFacadePlaybook):
        register_nonattack(cls())


_register_all()
