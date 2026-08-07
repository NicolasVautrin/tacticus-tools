"""probe #498-r3 -- LIVE : la tete `IsDisplaceable` d'`DisplaceUnitOperation$$Execute` s'applique
AUSSI au case 5 (`SwitchPosition`).

LE CRITERE, AVANT LA METHODE

Existe-t-il un etat de jeu ou le natif REFUSE un deplacement que le port AUTORISE ? Oui, et c'est
le site que le constat d'origine n'avait pas vu : `SwitchPositionOperation` ne portait AUCUNE des
quatre conditions d'`IdunBattle.Entities.UnitExtensions$$IsDisplaceable`, alors que la tete
d'`IdunBattle.Operations.DisplaceUnitOperation$$Execute` s'execute AVANT le `switch(direction)`.

    uVar4 = IdunBattle_Entities_UnitExtensions__IsDisplaceable(target);
    if ((char)uVar4 == '\0') { return uVar4; }          // <- AVANT le switch, donc case 5 compris
    ...
    case 5: return DisplaceUnitOperation__SwitchPosition(this, caster, target, options);

LE MONTAGE, et pourquoi il EXERCE la condition au lieu de la contourner

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SorcerousFacade_SwitchAbility$$CreateBehaviour`
= `SwitchPosition(Caster@0x48, Target@0x60)` -> `DisplaceUnitBehaviour(direction = 5,
displacingUnit = Caster, displacedUnit = Target)`, donc `target` (le gate) = l'ALLIE vise par le
cast de 1100. Le port COLLAPSE le `TriggerAbilityDelayed` inline : le switch a lieu DANS le cast,
live comme offline (mesure #287) -- l'observable est donc immediat.

L'allie du montage #287 (`thousSorcerer`) ne porte AUCUN des trois traits refusants. On lui AJOUTE
`BigTarget` dans `BC.Units[].Traits` (seed BC custom, `--seed-bc`) : c'est le canal que
`snapshot._load_unit_traits` lit, et le seul qui rende un trait EFFECTIF cote natif. Sans cette
ecriture, la condition ne mordrait sur aucune configuration atteignable de ce montage -- un accord
en regime ou la condition est trivialement satisfaite ne prouve RIEN.

TROIS BRAS, et leur role :
  * `base`  -- allie NORMAL. TEMOIN NON DEGENERE : le switch DOIT avoir lieu, sinon le bras `big`
                ne mesure rien (un refus systematique passerait pour un gate qui marche).
  * `big`   -- allie `BigTarget`. Le natif ne doit PAS echanger.
  * A/B     -- le MEME etat pre-cast rejoue OFFLINE deux fois : avec le port courant, puis avec le
                foyer MUTE (`unit_extensions_is_displaceable -> True`), qui reproduit exactement
                l'etat d'avant #498-r3. Le mutant DOIT echanger. C'est ce qui interdit d'attribuer
                l'accord du bras `big` a autre chose que ce gate.

Usage :
    python probe_498r3_switch_position_gate.py [--keep]
ASCII only ; exit 0 = tout conforme.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_custom_utility_inventory as INV
import probe_287_facade_combat as P287
from engine.entities.pathfinding.board import Board
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.snapshot import load_state

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs"
SEED_BC = ROOT / "data" / "seed-bc.json"

BOARD = "MC1_67"
SEED = 49831
FACADE = 1100
CASTER_VID = P287.CASTER_VID          # thousTzaangor (Yazaghor)
ALLY_VID = P287.ALLY_VID              # thousSorcerer (allie Psyker)
FOE_VID = P287.FOE_VID
FAR_VID = P287.FAR_VID
P_UNITS = P287.P_UNITS
A_UNITS = P287.A_UNITS

# Le trait AJOUTE a l'allie. `BigTarget` = `0x3f9` = 1017 dans
# `data/symbols/<build>/frida/enums.tsv`, enum `IdunBattle.Entities.Enum.UnitTrait` -- le 3e des
# trois `BaseUnitComponent$$HasTrait` d'`IsDisplaceable`. Choisi parce que c'est le SEUL des trois
# qui ait des porteurs mesures (13 unites du seed BC ; `Immovable` et `Hulking` en ont ZERO).
TRAIT_AJOUTE = UnitTrait.BigTarget.name
TRAIT_ID = int(UnitTrait.BigTarget)                # 0x3f9 = 1017


def _rpc(method, args=None, timeout=90000):
    return INV.rpc(INV._session_id(), method, args, timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def write_seed_bc_with_trait(out_path: Path, unit_id: str, trait: str) -> dict:
    """Seed BC custom : `trait` AJOUTE a `BC.Units[<unit_id>].Traits`. C'est la source que
    `snapshot._load_unit_traits` lit, et elle differe deja du kit gameconfig DANS LES DEUX SENS
    (mesure #264) -- ecrire ici n'est donc pas un detournement, c'est le canal normal."""
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    touched = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == unit_id:
            tr = list(u.get("Traits") or [])
            if trait not in tr:
                tr.append(trait)
            u["Traits"] = tr
            touched += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    return {"touched": touched, "path": str(out_path)}


def _arm(name: str, seed_bc: Path | None, keep: bool) -> dict:
    state = LOGS / ("rs_498r3_%s.json" % name)
    args = ["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
            "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(state)]
    if seed_bc is not None:
        args += ["--seed-bc", str(seed_bc)]
    _run(args)
    if not state.exists():
        return {"error": "build KO (state-file absent) -- bras %s" % name}
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    out = {"runner": rid, "arm": name}
    try:
        bg = _rpc("boardGraph", [{"runnerId": rid}])
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
        U = P287._units(dv)
        missing = [v for v in (CASTER_VID, ALLY_VID, FOE_VID, FAR_VID) if v not in U]
        if missing:
            return {"error": "unites absentes du build : %s" % missing}
        caster, ally, foe, far = (U[CASTER_VID], U[ALLY_VID], U[FOE_VID], U[FAR_VID])

        def move(uid, to):
            _rpc("applyAction", [{"runnerId": rid, "action": {
                "kind": "move", "unitId": uid,
                "to": {"col": int(to[0]), "row": int(to[1])}}}], 40000)

        # MEME geometrie que #287 : ennemi COLLE au caster (la regle dynamique de 1100 exige que le
        # caster puisse porter son attaque normale), allie LOIN (le switch doit etre visible).
        c_pos = P287._pos(caster)
        occ = {P287._pos(u) for u in U.values()} - {c_pos}
        foe_to = P287._free_at(board, c_pos, 1, occ)
        if foe_to is None:
            return {"error": "aucune tuile libre adjacente au caster"}
        move(foe["id"], foe_to)
        occ = {P287._pos(u) for u in P287._units(P287._dview(rid)).values()}
        ally_to = P287._free_at(board, c_pos, 5, occ) or P287._free_at(board, c_pos, 4, occ)
        if ally_to is None:
            return {"error": "aucune tuile libre a distance pour l'allie"}
        move(ally["id"], ally_to)
        occ = {P287._pos(u) for u in P287._units(P287._dview(rid)).values()}
        far_to = P287._free_at(board, c_pos, 6, occ)
        if far_to is not None:
            move(far["id"], far_to)

        my_player = caster.get("owner")
        for _ in range(8):
            dv = P287._dview(rid)
            if dv.get("currentPlayer") == my_player:
                break
            _rpc("applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}], 40000)

        dv = P287._dview(rid)
        U = P287._units(dv)
        ids = {v: U[v]["id"] for v in U}
        WATCH = (CASTER_VID, ALLY_VID)
        pre = {v: P287._pos(U[v]) for v in WATCH}

        # Le trait est-il REELLEMENT arrive sur l'unite ? (une ecriture de seed BC silencieusement
        # perdue rendrait le bras `big` identique au bras `base`, et le probe conclurait a tort)
        # ⚠ `combatSnapshot.units[].traits` publie des IDS `IdunBattle.Entities.Enum.UnitTrait`,
        # PAS des noms -- c'est l'invoke natif d'`UnitExtensions$$HasTrait` par valeur d'enum.
        cs = _rpc("combatSnapshot", [{"runnerId": rid}], 60000)
        traits_ally = []
        for u in (cs.get("units") or []):
            if u.get("entityId") == ids[ALLY_VID]:
                traits_ally = sorted(int(t) for t in (u.get("traits") or []))
        out["traits_ally_natif"] = traits_ally

        snap = {"dv": dv,
                "ob": _rpc("observeBattle", [{"runnerId": rid}], 40000),
                "snap": cs,
                "rng": _rpc("dumpRng", [{"runnerId": rid}], 30000)}

        res = _rpc("applyAction", [{"runnerId": rid, "action": {
            "kind": "ability", "casterId": ids[CASTER_VID], "targetId": ids[ALLY_VID],
            "abilityType": FACADE}}], 60000)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        dv2 = P287._dview(rid)
        U2 = P287._units(dv2)
        post = {v: (P287._pos(U2[v]) if v in U2 else None) for v in WATCH}
        out["live"] = {"ok": bool(a0.get("ok")), "pre": pre, "post": post,
                       "switched": post[CASTER_VID] != pre[CASTER_VID]}

        # --- REPLAY OFFLINE : port courant, puis MUTANT (foyer force a True = etat d'AVANT) ------
        out["offline"] = _replay(snap, board, ids, WATCH, mutant=False)
        out["offline_mutant"] = _replay(snap, board, ids, WATCH, mutant=True)
    finally:
        if not keep:
            _run(["dispose", "--runner", str(rid)])
    return out


def _replay(snap, board, ids, WATCH, mutant: bool) -> dict:
    from engine.runner.components import PositionComponent
    import engine.runner.operations.displace as DSP
    import engine.runner.abilities.loki.momentum as MOM
    from engine.runner.runner import Runner

    st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
    if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
        st.rng = P287._seed_rng(snap["rng"])

    def pos(uid):
        e = st.get_entity(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        return (pc.col, pc.row) if pc is not None else None

    pre = {v: pos(ids[v]) for v in WATCH}
    saved = (DSP.unit_extensions_is_displaceable, MOM.unit_extensions_is_displaceable)
    if mutant:
        # MUTANT = l'etat d'AVANT #498-r3 sur ce site precis : le gate rend TOUJOURS vrai.
        DSP.unit_extensions_is_displaceable = lambda e: True
        MOM.unit_extensions_is_displaceable = lambda e: True
    try:
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=ids[CASTER_VID], target_id=ids[ALLY_VID],
                                          ability_type=FACADE))
    finally:
        DSP.unit_extensions_is_displaceable, MOM.unit_extensions_is_displaceable = saved
    post = {v: pos(ids[v]) for v in WATCH}
    return {"pre": pre, "post": post, "switched": post[CASTER_VID] != pre[CASTER_VID]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    custom = LOGS / "seed_bc_498r3_bigtarget.json"
    w = write_seed_bc_with_trait(custom, ALLY_VID, TRAIT_AJOUTE)
    print("[seed-bc] %s : %s +%s sur %d entree(s)" % (custom.name, ALLY_VID, TRAIT_AJOUTE,
                                                      w["touched"]))
    if w["touched"] != 1:
        print("ROUGE -- l'allie n'a pas ete touche dans le seed BC")
        return 1

    rc = 0
    base = _arm("base", None, a.keep)
    big = _arm("big", custom, a.keep)
    for name, r in (("base", base), ("big", big)):
        if r.get("error"):
            print("ROUGE bras %s : %s" % (name, r["error"]))
            return 1
        print("")
        print("=== BRAS %s (runner %s) ===" % (name, r["runner"]))
        print("  traits NATIFS de l'allie : %s" % (r["traits_ally_natif"],))
        print("  live     ok=%s pre=%s post=%s switched=%s"
              % (r["live"]["ok"], r["live"]["pre"], r["live"]["post"], r["live"]["switched"]))
        print("  offline  switched=%s   (mutant pre-#498-r3 : switched=%s)"
              % (r["offline"]["switched"], r["offline_mutant"]["switched"]))

    print("")
    print("=== VERDICTS ===")
    checks = [
        ("le trait est bien arrive cote natif (id %d)" % TRAIT_ID,
         TRAIT_ID in big["traits_ally_natif"] and TRAIT_ID not in base["traits_ally_natif"]),
        ("bras base : le natif ECHANGE (temoin non degenere)", base["live"]["switched"] is True),
        ("bras base : le port ECHANGE aussi", base["offline"]["switched"] is True),
        ("bras big  : le natif N'ECHANGE PAS", big["live"]["switched"] is False),
        ("bras big  : le port N'ECHANGE PAS non plus", big["offline"]["switched"] is False),
        ("bras big  : le MUTANT (pre-fix) ECHANGE -> la divergence etait REELLE",
         big["offline_mutant"]["switched"] is True),
        ("bras base : le mutant ne change RIEN (le gate n'y mord pas)",
         base["offline_mutant"]["switched"] is True),
    ]
    for label, ok in checks:
        print("  %-58s %s" % (label, "OK" if ok else "ROUGE"))
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
