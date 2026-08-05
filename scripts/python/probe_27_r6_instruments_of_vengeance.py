"""probe #27-r6 -- InstrumentsOfVengeance (1215), 2e des 4 overrides « npc-only » de #27.

CE QUI EST TESTE
----------------
`IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$CalculateCustomUtility` :

    adj = battleQuery.<slot itf 0x80>(casterPosition, caster, ignoreSteppables: false);
    u   = adj.Any() ? 0 : 100;
    foreach (e in battleQuery.<slot itf 0x78>(caster, casterPosition, range: 2,
                                              includeCenter: false))
        if (!adj.Contains(e)) u += 20;
    return Fix64.op_Implicit(u + 20000);

TROIS constantes EN DUR, aucun `GetUtilityValue`. Les deux slots sont ancres par les decorateurs
enregistreurs : `...RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass155_0$$u003CGetAdjacentEnemiesu003Eb__0`
emet 0x80 = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, unit, ignoreSteppables)`,
et `...u003Cu003Ec__DisplayClass147_0$$u003CGetSurroundingEnemiesu003Eb__0` emet 0x78 =
`...$$GetSurroundingEnemies(actor, from, range, includeCenter)`.

LE POINT DE RE QUI NE SE DEVINE PAS -- LES DEUX ENSEMBLES N'ONT PAS LA MEME GEOMETRIE
------------------------------------------------------------------------------------
`GetAdjacentEnemies` passe par `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
qui applique la porte d'elevation `|dElev| < 2`. `GetSurroundingEnemies` passe par
`...$$GetSurroundingUnits` -> `...$$IterateSurroundingTiles`, un disque hex PUREMENT geometrique
(`TileUtil$$IsTileValidForList(..., checkElevation: 0)`). Un ennemi a distance hex 1 dont l'ecart
d'elevation vaut >= 2 est donc DANS `surrounding` et HORS `adj` : il compte `+20` **et** laisse le
`+100` arme. Ecrire ce terme `20 x |ennemis a distance EXACTEMENT 2|` serait un port FAUX dans
exactement ce regime -- le bras F le MESURE (le modele faux choisit une autre tuile que le natif).

CE QUE LE MONTAGE ETABLIT
-------------------------
* `...InstrumentsOfVengeanceAbility$$.ctor` fait une STATIC-COPY des 0x40 octets du preset
  `<TargetingOptions statics>+0x280` et la passe TELLE QUELLE a `AActiveAbility$$.ctor` : AUCUN appel
  a `TargetingOptions$$.ctor`. Le masque effectif est la constante ecrite par
  `IdunBattle.Core.Services.TargetingOptions$$.cctor` en `<preset>+0x28` :
      0x8004 = CasterIsPossibleTarget(0x8000) | CasterMatchesDynamicRule(0x4)
  C'est le MEME preset que 1216 MartialExemplar, SANS son `additionalRules = 0x10` -- donc 1215 n'a
  PAS `CasterHasNotMoved`, et son cast SURVIT au deplacement du caster (bras D, contraste direct
  avec 1216 dont `abilityTargets` tombait a 0).
* 1215 est SELF-CAST : `abilityTargets(1215)` rend UNE cible, le caster. Ses `attackPlans.evals` sur
  les ENNEMIS rendent tous `rankCount = 0` -> `_best_attack` ne peut rien produire, d'ou la ROUTE
  NON-ATTAQUE (`playbook/nonattack.py`) bien que `constants.damageProfile = HeavyRound`.
* `pairUtility(1215, SELF) = 0` -> `make_damage_predictions` rend `[]` (herite), et le RPC rend
  `playbookClass = InstrumentsOfVengeancePlaybook` sur l'unite GREFFEE : le natif charge bien le
  playbook PAR ABILITY.
* Comme le cast reste legal apres deplacement, il existe autant d'actions 1215 que de tuiles
  atteignables : le terme est reellement POSITION-DEPENDANT, et c'est le CHOIX DE TUILE qui rend les
  trois constantes DISCRIMINABLES (la ou 1216 n'avait qu'une seule action possible).

RESERVE DE MESURE, TRAITEE DANS LE MONTAGE
------------------------------------------
`...InstrumentsOfVengeancePlaybook$$GetUseProbability` rend `Fix64.Zero` si
`GetTurnsFinished(unit) == 0`, `Fix64.Half` si `== 1`, `Fix64.One` sinon, et
`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` en fait `p >= 1 -> true ; p <= 0 -> false ;
sinon TIRAGE`. L'ability est donc INDISPONIBLE au tour du build et TIREE A 1/2 au suivant : seule la
fenetre `GetTurnsFinished >= 2` est deterministe. Le probe y entre par QUATRE `act endturn`
(l'IA ne joue pas : la geometrie du montage est preservee) et VERIFIE `turnsFinished == 2` au
`combatSnapshot` avant de mesurer.

⚠ **Le bras E a CHANGE DE NATURE (#27-r8)** : il mesurait un ECART NOMME (le natif ne propose pas
1215 a `turnsFinished == 0`, le moteur si), il mesure desormais un ACCORD -- le gate slot-4 est
PORTE (`loki_custom.InstrumentsOfVengeancePlaybook.should_evaluate_unit`). Le verrou annonce
(<< `turnsFinished` absent de `decisionView` -> capteur a ecrire -> fenetre de reinject >>) etait
FAUX : la `Scene` de decision prend ces tables dans **`combatSnapshot`**, qui publie le champ
depuis #N11. Le bras vaut donc TROIS assertions, et les deux dernieres existent parce qu'un accord
seul ne prouverait rien : (1) le SUBSTRAT est mesure (`Scene.turns_finished(caster) == 0`, gate
`False`) -- sinon le canal serait muet et le gate permissif ; (2) natif et moteur s'accordent a ne
PAS proposer 1215 ; (3) **contre-epreuve** : le meme etat, gate neutralise, redonne 1215 -- si elle
ne mord pas, l'accord (2) vient d'ailleurs.

MONTAGE (board MC1_67, seed 909, rank 17)
-----------------------------------------
PORTEUR GREFFE : le seul porteur de 1215 est `darkaBossLion` (npc). On remplace `ActiveAbilities` de
`darkaAsmodai` (MEME faction Dark Angels, present dans `rl_duel build --list-pool`) par `[1215]` dans
une COPIE du seed BC (`case-92` §5bis). La formule ne lit ni stat ni trait du caster -> la greffe ne
la deforme pas.

LE CASTER N'EST DEPLACE QU'AU BRAS D (le dernier) : ce sont les ENNEMIS qu'on bouge, sinon le sweep
de tuiles -- qui EST le levier de mesure ici -- disparait.

BRAS (caster en (1,0), 13 tuiles de move ; elevations (1,2)=2, (1,3)=4, (2,3)=4)
  E : turnsFinished = 0            -> ni le natif ni le moteur ne proposent 1215 (gate slot-4
      porte, #27-r8), et la contre-epreuve « gate neutralise » redonne 1215
  A : tous les ennemis a distance >= 3 de toute tuile -> custom CONSTANT = 20100 -> le natif reste
      sur son origine (aucun `MoveUnitMessage`)
  B : un ennemi en (2,0), ADJACENT a l'origine        -> l'origine perd son `+100` -> le natif
      DEPLACE le caster pour caster depuis une tuile non adjacente
  C : un ennemi en (5,1), adjacent a AUCUNE tuile de l'origine -> seul le `+20` departage
  F : deux ennemis en (1,3) et (2,3) (elevation 4) + un en (3,2) -> la tuile (1,2) (elevation 2) a un
      ennemi a distance 1 avec |dElev| = 2 : HORS `adj`, DANS `surrounding`. Contre-epreuve du QUIRK :
      le modele `20 x |dist == 2|` choisit une AUTRE tuile que le natif.
  D : `CasterHasNotMoved` ABSENT -> apres un `act move` du caster, `abilityTargets(1215)` rend
      TOUJOURS sa cible (contraste 1216).

Usage (depuis scripts/python, ASCII only) :
    python probe_27_r6_instruments_of_vengeance.py --build
    python probe_27_r6_instruments_of_vengeance.py            # re-joue sur le runner du state-file
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_instruments_of_vengeance_graft.json"
STATE = LOGS / "rs_27r6_instruments_of_vengeance.json"
BOARD = "MC1_67"
SEED = 909

INSTRUMENTS = int(ActiveAbilityType.InstrumentsOfVengeance)     # 1215 = 0x4bf
NORMAL = 69

GRAFT_ON = "darkaAsmodai"
P_UNITS = "darkaAsmodai"
A_UNITS = "orksWarboss,necroWarden,astraCreed"

CASTER_VID = "darkaAsmodai"
E1_VID = "orksWarboss"
E2_VID = "necroWarden"
E3_VID = "astraCreed"

# Spawns adverses du seed 909 sur MC1_67 -- « loin » = distance >= 3 de TOUTE tuile atteignable.
FAR = {E1_VID: "6,8", E2_VID: "6,7", E3_VID: "5,8"}
ADJACENT_TO_ORIGIN = "2,0"      # bras B : voisin de l'origine (1,0), |dElev| = 1 -> ADJACENT
RING2_ONLY = "5,1"              # bras C : a distance 2 de (3,1)/(3,2), adjacent a aucune candidate
QUIRK_A = "1,3"                 # bras F : elevation 4, voisin de (1,2) (elevation 2) -> |dElev| = 2
QUIRK_B = "2,3"                 # bras F : elevation 4, voisin de (2,2)
BLOCKER = "3,2"                 # bras F : occupe la tuile a fort tile_utility qui masquait le quirk

TURNS_TO_ADVANCE = 4            # 2 tours PLEINS -> turnsFinished(caster) == 2 (fenetre deterministe)
MIN_TURNS_FINISHED = 2


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _endturn(rid: int) -> None:
    _run(["act", "endturn", "--state-file", str(STATE), "--runner", str(rid)])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- les ids ne sont JAMAIS hardcodes."""
    return {u["visualId"]: (u["id"], (u["pos"]["col"], u["pos"]["row"]))
            for u in (_dv(rid).get("units") or [])}


def _turns_finished(rid: int) -> dict:
    """{entityId: turnsFinished} -- `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished`
    (`UnitComponent + 0x5c`), le SEUL canal qui l'expose (`combatSnapshot`, pas `decisionView`)."""
    cs = L._rpc("combatSnapshot", [{"runnerId": rid, "want": ["units", "turnsFinished"]}])
    return {u.get("entityId"): u.get("turnsFinished") for u in (cs.get("units") or [])}


def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities` de `GRAFT_ON` remplace par `[1215]`.
    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`)."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [INSTRUMENTS]
            n += 1
    if n != 1:
        raise SystemExit("greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[graft] %s.ActiveAbilities = [%d]" % (GRAFT_ON, INSTRUMENTS))


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


def _targets(rid: int, cid: int) -> list:
    at = L._rpc("abilityTargets", [{"runnerId": rid, "unitId": cid, "abilityType": INSTRUMENTS}])
    out = []
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            out += [(t.get("kind"), t.get("targetId")) for t in (a.get("targets") or [])]
    return out


def _attack_plan_ranks(rid: int, cid: int) -> list:
    """`decisionView.attackPlans[cid].evals` filtre sur 1215 -- la preuve que `_best_attack` ne peut
    RIEN produire (tous les `rankCount` a 0, et sur des ENNEMIS alors que la cible retenue par le
    natif est le CASTER)."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True, "maxRank": 32}])
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") == cid:
            return [(ev.get("targetId"), ev.get("rankCount"))
                    for ev in (p.get("evals") or []) if ev.get("abilityId") == INSTRUMENTS]
    return []


def _pair_utility(rid: int, cid: int) -> dict:
    """`pairUtility(1215, caster, SELF)` = `ComparablePlaybook<T>.CalculateUtilityFromPredictions`
    invoque en direct -- doit valoir 0 (la cible est le caster, le natif ne predit aucun degat)."""
    return L._rpc("pairUtility", [{"runnerId": rid, "unitId": cid, "abilityType": INSTRUMENTS,
                                   "targetId": cid}])


def _native_choice(rid: int, cid: int) -> list:
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") == cid:
            return [(m.get("cls"), m.get("abilityType"), m.get("targetId"),
                     ((m.get("to") or {}).get("col"), (m.get("to") or {}).get("row"))
                     if m.get("to") else None)
                    for m in (u.get("proposed") or [])]
    return []


def _wrong_custom(pb, ctx, tile, _target, _aid) -> float:
    """LE MODELE FAUX que le decompile refute : `+20 x |ennemis a distance EXACTEMENT 2|`.

    Il resume la difference d'ensembles `surrounding \\ adj` par une distance, et perd donc les
    ennemis a distance 1 que la porte d'elevation d'`IterateAdjacentTiles` exclut d'`adj` alors que
    le disque d'`IterateSurroundingTiles` les garde. Joue au bras F comme CONTRE-EPREUVE."""
    adj = pb._adjacent_enemies(ctx, tile)
    n2 = sum(1 for u in (ctx.enemies or [])
             if (u.get("pos") or {}).get("col") is not None
             and hexgeo.distance(tile, (u["pos"]["col"], u["pos"]["row"])) == 2)
    return 20000.0 + (0.0 if adj else 100.0) + 20.0 * n2


def _engine(rid: int, cid: int) -> dict:
    """Quatre decisions MOTEUR sur le MEME etat : telle quelle / custom force a 0 / route desactivee /
    MODELE FAUX. Les trois dernieres sont les CONTRE-EPREUVES."""
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
    pb = PB.REGISTRY.get(INSTRUMENTS)
    targets = pb.eligible_targets(ctx, INSTRUMENTS)
    per_tile = [(T, pb.calculate_custom_utility(ctx, T, cid, INSTRUMENTS),
                 round(tile_utility(ctx, T), 6)) for T in (ctx.reach_nc or [])]

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, t, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    type(pb).calculate_custom_utility = _wrong_custom
    try:
        wrong = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)
    # #27-r8 : la CONTRE-EPREUVE du gate slot-4. `nogate` neutralise
    # `...InstrumentsOfVengeancePlaybook$$ShouldEvaluate` (retour True inconditionnel) : c'est
    # EXACTEMENT le moteur d'AVANT le port. Au bras E (`turnsFinished == 0`) les deux decisions
    # doivent DIFFERER -- sinon le gate ne mord pas, et un accord natif/moteur ne prouverait rien.
    orig_gate = type(pb).should_evaluate_unit
    type(pb).should_evaluate_unit = lambda self, c, aid: True
    try:
        nogate = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).should_evaluate_unit = orig_gate
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target"), zero.get("to")),
            "wrong": (wrong.get("ability"), wrong.get("target"), wrong.get("to")),
            "noroute": (noroute.get("ability"), noroute.get("target"), noroute.get("to")),
            "nogate": (nogate.get("ability"), nogate.get("target"), nogate.get("to")),
            # Le SUBSTRAT du gate, lu la ou le playbook le lit (jamais re-derive) : si ce canal est
            # muet, `should_evaluate_unit` est permissif et le bras E ne mesure RIEN.
            "gate_turns_finished": ctx.scene.turns_finished(cid) if ctx.scene is not None else None,
            "gate": pb.should_evaluate_unit(ctx, INSTRUMENTS),
            "targets": targets, "origin": ctx.origin, "per_tile": per_tile,
            "custom_origin": pb.calculate_custom_utility(ctx, ctx.origin, cid, INSTRUMENTS)}


def _native_move_to(ch) -> tuple | None:
    for cls, _a, _t, to in ch:
        if cls == "MoveUnitMessage":
            return to
    return None


def _native_ability(ch):
    ab = [(a, t) for cls, a, t, _to in ch if cls == "ActiveAbilityMessage"]
    return ab[-1] if ab else (None, None)


def run_ab(rid: int, engine: bool = True) -> dict:
    """Joue les six bras et rend les lignes structurees (consommees par le test de garde)."""
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    cid = ids[CASTER_VID]
    rows: dict = {"caster_id": cid, "spawn": _units(rid)[CASTER_VID][1]}

    def arm(key):
        ch = _native_choice(rid, cid)
        ab, tgt = _native_ability(ch)
        row = {"native": (ab, tgt), "native_to": _native_move_to(ch),
               "msgs": [c for c, _a, _t, _to in ch], "targets_rpc": _targets(rid, cid),
               "pos": {v: p for v, (_i, p) in _units(rid).items()}}
        if engine:
            row["engine"] = _engine(rid, cid)
        rows[key] = row

    # --- E : la fenetre NON deterministe, mesuree AVANT d'y entrer -------------------------------
    want = [(ids[v], to) for v, to in FAR.items()]
    for uid, to in want:
        _move(rid, uid, to)
    _assert_placed(rid, want)
    rows["turns_before"] = _turns_finished(rid).get(cid)
    arm("E_turns0")

    # --- fenetre deterministe : `GetTurnsFinished >= 2` ------------------------------------------
    for _ in range(TURNS_TO_ADVANCE):
        _endturn(rid)
    tf = _turns_finished(rid).get(cid)
    rows["turns_after"] = tf
    if tf is None or tf < MIN_TURNS_FINISHED:
        raise SystemExit("turnsFinished(caster) = %r < %d -- la fenetre deterministe de "
                         "`GetUseProbability` n'est PAS ouverte, aucune mesure ne vaut"
                         % (tf, MIN_TURNS_FINISHED))
    _assert_placed(rid, want)          # l'IA n'a pas joue : la geometrie est intacte
    rows["pair_utility"] = _pair_utility(rid, cid)
    rows["attack_plan_ranks"] = _attack_plan_ranks(rid, cid)
    arm("A_far")

    # --- B : un ennemi ADJACENT a l'origine -------------------------------------------------------
    _move(rid, ids[E1_VID], ADJACENT_TO_ORIGIN)
    _assert_placed(rid, [(ids[E1_VID], ADJACENT_TO_ORIGIN)])
    arm("B_adjacent")

    # --- C : le `+20` SEUL (aucune adjacence a l'origine) -----------------------------------------
    _move(rid, ids[E1_VID], FAR[E1_VID])
    _move(rid, ids[E2_VID], RING2_ONLY)
    _assert_placed(rid, [(ids[E1_VID], FAR[E1_VID]), (ids[E2_VID], RING2_ONLY)])
    arm("C_ring2")

    # --- F : le QUIRK d'elevation (adj gate, surrounding non gate) --------------------------------
    _move(rid, ids[E3_VID], QUIRK_A)
    _move(rid, ids[E2_VID], QUIRK_B)
    _move(rid, ids[E1_VID], BLOCKER)
    _assert_placed(rid, [(ids[E3_VID], QUIRK_A), (ids[E2_VID], QUIRK_B), (ids[E1_VID], BLOCKER)])
    arm("F_elevation")

    # --- D : `CasterHasNotMoved` ABSENT (MUTE l'etat -> joue en DERNIER) --------------------------
    before = _targets(rid, cid)
    origin = _units(rid)[CASTER_VID][1]
    dest = next((T for T, _c, _t in rows["F_elevation"]["engine"]["per_tile"]
                 if T != origin), None) if engine else None
    _move(rid, cid, "%d,%d" % dest if dest else "0,0")
    rows["caster_has_not_moved"] = {"before": before, "after": _targets(rid, cid),
                                    "native_after": _native_choice(rid, cid),
                                    "from": origin, "to": _units(rid)[CASTER_VID][1]}
    return rows


def main() -> int:
    argv = sys.argv[1:]
    engine = "--no-engine" not in argv
    rid = build() if "--build" in argv else _runner_id()
    print("[probe #27-r6] runner=%d board=%s engine=%s" % (rid, BOARD, engine))
    rows = run_ab(rid, engine=engine)
    print("  caster %s id=%d spawn=%s" % (CASTER_VID, rows["caster_id"], rows["spawn"]))
    print("  turnsFinished(caster) : avant=%s -> apres %d endturn = %s"
          % (rows["turns_before"], TURNS_TO_ADVANCE, rows["turns_after"]))
    ok = True

    e0 = rows["E_turns0"]
    gate_seen = e0["native"][0] != INSTRUMENTS
    print("  [E turnsFinished=0] natif=%s (attendu : PAS de 1215)  %s"
          % (e0["msgs"], "OK" if gate_seen else "MISMATCH"))
    ok &= gate_seen
    if engine:
        # #27-r8 : le gate slot-4 est PORTE -- le bras E est desormais un ACCORD, plus un ecart.
        ge = e0["engine"]
        # (1) le SUBSTRAT est-il mesure ? Un canal muet rendrait le gate permissif, et l'accord
        #     ci-dessous serait un accord de REGIME DEGENERE (les deux bras identiques par
        #     construction). On exige donc un temoin NON NUL avant de lire quoi que ce soit.
        substrate = (ge.get("gate_turns_finished") == 0 and ge.get("gate") is False)
        print("        substrat  : Scene.turns_finished(caster)=%r  gate=%r  %s"
              % (ge.get("gate_turns_finished"), ge.get("gate"),
                 "OK" if substrate else "NON MESURE -- le bras E ne prouve rien"))
        ok &= substrate
        # (2) l'accord lui-meme.
        agree = ge["on"][0] != INSTRUMENTS
        print("        moteur    : on=%s to=%s  %s"
              % (ge["on"], ge["to"], "OK (accord)" if agree else "MISMATCH -- 1215 propose"))
        ok &= agree
        # (3) la contre-epreuve : SANS le gate, le moteur proposait bien 1215. Si elle ne mord pas,
        #     l'accord (2) vient d'ailleurs et ce bras ne mesure PAS le gate.
        bites = ge["nogate"][0] == INSTRUMENTS
        print("        sans gate : %s  %s"
              % (ge["nogate"], "OK (le gate MORD)" if bites
                 else "NE MORD PAS -- l'accord ci-dessus n'est PAS du au gate"))
        ok &= bites

    pu = rows.get("pair_utility") or {}
    print("  [predictions] pairUtility(1215, SELF) = %r  playbookClass=%r"
          % (pu.get("utility"), pu.get("playbookClass")))
    print("  [attackPlans] evals 1215 sur les ENNEMIS = %r (rankCount attendu 0 partout)"
          % (rows.get("attack_plan_ranks"),))
    ok &= (pu.get("utility") == 0)
    ok &= all(rc == 0 for _t, rc in (rows.get("attack_plan_ranks") or []))

    for key in ("A_far", "B_adjacent", "C_ring2", "F_elevation"):
        r = rows[key]
        okr = r["native"][0] == INSTRUMENTS and r["native"][1] == rows["caster_id"]
        print("  [%s] natif=%s to=%s cibles=%s  %s"
              % (key, r["msgs"], r["native_to"], r["targets_rpc"], "OK" if okr else "MISMATCH"))
        if engine:
            e = r["engine"]
            same = (e["on"][0] == INSTRUMENTS and e["on"][1] == rows["caster_id"]
                    and e["to"] == r["native_to"])
            print("        moteur : on=%s to=%s custom(origine)=%s  %s"
                  % (e["on"], e["to"], e["custom_origin"], "ACCORD" if same else "DESACCORD"))
            print("        contre-epreuves : custom=0 -> %s | route OFF -> %s | modele FAUX -> %s"
                  % (e["zero"], e["noroute"], e["wrong"]))
            okr = okr and same
        ok &= okr

    if engine:
        f = rows["F_elevation"]
        quirk = f["engine"]["wrong"][2] != f["native_to"]
        print("  [F quirk elevation] natif to=%s | modele FAUX to=%s  %s"
              % (f["native_to"], f["engine"]["wrong"][2],
                 "OK (le modele faux DIVERGE)" if quirk else "NON DISCRIMINANT"))
        ok &= quirk

    d = rows["caster_has_not_moved"]
    survives = bool(d["before"]) and bool(d["after"])
    print("  [D pas de CasterHasNotMoved] %s -> %s | cibles avant=%s apres=%s  %s"
          % (d["from"], d["to"], d["before"], d["after"], "OK" if survives else "MISMATCH"))
    ok &= survives

    print("[probe #27-r6] %s" % ("TOUS LES BRAS OK" if ok else "AU MOINS UN BRAS EN ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
