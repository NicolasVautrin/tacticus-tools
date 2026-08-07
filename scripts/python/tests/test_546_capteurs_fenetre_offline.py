#!/usr/bin/env python
"""#546 -- GARDE du cliquet offline des capteurs qui attendent LA fenetre de reinject.

Le probe `probe_546_capteurs_fenetre_offline.py` MESURE (il confronte les capteurs ECRITS aux
tables VERSIONNEES du build courant). Ce fichier GARDE, et surtout il verifie que le cliquet
DISCRIMINE : un cliquet qui rendrait vert quoi qu'il arrive donnerait exactement le meme
resultat sur un depot pourri.

POURQUOI CE CLIQUET EXISTE
--------------------------
Une tranche de capteurs se livre AVANT sa fenetre. Entre la livraison et le rebuild, le code
n'est confronte par RIEN : un rebase, une regeneration de table ou un renommage peut le vider en
silence -- et la fenetre s'ouvrirait alors sur du code qui publie `null` partout, ce qui se lit
exactement comme « le regime n'existe pas ». Les quatre capteurs gardes :

  [1] #287-r10-r1 -- `NON_GENERIC_RULE_CODES.InFogOfWarBrokenTargetingRule = 1`. Sans cette
      ligne le RPC publie `hex: "0x0"` pour un REFUS, et tout `int(hex, 16)` lit « cible
      VALIDE ». Le decodeur Python, lui, connait deja la classe : le cliquet exige que les DEUX
      cotes portent la MEME table, sinon le hook publie un refus que le port ne sait pas lire.
  [2] #175-r      -- `tileMeta` : `door` (predicat `!DoorComponent.IsOpen`) + `occupantId` +
      `occupantIsPowerUp`.
  [3] #231-r      -- `effectsAll` : les entites-effet HORS de la liste possedee.
  [4] #347-r1     -- `actorStats[].movement` : les quatre `Nullable<UnitPositionId>` du
      **`MovementComponent`**. `case-347` §8 nomme `UnitComponent+0x98` ; sur `rnca9r7q6c` cet
      offset-la est `PendingHit`. L'offset coincide, le COMPOSANT non -- un capteur ecrit sur la
      foi de la fiche aurait lu le mauvais champ, sans lever.

  [5] LE CRAN QUI NE SE LIT PAS DANS LE TEXTE. Un capteur resout ses classes et ses methodes PAR
      NOM au runtime : un nom faux ne leve rien, il rend `null`. Le cliquet confronte donc chaque
      nom aux tables du build -- et l'ARITE ne suffit pas :
      `IdunBattle.Entities.UnitExtensions.GetUnit` a **trois** surcharges d'arite 2
      (`IEntity` / `FootEntity` / `TileEntity`), donc `findMethodByParamCount` en resoudrait une
      au hasard. Deux des trois ne prennent pas une tuile.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre ETROIT et DERIVE, et c'est mesure : ce fichier n'importe pas `engine`. Ce qu'il lit
#: est un ENSEMBLE NOMME de sources de hooks, le decodeur Python apparie, et les tables
#: versionnees du build -- donc les chemins se nomment un par un. Pas de glob
#: `scripts/python/*.py` : ce serait un `toujours: True` deguise (mesure `case-486-r24` §3bis :
#: 995 -> 20 fichiers declencheurs).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/probe_546_capteurs_fenetre_offline.py",
        "scripts/python/targeting_reason.py",
        "scripts/python/symbols_layout.py",
        "frida/hooks/features/ai-step/rpc-targeting.ts",
        "frida/hooks/features/ai-step/rpc-board.ts",
        "frida/hooks/features/ai-step/rpc-snapshot.ts",
        "frida/hooks/game/effects.ts",
        # ⚠ HORS de `scripts/python/` : l'etape 5 confronte les noms CITES aux tables du build.
        # Une regeneration de ces tables (changement de build) doit rejouer ce cliquet -- c'est
        # exactement le regime ou un nom devient faux en silence.
        "data/symbols/CURRENT",
        "data/symbols/**/frida/classes.tsv",
        "data/symbols/**/frida/methods.tsv",
    ),
    "build": True,
    "toujours": False,
    "raison": "`build: True` : ce cliquet FIGE des grandeurs derivees du binaire -- l'offset "
              "`PreviousPositionThisTurn = 0x98` MESURE sur `rnca9r7q6c`, et le fait que "
              "`UnitExtensions.GetUnit` y porte TROIS surcharges d'arite 2 (ce qui rend la "
              "desambiguisation par classe de parametre obligatoire). Les deux glissent au "
              "prochain build, en silence, et c'est precisement ce que la fenetre de reinject "
              "irait exercer. Perimetre etroit : aucun import d'`engine`, donc aucune cascade.",
}

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import probe_546_capteurs_fenetre_offline as P  # noqa: E402

TARGETING = P.TARGETING
BOARD = P.BOARD
SNAPSHOT = P.SNAPSHOT


@pytest.fixture(scope="module")
def build() -> str:
    return P._build_courant()


# ------------------------------------------------------- 1. le depot est PROPRE sur les 5 etapes

def test_le_capteur_de_brouillard_est_ecrit_des_deux_cotes():
    """#287-r10-r1 -- le hook et le decodeur Python portent la MEME classe et le MEME code."""
    assert P.etape1_brouillard() == []


def test_tilemeta_publie_porte_et_occupant():
    """#175-r -- les deux derniers sujets du `BLOCAGE: capteur` de #175-r."""
    assert P.etape2_tilemeta() == []


def test_effectsall_enumere_les_entites_effet_orphelines():
    """#231-r -- l'enumeration GLOBALE, seule capable de separer les trois regimes."""
    assert P.etape3_effectsall() == []


def test_le_capteur_de_mouvement_lit_le_bon_composant():
    """#347-r1 -- `MovementComponent`, PAS `UnitComponent` (dont `+0x98` est `PendingHit`)."""
    assert P.etape4_mouvement() == []


def test_les_noms_cites_existent_dans_le_build_courant(build):
    """[5] -- un nom faux ne leve pas : il rend `null`. On le confronte aux tables."""
    assert P.etape5_noms_du_build(build) == []


# --------------------------------------------------- 2. le cliquet MORD (contre-epreuves)
#
# Chaque mutation ecrit une source de hook, rejoue l'etape, puis RESTAURE le texte d'origine.
# Sans elles, les cinq verts ci-dessus ne prouveraient rien.

def _muter(chemin: Path, avant: str, apres: str, etape):
    src = chemin.read_text(encoding="utf-8")
    assert avant in src, (
        "la contre-epreuve ne peut pas s'installer : `%s` absent de %s -- une mutation qui ne "
        "MORD PAS rendrait ce test vert pour rien" % (avant[:60], chemin.name))
    try:
        chemin.write_text(src.replace(avant, apres, 1), encoding="utf-8")
        return etape()
    finally:
        chemin.write_text(src, encoding="utf-8")


def test_mutation_ligne_brouillard_retiree_rougit():
    ko = _muter(TARGETING, "    InFogOfWarBrokenTargetingRule: 1,\n", "",
                P.etape1_brouillard)
    assert ko, "retirer la ligne BROUILLARD doit ROUGIR l'etape 1"
    assert any("BROUILLARD" in m for m in ko), ko


def test_mutation_offset_de_position_deplace_rougit():
    ko = _muter(SNAPSHOT,
                'name: "PreviousPositionThisTurn", fallback: 0x98',
                'name: "PreviousPositionThisTurn", fallback: 0x88',
                P.etape4_mouvement)
    assert ko, "deplacer l'offset MESURE doit ROUGIR l'etape 4"
    assert any("previousPositionThisTurn" in m for m in ko), ko


def test_mutation_getunit_resolu_par_arite_rougit(build):
    ko = _muter(BOARD,
                'findMethodByParamClasses(unitExtClass, "GetUnit", ["TileEntity", null])',
                'findMethodByParamCount(unitExtClass, "GetUnit", 2)',
                lambda: P.etape5_noms_du_build(build))
    assert ko, ("resoudre `GetUnit` par l'ARITE doit ROUGIR l'etape 5 : trois surcharges "
                "d'arite 2 existent sur ce build")
    assert any("surcharges" in m for m in ko), ko


def test_mutation_cle_de_tilemeta_retiree_rougit():
    ko = _muter(BOARD, "occupantIsPowerUp: occ ? occ.isPowerUp : null,", "",
                P.etape2_tilemeta)
    assert ko, "retirer une cle publiee doit ROUGIR l'etape 2"


def test_mutation_ventilation_de_effectsall_retiree_rougit():
    ko = _muter(SNAPSHOT,
                'orphanCount: effects.filter((e) => !e.inOwnerList && !e.removed).length,', "",
                P.etape3_effectsall)
    assert ko, ("retirer `orphanCount` doit ROUGIR l'etape 3 : sans lui un `count: 0` ne dit "
                "plus de quoi il est le zero")
