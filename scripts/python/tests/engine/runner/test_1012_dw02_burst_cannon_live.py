"""CLIQUET #1012 -- la relique `Dw02AdvancedBurstCannon` (`TriggeredAbilityType` 1476).

CRITERE : << le porteur gagne-t-il `extraPierceRatio[niveau de RELIQUE]` d'`ExtraPierce` a CHAQUE
attaque, les perd-il TOUTES a la `nrOfAttacks`-ieme (et pas a la suivante), son ability ACTIVE
redevient-elle utilisable DANS CETTE MEME attaque -- et le port fait-il pareil ? >>

Le montage est IMPORTE du probe (`probe_1012_dw02_burst_cannon.py`, foyer `flags_de_build`) au lieu
d'etre re-transcrit : un montage duplique derive de son original sans que rien ne le signale. Les
SEQUENCES ATTENDUES viennent elles aussi du probe (`attendus`), derivees du RE.

TROIS bras :
  1. NOMINAL (niveau 3 : `extraPierceRatio = 4`, `nrOfAttacks = 8`) -- LIVE == OFFLINE == ATTENDU,
     sur les DEUX canaux (percage ET etat de l'active). Le niveau 3 est choisi parce qu'il SEPARE le
     palier tertiaire du palier CLAMPE (le dernier vaut `(6, 7)`) : un port qui lirait le niveau
     PASSIF se trahirait sur les DEUX variables ;
  2. NIVEAU6 (niveau 6 : `extraPierceRatio = 5`, `nrOfAttacks = 7`) -- `nrOfAttacks` change de
     palier au 6e cran, donc ce bras DEPLACE le reset : ni un port au mauvais niveau ni un port au
     mauvais seuil ne le reproduisent par hasard ;
  3. SPECTATEUR -- la relique reste sur le porteur, qui n'attaque PAS ; c'est une SECONDE unite de
     mon camp qui frappe. Le gate `get_OwnerIsCaster` doit fermer les DEUX canaux : percage NUL et
     active JAMAIS re-armee. C'est le SEUL bras qui exerce ce gate, le regime nominal ayant
     porteur == attaquant par construction.
  + MUTANTS -- six/sept mutations du port, chacune avec son verdict ATTENDU sur CHACUN des deux
    canaux.

⚠ TROIS PIECES DU MONTAGE ECHOUENT EN SILENCE, et les trois sont gardees dans `stage` :
  * les trois ecritures de la relique (#237) -- `TertiaryAbility`, la config d'ability, et
    `TertiaryAbilityLevel >= 1` : DEUX d'entre elles echouent SANS erreur. La garde LIT l'entree
    `unitAbilityStates.triggered` dont `raw[0] == 1476` ET `raw[10] == 3` (hierarchie TERTIAIRE) ;
  * `my_player` derive de la premiere unite vivante du `decisionView` peut etre celui de la CIBLE :
    l'attaque part alors, rend `ok: true` et ne mute RIEN ;
  * dans le bras SPECTATEUR, si l'ATTAQUANT portait lui aussi la relique, le gate qu'on croit
    exercer serait satisfait par lui-meme -- controle NEGATIF explicite.

⚠ LA SERIE SE JOUE A DISTANCE, ET C'EST UNE MESURE. Au CONTACT, l'arme de melee du porteur est
`Flame` + trait `OnFire`, dont la composante en POURCENTAGE des PV MAX (`0,20 x maxHP`, deux points
mesures a 900k et 9M) tue la cible-sac a la 6e action QUELS QUE SOIENT ses PV -- monter `--hp-target`
ne sauve rien. A distance 2 l'arme est `Pulse` (aucun trait) : ~8 500 par action. Le `CreateTrigger`
de la relique ne porte AUCUN gate de nature de coup, donc ce choix ne touche aucun etage mesure.

⚠ L'ACTIVE DU PORTEUR N'EST PAS UNE ATTAQUE (elle summone des drones + Overwatch) : elle est castee
HORS SERIE, dans `stage`, contrairement a #916 dont le cast d'active EST offensif et COMPTE dans le
decompte. La consommer est ce qui rend `ResetActiveAbility` observable
(`BattleQuery$$EntityCanHaveActiveAbilityReset` refuse de re-armer une active deja utilisable).

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

from probe_1012_dw02_burst_cannon import (  # noqa: E402
    ABILITY_ID, ATTACKER_ALT, CARRIER, EXTRA_PIERCE_KEY, NR_OF_ATTACKS_KEY, TARGET,
    Live, attaquant_de, attendus, flags_de_build, mutants_pour, p_units_de, paliers,
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
        # classe d'effet EMPILABLE sont l'objet meme du cliquet ; le vecteur `On(9)` est ce qui les
        # appelle ; les feuilles DSL touchees sont celles dont un changement deplacerait la sequence.
        "scripts/python/probe_1012_dw02_burst_cannon.py",
        "scripts/python/engine/runner/operations/triggers/loki/dw02_advanced_burst_cannon.py",
        "scripts/python/engine/entities/effects/loki/dw02_advanced_burst_cannon.py",
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
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/behaviours/persistent_data.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/ability_state.py",
        "scripts/python/engine/runner/operations/ability_reset.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il confronte au natif la SEQUENCE de percage et l'etat de l'active sur un cycle "
              "complet de la relique : le montage (probe), l'arbre DSL et son seuil, la classe "
              "d'effet EMPILABLE, le vecteur `On(9)`, le foyer du niveau TERTIAIRE et les cinq "
              "feuilles DSL de l'arbre.",
}

_P_PIERCE = paliers(EXTRA_PIERCE_KEY)
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
    ep, nr = _P_PIERCE[level - 1], _P_ATK[level - 1]
    n = nr + 2                       # deux actions APRES le reset -> le cycle doit REPARTIR
    nat_p, nat_u = serie_live(live, rec, n)
    off_p, off_u = serie_offline(live.board, rec, n)
    vues = {nom: serie_offline(live.board, rec, n, mutant=nom)
            for nom, _, _ in mutants_pour(bras, level, _P_PIERCE, _P_ATK,
                                          active_armee=rec["active_armee"])}
    att_p, att_u = attendus(bras, ep, nr, n, socle=rec["pierce0"],
                            active_armee=rec["active_armee"])
    return {"rec": rec, "ep": ep, "nr": nr, "n": n, "nat": (nat_p, nat_u), "off": (off_p, off_u),
            "att": (att_p, att_u), "vues": vues, "bras": bras, "level": level}


def _verifie_mutants(m):
    for nom, mord_p, mord_u in mutants_pour(m["bras"], m["level"], _P_PIERCE, _P_ATK,
                                            active_armee=m["rec"]["active_armee"]):
        mut_p, mut_u = m["vues"][nom]
        assert (mut_p != m["off"][0]) is mord_p, (
            "mutant %s : le canal PERCAGE doit %s (mut=%s off=%s)"
            % (nom, "MORDRE" if mord_p else "se TAIRE", mut_p, m["off"][0]))
        assert (mut_u != m["off"][1]) is mord_u, (
            "mutant %s : le canal ACTIVE doit %s (mut=%s off=%s)"
            % (nom, "MORDRE" if mord_u else "se TAIRE", mut_u, m["off"][1]))


@pytest.mark.parametrize("bras,level", [("NOMINAL", 3), ("NIVEAU6", 6)])
def test_la_pile_de_percage_monte_puis_se_vide_a_la_n_ieme_attaque(charge_regime, bras, level):
    """`If( GetPersistentData >= Subtract(ConfigVar(nrOfAttacks), <DSLFormulas+0x20> = Direct(1)),
            (RemoveEffect(1470) & ResetActiveAbility) & ClearPersistentData,
            AddStaticStatModifierEffect(1470, ExtraPierce, ConfigVar(extraPierceRatio))
              & AddPersistentData(+1) )`

    Le bras NIVEAU6 n'est pas un doublon : `nrOfAttacks` passe de 8 a 7 au 6e palier, donc il
    deplace le RESET -- ce que ni un port au mauvais niveau ni un port au mauvais seuil ne peuvent
    reproduire par hasard."""
    m = _mesure(charge_regime, bras, level)
    nat_p, nat_u = m["nat"]
    off_p, off_u = m["off"]
    att_p, att_u = m["att"]
    assert nat_p == att_p, (
        "le NATIF ne suit pas le RE : %s != %s (extraPierceRatio=%d nrOfAttacks=%d). Le maximum "
        "doit etre (N-1) x extraPierceRatio et le reset tomber a la N-ieme action."
        % (nat_p, att_p, m["ep"], m["nr"]))
    assert off_p == nat_p, "percage : port %s != natif %s" % (off_p, nat_p)
    assert att_u is not None, (
        "le canal ACTIVE n'a pas ete arme (cast de l'active refuse) : ce test ne mesurerait plus "
        "le `ResetActiveAbility` de la branche THEN")
    assert nat_u == att_u, (
        "l'active du porteur doit redevenir utilisable EXACTEMENT a la %d-ieme action, DANS "
        "l'attaque (pas a la fin de phase) : %s != %s" % (m["nr"], nat_u, att_u))
    assert off_u == nat_u, "active : port %s != natif %s" % (off_u, nat_u)
    _verifie_mutants(m)


def test_un_porteur_SPECTATEUR_ne_gagne_aucun_percage_et_ne_rearme_pas_son_active(charge_regime):
    """`get_OwnerIsCaster` -- le SEUL gate que le regime nominal n'exerce PAS (le porteur y est
    toujours l'attaquant).

    La relique est sur `%s`, qui n'attaque pas ; c'est `%s` -- SANS relique -- qui frappe. Le porteur
    ne doit gagner AUCUN percage ET son active ne doit JAMAIS redevenir utilisable ; le mutant
    `OWNERISCASTER_OFF` doit alors MORDRE sur les DEUX canaux : sans ce gate, toute unite du board
    portant la relique se bufferait sur l'attaque d'un tiers.""" % (CARRIER, ATTACKER_ALT)
    m = _mesure(charge_regime, "SPECTATEUR", 3)
    rec = m["rec"]
    assert attaquant_de("SPECTATEUR") == ATTACKER_ALT and rec["porteur"] != rec["att"], (
        "le montage n'a pas separe le porteur de l'attaquant : %s"
        % ({k: v for k, v in rec.items() if k != "snapshot"},))
    nat_p, nat_u = m["nat"]
    off_p, off_u = m["off"]
    att_p, att_u = m["att"]
    assert nat_p == att_p, (
        "le NATIF donne du percage a un porteur qui n'attaque pas : %s" % (nat_p,))
    assert off_p == nat_p, "percage : port %s != natif %s" % (off_p, nat_p)
    assert att_u is not None and nat_u == att_u, (
        "l'active d'un porteur qui n'attaque pas ne doit JAMAIS etre re-armee : %s != %s"
        % (nat_u, att_u))
    assert off_u == nat_u, "active : port %s != natif %s" % (off_u, nat_u)
    _verifie_mutants(m)


def test_le_montage_de_la_relique_est_bien_le_canal_TERTIAIRE(charge_regime):
    """Garde de MONTAGE explicite -- `stage` leve si la relique n'est pas montee en hierarchie 3,
    mais rien ne dit qu'un futur refactor gardera cette levee. Ici on le VERIFIE, et on verifie
    aussi que le port LIT ce niveau-la : `relic_vars` doit rendre le palier du niveau EQUIPE, pas
    le dernier (qui est ce que rendrait le niveau des PASSIFS)."""
    from engine.runner.snapshot import load_state
    import engine.runner.operations.triggers.loki.dw02_advanced_burst_cannon as DW
    level = 3
    h = charge_regime(p_units=p_units_de("NOMINAL"), a_units=TARGET, seed="777", board="MC1_67",
                      extra=flags_de_build("NOMINAL", level))
    live = Live(h.rpc, h.rid, h.board)
    rec = stage(live, "NOMINAL", level)             # leve si la hierarchie n'est pas 3
    s = rec["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=live.board)
    ep, nr = DW.relic_vars(st, rec["porteur"])
    assert (ep, nr) == (_P_PIERCE[level - 1], _P_ATK[level - 1]), (
        "le port lit (%d, %d) au lieu du palier %d (%d, %d) -- il lit le mauvais AbilityState"
        % (ep, nr, level, _P_PIERCE[level - 1], _P_ATK[level - 1]))
    assert ep != _P_PIERCE[-1] and nr != _P_ATK[-1], (
        "niveau %d : (%d, %d) coincide avec le DERNIER palier (%d, %d) -- ce test ne discriminerait "
        "pas le repli PASSIF (qui clampe au dernier)"
        % (level, ep, nr, _P_PIERCE[-1], _P_ATK[-1]))
    assert DW.ABILITY_ID == ABILITY_ID == "Dw02AdvancedBurstCannon"
