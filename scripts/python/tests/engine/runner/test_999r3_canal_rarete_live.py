"""#999-r3 -- le canal `rarity` CONFRONTE LIVE, et **uniquement en regime SEPARANT**.

POURQUOI CE FICHIER NE SE CONTENTE PAS DU REGIME PAR DEFAUT. `rl_duel build` impose
`targetRarity = 5` : sans montage, les dix unites d'une bataille rendent `Rarity.Mythic` et TOUT
gate de rarete y est uniformement vrai. Un port SANS gate y serait d'accord avec le natif partout.
Chaque assertion ci-dessous est donc tiree du bras SEPARANT (`orksKillaKan -> Rarity.Epic`), et le
bras DEGENERE n'est joue que comme TEMOIN -- pour etablir que le premier separe vraiment. Le couple
vaut mesure ; le second bras seul ne vaudrait rien.

Ce que les etages ajoutent a la garde offline (`tests/engine/test_999r3_canal_rarete_offline.py`) :

  1. le CAPTEUR emet, et il nomme son enum (`rarityEnum`) ;
  2. le TEMOIN degenere est bien degenere -- c'est ce qui donne son sens a l'etage 3 ;
  3. le bras SEPARANT separe, et il separe LA OU ON L'A DEMANDE (le `VisualId` vise, et lui seul) ;
  4. le PORT traverse : `UnitContext.rarity` == ce que le capteur publie, entite par entite ;
  5. les DEUX NOEUDS changent un ENSEMBLE OBSERVABLE dans ce regime (`UnitsWithRarity(Mythic)`
     PERD les unites retrogradees, `UnitsWithRarity(Epic)` les GAGNE, `HasRarity` bascule) ;
  6. une MACHINE OF WAR est mesuree comme les autres -- c'est la RAISON D'ETRE du capteur #1039
     (`readUnitConfig` filtre sur la classe `UnitComponent` et est AVEUGLE aux Machines,
     `case-1039` Sec.4), donc l'omettre laisserait non couvert exactement ce qui a motive le choix.

Montage : `scripts/python/probe_999r3_regime_separant_rarete.py`, via la fixture
`rarity_separating_case`. Un bras qui ne s'installe pas ECHOUE, il ne skippe pas (#268)."""
from __future__ import annotations

from engine.entities.rarity import RARITY_ENUM_FULL_NAME, Rarity

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_999r3_regime_separant_rarete.py",
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/rl_duel.py",
        "frida/hooks/game/rarity.ts",
        "frida/hooks/features/ai-step/rpc-snapshot.ts",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE du capteur #1039 et de sa consommation : le hook (TS), le "
              "montage (`--unit-stat Rarity=`), et les trois foyers du port. Un changement de "
              "build change les offsets que le capteur resout.",
}

VIS_SEPARE = "orksKillaKan"
RARETE_SEPARANTE = int(Rarity.Epic)      # 3 -- differe du `Mythic` que le harnais impose


def test_le_capteur_emet_et_nomme_son_enum(rarity_separating_case):
    """Etage 1. `rarityEnum` est le nom PLEIN, seul discriminant : cinq enums du build portent les
    six memes membres aux memes ordinaux. `rarityLayout` distingue un `null` de PANNE d'un `null`
    de mesure -- s'il porte des erreurs, la suite ne mesurerait rien."""
    r = rarity_separating_case()
    assert r["rarityEnum"] == RARITY_ENUM_FULL_NAME, (
        "le capteur publie %r : soit le resolveur a pris un enum homonyme, soit le champ a "
        "change de type." % (r["rarityEnum"],))
    assert r["nLignes"] > 0 and r["nMesurees"] == r["nLignes"], (
        "%d/%d lignes seulement portent une rarete -- canal partiellement muet"
        % (r["nMesurees"], r["nLignes"]))
    layout = r.get("rarityLayout") or {}
    assert not (layout.get("errors") or []), "rarityLayout.errors = %s" % (layout.get("errors"),)
    # Les six membres publies par le capteur DOIVENT etre ceux du mirror (le pendant live de
    # `probe_313`, sur la valeur que le port lit vraiment).
    assert r["rarityTypes"] == {m.name: int(m) for m in Rarity}


def test_le_TEMOIN_degenere_est_bien_degenere(rarity_separating_case):
    """Etage 2. C'est CE bras qui donne son sens au suivant : il etablit que le regime par defaut
    du harnais ne discrimine RIEN, donc qu'un vert obtenu sans montage serait vide."""
    t = rarity_separating_case(rarity=None)
    assert t["distinct"] == [int(Rarity.Mythic)], (
        "le bras SANS montage rend %s : la premisse `targetRarity = 5` ne tient plus, et le "
        "couple de bras ne prouve plus rien." % (t["distinct"],))
    assert t["separating"] is False


def test_le_bras_separant_separe_LA_OU_ON_L_A_DEMANDE(rarity_separating_case):
    """Etage 3. Pas seulement << deux valeurs distinctes >> : la valeur basse doit etre portee par
    le `VisualId` VISE et par lui SEUL -- sinon on aurait pu mesurer n'importe quel bruit."""
    r = rarity_separating_case()
    assert r["separating"] is True and r["distinct"] == [RARETE_SEPARANTE, int(Rarity.Mythic)]
    assert r["by_visual"].get(VIS_SEPARE) == [RARETE_SEPARANTE], (
        "%s rend %s au lieu de [%d]" % (VIS_SEPARE, r["by_visual"].get(VIS_SEPARE),
                                        RARETE_SEPARANTE))
    autres = {v: vs for v, vs in r["by_visual"].items()
              if v is not None and v != VIS_SEPARE}
    assert autres, "roster reduit au seul VisualId vise : le montage ne separerait rien"
    assert all(vs == [int(Rarity.Mythic)] for vs in autres.values()), (
        "le patch a deborde sur d'autres unites : %s" % (autres,))
    # La SOURCE de la fabrique (`UnitConfiguration.Rarity`, +0x80) doit porter la meme chose que le
    # COMPOSANT (+0x74) la ou elle est lisible -- c'est le temoin que `InitBaseComponent` recopie
    # bien, et qu'on ne mesure pas un champ fige ailleurs.
    ecarts = {eid: (r["by_entity"][eid], c) for eid, c in (r["config_by_entity"] or {}).items()
              if c is not None and r["by_entity"].get(eid) != c}
    assert not ecarts, "composant != configuration sur %s" % (ecarts,)


def test_le_PORT_traverse_entite_par_entite(rarity_separating_case):
    """Etage 4. Le capteur peut emettre pendant que le port jette : c'est la comparaison
    entite-par-entite, pas l'egalite des ensembles, qui l'exclut."""
    r = rarity_separating_case()
    manquantes = {eid: v for eid, v in r["by_entity"].items()
                  if r["ctx_by_entity"].get(eid) != v}
    assert not manquantes, (
        "%d entite(s) ou `UnitContext.rarity` != `combatSnapshot.units[].rarity` : %s"
        % (len(manquantes), dict(list(manquantes.items())[:5])))
    assert r["ctxDistinct"] == r["distinct"]


def test_les_deux_noeuds_CHANGENT_un_ensemble_observable(rarity_separating_case):
    """Etage 5 -- LE test qui distingue << porte >> de << actif >>. Dans le bras SEPARANT, la
    sortie des deux noeuds DOIT differer de celle du bras degenere, et differer exactement des
    entites retrogradees."""
    r = rarity_separating_case()
    t = rarity_separating_case(rarity=None)

    retrogradees = {eid for eid, v in r["by_entity"].items() if v == RARETE_SEPARANTE}
    assert retrogradees, "aucune entite retrogradee : rien a mesurer"

    mythic = set(r["unitsWithRarityMythic"])
    epic = set(r["unitsWithRarityEpic"])
    assert epic == retrogradees, (
        "UnitsWithRarity(Epic) = %s, attendu %s" % (sorted(epic), sorted(retrogradees)))
    assert mythic.isdisjoint(retrogradees), (
        "UnitsWithRarity(Mythic) garde des entites retrogradees : %s"
        % sorted(mythic & retrogradees))
    assert mythic, "UnitsWithRarity(Mythic) VIDE : le noeud filtrerait tout, pas seulement la rarete"

    # Le TEMOIN : dans le bras degenere, le meme noeud rend TOUT le monde et l'autre RIEN. C'est ce
    # contraste qui interdit de conclure d'un accord obtenu en regime non discriminant.
    assert not t["unitsWithRarityEpic"], (
        "le bras DEGENERE rend deja des Epic (%s) : il ne peut plus servir de temoin"
        % (t["unitsWithRarityEpic"],))
    assert set(t["unitsWithRarityMythic"]) == set(t["by_entity"]), (
        "le bras DEGENERE devrait rendre TOUTES les entites en Mythic")

    # `HasRarity`, sur le meme etat : le predicat par-entite doit etre l'exact complement.
    hr = {int(k): v for k, v in r["hasRarityMythicByEntity"].items()}
    assert {eid for eid, ok in hr.items() if ok} == mythic
    assert all(hr[eid] is False for eid in retrogradees)


def test_une_MACHINE_OF_WAR_est_mesuree_comme_les_autres(rarity_separating_case):
    """Etage 6 -- la RAISON D'ETRE du capteur #1039. La voie prescrite au depart
    (`readUnitConfig`) filtre sur la classe `IdunBattle.Entities.Components.UnitComponent` et rend
    `{"error": "visualId introuvable"}` pour toute Machine ; #1039 passe donc par
    `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent`, qui sert les deux familles. Un
    montage SANS MoW laisserait non couvert exactement ce qui a motive ce choix.

    Le bras porte une MoW EXPLICITE (`--p-mow`) : le roster par defaut de (MC1_67, 777) n'en a
    aucune, donc s'en remettre a lui aurait rendu ce test structurellement vide."""
    r = rarity_separating_case(p_mow="adeptExorcist")
    mows = r.get("machineIds") or []
    assert mows, ("aucune MoW dans le roster du bras : `--p-mow` n'a pas pris, et l'etage ne "
                  "mesure rien.")
    for eid in mows:
        assert r["by_entity"].get(eid) is not None, (
            "MoW u%s SANS rarete mesuree -- le capteur est retombe sur une voie aveugle aux "
            "Machines." % eid)
        assert r["ctx_by_entity"].get(eid) == r["by_entity"].get(eid), (
            "MoW u%s : le port n'a pas garde la rarete du capteur" % eid)
    # Et elle passe bien les DEUX noeuds (une MoW `Mythic` est dans `UnitsWithRarity(Mythic)`).
    mythic = set(r["unitsWithRarityMythic"])
    for eid in mows:
        if r["by_entity"][eid] == int(Rarity.Mythic):
            assert eid in mythic, "MoW u%s Mythic absente de UnitsWithRarity(Mythic)" % eid
