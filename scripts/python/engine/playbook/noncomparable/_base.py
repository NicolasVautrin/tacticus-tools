"""Fondations partagees des playbooks NonComparable (namespace `engine.playbook.noncomparable`).

Bases de hierarchie (`NonComparablePlaybook`, `_PlanTargetPlaybook`), contexte live `NCContext`, et
helpers transverses (config gameconfig, traits, sweep origine-d'abord, HasValidTargets). Chaque
playbook natif vit dans son propre module (bloody_fury.py, heals.py, ...) et importe d'ici ; le
registre + le driver `choose_action` sont dans le package `__init__.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import gameconfig as _gc


_CFG_CACHE: dict = {}


def _unit_cfg(visual_id) -> dict:
    """Config gameconfig d'une unite par visualId (resolue + cachee ; `resolve_unit_id` d'abord, comme
    `_faction`). Le dict porte `traits` / `GrandAllianceId` / `kind`. Vide si introuvable."""
    if not visual_id:
        return {}
    c = _CFG_CACHE.get(visual_id)
    if c is None:
        try:
            uid = _gc.resolve_unit_id(visual_id)
            c = (_gc.unit(uid) if uid else _gc.unit(visual_id)) or {}
        except Exception:
            c = {}
        _CFG_CACHE[visual_id] = c
    return c


def _traits(visual_id) -> list:
    """Traits gameconfig (Hero/Mechanical). heal = Healable = non-Mecanique ; resurrect hero = Hero(16)."""
    return _unit_cfg(visual_id).get("traits") or []


def _has_valid_targets(ctx: "NCContext", unit_id: int) -> bool:
    """`IBattleQuery.HasValidTargets(unit, GetUnitPosition(unit), GetNormalAttackType(unit))` (slot 0x3f
    -> `BattleQuery.HasValidTargets @18106e8d0` -> `AttackQuery.HasValidTargets @181057540`) résolu OFFLINE :
    l'unité peut-elle attaquer >= 1 ennemi avec son attaque NORMALE DEPUIS SA POSITION ACTUELLE (SANS bouger) ?
    = `abilityTargets(unit, GetNormalAttackType(unit))` -> `usable` (CanCurrentlyBeUsed = cooldown/munitions)
    ET `fromHereCount > 0` (`fromHere` = `AttackQuery.GetValidTargets(unit, pos, ability)` = légalité du cast
    immédiat : portée + LoS + filtre ennemi). POSITION-INDÉPENDANT du sweep du caster (dépend de la tuile
    FIXE de `unit`) -> à calculer 1x par cible. `ability_targets`/`units` absent, unité/attaque introuvable,
    RPC vide -> False (fallback = borne inf, = comportement pré-#77)."""
    if ctx.ability_targets is None:
        return False
    u = next((x for x in (ctx.units or []) if x.get("id") == unit_id), None)
    if u is None:
        return False
    # GetNormalAttackType = l'attaque normale CONCRETE de l'unité (id per-unit, pas l'abstrait 17).
    na = next((a for a in (u.get("abilities") or [])
               if a.get("kind") == "normal" and a.get("id") is not None), None)
    if na is None:
        return False
    at = ctx.ability_targets(unit_id, na["id"]) or {}
    for uu in (at.get("units") or []):
        if uu.get("unitId") != unit_id:
            continue
        for a in (uu.get("abilities") or []):
            if a.get("abilityId") == na["id"]:
                return (a.get("usable") is not False) and int(a.get("fromHereCount") or 0) > 0
    return False


def _normal_attack_ids(ctx: "NCContext", unit_id: int) -> set:
    """Ids de l'attaque NORMALE CONCRETE d'une unite (`GetNormalAttackType` ; per-unit, PAS l'abstrait
    17 — cf. project_ability_normal_attack_concrete). Vide si l'unite est absente de `ctx.units`."""
    u = next((x for x in (ctx.units or []) if x.get("id") == unit_id), None)
    return {a.get("id") for a in ((u or {}).get("abilities") or [])
            if a.get("kind") == "normal" and a.get("id") is not None}


def _will_normal_attack_kill(ctx: "NCContext", target_id, position: tuple | None) -> bool:
    """`BasePlaybook.WillNormalAttackKill @18111fff0` : `PredictAttack` (slot 0x20 = attaque NORMALE du
    caster DEPUIS `position`) -> `ProbableDamageEvent` -> `DamagePredictionResult.get_WillBeKill` =
    SURE-kill (borne MIN >= PV courants, = `killSure` du composite). `target == null` -> false (branche
    `param_3 == 0` du natif). Predicteur (`ctx.scene`) absent -> false (borne inf, pas de gate a l'aveugle).

    A NE PAS confondre avec `EnemyCouldBeKilledWithNormalAttack` (`_enemy_killed_by_normal_attack`,
    hammer_of_wrath) qui teste s'il EXISTE un ennemi sure-kill ; ici c'est CETTE cible-la."""
    if target_id is None or position is None or ctx.scene is None:
        return False
    from engine.playbook.prediction import make_normal_attack_predictions
    ev = make_normal_attack_predictions(ctx.scene, ctx.uid, target_id, position)
    if ev is None:
        return False
    return bool(ev.composite_fields().get("killSure"))


def _get_num_attack_targets_in_position(ctx: "NCContext", unit_id: int, tile: tuple | None) -> int:
    """`TheQuickeningPlaybook.GetNumAttackTargetsInPosition @18116b4b0` = `IBattleQuery` slot 0x7f
    (cibles d'attaque NORMALE de `unit_id` DEPUIS `tile`, POSITION HYPOTHETIQUE — la requete prend
    la tuile en argument, elle n'est PAS contrainte par le mouvement/l'occupation) suivi de `.Count`.

    Mirror OFFLINE via le plan natif (`decisionView.attackPlans`) : nombre de cibles DISTINCTES dont
    l'eval d'attaque NORMALE de `unit_id` liste `tile` parmi ses tuiles rankees — les tuiles rankees
    d'une paire (ability, cible) sont exactement les positions d'ou l'attaque est legale. Plan absent
    (le bridge offline `state_bridge` ne peuple que l'unite ACTIVE) -> 0 (borne inf assumee).

    FALLBACK GEOMETRIQUE (#46) : le plan est AVEUGLE hors de l'univers MOVABLE de `unit_id` — ses
    tuiles rankees sortent de `GetPossibleMovementTiles`, donc une tuile OCCUPEE (l'echange
    TheQuickening : caster sur la tuile d'un allie de meme empreinte) ou la position P d'un ALLIE
    echange n'y figure JAMAIS (mesure 31337 pas 15 : la cible native 52=(4,4), occupee par u79,
    etait jetee ici -> le port ratait la paire). Pour ces tuiles hors-plan on mirrore la partie
    MELEE du slot 0x7f : #ennemis ADJACENTS a `tile` (porte |dElev|<2, `is_adjacent`), si l'unite a
    une arme de melee (gameconfig `weapons` sans `Range`). Borne INF : l'arme RANGED (portee+LoS non
    portees) n'est pas comptee ; pour une tuile DU plan du caster le verdict plan reste autoritaire
    (pas de sur-comptage des tuiles movables sans attaque legale)."""
    if tile is None:
        return 0
    plan = (ctx.plans or {}).get(unit_id) or {}
    nids = _normal_attack_ids(ctx, unit_id)
    if not nids:
        return 0
    tgts = set()
    for ev in (plan.get("evals") or []):
        if ev.get("abilityId") not in nids or not ev.get("rankCount"):
            continue
        for rk in (ev.get("ranked") or []):
            if (rk.get("col"), rk.get("row")) == tile:
                tgts.add(ev.get("targetId"))
                break
    if tgts:
        return len(tgts)
    if unit_id == ctx.uid and tile in (ctx.reach_nc or []):
        return 0     # tuile DANS l'univers movable du plan du caster -> plan autoritaire
    u = next((x for x in (ctx.units or []) if x.get("id") == unit_id), None)
    if u is None:
        return 0
    weapons = _unit_cfg(u.get("visualId")).get("weapons") or []
    if not any("Range" not in w for w in weapons):
        return 0     # pas d'arme de melee -> le mirror geometrique ne sait pas compter (borne inf)
    from engine.battle_query import count_adjacent
    return count_adjacent(tile, ctx.epos or [], ctx.elev_by_pos)


def _turns_started_gate(ctx: "NCContext") -> bool:
    """Corps FOLDÉ (COMDAT) du slot-4 `ShouldEvaluate(unit)` « pas au 1er tour » — code UNIQUE
    @18111af90 (symbole `AlphaWarriorPlaybook$$ShouldEvaluate`, refcount 7) pointé par la vtable de
    PLUSIEURS playbooks : `return GetStat(unit, 0xc=TurnsStarted) > 1`.

    Vtables résolues LIVE (`resolveVtableSlot` @0x298, gqfc5mff6c) : TheQuickening(1151),
    HeroicFusillade(1180), VigilanceEternal(1202), AlphaWarrior (non porté) -> @18111af90.
    `turnsStarted` (stat 12) = compteur PER-UNIT incrémenté au StartTurn -> vaut 1 pendant le
    PREMIER tour de l'unité : l'ability n'est JAMAIS évaluée au 1er tour (mesure #46 seed 31337 :
    slot4=0 au pas 5 (1er tour u81, 8/8 déterministe), =1 au pas 15 (2e tour) — la corrélation
    RapidAssault n=2 était un PROXY du 1er tour, pas le mécanisme). Compteur non capturé (scene
    absente / uid hors tables) -> True : ne PAS gater à l'aveugle (mirror du précédent
    `_is_player_side`)."""
    if ctx.scene is None:
        return True
    ts = ctx.scene.turns_started(ctx.uid)
    if ts is None:
        return True
    return ts > 1


def _sweep_origin_first(ctx: "NCContext") -> list:
    """Ordre de balayage des positions candidates pour un SELF-CAST (heal/repair/rites) : ORIGINE
    D'ABORD, puis les tuiles de move.

    Le generateur natif `ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` evalue chaque
    position dans un Bucket ; `Bucket.AddAction @1813fbcc0` SEED le 1er ajoute puis ne remplace QUE si
    STRICTEMENT superieur (`System.TimeSpan.op_GreaterThan`) -> keep-first au tie. La `NullPosition`
    (cast EN PLACE) est TOUJOURS evaluee. CONFIRME LIVE (#76, deathRotbone RevitalizingMalignancy) :
    a utilite CONSTANTE (seul le caster blesse -> terme adjacents = 0) le natif RESTE EN PLACE (target
    = MainTile origine), il ne bouge QUE si une tuile de move AMELIORE STRICTEMENT la somme de soin.
    -> origine EN TETE du sweep + remplacement strict `>` = origine gagne le tie ; un move ne gagne
    que sur gain strict. (Le port balayait `reach_nc` = [moves..., origine] -> gardait la 1re tuile de
    move au tie -> divergence : bougeait pour rien.)"""
    if ctx.origin is None:
        return list(ctx.reach_nc)
    return [ctx.origin] + [t for t in ctx.reach_nc if t != ctx.origin]


@dataclass
class NCContext:
    """Etat live consomme par les generators de playbook (bundle du scope engine_decide)."""
    uid: int
    origin: tuple | None
    reach_nc: list                 # origine + tuiles de MOVE = positions candidates du caster
    epos: list                     # positions ennemies (GetAdjacentEnemies, slot 124/126)
    fpos: list                     # positions alliees, self exclu (GetAdjacentFriends, slot 128)
    plan: dict                     # plan natif (evals rankes) — abilities d'ATTAQUE
    hp_cur_by_id: dict             # PV courants par id cible (GetStat 5 = Health ; Vexilla)
    ability_targets: object = None # callable(uid, ability_id) -> dict RPC abilityTargets (summon)
    enemies: list = field(default_factory=list)    # unités ennemies {id, pos} (MÊME ordre que `epos`) :
    #                                emettre la CIBLE de l'arc pour Gauntlets (#117)
    neigh_by_pos: dict = field(default_factory=dict)  # {(col,row): [voisins ordre natif]} (boardGraph) :
    #                                cible EXACTE Gauntlets = 1er ennemi ring-1 en ordre voisins inversé (#117)
    walkable_by_pos: dict = field(default_factory=dict)  # {(col,row): walkable} (boardGraph, statique) :
    #                                gate STATIQUE de placement CanAddUnit (HammerOfWrath +5 displacement #116)
    obs_units: list = field(default_factory=list)  # observeBattle.units (isDead/teamId/visualId/pos) :
    #                                SOURCE DES MORTS pour RitesOfRestoration (decisionView garde les
    #                                depouilles -> observeBattle.isDead, cf. project_decisionview_keeps_dead)
    elev_by_pos: dict = None       # {(col,row): elevation} (tileMeta) — porte d'adjacence |Δelev|<2
    wt: object = None              # Weights BC (NovaShield : terme Tile(7) = tile_utility)
    is_temporary_by_pos: dict = field(default_factory=dict)  # Tile(7) (feuille is_temporary)
    effects_by_pos: dict = field(default_factory=dict)       # Tile(7) (feuille TileEffects)
    tile_id_by_pos: dict = field(default_factory=dict)       # {(col,row): tileEntityId} (boardGraph) :
    #                            cible d'une self-cast AoE (heal) = MainTile-id du caster, PAS son unit-id
    active_levels: object = None   # callable() -> {unitId: activeAbilityLevel} (lazy combatSnapshot) :
    #                            niveau d'ability des allies pour InspiredToGreatness (util = level)
    units: list = field(default_factory=list)   # dv.units (par-unite abilities + usable/cooldown) :
    #                            etat cooldown des allies pour InspiredToGreatness (GetActive usable)
    cast_from_tiles: object = None   # callable(uid, target_id, ability_id) -> {currentValid, moveTiles} :
    #                            positionnement move-to-reach des NC ally-targeted (#81)
    plans: dict = field(default_factory=dict)   # {unitId: plan attackPlans} de TOUTES les unites (#44) :
    #                            `GetNumAttackTargetsInPosition(unit, tile)` de TheQuickening interroge
    #                            aussi le plan d'un ALLIE (terme +1 de l'ami echange), pas seulement `plan`
    scene: object = None           # engine.playbook.Scene (predictor+sctx) — HammerOfWrath (#114) score
    #                            son utilité de décision via Σ CalculateUtilityFromDamageEvent (prédiction
    #                            dégât INTERNE, bypass du gate d'affichage #109) sur cible + adjacents.
    debug: bool = False


class NonComparablePlaybook:
    """`NonComparablePlaybook<T>` — playbook à heuristique ENTIÈRE écrite dans la feuille (summons,
    buffs, retraite), par opposition à `ComparablePlaybook<T>` (attaques/soins = somme pondérée sur
    prédictions). Priorité Normal(0) pour tous les portés. Sous-classe = un playbook natif homonyme
    (selector + leaf `EvaluateNonComparable` + MIN_UTILITY du cctor)."""
    ABILITY_ID: int = -1
    MIN_UTILITY: float = 0.0       # cctor du playbook -> gate Bucket.AddAction (util >= min)
    PRIORITY: int = 0              # get_Priority (slot0) -> tier NonComparable (dict[prio], @1810ed540)
    #                                les 4 portés = 0 (confirmé live via abilityPreferences/get_Priority)

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`IPlaybook` slot 4 `ShouldEvaluate(unit)` — gate AMONT du générateur
        `ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` (`FUN_180003bd0(4, …)`),
        évalué AVANT tout sweep de position : False -> l'ability est SAUTÉE entièrement (le
        fallback Comparable prend la main).

        Impl de base = `BasePlaybook.ShouldEvaluate @18111fb70` : `prob := vtable[0x1f8]
        GetUseProbability(unit)` puis `prob >= 1 -> True` ; `prob <= 0 -> False` ; sinon tirage
        RNG autobot. Les DEUX surcharges de base `GetUseProbability` (@18111f9b0 / @18111fa00,
        slots 0x208/0x1f8) rendent `Fix64(1)` -> True constant ici. Les playbooks à
        `GetUseProbability` conditionnelle (BlackRage @181121740 = 0.4, ItItches @1811477b0)
        restent True = écart assumé « porte ALÉATOIRE non modélisée » (moteur déterministe,
        cf. §5 case-44). Un playbook qui OVERRIDE le slot 4 lui-même (vtable ≠ @18111fb70)
        surcharge cette méthode (ex. corps foldé @18111af90 `GetStat(unit,12) > 1`)."""
        return True

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Mirror <GenerateActions>d__7 pour CETTE ability : balaie positions/cibles (selector
        propre), score (evaluate_non_comparable), gate par MIN_UTILITY. Rend 0 ou 1 candidat
        {target, ability, to, pred} = le meilleur de l'ability (Bucket local deja argmax-e)."""
        raise NotImplementedError


class _PlanTargetPlaybook(NonComparablePlaybook):
    """Base des abilities d'ATTAQUE NonComparable (BloodyFury, VexillaMagnifica). Le generator
    natif enumere ici les couples (cible, tuile d'attaque) via le plan natif rank
    (`abilityTargets`/ranked du plan) au lieu d'un balayage de tuiles de move ; leaf par sous-classe.

    `SWEEP_ALL_RANKED` (defaut False = 1re tuile rankee seulement) : quand l'utilite DEPEND de la tuile
    de cast (playbooks a utilite de DEGAT — BlackRage, VigilanceEternal), balayer TOUTES les tuiles
    rankees de la paire, ce qui mirrore le balayage de POSITIONS du generator natif
    (`<GenerateActions>d__7 @18119a3f0`) restreint aux positions LEGALES pour cette paire. Les
    playbooks a utilite position-INDEPENDANTE (BloodyFury/Vexilla/Hammer) gardent `ranked[0]`.
    """
    SWEEP_ALL_RANKED: bool = False

    def evaluate_non_comparable(self, tile: tuple, target, ctx: NCContext) -> float | None:
        raise NotImplementedError

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best = None  # (target, tile, util)
        for ev in (ctx.plan.get("evals") or []):
            if ev.get("abilityId") != self.ABILITY_ID or not ev.get("rankCount"):
                continue
            ranked = ev.get("ranked") or []
            if not ranked:
                continue
            tiles = ranked if self.SWEEP_ALL_RANKED else ranked[:1]
            tgt = ev.get("targetId")
            for rk in tiles:
                tile = (rk.get("col"), rk.get("row"))
                if tile[0] is None:
                    continue
                nu = self.evaluate_non_comparable(tile, tgt, ctx)
                if nu is None:
                    continue
                if best is None or nu > best[2]:   # strict > : premier max garde
                    best = (tgt, tile, nu)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]
