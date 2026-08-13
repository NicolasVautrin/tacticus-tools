"""#1024 -- `OnMyPosition` (mythique de `astraOrdnanceBattery`) : l'AURA et le BONUS, mesures.

Comme son jumeau `probe_1024_shield_of_faith_live.py`, ce probe n'a pas de port a valider : il
etablit le GROUND TRUTH des deux etages que le decompile ecrit.

  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OnMyPositionAbility` derive
  d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` et ne surcharge QUE
  `GetEffectType` -> `0x5a4` = `EffectType.OnMyPosition_ExtraDamagePct` (1444). L'ability se pose
  donc elle-meme sur son OWNER a `OnOwnerSpecificAbilityInit`, sans trigger propre.

  `IdunBattle.Entities.Effects.Loki.OnMyPosition_ExtraDamagePctEffect$$CreateTargetSelector` (AURA)
      Enemies(of = Owner,
              AdjacentUnits(   Friends(Owner, UnitsWithVisualId(
                                   VisualUnitIdFromUnitId(GetStringConstant(unitId)), 1))
                             + UnitsWithRarity(Friends(Owner, HeroUnits(...)), Mythic, 3),
                            unique = true, 3),
              3)

  `...OnMyPosition_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack`
      EffectBonus.ForPercentIncrease(
          OwnerIsTarget & AreFriends(Caster, EffectSource) & HasRarity(Caster, Mythic)
                        & IsRangedAttack,
          ConfigVar(0xa = extraDmgPct))

DEUX SEPARATIONS, et elles sont de natures DIFFERENTES -- c'est voulu :

  * GEOMETRIQUE, dans le MEME build : l'ennemi ADJACENT a un ami mythique porte l'effet,
    l'ennemi ELOIGNE ne le porte pas. Un montage ou les deux le porteraient (ou aucun) ne
    mesurerait pas l'aura ; le probe le REFUSE au lieu de conclure.
  * PAR BRAS : `--bras sans-mythique` rejoue le meme build sans `--equip-mythic`. AUCUN
    effet 1444 ne doit apparaitre, et la prediction de degat doit RETOMBER a la valeur de base.

Usage :
  python probe_1024_on_my_position_live.py --bras mythique --level 4
  python probe_1024_on_my_position_live.py --bras sans-mythique
Sortie ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import rl_duel as R  # noqa: E402

PORTEUR = "astraOrdnanceBattery"
ABILITY = "OnMyPosition"
EFFECT_TYPE = 1444                      # `EffectType.OnMyPosition_ExtraDamagePct` = 0x5a4
P_UNITS = "adeptRetributor,adeptCanoness,adeptHospitaller"
A_UNITS = "tyranTyrantGuard,tyranParasite"
ATTAQUANT_VIS = "adeptRetributor"       # ranged r2 -- exige le gate `IsRangedAttack`
ANCRE_VIS = "adeptCanoness"             # 2e ami adjacent : l'aure TIENT meme si l'attaquant bouge
#: TEMOIN du gate `IsRangedAttack` : `adeptHospitaller` n'a QU'UNE arme, `Range = null` -- donc
#: melee au sens d'`IdunBattle.Entities.WeaponProfile$$get_IsMelee` (seuil `Range >= 2`). Sa
#: prediction sur la MEME cible affectee ne doit PAS bouger entre les deux bras.
MELEE_VIS = "adeptHospitaller"
CIBLE_PROCHE_VIS = "tyranTyrantGuard"   # adjacent aux deux amis -> DOIT porter 1444
CIBLE_LOIN_VIS = "tyranParasite"        # a distance >= 2 de tout ami -> ne DOIT PAS le porter
BOARD = "MC1_67"                        # 7x9, entierement Grass : toute tuile est posable
POS_ATTAQUANT = (3, 4)
POS_CIBLE_PROCHE = (3, 5)
POS_ANCRE = (2, 5)
POS_MELEE = (4, 5)                      # 3e voisin hex de POS_CIBLE_PROCHE
POS_CIBLE_LOIN = (6, 8)


def _unwrap(x):
    return x["result"] if isinstance(x, dict) and "result" in x else x


def _lignes(dv: dict):
    """Les entites porteuses d'effets : `decisionView.units` ET `decisionView.mows`.

    ⚠ Une MoW n'est PAS dans `units` -- et c'est precisement elle qui PORTE l'effet d'aura ici."""
    return list(dv.get("units") or []) + list(dv.get("mows") or [])


def _effets(dv: dict) -> dict:
    """{entityId: [effet, ...]} -- l'entree BRUTE, `targetIds` compris.

    ⚠ UNE AURE NE SE LIT PAS SUR SA CIBLE. `decisionView` publie l'entite-EFFET une seule fois,
    portee par sa SOURCE, et c'est son champ `targetIds` qui enumere les unites affectees --
    l'ennemi adjacent, lui, ne montre RIEN dans sa propre liste (mesure #1024, premiere version de
    ce probe : elle concluait << aure muette >> alors que la prediction de degat portait deja
    +20 %). Meme angle mort que celui documente par `feedback_aura_unexplained_stat_delta`."""
    out = {}
    for u in _lignes(dv):
        out[u.get("id")] = list(u.get("effects") or [])
    return out


def _cibles_de_l_aure(dv: dict, effect_type: int) -> set:
    """Union des `targetIds` de toutes les entrees d'effet du type demande."""
    hit = set()
    for u in _lignes(dv):
        for e in (u.get("effects") or []):
            if e.get("effectType") == effect_type:
                hit.update(e.get("targetIds") or [])
    return hit


def _plans_par_tuile(dv: dict, caster: int, target: int, ability_id: int) -> dict:
    """{(col,row): (minDmg, maxDmg)} pour un triplet (caster, cible, ability) donne.

    Source : `decisionView.attackPlans[].evals[].ranked[]` -- la prediction NATIVE par tuile de
    depart. On la prend PAR TUILE (et non le meilleur) pour que la comparaison entre bras porte
    sur des points identiques."""
    out = {}
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") != caster:
            continue
        for ev in (p.get("evals") or []):
            if ev.get("targetId") != target or ev.get("abilityId") != ability_id:
                continue
            for r in (ev.get("ranked") or []):
                out[(r.get("col"), r.get("row"))] = (r.get("dmgMin"), r.get("dmgMax"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#1024 -- OnMyPosition, ground truth live")
    ap.add_argument("--bras", choices=["mythique", "sans-mythique"], default="mythique")
    ap.add_argument("--level", type=int, default=4)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    # La geometrie est PILOTEE : on l'assertionne plutot que de la subir.
    assert hexgeo.distance(POS_ATTAQUANT, POS_CIBLE_PROCHE) == 1
    assert hexgeo.distance(POS_ANCRE, POS_CIBLE_PROCHE) == 1
    assert hexgeo.distance(POS_MELEE, POS_CIBLE_PROCHE) == 1
    assert min(hexgeo.distance(p, POS_CIBLE_LOIN)
               for p in (POS_ATTAQUANT, POS_ANCRE, POS_MELEE)) >= 2

    import catalog_inject  # noqa: E402
    import gameconfig  # noqa: E402

    cfg = gameconfig.ability(ABILITY) or {}
    paliers = (cfg.get("variables") or {}).get("extraDmgPct") or []
    consts = cfg.get("constants") or {}
    attendu_pct = paliers[a.level - 1] if 1 <= a.level <= len(paliers) else None
    print("=== ETAGE 0 : ce que le gameconfig dit ===")
    print("  ability     = %s (TriggeredAbilityType=%d) -> EffectType %d"
          % (ABILITY, catalog_inject.triggered_ability_id(ABILITY), EFFECT_TYPE))
    print("  extraDmgPct = %s (rarity-flag: %s)"
          % (paliers, cfg.get("variablesAffectedByRarityBonus")))
    print("  constants   = %s ; visualId(unitId) = %s"
          % (consts, (gameconfig.unit(consts.get("unitId")) or {}).get("visualId")
             if consts.get("unitId") else None))
    print("  bras = %s ; niveau %d -> extraDmgPct attendu = %s"
          % (a.bras, a.level, attendu_pct))

    sf = a.state_file or str(Path(__file__).resolve().parents[2] / "logs"
                             / ("probe1024_omp_%s_l%d.json" % (a.bras, a.level)))
    argv = ["build", "--seed", str(a.seed), "--board", a.board,
            "--p-units", P_UNITS, "--a-units", A_UNITS,
            "--p-mow", PORTEUR,
            "--place", "%s:%d,%d" % (ATTAQUANT_VIS, POS_ATTAQUANT[0], POS_ATTAQUANT[1]),
            "--place", "%s:%d,%d" % (ANCRE_VIS, POS_ANCRE[0], POS_ANCRE[1]),
            "--place", "%s:%d,%d" % (MELEE_VIS, POS_MELEE[0], POS_MELEE[1]),
            "--a-place", "%s:%d,%d" % (CIBLE_PROCHE_VIS, POS_CIBLE_PROCHE[0], POS_CIBLE_PROCHE[1]),
            "--a-place", "%s:%d,%d" % (CIBLE_LOIN_VIS, POS_CIBLE_LOIN[0], POS_CIBLE_LOIN[1]),
            "--state-file", sf]
    if a.bras != "sans-mythique":
        argv[-2:-2] = ["--equip-mythic", "%s:%s:%d" % (PORTEUR, ABILITY, a.level)]

    print()
    print("=== ETAGE 1 : build ===")
    if R.main(argv) != 0:
        print("  BUILD ECHOUE -- rien n'est conclu")
        return 2
    st = json.loads(Path(sf).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    print("  runnerId=%s  equip-mythic=%s" % (rid, a.bras != "sans-mythique"))

    import rl_collect_batch as B  # noqa: E402
    sid = B._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(B._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    try:
        dv = rpc("decisionView", {"runnerId": rid}, 120) or {}
        ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}
        att = ids.get(ATTAQUANT_VIS)
        proche, loin = ids.get(CIBLE_PROCHE_VIS), ids.get(CIBLE_LOIN_VIS)
        if att is None or proche is None or loin is None:
            print("  MONTAGE INCOMPLET %s -- rien n'est conclu" % (ids,))
            return 2
        eff = _effets(dv)
        print()
        print("=== ETAGE 2 : l'AURA -- qui porte l'effet %d, et qui VISE-T-IL ? ===" % EFFECT_TYPE)
        for u in _lignes(dv):
            print("  u%-4s %-22s pos=%s effets=%s"
                  % (u.get("id"), u.get("visualId"), u.get("pos"),
                     [(e.get("effectType"), e.get("name"), e.get("targetIds"))
                      for e in eff.get(u.get("id")) or []]))
        vises = _cibles_de_l_aure(dv, EFFECT_TYPE)
        a_proche, a_loin = proche in vises, loin in vises
        print("  targetIds de l'effet %d : %s" % (EFFECT_TYPE, sorted(vises)))
        print("  cible PROCHE u%s (%s) visee ? %s" % (proche, POS_CIBLE_PROCHE, a_proche))
        print("  cible LOIN   u%s (%s) visee ? %s" % (loin, POS_CIBLE_LOIN, a_loin))

        namap = R._normal_ability_map(dv)
        melee = ids.get(MELEE_VIS)
        na, na_m = namap.get(att), namap.get(melee)
        plans = _plans_par_tuile(dv, att, proche, na) if na is not None else {}
        plans_m = _plans_par_tuile(dv, melee, proche, na_m) if na_m is not None else {}
        print()
        print("=== ETAGE 3 : prediction NATIVE sur la cible AFFECTEE u%s, par tuile ===" % proche)
        print("  -- attaquant DISTANCE u%s (%s), ability %s :" % (att, ATTAQUANT_VIS, na))
        for k in sorted(plans, key=lambda kk: (kk[0] is None, kk)):
            print("     depuis %-8s : %s" % (k, plans[k]))
        print("  -- TEMOIN MELEE     u%s (%s), ability %s :" % (melee, MELEE_VIS, na_m))
        for k in sorted(plans_m, key=lambda kk: (kk[0] is None, kk)):
            print("     depuis %-8s : %s" % (k, plans_m[k]))
        Path(sf).with_suffix(".plans.json").write_text(
            json.dumps({"bras": a.bras, "level": a.level, "attaquant": att,
                        "cible": proche, "ability": na,
                        "plans": {"%s,%s" % k: v for k, v in plans.items()},
                        "melee": melee, "abilityMelee": na_m,
                        "plansMelee": {"%s,%s" % k: v for k, v in plans_m.items()},
                        "aura": {"proche": a_proche, "loin": a_loin}}),
            encoding="utf-8")
        print("  [plans ecrits dans %s]" % Path(sf).with_suffix(".plans.json"))

        print()
        print("=== VERDICT (%s) ===" % a.bras)
        if a.bras == "sans-mythique":
            if a_proche or a_loin:
                print("  CONTRE-EPREUVE ROUGE : l'effet %d existe SANS --equip-mythic -- le bras"
                      " positif ne prouverait rien." % EFFECT_TYPE)
                return 1
            print("  CONTRE-EPREUVE VERTE : aucun effet %d. (predictions ecrites pour la"
                  " comparaison inter-bras)" % EFFECT_TYPE)
            return 0
        if not a_proche:
            print("  AURE MUETTE : l'ennemi adjacent a DEUX amis mythiques ne porte pas %d."
                  % EFFECT_TYPE)
            return 1
        if a_loin:
            print("  REGIME NON SEPARANT : l'ennemi ELOIGNE porte l'effet lui aussi -- le")
            print("  selecteur `AdjacentUnits` n'est donc pas ce qu'on mesure ici.")
            return 1
        print("  AURE CONFORME : %s porte %d, %s ne le porte pas (separation GEOMETRIQUE)."
              % (CIBLE_PROCHE_VIS, EFFECT_TYPE, CIBLE_LOIN_VIS))
        print("  (le facteur de degat se lit en comparant ce .plans.json a celui du bras"
              " `sans-mythique` -- ratio attendu 1 + %s/100)" % attendu_pct)
        return 0
    finally:
        if not a.keep and rid is not None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
                print("  [runner %s dispose]" % rid)
            except Exception as exc:  # noqa: BLE001
                print("  [dispose echoue : %s]" % type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
