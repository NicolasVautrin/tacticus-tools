#!/usr/bin/env python
"""Probe #1015-r1 -- le trait `CloseCombatWeakness` CONFRONTE LIVE, avec TEMOIN NON-NUL.

CE QU'IL MESURE, et contre quoi :

  1. KIT       -- l'ability `TriggeredAbilityType.CloseCombatWeakness` (1130) est-elle MONTEE sur le
                  porteur quand on force le trait ? Canal `unitAbilityStates` (l'`AbilitiesComponent`
                  REEL), jamais le gameconfig. C'est la confrontation LIVE du dict
                  `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor`
                  (+0x0), lu au decompile : cle `0x40b` (UnitTrait 1035) -> valeur `0x46a` (1130).

  2. NATIF     -- le natif applique-t-il vraiment le malus, et de combien ? DEUX runners, MEME seed,
                  MEME board, MEMES unites, MEME `Movement` : le seul ECART est le trait. On compare
                  la PREDICTION NATIVE (`decisionView.attackPlans`, `ranked[0].dmgMin/dmgMax`) de la
                  MEME attaque normale depuis la MEME tuile candidate. Le runner SANS trait EST le
                  temoin non-nul : sans lui, un accord ne prouverait rien (regime degenere).

  3. PORT      -- le port rend-il la MEME chose que le natif, DANS LES DEUX REGIMES ? La prediction
                  offline passe par `engine.playbook.prediction.make_normal_attack_predictions` sur
                  la `Scene`, exactement comme `predict_samples`. Un accord dans le seul regime SANS
                  trait ne prouverait rien non plus : c'est le couple qui fait la mesure.

MONTAGE. Les 16 porteurs du trait sont TOUS `units.npc`, donc hors pool. Le trait se GREFFE par
`rl_duel build --unit-stat "<vis>:Traits=[...]"`, levier qui mord sur 104 des 105 membres de
`UnitTrait`. Le porteur greffe est `astraBullgryn` : HERO du pool, arme MELEE unique, deux traits
seulement -- et rien dans `CloseCombatWeakness_ReduceDmg_Effect` ni dans son playbook ne lit les
stats ou les traits du caster, donc la greffe est LEGITIME (meme critere que `1194 NovaShield`).

`Movement=12` est pose SUR LES DEUX runners : il ne touche aucun canal de degat, et il met la tuile
d'attaque a portee du premier tour -- sans lui la mesure demanderait plusieurs tours de nav, donc
deux etats divergents.

⚠ MESURE INATTENDUE, ET ELLE EST DANS LE RESULTAT : `BC.Abilities.Traits` ne contient QUE
`{HeavyWeapon, MartialKatah, RangedSpecialist}` -- **pas** `CloseCombatWeakness` -- et le natif
applique quand meme le malus. La config de cette ability de trait n'est donc PAS lue depuis la
`BattleConfiguration` ; aucune injection de config n'est requise pour ce montage, contrairement au
verrou d'une ability de RELIQUE (#237). Le port lit la source AMONT (`globalValues.traitVariables`,
`closeCombatWeaknessMeleeDmgPctReduction` = -50 / `...Range...` = -25), et les deux concordent.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_1015r1_close_combat_weakness.py
    python probe_1015r1_close_combat_weakness.py --keep      # ne pas disposer les runners

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_duel as R                                                    # noqa: E402
from engine.playbook import scene as SC                                # noqa: E402
from engine.playbook import prediction                                 # noqa: E402
from engine.playbook.scene import Scene                                # noqa: E402
from engine.runner import snapshot as _snapshot                        # noqa: E402

#: le porteur GREFFE et sa liste de traits d'ORIGINE (le patch REMPLACE la liste, il ne l'augmente pas).
PORTEUR = "astraBullgryn"
PORTEUR_TRAITS = ["Hero", "BigTarget"]
CIBLE = "astraCreed"
BOARD = "MC1_67"
SEED = 777
TRAIT = "CloseCombatWeakness"
#: `TriggeredAbilityType.CloseCombatWeakness`, la valeur du dict `Trait$$GetTriggeredAbility`.
ABILITY_ID = 1130
#: `closeCombatWeaknessMeleeDmgPctReduction` du gameconfig -> `ConfigConst(0x4c = dmgPctReduction)`.
PCT_MELEE = -50


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _sf(nom: str) -> str:
    """State-file ABSOLU, unique par PID, HORS `data/` (que `rl_duel --state-file` refuse, #349)."""
    return os.path.join(tempfile.gettempdir(), "ccw_%d_%s.json" % (os.getpid(), nom))


def _build(state_file: str, with_trait: bool) -> int:
    traits = PORTEUR_TRAITS + ([TRAIT] if with_trait else [])
    R.main(["build", "--seed", str(SEED), "--board", BOARD,
            "--p-units", PORTEUR, "--a-units", CIBLE, "--state-file", state_file,
            "--unit-stat", "%s:Traits=%s" % (PORTEUR, str(traits).replace("'", '"')),
            "--unit-stat", "%s:Movement=12" % PORTEUR])
    return int(R._read_state(Path(state_file))["runnerId"])


def _mesure(sid, rid: int) -> dict:
    """Rend {`kit`, `plans`} pour le runner : le kit DECLENCHE du porteur (canal
    `unitAbilityStates`) et, par plan d'attaque NORMALE du porteur, le couple (oracle natif,
    prediction du port) a la MEME tuile candidate."""
    def rpc(m, body=None, t=90):
        return _res(R._rpc(sid, m, [body] if body is not None else [], timeout=t))

    st = rpc("unitAbilityStates", {"runnerId": rid})
    kit = {}
    for u in (st.get("units") or ()):
        if u.get("configId") == PORTEUR:
            kit[int(u["entityId"])] = sorted(int(t["raw"][0]) for t in (u.get("triggered") or ()))

    predictor = SC.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    dec = rpc("decisionView", _snapshot.decision_view_seed_body(rid, maxRank=3, allAbilities=True))
    sctx = SC.step_context(predictor, dec)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    plans = []
    for ap in (dec.get("attackPlans") or ()):
        a_id = ap.get("unitId")
        if a_id not in kit:                       # on ne mesure QUE le porteur greffe
            continue
        norm = {ab.get("id") for u in (dec.get("units") or ()) if u.get("id") == a_id
                for ab in (u.get("abilities") or ()) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or ()):
            if norm and ev.get("abilityId") not in norm:
                continue
            rk = (ev.get("ranked") or ())
            if not rk or rk[0].get("dmgMax") is None:
                continue
            r0, t_id = rk[0], ev.get("targetId")
            att_pos = ((r0.get("col"), r0.get("row")) if r0.get("col") is not None
                       else sctx["pos_by_id"].get(a_id))
            pred = prediction.make_normal_attack_predictions(scene, a_id, t_id, att_pos)
            res = pred.prediction.accurate_health_damage
            plans.append({"att": a_id, "tgt": t_id, "att_pos": att_pos,
                          "oracle": (r0.get("dmgMin"), r0.get("dmgMax")),
                          "port": (res.min, res.max),
                          "pred_opt": bool(r0.get("predOptimistic"))})
    return {"kit": kit, "plans": plans}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    sid = R._resolve_session()
    sf_w, sf_o = _sf("with"), _sf("without")
    rid_w = _build(sf_w, True)
    rid_o = _build(sf_o, False)
    print("runners : AVEC=%s SANS=%s" % (rid_w, rid_o))
    try:
        m_w, m_o = _mesure(sid, rid_w), _mesure(sid, rid_o)
    finally:
        if not a.keep:
            for f in (sf_w, sf_o):
                try:
                    R.main(["dispose", "--state-file", f])
                except SystemExit:
                    pass
                except Exception as e:                      # noqa: BLE001
                    print("[dispose] %s : %s" % (f, e))

    rc = 0

    # -- 1. KIT ----------------------------------------------------------------------------------
    kit_w = sorted(set().union(*m_w["kit"].values())) if m_w["kit"] else []
    kit_o = sorted(set().union(*m_o["kit"].values())) if m_o["kit"] else []
    print("\n1. KIT DECLENCHE du porteur (`unitAbilityStates`)")
    print("   AVEC trait : %s" % kit_w)
    print("   SANS trait : %s" % kit_o)
    if ABILITY_ID not in kit_w:
        print("   ECHEC : l'ability %d n'est PAS montee alors que le trait est pose -- le dict "
              "`Trait$$GetTriggeredAbility` ne mappe pas ce trait, ou le patch n'a pas mordu."
              % ABILITY_ID)
        rc = 1
    elif ABILITY_ID in kit_o:
        print("   ECHEC : l'ability %d est montee SANS le trait -- le temoin est DEGENERE, l'accord "
              "ne prouverait rien." % ABILITY_ID)
        rc = 1
    else:
        print("   OK : %d monte SSI le trait est pose (dict Trait +0x0 confronte LIVE)." % ABILITY_ID)

    # -- 2 & 3. NATIF et PORT --------------------------------------------------------------------
    print("\n2-3. PREDICTION d'attaque NORMALE du porteur, a la MEME tuile candidate")
    par_pos_w = {p["att_pos"]: p for p in m_w["plans"]}
    par_pos_o = {p["att_pos"]: p for p in m_o["plans"]}
    communs = sorted(set(par_pos_w) & set(par_pos_o))
    if not communs:
        print("   ECHEC : aucune tuile candidate COMMUNE aux deux runners -- rien n'est comparable "
              "(AVEC=%r SANS=%r)." % (sorted(par_pos_w), sorted(par_pos_o)))
        return 1
    attendu = 1.0 + PCT_MELEE / 100.0
    for pos in communs:
        w, o = par_pos_w[pos], par_pos_o[pos]
        print("   @%s  natif SANS=%s  natif AVEC=%s   |   port SANS=%s  port AVEC=%s"
              % (pos, o["oracle"], w["oracle"], o["port"], w["port"]))
        # (a) le NATIF applique bien le malus, et le temoin est NON-NUL.
        if o["oracle"] == w["oracle"]:
            print("      ECHEC : le natif rend LA MEME CHOSE avec et sans le trait -- soit la greffe "
                  "n'a pas mordu, soit la mecanique ne tire pas dans ce regime. Un accord "
                  "port/natif y serait un accord en regime DEGENERE.")
            rc = 1
            continue
        for i, quoi in ((0, "min"), (1, "max")):
            base, avec = o["oracle"][i], w["oracle"][i]
            if not base:
                continue
            ratio = avec / base
            ok = abs(ratio - attendu) <= 0.01
            print("      natif dmg%s : %s -> %s   ratio=%.4f  attendu=%.2f  %s"
                  % (quoi, base, avec, ratio, attendu, "OK" if ok else "ECART"))
            if not ok:
                rc = 1
        # (b) le PORT concorde avec le natif DANS LES DEUX REGIMES.
        for etiq, s in (("SANS", o), ("AVEC", w)):
            if s["pred_opt"]:
                print("      %s : oracle `predOptimistic` -> non exploitable (le preview ignore une "
                      "reduction), pas de verdict." % etiq)
                continue
            ecart = max(abs(s["oracle"][0] - s["port"][0]), abs(s["oracle"][1] - s["port"][1]))
            print("      port %s : oracle=%s port=%s ecart=%d %s"
                  % (etiq, s["oracle"], s["port"], ecart, "OK" if ecart <= 3 else "DIVERGENCE"))
            if ecart > 3:
                rc = 1

    print("\nVERDICT: %s" % ("OK" if rc == 0 else "ECHEC"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
