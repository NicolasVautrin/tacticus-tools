"""CONFRONT LIVE de `1069 SeekerMissileFrequencyLock` (`tauMarksman` Sho'syl, Tau, HERO) -- #491.

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * le cast NE FRAPPE PAS. L'audit `combat-ability-coverage` classe 1069 `DAMAGE(HeavyRound)` et la
    prediction native affiche bien un intervalle de degat -- mais
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour`
    ne porte AUCUN noeud d'attaque. Le `HeavyRound` du kit appartient a la PHASE 2
    (`...Triggered.Loki.SeekerMissileFrequencyLock_AttackAbility$$CreateBehaviour`,
    `TriggeredAbilityType.SeekerMissileFrequencyLock_Attack` = 1127), NON portee (residu #491-r1).
    Sans cette garde, un futur port « qui fait des degats parce que le kit en annonce » passerait.
  * les BONDS sont INVERSES et c'est le point ou une recopie du voisin se trompe : 1123 `_Target`
    sur la CIBLE bonde au CASTER, 1136 `_Aiming` sur le CASTER bonde a la CIBLE. L'empreinte
    d'effets seule NE PEUT PAS le voir (`decisionView.effects` ne publie pas le bond) -> la garde
    lit la CASCADE du cast natif, seul canal qui porte `BondEffect_BondedId`.
  * le GATE DE CIBLAGE mord. `TARGETING_OPTIONS` absent => `get_invalid_target_reason` rend 0
    immediatement : le moteur accepterait des casts que
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Degradation PERMISSIVE,
    ni erreur ni crash, invisible en self-play -- exactement le trou qu'un entrainement exploiterait.

Le montage (build + DRIVE des positions par `--place`/`--a-place`, la geometrie de spawn de MC1_67
mettant Sho'syl hors de sa portee 5) et TOUTES les lectures vivent dans
`scripts/python/probe_491_seeker_missile_frequency_lock.py` : le probe MESURE, ce test GARDE, une
seule implementation -- aucune divergence possible entre les deux.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_491_seeker_missile_frequency_lock as P

SEEKER = 1069                  # ActiveAbilityType.SeekerMissileFrequencyLock
MARKERLIGHT = P.MARKERLIGHT    # 1122 EffectType.Markerlight
SEEKER_TARGET = P.SEEKER_TARGET  # 1123 EffectType.SeekerMissileFrequencyLock_Target
SEEKER_AIMING = P.SEEKER_AIMING  # 1136 EffectType.SeekerMissileFrequencyLock_Aiming


@pytest.fixture(scope="module")
def seeker(live_session):
    """UN SEUL runner pour tout le fichier : le cast est joue une fois des DEUX cotes, les gardes
    ci-dessous relisent la MEME mesure (le cast n'est pas rejouable -- il consomme l'actif)."""
    m, dispose = P.measure(live_session, state_name="test_491_seeker")
    try:
        yield m
    finally:
        dispose()


def test_seeker_lock_execution_is_ported(seeker):
    """La face EXECUTION est portee : sans elle, la decision CHOISIT le cast et l'execution
    l'IGNORE -- 0 degat, 0 effet, AUCUNE erreur (le no-op silencieux que #491 ferme)."""
    assert seeker["routed"] == "handler" and seeker["ported"] is True, \
        "1069 non portee (routed=%s ported=%s)" % (seeker["routed"], seeker["ported"])
    assert not seeker["cast_error"], "cast natif bloque: %s" % seeker["cast_error"]


def test_seeker_lock_effect_footprint_matches_native(seeker):
    """Empreinte `{unite -> {effectType: remaining}}` : le port doit poser EXACTEMENT les effets du
    natif, sur les MEMES porteurs, avec les MEMES durees.

    `1122 Markerlight` porte `TurnsUntilEndOfCurrentPlayersNextTurn` (= `ConvertRoundsToTurns(1)+1`,
    le `Sum(TurnsFromRounds(1), Direct(1))` du decompile) ; les deux BONDS recoivent une struct
    d'options ZERO -> duree `DefaultAmountOfRounds`, publiee `remaining 0` (permanent)."""
    off, live = seeker["off"], seeker["live"]
    assert off == live, "empreinte d'effets offline %s != live %s" % (off, live)
    caster, target = seeker["caster"], seeker["target"]
    assert set(off.get(target, {})) == {MARKERLIGHT, SEEKER_TARGET}, \
        "la CIBLE u%d porte %s, attendu {1122 Markerlight, 1123 _Target}" % (target, off.get(target))
    assert set(off.get(caster, {})) == {SEEKER_AIMING}, \
        "le CASTER u%d porte %s, attendu {1136 _Aiming}" % (caster, off.get(caster))
    assert off[target][MARKERLIGHT] == seeker["turns"] and seeker["turns"] > 0, \
        "duree du Markerlight %s != TurnsUntilEndOfCurrentPlayersNextTurn %s" % (
            off[target].get(MARKERLIGHT), seeker["turns"])
    assert off[target][SEEKER_TARGET] == 0 and off[caster][SEEKER_AIMING] == 0, \
        "les deux bonds doivent porter la duree DEFAUT (remaining 0), pas une duree explicite"


def test_seeker_lock_bonds_are_inverted(seeker):
    """Les deux `AddBondEffect` passent les MEMES deux selecteurs dans l'ordre INVERSE.

    C'est le seul etage que l'empreinte ne voit pas, et le seul ou recopier l'ability voisine se
    trompe SILENCIEUSEMENT : les deux effets existeraient, sur les bons porteurs, avec les bonds
    croises a l'envers."""
    caster, target = seeker["caster"], seeker["target"]
    attendu = {SEEKER_TARGET: {"on": target, "bonded": caster},     # sur la CIBLE, bonde au CASTER
               SEEKER_AIMING: {"on": caster, "bonded": target}}     # sur le CASTER, bonde a la CIBLE
    for et, exp in attendu.items():
        got = seeker["off_bonds"].get(et)
        assert got is not None, "effet %d absent du port" % et
        assert (got["on"], got["bonded"]) == (exp["on"], exp["bonded"]), \
            "port: effet %d pose sur u%s bonde a u%s, attendu sur u%s bonde a u%s" % (
                et, got["on"], got["bonded"], exp["on"], exp["bonded"])

    # Le NATIF est l'oracle. Une cascade muette n'est PAS un vert : on le dit.
    live_bonds = seeker["live_bonds"]
    assert live_bonds, ("la cascade du cast natif n'a publie AUCUN bond -- l'oracle est MUET, "
                        "l'accord port/decompile ne peut pas etre confirme (canal a re-verifier)")
    for et, exp in attendu.items():
        got = live_bonds.get(et)
        assert got is not None, "effet %d absent de la cascade NATIVE" % et
        assert (got["on"], got["bonded"]) == (exp["on"], exp["bonded"]), \
            "natif: effet %d pose sur u%s bonde a u%s, attendu sur u%s bonde a u%s" % (
                et, got["on"], got["bonded"], exp["on"], exp["bonded"])


def test_seeker_lock_cast_deals_no_damage(seeker):
    """LA REFUTATION de la classification `DAMAGE(HeavyRound)` de l'audit : le cast ne retire
    AUCUN point de vie, ni cote port ni cote natif.

    Le degat existe -- il appartient a la triggered 1127 (phase 2, non portee, residu #491-r1). Un
    port qui le poserait au CAST diverge du natif d'un tour entier ET d'un porteur."""
    for cote, (before, after) in (("port", seeker["off_hp"]), ("natif", seeker["live_hp"])):
        changes = {k: (before[k], after.get(k)) for k in before if after.get(k) != before[k]}
        assert not changes, "%s : le CAST a change des HP %s -- il ne doit RIEN infliger" % (
            cote, changes)


def test_seeker_lock_markerlight_bites(seeker):
    """GENERALISATION : l'effet pose est-il VIVANT, ou seulement present ?

    `Markerlight` (1122) est PORTE (`MarkerlightEffect$$CreateDamageModifier`, ForPercentIncrease de
    la regle globale `MarkerlightDmgBonusPct`) : apres le cast, la prediction NATIVE d'une attaque
    ranged T'AU sur la cible doit monter de ce pourcentage. Un effet pose INERTE n'emet rien -- on
    tranche donc par le RETOUR (la prediction), pas par le silence.

    ⚠ On N'EXIGE PAS `round(affiche * 1.15)` : `dmgMin`/`dmgMax` sont DEJA arrondis, la valeur
    interne derriere `6008` vit dans [6007.5, 6008.5), et son image contient 6909 comme 6910.
    Reconstituer l'arrondi natif depuis une sortie arrondie serait fitter un scalaire. Le critere
    est l'ENCADREMENT, plus un temoin NON-NUL (un encadrement passe trivialement a bonus nul)."""
    before, after = seeker["pred_before"], seeker["pred_after"]
    pct = int(seeker["markerlight_pct"])
    communes = sorted(set(before) & set(after))   # meme TUILE des deux cotes, jamais `ranked[0]`
    assert communes, ("aucune tuile commune entre les deux predictions : le scenario ne mesure "
                      "RIEN (l'allie T'AU ranged doit pouvoir viser la cible avant ET apres)")
    assert pct > 0 and any(after[t] != before[t] for t in communes), \
        "REGIME DEGENERE (pct=%s, prediction inchangee) : l'encadrement ne prouverait rien" % pct
    for tile in communes:
        for v0, v1 in zip(before[tile], after[tile]):
            lo, hi = (v0 - 0.5) * (100 + pct) / 100, (v0 + 0.5) * (100 + pct) / 100
            assert (lo - 0.5) <= v1 <= (hi + 0.5), \
                "tuile %s : %d -> %d hors de l'image [%0.1f, %0.1f] du bonus +%d%%" % (
                    tile, v0, v1, lo, hi, pct)


def test_seeker_lock_targeting_gate_bites(seeker):
    """`TARGETING_OPTIONS` = 0x4002 (`TargetMatchesDynamicRule | TargetIsEnemy`), lu dans
    `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset +0x180>+0x28` (le ctor de
    l'ability n'appelle AUCUN `TargetingOptions$$.ctor` -- il recopie le preset statique).

    Ce test est le pendant de la regle « entrer au registre SANS son masque = regression
    silencieuse » : il echoue si le masque disparait, alors qu'AUCUN autre test ne le verrait
    (l'absence de masque ne casse rien, elle ACCEPTE tout)."""
    gate, natif = seeker["gate"], seeker["gate_natif"]
    assert gate["ennemi"] == 0, \
        "le port REFUSE la cible ennemie du natif (raison 0x%x)" % gate["ennemi"]
    assert gate["allie"] != 0, "le port ACCEPTE un cast sur un ALLIE -- gate TargetIsEnemy absent"
    assert gate["soi"] != 0, "le port ACCEPTE un cast sur SOI-MEME -- gate TargetIsEnemy absent"
    # Oracle natif du meme gate : `targets` (superset move-inclus) n'enumere QUE des ennemis.
    assert not natif["allie_dans_targets"] and not natif["soi_dans_targets"], \
        "le NATIF enumere l'allie/le caster comme cible legale : le gate porte est TROP strict"
