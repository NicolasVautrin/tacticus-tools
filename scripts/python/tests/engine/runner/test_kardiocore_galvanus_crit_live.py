"""CLIQUET #913 -- l'axe ADDITION du canal crit-DEGAT porte par une RELIQUE
(`KardiocoreGalvanus_ExtraCritDmg`, EffectType 0x5aa = 1450).

CRITERE : « le natif AJOUTE-t-il `extraCritDmg[niveau de RELIQUE] x <amis MECANIQUES adjacents au
porteur>` au degat de CRIT que ce porteur INFLIGE, et le port fait-il pareil ? »

Le montage est IMPORTE du probe (`probe_913_kardiocore_galvanus_live.py`) au lieu d'etre
re-transcrit : un montage duplique derive de son original sans que rien ne le signale.

## CE QUE CE FICHIER GARDE, ET POURQUOI CHAQUE BRAS EXISTE

  1. LIVE == OFFLINE, coup par coup ;
  2. `NOCHANNEL` (l'effet retire d'`EFFECT_CLASSES` -> retombe sur `BaseEffect`, canal `None`) :
     doit CHANGER ssi le compteur est non nul. Sans lui, « ca concorde » ne vaudrait rien ;
  3. `PASSIF` (le callable `tertiary_ability_state_of` retire du contexte) : le port retombe sur le
     niveau des PASSIFS (50 -> dernier palier). Doit CHANGER des que le niveau de relique demande
     n'est pas le dernier -- c'est ce qui prouve que le canal TERTIAIRE de #357 mord ICI ;
  4. le PRODUIT : `n = 1` et `n = 2` rendent DEUX bonus differents. C'est ce qui interdit de fitter
     un scalaire ;
  5. les TROIS traits d'`IsMechanical`, et un bras NEGATIF ;
  6. le filtre d'EQUIPE (`AdjacentFriends` -> `Friends(reference = Owner, ...)`).

## L'ETAGE COMPTEUR EST CONFRONTE SANS PASSER PAR LE DEGAT

`decisionView.effects[].level` publie le niveau STOCKE (`EffectComponent+0x68`), que
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` tient EGAL a `$$GetCalculateLevel`.
C'est donc le compteur NATIF, lisible directement -- chaque bras l'assertionne AVANT la magnitude,
ce qui separe « le compteur est faux » de « la magnitude est fausse ».

⚠ CE QUI DISTINGUE CET EFFET DE SES DEUX JUMEAUX DEJA PORTES. Sa `CreateActiveCondition` est
`<DSLTriggers+0x70>` = `YesTrigger`, CONSTANTE VRAIE : l'effet est publie ACTIF meme a `n = 0`.
L'activite n'est donc PAS un observable du compteur (elle l'est pour `AmuletOfTheVoidwyrm` et
`SupaCyborkBody`, dont la condition est geometrique) -- ici elle ne sert que de controle positif du
MONTAGE. Chaque bras l'assertionne a ce titre.

⚠ LE MONTAGE A UNE PIECE QUI ECHOUE EN SILENCE, et elle a ete MESUREE : `place` est un
`MoveUnitOperation` natif COMPLET, donc amener une unite ADVERSE au contact declenche les reactions
du porteur (`OptimizedGait` attaque au mouvement) et CONSOMME son action -- l'`applyAction` suivant
rend alors `mutated: false, changes: []`, sans erreur. Le montage recupere l'action par un cycle de
tour ; sans ce cran, le bras EQUIPE refusait systematiquement alors qu'il etait bon.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/_charge_regime.py",
        # LE MONTAGE : il est IMPORTE, pas recopie -- donc une derive du probe change ce fichier.
        "scripts/python/probe_913_kardiocore_galvanus_live.py",
        # LE PORT et ses trois etages : la classe, l'arbre du compteur, le cablage du canal.
        "scripts/python/engine/entities/effects/loki/kardiocore_galvanus.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # Les DEUX selecteurs de l'arbre `GetCalculateLevel` et le predicat `IsMechanical` :
        # `MechanicalUnits(AdjacentFriends(...))` n'est fidele que si ces trois-la le restent.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/dsl/base.py",
        # Le canal RELIQUE : le montage passe par `--equip-relic`, et le niveau lu est TERTIAIRE.
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/engine/runner/snapshot.py",
        # Les mirrors d'enum que la garde de registre confronte -- la collision d'ordinal 1457 est
        # le piege du cas, elle se voit ICI ou nulle part.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        # Le SUBSTRAT : la config de la relique et le seed BC dont sort le porteur.
        "scripts/python/gameconfig.py", "data/seed-bc.json",
        # Le CAPTEUR dont ce fichier lit `level` et `active` : si le hook cesse de publier le
        # niveau STOCKE, l'etage COMPTEUR devient inconfrontable sans que rien ici ne bouge.
        "frida/hooks/game/effects.ts",
    ),
    "build": False,
    "toujours": False,
    "raison": "Ce cliquet confronte TROIS etages du canal crit-DEGAT : le COMPTEUR "
              "(`GetCalculateLevel`, lu des deux cotes -- natif par `decisionView.effects[].level`, "
              "port par `adjacent_mechanical_friends_count`), l'`AbilityState` TERTIAIRE, et la "
              "MAGNITUDE (`ConfigVar(0x42) x niveau`). Le perimetre couvre donc la classe d'effet "
              "et son registre, les deux selecteurs de son arbre plus le predicat `IsMechanical`, "
              "le cablage du canal (`_crit_board` / `crit_damage_bonus_from_effects`), le canal "
              "relique qui porte le niveau, les mirrors d'enum de la garde de registre, la config "
              "gameconfig et le seed BC d'ou vient le porteur, et le hook qui publie le niveau "
              "STOCKE. Il ne declare PAS `build: True` : rien ici ne lit le binaire, seul le "
              "runner live est requis.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402

import pytest                                                            # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

from probe_913_kardiocore_galvanus_live import (  # noqa: E402
    ABILITY_ID, ATTACKER_EXT, CARRIER, COMPANIONS, EFFECT_NAME, TARGET, TRAITS_MECANIQUES,
    attendu_mecanique, etages, paliers_du_gameconfig, replay, stage, strike)

from _charge_regime import charge_regime  # noqa: E402,F401  (fixture)

_PALIERS = paliers_du_gameconfig()
#: assez GRAND pour que la salve soit lisible ; AUCUNE garde de saturation n'est requise ici --
#: le terme est ADDITIF, donc le `Math.Max(0, .)` de `CalculateCriticalDamage` ne peut pas mordre.
_CRIT_DAMAGE = 2000


def _harnais(charge_regime, level, trait="Mechanical", ennemi=False, board="MC1_67", seed="777",
             porteur_defenseur=False):
    comps = "%s,%s" % COMPANIONS
    traits = ",".join('"%s"' % t for t in str(trait).split(","))
    if porteur_defenseur:
        p_units, a_units = ATTACKER_EXT, "%s,%s" % (CARRIER, comps)
    else:
        p_units = CARRIER if ennemi else "%s,%s" % (CARRIER, comps)
        a_units = TARGET if not ennemi else "%s,%s" % (TARGET, comps)
    extra = ["--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
             "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[0], traits),
             "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[1], traits),
             # Le porteur garde `Hero` + `Mechanical` (il est EXCLU de son propre compteur par
             # l'`op_Subtraction unit` d'`AdjacentFriends`) et perd `Camouflage`/`Infiltrate`/
             # `Unstoppable`, qui ne changent rien au canal mais brouillent la salve.
             "--unit-stat", '%s:Traits=["Hero","Mechanical"]' % CARRIER,
             "--crit", "100,%d" % _CRIT_DAMAGE, "--block-target", "0,0",
             "--hp-target", "900000", "--hp-player", "900000"]
    if porteur_defenseur:
        extra += ["--unit-stat", '%s:Traits=["Hero"]' % ATTACKER_EXT]
    return charge_regime(p_units=p_units, a_units=a_units, seed=seed, board=board, extra=extra)


def _mesure(charge_regime, n, level, trait="Mechanical", ennemi=False, board="MC1_67",
            porteur_defenseur=False):
    h = _harnais(charge_regime, level, trait=trait, ennemi=ennemi, board=board,
                 porteur_defenseur=porteur_defenseur)
    rec, why = stage(h, n, ennemi=ennemi, porteur_defenseur=porteur_defenseur)
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    live, why = strike(h, rec)
    assert live is not None, "attaque non jouee : %s" % why
    off = replay(h, rec)[:len(live)]
    mut = replay(h, rec, mutate="NOCHANNEL")[:len(live)]
    passif = replay(h, rec, mutate="PASSIF")[:len(live)]
    return rec, live, off, mut, passif, etages(h, rec)


def _attendu(n, trait, ennemi) -> int:
    """Le compte que le NATIF doit voir : les compagnons sont poses adjacents dans TOUS les bras,
    seule leur ELIGIBILITE varie (trait mecanique, meme equipe)."""
    return n if (attendu_mecanique(trait) and not ennemi) else 0


@pytest.mark.parametrize("n", [0, 1, 2])
def test_le_bonus_suit_le_nombre_d_amis_mecaniques_adjacents(charge_regime, n):
    """`ForAddition(get_OwnerIsCaster, Multiply(ConfigVar(0x42), EffectLevel(effet)))`.

    `n = 0` verifie AUSSI que la `CreateActiveCondition` est bien CONSTANTE : le natif publie
    l'effet ACTIF meme sans aucun ami mecanique, et le port ne verse rien pour autant."""
    level = 3
    rec, live, off, mut, passif, et = _mesure(charge_regime, n, level)
    assert rec["actif_natif"] is True, (
        "`CreateActiveCondition` = `<DSLTriggers+0x70>` = YesTrigger : l'effet doit etre publie "
        "ACTIF a tout n, or n=%d rend %s" % (n, rec["actif_natif"]))
    assert rec["niveau_natif"] == n, (
        "compteur NATIF (decisionView.effects[].level, tenu egal a GetCalculateLevel par "
        "RefreshEffectsOperation$$UpdateLevel) = %s != %d" % (rec["niveau_natif"], n))
    assert et["compteur"] == n, "compteur du port %s != %d" % (et["compteur"], n)
    assert off == live, "n=%d : port %s != natif %s (etages %s)" % (n, off, live, et)
    assert (mut != off) is (n > 0), (
        "n=%d : le canal doit mordre SSI n > 0 (mut=%s off=%s)" % (n, mut, off))
    attendu = (_PALIERS[level - 1] * n) if n else None
    assert et["bonus_signe"] == attendu, (
        "bonus SIGNE du port %s != %s -- `ForAddition` verse un terme POSITIF"
        % (et["bonus_signe"], attendu))


def test_le_produit_discrimine_deux_regimes_non_nuls(charge_regime):
    """SECOND CAS DISCRIMINANT : `n = 1` et `n = 2` ne peuvent pas s'expliquer par un scalaire.
    Les deux salves sont jouees sur le MEME board et le MEME niveau, donc seul le compteur bouge."""
    level = 3
    _, live1, off1, _, _, et1 = _mesure(charge_regime, 1, level)
    _, live2, off2, _, _, et2 = _mesure(charge_regime, 2, level)
    assert off1 == live1 and off2 == live2, "port != natif (%s / %s)" % (off1, off2)
    assert et2["bonus_signe"] == 2 * et1["bonus_signe"], (
        "le bonus doit DOUBLER de n=1 a n=2 : %s puis %s"
        % (et1["bonus_signe"], et2["bonus_signe"]))
    assert live1 != live2, "les deux regimes rendent la MEME salve -- le bras ne discrimine rien"


@pytest.mark.parametrize("level", [1, 10])
def test_le_niveau_lu_est_celui_de_la_relique_pas_du_passif(charge_regime, level):
    """`GetAbilityState(effet)` -> l'`AbilityState` **TERTIAIRE** (`BC.Units[].TertiaryAbilityLevel`),
    pas celui des passifs. Le bras `PASSIF` le prouve : il ne peut mordre QUE si le niveau demande
    n'est pas le dernier palier (le repli passif y clampe justement)."""
    rec, live, off, mut, passif, et = _mesure(charge_regime, 2, level)
    assert off == live, "lvl=%d : port %s != natif %s (etages %s)" % (level, off, live, et)
    assert et["ability_state"][0] == level, (
        "le port lit le niveau %s au lieu de %d -- canal TERTIAIRE non branche"
        % (et["ability_state"], level))
    assert et["bonus_signe"] == 2 * _PALIERS[level - 1], (
        "ConfigVar(0x42) lu = %s, attendu %d" % (et["bonus_signe"], 2 * _PALIERS[level - 1]))
    assert mut != off, "lvl=%d : le canal doit mordre (n=2)" % level
    assert (passif != off) is (level != len(_PALIERS)), (
        "lvl=%d : le bras PASSIF doit mordre SSI le niveau n'est pas le dernier palier" % level)


@pytest.mark.parametrize("trait", list(TRAITS_MECANIQUES))
def test_les_trois_traits_de_IsMechanical_comptent_pareil(charge_regime, trait):
    """`IdunBattle.Entities.UnitExtensions$$IsMechanical` = `HasTrait(5 = Mechanical) ||
    HasTrait(0x3e8 = 1000 LivingMetal) || HasTrait(0x405 = 1029 Vehicle)`.

    Balayer les TROIS plutot que le seul `Mechanical` est ce qui interdit de confondre le filtre
    natif avec un test de trait unique -- un Necron `LivingMetal` est mecanique SANS porter
    `Mechanical`."""
    rec, live, off, mut, _, et = _mesure(charge_regime, 2, 3, trait=trait)
    assert rec["niveau_natif"] == 2, (
        "trait %s : compteur NATIF = %s, attendu 2" % (trait, rec["niveau_natif"]))
    assert et["compteur"] == 2 and et["bonus_signe"] == 2 * _PALIERS[2]
    assert off == live, "trait %s : port %s != natif %s (etages %s)" % (trait, off, live, et)
    assert mut != off, "trait %s : le canal doit mordre" % trait


def test_un_ami_adjacent_NON_mecanique_ne_compte_pas(charge_regime):
    """BRAS NEGATIF : deux amis ADJACENTS dont le trait n'est PAS lu par `IsMechanical`.
    `MechanicalUnitsSelector$$Select` les ecarte -> compteur 0, canal muet.

    Sans ce bras, « le compteur vaut n » ne distinguerait pas `MechanicalUnits(AdjacentFriends)` de
    `AdjacentFriends` tout court."""
    rec, live, off, mut, _, et = _mesure(charge_regime, 2, 3, trait="Hero")
    assert rec["niveau_natif"] == 0, (
        "le natif compte %s ami(s) NON mecanique(s) -- REFUTATION du filtre `MechanicalUnits`"
        % rec["niveau_natif"])
    assert et["compteur"] == 0 and et["bonus_signe"] is None
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert mut == off, "a compteur 0 le canal ne doit RIEN ajouter (mut=%s off=%s)" % (mut, off)


def test_un_ennemi_mecanique_adjacent_ne_compte_pas(charge_regime):
    """BRAS EQUIPE : les deux compagnons MECANIQUES passent cote ADVERSE.

    `DSLSelectors$$AdjacentFriends(unit, unique, selectionType)` =
    `Friends(reference = unit, Units(AdjacentTiles(unit), unique, selectionType) - unit,
    selectionType)` : la reference d'equipe EST le porteur, donc un ennemi mecanique adjacent ne
    doit rien ajouter. Sans ce bras, `AdjacentFriends` et `AdjacentUnits` seraient indistinguables."""
    rec, live, off, mut, _, et = _mesure(charge_regime, 2, 3, ennemi=True)
    assert rec["niveau_natif"] == 0, (
        "le natif compte %s ennemi(s) mecanique(s) adjacent(s) -- REFUTATION du filtre `Friends`"
        % rec["niveau_natif"])
    assert et["compteur"] == 0 and et["bonus_signe"] is None
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert mut == off, "a compteur 0 le canal ne doit RIEN ajouter (mut=%s off=%s)" % (mut, off)


def test_le_porteur_DEFENSEUR_ne_recoit_RIEN_malgre_un_compteur_PLEIN(charge_regime):
    """BRAS TRIGGER, et le SEUL qui separe cet effet de ses deux jumeaux.

    `EffectBonus.ForAddition(get_OwnerIsCaster, ...)` ou
    `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` = `AreEqual(Owner@DSLSelectors+0x30,
    Caster@DSLSelectors+0x48)`. `AmuletOfTheVoidwyrm_CritDamageReduction` et
    `SupaCyborkBody_CritDmgReduction` lisent l'AUTRE slot (`get_OwnerIsTarget`) : un port qui les
    confondrait passerait TOUS les autres bras de ce fichier.

    ⚠ CE QUI REND CE BRAS PROBANT est son TEMOIN NON NUL : le porteur DEFEND, mais ses deux amis
    mecaniques restent ADJACENTS, donc le compteur vaut **2** des deux cotes. Un bras ou le compteur
    serait nul serait vert pour la mauvaise raison (regime degenere) -- ici le canal doit se taire
    alors que TOUT le reste de la chaine est arme."""
    rec, live, off, mut, passif, et = _mesure(charge_regime, 2, 3, porteur_defenseur=True)
    assert rec["niveau_natif"] == 2, (
        "TEMOIN EFFONDRE : le compteur natif vaut %s au lieu de 2 -- sans amis mecaniques "
        "adjacents ce bras serait vert par degenerescence" % rec["niveau_natif"])
    assert et["compteur"] == 2, "compteur du port %s != 2" % et["compteur"]
    assert et["bonus_signe"] is None, (
        "le porteur DEFEND : `get_OwnerIsCaster` doit rendre FAUX, or le port verse %s -- c'est la "
        "confusion `OwnerIsTarget`/`OwnerIsCaster`" % et["bonus_signe"])
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert mut == off, (
        "le natif non plus ne verse rien : retirer le canal ne doit RIEN changer (mut=%s off=%s)"
        % (mut, off))


def test_l_effet_est_au_registre_avec_son_identite_de_config(charge_regime):
    """GARDE DE REGISTRE, OFFLINE : la cle `EFFECT_CLASSES` est le NOM que publie `decisionView`,
    et la config lue est la TRIGGERED 1457 -- pas l'EffectType 1457, qui est
    `RelicBoltPistol_ExtraPierce`, une AUTRE relique dont la config EXISTE au gameconfig (donc la
    confusion ne leverait pas : elle lirait juste la mauvaise variable, en silence).

    Les valeurs sont relues des enums, jamais recopiees."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.entities.effects.loki.kardiocore_galvanus import (
        KardiocoreGalvanusExtraCritDmgEffect)
    assert EFFECT_CLASSES.get(EFFECT_NAME) is KardiocoreGalvanusExtraCritDmgEffect
    assert EffectType(1450).name == EFFECT_NAME
    assert TriggeredAbilityType(1457).name == ABILITY_ID
    assert EffectType(1457).name != EFFECT_NAME, (
        "1457 en EffectType est une AUTRE relique -- la collision d'ordinal est le piege du cas")
    assert TriggeredAbilityType(1450).name != ABILITY_ID
