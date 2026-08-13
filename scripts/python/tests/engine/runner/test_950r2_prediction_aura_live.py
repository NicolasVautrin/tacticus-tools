"""#950-r2 / #953-r1 -- la face PREDICTION des passifs-AURA, confrontee a l'oracle NATIF.

CE QUE CE FICHIER GARDE
-----------------------
#950 et #953/#954 ont porte leurs passifs SYMETRIQUEMENT dans les deux facades -- COMBAT
(`runner/damage_model.py`, `runner/operations/damage.py`) et PREDICTION
(`playbook/prediction/_shared.py`, `normal_attack.py`) -- mais leurs probes ne mesuraient que le
COMBAT. Un fork prediction/combat y serait SILENCIEUX : l'IA n'ajusterait pas ses candidats, rien
ne leverait, aucun test ne rougirait.

**IL Y EN AVAIT UN, ET IL EST MESURE ICI.** Sur le carre `aura`/`away` de #950 (Jain Zar adjacente
a l'attaquant, tout le reste egal), la tuile candidate d'ou l'attaquant est adjacent au porteur
donnait, AVANT correctif :

    oracle natif (0, 1) = (2045, 5055)      port = (6030, 9040)      ecart = +3985 sur les DEUX bornes

Les quatre autres tuiles candidates concordaient a l'unite, et le bras temoin `tl_away` (porteur a
distance 3) concordait sur ses six tuiles. L'ecart est donc EXACTEMENT la reduction plate du canal
`TerrorsLament_DamageReduction` (`ForSubtraction(ConfigVar(0x12 = dmgReduction))`), non appliquee
par la face PREDICTION : `5 coups x 797 = 3985`. Le port appliquait bien l'autre moitie du passif
(`TerrorsLament_HitReduction`, 6 coups -> 5 : `7236 x 5/6 = 6030`), ce qui rendait l'ecart d'autant
plus lisible comme un fork de CANAL, pas de gate.

CAUSE : dans `_add_positional_and_defender_mods`, la patte SELF CONSOMMAIT ses reductions plates
(`mods.additive -= sum(def_mods.flat_reductions)`) tandis que la patte AURA les VERSAIT dans
`mods.flat_reductions` -- un bac que le pipeline de PREDICTION ne vide JAMAIS (seuls le combat,
via `AttackDamageOperation._apply_defender_flat_reductions`, et la patte SELF le font). La perte
etait donc silencieuse et n'affectait QUE les auras a reduction PLATE.

L'ORACLE. `decisionView.attackPlans[].evals[].ranked[]` -- les bornes que le natif publie PAR TUILE
CANDIDATE. La recette (non circulaire) est celle de `tests/engine/test_aura_position_live.py`
(#153), extraite dans `prediction_confrontation.py` pour etre partagee.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le foyer du fix : la boucle AURA-defense de la face PREDICTION.
        "scripts/python/engine/playbook/prediction/_shared.py",
        # Le module de confrontation : oracle, filtres et tolerance.
        "scripts/python/prediction_confrontation.py",
        # Le montage (bras, tuiles, unites) dont ce fichier depend entierement.
        "scripts/python/probe_950_terrors_lament_tough_to_kill.py",
        # Les deux effets confrontes -- leur face DEFENSE decide de la valeur attendue.
        "scripts/python/engine/entities/effects/loki/terrors_lament.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "CES chemins parce que le verdict est un ACCORD port <-> natif sur des bornes de "
              "prediction : il depend du pipeline de prediction (le foyer du fix), de la recette "
              "d'oracle, du montage geometrique qui rend le regime discriminant, et des deux "
              "classes d'effet dont la face DEFENSE porte la valeur. `build: False` : rien n'est "
              "lu du binaire ni de `data/symbols/**` -- l'oracle vient du runner LIVE, pas du "
              "dump. `toujours: False` : ces quatre chemins bornent le perimetre.",
}

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)


def _confronter(arm):
    """Monte le bras `arm` de #950, confronte la face PREDICTION, dispose le runner.

    Rend `(lignes, ecartes, contexte)`. Le montage est celui de `probe_950` -- meme carre de
    tuiles, memes unites : on ne re-decrit pas une geometrie deja mesuree et assertionnee la-bas.
    """
    import probe_950_terrors_lament_tough_to_kill as P
    import prediction_confrontation as PC

    rpc = P._mkrpc()
    spec = P.ARMS[arm]
    rid, err = P._build(spec)
    if rid is None:
        pytest.skip("build KO pour le bras %s : %s" % (arm, (err or "")[:200]))
    try:
        dv = P._view(rpc, rid)
        att = P._by_vis(dv, spec.get("att", P.ATT))
        vic = P._by_vis(dv, spec["victim"])
        car = P._by_vis(dv, spec["carrier"])
        if not (att and vic and car):
            pytest.skip("montage incomplet : att=%s vic=%s carrier=%s" % (att, vic, car))
        ab = P._normal_attack_id(dv, att["id"])
        if ab is None:
            pytest.skip("pas d'attaque normale sur l'attaquant")
        ctx = {"att": att["id"], "att_pos": P._pos(dv, att["id"]),
               "vic": vic["id"], "vic_pos": P._pos(dv, vic["id"]),
               "carrier": car["id"], "carrier_pos": P._pos(dv, car["id"]),
               "carrier_effects": P._effect_types(dv, car["id"]), "ability": ab}
        scene, sctx, dec = PC.construire_scene(rpc, rid, dv)
        if scene is None:
            pytest.skip("Scene non constructible (combatSnapshot KO)")
        lignes, ecartes = PC.lignes_de_confrontation(scene, sctx, dec, att["id"], vic["id"], ab)
        return lignes, ecartes, ctx
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                        # noqa: BLE001
            pass


def _exiger_regime(lignes, ctx, arm):
    """Le regime doit etre DISCRIMINANT avant qu'un accord veuille dire quelque chose.

    Trois exigences, toutes mesurees sur l'etat LIVE et non supposees : le porteur porte bien ses
    deux effets, la geometrie est celle du bras, et il existe au moins une ligne. Un accord en
    regime degenere (zero ligne, ou porteur sans effet) ne prouve rien.
    """
    from engine.entities.effect_type import EffectType

    attendus = {int(EffectType.TerrorsLament_DamageReduction),
                int(EffectType.TerrorsLament_HitReduction)}
    manquants = sorted(attendus - set(ctx["carrier_effects"]))
    assert not manquants, (
        "bras %s : le porteur (u%s @%s) ne porte pas %s -- le montage n'exerce PAS le passif, "
        "et tout accord serait obtenu en regime degenere. Effets lus : %s"
        % (arm, ctx["carrier"], ctx["carrier_pos"], manquants, ctx["carrier_effects"]))
    assert lignes, (
        "bras %s : AUCUNE tuile candidate rankee pour u%s -> u%s (ability %s). Sans ligne, "
        "l'accord est vide : c'est un regime degenere, pas une confrontation."
        % (arm, ctx["att"], ctx["vic"], ctx["ability"]))


@pytest.mark.parametrize("arm", ["tl_aura", "tl_away"])
def test_prediction_concorde_avec_l_oracle_natif(arm):
    """ETAGE 1 -- ACCORD. Sur CHAQUE tuile candidate, les bornes du port doivent egaler celles que
    le natif publie, dans le bras AURA comme dans son TEMOIN.

    C'est ce test qui rougissait AVANT le correctif, et seulement sur `tl_aura` : le temoin
    `tl_away` etait deja vert, ce qui localise l'ecart sur la GEOMETRIE du passif et non sur un
    terme de base."""
    import prediction_confrontation as PC

    lignes, ecartes, ctx = _confronter(arm)
    _exiger_regime(lignes, ctx, arm)
    div = PC.divergences(lignes)
    assert not div, (
        "bras %s : la face PREDICTION du port diverge de l'oracle natif sur %d tuile(s) sur %d.\n"
        "%s\ncontexte : attaquant u%s@%s, cible u%s@%s, porteur u%s@%s, ecartees=%s"
        % (arm, len(div), len(lignes), PC.resume(lignes, ecartes),
           ctx["att"], ctx["att_pos"], ctx["vic"], ctx["vic_pos"],
           ctx["carrier"], ctx["carrier_pos"], ecartes))


def test_le_carre_aura_away_est_discriminant():
    """ETAGE 2 -- LE REGIME EST DISCRIMINANT, et c'est assertionne, pas suppose.

    Le bras `tl_aura` doit publier, sur la tuile d'ou l'attaquant est adjacent au porteur, une
    borne STRICTEMENT INFERIEURE a celle du meme couple dans `tl_away`. Sans ce cran, un port qui
    n'appliquerait AUCUN des deux canaux serait vert a l'etage 1 des DEUX cotes -- l'accord se
    ferait sur un passif inerte."""
    lignes_a, _e1, ctx_a = _confronter("tl_aura")
    lignes_w, _e2, ctx_w = _confronter("tl_away")
    _exiger_regime(lignes_a, ctx_a, "tl_aura")
    _exiger_regime(lignes_w, ctx_w, "tl_away")
    tuile = ctx_a["att_pos"]
    oa = next((l["oracle"] for l in lignes_a if l["tile"] == tuile), None)
    ow = next((l["oracle"] for l in lignes_w if l["tile"] == tuile), None)
    assert oa is not None and ow is not None, (
        "la tuile de l'attaquant %s n'est pas rankee dans les deux bras (aura=%s away=%s) -- "
        "le carre n'est pas comparable" % (tuile, oa, ow))
    assert oa[0] < ow[0] and oa[1] < ow[1], (
        "le NATIF ne separe pas les deux bras sur la tuile %s : aura=%s away=%s. Le montage a "
        "cesse d'exercer `TerrorsLament` (porteur deplace, adjacence perdue, attaque devenue "
        "distante) -- repare le montage, ne relache pas ce cran : sans lui, l'etage 1 passerait "
        "sur un passif inerte." % (tuile, oa, ow))
