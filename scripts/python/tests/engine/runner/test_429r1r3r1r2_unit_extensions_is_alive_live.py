"""#429-r1-r3-r1-r1 + -r2 -- le canal `unitsNotAlive` BRANCHE, et `UnitExtensions$$IsAlive` PORTE.

CE QUI EST GARDE ICI, ET EN QUOI CE N'EST PAS #429-r1-r3-r1
-----------------------------------------------------------
#429-r1-r3-r1 a ferme le PERIMETRE du gate de MESSAGE et mesure la divergence FLED ; il l'a
laissee OUVERTE, gardee par ATTRIBUTION, sur deux points nommes :

1. **LE CANAL.** `combatSnapshot.units` n'enumere que les unites VIVANTES au sens
   d'`IdunBattle.Entities.UnitExtensions$$IsAlive` : une ENFUIE (PV PLEINS) en est absente, donc
   son `UnitFlag.Fled` n'atteignait le port par AUCUNE voie. Le bloc additif `unitsNotAlive` est
   desormais deploye ; ce qui est garde ici est qu'il est LU **et** que son ABSENCE reste
   DETECTABLE -- `snapshot.get(...) or []` rendait la meme chose pour « lu, aucune entite non
   vivante » et pour « le bundle n'a pas le champ ».

2. **LE SERVICE.** Le port n'avait AUCUN mirror d'`UnitExtensions$$IsAlive` : ses lecteurs
   appelaient `IdunBattle.Entities.Components.HealthComponent$$IsAlive` (hp >= 1). Le natif teste
   TROIS choses -- `UnitFlagsComponent.Has(6 = UnitFlag.Dead)`, l'appartenance au pool
   `EntityPool.AliveUnits` (0), puis seulement `HealthComponent.IsAlive`.

CHIFFRES MESURES (build `rnca9r7q6c`, board MC1_67, seed 777, 2026-08-05) :
  * l'ENFUI est **hors** de `combatSnapshot.units` et **dans** `unitsNotAlive` ; ses flags natifs
    sont **[9, 26]** (`Fled`, `Removed`) et **PAS 6** (`Dead`), a `hp = 1000/1000`. Ni les PV ni
    le flag `Dead` ne peuvent donc expliquer le refus natif : la branche qui mord est le POOL.
  * les deux etages du port, SEPARES sur le meme etat : `HealthComponent.IsAlive` -> **True**,
    `UnitExtensions.IsAlive` -> **False**.
  * natif sur l'enfui : **0** evenement (temoin cible vivante : **2**, groupe `User_UseAbility`).
  * port : refus nominal ; gate de MESSAGE seul neutralise -> refus **ENCORE** (gate d'OPERATION,
    la morsure de -r2) ; les DEUX neutralises -> **10 375** degats. Avant cette tranche, le
    deuxieme bras frappait deja.

LIVE-agreement, ASCII only. Cf. docs/rl/case-429r1r3r1r2-unit-extensions-is-alive.md.
"""
from __future__ import annotations

import pytest

import probe_429r1r3r1_message_gate_perimeter as P
import probe_429r1r3r1r2_unit_extensions_is_alive as Q

STREAM_GROUP_USER_USE_ABILITY = P.STREAM_GROUP_USER_USE_ABILITY
FLED_SEEDS = ("777", "31337", "123")


@pytest.fixture(scope="module")
def fled(live_session, tmp_path_factory):
    """Le regime FLED. La fuite est un TIRAGE (`BattleFatigue` : `chance` 10 / `chance_2` 40 en
    overkill) mais son issue est DETERMINISTE PAR SEED -- la sequence d'actions du montage est
    fixe, donc le flux MT aussi. MESURE : 777 -> 2 fuites, 31337 -> 0, 123 -> 0. La liste est un
    REPLI en cas de derive du flux, pas une loterie relancee jusqu'au vert : ce qui est rejoue est
    la PRODUCTION de l'etat, jamais la mesure. Aucun seed => `fail`, jamais un skip (#455)."""
    tentatives = []
    for i, seed in enumerate(FLED_SEEDS):
        sf = tmp_path_factory.mktemp("t429r1r3r1r2f%d" % i) / "state.json"
        r = Q.volet_fled(str(sf), seed=seed, board="MC1_67", essais=2, verbose=False)
        tentatives.append({"seed": seed, "roulements": r.get("roulements"),
                           "why": r.get("why") or ""})
        if not r.get("why"):
            r["seed_retenu"] = seed
            r["tentatives"] = tentatives
            return r
    pytest.fail("montage FLED non installe sur AUCUN seed %s : %s" % (list(FLED_SEEDS), tentatives),
                pytrace=False)


# --------------------------------------------------------------- 1. LE PERIMETRE DU MIRROR (OFFLINE)
def test_le_service_natif_est_porte_UNE_fois_et_ses_deux_lecteurs_passent_par_lui():
    """OFFLINE. Un service natif duplique est la cause racine de plusieurs divergences vecues ici :
    le mirror existe une seule fois, et les DEUX sites dont le decompile appelle litteralement
    `UnitExtensions$$IsAlive` passent par lui. La contre-epreuve est INTEGREE et porte sur des
    NOMS : `is_alive_and_not_fled` doit continuer a NE PAS l'appeler -- son propre decompile
    (`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled`) va chercher
    `HealthComponent$$IsDead`, jamais ce service. Sans cette moitie, le test ne dirait rien du
    fork inverse (router trop large)."""
    r = Q.volet_scan(verbose=False)
    assert r["mirror_existe"] is True, "`unit_extensions_is_alive` doit exister dans `components`"
    assert r["flag_dead"] == 6, (
        "`UnitFlag.Dead` vaut 6 dans `data/symbols/<build>/frida/enums.tsv` -- obtenu %s"
        % r["flag_dead"])
    for nom in Q.SITES_ROUTES:
        assert r["route_%s" % nom] is True, (
            "`%s` porte un site dont le decompile appelle `UnitExtensions$$IsAlive` : il doit "
            "passer par le mirror, pas par `HealthComponent$$IsAlive`" % nom)
    for nom in Q.SITES_NON_ROUTES:
        assert r["non_route_%s" % nom] is True, (
            "`%s` ne porte PAS un appel natif a `UnitExtensions$$IsAlive` -- le router y "
            "fabriquerait un refus que le natif ne fait pas" % nom)


# --------------------------------------------------------------- 2. LE TRI-ETAT DU CANAL (OFFLINE)
def test_l_absence_du_bloc_unitsNotAlive_est_NOMMEE_et_ne_se_confond_pas_avec_un_zero():
    """OFFLINE, et c'est LE garde du volet -r1. Trois etats NOMMES (`lu` / `muet` / `absent`), et
    aucun chemin ne fabrique un `0` : un `absent` rabattu sur `[]` se lit « aucune unite non
    vivante », donc « aucune fuite » -- exactement le silence par lequel `UnitFlag.Fled` est reste
    hors d'atteinte du port pendant que son gate etait pourtant arme."""
    r = Q.volet_trietat(verbose=False)
    assert r["absent_canal"] == "absent" and r["absent_nb"] is None, (
        "bundle Frida ANTERIEUR au correctif : le canal doit se DIRE absent, obtenu (%s, %s)"
        % (r["absent_canal"], r["absent_nb"]))
    assert r["muet_canal"] == "muet" and r["muet_nb"] is None, (
        "champ present mais `null` (capteur non resolu) : `muet`, jamais un compte")
    assert r["lu_vide_canal"] == "lu" and r["lu_vide_nb"] == 0, (
        "champ LU et vide : c'est un `0` MESURE, et il doit se distinguer des deux ci-dessus")
    assert r["aucun_zero_fabrique"] is True, (
        "un canal NON mesure ne doit JAMAIS rendre 0 -- meme regle que `host_inputs.py`")
    assert r["lu_enfuie_flags_de_l_enfuie"] == [9], (
        "le bloc `unitsNotAlive` doit POSER les flags qu'il porte, sinon le lecteur est inerte")


# --------------------------------------------------------------- 3. LE CANAL, EN LIVE
def test_l_enfui_est_hors_des_unites_VIVANTES_et_dans_le_bloc_unitsNotAlive(fled):
    """LA CAUSE RACINE, mesuree. Le filtre alive-only de `combatSnapshot` rendait le canal
    STRUCTURELLEMENT aveugle a cette unite-la : PV pleins, mais absente du bloc `units`."""
    assert fled["canal_unitsNotAlive"] == "lu", (
        "le bundle Frida charge ne publie pas `unitsNotAlive` (%s) -- cette tranche exige le "
        "capteur deploye" % fled["canal_unitsNotAlive"])
    assert fled["enfui_dans_units_vivantes"] is False, (
        "prealable : si l'enfui etait dans `units`, le canal n'aurait jamais ete aveugle et il n'y "
        "aurait rien a garder ici")
    assert fled["enfui_dans_unitsNotAlive"] is True, (
        "l'enfui doit etre publie par le bloc additif, obtenu %s" % fled["enfui_dans_unitsNotAlive"])
    assert fled["port_unit_flags_seed"]["units_not_alive_channel"] == "lu"
    assert fled["port_unit_flags_seed"]["units_not_alive"] == fled["nb_unitsNotAlive"], (
        "le port doit ENREGISTRER ce qu'il a lu, pas un compte devine -- obtenu %s vs %s"
        % (fled["port_unit_flags_seed"], fled["nb_unitsNotAlive"]))
    assert fled["port_voit_le_flag_fled"] is True, (
        "`UnitFlag.Fled` doit desormais atteindre le port")


def test_la_branche_qui_MORD_est_le_POOL_ni_les_PV_ni_le_flag_Dead(fled):
    """L'ATTRIBUTION, et elle est LUE, pas deduite. `IsAlive` a trois branches ; deux d'entre elles
    sont directement observables sur cet etat et sont FAUSSES comme explication :
      * les PV sont PLEINS -> `HealthComponent.IsAlive` est vrai ;
      * le flag `Dead` (6) n'est PAS pose -- les flags natifs de l'enfui sont publies.
    Reste la troisieme : l'appartenance au pool `EntityPool.AliveUnits`. C'est ce que
    `IdunBattle.Operations.FleeOperation$$Execute` change, et rien d'autre ici."""
    assert fled["enfui_hp"] and fled["enfui_hp"] > 0, (
        "l'enfui doit garder ses PV -- sinon le regime se confond avec la MORT")
    assert fled["branche_flag_dead"] is False, (
        "le flag `UnitFlag.Dead` (6) ne doit PAS etre pose sur un enfui -- s'il l'est, "
        "l'attribution de cette tranche est a re-lire (flags lus : %s)" % fled["enfui_flags_natifs"])
    assert fled["branche_flag_fled"] is True, (
        "le flag `UnitFlag.Fled` (9) doit l'etre -- flags lus : %s" % fled["enfui_flags_natifs"])
    assert fled["enfui_alive_decisionview"] is False, (
        "`UnitExtensions.IsAlive` (le canal `decisionView.units[].alive`) doit rendre FAUX")


# --------------------------------------------------------------- 4. LES DEUX ETAGES DU PORT
def test_les_deux_mirrors_de_liveness_du_port_DIVERGENT_sur_cet_etat(fled):
    """LE POINT DE -r2. Sur le MEME etat, les deux fonctions natives ne disent PAS la meme chose --
    et c'est precisement pour ca qu'il en faut deux. Un port qui n'a que celle des PV voit une
    unite VIVANTE ET INTACTE la ou le natif ne voit plus rien sur le plateau."""
    assert fled["port_health_is_alive"] is True, (
        "`HealthComponent$$IsAlive` doit rendre VRAI (hp %s) -- sinon le regime n'est pas celui "
        "qu'on croit" % fled["port_hp"])
    assert fled["port_unit_extensions_is_alive"] is False, (
        "`UnitExtensions$$IsAlive` doit rendre FAUX : le porteur de la branche POOL est "
        "`UnitComponent.alive` (%s)" % fled["port_uc_alive"])
    assert fled["port_uc_alive"] is False
    assert fled["port_voit_le_flag_dead"] is False, (
        "aucun flag `Dead` cote port non plus -- le port lit bien les MEMES flags que le natif")


def test_IsDead_du_port_exclut_toujours_expressement_le_flag_Fled(fled):
    """NON-REGRESSION DE FIDELITE. `IdunBattle.Entities.UnitExtensions$$IsDead` = `!IsAlive(u,
    state) && !HasFlag(u, 9)`. Router `IsAlive` sur le bon service ne doit PAS transformer un
    enfui en mort : les deux predicats restent non complementaires, et c'est ce qui rend le regime
    FLED discriminant entre les deux etages."""
    assert fled["port_unit_is_dead"] is False, (
        "un ENFUI n'est pas MORT au sens de `IsDead` -- obtenu %s" % fled["port_unit_is_dead"])
    assert fled["port_is_alive_and_not_fled"] is False, (
        "mais il n'est pas `IsAliveAndNotFled` non plus -- c'est le gate de MESSAGE")


# --------------------------------------------------------------- 5. L'ACCORD, ETAGE PAR ETAGE
def test_le_temoin_prouve_que_le_capteur_d_etage_est_arme(fled):
    """Un « 0 evenement » n'est interpretable que confronte a un bras dont on SAIT qu'il ouvre le
    groupe de stream `User_UseAbility`."""
    t = fled["temoin_cible_vivante"]
    assert t is not None and t["events"] and t["events"] > 0, (
        "temoin : cible VIVANTE, le pipeline doit produire des evenements, obtenu %s" % t)
    assert STREAM_GROUP_USER_USE_ABILITY in (t["groups"] or [])


def test_le_natif_refuse_l_enfui_et_le_port_aussi(fled):
    """L'ACCORD, sur l'etat que la tranche precedente ne pouvait garder que par attribution."""
    n = fled["natif_sur_enfui"]
    assert n["events"] == 0 and n["groups"] == [] and n["action_consumed"] is False, (
        "natif sur enfui : 0 evenement, aucun groupe -- obtenu %s" % n)
    assert fled["port_attaque_nominal"] is None, (
        "port : aucun coup ne doit partir sur l'enfui, obtenu %s" % fled["port_attaque_nominal"])
    assert fled["port_cast_nominal"].get("not_alive_and_not_fled") == "target", (
        "port : refus au rang MESSAGE attendu, obtenu %s" % fled["port_cast_nominal"])


def test_le_gate_d_OPERATION_prend_le_relais_quand_celui_du_MESSAGE_tombe(fled):
    """LA MORSURE DE -r2, et le seul bras qui l'isole. Le gate de MESSAGE neutralise, c'est
    `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` qui doit
    refuser -- il appelle `UnitExtensions$$IsAlive` au decompile. AVANT cette tranche il appelait
    `HealthComponent$$IsAlive`, voyait `hp = 1000` et laissait passer : le port frappait alors
    l'enfui pour 10 375."""
    assert fled["port_attaque_sans_gate_message"] is None, (
        "gate de MESSAGE neutralise : le gate d'OPERATION doit refuser l'enfui -- obtenu %s"
        % fled["port_attaque_sans_gate_message"])
    assert fled["port_cast_sans_gate_message"].get("dead_target_not_allowed") is True, (
        "et le refus doit etre ATTRIBUE au gate cible-morte, pas a autre chose -- obtenu %s"
        % fled["port_cast_sans_gate_message"])


def test_la_mutation_MORD_les_DEUX_gates_tombes_le_port_frappe(fled):
    """CONTRE-EPREUVE. Sans elle, les deux refus ci-dessus pourraient venir d'un montage inerte ou
    d'une substitution qui ne matche pas. On neutralise AUSSI le gate d'operation : le port doit
    frapper, et frapper l'ENFUI -- c'est la valeur qu'il produisait avant le fix."""
    d = fled["port_attaque_sans_les_deux"]
    assert d and d.get("total") and d["total"] > 0, (
        "les deux gates neutralises : le port doit frapper l'enfui, obtenu %s" % d)
    assert d.get("target") == fled["fled_id"], (
        "et c'est bien l'ENFUI qui encaisse -- obtenu %s" % d)
    assert (fled["port_cast_sans_les_deux"] or {}).get("dead_target_not_allowed") is None, (
        "le cast aussi doit passer une fois les deux gates tombes, obtenu %s"
        % fled["port_cast_sans_les_deux"])
