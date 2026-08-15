"""HammerOfWrathPlaybook — charge NonComparable (_PlanTarget), utilite = degat interne + bonus."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _traits
# FORME B, differes CLASSES GRATUITS depuis le degraissage du baril `engine.playbook`
# (#485-r1-r4) : plus aucun cycle a fermer -> HISSES.
from engine.playbook.prediction import abilities as _pred_ab
from engine.playbook import probable_damage_event as _pde


def _normal_attack_sure_kill_state(ctx: NCContext) -> bool | None:
    """`IdunBattle.AI.Playbook.BasePlaybook$$EnemyCouldBeKilledWithNormalAttack(onlyCertainKills = 1)`,
    LU VERBATIM (`rnca9r7q6c`) :

        d = BasePlaybook.GetAllNormalAttackTargets(this, attacker)   # dict a `+0x18`
        foreach (tile, targets) in d:
            foreach target in targets:
                p = battleQuery<this+0x28>.<slot 0x22>(attacker, target, tile)
                if (onlyCertainKills ? p.get_WillBeKill() : p.get_MightBeKill()) return true
        return false

    Les deux slots sont RESOLUS, pas devines (`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv`) :
    `GetAllNormalAttackTargets` = `IBattleQuery` slot `0x45` =
    `GetAllValidTargetsFromAllPossibleMovementTiles(unit, GetNormalAttackType(unit), 0)` -- donc le
    natif balaye TOUTES les positions de mouvement, ce que le sweep sur `ranked` mirrore ; et le
    slot `0x22` = `GetNormalAttackPrediction(unit, target, tile)`, celui qui passe par
    `IDamagePrediction` slot 9 = `IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack` --
    l'UNIQUE ecrivain de `CannotBeGuaranteedKilled@0x89`. Ce gate est donc VIVANT sur ce chemin.

    #566-r1 -- CE FOYER RE-ASSEMBLAIT `get_WillBeKill` A LA MAIN (`dmgMin >= hp`), quatrieme lieu
    apres les trois que #372 a fermes, et il ratait les MEMES deux crans que `projection.ts` :
    le gate `CannotBeGuaranteedKilled@0x89` (sortie anticipee, `false` quelles que soient les
    bornes) et la preference pour `BlockScenarios[0].Damage.HealthDamage.Min` sur
    `DefaultScenario...Min`. Consequence MESUREE (case-566 §6) : `tauCrisis` a 50 PV sous un plan
    `dmgMin = dmgMax = 50` -> natif `killSure = False` (block > 0) donc il CASTE, port `50 >= 50`
    donc il s'abstient. Le plan PUBLIE le verdict decode (`ranked[].killSure`, pose par
    `projection.ts::applyDmg` depuis `computeWillBeKill` de `game/damage-prediction.ts`) : on le
    LIT, on ne le re-derive plus.

    TRI-ETAT, et c'est le point qui separe une mesure d'une invention. `killSure` est ABSENT du
    `ranked` quand `willBeKill === null`, c'est-a-dire quand le decodeur natif n'a PAS pu conclure
    (chaine `DamagePredictionScenario` non resolue, `BlockScenarios` illisible) -- ou quand le plan
    vient d'un bundle anterieur a #372. Ce n'est PAS un `false`. On rend donc :

      * `True`  -- au moins une paire (tuile, cible) porte `killSure = True` : existence ETABLIE,
                   et elle court-circuite comme le `return true` natif ;
      * `False` -- toutes les paires lisibles portent `killSure = False` : absence ETABLIE ;
      * `None`  -- aucune `True`, et au moins une paire porte une PREDICTION (`dmgMin` present)
                   SANS `killSure` : le canal ne dit rien, on ne fabrique pas de verdict.

    Une entree sans AUCUN champ de degat (`dmgMin` absent) n'est pas << non mesuree sur killSure >> :
    c'est une tuile pour laquelle le hook n'a pas obtenu de prediction du tout. Elle est ignoree,
    comme avant, sans salir le tri-etat.

    ⚠ EXPOSE A LA TRONCATURE DU PLAN, et le foyer #350-r3a-r4 NE PEUT PAS le reparer : ce gate lit
    un champ de DEGAT, qui ne vit QUE dans `ranked` -- `castFromTiles` rend des positions, pas des
    degats. Face DECISION : une tuile sure-kill ecartee par `maxRank` fait rendre FAUX a tort, donc
    Hammer est evaluee la ou le natif s'abstient. Seul le harnais peut servir ce cas --
    `case-350r3a-r4-troncature-du-plan.md` §5. Face COMBAT : `ranked` complet, RAS."""
    me = next((u for u in (ctx.units or []) if u.get("id") == ctx.uid), None)
    if me is None:
        return False
    normal_ids = {a.get("id") for a in (me.get("abilities") or []) if a.get("kind") == "normal"}
    if not normal_ids:
        return False
    indecidable = False
    for ev in (ctx.plan.get("evals") or []):
        if ev.get("abilityId") not in normal_ids:
            continue
        if ctx.hp_cur_by_id.get(ev.get("targetId")) is None:
            continue           # cible hors de l'etat suivi : le natif ne la verrait pas non plus
        for rk in (ev.get("ranked") or []):
            sure = rk.get("killSure")          # `get_WillBeKill` DECODE (gate + choix de borne)
            if sure is True:
                return True                    # `return true` natif : court-circuit
            if sure is None and rk.get("dmgMin") is not None:
                indecidable = True             # prediction lue, verdict NON publie -> tri-etat
    return None if indecidable else False


def _enemy_killed_by_normal_attack(ctx: NCContext) -> bool:
    """Le gate BOOLEEN que consomment les trois `ShouldEvaluate` portes (`HammerOfWrath` 1153,
    `VexillaMagnifica` 1183, `SupremeCommander` 1160 -- ce dernier via
    `BasePlaybook$$EnemyWillBeKilledWithNormalAttack`, qui n'est qu'un relais passant
    `onlyCertainKills = 1`).

    BORNE DE PORT, unique et nommee : le tri-etat `None` de `_normal_attack_sure_kill_state`
    (canal `killSure` non publie) rend `False` = << le gate ne MORD PAS >>. Meme sens et meme
    direction que les deux bornes de `engine.playbook.base.will_normal_attack_kill` (predicteur
    absent, tuile absente), et meme comportement que le port d'avant #566-r1 -- un plan sans
    verdict n'abstient personne. Ce n'est pas une mesure : il est DISCERNABLE d'un `False` mesure
    par `_normal_attack_sure_kill_state`, que tout appelant qui veut la nuance peut interroger."""
    return _normal_attack_sure_kill_state(ctx) is True


class HammerOfWrathPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable` (id 0x481=1153, bloodIntercessor). Charge
    NonComparable : utilité de DÉCISION = Σ dégât INTERNE (cible + adjacents) + bonus trait, SANS émettre de
    ProbableDamageEvent affiché (dégât exclu de la prédiction #109). Le caster CHARGE la cible (move + attaque).

    - utilité(cible) = `+100·HasTrait(cible, 0x3eb=1003=Overwatch)` + `CalcUtilFromDamageEvent(PRIMARY)`
      + `Σ_{adj ∈ SelectUniqueUnits(GetAdjacentTargets,3)} CalcUtilFromDamageEvent(SECONDARY)`
      + `5·Σ_{n ∈ GetAdjacentTiles(cible)} CanAddUnit(n)` (#116, PORTÉ). Chemin dégât =
      `make_hammer_wrath_events` (primary minDmg/nrOfHits/Power ; secondary minDmg_2/nrOfHits_2/Physical sur
      ennemis adjacents à la cible), Σ `calculate_utility_from_damage_event`.
    - +5·CanAddUnit (#116, RE re-expert) : `+5` par voisin ring-1 de la CIBLE où une unité peut être placée.
      Le natif fait `IBattleQuery.slot0x4f(cible)` = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles` (prouvé slot 79 via
      `IdunBattle.Core.Services.MovementQuery$$IsAdjacent` + slot-map RecordedSimulationRequestsBattleQuery ; PAS GetTilesBehind
      = slot 0x53) puis `IdunBattle.Entities.TileExtensions$$CanAddUnit` (tuile walkable/non-wall ET VIDE). Biais du natif
      vers les cibles entourées d'ESPACE LIBRE (place pour le knock-back de la charge). Le terme dépend de la
      CIBLE (pas de la tuile de charge) -> influe l'ARGMAX de cible. Porté via `bq.adjacent_addable_count`
      (voisins boardGraph, porte |Δelev|<2 comme #45, gate `can_add_unit`). FLAG : co-location trait 0x1b +
      tuiles walkable-mais-réservées non modélisées (borne INF, cf. `can_add_unit`).
    - MIN_UTILITY=1 (IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$.cctor) ; IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$.ctor = `NonComparablePlaybook(0x481)` -> 1er arg =
      ability_id, PRIORITY=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170). GenerateAction(position, cible, util) + AddAction (argmax via base).
    - IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$ShouldEvaluate = `!EnemyCouldBeKilledWithNormalAttack(killSure)` : le natif N'ÉVALUE PAS
      Hammer si l'attaque normale du caster sure-kill déjà un ennemi (économise la charge). Porté ci-dessous.
    - Trait 1003 = `Overwatch` (enum UnitTrait, dump.cs gqfc5mff6c:863979 ; PAS BigTarget=1017).
    Éligibilité + tuile de charge = plan natif (evals rankées 1153), comme BloodyFury/Vexilla (_PlanTargetPlaybook)."""
    ABILITY_ID = int(ActiveAbilityType.HammerOfWrath)  # 1153
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$.cctor = Fix64(1)
    PRIORITY = 0
    _OVERWATCH = "Overwatch"   # trait 0x3eb=1003 (enum UnitTrait) -> +100 sur une cible en Overwatch

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 de la vtable -> `IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$ShouldEvaluate` = `!EnemyWillBeKilledWithNormalAttack`
        (relogé de generate_candidates vers l'étage natif du gate — le générateur le teste AVANT
        tout sweep, #46)."""
        if _enemy_killed_by_normal_attack(ctx):
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] Hammer SKIP (normal sure-kill)", file=sys.stderr)
            return False
        return True

    def evaluate_non_comparable(self, tile, target, ctx):
        if tile is None or ctx.scene is None:
            return None
        events = _pred_ab.make_hammer_wrath_events(ctx.scene, ctx.uid, target, tile)
        if not events:
            return None
        u = sum(_pde.calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(ev.target))
                for ev in events)
        # +100 si la CIBLE a le trait Overwatch (HasTrait(target, 0x3eb) IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable).
        vis = next((x.get("visualId") for x in (ctx.obs_units or []) if x.get("squadId") == target), None)
        if self._OVERWATCH in _traits(vis):
            u += 100.0
        disp = self._displacement_bonus(target, ctx)   # +5 par voisin ring-1 CanAddUnit de la cible (#116)
        u += disp
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Hammer tgt={target} tile={tile} events={len(events)} "
                  f"disp={disp:.0f} u={u:.1f}", file=sys.stderr)
        return u

    @staticmethod
    def _displacement_bonus(target, ctx: NCContext) -> float:
        """`+5 · Σ_{n ∈ GetAdjacentTiles(cible)} CanAddUnit(n)` (#116). Voisins ring-1 de la CIBLE
        (`IBattleQuery.GetAdjacentTiles` slot 0x4f IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles) où une unité peut être placée
        (`IdunBattle.Entities.TileExtensions$$CanAddUnit`). Occupation LIVE = TOUTES les unités vivantes
        (epos ∪ fpos ∪ origine, FRAÎCHE). Cible introuvable / sans position -> 0."""
        tu = next((u for u in (ctx.units or []) if u.get("id") == target), None)
        p = (tu or {}).get("pos") if tu else None
        if not p or p.get("col") is None:
            return 0.0
        occupied = bq.occupied_positions(ctx)     # #969-r3 : PAR PIED (`TileContentComponent`)
        return 5.0 * bq.adjacent_addable_count((p["col"], p["row"]), ctx.neigh_by_pos,
                                               ctx.walkable_by_pos, occupied, ctx.elev_by_pos)
