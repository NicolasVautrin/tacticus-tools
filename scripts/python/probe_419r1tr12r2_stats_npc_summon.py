#!/usr/bin/env python
"""#419-r1-tr12-r2 -- le CHEMIN DE STATS EXPLICITE des porteurs NPC et SUMMON.

CE QUI EST MESURE, ET POURQUOI CHAQUE ETAGE EST NECESSAIRE.

Le verrou (case-92 §5bis) : `buildNormalizedBC` calcule TOUTES les stats par
`IStatsFormula.StatsUsingProgressionIndexFor`, la formule des HEROS. Une unite sans table de
progression de heros y LEVE, part en `skipped` et n'atteint jamais le pool de `--p-units`. Toute
mecanique portee seulement par un npc ou un summon n'etait donc confrontable que par GREFFE de son
ability sur un heros du pool -- une greffe qui ne couvre NI les stats, NI les traits, NI les armes
du vrai porteur.

Le natif, lui, a deux autres chemins NOMMES, et ils ne se ressemblent pas :

  NPC     `IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats(unitId, level)`
          -> `idun.meta.extensions.UnitConfigExtensions$$GetStatsForLevel(config, level)`
          = `units.npc[id].stats[min(ToZeroBasedIndex(level), Count-1)]`, le `level` etant le
          suffixe `:<n>` de l'unitId (`idun.shared.UnitNamingConventions$$GetLevelFromUnitId`,
          DEFAUT 1). 491/491 npc du gameconfig portent cette table.

  SUMMON  `IdunMetaLogic.UserProgress.UnitProgression$$GetSummonStats(constantType, abilityConfig)`
          = les variables `summon*` de l'ABILITY qui invoque. Les 65 summons du gameconfig n'ont
          AUCUN `stats[]` -- et le jeu ecrit `Health=0` dans `BC.Units[]` pour les 65 (etage 4).

ETAGES
  1. TEMOIN NON NUL, offline. Le mirror npc est confronte aux entrees npc que LE JEU a ecrites
     dans le seed BC capture. Ce n'est PAS un accord entre deux lectures de la meme table : a
     gauche le gameconfig vivant, a droite ce que
     `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` a produit en bataille
     reelle. L'etage REFUSE un temoin vide -- un accord sur zero entree passerait pour un vert.
  2. DEUX REGIMES, pas un. Les stats posees doivent etre celles du CATALOGUE et pas celles d'un
     heros normalise : on imprime les trois cotes (npc palier 33, npc `Surv` palier 1, heros rank
     17 du template) et on assertionne qu'ils sont DEUX A DEUX distincts, et non nuls.
  3. CONTRE-EPREUVE LIVE, chemin DESARME. On injecte l'Electropriest npc au catalogue et on
     appelle `buildNormalizedBC` SANS `explicitStats` : attendu, l'unite tombe en `skipped` et son
     `Health` reste 0. C'est le cote « les stats redeviennent fausses ou absentes », mesure sur le
     natif, pas raisonne.
  4. CONTRE-EPREUVE LIVE, chemin ARME. Meme appel AVEC `explicitStats`. Sur une session dont le
     bundle est anterieur a cette tranche, le RPC ignore le champ : le harnais le DETECTE
     (`explicit` vide -> RuntimeError) et l'etage rend NON CONFRONTE -- jamais un faux vert.
  5. MUTANTS DU MIRROR, offline. Clamp haut, defaut de level, regime `_2` du summon : chacun doit
     DEPLACER le resultat, sinon l'etage 1 ne prouvait rien de ce qu'il croit prouver.

USAGE
    python probe_419r1tr12r2_stats_npc_summon.py                 # tous les etages
    python probe_419r1tr12r2_stats_npc_summon.py --offline       # 1, 2, 5 seulement
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_inject as CI            # noqa: E402
import gameconfig as G                 # noqa: E402
import rl_collect_batch as R           # noqa: E402

# Le porteur de #419-r1-tr12-r2. `admecSmnElectropriest` (SUMMON) est declare par
# `EnvFactionSummons:AdeptusMechanicus`, qu'AUCUNE unite ne porte -> pas d'invocateur a spawner.
# `admecNpc3Electropriest` est le MEME kit (memes `passiveAbilities` VoltagheistField + ElectroShock,
# meme arme 3 hits Particle, meme Movement 3) par la voie NPC, qui elle a une table de stats.
NPC_ID = "admecNpc3Electropriest"
NPC_LEVEL = 33          # palier Rank 17 / ProgressionIndex 15 de sa table (45 paliers)
NPC_SURV = "admecNpc3ElectropriestSurv"
SMN_ID = "admecSmnElectropriest"
RANK = 17


def _hdr(n: int, title: str) -> None:
    print(f"\n=== ETAGE {n} -- {title} " + "=" * max(0, 58 - len(title)))


# --------------------------------------------------------------------------- etage 1
def etape1_temoin(seed: dict) -> int:
    """⚠ CE TEMOIN EST PASSE DE 4 A 508 ENTREES (#10039), ET IL A TROUVE DEUX DEFAUTS.

    `data/seed-bc.json` n'est plus la capture d'UNE bataille mais un catalogue FORGE par
    `Idun.Source.IdunBattle.View.BattleConfigBuilder`. Les 4 npc d'avant etaient tous non-MoW et
    tous pourvus d'un passif : deux branches du mirror n'y etaient JAMAIS confrontees, et les deux
    etaient FAUSSES (branche MoW de `npc_progression_multiplier_pct`, hierarchie « Secondary » de
    `npc_stats`). 29 divergences -> 6 apres correctif.

    DEUX CRITERES ONT DU CHANGER, ET AUCUN N'A ETE AFFAIBLI :
      * `min(Health) > 0` sur TOUTES les entrees etait vrai sur 4 npc, faux sur 508 : 38 portent
        Health 0 parce que leur ligne `units.npc[id].stats[]` porte elle-meme 0 (`LootObj_*`,
        `powup*`, MoW npc). Le zero est un FAIT du gameconfig, pas un temoin degenere -- ce qu'il
        faut garder, c'est qu'AUCUN zero ne soit injustifie, et que la masse non nulle reste
        grosse ;
      * `div == 0` accusait le mirror pour `LootObj_CoinCrate:23`, une entree que la FORGE produit
        fautive (cf. `catalog_inject.NPC_WITNESS_STALE`). L'epingle est gardee dans les deux sens.
    """
    _hdr(1, "TEMOIN NON DEGENERE : le mirror npc contre ce que LE JEU a ecrit")
    rows, div = CI.npc_witness_diff(seed)
    for uid, bad in rows:
        if bad:
            print("  DIFF " + uid + "  " + json.dumps(bad, sort_keys=True))
    n_champs = len(rows) * len(CI.NPC_WITNESS_FIELDS)
    print(f"  npc confrontes = {len(rows)}  champs = {n_champs}  divergences = {div}")
    if not rows:
        print("  ECHEC : temoin VIDE -- aucun npc dans ce catalogue, rien n'a ete confronte")
        return 1
    ko = 0
    # (a) le temoin doit rester non degenere EN MASSE : un mirror qui rendrait 0 partout
    #     s'accorderait parfaitement avec un temoin integralement nul.
    ents = CI.npc_entries_of(seed)
    non_nuls = [u for u in ents if int(u.get("Health") or 0) > 0]
    print(f"  entrees a Health > 0 : {len(non_nuls)} / {len(ents)}")
    if len(non_nuls) <= 100:
        print("  ECHEC : trop peu de temoins non nuls -- regime degenere")
        ko = 1
    # (b) ... et chaque zero doit etre DIT par le gameconfig, jamais subi.
    injustifies = []
    for u in ents:
        if int(u.get("Health") or 0) != 0:
            continue
        try:
            attendu = int(CI.npc_stats_row(u["Id"]).get("Health") or 0)
        except Exception as exc:
            injustifies.append((u["Id"], f"ROW-ERR {exc}"))
            continue
        if attendu != 0:
            injustifies.append((u["Id"], attendu))
    if injustifies:
        print(f"  ECHEC : {len(injustifies)} entree(s) a Health 0 que la table `stats[]` "
              f"contredit -- le catalogue les a mal montees : {injustifies[:5]}")
        ko = 1
    # (c) les divergences restantes doivent etre EXACTEMENT l'epingle, dans les deux sens.
    mesure = {uid: sorted(bad) for uid, bad in rows if bad}
    attendu_pin = {uid: sorted(ch) for uid, ch in CI.NPC_WITNESS_STALE.items()}
    if mesure != attendu_pin:
        print(f"  ECHEC : divergences != NPC_WITNESS_STALE -- epingle={attendu_pin} "
              f"mesure={mesure}")
        ko = 1
    else:
        print(f"  divergences EXACTEMENT epinglees ({len(mesure)} entree(s)) : "
              f"{sorted(mesure)}")
    return ko


# --------------------------------------------------------------------------- etage 2
def etape2_deux_regimes(template: dict | None) -> int:
    _hdr(2, "DEUX REGIMES : catalogue npc vs heros normalise")
    a = CI.explicit_stats(f"{NPC_ID}:{NPC_LEVEL}")["fields"]
    b = CI.explicit_stats(NPC_SURV)["fields"]
    print(f"  {NPC_ID}:{NPC_LEVEL:<3} (npc, Rank {a['Rank']}) hp={a['Health']:>7} "
          f"dmg={a['Damage']:>6} fixedArmor={a['FixedArmor']:>6}")
    print(f"  {NPC_SURV:<28} (npc, Rank {b['Rank']}) hp={b['Health']:>7} "
          f"dmg={b['Damage']:>6} fixedArmor={b['FixedArmor']:>6}")
    # Ce que le CATALOGUE porte AVANT le chemin explicite : la synthese laisse les 8 stats a 0,
    # parce que jusqu'ici c'est la formule heros qui devait les ecrire (et qui LEVE).
    base = CI.synthesize(f"{NPC_ID}:{NPC_LEVEL}", rank=RANK)
    print(f"  catalogue AVANT le chemin explicite            hp={base['Health']:>7} "
          f"dmg={base['Damage']:>6} fixedArmor={base['FixedArmor']:>6}")
    rc = 0
    if a["Health"] == b["Health"]:
        print("  ECHEC : les deux paliers npc rendent le MEME Health -- la table ne discrimine pas")
        rc = 1
    if base["Health"] != 0:
        print("  ECHEC : la synthese ne part pas de 0, le contraste n'est pas celui qu'on croit")
        rc = 1
    if min(a["Health"], b["Health"]) <= 0:
        print("  ECHEC : un chemin explicite rend 0 -- rien a mesurer")
        rc = 1
    if template is not None:
        heroes = [u for u in template.get("Units") or []
                  if int(u.get("Rank") or 0) == RANK and int(u.get("Health") or 0) > 0
                  and str(u.get("Id", "")).split(":")[0] in G._cfg()["units"]["lineup"]]
        if heroes:
            h = min(heroes, key=lambda u: int(u["Health"]))
            H = max(heroes, key=lambda u: int(u["Health"]))
            print(f"  heros normalises rank {RANK} (formule HEROS) : "
                  f"{len(heroes)} unites, hp de {h['Health']} ({h['Id']}) "
                  f"a {H['Health']} ({H['Id']})")
            # Discrimination FORTE : aucun des 98 heros normalises ne doit porter EXACTEMENT le
            # Health que le chemin npc rend -- sinon les deux regimes seraient indiscernables sur
            # ce point, et un accord ne prouverait pas quel chemin a produit la valeur.
            collide = [u["Id"] for u in heroes if int(u["Health"]) in (a["Health"], b["Health"])]
            print(f"  heros portant EXACTEMENT un des deux Health npc : {collide or 'aucun'}")
            if collide:
                print("  ECHEC : les deux regimes sont indiscernables sur ce point")
                rc = 1
        else:
            print("  (template sans heros normalise -- comparaison heros NON JOUEE)")
    else:
        print("  (pas de template live -- comparaison aux heros normalises NON JOUEE)")
    return rc


# --------------------------------------------------------------------------- etage 5
def etape5_mutants() -> int:
    _hdr(5, "MUTANTS DU MIRROR : chaque regle doit DEPLACER le resultat")
    rc = 0
    ref = CI.npc_stats(f"{NPC_ID}:{NPC_LEVEL}")["Health"]
    n_paliers = len(G.unit(NPC_ID)["stats"])
    cases = [
        ("defaut de level (id sans suffixe -> 1, PAS le dernier palier)",
         CI.npc_stats(NPC_ID)["Health"]),
        ("palier voisin (level-1)",
         CI.npc_stats(f"{NPC_ID}:{NPC_LEVEL - 1}")["Health"]),
        (f"clamp HAUT (level {n_paliers + 500} -> dernier palier {n_paliers})",
         CI.npc_stats(f"{NPC_ID}:{n_paliers + 500}")["Health"]),
    ]
    for label, val in cases:
        moved = val != ref
        print(f"  {'MORD ' if moved else 'INERTE'} {label:<62} hp={val} (ref={ref})")
        if not moved:
            rc = 1
    # clamp HAUT == dernier palier exactement (pas une valeur inventee)
    last = int(G.unit(NPC_ID)["stats"][-1]["Health"])
    got = CI.npc_stats(f"{NPC_ID}:{n_paliers + 500}")["Health"]
    print(f"  clamp HAUT == stats[-1].Health ? {got} vs {last} -> "
          + ("OK" if got == last else "ECHEC"))
    if got != last:
        rc = 1
    # `ToZeroBasedIndex` LEVE sur <= 0 : le mirror doit lever aussi, pas clamper en silence.
    try:
        CI.npc_stats(f"{NPC_ID}:0")
        print("  ECHEC : level 0 accepte -- le natif ToZeroBasedIndex LEVE")
        rc = 1
    except ValueError:
        print("  OK    level 0 REFUSE (mirror de ToZeroBasedIndex, qui leve)")
    # SUMMON : le regime `_2` doit rendre autre chose que le regime primary.
    prim = CI.summon_stats(SMN_ID)
    print(f"  summon {SMN_ID} primary={prim['_primary']} via {prim['_ability']} "
          f"hp={prim['Health']} dmg={prim['Damage']} fixedArmor={prim['FixedArmor']}")
    if prim["Health"] <= 0:
        print("  ECHEC : le chemin summon rend Health=0 -- rien a mesurer")
        rc = 1
    lvl1 = CI.summon_stats(SMN_ID, ability_level=1)
    print(f"  summon au niveau d'ability 1 : hp={lvl1['Health']} (vs {prim['Health']} au 50)")
    if lvl1["Health"] == prim["Health"]:
        print("  ECHEC : le niveau d'ability ne deplace pas les stats du summon")
        rc = 1
    return rc


# --------------------------------------------------------------------------- etage 4bis
def etape4_summon_catalogue(seed: dict) -> int:
    _hdr(4, "CE QUE LE JEU ECRIT VRAIMENT POUR UN SUMMON (mesure, pas hypothese)")
    smn = G._cfg()["units"]["summons"]
    ents = [u for u in seed.get("Units") or []
            if str(u.get("Id", "")).split(":")[0] in smn]
    nz = [u["Id"] for u in ents if int(u.get("Health") or 0) != 0]
    print(f"  entrees summon du seed BC = {len(ents)}  avec Health != 0 = {len(nz)} {nz[:5]}")
    print(f"  -> poser des stats non nulles sur une entree summon est un MONTAGE "
          f"(etat POST-SPAWN), pas un mirror du catalogue.")
    if not ents:
        print("  ECHEC : aucune entree summon -- la mesure est vide")
        return 1
    return 0 if not nz else 1


# --------------------------------------------------------------------------- live
def etapes_live(sid: int) -> int:
    from rl_collect_batch import _rpc, _load_board_dump
    rc = 0
    print("\n[live] amorce...")
    w = _rpc(sid, "autoBootExtraire", [{}], timeout=180)
    print(f"[live] amorce -> {json.dumps(w)[:200]}")

    board = _load_board_dump("MC1_67")
    seed = R._load_seed_bc(None)
    uid = f"{NPC_ID}:{NPC_LEVEL}"
    seed, added, added_ab, _unres = CI.augment(seed, [uid], rank=RANK)
    print(f"[live] catalogue augmente : +{len(added)} unites {added} "
          f"+{len(added_ab)} configs d'ability")

    _hdr(3, "CONTRE-EPREUVE LIVE -- chemin DESARME (sans explicitStats)")
    # Appel RPC DIRECT (pas `_normalize_and_extract_pool`) : on veut la RAISON que le natif
    # attache au skip, pas seulement l'absence du pool. « hors pool » a plusieurs causes ;
    # `reason` en nomme une seule.
    args = {
        "baseBcJson": json.dumps(seed), "targetRank": RANK,
        "targetProgressionIndex": RANK, "targetRarity": 5, "targetLevel": 50,
        "targetStarLevel": 5, "targetAbilityLevel": 50,
        "boardJson": json.dumps(board["board"]),
        "spawnPointSetIndex": board.get("spawnPointsSet") or 0,
    }
    out = _rpc(sid, "buildNormalizedBC", [args], timeout=60).get("result") or {}
    if not out.get("ok"):
        print(f"  buildNormalizedBC a echoue: {out.get('err')}")
        return 1
    tmpl = json.loads(out["configJson"])
    ent = next((u for u in tmpl["Units"] if u.get("Id") == uid), None)
    au_pool = uid in set(out.get("normalized") or [])
    reason = next((s["reason"] for s in (out.get("skipped") or [])
                   if s.get("unitId") == uid), None)
    print(f"  {uid} normalise ? {au_pool}   skipped.reason = {reason!r}")
    print(f"  entree du template : hp={ent and ent.get('Health')} "
          f"dmg={ent and ent.get('Damage')} fixedArmor={ent and ent.get('FixedArmor')}")
    if au_pool:
        print("  INATTENDU : la formule heros a accepte ce npc -- le verrou decrit n'existe plus")
        rc = 1
    elif ent is not None and int(ent.get("Health") or 0) != 0:
        print("  INATTENDU : stats non nulles sans le chemin explicite")
        rc = 1
    elif reason is None:
        print("  INATTENDU : ni normalise ni skippe -- la mesure ne dit pas ce qui s'est passe")
        rc = 1
    else:
        print("  OK : desarme, l'unite est SKIPPEE par la formule heros et ses stats restent a 0")
    # Le template live porte les heros normalises : c'est le SECOND regime de l'etage 2, qu'on
    # ne pouvait pas jouer offline.
    rc |= etape2_deux_regimes(tmpl)

    _hdr(4, "CONTRE-EPREUVE LIVE -- chemin ARME (avec explicitStats)")
    patch = {uid: CI.explicit_stats(uid)["fields"]}
    print(f"  patch soumis : hp={patch[uid]['Health']} dmg={patch[uid]['Damage']} "
          f"fixedArmor={patch[uid]['FixedArmor']}")
    try:
        tmpl2, pool2, _m2 = R._normalize_and_extract_pool(
            sid, seed, RANK, board_dump=board, explicit_stats=patch)
    except RuntimeError as e:
        # ⚠ CE REFUS EST ROUGE DEPUIS #419-r1-tr12-r2 (2026-08-05). Il rendait `rc` inchange, au
        # motif que la session portait un bundle anterieur -- un repli qui RASSURE. Le bundle
        # porteur d'`explicitStats` est injecte et confronte depuis, et le montage complet
        # (`test_419r1tr12r2_electro_shock_reel_live.py`) en depend de bout en bout : un refus ne
        # peut donc plus vouloir dire « pas encore ». Les deux accuses possibles sont NOMMES.
        print(f"  ECHEC : le chemin ARME a ete refuse -- {e}")
        print("  accuses : (a) la session porte un bundle SANS `explicitStats` "
              "(`frida/hooks/features/normalize-bc/json-build.ts`) -> le confirmer avant tout ; "
              "(b) le patch soumis ne correspond a aucune entree de `BC.Units[]`.")
        return rc | 1
    ent2 = next((u for u in tmpl2["Units"] if u.get("Id") == uid), None)
    print(f"  {uid} au pool ? {uid in pool2}")
    print(f"  entree du template : hp={ent2 and ent2.get('Health')} "
          f"dmg={ent2 and ent2.get('Damage')} fixedArmor={ent2 and ent2.get('FixedArmor')}")
    if uid not in pool2 or int((ent2 or {}).get("Health") or 0) != patch[uid]["Health"]:
        print("  ECHEC : le chemin arme n'a pas pose les stats attendues")
        rc = 1
    else:
        print("  OK : arme, l'unite est AU POOL avec les stats de son propre catalogue")
    return rc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="n'appelle aucun RPC (etages 1, 2, 4-catalogue, 5)")
    a = ap.parse_args(argv)

    seed = json.loads((CI.SEED_BC).read_text(encoding="utf-8"))
    rc = 0
    rc |= etape1_temoin(seed)
    template = None
    sid = None
    if not a.offline:
        try:
            sid = R._resolve_session()
        except Exception as e:                        # pragma: no cover - diagnostic
            print(f"[live] session indisponible : {e}")
    rc |= etape2_deux_regimes(template)
    rc |= etape4_summon_catalogue(seed)
    rc |= etape5_mutants()
    if sid is not None:
        rc |= etapes_live(sid)
    print("\n[probe] rc =", rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
