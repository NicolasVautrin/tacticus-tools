"""probe #488 -- `1087 ExemplarOfTheKauyon` : MESURE de la face COMBAT, etage par etage.

LE CRITERE, POSE AVANT TOUTE METHODE
------------------------------------
Trois questions BINAIRES, chacune confrontee au NATIF, jamais entre deux sorties du port :

  E1 TELEPORT   -- apres le cast, le caster est-il sur la TUILE CIBLE, cote natif ET cote port ?
  E2 SPAWN      -- une unite `tauSmnDroneCommandLink` apparait-elle sur l'EX-tuile du caster, avec
                   le trait `Stationary` (0x418), cote natif ET cote port ?
  E3 ATTAQUE    -- le caster porte-t-il UNE attaque normale depuis sa nouvelle position, et le
                   nombre de COUPS vaut-il `arme + nrOfHits` (l'effet 1181 pose puis retire par le
                   cast) ? On compare le COMPTE de coups natif au compte porte.

Le port est joue sur un `State` charge du snapshot pris JUSTE AVANT le cast natif -- donc les deux
faces partent du meme substrat. Aucun scalaire n'est ajuste : chaque etage rend son propre verdict.

CE QUI EST MESURE, ET CE QUI NE L'EST PAS
-----------------------------------------
* La VALEUR des degats n'est pas re-confrontee ici : elle l'est deja, bit a bit, par
  `probe_366r1_exemplar_kauyon_hits.py` / `test_exemplar_of_the_kauyon_hits_live.py` (canal #179).
  Ce probe mesure ce que 1087 AJOUTE : la pose/depose de l'effet AUTOUR de l'attaque, le teleport et
  le spawn. Le COMPTE de coups suffit a etablir que l'effet a bien mordu.
* Le TIRAGE du repli de tuile de spawn (`SortByDistance(Randomize(AllTiles), exTile)`) n'est PAS
  confronte : il n'entre en jeu que si l'ex-tuile est prise, ce que ce montage ne produit pas.

MONTAGE -- reutilise le FOYER de `probe_366r1_exemplar_kauyon_hits.py` (`build_extra`, `arrange`,
`legal_destinations`) : meme roster, memes neutralisations de confond (crit/block a 0, PV a 300000
des DEUX cotes), meme geometrie « ennemi ancre / allie a d=2 / Shadowsun exilee a d>=4 ».

Usage :
    python probe_488_exemplar_of_the_kauyon.py [--board MC1_67] [--seed 777] [--keep]
    python probe_488_exemplar_of_the_kauyon.py --mutant     # vue ROUGE : 1087 RETIRE du registre
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

import hexgeo
import probe_366r1_exemplar_kauyon_hits as P366

HOST = P366.HOST
CARRIER = P366.CARRIER
ALLY = P366.ALLY
EXEMPLAR_OF_THE_KAUYON = P366.EXEMPLAR_OF_THE_KAUYON      # 1087
EFFECT_TYPE = P366.EFFECT_TYPE                            # 1181
SUMMON_VISUAL = "tauSmnDroneCommandLink"                  # `GetStringConstant(config, 0)` = unitId
STATIONARY = 0x418                                        # `UnitTrait.Stationary` (1048)


# ------------------------------------------------------------------ mesure NATIVE

def snapshot(sid, rid):
    """Le substrat COMMUN aux deux faces : ce que le port rechargera pour rejouer le meme cast."""
    return {"dv": P366.dview(sid, rid),
            "ob": P366._rpc(sid, "observeBattle", {"runnerId": rid}, 60),
            "snap": P366._rpc(sid, "combatSnapshot", {"runnerId": rid}, 90),
            "rng": P366._rpc(sid, "dumpRng", {"runnerId": rid}, 40)}


def traits_of(snap, uid):
    for u in ((snap or {}).get("units") or []):
        if u.get("entityId") == uid:
            return [int(t) for t in (u.get("traits") or [])]
    return []


def hits_count(res, attacker):
    """Les coups emis PAR `attacker` dans l'action : nombre, cibles, total. Toutes cibles confondues."""
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    n, cibles, total, detail = 0, [], 0, []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Attacker_Id") == attacker:
            n += 1
            total += int(td["Amount"])
            detail.append({"amount": int(td["Amount"]),
                           "profile": td.get("DamageProfile_Type") or td.get("DamageProfile"),
                           "effect": td.get("Effect_Type")})
            if td.get("Target_Id") is not None:
                cibles.append(int(td["Target_Id"]))
    return n, bool(a0.get("ok")), sorted(set(cibles)), total, detail


def cast_natif(sid, rid, board, verbose=True):
    """Joue le cast NATIF et rend tout ce que les trois etages exigent, snapshot AVANT compris."""
    plan = P366.arrange(sid, rid, board, verbose=verbose)
    if plan is None:
        return None
    if P366.reach_my_turn(sid, rid, plan["my_player"]) is None:
        print("[488] ABORT tour non atteint")
        return None
    dests = P366.legal_destinations(sid, rid, plan["carrier"])
    dests = sorted((d for d in dests if d != plan["anchor"]),
                   key=lambda d: hexgeo.distance(d, plan["anchor"]))
    if not dests:
        print("[488] ABORT aucune destination legale (le gate natif refuse tout)")
        return None
    dst = dests[0]
    avant = snapshot(sid, rid)
    pos_avant = {u["id"]: P366.upos(u) for u in P366.alive(avant["dv"])}
    ex_tile_pos = pos_avant.get(plan["carrier"])
    ids_avant = set(pos_avant)
    if verbose:
        print("[488] dst=%s d(enemy)=%d ex_tile=%s (%d destinations legales natives)"
              % (dst, hexgeo.distance(dst, plan["anchor"]), ex_tile_pos, len(dests)))
    res = P366._rpc(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "ability", "casterId": plan["carrier"],
         "to": {"col": dst[0], "row": dst[1]}, "abilityType": EXEMPLAR_OF_THE_KAUYON}]}, 180)
    n_hits, ok, cibles, total, detail = hits_count(res, plan["carrier"])
    apres_dv = P366.dview(sid, rid)
    apres_snap = P366._rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    pos_apres = {u["id"]: P366.upos(u) for u in P366.alive(apres_dv)}
    neufs = [u for u in P366.alive(apres_dv) if u.get("id") not in ids_avant]
    return {"plan": plan, "dst": dst, "ex_tile_pos": ex_tile_pos, "avant": avant, "ok": ok,
            "dests": dests, "n_hits": n_hits, "targets": cibles, "total": total, "detail": detail,
            "carrier_after": pos_apres.get(plan["carrier"]),
            "spawned": [{"id": u.get("id"), "visualId": u.get("visualId"), "pos": P366.upos(u),
                         "traits": traits_of(apres_snap, u.get("id"))} for u in neufs]}


# ------------------------------------------------------------------ rejeu PORTE

def rejeu_porte(rec, board):
    """Rejoue le MEME cast hors-ligne, depuis le snapshot pris AVANT le cast natif."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state
    from engine.runner.components import PositionComponent, StatsComponent
    from engine.entities.traits.unit_trait import UnitTrait, has_trait

    s = rec["avant"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=board)
    dump = s["rng"]
    if isinstance(dump, dict) and dump.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(dump["mt"])
        rng.mti = dump["mti"]
        st.rng = rng
    cid = rec["plan"]["carrier"]
    dest_id = st.board.id_at(rec["dst"][0], rec["dst"][1])
    avant_ids = set(st.entities)
    # ESPION sur le foyer d'attaque. `PerformAIAttack` -> `perform_ai_ability_unit_behaviour` appelle
    # `AttackDamageOperation.execute` DIRECTEMENT (l'attaque IA n'est pas un `AttackUnitMessage`),
    # donc `DamageHandler.last` reste VIDE : le compte de coups ne s'y lit pas. On capture le retour
    # de l'operation elle-meme, qui porte `per_hit` (phase ARME) et `additional_hits.per_hit` (#179).
    from engine.runner.operations.damage import AttackDamageOperation
    captures: list = []
    _vrai = AttackDamageOperation.execute

    def _espion(state, attacker_id, target_id, *args, **kw):
        r = _vrai(state, attacker_id, target_id, *args, **kw)
        captures.append({"attacker": attacker_id, "target": target_id, "r": r})
        return r

    AttackDamageOperation.execute = staticmethod(_espion)
    try:
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=dest_id,
                                          ability_type=EXEMPLAR_OF_THE_KAUYON))
    finally:
        AttackDamageOperation.execute = staticmethod(_vrai)
    last = getattr(runner.ability_handler, "last", None) or {}
    e = st.get_entity(cid)
    p = e.get_component(PositionComponent) if e is not None else None
    carrier_after = (p.col, p.row) if p is not None else None
    neufs = []
    for eid in sorted(set(st.entities) - avant_ids):
        ent = st.get_entity(eid)
        pp = ent.get_component(PositionComponent) if ent is not None else None
        sc = ent.get_component(StatsComponent) if ent is not None else None
        tr = getattr(getattr(sc, "ctx", None), "traits", None)
        neufs.append({"id": eid, "visualId": getattr(getattr(sc, "ctx", None), "visual_id", None),
                      "pos": (pp.col, pp.row) if pp is not None else None,
                      "stationary": bool(has_trait(tr or set(), UnitTrait.Stationary))})
    n_hits, cibles, total, detail = 0, [], 0, []
    for c in captures:
        if c["attacker"] != cid or not isinstance(c["r"], dict):
            continue
        r = c["r"]
        n_hits += len(r.get("per_hit") or [])
        n_hits += len(((r.get("additional_hits") or {}).get("per_hit")) or [])
        cibles.append(int(c["target"]))
        total += int(r.get("total") or 0)
        detail.append({"per_hit": list(r.get("per_hit") or []),
                       "additional": list(((r.get("additional_hits") or {}).get("per_hit")) or []),
                       "total": r.get("total"), "shield": r.get("shield_dmg"),
                       "armor": r.get("armor_dmg"), "profile": r.get("profile")})
    return {"last": last, "carrier_after": carrier_after, "spawned": neufs, "n_hits": n_hits,
            "targets": cibles, "total": total, "captures": captures, "detail": detail}


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--mutant", action="store_true",
                    help="rejoue le port avec 1087 RETIRE d'`ABILITY_CLASSES` (vue ROUGE : "
                         "le no-op silencieux d'avant #488 doit ressortir)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sid = P366._sid()
    print("[488] session=%s board=%s seed=%s" % (sid, a.board, a.seed))
    from engine.entities.pathfinding.board import Board
    sf = os.path.join(tempfile.gettempdir(), "p488_%s_%s.json" % (a.board, os.getpid()))
    rid = None
    rc = 1
    try:
        rid = P366.build(a.seed, a.board, sf)
        if rid is None:
            print("[488] ABORT build KO")
            return 1
        # Le board du PORT est celui du runner LIVE (`boardGraph`), pas un dump relu : c'est le
        # substrat que `load_state` recevra, donc les deux faces indexent les MEMES ids de tuile.
        bg = P366._rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        rec = cast_natif(sid, rid, board)
        if rec is None:
            return 1
        print("[488] NATIF   ok=%s carrier %s -> %s | hits=%d | spawned=%s"
              % (rec["ok"], rec["ex_tile_pos"], rec["carrier_after"], rec["n_hits"],
                 [(u["visualId"], u["pos"], STATIONARY in u["traits"]) for u in rec["spawned"]]))
        if a.mutant:
            from engine.runner.abilities.handler import ABILITY_CLASSES
            ABILITY_CLASSES.pop(EXEMPLAR_OF_THE_KAUYON, None)
            print("[488] MUTANT : 1087 retire d'ABILITY_CLASSES")
        port = rejeu_porte(rec, board)
        print("[488] PORTE   ported=%s carrier -> %s | hits=%d | spawned=%s"
              % ((port["last"] or {}).get("ported"), port["carrier_after"], port["n_hits"],
                 [(u["visualId"], u["pos"], u["stationary"]) for u in port["spawned"]]))
        e1 = (rec["carrier_after"] == rec["dst"] and port["carrier_after"] == rec["dst"])
        nat_sp = [u for u in rec["spawned"] if u["visualId"] == SUMMON_VISUAL]
        prt_sp = [u for u in port["spawned"] if u["visualId"] == SUMMON_VISUAL]
        e2 = (len(nat_sp) == 1 and len(prt_sp) == 1
              and nat_sp[0]["pos"] == rec["ex_tile_pos"] and prt_sp[0]["pos"] == rec["ex_tile_pos"]
              and STATIONARY in nat_sp[0]["traits"] and prt_sp[0]["stationary"])
        # La SEQUENCE, pas un total : le natif emet `arme... puis additionnels...` dans cet ordre, et
        # `AttackDamageOperation` rend les deux listes separement. Comparer un scalaire agrege
        # masquerait une compensation (2 coups justes + 2 faux peut donner la meme somme).
        seq_nat = [h["amount"] for h in rec["detail"]]
        seq_prt = []
        for d in port["detail"]:
            seq_prt += list(d["per_hit"]) + list(d["additional"])
        e3 = (rec["n_hits"] > 0 and seq_nat == seq_prt
              and rec["targets"] == sorted(set(port["targets"])))
        print("[488] E1 TELEPORT (natif %s / port %s / attendu %s) : %s"
              % (rec["carrier_after"], port["carrier_after"], rec["dst"], "OK" if e1 else "KO"))
        print("[488] E2 SPAWN    (natif %s / port %s / ex-tuile %s) : %s"
              % ([(u["visualId"], u["pos"]) for u in nat_sp],
                 [(u["visualId"], u["pos"]) for u in prt_sp], rec["ex_tile_pos"],
                 "OK" if e2 else "KO"))
        print("[488] NATIF detail %s" % (rec["detail"],))
        print("[488] PORTE detail %s" % (port["detail"],))
        print("[488] E3 COUPS    (natif %s sur %s / port %s sur %s) : %s"
              % (seq_nat, rec["targets"], seq_prt, sorted(set(port["targets"])),
                 "OK" if e3 else "KO"))
        rc = 0 if (e1 and e2 and e3) else 1
        print("[488] VERDICT : %s" % ("OK" if rc == 0 else "KO"))
        return rc
    finally:
        if rid is not None and not a.keep:
            P366._rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        if not a.keep:
            try:
                os.remove(sf)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())


