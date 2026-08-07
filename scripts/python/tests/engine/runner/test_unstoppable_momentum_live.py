"""GARDE LIVE #498 -- le cast de `1152 UnstoppableMomentumReworked` (`orksNob` « Tanksmasha »)
CONFRONTE au natif, etage par etage.

LE CRITERE, en une question binaire : **apres un cast de 1152, l'etat resultant du PORT est-il celui
du NATIF -- trajet du caster, degat coup par coup, effets, poussees -- sur le MEME etat de depart ?**

Avant cette tranche, 1152 etait un NO-OP SILENCIEUX : absente d'`ABILITY_CLASSES`, le cast etait
choisi par la decision et l'execution l'ignorait (0 degat, 0 effet, AUCUNE erreur). Le premier test
ci-dessous garde precisement cela (`ported is True`).

Le montage vit dans `scripts/python/probe_498_unstoppable_momentum.py` (`run(phase)` + `montages()`,
SOURCE UNIQUE des arguments de build) ; ce fichier n'est que sa PORTE pytest -- il ne re-derive
aucun montage et aucune valeur.

TROIS phases jouees, choisies pour SEPARER ce qu'un total confondrait :

  * `ligne`     -- deux ennemis ALIGNES aux pas 0 et 1 : trajet complet, degat par coup, et le terme
                   `extraDmg x traversedSteps` (E4) que seule une DIFFERENCE de pas peut isoler.
  * `bigtarget` -- un BigTarget au pas 0 : l'autre branche du `If(NOT CanBeDisplaced)` (`Stunned` et
                   non `Pinned`), le refus de poussee, et l'ARRET de la charge.
  * `allie`     -- un AMI au pas 2, encadre de deux ennemis : il doit etre DEPLACE sans coup ni
                   effet negatif (le `Enemies(...)` du natif). Un port qui l'oublierait passerait
                   toutes les autres phases.

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268/#455) : un `pytest.skip` sur un
regime non atteint est un VERT qui ment. Seule l'indisponibilite du HARNAIS (pas de session Frida)
skippe, et c'est `live_session` qui la porte.

RE : `docs/rl/case-498-unstoppable-momentum.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade ENTIERE des `conftest.py` jusqu'a ce
        # repertoire porte des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest).
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/board.py", "scripts/python/hexgeo.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres.
        "scripts/python/probe_498_unstoppable_momentum.py",
        # LE MOTEUR ENTIER, deliberement : chaque phase REJOUE le cast hors-ligne sur un `State`
        # complet (`load_state` -> `ActiveAbilityMessage` -> gates de ciblage, ligne de charge,
        # pipeline de degat avec crit/block, poussees, effets, flags de tour), donc sa fermeture
        # d'imports couvre bien plus que les fichiers touches par la tranche -- PRNG, pathfinding,
        # selecteurs DSL, operations de deplacement compris, tous capables de deplacer une valeur
        # bit-exacte. Enumerer les seuls fichiers de #498 serait DECLARER TROP ETROIT, et un
        # declencheur trop etroit est un FAUX VERT ; large est sain.
        # Les DEUX formes de glob sont necessaires : `**/` exige un SEGMENT, donc `engine/*.py`
        # (racine du paquet) ne serait pas couvert par `engine/**/*.py` seul -- et
        # `scripts/python/**/*.py` seul raterait `scripts/python/board.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1152 (`abilities/loki/momentum.py` : boucle de charge, `Move`/`Attack`/"
              "`Push`/`SuppressOrStun`), son cablage (registre `ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`, "
              "masque migre depuis `TARGETING_OPTIONS_UNPORTED`), la feuille `PushToPrioritizedTiles` "
              "et le mode `prioritized_tiles` de `DisplaceUnitOperation` -- et tout le moteur que le "
              "rejeu hors-ligne traverse. `build: True` parce que les trois phases confrontent le "
              "NATIF : un changement de build deplace les valeurs d'arme, les traits (BigTarget) "
              "comme les tuiles legales.",
}

import pytest

import probe_498_unstoppable_momentum as P
from engine.entities.effect_type import EffectType
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED

MOMENTUM = P.MOMENTUM        # 1152
PINNED = int(EffectType.Pinned)      # 1065
STUNNED = int(EffectType.Stunned)    # 1162

PHASES = ("ligne", "bigtarget", "allie")


@pytest.fixture(scope="module")
def momentum_cases(live_session):
    """Le montage, UNE fois pour tout le fichier : un journal par phase. Chaque runner est DISPOSE
    par `run()` en sortie, donc rien a liberer au teardown."""
    return {ph: P.run(ph) for ph in PHASES}


# --------------------------------------------------------------------------------- E0 : le registre

def test_1152_est_au_registre_avec_ses_deux_donnees_obligatoires():
    """OFFLINE, et c'est voulu : c'est le cliquet du no-op silencieux. Une ability qui entre dans
    `ABILITY_CLASSES` pose son `TARGETING_OPTIONS` **et** son `ABILITY_ATTACK_TYPE` dans le MEME
    commit, et sort de `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction)."""
    assert MOMENTUM in ABILITY_CLASSES, "1152 absente d'ABILITY_CLASSES -- le cast reste un no-op"
    klass = ABILITY_CLASSES[MOMENTUM]
    assert getattr(klass, "TARGETING_OPTIONS", None) is not None, (
        "1152 est au registre SANS masque -> get_invalid_target_reason rend 0 sans gate")
    assert ABILITY_ATTACK_TYPE.get(MOMENTUM) == AbilityAttackType.DirectTargetAttack, (
        "litteral `AActiveAbility..ctor(this, &opts, 0)` non transcrit")
    assert MOMENTUM not in TARGETING_OPTIONS_UNPORTED, (
        "1152 declare son masque DEUX FOIS (classe du registre ET table hors-registre)")


def test_le_masque_est_celui_du_ctor_natif():
    """Transcription du litteral `.ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x10120040, 0, 0)`
    -- surcharge FLAGS DIRECTS, donc le litteral EST le masque (aucun `| preset.rules`)."""
    opts = ABILITY_CLASSES[MOMENTUM].TARGETING_OPTIONS
    assert int(opts.rules) == 0x10120040, "masque = %s, attendu 0x10120040" % hex(int(opts.rules))
    assert opts.self_cast is False
    assert opts.force_melee_target == 1, "forceMeleeTarget = 1 = RangedBool.False (enum INVERSE)"


# --------------------------------------------------------------------------------- E1..E7 : le live

def test_aucun_ecart_avec_le_natif_sur_les_trois_phases(momentum_cases):
    """LA confrontation. `run()` accumule les ecarts des 7 etages dans `fails` ; ce test les REND,
    il ne les re-derive pas (le probe est la source unique)."""
    for ph, j in momentum_cases.items():
        assert j.get("fails") == [], "ECARTS [%s] : %r" % (ph, j["fails"])


def test_le_cast_est_reellement_execute_par_le_port(momentum_cases):
    """ANTI-TAUTOLOGIE. Le test precedent compare deux etats ; il serait VERT aussi si le port
    n'avait RIEN fait et que le natif non plus. On exige donc que l'execution ait EU LIEU des DEUX
    cotes : `ported is True`, cast live accepte, et au moins UNE cible touchee par phase."""
    for ph, j in momentum_cases.items():
        assert j.get("ported") is True, "[%s] le port declare ported=False (no-op silencieux)" % ph
        assert j.get("live_ok") is True, "[%s] le cast LIVE a ete refuse" % ph
        assert j.get("off_hits"), "[%s] AUCUNE cible touchee offline -- montage degenere" % ph
        assert j.get("live_hits"), "[%s] AUCUNE cible touchee live -- montage degenere" % ph


def test_la_charge_traverse_plusieurs_hex_et_le_caster_arrive_ou_le_natif_larrete(momentum_cases):
    """E2. La phase `ligne` DOIT faire avancer le caster de plusieurs tuiles (sinon la boucle
    `ExecuteBehaviourStep` n'est pas exercee) ; la phase `bigtarget` DOIT l'arreter au 1er pas
    (i2 : « until he hits an obstacle or a Big Target »)."""
    ligne = momentum_cases["ligne"]
    assert ligne["caster_off"] != ligne["caster_from"], "la charge n'a pas bouge le caster"
    assert int(ligne["steps"]) >= 3, "seulement %s pas -- la boucle n'est pas exercee" % ligne["steps"]

    big = momentum_cases["bigtarget"]
    assert int(big["steps"]) == 1, "la charge ne s'est PAS arretee sur le BigTarget (%s pas)" % big["steps"]
    assert big["caster_off"] == big["caster_from"], (
        "le caster a franchi le BigTarget : %s -> %s" % (big["caster_from"], big["caster_off"]))


def test_le_terme_per_hex_croit_lineairement_avec_le_pas(momentum_cases):
    """E4 -- l'etage qui separe `extraDmg x traversedSteps` du degat d'arme. Sur `ligne` et `allie`,
    deux cibles a des PAS differents : le terme doit etre NUL au pas 0 (l'ennemi adjacent ne
    traverse aucun hex) et strictement proportionnel ensuite. Jamais fitter un scalaire : on exige
    la LINEARITE, pas une valeur."""
    for ph in ("ligne", "allie"):
        j = momentum_cases[ph]
        steps = {int(k): int(v) for k, v in (j.get("steps_by_target") or {}).items()}
        extra = {int(k): int(v) for k, v in (j.get("extra_by_target") or {}).items()}
        assert len(steps) >= 2, "[%s] moins de 2 cibles -- le scaling n'est pas separe" % ph
        for t, k in steps.items():
            if k == 0:
                assert extra[t] == 0, "[%s] terme non nul au pas 0 sur u%d : %d" % (ph, t, extra[t])
        pairs = sorted(((k, extra[t]) for t, k in steps.items()), key=lambda kv: kv[0])
        (k1, e1), (k2, e2) = pairs[0], pairs[-1]
        assert k2 > k1, "[%s] toutes les cibles au meme pas -- rien a separer" % ph
        assert e2 > e1, "[%s] le terme per-hex ne CROIT pas (%d -> %d)" % (ph, e1, e2)
        per_hex = (e2 - e1) // (k2 - k1)
        assert per_hex > 0 and e2 == per_hex * k2, (
            "[%s] terme NON lineaire : pas %d -> %d, pas %d -> %d" % (ph, k1, e1, k2, e2))


def test_les_deux_branches_du_if_canbedisplaced_sont_distinctes(momentum_cases):
    """E5 -- `If(NOT CanBeDisplaced(target), AddEffect(Stunned), AddEffect(Pinned))`. Une cible
    ORDINAIRE recoit `Pinned` (« Suppressed » cote UI) ; un BigTarget recoit `Stunned`. Les deux
    phases sont exigees ENSEMBLE : verifier une seule branche laisserait passer un port qui pose
    toujours le meme effet."""
    ligne = momentum_cases["ligne"]
    for t in ligne["touched"]:
        got = [e for e in (ligne["off_effects"].get(int(t)) or []) if e in (PINNED, STUNNED)]
        assert got == [PINNED], "cible ordinaire u%s : effets %r (attendu [Pinned])" % (t, got)

    big = momentum_cases["bigtarget"]
    assert big["touched"], "aucune cible touchee sur la phase bigtarget"
    for t in big["touched"]:
        got = [e for e in (big["off_effects"].get(int(t)) or []) if e in (PINNED, STUNNED)]
        assert got == [STUNNED], "BigTarget u%s : effets %r (attendu [Stunned])" % (t, got)


def test_un_ami_traverse_est_deplace_sans_degat_ni_effet(momentum_cases):
    """E7 -- i2 : « Friendly units are also displaced, but take no damage or negative effects. »
    Le temoin est NON DEGENERE : on exige que l'ami ait REELLEMENT bouge (sinon le test serait vert
    sur un montage ou la charge ne l'a jamais atteint)."""
    j = momentum_cases["allie"]
    friends = [int(f) for f in (j.get("friends") or [])]
    assert friends, "montage degenere : aucun AMI sur la ligne de charge"
    bouge = 0
    for f in friends:
        assert not (j["off_hits"].get(f) or j["live_hits"].get(f)), (
            "l'ami u%d a pris des DEGATS -- le `Enemies(...)` du natif n'est pas porte" % f)
        neg_off = [e for e in (j["off_effects"].get(f) or []) if e in (PINNED, STUNNED)]
        neg_live = [e for e in (j["live_effects"].get(f) or []) if e in (PINNED, STUNNED)]
        assert not neg_off and not neg_live, "l'ami u%d a recu un effet NEGATIF" % f
        if j["off_pos"].get(f) != j["pos_before"].get(f):
            bouge += 1
        assert j["off_pos"].get(f) == j["live_pos"].get(f), (
            "position finale de l'ami u%d : port %r != natif %r"
            % (f, j["off_pos"].get(f), j["live_pos"].get(f)))
    assert bouge >= 1, "aucun ami DEPLACE -- le montage n'exerce pas la poussee amie"


def test_les_cibles_ordinaires_sont_poussees_hors_de_la_ligne(momentum_cases):
    """E6 -- `PushToPrioritizedTiles` : une cible DEPLACABLE quitte sa tuile (le caster prend sa
    place), un BigTarget NON. Le port et le natif doivent choisir la MEME tuile de destination --
    c'est ce qui verifie l'ordre des cinq `PathDefinition` et la consommation RNG des deux
    `Randomize`."""
    ligne = momentum_cases["ligne"]
    for t in ligne["touched"]:
        t = int(t)
        assert ligne["off_pos"].get(t) != ligne["pos_before"].get(t), (
            "la cible u%d n'a PAS ete poussee" % t)
        assert ligne["off_pos"].get(t) == ligne["live_pos"].get(t), (
            "tuile de poussee de u%d : port %r != natif %r"
            % (t, ligne["off_pos"].get(t), ligne["live_pos"].get(t)))

    big = momentum_cases["bigtarget"]
    for t in big["touched"]:
        t = int(t)
        assert big["off_pos"].get(t) == big["pos_before"].get(t), (
            "le BigTarget u%d a ete POUSSE (IsDisplaceable non porte)" % t)
