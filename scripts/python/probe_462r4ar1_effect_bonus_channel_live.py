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
    ap.add_argument("--wide", action="store_true",
                    help="arme sur TOUT le montage (moves compris) et joue en plus une VRAIE "
                         "attaque avant de disposer -- discrimine « le hook ne mord jamais » de "
                         "« le chemin de PREDICTION n'est pas celui qui est ancre »")
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

    # ---- capture ARMEE autour du seul `aiPlaybookPredict` du coup mesure (mode par defaut),
    #      ou sur TOUT le montage plus une vraie attaque (`--wide`).
    capture: dict = {}
    _orig_r = P._r

    def _r_narrow(sid_, method, body, timeout=60):
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
        capture.update({"on": on, "dump": dump, "runnerId": rid, "done": True})
        return out

    def _r_wide(sid_, method, body, timeout=60):
        """Capte TOUT, et joue une VRAIE attaque juste avant le `disposeRunner` du montage.

        Le montage hote ne joue AUCUNE attaque native : il compare `aiPlaybookPredict` a un
        REPLAY offline. Le chemin COMBAT natif n'est donc jamais emprunte -- et c'est justement
        l'une des deux lectures a departager quand la prediction ne rend rien."""
        if method == "aiPlaybookPredict":
            capture["pred_body"] = dict(body or {})
            capture["snap_pred"] = _orig_r(sid_, "effectBonusTraceDump",
                                           {"runnerId": (body or {}).get("runnerId")}, 120)
            out = _orig_r(sid_, method, body, timeout)
            capture["apres_pred"] = _orig_r(sid_, "effectBonusTraceDump",
                                            {"runnerId": (body or {}).get("runnerId")}, 120)
            return out
        if method == "disposeRunner" and not capture.get("done"):
            rid = (body or {}).get("runnerId")
            pb = capture.get("pred_body") or {}
            if pb.get("unitId") is not None:
                act = {"kind": "ability", "casterId": pb["unitId"],
                       "targetId": pb["targetId"], "abilityType": pb["abilityType"]}
                capture["attack"] = _orig_r(sid_, "applyAction",
                                            {"runnerId": rid, "action": act}, 120)
            capture["dump"] = _orig_r(sid_, "effectBonusTraceDump", {"runnerId": rid}, 120)
            _orig_r(sid_, "effectBonusTraceOff", {}, 60)
            capture["runnerId"] = rid
            capture["done"] = True
        return _orig_r(sid_, method, body, timeout)

    if a.wide:
        capture["on"] = _orig_r(sid, "effectBonusTraceOn", {"budget": a.budget}, 60)
        _orig_r(sid, "effectBonusTraceClear", {}, 60)
    P._r = _r_wide if a.wide else _r_narrow
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
    if a.wide:
        av = capture.get("snap_pred") or {}
        ap_ = capture.get("apres_pred") or {}
        print("[wide] AVANT la prediction : adds=%d factory=%d"
              % (len(av.get("adds") or []), len(av.get("factory") or [])))
        print("[wide] APRES la prediction : adds=%d factory=%d"
              % (len(ap_.get("adds") or []), len(ap_.get("factory") or [])))
        atk = capture.get("attack") or {}
        print("[wide] attaque REELLE jouee : ok=%s mutated=%s%s"
              % (atk.get("ok"), atk.get("mutated"),
                 ("  err=" + str(atk.get("error"))) if atk.get("error") else ""))
        print("[wide] APRES l'attaque reelle : adds=%d factory=%d" % (len(adds), len(facto)))
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
    # Une face a ZERO evenement est AMBIGUE tant qu'on ne sait pas si son hook est POSE. Les
    # deux champs qui la desambiguisent (`facesPosed`, `faceEnters`) sont livres avec la
    # correction du capteur ; tant qu'ils sont absents du bundle CHARGE, on le DIT.
    fp, fe = dump.get("facesPosed"), dump.get("faceEnters")
    print("    facesPosed = %s" % ("NON PUBLIE (bundle anterieur au correctif)"
                                   if fp is None else json.dumps(fp)))
    print("    faceEnters = %s" % ("NON PUBLIE (bundle anterieur au correctif)"
                                   if fe is None else json.dumps(fe)))
    absentes = [f for f in ("attacker", "defender") if not faces.get(f)]
    if absentes and fe is None:
        print("    INDECIDABLE: face(s) %s a ZERO evenement, et le capteur ne publie ni les"
              " hooks poses ni le compte d'entrees par fenetre -> impossible de separer"
              " « fenetre non traversee » de « hook non pose ». NON CONFRONTE." % absentes)

    # ---- pourcentages portes par le `DamageBonus` lui-meme (champ `CapModifier`, alias `pct`).
    pcts = [(e, _pct_of(e)) for e in adds]
    pcts = [(e, v) for (e, v) in pcts if v is not None]
    print("\n[pct] `Add` dont le `DamageBonus` porte un POURCENTAGE CAPE : %d" % len(pcts))
    vus = {}
    for (e, v) in pcts[:12]:
        dcap = (e.get("cappedAfter") or 0) - (e.get("cappedBefore") or 0)
        dmul = "IDENTIQUE" if e.get("multAfter") == e.get("multBefore") else "CHANGE"
        print("    seq=%-4s face=%-9s overload=%s pct=%+d  capped %s->%s (d=%+d)  mult %s->%s [%s]"
              % (e.get("seq"), e.get("face"), e.get("overload"), v,
                 e.get("cappedBefore"), e.get("cappedAfter"), dcap,
                 e.get("multBefore"), e.get("multAfter"), dmul))
        vus[v] = (e, dcap, dmul)
    if not pcts:
        print("    AUCUN. Le residu `#446-r2-r1` (« aucun EffectBonus porte ne pose de cap »)"
              " se verifie donc AUSSI cote natif : la liste capee n'est alimentee par aucun"
              " chemin de ce montage.")

    # ---- cran 5 : la surcharge 1 (`Add(modifier)`), le canal MULTIPLICATEUR sec. C'est PAR
    #      ELLE que le montage repond, et non par le champ `pct` : le decompile de la surcharge
    #      2 DELEGUE (`if (modifier.HasValue) Add(this, modifier.Value)`), donc tout
    #      multiplicateur reellement applique passe par un evenement de surcharge 1.
    ov1 = [e for e in adds if e.get("overload") == 1]
    print("\n[5] `Add(modifier)` (surcharge 1, canal MULTIPLICATEUR sec) : %d evenement(s)"
          % len(ov1))
    par_val = {}
    for e in ov1:
        mv = e.get("modifierValue")
        if isinstance(mv, (int, float)):
            par_val.setdefault(round(mv, 6), []).append(e)
    for v in sorted(par_val):
        e = par_val[v][0]
        print("    modifierValue=%-22s x%-3d  ex. seq=%s face=%s  mult %s -> %s"
              % (v, len(par_val[v]), e.get("seq"), e.get("face"),
                 e.get("multBefore"), e.get("multAfter")))

    # ---- coherence interne : `multAfter == multBefore * modifierValue`. C'est ce qui prouve
    #      que l'offset `Multiplier` est LU JUSTE -- sans elle, une valeur plausible mais lue
    #      au mauvais offset serait indiscernable d'une mesure.
    coh = incoh = 0
    for e in ov1:
        mb, ma, mv = e.get("multBefore"), e.get("multAfter"), e.get("modifierValue")
        if not all(isinstance(x, (int, float)) for x in (mb, ma, mv)):
            continue
        if abs(mb * mv - ma) < 1e-9:
            coh += 1
        else:
            incoh += 1
    print("    coherence multAfter == multBefore * modifierValue : %d OK / %d KO"
          % (coh, incoh))
    if incoh or not coh:
        print("    ECART: l'offset `Multiplier` n'est pas lu juste -- rien d'autre"
              " n'est interpretable.")
        bad += 1

    # ---- crans 2/3/4 : LE cran. L'attendu du plan est `cappedAfter == cappedBefore + 1` ET
    #      `multAfter == multBefore`. On le CONFRONTE, on ne le presuppose pas.
    grossi = [e for e in adds
              if isinstance(e.get("cappedAfter"), int) and isinstance(e.get("cappedBefore"), int)
              and e["cappedAfter"] > e["cappedBefore"]]
    print("\n[2/3/4] LE cran -- la liste CAPEE a-t-elle grossi ? %d evenement(s) sur %d"
          % (len(grossi), len(adds)))
    bouge_mult = [e for e in adds if e.get("multAfter") != e.get("multBefore")]
    print("        le MULTIPLICATEUR a-t-il bouge ? %d evenement(s) sur %d"
          % (len(bouge_mult), len(adds)))
    print("        ATTENDU (plan §8.4 cran 2) : capped +1 et mult INCHANGE.")
    if adds and not grossi and bouge_mult:
        print("        OBTENU : l'INVERSE -- capped JAMAIS touchee, mult modifie."
              " => les pourcentages de ce montage passent par le canal MULTIPLICATEUR,"
              " pas par la liste capee. Le plan dit que cet ecart REFUTE la lecture (a).")

    # ---- REGIME NON DEGENERE : il faut DEUX multiplicateurs DISTINCTS composes dans le MEME
    #      accumulateur. Un seul terme contributeur rendrait la mesure compatible avec
    #      n'importe quel modele de composition -- c'est le piege du vert qui ne prouve rien.
    par_accum = {}
    for e in ov1:
        par_accum.setdefault(e.get("accum"), []).append(e)
    compo = []
    for acc, evs in par_accum.items():
        vals = {round(e.get("modifierValue"), 6) for e in evs
                if isinstance(e.get("modifierValue"), (int, float))}
        chaines = [e for e in evs if e.get("multBefore") not in (1, 1.0)]
        if len(vals) >= 2 and chaines:
            compo.append((acc, sorted(vals), len(evs)))
    print("\n    REGIME NON DEGENERE : accumulateurs ou DEUX multiplicateurs distincts se"
          " composent : %d" % len(compo))
    for (acc, vals, n) in compo[:4]:
        print("        accum=%s  valeurs=%s  (%d evenements)" % (acc, vals, n))
    non_deg = bool(compo)
    if not non_deg:
        print("        ECART: un seul terme contributeur -- accord DEGENERE, la mesure ne"
              " discrimine aucun modele de composition.")
        bad += 1

    # ---- cran 6 : la FABRIQUE tire-t-elle ?
    print("\n[6] evenements de FABRIQUE (`CreateEffectDamageBonusForAttack`) : %d" % len(facto))
    for e in facto[:8]:
        print("    seq=%-4s effet=%s" % (e.get("seq"), e.get("effectClass") or e.get("cls")))
    if not facto:
        print("    -> NE TIRE PAS. Ce n'est PAS un echec : le symbole hooke est le FORWARDER de"
              " la classe de base, et l'effet mesure a un corps propre (107 corps concrets"
              " partagent ce nom). L'ancrage 3 (`DamageModifiers$$Add`) a deja tranche, et lui"
              " voit TOUS les effets. Trou NOMME d'avance par l'auteur du capteur (§8.2).")

    # ---- VERDICT. Le critere n'est PAS « les attendus du plan sont satisfaits » -- un plan
    # peut etre refute, et c'est un resultat. Le critere est : le capteur a-t-il rendu une
    # valeur qui DISCRIMINE ? Trois conditions, toutes necessaires :
    #   * il a transporte quelque chose (des evenements) ;
    #   * ce qu'il transporte est lu JUSTE (coherence multiplicative verifiee) ;
    #   * le regime n'est pas degenere (deux termes se composent, donc les modeles se separent).
    print("\n== CRITERE (canal muet vs canal absent vs canal qui DISCRIMINE)")
    c1 = bool(adds)
    c2 = coh > 0 and incoh == 0
    c3 = non_deg
    print("   transporte des evenements ............ %s (%d)" % ("OUI" if c1 else "NON", len(adds)))
    print("   lu juste (coherence multiplicative) .. %s (%d OK / %d KO)"
          % ("OUI" if c2 else "NON", coh, incoh))
    print("   regime NON degenere .................. %s" % ("OUI" if c3 else "NON"))
    ok = c1 and c2 and c3 and bad == 0
    print("\nVERDICT: %s (%d ecart(s) de capteur)" % ("PASS" if ok else "FAIL", bad))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
