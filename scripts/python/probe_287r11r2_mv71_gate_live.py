"""#287-r11-r2 -- CONFRONTATION LIVE de la regle dynamique de ciblage de `1076
MV71SniperDroneSquadAttack` (`tauMarksman`), contre l'oracle NATIF.

CE QUE CETTE TRANCHE A TROUVE, ET QUE LE MASQUE SEUL NE MONTRAIT PAS. `1076` EST l'attaque NORMALE
de `tauMarksman` : le porteur que la cascade du port consulte est donc
`targeting._NormalAttackTargeting`, qui appliquait a TOUS les types la regle de la BASE
(`ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason` = « une arme existe »). Or le natif lie
`options+0x38` au slot vtable `+0x480` de l'INSTANCE, et
`MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` SURCHARGE ce slot sans jamais
rappeler la base :

    if (!IsMeleeAttack(entities) && target != null && PickTile(entities, pickFirst: true) == null)
        return 1;                                  // = TargetingRule.ValidRequest
    return 0;

`tauMarksman` a des armes -> le port rendait `0` PARTOUT, y compris la ou le natif refuse faute de
tuile de spawn. Degradation PERMISSIVE, sans erreur ni crash.

L'ORACLE est `abilityReason(casterId, 1076, targetId)` = le masque `TargetingRule` rendu par
`TargetingQuery$$GetInvalidTargetReason`. Contrat de fidelite, identique a
`probe_287r11r1_regles_ciblage_live` :

    natif == 0   =>  port == 0          STRICT -- c'est CE bras qui attrape le SUR-REFUS
    natif != 0   =>  port == natif      (regle PORTEE)
                 ou  port == 0          (regle NON PORTEE -> permissif, documente)
    jamais       :   port != 0 et port != natif

DEUX PORTEURS SONT CONFRONTES AU MEME ORACLE, et c'est le point :
  * `classe`  = `ABILITY_CLASSES[1076]()` -- la voie de `turnflow.can_use_ability` ;
  * `normale` = `_NormalAttackTargeting(normal_attack_targeting_options(state, caster))` -- la voie
    de `valid_normal_attack_targets`, celle qui etait FAUSSE.
Mesurer un seul des deux aurait laisse l'autre en dette.

⚠ LA GEOMETRIE EST PLACEE, PAS SUBIE, ET LE BOARD EST CHOISI POUR ELLE. `GetUnitMaxRange
(tauSmnDroneSniper)` = **4** : saturer un disque r=4 demande 60 unites sur un board ordinaire.
`C1_t_01` (5x7, 25 tuiles marchables) porte un coin -- `(4,6)` -- dont le disque r=4 ne compte que
**8** tuiles marchables : huit occupants suffisent, et le caster en est un. Ce board a ete trouve
par balayage des 779 boards de `data/boards/`, pas suppose.

⚠ AUCUN ENNEMI ADJACENT AU CASTER, ET C'EST DELIBERE. Le masque de 1076 porte `forceMeleeTarget =
RangedBool.IfRangedCaster` : un ennemi au contact ferait clamper la portee a 1 par
`ShouldApplyRangedInMelee`, et la cible a d=2 serait refusee par `TargetIsInRange` -- un AUTRE bit,
qui masquerait la regle dynamique. Les quatre bloqueurs adjacents au caster sont donc des ALLIES.

Usage (session warmee ; le probe monte et DISPOSE ses propres runners, un a la fois) :
    python scripts/python/probe_287r11r2_mv71_gate_live.py
    python scripts/python/probe_287r11r2_mv71_gate_live.py --only sature
ASCII only ; exit 0 = contrat respecte, les deux verdicts natifs exerces, aucune violation.
"""
from __future__ import annotations

import argparse
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
from engine.runner.abilities.targeting import (                            # noqa: E402
    _NormalAttackTargeting, is_invalid_target, normal_attack_targeting_options)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

ROOT = HERE.parents[1]
LOGS = ROOT / "logs"

MV71 = int(ActiveAbilityType.MV71SniperDroneSquadAttack)       # 1076
CASTER = "tauMarksman"

# --------------------------------------------------------------------------------------------- #
# LES MONTAGES.
#
# `C1_t_01`, disque r=4 de la tuile (4,6) = EXACTEMENT huit tuiles marchables :
#     (0,4) (1,5) (1,6) (2,6) (3,3) (3,6) (4,3) (4,4)
# `sature` les occupe TOUTES -> `PickTile` ne trouve rien, le repli `HasTooManySummons` est inerte
# (aucun drone n'a encore ete pose) -> le natif rend `1 ValidRequest` sur la cible (4,6).
#
# `une-tuile` ne DEPLACE QU'UNE unite -- l'allie de (3,6) part en (2,2), hors du disque. MEME
# caster, MEME cible, MEME distance, MEME ligne de vue : le disque passe de 0 a EXACTEMENT UNE
# tuile libre et le verdict doit basculer. C'est ce qui etablit que le decideur est le COMPTE du
# disque, et non la distance ni la position.
#
# (3,6) est la tuile liberee, et le choix n'est pas indifferent : elle est ADJACENTE a la cible,
# donc le volet LIGNE DE VUE d'`IsTargetInAttackRangeForSummon` (que le port COLLAPSE en
# `1 <= d <= range`) n'a aucune tuile intermediaire a examiner. Liberer une tuile lointaine aurait
# expose le collapse et melange deux causes.
# --------------------------------------------------------------------------------------------- #

_ALLIES = "tauMarksman,ultraTitus,ultraTitus"
_ENNEMIS = "necroWarden,necroWarden,necroWarden,necroWarden,necroWarden,necroDestroyer"

MONTAGES = {
    "sature": dict(
        board="MC1_01", seed=4242, cible=(4, 6),
        p_units=_ALLIES, a_units=_ENNEMIS,
        place=["tauMarksman:2,6", "ultraTitus:1,6", "ultraTitus:3,6"],
        a_place=["necroWarden:4,6", "necroWarden:4,4", "necroWarden:3,3",
                 "necroWarden:1,5", "necroWarden:0,4", "necroDestroyer:4,3"],
    ),
    "une-tuile": dict(
        board="MC1_01", seed=4242, cible=(4, 6),
        p_units=_ALLIES, a_units=_ENNEMIS,
        place=["tauMarksman:2,6", "ultraTitus:1,6", "ultraTitus:2,2"],
        a_place=["necroWarden:4,6", "necroWarden:4,4", "necroWarden:3,3",
                 "necroWarden:1,5", "necroWarden:0,4", "necroDestroyer:4,3"],
    ),
}


def _libres_du_disque(board, alive, cible_pos, rayon: int) -> list:
    """INDICE geometrique : les tuiles MARCHABLES du disque `rayon` de la cible qu'aucune unite
    n'occupe. C'est le substrat que `PickTile` enumere -- imprime pour que le verdict soit lisible,
    jamais utilise comme verdict attendu (ce serait circulaire)."""
    occ = {R1._pos(u) for u in alive}
    out = []
    for q in hexgeo.disk(cible_pos[0], cible_pos[1], rayon):
        if q == cible_pos:
            continue
        tid = board.id_at(q[0], q[1])
        if tid is None or not board.walkable(tid) or q in occ:
            continue
        out.append(q)
    return sorted(out)


def mesurer(rid: int, m: dict, ctx) -> dict:
    dec, ob, snap, board, alive, by_vis = ctx
    state = load_state(dec, ob, snap, board=board)
    out = {"lignes": [], "viol": [], "sous_refus": [], "exact": [], "natif": {},
           "cibles": 0, "absent": None, "court_circuite": None, "cible_cle": None}
    out["substrat"] = ["%s t%d %s team%s" % (u.get("visualId"), u["id"], R1._pos(u), u.get("team"))
                       for u in alive]
    caster = by_vis.get(CASTER)
    if caster is None:
        out["absent"] = CASTER
        return out
    r0 = O and R1._rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
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
        libres = _libres_du_disque(board, alive, tp, 4) if tp else []
        libelle = "%s %s d=%s libresR4=%d" % (
            u.get("visualId"), tp,
            hexgeo.distance(cp, tp) if (cp and tp) else "?", len(libres))
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
    state_file = LOGS / f"rs_287r11r2_{nom}_{tag}.json"
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
        with P.desarme(MV71):
            temoin = mesurer(rid, m, ctx)
    finally:
        if not keep:
            R1._run(["dispose", "--state-file", str(state_file)])
    if refus:
        res["refus_placement"] = refus
    return rid, res, temoin


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r11-r2 : gate dynamique de 1076, live")
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
        print("[287r11r2-live] %s -- 1076 MV71SniperDroneSquadAttack -- porteur %s -- board %s "
              "-- runner %s" % (nom, CASTER, m["board"], rid))
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
        print("   cibles confrontees : %d | verdicts NATIFS : %s" % (res["cibles"], res["natif"]))
        if res["cibles"] == 0:
            print("   !! AUCUNE CIBLE : la mesure n'a pas eu lieu")
            rc = 2
        for k, v in res["natif"].items():
            natif_global[k] = natif_global.get(k, 0) + v
        for ligne in res["lignes"]:
            print("      t%-5d %-40s natif=%-8s [%s] port=%s"
                  % (ligne[0], ligne[1], ligne[2], ligne[3], ligne[4]))
        cle = res.get("cible_cle")
        if cle is None:
            print("   !! LA CIBLE CLE %s N'EST PAS DANS LE DOMAINE : montage non honore"
                  % (tuple(m["cible"]),))
            rc = max(rc, 2)
        # ATTRIBUTION PAR DESARMEMENT, et pas par le CODE rendu. `1076` rend `ValidRequest`, que le
        # filtre statique emploie AUSSI (tete de domaine TUILE) : trier sur le code confondrait deux
        # origines. Le discriminant est « le TEMOIN perd-il ce refus ? ».
        temoin_exact = {(r[0], r[1]) for r in temoin["exact"]}
        attribuables = [r for r in res["exact"] if (r[0], r[1]) not in temoin_exact]
        hors_regle = [r for r in res["exact"] if (r[0], r[1]) in temoin_exact]
        print("   refus ATTRIBUABLES a la regle (perdus par le temoin) : %d" % len(attribuables))
        for r in attribuables:
            print("      REGLE porteur=%-8s t%-5d %-40s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        print("   refus HORS regle (autre bit, survivent au desarmement) : %d" % len(hors_regle))
        preexistantes = {(r[0], r[1]) for r in temoin["viol"]}
        imputables = [r for r in res["viol"] if (r[0], r[1]) not in preexistantes]
        print("   SUR-refus imputables a cette tranche : %d" % len(imputables))
        for r in imputables:
            print("      SUR  porteur=%-8s t%-5d %-40s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        print("   SOUS-refus (natif refuse, port accepte) : %d" % len(res["sous_refus"]))
        for r in res["sous_refus"]:
            print("      SOUS porteur=%-8s t%-5d %-40s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        # LA VUE ROUGE, mesuree SUR PLACE : desarme, le port DOIT manquer les refus attribues a la
        # regle. Un temoin qui ne perd rien est un montage qui ne discrimine pas.
        print("   VUE ROUGE (temoin desarme) : %d SOUS-refus, %d refus encore reproduits"
              % (len(temoin["sous_refus"]), len(temoin["exact"])))
        for r in temoin["sous_refus"]:
            print("      ROUGE porteur=%-8s t%-5d %-40s natif=%-8s port=%s"
                  % (r[0], r[1], r[2], r[3], r[5]))
        if imputables or res["sous_refus"]:
            rc = 1
        if nom == "sature" and (not attribuables or not temoin["sous_refus"]):
            print("   !! le montage ne DISCRIMINE pas : desarme, le port rend le meme verdict")
            rc = max(rc, 1)
    print("")
    zero = sum(v for k, v in natif_global.items() if int(k, 16) == 0)
    refus = sum(v for k, v in natif_global.items() if int(k, 16) != 0)
    dyn = sum(v for k, v in natif_global.items()
              if int(k, 16) and (int(k, 16) & int(TR.ValidRequest)))
    print("[287r11r2-live] NON-DEGENERESCENCE : natif=%s -> %s"
          % (natif_global,
             "les DEUX verdicts sont exerces" if (zero and refus)
             else "!! REGIME DEGENERE : un seul verdict, l'accord ne prouve rien"))
    print("[287r11r2-live] refus portant `ValidRequest` (le code de CETTE regle) : %d" % dyn)
    if not (zero and refus):
        rc = max(rc, 1)
    print("[287r11r2-live] VERDICT : %s" % ("OK" if rc == 0 else "ROUGE (rc=%d)" % rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
