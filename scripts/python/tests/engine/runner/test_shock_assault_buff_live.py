"""case-366-r1 -- GARDE LIVE de `ShockAssault_Buff` (1000) : le buff des Inceptors suit le natif,
en MAGNITUDE comme en DUREE.

Le montage vit dans `probe_366r1_shock_assault_buff.py` ; ce fichier n'est que sa porte pytest. Il
comporte son BRAS DISCRIMINANT (la MEME capture rejouee avec l'inscription RETIREE du registre) et
son SECOND COUPLE (le niveau de PASSIF du poseur dissocie de son niveau d'ACTIF) -- sans eux, tout
serait vert dans les deux mondes : le `Current` capte est TOUJOURS reproduit par le residu opaque
de `seed_unit_stats`, et `buildNormalizedBC` met les deux niveaux a 50.

⚠ Montage non installe => ECHEC, jamais skip (#268) : un skip serait un vert qui ment.
"""
from __future__ import annotations

import pytest

import probe_366r1_shock_assault_buff as SA


@pytest.fixture(scope="module")
def shock_assault_case(build_runner, rpc):
    """Fabrique : `shock_assault_case()` (nominal, passif 50) / `shock_assault_case(passive=20)`
    (le second couple discriminant). `keep=True` : le runner appartient a `build_runner`."""
    cache: dict = {}

    def _case(seed: str = SA.SEED, board: str = SA.BOARD, passive: int | None = None) -> dict:
        key = (seed, board, passive)
        if key not in cache:
            r = SA.run(rpc, seed=seed, board=board, build_runner=build_runner,
                       passive_level=passive, keep=True)
            if not r.get("ok"):
                pytest.fail("montage ShockAssault_Buff NON INSTALLE (seed=%s board=%s passif=%s) : %s"
                            % (seed, board, passive, r.get("why")))
            cache[key] = r
        return cache[key]
    return _case


def test_shock_assault_buff_exists_and_survives_when_its_target_dies(shock_assault_case):
    """LE MONTAGE LUI-MEME est une mesure : en regime naturel 1000 est pose ET retire dans la MEME
    resolution (les events du kill le montrent), donc INOBSERVABLE. Il ne survit que parce que le
    Bellator TUE sa cible -> `IsAlive(target)` faux dans le `customUtility` de `PerformAIAbility`
    -> l'Inceptor ne joue pas. Si ce test rougit, la lecture du `b__1_1` est fausse."""
    r = shock_assault_case()
    assert r["live_present"], "1000 absent du live apres le kill -- le regime n'est pas celui decrit"
    src = [e for e in r["kill_events"] if e[2] == "ShockAssault_Buff"]
    assert len(src) >= 2, ("les events du kill devraient montrer AU MOINS une pose et un retrait "
                           "(un Inceptor a attaque, l'autre non) : %s" % (r["kill_events"],))
    assert any(e[2] == "ShockAssault" for e in r["kill_events"]), \
        "le passif ShockAssault n'a pas tire sur On(0xa) : %s" % (r["kill_events"],)


def test_shock_assault_buff_magnitude_matches_the_native_stat_modifier(shock_assault_case):
    """VALIDATION NON CIRCULAIRE, sur TROIS canaux independants :
      * `statMod.Amount` de l'entite-effet (= `StatModifierComponent+0x14`, ce que
        `StaticStatModifierEffect$$GetStatModificationAmount` relit) ;
      * `statModSources(attack)` (la `ValueModification` par SOURCE, residu natif 0) ;
      * `ability_var("ShockAssault", "extraDmg", <passif du POSEUR>, <mult du POSEUR>)` re-derive
        du gameconfig.
    Les trois doivent coincider : aucun scalaire n'est fitte."""
    r = shock_assault_case()
    native = int((r["live_effect"].get("statMod") or {}).get("Amount"))
    assert native == r["expected"], (
        "statMod.Amount natif %s != ShockAssault.extraDmg[L%s] x %s%% = %s"
        % (native, (r["poser_config"] or {}).get("passiveAbilityLevel"),
           (r["poser_config"] or {}).get("abilityVariablesMultiplier"), r["expected"]))
    assert r["live_statmod_effect"] == native, (
        "la ValueModification natif attribuee a l'entite-effet (%s) != statMod.Amount (%s)"
        % (r["live_statmod_effect"], native))
    assert int((r["live_statmod"] or {}).get("residual") or 0) == 0, \
        "residu natif non nul : %s" % (r["live_statmod"],)
    assert int((r["live_effect"].get("statMod") or {}).get("StatType")) == 0, \
        "l'axe natif n'est pas ATTACK : %s" % (r["live_effect"].get("statMod"),)
    assert int((r["live_effect"].get("statMod") or {}).get("ApplyCounter")) == 1, \
        "1000 empile (ApplyCounter != 1) -- le port ne modelise pas ce regime"


def test_shock_assault_buff_magnitude_follows_the_POSER_PASSIVE_level(shock_assault_case):
    """SECOND COUPLE DISCRIMINANT. Le regime nominal est DEGENERE (`buildNormalizedBC` met actif ET
    passif a 50) : on DISSOCIE avec `--unit-stat <bellator>:PassiveAbilityLevel=20`, l'actif restant
    a 50. Le natif doit suivre le PASSIF -- ce qui refute a la fois « la magnitude lit l'ACTIF » et
    « la magnitude est un scalaire »."""
    lo = shock_assault_case(passive=20)
    hi = shock_assault_case()
    a_lo = int((lo["live_effect"].get("statMod") or {}).get("Amount"))
    a_hi = int((hi["live_effect"].get("statMod") or {}).get("Amount"))
    assert (lo["poser_config"] or {}).get("activeAbilityLevel") == \
        (hi["poser_config"] or {}).get("activeAbilityLevel"), \
        "les deux bras ne dissocient rien : l'ACTIF a bouge aussi"
    assert a_lo != a_hi, "montage non discriminant : meme magnitude aux deux niveaux de passif"
    assert a_lo == lo["expected"] and a_hi == hi["expected"], (
        "le natif ne suit pas le niveau de PASSIF : %s (attendu %s) / %s (attendu %s)"
        % (a_lo, lo["expected"], a_hi, hi["expected"]))
    assert lo["declared"]["attributed"] == a_lo, \
        "MOTEUR: magnitude %s != natif %s au passif 20" % (lo["declared"]["attributed"], a_lo)


@pytest.mark.parametrize("passive", [None, 20])
def test_shock_assault_buff_seed_attribution_is_exact_and_not_opaque(shock_assault_case, passive):
    """CONDITION NECESSAIRE du revert : la contribution du seed vit sous une cle d'effet retirable,
    residu opaque 0, et vaut EXACTEMENT ce que le natif a attribue a l'entite-effet."""
    r = shock_assault_case(passive=passive)
    d = r["declared"]
    assert d["statmod_keys"], (
        "1000 SEEDE non attribue -- sa contribution est dans le residu opaque, donc NON retirable")
    assert d["opaque_residual"] == 0, "residu opaque non nul : %s" % (d["opaque_residual"],)
    assert d["attributed"] == r["live_statmod_effect"], (
        "montant attribue offline %s != montant natif %s"
        % (d["attributed"], r["live_statmod_effect"]))
    assert d["attack_on"] == r["live_attack"], \
        "MOTEUR: seed divergent (ATTACK=%s != live %s)" % (d["attack_on"], r["live_attack"])


def test_shock_assault_buff_removal_matches_the_native_one(shock_assault_case):
    """LA DUREE, confrontee au natif. LIVE : l'Inceptor rejoue au turn-start suivant
    (`PlayAutomaticUnits`), son attaque emet `On(0xa)` et 1000 part -- ATTACK redescend. MOTEUR :
    `attack_damage_attack_triggers` sur le porteur doit produire le MEME etat absolu."""
    r = shock_assault_case()
    assert not r["live_still_here"], "LIVE: 1000 survit a l'attaque de son porteur"
    d = r["declared"]
    assert not d["still_here"], "MOTEUR: 1000 non retire par On(0xa) & OwnerIsCaster"
    assert d["attack_off"] == r["live_attack_after"], (
        "MOTEUR: ATTACK apres retrait %s != live %s -- la ValueModification du seed n'est pas sortie"
        % (d["attack_off"], r["live_attack_after"]))
    d_live = r["live_attack"] - r["live_attack_after"]
    assert d_live == r["live_statmod_effect"], \
        "LIVE: delta a la consommation %s != montant du stat-mod %s" % (d_live, r["live_statmod_effect"])


def test_shock_assault_buff_undeclared_keeps_the_buff_alive_forever(shock_assault_case):
    """LE BRAS DISCRIMINANT -- sans lui rien de ce qui precede ne prouverait quoi que ce soit. La
    MEME capture, rejouee avec l'inscription RETIREE : les deux mondes rendent la MEME ATTACK
    AVANT le retrait, et divergent APRES."""
    r = shock_assault_case()
    u = r["undeclared"]
    assert u["attack_on"] == r["declared"]["attack_on"], (
        "les deux mondes divergent DEJA avant le retrait (%s vs %s)"
        % (u["attack_on"], r["declared"]["attack_on"]))
    assert u["opaque_residual"] > 0 and not u["statmod_keys"], (
        "sans inscription, la contribution devrait etre dans le residu opaque (residu=%s cles=%s)"
        % (u["opaque_residual"], u["statmod_keys"]))
    assert u["attack_off"] != r["live_attack_after"], (
        "le bras non declare rend le MEME resultat que le natif (%s) -- montage NON discriminant"
        % (u["attack_off"],))
    assert u["attack_off"] == u["attack_on"], \
        "le bras non declare devrait garder le buff A VIE (%s -> %s)" % (u["attack_on"], u["attack_off"])
