"""Overrides `CalculateCustomUtility` par-ability (namespace `IdunBattle.AI.Playbook[.Loki]`) — #27.

Terme d'ACTION `ComparablePlaybook<T>.IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility` (base = `Fix64(0)`, base.py),
ajoute PAR-DESSUS `u_full` dans `_best_attack` (`u_action = u_full + calculate_custom_utility`,
action_generators.py). Chaque sous-classe ci-dessous OVERRIDE ce terme, mirror 1:1 du corps natif (VA
citee). La prediction de degat reste celle du `DefaultActiveAbilityPlaybook` (heritee) : #27 ne porte
QUE le terme custom, pas la prediction (deja assuree par `prediction.py`).

PERIMETRE (cf. docs/rl/case-27-custom-utility.md) : seuls les overrides dont l'ensemble compte se
calcule FIDELEMENT sont portes ici -- soit depuis les primitives `ctx` (adjacence
`battle_query.count_adjacent` = port du selecteur DSL `AdjacentTiles->Units`, cf. sa docstring ;
iteration directe d'unites ; portee d'arme depuis la tuile courante ; constante), soit, quand
l'artefact natif EST un arbre de selecteurs, en EVALUANT cet arbre sur un `DslContext` monte depuis
la scene (`resurrection_orb`, `tile_targets`, et ici `MortarionsPlagueWindPlaybook`) -- la doctrine
DSL/imperatif (#149) impose la seconde voie des que le natif compose des nœuds `DSLSelectors`.
Les overrides dependant d'un SOUS-SYSTEME non porte (formes TilesInTriangleShape ;
`GenerateMultiHitAttackPredictions` ; utilite de deplacement
`UtilityMovementCase`/`GetTargetUtilityDiffOnDisplace`) restent en residu (doc #27).
⚠ `UnitsWithTrait` et la chaine `AdjacentUnits` a 3 vagues FIGURAIENT dans cette liste de residus :
elles n'y avaient plus lieu d'etre (toutes deux portees dans `entities/selectors/`) -- cf. #27-r5.

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

import engine.playbook.prediction as prediction   # sous-paquet FRERE, pas `from . import` (#270-r4-r2)
from .prediction.abilities import make_secondary_multihit_event
from .common import DefaultActiveAbilityPlaybook
from .base import NO_ACTION, register, tile_utility, tile_utility_for_unit
from .nonattack import NonAttackComparablePlaybook, register_nonattack
# #977 : les DEUX corps generiques de deplacement (`Playbook`1$$GetPushableTiles` /
# `$$GetTargetUtilityDiffOnDisplace`) ont demenage la -- foyer PARTAGE avec `1043 ThunderousAssault`
# (NonComparable), qui les appelle a l'identique. Forme B : le binding de module reste patchable.
from . import displace_utility as _displace
from .. import battle_query as bq
from .. import dsl
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.effect_type import EffectType
from ..entities.traits.unit_trait import (UnitTrait, entity_trait_names, has_any_trait,
                                          has_trait, is_normal_unit)
# Les vagues de 1093 sont l'arbre DSL de l'ABILITY (`deathguard.py`), pas une geometrie recalculee
# ici : le natif appelle depuis le playbook les MEMES methodes d'ability que depuis
# `ExecuteBehaviour`. Meme doctrine que `resurrection_orb` (`runner.abilities.necrons`).
from ..runner.abilities.deathguard import mortarions_plague_wind_psyker_selector
# #498-r4 : le tuple des trois traits refusants de `UnitExtensions$$IsDisplaceable`, LU au foyer
# runner au lieu d'etre recopie ici (il l'etait, et une 3e copie vivait dans `it_itches.py`).
from ..runner.components import NOT_DISPLACEABLE_TRAITS
from ..services.battle_query import find_melee_weapon, weapon_hits
from ..utilities.damage import will_be_overkill
from ..utilities.utility_type import UtilityType
from ..ai.utilities import get_movement_utility
from ..ai import cast_positions as CP    # #350-r3a-r4 -- forme B. Differe CLASSE GRATUIT (charger
                                         # `cast_positions` seul ne tire pas ce module), donc hisse.

# `_PROFILE_NONE` VIVAIT ICI (le `param_8` VIDE du call-site `GenerateMultiHitAttackPredictions` de
# 1100). Il a MIGRE dans `prediction.abilities._PLAYBOOK_PROFILE_OVERRIDE[1100]` avec la fin du fork
# de port (#351) : le profil du 2e batch se lit desormais la ou se lisent les onze autres.


class _CustomOnlyPlaybook(DefaultActiveAbilityPlaybook):
    """Base commune : HERITE la prediction de degat generique (`DefaultActiveAbilityPlaybook.
    make_damage_predictions` -> `prediction.make_damage_predictions`) et n'override QUE
    `calculate_custom_utility`. `ability_id` fixe la cle du registry (dispatch `get_playbook_or_default`)."""
    is_normal_attack = False


class ArmoriumCherubPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.ArmoriumCherubPlaybook$$CalculateCustomUtility`
    = `Fix64.FromInt(1)` CONSTANT (aucune garde, aucun poids). Porteur adeptRetributor 'Vindicta'
    [lineup, PRESENT dans `rl_duel build --list-pool`]. Bonus d'action +1 identique au patron
    NormalAttack (common.py) : ArmoriumCherub bat tout actif Comparable a Delta(pair+tile) < 1, et
    EGALISE l'attaque normale (elle aussi +1).

    Porte AUSSI son `ShouldExecute` depuis `#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1` -- cf. la methode.
    Il vit ICI et pas dans `should_execute_gates.py` parce que le registre est indexe par
    `ability_id` : deux entrees pour 1014 se seraient ECRASEES, et le gagnant aurait dependu de
    l'ordre d'import."""
    ability_id = int(ActiveAbilityType.ArmoriumCherub)  # 1014

    #: `if (n < 2)` du corps natif -- comparaison sur l'ENTIER rendu par `.<+0x10>.<+0x18 = Count>`.
    MIN_NORMAL_ATTACK_TARGETS: int = 2

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        return 1.0

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        """`IdunBattle.AI.Playbook.Loki.ArmoriumCherubPlaybook$$ShouldExecute` (1014), lu verbatim :

            position = new UnitPosition(casterTile);
            list = battleQuery.<slot d'interface 0x42 = 66 GetValidTargets>(
                       caster, position, ActiveAbilityType.Loki_NormalAttack);   // 0x45 = 69
            if (list.<+0x10>.<+0x18 = Count> < 2)
                return !ArmoriumCherubPlaybook.CanKillTarget(caster, casterTile, target);
            return true;

        et la feuille, relue en entier :

            // ...ArmoriumCherubPlaybook$$CanKillTarget(caster, casterTile, target)
            abilityState = Playbook<T>.GetAbilityState(caster);
            preds = this.<slot de vtable +0x358 = MakeDamagePredictions>(
                        caster, new UnitPosition(casterTile), target, abilityState);
            foreach (p in preds)
                if (DamagePredictionResult.get_MightBeKill(p.<+0x8>)) return true;
            return false;

        DEUX clauses, et l'utilite n'est LUE dans AUCUNE des deux -- ce gate n'a pas de seuil.
        Le sens : Vindicta lance le cherubin des qu'elle a **au moins deux** cibles d'attaque
        normale depuis la tuile de cast ; a une seule (ou zero), elle ne le depense que si l'ability
        ne peut PAS tuer -- l'inverse du gate `!WillNormalAttackKill` de la famille SpiritLeech, et
        c'est LU, pas devine : ici c'est un gate d'ECONOMIE DE SURTUAGE, la cible mourant de toute
        facon, autant garder la ressource.

        ⚠ **`MightBeKill`, PAS `WillBeKill`.** `get_MightBeKill` est la borne MAX (`kill` du
        composite du port) ; `get_WillBeKill` est le SURE-kill (`killSure`, qui compte le block du
        defenseur). Les deux different des qu'un block est possible, et prendre `killSure` ici
        rendrait le refus PLUS RARE que le natif -- degradation permissive silencieuse.

        ⚠ **Le compte est PAR TUILE DE CAST** : `casterTile` est le `casterPosition.MainTile` que
        `CalculateActionUtility` passe, donc la tuile CANDIDATE du sweep. Le gate departage donc
        aussi les POSITIONS, pas seulement l'opportunite du cast.

        ⚠ **La prediction est RECALCULEE, et c'est le natif qui le fait** : `CanKillTarget` rappelle
        le slot +0x358 avec exactement les memes arguments que `CalculateUtilityFromPredictions`
        vient de lui passer. Le port ne peut pas reutiliser la liste deja produite -- la signature
        de `ShouldExecute` ne la porte pas, cote natif comme ici.

        DEGRADATION : compte NON MESURABLE (`None` -- pas de tuile de cast, ou `visualId` absent
        d'`observeBattle` donc portee non derivable) -> VRAI, aucun refus invente. C'est la
        convention des cinq autres gates de la tranche. Le compte porte, lui, est une BORNE
        SUPERIEURE (cf. le foyer) : il sur-compte plutot que sous-compte, donc il tire vers la
        branche `>= 2` = ACCEPTER."""
        # DIFFERE PORTEUR, MESURE : en process FRAIS, `import engine.playbook.noncomparable._base`
        # fait deja atterrir `engine.playbook.loki_custom` dans `sys.modules` (la cascade du paquet
        # `engine.playbook` tire ce module) -- hisser fermerait donc un cycle. Forme B (le MODULE,
        # pas les noms) : un binding de module reste substituable sous `monkeypatch`.
        from .noncomparable import _base as _nc_base
        n = _nc_base.count_eligible_normal_attack_targets(ctx, ctx.uid, caster_tile, ctx.epos)
        if n is None:
            return True                       # canal muet -> aucun refus invente
        if n >= self.MIN_NORMAL_ATTACK_TARGETS:
            return True                       # `if (n < 2)` NON pris -> `return true`
        return not self._can_kill_target(ctx, caster_tile, target, ability_id)

    def _can_kill_target(self, ctx, caster_tile, target, ability_id) -> bool:
        """`...ArmoriumCherubPlaybook$$CanKillTarget` : `preds.Any(p => p.MightBeKill)`.

        `MightBeKill` = la cle `kill` du composite (`engine.utilities.damage.
        composite_fields_from_prediction`, foyer UNIQUE de la lecture d'un `DamagePredictionResult`),
        a ne pas confondre avec `killSure` (`get_WillBeKill`). Liste vide -> `False`, ce que rend
        aussi le natif (`foreach` sans iteration -> `return false`)."""
        for ev in (self.make_damage_predictions(ctx, caster_tile, target, ability_id) or ()):
            if (ev.composite_fields() or {}).get("kill"):
                return True
        return False


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
        n = bq.count_adjacent(caster_tile, ctx.epos, ctx.elev_by_pos, bq.neigh_map(ctx))
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

    Le slot 0x7f est l'overload `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(Tile, TUnit, bool)`
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
        if tpos is not None and bq.count_adjacent(tpos, ctx.epos, ctx.elev_by_pos, bq.neigh_map(ctx)) > 0:
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
        n = bq.count_adjacent(tpos, ctx.epos, ctx.elev_by_pos, bq.neigh_map(ctx))
        return float(n) * ctx.wt.sub("ActiveAbilities", self.W_KEY)   # 10


class MassDriverAcceleratorPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$CalculateCustomUtility` —
    **terme IDENTIQUEMENT NUL : le selecteur est ancre sur `Owner`, que ce corps-la laisse NULL.**

    Corps natif, relu VERBATIM sur `rnca9r7q6c` :

        sel      = MassDriverAcceleratorAbility.GetBuffTargets(this.ability);
        entities = new AbilityEntities(caster: caster, actor: caster, target: target,
                                       owner: null, <et TOUS les autres slots a null>);
        n        = sel.Count(entities);                 // slot 2 de l'interface selecteur
        return Fix64.FromInt(Math.Max(0, n - 1))
               * GetUtilityValue("MassDriverAccelerator_AdjacentFriendly");

    et `IdunBattleLogic.Entities.Abilities.Active.Loki.MassDriverAcceleratorAbility$$GetBuffTargets` :

        Owner + DSLSelectors.AdjacentFriends(Owner, unique: 1, unitSelectionType: 3)

    C'est **le MEME artefact natif que la face COMBAT** :
    `...MassDriverAcceleratorAbility$$ExecuteBehaviour` re-inline exactement le meme couple
    `(Owner, AdjacentFriends(Owner, 1, 3))` joint par `TargetsSelector.op_Addition` pour alimenter son
    `DSLBehaviors.AddStaticStatModifierEffect(<cible>, 0x606, 1, Get(extraMovement), ...)` : a
    l'EXECUTION, Kimm et ses amis adjacents gagnent bien le bonus de mouvement. Mais l'`AbilityEntities`
    de l'execution porte un `owner`, et **celui de la DECISION n'en porte pas**.

    LA CHAINE, LUE BOUT A BOUT (aucun maillon deduit) :

    1. `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` ecrit ses champs a
       `+0x00 = actor`, `+0x08 = caster`, `+0x10 = target`, **`+0x18 = owner`**
       (l'ordre des PARAMETRES est `(caster, actor, target, owner, casterTile, activePlayer,
       casterTiles, effect, targetTile, targetTiles, activeTarget, previousActiveTarget,
       currentAbilityOrEffect, ...)` — signature de `data/symbols/<build>/frida/methods.tsv`).
    2. Le call-site de `CalculateCustomUtility` passe `(caster, caster, target, 0, 0, 0, 0, 0, 0, 0,
       0, 0, &cur, &parent, &trig, ...)` : **9 zeros consecutifs en positions 4..12**, donc
       `owner = null` (et toutes les positions/tuiles nulles). A comparer avec
       `...MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason`, qui, LUI, remplit
       `casterTiles` et `targetTiles` — le contraste est dans le meme binaire, a deux fonctions d'ecart.
    3. `IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `entities+0x18` et, s'il est nul,
       **rend une `List` VIDE** (branche `if (owner == 0) return new List<>();`). Ses deux voisins
       lisent d'autres champs : `IdunBattle.Entities.Selectors.ActorSelector$$Select` lit `+0x00`,
       `IdunBattle.Entities.Selectors.CasterSelector$$Select` lit `+0x08` — c'est ce triplet qui
       interdit de confondre le champ.
    4. `AdjacentFriends(Owner, unique, sel)` = `Friends(Owner, Units(AdjacentTiles(Owner), unique,
       sel) - Owner, sel)` : sur un `Owner` vide, `AdjacentTiles` n'a aucune ancre -> vide aussi.
    5. Donc `n = 0`, `Math.Max(0, 0 - 1) = 0`, et le terme vaut `Fix64(0) * W = 0` — **quelle que
       soit l'adjacence, sur tout plateau**. Le poids
       `aiUtilities.Default.ActiveAbilities.MassDriverAccelerator_AdjacentFriendly = 5`, pourtant
       AJOUTE par ce build, n'est jamais applique.

    IDENTIFICATION DU SELECTEUR `Owner` (`DSLSelectors+0x30`) — quatre lectures convergentes :
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector`
        appelle `AdjacentFriends(champ+0x30, ownerTiles, 1)` — la surcharge `(unit, unitTile, unique)` :
        le parametre nomme **`ownerTiles`** (metadata IL2CPP) est la liste de tuiles de CE MEME `unit` ;
      * `IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateTargetSelector`
        a la structure BIT-A-BIT identique a `GetBuffTargets` et le port le documente deja
        « Self + AdjacentFriends(range 1) » pour une AURA (donc son porteur = l'owner de l'effet) ;
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ModifiedExoarmourAbility$$CreateBehaviour`
        (le PASSIF de Kimm) passe `champ+0x30` a la FOIS comme cible et comme owner de ses deux
        `AddEffect` auto-appliques ;
      * `entities/effects/factory.py` documente deja Defender comme `AdjacentFriends(1) - owner`.
    Les deux champs voisins ne sont PAS interchangeables : `+0x48` = CASTER (c'est lui que
    `ExecuteBehaviour` passe a `MoveUnit`/`AttackWithAttackDamage`/`IfAlive`) et `+0x60` = TARGET
    (`GetAdjacentAttackTargets` = `Enemies(champ+0x48, AdjacentUnits(champ+0x60, 1, 3))`).

    CE QUE LA FICHE #27-r1 ANNONCAIT, ET POURQUOI C'ETAIT FAUX : `max(0, Count(GetBuffTargets) - 1)
    * W` avec `Count = 1 + |amis adjacents|`. Cette lecture SUPPOSE `Owner = caster` ; elle vient de
    la face COMBAT, ou c'est vrai. Le port qui en decoule (`W x |amis adjacents|`) est un biais de
    +5 par allie colle a Kimm que le natif n'applique JAMAIS — mesure ci-dessous.

    CONFRONTATION LIVE (#27-r1, `probe_27_r1_massdriver_custom.py`, board MC1_67 seed 909,
    `votanChampion` injecte par `catalog_inject`) : Kimm a son SPAWN (1,0) — ne jamais la deplacer,
    un `act move` consomme son mouvement et rend 1222 ILLEGALE (`GetPossibleMoveTiles` vide) ;
    ennemi `tauCrisis` en (3,1) ; deux appats allies deplaces sur (1,1) et (0,0) pour n = 0/1/2 amis
    ADJACENTS. Le duel se joue entre 1222 (depuis (1,0)) et l'attaque NORMALE 69 (depuis (3,0)), et
    le stat `Damage` de Kimm est le curseur qui les met a egalite :

      | Damage | natif n=0 | natif n=1 | natif n=2 | moteur AVEC `W x n` |
      |---|---|---|---|---|
      | 3450..3525 | 1222 | 1222 | 1222 | 1222 (d'accord) |
      | 3550..3800 | 69   | 69   | 69   | **1222 des n=1** (DIVERGE) |

    Le point de bascule natif est le MEME a n=0, n=1 et n=2, dans une fenetre de 25 points de
    `Damage` — soit **moins de 0.5 point d'utilite** (pente mesuree : `pairUtility(69, (3,0))` =
    64.017 a Damage 3600, donc ~0.018 utilite par point de Damage). Un terme de +5 (n=1) aurait
    deplace ce point de ~280 points de Damage. La SENSIBILITE du montage n'est pas supposee : le
    moteur PORTANT `W x n` bascule bel et bien a n=1 la ou le natif ne bascule pas.

    VERDICT : le terme est un NO-OP natif. Le port le mirroir en rendant `Fix64(0)`, et cette classe
    existe pour VERROUILLER ce zero (sans elle, la formule de la fiche resterait la seule trace
    ecrite, et le prochain lecteur la re-porterait).

    Porteur `votanChampion` `Kimm` [hero, LeaguesOfVotann] — ABSENT du pool de la seed BC (unite
    ajoutee par ce build), amene en runner par `catalog_inject.py --units votanChampion` (#92).
    ROUTE : `constants.damageProfile = DirectDamage` -> l'ability entre dans `ctx.plans` et passe par
    `_best_attack` (aucun verrou de route, contrairement a Chronometron/ForwardObservers).

    VOLET SPLASH (`MakeDamagePredictions`) — PORTE depuis #305, et il n'est PAS dans cette classe.
    `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions` ajoute, APRES la
    prediction principale, un `GenerateMultiHitAttackPredictions` par entite de
    `GetAdjacentAttackTargets` (= les ENNEMIS DU CASTER adjacents a la CIBLE) avec
    `GetHits2`/`GetDamageProfile2` — chaque event portant sur SON ennemi (selecteur
    `IdunBattleLogic.Entities.DSLSelectors$$Entity(<entite iteree>)`), et non sur la cible principale.
    Le port passe par le chemin GENERIQUE (`prediction.make_damage_predictions` -> `get_aoe_targets` +
    `aoe_overrides`), donc `MassDriverAcceleratorPlaybook` n'a AUCUN `make_damage_predictions` propre :
    le SET vit sur `engine.entities.abilities.active_ability.MassDriverAcceleratorAbility` et les
    entrees per-batch sur `engine.playbook.prediction.abilities._mass_driver_accelerator_inputs`.
    Consequence pour ce terme-ci : le montage de #27-r1 (cible SANS ennemi adjacent) reste valide
    tel quel — le volet y est inerte, il ne pouvait donc pas confondre la mesure du terme custom."""
    ability_id = int(ActiveAbilityType.MassDriverAccelerator)  # 1222
    # Cle de poids CITEE mais JAMAIS lue : le natif ne l'atteint pas (multiplicande toujours 0).
    # La garder nommee ici rend le no-op cherchable depuis `BC.Utilities`.
    W_KEY = "MassDriverAccelerator_AdjacentFriendly"          # = 5, inerte (cf. docstring)

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        # `Math.Max(0, Count(Owner + AdjacentFriends(Owner)) - 1)` avec `owner == null`
        # -> `OwnerSelector.Select` rend une liste VIDE -> Count = 0 -> Max(0, -1) = 0.
        return 0.0


class StikkbombPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$CalculateCustomUtility` (ability 1051) —
    PENALITE DE TIR AMI. Corps natif relu VERBATIM sur `rnca9r7q6c` :

        formula = DSLFormulas.Get(GetVariableForLevel(config, 0xc = minDmg));   // == Direct(minDmg)
        hits2   = GetNumberConstant(config, 0x32 = nrOfHits_2);
        profile = GetDamageProfile(config);
        sel     = StikkbombAbility.GetAdjacentDamageTargets();
        preds   = new List<ProbableDamageEvent>();
        foreach (u in TargetsSelector.SelectUniqueUnits(sel, AbilityEntities(Target = target), 3))
            if (UnitExtensions.IsFriend(u, caster, state))
                preds.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, target,
                                    <selecteur Target>, formula, hits2, profile, null, null) );
        u = Fix64.Zero;
        foreach (p in preds) u = Fix64.op_Addition(u, CalculateUtilityFromDamageEvent(p, caster, casterPosition));
        return Fix64.op_UnaryNegation(u);

    TROIS points de RE qui ne se devinent pas, et qui font tout ce terme :

    1. **Le SOUS-SET est declaratif, le FILTRE est imperatif.** Le selecteur
       `...StikkbombAbility$$GetAdjacentDamageTargets` (corps PARTAGE, seul proprietaire nomme
       `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$GetAdjacentDamageTargets`)
       est un arbre `DSLSelectors.AdjacentUnits(Target, unique: 1, sel: 3)` =
       `Units(AdjacentTiles(Target), unique, sel) - Target` — SANS filtre d'equipe. C'est le MEME
       artefact natif que la face COMBAT (`...StikkbombAbility$$ExecuteBehaviour` passe ce meme
       selecteur a son 2e `AttackWithAttackDamage`), deja portee en
       `runner/abilities/loki/splash.py::stikkbomb_tree` sous la forme
       `Alive(AdjacentUnits(TargetTile()))` — friendly-fire INCLUS (#213). Le tri ami/ennemi, lui,
       n'est PAS un noeud : c'est un `foreach` + `UnitExtensions.IsFriend` DANS le playbook. D'ou le
       partage exact du SET avec la face combat, et la duplication d'aucun evaluateur.
       `IsFriend(u, caster, state)` compare `GetCurrentPlayer(u).<0x20>.<0x24>` a celui du caster :
       le CASTER est donc son propre ami et compte s'il est lui-meme adjacent a la cible (Stikkbomb
       est ranged r=2, cette configuration est atteignable). Les positions sont les positions
       REELLES du board (occupation de tuile), pas la tuile candidate du sweep -> terme
       INDEPENDANT de `caster_tile`, DEPENDANT de la cible (il arbitre l'argmax par CIBLE).
    2. **Chaque ami produit une prediction sur la CIBLE PRINCIPALE, pas sur lui-meme.** Le 4e
       argument passe a `GenerateMultiHitAttackPredictions` est `target`, pas l'unite iteree —
       DECOMPILE puis confirme a l'assembleur (cf. `prediction.make_secondary_multihit_event`, qui
       porte la lecture des home slots). Et dans cette fonction `param_4` ne sert qu'a peupler
       l'`AbilityEntities` : ce sont les entites du SELECTEUR `param_5` (= `Target`) qui recoivent
       les predictions. Le contenu de l'event est donc INVARIANT d'un ami a l'autre ; seul leur
       NOMBRE compte. (C'est un quirk natif : l'intention lisible etait de predire les degats
       infliges aux amis. On mirroir le code, pas l'intention.)
    3. **Le signe vient du `op_UnaryNegation` FINAL, pas d'un event `friendly`.** L'event porte la
       CIBLE (un ennemi) -> `CalculateUtilityFromDamageEvent` rend une utilite POSITIVE, que le
       playbook nie. Poser `friendly=True` sur l'event ET negger produirait le signe INVERSE.

    Magnitude : le terme vaut `-n x U(1 coup sur la cible)` la ou l'utilite de paire vaut
    `U(nrOfHits coups sur la cible)`. Ce n'est donc pas un petit biais de rang mais une penalite du
    meme ordre que l'action elle-meme — un seul ami colle a la cible ampute ~la moitie de sa valeur
    (config 1051 : nrOfHits = 2, nrOfHits_2 = 1). AUCUN poids `BC.Utilities` n'intervient : ce
    custom-ci ne lit pas `GetUtilityValue`.

    Porteurs : `orksOrkBoys` (SUMMON de `Waaagh`, porte par `orksWarboss` [lineup]) et
    `orksNpc2OrkBoy` [npc]. Confrontable par le summoner (cf. §Validation de case-27)."""
    ability_id = int(ActiveAbilityType.Stikkbomb)  # 1051

    def _adjacent_positions(self, ctx, friends: bool) -> list:
        """Positions candidates du sous-set : le natif enumere TOUTES les unites adjacentes a la
        cible (`AdjacentUnits`, aucun filtre d'equipe) puis garde celles pour lesquelles
        `IsFriend(u, caster)` vaut `friends`. Cote port, les deux moities de la partition sont deja
        materialisees par le contexte : `ctx.fpos` (allies VIVANTS, caster EXCLU) et `ctx.epos`
        (ennemis VIVANTS). Le caster est re-ajoute cote AMIS — `IsFriend(caster, caster)` est vrai
        (meme joueur), et `AdjacentUnits(Target)` ne soustrait que la CIBLE."""
        if not friends:
            return list(ctx.epos or [])
        pos = list(ctx.fpos or [])
        cpos = _main_tile_of(ctx, ctx.uid)
        if cpos is not None:
            pos.append(cpos)
        return pos

    def _splash_count(self, ctx, target, friends: bool) -> int:
        """`Enumerable.Count` du sous-set : unites adjacentes (hex, porte d'elevation
        d'`IterateAdjacentTiles` = `battle_query.count_adjacent`) a la MainTile REELLE de la cible.
        La cible est a distance 0 d'elle-meme -> jamais comptee (== le `- Target` natif)."""
        tpos = _main_tile_of(ctx, target)
        if tpos is None:
            return 0
        return bq.count_adjacent(tpos, self._adjacent_positions(ctx, friends), ctx.elev_by_pos, bq.neigh_map(ctx))

    def _splash_event(self, ctx, caster_tile, target, ability_id):
        """L'event de degat SPLASH natif (invariant, cf. point 2 de la docstring de classe)."""
        if ctx.scene is None:
            return None
        return make_secondary_multihit_event(ctx.scene, ctx.uid, target, ability_id,
                                             ctx.ab_name_by_id.get(ability_id), caster_tile)

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$MakeDamagePredictions` — l'exact MIROIR du
        custom, avec le test `IsFriend` INVERSE :

            preds = GenerateMultiHitAttackPredictions(..., target, <Target>, Get(minDmg),
                                                      GetNumberConstant(0x2f = nrOfHits), profile, ...)
            foreach (u in SelectUniqueUnits(GetAdjacentDamageTargets(), AbilityEntities(Target=target), 3))
                if (!IsFriend(u, caster, state))
                    preds.AddRange( GenerateMultiHitAttackPredictions(..., target, <Target>,
                                        Get(minDmg), GetNumberConstant(0x32 = nrOfHits_2), profile, ...) )
            return preds;

        L'event principal (base `minDmg` seul + `nrOfHits` LITTERAL) vient du chemin generique via
        `_stikkbomb_inputs` ; les events secondaires sont ajoutes ICI, un par ENNEMI adjacent a la
        cible — et, comme cote custom, ils portent tous sur la CIBLE PRINCIPALE avec `nrOfHits_2`.
        Consequence de gameplay : plus la cible est entouree d'ennemis, plus le natif SUR-evalue les
        degats qu'il lui inflige (chaque voisin ajoute un coup de plus... sur elle)."""
        events = super().make_damage_predictions(ctx, caster_tile, target, ability_id)
        if not events:
            return events
        n = self._splash_count(ctx, target, friends=False)
        if n <= 0:
            return events
        ev = self._splash_event(ctx, caster_tile, target, ability_id)
        if ev is None:
            return events
        return list(events) + [ev] * n

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        n = self._splash_count(ctx, target, friends=True)
        if n <= 0:
            return 0.0
        ev = self._splash_event(ctx, caster_tile, target, ability_id)
        if ev is None:
            return 0.0
        from .probable_damage_event import calculate_utility_from_damage_event
        u = calculate_utility_from_damage_event(ev, ctx.wt, ctx.hpmax_by_id.get(target))
        return -float(n) * u                                   # Fix64.op_UnaryNegation(somme)


class PlasmaGrenadePlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` (ability 1098) —
    BONUS DE GROUPEMENT, et un VETO. Corps natif relu VERBATIM sur `rnca9r7q6c` :

        formula = DSLFormulas.Get(GetVariableForLevel(config, 0xc = minDmg));   // == Direct(minDmg)
        hits2   = GetNumberConstant(config, 0x32 = nrOfHits_2);
        profile = GetDamageProfile(config);
        ownerId = OwnerComponent.get_CurrentPlayerEntityId(caster);
        u = Fix64.Zero;
        foreach (e in battleQuery.<slot itf 0x7d>(target, ownerId, ignoreSteppables: false))
            foreach (p in GenerateMultiHitAttackPredictions(caster, casterPosition, target,
                              <selecteur Target>, formula, hits2, profile, null, null))
                u = Fix64.op_Addition(u, CalculateUtilityFromDamageEvent(p, caster, casterPosition));
        if (u == Fix64(0)) u = BaseUtility.<statics+0x18>;      // sentinelle -> AUCUNE action
        return u;

    QUATRE points de RE, dont deux ne se devinent pas :

    1. **Le SET est un appel `BattleQuery`, pas un arbre DSL** — contrairement a Stikkbomb (1051), qui
       partage son sous-set avec sa face COMBAT. Le slot d'INTERFACE 0x7d est
       `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(IEntity from, BEntityId playerEntityId,
       bool ignoreSteppables)` =
       `GetUnitsOnTiles(IterateAdjacentTiles(from, onlyEmptyOrSteppable: false, onlyWalkableTiles: true,
       allowTemporary: true), friendsOf: null, enemiesOf: <ennemis du joueur du caster>, ignoreSteppables)`.
       `from` = la CIBLE : ses propres tuiles ne sont jamais dans ses tuiles adjacentes, donc elle ne se
       compte pas elle-meme. Le meme ensemble que DoomSiren / HeavyWarpFlamer -> `battle_query.count_adjacent`.
       ⚠ Le slot se RE-DERIVE, il ne se recopie pas : `probe_27_4g_battlequery_slots.py` mesure au runtime
       que 0x7d -> index de vtable 0x81 = `GetAdjacentEnemies`, la ou 0x7c -> 0x80 = `GetAdjacentUnits`
       (AMIS COMPRIS). Un decalage d'UN slot inverserait la semantique en silence.
    2. **Chaque ennemi adjacent produit une prediction sur la CIBLE PRINCIPALE, pas sur lui-meme** :
       AUCUN argument du `GenerateMultiHitAttackPredictions` ne depend de l'ennemi itere (4e argument =
       `target`, 5e = le selecteur `Target`). Le contenu de l'event est donc INVARIANT ; seul leur
       NOMBRE compte. Meme quirk natif, meme foyer de port et memes entrees que Stikkbomb
       (`prediction.make_secondary_multihit_event` : base `minDmg` SEULE, `nrOfHits_2` coups).
    3. **Le SIGNE est POSITIF** — Stikkbomb, dont le corps est le meme mold, applique un
       `Fix64.op_UnaryNegation` FINAL (il compte des AMIS : c'est une penalite de tir ami). Ici il n'y
       en a pas : plus la cible est entouree d'ENNEMIS, plus la grenade vaut.
    4. **Somme nulle => VETO, pas utilite nulle.** Le natif substitue `BaseUtility.<statics+0x18>`
       (= `Fix64.MinValue / FromIntFraction(1000001, 1000000)`), l'une des deux valeurs que
       `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
       traduit en `Nullable` VIDE : **aucune action n'est generee**. Cote port : `NO_ACTION`
       (`playbook/base.py`), consomme par `ai/action_generators._action_utility`. Sans lui, le moteur
       proposerait 1098 sur une cible ISOLEE la ou le natif ne la propose JAMAIS -- degradation
       PERMISSIVE, exactement le trou qu'un entrainement irait exploiter.

    AUCUN poids `BC.Utilities` n'intervient (ce custom n'appelle pas `GetUtilityValue`), comme Stikkbomb.
    Config 1098 : `nrOfHits` = 2, `nrOfHits_2` = 1, `damageProfile` = Plasma, `range` = 2.

    ⚠ ASYMETRIE AVEC `MakeDamagePredictions`, et elle est VOULUE (#352). Ce CUSTOM est vivant parce
    que son set est un appel de SERVICE (`battleQuery.GetAdjacentEnemies(target, ownerId, false)`),
    qui recoit la cible et le joueur du caster en ARGUMENTS. `...PlasmaGrenadePlaybook$$
    MakeDamagePredictions`, lui, resout son set par un ARBRE DSL
    (`...PlasmaGrenadeAbility$$GetOtherTargets` = `Enemies(caster@0x30, AdjacentUnits(Target@0x60,
    1, 3), 1)`) evalue sur un `AbilityEntities..ctor(entities, caster: 0, actor: 0, target: target,
    ...)` au **caster NUL** -> set toujours vide, donc AUCUN event secondaire. Cette classe n'a
    ainsi PAS de `make_damage_predictions` (contrairement a `StikkbombPlaybook`), et ce n'est pas un
    oubli : MESURE `probe_352_grenade_prediction_base.py`, MEME geometrie -- natif 1051 = 3 events,
    natif 1098 = 1 event. La base du batch principal, elle, est corrigee en amont par
    `prediction.abilities._plasma_grenade_inputs` (minDmg SEUL + `nrOfHits` LITTERAL).

    Porteurs : `eldarSmnGuardian` (SUMMON **sans invocateur** -- aucune unite du gameconfig ne porte
    l'ability qui le declare) et `eldarNpc1Guardian` [npc] ; tous deux refuses par `buildNormalizedBC`.
    Porteur GREFFE sur une unite du pool (`case-92` §5bis) -- le natif charge le playbook PAR ABILITY.

    ECART CONNU, hors #27 : `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$GetUseProbability` rend
    `Fix64.FromIntFraction(1, 3)`, et `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` en fait un
    TIRAGE (`p >= 1 -> true ; p <= 0 -> false ; sinon random(p)`). Le natif ne propose donc 1098 qu'un
    tirage sur trois. Le moteur offline est deterministe et ne modelise pas cette porte -- meme statut
    que `...BlackRagePlaybook$$GetUseProbability` et `...ScarabSummonPlaybook$$GetUseProbability`. La
    consequence est nommee dans `case-27` : offline emet 1098 la ou le natif la saute 2 fois sur 3."""
    ability_id = int(ActiveAbilityType.PlasmaGrenade)  # 1098

    def _adjacent_enemy_count(self, ctx, target) -> int:
        """`Enumerable.Count(battleQuery.<slot itf 0x7d>(target, ownerId(caster), false))` : les unites
        de l'equipe ADVERSE du caster situees sur les tuiles adjacentes a la MainTile REELLE de la
        cible. Mirror `battle_query.count_adjacent` (meme `IterateAdjacentTiles` + porte d'elevation)
        sur `ctx.epos`. Terme INDEPENDANT de la tuile d'attaque, DEPENDANT de la cible."""
        tpos = _main_tile_of(ctx, target)
        if tpos is None:
            return 0
        return bq.count_adjacent(tpos, ctx.epos, ctx.elev_by_pos, bq.neigh_map(ctx))

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id):
        n = self._adjacent_enemy_count(ctx, target)
        u = 0.0
        if n > 0 and ctx.scene is not None:
            ev = make_secondary_multihit_event(ctx.scene, ctx.uid, target, ability_id,
                                               ctx.ab_name_by_id.get(ability_id), caster_tile)
            if ev is not None:
                from .probable_damage_event import calculate_utility_from_damage_event
                u = float(n) * calculate_utility_from_damage_event(
                    ev, ctx.wt, ctx.hpmax_by_id.get(target))
        # `if (u == Fix64(0)) u = BaseUtility.<statics+0x18>` -> `CalculateActionUtility` rend un
        # `Nullable` VIDE. Le zero couvre les DEUX causes natives : aucun ennemi adjacent, et une
        # somme d'utilites qui s'annule (prediction indisponible cote port -> meme verdict, jamais
        # une action que le natif refuserait).
        return NO_ACTION if u == 0.0 else u


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
    3. **`AddRange` AJOUTE, il ne SUBSTITUE pas** (#351). Le `list = [normale]` puis
       `list.AddRange(batch)` rend DEUX events, tous deux sur `sel`. Mesure `aiPlaybookPredict` :
       `count = 2`, meme `targetId`. Le chemin generique substituait l'un a l'autre et rendait UN
       event -- residu ferme par `_PREPEND_NORMAL_ATTACK_EVENT`.

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
        return get_movement_utility(ctx, pos, UtilityType.Tile)

    def _get_target(self, ctx, caster_tile):
        """`SorcerousFacadeAbility$$GetTarget` evalue puis `TargetsSelector.SelectFirst` : l'ENNEMI
        valide de l'attaque NORMALE le plus proche, depuis `caster_tile`. `None` si aucun.

        `ValidNormalAttackTargets(Caster, CasterTiles)` -> mirror `ctx.plans` (les `attackPlans` de
        l'attaque normale, qui portent la cascade de ciblage native) restreint aux evals dont
        `ranked` contient `caster_tile` — c'est bien « valide DEPUIS cette tuile ».
        `SortByDistance(..., Caster)` -> distance a `ctx.origin` (position REELLE du caster).
        `First(1)` -> le minimum, keep-first a egalite (`OrderBy` LINQ est stable).

        Les positions passent par le FOYER `engine.ai.cast_positions` (#350-r3a-r4) : sur la face
        DECISION `computeAttackPlans` TRONQUE a `maxRank`, donc une tuile legale ecartee par le
        plafond faisait declarer la cible NON valide depuis `caster_tile` -- et `SelectFirst`
        elisait alors une autre cible, ou aucune."""
        legal: list = []
        for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or []):
            if ev.get("abilityId") not in ctx.normal_ids or not ev.get("rankCount"):
                continue
            positions = CP.positions_castables(ev, getattr(ctx, "cast_from_tiles", None),
                                               ctx.uid, ev.get("targetId"),
                                               ev.get("abilityId"), ctx.origin)
            if caster_tile in positions:
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
        """`IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill(caster, target, casterTile)` —
        FOYER `BasePlaybook.will_normal_attack_kill` (`base.py`), partagé avec les quinze playbooks
        de `normal_attack_kill_gate` et la route NonComparable. La cible est ici l'ALLIÉ visé — le
        natif ne teste PAS le camp."""
        return self.will_normal_attack_kill(ctx, target, caster_tile)

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
        """`...SorcerousFacadePlaybook$$MakeDamagePredictions` — la SEULE chose que cet override
        ajoute au chemin generique est la SUBSTITUTION DE CIBLE :

            sel = SelectFirst(GetTarget(ability), entities{Caster, CasterTile, CasterTiles})
            if (sel == null) return <liste VIDE statique>;
            <la suite est le regime generique, evalue sur `sel`>

        La cible passee en argument (l'ALLIE Psyker) n'entre PAS dans la prediction : le natif la
        remplace par `sel`, l'ENNEMI le plus proche attaquable a l'attaque normale. Tout le reste --
        l'event d'attaque normale EN TETE, puis l'`AddRange` du batch `GenerateMultiHitAttack
        Predictions(base = Half(Sum(minDmg, maxDmg)), hits = nrOfHits, profil = <vide>)` -- est le
        corps GENERIQUE, porte par `prediction.make_damage_predictions`
        (`_PREPEND_NORMAL_ATTACK_EVENT` + `_PLAYBOOK_PROFILE_OVERRIDE[1100]`).

        ⚠ CE CORPS RECONSTRUISAIT LES DEUX EVENTS A LA MAIN, et c'etait un FORK DE PORT : le meme
        artefact natif avait DEUX implementations Python, dont une seule etait juste. Le chemin
        generique, lui, rendait UN event (il SUBSTITUAIT l'attaque normale au batch au lieu de l'y
        AJOUTER) -- c'est le residu #351, mesure par `probe_351_facade_event_count.py` : natif
        `count = 2`, chemin generique 1. La reparation a eu lieu la-bas ; ici il ne reste que la
        substitution de cible, qui est la seule chose que le natif ecrit de special.

        L'ancienne mise en garde « ne pas deleguer : ca produirait DEUX fois l'attaque normale »
        etait vraie DU TEMPS de la substitution (`u_pred` 54.660 vs `pairUtility(1100)` natif
        27.340). Elle ne l'est plus : le chemin generique ne produit l'attaque normale qu'UNE fois,
        en tete, et le test `test_prediction_stage_matches_native` garde ce chiffre."""
        if ctx.scene is None:
            return []
        sel = self._get_target(ctx, caster_tile)
        if sel is None:
            return []                        # la liste VIDE statique du natif
        return prediction.make_damage_predictions(
            ctx.scene, ctx.uid, sel, self.ability_id,
            ctx.ab_name_by_id.get(self.ability_id), attack_pos=caster_tile)


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
class MortisRoundPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility` -- le GAIN d'utilite
    de TUILE que le PUSH inflige a la cible, TRONQUE vers `int`.

        Fix64 CalculateCustomUtility(caster, casterPosition, target, abilityState, possibleTargets) {
            var best = GetTargetUtilityDiffOnDisplace(caster, casterPosition.MainTile,
                                                     this.GetPushableTiles, target);
            return (Fix64)(int)best.<+0x18>;              // op_Explicit puis op_Implicit
        }

    et `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetTargetUtilityDiffOnDisplace`,
    relu VERBATIM :

        best = (target, Fix64(0))
        if (!UnitExtensions.IsDisplaceable(target)) return best;      // -> 0
        util = GetUtility(UtilityType.Tile);                          // composite 7
        t0   = EntityExtensions.GetMainTile(target)
        u0   = util.EvaluateAttack(UtilityAttackCase.Base(target, UnitPosition(t0), t0, aoe))
        foreach (tile in tilesFunc(casterTile, target)) {
            uN   = util.EvaluateAttack(UtilityAttackCase.Base(target, UnitPosition(tile), tile, aoe))
            diff = u0 - uN
            if (diff > Fix64(0) && diff > best.value) best = (target, diff)
        }
        return best

    CINQ points de RE, dont trois ne se devinent pas :

    1. **L'unite du `UtilityAttackCase` est la CIBLE**, jamais le caster (`+0x10` = `target`). Les
       feuilles Tile(7) recopient ce champ dans `UtilityMovementCase+0x10` puis le passent a
       `HasTrait(case.unit, ...)` / `HasFaction(case.unit, ...)` -> le composite doit etre evalue
       AVEC LE KIT DE LA CIBLE (`base.tile_utility_for_unit`), pas celui du lanceur.
    2. **`EvaluateAttack` sur le composite Tile(7) EST `EvaluateMovement`.** Ce n'est pas une
       supposition de commodite : chaque feuille de tuile convertit son `UtilityAttackCase` en
       `UtilityMovementCase` et saute au slot `EvaluateMovementInSteps` (corps IDENTIQUES de
       `IdunBattle.AI.Utilities.ElevationUtility$$EvaluateAttackInSteps`,
       `...AUnitEffectsUtility$$EvaluateAttackInSteps`,
       `...CapturePointTileUtility$$EvaluateAttackInSteps`). Le facteur de
       `IdunBattle.AI.Utilities.ComposedUtility$$CalculateAttackModifier` vaut 1 ici : les TROIS
       seules utilities qui l'overrident (`DislikeBossUtility`, `DislikeEnvironmentUnitsUtility`,
       `DislikeObjectsUtility`) appartiennent au composite d'ATTAQUE, aucune a Tile(7).
    3. **La TRONCATURE vers `int`** (`Fix64$$op_Explicit` puis `op_Implicit`) est ce qui explique le
       « terme mesure nul » des tranches 1-3 : elle ecrase vers 0 tout gain `< 1`, et sur un plateau
       PLAT le composite Tile(7) est constant, donc `diff == 0` partout. Le terme n'existe qu'avec
       une feuille de tuile DISCRIMINANTE (elevation en tete : `Elevation.Multiplier` = 10 par
       niveau -> un push d'un niveau vaut deja 10 points d'utilite d'action).
    4. **C'est un MAX, gate a `> 0`** : les tuiles de push qui AMELIORENT la position de la cible
       n'apportent aucun malus (le terme ne descend jamais sous 0), et deux tuiles candidates ne
       s'additionnent pas.
    5. **La liste de tuiles est l'arc ARRIERE, pas la destination reelle du push.**
       `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetPushableTiles`
       = `EmptyOrHasSteppableUnit(battleQuery.<slot itf 0x4e>(casterTile, target))`, et le slot
       0x4e est `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile` (index de
       vtable 0x52, `interfaceOffset` = 4 -- RE-DERIVE au runtime, pas recopie d'une fiche). La
       DECISION ne rejoue donc pas `FindTileToPush` (le tirage de la face COMBAT) : elle score
       l'arc entier. Sur un push melee axis-aligne l'arc est degenere en UNE tuile, les deux
       coincident ; hors alignement l'arc peut porter DEUX tuiles et le natif prend le MAX.

    Terme POSITION-dependant (`casterTile` oriente l'arc) ET CIBLE-dependant : il arbitre a la fois
    l'argmax par tuile et l'argmax par cible.

    Porteur `ultraEliminatorSgt` 'Certus' [lineup, **present dans `rl_duel build --list-pool`**] --
    le seul override non porte de #27 dont le porteur soit un HERO du pool, sans catalog_inject ni
    greffe. AUCUN poids BC : la magnitude sort entierement du composite Tile(7).

    RESIDU nomme : `IsDisplaceable` teste aussi `HasFlag(unit, 0x19)`, un `UnitFlag` que le substrat
    de DECISION (`decisionView`) n'expose pas -> gate INERTE (borne SUPERIEURE, jamais une tuile
    retiree a tort). Les quatre autres refus (mort, `Hulking`=3, `Immovable`=17, `BigTarget`=1017)
    sont portes.

    ⚠ #977 -- LES DEUX CORPS GENERIQUES ONT DEMENAGE dans `playbook/displace_utility.py`. Ils
    vivent sur la BASE `Playbook`1`, donc `1043 ThunderousAssault` (NonComparable) les appelle a
    l'identique ; les dupliquer aurait fait deux exemplaires libres de diverger, exactement le
    gisement que #498-r4 a ferme sur `NOT_DISPLACEABLE_TRAITS`. Ce qui RESTE ici est ce qui
    appartient VRAIMENT a `MortisRoundPlaybook$$CalculateCustomUtility` : la TRONCATURE vers `int`
    (`Fix64$$op_Explicit` puis `op_Implicit`), absente du corps generique."""
    ability_id = int(ActiveAbilityType.MortisRound)  # 1004

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        """1004 declare AUSSI son propre `ShouldExecute` (slot +0x328) -- et son corps est celui que
        la table des symboles attribue a
        `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute`, partage par QUATORZE
        classes (dedup IL2CPP ; recensement niveau par niveau, cf. `normal_attack_kill_gate`) :

            return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

        Cette classe est la SEULE des quatorze deja au registre (pour son `CalculateCustomUtility`)
        -- d'ou la delegation ici plutot qu'une seconde inscription."""
        return not self.will_normal_attack_kill(ctx, target, caster_tile)

    # `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` : les trois traits qui REFUSENT le
    # deplacement, lus au decompile (`BaseUnitComponent$$HasTrait` avec 0x11, 0x3, 0x3f9).
    # #498-r4 : la liste n'est plus RECOPIEE ici -- c'est le tuple du foyer runner
    # (`runner/components.py::NOT_DISPLACEABLE_TRAITS`). Trois exemplaires du meme tuple etaient
    # libres de diverger, et c'est le gisement exact que #498-r3 a ferme cote RUNNER.
    _NOT_DISPLACEABLE = NOT_DISPLACEABLE_TRAITS

    _unit = staticmethod(_displace.unit_of)

    @classmethod
    def _is_displaceable(cls, ctx, unit: dict) -> bool:
        """`IdunBattle.Entities.UnitExtensions$$IsDisplaceable(unit)` : vivante, et sans aucun des
        trois traits refusants.

        ⚠ #977 -- LE CORPS EST DANS `playbook/displace_utility.py` (foyer partage avec `1043`). Ce
        qui reste ici est l'alias : la docstring ci-dessous est la MESURE, elle ne doit pas se
        dupliquer avec le corps.

        DEUX des cinq conditions natives ne sont PAS portees ici, et #498-r4 les a MESUREES plutot
        que supposees -- les deux verdicts sont « ne pas cabler », pour deux raisons DIFFERENTES :

        * `HasFlag(unit, 0x19 = UnitFlag.Undisplaceable)` -- le substrat de DECISION ne publie que
          quatre `UnitFlag`. Recensement EXHAUSTIF des ecrivains natifs du flag (les DEUX voies) :
          `IdunBattleLogic.Entities.DSLBehaviors$$AddFlag` a **10** appelants, litteral relu a
          chacun, et UN SEUL pose `0x19` -- `IdunBattleLogic.Entities.Abilities.Active.Loki.
          UnstoppableMomentumReworkedAbility$$ExecuteBehaviour`, qui porte aussi le `RemoveFlag`
          apparie ; `IdunBattle.Entities.Components.UnitFlagsComponent$$Add` a **40** sites de jeu,
          litteral relu a chacun, qui posent 21 ordinaux distincts et JAMAIS `0x19` ; et
          `UnitFlagsComponent$$.ctor` construit un `OrderedSet` VIDE (aucune unite ne nait avec).
          Le flag n'existe donc qu'a l'INTERIEUR d'une execution d'ability, ou la decision
          n'evalue jamais. Direction si le port se trompait : PERMISSIVE.
        * `GetEntityType(unit) != EntityType.Unit` -- STRUCTURELLEMENT inerte : le `unit` vient de
          `ctx.units`, dont le foyer offline (`ai/state_bridge.py::_dv_units`) EXCLUT les MoW
          (`is_machine_of_war(e) -> continue`) et dont le foyer live est `decisionView.units`,
          canal separe de `.mows`. Et `_unit` rend `None` sur tout id qui n'est pas dans cette
          liste, ce que la premiere ligne refuse deja.

        Le gate `alive` en tete, lui, est un ECART du port : le natif ne teste AUCUNE liveness
        (cf. `runner/components.py::unit_extensions_is_displaceable`). RESTRICTIF, conserve."""
        return _displace.is_displaceable(ctx, unit)

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        # `GetTargetUtilityDiffOnDisplace(caster, casterTile, this.GetPushableTiles, target).<+0x18>`
        # -- corps GENERIQUE (`Playbook`1`), foyer `playbook/displace_utility.py` (#977).
        best = _displace.target_utility_diff_on_displace(ctx, caster_tile, target)
        # `Fix64$$op_Explicit` (Fix64 -> int) puis `op_Implicit` (int -> Fix64) : TRONCATURE vers
        # zero, pas un arrondi -- et elle appartient a CE corps-ci, pas au generique. `best` est
        # >= 0 par construction, donc `int()` suffit.
        return float(int(best))


def _mortarions_plague_wind_dsl_context(ctx, target):
    """Le `DslContext` d'evaluation des vagues de 1093, cote DECISION.

    Mirror de l'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor(this, caster, actor, target,
    owner, casterTile, ...)` que `...MortarionsPlagueWindPlaybook$$CalculateCustomUtility` construit
    apres avoir memset ses 0x128 octets a ZERO : il n'ecrit QUE trois arguments non nuls --
    `caster = caster`, `actor = caster`, `target = target`. TOUT le reste est nul, `owner` et
    `casterTile` COMPRIS.

    ⚠ CONSEQUENCE PORTEE, et elle differe de 1009/1216 : **aucun `caster_pos`**. Le natif ne
    transmet PAS `casterPosition` a l'`AbilityEntities` (l'argument existe pourtant dans la signature
    de `CalculateCustomUtility`, il n'est simplement jamais lu ici), et aucun nœud de la chaine ne
    lit la tuile du caster -- `Enemies` referme `<DSLSelectors+0x48>` = Caster, dont le selecteur ne
    consulte que le CAMP. Le terme est donc CONSTANT sur le sweep de tuiles et ne depend que de la
    CIBLE. Deplacer le caster dans `units` (ce que fait `resurrection_orb._dsl_context`, dont les
    arbres lisent `CasterTile`) serait ici une invention.

    `has_trait` est l'unique accesseur hors-state exige (le `Psyker` d'`UnitsWithTrait`) ; il lit le
    `UnitContext` de la `Scene`, le MEME objet que `StatsComponent.ctx` cote runner."""
    scene = getattr(ctx, "scene", None)
    if scene is None or getattr(scene, "board", None) is None:
        return None
    units = list(ctx.units or [])
    by_id = {u.get("id"): u for u in units}
    caster, tgt = by_id.get(ctx.uid), by_id.get(target)
    if caster is None or tgt is None:
        return None
    vis_by_id = {u.get("id"): u.get("visualId") for u in units}

    def _has_trait(u, trait) -> bool:
        uid = (u or {}).get("id")
        return has_trait(entity_trait_names(scene.ctx(uid), vis_by_id.get(uid)), trait)

    return dsl.DslContext(units=units, caster=caster, target=tgt, board=scene.board,
                          elev_by_pos=ctx.elev_by_pos, has_trait=_has_trait)


class MortarionsPlagueWindPlaybook(_CustomOnlyPlaybook):
    """`IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$CalculateCustomUtility` (#27-r5) :

        t1 = <ability>.GetTarget()                 // ghidra: StrikeFromTheShadowsAbility$$GetTarget
        t2 = <ability>.GetSecondaryTargets(t1)     // ghidra: StormOfWrathAbility$$<ExecuteBehaviour>b__1_0
        t3 = <ability>.GetTargets3(t1, t2)         // ghidra: PlagueWindAbility$$GetTargets3
        sel = DSLSelectors.UnitsWithTrait(t1 + t2 + t3, 0x3ea = Psyker, 3);
        return Fix64.op_Implicit( sel.<vslot 0x18 = Count>( AbilityEntities(caster, caster, target) ) );

    **AUCUN `GetUtilityValue`, aucune constante multiplicative : le COMPTE EST l'utilite.** Le
    `Count` est le slot virtuel 0x18 de `IdunBattle.DSL.TargetsSelector` (dont l'implementation de
    base, `IdunBattle.DSL.TargetsSelector$$Count`, vaut `Enumerable.Count(this.<vslot 0x17 =
    Select>(entities))`), et `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` ne recoit que
    `caster`/`actor`/`target` -- cf. `_mortarions_plague_wind_dsl_context`.

    Les trois vagues sont le mirror `plague_wind_wave_selectors()`
    (`runner/abilities/deathguard.py`), ou vit deja la MEME chaine pour la face COMBAT de son jumeau
    `PlagueWind` (1035, `deathTyphus`) : un seul artefact natif, un seul port. Ce qui les distingue
    n'est PAS la geometrie mais le `DSLSelectors$$Cache` que les deux `ExecuteBehaviour` posent et
    que le playbook n'a pas (cf. le bloc de commentaire de `deathguard.py`).

    LE VERROU ANNONCE N'EN ETAIT PLUS UN. La fiche #27-r5 tenait « l'evaluateur DSL `UnitsWithTrait`
    + la chaine `AdjacentUnits` a 3 vagues n'est pas portee cote decision ». Re-derive du code : les
    quatre primitives (`AdjacentUnits`/`adjacent_units`, `Enemies`, `Unique`, `UnitsWithTrait`) et
    les deux combinateurs (`Union` = `op_Addition`, `Sub` = `op_Subtraction`) sont TOUS portes dans
    `entities/selectors/`, et la voie « playbook -> `DslContext`  -> arbre de l'ability » a deja deux
    precedents (`resurrection_orb`, `playbook/tile_targets.py`). Il n'y avait aucune primitive a
    porter : seulement un contexte a monter.

    ROUTE : `_best_attack` (route d'ATTAQUE standard) -- 1093 a un `constants.damageProfile`
    (`Psychic`) et son masque EFFECTIF est `0x4002` = `TargetIsEnemy | TargetMatchesDynamicRule`
    (cf. `TARGETING_OPTIONS_UNPORTED[1093]`), donc des cibles ENNEMIES, pas un self-cast. Rien a voir
    avec la seconde route Comparable de 1216/1226/1185/1100.

    TERME INDEPENDANT DE LA TUILE D'ATTAQUE (cf. `_mortarions_plague_wind_dsl_context`) : il
    departage les CIBLES entre elles, jamais deux tuiles pour une meme cible.

    Porteur `deathBossMortarion` [npc] (unique, `unit_map find --ability MortarionsPlagueWind`) ->
    GREFFE sur une unite du pool (`case-92` §5bis). La greffe est legitime ICI parce que la formule
    ne lit NI stat NI trait NI arme NI portee du CASTER : le seul trait teste (`Psyker`) est celui
    des unites SELECTIONNEES, et le caster n'entre que comme referent d'inimitie (= son CAMP)."""
    ability_id = int(ActiveAbilityType.MortarionsPlagueWind)   # 1093 = 0x445

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        dctx = _mortarions_plague_wind_dsl_context(ctx, target)
        if dctx is None:
            return 0.0
        sel = mortarions_plague_wind_psyker_selector()
        return float(len(sel.evaluate(dctx)))


class MartialExemplarPlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.MartialExemplarPlaybook$$CalculateCustomUtility` (#27-r4) :

        n = Enumerable.Count(battleQuery.<slot itf 0x80>(casterPosition, caster,
                                                         ignoreSteppables: false),
                             UnitExtensions$$IsNormalUnit);
        return Fix64.op_Implicit(n * 1000);

    et son gate `...MartialExemplarPlaybook$$ShouldEvaluate(unit, position, possiblePositions)`
    (slot de vtable 6, appele PAR TUILE) :

        return battleQuery.<slot itf 0x80>(position, unit, false).Count > 0;

    ATTENTION -- ce second corps ne filtre PAS par `IsNormalUnit` : le gate compte TOUS les ennemis
    adjacents, l'utilite seulement les `IsNormalUnit`. Les deux comptes DIVERGENT des qu'un ennemi
    `Object`/`Steppable` est adjacent (l'action est alors generee avec `custom = 0`), et les
    confondre serait un port FAUX dans exactement ce regime.

    ANCRAGE DU SLOT 0x80 = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, unit,
    ignoreSteppables)` : le decorateur enregistreur
    `...RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass155_0$$u003CGetAdjacentEnemiesu003Eb__0`
    emet ce slot exact (et les DisplayClass 149/150/151 emettent 0x7a/0x7b/0x7c pour
    `GetAdjacentUnits`, la 147 emet 0x78 pour `GetSurroundingEnemies`). Son corps ne lit du `unit`
    que `IdunBattle.Entities.Components.OwnerComponent$$get_CurrentPlayerEntityId` -- le CAMP, ni
    stat ni trait ni arme ni portee. C'est CE fait qui rend l'ability greffable alors que son seul
    porteur, `darkaBossLion`, est un npc (`case-92` §5bis).

    POURQUOI LA ROUTE NON-ATTAQUE, alors que 1216 a un `damageProfile` (`constants.damageProfile` =
    `Power`) : son masque EFFECTIF est `0x8014` = `CasterIsPossibleTarget | CasterHasNotMoved |
    CasterMatchesDynamicRule` (cf. `TARGETING_OPTIONS_UNPORTED[1216]` -- forme PRESET+FLAGS, le
    litteral `0x10` du ctor n'est PAS le masque). L'ability est donc **SELF-CAST** : le natif ne
    retient qu'une cible, le CASTER. Mesure live : `abilityTargets(1216)` rend `[(unit, <caster>)]`,
    et les `attackPlans.evals` de 1216 sur les ENNEMIS rendent tous `rankCount = 0` -- `_best_attack`
    ne peut donc rien produire, exactement le critere de cette seconde route (cf. l'en-tete de
    `nonattack.py`, et le meme diagnostic que 1009 ResurrectionOrb).

    `make_damage_predictions` -> `[]` (herite) : la cible etant le caster lui-meme, le natif ne
    predit aucun degat sur elle -- MESURE `pairUtility(1216, SELF) = 0`, sur les trois tuiles
    testees. L'utilite d'action se reduit donc a `custom + tile_utility`, ce que fait la route.

    MAGNITUDE NON DISCRIMINABLE, et c'est ecrit plutot que masque : `CasterHasNotMoved` interdit le
    cast apres deplacement, et la cible est unique -> il n'existe qu'UNE action 1216 par tour. Le
    terme `1000 x n` ne departage donc jamais deux actions de 1216 entre elles ; face aux autres
    abilities il gagne des `n >= 1`. Toute constante >= ~10 produirait la meme decision. Ce qui EST
    mesure (`probe_27_r4_martial_exemplar.py`, 4 bras) : le GATE (n=0 -> le natif prend l'attaque
    normale ; n=1 et n=2 -> il prend 1216 sur lui-meme) et `CasterHasNotMoved`.

    Porteur `darkaBossLion` [npc] -> GREFFE sur `darkaAsmodai` (Dark Angels, melee, dans
    `rl_duel build --list-pool`). La greffe ne couvre pas les stats/traits/armes du vrai porteur --
    elle est legitime ICI parce que la formule n'en lit aucun."""
    ability_id = int(ActiveAbilityType.MartialExemplar)   # 1216 = 0x4c0
    ADJACENT_ENEMY_UTILITY = 1000.0     # CONSTANTE EN DUR du natif : aucun `GetUtilityValue`

    def _adjacent_enemies(self, ctx, caster_tile):
        """`battleQuery.<slot itf 0x80>(caster_tile, caster, ignoreSteppables: false)` — les ENNEMIS
        du caster sur une tuile adjacente a `caster_tile`. Mirror via `ctx.enemies` (le camp est
        deja resolu par `decisionView`, comme le `CurrentPlayerEntityId` du natif) et la porte
        d'elevation d'`is_adjacent`."""
        return [u for u in (ctx.enemies or [])
                if bq.is_adjacent(caster_tile, ((u.get("pos") or {}).get("col"),
                                                (u.get("pos") or {}).get("row")),
                                  ctx.elev_by_pos, bq.neigh_map(ctx))]

    def should_evaluate(self, ctx, caster_tile, ability_id) -> bool:
        """`...MartialExemplarPlaybook$$ShouldEvaluate` = `GetAdjacentEnemies(position, unit,
        false).Count > 0` — SANS filtre `IsNormalUnit` (cf. la docstring de classe)."""
        return bq.count_adjacent(caster_tile, ctx.epos, ctx.elev_by_pos, bq.neigh_map(ctx)) > 0

    def is_caster_added(self, ctx, caster_tile) -> bool:
        """Mirror du bit `CasterHasNotMoved` (0x10) du masque effectif `0x8014` :
        `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` refuse le cast des que le
        caster a quitte sa tuile d'origine. Cote decision, cela retire de l'enumeration toute tuile
        candidate autre que l'origine — sans ce mirror, le moteur proposerait 1216 depuis n'importe
        quelle tuile atteignable, une degradation PERMISSIVE que le natif refuse (mesure : un
        `act move` du caster fait tomber `abilityTargets(1216)` a ZERO cible)."""
        return caster_tile == ctx.origin

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        n = bq.count_adjacent_matching(
            caster_tile, ctx.enemies,
            lambda u: is_normal_unit(u.get("traits")), ctx.elev_by_pos, bq.neigh_map(ctx))
        return float(n) * self.ADJACENT_ENEMY_UTILITY


class TheLionsWrathPlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.TheLionsWrathPlaybook$$CalculateCustomUtility` (#27-r4) :

        n = 0; hits = 0;
        foreach (e in battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false))
            if (UnitExtensions.IsNormalUnit(e)
                && UnitExtensions.HasTrait(e, 0x7ea)      // Chaos
                && UnitExtensions.HasTrait(e, 0x10))      // Hero
                n++;
        var w = battleQuery.<slot itf 0xb2>(target);      // FindMeleeWeapon(TARGET)
        if (w != null) hits = w.<+0x20>;                  // Hits
        return Fix64.op_Implicit(hits * 0x1e + n * 2000
                                 + (UnitExtensions.HasTrait(target, 0x10) ? 0x96 : 0));

    AUCUN `GetUtilityValue` : les trois magnitudes (`0x1e` = 30, `2000`, `0x96` = 150) sont EN DUR
    dans le corps natif -- il n'existe aucune cle de poids BC a resoudre pour cette ability.

    CE QUI REND CE TERME DISCRIMINABLE, et c'est ce qui le distingue des trois autres customs
    « npc-only » de la meme tranche : ses DEUX premiers facteurs sont lus sur la **CIBLE**
    (`FindMeleeWeapon(target).Hits`, `HasTrait(target, Hero)`), donc il DEPARTAGE deux cibles d'une
    MEME ability -- ce qu'un terme purement caster-dependant (1215, 1216) ne peut jamais faire. Le
    3e facteur (`n`) depend de `casterPosition` et pas de la cible : il est constant sur la boucle
    MINEURE et n'arbitre que la TUILE, exactement comme le terme de 1216.

    ANCRAGE DES DEUX SLOTS D'INTERFACE (par le decorateur enregistreur, jamais par recopie de fiche) :
    `...RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass155_0$$u003CGetAdjacentEnemiesu003Eb__0`
    emet le slot **0x80** = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, unit,
    ignoreSteppables)`, et `...u003Cu003Ec__DisplayClass212_0$$u003CFindMeleeWeaponu003Eb__0` emet le
    slot **0xb2** = `IdunBattle.Core.Services.BattleQuery$$FindMeleeWeapon(unit)`, la surcharge a UN
    argument (cf. `services/battle_query.py::find_melee_weapon`). ⚠ Le numero de DisplayClass n'est
    PAS un index de slot -- chacun est lu dans le corps de SON display class.

    POURQUOI L'ABILITY EST GREFFABLE malgre un porteur `darkaBossLion` [npc] : le natif charge le
    playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), jamais par unite, et de son
    CASTER cette formule ne lit que le CAMP -- `...$$GetAdjacentEnemies` n'interroge du `unit` que
    `IdunBattle.Entities.Components.OwnerComponent$$get_CurrentPlayerEntityId`. Ni stat, ni trait,
    ni arme, ni portee du caster. L'arme et le trait `Hero` lus sont ceux de la CIBLE ; les traits
    `Chaos`/`Hero` filtres sont ceux des ADJACENTS (`case-92` §5bis).

    LE MASQUE : `0x4000` = `TargetIsEnemy` SEUL. `IdunBattleLogic.Entities.Abilities.Active.Loki.
    TheLionsWrathAbility$$.ctor` recopie les 0x40 octets du preset `<TargetingOptions statics>+0x40`
    et les passe TELS QUELS a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts,
    abilityAttackType)` -- dont le corps recopie la struct sans OU-er le moindre flag (pas le piege
    PRESET+FLAGS de 1216 ; le 3e argument est l'`AbilityAttackType`, ici le litteral 0). La cible est
    donc un ENNEMI, jamais le caster : `TARGETING_OPTIONS_UNPORTED[1217]`, sa face COMBAT n'etant pas
    portee.

    ROUTE NON-ATTAQUE, et pour une raison DIFFERENTE de celle de 1216 (qui y est parce que son masque
    est SELF-CAST) : ici c'est le motif de **1009 ResurrectionOrb** --
    `...TheLionsWrathPlaybook$$MakeDamagePredictions` rend une liste VIDE (cf. son override
    ci-dessous), donc `calculate_action_utility` rend `None` et `_best_attack` **ne peut
    structurellement pas** la produire (son gate `best[0] > 0` porte sur la seule utilite de DEGAT).
    Le critere de `nonattack.py` -- « Comparable INVISIBLE de `_best_attack` » -- est donc rempli, et
    ce alors meme que 1217 a un `constants.damageProfile` (`Power`) ET des `attackPlans` a
    `rankCount > 0`. C'est le 4e motif d'entree dans cette route.

    ⚠ Ce qui SEPARE les deux routes ici n'est pas cosmetique : `nonattack_candidates` mirroir
    `CalculateActionUtility` a la lettre -- `u = custom` PUIS `u += Sigma predictions` PUIS
    `ShouldExecute(u)` -- donc il passe au gate `custom + predictions`, ce que fait le natif. La
    route d'attaque, elle, gate sur les predictions SEULES et supprimerait l'action. MESURE : sans
    ce routage le moteur rendait `(None, None)` la ou le natif emet `ActiveAbilityMessage(1217)`.

    LE GATE N'EST PAS PORTE, et c'est un FAIT LU, pas un oubli.
    `...TheLionsWrathPlaybook$$ShouldEvaluate(unit, position, possiblePositions)` (surcharge 4-args,
    slot de vtable 6, celui qu'expose `NonAttackComparablePlaybook.should_evaluate`) relu A
    L'ASSEMBLEUR -- le decompile Ghidra `(extraout_var >> 7 ^ 1) & bVar1` modelise sur un OCTET un
    decalage qui porte sur 32 bits :

        call  <slot 0x1b>(unit, 2)      ; HasMinimumRemainingTurns  -> movzx ebp, al
        call  <slot 0x80>(position, unit, false)                    ; GetAdjacentEnemies
        call  <Count>                                               ; -> eax
        shr   eax, 0x1f                 ; bit de SIGNE du compte
        xor   al, 1                     ; -> (count >= 0)
        and   al, bpl                   ; & HasMinimumRemainingTurns

    Le second terme est donc `Count() >= 0`, **TOUJOURS VRAI** pour un compte -- et ce n'est PAS ce
    que fait sa jumelle : `...MartialExemplarPlaybook$$ShouldEvaluate`, structurellement identique,
    finit par `cmp eax,1 ; setge al` = `Count() > 0`. Les deux fonctions different EXACTEMENT la, ce
    qui est la contre-epreuve du decodage. Recopier `> 0` par analogie aurait pose un gate que le
    natif n'a pas. Reste `HasMinimumRemainingTurns(unit, 2)`, dont
    `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` **n'utilise pas** son parametre
    `unit` : `limit = <victoryConfig @+0xb0>.<+0x18>[MainPlayerRoundLimitation]` ;
    `if (!limit.HasValue) return true` ; sinon
    `turns <= limit - TurnComponent$$GetAmountOfTurnsEndedByPlayer(GetPlayerTurnOrder()[0])`. Gate
    GLOBAL au match, neutre au porteur, et VRAI des que la limite de rounds est absente.
    ⚠ FICHE CORRIGEE (#287-r11-r1-r1) : « le PLAFOND DE TOURS DU MATCH n'a aucun substrat cote
    port » est PERIME. Le dictionnaire est `BC.Victory.VictoryConditions`, que le port lit
    (`engine.services.victory_config.get_max_rounds`, defaut DERIVE de `data/seed-bc.json`), et le
    mirror complet est `engine.services.battle_query.has_minimum_remaining_turns` -- desormais
    branche sur le bit `CasterHas2TurnsLeft` de 1160/1142/1188. Le COMPTEUR `TurnComponent+0x40` du
    SECOND bras, qui manquait encore, est porte depuis `#287-r11-r1-r1-r1` (`State.turns_ended`,
    ecrit par `turnflow.set_current_player`). Le gate se
    reduit donc a `True` PAR LECTURE sur toute BC sans `MainPlayerRoundLimitation`, c.-a-d.
    exactement le defaut de `NonAttackComparablePlaybook.should_evaluate` : l'overrider pour rendre
    `True` inconditionnellement serait du code mort. RESIDU NOMME `#27-r4-g` -- il ne pourra mordre
    que dans un match A PLAFOND DE ROUNDS, regime qu'aucun runner d'arene ne monte a ce jour.

    Porteur `darkaBossLion` [npc] -> GREFFE sur une unite du pool ; la greffe ne couvre pas ses
    stats/traits/armes, ce qui est legitime ICI puisque la formule n'en lit aucun."""
    ability_id = int(ActiveAbilityType.TheLionsWrath)   # 1217 = 0x4c1
    TARGET_MELEE_HIT_UTILITY = 30.0        # `iVar8 * 0x1e`
    ADJACENT_CHAOS_HERO_UTILITY = 2000.0   # `iVar7 * 2000` (litteral DECIMAL du decompile)
    HERO_TARGET_UTILITY = 150.0            # `-(uint)(HasTrait(target, Hero)) & 0x96`

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`...TheLionsWrathPlaybook$$MakeDamagePredictions` rend une **liste VIDE** -- l'ability ne
        predit AUCUN degat, et ce n'est pas une degradation du port mais le comportement natif.

        Comment on le sait, alors que le symbole n'apparait pas dans la table (corps DEDUPLIQUE) :
        `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions`
        est ABSTRAITE -- son corps entier est `FUN_1801f4390(<classe>, 0)`, c.-a-d. la levee
        `NotImplementedException`. Un override EXISTE donc forcement, et TROIS canaux INDEPENDANTS
        disent qu'il rend une liste vide NON NULLE :
          1. `aiPlaybookPredict(1217)` -> `retClass = ProbableDamageEvent[]`, `listNull = false`,
             `count = 0` (l'appel REUSSIT, il ne leve pas) ;
          2. `pairUtility(1217)` = `...$$CalculateUtilityFromPredictions` NATIF -> `utility = 0`,
             `utilRaw = "0"`, sur TOUTE cible ;
          3. COMPORTEMENTAL, et c'est le canal decisif : dans le bras `--hp-ahriman 100` de
             `probe_27_r4_lions_wrath.py`, les deux cibles ont des `u_full` de preview qui
             divergent de bien plus que l'ecart de custom (120), et le natif choisit malgre tout la
             cible d'argmax(CUSTOM). Il n'ajoute donc AUCUNE utilite de degat.
        Coherent avec le kit : `...TheLionsWrathAbility$$ExecuteBehaviour` differe l'attaque dans
        `IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect` (declenche par
        `On(...)`), il n'y a pas de degat a predire AU MOMENT DU CAST.

        ⚠ Sans cet override, le chemin generique de `DefaultActiveAbilityPlaybook` fabrique une
        prediction depuis `attackPlans` -- que `projection.ts` remplit avec la PREVIEW de l'attaque
        normale pour une ability sans prediction de playbook (mesure : `dmgMin/dmgMax` de 1217
        IDENTIQUES a ceux de 69 sur les deux cibles). C'est cette prediction fantome qui faisait
        DIVERGER le port du natif sur le bras discriminant.

        Il est REDONDANT avec le corps de `NonAttackComparablePlaybook` -- et il est ecrit quand meme,
        parce que la RAISON differe : la base y rend `[]` « parce que l'ability n'a pas de
        `damageProfile` », ce qui est FAUX ici (1217 en a un, `Power`). Effacer cette distinction
        laisserait croire que le routage de 1217 se deduit de son gameconfig."""
        return []

    @staticmethod
    def _unit(ctx, entity_id):
        for u in (ctx.units or []):
            if u.get("id") == entity_id:
                return u
        return None

    @staticmethod
    def _traits(ctx, unit) -> frozenset:
        """Le substrat COMPLET de `BaseUnitComponent$$HasTrait` cote decision : kit gameconfig +
        traits accordes en bataille + pseudo-trait de GRANDE-ALLIANCE. Ce dernier est INDISPENSABLE
        ici -- `Chaos` (0x7ea) n'est dans AUCUN `traits` de gameconfig, c'est le BattleConfiguration
        qui le pose (`UnitFactory$$InitBaseComponent`). Lire `unit["traits"]` nu, comme le fait
        `MartialExemplarPlaybook` (dont le predicat n'a pas besoin de l'alliance), rendrait ici un
        compte SYSTEMATIQUEMENT NUL, sans erreur ni crash."""
        scene = getattr(ctx, "scene", None)
        uctx = scene.ctx(unit.get("id")) if scene is not None else None
        return entity_trait_names(uctx, unit.get("visualId"))

    def _counts_as_chaos_hero(self, ctx, unit) -> bool:
        """`IsNormalUnit(e) && HasTrait(e, Chaos) && HasTrait(e, Hero)` -- les trois gardes du natif,
        dans leur ordre, sur un ADJACENT. `IsNormalUnit` = `!Object(0xd) && !Steppable(0x1b)`."""
        names = self._traits(ctx, unit)
        return (is_normal_unit(names)
                and has_trait(names, UnitTrait.Chaos)
                and has_trait(names, UnitTrait.Hero))

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        # 1er terme du natif (boucle sur `GetAdjacentEnemies(casterPosition, caster, false)`) :
        # meme `is_adjacent` que `count_adjacent`, donc la meme porte d'elevation
        # d'`IterateAdjacentTiles`. Aucun fork d'adjacence.
        n = bq.count_adjacent_matching(caster_tile, ctx.enemies,
                                       lambda u: self._counts_as_chaos_hero(ctx, u),
                                       ctx.elev_by_pos, bq.neigh_map(ctx))
        tu = self._unit(ctx, target)
        # `FindMeleeWeapon(target)` puis `w.<+0x20>` ; arme absente -> `iVar8` reste 0. Cible non
        # resolue -> le natif appellerait `IsUnit(null)` (faux) puis `HasTrait(null, ...)` (faux),
        # donc les deux termes de CIBLE tombent a 0 : c'est ce que rend cette branche.
        hits = weapon_hits(find_melee_weapon(tu.get("visualId"))) if tu is not None else 0
        hero = (self.HERO_TARGET_UTILITY
                if tu is not None and has_trait(self._traits(ctx, tu), UnitTrait.Hero) else 0.0)
        return (float(hits) * self.TARGET_MELEE_HIT_UTILITY
                + float(n) * self.ADJACENT_CHAOS_HERO_UTILITY
                + hero)


class InstrumentsOfVengeancePlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$CalculateCustomUtility` (#27-r6) :

        adj = battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false);
        u   = adj.Any() ? 0 : 100;
        foreach (e in battleQuery.<slot itf 0x78>(caster, casterPosition, range: 2,
                                                  includeCenter: false))
            if (!adj.Contains(e)) u += 20;
        return Fix64.op_Implicit(u + 20000);

    TROIS constantes EN DUR (`20000`, `100`, `20`) : ce corps n'appelle AUCUN `GetUtilityValue`, donc
    AUCUN poids de `BC.Utilities` n'y entre -- ne pas chercher de cle a resoudre. La base `20000` est
    d'un ordre de grandeur sans equivalent dans le reste du registre (l'utilite d'une action ordinaire
    se compte en dizaines) : des que 1215 est LEGALE, elle est l'action la plus prioritaire du jeu, et
    les deux autres termes ne departagent que des tuiles de cast entre elles.

    LES DEUX SLOTS, ancres par les decorateurs enregistreurs (jamais recopies d'une fiche) :
    `...RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass155_0$$u003CGetAdjacentEnemiesu003Eb__0`
    emet le slot **0x80** = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, unit,
    ignoreSteppables)` (3 arguments), et `...u003Cu003Ec__DisplayClass147_0$$u003CGetSurroundingEnemiesu003Eb__0`
    emet le slot **0x78** = `IdunBattle.Core.Services.BattleQuery$$GetSurroundingEnemies(actor, from,
    range, includeCenter)` (4 arguments). Les deux corps ne lisent du caster que son CAMP
    (`IdunBattle.Entities.Components.OwnerComponent$$get_CurrentPlayerEntityId` pour le premier,
    `IdunBattle.Entities.UnitExtensions$$IsEnemy` capture dans le predicat de
    `Idun.Shared.Extensions.ListExtensions$$FilterInPlace` pour le second) -- ni stat, ni trait, ni
    arme, ni portee. C'est CE fait qui rend l'ability greffable alors que son seul porteur,
    `darkaBossLion`, est un npc (`case-92` §5bis).

    ⚠ LES DEUX ENSEMBLES N'ONT PAS LA MEME GEOMETRIE, et la difference est OBSERVABLE :
    `GetAdjacentEnemies` passe par `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
    qui applique la porte d'elevation `|dElev| < 2` ; `GetSurroundingEnemies` passe par
    `...GetSurroundingUnits` -> `IterateSurroundingTiles`, un disque hex PUREMENT geometrique
    (`IsTileValidForList(..., checkElevation: 0)`, cf. `battle_query.is_surrounding`). Un ennemi a
    distance hex 1 dont l'ecart d'elevation vaut >= 2 est donc DANS `surrounding` et HORS `adj` : il
    compte `+20` **et** laisse le `+100` arme. Ecrire ce terme `20 x |ennemis a distance EXACTEMENT 2|`
    serait un port faux dans exactement ce regime -- d'ou la composition `is_surrounding AND NOT
    is_adjacent`, qui reproduit la difference d'ensembles du natif au lieu de la resumer.

    ROUTE NON-ATTAQUE, alors que 1215 A un `damageProfile` (`constants.damageProfile = HeavyRound`,
    `nrOfHits = 6`) : son masque EFFECTIF est `0x8004 = CasterIsPossibleTarget |
    CasterMatchesDynamicRule` (STATIC-COPY du preset `<TargetingOptions statics>+0x280` --
    `...InstrumentsOfVengeanceAbility$$.ctor` n'appelle AUCUN `TargetingOptions$$.ctor` ; cf.
    `TARGETING_OPTIONS_UNPORTED[1215]`). L'ability est donc SELF-CAST : la seule cible que le natif
    retient est le CASTER, les `attackPlans.evals` de 1215 sur les ENNEMIS rendent tous
    `rankCount = 0`, et `_best_attack` ne peut rien produire -- exactement le critere de cette seconde
    route (meme diagnostic que 1216 MartialExemplar et 1009 ResurrectionOrb).

    DIFFERENCE AVEC 1216, et elle est PORTANTE : 1215 n'a PAS `CasterHasNotMoved(0x10)`. Le cast reste
    donc legal APRES deplacement, et `is_caster_added` garde son defaut permissif (toutes les tuiles
    candidates). C'est ce qui rend le terme reellement POSITION-DEPENDANT ici : le natif evalue
    `CalculateCustomUtility` par tuile candidate dans
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`,
    et il existe autant d'actions 1215 que de tuiles atteignables -- la ou 1216 n'en avait qu'une.

    GATE PORTE (#27-r8) — et le verrou qu'annoncait la redaction precedente etait PERIME.
    `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate(unit)` est la surcharge **2 arguments**
    (slot de vtable 4, appelee UNE fois AVANT la boucle des tuiles -- a ne pas confondre avec la
    4-args slot 6 qu'overrident 1216 et 1217, cf. `nonattack.should_evaluate`) :

        return BasePlaybook.ShouldEvaluate(unit) && battleQuery.<slot itf 0x1b>(unit, 2);

    * `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns(unit, 2)` **n'utilise pas son
      parametre `unit`** : il lit la limite de tours du match (`<config>+0x18`, cle 1) moins
      `IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEndedByPlayer(joueur courant)`,
      et **rend `true` des que la limite est ABSENTE** (`Nullable.HasValue == 0` -> `return 1`). C'est
      un gate GLOBAL, neutre au porteur, et le regime du runner n'a pas de limite -> le defaut
      permissif de la route est EXACT ici. RESIDU : aucun canal offline n'expose cette limite.
    * `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit)` = `p = GetUseProbability(unit)` ;
      `p >= 1 -> true` ; `p <= 0 -> false` ; sinon TIRAGE (`random.<slot 4>(p)`). Et
      `...InstrumentsOfVengeancePlaybook$$GetUseProbability` rend
      `Fix64.Zero` si `GetTurnsFinished(unit) == 0`, `Fix64.Half` si `== 1`, `Fix64.One` sinon
      -- les trois statiques RELUS au `FixMath.NET.Fix64$$.cctor` : `+0x20 = 0x100000000` (One),
      `+0x28 = 0` (Zero), `+0x30 = op_Division(1, 2)` (Half). Le volet `== 1` est un TIRAGE, de
      meme statut que `...PlasmaGrenadePlaybook$$GetUseProbability` (1/3) -- non modelisable
      offline, laisse PERMISSIF et declare. Le volet `== 0`, lui, est DETERMINISTE, et c'est celui
      que ce port mirrore : le natif ne propose JAMAIS 1215 au tour ou l'unite n'a encore termine
      aucun tour.

      ⚠ **Le blocage annonce jusqu'ici -- << `turnsFinished` n'est pas dans `decisionView`, donc il
      faut un CAPTEUR, donc une fenetre de reinject >> -- etait FAUX sur DEUX crans** (#27-r8) :
      (a) le capteur EXISTE deja, livre par #N11 (`getTurnsFinishedMi` +
      `rpc-snapshot.ts::turnsFinished`), et alimente `UnitComponent.turns_finished` que
      `runner/turnflow.py::_bump_turns_finished` tient aussi offline ; (b) surtout, la `Scene` de
      DECISION ne se construit PAS depuis `decisionView` pour ces tables -- `build_predictor` les
      lit dans **`combatSnapshot`**, exactement le canal qui publie le champ, et c'est deja de la
      qu'elle tire `turnsStarted`. Il n'y avait donc rien a instrumenter : seulement un fil a
      brancher (`Scene.turns_finished_by_id`, #27-r8).

    Porteur `darkaBossLion` [npc] -> GREFFE sur `darkaAsmodai` (Dark Angels comme lui, present dans
    `rl_duel build --list-pool`), meme voie que 1216. La greffe ne couvre pas les stats/traits/armes du
    vrai porteur -- legitime ICI puisque la formule n'en lit aucun."""
    ability_id = int(ActiveAbilityType.InstrumentsOfVengeance)   # 1215 = 0x4bf
    # CONSTANTES EN DUR du natif -- aucune n'est un `GetUtilityValue` (cf. docstring).
    BASE_UTILITY = 20000.0                  # `Fix64.op_Implicit(u + 20000)`
    NO_ADJACENT_ENEMY_UTILITY = 100.0       # `adj.Any() ? 0 : 100`
    NON_ADJACENT_SURROUNDING_UTILITY = 20.0  # `if (!adj.Contains(e)) u += 20`
    SURROUNDING_RANGE = 2                   # `GetSurroundingEnemies(..., range: 2, ...)`

    def _adjacent_enemies(self, ctx, caster_tile) -> list:
        """`battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false)` — les ENNEMIS
        du caster sur une tuile ADJACENTE a `caster_tile` (porte d'elevation d'`IterateAdjacentTiles`).
        Le camp est deja resolu par `decisionView` (`ctx.enemies`), comme le
        `CurrentPlayerEntityId` du natif."""
        return [u for u in (ctx.enemies or [])
                if bq.is_adjacent(caster_tile, ((u.get("pos") or {}).get("col"),
                                                (u.get("pos") or {}).get("row")),
                                  ctx.elev_by_pos, bq.neigh_map(ctx))]

    def _surrounding_enemies(self, ctx, caster_tile) -> list:
        """`battleQuery.<slot itf 0x78>(caster, casterPosition, range: 2, includeCenter: false)` —
        `GetSurroundingUnits(casterPosition, 2, includeCenter: false)` filtre par `IsEnemy(u, caster)`.
        Disque hex PUR de rayon 2, centre EXCLU, SANS porte d'elevation
        (`battle_query.is_surrounding`)."""
        out = []
        for u in (ctx.enemies or []):
            p = (u or {}).get("pos") or {}
            if p.get("col") is None or p.get("row") is None:
                continue                       # hors plateau : sur aucune tuile du disque
            if bq.is_surrounding(caster_tile, (p["col"], p["row"]),
                                 self.SURROUNDING_RANGE, include_center_tile=False):
                out.append(u)
        return out

    def should_evaluate_unit(self, ctx, ability_id) -> bool:
        """`...InstrumentsOfVengeancePlaybook$$ShouldEvaluate(unit)` (slot 4) — mirror 1:1 :

            return BasePlaybook.ShouldEvaluate(unit) && battleQuery.<slot itf 0x1b>(unit, 2);

        `HasMinimumRemainingTurns(unit, 2)` est rendu `true` par le natif des que la limite de tours
        du match est absente -- le regime du runner -- donc ce facteur vaut `True` ici (cf. la
        docstring de classe, volet 1). Reste `BasePlaybook.ShouldEvaluate(unit)`, qui se reduit aux
        trois valeurs de `...InstrumentsOfVengeancePlaybook$$GetUseProbability` :

            t == 0 -> Fix64.Zero  -> `p <= 0` -> **False**   (DETERMINISTE, ce que ce port ajoute)
            t == 1 -> Fix64.Half  -> tirage `random.<slot 4>(0.5)`  -> non modelisable offline
            t >= 2 -> Fix64.One   -> `p >= 1` -> **True**

        Le volet `t == 1` reste PERMISSIF, et c'est DECLARE : le natif y tire a pile ou face, et le
        moteur n'a pas son PRNG a ce point (meme statut que le 1/3 de
        `...PlasmaGrenadePlaybook$$GetUseProbability`). Rendre `False` y serait aussi faux que
        `True`, mais RESTRICTIF -- on garde donc le sens qui ne retire jamais une action que le
        natif peut jouer.

        `t` non capture (`Scene` absente, uid hors tables) -> `True` : ne PAS gater a l'aveugle.
        Un `0` de repli signifierait `Fix64.Zero`, donc un REFUS que le natif n'a pas prononce --
        c'est la meme convention que `noncomparable/_base.py::_turns_started_gate`."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return True
        t = sc.turns_finished(ctx.uid)
        if t is None:
            return True                        # canal muet -> permissif, jamais un 0 invente
        return t != 0

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        adj_ids = {u.get("id") for u in self._adjacent_enemies(ctx, caster_tile)}
        u = self.BASE_UTILITY
        if not adj_ids:                                     # `adj.Any() ? 0 : 100`
            u += self.NO_ADJACENT_ENEMY_UTILITY
        for e in self._surrounding_enemies(ctx, caster_tile):
            if e.get("id") not in adj_ids:                  # `!adj.Contains(e)`
                u += self.NON_ADJACENT_SURROUNDING_UTILITY
        return u


def _register_all() -> None:
    for cls in (ArmoriumCherubPlaybook, LightOfSanguiniusPlaybook,
                HeraldOfTheApocalypsePlaybook, DrachnyenPlaybook,
                DoomSirenPlaybook, SavageEchoesPlaybook,
                HeavyWarpFlamerPlaybook, MassDriverAcceleratorPlaybook,
                StikkbombPlaybook, PlasmaGrenadePlaybook, MortisRoundPlaybook,
                MortarionsPlagueWindPlaybook):
        register(cls())
    # SECONDE route Comparable (#27-4b/4c/4d) : l'ability est absente de `ctx.plans` -- soit parce
    # qu'elle n'a pas de `damageProfile` (Chronometron, ForwardObservers), soit parce que son masque
    # de ciblage refuse toute cible ennemie (SorcerousFacade, veto #217). Registre + route dedies
    # (`playbook/nonattack.py`).
    # ... soit, 3e cas (#27-r4), parce que son masque est SELF-CAST (`CasterIsPossibleTarget`) : la
    # seule cible que le natif retient est le CASTER, donc les evals de `attackPlans` sur les
    # ENNEMIS rendent tous `rankCount = 0` et `_best_attack` ne peut rien produire.
    # ... soit, 4e cas (#27-r4), parce que son `MakeDamagePredictions` rend une liste VIDE alors
    # meme qu'elle a un `damageProfile` et des `attackPlans` a `rankCount > 0` : `_best_attack` gate
    # sur la seule utilite de DEGAT et ne peut donc rien produire (motif de 1009 ResurrectionOrb).
    for cls in (ChronometronPlaybook, ForwardObserversPlaybook, SorcerousFacadePlaybook,
                MartialExemplarPlaybook, TheLionsWrathPlaybook,
                InstrumentsOfVengeancePlaybook):
        register_nonattack(cls())


_register_all()
