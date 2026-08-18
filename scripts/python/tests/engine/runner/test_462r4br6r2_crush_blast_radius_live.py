"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r6-r2 -- les DEUX classes du blast radius du CRUSH, CONFRONTEES.

PORTE PYTEST du montage `probe_462r4br6r2_crush_blast_radius_live.py` : le probe MESURE (une mine
HAYWIRE posee par `astarCyrus` sert de `Steppable`, le porteur reel de chaque ability l'ECRASE en se
deplacant dessus), ce module ASSERTE. Aucun montage n'est duplique ici.

## CE QUE CE FICHIER ETABLIT, ET LES DEUX VERDICTS QU'IL RETOURNE

`#462-...-r6` avait LU les deux gates et conclu que les deux classes etaient << atteignables par le
MOVER >> (owner = le tueur) -- un verdict ANALYTIQUE, jamais oppose au jeu. La mesure le REFUTE sur
les deux, et chacune l'etait pour une raison DIFFERENTE :

  * `HazeCorruption_BonusHitAbility` -- son conjoint `IsDead(Target@0x178)` n'etait pas porte
    (`ev.dying_id is None` n'est pas `IsDead`). Un `Steppable` n'a AUCUNE SANTE (0/0), et
    `HealthComponent$$IsAlive` rend TRUE dans ce cas ; a `On(1 = PreUnitDeath)` le natif n'a encore
    pose ni le flag `Dead` ni le retrait du pool, donc `IsDead(crushe)` est FAUX. Cote port, le
    verdict restait FAUX pour une deuxieme raison : `movement.py` collapsait `uc.alive = False`
    AVANT les cinq evenements, alors que le natif retire par `RemoveUnit` ENTRE les deux premiers
    `RemoveEffects` -- et ce retrait est appele a son rang depuis #10015-r3, donc le collapse
    n'etait plus qu'un DOUBLON PREMATURE.
  * `DawnBlade_HealAbility` -- son conjoint `IsDefeatedByMeleeAttack` etait APPROXIME par la
    POSITION, et apres un crush le mover est SUR la tuile du crushe (distance 0 = << melee >>). Le
    marqueur natif, lui, vaut **False** : `KillUnitOperation$$Execute` l'ecrit
    INCONDITIONNELLEMENT (`(rangeType == Melee) & rangeType.HasValue`), et un crush ne transporte
    aucun `AttackRangeType`. Le port ne l'ecrivait que si la voie en portait un.

MESURE (2026-08-18, `MC1_67` / seed 777) :

| bras | natif | port AVANT | port APRES |
|---|---|---|---|
| HAZE / crush | 0 groupe `HazeOfCorruption` | fire | ne fire pas |
| HAZE / kill par ATTAQUE | 2 groupes | -- | (temoin de non-degenerescence) |
| DAWNBLADE / crush | 0 groupe, `defeatedByMelee=False` | fire | ne fire pas |
| DAWNBLADE / kill MELEE | 1 groupe, **+1997 PV**, `defeatedByMelee=True` | -- | (temoin) |
| les deux / SANS crush | 0 groupe | -- | ne fire pas |

Les bras `kill par attaque` sont ce qui empeche le PASS de venir d'une ability non montee : sans
eux, << le natif ne fire pas au crush >> ne distinguerait pas << le crush ne l'arme pas >> de
<< l'ability n'existe pas sur ce porteur >>.

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

import probe_462r4br6r2_crush_blast_radius_live as P     # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_462r4br6r2_crush_blast_radius_live.py",
        # Les deux classes confrontees, et le foyer du marqueur melee qu'elles partagent.
        "scripts/python/engine/runner/operations/triggers/loki/haze_of_corruption.py",
        "scripts/python/engine/runner/operations/triggers/loki/dawn_blade.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # Le CRUSH : son rang de retrait, et l'ecriture du marqueur.
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/remove_unit.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/snapshot.py",
        # Le poseur du `Steppable` et le registre qui monte les deux abilities.
        "scripts/python/engine/runner/operations/triggers/loki/haywire_mine.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # Le harnais qui monte la bataille et rejoue le pas offline.
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/tests/conftest.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("Confrontation LIVE du blast radius du crush : tout ce qui change le rang du retrait, "
               "l'ecriture du marqueur melee, les conjoints des deux triggers ou la pose du "
               "`Steppable` peut retourner le verdict. `build: True` parce que le flux natif "
               "(groupes d'ability) est lu dans le jeu."),
}


class _Args:
    """Les memes defauts que le CLI du probe -- un objet plutot qu'un `argparse.Namespace` pour
    que le montage du test soit LISIBLE au site."""

    def __init__(self, face: str, temoin_sans_crush=False, temoin_kill_attaque=False):
        self.face = face
        self.seed = "777"
        self.board = "MC1_67"
        self.ennemi1 = "necroWarden"
        self.ennemi2 = "necroOverlord"
        self.hp_target = 500 if temoin_kill_attaque else 900000
        self.hp_player = 900000
        self.temoin_sans_crush = temoin_sans_crush
        self.temoin_kill_attaque = temoin_kill_attaque
        self.verbose = False


@pytest.fixture(scope="module")
def _seed_bc():
    """Seed BC AUGMENTE d'`astarCyrus` : c'est lui qui POSE le `Steppable` (mine Haywire) qu'on
    ecrase. Il est HORS pool et HORS seed BC, et ce n'est PAS un refus."""
    p = P.seed_bc_avec_poseur()
    yield p
    Path(p).unlink(missing_ok=True)


def _mesure(rpc, build_runner, seed_bc, a):
    mover, _ability, extra = P.FACES[a.face]
    r = build_runner(seed=a.seed, board=a.board, extra=[
        "--seed-bc", seed_bc, "--rank", "17",
        "--p-units", "%s,%s" % (P.POSEUR, mover),
        "--a-units", "%s,%s" % (a.ennemi1, a.ennemi2),
        "--hp-target", str(a.hp_target), "--hp-player", str(a.hp_player),
        "--no-ai", "--crit", "0,0", "--crit-target", "0,0",
        "--block-target", "0,0", "--block-player", "0,0", *extra])
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    return P.mesurer(a, rpc, Board, ChargeRegimeHarness, r["rid"])


@pytest.fixture(scope="module")
def haze_crush(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, _Args("haze"))


@pytest.fixture(scope="module")
def haze_kill(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, _Args("haze", temoin_kill_attaque=True))


@pytest.fixture(scope="module")
def dawnblade_crush(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, _Args("dawnblade"))


@pytest.fixture(scope="module")
def dawnblade_kill(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, _Args("dawnblade", temoin_kill_attaque=True))


def _exige(m, crush_attendu):
    """Un montage rate n'est PAS un accord : il doit FAIRE ECHOUER, jamais passer en silence."""
    if not m.get("ok"):
        pytest.fail("regime NON ATTEINT (%s) : %s" % (m.get("bras"), m.get("why")), pytrace=False)
    mort = not m["live"]["mine_vivante"]
    if mort is not bool(crush_attendu):
        pytest.fail("le bras n'a pas produit son regime (victime morte=%s, attendu=%s)"
                    % (mort, crush_attendu), pytrace=False)


@pytest.mark.parametrize("face", ["haze", "dawnblade"])
def test_le_NATIF_sait_fire_hors_crush(face, haze_kill, dawnblade_kill):
    """NON-DEGENERESCENCE. Sans ce bras, << le natif ne fire pas au crush >> ne distingue pas
    << le crush ne l'arme pas >> de << l'ability n'est pas montee sur ce porteur >>."""
    m = haze_kill if face == "haze" else dawnblade_kill
    _exige(m, crush_attendu=True)
    assert len(m["live"]["groupes"]) > 0, (
        "le natif n'ouvre AUCUN groupe `%s` sur un kill ORDINAIRE -- l'ability n'est pas montee, "
        "et le bras CRUSH ne mesure rien" % m["rec"]["ability"])


def test_le_marqueur_melee_natif_DISCRIMINE_le_crush(dawnblade_crush, dawnblade_kill):
    """`defeatedByMelee` : **True** sur un kill melee, **False** sur un crush. C'est le canal que le
    port APPROXIMAIT par la position -- et la position, apres un crush, dit l'inverse (distance 0)."""
    _exige(dawnblade_kill, crush_attendu=True)
    _exige(dawnblade_crush, crush_attendu=True)
    assert dawnblade_kill["live"]["defeated_by_melee"] is True, dawnblade_kill["live"]
    assert dawnblade_crush["live"]["defeated_by_melee"] is False, dawnblade_crush["live"]


def test_le_natif_REPARE_sur_un_kill_melee_et_PAS_sur_un_crush(dawnblade_crush, dawnblade_kill):
    """L'observable propre de `DawnBlade_HealAbility` : les PV du porteur."""
    _exige(dawnblade_kill, crush_attendu=True)
    _exige(dawnblade_crush, crush_attendu=True)
    d_kill = (dawnblade_kill["live"]["hp_apres"] or 0) - (dawnblade_kill["rec"]["hp_avant"] or 0)
    d_crush = (dawnblade_crush["live"]["hp_apres"] or 0) - (dawnblade_crush["rec"]["hp_avant"] or 0)
    assert d_kill > 0, ("le natif ne repare PAS sur un kill melee (%+d) -- le temoin ne "
                        "discrimine rien" % d_kill)
    assert d_crush == 0, ("le natif repare sur un CRUSH (%+d) -- le verdict de ce fichier serait "
                          "inverse" % d_crush)


@pytest.mark.parametrize("face", ["haze", "dawnblade"])
def test_le_port_rend_le_MEME_verdict_que_le_natif_au_crush(face, haze_crush, dawnblade_crush):
    m = haze_crush if face == "haze" else dawnblade_crush
    _exige(m, crush_attendu=True)
    nat = len(m["live"]["groupes"]) > 0
    port = bool(m["offline"]["fire"][face])
    assert port == nat, ("%s : port fire=%s natif fire=%s" % (m["rec"]["ability"], port, nat))
    assert nat is False, ("le NATIF fire au crush (%d groupe(s)) -- la premisse de ce fichier est "
                          "renversee" % len(m["live"]["groupes"]))


@pytest.mark.parametrize("face", ["haze", "dawnblade"])
def test_le_CRUSH_lui_meme_a_bien_lieu_des_DEUX_cotes(face, haze_crush, dawnblade_crush):
    """Le port ne doit pas << concorder >> parce qu'il n'a rien ecrase : le retrait passe desormais
    par `RemoveUnitOperation` (le collapse `uc.alive = False` de `movement.py` est retire)."""
    m = haze_crush if face == "haze" else dawnblade_crush
    _exige(m, crush_attendu=True)
    assert m["offline"]["mine_vivante"] is False, (
        "le port n'a PAS ecrase le `Steppable` -- les deux cotes ne jouent pas le meme pas")


@pytest.mark.parametrize("face", ["haze", "dawnblade"])
def test_l_espion_a_bien_VISITE_le_predicat(face, haze_crush, dawnblade_crush):
    """Un `fire=False` obtenu parce que le trigger n'est pas INSTANCIE ne prouve rien : on exige que
    `matches` ait ete APPELE au moins une fois, et qu'il ait rendu False."""
    m = haze_crush if face == "haze" else dawnblade_crush
    _exige(m, crush_attendu=True)
    traces = (m["offline"]["traces"] or {}).get(face) or []
    assert traces, ("le predicat de `%s` n'a JAMAIS ete evalue -- l'ability n'est pas montee cote "
                    "port, donc `fire=False` ne dit rien" % m["rec"]["ability"])
    assert all(t["verdict"] is False for t in traces), traces
