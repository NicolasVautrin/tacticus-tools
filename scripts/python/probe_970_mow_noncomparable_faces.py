"""#970 -- confrontation LIVE des faces DECISION NonComparable portees sur MACHINES OF WAR.

Ce que ce probe etablit, et dans cet ordre :

  1. **REACHABILITY** : la MoW porteuse est deployee, elle a un `casterId`, et le selecteur natif
     (`abilityTargets`) rend des cibles pour l'ability. Sans ca, tout le reste est vide.
  2. **LE PORT PROPOSE** : `engine.ai.context.build_machine` + `engine.ai.tactic.DefaultMachineTactic`
     -- le chemin REEL, pas la feuille isolee -- rend une action portant l'`abilityType` attendu.
  3. **CONTRE-EPREUVE (non-degenerescence)** : le MEME appel, playbook RETIRE du registre, ne rend
     PLUS cette action. C'est ce qui distingue « mon port decide » de « quelque chose d'autre
     decidait deja » -- et c'est le cran qui manquait aux six contre-epreuves muettes de #957.
  4. **ORACLE NATIF** : `aiStepDryRun` sur le runner -- ce que le jeu DECIDE pour cette MoW.

Montage : `rl_duel build --p-mow <porteur>` (patron `probe_350r3_mow_caster` / `probe_360`), board
`MC1_67`. Une MoW est HORS PLATEAU : il n'y a rien a deplacer pour elle, et `ctx.reach_nc == []`
-- c'est precisement la contrainte structurelle que les deux playbooks doivent respecter, et elle
est CONFIRMEE par la mesure (`reach_nc=0, origin=None` sur les deux porteurs).

MESURES DU 2026-08-12 (session 69, board MC1_67, seed 35030) -- ce que ce probe a etabli :

  * `tauBroadside` / **1161** : 2 cibles `fromHere`, port rend
    `{kind: ability, target: 77, ability: 1161, to: None, util: 1.0}`, contre-epreuve (registre
    ampute) rend `{kind: finish}`. **La contre-epreuve MORD** -> avant ce port, l'ability n'etait
    proposee par AUCUN chemin.
  * `orksRukkatrukk` / **1201** : 58 cibles `fromHere`, la FEUILLE rend
    `{target: 61, ability: 1201, to: None, pred: 3.0}` -- utilite NON TRIVIALE (`1 + 2` ennemis
    adjacents), donc le mirror calcule. Mais le DRIVER ne la voit pas : `me.abilities` est VIDE.
  * CAUSE, localisee par etage et non supposee : `dv.mows[casterId].abilities` publie bien
    `[1160, 1161]` et `[1200, 1201]` -- c'est `build_machine` qui ne retient que les abilities
    UTILISABLES. Le partage est EXACTEMENT celui des `initialCooldownTurns` du gameconfig :
    `1161` = 0 (retenue, `usable: True, cooldown: 0`), `1160`/`1200`/`1201` = 1 (ecartees). Ce
    n'est donc PAS un trou du port : c'est `AActionGenerator$$CanAbilityBeUsed` cote natif, et la
    confrontation AU DRIVER de 1201 demande d'avancer d'un round (residu `#970-r1`).

    python probe_970_mow_noncomparable_faces.py --state-file <chemin ABSOLU unique>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import probe_350r3_mow_caster as P350
from probe_350r3_mow_caster import _build, _ids, _move, _r
from rl_collect_batch import _resolve_session, _rpc

from engine.entities.active_ability_type import ActiveAbilityType

BOARD = P350.BOARD
CENTER = P350.CENTER

#: (visualId de la MoW, ActiveAbilityType porte par CE probe, unites de remplissage)
CASES = [
    ("tauBroadside", int(ActiveAbilityType.TwinSmartMissileSystem)),    # 1161
    ("orksRukkatrukk", int(ActiveAbilityType.SquigMine)),              # 1201
]

P_UNITS = "%s,%s" % (P350.SUMMONER, P350.P_FILLER)
A_UNITS = "%s,%s" % (P350.GRAFT_ON, P350.A_FILLER)


def _montage(sid, sf: Path, seed: int, mow: str, level: int = 5):
    """Runner avec `mow` en MACHINE OF WAR du camp ADVERSE. Rend `(rid, casterId, dv)`.

    GEOMETRIE DRIVEE (jamais « bloque par le spawn ») : les quatre unites sont deplacees autour du
    centre pour qu'il existe des ennemis adjacents -- c'est ce qui rend l'utilite de `1201`
    NON TRIVIALE (elle vaut `1 + |ennemis adjacents a la tuile|`)."""
    # `--p-mow` (et NON `--a-mow`) : le tour courant au build est celui du JOUEUR, et une MoW du
    # camp adverse n'a alors ni cible ni activation -- `abilityTargets` rend 0 et `aiStepDryRun`
    # rend une liste VIDE. Mesure du 1er jet de ce probe : `--a-mow` -> 0 cible, contre-epreuve
    # muette. Ce n'est PAS un « porteur non confrontable », c'est le mauvais cote du plateau.
    rid = _build(sf, seed, ["--p-units", P_UNITS, "--a-units", A_UNITS, "--p-mow", mow,
                            "--unit-stat", "%s:ActiveAbilityLevel=%d,"
                                           "AbilityVariablesMultiplierPercentage=100" % (mow, level)],
                 board=BOARD)
    ids, dv = _ids(sid, rid)
    row = next((m for m in (dv.get("mows") or []) if m.get("visualId") == mow), None)
    if row is None:
        raise RuntimeError("MoW %s non deployee (mows=%s)"
                           % (mow, [m.get("visualId") for m in (dv.get("mows") or [])]))
    _move(sid, rid, ids[P350.SUMMONER], *CENTER)
    _move(sid, rid, ids[P350.P_FILLER], CENTER[0] - 1, CENTER[1])
    _move(sid, rid, ids[P350.GRAFT_ON], CENTER[0] + 1, CENTER[1])
    _move(sid, rid, ids[P350.A_FILLER], CENTER[0] + 1, CENTER[1] - 1)
    _, dv = _ids(sid, rid)
    return rid, row.get("casterId"), dv


def _port_action(sid, rid, cid, disabled: int | None = None) -> dict | None:
    """Le chemin PORTE : `build_machine` + `DefaultMachineTactic.calculate_next_action`.

    `disabled` : ability_id a RETIRER du registre `PLAYBOOKS` le temps de l'appel -- c'est la
    contre-epreuve. Le registre est restaure dans le `finally` (un probe qui laisserait le
    registre ampute contaminerait tout appel ulterieur du meme process)."""
    from engine.ai.tactic import DefaultMachineTactic
    from engine.playbook import noncomparable as NC
    saved = None
    if disabled is not None:
        saved = NC.PLAYBOOKS.pop(disabled, None)
        if saved is None:
            raise RuntimeError("contre-epreuve INERTE : %d n'etait pas dans PLAYBOOKS" % disabled)
    try:
        ctx, _dv = P350.ctx_machine(sid, rid, cid)     # `ctx_machine` rend le COUPLE (ctx, dv)
        if ctx is None:
            return None
        return DefaultMachineTactic().calculate_next_action(ctx)
    finally:
        if saved is not None:
            NC.PLAYBOOKS[disabled] = saved


def _native_action(sid, rid, cid) -> dict:
    """`aiStepDryRun` -- ce que le NATIF decide. `mutated:false` : aucune ecriture d'etat."""
    out = _r(sid, rid, "aiStepDryRun", {}, 240) or {}
    msgs = out.get("messages") or out.get("inputs") or []
    for m in msgs:
        if m.get("casterId") == cid or m.get("unitId") == cid:
            return m
    return {"_none_for_caster": cid, "_all": msgs}


def run(state_file: Path, seed: int = 35030) -> int:
    sid = _resolve_session()
    rc = 0
    for mow, ability in CASES:
        print("\n=== #970 %s -- ability %d ===" % (mow, ability))
        rid = None
        try:
            rid, cid, dv = _montage(sid, state_file, seed, mow)
            print("  [1] REACHABILITY : casterId=%s" % cid)
            # Le selecteur est lu par le MEME callable que les playbooks (`ctx.ability_targets`),
            # pas par un appel RPC re-invente : un ecart de nom d'argument ferait rendre ZERO au
            # probe alors que le port, lui, voit des cibles -- exactement le faux negatif a eviter.
            ctx0, _ = P350.ctx_machine(sid, rid, cid)
            at = ((ctx0.ability_targets(cid, ability) or {}) if ctx0 is not None
                  and ctx0.ability_targets is not None else {})
            n = sum(len(a.get("fromHere") or [])
                    for u in (at.get("units") or []) for a in (u.get("abilities") or [])
                    if a.get("abilityId") == ability)
            print("      cibles `fromHere` du selecteur natif : %d  (reach_nc=%d, origin=%s)"
                  % (n, len(getattr(ctx0, "reach_nc", []) or []), getattr(ctx0, "origin", "?")))
            # DIAGNOSTIC par ETAGE (jamais « ca ne sort pas ») : etat d'usabilite tel que le
            # driver `choose_action` le lit, puis ce que la feuille elle-meme rend.
            # `NonComparableGenerator.generate` lit `(ctx.me or {}).get("abilities")` et SAUTE
            # toute entree `usable is False` (mirror `AActionGenerator$$CanAbilityBeUsed`). C'est
            # donc CETTE liste-la qu'il faut imprimer, pas un attribut invente.
            abs_ctx = [a for a in ((getattr(ctx0, "me", None) or {}).get("abilities") or [])
                       if a.get("id") == ability] or None
            print("      etage driver : me.abilities[%d] = %s" % (ability, abs_ctx))
            print("      etage driver : me.abilities TOUTES = %s"
                  % [(a.get("id"), a.get("kind"), a.get("usable"), a.get("cooldown"))
                     for a in ((getattr(ctx0, "me", None) or {}).get("abilities") or [])])
            mrow = next((m for m in (dv.get("mows") or []) if m.get("casterId") == cid), {})
            print("      etage amont  : dv.mows[casterId=%s] cles=%s abilities=%s"
                  % (cid, sorted(mrow.keys()),
                     [(a.get("id") if isinstance(a, dict) else a)
                      for a in (mrow.get("abilities") or [])]))
            from engine.playbook import noncomparable as _NC
            pb = _NC.PLAYBOOKS.get(ability)
            if pb is not None and ctx0 is not None:
                print("      etage feuille : should_evaluate=%s generate_candidates=%s"
                      % (pb.should_evaluate(ctx0), pb.generate_candidates(ctx0)))
            avec = _port_action(sid, rid, cid)
            print("  [2] PORT (registre COMPLET)   : %s" % avec)
            sans = _port_action(sid, rid, cid, disabled=ability)
            print("  [3] CONTRE-EPREUVE (%d retire) : %s" % (ability, sans))
            nat = _native_action(sid, rid, cid)
            print("  [4] NATIF (aiStepDryRun)      : %s" % nat)
            propose = (avec or {}).get("ability") == ability or (avec or {}).get("abilityType") == ability
            change = avec != sans
            print("      VERDICT port propose %d : %s | la contre-epreuve MORD : %s"
                  % (ability, propose, change))
            if not change:
                # DISCRIMINANT : une contre-epreuve muette n'est un ECHEC que si le driver POUVAIT
                # voir l'ability. Si `me.abilities` ne la porte pas, elle a ete ecartee EN AMONT
                # (cooldown initial), et le silence du port est le comportement NATIF -- pas un
                # bug de la feuille, dont l'etage ci-dessus montre qu'elle rend bien un candidat.
                if abs_ctx is None:
                    print("      NON CONFRONTE AU DRIVER -- %d absente de `me.abilities` (ecartee "
                          "en amont : cooldown initial). La FEUILLE, elle, est mesuree ci-dessus."
                          % ability)
                else:
                    print("      !! contre-epreuve MUETTE -- ce probe ne prouve RIEN sur ce cas")
                    rc = 1
        except Exception as e:                       # noqa: BLE001
            print("  ECHEC : %s: %s" % (type(e).__name__, e))
            rc = 1
        finally:
            if rid is not None:
                try:
                    _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60)
                    print("  runner %s dispose" % rid)
                except Exception as e:               # noqa: BLE001
                    print("  dispose KO : %s" % e)
    return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", type=int, default=35030)
    a = ap.parse_args()
    sys.exit(run(Path(a.state_file), a.seed))
