"""probe #433-r4-r3 -- MONTAGE des deux `*NonOwnerPlaybook` qui manquaient au registre.

CE QUE CE PROBE MESURE. La feuille `TriggeredAbilitiesNonOwner(4)` verse un poids sur les tuiles
candidates du MOVER quand une AUTRE unite de son camp porte l'ability. Deux classes natives
l'exercaient sans etre portees :

  * `IdunBattle.AI.Playbook.Loki.PsychicFortressNonOwnerPlaybook` (1000, `ultraTigurius` -- HERO du
    pool spawnable) : `+20` des que la tuile candidate est adjacente au porteur. AUCUN autre gate.
  * `IdunBattle.AI.Playbook.Loki.ECogSupportPlaybookNonOwnerPlaybook` (1487, `votanIronmaster` --
    HERO HORS pool) : `+10`, mais seulement si le MOVER a le trait `Summon` ET que son parent EST le
    porteur. Le seul mover eligible est donc le summon `votanSmnEcog` que le porteur invoque
    lui-meme (`EcogSupport.constants.unitId`).

LE MONTAGE LIVE (`run_psychic_fortress`) est celui de #271, transpose sur la face NON-OWNER PURE :
on prend un ALLIE quelconque comme mover, on classe ses tuiles candidates SANS le terme, puis on
DEPLACE le porteur sur une tuile voisine NATIVE de la deuxieme (et pas de la premiere). Le terme
doit renverser l'argmax du port, et le natif doit jouer la tuile que le port retient AVEC.

Deplacer le PORTEUR (et non un tiers) est ce qui rend le montage sur : le poids ne depend que de
l'adjacence a lui, donc une seule unite bougee suffit a fabriquer la fenetre. On n'accepte le
couple (T1, T2) que si leur ecart SANS terme est inferieur au poids -- sinon le terme ne peut rien
renverser et la mesure ne prouverait rien.

Usage (ASCII only) :
  python probe_433_r4_r3_non_owner_playbooks.py --offline-only
  python probe_433_r4_r3_non_owner_playbooks.py --seed 777 --board MC1_67
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

PSYCHIC_FORTRESS = 1000            # TriggeredAbilityType.PsychicFortress
ECOG_SUPPORT = 1487                # TriggeredAbilityType.EcogSupport (0x5cf)
CARRIER_PF = "ultraTigurius"       # HERO, present dans `rl_duel build --list-pool`
CARRIER_ECOG = "votanIronmaster"   # HERO, HORS pool -> injection catalogue (case-92 §6)
SUMMON_ECOG = "votanSmnEcog"       # `GC.ability("EcogSupport").constants.unitId`
KEY_PF = "PSYCHICFORTRESS_AdjacentFriendly"          # Utilities.Default.TriggeredAbilitiesNonOwner
KEY_ECOG = "EcogSupport_EcogAdjacentToParent"        # idem

# Roster CRAFTE : le porteur + des allies aux passifs DEJA portes (ou sans passif de mouvement), de
# sorte que la seule difference entre les deux bras de l'A/B soit le terme 1000. Les ennemis sont
# ceux du montage #271, pour rester sur un etat de bataille deja eprouve sur ce board.
DEFAULT_P = "ultraTigurius,astraBullgryn,necroWarden,orksNob,orksWarboss"
DEFAULT_A = "worldKharn,templChampion,tauMarksman"
DEFAULT_BOARD = "MC1_67"
DEFAULT_SEED = "777"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, p_units, a_units, extra=None):
    """Runner ISOLE, state-file ABSOLU a nom unique (discipline `runner.md` §3)."""
    state = ROOT / "logs" / "runners" / ("probe433r4r3-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units] \
        + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, None, (p.stderr or p.stdout or "")[-900:]
    return json.loads(state.read_text())["runnerId"], state, None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


# --------------------------------------------------------------------------------------------
# ETAPE 0 -- garde de montage : les deux poids sont-ils NON NULS des DEUX cotes ?
# --------------------------------------------------------------------------------------------
def step0_weights(verbose=True) -> int:
    import contextlib
    import io
    from engine import weights as W

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = ((bc.get("Utilities") or {}).get("Default") or {}).get("TriggeredAbilitiesNonOwner") or {}
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    fell_back = "REPLI sur BC.Utilities" in err.getvalue()
    rows = [(KEY_PF, cap.get(KEY_PF), wt.sub("TriggeredAbilitiesNonOwner", KEY_PF)),
            (KEY_ECOG, cap.get(KEY_ECOG), wt.sub("TriggeredAbilitiesNonOwner", KEY_ECOG))]
    if verbose:
        for k, c, l in rows:
            print("[etape0] %-34s capture=%-5s moteur=%s" % (k, c, l))
    if fell_back:
        print("[etape0] REFUS : `engine.weights.load` est retombe sur la table de la CAPTURE.")
        return 1
    if any(not l for _, _, l in rows):
        print("[etape0] REFUS : au moins un poids vaut 0 cote moteur -- terme inerte.")
        return 1
    if verbose:
        print("[etape0] OK : les deux poids sont NON NULS, et IDENTIQUES capture/gameconfig "
              "(pas de piege #271 sur ce cas).")
    return 0


# --------------------------------------------------------------------------------------------
# ETAPE 1 -- A/B live PsychicFortress (face NON-OWNER pure)
# --------------------------------------------------------------------------------------------
def _score_map(ctx, wt, with_term: bool, ability: int):
    """`UnitMovement(6)` du port par tuile candidate, terme `ability` ACTIF ou AMPUTE du registre."""
    from engine.playbook.base import tile_utility
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS
    from engine.utilities.move import MIN_DIST_UTILITY
    saved = None
    if not with_term:
        saved = NON_OWNER_MOVE_PLAYBOOKS.pop(ability, None)
    try:
        out = {}
        for t in (ctx.move_tiles or []):
            p = (t["col"], t["row"])
            out[p] = tile_utility(ctx, p) + MIN_DIST_UTILITY.evaluate_movement(
                p, ctx.tgt_epos or ctx.epos, wt, ctx.pathdist_by_pos, case=ctx.mindist_case)
        return out
    finally:
        if saved is not None:
            NON_OWNER_MOVE_PLAYBOOKS[ability] = saved


def _ctx_for(sid, rid, uid, wt):
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    pred = _scene.build_predictor(lambda m, b, t=90: _r(sid, m, b, t), rid)
    ctx = _ai_ctx.build(lambda m, b, t=90: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, pred)
    return ctx, dv, mov_by_unit


def run_psychic_fortress(seed=DEFAULT_SEED, board=DEFAULT_BOARD, p_units=DEFAULT_P,
                         a_units=DEFAULT_A, verbose=False) -> dict:
    """Monte le montage, rend le dict de mesure (ou `{"error": ...}`). Dispose ses runners."""
    from engine import weights as W
    from engine.utilities.tile import tile_leaf_ctx

    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_PF))
    if w <= 0:
        return {"error": "%s vaut 0 cote moteur -- rien a mesurer" % KEY_PF}

    rid, state, err = _build(seed, board, p_units, a_units)
    if rid is None:
        return {"error": "build KO : %s" % err}
    try:
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or []) if u.get("ctrl")}
        carrier = ids.get(CARRIER_PF)
        if carrier is None:
            return {"error": "porteur %s absent de la bataille" % CARRIER_PF}
        mov0 = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov0.get("units") or [])}
        # `nb` = voisinage NATIF (boardGraph), pas hexgeo : c'est ce que le natif appelle adjacent.
        ctx_c, _, _ = _ctx_for(sid, rid, carrier, wt)
        nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx_c.neigh_by_pos or {}).items()}
        occupied = {tuple(p) for p in (list(ctx_c.epos or ()) + list(ctx_c.fpos or ()))}
        occupied.add(tuple(ctx_c.origin))
        carrier_tiles = [(t["col"], t["row"])
                         for t in ((mov_by_unit.get(carrier) or {}).get("tiles") or [])]

        pick = None
        for mover_vis, mover in sorted(ids.items()):
            if mover == carrier:
                continue
            ctx_m, _, _ = _ctx_for(sid, rid, mover, wt)
            base = _score_map(ctx_m, wt, with_term=False, ability=PSYCHIC_FORTRESS)
            if len(base) < 2:
                continue
            order = sorted(base.items(), key=lambda kv: -kv[1])
            t1 = order[0][0]
            for t2, s2 in order[1:]:
                if base[t1] - s2 >= w:          # le terme ne pourrait pas renverser
                    break
                for slot in carrier_tiles:
                    if slot in occupied or slot in (t1, t2):
                        continue
                    if slot in nb.get(t2, ()) and slot not in nb.get(t1, ()):
                        pick = (mover_vis, mover, t1, t2, slot)
                        break
                if pick:
                    break
            if pick:
                break
        if pick is None:
            return {"error": "aucun couple (mover, T1, T2, tuile du porteur) discriminant sur "
                             "%s/%s -- montage a re-etalonner" % (board, seed)}
        mover_vis, mover, t1, t2, slot = pick
        if verbose:
            print("[etape1] mover=%s(u%s) T1=%s T2=%s porteur u%s -> %s"
                  % (mover_vis, mover, t1, t2, carrier, slot))
    finally:
        _dispose(sid, rid)

    # Runner NEUF : on ne mute jamais celui qui a servi a CHERCHER le montage.
    rid2, state2, err = _build(seed, board, p_units, a_units)
    if rid2 is None:
        return {"error": "build KO (2e) : %s" % err}
    try:
        res = _r(sid, "applyAction", {"runnerId": rid2, "action": {
            "kind": "move", "unitId": carrier, "to": {"col": slot[0], "row": slot[1]}}}, 90)
        if not (res.get("actions") or [{}])[0].get("ok"):
            return {"error": "applyAction move du porteur KO : %r" % res}
        ctx2, dv2, _ = _ctx_for(sid, rid2, mover, wt)
        off = _score_map(ctx2, wt, with_term=False, ability=PSYCHIC_FORTRESS)
        on = _score_map(ctx2, wt, with_term=True, ability=PSYCHIC_FORTRESS)
        if not on:
            return {"error": "le mover n'a plus de tuile candidate apres le deplacement du porteur"}
        p_off = max(off, key=lambda k: off[k])
        p_on = max(on, key=lambda k: on[k])

        allu = _r(sid, "aiDryRunAllUnits", {"runnerId": rid2}, 240)
        row = next((u for u in (allu.get("units") or []) if u.get("unitId") == mover), None)
        if row is None:
            return {"error": "mover absent de aiDryRunAllUnits"}
        msgs = row.get("proposed") or []
        mv = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
        if mv is None or any(m.get("cls") == "ActiveAbilityMessage" for m in msgs):
            return {"error": "la proposition native du mover n'est pas un MOVE PUR (%r) -- la tuile "
                             "viendrait du sweep d'ATTAQUE, hors du modele UnitMovement(6)"
                             % [m.get("cls") for m in msgs]}
        native = (mv["to"]["col"], mv["to"]["row"])

        # kits, DEUX substrats (le port lit le `triggered` du voisin, le natif l'AbilitiesComponent)
        leaf = tile_leaf_ctx(ctx2)
        kit_port = []
        for u in ((leaf.get("friend_units") or []) + (leaf.get("enemy_units") or [])):
            if u.get("id") == carrier:
                kit_port = list(u.get("triggered") or ())
        states = _r(sid, "unitAbilityStates", {"runnerId": rid2}, 180)
        srow = next((u for u in (states.get("units") or []) if u.get("entityId") == carrier), None)
        kit_live = [t.get("raw", [None])[0] for t in ((srow or {}).get("triggered") or [])]

        out = {"mover": mover, "mover_vis": mover_vis, "carrier": carrier, "slot": slot,
               "t1": t1, "t2": t2, "p_on": p_on, "p_off": p_off, "native": native,
               "weight": w, "kit_port": kit_port, "kit_live": kit_live,
               "term_on": on.get(p_on), "term_off": off.get(p_off), "board": board, "seed": seed}
        if verbose:
            print("[etape1] argmax port SANS terme=%s  AVEC terme=%s  NATIF=%s"
                  % (p_off, p_on, native))
            print("[etape1] kit porteur -- port=%r live=%r" % (kit_port, kit_live))
        return out
    finally:
        _dispose(sid, rid2)


# --------------------------------------------------------------------------------------------
# ETAPE 2 -- ECogSupport : CONFRONTABILITE (porteur hors pool + mover = son summon)
# --------------------------------------------------------------------------------------------
def step2_ecog_reachability(verbose=True) -> dict:
    """Ce que le montage d'`EcogSupport` exige, RE-DERIVE (jamais recopie) -- et ou il bute.

    Le terme ne peut mordre que pendant le sweep de tuiles d'une unite qui a le trait `Summon` ET
    dont le parent est le porteur. Il faut donc, dans l'ordre : le porteur EN BATAILLE (hors pool ->
    injection catalogue), le summon EFFECTIVEMENT invoque, puis un sweep de tuiles DE CE SUMMON."""
    import gameconfig as GC
    ab = GC.ability("EcogSupport") or {}
    consts = ab.get("constants") or {}
    kit = GC.unit(SUMMON_ECOG) or {}
    out = {"summon_id": consts.get("unitId"), "max_summons": consts.get("maxSummons"),
           "summon_traits": list(kit.get("traits") or ()),
           "carrier_in_pool": None}
    try:
        p = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool"], cwd=str(PYDIR),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out["carrier_in_pool"] = any(line.strip() == CARRIER_ECOG
                                     for line in (p.stdout or "").splitlines())
    except Exception as exc:                                     # pragma: no cover - diagnostic
        out["carrier_in_pool"] = "ERREUR: %s" % exc
    if verbose:
        print("[etape2] summon invoque par EcogSupport : %s (max %s), traits=%r"
              % (out["summon_id"], out["max_summons"], out["summon_traits"]))
        print("[etape2] porteur %s dans `rl_duel build --list-pool` : %s"
              % (CARRIER_ECOG, out["carrier_in_pool"]))
        print("[etape2] => montage = injection catalogue du porteur, PUIS sweep de tuiles du "
              "summon (que le natif joue par `PlayAutomaticUnits`, cf. #291).")
    return out


# Roster du montage ECog : le porteur (INJECTE au catalogue) + une cible REPARABLE, parce que le
# trigger natif est `On(0x30 = EventTriggerType.UnitRepaired) & OwnerIsCaster`
# (`ECogSupportAbility$$CreateTrigger`). C'est la reparation qui fait apparaitre l'E-Cog, pas le
# debut de bataille : `ECogSupport_InitAbility` ne fait qu'un `AddFlag(0x18)`.
ECOG_P_UNITS = "votanIronmaster,admecRuststalker,astraBullgryn"
ECOG_A_UNITS = "worldKharn,templChampion"
ECOG_REPAIREE = "admecRuststalker"          # trait Mechanical -> `AttackQuery$$EntityCanBeRepaired`
REPAIR_ABILITY = 28                         # ActiveAbilityType.Repair, derivee du trait `Mechanic`


def run_ecog_support(seed=DEFAULT_SEED, board=DEFAULT_BOARD, verbose=False) -> dict:
    """MONTAGE ECogSupport : fait REELLEMENT apparaitre l'E-Cog, puis mesure le terme du PORT sur le
    `ctx` LIVE de ce summon.

    Ce que ce montage PROUVE (et c'est ce qui manquait au verdict « probablement equivalent ») :
      * l'atteignabilite n'est pas deduite -- le summon apparait, mesure, sous le `visualId`
        `votanNpc1Ecog` (piege de nommage `case-92` §5 : ce n'est PAS l'id d'entree `votanSmnEcog`) ;
      * les TROIS gates du corps passent sur des donnees LIVES : `unit_traits` du summon porte bien
        `UnitTrait.Summon`, `unit_parent_id` resout bien vers le porteur, et le terme vaut le poids
        exactement sur les tuiles adjacentes au porteur.

    Ce qu'il NE prouve PAS, et qui reste NON CONFRONTE : que le NATIF choisisse la meme tuile. Un
    summon n'entre jamais dans `decisionView.toActivate` et `aiDryRunAllUnits` rend pour lui
    `FinishUnitTurnMessage` (#291) -- son mouvement est joue par `PlayAutomaticUnits` au turn-start
    SUIVANT de sa team, donc l'oracle est DESTRUCTIF (un point de mesure par bataille, pas de
    dry-run) et la geometrie du spawn est TIREE AU SORT par le natif
    (`PickRandomly(CanAddUnit(AdjacentTiles(Caster)), 1)`)."""
    import catalog_inject
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.utilities.tile import tile_leaf_ctx
    from engine.utilities.utility_type import UtilityType
    from engine.utilities.tile import TILE_LEAVES
    from engine import battle_query as bq

    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", KEY_ECOG))
    if w <= 0:
        return {"error": "%s vaut 0 cote moteur" % KEY_ECOG}

    # seed BC AUGMENTE (le porteur est hors pool) -- ecrit sous `logs/` du checkout, jamais `data/`.
    # ⚠ ET DESEQUIPE : la cible de reparation (`admecRuststalker`) porte AU SEED la relique
    # `TertiaryAbility = 1457` (`TriggeredAbilityType.KardiocoreGalvanus`), dont la face non-owner
    # verse **+20** sur les tuiles adjacentes a son porteur sous le gate
    # `UnitExtensions.IsMechanical(case.Unit)` -- et l'E-Cog, qui est le MOVER de cette mesure, est
    # justement mecanique. Depuis que `1457` est PORTEE (#477-r33), la feuille rend donc
    # legitimement `EcogSupport(10) + KardiocoreGalvanus(20)` la ou le modele de cette mesure
    # n'attend que le premier : MESURE, 4 tuiles divergentes (30 pour 10, et 20 pour 0 sur une
    # tuile adjacente au seul Ruststalker). Ce n'est pas un ecart de port -- c'est un CONFOND de
    # montage, et on l'isole comme #477-r31 l'a fait sur le sien.
    bc = catalog_inject._load_seed(None)
    rep = catalog_inject.unequip_relic(bc, ECOG_REPAIREE)
    if verbose:
        print("[etape3] relique retiree : %s TertiaryAbility %s -> None%s"
              % (rep["unitId"], rep["tertiaryBefore"],
                 "  [RIEN A FAIRE]" if rep["rien_a_faire"] else ""))
    bc_out = ROOT / "logs" / "runners" / ("probe433r4r3-bc-%s.json" % uuid.uuid4().hex[:8])
    bc_out.parent.mkdir(parents=True, exist_ok=True)
    catalog_inject.write_augmented_seed_bc(str(bc_out), [CARRIER_ECOG], seed_bc=bc)

    rid, _, err = _build(seed, board, ECOG_P_UNITS, ECOG_A_UNITS,
                         ["--seed-bc", str(bc_out),
                          "--unit-stat", "%s:RemainingHealth=1200" % ECOG_REPAIREE])
    if rid is None:
        return {"error": "build KO : %s" % err}
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}
        carrier, repairee = ids.get(CARRIER_ECOG), ids.get(ECOG_REPAIREE)
        if carrier is None or repairee is None:
            return {"error": "porteur ou cible absent (%r)" % sorted(ids)}
        res = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": carrier, "targetId": repairee,
            "abilityType": REPAIR_ABILITY}}, 180)
        act = (res.get("actions") or [{}])[0]
        if not act.get("ok"):
            return {"error": "cast Repair KO : %r" % res}
        spawned = [c for c in (act.get("changes") or []) if c.get("appeared")]
        if not spawned:
            return {"error": "aucun summon apparu au Repair -- `On(UnitRepaired)` n'a pas tire"}
        summon = int(spawned[0]["squadId"])
        summon_pos = (spawned[0]["to"]["col"], spawned[0]["to"]["row"])

        ctx_s, _, _ = _ctx_for(sid, rid, summon, wt)
        leaf_ctx = tile_leaf_ctx(ctx_s)
        traits = {int(t) for t in (leaf_ctx.get("unit_traits") or ())}
        parent = leaf_ctx.get("unit_parent_id")
        owner_rec = next((u for u in ((leaf_ctx.get("friend_units") or [])
                                      + (leaf_ctx.get("enemy_units") or []))
                          if u.get("id") == carrier), None)
        leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
        elev = leaf_ctx.get("elev_by_pos")
        neigh = leaf_ctx.get("neigh_by_pos") or {}
        opos = (owner_rec or {}).get("pos")
        # Le summon vient d'apparaitre : son tour est DEJA termine (#291), donc `aiMovableTiles` ne
        # lui rend AUCUNE tuile. On balaie donc TOUT le plateau -- ce que la feuille rendrait pour
        # chaque tuile candidate possible -- au lieu du seul `move_tiles`, qui serait vide.
        tiles, mism = {}, []
        for p in sorted(neigh):
            got = leaf.evaluate(p, {}, leaf_ctx, wt)
            want = w if (opos and bq.are_entities_adjacent(p, tuple(opos), elev)) else 0.0
            tiles[p] = got
            if abs(got - want) > 1e-9:
                mism.append((p, got, want))

        out = {"carrier": carrier, "summon": summon, "summon_pos": summon_pos,
               "summon_vis": next((u.get("visualId") for u in (
                   _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180).get("units") or [])
                   if u.get("id") == summon), None),
               "has_summon_trait": int(UnitTrait.Summon) in traits,
               "parent_uid": parent, "carrier_pos": tuple(opos) if opos else None,
               "weight": w, "n_tiles": len(tiles),
               "n_tiles_scored": sum(1 for v in tiles.values() if v > 0),
               "mismatch": mism, "board": board, "seed": seed}
        if verbose:
            print("[etape3] summon u%s (%s) apparu en %s ; porteur u%s en %s"
                  % (summon, out["summon_vis"], summon_pos, carrier, out["carrier_pos"]))
            print("[etape3] ctx LIVE du summon : trait Summon=%s  unit_parent_id=%s (porteur=%s)"
                  % (out["has_summon_trait"], parent, carrier))
            print("[etape3] feuille 4 sur %d tuiles candidates : %d a %s, %d divergences"
                  % (out["n_tiles"], out["n_tiles_scored"], w, len(mism)))
        return out
    finally:
        _dispose(sid, rid)
        try:
            bc_out.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--p-units", default=DEFAULT_P)
    ap.add_argument("--a-units", default=DEFAULT_A)
    ap.add_argument("--ecog", action="store_true", help="joue AUSSI l'etape 3 (montage ECogSupport)")
    a = ap.parse_args()
    rc = step0_weights()
    step2_ecog_reachability()
    if a.offline_only or rc:
        return rc
    r = run_psychic_fortress(seed=a.seed, board=a.board, p_units=a.p_units, a_units=a.a_units,
                             verbose=True)
    if "error" in r:
        print("[etape1] ECHEC : %s" % r["error"])
        return 1
    ok = (r["p_on"] != r["p_off"]) and (r["native"] == r["p_on"])
    print("[etape1] VERDICT: %s" % ("PASS" if ok else "FAIL"))
    if a.ecog:
        e = run_ecog_support(seed=a.seed, board=a.board, verbose=True)
        if "error" in e:
            print("[etape3] ECHEC : %s" % e["error"])
            return 1
        eok = (e["has_summon_trait"] and e["parent_uid"] == e["carrier"] and not e["mismatch"]
               and e["n_tiles_scored"] > 0)
        print("[etape3] VERDICT: %s" % ("PASS" if eok else "FAIL"))
        ok = ok and eok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
