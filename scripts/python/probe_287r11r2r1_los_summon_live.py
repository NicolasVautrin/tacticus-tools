"""#287-r11-r2-r1 -- CONFRONTATION LIVE de la LIGNE DE VUE d'`IsTargetInAttackRangeForSummon`,
l'etage que le gate de ciblage de `1076 MV71SniperDroneSquadAttack` heritait COLLAPSE.

CE QUE #287-r11-r2 A LAISSE OUVERT. Le gate rend `1 ValidRequest` quand
`MV71SniperDroneSquadAttackAbility$$PickTile` ne trouve AUCUNE tuile de spawn ; le troisieme filtre
de `PickTile` est `IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon`
(`IBattleQuery` slot 196), que le port reduisait a `1 <= distance(tuile, cible) <= portee`. Or ce
corps natif, LU :

    if (target == null || !UnitExtensions.IsTargetable(target)) return false;
    range = max over weapons of (w.Range ?? 1);
    if (DamageCalculations.ShouldApplyRangedInMelee(parent, [tile], state, true)) {
        range = 1; if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false;
    } else if (range == 1 && !TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false;
    if (BattleQuery.GetDistance(tile, target) > range) return false;
    foreach (t in GetTiles(target))
        if (!<IMovementQuery slot 16>(tile, t, 6, 2).IsNullOrEmpty()) return false;   // LIGNE DE VUE
    if (range == 1)
        return DamageCalculations.CanMeleeAttackOverElevationDifference(tile, GetMainTile(target));
    return true;

Tant que `PickTile` ne servait qu'a l'EXECUTION, le collapse coutait une tuile de spawn parfois
differente. Depuis #287-r11-r2 il decide de la LEGALITE d'un cast : une tuile MASQUEE PAR DU
TERRAIN etait comptee valide, donc le port ACCEPTAIT une cible que le natif REFUSE (SOUS-refus).

⚠ LA GEOMETRIE EST PLACEE, ET LE BOARD EST CHOISI POUR ELLE. `C3_47` porte deux tuiles `Block`
d'elevation 3 en (1,1) et (1,2) ; depuis la tuile (0,1) (Grass, elevation 0), le disque r=4 se
coupe en DEUX : quatre tuiles marchables CLAIRES -- (0,2) (0,3) (1,4) (2,4) -- et DIX tuiles
marchables OBSCURCIES par ce mur de roche. Occuper les quatre claires (le caster en est une) suffit
donc a ne laisser que du MASQUE : le natif refuse, et le port d'avant cette tranche acceptait.
Quatre unites au lieu des soixante d'un disque r=4 ordinaire.

⚠ AUCUN ENNEMI ADJACENT AU CASTER, ET C'EST DELIBERE (meme raison qu'en #287-r11-r2) : le masque de
1076 porte `forceMeleeTarget = RangedBool.IfRangedCaster`, donc un ennemi au contact ferait clamper
la portee a 1 par `ShouldApplyRangedInMelee` et la cible a d=2 serait refusee par `TargetIsInRange`
-- un AUTRE bit, qui masquerait la regle. Les trois bloqueurs sont des ALLIES, et le seul ennemi du
montage EST la cible.

⚠ L'ATTRIBUTION NE SE FAIT PAS PAR LE CODE RENDU (`ValidRequest` sert aussi ailleurs) MAIS PAR
DESARMEMENT, et le desarmement est CIBLE SUR CETTE TRANCHE : `--temoin` substitue
`_is_target_in_attack_range_for_summon` par le collapse d'avant (toute candidate de l'anneau est
valide). Un temoin qui ne perd rien serait un montage qui ne discrimine pas.

Usage (session warmee ; le probe monte et DISPOSE ses propres runners, un a la fois) :
    python scripts/python/probe_287r11r2r1_los_summon_live.py
    python scripts/python/probe_287r11r2r1_los_summon_live.py --only masque
ASCII only ; exit 0 = contrat respecte, les deux verdicts natifs exerces, aucune violation.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hexgeo                                                              # noqa: E402
import oracle_targeting as O                                               # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
import probe_287r11r1_regles_ciblage_live as R1                            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.runner.abilities.loki import mv71 as MV                        # noqa: E402
from engine.runner.abilities.targeting import (                            # noqa: E402
    _NormalAttackTargeting, is_invalid_target, normal_attack_targeting_options)
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.services.movement_query import get_tiles_obscuring_terrain     # noqa: E402
from engine.services.targeting_query import (                              # noqa: E402
    BLOCKING_ELEVATION_DIFFERENCE, OBSCURING_TYPE_ALL)

ROOT = HERE.parents[1]
LOGS = ROOT / "logs"

MV71 = int(ActiveAbilityType.MV71SniperDroneSquadAttack)       # 1076
CASTER = "tauMarksman"
DRONE = "tauSmnDroneSniper"
CIBLE = (0, 1)

# --------------------------------------------------------------------------------------------- #
# LES MONTAGES. `C3_47`, cible en (0,1) :
#     CLAIRES   (0,2) d=1 | (0,3) d=2 | (1,4) d=3 | (2,4) d=4
#     MASQUEES  (2,0) (2,1) (2,2) (2,3) (3,0) (3,1) (3,2) (4,1) (4,2) (4,3)   <- par (1,1)/(1,2)
#
# `masque`  : les QUATRE claires sont occupees (caster en (0,3)) -> il ne reste que du masque.
#             Natif : `PickTile` == null -> `1 ValidRequest`. Port d'avant : accepte -> SOUS-refus.
# `degage`  : le bloqueur de (1,4) part en (5,5), HORS du disque. MEME caster, MEME cible, MEME
#             distance : EXACTEMENT UNE tuile libre CLAIRE -> le natif accepte. C'est ce bras qui
#             etablit que le decideur est la LIGNE DE VUE et non le compte du disque (`masque` en
#             laisse DIX libres, et le natif refuse quand meme).
# `melee-candidate` : `degage` a UNE SEULE variable pres -- l'occupant de (2,4) change d'EQUIPE
#             (allie -> ennemi). MEMES tuiles occupees, MEME ensemble libre, MEME ligne de vue.
#             (2,4) est adjacente a la tuile libre claire (1,4) et a d=2 du caster (donc PAS au
#             contact du caster, sinon `TargetIsInRange` masquerait la regle) :
#             `ShouldApplyRangedInMelee(parent, [(1,4)], state, true)` devient VRAI -> la portee du
#             drone est rabattue a 1 -> `IsAdjacentTo((1,4), (0,1))` est FAUX (d=3) -> plus aucune
#             candidate, le natif rebascule sur `1 ValidRequest`. C'est l'etage
#             `ShouldApplyRangedInMelee DEPUIS LA TUILE CANDIDATE` qui le decide -- ni la ligne de
#             vue, ni le compte. Elevations (1,4)=2 / (2,4)=3, |dElev| = 1 < 2, donc
#             `CanMeleeAttackOverElevationDifference` laisse passer l'ennemi.
#             ⚠ (2,3), pourtant voisine HEX de (1,4), NE CONVIENT PAS : le `ConnectivityComponent`
#             LIVE de (1,4) ne porte que 5 aretes et cette arete-la n'y est pas -- mesure, pas
#             suppose (le natif rend `0x0` avec l'ennemi en (2,3), et le port aussi).
# --------------------------------------------------------------------------------------------- #

_ALLIES = "tauMarksman,ultraTitus,ultraTitus,ultraTitus"
_ALLIES3 = "tauMarksman,ultraTitus,ultraTitus"
_ENNEMIS = "necroWarden"
_ENNEMIS2 = "necroWarden,necroWarden"

MONTAGES = {
    "masque": dict(
        board="C3_47", seed=4747, cible=CIBLE, p_units=_ALLIES, a_units=_ENNEMIS,
        place=["tauMarksman:0,3", "ultraTitus:0,2", "ultraTitus:1,4", "ultraTitus:2,4"],
        a_place=["necroWarden:0,1"],
        libres_clairs=0, natif_attendu=0x1,
    ),
    "degage": dict(
        board="C3_47", seed=4747, cible=CIBLE, p_units=_ALLIES, a_units=_ENNEMIS,
        place=["tauMarksman:0,3", "ultraTitus:0,2", "ultraTitus:5,5", "ultraTitus:2,4"],
        a_place=["necroWarden:0,1"],
        libres_clairs=1, natif_attendu=0x0,
    ),
    "melee-candidate": dict(
        board="C3_47", seed=4747, cible=CIBLE, p_units=_ALLIES3, a_units=_ENNEMIS2,
        place=["tauMarksman:0,3", "ultraTitus:0,2", "ultraTitus:5,5"],
        a_place=["necroWarden:0,1", "necroWarden:2,4"],
        libres_clairs=1, natif_attendu=0x1,
    ),
}


@contextlib.contextmanager
def collapse_avant():
    """LE PORT D'AVANT #287-r11-r2-r1, substitue EN PLACE : `PickTile` ne testait que
    `1 <= d <= portee`, deja applique par l'anneau -- donc le troisieme filtre rendait `True` pour
    TOUTE candidate de l'anneau, et le maillon `UnobscuredTiles` du repli ne retirait rien.

    Substitution d'ATTRIBUT DE MODULE (forme B) : `_pick_tile` lit ces deux noms comme globales de
    `mv71`, donc le patch MORD (cf. `probe_485r1r1_formes_dimport`)."""
    # #287-r11-r2-r1-r3 : `_is_obscured_from_tiles` (collapse imperatif) est devenu
    # `_unobscured_tiles`, qui monte le NOEUD DSL `UnobscuredTiles`. Le nom substitue suit, sans quoi
    # ce contre-modele n'aurait plus AUCUNE morsure -- et un desarmement qui ne desarme rien rend un
    # VERT qui ne prouve rien (le vice exact que `probe_485r1r1_formes_dimport` garde).
    old_range = MV._is_target_in_attack_range_for_summon
    old_obsc = MV._unobscured_tiles
    MV._is_target_in_attack_range_for_summon = lambda *a, **k: True
    MV._unobscured_tiles = lambda *a, **k: False
    try:
        yield
    finally:
        MV._is_target_in_attack_range_for_summon = old_range
        MV._unobscured_tiles = old_obsc


def _geometrie(board, alive, cible_pos, rayon: int):
    """Les tuiles LIBRES du disque `rayon` de la cible, ventilees CLAIRES / MASQUEES -- calculees
    sur le board LIVE (`boardGraph`) et l'occupation LIVE, jamais sur le JSON versionne.

    C'est le CONTROLE DE MONTAGE : un `--place` non honore (residu #287-r13) est SILENCIEUX, et
    sans cette mesure le verdict porterait sur une geometrie qui n'est pas celle qu'on croit."""
    occ = {R1._pos(u) for u in alive}
    clairs, masques = [], []
    for q in hexgeo.disk(cible_pos[0], cible_pos[1], rayon):
        if q == cible_pos:
            continue
        tid = board.id_at(q[0], q[1])
        if tid is None or not board.walkable(tid) or q in occ:
            continue
        obsc = get_tiles_obscuring_terrain(board, q, cible_pos, OBSCURING_TYPE_ALL,
                                           BLOCKING_ELEVATION_DIFFERENCE)
        (masques if obsc else clairs).append(q)
    return sorted(clairs), sorted(masques)


def mesurer(rid: int, m: dict, ctx) -> dict:
    dec, ob, snap, board, alive, by_vis = ctx
    state = load_state(dec, ob, snap, board=board)
    out = {"lignes": [], "viol": [], "sous_refus": [], "exact": [], "natif": {},
           "cibles": 0, "absent": None, "court_circuite": None, "cible_cle": None}
    out["substrat"] = ["%s t%d %s team%s" % (u.get("visualId"), u["id"], R1._pos(u), u.get("team"))
                       for u in alive]
    clairs, masques = _geometrie(board, alive, tuple(m["cible"]),
                                 MV._drone_attack_range(DRONE))
    out["clairs"], out["masques"] = clairs, masques
    caster = by_vis.get(CASTER)
    if caster is None:
        out["absent"] = CASTER
        return out
    r0 = R1._rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                   "abilityType": MV71}, 60000) or {}
    if O.oracle_court_circuite(r0):
        out["court_circuite"] = O.cause_du_court_circuit(r0)
        return out
    porteurs = {
        "classe": P._porteur(MV71),
        "normale": _NormalAttackTargeting(
            normal_attack_targeting_options(state, int(caster["id"]))),
    }
    mine = caster.get("team")
    cp = R1._pos(caster)
    for u in alive:
        if u.get("id") == caster.get("id") or u.get("team") == mine:
            continue
        tid = int(u["id"])
        tp = R1._pos(u)
        r = R1._rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                      "abilityType": MV71, "targetId": tid}, 60000) or {}
        tr = r.get("targetReason") or {}
        nat = int(tr.get("hex") or "0x0", 16)
        ports = {k: int(is_invalid_target(state, int(caster["id"]), tid, ab) or 0)
                 for k, ab in porteurs.items()}
        libelle = "%s %s d=%s libres(clair=%d masque=%d)" % (
            u.get("visualId"), tp, hexgeo.distance(cp, tp) if (cp and tp) else "?",
            len(clairs), len(masques))
        out["natif"][hex(nat)] = out["natif"].get(hex(nat), 0) + 1
        out["cibles"] += 1
        ligne = (tid, libelle, hex(nat), ",".join(tr.get("reasons") or []) or "-",
                 {k: hex(v) for k, v in ports.items()})
        out["lignes"].append(ligne)
        if tp == tuple(m["cible"]):
            out["cible_cle"] = ligne
        for k, port in ports.items():
            if nat == 0 and port != 0:
                out["viol"].append((k,) + ligne)
            elif nat != 0 and port == nat:
                out["exact"].append((k,) + ligne)
            elif nat != 0 and port == 0:
                out["sous_refus"].append((k,) + ligne)
            elif nat != 0:
                out["viol"].append((k,) + ligne)
    return out


def jouer(nom: str, keep: bool):
    m = MONTAGES[nom]
    tag = uuid.uuid4().hex[:8]
    state_file = LOGS / f"rs_287r11r2r1_{nom}_{tag}.json"
    args = ["build", "--seed", str(m["seed"]), "--board", m["board"], "--rank", "17",
            "--p-units", m["p_units"], "--a-units", m["a_units"], "--no-ai",
            "--state-file", str(state_file)]
    for p in m.get("place") or []:
        args += ["--place", p]
    for p in m.get("a_place") or []:
        args += ["--a-place", p]
    sortie = R1._run(args)
    refus = [ln.strip() for ln in sortie.splitlines() if "placement REFUSE" in ln]
    if not state_file.exists():
        return None, {"echec": "build KO (state-file absent)\n      " + "\n      ".join(
            ln.strip() for ln in sortie.splitlines() if ln.startswith("[error]"))}, None
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    try:
        ctx = R1._contexte(rid)
        res = mesurer(rid, m, ctx)
        with collapse_avant():
            temoin = mesurer(rid, m, ctx)
    finally:
        if not keep:
            R1._run(["dispose", "--state-file", str(state_file)])
    if refus:
        res["refus_placement"] = refus
    return rid, res, temoin


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r11-r2-r1 : ligne de vue du gate de 1076, live")
    ap.add_argument("--only", default=None, help="ne jouer qu'un montage")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    noms = [n for n in MONTAGES if a.only is None or n == a.only]
    rc = 0
    natif_global: dict = {}
    for nom in noms:
        m = MONTAGES[nom]
        rid, res, temoin = jouer(nom, a.keep)
        print("")
        print("[287r11r2r1-live] %s -- ligne de vue d'IsTargetInAttackRangeForSummon -- porteur %s "
              "-- board %s -- runner %s" % (nom, CASTER, m["board"], rid))
        if rid is None:
            print("   PAS MESURE : %s" % res["echec"])
            rc = 2
            continue
        for ln in (res.get("refus_placement") or []):
            print("   !! PLACEMENT REFUSE (la geometrie voulue n'est PAS celle mesuree) : %s" % ln)
            rc = max(rc, 1)
        if res.get("absent"):
            print("   PAS MESURE : porteur `%s` ABSENT du montage" % res["absent"])
            rc = 2
            continue
        if res.get("court_circuite"):
            print("   PAS MESURE : oracle COURT-CIRCUITE (%s)" % res["court_circuite"])
            rc = 2
            continue
        print("   substrat monte : %s" % " | ".join(res.get("substrat") or ["<vide>"]))
        print("   disque r=%d de %s -- libres CLAIRES %s | libres MASQUEES %s"
              % (MV._drone_attack_range(DRONE), tuple(m["cible"]), res["clairs"], res["masques"]))
        # CONTROLE DE MONTAGE : la geometrie MESUREE doit etre celle qu'on a voulue.
        if len(res["clairs"]) != m["libres_clairs"]:
            print("   !! MONTAGE NON HONORE : %d tuile(s) libre(s) CLAIRE(S), %d attendue(s)"
                  % (len(res["clairs"]), m["libres_clairs"]))
            rc = max(rc, 2)
        if not res["masques"]:
            print("   !! TEMOIN NUL : aucune tuile libre MASQUEE -- la ligne de vue ne mord pas ici, "
                  "l'accord ne prouverait rien")
            rc = max(rc, 2)
        print("   cibles confrontees : %d | verdicts NATIFS : %s" % (res["cibles"], res["natif"]))
        if res["cibles"] == 0:
            print("   !! AUCUNE CIBLE : la mesure n'a pas eu lieu")
            rc = 2
        for k, v in res["natif"].items():
            natif_global[k] = natif_global.get(k, 0) + v
        for ligne in res["lignes"]:
            print("      t%-5d %-48s natif=%-8s [%s] port=%s"
                  % (ligne[0], ligne[1], ligne[2], ligne[3], ligne[4]))
        cle = res.get("cible_cle")
        if cle is None:
            print("   !! LA CIBLE CLE %s N'EST PAS DANS LE DOMAINE : montage non honore"
                  % (tuple(m["cible"]),))
            rc = max(rc, 2)
        else:
            # LA RE PREDIT LE VERDICT NATIF DE CE REGIME. Ce n'est pas le port qu'on juge ici : si
            # le natif dit autre chose, c'est la LECTURE du decompile qui est fausse, et ca doit
            # etre bruyant plutot que noye dans un accord port<->natif.
            attendu, obtenu = int(m["natif_attendu"]), int(cle[2], 16)
            if attendu != obtenu:
                print("   !! PREDICTION DE LA RE NON CONFIRMEE sur la cible cle : attendu %s, "
                      "natif %s" % (hex(attendu), hex(obtenu)))
                rc = max(rc, 1)
        temoin_exact = {(r[0], r[1]) for r in temoin["exact"]}
        attribuables = [r for r in res["exact"] if (r[0], r[1]) not in temoin_exact]
        print("   refus ATTRIBUABLES a la LIGNE DE VUE (perdus par le temoin) : %d"
              % len(attribuables))
        for r in attribuables:
            print("      LOS  porteur=%-8s t%-5d %-48s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        preexistantes = {(r[0], r[1]) for r in temoin["viol"]}
        imputables = [r for r in res["viol"] if (r[0], r[1]) not in preexistantes]
        print("   SUR-refus imputables a cette tranche : %d" % len(imputables))
        for r in imputables:
            print("      SUR  porteur=%-8s t%-5d %-48s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        print("   SOUS-refus (natif refuse, port accepte) : %d" % len(res["sous_refus"]))
        for r in res["sous_refus"]:
            print("      SOUS porteur=%-8s t%-5d %-48s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        print("   VUE ROUGE (temoin = le collapse d'avant) : %d SOUS-refus, %d refus reproduits"
              % (len(temoin["sous_refus"]), len(temoin["exact"])))
        for r in temoin["sous_refus"]:
            print("      ROUGE porteur=%-8s t%-5d %-48s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        if imputables or res["sous_refus"]:
            rc = 1
        # Tout montage dont le natif REFUSE doit DISCRIMINER : sous le collapse d'avant, le port
        # doit perdre ce refus. Sinon l'accord est obtenu par autre chose et ne dit rien de la
        # tranche.
        if int(m["natif_attendu"]) != 0 and (not attribuables or not temoin["sous_refus"]):
            print("   !! le montage ne DISCRIMINE pas : sous le collapse d'avant, le port rend le "
                  "meme verdict -- l'etage porte n'est pas ce qui decide")
            rc = max(rc, 1)
    print("")
    zero = sum(v for k, v in natif_global.items() if int(k, 16) == 0)
    refus = sum(v for k, v in natif_global.items() if int(k, 16) != 0)
    print("[287r11r2r1-live] NON-DEGENERESCENCE : natif=%s -> %s"
          % (natif_global,
             "les DEUX verdicts sont exerces" if (zero and refus)
             else "!! REGIME DEGENERE : un seul verdict, l'accord ne prouve rien"))
    if not (zero and refus):
        rc = max(rc, 1)
    print("[287r11r2r1-live] VERDICT : %s" % ("OK" if rc == 0 else "ROUGE (rc=%d)" % rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
