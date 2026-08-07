#!/usr/bin/env python
"""#498-r4-r1 -- CONFRONTATION LIVE de la FUITE de `UnitFlag.Undisplaceable` (0x19) hors de la
charge de `1152 UnstoppableMomentumReworked` (`orksNob` « Tanksmasha »).

CE QUE #498-r4 A LAISSE OUVERT. Le recensement EXHAUSTIF des ecrivains de `0x19` (10 appelants de
`IdunBattleLogic.Entities.DSLBehaviors$$AddFlag`, 40 sites d'
`IdunBattle.Entities.Components.UnitFlagsComponent$$Add`) a etabli que
`...UnstoppableMomentumReworkedAbility$$ExecuteBehaviour` en est le SEUL, et qu'il l'ENCADRE. Mais
l'encadrement n'est PAS hermetique -- le decompile, relu ici verbatim :

    Execute( AddFlag(Caster@0x48, 0x19) )
    cache = Cache( First( TilesBehindInLine(...), amount: this+0xf0 = 10 ), true )
    for (index = 0; index < this+0xf0; index++) {
        tile = SelectTile( AtIndex(cache, index) );
        if (tile == null) return;                      // <<< SORTIE SANS RemoveFlag
        if (!ExecuteBehaviourStep(...)) break;
    }
    Execute( RemoveFlag(Caster@0x48, 0x19) )

La boucle N'ITERE PAS sur le cache : elle l'INDEXE, jusqu'a `10`. Des que la ligne de charge est
plus COURTE que 10 tuiles ET que la charge la traverse INTEGRALEMENT (tous les pas rendent `true`),
`SelectTile` rend `null` et le natif SORT SANS retirer le flag. Le caster reste `Undisplaceable`
POUR LE RESTE DE LA BATAILLE : rien ne vient le lever
(`UnitFlagsComponent$$RemoveTurnFlags` ne retire que `0, 1, 2, 3, 4, 0xc, 0x1b`).

Le port portait un `try/finally` qui retirait TOUJOURS -- degradation PERMISSIVE : il rendait
deplacable un caster que le natif verrouille. Six lecteurs portes en dependent, dont la tete de
`IdunBattle.Operations.DisplaceUnitOperation$$Execute` (tout push / pull / deplacement direct /
echange de position visant le caster) et `IdunBattle.Core.Services.DamagePrediction$$GetKnockback`.

LES DEUX BRAS, ET CE QUI LES SEPARE (une seule variable : le CHEMIN DE SORTIE de la boucle) :

  `fuite`   -- la cible est au COIN (0,0), le caster charge depuis (1,0). `TilesBehindInLine`
               s'arrete au bord : la ligne fait UNE tuile. Le pas 0 rend `true` (l'echange de
               position ou le push+move continuent la charge), donc `index` passe a 1 et sort du
               cache -> `return` SANS retrait. NATIF ATTENDU : `0x19` PRESENT apres le cast.
  `retrait` -- un `tyranTyrantGuard` (BigTarget) adjacent : `IsDisplaceable` est FAUX, `Push` rend
               `false`, la tuile reste occupee -> `ExecuteBehaviourStep` rend `false` -> `break` ->
               le `RemoveFlag` EST joue. NATIF ATTENDU : `0x19` ABSENT apres le cast.

Un seul bras ne prouverait rien : `fuite` seul serait compatible avec « le port ne retire jamais »,
`retrait` seul avec « le port retire toujours » (le comportement d'AVANT).

CANAL DE MESURE : `combatSnapshot.units[].unitFlags` -- le capteur n'y lit aucun set en memoire, il
invoque `IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` par valeur d'enum et rend la liste
des ordinaux poses (`combatSnapshot.unitFlagTypes` donne le mapping nom -> id, LU au runtime).

ATTRIBUTION PAR DESARMEMENT CIBLE : `--temoin` (joue systematiquement) re-retire le flag apres le
cast offline, ce qui est EXACTEMENT ce que faisait le `try/finally` d'avant. Sous ce temoin, le bras
`fuite` doit DIVERGER du natif -- sinon le montage ne discrimine pas.

Usage (session warmee ; le probe monte et DISPOSE ses propres runners, un a la fois) :
    python scripts/python/probe_498r4r1_fuite_flag_undisplaceable_live.py
    python scripts/python/probe_498r4r1_fuite_flag_undisplaceable_live.py --only fuite
ASCII only ; exit 0 = les deux verdicts natifs exerces, port d'accord, temoin en desaccord.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_498_unstoppable_momentum as P498                             # noqa: E402
from engine.runner.abilities.loki import momentum as MOM                  # noqa: E402
from engine.runner.components import UnitFlagsComponent                   # noqa: E402
from engine.entities.unit_flag import UnitFlag                            # noqa: E402

ROOT = PYDIR.parents[1]
LOGS = ROOT / "logs"

UNDISPLACEABLE = int(UnitFlag.Undisplaceable)      # 0x19 = 25

#: `nom -> (montage de `probe_498_unstoppable_momentum.montages()`, flag natif ATTENDU apres le cast)
#: Les montages sont LUS de leur source unique -- aucun argument de `rl_duel build` n'est recopie ici.
BRAS = {
    "fuite": ("switch", True),
    "retrait": ("bigtarget", False),
}


@contextlib.contextmanager
def finally_avant():
    """LE PORT D'AVANT #498-r4-r1, substitue EN PLACE : un `try/finally` retirait
    `UnitFlag.Undisplaceable` sur TOUS les chemins de sortie, y compris le `return` du (4).

    Reproduit en RE-retirant le flag apres l'appel, ce qui est STRICTEMENT equivalent au `finally`
    et MINIMAL : on ne recopie pas la boucle, donc le temoin ne peut pas diverger du port sur autre
    chose que le chemin de retrait -- c'est ce qui rend l'attribution valable."""
    cls = MOM.UnstoppableMomentumReworkedAbility
    orig = cls.execute_behaviour

    def patched(self, state, caster_id, target_id):
        try:
            return orig(self, state, caster_id, target_id)
        finally:
            MOM._set_charge_flag(state, caster_id, False)

    cls.execute_behaviour = patched
    try:
        yield
    finally:
        cls.execute_behaviour = orig


def _flags_live(sid, rid, uid: int):
    """Les ordinaux `UnitFlag` poses sur `uid`, LUS du canal `combatSnapshot.units[].unitFlags`.
    Rend `None` (jamais `[]`) quand l'entite n'a pas de ligne ou que le canal est muet : un `[]`
    fabrique se lirait comme « aucun flag », donc comme une mesure."""
    snap = P498._r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    for row in list(snap.get("units") or []) + list(snap.get("unitsNotAlive") or []):
        if int(row.get("entityId") or -1) != int(uid):
            continue
        fl = row.get("unitFlags")
        return None if not isinstance(fl, list) else sorted(int(x) for x in fl)
    return None


def _flag_offline(state, uid: int):
    e = state.get_entity(int(uid))
    fc = e.get_component(UnitFlagsComponent) if e is not None else None
    if fc is None:
        return None
    return bool(fc.has(UNDISPLACEABLE))


def jouer(nom: str, seed: int, keep: bool) -> dict:
    phase, natif_attendu = BRAS[nom]
    args = P498.montages(seed)[phase]
    state_path = LOGS / ("rs_498r4r1_%s.json" % nom)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    sid = P498._resolve_session()
    rid = P498._build(state_path, args)
    out: dict = {"nom": nom, "phase": phase, "rid": rid, "natif_attendu": natif_attendu,
                 "fails": []}
    try:
        mkstate, dec0, board = P498._capture(sid, rid)
        caster = P498._unit_of(dec0, P498.CASTER_VISUAL)
        if caster is None:
            out["fails"].append("caster %s ABSENT du montage" % P498.CASTER_VISUAL)
            return out
        cid = int(caster["id"])
        out["caster"] = cid
        out["flags_avant"] = _flags_live(sid, rid, cid)
        fh = P498._from_here(sid, rid, cid, P498.MOMENTUM)
        if not fh:
            out["fails"].append("aucune cible legale `fromHere` pour 1152")
            return out
        import hexgeo
        cpos = P498._pos(caster)
        foes = [u for u in P498._alive(dec0) if int(u["id"]) != cid and not u.get("ctrl")]
        nearest = min(foes, key=lambda u: hexgeo.distance(cpos, P498._pos(u))) if foes else None

        def _tile_xy(t):
            if isinstance(t, dict) and t.get("col") is not None:
                return (t["col"], t["row"])
            tid = P498._tid(t)
            xy = board.coord(int(tid)) if tid is not None else None
            return (int(xy[0]), int(xy[1])) if xy is not None else None

        cands = [(t, _tile_xy(t)) for t in fh]
        cands = [(t, xy) for (t, xy) in cands if xy is not None]
        if nearest is not None:
            cands.sort(key=lambda tx: hexgeo.distance(tx[1], P498._pos(nearest)))
        aim_t, aim_xy = cands[0]
        aim_id = P498._tid(aim_t) or board.id_at(aim_xy[0], aim_xy[1])
        out["aim"] = aim_xy

        # ---------------------------------------------------------------- PORT (etat AVANT le cast)
        st = mkstate()
        h = P498._offline_cast(st, cid, aim_id, P498.MOMENTUM)
        last = h.last or {}
        res = last.get("res") if isinstance(last.get("res"), dict) else last
        out["ported"] = bool(last.get("ported"))
        out["line"] = list(res.get("line") or [])
        out["steps"] = res.get("steps")
        out["flag_leaked"] = res.get("flag_leaked")
        out["port"] = _flag_offline(st, cid)

        # ---------------------------------------------------------------- TEMOIN (le port d'AVANT)
        st_t = mkstate()
        with finally_avant():
            P498._offline_cast(st_t, cid, aim_id, P498.MOMENTUM)
        out["temoin"] = _flag_offline(st_t, cid)

        # ---------------------------------------------------------------- LIVE
        live = P498._cast_live(sid, rid, cid, aim_id, P498.MOMENTUM)
        out["live_ok"] = bool(live.get("ok"))
        out["flags_apres"] = _flags_live(sid, rid, cid)
        out["natif"] = (None if out["flags_apres"] is None
                        else UNDISPLACEABLE in out["flags_apres"])
    finally:
        if not keep:
            P498._dispose(state_path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="#498-r4-r1 : la fuite de UnitFlag.Undisplaceable hors de la charge, live")
    ap.add_argument("--only", default=None, choices=sorted(BRAS))
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    rc = 0
    natifs = []
    for nom in sorted(BRAS):
        if a.only is not None and nom != a.only:
            continue
        r = jouer(nom, a.seed, a.keep)
        print("")
        print("[498r4r1-live] bras %s (montage %s) -- porteur %s -- board %s -- runner %s"
              % (nom, r["phase"], P498.CASTER_VISUAL, P498.BOARD, r.get("rid")))
        for f in r["fails"]:
            print("   PAS MESURE : %s" % f)
            rc = 2
        if r["fails"]:
            continue
        print("   aim=%s | ligne portee (%d tuiles)=%s | pas joues=%s | flag_leaked=%s"
              % (r.get("aim"), len(r.get("line") or []), r.get("line"), r.get("steps"),
                 r.get("flag_leaked")))
        print("   flags LIVE du caster : avant=%s | apres=%s"
              % (r.get("flags_avant"), r.get("flags_apres")))
        if not r.get("ported"):
            print("   !! le port declare `ported=False` : le cast offline est un no-op")
            rc = max(rc, 2)
        if not r.get("live_ok"):
            print("   !! le cast LIVE a echoue -- rien a confronter")
            rc = max(rc, 2)
            continue
        if r.get("natif") is None:
            print("   !! canal `unitFlags` MUET pour le caster : PAS MESURE (jamais rabattu sur 0)")
            rc = max(rc, 2)
            continue
        # CONTROLE DE MONTAGE : le bras doit exercer le CHEMIN DE SORTIE qu'il annonce.
        courte = len(r.get("line") or []) < MOM.MAX_CHARGE_TILES
        if r["natif_attendu"] and not courte:
            print("   !! MONTAGE NON HONORE : la ligne fait %d tuiles (>= %d), le `return` du (4) "
                  "n'est pas atteignable" % (len(r.get("line") or []), MOM.MAX_CHARGE_TILES))
            rc = max(rc, 2)
        natifs.append(bool(r["natif"]))
        # LA RE PREDIT LE VERDICT NATIF. Si le natif dit autre chose, c'est la LECTURE du decompile
        # qui est fausse, et ca doit etre BRUYANT plutot que noye dans un accord port <-> natif.
        if bool(r["natif"]) != bool(r["natif_attendu"]):
            print("   !! PREDICTION DE LA RE NON CONFIRMEE : natif porte 0x19 = %s, attendu %s"
                  % (r["natif"], r["natif_attendu"]))
            rc = max(rc, 1)
        accord = bool(r["port"]) == bool(r["natif"])
        print("   0x19 apres le cast -- natif=%s | port=%s | temoin (le try/finally d'avant)=%s -> %s"
              % (r["natif"], r["port"], r["temoin"], "ACCORD" if accord else "DESACCORD"))
        if not accord:
            print("   !! ECART DE PORT sur ce bras")
            rc = max(rc, 1)
        # VUE ROUGE : sur le bras `fuite`, le port d'AVANT doit DIVERGER. S'il concorde, le montage
        # ne discrimine pas et l'accord ci-dessus ne prouve rien.
        if r["natif_attendu"] and bool(r["temoin"]) == bool(r["natif"]):
            print("   !! le montage ne DISCRIMINE pas : sous le `try/finally` d'avant, le port rend "
                  "le meme verdict que le natif")
            rc = max(rc, 1)
        if r["natif_attendu"]:
            print("   VUE ROUGE : le port d'avant PERDAIT le flag (temoin=%s) la ou le natif le "
                  "GARDE (%s)" % (r["temoin"], r["natif"]))
    print("")
    print("[498r4r1-live] NON-DEGENERESCENCE : verdicts natifs exerces = %s -> %s"
          % (sorted(set(natifs)),
             "les DEUX (garde ET retire)" if len(set(natifs)) == 2
             else "!! REGIME DEGENERE : un seul verdict, l'accord ne prouve rien"))
    if a.only is None and len(set(natifs)) < 2:
        rc = max(rc, 1)
    print("[498r4r1-live] VERDICT : %s" % ("OK" if rc == 0 else "ROUGE (rc=%d)" % rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
