"""#910-r1 -- LE +PERCAGE D'EFFET ENTRE-T-IL DANS LA PREVISION QUE L'IA SCORE ?

## L'ecart, et pourquoi aucun replay-diff ne pouvait le voir

`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` n'a QUE des xrefs DATA :
c'est un service PARTAGE prediction+combat, et il somme les `EffectBonus` de percage
(`IdunBattle.Entities.Effects.BaseEffect$$PiercingBonusForAttack`) DANS son clamp unique. Le port,
lui, ne les faisait descendre que cote COMBAT -- la face DECISION passait `0`. Une attaque
s'EXECUTAIT donc correctement et se SCORAIT faux : ecart de DECISION pur, invisible de tout
replay-diff, et c'est ce qui l'a garde ouvert.

## L'ORACLE, et pourquoi il est NON CIRCULAIRE

`decisionView.attackPlans[].evals[].ranked[]` -- les bornes `dmgMin`/`dmgMax` que le NATIF publie
PAR TUILE CANDIDATE (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`). On les
apparie a `engine.playbook.prediction.make_normal_attack_predictions` appelee sur LA MEME tuile.
Fixture NOMMEE et partagee : `prediction_confrontation.py`.

## LE MONTAGE -- emprunte, pas recopie

`probe_910_relic_bolt_pistol_live.build(..., canal="PIERCE")` : `darkaHellblaster` equipe de
`RelicBoltPistol`, cible `astraBullgryn` dont les TRAITS sont ECRITS (`Xenos` = branche VRAIE du
`If`, donc `extraPierceRatio` x2). Deux reglages de ce montage sont des PARAMETRES DE REGIME, et
la fiche d'origine les a mesures :
  * `--crit 0,0` -- un coup CRITIQUE ne traverse pas l'armure de la meme facon, le percage n'y a
    plus d'observable ;
  * `--armor-target 6000` -- sans une armure qui ABSORBE toute la part non percee,
    `total = base*p + max(0, base*(1-p) - armure)` vaut `base - armure` quel que soit `p`.

## LE CONTREFACTUEL, et le piege de MORSURE qu'il fallait eviter

Bras `SANS_CANAL` = le port d'AVANT : `prediction_pierce_effect_bonus` rendue nulle. Elle est
importee en **FORME A** (`from ._shared import ...`) par `normal_attack`, donc substituer le seul
module SOURCE NE MORD PAS -- on substitue les DEUX liaisons et on les restaure toutes deux.

ASCII only. Usage :
  python probe_910r1_percage_face_decision_live.py [--seed 777] [--board MC1_67] [--trait Xenos]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

import prediction_confrontation as PC                     # noqa: E402
import probe_910_relic_bolt_pistol_live as P910           # noqa: E402
from rl_collect_batch import _resolve_session, _rpc       # noqa: E402


class _Args:
    """Le sous-ensemble de l'espace de noms d'arguments que `P910.build` lit."""

    def __init__(self, seed, board, armor, crit_damage):
        self.seed, self.board = seed, board
        self.armor, self.crit_damage = armor, crit_damage


def _ids(dec):
    out = {}
    for u in (dec.get("units") or []):
        vis = (u.get("visualId") or "")
        if vis.startswith(P910.CARRIER):
            out["att"] = int(u["id"])
        elif vis.startswith(P910.TARGET):
            out["tgt"] = int(u["id"])
    return out


def _confronte(rpc, rid, sans_canal: bool, ability_id):
    """Rend `(lignes, ecartes)` de la fixture, eventuellement avec le canal COUPE.

    ⚠ `ability_id` EST OBLIGATOIRE ICI, et ce n'est pas un confort : le port confronte sa
    prevision d'ATTAQUE NORMALE, tandis que `decisionView.attackPlans[].evals[]` publie une entree
    PAR ABILITY. Sans ce filtre, la meme tuile apparait plusieurs fois et le port se retrouve
    compare a l'oracle d'une AUTRE ability -- mesure : `(6,7)` rendu deux fois, oracle `(522,783)`
    pour l'attaque normale et `(2592,3888)` pour l'active. On compare deux grandeurs differentes,
    et l'ecart se lit comme un defaut de port."""
    import engine.playbook.prediction._shared as SH
    import engine.playbook.prediction.normal_attack as NA

    o_sh, o_na = SH.prediction_pierce_effect_bonus, NA.prediction_pierce_effect_bonus
    if sans_canal:
        def _zero(*a, **kw):
            return 0
        # FORME A des deux cotes -> substituer le seul module SOURCE NE MORD PAS.
        SH.prediction_pierce_effect_bonus = _zero
        NA.prediction_pierce_effect_bonus = _zero
    try:
        scene, sctx, dec = PC.construire_scene(rpc, rid)
        if scene is None:
            return None, None, dec
        ids = _ids(dec)
        if "att" not in ids or "tgt" not in ids:
            return None, None, dec
        lignes, ecartes = PC.lignes_de_confrontation(scene, sctx, dec, att_id=ids["att"],
                                                    tgt_id=ids["tgt"], ability_id=ability_id)
        return lignes, ecartes, dec
    finally:
        SH.prediction_pierce_effect_bonus = o_sh
        NA.prediction_pierce_effect_bonus = o_na


def run(seed: int, board: str, trait: str, level: int, armor: int) -> int:
    sid = _resolve_session()

    def rpc(method, body=None, timeout=60):
        return (_rpc(sid, method, [body if body is not None else {}],
                     timeout=timeout) or {}).get("result") or {}

    # ⚠ CANAL RELIQUE (#357/#363) : `load_state` ne tire `unitAbilityStates` que si un transport
    # AMBIANT est lie. Sans lui, `UnitContext.tertiary_ability` reste `None`, donc
    # `triggered_ability_state` retombe sur le couple PASSIF (niveau 50 = dernier palier) et la
    # magnitude confrontee ne serait PAS celle qu'on a equipee.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)

    a = _Args(seed, board, armor, P910.CRIT_DAMAGE)
    a.verbose = False
    rid, sf = P910.build(a, trait, "PIERCE", level)
    if rid is None:
        print("REFUS : build KO -- ce montage ne dit RIEN.")
        Path(sf).unlink(missing_ok=True)
        return 2
    rc = 0
    try:
        # POSITIONNEMENT : la fixture DEPLACE les unites a la distance du canal (melee = voisin
        # STOCKE de la cible) et verifie que la relique est MONTEE cote natif -- sans elle, le
        # `decisionView` ne publie AUCUN `attackPlan` (rien n'est a portee) et la confrontation
        # rendrait un accord DEGENERE.
        from engine.entities.pathfinding.board import Board
        from _charge_regime import ChargeRegimeHarness
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        try:
            rec = P910.stage(h, "PIERCE")
        except P910.MontageError as e:
            print("REFUS : %s" % e)
            return 2
        ab = rec["ability_type"]
        avec, ec_avec, _dec = _confronte(rpc, rid, False, ab)
        sans, ec_sans, _d2 = _confronte(rpc, rid, True, ab)
        print("== #910-r1 face DECISION : %s (relique %s niv.%d) -> %s [%s], armure %d, ability %s"
              % (P910.CARRIER, P910.ABILITY_ID, level, P910.TARGET, trait, armor, ab))
        if avec is None or sans is None:
            print("REFUS : la `Scene` ou les entites n'ont pas pu etre resolues.")
            return 2
        print("   AVEC canal : %s" % PC.resume(avec, ec_avec).replace("\n", "\n     "))
        print("   SANS canal : %s" % PC.resume(sans, ec_sans).replace("\n", "\n     "))
        if not avec:
            print("REFUS : AUCUNE ligne confrontee -- un accord en regime degenere ne prouve rien.")
            return 2
        d_avec, d_sans = PC.divergences(avec), PC.divergences(sans)
        if not d_sans:
            print("REFUS : le bras SANS canal CONCORDE deja -- ce montage n'exerce pas le canal "
                  "(porteur sans effet de percage ? armure trop faible ? cf. l'en-tete).")
            return 2
        if d_avec:
            print("!! LE PORT LIVRE DIVERGE sur %d ligne(s) : %s"
                  % (len(d_avec), [(l["tile"], l["oracle"], l["port"]) for l in d_avec[:4]]))
            rc |= 1
        print("DISCRIMINANT : SANS canal -> %d divergence(s), AVEC canal -> %d."
              % (len(d_sans), len(d_avec)))
        print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL rc=%d" % rc))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--trait", default="Xenos",
                    help="trait ECRIT sur la cible : `Xenos`/`Chaos` = branche VRAIE du `If` (x2)")
    ap.add_argument("--level", type=int, default=3)
    ap.add_argument("--armor", type=int, default=6000)
    a = ap.parse_args()
    return run(a.seed, a.board, a.trait, a.level, a.armor)


if __name__ == "__main__":
    raise SystemExit(main())

