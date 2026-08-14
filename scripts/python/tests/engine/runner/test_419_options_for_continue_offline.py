"""GARDE #419-r1-tr14-r5-r2-r1-r2-r2 (OFFLINE PURE) -- le SECOND jeu d'options, celui qu'aucun
`$$.ctor` n'ecrit.

LE RESIDU, mot pour mot : << les masques recalcules HORS `.ctor` ne sont pas recenses --
`AActiveAbility$$GetTargetingOptionsForContinue` (et sa surcharge `GreatFrostAxeAbility`)
produisent le SECOND jeu d'options, loge a `this+0xb0`, qu'un recensement limite aux `$$.ctor` ne
voit pas >>. Il portait sur l'EXHAUSTIVITE du recensement, pas sur un ecart mesure : ce jeu-la est
hors du chemin du cast top-level (`b__0`), la lambda qui le lit est `b__1` (slot 0xe).

CE QUE CE FICHIER PROTEGE, et ce qu'il ne pretend pas :

  1. **L'EXHAUSTIVITE, et elle est DERIVEE du dump** -- pas d'une liste ecrite a la main. L'etage 1
     balaie `data/symbols/<build>/ghidra/functions.tsv` : toute classe portant un
     `$$GetTargetingOptionsForContinue` autre que la base DOIT etre recensee. Une surcharge NEUVE
     au prochain build fait ROUGIR. C'est ce cran-la qui ferme le residu -- la fiche n'en nommait
     qu'UNE (`GreatFrostAxe`), le dump en porte DEUX (`EntropyCannons` aussi).
  2. **LA LOI DE BASE**, VERBATIM : `rules |= AllowIgnoreForcedAttackTarget` et
     `forceMeleeTarget = RangedBool.False`, sur une COPIE (le jeu du ctor n'est pas mute).
  3. **LES DEUX SURCHARGES N'APPLIQUENT PAS CETTE LOI** : elles repartent d'un litteral et ignorent
     `this+0x70`. Le cran le plus discriminant est `EntropyCannons`, dont le second jeu DESARME
     `TargetMatchesDynamicRule` (`.ctor` = 0x40004002, continue = 0x40004000) : appliquer la loi de
     base a sa place donnerait un masque qui GARDE le bit -- l'erreur exacte que ce test attrape.

Ce fichier ne teste AUCUN chemin actif : le port n'a pas la face << continue >>. C'est assume et
ecrit dans le module.
ASCII only. Aucune VA en dur ; les symboles sont cites verbatim.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import symbols_layout                                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType        # noqa: E402
from engine.runner.abilities.targeting import (                          # noqa: E402
    RANGED_BOOL_FALSE, RANGED_BOOL_TRUE, TARGETING_OPTIONS_FOR_CONTINUE_OVERRIDES as OVERRIDES,
    TargetingOptions, targeting_options_for, targeting_options_for_continue)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15). PRIS LARGE : le
#: cran d'exhaustivite est DERIVE du dump de symboles -- un re-dump (changement de build) peut
#: introduire une surcharge neuve sans qu'aucune ligne de `scripts/python/**` ne bouge.
DECLENCHEUR = {
    "chemins": (
        "data/symbols/**/ghidra/functions.tsv",             # la source du balayage d'exhaustivite
        "scripts/python/symbols_layout.py",                 # la resolution du build courant
        "scripts/python/engine/runner/abilities/**/*.py",   # les masques de `.ctor` et le registre
        "scripts/python/engine/entities/active_ability_type.py",
    ),
    "build": True,        # l'etage 1 LIT `data/symbols/<build>/ghidra/functions.tsv`
    "toujours": False,
    "raison": (
        "L'exhaustivite se DERIVE du dump, pas du code : un changement de build peut faire "
        "apparaitre une 3e surcharge de `GetTargetingOptionsForContinue` sans qu'aucune ligne de "
        "`scripts/python/**` ne bouge -- c'est exactement le regime que ce fichier doit attraper, "
        "donc `build: True` n'est pas une precaution mais LE declencheur principal."),
}

#: Le symbole de la BASE -- le seul `$$GetTargetingOptionsForContinue` qui n'est PAS une surcharge.
BASE = "IdunBattle.Entities.Abilities.AActiveAbility$$GetTargetingOptionsForContinue"
SUFFIXE = "$$GetTargetingOptionsForContinue"


def _classes_surchargeantes() -> set:
    """DERIVE du dump : les noms de classe (dernier segment, sans `Ability`) qui declarent leur
    propre `$$GetTargetingOptionsForContinue`."""
    tsv = symbols_layout.build_dir() / "ghidra" / "functions.tsv"
    if not tsv.exists():
        pytest.skip("dump ghidra absent : %s" % tsv)
    out = set()
    with open(tsv, encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if SUFFIXE not in ligne:
                continue
            sym = ligne.rstrip("\n").split("\t")[-1]
            if sym == BASE:
                continue
            plein = sym.split(SUFFIXE)[0]                 # `...Active.Loki.GreatFrostAxeAbility`
            court = plein.rsplit(".", 1)[-1]
            out.add(court[:-len("Ability")] if court.endswith("Ability") else court)
    return out


# --------------------------------------------------------- 1. l'exhaustivite, DERIVEE du dump

def test_le_dump_porte_bien_des_surcharges():
    """Le cran du dessous : un balayage qui ne trouverait RIEN rendrait l'etage suivant vert sans
    rien mesurer. Si ce test tombe, c'est le BALAYAGE qui est casse, pas le recensement."""
    assert _classes_surchargeantes(), (
        "aucune surcharge de %s dans le dump -- le balayage ne mesure plus rien" % SUFFIXE)


def test_toute_surcharge_du_build_est_RECENSEE():
    """LE CRAN DU RESIDU. Le recensement des masques ne s'arrete plus aux `$$.ctor` : toute classe
    qui REECRIT le second jeu doit avoir son entree. C'est ce balayage qui a montre que la fiche
    n'en nommait qu'une sur deux."""
    attendues = _classes_surchargeantes()
    recensees = {ActiveAbilityType(aid).name for aid in OVERRIDES}
    manquantes = attendues - recensees
    assert not manquantes, (
        "surcharge(s) de %s NON RECENSEE(S) dans TARGETING_OPTIONS_FOR_CONTINUE_OVERRIDES : %r "
        "(recensees : %r)" % (SUFFIXE, sorted(manquantes), sorted(recensees)))
    fantomes = recensees - attendues
    assert not fantomes, (
        "entree(s) recensee(s) SANS surcharge native -- renommee ou disparue au dernier build : %r"
        % (sorted(fantomes),))


# ------------------------------------------------------------------------- 2. la loi de base

def test_la_loi_de_base_AJOUTE_le_bit_et_FORCE_le_flag_melee():
    """VERBATIM : `opts.<+0x28 rules> |= 0x10000000000` et `opts.<+0x20 forceMeleeTarget> = 1`."""
    base = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=True,
                            force_melee_target=RANGED_BOOL_TRUE)
    got = targeting_options_for_continue(base)
    assert got.has(TR.AllowIgnoreForcedAttackTarget), (
        "le mode continue IGNORE la cible forcee : le bit 40 doit etre pose")
    assert got.has(TR.TargetIsEnemy), "les bits du ctor sont CONSERVES, pas remplaces"
    assert got.force_melee_target == RANGED_BOOL_FALSE
    assert got.self_cast is True, "le ctor `COPIE PURE` ne touche a aucun autre champ"


def test_la_loi_de_base_NE_MUTE_PAS_le_jeu_du_ctor():
    """Le natif construit une COPIE (`TargetingOptions..ctor(<copie de this+0x70..0xaf>)`) avant de
    modifier. Muter en place empoisonnerait le masque du cast top-level, qui est le MEME objet
    cote port (`TARGETING_OPTIONS` est un attribut de CLASSE, partage par toutes les instances)."""
    base = TargetingOptions(rules=TR.TargetIsEnemy, force_melee_target=RANGED_BOOL_TRUE)
    avant = (int(base.rules), base.force_melee_target)
    targeting_options_for_continue(base)
    assert (int(base.rules), base.force_melee_target) == avant, "le jeu du ctor a ete MUTE"


# --------------------------------------------------------------------- 3. les deux surcharges

@pytest.mark.parametrize("nom,attendu", [
    ("GreatFrostAxe", int(TR.TargetIsEnemy) | int(TR.AllowDeadTarget)),
    ("EntropyCannons", int(TR.TargetIsEnemy) | int(TR.AllowNullCasterTile)),
])
def test_les_surcharges_IGNORENT_la_loi_de_base(nom, attendu):
    """Elles repartent d'un litteral et n'appliquent PAS `|= AllowIgnoreForcedAttackTarget`."""
    aid = int(getattr(ActiveAbilityType, nom))
    got = targeting_options_for_continue(targeting_options_for(aid), aid)
    assert int(got.rules) == attendu, (
        "%s : masque continue 0x%x, attendu 0x%x" % (nom, int(got.rules), attendu))
    assert not got.has(TR.AllowIgnoreForcedAttackTarget), (
        "%s REECRIT le jeu entier : la loi de base ne doit PAS s'y appliquer" % nom)


def test_EntropyCannons_DESARME_la_regle_dynamique_en_mode_continue():
    """LE CRAN LE PLUS DISCRIMINANT. `.ctor` = 0x40004002 (avec `TargetMatchesDynamicRule`),
    `GetTargetingOptionsForContinue` = 0x40004000 (sans). Un port qui aurait applique la loi de
    base a sa place GARDERAIT le bit -- et le mode continue re-consulterait une regle dynamique que
    le natif ne consulte plus."""
    aid = int(ActiveAbilityType.EntropyCannons)
    ctor = targeting_options_for(aid)
    cont = targeting_options_for_continue(ctor, aid)
    assert ctor.has(TR.TargetMatchesDynamicRule), (
        "temoin : le masque du `.ctor` de 1168 doit bien porter le bit dynamique")
    assert not cont.has(TR.TargetMatchesDynamicRule), (
        "le second jeu de 1168 DESARME TargetMatchesDynamicRule : 0x%x" % int(cont.rules))
