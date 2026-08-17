"""Résurrection d'unité — `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (mutateur ECS IMPÉRATIF).

Frontière DSL : la feuille `IdunBattleLogic.Entities.DSLBehaviors$$Resurrect` (au-dessus, structurelle) APPELLE cette
Operation (en-dessous, impératif). Chaîne native : `IdunBattle.Entities.Behaviours.ResurrectBehaviour$$Execute` (zip units×tiles)
→ `ResurrectUnitMessage` → `Core.Services.OperationProcessor$$ResurrectUnit` → `IdunBattle.Operations.ResurrectUnitOperation$$Execute`. Ici on porte la MUTATION observable (le pipeline de file/stream = couche view non suivie) :

  * gardes `IsDefeated(unit)` (une unité vivante n'est pas ressuscitée) ;
  * gate `battleQuery.<slot 0x31>` = `IdunBattle.Core.Services.BattleQuery$$CanBeResurrected(unit,
    healType)` — AJOUTÉ par #564 (mirror : `abilities/attack_query.can_be_resurrected`). Il était
    ABSENT, et c'est le même mode de panne que #520 côté heal : l'Operation mutait sans consulter le
    gate, donc une cible `UnitFlag.PreventResurrect`, `UnitTrait.PermaDeath` ou du MAUVAIS
    `HealType` (mécanique sous un resurrect non-mécanique) revenait à la vie là où le natif
    l'écarte, en rendant un résultat d'apparence normale ;
  * repositionne l'unité sur la tuile du decoy ;
  * `IdunBattle.Operations.ResurrectUnitOperation$$KillSteppableUnits` : le decoy sur lequel on réapparaît est CRUSHÉ (`_kill_steppable_units`,
    G1) — c'est ce decoy MORT co-localisé qui alimente `DecoysAndMisdirection_BuffFriends` (G2, +582 + decoy) ;
  * flags natifs `Remove(6,0xf,8,0x1a,9)` puis `Add(2=alive, 0xe=UnitPostAbility)` → on pose `alive=True`
    + le flag one-shot `AMBUSH_CONSUMED (0xe)` (re-mourir ne re-ressuscite PAS) ;
  * `IdunBattle.Operations.ResurrectUnitOperation$$SetHealth` = PV pleins (le `StatAmount(unit, Health=5, mode=2)` passé par le behaviour) ;
  * si `takesImmediateTurn (param_7)` → `RemoveTurnFlags(unit,1,1)` → l'unité peut REJOUER immédiatement
    (l'exécution du tour = couche IA/contrôleur, pas cette Operation) ;
  * SINON (`param_7 == 0`) → `processor.<slot 0x23>(unit, 1)` =
    `IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute(unit, reverse: false)` —
    l'autre moitié du même `if`, AJOUTÉE par #564. C'est littéralement le « and are unable to act on
    this turn » de l'i2 de `1039 RitesOfRestoration`, le SEUL call-site porté qui prenne cette
    branche (l'Ambush de `genestealer.py` passe `takesImmediateTurn = true`) ;
  * émet `On(UnitResurrected=0x2e=46)` → `unit_resurrected_triggers` → alimente G2 `BuffFriends` + G5 ré-arme.

⚠ NE PAS confondre avec la couche DÉCISION `RitesOfRestorationPlaybook` (`playbook/noncomparable/heals.py`,
`GetPossibleResurrectTargets`) qui SCORE l'évaluation IA — le runner n'avait PAS d'Operation resurrect ;
c'est un AJOUT net (piège check-own-port).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (UnitComponent, PositionComponent, HealthComponent, UnitFlagsComponent,
                          PersistentDataComponent, StatsComponent, TriggeredAbilityComponent,
                          get_feet_count, get_unit_feet)
from ...entities.traits.unit_trait import UnitTrait, has_trait
from ...entities.unit_flag import UnitFlag
from .triggers.dispatch.move_death import unit_resurrected_triggers
from ..abilities.loki.swarm import on_group_unit_hp_changed
# #564-r3 : les DEUX gates de tuile de `ResurrectUnitOperation` sont les MEMES primitives natives
# que les gates amont de `MoveUnitOperation` (#448-r1-r1-r2-r2-r1) -- `BattleQuery` slot 0xa1
# (`IsWalkableTile`) et slot 0xa5 (`IsTileReservedForAnotherUnit`). On REUTILISE leur foyer porte
# plutot que d'en ecrire un second, ce qui garantit qu'une correction de polarite profite aux deux.
from .movement import _kill_steppable_units, _tiles_are_walkable
from .tile_reservation import is_tile_reserved_for_another_unit
from ..abilities.attack_query import can_be_resurrected


def update_flags_on_resurrect(fl: UnitFlagsComponent) -> None:
    """`IdunBattle.Operations.ResurrectUnitOperation$$UpdateFlags` -- la RAFALE de retraits, relue
    VERBATIM au build `rnca9r7q6c` (#462-r4e-o-r2-r1) :

        Remove(6) ; Remove(0xf) ; Remove(8) ; Remove(0x1a) ; Remove(9) ; Add(2) ; Add(0xe)

    Le port n'en portait qu'UN (`Remove(0x1a)`), et l'omission de `Remove(8)` est LOAD-BEARING :
    `UnitFlag.Overkilled` est le gate du SITE (A) d'
    `IdunBattle.Operations.ApplyDamageOperation$$Execute` (porte dans `damage.py`, qui sort en tete
    quand le flag est pose). Une unite RESSUSCITEE apres avoir ete overkillee restait donc
    INFRAPPABLE cote port : l'attaque suivante n'emettait AUCUN evenement la ou le natif les emet
    tous. MESURE (#462-r4e-o-r2-r1, montage Ambush) : port `[]` vs natif pleine cardinalite.

    Fonction de MODULE, sans etat, pour la meme raison que `damage_hits.overkill_hit_emits` :
    c'est le point de MUTATION des contre-epreuves.

    ⚠ **`Add(2 = UnitFlag.ActiveAbilityUsed)` EST PORTE depuis #564-r4, et le decompile TRANCHE la
    question que le residu laissait ouverte.** Le doute etait « le poser inconditionnellement
    contredirait le tour immediat » : il ne le contredit pas, parce que le natif le pose AVANT le
    bras `options` et que le bras `options != 0` (`takesImmediateTurn`) appelle ENSUITE
    `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`, qui retire TOUJOURS
    `{ActiveAbilityUsed(2), TurnFinished(3), TurnTerminated(27)}` (les trois `Remove` places hors
    de ses deux gates). L'inconditionnel du natif est donc DEJA la forme correcte pour les deux
    bras -- c'est le retrait qui est conditionnel, pas la pose.
    MESURE live (#564-r1-r2, `probe_564r1r2_soin_et_no_action.py`, cast de `1039` sur un tour non
    cloture) : flags natifs du ressuscite = `[ActiveAbilityUsed, ArrivedAtFinalTile, Moved,
    NoActionAvailable, Resurrected, TurnFinished, TurnTerminated]`, port = les memes MOINS
    `ActiveAbilityUsed` et `TurnTerminated`.

    `Add(0xe)` reste chez l'appelant : c'est lui qui porte le sens « one-shot »."""
    for f in (UnitFlagsComponent.DEAD,          # Remove(6)    -- UnitFlag.Dead
              UnitFlag.Downed,                  # Remove(0xf)  -- UnitFlag.Downed (aucun poseur porte)
              UnitFlagsComponent.OVERKILLED,    # Remove(8)    -- UnitFlag.Overkilled
              UnitFlagsComponent.REMOVED,       # Remove(0x1a) -- UnitFlag.Removed
              UnitFlagsComponent.FLED):         # Remove(9)    -- UnitFlag.Fled (pose par `behaviour.py`)
        fl.remove(f)
    fl.add(UnitFlagsComponent.ACTIVE_ABILITY_USED)   # Add(2) -- UnitFlag.ActiveAbilityUsed


def tiles_are_occupied(state: State, feet_tiles: list) -> bool:
    """`IdunBattle.Operations.ResurrectUnitOperation$$TilesAreOccupied(feetTiles)` (#564-r3).

    ⚠ **IL REFUSE QUAND IL REND VRAI** -- polarite INVERSE de son voisin immediat
    `TilesAreWalkable`, qui refuse quand il rend FAUX. Les deux se suivent dans `Execute` :

        if ( TilesAreOccupied(tiles))          return;      // <- VRAI = refus
        if (!TilesAreWalkable(unit, tiles))    return;      // <- FAUX = refus

    Corps natif :

        foreach (var tile in feetTiles)
            if (!TileExtensions.IsFreeTile(tile, state, allowSteppable: 1,
                                           allowTemporaryTile: 0, allowAnyUnit: 0))
                { log; return true; }
        return false;

    `allowSteppable: 1` est LU aux octets du call-site (le 3e argument porte `1`), pas suppose --
    et il est LOAD-BEARING ici : c'est ce qui laisse la resurrection reapparaitre SUR un decoy
    `Steppable`, que `KillSteppableUnits` ecrasera juste apres. Avec `allowSteppable: 0` le gate
    refuserait le cas NOMINAL de `1039` chaque fois que la tuile choisie porte un decoy.

    Branche `allowAnyUnit == 0` d'`IdunBattle.Entities.TileExtensions$$IsFreeTile` :
    `content.IsEmpty() || GetUnit(t).HasTrait(0x1b = Steppable)`. L'occupation est celle de la
    TUILE, jamais les PV de l'occupant (#462-r4b-...-r5) -> le critere est `UnitComponent.alive`,
    et un CADAVRE n'occupe rien (`KillUnitOperation` -> `RemoveUnitFromTiles` vide le
    `TileContentComponent`).

    Pas de board -> `False` (PERMISSIF) : on ne refuse pas faute de substrat, meme parti que
    `_tiles_are_walkable`."""
    if not feet_tiles:
        return False
    board = getattr(state, "board", None)
    if board is None:
        return False
    wanted = {(int(t[0]), int(t[1])) for t in feet_tiles if t is not None}
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or not uc.alive:
            continue
        # `allowSteppable: 1` : un occupant `Steppable` ne rend PAS la tuile occupee. Meme lecture
        # du substrat de traits que `_kill_steppable_units` (`StatsComponent.ctx.traits`), et meme
        # degradation VOULUE : un `StatsComponent` absent rend un substrat VIDE, donc « pas
        # Steppable », donc la tuile compte comme occupee.
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_trait(traits or [], UnitTrait.Steppable):
            continue
        for foot in get_unit_feet(state, uid):
            if (int(foot[0]), int(foot[1])) in wanted:
                return True                       # une tuile n'est pas libre -> REFUS
    return False


def feet_count_matches_tiles(state: State, unit_id: int, feet_tiles: list) -> bool:
    """L'empreinte MULTI-HEX -- `if (GetFeetCount(unit) != unitFeetTiles.Count) { log; return; }`
    (#564-r3). Rendu ici en polarite POSITIVE (`True` = on continue), pour ne pas ajouter une
    troisieme convention a deux voisins qui en ont deja deux.

    `IdunBattle.Entities.UnitExtensions$$GetFeetCount` = `GetUnitFeetIds(unit, state).Count`, c'est
    a dire le nombre de PIEDS de l'unite -- pas le nombre de tuiles occupees. Un cadavre les garde
    (c'est `ResetFeet`, APRES ce gate, qui detache leur `TileId`), donc le gate PASSE sur le cas
    nominal mono-hex : `1 != 1` est faux."""
    return int(get_feet_count(state, int(unit_id))) == len(feet_tiles or [])


def reset_persistent_data(state: State, unit_id: int) -> int:
    """`IdunBattle.Operations.ResurrectUnitOperation$$ResetPersistentData` (#564-r3) : DEUX
    `ClearAllPersistentData`, sur DEUX composants distincts de la meme unite --

        unit.GetComponent(PersistentDataComponent).ClearAllPersistentData();
        unit.GetComponent(TriggeredAbilityComponent).ClearAllPersistentData();

    L'unite revient donc SANS son sac de donnees persistantes NI ses compteurs de phase-triggers :
    un `LetTheGalaxyBurn` arme, un compteur de declenchements a son plafond, ne survivent pas a la
    resurrection. Rend le nombre d'entrees effacees (0 = rien a effacer, pas une erreur)."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return 0
    n = 0
    pdc = e.get_component(PersistentDataComponent)
    if pdc is not None and getattr(pdc, "data", None):
        n += len(pdc.data)
        pdc.data.clear()
    tac = e.get_component(TriggeredAbilityComponent)
    entries = getattr(tac, "entries", None) if tac is not None else None
    if entries:
        n += len(entries)
        entries.clear()
    return n


class ResurrectUnitOperation:
    """Mirror `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (mutateur ECS). `dest_coord` = (col,row) de la
    tuile du decoy ; `hp` = PV à restaurer (PV pleins) ; `immediate_turn` = tour immédiat après résurrection."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, dest_coord, hp,
                *, immediate_turn: bool, heal_type: int = 0) -> Optional[dict]:
        e = state.get_entity(unit_id)
        if e is None:
            return None
        uc = e.get_component(UnitComponent)
        if uc is None or uc.alive:            # IsDefeated : une unité vivante n'est pas ressuscitée
            return None
        # GATE `battleQuery.<slot 0x31>` = `IdunBattle.Core.Services.BattleQuery$$CanBeResurrected`,
        # le 2e test du natif, juste apres `IsDefeated`. Le natif sort ICI sur un `OperationResult`
        # d'erreur : aucune mutation, aucun flag, aucun `On(UnitResurrected)`.
        # `heal_type` = le `HealType` que le behaviour appelant a LU au decompile
        # (`RitesOfRestorationAbility$$ExecuteBehaviour` -> 0 ; `ResurrectionOrbAbility$$
        # GetResurrectBehaviour` -> 1). Le defaut `0` reprend la valeur de l'unique call-site
        # anterieur (Ambush) -- cf. `triggers/genestealer.py`, ou il est passe EXPLICITEMENT.
        if not can_be_resurrected(state, int(unit_id), int(heal_type)):
            return None
        # ── #564-r3 : les QUATRE gates de tuile, au RANG NATIF (entre `CanBeResurrected` et la
        # premiere mutation), et avec leurs polarites LUES une par une -- deux refusent quand ils
        # rendent VRAI, un quand il rend FAUX, et le quatrieme est rendu en positif :
        #
        #     if ( TilesAreOccupied(tiles))                        return;
        #     if (!TilesAreWalkable(unit, tiles))                  return;
        #     if ( GetFeetCount(unit) != tiles.Count)              return;
        #     if (!battleQuery.<0xa5>(tiles, unit))  <- LOG, puis la MUTATION continue
        #
        # ⚠ Le QUATRIEME est le piege : `IsTileReservedForAnotherUnit` REFUSE quand il rend VRAI
        # (le natif n'entre dans son bloc de mutation que sur la branche `cVar2 == 0`), comme le
        # gate G6 de `MoveUnitOperation` -- et NON l'inverse, malgre l'apparence du decompile.
        #
        # `feet_tiles` = l'empreinte de destination. Le call-site porte n'en fournit qu'UNE (le
        # zip `targets x tiles` de `ResurrectBehaviour` passe une tuile par cible) -> mono-hex.
        #
        # ⚠ `dest_coord is None` N'EST PAS une empreinte VIDE, et la distinction est DELIBEREE --
        # meme forme que le `()` vs `None` du lift-off de `MoveUnitOperation` (#448-r1-r1-r2-r2-r1).
        # AUCUN call-site NATIF ne passe une empreinte vide : `ResurrectBehaviour` zippe
        # `targets x tiles` et l'Ambush genestealer passe `Tiles(decoy)`. `None` est donc un regime
        # PROPRE AU PORT (les bancs qui ne mesurent que les PV, ex. la purge d'`over_reduce`
        # #462-r4e-o-r2), ou il n'y a AUCUNE tuile a valider et ou le port ne repositionne rien.
        # Les gates y sont NON APPLICABLES -- et non « passes ». S'ils y etaient armes,
        # `GetFeetCount(unit) != 0` refuserait tout, ce qui inventerait un refus sur un regime que
        # le natif n'a pas.
        gates = None
        if dest_coord is not None:
            feet_tiles = [(int(dest_coord[0]), int(dest_coord[1]))]
            gates = {"tiles_occupied": tiles_are_occupied(state, feet_tiles),
                     "tiles_walkable": _tiles_are_walkable(state, feet_tiles),
                     "feet_count_ok": feet_count_matches_tiles(state, int(unit_id), feet_tiles),
                     "reserved_for_another": is_tile_reserved_for_another_unit(
                         state, feet_tiles, int(unit_id))}
            if gates["tiles_occupied"] or not gates["tiles_walkable"] \
                    or not gates["feet_count_ok"] or gates["reserved_for_another"]:
                return None
        # repositionne sur la tuile du decoy
        #
        # ⚠ CE REPOSITIONNEMENT COLLAPSE TROIS ETAPES NATIVES, et c'est le RESIDU MULTI-HEX de
        # #564-r3 : `ResetPreviousTileIfStillOwned(unit, GetUnitFeet(unit).Select(f => f.Tile))`
        # (libere l'ancienne empreinte), `ResetFeet(unit)` (`foot.<+0x14> = 0` sur CHAQUE pied),
        # puis `processor.<slot 0x7e>(unit, unitFeetTiles)` (repose l'unite sur la NOUVELLE
        # empreinte). Le port n'ecrit qu'une `PositionComponent`, donc pour une unite MULTI-HEX
        # ses pieds resteraient sur l'ancienne empreinte. Le fermer exige que la feuille DSL
        # `Resurrect` transmette la LISTE de tuiles au lieu d'une seule -- foyer
        # `runner/abilities/behaviours/lifecycle.py`, hors de ce module.
        if dest_coord is not None:
            pc = e.get_component(PositionComponent)
            if pc is not None:
                pc.col, pc.row = int(dest_coord[0]), int(dest_coord[1])
        # `IdunBattle.Operations.ResurrectUnitOperation$$ResetPersistentData` (#564-r3) -- AVANT
        # `SetHealth`, comme le natif : l'unite revient sans son sac de donnees persistantes ni ses
        # compteurs de phase-triggers.
        persistent_cleared = reset_persistent_data(state, int(unit_id))
        # ── LA FENETRE D'INTOUCHABILITE DE LA RESURRECTION (#433-r3-r2-r1-r1) ────────────────────
        # `IdunBattle.Operations.ResurrectUnitOperation$$Execute` encadre son propre corps d'un
        # `UnitFlagsComponent$$Add(0x11)` ... `$$Remove(0x11)`, HORS de tout effet. Lu verbatim sur
        # `t6dpr4k06g`, entre les deux :
        #     SetHealth(unit, health)
        #     flags.Add(0x11)                                   <- POSE
        #     KillSteppableUnits(this, unit, tilesResolved)
        #     if (options) UnitFlagsComponent.RemoveTurnFlags(flags, 1)
        #     SendStreamEvents(this, unit, unitFeetTiles, abilityType)
        #     flags.Remove(0x11)                                <- RETRAIT
        #     ... On(0x2e = UnitResurrected), FinishUnitTurn, ...
        # **L'unite ressuscitee n'est donc PAS ciblable pendant les triggers de sa propre
        # resurrection.** Ce n'est pas une fenetre morte : `KillSteppableUnits` passe par
        # `KillUnitOperation$$Execute` en entier -- cinq evenements de mort, trois `RemoveEffects` --
        # donc du code de jeu s'execute dedans et peut enumerer des cibles.
        # Le RETRAIT est place AVANT `unit_resurrected_triggers` (`On(0x2e)`), comme le natif :
        # l'unite est deja ciblable quand ce vecteur-la part.
        # ⚠ ECART D'ORDRE PREEXISTANT, non introduit ici : le port joue `_kill_steppable_units`
        # AVANT `SetHealth`, le natif APRES. La fenetre ci-dessous couvre donc AUSSI le `fill_up`
        # et `on_group_unit_hp_changed` -- un sur-ensemble, dans le sens RESTRICTIF.
        # ⚠ `try/finally` : sans lui, un `return` ou une exception entre les deux laisserait
        # l'unite non ciblable POUR LE RESTE DE LA BATAILLE (le flag ne part que par ce retrait) --
        # exactement le mode de defaillance que #1074 a nomme pour `JustSummonedEffect`.
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        no_action = None
        finish_turn = None
        crushed = []
        fl.add(UnitFlagsComponent.UNTARGETABLE)                 # `flags.Add(0x11)`
        try:
            # IdunBattle.Operations.ResurrectUnitOperation$$KillSteppableUnits : crushe le decoy de la tuile d'arrivée (mover = l'unité ressuscitée,
            # non tuée elle-même). Le decoy MORT co-localisé -> source de G2 BuffFriends.
            if dest_coord is not None:
                crushed = _kill_steppable_units(state, (int(dest_coord[0]), int(dest_coord[1])),
                                                unit_id)
            # revive : alive + PV pleins + flag one-shot 0xe (Ambush consommé)
            uc.alive = True
            hc = e.get_component(HealthComponent)
            if hc is not None and hp is not None:
                # `IdunBattle.Operations.ResurrectUnitOperation$$SetHealth` -> la mutation PV est un
                # `IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` (RELATIF : `current +=
                # Min(amount, max - current)`), pas une ecriture absolue. Sur une unite morte `current`
                # vaut 0, donc les deux formes coincident -- mais seul `FillUp` purge l'accumulateur de
                # sur-reduction `+0x24` en queue (#462-r4e-o-r2), ce qui EMPECHE qu'une unite
                # RESSUSCITEE herite du compteur de sa vie precedente et soit marquee `UnitFlag.Overkilled`
                # des son premier coup recu. Foyer unique : `HealthComponent.fill_up`.
                # (Le REVIVE, lui, ne purge rien : quirk natif mirrore dans `revive.py`.)
                hc.fill_up(int(hp))
                # #60 : bras `On(UnitRevived=45) & OwnerIsTarget` du `SwarmAbility.CreateTrigger
                # IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` — re-evalue le stat-mod EXTRA_HITS du trait Swarm au retour a la vie.
                on_group_unit_hp_changed(state, unit_id)
            # `IdunBattle.Operations.ResurrectUnitOperation$$UpdateFlags` — rafale de RETRAITS complete
            # (foyer/point de mutation : `update_flags_on_resurrect`, cf. sa docstring).
            update_flags_on_resurrect(fl)
            fl.add(UnitFlagsComponent.AMBUSH_CONSUMED)      # Add(0xe) — one-shot
            # tour immédiat : RemoveTurnFlags(1,1) -> l'unité redevient actionnable (retire NoAction +
            # turn-flags, dont l'`ActiveAbilityUsed` que `update_flags_on_resurrect` vient de poser).
            # RANG NATIF : ce `RemoveTurnFlags` est DANS la fenetre d'intouchabilite (cf. le bloc
            # de commentaire ci-dessus), le vecteur `On(0x2e)` en dehors.
            if immediate_turn:
                fl.remove_turn_flags(include_no_action=True, new_activation=True)
        finally:
            fl.remove(UnitFlagsComponent.UNTARGETABLE)          # `flags.Remove(0x11)`
        # émet On(UnitResurrected=46) -> G2 BuffFriends (+582 + decoy si GS Cult) + G5 ré-arme HeroicFusillade
        downstream = unit_resurrected_triggers(state, unit_id)
        if not immediate_turn:
            # #564-r4 -- L'AUTRE BRAS DU MEME `if`, ET LE SLOT AVAIT ETE MAL RESOLU.
            # `if (!options) processor.<slot 0x23>(unit, 1)` : le slot `0x23` vaut **35 =
            # `FinishUnitTurn`** (2 parametres : unit, isTerminated), LU dans
            # `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv` -- et NON
            # `MarkUnitAsNoActionAvailable`, qui est le slot **118 = 0x76**. C'est cette confusion
            # qui laissait `UnitFlag.TurnTerminated` (27) sans poseur identifie.
            #
            # `IdunBattle.Operations.FinishUnitTurnOperation$$Execute(unit, isTerminated: true)`
            # pose, dans cet ordre : `Add(27 TurnTerminated)` (sous le gate `isTerminated`),
            # `Add(1 ArrivedAtFinalTile)`, `Add(3 TurnFinished)`, puis -- DERNIERE instruction,
            # inconditionnelle -- le slot 0x76 `MarkUnitAsNoActionAvailable`. Le
            # `UnitFlag.NoActionAvailable` mesure par #564-r1-r2 arrive donc bien par ce chemin :
            # le verdict live etait juste, seul son ETAGE etait mal nomme.
            #
            # ⚠ L'ORDRE N'EST PLUS INOBSERVABLE, et c'est pourquoi l'appel a DESCENDU sous
            # `unit_resurrected_triggers`. L'ancien appel ne posait qu'un flag muet ; celui-ci
            # PUBLIE (`On(0x28 = UnitFinishedTurn)`, et le step `Events`). Le natif l'emet APRES
            # `On(0x2e = UnitResurrected)` -- ordre du decompile, desormais reproduit.
            from .turnflow import FinishUnitTurnOperation
            finish_turn = FinishUnitTurnOperation.execute(state, int(unit_id), forced=True)
            no_action = finish_turn.get("no_action")
        return {"resurrected": int(unit_id), "tile": (int(dest_coord[0]), int(dest_coord[1])) if dest_coord else None,
                "hp": int(hp) if hp is not None else None, "crushed_decoy": crushed,
                "immediate_turn": bool(immediate_turn), "no_action": no_action,
                "finish_turn": finish_turn,
                "heal_type": int(heal_type), "downstream": downstream,
                # #564-r3 : les gates de tuile evalues (None = `dest_coord is None`, regime propre
                # au port ou ils sont NON APPLICABLES) et le compte d'entrees persistantes purgees.
                "tile_gates": gates, "persistent_cleared": persistent_cleared}
