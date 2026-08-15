"""Playbooks Comparable BESPOKE self-cast (RE ghidra gqfc5mff6c) — chacun OVERRIDE le scoring générique
(`ComparablePlaybook<T>.IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal`) par une utilité PROPRE (PAS `HEAL_PLAYBOOK.score`).
Identifiés par ID (pas `"Heal" in name` : leur nom n'a pas "Heal"). Self-cast / position-swept comme les
NonComparable heals (mais régime Comparable) -> candidate generators appelés par `ComparableAbilityGenerator`.

- `BloodChalicePlaybook`  (id 0x497=1175 ; bloodSanguinary/Nicodemus).
- `MomentShacklePlaybook` (id 0x4a0=1184 ; custoTrajann/Trajann).

(SpiritLeech(1104) = per-ENEMY attack + lifesteal -> régime `_best_attack`/registry, PAS ici.)

Poids `GetUtilityValue` résolus OFFLINE depuis `BattleConfiguration.Utilities.Default.ActiveAbilities`
(clés-strings du dump `stringliteral.json`, cf. `weights.Weights.sub`) :
  BloodChalice_AdjacentDamagedNonMechanicalFriend = 50
  MomentShackle_AdjacentEnemy                     = 25
"""
from __future__ import annotations

import hexgeo
import gameconfig as _gc
from engine import battle_query as bq
from engine.predict import heal_amount_config, predict_heal_effective, heal_utility
from engine.entities.effects.magnitude import ability_var  # #15 : GetVariableForLevel (CultDemagogue nrOfSummons)
from engine.entities.active_ability_type import ActiveAbilityType  # #158 : ABILITY_ID -> enum (abilities ACTIVES, cat W_KEY=ActiveAbilities)
from engine.playbook.static_threshold_gate import STATIC_UTILITY_THRESHOLD  # #419-r1-...-r2-r4

_TRAITS_CACHE: dict = {}


def _traits(visual_id) -> list:
    """Traits gameconfig d'une unité par visualId (cache). Pour la porte `IsMechanical` de BloodChalice."""
    if not visual_id:
        return []
    if visual_id in _TRAITS_CACHE:
        return _TRAITS_CACHE[visual_id]
    uid = _gc.resolve_unit_id(visual_id)
    u = _gc.unit(uid) if uid else None
    t = (u or {}).get("traits") or []
    _TRAITS_CACHE[visual_id] = t
    return t


class BloodChalicePlaybook:
    """`IdunBattle.AI.Playbook.BloodChalicePlaybook$$EvaluateInternal` (id 0x497=1175, bloodSanguinary/Nicodemus).

    Utilité BESPOKE (override total, PAS la HealUtility générique) = `count(alliés non-mécaniques
    ADJACENTS au caster, PV% < seuil) × W`. Self-cast AoE (cible = MainTile du caster ; `GenerateAction
    (this, casterTile, ...)`). Position-swept par le générateur.
    - Cibles (`GetTargets`) : `IsAffectedByHealType` = ami NON-mécanique ; PV% via `GetStat(Health, 1)`
      (FillUpStatComponent.GetStatPart(1) = round(cur/max×100)).
    - seuil = `AbilityConfiguration.GetNumberConstant(0x4f)` = config `healthPct` = 50.
    - W = `Utilities.Default.ActiveAbilities.BloodChalice_AdjacentDamagedNonMechanicalFriend` = 50.
    - MIN_UTILITY = `Fix64.FromInt(1)` = 1 (IdunBattle.AI.Playbook.BloodChalicePlaybook$$.cctor) -> gate `count>=1` (1×50=50>1).

    ⚠ **`IdunBattle.AI.Playbook.BloodChalicePlaybook$$ShouldExecute` EST DU CODE MORT, et c'est une
    lecture de REACHABILITY, pas une absence d'observation** (`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1`).
    Son corps existe et il est LU :

        thr = AbilityConfiguration.GetNumberConstant(0x4f);                 // healthPct = 50
        sum = 0;
        foreach (u in battleQuery.<slot d'interface 0x83 = 131 GetAdjacentFriends>(casterTile, caster))
            if (!UnitExtensions.IsMechanical(u))
                sum += thr - UnitExtensions.GetStat(u, StatType.Health, 1, 0);   // PV%
        return sum > 0;

    Mais AUCUN chemin ne l'appelle pour une instance de `BloodChalicePlaybook` :
      * `ShouldExecute` vit au slot de vtable **+0x328** et n'a qu'UN appelant,
        `ComparablePlaybook<T>$$CalculateActionUtility` ;
      * `CalculateActionUtility` n'a elle-meme qu'UN appelant (`list_xrefs` : un seul
        `UNCONDITIONAL_CALL`), `ComparablePlaybook<T>$$EvaluateInternal` ;
      * or `BloodChalicePlaybook$$EvaluateInternal` **OVERRIDE** ce corps generique -- meme slot
        (+0x238, celui que `BasePlaybook$$Evaluate` invoque), meme signature `(caster,
        casterPosition, abilityState, customUtility)` -- et son corps appelle `GenerateAction` +
        `Bucket$$AddAction` DIRECTEMENT, sans jamais passer par `CalculateActionUtility`.
    Le vtable porte donc l'override, et rien ne le franchit. Meme forme que `CultDemagoguePlaybook`
    (override d'`EvaluateInternal`, AUCUN `ShouldExecute` declare) ; a l'oppose,
    `MomentShacklePlaybook` n'override PAS `EvaluateInternal`, et c'est pour ca que SON
    `ShouldExecute` est vivant et porte plus bas.

    ⚠ Et le gate mort n'est PAS equivalent a celui d'`EvaluateInternal` -- l'ecart serait
    OBSERVABLE s'il vivait : `EvaluateInternal` compte les amis STRICTEMENT sous le seuil
    (`if (pct < thr) count++`, gate `count >= 1`), quand `ShouldExecute` SOMME des ecarts SIGNES
    (`sum += thr - pct`), donc un ami a 90 % de PV y contribue **-40** et peut annuler un ami a
    20 %. Le porter << au cas ou >> aurait ajoute un refus que le natif ne prononce pas.
    ⚠ Les deux corps n'interrogent meme pas la MEME requete : `EvaluateInternal` appelle le slot
    **0x84 = 132** (`GetAdjacentFriends(from: UnitPosition, unit)` -> `GetAdjacentUnits`),
    `ShouldExecute` le slot **0x83 = 131** (`GetAdjacentFriends(from: IEntity, unit)` ->
    `IterateAdjacentTiles` + `GetUnitsOnTiles`). Quatre surcharges vivent aux slots 129..132 ; les
    apparier a leurs corps s'est fait par les TYPES DECLARES de `frida/methods.tsv`, pas par
    l'ordre."""

    ABILITY_ID = int(ActiveAbilityType.BloodChalice)  # 1175
    W_KEY = "BloodChalice_AdjacentDamagedNonMechanicalFriend"   # cat ActiveAbilities
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx) -> list:
        me = ctx.me
        if me is None:
            return []
        team = me.get("team")
        w = ctx.wt.sub("ActiveAbilities", self.W_KEY)          # 50
        thr = int(((_gc.ability("BloodChalice") or {}).get("constants") or {}).get("healthPct") or 50)
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        # amis VIVANTS non-mécaniques (self exclu) positionnés + PV% courant
        allies = []
        for u in ctx.units:
            if u.get("id") == ctx.uid or u.get("team") != team or not u.get("alive"):
                continue
            p = u.get("pos")
            if not p or p.get("col") is None:
                continue
            if "Mechanical" in _traits(u.get("visualId")):
                continue
            ob = obs_by_sq.get(u.get("id")) or {}
            mx = int(ob.get("hpMax") or 0)
            cur = int(ob.get("hp") or 0)
            pct = round(cur / mx * 100) if mx > 0 else 100
            allies.append(((p["col"], p["row"]), pct))
        best = None   # (T, util)
        for T in ctx.reach_nc:   # origine d'abord -> keep-first au tie (Bucket.AddAction #76)
            count = sum(1 for pos, pct in allies
                        if pct < thr and bq.is_adjacent(T, pos, ctx.elev_by_pos, bq.neigh_map(ctx)))  # AdjacentUnits (#45)
            util = count * w
            if util < self.MIN_UTILITY:
                continue
            if best is None or util > best[1]:   # strict > : 1er max garde
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg BloodChalice u{ctx.uid}] W={w} thr={thr} best={best}", file=sys.stderr)
        if best is None:
            return []
        T, util = best
        target = ctx.tile_id_by_pos.get(T, ctx.uid)   # self-cast AoE = MainTile-id
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util, "full": util}]


class MomentShacklePlaybook:
    """`MomentShacklePlaybook IdunBattle.AI.Playbook.Loki.MomentShacklePlaybook$$.ctor` (id 0x4a0=1184, custoTrajann/Trajann). Comparable.

    Utilité = HealUtility(SELF-heal) + CalculateCasterPositionUtility, sommées par
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`. Cible = SOI (self-heal). Position-swept.
    - Self-heal : `IdunBattle.AI.Playbook.Loki.MomentShacklePlaybook$$MakeHealPredictions` -> `GetHealAmount = ConfigVar(0x20)` = `hpToHeal[level]`
      (MomentShackle config a `hpToHeal`) -> `GenerateHealPredictions` -> `IdunBattle.Core.Services.DamagePrediction$$PredictHeal`
      (`min(healAmount, missing_self)`, #79) -> `HealUtility` = `effective/(maxHP+1)×100`. POSITION-INDÉP.
    - Position : `IdunBattle.AI.Playbook.Loki.MomentShacklePlaybook$$CalculateCasterPositionUtility` = `count(ennemis ADJACENTS au caster@T) × W`.
      W = `Utilities.Default.ActiveAbilities.MomentShackle_AdjacentEnemy` = 25.
    - MIN_UTILITY = le PREMIER static de la classe, `Fix64(10)` : `...MomentShacklePlaybook$$.cctor`
      y ecrit bien `Fix64(1)`, mais `ComparablePlaybook<T>$$.cctor` y ecrit `Fix64(10)` APRES lui
      (cf. `playbook/static_threshold_gate.py`, seuil MESURE sur deux identites de la famille).
      Position-swept, origine-préférée (#76)."""

    ABILITY_ID = int(ActiveAbilityType.MomentShackle)  # 1184
    W_KEY = "MomentShackle_AdjacentEnemy"   # cat ActiveAbilities
    #: Foyer UNIQUE du seuil de la famille -- jamais un litteral recopie ici.
    MIN_UTILITY = STATIC_UTILITY_THRESHOLD

    def generate_candidates(self, ctx) -> list:
        me = ctx.me
        if me is None:
            return []
        w = ctx.wt.sub("ActiveAbilities", self.W_KEY)   # 25
        # self-heal magnitude = hpToHeal[activeLevel] (ConfigVar(0x20)) ; None -> saturation (défensif)
        hc = ctx.heal_config(ctx.uid)
        heal_amt = heal_amount_config("MomentShackle", hc["active"], hc["passive"], hc["multiplier"])
        ob = next((u for u in ctx.obs_units if u.get("squadId") == ctx.uid), None) or {}
        smax = int(ob.get("hpMax") or 0)
        scur = int(ob.get("hp") or 0)
        eff = max(0, smax - scur) if heal_amt is None else predict_heal_effective(heal_amt, scur, smax)
        self_heal_u = heal_utility(eff, smax, is_friend=True, is_boss=False)   # POSITION-INDÉPENDANT
        best = None   # (T, util)
        for T in ctx.reach_nc:   # origine d'abord -> keep-first au tie (#76)
            adj_enemies = sum(1 for e in ctx.epos if bq.is_adjacent(T, e, ctx.elev_by_pos, bq.neigh_map(ctx)))
            util = self_heal_u + adj_enemies * w
            # `IdunBattle.AI.Playbook.Loki.MomentShacklePlaybook$$ShouldExecute`, lu verbatim :
            #     return Fix64.op_GreaterThan(attackHealUtility, <premier static de la classe>);
            # Comparaison STRICTE, donc une utilite EGALE au seuil est REFUSEE (le port ecrivait
            # `util < MIN_UTILITY`, borne INCLUSIVE, #419-r1-tr14-r5-r2-r1-r1-r1-r2). Le SEUIL, lui,
            # vaut `Fix64(10)` et non `Fix64(1)` : le `.cctor` de la base generique ecrase celui de
            # la classe derivee (#419-r1-tr14-r5-r2-r1-r1-r1-r2-r4, mesure sur 1150 et 1069).
            if not util > self.MIN_UTILITY:
                continue
            if best is None or util > best[1]:   # strict >
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg MomentShackle u{ctx.uid}] W={w} healAmt={heal_amt} selfHealU={self_heal_u:.2f} "
                  f"best={best}", file=sys.stderr)
        if best is None:
            return []
        T, util = best
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,   # SELF-target (self-heal)
                 "to": (T if T != ctx.origin else None), "pred": util, "full": util}]


class CultDemagoguePlaybook:
    """`IdunBattle.AI.Playbook.Loki.CultDemagoguePlaybook$$EvaluateInternal` (id 0x49b=1179, Isaak genesPrimus). COMPARABLE
    BESPOKE (IdunBattle.AI.Playbook.Loki.CultDemagoguePlaybook$$.ctor = `ComparablePlaybook(0x49b)` -> classe COMPARABLE, PAS NonComparable ;
    override TOTAL d'`EvaluateInternal`, AUCUNE `MakeDamagePredictions` -> ne va PAS dans noncomparable/).
    Cible = un ENNEMI (<=2 hex) ; cast EN PLACE (pas de sweep : régime Comparable, position caster fixée).

    Utilité (par cible éligible) :
      u = 1 + min(#tuiles_libres autour CIBLE r2, nrOfSummons[lvl]) * W
            + (#decoys + #neophytes AMIS autour CIBLE r2) * W
    W = `Utilities.Default.ActiveAbilities.CultDemagogue_FriendlyDecoysAndNeophytes` = 20 (MÊME poids pour
    les DEUX termes, DAT_18327dcc8 unique). MIN_UTILITY = `Fix64.FromInt(1)` = 1 (IdunBattle.AI.Playbook.Loki.CultDemagoguePlaybook$$.cctor).
    Helpers natifs :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$PossibleTilesForDecoys` =
      `CanAddUnit( SurroundingTiles(<DSLSelectors+0x60>, includeCenter: 0,
                                    range = GetNumberConstant(0x44) = 2, onlyMovable: 0,
                                    includeNonWalkable: 0),
                   isSteppable: <DSLTriggers+0x40> )`.
      ⚠ **`<DSLSelectors+0x60>` est `Target`, PAS `Caster`** (#957). Le port a longtemps compté les
      tuiles libres autour du CASTER : c'était un FORK avec sa propre face COMBAT, qui dit déjà
      « tuiles libres ≤ `range` hex de la CIBLE » (`genestealer.SpawnDecoys` ->
      `_surrounding_free_tiles(state, _pos_of(state, target_id), radius)`), et avec la carte de
      champs que le reste du port cite partout (`+0x30 = Owner`, `+0x48 = Caster`, `+0x60 = Target`
      — cf. `HadesAutocannonsAbility`, `MassDriverAcceleratorAbility`, `FragBombAbility$$
      GetAdjacentTargets`, qui SOUSTRAIT `+0x48` pour retirer le caster).
      CONSÉQUENCE : ce terme n'est **PAS** constant sur les cibles — il DÉPARTAGE l'argmax, et il le
      domine (`W = 20`, `min(...)` va de 0 à `nrOfSummons`, quand le terme 2 dépasse rarement 1 ou 2).
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$GetDecoyAmount` = `GetVariableForLevel(0x4f)` = `nrOfSummons` (4->8 selon niveau, NON
      rarity-scaled). i2 : « up to 8 decoys ».
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$FriendlyDecoysAroundTarget` / `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$FriendlyNeophytesAroundTarget` =
      `SurroundingEnemies(<DSLSelectors+0x60> = Target, range=GetNumberConstant(0x44)=2, unique: 1,
      sel: 3)` filtré `UnitsWithId(genesSmnDecoy / genesSmnNeophyte)` -> les alliés du CASTER de ce
      visualId à <=2 hex de la cible (« ennemis DE LA CIBLE » = alliés du caster). Count via
      `SelectUniqueUnits` (le param 3 = mode SelectUnit, PAS un cap sur le count).
    L'ÉLIGIBILITÉ (ennemi <=2 hex) est déléguée à `ability_targets` (le RPC applique
    `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$GetDynamicInvalidTargetReason`).

    ⚠ LES DEUX `AbilityEntities` DU CORPS NE SONT PAS LE MÊME, et c'est LU : `PossibleTilesForDecoys`
    est évalué sur l'`AbilityEntities` COURANTE du `foreach` (celle que
    `GetEligibleTargetsSelectable` produit pour la cible en cours), tandis que les deux
    `SelectUniqueUnits` reçoivent un `AbilityEntities` NEUF (`memset` 0x128) dont SEUL `+0x10 =
    target` est renseigné. Aucun des trois sélecteurs ne lit le champ `caster` (`+0x08`) : les trois
    ancrent sur `<DSLSelectors+0x60>`, donc le buffer nul suffit."""

    ABILITY_ID = int(ActiveAbilityType.CultDemagogue)  # 1179
    W_KEY = "CultDemagogue_FriendlyDecoysAndNeophytes"   # cat ActiveAbilities ; W=20 (seed-bc)
    MIN_UTILITY = 1.0
    _RANGE = 2                             # constants.range (GetNumberConstant 0x44)
    _DECOY_VID = "genesSmnDecoy"           # constants.unitId
    _NEOPHYTE_VID = "genesSmnNeophyte"     # constants.unitId_2

    def generate_candidates(self, ctx) -> list:
        me = ctx.me
        if me is None or ctx.ability_targets is None:
            return []
        # cibles ennemies éligibles (RPC applique IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$GetDynamicInvalidTargetReason : ennemi <=2 hex).
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # ORDRE PRESERVE (#957) : `IdunBattle.AI.BucketSystem.Bucket<…>$$AddAction` SEED le premier
        # ajoute puis ne remplace que si STRICTEMENT superieur -- a utilite EGALE, c'est donc la
        # PREMIERE cible enumeree par `GetEligibleTargetsSelectable` qui gagne. Un `set` Python perd
        # cet ordre, et l'argmax devenait alors dependant du hachage : le port pouvait rendre deux
        # cibles differentes d'une execution a l'autre sur un tie. La liste garde l'ordre du RPC,
        # qui EST celui du selecteur natif.
        tgt_ids: list = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    tid = t.get("targetId")
                    if t.get("kind") == "unit" and tid is not None and tid not in tgt_ids:
                        tgt_ids.append(tid)
        if not tgt_ids:
            return []
        w = ctx.wt.sub("ActiveAbilities", self.W_KEY)          # 20
        lvl = ctx.heal_config(ctx.uid)["active"]               # niveau ACTIF du caster
        decoy_amt = int(ability_var("CultDemagogue", "nrOfSummons", lvl) or 0)
        # decoys/neophytes AMIS positionnés (pour le terme 2, par cible).
        team = me.get("team")
        summons = [(u["pos"]["col"], u["pos"]["row"]) for u in ctx.units
                   if u.get("team") == team and u.get("alive") and u.get("pos")
                   and u["pos"].get("col") is not None
                   and u.get("visualId") in (self._DECOY_VID, self._NEOPHYTE_VID)]
        pos_by_id = {u.get("id"): u.get("pos") for u in ctx.units}
        best = None   # (target, util)
        for tid in tgt_ids:
            tp = pos_by_id.get(tid)
            if not tp or tp.get("col") is None:
                continue
            tpos = (tp["col"], tp["row"])
            # Terme 1 -- PAR CIBLE (#957) : `min(|PossibleTilesForDecoys(TARGET)|, nrOfSummons)`.
            # L'ancre est `<DSLSelectors+0x60> = Target`, pas le caster (cf. la docstring).
            term1 = min(self._free_tiles_around(ctx, tpos), decoy_amt) * w
            n_around = sum(1 for s in summons if hexgeo.distance(tpos, s) <= self._RANGE)
            util = 1.0 + term1 + n_around * w
            if best is None or util > best[1]:            # argmax strict (Bucket keep-first au tie)
                best = (tid, util)
        if ctx.debug:
            import sys
            print(f"    [dbg CultDemagogue u{ctx.uid}] W={w} decoyAmt={decoy_amt} "
                  f"tgts={sorted(tgt_ids)} best={best}", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None,
                 "pred": best[1], "full": best[1]}]

    def _free_tiles_around(self, ctx, center) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$PossibleTilesForDecoys` :
        `CanAddUnit(SurroundingTiles(<DSLSelectors+0x60> = Target, includeCenter: 0, range = 2,
        onlyMovable: 0, includeNonWalkable: 0), isSteppable: <DSLTriggers+0x40>)` = tuiles LIBRES
        placeables à <=2 hex de la **CIBLE** (#957 : `center` est la position de la cible, pas
        l'origine du caster). `includeCenter = 0` LU au call-site -> le centre est exclu, et pas
        seulement parce qu'il est occupé.

        Occupation LIVE = `epos u fpos u origine` (frais), PAS l'`occupantUnitId` caché du boardGraph
        (cf. `can_add_unit` #116). L'origine du caster est ajoutée EXPLICITEMENT : `ctx.fpos` exclut
        le mover, et depuis #957 `center` ne l'est plus (il vaut la tuile de la cible, déjà dans
        `epos`)."""
        if center is None:
            return 0
        # #969-r3 : occupation PAR PIED (`TileContentComponent`), foyer `bq.occupied_positions`.
        # L'origine du caster y entre par `include_origin` (`fpos` exclut le mover).
        occ = bq.occupied_positions(ctx)
        return sum(1 for T in (ctx.walkable_by_pos or {})
                   if T != center and hexgeo.distance(center, T) <= self._RANGE
                   and bq.can_add_unit(T, ctx.walkable_by_pos, occ))


# Registry des self-cast/ENEMY-target bespoke Comparable (dispatché par id d'ability présente sur le caster).
# NB : CultDemagogue cible un ENNEMI (pas self) mais partage le même régime bespoke Comparable (override
# EvaluateInternal, hors du plan `evals`) et le même dispatch _bespoke_candidates.
BESPOKE_SELFCAST: dict = {
    BloodChalicePlaybook.ABILITY_ID: BloodChalicePlaybook(),
    MomentShacklePlaybook.ABILITY_ID: MomentShacklePlaybook(),
    CultDemagoguePlaybook.ABILITY_ID: CultDemagoguePlaybook(),
}
