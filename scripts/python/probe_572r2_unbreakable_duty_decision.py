"""#572-r2 -- face DECISION de `1061 UnbreakableDuty` (`templAncient`), confrontee au natif.

LE CRITERE, ENONCE AVANT LE MONTAGE
------------------------------------
`UnbreakableDutyPlaybook$$EvaluateNonComparable` rend une utilite CONSTANTE (`Fix64(1)`, le MEME
statique que `MIN_UTILITY`) : il n'y a donc RIEN a departager cote utilite, et un banc qui
comparerait des scores ne mesurerait rien. Tout le discriminant est dans
`UnbreakableDutyPlaybook$$GetUseProbability`, qui rend un POURCENTAGE :

    p = 10 * |allies dans le disque de rayon `range`(=2) autour du caster, centre EXCLU|
    p += 70 si (>=2 heros imperiaux allies MORTS) et (>=1 ennemi adjacent)
    p += 40 si (>=2 heros imperiaux allies MORTS) seulement
    prob = p / 100

`BasePlaybook$$ShouldEvaluate` : `prob <= 0` -> **FAUX** (l'ability n'est pas evaluee du tout),
`prob >= 1` -> **VRAI**, entre les deux -> TIRAGE.

⚠ LE REGIME `prob >= 1` N'EST PAS ATTEIGNABLE SUR CE HARNAIS, et c'est une MESURE, pas un renoncement.
`p >= 100` exigerait dix allies dans le disque de rayon 2 (le `+70` des morts imperiaux plafonne a
70). Or le maximum de spawns du cote JOUEUR, sur les 400+ boards de `data/boards/global`, est **7**
(`C1_75`, `MC1_64`, `MC1_75`, `EMC4_05`, `survival_01`) -- MC1_67 en a **5**, et un build a 11 unites
est refuse en amont du placement (`5 spawns joueur < 11 units`). Le critere est donc BINAIRE-vs-
FREQUENTIEL, et il est enonce ainsi AVANT la mesure :

  * `isole`  -- aucun allie dans le rayon 2, personne de mort : `p = 0` -> `prob <= 0` -> le natif
                N'EVALUE PAS 1061, et ce **quel que soit le nombre de tirages**. Un ennemi est
                pourtant a portee : l'abstention ne peut venir que du gate. Critere : **0 cast sur
                N dry-runs**.
  * `entoure` -- QUATRE allies dans le disque de rayon 2 : `p = 40`, donc `0 < prob < 1` -> le natif
                TIRE. Critere : **au moins 1 cast sur N dry-runs**. C'est ce qui separe << le gate
                laisse passer >> de << le gate bloque >>, et c'est la seule chose que ce regime peut
                etablir.

Cote PORT, le moteur est DETERMINISTE : la porte aleatoire n'est pas modelisee (meme statut assume
que `BlackRage` 0.4, `ItItches`, `ScarabSummon`), donc le port propose 1061 des que `p > 0`.
L'ecart de FREQUENCE sur `entoure` est cet ecart-la, nomme ; l'ecart de VERDICT sur `isole`, lui,
serait un bug -- et c'est celui que ce probe garde.

CONTRE-EPREUVE (port, memes etats) : le registre `PLAYBOOKS` ampute de 1061 -- c'est-a-dire le
port d'AVANT #572-r2, qui retombait sur le fallback Comparable.

ORACLE = `aiDryRunAllUnits` (`CalculateNextActionForUnit`, read-only, `mutated=false` verifie).

ASCII only (cp1252). Usage (depuis scripts/python, session Frida chaude) :
    python probe_572r2_unbreakable_duty_decision.py [--seed 57202] [--board MC1_67] [--garder]
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

UNBREAKABLE_DUTY = 1061
CASTER = "templAncient"
FIGURANT = "templChampion"     # allie de remplissage -- vivant, donc SANS effet sur le terme `morts`
FOE = "tauCrisis"
BOARD = "MC1_67"
RANK = 17

#: Le caster est au centre ; l'ennemi a DISTANCE 2 (= `constants.range` de 1061), donc castable
#: dans les DEUX bras -- une abstention ne peut alors venir que du gate.
POS_CASTER = (3, 4)
POS_FOE = (5, 4)
#: Bras `isole` : l'unique allie est a distance 3 (hors du disque de rayon 2).
POS_LOIN = (0, 2)
#: Bras `entoure` : QUATRE tuiles de l'anneau 1 autour de (3,4) -- le plafond de 5 spawns joueur de
#: MC1_67 (caster compris). Toutes sont a distance 1 <= `range` = 2, centre exclu.
POS_PROCHES = [(2, 3), (3, 3), (3, 5), (4, 3)]
#: `10 * 4 allies = 40` -> `0 < prob < 1` -> le natif TIRE (cf. l'en-tete).
PCT_ATTENDU_ENTOURE = 40
#: Nombre de dry-runs par bras. `isole` doit rendre 0 cast sur les N ; `entoure` au moins 1.
N_TIRAGES = 12


def _tile(p):
    return "%d,%d" % (p[0], p[1])


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def build(state_file: str, seed: int, board: str, allies: list):
    """`allies` = positions des figurants ALLIES (hors caster). Le reste du montage est fixe."""
    argv = ["build", "--seed", str(seed), "--board", board, "--rank", str(RANK),
            "--p-units", ",".join([CASTER] + [FIGURANT] * len(allies)),
            "--a-units", FOE,
            "--no-ai",
            "--place", "%s:%s" % (CASTER, _tile(POS_CASTER)),
            "--a-place", "%s:%s" % (FOE, _tile(POS_FOE)),
            "--state-file", state_file]
    for p in allies:
        argv += ["--place", "%s:%s" % (FIGURANT, _tile(p))]
    p = _duel(argv)
    if p.returncode != 0 or not os.path.exists(state_file):
        print("[build] rc=%s\n%s\n%s" % (p.returncode, (p.stdout or "")[-1800:],
                                         (p.stderr or "")[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def _par_position(sid, rid):
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[(p.get("col"), p.get("row"))] = u
    return out, dv


def assert_montage(par_pos, allies: list):
    """Un montage DEGENERE rendrait le verdict trivial : on echoue AVANT de mesurer."""
    u = par_pos.get(POS_CASTER)
    if u is None or u.get("visualId") != CASTER:
        raise SystemExit("caster ABSENT de %r (vu %r)" % (POS_CASTER, (u or {}).get("visualId")))
    f = par_pos.get(POS_FOE)
    if f is None or f.get("visualId") != FOE:
        raise SystemExit("ennemi ABSENT de %r (vu %r)" % (POS_FOE, (f or {}).get("visualId")))
    manquants = [p for p in allies
                 if (par_pos.get(p) or {}).get("visualId") != FIGURANT]
    if manquants:
        raise SystemExit("allies NON PLACES : %r -- le compte du gate serait FAUX" % (manquants,))
    return u["id"], f["id"]


def _port_sans_playbook(sid, rid, uid):
    """CONTRE-EPREUVE : le port d'AVANT #572-r2 -- 1061 retiree du registre NonComparable, donc
    traitee par le fallback Comparable."""
    from engine.playbook import noncomparable as NC
    ancien = NC.PLAYBOOKS.pop(UNBREAKABLE_DUTY, None)
    try:
        return port_proposal(sid, rid, uid)
    finally:
        if ancien is not None:
            NC.PLAYBOOKS[UNBREAKABLE_DUTY] = ancien


def _pct_du_port(sid, rid, uid):
    """`GetUseProbability` du PORT, en pourcents -- le DIAGNOSTIC par etage (pas l'oracle) : un
    verdict binaire ne dirait pas LEQUEL des trois termes a mordu."""
    from probe_119_supreme_commander_decision import port_gates  # noqa: F401  (meme montage NC)
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine import weights
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: r(sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: r(sid, m, b, t), rid, dv, mov_by_unit, uid,
                      weights.load(), predictor)
    nc = PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, wt=c.wt, obs_units=c.obs_units, units=c.units,
        ability_targets=c.ability_targets)
    pb = PB.PLAYBOOKS[UNBREAKABLE_DUTY]
    return pb.use_probability_pct(nc), [x.get("target") for x in pb.generate_candidates(nc)]


def confronte(tag, sid, rid, uid, attendu_cast: bool):
    """`attendu_cast = False` -> le natif ne doit JAMAIS proposer 1061 (0 sur `N_TIRAGES`).
    `attendu_cast = True`  -> il doit le proposer AU MOINS UNE FOIS (le gate laisse passer)."""
    tirages = []
    for _ in range(N_TIRAGES):
        nat = native_proposal(sid, rid, uid)
        tirages.append(nat)
        if (nat["ability"] == UNBREAKABLE_DUTY) is attendu_cast and attendu_cast:
            break                     # existence ETABLIE : inutile de retirer
    nat = tirages[-1]
    casts = sum(1 for t in tirages if t["ability"] == UNBREAKABLE_DUTY)
    port = port_proposal(sid, rid, uid)
    sans = _port_sans_playbook(sid, rid, uid)
    pct, cands = _pct_du_port(sid, rid, uid)
    nat_cast = casts > 0
    port_cast = port.get("kind") == "ability" and port.get("ability") == UNBREAKABLE_DUTY
    ok = (nat_cast == attendu_cast) and (port_cast == nat_cast)
    # La CIBLE ne se confronte que quand les deux castent -- et le natif TIRE, donc son dernier
    # tirage peut ne pas etre celui ou il a caste. On compare a la cible du tirage QUI A CASTE.
    nat_tgt = next((t["target"] for t in tirages if t["ability"] == UNBREAKABLE_DUTY), None)
    meme_cible = (nat_tgt is None or not port_cast or nat_tgt == port.get("target"))
    ok = ok and meme_cible
    print("[%s] u%s  NATIF(%d cast(s) de 1061 sur %d tirage(s) ; cible du cast=u%s)  "
          "PORT(%s ab=%s tgt=u%s)  SANS_PLAYBOOK(%s ab=%s)"
          % (tag, uid, casts, len(tirages), nat_tgt, port.get("kind"),
             port.get("ability"), port.get("target"), sans.get("kind"), sans.get("ability")))
    print("       GetUseProbability du PORT = %d%% ; candidats du playbook = %r ; cast de 1061 "
          "ATTENDU = %s -> %s" % (pct, cands, attendu_cast, "OK" if ok else "DESACCORD"))
    return {"tag": tag, "natif": nat, "natif_target": nat_tgt, "casts": casts,
            "tirages": len(tirages), "port": port, "sans_playbook": sans, "pct": pct,
            "candidats": cands, "attendu_cast": attendu_cast, "ok": ok}


def campagne(sid, sf, seed, board, garder=False):
    """Les DEUX bras, chacun sur SON runner (les rosters different). FOYER UNIQUE du montage et
    des criteres : `main` et la garde `test_572_unbreakable_duty_live.py` passent par ici."""
    recs = []
    for tag, allies, attendu, pct_min in (("isole", [POS_LOIN], False, 0),
                                          ("entoure", POS_PROCHES, True, PCT_ATTENDU_ENTOURE)):
        sfx = sf.replace(".json", "_%s.json" % tag)
        rid = build(sfx, seed, board, allies)
        if rid is None:
            print("[572r2] BUILD KO (%s)" % tag)
            return recs
        try:
            par_pos, _dv = _par_position(sid, rid)
            uid, _fid = assert_montage(par_pos, allies)
            print("[572r2] %s : runner=%s  caster=u%s@%s  %d allie(s)"
                  % (tag, rid, uid, POS_CASTER, len(allies)))
            rec = confronte(tag, sid, rid, uid, attendu)
            if rec["pct"] < pct_min:
                raise SystemExit("[572r2] %s : le port mesure %d%% < %d%% attendu -- le montage "
                                 "n'atteint PAS le regime deterministe, aucune mesure"
                                 % (tag, rec["pct"], pct_min))
            recs.append(rec)
        finally:
            if not garder:
                _duel(["dispose", "--state-file", sfx, "--runner", str(rid)], timeout=120)
    return recs


def verdict(recs) -> bool:
    """`True` ssi les DEUX bras concordent ET la contre-epreuve MORD sur `isole`."""
    if len(recs) < 2:
        print("[572r2] montage sterile : %d bras sur 2" % len(recs))
        return False
    ok = all(rec["ok"] for rec in recs)
    ent = next((rec for rec in recs if rec["tag"] == "entoure"), None)
    if ent is not None:
        # La morsure se lit sur `entoure` : c'est LA que le port neuf propose 1061 et que le port
        # d'avant (fallback Comparable) ne le proposait pas. Sur `isole` les deux s'abstiennent --
        # l'accord y est REEL mais NON attribuable, et le dire est le resultat.
        mord = ent["sans_playbook"].get("ability") != ent["port"].get("ability")
        print("[572r2] contre-epreuve `sans playbook 1061` (bras entoure) : %s"
              % ("MORD (ab=%s au lieu de ab=%s)" % (ent["sans_playbook"].get("ability"),
                                                    ent["port"].get("ability")) if mord
                 else "NON DISCRIMINANTE -- le fallback Comparable proposait deja 1061"))
        ok = ok and mord
    iso = next((rec for rec in recs if rec["tag"] == "isole"), None)
    if iso is not None and iso["sans_playbook"].get("ability") == iso["port"].get("ability"):
        print("[572r2] NOTE : sur `isole`, le port d'AVANT s'abstenait DEJA (fallback Comparable "
              "ab=%s) -- l'accord y est reel mais N'ATTRIBUE rien au gate."
              % (iso["sans_playbook"].get("ability"),))
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Face DECISION de 1061 -- le gate GetUseProbability")
    ap.add_argument("--seed", type=int, default=57202)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    sf = a.state_file or str(PYDIR.parents[1] / "logs" / ("probe572r2_%d.json" % os.getpid()))
    recs = campagne(sid, sf, a.seed, a.board, garder=a.garder)
    ok = verdict(recs)
    print("[572r2] VERDICT : %s" % ("OK" if ok else "DESACCORD"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
