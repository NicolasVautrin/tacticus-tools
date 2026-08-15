"""FIDELITE du synthetiseur de catalogue -- et PEREMPTION de la capture, qui n'est pas la meme chose.

POURQUOI CE FICHIER EXISTE A PART (#457). Ces tests sont 100 % OFFLINE : aucun runner, aucun RPC,
aucune session Frida. Ils vivaient dans `test_catalog_inject_live.py`, fichier MIXTE -- donc hors du
perimetre de `probe_457` (`not name.endswith("_live.py")`), le seul cliquet qui voie un test offline
ROUGE EN PERMANENCE. C'est ainsi que le rouge decrit ci-dessous a tenu du 2026-07-29 au 2026-08-02
sans que rien ne le dise : la suite complete est proscrite, aucun agent n'avait ce fichier pour
tranche, et les entrees `pytest_*` de la banque sont des ALLOWLISTS. Sorti dans un fichier
non-`_live`, ce lot entre au cliquet TOUT SEUL. Les tests LIVE (spawn / cast des porteurs injectes)
restent dans `test_catalog_inject_live.py`.

CE QUI EST CONFRONTE, ET CONTRE QUOI. `catalog_inject.synthesize` mirror
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` ; `synthesize_ability` mirror
le peuplement de `BattleConfiguration.Abilities`. L'oracle est `data/seed-bc.json` : un catalogue que
le JEU a construit. Re-synthetiser une entree dont le jeu a bati l'originale et retrouver l'originale
est la preuve qu'une entree INJECTEE n'est pas une approximation.

LA PREMISSE QUI A CEDE, ET QUI N'EST PAS UNE PREMISSE DE CODE. Cette confrontation ne vaut que si
les DEUX cotes viennent du MEME build : la capture est figee (`data/seed-bc.json`, UN seul commit,
`f467e649`), le gameconfig que lit la synthese est le fichier VIVANT, donc celui du build COURANT.
La MAJ `gqfc5mff6c` -> `rnca9r7q6c` a change le kit de `necroOverlord`, et le test a rendu ce
changement de DONNEE comme un defaut de CODE -- une mesure juste, attribuee au mauvais accuse.
Ce que ces tests separent desormais :

  * la FIDELITE de la synthese, STRICTE, sur tout ce que la migration n'a pas touche (174/175
    entrees `Units`, 273/277 configs d'ability) ;
  * la PEREMPTION de la capture, EPINGLEE (`catalog_inject.STALE_UNIT_ENTRIES`) et gardee dans les
    DEUX sens -- une derive de plus rougit, la resorption de celle-ci aussi.

ET LA MOITIE QUI NE POUVAIT PAS ROUGIR. L'ancien test confrontait les configs d'ability au seed
RECHARGE par `rl_collect_batch._load_seed_bc`, qui vient d'appeler `refresh_ability_configs` : il
comparait donc `synthesize_ability(x)` a une valeur que le rattrapage venait d'ecrire depuis
`synthesize_ability(x)`. Tautologie -- assertion structurellement incapable d'echouer. Mesure du
2026-08-02 : capture RAW = 4 derives (`ResurrectionOrb` x2, `FearOfTheUnseen`, `ShockAssault`),
capture RECHARGEE = 0. Ici, les deux catalogues sont confrontes a la capture BRUTE, et le
rattrapage est garde par l'EGALITE de deux ensembles calcules independamment.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import copy
import json

import build_pin
import catalog_inject as CI
import gameconfig as G
import symbols_layout


def build_de_la_capture() -> str:
    """Le build sur lequel `data/seed-bc.json` a ete capture, CONTROLE.

    Sert a ATTRIBUER la derive, pas a la constater : c'est la table d'enums de CE build qui
    etablit qu'elle vient de la MAJ. Le litteral passe par `build_pin.archived_build`, le seul
    foyer ou un hash ecrit a la main est legitime (#431) : il LEVE si l'archive a disparu, au lieu
    de laisser la comparaison rendre un vide qui se lirait comme un resultat.
    """
    return build_pin.archived_build(
        "gqfc5mff6c",
        "le build de la capture data/seed-bc.json -- sa table d'enums ATTRIBUE la derive de "
        "necroOverlord a la MAJ vers rnca9r7q6c (#254-bc)")


def _raw_seed() -> dict:
    """La capture BRUTE, sans aucun rattrapage -- l'oracle de la fidelite.

    Surtout PAS `rl_collect_batch._load_seed_bc` : il rafraichit `BC.Abilities` et `BC.Utilities`
    avant de rendre, donc confronter la synthese a son resultat est une tautologie (cf. l'en-tete).
    """
    return json.loads(CI.SEED_BC.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ catalogue UNITS

def test_la_synthese_reproduit_le_catalogue_capture_hors_derive_epinglee():
    """La synthese redonne EXACTEMENT l'entree que le jeu a batie, pour toute unite que la MAJ n'a
    pas touchee. STRICTE : le seul ecart tolere est celui, nomme, de `STALE_UNIT_ENTRIES`."""
    seed = _raw_seed()
    n, diffs = CI.validate(seed)
    assert n > 100, "catalogue anormalement petit (%d)" % n
    hors_epingle = {}
    for field, rows in diffs.items():
        for uid, synth, real in rows:
            if field not in CI.STALE_UNIT_ENTRIES.get(uid, ()):
                hors_epingle.setdefault(field, []).append((uid, synth, real))
    assert not hors_epingle, (
        "la synthese diverge de la capture HORS derive epinglee -- lire l'entree au decompile "
        "avant d'epingler quoi que ce soit: %r" % {k: v[:2] for k, v in hors_epingle.items()})
    touchees = len(CI.stale_unit_entries(seed))
    print("\n[catalog/units] %d entrees re-synthetisees, %d fidele(s) au bit pres, "
          "%d perimee(s) (epinglees)" % (n, n - touchees, touchees))


def test_le_bloc_units_perime_est_exactement_celui_qui_est_epingle():
    """L'epingle est gardee dans les DEUX sens.

    Une derive de PLUS = la capture ou la synthese a bouge, et il faut LIRE avant d'epingler.
    Une derive en MOINS = `data/seed-bc.json` a ete re-dumpe (#254-bc) : retirer l'entree de
    `STALE_UNIT_ENTRIES`, et relire `case-392` §3 -- le re-dump inverse aussi le cas
    `MartialApotheosis` et rend `MyWillBeDoneOverlord` dispatchable (#392-r1).
    """
    stale = CI.stale_unit_entries(_raw_seed())
    obtenu = {uid: sorted(champs) for uid, champs in stale.items()}
    attendu = {uid: sorted(champs) for uid, champs in CI.STALE_UNIT_ENTRIES.items()}
    assert obtenu == attendu, (
        "le bloc Units perime n'est plus celui qui est epingle.\n"
        "  epingle = %r\n  mesure  = %r\n"
        "  Un re-dump (#254-bc) VIDE cette liste ; une entree NEUVE doit etre lue avant d'y entrer."
        % (attendu, obtenu))
    print("\n[catalog/units] derive epinglee: %r" % obtenu)


def test_la_derive_du_bloc_units_est_attribuee_a_la_migration_de_build():
    """ATTRIBUER, pas constater : pourquoi c'est la CAPTURE qui est en arriere, pas la synthese.

    `MyWillBeDoneOverlord` est ABSENTE de l'enum du build de la capture et PRESENTE dans celui du
    build courant -- le gameconfig de `gqfc5mff6c` ne POUVAIT donc pas l'attribuer, et la synthese
    n'invente pas. `Resilient` existe dans les DEUX enums : le trait gagne est un pur changement de
    gameconfig, meme migration.
    """
    courant = CI.enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType")
    traits_courant = CI.enum_map("IdunBattle.Entities.Enum.UnitTrait")
    assert courant.get("MyWillBeDoneOverlord") == 1556
    assert courant.get("MartialApotheosis") == 1045
    assert traits_courant.get("Resilient") == 1009
    # Le gameconfig VIVANT tranche le sens de la derive : plus AUCUN porteur de MartialApotheosis.
    gc = G.unit("necroOverlord") or {}
    assert gc.get("passiveAbilities") == ["MyWillBeDoneOverlord"], gc.get("passiveAbilities")
    assert "Resilient" in (gc.get("traits") or []), gc.get("traits")
    # PAS de repli silencieux : sans la table du build de la capture l'attribution n'est plus
    # RE-DERIVABLE. `archived_build` LEVE si l'archive a disparu (les archives sont conservees
    # EXPRES -- leur diff EST le rapport de changement du jeu) ; et viser le build COURANT ne
    # comparerait rien, ce qui serait un vert vacueux (contre-epreuve M4).
    capture = build_de_la_capture()
    assert capture != symbols_layout.current_build(), (
        "le build de reference (%s) EST le build courant -- il n'y a plus de comparaison "
        "inter-build, donc plus d'attribution. Si le seed BC a ete re-dumpe (#254-bc), ce test et "
        "STALE_UNIT_ENTRIES n'ont plus d'objet." % capture)
    ancien = CI.enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType", capture)
    traits_ancien = CI.enum_map("IdunBattle.Entities.Enum.UnitTrait", capture)
    assert "MyWillBeDoneOverlord" not in ancien, (
        "l'ability existait deja sur %s : l'attribution de la derive a la MAJ tombe, "
        "relire avant de conclure" % capture)
    assert ancien.get("MartialApotheosis") == 1045
    assert traits_ancien.get("Resilient") == 1009, (
        "Resilient absent de l'enum de %s : la derive de trait serait un changement d'ENUM, "
        "pas de gameconfig" % capture)
    print("\n[catalog/attribution] TriggeredAbilityType: %s=%d membres (sans MyWillBeDoneOverlord) "
          "-> %s=%d membres (MyWillBeDoneOverlord=1556) ; Resilient=1009 dans les DEUX"
          % (capture, len(ancien), symbols_layout.current_build(), len(courant)))


def test_le_chargement_rafraichit_abilities_et_utilities_mais_PAS_units():
    """L'ASYMETRIE des trois catalogues, sous garde -- c'est elle qui fait qu'un runner deploie un
    kit perime SANS que personne le sache.

    `refresh_ability_configs` (#254) et `refresh_ai_utilities` (#27-4) rattrapent leurs catalogues
    au chargement ; `BC.Units` n'est PAS rattrape (#254-bc, arbitrage ouvert : un re-dump change le
    pool spawnable ET les stats de reference de tous les tests live). Ce test rougira le jour ou un
    rattrapage `Units` sera pose -- c'est le moment de revoir l'epingle.
    """
    import rl_collect_batch as R
    avant = CI.stale_unit_entries(_raw_seed())
    apres = CI.stale_unit_entries(R._load_seed_bc())
    assert apres == avant, (
        "le chargement a MODIFIE le bloc Units (avant=%r apres=%r) -- si c'est un rattrapage "
        "delibere, #254-bc est ferme : revoir STALE_UNIT_ENTRIES et case-392 §3"
        % (sorted(avant), sorted(apres)))
    # Et le rapport que le chargeur imprime desormais NOMME ce qu'il ne rattrape pas.
    rapport = CI.stale_unit_report(_raw_seed())
    assert rapport and "necroOverlord" in rapport and "INATTENDUE" not in rapport, rapport
    print("\n[catalog/asymetrie] %s" % rapport)


# ------------------------------------------------------------------ catalogue ABILITIES

def test_le_rattrapage_repare_exactement_les_configs_dability_qui_derivent():
    """Le rattrapage #254 repare EXACTEMENT ce qui derive -- ni moins (une config laissee perimee
    fait LEVER `AbilityConfiguration$$GetStringConstant` au cast ou au deploiement), ni plus.

    C'est l'EGALITE de deux ensembles calcules independamment qui garde ici : la derive mesuree sur
    la capture BRUTE d'un cote, la liste que `refresh_ability_configs` declare avoir rafraichie de
    l'autre. Comparer la synthese au seed DEJA rafraichi ne garderait rien (tautologie).
    """
    raw = _raw_seed()
    nc, ni, adiffs = CI.validate_abilities(raw)
    assert nc > 100, "peu de configs confrontees (%d)" % nc
    derivees = {name for rows in adiffs.values() for name, _s, _r in rows}
    bc = copy.deepcopy(raw)
    refreshed, added = CI.refresh_ability_configs(bc)
    assert set(refreshed) == derivees, (
        "le rattrapage ne repare pas exactement ce qui derive: derive=%r rafraichies=%r"
        % (sorted(derivees), sorted(refreshed)))
    _nc2, _ni2, apres = CI.validate_abilities(bc)
    assert not apres, "des configs derivent ENCORE apres rattrapage: %r" % (
        {k: v[:2] for k, v in apres.items()})
    print("\n[catalog/abilities] %d configs confrontees (%d internes moteur ignorees) ; "
          "%d derivee(s) reparee(s) %r ; %d ajoutee(s) %r"
          % (nc, ni, len(derivees), sorted(derivees), len(added), added))


# ============================================== catalogue UNITS -- l'axe AJOUT (#254-bc-r1)
#
# `STALE_UNIT_ENTRIES` garde la derive des entrees PRESENTES. Ce que la capture n'a PAS DU TOUT
# relevait de `missing_from_seed_bc`, qui enumere sans comparer : l'ecart est passe de 17 a 21
# unites `lineup` sans qu'aucun garde le dise, et la docstring du module annoncait encore 17.

def test_l_ecart_d_ajout_lineup_est_exactement_celui_qui_est_epingle():
    """Garde dans les DEUX sens, comme l'epingle voisine.

    Une unite de PLUS = le gameconfig a ajoute un heros depuis la capture ; il n'est atteignable
    que par injection (`write_augmented_seed_bc`, case-92 Sec.6) et il faut l'INSCRIRE ici apres
    l'avoir lu. Une unite en MOINS = elle est entree au catalogue (re-dump #254-bc, ou seed BC
    remplace) : la retirer de l'epingle.
    """
    gap = CI.catalog_gap(_raw_seed())
    assert gap["lineup"]["total"] > 100, gap["lineup"]["total"]
    obtenu = set(gap["lineup"]["missing"])
    assert obtenu == set(CI.MISSING_LINEUP_ENTRIES), {
        "neuves hors epingle": sorted(obtenu - set(CI.MISSING_LINEUP_ENTRIES)),
        "epinglees mais presentes": sorted(set(CI.MISSING_LINEUP_ENTRIES) - obtenu)}
    print("\n[catalog/gap] lineup: %d au gameconfig, %d hors catalogue (epingle)"
          % (gap["lineup"]["total"], len(obtenu)))


def test_tous_les_summons_du_gameconfig_sont_au_catalogue():
    """INVARIANT, pas seuil -- et il porte une consequence de HARNAIS : un summon present au
    catalogue s'amene en spawnant son summoner, SANS injection (gate de confrontabilite du
    CLAUDE.md). Le jour ou le jeu en ajoute un, cette propriete tombe pour lui, et le montage qui
    l'ignorerait conclurait « pas de porteur » a tort."""
    gap = CI.catalog_gap(_raw_seed())
    assert gap["summons"]["total"] > 50, "temoin summon trop maigre -- rien n'est mesure"
    assert gap["summons"]["missing"] == [], (
        "des summons du gameconfig ne sont plus au catalogue : %r -- ils exigent desormais une "
        "injection catalogue, et tout verdict « non confrontable » les concernant est a relire"
        % gap["summons"]["missing"])


def test_les_npc_sont_RAPPORTES_et_non_gardes():
    """La capture ne porte que les npc de CETTE bataille : les 487 autres s'injectent a la demande.
    Les garder rougirait a chaque MAJ pour rien. Ce qui compte, et qui EST garde : les quelques
    npc presents restent la -- `npc_witness_diff` (le seul temoin non degenere du chemin npc) n'a
    d'objet que par eux."""
    gap = CI.catalog_gap(_raw_seed())
    presents = gap["npc"]["total"] - len(gap["npc"]["missing"])
    assert presents >= 4, (
        "il ne reste que %d npc au catalogue : le temoin de `npc_witness_diff` devient degenere"
        % presents)
    assert len(gap["npc"]["missing"]) > 100, "regime inattendu -- relire avant de conclure"


def test_le_rapport_d_ecart_se_TAIT_en_regime_nominal_et_PARLE_dans_les_deux_sens():
    """Un rapport qui parle tout le temps ne se lit plus. Celui-ci rend `None` tant que l'ecart est
    exactement l'epingle -- et les deux mutations le font parler, chacune avec son propre mot."""
    seed = _raw_seed()
    assert CI.catalog_gap_report(seed) is None

    # (a) une unite `lineup` NEUVE au gameconfig, absente de la capture.
    neuve = "zzUniteQuiNexistePas"
    idx = G._index()
    idx["lineup"][neuve] = {"traits": []}
    try:
        rapport = CI.catalog_gap_report(seed)
        assert rapport and "NEUVES hors epingle" in rapport and neuve in rapport, rapport
    finally:
        idx["lineup"].pop(neuve, None)

    # (b) une unite EPINGLEE qui entre au catalogue (ce que ferait un re-dump).
    entree = sorted(CI.MISSING_LINEUP_ENTRIES)[0]
    seed2 = copy.deepcopy(seed)
    seed2["Units"].append({"Id": entree})
    rapport = CI.catalog_gap_report(seed2)
    assert rapport and "epinglees mais PRESENTES" in rapport and entree in rapport, rapport

    # (c) un SUMMON qui disparait du catalogue -- l'axe que `missing_from_seed_bc` ne voyait pas.
    smn = sorted(G._index()["summons"])[0]
    seed3 = copy.deepcopy(seed)
    seed3["Units"] = [u for u in seed3["Units"] if u["Id"].split(":")[0] != smn]
    rapport = CI.catalog_gap_report(seed3)
    assert rapport and "SUMMONS absents" in rapport and smn in rapport, rapport
    assert CI.catalog_gap_report(seed) is None       # aucune fuite d'etat entre les bras
