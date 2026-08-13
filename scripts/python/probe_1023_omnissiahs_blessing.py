"""#1023 LIVE -- `OmnissiahsBlessing` (passif 0x513 = 1299) confronte au natif.

LE PROBLEME DE PORTEUR, ET SA SOLUTION (a lire avant de toucher au montage)
==========================================================================
Les DEUX porteurs du passif sont hors pool : `admecNpc2Techpriest` (npc) et `admecSmnTechpriest`
(SUMMON dont l'unique invocateur est `InvocationOfMachineVengeance`, portee par le seul
`admecBossBelisarius`, npc). Et les TROIS seules sources de l'effet transfere -- `1365
MachineVengeance` -- sont elles aussi sur Belisarius (`ArcScourge`, `ShroudPsalm`) ou sur le
Tech-Priest lui-meme (`VengeanceForTheOmnissiah`, non porte).

Le montage GREFFE donc sur `admecManipulus` (HERO du pool, trait `Mechanic` donc REPARATEUR) :

  * `PassiveAbilities += 1299 OmnissiahsBlessing` -- le passif confronte. Sa condition de greffe
    est VERIFIEE, pas supposee : sa config gameconfig n'a **aucune variable ni constante**, et son
    `CreateTrigger`/`CreateBehaviour` ne lisent ni stat, ni trait, ni arme du caster (les seuls
    canaux sont `HasEffect(Owner, 0x555)` et les selecteurs `Owner`/`Target`).
  * `ActiveAbilities = [1173 ArcScourge]` -- le VECTEUR DE POSE de la pile, et il est choisi parce
    qu'il est **porte des deux cotes** (`ABILITY_CLASSES[1173]`, `runner/abilities/admec.py`) :
    `ShroudPsalm`, l'autre poseur, ne l'est pas, et il exclut de toute facon le caster de ses
    cibles. `ArcScourge` pose la pile SUR SON CASTER (`If(HasEffect(Caster, 0x555),
    IncreaseEffectLevel(pd), AddEffect(0x555, level = pd))`).
  * `1199 GalvanicField` est CONSERVE : c'est lui qui accorde `1119 Repair_GalvanicField` au
    Manipulus (`AddActiveAbility(Owner, 0x45f)`), donc sa REPARATION -- l'evenement `On(0x30 =
    UnitRepaired)` dont depend tout le passif confronte.

CE QUE LA GREFFE NE COUVRE PAS, et il faut le lire comme une limite : les stats, traits et armes du
VRAI porteur. Aucune des deux faces d'`OmnissiahsBlessing` ne les lit -- c'est precisement la
condition qui rend la greffe legitime (`docs/rl/case-92-catalog-injection.md` §5bis).

LE MONTAGE, PAS A PAS
=====================
  1. `admecManipulus` caste `ArcScourge` sur l'ennemi -> `MachineVengeance` niveau N sur LUI.
  2. CAPTURE (`decisionView` + `observeBattle` + `combatSnapshot` + `unitAbilityStates`).
  3. NATIF : `admecManipulus` repare l'allie MECANIQUE blesse (ability 1119) -> on relit les deux
     piles.
  4. PORT : depuis la MEME capture, on rejoue le vecteur `On(0x30 = UnitRepaired)` et on compare.
     Contre-bras `ability_states=False` : le canal de greffe est MUET, le passif n'est pas monte --
     le port ne doit alors RIEN faire.

⚠ L'allie est BLESSE a dessein : `IdunBattle.Operations.RepairUnitOperation$$Execute` sort par
`if (repaired < 1 && cleansed < 1 && !HasFlag(target, 0x18)) return {}` AVANT d'emettre
`On(0x30)`. Une cible a PV pleins ne produirait donc aucun evenement -- le flag `0x18` teste la est
celui de la CIBLE, pas celui du caster.

Reproduire (depuis scripts/python, session Frida chaude) :

    python probe_1023_omnissiahs_blessing.py

Sorties dans `logs/` (jamais `data/`). ASCII only (cp1252). Discipline runner : `--state-file`
absolu, UN runner, dispose en sortie.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]
sys.path.insert(0, str(_PYDIR))

CARRIER = "admecManipulus"          # HERO du pool, trait `Mechanic` -> il REPARE
ALLY = "admecDestroyer"             # allie MECANIQUE reparable, du pool
FOE = "necroWarden"                 # cible d'`ArcScourge` (`TargetIsEnemy`, range 2)

OMNISSIAHS_BLESSING_ID = 1299       # 0x513 `TriggeredAbilityType.OmnissiahsBlessing`
GALVANIC_FIELD_ID = 1199            # 0x4af, CONSERVE : c'est lui qui accorde 1119
ARC_SCOURGE_ID = 1173               # 0x495 `ActiveAbilityType.ArcScourge`
REPAIR_GALVANIC_ID = 1119           # 0x45f, l'ability de reparation accordee par 1199
MACHINE_VENGEANCE = 1365            # 0x555 `EffectType.MachineVengeance`

BOARD = "MC1_67"
SEED = "777"
ALLY_MAX_HP = 900000
ALLY_START_HP = 1000


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _out_dir() -> Path:
    p = _ROOT / "logs" / ("probe_1023-%d" % os.getpid())
    p.mkdir(parents=True, exist_ok=True)
    return p


def seed_bc_path() -> Path:
    """Seed BC ou `admecManipulus` porte la greffe.

    ⚠ LA CONFIG D'`ArcScourge` DOIT ETRE INJECTEE EXPLICITEMENT, et c'est MESURE : le
    rafraichissement d'`BC.Abilities` de `rl_duel._load_seed_bc` (`refresh_ability_configs`) MET A
    JOUR les entrees PRESENTES, il n'en CREE pas -- `ArcScourge` est absente de la capture (seul
    `admecBossBelisarius` la porte, et il n'est pas au catalogue). Sans cette injection, le cast
    revient en `{"ok": false, "error": "system error"}`, MEME VERROU que #226/#237 : le natif lit
    la config a la construction du behaviour et LEVE sur cle absente."""
    import catalog_inject as CI
    bc = CI._load_seed(None)
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == CARRIER]
    if not hits:
        raise KeyError("%s absent de BC.Units" % CARRIER)
    node = bc.setdefault("Abilities", {}).setdefault("ActiveAbilities", {})
    if "ArcScourge" not in node:
        node["ArcScourge"] = CI.synthesize_ability("ArcScourge")
    for u in hits:
        pas = [int(p) for p in (u.get("PassiveAbilities") or [])]
        if OMNISSIAHS_BLESSING_ID not in pas:
            pas.append(OMNISSIAHS_BLESSING_ID)
        u["PassiveAbilities"] = pas
        u["ActiveAbilities"] = [ARC_SCOURGE_ID]
    CI.declare_graft("passive", CARRIER, "OmnissiahsBlessing (%d)" % OMNISSIAHS_BLESSING_ID)
    CI.declare_graft("active", CARRIER, "ArcScourge (%d) -- vecteur de pose de 1365"
                     % ARC_SCOURGE_ID)
    import host_inputs
    p = host_inputs.reject_data_output(_out_dir() / "seed-bc-1023.json", "probe_1023")
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(bc), encoding="utf-8")
    return Path(p)


def build_args(seed_bc: Path) -> list[str]:
    return ["--board", BOARD, "--seed-bc", str(seed_bc), "--no-ai",
            "--p-units", "%s,%s" % (CARRIER, ALLY), "--a-units", FOE,
            "--dmg-target", "1",
            # L'allie DOIT etre blesse : sans manque, `RepairUnitOperation$$Execute` sort avant
            # d'emettre `On(0x30 = UnitRepaired)` -- cf. l'en-tete.
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (ALLY, ALLY_MAX_HP, ALLY_START_HP)]


def _build_subprocess(argv_extra: list[str]) -> tuple[int, Path]:
    state = _out_dir() / "runner.json"
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *argv_extra]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-1200:]))
    return json.loads(state.read_text())["runnerId"], state


def _live_units(rpc, rid: int) -> dict:
    return {u["squadId"]: u
            for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
            if not u.get("isDead")}


def _move_to(rpc, rid, sq, tile, board):
    c, r = board.coord(tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": sq, "to": {"col": c, "row": r}}}, 60)


def _drive_adjacent(rpc, rid, board, sq_mover, anchor_tile) -> bool:
    """DEPLACE `sq_mover` sur une tuile LIBRE adjacente a `anchor_tile`. On CONDUIT les positions --
    la geometrie de spawn n'est jamais une raison de ne pas mesurer."""
    U = _live_units(rpc, rid)
    mt = board.id_at(U[sq_mover]["col"], U[sq_mover]["row"])
    if mt is not None and mt in board.neighbours(anchor_tile):
        return True
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    cands = [n for n in board.neighbours(anchor_tile)
             if n in board.by_id and board.walkable(n) and n not in occ]
    cands.sort(key=lambda n: abs(board.coord(n)[0] - U[sq_mover]["col"])
               + abs(board.coord(n)[1] - U[sq_mover]["row"]))
    for n in cands:
        _move_to(rpc, rid, sq_mover, n, board)
        U2 = _live_units(rpc, rid)
        if sq_mover not in U2:
            return False
        m2 = board.id_at(U2[sq_mover]["col"], U2[sq_mover]["row"])
        if m2 is not None and m2 in board.neighbours(anchor_tile):
            return True
    return False


def _mv_levels(rpc, rid: int) -> dict:
    """`{visualId: niveau CUMULE de 1365}` -- LU sur `decisionView.units[].effects`, le canal qui
    porte le `level` d'une instance. Une unite sans instance n'a PAS de cle : c'est une MESURE
    (« aucune pile »), a distinguer d'un zero. Somme des instances non `removed`, comme le fait
    `EffectLevelFormula$$Calculate`."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90) or {}
    out: dict = {}
    for u in (dv.get("units") or []):
        vis = u.get("visualId")
        for e in (u.get("effects") or []):
            if int(e.get("effectType") or -1) != MACHINE_VENGEANCE or e.get("removed"):
                continue
            out[vis] = out.get(vis, 0) + int(e.get("level") or 0)
    return out


def _ability_ids(dv, sq) -> list:
    """`decisionView.units[].abilities` : `id` + `kind` (`normal` / `active` / `granted`).
    `granted` = accordee par un passif -- c'est sous ce `kind` que `1119 Repair_GalvanicField`
    arrive, via `GalvanicFieldAbility$$CreateBehaviour`."""
    for u in (dv.get("units") or []):
        if u.get("id") == sq:
            return [{"id": a.get("id"), "kind": a.get("kind")}
                    for a in (u.get("abilities") or [])]
    return []


def _by_vis(state, vis):
    from engine.runner.components import StatsComponent
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _port_replay(dv, ob, snap, board, ability_states) -> dict:
    """Rejoue `On(0x30 = UnitRepaired)` OFFLINE sur la capture (`caster = le Manipulus`,
    `target = l'allie`), et rend les niveaux de 1365 AVANT / APRES.

    `ability_states=False` = le canal de greffe REFUSE -> `collect_triggered_abilities` retombe sur
    le kit gameconfig d'`admecManipulus`, qui ne contient PAS `OmnissiahsBlessing` : c'est le
    contre-bras SANS RAIL."""
    from engine.runner.operations.triggers.dispatch.repair import unit_repaired_triggers
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board, ability_states=ability_states)
    car, ally = _by_vis(state, CARRIER), _by_vis(state, ALLY)
    if car is None or ally is None:
        return {"error": "unites absentes offline (%s/%s)" % (car, ally)}

    def lvl(uid):
        if state.effects is None:
            return 0
        return sum(int(getattr(e, "level", 0) or 0)
                   for e in state.effects.by_unit.get(int(uid), [])
                   if not getattr(e, "consumed", False)
                   and int(getattr(e, "effect_type", -1)) == MACHINE_VENGEANCE)

    before = {"carrier": lvl(car), "ally": lvl(ally)}
    out = unit_repaired_triggers(state, car, ally) or []
    ev = [e for e in out if isinstance(e, dict) and e.get("passive") == "OmnissiahsBlessing"]
    return {"before": before, "after": {"carrier": lvl(car), "ally": lvl(ally)},
            "fired": len(ev), "event": (ev[0] if ev else None)}


def _wait_turn_of(rpc, rid, sq_unit, tours: int = 6) -> bool:
    """Passe les tours jusqu'a ce que `sq_unit` puisse agir. `ArcScourge` TERMINE le tour de son
    caster (`AddFlagsAfterAbilityExecution`), donc un second cast exige un tour de plus -- et c'est
    aussi ce qui espace la reparation du dernier cast."""
    for _ in range(int(tours)):
        dvn = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90) or {}
        # `toActivate` est une liste d'IDS d'unite (les `squadId` du live), pas d'objets.
        if int(sq_unit) in {int(x) for x in (dvn.get("toActivate") or []) if x is not None}:
            return True
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return False


def run(rpc, keep: bool = False, chain: int = 2) -> dict:
    from engine.entities.pathfinding.board import Board
    out: dict = {"ok": False, "why": None, "chain": int(chain)}
    sbc = seed_bc_path()
    rid, _state = _build_subprocess(build_args(sbc))
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            out["why"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")
        U = _live_units(rpc, rid)
        sq = {u.get("visualId"): s for s, u in U.items()}
        for vis in (CARRIER, ALLY, FOE):
            if vis not in sq:
                out["why"] = "%s absent du live (%s)" % (vis, sorted(sq))
                return out

        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        out["carrier_abilities"] = _ability_ids(dv0, sq[CARRIER])
        ids = {a.get("id") for a in out["carrier_abilities"]}
        if ARC_SCOURGE_ID not in ids:
            out["why"] = ("la greffe d'`ArcScourge` (%d) n'a pas pris : %s"
                          % (ARC_SCOURGE_ID, out["carrier_abilities"]))
            return out

        # --- 1. POSE de la pile : UN cast d'`ArcScourge`, `chain` maillons -----------------------
        # LE NIVEAU POSE = le NOMBRE DE MAILLONS de la chaine (`AddPersistentData(+1)` par maillon,
        # converti en fin de cast par `If(HasEffect, IncreaseEffectLevel(pd), AddEffect(level=pd))`).
        # Pour obtenir 2, on met l'ALLIE MECANIQUE au contact de l'ennemi : le selecteur de saut
        # d'`ArcScourge` PRIORISE les unites `Mechanical` adjacentes, ALLIES COMPRIS
        # (`UnitsWithTrait(sans, 5 Mechanical, 3).Otherwise(Enemies(...))`), et sur un allie la
        # branche ne fait qu'incrementer le compteur -- aucun degat.
        # ⚠ RE-CASTER ne marche PAS, et c'est MESURE : le 2e cast rend `ok: true` avec DEUX events
        # et n'incremente RIEN (l'ennemi n'est plus une cible valide apres le premier).
        if chain > 1:
            ft0 = board.id_at(U[sq[FOE]]["col"], U[sq[FOE]]["row"])
            out["ally_au_contact"] = _drive_adjacent(rpc, rid, board, sq[ALLY], ft0)
            if not out["ally_au_contact"]:
                out["why"] = ("%s ne peut pas atteindre le contact de %s -- la chaine resterait a "
                              "UN maillon, et le montage ne separerait plus << transfere TOUT >> "
                              "de << transfere 1 >>" % (ALLY, FOE))
                return out
            if not _wait_turn_of(rpc, rid, sq[CARRIER]):
                out["why"] = "%s n'a pas retrouve son tour apres le placement de l'allie" % CARRIER
                return out
        U = _live_units(rpc, rid)
        if sq[FOE] not in U or sq[CARRIER] not in U:
            out["why"] = "une unite du volet ArcScourge a disparu avant le cast"
            return out
        ft = board.id_at(U[sq[FOE]]["col"], U[sq[FOE]]["row"])
        if not _drive_adjacent(rpc, rid, board, sq[CARRIER], ft):
            out["why"] = "%s ne peut pas atteindre le contact de %s" % (CARRIER, FOE)
            return out
        out["arc"] = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sq[CARRIER], "targetId": sq[FOE],
            "abilityType": ARC_SCOURGE_ID}}, 120)
        out["mv_apres_arc"] = _mv_levels(rpc, rid)
        n = int(out["mv_apres_arc"].get(CARRIER, 0))
        if n <= 0:
            out["why"] = ("`ArcScourge` n'a pose AUCUN niveau de 1365 sur %s : %s -- le montage ne "
                          "separe alors RIEN (temoin NUL)" % (CARRIER, out["mv_apres_arc"]))
            return out
        out["niveau_pose"] = n

        # --- 2. CAPTURE, avant la reparation -----------------------------------------------------
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60)
        out["port"] = _port_replay(dv, ob, snap, board, uas)
        out["port_sans_rail"] = _port_replay(dv, ob, snap, board, False)

        # --- 3. NATIF : la reparation ------------------------------------------------------------
        # `ArcScourge` a termine le tour du caster -> on passe au tour suivant avant de reparer.
        if not _wait_turn_of(rpc, rid, sq[CARRIER]):
            out["why"] = "%s n'a pas retrouve son tour pour la reparation" % CARRIER
            return out
        U = _live_units(rpc, rid)
        if sq[CARRIER] not in U or sq[ALLY] not in U:
            out["why"] = "une des deux unites a disparu du live avant la reparation"
            return out
        at = board.id_at(U[sq[ALLY]]["col"], U[sq[ALLY]]["row"])
        if not _drive_adjacent(rpc, rid, board, sq[CARRIER], at):
            out["why"] = "%s ne peut pas atteindre le contact de %s" % (CARRIER, ALLY)
            return out
        out["mv_avant_repair"] = _mv_levels(rpc, rid)
        out["repair"] = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sq[CARRIER], "targetId": sq[ALLY],
            "abilityType": REPAIR_GALVANIC_ID}}, 120)
        out["mv_apres_repair"] = _mv_levels(rpc, rid)
        out["ok"] = True
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="#1023 -- OmnissiahsBlessing, confrontation live")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--chain", type=int, default=2,
                    help="nombre de MAILLONS vise pour la chaine d'`ArcScourge` = le niveau de la "
                         "pile posee. `2` (defaut) met l'allie MECANIQUE au contact de l'ennemi et "
                         "SEPARE << transfere TOUT >> de << transfere 1 >> ; `1` ne separe rien.")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, keep=a.keep, chain=a.chain)
    print("runner=%s chain=%s ok=%s why=%s"
          % (r.get("rid"), r.get("chain"), r.get("ok"), r.get("why")))
    print("abilities du porteur greffe : %s" % (r.get("carrier_abilities"),))
    if not r.get("ok"):
        (_out_dir() / "resultat.json").write_text(json.dumps(r, indent=1, default=str),
                                                  encoding="utf-8")
        return 1
    print("[NATIF]  1365 apres ArcScourge   = %s   (niveau pose = %s)"
          % (r.get("mv_apres_arc"), r.get("niveau_pose")))
    print("[NATIF]  1365 avant reparation   = %s" % (r.get("mv_avant_repair"),))
    print("[NATIF]  1365 apres reparation   = %s" % (r.get("mv_apres_repair"),))
    print("[PORT]   %s" % (r.get("port"),))
    print("[PORT sans rail] %s" % (r.get("port_sans_rail"),))
    (_out_dir() / "resultat.json").write_text(json.dumps(r, indent=1, default=str),
                                              encoding="utf-8")
    print("[out] %s" % (_out_dir() / "resultat.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
