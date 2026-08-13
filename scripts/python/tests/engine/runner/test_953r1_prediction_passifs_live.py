"""#953-r1 -- la face PREDICTION de `Skullsmasher` et d'`ObsessiveAnnunciation`, contre l'oracle NATIF.

CE QUE CE FICHIER GARDE
-----------------------
#953/#954 ont pose leurs cles de contexte SYMETRIQUEMENT dans les deux facades, mais les huit bras
de leur probe ne mesurent que le COMBAT. Le residu #953-r1 signalait un risque PLUS ELEVE que pour
#950-r2. Il avait raison, et la cause n'etait pas celle qu'il visait.

**LE BUG MESURE.** Sur `worldJakhal` << Macer >> blesse (9 474 / 20 000 PV, soit 52,63 % manquants),
AVANT correctif :

    tuile (1,1)  oracle natif (15342, 20760)   port (10842, 16260)   ecart -4500   [3 coups]
    tuile (2,1)  oracle natif (10227, 13839)   port ( 7227, 10839)   ecart -3000   [2 coups]

soit **1 500 par coup** = `floor(52,63 % / hpPct = 10) = 5 paliers x extraDmg = 300`. Le port
rendait EXACTEMENT la prediction du porteur INTACT : le canal `Skullsmasher_ExtraDamage` etait
entierement MUET en prediction, sur les 5 tuiles candidates.

**LA CAUSE, et ce n'est pas celle que le residu visait.** #953-r1 soupconnait la cle
`adjacent_enemy_ids_of`, resolue par deux substrats differents. Elle n'est pas en cause : les bras
`oa_aura`/`oa_away` d'`ObsessiveAnnunciation` concordaient DEJA a l'unite avant tout correctif
(7364/10316 contre 5903/8855, port == natif des deux cotes). Le fork etait dans le substrat de
`Scene` : `hpmax_by_id` etait STRUCTURELLEMENT VIDE sur la voie PREDICTION-LIVE, parce que
`step_context` ne le produit pas et ne le PEUT pas -- `decisionView.units[]` ne publie aucune cle
de PV max. `scene.hpmax` rendait donc `None` pour TOUTE unite, la cle
`StatAmount(Owner, Health, {Missing, Maximum})` arrivait en `(9474, None)`, et le tri-etat fermait
le gate. Cote offline, `Scene.from_state` le remplissait depuis `HealthComponent.hp_max` : les deux
voies de la MEME classe divergeaient.

C'est pourquoi ce fichier confronte les DEUX passifs : celui qui etait casse et celui qui ne
l'etait pas. Le second est le TEMOIN qui interdit d'attribuer l'ecart a la geometrie.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le foyer du fix : le substrat de PV max sur la voie prediction-live.
        "scripts/python/engine/playbook/scene.py",
        # L'effet dont la magnitude est confrontee.
        "scripts/python/engine/entities/effects/loki/skullsmasher.py",
        # La face PREDICTION qui pose la cle `owner_health`.
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        # Le module de confrontation : oracle, filtres, tolerance.
        "scripts/python/prediction_confrontation.py",
        # Le montage (geometrie, unites, PV du porteur).
        "scripts/python/probe_953_954_skullsmasher_obsessive_annunciation.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "CES chemins parce que le verdict est un ACCORD port <-> natif sur des bornes de "
              "prediction : il depend du substrat qui porte les PV max (le foyer du fix), de la "
              "classe d'effet dont la magnitude est mesuree, du site qui pose la cle de contexte, "
              "de la recette d'oracle, et du montage qui rend le regime discriminant (un porteur "
              "INTACT ne franchit AUCUN palier : la mesure serait vide). `build: False` : "
              "l'oracle vient du runner LIVE, pas du dump.",
}

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)


def _monter_skullsmasher(blesser):
    """Monte le bras `sk_full` (porteur INTACT) ou `sk_hurt` (porteur BLESSE), confronte, dispose.

    Blesser Macer se fait en le faisant frapper par la VICTIME (les deux camps sont pilotables) --
    meme geste que `probe_953_954.run_sk`. Ses PV sont volontairement BAS (`--hp-player`) : a
    400 000 PV un retour de 10 526 ne franchit AUCUN palier et la mesure serait VIDE.
    """
    import probe_953_954_skullsmasher_obsessive_annunciation as P
    import prediction_confrontation as PC

    g = P.geometry(P.BOARD)
    rpc = P._mkrpc()
    rid, err = P._build([P.MACER], [P.VICTIM, P.SACRIFICE],
                        [(P.MACER, g["M"])],
                        [(P.VICTIM, g["V"]), (P.SACRIFICE, g["SAC"])],
                        extra=["--hp-target", "400000", "--hp-player", str(P.MACER_HP)])
    if rid is None:
        pytest.skip("build KO : %s" % (err or "")[:200])
    try:
        dv = P._view(rpc, rid, inactive=True)
        mac, vic = P._by_vis(dv, P.MACER), P._by_vis(dv, P.VICTIM)
        if not (mac and vic):
            pytest.skip("montage incomplet (macer=%s victime=%s)" % (mac, vic))
        mid, tid = mac["id"], vic["id"]
        encaisse = []
        if blesser:
            _r, encaisse = P._attack(rpc, rid, tid, mid, P._normal_attack_id(dv, tid))
            dv = P._view(rpc, rid, inactive=True)
        ab = P._normal_attack_id(dv, mid)
        scene, sctx, dec = PC.construire_scene(rpc, rid, dv)
        if scene is None:
            pytest.skip("Scene non constructible (combatSnapshot KO)")
        lignes, ecartes = PC.lignes_de_confrontation(scene, sctx, dec, mid, tid, ab)
        ctx = {"macer": mid, "victime": tid, "hp": scene.hp(mid), "hpmax": scene.hpmax(mid),
               "encaisse": encaisse, "effets": P._effect_types(dv, mid)}
        return lignes, ecartes, ctx
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                        # noqa: BLE001
            pass


def test_le_substrat_publie_les_pv_max_sur_la_voie_prediction():
    """ETAGE 0 -- LE SUBSTRAT. `scene.hpmax` doit rendre une valeur sur la voie PREDICTION-LIVE.

    C'est l'assertion la plus basse de la chaine, et c'est elle qui rougissait AVANT le correctif :
    `step_context` ne produit pas `hpmax_by_id` et `decisionView.units[]` ne porte aucune cle de PV
    max, donc `scene.hpmax` rendait `None` pour TOUTE unite. Un test qui n'assertionnerait que la
    VALEUR finale ne dirait pas OU la chaine casse."""
    lignes, _ec, ctx = _monter_skullsmasher(blesser=False)
    assert ctx["hpmax"] is not None, (
        "`scene.hpmax(u%s)` rend None sur la voie PREDICTION-LIVE : le substrat de PV max est vide "
        "(`step_context` ne le produit pas, `decisionView.units[]` ne le publie pas). Toute cle "
        "`{Missing, Maximum}` se degrade alors en gate FERME, en silence. hp lu = %s"
        % (ctx["macer"], ctx["hp"]))
    assert ctx["hpmax"] > 0, "PV max non positif (%s) -- substrat present mais absurde" % ctx["hpmax"]
    assert lignes, "aucune tuile candidate rankee : regime degenere, l'etage 0 ne prouve rien seul"


def test_skullsmasher_blesse_concorde_avec_l_oracle_natif():
    """ETAGE 1 -- LA VALEUR, en regime PORTEUR. Le porteur blesse franchit des paliers ; le port
    doit publier les MEMES bornes que le natif sur CHAQUE tuile candidate."""
    import prediction_confrontation as PC

    lignes, ecartes, ctx = _monter_skullsmasher(blesser=True)
    assert lignes, "aucune tuile candidate rankee -- regime degenere"
    assert ctx["encaisse"], (
        "le porteur n'a rien encaisse : le bras BLESSE n'est pas monte, et il mesurerait alors "
        "le meme regime que son temoin (0 palier). Coups lus : %s" % (ctx["encaisse"],))
    assert ctx["hpmax"] and ctx["hp"] < ctx["hpmax"], (
        "PV du porteur %s / %s : aucun PV manquant, donc AUCUN palier -- le bras est un second "
        "temoin deguise" % (ctx["hp"], ctx["hpmax"]))
    div = PC.divergences(lignes)
    assert not div, (
        "la face PREDICTION de `Skullsmasher` diverge de l'oracle natif sur %d tuile(s) sur %d.\n"
        "%s\nporteur u%s a %s/%s PV (encaisse %s), effets %s"
        % (len(div), len(lignes), PC.resume(lignes, ecartes), ctx["macer"], ctx["hp"],
           ctx["hpmax"], ctx["encaisse"], ctx["effets"]))


def test_le_regime_blesse_est_discriminant():
    """ETAGE 2 -- LE REGIME EST DISCRIMINANT, assertionne et non suppose.

    Le NATIF doit publier STRICTEMENT PLUS pour le porteur blesse que pour le porteur intact, sur
    la meme tuile. Sans ce cran, un port qui n'appliquerait JAMAIS le passif serait vert a l'etage
    1 des deux cotes -- c'est exactement l'etat qui precedait le correctif, et il faut qu'un
    montage qui cesse d'exercer le passif ROUGISSE au lieu de rassurer."""
    l_intact, _e1, c_intact = _monter_skullsmasher(blesser=False)
    l_blesse, _e2, c_blesse = _monter_skullsmasher(blesser=True)
    assert l_intact and l_blesse, "un des deux bras n'a aucune ligne -- regime degenere"
    par_tuile = {l["tile"]: l["oracle"] for l in l_intact}
    communes = [(l["tile"], par_tuile[l["tile"]], l["oracle"])
                for l in l_blesse if l["tile"] in par_tuile]
    assert communes, (
        "aucune tuile candidate commune aux deux bras (intact=%s, blesse=%s) -- les deux montages "
        "ne sont pas comparables"
        % (sorted(par_tuile), sorted(l["tile"] for l in l_blesse)))
    plus_haut = [(t, a, b) for t, a, b in communes if b[0] > a[0] and b[1] > a[1]]
    assert plus_haut, (
        "le NATIF ne separe pas le porteur BLESSE (%s/%s PV) du porteur INTACT (%s/%s PV) sur "
        "aucune des %d tuiles communes : %s. Le montage a cesse d'exercer `Skullsmasher` (PV du "
        "porteur trop hauts pour franchir un palier, ou coup de retour trop faible) -- repare le "
        "montage, ne relache pas ce cran."
        % (c_blesse["hp"], c_blesse["hpmax"], c_intact["hp"], c_intact["hpmax"],
           len(communes), communes[:4]))
