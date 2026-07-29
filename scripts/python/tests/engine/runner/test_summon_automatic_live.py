"""GARDE live de la CAUSE du trait `Summon` (#250) et du masque de 1065 `ScythingTalons`.

Trois cas (#245, #248, #243) ont CONTOURNE le meme symptome -- « une unite a trait `Summon` rend
`abilityState.usable == false` sur ses actives, donc l'oracle de ciblage court-circuite a `0x1` » --
en retirant le trait de l'entree de catalogue, sans jamais expliquer pourquoi. La cause, lue au
decompile puis mesuree, tient en deux maillons :

  1. `IdunBattle.Entities.UnitExtensions$$IsAutomatic` = `HasTrait(2 Summon) || HasTrait(13 Object)`,
     et `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` joue LUI-MEME toute unite
     automatique du camp (jusqu'a 5 actions tant que `HasActionLeft`, puis fin de tour). L'unite
     n'est jamais offerte au joueur.
  2. Quand elle caste, `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` incremente
     `ActiveAbility.AmountOfTimesUsed@0x10` puis re-evalue
     `IdunBattle.Entities.Abilities.AActiveAbility$$CanStillBeUsed(caster, amountOfTimesAlreadyUsed)`,
     qui -- hors boss / machine-primaire / `GetCooldownAfterUse() > 0` -- rend
     `amountOfTimesAlreadyUsed == 0`, donc `false`.

=> `CanStillBeUsed = false` n'est PAS un gate arme par le trait : c'est le RESIDU d'un cast reel.
Aucune regle « un summon ne rejoue pas ses actives » n'existe, donc le port n'a rien a MIRRORER
cote ciblage -- et il n'y a pas de degradation permissive sur cet axe.

Ce que ce test exige :
  * AVEC le trait -- le porteur n'est JAMAIS `ctrl` ni `hasAction`, et il CHANGE DE POSITION alors
    que la seule action emise est `endturn` : le moteur le joue ;
  * SANS le trait -- il est `ctrl`, il ne bouge pas d'un hex : c'est bien le trait qui commande ;
  * l'USAGE eteint le champ -- un cast conduit a la main fait passer `usable` true -> false ET
    inflige des degats (sans les degats, « usable=false » ne prouverait pas que l'ability a servi) ;
  * le masque de 1065 -- accord natif/port sur toutes les lignes, au moins une ligne ACCEPTEE, au
    moins une ligne que `TARGETING_OPTIONS = None` faux-accepterait, et le seuil de portee encadre
    des DEUX cotes (ENNEMI d=1 accepte / ENNEMI d=2 `TargetIsInRange`).

Le probe MESURE (`probe_250_summon_automatic.py`, qui porte le montage et sa justification), ce
test GARDE. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import probe_250_summon_automatic as P


@pytest.fixture(scope="module")
def auto(live_session):
    """Monte les DEUX variantes du meme roster (trait conserve / retire). Aucune action n'est
    emise sur le porteur : seulement `endturn`. Chaque runner est dispose par `run_variant`."""
    sid = live_session
    keep = P.run_variant(sid, P.SEED, P.BOARD, keep=True, rounds=3)
    strip = P.run_variant(sid, P.SEED, P.BOARD, keep=False, rounds=3)
    assert keep and strip, "montage KO : le porteur est absent du decisionView"
    return {"keep": keep, "strip": strip}


@pytest.fixture(scope="module")
def cast(live_session):
    """Variante CONTROLABLE : ennemi amene au contact, masque confronte, puis cast conduit."""
    out = P.run_cast(live_session, P.SEED, P.BOARD, rounds=6)
    assert out.get("before") and out.get("after"), \
        "montage KO : le porteur n'a jamais ete jouable (corriger le MONTAGE, pas l'assertion)"
    return out


def _usable(snap, aid=P.ABILITY):
    for a in snap["abilities"]:
        if a["id"] == aid:
            return a["usable"]
    raise AssertionError("ability %d absente du porteur" % aid)


# --------------------------------------------------------------- maillon 1 : le trait = automatique

def test_summon_never_offered_to_the_player(auto):
    """`PlayAutomaticUnitsOperation` prend l'unite en charge : elle n'a JAMAIS d'action a offrir.

    Le discriminant est `hasAction`, pas `ctrl` : `ctrl` designe le joueur COURANT (le camp a la
    main), pas la jouabilite de l'unite -- piege deja nomme par `probe_243`. La ligne probante est
    donc `ctrl=True` ET `hasAction=False` : le camp du porteur a la main, et pourtant le porteur
    n'offre rien, parce que le moteur l'a deja joue."""
    keep = auto["keep"]
    assert all(s["hasAction"] is False for s in keep), \
        "porteur avec une action offerte au joueur : %r" % ([s for s in keep if s["hasAction"]],)
    assert any(s["ctrl"] for s in keep), \
        "le camp du porteur n'a jamais eu la main : le montage ne prouve rien"
    assert any(s["ctrl"] and not s["hasAction"] for s in keep), \
        "aucune ligne `camp a la main + aucune action offerte` : montage non probant"


def test_summon_moves_without_any_order(auto):
    """Le moteur le JOUE : la position change alors que la seule action emise est `endturn`."""
    poss = [s["pos"] for s in auto["keep"]]
    assert len(set(poss)) > 1, "le porteur automatique n'a pas bouge : %s" % (poss,)


def test_without_the_trait_the_unit_is_controllable_and_inert(auto):
    """Contrefactuel : le MEME roster sans le seul trait `Summon` rend l'unite au joueur."""
    strip = auto["strip"]
    assert any(s["hasAction"] for s in strip), \
        "sans le trait, le porteur n'offre jamais d'action : le trait ne serait pas le facteur"
    poss = [s["pos"] for s in strip]
    assert len(set(poss)) == 1, "sans le trait, le porteur bouge quand meme : %s" % (poss,)


# --------------------------------------------------------- maillon 2 : l'USAGE eteint CanStillBeUsed

def test_usage_extinguishes_can_still_be_used(cast):
    """`ActiveAbilityOperation$$ExecuteInternal` : AmountOfTimesUsed++ puis re-evaluation."""
    assert _usable(cast["before"]) is True, "l'ability n'etait pas armee avant le cast"
    assert _usable(cast["after"]) is False, "l'ability est restee armee apres le cast"
    assert (cast["dmg"] or 0) > 0, \
        "aucun degat : `usable=false` ne prouverait pas que l'ability a SERVI"


# --------------------------------------------------------------- masque 1065 confronte sur le porteur

def test_mask_1065_agrees_with_native(cast):
    rows = cast["rows"]
    bad = [r for r in rows if r["nat"] != r["apres"]]
    assert not bad, "desaccord natif/port sur 1065 : %r" % (bad,)


def test_mask_1065_has_an_accepted_line(cast):
    """Sans une ligne a `0x0`, « le natif refuse tout » ne distingue pas le masque d'une ability
    indisponible (le court-circuit `CanCurrentlyBeUsed` rend `0x1` partout)."""
    assert any(r["nat"] == 0 for r in cast["rows"]), "aucune cible acceptee : montage non probant"


def test_mask_1065_closes_permissive_lines(cast):
    """Au moins une ligne que l'etat pre-masque (`TARGETING_OPTIONS = None`) faux-accepterait."""
    closed = [r for r in cast["rows"] if r["avant"] == 0 and r["nat"] != 0]
    assert closed, "le masque ne ferme aucun cast illegal : il serait inerte"


def test_mask_1065_range_threshold_is_bracketed(cast):
    """Le seuil de portee encadre des DEUX cotes : sans la ligne d=2, un port SANS volet portee
    passerait aussi."""
    foes = [r for r in cast["rows"] if r["side"] == "ENNEMI"]
    d1 = [r for r in foes if r["dist"] == 1]
    d2 = [r for r in foes if r["dist"] == 2]
    assert d1 and d2, "seuil non encadre : d=%s" % sorted({r["dist"] for r in foes})
    assert all(r["nat"] == 0 for r in d1), "ennemi au contact refuse : %r" % (d1,)
    assert all(r["nat"] == int(P.TR_IN_RANGE) for r in d2), \
        "ennemi a d=2 non refuse sur TargetIsInRange : %r" % (d2,)
