#!/usr/bin/env python3
"""probe_921 -- ISOLE le passif `SanguinaryPriest` de `bloodSanguinary` (port #921).

POURQUOI CE PROBE. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility` est
un `On(0x1c = ArrivedAtFinalTile)` : il tire SUR LE MOVE SEUL, sans qu'aucune ability ne soit
castee. Tout delta de PV mesure sur un allie adjacent apres un simple deplacement du pretre est
donc, entierement, ce passif -- exactement le meme isolat que `probe_303` pour
`FabricatorClawArray`, et pour la meme raison native.

DECOMPOSITION PAR ETAGE (jamais un scalaire fitte) :

  E1  CONFIG     : `hpToHeal[lvl]` / `maxHpToHeal[lvl]` x multiplicateur de rarete
                   (= `AbilityConfiguration$$GetVariableForLevel(cfg, 0x20 / 0x47, abilityState)`)
  E2  SELECTEUR  : `AdjacentFriends(Owner,1,3)` puis `MechanicalUnits(., 3)` puis la soustraction,
                   etage par etage, sur l'etat POST-move du port
  E3  MOVE SEUL  : delta PV de CHAQUE allie, LIVE (le natif) vs PORT (`MoveUnitMessage` sur la MEME
                   capture, PRNG cale sur l'etat MT live) -- le montant est compare PAR CIBLE
  E3b TIRAGE     : avec DEUX cibles, les deux montants natifs doivent pouvoir DIFFERER (le natif
                   appelle `<+0x60>.Calculate` DANS la boucle de `HealBehaviour$$Execute`)
  E4  CONTROLE   : un 2e move dans le MEME tour ne doit RIEN soigner (le flag `ArrivedAtFinalTile`
                   est deja pose -> `UnitFlagsComponent.Add` rend false -> aucun `On(0x1c)`)
  E5  OWNER-IS-ACTOR : le montage DEPLACE d'abord les allies eux-memes ; aucun d'eux ne doit etre
                   soigne par SON PROPRE move (`get_OwnerIsActor` du `CreateTrigger`)
  E6  DISCRIMINANTS : l'allie MECANIQUE adjacent reste a 0 (filtre `MechanicalUnits` du selecteur),
                   un ENNEMI adjacent reste a 0, et le TEMOIN est assertionne NON VIDE (au moins un
                   soin > 0 : un accord a montant nul serait sature)

MONTAGE (roster derive, pas espere) :
  team 1 = `bloodSanguinary` (le pretre) + DEUX allies NON mecaniques blesses (`astraBullgryn`,
           `bloodDeathCompany`) + UN allie MECANIQUE blesse (`admecMarshall`, traits {Hero,
           Mechanical} -- aucun trait de placement qui perturberait le deploiement)
  team 2 = `blackTerminator`, `worldJakhal`
  `--unit-stat <vis>:RemainingHealth=1` blesse AU MAXIMUM sans toucher la sante MAX (`--hp-player`
  ecrirait `Health` ET `RemainingHealth`, donc l'unite resterait a 100 % et
  `AttackQuery$$IsDamagedUnit` serait FAUX -- piege mesure le 2026-07-30, cf. `_repair_stage.py`).
  DEUX cibles non mecaniques, c'est le regime qui discrimine le TIRAGE PAR CIBLE : un port qui
  hisserait le tirage hors de la boucle rendrait deux montants EGAUX.

MESURE DE REFERENCE (board MC1_67, seed 777, passif L50 mult 180 %, plage [1496, 2194]) :
  natif +2179 / +1912 (DEUX montants DISTINCTS), port +2179 / +1912 ; mecanique 0/0 ; 2e move 0/0.

MUTANTS (voir `--mutant`), joues sur la MEME capture :
  `tirage-hisse` TUE · `sans-mecanique` TUE · `borne-exclusive` TUE · `sans-scope-groupe` SURVIVANT
  (cause MESUREE : `GetGroupUnitHealLimit` rend `int.MaxValue` des que `nrOfMembers < 2`, et AUCUNE
   unite du pool rank 17 n'est multi-membres -> le `scope = 1` est etabli par les xrefs
   `HealBehaviourOptions$$ForRegenerate` du decompile, pas par un regime confrontable).

Usage:
    python probe_921_sanguinary_priest.py [--board MC1_67] [--seed 777] [--state-file <abs>]
                                          [--mutant aucun|tirage-hisse|...]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]

from engine.dsl.base import Const                                       # noqa: E402
from engine.entities.pathfinding.board import Board                     # noqa: E402
from engine.entities.selectors.accessors import Owner                   # noqa: E402
from engine.entities.selectors.units import (AdjacentFriends,           # noqa: E402
                                             MechanicalUnits)
from engine.runner.abilities.behaviours.context import entities_from_state   # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent    # noqa: E402
from engine.runner.messages import MoveUnitMessage                      # noqa: E402
from engine.runner.operations.triggers.loki.sanguinary_priest import (  # noqa: E402
    SELECTION_TYPE, sanguinary_priest_hp_to_heal, sanguinary_priest_max_hp_to_heal,
    sanguinary_priest_targets)
from engine.runner.runner import Runner                                 # noqa: E402
from engine.runner.snapshot import load_state                           # noqa: E402

PRIEST = "bloodSanguinary"
FRIENDS_SOFT = ("astraBullgryn", "bloodDeathCompany")      # NON mecaniques -> cibles du soin
FRIEND_MECH = "admecMarshall"                              # traits {Hero, Mechanical} -> EXCLU
ENEMIES = ("blackTerminator", "worldJakhal")

#: LES MUTANTS -- chacun DESARME un etage du port, et le probe doit alors ROUGIR. Un mutant qui
#: reste VERT dit que le temoin est AVEUGLE a cet etage, et il est nomme comme tel dans la sortie.
#: Ils sont appliques APRES la capture, sur le MEME etat et le MEME PRNG que le run de reference :
#: ce qui change est le PORT, jamais le montage.
MUTANTS = ("aucun", "tirage-hisse", "sans-mecanique", "borne-exclusive", "sans-scope-groupe")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _live_units(rpc, rid):
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u["squadId"]: u for u in (ob.get("units") or [])}


def _capture(rpc, rid, board):
    """Capture offline + CALAGE du PRNG sur l'etat MT live (`dumpRng`).

    `RandomAmount$$Calculate` CONSOMME le PRNG (`NextInternal(min, max + 1)`), une fois PAR CIBLE.
    Sans calage, `RandomAmount` retombe sur sa borne MIN (degradation documentee) et le port rendrait
    `hpToHeal` pour toutes les cibles -- juste par accident si le tirage tombait dessus."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (dv and ob and snap):
        return None
    state = load_state(dv, ob, snap, board=board)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if isinstance(s0, dict) and s0.get("mt"):
        from engine.runner.prng import IntBasedMersenneTwister
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state


def _build(seed, board: str, state_file: Path) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    hurt = ";".join("%s:RemainingHealth=1" % v for v in (FRIENDS_SOFT + (FRIEND_MECH,)))
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state_file),
            "--board", board,
            "--p-units", ",".join((PRIEST,) + FRIENDS_SOFT + (FRIEND_MECH,)),
            "--a-units", ",".join(ENEMIES),
            "--unit-stat", hurt]
    p = subprocess.run(argv, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if not state_file.exists():
        raise RuntimeError("build runner KO : " + ((p.stderr or p.stdout or "")[-500:]))
    return json.loads(state_file.read_text())["runnerId"]


def _free(board, units, tid) -> bool:
    occupied = {board.id_at(u["col"], u["row"]) for u in units.values()}
    return tid in board.by_id and board.walkable(tid) and tid not in occupied


def _rendezvous(board, units, priest_sq):
    """La tuile de RENDEZ-VOUS `T` : libre, marchable, a distance 1 du pretre, et portant le PLUS de
    voisins libres (on y amenera les trois allies). DEPLACER pour forcer la configuration -- jamais
    << bloque par la geometrie de spawn >* : le premier montage ne rendait qu'UNE cible adjacente,
    ce qui ne discrimine PAS le tirage par cible.

    Rend `(T, [voisins libres de T])` ou `(None, [])`."""
    here = board.id_at(units[priest_sq]["col"], units[priest_sq]["row"])
    best, best_ring = None, []
    for n in board.neighbours(here):
        if not _free(board, units, n):
            continue
        ring = [m for m in board.neighbours(n) if _free(board, units, m) and m != here]
        if len(ring) > len(best_ring):
            best, best_ring = n, ring
    return best, best_ring


def _move_live(rpc, rid, sq, board, tile) -> bool:
    """`applyAction move` LIVE + VERIFICATION de la position obtenue (un refus natif est SILENCIEUX :
    `AreTilesDisallowedAndLog` / hors portee -> retour nul). Rend True si l'unite y est."""
    col, row = board.coord(tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": sq, "to": {"col": col, "row": row}}}, 60)
    u = _live_units(rpc, rid).get(sq) or {}
    return u.get("col") == col and u.get("row") == row


def _appliquer_mutant(nom: str) -> str:
    """Desarme UN etage du port. Rend une description de ce qui a ete change."""
    if nom == "aucun":
        return "port intact"
    if nom == "tirage-hisse":
        # LA REGRESSION D'ORIGINE : `amount_fn` evalue UNE FOIS avant la boucle (ce que la feuille
        # `Heal` faisait avant #921), au lieu du `Calculate` PAR CIBLE de `HealBehaviour$$Execute`.
        from engine.dsl.base import _units_of
        from engine.dsl.effects import OperationResult
        from engine.runner.abilities.behaviours import stats as ST
        from engine.runner.operations.heal import HealUnitOperation

        def execute_hissee(self, entities, ectx):
            state = ectx.state
            amount = int((self.amount_fn(entities, ectx) if callable(self.amount_fn)
                          else self.amount_fn) or 0)
            heals = []
            if state is not None and amount > 0:
                src = (entities.caster or {}).get("id")
                for u in _units_of(self.targets_sel, entities):
                    tid = u.get("id") if isinstance(u, dict) else None
                    if tid is None:
                        continue
                    if self.guard is not None and not self.guard(entities, ectx, u):
                        continue
                    healed = HealUnitOperation.execute(state, src, tid, amount,
                                                       scope=self.scope,
                                                       remove_effects=self.remove_effects)
                    heals.append({"target": tid, "healed": healed, "amount": amount})
            ectx.emit("Heal", amount=amount, heals=heals)
            return OperationResult.ok()

        ST.Heal.execute = execute_hissee
        return "feuille `Heal` : amount_fn evalue UNE FOIS avant la boucle"
    if nom == "sans-mecanique":
        # Le filtre `MechanicalUnits` du selecteur natif est retire -> l'allie MECANIQUE entre dans
        # le set. Observable UNIQUEMENT par le DECALAGE DU PRNG : le gate
        # `AttackQuery$$EntityCanBeHealed` de l'Operation refuse quand meme le mecanique, mais son
        # tirage, lui, a deja ete consomme.
        from engine.runner.operations.triggers.loki import sanguinary_priest as SP
        SP.sanguinary_priest_targets = (
            lambda: AdjacentFriends(Owner(), Const(1), Owner(), selection_type=SELECTION_TYPE))
        return "selecteur : `op_Subtraction MechanicalUnits(.)` retire"
    if nom == "borne-exclusive":
        # `RandomAmount$$Calculate` = `NextInternal(min, max + 1)` : le `+1` est LU au decompile.
        from engine.entities import formulas as F
        F.RandomAmount.calculate = (
            lambda self, ctx: (int(self.min_node.evaluate(ctx)) if self.rng is None
                               else self.rng.next_internal(int(self.min_node.evaluate(ctx)),
                                                           int(self.max_node.evaluate(ctx)))))
        return "`RandomAmount` : borne haute EXCLUSIVE (le `+ 1` natif retire)"
    if nom == "sans-scope-groupe":
        # `HealBehaviourOptions$$ForRegenerate` = `(scope 1, removeEffects 0)`. `scope 0` desarme le
        # cap de GROUPE `GetGroupUnitHealLimit` de `PredictHeal`.
        from engine.runner.operations.triggers.loki import sanguinary_priest as SP
        SP.HEAL_SCOPE = 0
        return "options : `scope` 1 -> 0 (cap de groupe desarme)"
    raise SystemExit("mutant inconnu : %s" % nom)


def run(board_id: str = "MC1_67", seed=777, state_file=None, mutant: str = "aucun",
        rpc=None) -> dict:
    """Monte le scenario, mesure les six etages, DISPOSE le runner, rend le dict de mesure.

    `rpc` = appel RPC deballe (fourni par pytest via la fixture de session) ; absent, on resout la
    session par `rl_collect_batch`. `err` non nul = MONTAGE KO (jamais un verdict sur le port)."""
    if rpc is None:
        import rl_collect_batch as R          # meme voie host que le conftest (import PARESSEUX)
        sid = R._resolve_session()

        def rpc(method, body=None, timeout=90):                       # noqa: F811
            return _unwrap(R._rpc(sid, method, [body] if body is not None else [],
                                  timeout=timeout))

    sf = Path(state_file or (ROOT / "logs" /
                             ("state-921-sanguinary-%d.json" % os.getpid())))
    out: dict = {"err": None, "board": board_id, "seed": seed, "mutant": mutant}
    rid = _build(seed, board_id, sf)
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (bg and bg.get("tiles")):
            out["err"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")

        U = _live_units(rpc, rid)
        vis2sq: dict = {}
        for sq, u in U.items():
            vis2sq.setdefault(u.get("visualId"), sq)
        missing = [v for v in (PRIEST,) + FRIENDS_SOFT + (FRIEND_MECH,) if v not in vis2sq]
        if missing:
            out["err"] = "absent(s) du live : %s" % missing
            return out
        sq_p = vis2sq[PRIEST]
        soft_sq = [vis2sq[v] for v in FRIENDS_SOFT]
        sq_m = vis2sq[FRIEND_MECH]
        enemy_sq = [sq for sq, u in U.items() if u.get("visualId") in ENEMIES]

        dest, ring = _rendezvous(board, U, sq_p)
        if dest is None:
            out["err"] = "aucune tuile libre adjacente au pretre"
            return out
        dcol, drow = board.coord(dest)

        # --- E0/E5 MONTAGE : on AMENE les trois allies autour de `dest` (moves LIVE, verifies) ----
        # E5 en passant : leurs PROPRES moves ne doivent soigner personne (`get_OwnerIsActor`).
        hp_avant_montage = {sq: U[sq]["hp"] for sq in soft_sq + [sq_m]}
        placed = []
        for v in FRIENDS_SOFT + (FRIEND_MECH,):
            sq = vis2sq[v]
            U = _live_units(rpc, rid)
            if board.id_at(U[sq]["col"], U[sq]["row"]) in board.neighbours(dest):
                placed.append((v, "deja adjacent"))
                continue
            libres = [t for t in board.neighbours(dest) if _free(board, U, t)]
            ok = next((t for t in libres if _move_live(rpc, rid, sq, board, t)), None)
            placed.append((v, ("-> (%d,%d)" % board.coord(ok)) if ok is not None
                           else "NON DEPLACE"))
        U = _live_units(rpc, rid)
        out["placements"] = placed
        out["rendezvous"] = (dcol, drow)
        out["ring_libre"] = len(ring)
        out["owner_is_actor_deltas"] = {v: U[vis2sq[v]]["hp"] - hp_avant_montage[vis2sq[v]]
                                        for v in FRIENDS_SOFT + (FRIEND_MECH,)}
        if not _free(board, U, dest):
            out["err"] = "la tuile de rendez-vous a ete OCCUPEE par le montage"
            return out

        # --- capture PRE-move (l'etat COMMUN aux deux cotes) --------------------------------------
        state = _capture(rpc, rid, board)
        if state is None:
            out["err"] = "capture pre-move KO"
            return out
        pid = _by_vis(state, PRIEST)
        soft_ids = [_by_vis(state, v) for v in FRIENDS_SOFT]
        mech_id = _by_vis(state, FRIEND_MECH)
        if pid is None or any(i is None for i in soft_ids) or mech_id is None:
            out["err"] = "roster incomplet offline"
            return out

        # --- E1 CONFIG -----------------------------------------------------------------------------
        ctx = state.get_entity(pid).get_component(StatsComponent).ctx
        out["passive_level"] = getattr(ctx, "passive_ability_level", None)
        out["multiplier"] = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        lo = sanguinary_priest_hp_to_heal(state, pid)
        hi = sanguinary_priest_max_hp_to_heal(state, pid)
        out["lo"], out["hi"] = lo, hi

        # --- MUTANT (applique APRES la capture : montage identique au run de reference) -----------
        out["mutant_quoi"] = _appliquer_mutant(mutant)

        # --- E3 MOVE SEUL : le PORT d'abord (etat commun), puis le LIVE ---------------------------
        hp_pre_off = {i: int(state.get_entity(i).get_component(HealthComponent).hp)
                      for i in soft_ids + [mech_id]}
        runner = Runner(state).install_default_handlers(20)
        runner.apply(MoveUnitMessage(unit_id=pid, to=(dcol, drow)))
        off_delta = {i: int(state.get_entity(i).get_component(HealthComponent).hp) - hp_pre_off[i]
                     for i in soft_ids + [mech_id]}

        # --- E2 SELECTEUR, etage par etage, sur l'etat POST-move du port --------------------------
        ents = entities_from_state(state, pid, None, actor_id=pid)
        out["sel_adj"] = [u.get("id") for u in
                          AdjacentFriends(Owner(), Const(1), Owner(),
                                          selection_type=SELECTION_TYPE).select(ents)]
        out["sel_mech"] = [u.get("id") for u in
                           MechanicalUnits(AdjacentFriends(Owner(), Const(1), Owner(),
                                                           selection_type=SELECTION_TYPE),
                                           SELECTION_TYPE).select(ents)]
        out["sel_targets"] = [u.get("id") for u in sanguinary_priest_targets().select(ents)]
        out["ids"] = {"pretre": pid, "doux": soft_ids, "meca": mech_id}

        live_pre = {sq: U[sq]["hp"] for sq in soft_sq + [sq_m] + enemy_sq}
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": sq_p, "to": {"col": dcol, "row": drow}}}, 60)
        U2 = _live_units(rpc, rid)
        live_delta = {sq: U2[sq]["hp"] - live_pre[sq] for sq in live_pre}

        out["delta_live"] = {v: live_delta[sq] for v, sq in zip(FRIENDS_SOFT, soft_sq)}
        out["delta_port"] = {v: off_delta[i] for v, i in zip(FRIENDS_SOFT, soft_ids)}
        out["delta_live"][FRIEND_MECH] = live_delta[sq_m]
        out["delta_port"][FRIEND_MECH] = off_delta[mech_id]
        out["delta_live_ennemis"] = {U2[sq].get("visualId"): live_delta[sq] for sq in enemy_sq}
        out["accord"] = out["delta_live"] == out["delta_port"]
        soignes = [live_delta[sq] for sq in soft_sq if live_delta[sq] > 0]
        out["n_soignes"] = len(soignes)
        out["temoin_natif_non_nul"] = bool(soignes)
        out["montants_dans_la_plage"] = all(lo <= m <= hi for m in soignes)
        out["montants_natifs"] = [live_delta[sq] for sq in soft_sq]
        out["montants_distincts"] = len(set(out["montants_natifs"])) > 1

        # --- E4 CONTROLE : 2e move dans le MEME tour ----------------------------------------------
        occupied2 = {board.id_at(u["col"], u["row"]) for u in U2.values()}
        here2 = board.id_at(U2[sq_p]["col"], U2[sq_p]["row"])
        dest2 = next((n for n in board.neighbours(here2)
                      if n in board.by_id and n not in occupied2 and board.walkable(n)), None)
        if dest2 is None:
            out["controle"] = None                       # non joue (aucune 2e tuile libre)
        else:
            d2c, d2r = board.coord(dest2)
            pre2_off = {i: int(state.get_entity(i).get_component(HealthComponent).hp)
                        for i in soft_ids}
            runner.apply(MoveUnitMessage(unit_id=pid, to=(d2c, d2r)))
            off2 = [int(state.get_entity(i).get_component(HealthComponent).hp) - pre2_off[i]
                    for i in soft_ids]
            pre2_live = {sq: _live_units(rpc, rid)[sq]["hp"] for sq in soft_sq}
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": sq_p, "to": {"col": d2c, "row": d2r}}}, 60)
            U3 = _live_units(rpc, rid)
            live2 = [U3[sq]["hp"] - pre2_live[sq] for sq in soft_sq]
            out["controle"] = {"live": live2, "port": off2}
    finally:
        try:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(sf)],
                           cwd=str(HERE), capture_output=True, text=True, timeout=120)
        except Exception:
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--mutant", default="aucun", choices=MUTANTS,
                    help="desarme un etage du PORT apres la capture -- le probe doit alors ROUGIR")
    ap.add_argument("--state-file", default=None)
    args = ap.parse_args()

    m = run(board_id=args.board, seed=args.seed, state_file=args.state_file, mutant=args.mutant)
    print("[921] runner=%s board=%s seed=%s" % (m.get("rid"), args.board, args.seed))
    if m.get("err"):
        print("[921] MONTAGE KO : %s" % m["err"])
        return 2
    print("[921] rendez-vous en (%d,%d) ; %d voisin(s) libre(s) au depart"
          % (m["rendezvous"][0], m["rendezvous"][1], m["ring_libre"]))
    for v, how in m["placements"]:
        print("      %-20s %s" % (v, how))
    print("\n[E1 CONFIG] passive_ability_level=%s multiplier=%d%% hpToHeal=%d maxHpToHeal=%d"
          % (m["passive_level"], m["multiplier"], m["lo"], m["hi"]))
    print("\n[MUTANT] %s -- %s" % (args.mutant, m["mutant_quoi"]))
    print("\n[E2 SELECTEUR] POST-move (port)   ids: pretre=%s doux=%s meca=%s"
          % (m["ids"]["pretre"], m["ids"]["doux"], m["ids"]["meca"]))
    print("  AdjacentFriends(Owner,1,3)   = %s" % m["sel_adj"])
    print("  MechanicalUnits(., 3)        = %s" % m["sel_mech"])
    print("  adj op_Subtraction mech      = %s" % m["sel_targets"])
    print("\n[E5 OWNER-IS-ACTOR] deltas PV pendant les moves des ALLIES (attendu 0 partout) : %s"
          % m["owner_is_actor_deltas"])
    print("\n[E3 MOVE SEUL] delta PV -- live vs port, PAR CIBLE (plage attendue [%d, %d])"
          % (m["lo"], m["hi"]))
    rc = 0
    for v in FRIENDS_SOFT + (FRIEND_MECH,):
        l, o = m["delta_live"][v], m["delta_port"][v]
        note = "  (MECANIQUE : attendu 0 des deux cotes)" if v == FRIEND_MECH else ""
        print("  %-5s %-20s live=%-6d port=%-6d ecart=%d%s"
              % ("OK" if l == o else "ROUGE", v, l, o, l - o, note))
        if l != o:
            rc = 1
    if m["delta_live"][FRIEND_MECH] or m["delta_port"][FRIEND_MECH]:
        print("      ROUGE : l'allie MECANIQUE a ete soigne")
        rc = 1
    for v, d in (m["delta_live_ennemis"] or {}).items():
        if d > 0:
            print("      ROUGE : l'ennemi %s a ete SOIGNE (%d)" % (v, d))
            rc = 1
    if not m["montants_dans_la_plage"]:
        print("      ROUGE : un montant natif sort de [%d, %d] -> %s"
              % (m["lo"], m["hi"], m["montants_natifs"]))
        rc = 1
    if any(d != 0 for d in (m["owner_is_actor_deltas"] or {}).values()):
        print("      ROUGE : un allie a ete soigne par SON PROPRE move (get_OwnerIsActor)")
        rc = 1
    if not m["temoin_natif_non_nul"]:
        print("\n[921] TEMOIN VIDE : aucune cible soignee cote natif -- l'accord ne prouve RIEN.")
        rc = 2
    else:
        print("\n[E3b TIRAGE PAR CIBLE] montants natifs = %s -> %s"
              % (m["montants_natifs"],
                 "DISTINCTS (le tirage est par cible)" if m["montants_distincts"]
                 else "EGAUX sur ce tirage (non discriminant a lui seul)"))
    if m.get("controle") is None:
        print("\n[E4 CONTROLE] pas de 2e tuile libre adjacente -- controle non joue")
    else:
        c = m["controle"]
        ok = all(v == 0 for v in c["live"]) and all(v == 0 for v in c["port"])
        print("\n[E4 CONTROLE] 2e move MEME tour : live=%s port=%s (attendu 0 partout) -> %s"
              % (c["live"], c["port"], "OK" if ok else "ROUGE"))
        if not ok:
            rc = 1

    if args.mutant != "aucun":
        # INVERSION DELIBEREE : un mutant qui laisse le probe VERT dit que le temoin est AVEUGLE a
        # l'etage desarme. On le NOMME, et on rend rc=1 pour que la passe le voie.
        print("\n[921] MUTANT %s : %s"
              % (args.mutant, "TUE (le temoin voit cet etage)" if rc
                 else "SURVIVANT -- LE TEMOIN EST AVEUGLE A CET ETAGE"))
        return 0 if rc else 1
    print("\n[921] rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
