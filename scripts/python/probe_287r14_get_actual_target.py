"""probe #287-r14 -- `TargetingQuery$$GetActualTarget` : le port recoit ce que l'APPELANT donne,
le natif RESOUT lui-meme.

LE FAIT NATIF (relu au decompile, build rnca9r7q6c)
--------------------------------------------------
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` ne passe JAMAIS son parametre
`target` a la suite. Il le TRANSFORME, et le fait AVANT ses deux gates (ordre lu, pas suppose) :

    ability     = AbilitiesDatabase.Get(abilityType);
    casterTiles = EntityExtensions.GetTiles(caster, state);
    finalTarget = IActiveAbility.GetActualTarget(ability, caster, target);   // slot IActiveAbility 16
    if (finalTarget == null) return;                                        // abandon SILENCIEUX
    if (IsDeadUnitAndNotAllowedByAbility(abilityType, finalTarget)) return;
    if (IsInvalidTarget(caster, casterTiles, finalTarget, ...)) return;
    ...
    GetAbilityEntities(this, caster, casterTiles, finalTarget, abilityType);   // +0x10 <- finalTarget

`IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget` recopie les 0x40 octets de SES
`TargetingOptions` (`this+0xb0`) et delegue au slot `ITargetingQuery` 6 =
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`, dont le corps est :

    if (options.isSelfCasting == 0) {                     // byte @options+0x00
        if (options.rules & 0x40)          return EntityExtensions.GetMainTile(target, state);
        if (options.rules & (1<<44))       return UnitExtensions.GetMachine(target, state);
        if (options.rules & (1<<46)) { u = UnitExtensions.GetUnit(target, state);
                                       return u != null ? u : GetMachine(target, state); }
        return UnitExtensions.GetUnit(target, state);
    }
    return caster;                                       // self-cast

Les deux slots sont LUS dans `data/symbols/rnca9r7q6c/metadata/interface_slots.tsv`
(`ITargetingQuery 6 GetActualTarget`, `IActiveAbility 16 GetActualTarget`), et la surcharge de
`GetUnit` retenue est celle que les DEUX call-sites de `GetActualTarget` visent (xrefs) : la
surcharge DOMAINE MIXTE (unite -> elle-meme ; tuile -> occupant via `TileContentComponent`, avec
RECURSION ; pied -> son unite ; sinon null).

CE QUE CE PROBE MESURE
----------------------
Le port a DEUX regimes d'appel qui coexistent, et le natif n'en connait qu'UN :

  * regime U -- `target_id` = id d'UNITE  (tous les tests live : `_ringed_cast.cast_and_confront`
    envoie `targetId: <unite>`, et le natif l'accepte PARCE QU'IL TRANSFORME) ;
  * regime T -- `target_id` = id de TUILE (la face DECISION portee : `abilityTargets` rend
    `kind: "tile"`, l'action porte le `tileEntityId`).

Etage [1] balaye TOUT `ABILITY_CLASSES` et joue les deux regimes sur un substrat FRAIS identique,
meme MT, puis compare une EMPREINTE D'ETAT (effets poses + PV + positions + morts) plus le
diagnostic rendu. Une ability dont les deux regimes DIVERGENT est dans le rayon : l'un des deux
est faux, et pour une ability `TargetIsTile` c'est le regime U (le natif pose sur la TUILE --
mesure live #287-r12 : `1018` inscrit `1022` dans `tileMeta.tiles[].effects`, `decisionView.
units[].effects` reste inchange).

⚠ L'empreinte porte sur l'ETAT, pas sur le retour : `1018` rendait un diagnostic IDENTIQUE dans
les deux regimes (`deferred_effect: 1022`) alors que l'effet atterrissait sur deux PORTEURS
differents. Un critere par le retour aurait rendu << rayon 0 >>.

Usage (depuis scripts/python, ASCII only, 100 % OFFLINE -- aucun runner, aucune session Frida) :
    python probe_287r14_get_actual_target.py                # etage 1 : le rayon
    python probe_287r14_get_actual_target.py --ability 1018 # une seule, verbeux
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.entities.active_ability_type import ActiveAbilityType      # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402
from engine.runner.components import (HealthComponent, PositionComponent,  # noqa: E402
                                      UnitComponent)
from probe_287r12_role_target_tuile import (POS_CIBLE, U_CASTER, U_CIBLE,   # noqa: E402
                                            _board, _montage, _tid, PORTEURS)

#: Porteur GENERIQUE du balayage -- le caster n'est pas le sujet : ce que la mesure delimite, c'est
#: ce que la RESOLUTION DE CIBLE change. Les cinq abilities deja instrumentees par #287-r12 gardent
#: leur vrai porteur (`PORTEURS`), les autres prennent celui-ci.
PORTEUR_GENERIQUE = "astraBullgryn"


def _montage_pour(aid: int, board):
    """Substrat FRAIS pour `aid` : son porteur RE-lu quand on le connait, sinon un porteur
    generique. Meme geometrie que #287-r12 (cible au centre, 2 ennemis + 1 allie adjacents)."""
    if aid in PORTEURS:
        return _montage(aid, board)
    from probe_287r12_role_target_tuile import _substrat
    voisins = [board.coord(t) for t in board.neighbours_native(_tid(*POS_CIBLE))]
    from probe_287r12_role_target_tuile import POS_CASTER, U_ADJ1, U_ADJ2, U_ALLIE
    return _substrat([(U_CASTER, PORTEUR_GENERIQUE, 1, POS_CASTER),
                      (U_CIBLE, "necroWarden", 2, POS_CIBLE),
                      (U_ADJ1, "necroDestroyer", 2, voisins[0]),
                      (U_ADJ2, "orksNob", 2, voisins[1]),
                      (U_ALLIE, "astraCreed", 1, voisins[2])], board)


def empreinte_etat(st) -> tuple:
    """Ce que le cast a FAIT, canonicalise : effets poses (PORTEUR, type, niveau), PV, positions,
    vivant/mort. C'est le canal par lequel un role `target` mal resolu se voit -- le DIAGNOSTIC
    rendu, lui, peut etre identique dans les deux regimes (mesure : `1018`)."""
    effets = []
    if st.effects is not None:
        for uid, effs in sorted(st.effects.by_unit.items()):
            for e in effs:
                effets.append((int(uid), int(e.effect_type), int(e.level or 0),
                               bool(e.consumed), bool(e.expired)))
    unites = []
    for eid, e in sorted(st.entities.items()):
        hc = e.get_component(HealthComponent)
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        unites.append((int(eid),
                       None if hc is None or hc.hp is None else int(hc.hp),
                       None if pc is None else (int(pc.col), int(pc.row)),
                       None if uc is None else bool(uc.alive)))
    return (tuple(sorted(effets)), tuple(unites))


def _norm_out(out):
    """Diagnostic canonique : la cle `target` porte l'ARGUMENT, qui differe par construction entre
    les deux regimes -- on la jette pour ne comparer que ce que l'ability a FAIT."""
    if out is None:
        return None
    return tuple(sorted((k, repr(v)) for k, v in out.items() if k != "target"))


def _joue(aid: int, cls, target_id: int, board, voie: str = "behaviour"):
    """`voie == "behaviour"` : `execute_behaviour(state, caster, target)` en direct -- ce que font
    les tests de migration et les probes. `voie == "handler"` : `AbilityHandler.
    visit_ActiveAbilityMessage`, c'est-a-dire le CHEMIN REEL du moteur, mirror d'
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` -- la ou la resolution de cible
    est posee (#287-r14). Les deux voies sont mesurees parce qu'elles ne couvrent pas le meme
    ensemble d'appelants."""
    st = _montage_pour(aid, board)
    if voie == "handler":
        from engine.runner.abilities.handler import AbilityHandler
        from engine.runner.messages import ActiveAbilityMessage
        h = AbilityHandler(st)
        h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
            caster_id=U_CASTER, target_id=int(target_id), ability_type=int(aid)))
        out = dict(h.last or {})
        # Le diagnostic du handler porte les cles de tour (`flags`) et l'ARGUMENT (`target`,
        # `actual_target`), qui different par construction entre les deux regimes -> on ne garde que
        # ce que l'ability a FAIT.
        for k in ("target", "actual_target", "caster", "ability_type"):
            out.pop(k, None)
        return _norm_out(out), empreinte_etat(st)
    out = cls().execute_behaviour(st, U_CASTER, target_id)
    return _norm_out(out), empreinte_etat(st)


def _categorie(cls) -> str:
    """Sous quelle BRANCHE de `TargetingQuery$$GetActualTarget` cette ability tombe-t-elle ?
    L'ordre est celui du decompile : self-cast, puis TargetIsTile, puis machine, puis actor, puis
    la branche par defaut `GetUnit`. `masque non lu` = `TARGETING_OPTIONS is None` (aucun gate, cf.
    la regle de non-regression du CLAUDE.md) -- le port n'a alors AUCUN moyen de resoudre."""
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    if opts is None:
        return "masque non lu"
    if getattr(opts, "self_cast", False):
        return "self-cast"
    r = int(opts.rules)
    if r & int(TR.TargetIsTile):
        return "TargetIsTile"
    if r & int(TR.TargetIsMachine):
        return "TargetIsMachine"
    if r & int(TR.TargetIsActor):
        return "TargetIsActor"
    return "GetUnit (defaut)"


def rayon(ability: int | None = None, verbeux: bool = False, voie: str = "behaviour") -> int:
    board = _board()
    tuile = _tid(*POS_CIBLE)
    cibles = {ability: ABILITY_CLASSES[ability]} if ability else dict(sorted(ABILITY_CLASSES.items()))
    divergentes, identiques, levees, inertes = [], [], [], []
    for aid, cls in cibles.items():
        cat = _categorie(cls)
        try:
            u_out, u_st = _joue(aid, cls, U_CIBLE, board, voie)
            t_out, t_st = _joue(aid, cls, tuile, board, voie)
        except Exception as exc:                                        # noqa: BLE001
            levees.append((aid, cat, type(exc).__name__))
            continue
        if (u_out, u_st) == (t_out, t_st):
            identiques.append((aid, cat))
            # TEMOIN NON NUL (accord en regime DEGENERE = zero preuve) : un cast qui ne mute RIEN
            # rend deux empreintes egales sans que la resolution y soit pour quelque chose.
            if u_st == empreinte_etat(_montage_pour(aid, board)):
                inertes.append((aid, cat))
        else:
            divergentes.append((aid, cat))
            if verbeux or ability:
                print(f"\n--- {aid} {ActiveAbilityType(aid).name} [{cat}] DIVERGE")
                print(f"    U out    = {u_out}")
                print(f"    T out    = {t_out}")
                if u_st[0] != t_st[0]:
                    print(f"    U effets = {u_st[0]}")
                    print(f"    T effets = {t_st[0]}")
                if u_st[1] != t_st[1]:
                    for a, b in zip(u_st[1], t_st[1]):
                        if a != b:
                            print(f"    unite U={a} T={b}")
    par_cat: dict = {}
    for aid, cat in divergentes:
        par_cat.setdefault(cat, []).append(aid)
    print(f"\n=== RAYON #287-r14 (registre = {len(ABILITY_CLASSES)} abilities, voie = {voie}) ===")
    print(f"  jouees              : {len(divergentes) + len(identiques)}")
    print(f"  DIVERGENTES (U != T): {len(divergentes)}")
    for cat in sorted(par_cat):
        print(f"      {cat:20s} : {len(par_cat[cat])} -> {par_cat[cat]}")
    print(f"  identiques          : {len(identiques)}")
    print(f"      dont INERTES (aucune mutation, l'accord ne prouve RIEN) : {len(inertes)}")
    print(f"      dont TEMOINS NON NULS (le cast a mute l'etat)           : "
          f"{len(identiques) - len(inertes)}")
    tt_temoins = sorted(a for a, c in identiques
                        if c == "TargetIsTile" and (a, c) not in inertes)
    print(f"      TargetIsTile a temoin non nul : {len(tt_temoins)} -> {tt_temoins}")
    print(f"  levees (montage)    : {len(levees)} -> {levees}")
    tile_target = sorted(a for a, c in ABILITY_CLASSES.items() if _categorie(c) == "TargetIsTile")
    print(f"  portent TargetIsTile: {len(tile_target)} -> {tile_target}")
    print("  NB : le montage generique DELIMITE, il ne prouve pas -- une ability dont l'arbre ne")
    print("       lit pas le role `target` sur CE substrat peut le lire sur le sien.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", type=int, default=None)
    ap.add_argument("--verbeux", action="store_true")
    ap.add_argument("--voie", choices=("behaviour", "handler"), default="behaviour",
                    help="behaviour = `execute_behaviour` en direct ; handler = le chemin REEL "
                         "du moteur (`visit_ActiveAbilityMessage`), la ou vit la resolution")
    ns = ap.parse_args()
    return rayon(ns.ability, ns.verbeux, ns.voie)


if __name__ == "__main__":
    raise SystemExit(main())
