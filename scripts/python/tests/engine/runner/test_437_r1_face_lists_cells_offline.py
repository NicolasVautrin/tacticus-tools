"""#437-r1 -- les CELLULES NATIVES du tir d'overwatch, verrouillees OFFLINE.

LA LOI, telle que #437-r1-r1 l'a etablie (decompile + capteur) : le nombre de
`FixMath.NET.Fix64$$Round` est le NOMBRE D'ACCUMULATEURS `Multiplier@0x30` NON NULS -- les etapes
3 et 4 de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
(`CalculateBaseDamageWithModifiers`), chacune INCONDITIONNELLE des que son `Nullable` a une valeur.
Ce que le port appelle `pct_list` / `pct_list_defender` EST ce `Multiplier@0x30`, une face chacun ;
`separate_face_lists=True` restitue donc « UN `Round` PAR FACE », qui est la loi.

⚠ Ce n'est PAS « deux appels a `ApplyCappedModifiers` » : ce foyer-la arrondit PAR ENTREE et
inconditionnellement, donc y decouper une liste en deux appels serait ARITHMETIQUEMENT NEUTRE ; et
sa liste `@0x18` n'est alimentee par AUCUN chemin porte (capteur `effect-bonus-trace` : 0 sur 199
sur CE montage, 0 sur 693 sur celui de #462-r4a). Le port COMBAT fusionnait les deux faces dans UNE
chaine, donc UN seul arrondi : `-1` sur la borne des que le produit de la face attaquant tombait
sur un demi-entier.

LES CELLULES, ET COMMENT ELLES ONT ETE OBTENUES. Ce ne sont pas des soustractions : les bornes
natives sont INVERSEES depuis l'alea BRUT du tirage. `IdunBattle.Utils.PRNG.
IntBasedMersenneTwister$$NextInternal` rend `lo + ((genrand >> 1) % (hi + 1 - lo))` ; a `r` connu
(rejeu offline sur le MEME `dumpRng`) et degat natif connu, on enumere les (lo, hi) qui satisfont
l'egalite. Montage `probe_437r1_overwatch_offbyone.py --capture --dmg-target N` (board `MC1_67`,
seed 4321, `eldarRanger` -> `spaceStormcaller`) :

  base d'attaque | bornes brutes | bornes NATIVES  | chaine unique   | deux appels
  4518           | 3614 / 5422   | (1130, 1695)    | (1129, 1694) X  | (1130, 1695) OK
  4526           | 3621 / 5431   | (1132, 1697)    | (1132, 1697) OK | (1132, 1697) OK   <- TEMOIN
  4538           | 3630 / 5446   | (1135, 1702)    | (1134, 1702) X  | (1135, 1702) OK   <- UNIQUE

La base 4526 est le TEMOIN NON DISCRIMINANT : les deux modeles y coincident. Sans lui, on ne
saurait pas qu'un accord peut venir du REGIME et non du modele. La base 4538 est la seule dont
l'inversion rende UNE SEULE paire -- c'est elle qui porte la preuve.

Faces du regime : ATTAQUANT = `HeavyWeapon_ExtraDmg` (effet, `PercentIncrease` 25 -> x1.25),
DEFENSEUR = `TerminatorArmour_ReduceDmg` (effet, `PercentDecrease` 75 -> x0.25). Percage 30,
armure 0 (`--hp-player` met Armor/FixedArmor a 0) -> la branche `d - armure` gagne et la valeur
d'entree est ENTIERE : le regime ne doit RIEN a une fraction de percage, contrairement a #446-r2 /
#462-r4d. C'est un gisement distinct.

Ce cran appelle le FOYER REEL (`apply_pierce_and_modifiers`), jamais une reimplementation.
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.services.damage_modifiers import DamageModifiers
from engine.services.damage_prediction import apply_pierce_and_modifiers, get_base_damage_fix64

PIERCE = 30
ARMOR = 0
ATT_PCT = 1.25          # HeavyWeapon_ExtraDmg  (PercentIncrease 25)
DEF_PCT = 0.25          # TerminatorArmour_ReduceDmg (PercentDecrease 75)

# (base d'attaque, bornes brutes attendues, bornes NATIVES, discriminant ?)
CELLS = [
    (4518, (3614, 5422), (1130, 1695), True),
    (4526, (3621, 5431), (1132, 1697), False),      # TEMOIN : les deux modeles coincident
    (4538, (3630, 5446), (1135, 1702), True),       # inversion a solution UNIQUE
]


def _mods():
    """L'accumulateur tel que le COMBAT le presente : face ATTAQUANT dans `pct_list`, face
    DEFENSEUR deja fusionnee dans `pct_list_defender` (ce que fait
    `AttackDamageOperation._apply_defender_flat_reductions`)."""
    m = DamageModifiers()
    m.pct_list.append((ATT_PCT, None))
    m.pct_list_defender.append((DEF_PCT, None))
    return m


def _mods_fusionnees():
    """LE CONTRE-MODELE : les deux entrees dans la MEME face, donc UN SEUL `Round`. C'est ce que
    rendait le port d'`origin/master` avant #437-r1, et c'est ce que rendrait un port qui
    re-fusionnerait les faces. Depuis #437-r1-r1-r1 il n'y a plus de drapeau a basculer :
    la seule facon de fabriquer la chaine unique est de mettre les deux entrees sur une face."""
    m = DamageModifiers()
    m.pct_list.extend([(ATT_PCT, None), (DEF_PCT, None)])
    return m


def _bound(base_value: int, mods) -> int:
    return int(apply_pierce_and_modifiers(base_value, PIERCE, ARMOR, mods,
                                          attacker_additive_pre=True))


@pytest.mark.parametrize("attack,raw,native,_disc", CELLS)
def test_bornes_brutes_du_spread(attack, raw, native, _disc):
    """Etage AMONT : `GetBaseDamageFix64` (spread 20%). Si celui-ci derivait, les cellules
    ci-dessous ne mesureraient plus le meme etage."""
    mm = get_base_damage_fix64(attack, extra_max=0, spread_pct=20)
    assert (int(mm.min), int(mm.max)) == raw


@pytest.mark.parametrize("attack,raw,native,_disc", CELLS)
def test_cellules_natives_avec_faces_separees(attack, raw, native, _disc):
    """Le port COMBAT doit rendre les bornes NATIVES, a l'unite, sur les trois bases."""
    got = (_bound(raw[0], _mods()), _bound(raw[1], _mods()))
    assert got == native, ("base %d : bornes %s attendues %s (natives, inversees depuis l'alea "
                           "brut du tirage)" % (attack, got, native))


@pytest.mark.parametrize("attack,raw,native,disc", [c for c in CELLS if c[3]])
def test_la_chaine_unique_manque_la_cellule(attack, raw, native, disc):
    """CONTRE-EPREUVE : la chaine UNIQUE (les deux entrees sur la MEME face, donc UN seul arrondi)
    rate la borne basse. Sans ce cran, un cas non discriminant pourrait faire croire que les deux
    modeles se valent."""
    got = (_bound(raw[0], _mods_fusionnees()), _bound(raw[1], _mods_fusionnees()))
    assert got != native, ("base %d : la chaine unique rend %s, or elle doit DIFFERER des bornes "
                           "natives %s -- sinon cette base n'est pas discriminante et n'a rien a "
                           "faire dans cette liste" % (attack, got, native))
    assert got[0] == native[0] - 1, ("base %d : l'ecart attendu sur la borne BASSE est -1 "
                                     "(un arrondi manquant), obtenu %s vs %s"
                                     % (attack, got, native))


def test_temoin_non_discriminant_coincide():
    """La base 4526 rend la MEME chose sous les DEUX modeles. C'est ce qui prouve qu'un accord ne
    vaut pas preuve de modele -- et c'est pour ca qu'elle est dans la liste."""
    attack, raw, native, disc = CELLS[1]
    assert disc is False
    assert (_bound(raw[0], _mods()), _bound(raw[1], _mods())) == native
    assert (_bound(raw[0], _mods_fusionnees()),
            _bound(raw[1], _mods_fusionnees())) == native


def test_la_separation_est_INCONDITIONNELLE():
    """#437-r1-r1-r1 -- LA DEROGATION NE DOIT PAS REVENIR.

    Il a existe ici un parametre `separate_face_lists`, a `True` sur les quatre vecteurs COMBAT et
    `False` en PREDICTION. Ce n'etait PAS un arbitrage de vecteur (#437-r1-r1 l'avait refute : les
    deux gardes contradictoires etaient toutes deux mesurees sur le vecteur COMBAT) : il compensait
    une ATTRIBUTION DE FACE divergente du port. Celle-ci etant corrigee, le parametre est retire.

    Ce cran garde les DEUX faces de cette suppression, et il est TOKEN-AWARE (`ast`) et non un
    `in` sur le texte -- une version anterieure cherchait la sous-chaine dans le source et le
    COMMENTAIRE qui documentait le drapeau la contenait, si bien que la mutation ne mordait pas :
      1. la SIGNATURE de `apply_pierce_and_modifiers` ne porte plus le parametre ;
      2. AUCUN module d'`engine/` ne le passe en mot-cle -- ce qui interdit de le re-introduire
         discretement par un `**kwargs` ou une signature parallele.
    """
    import ast
    import inspect
    from pathlib import Path
    from engine.services import damage_prediction as dp

    sig = inspect.signature(dp.apply_pierce_and_modifiers)
    assert "separate_face_lists" not in sig.parameters, (
        "`apply_pierce_and_modifiers` reprend un parametre `separate_face_lists` : la separation "
        "des deux faces est la LOI (un `Round` par accumulateur `Multiplier@0x30` non nul), pas une "
        "option. Ce qu'un tel drapeau compenserait est une ATTRIBUTION DE FACE -- a corriger dans "
        "`EffectBonus.native_face` / `BaseEffect.*_NATIVE_FACE`, garde par "
        "`probe_437r1r1r1_effect_face_table.py`.")

    root = Path(dp.__file__).resolve().parents[1]          # .../engine
    porteurs = []
    for py in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                                 # pragma: no cover - source du depot
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and any(
                    k.arg == "separate_face_lists" for k in node.keywords):
                porteurs.append("%s:%d" % (py.relative_to(root), node.lineno))
    assert not porteurs, ("le mot-cle `separate_face_lists` est repasse quelque part dans "
                          "`engine/` : %s" % porteurs)


def test_garde_A_sous_les_faces_MESUREES():
    """LA DISSOLUTION DE LA « CONTRADICTION », encodee.

    Le capteur `effect-bonus-trace` lit, sur le montage de la garde A (#462-r4a `--two-faces`), UN
    SEUL accumulateur qui COMPOSE : `1 -> 0.6999999999534339 -> 1.0499999998137355`, les DEUX bonus
    etant etiquetes `face=attacker` par le natif (`Terrifying_ExtraDefense` compris). Sous cette
    attribution, la garde A tombe juste MEME AVEC la separation armee -- donc elle ne contredit PAS
    la garde B, qui exige deux `Round` parce que le capteur y lit DEUX accumulateurs distincts
    (`face=attacker x1.25` et `face=defender x0.25`, chacun repartant de `1`, 41/41).

    Ce cran est ce qui interdit de re-justifier une fusion des faces par le VECTEUR."""
    m = DamageModifiers()
    m.pct_list.extend([(1.5, None), (0.7, None)])          # les DEUX sur la face ATTAQUANTE
    for base, attendu in ((725, 761), (1087, 1141)):
        got = int(apply_pierce_and_modifiers(base, 100, 0, m, attacker_additive_pre=True))
        assert got == attendu, ("garde A, faces MESUREES (les deux en face attaquante), base %d : "
                                "%d != %d natif" % (base, got, attendu))

    # CONTRE-EPREUVE : sous l'attribution ABANDONNEE (une face chacun), la separation DEPLACE la
    # garde A -- c'est exactement ce qui avait fait croire a une contradiction.
    m2 = DamageModifiers()
    m2.pct_list.append((1.5, None))
    m2.pct_list_defender.append((0.7, None))
    got2 = tuple(int(apply_pierce_and_modifiers(b, 100, 0, m2, attacker_additive_pre=True))
                 for b in (725, 1087))
    assert got2 == (762, 1142), ("l'attribution de face ABANDONNEE devait rendre 762/1142, obtenu "
                                 "%s -- si elle rend 761/1141, les deux faces sont refusionnees"
                                 % (got2,))


def test_les_faces_MESUREES_sont_CABLEES_dans_les_classes_d_effet():
    """#437-r1-r1-r1 -- LE CABLAGE, garde a part, et c'est necessaire : tous les crans ci-dessus
    construisent leur `DamageModifiers` A LA MAIN, donc ils restent VERTS si une classe d'effet
    cesse de declarer sa face NATIVE. C'est exactement le trou qu'avait laisse le drapeau.

    Les CINQ effets ci-dessous sont ceux dont la face NATIVE differe de celle de leur canal de PORT
    **avec une consequence arithmetique** (canal POURCENT). Les quatre autres divergences connues
    sont ADDITIVES : `PredictAttackRaw` somme le `Addition@+0x10` des DEUX accumulateurs avant
    `CalculateBaseDamageWithAllModifiers` (RE #462-r4b-r1), donc les deux attributions y predisent
    le MEME nombre -- regime DEGENERE, garde par le probe et non ici.

    La table exhaustive (59 classes) est derivee des tables de symboles par
    `scripts/python/probe_437r1r1r1_effect_face_table.py` ; ce cran verrouille le sous-ensemble qui
    DEPLACE une valeur."""
    from engine.entities.effects.factory import EFFECT_CLASSES

    attendu = {
        # effet du port                        -> (attribut, face NATIVE)
        "Terrifying_ExtraDefense":              ("DEFENSE_MALUS_NATIVE_FACE", "attacker"),
        "MartialKatah_DmgReduction":            ("DEFENSE_MALUS_NATIVE_FACE", "attacker"),
        "Markerlight":                          ("DEFENSE_MALUS_NATIVE_FACE", "attacker"),
        "DaughterOfTheAbyss_ExtraDamagePct":    ("AURA_DEFENSE_MALUS_NATIVE_FACE", "attacker"),
        "Stunned_DamageModifier":               ("ATTACK_BONUS_NATIVE_FACE", "defender"),
    }
    for nom, (attr, face) in attendu.items():
        cls = EFFECT_CLASSES.get(nom)
        assert cls is not None, "effet %s absent du registre -- cran a re-deriver" % nom
        got = getattr(cls, attr, None)
        assert got == face, (
            "%s.%s = %r, attendu %r : le natif verse sa contribution POURCENT dans l'accumulateur "
            "%s (slot virtuel lu dans `data/symbols/<build>/frida/{classes,methods}.tsv`). Sans "
            "cette declaration, l'entree retombe sur la face de son CANAL DE PORT et prend le "
            "mauvais `Round`." % (cls.__name__, attr, got, face, face))


def test_add_modifier_route_bien_sur_la_face():
    """Le FOYER de routage, teste sur son comportement et pas sur sa forme : `add_modifier` doit
    ranger une entree POURCENT dans `pct_list` ou `pct_list_defender` selon `native_face`, et faire
    de meme pour le canal `Multiplier@0x30` (`from_stat_mod`)."""
    from engine.services.damage_modifiers import add_modifier
    from engine.services.effect_bonus import EffectBonus

    m = DamageModifiers()
    add_modifier(m, EffectBonus("PercentDecrease", 30, native_face="attacker"))
    add_modifier(m, EffectBonus("PercentDecrease", 75, native_face="defender"))
    assert [round(v, 6) for v, _c in m.pct_list] == [0.7]
    assert [round(v, 6) for v, _c in m.pct_list_defender] == [0.25]

    s = DamageModifiers()
    add_modifier(s, EffectBonus("PercentIncrease", 50, from_stat_mod=True, native_face="defender"))
    assert round(s.multiplicative, 6) == 1.0 and round(s.multiplicative_defender, 6) == 1.5


def test_un_round_par_face_est_la_loi():
    """La loi native ne se lit pas sur le NOMBRE D'APPELS mais sur le NOMBRE DE FACES non vides.
    Deux entrees sur UNE face se composent sans arrondi entre elles (#98) ; une entree sur CHAQUE
    face en prend un chacune. Le port doit donc rendre la MEME chose pour `[a, b] / []` que pour
    `[a*b] / []`, et une chose DIFFERENTE pour `[a] / [b]` des que `a` produit un demi-entier."""
    def _val(att, deff, base):
        m = DamageModifiers()
        m.pct_list.extend((v, None) for v in att)
        m.pct_list_defender.extend((v, None) for v in deff)
        return int(apply_pierce_and_modifiers(base, PIERCE, ARMOR, m, attacker_additive_pre=True))

    for base in (3614, 3630, 5422, 5446):
        assert _val((1.25, 0.25), (), base) == _val((1.25 * 0.25,), (), base), (
            "base %d : deux entrees sur la MEME face doivent se composer SANS arrondi entre elles"
            % base)
    # DISCRIMINANTES : `base x 1.25` tombe sur un demi-entier, donc la face gouverne.
    for base in (3614, 3630, 5422):
        assert _val((1.25,), (0.25,), base) == _val((1.25, 0.25), (), base) + 1, (
            "base %d : une entree PAR FACE doit prendre un `Round` chacune (donc +1 ici) -- sinon "
            "la face ne gouverne plus rien et les cellules de #437-r1 retombent" % base)
    # TEMOIN NON DISCRIMINANT, garde volontairement : `5446 x 1.25 = 6807.5` arrondit vers le haut
    # ET la chaine unique atteint la meme cellule. Un accord n'est donc PAS une preuve de modele.
    assert _val((1.25,), (0.25,), 5446) == _val((1.25, 0.25), (), 5446) == 1702


def test_no_op_quand_une_face_est_vide():
    """La separation est STRICTEMENT NO-OP des qu'une des deux `%-list` est vide -- c'est ce qui
    conserve tous les regimes a UNE face deja mesures (#446-r2 `T` et `A`, le balayage d'armure de
    #462-r4a, les cellules #462-r4d). `apply_pct_entries([])` rend la valeur INCHANGEE, sans
    `Round` : il n'y a donc aucun arrondi surnumeraire a fabriquer.

    On le mesure en CONFRONTANT la sequence a deux appels au regroupement en UN seul (le modele
    d'avant #437-r1), reconstruit ici -- il n'y a plus de drapeau a basculer, donc le contre-modele
    doit etre ECRIT pour que la garde puisse encore rougir."""
    from engine.services.damage_modifiers import apply_pct_entries, \
        calculate_base_damage_with_modifiers
    from engine.services.static_battle_rules import get_damage_with_piercing

    def _chaine_unique(base, att, deff):
        d = get_damage_with_piercing(base, PIERCE, ARMOR)
        d = max(0, apply_pct_entries(d, [(v, None) for v in att] + [(v, None) for v in deff]))
        d = calculate_base_damage_with_modifiers(d, 1.0)
        return int(calculate_base_damage_with_modifiers(d, 1.0))

    for att, deff in (((1.25,), ()), ((), (0.25,)), ((), ())):
        m = DamageModifiers()
        m.pct_list.extend((v, None) for v in att)
        m.pct_list_defender.extend((v, None) for v in deff)
        for base in (3614, 3621, 3630, 5422, 5446, 1445, 907):
            a = int(apply_pierce_and_modifiers(base, PIERCE, ARMOR, m,
                                               attacker_additive_pre=True))
            b = _chaine_unique(base, att, deff)
            assert a == b, ("faces att=%s def=%s base=%d : la separation a DEPLACE une valeur "
                            "alors qu'une face est vide (%s vs %s)" % (att, deff, base, a, b))
