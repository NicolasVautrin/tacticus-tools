"""WaaaghPlaybook (1058, `orksWarboss` « Snotflogga ») -- face DECISION (#971).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`
(`IdunBattle.AI.Playbook.Loki.WaaaghPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1`),
pas deduite du ctor : Ghidra etiquette le corps gshared `ComparablePlaybook<...>$$.ctor` pour les
DEUX hierarchies. A ne pas confondre avec `DaGreatWaaaghPlaybook` (1084), une AUTRE classe.

REACHABILITE : `data/symbols/<build>/metadata/active_playbook_builders.tsv` ->
`active 1058 IdunBattle.AI.Playbook.Loki.WaaaghPlaybook`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.WaaaghPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics>+0x00))     # `.cctor` : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                 casterPosition.get_MainTile()):
        nBuffed  = GetNumExistingUnitsBuffed(caster)                  # cf. plus bas
        nSummons = GetNumSummons(caster, casterPosition)              # cf. plus bas
        u        = Fix64.op_Implicit(nSummons + nBuffed)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, u))

⚠ **LES DEUX TERMES SONT CALCULES DANS LA BOUCLE ET AUCUN NE LIT LA CIBLE.** L'utilite est donc
CONSTANTE sur les cibles d'une meme position ; `Bucket$$AddAction` ne remplacant que sur
`Fix64.op_GreaterThan` STRICT, c'est la PREMIERE cible enumeree par le selecteur qui gagne. La
cible n'est pas choisie par une utilite : elle est choisie par l'ORDRE du selecteur.

`IdunBattle.AI.Playbook.Loki.WaaaghPlaybook$$GetNumSummons(caster, casterPosition)` :

    n    = WaaaghAbility.GetNumSummons(this.ability@+0x68)     # GetNumberConstant(0x10)
    sel  = WaaaghAbility.GetPossibleSummonTiles(this.ability@+0x68)
    ae   = new AbilityEntities(caster, .., casterTile: casterPosition.get_MainTile(), ..)
    return Math.Min(n, <iface slot 2>(sel, ae))                # `SelectUnique...().Count`

`IdunBattle.AI.Playbook.Loki.WaaaghPlaybook$$GetNumExistingUnitsBuffed(unit)` :

    sel = WaaaghAbility.GetBuffedUnitsSelector(this.ability@+0x68)
    ae  = new AbilityEntities(unit, .., <TOUS les autres champs NULS>)
    return <iface slot 2>(sel, ae)

⚠ **LE PREMIER TERME EST POSITION-DEPENDANT, LE SECOND NON, ET LA DIFFERENCE EST LUE AU
CALL-SITE.** `GetNumSummons` construit son `AbilityEntities` avec `casterTile =
casterPosition.MainTile` -- la position CANDIDATE. `GetNumExistingUnitsBuffed`, lui, ne renseigne
QUE `+0x08 = Caster` : `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` descend alors
toute sa cascade (`CasterPosition@+0x48` nul, `CasterTile@+0x40` nul) jusqu'a
`EntityExtensions.GetTiles(entities.Caster, state)` = l'empreinte COURANTE, c'est-a-dire
l'ORIGINE. Ce terme est donc CONSTANT sur tout le sweep.

LES DEUX SELECTEURS SONT DEJA PORTES SUR LA FACE COMBAT, ET C'EST LE MEME ARTEFACT NATIF
-----------------------------------------------------------------------------------------
* `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleSummonTiles` =
  `CanAddUnit(AdjacentTiles(<DSLSelectors+0x50 = CasterTile>))`
  -> `engine/runner/abilities/orks.py::waaagh_spawn_tree` porte le MEME couple
  (`Spawn(CanAddUnit(AdjacentTiles(Caster())), ...)`).
* `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffedUnitsSelector` =
  `Unique( <+0x48 Caster>
           + AdjacentFriends(<+0x48 Caster>, unique: 1, 3)
           + UnitsFromFaction(Friends(<+0x48 Caster>, <+0x20 AllAliveUnits>, 3), 5 = Orks, 3) )`
  -> `engine/runner/abilities/orks.py::waaagh_buffed_units_selector`, VERBATIM le meme arbre. La
  face DECISION en compte le CARDINAL ; la face COMBAT y pose les trois buffs 1099/1100/1101.

Le port de DECISION ne peut pas evaluer ces arbres DSL (ils exigent un `State` runner, absent du
substrat `decisionView`) : il en mirrore le CARDINAL terme a terme, sur les canaux publies. Les
deux etages sont cites cote a cote pour que la divergence, si elle apparait, se localise.

`<DSLSelectors+0x50>` = `CasterTile` et `<+0x48>` = `Caster` : carte etablie par
`IdunBattleLogic.Entities.DSLTriggers$$get_CasterIsCasterTile` = `AreEqual(+0x48, +0x50)`
(cf. `engine/entities/selectors/accessors.py`), pas par un nom.

`nrOfSummons` = `AbilityConfiguration.GetNumberConstant(config, 0x10)` =
`AbilityConstantType.nrOfSummons` = 2 au gameconfig -- l'index est le MEME que celui deja lu par
`engine/runner/abilities/orks.py::CONST_NR_OF_SUMMONS`.

LE GATE `ShouldEvaluate`, ET IL N'EST PAS CONSTANT
---------------------------------------------------
`WaaaghPlaybook` **surcharge `GetUseProbability`** (le slot que `IdunBattle.AI.Playbook.
BasePlaybook$$ShouldEvaluate` invoque), et le corps est LU :

    IdunBattle.AI.Playbook.Loki.WaaaghPlaybook$$GetUseProbability(unit, actionTiles) :
        ts = UnitExtensions.GetStat(unit, 0xc = TurnsStarted)
        nB = GetNumExistingUnitsBuffed(unit)
        return Fix64.op_Implicit(nB * ts) * Fix64.FromIntFraction(5, 100)      # 0.05

et `BasePlaybook$$ShouldEvaluate` : `p >= 1 -> True` ; `p <= 0 -> False` ; sinon TIRAGE RNG.

Le port tranche les DEUX branches DETERMINISTES et ne devine pas la troisieme :
`p = 0.05 * ts * nB`. `nB >= 1` toujours (le `Caster` est un terme de l'union) et `ts >= 1`
pendant le tour de l'unite -> la branche `p <= 0` n'est atteignable qu'avec un canal MUET, ou le
port refuse de gater. La branche `p >= 1` (`ts * nB >= 20`) est EXACTE. Entre les deux, le port
rend `True` : c'est l'ecart « porte ALEATOIRE non modelisee » deja assume par le projet pour
`BlackRagePlaybook` (0.4) et `ItItchesPlaybook` (moteur deterministe, cf. §5 case-44). ⚠ Il est
ici bien plus MORDANT qu'ailleurs : sur un plateau ou le Warboss a 3 allies Orks, `p = 0.05*ts*4`
ne franchit 1 qu'au 5e tour -- le natif SAUTE l'ability la plupart du temps, le port la propose
toujours. Residu `#971-r2`.

VOIE D'ENUMERATION -- CIBLE UNITE (ENNEMI), CHARGE
---------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$.ctor` pose
`TargetMatchesDynamicRule | CasterHasNotMoved | TargetIsEnemy | AllowObscuredTargetByElevation |
AllowObscuredTargetByWalls | TargetIsNotAdjacent` (deja transcrit par
`engine/runner/abilities/orks.py::WaaaghAbility.TARGETING_OPTIONS`), et
`WaaaghAbility$$GetDynamicInvalidTargetReason` exige qu'il RESTE une tuile de charge atteignable
(`TargetIsInRange` sinon). L'ensemble des cibles est donc **PAR POSITION**, et le RPC
`abilityTargets` n'a de vue par-position que pour l'origine (`fromHere`). Pour les tuiles de move
on interroge `castFromTiles` (= `AttackQuery$$GetInvalidTargetReason` tuile par tuile, SANS
troncature) via le foyer unique `engine.ai.cast_positions.positions_castables` -- le meme foyer
que `_PlanTargetPlaybook.eligible_positions`, avec `ranked` VIDE puisque 1058 n'a pas de plan
d'attaque (`ABILITY_ATTACK_TYPE[Waaagh] = Others`). Seam absente -> ensemble vide -> l'ability ne
propose rien, plutot que de proposer un cast illegal.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.ai import cast_positions as CP        # FORME B (liaison de MODULE) : le foyer
#                                                   #350-r3a-r4 reste substituable par un
#                                                   patcheur. Meme ecriture qu'`_base`.
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effects.magnitude import ability_var

from ._base import NCContext, NonComparablePlaybook, _unit_cfg

#: `UnitsFromFaction(..., 5, 3)` -- `UnitFaction.Orks = 5`, que le natif convertit par
#: `System.Enum.ToString` en le `FactionId` gameconfig que le selecteur compare
#: (`UnitsFromFactionSelector$$Select` -> `UnitExtensions$$HasFaction(unit, factionId)`).
#: MEME litteral que `engine/runner/abilities/orks.py::WAAAGH_FACTION`, cote COMBAT.
WAAAGH_FACTION = "Orks"

#: `GetNumberConstant(0x10)` (`WaaaghAbility$$GetNumSummons`). Membre nomme, pas l'ordinal.
CONST_NR_OF_SUMMONS = AbilityConstantType.nrOfSummons

#: `Fix64.FromIntFraction(5, 100)` de `WaaaghPlaybook$$GetUseProbability`.
_USE_PROBABILITY_STEP = 0.05


class WaaaghPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.WaaaghPlaybook$$EvaluateNonComparable` (0x422 = 1058).

    Utilite = `GetNumExistingUnitsBuffed(caster)` (CONSTANTE, ancree sur l'ORIGINE)
    `+ min(nrOfSummons, |CanAddUnit(AdjacentTiles(<position candidate>))|)` (POSITION-dependant).
    Aucun terme ne lit la cible."""

    ABILITY_ID = int(ActiveAbilityType.Waaagh)   # 0x422 = 1058
    #: `WaaaghPlaybook$$.cctor` = `Fix64.op_Implicit(1)`. Gate d'`AddAction` INCLUSIF (`>=`,
    #: `FUN_18004ed00`), donc inerte : `nBuffed >= 1` (le `Caster` est un terme de l'union).
    MIN_UTILITY = 1.0
    #: 1058 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170 des 258 valeurs de l'enum)
    #: -> tier `AbilityPriority.Normal`. ⚠ `DaGreatWaaagh` (1084), elle, y est a -1000 : ce sont
    #: DEUX abilities et DEUX playbooks distincts.
    PRIORITY = 0

    # -- les deux termes de l'utilite ---------------------------------------------------------

    def _allies(self, ctx: NCContext) -> list[dict]:
        """Les unites AMIES vivantes du caster, self exclu -- le MEME predicat que celui dont
        `engine/ai/context.py` derive `ctx.fpos` (`u["ctrl"] and u["alive"] and u["pos"] and
        u["id"] != uid`). On repart de `ctx.units` et non de `fpos` parce que le terme « faction
        Orks » a besoin du `visualId`, que `fpos` (des positions) ne porte pas."""
        out = []
        for u in (ctx.units or []):
            if u.get("id") == ctx.uid or not u.get("ctrl") or not u.get("alive"):
                continue
            p = u.get("pos") or {}
            if p.get("col") is None:
                continue
            out.append(u)
        return out

    def num_existing_units_buffed(self, ctx: NCContext) -> int:
        """`WaaaghPlaybook$$GetNumExistingUnitsBuffed(unit)` = le CARDINAL de

            Unique( Caster + AdjacentFriends(Caster, 1, 3)
                           + UnitsFromFaction(Friends(Caster, AllAliveUnits, 3), Orks, 3) )

        evalue avec un `AbilityEntities` dont SEUL `+0x08 = Caster` est renseigne -> l'ancre
        geometrique d'`AdjacentFriends` est l'empreinte COURANTE du caster (`ctx.origin`), jamais
        la position candidate (cf. l'en-tete). Le terme est donc CONSTANT sur le sweep.

        `Unique` = dedup par ENTITE : un allie Ork adjacent n'est compte qu'une fois, et le caster
        (lui-meme Ork) ne se compte pas deux fois. D'ou l'union d'ensembles d'ids ci-dessous plutot
        qu'une somme.

        L'adjacence est `bq.is_adjacent` (liste de voisinage STOCKEE + porte `|dElev| < 2` =
        `IterateAdjacentTiles`), le foyer que le selecteur d'anneau du port consomme deja.

        La faction est le `FactionId` gameconfig, exactement ce que compare
        `IdunBattle.Entities.Selectors.UnitsFromFactionSelector$$Select` -- lu via `_unit_cfg`,
        le foyer de config du package.

        RESIDUS NOMMES : `AdjacentFriends`/`Friends` natifs testent `UnitExtensions.AreFriends`
        (meme equipe) la ou `ctx.units[].ctrl` designe le camp CONTROLE -- identique pendant le
        tour de l'IA, divergent sous controle mental ; et le natif compare des EMPREINTES la ou
        le port compare des tuiles principales."""
        n_caster = 1                                   # le terme `<+0x48 Caster>` de l'union
        if ctx.origin is None:
            return n_caster                            # ancre absente -> seul le caster est sur
        neigh = bq.neigh_map(ctx)
        ids: set = set()
        for u in self._allies(ctx):
            p = u.get("pos") or {}
            q = (p.get("col"), p.get("row"))
            adjacent = bq.is_adjacent(ctx.origin, q, ctx.elev_by_pos, neigh)
            ork = _unit_cfg(u.get("visualId")).get("FactionId") == WAAAGH_FACTION
            if adjacent or ork:
                ids.add(u.get("id"))
        return n_caster + len(ids)

    def num_summons(self, ctx: NCContext, tile: tuple, occupied: set) -> int:
        """`WaaaghPlaybook$$GetNumSummons(caster, casterPosition)` =
        `Math.Min( WaaaghAbility.GetNumSummons(), |CanAddUnit(AdjacentTiles(casterTile))| )`,
        avec `casterTile = casterPosition.MainTile` = la position CANDIDATE.

        `bq.adjacent_addable_count` EST la composition `CanAddUnit o AdjacentTiles` : voisinage
        STOCKE + `|dElev| < 2`, puis `can_add_unit` (walkable ET libre). Les deux etages sont ceux
        que la face COMBAT consomme deja (`orks.py::waaagh_spawn_tree`).

        OCCUPATION : le natif lit le plateau COURANT -- le sweep de positions est HYPOTHETIQUE, il
        ne deplace rien. La tuile d'ORIGINE du caster reste donc OCCUPEE meme quand on evalue une
        tuile de move, et c'est ce que `occupied` porte (meme construction que
        `bespoke.CultDemagoguePlaybook._free_tiles_around` et `master_of_the_tutelaries`)."""
        cap = ability_var(ActiveAbilityType(self.ABILITY_ID).name,
                          CONST_NR_OF_SUMMONS.name, is_constant=True)
        if cap is None:
            return 0                                   # config illisible -> borne INF assumee
        free = bq.adjacent_addable_count(tile, ctx.neigh_by_pos, ctx.walkable_by_pos,
                                         occupied, ctx.elev_by_pos)
        return min(int(cap), int(free))

    # -- gate amont ----------------------------------------------------------------------------

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`IPlaybook` slot 4 = `BasePlaybook$$ShouldEvaluate`, dont le slot 0x1f8
        `GetUseProbability` est SURCHARGE par `WaaaghPlaybook$$GetUseProbability` :
        `p = 0.05 * GetStat(unit, 0xc = TurnsStarted) * GetNumExistingUnitsBuffed(unit)`.

        `p >= 1` -> True (EXACT) ; `p <= 0` -> False (EXACT) ; entre les deux, tirage RNG que le
        moteur deterministe ne modelise pas -> True (ecart assume, residu `#971-r2`).

        `turnsStarted` non mesure (`ctx.scene` absente, uid hors tables) -> True : on ne gate pas
        a l'aveugle, meme regle que `_base._turns_started_gate`."""
        if ctx.scene is None:
            return True
        ts = ctx.scene.turns_started(ctx.uid)
        if ts is None:
            return True
        p = _USE_PROBABILITY_STEP * float(ts) * float(self.num_existing_units_buffed(ctx))
        return p > 0.0

    # -- sweep ---------------------------------------------------------------------------------

    def _target_order(self, ctx: NCContext) -> tuple[list, list]:
        """`(fromHere, union)` d'ids de cibles UNITE, dans l'ordre du RPC.

        `fromHere` = `GetValidTargets(caster, position COURANTE, 1058)` -> l'ORDRE EXACT du
        selecteur natif a l'origine ; `targets` = l'union sur toutes les tuiles de move, dont
        l'ordre n'est celui d'AUCUNE position. L'utilite ne departageant pas les cibles, cet ordre
        EST la decision."""
        if ctx.ability_targets is None:
            return [], []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        from_here: list = []
        union: list = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for key, out in (("fromHere", from_here), ("targets", union)):
                    for t in (a.get(key) or []):
                        tid = t.get("targetId")
                        if t.get("kind") == "unit" and tid is not None and tid not in out:
                            out.append(tid)
        return from_here, union

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Mirror du sweep natif : positions candidates (ORIGINE d'abord) x cibles eligibles DE
        CETTE POSITION, argmax STRICT.

        L'utilite ne dependant pas de la cible, seule la PREMIERE cible legale d'une position peut
        gagner a cette position (`AddAction` ne remplace que sur `>`), et seule une position
        STRICTEMENT meilleure fait bouger le caster."""
        from_here, union = self._target_order(ctx)
        if not from_here and not union:
            return []
        n_buffed = self.num_existing_units_buffed(ctx)          # CONSTANT (ancre = origine)
        # #969-r3 : PAR PIED (`TileContentComponent`) ; l'origine y entre (le caster n'a PAS bouge).
        occupied = bq.occupied_positions(ctx)
        legal: dict = {}                                        # tid -> positions castables
        best = None                                             # (cible, position, utilite)
        for T in (ctx.reach_nc or []):
            seq = from_here if (T == ctx.origin and from_here) else union
            u = float(n_buffed + self.num_summons(ctx, T, occupied))
            for tid in seq:
                if tid not in legal:
                    legal[tid] = CP.positions_castables(
                        {"ranked": []}, getattr(ctx, "cast_from_tiles", None),
                        ctx.uid, tid, self.ABILITY_ID, ctx.origin)
                if T not in legal[tid]:
                    continue
                if best is None or u > best[2]:                 # strict > : 1re paire du max gagne
                    best = (tid, T, u)
                break        # utilite constante sur les cibles -> les suivantes ne peuvent pas
                #              remplacer (`AddAction` est keep-first au tie)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        tid, T, u = best
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] Waaagh tgt=%s T=%s nBuffed=%s u=%s"
                  % (ctx.uid, tid, T, n_buffed, u), file=sys.stderr)
        return [{"target": tid, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": u}]
