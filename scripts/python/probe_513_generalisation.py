"""probe_513 -- CONTRE-EPREUVES du foyer `APendingAttackEffect` et de la phase 2 de 1069.

`probe_513_seeker_phase2.py` mesure UN scenario. Celui-ci CHERCHE A LE CASSER : chaque bras
DEPLACE une variable dont le port pourrait dependre a tort, et confronte au natif.

  G1  AUTRE BOARD (`C1_02`)      : l'accord port/natif tient-il hors de MC1_67 ? Un port qui aurait
                                   absorbe une particularite de geometrie tomberait ici.
  G2  DEUX PORTEURS, DEUX CIBLES : deux effets 1123 vivants au MEME `On(0x15)`. Exerce la
                                   cardinalite du foyer (`EFFECT_TRIGGERS` instancie UN trigger PAR
                                   PORTEUR) et l'ordre des deux tirs. Un port qui ne firerait qu'une
                                   fois, ou qui attribuerait les deux missiles au meme attaquant,
                                   tombe ici -- et le total de degat le dit.
  G3  LE CASTER BOUGE HORS PORTEE: le `Triggered()` n'a AUCUN gate de distance (lu : son trigger est
                                   `On(0x15) & IsTurnOf(...)`, rien d'autre). Le missile DOIT partir
                                   quand meme. Un port qui aurait recopie la portee 5 du ciblage de
                                   l'ACTIVE tombe ici.

Sortie ASCII stricte. Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_513_generalisation.py [--only G1,G2,G3]
"""
from __future__ import annotations

import json
import sys

import probe_513_seeker_phase2 as P

SEEKER = P.SEEKER
SEEKER_TARGET = P.SEEKER_TARGET
SEEKER_AIMING = P.SEEKER_AIMING


def _cast_targets(sid, rid, caster_id):
    at = P.rpc(sid, "abilityTargets",
               {"runnerId": rid, "unitId": caster_id, "abilityType": SEEKER}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == SEEKER), {})
    return [int(t["targetId"]) for t in (ab.get("fromHere") or [])]


def g1(sid) -> bool:
    """AUTRE BOARD. Rejoue le scenario complet sur `C1_02` -- le montage force les positions, donc
    le seul degre de liberte qui bouge est la GEOMETRIE (elevation, couverture, adjacences)."""
    print("\n=== G1 -- AUTRE BOARD (C1_02) ===")
    m, dispose = P.measure(sid, board="C1_02", state_name="probe_513_g1")
    try:
        d_off = P._hp_delta(*m["off_hp"])
        d_live = P._hp_delta(*m["live_hp"])
        dmg_off = {k: v[0] - v[1] for k, v in d_off.items()}
        dmg_live = {k: v[0] - v[1] for k, v in d_live.items()}
        live_draws = m["live_draws"][1] - m["live_draws"][0]
        print("  cast port==natif : %s" % (m["off_cast"] == m["live_cast"]))
        print("  degat port=%s natif=%s   tirages port=%s natif=%s"
              % (dmg_off, dmg_live, m["off_draws"], live_draws))
        ok = (bool(dmg_live) and dmg_off == dmg_live and m["off_draws"] == live_draws
              and m["off_cast"] == m["live_cast"])
        print("  -> %s" % ("OK" if ok else "ECHEC"))
        return ok
    finally:
        dispose()


def g2(sid) -> bool:
    """DEUX PORTEURS, DEUX CIBLES : deux instances de 1123 vivantes au meme `On(0x15)`.

    Les deux `tauMarksman` castent dans le MEME tour (1069 termine le tour du caster, pas celui de
    l'equipe). Au tour suivant, le vecteur doit firer DEUX fois -- une par PORTEUR de 1123 -- et
    chaque missile doit venir de SON attaquant."""
    print("\n=== G2 -- DEUX PORTEURS, DEUX CIBLES ===")
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    state_path = P.LOGS / "probe_513_g2.json"
    rid = P.build(state_path, [
        "--seed", "777", "--board", P.BOARD,
        "--p-units", "tauMarksman,tauMarksman",
        "--a-units", "orksNob,orksRuntherd",
        "--place", "tauMarksman:2,2", "--place", "tauMarksman:1,2",
        "--a-place", "orksNob:3,3", "--a-place", "orksRuntherd:4,4"])
    try:
        P.bind_transport(sid)
        dec0 = P.decision(sid, rid)
        casters = [int(u["id"]) for u in dec0["units"] if u.get("visualId") == "tauMarksman"]
        if len(casters) < 2:
            print("  MONTAGE IMPOSSIBLE : %d tauMarksman (il en faut 2)" % len(casters))
            return False
        paires = []
        for c in casters:
            cibles = _cast_targets(sid, rid, c)
            if not cibles:
                print("  MONTAGE IMPOSSIBLE : u%d n'a aucune cible legale sur place" % c)
                return False
            paires.append((c, cibles))
        # APPARIEMENT PARFAIT : deux cibles DISTINCTES, sinon le regime teste n'est pas
        # << deux porteurs >>. On ENUMERE les couples plutot que de figer le premier caster --
        # figer u77 sur u83 rendait le montage impossible alors qu'un autre appariement existait.
        (ca, la), (cb, lb) = paires
        choix = [(ca, x, cb, y) for x in la for y in lb if x != y]
        if not choix:
            print("  MONTAGE IMPOSSIBLE : les deux porteurs ne voient qu'une seule cible commune "
                  "(u%d:%s / u%d:%s)" % (ca, la, cb, lb))
            return False
        c1, t1, c2, t2 = choix[0]
        print("  u%d -> u%d   et   u%d -> u%d" % (c1, t1, c2, t2))

        state, _ = P.load(sid, rid)
        P.seed_offline_rng(state, P.rng_dump(sid, rid))
        for c, t in ((c1, t1), (c2, t2)):
            _apply_active_ability(state, c, t, SEEKER)
            P.rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": c, "abilityType": SEEKER, "targetId": t}}, 90)
        # ⚠ LE JEU AUTO-ENDTURN quand TOUTES mes unites ont agi : apres le 2e cast la main est deja
        # passee a l'adversaire. Un `endturn` en aveugle aurait donc RENDU MON TOUR -- et fait
        # partir les deux missiles -- AVANT la mesure de reference. On borne sur `currentPlayer`,
        # jamais sur un nombre de `endturn`.
        mon_joueur = P._player_of(state, c1)
        live_hp0 = P.hp_live(sid, rid)
        rng_avant = P.rng_dump(sid, rid)
        for _ in range(4):
            if int((P.decision(sid, rid) or {}).get("currentPlayer", -1)) == mon_joueur:
                break
            P.rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        rng_off = P.seed_offline_rng(state, rng_avant)
        off_hp0 = P.hp_off(state)
        tirs = delayed_attack_triggers(state, mon_joueur)
        off_hp1 = P.hp_off(state)
        live_hp1 = P.hp_live(sid, rid)
        rng_apres = P.rng_dump(sid, rid)

        d_off = {k: off_hp0[k] - off_hp1.get(k, off_hp0[k])
                 for k in off_hp0 if off_hp1.get(k) != off_hp0[k]}
        d_live = {k: live_hp0[k] - live_hp1.get(k, live_hp0[k])
                  for k in live_hp0 if live_hp1.get(k) != live_hp0[k]}
        attaquants = sorted(int(x["attacker"]) for x in tirs)
        porteurs = sorted(int(x["owner"]) for x in tirs)
        live_draws = int(rng_apres.get("callCount") or 0) - int(rng_avant.get("callCount") or 0)
        print("  port  : %d tir(s), attaquants=%s porteurs=%s" % (len(tirs), attaquants, porteurs))
        print("  degat port=%s   natif=%s" % (d_off, d_live))
        print("  tirages port=%s natif=%s" % (rng_off.call_count, live_draws))
        ok = (len(tirs) == 2 and attaquants == sorted([c1, c2]) and porteurs == sorted([t1, t2])
              and d_off == d_live and len(d_live) == 2 and rng_off.call_count == live_draws)
        print("  -> %s" % ("OK" if ok else "ECHEC"))
        return ok
    finally:
        P.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)


def g3(sid) -> bool:
    """LE CASTER BOUGE HORS PORTEE avant que le missile ne parte.

    Le `Triggered()` d'`APendingAttackEffect` n'a que `On(0x15) & IsTurnOf(<attaquant>)` : ni
    distance, ni ligne de vue, ni verification que la cible soit encore ciblable. Le missile doit
    donc partir meme si l'attaquant s'est mis hors de la portee 5 de l'ACTIVE."""
    print("\n=== G3 -- LE CASTER BOUGE HORS PORTEE ===")
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    state_path = P.LOGS / "probe_513_g3.json"
    rid = P.build(state_path, [
        "--seed", "777", "--board", P.BOARD,
        "--p-units", "tauMarksman,tauShadowsun",
        "--a-units", "orksNob,orksRuntherd",
        "--place", "tauMarksman:2,2", "--place", "tauShadowsun:1,2",
        "--a-place", "orksNob:2,5", "--a-place", "orksRuntherd:4,4"])
    try:
        P.bind_transport(sid)
        dec0 = P.decision(sid, rid)
        cid = int(P.find(dec0, "tauMarksman")["id"])
        cibles = _cast_targets(sid, rid, cid)
        if not cibles:
            print("  MONTAGE IMPOSSIBLE : aucune cible legale sur place")
            return False
        tid = cibles[0]
        # 1) cast des deux cotes
        state, _ = P.load(sid, rid)
        P.seed_offline_rng(state, P.rng_dump(sid, rid))
        _apply_active_ability(state, cid, tid, SEEKER)
        P.rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "abilityType": SEEKER, "targetId": tid}}, 90)
        # 2) tour ennemi NU, puis on ELOIGNE le caster avant que son tour ne commence : le natif
        #    n'accepte un `move` que pendant SON tour -> on deplace au tour SUIVANT, donc APRES le
        #    tir. Le levier qui marche AVANT le tir est de bouger l'unite DANS le meme tour que le
        #    cast : impossible (1069 termine le tour). On mesure donc la DISTANCE au moment du tir
        #    et on verifie qu'aucun gate ne la lit -- en ELOIGNANT la CIBLE, que l'IA, elle, peut
        #    bouger. A defaut d'IA, on constate la distance effective et on l'ECRIT.
        P.rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        rng_avant = P.rng_dump(sid, rid)
        P.seed_offline_rng(state, rng_avant)
        # 2bis) DEPLACEMENT FORCE cote PORT : on met l'attaquant a l'autre bout du plateau. C'est
        # une greffe d'ETAT (pas un ordre de jeu) -- elle exerce le gate, pas le pathfinding.
        from engine.runner.components import PositionComponent
        pc = state.get_entity(cid).get_component(PositionComponent)
        avant = (pc.col, pc.row)
        loin = _tuile_libre_loin(state, tid)
        if loin is None:
            print("  MONTAGE IMPOSSIBLE : aucune tuile libre eloignee")
            return False
        pc.col, pc.row = loin
        import hexgeo
        tpc = state.get_entity(tid).get_component(PositionComponent)
        dist = hexgeo.distance((pc.col, pc.row), (tpc.col, tpc.row))
        print("  attaquant deplace %s -> %s ; distance a la cible = %d (portee de l'ACTIVE = 5)"
              % (avant, loin, dist))
        off_hp0 = P.hp_off(state)
        tirs = delayed_attack_triggers(state, P._player_of(state, cid))
        off_hp1 = P.hp_off(state)
        d_off = {k: off_hp0[k] - off_hp1.get(k, off_hp0[k])
                 for k in off_hp0 if off_hp1.get(k) != off_hp0[k]}
        print("  port : %d tir(s), degat=%s" % (len(tirs), d_off))
        ok = dist > 5 and len(tirs) == 1 and bool(d_off)
        print("  -> %s (OFFLINE PUR -- le natif ne peut pas etre mis dans ce regime sans un tour "
              "d'IA ; residu nomme)" % ("OK" if ok else "ECHEC"))
        return ok
    finally:
        P.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)


def _tuile_libre_loin(state, tid):
    """La tuile la PLUS ELOIGNEE de la cible parmi les tuiles libres du plateau."""
    import hexgeo
    from engine.runner.components import PositionComponent
    b = state.board
    if b is None:
        return None
    tpc = state.get_entity(tid).get_component(PositionComponent)
    occupees = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        if pc is not None:
            occupees.add((pc.col, pc.row))
    # `elev_by_pos` est le seul recensement EXHAUSTIF des positions du plateau expose par `Board`
    # (une entree par tuile). `walkable` filtre les murs.
    libres = [t for t in (b.elev_by_pos() or {})
              if t not in occupees and b.walkable(b.id_at(t[0], t[1]))]
    if not libres:
        return None
    return max(libres, key=lambda t: hexgeo.distance(t, (tpc.col, tpc.row)))


def main() -> int:
    sid = P._session()
    seul = None
    if "--only" in sys.argv:
        seul = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    res = {}
    for nom, fn in (("G1", g1), ("G2", g2), ("G3", g3)):
        if seul and nom not in seul:
            continue
        res[nom] = fn(sid)
    print("\nBILAN : %s" % json.dumps({k: ("OK" if v else "ECHEC") for k, v in res.items()}))
    print("PROBE %s" % ("OK" if all(res.values()) else "ECHEC"))
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
