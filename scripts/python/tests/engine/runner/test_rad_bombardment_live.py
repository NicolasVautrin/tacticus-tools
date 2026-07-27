"""RadBombardment (actif 1116, `admecDominus` -- Dominus, HERO AdeptusMechanicus) : face COMBAT portee
-> arbre DSL, confrontee au LIVE sur DEUX geometries (1 puis >= 2 unites alignees) -- case-224.

`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1 -- cf. `abilities/admec.py`) :

    AActiveAbility.Execute( op_Addition( op_Addition(
        AttackWithAbilityDamage(caster@0x160, Units(GetAffectedTiles()), MinMaxDamage(0xc/0xd),
                                DamageProfileFromConfig, Get(GetHits() = ConfigConst(0x2f))),
        AddEffect(0x429 = 1065 Pinned, stateRef, source = caster@0x160, <les MEMES unites>) ),
      AddEffect(0x4dc = 1244 Contaminated, stateRef, GetAffectedTiles()) ) )   # surcharge 4-ARGS

    GetAffectedTiles() = SortReverse( TilesBehindInLine(CasterTile@0x168, TargetTiles@0x190,
                                      settings{+0x10 = 0, +0x11 = 1}, AffectedTileAmount()) )
                         op_Subtraction Blocking(<le meme>)
    AffectedTileAmount() = Sum( Get(1), RoundsStarted(caster@0x160),
                                TotalRepairActionsAmount(UnitsWithTrait(Friends(caster, AllUnits), 0xc)) )

CE QUE CES TESTS PROUVENT (lisent l'etat LIVE ; DRIVENT les positions ET l'aim ; state-file UNIQUE
dispose au teardown) :
  (1) EXECUTION REELLE : `ported=True` (garde anti-no-op -- AVANT ce port, 1116 etait ABSENT du registre
      COMBAT : `ported=False`, 0 degat, AUCUNE erreur. Mesure du 2026-07-26, runner MC1_67 : live 1 coup
      de 3389 + Pinned + 2 tuiles Contaminated / port RIEN -- divergence d'etat SILENCIEUSE).
  (2) GEOMETRIE DE LA LIGNE : l'ensemble des tuiles qui recoivent `Contaminated` (1244) LIVE ==
      l'ensemble calcule offline. C'est l'observable DIRECT de `GetAffectedTiles` : longueur
      (`AffectedTileAmount`), sens (`TilesBehindInLine` depuis l'aim en s'eloignant du caster), settings
      (`check_walkable=False` -> pas de gate d'elevation) et troncature (`- Blocking`).
  (3) DEGAT BIT-EXACT per-coup, PAR UNITE touchee (famille ABILITY = 1 tirage/coup).
  (4) `Pinned` (1065) sur CHAQUE unite touchee, live ET offline.
  (5) ORDRE DES CIBLES (geometrie 2) : le natif ENUMERE le selecteur TEL QUEL
      (`IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$Execute` n'a AUCUN `OrderBy`, contraste
      `AttackBehaviour$$Execute`) -> apres `SortReverse`, la tuile la PLUS LOINTAINE est frappee EN
      PREMIER. Le port le reproduit avec `Foreach` (et NON `multi=True`, qui folderait l'`OrderBy` de la
      famille ATTACK). Assertion : la sequence des cibles live == la sequence offline.

ORACLES DES PARAMS (#96) : `nrOfHits` et `damageProfile` sont lus BRUTS de
`gameconfig.ability("RadBombardment").constants` (le natif : `ConfigConst(0x2f)` +
`DamageProfileFromConfig`). La LONGUEUR de ligne n'a PAS d'oracle de config -- elle est CALCULEE
(`Sum(Get(1), RoundsStarted, TotalRepairActionsAmount)`) ; son oracle est donc le LIVE lui-meme
(l'ensemble des tuiles Contaminated), ce que (2) confronte.

CIBLES NON-DAEMON EXIGEES : une unite Daemon porte `Daemon_ExtraBlock` (1034), pour laquelle le natif
roule un jet de block que l'etage partage `AttackDamageOperation._block_sources` saute (gap chiffre par
`probe_daemon_extrablock_gap.py`, cf. `test_brazier_of_holy_fire_live`) -> desync RNG. Les rosters de ce
fichier sont donc explicitement sans Daemon, et une garde le VERIFIE.

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import pytest

import gameconfig as GC
from engine import battle_query as bq
from engine.entities.pathfinding.board import Board
from engine.entities.effect_type import EffectType
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.abilities.admec import RadBombardmentAbility
from engine.runner.abilities.handler import ABILITY_CLASSES

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "admecDominus"
# ESCORTE : une 2e unite dans MON camp, qui NE CASTE PAS. Elle existe pour une raison de MESURE (#98) :
# 1116 pose les turn-flags par defaut, donc le cast FINIT le tour du caster ; en 1v1 strict il n'y a plus
# d'unite activable -> le moteur natif BASCULE de joueur et TICKE (RefreshEffects) avant qu'on ne relise
# `decisionView` -- un `Pinned` fraichement pose peut alors avoir ete decremente/retire, et un
# `LivingMetal` avoir regenere. Avec une 2e unite, le joueur garde une activation : PAS de bascule, PAS
# de tick, la lecture est PRE-tick. Elle reste a son spawn (on ne deplace que le caster).
ESCORT_VIS = "adeptHospitaller"
ABILITY = 1116
PINNED = int(EffectType.Pinned)                              # 0x429 = 1065
CONTAMINATED = int(EffectType.Contaminated)                  # 0x4dc = 1244


def _const(key):
    v = ((GC.ability("RadBombardment") or {}).get("constants") or {}).get(key)
    assert v is not None, (f"oracle introuvable : gameconfig.ability('RadBombardment').constants.{key} "
                           f"absent -- le natif le lit en ConfigConst, il DOIT exister")
    return v


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _build(seed, a_units):
    sf = ROOT / "logs" / "runners" / f"radbomb-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "2", "--p-units", CASTER_VIS + "," + ESCORT_VIS,
         "--a-units", a_units],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _aim_positions(rpc, rid, cid):
    """Tuiles LEGALES du cast tile-target, SANS bouger (`fromHere`) -- le `.ctor` de 1116 pose
    `TargetingRange.CustomRange(1)`, donc ce sont les VOISINES du caster (= l'AIM = la direction)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ABILITY), {})
    out = []
    for x in (ab.get("fromHere") or []):
        t = x.get("tile") or {}
        if t.get("col") is not None:
            out.append((t["col"], t["row"]))
    return out, (ab.get("kind") or "")


def _drive_to_alignment(rpc, rid, board, want_targets: int):
    """DRIVE les positions (doctrine : jamais « bloque par la geometrie de spawn ») : avance jusqu'a mon
    tour, deplace le caster, et rend le 1er (cid, aim) dont la LIGNE couvre >= `want_targets` ennemis.
    La ligne prospective est calculee par `engine.battle_query.get_tiles_behind` -- le MEME mirror que le
    noeud `TilesBehindInLine` du port, avec les settings du call-site (`check_walkable=False`,
    `update_reference=True`). Renvoie (cid, aim, my_player) ou None."""
    def bfs(src):
        dist, q = {src: 0}, deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1
                    q.append(n)
        return dist

    wa, ea, te = bq.tiles_behind_accessors(None, None)
    my = None
    for _ in range(30):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster = _find(units, CASTER_VIS)
        if caster is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cid, cpos = caster["id"], _cr(caster)
        enemies = {_cr(u): u["id"] for u in units
                   if u.get("owner") != my and u.get("alive") and _cr(u)}
        if not enemies:
            return None
        aims, _kind = _aim_positions(rpc, rid, cid)
        best, bestn, best_disc = None, 0, False
        for aim in aims:
            line = bq.get_tiles_behind(cpos, aim, max_count=12, check_walkable=False,
                                       update_reference=True, walkable_at=wa, elevation_at=ea,
                                       tile_exists=te)
            hit = [enemies[p] for p in line if p in enemies]
            n = len(hit)
            # ORDRE apres `SortReverse` = ligne INVERSEE. Un aim est DISCRIMINANT vs un tri par id si
            # cet ordre-la n'est PAS l'ordre croissant des ids (sinon `multi=True` donnerait le meme
            # resultat et le test ne prouverait rien sur l'ordre).
            rev = list(reversed(hit))
            disc = n >= 2 and rev != sorted(rev)
            if (n > bestn) or (n == bestn and disc and not best_disc):
                best, bestn, best_disc = aim, n, disc
        if best is not None and bestn >= want_targets:
            return cid, best, my
        # pas encore : on se rapproche du BARYCENTRE des ennemis (augmente les chances d'alignement)
        target_pos = min(enemies, key=lambda p: sum(abs(p[0] - q[0]) + abs(p[1] - q[1])
                                                    for q in enemies))
        dist = bfs(board.id_at(*target_pos))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist and dist[t] >= 1]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        col, row = reach[min(pool, key=lambda t: dist[t])]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
    return None


def _cast_live(rpc, rid, cid, aim):
    """Cast LIVE tile-target (`to` = l'aim) ; rend la SEQUENCE (ordre natif) des (cible, Amount) et les
    flags crit/block/evade."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "abilityType": ABILITY,
        "to": {"col": aim[0], "row": aim[1]}}, "captureEvents": True}, 150)
    seq, flags = [], {"crit": False, "block": False, "evade": False}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                seq.append((td.get("Target_Id"), td.get("Amount")))
                flags["crit"] = flags["crit"] or bool(td.get("Attack_DidCrit"))
                flags["block"] = flags["block"] or bool(td.get("Attack_DidBlock"))
                flags["evade"] = flags["evade"] or bool(td.get("Attack_DidEvade"))
    return seq, flags, res


def _tile_effect_ids(rpc, rid, board, effect_type):
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out = set()
    for t in (tm.get("tiles") or []):
        if any(e.get("effectType") == effect_type for e in (t.get("effects") or [])):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out.add(tid)
    return out


def _run(rpc, a_units, want_targets, seed="777"):
    rid, sf, err = _build(seed, a_units)
    if rid is None:
        pytest.skip(f"build runner KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _drive_to_alignment(rpc, rid, board, want_targets)
        if placed is None:
            pytest.skip(f"aucune position/aim n'aligne {want_targets} ennemi(s) en {30} pas")
        cid, aim, my = placed

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        # GARDE anti-confond : aucun Daemon en jeu (cf. l'en-tete -- gap Daemon_ExtraBlock).
        for u in (dv.get("units") or []):
            traits = (GC.unit(u.get("visualId")) or {}).get("traits") or []
            assert "Daemon" not in traits, (
                f"{u.get('visualId')} porte le trait Daemon : le jet de block `Daemon_ExtraBlock` non "
                f"roule par le port desyncherait le rng -- ce fichier exige des cibles NON-Daemon")
        cont_pre = _tile_effect_ids(rpc, rid, board, CONTAMINATED)
        eff_pre = {u["id"]: [e.get("effectType") for e in (u.get("effects") or [])]
                   for u in (dv.get("units") or [])}

        live_seq, flags, res = _cast_live(rpc, rid, cid, aim)
        if not live_seq:
            pytest.skip(f"aucun degat live (aim sans occupant ?) cast={str(res)[:160]}")
        if flags["crit"] or flags["block"] or flags["evade"]:
            pytest.skip(f"coup non propre (crit/block/evade): {flags}")
        cont_post = _tile_effect_ids(rpc, rid, board, CONTAMINATED)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        eff_post = {u["id"]: [e.get("effectType") for e in (u.get("effects") or [])]
                    for u in (dv2.get("units") or [])}

        st = load_state(dv, ob, snap, board=board)
        st.rng = _seed_rng(s0)
        runner = Runner(st).install_default_handlers(20)
        aim_tile = board.id_at(aim[0], aim[1])
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=aim_tile,
                                          ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        return {"rid": rid, "sf": sf, "board": board, "cid": cid, "aim": aim, "aim_tile": aim_tile,
                "live_seq": live_seq, "last": last, "st": st, "runner": runner,
                "cont_new": cont_post - cont_pre, "eff_pre": eff_pre, "eff_post": eff_post}
    except BaseException:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        sf.unlink(missing_ok=True)
        raise


def _dispose(rpc, ctx):
    try:
        rpc("disposeRunner", {"runnerId": ctx["rid"]}, 20)
    except Exception:
        pass
    try:
        ctx["sf"].unlink()
    except Exception:
        pass


def _assert_common(ctx, want_targets: int, compare_damage_targets=None):
    """`compare_damage_targets` = nombre de CIBLES dont le degat est confronte BIT-EXACT (None = toutes).

    Au-dela de la 1re cible, la confrontation est bornee pour une raison MESUREE et EXTERIEURE a ce port :
    le profil `Toxic` porte le DamageTrait `OnToxic` (4), qui arme
    `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility` (1203) --
        CreateTrigger   = On(0x10, 1) & DamageProfileHasTrait(4) & !TriggeringEffectIs(0x4dc)
        CreateBehaviour = If( IsFirstHitInSeries() & Maybe(ConfigConst(1203, Self@0x148, 0x2a = chance)),
                              AddEffect(0x4dc = Contaminated, stateRef, Tiles(target@0x178)) )
    Le `Maybe` consomme UN tirage AU PREMIER COUP DE CHAQUE SERIE, donc une fois PAR CIBLE. Ce canal
    on-hit n'est PAS porte (cf. `triggers/loki/rad_saturation.py` : « OnToxicDamageAbility (1203),
    l'autre source on-hit Toxic, n'est PAS porte ») -> le port a un tirage de retard des la 2e cible.
    GAP ADJACENT (il touche TOUTE attaque de profil Toxic, quelle que soit l'ability) -> backlog.
    Ce qui reste PLEINEMENT confrontable, et que ce port decide : le nombre de coups, l'ENSEMBLE des
    cibles, leur ORDRE, la geometrie de la ligne, les deux volets d'effet."""
    last, live_seq = ctx["last"], ctx["live_seq"]
    assert last.get("ported") is True, (
        f"RadBombardment (1116) non execute (no-op) : last={last} ; "
        f"unported={getattr(ctx['runner'].ability_handler, 'unported', None)}")
    want_hits = int(_const("nrOfHits"))

    off_seq = []
    for atk in (last.get("attacks") or []):
        for amount in ((atk.get("attack") or {}).get("per_hit") or []):
            off_seq.append((atk.get("target"), amount))
    assert len(live_seq) == want_hits * want_targets, (
        f"{len(live_seq)} coups LIVE (seq={live_seq}) != nrOfHits({want_hits}) x cibles({want_targets}) "
        f"-- soit la ligne ne couvre pas ce qu'on croit, soit le nb de coups n'est pas ConfigConst(0x2f)")
    # (5) ORDRE + ENSEMBLE des cibles : confronte sur TOUTE la sequence (independant du rng).
    assert [t for t, _ in off_seq] == [t for t, _ in live_seq], (
        f"sequence des CIBLES offline {[t for t, _ in off_seq]} != live {[t for t, _ in live_seq]} : "
        f"le port a re-trie ce que `AbilityDamageBehaviour$$Execute` laisse dans l'ordre du selecteur "
        f"(apres SortReverse : la tuile la PLUS LOINTAINE d'abord)")
    # (3) DEGAT per-coup bit-exact, borne aux `compare_damage_targets` premieres cibles (cf. docstring).
    k = want_targets if compare_damage_targets is None else int(compare_damage_targets)
    n = want_hits * k
    assert off_seq[:n] == live_seq[:n], (
        f"degat per-coup offline {off_seq[:n]} != live {live_seq[:n]} (sur les {k} premieres cibles) : "
        f"un etage du coup diverge (bornes MinMaxDamage, percage du profil Toxic, famille de factory)")

    # (2) GEOMETRIE : l'ensemble des tuiles Contaminated live == l'ensemble offline
    off_cont = {p["target"] for p in (last.get("contaminated") or []) if p.get("placed")}
    assert off_cont == ctx["cont_new"], (
        f"tuiles Contaminated offline {sorted(off_cont)} != live {sorted(ctx['cont_new'])} -- "
        f"GetAffectedTiles diverge (longueur AffectedTileAmount, sens de TilesBehindInLine, settings "
        f"walkable/elevation, ou la troncature `- Blocking`). aim={ctx['aim_tile']} "
        f"n_tiles={last.get('n_tiles')} tiles={last.get('tiles')}")
    assert ctx["aim_tile"] in off_cont, (
        f"la tuile AIM {ctx['aim_tile']} n'est pas contaminee : `TilesBehindInLine` doit rendre `to` "
        f"comme PREMIERE tuile de la ligne")

    # (4) PINNED sur chaque unite touchee, live ET offline
    hit_units = {t for t, _ in live_seq}
    off_pin = {p["target"] for p in (last.get("pinned") or []) if p.get("placed")}
    assert hit_units <= off_pin, (
        f"Pinned offline pose sur {sorted(off_pin)} mais les unites touchees sont {sorted(hit_units)}")
    for uid in hit_units:
        pre = ctx["eff_pre"].get(uid) or []
        post = ctx["eff_post"].get(uid) or []
        assert PINNED not in pre, (
            f"u{uid} portait DEJA Pinned avant le cast (effets={pre}) : la pose n'est plus observable "
            f"par delta sur cette unite")
        assert PINNED in post, (
            f"le natif n'a PAS pose Pinned sur u{uid} (avant={pre} apres={post}) -- volet "
            f"`AddEffect(0x429, stateRef, source=caster@0x160, Units(GetAffectedTiles()))`")
        assert ctx["st"].effects.has_effect(uid, effect_type=PINNED), \
            f"Pinned non materialise offline sur u{uid}"


# ======================================= GEOMETRIE 1 : la ligne couvre UNE unite

def test_rad_bombardment_single_target_live(live_session, rpc):
    """Ligne couvrant 1 ennemi : execution reelle, degat bit-exact, Pinned, et surtout la GEOMETRIE
    (ensemble des tuiles Contaminated live == offline) -- c'est elle qui valide `AffectedTileAmount`
    (`1 + RoundsStarted + TotalRepairActions`) et `TilesBehindInLine`."""
    ctx = _run(rpc, "necroWarden,necroOverlord", want_targets=1)
    try:
        _assert_common(ctx, want_targets=1)
        print(f"\n[RADBOMB/1] aim={ctx['aim']} n_tiles={ctx['last'].get('n_tiles')} "
              f"tiles={ctx['last'].get('tiles')} cont_live={sorted(ctx['cont_new'])} "
              f"seq={ctx['live_seq']}")
    finally:
        _dispose(rpc, ctx)


# ================================= GEOMETRIE 2 : la ligne couvre AU MOINS DEUX unites (ORDRE)

def test_rad_bombardment_two_targets_ordered_live(live_session, rpc):
    """Ligne couvrant >= 2 ennemis : la SEQUENCE (cible, degat) live == offline. C'est le scenario
    DISCRIMINANT de l'ordre : un port qui folderait l'`OrderBy` de la famille ATTACK (`multi=True`)
    trierait les cibles par id, alors que `AbilityDamageBehaviour$$Execute` enumere le selecteur TEL
    QUEL -- apres `SortReverse`, la tuile la PLUS LOINTAINE en premier. Il valide aussi le multi-volet
    `Pinned` et la contamination de TOUTE la ligne."""
    ctx = _run(rpc, "necroWarden,necroOverlord,necroDestroyer", want_targets=2)
    try:
        n = len({t for t, _ in ctx["live_seq"]})
        assert n >= 2, f"la ligne n'a touche que {n} unite(s) : geometrie 2 non atteinte"
        _assert_common(ctx, want_targets=n, compare_damage_targets=1)
        # ORDRE explicite : la 1re cible frappee doit etre la PLUS ELOIGNEE du caster (SortReverse).
        board, last = ctx["board"], ctx["last"]
        order = []
        for t, _ in ctx["live_seq"]:
            if t not in order:
                order.append(t)
        disc = order != sorted(order)     # l'ordre-ligne DIFFERE-t-il d'un tri par id ?
        print(f"\n[RADBOMB/2] aim={ctx['aim']} n_tiles={last.get('n_tiles')} "
              f"tiles={last.get('tiles')} ordre_live={order} "
              f"discriminant_vs_tri_par_id={disc} cont_live={sorted(ctx['cont_new'])}")
        tiles = list(last.get("tiles") or [])
        assert tiles, "le port n'a resolu aucune tuile de ligne"
        # `tiles` est deja dans l'ordre SortReverse (lointain -> aim) : les cibles doivent suivre.
        pos_of = {t: i for i, t in enumerate(tiles)}
        idx = [pos_of.get(board.id_at(*_pos_of_unit(ctx, u)), -1) for u in order]
        assert idx == sorted(idx), (
            f"l'ordre des cibles live {order} (indices de ligne {idx}) ne suit pas l'ordre du selecteur "
            f"apres SortReverse {tiles}")
    finally:
        _dispose(rpc, ctx)


def _pos_of_unit(ctx, uid):
    from engine.runner.components import PositionComponent
    e = ctx["st"].get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else (-1, -1)


# ============================================================ table offline (aucune session requise)

def test_rad_bombardment_line_order_is_not_id_order():
    """GARDE DETERMINISTE de l'ORDRE (offline pur, aucune session) -- le complement du test live, dont la
    geometrie de spawn peut faire COINCIDER l'ordre-ligne et l'ordre par id (`discriminant_vs_tri_par_id`
    imprime par le test 2).

    On construit une ligne ou les deux ordres DIVERGENT : le caster tire vers `aim`, la cible LOINTAINE
    porte l'id 200 et la cible PROCHE l'id 100. Le natif
    (`IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$Execute`) enumere le selecteur TEL QUEL --
    aucun `OrderBy`, contrairement a `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` -- donc
    apres `SortReverse` c'est [200, 100]. Un port qui aurait garde `multi=True` (qui folde l'`OrderBy` de
    la famille ATTACK) rendrait [100, 200] et TOMBERAIT ici."""
    from engine.dsl.base import DslContext
    from engine.entities.selectors import Units
    from engine.runner.abilities.admec import rad_bombardment_affected_tiles
    tiles = [{"id": r * 10 + c, "col": c, "row": r, "walkable": True, "elevation": 0}
             for r in range(6) for c in range(6)]
    board = Board(tiles, adjacency="native_sym")
    # Ligne hex REELLE depuis (1,3) via l'aim (1,4) : [(1,4), (1,5), (1,6), ...] (geometrie CUBE, pas
    # cartesienne -- on ne la devine pas, on la lit du mirror partage `battle_query.get_tiles_behind`).
    caster = {"id": 1, "team": 1, "alive": True, "hp": 100, "pos": {"col": 1, "row": 3}}
    far = {"id": 200, "team": 2, "alive": True, "hp": 100, "pos": {"col": 1, "row": 5}}
    near = {"id": 100, "team": 2, "alive": True, "hp": 100, "pos": {"col": 1, "row": 4}}
    ctx = DslContext(units=[caster, far, near], caster=caster, target=None, board=board)
    aim = board.id_at(1, 4)
    sel = rad_bombardment_affected_tiles(aim, 3)
    line = list(sel.evaluate(ctx))
    assert line, "la ligne est vide : TilesBehindInLine n'a rien rendu sur la grille synthetique"
    assert line[-1] == aim, (
        f"apres SortReverse, l'AIM doit etre la DERNIERE tuile (la ligne est parcourue de la plus "
        f"lointaine vers l'aim) : line={line} aim={aim}")
    order = [u["id"] for u in Units(sel).evaluate(ctx)]
    assert order == [200, 100], (
        f"ordre des cibles {order} != ordre du selecteur apres SortReverse [200, 100] -- le port a "
        f"re-trie par id (folding de l'`OrderBy` de la famille ATTACK), ce que "
        f"`AbilityDamageBehaviour$$Execute` NE FAIT PAS")
    assert order != sorted(order), "le cas construit n'est plus discriminant vs un tri par id"


def test_rad_bombardment_registered_and_turn_flags():
    """1116 route vers la classe portee et garde les turn-flags PAR DEFAUT. Pur offline."""
    from engine.runner.abilities.base import (NO_END_TURN_ABILITY_TYPES,
                                              NO_ABILITY_USED_FLAG_ABILITY_TYPES,
                                              sets_end_turn_flags_for,
                                              sets_active_ability_used_flag_for)
    from engine.runner.state import State
    assert ABILITY_CLASSES.get(ABILITY) is RadBombardmentAbility
    assert RadBombardmentAbility.ABILITY_TYPE == ABILITY
    assert ABILITY not in NO_END_TURN_ABILITY_TYPES
    assert ABILITY not in NO_ABILITY_USED_FLAG_ABILITY_TYPES
    st = State()
    assert sets_end_turn_flags_for(ABILITY, st, 1) is True
    assert sets_active_ability_used_flag_for(ABILITY, st, 1) is True
    for k in ("nrOfHits", "damageProfile"):
        assert _const(k) is not None
