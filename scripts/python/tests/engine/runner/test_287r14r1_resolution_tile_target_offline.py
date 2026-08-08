#!/usr/bin/env python3
"""#287-r14-r1 -- garde de l'invariant << toute `TargetIsTile` resout sa cible en tete >>.

Le residu proposait de porter la resolution sur **73** tetes d'`execute_behaviour`. La mesure
l'a renverse : le regime que ces 73 couvriraient (passer une TUILE a une ability unit-target)
n'est emprunte par AUCUN appelant -- donc 73 copies d'une ligne inerte. Ce qui manquait, c'est
le cliquet sur le regime SYMETRIQUE, celui qui EST emprunte : passer une UNITE a une ability
tile-target (`test_valkyrie_strike_migration_live` le grave).

Ce fichier garde les deux faces : l'invariant (23/23) et le verdict de mort (etage 2).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_287r14r1_resolution_tile_target as P  # noqa: E402

#: ⚠ CE FICHIER A DEUX PERIMETRES, et le second est l'ARBRE (corrige apres #845, meme faute que
#: son voisin #431-r1 : la declaration initiale ne nommait que la sonde + `abilities/**`, donc
#: `toujours: False` la lisait << ne se rejoue que si le registre bouge >>).
#:
#:   * etage 1 -- l'INVARIANT : `ABILITY_CLASSES` et les masques `TARGETING_OPTIONS`. Borne par
#:     `engine/runner/abilities/**`, et une fermeture d'imports le voit.
#:   * etage 2 -- le VERDICT DE BRANCHE MORTE : il recense les appelants DIRECTS
#:     d'`execute_behaviour` dans TOUT `.py` versionne. Ce sont des probes et des tests, donc
#:     personne ne les IMPORTE : la fermeture est structurellement aveugle. Un probe NEUF qui
#:     passerait une tuile a une ability unit-target ferait basculer le verdict -- et c'est
#:     precisement le scenario que le cliquet existe pour attraper (il est ecrit au site :
#:     << le regime etait MORT quand #287-r14-r1 a ete tranche ; il ne l'est plus >>).
#:
#: `toujours: True` est donc la seule declaration honnete, et elle rend le bypass
#: `hors_confrontation` inutile : il est retire.
DECLENCHEUR = {
    "chemins": ("*", "**"),
    "build": False,
    "toujours": True,
    "raison": "Deux perimetres : le registre d'abilities (etage 1) ET tout `.py` versionne "
              "(etage 2, qui recense les appelants directs d'`execute_behaviour` -- des probes "
              "et des tests, que personne n'importe). Un fichier NEUF peut faire basculer le "
              "verdict de branche morte sans toucher a `engine/`.",
}


@pytest.fixture(scope="module")
def ventilation():
    return P.ventiler()


# ============================================ 1. l'INVARIANT, et son propre non-vide
def test_l_ensemble_des_tile_target_n_est_PAS_vide(ventilation):
    """Un ensemble VIDE passerait pour un vert -- exactement le piege du controle d'ordinaux
    de #270-r1-r1-r3, dont le premier ensemble etait vide et qui serait passe."""
    tile, autres, sans_masque = ventilation
    assert len(tile) >= 20, "seulement %d tile-target : le registre ou les masques ont casse" \
                            % len(tile)
    assert len(autres) >= 50, "le versant non-tile est suspect : %d" % len(autres)


def test_TOUTES_les_tile_target_resolvent_leur_cible(ventilation):
    """L'invariant. Meme famille que `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` : un zero que
    notre PROPRE cadence de portage rouvre, ability tile-target neuve par ability neuve.

    Sans la ligne, l'ability opere sur l'UNITE la ou le natif lui donne sa TUILE
    (`ActiveAbilityOperation$$ExecuteInternal` resout AVANT `GetAbilityEntities`) -- une
    degradation PERMISSIVE, donc invisible en self-play.
    """
    tile, _autres, _sm = ventilation
    manquantes = [(a, n, v) for a, n, v in tile if v != "OUI"]
    assert manquantes == [], (
        "ability(s) `TargetIsTile` sans `self.get_actual_target(...)` en tete de leur "
        "`execute_behaviour` : %r" % (manquantes,))


def test_aucune_non_tile_ne_resout_en_tete(ventilation):
    """La contre-partie : la resolution est posee la ou elle MORD, pas partout.

    Ce test n'est pas une preference de style -- c'est ce qui rend le compte du premier test
    LISIBLE. Si des non-tile se mettaient a resoudre, << 23/23 >> ne dirait plus rien du
    perimetre reellement couvert.
    """
    _tile, autres, _sm = ventilation
    surplus = [(a, n) for a, n, v in autres if v == "OUI"]
    assert surplus == [], "non-tile qui resolvent : %r" % (surplus,)


def test_un_masque_NON_RE_LU_n_est_pas_compte_comme_non_tile(ventilation):
    """`TARGETING_OPTIONS is None` = PAS MESURE, jamais << pas tile-target >>.

    Le rabattre sur le versant non-tile fabriquerait un zero -- meme regle tri-etat que
    `host_inputs.py`. Le seau existe et est imprime ; il se trouve vide aujourd'hui.
    """
    tile, autres, sans_masque = ventilation
    total = len(tile) + len(autres) + len(sans_masque)
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert total == len(ABILITY_CLASSES), \
        "la ventilation n'est pas une PARTITION du registre : %d != %d" \
        % (total, len(ABILITY_CLASSES))


# =================================================== 2. le CRITERE mord (contre-epreuves)
def test_resout_sa_cible_discrimine():
    """Le lecteur est un AST sur la SOURCE de la methode, pas un grep sur le fichier.

    Un grep attribuerait a une classe la ligne de sa voisine : les modules d'abilities en
    portent jusqu'a 40.
    """
    class Base:
        def execute_behaviour(self, state, caster_id, target_id):
            return None

    class Resout(Base):
        def execute_behaviour(self, state, caster_id, target_id):
            target_id = self.get_actual_target(state, caster_id, target_id)
            return {"t": target_id}

    class NeResoutPas(Base):
        def execute_behaviour(self, state, caster_id, target_id):
            return {"t": target_id}

    class Herite(Base):
        pass

    assert P.resout_sa_cible(Resout) == "OUI"
    assert P.resout_sa_cible(NeResoutPas) == "NON"
    assert P.resout_sa_cible(Herite) == "HERITE"


def test_l_attribution_d_un_appel_est_EXACTE_ou_ABSENTE():
    """`XAbility().execute_behaviour(...)` s'attribue ; `cls().execute_behaviour(...)` non --
    et le second est IMPRIME plutot que devine. Un recenseur ne peut pas rendre zero sur ce
    qu'il ne visite pas."""
    import ast
    def appel(src):
        return next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
                    and getattr(n.func, "attr", "") == "execute_behaviour")
    assert P._nom_classe_appelee(appel("XAbility().execute_behaviour(s, c, t)")) == "XAbility"
    assert P._nom_classe_appelee(appel("cls().execute_behaviour(s, c, t)")) is None
    assert P._nom_classe_appelee(appel("obj.execute_behaviour(s, c, t)")) is None


# ======================================== 3. le VERDICT de branche morte, re-derive
def test_le_regime_TUILE_en_direct_reste_MORT():
    """Le resultat qui a fait RENONCER au port des 73 tetes -- re-derive, jamais cite.

    S'il tombe, ce n'est pas une regression : c'est que le regime est redevenu vivant, et
    alors la tete des abilities CONCERNEES (pas les 73) doit etre portee.
    """
    tile, _autres, _sm = P.ventiler()
    noms_tile = {n for _a, n, _v in tile}
    attribues, non_attribues = P.appels_directs()
    assert len(attribues) + len(non_attribues) > 100, \
        "trop peu d'appels directs releves (%d) : le releveur a casse" \
        % (len(attribues) + len(non_attribues))
    hors = [(r, l, k, c) for r, l, k, c in attribues
            if any(m in c for m in P.MOTS_TUILE) and k not in noms_tile]
    assert hors == [], (
        "un appelant direct passe une TUILE a une ability unit-target -- le regime que "
        "#287-r14-r1 avait mesure MORT est redevenu vivant : %r" % (hors,))


def test_les_sites_qui_passent_une_tuile_visent_TOUS_une_tile_target():
    """La face positive du meme fait : le releve n'est pas vide, il est CONFORME.

    Un `hors == []` obtenu sur un releve vide ne prouverait rien -- c'est le vice que le
    recenseur d'enums de #270-r1-r1-r3 a du corriger trois fois.
    """
    tile, _autres, _sm = P.ventiler()
    noms_tile = {n for _a, n, _v in tile}
    attribues, _anon = P.appels_directs()
    par_tuile = [(r, l, k, c) for r, l, k, c in attribues
                 if any(m in c for m in P.MOTS_TUILE)]
    assert len(par_tuile) >= 3, \
        "aucun site attribuable ne passe une tuile : le temoin du regime a disparu"
    assert all(k in noms_tile for _r, _l, k, _c in par_tuile)
