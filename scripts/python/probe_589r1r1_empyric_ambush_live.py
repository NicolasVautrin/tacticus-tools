#!/usr/bin/env python
"""probe #589-r1-r1 -- MESURE du SEUIL de `EmpyricAmbushEffect$$IsValidAttackForBuff` (1578).

CRITERE BINAIRE, pose avant toute methode :

    « A quelle valeur de `TilesMovedThisTurn` du CASTER DE L'ATTAQUE le natif bascule-t-il
      `IsValidAttackForBuff`, et le port fait-il pareil ? »

Le seuil natif est `Direct(GetNumberConstant(0x51 = movement))`, RELU du gameconfig
(`abilities.EmpyricAmbush.constants["movement"]` = 4), jamais code en dur. C'est le SEUL des six
consommateurs de `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn` qui echappe a la borne
saturante de #589 (`min(n_G, n_C) >= 2` des que la beeline mord, donc tout seuil `<= 2` est deja
franchi AVANT le rebranchement -- `case-589-r1` §2).

## LE MONTAGE, et pourquoi chaque piece y est

  * `eldarLhykhis` porte l'ability active. Elle est **HORS CATALOGUE** (`catalog_inject --missing`
    la liste) -> `write_augmented_seed_bc` + `--seed-bc`. La fiche #589-r1-r1 la disait « au pool » :
    c'est FAUX, `rl_duel build --list-pool` ne la rend pas.
  * L'ATTAQUANT est `blackHaarken`, et ce choix est ce qui rend la mesure DISCRIMINANTE :
      - trait `Hero`      -> `HasTrait(Caster, 0x10)` OUVRE ;
      - faction BlackLegion -> `HasFaction(Caster, 8 = Aeldari)` FERME, donc le `op_BitwiseOr` NE
        SATURE PAS et seul `TilesMovedThisTurn >= movement` peut ouvrir le buff. Un attaquant
        Aeldari rendrait le seuil INOBSERVABLE (regime degenere) ;
      - trait `Flying`    -> regime `Fly` (ptype 3), l'un des deux regimes ou le rebranchement de
        #589 mord (`Walk` est mesure INERTE : 0 basculement sur 3906 couples x 2 boards) ;
      - arme MELEE 4 coups -> la salve est lisible coup par coup.
  * `--crit 100,700` : TOUS les coups critent des DEUX cotes, donc `extraCritChance` est sature
    (`clamp(100 + 25) = 100`) et ce qui bouge est `extraCritDmg` -- un ecart DETERMINISTE de
    `554 x 1.80 = 997` par coup, sans le moindre tirage. C'est le regime le plus fort, pas le plus
    confortable : a `--crit 0,700` le buff n'ouvre qu'une chance de 25 %, donc un bras sans crit ne
    prouverait rien.
  * Le bras est ETIQUETE PAR LE COMPTEUR NATIF MESURE (`actorStats.tilesMovedThisTurn`), jamais par
    la distance qu'on visait : on MESURE `n`, on ne le suppose pas.

## CE QUE LE CARRE PROUVE

Pour chaque `n` mesure, deux confrontations independantes :
  1. LIVE == OFFLINE (le port reproduit le natif a ce `n`) ;
  2. MUTATION `NOCHANNEL` (l'effet retire d'`EFFECT_CLASSES` -> retombe sur `BaseEffect`, qui rend
     `None`) : le rejeu doit CHANGER quand `n >= movement`, et NE PAS changer quand `n < movement`.

Le point 2 est ce qui interdit l'accord DEGENERE : sans lui, « ca concorde » ne vaut rien -- les
deux cotes pourraient etre d'accord parce qu'AUCUN des deux n'applique le buff.

Usage :
    python probe_589r1r1_empyric_ambush_live.py --dist 2      # sous le seuil attendu
    python probe_589r1r1_empyric_ambush_live.py --dist 4      # au-dessus
    python probe_589r1r1_empyric_ambush_live.py --dist 2,3,4,5 --board C1_74
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

CARRIER = "eldarLhykhis"          # porteur de l'ability active 1232 (HORS CATALOGUE -> --seed-bc)
ATTACKER = "blackHaarken"         # Hero + NON-Aeldari + Flying + melee : le sujet du seuil
EFFECT_NAME = "EmpyricAmbush"     # cle EFFECT_CLASSES == decisionView.units[].effects[].name
EFFECT_TYPE = 1578                # EffectType 0x62a
ABILITY_TYPE = 1232               # ActiveAbilityType 0x4d0


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def seuil_du_gameconfig() -> int:
    """`GetNumberConstant(0x51 = movement)` RELU, jamais code en dur -- c'est la meme lecture que
    le cran offline `test_589r1_tiles_moved_consumers_offline.py`."""
    import gameconfig as GC
    v = ((GC.ability("EmpyricAmbush") or {}).get("constants") or {}).get("movement")
    if v is None:
        raise SystemExit("EmpyricAmbush.constants.movement absent du gameconfig")
    return int(v)


def seed_bc_avec_lhykhis() -> str:
    """`eldarLhykhis` n'est PAS au catalogue du seed BC -> injection (jamais un deepcopy a la main,
    qui ne poserait que `BC.Units` et fauterait au cast, cf. runner.md §1bis)."""
    import catalog_inject
    fd, out = tempfile.mkstemp(prefix="probe_589r1r1_bc_", suffix=".json")
    os.close(fd)
    catalog_inject.write_augmented_seed_bc(out, [CARRIER])
    return out


def _hits_of(res, caster, target) -> tuple:
    """Degats PAR COUP : les `tags` des events d'`applyAction`, cle `Amount`, filtres sur la paire
    (`Attacker_Id`, `Target_Id`)."""
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    out = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Attacker_Id") == caster and td.get("Target_Id") == target:
            out.append(int(td["Amount"]))
    return bool(a0.get("ok")), out


def build(a, tag, seed_bc):
    fd, sf = tempfile.mkstemp(prefix="probe_589r1r1_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--seed-bc", seed_bc,
            "--p-units", "%s,%s" % (CARRIER, ATTACKER),
            "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", "400000", "--hp-player", "400000",
            "--no-ai", "--crit", a.crit, "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (tag, (p.stderr or p.stdout or "")[-600:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def stage(h, dist, verbose=False):
    """Monte le regime et rend `(rec, raison)` -- `raison is None` == regime ATTEINT.

    ORDRE NON NEGOCIABLE (chaque inversion a deja coute une mesure fausse) :
      1. PLACER les trois unites (un `move` compte dans `tilesMovedThisTurn`) ;
      2. `reach_my_turn(force_cycle=True)` -- le cycle force purge les compteurs via
         `IdunBattle.Operations.StartTurnOperation$$ResetUnit` ;
      3. Lhykhis CASTE 1232 (elle VOLE d'elle-meme vers une tuile adjacente a la cible : le
         `FlyUnit` du `ExecuteBehaviour` -- rien a placer pour elle) ;
      4. SNAPSHOT (avant le pas de l'attaquant, que `replay_offline` rejouera) ;
      5. l'ATTAQUANT fait SON pas -- le seul move compte ;
      6. LIRE le compteur natif : c'est lui qui ETIQUETTE le bras."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    att = h.by_visual(ATTACKER, dv)
    if me is None or att is None:
        return None, "porteur ou attaquant absent du deploiement"
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < 1:
        return None, "aucun ennemi"
    tgt = ens[0]

    # (1) placer : la cible sur une ancre a 6 voisins, l'attaquant a `dist`, les autres au loin.
    for anchor in [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]:
        starts = h.free_tiles(anchor, dist + 2, exclude=(me["id"], tgt["id"], att["id"]))
        cands = [s for s in starts if hexgeo.distance(s, anchor) == dist]
        if not cands:
            continue
        far = [s for s in starts if hexgeo.distance(s, anchor) >= dist + 2]
        if not far:
            continue
        for other in ens[1:]:
            h.place(other["id"], far[0])
        if not h.place(tgt["id"], anchor):
            continue
        # l'attaquant part d'une tuile ADJACENTE a son point de depart vise : c'est SON pas
        # (etape 5) qui doit compter `dist` tuiles, donc on le pose LOIN et il ira sur `cands[0]`...
        # non : on le pose sur `cands[0]` et il ira A L'ANCRE (contact melee) en `dist` tuiles.
        if not h.place(att["id"], cands[0]):
            continue
        start, step_to = cands[0], None
        # tuile de CONTACT : adjacente a l'ancre, libre, d'ou l'attaque melee est legale
        contacts = [s for s in h.free_tiles(anchor, 1, exclude=(me["id"], tgt["id"], att["id"]))
                    if hexgeo.distance(s, anchor) == 1]
        if not contacts:
            continue
        step_to = contacts[0]
        break
    else:
        return None, "geometrie non realisable (dist=%d)" % dist

    # (2) mon tour, compteurs purges
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    me, att, tgt = (h.by_visual(CARRIER, dv), h.by_visual(ATTACKER, dv),
                    next((u for u in h.enemies_of(h.my_player, dv) if u["id"] == tgt["id"]), None))
    if me is None or att is None or tgt is None:
        return None, "une unite a disparu apres le cycle de tour"

    # (3) le CAST : Lhykhis pose la marque sur la cible (et vole elle-meme)
    cast = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
        "abilityType": ABILITY_TYPE}}, 60)
    a0 = (cast.get("actions") or [{}])[0] if isinstance(cast, dict) else {}
    if not a0.get("ok"):
        return None, "cast EmpyricAmbush refuse : %s" % str(cast)[:300]
    dv = h.dview()
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
    names = [e.get("name") for e in ((tu or {}).get("effects") or [])]
    if EFFECT_NAME not in names:
        return None, "la marque %s n'est PAS sur la cible (effets: %s)" % (EFFECT_NAME, names)

    # (4) snapshot AVANT le pas de l'attaquant
    atk_type = h.normal_attack_type(att["id"], dv)
    rec = {"caster": att["id"], "target": tgt["id"], "lhykhis": me["id"],
           "start": start, "step_to": step_to, "anchor": anchor,
           "ability_type": int(atk_type), "dist": dist}
    rec["snapshot"] = h.snapshot()

    # (5) LE PAS -- le seul move compte pour `TilesMovedThisTurn(Caster)`
    if not h.place(att["id"], step_to):
        return None, "pas de l'attaquant refuse"

    # (6) le compteur NATIF etiquette le bras
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
    if verbose:
        print("    start=%s -> step_to=%s (ancre %s) | n natif = %d" % (start, step_to, anchor, n))
    return rec, None


def strike(h, rec):
    live = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    ok, hits = _hits_of(live, rec["caster"], rec["target"])
    if not ok or not hits:
        return None, "attaque live refusee/vide (%s)" % str(live)[:200]
    if not any(u.get("id") == rec["target"] for u in h.alive()):
        return None, "cible MORTE pendant la salve -- flux live tronque"
    return hits, None


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE du MEME pas + de la MEME attaque, RNG neutralise par le dump pris apres le pas.

    MUTATION `NOCHANNEL` : l'effet retire d'`EFFECT_CLASSES` AVANT `load_state` -- c'est la FACTORY
    (`EffectFactory.create` -> `registry.get(name, BaseEffect)`) qui materialise l'effet capte, donc
    le retrait le fait retomber sur `BaseEffect`, dont les deux canaux crit rendent `None`.
    C'est la vue « d'avant ce port ». Restauree en `finally`."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    saved = EFFECT_CLASSES.get(EFFECT_NAME)
    try:
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        return h.replay_offline(rec)["per_hit"]
    finally:
        if saved is not None:
            EFFECT_CLASSES[EFFECT_NAME] = saved


def run_case(a, rpc, Board, Harness, dist, seuil, seed_bc) -> int:
    rid, sf = build(a, "d%d" % dist, seed_bc)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, dist, a.verbose)
        if rec is None:
            print("[dist=%d] REFUS : %s" % (dist, why))
            return 2
        n = rec["n_natif"]
        attendu = n >= seuil                       # AmountIsEqualOrGreater(n, movement)

        live, why = strike(h, rec)
        if live is None:
            print("[dist=%d n=%d] REFUS : %s" % (dist, n, why))
            return 2
        off = replay(h, rec)
        k = len(live)
        accord = (off[:k] == live)

        # CONTRE-EPREUVE : sans le canal, le rejeu doit CHANGER ssi le buff s'appliquait.
        mut = replay(h, rec, mutate="NOCHANNEL")
        mord = (mut[:k] != off[:k])

        rc = 0
        if not accord:
            rc |= 1
        if mord != attendu:
            rc |= 1
        print("[n=%d] seuil=%d attendu=%-5s | LIVE %s" % (n, seuil, attendu, live[:6]))
        print("        OFFLINE %s  accord=%s" % (off[:k][:6], accord))
        print("        NOCHANNEL %s  buff_actif=%s (attendu %s)" % (mut[:k][:6], mord, attendu))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit", default="100,700",
                    help="CritChance,CritDamage des p-units. 100 sature extraCritChance -> ce qui "
                         "bouge est extraCritDmg, DETERMINISTE.")
    ap.add_argument("--target-unit", default="necroWarden")
    ap.add_argument("--other-unit", default="necroOverlord")
    ap.add_argument("--dist", default="2,4", help="distances a jouer (un runner par distance)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    seuil = seuil_du_gameconfig()
    print("== #589-r1-r1 EmpyricAmbush -- seuil movement (gameconfig) = %d" % seuil)

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    seed_bc = seed_bc_avec_lhykhis()
    rc = 0
    try:
        for d in [int(x) for x in a.dist.split(",") if x.strip()]:
            rc |= run_case(a, rpc, Board, ChargeRegimeHarness, d, seuil, seed_bc)
    finally:
        Path(seed_bc).unlink(missing_ok=True)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
