#!/usr/bin/env python
"""probe #589-r1-r1-r2 -- le PRODUIT « compteur REBRANCHE x seuil FRANCHI », de bout en bout.

CRITERE BINAIRE, pose avant toute methode :

    « Existe-t-il un trajet ou le compteur REBRANCHE (#589) fait FRANCHIR le seuil
      d'`EmpyricAmbush` (#589-r1-r1), et le port s'accorde-t-il au natif SUR CE TRAJET ? »

Les deux moities existaient, leur PRODUIT non :
  * #589-r1   -- le compteur est rebranche (`MovementQuery$$GetConnectedPathTo` recoud par une
                 beeline qui lit le `ConnectivityComponent`) : 17/17 accord CANAL sur deux boards ;
  * #589-r1-r1 -- le seuil bascule a `n = 4` (`EmpyricAmbushEffect$$IsValidAttackForBuff`), natif
                 et port, 7 mesures 7 accords -- mais sur `MC1_67`, un board SANS `Bridge`.

Le trajet qui les JOINT est celui ou `n_G < movement <= n_C` : la GEOMETRIE dit « sous le seuil »,
le substrat STOCKE dit « au-dessus ». La, et seulement la, le rebranchement change la DECISION au
lieu de changer un nombre.

## LE CARRE, quatre bras -- et trois d'entre eux sont des CONTRE-EPREUVES

Pour un trajet mesure discriminant (`n_natif >= movement` ET `n_G < movement`) :

  1. LIVE                          -- le natif, l'oracle ;
  2. port CANAL (etat livre)       -- doit EGALER le live ;
  3. port GEOMETRIE (etat d'AVANT #589 : `Board.base_add_neighbours` -> `neighbours_geometric`)
                                   -- doit DIVERGER du live, et son compteur doit valoir `n_G` ;
  4. port NOCHANNEL (`EmpyricAmbush` retire d'`EFFECT_CLASSES` -> `BaseEffect`, deux canaux `None`)
                                   -- doit EGALER le bras 3, ce qui IDENTIFIE la cause de l'ecart :
                                      c'est le BUFF qui manque en geometrie, pas autre chose.

Le bras 3 est ce qui interdit l'accord DEGENERE : sans lui, « ca concorde » ne vaudrait rien -- les
deux cotes pourraient etre d'accord parce que le trajet ne discrimine rien. Le bras 4 est ce qui
interdit d'attribuer l'ecart a un effet de bord de la mutation de substrat.

Le bras TEMOIN (`--temoin`) joue un trajet NON discriminant (`n_G == n_C`) : les quatre bras y
coincident sauf `NOCHANNEL`, ce qui prouve que la mutation de substrat n'est pas un marteau qui
casserait tout rejeu.

## CE QUI REND LE MONTAGE DIFFICILE (et ce que chaque piece y fait)

  * board a `Bridge` OBLIGATOIRE -- ailleurs `G == C` et le produit n'existe pas. `MC1_67`, ou le
    seuil a ete confronte, est justement un board DEGENERE pour le compteur.
  * `eldarLhykhis` n'est PAS au pool (`--list-pool` la dement) -> `write_augmented_seed_bc`.
  * l'ATTAQUANT doit etre `Hero` ET NON-Aeldari (sinon le `op_BitwiseOr` sature, seuil
    inobservable) ET volant/teleporteur (le regime `Walk` est mesure INERTE pour #589).
  * le TRAJET ne se choisit pas a la distance hex : il se CALCULE (`n_G < K <= n_C`), et il se
    RE-CALCULE apres le cast, parce que le `FlyUnit` du `ExecuteBehaviour` de Lhykhis vient occuper
    une tuile adjacente a la cible -- potentiellement celle qu'on visait.
  * `--crit 100,700` : tous les coups critent des deux cotes, donc ce qui bouge est `extraCritDmg`,
    un ecart DETERMINISTE sans tirage.

Usage :
    python probe_589r1r1r2_produit_canal_seuil_live.py --only SCAN --boards C1_74,C3_14
    python probe_589r1r1r2_produit_canal_seuil_live.py --only DUEL --board C1_74
    python probe_589r1r1r2_produit_canal_seuil_live.py --only DUEL --board C1_74 --temoin
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

import probe_589r1_tiles_moved_consumers_live as P1     # noqa: E402  (SCAN : substrats imposes)
import probe_589r1r1_empyric_ambush_live as P2          # noqa: E402  (seuil : garde de regime)

#: Les boards a `Bridge` deja confrontes par #589-r1 (17/17 accord CANAL). Le produit ne peut
#: exister que la ou `G \ C != 0` -- un board sans pont est DEGENERE pour cette question.
BOARDS_BRIDGE = ("C1_74", "C3_14")

#: Regimes de `MovementQuery$$GetPathfinderTypeForUnit` ou la beeline est seulement APPELEE.
#: `Walk` (0) en est absent PAR MESURE (0 basculement sur 3906 couples x 2 boards, `case-589-r1`).
REGIMES = {3: "Fly", 7: "TeleportStrike(+Fly)"}


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


# --------------------------------------------------------------------------- substrat impose
class substrat:
    """Impose le substrat de voisinage que la beeline consomme, le temps d'un bloc.

    `"C"` = le `ConnectivityComponent` (l'etat LIVRE par #589) ; `"G"` = la GEOMETRIE (l'etat
    d'AVANT #589) ; `"N"` = le champ ampute (ferme par #584). C'est `Board.base_add_neighbours` que
    `beeline_pathfinder` lit -- `fly_pathfinder`, lui, garde la geometrie EN DUR (override natif
    `FlyPathfinder$$AddNeighbours`), donc ce levier ne le touche pas, et c'est fidele."""

    def __init__(self, quel: str):
        self.quel = quel
        self.orig = None

    def __enter__(self):
        from engine.entities.pathfinding.board import Board
        self.Board = Board
        self.orig = Board.base_add_neighbours
        if self.quel == "G":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_geometric(tid))
        elif self.quel == "N":
            Board.base_add_neighbours = (
                lambda self, tid, fallback=None: self.neighbours_native(tid))
        return self

    def __exit__(self, *exc):
        self.Board.base_add_neighbours = self.orig
        return False


def _n_prevu(bd, ptype: int, a: int, b: int, quel: str):
    """`GetNumTilesMoved(GetConnectedPathTo(...))` du PORT sous un substrat impose -- l'etage
    COMPLET (`pathfinders.find_path` PUIS la re-densification), pas la beeline nue."""
    from engine.entities.pathfinding.board import Board
    return P1._connected_len(bd, Board, ptype, a, b, quel)


# --------------------------------------------------------------------------- cran SCAN
def _plans_basculants(bd, ptype: int, seuil: int):
    """Tous les couples `(start, step_to)` du board ou le REBRANCHEMENT franchit le seuil, avec les
    ancres (tuiles marchables adjacentes-NATIVES a `step_to`) ou poser la cible.

    ⚠ L'adjacence de JEU n'est PAS `hexgeo.distance <= 1` : `MovementUtil$$AreTilesAdjacent` vaut
    `(|dElev| < 2) & ConnectivityComponent$$IsNeighbour`, c'est-a-dire `neighbours_native`. Une
    ancre choisie a la distance hex fait rendre `pred: null` au natif (`case-589-r1` §6)."""
    marchables = [t for t in sorted(bd.by_id) if bd.walkable(t)]
    out = []
    for a in marchables:
        for b in marchables:
            if a == b:
                continue
            ng = _n_prevu(bd, ptype, a, b, "G")
            nc = _n_prevu(bd, ptype, a, b, "C")
            if ng is None or nc is None or not (ng < seuil <= nc):
                continue
            ancres = [v for v in bd.neighbours_native(b) if bd.walkable(v) and v != a]
            if ancres:
                out.append((a, b, ng, nc, ancres))
    return out, len(marchables) * (len(marchables) - 1)


def run_scan(sid, rpc, boards, seuil: int, reuse: bool) -> int:
    """LE BALAYAGE CHIFFRE -- « combien de trajets franchissent le seuil par le CANAL seul, sur
    combien examines ». Un zero mesure sur N serait un livrable ; un « je n'ai pas trouve » non."""
    from engine.entities.pathfinding.board import Board
    total_bascule = 0
    for bid in boards:
        bg = P1._get_board_graph(sid, rpc, bid, 777, reuse)
        bd = Board(bg["tiles"], adjacency="native_sym")
        ponts = [t["id"] for t in bg["tiles"] if t.get("tileDefId") == "Bridge"]
        if not bd.has_connectivity_channel():
            print("  %-8s CANAL ABSENT du boardGraph -- NON MESURE" % bid)
            return 1
        print("  == %s : %d tuiles, %d `Bridge`" % (bid, len(bd.by_id), len(ponts)))
        for pt, nom in sorted(REGIMES.items()):
            plans, tot = _plans_basculants(bd, pt, seuil)
            total_bascule += len(plans)
            print("     ptype=%-2d %-22s : %d trajet(s) `n_G < %d <= n_C` sur %d couples marchables"
                  % (pt, nom, len(plans), seuil, tot))
            ecarts = {}
            for (_a, _b, ng, nc, _anc) in plans:
                ecarts[(ng, nc)] = ecarts.get((ng, nc), 0) + 1
            for (ng, nc), n in sorted(ecarts.items()):
                print("        n_G=%d -> n_C=%d : %d" % (ng, nc, n))
            for (a, b, ng, nc, anc) in plans[:4]:
                print("        start=%s step_to=%s (n_G=%d n_C=%d) ancres=%s"
                      % (bd.coord(a), bd.coord(b), ng, nc,
                         [bd.coord(x) for x in anc[:3]]))
    print("\n  -> %d trajet(s) basculant(s) au total sur %s" % (total_bascule, ",".join(boards)))
    if total_bascule == 0:
        print("     ZERO MESURE : le produit n'est pas atteignable sur ces boards. L'ecart reste "
              "REEL (les deux moities sont mesurees) mais NON ATTEIGNABLE ici.")
    return 0


# --------------------------------------------------------------------------- montage live
def build(a, tag, seed_bc, attaquant):
    fd, sf = tempfile.mkstemp(prefix="probe_589r1r1r2_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--seed-bc", seed_bc,
            "--p-units", "%s,%s" % (P2.CARRIER, attaquant),
            "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", "400000", "--hp-player", "400000",
            "--no-ai", "--crit", a.crit, "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (tag, (p.stderr or p.stdout or "")[-800:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _occupe(h, dv=None, sauf=()):
    out = set()
    for u in h.alive(dv):
        if u.get("id") in set(sauf):
            continue
        p = u.get("pos") or {}
        if p.get("col") is not None:
            out.add((p["col"], p["row"]))
    return out


def _ptype_de(h, uid: int, bd):
    """Le REGIME est RE-DERIVE de l'etat porte, jamais suppose : c'est lui qui decide si la beeline
    est seulement APPELEE, donc si le substrat peut mordre (`GetPathfinderTypeForUnit`)."""
    from engine.runner.components import StatsComponent
    from engine.runner.snapshot import load_state
    from engine.services.movement_query import get_pathfinder_type_for_unit, unit_has_effect_fn
    snap = h.snapshot()
    st = load_state(snap["dv"], snap["ob"], snap["snap"], board=bd)
    e = st.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = getattr(sc.ctx, "traits", None) if sc is not None else None
    return get_pathfinder_type_for_unit(unit_has_effect_fn(st, int(uid)), traits or [])


def stage(h, bd, seuil, attaquant, temoin=False, verbose=False):
    """Monte le trajet DISCRIMINANT et rend `(rec, raison)` -- `raison is None` == regime ATTEINT.

    ORDRE NON NEGOCIABLE (chaque inversion a deja coute une mesure fausse, cf. `_charge_regime`) :
      1. PLACER les quatre unites (un `move` compte dans `tilesMovedThisTurn`) ;
      2. `reach_my_turn(force_cycle=True)` -- purge les compteurs
         (`IdunBattle.Operations.StartTurnOperation$$ResetUnit`) ;
      3. Lhykhis CASTE 1232 -- et son `FlyUnit` vient occuper une adjacente de la cible ;
      4. RE-CALCULER le trajet depuis la position REELLE de l'attaquant (le vol a pu prendre la
         tuile visee) ;
      5. SNAPSHOT (avant le pas, que le rejeu offline doit REJOUER lui-meme) ;
      6. le PAS ; 7. LIRE le compteur natif -- c'est LUI qui etiquette le bras.
    """
    dv = h.dview()
    me = h.by_visual(P2.CARRIER, dv)
    att = h.by_visual(attaquant, dv)
    if me is None or att is None:
        return None, "porteur ou attaquant absent du deploiement"
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if not ens:
        return None, "aucun ennemi"
    tgt = ens[0]

    ptype = _ptype_de(h, int(att["id"]), bd)
    if ptype not in REGIMES:
        return None, ("regime ptype=%s hors des deux ou la beeline mord (`Walk` est mesure INERTE)"
                      % ptype)
    plans, _tot = _plans_basculants(bd, ptype, seuil)
    if temoin:
        # BRAS TEMOIN : un trajet NON discriminant (`n_G == n_C >= seuil`). Le buff s'y applique des
        # DEUX cotes, donc la mutation de substrat ne doit RIEN changer -- c'est ce qui prouve
        # qu'elle n'est pas un marteau qui casse tout rejeu.
        marchables = [t for t in sorted(bd.by_id) if bd.walkable(t)]
        plans = []
        for a in marchables:
            for b in marchables:
                if a == b:
                    continue
                ng = _n_prevu(bd, ptype, a, b, "G")
                nc = _n_prevu(bd, ptype, a, b, "C")
                if ng is None or nc is None or ng != nc or nc < seuil:
                    continue
                anc = [v for v in bd.neighbours_native(b) if bd.walkable(v) and v != a]
                if anc:
                    plans.append((a, b, ng, nc, anc))
    if not plans:
        return None, ("aucun trajet %s sur ce board en ptype=%d"
                      % ("temoin (n_G == n_C >= seuil)" if temoin
                         else "discriminant (n_G < %d <= n_C)" % seuil, ptype))
    print("   regime ptype=%d (%s) : %d trajet(s) %s disponibles"
          % (ptype, REGIMES[ptype], len(plans), "temoins" if temoin else "discriminants"))

    # (1) PLACER. L'ancre est choisie BIEN ENTOUREE : le `FlyUnit` de Lhykhis va prendre une de ses
    # adjacentes, et il doit rester une tuile de contact ou le trajet reste discriminant.
    occ = _occupe(h, dv)
    par_ancre = {}
    for (a, b, ng, nc, ancres) in plans:
        for anc in ancres:
            par_ancre.setdefault(anc, []).append((a, b, ng, nc))
    # Le meilleur (start, ancre) = celui qui laisse le PLUS de `step_to` discriminants distincts.
    best = None
    for anc, lst in par_ancre.items():
        libres_autour = [v for v in bd.neighbours_native(anc) if bd.walkable(v)]
        par_start = {}
        for (a, b, ng, nc) in lst:
            par_start.setdefault(a, []).append((b, ng, nc))
        for a, sts in par_start.items():
            cle = (len(sts), len(libres_autour))
            if best is None or cle > best[0]:
                best = (cle, a, anc, sts)
    if best is None:
        return None, "aucun couple (start, ancre) exploitable"
    _cle, start_t, anc_t, sts = best
    start, anchor = bd.coord(start_t), bd.coord(anc_t)
    if verbose:
        print("   plan : start=%s ancre=%s ; step_to candidats %s"
              % (start, anchor, [(bd.coord(b), ng, nc) for (b, ng, nc) in sts]))

    # Garer les AUTRES ennemis loin, poser la cible sur l'ancre, poser Lhykhis a portee mais HORS
    # des tuiles utiles, poser l'attaquant sur `start`.
    import hexgeo
    utiles = {start, anchor} | {bd.coord(b) for (b, _g, _c) in sts}
    loin = [bd.coord(t) for t in sorted(bd.by_id)
            if bd.walkable(t) and bd.coord(t) not in utiles
            and hexgeo.distance(bd.coord(t), anchor) >= 4 and bd.coord(t) not in occ]
    for other in ens[1:]:
        if loin:
            h.place(other["id"], loin.pop())
    if not h.place(tgt["id"], anchor):
        return None, "placement de la cible refuse"
    # Lhykhis : a distance 2 de l'ancre, hors des tuiles utiles -- assez pres pour que le cast
    # passe, assez loin pour ne pas boucher un `step_to`.
    poses = [bd.coord(t) for t in sorted(bd.by_id)
             if bd.walkable(t) and bd.coord(t) not in utiles
             and hexgeo.distance(bd.coord(t), anchor) == 2]
    for p in poses:
        if h.place(me["id"], p):
            break
    if not h.place(att["id"], start):
        return None, "placement de l'attaquant refuse"

    # (2) mon tour, compteurs purges
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    me, att = h.by_visual(P2.CARRIER, dv), h.by_visual(attaquant, dv)
    tgt = next((u for u in h.enemies_of(h.my_player, dv) if u["id"] == tgt["id"]), None)
    if me is None or att is None or tgt is None:
        return None, "une unite a disparu apres le cycle de tour"

    # (3) LE CAST : Lhykhis pose la marque sur la cible (et vole d'elle-meme)
    cast = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
        "abilityType": P2.ABILITY_TYPE}}, 60)
    a0 = (cast.get("actions") or [{}])[0] if isinstance(cast, dict) else {}
    if not a0.get("ok"):
        return None, "cast EmpyricAmbush refuse : %s" % str(cast)[:300]
    dv = h.dview()
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
    names = [e.get("name") for e in ((tu or {}).get("effects") or [])]
    if P2.EFFECT_NAME not in names:
        return None, "la marque %s n'est PAS sur la cible (effets: %s)" % (P2.EFFECT_NAME, names)

    # (4) RE-CALCULER le trajet depuis la position REELLE de l'attaquant : le `FlyUnit` a pu prendre
    # la tuile visee, et la cible a pu etre poussee (`AttackWithAttackDamage` du meme behaviour).
    att = h.by_visual(attaquant, dv)
    ap = att.get("pos") or {}
    apos = (ap.get("col"), ap.get("row"))
    tp = (next(u for u in h.alive(dv) if u["id"] == tgt["id"]).get("pos") or {})
    tpos = (tp.get("col"), tp.get("row"))
    occ2 = _occupe(h, dv, sauf=(att["id"],))
    a_t, t_t = bd.id_at(*apos), bd.id_at(*tpos)
    cands = []
    for b in bd.neighbours_native(t_t):
        if not bd.walkable(b) or bd.coord(b) in occ2 or b == a_t:
            continue
        ng = _n_prevu(bd, ptype, a_t, b, "G")
        nc = _n_prevu(bd, ptype, a_t, b, "C")
        if ng is None or nc is None:
            continue
        ok = (ng == nc and nc >= seuil) if temoin else (ng < seuil <= nc)
        if ok:
            cands.append((b, ng, nc))
    if not cands:
        return None, ("aucun `step_to` %s libre apres le vol de Lhykhis (attaquant %s, cible %s)"
                      % ("temoin" if temoin else "discriminant", apos, tpos))
    step_t, ng, nc = cands[0]
    step_to = bd.coord(step_t)

    # (5) SNAPSHOT AVANT le pas -- c'est le pas que le rejeu offline doit REJOUER lui-meme, pas
    # declarer : declarer court-circuiterait justement le morceau de port qu'on confronte.
    atk_type = h.normal_attack_type(att["id"], dv)
    if atk_type is None:
        return None, "attaque normale introuvable pour l'attaquant"
    rec = {"caster": att["id"], "target": tgt["id"], "lhykhis": me["id"],
           "start": apos, "step_to": step_to, "anchor": tpos, "ptype": ptype,
           "ability_type": int(atk_type), "n_G": ng, "n_C": nc, "temoin": bool(temoin)}
    rec["snapshot"] = h.snapshot()

    # (6) LE PAS -- le seul move compte pour `TilesMovedThisTurn(Caster)`
    if not h.place(att["id"], step_to):
        return None, "pas de l'attaquant refuse"

    # (7) le compteur NATIF etiquette le bras (tri-etat : `None` = NON MESURE, jamais 0)
    ast = h.rpc("actorStats", {"runnerId": h.rid}, 60)
    n = None
    for u in ((ast or {}).get("units") or []):
        if u.get("entityId") is not None and int(u["entityId"]) == int(att["id"]):
            v = u.get("tilesMovedThisTurn")
            n = None if v is None else int(v)
    if n is None:
        return None, "tilesMovedThisTurn NON MESURE pour l'attaquant"
    rec["n_natif"] = n
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    print("   trajet %s -> %s : port n_G=%d n_C=%d | NATIF n=%d" % (apos, step_to, ng, nc, n))
    return rec, None


def rejeu(h, rec, quel_substrat: str, sans_effet: bool = False):
    """Rejeu OFFLINE du MEME pas + de la MEME attaque sous un substrat impose.

    Rend `(per_hit, compteur_du_port)`. Le COMPTEUR est rendu parce qu'un bras de contre-epreuve
    doit prouver que la MUTATION A MORDU : un rejeu qui rendrait le meme compteur que le bras livre
    serait VERT sans rien mesurer."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.components import unit_tiles_moved_this_turn
    saved = EFFECT_CLASSES.get(P2.EFFECT_NAME)
    try:
        if sans_effet:
            EFFECT_CLASSES.pop(P2.EFFECT_NAME, None)
        with substrat(quel_substrat):
            out = h.replay_offline(rec)
        return out["per_hit"], unit_tiles_moved_this_turn(out["state"], int(rec["caster"]))
    finally:
        if saved is not None:
            EFFECT_CLASSES[P2.EFFECT_NAME] = saved


def run_duel(a, rpc, Board, Harness, seuil, seed_bc) -> int:
    rid, sf = build(a, "duel", seed_bc, a.attacker)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        bd = Board(bg["tiles"], adjacency="native_sym")
        if not bd.has_connectivity_channel():
            print("   CANAL ABSENT du boardGraph -- NON MESURE")
            return 2
        h = Harness(rpc, rid, bd)
        rec, why = stage(h, bd, seuil, a.attacker, temoin=a.temoin, verbose=a.verbose)
        if rec is None:
            print("REFUS : %s" % why)
            return 2
        n, ng, nc = rec["n_natif"], rec["n_G"], rec["n_C"]

        # GARDE DE REGIME : le bras ne discrimine que si le natif est AU-DESSUS du seuil et la
        # geometrie EN DESSOUS. Sinon on rendrait un vert qui ne mesure rien.
        if not rec["temoin"] and not (ng < seuil <= n):
            print("REFUS : le trajet ne discrimine pas (n_G=%d, natif=%d, seuil=%d)"
                  % (ng, n, seuil))
            return 2
        if rec["temoin"] and not (ng == nc and n >= seuil):
            print("REFUS : le bras temoin n'est pas dans son regime (n_G=%d n_C=%d natif=%d)"
                  % (ng, nc, n))
            return 2

        live_ok, live = P2._hits_of(h.rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
            "abilityType": int(rec["ability_type"])}}, 60), rec["caster"], rec["target"])
        if not live_ok or not live:
            print("REFUS : attaque live refusee/vide")
            return 2
        if not any(u.get("id") == rec["target"] for u in h.alive()):
            print("REFUS : cible MORTE pendant la salve -- flux live tronque")
            return 2
        k = len(live)

        canal, n_canal = rejeu(h, rec, "C")
        geom, n_geom = rejeu(h, rec, "G")
        nochan, _ = rejeu(h, rec, "C", sans_effet=True)

        accord = canal[:k] == live
        mutation_mord = (n_geom == ng and n_geom != n_canal) if not rec["temoin"] else (n_geom == n_canal)
        decision_change = geom[:k] != live
        cause_buff = geom[:k] == nochan[:k]

        print("\n[PRODUIT] natif n=%d  port n_G=%d n_C=%d  seuil=%d  temoin=%s"
              % (n, ng, nc, seuil, rec["temoin"]))
        print("   LIVE            %s" % live[:6])
        print("   port CANAL      %s  compteur=%s  accord=%s" % (canal[:k][:6], n_canal, accord))
        print("   port GEOMETRIE  %s  compteur=%s  decision CHANGEE=%s"
              % (geom[:k][:6], n_geom, decision_change))
        print("   port NOCHANNEL  %s  == GEOMETRIE : %s" % (nochan[:k][:6], cause_buff))

        rc = 0
        if not accord:
            print("   ECART: le port ne reproduit PAS le natif sur ce trajet")
            rc |= 1
        if n_canal != n:
            print("   ECART: le compteur du port (CANAL) vaut %s, le natif %d" % (n_canal, n))
            rc |= 1
        if not mutation_mord:
            print("   ECART: la MUTATION de substrat n'a pas mordu (compteur GEOM=%s, attendu %s)"
                  % (n_geom, ng))
            rc |= 1
        if rec["temoin"]:
            # Trajet NON discriminant : la mutation ne doit RIEN changer, mais NOCHANNEL si.
            if decision_change:
                print("   ECART: sur un trajet NON discriminant, la geometrie change quand meme le "
                      "resultat -- la mutation de substrat a un effet de bord")
                rc |= 1
            if nochan[:k] == live:
                print("   ECART: NOCHANNEL ne mord pas -- le buff ne s'appliquait pas, le temoin "
                      "ne prouve rien")
                rc |= 1
        else:
            if not decision_change:
                print("   ECART: la geometrie rend le MEME resultat que le canal -- le trajet ne "
                      "discrimine RIEN (accord DEGENERE)")
                rc |= 1
            if not cause_buff:
                print("   ECART: GEOMETRIE != NOCHANNEL -- l'ecart n'est PAS imputable au buff")
                rc |= 1
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("SCAN", "DUEL"), default="DUEL")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C1_74", help="board a `Bridge` -- ailleurs G == C")
    ap.add_argument("--boards", default=",".join(BOARDS_BRIDGE), help="SCAN : boards a balayer")
    ap.add_argument("--reuse-bg", action="store_true",
                    help="SCAN : relit le boardGraph deja capte dans logs/ (aucun runner monte)")
    ap.add_argument("--crit", default="100,700",
                    help="CritChance,CritDamage des p-units. 100 sature extraCritChance -> ce qui "
                         "bouge est extraCritDmg, DETERMINISTE.")
    ap.add_argument("--target-unit", default="necroWarden")
    ap.add_argument("--other-unit", default="necroOverlord")
    ap.add_argument("--attacker", default="blackHaarken",
                    help="Hero + NON-Aeldari + volant/teleporteur (cf. la garde de regime de "
                         "`probe_589r1r1_empyric_ambush_live`).")
    ap.add_argument("--temoin", action="store_true",
                    help="BRAS TEMOIN : trajet NON discriminant (n_G == n_C >= seuil). La mutation "
                         "de substrat ne doit RIEN changer -- c'est ce qui prouve qu'elle n'est "
                         "pas un marteau.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    seuil = P2.seuil_du_gameconfig()
    print("== #589-r1-r1-r2 -- PRODUIT compteur REBRANCHE x seuil FRANCHI ; movement = %d" % seuil)

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    if a.only == "SCAN":
        def rpc2(sid_, m, args, t=180):
            return rpc(m, args, t) or {}
        rc = run_scan(sid, rpc2, [b for b in a.boards.split(",") if b.strip()], seuil, a.reuse_bg)
        print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
        return 0 if rc == 0 else 1

    P2._garde_attaquant(a.attacker)
    seed_bc = P2.seed_bc_avec_lhykhis()
    try:
        rc = run_duel(a, rpc, Board, ChargeRegimeHarness, seuil, seed_bc)
    finally:
        Path(seed_bc).unlink(missing_ok=True)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
