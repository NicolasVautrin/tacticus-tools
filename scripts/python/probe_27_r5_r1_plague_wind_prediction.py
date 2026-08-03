"""probe #27-r5-r1 -- les TROIS batchs de `MakeDamagePredictions` de 1035 et 1093.

CE QUI EST MESURE
-----------------
`IdunBattle.AI.Playbook.Loki.PlagueWindPlaybook$$MakeDamagePredictions` (1035) et
`IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$MakeDamagePredictions` (1093)
enchainent TROIS `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` -- un par vague, avec
sa propre formule de degat et le MEME `GetHits()` -- puis `AddRange` des trois. Le port n'en rendait
qu'UN (chemin generique mono-cible). L'oracle est `aiPlaybookPredict`, qui invoque le
`MakeDamagePredictions` NATIF : on compare la LISTE ENTIERE d'events, par cible et par champ.

Le facteur `Summon` de 1093 (`If(HasTrait(<DSLSelectors+0x60> = Target, 2 = Summon),
Multiply(<avg>, <DSLFormulas+0x28> = Direct(2)), <avg>)`) porte sur la **CIBLE PRINCIPALE**, jamais
sur l'unite frappee : la formule est evaluee UNE FOIS, hors de la boucle de
`GenerateMultiHitAttackPredictions`, sur l'`AbilityEntities` du message. Les deux bras `summon_*`
existent pour trancher exactement ce point.

MONTAGE (board MC1_67, seed 909)
--------------------------------
UN seul build par bras, DEUX abilities mesurees dessus :
  * `deathTyphus`     porte 1035 nativement (present dans `rl_duel build --list-pool`) ;
  * `deathBlightlord` porte 1093 par GREFFE (`catalog_inject.write_grafted_seed_bc(kind="active")`
    -- 1093 est absente des `BC.Abilities.ActiveAbilities` du seed, et poser la seule liste de
    l'unite echoue EN SILENCE au build, cf. #27-r5).

Grappe d'ennemis en LIGNE, lue au `boardGraph` (porte d'elevation comprise) :
    T = (3,1)  cible principale       -> vague 1
    V = (3,2)  voisin de T            -> vague 2
    W = (3,3)  voisin de V, PAS de T  -> vague 3
    F = (0,1)  temoin, loin de tout   -> aucune vague
Une geometrie a 3 anneaux est ce qui rend les trois batchs SEPAREMENT observables : les trois
plages de degat de la config different (1093 : 1109-1385 / 1662-1939 / 2770-3878), donc un port qui
raterait une vague, ou qui melangerait deux bases, se voit sur les VALEURS et pas seulement sur le
compte.

BRAS
----
  plain        : aucun trait pose                -> facteur 1 partout, pour les DEUX abilities
  summon_T     : T porte `Summon`                -> 1093 : x2 sur les TROIS vagues (V et W ne sont
                                                    PAS des summons -- c'est le quirk) ; 1035 : x1
  summon_V     : V porte `Summon`, T non         -> 1093 : x1 PARTOUT, y compris sur V lui-meme
                                                    (le trait de l'unite frappee n'entre pas)
  wide         : geometrie DERIVEE du boardGraph -> DEUX unites en vague 2, une en vague 3
                                                    (4 events). GENERALISATION de la multiplicite :
                                                    les trois bras `line` ne peuplent jamais une
                                                    vague de plus d'une unite.

MUTATIONS ADVERSARIALES (le port, pas le natif)
-----------------------------------------------
  waves  : `_MAKE_DMG_EXTRA_EVENTS` vide pour 1035/1093 -> retour a UN event  => ROUGE partout
  summon : `wave_damage_formula` rend toujours l'avg nue                      => ROUGE sur summon_T
                                                                                 SEUL (deborde zero)
  quirk  : le `HasTrait` porte sur l'unite FRAPPEE au lieu de la cible        => ROUGE sur summon_T
                                                                                 ET summon_V

Usage (depuis scripts/python, ASCII only) :
    python probe_27_r5_r1_plague_wind_prediction.py --all
    python probe_27_r5_r1_plague_wind_prediction.py --arm plain
    python probe_27_r5_r1_plague_wind_prediction.py --dispose
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_27r5r1_plague_wind.json"
STATE = LOGS / "rs_27r5r1_plague_wind.json"
BOARD = "MC1_67"
SEED = 909

PW = int(ActiveAbilityType.PlagueWind)                    # 1035 = 0x40b
MPW = int(ActiveAbilityType.MortarionsPlagueWind)         # 1093 = 0x445

CASTER_PW = "deathTyphus"          # porteur NATIF de 1035 (pool)
CASTER_MPW = "deathBlightlord"     # porteur GREFFE de 1093 (pool, meme faction)
P_UNITS = "%s,%s" % (CASTER_PW, CASTER_MPW)

TGT = "necroWarden"                # T -- cible principale (vague 1)
SEC = "astraBullgryn"              # V -- vague 2
TER = "orksWarboss"                # W -- vague 3
FAR = "astraPrimarisPsy"           # F -- temoin hors de toute vague
A_UNITS = "%s,%s,%s,%s" % (TGT, SEC, TER, FAR)

T = (3, 1)
V = (3, 2)
W = (3, 3)
F = (0, 1)
LINE_LAYOUT = {TGT: T, SEC: V, TER: W, FAR: F}

# Champs compares event par event -- les MEMES que #305 (`probe_305_massdriver_splash`).
CMP_KEYS = ("appliedHits", "healthDmgMin", "healthDmgMax", "rawHealthDmgMin", "rawHealthDmgMax")

# Un bras = une GEOMETRIE + un patch `BC.Units[].Traits` sur UNE unite (`None` = aucun patch).
#   `line` : la grappe en ligne ci-dessus -- UNE unite par vague (1/1/1), 3 events.
#   `wide` : geometrie DERIVEE du `boardGraph` vivant -- DEUX unites en vague 2, une en vague 3
#            (1/2/1), 4 events. C'est la generalisation de la MULTIPLICITE : les trois bras `line`
#            ne verifient jamais qu'une vague peuple plus d'un event, ni que la vague 3 se derive
#            de PLUSIEURS ancres.
#   `relief` : la PORTE D'ELEVATION. `T` + une unite sur une tuile hex-voisine de `T` mais
#              **GATEE** (`|dElev| >= 2`, donc ABSENTE du voisinage natif) + une unite sur un
#              voisin NATIF. Attendu : **2 events** (T et le voisin natif), l'unite gatee n'entrant
#              dans AUCUNE vague. Un port qui lirait la geometrie hex NUE en rendrait 3.
ARMS = {"plain": {"layout": "line", "patch": None},
        "summon_T": {"layout": "line", "patch": (TGT, ["Summon"])},
        "summon_V": {"layout": "line", "patch": (SEC, ["Summon"])},
        "wide": {"layout": "wide", "patch": None},
        "relief": {"layout": "relief", "patch": None}}

# Nombre d'events attendu par bras (identique pour les deux abilities : le SET ne depend pas de
# l'ability, seules les BASES en dependent).
EXPECT_EVENTS = {"plain": 3, "summon_T": 3, "summon_V": 3, "wide": 4, "relief": 2}


def _run(args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                          capture_output=True, text=True, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- aucun id n'est jamais code en dur."""
    return {u["visualId"]: (u["id"], (u["pos"]["col"], u["pos"]["row"]))
            for u in (_dv(rid).get("units") or []) if u.get("pos")}


def write_graft_seed_bc() -> None:
    """1093 sur `deathBlightlord`. DEUX ecritures, dont une dont l'oubli est SILENCIEUX au build :
    la config d'ability (absente des `BC.Abilities.ActiveAbilities` du seed) ET la liste de l'unite.
    `catalog_inject.write_grafted_seed_bc(kind="active")` fait les deux (cf. #27-r5, meme verrou
    que #226)."""
    import catalog_inject as C
    LOGS.mkdir(parents=True, exist_ok=True)
    _p, reports = C.write_grafted_seed_bc(SEED_BC, ["%s:MortarionsPlagueWind" % CASTER_MPW],
                                          kind="active")
    import probe_380_seed_bc_patch_survival as S
    S.assert_survives(str(SEED_BC))
    for r in reports:
        print("[graft] %s.ActiveAbilities %s -> %s (configAdded=%s)"
              % (r["unitId"], r["activeAbilitiesBefore"], r["activeAbilitiesAfter"],
                 r["configAdded"]))


def build(arm: str) -> int:
    write_graft_seed_bc()
    cmd = ["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
           "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
           # PV HAUTS : aucun event ne doit etre CAPE par les PV restants de sa cible, sinon les
           # trois bases se confondent au plafond et le bras ne mesure plus la base.
           "--hp-target", "400000",
           # Les deux casters sont FIGES : `Movement=0` fixe la tuile d'attaque (une seule), donc
           # le meme `casterPosition` des deux cotes, et aucune migration de spawn entre les bras.
           "--unit-stat", "%s:Movement=0" % CASTER_PW,
           "--unit-stat", "%s:Movement=0" % CASTER_MPW,
           "--state-file", str(STATE)]
    patch = ARMS[arm]["patch"]
    if patch is not None:
        vid, traits = patch
        # `--unit-stat` separe les CHAMPS par une virgule : le JSON ne doit pas en contenir.
        cmd += ["--unit-stat", "%s:Traits=%s" % (vid, json.dumps(traits, separators=(",", ":")))]
    prev = _runner_id() if STATE.exists() else None
    cp = _run(cmd)
    if not STATE.exists():
        raise SystemExit("build KO:\n%s\n%s" % (cp.stdout[-2000:], cp.stderr[-2000:]))
    rid = _runner_id()
    if prev is not None and rid == prev:
        raise SystemExit("build KO (runner %d re-servi) :\n%s" % (rid, cp.stdout[-2000:]))
    return rid


def dispose() -> None:
    if STATE.exists():
        _run(["dispose", "--state-file", str(STATE), "--runner", str(_runner_id())])
        print("[dispose] runner du state-file libere")


def wide_layout(rid: int) -> dict:
    """Geometrie DERIVEE du `boardGraph` vivant : `T` + **DEUX** voisins de `T` (vague 2) + un
    voisin de l'un d'eux qui n'est PAS voisin de `T` (vague 3).

    L'adjacence lue est celle du `boardGraph` (`tiles[].neighbours`), c.-a-d. celle
    d'`IterateAdjacentTiles` avec sa porte d'elevation -- jamais `hexgeo`, qui ignore l'elevation
    et rangerait dans une vague une tuile que le natif exclut. Meme voie que #305.

    Les tuiles des DEUX casters sont bannies : ils ne bougent pas (`Movement=0`) et un `act move`
    vers une tuile occupee echouerait, ce que `_assert_placed` transformerait en arret -- mais
    autant ne pas les proposer."""
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    tiles = bg.get("tiles") or []
    by_id = {t.get("id"): t for t in tiles}
    by_pos = {(t.get("col"), t.get("row")): t for t in tiles}
    u = _units(rid)
    banned = {u[CASTER_PW][1], u[CASTER_MPW][1], T}
    ttile = by_pos.get(T)
    if ttile is None:
        raise SystemExit("tuile T=%s absente du boardGraph" % (T,))

    def _free_neighbours(tile, extra_banned=frozenset()) -> list:
        out = []
        for i in (tile.get("neighbours") or []):
            t = by_id.get(i)
            if t is None or not t.get("walkable"):
                continue
            p = (t.get("col"), t.get("row"))
            if p in banned or p in extra_banned:
                continue
            out.append(p)
        return sorted(out)

    ring1 = _free_neighbours(ttile)
    if len(ring1) < 2:
        raise SystemExit("T=%s n'a que %d voisin(s) walkable libre(s) : le bras `wide` exige 2 "
                         "unites en vague 2 -- changer de board/seed" % (T, len(ring1)))
    v1, v2 = ring1[0], ring1[1]
    # La vague 3 = adjacent a un SECONDAIRE et PAS a la cible : on bannit tout l'anneau 1.
    ring2 = _free_neighbours(by_pos[v1], extra_banned=set(ring1))
    if not ring2:
        raise SystemExit("aucun voisin de %s hors de l'anneau 1 de T : pas de vague 3" % (v1,))
    return {TGT: T, SEC: v1, TER: v2, FAR: ring2[0]}


def board_graph(rid: int) -> tuple:
    """`(by_id, by_pos)` du `boardGraph` vivant."""
    tiles = (L._rpc("boardGraph", [{"runnerId": rid}]).get("tiles") or [])
    return ({t.get("id"): t for t in tiles},
            {(t.get("col"), t.get("row")): t for t in tiles})


def gated_edges(rid: int) -> list:
    """Les aretes hex-voisines ABSENTES du champ brut `boardGraph.neighbours` -- c.-a-d. celles que
    la porte `|dElev| < 2` de `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` REFUSE.

    Le capteur du `boardGraph` passe par ce meme `IterateAdjacentTiles` : la porte est donc deja
    CUITE dans le champ, et c'est par la -- pas par `DslContext.elev_by_pos` -- qu'elle entre dans
    `AdjacentTiles` (`Board.neighbours_native`). Cette fonction MESURE ce fait au lieu de le
    supposer : elle rend les aretes refusees ET leur `dElev`, ce qui permet d'assurer qu'AUCUNE
    n'est refusee sous 2 (le refus serait alors autre chose que l'elevation)."""
    import hexgeo
    by_id, by_pos = board_graph(rid)
    out = []
    for p, t in by_pos.items():
        nat = {by_id[i]["id"] for i in (t.get("neighbours") or []) if i in by_id}
        for q, u in by_pos.items():
            if hexgeo.distance(p, q) == 1 and u.get("id") not in nat:
                out.append({"a": p, "b": q, "elev_a": t.get("elevation"),
                            "elev_b": u.get("elevation"),
                            "d_elev": abs((t.get("elevation") or 0) - (u.get("elevation") or 0)),
                            "walkable": bool(t.get("walkable") and u.get("walkable"))})
    return out


def relief_layout(rid: int) -> dict:
    """Le bras qui fait MORDRE la porte d'elevation, DERIVE du `boardGraph` vivant.

    On cherche un triplet `(T, G, K)` ou :
      * `G` est hex-voisine de `T` mais **GATEE** (absente du voisinage natif de `T`) et walkable ;
      * `K` est un voisin **NATIF** walkable de `T` ;
      * `G` n'est PAS non plus voisin natif de `K` -- sans quoi elle rentrerait par la vague 3 et
        le bras cesserait de discriminer (le compte redeviendrait le meme des deux cotes).
    Le 4e mannequin est parque LOIN (distance >= 3 de `T`, donc hors de toute vague).

    Attendu : `t1 = {T}`, `t2 = {K}`, `t3 = {}` -> **2 events**. Un port qui lirait la geometrie
    hex NUE mettrait `G` en vague 2 et en rendrait 3."""
    import hexgeo
    by_id, by_pos = board_graph(rid)
    u = _units(rid)
    banned = {u[CASTER_PW][1], u[CASTER_MPW][1]}

    def _nat(p) -> set:
        return {(by_id[i]["col"], by_id[i]["row"]) for i in (by_pos[p].get("neighbours") or [])
                if i in by_id}

    def _hex(p) -> set:
        return {q for q in by_pos if hexgeo.distance(p, q) == 1}

    for tp in sorted(by_pos):
        if not by_pos[tp].get("walkable") or tp in banned:
            continue
        gates = sorted(g for g in (_hex(tp) - _nat(tp))
                       if by_pos[g].get("walkable") and g not in banned)
        if not gates:
            continue
        for g in gates:
            for k in sorted(_nat(tp)):
                if k in banned or k == g or not by_pos[k].get("walkable") or g in _nat(k):
                    continue
                far = sorted(q for q in by_pos
                             if by_pos[q].get("walkable") and q not in banned
                             and q not in (tp, g, k) and hexgeo.distance(q, tp) >= 3)
                if not far:
                    continue
                return {TGT: tp, SEC: g, TER: k, FAR: far[0]}
    raise SystemExit("aucun triplet (T, voisin GATE, voisin natif) sur ce board : la porte "
                     "d'elevation n'y est pas exercable -- changer de board")


def layout_for(rid: int, arm: str) -> dict:
    kind = ARMS[arm]["layout"]
    if kind == "line":
        return LINE_LAYOUT
    return wide_layout(rid) if kind == "wide" else relief_layout(rid)


def place(rid: int, layout: dict) -> None:
    u = _units(rid)
    for vid, to in layout.items():
        if vid not in u:
            raise SystemExit("unite %r absente du runner" % vid)
        _run(["act", "move", "--unit", str(u[vid][0]), "--to", "%d,%d" % to,
              "--state-file", str(STATE), "--runner", str(rid)])
    got = {v: p for v, (_i, p) in _units(rid).items()}
    bad = [(v, to, got.get(v)) for v, to in layout.items() if got.get(v) != to]
    if bad:
        # Un `act move` REFUSE ne leve rien (`rl_duel` rend `ok=False` sur une unite adverse alors
        # que le deplacement EST applique) : seule la position RELUE fait foi.
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s" % bad)


def _native_events(rid: int, cid: int, tid: int, ability: int, tile) -> list:
    """`aiPlaybookPredict` = `<X>Playbook$$MakeDamagePredictions` NATIF depuis `tile`."""
    r = L._rpc("aiPlaybookPredict", [{"runnerId": rid, "unitId": cid, "targetId": tid,
                                      "abilityType": ability,
                                      "col": int(tile[0]), "row": int(tile[1])}])
    if not r.get("ok"):
        raise SystemExit("aiPlaybookPredict KO (ability %d) : %r" % (ability, r))
    return r.get("events") or []


def _nat_fields(ev: dict) -> dict:
    hp = ev.get("hpBefore") or 0
    return {"appliedHits": ev.get("appliedHits") or 0,
            "healthDmgMin": min(ev.get("healthDmgMin") or 0, hp),
            "healthDmgMax": min(ev.get("healthDmgMax") or 0, hp),
            "rawHealthDmgMin": ev.get("willKillDmg") or 0,
            "rawHealthDmgMax": ev.get("mightKillDmg") or 0}


def _by_target(rows: list) -> dict:
    out: dict = {}
    for tid, f in rows:
        out.setdefault(tid, []).append(f)
    return out


def _ctx_for(rid: int, cid: int):
    """`AiDecisionContext` du caster sur le runner vivant (meme couture qu'`engine_validate`)."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    sid = L.INV._session_id()

    def rpc(m, b, t):
        return EV._r(sid, m, b, t)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(rpc, rid)
    return AICTX.build(rpc, rid, dv, mov_by_unit, cid, W.load(), predictor)


def confront(rid: int, ctx, cid: int, tid: int, ability: int, tile) -> dict:
    """Confronte la LISTE ENTIERE d'events (les trois vagues), par cible et par champ."""
    from engine.playbook import get_playbook_or_default
    nat = _by_target([(e.get("targetId"), _nat_fields(e))
                      for e in _native_events(rid, cid, tid, ability, tile)])
    pb = get_playbook_or_default(ability)
    off_evs = pb.make_damage_predictions(ctx, tile, tid, ability) or []
    off = _by_target([(e.target, {k: e.composite_fields().get(k) for k in CMP_KEYS})
                      for e in off_evs])
    deltas, missing, extra = [], [], []
    for t, nevs in nat.items():
        oevs = off.get(t)
        if not oevs:
            missing.append(t)
            continue
        if len(oevs) != len(nevs):
            deltas.append({"target": t, "field": "n_events", "nat": len(nevs), "off": len(oevs)})
        for nf, of in zip(nevs, oevs):
            for k in CMP_KEYS:
                if nf.get(k) != of.get(k):
                    deltas.append({"target": t, "field": k, "nat": nf.get(k), "off": of.get(k)})
    for t in off:
        if t not in nat:
            extra.append(t)
    return {"nat": nat, "off": off, "deltas": deltas, "missing": missing, "extra": extra,
            "match": not deltas and not missing and not extra}


def _label(u: dict, tid) -> str:
    for vid, (uid, _p) in u.items():
        if uid == tid:
            return vid
    return str(tid)


def measure(rid: int, verbose: bool = True) -> dict:
    """Mesure les DEUX abilities sur l'etat courant du runner."""
    u = _units(rid)
    tid = u[TGT][0]
    out = {}
    for ability, caster_vid in ((PW, CASTER_PW), (MPW, CASTER_MPW)):
        cid, tile = u[caster_vid]
        ctx = _ctx_for(rid, cid)
        res = confront(rid, ctx, cid, tid, ability, tile)
        out[ability] = res
        if verbose:
            print("  [%d %s] caster=%s@%s cible=%s  match=%s"
                  % (ability, caster_vid, cid, tile, tid, res["match"]))
            for t in sorted(res["nat"], key=lambda x: (x is None, x)):
                for i, nf in enumerate(res["nat"][t]):
                    of = (res["off"].get(t) or [{}])[i] if i < len(res["off"].get(t) or []) else {}
                    print("     -> %-20s nat hits=%s dmg=[%s,%s] raw=[%s,%s] | port hits=%s "
                          "dmg=[%s,%s] raw=[%s,%s]"
                          % (_label(u, t), nf["appliedHits"], nf["healthDmgMin"],
                             nf["healthDmgMax"], nf["rawHealthDmgMin"], nf["rawHealthDmgMax"],
                             of.get("appliedHits"), of.get("healthDmgMin"),
                             of.get("healthDmgMax"), of.get("rawHealthDmgMin"),
                             of.get("rawHealthDmgMax")))
            if not res["match"]:
                print("     DELTAS=%s missing=%s extra=%s"
                      % (res["deltas"][:8], res["missing"], res["extra"]))
    return out


# ---------------------------------------------------------------- mutations adversariales
def _mutate(kind: str):
    """Mute le PORT (jamais le natif) et rend le callable de restauration."""
    from engine.playbook.prediction import abilities as PA
    from engine.playbook.prediction import plague_wind as PWM
    if kind == "waves":
        saved = {a: PA._MAKE_DMG_EXTRA_EVENTS.pop(a) for a in (PW, MPW)}
        return lambda: PA._MAKE_DMG_EXTRA_EVENTS.update(saved)
    if kind == "summon":
        orig = PWM.wave_damage_formula

        def _bare(ability_id, mn, mx):
            return PWM.min_max_damage_average(mn, mx)
        PWM.wave_damage_formula = _bare

        def _restore():
            PWM.wave_damage_formula = orig
        return _restore
    if kind == "quirk":
        # LA LECTURE NAIVE, celle que le decompile refute : le `HasTrait` porterait sur l'unite
        # FRAPPEE. On ne peut pas l'exprimer en changeant l'ARBRE (le sujet du `HasTrait` natif est
        # le selecteur `Target`) -- il faut deplacer l'EVALUATION dans la boucle, avec l'unite
        # frappee comme `target` du contexte. C'est exactement le second etage de la structure
        # native : `GenerateMultiHitAttackPredictions` evalue sa formule UNE FOIS, HORS boucle.
        orig = PWM.wave_events

        def _per_hit(scene, caster_id, target_id, ability_id, ability_name, attack_pos, ab, cfg):
            from engine.playbook.prediction.abilities import generate_multi_hit_attack_prediction
            from engine.runner.abilities.deathguard import plague_wind_wave_selectors
            from engine.playbook.probable_damage_event import ProbableDamageEvent
            if cfg is None or ab is None:
                return []
            hits = int((cfg.constants or {}).get(PWM.HITS_CONST) or 0)
            dctx = PWM.dsl_context(scene, caster_id, target_id)
            if not hits or dctx is None or dctx.target is None:
                return []
            _t1, t2, t3 = plague_wind_wave_selectors()
            evs = []
            for wave, sel in ((1, t2), (2, t3)):
                for u in sel.evaluate(dctx):
                    tid = (u or {}).get("id")
                    if tid is None:
                        continue
                    hit_ctx = PWM.dsl_context(scene, caster_id, tid)      # <-- LA MUTATION
                    base = PWM._wave_base(int(ability_id), ab, cfg, wave, hit_ctx)
                    if base <= 0:
                        continue
                    dp = generate_multi_hit_attack_prediction(
                        scene, caster_id, tid, ability_id, ability_name, attack_pos=attack_pos,
                        base_override=base, hits_override=hits)
                    if dp is not None:
                        evs.append(ProbableDamageEvent(target=tid, prediction=dp))
            return evs
        PWM.wave_events = _per_hit

        def _restore():
            PWM.wave_events = orig
        return _restore
    if kind == "hexgeo":
        # LA PORTE D'ELEVATION, desarmee. `AdjacentTiles` lit `Board.neighbours_native` = le champ
        # BRUT `boardGraph.neighbours`, dont le capteur passe par
        # `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` -- lequel applique
        # `|dElev| < 2` INCONDITIONNELLEMENT. La porte est donc CUITE dans le canal, et non lue par
        # `DslContext.elev_by_pos` (qu'`AdjacentTiles` ne consulte pas). On la desarme en rendant la
        # geometrie hex NUE : si le port etait aveugle a l'elevation, c'est CE resultat qu'il
        # produirait -- et il doit rougir sur `relief`.
        import hexgeo
        from engine.entities.pathfinding.board import Board
        orig = Board.neighbours_native

        def _pure_hex(self, tid):
            src = self.by_id.get(tid)
            if src is None:
                return orig(self, tid)
            p = (src.get("col"), src.get("row"))
            return [i for i, t in self.by_id.items()
                    if hexgeo.distance(p, (t.get("col"), t.get("row"))) == 1]
        Board.neighbours_native = _pure_hex

        def _restore():
            Board.neighbours_native = orig
        return _restore
    raise SystemExit("mutation inconnue : %r" % kind)


EXPECT_MUTATION = {
    # mutation -> {bras: doit ROUGIR ?}. Une mutation qui ne rougit NULLE PART ne garde rien ;
    # une qui rougit PARTOUT ne discrimine pas ce qu'elle pretend garder.
    "waves": {"plain": True, "summon_T": True, "summon_V": True, "wide": True, "relief": True},
    "summon": {"plain": False, "summon_T": True, "summon_V": False, "wide": False,
               "relief": False},
    "quirk": {"plain": False, "summon_T": True, "summon_V": True, "wide": False, "relief": False},
    # La porte d'elevation ne MORD que la ou une unite est posee sur une tuile GATEE : c'est le
    # bras `relief`, et lui seul. Verte ailleurs = la mutation ne fabrique pas un rouge global.
    "hexgeo": {"plain": False, "summon_T": False, "summon_V": False, "wide": False, "relief": True},
}


def elevation_profile(rid: int, layout: dict) -> dict:
    """Le PROFIL D'ELEVATION du montage : l'elevation de chaque tuile posee et le `dElev` de chaque
    arete hex du montage. Sans lui, un accord VERT ne dit RIEN sur la porte d'elevation -- il peut
    tenir simplement parce qu'aucune arete du montage n'a d'ecart. On l'IMPRIME donc, toujours."""
    import hexgeo
    _by_id, by_pos = board_graph(rid)
    elev = {vid: by_pos.get(p, {}).get("elevation") for vid, p in layout.items()}
    edges = []
    items = sorted(layout.items())
    for i, (va, pa) in enumerate(items):
        for vb, pb in items[i + 1:]:
            if hexgeo.distance(pa, pb) == 1:
                edges.append({"a": va, "b": vb,
                              "d_elev": abs((elev[va] or 0) - (elev[vb] or 0))})
    return {"elev": elev, "hex_edges": edges,
            "max_d_elev": max([e["d_elev"] for e in edges], default=0)}


def run_arm(arm: str, mutations: bool = True) -> dict:
    rid = build(arm)
    layout = layout_for(rid, arm)
    place(rid, layout)
    prof = elevation_profile(rid, layout)
    print("[bras %s] runner=%d layout=%s" % (arm, rid, layout))
    print("          elevation=%s aretes-hex=%s  max|dElev|=%d%s"
          % (prof["elev"], [(e["a"], e["b"], e["d_elev"]) for e in prof["hex_edges"]],
             prof["max_d_elev"],
             "  <- une arete du montage est GATEE" if prof["max_d_elev"] >= 2 else ""))
    base = measure(rid)
    ok = all(r["match"] for r in base.values())
    n_ok = all(sum(len(v) for v in r["nat"].values()) == EXPECT_EVENTS[arm]
               for r in base.values())
    ok = ok and n_ok
    print("[bras %s] ACCORD natif<->port : %s | events attendus %d : %s"
          % (arm, "OK" if ok else "KO", EXPECT_EVENTS[arm], "OK" if n_ok else "KO"))
    muts = {}
    if mutations:
        for kind, per_arm in sorted(EXPECT_MUTATION.items()):
            restore = _mutate(kind)
            try:
                red = not all(r["match"] for r in measure(rid, verbose=False).values())
            finally:
                restore()
            want = per_arm[arm]
            muts[kind] = {"red": red, "want": want, "ok": red == want}
            print("  [mutation %-6s] rouge=%s (attendu %s) %s"
                  % (kind, red, want, "OK" if red == want else "KO"))
    return {"arm": arm, "rid": rid, "ok": ok, "base": base, "mutations": muts, "layout": layout,
            "elevation": prof, "gated_edges": gated_edges(rid)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-mutations", action="store_true")
    ap.add_argument("--dispose", action="store_true")
    a = ap.parse_args()
    if a.dispose:
        dispose()
        return 0
    arms = sorted(ARMS) if a.all else ([a.arm] if a.arm else ["plain"])
    ok = True
    for arm in arms:
        r = run_arm(arm, mutations=not a.no_mutations)
        ok = ok and r["ok"] and all(m["ok"] for m in r["mutations"].values())
    print("VERDICT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
