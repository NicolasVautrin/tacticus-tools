"""#888 -- `snapshot._ability_state_from_rows` / `_ability_state_with_rows` : le TROISIEME canal
d'`AbilityState`, celui d'un porteur SANS `unitConfig`.

POURQUOI CE CANAL EXISTE
------------------------
Un **GUILD BOSS** (`gameconfig.units[].kind == "npc"`, ex. `deathBossMortarion`) n'a AUCUNE
`UnitConfiguration` cote natif : `combatSnapshot.units[].unitConfig` rend litteralement
`{"error": "config null"}` -- MESURE, pas suppose. `_ability_state_from_config` y rend le neutre
`(100, None, None)`, donc `ctx.active_ability_level` restait `None` = l'INDEX 0 de chaque tableau de
variables = le niveau **1** a la place du **55** que l'entite porte. Mesure sur
`1093 MortarionsPlagueWind` : les trois vagues sortaient a **45 / 65 / 120** contre
**3080 / 4448 / 8211** live. Le canal qui porte l'information est
`combatSnapshot.units[].abilityStates` (`ActiveAbility._abilityState` @0x4c), que la face DECISION
consommait deja (`playbook/scene.py`) et que le COMBAT ignorait.

CE QUE CE FICHIER GARDE, ET POURQUOI IL EST OFFLINE
---------------------------------------------------
Le confront LIVE (`test_888_mortarion_boss_abilities_live.py`) prouve que le comblement DONNE LA
BONNE VALEUR sur un porteur reel. Il ne peut PAS prouver ce qui suit, parce que ces regimes
n'existent pas sur ce porteur-la : le **desaccord** entre entrees, et le refus d'ecraser une valeur
**mesuree**. Ce sont pourtant les deux crans qui separent « combler un trou » de « deviner ».

Les quatre etages sont des fonctions PURES sur un dict de ligne de snapshot -- aucun runner, aucun
RPC. ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # Le SEUL foyer que ce fichier exerce -- il n'appelle que deux fonctions pures de ce module.
        "scripts/python/engine/runner/snapshot.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Quatre fonctions PURES sur un dict de ligne de `combatSnapshot` : aucun runner, "
              "aucun RPC, aucune lecture du build. Le seul changement qui peut faire changer ce "
              "fichier d'avis est une edition de `snapshot.py` (ou de la cascade des conftest).",
}

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

from engine.runner import snapshot as S            # noqa: E402  (forme B : le patch mord toujours)

#: La ligne de snapshot d'un GUILD BOSS, VERBATIM de la mesure (`deathBossMortarion` palier 4,
#: board `GB_Mortarion_05`) : `unitConfig` en ERREUR, et les trois actives portant leur etat.
BOSS = {
    "entityId": 100,
    "unitConfig": {"error": "config null"},
    "abilityStates": [
        {"id": 1093, "name": "MortarionsPlagueWind", "kind": "active", "level": 55, "multiplier": 200},
        {"id": 1094, "name": "TheLantern", "kind": "active", "level": 55, "multiplier": 200},
        {"id": 1095, "name": "ReapingScythe", "kind": "active", "level": 55, "multiplier": 200},
    ],
}

#: Une unite NORMALE, VERBATIM de la meme mesure : son `unitConfig` porte tout.
NORMALE = {
    "entityId": 84,
    "unitConfig": {"visualId": "astraBullgryn", "abilityVariablesMultiplier": 180,
                   "tertiaryAbilityVariablesMultiplier": 100, "level": 50,
                   "activeAbilityLevel": 50, "passiveAbilityLevel": 50},
    "abilityStates": [{"id": 1, "kind": "active", "level": 50, "multiplier": 180}],
}


def test_etage1_le_boss_recupere_son_niveau_et_son_multiplicateur():
    """Le trou est COMBLE : sans `unitConfig`, le canal per-ability fournit `(200, None, 55)`."""
    brut = S._ability_state_from_config(BOSS["unitConfig"])
    assert brut == (100, None, None), \
        "le neutre attendu faute de `unitConfig` a change : %s" % (brut,)
    mult, passif, actif = S._ability_state_with_rows(brut, BOSS)
    assert (mult, actif) == (200, 55), \
        "comblement KO : (mult, actif) = (%s, %s) au lieu de (200, 55)" % (mult, actif)
    assert passif is None, \
        ("un niveau PASSIF a ete invente (%s) : les trois entrees sont `kind = active`, "
         "le canal ne dit RIEN du passif" % passif)


def test_etage2_le_desaccord_rend_None_jamais_l_une_des_valeurs():
    """⚠ LE CRAN QUI SEPARE « COMBLER » DE « DEVINER ». Le port ne dispose que d'UN
    `active_ability_level` par unite la ou le natif porte un `AbilityState` par ABILITY : si deux
    actives portaient des niveaux differents, aucun scalaire n'est juste. On rend `None` (non
    mesure), jamais l'une des deux.

    Ce regime n'existe PAS sur le porteur du confront live -- d'ou ce test."""
    dissonant = {**BOSS, "abilityStates": [
        {"id": 1093, "kind": "active", "level": 55, "multiplier": 200},
        {"id": 1095, "kind": "active", "level": 30, "multiplier": 200},   # <- desaccord
    ]}
    mult, _p, actif = S._ability_state_with_rows(S._ability_state_from_config(dissonant["unitConfig"]),
                                                 dissonant)
    assert actif is None, \
        ("deux actives a 55 et 30 ont rendu le niveau %s : une valeur a ete CHOISIE alors "
         "qu'aucune n'est justifiee" % actif)
    assert mult == 200, \
        "le multiplicateur, lui, est UNANIME (200) et doit rester comble : %s" % mult


def test_etage3_une_valeur_MESUREE_n_est_jamais_ecrasee():
    """Une unite NORMALE a son `unitConfig` : le canal ne doit rien y toucher, meme si les deux
    sources disent la meme chose -- c'est la PRESENCE du champ qui decide, pas sa valeur (sans quoi
    un multiplicateur mesure a `100` serait indistinguable du neutre et se ferait ecraser)."""
    brut = S._ability_state_from_config(NORMALE["unitConfig"])
    assert brut == (180, 50, 50), "lecture du `unitConfig` KO : %s" % (brut,)
    assert S._ability_state_with_rows(brut, NORMALE) == brut, \
        "le canal a modifie l'etat d'une unite dont le `unitConfig` est MESURE"

    # Contre-cas DUR : `unitConfig` mesure a 100, canal a 200. Le 100 doit TENIR.
    piege = {"entityId": 7,
             "unitConfig": {"visualId": "x", "abilityVariablesMultiplier": 100,
                            "activeAbilityLevel": 3, "passiveAbilityLevel": 3},
             "abilityStates": [{"id": 1, "kind": "active", "level": 55, "multiplier": 200}]}
    assert S._ability_state_with_rows(S._ability_state_from_config(piege["unitConfig"]), piege) \
        == (100, 3, 3), \
        ("un `abilityVariablesMultiplier` MESURE a 100 a ete ecrase par le canal -- la garde lit "
         "la VALEUR au lieu de la PRESENCE du champ")


def test_etage4_sans_canal_le_comportement_est_STRICTEMENT_anterieur():
    """Une ligne sans `abilityStates` (ou vide) doit laisser le triple INCHANGE : le comblement est
    un ajout, jamais une reecriture du chemin existant."""
    for rows in (None, [], "pas une liste"):
        su = {"entityId": 1, "unitConfig": {"error": "config null"}, "abilityStates": rows}
        assert S._ability_state_from_rows(su) == (None, None, None), \
            "`abilityStates = %r` doit rendre un triple VIDE" % (rows,)
        brut = S._ability_state_from_config(su["unitConfig"])
        assert S._ability_state_with_rows(brut, su) == brut, \
            "`abilityStates = %r` a modifie le triple" % (rows,)
    assert S._ability_state_from_rows({}) == (None, None, None)
