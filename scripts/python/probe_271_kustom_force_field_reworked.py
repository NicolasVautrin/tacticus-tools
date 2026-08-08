#!/usr/bin/env python
"""#271 - KustomForceFieldReworked (1547, `orksBigMek`) : les DEUX termes de playbook demasques par
le refresh `catalog_inject.refresh_ai_utilities` FONT-ILS BASCULER le choix NATIF ?

QUESTION BINAIRE (celle du cas) : avec les poids VIVANTS, un A/B qui fait varier le nombre d'ALLIES
ADJACENTS au porteur fait-il basculer le choix natif ? Oui -> le terme est confrontable ; non -> il
ne l'est pas, et il faut le DIRE.

DEUX faces, DEUX categories de poids, DEUX feuilles de tuile :

  * OWNER    -- `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedPlaybook$$GetAdjacentFriendUtility`
    (feuille `TriggeredAbilities(2)`, cle `KustomForceFieldReworked_LikesAdjacentFriends`) :
    quand le BIG MEK bouge, chaque ami a R1 de la tuile candidate vaut le poids, DOUBLE si cet ami
    est de faction Orks (`HasFaction(unit, 5)`).
  * NONOWNER -- `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook.
    u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` (feuille `TriggeredAbilitiesNonOwner(4)`,
    cle `KustomForceFieldReworked_FriendsLikeToBeAdjacent`) : quand un AMI du Big Mek bouge, une
    tuile candidate ADJACENTE au Big Mek vaut le poids, DOUBLE si LE MOVER est Orks.

ETAPE 0 (offline, aucun live) - GARDE DE MONTAGE. Le motif du cas est que natif et moteur lisaient
la MEME table PERIMEE : les deux cles valaient 0 dans `data/seed-bc.json` (la CAPTURE) et valent 10
au gameconfig VIVANT. Un A/B mene sur la capture rendrait « aucun ecart » et conclurait a tort.
L'etape 0 imprime les deux valeurs COTE A COTE et REFUSE de continuer si le moteur retombe sur la
capture (`engine.weights.load` annonce ce repli sur stderr).

ETAPE 1 (live) - A/B PAR AMPUTATION DU REGISTRE, sur l'argmax d'action. Les hooks par-tuile de
`scorer-damage-trace` portent des RVA du build `gqfc5mff6c` et ne sont PAS re-armables sur
`rnca9r7q6c` sans reinjection (interdite) : le canal de confrontation disponible est donc l'ARGMAX,
celui-la meme qu'utilisent les gardes #193c/#211/#212. On marche la trajectoire NATIVE et, a chaque
pas, on compare TROIS choses sur les MEMES tuiles candidates :

    tuile NATIVE jouee   vs   argmax du port TERME ACTIF   vs   argmax du port TERME AMPUTE

Un pas est DISCRIMINANT quand le terme prend au moins deux valeurs distinctes sur les candidates.
Un pas est BASCULANT quand les deux argmax different -- c'est la seule configuration ou le natif
peut trancher entre « il applique le terme » et « il ne l'applique pas ».

Usage (ASCII only) :
  python probe_271_kustom_force_field_reworked.py --offline-only
  python probe_271_kustom_force_field_reworked.py --seed 777 --board MC1_67 --steps 40
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

ABILITY = 1547                     # TriggeredAbilityType.KustomForceFieldReworked (0x60b)
CARRIER = "orksBigMek"
KEY_OWNER = "KustomForceFieldReworked_LikesAdjacentFriends"        # Utilities.Default.TriggeredAbilities
KEY_NONOWNER = "KustomForceFieldReworked_FriendsLikeToBeAdjacent"  # ...TriggeredAbilitiesNonOwner

# Roster CRAFTE pour que les DEUX faces soient discriminantes sur le meme montage :
#   - cote OWNER    : 2 amis Orks (x2) + 2 amis non-Orks (x1) -> deux tuiles a MEME nombre d'amis
#     adjacents ne valent PAS la meme chose ;
#   - cote NONOWNER : les movers alternent Orks / non-Orks -> le meme voisinage du Big Mek ne vaut
#     pas la meme chose selon QUI bouge.
DEFAULT_P = "orksBigMek,orksNob,orksWarboss,astraBullgryn,necroWarden"
DEFAULT_A = "worldKharn,templChampion,eldarJainZar,tauMarksman,darkaHellblaster"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# --------------------------------------------------------------------------------------------
# ETAPE 0 - garde de MONTAGE : le moteur voit-il les poids VIVANTS, ou la table de la CAPTURE ?
# --------------------------------------------------------------------------------------------
def step0_weights() -> int:
    import io
    import contextlib
    from engine import weights as W

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = (bc.get("Utilities") or {}).get("Default") or {}
    cap_owner = ((cap.get("TriggeredAbilities") or {}).get(KEY_OWNER))
    cap_non = ((cap.get("TriggeredAbilitiesNonOwner") or {}).get(KEY_NONOWNER))

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    fell_back = "REPLI sur BC.Utilities" in err.getvalue()
    live_owner = wt.sub("TriggeredAbilities", KEY_OWNER)
    live_non = wt.sub("TriggeredAbilitiesNonOwner", KEY_NONOWNER)

    print("[etape0] cle OWNER    %-46s capture=%-5s moteur=%s" % (KEY_OWNER, cap_owner, live_owner))
    print("[etape0] cle NONOWNER %-46s capture=%-5s moteur=%s" % (KEY_NONOWNER, cap_non, live_non))
    if fell_back:
        print("[etape0] REFUS : `engine.weights.load` est retombe sur la table de la CAPTURE --")
        print("[etape0] toute mesure d'A/B lirait le NEANT (c'est le motif meme de ce cas).")
        return 1
    if not live_owner or not live_non:
        print("[etape0] REFUS : au moins une cle vaut 0 cote moteur -- terme inerte, rien a mesurer.")
        return 1
    print("[etape0] OK : les deux cles sont NON NULLES cote moteur et viennent du gameconfig vivant.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAPE 1 - A/B live par amputation du registre
# --------------------------------------------------------------------------------------------
def _build(seed, board, p_units, a_units, extra):
    state = ROOT / "logs" / "runners" / ("probe271-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-800:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def _apply_native(sid, rid, dry):
    for m in (dry.get("action") or {}).get("messages") or []:
        cls = m.get("cls")
        if cls == "MoveUnitMessage":
            a = {"kind": "move", "unitId": m["unitId"],
                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}}
        elif cls == "ActiveAbilityMessage":
            a = {"kind": "ability", "casterId": m["casterId"],
                 "targetId": m.get("targetId"), "abilityType": m["abilityType"]}
        elif cls == "FinishUnitTurnMessage":
            a = {"kind": "finish", "unitId": m["unitId"]}
        else:
            continue
        _r(sid, "applyAction", {"runnerId": rid, "action": a}, 90)


def _face_terms(ctx, leaf_ctx, wt):
    """Terme de CHAQUE face, tuile candidate par tuile candidate.

    OWNER    : `load_playbook(1547).calculate_movement_utility_in_steps` (feuille 2) -- non nul
               seulement si le MOVER porte l'ability.
    NONOWNER : la feuille 4 ENTIERE (`TriggeredAbilitiesNonOwnerUtility`), qui n'a d'autre
               contributeur que ce playbook sur ce montage."""
    from engine.playbook.adjacent_unit_preference import load_playbook
    from engine.utilities.tile import TILE_LEAVES
    from engine.utilities.utility_type import UtilityType
    pb = load_playbook(ABILITY)
    non = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    kit = leaf_ctx.get("unit_triggered_abilities") or ()
    own, nono = {}, {}
    for t in (ctx.action_tiles or []):
        own[t] = (pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt)
                  if (pb is not None and ABILITY in kit) else 0.0)
        nono[t] = non.evaluate(t, {}, leaf_ctx, wt) if non is not None else 0.0
    return own, nono


def _argmax_tile(ctx):
    """Tuile de la decision COMPLETE du port -- `DefaultAiUnitTactic.calculate_next_action`, donc
    la MEME chaine de generateurs que le natif (`IdunBattle.AI.Tactics.DefaultAiUnitTactic.
    u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`).

    Pourquoi PAS `ComparableAbilityGenerator._best_attack` (ce qu'utilisent les gardes #193c/#211) :
    le Big Mek est une unite de SOUTIEN, ses pas sont majoritairement des MOUVEMENTS PURS, tranches
    par le `MovementActionGenerator` (`move.best_move_faithful` = Tile(7) + MinDist(16)). Sur ces
    pas-la `_best_attack` rend None et l'A/B ne mesurerait RIEN -- exactement le regime que le cas
    demande d'exercer."""
    from engine.ai.tactic import DefaultAiUnitTactic
    act = DefaultAiUnitTactic().calculate_next_action(ctx) or {}
    return act.get("to"), act


def _explain(ctx, leaf_ctx, wt, own, nono, nat_tile):
    """DECOMPOSITION PAR ETAGE du decideur de move PUR sur les tuiles candidates.

    `UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(17)` (`engine/move.py`). On imprime,
    tuile par tuile : la distance de CHEMIN a l'ennemi le plus proche, le terme MinDist, le
    composite `Tile(7)` du port, et la part que les DEUX faces de 1547 y prennent. C'est ce qui
    distingue « le terme ne bascule rien parce qu'il est domine » de « le port se trompe »."""
    from engine.utilities.move import MIN_DIST_UTILITY
    from engine.playbook.base import tile_utility as _tile_u
    print("        %-8s %8s %10s %10s %8s %9s %10s" %
          ("tuile", "pathd", "MinDist", "Tile(7)", "KFF_own", "KFF_non", "TOTAL"))
    rows = []
    for t in (ctx.move_tiles or []):
        p = (t["col"], t["row"]) if isinstance(t, dict) else (t[0], t[1])
        md = MIN_DIST_UTILITY.evaluate_movement(p, ctx.tgt_epos or ctx.epos, wt,
                                                ctx.pathdist_by_pos, case=ctx.mindist_case)
        tu = _tile_u(ctx, p)
        rows.append((p, (ctx.pathdist_by_pos or {}).get(p), md, tu,
                     own.get(p, 0.0), nono.get(p, 0.0), tu + md))
    for p, pd, md, tu, ko, kn, tot in sorted(rows, key=lambda r: -r[6])[:12]:
        print("        %-8s %8s %10.2f %10.2f %8.1f %9.1f %10.2f%s"
              % (str(p), pd, md, tu, ko, kn, tot, "   <-- NATIF" if p == nat_tile else ""))


def _without_registry(face: str):
    """Contexte d'AMPUTATION du registre : retire l'entree 1547 de la face demandee.

    C'est l'etape adversariale : si l'argmax ne bouge pas quand le terme disparait, la mesure ne
    prouve RIEN sur ce pas."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
        from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS
        reg = TRIGGERED_MOVE_PLAYBOOKS if face == "owner" else NON_OWNER_MOVE_PLAYBOOKS
        saved = reg.pop(ABILITY, None)
        try:
            yield
        finally:
            if saved is not None:
                reg[ABILITY] = saved
    return _cm()


def run(sid, rid, steps, verbose):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.utilities.tile import tile_leaf_ctx

    dv0 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    vmap = {u.get("id"): u.get("visualId") for u in (dv0.get("units") or [])}
    teams = {u.get("id"): u.get("ctrl") for u in (dv0.get("units") or [])}
    mek = [i for i, v in vmap.items() if v == CARRIER]
    print("[etape1] runner %s : %s = %s ; %d unites"
          % (rid, CARRIER, mek, len(vmap)))
    if not mek:
        print("[etape1] REFUS : le porteur %s n'est pas dans la bataille." % CARRIER)
        return 1

    rows = []
    for step in range(steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("[etape1] trajectoire native epuisee au pas %d (%s)" % (step, dry.get("error")))
            break
        uid = dry.get("activatedUnitId")
        msgs = (dry.get("action") or {}).get("messages") or []
        nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        if me is None:
            _apply_native(sid, rid, dry)
            continue
        mpos = me.get("pos") or {}
        origin = (mpos["col"], mpos["row"]) if mpos.get("col") is not None else None
        nat_tile = ((nat_move["to"]["col"], nat_move["to"]["row"]) if nat_move else origin)

        wt = W.load()
        pred = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
        ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
        leaf_ctx = tile_leaf_ctx(ctx)
        own, nono = _face_terms(ctx, leaf_ctx, wt)

        for face, term in (("owner", own), ("nonowner", nono)):
            vals = sorted({round(v, 4) for v in term.values()})
            if len(vals) < 2:
                continue                      # pas discriminant : le terme ne peut rien trancher
            on_tile, _ = _argmax_tile(ctx)
            with _without_registry(face):
                off_tile, _ = _argmax_tile(ctx)
            rows.append({"step": step, "face": face, "uid": uid, "vis": vmap.get(uid),
                         "ctrl": teams.get(uid), "vals": vals, "native": nat_tile,
                         "on": on_tile, "off": off_tile,
                         "n_tiles": len(ctx.action_tiles or [])})
            print("  pas %-3d %-9s u%-4s %-16s terme=%s  natif=%s  port(ON)=%s  port(OFF)=%s%s"
                  % (step, face, uid, vmap.get(uid), vals, nat_tile, on_tile, off_tile,
                     "  <-- BASCULE" if on_tile != off_tile else ""))
            if verbose or on_tile != off_tile:
                print("        terme par tuile : %s"
                      % {t: round(v, 2) for t, v in sorted(term.items()) if v})
                _explain(ctx, leaf_ctx, wt, own, nono, nat_tile)
        _apply_native(sid, rid, dry)

    print("")
    print("=== BILAN ===")
    for face in ("owner", "nonowner"):
        f = [r for r in rows if r["face"] == face]
        sw = [r for r in f if r["on"] != r["off"]]
        ok = [r for r in sw if r["on"] == r["native"]]
        ko = [r for r in sw if r["on"] != r["native"]]
        print("face %-9s : %d pas discriminants, %d BASCULANTS (port ON != port OFF)"
              % (face, len(f), len(sw)))
        for r in sw:
            print("   pas %-3d %-16s natif=%s  ON=%s  OFF=%s  -> %s"
                  % (r["step"], r["vis"], r["native"], r["on"], r["off"],
                     "ON d'accord avec le NATIF" if r["on"] == r["native"]
                     else ("OFF d'accord avec le NATIF" if r["off"] == r["native"]
                           else "NI l'un NI l'autre")))
        print("   -> ON==natif sur %d/%d bascules ; OFF==natif sur %d/%d"
              % (len(ok), len(sw), sum(1 for r in sw if r["off"] == r["native"]), len(sw)))
    return 0


# --------------------------------------------------------------------------------------------
# ETAPE 2 - SCENARIO CRAFTE : on DEPLACE un allie pour forcer la configuration discriminante.
#
# Pourquoi il FAUT crafter. L'etape 1 mesure sur la trajectoire NATURELLE, et elle y montre que le
# terme VARIE beaucoup mais ne BASCULE presque jamais : le decideur de move pur est
# `UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(17)` et `MinDist.PerTileDistance` vaut -100
# PAR TUILE de distance-CHEMIN. Un ecart d'une seule tuile de chemin (100) ecrase le terme (10..40).
# Le terme ne peut donc trancher qu'entre tuiles a distance-chemin EGALE -- configuration qu'il faut
# FABRIQUER, pas attendre (cf. runner.md, « tu as la maitrise totale du setup »).
#
# Le montage : bigMek au spawn, ennemis a l'autre bout (aucune attaque possible -> move pur). On
# repere T1 = argmax du port SANS le terme, et T2 = la meilleure AUTRE tuile ; on pose un allie sur
# une tuile adjacente a T2 SEULE. Le terme devient le seul ecart entre les deux, et il est CENSE
# faire passer T2 devant T1. Le natif tranche.
#   variante ORK    : l'allie pose est de faction Orks     -> terme(T2) = 2 x w
#   variante NONORK : l'allie pose ne l'est pas            -> terme(T2) =     w
# Si l'ecart `T1 - T2` tombe entre w et 2w, les DEUX variantes se separent : c'est le seul montage
# qui confronte le FACTEUR 2 (`HasFaction(unit, 5)`) et pas seulement le poids.
# --------------------------------------------------------------------------------------------
def _ctx_for(sid, rid, uid):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    pred = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    return dv, _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, pred), wt


def _score_map(ctx, wt, with_term: bool):
    """`UnitMovement(6)` du port par tuile candidate : `Tile(7) + MinDist(16)`, terme ACTIF ou AMPUTE."""
    from engine.playbook.base import tile_utility
    from engine.utilities.move import MIN_DIST_UTILITY
    import contextlib
    cm = contextlib.nullcontext() if with_term else _without_both()
    out = {}
    with cm:
        for t in (ctx.move_tiles or []):
            p = (t["col"], t["row"])
            md = MIN_DIST_UTILITY.evaluate_movement(p, ctx.tgt_epos or ctx.epos, wt,
                                                    ctx.pathdist_by_pos, case=ctx.mindist_case)
            out[p] = tile_utility(ctx, p) + md
    return out


_AMPUTATE = [ABILITY]      # ability dont on ampute le registre pour la ligne de base (cf. --ability)


def _without_both():
    """Amputation des DEUX faces (etat `master` avant #271) -- la ligne de base de l'A/B."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
        from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS
        ab = _AMPUTATE[0]
        a = TRIGGERED_MOVE_PLAYBOOKS.pop(ab, None)
        b = NON_OWNER_MOVE_PLAYBOOKS.pop(ab, None)
        try:
            yield
        finally:
            if a is not None:
                TRIGGERED_MOVE_PLAYBOOKS[ab] = a
            if b is not None:
                NON_OWNER_MOVE_PLAYBOOKS[ab] = b
    return _cm()


def _native_move(sid, rid, uid):
    """Action que l'IA NATIVE proposerait pour `uid` contre l'etat COURANT (`aiDryRunAllUnits`,
    `CalculateNextActionForUnit`, `mutated:false`).

    Rend `(tuile, pure_move, row)`. `pure_move` est FAUX des que la proposition contient un
    `ActiveAbilityMessage` : la tuile vient alors du sweep d'ATTAQUE
    (`ActiveAbilityActionGenerator`), PAS du `MovementActionGenerator` que ce probe modelise
    (`UnitMovement(6) = Tile(7) + MinDist(16)`). Comparer l'argmax de move a une tuile d'attaque
    ne mesure rien -- c'est ce qui rendait des verdicts « NATIF != les deux » incomprehensibles."""
    res = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 240)
    row = next((u for u in (res.get("units") or []) if u.get("unitId") == uid), None)
    if row is None:
        return None, False, None
    msgs = row.get("proposed") or []
    mv = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    pure = mv is not None and not any(m.get("cls") == "ActiveAbilityMessage" for m in msgs)
    return ((mv["to"]["col"], mv["to"]["row"]) if mv else None), pure, row


def _place(sid, rid, uid, tile) -> bool:
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": tile[0], "row": tile[1]}}}, 90)
    acts = res.get("actions") or []
    return bool(acts and acts[0].get("ok"))


MAX_GAP = 25.0     # au-dela, aucun terme de ce module (10/20/30) ne peut renverser la paire


def _pick_pair(base, nb, mv, dv0, mek, want_ork, occupied, max_gap=MAX_GAP, min_gap=0.0):
    """(T1, T2, ecart, slot) : T1 = argmax du score SANS terme ; T2 = la meilleure AUTRE tuile
    telle que (a) l'ecart soit franchissable par le terme et (b) il existe une tuile LIBRE,
    voisine NATIVE de T2 et PAS de T1, atteignable par un allie de la faction demandee.

    `want_ork=None` -> aucun allie a poser (variante temoin), on rend juste la meilleure paire."""
    from engine.entities.unit_faction import faction_value, UnitFaction
    order = sorted(base.items(), key=lambda kv: -kv[1])
    if len(order) < 2:
        return None
    t1 = order[0][0]
    for t2, s2 in order[1:]:
        gap = base[t1] - s2
        if gap > max_gap:
            break
        if gap < min_gap:
            continue
        if want_ork is None:
            return t1, t2, gap, None
        for u in (dv0.get("units") or []):
            if not u.get("ctrl") or u.get("id") == mek:
                continue
            if (faction_value(u.get("visualId")) == int(UnitFaction.Orks)) != want_ork:
                continue
            for t in ((mv.get(u["id"]) or {}).get("tiles") or []):
                c = (t["col"], t["row"])
                if c in occupied or c in (t1, t2):
                    continue
                if c in nb.get(t2, ()) and c not in nb.get(t1, ()):
                    return t1, t2, gap, (u["id"], u.get("visualId"), c)
    return None


def step2_driven(sid, seed, board, ally_kind, p_units, a_units, verbose,
                 carrier=CARRIER, ability=ABILITY, min_gap=0.0) -> dict:
    """UNE variante du scenario crafte. `ally_kind` = "ork" | "nonork" | "none" (temoin).

    `carrier`/`ability` sont parametrables pour permettre le CONTROLE DE L'INSTRUMENT : rejouer le
    MEME montage avec un terme dont la vivacite native est deja etablie par une autre voie (ex.
    `GuardianOrganism` 1181 / `tyranTyrantGuard`, mesure aux hooks de case-36 : 30 par ami adjacent,
    30/90 EXACTS). Sans ce controle, un « le natif ne suit pas » ne distingue pas « le terme est
    mort » de « mon montage ne mesure pas ce que je crois »."""
    rid, state = _build(seed, board, p_units, a_units, [])
    if rid is None:
        return {"ok": False}
    out = {"ok": False, "seed": seed, "board": board, "kind": ally_kind, "rid": rid,
           "carrier": carrier}
    try:
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or [])}
        mek = ids.get(carrier)
        if mek is None:
            print("  [%s] REFUS : %s absent" % (ally_kind, carrier))
            return out
        dv, ctx, wt = _ctx_for(sid, rid, mek)
        base = _score_map(ctx, wt, with_term=False)
        # ⚠ ADJACENCE **NATIVE** (`ctx.neigh_by_pos` = `boardGraph`), PAS `hexgeo.distance == 1`.
        # C'est le piege qui a d'abord fait rendre a ce probe un faux verdict « le natif n'applique
        # pas le terme » : sur `MC1_67`, (1,3) est un voisin hexgeo de (2,2) mais PAS un voisin
        # natif (elevation 4 vs 2 -> le gate `|Delta| < 2` de `IterateAdjacentTiles` les separe).
        # L'allie pose la n'etait adjacent QUE POUR LE PORT -- cf. l'etape 3 (`--adjacency`).
        nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx.neigh_by_pos or {}).items()}
        occupied = set(ctx.epos) | set(ctx.fpos) | {ctx.origin}
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        mv = {u.get("unitId"): u for u in (mov.get("units") or [])}
        want = None if ally_kind == "none" else (ally_kind == "ork")
        pair = _pick_pair(base, nb, mv, dv0, mek, want, occupied, min_gap=min_gap)
        if pair is None:
            print("  [%s] REFUS : aucune paire (T1,T2) franchissable avec un slot d'allie %s"
                  % (ally_kind, ally_kind))
            return out
        t1, t2, gap, slot = pair
        out.update({"t1": t1, "t2": t2, "gap": gap})
        print("  [%s] sans terme : T1=%s (%.2f) > T2=%s (%.2f), ecart=%.2f"
              % (ally_kind, t1, base[t1], t2, base[t2], gap))
        if slot is not None:
            print("  [%s] pose %s (u%s) en %s (voisin NATIF de T2=%s, pas de T1=%s)"
                  % (ally_kind, slot[1], slot[0], slot[2], t2, t1))
            if not _place(sid, rid, slot[0], slot[2]):
                print("  [%s] REFUS : applyAction move KO" % ally_kind)
                return out
            dv, ctx, wt = _ctx_for(sid, rid, mek)      # etat MUTE : tout recalculer

        base2 = _score_map(ctx, wt, with_term=False)
        on2 = _score_map(ctx, wt, with_term=True)
        p_off = max(base2, key=lambda k: base2[k]) if base2 else None
        p_on = max(on2, key=lambda k: on2[k]) if on2 else None
        nat, pure, row = _native_move(sid, rid, mek)
        out["pure_move"] = pure
        out.update({"port_off": p_off, "port_on": p_on, "native": nat,
                    "term_t1": on2.get(t1, 0) - base2.get(t1, 0),
                    "term_t2": on2.get(t2, 0) - base2.get(t2, 0)})
        print("  [%s] terme(T1)=%+.1f terme(T2)=%+.1f | port OFF=%s  port ON=%s  NATIF=%s%s"
              % (ally_kind, out["term_t1"], out["term_t2"], p_off, p_on, nat,
                 "   <-- BASCULE" if p_on != p_off else ""))
        if verbose:
            for p in sorted(on2, key=lambda k: -on2[k])[:8]:
                print("        %-8s OFF=%9.2f ON=%9.2f  pathd=%s"
                      % (str(p), base2[p], on2[p], (ctx.pathdist_by_pos or {}).get(p)))
        out["ok"] = True
        return out
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        Path(state).unlink(missing_ok=True)


# --------------------------------------------------------------------------------------------
# ETAPE 2bis - ECHANGE DE FACTIONS : le seul montage qui isole le FACTEUR 2 (`HasFaction(unit, 5)`).
#
# Aucun couple (board, seed) teste n'offre un ecart T1-T2 dans l'intervalle ]10, 20[ ou le poids
# seul (10) echouerait la ou le poids double (20) reussirait : les Tile(7) sont quantifies par
# paliers (Elevation 10/niveau, LightCover 9) et MinDist saute de 100. On isole donc le facteur 2
# AUTREMENT, sans dependre de l'ecart : on pose UN ami de CHAQUE faction, un de chaque cote.
#
#   variante A (ork_t2)  : ami ORK voisin de T2, ami NON-ORK voisin de T1
#                          -> terme(T2)=2w, terme(T1)=w  -> avantage NET +w pour T2
#   variante B (ork_t1)  : l'INVERSE (pur echange de places)
#                          -> terme(T2)=w,  terme(T1)=2w -> avantage NET +w pour T1
#
# La GEOMETRIE est identique dans les deux variantes ; seule change la FACTION de l'occupant de
# chaque tuile. Si le facteur 2 n'existait pas (poids plat, quelle que soit sa valeur), les deux
# termes s'annuleraient et T1 gagnerait dans LES DEUX variantes. La variante A qui bascule vers T2
# est donc la signature EXCLUSIVE du `HasFaction(unit, 5) -> v *= 2`.
# --------------------------------------------------------------------------------------------
def _slot_for(dv0, mv, mek, want_ork, nb, near, far, occupied, taken):
    """Tuile LIBRE voisine NATIVE de `near` et PAS de `far`, atteignable par un allie de la faction
    demandee et pas deja prise. Rend `(unitId, visualId, tile)`."""
    from engine.entities.unit_faction import faction_value, UnitFaction
    for u in (dv0.get("units") or []):
        if not u.get("ctrl") or u.get("id") == mek or u.get("id") in {t[0] for t in taken}:
            continue
        if (faction_value(u.get("visualId")) == int(UnitFaction.Orks)) != want_ork:
            continue
        for t in ((mv.get(u["id"]) or {}).get("tiles") or []):
            c = (t["col"], t["row"])
            if c in occupied or c in (near, far) or c in {x[2] for x in taken}:
                continue
            if c in nb.get(near, ()) and c not in nb.get(far, ()):
                return (u["id"], u.get("visualId"), c)
    return None


def step2_swap(sid, seed, board, variant, p_units, a_units, verbose) -> dict:
    """UNE variante de l'echange de factions. `variant` = "ork_t2" | "ork_t1"."""
    rid, state = _build(seed, board, p_units, a_units, [])
    if rid is None:
        return {"ok": False}
    out = {"ok": False, "seed": seed, "board": board, "kind": variant}
    try:
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or [])}
        mek = ids.get(CARRIER)
        if mek is None:
            print("  [%s] REFUS : %s absent" % (variant, CARRIER))
            return out
        dv, ctx, wt = _ctx_for(sid, rid, mek)
        base = _score_map(ctx, wt, with_term=False)
        nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx.neigh_by_pos or {}).items()}
        occupied = set(ctx.epos) | set(ctx.fpos) | {ctx.origin}
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        mv = {u.get("unitId"): u for u in (mov.get("units") or [])}
        order = sorted(base.items(), key=lambda kv: -kv[1])
        if len(order) < 2:
            print("  [%s] REFUS : moins de 2 tuiles candidates" % variant)
            return out
        t1 = order[0][0]
        found = None
        for t2, s2 in order[1:]:
            gap = base[t1] - s2
            if gap > MAX_GAP:
                break
            taken = []
            ork_near, non_near = (t2, t1) if variant == "ork_t2" else (t1, t2)
            s_ork = _slot_for(dv0, mv, mek, True, nb, ork_near,
                              t1 if ork_near == t2 else t2, occupied, taken)
            if s_ork is None:
                continue
            taken.append(s_ork)
            s_non = _slot_for(dv0, mv, mek, False, nb, non_near,
                              t1 if non_near == t2 else t2, occupied, taken)
            if s_non is None:
                continue
            found = (t2, gap, s_ork, s_non)
            break
        if found is None:
            print("  [%s] REFUS : pas de paire avec DEUX slots (un par faction, un par cote)" % variant)
            return out
        t2, gap, s_ork, s_non = found
        out.update({"t1": t1, "t2": t2, "gap": gap})
        print("  [%s] T1=%s (%.2f) T2=%s (%.2f) ecart=%.2f | ORK %s -> %s | NON-ORK %s -> %s"
              % (variant, t1, base[t1], t2, base[t2], gap, s_ork[1], s_ork[2], s_non[1], s_non[2]))
        for sl in (s_ork, s_non):
            if not _place(sid, rid, sl[0], sl[2]):
                print("  [%s] REFUS : applyAction move KO pour u%s" % (variant, sl[0]))
                return out
        dv, ctx, wt = _ctx_for(sid, rid, mek)
        base2 = _score_map(ctx, wt, with_term=False)
        on2 = _score_map(ctx, wt, with_term=True)
        p_off = max(base2, key=lambda k: base2[k]) if base2 else None
        p_on = max(on2, key=lambda k: on2[k]) if on2 else None
        nat, pure, _ = _native_move(sid, rid, mek)
        out["pure_move"] = pure
        out.update({"port_off": p_off, "port_on": p_on, "native": nat,
                    "term_t1": on2.get(t1, 0) - base2.get(t1, 0),
                    "term_t2": on2.get(t2, 0) - base2.get(t2, 0)})
        print("  [%s] terme(T1)=%+.1f terme(T2)=%+.1f | port OFF=%s  port ON=%s  NATIF=%s"
              % (variant, out["term_t1"], out["term_t2"], p_off, p_on, nat))
        out["ok"] = True
        return out
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        Path(state).unlink(missing_ok=True)


def run_swap(sid, seeds, boards, p_units, a_units, verbose) -> int:
    print("")
    print("=== ETAPE 2bis : ECHANGE DE FACTIONS (isole le facteur 2 de `HasFaction(unit, 5)`) ===")
    rows = []
    for board in boards:
        for seed in seeds:
            print("-- board=%s seed=%s" % (board, seed))
            for variant in ("ork_t2", "ork_t1"):
                rows.append((board, seed, variant,
                             step2_swap(sid, seed, board, variant, p_units, a_units, verbose)))
    print("")
    print("=== BILAN ETAPE 2bis ===")
    for board, seed, variant, r0 in rows:
        if not r0.get("ok"):
            print("%-10s %-6s %-7s : NON CONCLUANT" % (board, seed, variant))
            continue
        print("%-10s %-6s %-7s : T1=%s T2=%s ecart=%.1f | terme T1=%+.0f T2=%+.0f | ON=%s NATIF=%s"
              " -> %s"
              % (board, seed, variant, r0["t1"], r0["t2"], r0["gap"], r0["term_t1"], r0["term_t2"],
                 r0["port_on"], r0["native"],
                 "NATIF == ON" if r0["native"] == r0["port_on"] else "NATIF != ON"))
    return 0


# --------------------------------------------------------------------------------------------
# ETAPE 2ter - face NON-OWNER : c'est un AMI qui bouge, et c'est la position du BIG MEK qui pese.
#
# Meme montage retourne : le SUJET est un allie du Big Mek, et l'unite qu'on DEPLACE est le Big Mek
# lui-meme, pose sur une tuile voisine NATIVE de T2 et pas de T1. Le terme
# `KustomForceFieldReworked_FriendsLikeToBeAdjacent` doit alors faire passer T2 devant T1.
# Deux sujets : un mover ORK (terme = 2w) et un mover NON-ORK (terme = w) -- le `HasFaction` de
# cette face lit LE MOVER, pas le voisin.
# --------------------------------------------------------------------------------------------
def step2_nonowner(sid, seed, board, mover_vis, p_units, a_units, verbose, pre_steps=0,
                   side="t2", min_gap=0.0, force_pair=None) -> dict:
    """`pre_steps` : chunks de la trajectoire NATIVE joues AVANT le montage.

    Au tour 1 tout le monde est colle au spawn : les meilleures tuiles du mover sont 2-3 cases en
    AVANT, hors de portee du Big Mek, donc aucune tuile « voisine de T2 et pas de T1 » ne lui est
    accessible. Laisser l'IA avancer quelques chunks etale les unites et rend le montage montable
    -- c'est le meme geste que `_walk_to` des gardes #193c."""
    rid, state = _build(seed, board, p_units, a_units, [])
    if rid is None:
        return {"ok": False}
    out = {"ok": False, "seed": seed, "board": board, "kind": "nonowner:" + mover_vis,
           "pre": pre_steps, "side": side}
    try:
        for _ in range(pre_steps):
            d = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not d.get("ok") or not d.get("hasNext"):
                break
            _apply_native(sid, rid, d)
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or [])}
        act = {u.get("id"): u.get("hasAction") for u in (dv0.get("units") or [])}
        mek, mover = ids.get(CARRIER), ids.get(mover_vis)
        if mek is None or mover is None:
            print("  [%s] REFUS : porteur ou mover absent" % mover_vis)
            return out
        if not act.get(mek) or not act.get(mover):
            print("  [%s] REFUS pas=%d : action deja consommee (mek=%s mover=%s)"
                  % (mover_vis, pre_steps, act.get(mek), act.get(mover)))
            return out
        dv, ctx, wt = _ctx_for(sid, rid, mover)
        base = _score_map(ctx, wt, with_term=False)
        nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx.neigh_by_pos or {}).items()}
        occupied = set(ctx.epos) | set(ctx.fpos) | {ctx.origin}
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        mv = {u.get("unitId"): u for u in (mov.get("units") or [])}
        mek_tiles = [(t["col"], t["row"]) for t in ((mv.get(mek) or {}).get("tiles") or [])]
        order = sorted(base.items(), key=lambda kv: -kv[1])
        if len(order) < 2:
            print("  [%s] REFUS : moins de 2 tuiles candidates" % mover_vis)
            return out
        t1 = order[0][0]
        if force_pair is not None and t1 != force_pair[0]:
            # MIROIR STRICT : meme paire (T1,T2) que la variante precedente, seul l'AIMANT change.
            # Sur un ex aequo c'est le SEUL controle valable -- un tie-break natif FIXE ne peut pas
            # rendre deux reponses differentes sur la MEME paire.
            print("  [%s/%s] REFUS : T1 a change (%s vs %s) -- miroir non comparable"
                  % (mover_vis, side, t1, force_pair[0]))
            return out
        found = None
        for t2, s2 in order[1:]:
            gap = base[t1] - s2
            if gap > MAX_GAP:
                break
            if force_pair is not None and t2 != force_pair[1]:
                continue
            # `min_gap > 0` EXIGE que T1 batte STRICTEMENT T2 sans le terme : sur un ex aequo, un
            # tie-break natif constant produirait le meme resultat que le terme, et la mesure ne
            # trancherait rien -- SAUF si le miroir strict ci-dessus est joue.
            if gap < min_gap:
                continue
            # `side` = de QUEL COTE on pose le Big Mek. "t2" attire vers T2 (bascule attendue) ;
            # "t1" est le MIROIR de controle : meme geometrie, aimant de l'autre cote. Sur un ex
            # aequo (`ecart == 0`) le miroir est INDISPENSABLE -- sans lui, un tie-break natif
            # constant produirait le meme resultat que le terme et on lirait une confirmation
            # imaginaire.
            def _slot(near, far):
                for c in mek_tiles:
                    # `c` PEUT etre une tuile candidate du mover : le Big Mek l'occupe, elle sort
                    # du set -- sans consequence tant que ce n'est ni T1 ni T2 (le score est
                    # integralement RECALCULE sur l'etat mute).
                    if c in occupied or c in (t1, t2):
                        continue
                    if c in nb.get(near, ()) and c not in nb.get(far, ()):
                        return c
                return None
            # Aimant posable du cote demande. Sur un ex aequo (`gap == 0`) on EXIGE en plus qu'il
            # soit posable de l'AUTRE cote, pour que le miroir strict -- seul controle valable
            # contre un tie-break natif fixe -- reste montable. Des que `gap > 0`, la variante
            # directe suffit : sans le terme, T1 gagne SANS ambiguite.
            c = _slot(t2, t1) if side == "t2" else _slot(t1, t2)
            if c is None:
                continue
            if gap <= 0 and _slot(t1, t2) is None:
                continue
            found = (t2, gap, c)
            break
        if found is None:
            print("  [%s] REFUS pas=%d : aucune tuile ou poser le Big Mek voisin de T2 seule "
                  "(T1=%s, ecarts=%s, mek atteint %d tuiles)"
                  % (mover_vis, pre_steps, t1,
                     [round(base[t1] - s, 1) for _t, s in order[1:5]], len(mek_tiles)))
            return out
        t2, gap, c = found
        out.update({"t1": t1, "t2": t2, "gap": gap})
        print("  [%s/%s] T1=%s (%.2f) T2=%s (%.2f) ecart=%.2f | Big Mek -> %s (voisin NATIF de %s)"
              % (mover_vis, side, t1, base[t1], t2, base[t2], gap, c, side.upper()))
        if not _place(sid, rid, mek, c):
            print("  [%s] REFUS : applyAction move KO (Big Mek)" % mover_vis)
            return out
        dv, ctx, wt = _ctx_for(sid, rid, mover)
        base2 = _score_map(ctx, wt, with_term=False)
        on2 = _score_map(ctx, wt, with_term=True)
        p_off = max(base2, key=lambda k: base2[k]) if base2 else None
        p_on = max(on2, key=lambda k: on2[k]) if on2 else None
        nat, pure, _ = _native_move(sid, rid, mover)
        out["pure_move"] = pure
        if not pure:
            print("  [%s/%s] REFUS : la proposition native n'est PAS un move pur (attaque) -- la "
                  "tuile vient du sweep d'ATTAQUE, hors du modele UnitMovement(6)" % (mover_vis, side))
            return out
        out.update({"port_off": p_off, "port_on": p_on, "native": nat,
                    "term_t1": on2.get(t1, 0) - base2.get(t1, 0),
                    "term_t2": on2.get(t2, 0) - base2.get(t2, 0)})
        print("  [%s/%s] terme(T1)=%+.1f terme(T2)=%+.1f | port OFF=%s  port ON=%s  NATIF=%s%s"
              % (mover_vis, side, out["term_t1"], out["term_t2"], p_off, p_on, nat,
                 "   <-- BASCULE" if p_on != p_off else ""))
        if verbose:
            for p in sorted(on2, key=lambda k: -on2[k])[:8]:
                print("        %-8s OFF=%9.2f ON=%9.2f" % (str(p), base2[p], on2[p]))
        out["ok"] = True
        return out
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        Path(state).unlink(missing_ok=True)


def step2_nonowner_preplace(sid, seed, board, mover_vis, p_units, a_units, verbose,
                            min_gap=1.0, essais=12, loin=6) -> dict:
    """VOIE (b) de `#271-r1` : le Big Mek est **PRE-POSITIONNE AU BUILD**, pas deplace en jeu.

    POURQUOI LA VOIE (a) NE FERMAIT PAS, MESURE. `step2_nonowner` laisse l'IA avancer `pre_steps`
    chunks pour etaler les unites, puis DEPLACE le Big Mek sur une tuile voisine de T2 seule. Les
    deux moities se contredisent : a `pre_steps = 0` tout le monde a son action mais le Big Mek,
    ne au fond du spawn, n'ATTEINT aucune tuile utile ; des qu'on avance, l'IA CONSOMME son action
    ou celle du mover. Balayage du 2026-08-08 (4 boards x 2 seeds x 2 movers x pas 0..8, 80
    montages, `--gap-min 1`) : **0 concluant**, et la cause dominante est
    << action deja consommee >> (38 refus sur 80), pas la geometrie.

    `--place` tranche les deux d'un coup : il pose les unites AVANT le premier tour, donc sans
    consommer d'action ET sans dependre de la portee de deplacement. C'est litteralement le
    << pre-positionner le Big Mek DEVANT ses allies >> de la fiche.

    Le critere reste celui de la voie (a) -- `min_gap >= 1` EXIGE que T1 batte STRICTEMENT T2 sans
    le terme : sur un ex aequo, un tie-break natif constant produirait le meme resultat et la
    mesure ne trancherait rien. C'est exactement ce que #271-r1 reproche aux deux bascules deja
    mesurees.
    """
    from engine.entities.pathfinding.board import Board

    # -- 1. runner SONDE : le boardGraph et la geometrie du spawn, puis on le rend tout de suite
    rid0, state0 = _build(seed, board, p_units, a_units, [])
    if rid0 is None:
        return {"ok": False}
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid0}, 60)
        dv0 = _r(sid, "decisionView", {"runnerId": rid0, "maxRank": 1}, 180)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid0}, 30)
        Path(state0).unlink(missing_ok=True)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        print("  [%s] REFUS : boardGraph indispo -- NON MESURE" % mover_vis)
        return {"ok": False}
    bd = Board(bg["tiles"], adjacency="native_sym")
    occ0 = {(u["pos"]["col"], u["pos"]["row"]) for u in (dv0.get("units") or [])
            if u.get("pos") and u.get("alive")}
    mine = [u for u in (dv0.get("units") or []) if u.get("ctrl") and u.get("pos")]
    if not mine:
        print("  [%s] REFUS : aucune unite controlee dans la sonde" % mover_vis)
        return {"ok": False}

    # -- 2. choisir (M, B) : deux tuiles ADJACENTES (adjacence NATIVE), libres, dans la moitie du
    #       board ou nos unites apparaissent. Le Big Mek en `B` couvre alors une PARTIE de
    #       l'anneau de deplacement du mover parti de `M`, et pas l'autre -- ce qui est
    #       exactement la configuration que la voie (a) n'arrivait pas a atteindre.
    lignes = [u["pos"]["row"] for u in mine]
    r_lo, r_hi = min(lignes), max(lignes)
    # ⚠ LOIN DES ENNEMIS, et ce n'est pas une precaution : c'est le SECOND blocage, mesure.
    # Le premier balayage pre-place (30 positions x 2 movers, `MC1_67`/777) a bien produit la
    # paire a ecart STRICT que la voie (a) n'atteignait jamais (24, sur `mover@(4,4)
    # mek@(4,5)`) -- mais `aiDryRunAllUnits` y proposait une ATTAQUE, donc une tuile issue du
    # sweep `ActiveAbilityActionGenerator` et NON du `MovementActionGenerator` que ce probe
    # modelise (`UnitMovement(6) = Tile(7) + MinDist(16)`). Comparer l'argmax de move a une tuile
    # d'attaque ne mesure rien. On ecarte donc les positions a portee d'un ennemi.
    import hexgeo
    epos = [(u["pos"]["col"], u["pos"]["row"]) for u in (dv0.get("units") or [])
            if u.get("pos") and u.get("alive") and not u.get("ctrl")]
    candidats = []
    for M in sorted(bd.by_id):
        cm = bd.coord(M)
        if not bd.walkable(M) or cm in occ0 or not (r_lo - 1 <= cm[1] <= r_hi + 2):
            continue
        if epos and min(hexgeo.distance(cm, e) for e in epos) < loin:
            continue
        for B in bd.neighbours(M):
            cb = bd.coord(B)
            if not bd.walkable(B) or cb in occ0 or cb == cm:
                continue
            candidats.append((cm, cb))
    if not candidats:
        print("  [%s] REFUS : aucune paire (mover, Big Mek) adjacente et libre" % mover_vis)
        return {"ok": False}

    # Le CENTRE d'abord : une tuile centrale laisse au mover un anneau de deplacement large, donc
    # plus de chances qu'une paire (T1, T2) a ecart STRICT existe avec T2 seule voisine du Big Mek.
    cx = sum(bd.coord(t)[0] for t in bd.by_id) / max(1, len(bd.by_id))
    cy = sum(bd.coord(t)[1] for t in bd.by_id) / max(1, len(bd.by_id))
    candidats.sort(key=lambda p: (p[0][0] - cx) ** 2 + (p[0][1] - cy) ** 2)

    out = {"ok": False, "seed": seed, "board": board, "kind": "preplace:" + mover_vis}
    causes = {"build KO": 0, "montage": 0, "pas de paire a ecart STRICT": 0,
              "proposition NON PURE (attaque)": 0}
    for cm, cb in candidats[:essais]:
        places = ["--place", "%s:%d,%d" % (mover_vis, cm[0], cm[1]),
                  "--place", "%s:%d,%d" % (CARRIER, cb[0], cb[1])]
        rid, state = _build(seed, board, p_units, a_units, places)
        if rid is None:
            causes["build KO"] += 1
            continue
        try:
            dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
            ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}
            act = {u.get("id"): u.get("hasAction") for u in (dv.get("units") or [])}
            mek, mover = ids.get(CARRIER), ids.get(mover_vis)
            if mek is None or mover is None or not act.get(mover):
                causes["montage"] += 1
                continue
            _dv, ctx, wt = _ctx_for(sid, rid, mover)
            base = _score_map(ctx, wt, with_term=False)
            on = _score_map(ctx, wt, with_term=True)
            nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx.neigh_by_pos or {}).items()}
            order = sorted(base.items(), key=lambda kv: -kv[1])
            if len(order) < 2:
                causes["pas de paire a ecart STRICT"] += 1
                continue
            t1 = order[0][0]
            trouve = None
            for t2, s2 in order[1:]:
                gap = base[t1] - s2
                if gap > MAX_GAP:
                    break
                if gap < min_gap:
                    continue
                # le Big Mek doit etre voisin NATIF de T2 et PAS de T1 : c'est ce qui fait que le
                # terme s'ajoute a T2 seule.
                if cb in nb.get(t2, ()) and cb not in nb.get(t1, ()):
                    trouve = (t2, gap)
                    break
            if trouve is None:
                causes["pas de paire a ecart STRICT"] += 1
                continue
            t2, gap = trouve
            p_off = max(base, key=lambda k: base[k])
            p_on = max(on, key=lambda k: on[k])
            nat, pure, _row = _native_move(sid, rid, mover)
            print("  [%s/preplace] mover@%s mek@%s | T1=%s (%.2f) T2=%s (%.2f) ecart=%.2f"
                  % (mover_vis, cm, cb, t1, base[t1], t2, base[t2], gap))
            print("  [%s/preplace] terme(T1)=%+.1f terme(T2)=%+.1f | OFF=%s ON=%s NATIF=%s%s%s"
                  % (mover_vis, on.get(t1, 0) - base.get(t1, 0), on.get(t2, 0) - base.get(t2, 0),
                     p_off, p_on, nat, "" if pure else "  (proposition NON PURE : attaque)",
                     "   <-- BASCULE" if p_on != p_off else ""))
            if not pure:
                causes["proposition NON PURE (attaque)"] += 1
                continue                      # tuile issue du sweep d'ATTAQUE : hors modele
            out.update({"ok": True, "t1": t1, "t2": t2, "gap": gap, "mover": cm, "mek": cb,
                        "port_off": p_off, "port_on": p_on, "native": nat,
                        "term_t2": on.get(t2, 0) - base.get(t2, 0)})
            return out
        finally:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            Path(state).unlink(missing_ok=True)
    print("  [%s] REFUS : aucune des %d positions pre-placees n'a produit une paire a ecart >= %.0f"
          " avec proposition native PURE" % (mover_vis, min(essais, len(candidats)), min_gap))
    print("  [%s] ventilation des refus : %s"
          % (mover_vis, ", ".join("%s=%d" % kv for kv in sorted(causes.items()) if kv[1])))
    return out


def run_nonowner_preplace(sid, seeds, boards, movers, p_units, a_units, verbose,
                          min_gap=1.0, essais=12, loin=6) -> int:
    print("")
    print("=== ETAPE 2quater : face NON-OWNER, Big Mek PRE-PLACE au build (#271-r1 voie b) ===")
    rows = []
    for board in boards:
        for seed in seeds:
            print("-- board=%s seed=%s" % (board, seed))
            for m in movers:
                rows.append((board, seed, m,
                             step2_nonowner_preplace(sid, seed, board, m, p_units, a_units,
                                                     verbose, min_gap=min_gap,
                                                     essais=essais, loin=loin)))
    print("")
    print("=== BILAN ETAPE 2quater ===")
    concluants = 0
    for board, seed, m, r0 in rows:
        if not r0.get("ok"):
            print("%-10s %-6s %-16s : NON CONCLUANT" % (board, seed, m))
            continue
        concluants += 1
        verdict = ("NATIF == ON" if r0["native"] == r0["port_on"]
                   else "NATIF == OFF" if r0["native"] == r0["port_off"]
                   else "NATIF != les deux")
        print("%-10s %-6s %-16s : T1=%s T2=%s ecart STRICT=%.1f terme(T2)=%+.0f | OFF=%s ON=%s "
              "NATIF=%s | %s%s"
              % (board, seed, m, r0["t1"], r0["t2"], r0["gap"], r0["term_t2"],
                 r0["port_off"], r0["port_on"], r0["native"],
                 "BASCULE -> " if r0["port_on"] != r0["port_off"] else "pas de bascule -> ",
                 verdict))
    return 0 if concluants else 1


def run_nonowner(sid, seeds, boards, movers, p_units, a_units, verbose, pre_list=(0,),
                 min_gap=0.0) -> int:
    print("")
    print("=== ETAPE 2ter : face NON-OWNER (un AMI bouge, le Big Mek attire) ===")
    rows = []
    for board in boards:
        for seed in seeds:
            print("-- board=%s seed=%s" % (board, seed))
            for m in movers:
                for pre in pre_list:
                    res = step2_nonowner(sid, seed, board, m, p_units, a_units, verbose,
                                         pre_steps=pre, side="t2", min_gap=min_gap)
                    rows.append((board, seed, "%s/pas%d/T2" % (m, pre), res))
                    if res.get("ok"):
                        # MIROIR STRICT sur la MEME paire (T1,T2) : seul l'aimant change de cote.
                        mir = step2_nonowner(sid, seed, board, m, p_units, a_units, verbose,
                                             pre_steps=pre, side="t1", min_gap=min_gap,
                                             force_pair=(res["t1"], res["t2"]))
                        rows.append((board, seed, "%s/pas%d/T1" % (m, pre), mir))
                        break            # montage trouve : inutile d'avancer plus loin
    print("")
    print("=== BILAN ETAPE 2ter ===")
    for board, seed, m, r0 in rows:
        if not r0.get("ok"):
            print("%-10s %-6s %-16s : NON CONCLUANT" % (board, seed, m))
            continue
        print("%-10s %-6s %-16s : T1=%s T2=%s ecart=%.1f terme(T2)=%+.0f | OFF=%s ON=%s NATIF=%s"
              " | %s%s"
              % (board, seed, m, r0["t1"], r0["t2"], r0["gap"], r0["term_t2"],
                 r0["port_off"], r0["port_on"], r0["native"],
                 "BASCULE -> " if r0["port_on"] != r0["port_off"] else "pas de bascule -> ",
                 "NATIF == ON" if r0["native"] == r0["port_on"]
                 else ("NATIF == OFF" if r0["native"] == r0["port_off"] else "NATIF != les deux")))
    return 0


def run_driven(sid, seeds, boards, p_units, a_units, verbose,
               carrier=CARRIER, ability=ABILITY, min_gap=0.0) -> int:
    print("")
    print("=== ETAPE 2 : scenario CRAFTE (deplacement d'un allie) -- porteur %s, ability %d%s ==="
          % (carrier, ability, (" (ecart minimal %.0f)" % min_gap) if min_gap else ""))
    _AMPUTATE[0] = ability
    verdicts = []
    for board in boards:
        for seed in seeds:
            print("-- board=%s seed=%s" % (board, seed))
            res = {}
            for kind in ("none", "ork", "nonork"):
                res[kind] = step2_driven(sid, seed, board, kind, p_units, a_units, verbose,
                                         carrier=carrier, ability=ability, min_gap=min_gap)
            verdicts.append((board, seed, res))
    print("")
    print("=== BILAN ETAPE 2 ===")
    for board, seed, res in verdicts:
        for kind in ("none", "ork", "nonork"):
            r0 = res.get(kind) or {}
            if not r0.get("ok"):
                print("%-10s %-6s %-7s : NON CONCLUANT (montage non monte)" % (board, seed, kind))
                continue
            agree_on = (r0["native"] == r0["port_on"])
            agree_off = (r0["native"] == r0["port_off"])
            flip = r0["port_on"] != r0["port_off"]
            print("%-10s %-6s %-7s : T1=%s T2=%s ecart=%.1f terme(T2)=%+.1f | OFF=%s ON=%s NATIF=%s"
                  " | %s%s"
                  % (board, seed, kind, r0.get("t1"), r0.get("t2"), r0.get("gap", 0),
                     r0.get("term_t2", 0), r0["port_off"], r0["port_on"], r0["native"],
                     "BASCULE -> " if flip else "pas de bascule -> ",
                     ("NATIF == ON" if agree_on else ("NATIF == OFF" if agree_off
                                                      else "NATIF != les deux"))))
    return 0


# --------------------------------------------------------------------------------------------
# ETAPE 3 - GARDE D'ADJACENCE : quel predicat du port reproduit le voisinage NATIF ?
#
# Trouve en cherchant pourquoi l'etape 2 rendait « le natif ne suit pas » MEME sur un terme dont la
# vivacite est etablie (GuardianOrganism 1181, case-36). La reponse n'etait pas dans le terme : le
# port comptait un voisin que le NATIF ne compte pas. `IBattleQuery.GetAdjacent{Friends,Enemies}`
# passe par `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui
# applique un gate INCONDITIONNEL `abs(elev(tuile) - elev(voisin)) < 2`.
# --------------------------------------------------------------------------------------------
def step3_adjacency(sid, seeds, boards, p_units, a_units) -> int:
    import hexgeo
    from engine import battle_query as bq
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    print("")
    print("=== ETAPE 3 : predicat d'adjacence du port vs voisinage NATIF (boardGraph) ===")
    rc = 0
    for board in boards:
        seed = seeds[0]
        rid, state = _build(seed, board, p_units, a_units, [])
        if rid is None:
            return 1
        try:
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 8}, 180)
            uid = (dv.get("units") or [{}])[0].get("id")
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            mv = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt = W.load()
            pred = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mv, uid, wt, pred)
            nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx.neigh_by_pos or {}).items()}
            elev = ctx.elev_by_pos
            n = h_bad = b_bad = 0
            ex = []
            for p in nb:
                for q in nb:
                    if p >= q:
                        continue
                    n += 1
                    nat = q in nb[p]
                    if (hexgeo.distance(p, q) == 1) != nat:
                        h_bad += 1
                        if len(ex) < 4:
                            ex.append((p, q, elev.get(p), elev.get(q)))
                    if bq.is_adjacent(p, q, elev) != nat:
                        b_bad += 1
            print("  %-10s %5d paires | hexgeo nu FAUX=%-3d | bq.is_adjacent FAUX=%d"
                  % (board, n, h_bad, b_bad))
            for p, q, ep, eq in ex:
                print("        ex : %s(elev %s) / %s(elev %s) -- hexgeo dit voisins, le natif NON"
                      % (p, ep, q, eq))
            if b_bad:
                rc = 1
        finally:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            Path(state).unlink(missing_ok=True)
    print("  VERDICT : %s" % ("bq.is_adjacent == voisinage natif sur tous les boards testes"
                              if rc == 0 else "ECART -- le predicat du port n'est plus exact"))
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--p-units", default=DEFAULT_P)
    ap.add_argument("--a-units", default=DEFAULT_A)
    ap.add_argument("--extra", default="", help="args supplementaires de `rl_duel build`")
    ap.add_argument("--driven", action="store_true",
                    help="ETAPE 2 : scenario CRAFTE (deplacement d'un allie) au lieu de la marche")
    ap.add_argument("--seeds", default="", help="etape 2 : seeds separees par des virgules")
    ap.add_argument("--boards", default="", help="etape 2 : boards separes par des virgules")
    ap.add_argument("--carrier", default=CARRIER,
                    help="etape 2 : porteur (CONTROLE DE L'INSTRUMENT : tyranTyrantGuard/1181)")
    ap.add_argument("--ability", type=int, default=ABILITY, help="etape 2 : ability du porteur")
    ap.add_argument("--gap-min", type=float, default=0.0,
                    help="etape 2 : ecart MINIMAL T1-T2 exige. >10 isole le FACTEUR 2 (x2 si Ork) : "
                         "un ami non-Ork (+10) ne suffit plus, un ami Ork (+20) oui")
    ap.add_argument("--loin", type=int, default=6,
                    help="etape 2quater : distance hex MINIMALE aux ennemis (ecarte les positions "
                         "ou la proposition native serait une ATTAQUE, hors du modele de move)")
    ap.add_argument("--essais", type=int, default=12,
                    help="etape 2quater : positions pre-placees essayees par (board, seed, mover)")
    ap.add_argument("--preplace", action="store_true",
                    help="ETAPE 2quater (#271-r1 voie b) : Big Mek PRE-PLACE au build (--place), "
                         "donc sans consommer d'action ni dependre de sa portee")
    ap.add_argument("--nonowner", default="",
                    help="ETAPE 2ter : movers (visualIds, virgules) pour la face NON-OWNER")
    ap.add_argument("--pre-steps", default="0",
                    help="etape 2ter : chunks NATIFS joues avant le montage (liste, essayes en ordre)")
    ap.add_argument("--swap", action="store_true",
                    help="ETAPE 2bis : echange de factions a geometrie identique (isole le x2)")
    ap.add_argument("--adjacency", action="store_true",
                    help="ETAPE 3 : re-derive la garde d'adjacence (hexgeo nu vs bq.is_adjacent)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    rc = step0_weights()
    if rc or a.offline_only:
        return rc

    sid = _resolve_session()
    seeds = [s for s in (a.seeds or a.seed).split(",") if s]
    boards = [b for b in (a.boards or a.board).split(",") if b]
    if a.adjacency:
        return step3_adjacency(sid, seeds, boards, a.p_units, a.a_units)
    if a.nonowner and a.preplace:
        return run_nonowner_preplace(sid, seeds, boards,
                                     [m for m in a.nonowner.split(",") if m],
                                     a.p_units, a.a_units, a.verbose,
                                     min_gap=(a.gap_min or 1.0), essais=a.essais,
                                     loin=a.loin)
    if a.nonowner:
        pre = [int(x) for x in a.pre_steps.split(",")] if a.pre_steps else [0]
        return run_nonowner(sid, seeds, boards, [m for m in a.nonowner.split(",") if m],
                            a.p_units, a.a_units, a.verbose, pre_list=pre, min_gap=a.gap_min)
    if a.swap:
        return run_swap(sid, seeds, boards, a.p_units, a.a_units, a.verbose)
    if a.driven:
        return run_driven(sid, seeds, boards, a.p_units, a.a_units, a.verbose,
                          carrier=a.carrier, ability=a.ability, min_gap=a.gap_min)

    rid, state = _build(a.seed, a.board, a.p_units, a.a_units, a.extra.split() if a.extra else [])
    if rid is None:
        return 1
    try:
        return run(sid, rid, a.steps, a.verbose)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        Path(state).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
