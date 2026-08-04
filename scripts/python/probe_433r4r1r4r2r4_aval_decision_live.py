"""#433-r4-r1-r4-r2-r4 -- l'AVAL du basculement d'adjacence : une DECISION change-t-elle ?

LE CRITERE, pose AVANT la methode
---------------------------------
#433-r4-r1-r4-r2 a montre que `battle_query.is_adjacent` CHANGE DE VERDICT quand on l'branche sur
la liste STOCKEE du `ConnectivityComponent` (`boardGraph.neighbours`) au lieu de la couronne hex,
et que le natif est d'accord (oracle independant : le splash de `FragBomb`). Ce qui n'a jamais ete
mesure, c'est si ce basculement change une DECISION. Trois questions BINAIRES, par valeur
decroissante :

  Q1. Sur N situations (board x seed x etat x unite activable), combien de fois l'action CHOISIE
      par le playbook porte differe-t-elle entre les deux substrats ?
  Q2. Combien de fois le CLASSEMENT des candidats bouge sans que le premier change ?
  Q3. De combien l'utilite BRUTE bouge-t-elle (support des deux precedentes) ?

LE DISCRIMINANT : la comparaison DIRECTE des deux substrats du MEME port, sur le MEME etat. Le
natif n'entre pas dans cette mesure -- un critere a trois valeurs noierait le cas utile (lecon de
#589-r1, repayee en #433-r4-r1-r4-r2).

  substrat NAT = `is_adjacent(t, p, elev, neigh)`   <- ce que le port fait DEPUIS #606
  substrat GEO = `is_adjacent(t, p, elev, None)`    <- ce qu'il faisait AVANT

Le patch porte sur la PRIMITIVE (`battle_query.is_adjacent`), jamais sur le canal : `neigh_by_pos`
a d'AUTRES lecteurs qui le lisent directement (l'ordre natif des voisins pour la cible exacte de
`GauntletsOfUltramar`, #117) et qui, eux, ne changent pas entre les deux etats du depot. Neutraliser
le canal mesurerait donc AUTRE CHOSE que le basculement.

L'ACCORD PEUT ETRE DEGENERE, et c'est le piege central de cette mesure : "0 decision changee" ne
vaut RIEN si aucune adjacence n'a bascule pendant les decisions. Le probe compte donc, pour chaque
situation, les APPELS d'`is_adjacent` dont le verdict DIFFERE entre les deux substrats
(`bascules`), et les ventile PAR APPELANT (fichier:fonction) -- c'est la reponse mesuree a "quelles
voies le playbook emprunte-t-il", et c'est ce qui separe :

    bascules == 0  -> regime MUET (rien a conclure sur la decision)
    bascules  > 0 et decisions changees == 0  -> ecart de FIDELITE SANS impact sur la politique
    decisions changees > 0                    -> ecart de fidelite AVEC impact

CRAN ANTI-CONTAMINATION : chaque situation rejoue le substrat NAT une 2e fois APRES le GEO. Un
desaccord NAT/NAT accuserait un cache (ou un effet de bord) du port, pas le basculement -- il
invaliderait la mesure et fait rougir.

CONTRE-EPREUVE DE DETECTION (`--substrat mut`) : le substrat alternatif est remplace par un
substrat volontairement FAUX (disque hex r<=2). Il n'a aucune valeur de fidelite -- son seul role
est de prouver que ce harnais RAPPORTE un changement de decision quand il y en a un. Un `mut` qui
rendrait lui aussi 0 accuserait le harnais, et la mesure `geo` ne vaudrait rien.

Usage (session warmee) :
    python probe_433r4r1r4r2r4_aval_decision_live.py                      # les boards par defaut
    python probe_433r4r1r4r2r4_aval_decision_live.py --board C3_14 --steps 14 --seed 31337
    python probe_433r4r1r4r2r4_aval_decision_live.py --board C3_14 --substrat mut  # contre-epreuve
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

# `C3_14` porte 15 `Bridge` (38 aretes permissives), `C1_74` en porte 2 (4 aretes) -- le contraste
# mesure en #433-r4-r1-r4-r2. `MC1_67` est l'arene de reference et `C6_25` le temoin sans `Bridge`
# (gisement NUL attendu : leur presence est ce qui rend la dispersion lisible).
BOARDS = ("C3_14", "C1_74", "MC1_67", "C6_25")


# --------------------------------------------------------------------------- montage runner

def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int, tag: str) -> tuple[int, pathlib.Path]:
    """Meme degradation de roster que `probe_433r4r1r4r2_is_adjacent_substrat_live` : un board
    pauvre en spawns joueur ne doit pas faire echouer la mesure, seulement la reduire."""
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p433r4r1r4r2r4_%s_%s.json" % (tag, board))
    p = None
    for roster in (5, 4, 3, 2):
        state_file.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
               "--board", board, "--no-ai", "--roster", str(roster),
               "--state-file", str(state_file)]
        p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state_file.exists():
            return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), state_file
        if "spawns joueur <" not in ((p.stdout or "") + (p.stderr or "")):
            break
    sys.stdout.write(((p.stdout if p else "") or "")[-1200:])
    sys.stdout.write(((p.stderr if p else "") or "")[-1200:])
    raise SystemExit("build KO (%s)" % board)


# --------------------------------------------------------------------------- la sonde

def _ident(payload) -> tuple | None:
    """L'IDENTITE d'une action, SANS son utilite -- c'est ce qui permet de distinguer "la meme
    action vaut un peu plus" (amplitude) de "ce n'est plus la meme action" (decision)."""
    if payload is None:
        return None
    k = payload.get("kind")
    to = payload.get("to")
    to = (to[0], to[1]) if to else None
    if k == "ability":
        return ("ability", payload.get("ability"), payload.get("target"), to)
    if k == "move":
        return ("move", to)
    return (k, to)


def _appelant() -> str:
    """Le call-site METIER d'`is_adjacent` : on remonte les frames tant qu'on est dans
    `battle_query` (les trois derivees `count_adjacent`/`count_adjacent_matching`/
    `are_entities_adjacent` y delegent, et c'est leur APPELANT qui nomme la voie)."""
    import sys as _s
    f = _s._getframe(2)
    for _ in range(6):
        if f is None:
            break
        nom = pathlib.Path(f.f_code.co_filename).name
        if nom not in ("battle_query.py", "probe_433r4r1r4r2r4_aval_decision_live.py"):
            return "%s:%s" % (nom, f.f_code.co_name)
        f = f.f_back
    return "?"


class Sonde:
    """Instrumentation NON INVASIVE (aucune ecriture dans `engine/`) : elle substitue la primitive
    d'adjacence et les trois points ou le port RANGE ses candidats, pour pouvoir rejouer la MEME
    decision sous les deux substrats et lire, en plus de l'action retenue, le CLASSEMENT."""

    def __init__(self, substrat: str = "geo"):
        from engine import battle_query as bq
        from engine import move as mv
        from engine.ai import bucket as bk
        self._bq, self._mv, self._bk = bq, mv, bk
        self.substrat = substrat   # "geo" = l'etat d'AVANT #606 ; "mut" = contre-epreuve (cf. _alt)
        self._orig_isadj = bq.is_adjacent
        self._orig_add = bk.Bucket.add_action
        self._orig_bmf = mv.best_move_faithful
        self._nc_restaure = []
        self.mode = "nat"
        self.freeze = False        # rejeu de CLASSEMENT : ne pas recompter les bascules
        self.reset_situation()
        self._install()

    # -- etat par situation -------------------------------------------------
    def reset_situation(self):
        self.n_calls = 0
        self.n_calls_canal = 0     # appels ou le canal est FOURNI (voie non muette)
        self.n_bascules = 0        # appels dont le verdict DIFFERE entre les deux substrats
        self.voies = {}            # {"fichier:fonction": n_bascules}
        self.cands = []            # [(gen_idx, source, key, ident)]
        self.gen_cur = -1
        self.gens_joues = []
        self.move_args = None

    # -- installation -------------------------------------------------------
    def _alt(self, tile, pos, elev_by_pos):
        """Le substrat ALTERNATIF confronte au natif.

        * `geo` = `is_adjacent` SANS canal, c'est-a-dire EXACTEMENT ce que le port faisait avant
          #606 (couronne hex + porte d'elevation). C'est la mesure demandee.
        * `mut` = CONTRE-EPREUVE de DETECTION : un substrat volontairement FAUX (disque hex r<=2,
          sans porte). Il n'a aucune valeur de fidelite -- son seul role est de prouver que ce
          harnais RAPPORTE un changement de decision quand il y en a un. Un `mut` qui rendrait
          lui aussi 0 decision changee accuserait le harnais, pas le basculement."""
        if self.substrat == "mut":
            import hexgeo
            return hexgeo.distance((tile[0], tile[1]), (pos[0], pos[1])) in (1, 2)
        return self._orig_isadj(tile, pos, elev_by_pos, None)

    def _install(self):
        sonde = self
        orig = self._orig_isadj

        def is_adjacent(tile, pos, elev_by_pos=None, neigh_by_pos=None):
            v_nat = orig(tile, pos, elev_by_pos, neigh_by_pos)
            if neigh_by_pos is None and sonde.substrat != "mut":
                return v_nat                      # aucun canal -> les deux substrats coincident
            v_alt = sonde._alt(tile, pos, elev_by_pos)
            if not sonde.freeze:
                sonde.n_calls += 1
                sonde.n_calls_canal += int(neigh_by_pos is not None)
                if v_nat != v_alt:
                    sonde.n_bascules += 1
                    k = _appelant()
                    sonde.voies[k] = sonde.voies.get(k, 0) + 1
            return v_nat if sonde.mode == "nat" else v_alt

        self._bq.is_adjacent = is_adjacent

        orig_add = self._orig_add

        def add_action(bucket_self, action):
            if action is not None:
                sonde.cands.append((sonde.gen_cur, "cmp", tuple(action.key),
                                    _ident(action.payload)))
            return orig_add(bucket_self, action)

        self._bk.Bucket.add_action = add_action

        orig_bmf = self._orig_bmf

        def best_move_faithful(tiles, *a, **kw):
            sonde.move_args = (list(tiles or []), a, dict(kw))
            return orig_bmf(tiles, *a, **kw)

        self._mv.best_move_faithful = best_move_faithful
        # `action_generators` a importe le MODULE (`from engine import move`) -> la substitution
        # au module est vue par le generateur. Verifie a l'installation, jamais suppose.
        from engine.ai import action_generators as ag
        assert ag.move.best_move_faithful is best_move_faithful

        # Playbooks NonComparable : la collecte de candidats vit dans `choose_action`, dont la
        # liste est LOCALE -> on wrappe chaque INSTANCE du registre (l'attribut d'instance prime
        # sur la methode de classe, donc les surcharges par playbook sont couvertes).
        from engine.playbook import noncomparable as nc
        vus = set()
        for pb in nc.PLAYBOOKS.values():
            if id(pb) in vus:      # une meme INSTANCE peut servir plusieurs ids -> jamais 2 wraps
                continue
            vus.add(id(pb))
            self._wrap_nc(pb)

    def _wrap_nc(self, pb):
        sonde = self
        orig_gen = pb.generate_candidates
        self._nc_restaure.append(pb)

        def generate_candidates(ctx, _o=orig_gen):
            out = _o(ctx) or []
            if not sonde.freeze:
                for c in out:
                    to = c.get("to")
                    sonde.cands.append((sonde.gen_cur, "nc", (c.get("pred") or 0.0,),
                                        ("ability", c.get("ability"), c.get("target"),
                                         (to[0], to[1]) if to else None)))
            return out

        pb.generate_candidates = generate_candidates

    def instrumenter_tactic(self, tac):
        """Marque le generateur COURANT (index dans la liste ordonnee du tactic) : sans lui, les
        candidats des 5 tiers NonComparable, du tier Comparable et du fallback Movement seraient
        melanges, alors que le tactic prend la PREMIERE action non-nulle PAR generateur."""
        sonde = self
        for i, g in enumerate(tac.generators):
            orig_g = g.generate

            def generate(ctx, _i=i, _o=orig_g):
                sonde.gen_cur = _i
                sonde.gens_joues.append(_i)
                return _o(ctx)

            g.generate = generate
        return tac

    def desinstaller(self):
        self._bq.is_adjacent = self._orig_isadj
        self._bk.Bucket.add_action = self._orig_add
        self._mv.best_move_faithful = self._orig_bmf
        for pb in self._nc_restaure:
            try:
                del pb.generate_candidates          # retour a la methode de CLASSE
            except AttributeError:
                pass


# --------------------------------------------------------------------------- classement

def _classement(cands: list, gen_retenu: int) -> tuple:
    """La sequence des candidats du generateur RETENU, triee par cle DECROISSANTE avec tie-break =
    ordre d'insertion -- mirror de `Bucket$$AddAction` (`op_GreaterThan` STRICT, donc keep-first).
    `sorted(reverse=True)` est STABLE, donc a cle egale l'ordre d'insertion est preserve : c'est ce
    qui evite d'imposer une negation aux cles (elles portent des `Fraction`, pas que des `float`).
    Rend `(sequence d'idents, {ident: cle})` -- l'amplitude est une AUTRE question que l'ordre."""
    lot = [c for c in cands if c[0] == gen_retenu]
    ordre = sorted(range(len(lot)), key=lambda i: lot[i][2], reverse=True)
    return [lot[i][3] for i in ordre], {lot[i][3]: lot[i][2] for i in range(len(lot))}


def _classement_move(sonde: "Sonde") -> tuple:
    """Le fallback MOVEMENT ne passe pas par un `Bucket` : son argmax est la boucle de
    `engine.move.best_move_faithful`. On rejoue la MEME fonction, tuile par tuile, avec les
    arguments CAPTURES -- l'utilite d'une tuile ne depend pas du candidate-set (les extremes
    d'elevation sont pris sur le BOARD ENTIER, cf. son corps), donc la decomposition est exacte."""
    if sonde.move_args is None:
        return [], {}
    tiles, a, kw = sonde.move_args
    orig = sonde._orig_bmf
    out = []
    sonde.freeze = True            # rejeu de DIAGNOSTIC : il ne doit pas recompter les bascules
    try:
        for t in tiles:
            c, u = orig([t], *a, **kw)
            if c is not None:
                out.append((("move", (c[0], c[1])), (u,)))
    finally:
        sonde.freeze = False
    ordre = sorted(range(len(out)), key=lambda i: out[i][1], reverse=True)
    return [out[i][0] for i in ordre], {out[i][0]: out[i][1] for i in range(len(out))}


# --------------------------------------------------------------------------- une situation

def _decider(sonde: Sonde, ctx, tac_cls):
    """Joue le tactic instrumente sur `ctx` et rend
    `(action, classement du generateur RETENU, utilites de TOUS les generateurs, gen_retenu)`.

    Les deux perimetres sont DIFFERENTS a dessein : c'est le generateur retenu qui DECIDE (donc le
    classement s'y limite -- le tactic prend la premiere action non-nulle PAR generateur, il n'y a
    pas d'argmax inter-generateurs), mais l'amplitude en utilite est une question de FIDELITE, qui
    se pose sur tout ce que le port a score, retenu ou non."""
    sonde.cands = []
    sonde.gens_joues = []
    sonde.move_args = None
    tac = sonde.instrumenter_tactic(tac_cls())
    action = tac.calculate_next_action(ctx)
    gen_retenu = sonde.gens_joues[-1] if sonde.gens_joues else -1
    tous = {(c[0], c[3]): c[2] for c in sonde.cands}     # {(generateur, ident): cle}
    if any(c[0] == gen_retenu for c in sonde.cands):
        seq, _ = _classement(sonde.cands, gen_retenu)
    else:
        seq, um = _classement_move(sonde)                # le fallback MOVEMENT n'a pas de Bucket
        tous.update({(gen_retenu, k): v for k, v in um.items()})
    return _ident(action), seq, tous, gen_retenu


def _ecart_utilite(u_nat: dict, u_geo: dict) -> tuple:
    """`(amplitude max, au moins une utilite a bouge)` sur les candidats COMMUNS aux deux
    substrats. Les cles sont des tuples heterogenes (`Fraction`, `float`) -> comparaison du
    PREMIER terme, qui est l'utilite ; les termes suivants sont des tie-breaks (id de cible)."""
    ampl, bouge = 0.0, False
    for k in set(u_nat) & set(u_geo):
        a, b = u_nat[k], u_geo[k]
        if a == b:
            continue
        bouge = True
        try:
            ampl = max(ampl, abs(float(a[0]) - float(b[0])))
        except (TypeError, ValueError, IndexError):
            pass
    return ampl, bouge


def _marge(seq: list, utils: dict, gen: int):
    """L'ecart d'utilite entre le 1er et le 2e du classement RETENU -- la DISTANCE au renversement.

    C'est ce qui transforme "l'utilite bouge de X" en une reponse a "est-ce que ca peut mordre ?" :
    tant que l'amplitude reste STRICTEMENT sous la marge, aucun renversement n'est possible dans
    cette situation. `None` = moins de deux candidats (rien a departager)."""
    if len(seq) < 2:
        return None
    try:
        a = float(utils[(gen, seq[0])][0])
        b = float(utils[(gen, seq[1])][0])
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return abs(a - b)


def mesurer_situation(sonde: Sonde, ctx, tac_cls) -> dict:
    sonde.reset_situation()
    sonde.mode = "nat"
    a_nat, s_nat, u_nat, g_nat = _decider(sonde, ctx, tac_cls)
    bascules_nat, calls, canal = sonde.n_bascules, sonde.n_calls, sonde.n_calls_canal
    voies = dict(sonde.voies)
    sonde.mode = "alt"
    a_alt, s_alt, u_alt, g_alt = _decider(sonde, ctx, tac_cls)
    sonde.mode = "nat"
    a_nat2, s_nat2, _u2, _g2 = _decider(sonde, ctx, tac_cls)
    ampl, bouge = _ecart_utilite(u_nat, u_alt)
    return {
        "action_nat": a_nat, "action_alt": a_alt, "stable": (a_nat == a_nat2 and s_nat == s_nat2),
        "decision_change": a_nat != a_alt,
        "classement_change": s_nat != s_alt,
        "meme_ensemble": set(s_nat) == set(s_alt),
        "cands_ensemble_change": set(u_nat) != set(u_alt),
        "utilite_change": bouge,
        "amplitude": ampl,
        "marge": _marge(s_nat, u_nat, g_nat),
        "bascules": bascules_nat, "calls": calls, "calls_canal": canal, "voies": voies,
        "gen_nat": g_nat, "gen_alt": g_alt, "n_cands": len(s_nat), "n_scores": len(u_nat),
    }


# --------------------------------------------------------------------------- balayage d'un board

def _gisement(res: dict) -> int:
    """Le GISEMENT STATIQUE du board : le nombre d'aretes dirigees que le basculement FERME
    (`G_gated \\ N`, mesure de #433-r4-r1-r4-r2). Il borne ce que l'aval peut voir -- un board a
    gisement nul ne peut RIEN faire bouger, et c'est ce qui rend la dispersion par board lisible
    (4 aretes sur `C1_74` contre 38 sur `C3_14`)."""
    from engine.entities.pathfinding.board import Board

    tiles = res.get("tiles") or []
    by_id = {t["id"]: t for t in tiles}
    bd = Board(tiles)
    elev = {t["id"]: int(t.get("elevation") or 0) for t in tiles}
    G, N = set(), set()
    for t in tiles:
        tid = t["id"]
        for nid in bd.neighbours_geometric(tid):
            if nid in by_id:
                G.add((tid, nid))
        for nid in (t.get("neighbours") or []):
            if nid in by_id:
                N.add((tid, nid))
    Gg = {(a, b) for (a, b) in G if abs(elev[a] - elev[b]) < 2}
    return len(Gg - N)


def _rpc_cache(rpc, sid):
    """`observeBattle` et `tileMeta` ne dependent QUE de l'etat, pas de l'unite : les cacher par
    ETAT divise par ~2 le cout RPC du balayage (le `build` du contexte les appelle une fois par
    unite). `pathDistToEnemies` depend de l'unite -> jamais cache."""
    cache: dict = {}

    def call(m, b, t=90):
        if m in ("observeBattle", "tileMeta", "combatSnapshot"):
            k = (m, json.dumps(b, sort_keys=True))
            if k not in cache:
                cache[k] = rpc(sid, m, b, t)
            return cache[k]
        return rpc(sid, m, b, t)

    call.vider = cache.clear
    return call


def balayer(sid, rpc, board: str, seed: int, steps: int, verbose: bool,
            substrat: str = "geo") -> tuple[int, dict]:
    from engine import weights
    from engine.ai import context as ai_ctx
    from engine.ai.tactic import DefaultAiUnitTactic
    from engine.playbook import scene as pb_scene
    from engine.runner import snapshot as snap

    rid, state_file = _build(board, seed, "walk")
    wt = weights.load()
    sonde = None
    resume = {"situations": 0, "decisions": 0, "classements": 0, "bascules": 0,
              "situations_avec_bascule": 0, "amplitude_max": 0.0, "voies": {},
              "instables": 0, "calls_canal": 0, "utilites": 0, "ensembles": 0,
              "amplitudes": [], "marges": [], "serrees": 0, "gisement": None}
    bad = 0
    try:
        r = _rpc_cache(rpc, sid)
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 180)
        if bg.get("ok"):
            resume["gisement"] = _gisement(bg)
            print("  gisement STATIQUE du board : %d arete(s) dirigee(s) fermee(s) par le "
                  "basculement" % resume["gisement"])
        predictor = pb_scene.build_predictor(r, rid)
        if predictor is None:
            print("  combatSnapshot KO -- prediction indisponible (scoring attaque desactive)")
        sonde = Sonde(substrat)
        for step in range(steps):
            r.vider()
            dv = rpc(sid, "decisionView",
                     snap.decision_view_seed_body(rid, allAbilities=True, maxRank=32), 180)
            mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            if predictor is not None:
                pb_scene.refresh_shields(predictor, r, rid)
            for uid in sorted(x for x in mov_by_unit if x is not None):
                if ai_ctx.machine_row(dv, uid) is not None:
                    continue                       # MoW : tactic DEDIE, hors perimetre (cf. rapport)
                ctx = ai_ctx.build(r, rid, dv, mov_by_unit, uid, wt, predictor)
                m = mesurer_situation(sonde, ctx, DefaultAiUnitTactic)
                resume["situations"] += 1
                resume["bascules"] += m["bascules"]
                resume["calls_canal"] += m["calls_canal"]
                resume["situations_avec_bascule"] += int(m["bascules"] > 0)
                resume["decisions"] += int(m["decision_change"])
                resume["classements"] += int(m["classement_change"] and not m["decision_change"])
                resume["utilites"] += int(m["utilite_change"])
                resume["ensembles"] += int(m["cands_ensemble_change"])
                resume["amplitude_max"] = max(resume["amplitude_max"], m["amplitude"])
                if m["utilite_change"]:
                    resume["amplitudes"].append(m["amplitude"])
                    if m["marge"] is not None:
                        resume["marges"].append(m["marge"])
                        # SERREE = l'amplitude atteint la marge -> un renversement etait POSSIBLE
                        # dans cette situation. C'est la mesure de PROXIMITE au basculement, celle
                        # qui empeche de lire "0 decision" comme "ca ne peut jamais mordre".
                        resume["serrees"] += int(m["amplitude"] >= m["marge"])
                for k, v in m["voies"].items():
                    resume["voies"][k] = resume["voies"].get(k, 0) + v
                if not m["stable"]:
                    resume["instables"] += 1
                    bad += 1
                    print("      INSTABLE step %d u%s : NAT != NAT (contamination)" % (step, uid))
                if m["decision_change"]:
                    print("      DECISION step %d u%s : nat=%s  alt=%s  (bascules=%d, gen %s/%s)"
                          % (step, uid, m["action_nat"], m["action_alt"], m["bascules"],
                             m["gen_nat"], m["gen_alt"]))
                elif m["classement_change"]:
                    print("      CLASSEMENT step %d u%s : meme action %s, ordre different "
                          "(%d cands, meme ensemble=%s, ampl=%.4f)"
                          % (step, uid, m["action_nat"], m["n_cands"], m["meme_ensemble"],
                             m["amplitude"]))
                elif verbose and m["bascules"]:
                    print("      inerte  step %d u%s : %d bascule(s), ampl=%.4f marge=%s gen=%s"
                          % (step, uid, m["bascules"], m["amplitude"],
                             ("%.4f" % m["marge"]) if m["marge"] is not None else "-", m["gen_nat"]))
            # avance d'un pas NATIF (on marche SA trajectoire, comme `engine_validate`)
            dry = rpc(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print("  natif epuise au step %d (%s)" % (step, dry.get("error") or "no action"))
                break
            acts = []
            for msg in ((dry.get("action") or {}).get("messages") or []):
                cls = msg.get("cls")
                if cls == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": msg["unitId"],
                                 "to": {"col": msg["to"]["col"], "row": msg["to"]["row"]}})
                elif cls == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": msg["casterId"],
                                 "targetId": msg.get("targetId"),
                                 "abilityType": msg["abilityType"]})
                elif cls == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": msg["unitId"]})
            if acts:
                rpc(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)
    finally:
        if sonde is not None:
            sonde.desinstaller()
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)
    return bad, resume


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", action="append", default=None)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--substrat", choices=("geo", "mut"), default="geo",
                    help="geo = l'etat d'AVANT #606 (la mesure) ; mut = contre-epreuve de "
                         "DETECTION du harnais (substrat volontairement faux, r<=2)")
    a = ap.parse_args()
    boards = a.board or list(BOARDS)
    sid, rpc = _rpc_factory()
    print("== #433-r4-r1-r4-r2-r4 -- l'AVAL du basculement d'adjacence (decision / classement)")
    print("   session=%s boards=%s seed=%d steps=%d substrat=%s"
          % (sid, ",".join(boards), a.seed, a.steps, a.substrat))
    bad, tout = 0, {}
    for b in boards:
        print("\n-- board %s" % b)
        n, res = balayer(sid, rpc, b, a.seed, a.steps, a.verbose, a.substrat)
        bad += n
        tout[b] = res
        print("   situations=%d  bascules=%d (sur %d situations)  decisions=%d  classements=%d  "
              "utilites=%d  ampl_max=%.4f" % (res["situations"], res["bascules"],
                                              res["situations_avec_bascule"], res["decisions"],
                                              res["classements"], res["utilites"],
                                              res["amplitude_max"]))
    print("\n== RESUME")
    tot_sit = sum(r["situations"] for r in tout.values())
    tot_bas = sum(r["bascules"] for r in tout.values())
    tot_dec = sum(r["decisions"] for r in tout.values())
    tot_cla = sum(r["classements"] for r in tout.values())
    tot_uti = sum(r["utilites"] for r in tout.values())
    tot_ens = sum(r["ensembles"] for r in tout.values())
    print("   board    gisem N     bascules  sit_bascule  DECISION  CLASSEMENT  utilite  ensemble"
          "  ampl_max")
    for b, r in tout.items():
        print("   %-8s %-5s %-5d %-9d %-12d %-9d %-11d %-8d %-9d %.4f"
              % (b, r["gisement"] if r["gisement"] is not None else "?", r["situations"],
                 r["bascules"], r["situations_avec_bascule"], r["decisions"], r["classements"],
                 r["utilites"], r["ensembles"], r["amplitude_max"]))
    voies = {}
    for r in tout.values():
        for k, v in r["voies"].items():
            voies[k] = voies.get(k, 0) + v
    print("   VOIES qui BASCULENT (call-site metier d'`is_adjacent`) :")
    for k, v in sorted(voies.items(), key=lambda kv: -kv[1])[:15]:
        print("      %-52s %d" % (k, v))
    if not voies:
        print("      (aucune)")
    amps = sorted(x for r in tout.values() for x in r["amplitudes"])
    marges = sorted(x for r in tout.values() for x in r["marges"])
    serrees = sum(r["serrees"] for r in tout.values())
    if amps:
        print("   AMPLITUDE en utilite brute (situations ou au moins un candidat bouge, n=%d) : "
              "min=%.4f med=%.4f max=%.4f" % (len(amps), amps[0], amps[len(amps) // 2], amps[-1]))
    if marges:
        print("   MARGE 1er-2e du classement retenu, sur CES memes situations (n=%d) : "
              "min=%.4f med=%.4f max=%.4f" % (len(marges), marges[0],
                                              marges[len(marges) // 2], marges[-1]))
        print("   situations SERREES (amplitude >= marge, un renversement etait possible) : %d"
              % serrees)
    print("   TOTAL  N=%d  bascules=%d  DECISIONS CHANGEES=%d  CLASSEMENTS CHANGES=%d  "
          "utilites bougees=%d  ensembles changes=%d"
          % (tot_sit, tot_bas, tot_dec, tot_cla, tot_uti, tot_ens))
    # REGIME : un zero de decision ne vaut que si des bascules ont EU LIEU pendant les decisions.
    if tot_bas == 0:
        print("   REGIME: MUET -- aucune adjacence n'a bascule pendant les decisions mesurees ;")
        print("           un '0 decision changee' ne conclut RIEN. (cf. --substrat mut)")
        bad += 1
    else:
        print("   REGIME: MORDANT -- %d bascule(s) d'adjacence traversees par les decisions" % tot_bas)
    if a.substrat == "mut":
        # CONTRE-EPREUVE : un substrat volontairement faux DOIT faire bouger des decisions. S'il
        # n'en bouge aucune, c'est le HARNAIS qui est aveugle, et la mesure `geo` ne vaut rien.
        print("   CONTRE-EPREUVE (substrat mut) : %d decision(s) changee(s) -- attendu > 0" % tot_dec)
        if tot_dec == 0:
            bad += 1
    print("VERDICT: %s (%d ecart(s) de harnais)" % ("PASS" if bad == 0 else "FAIL", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
