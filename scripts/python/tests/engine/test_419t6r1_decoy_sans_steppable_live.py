"""#419-t6-r1 -- le gate de `CosmicHorror` (1277) est `HasTrait(Decoy)` SEUL, MESURE.

CE QUE CE FICHIER FERME. La tranche #419-t6 avait porte le gate fidelement
(`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
teste `UnitExtensions.HasTrait(u, 0x41d)` -- `UnitTrait.Decoy` seul) mais elle ne pouvait pas
l'EPROUVER : les deux seules unites du catalogue qui portent `Decoy` (`genesDecoy` npc,
`genesSmnDecoy` summon) portent AUSSI `Steppable`. Un port qui aurait ajoute `Steppable` au gate
passait toutes ses mesures. C'etait `BLOCAGE: porteur`.

LE PORTEUR SE FABRIQUE, il n'existait simplement pas au catalogue :
`catalog_inject.add_unit_trait(bc, 'genesPatriarch', 'Decoy')` ecrit `BC.Units[].Traits`, que
`buildNormalizedBC` LIT sans jamais l'ECRIRE. Le Patermine ne porte NI `Decoy` NI `Steppable`, donc
l'accorder produit exactement le porteur manquant.

ET C'EST LE CASTER QU'ON EQUIPE, pas un voisin -- lecture, pas commodite : une tuile n'entre dans
les tuiles d'action que si elle est vide ou si son occupant est `Steppable`
(`IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable`), donc un leurre NON `Steppable` pose a
cote serait structurellement hors du movable set et `pairUtility` refuserait la tuile. La tuile
COURANTE du caster, elle, est toujours acceptee : c'est la tuile `C` de #419-t6, celle qui y rend 0
parce que son occupant est ami mais PAS leurre. `IsFriend(u, case.Caster, state)` avec `u == caster`
passe trivialement -- `IdunBattle.Entities.UnitExtensions$$IsFriend` compare
`GetCurrentPlayer(x).<+0x20>.<+0x24>` des deux cotes, sans aucune exclusion de l'identite.

CE QUI EST GARDE -- cinq choses :

  1. LE PORTEUR EST BIEN CELUI QU'ON VEUT : `Decoy` PRESENT et `Steppable` ABSENT, lus au canal
     `combatSnapshot.units[].traits` (l'invocation native de `HasTrait` par valeur d'enum), source
     INDEPENDANTE du substrat que consomme le port. S'il portait les deux, le montage retomberait
     dans le regime que #419-t6 ne separait pas -- le probe LEVE dans ce cas.
  2. LE NATIF LUI-MEME rend le poids de plus : comparaison INTER-BRAS sur la MEME tuile, la MEME
     geometrie, la MEME cible ; le seul ecart entre les deux runners est le trait accorde.
  3. CONFORMITE EN NIVEAU : `port == natif` sur les deux tuiles des deux bras (cette paire ne porte
     aucun residu).
  4. NON-DEGENERESCENCE : la tuile `F` (libre, voisine de la meme cible) rend 0 dans les DEUX bras
     -- sans elle, un port qui verserait le poids partout passerait (2) et (3).
  5. LES DEUX CONTRE-EPREUVES MORDENT, ET DANS DES BRAS DIFFERENTS : `steppable_too` (le port que
     #419-t6 ne pouvait pas ecarter) diverge de 10 sur `C` dans le bras AVEC ; `no_trait` diverge
     de 10 sur `C` dans le bras SANS. Aucune des deux ne mord dans l'autre bras -- elles ne sont
     donc pas colineaires, et le montage exerce bien DEUX faits distincts.

Le critere des mutants est le DEPLACEMENT par rapport au port NON MUTE, jamais l'ecart au natif.

ASCII only. Probe jumeau : `scripts/python/probe_419t6r1_decoy_sans_steppable.py`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import probe_419t6r1_decoy_sans_steppable as P

EPS = P.EPS
_LOGS = Path(__file__).resolve().parents[3] / "logs"


def _case(live_session, rpc, build_runner, bras: str):
    try:
        _LOGS.mkdir(parents=True, exist_ok=True)
        bc = P.seed_bc_for(bras, str(_LOGS / f"419t6r1-{bras}-seed-bc.json"))
        rid = build_runner(P.SEED, P.build_args(bras, bc))["rid"]
        return P.build_case(live_session, rpc, rid, bras)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def cas_avec(live_session, rpc, build_runner):
    """Le caster porte `Decoy` (accorde), et PAS `Steppable`."""
    return _case(live_session, rpc, build_runner, "avec")


@pytest.fixture(scope="module")
def cas_sans(live_session, rpc, build_runner):
    """CONTRE-BRAS EXTERNE : meme montage, seed BC PARTAGE, aucun trait accorde."""
    return _case(live_session, rpc, build_runner, "sans")


@pytest.fixture(scope="module")
def rows_avec(cas_avec, rpc):
    try:
        return P.measure(rpc, cas_avec)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def rows_sans(cas_sans, rpc):
    try:
        return P.measure(rpc, cas_sans)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def mutants(rows_avec, rows_sans, cas_avec, cas_sans, rpc):
    try:
        return {b: {m: P.measure_mutant(rpc, c, m)
                    for m in ("steppable_too", "no_trait")}
                for b, c in (("avec", cas_avec), ("sans", cas_sans))}
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def _row(rows, key):
    return next(r for r in rows if r["tile_key"] == key)


def test_le_porteur_fabrique_est_decoy_SANS_steppable(cas_avec, cas_sans):
    """(1) Le fait meme que #419-t6 n'avait pas : un porteur `Decoy` qui n'est PAS `Steppable`.

    Lu au canal ECS. Le bras `sans` atteste le contre-etat -- sans lui, un montage qui poserait le
    trait dans les DEUX bras rendrait le meme resultat partout, et l'accord serait degenere.
    """
    a, s = cas_avec["traits"], cas_sans["traits"]
    assert a["decoy"] is True and a["steppable"] is False, a
    assert s["decoy"] is False and s["steppable"] is False, s
    # Le trait `Decoy` du build, QUALIFIE : a id egal, `TriggeredAbilityType` 1053 =
    # `BroodProgenitor`, `ActiveAbilityType` 1053 = `DevoutPush`. C'est bien l'enum des TRAITS.
    assert P.DECOY_TRAIT_ID in a["trait_ids"] and P.DECOY_TRAIT_ID not in s["trait_ids"]
    assert P.STEPPABLE_TRAIT_ID not in a["trait_ids"]


def test_le_NATIF_rend_le_poids_de_plus_quand_le_caster_est_un_leurre(rows_avec, rows_sans):
    """(2) La mesure qui FERME le residu, et elle est INTER-BRAS : meme tuile, meme geometrie,
    meme cible, meme ability -- seul le trait change, et le NATIF bouge exactement du poids BC."""
    a, s = _row(rows_avec, "C"), _row(rows_sans, "C")
    assert a["tile"] == s["tile"], (a["tile"], s["tile"])
    poids = a["weight"]
    assert poids > 0, "poids BC nul -- le terme serait inerte et la mesure ne trancherait rien"
    assert abs((a["native"] - s["native"]) - poids) <= EPS, (
        "le natif ne rend pas le poids de plus : avec=%.6f sans=%.6f poids=%.6f"
        % (a["native"], s["native"], poids))


def test_le_port_est_conforme_au_natif_en_NIVEAU(rows_avec, rows_sans):
    """(3) `port == natif` sur les deux tuiles des DEUX bras. Cette paire ne porte aucun residu :
    le niveau est assertable, c'est la garde la plus forte."""
    for rows in (rows_avec, rows_sans):
        for r in rows:
            assert abs(r["native"] - r["port"]) <= EPS, (
                "bras %s tuile %s%s : natif=%.6f port=%.6f"
                % (r["bras"], r["tile_key"], r["tile"], r["native"], r["port"]))


def test_le_terme_vaut_le_poids_sur_C_et_ZERO_sur_F(rows_avec, rows_sans):
    """(4) NON-DEGENERESCENCE. Le terme est isole en RETIRANT 1277 du registre -- un port qui
    verserait un terme plat passerait (3) et tomberait ici. `F` (libre, voisine de la MEME cible)
    doit rendre 0 dans les deux bras."""
    for rows in (rows_avec, rows_sans):
        for r in rows:
            terme = r["port"] - r["port_muted"]
            assert abs(terme - r["expected"]) <= EPS, (
                "bras %s tuile %s%s : terme=%+.6f attendu=%+.6f"
                % (r["bras"], r["tile_key"], r["tile"], terme, r["expected"]))
    assert abs(_row(rows_avec, "C")["expected"] - _row(rows_avec, "C")["weight"]) <= EPS
    assert _row(rows_avec, "F")["expected"] == 0.0
    assert _row(rows_sans, "C")["expected"] == 0.0


def test_le_mutant_QUI_AJOUTE_steppable_DIVERGE(mutants, rows_avec):
    """(5a) LE mutant du residu : `Decoy && Steppable`, exactement le port que #419-t6 ne pouvait
    pas ecarter. Il perd le poids sur `C` dans le bras AVEC -- donc il DIVERGE du natif de 10."""
    rows = mutants["avec"]["steppable_too"]
    c = next(r for r in rows if r["tile_key"] == "C")
    poids = _row(rows_avec, "C")["weight"]
    assert abs((c["port_ref"] - c["port"]) - poids) <= EPS, (
        "le mutant `Decoy && Steppable` ne perd PAS le poids : port_mute=%.6f port_ref=%.6f"
        % (c["port"], c["port_ref"]))
    assert abs(c["port"] - _row(rows_avec, "C")["native"]) > EPS, (
        "le mutant reste conforme au natif -- le montage ne l'ecarte pas")
    f = next(r for r in rows if r["tile_key"] == "F")
    assert abs(f["port"] - f["port_ref"]) <= EPS, "le mutant a bouge la tuile TEMOIN"


def test_le_mutant_SANS_gate_de_trait_DIVERGE_dans_l_autre_bras(mutants, rows_sans):
    """(5b) Le pendant : gate `HasTrait` retire -> le poids est verse a tort dans le bras SANS.
    Il mord donc dans l'AUTRE bras que `steppable_too` : les deux contre-epreuves ne sont pas
    colineaires, et le montage exerce bien deux faits distincts."""
    rows = mutants["sans"]["no_trait"]
    c = next(r for r in rows if r["tile_key"] == "C")
    poids = _row(rows_sans, "C")["weight"]
    assert abs((c["port"] - c["port_ref"]) - poids) <= EPS, (
        "le mutant sans gate de trait ne GAGNE pas le poids : port_mute=%.6f port_ref=%.6f"
        % (c["port"], c["port_ref"]))
    assert abs(c["port"] - _row(rows_sans, "C")["native"]) > EPS


def test_chaque_mutant_est_INERTE_dans_le_bras_ou_il_ne_doit_pas_mordre(mutants):
    """La NON-COLINEARITE, assertionnee dans les deux sens -- sans elle, deux mutants qui mordent
    les MEMES lignes ne prouveraient qu'un seul fait."""
    inertes = (("sans", "steppable_too"), ("avec", "no_trait"))
    for bras, m in inertes:
        for r in mutants[bras][m]:
            assert abs(r["port"] - r["port_ref"]) <= EPS, (
                "le mutant %s a bouge dans le bras %s (tuile %s) : %.6f -> %.6f -- le montage ne "
                "separe plus les deux faits" % (m, bras, r["tile_key"], r["port_ref"], r["port"]))
