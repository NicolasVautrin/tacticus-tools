"""probe #27-r4 -- MartialExemplar (1216), 1er des 4 overrides « npc-only » de #27.

CE QUI EST TESTE
----------------
`IdunBattle.AI.Playbook.Loki.MartialExemplarPlaybook$$CalculateCustomUtility` :

    n = |{ e in battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false)
           : UnitExtensions$$IsNormalUnit(e) }|
    return Fix64.FromInt(n * 1000)

et son gate, `...MartialExemplarPlaybook$$ShouldEvaluate(unit, position, possiblePositions)` :

    return battleQuery.<slot itf 0x80>(position, unit, false).Count > 0

Le slot 0x80 est `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, unit,
ignoreSteppables)` -- ancre par le decorateur enregistreur
`...RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass155_0$$u003CGetAdjacentEnemiesu003Eb__0`,
qui emet exactement ce slot. Son corps ne lit du `unit` que
`OwnerComponent$$get_CurrentPlayerEntityId` -- le CAMP, ni stat ni trait ni arme ni portee : c'est ce
qui rend l'ability GREFFABLE malgre un porteur npc-seul (`darkaBossLion`).
`UnitExtensions$$IsNormalUnit(e)` = `!HasTrait(e, 0xd = Object) && !HasTrait(e, 0x1b = Steppable)`.

CE QUE LE MONTAGE A ETABLI, ET QUI CHANGE LE DOSSIER
----------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$.ctor` n'appelle PAS la
surcharge explicite de `TargetingOptions$$.ctor` : il recopie le preset
`<TargetingOptions statics>+0x280` et passe `additionalRules = 0x10` a la surcharge
`.ctor(this, template, additionalRules)`, qui fait `this.rules = additionalRules | template.rules`.
Le preset porte `rules = 0x8004` (ecrit par `...TargetingOptions$$.cctor`), donc le masque EFFECTIF
est `0x8014` -- et le litteral visible `0x10` seul aurait ete FAUX. Decode contre
`IdunBattle.Core.Services.TargetingRule` (`data/symbols/<build>/frida/enums.tsv`) :

    0x8014 = CasterIsPossibleTarget(0x8000) | CasterHasNotMoved(0x10) | CasterMatchesDynamicRule(0x4)

Les deux premiers bits sont MESURES ici, et ils bornent tout ce qui suit :

* `CasterIsPossibleTarget` -> 1216 est **SELF-CAST** : `abilityTargets(1216)` rend UNE cible, le
  caster lui-meme. Les `attackPlans.evals` de 1216 sur les ENNEMIS rendent tous `rankCount = 0`.
* `CasterHasNotMoved` -> l'ability n'est castable QUE depuis la tuile d'origine. Mesure : deplacer le
  caster fait passer `abilityTargets(1216)` de 1 cible a **0**.

=> Le terme custom est ancre sur `casterPosition`, mais comme le cast est interdit apres deplacement,
il n'existe qu'UNE action 1216 possible par tour. Le custom ne peut donc jamais departager deux
actions de 1216 entre elles : sa MAGNITUDE (1000 par ennemi adjacent) est NON DISCRIMINABLE par le
choix natif dans ce regime -- toute valeur >= ~10 produirait la meme decision. Ce probe mesure ce
qui EST discriminable (le gate, et le fait que la greffe exerce bien le playbook), et le dit.

MONTAGE (board MC1_67)
----------------------
PORTEUR GREFFE. La seule unite qui porte 1216 est `darkaBossLion` (npc). « npc-only » n'est PAS
« non confrontable » : le natif charge le playbook PAR ABILITY
(`PlaybookDatabase.LoadPlaybook(abilityType)`), jamais par unite, et cette formule ne lit ni stat ni
trait du CASTER. On remplace donc `ActiveAbilities` de `darkaAsmodai` (MEME faction Dark Angels, arme
de melee, present dans `rl_duel build --list-pool`) par `[1216]` dans une COPIE du seed BC
(`case-92` §5bis).

LE CASTER N'EST JAMAIS DEPLACE -- c'est une ASSERTION du probe, pas une precaution : un `act move` du
caster arme `CasterHasNotMoved` et desarme l'ability, et les trois bras degenereraient en « le natif
ne propose jamais 1216 », un faux negatif parfaitement coherent. On DEPLACE LES ENNEMIS.

BRAS (le caster spawne en (1,0), dont les 3 voisins walkables sont (0,0), (1,1), (2,0))
  A : n=0 -- les 3 ennemis a distance >= 2  -> `ShouldEvaluate` FAUX partout ou le cast est legal
                                              -> le natif propose l'attaque NORMALE (69)
  B : n=1 -- un ennemi amene en (1,1)       -> le natif propose 1216
  C : n=2 -- un second ennemi en (0,0)      -> le natif propose 1216 (le choix ne CHANGE pas :
                                              c'est la preuve que la magnitude n'est pas
                                              discriminable, pas un defaut du montage)
  D : contre-epreuve `CasterHasNotMoved` -- depuis l'etat C, on DEPLACE le caster et
      `abilityTargets(1216)` doit tomber a 0 cible.

Usage (depuis scripts/python, ASCII only) :
    python probe_27_r4_martial_exemplar.py --build
    python probe_27_r4_martial_exemplar.py            # re-joue sur le runner du state-file
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_martial_exemplar_graft.json"
STATE = LOGS / "rs_27r4_martial_exemplar.json"
BOARD = "MC1_67"
SEED = 909

MARTIAL_EXEMPLAR = int(ActiveAbilityType.MartialExemplar)      # 1216 = 0x4c0
NORMAL = 69

GRAFT_ON = "darkaAsmodai"
P_UNITS = "darkaAsmodai"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

CASTER_VID = "darkaAsmodai"
E1_VID = "orksWarboss"
E2_VID = "necroWarden"
E3_VID = "astraCreed"

FAR = {E1_VID: "3,2", E2_VID: "4,4", E3_VID: "6,7"}   # bras A : aucun voisin de (1,0)
NEAR_1 = "1,1"                                        # bras B : voisin de (1,0)
NEAR_2 = "0,0"                                        # bras C : second voisin de (1,0)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- les ids ne sont JAMAIS hardcodes."""
    return {u["visualId"]: (u["id"], (u["pos"]["col"], u["pos"]["row"]))
            for u in (_dv(rid).get("units") or [])}


def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities` de `GRAFT_ON` remplace par `[1216]`.
    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`)."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [MARTIAL_EXEMPLAR]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d]" % (GRAFT_ON, MARTIAL_EXEMPLAR))


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : les bras degenerent en UN seul etat, ou l'accord
    natif<->attendu est trivialement vrai (piege mesure le 2026-07-30 sur #27-4)."""
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def build() -> int:
    write_graft_seed_bc()
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
          "--state-file", str(STATE)])
    return _runner_id()


def _adjacent_enemy_count(rid: int, caster_pos: tuple) -> int:
    """Mirror LIVE de `battleQuery.<0x80>(casterPosition, caster).Count(IsNormalUnit)` : compte lu
    du BOARD natif (`boardGraph` = `GetAdjacentTiles` + porte d'elevation d'`IterateAdjacentTiles`),
    pas du port -- c'est la reference contre laquelle le port sera compare."""
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    tiles = {t["id"]: t for t in (bg.get("tiles") or [])}
    pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles.values()}
    id_of = {v: k for k, v in pos_of.items()}
    elev = {pos_of[i]: t.get("elevation") for i, t in tiles.items()}
    walk = {pos_of[i] for i, t in tiles.items() if t.get("walkable")}
    near = set()
    for n in (tiles[id_of[caster_pos]].get("neighbours") or []):
        q = pos_of.get(n)
        if q is None or q not in walk:
            continue
        if elev.get(caster_pos) is not None and elev.get(q) is not None \
                and abs(elev[caster_pos] - elev[q]) >= 2:
            continue
        near.add(q)
    return sum(1 for u in (_dv(rid).get("units") or [])
               if not u.get("ctrl") and (u["pos"]["col"], u["pos"]["row"]) in near)


def _targets(rid: int, cid: int) -> list:
    at = L._rpc("abilityTargets", [{"runnerId": rid, "unitId": cid,
                                    "abilityType": MARTIAL_EXEMPLAR}])
    out = []
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            out += [(t.get("kind"), t.get("targetId")) for t in (a.get("targets") or [])]
    return out


def _native_choice(rid: int, cid: int) -> list:
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") == cid:
            return [(m.get("cls"), m.get("abilityType"), m.get("targetId"))
                    for m in (u.get("proposed") or [])]
    return []


def _engine(rid: int, cid: int) -> dict:
    """Trois decisions MOTEUR sur le MEME etat : telle quelle / custom force a 0 / route desactivee.

    Les deux dernieres sont les CONTRE-EPREUVES : si le choix ne bouge pas quand on desarme le
    terme, c'est que l'accord ne vient pas de lui."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.ai import context as AICTX
    from engine.playbook.base import tile_utility

    sid = L.INV._session_id()

    def rpc(m, b, t):
        return EV._r(sid, m, b, t)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, cid, wt, predictor)
    pb = PB.REGISTRY.get(MARTIAL_EXEMPLAR)
    targets = pb.eligible_targets(ctx, MARTIAL_EXEMPLAR)
    custom = pb.calculate_custom_utility(ctx, ctx.origin, cid, MARTIAL_EXEMPLAR)
    gate = pb.should_evaluate(ctx, ctx.origin, MARTIAL_EXEMPLAR)
    # `CasterHasNotMoved` : toute tuile autre que l'origine doit etre REFUSEE
    off_origin = [T for T in (ctx.reach_nc or []) if T != ctx.origin]
    added_off = [T for T in off_origin if pb.is_caster_added(ctx, T)]

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, t, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "targets": targets, "custom": custom, "gate": gate,
            "tile": tile_utility(ctx, ctx.origin),
            "off_origin": len(off_origin), "added_off": added_off}


def _arm(rid: int, name: str, cid: int, cpos: tuple, expect_ability: int,
         expect_custom: float, engine: bool) -> bool:
    n = _adjacent_enemy_count(rid, cpos)
    tg = _targets(rid, cid)
    ch = _native_choice(rid, cid)
    ab = [a for cls, a, _t in ch if cls == "ActiveAbilityMessage"]
    got = ab[-1] if ab else None
    ok = got == expect_ability
    print("  [%s] n(adjacents normaux)=%d  abilityTargets(1216)=%s" % (name, n, tg))
    print("        natif  : %s -> ability=%s  attendu=%s  %s"
          % ([c for c, _a, _t in ch], got, expect_ability, "OK" if ok else "MISMATCH"))
    if not engine:
        return ok
    e = _engine(rid, cid)
    eng_ab = e["on"][0]
    ok_eng = eng_ab == expect_ability
    ok_custom = abs(float(e["custom"]) - expect_custom) < 1e-9
    # CasterHasNotMoved : AUCUNE tuile hors origine ne doit passer `is_caster_added`
    ok_moved = not e["added_off"]
    print("        moteur : on=%s to=%s | custom=%s (attendu %s) gate=%s cibles=%s"
          % (e["on"], e["to"], e["custom"], expect_custom, e["gate"], e["targets"]))
    print("        contre-epreuves : custom force a 0 -> %s | route DESACTIVEE -> %s"
          % (e["zero"], e["noroute"]))
    print("        CasterHasNotMoved : %d tuiles hors origine, %d acceptees (attendu 0)"
          % (e["off_origin"], len(e["added_off"])))
    for lbl, v in (("moteur==natif", ok_eng), ("custom", ok_custom),
                   ("CasterHasNotMoved", ok_moved)):
        if not v:
            print("        !! ECHEC %s" % lbl)
    return ok and ok_eng and ok_custom and ok_moved


def run_ab(rid: int, engine: bool = True) -> dict:
    """Joue les quatre bras et rend les lignes structurees (consommees par le test de garde).

    Chaque bras : `{n, native, engine, targets, custom_expected}`. Le bras D est rendu a part sous
    la cle `caster_has_not_moved` (`{before, after}`) -- il MUTE l'etat (il deplace le caster), donc
    il est joue EN DERNIER."""
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    cid = ids[CASTER_VID]
    cpos = _units(rid)[CASTER_VID][1]
    rows: dict = {}

    def arm(key, expect_ability, expect_custom):
        n = _adjacent_enemy_count(rid, cpos)
        ch = _native_choice(rid, cid)
        ab = [a for cls, a, _t in ch if cls == "ActiveAbilityMessage"]
        tgt = [t for cls, _a, t in ch if cls == "ActiveAbilityMessage"]
        row = {"n": n, "native": (ab[-1] if ab else None, tgt[-1] if tgt else None),
               "msgs": [c for c, _a, _t in ch], "targets_rpc": _targets(rid, cid),
               "expect_ability": expect_ability, "expect_custom": expect_custom}
        if engine:
            row["engine"] = _engine(rid, cid)
        rows[key] = row

    want = [(ids[v], to) for v, to in FAR.items()]
    for uid, to in want:
        _move(rid, uid, to)
    _assert_placed(rid, want)
    arm("n=0", NORMAL, 0.0)

    _move(rid, ids[E1_VID], NEAR_1)
    _assert_placed(rid, [(ids[E1_VID], NEAR_1)])
    arm("n=1", MARTIAL_EXEMPLAR, 1000.0)

    _move(rid, ids[E2_VID], NEAR_2)
    _assert_placed(rid, [(ids[E2_VID], NEAR_2)])
    arm("n=2", MARTIAL_EXEMPLAR, 2000.0)

    before = _targets(rid, cid)
    _move(rid, cid, "2,0")
    rows["caster_has_not_moved"] = {"before": before, "after": _targets(rid, cid)}
    return rows


def main() -> int:
    argv = sys.argv[1:]
    engine = "--no-engine" not in argv
    rid = build() if "--build" in argv else _runner_id()
    print("[probe #27-r4] runner=%d board=%s engine=%s" % (rid, BOARD, engine))
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    cid = ids[CASTER_VID]
    print("  caster %s id=%d spawn=%s (JAMAIS deplace)"
          % (CASTER_VID, cid, _units(rid)[CASTER_VID][1]))

    rows = run_ab(rid, engine=engine)
    ok = True
    for key in ("n=0", "n=1", "n=2"):
        r = rows[key]
        got = r["native"][0]
        okr = got == r["expect_ability"]
        print("  [%s] n(adjacents normaux)=%d  abilityTargets(1216)=%s"
              % (key, r["n"], r["targets_rpc"]))
        print("        natif  : %s -> ability=%s  attendu=%s  %s"
              % (r["msgs"], got, r["expect_ability"], "OK" if okr else "MISMATCH"))
        if engine:
            e = r["engine"]
            oke = e["on"][0] == r["expect_ability"]
            okc = abs(float(e["custom"]) - r["expect_custom"]) < 1e-9
            okm = not e["added_off"]
            print("        moteur : on=%s to=%s | custom=%s (attendu %s) gate=%s cibles=%s"
                  % (e["on"], e["to"], e["custom"], r["expect_custom"], e["gate"], e["targets"]))
            print("        contre-epreuves : custom force a 0 -> %s | route DESACTIVEE -> %s"
                  % (e["zero"], e["noroute"]))
            print("        CasterHasNotMoved : %d tuiles hors origine, %d acceptees (attendu 0)"
                  % (e["off_origin"], len(e["added_off"])))
            okr = okr and oke and okc and okm
        ok &= okr
    d = rows["caster_has_not_moved"]
    moved_ok = bool(d["before"]) and not d["after"]
    print("  [D CasterHasNotMoved] avant move=%s  apres move=%s  %s"
          % (d["before"], d["after"], "OK" if moved_ok else "MISMATCH"))
    ok &= moved_ok

    print("[probe #27-r4] %s" % ("TOUS LES BRAS OK" if ok else "AU MOINS UN BRAS EN ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
