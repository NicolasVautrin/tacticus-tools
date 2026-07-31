"""#371 -- GARDE LIVE du gisement G1 : le stat-mod SEEDE d'une instance generique
`StaticStatModifierEffect` suit le natif, A L'EXPIRATION comme AU SEED.

Les DEUX montages vivent dans des probes (`probe_371_serene_unifier_live.py` /
`probe_371_unbreakable_duty_live.py`) ; ce fichier n'est que leur porte pytest. Chaque montage
comporte son BRAS DISCRIMINANT : la MEME capture rejouee avec l'inscription RETIREE du registre.
Sans lui, ces tests seraient verts dans les deux mondes -- c'est le piege exact de ce lot, ou le
`Current` capte est toujours reproduit par le residu opaque de `seed_unit_stats`.

  * `1171 SereneUnifierStormOfFire` -- le SEUL membre inscrit a porter un TIMER
    (`TurnsFromRounds(1)`). L'observable est la DUREE : apres l'echeance, ATTACK doit REDESCENDRE
    du meme montant que le natif.
  * `1251/1256 UnbreakableDuty_*` -- PERMANENTS (`turns = NULL` au decompile). L'observable est
    l'ATTRIBUTION : le `statDelta` publie par le natif apres le cast doit egaler, au point pres, la
    magnitude RE-DERIVEE de gameconfig -- deux sources independantes, donc validation NON CIRCULAIRE
    de l'index de variable lu au decompile.

⚠ Montage non installe => ECHEC, jamais skip (#268) : un skip serait un vert qui ment (aucune mesure
n'a eu lieu, et rien ne rougit pour personne).
"""
from __future__ import annotations

import pytest

import probe_371_serene_unifier_live as SU
import probe_371_unbreakable_duty_live as UD


@pytest.fixture(scope="module")
def storm_of_fire_case(build_runner, rpc):
    """Fabrique : `storm_of_fire_case()` / `storm_of_fire_case("4242", "C4_09")` -> le dict de
    mesure du montage #371-SereneUnifier. `keep=True` : le runner appartient a `build_runner`
    (teardown du module), le probe ne doit pas le disposer sous les pieds de son proprietaire."""
    cache: dict = {}

    def _case(seed: str = SU.SEED, board: str = SU.BOARD) -> dict:
        key = (seed, board)
        if key not in cache:
            r = SU.run(rpc, seed=seed, board=board, build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage StormOfFire NON INSTALLE (seed=%s board=%s) : %s"
                            % (seed, board, r.get("why")))
            cache[key] = r
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def unbreakable_duty_case(build_runner, rpc):
    """Fabrique : `unbreakable_duty_case()` -> le dict de mesure du montage #371-UnbreakableDuty
    (deux allies Black Templars a 1 PV TUES pour armer la gate `>= 2 morts`, puis cast)."""
    cache: dict = {}

    def _case(seed: str = UD.SEED, board: str = UD.BOARD) -> dict:
        key = (seed, board)
        if key not in cache:
            r = UD.run(rpc, seed=seed, board=board, build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage UnbreakableDuty NON INSTALLE (seed=%s board=%s) : %s"
                            % (seed, board, r.get("why")))
            cache[key] = r
        return cache[key]
    return _case


# --------------------------------------------------------------------------------------------------
# 1171 -- LA DUREE.
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("seed,board", [
    # DEUX couples (seed, board) : le verdict ne doit rien devoir a la geometrie d'UN plateau
    # (discipline de generalisation -- le cycle du passif est turn-based, pas positionnel, mais le
    # buff arrose un voisinage, donc la geometrie entre bien dans le montage).
    (SU.SEED, SU.BOARD),
    ("4242", "C4_09"),
])
def test_storm_of_fire_seeded_statmod_reverts_on_expiry_like_native(storm_of_fire_case, seed, board):
    """LE CRITERE DU LOT, confronte au natif : l'etat offline est charge APRES la pose (l'effet est
    DEJA actif, son +extraDmg DEJA CUIT dans `combatSnapshot.stats`), et le stat-mod doit quand meme
    SORTIR a l'echeance -- du MEME montant que le live.

    Natif : `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` ecrit un
    `ChangeStat(Entity(target), Position(stat, part 5|9), Direct(amount), Entity(<effectEntity>))` --
    la SOURCE est l'entite-effet -- et `...$$RevertModification` rejoue le MEME appel en part 6 avec
    LA MEME entite. Un effet a stat-mod ne peut donc PAS disparaitre en laissant sa contribution."""
    r = storm_of_fire_case(seed, board)
    assert r["attack_off_on"] == r["attack_live_on"], (
        "MOTEUR: seed divergent AVANT tout tick (ATTACK=%s != live %s)"
        % (r["attack_off_on"], r["attack_live_on"]))
    assert not r["live_still_here"], "LIVE: StormOfFire n'expire pas"
    assert not r["off_still_here"], "MOTEUR: effet a timer non retire a l'echeance"
    assert r["attack_off_off"] == r["attack_live_off"], (
        "MOTEUR: stat-mod SEEDE non reverte a l'expiration (ATTACK=%s, live %s) -- la contribution "
        "du seed n'est attribuee a aucune source retirable"
        % (r["attack_off_off"], r["attack_live_off"]))
    d_live = r["attack_live_on"] - r["attack_live_off"]
    d_off = r["attack_off_on"] - r["attack_off_off"]
    assert d_live > 0, "LIVE: ATTACK ne redescend pas a l'expiration -- montage sans observable"
    assert d_off == d_live, "MOTEUR: delta %s != live %s" % (d_off, d_live)


def test_storm_of_fire_seed_attribution_is_exact_and_not_opaque(storm_of_fire_case):
    """La CONDITION NECESSAIRE du revert, et une validation NON CIRCULAIRE : sur le porteur-SOURCE
    (Aun'Shi se buffe lui-meme), la magnitude re-derivee de gameconfig explique EXACTEMENT le
    `statDelta` natif -> `residu opaque == 0`."""
    r = storm_of_fire_case()
    assert r["statmod_keys"], (
        "1171 SEEDE non attribue -- sa contribution est dans le residu opaque, donc NON retirable")
    assert r["opaque_residual"] == 0, \
        "residu opaque non nul (%s) : la magnitude offline n'explique pas le delta natif" \
        % (r["opaque_residual"],)
    assert r["attributed"] == r["attack_live_on"] - r["attack_live_off"], (
        "montant attribue %s != delta natif a l'expiration %s"
        % (r["attributed"], r["attack_live_on"] - r["attack_live_off"]))


def test_storm_of_fire_undeclared_keeps_the_buff_alive_forever(storm_of_fire_case):
    """LE BRAS DISCRIMINANT -- sans lui les deux tests ci-dessus ne prouveraient rien. La MEME
    capture, rejouee avec l'inscription RETIREE du registre :
      * AVANT l'echeance, les deux mondes rendent la MEME valeur (donc un test qui mesurerait la
        serait vert dans les deux cas) ;
      * APRES, le monde non declare garde le bonus alors que le natif l'a retire."""
    r = storm_of_fire_case()
    u = r["undeclared"]
    assert u["attack_on"] == r["attack_off_on"], (
        "les deux mondes divergent DEJA avant l'echeance (%s vs %s) -- le montage ne mesure alors "
        "plus la DUREE mais la valeur" % (u["attack_on"], r["attack_off_on"]))
    assert u["opaque_residual"] > 0 and not u["statmod_keys"], (
        "sans inscription, la contribution devrait etre dans le residu opaque (residu=%s cles=%s)"
        % (u["opaque_residual"], u["statmod_keys"]))
    assert u["attack_off"] != r["attack_live_off"], (
        "le bras non declare rend le MEME resultat que le natif (%s) -- le montage n'est PAS "
        "discriminant, il ne conclut rien" % (u["attack_off"],))
    assert u["attack_off"] == u["attack_on"], (
        "le bras non declare devrait garder le buff A VIE (%s -> %s)"
        % (u["attack_on"], u["attack_off"]))


# --------------------------------------------------------------------------------------------------
# 1251 / 1256 -- L'ATTRIBUTION (ils sont PERMANENTS : il n'y a pas de duree a fermer).
# --------------------------------------------------------------------------------------------------

def test_unbreakable_duty_magnitudes_match_the_native_stat_delta(unbreakable_duty_case):
    """VALIDATION NON CIRCULAIRE de l'index de variable lu au decompile : `ConfigVar(0x1e)` a ete
    tranche `extraHp` par ELIMINATION sur les trois variables de l'ability (`extraDmg` = 8,
    `dmgReductionPct` = 0x46 lu sur `UnbreakableDuty_DamageReductionEffect$$
    CreateEffectDamageMalusForDefense`). Si l'elimination etait fausse, le `statDelta` natif ne
    tomberait pas sur la magnitude gameconfig."""
    r = unbreakable_duty_case()
    assert r["effects"]["1251"] and r["effects"]["1256"], "les deux effets ne sont pas poses"
    assert r["after"]["d_attack"] == r["config"]["extraDmg"], (
        "statDelta[attack] natif %s != UnbreakableDuty.extraDmg[L%s] x %s%% = %s"
        % (r["after"]["d_attack"], r["level"], r["multiplier"], r["config"]["extraDmg"]))
    assert r["after"]["d_health"] == r["config"]["extraHp"], (
        "statDelta[health] natif %s != UnbreakableDuty.extraHp[L%s] x %s%% = %s -- l'index "
        "ConfigVar(0x1e) = extraHp serait alors FAUX"
        % (r["after"]["d_health"], r["level"], r["multiplier"], r["config"]["extraHp"]))


def test_unbreakable_duty_seed_attribution_is_not_opaque(unbreakable_duty_case):
    """L'observable que l'inscription ferme, avec son BRAS DISCRIMINANT : la capture post-cast,
    seedee offline, porte ses deux contributions sous une cle d'effet (residu 0) ; sans
    l'inscription elles tombent dans le residu opaque -- et les stats COURANTES sont identiques dans
    les deux bras, ce qui est exactement la raison pour laquelle ce bug est silencieux."""
    r = unbreakable_duty_case()
    d, u = r["declared"], r["undeclared"]
    assert d["attack_attributed"] == r["config"]["extraDmg"] and d["attack_opaque"] == 0, \
        "1256 non attribue (attribue=%s residu=%s)" % (d["attack_attributed"], d["attack_opaque"])
    assert d["health_attributed"] == r["config"]["extraHp"] and d["health_opaque"] == 0, \
        "1251 non attribue (attribue=%s residu=%s)" % (d["health_attributed"], d["health_opaque"])
    assert u["attack_attributed"] == 0 and u["attack_opaque"] == r["config"]["extraDmg"], \
        "bras non declare non discriminant sur ATTACK : %s" % (u,)
    assert u["health_attributed"] == 0 and u["health_opaque"] == r["config"]["extraHp"], \
        "bras non declare non discriminant sur HEALTH : %s" % (u,)
    assert (d["attack"], d["health"]) == (u["attack"], u["health"]), (
        "les stats COURANTES different entre les deux bras (%s vs %s) -- l'inscription ne doit "
        "changer QUE l'attribution" % ((d["attack"], d["health"]), (u["attack"], u["health"])))
