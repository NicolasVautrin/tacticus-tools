"""DoctrinaImperativesPlaybook — decision NonComparable self-cast (Tan Gi'da, toggle Protector/Conqueror)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first, _has_valid_targets
from engine import battle_query as bq
from engine.entities.effects.magnitude import ability_var


class DoctrinaImperativesPlaybook(NonComparablePlaybook):
    """`DoctrinaImperativesPlaybook` (RE IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$.ctor, ctor `NonComparablePlaybook(0x45e=1118)`).

    - IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$.cctor : `MIN_UTILITY = Fix64.FromInt(1)` (gate Bucket.AddAction).
    - `IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$GetUseProbability` : `Fix64(1)` (100%) si `HasUsedAbilityThisTurn == false`, sinon `Fix64(0)`
      -> l'IA n'active DoctrinaImperatives qu'UNE fois par tour (le once-per-turn est reflete cote driver par
      `usable is False` une fois utilise, comme les autres actives -- non re-modelise ici).
    - `IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$EvaluateNonComparable` : **GATE 3 branches** (verdict re-expert task #31, slots BattleQuery
      0x51=`GetAdjacentUnits` / 0xc9=`IdunBattle.Core.Services.BattleQuery$$ReachedSummonCap resolus). Le natif ne score l'usage a 100
      (`GenerateAction(Fix64.FromInt(100))`) QUE si le gate passe -- sinon bucket vide -> pas d'action -> le
      fallback Comparable (attaque) prend la main. Notre port emmettait 1118 INCONDITIONNELLEMENT (overfire
      #31 : s01/s07 AdMech + 31337 s17, le toggle ecrasait une attaque native ab=69).

      Gate natif (mirror `_should_emit`, DESASSEMBLE IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$EvaluateNonComparable #38b : `jle` sur le count
      free-adjacent -> emit ; sinon ReachedSummonCap) :
        count = GetEligibleTargetsForNormalAttack(caster) = cibles d'attaque normale SANS bouger (fromHere).
        - count == 0 : emit ssi `HasEffect(caster, ConquerorImperative 0x4e0=1248)` -- en Conqueror et rien a
          taper depuis la position courante -> rebascule Protector (reprend tank/summon) ; en Protector -> rien.
        - count > 0 : free = `GetFreeAdjacentTiles(caster)` (IBattleQuery slot 0x52 IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles,
          RESOLU LIVE vtable #38b -- l'ancien verdict case-31 "GetAdjacentUnits TOUT CAMP" etait
          FAUX ; slot 0x51 = TUILES LIBRES placables adjacentes, PAS des unites) ;
          - free == 0 : emit inconditionnel (Tan encercle : plus de place a summon -> toggle libre).
          - free > 0  : emit ssi `ReachedSummonCap(caster, ControlEdict 0x4b0=1200)` (slot 0xc9, cap
            maxSummons[level passif] (3/4/5) d'enfants JAMAIS spawnes atteint -- morts inclus, cf.
            `_reached_summon_cap` -> plus rien a gagner a rester en Protector -> basculer).
      VALIDE LIVE #38b (oracle natif `ncEvaluate` + A/B seed 777 tuile (4,7)) : a 0 summon la tuile
      ouverte (free=6, count=2) N'EMET PAS ; a >=5 summons (cap) la MEME tuile EMET -> causation par
      le CAP (pas free==0). Miss s32/44/50 = `_reached_summon_cap` comptait le mauvais visualId.

    SELF-cast (comme NovaBoost/heals #76/#80) : la cible = self, position-independante -> le generateur
    `<GenerateActions>d__7` gate les tuiles de move par `HasValidTargets` (self position-independant -> aucune
    tuile motivee) et garde le 1er ajoute (NullPosition = cast EN PLACE) -> le natif RESTE EN PLACE
    (`_sweep_origin_first` -> to=None)."""
    ABILITY_ID = int(ActiveAbilityType.DoctrinaImperatives)   # 1118
    MIN_UTILITY = 1.0
    PRIORITY = 0          # AbilityPriority.Normal : 1118 hors NATIVE_PRIORITY (sweep #170)
    UTILITY = 100.0       # GenerateAction(..., Fix64.FromInt(100)) IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$EvaluateNonComparable

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self._usable(ctx):
            return []
        if not self._should_emit(ctx):
            return []
        to = next(iter(_sweep_origin_first(ctx)), None)
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (to if to != ctx.origin else None), "pred": self.UTILITY}]

    def _should_emit(self, ctx: NCContext) -> bool:
        """Mirror du gate `IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$EvaluateNonComparable` (3 branches, cf. docstring de classe)."""
        # count = GetEligibleTargetsForNormalAttack(caster) : `_has_valid_targets` mirror `HasValidTargets`
        # (0x3f) = >=1 ennemi attaquable a l'attaque NORMALE DEPUIS la position courante (fromHereCount>0).
        if not _has_valid_targets(ctx, ctx.uid):          # count == 0
            return self._is_conqueror(ctx)
        # count > 0
        if self._free_adjacent_tiles(ctx) > 0:            # GetFreeAdjacentTiles(caster) (slot 0x51, #38b)
            return self._reached_summon_cap(ctx)          # emit ssi cap maxSummons Skitarii atteint
        return True                                       # free == 0 (encercle) -> toggle libre

    def _is_conqueror(self, ctx: NCContext) -> bool:
        """`HasEffect(caster, EffectType.ConquerorImperative=1248)`. Source : effets par-unite de
        decisionView (`me.effects`, IsActive-filtre -- valide LIVE re-expert #31 : le toggle y remplace
        Protector par Conqueror) ; fallback `EffectsState` structure (`scene.eff_state`, mirror HasEffect)."""
        me = next((u for u in (ctx.units or []) if u.get("id") == ctx.uid), None)
        for e in ((me or {}).get("effects") or []):       # noms serialises OU dicts {name,...}
            nm = e if isinstance(e, str) else (e.get("name") if isinstance(e, dict) else None)
            if nm == "ConquerorImperative":
                return True
        eff = getattr(getattr(ctx, "scene", None), "eff_state", None)
        if eff is not None:
            return bool(eff.has_effect(ctx.uid, effect_type=int(EffectType.ConquerorImperative)))
        return False

    def _free_adjacent_tiles(self, ctx: NCContext) -> int:
        """`GetFreeAdjacentTiles(caster)` (IBattleQuery slot 0x52 IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles) = nombre de TUILES
        LIBRES placables adjacentes au caster.

        RESOLU LIVE #38b (`resolveVtableSlot` sur BattleQuery, ancre slot 0xca=IdunBattle.Core.Services.BattleQuery$$ReachedSummonCap -> slot 0x52 = `GetFreeAdjacentTiles`). CORRIGE le verdict case-31 (slot 0x51 =
        "GetAdjacentUnits TOUT CAMP") -- MEME lot de RE que le faux "gate per-player" refute #39 :
        GetAdjacentUnits prend 3 params (from/friendsOf/enemiesOf) et ne matche PAS le dispatch a
        1 argument du call-site (`FUN_180003bd0(0x51, itf, service, caster)`). Le natif IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles =
        `GetAdjacentTiles(caster,1,1,1)` puis `FilterInPlace(CanAddUnit(tile, world, 1,0,0))` = tuiles
        WALKABLE + VIDES + |dElev|<2 adjacentes. Mirror = `battle_query.adjacent_addable_count` (MEME
        primitive que AggressiveOnslaught @181163... et HammerOfWrath #116).

        Occupation LIVE = toutes les unites VIVANTES (obs_units, summons INCLUS ; fallback epos+fpos si
        obs vide). VALIDE #38b (A/B seed 777 tuile (4,7)) : tuile ouverte free=6 -> le natif N'EMET PAS
        a 0 summon (refute tout modele "adj==0 -> emit inconditionnel" ; l'ancien `_adjacent_units`=0
        aurait OVERFIRE ici). Borne OPPOSEE confrontee #38c (board C4_09, seeds 777 et 54321) : a 3
        Skitarii Tan n'a PLUS de voisin libre -> free==0 avec cap FAUX, et le natif EMET quand meme
        (branche encerclement) == le port. Les deux bornes du mirror sont donc mesurees."""
        if ctx.origin is None:
            return 0
        # #969-r3 : les DEUX substrats ne portent que la MAIN TILE -> expansion PAR PIED dans le
        # foyer `bq.occupied_positions` (`base` = l'univers choisi ici, jamais elargi).
        occ = {(u.get("col"), u.get("row")) for u in (ctx.obs_units or [])
               if not u.get("isDead") and u.get("col") is not None}
        occ = bq.occupied_positions(ctx, base=occ) if occ else bq.occupied_positions(
            ctx, include_origin=False)
        # ⚠ Ce `discard` ne retire que la MAIN TILE du caster. Si le CASTER lui-meme etait
        # multi-hex, ses AUTRES pieds resteraient occupes -- non tranche ici (aucune RE de ce site
        # ne dit si le natif s'exclut de son propre contenu sur CE chemin, qui passe par
        # `BattleQuery$$GetAdjacentTiles` et non par le selecteur DSL `AdjacentTiles`, seul dont on
        # ait LU le retrait d'empreinte). NO-OP sur tout caster a un pied, c.-a-d. partout
        # aujourd'hui.
        occ.discard(ctx.origin)
        return bq.adjacent_addable_count(ctx.origin, ctx.neigh_by_pos, ctx.walkable_by_pos,
                                         occ, ctx.elev_by_pos)

    def _reached_summon_cap(self, ctx: NCContext) -> bool:
        """Mirror `IdunBattle.Core.Services.BattleQuery$$ReachedSummonCap` (arg fixe ControlEdict 0x4b0=1200, ability
        TRIGGERED -> branche `IsTriggered` du natif) :
        `GetVariableForLevel(config(ControlEdict), maxSummons=49, level) <= GetChildrenCount(caster)`.

        - `IdunBattle.Entities.UnitExtensions$$GetChildrenCount` = len(`ParentComponent.children`) du caster, SANS FILTRE
          (predicat null) : liste append-only -- creee VIDE par `IdunBattle.Entities.Blueprints$$Unit+0x4fd`, alimentee
          au spawn (AddUnitOperation), JAMAIS purgee a la mort (`IdunBattle.Operations.RemoveUnitOperation$$Execute`
          ne touche que les listes units/removed du PlayerComponent, aucun RemoveChild n'existe) ->
          compte TOUT enfant jamais spawne, DEPOUILLES INCLUSES. NB : sematique DIFFERENTE du cap
          runner-face (`execute_control_edict_summon` : Skitarii VIVANTS) -- un Skitarii mort libere le
          re-summon cote runner mais reste compte ici (le toggle peut donc sortir cap "plein de morts").
          CONFRONTE LIVE #38c : a alive=3 < cap=5 <= ever=5 (Skitarii detruits par le camp adverse) la
          leaf native EMET toujours -> append-only confirme, et obs_units GARDE les depouilles.
        - level = `GetAbilityState(caster, ControlEdict).level` = niveau PASSIF de Tan Gi'da
          (ControlEdict est son passif) -> `ctx.ability_config(uid)["passive"]` (combatSnapshot).
        - Le gate amont `HasTriggeredAbility(caster, ControlEdict)` est structurel (l'unique porteur de
          DoctrinaImperatives porte ControlEdict) -- non re-code.

        Offline (aucun lien parent->enfants dans decisionView/observeBattle) : approx IDENTITE = squads
        `obs_units` du summon ControlEdict du MEME CAMP que le caster, MORTS INCLUS (obs_units garde les
        depouilles -- cf. RitesOfRestoration / project_decisionview_keeps_dead).

        *** BUG #38b (cause racine des miss s32/44/50) : la cle de config `constants.unitId` =
        `admecSmnVanguard` N'EST PAS le `visualId` expose LIVE. Le summon apparait dans obs_units/
        decisionView avec `visualId == admecNpc1Vanguard` (le champ `visualId` du config
        `admecSmnVanguard` pointe dessus). L'ancien mirror comparait `u.visualId == "admecSmnVanguard"`
        -> 0 enfant vu -> cap TOUJOURS False -> le natif emettait (cap atteint, 6-7 summons) la ou le
        port refusait. FIX : resoudre `constants.unitId -> gameconfig.visualId` (comme
        test_control_edict_live : SUMMON_VIS cle vs SUMMON_LIVE_VIS visualId). ***

        Exact tant que le caster est l'unique source de ce vid dans son camp (2 Marshals au meme camp
        pooleraient leurs comptes ; un summon RemoveUnit-ed -- retire du board, pas seulement mort --
        sortirait d'obs_units -> sous-compte). Cf. case-38 / case-38b."""
        import gameconfig as GC
        unit_id = ((GC.ability("ControlEdict") or {}).get("constants") or {}).get("unitId")
        if unit_id is None:
            return False
        # cle de config (admecSmnVanguard) -> visualId LIVE (admecNpc1Vanguard). #38b.
        live_vis = (GC.unit(unit_id) or {}).get("visualId") or unit_id
        obs = ctx.obs_units or []
        my_team = next((u.get("teamId") for u in obs if u.get("squadId") == ctx.uid), None)
        if my_team is None:
            return False
        kids = {u.get("squadId") for u in obs
                if u.get("visualId") == live_vis and u.get("teamId") == my_team}
        cfg_f = getattr(ctx, "ability_config", None)
        level = ((cfg_f(ctx.uid) or {}).get("passive") if callable(cfg_f) else None)
        cap = int(ability_var("ControlEdict", "maxSummons", level) or 5)   # per-niveau (3/4/5)
        return len(kids) >= cap

    def _usable(self, ctx: NCContext) -> bool:
        """Ability disponible pour le caster ? Le driver filtre deja `usable is False` (encode le
        `GetUseProbability`=0 apres usage / once-per-turn) ; permissif si `ability_targets` indispo."""
        if ctx.ability_targets is None:
            return True
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID:
                    return bool(a.get("targets") or a.get("usable", True))
        return True
