"""UnstoppableMomentumReworkedPlaybook -- utilite = #ennemis TRAVERSES par la charge."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import entity_trait_names, has_any_trait
from engine.runner.components import NOT_DISPLACEABLE_TRAITS   # foyer UNIQUE de la liste (#498-r4)

from ._base import NCContext, NonComparablePlaybook, native_priority, _normal_attack_ids


class UnstoppableMomentumReworkedPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.UnstoppableMomentumReworkedPlaybook$$EvaluateNonComparable`
    (id 0x480 = 1152). Face DECISION de l'ability portee cote COMBAT par #498.

    Corps natif, remis en C# :

        minUtility = EnemyCouldBeDamagedWithNormalAttack(caster) ? <statique[0]> : <statique[1]>
        bucket     = new Bucket(0, Nullable<Fix64>(minUtility))
        foreach (e in BasePlaybook.GetEligibleTargetsSelectable(this, caster,
                                                                casterPosition.MainTile)) {
            tiles = UnstoppableMomentumReworkedAbility.GetAllTilesInLine(ability).SelectTiles(e);
            count = 0;
            foreach (tile in tiles) {
                trigger = UnstoppableMomentumReworkedAbility.CanContinue(
                              ability, DSLSelectors.Entity(dsl, tile));
                if (!trigger.<slot 5 = ShouldTrigger>(e, 0x20)) break;      // ARRET, pas `continue`
                unit = UnitExtensions.GetUnit(tile, state);
                if (unit != null && !UnitExtensions.IsFriend(unit, caster, state)) count++;
            }
            bucket.AddAction(BasePlaybook.GenerateAction(this, casterPosition, e, Fix64(count)));
        }

    TROIS lectures qui ne se devinent pas, et qu'aucune des deux fiches (#498 §4-§5, backlog) ne
    portait :

    1. **`MIN_UTILITY` est DYNAMIQUE, a deux valeurs.** Le `.cctor` ecrit DEUX statiques --
       `Fix64(2)` en `[0]` et `Fix64(1)` en `[+8]` -- et la leaf choisit selon
       `IdunBattle.AI.Playbook.BasePlaybook$$EnemyCouldBeDamagedWithNormalAttack(caster)` :
       **2** si le caster peut deja toucher un ennemi a l'attaque NORMALE, **1** sinon. Autrement
       dit : quand il a deja une attaque disponible, la charge doit traverser au moins DEUX ennemis
       pour valoir la peine ; sinon un seul suffit. Un `MIN_UTILITY` scalaire aurait ete faux dans
       l'un des deux regimes -- et vert dans l'autre.
    2. **Le `break` fait de l'utilite un PREFIXE, pas un compte.** Des que `CanContinue` refuse une
       tuile, la boucle SORT : les ennemis situes DERRIERE le blocage ne comptent pas. C'est la
       forme du natif, et c'est la seule qui rende la charge « ce que je vais reellement
       traverser ».
    3. **`CasterTile` de la ligne est la POSITION CANDIDATE, pas la tuile reelle du caster.** LU
       dans `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` (surcharge 3 args),
       qui memset la struct `AbilityEntities` (0x124 -> 0x128 alignee) puis ecrit
       `+0x40 casterTile = possibleCasterTile` et `+0x48 casterTiles = ToList(possibleCasterTile)`
       -- avec `+0x08 caster`, `+0x10 target` (l'entite cible), `+0x18 owner = caster`,
       `+0x30 targetTile = GetMainTile(cible)`, `+0x38 targetTiles = GetTiles(cible)`. Ces offsets
       sont ceux d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (l'overload 32 params, ou
       Ghidra porte deja les noms) -- **a ne pas confondre avec les slots de `DSLSelectors`**
       (`+0x20 AllUnits`, `+0x48 Caster`, `+0x60 Target`, `+0x68 ActiveTarget`), qui sont un AUTRE
       objet et que plusieurs fiches citent au meme endroit. La ligne est donc re-tracee DEPUIS
       CHAQUE POSITION balayee ; la traiter comme fixe aurait fige l'utilite.

    `GetAllTilesInLine` (lu par #498) =
    `First(TilesBehindInLine(CasterTile@0x50, Target@0x60, settings{+0x10 = 1, +0x11 = 1}),
    amount: 10)` -> `bq.get_tiles_behind(..., max_count=10, check_walkable=True,
    update_reference=True)`.
    `CanContinue(nextTile)` (lu par #498) =
    `CanBeDisplaced(Units(nextTile, unique:1, sel:1)) | IsCanAddUnit(nextTile)`
    (`AbilityTrigger$$op_BitwiseOr`) -- un OU, donc une tuile LIBRE (placable) passe tout autant
    qu'une tuile occupee par une unite deplacable.

    `get_Priority` : 1152 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170) -> tier **0**.
    Hierarchie LUE dans `data/symbols/<build>/frida/classes.tsv` :
    `IdunBattle.AI.Playbook.NonComparablePlaybook`1` (le meme controle que pour 1088 -- le nom du
    `.ctor` gshared ne fait pas foi).

    ECARTS ASSUMES, nommes :
    * `IsDisplaceable` ne teste ici que les trois traits + la vie : `HasFlag(0x19)` et
      `EntityType == Unit` ne sont pas lisibles du substrat DECISION -- c'est le residu **#498-r4**,
      deja ouvert et de direction PERMISSIVE, et ce site en est un troisieme porteur.
    * `IsCanAddUnit` est reduit a « tuile marchable et inoccupee » (`ctx.walkable_by_pos`, le meme
      gate STATIQUE de placement que `HammerOfWrathPlaybook` #116) : le natif y ajoute des gates
      d'empreinte que le canal ne publie pas. Direction PERMISSIVE, comme le gate jumeau.
    * L'eligibilite PAR POSITION est reconstituee comme partout ailleurs : `fromHere` a l'origine
      (l'ordre EXACT du selector natif), l'union `targets` ailleurs (approximation d'ORDRE, cf.
      `eligible_target_tiles`)."""

    ABILITY_ID = int(ActiveAbilityType.UnstoppableMomentumReworked)      # 0x480 = 1152
    #: `.cctor` : `statiques[0] = Fix64(2)`, `statiques[1] = Fix64(1)`. Le seuil EFFECTIF est choisi
    #: par `EnemyCouldBeDamagedWithNormalAttack` -- cf. `min_utility_for`.
    MIN_UTILITY_WITH_ATTACK = 2.0
    MIN_UTILITY_WITHOUT_ATTACK = 1.0
    #: Valeur de repli du champ de base (le driver ne l'utilise pas ici : le gate est applique dans
    #: `generate_candidates`, avec le seuil DYNAMIQUE). Pose a la BORNE BASSE pour qu'un appelant
    #: qui lirait l'attribut ne refuse jamais plus que le natif.
    MIN_UTILITY = MIN_UTILITY_WITHOUT_ATTACK
    PRIORITY = native_priority(int(ActiveAbilityType.UnstoppableMomentumReworked))   # 0 = Normal

    # ------------------------------------------------------------------------------------------
    def _enemy_could_be_damaged_with_normal_attack(self, ctx: NCContext) -> bool:
        """`IdunBattle.AI.Playbook.BasePlaybook$$EnemyCouldBeDamagedWithNormalAttack(attacker)` =
        `GetAllNormalAttackTargets(attacker).<liste>.Count > 0`, ou `GetAllNormalAttackTargets` est
        `IBattleQuery` slot **0x45** `(unit, UnitExtensions.GetNormalAttackType(unit), 0)` =
        `GetAllValidTargetsFromAllPossibleMovementTiles`.

        C'est bien l'UNION sur toutes les tuiles de move (le `targets` du RPC `abilityTargets`), PAS
        `HasValidTargets` depuis la position courante (`fromHere`) -- les deux existent cote port et
        les confondre deplacerait le seuil d'une unite.

        ⚠ Ce predicat ne dit rien du DEGAT : il compte des CIBLES. Le nom natif dit `Damaged`, le
        corps dit `Count > 0` ; on mirrore le corps."""
        if ctx.ability_targets is None:
            return False           # canal absent -> borne BASSE du seuil (jamais plus restrictif)
        for aid in _normal_attack_ids(ctx, ctx.uid):
            at = ctx.ability_targets(ctx.uid, aid) or {}
            for u in (at.get("units") or []):
                if u.get("unitId") != ctx.uid:
                    continue
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == aid and (a.get("targets") or []):
                        return True
        return False

    def min_utility_for(self, ctx: NCContext) -> float:
        """Le seuil EFFECTIF du `Bucket` pour CE caster (2 ou 1, cf. la docstring de classe)."""
        return (self.MIN_UTILITY_WITH_ATTACK
                if self._enemy_could_be_damaged_with_normal_attack(ctx)
                else self.MIN_UTILITY_WITHOUT_ATTACK)

    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _is_displaceable(ctx: NCContext, unit: dict) -> bool:
        """`IdunBattle.Entities.UnitExtensions$$IsDisplaceable` -- vivante, et sans aucun des trois
        traits refusants (`NOT_DISPLACEABLE_TRAITS`, foyer UNIQUE cote runner).

        MEME corps que `ItItchesPlaybook._is_displaceable` et
        `loki_custom.py::MortisRoundPlaybook._is_displaceable`, et MEME residu ouvert (#498-r4) :
        `HasFlag(0x19 UnitFlag.Undisplaceable)` et la tete `EntityType == Unit` ne sont pas dans le
        substrat DECISION."""
        if unit is None or unit.get("alive") is False:
            return False
        scene = getattr(ctx, "scene", None)
        uctx = scene.ctx(unit.get("id")) if scene is not None else None
        return not has_any_trait(entity_trait_names(uctx, unit.get("visualId")),
                                 NOT_DISPLACEABLE_TRAITS)

    def _can_continue(self, ctx: NCContext, tile: tuple, occupant: dict | None) -> bool:
        """`UnstoppableMomentumReworkedAbility$$CanContinue(nextTile)` =
        `CanBeDisplaced(Units(nextTile)) | IsCanAddUnit(nextTile)` -- un OU (`op_BitwiseOr`).

        `IsCanAddUnit` est reduit au gate STATIQUE de placement : tuile MARCHABLE et INOCCUPEE.
        `ctx.walkable_by_pos` vide (canal muet) -> on ne refuse pas sur ce volet (PERMISSIF)."""
        if occupant is not None:
            return self._is_displaceable(ctx, occupant)      # CanBeDisplaced(Units(tile))
        wb = ctx.walkable_by_pos or {}
        if not wb:
            return True                                      # canal muet -> pas de refus invente
        return bool(wb.get(tile, False))                     # IsCanAddUnit sur tuile libre

    # ------------------------------------------------------------------------------------------
    def _targets_by_position(self, ctx: NCContext) -> tuple[list, list]:
        """`GetEligibleTargetsSelectable` en domaine UNITE : (`fromHere`, union), ordre preserve."""
        if ctx.ability_targets is None:
            return [], []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        fromhere: list[int] = []
        union: list[int] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for key, out in (("fromHere", fromhere), ("targets", union)):
                    for t in (a.get(key) or []):
                        if t.get("kind") == "unit" and t.get("targetId") is not None:
                            out.append(int(t["targetId"]))
        return list(dict.fromkeys(fromhere)), list(dict.fromkeys(union))

    @staticmethod
    def _first_step(frm: tuple, to: tuple) -> tuple | None:
        """La PREMIERE tuile de la ligne native `GetTilesBehind(frm, to)` : `frm - DirectionTo(frm, to)`.

        ⚠ POURQUOI CE DETOUR, ET CE QU'IL NOMME. Le natif calcule
        `dir = CubeCoordinate$$DirectionTo(cube(frm), cube(to))`, qui **CLAMPE chaque composante a
        +-1** (mirror porte : `battle_query.direction_to`), puis avance par `next = cur - dir` --
        donc un pas UNITAIRE. Le mirror partage `battle_query.get_tiles_behind`, lui, pose
        `dir = cube(to) - cube(frm)` **SANS clamp** : les deux coincident exactement quand `to` est
        ADJACENT a `frm` (le regime de ses quatre call-sites connus), et DIVERGENT des que la cible
        est plus loin -- la ligne avance alors par bonds de `d(frm, to)` au lieu de 1.

        `UnstoppableMomentumReworked` est la premiere ability portee dont la cible n'est PAS
        adjacente (c'est une CHARGE). On ne forke donc pas la geometrie : on donne au foyer partage
        le PAS UNITAIRE comme `to`, ce qui lui fait produire exactement la ligne native
        (`frm + k * pas`, k = 1..). La divergence du foyer elle-meme est un residu NOMME -- elle
        touche aussi `DarkTalonStrikePlaybook` et `ExcruciatingFrequenciesPlaybook`, dont les
        cibles-tuiles peuvent etre distantes, et sa correction exige de rejouer LEURS confrontations
        live (ce que cette tranche ne fait pas)."""
        import hexgeo
        fx, fy, fz = hexgeo.to_cube(frm[0], frm[1])
        dx, dy, dz = bq.direction_to(frm, to)
        if (dx, dy, dz) == (0, 0, 0):
            return None
        return hexgeo.from_cube(fx - dx, fz - dz)

    def _utility(self, ctx: NCContext, caster_pos: tuple, target_pos: tuple,
                 occ_by_pos: dict) -> float:
        """#ennemis TRAVERSES le long de la ligne, ARRETE a la 1re tuile ou `CanContinue` refuse."""
        step1 = self._first_step(caster_pos, target_pos)
        if step1 is None:
            return 0.0
        line = bq.get_tiles_behind(
            caster_pos, step1, max_count=10, check_walkable=True, update_reference=True,
            elevation_at=(lambda p: (ctx.elev_by_pos or {}).get(p)),
            walkable_at=(lambda p: (ctx.walkable_by_pos or {}).get(p, True)),
            tile_exists=((lambda p: p in ctx.walkable_by_pos) if ctx.walkable_by_pos else None))
        count = 0
        for tile in line:
            occ = occ_by_pos.get(tile)
            if not self._can_continue(ctx, tile, occ):
                break                                # `break` natif : PREFIXE, pas un filtre
            if occ is not None and not occ.get("ctrl"):
                count += 1                           # `unit != null && !IsFriend(unit, caster)`
        return float(count)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        fromhere, union = self._targets_by_position(ctx)
        if not fromhere and not union:
            return []
        min_u = self.min_utility_for(ctx)
        pos_by_id = {}
        occ_by_pos = {}
        for u in (ctx.units or []):
            p = u.get("pos") or {}
            if p.get("col") is None or u.get("alive") is False:
                continue
            t = (p["col"], p["row"])
            pos_by_id[u.get("id")] = t
            occ_by_pos[t] = u
        best = None      # (util, caster_pos, target)
        for caster_pos in (ctx.reach_nc or []):
            # Selector PAR POSITION : `fromHere` a l'origine (ordre natif exact), union ailleurs.
            targets = fromhere if (caster_pos == ctx.origin and fromhere) else union
            for tgt in targets:
                tpos = pos_by_id.get(tgt)
                if tpos is None or tpos == caster_pos:
                    continue
                u = self._utility(ctx, caster_pos, tpos, occ_by_pos)
                if best is None or u > best[0]:     # strict `>` : 1re paire du max gagne
                    best = (u, caster_pos, tgt)
        if best is None or best[0] < min_u:
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] UnstoppableMomentum best={best} min={min_u} "
                      f"-> aucun candidat", file=sys.stderr)
            return []
        util, caster_pos, tgt = best
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] UnstoppableMomentum tgt={tgt} to={caster_pos} "
                  f"util={util} min={min_u}", file=sys.stderr)
        return [{"target": tgt, "ability": self.ABILITY_ID,
                 "to": (caster_pos if caster_pos != ctx.origin else None), "pred": util}]
