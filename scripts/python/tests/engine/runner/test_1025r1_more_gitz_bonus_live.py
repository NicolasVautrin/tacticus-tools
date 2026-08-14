"""#1025-r1 -- le BONUS de `MoreGitzOverEre_ExtraDamagePct` (1449) CONFRONTE LIVE, en regime
SEPARANT. Port : `engine/entities/effects/loki/extra_damage_aura.py::MoreGitzOverEreExtraDamagePctEffect`.

CE QUE CE FICHIER GARDE, ET CE QUE LE CLIQUET OFFLINE NE PEUT PAS GARDER. L'offline
(`test_1035r2_1025r1_auras_mow_offline.py`) montre qu'un etat SYNTHETIQUE traverse les gates ; il
ne peut pas montrer que le JEU produit la matiere ni que le NATIF applique le meme nombre. Ici on
compare le PREVIEW natif (`aiPredict` = `IdunBattle.Core.Services.DamagePredictionQuery$$
GetAllPredictions`) a la prediction du PORT sur le MEME etat, sur QUATRE bras.

⚠ LE PIEGE QUI ANNULERAIT CETTE VALIDATION. `rl_duel build` impose `targetRarity = 5` a toute unite
normalisee : dans le regime PAR DEFAUT, `HasRarity(Caster, Mythic)` et `UnitsWithRarity(voisins,
Mythic)` sont uniformement VRAIS, et un port qui OUBLIERAIT ces deux etages serait d'accord avec le
natif PARTOUT. Les bras `caster` et `count` fabriquent donc le regime SEPARANT
(`--unit-stat "<vis>:Rarity=3"`), et le TEMOIN NON NUL est le couple `on`/`count` : le MEME
`orksWarboss` est PRIS quand il est Mythique et ECARTE quand il est Epic, toutes choses egales.

⚠ `caster` et `count` ne sont PAS redondants. Dans `caster` (l'attaquant descend en Epic) les DEUX
gates tombent ENSEMBLE -- l'attaquant perd son `HasRarity` et sort en meme temps du compte des
voisins Mythiques, `AdjacentUnits(<la cible>)` ne l'excluant pas. Seul `count` (c'est le VOISIN qui
descend) isole `AmountIsEqualOrGreater(..., Direct(2))` sans toucher a l'attaquant.

Probe : `scripts/python/probe_1025r1_more_gitz_bonus_live.py` (geometrie FORCEE par
`--place`/`--a-place` : jamais << bloque par la geometrie de spawn >>). Un montage qui ne
s'installe pas LEVE et fait ROUGIR ce fichier -- il ne skippe pas (#268/#455).

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_1025r1_more_gitz_bonus_live as P

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1025r1_more_gitz_bonus_live.py",
        # La classe portee et son registre.
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/entities/effects/factory.py",
        # Les DEUX faces du ctx d'aura DEFENSE et leurs substrats.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/effects/__init__.py",
        # Le chemin de prediction compare au natif.
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        # Le MONTAGE (voie tertiaire, placement, forcage de rarete).
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        # Le canal de rarete en amont.
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/runner/snapshot.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE : les nombres viennent du JEU (`aiPredict`), le montage passe par "
              "`--equip-mythic` et par `orksRukkatrukk.mythicAbilities`, et la magnitude est lue au "
              "gameconfig (`MoreGitzOverEre.extraDmgPct`) -- les trois se periment SEPAREMENT du "
              "code, et un changement de build change ce que le jeu rend.",
}


@pytest.fixture(scope="module")
def bras(live_session):
    """Fabrique : `bras("on")` -> la mesure d'UN bras. UN runner par bras, DISPOSE en sortie de
    `run()`. Cache module : les quatre bras servent plusieurs assertions chacun."""
    cache: dict = {}

    def _b(nom: str) -> dict:
        if nom not in cache:
            try:
                cache[nom] = P.run(arm=nom, verbose=False)
            except RuntimeError as exc:
                pytest.fail("montage #1025-r1 NON INSTALLE (bras=%s) : %s" % (nom, exc),
                            pytrace=False)
        return cache[nom]
    return _b


def test_le_montage_pose_bien_l_aura_et_le_regime_separe(bras):
    """TEMOIN DE NON-DEGENERESCENCE. Sans lui, les trois tests suivants pourraient tous passer
    parce que RIEN n'est monte : `off` == `on` == `count` serait un accord VIDE."""
    on, off = bras("on"), bras("off")
    assert on["auraPosee"] is True, "la mythique n'est pas montee : rien n'est mesure"
    assert off["auraPosee"] is False, "le bras temoin porte l'aura : il ne temoigne de rien"
    # Le canal de rarete REPOND, et il est nomme (cinq enums du build partagent les six memes
    # ordinaux : seul le nom PLEIN trahirait une confusion d'appariement).
    assert on["rarityEnum"] == "idun.meta.Rarity"
    assert set(on["rarityByEntity"].values()) == {5}, "bras `on` : regime Mythic uniforme attendu"
    assert 3 in set(bras("count")["rarityByEntity"].values()), (
        "bras `count` : le forcage `--unit-stat Rarity=3` n'a pas mordu -- le regime reste "
        "DEGENERE et tout vert obtenu ici serait VIDE")


def test_le_natif_applique_le_bonus_et_le_port_le_suit(bras):
    """Bras `on` : accord BIT-EXACT natif/port, et la contribution est NOMMEMENT celle de 1449.

    Le second controle n'est pas un ornement : deux erreurs compensatoires donneraient le meme
    total. `mods_detail` dit QUEL `EffectBonus` a produit le facteur."""
    on = bras("on")
    assert on["natif"] == on["port"], (
        "port != natif dans le bras ou l'aura FIRE : natif=%s port=%s" % (on["natif"], on["port"]))
    from engine.entities.effects.magnitude import ability_var
    pct = ability_var("MoreGitzOverEre", "extraDmgPct", 1)   # palier TERTIAIRE 1
    assert ("PercentIncrease", int(pct), True) in on["portPctList"], (
        "la contribution %%-attaquant de 1449 (+%s%%) n'est pas dans la pct-list : %s"
        % (pct, on["portPctList"]))


def test_le_bonus_est_REELLEMENT_load_bearing(bras):
    """`on` vs `off` : sans la mythique equipee, le NATIF rend un autre nombre. Sans ce couple,
    l'accord du test precedent pourrait tenir a un bonus qui ne change rien.

    ⚠ ON NE FITTE PAS LE SCALAIRE FINAL, et une premiere version de ce test l'a tente : le rapport
    `on/off` des bornes N'EST PAS `1 + pct/100` (mesure : 4773 contre 4775 attendus sur la borne
    haute). Le natif n'applique pas le pourcentage au nombre RENDU -- il l'accumule dans
    `attackModifiers`, que `IdunBattle.Core.Services.DamagePrediction$$
    CalculateBaseDamageWithAllModifiers` consomme AVANT percage/armure, avec un `Fix64.Round` par
    accumulateur non nul. Fitter le rapport ferait donc rougir un port JUSTE.

    Ce qui se compare, c'est la DECOMPOSITION PAR ETAGE : `base`, `pierce`, `armor`, `hits`
    identiques entre les deux bras, et pour SEULE difference l'entree `PercentIncrease(extraDmgPct)`
    de la pct-list."""
    on, off = bras("on"), bras("off")
    assert on["natif"] != off["natif"], (
        "le natif rend la MEME chose avec et sans l'aura -- le montage ne mesure pas le bonus")
    assert off["natif"] == off["port"], "port != natif dans le bras SANS aura"
    assert off["portPctList"] == [], "le port contribue alors que l'effet n'existe pas"
    from engine.entities.effects.magnitude import ability_var
    pct = int(ability_var("MoreGitzOverEre", "extraDmgPct", 1))
    mon, moff = on["portMeta"], off["portMeta"]
    for etage in ("base", "pierce", "armor", "hits"):
        assert mon.get(etage) == moff.get(etage), (
            "l'etage `%s` a bouge entre les deux bras (%s vs %s) : l'ecart mesure n'est PAS le "
            "seul fait de l'aura" % (etage, mon.get(etage), moff.get(etage)))
    assert on["portPctList"] == [("PercentIncrease", pct, True)], (
        "la SEULE difference de decomposition attendue est l'entree de 1449 : %s"
        % (on["portPctList"],))


@pytest.mark.parametrize("nom,etage", [
    ("caster", "HasRarity(Caster@<DSLSelectors+0x48>, 5 = Mythic)"),
    ("count", "AmountIsEqualOrGreater(Friends(Owner, UnitsWithRarity(AdjacentUnits(<cible>), "
              "Mythic)), Direct(2))"),
])
def test_chaque_gate_de_rarete_eteint_le_bonus_des_DEUX_cotes(bras, nom, etage):
    """REGIME SEPARANT, TEMOIN NON NUL. Le natif retombe sur la base ET le port aussi -- une
    extinction d'un seul cote serait une divergence, pas une validation."""
    off, x = bras("off"), bras(nom)
    assert x["auraPosee"] is True, "l'aura doit rester POSEE : c'est le GATE qu'on eteint, pas elle"
    assert x["natif"] == off["natif"], (
        "le natif applique encore le bonus alors que `%s` est FAUX : natif=%s base=%s"
        % (etage, x["natif"], off["natif"]))
    assert x["port"] == x["natif"], (
        "port != natif dans le bras `%s` : port=%s natif=%s" % (nom, x["port"], x["natif"]))
    assert x["portPctList"] == [], (
        "le port contribue encore alors que `%s` est FAUX : %s" % (etage, x["portPctList"]))
