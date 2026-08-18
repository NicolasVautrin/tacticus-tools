"""#1081 -- cliquet OFFLINE de la tranche de BLOCAGE du foyer `entities/effects/factory.py`.

Trois etages, et chacun garde un resultat DIFFERENT de la tranche :

  [1] le PROBE de premisses rend `rc 0` -- c'est lui qui confronte le champ `BLOCAGE:` ecrit dans
      `docs/rl/backlog.md` a ce que le code MESURE. Il rougit des qu'un champ se perime, ce qui
      est le mode de panne que la tranche a trouve (2 champs sur 10 l'etaient).

  [2] `MischiefMakers` (`EffectType` 1469) est au registre ET derive de `HealBlockingEffect` --
      les deux, parce qu'une entree au registre pointant une classe qui ne derive PAS de la base
      ne bloquerait AUCUN soin, silencieusement (`attack_query.has_heal_blockers` teste
      `isinstance`, pas la presence au registre).

  [3] `MachineVengeance` (`EffectType` 1365) rend `+5 % PAR NIVEAU` de pile, avec ses quatre
      etages SEPARABLES. Le cran qui compte n'est pas la valeur : c'est que le TRI-ETAT tienne
      (`level = None` ne doit JAMAIS se lire comme `level = 0`) et que la constante vienne de
      `BC.Effect`, jamais d'un litteral.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

#: `<depot>/scripts/python` -- ce fichier vit dans `scripts/python/tests/engine/`, donc DEUX
#: niveaux au-dessus. (Le derivant de la racine du depot, on obtenait `scripts/scripts/python`.)
PY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PY))

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # L'etage [1] SOUS-PROCESSUS le probe : il n'entre donc PAS par la fermeture d'imports,
        # et c'est exactement le cas qu'un declencheur derive ne peut pas voir.
        "scripts/python/probe_1081_premisses_foyer_factory.py",
        # #1084 -- le PARSEUR AUTORITAIRE du champ. L'etage [1] le sous-processe, et le cran de
        # temoin derive le SUBSTITUE : ses deux marqueurs de champ decident a eux seuls si le
        # cliquet lit le champ ou une bribe de prose.
        "scripts/python/backlog_entries.py",
        # ENTREES LUES AU TEXTE par ce probe, qu'aucun import ne revele : le backlog (les champs
        # `BLOCAGE:` des dix fiches -- l'etage [1] rougit des qu'un mot y change), et les trois
        # fichiers que l'inventaire mesure par SIGNATURE ou par presence d'une cle de contexte.
        "docs/rl/backlog.md",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/probe_961_necron_passives.py",
    ),
    "build": False,   # aucune lecture du binaire ni de `data/symbols/**`
    "toujours": False,
    "raison": (
        "CES chemins parce qu'ils sont les seuls a echapper a la cascade DERIVEE (#531) : "
        "`probe_486r15 --proposer` mesure que la fermeture d'imports de ce fichier y tient "
        "ENTIEREMENT, donc declarer `factory.py`, `machine_vengeance.py`, `heal_blocking.py` ou "
        "`effect_bonus.py` serait redondant -- les etages [2] et [3] les atteignent par import. "
        "Ce qui n'y est PAS : le probe de l'etage [1], lance en SOUS-PROCESSUS, et les fichiers "
        "qu'il lit au TEXTE (le backlog, dont un champ `BLOCAGE:` modifie change le verdict sans "
        "qu'aucun module bouge ; les deux modules dont il teste la SIGNATURE ou une cle ; et "
        "`probe_961_necron_passives.py`, dont il cherche le drapeau `includeInactive`). "
        "PAS `toujours: True` : ce fichier ne mesure aucune propriete globale de l'arbre."
    ),
}


# --------------------------------------------------------------------------- [1] le probe

def test_1081_le_probe_de_premisses_est_vert():
    """Le champ `BLOCAGE:` de chacun des dix residus concorde avec la mesure.

    Un champ perime ECARTE le residu au dispatch (`capteur` / `porteur` / `etage` sont filtres),
    donc il le rend INDISPATCHABLE EN SILENCE -- pire que son absence, puisque personne ne relit
    un champ qui a l'air rempli."""
    r = subprocess.run([sys.executable, "probe_1081_premisses_foyer_factory.py"],
                       cwd=str(PY), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (
        "probe_1081 ROUGE (rc=%s) -- un champ BLOCAGE ne dit plus ce que le code mesure :\n%s"
        % (r.returncode, r.stdout[-3000:]))
    # Le probe doit avoir REELLEMENT compare : un recenseur muet passerait pour vert.
    assert "ETAGE 3" in r.stdout and "temoin parseur" in r.stdout, \
        "le probe n'a pas joue son etage de confrontation :\n%s" % r.stdout[-1500:]


def test_1081_le_temoin_de_parseur_est_DERIVE_et_MORD(monkeypatch):
    """#1084 -- LE TEMOIN N'EST PLUS UN COUPLE FIGE, ET LA MUTATION LE MONTRE.

    L'ancien temoin nommait `#943-r7` avec le mot `seeding` ; la fiche a ete resolue trois jours
    plus tard et son champ est passe a `aucun` -- le cliquet rougissait donc sur un MOUVEMENT
    LEGITIME du backlog, pas sur le vice qu'il garde. Le temoin derive, lui, tient tant qu'une
    entree cite l'etiquette en prose.

    On verifie DEUX choses : (a) le gisement de temoins est NON VIDE et DISCRIMINE ; (b) en
    remettant le deux-points OPTIONNEL dans `backlog_entries` -- l'etat d'avant #1084 -- des champs
    HORS VOCABULAIRE reapparaissent, c'est-a-dire que ce cran MORD pour de vrai."""
    import re

    import backlog_entries as B
    import probe_1081_premisses_foyer_factory as P

    _, entrees = P._lire_backlog()
    temoins = P.temoins_de_parseur(entrees)
    assert temoins, ("gisement de temoins VIDE : plus aucune entree ne cite l'etiquette `BLOCAGE` "
                     "en prose -- le cran ne mesure plus rien, le re-ancrer")
    hors = [(e.ident, e.blocage) for e in temoins
            if e.blocage is not None and e.blocage not in B.BLOCAGES]
    assert not hors, "champ(s) hors vocabulaire rendus par le parseur AUTORITAIRE : %r" % (hors,)
    discriminants = [e for e in temoins if P._lecture_naive(e.brut) != (e.blocage or None)]
    assert discriminants, ("temoin DEGENERE : la lecture naive rend partout la meme chose que le "
                           "parseur, donc ce cran passerait aussi sur un parseur casse")

    # (b) LA MUTATION -- le regime d'AVANT #1084 (`:` optionnel).
    monkeypatch.setattr(B, "_MARQ_FOYER", re.compile(r"\*{0,2}FOYER\s*:?\*{0,2}"))
    monkeypatch.setattr(B, "_MARQ_BLOCAGE", re.compile(r"\*{0,2}BLOCAGE\s*:?\*{0,2}"))
    _, mutees = P._lire_backlog()
    hors_mute = [(e.ident, e.blocage) for e in P.temoins_de_parseur(mutees)
                 if e.blocage is not None and e.blocage not in B.BLOCAGES]
    assert hors_mute, (
        "sous la mutation << deux-points OPTIONNEL >>, AUCUN champ hors vocabulaire ne "
        "reapparait : ce cran ne garde donc pas ce qu'il pretend garder. (Il en rendait 4 le "
        "2026-08-18 : RE x2, RETIRES, sont.)")


# --------------------------------------------------------------------------- [2] MischiefMakers

def test_1081_mischief_makers_est_au_registre_ET_derive_de_la_base():
    from engine.entities.effects import factory as F
    from engine.entities.effects.loki.heal_blocking import HealBlockingEffect

    cls = F.EFFECT_CLASSES.get("MischiefMakers")
    assert cls is not None, (
        "1469 MischiefMakers a quitte EFFECT_CLASSES -- un de ses porteurs "
        "(deathNpc3Nurglings, deathSmnNurglings) redeviendrait soignable cote port")
    assert issubclass(cls, HealBlockingEffect), (
        "l'entree existe mais ne derive pas de HealBlockingEffect : `has_heal_blockers` teste un "
        "`isinstance`, donc le blocage serait INERTE sans qu'aucune entree ne manque")


def test_1081_les_deux_porteurs_de_heal_blocking_sont_distincts_et_presents():
    """Les DEUX sous-classes vivent, et ne se confondent pas.

    Sans ce cran, remplacer l'une par l'autre au registre resterait vert (les deux derivent de la
    meme base) alors que l'un des deux effets ne serait plus jamais materialise."""
    from engine.entities.effects import factory as F

    fury = F.EFFECT_CLASSES.get("FuryOfTheAncients")
    mischief = F.EFFECT_CLASSES.get("MischiefMakers")
    assert fury is not None and mischief is not None
    assert fury is not mischief, "les deux entrees pointent la MEME classe"
    assert {fury.__name__, mischief.__name__} == {"FuryOfTheAncientsEffect", "MischiefMakersEffect"}


# --------------------------------------------------------------------------- [3] MachineVengeance

def _mv(level):
    from engine.entities.effects.loki.machine_vengeance import MachineVengeanceEffect
    e = MachineVengeanceEffect("MachineVengeance")
    e.level = level
    return e


CTX = {"owner_id": 7, "att_id": 7}


def test_1081_machine_vengeance_est_au_registre():
    from engine.entities.effects import factory as F
    from engine.entities.effects.loki.machine_vengeance import MachineVengeanceEffect
    assert F.EFFECT_CLASSES.get("MachineVengeance") is MachineVengeanceEffect


def test_1081_machine_vengeance_ne_derive_PAS_de_heal_blocking():
    """Sa voisine immediate au registre en derive, elle NON -- `frida/classes.tsv` le dit
    (`MachineVengeanceEffect -> BaseEffect`). L'y rattacher bloquerait des soins que le natif
    autorise : degradation RESTRICTIVE, celle qui se voit le moins en self-play."""
    from engine.entities.effects.loki.heal_blocking import HealBlockingEffect
    from engine.entities.effects.loki.machine_vengeance import MachineVengeanceEffect
    assert not issubclass(MachineVengeanceEffect, HealBlockingEffect)


@pytest.mark.parametrize("level,attendu", [(1, 5), (2, 10), (3, 15), (10, 50)])
def test_1081_machine_vengeance_rend_5_pct_par_niveau(level, attendu):
    """`Multiply(Get(EffectConfig(7)), EffectLevel)` -- la LINEARITE est le mirror, pas la valeur.

    Tester plusieurs niveaux (et pas un seul) est ce qui distingue « le port multiplie » de « le
    port rend une constante qui se trouve juste au niveau teste »."""
    eb = _mv(level).create_effect_damage_bonus_for_attack(att_ctx=CTX)
    assert eb is not None and eb.kind == "PercentIncrease"
    assert eb.value == attendu, "niveau %d -> attendu +%d%%, lu %s" % (level, attendu, eb.value)


def test_1081_la_constante_vient_de_BC_Effect_pas_d_un_litteral():
    """La magnitude doit SUIVRE `BC.Effect["MachineVengeanceExtraPct"]`.

    On substitue la lecture de configuration et on verifie que la sortie bouge : sans ce cran, un
    `5` code en dur passerait tous les tests ci-dessus."""
    from engine.entities.effects.loki import machine_vengeance as MV

    reel = MV.bc_effect_config
    MV.bc_effect_config = lambda cle, defaut=None: 11 if cle == MV.EFFECT_CONFIG_KEY else reel(cle, defaut)
    try:
        eb = _mv(3).create_effect_damage_bonus_for_attack(att_ctx=CTX)
    finally:
        MV.bc_effect_config = reel
    assert eb is not None and eb.value == 33, (
        "la magnitude n'a pas suivi la config substituee (%s) -- la constante est ecrite en dur"
        % (eb.value if eb else None))
    # et la valeur REELLE du build reste celle qu'on croit
    assert reel(MV.EFFECT_CONFIG_KEY) == 5


def test_1081_le_niveau_non_mesure_ne_se_lit_PAS_comme_zero():
    """TRI-ETAT. `None` et `0` rendent tous deux « pas de bonus », donc l'erreur serait
    SILENCIEUSE ; ce qui la rend visible, c'est que `None` ne doit jamais etre CONVERTI en 0 en
    chemin (un `int(None or 0)` leverait ici)."""
    assert _mv(None).create_effect_damage_bonus_for_attack(att_ctx=CTX) is None
    assert _mv(0).create_effect_damage_bonus_for_attack(att_ctx=CTX) is None


def test_1081_le_gate_owner_is_caster_ecarte_un_autre_attaquant():
    assert _mv(3).create_effect_damage_bonus_for_attack(
        att_ctx={"owner_id": 7, "att_id": 9}) is None, \
        "l'effet a verse son bonus a une unite qui ne le porte pas"


def test_1081_le_gate_reste_STRUCTUREL_quand_l_identite_n_est_pas_mesuree():
    """Contre-epreuve du test precedent : sans identites dans le contexte, le canal ne doit PAS se
    fermer -- il n'est parcouru que pour l'attaque du porteur, et fermer ici rendrait l'effet
    INERTE dans tous les appelants qui ne threadent pas `owner_id`."""
    eb = _mv(3).create_effect_damage_bonus_for_attack(att_ctx=None)
    assert eb is not None and eb.value == 15


def test_1081_aucun_gate_de_nature_de_coup_n_a_ete_invente():
    """Le natif n'ecrit NI `IsRangedAttack`, NI `IsNormalAttack`, NI `DamageProfileIs`.

    Le port recoit ces parametres et doit les IGNORER : un gate invente serait plus grave qu'une
    absence, parce qu'il eteindrait le bonus dans un regime ou le natif le verse."""
    ref = _mv(4).create_effect_damage_bonus_for_attack(att_ctx=CTX).value
    for kw in ({"is_ranged": True}, {"is_ranged": False}, {"is_normal_attack": False},
               {"has_moved": True}, {"target_armor_reduced": True},
               {"target_traits": frozenset({"Hero"})}, {"is_prediction": True}):
        eb = _mv(4).create_effect_damage_bonus_for_attack(att_ctx=CTX, **kw)
        assert eb is not None and eb.value == ref, \
            "un gate a ete introduit sur %s : %s au lieu de %s" % (kw, eb and eb.value, ref)
