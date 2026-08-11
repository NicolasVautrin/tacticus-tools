"""GARDE LIVE de `1319 LegacyOfCombat` (#928) -- la face COMBAT, ses DEUX branches.

Avant #928 le passif etait un **NO-OP SILENCIEUX**, et son absence etait MESUREE sans etre nommee
comme telle : `probe_509` comptait `2 x <tous les coups natifs>` = 18 tirages `genrand_int32` la ou
le port n'en consommait que 6 -- l'ecart, exactement, etant les 6 coups de 1319. Aucun test ne
rougissait : le port ne jouait simplement pas une attaque que le natif joue.

CE QUE LE PORT DOIT PRODUIRE, et ce que ce fichier garde :

    On(0xb = UnitAbility) & OwnerIsActor & !CurrentAbilityIs(1319)
      & AmountIsEqual(TimesAttackMadeThisTurn(Owner, null), Direct(1))
    -> If( AmountIsGreaterThanZero(First(SortByDamagePrediction(Randomize(BigTargets adjacents)))),
           AttackWithAttackDamage(ce Big Target, minDmg_2/maxDmg_2, Piercing, nrOfHits_2 = 1),
           AttackWithAttackDamage(TOUS les ennemis adjacents, minDmg/maxDmg, Power, nrOfHits = 3) )

DEUX BRANCHES, et le fichier EXIGE les deux -- un montage qui n'en exercerait qu'une laisserait
l'autre invalidee :

  * `adjacents`   -- `necroWarden` + `necroOverlord` adjacents, AUCUN `BigTarget` : 3x Power sur
                     CHACUN (6 coups, 2 cibles distinctes) ;
  * `big_target`  -- `astraBullgryn` (trait `BigTarget`) adjacent : 1x Piercing sur LUI SEUL.

CE QUI EST ASSERTIONNE :
  * le DELTA DE PV PAR CIBLE, port contre natif -- l'observable de bout en bout, qui ne depend
    d'aucun canal de diagnostic (les `UnitDamaged` natifs des coups declenches ne portent pas
    d'`Active_Ability_Type`) ;
  * les TIRAGES `genrand_int32` consommes, port contre natif -- l'etage qui separe une faute
    d'ARITHMETIQUE d'une faute de STRUCTURE, et le seul qui puisse voir la DOUBLE evaluation du
    sous-arbre `Randomize` (natif 10 tirages a un Big Target, 8 sans le `Randomize`) ;
  * SIX MUTANTS PAR BRANCHE, chacun retirant UNE lecture du mirror et devant MORDRE. Ils sont
    CHOISIS PAR BRANCHE : muter la branche `else` pendant que le `If` prend la branche `then` ne
    prouverait rien, et serait un vert par pauvrete du MUTANT.

MESURE = `probe_928_legacy_of_combat.py` (ce fichier ne duplique NI le montage NI les criteres :
il appelle le probe, foyer unique -- meme discipline que `test_509_martial_inspiration_live.py`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) --
sauf indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- les deux probes : celui qui porte le montage (509) et celui qui
        # porte les criteres et les mutants (928).
        "scripts/python/probe_928_legacy_of_combat.py",
        "scripts/python/probe_509_martial_inspiration.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner.apply(ActiveAbilityMessage)`,
        # donc sa fermeture d'imports MESUREE traverse le vecteur `On(0xb)`, le dispatch de
        # triggers, le pipeline de degat, le PRNG, la couche d'effets (dont le gate
        # `CurrentAbilityIs` de 1408) et le compteur `ActorStatisticsComponent+0x24` -- tous
        # capables de deplacer une valeur bit-exacte. Enumerer les seuls fichiers de #928 serait
        # DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT ; large est sain.
        # ⚠ Les DEUX formes de glob sont necessaires : `**/` exige un segment, donc `engine/*.py`
        # n'est PAS couvert par `engine/**/*.py` seul.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1319 (`runner/operations/triggers/loki/legacy_of_combat.py` : arbre "
              "`If` + deux feuilles `AttackWithAttackDamage`), le vecteur `On(0xb = UnitAbility)` "
              "et ses DEUX emetteurs (`dispatch/ability.py`, `dispatch/attack.py`, "
              "`abilities/handler.py`), le registre `ABILITY_TRIGGERS`, le compteur "
              "`ActorStatisticsComponent+0x24` (`components.unit_attacks_made_this_turn`), le "
              "canal `att_ctx['ability_type']` que les deux feuilles alimentent -- et tout le "
              "moteur que le rejeu hors-ligne traverse. `build: True` parce que la confrontation "
              "est bit-exacte au tirage pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_509_martial_inspiration as P509                  # noqa: E402
import probe_928_legacy_of_combat as P                        # noqa: E402

SEED = 50901
TOURS = 4


def _mesure(big_target: bool):
    """Monte le runner, joue les casts, DISPOSE. Rend `None` si le host est injoignable."""
    try:
        sid = P509._sid()
    except Exception as e:                                    # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    if big_target:
        a_places = (("astraBullgryn", "6,8"), (P509.FILLER, "6,7"))
    else:
        a_places = P509.A_PLACES
    sf = os.path.join(os.environ.get("TEMP", "."),
                      "t928_%s_%d.json" % ("bt" if big_target else "adj", os.getpid()))
    try:
        m = P.mesure_live(sid, sf, SEED, P509.BOARD, [v for v, _t in a_places], a_places,
                          tours=TOURS, big_target=big_target)
    finally:
        try:
            os.remove(sf)
        except OSError:
            pass
    if m is None:
        pytest.skip("build KO -- session/host indisponible")
    return m


@pytest.fixture(scope="module")
def mesure_adjacents():
    return _mesure(big_target=False)


@pytest.fixture(scope="module")
def mesure_big_target():
    return _mesure(big_target=True)


def _casts(m):
    assert m["casts"], "montage STERILE : aucun cast de 1191 n'a pu etre joue"
    return m["casts"]


# --------------------------------------------------------------------- branche << each adjacent >>

def test_branche_adjacents_le_delta_de_PV_est_BIT_EXACT_par_cible(mesure_adjacents):
    """L'observable de bout en bout. Le natif joue, dans le MEME appel `act` que le cast de 1191,
    `nrOfHits = 3` coups Power sur CHAQUE ennemi adjacent -- donc le delta de PV de la 2e cible
    (jamais visee par 1191) est ENTIEREMENT du a 1319."""
    for c in _casts(mesure_adjacents):
        assert c["port"]["hp"] == c["hp_natif"], c


def test_branche_adjacents_le_port_frappe_AU_MOINS_DEUX_cibles(mesure_adjacents):
    """Le << each adjacent enemy >> du natif. Un port qui aurait recopie la branche `then`
    (mono-cible) rendrait UNE cible et un delta nul sur l'autre -- ce que le test precedent
    verrait, mais sans dire POURQUOI."""
    for c in _casts(mesure_adjacents):
        cibles = {t for t, _a in c["port"]["seq_1319"]}
        assert len(cibles) >= 2, c["port"]["seq_1319"]
        assert len(c["port"]["seq_1319"]) == 6, "3 coups x 2 cibles attendus"


def test_branche_adjacents_les_TIRAGES_du_port_egalent_ceux_du_natif(mesure_adjacents):
    """AVANT #928 : port 6, natif 18 (l'ecart = les 6 coups de 1319, 2 tirages chacun a
    `critChance = 0`). APRES : 18 / 18."""
    for c in _casts(mesure_adjacents):
        assert c["tirages_port"] == c["tirages_natif"], c


def test_branche_adjacents_les_SIX_mutants_MORDENT(mesure_adjacents):
    """Chacun retire UNE lecture : le registre, le profil du volet, le nb de coups, les bornes,
    le 7e argument `abilityOrEffect`, et le filtre `BigTarget` du selecteur de condition."""
    for c in _casts(mesure_adjacents):
        mut = c["mutants"]
        ref = (mut["ref"]["hp"], mut["ref"]["tirages"])
        inertes = [n for n, r in mut.items()
                   if n != "ref" and (r["hp"], r["tirages"]) == ref]
        assert not inertes, "mutants NON discriminants : %r" % (inertes,)
        assert len(mut) - 1 == 6, sorted(mut)          # `ref` + SIX mutants


# --------------------------------------------------------------------- branche << Big Target >>

def test_branche_big_target_le_delta_de_PV_est_BIT_EXACT_par_cible(mesure_big_target):
    """`astraBullgryn` porte `UnitTrait.BigTarget` : le `If` prend la branche `then`, et le natif
    ne joue qu'UN coup Piercing (`nrOfHits_2 = 1`) sur lui."""
    for c in _casts(mesure_big_target):
        assert c["port"]["hp"] == c["hp_natif"], c


def test_branche_big_target_UN_SEUL_coup_sur_UNE_SEULE_cible(mesure_big_target):
    """`nrOfHits_2 = 1` et `First(..., amount = 1)`. Un port qui aurait pris `nrOfHits` (= 3) ou
    oublie le `First` frapperait plus."""
    for c in _casts(mesure_big_target):
        assert len(c["port"]["seq_1319"]) == 1, c["port"]["seq_1319"]


def test_branche_big_target_les_TIRAGES_revelent_la_DOUBLE_evaluation(mesure_big_target):
    """4 coups (3 de 1191 + 1 de 1319) = 8 tirages, et le natif en consomme **10** : les 2 de plus
    sont le `Randomize` du sous-arbre `firstBigTarget`, evalue DEUX FOIS (condition du `If` puis
    cible de l'attaque) sur un pool de 1. Le port doit consommer les MEMES 10."""
    for c in _casts(mesure_big_target):
        assert c["tirages_port"] == c["tirages_natif"], c
        assert c["tirages_port"] == 2 * (len(c["port"]["seq_1191"])
                                         + len(c["port"]["seq_1319"])) + 2, c


def test_branche_big_target_les_SIX_mutants_MORDENT(mesure_big_target):
    """Mutants CHOISIS POUR CETTE BRANCHE (ceux de la branche `else` seraient inertes ici, le
    noeud mute n'etant pas execute) -- dont `sans_randomize`, qui ne deplace aucun montant a pool
    de 1 mais change la consommation RNG."""
    for c in _casts(mesure_big_target):
        mut = c["mutants"]
        ref = (mut["ref"]["hp"], mut["ref"]["tirages"])
        inertes = [n for n, r in mut.items()
                   if n != "ref" and (r["hp"], r["tirages"]) == ref]
        assert not inertes, "mutants NON discriminants : %r" % (inertes,)
        assert "sans_randomize" in mut and "then_hits_volet1" in mut, sorted(mut)


def test_les_DEUX_regimes_du_compteur_sont_atteints(mesure_adjacents):
    """`MartialInspiration_ExtraDamage` (1408) buffe l'attaque de 1319 par
    `CurrentAbilityIs(1319)` : a `TotalTurnsWithAttacksMade = 0` le bonus vaut 0, donc un port qui
    omettrait le 7e argument `abilityOrEffect` serait bit-exact. Le montage doit atteindre AU MOINS
    DEUX regimes, sinon l'accord ne prouve pas cette lecture."""
    regimes = sorted({c.get("compteur_live") for c in _casts(mesure_adjacents)})
    assert len(regimes) >= 2, "REGIME DEGENERE : compteurs atteints = %r" % (regimes,)
