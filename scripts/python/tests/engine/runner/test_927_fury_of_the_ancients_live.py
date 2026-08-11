"""#927 -- `FuryOfTheAncients` (`TriggeredAbilityType` 0x4df = 1247), le passif de `bloodMephiston`
<< Mephiston >>, CONFRONTE AU LIVE.

CE QUE CES TESTS VERROUILLENT. Le passif n'etait dans AUCUN registre de trigger : offline,
Mephiston terminait son activation SANS frapper personne et SANS poser son blocage de soin -- ni
erreur, ni crash, donc invisible en self-play. `kit-coverage` l'annoncait `manque 1` ; au decompile
il y a TROIS faces (decision/mouvement DEJA portee par #32, decision/attaque DEAD, combat ABSENTE).

CRITERE BINAIRE, sur TROIS observables INDEPENDANTS : quand Mephiston termine son activation a cote
d'un ennemi,
  (a) QUI est frappe -- le natif frappe **DEUX** unites (la cible du tri + un ennemi adjacent A
      ELLE) : un port sans chaine, ou qui aurait lu `maxTargets = 0`, n'en frapperait qu'une ;
  (b) COMBIEN chacune perd -- l'accord est bit-exact, ce qui exerce AUSSI l'alignement PRNG : le
      `SortByFormula` du `GetTarget` natif consomme 2 tirages PAR CANDIDAT avant l'attaque ;
  (c) QUI porte l'effet 1320 `FuryOfTheAncients` apres coup -- le blocage de soin, qui doit
      atterrir sur CHAQUE maillon.

CHAINE PORTEE (cf. `engine/runner/operations/triggers/loki/fury_of_the_ancients.py`) :
    `...$$CreateTrigger`   -> `matches` (`OwnerIsActor & !AmountIsZero(Damageable(AdjacentEnemies))`)
                              sur le vecteur `On(0x1c = ArrivedAtFinalTile)`
    `...$$CreateBehaviour` -> `ChainAttackDamage(GetTarget(), GetSecondTargetSelector, Direct(1),
                                 MinMaxDamage, Psychic, nrOfHits, AddEffect(1320))`

⚠ LE REGIME COMPTE DEUX FOIS, et les deux couples ci-dessous ne sont PAS redondants : il faut que
la tuile d'arrivee touche un ennemi (sinon pas de fire) ET que cet ennemi ait un voisin ennemi
(sinon la chaine est degeneree a une cible). `test_regime_chaine_non_degenere` ASSERTIONNE qu'au
moins une mesure a bien frappe DEUX cibles.

MESURE DE REFERENCE (2026-08-11) :
  * MC1_67 / 777  : natif -958 (sq 77) et -1834 (sq 81), sq 79 intact ; effet 1320 sur 77 et 81 ;
  * MC1_63 / 38704: natif -826 (sq 49) et -805 (sq 51), sq 53 intact ; effet 1320 sur 49 et 51.
Port identique aux deux, sur les trois axes.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import probe_927_fury_of_the_ancients as P                            # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # UN SEUL chemin hors cascade, et c'est une MESURE (`--proposer`) : le probe porte tout le
    # montage et les sept mutants, et rien ne l'importe. Les onze foyers de la tranche (le passif,
    # son registre, `chain`, `formulas`, `units`, `heal_blocking`, `factory`, `attack_query`,
    # `context`, `attack_prediction`) sont DEJA dans la fermeture d'imports que le foyer derive
    # lui-meme (#531) -- les recopier serait du bruit.
    "chemins": (
        "scripts/python/probe_927_fury_of_the_ancients.py",
    ),
    "build": False,
    # Un test LIVE depend de l'etat du JEU (build, seed BC, geometrie des boards) autant que du
    # code : son verdict peut changer sans qu'aucun chemin versionne bouge. Trop LARGE est sain.
    "toujours": True,
    "raison": ("montage LIVE : le verdict depend du build du jeu, de la seed BC et de la "
               "geometrie des boards -- aucun de ces trois n'est un chemin versionne, donc "
               "`toujours` est un RESULTAT. Ce fichier confronte les TROIS observables du passif "
               "(cibles de la chaine, PV bit-exacts, effet 1320 par maillon) et exige que les "
               "sept mutants mordent sur l'UNION des deux regimes."),
}

# Deux couples (board, seed) : le premier est la mesure de reference, le second la GENERALISATION
# (autre plateau, autre geometrie de spawn, autre flux PRNG, autre regime de coups).
CASES = {
    "mc167": dict(board_id="MC1_67", seed=777),
    "mc163": dict(board_id="MC1_63", seed=38704),
    # REGIME SOLO : tuile adjacente a EXACTEMENT UN ennemi. C'est le seul des trois qui exerce le
    # GATE (`!AmountIsZero(pool)`) -- les deux autres arrivent a 2 adjacents, ou aucune lecture du
    # seuil ne peut diverger. Il tranche aussi la lecture d'offset decrite dans
    # `solo_candidates` : le natif FRAPPE a un seul adjacent, donc `minAmount = 0`.
    "solo": dict(board_id="MC1_67", seed=777, solo=True),
}


@pytest.fixture(scope="module")
def fury_case(live_session):
    """Fabrique : `fury_case("mc167")` -> le dict de mesure du probe #927 (mutants COMPRIS).

    Chaque appel monte UN runner isole (build + drive au contact + move) et le DISPOSE en sortie de
    `run()`. Portee MODULE : les deux couples sont partages par les assertions du fichier."""
    cache: dict = {}

    def _case(name: str) -> dict:
        if name not in cache:
            cfg = dict(CASES[name])
            cfg["state_file"] = os.path.join(
                os.environ.get("TEMP", "."), "st_927_%s_%d.json" % (name, os.getpid()))
            cache[name] = P.run(mutants=True, **cfg)
        return cache[name]

    return _case


def _require(m):
    if m.get("err"):
        pytest.fail("montage KO : %s" % m["err"])
    # GARDE ANTI-ACCORD-A-ZERO : un accord ou les deux cotes rendent 0 ne prouve RIEN.
    assert m.get("temoin_natif_non_nul"), (
        "le TEMOIN NATIF est nul (le natif n'a rien fait) -- l'accord serait vide de sens ; "
        "montage a revoir, pas le port")
    return m


@pytest.mark.parametrize("name", sorted(CASES))
def test_cibles_de_la_chaine_identiques(fury_case, name):
    """(a) LES MEMES unites sont frappees live et offline.

    C'est l'observable qui exerce le `GetTarget` (tri par prediction, PAS un tirage) ET le saut de
    chaine (`GetSecondTargetSelector` = allies de la CIBLE, donc les autres ennemis du caster)."""
    m = _require(fury_case(name))
    assert m["accord_cible"], (
        "cibles : natif %s vs port %s" % (m["cible_live"], m["cible_port"]))


@pytest.mark.parametrize("name", sorted(CASES))
def test_degats_bit_exacts(fury_case, name):
    """(b) Chaque cible perd les MEMES PV live et offline.

    Bit-exact parce que le PRNG est cale sur l'etat MT live avant le rejeu -- ce qui rend ce test
    sensible a TOUTE consommation parasite ou manquante, y compris celles du TRI (2 tirages par
    candidat, meme quand le second maillon n'existe pas)."""
    m = _require(fury_case(name))
    assert m["accord_hp"], "PV : natif %s vs port %s" % (m["delta_live"], m["delta_port"])


@pytest.mark.parametrize("name", sorted(CASES))
def test_effet_1320_pose_sur_chaque_maillon(fury_case, name):
    """(c) L'effet 1320 `FuryOfTheAncients` (bloqueur de soin) est sur LES MEMES unites.

    Sans lui, la moitie de l'i2 (`cannot be revived, healed, repaired`) serait perdue -- et perdue
    SILENCIEUSEMENT, puisque le degat, lui, serait juste."""
    m = _require(fury_case(name))
    assert m["accord_effet"], (
        "effet 1320 : natif sur %s vs port sur %s" % (m["fury_live"], m["fury_port"]))
    assert m["fury_live"], "aucun effet 1320 pose cote natif -- montage non discriminant"
    # l'effet suit le degat : tout ce qui a ete frappe porte l'effet.
    assert set(m["fury_live"]) == set(m["cible_live"]), (
        "natif : frappes %s mais effet sur %s" % (m["cible_live"], m["fury_live"]))


def test_gate_fire_avec_UN_SEUL_ennemi_adjacent(fury_case):
    """LE GATE : `!AmountIsZero(Damageable(AdjacentEnemies(Caster)))` doit passer a **UN** adjacent.

    `AmountIsZero(x)` = `NOT( AmountIsGreater(x, minAmount = <DSLFormulas+0x20>) )` et
    `AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend `minAmount < count`. Lire `minAmount = 1`
    (la valeur que le MEME offset porte cote `maxTargets`) donnerait un gate `count > 1`, donc un
    passif INERTE contre un ennemi isole. Ce test mesure l'inverse, et c'est ce qui fixe
    `minAmount = 0` -- une lecture d'offset ne pouvait pas le faire, les deux etant en conflit."""
    m = _require(fury_case("solo"))
    assert m.get("adj_atteint") == 1, (
        "montage non discriminant : %s ennemi(s) adjacent(s) a la tuile atteinte, il en faut "
        "EXACTEMENT 1" % m.get("adj_atteint"))
    assert m["cible_live"], (
        "le natif n'a RIEN frappe avec un seul ennemi adjacent -- le gate serait `count > 1`, et "
        "le port (`count > 0`) sur-declencherait")


def test_regime_chaine_non_degenere(fury_case):
    """GARDE DE VALEUR DES TESTS EUX-MEMES : au moins une mesure a frappe DEUX cibles.

    Avec une seule cible, ni le saut de chaine ni `maxTargets` ne sont exerces -- les trois tests
    ci-dessus diraient seulement << le port frappe l'ennemi adjacent >>. Ce test existe pour que la
    degradation du montage (spawns qui changent, board retire) se VOIE au lieu d'affaiblir
    silencieusement les autres."""
    lens = {}
    for name in sorted(CASES):
        m = fury_case(name)
        if not m.get("err"):
            lens[name] = m.get("chain_len_live")
    assert lens, "aucune mesure exploitable"
    assert any((n or 0) >= 2 for n in lens.values()), (
        "aucune mesure en regime de CHAINE (longueurs mesurees : %s) -- ni le saut ni `maxTargets` "
        "ne sont discrimines" % lens)


def test_mutants_mordent_sur_l_union_des_deux_regimes(fury_case):
    """CONTRE-EPREUVE : chaque mutation d'un littéral ou d'un etage LU doit MORDRE quelque part.

    ⚠ L'UNION est le bon critere, et c'est une MESURE, pas une commodite : `nrOfHits = 1` est
    INERTE sur MC1_63 parce que le canal `AttackHitsWithModifiers` y rabat DEJA les coups a 1 (lu :
    `hits demandes=2 -> coups JOUES=1` des deux cotes), tandis que `SortByFormula lie subject seul`
    et `null-guard avant le tirage` sont inertes sur MC1_67, ou l'argmax du tri coincide avec le
    premier de l'ordre source et ou tous les candidats ont une seconde cible. Exiger que TOUS
    mordent sur CHAQUE couple ferait donc rougir un port JUSTE.

    Un mutant `mord is None` = le harnais a leve : verdict INDISPONIBLE, jamais un vert (mesure du
    2026-08-11 : un `NameError` d'instrumentation avait fait passer 7/7)."""
    par_mutant: dict = {}
    casses: dict = {}
    for name in sorted(CASES):
        m = fury_case(name)
        if m.get("err"):
            continue
        for x in (m.get("mutants") or []):
            if x["mord"] is None:
                casses.setdefault(x["mutant"], []).append((name, x.get("detail")))
                continue
            par_mutant.setdefault(x["mutant"], []).append(bool(x["mord"]))
    assert not casses, "mutant(s) CASSE(S) -- verdict indisponible : %s" % casses
    assert par_mutant, "aucun mutant joue"
    inertes = sorted(k for k, v in par_mutant.items() if not any(v))
    assert not inertes, (
        "mutant(s) INERTE(S) sur les DEUX regimes -- le port n'est pas discrimine sur cet axe : %s"
        % inertes)
