"""GARDE LIVE #1083-r1 -- les CINQ passifs `PowerUp_*` de boost de stat, confrontes au natif.

Ce que cette garde exige, et de quel artefact : qu'une unite qui MARCHE sur un power-up recoive du
NATIF exactement ce que le port lui donne, rejoue depuis la MEME capture -- le bouclier commun
d'`APowerUpAbility$$AddShield` ET le boost propre au power-up ecrase.

Montage : `probe_1083r1_power_up_stat_boosts.py`. Le BOARD n'y joue AUCUN role (le canal
`PowerUpUnits` n'est lu qu'au build de la BC, cf.
`docs/rl/case-1083-powerup-le-board-ne-confronte-rien.md`) : c'est
`catalog_inject --units powup<X>` + `--explicit-stats` + `--a-units` qui amenent l'unite, et un
`--a-place` / `--place` qui la posent A COTE du ramasseur.

⚠ DEUX FAUX NEGATIFS ONT ETE MESURES SUR CE MONTAGE, et les deux crans qui les gardent sont ici :
  * `Health` est une stat FILL-UP -- le moteur ecrit dans `HealthComponent`, pas dans
    `UnitStats.components`. Une lecture par le mauvais reservoir rend un port IMMOBILE alors qu'il
    est juste ; le probe lit desormais par le MEME dispatch que l'ecriture
    (`stat_ops._fillup_component`) ;
  * `decisionView.units[].effects` publie un `name`, jamais un `type`. La premiere version lisait
    la mauvaise cle et rendait TOUJOURS `[]`, ce qui se lit comme << le natif ne pose rien >>.

⚠ TEMOIN NON DEGENERE : chaque cas nominal assertionne que le DELTA NATIF est non nul AVANT de
comparer. Un accord a zero est exactement ce qu'un port inerte rendrait.

CONTRE-BRAS : le regime `hors-tuile` deplace le ramasseur sur une tuile VOISINE. Le natif comme le
port doivent alors ne RIEN faire, et le power-up doit SURVIVRE -- c'est ce qui separe << le port
joue le trigger >> de << le port buffe a chaque deplacement >>. ASCII only.
"""
from __future__ import annotations

#: LIVE : le verdict depend du NATIF, donc de la session et du build -- aucun ensemble de chemins du
#: depot ne le determine. `toujours: True` est un RESULTAT.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1083r1_power_up_stat_boosts.py",
        "scripts/python/engine/runner/operations/triggers/loki/power_up.py",
        "scripts/python/engine/entities/effects/loki/power_up.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/runner/operations/stat_ops.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/catalog_inject.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": True,
    "raison": "Confrontation AU NATIF : les cinq `powup*` sont amenes par `catalog_inject` + "
              "`--explicit-stats`, le crush est joue par un `applyAction` de MOUVEMENT reel, et les "
              "stats confrontees sortent du jeu (`combatSnapshot.units[].stats`), pas du depot. Se "
              "rejoue donc a chaque passe live.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

import probe_1083r1_power_up_stat_boosts as P                             # noqa: E402

#: Les cinq cas, avec le DELTA attendu (derive du gameconfig, jamais code en dur ici : c'est la
#: FORME qui est fixee -- additif plat vs pourcentage de la part INITIAL du stat).
CAS_NOMINAUX = ("armor", "damage", "health", "hits", "meleehits")


@pytest.fixture(scope="module")
def mesures(rpc):
    """Les cinq mesures nominales + une contre-epreuve, un runner chacune, disposes par le probe.
    ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    out = {}
    for cas in CAS_NOMINAUX:
        r = P.run(rpc, cas, "nominal")
        if not r.get("ok"):
            pytest.fail("montage PowerUp %s NON INSTALLE : %s" % (cas, r.get("why")))
        out[cas] = r
    r = P.run(rpc, "damage", "hors-tuile")
    if not r.get("ok"):
        pytest.fail("contre-epreuve hors-tuile NON INSTALLEE : %s" % (r.get("why"),))
    out["hors-tuile"] = r
    return out


def _deltas(m):
    return (int(m["natif_apres"]) - int(m["natif_avant"]),
            int(m["port_apres"]) - int(m["port_avant"]),
            m["shield_natif"][1] - m["shield_natif"][0],
            m["shield_port"][1] - m["shield_port"][0])


@pytest.mark.parametrize("cas", CAS_NOMINAUX)
def test_le_power_up_est_bien_MONTE_et_ECRASE(mesures, cas):
    """PREMISSE, pas observable : sans l'entree catalogue l'unite n'apparait meme pas (echec
    SILENCIEUX mesure dans la case-doc), et sans crush il n'y a pas de vecteur `On(1)`."""
    m = mesures[cas]
    assert m["powup_vivant_natif"] is False, (
        "le power-up %s n'a PAS ete ecrase cote natif -- le vecteur `On(1 = PreUnitDeath)` n'a pas "
        "eu lieu, la mesure ne conclut RIEN : %s" % (cas, m))
    assert m["powup_vivant_port"] is False, (
        "le power-up %s survit cote PORT : `_kill_steppable_units` ne l'a pas vu" % cas)


@pytest.mark.parametrize("cas", CAS_NOMINAUX)
def test_le_temoin_est_NON_DEGENERE(mesures, cas):
    """Le natif doit avoir REELLEMENT bouge la stat ET pose un bouclier. A delta nul, un port
    integralement inerte passerait pour juste."""
    d_nat, _, ds_nat, _ = _deltas(mesures[cas])
    assert d_nat != 0, ("cas %s : le NATIF n'a pas bouge la stat %s -- temoin degenere"
                        % (cas, mesures[cas]["stat"]))
    assert ds_nat > 0, "cas %s : le NATIF n'a pose AUCUN bouclier -- temoin degenere" % cas


@pytest.mark.parametrize("cas", CAS_NOMINAUX)
def test_PORT_le_meme_boost_que_le_natif(mesures, cas):
    """L'observable : meme delta de stat, meme bouclier, meme effet pose."""
    m = mesures[cas]
    d_nat, d_port, ds_nat, ds_port = _deltas(m)
    assert d_port == d_nat, ("cas %s : delta %s natif=%d port=%d (avant nat=%s port=%s)"
                             % (cas, m["stat"], d_nat, d_port, m["natif_avant"], m["port_avant"]))
    assert ds_port == ds_nat, ("cas %s : bouclier natif=%d port=%d -- `AddShield` est COMMUN aux "
                               "cinq (`shieldPct %% de la part INITIAL de Health`)"
                               % (cas, ds_nat, ds_port))
    assert m["effet_pose_natif"] and m["effet_pose_port"], (
        "cas %s : l'effet %s doit etre pose des DEUX cotes (natif=%s port=%s)"
        % (cas, m["effet_attendu"], m["effets_natif"], m["effets_port"]))


def test_PowerUp_Health_remplit_AUSSI_les_PV_COURANTS(mesures):
    """Le volet HEALTH d'`AddPctBasedBoost` a DEUX etages : le stat-mod monte le MAXIMUM, et un
    `ChangeStat(Health, Add, <le meme montant>)` remplit les PV COURANTS. Sans le second, un +200 %
    de PV max laisserait l'unite au meme nombre de PV -- et le port passerait quand meme le test de
    delta ci-dessus, qui ne lit que le maximum."""
    m = mesures["health"]
    dh_nat = m["hp_natif"][1] - m["hp_natif"][0]
    dh_port = m["hp_port"][1] - m["hp_port"][0]
    assert dh_nat > 0, "le NATIF n'a pas rempli les PV courants -- temoin degenere : %s" % m
    assert dh_port == dh_nat, "PV courants : natif=%d port=%d" % (dh_nat, dh_port)


@pytest.mark.parametrize("cas", ("hits", "meleehits"))
def test_le_boost_ABSOLU_reste_PLAT(mesures, cas):
    """`PowerUp_Hits` / `PowerUp_MeleeHits` sont construits avec `isMultiply = 0` (lambdas
    `EffectsDatabase.<InitializeEffects>b__14_169/170`), donc `StatPart.Modification` (5) : le
    montant est la CONSTANTE `extraHit` elle-meme. Ce cran fige la FORME : si un jour le port les
    faisait passer par le chemin multiplicatif, le delta deviendrait un pourcentage de la part
    INITIAL du stat -- enorme, et ce test le verrait."""
    m = mesures[cas]
    d_nat, _, _, _ = _deltas(m)
    assert 0 < d_nat <= 32, (
        "cas %s : delta %s = %d -- un `extraHit` PLAT vaut quelques unites ; une valeur de cet "
        "ordre de grandeur trahirait un passage par la voie MULTIPLICATIVE" % (cas, m["stat"], d_nat))


def test_le_boost_PCT_est_bien_MULTIPLICATIF(mesures):
    """Le pendant du precedent, sur l'autre branche : `PowerUp_Damage` est construit avec
    `isMultiply = 1`, donc `StatPart.MultiplierModification` (9) -> `ValueModification.
    MultiplyModifier` -> `initialValue * dmgPct / 100`. Lire `AddPctBasedBoost` seul ferait ecrire
    un `+dmgPct` PLAT (`+100` d'attaque au lieu d'un DOUBLEMENT) : c'est la faute que ce cran
    interdit, et elle a ete commise avant d'etre mesuree."""
    m = mesures["damage"]
    d_nat, d_port, _, _ = _deltas(m)
    avant = int(m["natif_avant"])
    assert avant > 0, "attaque initiale nulle -- le test ne separerait rien"
    assert d_nat > avant // 2, (
        "delta attaque = %d pour une attaque initiale de %d : un montant PLAT (`dmgPct` = quelques "
        "centaines) ne peut pas atteindre cet ordre de grandeur -- si ce test tombe, verifier "
        "d'abord que le natif n'a pas change de flag `isMultiply`" % (d_nat, avant))
    assert d_port == d_nat


def test_CONTRE_BRAS_hors_tuile_les_DEUX_sont_INERTES(mesures):
    """Le ramasseur se deplace A COTE du power-up : aucun crush, donc aucun `On(1)`, donc rien.
    Sans ce bras, un port qui bufferait a CHAQUE deplacement passerait tous les tests ci-dessus."""
    m = mesures["hors-tuile"]
    assert m["powup_vivant_natif"] is True, (
        "le power-up est mort alors que le ramasseur ne l'a PAS traverse -- la contre-epreuve ne "
        "separe rien : %s" % m)
    d_nat, d_port, ds_nat, ds_port = _deltas(m)
    assert (d_nat, d_port, ds_nat, ds_port) == (0, 0, 0, 0), (
        "hors tuile, NI le natif NI le port ne doivent rien faire : %s" % (m,))
    assert not m["effet_pose_port"], (
        "le port a pose %s sans crush -- son trigger ne lit pas `HasDeathReason(Steppable)`"
        % m["effet_attendu"])
