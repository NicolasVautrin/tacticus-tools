#!/usr/bin/env python
"""#119 — face DECISION de `SupremeCommanderPlaybook` (1028) CONFRONTEE a l'IA NATIVE.

ORACLE = la decision de l'IA native elle-meme : `CalculateNextActionForUnit` (RPC
`aiDryRunAllUnits`, read-only, `mutated=false` verifie), doublee d'un TOUR REELLEMENT JOUE
(`playTurn`) sur le scenario nominal. JAMAIS `aiPredict`/`GetAllPredictions` (preview du seul
vecteur Attack — cf. feedback_aipredict_preview_not_playbook_oracle).

`IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$ShouldEvaluate` :
  (1) `BasePlaybook.EnemyWillBeKilledWithNormalAttack(this, unit)` -> True = ABSTENTION
  (2) `Any(u in baseSelector@+0x80 + AllDeadUnits() : IsFriendlyKell(u, unit))` -> False = ABSTENTION
      `IsFriendlyKell` = `u.GetComponent<ChildComponent>().ParentId(+0x10) == EntityId(unit)`
      `&& UnitExtensions.IsFriend(u, unit)`
  (3) tirage `IRandom.Chance(1/2 + FillUpStat(unit, 5=Health).RemainingPercentage / 2)`
      -> a PV PLEINS la chance vaut 1 : etage DETERMINISTE (verifie ici, N tirages d'affilee)

SCENARIOS (geometrie PILOTEE — les unites sont deplacees, pas subies ; le rendez-vous est DERIVE du
`boardGraph`, donc le montage vaut pour n'importe quel board) :
  A  gate (2) VRAI   : Kell en jeu, Creed PV pleins, ennemis increvables -> natif CASTE 1028
                       (MC1_67 / seed 4242)
  B  gate (2) FAUX   : meme build, Creed jamais attaque -> pas de Kell -> natif S'ABSTIENT
  C  gate (2) EQUIPE : DEUX Creed (un par camp) ; seul le camp ADVERSE a un Kell.
                       MON Creed s'abstient, LE SIEN caste -> le filtre `IsFriend` est EXERCE
                       (une regle naive « un Kell existe sur le plateau » se tromperait ici)
  D  gate (1) VRAI   : Kell en jeu MAIS un ennemi sure-kill a l'attaque normale -> ABSTENTION
  A2 generalisation  : A rejoue sur un AUTRE couple (board C3_01 / seed 777)
  E  etage (3)       : MESURE (non bloquante) de la frequence de cast a PV REDUITS

Chaque scenario compare, sur le MEME etat, le natif et `engine_decide` (le port).
Usage : python probe_119_supreme_commander_decision.py [--keep]
ASCII only (cp1252). Rend 0 si tous les scenarios concordent.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc    # noqa: E402

ABILITY = 1028
CREED = "astraCreed"
KELL = "astraSmnKell"
ALLY = "astraBullgryn"
FOE = "necroSpyder"
FOE2 = "necroWarden"
BOARD = "MC1_67"
PYDIR = Path(__file__).resolve().parent


def r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


class Drv:
    """Pilotage RPC d'un runner — les DEUX camps (`applyAction` ne verifie pas la propriete)."""

    def __init__(self, sid, rid):
        self.sid, self.rid = sid, rid

    def view(self):
        return r(self.sid, "decisionView",
                 {"runnerId": self.rid, "allAbilities": True, "maxRank": 32}, 180)

    def units(self):
        return self.view().get("units") or []

    def act(self, action, t=120):
        return r(self.sid, "applyAction", {"runnerId": self.rid, "action": action}, t)

    def move(self, uid, col, row):
        return self.act({"kind": "move", "unitId": uid, "to": {"col": col, "row": row}})

    def endturn(self):
        return self.act({"kind": "endturn"})

    def owner_of(self, team, dv=None):
        dv = dv or self.view()
        return next((u.get("owner") for u in dv["units"] if u.get("team") == team), None)

    def ensure_turn(self, team, max_end=6):
        """Rend la main a `team` (endturn tant que ce n'est pas son tour).

        INDISPENSABLE : `endturn` clot le tour de l'equipe COURANTE, et une equipe dont toutes les
        unites ont deja agi termine SEULE -> un `endturn` de plus inverse la parite et le reste du
        scenario se joue au mauvais tour (mesure : ennemi bouge ses 2 unites -> auto-fin -> mon
        `endturn` cloturait MON tour). On ne compte donc jamais les tours : on VERIFIE le joueur."""
        want = self.owner_of(team)
        for _ in range(max_end):
            dv = self.view()
            if dv.get("currentPlayer") == want:
                return True
            self.endturn()
        return self.view().get("currentPlayer") == want

    def cast(self, caster, target, ability):
        return self.act({"kind": "ability", "casterId": caster, "targetId": target,
                         "abilityType": ability})

    def normal_id(self, uid, dv=None):
        dv = dv or self.view()
        u = next((x for x in dv["units"] if x["id"] == uid), None)
        if u is None:
            return None
        a = next((a for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)
        return a and a.get("id")

    def in_range(self, uid, tgt, ab):
        at = r(self.sid, "abilityTargets",
               {"runnerId": self.rid, "unitId": uid, "abilityType": ab}, 40)
        for uu in (at.get("units") or []):
            if uu.get("unitId") != uid:
                continue
            for a in (uu.get("abilities") or []):
                if a.get("abilityId") == ab:
                    return any(t.get("targetId") == tgt for t in (a.get("fromHere") or []))
        return False

    def step_toward(self, uid, dest):
        """Un pas de rapprochement de `uid` vers `dest` (tuiles legales du tour courant)."""
        mov = r(self.sid, "aiMovableTiles", {"runnerId": self.rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == uid), None)
        cur = next((u for u in self.units() if u["id"] == uid), None)
        if mu is None or cur is None:
            return False
        d0 = hexgeo.distance(upos(cur), dest)
        best = None
        for t in (mu.get("tiles") or []):
            if t.get("col") is None:
                continue
            d = hexgeo.distance((t["col"], t["row"]), dest)
            if best is None or d < best[0]:
                best = (d, (t["col"], t["row"]))
        if best is None or best[0] >= d0:
            return False
        self.move(uid, best[1][0], best[1][1])
        return True

    def id_of(self, vis, team=None, dv=None):
        dv = dv or self.view()
        for u in dv["units"]:
            if u.get("visualId") == vis and (team is None or u.get("team") == team):
                return u["id"]
        return None


_CAP_MARKER = "runner cap reached"


def build(sid, seed, p_units, a_units, extra, tag, board=BOARD):
    """Build ISOLE (state-file propre a CE probe + PID). Au cap `MAX_RUNNERS` sature on ATTEND
    qu'un slot se libere (les autres agents disposent au fil de l'eau) plutot que d'echouer —
    meme discipline que `tests/conftest.py::build_runner`."""
    st = Path(tempfile.gettempdir()) / f"probe119_{tag}_{__import__('os').getpid()}.json"
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(st),
            "--board", board, "--p-units", p_units, "--a-units", a_units, *extra]
    out = ""
    waited = 0.0
    while True:
        st.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (p.stderr or p.stdout or "")
        if st.exists():
            return json.loads(st.read_text())["runnerId"], st
        if _CAP_MARKER not in out or waited >= 300:
            raise RuntimeError("build KO: " + out[-400:])
        __import__("time").sleep(15)
        waited += 15


def native_proposal(sid, rid, uid):
    """Action proposee par l'IA NATIVE pour `uid` contre l'etat COURANT (read-only)."""
    res = r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 180)
    if not res.get("ok"):
        raise RuntimeError("aiDryRunAllUnits KO: " + str(res)[:300])
    if res.get("mutated"):
        raise RuntimeError("aiDryRunAllUnits a MUTE l'etat -> oracle invalide")
    row = next((u for u in (res.get("units") or []) if u.get("unitId") == uid), None)
    ab = tgt = mv = None
    for m in ((row or {}).get("proposed") or []):
        if m.get("cls") == "ActiveAbilityMessage" and ab is None:
            ab, tgt = m.get("abilityType"), m.get("targetId")
        elif m.get("cls") == "MoveUnitMessage" and mv is None:
            to = m.get("to") or {}
            mv = (to.get("col"), to.get("row"))
    return {"ability": ab, "target": tgt, "move": mv, "present": row is not None}


def port_proposal(sid, rid, uid):
    """Decision du PORT sur le MEME etat (`engine_decide` = spine natif porte)."""
    import engine_validate as EV
    from engine import weights
    from engine.playbook import scene as _scene
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: r(sid, m, b, t), rid)
    return EV.engine_decide(sid, rid, dv, mov_by_unit, uid, weights.load(), predictor)


def port_gates(sid, rid, uid):
    """Etat des gates du port pour 1028 (diagnostic par ETAGE, pas un oracle)."""
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook.noncomparable.hammer_of_wrath import _enemy_killed_by_normal_attack
    from engine import weights
    from engine.playbook import scene as _scene
    dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: r(sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: r(sid, m, b, t), rid, dv, mov_by_unit, uid,
                      weights.load(), predictor)
    nc = PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)
    pb = PB.playbook_for(ABILITY)
    return {"gate1_enemy_sure_kill": bool(_enemy_killed_by_normal_attack(nc)),
            "gate2_friendly_child": bool(pb._has_friendly_kell(nc)),
            "should_evaluate": bool(pb.should_evaluate(nc))}


def confront(tag, sid, rid, uid, expect_cast):
    """UN point de confrontation : rend le RECORD (natif, port, gates, verdicts) et l'imprime.

    Rend un dict (et non un booleen) pour que le test de garde puisse asserter sur la MESURE et
    afficher les deux cotes en cas d'echec."""
    nat = native_proposal(sid, rid, uid)
    eng = port_proposal(sid, rid, uid)
    g = port_gates(sid, rid, uid)
    nat_cast = nat["ability"] == ABILITY
    eng_cast = eng.get("kind") == "ability" and eng.get("ability") == ABILITY
    same_target = (not nat_cast) or (eng.get("target") == nat["target"])
    rec = {"tag": tag, "uid": uid, "native": nat, "engine": eng, "gates": g,
           "expect_cast": expect_cast, "native_cast": nat_cast, "port_cast": eng_cast,
           "same_target": same_target,
           "ok": (nat_cast == expect_cast) and (eng_cast == nat_cast) and same_target}
    print("[%s] u%s natif(ab=%s tgt=%s move=%s) | port(%s ab=%s tgt=%s to=%s)"
          % (tag, uid, nat["ability"], nat["target"], nat["move"],
             eng.get("kind"), eng.get("ability"), eng.get("target"), eng.get("to")))
    print("       gates port %s | attendu-natif=%s natif=%s port=%s -> %s"
          % (json.dumps(g), expect_cast, nat_cast, eng_cast, "OK" if rec["ok"] else "DESACCORD"))
    return rec


def hp_frac(sid, rid, uid):
    ob = r(sid, "observeBattle", {"runnerId": rid}, 40)
    u = next((x for x in (ob.get("units") or []) if x.get("squadId") == uid), None)
    if not u or not u.get("hpMax"):
        return None
    return (u.get("hp") or 0) / float(u["hpMax"])


def native_cast_rate(sid, rid, uid, n):
    """Frequence de cast 1028 sur `n` tirages NATIFS d'affilee (etage (3) = RNG)."""
    c = 0
    for _ in range(n):
        if native_proposal(sid, rid, uid)["ability"] == ABILITY:
            c += 1
    return c, n


# ------------------------------------------------------------------------------------------ #
# Scenarios
# ------------------------------------------------------------------------------------------ #

def open_tile(sid, rid, anchors, min_nbrs=6):
    """Tuile jouable a >= `min_nbrs` voisins JOUABLES, la plus proche (au pire cas) des `anchors`.

    Le rendez-vous n'est pas un detail cosmetique : `SwornProtectorAbility$$GetSpawnTile` =
    `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(cible))))` -> si la cible n'a aucun
    voisin LIBRE, Kell ne spawne pas et le scenario devient silencieusement vide (mesure : Creed
    adverse a son spawn (6,8) de MC1_67 = 2 voisins, tous deux occupes -> aucun Kell)."""
    bg = r(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    byid = {t.get("id"): t for t in tiles}
    best = None
    for t in tiles:
        if not t.get("walkable"):
            continue
        nb = [byid[n] for n in (t.get("neighbours") or []) if n in byid]
        if sum(1 for x in nb if x.get("walkable")) < min_nbrs:
            continue
        p = (t.get("col"), t.get("row"))
        cost = max(hexgeo.distance(p, a) for a in anchors) if anchors else 0
        if best is None or cost < best[0]:
            best = (cost, p)
    if best is None:
        raise RuntimeError("aucune tuile a %d voisins jouables sur ce board" % min_nbrs)
    return best[1]


def _drive_creed_faces_foe(d, sid, rid, creed, foe, max_turns=16):
    """Amene Creed sur une tuile OUVERTE (6 voisins jouables) et l'ennemi a son CONTACT.

    Pilotage explicite des DEUX camps, chaque geste precede d'un `ensure_turn` (jamais un comptage
    de tours). BOARD-AGNOSTIQUE : le rendez-vous est derive du `boardGraph`, pas code en dur."""
    pos = {u["id"]: upos(u) for u in d.units()}
    rdv = open_tile(sid, rid, [pos[creed], pos[foe]])
    for _ in range(max_turns):
        d.ensure_turn(1)
        cpos = next(upos(u) for u in d.units() if u["id"] == creed)
        if cpos != rdv:
            d.step_toward(creed, rdv)
        d.ensure_turn(2)
        cpos = next(upos(u) for u in d.units() if u["id"] == creed)
        fpos = next(upos(u) for u in d.units() if u["id"] == foe)
        if cpos == rdv and hexgeo.distance(cpos, fpos) == 1:
            return rdv
        d.step_toward(foe, cpos)
    cpos = next(upos(u) for u in d.units() if u["id"] == creed)
    fpos = next(upos(u) for u in d.units() if u["id"] == foe)
    if hexgeo.distance(cpos, fpos) != 1:
        raise RuntimeError("mise au contact impossible (creed=%s foe=%s rdv=%s)" % (cpos, fpos, rdv))
    return rdv


def scenario_A(sid, rids, board=BOARD, seed=4242, tag="A"):
    """A : Kell en jeu (SwornProtector), Creed PV pleins, ennemis increvables -> le natif CASTE."""
    rid, st = build(sid, seed, CREED, f"{FOE},{FOE2}",
                    ["--hp-player", "400000", "--hp-target", "400000"], tag, board=board)
    rids.append((rid, st))
    d = Drv(sid, rid)
    creed, foe = d.id_of(CREED), d.id_of(FOE)
    _drive_creed_faces_foe(d, sid, rid, creed, foe)
    d.cast(foe, creed, d.normal_id(foe))          # SwornProtector -> Kell
    d.ensure_turn(1)
    us = d.units()
    kell = [u for u in us if u.get("visualId") == KELL]
    hpf = hp_frac(sid, rid, creed)
    print("[%s] runner=%s board=%s seed=%s Kell=%s hp%%Creed=%.2f"
          % (tag, rid, board, seed, bool(kell), hpf))
    if not kell:
        raise RuntimeError("%s : Kell n'est pas apparu -> scenario non discriminant" % tag)
    recs = [confront("%s kell-ami" % tag, sid, rid, creed, expect_cast=True)]
    # etage (3) : a PV PLEINS (chance = 1) le tirage doit passer a TOUS les coups
    c, n = native_cast_rate(sid, rid, creed, 20)
    print("[%s] etage(3) PV pleins : %d/%d tirages natifs castent 1028" % (tag, c, n))
    # ORACLE FORT : un tour REELLEMENT joue (pas seulement le dry-run non applique)
    before = {u["id"] for u in d.units()}
    r(sid, "playTurn", {"runnerId": rid}, 240)
    spawned = sorted({u.get("visualId") for u in d.units() if u["id"] not in before})
    print("[%s] tour NATIF joue -> unite(s) apparue(s) : %s" % (tag, spawned))
    return {"records": recs, "hp_frac": hpf, "draws": (c, n), "played_turn_spawned": spawned,
            "board": board, "seed": seed}


def scenario_A2(sid, rids):
    """A' : le MEME accord sur un AUTRE couple (board, seed) — la geometrie de spawn de Kell et les
    positions dependent du board, l'accord ne doit pas en dependre (discipline de generalisation)."""
    return scenario_A(sid, rids, board="C3_01", seed=777, tag="A2")


def scenario_B(sid, rids):
    """B : meme build, Creed JAMAIS attaque -> pas d'enfant -> le natif S'ABSTIENT."""
    rid, st = build(sid, 4242, CREED, f"{FOE},{FOE2}",
                    ["--hp-player", "400000", "--hp-target", "400000"], "B")
    rids.append((rid, st))
    d = Drv(sid, rid)
    creed, foe = d.id_of(CREED), d.id_of(FOE)
    _drive_creed_faces_foe(d, sid, rid, creed, foe)
    d.ensure_turn(1)
    us = d.units()
    print("[B] runner=%s Kell=%s" % (rid, any(u.get("visualId") == KELL for u in us)))
    if any(u.get("visualId") == KELL for u in us):
        raise RuntimeError("B : un Kell est apparu -> contre-cas invalide")
    return {"records": [confront("B sans-enfant", sid, rid, creed, expect_cast=False)]}


def scenario_C(sid, rids):
    """C : DEUX Creed (un par camp) ; SEUL le camp adverse a un Kell.

    Le mien s'abstient, le SIEN caste -> le filtre `IsFriend` de `IsFriendlyKell` est EXERCE : une
    regle naive « il existe un Kell sur le plateau » rendrait True pour les deux."""
    rid, st = build(sid, 4242, f"{CREED},{ALLY}", f"{CREED},{FOE2}",
                    ["--hp-player", "400000", "--hp-target", "400000"], "C")
    rids.append((rid, st))
    d = Drv(sid, rid)
    dv = d.view()
    mine = d.id_of(CREED, team=1, dv=dv)
    theirs = d.id_of(CREED, team=2, dv=dv)
    ally = d.id_of(ALLY, team=1, dv=dv)
    if None in (mine, theirs, ally):
        raise RuntimeError("C : roster incomplet (mine=%s theirs=%s ally=%s)" % (mine, theirs, ally))
    na = d.normal_id(ally, dv)
    # RENDEZ-VOUS sur une tuile a SIX voisins jouables : `SwornProtectorAbility$$GetSpawnTile` =
    # `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(cible))))` -> sans voisin libre,
    # Kell ne spawne PAS (mesure : Creed adverse au spawn (6,8), 2 voisins, tous deux occupes ->
    # aucun Kell, contre-cas silencieusement vide).
    RDV = (4, 4)
    for _ in range(14):
        d.ensure_turn(1)                          # mon tour : l'allie approche
        if d.in_range(ally, theirs, na):
            break
        d.step_toward(ally, RDV)
        d.ensure_turn(2)                          # tour adverse : leur Creed vient au RDV
        d.step_toward(theirs, RDV)
    d.ensure_turn(1)
    tpos = upos(next(u for u in d.units() if u["id"] == theirs))
    if not d.in_range(ally, theirs, na):
        raise RuntimeError("C : l'allie n'a pas atteint le Creed adverse (lui=%s)" % (tpos,))
    d.cast(ally, theirs, na)                     # SwornProtector ADVERSE -> son Kell
    us = d.units()
    kells = [u for u in us if u.get("visualId") == KELL]
    print("[C] runner=%s Kell(s)=%s" % (rid, [(k["id"], k.get("team")) for k in kells]))
    if not kells or any(k.get("team") == 1 for k in kells):
        raise RuntimeError("C : Kell absent ou dans MON camp -> contre-cas invalide")
    recs = [confront("C mon-creed(sans enfant)", sid, rid, mine, expect_cast=False)]
    d.ensure_turn(2)                              # main au camp adverse
    recs.append(confront("C creed-adverse(avec enfant)", sid, rid, theirs, expect_cast=True))
    return {"records": recs, "kell_teams": [k.get("team") for k in kells]}


def scenario_D(sid, rids):
    """D : Kell en jeu (gate 2 VRAI) MAIS un ennemi SURE-KILL a l'attaque normale -> gate (1) -> ABSTENTION.

    Le SEUL parametre qui change vs A est les PV ennemis (`--hp-target 1`) : meme board, meme seed,
    meme geometrie de contact. C'est donc bien le gate (1) qui bascule la decision, pas la scene."""
    # 6000 PV : au-dessus de la riposte encaissee par l'attaquant (~5500 mesures) donc l'ennemi
    # SURVIT a son propre coup, et au-dessous du `dmgMin` de l'attaque normale de Creed (6102 sur
    # ce board/rank) donc il est SURE-KILL au tour suivant.
    rid, st = build(sid, 4242, CREED, f"{FOE},{FOE2}",
                    ["--hp-player", "400000", "--hp-target", "6000"], "D")
    rids.append((rid, st))
    d = Drv(sid, rid)
    dv0 = d.view()
    creed = d.id_of(CREED, dv=dv0)
    foe = d.id_of(FOE, dv=dv0)
    _drive_creed_faces_foe(d, sid, rid, creed, foe)
    d.cast(foe, creed, d.normal_id(foe))          # SwornProtector -> Kell
    d.ensure_turn(1)
    us = d.units()
    if not any(u.get("visualId") == KELL and u.get("team") == 1 for u in us):
        raise RuntimeError("D : Kell absent -> le gate (2) ne serait pas VRAI, cas non discriminant")
    # PRECONDITION lue sur le plan NATIF (decisionView.attackPlans), pas sur le port : une cible
    # de l'attaque normale de Creed dont les PV sont <= dmgMin => `WillBeKill` (sure-kill).
    dv = d.view()
    plan = next((p for p in (dv.get("attackPlans") or []) if p.get("unitId") == creed), None)
    hp_by_id = {u["id"]: u.get("hp") for u in dv["units"]}
    sure = []
    for ev in ((plan or {}).get("evals") or []):
        if ev.get("abilityId") != d.normal_id(creed, dv):
            continue
        hp = hp_by_id.get(ev.get("targetId"))
        for rk in (ev.get("ranked") or []):
            if hp is not None and rk.get("dmgMin") is not None and rk["dmgMin"] >= hp:
                sure.append((ev.get("targetId"), hp, rk["dmgMin"]))
                break
    print("[D] runner=%s Kell=True sure-kill(natif plan)=%s hp%%Creed=%.2f"
          % (rid, sure, hp_frac(sid, rid, creed)))
    if not sure:
        raise RuntimeError("D : aucun ennemi sure-kill dans le plan natif -> gate (1) non exerce")
    return {"records": [confront("D sure-kill", sid, rid, creed, expect_cast=False)],
            "sure_kill": sure}


def scenario_E(sid, rids):
    """E (MESURE, non bloquante) : Creed BLESSE -> `chance = 1/2 + hp%/2` < 1.

    On tue Kell (degat adverse force par `--dmg-target`) puis on entame Creed, et on compte la
    frequence de cast sur N tirages natifs. Confirme que l'etage (3) est bien un TIRAGE indexe sur
    les PV du caster, et BORNE le gap assume du port (qui rend toujours True)."""
    rid, st = build(sid, 4242, CREED, f"{FOE},{FOE2}",
                    ["--hp-player", "400000", "--hp-target", "400000",
                     "--dmg-target", "120000"], "E")
    rids.append((rid, st))
    d = Drv(sid, rid)
    creed, foe, foe2 = d.id_of(CREED), d.id_of(FOE), d.id_of(FOE2)
    _drive_creed_faces_foe(d, sid, rid, creed, foe)
    d.cast(foe, creed, d.normal_id(foe))           # -> Kell (encaisse a la place de Creed)
    # Tant que Kell VIT, `SwornProtector_Protect` reprend les coups a la place de Creed : on vise
    # donc Kell d'abord (il reste un enfant valide une fois MORT — `AllDeadUnits`), puis Creed.
    for _ in range(14):
        f = hp_frac(sid, rid, creed)
        if f is not None and f <= 0.65:
            break
        d.ensure_turn(2)
        us = d.units()
        kell = next((u for u in us if u.get("visualId") == KELL and u.get("alive")), None)
        victim = kell["id"] if kell else creed
        for f_id in (foe, foe2):
            na = d.normal_id(f_id)
            if na is None:
                continue
            if not d.in_range(f_id, victim, na):
                vpos = next((upos(u) for u in d.units() if u["id"] == victim), None)
                if vpos:
                    d.step_toward(f_id, vpos)
            if d.in_range(f_id, victim, na):
                d.cast(f_id, victim, na)
        d.ensure_turn(1)
    d.ensure_turn(1)
    f = hp_frac(sid, rid, creed)
    us = d.units()
    has_child = any(u.get("visualId") in (KELL, "astraNpc1Guardsman") and u.get("team") == 1
                    for u in us)
    if f is None or f > 0.95 or not has_child:
        print("[E] non mesure (hp%%=%s enfant=%s) — etage (3) non exerce" % (f, has_child))
        return {"records": [], "measured": False, "hp_frac": f}
    c, n = native_cast_rate(sid, rid, creed, 40)
    print("[E] hp%%Creed=%.3f -> chance attendue %.3f ; mesure NATIVE %d/%d = %.3f "
          "(le port rend TOUJOURS True : gap assume)" % (f, 0.5 + f / 2, c, n, c / float(n)))
    return {"records": [], "measured": True, "hp_frac": f, "expected_chance": 0.5 + f / 2,
            "draws": (c, n)}


SCENARIOS = (("A", scenario_A), ("B", scenario_B), ("C", scenario_C),
             ("D", scenario_D), ("A2", scenario_A2), ("E", scenario_E))
# Scenarios qui MESURENT sans confronter (aucun point port-vs-natif a valider).
MEASURE_ONLY = {"E"}


def run_all(sid, only=None, keep=False):
    """Joue les scenarios demandes et rend `{tag: resultat}`.

    Un SEUL runner vivant a la fois : chacun est dispose des sa mesure capturee (MAX_RUNNERS
    est partage entre agents). Reutilise tel quel par le test de garde
    `tests/engine/test_supreme_commander_decision_live.py`."""
    want = {x.strip() for x in only.split(",")} if only else None
    rids: list = []
    res = {}
    try:
        for tag, fn in SCENARIOS:
            if want is not None and tag not in want:
                continue
            res[tag] = fn(sid, rids)
            if not keep and rids:
                rid, st = rids.pop()
                r(sid, "disposeRunner", {"runnerId": rid}, 20)
                st.unlink(missing_ok=True)
    finally:
        if not keep:
            for rid, st in rids:
                try:
                    r(sid, "disposeRunner", {"runnerId": rid}, 20)
                except Exception:
                    pass
                st.unlink(missing_ok=True)
    return res


def verdict(res):
    """`(ok, records)` — tous les points de confrontation de tous les scenarios."""
    recs = [rec for v in res.values() for rec in (v.get("records") or [])]
    ok = bool(recs) and all(rec["ok"] for rec in recs)
    for v in res.values():
        if "draws" in v and "played_turn_spawned" in v:      # scenarios de type A
            c, n = v["draws"]
            ok = ok and c == n and bool(v["played_turn_spawned"])
    return ok, recs


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", default=None,
                    help="liste de tags separes par des virgules : A,B,C,D,A2,E (defaut: tous)")
    a = ap.parse_args(argv)
    sid = _resolve_session()
    print("[probe119] session", sid)
    res = run_all(sid, only=a.only, keep=a.keep)
    ok, recs = verdict(res)
    if not recs:
        # AUCUN point de confrontation : legitime seulement si la selection ne contient que des
        # scenarios de MESURE (E). Sinon c'est un run VIDE, jamais un succes.
        if set(res) <= MEASURE_ONLY:
            print("[probe119] scenarios de MESURE seuls (%s) — rien a confronter" % sorted(res))
            return 0
        print("[probe119] AUCUN point de confrontation joue -> run VIDE, pas un succes")
        return 1
    print("[probe119] points:", json.dumps([(x["tag"], x["ok"]) for x in recs]))
    print("[probe119] verdict:", "ACCORD" if ok else "DESACCORD")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
