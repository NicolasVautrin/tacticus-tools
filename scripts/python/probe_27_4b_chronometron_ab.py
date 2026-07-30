"""probe #27-4b -- A/B causal LIVE de Chronometron (1226), la PREUVE que la route non-attaque marche.

CE QUI EST TESTE, et pourquoi ce n'est pas un simple « le moteur choisit la meme chose »

1226 n'a PAS de `damageProfile` : `state_bridge._is_attack_ability` la rejette, elle n'entre jamais
dans `plans`, et `ComparableAbilityGenerator._best_attack` ne la voit pas. AVANT la route
`playbook/nonattack.py`, le moteur ne pouvait donc **structurellement pas** proposer 1226 -- quelle
que soit la geometrie. Le bras `route OFF` de ce probe le re-mesure a chaque run (il vide
`NONATTACK_PLAYBOOKS`) : c'est le controle qui distingue « le port marche » de « le port est inerte
et l'accord vient d'ailleurs ».

FORMULE PORTEE (`IdunBattle.AI.Playbook.Loki.ChronometronPlaybook$$CalculateCustomUtility`) :
    W("Chronometron_AffectedEnemies") * Count( ChronometronAbility$$GetAffectedEnemies )
avec `GetAffectedEnemies` = `DSLSelectors.SurroundingEnemies(<unite>, GetNumberConstant(0x16 = range),
unique: 1, sel: 3)` -- surcharge 5-args, donc centre = MainTile REELLE du caster, centre exclu, pas
de `Unobscured`. Terme LINEAIRE dans le compte, CONSTANT sur (tuile, cible).

MONTAGE (board MC1_67 -- memes tuiles que `probe_27_4_warpflamer_ab.py`, deja eprouvees) :
  caster necroChronomancer en (2,6) ; cible de l'attaque normale FIXE en (2,3) (d=3, HORS du rayon 2,
  donc elle ne compte jamais dans le terme) ; deux appats qui passent de « loin » a d=2 :
  (2,4) puis (2,8). Un ALLIE prend ensuite la place du 2e appat : le selecteur est `Enemies(...)`,
  le compte doit RETOMBER.

Le probe mesure dans CHAQUE bras les `pairUtility` natives (attaque normale sur chaque ennemi) :
bit-identiques d'un bras a l'autre = confond de prediction MESURE et NUL (le deplacement d'un appat
ne change ni les stats ni le profil de degat ; sur ce board plat il ne change pas non plus le terme
de couverture).

Usage :
    python catalog_inject.py --units necroChronomancer --out <abs>/logs/bc_chrono.json
    python probe_27_4b_chronometron_ab.py --build [--engine] [--hp-target N]
    python probe_27_4b_chronometron_ab.py --engine        # re-joue sur le runner du state-file
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_chrono.json"
STATE = LOGS / "rs_chrono_ab.json"
BOARD = "MC1_67"
SEED = 909
CHRONOMETRON = 1226
NORMAL = 69

P_UNITS = "necroChronomancer,ultraCalgar"
A_UNITS = "tauCrisis,orksWarboss,necroWarden"

CASTER_VID = "necroChronomancer"
ALLY_VID = "ultraCalgar"
TGT_VID = "tauCrisis"          # decor : reste a d=3 (hors rayon ET hors portee d'arme -> pair 0)
# L'ORDRE des appats est CALIBRE : le PREMIER amene est celui dont la `pairUtility(69)` est la plus
# FORTE. Le maximum des paires est donc atteint des le bras n=1 et ne bouge plus -- l'utilite de
# l'attaque normale concurrente est CONSTANTE de n=1 a n=2, et seule la marche `W -> 2W` du custom
# peut expliquer une bascule. C'est ce qui rend la LINEARITE mesurable (un terme booleen aurait
# bascule des n=1).
BAIT1_VID = "orksWarboss"      # arrive le PREMIER, sur la tuile a paire FORTE
BAIT2_VID = "necroWarden"      # arrive ensuite, sur la tuile a paire FAIBLE

CASTER_TILE = "2,6"
TGT_TILE = "2,3"               # d=3 du caster -> JAMAIS dans SurroundingEnemies(range=2)
# Les deux tuiles a d=2. MESURE (et non supposé) : depuis (2,6), une cible en (2,8) rend une
# `pairUtility(69)` ~3x celle d'une cible en (2,4) -- c'est la TUILE qui porte l'ecart, pas l'unite
# (les deux ordres ont ete essayes). NEAR1 est donc la tuile FORTE : le plancher `max(pair)` est
# atteint des le bras n=1 et ne bouge plus quand le second appat arrive.
NEAR1, NEAR2 = "2,8", "2,4"
FAR1, FAR2, FAR3 = "6,0", "5,0", "4,0"
# `--hp-target` par DEFAUT : l'utilite de degat est ~ degat/PVmax, donc gonfler les PV des cibles
# CONTRACTE l'ecart absolu sans changer l'ordre des paires. 34000 amene `pair(necroWarden)` de 56.4
# a ~14 : l'attaque normale vaut alors `pair + Tile + 1` dans (W, 2W) -- la fenetre ou la marche du
# custom decide. Aucun scalaire n'est ajuste : on deplace le POINT DE MESURE.
HP_TARGET_DEFAULT = 85000


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} depuis `decisionView` -- les ids ne sont PAS hardcodes."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")))
    return out


def build(hp_target: int) -> int:
    if not SEED_BC.exists():
        raise SystemExit(
            "seed BC augmentee absente : lancer d'abord\n"
            "  python catalog_inject.py --units necroChronomancer --out %s" % SEED_BC)
    extra = ["--hp-target", str(hp_target)] if hp_target else []
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(STATE)] + extra)
    rid = _runner_id()
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    want = ((ids[CASTER_VID], CASTER_TILE), (ids[TGT_VID], TGT_TILE),
            (ids[BAIT1_VID], FAR1), (ids[BAIT2_VID], FAR2), (ids[ALLY_VID], FAR3))
    for unit, to in want:
        _move(rid, unit, to)
    _assert_placed(rid, want)
    return rid


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : l'unite reste ou elle est et les bras degenerent en UN
    seul etat, ou l'accord moteur<->natif est trivialement vrai (mesure du 2026-07-30, #27-4)."""
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def _native(rid: int, caster: int, enemies: list) -> tuple[dict, tuple, list]:
    pairs = {}
    for tgt in enemies:
        r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": caster,
                                    "targetId": tgt, "abilityType": NORMAL}])
        pairs[tgt] = r.get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen, msgs = (None, None), []
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        msgs = u.get("proposed") or []
        for m in msgs:
            if m.get("cls") == "ActiveAbilityMessage":
                chosen = (m.get("abilityType"), m.get("targetId"))
    return pairs, chosen, msgs


def _engine(rid: int, caster: int) -> dict:
    """Trois decisions MOTEUR sur le MEME etat :
      * `on`     : telle quelle ;
      * `zero`   : custom de 1226 force a 0 -> le terme est-il NECESSAIRE ?
      * `noroute`: `NONATTACK_PLAYBOOKS` vide -> etat d'AVANT le port (controle de deblocage).
    Rend aussi le custom calcule et le compte d'ennemis dans le rayon."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor)
    pb = PB.REGISTRY.get(CHRONOMETRON)
    custom = pb.calculate_custom_utility(ctx, ctx.origin, caster, CHRONOMETRON)
    from engine import battle_query as bq
    from engine.playbook.base import tile_utility
    n = len(bq.surrounding_enemies_in_range(ctx.origin, ctx.epos, pb._range()))
    added = pb.is_caster_added(ctx, ctx.origin)
    tile = tile_utility(ctx, ctx.origin)     # terme positionnel a la tuile COURANTE (encadrement)

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, tile, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)
    # HYPOTHESE CONCURRENTE : et si le selecteur etait ancre sur la TUILE CANDIDATE (`caster_tile`)
    # au lieu de l'entite ? On rejoue la decision moteur avec CETTE variante. Si elle fait basculer
    # le moteur sur 1226 alors que le natif dit autre chose, l'hypothese est REFUTEE PAR LE NATIF --
    # c'est ce qui transforme le bras d'ancrage en mesure, au lieu d'un simple « le natif n'a pas
    # caste » (qui pourrait s'expliquer par n'importe quel autre terme).
    def _tile_anchored(self, c, tile, target, aid):
        from engine import battle_query as _bq
        return float(len(_bq.surrounding_enemies_in_range(tile, c.epos, self._range()))) \
            * c.wt.sub("ActiveAbilities", self.W_KEY)
    type(pb).calculate_custom_utility = _tile_anchored
    orig_added = type(pb).is_caster_added
    type(pb).is_caster_added = lambda self, c, tile: True
    try:
        tileanchor = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
        type(pb).is_caster_added = orig_added
    return {"on": (on.get("ability"), on.get("target")),
            "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "tileanchor": (tileanchor.get("ability"), tileanchor.get("target")),
            "custom": custom, "n": n, "caster_added": added, "tile": tile,
            # ORDRE des cibles eligibles tel que le port le consomme (`GetEligibleTargetsEntities`).
            # A custom EGAL entre deux cibles, c'est cet ordre qui tranche (keep-first STRICT) --
            # le natif, lui, herite de l'ordre de `TileQuery.IterateSurroundingTiles`. Affiche pour
            # que la coincidence soit VERIFIEE, pas supposee.
            "targets": pb.eligible_targets(ctx, CHRONOMETRON)}


def measure(rid: int, label: str, engine: bool) -> dict:
    u = _units(rid)
    caster = u[CASTER_VID][0]
    enemies = [u[v][0] for v in (TGT_VID, BAIT1_VID, BAIT2_VID)]
    pairs, chosen, msgs = _native(rid, caster, enemies)
    print("  --- %s ---" % label)
    print("      positions : caster=%s tgt=%s bait1=%s bait2=%s ally=%s"
          % (u[CASTER_VID][1], u[TGT_VID][1], u[BAIT1_VID][1],
             u[BAIT2_VID][1], u[ALLY_VID][1]))
    print("      pairUtility(69) natives : %s"
          % {v: pairs[u[v][0]] for v in (TGT_VID, BAIT1_VID, BAIT2_VID)})
    print("      natif  : ability=%s target=%s  (messages=%s)"
          % (chosen[0], chosen[1], [m.get("cls") for m in msgs]))
    row = {"pairs": pairs, "native": chosen, "caster": caster}
    if engine:
        e = _engine(rid, caster)
        print("      moteur : on=%s | custom=%s n=%s caster_added=%s tile=%.6f"
              % (e["on"], e["custom"], e["n"], e["caster_added"], e["tile"]))
        print("      moteur : custom force a 0 -> %s | route DESACTIVEE -> %s | to=%s"
              % (e["zero"], e["noroute"], e["to"]))
        print("      cibles eligibles (ordre consomme par la route) : %s" % (e["targets"],))
        row["engine"] = e
    return row


def anchor_build(hp_target: int) -> int:
    """Monte un runner DEDIE au bras d'ancrage. Le caster n'est JAMAIS deplace : il garde sa tuile de
    spawn ET son mouvement (un `act move` le consomme -- sur le runner de l'A/B principal
    `aiMovableTiles` rend 0 tuile pour lui, ce qui rend le test d'ancrage impossible : sans tuile
    candidate differente de l'origine, les deux hypotheses coincident)."""
    import hexgeo
    if not SEED_BC.exists():
        raise SystemExit("seed BC augmentee absente (cf. l'en-tete)")
    extra = ["--hp-target", str(hp_target)] if hp_target else []
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(STATE)] + extra)
    rid = _runner_id()
    u = _units(rid)
    caster, origin = u[CASTER_VID]
    mv = L._rpc("aiMovableTiles", [{"runnerId": rid}])
    tiles = []
    for x in (mv.get("units") or []):
        if x.get("unitId") == caster:
            tiles = [(t["col"], t["row"]) for t in (x.get("tiles") or [])]
    board = [(c, r) for c in range(7) for r in range(9)]
    occupied = {p for _v, (_i, p) in u.items()}
    best = None
    for T in tiles:
        cand = [p for p in board
                if p not in occupied and p != T
                and hexgeo.distance(p, T) <= 2 and hexgeo.distance(p, origin) > 2]
        if len(cand) >= 2:
            best = (T, cand[:2])
            break
    if best is None:
        raise SystemExit("aucune tuile de move ne separe les deux ancrages -- montage impossible")
    T, (A, B) = best
    print("[anchor] caster=%s origin=%s tuile de MOVE visee=%s appats=%s,%s "
          "(d(origin)=%d,%d ; d(T)=%d,%d)"
          % (caster, origin, T, A, B, hexgeo.distance(A, origin), hexgeo.distance(B, origin),
             hexgeo.distance(A, T), hexgeo.distance(B, T)))
    want = ((u[TGT_VID][0], FAR1), (u[ALLY_VID][0], FAR3),
            (u[BAIT1_VID][0], "%d,%d" % A), (u[BAIT2_VID][0], "%d,%d" % B))
    for unit, to in want:
        _move(rid, unit, to)
    _assert_placed(rid, want)
    return rid


def anchor(rid: int, engine: bool) -> int:
    """BRAS D'ANCRAGE — le custom est-il pris a la position REELLE du caster, ou a la TUILE CANDIDATE
    du balayage IA ?

    `ChronometronAbility$$GetAffectedEnemies` passe a `DSLSelectors.SurroundingEnemies` la surcharge
    5-args dont le centre est une ENTITE : `SurroundingTiles`/`Tiles` partent de
    `EntityExtensions.IterateTiles(unit)`, donc de la MainTile REELLE — et l'`AbilityEntities` que
    `ChronometronPlaybook$$CalculateCustomUtility` construit a ses slots de POSITION zero-initialises.
    Le port en tire un terme CONSTANT sur les tuiles. Ce bras le CONFRONTE au lieu de le supposer.

    Montage : les deux appats sont groupes a d=3 et d=4 du caster (donc n = 0 a sa position REELLE),
    mais a d<=2 d'une tuile de MOVE atteignable. Si le natif ancrait sur la tuile candidate, il y
    verrait n=2 (custom = 2W = 20 > l'attaque normale de ce montage) et casterait 1226 en se
    deplacant. S'il ancre sur la position reelle, custom = 0 et il ne caste pas."""
    row = measure(rid, "ANCRAGE : appats a d>2 du caster REEL, d<=2 d'une tuile de MOVE",
                  engine)
    nat_ab = row["native"][0]
    print("\n=== ANCRAGE ===")
    print("  natif -> ability=%s target=%s" % row["native"])
    ok = (nat_ab != CHRONOMETRON)
    if engine:
        e = row["engine"]
        print("  moteur (port, ancre ENTITE)     -> %s | custom=%s n=%s"
              % (e["on"], e["custom"], e["n"]))
        print("  moteur (variante ancre TUILE)   -> %s" % (e["tileanchor"],))
        disc = (e["tileanchor"][0] == CHRONOMETRON)
        print("  bras DISCRIMINANT (la variante tuile aurait bascule sur 1226) : %s"
              % ("OUI" if disc else "NON -- montage non concluant, ne rien conclure"))
        ok = ok and disc and (e["on"] == row["native"])
    print("  ancrage sur la position REELLE (le natif NE caste PAS 1226) : %s"
          % ("CONFIRME" if nat_ab != CHRONOMETRON else "REFUTE -- le port est FAUX"))
    return 0 if ok else 1


def run_ab(rid: int, engine: bool) -> dict:
    """Deroule les QUATRE bras sur un runner deja monte et rend les mesures. Extrait de `main` pour
    que la garde `tests/engine/test_chronometron_decision_live.py` les rejoue sans dupliquer le
    montage."""
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    rows = {}
    rows["n=0"] = measure(rid, "n=0 : aucun ennemi a d<=2 du caster", engine)
    _move(rid, ids[BAIT1_VID], NEAR1)
    rows["n=1"] = measure(rid, "n=1 : %s en %s (tuile FORTE)" % (BAIT1_VID, NEAR1), engine)
    _move(rid, ids[BAIT2_VID], NEAR2)
    rows["n=2"] = measure(rid, "n=2 : %s en %s (tuile faible)" % (BAIT2_VID, NEAR2), engine)
    _move(rid, ids[BAIT2_VID], FAR2)
    _move(rid, ids[ALLY_VID], NEAR2)
    rows["ally"] = measure(rid, "n=1 ennemi + 1 ALLIE a d=2 (controle `Enemies`)", engine)
    return rows


def main() -> int:
    argv = sys.argv[1:]
    engine = "--engine" in argv
    if "--anchor" in argv:
        hp0 = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--hp-target=")),
                       str(HP_TARGET_DEFAULT)))
        return anchor(anchor_build(hp0) if "--build" in argv else _runner_id(), engine)
    hp = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--hp-target=")),
                  str(HP_TARGET_DEFAULT)))
    rid = build(hp) if "--build" in argv else _runner_id()
    print("runner=%d board=%s seed=%d hp-target=%s" % (rid, BOARD, SEED, hp or "defaut"))
    rows = run_ab(rid, engine)

    print("\n=== SYNTHESE ===")
    ok = True
    for k in ("n=0", "n=1", "n=2", "ally"):
        nat_ab, nat_tgt = rows[k]["native"]
        line = "  %-5s : natif -> ability=%s target=%s" % (k, nat_ab, nat_tgt)
        if engine:
            e = rows[k]["engine"]
            agree = (e["on"] == (nat_ab, nat_tgt))
            ok = ok and agree
            line += " | moteur -> %s %s (custom=%s n=%s)" % (
                e["on"], "MATCH" if agree else "DIVERGE", e["custom"], e["n"])
        print(line)
    # Le natif ne peut pas caster 1226 sans ennemi a portee (`GetCasterNotAddedReason` -> 0x800).
    print("  n=0 (aucune cible eligible) : le natif ne propose PAS 1226 : %s"
          % ("OUI" if rows["n=0"]["native"][0] != CHRONOMETRON else "NON"))
    print("  n=2 : le natif propose 1226 : %s"
          % ("OUI" if rows["n=2"]["native"][0] == CHRONOMETRON else "NON"))
    if engine:
        nec = any(rows[k]["engine"]["zero"] != rows[k]["engine"]["on"]
                  for k in ("n=1", "n=2"))
        deb = any(rows[k]["engine"]["noroute"] != rows[k]["engine"]["on"]
                  for k in ("n=1", "n=2"))
        print("  terme NECESSAIRE (custom=0 fait diverger le moteur)        : %s"
              % ("OUI" if nec else "NON"))
        print("  route NECESSAIRE (sans elle le moteur ne peut pas dire 1226) : %s"
              % ("OUI" if deb else "NON"))
        print("  linearite : custom n=1 -> %s ; n=2 -> %s"
              % (rows["n=1"]["engine"]["custom"], rows["n=2"]["engine"]["custom"]))
        # ENCADREMENT sans fitting. `u_action(69) = pair_max + Tile + 1` (custom de l'attaque
        # normale = +1, deja etabli) et `u_action(1226) = n*W + Tile` a la MEME tuile -> le terme
        # Tile s'annule. n=1 ne bascule pas => W < pair_max + 1 ; n=2 bascule => 2W > pair_max + 1.
        lin = (rows["n=1"]["native"][0] != CHRONOMETRON
               and rows["n=2"]["native"][0] == CHRONOMETRON)
        print("  linearite MESUREE (n=1 ne bascule pas, n=2 bascule) : %s"
              % ("PROUVEE -- un terme booleen est exclu" if lin else "NON ETABLIE"))
        if lin:
            floor = max(rows["n=2"]["pairs"].values()) + 1.0
            print("  encadrement du poids (forme lineaire W*n) : %.4f < W < %.4f"
                  % (floor / 2.0, floor))
    print("(pense a disposer le runner : disposeRunner)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
