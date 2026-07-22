"""DoctrinaImperativesPlaybook — decision NonComparable self-cast (Tan Gi'da, toggle Protector/Conqueror)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first, _has_valid_targets


class DoctrinaImperativesPlaybook(NonComparablePlaybook):
    """`DoctrinaImperativesPlaybook` (RE @18112ccf0, ctor `NonComparablePlaybook(0x45e=1118)`).

    - cctor @18112cc80 : `MIN_UTILITY = Fix64.FromInt(1)` (gate Bucket.AddAction).
    - `GetUseProbability @18112cbf0` : `Fix64(1)` (100%) si `HasUsedAbilityThisTurn == false`, sinon `Fix64(0)`
      -> l'IA n'active DoctrinaImperatives qu'UNE fois par tour (le once-per-turn est reflete cote driver par
      `usable is False` une fois utilise, comme les autres actives -- non re-modelise ici).
    - `EvaluateNonComparable @18112c8d0` : **GATE 3 branches** (verdict re-expert task #31, slots BattleQuery
      0x51=`GetAdjacentUnits` / 0xc9=`ReachedSummonCap` @181070f60 resolus). Le natif ne score l'usage a 100
      (`GenerateAction(Fix64.FromInt(100))`) QUE si le gate passe -- sinon bucket vide -> pas d'action -> le
      fallback Comparable (attaque) prend la main. Notre port emmettait 1118 INCONDITIONNELLEMENT (overfire
      #31 : s01/s07 AdMech + 31337 s17, le toggle ecrasait une attaque native ab=69).

      Gate natif (mirror `_should_emit`) :
        count = GetEligibleTargetsForNormalAttack(caster) = cibles d'attaque normale SANS bouger (fromHere).
        - count == 0 : emit ssi `HasEffect(caster, ConquerorImperative 0x4e0=1248)` -- en Conqueror et rien a
          taper depuis la position courante -> rebascule Protector (reprend tank/summon) ; en Protector -> rien.
        - count > 0 : adj = `GetAdjacentUnits(caster)` (slot 0x51, TOUT CAMP) ;
          - adj > 0  : emit ssi `ReachedSummonCap(caster, ControlEdict 0x4b0=1200)` (slot 0xc9, cap
            maxSummons[level passif] (3/4/5) d'enfants JAMAIS spawnes atteint -- morts inclus, cf.
            `_reached_summon_cap` -> plus rien a gagner a rester en Protector -> basculer).
          - adj == 0 : emit inconditionnel (toggle libre).

    SELF-cast (comme NovaBoost/heals #76/#80) : la cible = self, position-independante -> le generateur
    `<GenerateActions>d__7` gate les tuiles de move par `HasValidTargets` (self position-independant -> aucune
    tuile motivee) et garde le 1er ajoute (NullPosition = cast EN PLACE) -> le natif RESTE EN PLACE
    (`_sweep_origin_first` -> to=None)."""
    ABILITY_ID = int(ActiveAbilityType.DoctrinaImperatives)   # 1118
    MIN_UTILITY = 1.0
    PRIORITY = 0          # get_Priority de base NonComparable (aucun override lu)
    UTILITY = 100.0       # GenerateAction(..., Fix64.FromInt(100)) @18112c8d0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self._usable(ctx):
            return []
        if not self._should_emit(ctx):
            return []
        to = next(iter(_sweep_origin_first(ctx)), None)
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (to if to != ctx.origin else None), "pred": self.UTILITY}]

    def _should_emit(self, ctx: NCContext) -> bool:
        """Mirror du gate `EvaluateNonComparable @18112c8d0` (3 branches, cf. docstring de classe)."""
        # count = GetEligibleTargetsForNormalAttack(caster) : `_has_valid_targets` mirror `HasValidTargets`
        # (0x3f) = >=1 ennemi attaquable a l'attaque NORMALE DEPUIS la position courante (fromHereCount>0).
        if not _has_valid_targets(ctx, ctx.uid):          # count == 0
            return self._is_conqueror(ctx)
        # count > 0
        if self._adjacent_units(ctx) > 0:                 # GetAdjacentUnits(caster) (slot 0x51, tout camp)
            return self._reached_summon_cap(ctx)          # emit ssi cap 5 Skitarii atteint
        return True                                       # adj == 0 -> toggle libre

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

    def _adjacent_units(self, ctx: NCContext) -> int:
        """`GetAdjacentUnits(caster)` (slot 0x51) = unites (TOUT CAMP : allies + ennemis) sur les tuiles
        hex-adjacentes (ordre natif `GetAdjacentTiles` = `neigh_by_pos`) a la position du caster."""
        if ctx.origin is None:
            return 0
        neigh = set((ctx.neigh_by_pos or {}).get(ctx.origin) or [])
        if not neigh:
            return 0
        occupied = set(ctx.epos or []) | set(ctx.fpos or [])
        return len(neigh & occupied)

    def _reached_summon_cap(self, ctx: NCContext) -> bool:
        """Mirror `BattleQuery.ReachedSummonCap @181070f60` (arg fixe ControlEdict 0x4b0=1200, ability
        TRIGGERED -> branche `IsTriggered` du natif) :
        `GetVariableForLevel(config(ControlEdict), maxSummons=49, level) <= GetChildrenCount(caster)`.

        - `GetChildrenCount @180ecf290` = len(`ParentComponent.children`) du caster, SANS FILTRE
          (predicat null) : liste append-only -- creee VIDE par `Blueprints.Unit @180eb3a3d`, alimentee
          au spawn (AddUnitOperation), JAMAIS purgee a la mort (`RemoveUnitOperation.Execute @180e8add0`
          ne touche que les listes units/removed du PlayerComponent, aucun RemoveChild n'existe) ->
          compte TOUT enfant jamais spawne, DEPOUILLES INCLUSES. NB : sematique DIFFERENTE du cap
          runner-face (`execute_control_edict_summon` : Skitarii VIVANTS) -- un Skitarii mort libere le
          re-summon cote runner mais reste compte ici (le toggle peut donc sortir cap "plein de morts").
        - level = `GetAbilityState(caster, ControlEdict).level` = niveau PASSIF de Tan Gi'da
          (ControlEdict est son passif) -> `ctx.ability_config(uid)["passive"]` (combatSnapshot).
        - Le gate amont `HasTriggeredAbility(caster, ControlEdict)` est structurel (l'unique porteur de
          DoctrinaImperatives porte ControlEdict) -- non re-code.

        Offline (aucun lien parent->enfants dans decisionView/observeBattle) : approx IDENTITE = squads
        `obs_units` de visualId == `ability("ControlEdict").constants.unitId` (admecSmnVanguard) du MEME
        CAMP que le caster, MORTS INCLUS (obs_units garde les depouilles -- cf. RitesOfRestoration /
        project_decisionview_keeps_dead). Exacte tant que le caster est l'unique source de ce vid dans
        son camp (2 Marshals au meme camp pooleraient leurs comptes ; un summon RemoveUnit-ed sortirait
        d'obs_units -> sous-compte). Cf. case-38."""
        import gameconfig as GC
        from engine.entities.effects.magnitude import ability_var
        vid = ((GC.ability("ControlEdict") or {}).get("constants") or {}).get("unitId")
        if vid is None:
            return False
        obs = ctx.obs_units or []
        my_team = next((u.get("teamId") for u in obs if u.get("squadId") == ctx.uid), None)
        if my_team is None:
            return False
        kids = {u.get("squadId") for u in obs
                if u.get("visualId") == vid and u.get("teamId") == my_team}
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
