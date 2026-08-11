"""#931 -- GARDE LIVE du passif `TwistedScience` (`genesBiophagus` "Hollan"), face COMBAT.

Le probe `probe_931_twisted_science.py` MESURE ; ce fichier ASSERTE. Chaque test rejoue UNE phase
du probe, sur son propre montage, et exige l'accord avec l'oracle NATIF :

  [swap]   `...TwistedScienceAbility$$CreateBehaviour` = `RemoveActiveAbility(Owner, 18 Heal) &
           AddActiveAbility(Owner, 1167 Heal_TwistedScience)`. L'assertion est CROISEE : Hollan a
           1167 et PAS 18, `ultraApothecary` (MEME trait `Healer`, PAS le passif) a 18 et PAS 1167.
           C'est ce releve qui etablit que le port n'a PAS a rejouer le swap -- il charge un etat ou
           le natif l'a deja fait.
  [gates]  l'ORACLE NATIF `abilityTargets(...).fromHere` == le verdict du port, AVANT et APRES un
           marquage. Il DISCRIMINE : l'ensemble natif PASSE de {83, 85} a {85}.
  [meca]   un allie MECANIQUE et un allie ELOIGNE sont exclus des DEUX cotes -- sans eux, le
           premier gate (`IsAffectedByHealType`) et la PORTEE ne sont jamais exerces (mesure : les
           mutants M7 et M12 passaient VERTS).
  [cast]   cible a PV PLEINS, deux bras : `Genestealers` (1355 + 1356) et NON (1355 seul). Le
           second est le contre-temoin du gate de FACTION.
  [blesse] cible BLESSEE -- le SEUL regime ou le `Heal` final est clampe, donc le seul qui exige
           que le stat-mod 1355 ait releve `get_CurrentMaximumValue()` AVANT lui. Mesure de
           reference : 1000 -> 7606 des deux cotes ; sans `applied_stat_mods` sur la classe
           d'effet, le port s'arretait a 6023.
  [self]   Hollan BLESSE se cible lui-meme : le natif le SOIGNE et ne lui pose AUCUN des deux
           effets (`NOT get_OwnerIsTarget`). Regime CONSTRUIT -- a PV pleins le self-cast est
           refuse, donc ce terme ne s'exerce pas.
  [pauvre] attaque de Hollan ecrasee (`HealAmount` << `hp`) : le seul regime qui SEPARE le
           `ChangeStat` du `Heal`, les deux se confondant au regime nominal.
  [dmg]    l'effet 1356 rend `ForAddition(extraDmg[level] x mult)` sur les DEUX voies d'arrivee
           (pose offline et seed live), au multiplicateur du POSEUR -- le montage descend celui de
           la cible a 100 pour casser le regime degenere du runner normalise.

Chaque test monte et DISPOSE son propre runner (les phases ont des montages differents : patch de
PV, patch d'attaque, patch de multiplicateur, `--place`). ASCII only."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

#: #486-r15 -- les chemins dont une modification DOIT rejouer ce fichier. Perimetre pris LARGE :
#: l'accord depend de la classe d'ability et de son arbre, des DEUX classes d'effet, des deux
#: registres, du gate de ciblage et de ses helpers, et de toute la chaine qui porte un stat-mod
#: HEALTH jusqu'au plafond de PV (c'est elle que la phase `blesse` mesure).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/probe_931_twisted_science.py",
        "scripts/python/engine/runner/abilities/genestealer.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/runner/abilities/attack_query.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/operations/stat_ops.py",
        "scripts/python/engine/runner/operations/heal.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/effects/loki/twisted_science.py",
        "scripts/python/engine/entities/effects/loki/extra_damage.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/predict.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Live : monte huit runners (un par phase, les montages different -- patch de PV, "
              "d'attaque, de multiplicateur, `--place`) et confronte la face COMBAT de 1167 a ses "
              "oracles NATIFS : inventaire d'abilities (le SWAP du passif), "
              "`abilityTargets.fromHere` (les deux gates), et les PV + effets apres cast. Toute "
              "modification de l'ability, d'une des deux classes d'effet, d'un registre, du gate "
              "de ciblage ou de la chaine stat-mod HEALTH -> plafond peut deplacer l'accord.",
}

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_931_twisted_science as P                             # noqa: E402


@pytest.fixture(scope="module")
def sid931():
    return P._resolve_session()


def _play(sid, tmp_path_factory, nom: str, fn) -> bool:
    """Joue UNE phase sur un state-file dedie (chemin ABSOLU, nom unique) et rend son verdict.
    La phase DISPOSE elle-meme son runner (chaque `phase_*` a son `finally`)."""
    state = tmp_path_factory.mktemp("st931-%s" % nom) / ("st-931-%s.json" % nom)
    return bool(fn(sid, state))


def test_swap_ability_18_remplacee_par_1167(sid931, tmp_path_factory):
    """Le passif RETIRE `18 Heal` et AJOUTE `1167 Heal_TwistedScience` -- assertion CROISEE avec
    `ultraApothecary`, qui porte le MEME trait `Healer` sans le passif."""
    assert _play(sid931, tmp_path_factory, "swap", P.phase_swap), (
        "l'inventaire natif d'abilities ne montre plus le swap 18 -> 1167 sur genesBiophagus, ou "
        "le contre-temoin ultraApothecary a cesse de porter 18")


def test_gates_accord_avec_from_here(sid931, tmp_path_factory):
    """`abilityTargets.fromHere` == `get_invalid_target_reason == 0`, AVANT et APRES marquage."""
    assert _play(sid931, tmp_path_factory, "gates", P.phase_gates), (
        "le gate dynamique du port diverge de l'oracle natif : soit la clause 'allie non marque = "
        "legal meme a PV pleins', soit le refus de la cible deja marquee")


def test_gates_machine_et_hors_portee_exclues(sid931, tmp_path_factory):
    """Le PREMIER gate (`IsAffectedByHealType`) et la PORTEE, chacun exerce par une unite dediee."""
    assert _play(sid931, tmp_path_factory, "meca", P.phase_meca), (
        "un allie MECANIQUE ou un allie ELOIGNE n'est plus exclu du meme cote que le natif")


def test_cast_pv_pleins_les_deux_bras(sid931, tmp_path_factory):
    """PV et effets poses, port == natif, sur une cible Genestealers et une cible qui ne l'est pas."""
    assert _play(sid931, tmp_path_factory, "cast", P.phase_cast), (
        "le cast diverge du natif : PV finaux, ou l'ensemble des effets poses (1356 ne doit aller "
        "qu'a une cible de faction Genestealers)")


def test_cible_blessee_le_plafond_est_releve_avant_le_soin(sid931, tmp_path_factory):
    """La chaine `AddDynamicStatModifierEffect(1355, Health)` -> `HealthComponent.modify_max` ->
    plafond du `Heal`. Sans elle : 6023 au lieu de 7606 (mesure du 2026-08-11)."""
    assert _play(sid931, tmp_path_factory, "blesse", P.phase_blesse), (
        "le soin d'une cible BLESSEE ne rend plus le montant natif -- typiquement le stat-mod 1355 "
        "n'atteint plus `get_CurrentMaximumValue()` avant le Heal")


def test_self_cast_soigne_sans_buffer(sid931, tmp_path_factory):
    """`NOT get_OwnerIsTarget` : Hollan blesse se soigne SANS recevoir 1355 ni 1356."""
    assert _play(sid931, tmp_path_factory, "self", P.phase_self), (
        "le self-cast pose des effets que le natif ne pose pas (terme `!OwnerIsTarget` du gate de "
        "buff), ou le montant du soin diverge")


def test_change_stat_separe_du_heal(sid931, tmp_path_factory):
    """Attaque ecrasee : le delta natif vaut EXACTEMENT `+hp`, jamais `+HealAmount`."""
    assert _play(sid931, tmp_path_factory, "pauvre", P.phase_pauvre), (
        "au regime `HealAmount << hp`, le port ne rend plus le meme delta que le natif -- le "
        "`ChangeStat` de PV COURANTS est en cause")


def test_effet_1356_magnitude_et_canal(sid931, tmp_path_factory):
    """`ForAddition(extraDmg[level] x mult du POSEUR)`, sur les DEUX voies d'arrivee de l'effet."""
    assert _play(sid931, tmp_path_factory, "dmg", P.phase_dmg), (
        "l'effet 1356 ne rend plus `extraDmg` au multiplicateur du POSEUR sur le canal Addition, "
        "ou il est arrive sur une unite que le gate de faction devait exclure")
