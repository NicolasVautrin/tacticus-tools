"""MONTAGE reutilisable << ArcaneShield >> (Thaumachus, `thousSorcerer`) — roster mixte + positions DRIVEES.

POURQUOI UN MONTAGE, ET PAS UN SETUP INLINE. Le port d'`ArcaneShield` a deux faces que seul un roster
MIXTE peut separer : le VECTEUR d'activation (`On(0x1c=ArrivedAtFinalTile)` = apres le move OU en fin de
tour sans move) et la FORMULE DE TRI de la cible. Cette derniere est un SCORE ADDITIF
(`3*distance + faction + chaos + owner`, cf. `triggers/loki/arcane_shield.py::_arcaneshield_score`) : pour
la confronter il faut, EN MEME TEMPS et A PORTEE, un ami de la MEME faction, un ami d'une AUTRE faction
Chaos, et un ami NON-Chaos, chacun a une distance CHOISIE. Ce montage-la est la vraie valeur du lot ; il
resservira a toute confrontation ulterieure du meme selecteur (ou de tout selecteur qui pondere
faction/alliance/distance).

ROSTER (tous HERO, tous presents dans `rl_duel.py build --list-pool`, rank 17) :

  | role           | unite            | FactionId      | GrandAllianceId | pourquoi CELUI-LA               |
  |----------------|------------------|----------------|-----------------|---------------------------------|
  | owner          | `thousSorcerer`  | ThousandSons   | Chaos           | le porteur d'`ArcaneShield`     |
  | same_faction   | `thousTzaangor`  | ThousandSons   | Chaos           | faction == owner -> penalite 0  |
  | other_chaos    | `worldJakhal`    | WorldEaters    | Chaos           | Chaos mais autre faction -> +1  |
  | non_chaos      | `astraDreir`     | AstraMilitarum | Imperial        | ni faction ni Chaos -> +1 +1    |
  | (adversaire)   | `necroWarden`    | Necrons        | Xenos           | juste de quoi avoir une bataille|

Aucun des trois amis ne porte `TeleportStrike` (le volet << Targetable >> d'`OnlyAliveAndTargetable` les
exclurait tant qu'ils sont en Deep Strike) ni `Steppable` (`UnitsWithoutTrait(0x1b)`), et aucun ne porte de
trigger qui pollue le vecteur teste. Ce choix est un CRITERE, pas une preference : le relire avant de
substituer une unite.

SCORES ATTENDUS (range = 2, lu de `ArcaneShield.constants.range`) :

    role          d=1   d=2      formule
    same_faction    3     6      3*d + 0 + 0
    other_chaos     4     7      3*d + 1 + 0
    non_chaos       5     8      3*d + 1 + 1
    owner (d=0)          10      0 + 0 + 0 + (range*3 + 4)

D'ou le montage DISCRIMINANT du lot : `non_chaos` a d=1 (5) BAT `same_faction` a d=2 (6). Un port qui
trierait << faction d'abord, distance ensuite >> choisirait l'inverse.

ASCII only (console cp1252).
"""
from __future__ import annotations

from collections import deque

import pytest

OWNER_VIS = "thousSorcerer"          # Thaumachus, passive ArcaneShield (ThousandSons / Chaos)
SAME_FACTION_VIS = "thousTzaangor"   # ThousandSons / Chaos      -> $$Faction = 0, $$Chaos = 0
OTHER_CHAOS_VIS = "worldJakhal"      # WorldEaters  / Chaos      -> $$Faction = 1, $$Chaos = 0
NON_CHAOS_VIS = "astraDreir"         # AstraMilitarum / Imperial -> $$Faction = 1, $$Chaos = 1
ENEMY_VIS = "necroWarden"

ROLE_VIS = {"owner": OWNER_VIS, "same_faction": SAME_FACTION_VIS,
            "other_chaos": OTHER_CHAOS_VIS, "non_chaos": NON_CHAOS_VIS}
FRIEND_ROLES = ("same_faction", "other_chaos", "non_chaos")

# Le seed n'est qu'un GENERATEUR de bataille (les positions sont ensuite drivees) ; le board est fixe
# pour que le montage soit reproductible d'une passe a l'autre.
SEED = "777"
BOARD = "MC1_67"
# Rayon de recherche d'une tuile-ancre pour l'owner quand sa tuile de spawn ne peut pas realiser la
# configuration demandee (cf. `place`). `Board` n'expose pas d'enumeration globale des tuiles : on
# balaye les tuiles walkable atteignables autour du spawn, du plus proche au plus loin.
_ANCHOR_SEARCH_RADIUS = 12
BUILD_ARGS = ["--p-units", ",".join(ROLE_VIS[r] for r in ("owner", *FRIEND_ROLES)),
              "--a-units", ENEMY_VIS, "--board", BOARD]


class ArcaneShieldStage:
    """Bataille LIVE montee + de quoi en tirer autant d'etats OFFLINE que de scenarios.

    `load()` rend un `State` NEUF a chaque appel (memes captures live) : chaque scenario part donc d'un
    etat vierge — flags de tour non poses, boucliers a leur valeur reelle — sans re-construire de runner.
    `place()` DRIVE les positions (doctrine : on deplace les unites pour obtenir la configuration voulue,
    on ne subit pas la geometrie de spawn)."""

    def __init__(self, rid, board, dec, ob, snap, ids):
        self.rid = rid
        self.board = board
        self.dec, self.ob, self.snap = dec, ob, snap
        self.ids = ids                       # role -> entity id
        self.owner_id = ids["owner"]

    # -- etat ---------------------------------------------------------------------------------------
    def load(self):
        from engine.runner.snapshot import load_state
        return load_state(self.dec, self.ob, self.snap, board=self.board)

    # -- geometrie ----------------------------------------------------------------------------------
    def _rings(self, src: int, max_d: int) -> dict:
        """Anneaux BFS (tuiles WALKABLE par distance) autour de `src`. MEME metrique que
        `triggers/base.py::_hex_dist` (BFS sur `board.neighbours`, murs ignores) — donc ce que le
        selecteur `SurroundingFriends(., range)` du port va mesurer."""
        seen = {src: 0}
        rings: dict = {}
        q = deque([src])
        while q:
            x = q.popleft()
            if seen[x] >= max_d:
                continue
            for n in self.board.neighbours(x):
                if n in seen:
                    continue
                seen[n] = seen[x] + 1
                if self.board.walkable(n):
                    rings.setdefault(seen[n], []).append(n)
                q.append(n)
        return rings

    def place(self, state, layout: dict, exile_others: bool = True) -> dict:
        """DRIVE : impose la configuration `layout` (`role -> distance hex de l'owner`). Les amis NON
        cites sont EXILES hors du rayon d'`ArcaneShield` quand `exile_others` (defaut) — sans quoi leur
        position de spawn polluerait le classement. Rend `{role: tile_id}`.

        L'OWNER EST DEPLACE AUSSI SI NECESSAIRE. C'est le point qui rend ce montage utilisable : la
        tuile de spawn de Thaumachus peut n'avoir que 2 ou 3 voisins walkable, et une configuration qui
        demande deux amis a distance 1 n'y tient pas. Plutot que de skipper (<< bloque par la geometrie
        de spawn >>), on CHERCHE une tuile-ancre dont les anneaux realisent la configuration demandee,
        et on y met l'owner. Les tuiles occupees par des unites qu'on NE deplace PAS (les adversaires)
        restent interdites ; celles des amis se liberent puisqu'ils sont tous replaces."""
        from engine.runner.components import PositionComponent
        movable = set(self.ids.values())
        blocked = set()
        for uid, ent in state.entities.items():
            if uid in movable:
                continue                     # sera replace -> sa tuile se libere
            pc = ent.get_component(PositionComponent)
            if pc is not None:
                blocked.add(self.board.id_at(pc.col, pc.row))

        wanted = dict(layout)
        exile_d = (max(int(d) for d in layout.values()) + 3) if layout else 5
        if exile_others:
            for r in FRIEND_ROLES:
                wanted.setdefault(r, exile_d)
        need: dict = {}
        for d in wanted.values():
            need[int(d)] = need.get(int(d), 0) + 1
        max_d = max(need) if need else 1

        def _fits(anchor: int):
            rings = self._rings(anchor, max_d=max_d + 1)
            for d, n in need.items():
                free = [t for t in rings.get(d, []) if t not in blocked]
                if len(free) < n:
                    return None
            return rings

        opc = state.get_entity(self.owner_id).get_component(PositionComponent)
        anchor = self.board.id_at(opc.col, opc.row)
        rings = None if anchor in blocked else _fits(anchor)
        if rings is None:                    # la tuile de spawn ne tient pas -> on RE-ANCRE l'owner
            # Espace de candidats = les tuiles walkable atteignables autour du spawn (BFS large) ;
            # `Board` n'expose pas d'enumeration globale, et rester dans la zone de spawn garde
            # l'ancre a portee du reste de la bataille.
            reach = self._rings(anchor, max_d=_ANCHOR_SEARCH_RADIUS)
            for _d in sorted(reach):
                for cand in reach[_d]:
                    if cand in blocked:
                        continue
                    rings = _fits(cand)
                    if rings is not None:
                        anchor = cand
                        col, row = self.board.coord(cand)
                        opc.col, opc.row = col, row
                        break
                if rings is not None:
                    break
        if rings is None:
            pytest.skip(f"board {BOARD}: aucune tuile-ancre ne realise la configuration {wanted}")

        taken = set(blocked) | {anchor}
        placed: dict = {}
        for role, dist in sorted(wanted.items(), key=lambda kv: kv[1]):
            tile = next((t for t in rings.get(int(dist), []) if t not in taken), None)
            if tile is None:                 # _fits l'a exclu ; garde-fou, pas un chemin attendu
                pytest.skip(f"board {BOARD}: plus de tuile libre a distance {dist} ({role})")
            col, row = self.board.coord(tile)
            pc = state.get_entity(self.ids[role]).get_component(PositionComponent)
            pc.col, pc.row = col, row
            taken.add(tile)
            if role in layout:
                placed[role] = tile
        return placed


def build_stage(build_runner, rpc) -> ArcaneShieldStage:
    """Monte la bataille du montage et capture l'etat live UNE fois. Utilise par la fixture pytest
    `arcaneshield_stage` (`tests/conftest.py`) — c'est par elle qu'on s'en sert."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner(SEED, extra=list(BUILD_ARGS))["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    if not (isinstance(dec, dict) and dec.get("ok")):
        pytest.skip("decisionView KO")
    ids = {}
    for role, vis in ROLE_VIS.items():
        u = next((x for x in (dec.get("units") or [])
                  if x.get("visualId") == vis and x.get("alive")), None)
        if u is None:
            pytest.skip(f"{vis} ({role}) absent de l'etat capture")
        ids[role] = u["id"]
    stage = ArcaneShieldStage(rid, board, dec, ob, snap, ids)
    probe = stage.load()
    for role, uid in ids.items():
        if probe.get_entity(uid) is None:
            pytest.skip(f"{role} absent offline (snapshot incomplet)")
    return stage
