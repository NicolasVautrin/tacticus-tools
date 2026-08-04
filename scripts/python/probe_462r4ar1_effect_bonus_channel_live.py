"""#462-r4a-r1 -- CONFRONTATION du capteur `effect-bonus-trace` (#466), par FACE et par CANAL.

LE CRITERE, pose AVANT la methode
---------------------------------
`#462-r4a` a etabli PAR LA MESURE (six regimes) que la %-list d'un EFFET se compose SANS arrondi
intercale, donc qu'elle ne traverse PAS l'etage `Multiplier@0x30`. Le decompile de
`IdunBattle.Core.Services.DamageModifiers$$Add(this, damageBonus, modifier)` le corrobore : le
`Multiplier` n'est touche QUE par l'argument `modifier`, un POURCENTAGE part dans la liste capee
`@0x18`. Mais « ce que la fabrique produit » ne dit rien sans « ou l'appelant le verse » -- le
MEME `DamageBonus` peut alimenter les deux canaux selon l'appelant. Aucune lecture statique ne
referme ce noeud : il faut voir les deux SUR LE MEME EVENEMENT.

Question binaire : sur l'`Add` qui porte le `x0.70` de `Terrifying`,
`cappedAfter == cappedBefore + 1` **et** `multAfter == multBefore` ?

REGIME NON DEGENERE -- ce qui rend la mesure discriminante. Le montage `--two-faces` de
`probe_462_r4a_terrifying_rounding.py` est le SEUL ou les deux faces sont non neutres :
elevation `x1.50` cote ATTAQUANT et `Terrifying` `x0.70` cote DEFENSEUR, sur le meme coup. Un
montage a UNE seule face laisserait l'attribution de face indiscernable (n'importe quelle
etiquette collerait), et un montage sans effet ne testerait aucun canal. La preuve que le regime
sort du degenere se lit dans la sortie : DEUX `Add` de pourcentage, de SIGNES OPPOSES
(`-30` et `+50`), sur DEUX faces distinctes.

CE QUE CHAQUE CRAN TRANCHE : cf. `docs/rl/case-462-r4a-canal-du-multiplicateur.md` §8.4.

ANCRAGE DE LA CAPTURE. On arme la trace autour du SEUL appel `aiPlaybookPredict` (monkeypatch du
`_r` du probe hote), pas autour de tout le montage : les `applyAction move` du placement font
tirer des predictions de deplacement dont les `Add` bruiteraient la lecture, et le budget est
partage. La capture est donc exactement la fenetre du coup mesure.

Usage (session warmee) :
    python probe_462r4ar1_effect_bonus_channel_live.py
    python probe_462r4ar1_effect_bonus_channel_live.py --budget 4000 --dump-raw
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))


def _nullable(nb) -> "tuple[bool, int] | None":
    """Interprete un `Nullable<int>` publie DANS LES DEUX ORDRES DE CHAMP.

    Le capteur ne tranche pas a l'aveugle : il publie `{hv0, v4}` (has_value en tete) ET
    `{hv4, v0}` (valeur en tete). Ce depot documente les deux layouts, donc l'arbitrage se fait
    ici, sur le SEUL ordre dont le drapeau est un booleen valide (0/1). Si les deux sont valides
    et non nuls, on rend `None` -- ambigu, jamais une valeur devinee."""
    if not isinstance(nb, dict):
        return None
    cands = []
    if nb.get("hv0") in (0, 1):
        cands.append((bool(nb["hv0"]), int(nb.get("v4") or 0), "hv_first"))
    if nb.get("hv4") in (0, 1):
        cands.append((bool(nb["hv4"]), int(nb.get("v0") or 0), "v_first"))
    actifs = [c for c in cands if c[0]]
    if len(actifs) == 1:
        return actifs[0][0], actifs[0][1]
    if not actifs and cands:
        return False, 0
    return None


def _pct_of(ev: dict) -> "int | None":
    r = _nullable(ev.get("pct"))
    if r is None or not r[0]:
        return None
    return r[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--dump-raw", action="store_true")
    a = ap.parse_args()

    import probe_462_r4a_terrifying_rounding as P
    from rl_collect_batch import _resolve_session

    sid = _resolve_session()
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    bad = 0
    print("== #462-r4a-r1 -- confrontation du capteur `effect-bonus-trace` (session %s)" % sid)

    # ---- cran 0 : le LAYOUT. A lire AVANT tout le reste : un offset faux invaliderait toutes
    #      les valeurs interpretees des crans 1-5 (les `rawHex`, eux, resteraient exploitables).
    lay = P._r(sid, "effectBonusTraceLayout", {}, 60) or {}
    print("\n[0] effectBonusTraceLayout")
    if not lay.get("ok"):
        print("    KO: %s" % json.dumps(lay)[:300])
        bad += 1
    (LOGSDIR / "p462r4ar1_layout.json").write_text(json.dumps(lay, indent=1), encoding="utf-8")
    for ent in (lay.get("layouts") or lay.get("classes") or []):
        if not isinstance(ent, dict):
            continue
        print("    %s" % (ent.get("cls") or ent.get("name")))
        for f in (ent.get("fields") or []):
            print("       %-24s @0x%02x  %s" % (f.get("name"), f.get("offset"), f.get("type")))
    chain = lay.get("damageModifierAbilityEffectChain") or lay.get("chain")
    print("    chaine d'heritage DamageModifierAbilityEffect : %s" % chain)

    # ---- capture ARMEE autour du seul `aiPlaybookPredict` du coup mesure.
    capture: dict = {}
    _orig_r = P._r

    def _r_traced(sid_, method, body, timeout=60):
        if method != "aiPlaybookPredict" or capture.get("done"):
            return _orig_r(sid_, method, body, timeout)
        rid = (body or {}).get("runnerId")
        on = _orig_r(sid_, "effectBonusTraceOn", {"budget": a.budget}, 60)
        _orig_r(sid_, "effectBonusTraceClear", {}, 60)
        try:
            out = _orig_r(sid_, method, body, timeout)
        finally:
            dump = _orig_r(sid_, "effectBonusTraceDump", {"runnerId": rid}, 120)
            _orig_r(sid_, "effectBonusTraceOff", {}, 60)
        capture["on"] = on
        capture["dump"] = dump
        capture["runnerId"] = rid
        capture["done"] = True
        return out

    P._r = _r_traced
    state = LOGSDIR / ("p462r4ar1_2f_%s.json" % uuid.uuid4().hex[:8])
    try:
        row = P.two_faces(state_file=str(state), verbose=True)
    finally:
        P._r = _orig_r
    print("\n[montage] natif MIN/MAX = %s / %s ; port = %s / %s"
          % (row.get("native_min"), row.get("native_max"),
             row.get("port_min"), row.get("port_max")))
    print("          modsATT=%s  modsDEF=%s" % (row.get("att_pct"), row.get("def_pct")))

    on = capture.get("on") or {}
    dump = capture.get("dump") or {}
    print("\n[armement] %s" % json.dumps(on)[:300])
    if a.dump_raw:
        (LOGSDIR / "p462r4ar1_dump.json").write_text(json.dumps(dump, indent=1), encoding="utf-8")
    adds = dump.get("adds") or []
    facto = dump.get("factory") or []
    print("[capture] adds=%d  factory=%d  spent=%s/%s"
          % (len(adds), len(facto), dump.get("spent"), dump.get("budget")))
    if not adds:
        print("    ECART: AUCUN `Add` capte -- le canal ne transporte rien sur ce chemin.")
        bad += 1

    # ---- cran 1 : chaque `Add` porte-t-il une FACE ?
    sans_face = [e for e in adds if e.get("face") in (None, "")]
    print("\n[1] `Add` sans face : %d / %d" % (len(sans_face), len(adds)))
    faces = {}
    for e in adds:
        faces[e.get("face")] = faces.get(e.get("face"), 0) + 1
    print("    repartition par face : %s" % faces)
    if adds and len(sans_face) == len(adds):
        print("    ECART: face `null` en MASSE -> le chemin emprunte n'est pas"
              " `Calculate*ModifiersForPrediction` ; c'est une information, pas une panne.")
        bad += 1

    # ---- crans 2/3/4 : les DEUX `Add` de pourcentage, de signes OPPOSES.
    pcts = [(e, _pct_of(e)) for e in adds]
    pcts = [(e, v) for (e, v) in pcts if v is not None]
    print("\n[2/3/4] `Add` portant un POURCENTAGE : %d" % len(pcts))
    vus = {}
    for (e, v) in pcts:
        dcap = (e.get("cappedAfter") or 0) - (e.get("cappedBefore") or 0)
        dmul = "IDENTIQUE" if e.get("multAfter") == e.get("multBefore") else "CHANGE"
        print("    seq=%-4s face=%-9s overload=%s pct=%+d  capped %s->%s (d=%+d)  mult %s->%s [%s]"
              % (e.get("seq"), e.get("face"), e.get("overload"), v,
                 e.get("cappedBefore"), e.get("cappedAfter"), dcap,
                 e.get("multBefore"), e.get("multAfter"), dmul))
        vus[v] = (e, dcap, dmul)

    def _cran(label, pct_attendu, face_attendue):
        nonlocal bad
        got = vus.get(pct_attendu)
        if got is None:
            print("    [%s] ECART: aucun `Add` avec pct=%+d" % (label, pct_attendu))
            bad += 1
            return
        e, dcap, dmul = got
        ok_cap = dcap == 1
        ok_mul = dmul == "IDENTIQUE"
        ok_face = e.get("face") == face_attendue
        print("    [%s] pct=%+d : cappedAfter==cappedBefore+1 %s | multAfter==multBefore %s |"
              " face==%s %s (lue: %s)"
              % (label, pct_attendu, "OUI" if ok_cap else "NON",
                 "OUI" if ok_mul else "NON", face_attendue,
                 "OUI" if ok_face else "NON", e.get("face")))
        bad += 0 if (ok_cap and ok_mul and ok_face) else 1

    _cran("2/3 Terrifying x0.70", -30, "defender")
    _cran("4   elevation x1.50", 50, "attacker")

    # Le regime n'est NON DEGENERE que si les deux pourcentages de signes opposes sont la, sur
    # deux faces distinctes : un seul terme contributeur rendrait n'importe quelle etiquette de
    # face compatible avec la mesure.
    signes = sorted(v for v in vus)
    faces_pct = {vus[v][0].get("face") for v in vus}
    non_deg = (-30 in vus) and (50 in vus) and len(faces_pct) >= 2
    print("\n    regime NON DEGENERE : %s (pourcentages vus=%s, faces distinctes=%s)"
          % ("OUI" if non_deg else "NON", signes, sorted(str(f) for f in faces_pct)))
    if not non_deg:
        bad += 1

    # ---- cran 5 : la surcharge 1 (`Add(modifier)`), le canal MULTIPLICATEUR sec.
    ov1 = [e for e in adds if e.get("overload") == 1]
    print("\n[5] `Add(modifier)` (surcharge 1) : %d evenement(s)" % len(ov1))
    for e in ov1[:8]:
        print("    seq=%-4s face=%-9s mult %s->%s  modifierValue=%s"
              % (e.get("seq"), e.get("face"), e.get("multBefore"), e.get("multAfter"),
                 e.get("modifierValue")))
    if not ov1:
        print("    -> ABSENTE sur ce montage : aucun stat-mod n'y participe (attendu -- le"
              " montage `T` tuile Thorns n'est pas joue ici). Residu NON CONFRONTE, nomme.")

    # ---- cran 6 : la FABRIQUE tire-t-elle ?
    print("\n[6] evenements de FABRIQUE (`CreateEffectDamageBonusForAttack`) : %d" % len(facto))
    for e in facto[:8]:
        print("    seq=%-4s effet=%s" % (e.get("seq"), e.get("effectClass") or e.get("cls")))
    if not facto:
        print("    -> NE TIRE PAS. Ce n'est PAS un echec : le symbole hooke est le FORWARDER de"
              " la classe de base, et l'effet mesure a un corps propre. L'ancrage 3"
              " (`DamageModifiers$$Add`) a deja tranche, et lui voit TOUS les effets.")

    print("\nVERDICT: %s (%d ecart(s))" % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
