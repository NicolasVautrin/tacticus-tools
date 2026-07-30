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
- Chronometron (1226) IdunBattle.AI.Playbook.Loki.ChronometronPlaybook$$CalculateCustomUtility =
  W(Chronometron_AffectedEnemies)=10 * COMPTE des ennemis du disque `constants.range` autour de la
  position REELLE du caster (centre exclu). Route NON-ATTAQUE (`engine/playbook/nonattack.py`) :
  l'ability n'a pas de `damageProfile` et n'atteint donc jamais `_best_attack` -- la garde verifie
  aussi sa presence dans `NONATTACK_PLAYBOOKS`, sans quoi le terme serait INERTE.
- Stikkbomb (1051) IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$CalculateCustomUtility =
  `-n x U(1 coup sur la CIBLE)` ou n = nb d'AMIS du caster adjacents a la CIBLE. Seule la SELECTION
  du sous-set est gardee ici (la valeur exige une Scene -> `test_stikkbomb_decision_live.py`) :
  les ENNEMIS adjacents sont EXCLUS du compte ami, le CASTER lui-meme est INCLUS s'il est adjacent
  (`IsFriend(caster, caster)` est vrai), cible inconnue -> 0.
- SorcerousFacade (1100) IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$CalculateCustomUtility =
  Tile(tuile de la CIBLE) - Tile(tuile candidate), donc `u_full` = Tile(tuile de la CIBLE) : le terme
  de la tuile candidate s'ANNULE (c'est la tuile de l'allie que le caster occupera apres l'echange).
  Route ALLIEE via `NONATTACK_PLAYBOOKS` (l'ability est absente de `plans` -- veto #217).
  CLIQUET DE NON-REGRESSION #217 : `_is_attack_ability(1100)` doit rester False et `_ability_kind`
  doit rester 'ally', sinon la route ENNEMIE (les actions FANTOMES) se rouvre.

Usage : python probe_custom_utility_27.py   (depuis scripts/python ; ASCII only ; exit 0 = OK)
"""
from __future__ import annotations

import sys
import types

import engine.playbook as pb
import engine.weights as W


def _fake_ctx(wt, **kw):
    d = dict(me={"team": 1, "id": 100}, units=[], obs_units=[], epos=[], elev_by_pos={}, wt=wt,
             uid=100, plans={}, normal_ids={69}, hp_cur_by_id={}, hpmax_by_id={},
             origin=None,
             # champs consommes par le composite Tile(7) et par la route non-attaque (1100) :
             # neutres pour tous les autres cas de ce probe. `fpos` sert aussi au sous-set de
             # Stikkbomb (1051) : les AMIS adjacents a la cible.
             is_temporary_by_pos={}, effects_by_pos={}, terrain_by_pos={}, fpos=[], enemies=[],
             reach_nc=[], scene=None, ab_name_by_id={})
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
                      (1227, "HeavyWarpFlamerPlaybook"), (1185, "ForwardObserversPlaybook"),
                      (1051, "StikkbombPlaybook")):
        got = type(reg.get(aid)).__name__
        if got != name:
            fails.append(f"dispatch {aid}: attendu {name}, obtenu {got}")
    # SorcerousFacade (1100) : le cliquet a CHANGE DE SENS (#27-4e). Elle DOIT etre enregistree,
    # et sur la route ALLIEE (`NONATTACK_PLAYBOOKS`) -- surtout pas sur la route ennemie.
    from engine.playbook.nonattack import NONATTACK_PLAYBOOKS
    if type(reg.get(1100)).__name__ != "SorcerousFacadePlaybook":
        fails.append(f"dispatch 1100: attendu SorcerousFacadePlaybook, obtenu "
                     f"{type(reg.get(1100)).__name__}")
    if 1100 not in NONATTACK_PLAYBOOKS:
        fails.append("SorcerousFacade (1100) absente de NONATTACK_PLAYBOOKS : la seule route qui "
                     "lui donne des cibles ALLIEES -> le terme serait INERTE")
    # CLIQUET DE NON-REGRESSION #217 : le masque 0x402 (TargetIsFriendly|TargetMatchesDynamicRule)
    # doit continuer de VETO-er la route ENNEMIE. Si `_is_attack_ability` redevenait True, 1100
    # reprendrait des cibles ennemies dans `_plans_for_unit` -- l'action FANTOME que #217 a fermee.
    from engine.ai.state_bridge import _ability_kind, _is_attack_ability, _resolve_ability
    _n1100, _cfg1100 = _resolve_ability(1100)
    if _is_attack_ability(1100, _cfg1100):
        fails.append("REGRESSION #217 : _is_attack_ability(1100) est True -> route ENNEMIE rouverte")
    if _ability_kind(1100, _n1100, _cfg1100) != "ally":
        fails.append(f"REGRESSION #217 : _ability_kind(1100) = "
                     f"{_ability_kind(1100, _n1100, _cfg1100)!r}, attendu 'ally'")

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

    # --- Stikkbomb (1051) : le SOUS-SET du custom = les AMIS du caster adjacents a la CIBLE.
    # La VALEUR du terme (`-n x U(1 coup sur la cible)`) exige une Scene et n'est donc pas gardee
    # ici -- c'est le role de `test_stikkbomb_decision_live.py`. Ce qui l'est, c'est la SELECTION,
    # c'est-a-dire tout le verrou 3 : qui entre dans le compte, qui n'y entre pas, et sur quoi il
    # est ancre. Le natif enumere `AdjacentUnits(Target)` (aucun filtre d'equipe) puis garde
    # `IsFriend(u, caster)` -- donc les ENNEMIS adjacents sont EXCLUS, et le CASTER lui-meme est
    # INCLUS s'il est adjacent a la cible (`IsFriend(caster, caster)` est vrai : meme joueur).
    sk = pb.get_playbook(1051)
    tgt_u = [{"id": 200, "team": 2, "alive": True, "pos": {"col": 3, "row": 3}},
             {"id": 100, "team": 1, "alive": True, "pos": {"col": 8, "row": 8}}]   # caster LOIN
    c_far = _fake_ctx(wt, units=tgt_u, fpos=[(3, 4), (3, 2)], epos=[(2, 3)])
    n_fr = sk._splash_count(c_far, 200, friends=True)
    n_fo = sk._splash_count(c_far, 200, friends=False)
    if n_fr != 2:
        fails.append(f"Stikkbomb amis adjacents a la cible: attendu 2, obtenu {n_fr}")
    if n_fo != 1:
        fails.append(f"Stikkbomb ennemis adjacents a la cible: attendu 1, obtenu {n_fo}")
    # ancrage CIBLE : la tuile d'attaque ne doit RIEN changer (contraste avec Drachnyen).
    if sk._splash_count(c_far, 200, friends=True) != sk._splash_count(c_far, 200, friends=True):
        fails.append("Stikkbomb: compte non deterministe")
    # le CASTER compte s'il est lui-meme adjacent a la cible (Stikkbomb est ranged r2, c'est
    # atteignable) -- `ctx.fpos` l'EXCLUT par construction, le port le re-ajoute explicitement.
    tgt_u2 = [{"id": 200, "team": 2, "alive": True, "pos": {"col": 3, "row": 3}},
              {"id": 100, "team": 1, "alive": True, "pos": {"col": 3, "row": 4}}]  # caster ADJACENT
    n_self = sk._splash_count(_fake_ctx(wt, units=tgt_u2, fpos=[], epos=[]), 200, friends=True)
    if n_self != 1:
        fails.append(f"Stikkbomb: le caster adjacent a la cible doit compter (attendu 1, obtenu {n_self})")
    # cible hors plateau / inconnue -> 0 (degradation fidele, aucun compte fantome)
    if sk._splash_count(_fake_ctx(wt, units=tgt_u, fpos=[(3, 4)]), 999, friends=True) != 0:
        fails.append("Stikkbomb: cible inconnue doit rendre 0")

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

    # --- Chronometron (1226) : W(10) * COMPTE d'ennemis dans le DISQUE `range` autour de la
    # position REELLE du caster (centre exclu). Route NON-ATTAQUE (`playbook/nonattack.py`) :
    # l'ability n'a pas de `damageProfile`, elle n'atteint jamais `_best_attack`.
    from engine.playbook.nonattack import NONATTACK_PLAYBOOKS
    wch = wt.sub("ActiveAbilities", "Chronometron_AffectedEnemies")
    if wch == 0:
        fails.append("Chronometron_AffectedEnemies absent des poids : la table `Utilities` n'a pas "
                     "ete re-synthetisee depuis le gameconfig courant "
                     "(cf. catalog_inject.refresh_ai_utilities)")
    if 1226 not in NONATTACK_PLAYBOOKS:
        fails.append("Chronometron (1226) absente de NONATTACK_PLAYBOOKS : sans la route non-attaque "
                     "le terme est INERTE (l'ability n'entre jamais dans `plans`)")
    ch = pb.get_playbook(1226)
    if type(ch).__name__ != "ChronometronPlaybook":
        fails.append("dispatch 1226: attendu ChronometronPlaybook, obtenu %s" % type(ch).__name__)
    else:
        rng = ch._range()
        # anneaux successifs autour de l'origine (0,0) : d=1 puis d=2 ; la 3e est a d=3 -> HORS.
        near = [(0, 1), (1, 0), (0, 2)]         # d = 1, 1, 2  -> dans le disque range=2
        far = (0, 3)                            # d = 3        -> hors
        for n in range(len(near) + 1):
            c = _fake_ctx(wt, origin=(0, 0), epos=list(near[:n]))
            v = ch.calculate_custom_utility(c, (0, 0), 100, 1226)
            if v != n * wch:
                fails.append(f"Chronometron {n} ennemi(s) dans le rayon: attendu {n * wch}, obtenu {v}")
        c_far = _fake_ctx(wt, origin=(0, 0), epos=[far])
        if ch.calculate_custom_utility(c_far, (0, 0), 100, 1226) != 0.0:
            fails.append("Chronometron: un ennemi a d=%d est compte a tort (range=%d)"
                         % (3, rng))
        # ANCRAGE : le terme ne doit PAS bouger avec la tuile candidate (surcharge 5-args de
        # `DSLSelectors$$SurroundingEnemies`, centre = ENTITE). Confronte live (bras `--anchor` de
        # `probe_27_4b_chronometron_ab.py`) : la variante ancree-tuile bascule sur 1226 la ou le
        # natif reste sur l'attaque normale.
        c2 = _fake_ctx(wt, origin=(0, 0), epos=[(0, 1), (1, 0)])
        if ch.calculate_custom_utility(c2, (8, 8), 100, 1226) != 2 * wch:
            fails.append("Chronometron: terme ancre a tort sur la tuile candidate")
        # le CENTRE est exclu (`- Tiles(unit)`)
        if ch.calculate_custom_utility(_fake_ctx(wt, origin=(0, 0), epos=[(0, 0)]),
                                       (0, 0), 100, 1226) != 0.0:
            fails.append("Chronometron: la tuile du caster est comptee (le `- Tiles(unit)` manque)")
        # gate self-cast `GetCasterNotAddedReason` : aucun ennemi a portee -> pas d'action
        if ch.is_caster_added(_fake_ctx(wt, origin=(0, 0), epos=[far]), (0, 0)):
            fails.append("Chronometron: caster ajoute sans ennemi a portee (gate 0x800 manquant)")
        if not ch.is_caster_added(_fake_ctx(wt, origin=(0, 0), epos=[(0, 2)]), (0, 0)):
            fails.append("Chronometron: caster refuse alors qu'un ennemi est a portee")
        # `ShouldExecute` (slot +0x328) = `return true` : une utilite NULLE ne doit pas gater
        if not ch.should_execute(_fake_ctx(wt), (0, 0), 100, 1226, 0.0):
            fails.append("Chronometron: ShouldExecute gate a 0 -- le slot +0x328 rend `true`")

    # --- ForwardObservers (1185) : DEUX termes de nature differente.
    #   custom = [aucun ENNEMI ne porte Markerlight(1122)] * W(EnemyHasNoMarkerlight = 200)
    #          + RemainingPercentage(CIBLE) * W(TargetHealthPercentage = 40)
    # Le 1er est BOOLEEN et GLOBAL (`CheckIfAnyEnemyHasMarkerLight` boucle sur
    # `GetAllEnemiesOf(joueur du caster)` et `break` au premier), le 2nd est LINEAIRE dans le RATIO
    # de PV de la cible (`FillUpStatComponent$$RemainingPercentage` = `max(0, cur/max)`, PAS un
    # pourcentage arrondi). Route NON-ATTAQUE, comme Chronometron.
    wfo_mk = wt.sub("ActiveAbilities", "ForwardObservers_EnemyHasNoMarkerlight")
    wfo_hp = wt.sub("ActiveAbilities", "ForwardObservers_TargetHealthPercentage")
    if wfo_mk == 0 or wfo_hp == 0:
        fails.append("poids ForwardObservers_* absents : la table `Utilities` n'a pas ete "
                     "re-synthetisee depuis le gameconfig courant (catalog_inject.refresh_ai_utilities)")
    if 1185 not in NONATTACK_PLAYBOOKS:
        fails.append("ForwardObservers (1185) absente de NONATTACK_PLAYBOOKS : sans la route "
                     "non-attaque le terme est INERTE (pas de `damageProfile` -> jamais dans `plans`)")
    fo = pb.get_playbook(1185)
    if type(fo).__name__ != "ForwardObserversPlaybook":
        fails.append("dispatch 1185: attendu ForwardObserversPlaybook, obtenu %s" % type(fo).__name__)
    else:
        MK = 1122
        # `ctrl` (canal decisionView) porte l'appartenance : False = ennemi du caster, le predicat
        # exact de `BattleQuery$$GetAllEnemiesOf`.
        u_clean = [{"id": 100, "ctrl": True, "effects": [{"effectType": MK}]},   # ALLIE marque -> ignore
                   {"id": 200, "ctrl": False, "effects": []},
                   {"id": 201, "ctrl": False, "effects": [{"effectType": 9999}]}]
        u_marked = [{"id": 200, "ctrl": False, "effects": []},
                    {"id": 201, "ctrl": False, "effects": [{"effectType": MK}]}]
        hp_cur, hp_max = {200: 50, 201: 100}, {200: 100, 201: 100}
        c_clean = _fake_ctx(wt, units=u_clean, hp_cur_by_id=hp_cur, hpmax_by_id=hp_max)
        c_marked = _fake_ctx(wt, units=u_marked, hp_cur_by_id=hp_cur, hpmax_by_id=hp_max)
        if fo.any_enemy_has_markerlight(c_clean):
            fails.append("ForwardObservers: un ALLIE marque declenche le predicat -- le natif itere "
                         "`GetAllEnemiesOf`, pas toutes les unites")
        if not fo.any_enemy_has_markerlight(c_marked):
            fails.append("ForwardObservers: un ENNEMI marque ne declenche pas le predicat")
        # terme booleen + terme lineaire, cible a 50 % puis a 100 %
        got = fo.calculate_custom_utility(c_clean, (0, 0), 200, 1185)
        if got != wfo_mk + 0.5 * wfo_hp:
            fails.append("ForwardObservers (mk=0, cible 50%%): attendu %s, obtenu %s"
                         % (wfo_mk + 0.5 * wfo_hp, got))
        got = fo.calculate_custom_utility(c_clean, (0, 0), 201, 1185)
        if got != wfo_mk + 1.0 * wfo_hp:
            fails.append("ForwardObservers (mk=0, cible 100%%): attendu %s, obtenu %s"
                         % (wfo_mk + wfo_hp, got))
        # markerlight pose -> le terme BOOLEEN disparait, le terme de PV reste
        got = fo.calculate_custom_utility(c_marked, (0, 0), 200, 1185)
        if got != 0.5 * wfo_hp:
            fails.append("ForwardObservers (mk=1, cible 50%%): attendu %s, obtenu %s"
                         % (0.5 * wfo_hp, got))
        # LINEARITE stricte : 4 ratios -> 4 valeurs proportionnelles (un terme booleen les egaliserait).
        # C'est le pendant OFFLINE du bras A2 de `probe_27_4c_forwardobservers_ab.py`, ou le natif
        # REFUTE le modele constant sur un etat que les deux modeles departagent.
        for num in (0, 25, 60, 100):
            cc = _fake_ctx(wt, units=u_marked, hp_cur_by_id={200: num}, hpmax_by_id={200: 100})
            got = fo.calculate_custom_utility(cc, (0, 0), 200, 1185)
            if abs(got - (num / 100.0) * wfo_hp) > 1e-9:
                fails.append("ForwardObservers lineaire (cible %d%%): attendu %s, obtenu %s"
                             % (num, (num / 100.0) * wfo_hp, got))
        # PV max illisible -> le terme de PV s'eteint, le booleen reste (jamais de terme invente)
        c_nohp = _fake_ctx(wt, units=u_clean, hp_cur_by_id={}, hpmax_by_id={})
        if fo.calculate_custom_utility(c_nohp, (0, 0), 200, 1185) != wfo_mk:
            fails.append("ForwardObservers (PV illisibles): le terme de PV doit valoir 0")
        # `ShouldExecute` (slot +0x328) = `return true` -- MESURE sur CE playbook (#288)
        if not fo.should_execute(_fake_ctx(wt), (0, 0), 200, 1185, 0.0):
            fails.append("ForwardObservers: ShouldExecute gate a 0 -- le slot +0x328 rend `true`")
        # pas de self-cast (`isSelfCasting = 0` au ctor) -> aucun gate de caster invente
        if not fo.is_caster_added(_fake_ctx(wt, origin=(0, 0), epos=[]), (0, 0)):
            fails.append("ForwardObservers: gate self-cast applique alors que isSelfCasting = 0")

    # --- SorcerousFacade (1100), #27-4e ---------------------------------------------------------
    # `...SorcerousFacadePlaybook$$CalculateCustomUtility` = Tile(tuile de la CIBLE) - Tile(tuile
    # candidate). La garde verifie la formule ET sa consequence STRUCTURELLE : comme la route ajoute
    # ensuite `+ Tile(tuile candidate)`, l'utilite d'action porte EXACTEMENT Tile(tuile de la CIBLE)
    # -- c'est la tuile que le caster occupera apres l'echange de positions.
    from engine.playbook.base import tile_utility as _tileu
    sf = pb.get_playbook(1100)
    _u_allie = 200
    _units_sf = [{"id": 100, "team": 1, "alive": True, "pos": {"col": 0, "row": 0}},
                 {"id": _u_allie, "team": 1, "alive": True, "pos": {"col": 1, "row": 1}}]
    c_sf = _fake_ctx(wt, units=_units_sf, elev_by_pos={(0, 0): 0, (1, 1): 3, (2, 2): 1},
                     origin=(0, 0), reach_nc=[(0, 0), (2, 2)])
    _u_cible = _tileu(c_sf, (1, 1))
    for T in ((0, 0), (2, 2)):
        got = sf.calculate_custom_utility(c_sf, T, _u_allie, 1100)
        want = _u_cible - _tileu(c_sf, T)
        if abs(got - want) > 1e-9:
            fails.append(f"SorcerousFacade custom @{T}: attendu {want}, obtenu {got}")
        if abs((got + _tileu(c_sf, T)) - _u_cible) > 1e-9:
            fails.append(f"SorcerousFacade @{T}: le terme Tile de la tuile candidate ne s'annule pas "
                         f"(u_full doit valoir Tile(tuile de la CIBLE) = {_u_cible})")
    if sf.calculate_custom_utility(c_sf, (0, 0), _u_allie, 1100) == 0.0:
        fails.append("SorcerousFacade: terme NUL sur un board a elevation -> la garde ne garde rien")
    if sf.calculate_custom_utility(c_sf, (0, 0), 999, 1100) != 0.0:
        fails.append("SorcerousFacade: cible hors plateau -> le terme doit valoir 0 (GetMainTile)")
    # `ShouldExecute` (OVERRIDE du slot +0x328), branche `sel == null` (aucun ennemi attaquable a
    # l'attaque normale depuis la tuile candidate -> `plans` vide ici) : REFUS des qu'une tuile de
    # `GetCurrentAndMovableTilesOf` est MEILLEURE que celle de la cible.
    c_bad = _fake_ctx(wt, units=_units_sf, elev_by_pos={(0, 0): 0, (1, 1): 1, (2, 2): 5},
                      origin=(0, 0), reach_nc=[(0, 0), (2, 2)])
    if sf.should_execute(c_bad, (0, 0), _u_allie, 1100, 0.0):
        fails.append("SorcerousFacade ShouldExecute: accepte alors qu'une tuile atteignable a une "
                     "utilite de mouvement SUPERIEURE a celle de la tuile de la cible")
    c_ok = _fake_ctx(wt, units=_units_sf, elev_by_pos={(0, 0): 0, (1, 1): 5, (2, 2): 1},
                     origin=(0, 0), reach_nc=[(0, 0), (2, 2)])
    if not sf.should_execute(c_ok, (0, 0), _u_allie, 1100, 0.0):
        fails.append("SorcerousFacade ShouldExecute: refus alors que la tuile de la cible domine "
                     "toutes les tuiles atteignables")
    # `GetTarget` -> `SelectFirst` : l'ennemi valide de l'attaque NORMALE le plus proche de la
    # position REELLE du caster, restreint aux cibles legales DEPUIS la tuile candidate.
    _plans_sf = {100: {"evals": [
        {"abilityId": 69, "targetId": 81, "rankCount": 2,
         "ranked": [{"col": 0, "row": 0}, {"col": 2, "row": 2}]},          # loin  (d=4)
        {"abilityId": 69, "targetId": 79, "rankCount": 1,
         "ranked": [{"col": 2, "row": 2}]},                                # proche (d=1), tuile (2,2)
    ]}}
    _units_gt = _units_sf + [
        {"id": 79, "team": 2, "alive": True, "pos": {"col": 1, "row": 0}},
        {"id": 81, "team": 2, "alive": True, "pos": {"col": 4, "row": 0}}]
    c_gt = _fake_ctx(wt, units=_units_gt, elev_by_pos={(0, 0): 0, (1, 1): 3, (2, 2): 1},
                     origin=(0, 0), reach_nc=[(0, 0), (2, 2)], plans=_plans_sf)
    if sf._get_target(c_gt, (0, 0)) != 81:
        fails.append("SorcerousFacade GetTarget@(0,0): seule 81 est legale depuis cette tuile, "
                     f"obtenu {sf._get_target(c_gt, (0, 0))}")
    if sf._get_target(c_gt, (2, 2)) != 79:
        fails.append("SorcerousFacade GetTarget@(2,2): 79 est la PLUS PROCHE de la position reelle "
                     f"du caster, obtenu {sf._get_target(c_gt, (2, 2))}")
    if sf._get_target(c_gt, (7, 7)) is not None:
        fails.append("SorcerousFacade GetTarget: une tuile hors de tout `ranked` doit rendre None")

    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("OK: ArmoriumCherub=1 ; LightOfSanguinius=2*W(", w, ")=", expected,
          "; Drachnyen 2adj=", v2, "/1adj=", v1, "; Herald far=", v_far, "/near=", v_near,
          "; DoomSiren adj=", v_adj, "/isolee=", v_alone, "(W_overkill=", wok, ")",
          "; SavageEchoes 49.64%=0 / 50.19%=", wse, "(seuil", thr, "%)",
          "; HeavyWarpFlamer lineaire 0/W/2W/3W avec W=", wwf,
          "; Chronometron lineaire 0..3 dans le rayon", ch._range(), "avec W=", wch,
          "(ancre ENTITE, centre exclu, gate self-cast)",
          "; ForwardObservers W_mk=", wfo_mk, "+ pct*W_hp=", wfo_hp,
          "(predicat ENNEMIS-only, lineaire en pct)",
          "; SorcerousFacade custom = Tile(cible)-Tile(candidate) (u_full =", round(_u_cible, 4),
          "= Tile(cible)), ShouldExecute branche `sel==null` OK, GetTarget plus-proche OK,",
          "route ALLIEE (NONATTACK_PLAYBOOKS) + veto #217 INTACT",
          "; Stikkbomb sous-set amis/ennemis adjacents a la CIBLE = ", n_fr, "/", n_fo,
          "(caster inclus s'il est adjacent, cible inconnue -> 0)",
          "; dispatch 1014/1051/1177/1020/1029/1100/1185/1199/1226/1227/1230 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
