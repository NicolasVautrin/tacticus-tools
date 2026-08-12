"""#947 / #948 -- MESURE live des DEUX passifs `_ExtraDamageEffect` portes ensemble.

  * `HeadClaimer` (`blackHaarken` << Haarken >>) -- compteur de TETES : chaque non-ami VAINCU monte
    `1028 HeadClaimer_ExtraDmg` de +1 ; SEUL un `Hero` (le << Character >> de l'i2) monte AUSSI
    `1029 HeadClaimer_ExtraHit`. Le discriminant est donc une victime NON-Hero, et le seul porteur
    confrontable qui n'ait PAS le trait `Hero` est une MACHINE OF WAR (`--a-mow`).
  * `EnmityForTheUnworthy` (`darkaCompanion` << Forcas >>) -- DEUX bonus a compteurs DIFFERENTS :
    `+extraDmgPct %` par unite ADJACENTE (amies ET ennemies) et `+extraDmg` par ami DARK ANGEL
    adjacent. La geometrie est CALCULEE depuis le `boardGraph` puis ASSERTIONNEE, jamais esperee.

Chaque bras REJOUE offline le meme enchainement depuis la capture prise AVANT l'action, avec le
MEME flux RNG, et compare COUP PAR COUP (degat) et NIVEAU PAR NIVEAU (les stacks).

MUTANTS (`--mutate <nom>`) -- chacun doit MORDRE, et chacun EST un etat reel du depot :
  * `hc_effet`   : retire `EFFECT_CLASSES["HeadClaimer_ExtraDmg"]`   -> le stack monte, le degat non ;
  * `hc_hits`    : retire `EFFECT_CLASSES["HeadClaimer_ExtraHit"]`   -> le NOMBRE de coups baisse ;
  * `hc_trigger` : retire `ABILITY_TRIGGERS["HeadClaimer"]`          -> aucun stack ne monte ;
  * `en_da`      : force le compteur d'amis DARK ANGELS a 0          -> la face ADDITIVE disparait ;
  * `en_units`   : force le compteur d'unites adjacentes a 0         -> la face POURCENTAGE disparait.

CLI (depuis scripts/python) :
  python probe_947_948_extra_damage_passives.py
  python probe_947_948_extra_damage_passives.py --bras enmity --verbose
  python probe_947_948_extra_damage_passives.py --bras headclaimer --mutate hc_trigger

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                    # noqa: E402

BOARD = "MC1_67"
SEED = "4321"

#: --- bras `enmity` -------------------------------------------------------------------------------
FORCAS = "darkaCompanion"        # le porteur d'`EnmityForTheUnworthy` (melee)
AMI_DA_1 = "darkaHellblaster"    # Dark Angels -> compte dans les DEUX compteurs
AMI_DA_2 = "darkaAsmodai"        # Dark Angels -> idem
AMI_HORS_DA = "blackAbaddon"     # Black Legion -> compte SEULEMENT dans `AdjacentUnits`
CIBLE_EN = "tauCrisis"           # la victime de Forcas (ennemie -> compte aussi dans `AdjacentUnits`)

#: --- bras `headclaimer` --------------------------------------------------------------------------
HAARKEN = "blackHaarken"
VICTIME_HERO_1 = "tauCrisis"     # HERO ennemi -> monte 1028 ET 1029
VICTIME_HERO_2 = "necroWarden"   # idem -> les DEUX compteurs passent a 2
CIBLE_FINALE = "tauAunShi"       # la 3e cible, celle sur qui on MESURE le bonus accumule

#: ⚠ LA BRANCHE `If(IsHero(Target), AddEffectOrIncreaseLevel(1029))` N'EST PAS CONFRONTEE PAR SON
#: CAS NEGATIF, et la raison est MESUREE, pas supposee :
#:   * toutes les unites `lineup` du pool portent `Hero` (balayage gameconfig), et le natif le
#:     REPOSE independamment de `BC.Units[].Traits` -- mesure : `--unit-stat "necroWarden:Traits=[]"`
#:     laisse `combatSnapshot.traits == [16]` (= `UnitTrait.Hero` SEUL) ;
#:   * les MACHINES OF WAR sont les seules unites confrontables SANS `Hero` (mesure :
#:     `traits == [1006 Xenos, 1049 MachineOfWar]`), mais elles ne sont PAS posees sur le plateau --
#:     absentes de `decisionView.units`, donc inattaquables en melee, et `--a-place` les refuse
#:     (il n'accepte que des `--a-units`).
#: Le cas negatif est donc garde OFFLINE (`test_947_948_..._offline.py`, etage HeadClaimer/IsHero),
#: qui execute le behaviour contre un `AbilityEntities` dont la cible n'a pas le trait.
CAS_NEGATIF_ISHERO = "non confronte live -- cf. le commentaire ci-dessus (mesure)"

EXTRA_DMG_EFFECT = 1028          # EffectType.HeadClaimer_ExtraDmg
EXTRA_HIT_EFFECT = 1029          # EffectType.HeadClaimer_ExtraHit
ENMITY_ADD = 1400                # EffectType.EnmityForTheUnworthy_ExtraDamage
ENMITY_PCT = 1399                # EffectType.EnmityForTheUnworthy_ExtraDamagePct


# --------------------------------------------------------------------------- montage live


def _build(seed, board, p_units, a_units, extra, hp=None, mow=None):
    sf = ROOT / "logs" / "runners" / ("p947-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
            "--board", board, "--rank", "17",
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units),
            "--crit", "0,0", "--crit-target", "0,0", "--block-target", "0,0",
            "--block-player", "0,0", "--no-ai", *extra]
    if hp:
        # `--hp-target` SEUL : le porteur garde ses PV natifs. Le passer aussi en `--hp-player`
        # mettrait Haarken a 1 PV, et le tour d'IA adverse necessaire pour lui rendre la main
        # (§ `_passer_le_tour`) le tuerait avant l'attaque de mesure.
        argv += ["--hp-target", hp]
    if mow:
        argv += ["--a-mow", mow]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-900:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _effect_level(dv, uid, effect_type):
    """(present, niveau) de l'instance `effect_type` sur `uid` -- `EffectComponent+0x68`."""
    for e in ((_unit(dv, uid) or {}).get("effects") or []):
        et = e.get("effectType")
        if et is not None and int(et) == int(effect_type):
            return True, e.get("level")
    return False, None


def _normal_attack_id(dv, uid):
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _pos(dv, uid):
    u = _unit(dv, uid)
    p = (u or {}).get("pos")
    return None if not p else (int(p["col"]), int(p["row"]))


def _attack(rpc, rid, cid, tid, ab):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ab)}, "captureEvents": True}, 150)
    hits = []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and int(td.get("Target_Id", td.get("TargetId", tid)) or tid) == int(tid):
                hits.append(int(td["Amount"]))
    return res, hits


def _passer_le_tour(rpc, rid, mon_joueur, essais=6):
    """Une unite n'a QU'UNE action par tour : sans passage de tour, la 2e attaque de Haarken est
    refusee et le compteur reste a 1 (mesure : `1028 = 1` la ou on attendait 2). On termine donc le
    tour cote a cote -- `applyAction {"kind": "endturn"}` -- jusqu'a ce que la main revienne.
    Rend `True` si elle est revenue, `False` sinon (le bras rend alors `indisponible`)."""
    for _ in range(essais):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        dv = rpc("decisionView", {"runnerId": rid}, 120)
        if dv.get("currentPlayer") == mon_joueur or dv.get("currentPlayerId") == mon_joueur:
            return True
    return False


def _sonde_graphe(rpc, board_id, seed):
    """Un build MINIMAL, uniquement pour lire le `boardGraph` et calculer une geometrie AVANT le
    build de mesure (`--place` est un argument de BUILD). Le runner est dispose aussitot."""
    from engine.entities.pathfinding.board import Board
    rid, _sf, err = _build(seed, board_id, [FORCAS], [CIBLE_EN], [])
    if rid is None:
        return None, "sonde KO : %s" % err
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        return Board(bg["tiles"], adjacency="native_sym"), None
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _tuile_a_six_voisins(board):
    """La geometrie de ce bras COMPTE des voisins : on exige explicitement une tuile a 6 voisins
    JOUABLES, on ne l'espere pas (runner.md : un spawn en coin sous-exerce silencieusement toute
    mecanique d'adjacence). Rend `(centre, [voisins])`, centre le plus proche du milieu du board."""
    ids = sorted(board.by_id.keys())
    coords = [c for c in (board.coord(t) for t in ids) if c is not None]
    if not coords:
        return None, None
    cols = [c for c, _r in coords]
    rows = [r for _c, r in coords]
    mid = ((min(cols) + max(cols)) / 2.0, (min(rows) + max(rows)) / 2.0)
    best = None
    for t in ids:
        c = board.coord(t)
        if c is None or not board.walkable(t):
            continue
        # les voisins doivent etre POSABLES : une tuile a 6 voisins dont 3 murs sous-exercerait
        # le compteur exactement comme un spawn en coin (runner.md).
        ring = [x for x in board.neighbours(t) if board.walkable(x)]
        if len(ring) < 6:
            continue
        d = abs(c[0] - mid[0]) + abs(c[1] - mid[1])
        if best is None or d < best[0]:
            best = (d, t, ring[:6])
    if best is None:
        return None, None
    return board.coord(best[1]), [board.coord(x) for x in best[2]]


# --------------------------------------------------------------------------- rejeu offline


def _port_level(state, uid, effect_type):
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(uid), []):
        if e.effect_type == effect_type and not e.consumed:
            return int(e.level or 0)
    return None


def _replay(cap, board, paires, mutate=None, niveaux_de=()):
    """Rejoue les attaques `paires = [(attaquant, cible), ...]` ENCHAINEES sur le MEME `State` et le
    MEME flux RNG. C'est l'ENCHAINEMENT qui compte pour `HeadClaimer` : l'attaque #3 n'est exercee
    que si les kills #1 et #2 ont monte les stacks.

    ⚠ LES MUTANTS SONT POSES **AVANT** `load_state` : `EFFECT_CLASSES` n'est lu qu'a la CREATION des
    instances (`EffectFactory.create`), donc un `pop` fait apres arrive TROP TARD pour un effet deja
    present au seed -- c'est la forme exacte du faux vert que #932 a documentee."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki import enmity_for_the_unworthy as EN

    saved_trig = saved_eff = saved_count = None
    portes: list = []
    if mutate == "hc_trigger":
        saved_trig = ABILITY_TRIGGERS.pop("HeadClaimer", None)
        assert saved_trig is not None, "MUTANT INOPERANT : ABILITY_TRIGGERS['HeadClaimer'] absent"
    elif mutate in ("hc_effet", "hc_hits"):
        _cle = "HeadClaimer_ExtraDmg" if mutate == "hc_effet" else "HeadClaimer_ExtraHit"
        saved_eff = (_cle, EFFECT_CLASSES.pop(_cle, None))
        assert saved_eff[1] is not None, "MUTANT INOPERANT : EFFECT_CLASSES[%r]" % _cle
    elif mutate in ("en_da", "en_units"):
        cle = EN.CTX_ADJACENT_DA if mutate == "en_da" else EN.CTX_ADJACENT_UNITS
        saved_count = EN._EnmityForTheUnworthyEffect._count

        def _zero(self, ctx, _cle=cle, _old=saved_count):
            return 0 if self._CTX_KEY == _cle else _old(self, ctx)
        EN._EnmityForTheUnworthyEffect._count = _zero
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        out = []
        for att, tgt in paires:
            e = st.get_entity(int(tgt))
            hc = e.get_component(HealthComponent)
            h0 = int(hc.hp) if hc is not None else None
            runner.apply(AttackUnitMessage(int(att), int(tgt)))
            last = runner.damage_handler.last or {}
            # ⚠ #949 -- LE LEDGER COMPLET N'EST **PAS** `last["per_hit"]`. Ce champ ne porte que la
            # PHASE D'ARME : `damage_ops/normal.py::execute` rend les coups du canal #179 A COTE,
            # dans `last["additional_hits"]`, et c'est voulu (deux sous-operations natives
            # distinctes). Les additionner ici n'est donc pas une commodite -- c'est ce qui rend la
            # comparaison HOMOGENE avec le ledger natif, qui, lui, est un flux d'events unique.
            # Sans ce recollement, tout attaquant portant un descripteur #179 ACTIF fabrique un faux
            # ecart de coups : c'est exactement ce qui a fait ecrire << 8 coups natif contre 6 port,
            # ecart de 66 723 >> au Sec.6 de `docs/rl/case-947-948-passifs-extra-damage.md`, alors
            # que le port etait bit-exact (mesure : `probe_949_ltgb_coup_manquant.py`, ledger natif
            # reproduit 6/6, `hp_delta` == somme des coups natifs). L'ecart n'existait que dans le
            # LECTEUR. `hp_delta` (retrait REEL de PV) est publie a cote comme arbitre : il est
            # insensible a la facon dont le port ventile ses canaux.
            ah = last.get("additional_hits") or {}
            per_hit = list(last.get("per_hit") or []) + list(ah.get("per_hit") or [])
            out.append({"attacker": int(att), "target": int(tgt),
                        "hp_delta": (None if h0 is None else h0 - int(hc.hp)),
                        "total": int(last.get("total") or 0) + int(ah.get("total") or 0),
                        "per_hit": per_hit,
                        # les deux canaux restent lisibles SEPAREMENT : une divergence de compte de
                        # coups doit pouvoir dire LEQUEL des deux a bouge.
                        "arme_per_hit": last.get("per_hit"),
                        "additional_per_hit": ah.get("per_hit")})
        niveaux = {"%s@%s" % (et, u): _port_level(st, int(u), int(et))
                   for u, et in niveaux_de}
        # DIAGNOSTIC : ce que le port a REELLEMENT materialise sur l'attaquant. Sans lui, une
        # divergence de COUPS ne dit pas si l'instance manque, si sa CLASSE n'est pas cablee, ou si
        # le canal ne la consulte pas.
        if paires:
            att0 = int(paires[0][0])
            eff = getattr(st, "effects", None)
            portes = [] if eff is None else [
                (e.name, e.effect_type, e.level, e.__class__.__name__, e.active)
                for e in eff.by_unit.get(att0, []) if not e.consumed]
    finally:
        if saved_trig is not None:
            ABILITY_TRIGGERS["HeadClaimer"] = saved_trig
        if saved_eff is not None:
            EFFECT_CLASSES[saved_eff[0]] = saved_eff[1]
        if saved_count is not None:
            from engine.entities.effects.loki import enmity_for_the_unworthy as _EN
            _EN._EnmityForTheUnworthyEffect._count = saved_count
    return {"attacks": out, "niveaux": niveaux, "effets_attaquant": portes}


# --------------------------------------------------------------------------- bras ENMITY


def _bras_enmity(rpc, board_id, seed, mutate, verbose, nom="enmity"):
    """DEUX regimes sur le MEME board, de geometries CALCULEES puis ASSERTIONNEES :

      * `solo` : Forcas adjacent a SA SEULE cible          -> units=1, DA=0
      * `entoure` : + 2 amis DARK ANGELS + 1 ami HORS-DA   -> units=4, DA=2

    L'ecart entre les deux regimes exerce les DEUX faces a la fois : la face POURCENTAGE passe de
    x1 a x4 et la face ADDITIVE de 0 a 2 -- une seule des deux fausse ferait diverger."""
    board, err = _sonde_graphe(rpc, board_id, seed)
    if board is None:
        return {"verdict": "indisponible", "cause": err}
    centre, ring = _tuile_a_six_voisins(board)
    if centre is None:
        return {"verdict": "indisponible", "cause": "aucune tuile a 6 voisins sur %s" % board_id}

    lignes, mesures = [], []
    for regime in ("solo", "entoure"):
        place = ["--place", "%s:%d,%d" % (FORCAS, centre[0], centre[1])]
        aplace = ["--a-place", "%s:%d,%d" % (CIBLE_EN, ring[0][0], ring[0][1])]
        amis = []
        if regime == "entoure":
            amis = [AMI_DA_1, AMI_DA_2, AMI_HORS_DA]
            for i, v in enumerate(amis):
                place += ["--place", "%s:%d,%d" % (v, ring[i + 1][0], ring[i + 1][1])]
        rid, _sf, err = _build(seed, board_id, [FORCAS] + amis, [CIBLE_EN], place + aplace)
        if rid is None:
            return {"verdict": "indisponible", "cause": "build %s KO : %s" % (regime, err)}
        try:
            dv = _view(rpc, rid, inactive=True)
            fid = (_by_vis(dv, FORCAS) or {}).get("id")
            cid = (_by_vis(dv, CIBLE_EN) or {}).get("id")
            if fid is None or cid is None:
                return {"verdict": "indisponible", "cause": "unite absente (%s)" % regime}
            fid, cid = int(fid), int(cid)
            # GEOMETRIE ASSERTIONNEE -- recalculee depuis les positions REELLES, pas depuis le plan.
            fpos = _pos(dv, fid)
            ftile = board.id_at(*fpos)
            voisines = {board.coord(t) for t in board.neighbours(ftile)}
            import gameconfig as GC
            adj_units = adj_da = 0
            for u in (dv.get("units") or []):
                if int(u.get("id", -1)) == fid or not u.get("pos"):
                    continue
                p = (int(u["pos"]["col"]), int(u["pos"]["row"]))
                if p not in voisines:
                    continue
                adj_units += 1
                if u.get("team") == _unit(dv, fid).get("team") and \
                        (GC.unit(u.get("visualId")) or {}).get("FactionId") == "DarkAngels":
                    adj_da += 1
            attendu = (1, 0) if regime == "solo" else (4, 2)
            if (adj_units, adj_da) != attendu:
                return {"verdict": "indisponible",
                        "cause": "geometrie %s NON obtenue : units=%d DA=%d (attendu %s) ; "
                                 "forcas@%s ring=%s" % (regime, adj_units, adj_da, attendu,
                                                        fpos, sorted(voisines))}
            pres_add, lvl_add = _effect_level(dv, fid, ENMITY_ADD)
            pres_pct, lvl_pct = _effect_level(dv, fid, ENMITY_PCT)
            na = _normal_attack_id(dv, fid)
            if na is None:
                return {"verdict": "indisponible", "cause": "attaque normale de Forcas introuvable"}
            cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                   "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
                   "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
            _r, hits = _attack(rpc, rid, fid, cid, na)
            if not hits:
                return {"verdict": "indisponible",
                        "cause": "cascade VIDE en %s (ok=%s)" % (regime, _r.get("ok"))}
            port = _replay(cap, board, [(fid, cid)], mutate=mutate)
            pt = port["attacks"][0]["total"]
            lignes.append({"rang": len(lignes) + 1, "attacker": "%s/%s" % (FORCAS, regime),
                           "natif": sum(hits), "port": (None if pt is None else int(pt)),
                           "ecart": (None if pt is None else int(pt) - sum(hits)),
                           "egal": pt is not None and int(pt) == sum(hits),
                           "natif_hits": hits, "port_hits": port["attacks"][0].get("per_hit")})
            mesures.append({"regime": regime, "adj_units": adj_units, "adj_da": adj_da,
                            "effets": {"1400": (pres_add, lvl_add), "1399": (pres_pct, lvl_pct)},
                            "natif_total": sum(hits)})
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    # Le REGIME doit CHANGER le resultat : deux totaux egaux signeraient une mesure vide.
    totaux = [m["natif_total"] for m in mesures]
    if len(set(totaux)) < 2:
        return {"verdict": "indisponible",
                "cause": "les deux regimes rendent le MEME total natif (%s) -- la geometrie "
                         "n'a rien change, la mesure est vide" % totaux}
    ok = all(l["egal"] for l in lignes)
    out = {"bras": nom, "verdict": "EGAL" if ok else "DIVERGE", "lignes": lignes,
           "mesures": mesures, "mutate": mutate}
    if verbose:
        print(json.dumps(out, indent=1))
    return out


# --------------------------------------------------------------------------- bras HEADCLAIMER


def _bras_headclaimer(rpc, board_id, seed, mutate, verbose, nom="headclaimer"):
    """TROIS actions ENCHAINEES sur le meme runner :

      1. Haarken TUE un HERO ennemi  -> attendu : `1028` = 1 ET `1029` = 1 ;
      2. Haarken TUE un 2e HERO      -> attendu : `1028` = 2 ET `1029` = 2 (aucun cap) ;
      3. Haarken attaque une 3e cible SURVIVANTE -> c'est LA que le bonus accumule se mesure, sur
         les DEUX axes a la fois (le degat par coup ET le NOMBRE de coups).

    `--hp-target 1` rend les kills deterministes (le levier met aussi `Armor`/`FixedArmor` a 0, ce
    qui est SANS effet ici : on ne mesure pas l'etage armure) ; la 3e cible recoit ses PV par
    `--unit-stat`, sinon elle meurt au premier coup et l'attaque #3 n'a plus de ledger.

    ⚠ Le cas NEGATIF du `If(IsHero(Target))` n'est PAS confronte ici -- cf. `CAS_NEGATIF_ISHERO`
    en tete de module (raison MESUREE, pas supposee)."""
    board, err = _sonde_graphe(rpc, board_id, seed)
    if board is None:
        return {"verdict": "indisponible", "cause": err}
    centre, ring = _tuile_a_six_voisins(board)
    if centre is None:
        return {"verdict": "indisponible", "cause": "aucune tuile a 6 voisins sur %s" % board_id}
    place = ["--place", "%s:%d,%d" % (HAARKEN, centre[0], centre[1]),
             "--a-place", "%s:%d,%d" % (VICTIME_HERO_1, ring[0][0], ring[0][1]),
             "--a-place", "%s:%d,%d" % (CIBLE_FINALE, ring[1][0], ring[1][1]),
             "--a-place", "%s:%d,%d" % (VICTIME_HERO_2, ring[2][0], ring[2][1]),
             "--unit-stat", "%s:Health=900000,RemainingHealth=900000" % CIBLE_FINALE,
             # ISOLER LA MECANIQUE MESUREE. Haarken porte `LetTheGalaxyBurn` (trait 1058 -> effet
             # 1477), dont le `CreateAdditionalHits` ajoute UN coup ; le retrait garde la
             # comparaison de COUPS lisible sur le seul `HeadClaimer`. `Traits=[]` retire les traits
             # du KIT ; le natif REPOSE `Hero` de son cote (mesure : le `combatSnapshot` rend
             # `[16]`), ce qui est SANS effet sur l'attaquant.
             #
             # ⚠ #949 -- CE COMMENTAIRE PORTAIT UNE MESURE FAUSSE, ET ELLE VENAIT DU LECTEUR. Il
             # annoncait << 8 coups natif contre 6 port, dont un ecart de 66 723 sur le dernier >>.
             # Re-mesure (`probe_949_ltgb_coup_manquant.py --bras reproduction`) : le `66 723`
             # n'est PAS un coup -- son tag natif porte `Effect_Type = 1476` (`DespoiledGround`,
             # le DoT de tuile pose par `LetTheGalaxyBurn_ResetAbility`, non porte : residu deja
             # nomme dans `runner/operations/triggers/loki/let_the_galaxy_burn.py`). Le ledger de
             # COUPS natif en compte donc **7**, pas 8 ; et le port en rend 7 lui aussi, bit-exact,
             # des qu'on lit son canal #179 (cf. `_replay` ci-dessus). L'ecart de coups etait un
             # ARTEFACT D'OBSERVATION : `_attack` agrege TOUT event portant un `Amount`, canaux
             # etrangers a l'attaque compris, alors que `_replay` ne lisait que la phase d'arme.
             # Le retrait des traits reste utile (il garde le bras focalise sur `HeadClaimer`),
             # mais il ne masque AUCUN bug de port.
             "--unit-stat", "%s:Traits=[]" % HAARKEN]
    rid, _sf, err = _build(seed, board_id, [HAARKEN],
                           [VICTIME_HERO_1, CIBLE_FINALE, VICTIME_HERO_2], place, hp="1")
    if rid is None:
        return {"verdict": "indisponible", "cause": "build KO : %s" % err}
    try:
        dv = _view(rpc, rid, inactive=True)
        ids = {}
        for v in (HAARKEN, VICTIME_HERO_1, CIBLE_FINALE, VICTIME_HERO_2):
            u = _by_vis(dv, v)
            if u is None:
                return {"verdict": "indisponible", "cause": "unite absente : %s" % v}
            ids[v] = int(u["id"])
        hpos = _pos(dv, ids[HAARKEN])
        voisines = {board.coord(t) for t in board.neighbours(board.id_at(*hpos))}
        for v in (VICTIME_HERO_1, CIBLE_FINALE, VICTIME_HERO_2):
            if _pos(dv, ids[v]) not in voisines:
                return {"verdict": "indisponible",
                        "cause": "%s @%s n'est PAS adjacent a Haarken @%s (voisines %s)"
                                 % (v, _pos(dv, ids[v]), hpos, sorted(voisines))}
        # aucune tete au depart : sinon la mesure des increments serait faussee
        for et in (EXTRA_DMG_EFFECT, EXTRA_HIT_EFFECT):
            if _effect_level(dv, ids[HAARKEN], et)[0]:
                return {"verdict": "indisponible",
                        "cause": "Haarken porte deja l'effet %d au depart" % et}
        na = _normal_attack_id(dv, ids[HAARKEN])
        if na is None:
            return {"verdict": "indisponible", "cause": "attaque normale de Haarken introuvable"}
        def _capture():
            return {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                    "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
                    "rng": rpc("dumpRng", {"runnerId": rid}, 30)}

        mon_joueur = (_view(rpc, rid).get("currentPlayer")
                      or _view(rpc, rid).get("currentPlayerId"))
        # DEUX captures, et c'est LOAD-BEARING : le natif joue des `endturn` entre les attaques
        # (une action par unite et par tour), or le rejeu offline enchaine des `AttackUnitMessage`
        # SANS passage de tour. Rejouer les trois d'un bloc depuis une capture unique comparerait
        # deux histoires differentes. On confronte donc SEPAREMENT ce que chaque capture permet :
        #   cap_trigger -> le kill #1 : les NIVEAUX (face TRIGGER, `AddEffectOrIncreaseLevel`) ;
        #   cap_degat   -> l'attaque #3 : le DEGAT et les COUPS (face EFFET, magnitude x level).
        cap_trigger = _capture()
        etapes, natif, cap_degat = [], [], None
        paires = [(ids[HAARKEN], ids[VICTIME_HERO_1]),
                  (ids[HAARKEN], ids[VICTIME_HERO_2]),
                  (ids[HAARKEN], ids[CIBLE_FINALE])]
        for i, (att, tgt) in enumerate(paires):
            if i == 2:
                cap_degat = _capture()
            _r, hits = _attack(rpc, rid, att, tgt, na)
            dv = _view(rpc, rid, inactive=True)
            d_pres, d_lvl = _effect_level(dv, ids[HAARKEN], EXTRA_DMG_EFFECT)
            h_pres, h_lvl = _effect_level(dv, ids[HAARKEN], EXTRA_HIT_EFFECT)
            etapes.append({"rang": i + 1, "cible": tgt, "hits": hits,
                           "1028": (d_pres, d_lvl), "1029": (h_pres, h_lvl)})
            natif.append({"attacker": HAARKEN, "hits": hits, "total": sum(hits)})
            if i < 2 and not _passer_le_tour(rpc, rid, mon_joueur):
                return {"verdict": "indisponible",
                        "cause": "la main n'est pas revenue apres l'attaque #%d -- impossible de "
                                 "poursuivre l'accumulation" % (i + 1)}
        # LE NATIF DOIT AVOIR ACCUMULE -- sinon il n'y a RIEN a confronter (jamais un vert par
        # defaut) : `1028` et `1029` a 1 apres le premier kill de HERO, a 2 apres le second (aucun
        # cap : le `max` d'`AddEffectOrIncreaseLevel` est NULL).
        for i, attendu in ((0, 1), (1, 2)):
            for et in ("1028", "1029"):
                pres, lvl = etapes[i][et]
                if not pres or int(lvl or 0) != attendu:
                    return {"verdict": "indisponible",
                            "cause": "kill #%d : %s = %s (attendu niveau %d) -- l'accumulation "
                                     "native n'a pas eu lieu" % (i + 1, et, (pres, lvl), attendu)}
        if not etapes[2]["hits"]:
            return {"verdict": "indisponible",
                    "cause": "attaque #3 sans cascade -- la 3e cible est morte trop tot"}
        # (A) face TRIGGER : le kill #1 rejoue depuis la capture d'AVANT -- les NIVEAUX.
        niv_de = [(ids[HAARKEN], EXTRA_DMG_EFFECT), (ids[HAARKEN], EXTRA_HIT_EFFECT)]
        p_trig = _replay(cap_trigger, board, [paires[0]], mutate=mutate, niveaux_de=niv_de)
        nat_niv = {"%d@%d" % (EXTRA_DMG_EFFECT, ids[HAARKEN]): etapes[0]["1028"][1],
                   "%d@%d" % (EXTRA_HIT_EFFECT, ids[HAARKEN]): etapes[0]["1029"][1]}
        niveau_egal = all(
            (p_trig["niveaux"].get(k) is not None and int(p_trig["niveaux"][k]) == int(v or 0))
            for k, v in nat_niv.items())
        # (B) face EFFET : l'attaque #3 rejouee depuis la capture d'AVANT -- le DEGAT et les COUPS,
        # avec les DEUX stacks deja a 2 dans l'etat charge.
        p_dmg = _replay(cap_degat, board, [paires[2]], mutate=mutate, niveaux_de=niv_de)
        n3, p3 = natif[2], p_dmg["attacks"][0]
        pt = p3["total"]
        lignes = [{"rang": 3, "attacker": "%s (2 tetes)" % HAARKEN, "natif": int(n3["total"]),
                   "port": (None if pt is None else int(pt)),
                   "ecart": (None if pt is None else int(pt) - int(n3["total"])),
                   "egal": pt is not None and int(pt) == int(n3["total"]),
                   "natif_hits": n3["hits"], "port_hits": p3.get("per_hit")}]
        # LE NOMBRE DE COUPS est un observable a part entiere ici : `1029` ajoute `extraHit x level`
        # coups, donc un port qui ne porterait QUE la face degat rendrait le bon total par coup et
        # le MAUVAIS nombre de coups.
        coups_egal = (p3.get("per_hit") is not None
                      and len(p3["per_hit"]) == len(n3["hits"]))
        ok = all(l["egal"] for l in lignes) and niveau_egal and coups_egal
        out = {"bras": nom, "verdict": "EGAL" if ok else "DIVERGE", "lignes": lignes,
               "etapes": etapes, "niveaux_natif": nat_niv, "niveaux_port": p_trig["niveaux"],
               "niveau_egal": niveau_egal, "coups_egal": coups_egal,
               "coups_natif": len(n3["hits"]),
               "coups_port": (None if p3.get("per_hit") is None else len(p3["per_hit"])),
               "effets_port": p_dmg.get("effets_attaquant"),
               "effets_natif": [(e.get("effectType"), e.get("level"), e.get("name"))
                                for e in ((_unit(cap_degat["dec"], ids[HAARKEN]) or {})
                                          .get("effects") or [])],
               "mutate": mutate}
        if verbose:
            print(json.dumps(out, indent=1))
        return out
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


# --------------------------------------------------------------------------- CLI


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", choices=["enmity", "headclaimer", "tous"], default="tous")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--mutate", default=None)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    rpc = _mkrpc()
    bras = ["enmity", "headclaimer"] if a.bras == "tous" else [a.bras]
    rc = 0
    for b in bras:
        fn = _bras_enmity if b == "enmity" else _bras_headclaimer
        res = fn(rpc, a.board, a.seed, a.mutate, a.verbose)
        print("[%s] verdict=%s" % (b, res.get("verdict")))
        if res.get("cause"):
            print("   cause : %s" % res["cause"])
        for l in (res.get("lignes") or []):
            print("   #%d %-28s natif=%-8s port=%-8s ecart=%s" % (
                l["rang"], l["attacker"], l["natif"], l["port"], l["ecart"]))
        for m in (res.get("mesures") or []):
            print("   geo %-8s units=%d DA=%d effets=%s" % (
                m["regime"], m["adj_units"], m["adj_da"], m["effets"]))
        for e in (res.get("etapes") or []):
            print("   etape %d cible=%s hits=%s 1028=%s 1029=%s" % (
                e["rang"], e["cible"], e["hits"], e["1028"], e["1029"]))
        if res.get("niveaux_natif"):
            print("   niveaux natif=%s port=%s egal=%s" % (
                res["niveaux_natif"], res.get("niveaux_port"), res.get("niveau_egal")))
            print("   coups natif=%s port=%s egal=%s" % (
                res.get("coups_natif"), res.get("coups_port"), res.get("coups_egal")))
            print("   effets natif=%s" % (res.get("effets_natif"),))
            print("   effets port =%s" % (res.get("effets_port"),))
        if res.get("verdict") != "EGAL":
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
