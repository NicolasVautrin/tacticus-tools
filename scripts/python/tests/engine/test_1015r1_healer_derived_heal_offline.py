"""#1015-r1 -- le CLIQUET OFFLINE du trait `Healer` (18 porteurs, dont 6 en `lineup`).

LA CHAINE, LUE AU DECOMPILE (aucun maillon deduit) :

    idun...StaticBattleRules.Trait$$.cctor            dict `<Trait statics>+0x08` :
        Add(key = 0x0a UnitTrait.Healer,   value = 0x12 ActiveAbilityType.Heal)
        Add(key = 0x0c UnitTrait.Mechanic, value = 0x1c ActiveAbilityType.Repair)
    idun...StaticBattleRules.Trait$$GetActiveAbility  lit ce dict (`TryGetValue` -> `Nullable`)
    IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities   3e boucle (config@+0xd0) :
        `Level..ctor(1, 0)` -> `AbilityState..ctor(level, config@+0x74)`
        -> `ActiveAbilityComponent$$Add(type, state)`
    IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities     idem, EN BATAILLE
    IdunBattle.Operations.RemoveTraitOperation$$RemoveDerivedAbilities   l'inverse

CE QU'IL GARDE, et contre quoi :

  1. LE DICT LUI-MEME, EXACTEMENT DEUX ENTREES. En ajouter une troisieme, c'est inventer une
     derivation que le `.cctor` ne fait pas ; en retirer une, c'est amputer le mirror. Les DEUX
     sens rougissent.
  2. LE RETRAIT PAR LE PASSIF SUBSTITUTIF. `DSLBehaviors$$RemoveActiveAbility` n'a que TROIS
     appelants de code dans le build ; les trois sont ici. Sans eux, `genesBiophagus` porterait
     `18` ET `1167`, et `admecManipulus` `28` ET `1119` -- la seconde forme CONTREDIT une mesure
     live deja au depot (`test_952_hunters_beyond_death_offline`).
  3. LE CABLAGE EFFECTIF, sur les 18 porteurs, ventile par CE QUE LE NATIF EN FAIT : 4 lineup
     gardent `18`, 2 lineup la PERDENT (contre-temoins), les 12 npc la gardent.
  4. LE TRI-ETAT DU SUBSTRAT. `traits=None` = canal muet -> repli KIT ; une mesure d'entite, meme
     vide, FAIT AUTORITE. C'est la forme de piege #264 : le natif lit `UnitConfiguration.Traits`
     (`BC.Units[].Traits`), qui n'est PAS le `traits` du gameconfig.
  5. LE NOM PORTE, ET IL EST FONCTIONNEL. `ActionGenerators._heal_candidates` selectionne les
     abilities de soin par `"Heal" in ab["name"]` : un id sans nom d'enum (le repli `str(aid)`)
     serait invisible du decideur -- exactement le trou qu'on repare, redéposé un etage plus bas.

CE QU'IL NE GARDE PAS, et c'est ecrit : la FACE COMBAT n'a rien a garder ici. `18 Heal` est deja
au registre d'execution avec son masque (#931-r1, `runner/abilities/heal.py`) ; ce qui manquait
etait le canal qui la MET dans le kit, donc la face DECISION.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

#: Ce qui doit faire REJOUER ce fichier.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/active_abilities.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/ai/state_bridge.py",
        "scripts/python/engine/ai/action_generators.py",
        "scripts/python/engine/runner/abilities/heal.py",
        "scripts/python/engine/runner/abilities/repair.py",
        "scripts/python/enum_maps.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Cliquet OFFLINE de #1015-r1 : le dict `Trait$$GetActiveAbility` a deux entrees, le "
        "retrait par passif substitutif, le cablage sur les 18 porteurs et le tri-etat du "
        "substrat. Aucun runner. Le gameconfig est atteint par `enum_maps`/`gameconfig`, tous "
        "deux dans la fermeture d'imports de `state_bridge`."),
}

import pytest                                                                 # noqa: E402

import gameconfig as GC                                                       # noqa: E402
from engine.ai.state_bridge import _abilities_of                              # noqa: E402
from engine.entities.active_abilities import (                                # noqa: E402
    PASSIVE_ADDS_ACTIVE_ABILITY, PASSIVE_REMOVES_ACTIVE_ABILITY,
    TRAIT_DERIVED_ACTIVE_ABILITIES,
    derived_active_ability_ids, trait_derived_active_ability)
from engine.entities.active_ability_type import ActiveAbilityType             # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                       # noqa: E402

TRAIT = UnitTrait.Healer.name

#: Les 6 porteurs `lineup`, VENTILES par ce que le natif leur laisse -- le contre-temoin est dans
#: la donnee, pas dans un commentaire.
LINEUP_GARDENT_18 = ("adeptHospitaller", "bloodSanguinary", "deathRotbone", "ultraApothecary")
LINEUP_PERDENT_18 = {"genesBiophagus": "TwistedScience", "spaceWolfPriest": "HealingBalms"}


def _porteurs(trait: str) -> dict:
    """{seau: [unitId]} des porteurs du trait, TOUS SEAUX. Derive du gameconfig, jamais liste."""
    out: dict = {}
    idx = GC._index()
    for seau in ("lineup", "npc", "summons"):
        out[seau] = sorted(uid for uid, u in (idx[seau] or {}).items()
                           if trait in (u.get("traits") or []))
    return out


def _tous_les_unit_ids() -> list:
    """Les `unitId` des TROIS seaux, a plat. Derive du gameconfig -- une liste ecrite ici se
    perimerait au prochain patch de contenu, et le test se tairait sur le porteur qu'elle ignore."""
    d = GC.all_unit_ids()
    return sorted(v for seau in ("lineup", "npc", "summons") for v in (d.get(seau) or ()))


# ================================================================================================
# 1. LE DICT -- exactement les deux `Add` du `.cctor`
# ================================================================================================

def test_le_dict_GetActiveAbility_a_exactement_les_deux_entrees_lues():
    """`Trait$$.cctor` fait DEUX `Dictionary$$Add` sur le dict `<Trait statics>+0x08`, pas trois.

    Le test FIGE l'ensemble, pas seulement l'appartenance : une entree ajoutee << au passage >>
    (un trait dont on suppose qu'il derive une active) est le mode d'echec le plus probable, et
    l'`in` ne la verrait pas."""
    assert TRAIT_DERIVED_ACTIVE_ABILITIES == {
        UnitTrait.Healer.name: int(ActiveAbilityType.Heal),
        UnitTrait.Mechanic.name: int(ActiveAbilityType.Repair),
    }
    # Les ordinaux du dict natif, cotes CLE comme cotes VALEUR (les deux sont des enums distincts,
    # et c'est la confusion qui serait silencieuse -- cf. CLAUDE.md sur les enums homonumeriques).
    assert int(UnitTrait.Healer) == 0x0a and int(ActiveAbilityType.Heal) == 0x12
    assert int(UnitTrait.Mechanic) == 0x0c and int(ActiveAbilityType.Repair) == 0x1c
    assert trait_derived_active_ability(TRAIT) == int(ActiveAbilityType.Heal)
    # `TryGetValue` qui echoue -> `Nullable` VIDE, jamais un 0 (`ActiveAbilityType.None` = 0
    # existe : rendre 0 ferait deriver une ability REELLE de l'enum sur tout trait inconnu).
    assert trait_derived_active_ability("Flying") is None
    assert trait_derived_active_ability("PasUnTrait") is None


def test_le_dict_TRIGGERED_est_un_AUTRE_dict_et_ne_doit_pas_le_recouvrir():
    """`<Trait statics>+0x00` (`$$GetTriggeredAbility`) porte des TRIGGERED abilities et sert le
    chemin owner-effect ; `+0x08` porte des ACTIVES. Les deux registres du port sont disjoints par
    leurs CLES ici, et le resteront tant qu'aucun trait ne derive les deux."""
    from engine.entities.effects.factory import TRAIT_DERIVED_ABILITIES
    communs = set(TRAIT_DERIVED_ACTIVE_ABILITIES) & set(TRAIT_DERIVED_ABILITIES)
    assert communs == set(), (
        "un trait est dans les DEUX registres (%r) : si le natif le fait vraiment (le `.cctor` "
        "ecrit les deux dicts), c'est legitime -- mais alors VERIFIE-le au decompile avant de "
        "relacher cette assertion, elle n'est pas un dogme." % sorted(communs))


# ================================================================================================
# 2. LE RETRAIT PAR LE PASSIF SUBSTITUTIF
# ================================================================================================

def test_les_trois_RemoveActiveAbility_du_build_sont_portes():
    """`DSLBehaviors$$RemoveActiveAbility` : TROIS appelants de code, tous transcrits.

    Les valeurs sont les LITTERAUX passes aux `CreateBehaviour` (`0x12` deux fois, `0x1c` une
    fois), pas une deduction depuis le nom de l'ability substituee."""
    assert PASSIVE_REMOVES_ACTIVE_ABILITY == {
        "TwistedScience": int(ActiveAbilityType.Heal),
        "HealingBalms": int(ActiveAbilityType.Heal),
        "GalvanicField": int(ActiveAbilityType.Repair),
    }


@pytest.mark.parametrize("vid,passif", sorted(LINEUP_PERDENT_18.items()))
def test_un_porteur_Healer_qui_substitue_PERD_le_18(vid, passif):
    """`TwistedScience` / `HealingBalms` font `RemoveActiveAbility(Owner, 0x12)` a l'init. Le
    porteur garde son trait `Healer` -- c'est bien le passif qui tranche, pas le trait."""
    gu = GC.unit(vid) or {}
    assert TRAIT in (gu.get("traits") or []), (
        "%s ne porte plus le trait `%s` au gameconfig : ce test ne mesure plus ce qu'il croit "
        "(re-deriver les porteurs avant de le corriger)." % (vid, TRAIT))
    assert passif in (gu.get("passiveAbilities") or [])
    ids = [i for (i, _n) in _abilities_of(vid)]
    assert int(ActiveAbilityType.Heal) not in ids, (
        "%s garde `18 Heal` alors que `%s` la retire -- kit rendu %r" % (vid, passif, ids))


def test_le_retrait_ne_mord_QUE_sur_ce_que_le_passif_nomme():
    """Contre-epreuve : un passif substitutif de SOIN ne doit pas retirer la REPARATION, et
    reciproquement. Un registre a valeur unique (ou un `remove` inconditionnel) passerait le test
    precedent et casserait celui-ci."""
    assert derived_active_ability_ids(("Healer", "Mechanic"), ("TwistedScience",)) == [
        int(ActiveAbilityType.Repair)]
    assert derived_active_ability_ids(("Healer", "Mechanic"), ("GalvanicField",)) == [
        int(ActiveAbilityType.Heal)]
    assert derived_active_ability_ids(("Healer", "Mechanic"), ()) == [
        int(ActiveAbilityType.Heal), int(ActiveAbilityType.Repair)]
    # Un passif QUELCONQUE ne retire rien.
    assert derived_active_ability_ids(("Healer",), ("Narthecium",)) == [int(ActiveAbilityType.Heal)]


# ================================================================================================
# 3. LE CABLAGE EFFECTIF sur les 18 porteurs
# ================================================================================================

def test_les_dix_huit_porteurs_sont_ventiles_comme_le_natif_les_traite():
    """EXHAUSTIF sur la population REELLE (derivee du gameconfig, pas listee) : chaque porteur
    `Healer` recoit `18 Heal` SAUF s'il porte un passif qui la retire.

    ⚠ Le test assertionne son PROPRE non-vide : une population vide (gameconfig change de forme,
    trait renomme) rendrait toutes les boucles vraies par vacuite."""
    p = _porteurs(TRAIT)
    total = sum(len(v) for v in p.values())
    assert total == 18, (
        "population des porteurs `%s` = %d (attendu 18 : 6 lineup + 12 npc) -- si le gameconfig a "
        "bouge, RE-DERIVER et mettre a jour, ne pas relacher l'assertion. Ventilation : %r"
        % (TRAIT, total, {k: len(v) for k, v in p.items()}))
    assert len(p["lineup"]) == 6 and len(p["npc"]) == 12 and p["summons"] == []
    for seau, uids in p.items():
        for vid in uids:
            gu = GC.unit(vid) or {}
            substitue = [q for q in (gu.get("passiveAbilities") or [])
                         if PASSIVE_REMOVES_ACTIVE_ABILITY.get(q) == int(ActiveAbilityType.Heal)]
            ids = [i for (i, _n) in _abilities_of(vid)]
            if substitue:
                assert int(ActiveAbilityType.Heal) not in ids, (
                    "%s/%s substitue (%r) et garde pourtant 18 : %r" % (seau, vid, substitue, ids))
            else:
                assert int(ActiveAbilityType.Heal) in ids, (
                    "%s/%s porte `%s` sans passif substitutif et n'a PAS `18 Heal` : le canal "
                    "trait -> ability est mort. Kit rendu %r" % (seau, vid, TRAIT, ids))


@pytest.mark.parametrize("vid", LINEUP_GARDENT_18)
def test_les_quatre_lineup_confrontables_recoivent_18_avec_son_NOM(vid):
    """LE NOM EST FONCTIONNEL, pas decoratif : `ActionGenerators._heal_candidates` filtre
    `me["abilities"]` par `"Heal" in ab["name"]`. Un id sans nom d'enum passerait l'assertion
    d'appartenance et resterait INVISIBLE du decideur."""
    entrees = dict((n, i) for (i, n) in _abilities_of(vid))
    assert entrees.get(ActiveAbilityType.Heal.name) == int(ActiveAbilityType.Heal), (
        "%s : `18` absente ou nommee autrement -- entrees %r" % (vid, sorted(entrees)))
    noms_heal = [n for n in entrees if "Heal" in n]
    assert noms_heal, (
        "%s : aucune entree dont le nom contient 'Heal' -- `_heal_candidates` rendrait [] et le "
        "decideur ne proposerait AUCUN soin. Entrees %r" % (vid, sorted(entrees)))


def test_une_unite_SANS_le_trait_ne_recoit_rien():
    """Le contre-temoin de population : sans `Healer`, pas de `18`. Sans lui, un cablage
    inconditionnel (qui donnerait 18 a tout le monde) passerait tous les tests ci-dessus."""
    idx = GC._index()
    sans = [uid for uid, u in (idx["lineup"] or {}).items()
            if TRAIT not in (u.get("traits") or []) and (u.get("weapons"))]
    assert len(sans) > 50, (
        "moins de 50 unites lineup SANS `%s` : le contre-temoin est trop maigre pour prouver "
        "quoi que ce soit (%d)" % (TRAIT, len(sans)))
    fautifs = [uid for uid in sans
               if int(ActiveAbilityType.Heal) in [i for (i, _n) in _abilities_of(uid)]]
    assert fautifs == [], (
        "des unites SANS le trait `%s` recoivent `18 Heal` : %r" % (TRAIT, fautifs[:5]))


# ================================================================================================
# 4. LE TRI-ETAT DU SUBSTRAT (#264)
# ================================================================================================

def test_le_substrat_est_l_ENTITE_et_le_canal_muet_retombe_sur_le_kit():
    """Trois regimes, tous les trois exerces :

      * `traits=None` -> canal MUET, repli sur le KIT gameconfig (BORNE nommee) ;
      * une mesure d'entite qui PORTE le trait -> `18`, meme si le kit ne le porte pas ;
      * une mesure d'entite qui NE le porte PAS -> pas de `18`, meme si le kit le porte.

    Le troisieme est le seul qui distingue << mesure >> de << union avec le kit >>, et c'est le
    regime que `--unit-stat "<vis>:Traits=[...]"` produit en live."""
    porteur = LINEUP_GARDENT_18[0]                      # kit AVEC `Healer`
    heal = int(ActiveAbilityType.Heal)
    assert heal in [i for (i, _n) in _abilities_of(porteur, None, None)]
    assert heal not in [i for (i, _n) in _abilities_of(porteur, None, ("Hero", "Imperial"))], (
        "une mesure d'entite SANS `%s` laisse quand meme `18` : le kit prime sur la mesure, ce qui "
        "est l'inverse du contrat (#264)." % TRAIT)
    # Symetrique : une unite dont le KIT n'a pas le trait, mais dont l'ENTITE l'a recu en bataille
    # (`IdunBattleLogic.Entities.DSLBehaviors$$AddTrait` -> `AddTraitOperation$$AddDerivedAbilities`).
    # ⚠ L'unite doit EXISTER : un `unitId` mort rend `GC.unit(...) is None`, et les deux premieres
    # assertions passeraient par VACUITE (faute commise a l'ecriture de ce test, sur un
    # `ultraIntercessor` qui n'est pas au gameconfig).
    sans_kit = "ultraTigurius"
    gu = GC.unit(sans_kit)
    assert gu is not None, (
        "%r n'existe pas au gameconfig : ce contre-temoin ne mesure RIEN. Re-deriver une unite "
        "lineup reelle sans le trait `%s`." % (sans_kit, TRAIT))
    assert TRAIT not in (gu.get("traits") or [])
    assert heal not in [i for (i, _n) in _abilities_of(sans_kit, None, None)]
    assert heal in [i for (i, _n) in _abilities_of(sans_kit, None, (TRAIT,))], (
        "un trait ACCORDE EN BATAILLE ne derive pas son ability : "
        "`AddTraitOperation$$AddDerivedAbilities` est le jumeau EN BATAILLE de la fabrique, et il "
        "lit le MEME dict.")


def test_le_passif_MESURE_prime_lui_aussi_sur_le_kit():
    """Meme contrat sur la seconde liste : un `genesBiophagus` dont l'entite n'a PLUS
    `TwistedScience` (passif retire par un montage) RECUPERE `18` -- c'est ce que ferait le natif,
    dont le `RemoveActiveAbility` est porte par le `CreateBehaviour` du passif."""
    heal = int(ActiveAbilityType.Heal)
    assert heal not in [i for (i, _n) in _abilities_of("genesBiophagus", None, None)]
    assert heal in [i for (i, _n) in _abilities_of("genesBiophagus", (), None)], (
        "une mesure de passifs VIDE laisse quand meme le retrait applique : le kit prime sur la "
        "mesure, meme vice que ci-dessus.")


# ================================================================================================
# 4bis. LE FIX EST BRANCHE -- `build_from_state` publie l'ability, pas seulement `_abilities_of`
# ================================================================================================

def _state_avec_traits_mesures(vid: str, traits):
    """`State` OFFLINE minimal. `traits` = la liste SEEDEE dans `UnitContext.traits` (ce que
    `runner.snapshot._load_unit_traits` pose depuis `combatSnapshot.units[].traits`) ;
    `traits is None` = l'entite n'a PAS de `StatsComponent` du tout, donc pas de `UnitContext`.

    ⚠ CETTE DERNIERE FORME EST LE SEUL << canal muet >> qu'`entity_trait_names` connaisse, et c'est
    une DIFFERENCE DE CONTRAT avec l'axe passif : `UnitContext.passive_abilities` vaut `None` par
    defaut (tri-etat porte par le CHAMP), tandis que `UnitContext.traits` a `default_factory=list`
    -- une liste VIDE y est donc deja une mesure (<< cette entite ne porte aucun trait >>), et le
    repli kit n'a lieu que si le `UnitContext` lui-meme est absent. Confondre les deux ferait ecrire
    un test qui rougit pour une raison inventee (faute commise a l'ecriture de ce fichier)."""
    from engine.entities.pathfinding.board import Board
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import (OwnerComponent, PositionComponent, StatsComponent,
                                          UnitComponent)
    from engine.runner.state import State
    tiles = [{"id": c * 3 + r + 1, "col": c, "row": r, "walkable": True, "elevation": 0}
             for c in range(3) for r in range(3)]
    st = State()
    st.board = Board(tiles, adjacency="evenq")
    e = st.add_entity(101)
    e.add_component(UnitComponent(visual_id=vid, alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    e.add_component(PositionComponent(col=1, row=1))
    if traits is not None:
        e.add_component(StatsComponent(UnitContext(entity_id=101, visual_id=vid,
                                                   traits=list(traits))))
    return st


@pytest.mark.parametrize("vid,traits,attendu", [
    ("ultraTigurius", ["Hero", "Psyker", TRAIT], True),    # greffe  : mesure -> derivee
    ("ultraTigurius", ["Hero", "Psyker"], False),          # mesure SANS le trait -> rien
    ("adeptHospitaller", ["Hero"], False),                 # retrait : la mesure prime sur le kit
    ("adeptHospitaller", None, True),                      # pas de ctx -> repli KIT -> derivee
])
def test_build_from_state_publie_l_ability_derivee(vid, traits, attendu):
    """Etage BRANCHEMENT. Sans lui, tous les etages precedents garderaient un foyer
    (`_abilities_of`) que le contexte de DECISION n'appellerait pas avec le bon substrat -- c'est
    exactement le mode d'echec que `test_931r2` a du couvrir sur l'axe passif.

    ⚠ Le regime greffe `["Hero","Psyker","Healer"]` sur `ultraTigurius` est celui CONFRONTE LIVE
    (`--unit-stat 'ultraTigurius:Traits=[...]'`, runner board MC1_67) : le natif publie alors
    `[granted] Heal (id18)` pour lui, et RIEN sans le trait (build temoin, meme board, meme seed)."""
    import engine.ai.state_bridge as SB
    st = _state_avec_traits_mesures(vid, traits)
    ctx = SB.build_from_state(st, 101)
    ids = [a["id"] for a in (ctx.me or {}).get("abilities", [])]
    assert (int(ActiveAbilityType.Heal) in ids) is attendu, (vid, traits, ids)


# ================================================================================================
# 5. LA BORNE EST LEVEE (#1015-r4) -- L'AUTRE MOITIE DE LA SUBSTITUTION
# ================================================================================================
#
# Ce qui vivait ici etait un test-BORNE (`test_spaceWolfPriest_reste_SANS_soin_offline_...`) : il
# FIGEAIT le statu quo et disait « si je rougis, ENTERINER ». #1015-r4 l'a fait rougir, et les
# assertions ci-dessous sont l'enterinement -- memes faits, sens INVERSE.
#
# La cause etait un demi-mirror : le port portait le `RemoveActiveAbility` des trois passifs
# substitutifs (section 2 ci-dessus) et DERIVAIT le `AddActiveAbility` d'une convention de nommage
# (`Heal_<Passif>`). Or les deux appels sont COMPOSES dans le meme behaviour et
# `DSLBehaviors$$AddActiveAbility` a EXACTEMENT les memes trois appelants de code que son jumeau.

def test_le_registre_des_AJOUTS_par_passif_est_le_jumeau_EXACT_des_retraits():
    """Les valeurs sont les LITTERAUX du 3e argument de `DSLBehaviors$$AddActiveAbility` dans les
    trois `CreateBehaviour` (`0x48f`, `0x4bc`, `0x45f`), pas une deduction depuis un nom.

    Le test garde AUSSI la BIJECTION des CLES avec `PASSIVE_REMOVES_ACTIVE_ABILITY` : les deux
    appels natifs sont composes dans un meme behaviour (`op_Addition`/`op_BitwiseAnd`), donc un
    passif qui RETIRE sans AJOUTER -- ou l'inverse -- serait un demi-mirror, exactement la faute
    que #1015-r4 repare."""
    assert PASSIVE_ADDS_ACTIVE_ABILITY == {
        "TwistedScience": int(ActiveAbilityType.Heal_TwistedScience),    # 0x48f
        "HealingBalms": int(ActiveAbilityType.HealingBalms_Heal),        # 0x4bc
        "GalvanicField": int(ActiveAbilityType.Repair_GalvanicField),    # 0x45f
    }
    assert set(PASSIVE_ADDS_ACTIVE_ABILITY) == set(PASSIVE_REMOVES_ACTIVE_ABILITY), (
        "un passif substitutif qui retire sans ajouter (ou l'inverse) est un demi-mirror : les "
        "deux appels natifs vivent dans le MEME behaviour compose")


def test_la_CONVENTION_de_nommage_ne_couvrait_qu_UN_des_trois_et_c_est_MESURE():
    """LE CONTRE-TEMOIN de la reparation, derive du gameconfig -- pas une affirmation de prose.

    L'ancien foyer resolvait `Heal_<Passif>`. Sur les passifs REELLEMENT portes par une unite, cette
    forme ne nomme qu'UN membre d'enum ; les deux autres abilities substituees portent des formes
    que la convention ne peut pas voir. Si un futur build renommait les membres, ce test dirait
    LEQUEL des trois axes a bouge."""
    passifs = {p for vid in _tous_les_unit_ids()
               for p in ((GC.unit(vid) or {}).get("passiveAbilities") or [])}
    assert passifs, "gameconfig muet : ce test ne mesure plus ce qu'il croit"
    vus_par_la_convention = {p for p in PASSIVE_ADDS_ACTIVE_ABILITY
                             if f"Heal_{p}" in ActiveAbilityType.__members__}
    assert vus_par_la_convention == {"TwistedScience"}, vus_par_la_convention
    # ... et les deux autres existent bel et bien, sous une AUTRE forme.
    assert "HealingBalms_Heal" in ActiveAbilityType.__members__
    assert "Repair_GalvanicField" in ActiveAbilityType.__members__
    # Aucun passif HORS registre ne doit tomber dans la convention : sinon le registre LU serait
    # un SOUS-ensemble de l'heuristique qu'il remplace, et la reparation PERDRAIT une ability.
    convention_hors_registre = {p for p in passifs
                                if f"Heal_{p}" in ActiveAbilityType.__members__
                                and p not in PASSIVE_ADDS_ACTIVE_ABILITY}
    assert convention_hors_registre == set(), convention_hors_registre


@pytest.mark.parametrize("passif,aid", sorted(PASSIVE_ADDS_ACTIVE_ABILITY.items()))
def test_chaque_porteur_d_un_passif_substitutif_recoit_l_ability_SPECIALISEE(passif, aid):
    """LE CABLAGE EFFECTIF, sur TOUS les porteurs du passif (derives du gameconfig, jamais listes).

    Et le pendant du contre-temoin de la section 2 : le porteur recoit la SPECIALISEE **et** a
    perdu la GENERIQUE. Un port qui reintroduirait l'ajout sans le retrait (ou qui ferait l'union
    avec le kit) porterait les deux -- ce que `test_952_hunters_beyond_death_offline` contredit
    live sur `admecManipulus`."""
    generique = PASSIVE_REMOVES_ACTIVE_ABILITY[passif]
    porteurs = [vid for vid in _tous_les_unit_ids()
                if passif in ((GC.unit(vid) or {}).get("passiveAbilities") or [])]
    assert porteurs, f"aucun porteur de `{passif}` au gameconfig : ce test est vacant"
    for vid in porteurs:
        ids = [i for (i, _n) in _abilities_of(vid)]
        assert int(aid) in ids, (vid, passif, ids)
        assert int(generique) not in ids, (vid, passif, ids)


def test_le_NOM_de_l_ability_accordee_reste_celui_que_le_DECIDEUR_filtre():
    """Section 5 de l'en-tete, appliquee aux accordees : `_heal_candidates` selectionne par
    `"Heal" in ab["name"]` et `_repair_galvanic_candidates` par l'ID `1119`. Un repli `str(aid)`
    sur le nom rendrait `1212` invisible du generateur de soin -- le trou repare, redepose un
    etage plus bas."""
    noms = dict((i, n) for vid in ("spaceWolfPriest", "genesBiophagus", "admecManipulus")
                for (i, n) in _abilities_of(vid))
    assert "Heal" in noms[int(ActiveAbilityType.HealingBalms_Heal)]
    assert "Heal" in noms[int(ActiveAbilityType.Heal_TwistedScience)]
    assert noms[int(ActiveAbilityType.Repair_GalvanicField)] == "Repair_GalvanicField"
