"""GARDES #894 -- LA VOIE DU GAMECONFIG NE DIT PAS L'ENUM : le routage se fait PAR NOM.

LE VERROU QUE CE FICHIER GARDE. `catalog_inject.synthesize` resolvait `passiveAbilities` par
`triggered_ability_id` et `activeAbilities` par `active_ability_id` -- « la VOIE dit l'enum ».
Deux entrees du gameconfig contredisent cette equation et l'une rendait `admecBossBelisarius`
INMONTABLE (`KeyError: TriggeredAbilityType.ShroudPsalm inconnu du build courant`).

CE QUE LE NATIF FAIT, LU (`Idun.Source.IdunBattle.View.BattleConfigBuilder$$SetupAbilities`) : il
itere UNE liste de `IdunMetaLogic.UserProgress.Model.UnitAbility` dont `+0x0c` porte
`activeAbilities.Contains(abilityId)` -- un HINT, pas une decision -- et resout le NOM :
  voie ACTIVE : `UnitAbility$$TryParseActiveAbilityType` ; sur ECHEC il TOMBE dans le chemin passif
  chemin PASSIF: `UnitAbility$$TryParseTriggeredAbilityType` ; sur ECHEC **rien n'est ajoute**
Le repli est donc ASYMETRIQUE : ACTIVE -> PASSIVE existe, PASSIVE -> ACTIVE **n'existe pas**.
C'est le point qu'une resolution croisee « symetrique » (essayer les deux enums) violerait.

Les quatre etages sont OFFLINE (aucun runner, aucun RPC). ASCII only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0].rstrip("\\/"))

import catalog_inject as C          # noqa: E402
import gameconfig as G              # noqa: E402

ACT = "IdunBattle.Entities.Enum.ActiveAbilityType"
TRI = "IdunBattle.Entities.Enum.TriggeredAbilityType"

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    # PERIMETRE DERIVE du role du fichier, pas prudentiel. Le verdict depend de TROIS entrees :
    #   * le routage lui-meme (`catalog_inject.route_configured_abilities` / `_ability_names`) ;
    #   * les deux tables d'enum du build (`data/symbols/<build>/frida/enums.tsv`) et le
    #     `gameconfig.json` qui les apparie -- une livraison de contenu peut creer un 3e nom mal
    #     range, ou en supprimer un ;
    #   * la capture `data/seed-bc.json`, qui EST le temoin de l'etage 4.
    # Une liste choisie de fichiers Python serait un FAUX VERT : le gisement vit dans les DONNEES.
    "chemins": ("scripts/python/catalog_inject.py", "scripts/python/gameconfig.py",
                "scripts/python/symbols_layout.py",
                "data/symbols/*/frida/enums.tsv", "data/symbols/*/gameconfig.json",
                "data/symbols/*/BUILD", "data/seed-bc.json"),
    # Le build EST une entree du verdict : les deux enums et le gameconfig sont per-build, et
    # c'est precisement une mise a jour qui peut creer (ou dissoudre) un nom mal range.
    "build": True,
    "toujours": False,
    "raison": ("Le verdict depend du ROUTAGE (`catalog_inject`) ET des DONNEES per-build : "
               "les deux tables d'enum, le gameconfig vivant, et la capture `data/seed-bc.json` "
               "qui est le TEMOIN de l'etage 4. Une livraison de contenu peut faire apparaitre "
               "un 3e nom mal range sans qu'aucun fichier Python ne bouge."),
}


def _all_unit_ids():
    cfg = G._cfg()["units"]
    out = []
    for kind in ("lineup", "npc", "summons"):
        out += list((cfg.get(kind) or {}).keys())
    return out


# --------------------------------------------------------------------- etage 1 : l'INVARIANT
#
# Ce qui est exigible n'est PAS « exactement deux noms mal ranges » (ce compte bouge avec le
# gameconfig, donc un test dessus serait un faux rouge a la prochaine livraison de contenu) --
# c'est que TOUT porteur du gameconfig se synthetise. C'est l'invariant que le verrou brisait.

def test_894_etage1_toute_unite_du_gameconfig_se_synthetise():
    ids = _all_unit_ids()
    assert len(ids) > 100, "recensement degenere : %d unites -- un test vide passerait pour vert" % len(ids)
    fautes = []
    for uid in ids:
        try:
            C.synthesize(uid)
        except Exception as exc:                                  # pragma: no cover - diagnostic
            fautes.append((uid, type(exc).__name__, str(exc)[:120]))
    assert not fautes, "synthesize LEVE sur %d unite(s) : %s" % (len(fautes), fautes[:5])


def test_894_etage1_belisarius_monte_ses_trois_actives():
    """Le porteur qui a revele le verrou -- nomme, pas noye dans l'etage precedent."""
    e = C.synthesize("admecBossBelisarius")
    act = C.enum_map(ACT)
    attendu = [act["InvocationOfMachineVengeance"], act["ArcScourge"], act["SolarAtomizer"]]
    assert e["ActiveAbilities"] == attendu, e["ActiveAbilities"]
    tri = C.enum_map(TRI)
    assert e["PassiveAbilities"] == [tri["SelfRepairMechanismReworked"],
                                     tri["PreCalibratedPurgeSolution"]], e["PassiveAbilities"]
    # `ShroudPsalm` est un `ActiveAbilityType` ecrit en `passiveAbilities` : le natif l'ABANDONNE
    # (pas de repli PASSIVE -> ACTIVE). Et son ordinal, lui, est un membre VALIDE de l'autre enum
    # -- l'ecrire dans `PassiveAbilities` monterait un passif ETRANGER, sans la moindre erreur.
    assert act["ShroudPsalm"] not in e["PassiveAbilities"]
    assert C.route_configured_abilities(G.unit("admecBossBelisarius"))["dropped"] == \
        [("ShroudPsalm", "passiveAbilities")]


# ------------------------------------------------- etage 2 : l'ASYMETRIE du repli, sur du SYNTHETIQUE
#
# Sur des `gc` fabriques : la REGLE reste gardee meme si le gameconfig cesse un jour de porter un
# cas reel. Les noms utilises sont RE-DERIVES des tables d'enum du build (pas ecrits en dur).

def _un_nom(dans, pas_dans):
    for n in sorted(dans):
        if n not in pas_dans:
            return n
    raise AssertionError("aucun nom exclusif -- les deux enums seraient identiques")


def test_894_etage2_repli_actif_vers_passif_existe():
    act, tri = C.enum_map(ACT), C.enum_map(TRI)
    nom = _un_nom(tri, act)                    # TriggeredAbilityType SEUL, ecrit en voie ACTIVE
    r = C.route_configured_abilities({"activeAbilities": [nom], "passiveAbilities": []})
    assert r["ActiveAbilities"] == []
    assert r["PassiveAbilities"] == [tri[nom]], r
    assert r["dropped"] == []


def test_894_etage2_repli_passif_vers_actif_N_EXISTE_PAS():
    act, tri = C.enum_map(ACT), C.enum_map(TRI)
    nom = _un_nom(act, tri)                    # ActiveAbilityType SEUL, ecrit en voie PASSIVE
    r = C.route_configured_abilities({"activeAbilities": [], "passiveAbilities": [nom]})
    assert r["ActiveAbilities"] == [], "le natif n'a AUCUN repli PASSIVE -> ACTIVE : %r" % (r,)
    assert r["PassiveAbilities"] == []
    assert r["dropped"] == [(nom, "passiveAbilities")], r


def test_894_etage2_ordre_actives_puis_passives():
    """`UnitProgression$$GetAllAbilities` = GetAbilities(isActive:true) PUIS (isActive:false)."""
    act, tri = C.enum_map(ACT), C.enum_map(TRI)
    a1, a2 = sorted(n for n in act if n not in tri)[:2]
    p1, p2 = sorted(n for n in tri if n not in act)[:2]
    r = C.route_configured_abilities({"activeAbilities": [a2, a1], "passiveAbilities": [p2, p1]})
    assert r["ActiveAbilities"] == [act[a2], act[a1]], r
    assert r["PassiveAbilities"] == [tri[p2], tri[p1]], r


# ------------------------------------------------------------ etage 3 : LE MUTANT DOIT MORDRE
#
# Contre-epreuve : on DESARME la resolution croisee (on remet « la voie dit l'enum ») et on exige
# que l'etage 1 ROUGISSE. Sans elle, un etage 1 vert ne prouve rien -- il pourrait etre vert parce
# que rien ne le contraint.

def _regle_par_la_voie(gc: dict) -> dict:
    """L'ANCIENNE regle, telle qu'elle etait ecrite avant #894 -- volontairement infidele."""
    return {
        "ActiveAbilities": [C.active_ability_id(a) for a in (gc.get("activeAbilities") or [])],
        "PassiveAbilities": [C.triggered_ability_id(a) for a in (gc.get("passiveAbilities") or [])],
        "dropped": [],
    }


def test_894_etage3_contre_epreuve_le_mutant_mord(monkeypatch):
    # (a) la mutation a bien MORDU : le symbole substitue est celui que `synthesize` appelle.
    #     `synthesize` fait `route_configured_abilities(gc)` -- une lecture du global du MODULE,
    #     donc `setattr` sur le module mord (forme B, cf. CLAUDE.md).
    monkeypatch.setattr(C, "route_configured_abilities", _regle_par_la_voie)
    assert C.route_configured_abilities is _regle_par_la_voie

    # (b) l'etage 1 ROUGIT : au moins un porteur du gameconfig cesse de se synthetiser.
    fautes = []
    for uid in _all_unit_ids():
        try:
            C.synthesize(uid)
        except KeyError as exc:
            fautes.append((uid, str(exc.args[0])[:80]))
    assert fautes, ("le mutant est INERTE : desarmer la resolution croisee ne casse RIEN, donc "
                    "l'etage 1 ne prouvait rien")
    porteurs = {uid for uid, _ in fautes}
    assert "admecBossBelisarius" in porteurs, porteurs
    assert "eldarBossMauganRaUltra" in porteurs, porteurs


# ------------------------------------------------- etage 4 : le TEMOIN, et qu'il DISCRIMINE
#
# `BC.Abilities.ActiveAbilities` / `.PassiveAbilities` sont des `Dictionary<<enum>, ...>` cote
# natif (`AbilitiesConfiguration$$GetActive` / `$$GetPassive`), donc une cle qui ne parse pas fait
# LEVER `EnumUtils$$ParseEnum` a la relecture du BC. La capture ECRITE PAR LE JEU le confirme --
# et le temoin DISCRIMINE : sur le MEME fichier, les deux noeuds keyes par string libre portent
# des cles hors enum. Un temoin qui rendrait 0 partout ne prouverait rien.

def _seed_abilities():
    p = Path(C.ROOT) / "data" / "seed-bc.json"
    if not p.exists():                                            # pragma: no cover - montage
        pytest.skip("seed BC absent : %s" % p)
    return json.loads(p.read_text(encoding="utf-8")).get("Abilities") or {}


def test_894_etage4_temoin_noeuds_types_et_son_discriminant():
    ab = _seed_abilities()
    act, tri = C.enum_map(ACT), C.enum_map(TRI)
    for noeud, table in (("ActiveAbilities", act), ("PassiveAbilities", tri)):
        keys = list((ab.get(noeud) or {}).keys())
        assert len(keys) > 50, "noeud %s degenere (%d cles)" % (noeud, len(keys))
        hors = [k for k in keys if k not in table]
        assert not hors, "%s porte %d cle(s) hors enum : %s" % (noeud, len(hors), hors[:5])
    # LE DISCRIMINANT : si le temoin rendait 0 partout, il ne mesurerait pas le typage.
    libres = [k for k in (ab.get("EnvironmentAbilities") or {}) if k not in tri]
    assert libres, ("temoin NON discriminant : aucun noeud de ce BC ne porte de cle hors enum, "
                    "donc le 0 des deux noeuds types ne prouve rien")


def test_894_etage4_les_cles_derivees_sont_valides_pour_leur_noeud():
    """`_ability_names` alimente `BC.Abilities` : chaque nom doit parser dans SON noeud."""
    act, tri = C.enum_map(ACT), C.enum_map(TRI)
    fautes = []
    n_act = n_pas = 0
    for uid in _all_unit_ids():
        a, p = C._ability_names(uid)
        n_act += len(a)
        n_pas += len(p)
        fautes += [(uid, "ActiveAbilities", n) for n in a if n not in act]
        fautes += [(uid, "PassiveAbilities", n) for n in p if n not in tri]
    assert n_act > 100 and n_pas > 100, "recensement degenere (%d/%d)" % (n_act, n_pas)
    assert not fautes, "cle(s) qui feraient LEVER EnumUtils$$ParseEnum : %s" % (fautes[:5],)
