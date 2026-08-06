#!/usr/bin/env python
"""#419-r5 -- le canal CRIT/BLOCK etait MUET sur TOUTES les unites de TOUS les runners.

LE FAIT
-------
`adeptMorvenn` porte `CritChance = 20` / `CritDamage = 352` dans `data/seed-bc.json`, et le
port lisait `(cc = 20, cd = 0, could_crit = False)` sur l'etat charge. Il fallait poser
`CritDamage` par `--unit-stat` pour ouvrir le canal (cf. `probe_419r3_fold_attack_state.py`).

LA QUESTION BINAIRE, ET LE CRITERE QUI LA TRANCHE
-------------------------------------------------
Deux suspects : `buildNormalizedBC` qui remet le champ a zero, ou `combatSnapshot` qui ne le
publie pas. Le critere enonce AVANT de mesurer : lire la valeur de l'unite EN BATAILLE par un
canal INDEPENDANT de `combatSnapshot`.

  * natif en bataille > 0  ==> le BC transmis est bon, c'est la PUBLICATION qui est muette ;
  * natif en bataille == 0 ==> le champ est perdu EN AMONT, et alors le NATIF LUI-MEME ne crite
    jamais -- un fait observable sans rien devoir a notre port.

Les deux branches ont des consequences disjointes, donc le critere tranche. Le canal
independant retenu est le TEMPLATE que `buildNormalizedBC` RENVOIE (`configJson`) : il est en
amont du spawn, donc en amont de tout snapshot.

LA CAUSE, ETABLIE
-----------------
`buildNormalizedBC` ECRASE les 8 stats numeriques du seed BC par la sortie de
`IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor`
(`frida/hooks/features/normalize-bc/json-build.ts` : `u.CritDamage = b.add(0x14).readS32()`).
Or les 4 stats crit/block ne sont PAS dans la base d'un heros -- mesure sur le gameconfig du
build courant, `adeptMorvenn` porte `stats = {Health, Damage, FixedArmor}` et
`itemSlots = ["I_Crit", "I_Block", "I_Booster_Block"]`. Elles n'arrivent QUE par les ITEMS,
que `IdunMetaLogic.Formulas.StatsFormula$$StatsFor` fusionne via
`IdunMetaLogic.Formulas.UnitDynamicStats$$Merge`. Appelee avec une liste d'items VIDE, la
formule rend donc legitimement 0 -- et ce 0 ecrase le 352 du seed.

`combatSnapshot` est HORS DE CAUSE : il publie fidelement le 0 que le natif porte.

Le LAYOUT n'est pas en cause non plus, et c'est verifie plutot que suppose :
`IdunMetaLogic.Formulas.UnitDynamicStats$$Merge` compose les indices 4, 6, 8, 10 en
PROBABILITE (`p += (1 - p/100) * q`) et les autres ADDITIVEMENT -- exactement CritChance,
BlockChance, CritChanceBonus, BlockChanceBonus aux offsets 0x10 / 0x18 / 0x20 / 0x28.

POURQUOI C'EST COUTEUX
----------------------
`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` est `GetStat(9) > 0 && GetStat(10) > 0`
-- une CONJONCTION. Le canal muet le rendait FAUX pour toute unite, cote natif COMME cote port.
`RollCritical` et le gate << never crit >> etaient donc structurellement inertes, et tout accord
natif-port sur ces chemins etait un accord en REGIME DEGENERE : les deux cotes rendaient zero.
Meme raisonnement pour `IdunBattle.Core.Services.DamageCalculations$$CouldBlock`.

CE QUE CE PROBE MESURE
----------------------
  etape 1  TEMOIN   -- normalisation SANS items : could_crit / could_block sur le pool.
  etape 2  CORRIGE  -- normalisation AVEC items BiS : les memes comptes.
  etape 3  ADDITIF  -- Health / Damage / Armor / FixedArmor INCHANGES entre 1 et 2. C'est ce qui
                       borne le rayon de souffle : le correctif n'ouvre QUE le canal crit/block.
  etape 4  LIVE     -- un runner monte, `combatSnapshot` relu : le natif porte-t-il vraiment
                       `GetStat(9) > 0 && GetStat(10) > 0` ? C'est le bout-en-bout, et c'est
                       aussi ce qui INNOCENTE `combatSnapshot` par la mesure et non par lecture.

Aucune assertion : c'est un probe, il MESURE. La garde vit dans
`tests/engine/test_419r5_canal_crit_ouvert_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import gameconfig as gc          # noqa: E402
import rl_collect_batch as R     # noqa: E402

# Les deux conjoints de `IdunBattle.Core.Services.DamageCalculations$$CouldCrit` et de
# `$$CouldBlock`, nommes cote BC (le JSON du BattleConfiguration), pas cote StatType.
_CRIT = ("CritChance", "CritDamage")
_BLOCK = ("BlockChance", "BlockDamage")
# Les 4 stats que la formule alimente SANS items -- le temoin du caractere additif du correctif.
_HORS_ITEMS = ("Health", "Damage", "Armor", "FixedArmor")


def _conjonction(u: dict, paire: tuple) -> bool:
    """Mirror de la conjonction native : les DEUX conjoints doivent etre > 0."""
    return all((u.get(k) or 0) > 0 for k in paire)


def _compter(tpl_by_id: dict, ids) -> tuple[int, int]:
    return (sum(1 for u in ids if _conjonction(tpl_by_id.get(u, {}), _CRIT)),
            sum(1 for u in ids if _conjonction(tpl_by_id.get(u, {}), _BLOCK)))


def etape_1_2_3(sid: int, rank: int, verbeux: bool) -> dict:
    seed = R._load_seed_bc()

    tpl_t, pool_t, mow_t = R._normalize_and_extract_pool(
        sid, seed, rank, equip_items=False)
    tpl_c, pool_c, mow_c = R._normalize_and_extract_pool(
        sid, seed, rank, equip_items=True)

    ids = sorted(set(pool_t) | set(mow_t))
    t_by = {u["Id"]: u for u in tpl_t["Units"]}
    c_by = {u["Id"]: u for u in tpl_c["Units"]}

    crit_t, block_t = _compter(t_by, ids)
    crit_c, block_c = _compter(c_by, ids)

    print("=== etape 1/2 -- le canal, sur les %d unites normalisees (rank %d) ==="
          % (len(ids), rank))
    print("  TEMOIN  (sans items) : could_crit %3d / %d   could_block %3d / %d"
          % (crit_t, len(ids), block_t, len(ids)))
    print("  CORRIGE (items BiS)  : could_crit %3d / %d   could_block %3d / %d"
          % (crit_c, len(ids), block_c, len(ids)))

    # etape 3 -- LE RAYON DE SOUFFLE, ventile.
    #
    # La premiere ecriture de cette etape portait la premisse << equiper ne touche QUE le canal
    # crit/block, donc 0 divergence attendue >>. LA MESURE LA REFUTE, et c'est le resultat le
    # plus utile de ce probe : equiper un heros le fait aussi entrer dans ses AUTRES slots.
    # On ne compte donc pas un ecart a zero -- on VENTILE par stat et par jeu de slots, parce
    # que c'est le jeu de slots qui explique QUI bouge.
    from collections import Counter
    bouge = []
    par_stat: Counter = Counter()
    slots_bougent: Counter = Counter()
    slots_stables: Counter = Counter()
    for uid in ids:
        touchees = []
        for k in _HORS_ITEMS:
            a, b = t_by.get(uid, {}).get(k), c_by.get(uid, {}).get(k)
            if a != b:
                bouge.append((uid, k, a, b))
                touchees.append(k)
                par_stat[k] += 1
        sl = tuple((gc.unit(uid) or {}).get("itemSlots") or [])
        (slots_bougent if touchees else slots_stables)[sl] += 1

    print("=== etape 3 -- RAYON DE SOUFFLE hors canal crit/block ===")
    print("  unites dont une stat hors-items bouge : %d / %d"
          % (len({u for u, _, _, _ in bouge}), len(ids)))
    print("  ventilation par stat : %s"
          % (dict(par_stat) if par_stat else "(aucune)"))
    print("  -- jeux de slots des unites qui BOUGENT :")
    for sl, n in slots_bougent.most_common():
        print("     %3d  %s" % (n, list(sl)))
    print("  -- jeux de slots des unites STABLES :")
    for sl, n in slots_stables.most_common():
        print("     %3d  %s" % (n, list(sl)))
    for uid, k, a, b in bouge[:8]:
        print("     ex. %-24s %-12s %s -> %s" % (uid, k, a, b))

    if verbeux:
        print("=== echantillon ===")
        for uid in ids[:12]:
            c = c_by.get(uid, {})
            print("  %-24s cc %4s cd %6s bc %4s bd %6s | hp %6s dmg %6s"
                  % (uid, c.get("CritChance"), c.get("CritDamage"),
                     c.get("BlockChance"), c.get("BlockDamage"),
                     c.get("Health"), c.get("Damage")))

    return {"ids": ids, "crit_temoin": crit_t, "crit_corrige": crit_c,
            "block_temoin": block_t, "block_corrige": block_c,
            "hors_items_bouge": bouge, "tpl_corrige": c_by}


def etape_4(sid: int, rank: int, state_file: str, board: str,
            porteur: str, adverse: str, seed: str, sans_items: bool) -> dict:
    """LIVE -- monte un runner et relit `combatSnapshot`.

    C'est l'etage qui INNOCENTE `combatSnapshot` par la mesure : si le template porte 2727 et
    que le snapshot rend 2727, la publication est fidele ; si le template porte 2727 et que le
    snapshot rend 0, alors le suspect ecarte a l'etape 1 redevient coupable.
    """
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", state_file, "--rank", str(rank), "--board", board,
            "--p-units", porteur, "--a-units", adverse]
    if not sans_items:
        argv.append("--bis-items")
    p = subprocess.run(argv, cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("rl_duel build a echoue (rc=%d) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-900:]))
    rid = int(json.load(open(state_file, encoding="utf-8"))["runnerId"])

    snap = R._rpc(sid, "combatSnapshot", [{"runnerId": rid}],
                  timeout=60).get("result") or {}
    if not snap.get("ok"):
        raise RuntimeError("combatSnapshot a echoue : %r" % (snap.get("error"),))

    lignes = []
    for u in snap.get("units") or []:
        st = u.get("stats") or {}
        cc, cd = st.get("critChance"), st.get("critDamage")
        bc_, bd = st.get("blockChance"), st.get("blockDamage")
        lignes.append({
            "entityId": u.get("entityId"),
            "critChance": cc, "critDamage": cd,
            "blockChance": bc_, "blockDamage": bd,
            "could_crit": bool((cc or 0) > 0 and (cd or 0) > 0),
            "could_block": bool((bc_ or 0) > 0 and (bd or 0) > 0),
        })
    return {"runnerId": rid, "statTypes": snap.get("statTypes"), "units": lignes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--porteur", default="adeptMorvenn")
    ap.add_argument("--adverse", default="tauCrisis")
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU pour l'etage live (sinon l'etage est saute)")
    ap.add_argument("--sans-items", action="store_true",
                    help="etage live : monte le runner SANS --bis-items (TEMOIN)")
    ap.add_argument("--verbeux", action="store_true")
    a = ap.parse_args(argv)

    sid = R._resolve_session()
    print("[419-r5] session %d | build %s | rank %d"
          % (sid, gc.identity().get("build") or "?", a.rank))

    res = etape_1_2_3(sid, a.rank, a.verbeux)

    if a.state_file:
        print("=== etape 4 -- LIVE (%s vs %s, board %s%s) ==="
              % (a.porteur, a.adverse, a.board,
                 ", --no-items" if a.sans_items else ""))
        live = etape_4(sid, a.rank, a.state_file, a.board,
                       a.porteur, a.adverse, a.seed, a.sans_items)
        print("  runner %d | %d unite(s)" % (live["runnerId"], len(live["units"])))
        for u in live["units"]:
            print("    e%-4s cc %5s cd %6s bc %5s bd %6s | could_crit %-5s could_block %s"
                  % (u["entityId"], u["critChance"], u["critDamage"],
                     u["blockChance"], u["blockDamage"],
                     u["could_crit"], u["could_block"]))
        n_crit = sum(1 for u in live["units"] if u["could_crit"])
        print("  NATIF EN BATAILLE : could_crit %d / %d"
              % (n_crit, len(live["units"])))
        try:
            R._rpc(sid, "disposeRunner", [{"runnerId": live["runnerId"]}], timeout=30)
            print("  runner %d dispose" % live["runnerId"])
        except Exception as e:                                    # noqa: BLE001
            print("  [avertissement] dispose a echoue : %s" % e)

    print("=== BILAN ===")
    print("  canal crit  : %d -> %d" % (res["crit_temoin"], res["crit_corrige"]))
    print("  canal block : %d -> %d" % (res["block_temoin"], res["block_corrige"]))
    print("  couples (unite, stat hors-items) qui bougent : %d "
          "-- ventilation a l'etape 3" % len(res["hors_items_bouge"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
