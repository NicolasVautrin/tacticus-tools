"""#447-r1-r1 -- la branche INCLUSION du bit 15 sur la face DECISION.

LA QUESTION BINAIRE. `CasterIsPossibleTarget` (bit 15) met la tuile du CASTER dans la zone. La
face CIBLAGE (`abilityTargets`) l'a confronte (#447-r1). La face DECISION -- celle que
`engine.services.ability_range._zone_contains_distance` sert a
`is_tile_in_range_of_any_ability`, oracle `aiMovableTiles {threat: true}` -- n'avait qu'une garde
OFFLINE pour la branche << bit arme >>. Le natif verse-t-il, LA, la tuile source ?

L'ORACLE, et pourquoi c'est le bon. `aiMovableTiles {threat: true}` enchaine
`IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor(unit, opts)` puis
`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, <ce set>,
includeNormalAttack: 1)`. La surcharge 3 arguments convertit le set par
`IdunBattle.Core.UnitPositionExtensions$$ToUnitPositionList` et ITERE : pour chaque position
CANDIDATE, la surcharge 4 arguments evalue les quatre gates CASTER puis verse les slots 9/10 de
l'ability. La zone d'une position candidate `p` est donc calculee avec `casterTiles = {p}`, et
`p` y figure ssi `TargetingQuery$$GetPossibleTargetsForOptions` ajoute `casterTiles` --
c'est-a-dire ssi le bit 15 (ou le bit 57 `TargetIsCasterOrEnemy`) est arme.

⚠ LE PIEGE DE MESURE (regime DEGENERE), et il est le meme qu'au #447-r1 sous une autre forme.
Le resultat est l'UNION sur TOUTES les positions candidates. Des que deux positions candidates
sont a portee l'une de l'autre, chacune est couverte DEPUIS L'AUTRE par l'attaque normale -- et
la reponse ne depend plus du bit 15. Le seul regime qui DECIDE est le movable set SINGLETON.
Ce probe l'OBTIENT par la GEOMETRIE et le VERIFIE (`n_move == 1`), au lieu de l'esperer :
chaque porteur isole est place sur un CUL-DE-SAC -- une tuile marchable dont UNE SEULE voisine
passe la porte d'elevation de `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`
(`|dElev| < 2`) -- et `overrideRange: 1` borne le deplacement a un pas. Un cinquieme poste, en
terrain OUVERT, MESURE le regime degenere au lieu de le supposer.

CE QUE LE MONTAGE SEPARE, en UN SEUL runner (le natif repond a tout dans le MEME etat) :

  * `astraCreed` / `1028 SupremeCommander` (`0x208000`, RANGE_SELF, AUCUN gate caster) -- bit 15
    arme, zone de l'ability = EXACTEMENT `casterTiles`. La tuile source doit etre versee.
  * `astraBullgryn` / `1017 FragBomb` (`0x80040`, rayon 1) -- pas de bit 15 : CONTROLE, la tuile
    source ne doit PAS etre versee. Meme `unit_threat_reach` (1) que le precedent.
  * `orksRuntherd` / `1045 GetEmRuntz` (`0x8004`, RANGE_SELF + `CasterMatchesDynamicRule`), en
    DEUX exemplaires -- c'est la MESURE DU BLOCAGE que `#447-r1` §8 annoncait. Sa regle-delegue
    `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetDynamicInvalidCasterReason`
    rend **2** quand `GetSpawnTileSelector` est vide (aucune tuile LIBRE adjacente au caster ET
    adjacente a un ennemi). Un exemplaire a un ennemi pose contre la sortie de son cul-de-sac
    (gate PASSE), l'autre non (gate MORD). MEME ability, MEME bit 15 : ce qui les separe est le
    GATE, pas le masque.

⚠ CE QUE CE PROBE REFUTE. Le blocage etait annonce comme
<< `AttackQuery$$GetInvalidCasterReason` NON PORTE >>. Il l'EST depuis
`#433-r4-r2-r1-r2-r2-r1-r1-r1-r4` (`engine.services.ability_caster_gates.invalid_caster_reason`,
onze regles dans l'ordre natif). Ce qui reste vrai du blocage est un fait de MONTAGE, pas de
port : sans ennemi a portee du cul-de-sac, le natif ne verse rien pour `1045` et la mesure
n'atteint jamais la zone. On DEPLACE les unites, on n'accuse pas la geometrie.

Le TEST qui garde le port est `tests/engine/test_447_r1_r1_zone_inclusion_decision_live.py`.
ASCII only.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo                                                             # noqa: E402
from engine.runner.abilities import targeting as TGT                      # noqa: E402
from engine.runner.abilities.targeting import targeting_options_for       # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR    # noqa: E402
from engine.services import ability_caster_gates as acg                   # noqa: E402
from engine.services import ability_range as AR                           # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
SEED = "777"

#: `MovementOptions.OverrideRange` de la mesure -- UN pas. Avec un cul-de-sac, le movable set se
#: reduit alors a la SEULE voisine praticable, ce qui est le regime non degenere (cf. l'en-tete).
#: `overrideRange: 0` est inutilisable : il rend `tiles: []` ET `threatTiles: []` (mesure #...-r1-r1-r1).
MEASURE_RANGE = 1

#: `C1_70` porte CINQ culs-de-sac de degre 1 (une seule voisine passe la porte d'elevation) ET
#: assez de points de spawn joueur pour un roster de cinq -- les deux contraintes ensemble ne sont
#: satisfaites que par quatre boards du corpus (`C4_05`, plus riche en culs-de-sac, n'a que TROIS
#: spawns joueur et refuse le roster). La propriete est RE-DERIVEE de
#: `data/boards/global/C1_70.json` par `--step geometrie`, jamais affirmee.
BOARD = "C1_70"
FILLER = "necroWarden"

#: Le poste OUVERT -- degre 6, toutes voisines mutuellement adjacentes : le TEMOIN du regime
#: degenere. Sans lui, << la tuile source est dans la menace >> se lirait comme une preuve du bit 15.
TEMOIN_OUVERT = (5, 2)

#: L'ennemi qui OUVRE le gate de l'un des deux Runtherd : pose contre la sortie `(2,4)` du
#: cul-de-sac `(1,5)`, il rend `GetSpawnTileSelector` non vide. L'autre ennemi n'est adjacent a
#: AUCUNE sortie -- les deux proprietes sont re-derivees par `--step geometrie`.
ENNEMI_OUVRE = (2, 3)
ENNEMI_LOIN = (6, 0)

#: Les postes du montage. `pos` = le cul-de-sac (ou le terrain ouvert), `sortie` = l'unique voisine
#: praticable attendue -- RE-DERIVEE du board par `--step geometrie` et RE-VERIFIEE au runtime
#: contre le movable set que le natif rend.
POSTES = [
    {"cle": "creed_bit", "visual": "astraCreed", "ability": 1028,
     "pos": (2, 1), "sortie": (1, 1), "isole": True, "bit15": True, "attendu": "INCLUS"},
    {"cle": "bullgryn_sans_bit", "visual": "astraBullgryn", "ability": 1017,
     "pos": (6, 5), "sortie": (5, 5), "isole": True, "bit15": False, "attendu": "EXCLUS"},
    {"cle": "ork_gate_passe", "visual": "orksRuntherd", "ability": 1045,
     "pos": (1, 5), "sortie": (2, 4), "isole": True, "bit15": True, "attendu": "INCLUS"},
    {"cle": "ork_gate_mord", "visual": "orksRuntherd", "ability": 1045,
     "pos": (3, 7), "sortie": (3, 6), "isole": True, "bit15": True, "attendu": "EXCLUS"},
    {"cle": "temoin_ouvert", "visual": "astraBullgryn", "ability": 1017,
     "pos": TEMOIN_OUVERT, "sortie": None, "isole": False, "bit15": False, "attendu": "DEGENERE"},
]

#: Le code que la regle-delegue de `1045` rend quand `GetSpawnTileSelector` est vide -- le litteral
#: **2**, que l'enum genere nomme `TargetMatchesDynamicRule` (le natif reutilise ce code pour le
#: volet CASTER ; cf. `ability_caster_gates.dynamic_caster_reason`).
GATE_MORD_CODE = int(TR.TargetMatchesDynamicRule)

UNWALKABLE_TILE_IDS = ("Water", "Block")


# ------------------------------------------------------------------------------------------------
# ETAPE 0 -- LA GEOMETRIE, RE-DERIVEE DU BOARD (offline)
# ------------------------------------------------------------------------------------------------

def geometrie(board=None) -> dict:
    """Les culs-de-sac du board, RE-DERIVES de `data/boards/global/<board>.json`.

    Un cul-de-sac est une tuile MARCHABLE dont UNE SEULE voisine hex est marchable ET passe la
    porte d'elevation `|dElev| < 2` de
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. C'est
    exactement ce qui borne `GetMovableTilesFor` a un singleton sous `overrideRange: 1`.

    Rendre cette table est ce qui empeche les constantes de POSTES de se perimer en silence : si le
    board change, `--step geometrie` cesse de les confirmer."""
    from board import Board
    bid = board or BOARD
    src = ROOT / "data" / "boards" / "global" / ("%s.json" % bid)
    d = json.loads(src.read_text(encoding="utf-8"))
    b = Board({"Board": d["board"], "SpawnPointSetIndex": 0, "Player": {"Players": {}}})
    ok = {p: t for p, t in b.tiles.items()
          if t["playable"] and t["tileId"] not in UNWALKABLE_TILE_IDS}

    def voisines(p):
        t = ok[p]
        return [tuple(n) for n in hexgeo.neighbors(*p)
                if tuple(n) in ok and abs(int(ok[tuple(n)]["elevation"]) - int(t["elevation"])) < 2]

    culs = {p: voisines(p)[0] for p in ok if len(voisines(p)) == 1}
    ouverts = [p for p in ok if len(voisines(p)) == 6]
    attendus = {tuple(P["pos"]): (None if P["sortie"] is None else tuple(P["sortie"]))
                for P in POSTES if P["isole"]}
    return {"board": bid, "tuiles_marchables": len(ok),
            "culs_de_sac": {str(k): list(v) for k, v in sorted(culs.items())},
            "ouverts_degre_6": [list(p) for p in sorted(ouverts)],
            "postes_isoles_sont_des_culs_de_sac":
                all(culs.get(p) == s for p, s in attendus.items()),
            "temoin_est_ouvert": tuple(TEMOIN_OUVERT) in set(ouverts),
            "ennemi_ouvre_est_adjacent_a_la_sortie":
                tuple(ENNEMI_OUVRE) in set(voisines(tuple(
                    next(P["sortie"] for P in POSTES if P["cle"] == "ork_gate_passe")))),
            "ennemi_loin_nest_adjacent_a_aucune_sortie":
                all(tuple(ENNEMI_LOIN) not in set(voisines(tuple(P["sortie"])))
                    for P in POSTES if P["isole"])}


# ------------------------------------------------------------------------------------------------
# ETAPE 1 -- LA PAIRE, RE-DERIVEE (offline)
# ------------------------------------------------------------------------------------------------

def masques() -> dict:
    """Les proprietes des trois masques du montage, RE-DERIVEES du foyer `targeting_options_for` --
    jamais affirmees. `zone_d0` est la reponse du port a << la tuile source est-elle dans la zone
    >>, la fonction meme que cette tranche confronte."""
    out = {}
    for P in POSTES:
        aid = int(P["ability"])
        o = targeting_options_for(aid)
        r = int(getattr(o, "rules", 0) or 0)
        out[P["cle"]] = {
            "ability": aid, "visual": P["visual"], "rules": "0x%x" % r,
            "bit15": bool(r & int(TR.CasterIsPossibleTarget)),
            "bit57": bool(r & int(TR.TargetIsCasterOrEnemy)),
            "gate_caster": acg.dynamic_caster_gate_of(aid),
            "reach_ability": AR.tiles_in_range_reach(aid, P["visual"]),
            "threat_reach": AR.unit_threat_reach(P["visual"]),
            "zone_d0": AR.tiles_in_range_zone_contains(aid, P["visual"], 0),
            "kit": sorted(AR._active_ability_ids(P["visual"])),
        }
    return out


def masques_discriminants(m) -> list:
    """Les proprietes SANS lesquelles la mesure ne demontrerait rien -- chacune re-derivee."""
    creed, bull = m["creed_bit"], m["bullgryn_sans_bit"]
    ork_p, ork_m = m["ork_gate_passe"], m["ork_gate_mord"]
    return [
        ("le porteur BIT porte bien le bit 15", creed["bit15"] is True),
        ("le CONTROLE ne porte NI bit 15 NI bit 57",
         bull["bit15"] is False and bull["bit57"] is False),
        ("les deux ont le MEME threat_reach", creed["threat_reach"] == bull["threat_reach"]),
        ("le port separe deja les deux a d=0 (offline)",
         creed["zone_d0"] is True and bull["zone_d0"] is False),
        ("le porteur BIT n'a QU'UNE ability active (aucune autre ne peut verser d=0)",
         len(creed["kit"]) == 1),
        ("le CONTROLE n'a QU'UNE ability active", len(bull["kit"]) == 1),
        ("les deux Runtherd sont la MEME ability, MEME masque",
         ork_p["ability"] == ork_m["ability"] and ork_p["rules"] == ork_m["rules"]),
        ("le Runtherd porte le gate `spawn_tile`", ork_p["gate_caster"] == "spawn_tile"),
        ("le porteur BIT ne porte AUCUN gate caster", creed["gate_caster"] == "none"),
    ]


# ------------------------------------------------------------------------------------------------
# PLOMBERIE LIVE
# ------------------------------------------------------------------------------------------------

def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(board, p_units, a_units, place, a_place):
    state = ROOT / "logs" / "runners" / ("p447r1r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    for pl in place:
        argv += ["--place", pl]
    for pl in a_place:
        argv += ["--a-place", pl]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1800:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                                     # pragma: no cover
        pass


def _obs(sid, rid):
    o = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    return ([u for u in (o.get("units") or [])
             if not u.get("isDead") and u.get("col") is not None],
            o.get("currentPlayer"))


def _threat(sid, rid):
    mov = _r(sid, "aiMovableTiles",
             {"runnerId": rid, "threat": True, "side": "all",
              "overrideRange": MEASURE_RANGE}, 180)
    return {u.get("unitId"): ([(t["col"], t["row"]) for t in (u.get("tiles") or [])],
                              {(t["col"], t["row"]) for t in (u.get("threatTiles") or [])})
            for u in (mov.get("units") or [])}


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    tiles = bg.get("tiles") or []
    pos = {t["id"]: (t["col"], t["row"]) for t in tiles}
    return ({pos[t["id"]]: t.get("elevation") for t in tiles},
            {pos[t["id"]]: bool(t.get("walkable")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isWall")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isInFog")) for t in tiles})


def _dv_rows(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)
    return {u.get("id"): u for u in (dv.get("units") or []) if u.get("id") is not None}


def _hex_to_int(h):
    if not h:
        return None
    try:
        return int(str(h), 16)
    except ValueError:                                                    # pragma: no cover
        return None


def _caster_reason(sid, rid, uid, aid):
    """`casterReason` de l'oracle `abilityReason` = `AttackQuery$$GetInvalidCasterReason(caster,
    getUnitMainTile(caster), ability)`. `None` = l'oracle n'a rien resolu, PAS << valide >>."""
    rep = _r(sid, "abilityReason",
             {"runnerId": rid, "casterId": uid, "abilityType": int(aid)}, 90)
    cr = (rep or {}).get("casterReason")
    return (None if cr is None else _hex_to_int(cr.get("hex")),
            None if cr is None else (cr.get("reasons") or []))


class _SansBit15:
    """Le contre-factuel : le port SANS le bit 15, le reste du masque INCHANGE.

    Retirer le bit du masque est plus fidele que court-circuiter la fonction -- on demande << et si
    le natif ne l'armait pas ? >>, donc les autres etages continuent de s'appliquer. La substitution
    porte sur `engine.runner.abilities.targeting.targeting_options_for`, que
    `ability_range._options_of` importe A CHAQUE APPEL (import paresseux, pour casser le cycle
    services <-> runner) : muter l'attribut de module est donc EFFECTIF."""

    def __enter__(self):
        self._f = TGT.targeting_options_for
        bit, orig = int(TR.CasterIsPossibleTarget), self._f

        def sans(aid):
            o = orig(aid)
            return None if o is None else dataclasses.replace(o, rules=int(o.rules) & ~bit)
        TGT.targeting_options_for = sans
        AR._REACH_CACHE.clear()
        return self

    def __exit__(self, *_exc):
        TGT.targeting_options_for = self._f
        AR._REACH_CACHE.clear()
        return False


class _SansClause2:
    """Le contre-factuel de la 2e clause de `CasterHasNotMoved` : le substrat n'expose plus la
    position INTERROGEE, donc la clause ne peut plus refuser -- exactement ce que le port faisait
    avant #447-r1-r1 (`CasterSubstrate` n'avait pas ce champ).

    La substitution porte sur `acg.CasterSubstrate`, que `is_tile_in_range_of_any_ability` appelle
    par son nom de MODULE et en arguments NOMMES -- elle est donc effective."""

    def __enter__(self):
        self._c = acg.CasterSubstrate
        orig = self._c

        def sans(**kw):
            kw = dict(kw)
            kw["interrogated_pos"] = None
            return orig(**kw)
        acg.CasterSubstrate = sans
        AR._REACH_CACHE.clear()
        return self

    def __exit__(self, *_exc):
        acg.CasterSubstrate = self._c
        AR._REACH_CACHE.clear()
        return False


class _SansGate4:
    """Le contre-factuel du QUATRIEME gate CASTER : `invalid_caster_reason` rend toujours
    << valide >>, ce que le port faisait avant `#433-r4-r2-r1-r2-r2-r1-r1-r1-r4`.

    `caster_gate_reason` appelle `invalid_caster_reason` par son nom de MODULE -- la substitution
    est donc effective."""

    def __enter__(self):
        self._f = acg.invalid_caster_reason
        acg.invalid_caster_reason = lambda ability_id, caster=None: 0
        AR._REACH_CACHE.clear()
        return self

    def __exit__(self, *_exc):
        acg.invalid_caster_reason = self._f
        AR._REACH_CACHE.clear()
        return False


def _port_zone(move_tiles, all_tiles, visual, elev, walk, wall, fog, caster_pos,
               caster_team=None, team_by_pos=None, ability_ids=None,
               ability_state=None, normal_attack_id=None, is_turn_of_unit=None):
    """Le port, en UNION sur le MOVABLE SET -- le meme `possiblePositions` que le natif.

    `caster_pos` est passe EXPLICITEMENT : la position balayee n'est pas la tuile courante, et le
    4e gate lit la COURANTE (`CasterSelector$$Select` rend l'ENTITE caster). `is_turn_of_unit`
    alimente le PREFIXE de `CasterHasNotMoved`, dont la 2e clause compare la position BALAYEE aux
    tuiles reelles du caster -- c'est le seul regime ou elle mord (#447-r1-r1)."""
    AR._REACH_CACHE.clear()
    out = set()
    for T in all_tiles:
        for X in move_tiles:
            if AR.is_tile_in_range_of_any_ability(X, T, visual, ability_ids=ability_ids,
                                                  elev_by_pos=elev, ability_state=ability_state,
                                                  normal_attack_id=normal_attack_id,
                                                  is_wall_by_pos=wall, walkable_by_pos=walk,
                                                  is_in_fog_by_pos=fog, caster_pos=caster_pos,
                                                  caster_team=caster_team,
                                                  team_by_pos=team_by_pos,
                                                  is_turn_of_unit=is_turn_of_unit):
                out.add(T)
                break
    return out


def _roster():
    """Le roster et les `--place`, DERIVES de `POSTES` -- l'ordre des occurrences d'un meme
    `unitId` est celui que `rl_duel._apply_place_overrides` consomme."""
    p_units = [P["visual"] for P in POSTES]
    place = ["%s:%d,%d" % (P["visual"], P["pos"][0], P["pos"][1]) for P in POSTES]
    a_units = [FILLER, FILLER]
    a_place = ["%s:%d,%d" % (FILLER, ENNEMI_OUVRE[0], ENNEMI_OUVRE[1]),
               "%s:%d,%d" % (FILLER, ENNEMI_LOIN[0], ENNEMI_LOIN[1])]
    return ",".join(p_units), ",".join(a_units), place, a_place


def live(sid, board=None) -> dict:
    """LA CONFRONTATION. UN seul runner porte les CINQ postes : le natif repond a toutes les
    questions dans le MEME etat, donc aucune variable de montage ne les separe."""
    bid = board or BOARD
    p_units, a_units, place, a_place = _roster()
    rid, err = _build(bid, p_units, a_units, place, a_place)
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        out = {"board": bid, "runner": rid, "postes": {}}
        elev, walk, wall, fog = _board_maps(sid, rid)
        allp = sorted(elev)
        th, units, joueur = None, None, None
        for _ in range(6):
            th = _threat(sid, rid)
            units, joueur = _obs(sid, rid)
            if any(v[0] for v in th.values()):
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        by_pos = {(u["col"], u["row"]): u for u in (units or [])}
        team_by_pos = {(u["col"], u["row"]): u.get("teamId") for u in (units or [])}
        out["positions"] = {str((u["col"], u["row"])): u.get("visualId") for u in (units or [])}
        rows = _dv_rows(sid, rid)
        for P in POSTES:
            pos = tuple(P["pos"])
            u = by_pos.get(pos)
            if u is None or u.get("visualId") != P["visual"]:
                out["postes"][P["cle"]] = {
                    "error": "poste %s : attendu %s en %s, trouve %s"
                             % (P["cle"], P["visual"], list(pos),
                                None if u is None else u.get("visualId"))}
                continue
            uid = u["squadId"]
            move, natif = th.get(uid) or ([], set())
            natif = set(natif) & set(allp)
            st = acg.ability_state_map(rows.get(uid))
            na_id = acg.normal_attack_id(rows.get(uid))
            sub = acg.CasterSubstrate(pos=pos, has_tile=True, team=u.get("teamId"),
                                      team_by_pos=team_by_pos, walkable_by_pos=walk,
                                      elev_by_pos=elev, neigh_by_pos=None)
            nat_reason, noms = _caster_reason(sid, rid, uid, P["ability"])
            kw = dict(caster_team=u.get("teamId"), team_by_pos=team_by_pos,
                      ability_state=st, normal_attack_id=na_id,
                      is_turn_of_unit=(None if joueur is None or u.get("playerId") is None
                                       else int(u["playerId"]) == int(joueur)))
            port = _port_zone(move, allp, P["visual"], elev, walk, wall, fog, pos, **kw)
            normale = _port_zone(move, allp, P["visual"], elev, walk, wall, fog, pos,
                                 ability_ids=[], **kw)
            with _SansBit15():
                sans_bit = _port_zone(move, allp, P["visual"], elev, walk, wall, fog, pos, **kw)
                # LE MASQUE TEL QUE LE PORT LE LIT, pas tel que ce probe l'importe : `_options_of`
                # refait l'import PARESSEUX a chaque appel, donc c'est le seul chemin qui prouve
                # que la mutation atteint bien le consommateur. Passer par le nom importe ici
                # rendrait le masque NON MUTE -- un << vert >> qui ne verifierait rien.
                masque_mute = "0x%x" % int(getattr(AR._options_of(P["ability"]),
                                                   "rules", 0) or 0)
            with _SansGate4():
                sans_gate = _port_zone(move, allp, P["visual"], elev, walk, wall, fog, pos, **kw)
            out["postes"][P["cle"]] = {
                "visual": P["visual"], "ability": P["ability"], "attendu": P["attendu"],
                "pos": list(pos), "uid": uid, "n_move": len(move),
                "move": sorted(tuple(t) for t in move),
                "sortie_attendue": None if P["sortie"] is None else tuple(P["sortie"]),
                "natif_caster_reason": nat_reason, "natif_caster_noms": noms,
                "port_caster_reason": acg.invalid_caster_reason(P["ability"], sub),
                "port_gate_nom": acg.caster_gate_reason(P["ability"], st.get(P["ability"]), sub),
                # LE DISCRIMINANT : les positions CANDIDATES elles-memes figurent-elles dans
                # l'ensemble rendu ? C'est la seule question a laquelle le bit 15 reponde ici.
                "source_natif": sorted(t for t in move if t in natif),
                "source_port": sorted(t for t in move if t in port),
                "source_port_sans_bit15": sorted(t for t in move if t in sans_bit),
                "source_port_sans_gate4": sorted(t for t in move if t in sans_gate),
                "source_port_normale_seule": sorted(t for t in move if t in normale),
                "masque_mute_sans_bit15": masque_mute,
                "n_natif": len(natif), "n_port": len(port), "n_normale_seule": len(normale),
                "fp": sorted(port - natif), "fn": sorted(natif - port),
                "fp_normale": sorted(normale - natif), "fn_normale": sorted(natif - normale),
            }
        return out
    finally:
        _dispose(sid, rid)


# ------------------------------------------------------------------------------------------------
# LE VOLET << PORTEE NON LUE >> -- l'ajout aval ne depend PAS de la portee
#
# `GetPossibleTargetsForOptions` ajoute `casterTiles` APRES `GetTilesInRange` et sans consulter la
# portee : une ability dont le `TargetingRange` n'est PAS RE-lu met quand meme la tuile du caster
# dans ses cibles possibles des que le bit 15 est arme. Le port, lui, court-circuite en amont
# (`_ability_covers_tile` : `base = tiles_in_range_reach(...); if base is None: return False`) et
# ne verse RIEN -- ecart RESTRICTIF.
#
# GISEMENT re-derive : EXACTEMENT deux abilities ont `rules & (bit15|bit57)` et un
# `tiles_in_range_reach` a `None` -- `1215 InstrumentsOfVengeance` et `1216 MartialExemplar`, dont
# le `range` est `None` DELIBERE (bloc `<preset>+0x08..0x1f` non resolu). Toutes deux sur le seul
# `darkaBossLion` (npc) -> on les GREFFE sur une unite du pool (recette `case-92` §5bis, deja
# employee par `probe_27_r6_instruments_of_vengeance.py`).
# ------------------------------------------------------------------------------------------------

#: L'ability a portee NON LUE qui porte le bit 15, et l'unite du POOL sur laquelle on la greffe.
PORTEE_NON_LUE_ABILITY = 1215
GRAFT_ON = "darkaAsmodai"
#: Le cul-de-sac du greffe et sa sortie -- memes proprietes que les postes du montage principal.
GRAFT_POS = (2, 1)
GRAFT_SORTIE = (1, 1)


def _write_graft_seed_bc(path: Path, ability_id: int) -> str:
    """Copie du seed BC PARTAGE avec `ActiveAbilities` de `GRAFT_ON` remplace par `[ability_id]`.

    N'ECRIT JAMAIS le seed BC partage (meme discipline que `catalog_inject --out`) : la copie va
    dans `logs/`, qui meurt avec le worktree."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    n = 0
    for u in (bc.get("Units") or []):
        if u.get("Id") == GRAFT_ON:
            u["ActiveAbilities"] = [int(ability_id)]
            n += 1
    if n != 1:
        return "greffe impossible : %d entree(s) %r dans BC.Units" % (n, GRAFT_ON)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bc), encoding="utf-8")
    return ""


def _abilities_de_la_ligne(row) -> list:
    """Les ids d'ability ACTIVE que l'ENTITE porte, lus dans `decisionView.units[].abilities[]`.

    ⚠ PAS le kit gameconfig : une GREFFE change `BC.Units[].ActiveAbilities` et donc l'entite,
    JAMAIS le gameconfig -- `ability_range._active_ability_ids` enumererait le kit d'origine et la
    mesure porterait sur une autre ability (piege KIT != ENTITE, 3e occurrence connue)."""
    return sorted({int(a["id"]) for a in ((row or {}).get("abilities") or [])
                   if a.get("id") is not None and a.get("kind") != "normal"})


#: LA GENERALISATION du volet ci-dessous, SANS greffe : un porteur du POOL dont le masque porte le
#: bit 15 ET `CasterHasNotMoved`, et dont la portee EST lue. Il exerce la 2e clause sur un chemin
#: entierement different de celui du greffe (kit d'origine, portee derivable) -- ce qui separe la
#: clause du correctif de portee.
POOL_HAS_NOT_MOVED = ("spaceBlackmane", 1106)


def portee_non_lue(sid, board=None, ability=None, visual=None) -> dict:
    """UN porteur sur un cul-de-sac : le natif verse-t-il la tuile source, et le port le suit-il ?

    `ability` -- l'autre membre du gisement PORTEE NON LUE (`1216 MartialExemplar`) se mesure par ce
    parametre ; il exerce en plus la 2e clause de `CasterHasNotMoved`, que `1216` arme et `1215`
    non -- les deux masques sortent du MEME preset et ne different que par ce bit.
    `visual` -- quand il est fourni ET different de `GRAFT_ON`, AUCUNE greffe n'est faite : l'unite
    entre avec son kit d'origine (voie de GENERALISATION, cf. `POOL_HAS_NOT_MOVED`)."""
    aid_greffe = int(ability or PORTEE_NON_LUE_ABILITY)
    porteur = visual or GRAFT_ON
    greffe = (porteur == GRAFT_ON)
    bid = board or BOARD
    state = ROOT / "logs" / "runners" / ("p447r1r1g-%s.json" % uuid.uuid4().hex[:8])
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", bid,
            "--state-file", str(state),
            "--p-units", porteur, "--a-units", "%s,%s" % (FILLER, FILLER),
            "--hp-target", "90000", "--hp-player", "90000",
            "--place", "%s:%d,%d" % (porteur, GRAFT_POS[0], GRAFT_POS[1]),
            "--a-place", "%s:%d,%d" % (FILLER, ENNEMI_LOIN[0], ENNEMI_LOIN[1]),
            "--a-place", "%s:%d,%d" % (FILLER, TEMOIN_OUVERT[0], TEMOIN_OUVERT[1])]
    if greffe:
        seed_bc = ROOT / "logs" / "runners" / ("bc447r1r1-graft-%s.json" % uuid.uuid4().hex[:8])
        err = _write_graft_seed_bc(seed_bc, aid_greffe)
        if err:
            return {"error": err}
        argv[3:3] = ["--seed-bc", str(seed_bc)]   # apres le sous-commande `build`
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return {"error": "build KO -- %s" % (p.stderr or p.stdout or "")[-1800:]}
    rid = json.loads(state.read_text())["runnerId"]
    try:
        out = {"board": bid, "runner": rid, "ability": aid_greffe,
               "porteur": porteur, "greffe": greffe}
        elev, walk, wall, fog = _board_maps(sid, rid)
        allp = sorted(elev)
        th, units, joueur = None, None, None
        for _ in range(6):
            th = _threat(sid, rid)
            units, joueur = _obs(sid, rid)
            if any(v[0] for v in th.values()):
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        u = next((x for x in (units or []) if x.get("visualId") == porteur), None)
        if u is None:
            out["error"] = "porteur %r absent du runner" % porteur
            return out
        pos = (u["col"], u["row"])
        uid = u["squadId"]
        rows = _dv_rows(sid, rid)
        aids = _abilities_de_la_ligne(rows.get(uid))
        move, natif = th.get(uid) or ([], set())
        natif = set(natif) & set(allp)
        team_by_pos = {(x["col"], x["row"]): x.get("teamId") for x in (units or [])}
        st = acg.ability_state_map(rows.get(uid))
        na_id = acg.normal_attack_id(rows.get(uid))
        est_son_tour = (None if joueur is None or u.get("playerId") is None
                        else int(u["playerId"]) == int(joueur))
        kw = dict(caster_team=u.get("teamId"), team_by_pos=team_by_pos,
                  ability_state=st, normal_attack_id=na_id, is_turn_of_unit=est_son_tour)
        port = _port_zone(move, allp, porteur, elev, walk, wall, fog, pos,
                          ability_ids=aids, **kw)
        normale = _port_zone(move, allp, porteur, elev, walk, wall, fog, pos,
                             ability_ids=[], **kw)
        with _SansBit15():
            sans_bit = _port_zone(move, allp, porteur, elev, walk, wall, fog, pos,
                                  ability_ids=aids, **kw)
            masque_mute = "0x%x" % int(getattr(AR._options_of(aid_greffe),
                                               "rules", 0) or 0)
        with _SansClause2():
            sans_clause2 = _port_zone(move, allp, porteur, elev, walk, wall, fog, pos,
                                      ability_ids=aids, **kw)
        nat_reason, noms = _caster_reason(sid, rid, uid, aid_greffe)
        out.update({
            "pos": list(pos), "uid": uid, "abilities_de_l_entite": aids,
            "est_son_tour": est_son_tour,
            "porte_caster_has_not_moved": bool(
                int(getattr(targeting_options_for(aid_greffe), "rules", 0) or 0)
                & int(TR.CasterHasNotMoved)),
            "kit_de_l_entite_est_le_bon": aids == [aid_greffe],
            "n_move": len(move), "move": sorted(tuple(t) for t in move),
            "sortie_attendue": tuple(GRAFT_SORTIE),
            "reach_port": AR.tiles_in_range_reach(aid_greffe, porteur),
            "zone_d0_port": AR.tiles_in_range_zone_contains(aid_greffe, porteur, 0),
            "natif_caster_reason": nat_reason, "natif_caster_noms": noms,
            "source_natif": sorted(t for t in move if t in natif),
            "source_port": sorted(t for t in move if t in port),
            "source_port_sans_bit15": sorted(t for t in move if t in sans_bit),
            "source_port_sans_clause2": sorted(t for t in move if t in sans_clause2),
            "source_port_normale_seule": sorted(t for t in move if t in normale),
            "masque_mute_sans_bit15": masque_mute,
            "n_natif": len(natif), "n_port": len(port),
        })
        return out
    finally:
        _dispose(sid, rid)


def attendu_du_greffe(d):
    """Ce que le NATIF doit verser, DERIVE du masque et de l'etat -- jamais suppose.

    Deux regimes, et c'est la 2e clause de `CasterHasNotMoved` qui les separe : si le masque porte
    le bit 4 ET que c'est le tour du proprietaire, le natif REFUSE toute position candidate
    differente de la tuile courante (`GetTiles(caster).IsEquivalentTo(casterTiles)`), donc il ne
    verse RIEN. Sinon l'ajout aval du bit 15 s'applique et il verse la tuile source."""
    if d.get("porte_caster_has_not_moved") and d.get("est_son_tour") is True:
        return []
    return d.get("move")


def verdicts_portee_non_lue(d) -> list:
    attendu = attendu_du_greffe(d)
    bloque = attendu == []
    v = [("l'ENTITE ne porte que l'ability mesuree",
          bool(d.get("kit_de_l_entite_est_le_bon")), d.get("abilities_de_l_entite")),
         ("regime NON DEGENERE : n_move == 1 et c'est la sortie",
          d.get("n_move") == 1 and d.get("move") == [d.get("sortie_attendue")],
          "%s %s" % (d.get("n_move"), d.get("move"))),
         ("la portee lue par le port est celle attendue du masque",
          (d.get("reach_port") is None) == bool(d.get("greffe")), d.get("reach_port")),
         ("le gate CASTER natif ne mord pas DEPUIS LA TUILE COURANTE",
          d.get("natif_caster_reason") == 0, d.get("natif_caster_noms")),
         ("l'attaque normale seule ne verse pas la tuile source",
          d.get("source_port_normale_seule") == [], d.get("source_port_normale_seule")),
         ("le natif verse ce que le masque PREDIT (%s)" % ("RIEN" if bloque else "la tuile source"),
          d.get("source_natif") == attendu,
          "natif=%s attendu=%s" % (d.get("source_natif"), attendu)),
         ("le port est d'accord",
          d.get("source_port") == d.get("source_natif"),
          "port=%s natif=%s" % (d.get("source_port"), d.get("source_natif")))]
    if not bloque:
        # ⚠ CETTE contre-epreuve n'appartient QU'AU sous-pas `portee_non_lue` : c'est lui, et lui
        # seul, qui mute le masque en RETIRANT le bit 15. Le sous-pas `has_not_moved` mute la 2e
        # CLAUSE de `CasterHasNotMoved` et garde le bit (`0x8014`) -- l'assertion y echouait donc
        # PAR CONSTRUCTION, et rendait `master` rouge sur `--step has_not_moved` en accusant le
        # port alors que les sept assertions de fond etaient vertes. Sa place est ici.
        v.append(("contre-epreuve : le masque est REELLEMENT mute",
                  int(d.get("masque_mute_sans_bit15") or "0x0", 16)
                  & int(TR.CasterIsPossibleTarget) == 0, d.get("masque_mute_sans_bit15")))
        v.append(("contre-epreuve : sans le bit 15 le port PERD la tuile",
                  d.get("source_port_sans_bit15") == [] and d.get("source_port") != [],
                  d.get("source_port_sans_bit15")))
    else:
        # La 2e clause de `CasterHasNotMoved` est ce qui produit le refus : sans elle, le port
        # verserait la tuile que le natif refuse. Un bras mute IDENTIQUE au temoin ne prouverait
        # rien -- on exige donc qu'il DIFFERE.
        v.append(("contre-epreuve : sans la 2e clause le port verse ce que le natif REFUSE",
                  d.get("source_port_sans_clause2") == d.get("move")
                  and d.get("source_port") == [],
                  d.get("source_port_sans_clause2")))
    return v


# ------------------------------------------------------------------------------------------------
# VERDICT
# ------------------------------------------------------------------------------------------------

def verdicts(res) -> list:
    """Les verdicts, dans l'ordre : le REGIME d'abord (sans quoi le discriminant ne discrimine
    rien), puis les quatre postes, puis les DEUX contre-epreuves."""
    P = res.get("postes") or {}
    v = []
    for cle in ("creed_bit", "bullgryn_sans_bit", "ork_gate_passe", "ork_gate_mord",
                "temoin_ouvert"):
        if cle not in P or P[cle].get("error"):
            v.append(("montage %s" % cle, False,
                      (P.get(cle) or {}).get("error") or "poste absent"))
    if v:
        return v
    creed, bull = P["creed_bit"], P["bullgryn_sans_bit"]
    ork_p, ork_m, ouvert = P["ork_gate_passe"], P["ork_gate_mord"], P["temoin_ouvert"]

    # 1. LE REGIME. Un movable set SINGLETON, et sa tuile est bien la sortie du cul-de-sac.
    for d in (creed, bull, ork_p, ork_m):
        v.append(("regime NON DEGENERE (%s) : n_move == 1 et c'est la sortie" % d["visual"],
                  d["n_move"] == 1 and d["move"] == [d["sortie_attendue"]],
                  "n_move=%d move=%s attendu=%s" % (d["n_move"], d["move"],
                                                    d["sortie_attendue"])))
    # 2. LE TEMOIN DEGENERE. Sans bit 15, ses positions candidates sont QUAND MEME dans la menace
    #    -- couvertes les unes depuis les autres. C'est la mesure qui interdit de lire un verdict
    #    dans ce regime.
    v.append(("temoin OUVERT : regime effectivement degenere",
              ouvert["n_move"] >= 2 and ouvert["source_natif"] == ouvert["move"],
              "n_move=%d source_natif=%d/%d" % (ouvert["n_move"], len(ouvert["source_natif"]),
                                                ouvert["n_move"])))
    # 3. LE DISCRIMINANT.
    v.append(("INCLUSION : bit 15 sans gate -> le natif verse la tuile source",
              creed["source_natif"] == creed["move"], creed["source_natif"]))
    v.append(("EXCLUSION : sans le bit -> le natif ne la verse PAS",
              bull["source_natif"] == [], bull["source_natif"]))
    v.append(("INCLUSION : le port est d'accord (bit)",
              creed["source_port"] == creed["source_natif"], creed["source_port"]))
    v.append(("EXCLUSION : le port est d'accord (sans bit)",
              bull["source_port"] == bull["source_natif"], bull["source_port"]))
    # 4. LE BLOCAGE, MESURE. Meme ability, meme bit : c'est le GATE qui separe.
    v.append(("gate PASSE (ennemi contre la sortie) : casterReason == 0",
              ork_p["natif_caster_reason"] == 0, ork_p["natif_caster_noms"]))
    v.append(("gate MORD (aucun ennemi) : casterReason == TargetMatchesDynamicRule",
              ork_p["natif_caster_reason"] is not None
              and ork_m["natif_caster_reason"] == GATE_MORD_CODE, ork_m["natif_caster_noms"]))
    v.append(("gate PASSE -> le natif verse la tuile source",
              ork_p["source_natif"] == ork_p["move"], ork_p["source_natif"]))
    v.append(("gate MORD -> le natif ne la verse PAS, MEME masque",
              ork_m["source_natif"] == [], ork_m["source_natif"]))
    v.append(("le port suit le gate sur les deux Runtherd",
              ork_p["source_port"] == ork_p["source_natif"]
              and ork_m["source_port"] == ork_m["source_natif"],
              [ork_p["source_port"], ork_m["source_port"]]))
    # 5. CONTRE-EPREUVE bit 15 -- et le bras mute doit DIFFERER du bras temoin.
    v.append(("contre-epreuve : le masque est REELLEMENT mute",
              int(creed["masque_mute_sans_bit15"], 16) & int(TR.CasterIsPossibleTarget) == 0,
              creed["masque_mute_sans_bit15"]))
    v.append(("contre-epreuve : sans le bit 15 le port PERD la tuile (creed)",
              creed["source_port_sans_bit15"] == [] and creed["source_port"] != [],
              creed["source_port_sans_bit15"]))
    v.append(("contre-epreuve : sans le bit 15 le port PERD la tuile (ork qui passe)",
              ork_p["source_port_sans_bit15"] == [] and ork_p["source_port"] != [],
              ork_p["source_port_sans_bit15"]))
    v.append(("contre-epreuve : le CONTROLE ne bouge pas (rien a desarmer)",
              bull["source_port_sans_bit15"] == bull["source_port"],
              bull["source_port_sans_bit15"]))
    # 6. CONTRE-EPREUVE gate 4 -- sans lui, le port verse la tuile que le natif refuse.
    v.append(("contre-epreuve : sans le 4e gate le port verse la tuile que le natif refuse",
              ork_m["source_port_sans_gate4"] == ork_m["move"] and ork_m["source_natif"] == [],
              ork_m["source_port_sans_gate4"]))
    # 7. L'ATTAQUE NORMALE ne verse JAMAIS la tuile source -- l'etage isole, pour attribuer.
    for d in (creed, bull, ork_p, ork_m):
        v.append(("attaque normale seule : aucune tuile source (%s)" % d["visual"],
                  d["source_port_normale_seule"] == [], d["source_port_normale_seule"]))
    # 8. LA ZONE ENTIERE, VENTILEE et non agregee : `fp_normale` est le residu du terme d'ATTAQUE
    #    NORMALE (LoS / elevation / walkability), PREEXISTANT et hors de cette tranche ; ce qui lui
    #    est imputable est `fp \ fp_normale` et tout `fn`. Confondre les deux ferait accuser cette
    #    tranche d'un ecart qu'elle n'a pas cree.
    for cle in ("creed_bit", "bullgryn_sans_bit", "ork_gate_passe", "ork_gate_mord"):
        d = P[cle]
        impute = [t for t in d["fp"] if t not in d["fp_normale"]]
        v.append(("zone entiere (%s) : aucun ecart IMPUTABLE a la couche ability" % cle,
                  not impute and not d["fn"],
                  "fp_impute=%s fn=%s (residu normale=%d)"
                  % (impute, d["fn"], len(d["fp_normale"]))))
    return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="offline",
                    choices=("offline", "geometrie", "masques", "live", "portee_non_lue",
                             "has_not_moved"))
    ap.add_argument("--board", default=None)
    ap.add_argument("--ability", type=int, default=None,
                    help="step portee_non_lue : l'ability GREFFEE (defaut 1215 ; 1216 est l'autre "
                         "membre du gisement, et il arme en plus `CasterHasNotMoved`)")
    args = ap.parse_args(argv)
    rc = 0

    if args.step in ("offline", "geometrie"):
        g = geometrie(args.board)
        print("== GEOMETRIE (%s) ==" % g["board"])
        print("   tuiles marchables : %d ; culs-de-sac (degre 1) : %d ; ouvertes (degre 6) : %d"
              % (g["tuiles_marchables"], len(g["culs_de_sac"]), len(g["ouverts_degre_6"])))
        print("   culs-de-sac : %s" % g["culs_de_sac"])
        for k in ("postes_isoles_sont_des_culs_de_sac", "temoin_est_ouvert",
                  "ennemi_ouvre_est_adjacent_a_la_sortie",
                  "ennemi_loin_nest_adjacent_a_aucune_sortie"):
            print("   %-42s %s" % (k, g[k]))
            rc = max(rc, 0 if g[k] else 1)
        if args.step == "geometrie":
            return rc

    if args.step in ("offline", "masques"):
        m = masques()
        print("== MASQUES ==")
        for k, d in m.items():
            print("   %-20s %4d %-10s bit15=%-5s gate=%-11s reach=%-4s threat=%-3s d0=%s kit=%s"
                  % (k, d["ability"], d["rules"], d["bit15"], d["gate_caster"],
                     d["reach_ability"], d["threat_reach"], d["zone_d0"], d["kit"]))
        for nom, ok in masques_discriminants(m):
            print("   %-64s %s" % (nom, "OK" if ok else "FAIL"))
            rc = max(rc, 0 if ok else 1)
        if args.step == "masques":
            return rc

    if args.step == "live":
        sid = _resolve_session()
        res = live(sid, args.board)
        print("[RAW] " + json.dumps(res, sort_keys=True, default=str))
        if res.get("error"):
            print("VERDICT live: %s" % res["error"])
            return 2
        print("== POSTES (board %s, runner %s) ==" % (res["board"], res["runner"]))
        for cle, d in (res.get("postes") or {}).items():
            if d.get("error"):
                print("   %-18s ERREUR %s" % (cle, d["error"]))
                continue
            print("   %-18s %-15s a%-5d n_move=%d move=%s  casterReason=%s %s"
                  % (cle, d["visual"], d["ability"], d["n_move"], d["move"],
                     d["natif_caster_reason"], d["natif_caster_noms"]))
            print("        source natif=%s port=%s sans_bit15=%s sans_gate4=%s "
                  "normale_seule=%s | zone natif=%d port=%d FP=%d FN=%d"
                  % (d["source_natif"], d["source_port"], d["source_port_sans_bit15"],
                     d["source_port_sans_gate4"], d["source_port_normale_seule"],
                     d["n_natif"], d["n_port"], len(d["fp"]), len(d["fn"])))
        vs = verdicts(res)
        for nom, ok, det in vs:
            print("   %-62s %-4s %s" % (nom, "OK" if ok else "FAIL", det))
        rc = 0 if all(ok for _n, ok, _d in vs) else 1
        print("VERDICT live: %s" % ("EXACT" if rc == 0 else "ECART"))

    if args.step in ("portee_non_lue", "has_not_moved"):
        sid = _resolve_session()
        if args.step == "has_not_moved":
            vis, aid = POOL_HAS_NOT_MOVED
            d = portee_non_lue(sid, args.board, args.ability or aid, vis)
        else:
            d = portee_non_lue(sid, args.board, args.ability)
        print("[RAW] " + json.dumps(d, sort_keys=True, default=str))
        if d.get("error"):
            print("VERDICT portee_non_lue: %s" % d["error"])
            return 2
        for nom, ok, det in verdicts_portee_non_lue(d):
            print("   %-62s %-4s %s" % (nom, "OK" if ok else "FAIL", det))
        rc = 0 if all(ok for _n, ok, _d in verdicts_portee_non_lue(d)) else 1
        print("VERDICT portee_non_lue: %s" % ("EXACT" if rc == 0 else "ECART"))
    return rc


if __name__ == "__main__":                                                # pragma: no cover
    raise SystemExit(main())
