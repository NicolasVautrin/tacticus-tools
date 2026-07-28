"""Helper REUTILISABLE de REPLAY-DIFF d'un CAST D'ABILITY ACTIVE (live vs offline).

Pendant d'`_combat_replay.py` (qui, lui, ne couvre que l'ATTAQUE NORMALE) : ici on monte une bataille
isolee, on DRIVE les positions des DEUX camps (`applyAction` ne verifie pas la propriete), on casse
l'ability LIVE, et on rejoue EXACTEMENT le meme cast OFFLINE depuis le snapshot PRE-cast avec le MEME
etat de MT. Le test appelant compose sa geometrie et decide pass/skip -- le helper ne fait aucun
assert.

Ce que le harnais garantit, et qui est la raison de son existence :
  * le snapshot (`decisionView` / `observeBattle` / `combatSnapshot` / `dumpRng`) est pris JUSTE AVANT
    le cast live -- c'est la seule facon d'avoir un offline qui parte du MEME etat ET du MEME MT ;
  * `offline_state()` est REJOUABLE a volonte (chaque appel reconstruit un `State` neuf depuis les
    memes payloads), donc un test peut confronter plusieurs variantes sans re-payer de RPC ;
  * les degats live sont extraits des `tags` d'evenement (`Amount` / `Target_Id` /
    `Active_Ability_Type`), donc PAR CIBLE et attribues a L'ABILITY -- pas au bruit de la cascade.

Usage (fixture nommee `ability_cast_harness`, factory de portee session) :

    from _ability_cast_replay import ability_cast_harness   # noqa: F401  (fixture)

    def test_x(ability_cast_harness):
        h = ability_cast_harness(p_units="emperKakophonist", a_units="orksNob,tyranTyrantGuard")
        h.reach_my_turn()
        h.place(h.mine[0]["id"], (3, 4))
        ...
        snap = h.snapshot()
        live = h.cast_live(caster, target, 1199)
        st = h.offline_state(snap)

Invariants du projet respectes : aucune tuile/RVA hardcodee (tout vient du `boardGraph` LIVE), le seed
n'est qu'un generateur de bataille, sorties ASCII.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


class AbilityCastHarness:
    """Une bataille isolee pilotable action par action + son pont live/offline.

    Attributs : `rid` (runnerId), `board` (`Board`, adjacence `native_sym` = la verite hex),
    `my_player` (id du joueur que je pilote). Methodes : cf. les docstrings individuelles."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board
        self.my_player = None

    # ------------------------------------------------------------------ lecture d'etat live

    def dview(self):
        return self.rpc("decisionView",
                        {"runnerId": self.rid, "maxRank": 1, "allAbilities": True}, 90)

    def alive(self, dv=None):
        """Unites VIVANTES du `decisionView` (le RPC garde les cadavres, cf.
        `project_decisionview_keeps_dead`)."""
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, visual_id, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == visual_id), None)

    def enemies_of(self, player, dv=None):
        return [u for u in self.alive(dv) if u.get("owner") != player]

    def effects_of(self, unit_id, dv=None):
        """Noms des effets ACTIFS portes par `unit_id` (`decisionView.effects[].name`). C'est la
        MEME source que celle qu'`EffectsState.seed` consomme -- donc directement comparable au
        `state.effects` offline."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if u.get("id") == unit_id:
                return [e.get("name") for e in (u.get("effects") or [])]
        return []

    # ------------------------------------------------------------------ pilotage

    def reach_my_turn(self, max_end_turns=12):
        """Enchaine des `endturn` jusqu'a ce que le joueur courant soit `self.my_player`. Renvoie le
        `decisionView` a mon tour, ou None si jamais atteint."""
        dv = self.dview()
        if self.my_player is None:
            mine = self.alive(dv)
            self.my_player = mine[0].get("owner") if mine else None
        for _ in range(max_end_turns):
            if dv.get("currentPlayer") == self.my_player:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
            dv = self.dview()
        return dv if dv.get("currentPlayer") == self.my_player else None

    def place(self, unit_id, coord):
        """Deplace `unit_id` sur `coord` -- `applyAction` ne verifie NI la propriete NI la portee,
        donc les DEUX camps sont pilotables (cf. `feedback_drive_positions_dont_blame_geometry`).
        Renvoie True si l'unite est effectivement sur la tuile apres coup.

        ORDRE OBLIGATOIRE : **placer D'ABORD, `reach_my_turn()` ENSUITE**. Chaque `move` consomme
        une activation et peut faire BASCULER le joueur courant ; un cast tente apres coup part
        alors du mauvais tour et le natif le REFUSE en silence (signature #111 : `ok=True`,
        `mutated` absent, 2 evenements, AUCUN degat -- mesure `probe_154_doom_siren_live.py`).
        Repasser par `reach_my_turn()` APRES les placements donne au caster un tour NEUF, flags de
        tour purges (`IdunBattle.Operations.StartTurnOperation$$ResetUnit`) : il n'a donc PAS bouge
        ce tour-la, ce qu'exige tout masque portant `CasterHasNotMoved`."""
        self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": unit_id,
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)
        u = next((x for x in self.alive() if x.get("id") == unit_id), None)
        return u is not None and _upos(u) == (int(coord[0]), int(coord[1]))

    def free_neighbours(self, center, radius=1, exclude=()):
        """Tuiles MARCHABLES a distance hex EXACTEMENT `radius` de `center`, libres de toute unite
        vivante (hors `exclude`). Ordre deterministe (id de tuile croissant)."""
        occupied = {_upos(u) for u in self.alive() if u.get("id") not in set(exclude)}
        out = []
        for t in sorted(self.board.by_id):
            c = self.board.coord(t)
            if (self.board.walkable(t) and hexgeo.distance(center, c) == radius
                    and c not in occupied and c != tuple(center)):
                out.append(c)
        return out

    # ------------------------------------------------------------------ pont live <-> offline

    def snapshot(self):
        """Fige l'etat PRE-cast : `decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`.
        A appeler JUSTE avant `cast_live` -- c'est ce quadruplet que `offline_state` rejoue."""
        return {
            "dv": self.dview(),
            "ob": self.rpc("observeBattle", {"runnerId": self.rid}, 40),
            "snap": self.rpc("combatSnapshot", {"runnerId": self.rid}, 60),
            "rng": self.rpc("dumpRng", {"runnerId": self.rid}, 30),
        }

    def offline_state(self, s):
        """Reconstruit un `State` OFFLINE depuis un `snapshot()`, MT cale sur le meme tirage.
        Rejouable : chaque appel rend un etat NEUF (aucun partage de mutation)."""
        st = load_state(s["dv"], s["ob"], s["snap"], board=self.board)
        if isinstance(s["rng"], dict) and s["rng"].get("mt"):
            st.rng = _seed_rng(s["rng"])
        return st

    def cast_live(self, caster_id, target_id, ability_type):
        """Casse l'ability LIVE et rend
        `{ok, raw, damage_by_target, events}` :
          * `damage_by_target` = {targetId: [Amount par coup]} extrait des `tags` d'evenement filtres
            sur `Active_Ability_Type == ability_type` -- donc les coups de CETTE ability seulement ;
          * `ok=False` = le natif a REFUSE le cast (gate de ciblage / caster) ou l'action a echoue."""
        action = {"kind": "ability", "casterId": caster_id, "abilityType": int(ability_type)}
        if target_id is not None:
            action["targetId"] = target_id
        res = self.rpc("applyAction", {"runnerId": self.rid, "action": action}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        by_tgt = {}
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == int(ability_type):
                by_tgt.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        return {"ok": bool(_ok(res) and a0.get("ok")), "raw": res,
                "damage_by_target": by_tgt, "events": a0.get("events") or []}

    def dispose(self):
        self.rpc("disposeRunner", {"runnerId": self.rid}, 20)


@pytest.fixture(scope="session")
def ability_cast_harness(rpc, build_runner):
    """FABRIQUE de `AbilityCastHarness` -- fixture NOMMEE, reutilisable par tout test de cast.

    `make(p_units=..., a_units=..., seed=..., board=..., extra=[...])` : construit un runner isole
    (cap/liberation geres par `build_runner` du conftest), lit son `boardGraph` et rend le harnais
    pret a piloter. Le `board` par defaut est l'arene `MC1_67` (cf. `runner.md` : `--board` est
    OBLIGATOIRE au build)."""
    def make(p_units, a_units, seed="777", board="MC1_67", extra=None):
        args = ["--p-units", p_units, "--a-units", a_units, *(extra or [])]
        rid = build_runner(seed, extra=args, board=board)["rid"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        h = AbilityCastHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        dv = h.dview()
        if not _ok(dv):
            pytest.skip("decisionView KO")
        return h
    return make
