"""probe #433-r4-r2 -- les DEUX consommateurs qui tranchaient l'adjacence HORS du foyer mirror.

QUELLE PRIMITIVE, POUR CHACUN (lue au decompile, jamais deduite du nom) :

  1. `IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable` --
     `adj = TileExtensions.IsAdjacentTo(GetMainTile(caster), GetTiles(otherUnit))`, surcharge
     `(tile, otherTiles)` = un `exists` dont chaque paire passe par
     `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` (SCALAIRE) :
     `(|dElev| < 2) & (t1 == t2 || ConnectivityComponent.IsNeighbour)`. Le port tranchait par
     `hexgeo.distance(origin, ep) == 1` : la PORTE D'ELEVATION manquait -> FORK.
     Ce booleen choisit la BRANCHE : `adj` faux -> branche A (`+50` si NON
     `IsTileInRangeOfAnyAbility(E, P)`), `adj` vrai -> branche B (`+50` si `threshold(E) < d`).

  2. `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy` -- son terme « en melee » est
     `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`, appele DIRECTEMENT (et non
     `$$AreUnitsInMelee`, qui n'est qu'un passe-plat d'une ligne vers la meme fonction), lui-meme
     `MovementUtil$$AreTilesAdjacent`. Le port passait par `battle_query.is_adjacent`, mirror de
     `TileQuery$$IterateAdjacentTiles` -- une primitive DIFFERENTE (#433-r1 §4 la designe comme
     contre-exemple : elle ne rend JAMAIS la tuile source). Mauvais foyer, mais ecart observable
     NUL par composition (cf. etape 2).

CE QUE LE PROBE MESURE, en trois etapes :

  * `--step slots` : re-derive AU RUNTIME les slots d'interface `IBattleQuery` cites par les deux
    corps. Les numeros ont BOUGE d'un cran entre `gqfc5mff6c` et `rnca9r7q6c` (#433-r1 §7), donc
    les recopier d'une fiche est un faux ami. Sortie : 0x4a=GetNearestEnemy, 0x60=AreEntitiesAdjacent,
    0x6c=GetDistance, 0x89=GetAllAliveUnits, 0xb3=FindRangedWeapon, 0xc5=IsTileInRangeOfAnyAbility.

  * `--step partition` : LA MESURE QUI ISOLE LA CAUSE. Meme caster, MEME tuile O, meme sweep, meme
    ennemi -- on ne bouge QUE la tuile de l'ennemi, d'un voisin hex a `|dElev| >= 2` (donc NON
    adjacent pour le natif) a un voisin PLAT (adjacent). Le natif change de BRANCHE, et ca se lit
    dans son bonus a `d = 4`. C'est une comparaison du natif AVEC LUI-MEME : aucun terme du port
    n'y participe, donc aucune confusion possible avec les deux approximations voisines.

  * `--step couple` : le couple divergence -> convergence sur le port. La CONTRE-EPREUVE est le
    port d'AVANT `#433-r4-r2` -- c'est-a-dire le partage A/B tranche par
    `hexgeo.distance(origine, E) == 1`, TOUS LES AUTRES CANAUX INTACTS (classe
    `EarlyWarningOverrideAvant433r4r2` ci-dessous). C'est la seule mutation qui isole le foyer
    d'adjacence, et elle a remplace une neutralisation de canal qui avait cesse de mordre :

      - `elev_by_pos = None` ne retire PLUS l'adjacence depuis `fix(#433-r4-r1-r4-r2)`
        (`489bb349`, 2026-08-04) : `battle_query.is_adjacent` enumere d'abord `neigh_by_pos`, la
        liste STOCKEE que `BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` rend -- donc DEJA traversee
        par la porte de `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. Les deux canaux
        portent la meme exclusion : en neutraliser UN SEUL ne restitue rien (MESURE, etape
        `adj_par_canal` : `elev+neigh` [] / `neigh seul` [] / `elev seul` [] / `aucun` [Y]) ;
      - et `elev_by_pos` a acquis un SECOND role depuis `feat(#433-r4-r2-r1-r2)` -- il est le
        substrat de la LIGNE DE VUE d'`AttackQuery$$GetAllTilesInAbilityRange` (branche A). Le
        neutraliser ELARGIT la zone d'ability de l'ennemi en meme temps : deux mecanismes
        bougeaient d'un coup, et le bras de contre-epreuve ne mesurait plus une cause.

    Deuxieme correctif de la meme passe : `rows` appelait `utility_at` SANS les canaux que
    `generate_candidates` lui passe (elevation, murs, equipes, walkability, brouillard). Il
    confrontait donc au natif un port AMPUTE, et fabriquait une divergence -- `1/34`, imputee au
    residu LoS. Avec les canaux reellement passes : **0/34**.

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_adjacency_foyer.py --step slots
  python probe_433_r4_r2_adjacency_foyer.py --step partition
  python probe_433_r4_r2_adjacency_foyer.py --step couple
  python probe_433_r4_r2_adjacency_foyer.py --step all
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                     # noqa: E402
from rl_collect_batch import _resolve_session, _rpc               # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASTER = "tauCrisis"          # HERO du pool ; seul porteur `lineup` de 1077
ENEMY = "tauMarksman"         # arme a distance de portee 3 -> branche A et branche B DIFFERENT
ABILITY = 1077                # ActiveAbilityType.EarlyWarningOverride
BOARD = "MC1_67"              # 4 niveaux d'elevation, 18 paires voisines a |dElev| >= 2
SEED = "777"

# Slots d'interface `IBattleQuery` cites par les deux corps, avec leur nom ATTENDU. Le probe les
# re-derive au runtime (`probe_27_4g_battlequery_slots.py`) : une divergence ici veut dire que le
# build a bouge et que toute citation de slot des deux docstrings est a re-lire.
EXPECTED_SLOTS = {
    0x4A: "GetNearestEnemy",            # gate `< 9` d'EarlyWarningOverride + terme melee (#2)
    0x60: "AreEntitiesAdjacent",        # le predicat par paire de `GetNearestEnemy`
    0x6C: "GetDistance",
    0x89: "GetAllAliveUnits",
    0xB3: "FindRangedWeapon",           # branche B : `threshold = weapon.Range ?? 1`
    0xC5: "IsTileInRangeOfAnyAbility",  # branche A
    # Les deux autres slots que cite `MasterOfTheTutelariesPlaybook` -- ils etaient ecrits 0x52/0x72
    # (build precedent), et 0x72 designe aujourd'hui `GetAngleBetweenVectors`, pas du tout la meme
    # question. C'est le mode de panne que cette etape existe pour attraper.
    0x53: "GetFreeAdjacentTiles",
    0x73: "GetUnitsAtDistance",
}


class _AdjacenceHexNue(object):
    """Le partage A/B d'AVANT `#433-r4-r2` : `hexgeo.distance(origine, E) == 1`.

    MIXIN, et non une copie du playbook : la mutation ne touche QUE `adjacent_at_origin` -- les
    deux branches, les canaux de ligne de vue et les gates CASTER restent ceux du port LIVRE. C'est
    la condition pour qu'un ecart mesure soit imputable au foyer d'adjacence et a lui seul.

    C'est litteralement ce que le port tranchait avant `#433-r4-r2` (cf. l'en-tete de ce module) :
    ni liste stockee du `ConnectivityComponent`, ni porte d'elevation de
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`."""

    def adjacent_at_origin(self, ctx, enemies) -> set:
        if ctx.origin is None:
            return set()
        return {e[0] for e in enemies if hexgeo.distance(ctx.origin, e[0]) == 1}


def EarlyWarningOverrideAvant433r4r2():
    """Instance du playbook LIVRE dont le seul foyer d'adjacence est remplace par l'ancien.

    Fabrique (et non classe de module) parce que la base vit dans `engine.playbook.noncomparable`,
    dont l'import est differe : ce probe est importable sans que `engine` soit charge."""
    from engine.playbook.noncomparable.early_warning_override import \
        EarlyWarningOverridePlaybook
    return type("EarlyWarningOverrideAvant", (_AdjacenceHexNue, EarlyWarningOverridePlaybook),
                {})()


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(extra=None):
    """Runner ISOLE, state-file ABSOLU a nom unique (discipline `runner.md` §3)."""
    state = ROOT / "logs" / "runners" / ("probe433r4r2-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state), "--p-units", CASTER, "--a-units", ENEMY,
            "--hp-target", "90000", "--hp-player", "90000"] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                             # pragma: no cover - diagnostic
        pass


def _place(sid, rid, caster_id, enemy_id, O, Y):
    """DEPLACE les deux unites puis rend la main au caster avec un set de move FRAIS.

    `applyAction move` ignore portee et propriete (il pose l'unite), mais il POSE AUSSI le drapeau
    `Moved` : le caster n'a plus aucune tuile candidate juste apres. Un cycle de fins de tour le
    lui rend -- sans quoi le sweep d'`ncEvaluate` se reduirait a la tuile courante et la mesure
    serait vide (mesure : 0 tuile juste apres le pas, 17 apres le cycle)."""
    for uid, p in ((enemy_id, Y), (caster_id, O)):
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 90)
    for _ in range(4):
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        if (by_unit.get(caster_id) or {}).get("tiles"):
            return True
    return False


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles}
    elev = {pos_of[t["id"]]: t.get("elevation") for t in tiles}
    # `neighbours` du boardGraph = `GetAdjacentTiles` -> `IterateAdjacentTiles` : la liste a DEJA
    # traverse la porte d'elevation. C'est pourquoi le voisin a |dElev| >= 2 se cherche dans la
    # COURONNE HEX, pas dans cette liste (il en est absent, et c'est le fait meme qu'on mesure).
    native_nb = {pos_of[t["id"]]: {pos_of[n] for n in (t.get("neighbours") or []) if n in pos_of}
                 for t in tiles}
    return elev, native_nb


def _units(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    c = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER), None)
    e = next((u for u in (dv.get("units") or []) if u.get("visualId") == ENEMY), None)
    return dv, c, e


def _nc_bonus_by_distance(sid, rid, uid, Y) -> dict:
    """`{d: set(bonus)}` -- le bonus etant `util + 10*d`, c'est-a-dire le terme `+50/0` ISOLE du
    terme de distance. `util = Sum_E [bonus(E,P)] - 10*Sum_E d(P,E)` et il n'y a qu'UN ennemi."""
    nat = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": uid, "abilityType": ABILITY,
                                 "sweep": True}, 180)
    out: dict = {}
    for p in (nat.get("positions") or []):
        if p.get("util") is None:
            continue
        d = hexgeo.distance(tuple(p["pos"]), Y)
        out.setdefault(d, set()).add(round(p["util"] + 10 * d, 6))
    return out, nat


# ------------------------------------------------------------------------------------------------
# etape SLOTS -- re-derivation runtime des slots d'interface cites
# ------------------------------------------------------------------------------------------------
def step_slots(verbose=True) -> dict:
    """Delegue a `probe_27_4g_battlequery_slots.py` (qui balaye la vtable PROPRE de `BattleQuery`
    au runtime et verifie sa conversion `slot d'interface + 4 = index de vtable` sur deux ancres
    independantes). On ne recopie AUCUN numero : on les redemande."""
    p = subprocess.run(
        [sys.executable, "probe_27_4g_battlequery_slots.py",
         "--slots", ",".join(hex(s) for s in sorted(EXPECTED_SLOTS))],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    got: dict = {}
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("slot itf "):
            parts = line.split()
            got[int(parts[2], 16)] = parts[-1]
    ok = bool(got) and all(got.get(s) == n for s, n in EXPECTED_SLOTS.items())
    if verbose:
        for s in sorted(EXPECTED_SLOTS):
            print("[slots] 0x%02x -> %-26s attendu %-26s %s"
                  % (s, got.get(s), EXPECTED_SLOTS[s],
                     "OK" if got.get(s) == EXPECTED_SLOTS[s] else "DIVERGE"))
        print("[slots] verdict : %s" % ("OK" if ok else "DIVERGE -- re-lire les docstrings"))
        if not got:
            print("[slots] sortie du probe 27-4g : %s" % ((p.stderr or p.stdout or "")[-400:],))
    return {"slots": got, "ok": ok}


# ------------------------------------------------------------------------------------------------
# etape PARTITION -- la bascule A/B du NATIF, mesuree contre LUI-MEME
# ------------------------------------------------------------------------------------------------
def step_partition(verbose=True) -> dict:
    """Meme O, meme sweep, meme ennemi : seule la TUILE de l'ennemi change (voisin HAUT vs PLAT).

    Le natif doit changer de branche, et ca se lit au bonus a `d = 4` :
      * voisin a `|dElev| >= 2` -> branche A -> `IsTileInRangeOfAnyAbility` VRAI a d=4 -> bonus 0 ;
      * voisin PLAT             -> branche B -> `d > FindRangedWeapon().Range = 3` -> bonus 50.
    Aucun terme du port n'entre dans cette mesure."""
    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    rid, err = _build()
    if rid is None:
        return {"error": "build KO : %s" % err}
    try:
        elev, native_nb = _board_maps(sid, rid)
        dv, c, e = _units(sid, rid)
        if c is None or e is None:
            return {"error": "caster/ennemi absent de la bataille"}
    finally:
        _dispose(sid, rid)

    # O = une tuile portant a la fois un voisin hex a |dElev| >= 2 ET un voisin PLAT. Choisie sur le
    # BOARD (entree versionnee), pas hardcodee.
    pick = None
    for O in sorted(elev):
        if elev[O] is None:
            continue
        crown = [q for q in hexgeo.neighbors(O[0], O[1]) if elev.get(q) is not None]
        hi = [q for q in crown if abs(elev[q] - elev[O]) >= 2]
        lo = [q for q in crown if abs(elev[q] - elev[O]) <= 1]
        if hi and lo:
            pick = (O, hi[0], sorted(lo)[0])
            break
    if pick is None:
        return {"error": "aucune tuile de %s avec un voisin HAUT et un voisin PLAT" % BOARD}
    O, Y_hi, Y_lo = pick

    out = {"O": O, "Y_hi": Y_hi, "Y_lo": Y_lo, "elev": {O: elev[O], Y_hi: elev[Y_hi],
                                                        Y_lo: elev[Y_lo]},
           "hi_absent_de_la_liste_native": Y_hi not in native_nb.get(O, set()),
           "lo_present_dans_la_liste_native": Y_lo in native_nb.get(O, set())}
    for tag, Y in (("hi", Y_hi), ("lo", Y_lo)):
        sid = _resolve_session()
        rid, err = _build()
        if rid is None:
            return {"error": "build KO (%s) : %s" % (tag, err)}
        try:
            _dv, c, e = _units(sid, rid)
            if not _place(sid, rid, c["id"], e["id"], O, Y):
                return {"error": "montage %s non installe (pas de tuile candidate)" % tag}
            dv2, c2, e2 = _units(sid, rid)
            posn = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                    for u in (dv2.get("units") or []) if u.get("pos")}
            if posn.get(c2["id"]) != O or posn.get(e2["id"]) != Y:
                return {"error": "positions non atteintes (%s) : %r" % (tag, posn)}
            bonus, nat = _nc_bonus_by_distance(sid, rid, c2["id"], Y)
            out[tag] = {d: sorted(v) for d, v in sorted(bonus.items())}
            out[tag + "_n"] = len(nat.get("positions") or [])
        finally:
            _dispose(sid, rid)
    if verbose:
        print("[partition] O=%s elev=%s | Y_hi=%s elev=%s (|dElev|=%d) | Y_lo=%s elev=%s"
              % (O, elev[O], Y_hi, elev[Y_hi], abs(elev[Y_hi] - elev[O]), Y_lo, elev[Y_lo]))
        print("[partition] Y_hi ABSENT de la liste d'adjacence NATIVE de O : %s"
              % out["hi_absent_de_la_liste_native"])
        print("[partition] bonus natif par distance -- HI %r" % (out.get("hi"),))
        print("[partition] bonus natif par distance -- LO %r" % (out.get("lo"),))
    return out


# ------------------------------------------------------------------------------------------------
# etape COUPLE -- divergence -> convergence du PORT, sweep confine a `d <= 3`
# ------------------------------------------------------------------------------------------------
def _nc_context(sid, rid, dv, uid):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.noncomparable._base import NCContext
    wt = W.load()
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    pred = _scene.build_predictor(lambda m, b, t=90: _r(sid, m, b, t), rid)
    a = _ai_ctx.build(lambda m, b, t=90: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
    return NCContext(
        uid=a.uid, origin=a.origin, reach_nc=a.reach_nc, epos=a.epos, fpos=a.fpos,
        enemies=a.enemies, neigh_by_pos=a.neigh_by_pos, walkable_by_pos=a.walkable_by_pos,
        plan=a.plans.get(a.uid) or {}, plans=a.plans, hp_cur_by_id=a.hp_cur_by_id,
        elev_by_pos=a.elev_by_pos, ability_targets=a.ability_targets, wt=a.wt,
        is_temporary_by_pos=a.is_temporary_by_pos, effects_by_pos=a.effects_by_pos,
        obs_units=a.obs_units, tile_id_by_pos=a.tile_id_by_pos,
        active_levels=a.active_ability_levels, ability_config=a.heal_config, units=a.units,
        cast_from_tiles=a.cast_from_tiles, scene=a.scene)


def _ability_reach(visual_id) -> int:
    """La zone d'ability de l'ennemi (`AttackQuery$$GetAllTilesInAbilityRange`), pour la sortie."""
    from engine.services import ability_range as ar
    return ar.unit_threat_reach(visual_id)


def step_couple(verbose=True) -> dict:
    """Le couple : ennemi a un voisin hex a `|dElev| >= 2` du caster, caster a `Movement = 4`.

    RE-ETALONNE par #433-r4-r2-r1/-r2. L'ancien montage forcait `Movement = 2` pour CONFINER le
    sweep a `d <= 3` : c'etait le domaine ou les deux approximations de branche d'alors (branche A
    = portee d'ARME, branche B = `threshold` fige a 1) restaient exactes. Les deux etant desormais
    portees (zone d'ability 5, `threshold` 3 sur `tauMarksman`), le confinement n'a plus lieu
    d'etre -- et il RETIRAIT precisement les distances ou les deux branches DIFFERENT. Le sweep
    doit ATTEINDRE `d = 4` : c'est la que la branche A ne verse rien (`d <= 5`, en portee) alors
    que la branche B verse `+50` (`d > 3`), donc c'est la que le partage A/B se lit.

    RE-ETALONNE une SECONDE fois par #433-r4-r2-r4. La contre-epreuve n'est plus une neutralisation
    de canal (`elev_by_pos = None`) mais le PORT D'AVANT `#433-r4-r2` -- adjacence tranchee par la
    distance hex nue, tous les autres canaux intacts (`EarlyWarningOverrideAvant433r4r2`). L'ancienne
    mutation avait cesse de mordre le 2026-08-04 a `489bb349` sans qu'aucun port ne regresse : elle
    est conservee sous `cand_elev_neutralise`, comme TEMOIN, et l'etape publie `adj_par_canal` qui
    montre POURQUOI (les deux canaux portent la meme exclusion)."""
    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    rid, err = _build()
    if rid is None:
        return {"error": "build KO : %s" % err}
    try:
        elev, native_nb = _board_maps(sid, rid)
    finally:
        _dispose(sid, rid)
    pick = None
    for O in sorted(elev):
        if elev[O] is None:
            continue
        hi = [q for q in hexgeo.neighbors(O[0], O[1])
              if elev.get(q) is not None and abs(elev[q] - elev[O]) >= 2]
        if hi:
            pick = (O, hi[0])
            break
    if pick is None:
        return {"error": "aucune paire (O, voisin a |dElev| >= 2) sur %s" % BOARD}
    O, Y = pick

    sid = _resolve_session()
    rid, err = _build(["--unit-stat", "%s:Movement=4" % CASTER])
    if rid is None:
        return {"error": "build KO (couple) : %s" % err}
    try:
        _dv, c, e = _units(sid, rid)
        if c is None or e is None:
            return {"error": "caster/ennemi absent"}
        if not _place(sid, rid, c["id"], e["id"], O, Y):
            return {"error": "montage non installe (pas de tuile candidate apres le cycle)"}
        dv, c, e = _units(sid, rid)
        posn = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("pos")}
        if posn.get(c["id"]) != O or posn.get(e["id"]) != Y:
            return {"error": "positions non atteintes : %r" % posn}
        nat = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": c["id"],
                                     "abilityType": ABILITY, "sweep": True}, 180)
        native = {tuple(p["pos"]): p.get("util") for p in (nat.get("positions") or [])}

        from engine.playbook.noncomparable._base import occupant_team_by_pos
        from engine.playbook.noncomparable.early_warning_override import \
            EarlyWarningOverridePlaybook
        nc_on = _nc_context(sid, rid, dv, c["id"])
        pb = EarlyWarningOverridePlaybook()
        pb_avant = EarlyWarningOverrideAvant433r4r2()             # l'etat d'AVANT #433-r4-r2
        enemies = pb.enemies_of(nc_on)
        adj_on = pb.adjacent_at_origin(nc_on, enemies)
        adj_avant = pb_avant.adjacent_at_origin(nc_on, enemies)

        # Les QUATRE combinaisons du foyer d'adjacence. Elles ne servent pas la confrontation au
        # natif : elles VERROUILLENT le fait qui a rendu l'ancienne contre-epreuve muette -- les
        # deux canaux (liste stockee, porte d'elevation) portent la MEME exclusion, donc en
        # neutraliser un seul ne restitue pas l'adjacence.
        adj_par_canal = {}
        for tag, kw in (("elev+neigh", {}), ("neigh seul", {"elev_by_pos": None}),
                        ("elev seul", {"neigh_by_pos": None}),
                        ("aucun", {"elev_by_pos": None, "neigh_by_pos": None})):
            ctx2 = dataclasses.replace(nc_on, **kw) if kw else nc_on
            adj_par_canal[tag] = sorted(pb.adjacent_at_origin(ctx2, enemies))

        # `utility_at` recoit EXACTEMENT les canaux que `generate_candidates` lui passe : sans eux
        # on confronte au natif un port ampute, et l'ecart mesure n'est pas un residu du port mais
        # un artefact de la mesure (c'etait le cas -- 1/34, cf. l'en-tete).
        team_by_pos = occupant_team_by_pos(nc_on)
        canaux = (nc_on.elev_by_pos, getattr(nc_on, "is_wall_by_pos", None), team_by_pos,
                  getattr(nc_on, "walkable_by_pos", None), getattr(nc_on, "is_in_fog_by_pos", None))
        rows = []
        for P in sorted(native):
            rows.append({"pos": P, "d": hexgeo.distance(P, Y), "natif": native[P],
                         "port_on": pb.utility_at(P, enemies, adj_on, *canaux),
                         "port_avant": pb_avant.utility_at(P, enemies, adj_avant, *canaux)})
        out = {
            "O": O, "Y": Y, "elev_O": elev[O], "elev_Y": elev[Y],
            "caster": c["id"], "enemy": e["id"],
            # Les DEUX seuils de branche, desormais DISTINCTS (#433-r4-r2-r1 + -r2 fermes ensemble) :
            # `reach` = zone d'ability (`IsTileInRangeOfAnyAbility`), `threshold` = portee de l'arme
            # a distance (`FindRangedWeapon`). Sur `tauMarksman` : 5 et 3.
            # `enemies_of` rend 5 termes depuis #433-r4-r2-r1-r1-c : les deux derniers sont l'etat
            # d'abilities de l'ennemi et l'id de son attaque normale (les gates CASTER).
            "enemies": [{"pos": list(e[0]), "visualId": e[1], "threshold": e[2],
                         "reach": _ability_reach(e[1])} for e in enemies],
            "adj_on": sorted(adj_on), "adj_avant": sorted(adj_avant),
            "adj_par_canal": adj_par_canal,
            "d_max": max(r["d"] for r in rows) if rows else None,
            "n": len(rows),
            "diff_on": [r for r in rows if r["natif"] != r["port_on"]],
            "diff_avant": [r for r in rows if r["natif"] != r["port_avant"]],
            "cand_on": pb.generate_candidates(nc_on),
            "cand_avant": pb_avant.generate_candidates(nc_on),
            # L'ANCIENNE mutation, conservee comme TEMOIN : elle ne neutralise plus l'adjacence
            # (l'autre canal la porte) et elargit au contraire la zone d'ability de l'ennemi en
            # coupant la ligne de vue. C'est ce qui a fait rougir le test sans qu'aucun port ne
            # regresse -- le garder mesure evite de re-croire un jour qu'elle isole quelque chose.
            "cand_elev_neutralise": pb.generate_candidates(
                dataclasses.replace(nc_on, elev_by_pos=None)),
            # Le MAXIMUM que le natif attribue sur tout le sweep. A ne PAS confondre avec « le
            # natif caste » : le Bucket d'EarlyWarningOverride est construit par le ctor a DEUX
            # arguments, donc SANS `min` -- il admet des utilites negatives, et `ncEvaluate` le
            # confirme (un `best` a util < 0 a chaque position). Le `MIN_UTILITY = 1` du port est
            # un residu NOMME, pas un fait mesure ici.
            "native_best": max((v for v in native.values() if v is not None), default=None),
            "rows": rows,
        }
        if verbose:
            print("[couple] O=%s(elev %s) Y=%s(elev %s) |dElev|=%d ; sweep n=%d d_max=%d"
                  % (O, elev[O], Y, elev[Y], abs(elev[Y] - elev[O]), out["n"], out["d_max"]))
            print("[couple] adj_origin PORT LIVRE=%r  AVANT #433-r4-r2 (hex nue)=%r"
                  % (out["adj_on"], out["adj_avant"]))
            for tag in ("elev+neigh", "neigh seul", "elev seul", "aucun"):
                print("[couple]   adj par canal  %-11s -> %r" % (tag, adj_par_canal[tag]))
            print("[couple] positions ou port != natif : LIVRE %d/%d, AVANT %d/%d"
                  % (len(out["diff_on"]), out["n"], len(out["diff_avant"]), out["n"]))
            for r in out["diff_on"]:
                print("[couple]   diff_on %r d=%d natif=%r port=%r"
                      % (r["pos"], r["d"], r["natif"], r["port_on"]))
            for r in out["diff_avant"][:6]:
                print("[couple]   diff_avant %r d=%d natif=%r avant=%r"
                      % (r["pos"], r["d"], r["natif"], r["port_avant"]))
            print("[couple] action portee -- LIVRE %r ; AVANT %r"
                  % (out["cand_on"], out["cand_avant"]))
            print("[couple] TEMOIN `elev_by_pos=None` (l'ancienne mutation, qui n'isole plus "
                  "rien) -- action %r" % (out["cand_elev_neutralise"],))
            print("[couple] utilite MAXIMALE du natif sur le sweep : %r" % (out["native_best"],))
        return out
    finally:
        _dispose(sid, rid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all",
                    choices=["slots", "partition", "couple", "all"])
    a = ap.parse_args()
    rc = 0
    if a.step in ("slots", "all"):
        res = step_slots()
        rc |= 0 if res.get("ok") else 1
    if a.step in ("partition", "all"):
        res = step_partition()
        if "error" in res:
            print("[partition] REFUS : %s" % res["error"])
            rc |= 1
    if a.step in ("couple", "all"):
        res = step_couple()
        if "error" in res:
            print("[couple] REFUS : %s" % res["error"])
            rc |= 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
