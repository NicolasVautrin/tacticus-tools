"""SorcerousFacade (1100, Yazaghor `thousTzaangor`) -- face COMBAT, confrontee au LIVE (#287).

CE QUE CE FICHIER GARDE, et pourquoi aucun de ces points ne passe par accident

`...SorcerousFacadeAbility$$ExecuteBehaviour` a QUATRE termes ; chacun a un observable PROPRE, et un
port qui n'en porterait que trois passerait n'importe quel controle global. Ils sont donc separes :

A. **L'EFFET [1]** `AddEffect(1204 SorcerousFacade_AdditionalHits -> Caster + Target)` : l'effet est
   sur LES DEUX unites, live comme offline. Il n'est pas decoratif -- pose AVANT l'attaque, il lui
   ajoute son coup Psychic (visible dans le diagnostic `attack.additional_hits`).
B. **LES DEUX RAILS [2]** : la cible du CAST est un ALLIE (`abilityTargets` natif ne rend QUE lui),
   l'attaque part sur `sel` = l'ENNEMI le plus proche. Les PV de l'allie ne bougent pas.
C. **LE SELECTEUR est bien `First(SortByDistance(..., Caster))`** : deux bras ou l'ennemi COLLE au
   caster change (`swap_foes`). Un port qui prendrait « le premier ennemi enumere » (ordre d'id)
   frapperait la MEME unite dans les deux bras -- ici c'est `ultraTitus` (id 77) dans un bras et
   `ultraCalgar` (id 79) dans l'autre, donc l'ordre d'id est EXCLU.
D. **LE SWITCH [4] a lieu DANS LE CAST** : `TriggerAbilityDelayed` est PLANIFIE cote natif ; le port
   le collapse inline. Les positions echangees juste apres `applyAction` TRANCHENT que le collapse
   est fidele -- s'il ne l'etait pas, il faudrait un scheduler.
E. **A/B CAUSAL** : le MEME etat rejoue avec 1100 RETIRE d'`ABILITY_CLASSES` ne bouge RIEN. C'est ce
   qui interdit d'attribuer l'accord a autre chose que ce port.
F. **LES FLAGS DE TOUR** : le switch ne pose PAS `UnitFlag.Moved` (mesure `combatSnapshot.unitFlags`
   AVANT/APRES). C'est le `MoveUnitOptions+0x11` du natif, et c'est ce qui a fait naitre le
   parametre `MoveUnitOperation(set_moved=...)`.
G. **LA REGLE DYNAMIQUE MORD** (bras `far`) : les deux ennemis hors de portee -> le natif REFUSE le
   cast EN SILENCE (`ok=True`, aucune mutation -- signature #111), parce que
   `...$$GetDynamicInvalidTargetReason` exige que le caster ait une cible d'attaque normale. Sans
   cette regle le port posait l'effet sur DEUX unites et echangeait les positions : une divergence
   qui MUTAIT l'etat, pas un ecart theorique.

Le montage vit dans `scripts/python/probe_287_facade_combat.py` (build isole, drive des positions
des DEUX camps, snapshot pre-cast, cast LIVE, replay OFFLINE sur le MEME `state.rng`). ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_287_facade_combat as P                          # noqa: E402

CASTER = P.CASTER_VID
ALLY = P.ALLY_VID
EFFECT = P.EFFECT_NAME


@pytest.fixture(scope="module")
def facade_cases(live_session):
    """Les DEUX bras du montage (`base` / `swap`), montes une fois pour tout le fichier.

    Montage NON installe => ECHEC, jamais skip (#268) : un skip ici serait un vert qui ment."""
    cache: dict = {}

    ARMS = {"base": (False, False, 0, "rs_287_facade.json"),
            "swap": (True, False, 1, "rs_287_facade_swap.json"),
            "far": (False, True, 2, "rs_287_facade_far.json")}

    def _case(name: str) -> dict:
        if name not in cache:
            swap, far, dseed, sfile = ARMS[name]
            r = P.run(swap_foes=swap, far_foes=far, seed=P.SEED + dseed, state_name=sfile)
            if r.get("error"):
                pytest.fail("montage SorcerousFacade COMBAT NON INSTALLE (%s) : %s"
                            % (name, r["error"]))
            cache[name] = r
        return cache[name]
    return _case


def _foe(r):
    return r["live"]["foe"]


def test_le_cast_est_accepte_et_ne_vise_que_l_allie(facade_cases):
    """B -- rail ALLIE. `abilityTargets` natif rend UNE seule cible legale pour 1100 : l'allie
    Psyker. C'est la non-regression du VETO #217 vue depuis la face COMBAT."""
    r = facade_cases("base")
    assert r["live"]["ok"], "le natif a REFUSE le cast : montage invalide, aucune mesure"
    assert r["live"]["legal_targets"] == [r["ids"][ALLY]], (
        "cibles legales natives de 1100 = %s (attendu : le seul allie Psyker %s)"
        % (r["live"]["legal_targets"], r["ids"][ALLY]))


def test_le_switch_de_positions_a_lieu_dans_le_cast(facade_cases):
    """D -- le terme [4]. Les positions du caster et de l'allie sont ECHANGEES, live ET offline.
    Le fait qu'elles le soient JUSTE APRES `applyAction` est ce qui valide le collapse inline du
    `TriggerAbilityDelayed`."""
    for name in ("base", "swap"):
        r = facade_cases(name)
        L = r["live"]
        assert L["post"][CASTER] == L["pre"][ALLY] and L["post"][ALLY] == L["pre"][CASTER], (
            "bras %s : le natif n'a pas echange les positions (%s -> %s)"
            % (name, L["pre"], L["post"]))
        assert r["offline"]["post"] == L["post"], (
            "bras %s : positions offline %s != natif %s"
            % (name, r["offline"]["post"], L["post"]))


def test_l_attaque_part_sur_l_ennemi_pas_sur_l_allie(facade_cases):
    """B -- le terme [2]. `sel` est l'ENNEMI le plus proche : ses PV baissent, ceux de l'allie et du
    caster ne bougent pas. Degat compare LIVE vs OFFLINE a l'unite pres (meme `state.rng`)."""
    for name in ("base", "swap"):
        r = facade_cases(name)
        L, O, foe = r["live"], r["offline"], _foe(r)
        dmg = L["pre_hp"][foe] - L["post_hp"][foe]
        assert dmg > 0, "bras %s : l'ennemi colle (%s) n'a pris aucun degat" % (name, foe)
        assert L["post_hp"][ALLY] == L["pre_hp"][ALLY], "bras %s : l'ALLIE a pris du degat" % name
        assert L["post_hp"][CASTER] == L["pre_hp"][CASTER], "bras %s : le CASTER a pris du degat" % name
        assert O["post_hp"] == L["post_hp"], (
            "bras %s : PV offline %s != natif %s" % (name, O["post_hp"], L["post_hp"]))


def test_le_selecteur_prend_le_plus_proche_pas_le_premier_enumere(facade_cases):
    """C -- LE discriminant du sous-arbre `First(SortByDistance(ValidNormalAttackTargets, Caster))`.
    Les deux bras ont les MEMES deux ennemis ; seul CHANGE lequel est colle au caster. L'unite
    frappee doit SUIVRE, dans les deux camps de la mesure."""
    hit = {}
    for name in ("base", "swap"):
        r = facade_cases(name)
        foe, far = r["live"]["foe"], r["live"]["far"]
        assert r["live"]["post_hp"][far] == r["live"]["pre_hp"][far], (
            "bras %s : l'ennemi LOINTAIN (%s) a pris du degat -- ce n'est pas `sel`" % (name, far))
        hit[name] = foe
    assert hit["base"] != hit["swap"], (
        "les deux bras frappent la MEME unite (%s) : le selecteur ne suit pas la DISTANCE "
        "(un ordre par id donnerait exactement ce resultat)" % hit["base"])


def test_l_effet_1204_est_pose_sur_le_caster_ET_l_allie(facade_cases):
    """A -- le terme [1]. `AddEffect(1204 -> Caster + Target)` : DEUX poses, live comme offline."""
    for name in ("base", "swap"):
        r = facade_cases(name)
        L, O = r["live"], r["offline"]
        assert EFFECT in L["effects_caster"], "bras %s : effet 1204 absent du CASTER (live)" % name
        assert EFFECT in L["effects_ally"], "bras %s : effet 1204 absent de l'ALLIE (live)" % name
        assert EFFECT in (O["effects"].get(CASTER) or []), "bras %s : 1204 absent du caster (port)" % name
        assert EFFECT in (O["effects"].get(ALLY) or []), "bras %s : 1204 absent de l'allie (port)" % name


def test_l_effet_1204_alimente_deja_l_attaque_du_meme_cast(facade_cases):
    """A/[1] avant [2] -- l'ORDRE des termes est observable : l'effet pose par [1] ajoute son coup
    Psychic a l'attaque de [2]. Si le port posait l'effet APRES l'attaque, `additional_hits` serait
    vide et le total live ne serait pas atteint."""
    r = facade_cases("base")
    atk = ((r["offline"]["diag"] or {}).get("attack") or {}).get("attack") or {}
    ah = atk.get("additional_hits") or {}
    assert ah.get("hits"), "aucun coup additionnel : l'effet 1204 n'alimente pas l'attaque"
    assert "Psychic" in (ah.get("profiles") or []), (
        "profil des coups additionnels = %s (attendu Psychic, `constants.damageProfile` de 1100)"
        % ah.get("profiles"))


def test_sans_le_port_rien_ne_bouge(facade_cases):
    """E -- A/B CAUSAL. Le MEME etat, rejoue avec 1100 hors d'`ABILITY_CLASSES`, laisse positions ET
    PV INCHANGES : l'accord mesure plus haut ne peut donc pas venir d'ailleurs."""
    for name in ("base", "swap"):
        r = facade_cases(name)
        assert r["noport"]["post"] == r["offline"]["pre"], (
            "bras %s : les positions bougent SANS le port -- une autre voie execute 1100" % name)
        assert r["noport"]["post_hp"] == r["offline"]["pre_hp"], (
            "bras %s : les PV bougent SANS le port" % name)


def test_la_regle_dynamique_refuse_le_cast_sans_cible_d_attaque_normale(facade_cases):
    """G -- `...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason`, 2e conjonction. Les deux
    ennemis hors de portee : le natif REFUSE (aucune mutation malgre `ok=True`) et le port aussi
    (`invalid_target = TargetMatchesDynamicRule`). C'est la seule mesure du lot ou l'observable est
    « RIEN ne se passe » -- donc la seule ou un port trop permissif se voit."""
    r = facade_cases("far")
    L, O = r["live"], r["offline"]
    assert L["post"] == L["pre"], "bras far : le NATIF a mute les positions (%s -> %s)" % (L["pre"], L["post"])
    assert L["post_hp"] == L["pre_hp"], "bras far : le NATIF a inflige du degat"
    assert not L["effects_caster"] and not L["effects_ally"], (
        "bras far : le natif a POSE des effets (%s / %s) -- le refus n'est pas total"
        % (L["effects_caster"], L["effects_ally"]))
    assert O["post"] == O["pre"], "bras far : le PORT execute un cast que le natif refuse"
    assert not any(O["effects"].values()), (
        "bras far : le PORT pose l'effet 1204 alors que le natif refuse le cast (%s)" % O["effects"])
    assert (O["diag"] or {}).get("invalid_target") == 2, (
        "bras far : le port ne refuse pas par la REGLE DYNAMIQUE (diag=%s)" % (O["diag"],))


def test_le_switch_ne_pose_pas_le_flag_moved(facade_cases):
    """F -- `MoveUnitOptions+0x11`. Le caster TELEPORTE par le switch ne recoit PAS `UnitFlag.Moved`
    (0) cote natif ; le port ne doit pas le poser non plus (sinon il fermerait a tort la regle
    `CasterHasNotMoved` d'un cast ulterieur du meme tour).

    ⚠ `NoActionAvailable` (4) reste ABSENT cote port : il est pose par
    `IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation`, que le port n'a jamais porte --
    residu TRANSVERSE (turn-flow), pas un effet de ce cast. Le test le nomme au lieu de le taire."""
    r = facade_cases("base")
    MOVED, NO_ACTION = 0, 4
    assert MOVED not in (r["live"]["flags_added"][CASTER] or []), (
        "le natif POSE `Moved` sur le caster du switch : la lecture du port est a revoir")
    assert MOVED not in (r["offline"]["flags_post"][CASTER] or []), (
        "le port pose `Moved` sur le caster du switch (flags=%s) alors que le natif ne le fait pas"
        % r["offline"]["flags_post"][CASTER])
    live_added = set(r["live"]["flags_added"][CASTER] or [])
    off_added = set(r["offline"]["flags_post"][CASTER] or [])
    assert live_added - off_added == {NO_ACTION}, (
        "ecart de flags AUTRE que le residu turn-flow connu : live=%s port=%s"
        % (sorted(live_added), sorted(off_added)))
