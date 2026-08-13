"""#1009 -- CONFRONTATION LIVE des deux reliques DARK ANGELS : NATIF <-> PORT.

UN SEUL montage porte les deux abilities (`darkaCompanion` << Forcas >> / `MonsterSlayerOfCaliban`
1527, `darkaTerminator` << Baraqiel >> / `RelicPowerFist` 1466), toutes deux equipees au **niveau
3** -- choisi parce qu'il SEPARE le palier TERTIAIRE du palier CLAMPE des passifs (`extraDmg`
543 vs 728, `blockDmg` 1629 vs 2184, `chance` 36 vs 50). A un niveau ou les deux coincident, ces
tests ne discrimineraient rien.

TROIS BRAS, chacun tombant pour une raison DIFFERENTE (montage :
`probe_1009_reliques_dark_angels.py`) :
  * POSITIF : les deux reliques equipees -> 1539/1540 captes sur Forcas, bonus de degat ENGAGE vs
              `Vehicle`/`BigTarget`, et l'attaque de Baraqiel pose `Pinned` sur sa cible ;
  * TEMOIN  : MEME montage, MEMES attaques, SANS `--equip-relic` -> aucun des deux effets, aucun
              `Pinned`/`Stunned`. Sans lui, un `Pinned` observe ne prouverait rien ;
  * PORT    : la MEME capture pre-attaque, rejouee OFFLINE avec le MT19937 dumpe, rend les MEMES
              per-hit, les MEMES PV, le MEME etat de MT et les MEMES effets poses.

⚠ **L'ETAT DU MT EST UN OBSERVABLE A PART ENTIERE**, et c'est le seul qui garde le point le plus
dur du port de `RelicPowerFist` : ses DEUX `Maybe` consomment DEUX tirages `next_bool`, meme quand
les deux tombent a faux. Un port qui n'en ferait qu'un (ou aucun) desynchroniserait le PRNG pour
tout le reste de la bataille sans qu'aucun degat ne bouge. Mesure #1009 : avant la reparation du
rail de niveau, `mti` valait **14** cote port contre **16** cote natif.

⚠ Le seed `4242` n'est pas decoratif : c'est celui pour lequel le premier tirage de `RelicPowerFist`
PASSE au niveau 3 (36 %), donc le seul de ceux essayes (777 / 31337 / 999 / 4242) qui donne un bras
POSITIF sur l'axe << effet pose >>. Les trois autres restent verts sur la CONCORDANCE.

⚠ Montage non installe => ECHEC, jamais skip (#268).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE MONTAGE de ce fichier.
        "scripts/python/probe_1009_reliques_dark_angels.py",
        # LES DEUX MIRRORS et leurs registres.
        "scripts/python/engine/entities/effects/loki/monster_slayer_of_caliban.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/loki/relic_power_fist.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # LE NOEUD DSL neuf et les formules qu'il compose.
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/behaviours.py",
        # LE RAIL du couple TERTIAIRE (#1005/#1007/#1009) -- sans lui, les magnitudes sont celles
        # du palier clampe des passifs, en silence.
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects_state.py",
        # LES CANAUX que les deux faces empruntent.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effect_type.py",
        # LE MONTAGE #237 de la relique.
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier confronte au NATIF les deux reliques Dark Angels `MonsterSlayerOfCaliban` "
        "(1527) et `RelicPowerFist` (1466). Les chemins listes sont ceux dont une modification "
        "peut faire changer un verdict : le montage, les deux mirrors, leurs registres, le noeud "
        "DSL `IsSpecialActiveAbility`, le rail du couple TERTIAIRE et les canaux de degat/effet."),
}

import probe_1009_reliques_dark_angels as P                                  # noqa: E402

#: Le seed qui donne le bras POSITIF sur l'axe << effet pose >> (cf. l'en-tete).
SEED = "4242"

#: Les paliers ATTENDUS au niveau 3, et ceux du palier CLAMPE (niveau des passifs = 50). Les DEUX
#: sont assertes : le second est ce qu'un rail de niveau casse ferait lire.
EXTRA_DMG_L3, EXTRA_DMG_CLAMP = 543, 728
BLOCK_DMG_L3, BLOCK_DMG_CLAMP = 1629, 2184
CHANCE_L3, CHANCE_CLAMP = 36, 50


@pytest.fixture(scope="module")
def cas(build_runner, rpc):
    """Fabrique : `cas(True)` -> le releve du montage AVEC les deux reliques. Portee MODULE (un
    build par regime, deux au total)."""
    from engine.runner import snapshot as _snap
    cache: dict = {}

    def _case(avec_reliques: bool) -> dict:
        key = bool(avec_reliques)
        if key not in cache:
            # Le canal `unitAbilityStates` est AMBIANT (#363) : sans transport lie, `load_state`
            # ne voit AUCUNE relique et le port lit le palier des passifs -- exactement le regime
            # que ces tests doivent distinguer. Le lier ICI, pas dans le probe : c'est le HARNAIS
            # qui possede le transport.
            prev = _snap.bind_live_rpc(rpc)
            try:
                r = P.run(rpc, key, build_runner=build_runner, keep=True, seed=SEED)
            finally:
                _snap.bind_live_rpc(prev)
            if not r.get("ok"):
                pytest.fail("montage #1009 NON INSTALLE (reliques=%s) : %s" % (key, r.get("why")))
            cache[key] = r
        return cache[key]

    return _case


# --------------------------------------------------------------------------------------------
# `MonsterSlayerOfCaliban` (1527) -- les DEUX owner-effects poses a l'init
# --------------------------------------------------------------------------------------------
def test_le_natif_pose_les_deux_owner_effects_de_la_relique(cas):
    """POSITIF -- `OnOwnerSpecificAbilityInit(1527)` -> `AddEffect(1539) & AddExtraBlockEffect
    ToOwner(1540)`, mesure sur le NATIF (`decisionView.units[].effects`).

    C'est ce bras qui etablit le CANAL : les deux effets sont la DES LE DEPLOIEMENT, sans qu'aucune
    attaque n'ait eu lieu -> `ABILITY_INIT_OWNER_EFFECTS`, jamais `RELIC_ABILITY_TRIGGERS`."""
    r = cas(True)
    natif = r["forcas_effects_natif"]
    assert 1539 in natif and 1540 in natif, (
        "le NATIF ne pose pas les deux owner-effects de 1527 sur Forcas : %r" % (natif,))
    o = r["offline"]
    assert o["forcas_tertiary"] == "MonsterSlayerOfCaliban" and o["forcas_tertiary_level"] == 3, (
        "la relique n'est pas montee au niveau attendu : %r / %r"
        % (o["forcas_tertiary"], o["forcas_tertiary_level"]))
    assert o["has_extra_dmg"] and o["has_extra_block"], (
        "le PORT n'a pas materialise les deux effets : dmg=%r block=%r"
        % (o["has_extra_dmg"], o["has_extra_block"]))


def test_sans_la_relique_aucun_des_deux_effets(cas):
    """TEMOIN -- MEME porteur, MEME board, MEMES tuiles, SANS `--equip-relic`.

    Sans lui, la presence des effets ne prouverait pas qu'ils viennent de la RELIQUE : Forcas porte
    par ailleurs `EnmityForTheUnworthy_ExtraDamagePct` et `CalibaniteGreatswordStrike`, deux
    effets de degat de son KIT."""
    r = cas(False)
    natif = r["forcas_effects_natif"]
    assert 1539 not in natif and 1540 not in natif, (
        "le NATIF pose 1539/1540 SANS relique : %r -- le bras positif ne prouverait rien" % (natif,))
    o = r["offline"]
    assert o["forcas_tertiary"] is None, "une relique est montee dans le TEMOIN : %r" % (
        o["forcas_tertiary"],)
    assert not o["has_extra_dmg"] and not o["has_extra_block"], (
        "le PORT materialise les effets SANS relique : %r" % (o,))


def test_le_gate_de_trait_refuse_une_cible_sans_vehicle_ni_bigtarget(cas):
    """`ForAddition( get_OwnerIsCaster & (HasTrait(Target, Vehicle) | HasTrait(Target, BigTarget)),
    ConfigVar(extraDmg) )` -- les DEUX disjoints PASSENT, le hors-groupe REFUSE.

    `eldarRanger` ne porte ni l'un ni l'autre (traits LUS dans la capture, pas supposes)."""
    o = cas(True)["offline"]
    assert "Vehicle" in o["traits"]["vehicle"], o["traits"]["vehicle"]
    assert "BigTarget" in o["traits"]["bigtarget"], o["traits"]["bigtarget"]
    assert not ({"Vehicle", "BigTarget"} & set(o["traits"]["neutre"])), o["traits"]["neutre"]
    b = o["bonus"]
    assert b["vehicle"] == {"kind": "Addition", "value": EXTRA_DMG_L3}, b["vehicle"]
    assert b["bigtarget"] == {"kind": "Addition", "value": EXTRA_DMG_L3}, b["bigtarget"]
    assert b["neutre"] is None, "le bonus s'applique a une cible hors groupe : %r" % (b["neutre"],)


def test_aucun_gate_de_nature_dattaque(cas):
    """CONTRE-EPREUVE du voisin de forme : `BeastSlayer_ExtraDmgEffect` porte la MEME paire de
    traits cible mais AUSSI un `IsMeleeAttack`, et rend un `ForPercentIncrease`.

    Le `CreateDamageModifier` de 1539 n'a AUCUN autre noeud que `get_OwnerIsCaster` et le
    `op_BitwiseOr` de traits -> le bonus vaut aussi en RANGED et sur une attaque d'ABILITY, et il
    est ADDITIF. Recopier le voisin aurait eteint deux regimes et change le canal."""
    b = cas(True)["offline"]["bonus"]
    assert b["vehicle_ranged"] == {"kind": "Addition", "value": EXTRA_DMG_L3}, b["vehicle_ranged"]
    assert b["vehicle_ability"] == {"kind": "Addition", "value": EXTRA_DMG_L3}, b["vehicle_ability"]


def test_les_magnitudes_sont_celles_du_palier_tertiaire_pas_du_palier_clampe(cas):
    """LE CRAN DU DESSOUS (#1005/#1007/#1009) -- et il a MORDU dans cette tranche meme.

    Un owner-effect de relique CAPTE LIVE arrivait avec le couple des PASSIFS (`level 50`), donc au
    dernier palier apres clamp : `extraDmg` lu **728** au lieu de **543** et `blockDmg` lu **2184**
    au lieu de **1629**. Les deux valeurs FAUSSES sont assertees en negatif : sans ca, un test qui
    ne verifierait que << le bonus existe >> resterait vert sur le rail casse."""
    o = cas(True)["offline"]
    assert o["forcas_passive_level"] == 50, (
        "le porteur n'est pas au palier passif clampe -- ce test ne discrimine plus : %r"
        % (o["forcas_passive_level"],))
    assert EXTRA_DMG_L3 != EXTRA_DMG_CLAMP and BLOCK_DMG_L3 != BLOCK_DMG_CLAMP, (
        "les deux paliers COINCIDENT : le montage ne discrimine rien")
    assert o["bonus"]["vehicle"]["value"] == EXTRA_DMG_L3, (
        "extraDmg lu %r (palier clampe = %r) -- le couple TERTIAIRE n'atteint pas l'effet"
        % (o["bonus"]["vehicle"]["value"], EXTRA_DMG_CLAMP))
    bs = o["block_source"]
    assert bs is not None and bs["amount"] == BLOCK_DMG_L3, (
        "blockDmg lu %r (palier clampe = %r)" % (bs and bs["amount"], BLOCK_DMG_CLAMP))
    # `blockChance` est CONSTANTE (10) sur les dix paliers du gameconfig : elle ne peut pas
    # discriminer un niveau, et c'est dit plutot que masque.
    assert bs["chance"] == 10, bs["chance"]
    assert bs["block_id"] == 1540, (
        "le `BlockChanceInfo.entityId` doit etre l'EFFET, pas la chance : %r" % (bs["block_id"],))


def test_le_degat_de_forcas_est_bit_exact(cas):
    """COEUR de la face DEGAT : l'attaque de Forcas contre le `Vehicle`, rejouee RNG-seedee, rend
    les MEMES per-hit et les MEMES PV que le natif.

    C'est CE test qui a rougi tant que le rail de niveau etait casse : le port lisait +728 au lieu
    de +543 et rendait `[3196, 920, 944, 829, 1040, 875]` contre `[2974, 772, 734, 860, 747, 863]`
    live. Une assertion sur la seule PRESENCE du bonus ne l'aurait pas vu."""
    c = cas(True)["msc"]
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice extra-dmg)")
    assert c["off_ph"] == c["live_ph"], (
        "per-hit offline != live : off=%r live=%r" % (c["off_ph"], c["live_ph"]))
    assert c["off_after"] == c["live_after"], (
        "PV cible offline %r != live %r" % (c["off_after"], c["live_after"]))


# --------------------------------------------------------------------------------------------
# `RelicPowerFist` (1466) -- le trigger et ses DEUX tirages
# --------------------------------------------------------------------------------------------
def test_relic_power_fist_lit_le_palier_tertiaire(cas):
    """`ConfigVar(chance = 0x3a)` / `ConfigVar(chance_2 = 0x3b)` resolus contre l'`AbilityState`
    TERTIAIRE -- `chance[3] = 36`, PAS `chance[10] = 50` (palier clampe des passifs).

    Les DEUX variables sont lues SEPAREMENT : le gameconfig leur donne aujourd'hui les memes dix
    paliers, mais ce sont deux `AbilityVariableType` distincts et les fusionner casserait au
    prochain equilibrage."""
    o = cas(True)["offline"]
    assert o["baraqiel_tertiary"] == "RelicPowerFist" and o["baraqiel_tertiary_level"] == 3, (
        "%r / %r" % (o["baraqiel_tertiary"], o["baraqiel_tertiary_level"]))
    assert CHANCE_L3 != CHANCE_CLAMP, "les deux paliers COINCIDENT : le montage ne discrimine rien"
    assert list(o["rpf_vars"]) == [CHANCE_L3, CHANCE_L3], (
        "(chance, chance_2) lus %r (palier clampe = %r)" % (o["rpf_vars"], CHANCE_CLAMP))


def test_le_natif_pose_pinned_et_le_port_pose_le_meme(cas):
    """POSITIF de la face TRIGGER : au seed `4242`, le premier `Maybe` PASSE -> le natif pose
    `Pinned` (1065) sur la cible, et le port rejoue EXACTEMENT le meme ensemble.

    L'ensemble est compare TYPE PAR TYPE, restreint a {`Pinned`, `Stunned`} : les autres effets de
    la cible bougent pour des raisons qui ne regardent pas ce port (mesure : `RangedSpecialist`
    s'eteint quand l'attaquant devient adjacent)."""
    c = cas(True)["rpf"]
    assert c["rpf_natif"], (
        "aucun `Pinned`/`Stunned` pose par le NATIF au seed %s -- le bras POSITIF est VIDE "
        "(les deux tirages sont tombes a faux ; ce n'est pas une faute du port, mais ce test-ci "
        "ne prouve alors plus rien : changer de seed)" % SEED)
    assert c["rpf_port"] == c["rpf_natif"], (
        "effets poses par le PORT %r != NATIF %r" % (c["rpf_port"], c["rpf_natif"]))


def test_sans_la_relique_aucun_pinned_ni_stunned(cas):
    """TEMOIN de la face TRIGGER : MEME attaque, MEME seed, SANS relique -> ni `Pinned` ni
    `Stunned`, des DEUX cotes. Sans lui, le `Pinned` du bras positif pourrait venir d'ailleurs
    (`CrushingStrike` de Baraqiel, ou un effet de la cible)."""
    c = cas(False)["rpf"]
    assert c["rpf_natif"] == [], "le NATIF pose %r SANS relique" % (c["rpf_natif"],)
    assert c["rpf_port"] == [], "le PORT pose %r SANS relique" % (c["rpf_port"],)


def test_les_deux_maybe_consomment_deux_tirages(cas):
    """LE POINT LE PLUS DUR, et il est INVISIBLE des degats : `Maybe(Pinned) & Maybe(Stunned)`
    consomme DEUX `next_bool`, que les tirages passent ou non.

    On le mesure par l'ETAT DU MT19937 apres l'attaque, des deux cotes (`dumpRng.mti` contre
    `state.rng.mti`, plus l'egalite du buffer entier). Mesure #1009 : tant que le trigger ne firait
    pas, le port s'arretait a `mti = 14` la ou le natif etait a `16` -- alors que TOUS les per-hit
    et les PV concordaient deja."""
    c = cas(True)["rpf"]
    assert c["off_ph"] == c["live_ph"], (
        "per-hit offline != live : off=%r live=%r" % (c["off_ph"], c["live_ph"]))
    assert c["off_after"] == c["live_after"], (
        "PV cible offline %r != live %r" % (c["off_after"], c["live_after"]))
    assert c["mti_apres_port"] == c["mti_apres_natif"], (
        "le port a consomme un NOMBRE DIFFERENT de tirages : mti port=%r natif=%r "
        "(les deux `Maybe` de RelicPowerFist tirent meme quand ils echouent)"
        % (c["mti_apres_port"], c["mti_apres_natif"]))
    assert c["mt_egal"], "le buffer MT19937 diverge apres l'attaque"


def test_le_temoin_est_lui_aussi_bit_exact(cas):
    """Le bras TEMOIN doit CONCORDER lui aussi -- sinon le test positif ne prouverait pas que c'est
    la RELIQUE qui explique l'ecart, seulement que le port et le natif divergent moins avec elle.

    Il garde en particulier que le port ne consomme AUCUN tirage quand la relique est absente (le
    registre est indexe par NOM d'ability : sans `tertiary_ability`, rien ne doit s'inscrire)."""
    for cle in ("msc", "rpf"):
        c = cas(False)[cle]
        assert c["off_ph"] == c["live_ph"], (
            "%s : per-hit offline %r != live %r" % (cle, c["off_ph"], c["live_ph"]))
        assert c["off_after"] == c["live_after"], (
            "%s : PV offline %r != live %r" % (cle, c["off_after"], c["live_after"]))
        assert c["mti_apres_port"] == c["mti_apres_natif"], (
            "%s : mti port=%r natif=%r" % (cle, c["mti_apres_port"], c["mti_apres_natif"]))
