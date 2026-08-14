"""#1077 -- MESURE live des deux passifs portes : `FiringPosition` (effet 1150) et
`MischiefMakers` (ability 1471 -> effet 1469).

CE QU'IL MESURE, ET POURQUOI CES MONTAGES-LA
================================================================================================
Les DEUX porteurs sont des couples **summon + npc jumeau** (`blackSmnHavoc`/`blackNpc4Havoc`,
`deathSmnNurglings`/`deathNpc3Nurglings`, apparies par `visualId`). Aucun des deux summons n'a
d'invocateur atteignable -- balayage EXHAUSTIF du gameconfig (toute chaine de l'arbre) :
`EnvFactionSummons:EmperorsChildren` n'est portee par aucune unite (seulement par
`liveEvents.idunLiveEventConfigs[].factionWarData`), `EnvFactionSummons:DeathGuard` par rien du
tout. La voie est donc le JUMEAU NPC via `--explicit-stats <id>:45` (case-92 Sec.5bis recours 4) :
un MIRROR du porteur avec SES stats, SES traits et SES armes, pas une greffe.

⚠ **PALIER 45 = CONDITION D'OBSERVABILITE**, pas une preference (leçon #1052) : au palier 1 le
Havoc n'a pas de quoi tuer en un tir, donc le trigger `LegitDeathReasons` ne se leve jamais et les
deux regimes rendraient le MEME resultat -- un accord en regime degenere.

* **MischiefMakers** -- volet EFFET + TIRAGE. Le Nurglings porte une attaque NORMALE sur une cible ;
  on compare les effets POSES live vs port. Le temoin n'est pas la seule PRESENCE de 1469 : c'est
  `attack_query.has_heal_blockers(cible)`, le predicat que lisent reellement les trois gates natifs
  (SOIN / REPARATION / RESURRECTION). DEUX contre-epreuves par MUTATION, a DEUX etages distincts :
    (A) `ABILITY_TRIGGERS.pop("MischiefMakers")`  -> l'ability ne fire plus du tout ;
    (B) `EFFECT_CLASSES.pop("MischiefMakers")`    -> l'effet est POSE mais materialise en
        `BaseEffect` nu, donc `has_heal_blockers` retombe a False. C'est CETTE mutation-la qui
        prouve que l'inscription au registre MORD -- (A) seule ne la distinguerait pas.

* **FiringPosition** -- volet TRIGGER. Le Havoc entre en bataille avec 1009 `Overwatch_AutoAttack`
  (trait `Overwatch`) ET 1150, pose a l'init par `AOwnerEffectTriggeredAbility`. Une unite ramenee
  a 1 PV se DEPLACE dans son rayon : le tir d'overwatch la tue, et le porteur doit recevoir 1151
  `FiringPosition_HitReduction` = `EXTRA_HITS -2`. **Le `-2` est le discriminant** : ses deux
  classes soeurs deja portees valent `-1` (1146 pour `EarlyWarningOverride`, 1019 pour
  `InescapableDeath`), donc un port qui aurait recopie le voisin de forme rendrait `-1`.
  MUTATION : `EFFECT_TRIGGERS.pop(1150)` -> plus de 1151.
  ⚠ TROIS pieges de montage, tous MESURES et tous corriges dans les constantes ci-dessous :
  `--hp-target` vise les a-units (donc le Havoc) et non la victime ; aux SpawnPoints les deux
  unites sont a **7** hexes, hors de portee en un tour ; et avec UN SEUL p-unit, son kill termine
  la bataille et `decisionView` ne rend plus le porteur du tout.

USAGE
    python probe_1077_firing_position_mischief_makers.py --volet mischief
    python probe_1077_firing_position_mischief_makers.py --volet firing
Sorties ASCII (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from rl_collect_batch import _rpc, _resolve_session          # noqa: E402

SEED = "777"
BOARD = "MC1_67"

#: PALIER 45 = `units.npc[].stats[44]`, le DERNIER des 45 (les deux npc en ont autant).
HAVOC = "blackNpc4Havoc:45"
HAVOC_VIS = "blackNpc4Havoc"
NURGLINGS = "deathNpc3Nurglings:45"
NURGLINGS_VIS = "deathNpc3Nurglings"
#: Temoin des deux volets : une seule arme, aucun trait d'aura qui change le nombre de coups RECUS
#: par un voisin (le piege `BigTarget` de #1052-r3).
CIBLE = "orksNob"

#: GEOMETRIE du volet `firing`, posee au build (cf. le commentaire du `--place` ci-dessous).
#: Distance 3 -> la victime entre dans le rayon d'overwatch (arme `Projectile` Range 2) en UN
#: deplacement, ce que les SpawnPoints du board (7 hexes d'ecart) rendaient impossible.
HAVOC_TILE = (3, 3)
VICTIME_TILE = (3, 6)
#: SECONDE unite de mon camp, posee LOIN et laissee intacte. Elle n'a qu'un role : **la bataille ne
#: doit pas se terminer a la mort de la victime**. Mesure : avec un seul p-unit a 1 PV, son kill
#: vide le camp, `decisionView` ne rend plus le Havoc du tout (`hav2 is None`) et l'observable de la
#: tranche -- les effets du PORTEUR apres le kill -- devient illisible.
SURVIVANT = "orksNob"
SURVIVANT_TILE = (0, 0)
#: La VICTIME du tir d'overwatch : une unite DISTINCTE, ramenee a 1 PV par `--unit-stat` (per-unit),
#: pas par `--hp-player` (qui ecraserait tout le camp, survivant compris).
VICTIME = "adeptHospitaller"

MISCHIEF_MAKERS_EFFECT = 1469        # `EffectType.MischiefMakers`
PINNED = 1065                        # `EffectType.Pinned` (<< Suppress >> cote i2)
FIRING_POSITION_REACTIVATE = 1150    # `EffectType.FiringPosition_ReactivateOverwatch`
FIRING_POSITION_HIT_RED = 1151       # `EffectType.FiringPosition_HitReduction`
OVERWATCH = 1009                     # `EffectType.Overwatch_AutoAttack`


# --------------------------------------------------------------------------------- harnais runner

def _build(state_file: str, extra: list, build_runner=None) -> dict:
    """`rl_duel build` en sous-processus, `--state-file` ABSOLU et unique (discipline runner.md)."""
    if build_runner is not None:
        return {"rc": 0, "rid": build_runner(SEED, extra=list(extra), board=BOARD)["rid"],
                "stdout": "", "stderr": ""}
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
           "--state-file", state_file, *extra]
    r = subprocess.run(cmd, cwd=str(_HERE), capture_output=True, text=True, timeout=900)
    out = {"rc": r.returncode, "stdout": (r.stdout or "")[-3000:], "stderr": (r.stderr or "")[-2000:]}
    try:
        out["rid"] = json.loads(Path(state_file).read_text(encoding="utf-8")).get("runnerId")
    except Exception as exc:                                  # noqa: BLE001
        out["rid"] = None
        out["why"] = "state-file illisible : %s" % exc
    return out


def _dispose(sid, rid, build_runner=None):
    if build_runner is not None:
        return
    if rid is not None:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:                                     # noqa: BLE001
            pass


def _res(sid, method, args, timeout=90):
    return (_rpc(sid, method, [args], timeout=timeout) or {}).get("result") or {}


def _dv(sid, rid):
    return _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _eff_ids(u):
    return sorted(int(e["effectType"]) for e in ((u or {}).get("effects") or []))


def _normal_attack_type(u):
    for ab in ((u or {}).get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    return None


def _board_of(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = _res(sid, "boardGraph", {"runnerId": rid}, 60)
    return Board(bg["tiles"], adjacency="native_sym") if bg.get("tiles") else None


def _reach_turn(sid, rid, player, max_end=8):
    dv = _dv(sid, rid)
    for _ in range(max_end):
        if dv.get("currentPlayer") == player:
            return dv
        _res(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv = _dv(sid, rid)
    return dv


def _snapshot(sid, rid):
    return {
        "dv": _dv(sid, rid),
        "ob": _res(sid, "observeBattle", {"runnerId": rid}, 60),
        "snap": _res(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "rng": _res(sid, "dumpRng", {"runnerId": rid}, 30),
    }


def _offline_state(s, board):
    """Etat OFFLINE rejouable, PRNG cale sur celui du natif (`dumpRng`) -- indispensable ici :
    `MischiefMakers` consomme un `next_bool` par attaque."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    st = load_state(s["dv"], s["ob"], s["snap"], board=board)
    r = s.get("rng") or {}
    if r.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(r["mt"])
        rng.mti = r["mti"]
        st.rng = rng
    return st


def _uid_by_vis(st, vis):
    from engine.runner.components import StatsComponent
    for uid, e in st.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _port_effect_ids(st, uid):
    lst = (st.effects.by_unit.get(int(uid)) or []) if st.effects is not None else []
    return sorted(int(getattr(e, "effect_type", -1)) for e in lst)


def _diag_montage(st, uid, nom_classe: str) -> dict:
    """DECOMPOSITION PAR ETAGE d'un `ABILITY_TRIGGERS` muet : le port peut echouer AVANT `matches`
    (passif non monte parce que le substrat `passive_abilities` MESURE ne le porte pas, ou parce que
    le `visual_id` ne resout pas au kit). Sans ce diagnostic on fitterait le mauvais etage."""
    from engine.runner.components import StatsComponent
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    sc = st.get_entity(int(uid)).get_component(StatsComponent)
    ctx = getattr(sc, "ctx", None)
    montes = [type(t).__name__ for t in collect_triggered_abilities(st)
              if int(getattr(t, "owner_id", -1)) == int(uid)]
    return {
        "visual_id": getattr(ctx, "visual_id", None),
        "passive_abilities_mesurees": getattr(ctx, "passive_abilities", None),
        "traits": list(getattr(ctx, "traits", None) or [])[:10],
        "triggers_montes": montes,
        "classe_montee": any(nom_classe in m for m in montes),
    }


# ============================================================================== volet MischiefMakers

def volet_mischief(sid, state_file, build_runner=None) -> dict:
    """Le Nurglings porte une attaque NORMALE ; on compare les effets poses live vs port, avec DEUX
    mutations a deux etages (registre d'ability, registre de classe d'effet)."""
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner

    out = {"volet": "mischief", "ok": False}
    b = _build(state_file, ["--p-units", CIBLE, "--a-units", NURGLINGS,
                            "--explicit-stats", NURGLINGS, "--roster", "1",
                            "--crit", "0,0", "--block-target", "0,0"], build_runner)
    out["build_rc"] = b["rc"]
    rid = b.get("rid")
    out["rid"] = rid
    if rid is None:
        out["why"] = "build KO : %s" % (b.get("stderr") or b.get("stdout"))[-600:]
        return out
    try:
        board = _board_of(sid, rid)
        if board is None:
            out["why"] = "boardGraph indispo"
            return out
        dv = _dv(sid, rid)
        car = _by_vis(dv, NURGLINGS_VIS)
        cib = _by_vis(dv, CIBLE)
        if car is None or cib is None:
            out["why"] = "unites absentes : %s" % sorted({u.get("visualId") for u in _alive(dv)})
            return out

        # DRIVE des positions : on AMENE le porteur au contact, on ne subit pas la geometrie de spawn.
        dv = _reach_turn(sid, rid, car.get("owner"))
        car, cib = _by_vis(dv, NURGLINGS_VIS), _by_vis(dv, CIBLE)
        voisines = [board.coord(t) for t in board.neighbours(board.id_at(*_pos(cib)))
                    if board.walkable(t)]
        occ = {_pos(u) for u in _alive(dv)}
        libres = [c for c in voisines if c not in occ]
        if libres:
            import hexgeo
            best = min(libres, key=lambda q: hexgeo.distance(q, _pos(car)))
            _res(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(car["id"]),
                "to": {"col": best[0], "row": best[1]}}}, 60)
        dv = _dv(sid, rid)
        car, cib = _by_vis(dv, NURGLINGS_VIS), _by_vis(dv, CIBLE)
        out["pos"] = {"caster": _pos(car), "cible": _pos(cib)}
        out["effets_cible_avant"] = _eff_ids(cib)

        nat = _normal_attack_type(car)
        if nat is None:
            out["why"] = "pas d'attaque normale exposee"
            return out

        s = _snapshot(sid, rid)
        act = _res(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(car["id"]), "targetId": int(cib["id"]),
            "abilityType": int(nat)}}, 120)
        a0 = (act.get("actions") or [{}])[0]
        out["live_ok"] = bool(a0.get("ok"))
        dv2 = _dv(sid, rid)
        cib2 = _by_vis(dv2, CIBLE)
        out["effets_cible_apres_live"] = _eff_ids(cib2)
        out["live_pose_1469"] = MISCHIEF_MAKERS_EFFECT in out["effets_cible_apres_live"]
        out["live_pose_pinned"] = PINNED in out["effets_cible_apres_live"]
        out["live_duree_1469"] = next(
            (e.get("turnsLeft") for e in ((cib2 or {}).get("effects") or [])
             if int(e.get("effectType", -1)) == MISCHIEF_MAKERS_EFFECT), None)
        # TEMOIN PRNG -- le `Maybe` consomme UN `next_bool`. Comparer les `mti` du MT19937 avant et
        # apres, des DEUX cotes, dit si le port a consomme le MEME NOMBRE de tirages au MEME rang.
        # C'est le seul observable qui voie le tirage QUAND IL NE TOMBE PAS (le cas le plus
        # frequent a 25 %) : sans lui, un port qui aurait OUBLIE le `Maybe` serait vert 3 fois sur 4.
        out["mti_avant"] = (s.get("rng") or {}).get("mti")
        out["mti_apres_live"] = _res(sid, "dumpRng", {"runnerId": rid}, 30).get("mti")

        from engine.entities.effects import factory as F
        from engine.runner.abilities import attack_query as AQ
        from engine.runner.operations.triggers.dispatch import registry as REG

        def _port(regime: str) -> dict:
            """`avec` = registres INTACTS ; `sans_ability` / `sans_classe` = les deux mutations."""
            sauve_ab = REG.ABILITY_TRIGGERS.get("MischiefMakers")
            sauve_cl = F.EFFECT_CLASSES.get("MischiefMakers")
            try:
                if regime == "sans_ability":
                    REG.ABILITY_TRIGGERS.pop("MischiefMakers", None)
                if regime == "sans_classe":
                    F.EFFECT_CLASSES.pop("MischiefMakers", None)
                st = _offline_state(s, board)
                u_car, u_cib = _uid_by_vis(st, NURGLINGS_VIS), _uid_by_vis(st, CIBLE)
                if u_car is None or u_cib is None:
                    return {"why": "uid introuvable offline"}
                diag = _diag_montage(st, u_car, "MischiefMakers")
                r = Runner(st).install_default_handlers(20)
                r.apply(AttackUnitMessage(attacker_id=int(u_car), target_id=int(u_cib)))
                effs = _port_effect_ids(st, u_cib)
                return {
                    "diag": diag,
                    "effets_cible": effs,
                    "pose_1469": MISCHIEF_MAKERS_EFFECT in effs,
                    "pose_pinned": PINNED in effs,
                    # LE TEMOIN : le predicat que lisent reellement les gates natifs SOIN /
                    # REPARATION / RESURRECTION -- pas la seule presence d'un effectType.
                    "has_heal_blockers": bool(AQ.has_heal_blockers(st, int(u_cib))),
                    "mti_apres": getattr(st.rng, "mti", None),
                    "trigs": [e for e in (r.damage_handler.after_hit or [])
                              if isinstance(e, dict) and e.get("passive") == "MischiefMakers"],
                }
            finally:
                if sauve_ab is not None:
                    REG.ABILITY_TRIGGERS["MischiefMakers"] = sauve_ab
                if sauve_cl is not None:
                    F.EFFECT_CLASSES["MischiefMakers"] = sauve_cl

        out["port_avec"] = _port("avec")
        out["port_sans_ability"] = _port("sans_ability")
        out["port_sans_classe"] = _port("sans_classe")

        pa, sa, sc = out["port_avec"], out["port_sans_ability"], out["port_sans_classe"]
        out["accord_1469"] = (out["live_pose_1469"] == pa.get("pose_1469") is True)
        out["accord_pinned"] = (out["live_pose_pinned"] == pa.get("pose_pinned"))
        # NON DEGENERE : les trois regimes doivent SEPARER le temoin.
        out["mutation_A_mord"] = (pa.get("pose_1469") is True and sa.get("pose_1469") is False)
        out["mutation_B_mord"] = (pa.get("has_heal_blockers") is True
                                  and sc.get("has_heal_blockers") is False
                                  and sc.get("pose_1469") is True)
        # Le tirage du `Maybe` a-t-il ete consomme des DEUX cotes, au meme rang ? Le regime SANS
        # l'ability ne doit PAS le consommer -- c'est ce qui rend ce temoin non degenere.
        out["mti_apres_port"] = pa.get("mti_apres")
        out["accord_mti"] = (out.get("mti_apres_live") is not None
                             and out["mti_apres_live"] == pa.get("mti_apres"))
        out["mti_sans_ability"] = sa.get("mti_apres")
        out["tirage_maybe_consomme"] = (pa.get("mti_apres") is not None
                                        and sa.get("mti_apres") is not None
                                        and pa["mti_apres"] != sa["mti_apres"])
        out["ok"] = bool(out["accord_1469"] and out["accord_pinned"]
                         and out["mutation_A_mord"] and out["mutation_B_mord"]
                         and out["accord_mti"] and out["tirage_maybe_consomme"])
        return out
    finally:
        _dispose(sid, rid, build_runner)


# ============================================================================== volet FiringPosition

def volet_firing(sid, state_file, build_runner=None) -> dict:
    """Une unite a 1 PV entre dans le rayon du Havoc : le tir d'overwatch la tue, le porteur doit
    recevoir 1151 `EXTRA_HITS -2` et RESTER en overwatch."""
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.runner import Runner

    out = {"volet": "firing", "ok": False}
    # ⚠ `--hp-player` (p-units), PAS `--hp-target` (a-units) : c'est la VICTIME qui doit etre
    # fragile, pas le Havoc. Mesure : avec `--hp-target 1` le tir d'overwatch ne tuait pas et les
    # deux regimes rendaient le MEME resultat -- un accord en regime degenere.
    # ⚠ GEOMETRIE PILOTEE, pas subie : aux SpawnPoints du board les deux unites sont a **7** hexes,
    # la victime ne peut pas entrer dans le rayon d'overwatch (Range 2) en un deplacement, et le
    # scenario ne se produit JAMAIS. `--place`/`--a-place` les posent a distance 3 -- MC1_67 est
    # 7x9 et ses 63 tuiles sont toutes jouables, donc ces deux-la sont valides par construction
    # (et `rl_duel` VERIFIE la position obtenue apres le build).
    b = _build(state_file, ["--p-units", "%s,%s" % (VICTIME, SURVIVANT), "--a-units", HAVOC,
                            "--explicit-stats", HAVOC, "--roster", "2",
                            "--place", "%s:%d,%d" % (VICTIME, VICTIME_TILE[0], VICTIME_TILE[1]),
                            "--place", "%s:%d,%d" % (SURVIVANT, SURVIVANT_TILE[0], SURVIVANT_TILE[1]),
                            "--a-place", "%s:%d,%d" % (HAVOC, HAVOC_TILE[0], HAVOC_TILE[1]),
                            "--unit-stat", "%s:Health=1,RemainingHealth=1,Armor=0,FixedArmor=0" % VICTIME,
                            "--crit", "0,0", "--block-target", "0,0"],
               build_runner)
    out["build_rc"] = b["rc"]
    rid = b.get("rid")
    out["rid"] = rid
    if rid is None:
        out["why"] = "build KO : %s" % (b.get("stderr") or b.get("stdout"))[-600:]
        return out
    try:
        board = _board_of(sid, rid)
        if board is None:
            out["why"] = "boardGraph indispo"
            return out
        import hexgeo
        dv = _dv(sid, rid)
        hav = _by_vis(dv, HAVOC_VIS)
        vic = _by_vis(dv, VICTIME)
        if hav is None or vic is None:
            out["why"] = "unites absentes : %s" % sorted({u.get("visualId") for u in _alive(dv)})
            return out
        # OBSERVABLE #1 -- l'owner-effect POSE A L'INIT par `AOwnerEffectTriggeredAbility`.
        out["effets_havoc_init"] = _eff_ids(hav)
        out["live_init_1150"] = FIRING_POSITION_REACTIVATE in out["effets_havoc_init"]
        out["live_init_overwatch"] = OVERWATCH in out["effets_havoc_init"]

        out["pos_initiales"] = {"havoc": _pos(hav), "victime": _pos(vic),
                                "distance": hexgeo.distance(_pos(hav), _pos(vic))}
        # DRIVE : la victime (mon camp, 1 PV) entre dans le rayon du Havoc.
        dv = _reach_turn(sid, rid, vic.get("owner"))
        hav, vic = _by_vis(dv, HAVOC_VIS), _by_vis(dv, VICTIME)
        # TRACE : les effets du Havoc APRES la prise de main, avant tout mouvement. Sans elle, une
        # disparition de 1009/1150 (overwatch consomme, effet purge) accuserait le mouvement a tort.
        out["effets_havoc_avant_move"] = _eff_ids(hav)
        hpos = _pos(hav)
        mv = _res(sid, "aiMovableTiles", {"runnerId": rid}, 90) or {}
        tiles = next(([(t["col"], t["row"]) for t in (u.get("tiles") or [])]
                      for u in (mv.get("units") or [])
                      if int(u.get("unitId", -1)) == int(vic["id"])), [])
        if not tiles:
            out["why"] = "aucune tuile atteignable pour la victime"
            return out
        best = min(tiles, key=lambda q: hexgeo.distance(q, hpos))
        out["cible_va_en"] = best
        out["distance_finale"] = hexgeo.distance(best, hpos)
        out["tuiles_atteignables"] = len(tiles)
        out["meilleure_distance_atteignable"] = min(hexgeo.distance(q, hpos) for q in tiles)

        s = _snapshot(sid, rid)
        # PV publies par le NATIF, avant et apres le move -- ils QUALIFIENT le `hp_victime` du port.
        # Sans eux, un `[0, 0]` cote port se lit comme « la victime etait deja morte », donc comme
        # un scenario vide, alors que le trigger a bel et bien fire des deux cotes.
        out["hp_live_avant"] = {int(u["squadId"]): u["hp"]
                                for u in ((s["ob"] or {}).get("units") or [])}
        _res(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": int(vic["id"]),
            "to": {"col": best[0], "row": best[1]}}}, 120)
        out["hp_live_apres"] = {int(u["squadId"]): u["hp"] for u in
                                ((_res(sid, "observeBattle", {"runnerId": rid}, 60) or {})
                                 .get("units") or [])}
        dv2 = _dv(sid, rid)
        hav2 = _by_vis(dv2, HAVOC_VIS)
        vic2 = _by_vis(dv2, VICTIME)
        out["victime_morte_live"] = not bool((vic2 or {}).get("alive"))
        out["effets_havoc_apres_live"] = _eff_ids(hav2)
        out["live_pose_1151"] = FIRING_POSITION_HIT_RED in out["effets_havoc_apres_live"]
        out["live_garde_overwatch"] = OVERWATCH in out["effets_havoc_apres_live"]
        # Le stat-mod porte par 1151, tel que le natif le publie.
        out["live_statmod_1151"] = _res(sid, "statModSources", {"runnerId": rid,
                                                               "unitId": int(hav2["id"])}, 90)

        from engine.runner.operations.triggers.dispatch import registry as REG

        def _port(avec: bool) -> dict:
            sauve = REG.EFFECT_TRIGGERS.get(FIRING_POSITION_REACTIVATE)
            try:
                if not avec:
                    REG.EFFECT_TRIGGERS.pop(FIRING_POSITION_REACTIVATE, None)
                st = _offline_state(s, board)
                u_hav, u_vic = _uid_by_vis(st, HAVOC_VIS), _uid_by_vis(st, VICTIME)
                if u_hav is None or u_vic is None:
                    return {"why": "uid introuvable offline"}
                from engine.runner.components import HealthComponent, StatsComponent
                # ⚠ CAPTURER LA VALEUR, PAS LA REFERENCE : `get_component` rend le MEME objet avant
                # et apres, donc `hc0.hp` relu dans le `return` vaut deja le hp d'APRES. Mesure : le
                # probe rendait `hp_victime = [0, 0]` sur un montage ou le natif publie 1 puis 0 --
                # un faux « la victime etait deja morte », donc un scenario qu'on aurait cru vide.
                _hc = st.get_entity(u_vic).get_component(HealthComponent)
                hp_avant = None if _hc is None else int(_hc.hp)
                r = Runner(st).install_default_handlers(20)
                r.apply(MoveUnitMessage(unit_id=int(u_vic), to=(int(best[0]), int(best[1]))))
                hc1 = st.get_entity(u_vic).get_component(HealthComponent)
                effs = _port_effect_ids(st, u_hav)
                sc = st.get_entity(u_hav).get_component(StatsComponent)
                from engine.entities.stats import StatType
                return {
                    "hp_victime": [hp_avant, None if hc1 is None else int(hc1.hp)],
                    "effets_havoc": effs,
                    "pose_1151": FIRING_POSITION_HIT_RED in effs,
                    "garde_overwatch": OVERWATCH in effs,
                    # LE DISCRIMINANT : -2 ici, -1 chez les deux classes soeurs deja portees.
                    "extra_hits": (None if sc is None
                                   else int(sc.ctx.stat(StatType.EXTRA_HITS))),
                }
            finally:
                if sauve is not None:
                    REG.EFFECT_TRIGGERS[FIRING_POSITION_REACTIVATE] = sauve

        out["port_avec"] = _port(True)
        out["port_sans"] = _port(False)
        pa, ps = out["port_avec"], out["port_sans"]
        out["accord_1151"] = (out["live_pose_1151"] == pa.get("pose_1151"))
        out["accord_overwatch"] = (out["live_garde_overwatch"] == pa.get("garde_overwatch"))
        out["mutation_mord"] = (pa.get("pose_1151") is True and ps.get("pose_1151") is False)
        out["hits_reduction_vaut_2"] = (pa.get("extra_hits") is not None
                                        and ps.get("extra_hits") is not None
                                        and (ps["extra_hits"] - pa["extra_hits"]) == 2)
        out["ok"] = bool(out["live_init_1150"] and out["accord_1151"]
                         and out["mutation_mord"] and out["hits_reduction_vaut_2"])
        return out
    finally:
        _dispose(sid, rid, build_runner)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#1077 FiringPosition / MischiefMakers -- mesure live")
    ap.add_argument("--volet", choices=("mischief", "firing"), required=True)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args(argv)
    sf = a.state_file or str(_HERE.parent.parent / "logs" / ("probe_1077_%s.json" % a.volet))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    fn = volet_mischief if a.volet == "mischief" else volet_firing
    res = fn(sid, sf)
    print(json.dumps(res, indent=1, default=str, ensure_ascii=True))
    print("VERDICT %s : %s" % (a.volet, "OK" if res.get("ok") else "KO"))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
