"""#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1 / -r2 / -r4-r1 -- les trois lectures de `GetRange` mirrorees.

Ce que ces crans gardent, et pourquoi chacun peut ROUGIR :

  1. **LE 3e CHAMP EST UN ALIAS EXACT** d'`options.Range.UseWholeBoard`, dans les DEUX regimes
     (caster avec tuile / sans tuile). Ce n'est pas un detail de style : c'est la propriete qui rend
     le mirror sur pour tout consommateur, present ou futur. Un `get_range` qui cesserait de la
     tenir signalerait une 4e sortie native non lue.
  2. **LES DEUX COURT-CIRCUITS RENDENT LE TRIPLET NATIF**, pas un `None`. Et le consommateur ne pose
     AUCUN refus dans ces deux regimes -- c'est la NON-REGRESSION : avant le mirror, ils sortaient
     par le `return None` global, et confondre les trois causes de `None` etait justement le vice.
  3. **`use_whole_board` DESARME LE GATE DE DISTANCE, ET IL LE DESARME DEPUIS LES OPTIONS.** Le
     natif teste `options.Range.UseWholeBoard`, pas le champ homonyme du `Range` rendu. Un cran
     MUTANT (options a `False`, `Range` rendu a `True`) verifie qu'on lit bien la bonne source.
  4. **LE REGIME D'ECART DU COURT-CIRCUIT `casterTiles` VIDE EST VIDE**, et c'est MESURE :
     22/22 masques `AllowNullCasterTile` portent `use_whole_board`, et les 22 unites `MachineOfWar`
     du gameconfig n'ont que ces actives-la. S'il rougit, une MoW a gagne une ability non-whole-board
     -> le gate de distance devient atteignable pour un caster SANS TUILE, et il faut CONFRONTER.
  5. **`GetStat(StatType.Range = 2)` EST OBSERVABLE** -- le catalogue `statTypes` de
     `combatSnapshot` apparie la cle `range` a l'index 2. Le cran LIVE le verifie et mesure la stat
     sur des unites SANS ARME (les MoW du pool). Un appariement qui bougerait ferait lire une cle
     homonyme, donc une valeur qui n'est pas celle du natif.
  6. **LA MACHINE OF WAR N'A AUCUNE TUILE** (`pos: null`, `feet: []`) -- le PORTEUR du court-circuit
     `-r2`, que la fiche declarait inexistant.

RE et mesures : `docs/rl/case-419-r1-tr14-r5-r2-r1-r2-r1-r1-only-adjacent-portee-non-observable.md`.
Probe jumeau : `probe_419r1tr14r5r2r1r2r1r1r1_court_circuits_getrange.py`. ASCII only.
"""
from __future__ import annotations

import dataclasses

import pytest

import probe_419r1tr14r5r2r1r2r1r1r1_court_circuits_getrange as P
from engine.entities.stats import StatType
from engine.runner.abilities import targeting as TGT
from engine.runner.abilities.targeting import Range
from engine.runner.abilities.targeting_rule import TargetingRule as TR

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: Les crans LIVE dependent en outre de l'etat du jeu (une MoW qui gagnerait une tuile, un
#: `combatSnapshot` qui cesserait de publier `stats.range`) : cela ne se derive d'aucun chemin, d'ou
#: `toujours: True` -- c'est un RESULTAT, pas un aveu.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/targeting.py",       # `Range`, `get_range`
        "scripts/python/engine/runner/abilities/targeting_rule.py",  # les bits lus ici
        "scripts/python/engine/entities/stats.py",                   # `StatType.RANGE`
        "scripts/python/probe_419r1tr14r5r2r1r2r1r1r1_court_circuits_getrange.py",
        "data/seed-bc.json",                                          # l'etage CATALOGUE
    ),
    # `True` : l'etage MODIFICATION lit `data/symbols/<build>/gameconfig.json` par un
    # `read_text` qu'aucun import ne revele -- exactement l'angle mort que `--proposer` signale.
    "build": True,
    "toujours": True,
    "raison": ("les crans LIVE interrogent le jeu (MoW sans tuile, catalogue `statTypes` de "
               "`combatSnapshot`, stat `range` resolue) -- aucun chemin du depot ne les borne."),
}


# ------------------------------------------------------------------------------------------------
# 1-2. Le champ ALIAS et les deux court-circuits (OFFLINE)
# ------------------------------------------------------------------------------------------------

def test_le_champ_use_whole_board_est_un_alias_exact_des_options():
    r = P.champ_alias()
    assert r["couples_balayes"] > 300, (
        "le balayage s'est vide (%d couples) -- un cran qui ne visite rien ne garde rien"
        % r["couples_balayes"])
    assert r["alias_exact"], (
        "le 3e champ du `Range` n'est plus l'alias d'`options.Range.UseWholeBoard` : %s"
        % r["ecarts"][:5])


def test_les_deux_court_circuits_rendent_le_triplet_natif_et_ne_posent_aucun_refus():
    r = P.court_circuits()
    assert r["whole_board"] > 0 and r["non_whole_board"] > 0, (
        "regime DEGENERE : il faut des masques des DEUX cotes pour que ce cran discrimine (%s)" % r)
    assert not r["ecarts_uwb"], (
        "le court-circuit `UseWholeBoard` ne rend plus `{1, false, true}` : %s" % r["ecarts_uwb"][:5])
    assert not r["ecarts_sans_tuile"], (
        "le court-circuit `casterTiles` vide ne rend plus `{0, false, options.UseWholeBoard}` : %s"
        % r["ecarts_sans_tuile"][:5])
    assert not r["refus_poses"], (
        "REGRESSION : le port pose un refus de portee la ou il n'en posait aucun : %s"
        % r["refus_poses"][:5])


# ------------------------------------------------------------------------------------------------
# 3. Le gate lit les OPTIONS, pas le champ du `Range`
# ------------------------------------------------------------------------------------------------

def test_le_gate_whole_board_lit_les_options_pas_le_champ_du_range(monkeypatch):
    """`GetInvalidTargetReason` teste `options.Range.UseWholeBoard`. Les deux sont egaux dans le
    natif -- c'est justement pourquoi seule une MUTATION peut dire lequel le port lit.

    On force `get_range` a rendre un `Range` a `use_whole_board=True` pour des OPTIONS qui, elles,
    ne le portent pas. Le port doit alors POSER son gate de distance : s'il ne le pose pas, c'est
    qu'il lit le champ du `Range`, et un futur consommateur natif divergerait."""
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.state import State

    from engine.runner.abilities.targeting import RANGED_BOOL_FALSE
    # Le masque doit poser un gate de DISTANCE effectif : portee fixe, pas d'adjacence (qui
    # sortirait par `are_entities_adjacent`, lequel rend 0 faute de `board`), pas de clamp de melee.
    opts = next(o for o in P._masques_lus().values()
                if o.range is not None and not o.range.use_whole_board
                and o.range.override_range is not None and int(o.range.override_range) == 1
                and int(o.range.only_adjacent) == RANGED_BOOL_FALSE
                and int(o.force_melee_target) == RANGED_BOOL_FALSE)
    st = State()
    ent = st.add_entity()
    ent.add_component(UnitComponent(visual_id="", alive=True))
    ent.add_component(PositionComponent(col=3, row=3))
    ent.add_component(OwnerComponent(team=0))
    cid = int(next(k for k, v in st.entities.items() if v is ent))
    cible = st.add_entity()
    cible.add_component(UnitComponent(visual_id="", alive=True))
    cible.add_component(PositionComponent(col=3, row=6))          # d = 3 > override_range = 1
    tid = int(next(k for k, v in st.entities.items() if v is cible))

    assert TGT.get_range_broken_rule(st, cid, tid, opts) == int(TR.TargetIsInRange), (
        "temoin : sans mutation, la cible hors portee doit rompre `TargetIsInRange`")

    vrai = TGT.get_range
    monkeypatch.setattr("engine.runner.abilities.targeting.get_range",
                        lambda s, c, o: dataclasses.replace(vrai(s, c, o), use_whole_board=True))
    assert TGT.get_range_broken_rule(st, cid, tid, opts) == int(TR.TargetIsInRange), (
        "le port a desarme son gate alors que SEUL le champ du `Range` porte `use_whole_board` : "
        "il lit la mauvaise source (le natif teste `options.Range.UseWholeBoard`)")


# ------------------------------------------------------------------------------------------------
# 4. Le regime d'ECART du court-circuit `casterTiles` vide
# ------------------------------------------------------------------------------------------------

def test_le_gisement_du_court_circuit_caster_sans_tuile_est_vide():
    r = P.mow_masques()
    assert r["porteurs_bit30"] > 0 and r["mow_gameconfig"] > 0, (
        "recensement VIDE -- il ne peut alors rien garder : %s" % r)
    assert not r["bit30_sans_whole_board"], (
        "une ability porte `AllowNullCasterTile` SANS `use_whole_board` : le gate de distance "
        "devient atteignable pour un caster sans tuile -> CONFRONTER, ne pas ajuster : %s"
        % r["bit30_sans_whole_board"])
    assert not r["actives_de_mow_hors_whole_board"], (
        "une MACHINE OF WAR porte une active non-`UseWholeBoard` : %s"
        % r["actives_de_mow_hors_whole_board"][:5])


def test_le_port_lit_la_stat_range_quand_le_canal_est_la_et_pas_sinon():
    """La branche `!HasAnyWeapon` : `None` sans canal de stats (face DECISION), la VALEUR avec.

    Les deux sens comptent -- rendre `0` sans canal inventerait une mesure, rendre `None` avec le
    canal desarmerait le gate de distance que le natif, lui, arme."""
    from engine.entities.stats import StatComponent, UnitStats
    from engine.runner.components import (OwnerComponent, PositionComponent, StatsComponent,
                                          UnitComponent)
    from engine.runner.state import State

    opts = next(o for o in P._masques_lus().values()
                if o.range is not None and not o.range.use_whole_board
                and o.range.override_range is None and not o.range.use_range_from_config
                and not o.range.override_range_func)

    def _st(avec_stats):
        s = State()
        e = s.add_entity()
        e.add_component(UnitComponent(visual_id="tyranBiovore", alive=True))   # SANS arme au kit
        e.add_component(PositionComponent(col=3, row=3))
        e.add_component(OwnerComponent(team=0))
        if avec_stats:
            us = UnitStats()
            us.set_component(int(StatType.RANGE), StatComponent(initial=0))
            e.add_component(StatsComponent(ctx=us))
        return s, int(next(k for k, v in s.entities.items() if v is e))

    sans, cid = _st(False)
    assert TGT.get_range(sans, cid, opts).value is None, (
        "sans canal de stats, la portee d'une unite SANS ARME n'est pas observable -- rendre une "
        "valeur y inventerait une mesure")
    avec, cid2 = _st(True)
    assert TGT.get_range(avec, cid2, opts).value == 0, (
        "avec le canal, le port doit rendre `GetStat(caster, StatType.Range = 2)`, que le natif LIT")


# ------------------------------------------------------------------------------------------------
# 5-6. LIVE -- la MoW sans tuile, et la stat `range` sur des unites SANS ARME
# ------------------------------------------------------------------------------------------------

def test_live_la_machine_of_war_n_a_aucune_tuile():
    r = P.mow_sans_tuile()
    if r["erreurs"] and not r["lignes"]:
        pytest.fail("montage NON POSE (aucune MoW observee) : %s" % r["erreurs"][:2])
    assert r["mows_observees"] >= 2, (
        "il faut au moins DEUX MoW pour que ce ne soit pas une singularite : %s" % r)
    assert r["toutes_sans_tuile"], (
        "une MoW porte une tuile -- le court-circuit `casterTiles` vide perdrait son porteur : %s"
        % r["lignes"])


def test_live_getstat_range_vaut_zero_sur_les_trois_etages():
    r = P.stat_range()
    if r["erreurs"] and not r["unites_observees"]:
        pytest.fail("montage NON POSE : %s" % r["erreurs"][:2])
    assert r["appariement_est_bien_2"], (
        "le catalogue `statTypes` n'apparie plus `range` a `StatType.RANGE` (%s) : on mesurerait "
        "une cle homonyme" % r["appariement_statTypes_range"])
    assert r["catalogue"]["entrees"] > 100 and r["catalogue"]["valeurs_distinctes"] == ["0"], (
        "etage CATALOGUE : `UnitConfiguration.Range` n'est plus uniformement nul : %s"
        % r["catalogue"])
    assert r["modification"]["aucune_ne_nomme_range"], (
        "etage MODIFICATION : un `statType` du gameconfig nomme desormais `range` -- la stat peut "
        "etre deplacee, le zero de l'etage RESOLU n'est plus generalisable : %s"
        % r["modification"]["valeurs_de_statType_du_gameconfig"])
    assert r["substrat_arme_mesurable"] >= 4, (
        "le canal `combatSnapshot.units[].weapons` ne repond pas : `!HasAnyWeapon` serait alors "
        "apparie depuis le GAMECONFIG, pas depuis le `WeaponsComponent` que le natif interroge -- "
        "la mesure porterait sur une population voisine, pas sur la bonne (%s mesurables)"
        % r["substrat_arme_mesurable"])
    assert not r["desaccords_kit_vs_ecs"], (
        "le kit gameconfig et le `WeaponsComponent` de l'ECS ne s'accordent plus sur « a une arme » "
        "-- tout ce qui apparie « sans arme » par le kit devient suspect : %s"
        % r["desaccords_kit_vs_ecs"][:5])
    assert r["sans_arme_observees"] >= 4, (
        "moins de quatre unites SANS ARME observees : une mesure sur une seule ne generalise pas "
        "(c'est la reserve que ce residu portait) : %s" % r["sans_arme_distinctes"])
    assert r["toutes_a_zero"], (
        "etage RESOLU : `GetStat(StatType.Range)` n'est plus nul : %s" % r["non_nulles"][:5])
