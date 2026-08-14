"""#924-r2 -- la PLACE de l'additif `EffectBonus.ForAddition` ATTAQUANT, et pourquoi la
mesure qui la disait FAUSSE ne pouvait rien prouver.

CE QUE LE DECOMPILE DIT, LU LE 2026-08-14 sur `rnca9r7q6c` (build courant).
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` calcule LUI-MEME les deux
jeux de modificateurs -- slots `0xd` (ATTAQUANT) et `0xe` (DEFENSEUR) de
`IDamageCalculations`, c'est-a-dire
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`
et son jumeau DEFENSE, dont la signature `(this, state, entities, activeEffects)` prend
un `IdunBattle.Entities.Abilities.AbilityEntities`. De CHACUN des deux structs rendus il
lit le champ `+0x10` (= `DamageModifiers.Addition`) et le SOMME au `baseDamage` qu'il
passe a `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
-- pour la borne MIN **et** pour la borne MAX, avec les MEMES deux termes (seul le terme
de spread differe entre les deux appels).

La disposition du struct est confirmee terme a terme au meme endroit : `+0x00` est lu
comme un `Nullable` dont la valeur ECRASE le degat de base (= `Override`), `+0x10` est le
terme additif ci-dessus, et `CalculateBaseDamageWithAllModifiers` ne lit, lui, que
`+0x20` (`Piercing`), `+0x28` (`IgnoreArmor`), la liste `+0x18` et `+0x30`
(`Multiplier`) -- **jamais `+0x10`**.

DONC : l'additif des DEUX faces entre AVANT le percage/l'armure et AVANT les %-mods.
C'est exactement la position du port -- `attacker_additive_pre=True` dans
`engine/services/damage_prediction.py::apply_pierce_and_modifiers`, qui fait
`d = round(value + mods.additive)` PUIS `get_damage_with_piercing` PUIS la %-liste.

CE QUE LA MESURE DE #924 NE POUVAIT PAS PROUVER. Elle conclut que le port pose l'additif
« un etage trop bas » a partir d'un ecart mesure `armure 0 des deux cotes`. Or a armure
nulle, `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$
GetDamageWithPiercing` rend `max(0, d - 0, d * p/100) = d` : la fonction est l'IDENTITE,
donc ajouter l'additif AVANT ou APRES elle donne le MEME nombre. Le montage etait
DEGENERE pour la question posee -- il ne separe pas les deux positions, quel que soit
l'ecart observe. L'etage 2 ci-dessous le mesure : `+898` des DEUX cotes.

Le meme couple, joue dans le regime SEPARANT (celui de #75, `orksNob SmashaEad` :
`pierce = 50`, `armure = 2208`), rend `+449` en position PRE contre `+898` en position
POST -- un facteur 2 franc. C'est CE regime qu'il aurait fallu jouer.

⇒ La prémisse de #924-r2 est REFUTEE : la place est JUSTE. L'ecart `898` contre `617,3`
mesure sur Imospekh a une AUTRE cause, non localisee -- il reste ouvert, mais il ne
designe plus l'etage.

CE QUE CE CLIQUET GARDE : que personne ne « repare » #924-r2 en DEPLACANT l'additif.
Le deplacement casserait la bit-exactness de #75, qui est validee live.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.services.damage_modifiers import DamageModifiers
from engine.services.damage_prediction import apply_pierce_and_modifiers

_RACINE = Path(__file__).resolve().parents[2] / "engine"

#: Le montage de #75, VALIDE BIT-EXACT LIVE (orksNob `SmashaEad`) : additif 599,
#: `pierce = 50`, armure de la cible 2208. C'est le regime ou le percage DOMINE
#: (`d - armure < d * p/100`), donc celui ou les deux positions se separent.
_SEPARANT = dict(pierce=50, armor=2208)
#: Le montage de #924 : `armure 0 des deux cotes`. `GetDamageWithPiercing` y est
#: l'IDENTITE, donc les deux positions coincident -- regime DEGENERE.
_DEGENERE = dict(pierce=50, armor=0)

_BASE = 906          # stat Attack mesuree sur l'attaquant de #924
_ADDITIF = 898       # ecart par coup mesure cote port dans #924


def _ecart(additif: int, pierce: int, armor: int, pre: bool) -> float:
    """Ce que l'additif RAPPORTE, a la position demandee, tout le reste egal."""
    avec = DamageModifiers()
    avec.additive = additif
    sans = DamageModifiers()
    a = apply_pierce_and_modifiers(_BASE, pierce, armor, avec, attacker_additive_pre=pre)
    b = apply_pierce_and_modifiers(_BASE, pierce, armor, sans, attacker_additive_pre=pre)
    if not pre:                        # position POST : l'additif s'ajoute APRES la reduction
        a = float(b) + additif
    return float(a) - float(b)


def test_etage1_le_regime_de_924_est_DEGENERE_pour_la_question_posee():
    """A armure nulle, PRE et POST rendent le MEME nombre -- la mesure ne separe rien.

    C'est le coeur de la refutation, et il ne depend d'AUCUNE lecture du decompile :
    quel que soit l'ecart observe dans ce montage, il ne peut pas designer la position
    de l'additif.
    """
    pre = _ecart(_ADDITIF, pre=True, **_DEGENERE)
    post = _ecart(_ADDITIF, pre=False, **_DEGENERE)
    assert pre == post == float(_ADDITIF), (pre, post)


def test_etage2_le_regime_de_75_SEPARE_les_deux_positions():
    """Contre-epreuve OBLIGATOIRE : le test 1 ne vaut que si un regime separant EXISTE.

    Sans lui, « les deux positions coincident » pourrait vouloir dire « le drapeau est
    inerte », et le cliquet serait un vert qui ment.
    """
    pre = _ecart(_ADDITIF, pre=True, **_SEPARANT)
    post = _ecart(_ADDITIF, pre=False, **_SEPARANT)
    assert pre != post, (pre, post)
    # le percage DOMINE, donc la position PRE fait traverser `x p/100` a l'additif
    assert pre == pytest.approx(_ADDITIF * _SEPARANT["pierce"] / 100.0, abs=1.0), pre
    assert post == float(_ADDITIF), post


def test_etage3_tous_les_vecteurs_de_degat_posent_la_position_PRE():
    """Perimetre DERIVE : tout appel de `apply_pierce_and_modifiers` sous `engine/**`.

    Le decompile place l'additif AVANT `CalculateBaseDamageWithAllModifiers` (donc avant
    percage et %-mods) : le port doit passer `attacker_additive_pre=True` PARTOUT. Un
    appel qui l'omet retomberait sur le chemin legacy POST-percage, plus utilise --
    exactement le « deplacement d'etage » que #924-r2 prescrivait a tort.

    Un appel qui passe `mods=None` LITTERAL est ECARTE, et l'ecart est NOMME dans la
    sortie : sans modificateur il n'y a pas d'additif, donc la position n'existe pas. Le
    critere n'exempte QUE cette forme -- un `mods` transmis par variable reste exige, meme
    quand la fonction qui le transmet n'a aujourd'hui aucun appelant (`resolve_one_hit` :
    piege dormant, ferme dans le meme commit).
    """
    manquants, ecartes = [], []
    for chemin in sorted(_RACINE.rglob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            nom = getattr(noeud.func, "attr", None) or getattr(noeud.func, "id", None)
            if nom != "apply_pierce_and_modifiers":
                continue
            site = "%s:%d" % (chemin.relative_to(_RACINE).as_posix(), noeud.lineno)
            kw = {k.arg: k.value for k in noeud.keywords if k.arg}
            if "attacker_additive_pre" in kw:
                continue
            mods = kw.get("mods")
            if mods is None and len(noeud.args) >= 4:
                mods = noeud.args[3]
            if isinstance(mods, ast.Constant) and mods.value is None:
                ecartes.append(site)          # `mods=None` LITTERAL : pas d'additif possible
                continue
            manquants.append(site)
    print("[924-r2] ECARTES PAR CE CRITERE (mods=None litteral) : %s" % (ecartes or "aucun"))
    assert not manquants, (
        "appel(s) de `apply_pierce_and_modifiers` sans `attacker_additive_pre` : %s" % manquants)


def test_etage3bis_le_perimetre_du_balayage_est_NON_VIDE():
    """Un balayage qui ne visite rien passerait pour vert. Il doit VOIR des appels."""
    vus = 0
    for chemin in sorted(_RACINE.rglob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Call):
                nom = getattr(noeud.func, "attr", None) or getattr(noeud.func, "id", None)
                if nom == "apply_pierce_and_modifiers":
                    vus += 1
    assert vus >= 5, vus
