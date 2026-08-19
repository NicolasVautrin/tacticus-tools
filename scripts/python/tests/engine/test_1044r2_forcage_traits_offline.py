"""#1044-r2 -- la BORNE du substrat de repli des traits, et l'arithmetique qui l'ETABLIT.

CRITERE BINAIRE, pose avant la methode :

    « Porter le forcage `{Hero, NPC, Summon}` dans le substrat de REPLI repare-t-il plus de cas
      qu'il n'en casse ? »

La reponse est NON, et elle est CHIFFREE -- pas argumentee. C'est ce que ce fichier fige.

CE QUE LE NATIF FAIT (`rnca9r7q6c`), les DEUX surcharges d'
`IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` :

    (3 args) ecrit UN trait, retire les deux autres, sur `BaseUnitComponent+0x40` :
        Hero   (0) : Add(0x10 Hero)      Remove(0x7e6 NPC)  Remove(2 Summon)
        NPC    (1) : Remove(0x10 Hero)   Add(0x7e6 NPC)     Remove(2 Summon)
        Summon (2) : Remove(0x10 Hero)   Remove(0x7e6 NPC)  Add(2 Summon)

    (4 args) choisit lequel :
        heroDeDroit = !hasParent && !Contains(coll, NPC) && !Contains(coll, Summon)
        ov = options.<Nullable<UnitOverrideType> @+0x8>   (inatteignable depuis la BC, #1044-r1)
        ov.Value si presente ; sinon Hero si heroDeDroit ; sinon RETURN 0 (aucune ecriture)

CE QUE CE FICHIER GARDE, ETAGE PAR ETAGE :

  [1] les TROIS ordinaux, QUALIFIES sur le mirror -- `0x10`/`2`/`0x7e6` designent bien
      `Hero`/`Summon`/`NPC`, et pas trois entiers qui se trouvent la ;
  [2] le mirror `add_unit_type_traits` : table des trois branches + le `return 0` ;
  [3] l'ECART reel du repli (`gagnent` / `perdent`) et la PARTITION EXHAUSTIVE (= le nombre
      d'entrees du catalogue) -- un recenseur qui ne partitionne pas peut sous-compter sans qu'on
      le voie ; les comptes eux-memes sont dans `ATTENDU`, RE-DERIVES et jamais cites de memoire ;
  [4] LE POINT QUI DECIDE : evaluer le forcage sur le KIT (seul substrat du repli) fait diverger
      BEAUCOUP plus de verdicts qu'il n'en repare, TOUS dans le sens permissif. C'est ce qui rend
      « nommer la borne » une MESURE et non un renoncement ;
  [5] la borne est ECRITE la ou un futur portage la lira (docstring d'`unit_trait_names`), et
      `entity_trait_names` court-circuite bien la derivation quand la mesure existe.

Aucun runner, aucune session Frida. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engine.entities.traits.unit_trait import (UnitTrait, entity_trait_names,   # noqa: E402
                                               unit_trait_names)
from probe_1044r2_ecart_forcage_traits import (HERO, NPC, SUMMON,               # noqa: E402
                                               add_unit_type_traits)

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r12).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/tests/engine/conftest.py",
        # PROPRE A CE FICHIER : le substrat borne, le mirror du forcage, et la SOURCE des chiffres.
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/probe_1044r2_ecart_forcage_traits.py",
        # Les entrees et leurs `Traits` vivent dans le seed BC ; le kit, dans le gameconfig qu'il
        # porte. Un seed different change TOUS les comptes de l'etage 3 et 4 -- c'est arrive au
        # passage de la capture (175) au catalogue forge (717), et ce declencheur l'a vu.
        "data/seed-bc.json",
    ),
    # Les trois ordinaux sont apparies par NOM au build : un renumerotage change l'etage 1.
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : le mirror des deux surcharges d'`AddUnitTypeTraits`, l'ecart "
              "CHIFFRE du substrat de repli (14 / 0 / partition 175) et surtout la mesure qui "
              "TRANCHE contre le portage (47 verdicts divergents si le forcage est evalue sur le "
              "kit). Aucun runner, aucune session Frida.",
}

#: Les comptes MESURES (`probe_1044r2_ecart_forcage_traits.py`).
#:
#: ⚠ RE-DERIVES le 2026-08-19 (#10039) : `data/seed-bc.json` n'est plus la capture d'UNE bataille
#: (175 entrees) mais un catalogue FORGE par `Idun.Source.IdunBattle.View.BattleConfigBuilder`
#: (717 entrees, lineup 127/127, summons 65/65, npc 489/491). TOUS les comptes de l'etage 3 et 4
#: en dependent -- c'est exactement ce que le message de l'etage 3 annonce, et pourquoi
#: `data/seed-bc.json` figure au DECLENCHEUR ci-dessus.
#:
#: Ce qui n'a PAS bouge, et c'est le point du fichier : `perdent` reste **0** (propriete
#: STRUCTURELLE, cf. etage 3b) et le rapport `divergents` >> `gagnent` est CONFIRME, meme
#: RENFORCE -- 47/14 (facteur 3,4) sur la capture, 233/17 (facteur 13,7) sur le catalogue. La
#: borne n'a pas seulement tenu : le substrat plus large la rend plus nette.
#:
#: Avant (capture, 175) : gagnent 14, perdent 0, deja_hero_kit 0, deja_hero_bc 98, intactes 63,
#: divergents 47.
ATTENDU = {"gagnent": 17, "perdent": 0, "deja_hero_kit": 0, "deja_hero_bc": 438,
           "intactes": 262, "divergents": 233, "total": 717}


def _mesure():
    """Rejoue la mesure du probe, sans passer par son `main` (qui imprime)."""
    import json

    import gameconfig as GC
    from probe_1044r2_ecart_forcage_traits import SEED_BC
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    out = {k: 0 for k in ATTENDU}
    units = bc.get("Units") or []
    out["total"] = len(units)
    for u in units:
        vis = str(u.get("VisualId") or str(u.get("Id") or "").split(":")[0])
        depart = {str(t) for t in (u.get("Traits") or []) if t is not None}
        kit = {str(x) for x in ((GC.unit(vis) or {}).get("traits") or ())}
        apres, apres_kit = (add_unit_type_traits(depart, has_parent=False),
                            add_unit_type_traits(kit, has_parent=False))
        if (apres is None) != (apres_kit is None):
            out["divergents"] += 1
        if apres is None:
            out["intactes"] += 1
            continue
        if HERO.name in depart:
            out["deja_hero_bc"] += 1
        elif HERO.name in kit:
            out["deja_hero_kit"] += 1
        else:
            out["gagnent"] += 1
        if any(t in depart and t not in apres for t in (NPC.name, SUMMON.name)):
            out["perdent"] += 1
    return out


# ---------------------------------------------------------------------------------------------
# [1] LES TROIS ORDINAUX, QUALIFIES
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("ordinal,membre", [(0x10, "Hero"), (2, "Summon"), (0x7e6, "NPC")])
def test_etage1_ordinaux_qualifies(ordinal, membre):
    """Le decompile ecrit `0x10`, `2`, `0x7e6`. Le NOM est le seul canal ou une confusion d'enum
    serait visible -- un ordinal juste aujourd'hui devient faux au build suivant, en silence."""
    assert UnitTrait(ordinal).name == membre


# ---------------------------------------------------------------------------------------------
# [2] LE MIRROR DES DEUX SURCHARGES
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("override,attendus,absents", [
    (int(HERO), {"Hero"}, {"NPC", "Summon"}),
    (int(NPC), {"NPC"}, {"Hero", "Summon"}),
    (int(SUMMON), {"Summon"}, {"Hero", "NPC"}),
])
def test_etage2_trois_branches_posent_UN_trait_et_retirent_les_deux_autres(override, attendus,
                                                                          absents):
    depart = {"Hero", "NPC", "Summon", "Imperial"}      # les trois presents -> les Remove MORDENT
    out = add_unit_type_traits(depart, has_parent=False, override=override)
    assert attendus <= out and not (absents & out)
    assert "Imperial" in out, "le forcage ne touche QUE les trois traits de type"


def test_etage2b_heroDeDroit_et_le_return0():
    """La regle du regime SANS override, dans les deux sens."""
    assert add_unit_type_traits({"Imperial"}, has_parent=False) == {"Imperial", "Hero"}
    # `hasParent` ou l'un des deux marqueurs -> `return 0` : AUCUNE ecriture (pas un ensemble vide)
    assert add_unit_type_traits({"Imperial"}, has_parent=True) is None
    assert add_unit_type_traits({"NPC"}, has_parent=False) is None
    assert add_unit_type_traits({"Summon"}, has_parent=False) is None


# ---------------------------------------------------------------------------------------------
# [3] L'ECART REEL, ET SA PARTITION EXHAUSTIVE
# ---------------------------------------------------------------------------------------------
def test_etage3_ecart_chiffre_et_partition():
    m = _mesure()
    assert m["total"] == ATTENDU["total"], (
        "le seed BC ne porte plus %d unites mais %d -- tous les comptes ci-dessous changent de sens"
        % (ATTENDU["total"], m["total"]))
    for k in ("gagnent", "perdent", "deja_hero_kit", "deja_hero_bc", "intactes"):
        assert m[k] == ATTENDU[k], "%s : mesure %d, fige %d" % (k, m[k], ATTENDU[k])
    somme = m["gagnent"] + m["deja_hero_kit"] + m["deja_hero_bc"] + m["intactes"]
    assert somme == m["total"], (
        "PARTITION INCOMPLETE (%d / %d) : une categorie n'est pas comptee, donc le recensement "
        "peut sous-compter l'ecart sans que rien ne rougisse" % (somme, m["total"]))


def test_etage3b_le_zero_de_perdent_est_STRUCTUREL():
    """`0 perdent` n'est pas une chance du seed : `heroDeDroit` EXIGE l'absence des deux marqueurs,
    donc la branche Hero ne peut jamais en retirer un. On le montre sur le mirror, pas sur le
    corpus -- un zero mesure sur un seul substrat ne prouverait pas la propriete."""
    for marqueur in (NPC.name, SUMMON.name):
        assert add_unit_type_traits({marqueur, "Imperial"}, has_parent=False) is None


# ---------------------------------------------------------------------------------------------
# [4] LE POINT QUI DECIDE
# ---------------------------------------------------------------------------------------------
def test_etage4_porter_sur_le_KIT_casserait_plus_qu_il_ne_repare():
    """CE QUI REND « NOMMER LA BORNE » UNE MESURE. Le forcage se decide sur `BC.Units[].Traits` ;
    le repli n'a que le kit gameconfig. Evaluer le MEME forcage sur le kit fait diverger BEAUCOUP
    plus de verdicts qu'il n'en repare -- et dans le sens PERMISSIF (`Hero` ouvre des gates).

    Le rapport est ce qui compte, pas le chiffre : 47/14 sur la capture a 175 entrees, 233/17 sur
    le catalogue forge a 717. L'assertion de rapport ci-dessous est donc la garde REELLE ; le
    chiffre exact vit dans `ATTENDU` et se re-derive."""
    m = _mesure()
    assert m["divergents"] == ATTENDU["divergents"], (
        "divergences kit/BC : mesure %d, fige %d" % (m["divergents"], ATTENDU["divergents"]))
    assert m["divergents"] > m["gagnent"], (
        "le rapport s'est INVERSE (%d divergences pour %d reparations) : la borne n'est plus la "
        "bonne reponse, RE-TRANCHER au lieu de garder ce verdict"
        % (m["divergents"], m["gagnent"]))


# ---------------------------------------------------------------------------------------------
# [5] LA BORNE EST ECRITE LA OU ON LA LIRA, ET LA MESURE COURT-CIRCUITE LA DERIVATION
# ---------------------------------------------------------------------------------------------
def test_etage5_borne_ecrite_dans_la_docstring():
    """Un futur portage lira `unit_trait_names` avant de la modifier. Si la borne n'y est pas, il
    refera le raisonnement -- et rien ne dit qu'il refera la mesure."""
    doc = unit_trait_names.__doc__ or ""
    assert "AddUnitTypeTraits" in doc and "#1044-r2" in doc, (
        "la borne a disparu de la docstring : le prochain lecteur ne saura pas qu'elle est MESUREE")


def test_etage5b_la_mesure_court_circuite_la_derivation():
    """La reponse correcte n'est pas le repli, c'est `traits_measured`. Sans cet etage, l'etage 4
    se lirait comme « on ne peut rien faire »."""
    class _Ctx:
        traits = ["Hero", "Imperial"]
        traits_measured = True
        visual_id = "necroOverlord"
    assert entity_trait_names(_Ctx(), "necroOverlord") == frozenset({"Hero", "Imperial"}), (
        "quand `combatSnapshot.units[].traits` a parle, rien ne doit etre re-derive par-dessus")
