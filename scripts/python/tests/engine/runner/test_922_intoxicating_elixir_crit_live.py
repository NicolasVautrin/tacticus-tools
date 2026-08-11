"""CLIQUET #922 -- la relique `IntoxicatingElixir` (`EffectType` 0x5b3 = 1459), TROIS etages.

Ce que ce fichier GARDE, et ou le port se casserait sans lui :

  1. le COMPTEUR `Min(Count(EntitiesWithAnyEffect(SurroundingUnits(Tiles(Owner), range = 2,
     unique: 1, includeCenter: 1, sel 3), [Pinned, Stunned, Taunted_OnlySpecificTargets,
     ThrillSeekers])), nrOfUnits = 6)`, confronte des DEUX cotes -- natif par
     `decisionView.effects[].level` (le niveau STOCKE que `RefreshEffectsOperation$$UpdateLevel`
     tient egal a `$$GetCalculateLevel`), port par `debuffed_units_in_range_count` ;
  2. la CONDITION D'ACTIVITE `AmountIsGreaterThanZero(<ce compteur>)` -- GEOMETRIQUE, contrairement
     au `YesTrigger` CONSTANT de son voisin `KardiocoreGalvanus` ;
  3. la MAGNITUDE `ConfigVar(0x42 = extraCritDmg) x <compteur> x (2 si HealthPct(Owner) <=
     healthPct)`, coup par coup, LIVE contre REJEU OFFLINE.

Et il garde les QUATRE quirks qui distinguent cet effet de ses voisins de forme, chacun par un
bras dedie : le PORTEUR se compte lui-meme (`includeCenter = 1`), un AMI compte autant qu'un
ennemi (AUCUN filtre d'equipe), le disque est de rayon 2 (`SurroundingUnits`, CUBE, sans porte
d'elevation -- pas le ring-1 STOCKE d'`AdjacentFriends`), et le compte est PLAFONNE.

⚠ Il garde AUSSI le correctif #922 des trois vecteurs de degat : dans
`AttackDamageOperation$$ExecuteHit`, `On(6)` tombe ENTRE `RollCritical` (slot 0xa) et
`CalculateCriticalDamage` (slot 0xb), donc ce qu'il pose ne mord pas sur le TIRAGE du coup 0 mais
mord sur sa MAGNITUDE. Le bras `--thrilled` l'exerce (le porteur devient `Thrilled` a son propre
coup 0, ce qui fait MONTER son compteur en cours de salve) et sa contre-epreuve `CRITDMG_AVANT`
rejoue l'etat d'avant le correctif.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/_charge_regime.py",
        # LE MONTAGE : il est IMPORTE, pas recopie -- une derive du probe change ce fichier.
        "scripts/python/probe_922_intoxicating_elixir_live.py",
        # LE PORT et ses etages : la classe, l'arbre du compteur, le cablage du canal CRIT.
        "scripts/python/engine/entities/effects/loki/intoxicating_elixir.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/damage_hits.py",
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/damage_ops/normal_like.py",
        "scripts/python/engine/runner/operations/damage_ops/ability.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # Le trigger qui POSE le second debuff exerce (`ThrillSeekers` 1434) : sans lui les bras
        # `includeCenter` et `--thrilled` deviennent degeneres SANS que rien ne rougisse.
        "scripts/python/engine/runner/operations/triggers/loki/thrill_seekers.py",
        # Les trois noeuds de l'arbre du compteur -- il n'est fidele que s'ils le restent.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/dsl/base.py",
        # Le canal RELIQUE : le montage passe par `--equip-relic`, le niveau lu est TERTIAIRE.
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/engine/runner/snapshot.py",
        # Les mirrors d'enum de la garde de registre -- la collision d'ordinal 1463 est le piege
        # du cas (EffectType 1463 = `OrbsOfDecay_AdditionalHits`).
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        # Le SUBSTRAT : la config de la relique et le seed BC d'ou sortent les porteurs.
        "scripts/python/gameconfig.py", "data/seed-bc.json",
        # Le CAPTEUR dont ce fichier lit `level` et `active`.
        "frida/hooks/game/effects.ts",
    ),
    "build": False,
    "toujours": False,
    "raison": "Ce cliquet confronte le COMPTEUR (lu des deux cotes), la CONDITION D'ACTIVITE et la "
              "MAGNITUDE du canal crit-DEGAT de la relique `IntoxicatingElixir`, plus le correctif "
              "des trois vecteurs sur la place de la crit DAMAGE par rapport a `On(6)`. Le "
              "perimetre couvre donc la classe d'effet et son registre, les trois noeuds de son "
              "arbre, le cablage du canal, le trigger `ThrillSeekers` qui pose le debuff exerce, "
              "les trois vecteurs de degat, le canal relique qui porte le niveau, les mirrors "
              "d'enum, la config gameconfig et le seed BC, et le hook qui publie le niveau STOCKE. "
              "Pas de `build: True` : rien ici ne lit le binaire, seul le runner live est requis.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402
from pathlib import Path                                                 # noqa: E402

import pytest                                                            # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

from probe_922_intoxicating_elixir_live import (  # noqa: E402
    CARRIER, EFFECT_NAME, build, config_du_gameconfig, etages, frappe, mutants_compteur,
    rejeu, stage_degat)

_CFG = config_du_gameconfig()
_PALIERS = _CFG["paliers"]
#: assez GRAND pour rendre la salve lisible ; AUCUNE garde de saturation n'est requise -- le terme
#: est ADDITIF, donc le `Math.Max(0, .)` de `CalculateCriticalDamage` ne peut pas mordre.
_CRIT_DAMAGE = 2000
_LEVEL = 3


class _Args:
    """Les memes arguments que la ligne de commande du probe -- le montage est PARTAGE, pas
    recopie : une derive du probe fait bouger ce fichier."""

    seed, board, crit_damage = "922", "MC1_67", _CRIT_DAMAGE
    level, dist, low_hp, thrilled, mutants = _LEVEL, 2, False, False, False

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture(scope="module")
def _bind(rpc):
    """⚠ CANAL RELIQUE : sans transport AMBIANT (`snapshot.bind_live_rpc`, #357/#363),
    `UnitContext.tertiary_ability` reste `None` et le port lirait le niveau des PASSIFS."""
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)
    return rpc


def _mesure(rpc, live_session, n, **kw):
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    a = _Args(**kw)
    rid, sf = build(a, "test_n%d_%s" % (n, os.getpid()), a.level)
    assert rid is not None, "build du runner NON ATTEINT -- jamais un skip vert"
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage_degat(h, a, n, _CFG)
        assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
        live, why = frappe(h, rec)
        assert live is not None, "attaque non jouee : %s" % why
        k = len(live)
        return {"rec": rec, "live": live, "off": rejeu(h, rec)[:k],
                "nochannel": rejeu(h, rec, mutate="NOCHANNEL")[:k],
                "passif": rejeu(h, rec, mutate="PASSIF")[:k],
                "sanssante": rejeu(h, rec, mutate="SANSSANTE")[:k],
                "et": etages(h, rec), "st": h.offline_state(rec)}
    finally:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


@pytest.mark.parametrize("n", [0, 1, 2])
def test_le_bonus_suit_le_nombre_d_unites_debuffees_a_portee(live_session, _bind, rpc, n):
    """`ForAddition(get_OwnerIsCaster, Multiply(Multiply(ConfigVar(0x42), EffectLevel(effet)),
    ConditionalAmount(...)))`, et la CONDITION D'ACTIVITE qui va avec.

    `n = 0` verifie AUSSI que la condition est bien GEOMETRIQUE : le natif publie l'effet
    INACTIF sans aucune unite debuffee a portee -- l'inverse de `KardiocoreGalvanus`."""
    m = _mesure(rpc, live_session, n)
    rec, et = m["rec"], m["et"]
    assert rec["n"] == n, "regime NON ATTEINT : %d unites debuffees a portee au lieu de %d" % (
        rec["n"], n)
    assert bool(rec["actif_natif"]) is (n > 0), (
        "`CreateActiveCondition` = `AmountIsGreaterThanZero(GetLevelFormula(...))` : l'effet doit "
        "etre publie ACTIF SSI le compteur est > 0, or n=%d rend %s" % (n, rec["actif_natif"]))
    assert et["effet_actif_port"] is (n > 0), (
        "activite du PORT = %s a n=%d" % (et["effet_actif_port"], n))
    if rec["actif_natif"]:
        # ⚠ `level` ne fait foi QUE si l'effet est ACTIF : `UpdateLevel` ne rafraichit pas le
        # niveau d'un effet inactif, qui reste a sa valeur d'initialisation (MESURE : 1 a n = 0).
        assert rec["niveau_natif"] == n, (
            "compteur NATIF (decisionView.effects[].level) = %s != %d" % (rec["niveau_natif"], n))
    assert et["compteur"] == n, "compteur du port %s != %d" % (et["compteur"], n)
    assert m["off"] == m["live"], "n=%d : port %s != natif %s (etages %s)" % (
        n, m["off"], m["live"], et)
    attendu = (_PALIERS[_LEVEL - 1] * n) if n else None
    assert et["bonus_signe"] == attendu, (
        "bonus SIGNE du port %s != %s -- `ForAddition` verse un terme POSITIF"
        % (et["bonus_signe"], attendu))
    assert (m["nochannel"] != m["off"]) is (n > 0), (
        "n=%d : le canal doit mordre SSI n > 0" % n)


def test_le_produit_discrimine_deux_regimes_non_nuls(live_session, _bind, rpc):
    """SECOND CAS DISCRIMINANT : `n = 1` et `n = 2` ne s'expliquent pas par un scalaire."""
    m1 = _mesure(rpc, live_session, 1)
    m2 = _mesure(rpc, live_session, 2)
    assert m1["off"] == m1["live"] and m2["off"] == m2["live"]
    assert m2["et"]["bonus_signe"] == 2 * m1["et"]["bonus_signe"], (
        "le bonus doit DOUBLER de n=1 a n=2 : %s puis %s"
        % (m1["et"]["bonus_signe"], m2["et"]["bonus_signe"]))
    assert m1["live"] != m2["live"], "les deux regimes rendent la MEME salve"


def test_le_disque_a_le_rayon_de_la_constante_range(live_session, _bind, rpc):
    """`SurroundingUnits(..., range = GetNumberConstant(0x16), ...)` : une victime DEBUFFEE posee
    a `range + 1` ne doit PAS compter. C'est le bras qui separe le rayon 2 du ring-1 des voisins
    de forme, et il a un TEMOIN NON NUL (l'autre victime, elle, compte)."""
    m = _mesure(rpc, live_session, 2, dist=_CFG["range"] + 1)
    assert m["rec"]["n"] == 1, (
        "DEUX victimes debuffees dont une a distance %d : le compteur doit valoir 1, or %s"
        % (_CFG["range"] + 1, m["rec"]["n"]))
    assert m["rec"]["niveau_natif"] == 1, "compteur NATIF = %s" % m["rec"]["niveau_natif"]
    assert m["et"]["compteur"] == 1, "compteur du port = %s" % m["et"]["compteur"]
    assert m["off"] == m["live"], "port %s != natif %s" % (m["off"], m["live"])


def test_le_bonus_double_sous_le_seuil_de_vie(live_session, _bind, rpc):
    """`ConditionalAmount(HealthPctIsBelowOrEqual(Owner, Get(ConfigConst(0x4f = healthPct))),
    <DSLFormulas+0x28> = Direct(2), <DSLFormulas+0x20> = Direct(1))`.

    Le PV du porteur est RELU (jamais suppose) : `--hp-player` forcerait `Health ==
    RemainingHealth`, donc 100 %, et n'exercerait JAMAIS ce facteur."""
    m = _mesure(rpc, live_session, 1, low_hp=True)
    hp, mx = m["et"]["sante"]
    assert hp is not None and mx, "PV du porteur NON MESURES -- bras degenere"
    assert 100 * int(hp) <= _CFG["healthPct"] * int(mx), (
        "regime NON ATTEINT : %s/%s n'est pas sous %d %%" % (hp, mx, _CFG["healthPct"]))
    assert m["et"]["bonus_signe"] == 2 * _PALIERS[_LEVEL - 1], (
        "le bonus doit etre DOUBLE : %s" % m["et"]["bonus_signe"])
    assert m["off"] == m["live"], "port %s != natif %s" % (m["off"], m["live"])
    assert m["sanssante"] != m["off"], (
        "le bras SANTE ne mord pas -- le facteur `ConditionalAmount` n'est pas exerce")


def test_le_niveau_lu_est_celui_de_la_relique_pas_du_passif(live_session, _bind, rpc):
    """`GetAbilityState(effet)` -> l'`AbilityState` **TERTIAIRE** (`BC.Units[].TertiaryAbilityLevel`).
    Le bras `PASSIF` ne peut mordre QUE si le niveau demande n'est pas le dernier palier."""
    m = _mesure(rpc, live_session, 1)
    assert m["et"]["ability_state"][0] == _LEVEL, (
        "le port lit le niveau %s au lieu de %d -- canal TERTIAIRE non branche"
        % (m["et"]["ability_state"], _LEVEL))
    assert (m["passif"] != m["off"]) is (_LEVEL != len(_PALIERS)), (
        "le bras PASSIF doit mordre SSI le niveau n'est pas le dernier palier")


def test_les_six_lectures_fausses_du_compteur_mordent(live_session, _bind, rpc):
    """SIX mutations PLAUSIBLES de `$$GetLevelFormula` -- centre exclu, geometrie de
    `KardiocoreGalvanus` (ring-1 + filtre d'equipe), rayon 1, bloc ampute de `Pinned`, bloc ampute
    de `ThrillSeekers`, plafond a 1. Chacune doit MORDRE dans ce regime (deux ennemis DEBUFFES a
    portee) ou se taire, exactement comme le declare `_MUTANTS`. Un mutant VERT la ou il doit
    mordre dit que le temoin est aveugle."""
    m = _mesure(rpc, live_session, 2)
    rc = mutants_compteur(m["st"], m["rec"]["porteur"], 2, "enn")
    assert rc == 0, "au moins un mutant du compteur ne se comporte pas comme declare"


def test_la_crit_damage_se_relit_apres_l_event_du_coup_zero(live_session, _bind, rpc):
    """CORRECTIF #922 des trois vecteurs. `AttackDamageOperation$$ExecuteHit` : slot 0xa
    `RollCritical` -> `EnqueueOperation(6)` -> slot 0xb `CalculateCriticalDamage`. `On(6)` tombe
    ENTRE les deux, donc ce qu'il pose mord sur la MAGNITUDE du coup 0.

    Regime : la cible de melee reste a PLEINE VIE, donc `ThrillSeekersAbility` rend le PORTEUR
    `Thrilled` apres son coup 0 -- son compteur passe de 1 a 2 EN COURS DE SALVE. Le port doit
    suivre le natif COUP PAR COUP, et la contre-epreuve `CRITDMG_AVANT` (crit damage figee sur sa
    premiere mesure) doit DIVERGER."""
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    from probe_922_intoxicating_elixir_live import _debuffs_of
    a = _Args(thrilled=True, dist=1)
    rid, sf = build(a, "test_thrilled_%s" % os.getpid(), a.level)
    assert rid is not None, "build du runner NON ATTEINT -- jamais un skip vert"
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage_degat(h, a, 1, _CFG)
        assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
        assert rec["actif_natif"], (
            "l'effet doit etre ACTIF au snapshot, sinon il est ABSENT de l'etat offline "
            "(canal `decisionView` ACTIF-ONLY) et le bras ne mesure plus le correctif")
        live, why = frappe(h, rec)
        assert live is not None, "attaque non jouee : %s" % why
        k = len(live)
        off = rejeu(h, rec)[:k]
        avant = rejeu(h, rec, mutate="CRITDMG_AVANT")[:k]
        assert _debuffs_of(h, rec["porteur"]), (
            "le porteur n'est PAS devenu `Thrilled` -- bras degenere, le compteur ne monte pas")
        assert off == live, "port %s != natif %s (le compteur monte EN COURS DE SALVE)" % (
            off, live)
        assert avant != off, (
            "la contre-epreuve CRITDMG_AVANT ne mord pas : ce bras n'exerce PAS le correctif")
    finally:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)
