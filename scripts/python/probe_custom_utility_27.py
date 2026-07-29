"""Garde legere OFFLINE des overrides CalculateCustomUtility portes (#27, case-27).

Verifie la FORME des termes custom portes (dispatch + formule), pas le live :
- ArmoriumCherub (1014) IdunBattle.AI.Playbook.Loki.ArmoriumCherubPlaybook$$CalculateCustomUtility = Fix64(1) constant.
- LightOfSanguinius (1177) IdunBattle.AI.Playbook.LightOfSanguiniusPlaybook$$CalculateCustomUtility = count(units caster-team a PV%==100) * W(-10).
- HeraldOfTheApocalypse (1020) IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$CalculateCustomUtility = 0 si un ennemi normal-attaquable par le caster
  peut lui-meme frapper quelqu'un, sinon W(HeraldOfTheApocalypse_CannotKillEnemy)=50.
- Drachnyen (1029) IdunBattle.AI.Playbook.Loki.DrachnyenPlaybook$$CalculateCustomUtility = W(Drachnyen_MultipleAdjacentUnits)=10 si >= 2 ENNEMIS
  adjacents a la TUILE D'ATTAQUE, sinon 0.
- DoomSiren (1199) IdunBattle.AI.Playbook.Loki.DoomSirenPlaybook$$CalculateCustomUtility =
  W(DoomSiren_DefinitelyOverkill)=40 * #(predictions WillBeOverkill)
  + W(DoomSiren_TargetHasAdjacentEnemy)=50 si au moins UN ennemi est adjacent a la TUILE DE LA CIBLE.
- SavageEchoes (1230) IdunBattle.AI.Playbook.Loki.SavageEchoesPlaybook$$CalculateCustomUtility =
  0 si le RATIO de PV du CASTER est <= constants.healthPct/100, sinon
  W(SavageEchoes_DislikesAboveHealthPct) = -10. Comparaison de RATIO
  (`IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger`),
  PAS un pourcentage arrondi -> la borne 50.19 % doit rendre W et 49.64 % doit rendre 0.
- HeavyWarpFlamer (1227) IdunBattle.AI.Playbook.Loki.HeavyWarpFlamerPlaybook$$CalculateCustomUtility =
  W(HeavyWarpFlamer_LikesAdjacentEnemies)=10 * COMPTE d'ennemis adjacents a la TUILE DE LA CIBLE.
  Meme ensemble que le 2e terme de DoomSiren, mais LINEAIRE : le test de linearite (0/1/2/3
  voisins -> 0/W/2W/3W) est ce qui distingue ce port d'une copie booleenne de DoomSiren.
- CLIQUET DE NON-REGRESSION : SorcerousFacade (1100) NE DOIT PAS etre enregistree (son terme
  s'ancre sur un ALLIE Psyker que le moteur ne route pas ; cf. case-27 tranche 3).

Usage : python probe_custom_utility_27.py   (depuis scripts/python ; ASCII only ; exit 0 = OK)
"""
from __future__ import annotations

import sys
import types

import engine.playbook as pb
import engine.weights as W


def _fake_ctx(wt, **kw):
    d = dict(me={"team": 1, "id": 100}, units=[], obs_units=[], epos=[], elev_by_pos={}, wt=wt,
             uid=100, plans={}, normal_ids={69}, hp_cur_by_id={}, hpmax_by_id={})
    d.update(kw)
    return types.SimpleNamespace(**d)


def main() -> int:
    wt = W.load()
    fails = []

    # dispatch : les ids doivent etre enregistres sur les classes attendues.
    reg = pb.REGISTRY
    for aid, name in ((1014, "ArmoriumCherubPlaybook"), (1177, "LightOfSanguiniusPlaybook"),
                      (1020, "HeraldOfTheApocalypsePlaybook"), (1029, "DrachnyenPlaybook"),
                      (1199, "DoomSirenPlaybook"), (1230, "SavageEchoesPlaybook"),
                      (1227, "HeavyWarpFlamerPlaybook")):
        got = type(reg.get(aid)).__name__
        if got != name:
            fails.append(f"dispatch {aid}: attendu {name}, obtenu {got}")
    # cliquet : 1100 ne doit PAS revenir au registre (terme ancre sur un ALLIE, route absente)
    if 1100 in reg:
        fails.append("SorcerousFacade (1100) est ENREGISTREE : son terme s'ancre sur la tuile d'un "
                     "ALLIE Psyker, le moteur ne lui route que des ENNEMIS -> port non validable")

    # ArmoriumCherub = 1 constant (independant du ctx).
    cb = pb.get_playbook(1014)
    v = cb.calculate_custom_utility(_fake_ctx(wt), (0, 0), 5, 1014)
    if v != 1.0:
        fails.append(f"ArmoriumCherub custom attendu 1.0, obtenu {v}")

    # LightOfSanguinius = count(full-HP friends) * W(-10). 2 amis pleins (100,101) sur la team 1.
    units = [
        {"team": 1, "id": 100, "alive": True},
        {"team": 1, "id": 101, "alive": True},
        {"team": 1, "id": 102, "alive": True},   # blesse -> exclu
        {"team": 2, "id": 200, "alive": True},   # ennemi -> exclu
        {"team": 1, "id": 103, "alive": False},  # mort -> exclu
    ]
    obs = [
        {"squadId": 100, "hp": 100, "hpMax": 100},
        {"squadId": 101, "hp": 50, "hpMax": 50},
        {"squadId": 102, "hp": 30, "hpMax": 100},
        {"squadId": 200, "hp": 80, "hpMax": 80},
        {"squadId": 103, "hp": 0, "hpMax": 100},
    ]
    w = wt.sub("ActiveAbilities", "LightOfSanguinius_FullHealthFriendlyUnits")
    ls = pb.get_playbook(1177)
    v = ls.calculate_custom_utility(_fake_ctx(wt, units=units, obs_units=obs), (0, 0), 5, 1177)
    expected = 2 * w
    if v != expected:
        fails.append(f"LightOfSanguinius custom attendu {expected} (2 amis pleins * W={w}), obtenu {v}")

    # --- Drachnyen (1029) : >= 2 ENNEMIS adjacents a la TUILE D'ATTAQUE -> W(10), sinon 0.
    wd = wt.sub("ActiveAbilities", "Drachnyen_MultipleAdjacentUnits")
    dr = pb.get_playbook(1029)
    tile = (2, 5)
    adj2 = [(2, 4), (2, 6)]            # deux voisins de (2,5)
    adj1 = [(2, 4), (9, 9)]            # un seul voisin
    v2 = dr.calculate_custom_utility(_fake_ctx(wt, epos=adj2), tile, 5, 1029)
    v1 = dr.calculate_custom_utility(_fake_ctx(wt, epos=adj1), tile, 5, 1029)
    v0 = dr.calculate_custom_utility(_fake_ctx(wt, epos=[]), tile, 5, 1029)
    if v2 != wd:
        fails.append(f"Drachnyen 2 ennemis adjacents: attendu {wd}, obtenu {v2}")
    if v1 != 0.0 or v0 != 0.0:
        fails.append(f"Drachnyen <2 adjacents: attendu 0/0, obtenu {v1}/{v0}")
    # position-DEPENDANCE : la meme config vue depuis une tuile eloignee doit rendre 0
    if dr.calculate_custom_utility(_fake_ctx(wt, epos=adj2), (8, 8), 5, 1029) != 0.0:
        fails.append("Drachnyen: terme non position-dependant (tuile eloignee != 0)")

    # --- Herald (1020) : 0 si un ennemi normal-attaquable peut lui-meme frapper, sinon W(50).
    wh = wt.sub("ActiveAbilities", "HeraldOfTheApocalypse_CannotKillEnemy")
    hp = pb.get_playbook(1020)
    # caster (id 100, team 1) ; ennemi 200 (team 2, blackTerminator = melee portee 1).
    units_far = [{"id": 100, "team": 1, "alive": True, "visualId": "blackHaarken",
                  "pos": {"col": 0, "row": 0}},
                 {"id": 200, "team": 2, "alive": True, "visualId": "blackTerminator",
                  "pos": {"col": 0, "row": 4}}]
    plans = {100: {"evals": [{"abilityId": 69, "targetId": 200, "rankCount": 3}]}}
    v_far = hp.calculate_custom_utility(
        _fake_ctx(wt, units=units_far, plans=plans), (0, 3), 200, 1020)
    if v_far != wh:
        fails.append(f"Herald (ennemi hors de SA portee): attendu {wh}, obtenu {v_far}")
    units_near = [dict(units_far[0], pos={"col": 0, "row": 3}), units_far[1]]
    v_near = hp.calculate_custom_utility(
        _fake_ctx(wt, units=units_near, plans=plans), (0, 3), 200, 1020)
    if v_near != 0.0:
        fails.append(f"Herald (ennemi ADJACENT au caster -> peut frapper): attendu 0, obtenu {v_near}")
    # aucune cible normale atteignable -> la boucle sort immediatement -> W
    v_none = hp.calculate_custom_utility(
        _fake_ctx(wt, units=units_far, plans={100: {"evals": []}}), (0, 3), 200, 1020)
    if v_none != wh:
        fails.append(f"Herald (aucune cible normale): attendu {wh}, obtenu {v_none}")

    # --- DoomSiren (1199) : 40 * #(preds WillBeOverkill) + 50 si un ennemi est adjacent a la CIBLE.
    wok = wt.sub("ActiveAbilities", "DoomSiren_DefinitelyOverkill")
    wadj = wt.sub("ActiveAbilities", "DoomSiren_TargetHasAdjacentEnemy")
    ds = pb.get_playbook(1199)
    tgt_units = [{"id": 200, "team": 2, "alive": True, "pos": {"col": 3, "row": 3}}]
    # `make_damage_predictions` neutralise (pas de Scene offline) -> isole le terme d'adjacence.
    ds_noscene = types.SimpleNamespace(**{**vars(_fake_ctx(wt, units=tgt_units, epos=[(3, 4)])),
                                          "scene": None})
    v_adj = ds.calculate_custom_utility(ds_noscene, (2, 3), 200, 1199)
    ds_alone = types.SimpleNamespace(**{**vars(_fake_ctx(wt, units=tgt_units, epos=[(9, 9)])),
                                        "scene": None})
    v_alone = ds.calculate_custom_utility(ds_alone, (2, 3), 200, 1199)
    if v_adj != wadj:
        fails.append(f"DoomSiren (ennemi adjacent a la cible): attendu {wadj}, obtenu {v_adj}")
    if v_alone != 0.0:
        fails.append(f"DoomSiren (cible isolee): attendu 0, obtenu {v_alone}")
    # le terme d'adjacence est ancre sur la CIBLE, pas sur la tuile d'attaque : deplacer la tuile
    # d'attaque loin ne change rien (contraste avec Drachnyen).
    if ds.calculate_custom_utility(
            types.SimpleNamespace(**{**vars(_fake_ctx(wt, units=tgt_units, epos=[(3, 4)])),
                                     "scene": None}), (8, 8), 200, 1199) != wadj:
        fails.append("DoomSiren: terme d'adjacence ancre a tort sur la tuile d'attaque")
    # WillBeOverkill : mirror direct (le terme overkill somme W par prediction sur-tuante).
    from engine.utilities.damage import will_be_overkill
    if not will_be_overkill({"hpBefore": 100, "rawHealthDmgMin": 250, "rawHealthDmgMax": 300}):
        fails.append("will_be_overkill: dmgMin 250 vs hp 100 devrait etre un overkill garanti")
    if will_be_overkill({"hpBefore": 100, "rawHealthDmgMin": 120, "rawHealthDmgMax": 300}):
        fails.append("will_be_overkill: dmgMin 120 vs hp 100 (over-shoot 20% < 100%) n'est PAS garanti")

    # --- SavageEchoes (1230) : ratio PV du caster <= healthPct/100 -> 0, sinon W(-10).
    import gameconfig as GC
    thr = int(((GC.ability("SavageEchoes") or {}).get("constants") or {}).get("healthPct") or 0)
    wse = wt.sub("ActiveAbilities", "SavageEchoes_DislikesAboveHealthPct")
    se = pb.get_playbook(1230)
    # Bornes MESUREES live (probe_27_3_savage_ab.py) : 1638/3300 = 49.64 % -> 0 ;
    # 1675/3337 = 50.19 % -> W. Un pourcentage ARRONDI rendrait 0 dans les deux cas.
    cases = [((1638, 3300), 0.0), ((1675, 3337), wse), ((1708, 3370), wse),
             ((1738, 3400), wse), ((3300, 3300), wse), ((1650, 3300), 0.0)]
    for (cur, mx), want in cases:
        c = _fake_ctx(wt, hp_cur_by_id={100: cur}, hpmax_by_id={100: mx})
        v = se.calculate_custom_utility(c, (0, 0), 5, 1230)
        if v != want:
            fails.append(f"SavageEchoes {cur}/{mx} ({cur / mx * 100:.2f}%, seuil {thr}%): "
                         f"attendu {want}, obtenu {v}")
    # stats illisibles -> pas de terme invente
    if se.calculate_custom_utility(_fake_ctx(wt), (0, 0), 5, 1230) != 0.0:
        fails.append("SavageEchoes sans stats de caster: attendu 0.0")

    # --- HeavyWarpFlamer (1227) : W(10) * COMPTE d'ennemis adjacents a la TUILE DE LA CIBLE.
    wwf = wt.sub("ActiveAbilities", "HeavyWarpFlamer_LikesAdjacentEnemies")
    if wwf == 0:
        fails.append("HeavyWarpFlamer_LikesAdjacentEnemies absent des poids : la table `Utilities` "
                     "n'a pas ete re-synthetisee depuis le gameconfig courant "
                     "(cf. catalog_inject.refresh_ai_utilities)")
    wf = pb.get_playbook(1227)
    wf_units = [{"id": 200, "team": 2, "alive": True, "pos": {"col": 3, "row": 3}}]
    # LINEARITE : 0/1/2/3 voisins -> 0/W/2W/3W. Un terme BOOLEEN (copie de DoomSiren) rendrait
    # 0/W/W/W -- c'est le seul controle offline qui separe les deux formes.
    voisins = [(3, 4), (3, 2), (4, 3), (4, 2), (2, 3), (2, 2)]   # les 6 voisins de (3,3)
    for n in range(4):
        c = _fake_ctx(wt, units=wf_units, epos=voisins[:n])
        v = wf.calculate_custom_utility(c, (2, 3), 200, 1227)
        if v != n * wwf:
            fails.append(f"HeavyWarpFlamer {n} voisin(s): attendu {n * wwf}, obtenu {v}")
    # ancre sur la CIBLE, pas sur la tuile d'attaque (comme DoomSiren, contrairement a Drachnyen)
    if wf.calculate_custom_utility(
            _fake_ctx(wt, units=wf_units, epos=voisins[:2]), (8, 8), 200, 1227) != 2 * wwf:
        fails.append("HeavyWarpFlamer: terme ancre a tort sur la tuile d'attaque")
    # cible hors plateau / inconnue -> pas de terme invente
    if wf.calculate_custom_utility(_fake_ctx(wt, units=[], epos=voisins), (0, 0), 999, 1227) != 0.0:
        fails.append("HeavyWarpFlamer (cible inconnue): attendu 0.0")

    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("OK: ArmoriumCherub=1 ; LightOfSanguinius=2*W(", w, ")=", expected,
          "; Drachnyen 2adj=", v2, "/1adj=", v1, "; Herald far=", v_far, "/near=", v_near,
          "; DoomSiren adj=", v_adj, "/isolee=", v_alone, "(W_overkill=", wok, ")",
          "; SavageEchoes 49.64%=0 / 50.19%=", wse, "(seuil", thr, "%)",
          "; HeavyWarpFlamer lineaire 0/W/2W/3W avec W=", wwf,
          "; dispatch 1014/1177/1020/1029/1199/1227/1230 OK ; 1100 non enregistree OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
