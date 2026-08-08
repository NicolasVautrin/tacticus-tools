"""Résurrection d'unité — `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (mutateur ECS IMPÉRATIF).

Frontière DSL : la feuille `IdunBattleLogic.Entities.DSLFactory$$Resurrect` (au-dessus, structurelle) APPELLE cette
Operation (en-dessous, impératif). Chaîne native : `IdunBattle.Entities.Behaviours.ResurrectBehaviour$$Execute` (zip units×tiles)
→ `ResurrectUnitMessage` → `Core.Services.OperationProcessor$$ResurrectUnit` → `IdunBattle.Operations.ResurrectUnitOperation$$Execute`. Ici on porte la MUTATION observable (le pipeline de file/stream = couche view non suivie) :

  * gardes `IsDefeated(unit)` (une unité vivante n'est pas ressuscitée) ;
  * gate `battleQuery.<slot 0x31>` = `IdunBattle.Core.Services.BattleQuery$$CanBeResurrected(unit,
    healType)` — AJOUTÉ par #855 (mirror : `abilities/attack_query.can_be_resurrected`). Il était
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
    l'autre moitié du même `if`, AJOUTÉE par #855. C'est littéralement le « and are unable to act on
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
from ..components import (UnitComponent, PositionComponent, HealthComponent, UnitFlagsComponent)
from ...entities.unit_flag import UnitFlag
from .triggers.dispatch.move_death import unit_resurrected_triggers
from ..abilities.loki.swarm import on_group_unit_hp_changed
from .movement import _kill_steppable_units


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

    ⚠ `Add(2 = UnitFlag.ActiveAbilityUsed)` du natif reste NON PORTE : aucune mesure ne l'exerce ici
    (il gouverne la face DECISION -- `HasOwnersActiveAbilityBeenUsed` --, pas la cardinalite d'une
    attaque), et le poser sans confrontation contredirait le tour immediat que `immediate_turn`
    vient d'ouvrir. Residu nomme dans `docs/rl/case-462-r4e-o-amount-borne-aux-pv.md` SS 8.
    `Add(0xe)` reste chez l'appelant : c'est lui qui porte le sens « one-shot »."""
    for f in (UnitFlagsComponent.DEAD,          # Remove(6)    -- UnitFlag.Dead
              UnitFlag.Downed,                  # Remove(0xf)  -- UnitFlag.Downed (aucun poseur porte)
              UnitFlagsComponent.OVERKILLED,    # Remove(8)    -- UnitFlag.Overkilled
              UnitFlagsComponent.REMOVED,       # Remove(0x1a) -- UnitFlag.Removed
              UnitFlagsComponent.FLED):         # Remove(9)    -- UnitFlag.Fled (pose par `behaviour.py`)
        fl.remove(f)


class ResurrectUnitOperation:
    """Mirror `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (mutateur ECS). `dest_coord` = (col,row) de la
    tuile du decoy ; `hp` = PV à restaurer (PV pleins) ; `immediate_turn` = tour immédiat après résurrection."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, dest_coord, hp,
                *, immediate_turn: bool, heal_type: int = 0) -> Optional[dict]:
        from ..abilities.attack_query import can_be_resurrected
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
        # repositionne sur la tuile du decoy
        if dest_coord is not None:
            pc = e.get_component(PositionComponent)
            if pc is not None:
                pc.col, pc.row = int(dest_coord[0]), int(dest_coord[1])
        # IdunBattle.Operations.ResurrectUnitOperation$$KillSteppableUnits : crushe le decoy de la tuile d'arrivée (mover = l'unité ressuscitée,
        # non tuée elle-même). Le decoy MORT co-localisé -> source de G2 BuffFriends.
        crushed = []
        if dest_coord is not None:
            crushed = _kill_steppable_units(state, (int(dest_coord[0]), int(dest_coord[1])), unit_id)
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
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        # `IdunBattle.Operations.ResurrectUnitOperation$$UpdateFlags` — rafale de RETRAITS complete
        # (foyer/point de mutation : `update_flags_on_resurrect`, cf. sa docstring).
        update_flags_on_resurrect(fl)
        fl.add(UnitFlagsComponent.AMBUSH_CONSUMED)      # Add(0xe) — one-shot
        # tour immédiat : RemoveTurnFlags(1,1) -> l'unité redevient actionnable (retire NoAction + turn-flags)
        no_action = None
        if immediate_turn:
            fl.remove_turn_flags(include_no_action=True, new_activation=True)
        else:
            # `if (!options) processor.<slot 0x23>(unit, 1)` -- l'AUTRE bras du meme `if`, place par
            # le natif APRES l'emission d'`On(UnitResurrected)`. Le port l'appelle ici, avant le
            # dispatch : `MarkUnitAsNoActionAvailableOperation` ne pose qu'un flag et n'emet aucun
            # evenement, donc l'ordre est inobservable -- et le faire AVANT garantit qu'un trigger
            # aval voit deja l'unite hors-jeu pour ce tour.
            from .turnflow import MarkUnitAsNoActionAvailableOperation
            no_action = MarkUnitAsNoActionAvailableOperation.execute(state, int(unit_id))
        # émet On(UnitResurrected=46) -> G2 BuffFriends (+582 + decoy si GS Cult) + G5 ré-arme HeroicFusillade
        downstream = unit_resurrected_triggers(state, unit_id)
        return {"resurrected": int(unit_id), "tile": (int(dest_coord[0]), int(dest_coord[1])) if dest_coord else None,
                "hp": int(hp) if hp is not None else None, "crushed_decoy": crushed,
                "immediate_turn": bool(immediate_turn), "no_action": no_action,
                "heal_type": int(heal_type), "downstream": downstream}
