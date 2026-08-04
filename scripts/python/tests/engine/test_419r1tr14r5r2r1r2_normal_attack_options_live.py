"""#419-r1-tr14-r5-r2-r1-r2 -- les `TargetingOptions` de l'ATTAQUE NORMALE sont PAR TYPE.

`IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` ne porte aucun masque : il
en DEMANDE un PAR TYPE (`battleQuery.<slot 0x3e>(GetNormalAttackType(unit))`), et chaque
`<X>NormalAttackAbility$$.ctor` pose les siennes. Le port n'en avait qu'UN, celui de
`69 Loki_NormalAttack`, applique a toutes les unites.

CE QUE CE FICHIER GARDE -- cinq choses, aucune redondante :

  1. **LES VALEURS LUES** (cran OFFLINE). Les deux presets recopies
     (`<TargetingOptions statics>+0x00` = `0x4002`, `+0x80` = `0x4000`, ecrits par
     `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`) et surtout les DEUX
     LITTERAUX qui ne recopient aucun preset :
     `RogalDorn_NormalAttackAbility$$.ctor` -> `forceMeleeTarget = RangedBool.False`,
     `FloatingDeath_NormalAttackAbility$$.ctor` -> `range <- TargetingRange statics+0x30`
     (RANGE_ADJACENT). Une valeur changee sans repasser par la mesure rougit ici.
  2. **QUE LA TABLE N'EST PAS PLATE.** Si quelqu'un rabat les 18 types sur un jeu unique, le compte
     de jeux DISTINCTS tombe et le cran rougit -- c'est exactement la regression que la tranche
     corrige.
  3. **LE PORT CONTRE LE NATIF**, sur un type dont les options DIFFERENT du generique. Montage
     ECRIT (`BC.Units[].PassiveAbilities = ["FloatingDeath"]` -> attaque normale `1146`), deux
     runners APPARIES dont c'est le SEUL champ de difference.
  4. **LA CONTRE-EPREUVE MORD.** La BASELINE (la constante unique, c.-a-d. le port d'avant) doit
     DIVERGER du natif sur au moins une ligne. Sans ce cran, un vert de (3) ne prouverait pas que la
     tranche sert a quelque chose : les deux modeles coincident partout ou le `TargetingRange` est le
     meme. Le bras `ctrl` est la reciproque -- il BORNE : le port par-type n'y perd aucune ligne.
  5. **L'INERTIE DU BIT, DITE ET MESUREE.** `TargetMatchesDynamicRule` (le seul ecart des deux
     presets) cable `ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
     (= `FindAttackWeapon(...) != null ? 0 : 2`), NON PORTE -> le bit ne deplace aujourd'hui aucun
     verdict. Le cran l'ASSERTE au lieu de laisser croire que les types `0x4000` sont valides par
     l'observable. Le jour ou la regle est portee (residu `#419-r1-tr14-r5-r2-r1-r2-r1`), ce cran
     rougit et REDEMANDE une mesure -- c'est le point : sans la table par type, la regle serait alors
     armee sur cinq types que le natif desarme.

⚠ Le montage est OBLIGATOIRE, et c'est une MESURE :
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` commence par
`ActiveAbilityComponent.GetOrNull(comp, abilityType)` et rend `ValidRequest` (0x1) si l'ability n'est
pas MONTEE sur le caster. On ne peut donc pas interroger un type que le caster ne porte pas.

RE et mesures : `docs/rl/case-419-r1-tr14-r5-r2-r1-r2-presets-targeting.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2r1r2_normal_attack_options.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r2_normal_attack_options as P
from engine.runner.abilities.targeting import (
    RANGE_ADJACENT, RANGE_ADJACENT_IF_MELEE_CASTER, RANGED_BOOL_FALSE,
    RANGED_BOOL_IF_RANGED_CASTER, NORMAL_ATTACK_TARGETING_OPTIONS,
    NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE as OPTS)
from engine.runner.abilities.targeting_rule import TargetingRule as TR

TARGET_IS_IN_RANGE = int(TR.TargetIsInRange)


@pytest.fixture(scope="module")
def mesure(rpc):
    """Les deux bras APPARIES (`float` / `ctrl`), natif ET port. Un montage qui n'a pas mordu est un
    ECHEC (`MontageError`), jamais un skip vert."""
    from rl_collect_batch import _resolve_session
    try:
        return P.run(_resolve_session())
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


# ------------------------------------------------------------------------------- crans OFFLINE

def test_les_deux_presets_recopies():
    """(1) `<TargetingOptions statics>+0x00` = `0x4002`, `+0x80` = `0x4000` -- et les deux presets
    sont IDENTIQUES par ailleurs (meme `TargetingRange`, meme `forceMeleeTarget`)."""
    p00, p80 = OPTS[69], OPTS[1030]
    assert int(p00.rules) == 0x4002, "preset statics+0x00 : rules lues a <preset>+0x28"
    assert int(p80.rules) == 0x4000, "preset statics+0x80 : rules lues a <preset>+0x28"
    assert int(p00.rules) ^ int(p80.rules) == int(TR.TargetMatchesDynamicRule), (
        "le SEUL ecart des deux presets est le bit 1 TargetMatchesDynamicRule")
    for champ in ("self_cast", "range", "force_melee_target"):
        assert getattr(p00, champ) == getattr(p80, champ), (
            f"{champ} doit etre le meme dans les deux presets (recopie octet a octet)")
    assert p00.range == RANGE_ADJACENT_IF_MELEE_CASTER
    assert p00.force_melee_target == RANGED_BOOL_IF_RANGED_CASTER
    # Les trois types qui recopient `+0x80`, LUS ctor par ctor (1114 delegue au ctor de 1030).
    for aid in (17, 1030, 1114):
        assert int(OPTS[aid].rules) == 0x4000, aid


def test_les_deux_litteraux_hors_preset():
    """(1) Les deux ctors qui ne recopient AUCUN preset de `TargetingOptions`. Ce sont eux qui
    portent un champ AUTRE que `rules` different du generique -- donc les seuls observables."""
    assert OPTS[1126].force_melee_target == RANGED_BOOL_FALSE, (
        "RogalDorn_NormalAttackAbility$$.ctor passe `1` = RangedBool.False, pas `2`")
    assert OPTS[1126].range == RANGE_ADJACENT_IF_MELEE_CASTER, (
        "RogalDorn recopie bien `TargetingRange statics+0x00`")
    assert OPTS[1146].range == RANGE_ADJACENT, (
        "FloatingDeath_NormalAttackAbility$$.ctor recopie `TargetingRange statics+0x30`")
    assert OPTS[1146].force_melee_target == RANGED_BOOL_IF_RANGED_CASTER
    assert int(OPTS[1146].rules) == 0x4000 and int(OPTS[1126].rules) == 0x4000


def test_la_table_n_est_pas_plate():
    """(2) La regression que la tranche corrige = rabattre les 18 types sur UN jeu d'options."""
    distinct = {(int(o.rules), o.range, o.force_melee_target) for o in OPTS.values()}
    assert len(OPTS) >= 18, "les 18 types d'attaque normale du registre natif"
    assert len(distinct) == 4, (
        "quatre jeux d'options DISTINCTS sont LUS (preset+0x00, preset+0x80, RogalDorn, "
        f"FloatingDeath) ; trouve {len(distinct)}")
    assert NORMAL_ATTACK_TARGETING_OPTIONS is OPTS[69], (
        "le defaut du port reste le GENERIQUE 69, celui que la fabrique pose sans substitution")


# ---------------------------------------------------------------------------------- crans LIVE

def test_le_montage_a_mordu(mesure):
    """(3) Les deux bras portent bien le type attendu -- sans ca, les crans suivants mesureraient
    deux fois la meme chose."""
    for arm, _passives, want in P.ARMS:
        assert mesure[arm]["rows"], f"bras {arm} : aucune ligne mesuree"


def test_le_port_par_type_est_daccord_avec_le_natif(mesure):
    """(3) Accord TOTAL sur les deux bras."""
    t = P.tally(mesure)
    assert t["tot"] > 0, "aucune ligne native lisible"
    assert t["new"] == t["tot"], (
        f"port PAR TYPE : {t['new']}/{t['tot']} d'accord avec le natif")
    assert t["perte"] == 0, (
        f"{t['perte']} ligne(s) que la constante unique avait juste et que le par-type rate")


def test_la_constante_unique_diverge_du_natif(mesure):
    """(4) LA CONTRE-EPREUVE. Sans elle le vert precedent serait un accord DEGENERE."""
    t = P.tally(mesure)
    assert t["gain"] >= 1, (
        "REGIME DEGENERE : la constante unique est d'accord partout, cette geometrie ne separe pas "
        "les deux modeles (il faut une cible a d>1 DANS la portee d'arme et AUCUN ennemi adjacent)")
    # Et on NOMME le refus : le natif rompt `TargetIsInRange`, pas une autre regle.
    diverge = [r for r in mesure["float"]["rows"] if r["nat"] != r["old"]]
    assert diverge, "bras `float` : aucune ligne ou la baseline diverge"
    for r in diverge:
        assert r["nat"] == TARGET_IS_IN_RANGE, (
            f"cible u{r['tid']} d={r['d']} : le natif doit rompre TargetIsInRange, "
            f"trouve {hex(r['nat'])}")
        assert r["old"] == 0, (
            f"cible u{r['tid']} d={r['d']} : la baseline l'ACCEPTAIT (degradation permissive), "
            f"trouve {hex(r['old'])}")
        assert r["new"] == r["nat"]


def test_le_bras_ctrl_est_inchange(mesure):
    """(4) RECIPROQUE : sur le type GENERIQUE, le port par-type rend exactement ce que rendait la
    constante unique. Une tranche qui deborderait ferait bouger ce bras."""
    for r in mesure["ctrl"]["rows"]:
        assert r["new"] == r["old"], (
            f"bras ctrl, cible u{r['tid']} : le par-type ({hex(r['new'])}) doit coincider avec la "
            f"baseline ({hex(r['old'])}) -- le type 69 EST le generique")


def test_le_bit_dynamic_rule_est_inerte(mesure):
    """(5) `TargetMatchesDynamicRule` ne deplace aucun verdict tant que
    `ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason` n'est pas porte. Ce cran DIT la
    borne ; il rougira quand la regle sera portee, et c'est voulu."""
    assert mesure["bit_diff"] == 0, (
        f"{mesure['bit_diff']} ligne(s) differencient 69 et 1030 alors que seul le bit "
        "TargetMatchesDynamicRule les separe : la regle dynamique semble portee -> re-mesurer, "
        "la table par type devient alors OBSERVABLE sur cinq types de plus")
