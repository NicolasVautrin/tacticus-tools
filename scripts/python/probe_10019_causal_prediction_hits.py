"""#10019 -- CONTRE-EPREUVE CAUSALE : on fait VARIER la marque, et on regarde l'ORACLE bouger.

Ce que les trois divergences du seed 777 etablissent est une CORRELATION : les attaquants qui
divergent frappent une cible qui porte `MasterAnnihilator_extraHit`, celui qui concorde une cible
qui ne la porte pas. C'est fort (le temoin est un vrai discriminant), mais ce n'est pas causal :
les quatre attaquants sont des unites DIFFERENTES, et rien n'exclut qu'un autre attribut les
separe. Ce probe supprime ce degre de liberte -- MEME attaquant, MEME cible, MEME tuile, MEME
runner, la marque etant la SEULE chose qui change entre les deux mesures.

MONTAGE (celui de `probe_204_ah_channel.py --case master`, reutilise a dessein : c'est deja lui qui
a tranche la face COMBAT, donc les deux faces sont mesurees sur le MEME banc) :
  * `admecDominus` << Vitruvius >>  -- le POSEUR ; sa seule fonction ici est d'attaquer la cible ;
  * `ultraApothecary`              -- l'ATTAQUANT TEMOIN : 1 SEUL coup melee, aucune mecanique
                                      parasite. Une base de 1 rend l'ecart MAXIMALEMENT visible
                                      (le rapport attendu est 2/1, pas 7/6) ;
  * `bloodSanguinary`              -- la cible.

PROTOCOLE, deux phases sur le MEME runner :
  phase NUE   -- l'apothicaire attaque, Vitruvius n'a rien fait : la cible ne porte PAS la marque ;
  phase ARMEE -- Vitruvius attaque la cible d'abord, puis on re-interroge l'oracle pour la MEME
                 paire : la cible porte la marque (elle dure 1 tour).

CRITERE (annonce AVANT la mesure, et il porte sur un COMPTE, pas sur un degat) : `aiPlaybookPredict`
-- l'oracle que le scorer de DECISION consomme reellement -- doit rendre en phase ARMEE un
`rawHealthDmg` valant `(h+1)/h` fois celui de la phase NUE, sur les DEUX bornes a la fois. On lit
les bornes BRUTES (`raw*`) et pas les bornes portees : entre les deux phases la cible a perdu des
PV (Vitruvius l'a frappee), donc `healthDmg*` est borne par les PV restants et bougerait pour une
raison qui n'est PAS la notre. Confondre les deux ferait conclure sur le mauvais etage.

CONTROLE DE NON-DEGENERESCENCE : si les deux phases rendent le meme nombre, ce probe ne conclut
RIEN et le DIT -- soit la marque n'a pas ete posee (Vitruvius n'a pas atteint la cible), soit le
montage ne discrimine pas. Un accord en regime degenere serait un faux vert sur le residu le plus
cher du backlog.

Le port est confronte dans LES DEUX phases : un correctif qui rendrait la phase ARMEE juste en
cassant la phase NUE serait invisible d'une mesure a une seule phase.

ASCII only. Ce probe ne (re)injecte JAMAIS. Usage (depuis `scripts/python`) :

    python probe_10019_causal_prediction_hits.py --state-file <ABSOLU propre> [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent

POSEUR = "admecDominus"        # Vitruvius : pose `MasterAnnihilator_extraHit` sur SA cible
ATTAQUANT = "ultraApothecary"  # temoin : 1 coup melee -- rapport attendu 2/1
CIBLE = "bloodSanguinary"

SID = None


def rpc(method, body, timeout=90):
    r = _rpc(SID, method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def build(seed: int, state: Path, board: str):
    """Mirror EXACT du build de `probe_204_ah_channel.py` : memes unites, memes PV gonfles, crit et
    block a zero. Les PV enormes evitent qu'un kill interrompe la phase ARMEE avant la mesure."""
    out = subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "build",
                          "--seed", str(seed), "--state-file", str(state),
                          "--p-units", f"{POSEUR},{ATTAQUANT}", "--a-units", CIBLE,
                          "--board", board, "--hp-target", "900000",
                          "--hp-player", "900000", "--crit", "0,0", "--block-target", "0,0"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in (out.stdout or "").splitlines():
        if "runnerId=" in ln:
            return int(ln.split("runnerId=")[1].split()[0])
    print("[10019-causal] build KO :", (out.stdout or "")[-400:], (out.stderr or "")[-400:])
    return None


def _oracle(rid, uid, ab, tgt, tile):
    """`aiPlaybookPredict` = `<Ability>Playbook.MakeDamagePredictions`, l'oracle de DECISION (et
    NON le preview `aiPredict`). Rend (rawMin, rawMax) de l'event porte sur la cible principale."""
    body = {"runnerId": rid, "unitId": uid, "targetId": tgt, "abilityType": ab,
            "col": int(tile[0]), "row": int(tile[1])}
    resp = rpc("aiPlaybookPredict", body, 60)
    if not (isinstance(resp, dict) and resp.get("ok")):
        print(f"   [oracle] RPC KO : {json.dumps(resp)[:300]}")
        return None
    evs = resp.get("events") or []
    if not evs:
        print(f"   [oracle] aucun event : {json.dumps(resp)[:300]}")
        return None
    # MEMES cles que `engine_agreement_stages._fields_from_native_event` : les bornes BRUTES sont
    # `willKillDmg` / `mightKillDmg` (struct +0x24 / +0x28), PAS `rawHealthDmg*` (qui est le nom du
    # champ COMPOSITE cote port). Se tromper de cle ici rendrait `None` en silence.
    ev = next((e for e in evs if e.get("targetId") == tgt), evs[0])
    return (ev.get("willKillDmg") or 0, ev.get("mightKillDmg") or 0)


def _marque_presente(rid, tgt):
    """Lit les effets ACTIFS de la cible -- on VERIFIE que la mutation a mordu au lieu de la
    supposer. Une phase << ARMEE >> qui ne porte pas la marque invaliderait toute la mesure."""
    dv = _dview(rid)
    u = next((x for x in (dv.get("units") or []) if x.get("id") == tgt), None)
    noms = []
    for e in ((u or {}).get("effects") or []):
        n = e.get("name") if isinstance(e, dict) else e
        if n:
            noms.append(str(n))
    return any("MasterAnnihilator" in n for n in noms), noms


def _dview(rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})


def _attendre_tour(rid, joueur, essais=6):
    """Rend la main au bon joueur -- sans cela un `applyAction` est refuse et la << mutation >>
    n'aurait jamais lieu, ce qui se lirait a tort comme un verdict."""
    for _ in range(essais):
        dv = _dview(rid)
        if dv.get("currentPlayer") == joueur:
            return dv
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None


def _drive(rid, board_tiles, aid, cid, tid):
    """Colle l'apothicaire ET le poseur a la cible, par `applyAction move` (la voie du jeu).

    On DEPLACE pour forcer la configuration : la geometrie de spawn ne doit jamais etre la raison
    d'un << non confronte >>."""
    dv = _dview(rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    en = next((u for u in units if u.get("id") == tid), None)
    if en is None:
        return None, None
    T = upos(en)
    occ = {upos(u) for u in units if upos(u) is not None and u.get("id") not in (aid, cid)}
    libres = [c for c in board_tiles if hexgeo.distance(c, T) == 1 and c not in occ]
    if len(libres) < 2:
        return None, None
    for uid, dest in ((aid, libres[0]), (cid, libres[1])):
        cur = next((upos(u) for u in units if u.get("id") == uid), None)
        if cur != dest:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 40)
    return libres[0], libres[1]


def main(argv):
    global SID
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--board", type=str, default="MC1_67")
    ap.add_argument("--state-file", type=str, required=True)
    args = ap.parse_args(argv)

    SID = _resolve_session()
    if SID is None:
        print("[10019-causal] aucune session Frida -- ABANDON (ce probe ne (re)injecte JAMAIS)")
        return 2
    rid = build(args.seed, Path(args.state_file), args.board)
    if rid is None:
        return 2
    print(f"[10019-causal] runner={rid} board={args.board} seed={args.seed}")
    try:
        dv = _dview(rid)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        att = next((u for u in units if u.get("visualId") == ATTAQUANT), None)
        pos_u = next((u for u in units if u.get("visualId") == POSEUR), None)
        en = next((u for u in units if u.get("visualId") == CIBLE), None)
        if att is None or pos_u is None or en is None:
            print("[10019-causal] montage incomplet :",
                  [u.get("visualId") for u in units], "-- rien n'est conclu")
            return 3
        aid, cid, tid, joueur = att["id"], pos_u["id"], en["id"], att.get("owner")
        a_norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
        c_norm = next((a for a in (pos_u.get("abilities") or []) if a.get("kind") == "normal"), None)
        if a_norm is None or c_norm is None:
            print("[10019-causal] attaque normale introuvable -- rien n'est conclu")
            return 3
        a_ab, c_ab = a_norm["id"], c_norm["id"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = [(t.get("col"), t.get("row")) for t in (bg.get("tiles") or []) if t.get("walkable")]
        if _attendre_tour(rid, joueur) is None:
            print("[10019-causal] la main n'est jamais revenue au joueur -- rien n'est conclu")
            return 3
        a_tile, c_tile = _drive(rid, tiles, aid, cid, tid)
        if a_tile is None:
            print("[10019-causal] pas deux tuiles libres autour de la cible -- rien n'est conclu")
            return 3

        # --- PHASE NUE : la marque n'est PAS posee ---
        armee0, noms0 = _marque_presente(rid, tid)
        nue = _oracle(rid, aid, a_ab, tid, a_tile)
        print(f"[10019-causal] phase NUE   marque={armee0} effets={noms0} oracle raw={nue}")
        if armee0:
            print("[10019-causal] la marque est DEJA la en phase nue -- le montage ne discrimine "
                  "pas, rien n'est conclu")
            return 3

        # --- POSE : Vitruvius attaque la cible (MEME forme d'action que `probe_204`) ---
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": c_ab}}, 90)
        armee1, noms1 = _marque_presente(rid, tid)
        apres = _oracle(rid, aid, a_ab, tid, a_tile)
        print(f"[10019-causal] phase ARMEE marque={armee1} effets={noms1} oracle raw={apres}")

        # --- VERDICT ---
        if not armee1:
            print("[10019-causal] la marque n'a PAS ete posee -- la mutation n'a pas mordu, "
                  "rien n'est conclu (ce n'est PAS un verdict negatif)")
            return 3
        if nue is None or apres is None or not all(nue) or not all(apres):
            print("[10019-causal] oracle muet sur une des deux phases -- rien n'est conclu")
            return 3
        r_min = apres[0] / nue[0]
        r_max = apres[1] / nue[1]
        print(f"[10019-causal] rapports natifs : min={r_min:.4f} max={r_max:.4f}")
        if abs(r_min - 1.0) < 1e-9 and abs(r_max - 1.0) < 1e-9:
            print("[10019-causal] REGIME DEGENERE : l'oracle rend la MEME chose avec et sans la "
                  "marque -- ce montage ne prouve RIEN sur le compte de coups")
            return 3
        print("[10019-causal] L'ORACLE NATIF BOUGE avec la marque, et lui seul a change entre les "
              "deux phases -- l'attribution est CAUSALE, plus seulement correlee")

        # --- CONFRONTATION DU PORT, DANS LES DEUX PHASES -------------------------------------
        # Une seule phase ne suffirait pas : un correctif qui rendrait la phase ARMEE juste en
        # cassant la phase NUE y serait invisible. On confronte donc le RAPPORT, qui est la
        # grandeur que la mesure native etablit (un COMPTE, pas un degat).
        from engine.entities.effects.loki.hits import MasterAnnihilatorAdditionalHitEffect
        from engine.services.attack_hits_formula import attack_hits_with_modifiers
        marque = MasterAnnihilatorAdditionalHitEffect(name="MasterAnnihilator_extraHit",
                                                      effect_type=1249)
        board_min = {"att_id": aid, "tgt_id": tid, "attack_pos": a_tile, "t_pos": upos(en),
                     "tgt_team": 1, "is_melee": True,
                     "pos_by_id": {aid: a_tile, tid: upos(en)}, "team_by_id": {aid: 0, tid: 1}}

        def _port(effets_cible):
            return attack_hits_with_modifiers(
                weapon_hits=1, extra_hits=0, extra_hits_melee=0, attacker_effects=[],
                trait_objects=[], target_effects=effets_cible, aura_sources=[], board=board_min,
                is_melee=True, damage_profile="Physical", include_bonus_hit_behaviours=True,
                is_prediction=True)

        p_nue, p_armee = _port([]), _port([marque])
        r_port = (p_armee / p_nue) if p_nue else None
        print(f"[10019-causal] port : nue={p_nue} armee={p_armee} rapport={r_port}")
        if r_port is None or abs(r_port - r_min) > 1e-9 or abs(r_port - r_max) > 1e-9:
            print(f"[10019-causal] ECHEC : le port rend un rapport {r_port} la ou le natif rend "
                  f"{r_min:.4f}/{r_max:.4f} -- la face PREDICTION diverge encore")
            return 1
        print("[10019-causal] le port reproduit le rapport natif DANS LES DEUX PHASES")
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
