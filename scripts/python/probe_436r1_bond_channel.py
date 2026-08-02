"""#436-r1 -- la vue d'effet PUBLIE-T-ELLE le lien BONDE, et le port l'INGERE-T-IL ?

LE PROBLEME QU'ON FERME. `TargetIsAllowedForCaster` (bit 23) est portee depuis #436, mais son
ENTREE -- la liste `ForcedAttackTargetsComponent` -- n'existait que quand c'etait le PORT qui avait
pose le taunt. Un etat reconstruit depuis un snapshot natif repartait `GetOnlyTargets == []`, et le
natif n'arme la regle QUE sous `Count > 0` : la restriction disparaissait donc SANS erreur ni crash.
Degradation PERMISSIVE, invisible en self-play -- exactement le trou qu'un entrainement exploite.

RE (decompile = verite). `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` appelle
`IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId(effect)` et ecrit `[cette valeur]` dans le
`ForcedAttackTargetsComponent@+0x50` de la cible. `BondedEntityId` lit le champ `+0x10` du
`BondComponent` porte par l'ENTITE-EFFET. Cet offset est etabli par CINQ lectures independantes,
dont l'ECRIVAIN :
  * `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder(id, abilityState,
    bondedEntityId)` -- `*(int *)(comp + 0x10) = (int)bondedEntityId` (et c'est ce parametre qui
    NOMME le champ) ;
  * `IdunBattle.Entities.Components.BondComponent$$ToString` -- box Int32 de `this+0x10`, champ
    UNIQUE (classe de 24 o = header + int32) ;
  * `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId` ;
  * `IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$Select` ;
  * `IdunBattle.Entities.EntityExtensions$$TryGetBondEffect`.

CE QUE CE PROBE MESURE, par etages :

  E0 canal -- une entree de `decisionView.units[].effects[]` porte-t-elle `bondMeasured` ? Sinon le
              capteur n'est pas charge -> NON CONFRONTE, et aucun etage suivant ne conclut rien.
  E1 taunt -- `tyranTyrantGuard` caste `CrushingClaws` (1105) EN LIVE sur un ennemi au contact.
              C'est le seul moyen d'obtenir un effet 27 pose PAR LE JEU (le probe #436, lui, le
              posait offline -- donc il ne pouvait rien dire du canal).
  E2 lien  -- l'effet 27 du taunte porte-t-il `bondedEntityId == tyrantGuard` ?
  E3 seed  -- `load_state(...)` puis `get_only_targets(state, taunte)` rend-il `[tyrantGuard]` ?
              C'est le bout de la chaine : l'entree de la regle 23.

Les VERDICTS sont des fonctions PURES, exercees offline par
`tests/engine/test_436r1_bond_channel_offline.py` (qui garde AUSSI la face port).

Usage (depuis scripts/python) :
    python probe_436r1_bond_channel.py [--seed 777] [--board MC1_67]

ASCII only.
"""
from __future__ import annotations

import argparse
import sys

CRUSHING = 1105                      # `CrushingClaws`, porteur `tyranTyrantGuard` (HERO, au pool)
TAUNTED = 27                         # `Taunted_OnlySpecificTargets`

HOOK_NOT_REINJECTED = (
    "NON CONFRONTE -- le capteur #436-r1 n'est PAS charge : aucune entree de "
    "`decisionView.units[].effects[]` ne porte `bondMeasured`. Le capteur vit dans "
    "`frida/hooks/game/effects.ts` (`readBondLink`) et reste INERTE tant que le bundle n'a pas ete "
    "rebuilde ET reinjecte. Rien n'est conclu du natif : ni « pas de taunt », ni « pas de lien ».")


# ------------------------------------------------------------------ verdicts (fonctions PURES)

def check_channel(dv: dict) -> dict:
    """Le capteur est-il charge ? On regarde la PRESENCE de la cle `bondMeasured` sur au moins une
    entree d'effet, pas sa valeur : un hook anterieur ne la connait pas du tout, un capteur charge
    la pose sur CHAQUE entree (fut-ce a `False` si `BondComponent` etait irresoluble).

    ⚠ On ne peut PAS discriminer sur `bondedEntityId` : il vaut `null` dans les deux mondes pour
    l'immense majorite des effets (qui ne sont pas des bond effects). C'est exactement l'ambiguite
    que `bondMeasured` existe pour fermer."""
    effs = [e for u in ((dv or {}).get("units") or []) for e in (u.get("effects") or [])]
    if not effs:
        return {"status": "no-effects",
                "message": "aucun effet dans decisionView -- montage KO, rien n'est conclu"}
    n = sum(1 for e in effs if "bondMeasured" in e)
    if n == 0:
        return {"status": "not_reinjected", "message": HOOK_NOT_REINJECTED}
    return {"status": "measured",
            "message": "capteur #436-r1 charge (%d/%d entrees portent bondMeasured)" % (n, len(effs))}


def check_bond(dv: dict, tauntee_id: int, expected: int) -> dict:
    """L'effet 27 du taunte porte-t-il le TAUNTANT ? Trois issues distinctes -- et
    `bondMeasured=False` n'est JAMAIS lu comme « pas de lien »."""
    row = next((u for u in ((dv or {}).get("units") or [])
                if int(u.get("id") or -1) == int(tauntee_id)), None)
    if row is None:
        return {"status": "absent", "message": "u%s absent de decisionView" % tauntee_id}
    taunts = [e for e in (row.get("effects") or []) if e.get("effectType") == TAUNTED]
    if not taunts:
        return {"status": "no-taunt",
                "message": ("u%s ne porte AUCUN effet %d -- le cast n'a pas pose le taunt, rien "
                            "n'est conclu du canal" % (tauntee_id, TAUNTED))}
    e = taunts[0]
    if e.get("bondMeasured") is not True:
        return {"status": "not-measured",
                "message": ("effet %d de u%s : bondMeasured=%r -- la mesure n'a PAS eu lieu "
                            "(classe `BondComponent` irresolue ou lecture KO). Le "
                            "`bondedEntityId=%r` qui l'accompagne ne veut RIEN dire."
                            % (TAUNTED, tauntee_id, e.get("bondMeasured"),
                               e.get("bondedEntityId")))}
    got = e.get("bondedEntityId")
    if got != expected:
        return {"status": "wrong",
                "message": ("effet %d de u%s : bondedEntityId=%r, attendu u%s (le TAUNTANT). "
                            "ATTENTION `source` vaut aussi u%s chez ce producteur -- une lecture "
                            "qui les "
                            "confondrait passerait ici par accident."
                            % (TAUNTED, tauntee_id, got, expected, e.get("source")))}
    return {"status": "ok",
            "message": "effet %d de u%s -> bondedEntityId u%s (LU)" % (TAUNTED, tauntee_id, got)}


def check_seed(state, tauntee_id: int, expected: int) -> dict:
    """Le port a-t-il INGERE le lien ? Le bout de la chaine : `get_only_targets` est ce
    qu'interroge `TargetIsAllowedForCaster`, et le natif n'arme la regle que sous `Count > 0`."""
    from engine.runner.abilities.targeting import get_only_targets
    got = list(get_only_targets(state, tauntee_id) or [])
    if got != [int(expected)]:
        return {"status": "wrong",
                "message": ("load_state : get_only_targets(u%s) = %r, attendu [%s] -- le seed "
                            "`_load_forced_attack_targets` n'a pas mordu, et la regle 23 reste "
                            "DESARMEE (degradation permissive)" % (tauntee_id, got, expected))}
    return {"status": "ok",
            "message": "load_state : get_only_targets(u%s) = %r -- regle 23 ARMEE"
                       % (tauntee_id, got)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-units", default="necroWarden,necroWarden,necroWarden,necroWarden")
    a = ap.parse_args(argv)

    # Imports TARDIFS : le montage est celui de `probe_436_taunt_targeting`, repris TEL QUEL pour
    # qu'aucun des deux probes ne monte une variante de l'autre. Les importer au chargement
    # ferait echouer la garde offline, qui n'exerce que les verdicts PURS ci-dessus.
    import probe_247_splash_targeting as P247             # transport partage (_act/_by_vis/...)
    from probe_436_taunt_targeting import (
        P_UNITS, _build, _capture, _make_adjacent, _mk_state, _resolve_session,
    )

    sid = _resolve_session()
    rid, state_file = _build(sid, a.seed, a.board, P_UNITS, a.a_units)
    print("[build] runner=%d board=%s seed=%s" % (rid, a.board, a.seed))
    try:
        for _ in range(P247.WARMUP_ENDTURNS):
            P247._act(sid, rid, {"kind": "endturn"}, 60)

        tauntee_id = _make_adjacent(sid, rid, "tyranTyrantGuard")
        if tauntee_id is None:
            print("[FAIL] impossible d'amener tyranTyrantGuard au contact")
            return 2
        P247._give_turn_to(sid, rid, "tyranTyrantGuard")
        dv_pre, _ = _capture(sid, rid)
        guard = P247._by_vis(dv_pre, "tyranTyrantGuard")
        if guard is None:
            print("[FAIL] tauntant absent apres montage")
            return 2
        cid = int(guard["id"])

        # ---- E0 : LE CANAL --------------------------------------------------------------- #
        v0 = check_channel(dv_pre)
        print("E0 canal   [%s] %s" % (v0["status"], v0["message"]))

        # ---- E1 : LE CAST, EN LIVE -------------------------------------------------------- #
        # LIVE et non offline : c'est ce qui distingue ce probe de #436. Un taunt pose par le PORT
        # renseigne `eff.bonded` par construction et ne dirait RIEN du canal de capture.
        res = P247._act(sid, rid, {"kind": "ability", "casterId": cid,
                                   "abilityType": CRUSHING, "targetId": tauntee_id}, 120)
        ok = ((res or {}).get("actions") or [{}])[0].get("ok")
        print("E1 cast    [%s] CrushingClaws(u%d -> u%d) ok=%s"
              % ("ok" if ok else "ko", cid, tauntee_id, ok))
        if not ok:
            print("[FAIL] le cast a echoue -- rien n'est conclu du canal")
            return 3

        # ---- E2/E3 ------------------------------------------------------------------------ #
        dv_post, payloads = _capture(sid, rid)
        v2 = check_bond(dv_post, tauntee_id, cid)
        print("E2 lien    [%s] %s" % (v2["status"], v2["message"]))
        st = _mk_state(payloads)
        v3 = check_seed(st, tauntee_id, cid)
        print("E3 seed    [%s] %s" % (v3["status"], v3["message"]))

        if v0["status"] != "measured":
            print("\nVERDICT: %s" % HOOK_NOT_REINJECTED)
            print("Le MONTAGE, lui, est PRET : le taunt LIVE est pose (u%d taunte par u%d) et les "
                  "trois etages sont cables. Il ne manque que la fenetre." % (tauntee_id, cid))
            return 7
        bad = [v for v in (v2, v3) if v["status"] != "ok"]
        if bad:
            print("\nVERDICT: %d etage(s) en ECHEC -- %s"
                  % (len(bad), " | ".join(v["message"] for v in bad)))
            return 8
        print("\nVERDICT: OK -- le lien BONDE est PUBLIE par la vue d'effet et le port l'INGERE "
              "(load_state -> get_only_targets), donc la regle `TargetIsAllowedForCaster` est "
              "ARMEE sur un etat HYDRATE.")
        return 0
    finally:
        try:
            import subprocess
            subprocess.run([sys.executable, "rl_duel.py", "dispose",
                            "--state-file", str(state_file)], capture_output=True, text=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
