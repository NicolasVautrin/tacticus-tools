"""CLIQUET #916 -- la relique `DaemonfleshPlate` (`TriggeredAbilityType` 1493).

CRITERE : << le porteur gagne-t-il `extraArmor[niveau de RELIQUE]` de `FixedArmor` a CHAQUE attaque,
les perd-il TOUTES a la `nrOfAttacks`-ieme (et pas a la suivante), et son ability ACTIVE
redevient-elle utilisable a ce moment-la -- et le port fait-il pareil ? >>

Le montage est IMPORTE du probe (`probe_916_daemonflesh_plate_live.py`, foyer `flags_de_build`) au
lieu d'etre re-transcrit : un montage duplique derive de son original sans que rien ne le signale.
Les SEQUENCES ATTENDUES viennent elles aussi du probe (`attendus`), derivees du RE.

QUATRE bras :
  1. NOMINAL (niveau 1 : `extraArmor = 145`, `nrOfAttacks = 8`) -- LIVE == OFFLINE == ATTENDU, sur
     les DEUX canaux (armure ET etat de l'active) ;
  2. NIVEAU6 (niveau 6 : `extraArmor = 184`, `nrOfAttacks = 7`) -- il discrimine DEUX choses d'un
     coup : le PALIER de `nrOfAttacks` (la seule variable de la relique qui change de palier) et le
     fait que le niveau lu est bien le TERTIAIRE. Un port qui lirait le niveau PASSIF (50 sur tout
     runner normalise) rendrait le DERNIER palier dans les deux bras ;
  3. SPECTATEUR -- la relique est sur une SECONDE unite de mon camp, qui n'attaque PAS. Le gate
     `get_OwnerIsCaster` doit fermer le canal : armure NULLE. C'est le SEUL bras qui exerce ce gate,
     le regime nominal ayant porteur == attaquant par construction ;
  4. MUTANTS -- sept mutations du port, chacune avec son verdict ATTENDU sur CHACUN des deux canaux.

⚠ TROIS PIECES DU MONTAGE ECHOUENT EN SILENCE, et les trois sont gardees dans `stage` :
  * les trois ecritures de la relique (#237) -- `TertiaryAbility`, la config d'ability, et
    `TertiaryAbilityLevel >= 1` : DEUX d'entre elles echouent SANS erreur. La garde LIT l'entree
    `unitAbilityStates.triggered` dont `raw[0] == 1493` ET `raw[10] == 3` (hierarchie TERTIAIRE) ;
  * `my_player` derive de la premiere unite vivante du `decisionView` peut etre celui de la CIBLE :
    l'attaque part alors, rend `ok: true` et ne mute RIEN ;
  * dans le bras SPECTATEUR, si l'ATTAQUANT portait lui aussi la relique, le gate qu'on croit
    exercer serait satisfait par lui-meme -- controle NEGATIF explicite.

⚠ LE CAST D'UNE ABILITY OFFENSIVE COMPTE COMME UNE ATTAQUE. `On(9 = Attack)` est l'evenement
GENERIQUE de fin d'attaque (`FinishAttackOperation`), emis pour l'attaque normale COMME pour une
ability. La serie ouvre donc par le cast de l'active du porteur -- c'est lui qui la CONSOMME, donc
qui rend le volet `DaemonfleshPlate_ResetActiveAbility` observable -- et ce cast COMPTE dans le
decompte. Le traiter comme << hors serie >> decalerait l'attendu d'un cran.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

from probe_916_daemonflesh_plate_live import (  # noqa: E402
    ABILITY_ID, CARRIER, EXTRA_ARMOR_KEY, NR_OF_ATTACKS_KEY, SPECTATOR, TARGET,
    Live, attendus, flags_de_build, mutants_pour, p_units_de, paliers, porteur_de,
    serie_live, serie_offline, stage)

from _charge_regime import charge_regime  # noqa: E402,F401  (fixture)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test live : la cascade des `conftest.py` et le harnais.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/catalog_inject.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/rl_duel.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Le montage ET les attendus viennent du probe ; l'arbre DSL et la
        # classe d'effet EMPILABLE sont l'objet meme du cliquet ; les deux VECTEURS d'evenement
        # (`On(9)` et `On(0x3a)`) sont ce qui les appelle ; les feuilles DSL touchees sont celles
        # dont un changement deplacerait la sequence.
        "scripts/python/probe_916_daemonflesh_plate_live.py",
        "scripts/python/engine/runner/operations/triggers/loki/daemonflesh_plate.py",
        "scripts/python/engine/entities/effects/loki/daemonflesh_plate.py",
        # Le paquet `loki` est traverse par la fermeture d'imports (`factory` l'entre) : declare
        # explicitement, sinon `probe_486r15` rougit sur un DECLENCHEUR trop ETROIT.
        "scripts/python/engine/entities/effects/loki/__init__.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/runner/abilities/behaviours/persistent_data.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/ability_state.py",
        "scripts/python/engine/runner/operations/ability_reset.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/phase.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il confronte au natif la SEQUENCE d'armure et l'etat de l'active sur un cycle "
              "complet de la relique : le montage (probe), l'arbre DSL et son seuil, la classe "
              "d'effet EMPILABLE, les deux vecteurs d'evenement `On(9)`/`On(0x3a)`, le foyer du "
              "niveau TERTIAIRE et les cinq feuilles DSL de l'arbre.",
}

_P_ARMOR = paliers(EXTRA_ARMOR_KEY)
_P_ATK = paliers(NR_OF_ATTACKS_KEY)


def _mesure(charge_regime, bras, level, board="MC1_67", seed="777"):
    """Monte, joue la serie, rejoue offline -- et rend toutes les vues d'un coup. Toute
    impossibilite de MONTAGE LEVE (jamais un skip vert : un echec de montage parti en skip est un
    VERT QUI MENT)."""
    h = charge_regime(p_units=p_units_de(bras), a_units=TARGET, seed=seed, board=board,
                      extra=flags_de_build(bras, level))
    # `charge_regime` rend un harnais de CHARGE ; on ne lui emprunte que le runner et le board, le
    # pilotage de cette mecanique-ci vivant dans `Live` (foyer partage avec le probe).
    live = Live(h.rpc, h.rid, h.board)
    rec = stage(live, bras, level)
    ea, nr = _P_ARMOR[level - 1], _P_ATK[level - 1]
    n = nr + 2                       # deux actions APRES le reset -> le cycle doit REPARTIR
    actif = (bras != "SPECTATEUR")
    nat_a, nat_u = serie_live(live, rec, n, active_en_tete=actif)
    off_a, off_u = serie_offline(live.board, rec, n, active_consommee=actif)
    vues = {nom: serie_offline(live.board, rec, n, mutant=nom, active_consommee=actif)
            for nom, _, _ in mutants_pour(bras, level, _P_ARMOR, _P_ATK)}
    att_a, att_u = attendus(bras, ea, nr, n)
    return {"rec": rec, "ea": ea, "nr": nr, "n": n, "nat": (nat_a, nat_u), "off": (off_a, off_u),
            "att": (att_a, att_u), "vues": vues, "bras": bras, "level": level}


def _verifie_mutants(m):
    for nom, mord_a, mord_u in mutants_pour(m["bras"], m["level"], _P_ARMOR, _P_ATK):
        mut_a, mut_u = m["vues"][nom]
        assert (mut_a != m["off"][0]) is mord_a, (
            "mutant %s : le canal ARMURE doit %s (mut=%s off=%s)"
            % (nom, "MORDRE" if mord_a else "se TAIRE", mut_a, m["off"][0]))
        assert (mut_u != m["off"][1]) is mord_u, (
            "mutant %s : le canal ACTIVE doit %s (mut=%s off=%s)"
            % (nom, "MORDRE" if mord_u else "se TAIRE", mut_u, m["off"][1]))


@pytest.mark.parametrize("bras,level", [("NOMINAL", 1), ("NIVEAU6", 6)])
def test_la_pile_d_armure_monte_puis_se_vide_a_la_n_ieme_attaque(charge_regime, bras, level):
    """`If( GetPersistentData >= Subtract(ConfigVar(nrOfAttacks), Direct(1)),
            RemoveEffect(1490) & AddEffect(1491) & ClearPersistentData,
            AddStaticStatModifierEffect(1490, FixedArmor, ConfigVar(extraArmor)) & AddPersistentData(+1) )`

    Le bras NIVEAU6 n'est pas un doublon : `nrOfAttacks` passe de 8 a 7 au 6e palier, donc il
    deplace le RESET -- ce que ni un port au mauvais niveau ni un port au mauvais seuil ne peuvent
    reproduire par hasard."""
    m = _mesure(charge_regime, bras, level)
    nat_a, nat_u = m["nat"]
    off_a, off_u = m["off"]
    att_a, att_u = m["att"]
    assert nat_a == att_a, (
        "le NATIF ne suit pas le RE : %s != %s (extraArmor=%d nrOfAttacks=%d). Le maximum doit "
        "etre (N-1) x extraArmor et le reset tomber a la N-ieme action."
        % (nat_a, att_a, m["ea"], m["nr"]))
    assert off_a == nat_a, "armure : port %s != natif %s" % (off_a, nat_a)
    assert nat_u == att_u, (
        "l'active du porteur doit redevenir utilisable EXACTEMENT a la %d-ieme action : %s != %s"
        % (m["nr"], nat_u, att_u))
    assert off_u == nat_u, "active : port %s != natif %s" % (off_u, nat_u)
    _verifie_mutants(m)


def test_un_porteur_SPECTATEUR_ne_gagne_aucune_armure(charge_regime):
    """`get_OwnerIsCaster` -- le SEUL gate que le regime nominal n'exerce PAS (le porteur y est
    toujours l'attaquant).

    La relique est sur `%s`, qui n'attaque pas ; c'est `%s` -- SANS relique -- qui frappe. Le porteur
    ne doit gagner AUCUNE armure, et le mutant `OWNERISCASTER_OFF` doit alors MORDRE : sans ce gate,
    toute unite du board portant la relique se bufferait sur l'attaque d'un tiers.""" % (
        SPECTATOR, CARRIER)
    m = _mesure(charge_regime, "SPECTATEUR", 1)
    rec = m["rec"]
    assert rec["porteur_vis"] == SPECTATOR and rec["porteur"] != rec["att"], (
        "le montage n'a pas separe le porteur de l'attaquant : %s" % (rec,))
    nat_a, _ = m["nat"]
    off_a, _ = m["off"]
    att_a, _ = m["att"]
    assert nat_a == att_a, (
        "le NATIF donne de l'armure a un porteur qui n'attaque pas : %s" % (nat_a,))
    assert off_a == nat_a, "armure : port %s != natif %s" % (off_a, nat_a)
    _verifie_mutants(m)


def test_le_montage_de_la_relique_est_bien_le_canal_TERTIAIRE(charge_regime):
    """Garde de MONTAGE explicite -- `stage` leve si la relique n'est pas montee en hierarchie 3,
    mais rien ne dit qu'un futur refactor gardera cette levee. Ici on le VERIFIE, et on verifie
    aussi que le port LIT ce niveau-la : `relic_vars` doit rendre le palier du niveau EQUIPE, pas
    le dernier (qui est ce que rendrait le niveau des PASSIFS)."""
    from engine.runner.snapshot import load_state
    import engine.runner.operations.triggers.loki.daemonflesh_plate as DFP
    level = 3
    h = charge_regime(p_units=p_units_de("NOMINAL"), a_units=TARGET, seed="777", board="MC1_67",
                      extra=flags_de_build("NOMINAL", level))
    live = Live(h.rpc, h.rid, h.board)
    rec = stage(live, "NOMINAL", level)             # leve si la hierarchie n'est pas 3
    s = rec["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=live.board)
    ea, nr = DFP.relic_vars(st, rec["porteur"])
    assert (ea, nr) == (_P_ARMOR[level - 1], _P_ATK[level - 1]), (
        "le port lit (%d, %d) au lieu du palier %d (%d, %d) -- il lit le mauvais AbilityState"
        % (ea, nr, level, _P_ARMOR[level - 1], _P_ATK[level - 1]))
    assert ea != _P_ARMOR[-1], (
        "niveau %d : `extraArmor` y vaut deja le DERNIER palier, ce test ne discriminerait pas le "
        "repli PASSIF (qui clampe au dernier)" % level)
    assert porteur_de("NOMINAL") == CARRIER and ABILITY_ID == "DaemonfleshPlate"
