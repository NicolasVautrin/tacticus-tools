#!/usr/bin/env python
"""probe_566_vexilla_magnifica_decision -- face DECISION de `1183 VexillaMagnifica`, et le SEUL
etage que #566 y ajoute : le `continue` sur `HasEffect(cible, Stunned)`.

LA QUESTION BINAIRE
-------------------
`IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$EvaluateNonComparable`, relu integralement :

    bucket = new Bucket(0, Nullable(<statics[0]>))            # `$$.cctor` : Fix64(1) = MIN_UTILITY
    foreach entity in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
        utility = Fix64( UnitExtensions.GetStat(entity, 5 = Health, 0, 0) )
        if (EntityExtensions.HasEffect(entity, this.State@+0x20, 0x48a = 1162 Stunned,
                                       onlyActive: null))  continue;
        bucket.AddAction( BasePlaybook.GenerateAction(casterPosition, entity, utility) )

L'utilite est donc les PV COURANTS -> le natif prefere la cible la PLUS GROSSE ; et une cible
STUNNEE est ECARTEE, quelle que soit son utilite. Le port ne portait que la premiere moitie
(`[filtre HasEffect 0x48a : TODO]` dans sa docstring).

MONTAGE -- DEUX Aesoth, et c'est ce qui rend le stun ATTEIGNABLE
---------------------------------------------------------------
1183 stunne ses deux cibles, mais son `cooldownTurns` (2) est du meme ordre que la duree du stun :
un seul porteur ne peut pas se retrouver a DECIDER pendant que sa propre victime est encore stunnee.
Le montage met donc DEUX `custoVexilusPraetor` dans mon camp :

    A  (3,4)  ennemi PV HAUTS   -- cible du cast d'Aesoth#1, donc STUNNE ensuite ; adjacent aux DEUX
    A1 (2,3)  Aesoth#1          -- adjacent a A et a B
    A2 (4,4)  Aesoth#2          -- adjacent a A et a C, c'est LUI qu'on interroge
    B  (2,2)  ennemi PV HAUTS   -- 2e cible du cast d'Aesoth#1 (adjacent a A1 SEUL)
    C  (5,4)  ennemi PV BAS     -- adjacent a A2 SEUL

`Movement = 0` sur les deux Aesoth (`--unit-stat`, meme visualId donc les deux a la fois) : le
balayage de positions du generateur se reduit a l'origine, donc l'ensemble des cibles eligibles
d'Aesoth#2 est EXACTEMENT `{A, C}`. Sans ca, une tuile de move ferait entrer B dans le jeu et le
verdict ne dirait plus rien du filtre.

SCENARIOS (le MEME etat, a UNE difference pres : le stun)
  * `sans_stun` -- Aesoth#2 decide AVANT tout cast. `PV(A) > PV(C)` -> le natif vise **A**.
                   C'est le TEMOIN : il etablit que l'utilite est bien `GetStat(Health)` et que le
                   port la porte, AVANT d'ajouter le filtre.
  * `avec_stun` -- Aesoth#1 caste 1183 sur A (A et B deviennent `Stunned`), puis Aesoth#2 decide.
                   Le natif doit BASCULER sur **C**, malgre `PV(A) > PV(C)`.

CONTRE-EPREUVE (port, meme etat) : `_target_is_stunned` neutralise -> le port doit REDEVENIR **A**
au scenario `avec_stun`. Sans elle, un accord sur `C` pourrait venir de n'importe quoi d'autre.

ORACLE = `aiDryRunAllUnits` (`CalculateNextActionForUnit`, read-only, `mutated=false` verifie),
JAMAIS `aiPredict` (preview du seul vecteur Attack).

ASCII only (cp1252). Usage (depuis scripts/python, session Frida chaude) :
    python probe_566_vexilla_magnifica_decision.py [--seed 56601] [--board MC1_67] [--garder]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_119_supreme_commander_decision import native_proposal, port_proposal, r  # noqa: E402
from rl_collect_batch import _resolve_session                                       # noqa: E402

VEXILLA_MAGNIFICA = 1183
CASTER = "custoVexilusPraetor"
FOE_HAUT = "necroWarden"      # A -- PV hauts, cible du cast d'Aesoth#1 -> STUNNE
FOE_2E = "bloodMephiston"     # B -- 2e cible du cast d'Aesoth#1 (hors du champ d'Aesoth#2)
FOE_BAS = "tauCrisis"         # C -- PV bas, la SEULE alternative d'Aesoth#2 une fois A stunne
BOARD = "MC1_67"
RANK = 17

POS_A = (3, 4)
POS_A1 = (2, 3)
POS_A2 = (4, 4)
POS_B = (2, 2)
POS_C = (5, 4)
#: PV : A et B increvables (le cast d'Aesoth#1 ne doit tuer personne), C STRICTEMENT plus bas que A
#: -- c'est l'ECART qui rend le verdict lisible (sans filtre, l'argmax d'utilite est A).
HP_HAUT = 200000
HP_BAS = 100000


def _tile(p):
    return "%d,%d" % (p[0], p[1])


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def build(state_file: str, seed: int, board: str):
    argv = ["build", "--seed", str(seed), "--board", board, "--rank", str(RANK),
            "--p-units", "%s,%s" % (CASTER, CASTER),
            "--a-units", "%s,%s,%s" % (FOE_HAUT, FOE_2E, FOE_BAS),
            "--no-ai",
            "--place", "%s:%s" % (CASTER, _tile(POS_A1)),
            "--place", "%s:%s" % (CASTER, _tile(POS_A2)),
            "--a-place", "%s:%s" % (FOE_HAUT, _tile(POS_A)),
            "--a-place", "%s:%s" % (FOE_2E, _tile(POS_B)),
            "--a-place", "%s:%s" % (FOE_BAS, _tile(POS_C)),
            # Movement 0 : le balayage de positions du generateur se reduit a l'origine (cf.
            # l'en-tete). `--unit-stat` est keye par visualId -> les DEUX Aesoth le recoivent.
            "--unit-stat", "%s:Movement=0" % CASTER,
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (FOE_HAUT, HP_HAUT, HP_HAUT),
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (FOE_2E, HP_HAUT, HP_HAUT),
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (FOE_BAS, HP_BAS, HP_BAS),
            "--state-file", state_file]
    p = _duel(argv)
    if p.returncode != 0 or not os.path.exists(state_file):
        print("[build] rc=%s\n%s\n%s" % (p.returncode, (p.stdout or "")[-1500:],
                                         (p.stderr or "")[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def _par_position(sid, rid):
    """`{(col,row): unite}` du `decisionView` -- les DEUX Aesoth partagent leur `visualId`, seule la
    POSITION les distingue."""
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[(p.get("col"), p.get("row"))] = u
    return out, dv


def assert_montage(par_pos):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer."""
    voulu = {POS_A: FOE_HAUT, POS_A1: CASTER, POS_A2: CASTER, POS_B: FOE_2E, POS_C: FOE_BAS}
    for pos, vis in voulu.items():
        u = par_pos.get(pos)
        if u is None or u.get("visualId") != vis:
            raise SystemExit("placement REFUSE en %r (attendu %s, vu %r) -- pas de mesure"
                             % (pos, vis, (u or {}).get("visualId")))
    hp_a, hp_c = par_pos[POS_A].get("hp"), par_pos[POS_C].get("hp")
    if not (hp_a and hp_c and hp_a > hp_c):
        raise SystemExit("PV(A)=%s doit etre STRICTEMENT > PV(C)=%s : sans cet ecart le verdict "
                         "`sans_stun` ne dirait rien de l'utilite" % (hp_a, hp_c))


def _port_sans_filtre(sid, rid, uid):
    """MEME decision, avec le filtre `HasEffect(Stunned)` NEUTRALISE -- la contre-epreuve."""
    from engine.playbook.noncomparable.vexilla_magnifica import VexillaMagnificaPlaybook as VM
    ancien = VM._target_is_stunned
    VM._target_is_stunned = lambda self, target, ctx: False
    try:
        return port_proposal(sid, rid, uid)
    finally:
        VM._target_is_stunned = ancien


def _stunnes(sid, rid):
    """Les unites qui portent `Stunned` (1162), LU du `decisionView` -- l'entree du filtre.

    ⚠ Le `decisionView` ne publie AUCUNE liste `effects` de premier niveau : les effets sont des
    NOMS, per-unite, sous `units[].effects` (mesure du 2026-08-08 -- un lecteur qui cherchait
    `dv["effects"]` rendait la liste VIDE, donc « personne n'est stunne » sur un etat ou le natif
    venait de stunner)."""
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    out = set()
    for u in (dv.get("units") or []):
        for e in (u.get("effects") or []):
            nom = e if isinstance(e, str) else (e.get("name") if isinstance(e, dict) else None)
            if nom == "Stunned":
                out.add(int(u.get("id")))
    return sorted(out)


def confronte(tag, sid, rid, uid, attendu_cible):
    nat = native_proposal(sid, rid, uid)
    port = port_proposal(sid, rid, uid)
    sans = _port_sans_filtre(sid, rid, uid)
    nat_cast = nat["ability"] == VEXILLA_MAGNIFICA
    port_cast = port.get("kind") == "ability" and port.get("ability") == VEXILLA_MAGNIFICA
    ok = (nat_cast and port_cast and nat["target"] == port.get("target")
          and nat["target"] == attendu_cible)
    print("[%s] u%s  NATIF(ab=%s tgt=u%s)  PORT(%s ab=%s tgt=u%s)  "
          "PORT_SANS_FILTRE(%s ab=%s tgt=u%s)"
          % (tag, uid, nat["ability"], nat["target"], port.get("kind"), port.get("ability"),
             port.get("target"), sans.get("kind"), sans.get("ability"), sans.get("target")))
    print("       stunnes = %s ; cible ATTENDUE = u%s -> %s"
          % (_stunnes(sid, rid), attendu_cible, "OK" if ok else "DESACCORD"))
    return {"tag": tag, "natif": nat, "port": port, "sans_filtre": sans,
            "attendu": attendu_cible, "ok": ok}


def campagne(sid, sf, seed, board, garder=False):
    """Joue les DEUX scenarios sur le MEME runner et rend `list[record]` (vide = montage KO).

    FOYER UNIQUE du montage et des criteres : `main` et la garde
    `test_566_vexilla_magnifica_live.py` passent tous deux par ici."""
    rid = build(sf, seed, board)
    if rid is None:
        print("[566d] BUILD KO")
        return []
    recs = []
    try:
        par_pos, _dv = _par_position(sid, rid)
        assert_montage(par_pos)
        a1, a2 = par_pos[POS_A1], par_pos[POS_A2]
        ida, idc = par_pos[POS_A]["id"], par_pos[POS_C]["id"]
        print("[566d] runner=%s  Aesoth#1=u%s@%s  Aesoth#2=u%s@%s  A=u%s(PV %s)  C=u%s(PV %s)"
              % (rid, a1["id"], POS_A1, a2["id"], POS_A2, ida, par_pos[POS_A]["hp"],
                 idc, par_pos[POS_C]["hp"]))

        # --- TEMOIN : aucun stun, l'utilite seule decide -> la cible aux PV les plus HAUTS.
        recs.append(confronte("sans_stun", sid, rid, a2["id"], ida))

        # --- Aesoth#1 caste 1183 sur A : A (et sa 2e cible B) deviennent `Stunned`.
        p = _duel(["act", "ability", "--caster", str(a1["id"]), "--ability",
                   str(VEXILLA_MAGNIFICA), "--target", str(ida),
                   "--state-file", sf, "--runner", str(rid)])
        if p.returncode != 0:
            raise SystemExit("[566d] cast d'amorce KO rc=%s\n%s"
                             % (p.returncode, (p.stdout or "")[-1200:]))
        stunnes = _stunnes(sid, rid)
        if ida not in stunnes:
            raise SystemExit("[566d] A (u%s) n'est PAS stunne apres le cast d'amorce (%s) -- "
                             "montage sterile" % (ida, stunnes))
        if idc in stunnes:
            raise SystemExit("[566d] C (u%s) est stunne AUSSI -- le montage ne discrimine plus"
                             % idc)
        recs.append(confronte("avec_stun", sid, rid, a2["id"], idc))
    finally:
        if not garder:
            _duel(["dispose", "--state-file", sf, "--runner", str(rid)], timeout=120)
    return recs


def verdict(recs) -> bool:
    """`True` ssi les DEUX scenarios concordent ET la contre-epreuve MORD."""
    if len(recs) < 2:
        print("[566d] montage sterile : %d scenario(s)" % len(recs))
        return False
    ok = all(rec["ok"] for rec in recs)
    # La contre-epreuve DOIT mordre au scenario `avec_stun` : sinon le filtre n'est pas ce qui
    # produit l'accord, et le port pourrait etre juste par hasard.
    av = next((rec for rec in recs if rec["tag"] == "avec_stun"), None)
    if av is not None:
        mord = av["sans_filtre"].get("target") != av["port"].get("target")
        print("[566d] contre-epreuve `sans filtre` : %s"
              % ("MORD (cible u%s au lieu de u%s)"
                 % (av["sans_filtre"].get("target"), av["port"].get("target")) if mord
                 else "NON DISCRIMINANTE -- le filtre n'est pas ce qui decide"))
        ok = ok and mord
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Face DECISION de 1183 -- filtre HasEffect(Stunned)")
    ap.add_argument("--seed", type=int, default=56601)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    sf = a.state_file or str(PYDIR.parents[1] / "logs" / ("probe566d_%d.json" % os.getpid()))
    recs = campagne(sid, sf, a.seed, a.board, garder=a.garder)
    ok = verdict(recs)
    print("[566d] VERDICT : %s" % ("OK" if ok else "DESACCORD"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
