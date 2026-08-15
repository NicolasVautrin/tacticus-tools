"""#447-r1-r1-r1 -- le retrait des NON MARCHABLES est EN AMONT de l'ajout aval de `casterTiles`.

Ce que ces crans gardent, et pourquoi chacun peut ROUGIR :

  1. **LE FOG SUR LA TUILE SOURCE NE CHANGE RIEN** pour une ability qui la verse par l'ajout aval.
     Le `RemoveAll` de walkability est la DERNIERE instruction de `TargetingQuery$$GetTilesInRange`,
     les deux `AddRange(casterTiles)` sont chez son APPELANT : le natif ne filtre donc jamais ce
     qu'il vient d'ajouter. Le critere est l'INVARIANCE, pas « la tuile est gardee » -- plusieurs
     porteurs du bit 15 sont deja retires par le court-circuit `TargetIsFriendly && !TargetIsEnemy`
     de `GetPossibleTargetTiles`, et exiger `True` melangerait deux etages.
  2. **LE FOG RETIRE ENCORE UNE TUILE DE `GetTilesInRange`** -- sans ce second bras, un correctif
     qui aurait simplement supprime l'appel a `_unwalkable` passerait pour juste.
  3. **UN SEUL FOYER POUR LA CONDITION** : `verse_par_ajout_aval` est lue par
     `_zone_contains_distance` (« la tuile EST dans la zone ») ET par `_ability_covers_tile`
     (« elle n'a pas traverse le `RemoveAll` »). Deux ecritures du meme fait natif se
     desynchroniseraient -- c'est le FORK que `#433-r4-r2-r1-r2-r2-r1-r1` avait deja supprime
     ailleurs.
  4. **L'ATTAQUE NORMALE RESTE HORS DU QUIRK** : aucun de ses 18 profils ne porte
     `CasterIsPossibleTarget` ni `TargetIsCasterOrEnemy`, donc son terme est toujours filtre par la
     walkability. Si un profil en gagnait un, le quirk s'y appliquerait aussi -- et il faudrait
     l'ecrire.

NON CONFRONTE LIVE, et c'est une MESURE, pas un aveu : l'ecart exige un caster sur une tuile NON
MARCHABLE ou EN BROUILLARD. Sur les deux boards sondes (`MC1_67` 0 tuile en fog, `C6_02` **32** sur
63) l'intersection « occupee ET (fog ou non marchable) » vaut **0**. Cause structurelle, LUE :
`AddUnitOperation$$AreTilesDisallowedAndLog` refuse la tuile au spawn, `GetMovableTilesFor` n'en
rend pas en brouillard, et le brouillard RECULE au lieu d'avancer. Etape `gisement` du probe.

RE et mesures : `docs/rl/case-447-r1-r1-inclusion-face-decision.md`.
Probe jumeau : `probe_447r1r1r1_ordre_walkability.py`. ASCII only.
"""
from __future__ import annotations

import inspect

import probe_447r1r1r1_ordre_walkability as P
from engine.runner.abilities import targeting as TGT
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.services import ability_range as AR

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/services/ability_range.py",           # le foyer edite
        "scripts/python/engine/services/targeting_query.py",         # `tile_removed_by_walkability`
        "scripts/python/engine/runner/abilities/targeting_rule.py",  # les bits 15 / 57 / 43
        "scripts/python/probe_447r1r1r1_ordre_walkability.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("ces crans sont PUREMENT offline : ils n'interrogent ni le jeu ni le binaire, "
               "seulement le port et son registre de masques. L'etape `gisement` du probe, elle, "
               "est live -- mais elle MESURE une absence de porteur, elle ne garde pas le port, "
               "donc elle n'entre pas dans ce fichier."),
}


def test_le_fog_sur_la_tuile_source_ne_change_rien_pour_l_ajout_aval():
    r = P.synthetique()
    assert r["porteurs_de_l_ajout_aval"] >= 5, (
        "moins de cinq porteurs du bit 15/57 dans le registre -- le cran ne discrimine plus : %s"
        % r["porteurs_de_l_ajout_aval"])
    assert r["A_le_fog_sur_la_source_ne_change_rien"], (
        "le port filtre encore par la walkability une tuile versee par l'ajout aval : %s"
        % [l for l in r["bras_a_source"] if not l["inchange"]][:5])


def test_le_fog_retire_encore_une_tuile_entree_par_get_tiles_in_range():
    r = P.synthetique()
    assert r["B_lignes_discriminantes"] >= 1, (
        "aucune ligne discriminante au bras B : le cran serait VACANT, donc incapable de voir un "
        "desarmement complet de la walkability")
    assert r["B_le_fog_retire_encore_une_tuile_de_GetTilesInRange"], (
        "le correctif a DESARME la walkability au lieu de la deplacer : %s"
        % [l for l in r["bras_b_voisine"] if l["sans_fog"] and not l["retire_par_le_fog"]][:5])


def test_la_condition_de_l_ajout_aval_a_un_foyer_unique():
    """Les DEUX lecteurs appellent `verse_par_ajout_aval` -- verifie sur le SOURCE, pas sur la
    prose : une seconde ecriture de la condition se re-desynchroniserait en silence."""
    for fn in (AR._zone_contains_distance, AR._ability_covers_tile):
        src = inspect.getsource(fn)
        assert "verse_par_ajout_aval" in src, (
            "%s n'appelle plus le foyer de la condition d'ajout aval" % fn.__name__)
    # et le foyer rend bien ce que le natif ajoute : `casterTiles`, donc `d == 0`, sous bit 15 ou 57
    b15, b57 = int(TR.CasterIsPossibleTarget), int(TR.TargetIsCasterOrEnemy)
    assert AR.verse_par_ajout_aval(b15, 0) and AR.verse_par_ajout_aval(b57, 0)
    assert not AR.verse_par_ajout_aval(b15, 1), "l'ajout aval ne verse QUE `casterTiles`"
    assert not AR.verse_par_ajout_aval(0, 0), "sans bit 15 ni 57, le natif n'ajoute rien"
    assert not AR.verse_par_ajout_aval(None, 0), "masque NON LU -> aucun ajout (convention permissive)"


def test_l_attaque_normale_reste_hors_du_quirk():
    b15, b57 = int(TR.CasterIsPossibleTarget), int(TR.TargetIsCasterOrEnemy)
    profils = dict(TGT.NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE)
    assert len(profils) >= 10, "recensement des profils d'attaque normale vide ou tronque"
    porteurs = sorted(t for t, o in profils.items() if int(o.rules) & (b15 | b57))
    assert not porteurs, (
        "un profil d'attaque normale porte desormais l'ajout aval (%s) : son terme cesse d'etre "
        "filtre par la walkability, et il faut l'ECRIRE dans `is_tile_in_range_of_any_ability`"
        % porteurs)
