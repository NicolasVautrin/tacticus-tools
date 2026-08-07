"""GARDE de `1132 KillMaimBurn` (#504) -- la face COMBAT, bande par bande.

Avant #504 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la face
DECISION la choisissait (playbook porte depuis #362) et l'execution l'ignorait -- 0 degat, 0 effet,
AUCUNE erreur. Ce fichier garde ce que le port doit desormais produire, confronte au NATIF sur le
MEME substrat (le port rejoue le cast depuis la capture prise juste avant le cast natif), dans
DEUX regimes qui exercent des chemins DIFFERENTS de `KillMaimBurnAbility$$GetNextTarget` :

  R1 `survivant`   personne ne meurt -> `IsAlive(previousTarget)` VRAI partout -> les TROIS bandes
                   frappent la MEME cible et AUCUN tirage de tri n'est consomme. C'est le regime
                   qui isole les trois plages / profils / comptes de coups (1x `Piercing`,
                   6x `Eviscerate`, 1x `Plasma`).
  R4 `pool elargi` la bande 1 tue la cible du message, la bande 2 tue le re-cible, et les deux
                   survivants sont HORS adjacence -> le pool de `t2` est VIDE, `.Otherwise` rend le
                   cadavre, `IsAlive` est FAUX, et la bande 3 consulte ENFIN son propre pool
                   `Unobscured(SurroundingEnemies(caster, range = 2))`.

CE QUI EST ASSERTIONNE, et pourquoi ce n'est pas un total :
  * la SEQUENCE coup par coup (8 `UnitDamaged` natifs vs les `per_hit_health` capes du port) --
    un critere sur le TOTAL serait reste VERT sur les DEUX bugs que ce cas a trouves, parce que
    les cibles surtuees rendent le meme delta quelle que soit la valeur des coups ;
  * le NOMBRE DE TIRAGES `genrand_int32` consommes, PORT vs NATIF. C'est l'etage qui LOCALISE :
    comptes egaux + montants differents = arithmetique ; comptes differents = STRUCTURE ;
  * les SEPT contre-epreuves, chacune ne changeant QU'UNE lecture du mirror. `AB5` (pool de la
    bande 3 rabattu sur `AdjacentEnemies`) ne diverge QUE dans R4 : c'est ce qui rend ce regime
    obligatoire.

MESURE = `probe_504_kill_maim_burn.py` (ce fichier ne duplique NI le montage NI les criteres : il
appelle le probe, foyer unique -- meme discipline que `test_500_foul_infusion_live.py`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) --
sauf indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        # Elles portent des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest) -- donc aucun graphe d'imports ne les verrait.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres :
        "scripts/python/probe_504_kill_maim_burn.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner.apply(ActiveAbilityMessage)`,
        # donc sa fermeture d'imports MESUREE traverse le pipeline de degat, le PRNG, le
        # pathfinding, la cascade de ciblage, le tri par utilite et la couche d'effets -- tous
        # capables de deplacer une valeur bit-exacte. Enumerer les seuls fichiers de #504 serait
        # DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT ; large est sain.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul -- et
        # `scripts/python/**/*.py` seul raterait `scripts/python/board.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1132 (arbre DSL `runner/abilities/worldeaters.py` : trois bandes "
              "`AttackWithAttackDamage` a volets `_2`/`_3`, noeud de re-ciblage "
              "`KillMaimBurnNextTarget`, selecteurs `AdjacentEnemies`/`SurroundingEnemies`/"
              "`Unobscured`/`non_steppable_or_object_units`/`Otherwise`, tri "
              "`operations/damage_utility`), le noeud PARTAGE `entities/behaviours.Group` (dont "
              "#504 a corrige l'evaluation du selecteur de groupe), son cablage (registre "
              "`ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`, masque migre depuis `targeting.py`) -- et "
              "tout le moteur que le rejeu hors-ligne traverse. `build: True` parce que la "
              "sequence confronte le NATIF au tirage pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_504_kill_maim_burn as P                          # noqa: E402


def _mesure(regime, avec_ab):
    try:
        sid = P._sid()
    except Exception as e:                                    # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t504_%s_%s.json" % (regime, os.getpid()))
    m = P.mesure(sid, sf, regime, avec_ab=avec_ab)
    if m is None:
        pytest.skip("build KO -- session/host indisponible")
    try:
        yield m
    finally:
        try:
            os.remove(sf)
        except OSError:
            pass


@pytest.fixture(scope="module")
def r1():
    """Regime SURVIVANT : un seul montage, un seul cast natif, un seul rejeu porte."""
    yield from _mesure("R1", False)


@pytest.fixture(scope="module")
def r4():
    """Regime POOL ELARGI + les sept contre-epreuves (le runner est cher : une seule mesure)."""
    yield from _mesure("R4", True)


# ---------------------------------------------------------------- 0. le cablage, hors live

def test_le_cablage_du_registre_est_complet():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType`
    DANS LE MEME COMMIT, et SORT de `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : une
    ability a UNE source de masque, jamais deux). Sans masque, `get_invalid_target_reason` rend 0
    et le moteur accepte des casts que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    cls = ABILITY_CLASSES.get(P.KILL_MAIM_BURN)
    assert cls is not None, "1132 absente d'ABILITY_CLASSES : c'est le NO-OP d'avant #504"
    assert P.KILL_MAIM_BURN not in TARGETING_OPTIONS_UNPORTED, (
        "1132 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (disjonction rompue)")
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "1132 au registre SANS masque = gate de ciblage DESARME"
    # `<TargetingOptions statics>+0x68` = `<preset +0x40>+0x28` = 0x4000, LU dans le cctor.
    assert int(opts.rules) == int(TR.TargetIsEnemy), (
        "masque 1132 = %r, attendu TargetIsEnemy seul (0x4000)" % (opts.rules,))
    # 3e argument d'`AActiveAbility$$.ctor` -- litteral `0`, transcrit tel quel.
    assert ABILITY_ATTACK_TYPE.get(P.KILL_MAIM_BURN) == AbilityAttackType.DirectTargetAttack


# ---------------------------------------------------------------- 1. regime SURVIVANT

def test_r1_le_cast_est_porte_et_le_natif_a_bien_agi(r1):
    """Le prealable : sans lui, un desaccord ne dirait pas de quel cote il vient."""
    assert r1["port"]["ported"] is True, (
        "1132 non portee (retour du handler) -- c'est le NO-OP SILENCIEUX d'avant #504")
    assert r1["natif"]["seq"], "le cast NATIF n'a inflige AUCUN degat : rien a confronter"


def test_r1_trois_bandes_une_seule_cible_et_huit_coups(r1):
    """`nrOfHits`=1 `Piercing` + `nrOfHits_2`=6 `Eviscerate` + `nrOfHits_3`=1 `Plasma` = 8 coups,
    TOUS sur la cible du message puisque personne ne meurt. Trois profils NATIFS distincts dans
    l'ordre 1-6-1 : c'est la lecture des volets `_2`/`_3` (`MinMaxDamage2`/`MinMaxDamage3`,
    `GetDamageProfile2`/`GetDamageProfile3`, `ConfigConst(0x32)`/`ConfigConst(0x66)`)."""
    prof = r1["natif"]["profils"]
    assert len(prof) == 8, "8 coups attendus (1 + 6 + 1), natif : %r" % (prof,)
    assert len(set(prof)) == 3, "trois profils DISTINCTS attendus, natif : %r" % (prof,)
    assert prof[1:7] == [prof[1]] * 6, "la bande du milieu doit porter 6 coups d'un seul profil"
    assert prof[0] != prof[1] and prof[7] != prof[1] and prof[0] != prof[7]
    cibles = {t for t, _a in r1["natif"]["seq"]}
    assert cibles == {r1["cible"]}, (
        "R1 : personne ne meurt, les trois bandes doivent frapper la cible du message -- %r" % (cibles,))


def test_r1_sequence_et_tirages_bit_exacts(r1):
    """L'accord AU COUP PRES et AU TIRAGE PRES. `E4'` est ce qui distingue une divergence
    d'arithmetique d'une divergence de STRUCTURE : en R1 le `If` court-circuite, donc AUCUN tri
    n'est evalue et le compte de tirages doit valoir exactement 2 par coup."""
    assert r1["port"]["seq"] == r1["natif"]["seq"], (
        "SEQUENCE PORT=%r NATIF=%r" % (r1["port"]["seq"], r1["natif"]["seq"]))
    assert r1["port"]["delta"] == r1["natif"]["delta"]
    assert r1["port"]["tirages"] == r1["natif"]["tirages"] is not None, (
        "tirages PORT=%r NATIF=%r" % (r1["port"]["tirages"], r1["natif"]["tirages"]))
    assert r1["port"]["tirages"] == 2 * len(r1["natif"]["seq"]), (
        "R1 ne doit consommer QUE les tirages d'attaque (2 par coup a cc=0) : %r"
        % (r1["port"]["tirages"],))
    assert not any(n["rolls"] for n in (r1["port"]["nt2"], r1["port"]["nt3"])), (
        "R1 : aucune cible ne meurt, donc le `If` court-circuite et AUCUN tri ne doit tirer -- %r"
        % ((r1["port"]["nt2"], r1["port"]["nt3"]),))


# ---------------------------------------------------------------- 2. regime POOL ELARGI

def test_r4_le_montage_descend_bien_jusqu_au_pool_de_la_bande_3(r4):
    """LE PREALABLE de R4. Trois unites DIFFERENTES doivent etre frappees, la derniere etant celle
    a DISTANCE 2 -- sinon la bande 3 n'aurait jamais consulte son propre pool et l'accord des
    etages suivants ne prouverait pas ce qu'on croit."""
    ids = r4["ids"]
    cibles = [t for t, _a in r4["natif"]["seq"]]
    assert len(set(cibles)) == 3, "R4 : trois cibles distinctes attendues -- %r" % (cibles,)
    assert cibles[-1] == ids[P.FOE_FAR], (
        "la DERNIERE bande doit frapper l'unite a distance 2 (%s) -- %r" % (P.FOE_FAR, cibles))
    assert any(p[0] == "otherwise" for p in r4["port"]["nt2"]["picks"]), (
        "le pool de la bande 2 doit s'etre VIDE (branche `.Otherwise(previousTarget)`) -- %r"
        % (r4["port"]["nt2"]["picks"],))
    assert any(p[0] == "retarget" for p in r4["port"]["nt3"]["picks"]), (
        "la bande 3 doit avoir TRIE son propre pool -- %r" % (r4["port"]["nt3"]["picks"],))


def test_r4_sequence_et_tirages_bit_exacts(r4):
    """Meme accord qu'en R1, mais sur le chemin qui TRIE : les tirages de
    `SortUnitsByDamageUtilitySelector$$Select` (`RandomAmount(minDmg_2, maxDmg_2)`) entrent dans le
    flux, et le compte doit tomber juste des deux cotes."""
    assert r4["port"]["seq"] == r4["natif"]["seq"], (
        "SEQUENCE PORT=%r NATIF=%r" % (r4["port"]["seq"], r4["natif"]["seq"]))
    assert r4["port"]["delta"] == r4["natif"]["delta"]
    assert r4["port"]["tirages"] == r4["natif"]["tirages"] is not None, (
        "tirages PORT=%r NATIF=%r -- un ECART ici est STRUCTUREL (une evaluation de selecteur en "
        "trop ou en moins), pas arithmetique" % (r4["port"]["tirages"], r4["natif"]["tirages"]))
    assert r4["port"]["tirages"] > 2 * len(r4["natif"]["seq"]), (
        "R4 doit consommer des tirages DE TRI en plus des tirages d'attaque : %r"
        % (r4["port"]["tirages"],))


def test_r4_les_sept_contre_epreuves_ecartent_toutes_du_natif(r4):
    """LA garde du cas. Un accord ne vaut que si le desaccord etait POSSIBLE : chaque variante ne
    change QU'UNE lecture du mirror, et chacune doit s'ecarter du natif.

    `AB3` (ordre inverse) et `AB5` (pool de la bande 3 rabattu sur `AdjacentEnemies`) sont celles
    qui comptent : elles rendent le MEME nombre de coups que la reference."""
    nat_total = sum(v for i, v in r4["natif"]["delta"].items() if i != r4["caster"])
    ref = r4["ab"]["REF"]
    assert ref["total"] == nat_total, (
        "le mirror hors-ligne (%s) doit reproduire le total natif (%s)" % (ref["total"], nat_total))
    identiques = [nom for nom, v in r4["ab"].items()
                  if nom != "REF" and v["total"] == ref["total"] and v["delta"] == ref["delta"]]
    assert identiques == [], (
        "contre-epreuve(s) NON discriminante(s) : %r -- le montage ne mesure pas ces lectures"
        % (identiques,))
