"""#883 -- L'ARRONDI du bonus crit-sur-Ice est `Fix64.Round`, PAS un floor.

CE QUE CE CLIQUET GARDE, ET POURQUOI IL EXISTE SEPAREMENT DU TEST LIVE
----------------------------------------------------------------------
`IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack` remplit le canal
ADDITION avec `PercentageOf(StatAmount(attaquant, 10 = CRIT_DAMAGE), EffectConfig(5))` -- et lui
passe **`roundingRule = 0`**, litteral LU dans le decompile (`rnca9r7q6c`). Le consommateur
`IdunBattle.DSL.AAmountFormula$$RoundFix64Result` lit cette regle ainsi :

    rule == 1 -> Fix64.Ceiling
    rule == 2 -> Fix64.Floor
    sinon (0) -> Fix64.Round          <- LA NOTRE

Le port `engine/runner/damage_model.py::ice_crit_damage_addition` ecrivait `(cd * pct) // 100`,
c'est-a-dire un FLOOR, donc la regle 2. Divergence de -1 chaque fois que `cd x pct / 100` a une
partie fractionnaire >= 0.5.

⚠ POURQUOI UN CLIQUET OFFLINE ALORS QUE LE LIVE L'A TROUVE. Le temoin live est
`test_lord_of_tempests_ice_live.py::test_lord_of_tempests_snowball_second_attack` : il a rougi
parce que Njal porte `cd = 2727` et que `2727 x 25 / 100 = 681.75`. Mais ce `cd` n'est pas un
choix du test -- il tombe de la stat de l'unite et de la geometrie du drive. Le temoin qui
attestait le floor AVANT (`probe_45f --case crit`) forcait `cd = 700`, et `700 x 25 / 100 = 175.0`
n'a AUCUNE fraction : floor et round y rendent le meme 175, sur 4 coups sur 4. Un accord en
REGIME DEGENERE, qui a fait ecrire « floor » dans le port et l'y a maintenu.

Le meme sort guette le temoin live actuel : que la stat de Njal, le rank du montage ou
`IceCritDmgBonusPct` bougent vers un couple non fractionnaire, et il redeviendrait VERT avec le
floor restaure -- sans plus rien garder. Ce fichier-ci ne depend d'AUCUNE geometrie, d'aucune
unite et d'aucun runner : il interroge la fonction sur des valeurs CHOISIES pour etre
discriminantes, et exige que ce choix soit lui-meme non vide.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

from fractions import Fraction

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/dsl/base.py",
        # #547-r6 -- AJOUTE APRES MESURE. La confrontation de `probe_486r15` a nomme ce chemin des
        # que l'empreinte de ce fichier a ete GRAVEE (`--measure-missing`) : `damage_model` tire la
        # cascade qui lit la seed au CHARGEMENT, donc le verdict en depend, meme si aucun cas ne
        # l'ouvre lui-meme. C'est le regime #486-r29 -- le manque n'apparait pas chez l'auteur, il
        # apparait au merge, quand l'empreinte existe. Meme correctif que celui applique a
        # `probe_485r1r1_acces_attributaires` par #880, pour la meme raison.
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : aucun runner, aucun RPC, aucune lecture du binaire ni du "
              "gameconfig. Les trois etages n'exercent QUE l'arithmetique d'arrondi -- le foyer "
              "partage `_round_fix64` (`engine/dsl/base.py`, mirror de "
              "`AAmountFormula$$RoundFix64Result`) et le site qui doit le consommer "
              "(`ice_crit_damage_addition`, dans `damage_model.py`). Le perimetre se reduit donc "
              "a ces deux fichiers : un changement ailleurs ne peut pas renverser ces verdicts, "
              "et un changement dans l'un des deux le peut.",
}


def _floor_pct(cd: int, pct: int) -> int:
    """Ce que le port ECRIVAIT : la regle 2 (`Fix64.Floor`) -- conservee ici comme CONTRE-MODELE."""
    return (cd * pct) // 100


def test_round_fix64_mode0_est_bien_round_et_pas_floor():
    """ETAGE 1 -- le foyer partage applique les TROIS regles de `RoundFix64Result`, distinctement.

    Si ce cliquet tombe, ce n'est pas le site Ice qui a bouge mais le mirror d'arrondi lui-meme.
    """
    from engine.dsl.base import _round_fix64
    v = Fraction(68175, 100)                     # 681.75 -- le cas exact du snowball (#883)
    assert _round_fix64(v, 0) == 682, "mode 0 doit etre Fix64.Round"
    assert _round_fix64(v, 1) == 682, "mode 1 doit etre Fix64.Ceiling"
    assert _round_fix64(v, 2) == 681, "mode 2 doit etre Fix64.Floor"
    # Demi-vers-le-PAIR (`Fix64.Round(., midpointRounding = 0)`), pas demi-en-haut : c'est ce qui
    # distingue le mirror d'un `round()` naif, et les deux divergent sur UN cas sur deux.
    assert _round_fix64(Fraction(50, 100), 0) == 0, "0.5 -> 0 (half-to-even)"
    assert _round_fix64(Fraction(150, 100), 0) == 2, "1.5 -> 2 (half-to-even)"
    assert _round_fix64(Fraction(250, 100), 0) == 2, "2.5 -> 2 (half-to-even)"


def _etat_cible_sur_glace(cd: int):
    """Etat MINIMAL suffisant pour franchir les gates de `ice_crit_damage_addition` : une cible
    positionnee, la tuile qu'elle occupe porteuse d'un effet `Ice` ACTIF, aucun trait `Immune`,
    et un `ctx` qui rend `cd` sur `GetStat(10)`. Aucun runner, aucun RPC."""
    from engine.runner.state import State
    from engine.runner.components import PositionComponent
    from engine.entities.stats import StatType
    from engine.entities.effect_type import EffectType

    tuile = 9001

    class _Board:
        def id_at(self, col, row):
            return tuile

    class _Ice:
        effect_type = int(EffectType.Ice)
        consumed = False

    class _Effects:
        by_unit = {tuile: [_Ice()]}

    class _Ctx:
        def stat(self, s):
            return cd if int(s) == int(StatType.CRIT_DAMAGE) else 0

    st = State()
    st.board, st.effects = _Board(), _Effects()
    st.add_entity(77).add_component(PositionComponent(col=3, row=4))
    return st, _Ctx()


def test_ice_crit_addition_arrondit_au_lieu_de_tronquer():
    """ETAGE 2 -- LE SITE LUI-MEME consomme la regle 0, sur le couple mesure live.

    ⚠ Cet etage appelle `ice_crit_damage_addition` POUR DE VRAI, et c'est le seul point de ce
    fichier qui MORDE sur une regression du port : un etage qui se contenterait de comparer
    `_round_fix64(...)` a `_floor_pct(...)` resterait VERT si l'on restaurait le `// 100` dans
    `damage_model.py`, puisqu'il ne toucherait jamais au site. Contre-epreuve jouee a l'ecriture :
    avec le floor restaure, cet etage rend 681 et ROUGIT ; avec le port courant il rend 682.

    Couple EXACT mesure le 2026-08-10 : `cd = 2727` (Njal `spaceStormcaller`), `pct = 25`
    (`IceCritDmgBonusPct`). L'ecart y vaut 1, et il s'est propage en +1 par coup CRITIQUE dans le
    live -- port `[5197, 4128, 1200]` contre natif `[5198, 4129, 1200]`.
    """
    from engine.runner.damage_model import ice_crit_damage_addition, bc_effect_config
    from engine.dsl.base import _round_fix64

    assert bc_effect_config("IceCritDmgBonusPct", 25) == 25, \
        "IceCritDmgBonusPct a change -- re-deriver le couple discriminant de ce fichier"

    cd = 2727
    st, ctx = _etat_cible_sur_glace(cd)
    obtenu = ice_crit_damage_addition(st, 89, 77, ctx)
    assert obtenu == 682, (
        "le site doit appliquer `Fix64.Round` (regle 0), pas un floor : "
        "2727 x 25 / 100 = 681.75 -> 682, obtenu %r" % (obtenu,))
    assert obtenu != _floor_pct(cd, 25), \
        "ce couple DOIT etre discriminant, sinon cet etage ne prouve rien"
    assert obtenu == _round_fix64(Fraction(cd * 25, 100), 0), \
        "le site doit passer par le FOYER partage, pas par un arrondi local"


def test_le_temoin_historique_ne_pouvait_pas_departager():
    """ETAGE 3 -- l'ANTI-VACUITE, et c'est le vrai sujet de ce fichier.

    Deux affirmations, et la seconde est celle qui compte :
      (a) le temoin qui attestait le floor (`cd = 700`) rend la MEME valeur des deux facons -- il
          etait donc incapable de trancher, et l'accord qu'il rapportait ne prouvait rien ;
      (b) les couples discriminants ne sont pas une curiosite : ils sont MAJORITAIRES en nombre
          sur une plage realiste de `cd`. On l'asserte pour qu'un futur changement de `pct` qui
          rendrait le fix inobservable (ex. `pct = 50`, ou floor et round coincident 1 fois sur 2
          seulement, ou `pct = 100`, ou ils coincident TOUJOURS) fasse rougir ICI plutot que de
          laisser ce fichier passer a vide.
    """
    from engine.dsl.base import _round_fix64
    assert _floor_pct(700, 25) == _round_fix64(Fraction(700 * 25, 100), 0) == 175, \
        "le temoin historique doit bien etre NON discriminant (c'est la cause du bug)"

    pct = 25
    discriminants = [cd for cd in range(1, 4001)
                     if _floor_pct(cd, pct) != _round_fix64(Fraction(cd * pct, 100), 0)]
    assert discriminants, "aucun cd discriminant : ce fichier ne garderait plus rien"
    # 1500 sur 4000 = 37,5 % a pct = 25 (les cd non multiples de 4 dont le reste vaut 2 ou 3).
    assert len(discriminants) > 1000, (
        "trop peu de couples discriminants (%d/4000) -- l'ecart est devenu marginal, "
        "verifier que `IceCritDmgBonusPct` n'a pas change" % len(discriminants))
    assert 2727 in discriminants, "le temoin live du snowball doit rester discriminant"
    assert 700 not in discriminants, "le temoin historique doit rester NON discriminant"
