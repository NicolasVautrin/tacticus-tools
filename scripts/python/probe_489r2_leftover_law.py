#!/usr/bin/env python
"""Probe #489-r2 -- LA LOI de `ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits`, lue sur
l'index d'OVERKILL et non sur celui de la MORT.

CE QUE CE PROBE MESURE, ET POURQUOI IL A DEUX BRAS
--------------------------------------------------
`GetLeftOverHits` compte les entrees `LeftOverDamages` de la CIBLE dont le FLAG (`+0x78`) est vrai
ET dont l'`AbilityOrEffect` (`+0x18`) est la notre, puis ajoute `extraHits` des que la liste est
NON VIDE. Les entrees viennent des TROIS call-sites d'
`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit`, RELUS AU BUILD COURANT :

  (a) `UnitExtensions.HasFlag(target, UnitFlag.Overkilled = 8)` en TETE d'
      `ApplyDamageOperation$$Execute` -> entree flag LITTERAL **1**, puis `return` : ce coup-la
      n'emet AUCUN event et ne mute RIEN ;
  (b) sous le gate `0 < DamageAppliedResult.get_Damage(result)`, si `HealthComponent.IsDead(hp)`
      AVANT la mutation -> entree, flag = ce meme `IsDead` d'avant (donc VRAI) ;
  (c) sous le gate `0 < <reduction REELLEMENT appliquee>` (le retour de
      `FillUpStatComponent$$Reduce`), si `IsDead(hp)` APRES la mutation -> entree, flag = l'`IsDead`
      d'AVANT (donc FAUX sur le coup qui tue).

Et le flag `UnitFlag.Overkilled` est pose par `UnitFlagsComponent$$Add(flags, 8)` a la FIN du meme
`Execute`, sous `record+0xF (didOverkill) != 0 && UnitExtensions.CanBeOverkilled(target)` -- donc
APRES l'emission de son propre coup. L'index qui commande le site (a) est celui-la, pas celui de la
mort : c'est ce que `#489-r2` appelle `o`.

>>> CONSEQUENCE OBSERVATIONNELLE, ET C'EST TOUT LE MONTAGE : le nombre d'events de degat qu'un
>>> maillon MOURANT emet **EST** `o`. Les coups `1..o` traversent `Execute` en entier (le dernier
>>> avec `Amount = 0`, la cible etant deja a 0 PV) ; les coups `o+1..H` sortent au site (a) et
>>> n'emettent plus rien. `o` est donc NATIVEMENT LISIBLE, sans capteur neuf.

⚠ POURQUOI LE MONTAGE ECRIT DANS LA FICHE #489-r2 NE POUVAIT PAS TRANCHER : il proposait de lire
`overkill_at_hit` -- une valeur que le PORT calcule (`damage_hits.overkill_flag_posted_by_hit`).
Confronter la loi du port a l'index du port est la MEME tautologie que le VERDICT-4 de
`probe_489_fragstorm_grenade_launcher.py`, que `#489-r1` reprochait deja. Ici `o` est lu dans le
LIVE, et l'index du port n'est qu'un ETAGE de plus, confronte SEPAREMENT.

LES DEUX BRAS (meme montage, meme seed, une SEULE variable : les PV de la cible principale)
-------------------------------------------------------------------------------------------
  * bras TEMOIN  -- cible principale IMMORTELLE : elle survit, donc chaque coup emet son event et
                    `len(events) == H`. C'est la SEULE facon de lire H nativement (dans le bras
                    mortel, la salve est tronquee par le site (a) -- confondre les deux, c'est
                    exactement l'erreur « deux mesures prises a des TICKS differents »).
  * bras MORTEL  -- cible principale a `X` PV : `len(events) == o`, le DERNIER index a `Amount != 0`
                    est `k` (le coup qui tue ; les suivants appliquent 0), et le 2e maillon SURVIT
                    (les autres ennemis sont immortels) donc `len(events du 2e maillon) == report`.
    `k` et `o` sortent donc du MEME bras et du MEME tick.

LOIS CONFRONTEES (report = <compte flag-vrai> + extraHits, et `extraHits` vaut **0** pour 1129 --
`extraHitsAfterTargetKilled` est passe **null**, cf. `abilities/worldeaters.py`) :

    L1  max(0, H - k - 1)   le port au 2026-08-17 (`_left_over_hits`)
    L2  max(0, H - k)       « les coups joues apres la mort » -- REFUTEE LIVE par #489-r1
    L3  max(0, H - o)       les seuls coups gates par le SITE (A)
    L4  max(0, H - o + 1)

⚠ LE REGIME QUI SEPARE L1 DE L3 est celui ou `o != k + 1`. `o` est le premier coup dont le CUMUL
de degat demande atteint le seuil d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`
(`accum >= PV de depart` ET excedent >= `overkillDmgPctOfHealth`, sinon `isCritical`) : viser des
PV BAS (un seul coup double les PV -> `o = k`) et des PV HAUTS (il faut deux coups de plus ->
`o = k + 2`). Un balayage qui ne rendrait que `o = k + 1` ne conclurait RIEN.

ASCII only (cp1252). Usage :
    python probe_489r2_leftover_law.py [--seed 4242] [--board MC1_67] [--attacks 3]
                                       [--main-hp 900,1800,3000,5200]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_116_necrons import (_alive_units, _build, _capture, _cast_live, _dispose,   # noqa: E402
                               _from_here, _live_per_hit, _offline_cast, _r, _tid,
                               _unit_of)
from probe_505_bloody_fury import (RING_TILES, WRASK_TILE, _dec, _drive_attacks,       # noqa: E402
                                   _pos_of, _turn_of, _adjacents)
from rl_collect_batch import _resolve_session                                          # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                      # noqa: E402
from engine.runner.components import UnitComponent                                     # noqa: E402

ROOT = PYDIR.parents[1]
BLOODY_FURY = int(ActiveAbilityType.BloodyFury)          # 1129
#: `extraHitsAfterTargetKilled` = **null** pour 1129 (LU : `abilities/worldeaters.py`, le 8e argument
#: de `DSLBehaviors$$ChainLeftOverHitsAttackDamage`). C'est ce qui rend le report LISIBLE : le compte
#: d'entrees flag-vraies n'est pas noye dans un « +1 par ennemi tue ».
EXTRA_HITS_1129 = 0

_IMMORTEL = 400000


# ------------------------------------------------------------------ lecture NATIVE d'un maillon

def index_du_coup_fatal(per_hit_live) -> int:
    """`k` (1-BASED) = le DERNIER coup dont l'`Amount` live est NON NUL.

    C'est le coup qui met la cible a 0 PV : au-dela, `FillUpStatComponent$$Reduce` ne retire plus
    rien, donc l'event porte `Amount = 0` (mesure #462-r4e-o-r1 : `live = [2000, 0]`). Rend 0 si la
    cible n'est pas tombee (aucun `Amount` nul en queue)."""
    last = 0
    for i, a in enumerate(per_hit_live or []):
        if int(a) != 0:
            last = i + 1
    return last


def index_de_pose_du_flag(per_hit_live) -> int:
    """`o` (1-BASED) = le NOMBRE d'events emis par le maillon mourant.

    `ApplyDamageOperation$$Execute` sort au SITE (A) des que `HasFlag(target, UnitFlag.Overkilled)`
    est vrai a l'ENTREE du coup, AVANT toute emission ; et le flag est pose a la FIN du coup `o`.
    Les coups `1..o` emettent donc, les coups `o+1..H` non."""
    return len(per_hit_live or [])


# ------------------------------------------------------------------ les lois confrontees

def lois_candidates(H: int, k: int, o: int, extra: int) -> dict:
    """Les QUATRE formes en lice, evaluees sur un point de mesure. Aucune n'est privilegiee ici :
    c'est la table imprimee qui tranche, jamais un ajustement."""
    return {
        "L1 max(0,H-k-1)": max(0, H - k - 1) + extra,
        "L2 max(0,H-k)":   max(0, H - k) + extra,
        "L3 max(0,H-o)":   max(0, H - o) + extra,
        "L4 max(0,H-o+1)": max(0, H - o + 1) + extra,
    }


# ------------------------------------------------------------------ un bras de mesure

def bras(args, main_hp: int, label: str) -> dict:
    """UN bras complet : build -> snowball -> cast -> lecture des events. Rend un dict de MESURES
    (aucun verdict) ; `main_hp = None` => bras TEMOIN (cible principale immortelle).

    GEOMETRIE FIGEE AU BUILD, exactement comme `probe_505_bloody_fury.phase` et pour les memes deux
    raisons mesurees : un deplacement du caster attire l'OVERWATCH (le compteur `+0x34` monte sans
    que le probe le sache) et `applyAction move` consomme l'activation de l'unite deplacee."""
    st_file = Path(args.state_file or (ROOT / "logs" / "runners" / ("_489r2_%s.json" % label)))
    st_file.parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    a_units = [x for x in args.a_units.split(",") if x]
    placement = ["--place", "worldTerminator:%d,%d" % WRASK_TILE]
    for uid, tile in zip(a_units, RING_TILES):
        placement += ["--a-place", "%s:%d,%d" % (uid, tile[0], tile[1])]
    hp_main = _IMMORTEL if main_hp is None else int(main_hp)
    placement += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (a_units[0], hp_main, hp_main)]
    tag = "[489r2/%s]" % label
    rid = _build(st_file, ["--seed", str(args.seed), "--board", args.board, "--rank", "17",
                           "--p-units", "worldTerminator", "--a-units", args.a_units,
                           "--no-ai", "--hp-player", "900000",
                           "--hp-target", str(_IMMORTEL)] + placement)
    out = {"label": label, "main_hp": main_hp, "ok": False}
    print("%s runner=%s board=%s seed=%s main_hp=%s" % (tag, rid, args.board, args.seed, hp_main))
    try:
        dec = _dec(sid, rid)
        w = _unit_of(dec, "worldTerminator")
        if w is None:
            print("%s Wrask ABSENT du deploiement -- montage a revoir" % tag)
            return out
        cid = int(w["id"])
        foes = [int(u["id"]) for u in _alive_units(dec) if not u.get("ctrl")]
        adj = _adjacents(dec, cid, foes)
        if len(adj) < 2:
            print("%s ECHEC DE MONTAGE : %d ennemi(s) adjacent(s) -- le report ne peut pas "
                  "s'exercer" % (tag, len(adj)))
            return out
        attaquants = [foes[i] for i in [int(x) for x in args.attackers.split(",") if x != ""]
                      if i < len(foes)]

        # --- SNOWBALL : les attaques recues, qui fixent H -----------------------------------------
        mkstate0, _d0, _b0 = _capture(sid, rid)
        _turn_of(sid, rid, cid, mine=False)
        delivered, per_turn, driven = _drive_attacks(sid, rid, cid, attaquants, args.attacks)
        if delivered != args.attacks:
            print("%s ECHEC DE MONTAGE : %d attaques sur %d" % (tag, delivered, args.attacks))
            return out
        _turn_of(sid, rid, cid, mine=True)
        _turn_of(sid, rid, cid, mine=False)     # tour ennemi BLANC (cf. probe_505)
        # `+0x34` cote PORT, rejoue depuis l'etat d'AVANT par le chemin reel (aucun RPC ne l'expose).
        from engine.runner.messages import AttackUnitMessage
        from engine.runner.runner import Runner
        st0 = mkstate0()
        rr = Runner(st0).install_default_handlers(20)
        for f, _nat in driven:
            rr.apply(AttackUnitMessage(attacker_id=int(f), target_id=int(cid)))
        k_off = int(st0.get_entity(cid).get_component(UnitComponent).total_times_attacked)
        _turn_of(sid, rid, cid, mine=True)

        dec = _dec(sid, rid)
        cid = int(_unit_of(dec, "worldTerminator")["id"])
        fh, tg = _from_here(sid, rid, cid, BLOODY_FURY)
        legal = [t for t in (_tid(x) for x in fh) if t is not None]
        if not legal:
            print("%s AUCUNE cible legale fromHere (targets=%s)" % (tag, tg))
            return out
        hp_of = {int(u["id"]): int(u.get("hp") or 0) for u in _alive_units(dec)}
        tid = min(legal, key=lambda t: (hp_of.get(t, 1 << 30), t))

        # --- OFFLINE (le PORT, pour l'etage `overkill_at_hit` et `applied_hits`) -------------------
        mkstate, dec, board = _capture(sid, rid)
        st = mkstate()
        st.get_entity(cid).get_component(UnitComponent).total_times_attacked = k_off
        diag = _offline_cast(st, cid, tid, BLOODY_FURY)
        chain = diag.get("chain") or []

        # --- LIVE -----------------------------------------------------------------------------------
        res = _cast_live(sid, rid, cid, tid, BLOODY_FURY, capture_events=True)
        live = _live_per_hit(res, BLOODY_FURY)
        ordre = list(live.keys())
        print("%s compteur `+0x34` (port) = %d -> H attendu = %d ; cible = u%s"
              % (tag, k_off, 1 + min(k_off, 7), tid))
        print("%s LIVE per-coup par cible : %s"
              % (tag, json.dumps({str(a): b for a, b in live.items()})))
        print("%s PORT chaine : %s"
              % (tag, [{"target": c.get("target"), "hits": c.get("hits"),
                        "applied_hits": c.get("applied_hits"),
                        "overkill_at_hit": c.get("overkill_at_hit")} for c in chain]))
        out.update(ok=True, k_off=k_off, target=int(tid), ordre=ordre,
                   live=live, chain=[{kk: vv for kk, vv in c.items() if kk != "attack"}
                                     for c in chain],
                   port_hits=(int(chain[0].get("hits")) if chain else None),
                   port_applied=(int(chain[0].get("applied_hits") or 0) if chain else None),
                   port_ovk_at=(chain[0].get("overkill_at_hit") if chain else None),
                   port_report=(int(chain[1].get("hits")) if len(chain) > 1 else 0))
        if ordre:
            ph = live.get(ordre[0]) or []
            out["live_maillon1"] = ph
            out["o_live"] = index_de_pose_du_flag(ph)
            out["k_live"] = index_du_coup_fatal(ph)
            out["report_live"] = len(live.get(ordre[1]) or []) if len(ordre) > 1 else 0
    finally:
        if not args.keep:
            _dispose(st_file)
    return out


# ------------------------------------------------------------------ le verdict

def confronter(temoin: dict, mortels: list, extra: int = EXTRA_HITS_1129) -> int:
    """Table (H, k, o) -> report LIVE contre les quatre lois. Rend 0 si une loi UNIQUE explique
    TOUS les points, 1 sinon (aucune, ou plusieurs -- un balayage qui n'a pas separe ne conclut
    RIEN et doit le DIRE)."""
    if not temoin.get("ok") or not temoin.get("live"):
        print("[489r2] TEMOIN indisponible -- H n'est pas lisible nativement, aucun verdict")
        return 1
    ordre_t = temoin["ordre"]
    H_live = len(temoin["live"].get(ordre_t[0]) or [])
    H_port = temoin.get("port_applied")
    print("[489r2] H NATIF (bras TEMOIN, cible survivante -> 1 event = 1 coup) = %d "
          "; H port (applied_hits) = %s -> %s"
          % (H_live, H_port, "ACCORD" if H_port == H_live else "ECART (H n'est pas confrontable)"))
    if H_port != H_live:
        print("[489r2] Le nombre de coups DIVERGE entre port et natif : la loi de report n'est pas "
              "isolable sur ce montage (l'ecart serait impute au report alors qu'il est en amont).")
        return 1
    H = H_live
    print("[489r2] --- points de mesure ------------------------------------------------------")
    print("[489r2] %-8s %-3s %-3s %-3s %-24s %-7s %s"
          % ("PV", "H", "k", "o", "per-coup live maillon1", "report", "lois"))
    survivantes = None
    n_pts = 0
    for m in mortels:
        if not m.get("ok") or not m.get("live_maillon1"):
            print("[489r2] PV=%s : bras INDISPONIBLE" % m.get("main_hp"))
            continue
        k, o = m["k_live"], m["o_live"]
        rep = m["report_live"]
        if k == 0:
            print("[489r2] PV=%-6s cible NON tombee (aucun coup fatal) -- point NON PORTANT"
                  % m["main_hp"])
            continue
        if len(m.get("ordre") or []) < 2:
            print("[489r2] PV=%-6s AUCUN 2e maillon live -- report non lisible, point NON PORTANT"
                  % m["main_hp"])
            continue
        lois = lois_candidates(H, k, o, extra)
        ok = {n for n, v in lois.items() if v == rep}
        n_pts += 1
        survivantes = ok if survivantes is None else (survivantes & ok)
        print("[489r2] %-8s %-3d %-3d %-3d %-24s %-7d %s"
              % (m["main_hp"], H, k, o, m["live_maillon1"], rep,
                 " ".join("%s=%d%s" % (n, v, "*" if v == rep else "") for n, v in lois.items())))
        # ETAGE SEPARE : l'index d'overkill du PORT contre celui du NATIF. Une divergence ici
        # n'invalide pas la loi -- elle accuse `damage_hits.overkill_flag_posted_by_hit`.
        po = m.get("port_ovk_at")
        po1 = (int(po) + 1) if po is not None else None
        print("[489r2]          etage OVERKILL : o natif=%d ; port `overkill_at_hit`+1=%s -> %s"
              % (o, po1, "ACCORD" if po1 == o else "ECART (etage amont, cf. rapport)"))
    print("[489r2] ---------------------------------------------------------------------------")
    if not n_pts:
        print("[489r2] AUCUN point portant -- le balayage n'a rien mesure")
        return 1
    if survivantes is None or not survivantes:
        print("[489r2] AUCUNE des quatre lois n'explique les %d points : la forme est AILLEURS "
              "(cf. les trois call-sites en tete de ce fichier)" % n_pts)
        return 1
    if len(survivantes) > 1 and n_pts > 0:
        print("[489r2] %d lois restent INDISTINGUABLES sur ces %d points (%s) -- le balayage n'a "
              "PAS separe : viser un regime ou `o != k+1`"
              % (len(survivantes), n_pts, ", ".join(sorted(survivantes))))
        return 1
    print("[489r2] LOI UNIQUE retenue sur %d points : %s" % (n_pts, sorted(survivantes)[0]))
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--attacks", type=int, default=3)
    ap.add_argument("--a-units", default="eldarRanger,astraBullgryn,tauCrisis,necroWarden")
    ap.add_argument("--attackers", default="0,1,3",
                    help="INDICES des attaquants (tauCrisis EXCLU : son attaque normale incremente "
                         "`+0x34` TROIS fois, mesure #505)")
    ap.add_argument("--main-hp", default="900,1800,3000,5200",
                    help="PV de la SEULE cible fragile -- BALAYAGE de `k` ET de `o`")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    temoin = bras(args, None, "TEMOIN")
    mortels = [bras(args, hp, "MORTEL-%d" % hp)
               for hp in [int(x) for x in str(args.main_hp).split(",")]]
    rc = confronter(temoin, mortels)
    print("[489r2] rc=%s" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
