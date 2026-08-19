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
  E4 gate  -- LE CRITERE D'ACCEPTATION DE #456. `get_only_targets` non vide prouve que l'ENTREE est
              peuplee, PAS que le gate mord. On confronte donc cible par cible, sur l'etat HYDRATE
              (jamais mute par le port), le verdict du natif -- `abilityReason(caster=taunte,
              abilityType=69)` -- a `get_invalid_target_reason`. Avec son CONTREFACTUEL : le MEME
              etat recharge d'un `decisionView` dont on a RETIRE `bondMeasured` (ce que rendait
              exactement le hook d'avant #496) doit ACCEPTER ce que le natif REFUSE. Sans ce
              contrefactuel, un accord ne distinguerait pas « le gate mord » de « la cible etait de
              toute facon refusee pour une autre raison ».

Les VERDICTS sont des fonctions PURES, exercees offline par
`tests/engine/test_436r1_bond_channel_offline.py` (qui garde AUSSI la face port).

Usage (depuis scripts/python) :
    python probe_436r1_bond_channel.py [--seed 777] [--board MC1_67]

ASCII only.
"""
from __future__ import annotations

import argparse
import copy
import sys

from sibling_script import sibling_script

CRUSHING = 1105                      # `CrushingClaws`, porteur `tyranTyrantGuard` (HERO, au pool)
TAUNTED = 27                         # `Taunted_OnlySpecificTargets`
NORMAL_ATTACK = 69                   # `Loki_NormalAttack` -- l'id CONCRET, jamais l'abstrait 17
# `TargetingRule.TargetIsAllowedForCaster` -- le CODE que rend `TargetingQuery$$GetInvalidTargetReason`
# quand `GetOnlyTargets(caster)` est non vide et que la cible n'y figure pas. Le bit 23 n'est jamais
# TESTE par la regle : il n'en est que la sortie (cf. `probe_436_taunt_targeting`).
FORCED = 0x800000

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


def check_gate(rows) -> dict:
    """E4 -- le gate MORD-IL, et est-ce bien LE CANAL qui l'arme ?

    `check_seed` prouve que l'ENTREE de la regle est peuplee. Ce n'est pas la meme question que
    « le port refuse ce que le natif refuse » : entre les deux il y a toute la cascade de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, et le port pourrait tres
    bien refuser POUR UNE AUTRE RAISON (portee, camp, cible morte) et rendre un accord trompeur.

    `rows` : une par cible vivante, avec
      * `nat`             -- `abilityReason(casterId=taunte, abilityType=69, targetId=X)` ;
      * `port`            -- `get_invalid_target_reason` sur l'etat HYDRATE (jamais mute par le
                             port : le taunt n'y est arrive que par `load_state`) ;
      * `portSansCanal`   -- le MEME etat recharge d'un `decisionView` prive de `bondMeasured`,
                             c'est-a-dire ce que rendait le hook d'AVANT #496.

    QUATRE conditions, et la derniere est celle qui fait la difference entre une mesure et une
    coincidence :
      (1) accord natif/port sur TOUTES les lignes ;
      (2) au moins une ligne ou le natif rend `0x800000` -- sinon le gate n'a rien a mordre ici ;
      (3) au moins une ligne ACCEPTEE (`0x0`) -- sinon un port qui refuserait TOUT passerait (1)+(2) ;
      (4) au moins une ligne refusee `0x800000` que le port SANS CANAL ACCEPTAIT (`0x0`) : c'est la
          degradation PERMISSIVE de #436-r1, prise en flagrant delit. Sans (4), rien ne prouve que
          c'est l'hydratation qui arme la regle."""
    if not rows:
        return {"status": "no-rows", "message": "aucune cible mesuree -- rien n'est conclu"}
    desaccords = [r for r in rows if r.get("nat") != r.get("port")]
    refus = [r for r in rows if r.get("nat") == FORCED]
    acceptes = [r for r in rows if r.get("nat") == 0]
    gagnees = [r for r in refus if r.get("portSansCanal") == 0]
    probs = []
    if desaccords:
        probs.append("%d/%d ligne(s) en DESACCORD natif/port : %s"
                     % (len(desaccords), len(rows),
                        [(r.get("target"), _h(r.get("nat")), _h(r.get("port")))
                         for r in desaccords[:5]]))
    if not refus:
        probs.append("le natif ne rend `TargetIsAllowedForCaster` (0x800000) sur AUCUNE ligne -- "
                     "le gate n'a rien a mordre sur ce montage, l'accord ne prouve donc rien")
    if not acceptes:
        probs.append("le natif n'ACCEPTE aucune ligne -- un port qui refuserait tout passerait les "
                     "autres controles")
    if refus and not gagnees:
        probs.append("aucune des %d ligne(s) refusees par le natif n'etait ACCEPTEE par le port "
                     "sans canal (%s) -- le contrefactuel ne mord pas, donc rien ne prouve que "
                     "c'est l'hydratation qui arme la regle"
                     % (len(refus), [(r.get("target"), _h(r.get("portSansCanal")))
                                     for r in refus[:5]]))
    if probs:
        return {"status": "wrong", "message": " | ".join(probs)}
    return {"status": "ok",
            "message": ("%d cibles, accord natif/port PARTOUT ; %d refus 0x800000, %d acceptations ; "
                        "%d ligne(s) que le port SANS CANAL acceptait (degradation permissive "
                        "fermee) : %s"
                        % (len(rows), len(refus), len(acceptes), len(gagnees),
                           [r.get("target") for r in gagnees[:5]]))}


def _h(v):
    """hex lisible, tolerant au `None` (le natif rend `None` quand la raison n'est pas decodable)."""
    return "-" if v is None else hex(int(v))


def _strip_bond_channel(dv: dict) -> dict:
    """Le CONTREFACTUEL : le MEME `decisionView`, prive de `bondMeasured` sur chaque effet.

    C'est litteralement ce que rendait le hook d'AVANT #496 -- la cle n'existait pas. On coupe le
    CANAL et non le composant : la coupure traverse alors toute la chaine du port
    (`EffectFactory.create` -> `eff.bonded is None` -> `_load_forced_attack_targets` n'ecrit rien ->
    `get_only_targets == []` -> regle 23 DESARMEE), au lieu de simuler l'effet final en supposant
    le chemin."""
    out = copy.deepcopy(dv)
    for u in (out.get("units") or []):
        for e in (u.get("effects") or []):
            e.pop("bondMeasured", None)
            e.pop("bondedEntityId", None)
    return out


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
        P_UNITS, _bring_within, _build, _capture, _make_adjacent, _mk_state, _resolve_session,
    )
    from engine.runner.abilities.targeting import (
        _NormalAttackTargeting, get_invalid_target_reason)

    sid = _resolve_session()
    rid, state_file = _build(sid, a.seed, a.board, P_UNITS, a.a_units)
    print("[build] runner=%d board=%s seed=%s" % (rid, a.board, a.seed))
    try:
        for _ in range(P247.TOURS_DE_CHAUFFE):
            P247._act(sid, rid, {"kind": "endturn"}, 60)

        tauntee_id = _make_adjacent(sid, rid, "tyranTyrantGuard")
        if tauntee_id is None:
            print("[FAIL] impossible d'amener tyranTyrantGuard au contact")
            return 2
        # `ultraCalgar` AU CONTACT du TAUNTE, et c'est LOAD-BEARING pour E4 : c'est la SECONDE
        # cible, celle que le taunt doit faire REFUSER. A d>=2, `necroWarden` (ranged r3, clampe en
        # melee par `forceMeleeTarget` des qu'il est adjacent a un ennemi) serait deja refuse pour
        # PORTEE avant tout taunt -- la ligne resterait un refus, mais le contrefactuel (4) ne
        # montrerait plus la degradation PERMISSIVE. Meme geometrie que `probe_436_taunt_targeting`.
        d_cal = _bring_within(sid, rid, "ultraCalgar", tauntee_id, 1)
        print("[geometrie] taunte=u%s ; ultraCalgar a d=%s du taunte" % (tauntee_id, d_cal))
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

        # ---- E4 : LE GATE, sur l'etat HYDRATE, avec son CONTREFACTUEL ---------------------- #
        # `st` n'a JAMAIS ete mute par le port : le taunt n'y est arrive que par `load_state`.
        # `st_sans` est le meme etat recharge d'un `decisionView` prive de `bondMeasured`.
        dvp, ob, snap, bg = payloads
        st_sans = _mk_state((_strip_bond_channel(dvp), ob, snap, bg))
        pport = _NormalAttackTargeting()
        rows = []
        print("E4 gate    -- ability %d du TAUNTE u%d, sur l'etat HYDRATE"
              % (NORMAL_ATTACK, tauntee_id))
        print("   %-22s %-6s %-10s %-10s %-10s %s"
              % ("cible", "id", "natif", "port", "sansCanal", "accord"))
        for u in (dv_post.get("units") or []):
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            nat = P247._nat(sid, rid, tauntee_id, NORMAL_ATTACK, tid)
            nv = P247._hexval((nat or {}).get("targetReason") or {})
            pv = int(get_invalid_target_reason(st, tauntee_id, tid, pport))
            sv = int(get_invalid_target_reason(st_sans, tauntee_id, tid, pport))
            rows.append({"target": tid, "vis": u.get("visualId"), "nat": nv, "port": pv,
                         "portSansCanal": sv})
            print("   %-22s %-6d %-10s %-10s %-10s %s"
                  % (str(u.get("visualId"))[:22], tid, _h(nv), _h(pv), _h(sv),
                     "OK" if nv == pv else "MISMATCH"))
        v4 = check_gate(rows)
        print("E4 gate    [%s] %s" % (v4["status"], v4["message"]))

        if v0["status"] != "measured":
            print("\nVERDICT: %s" % HOOK_NOT_REINJECTED)
            print("Le MONTAGE, lui, est PRET : le taunt LIVE est pose (u%d taunte par u%d) et les "
                  "quatre etages sont cables. Il ne manque que la fenetre." % (tauntee_id, cid))
            return 7
        bad = [v for v in (v2, v3, v4) if v["status"] != "ok"]
        if bad:
            print("\nVERDICT: %d etage(s) en ECHEC -- %s"
                  % (len(bad), " | ".join(v["message"] for v in bad)))
            return 8
        print("\nVERDICT: OK -- le lien BONDE est PUBLIE par la vue d'effet, le port l'INGERE "
              "(load_state -> get_only_targets), et le gate `TargetIsAllowedForCaster` MORD sur "
              "l'etat HYDRATE en accord avec le natif -- la ou le port SANS CANAL acceptait.")
        return 0
    finally:
        try:
            import subprocess
            subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose",
                            "--state-file", str(state_file)], capture_output=True, text=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
