"""ForwardObservers (1185) -- face DECISION, confrontee au LIVE.

CE QUE CE TEST GARDE (et pourquoi il ne peut pas passer par accident) :

A. **La ROUTE non-attaque existe et sert.** 1185 n'a pas de `damageProfile` : `_is_attack_ability` la
   rejette, elle n'entre jamais dans `plans`, et `_best_attack` ne la voit pas. Le bras `noroute`
   (registre `NONATTACK_PLAYBOOKS` vide) rejoue la decision dans l'etat d'AVANT le port -- s'il rend
   la MEME chose que le port, c'est que le port est inerte et que l'accord vient d'ailleurs.
B. **Le terme custom est NECESSAIRE** : force a 0, le moteur DIVERGE du natif.
C. **Le terme de Markerlight est BOOLEEN et GLOBAL** : des qu'UN ennemi (n'importe lequel, meme hors
   de portee et non ciblable) porte 0x462, le bonus de 200 disparait et le natif abandonne 1185.
D. **Le terme de PV est PROPORTIONNEL au ratio de la cible, pas booleen ni constant.** Deux mesures
   independantes :
     - la CIBLE choisie change quand une des deux est blessee -- et elle change CONTRE l'ordre
       d'enumeration natif, que suivrait tout terme constant ou booleen ;
     - le bras `A2` place le montage la ou les deux modeles predisent des choix OPPOSES
       (`W_B * pct < pair_max + 1 < W_B`) et laisse le natif trancher.

Le porteur est GREFFE (`tauCrisis.ActiveAbilities = [1185]` dans une COPIE du seed BC) : les deux
seules unites qui portent 1185 sont un SUMMON SANS INVOCATEUR et un npc, tous deux refuses par
`buildNormalizedBC` (`IStatsFormula.StatsUsingProgressionIndexFor` -> `system error`). La greffe est
licite parce que le playbook natif est charge PAR ABILITY (`PlaybookDatabase.LoadPlaybook`) : le code
exerce est bien `ForwardObserversPlaybook`, et le natif le prouve en proposant 1185. Detail complet :
en-tete de `probe_27_4c_forwardobservers_ab.py` et `docs/rl/case-27-custom-utility.md`.

Aucun scalaire de gameplay n'est fige : les poids viennent de la BC re-synthetisee, les encadrements
des `pairUtility` natives du montage.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_4c_forwardobservers_ab as AB                # noqa: E402

FORWARD_OBSERVERS = AB.FORWARD_OBSERVERS
NORMAL = AB.NORMAL
# `--hp-target` du montage : il place l'attaque normale concurrente juste SOUS le terme de PV a
# pct = 1 et juste AU-DESSUS a pct = 0.88 -- c'est ce qui rend le bras A2 discriminant. Valeur
# TROUVEE par balayage live (36.54 < W_B < 41.41), pas ajustee sur le resultat attendu.
HP_TARGET = 47000


@pytest.fixture(scope="module")
def rows():
    rid = AB.build(HP_TARGET)
    try:
        yield AB.run_ab(rid, engine=True)
    finally:
        try:
            AB.L._rpc("disposeRunner", [{"runnerId": rid}])
        except Exception:                                   # noqa: BLE001
            pass


def test_engine_matches_native_on_all_arms(rows):
    """Le moteur reproduit le choix NATIF dans les quatre bras (B0 / B1 / A1 / A2)."""
    for k, row in rows.items():
        assert row["engine"]["on"] == row["native"], (
            "bras %s : moteur %s != natif %s" % (k, row["engine"]["on"], row["native"]))


def test_markerlight_is_a_global_boolean(rows):
    """Le bonus de 200 tombe des qu'UN ennemi porte Markerlight -- meme un ennemi hors de portee,
    non ciblable, et qui n'est meme pas celui vise par le tir (ici le summon intercepteur)."""
    assert rows["B0"]["mk_native"] is False and rows["B0"]["native"][0] == FORWARD_OBSERVERS
    assert rows["A2"]["mk_native"] is True, "aucun Markerlight pose -- le montage n'a pas exerce le terme"
    assert rows["A2"]["native"][0] == NORMAL, (
        "le natif garde 1185 alors qu'un ennemi porte Markerlight -> terme booleen non exerce")
    assert rows["A2"]["engine"]["markerlight"] is True


def test_target_choice_follows_health_ratio(rows):
    """Le terme de PV s'ancre sur la CIBLE et suit son RATIO : blesser la cible choisie fait passer
    le natif sur l'autre -- CONTRE l'ordre d'enumeration, que suivrait un terme constant."""
    ids = rows["B0"]["ids"]
    sain, blesse = ids[AB.TGT_A_VID], ids[AB.TGT_B_VID]
    assert rows["B0"]["native"] == (FORWARD_OBSERVERS, blesse), (
        "bras B0 : la cible de reference n'est pas celle attendue (%r)" % (rows["B0"]["native"],))
    assert rows["B1"]["pct"][blesse] < rows["B1"]["pct"][sain], "la cible n'a pas ete blessee"
    assert rows["B1"]["native"] == (FORWARD_OBSERVERS, sain), (
        "bras B1 : le natif garde la cible blessee -> le terme ne lit pas le ratio de PV")


def test_health_term_is_proportional_not_constant(rows):
    """Bras A2 -- le montage separe les deux modeles : `W_B * pct < pair_max + 1 < W_B`. Le modele
    PROPORTIONNEL predit l'attaque normale, un terme CONSTANT predirait 1185. Le natif tranche."""
    r = rows["A2"]
    pair_max = max(v for v in r["pairs"].values() if v is not None)
    tgts = r["engine"]["targets"] or []
    assert len(tgts) == 1, "A2 doit ne laisser qu'UNE cible eligible (obtenu %r)" % (tgts,)
    pct = r["pct"][tgts[0]]
    from engine import weights as W
    w_b = W.load().sub("ActiveAbilities", "ForwardObservers_TargetHealthPercentage")
    assert w_b * pct < pair_max + 1.0 < w_b, (
        "montage NON discriminant : les deux modeles predisent la meme chose "
        "(pct=%.4f pair_max+1=%.4f W_B=%s)" % (pct, pair_max + 1.0, w_b))
    assert r["native"][0] == NORMAL, "le natif suit le modele CONSTANT -> le port est FAUX"


def test_custom_term_is_necessary(rows):
    """Force a 0, le custom fait DIVERGER le moteur du natif sur les bras ou 1185 est choisie."""
    diverged = [k for k, r in rows.items() if r["engine"]["zero"] != r["engine"]["on"]]
    assert diverged, "custom force a 0 ne change rien -> le terme est inerte"


def test_nonattack_route_is_necessary(rows):
    """Sans la route non-attaque, le moteur ne PEUT PAS proposer 1185 (elle n'est dans aucun `plan`)."""
    picked = [k for k, r in rows.items() if r["engine"]["on"][0] == FORWARD_OBSERVERS]
    assert picked, "aucun bras ne fait choisir 1185 -- le montage ne prouve rien"
    for k in picked:
        assert rows[k]["engine"]["noroute"][0] != FORWARD_OBSERVERS, (
            "bras %s : le moteur propose 1185 SANS la route non-attaque -- une autre voie la fait "
            "passer, la mesure ne prouve rien sur le deblocage" % k)
