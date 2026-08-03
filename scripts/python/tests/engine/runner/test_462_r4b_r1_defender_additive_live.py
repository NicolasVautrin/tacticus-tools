"""#462-r4b-r1 -- le DEGAT de l'attaque COMMANDEE par `UseActiveAbility`, assertionne PAR COUP.

C'est le trou que #462-r4b avait NOMME sans le fermer (`case-462-r4b-pose-vs-etat-final.md` §7) :

    blackAbaddon (trait TerminatorArmour)   PORT 10038 -> 2308   (7730 infliges)
                                            LIVE 10038 -> 7442   (2596 infliges)   facteur 2,98

Il a survecu parce qu'AUCUN test ne regardait ce degat -- `test_chain_after_refused_addeffect_live`
n'assertionne, sur ce bras, que la POSE, la MORT et l'etat FINAL des effets.

LA CAUSE, LUE AU DECOMPILE : `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` resout ses
DEUX accumulateurs par les slots d'interface `0xd` et `0xe`, lit le champ `Addition@+0x10` de CHACUN
(`FixMath.NET.Fix64$$op_Explicit`) et passe a
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` la SOMME
`base + Addition(0xd) + Addition(0xe)` -- aux DEUX call-sites (borne MIN et borne MAX). Ce dernier NE
re-consomme PAS `+0x10` (il commence par `GetBaseDamageWithFixedPiercedArmor`). L'additif du
DEFENSEUR partage donc le slot PRE-PERCAGE de celui de l'ATTAQUANT (#75), ce que la PREDICTION faisait
deja (`_add_positional_and_defender_mods`) et que le COMBAT ne faisait PAS : il le laissait a
`apply_all_modifiers(., def_mods)`, donc APRES les %-list et les deux `Multiplier@0x30` -- un `+997`
(`ExemplarOfHate_Target.extraDmg`) ni dilue par l'armure, ni reduit par le `x0.25` de
`TerminatorArmour_ReduceDmg`.

DEUX BRAS, ET CHACUN SEPARE UN AXE :

  * `blackAbaddon`     -- additif defenseur ET `%-list` defenseur `x0.25` : le regime du residu ;
  * `blackPossession`  -- additif defenseur SEUL (aucune reduction) : l'axe ARMURE a nu, la borne MIN
                          separant les deux placements parce que la MAX bascule sur la branche
                          `d - armure` du plancher.

Le ledger PAR COUP est confronte a l'unite (l'etat port est cale sur le RNG du runner, donc les deux
cotes tirent le MEME flux) ; le bras `control` TUE la cible, donc seuls ses coups NON ECRETES sont
comparables -- ce que le test derive au lieu de le supposer.

Montage : `probe_462_r4b_r1_terminator_commanded_attack.measure` (ce fichier n'en est que la porte
pytest). ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_terminator_commanded_attack as PB
import probe_n5_chain_after_refused_addeffect as N5

TERMINATOR_REDUCE = 1147          # `TerminatorArmour_ReduceDmg`
EOH_TARGET = 1293                 # `ExemplarOfHate_Target` (l'additif defenseur, pose par la chaine)


@pytest.fixture(scope="module")
def enemy_layout(live_session):
    """Positions REELLES du camp adverse (build de reconnaissance jetable) -- ancre de deploiement
    des runners de mesure : on CHOISIT les positions au lieu de les subir."""
    return N5.enemy_layout(live_session)


@pytest.fixture(scope="module")
def immune_case(live_session, enemy_layout):
    m = PB.measure(live_session, N5.IMMUNE_VICTIM, enemy_layout, with_variant=True)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


@pytest.fixture(scope="module")
def control_case(live_session, enemy_layout):
    m = PB.measure(live_session, N5.CONTROL_VICTIM, enemy_layout, with_variant=True)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


def _live_unclamped(m):
    """Les coups natifs COMPARABLES : le ledger live s'arrete des que la cible meurt (coups a 0) et
    ECRETE le coup letal aux PV restants. On garde le prefixe STRICTEMENT avant l'ecretage, derive
    des PV -- jamais un compte suppose."""
    hits, hp = list(m["live_per_hit"]), (m["live_hp"][0] or (0,))[0]
    out = []
    for h in hits:
        if h <= 0 or h >= hp:          # coup post-mortem, ou coup letal ecrete
            break
        out.append(h)
        hp -= h
    return out


# --------------------------------------------------------- (1) le regime du residu : REDUCTION + ADDITIF

def test_terminator_armour_reduit_l_attaque_commandee(immune_case):
    """Le degat de l'attaque libre de la chaine, PAR COUP, contre une cible `TerminatorArmour`.
    La cible SURVIT (10038 PV) : les six coups sont comparables sans ecretage."""
    m = immune_case
    assert TERMINATOR_REDUCE in m["pre_active"], (
        "l'armure n'est pas ACTIVE au chargement -> le regime ne teste pas la reduction (%s)"
        % (m["pre_active"],))
    assert m["port_per_hit"] == m["live_per_hit"], (
        "ledger PAR COUP divergent\n  port=%s\n  live=%s" % (m["port_per_hit"], m["live_per_hit"]))
    assert m["port_delta"] == m["live_delta"], (
        "degat total port=%s live=%s" % (m["port_delta"], m["live_delta"]))
    assert m["live_delta"] > 0, "aucun degat -> la chaine n'a pas porte son attaque"


def test_le_contre_modele_POST_pct_list_MORD_sur_ce_bras(immune_case):
    """Le rejeu du MEME etat avec le corps d'AVANT ce correctif (`_no_merge_variant`, l'etat exact
    d'`origin/master`) doit DIVERGER du natif. Sans ce test, `port == live` pourrait tenir d'un port
    qui n'exerce plus l'axe du tout : ici on prouve que l'axe DECIDE du resultat."""
    m = immune_case
    assert m["variant_per_hit"], "contre-modele non joue"
    assert m["variant_per_hit"] != m["live_per_hit"], (
        "le contre-modele rend le MEME ledger -> regime NON discriminant (%s)" % (m["variant_per_hit"],))
    assert sum(m["variant_per_hit"]) > 2 * sum(m["live_per_hit"]), (
        "le contre-modele devait SUR-infliger largement : variant=%s live=%s"
        % (sum(m["variant_per_hit"]), sum(m["live_per_hit"])))


# --------------------------------------------------- (2) l'axe ARMURE seul (cible SANS TerminatorArmour)

def test_l_additif_defenseur_traverse_l_armure_sans_reduction(control_case):
    """Bras `control` : la cible n'a PAS le trait, donc aucune `%-list` defenseur. Ce qui separe
    encore les deux placements, c'est le PERCAGE -- l'additif pre-percage est dilue par l'armure.
    La cible MEURT ici : on ne confronte que les coups non ecretes, derives des PV."""
    m = control_case
    assert TERMINATOR_REDUCE not in m["pre_active"], "bras control contamine par l'armure"
    live = _live_unclamped(m)
    assert len(live) >= 3, "moins de 3 coups non ecretes -> bras non concluant (%s)" % (m["live_per_hit"],)
    assert m["port_per_hit"][:len(live)] == live, (
        "ledger PAR COUP divergent hors ecretage\n  port=%s\n  live=%s"
        % (m["port_per_hit"][:len(live)], live))
    assert m["port_delta"] == m["live_delta"], (
        "degat SANTE total port=%s live=%s" % (m["port_delta"], m["live_delta"]))


def test_le_contre_modele_MORD_aussi_sans_reduction(control_case):
    """Le meme contre-modele, sur le bras SANS reduction : il doit deja diverger a la borne MIN.
    C'est ce qui etablit que le correctif ne se reduit PAS a « la face defenseur multiplicative » --
    l'additif est mal place meme quand cette face est vide."""
    m = control_case
    live = _live_unclamped(m)
    assert m["variant_per_hit"], "contre-modele non joue"
    assert m["variant_per_hit"][:len(live)] != live, (
        "le contre-modele rend le MEME ledger sans reduction -> l'axe ARMURE ne separe pas ici")


# ------------------------------------- (3) GENERALISATION D'ACCORD : autre vecteur, autre attaquant

@pytest.fixture(scope="module")
def followup_case(live_session):
    m = PB.measure_followup(live_session)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


def test_accord_sur_l_attaque_NORMALE_d_un_autre_attaquant(followup_case):
    """MEME foyer, TROIS variables changees : vecteur (attaque NORMALE ordinaire, plus
    `UseActiveAbility`), attaquant (`darkaHellblaster`, qui ne porte PAS `FearedInterrogator_Owner`
    -> additif ATTAQUANT NUL, l'additif DEFENSEUR est SEUL), profil (`Physical`).

    ⚠ CE BRAS N'EST PAS DISCRIMINANT et le test l'ASSERTIONNE : sur la branche ARMURE du plancher
    `max(d x pierce%, d - armure)`, le plancher est AFFINE DE PENTE 1, donc `P(v + A) = P(v) + A` --
    les deux placements coincident. C'est un datapoint d'ACCORD, pas une garde du correctif ; le cran
    algebrique correspondant vit dans `test_462_r4b_r1_defender_additive_offline.py`. L'assertion sur
    le contre-modele est ici une garde de LECTURE : si ce bras devenait discriminant sans qu'on s'en
    aperçoive, on le prendrait a tort pour une confirmation."""
    m = followup_case
    assert m["port_per_hit"] == m["live_per_hit"], (
        "ledger divergent sur l'attaque normale\n  port=%s\n  live=%s"
        % (m["port_per_hit"], m["live_per_hit"]))
    assert m["port_total"] == m["live_delta"], (
        "degat total port=%s live=%s" % (m["port_total"], m["live_delta"]))
    assert any("ExemplarOfHate_Target" in (c["active"] or []) for c in m["def_mods_calls"]), (
        "l'additif defenseur n'est pas en jeu -> le bras ne mesure rien")
    assert m["variant_per_hit"] == m["port_per_hit"], (
        "ce bras est devenu DISCRIMINANT (variant=%s port=%s) -- il ne doit plus se lire comme un "
        "simple accord, et le cran offline `branche ARMURE` est a revoir"
        % (m["variant_per_hit"], m["port_per_hit"]))


# ------------------------------------------------------------ (4) l'additif est bien celui de la CHAINE

def test_l_additif_defenseur_est_pose_par_la_chaine_elle_meme(immune_case):
    """Non-degenerescence : le `+997` mesure vient d'`ExemplarOfHate_Target`, pose par la chaine
    AVANT son attaque libre (donc absent de l'etat au chargement et present a l'arrivee). Si un jour
    il disparaissait, les deux bras deviendraient muets sans rougir."""
    m = immune_case
    assert EOH_TARGET not in m["pre_active"], "l'effet est deja la au chargement -> montage biaise"
    calls = m["def_mods_calls"]
    assert calls, "aucun appel de `defender_modifiers` capte pendant l'attaque libre"
    assert any("ExemplarOfHate_Target" in (c["active"] or []) for c in calls), (
        "l'additif defenseur n'est pas dans les effets ACTIFS vus par le foyer (%s)"
        % ([c["active"] for c in calls],))
    assert EOH_TARGET in {int(e[0]) for e in m["live_effects_post"]}, (
        "le natif ne porte pas l'effet apres le cast (%s)" % (m["live_effects_post"],))
