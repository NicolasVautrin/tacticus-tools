#!/usr/bin/env python3
"""#969-r2 -- l'utilite de `DeathFromAbovePlaybook` EST le nombre de tuiles ou un Inceptor peut
atterrir autour de la cible, et son argmax est keep-first.

CE QUE CE FICHIER GARDE, ET POURQUOI IL EXISTE. Le residu #969-r2 annoncait << le port vise la
MAUVAISE CIBLE : le natif caste `1003` sur `u77`, le port sur `u114` >>. **Re-mesure le
2026-08-14 (`probe_969r2_terme_divergent.py`), l'ecart ne se reproduit pas** : sur TROIS montages
controles du board `MC1_67`, dont DEUX non degeneres a maximum UNIQUE et a argmax DIFFERENT,
l'utilite native (`ncEvaluate`, champ `util` = le compte de la cible gagnante, l'utilite de 1003
ETANT ce compte) et l'argmax du port CONCORDENT. Les valeurs ci-dessous sont ces mesures LIVE,
figees ici pour qu'une regression les fasse rougir sans runner.

RE relue VERBATIM sur `rnca9r7q6c` :

    `IdunBattle.AI.Playbook.Loki.DeathFromAbovePlaybook$$EvaluateNonComparable` :
        bucket = new Bucket(priority: 0, minUtility: <cctor> = 1);
        foreach (e in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile))
            bucket.AddAction(GenerateAction(pos, e.Target,
                                            Fix64(GetNumPossibleSpawnTilesForTarget(e.Target))));

    `...$$GetNumPossibleSpawnTilesForTarget` -> l'arbre que Ghidra nomme
    `...SpawnTermagantsAbility$$u003CExecuteBehaviouru003Eb__1_0` (fusion ICF -- le NOM ment, pas
    la structure) = `CanAddUnit(AdjacentTiles(Entity(target)))`, puis le slot `Count`.

    `Bucket$$AddAction` remplace sur `op_GreaterThan` STRICT -> **keep-first a egalite**.

TROIS MONTAGES, MESURES LIVE (board `MC1_67`, seed 777, caster `ultraInceptorSgt` @(3,4),
cibles `necroDestroyer` u87 @(3,5), `tauCrisis` u89 @(4,4), `necroWarden` u85 @(3,3)) :

    montage   allies places                       comptes u87/u89/u85   util natif   argmax
    A         (2,3) (4,5) (5,5)                   3 / 2 / 4             4            u85
    B         (2,3) (3,2) (2,2)                   4 / 4 / 2             4            u87 (egalite)
    C         (2,3) (3,2) (5,5)                   4 / 3 / 3             4            u87

Le montage B porte une EGALITE en tete (4/4) : il ne discrimine pas l'argmax par l'utilite, il
garde le TIE-BREAK (keep-first sur l'ordre `fromHere`). A et C, eux, ont un maximum UNIQUE et le
portent sur des cibles DIFFERENTES -- c'est ce qui interdit de lire l'accord comme accidentel.

⚠ UN ETAGE RESTE NON PORTE, et il est LU, pas suppose (residu `#969-r4`) :
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` applique, entre le slot `0x42`
d'`IAttackQuery` et la boucle, un `ListExtensions.Remove(targets, predicate)` dont le predicat est
`...BasePlaybook$$u003CGetEligibleTargetsEntitiesu003Eb__58_0` = `t => !this.<slot 0x248>(t)`,
c.-a-d. `Remove` de tout ce dont `ShouldEvaluateTarget` est FAUX. Le corps de base
(`...BasePlaybook$$ShouldEvaluateTarget`) est
`!(IsUnit(t) && CurrentOwnerIsEnvironment(t, state)) && !IsIrrelevantObject(t)`. Le port n'a AUCUN
homologue : `fromHere` est la sortie du slot, SANS ce `Remove`. Il ne mord sur aucun des trois
montages (aucune unite Environment ni IrrelevantObject n'y est en jeu), donc il n'explique pas
l'ecart annonce -- mais c'est une divergence STRUCTURELLE reelle, et elle est permissive.

⚠ NON COUVERT ICI : le regime MULTI-HEX. `dv.units[].feet` est mesure sur les 8 unites des trois
montages et AUCUNE n'a plus d'un pied, donc le mecanisme du residu `#969-r3` (`occupied` derive
des MAIN TILES alors que le natif decide par `TileContentComponent$$IsEmpty`, donc PAR PIED) n'est
ni confirme ni infirme par ces mesures. Le seul porteur multi-hex de la face DECISION est un
SUMMON (`ultraSmnDreadnought`, 3 hexes, cf. `frida/hooks/features/ai-step/projection.ts`).

Offline pur, aucun runner. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.playbook.noncomparable import NCContext                      # noqa: E402
from engine.playbook.noncomparable.death_from_above import (             # noqa: E402
    DeathFromAbovePlaybook,
)

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/noncomparable/death_from_above.py",
                "scripts/python/engine/playbook/noncomparable/_targets.py",
                "scripts/python/engine/battle_query.py"),
    "build": False,
    "toujours": False,
    "raison": "Il garde l'utilite de `DeathFromAbovePlaybook` (= `|CanAddUnit(AdjacentTiles("
              "target))|`), son argmax keep-first et son seuil `MIN_UTILITY`, contre des ANCRES "
              "mesurees live sur trois montages du board MC1_67.",
}

ABILITY = 1003
CASTER = 77
ORIGINE = (3, 4)

#: Voisinage NATIF (`boardGraph.neighbours`) des trois cibles, DERIVE des mesures live : pour
#: chaque cible, l'union de ses voisins libres sur les trois montages plus les tuiles occupees en
#: permanence redonne exactement SIX voisins -- la couronne hex complete.
VOISINS = {
    (3, 5): [(3, 4), (4, 4), (3, 6), (4, 5), (2, 4), (2, 5)],   # u87 necroDestroyer
    (4, 4): [(3, 4), (3, 3), (4, 5), (5, 5), (5, 4), (4, 3)],   # u89 tauCrisis
    (3, 3): [(3, 4), (2, 3), (4, 3), (4, 2), (3, 2), (2, 2)],   # u85 necroWarden
}

#: Toutes les tuiles du voisinage etendu, toutes marchables (le board MC1_67 ne porte ni mur ni
#: eau dans cette zone -- les comptes live le confirment terme a terme).
TUILES = sorted({p for vs in VOISINS.values() for p in vs} | set(VOISINS) | {ORIGINE})

#: ORDRE de `fromHere` MESURE live -- c'est lui que `Bucket$$AddAction` consomme, et le tie-break
#: keep-first en depend. Ne pas le trier.
FROM_HERE = [(87, (3, 5)), (89, (4, 4)), (85, (3, 3))]

#: Les trois montages : {nom: (positions des allies NON caster, comptes attendus par cible)}.
#: Les comptes sont les valeurs MESUREES LIVE, pas des valeurs recalculees.
MONTAGES = {
    "A": {"allies": [(2, 3), (4, 5), (5, 5)], "comptes": {87: 3, 89: 2, 85: 4},
          "argmax": 85, "util_natif": 4, "unique": True},
    "B": {"allies": [(2, 3), (3, 2), (2, 2)], "comptes": {87: 4, 89: 4, 85: 2},
          "argmax": 87, "util_natif": 4, "unique": False},
    "C": {"allies": [(2, 3), (3, 2), (5, 5)], "comptes": {87: 4, 89: 3, 85: 3},
          "argmax": 87, "util_natif": 4, "unique": True},
}

ENNEMIS = [(3, 5), (4, 4), (3, 3), (1, 5)]      # les 3 cibles + `worldJakhal`, hors de portee


def contexte_death_from_above(allies, ennemis=ENNEMIS, from_here=None, walkable=None):
    """FIXTURE REUTILISABLE -- le `NCContext` d'un montage de `DeathFromAbove`.

    `allies` = positions des allies AUTRES que le caster (le caster est a `ORIGINE`, et le natif
    l'occupe comme n'importe qui). `from_here` remplace l'ordre natif des cibles quand un test
    veut exercer le tie-break. `walkable` permet de fermer des tuiles (test du seuil).
    """
    fh = FROM_HERE if from_here is None else from_here
    wk = {p: True for p in TUILES}
    if walkable:
        wk.update(walkable)
    units = [{"id": CASTER, "pos": {"col": ORIGINE[0], "row": ORIGINE[1]}, "ctrl": True,
              "alive": True}]
    for i, p in enumerate(allies):
        units.append({"id": 1000 + i, "pos": {"col": p[0], "row": p[1]}, "ctrl": True,
                      "alive": True})
    for (tid, p) in fh:
        units.append({"id": tid, "pos": {"col": p[0], "row": p[1]}, "ctrl": False,
                      "alive": True})

    def ability_targets(uid, ability_id):
        if uid != CASTER or ability_id != ABILITY:
            return {}
        return {"units": [{"unitId": CASTER, "abilities": [{
            "abilityId": ABILITY,
            "fromHere": [{"kind": "unit", "targetId": tid,
                          "pos": {"col": p[0], "row": p[1]}} for (tid, p) in fh]}]}]}

    return NCContext(
        uid=CASTER, origin=ORIGINE, reach_nc=[ORIGINE], epos=list(ennemis), fpos=list(allies),
        plan={}, hp_cur_by_id={}, ability_targets=ability_targets,
        neigh_by_pos=dict(VOISINS), walkable_by_pos=wk,
        elev_by_pos={p: 0 for p in TUILES}, units=units)


@pytest.fixture(name="playbook")
def _fixture_playbook():
    return DeathFromAbovePlaybook()


# --------------------------------------------------------------------------------------------
# E2 -- le COMPTE par cible, ancre sur les mesures LIVE des trois montages.
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("nom", sorted(MONTAGES))
def test_compte_par_cible_egal_a_la_mesure_live(playbook, nom):
    """`GetNumPossibleSpawnTilesForTarget(target)` = `|CanAddUnit(AdjacentTiles(target))|`.

    Les valeurs attendues sont celles RELEVEES LIVE (`probe_969r2_terme_divergent.py`, board
    `MC1_67`), pas des valeurs recalculees : c'est ce qui rend ce test offline probant."""
    m = MONTAGES[nom]
    ctx = contexte_death_from_above(m["allies"])
    obtenu = {tid: int(playbook._spawn_tiles(ctx, p)) for (tid, p) in FROM_HERE}
    assert obtenu == m["comptes"], (
        "montage %s : comptes de tuiles d'atterrissage %r, mesure live %r"
        % (nom, obtenu, m["comptes"]))
    # temoin NON NUL : un montage dont tous les comptes seraient 0 validerait tout
    assert any(v > 0 for v in obtenu.values()), "montage %s DEGENERE : tous les comptes a 0" % nom


@pytest.mark.parametrize("nom", sorted(MONTAGES))
def test_utilite_emise_egale_l_utilite_native(playbook, nom):
    """L'utilite que le port EMET (`pred`) est le compte de la cible retenue, et elle egale le
    champ `util` d'`ncEvaluate` -- la grandeur que le natif a mise dans le bucket."""
    m = MONTAGES[nom]
    ctx = contexte_death_from_above(m["allies"])
    cands = playbook.generate_candidates(ctx)
    assert cands, "montage %s : aucun candidat alors que le natif en a un (util=%s)" % (
        nom, m["util_natif"])
    assert cands[0]["pred"] == float(m["util_natif"]), (
        "montage %s : utilite emise %s, `util` natif mesure %s"
        % (nom, cands[0]["pred"], m["util_natif"]))


@pytest.mark.parametrize("nom", ["A", "C"])
def test_argmax_sur_maximum_unique(playbook, nom):
    """LE cran du residu, et il n'est PROBANT que sur un maximum UNIQUE : le montage A porte son
    max sur `u85`, le montage C sur `u87`. Deux argmax DIFFERENTS, tous deux concordants avec le
    natif -- un accord sur un seul montage se lirait comme une coincidence."""
    m = MONTAGES[nom]
    assert m["unique"], "montage %s n'a pas de maximum unique : il ne peut pas garder l'argmax" % nom
    ctx = contexte_death_from_above(m["allies"])
    cands = playbook.generate_candidates(ctx)
    assert cands and cands[0]["target"] == m["argmax"], (
        "montage %s : cible retenue %s, cible native %s"
        % (nom, (cands or [{}])[0].get("target"), m["argmax"]))


def test_les_deux_montages_uniques_ne_designent_pas_la_meme_cible():
    """Contre-epreuve du precedent : si A et C designaient la MEME cible, le test ci-dessus
    passerait avec un port qui rendrait toujours cette cible-la."""
    assert MONTAGES["A"]["argmax"] != MONTAGES["C"]["argmax"], (
        "les deux montages a maximum unique designent la meme cible -- ils ne discriminent rien")


def test_tie_break_keep_first_sur_egalite(playbook):
    """Montage B : deux cibles a 4. `Bucket$$AddAction` remplace sur `op_GreaterThan` STRICT, donc
    c'est la PREMIERE de l'ordre `fromHere` qui reste -- ici `u87`."""
    m = MONTAGES["B"]
    ctx = contexte_death_from_above(m["allies"])
    cands = playbook.generate_candidates(ctx)
    assert cands and cands[0]["target"] == 87, (
        "tie-break : cible retenue %s au lieu de la PREMIERE de `fromHere` (87)"
        % ((cands or [{}])[0].get("target"),))


def test_tie_break_suit_l_ordre_de_from_here_pas_l_id(playbook):
    """Le tie-break garde le PREMIER ENUMERE, pas le plus petit id : on INVERSE `fromHere` sur le
    meme montage B et la cible retenue change. Sans ce test, un port qui trierait par id passerait
    le precedent (87 < 89)."""
    m = MONTAGES["B"]
    ctx = contexte_death_from_above(m["allies"], from_here=list(reversed(FROM_HERE)))
    cands = playbook.generate_candidates(ctx)
    assert cands and cands[0]["target"] == 89, (
        "ordre inverse : cible retenue %s au lieu de 89 (la premiere enumeree a egalite)"
        % ((cands or [{}])[0].get("target"),))


def test_min_utility_ecarte_une_cible_sans_tuile_libre(playbook):
    """`...DeathFromAbovePlaybook$$.cctor` pose `MIN_UTILITY = 1` et le corps ne porte AUCUN gate
    `n > 0` : c'est le SEUIL qui ecarte une cible entouree. On ferme les six voisins de `u85`
    (non marchables) -- son compte tombe a 0 et elle ne peut plus etre retenue."""
    ferme = {p: False for p in VOISINS[(3, 3)]}
    ctx = contexte_death_from_above(MONTAGES["B"]["allies"], walkable=ferme)
    assert int(playbook._spawn_tiles(ctx, (3, 3))) == 0, "le montage du seuil n'a pas mordu"
    cands = playbook.generate_candidates(ctx)
    assert cands, "toutes les cibles ecartees : montage degenere, le seuil n'est pas exerce"
    assert cands[0]["target"] != 85, "une cible a 0 tuile libre a ete retenue : %r" % (cands,)


def test_aucune_cible_admissible_ne_rend_aucun_candidat(playbook):
    """Toutes les cibles a 0 -> liste VIDE, jamais un candidat a utilite nulle. C'est le seul cas
    ou le playbook ne propose rien, et il doit rester distinct d'un `pred = 0`."""
    ferme = {p: False for vs in VOISINS.values() for p in vs}
    ctx = contexte_death_from_above(MONTAGES["A"]["allies"], walkable=ferme)
    assert playbook.generate_candidates(ctx) == [], (
        "des candidats subsistent alors qu'aucune cible n'a de tuile d'atterrissage")


def test_le_caster_ne_se_deplace_pas(playbook):
    """L'utilite est POSITION-INDEPENDANTE (ni le compte ni la cible ne lisent `casterPosition`),
    et le balayage natif met l'ORIGINE en tete avec un `AddAction` keep-first -> `to is None`."""
    ctx = contexte_death_from_above(MONTAGES["A"]["allies"])
    cands = playbook.generate_candidates(ctx)
    assert cands and cands[0]["to"] is None, (
        "le port propose un deplacement pour une utilite position-independante : %r" % (cands,))
