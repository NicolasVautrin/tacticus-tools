#!/usr/bin/env python
"""Cliquet #275 -- les SIX tables de `enum_maps.py` collent au build courant.

POURQUOI UN CLIQUET, ET PAS SEULEMENT UNE CORRECTION
----------------------------------------------------
Une table d'enum perimee ne casse rien : elle rend un AUTRE nom. `GROUP_TYPE` a porte
**66 ids au nom FAUX** pendant des mois (un membre insere en 36 decalait toute la suite), et
`EFFECT_TYPE` donnait `1563 = DA_Hero6_Passive_1` la ou le jeu dit
`SpecialIssueCombiMelta_AdditionalHits`. Aucune erreur, aucune trace -- c'est le lecteur humain
qui paie, et l'ingest RL qui ecrit un mauvais libelle en base.

La derive est ARRIVEE parce que le reparateur etait en panne : `rl_gen_enum_columns.py` lit
`data/dumps/<hash>/dump.cs`, artefact Il2CppDumper SUPPRIME le 2026-07-25. Le cliquet ne sert donc
pas seulement a constater : il PROUVE que `regen_enum_maps.py` a tourne, et son message le dit.

Ce fichier verifie TROIS choses, et les deux dernieres ne sont pas decoratives :

1. les six blocs coincident avec `data/symbols/<CURRENT>/frida/enums.tsv` -- le cliquet ;
2. le DETECTEUR mord vraiment (un cliquet qui ne detecte rien passerait au vert sur une table
   pourrie) : on lui soumet les trois formes de derive REELLEMENT observees -- membre retire,
   membre ajoute, et valeur REATTRIBUEE (la pire : elle resout et pointe ailleurs) ;
3. `enum_maps.GROUP_TYPE` et `stream_events.group_name` -- DEUX lectures independantes de la meme
   table versionnee, par deux chemins de code differents -- rendent le meme nom. C'est ce
   recoupement qui manquait : `rl_collect_batch` a resolu par les deux voies a la fois, l'une
   juste et l'autre fausse, sans que rien ne les confronte.

Offline pur : aucun runner, aucune session Frida. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import enum_maps as EM  # noqa: E402
import probe_275_enum_maps_drift as P  # noqa: E402
import stream_events as SE  # noqa: E402
from symbols_layout import current_build  # noqa: E402


# --------------------------------------------------- 1. le cliquet : les 6 blocs collent

def test_les_six_blocs_collent_au_build_courant():
    build = current_build()
    depot = P.blocs_enum_maps()
    ecarts = []
    for bloc, cle, _, _ in P.BLOCS:
        t = depot.get(bloc, {})
        jeu = P.enum_natif(build, cle)
        renum = [(v, t[v], sorted(jeu[v])) for v in sorted(set(t) & set(jeu))
                 if t[v] not in jeu[v]]
        absents = sorted(set(t) - set(jeu))
        manquants = sorted(set(jeu) - set(t))
        if renum or absents or manquants:
            ecarts.append("  %s : RENUMEROTES=%d absents-du-jeu=%d manquants=%d ; ex. %s"
                          % (bloc, len(renum), len(absents), len(manquants),
                             renum[:3] or absents[:3] or manquants[:3]))
    assert not ecarts, (
        "enum_maps.py a derive du build %s :\n%s\n"
        "  Reparer : python scripts/python/regen_enum_maps.py --ecrire\n"
        "  Inventorier d'abord : python scripts/python/probe_275_enum_maps_drift.py --citations\n"
        "  (le generateur historique rl_gen_enum_columns.py lit un dump.cs SUPPRIME : il ne peut\n"
        "   plus tourner)" % (build, "\n".join(ecarts)))


def test_by_column_pointe_les_blocs_lus_par_l_ingest():
    """`BY_COLUMN` est ce que `rl_collect_batch` consulte pour remplir les colonnes `*_name`.
    Une regeneration qui casserait ces alias rendrait l'ingest muet -- sans erreur."""
    assert set(EM.BY_COLUMN) == {"effect_type", "active_ability_type", "passive_ability_type",
                                 "damage_profile_type", "unit_spawn_source"}
    for col, table in EM.BY_COLUMN.items():
        assert table, "BY_COLUMN[%r] est vide" % col
        assert all(isinstance(k, int) and isinstance(v, str) for k, v in table.items())


# --------------------------------- 2. le detecteur mord (sinon le cliquet ne prouve rien)

def _diff(depot: dict[int, str], jeu: dict[int, set[str]]) -> tuple[int, int, int]:
    """Le calcul EXACT du cliquet, isole pour qu'on puisse le nourrir de tables truquees."""
    renum = sum(1 for v in set(depot) & set(jeu) if depot[v] not in jeu[v])
    return renum, len(set(depot) - set(jeu)), len(set(jeu) - set(depot))


def test_detecte_un_membre_retire_par_le_jeu():
    jeu = {0: {"A"}, 1: {"B"}}
    assert _diff({0: "A", 1: "B", 2: "C"}, jeu) == (0, 1, 0)


def test_detecte_un_membre_ajoute_par_le_jeu():
    jeu = {0: {"A"}, 1: {"B"}, 2: {"C"}}
    assert _diff({0: "A", 1: "B"}, jeu) == (0, 0, 1)


def test_detecte_une_valeur_REATTRIBUEE():
    """LE cas qui a coute : meme id, autre membre. Il resout, pointe ailleurs, rien ne proteste.
    C'est la forme exacte de `GROUP_TYPE` (insertion en 36 -> 66 ids decales) et de
    `EFFECT_TYPE[1563]`."""
    jeu = {36: {"Ability_Displace"}, 37: {"Ability_Buff"}}
    renum, absents, manquants = _diff({36: "Ability_Buff", 37: "Ability_Stance"}, jeu)
    assert (renum, absents, manquants) == (2, 0, 0)


def test_un_alias_de_valeur_n_est_PAS_une_derive():
    """Plusieurs membres partagent parfois une valeur (mesure : `ActiveAbilityType` 9999 porte
    `STRIPPED` ET `testAssetBundles`). Le cliquet compare a l'ENSEMBLE, pas a un nom unique --
    sinon il crierait a chaque build sur une table pourtant juste."""
    assert _diff({9999: "STRIPPED"}, {9999: {"STRIPPED", "testAssetBundles"}}) == (0, 0, 0)


# ------------------- 3. les deux lectures independantes de GroupType sont d'accord

def test_group_type_et_stream_events_rendent_le_meme_nom():
    """`enum_maps.GROUP_TYPE` (table recopiee) et `stream_events.group_name` (resolution par nom
    contre `enums.tsv`) doivent coincider MEMBRE PAR MEMBRE. Quand ils divergeaient,
    `rl_collect_batch` ecrivait `59 = NormalAttack_AtomicDamage` la ou le build dit
    `ZingerAbility` -- et le fallback « 015 » ne s'armait donc JAMAIS sur une attaque normale."""
    divergents = [(v, n, SE.group_name(v)) for v, n in sorted(EM.GROUP_TYPE.items())
                  if SE.group_name(v) != n]
    assert not divergents, ("GROUP_TYPE diverge de stream_events sur %d ids : %s"
                            % (len(divergents), divergents[:5]))


def test_les_deux_membres_qui_manquaient_a_group_type_sont_la():
    """`Ability_Displace` et `EndTurn` : les deux insertions qui decalaient tout le reste. Les
    citer par NOM (jamais par ordinal) est ce qui rend ce test survivant au prochain build."""
    for nom in ("Ability_Displace", "EndTurn"):
        assert EM.GROUP_TYPE[SE.group_id(nom)] == nom
