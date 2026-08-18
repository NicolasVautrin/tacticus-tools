"""#951-r4 -- le `ownerNeedsToBeAlive: true` de `FireOfAbsolution` : VERDICT MESURE, et le CLIQUET
qui empeche de le porter par erreur.

PORTE PYTEST du montage `probe_951r4_fire_of_absolution_owner_alive.py` : le probe MESURE
(`adeptRetributor` tire sur `darkaHellblaster`, qui riposte via `GrimRetribution`), ce module
ASSERTE. Aucun montage n'est duplique ici.

## CE QUE CE FICHIER ETABLIT

Le conjoint EXISTE au decompile -- `DSLTriggers$$On(0x4a, ownerNeedsToBeAlive)` construit
`EventTypeTrigger(0x4a) & <DSLTriggers+0x20>`, et ce slot porte `OwnerIsAliveAbilityTrigger`
(`IsUnit(Owner) ? UnitExtensions$$IsAlive(owner, state) : true`). La question n'est donc pas s'il
existe, mais s'il peut MORDRE. Mesure :

  * l'ORDRE natif du flux est `arme -> SPLASH -> riposte` (1er coup de splash **#4**, 1er coup porte
    SUR le caster **#10**). `ExecuteAtomic(this, b, entities, 0x3d)` enveloppe
    `GetAttackDamageBehaviour` ET `EvaluateAbilities(0x4a)` : les abilities declenchees par `On(9)`
    sont mises en FILE et jouees a la SORTIE du groupe. L'owner est donc VIVANT a `On(0x4a)` --
    toujours, et pas << parce qu'il vient de frapper >>, la raison qu'ecrivait la fiche ;
  * le natif applique le MEME splash (**18 714**) que Vindicta survive ou meure : c'est la preuve
    ARITHMETIQUE que la riposte n'a pas encore mordu quand le splash est calcule ;
  * le PORT, lui, joue la riposte AVANT ce vecteur : son splash tombe a **14 970** (-20 %, une perte
    de membre d'escouade). Divergence de RANG, PREEXISTANTE -- residu `#951-r9` ;
  * **poser le gate mettrait le splash du port a ZERO** (contre-epreuve `WITHGATE`), transformant
    une divergence de 20 % en no-op complet.

Le cliquet de ce fichier est donc : *le port applique un splash NON NUL meme quand son caster est
mort*. Quiconque poserait le gate sans avoir ferme `#951-r9` le fait rougir.

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[3]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_951r4_fire_of_absolution_owner_alive as P     # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_951r4_fire_of_absolution_owner_alive.py",
        # Le passif et son vecteur imperatif -- c'est LA qu'un gate `ownerNeedsToBeAlive` serait pose.
        "scripts/python/engine/runner/operations/triggers/loki/fire.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/ability.py",
        # Le RANG : c'est ce site qui appelle le vecteur `On(0x4a)`, apres le pipeline d'attaque.
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # La riposte qui tue le caster, et le predicat de vivacite que le gate lirait.
        "scripts/python/engine/runner/operations/triggers/loki/grim_retribution.py",
        "scripts/python/engine/entities/effects/loki/counter_attack.py",
        "scripts/python/engine/runner/components.py",
        # Le harnais qui monte la bataille et rejoue le coup offline.
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/rl_duel.py", "scripts/python/tests/conftest.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("Verdict LIVE sur le `ownerNeedsToBeAlive` de `FireOfAbsolution` : tout ce qui "
               "change le RANG du vecteur `On(0x4a)`, le predicat de vivacite, la riposte qui tue "
               "le caster ou le splash lui-meme peut retourner le verdict. `build: True` parce que "
               "l'ORDRE du flux natif est lu dans le jeu."),
}


class _Args:
    """Les memes defauts que le CLI du probe -- un objet plutot qu'un `argparse.Namespace` pour
    que le montage du test soit LISIBLE au site."""

    def __init__(self, survivant: bool):
        self.seed = "777"
        self.board = "MC1_67"
        self.defender = P.DEFENDER          # `darkaHellblaster` : riposte `GrimRetribution`
        self.voisin1 = "necroWarden"
        self.voisin2 = "necroOverlord"
        self.dist = 2                       # >= 2, sinon la riposte est DESARMEE
        self.hp_target = 900000
        self.hp_carrier = 2000              # la riposte (~2000 mesures) TUE Vindicta
        self.hp_survivant = 900000
        self.essais = 8
        self.survivant = survivant
        self.verbose = False


def _mesure(rpc, build_runner, survivant: bool):
    a = _Args(survivant)
    r = build_runner(seed=a.seed, board=a.board, extra=[
        "--p-units", "%s,%s" % (P.CARRIER, P.ALLY),
        "--a-units", "%s,%s,%s" % (a.defender, a.voisin1, a.voisin2),
        "--hp-target", str(a.hp_target),
        "--hp-player", str(a.hp_survivant if survivant else a.hp_carrier),
        "--no-ai", "--crit", "0,0", "--crit-target", "0,0",
        "--block-target", "0,0", "--block-player", "0,0"])
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    return P.mesurer(a, rpc, Board, ChargeRegimeHarness, r["rid"])


@pytest.fixture(scope="module")
def bras_regime(rpc, build_runner):
    return _mesure(rpc, build_runner, survivant=False)


@pytest.fixture(scope="module")
def bras_survivant(rpc, build_runner):
    return _mesure(rpc, build_runner, survivant=True)


def _exige_regime(m, mort_attendue):
    """Un montage rate n'est PAS un accord : il doit FAIRE ECHOUER, jamais passer en silence."""
    if not m.get("ok"):
        pytest.fail("regime NON ATTEINT (%s) : %s" % (m.get("bras"), m.get("why")), pytrace=False)
    av, ap = m["rec"]["hp_cible_avant"], m["live"].get("hp_cible")
    if av is None or ap is None or int(ap) >= int(av):
        pytest.fail("la CIBLE n'a pris AUCUN degat live (%s -> %s) -- l'attaque n'a pas eu lieu "
                    "(hors portee ?), il n'y a rien a comparer" % (av, ap), pytrace=False)
    if bool(m["live"]["caster_mort"]) is not bool(mort_attendue):
        pytest.fail("le bras n'a pas produit son regime (caster_mort=%s, attendu=%s)"
                    % (m["live"]["caster_mort"], mort_attendue), pytrace=False)


def test_le_caster_MEURT_bien_dans_le_bras_regime(bras_regime):
    """Sans la mort du caster, le gate n'aurait rien a mordre et le bras ne discriminerait rien."""
    _exige_regime(bras_regime, mort_attendue=True)
    assert bras_regime["live"]["caster_mort"] is True, bras_regime["live"]


def test_le_NATIF_riposte_APRES_le_splash(bras_regime):
    """L'etage qui tranche `#951-r4` : `ExecuteAtomic` draine les abilities declenchees par `On(9)`
    a la SORTIE du groupe, donc l'owner est vivant quand `On(0x4a)` part."""
    _exige_regime(bras_regime, mort_attendue=True)
    o = bras_regime["ordre"]
    assert o["splash"] is not None and o["riposte"] is not None, o
    assert o["riposte"] > o["splash"], ("le natif riposte AVANT le splash (#%s < #%s) -- alors le "
                                        "gate `ownerNeedsToBeAlive` MORDRAIT et il faudrait le "
                                        "porter" % (o["riposte"], o["splash"]))


def test_le_NATIF_applique_le_splash_MALGRE_la_mort_du_caster(bras_regime):
    _exige_regime(bras_regime, mort_attendue=True)
    assert bras_regime["splash_live"] > 0, bras_regime["splash_live"]


def test_le_natif_applique_le_MEME_splash_que_le_caster_meure_ou_non(bras_regime, bras_survivant):
    """Preuve ARITHMETIQUE que la riposte n'a pas mordu quand le splash est calcule : les deux bras
    ne different que par les PV du caster, et le natif rend la MEME somme."""
    _exige_regime(bras_regime, mort_attendue=True)
    _exige_regime(bras_survivant, mort_attendue=False)
    assert bras_regime["splash_live"] == bras_survivant["splash_live"], \
        (bras_regime["splash_live"], bras_survivant["splash_live"])


def test_le_port_est_BIT_EXACT_quand_personne_ne_meurt(bras_survivant):
    """Le bras TEMOIN etablit que le port sait faire ce splash -- sans lui, l'ecart du bras REGIME
    ne dirait pas s'il s'agit d'un rang ou d'un port absent."""
    _exige_regime(bras_survivant, mort_attendue=False)
    assert bras_survivant["splash_port"] == bras_survivant["splash_live"], \
        (bras_survivant["splash_port"], bras_survivant["splash_live"])


def test_CLIQUET_le_port_applique_un_splash_NON_NUL_meme_caster_mort(bras_regime):
    """LE cliquet de `#951-r4`. Poser le gate `ownerNeedsToBeAlive` sur le vecteur imperatif met ce
    splash a ZERO (cf. la contre-epreuve ci-dessous) : ce test rougit alors.

    ⚠ Il n'asserte PAS l'egalite au natif -- l'ecart de 20 % est une divergence de RANG connue et
    NOMMEE (`#951-r9`, le port joue la riposte avant `On(0x4a)`). Asserter l'egalite ici ferait de
    ce fichier un test de `#951-r9`, qu'il ne repare pas."""
    _exige_regime(bras_regime, mort_attendue=True)
    assert bras_regime["splash_port"] > 0, (
        "le port n'applique AUCUN splash (%s) alors que le natif en applique %s -- le gate "
        "`ownerNeedsToBeAlive` a-t-il ete pose ? cf. #951-r4"
        % (bras_regime["splash_port"], bras_regime["splash_live"]))


def test_la_CONTRE_EPREUVE_montre_que_poser_le_gate_met_le_splash_a_ZERO(bras_regime):
    """`WITHGATE` pose le gate absent. Sans cette mesure, << on ne le porte pas >> serait une
    opinion ; avec elle, c'est un fait chiffre."""
    _exige_regime(bras_regime, mort_attendue=True)
    assert bras_regime["splash_withgate"] == 0, (
        "la contre-epreuve ne ramene PAS le splash a zero (%s) -- elle ne demontre alors rien"
        % bras_regime["splash_withgate"])
    assert bras_regime["splash_withgate"] != bras_regime["splash_port"], (
        "WITHGATE rend le MEME observable que le port -- le patch ne mord pas (forme A ?)")
