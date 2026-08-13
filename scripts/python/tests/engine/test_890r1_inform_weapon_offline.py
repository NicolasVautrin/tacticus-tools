"""#890-r1 -- `InformWeapon` dans l'arbre de `StranglethornCannon` : la feuille EXISTAIT, le
cablage manquait, et le `Nullable` n'etait PAS VIDE.

L'enonce du residu disait << le noeud `DSLBehaviors$$InformWeapon` n'est pas materialise en
feuille >>. **PERIME** : la feuille `runner/abilities/behaviours/combat.py::InformWeapon` existe
depuis longtemps et deux autres arbres l'utilisent (`admec`, `blacktemplars`). Ce qui manquait,
c'est le CABLAGE dans l'arbre `1056`.

⚠ **ET LA NOTE DU PORT LISAIT LE CALL-SITE A L'ENVERS.** Elle ecrivait
`InformWeapon(Nullable<DamageProfileType>(), null, null)` -- un `Nullable` VIDE. Relu (#890-r1,
build `rnca9r7q6c`), `StranglethornCannonAbility$$ExecuteBehaviour` construit
`Nullable__ctor(&local_210, local_res8)` sur le MEME `local_res8` que les DEUX
`AttackWithAttackDamage`, c'est-a-dire la VALEUR de `GetDamageProfile(config@0x60)`. L'ecart
comptait : `DSLBehaviors$$InformWeapon` ecrit

    tags[0x93 Attack_Weapon_DamageProfile] = hasValue ? (int)value : **-1**

donc un `Nullable` vide aurait fait ecrire `-1` (`DamageProfileType.None_`) la ou le natif ecrit
`Blast` -- MESURE live : `18` (`test_890_hive_tyrant_live.py::
test_cannon_inform_weapon_is_emitted_by_native_only_live`).

Les DEUX autres arguments sont des litteraux `0` : `Attack_Weapon_IsMelee = 0`, et
`Attack_Weapon_Use_Special` **ABSENT** (le natif ne pose cette 3e cle que `if (useSpecial != 0)`).

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe l'arbre `tyranids`, donc le registre
    # d'abilities, les selecteurs, les formules et le gameconfig. Declarer etroit produirait un
    # FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` -- aucune valeur n'est figee depuis le binaire ; ce qui est fige, c'est la
    # STRUCTURE de l'arbre et les DEUX litteraux du call-site, lus au decompile.
    "build": False,
    # `toujours: True` : offline, aucun runner, < 2 s.
    "toujours": True,
    "raison": "Cablage d'`InformWeapon` en TETE de l'arbre `1056 StranglethornCannon` : sa "
              "POSITION (donc l'ordre de `state.rng`), son profil NON NUL, et les deux litteraux "
              "`isMelee`/`useSpecial` du call-site.",
}

import pytest

from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage, InformWeapon


def _aplatir(noeud, out=None):
    """Feuilles d'un arbre `Seq`/`AtomicGroup`, DANS L'ORDRE d'execution."""
    out = [] if out is None else out
    enfant = getattr(noeud, "child", None)
    if enfant is not None:
        return _aplatir(enfant, out)
    g, d = getattr(noeud, "left", None), getattr(noeud, "right", None)
    if g is not None or d is not None:
        if g is not None:
            _aplatir(g, out)
        if d is not None:
            _aplatir(d, out)
        return out
    out.append(noeud)
    return out


@pytest.fixture(name="feuilles_1056")
def _feuilles_1056():
    from engine.runner.abilities.tyranids import stranglethorn_cannon_tree
    f = _aplatir(stranglethorn_cannon_tree())
    assert len(f) == 3, "l'arbre doit porter TROIS feuilles (inform, main, splash) : %s" % \
        [type(x).__name__ for x in f]
    return f


def test_inform_weapon_est_la_PREMIERE_feuille(feuilles_1056):
    """`op_BitwiseAnd(op_BitwiseAnd(inform, main), splash)` : l'association du natif met `inform`
    en TETE. Le noeud etant COMBAT-INERTE (0 tirage, 0 mutation), sa presence ne DEPLACE aucun
    tirage -- mais sa POSITION est ce qui rend la cascade d'events comparable event-a-event."""
    assert isinstance(feuilles_1056[0], InformWeapon)
    assert isinstance(feuilles_1056[1], AttackWithAttackDamage), "main en 2e"
    assert isinstance(feuilles_1056[2], AttackWithAttackDamage), "splash en 3e"


def test_le_profil_informe_N_EST_PAS_NUL_et_vaut_celui_de_l_ability(feuilles_1056):
    """LE piege du residu. Un `Nullable` vide ferait ecrire `-1` = `DamageProfileType.None_` ;
    le natif passe la VALEUR (`local_res8`, le meme buffer que les deux attaques)."""
    from engine.runner.abilities.tyranids import STRANGLETHORN_PROFILE

    inform = feuilles_1056[0]
    assert inform.profile is not None, \
        "un profil `None` ecrirait `Attack_Weapon_DamageProfile = -1`, le natif ecrit `Blast`"
    assert inform.profile == STRANGLETHORN_PROFILE == "Blast"
    assert feuilles_1056[1].profile == inform.profile, \
        "le natif passe le MEME `local_res8` a l'inform et aux deux attaques"


def test_les_deux_litteraux_du_call_site_sont_a_ZERO(feuilles_1056):
    """`isMelee` et `useSpecial` sont des litteraux du CALL-SITE, jamais deduits.

    ⚠ `is_melee=False` ici ne CONTREDIT PAS `STRANGLETHORN_IS_MELEE = None` : ce sont deux
    questions distinctes -- le TAG d'arme du flux (un `bool` natif) contre la NATURE du coup
    (`attackRangeType` du gameconfig, absent pour `1056`). Les confondre reintroduirait l'ecart
    que la docstring de `STRANGLETHORN_IS_MELEE` documente."""
    inform = feuilles_1056[0]
    assert inform.is_melee is False
    assert inform.use_special is False


def test_le_tag_use_special_reste_ABSENT_quand_le_litteral_est_zero():
    """`if ((char)useSpecial != 0) tags[0x94] = ...` -- la 3e cle n'est POSEE que si le litteral est
    non nul. Un port qui l'ecrirait toujours ajouterait une cle que le natif n'emet pas."""
    from engine.streams.tag_key import TagKey

    sans = InformWeapon("Blast", is_melee=False, use_special=False).tags()
    avec = InformWeapon("Blast", is_melee=False, use_special=True).tags()
    assert int(TagKey.Attack_Weapon_Use_Special) not in sans, \
        "cle `Use_Special` POSEE alors que le litteral est 0"
    assert int(TagKey.Attack_Weapon_Use_Special) in avec, \
        "temoin NON NUL : la cle DOIT apparaitre quand le litteral est non nul"
