"""#1024-r2 -- le BONUS d'`OnMyPosition_ExtraDamagePct` (1444) CONFRONTE LIVE, en regime SEPARANT.
Port : `engine/entities/effects/loki/extra_damage_aura.py::OnMyPositionExtraDamagePctEffect`.

CE QUE CE FICHIER GARDE, ET QUE LE CLIQUET OFFLINE NE PEUT PAS GARDER. L'offline
(`test_1024r2_on_my_position_offline.py`) montre qu'un etat SYNTHETIQUE traverse les gates ; il ne
peut pas montrer que le JEU produit la matiere ni que le NATIF applique le meme nombre. Ici on
compare le PREVIEW natif (`aiPredict` = `IdunBattle.Core.Services.DamagePredictionQuery$$
GetAllPredictions`) a la prediction du PORT sur le MEME etat, sur QUATRE bras.

⚠ LE PIEGE QUI ANNULERAIT CETTE VALIDATION. `rl_duel build` impose `targetRarity = 5` a toute unite
normalisee : dans le regime PAR DEFAUT, `HasRarity(Caster, Mythic)` (le BONUS) et
`UnitsWithRarity(Friends(Owner, HeroUnits), Mythic)` (le SELECTEUR) sont uniformement VRAIS, et un
port qui OUBLIERAIT ces deux etages serait d'accord avec le natif PARTOUT. Les bras `caster` et
`selecteur` fabriquent le regime SEPARANT (`--unit-stat "<vis>:Rarity=3"`).

⚠ `caster` et `selecteur` ne sont PAS redondants, et c'est la GEOMETRIE qui les separe : l'attaquant
est place a distance 2 de la cible, donc il n'est PAS lui-meme un voisin du selecteur. Descendre sa
rarete eteint le BONUS en laissant l'effet POSE sur la cible (`targetIds` non vide) ; descendre
celle des DEUX voisins vide le SELECTEUR (`targetIds` vide) en laissant l'attaquant Mythique. Le
discriminant est DIRECT : `targetIds` de l'effet 1444, lu sur la MoW.

Le TEMOIN MELEE (`adeptHospitaller`, `Range = null`) attaque la MEME cible affectee dans le bras
`on` : sa prediction ne bouge PAS. C'est le gate `IsRangedAttack`, que les DEUX voisins de famille
de cette aura (1442 `BlightedLand`, 1449 `MoreGitzOverEre`) n'ont pas -- 1449 portant meme la
polarite INVERSE (`IsMeleeAttack`).

Probe : `scripts/python/probe_1024r2_on_my_position_bonus_live.py` (geometrie FORCEE par
`--place`/`--a-place`). Un montage qui ne s'installe pas LEVE et fait ROUGIR ce fichier -- il ne
skippe pas (#268/#455).

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_1024r2_on_my_position_bonus_live as P

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1024r2_on_my_position_bonus_live.py",
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
        # Le canal de rarete en amont et le substrat de traits (`HeroUnits`).
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE : les nombres viennent du JEU (`aiPredict`), le montage passe par "
              "`--equip-mythic` et par `astraOrdnanceBattery.mythicAbilities`, et la magnitude est "
              "lue au gameconfig (`OnMyPosition.extraDmgPct`) -- les trois se periment SEPAREMENT "
              "du code, et un changement de build change ce que le jeu rend.",
}


def _pct_1444() -> int:
    """`ConfigVar(0xa = extraDmgPct)` au palier TERTIAIRE 1 (`--equip-mythic` sans niveau)."""
    from engine.entities.effects.magnitude import ability_var
    return int(ability_var("OnMyPosition", "extraDmgPct", 1))


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
                pytest.fail("montage #1024-r2 NON INSTALLE (bras=%s) : %s" % (nom, exc),
                            pytrace=False)
        return cache[nom]
    return _b


def test_le_montage_pose_bien_l_aura_et_le_regime_separe(bras):
    """TEMOIN DE NON-DEGENERESCENCE. Sans lui, les tests suivants pourraient tous passer parce que
    RIEN n'est monte : `off` == `on` == `selecteur` serait un accord VIDE."""
    on, off = bras("on"), bras("off")
    assert on["auraPosee"] is True, "la mythique n'est pas montee : rien n'est mesure"
    assert off["auraPosee"] is False, "le bras temoin porte l'aura : il ne temoigne de rien"
    # Le canal de rarete REPOND, et il est nomme (cinq enums du build partagent les six memes
    # ordinaux : seul le nom PLEIN trahirait une confusion d'appariement).
    assert on["rarityEnum"] == "idun.meta.Rarity"
    assert set(on["rarityByEntity"].values()) == {5}, "bras `on` : regime Mythic uniforme attendu"
    for nom in ("caster", "selecteur"):
        assert 3 in set(bras(nom)["rarityByEntity"].values()), (
            "bras `%s` : le forcage `--unit-stat Rarity=3` n'a pas mordu -- le regime reste "
            "DEGENERE et tout vert obtenu ici serait VIDE" % nom)
    # La GEOMETRIE est celle qui rend `caster` et `selecteur` non redondants : l'attaquant N'EST PAS
    # adjacent a la cible (sinon il serait lui-meme dans le selecteur, et les deux bras se
    # confondraient -- exactement le piege que #1025-r1 a du contourner par un 3e bras).
    import hexgeo
    assert hexgeo.distance(P.POS_ATT, P.POS_FOE) == 2, (
        "l'attaquant doit rester a distance 2 : %s -> %s" % (P.POS_ATT, P.POS_FOE))
    assert hexgeo.distance(P.POS_ANCRE, P.POS_FOE) == 1
    assert hexgeo.distance(P.POS_MELEE, P.POS_FOE) == 1


def test_le_natif_applique_le_bonus_et_le_port_le_suit(bras):
    """Bras `on` : accord BIT-EXACT natif/port, et la contribution est NOMMEMENT celle de 1444.

    Le second controle n'est pas un ornement : deux erreurs compensatoires donneraient le meme
    total. `mods_detail` dit QUEL `EffectBonus` a produit le facteur."""
    on = bras("on")
    assert on["natif"] == on["port"], (
        "port != natif dans le bras ou l'aura FIRE : natif=%s port=%s" % (on["natif"], on["port"]))
    assert ("PercentIncrease", _pct_1444(), True) in on["portPctList"], (
        "la contribution %%-attaquant de 1444 (+%s%%) n'est pas dans la pct-list : %s"
        % (_pct_1444(), on["portPctList"]))
    assert on["cibleEstVisee"] is True, (
        "`targetIds` de 1444 ne contient pas la cible : le selecteur natif ne la vise pas, donc "
        "l'accord ci-dessus ne porte sur RIEN")


def test_le_bonus_est_REELLEMENT_load_bearing(bras):
    """`on` vs `off` : sans la mythique equipee, le NATIF rend un autre nombre.

    ⚠ ON NE FITTE PAS LE SCALAIRE FINAL (mesure #1025-r1 : le rapport `on/off` n'est PAS
    `1 + pct/100`, le natif accumulant le %% dans `attackModifiers` que
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` consomme AVANT
    percage/armure, avec un `Fix64.Round` par accumulateur non nul). Ce qui se compare est la
    DECOMPOSITION PAR ETAGE : `base`, `pierce`, `armor`, `hits` identiques entre les deux bras, et
    pour SEULE difference l'entree `PercentIncrease(extraDmgPct)` de la pct-list."""
    on, off = bras("on"), bras("off")
    assert on["natif"] != off["natif"], (
        "le natif rend la MEME chose avec et sans l'aura -- le montage ne mesure pas le bonus")
    assert off["natif"] == off["port"], "port != natif dans le bras SANS aura"
    entree = ("PercentIncrease", _pct_1444(), True)
    assert entree not in off["portPctList"], (
        "le port contribue alors que l'effet n'existe pas : %s" % (off["portPctList"],))
    mon, moff = on["portMeta"], off["portMeta"]
    for etage in ("base", "pierce", "armor", "hits"):
        assert mon.get(etage) == moff.get(etage), (
            "l'etage `%s` a bouge entre les deux bras (%s vs %s) : l'ecart mesure n'est PAS le "
            "seul fait de l'aura" % (etage, mon.get(etage), moff.get(etage)))
    # La SEULE difference de decomposition attendue est l'entree de 1444 -- les autres
    # contributions (`HeavyWeapon_ExtraDmg`, `CondemnorStake_ExtraDmg`, ...) sont communes.
    assert ([x for x in on["portPctList"] if x != entree] == list(off["portPctList"])), (
        "la pct-list differe ailleurs que sur l'entree de 1444 : %s vs %s"
        % (on["portPctList"], off["portPctList"]))


def test_le_gate_du_BONUS_seul_seteint_sans_toucher_au_selecteur(bras):
    """Bras `caster` : `HasRarity(Caster@<DSLSelectors+0x48>, 5 = Mythic)` est FAUX, mais le
    `$$CreateTargetSelector` TIENT -- l'effet reste POSE sur la cible.

    C'est ce qui SEPARE les deux usages de la rarete dans cette ability. Sans ce bras, on ne
    saurait pas si l'extinction vient du trigger ou du selecteur."""
    off, x = bras("off"), bras("caster")
    assert x["auraPosee"] is True, "l'aura doit rester POSEE : c'est le GATE qu'on eteint, pas elle"
    assert x["cibleEstVisee"] is True, (
        "`targetIds` s'est vide : ce bras n'isole plus le trigger -- il eteint AUSSI le selecteur")
    assert x["natif"] == off["natif"], (
        "le natif applique encore le bonus alors que `HasRarity(Caster, Mythic)` est FAUX : "
        "natif=%s base=%s" % (x["natif"], off["natif"]))
    assert x["port"] == x["natif"], (
        "port != natif dans le bras `caster` : port=%s natif=%s" % (x["port"], x["natif"]))
    assert ("PercentIncrease", _pct_1444(), True) not in x["portPctList"], (
        "le port contribue encore : %s" % (x["portPctList"],))


def test_le_gate_du_SELECTEUR_seul_vide_les_cibles(bras):
    """Bras `selecteur` : les DEUX voisins de la cible descendent en `Rarity.Epic`, l'attaquant
    reste Mythique. `UnitsWithRarity(Friends(Owner, HeroUnits(AllUnits, 3), 3), Mythic, 3)` ne
    contient plus personne -> `targetIds` de 1444 devient VIDE.

    Verdict INVERSE du bras precedent, et c'est ce qui etablit que le port lit bien DEUX etages
    distincts et non un seul."""
    off, x = bras("off"), bras("selecteur")
    assert x["auraPosee"] is True, "l'aura doit rester POSEE"
    assert x["cibleEstVisee"] is False, (
        "`targetIds` contient encore la cible alors qu'aucun voisin n'est Mythique : %s"
        % (x["cibles1444"],))
    assert x["natif"] == off["natif"], (
        "le natif applique encore le bonus : natif=%s base=%s" % (x["natif"], off["natif"]))
    assert x["port"] == x["natif"], (
        "port != natif dans le bras `selecteur` : port=%s natif=%s" % (x["port"], x["natif"]))
    assert ("PercentIncrease", _pct_1444(), True) not in x["portPctList"], (
        "le port contribue encore : %s" % (x["portPctList"],))


def test_IsRangedAttack_le_temoin_MELEE_ne_bouge_JAMAIS(bras):
    """Le TEMOIN MELEE (`adeptHospitaller`, `Range = null` -> melee au sens
    d'`IdunBattle.Entities.WeaponProfile$$get_IsMelee`) attaque la MEME cible, AFFECTEE par l'aura
    dans le bras `on`. Sa prediction est IDENTIQUE dans les quatre bras.

    ⚠ Le bras qui exerce vraiment ce gate est `on` : la cible y porte l'effet et l'attaquant
    DISTANCE monte, alors que le temoin MELEE reste a la base. Dans `caster`/`selecteur` le bonus
    est de toute facon eteint -- l'invariance y est necessaire mais pas separante."""
    on = bras("on")
    valeurs = {nom: tuple(bras(nom)["natifMelee"]) for nom in ("on", "off", "caster", "selecteur")}
    assert len(set(valeurs.values())) == 1, (
        "la prediction MELEE bouge d'un bras a l'autre -- `IsRangedAttack` n'est pas exerce : %s"
        % (valeurs,))
    assert tuple(on["natifMelee"]) == tuple(on["portMelee"]), (
        "port != natif sur le temoin MELEE dans le bras `on` : natif=%s port=%s"
        % (on["natifMelee"], on["portMelee"]))
    # TEMOIN NON NUL du bras `on` : l'attaquant DISTANCE, lui, a bien monte sur la MEME cible.
    assert tuple(on["natif"]) != tuple(bras("off")["natif"]), (
        "l'invariance du temoin MELEE ne separe rien si l'attaquant DISTANCE ne bouge pas non plus")
