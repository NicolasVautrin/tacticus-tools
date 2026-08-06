"""#419-r1-tr14-r4-r2 -- GARDE hors ligne des trois tags d'`InformWeapon`.

Le PROBE mesure (`probe_419r1tr14r4r2_inform_weapon_tags.py` : cast live + contre-epreuve) ; ce
fichier-ci FIGE ce qui a ete mesure, sans runner.

Ce qu'il garde, et pourquoi chaque etage existe :

  [1] les TROIS ordinaux du mirror `TagKey` sont ceux du BUILD (`data/symbols/<CURRENT>/frida/
      enums.tsv`). Un mirror regenere apres un renumerotage redeviendrait vert tout seul ; ce qui
      compte, c'est que l'ordinal ECRIT AU SITE reste celui du build.
  [2] la structure du dict pose : DEUX cles inconditionnelles, la troisieme SEULEMENT si
      `use_special` -- c'est le `if ((char)useSpecial != '\\0')` du decompile.
  [3] `profile is None` -> `-1`, et `-1` EST `DamageProfileType.None_` (le natif ecrit `-1` quand
      le `Nullable<DamageProfileType>` est vide ; ce n'est PAS un weaponId).
  [4] les DEUX porteurs portes concordent avec le FLUX NATIF mesure le 2026-08-06.
  [5] anti-regime-degenere : les deux porteurs DIFFERENT sur `IsMelee`. Sans cet etage, un port
      qui ecrirait une CONSTANTE au lieu de lire le litteral de chaque appelant passerait [4] sur
      un seul porteur.
  [6] un profil INCONNU LEVE -- jamais un `-1` muet, qui se lirait comme un `Nullable` vide.

⚠ Le vice que ce fichier garde est une DOCSTRING FAUSSE, pas un nombre faux : l'ancienne
description du foyer intervertissait `0x92`/`0x93`, nommait la classe construite
`ActivateEffectBehaviour` (qui n'a AUCUN ctor a `Dictionary`) et inventait une operation `0x2c`.
Rien ne cassait, aucun test ne rougissait -- exactement le patron de #419-r1-tr14-r1-r1.

ASCII only (cp1252). Aucun runner, aucun RPC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]              # scripts/python
sys.path.insert(0, str(PYDIR))

import stream_events as SE                                # noqa: E402
from engine.dsl.effects import ExecutionContext           # noqa: E402
from engine.streams.tag_key import TagKey                 # noqa: E402
from engine.entities.damage_profile_type import DamageProfileType   # noqa: E402
from engine.runner.abilities.behaviours.combat import InformWeapon  # noqa: E402
from engine.runner.abilities.deathguard import flail_swing_tree     # noqa: E402
from engine.runner.abilities.admec import sentinel_directives_tree  # noqa: E402

# ORDINAUX MESURES A LA CONVERSION (2026-08-06, build `rnca9r7q6c`) -- figes ici pour que [1]
# garde la valeur ECRITE AU SITE, pas seulement l'accord mirror <-> build.
ORDINAUX_AU_SITE = {
    "Attack_Weapon_IsMelee": 0x92,
    "Attack_Weapon_DamageProfile": 0x93,
    "Attack_Weapon_Use_Special": 0x94,
}

# FLUX NATIF mesure le 2026-08-06 (MC1_67, seed 41902) : deux casts, deux dicts de tags.
MESURE_NATIVE = {
    "FlailSwing": {"Attack_Weapon_DamageProfile": 14, "Attack_Weapon_IsMelee": 1},
    "SentinelDirectives": {"Attack_Weapon_DamageProfile": 0, "Attack_Weapon_IsMelee": 0},
}
ARBRES = {"FlailSwing": flail_swing_tree, "SentinelDirectives": sentinel_directives_tree}


def _tags(feuille: InformWeapon) -> dict:
    ctx = ExecutionContext(state=None, rng=None)
    feuille.execute(None, ctx)
    return dict(next(p["tags"] for n, p in ctx.emitted if n == "InformWeapon"))


def _feuille(node):
    if isinstance(node, InformWeapon):
        return node
    for attr in ("left", "right", "a", "b", "first", "second", "nodes", "children"):
        v = getattr(node, attr, None)
        if v is None:
            continue
        for sub in (v if isinstance(v, (list, tuple)) else [v]):
            f = _feuille(sub)
            if f is not None:
                return f
    return None


def test_1_ordinaux_tagkey_contre_le_build():
    """Les trois cles du foyer sont celles du BUILD, et l'ordinal ecrit au site n'a pas glisse."""
    par_nom = SE._par_nom("IdunBattle.Streams.TagKey")
    assert par_nom, "enums.tsv illisible -- l'etage ne prouverait rien (assertion de non-vide)"
    for nom, ordinal in ORDINAUX_AU_SITE.items():
        assert par_nom.get(nom) == ordinal, (
            f"TagKey.{nom} vaut {par_nom.get(nom)} au build, {ordinal} au site")
        assert int(getattr(TagKey, nom)) == ordinal, (
            f"mirror TagKey.{nom} = {int(getattr(TagKey, nom))} != {ordinal} mesure a la conversion")


def test_2_structure_du_dict_pose():
    """DEUX cles inconditionnelles ; la troisieme SEULEMENT si `use_special`."""
    sans = _tags(InformWeapon("Power", is_melee=True, use_special=False))
    assert set(sans) == {TagKey.Attack_Weapon_DamageProfile, TagKey.Attack_Weapon_IsMelee}, sans
    avec = _tags(InformWeapon("Power", is_melee=True, use_special=True))
    assert set(avec) == {TagKey.Attack_Weapon_DamageProfile, TagKey.Attack_Weapon_IsMelee,
                         TagKey.Attack_Weapon_Use_Special}, avec
    assert avec[TagKey.Attack_Weapon_Use_Special] == 1
    # `isMelee` est INCONDITIONNEL : il vaut 0, il est quand meme pose (contraste avec `useSpecial`)
    zero = _tags(InformWeapon("Physical", is_melee=False, use_special=False))
    assert zero[TagKey.Attack_Weapon_IsMelee] == 0
    assert TagKey.Attack_Weapon_IsMelee in zero


def test_3_profil_absent_vaut_moins_un_et_cest_None_():
    """`damageProfileType.HasValue ? (int)value : -1` -- et `-1` EST un membre nomme de l'enum."""
    t = _tags(InformWeapon(None, is_melee=False))
    assert t[TagKey.Attack_Weapon_DamageProfile] == -1
    assert int(DamageProfileType.None_) == -1, "le -1 natif n'est pas un sentinel, c'est `None_`"


@pytest.mark.parametrize("nom", sorted(MESURE_NATIVE))
def test_4_porteurs_concordent_avec_le_flux_natif(nom):
    """Le port pose EXACTEMENT ce que le flux natif porte, cle par cle."""
    f = _feuille(ARBRES[nom]())
    assert f is not None, f"aucune feuille InformWeapon dans l'arbre porte de {nom}"
    porte, natif = _tags(f), MESURE_NATIVE[nom]
    for cle, attendu in natif.items():
        assert int(porte[getattr(TagKey, cle)]) == int(attendu), (
            f"{nom}.{cle}: port={porte.get(getattr(TagKey, cle))} != natif={attendu}")
    assert TagKey.Attack_Weapon_Use_Special not in porte, (
        f"{nom}: le flux natif ne porte PAS Use_Special (`useSpecial == 0` au litteral)")


def test_5_les_deux_porteurs_different_sur_is_melee():
    """ANTI-REGIME-DEGENERE. `isMelee` est le litteral de CHAQUE appelant, pas une constante du
    noeud : `FlailSwingAbility$$ExecuteBehaviour` passe 1, `SentinelDirectivesAbility$$Execute
    Behaviour` passe 0. Si les deux devenaient egaux, [4] ne discriminerait plus rien."""
    vals = {n: int(_tags(_feuille(ARBRES[n]()))[TagKey.Attack_Weapon_IsMelee]) for n in ARBRES}
    assert len(vals) == 2, vals
    assert len(set(vals.values())) == 2, (
        f"regime DEGENERE : les deux porteurs portent le meme isMelee {vals}")
    # ...et l'interversion 0x92/0x93 (la faute de l'ancienne docstring) est INERTE sur
    # SentinelDirectives (Physical == 0 ET isMelee == 0) : c'est FlailSwing qui la revele.
    sd = _tags(_feuille(sentinel_directives_tree()))
    assert sd[TagKey.Attack_Weapon_DamageProfile] == sd[TagKey.Attack_Weapon_IsMelee] == 0, (
        "l'equivalence algebrique a bouge : re-mesurer la contre-epreuve M4b")
    fs = _tags(_feuille(flail_swing_tree()))
    assert fs[TagKey.Attack_Weapon_DamageProfile] != fs[TagKey.Attack_Weapon_IsMelee], (
        "FlailSwing ne separe plus 0x92 de 0x93 : plus AUCUN porteur ne revele l'interversion")


def test_6_profil_inconnu_leve():
    """Un nom hors de l'enum est un BUG DE PORT : il doit LEVER, jamais rendre un `-1` muet --
    sinon il se lirait comme un `Nullable<DamageProfileType>` vide."""
    with pytest.raises(KeyError):
        _tags(InformWeapon("ProfilQuiNExistePas", is_melee=True))
