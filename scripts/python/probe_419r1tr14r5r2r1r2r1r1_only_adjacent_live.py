"""probe #419-r1-tr14-r5-r2-r1-r2-r1-r1 (LIVE) -- le gate d'adjacence sur une portee NON OBSERVABLE.

QUESTION BINAIRE
    Sur un caster dont la portee d'arme n'est pas observable et dont `only_adjacent` est VRAI, le
    port NOMME-t-il la meme regle que le natif sur une cible NON adjacente ?

    natif            `TargetIsInRange` (0x8000000) -- la branche `range.OnlyAdjacent` du volet portee
    port AVANT       aucun refus de portee (`get_range` rendait `None`), donc la cascade CONTINUE et
                     le refus tombe plus loin (`TargetMatchesDynamicRule`) ou pas du tout
    port APRES       `TargetIsInRange`

    CE QUI M'AURAIT FAIT CONCLURE L'INVERSE : `0x0` cote natif sur ces lignes (le natif desarmerait
    lui aussi), ou un `TargetMatchesDynamicRule` natif (le gate de portee ne mordrait pas ici).

MONTAGE -- CELUI DE #419-r1-tr14-r5-r2-r1-r2-r1, REUTILISE TEL QUEL
    `genesPrimus` -> `CultDemagogue` (1179) invoque `genesSmnDecoy` (`weapons = []` AU KIT **et**
    `Weapons = []` dans `BC.Units` : substrats CONCORDANTS) et `genesSmnNeophyte` (ARME, temoin).
    Geometrie PILOTEE : on amene l'ancre au contact AVANT de caster, les summons apparaissent autour
    d'elle -- donc un spectre de distances `d = 1, 2, ...` sur les memes ennemis.

    Le gisement de CETTE tranche est l'inverse de celui de la precedente : les lignes `d >= 2` du
    caster SANS ARME, la ou #...-r1 mesurait la ligne `d = 1`.

    ⚠ `genesSmnDecoy` est dans le RAYON REEL chiffre hors ligne
    (`probe_419r1tr14r5r2r1r2r1r1_range_only_adjacent.py` : 57 porteurs, tous sur l'attaque normale
    generique `69`) -- ce n'est donc pas un cas de bord fabrique pour l'occasion.

LA BASELINE, ET POURQUOI ELLE EST EXACTE
    `_avant_r1r1` = `get_range(...)` puis `None if rr.value is None else rr`. C'est LITTERALEMENT le
    corps d'avant : l'ancien `get_range` sortait en `return None` exactement dans les deux cas ou le
    nouveau rend `value = None` (portee d'arme non observable, `OverrideRangeFunc`), et rendait le
    MEME `Range` partout ailleurs. La substitution porte sur l'attribut de MODULE, que
    `get_range_broken_rule` resout au moment de l'appel.

VERDICT
    rc 0 si (a) le montage a mordu, (b) le port APRES est en accord avec le natif sur le CODE
    (la regle exacte) pour toutes les lignes du caster sans arme, (c) la BASELINE diverge sur au
    moins une ligne -- sinon regime DEGENERE --, et (d) le TEMOIN arme est inchange.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session, bind_ambient_rpc      # noqa: E402

import probe_247_splash_targeting as P247                                # noqa: E402
import probe_436_taunt_targeting as P436                                 # noqa: E402
import probe_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule as P583      # noqa: E402

from engine.runner.abilities import targeting as T                       # noqa: E402
from engine.runner.abilities.targeting import (                          # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE as OPTS,
    _NormalAttackTargeting, get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

GENERIC_TYPE = P583.GENERIC_TYPE
MontageError = P583.MontageError


#: La VRAIE fonction, capturee A L'IMPORT -- surtout pas relue depuis le module au moment de
#: l'appel : la substitution ci-dessous la remplace, et `_avant_r1r1` s'appellerait lui-meme.
_VRAI_GET_RANGE = T.get_range


def _avant_r1r1(state, caster_id, options):
    """`get_range` DANS SA FORME D'AVANT : `None` des que la portee numerique manque.

    ⚠ **CETTE BASELINE NE PEUT PAS SE DEFINIR PAR `rr.value is None`, ET C'EST UNE CORRECTION**
    (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1). Elle est RECONSTRUITE par-dessus le `get_range` COURANT :
    elle n'est donc fidele que tant que la frontiere du `None` courant ne bouge pas. Or elle a bouge
    deux fois -- les deux court-circuits (`casterTiles` vide, `UseWholeBoard`) rendent desormais un
    triplet DEFINI, et la branche `!HasAnyWeapon` lit `GetStat(caster, StatType.Range = 2)`. Sur le
    montage de cette tranche, dont le caster est justement SANS ARME, la baseline avait donc cesse
    de diverger : elle mesurait le port courant, pas l'ancien. C'est le vice « un changement de
    harnais perime les premisses d'un test », pris sur le fait.

    On enonce donc les QUATRE sorties `None` de l'ancien corps, sans dependre de la frontiere
    d'aujourd'hui : `TargetingRange` non RE-lu, caster sans tuile, `UseWholeBoard`, et portee
    numerique non observable -- cette derniere lue comme l'ancien corps la lisait, c'est-a-dire
    `unit_weapon_range` SEUL (il rend `None` sur `!HasAnyWeapon`, quel que soit le porteur de
    stats), jamais `GetStat`."""
    rng = getattr(options, "range", None)
    if rng is None or T._tile_of(state, caster_id) is None or rng.use_whole_board:
        return None
    rr = _VRAI_GET_RANGE(state, caster_id, options)
    if rr is None or rr.value is None:
        return None
    if rng.override_range is None and not rng.use_range_from_config:
        e = state.get_entity(int(caster_id))
        sc = e.get_component(T.StatsComponent) if e is not None else None
        if T.unit_weapon_range(T._visual_id(state, caster_id),
                               sc.ctx if sc is not None else None) is None:
            return None                               # branche `!HasAnyWeapon` de l'ANCIEN corps
    return rr


class _Substitue:
    """Substitue `targeting.get_range` le temps d'une mesure -- `get_range_broken_rule` le resout
    par le module, donc la substitution mord. Restauration GARANTIE (le module est partage)."""

    def __enter__(self):
        T.get_range = _avant_r1r1
        return self

    def __exit__(self, *exc):
        T.get_range = _VRAI_GET_RANGE
        return False


def _rows(sid, rid, st, dv, caster_u, aid: int = GENERIC_TYPE):
    """Une ligne par cible ENNEMIE vivante : natif, port APRES, port AVANT (`get_range` substitue)."""
    cid = int(caster_u["id"])
    ab = _NormalAttackTargeting(OPTS[aid])
    out = []
    for u in (dv.get("units") or []):
        if not u.get("alive") or int(u["id"]) == cid or u.get("owner") == caster_u.get("owner"):
            continue
        tid = int(u["id"])
        tr = (P247._nat(sid, rid, cid, aid, tid) or {}).get("targetReason") or {}
        after = int(get_invalid_target_reason(st, cid, tid, ab))
        with _Substitue():
            before = int(get_invalid_target_reason(st, cid, tid, ab))
        out.append({"tid": tid, "vis": u.get("visualId"),
                    "d": hexgeo.distance(P247._pos(caster_u), P247._pos(u)),
                    "nat": P247._hexval(tr), "after": after, "before": before})
    return out


def _print_rows(label, rows):
    print("\n  --- CASTER %s" % label)
    print("      %-5s %-16s %-3s %-12s %-12s %-12s" % ("id", "cible", "d", "natif", "portApres",
                                                       "portAvant"))
    for r in rows:
        mark = "   <- DISCRIMINANT" if r["after"] != r["before"] else ""
        print("      %-5d %-16s %-3d %-12s %-12s %-12s%s"
              % (r["tid"], r["vis"], r["d"], "?" if r["nat"] is None else hex(r["nat"]),
                 hex(r["after"]), hex(r["before"]), mark))


#: BRAS 2 -- l'ACTIVE dont la cascade `UnitFactory$$AddNormalAttackAbility` derive l'attaque normale
#: `1126 RogalDorn_NormalAttack`. Son masque est `0x4000` : il ne pose PAS `TargetMatchesDynamicRule`,
#: donc rien ne rattrape le refus en aval du volet portee. C'est ce qui rend ce bras discriminant sur
#: le VERDICT, la ou le bras `69` (masque `0x4002`) ne l'est que sur la CAUSE.
GRAFT_ACTIVE = "PoundThemToDust"
GRAFT_TYPE = 1126


def _build_bc(sid, seed, board, seed_bc):
    """`rl_duel build --seed-bc`, state-file PROPRE sous `logs/`. ATTEND si `MAX_RUNNERS` est sature
    (cap PARTAGE entre agents)."""
    import itertools
    import json
    import os
    import subprocess
    import time
    global _SEQ
    try:
        _SEQ
    except NameError:
        _SEQ = itertools.count(1)
    root = PYDIR.parent.parent
    state = root / "logs" / ("_probe419r5r2r1r2r1r1-%d-%d.json" % (os.getpid(), next(_SEQ)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--seed-bc", str(seed_bc), "--p-units", P583.P_UNITS, "--a-units", P583.A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-600:])
        time.sleep(10)


def run_greffe(sid, seed: str = "4192", board: str = "MC1_67", sans_canal: bool = False) -> dict:
    """BRAS 2 -- le MEME montage, `PoundThemToDust` greffee sur le summon SANS ARME.

    ⚠ La greffe porte sur `BC` (ce que lit le NATIF). Le port, lui, tire son type d'attaque normale
    du KIT gameconfig, donc il continuerait de dire `69` : c'est pourquoi le jeu d'options `1126` est
    passe EXPLICITEMENT aux deux modeles, et l'oracle natif interroge `abilityReason(cid, 1126, tid)`.
    On mesure ainsi le MEME jeu d'options des deux cotes, ce que la divergence des substrats
    (residu `#419-r1-tr14-r5-r2-r1-r2-r1-r2`) interdirait de faire par la voie implicite."""
    import json
    import subprocess
    import tempfile
    import catalog_inject
    bc = catalog_inject._load_seed(None)
    rep = catalog_inject.graft_active_ability(bc, P583.NOWEAPON_VIS, GRAFT_ACTIVE, replace=True)
    if sans_canal:
        catalog_inject.clear_declared_grafts()   # neutralise le refus : on veut le VERDICT d'avant
    tmp = Path(tempfile.mkdtemp()) / "seed-graft.json"
    tmp.write_text(json.dumps(bc), encoding="utf-8")
    print("=== BRAS 2 : %s.ActiveAbilities = [%s] (id %s, configAdded=%s)"
          % (P583.NOWEAPON_VIS, GRAFT_ACTIVE, rep["abilityId"], rep["configAdded"]))
    rid, state = _build_bc(sid, seed, board, str(tmp))
    try:
        for _ in range(P247.WARMUP_ENDTURNS):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
        P583._drive_and_summon(sid, rid)
        print("  contact force : %s"
              % P583.forcer_contact(sid, rid, vis_list=(P583.NOWEAPON_VIS,)))
        dv, payloads = P436._capture(sid, rid)
        st = P436._mk_state(payloads)
        nw = P583._pick_adjacent(dv, P583.NOWEAPON_VIS)
        if nw is None:
            raise MontageError("bras 2 : aucun `%s` vivant adjacent -> montage non pose"
                               % P583.NOWEAPON_VIS)
        got = P583._normal_attack_id(nw)
        print("  montage u%-4s %-18s attaque normale NATIVE = %s (attendu %d) -> %s"
              % (nw["id"], nw.get("visualId"), got, GRAFT_TYPE,
                 "MORD" if got == GRAFT_TYPE else "N'A PAS MORDU"))
        if got != GRAFT_TYPE:
            raise MontageError("la greffe n'a pas substitue l'attaque normale (%s != %d)"
                               % (got, GRAFT_TYPE))
        # LA VOIE IMPLICITE (#448-r3-r1-r1) -- ce que le PORT dit tout seul, sans qu'on lui souffle
        # `1126`. C'est le residu `#419-r1-tr14-r5-r2-r1-r2-r1-r2` (« divergence des substrats »),
        # que le contournement ci-dessus rend invisible aux lignes de mesure. Sans le canal
        # `unitAbilityStates` le port derive du gameconfig et dit `69` ; avec, il lit le kit
        # REELLEMENT monte et doit dire `1126`. Mesure IMPRIMEE, jamais supposee.
        from engine.runner.abilities.targeting import normal_attack_type_for
        implicite = normal_attack_type_for(st, int(nw["id"]))
        print("  voie IMPLICITE du port (normal_attack_type_for) = %s (natif %d) -> %s"
              % (implicite, GRAFT_TYPE,
                 "ACCORD" if implicite == GRAFT_TYPE else "DIVERGENCE (substrat gameconfig)"))
        rows = _rows(sid, rid, st, dv, nw, aid=GRAFT_TYPE)
        _print_rows("SANS ARME + GREFFE  u%s (type %d, masque 0x4000)" % (nw["id"], GRAFT_TYPE), rows)
        return {"greffe": rows}
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state)],
                       cwd=str(PYDIR), capture_output=True, text=True)


def run(sid, seed: str = "4192", board: str = "MC1_67", sans_canal: bool = False) -> dict:
    """La MESURE, sans verdict. Leve `MontageError` si le montage n'a pas mordu."""
    import subprocess
    rid, state = P583._build(sid, seed, board)
    print("=== montage : %s -> `CultDemagogue` -> %s (SANS ARME) + %s (ARME)  (runner %d)"
          % (P583.ANCHOR_VIS, P583.NOWEAPON_VIS, P583.ARMED_VIS, rid))
    try:
        for _ in range(P247.WARMUP_ENDTURNS):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
        P583._drive_and_summon(sid, rid)
        print("  contact force : %s" % P583.forcer_contact(sid, rid))
        dv, payloads = P436._capture(sid, rid)
        st = P436._mk_state(payloads)
        nw = P583._pick_adjacent(dv, P583.NOWEAPON_VIS)
        ar = P583._pick_adjacent(dv, P583.ARMED_VIS)
        if nw is None:
            raise MontageError("aucun `%s` vivant ADJACENT a un ennemi -> montage non pose"
                               % P583.NOWEAPON_VIS)
        if ar is None:
            raise MontageError("aucun `%s` vivant ADJACENT a un ennemi -> temoin non pose"
                               % P583.ARMED_VIS)
        for tag, u in (("SANS ARME", nw), ("ARME", ar)):
            got = P583._normal_attack_id(u)
            print("  montage %-9s u%-4s %-18s attaque normale NATIVE = %s (attendu %d) -> %s"
                  % (tag, u["id"], u.get("visualId"), got, GENERIC_TYPE,
                     "MORD" if got == GENERIC_TYPE else "N'A PAS MORDU"))
            if got != GENERIC_TYPE:
                raise MontageError("%s ne porte pas l'attaque normale generique" % u.get("visualId"))
        d_rows = _rows(sid, rid, st, dv, nw)
        a_rows = _rows(sid, rid, st, dv, ar)
        _print_rows("SANS ARME  u%s %s" % (nw["id"], P583.NOWEAPON_VIS), d_rows)
        _print_rows("ARME       u%s %s" % (ar["id"], P583.ARMED_VIS), a_rows)
        return {"decoy": d_rows, "anchor": a_rows}
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state)],
                       cwd=str(PYDIR), capture_output=True, text=True)


def tally(res: dict) -> dict:
    """Le bilan sur le CODE (la regle EXACTE) -- l'axe de CETTE tranche. Le verdict binaire
    (refuse/accepte) etait deja garde par #419-r1-tr14-r5-r2-r1-r2-r1 ; ici on garde la CAUSE, parce
    qu'une cause fausse se propage (elle gouverne quel gate un consommateur croit avoir franchi)."""
    out = {"tot": 0, "after": 0, "before": 0, "gain": 0, "perte": 0,
           "v_after": 0, "v_before": 0, "v_gain": 0, "v_perte": 0}
    for key in ("decoy", "anchor", "greffe"):
        rows = [r for r in (res.get(key) or []) if r["nat"] is not None]
        out["tot"] += len(rows)
        out["after"] += sum(1 for r in rows if r["after"] == r["nat"])
        out["before"] += sum(1 for r in rows if r["before"] == r["nat"])
        out["gain"] += sum(1 for r in rows if r["after"] == r["nat"] and r["before"] != r["nat"])
        out["perte"] += sum(1 for r in rows if r["after"] != r["nat"] and r["before"] == r["nat"])
        for r in rows:
            nat, af, bf = bool(r["nat"]), bool(r["after"]), bool(r["before"])
            out["v_after"] += int(af == nat)
            out["v_before"] += int(bf == nat)
            out["v_gain"] += int(af == nat and bf != nat)
            # PERTE = le natif ACCEPTE et le port REFUSE : l'echec symetrique, un refus trop large.
            out["v_perte"] += int(af != nat and bf == nat)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4192")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--no-graft", action="store_true",
                    help="ne joue que le bras 1 (economise un runner ; perd le discriminant VERDICT)")
    ap.add_argument("--sans-canal", action="store_true",
                    help="CONTRE-EPREUVE : rejoue le regime d'AVANT #448-r3-r1-r1 (canal "
                         "`unitAbilityStates` muet, le port derive le kit du gameconfig)")
    a = ap.parse_args(argv)
    sid = _resolve_session()
    # ⚠ LE CANAL (#448-r3-r1-r1). Le bras 2 GREFFE `PoundThemToDust` sur un summon SANS ARME ; sans
    # le canal `unitAbilityStates`, `snapshot._load_{active,config_active,triggered}_abilities` ne
    # posent rien et `services.custom_normal_attack` derive le type d'attaque normale du KIT
    # gameconfig -- qui ne connait pas la greffe. C'est la « divergence des substrats » que la
    # docstring de `run_greffe` contourne en passant `1126` EXPLICITEMENT aux deux modeles
    # (residu `#419-r1-tr14-r5-r2-r1-r2-r1-r2`). Lier le canal la fait disparaitre.
    if not a.sans_canal:
        bind_ambient_rpc(sid)
        print("[canal] `unitAbilityStates` LIE en ambiant (bind_live_rpc)")
    else:
        print("[canal] MUET (--sans-canal) -- regime d'AVANT, kit derive du gameconfig")
    try:
        res = run(sid, a.seed, a.board, sans_canal=a.sans_canal)
        if not a.no_graft:
            res.update(run_greffe(sid, a.seed, a.board, sans_canal=a.sans_canal))
    except MontageError as e:
        print("\n[FAIL] MONTAGE : %s" % e)
        return 2
    t = tally(res)
    print("\n=== BILAN sur %d lignes" % t["tot"])
    print("  CODE    (regle exacte)   : accord APRES %d | accord AVANT %d | gagnees %d | PERDUES %d"
          % (t["after"], t["before"], t["gain"], t["perte"]))
    print("  VERDICT (refuse/accepte) : accord APRES %d | accord AVANT %d | gagnees %d | PERDUES %d"
          % (t["v_after"], t["v_before"], t["v_gain"], t["v_perte"]))
    rc = 0
    if t["v_after"] != t["tot"]:
        print("[FAIL] %d ligne(s) ou le port et le natif divergent SUR LE VERDICT"
              % (t["tot"] - t["v_after"]))
        rc = 1
    if t["v_perte"]:
        print("[FAIL] %d cible(s) LEGITIME(S) PERDUE(S) : le refus porte est trop large"
              % t["v_perte"])
        rc = 1
    if not a.no_graft and t["v_gain"] == 0:
        print("[FAIL] le bras GREFFE ne deplace AUCUN verdict -- il devait montrer l'ecart PERMISSIF "
              "sur un masque sans `TargetMatchesDynamicRule`")
        rc = 1
    if t["after"] != t["tot"]:
        print("[FAIL] %d ligne(s) ou le port et le natif divergent SUR LE CODE"
              % (t["tot"] - t["after"]))
        rc = 1
    if t["gain"] == 0:
        print("[FAIL] REGIME DEGENERE : la baseline nomme la meme regle partout -- la mesure ne "
              "prouve rien, meme si l'accord est parfait")
        rc = 1
    if t["perte"]:
        print("[FAIL] %d ligne(s) PERDUE(S) : le correctif deplace une cause qui etait juste"
              % t["perte"])
        rc = 1
    for r in res["anchor"]:
        if r["after"] != r["before"]:
            print("[FAIL] temoin ARME u%d deplace : %s -> %s (la portee y est OBSERVABLE)"
                  % (r["tid"], hex(r["before"]), hex(r["after"])))
            rc = 1
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
