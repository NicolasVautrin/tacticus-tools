"""#1035-r2 -- le BONUS de `BlightedLand_ExtraDamagePct` (1442) CONFRONTE LIVE, en regime SEPARANT.
Port : `engine/entities/effects/loki/extra_damage_aura.py::BlightedLandEffect`.

CE QUE CE FICHIER GARDE, ET CE QUE L'OFFLINE NE PEUT PAS GARDER. Le cliquet offline
(`test_1035r2_1025r1_auras_mow_offline.py`) montre qu'un etat SYNTHETIQUE traverse les trois etages
du selecteur ; il ne peut pas montrer que le JEU pose une tuile `Contaminated`, ni que le NATIF
applique le meme nombre. Ici on compare le PREVIEW natif (`aiPredict`) a la prediction du PORT sur
le MEME etat, sur TROIS bras.

LE TERRAIN VIENT DE LA PORTEUSE ELLE-MEME : `deathCrawler` porte l'active `PlagueburstMortar`
(1169), dont l'`ExecuteBehaviour` finit par `AddEffect(0x4dc = Contaminated, <tuile ciblee> + ...)`.
Le montage n'a donc besoin d'aucune unite tierce.

⚠ LE BRAS TEMOIN TIRE LE MORTIER LUI AUSSI. Sans cela il differerait du bras `on` par DEUX choses
(l'aura ET l'etat du terrain, `Contaminated_Unit` compris, qui reduit l'armure de l'occupant), et
l'ecart mesure ne serait plus imputable a l'aura seule.

⚠ LE PIEGE QUI ANNULERAIT CETTE VALIDATION : `rl_duel build` impose `targetRarity = 5`, donc
`UnitsWithRarity(..., Mythic)` est uniformement VRAI dans le regime par defaut. Le bras `rarity`
fabrique le regime SEPARANT, et le TEMOIN NON NUL est le couple `on`/`rarity` : la MEME unite, sur
la MEME tuile contaminee, PRISE quand elle est Mythique et ECARTEE quand elle est Epic.

Probe : `scripts/python/probe_1035r2_blighted_land_bonus_live.py`. Un montage qui ne s'installe pas
LEVE et fait ROUGIR ce fichier -- il ne skippe pas (#268/#455).

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_1035r2_blighted_land_bonus_live as P

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1035r2_blighted_land_bonus_live.py",
        # La classe portee et son registre.
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/entities/effects/factory.py",
        # Les DEUX faces du ctx d'aura ATTAQUE (`att_rarity`, `tile_effects_by_pos`).
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/entities/effects/__init__.py",
        # Le chemin de prediction compare au natif.
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        # Le POSEUR de la tuile Contaminated (l'active de la MEME MoW).
        "scripts/python/engine/runner/abilities/deathguard.py",
        # Le MONTAGE et le canal de rarete.
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/runner/snapshot.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE : les nombres viennent du JEU (`aiPredict`), le terrain est pose "
              "par une ability du jeu (`PlagueburstMortar`), le montage passe par `--equip-mythic` "
              "et `deathCrawler.mythicAbilities`, et la magnitude est lue au gameconfig "
              "(`BlightedLand.extraDmgPct`) -- tous se periment SEPAREMENT du code.",
}


@pytest.fixture(scope="module")
def bras(live_session):
    """Fabrique : `bras("on")` -> la mesure d'UN bras. UN runner par bras, DISPOSE en sortie."""
    cache: dict = {}

    def _b(nom: str) -> dict:
        if nom not in cache:
            try:
                cache[nom] = P.run(arm=nom, verbose=False)
            except RuntimeError as exc:
                pytest.fail("montage #1035-r2 NON INSTALLE (bras=%s) : %s" % (nom, exc),
                            pytrace=False)
        return cache[nom]
    return _b


def test_le_montage_pose_la_tuile_l_aura_et_le_regime_separe(bras):
    """TEMOIN DE NON-DEGENERESCENCE : sans lui, l'accord des tests suivants pourrait tenir a ce que
    RIEN n'est monte."""
    on, off, rar = bras("on"), bras("off"), bras("rarity")
    for nom, r in (("on", on), ("off", off), ("rarity", rar)):
        assert r["attaquantContamine"] is True, (
            "bras `%s` : la tuile de l'attaquant n'est pas Contaminee (%s) -- le terrain n'est pas "
            "monte, donc l'etage `UnitsOnTilesWithEffect` n'est pas exerce"
            % (nom, r["tuileAttaquant"]))
    assert on["auraPosee"] is True, "la mythique n'est pas montee : rien n'est mesure"
    assert off["auraPosee"] is False, "le bras temoin porte l'aura : il ne temoigne de rien"
    assert on["rarityEnum"] == "idun.meta.Rarity"
    assert set(on["rarityByEntity"].values()) == {5}, "bras `on` : regime Mythic uniforme attendu"
    assert 3 in set(rar["rarityByEntity"].values()), (
        "bras `rarity` : le forcage `--unit-stat Rarity=3` n'a pas mordu -- le regime reste "
        "DEGENERE et tout vert obtenu ici serait VIDE")


def test_le_natif_applique_le_bonus_et_le_port_le_suit(bras):
    """Bras `on` : accord BIT-EXACT, et la contribution est NOMMEMENT celle de 1442 (deux erreurs
    compensatoires donneraient le meme total -- `mods_detail` dit QUEL `EffectBonus` l'a produit)."""
    on = bras("on")
    assert on["natif"] == on["port"], (
        "port != natif dans le bras ou l'aura FIRE : natif=%s port=%s" % (on["natif"], on["port"]))
    from engine.entities.effects.magnitude import ability_var
    pct = int(ability_var("BlightedLand", "extraDmgPct", 1))   # palier TERTIAIRE 1
    assert ("PercentIncrease", pct, True) in on["portPctList"], (
        "la contribution %%-attaquant de 1442 (+%d%%) n'est pas dans la pct-list : %s"
        % (pct, on["portPctList"]))


def test_le_bonus_est_REELLEMENT_load_bearing(bras):
    """`on` vs `off` : MEME terrain, MEME `Contaminated_Unit`, seule l'aura change -- et le NATIF
    rend un autre nombre.

    ⚠ ON NE FITTE PAS LE SCALAIRE FINAL : le natif accumule le pourcentage dans `attackModifiers`,
    consomme AVANT percage/armure par `IdunBattle.Core.Services.DamagePrediction$$
    CalculateBaseDamageWithAllModifiers`, avec un `Fix64.Round` par accumulateur non nul -- le
    rapport des nombres RENDUS n'est donc pas `1 + pct/100`. On compare la DECOMPOSITION PAR
    ETAGE."""
    on, off = bras("on"), bras("off")
    assert on["natif"] != off["natif"], (
        "le natif rend la MEME chose avec et sans l'aura -- le montage ne mesure pas le bonus")
    assert off["natif"] == off["port"], "port != natif dans le bras SANS aura"
    from engine.entities.effects.magnitude import ability_var
    pct = int(ability_var("BlightedLand", "extraDmgPct", 1))
    mon, moff = on["portMeta"], off["portMeta"]
    for etage in ("base", "pierce", "armor", "hits"):
        assert mon.get(etage) == moff.get(etage), (
            "l'etage `%s` a bouge entre les deux bras (%s vs %s) : l'ecart n'est PAS le seul fait "
            "de l'aura" % (etage, mon.get(etage), moff.get(etage)))
    ajoutees = [x for x in on["portPctList"] if x not in off["portPctList"]]
    assert ajoutees == [("PercentIncrease", pct, True)], (
        "la SEULE contribution ajoutee par l'aura doit etre celle de 1442 : %s" % (ajoutees,))


def test_le_gate_de_rarete_eteint_le_bonus_des_DEUX_cotes(bras):
    """REGIME SEPARANT, TEMOIN NON NUL : la MEME unite, sur la MEME tuile contaminee, ECARTEE parce
    qu'elle n'est plus Mythique. Le natif retombe sur la base ET le port aussi."""
    off, rar = bras("off"), bras("rarity")
    assert rar["auraPosee"] is True, "l'aura doit rester POSEE : c'est le GATE qu'on eteint"
    assert rar["attaquantContamine"] is True, "la tuile doit rester Contaminee"
    assert rar["natif"] == off["natif"], (
        "le natif applique encore le bonus a un attaquant NON Mythique : natif=%s base=%s"
        % (rar["natif"], off["natif"]))
    assert rar["port"] == rar["natif"], (
        "port != natif dans le bras `rarity` : port=%s natif=%s" % (rar["port"], rar["natif"]))
    assert rar["portPctList"] == off["portPctList"], (
        "le port contribue encore alors que `UnitsWithRarity(..., Mythic)` est FAUX : %s"
        % (rar["portPctList"],))
