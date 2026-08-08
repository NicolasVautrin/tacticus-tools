"""#564 -- `1039 RitesOfRestoration` (`adeptHospitaller` « Isabella »), confrontee au LIVE.

CE QUE CE FICHIER GARDE, et pourquoi il ne peut pas passer par accident.

AVANT ce port, 1039 etait un NO-OP SILENCIEUX : absente d'`ABILITY_CLASSES`, le cast rendait
`ported: False` -- 0 soin, 0 resurrection, aucune erreur. Un test qui se contenterait de « le port
rend un dict » resterait vert sur cet etat-la. Les quatre crans ci-dessous sont choisis pour que
CHACUN tombe si un etage du port disparait :

  [1] NON-DEGENERESCENCE du montage -- le natif doit CHANGER d'avis entre les deux regimes. Si
      `fromHere` est vide (ou plein) AUX DEUX instants, le montage ne separe rien et on refuse de
      lire l'accord comme une preuve.
  [2] GATE DE CASTER -- le port et le natif s'accordent DANS LES DEUX regimes. C'est
      `RitesOfRestorationAbility$$GetDynamicInvalidCasterReason`, atteint par le bit
      `AddCasterIfMatchesDynamicRule` (0x8) du masque via `TargetingQuery$$GetCasterNotAddedReason`.
      Un port sans ce corps rendrait `0` partout -> il tomberait au regime t0.
  [3] LA TUILE DE REAPPARITION -- le port PREDIT la tuile, le natif la CHOISIT, et elles doivent
      etre EGALES. C'est l'observable du zip `targets x tiles` de `ResurrectBehaviour$$Execute` :
      un port qui ressusciterait « quelque part » passerait le cran [4] et tomberait ici.
  [4] LE RETOUR A LA VIE -- le natif rend l'allie VIVANT, et ses PV valent `Min(hp de config,
      hpMax)` (le `FillUp` de `ResurrectUnitOperation$$SetHealth` plafonne). Les deux cotes lisent
      le MEME plafond.

Le montage : `adeptHospitaller` (caster, reste a son spawn) + `ultraCalgar` (Hero, Imperial,
NON mecanique) envoye AU CONTACT ; un tour adverse le TUE -> il devient la cible resurrectable.
PV joueur bas / frappe adverse haute : on choisit OU l'on mesure, on ne fitte aucun scalaire.

PORTEUR : `adeptHospitaller` est un `lineup` DANS le pool rank 17 -- aucune injection de catalogue.

ASCII only.
"""
from __future__ import annotations

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE PORT et son probe de mesure.
        "scripts/python/probe_564_rites_of_restoration.py",
        "scripts/python/engine/runner/abilities/sisterhood.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/operations/resurrect.py",
        "scripts/python/engine/runner/abilities/attack_query.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/entities/selectors/units.py",
        # ⚠ ELARGI : la liste feuille-a-feuille ci-dessus est ECRITE POUR LE LECTEUR (elle dit OU
        # regarder) ; ce sont les DEUX globs qui disent ce qui fait vraiment changer d'avis --
        # importer l'ability tire tout le paquet `runner`, et une liste choisie ne peut pas montrer
        # le module qu'elle a oublie. Les DEUX formes sont necessaires : `**/` exige un SEGMENT,
        # donc `scripts/python/**/*.py` ne voit PAS `scripts/python/rl_duel.py`.
        "scripts/python/*.py", "scripts/python/**/*.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Fichier LIVE : il confronte le port au binaire charge, donc tout changement de BUILD "
              "peut changer son verdict sans qu'aucun fichier du depot bouge. `toujours: True` "
              "repare la SELECTION, les deux globs la FERMETURE -- les deux crans sont "
              "INDEPENDANTS (mesure du 2026-08-08).",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_564_rites_of_restoration as P                   # noqa: E402

RITES = P.RITES


@pytest.fixture(scope="module")
def mesure(live_session):
    import uuid
    state = PYDIR.parents[1] / "logs" / ("rs_564_%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    m = None
    try:
        m = P.mesure(state)
        yield m
    finally:
        if m is not None:
            try:
                P.L._rpc("disposeRunner", [{"runnerId": m["rid"]}])
            except Exception:                                # noqa: BLE001
                pass
        state.unlink(missing_ok=True)


def _montage_ok(m):
    if m.get("ally_alive_after_ai_turn"):
        pytest.fail("MONTAGE : l'appat a survecu au tour adverse -- aucune cible resurrectable, "
                    "donc AUCUNE mesure. Reparer le montage (ALLY_BAIT / DMG_TARGET), pas le test.")


def test_le_natif_change_d_avis_entre_les_deux_regimes(mesure):
    """[1] NON-DEGENERESCENCE. Sans allie soignable NI mort resurrectable, le natif ne propose
    AUCUNE cible pour 1039 ; avec un mort Imperial non-mecanique et un hex libre, il propose le
    CASTER (l'ability est self-castee). Si les deux regimes rendaient la meme chose, l'accord du
    cran [2] serait vrai pour n'importe quel port."""
    m = mesure
    _montage_ok(m)
    assert m["t0_native"] == [], (
        "regime t0 : le natif propose deja %s -- le montage ne separe pas les deux regimes"
        % m["t0_native"])
    assert m["t1_native"] == [m["caster"]], (
        "regime t1 : le natif rend %s, attendu [%s] (le caster)" % (m["t1_native"], m["caster"]))


def test_le_gate_de_caster_est_d_accord_dans_les_deux_regimes(mesure):
    """[2] `RitesOfRestorationAbility$$GetDynamicInvalidCasterReason`, via
    `TargetingQuery$$GetCasterNotAddedReason` (bit `AddCasterIfMatchesDynamicRule` du masque).

    Le litteral refuse du natif est `2` = `TargetingRule.TargetMatchesDynamicRule` -- on ne teste
    QUE la nullite/non-nullite ici (c'est ce que `IBrokenTargetingRuleExtensions$$IsInvalid` lit),
    le litteral lui-meme etant garde offline."""
    m = mesure
    _montage_ok(m)
    assert m["t0_port_reason"] != 0, (
        "regime t0 : le port rend 0 (cast VALIDE) alors que le natif ne propose aucune cible -- "
        "le corps `GetDynamicInvalidCasterReason` est absent ou inerte")
    assert m["t1_port_reason"] == 0, (
        "regime t1 : le port rend %s (cast REFUSE) alors que le natif propose le caster"
        % m["t1_port_reason"])


def test_les_etages_de_ciblage_sont_mesures_separement(mesure):
    """Les trois comptes que le gate CONJUGUE sont releves un par un -- une divergence se localise
    au lieu de se compenser dans un booleen : l'allie mort doit etre reconnu `Hero` ET `Imperial`
    ET non-mecanique (`UnitsAffectedByHealType(0)`), et il doit exister au moins un hex libre."""
    m = mesure
    _montage_ok(m)
    st = m["stages"]
    assert st["resurrect"] == [m["ally"]], (
        "GetPossibleResurrectTargets = %s, attendu [%s]" % (st["resurrect"], m["ally"]))
    assert st["heroes"] == [m["ally"]], (
        "GetPossibleResurrectHeroTargets = %s -- le trait Hero (0x10) n'est pas lu" % st["heroes"])
    assert st["summons"] == [], (
        "GetPossibleResurrectSummonTargets = %s -- un Hero ne porte pas le trait Summon (2)"
        % st["summons"])
    assert st["tiles"], "CanAddUnit(AdjacentTiles(CasterTile())) est VIDE -- le board du mirroir " \
                        "n'est pas seede, la mesure ne dit rien du port"


def test_la_tuile_de_reapparition_predite_est_celle_du_natif(mesure):
    """[3] L'OBSERVABLE DU ZIP. `ResurrectBehaviour$$Execute` apparie la i-eme cible avec la i-eme
    TUILE (`Min(|targets|, |tiles|)`), les deux listes etant figees AVANT la boucle. Le port doit
    donc poser le ressuscite sur EXACTEMENT la meme tuile que le natif -- pas « quelque part
    d'adjacent »."""
    m = mesure
    _montage_ok(m)
    res = [r for bloc in (m["port"]["resurrections"] or [])
           for r in (bloc.get("resurrections") or [])]
    assert len(res) == 1, "le port a ressuscite %s unite(s), attendu 1 : %s" % (len(res), res)
    assert int(res[0]["resurrected"]) == m["ally"]
    assert res[0]["immediate_turn"] is False, (
        "`takesImmediateTurn` doit valoir false (i2 : « unable to act on this turn »)")
    port_tile = tuple(res[0]["tile"])
    native_tile = tuple(m["native_after"]["pos"])
    assert port_tile == native_tile, (
        "tuile de reapparition : port %s != natif %s -- le zip cible/tuile diverge"
        % (port_tile, native_tile))


def test_le_natif_ressuscite_bien_et_les_pv_sont_ceux_du_plafond(mesure):
    """[4] Le RETOUR A LA VIE cote NATIF, et le plafond de PV.

    `ResurrectUnitOperation$$SetHealth` est un `FillUpStatComponent$$FillUp` : les PV rendus valent
    `Min(hp de config, hpMax)`. Le montage force `hpMax` sous la valeur de config (`--hp-player`),
    ce qui rend le plafond OBSERVABLE au lieu d'etre confondu avec le montant brut."""
    m = mesure
    _montage_ok(m)
    ally = m["ally"]
    hp_b = m["hp_before"].get(ally)
    hp_a = m["hp_after"].get(ally)
    assert hp_b is not None and hp_a is not None, "PV non lisibles -- NON MESURE"
    assert hp_b[2] is True and hp_b[0] == 0, "l'appat n'etait pas mort AVANT le cast : %s" % (hp_b,)
    assert m["native_after"]["alive"] is True, "le natif n'a PAS ressuscite l'appat"
    hp_max = hp_a[1]
    cfg_hp = int(m["port"]["resurrect_hp"])
    assert hp_a[0] == min(cfg_hp, hp_max), (
        "PV apres resurrection : natif %s, attendu Min(config %s, hpMax %s)"
        % (hp_a[0], cfg_hp, hp_max))
