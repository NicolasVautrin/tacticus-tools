"""#477-r18-r4 -- GARDE des deux lecteurs de `TagKey` ajoutes au probe du perimetre.

Le probe `probe_477r18_deroule_perimetre.py` ne tourne qu'avec `ghidra-mcp` ALLUME et un flux
live : son etape [8] est une mesure, pas un cliquet. Ce qui peut se casser EN SILENCE, lui, est
purement textuel -- les deux PARSEURS qui lisent le pseudo-C. Ce fichier les garde hors ligne,
sur des extraits VERBATIM du build `rnca9r7q6c`.

Pourquoi ces deux-la et pas l'etape [8] : une regression du parseur rend un ENSEMBLE VIDE, et un
ensemble vide se lit comme « rien a signaler ». Chaque etage assertionne donc son propre NON-VIDE
avant d'assertionner son contenu.
"""
from __future__ import annotations

import sys
from pathlib import Path

ICI = Path(__file__).resolve().parents[1]
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

import probe_477r18_deroule_perimetre as P  # noqa: E402
from engine.streams import TagKey  # noqa: E402

#: VERBATIM de `IdunBattle.Operations.TransformUnitOperation$$.cctor` -- les deux entrees de la
#: table `Dictionary<StatType, ModStatTransformConfig>` qui portent les six `TagKey` que le flux
#: EMET et que le balayage n'atteignait pas. Les stores 64 bits EMPAQUETTENT DEUX champs :
#: `local_2b8 = 0x300000002f` = champ0 `UnitStats_Movement` (0x2f), champ1 `..._Modification`
#: (0x30). La variable passee en CLE de la table (`local_res10`, un `StatType`) est HORS de la
#: plage de slots de la struct -- c'est ce qui la rend inconfondable avec un `TagKey`.
CCTOR = """
    local_2b8 = 0x300000002f;
    uStack_2b0 = 0x3100000032;
    uStack_2a0 = 0x35;
    local_298 = 0;
    local_res10[0] = 1;
    local_2a8 = 0x3400000033;
    System_Collections_Generic_Dictionaryu003C__Il2CppFullySharedGenericType____Il2CppFullySharedGenericTypeu003E__Add
              (lVar1,local_res10,&local_2b8,DAT_1833bd988);
    local_198 = 0x2b0000002a;
    uStack_190 = 0x2c0000002d;
    uStack_180 = 0;
    local_178 = 0;
    local_res10[0] = 0x10;
    local_188 = 0;
    System_Collections_Generic_Dictionaryu003C__Il2CppFullySharedGenericType____Il2CppFullySharedGenericTypeu003E__Add
              (lVar1,local_res10,&local_198,DAT_1833bd988);
"""

#: VERBATIM de la premiere entree du meme `.cctor` (`StatType.Attack`) : son dernier champ est
#: ecrit par un `CONCAT44` dont UN SEUL membre est un immediat. Sans cette forme, `0x29`
#: (`UnitStats_Attack_Override_IsModifiable`) etait perdu.
CCTOR_CONCAT = """
    local_2e8 = 0x2400000023;
    uStack_2e0 = 0x2500000026;
    uStack_2d0 = CONCAT44(uStack_2fc,0x29);
    local_2c8 = uStack_2f8;
    local_res10[0] = 0;
    local_2d8 = 0x2800000027;
    System_Collections_Generic_Dictionaryu003C__Il2CppFullySharedGenericType____Il2CppFullySharedGenericTypeu003E__Add
              (lVar1,local_res10,&local_2e8,DAT_1833bd988);
"""

#: VERBATIM de `IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(damageProfileType, isMelee,
#: useSpecial)`. Ce noeud DSL ECRIT trois tags et n'appelle JAMAIS `IStreamListener` : c'est
#: exactement ce que le canal 1 ne pouvait pas voir.
INFORM_WEAPON = """
  if (lVar1 != 0) {
    local_28[0] = 0x93;
    System_Collections_Generic_Dictionaryu003C__Il2CppFullySharedGenericType____Il2CppFullySharedGenericTypeu003E__Add
              (lVar1,local_28,local_res10,DAT_183345050);
    local_28[0] = 0x92;
    local_res10[0] = (uint)isMelee & 0xff;
    System_Collections_Generic_Dictionaryu003C__Il2CppFullySharedGenericType____Il2CppFullySharedGenericTypeu003E__Add
              (lVar1,local_28,local_res10,DAT_183345050);
    if ((char)useSpecial != '\\0') {
      local_28[0] = 0x94;
      local_res10[0] = (uint)useSpecial & 0xff;
      System_Collections_Generic_Dictionaryu003C__Il2CppFullySharedGenericType____Il2CppFullySharedGenericTypeu003E__Add
                (lVar1,local_28,local_res10,DAT_183345050);
    }
  }
"""

DAT_TAGS = {"DAT_183345050"}
#: `ModStatTransformConfig..ctor` declare HUIT parametres `IdunBattle.Streams.TagKey` -- lu dans
#: `frida/methods.tsv`, jamais compte a la main. C'est ce nombre qui donne la portee de slots.
N_CLES = 8


def test_etage1_les_six_cles_de_la_table_statique():
    """Le canal 5 rend EXACTEMENT les deux familles de la table, ni plus ni moins."""
    vals, sites = P.litteraux_table_statique(CCTOR, N_CLES)
    assert sites == 2, "les deux entrees de table doivent etre VUES (sites lus : %d)" % sites
    assert vals, "ensemble VIDE : le parseur ne mord plus, ce n'est pas une absence du binaire"
    attendus = {
        int(TagKey.UnitStats_Movement), int(TagKey.UnitStats_Movement_Modification),
        int(TagKey.UnitStats_Movement_Modification_Entity),
        int(TagKey.UnitStats_Movement_Modification_Change),
        int(TagKey.UnitStats_Movement_Override), int(TagKey.UnitStats_Movement_Override_Entity),
        int(TagKey.UnitStats_Movement_Override_IsModifiable),
        int(TagKey.UnitStats_FixedArmor), int(TagKey.UnitStats_FixedArmor_Modification),
        int(TagKey.UnitStats_FixedArmor_Modification_Entity),
        int(TagKey.UnitStats_FixedArmor_Modification_Change),
    }
    assert vals == attendus, "lu %s, attendu %s" % (sorted(vals), sorted(attendus))


def test_etage2_les_six_de_la_contre_epreuve_sont_bien_couverts():
    """Les SIX noms que l'etape [8] listait comme emis-non-atteints, un par un."""
    vals, _s = P.litteraux_table_statique(CCTOR, N_CLES)
    manquants = [n for n in ("UnitStats_FixedArmor_Modification",
                             "UnitStats_FixedArmor_Modification_Change",
                             "UnitStats_FixedArmor_Modification_Entity",
                             "UnitStats_Movement_Modification",
                             "UnitStats_Movement_Modification_Change",
                             "UnitStats_Movement_Modification_Entity")
                 if int(TagKey[n]) not in vals]
    assert not manquants, "encore emis-non-atteints : %s" % manquants


def test_etage3_le_zero_est_exclu():
    """`0` est la sentinelle « non implemente », pas un tag.

    `IdunBattle.Operations.TransformUnitOperation$$AddTagIfImplemented` commence par
    `if (key != 0)` : un champ nul n'ecrit RIEN. Les deux entrees de `CCTOR` en portent quatre.
    """
    vals, _s = P.litteraux_table_statique(CCTOR, N_CLES)
    assert int(TagKey.UnitStats_Unimplemented) == 0
    assert 0 not in vals


def test_etage4_le_concat44_rend_son_dword_litteral():
    """Ghidra fusionne deux dwords dont un seul est un immediat -- le litteral doit survivre."""
    vals, sites = P.litteraux_table_statique(CCTOR_CONCAT, N_CLES)
    assert sites == 1 and vals
    assert int(TagKey.UnitStats_Attack_Override_IsModifiable) in vals, (
        "0x29 perdu : c'est la forme CONCAT44 qui n'est plus lue")
    assert vals <= {int(x) for x in TagKey}, "valeurs HORS enum : %s" % sorted(
        vals - {int(x) for x in TagKey})


def test_etage5_le_canal4_lit_les_trois_tags_du_noeud_dsl():
    """`InformWeapon` ecrit trois `TagKey` sans jamais emettre : c'est le canal 4 qui le voit."""
    vus = P.scanner_tags(INFORM_WEAPON, DAT_TAGS)
    assert vus == {int(TagKey.Attack_Weapon_IsMelee),
                   int(TagKey.Attack_Weapon_DamageProfile),
                   int(TagKey.Attack_Weapon_Use_Special)}, sorted(vus)


def test_etage6_le_parseur_n_invente_pas():
    """CONTRE-EPREUVE du lecteur : sans slot de struct en 3e argument, il rend VIDE.

    Un parseur qui « trouverait » quelque chose ici fabriquerait de la couverture -- exactement
    le vice que le canal 5 doit eviter (un entier n'est pas un `TagKey` parce qu'il tient dans
    l'enum). Le temoin est la MEME table avec la struct passee par une variable non nommee par
    offset de pile.
    """
    sans_slot = CCTOR.replace("&local_2b8", "pvVar9").replace("&local_198", "pvVar9")
    vals, sites = P.litteraux_table_statique(sans_slot, N_CLES)
    assert sites == 0 and vals == set(), "a lu %s alors que rien n'est adressable" % sorted(vals)


def test_etage7_les_ordinaux_ecrits_ici_sont_ceux_du_build():
    """Fige l'ordinal MESURE, pas seulement le nom.

    Le mirror peut etre regenere apres un renumerotage et redevenir « coherent » alors que les
    litteraux lus dans le `.cctor` de `rnca9r7q6c`, eux, n'ont pas bouge. Sans cet etage, le
    glissement serait invisible.
    """
    assert (int(TagKey.UnitStats_FixedArmor), int(TagKey.UnitStats_FixedArmor_Modification),
            int(TagKey.UnitStats_FixedArmor_Modification_Entity),
            int(TagKey.UnitStats_FixedArmor_Modification_Change)) == (0x2A, 0x2B, 0x2C, 0x2D)
    assert (int(TagKey.UnitStats_Movement), int(TagKey.UnitStats_Movement_Modification),
            int(TagKey.UnitStats_Movement_Modification_Entity),
            int(TagKey.UnitStats_Movement_Modification_Change)) == (0x2F, 0x30, 0x31, 0x32)
    assert (int(TagKey.Attack_Weapon_IsMelee), int(TagKey.Attack_Weapon_DamageProfile),
            int(TagKey.Attack_Weapon_Use_Special)) == (0x92, 0x93, 0x94)
    assert int(TagKey.Custom_Data) == 0xCC
