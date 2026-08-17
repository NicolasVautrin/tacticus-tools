"""#10019 -- DECOMPOSITION PAR ETAGE du nombre de COUPS de la face PREDICTION.

Contexte. La fiche `#10019` accuse la face PREDICTION d'appeler
`IdunBattle.Core.Services.DamagePrediction$$GetDefaultAttackHits` (base seule) la ou le natif
appelle sa soeur `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` (base + modificateurs).
Sur le vecteur ATTAQUE NORMALE cette accusation est FAUSSE : `playbook/prediction/normal_attack.py`
traverse DEJA la formule complete (`engine/services/attack_hits_formula.py::
attack_hits_with_modifiers`, mirror du corps de `GetAttackHits`) avec un jumeau de `board` /
`aura_sources` / `target_effects` bati depuis la `Scene`. Les trois divergences mesurees
(seed 777, board `MC1_67`, pas 6/8/9, `ability 69` = attaque normale, cible 93) sont donc un ecart
DANS cette formule, pas une absence de formule.

Ce probe est le DISCRIMINANT : il rejoue le walk d'agreement et intercepte CHAQUE appel de la
formule cote prediction pour en imprimer les SIX etages separement --

    base_default = `GetDefaultAttackHits` (weapon + ExtraHits(0x11) [+ ExtraHitsMelee(0x17)])
    eff_hits     = bonus/malus d'effets de l'ATTAQUANT   (`hits_bonus_from_effects`)
    bonus_hits   = GetStuckIn / traits                    (`attacker_bonus_hits`)
    aura_bonus   = auras de coups cote ATTAQUE            (`aura_hits_bonus_for_attack`)
    malus_def    = effets de la CIBLE                     (`hits_malus_from_defender_effects`)
    aura_malus   = auras de coups cote DEFENSE            (`aura_hits_malus_for_defense`)

-- de sorte qu'une divergence de COMPTE se lise sur l'etage qui la porte, jamais sur un scalaire
ajuste. Le rapport `(h+1)/h` observe sur les six nombres natifs dit que l'ecart vaut EXACTEMENT
un coup : l'etage coupable est celui dont le port rend 0 la ou le natif rend 1.

TEMOIN NEGATIF OBLIGATOIRE : `u83` attaque la MEME cible 93 avec la MEME `ability 69` au pas 5 et
CONCORDE. Tout diagnostic qui expliquerait aussi `u83` est FAUX. Le probe imprime donc les quatre
unites ensemble, jamais les trois divergentes seules -- un accord en regime degenere ne prouve rien.

Usage (depuis `scripts/python`) :

    python probe_10019_prediction_hits.py --seed 777 --steps 12 \
        --state-file <ABSOLU propre>

Discipline runner : `--state-file` ABSOLU et propre, board `MC1_67` impose (le montage de la fiche),
runner dispose en fin de run. Session Frida deja warmee (ce probe ne (re)injecte JAMAIS).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine_agreement_stages as EAS  # noqa: E402  (SOURCE UNIQUE du walk d'agreement)
from engine.playbook.prediction import normal_attack as NA  # noqa: E402
from engine.services import attack_hits_formula as AHF  # noqa: E402
from engine.entities.effects import (hits_bonus_from_effects,  # noqa: E402
                                     hits_malus_from_defender_effects,
                                     aura_hits_malus_for_defense, aura_hits_bonus_for_attack,
                                     block_hits_reduction_from_effects, board_effect_carriers)
from engine.entities.traits import attacker_bonus_hits  # noqa: E402
from engine.services.damage_prediction import get_default_attack_hits  # noqa: E402
import hexgeo  # noqa: E402

# Les quatre unites du montage de la fiche : trois DIVERGENTES et le TEMOIN NEGATIF.
# `u83` doit rester dans toute sortie -- c'est lui qui invalide un diagnostic trop large.
UNITES_DIVERGENTES = (85, 79, 77)
UNITE_TEMOIN = 83
CIBLE = 93


def _decompose(kw: dict) -> dict:
    """Rejoue `attack_hits_with_modifiers` etage par etage, sans rien recalculer autrement.

    Mirror STRUCTUREL du corps de `engine/services/attack_hits_formula.py` : chaque ligne ci-dessous
    correspond a un appel de ce corps, dans le MEME ordre et avec les MEMES arguments. Toute
    divergence entre `total` et le retour reel de la formule est un bug DE CE PROBE, et il est
    assertionne (`coherent`) -- un decompositeur qui derive de sa cible mesure autre chose qu'elle.
    """
    board = dict(kw.get("board") or {})
    weapon_hits = int(kw["weapon_hits"])
    is_melee = kw.get("is_melee")
    damage_profile = kw.get("damage_profile")
    is_normal_attack = bool(kw.get("is_normal_attack", True))
    attacker_effects = kw.get("attacker_effects")
    target_effects = kw.get("target_effects")
    aura_sources = kw.get("aura_sources")

    block_reduction = block_hits_reduction_from_effects(
        board_effect_carriers(board.get("att_id"), attacker_effects,
                              board.get("tgt_id"), target_effects, aura_sources), dict(board))
    eff_hits = hits_bonus_from_effects(attacker_effects, is_normal_attack, att_ctx=dict(board),
                                       block_reduction=block_reduction)
    base_default = get_default_attack_hits(weapon_hits, int(kw["extra_hits"]),
                                           int(kw["extra_hits_melee"]), bool(is_melee))
    floor = min(1, base_default)
    hits_pre = max(floor, base_default + eff_hits)
    board2 = {**board, "base_hits": hits_pre,
              "hit_group_index": kw.get("hit_group_index", 0),
              "is_normal_attack": is_normal_attack}
    bonus_hits = (attacker_bonus_hits(kw.get("trait_objects"), board2)
                  if kw.get("include_bonus_hit_behaviours") else 0)
    aura_bonus = aura_hits_bonus_for_attack(aura_sources, {
        **board2,
        "att_id": board2.get("att_id"), "att_pos": board2.get("attack_pos"),
        "att_team": (board2.get("team_by_id") or {}).get(board2.get("att_id")),
        "att_faction": board2.get("att_faction"),
        "is_melee": is_melee, "damage_profile": damage_profile,
        "turns_started_by_id": board2.get("turns_started_by_id"),
        "parent_by_id": board2.get("parent_by_id"),
        "rng": board2.get("rng")}, block_reduction=block_reduction)
    ap, tp = board2.get("attack_pos"), board2.get("t_pos")
    dist = (hexgeo.distance(tuple(ap), tuple(tp)) if (ap is not None and tp is not None) else None)
    malus_def = hits_malus_from_defender_effects(
        target_effects, is_melee, damage_profile,
        defender_on_cover=kw.get("defender_on_cover"), dist=dist,
        block_reduction=block_reduction, is_normal_attack=is_normal_attack, att_ctx=board2)
    aura_malus = aura_hits_malus_for_defense(aura_sources, board2, block_reduction=block_reduction)
    total = max(floor, hits_pre + bonus_hits + aura_bonus + malus_def + aura_malus)
    return {"weapon_hits": weapon_hits, "extra_hits": int(kw["extra_hits"]),
            "extra_hits_melee": int(kw["extra_hits_melee"]), "is_melee": is_melee,
            "base_default": base_default, "eff_hits": eff_hits, "hits_pre": hits_pre,
            "bonus_hits": bonus_hits, "aura_bonus": aura_bonus, "malus_def": malus_def,
            "aura_malus": aura_malus, "block_reduction": block_reduction, "dist": dist,
            "total": total}


class _Traceur:
    """Substitue le nom `attack_hits_with_modifiers` LIE dans `normal_attack` (forme B obligatoire).

    `playbook/prediction/normal_attack.py` importe la formule en FORME A
    (`from engine.services.attack_hits_formula import attack_hits_with_modifiers`), donc patcher
    `engine.services.attack_hits_formula.attack_hits_with_modifiers` NE MORD PAS -- le nom est deja
    lie. C'est exactement le mode de panne mesure de `#484` / `#485-r1-r1`. On substitue donc
    l'attribut du module CONSOMMATEUR, et on VERIFIE que la substitution a mordu (`self.appels`
    non vide en fin de run) plutot que de le supposer.
    """

    def __init__(self):
        self.appels: list = []
        self._orig = None

    def __enter__(self):
        self._orig = NA.attack_hits_with_modifiers

        def _trace(**kw):
            out = self._orig(**kw)
            b = kw.get("board") or {}
            rec = {"att_id": b.get("att_id"), "tgt_id": b.get("tgt_id"),
                   "attack_pos": b.get("attack_pos"), "t_pos": b.get("t_pos"),
                   "hits": out}
            try:
                rec["etages"] = _decompose(kw)
                rec["coherent"] = (rec["etages"]["total"] == out)
            except Exception as exc:                       # pragma: no cover - diagnostic
                rec["etages"] = None
                rec["coherent"] = None
                rec["erreur_decomposition"] = repr(exc)
            self.appels.append(rec)
            return out

        NA.attack_hits_with_modifiers = _trace
        return self

    def __exit__(self, *exc):
        NA.attack_hits_with_modifiers = self._orig
        return False


def _resume(appels: list, uids) -> None:
    """Imprime la decomposition par unite, TEMOIN COMPRIS (ASCII strict)."""
    print()
    print("=== ETAGES DU COMPTE DE COUPS (prediction, attaque normale) ===")
    print("   att -> tgt   tuile     base eff pre stuck auraB malusD auraM = hits")
    for rec in appels:
        if uids and rec.get("att_id") not in uids:
            continue
        e = rec.get("etages")
        if e is None:
            print("   {} -> {}   DECOMPOSITION KO : {}".format(
                rec.get("att_id"), rec.get("tgt_id"), rec.get("erreur_decomposition")))
            continue
        marque = "" if rec.get("coherent") else "  <<< DECOMPOSITION INCOHERENTE"
        print("   u{:<3} -> {:<3}  {!s:<9} {:>4} {:>3} {:>3} {:>5} {:>5} {:>6} {:>5} = {}{}".format(
            rec.get("att_id"), rec.get("tgt_id"), rec.get("attack_pos"),
            e["base_default"], e["eff_hits"], e["hits_pre"], e["bonus_hits"],
            e["aura_bonus"], e["malus_def"], e["aura_malus"], rec["hits"], marque))
        print("        weapon={} extra={} extraMelee={} is_melee={} dist={} block_red={}".format(
            e["weapon_hits"], e["extra_hits"], e["extra_hits_melee"], e["is_melee"],
            e["dist"], e["block_reduction"]))


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=str, default="777")
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--state-file", type=str, default=None)
    ap.add_argument("--board", type=str, default="MC1_67")
    ap.add_argument("--json", type=str, default=None)
    ap.add_argument("--uids", type=str, default="",
                    help="filtre d'unites (defaut : les 3 divergentes + le TEMOIN u83)")
    args = ap.parse_args(argv)

    uids = ({int(x) for x in args.uids.split(",") if x.strip()} if args.uids
            else set(UNITES_DIVERGENTES) | {UNITE_TEMOIN})

    sid = EAS._resolve_session()
    if sid is None:
        print("[10019] aucune session Frida -- ABANDON (ce probe ne (re)injecte JAMAIS)")
        return 2
    if args.state_file:
        EAS.STATE = Path(args.state_file)
    wt = EAS.weights.load()
    extra = ["--board", args.board]
    rid = EAS._build_runner(args.seed, extra)
    if rid is None:
        print("[10019] build runner KO")
        return 2
    print("[10019] seed={} runner={} steps={} board={}".format(args.seed, rid, args.steps, args.board))
    try:
        with _Traceur() as tr:
            out = EAS.run_stages(sid, rid, args.steps, wt)
    finally:
        EAS._r(sid, "disposeRunner", {"runnerId": rid}, 20)

    # LA SUBSTITUTION A-T-ELLE MORDU ? Un traceur muet rendrait un rapport VIDE qui se lirait
    # comme << aucune anomalie >>. On le dit, on ne le suppose pas (cf. l'angle mort forme A/B).
    if not tr.appels:
        print("[10019] AUCUN appel intercepte -- la substitution N'A PAS MORDU (ou aucune attaque "
              "normale predite sur ces pas). Rien n'est conclu.")
        return 3
    print("[10019] appels de formule interceptes : {}".format(len(tr.appels)))
    _resume(tr.appels, uids)

    incoherents = [r for r in tr.appels if r.get("coherent") is False]
    if incoherents:
        print("[10019] {} decomposition(s) INCOHERENTE(S) avec la formule -- le probe derive de sa "
              "cible, ses etages ne prouvent rien".format(len(incoherents)))

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"seed": args.seed, "appels": tr.appels,
             "agreement": out.get("agreement")}, indent=1, default=str), encoding="utf-8")
        print("[10019] dump JSON -> {}".format(args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
