"""#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4 -- les CLAMPS DE MELEE sur une portee `None`, CONFRONTES.

Le port fait, dans les DEUX clamps de `IdunBattle.Core.Services.TargetingQuery$$GetRange` :

    value = None if value is None else min(1, value)
    only_adjacent = True

L'argument qui rendait ce `None` inoffensif etait une LECTURE (les deux `Math.Min(1, v)` cohabitent
avec `onlyAdjacent = 1`, et le consommateur teste `range._4_1_` en premier). Ces crans la
CONFRONTENT -- bras `ForceMeleeTarget`, ouvert en POSANT le trait `Ranged` sur un caster sans arme
(seul moyen de dissocier les deux termes d'`UnitExtensions$$IsRanged`).

Ce que chaque cran garde :

  1. **B3 EST INDISTINGUABLE, ET C'EST MESURE.** « le clamp pose `value = 1` » rend le MEME
     `TargetingRule` que `None` sur le seul consommateur porte -- 0 ecart, sur un balayage qui
     DISCRIMINE ailleurs (contre-cran : hors `only_adjacent`, la valeur EST lue et les deux
     diffèrent). Sans le contre-cran, l'egalite serait triviale.
  2. **LE BRAS `ForcedInMelee` EST VIDE DANS LA POPULATION**, et ce cran chiffre l'impossibilite
     plutot que de la raconter. S'il rougit, un porteur est apparu -> il faut CONFRONTER.
  3. **LE MONTAGE A MORDU DES DEUX COTES** : le trait est publie par le NATIF
     (`combatSnapshot.units[].traits`, obtenu en invoquant `UnitExtensions$$HasTrait`) ET vu par le
     PORT. Un montage rate est un ECHEC, jamais un skip vert.
  4. **D1 -- LE CLAMP ARME `only_adjacent` MALGRE UNE VALEUR INCONNUE.** Accord TOTAL avec le natif
     sur le CODE, et la baseline B2 (« le clamp abandonne sur `None` ») DIVERGE : sans ce second
     terme l'accord serait degenere.
  5. **D2 -- LA VALEUR CLAMPEE N'EST PAS CONSOMMEE, et c'est PROUVE, pas lu.** La sonde etablit
     `GetStat(caster, StatType.Range = 2) == 0` ; le clamp poserait donc `min(1, 0) = 0`, valeur
     avec laquelle la branche DISTANCE refuserait TOUTE cible (`d >= 1 > 0`). Or le natif ACCEPTE
     le volet portee a `d = 1`. C'est la branche `OnlyAdjacent` qui a repondu.
     ⚠ Ce cran n'a de sens que si la sonde rend 0 : avec `Value >= 1` les deux branches coincident.
     Le probe le dit lui-meme (`d2_probant`) et rougit alors au lieu de compter l'accord.
  6. **AUCUNE PERTE** contre B2 : le clamp n'ajoute pas de refus que le natif n'a pas.
  7. **LE TEMOIN NON CLAMPE NOMME LE RESIDU** au lieu de le taire : la divergence de CODE y est
     celle, CONNUE, du tri-etat (#419-r1-tr14-r5-r2-r1-r2-r1-r1) -- pas une regression de cette
     tranche -- et le VERDICT y reste identique.

RE et mesures : `docs/rl/case-419-r1-tr14-r5-r2-r1-r2-r1-r1-only-adjacent-portee-non-observable.md`.
Probe jumeau : `probe_419r1tr14r5r2r1r2r1r1r4_melee_clamp_live.py`. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r2r1r1r4_melee_clamp_live as P
from engine.runner.abilities.targeting_rule import TargetingRule as TR

IN_RANGE = int(TR.TargetIsInRange)
DYNAMIC = int(TR.TargetMatchesDynamicRule)


@pytest.fixture(scope="module")
def mesure(rpc):
    """Les DEUX bras (clamp + sonde `GetStat(Range)`). Un montage rate est un ECHEC."""
    from rl_collect_batch import _resolve_session
    sid = _resolve_session()
    try:
        res = P.run(sid)
        res.update(P.run_sonde(sid))
        return res
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


# ------------------------------------------------------------------------------- crans OFFLINE

def test_b3_est_indistinguable_et_le_balayage_discrimine():
    """(1) `Range(None, True)` == `Range(1, True)` sur le seul consommateur porte -- et le balayage
    n'est pas degenere : plusieurs codes rendus, et des ecarts HORS `only_adjacent`."""
    b3 = P.b3_indistinguable(verbose=False)
    assert b3["verifies"] > 100, "echantillon trop maigre"
    assert len(b3["codes"]) >= 2, (
        f"un seul code rendu sous `only_adjacent` ({b3['codes']}) -- l'egalite ne prouve rien")
    assert b3["ecarts_hors_adj"] > 0, (
        "hors `only_adjacent` la valeur EST lue : les deux `Range` devaient differer")
    assert b3["ecarts"] == [], (
        f"B3 n'est plus indistinguable ({b3['ecarts'][:3]}) : le choix `None` vs `1` est devenu "
        "OBSERVABLE -> il doit etre CONFRONTE, plus raisonne")


def test_le_bras_forced_in_melee_est_vide_dans_la_population():
    """(2) Le bras (b) reste NON CONFRONTE parce que son regime est VIDE : aucune unite SANS ARME
    n'est `BloodAngels`, or le seul poseur LU
    (`TheQuickeningAbility$$GetTriggerAttackBehaviour`) est gate par `HasFaction(unit, 0xe)`."""
    imp = P.impossibilite_du_bras_forced_in_melee(verbose=False)
    assert imp["sans_arme"] > 0, "aucune unite sans arme -- substrat suspect"
    assert imp["sans_arme_bloodangels"] == [], (
        f"{imp['sans_arme_bloodangels']} porte(nt) desormais le regime (b) : il devient "
        "CONFRONTABLE et doit l'etre")


# --------------------------------------------------------------------------------- crans LIVE

def test_le_montage_a_mordu(mesure):
    """(3) Un caster CLAMPE, des temoins, et la sonde -- sinon rien n'est mesure."""
    assert mesure["clampes"], "aucun caster sous clamp de melee"
    assert mesure["temoins"], "aucun temoin non clampe"
    assert mesure["sonde"], "aucune ligne de sonde"
    lignes = [r for c in mesure["clampes"] for r in c["rows"]]
    assert any(r["d"] == 1 for r in lignes), "aucune cible a d = 1 sur le caster clampe (D2)"
    assert any(r["d"] >= 2 for r in lignes), "aucune cible a d >= 2 sur le caster clampe (D1)"


def test_d1_le_clamp_arme_only_adjacent_sur_une_valeur_inconnue(mesure):
    """(4) Le natif refuse `TargetIsInRange` a d >= 2 alors que la portee numerique lui est fournie
    par `GetStat(Range) = 0` : c'est le clamp qui a arme le gate. Le port dit la meme chose ; B2
    (« le clamp abandonne ») ne dit pas la meme chose -- donc le regime n'est pas degenere."""
    t = P.tally(mesure)
    assert t["port"] == t["tot"], (
        f"{t['tot'] - t['port']} ligne(s) ou le port et le natif divergent SUR LE CODE")
    assert t["v_port"] == t["tot"], (
        f"{t['tot'] - t['v_port']} ligne(s) ou ils divergent SUR LE VERDICT")
    assert t["gain_b2"] >= 1, (
        "REGIME DEGENERE : B2 nomme la MEME regle partout -- l'accord ne prouve rien")
    loin = [r for c in mesure["clampes"] for r in c["rows"] if r["d"] >= 2 and r["nat"] is not None]
    assert loin, "aucune ligne a d >= 2"
    for r in loin:
        assert r["nat"] == IN_RANGE, (
            f"u{r['tid']} d={r['d']} : le natif devait rompre TargetIsInRange, "
            f"trouve {hex(r['nat'])}")
        assert r["port"] == IN_RANGE
        assert r["b2"] != IN_RANGE, (
            f"u{r['tid']} d={r['d']} : B2 devait NE PAS armer le gate -- sinon le clamp n'est pas "
            "ce qui l'arme")


def test_d2_la_valeur_clampee_nest_pas_consommee(mesure):
    """(5) LE CRAN CENTRAL DE LA TRANCHE. La sonde (`1126`, `forceMeleeTarget = False`, masque
    `0x4000`) mesure `GetStat(Range) == 0` ; le clamp poserait `min(1, 0) = 0`, et la branche
    DISTANCE refuserait alors TOUTE cible. Le natif ACCEPTE pourtant le volet portee a `d = 1`."""
    valeur, borne, source = P.get_stat_range_mesure(mesure)
    assert valeur == 0, (
        f"`GetStat(Range)` mesure = {valeur} ({source}) : avec une valeur >= 1 le cran est "
        "DEGENERE (gate d'adjacence et branche distance coincident)")
    assert borne is None or borne >= 0
    probant, ok, detail = P.d2_probant(mesure, valeur)
    assert probant, f"D2 NON PROBANT : {detail}"
    assert ok, f"D2 REFUTE : {detail} -- propager `None` a travers le clamp serait FAUX"


def test_aucune_perte_contre_la_baseline(mesure):
    """(6) Le sens INVERSE : le clamp ne doit ajouter aucun refus que le natif n'a pas."""
    t = P.tally(mesure)
    assert t["perte_b2"] == 0, f"{t['perte_b2']} ligne(s) dont la cause etait juste et ne l'est plus"
    assert t["v_perte"] == 0, f"{t['v_perte']} cible(s) que le natif accepte et que le port REFUSE"


def test_le_temoin_non_clampe_nomme_le_residu(mesure):
    """(7) Sur un caster NON clampe, `only_adjacent` est faux (trait `Ranged`) et le port n'a plus
    de portee numerique : il ne pose AUCUN refus de distance la ou le natif rend `TargetIsInRange`
    (`Value = 0`). Divergence de CODE CONNUE -- le prix du tri-etat -- avec un VERDICT identique,
    puisque la regle dynamique refuse de toute facon un caster sans arme. Ce cran l'ATTESTE : s'il
    rougit, l'ecart a change de nature et doit etre re-instruit."""
    rows = [r for t in mesure["temoins"] for r in t["rows"] if r["nat"] is not None]
    assert rows, "aucune ligne de temoin"
    for r in rows:
        assert r["nat"] == IN_RANGE, (
            f"temoin u{r['tid']} d={r['d']} : le natif devait rompre TargetIsInRange "
            f"(`Value = 0`), trouve {hex(r['nat'])}")
        assert r["port"] == DYNAMIC, (
            f"temoin u{r['tid']} d={r['d']} : le port devait imputer le refus a la regle DYNAMIQUE "
            f"(portee non observable -> aucun gate de distance), trouve {hex(r['port'])}")
        assert bool(r["port"]) == bool(r["nat"]), "le VERDICT, lui, doit rester identique"


def test_la_sonde_chiffre_lecart_permissif_du_tri_etat(mesure):
    """(7bis) La SONDE est le seul regime ou l'ecart du tri-etat devient un ecart de VERDICT : sur
    `1126` (masque `0x4000`, sans regle dynamique pour rattraper), le natif REFUSE tout et le port
    ACCEPTE tout. C'est un ARTEFACT du montage -- il faut le trait `Ranged`, que ZERO unite porte,
    pour rendre `only_adjacent` faux sur un caster sans arme -- et ce cran fige le chiffre pour que
    personne ne le relise comme un gisement reel."""
    rows = [r for r in mesure["sonde"] if r["nat"] is not None]
    assert rows, "aucune ligne de sonde"
    assert all(r["nat"] == IN_RANGE for r in rows), (
        "la sonde doit refuser TOUTES ses cibles (`Value = 0`, masque sans regle dynamique)")
    assert all(r["port"] == 0 for r in rows), (
        "le port doit toutes les ACCEPTER -- c'est l'ecart permissif du tri-etat, chiffre ici")
