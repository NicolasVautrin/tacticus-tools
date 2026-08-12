"""#952 -- MESURE live du passif `HuntersBeyondDeath` (`spaceHound` << Tjark >>).

QUESTION BINAIRE. Sur un montage ou un PSYKER ennemi frappe une unite du camp de Tjark, le port
rend-il le MEME degat que le natif -- c'est-a-dire AVEC la soustraction plate
`dmgReduction[level] x multiplier` quand ce psyker est a `<= 2` hexes de Tjark, et SANS elle
au-dela ?

MECANIQUE (decompile = verite, cf. `engine/entities/effects/loki/hunters_beyond_death.py`) :

    HuntersBeyondDeathEffect$$CreateEffectDamageMalusForDefense =
        ForSubtraction( NOT AreFriends(EffectSource, Caster@+0x48)
                      &     AreFriends(EffectSource, Target@+0x60)
                      &     HasTrait(Caster@+0x48, 0x3ea = Psyker)
                      & NOT AmountIsGreater(MinDistance(EffectSource, Caster@+0x48), Direct(2)),
                        ConfigVar(0x12 = dmgReduction) )

L'effet vit sur TJARK (`AddEffect(0x4a6, source = Owner, targets = Owner)`), donc :

  * quand TJARK est le defenseur, le porteur EST la cible -> canal `create_effect_damage_malus_for
    _defense` (les DEUX agregateurs d'aura excluent `uid == tgt_id`) ;
  * quand un ALLIE est le defenseur -> canal AURA state-wide `create_aura_defense_damage_malus_for
    _ally`.

QUATRE BRAS, un runner par bras (geometrie CALCULEE depuis le `boardGraph` puis ASSERTIONNEE contre
les positions REELLES ; un bras qui n'obtient pas sa configuration rend `indisponible`, jamais un
skip) :

  * `self`      -- le psyker frappe TJARK, adjacent (d = 1)         -> patte SELF, malus ACTIF ;
  * `aura_pres` -- le psyker frappe l'ALLIE, Tjark a d = 2 du psyker -> patte AURA, malus ACTIF
                   (c'est la BORNE INCLUSIVE : `NOT AmountIsGreater(d, 2)`) ;
  * `aura_loin` -- MEME attaque, MEME cible, Tjark deplace a d >= 3  -> malus MUET ;
  * `extra`     -- l'AUTRE face du kit : TJARK frappe le psyker (1172, `ForAddition(OwnerIsCaster &
                   HasTrait(Target, Psyker), ConfigVar(extraDmg))`). Il est alors dans MON roster.

`aura_pres` et `aura_loin` ne different QUE par la position de Tjark : si les deux rendent le MEME
total natif, la mesure est VIDE et le probe REFUSE de conclure.

ORACLE = le degat REEL du natif (somme des `Amount` de la cascade d'events), confronte au REJEU
OFFLINE de la MEME attaque depuis la MEME capture et le MEME flux RNG. Aucune valeur attendue codee
en dur.

CASTER = `eldarFarseer` (trait `Psyker`, aucun passif qui modifie le degat de son attaque normale) ;
ALLIE de Tjark = `necroWarden`. Crit et block sont neutralises au build (`--crit 0,0` etc.) pour que
le ledger soit deterministe.

ASCII only (console cp1252).

CLI (depuis scripts/python) :
  python probe_952_hunters_beyond_death.py --board MC1_67 --seed 4321 [--verbose]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from probe_r6_round_materialize import _mkrpc          # foyer partage de la session RPC

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

BOARD = "MC1_67"
SEED = "4321"

PSYKER = "eldarFarseer"      # trait Psyker ; melee 2 coups ; aucun passif de degat sur SON attaque
TJARK = "spaceHound"         # le porteur de HuntersBeyondDeath
ALLIE = "necroWarden"        # l'allie de Tjark, cible de la patte AURA (NON Psyker)

EFF_MALUS = 1190             # EffectType.HuntersBeyondDeath
EFF_EXTRA = 1172             # EffectType.HuntersBeyondDeath_ExtraDamage
EFF_SUPPR = 1191             # EffectType.HuntersBeyondDeathPsykerSuppression

#: `d` de Tjark au psyker pour chaque bras. `2` est la BORNE INCLUSIVE du gate, `4` la met hors
#: portee sans ambiguite (une case de marge sur l'approximation multi-hex).
D_PRES, D_LOIN = 2, 4


def _build(seed, board, p_units, a_units, extra):
    sf = ROOT / "logs" / "runners" / ("p952-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
            "--board", board, "--rank", "17",
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units),
            "--crit", "0,0", "--crit-target", "0,0", "--block-target", "0,0",
            "--block-player", "0,0", "--no-ai", *extra]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-900:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _pos(dv, uid):
    p = (_unit(dv, uid) or {}).get("pos")
    return None if not p else (int(p["col"]), int(p["row"]))


def _normal_attack_id(dv, uid):
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _effets(dv, uid):
    return sorted(int(e["effectType"]) for e in ((_unit(dv, uid) or {}).get("effects") or [])
                  if e.get("effectType") is not None)


def _attack(rpc, rid, cid, tid, ab):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ab)}, "captureEvents": True}, 150)
    hits = []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and int(td.get("Target_Id", td.get("TargetId", tid)) or tid) == int(tid):
                hits.append(int(td["Amount"]))
    return res, hits


def _sonde_graphe(rpc, board_id, seed):
    """Build MINIMAL, uniquement pour lire le `boardGraph` : `--place` est un argument de BUILD, la
    geometrie doit donc etre calculee AVANT le build de mesure. Le runner est dispose aussitot."""
    from engine.entities.pathfinding.board import Board
    rid, err = _build(seed, board_id, [PSYKER], [TJARK], [])
    if rid is None:
        return None, "sonde KO : %s" % err
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        return Board(bg["tiles"], adjacency="native_sym"), None
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _geometrie(board):
    """CALCULE (jamais espere) un quadruplet de tuiles POSABLES :

        psyker, voisin_du_psyker (l'allie), tjark_pres a d == 2, tjark_loin a d >= 4

    On balaie les tuiles walkables et on retient la premiere qui satisfait TOUTES les contraintes,
    en preferant le centre du board (un montage en coin sous-exercerait la geometrie -- runner.md).
    Rend `(dict des 4 coords, None)` ou `(None, cause)`."""
    import hexgeo
    ids = [t for t in sorted(board.by_id.keys()) if board.walkable(t)]
    coords = {t: board.coord(t) for t in ids}
    coords = {t: c for t, c in coords.items() if c is not None}
    if not coords:
        return None, "boardGraph sans tuile walkable"
    cols = [c for c, _ in coords.values()]
    rows = [r for _, r in coords.values()]
    mid = ((min(cols) + max(cols)) / 2.0, (min(rows) + max(rows)) / 2.0)
    par_distance = sorted(coords.items(),
                          key=lambda kv: abs(kv[1][0] - mid[0]) + abs(kv[1][1] - mid[1]))
    libres = set(coords.values())
    for _t, p in par_distance:
        voisins = [coords[n] for n in board.neighbours(_t)
                   if n in coords and board.walkable(n)]
        if len(voisins) < 2:
            continue
        for allie in voisins:
            pres = [c for c in libres
                    if c not in (p, allie) and hexgeo.distance(p, c) == D_PRES]
            loin = [c for c in libres
                    if c not in (p, allie) and hexgeo.distance(p, c) >= D_LOIN]
            if pres and loin:
                return {"psyker": p, "allie": allie,
                        "tjark_pres": sorted(pres)[0], "tjark_loin": sorted(loin)[0]}, None
    return None, "aucune geometrie (psyker + voisin + tjark a d=2 et a d>=4) sur ce board"


# --------------------------------------------------------------------------- rejeu offline
def _replay(cap, board, attaquant, cible, mutate=None):
    """Rejoue L'ATTAQUE depuis la MEME capture et le MEME flux RNG.

    ⚠ LES MUTANTS SONT POSES **AVANT** `load_state` : `EFFECT_CLASSES` n'est lu qu'a la CREATION des
    instances (`EffectFactory.create`), donc un `pop` fait apres arriverait TROP TARD pour un effet
    deja present au seed (forme exacte du faux vert documentee par #932)."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects import base as EB
    from engine.entities.effects.loki import hunters_beyond_death as HBD

    saved_eff = saved_self = saved_aura = saved_dist = None
    if mutate in ("m_effet", "m_extra"):
        cle = "HuntersBeyondDeath" if mutate == "m_effet" else "HuntersBeyondDeath_ExtraDamage"
        saved_eff = (cle, EFFECT_CLASSES.pop(cle, None))
        assert saved_eff[1] is not None, "MUTANT INOPERANT : EFFECT_CLASSES[%r]" % cle
    elif mutate == "m_self":
        saved_self = HBD.HuntersBeyondDeathEffect.create_effect_damage_malus_for_defense
        HBD.HuntersBeyondDeathEffect.create_effect_damage_malus_for_defense = \
            lambda self, *a, **k: None
    elif mutate == "m_aura":
        saved_aura = HBD.HuntersBeyondDeathEffect.create_aura_defense_damage_malus_for_ally
        HBD.HuntersBeyondDeathEffect.create_aura_defense_damage_malus_for_ally = \
            lambda self, *a, **k: None
    elif mutate == "m_dist":
        # borne STRICTE au lieu d'inclusive : la confusion `AmountIsEqualOrGreater`.
        saved_dist = EB.min_distance_at_most
        EB.min_distance_at_most = lambda a, b, n, _o=saved_dist: _o(a, b, int(n) - 1)
        HBD.min_distance_at_most = EB.min_distance_at_most
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        e = st.get_entity(int(cible))
        hc = e.get_component(HealthComponent)
        h0 = int(hc.hp) if hc is not None else None
        runner.apply(AttackUnitMessage(int(attaquant), int(cible)))
        last = runner.damage_handler.last or {}
        eff = getattr(st, "effects", None)
        portes = [] if eff is None else [
            (x.name, x.effect_type, x.__class__.__name__)
            for x in eff.by_unit.get(int(cap["tjark"]), []) if not x.consumed]
        return {"total": last.get("total"), "per_hit": last.get("per_hit"),
                "hp_delta": (None if h0 is None else h0 - int(hc.hp)),
                "effets_tjark": portes}
    finally:
        if saved_eff is not None:
            EFFECT_CLASSES[saved_eff[0]] = saved_eff[1]
        if saved_self is not None:
            HBD.HuntersBeyondDeathEffect.create_effect_damage_malus_for_defense = saved_self
        if saved_aura is not None:
            HBD.HuntersBeyondDeathEffect.create_aura_defense_damage_malus_for_ally = saved_aura
        if saved_dist is not None:
            EB.min_distance_at_most = saved_dist
            HBD.min_distance_at_most = saved_dist


# --------------------------------------------------------------------------- les trois bras
def _un_bras(rpc, board, geo, board_id, seed, bras, mutate):
    """Monte UN runner, ASSERTIONNE la geometrie, attaque, rejoue offline. Rend une ligne."""
    import hexgeo
    if bras == "extra":
        # FACE ATTAQUANT (1172) : c'est TJARK qui frappe, donc il doit etre dans MON roster.
        place = ["--place", "%s:%d,%d" % (TJARK, geo["psyker"][0], geo["psyker"][1])]
        aplace = ["--a-place", "%s:%d,%d" % (PSYKER, geo["allie"][0], geo["allie"][1])]
        rid, err = _build(seed, board_id, [TJARK], [PSYKER], place + aplace)
    else:
        tj = geo["tjark_pres"] if bras != "aura_loin" else geo["tjark_loin"]
        if bras == "self":
            tj = geo["allie"]      # d = 1 du psyker : Tjark prend la case adjacente
        place = ["--place", "%s:%d,%d" % (PSYKER, geo["psyker"][0], geo["psyker"][1])]
        aplace = ["--a-place", "%s:%d,%d" % (TJARK, tj[0], tj[1])]
        if bras != "self":
            aplace += ["--a-place", "%s:%d,%d" % (ALLIE, geo["allie"][0], geo["allie"][1])]
        rid, err = _build(seed, board_id, [PSYKER],
                          [TJARK] if bras == "self" else [TJARK, ALLIE], place + aplace)
    if rid is None:
        return {"bras": bras, "verdict": "indisponible", "cause": "build KO : %s" % err}
    try:
        dv = _view(rpc, rid, inactive=True)
        pid = (_by_vis(dv, PSYKER) or {}).get("id")
        tid = (_by_vis(dv, TJARK) or {}).get("id")
        if bras == "extra":
            aid = pid                                  # Tjark ATTAQUE le psyker
        else:
            aid = (_by_vis(dv, ALLIE) or {}).get("id") if bras != "self" else tid
        if pid is None or tid is None or aid is None:
            return {"bras": bras, "verdict": "indisponible", "cause": "unite absente"}
        pid, tid, aid = int(pid), int(tid), int(aid)
        # GEOMETRIE ASSERTIONNEE -- recalculee depuis les positions REELLES, jamais depuis le plan.
        p_pos, t_pos, a_pos = _pos(dv, pid), _pos(dv, tid), _pos(dv, aid)
        if None in (p_pos, t_pos, a_pos):
            return {"bras": bras, "verdict": "indisponible", "cause": "position absente"}
        d_cible = hexgeo.distance(p_pos, a_pos) if bras != "extra" \
            else hexgeo.distance(t_pos, p_pos)
        d_tjark = hexgeo.distance(p_pos, t_pos)
        attendu = {"self": (1, 1), "aura_pres": (1, D_PRES), "aura_loin": (1, D_LOIN),
                   "extra": (1, 1)}[bras]
        if d_cible != attendu[0] or (bras == "aura_loin" and d_tjark < attendu[1]) \
                or (bras != "aura_loin" and d_tjark != attendu[1]):
            return {"bras": bras, "verdict": "indisponible",
                    "cause": "geometrie NON obtenue : d(psyker,cible)=%d d(psyker,tjark)=%d "
                             "(attendu %s) ; psyker@%s tjark@%s cible@%s"
                             % (d_cible, d_tjark, attendu, p_pos, t_pos, a_pos)}
        eff_tjark = _effets(dv, tid)
        for e in (EFF_MALUS, EFF_EXTRA, EFF_SUPPR):
            if e not in eff_tjark:
                return {"bras": bras, "verdict": "indisponible",
                        "cause": "l'effet %d n'est PAS sur Tjark (%s) -- le passif ne s'est pas "
                                 "pose, la mesure serait vide" % (e, eff_tjark)}
        att = tid if bras == "extra" else pid          # QUI frappe : Tjark (1172) ou le psyker (1190)
        na = _normal_attack_id(dv, att)
        if na is None:
            return {"bras": bras, "verdict": "indisponible",
                    "cause": "attaque normale de l'attaquant introuvable"}
        cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30), "tjark": tid}
        _r, hits = _attack(rpc, rid, att, aid, na)
        if not hits:
            return {"bras": bras, "verdict": "indisponible",
                    "cause": "cascade VIDE (ok=%s)" % _r.get("ok")}
        port = _replay(cap, board, att, aid, mutate=mutate)
        # COMPARAISON COUP PAR COUP, jamais sur le scalaire `total` : quand l'attaque TUE (bras
        # `extra`), le natif tague `Amount = 0` pour les coups d'apres, alors que `total` cote port
        # porte encore le degat BRUT du coup surnumeraire. Mesure : natif [2323, 2829, 2378, 0]
        # = 7530, `total` port = 10390 (ecart = le 4e coup non clampe). Les LISTES, elles,
        # coincident -- c'est donc la liste qui est l'observable.
        ph = port.get("per_hit")
        pt = None if ph is None else sum(int(x) for x in ph)
        return {"bras": bras,
                "verdict": "EGAL" if (ph is not None and list(ph) == list(hits)) else "DIVERGE",
                "natif": sum(hits), "port": pt,
                "ecart": (None if pt is None else pt - sum(hits)),
                "natif_hits": hits, "port_hits": port.get("per_hit"),
                "d_cible": d_cible, "d_tjark": d_tjark, "effets_tjark": port["effets_tjark"],
                "cible_est_tjark": aid == tid}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def mesurer(rpc, board_id=BOARD, seed=SEED, mutate=None, verbose=False):
    board, err = _sonde_graphe(rpc, board_id, seed)
    if board is None:
        return {"verdict": "indisponible", "cause": err}
    geo, err = _geometrie(board)
    if geo is None:
        return {"verdict": "indisponible", "cause": err}
    lignes = [_un_bras(rpc, board, geo, board_id, seed, b, mutate)
              for b in ("self", "aura_pres", "aura_loin", "extra")]
    ko = next((l for l in lignes if l.get("verdict") == "indisponible"), None)
    if ko is not None:
        return {"verdict": "indisponible", "cause": "%s : %s" % (ko["bras"], ko["cause"]),
                "lignes": lignes, "geo": geo}
    # Le REGIME doit CHANGER le resultat : deux totaux egaux signeraient une mesure vide.
    pres = next(l for l in lignes if l["bras"] == "aura_pres")["natif"]
    loin = next(l for l in lignes if l["bras"] == "aura_loin")["natif"]
    if pres == loin:
        return {"verdict": "indisponible", "lignes": lignes, "geo": geo,
                "cause": "aura_pres et aura_loin rendent le MEME total natif (%d) -- la position "
                         "de Tjark n'a rien change, la mesure est vide" % pres}
    out = {"verdict": "EGAL" if all(l["verdict"] == "EGAL" for l in lignes) else "DIVERGE",
           "lignes": lignes, "geo": geo, "mutate": mutate,
           "delta_natif_pres_loin": loin - pres}
    if verbose:
        print(json.dumps(out, indent=1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--mutate", default=None,
                    choices=[None, "m_effet", "m_self", "m_aura", "m_dist", "m_extra"])
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    out = mesurer(_mkrpc(), a.board, a.seed, a.mutate, verbose=True)
    if not a.verbose:
        print(json.dumps(out, indent=1))
    return 0 if out.get("verdict") == "EGAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
