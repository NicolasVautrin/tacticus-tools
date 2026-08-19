"""FIDELITE du synthetiseur de catalogue -- et ECART DE SUBSTRAT, qui n'est pas la meme chose.

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

L'ORACLE A CHANGE DE NATURE (#10039), ET C'EST UN GAIN. `data/seed-bc.json` n'est plus la CAPTURE
d'une bataille (175 entrees, figee sur `gqfc5mff6c`) : c'est une FORGE -- le meme
`BattleConfigBuilder`, appele hors bataille par `forge_seed_bc.py`, contre le build et le
gameconfig COURANTS. Trois consequences pour ce fichier :

  * l'oracle est ~4x plus large (717 entrees, lineup 127/127, summons 65/65, npc 489/491), donc il
    confronte des branches qu'une capture a 4 npc ne pouvait pas atteindre ;
  * la PEREMPTION inter-build a disparu : les deux cotes viennent du meme build. La derive
    `necroOverlord` (`MartialApotheosis` -> `MyWillBeDoneOverlord` + `Resilient` a la MAJ vers
    `rnca9r7q6c`), qu'on epinglait et attribuait ici, N'EXISTE PLUS ;
  * ce qui reste s'epingle toujours, mais pour une AUTRE cause -- l'etat JOUEUR. La fabrique
    enumere l'`IUnitProgression` du compte : une unite non possedee sort a Rank 0 avec ses
    abilities NON DEBLOQUEES, quand `synthesize` lit le kit COMPLET du gameconfig (ce qu'on veut
    d'une entree a injecter au rank 17). Ecart STRUCTUREL, pas defaut de mirror -- et il est
    ATTRIBUE par un croisement, pas constate (cf. `test_la_derive_du_bloc_units_est_attribuee_a_l_etat_joueur`).

CE QUE LES TESTS SEPARENT, DONC :

  * la FIDELITE de la synthese, STRICTE, sur tout ce que l'etat joueur ne touche pas ;
  * l'ECART epingle (`catalog_inject.STALE_UNIT_ENTRIES`), garde dans les DEUX sens -- un ecart de
    plus rougit, la resorption d'un ecart epingle aussi.

ET LA MOITIE QUI NE POUVAIT PAS ROUGIR. L'ancien test confrontait les configs d'ability au seed
RECHARGE par `rl_collect_batch._load_seed_bc`, qui vient d'appeler `refresh_ability_configs` : il
comparait donc `synthesize_ability(x)` a une valeur que le rattrapage venait d'ecrire depuis
`synthesize_ability(x)`. Tautologie -- assertion structurellement incapable d'echouer. Ici, les deux
catalogues sont confrontes au fichier BRUT, et le rattrapage est garde par l'EGALITE de deux
ensembles calcules independamment.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import copy
import json

import catalog_inject as CI
import gameconfig as G


def _raw_seed() -> dict:
    """Le catalogue BRUT, sans aucun rattrapage -- l'oracle de la fidelite.

    Surtout PAS `rl_collect_batch._load_seed_bc` : il rafraichit `BC.Abilities` et `BC.Utilities`
    avant de rendre, donc confronter la synthese a son resultat est une tautologie (cf. l'en-tete).
    """
    return json.loads(CI.SEED_BC.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ catalogue UNITS

def test_la_synthese_reproduit_le_catalogue_capture_hors_derive_epinglee():
    """La synthese redonne EXACTEMENT l'entree que la fabrique native a batie, pour toute unite
    dont l'etat joueur ne l'en empeche pas. STRICTE : le seul ecart tolere est celui, nomme, de
    `STALE_UNIT_ENTRIES`."""
    seed = _raw_seed()
    n, diffs = CI.validate(seed)
    assert n > 100, "catalogue anormalement petit (%d)" % n
    hors_epingle = {}
    for field, rows in diffs.items():
        for uid, synth, real in rows:
            if field not in CI.STALE_UNIT_ENTRIES.get(uid, ()):
                hors_epingle.setdefault(field, []).append((uid, synth, real))
    assert not hors_epingle, (
        "la synthese diverge du catalogue HORS ecart epingle -- lire l'entree au decompile "
        "avant d'epingler quoi que ce soit: %r" % {k: v[:2] for k, v in hors_epingle.items()})
    touchees = len(CI.stale_unit_entries(seed))
    print("\n[catalog/units] %d entrees re-synthetisees, %d fidele(s) au bit pres, "
          "%d ecart(s) epingle(s)" % (n, n - touchees, touchees))


def test_le_bloc_units_perime_est_exactement_celui_qui_est_epingle():
    """L'epingle est gardee dans les DEUX sens.

    Un ecart de PLUS = le catalogue ou la synthese a bouge, et il faut LIRE avant d'epingler.
    Un ecart en MOINS = l'entree est redevenue reproductible (le joueur a debloque l'unite, ou la
    forge a ete refaite) : la retirer de `STALE_UNIT_ENTRIES`, jamais la laisser en exemption
    permanente -- une epingle qui survit a son objet cesse de garder le mirror sans le dire.
    """
    stale = CI.stale_unit_entries(_raw_seed())
    obtenu = {uid: sorted(champs) for uid, champs in stale.items()}
    attendu = {uid: sorted(champs) for uid, champs in CI.STALE_UNIT_ENTRIES.items()}
    assert obtenu == attendu, (
        "le bloc Units divergent n'est plus celui qui est epingle.\n"
        "  epingle = %r\n  mesure  = %r\n"
        "  Une entree NEUVE doit etre LUE avant d'y entrer ; une entree resorbee doit en SORTIR."
        % (attendu, obtenu))
    print("\n[catalog/units] ecart epingle: %d entree(s)" % len(obtenu))


def test_la_derive_du_bloc_units_est_attribuee_a_l_etat_joueur():
    """ATTRIBUER, pas constater -- et l'attribution est un CROISEMENT, pas une histoire.

    ⚠ CE TEST A CHANGE D'ACCUSE (#10039). Il attribuait la derive a la MIGRATION DE BUILD :
    `data/seed-bc.json` etait fige sur `gqfc5mff6c`, le gameconfig etait celui du build courant, et
    `necroOverlord` avait change de kit entre les deux. Cette cause a DISPARU avec la forge -- les
    deux cotes viennent maintenant du meme build, et `necroOverlord` ne diverge plus du tout.
    Garder l'ancienne attribution aurait laisse un test VERT qui explique une derive inexistante.

    La cause d'aujourd'hui est l'ETAT JOUEUR, et elle se DERIVE : `BattleConfigBuilder` enumere
    l'`IUnitProgression` du compte, donc une unite non possedee sort avec `ActiveAbilities` et
    `PassiveAbilities` VIDES ; `synthesize` lit le kit COMPLET du gameconfig. Le croisement (BC
    vide) x (divergente) sur les `lineup` doit avoir ses DEUX cellules de contre-exemple a ZERO --
    sans quoi l'attribution serait un hasard, pas une mesure.

    ⚠ `Rank == 0` NE SUFFIRAIT PAS comme critere : 48 entrees lineup y sont, 20 seulement
    divergent (`thousDaemonPrince` est Rank 0 / StarLevel 0 / Rarity 0 AVEC ses deux actives).
    C'est bien l'etat des ABILITIES qui discrimine, pas le rang.
    """
    seed = _raw_seed()
    tab = CI.player_state_gap(seed)
    concordants = tab.get((True, True), [])
    intactes = tab.get((False, False), [])
    assert tab.get((True, False), []) == [], (
        "des entrees ont un kit VIDE au catalogue sans diverger de la synthese -- l'attribution "
        "tombe : %r" % tab[(True, False)])
    assert tab.get((False, True), []) == [], (
        "des entrees divergent AVEC un kit non vide -- une AUTRE cause existe, la lire : %r"
        % tab[(False, True)])
    assert concordants and intactes, (
        "une des deux cellules pleines est vide : le croisement est degenere et ne prouve rien "
        "(vides=%d, intactes=%d)" % (len(concordants), len(intactes)))

    # ... et ce sont EXACTEMENT les entrees epinglees pour ces deux champs.
    epinglees = {uid for uid, ch in CI.STALE_UNIT_ENTRIES.items()
                 if set(ch) & {"ActiveAbilities", "PassiveAbilities"}}
    assert set(concordants) == epinglees, {
        "mesurees hors epingle": sorted(set(concordants) - epinglees),
        "epinglees mais concordantes": sorted(epinglees - set(concordants))}

    # Le gameconfig, lui, PORTE bien le kit qui manque au catalogue : la synthese n'invente rien.
    for uid in sorted(concordants):
        gc = G.unit(uid.split(":")[0]) or {}
        assert gc.get("activeAbilities") or gc.get("passiveAbilities"), (
            "%s n'a AUCUN kit au gameconfig : ce n'est alors pas de l'etat joueur" % uid)
    print("\n[catalog/attribution] etat joueur : %d entrees lineup a kit VIDE (toutes divergentes)"
          ", %d a kit plein (toutes concordantes), 0 contre-exemple"
          % (len(concordants), len(intactes)))


def test_le_chargement_rafraichit_abilities_et_utilities_mais_PAS_units():
    """L'ASYMETRIE des trois catalogues, sous garde -- c'est elle qui fait qu'un runner deploie un
    kit different SANS que personne le sache.

    `refresh_ability_configs` (#254) et `refresh_ai_utilities` (#27-4) rattrapent leurs catalogues
    au chargement ; `BC.Units` n'est PAS rattrape (#254-bc). Ce test rougira le jour ou un
    rattrapage `Units` sera pose -- c'est le moment de revoir l'epingle.
    """
    import rl_collect_batch as R
    avant = CI.stale_unit_entries(_raw_seed())
    apres = CI.stale_unit_entries(R._load_seed_bc())
    assert apres == avant, (
        "le chargement a MODIFIE le bloc Units (avant=%r apres=%r) -- si c'est un rattrapage "
        "delibere, #254-bc est ferme : revoir STALE_UNIT_ENTRIES et case-392 §3"
        % (sorted(avant), sorted(apres)))
    # Et le rapport que le chargeur imprime NOMME ce qu'il ne rattrape pas, sans hurler : en
    # regime nominal il dit le COMPTE et que tout est epingle ; des qu'une entree sort de
    # l'epingle il la NOMME. Les deux bras sont verifies, sinon « pas de INATTENDUE » serait vrai
    # pour un rapport qui ne sait pas le dire.
    rapport = CI.stale_unit_report(_raw_seed())
    assert rapport and "TOUTES epinglees" in rapport and "INATTENDUE" not in rapport, rapport
    assert str(len(avant)) in rapport, rapport
    sauve = CI.STALE_UNIT_ENTRIES
    try:
        CI.STALE_UNIT_ENTRIES = {}
        bruyant = CI.stale_unit_report(_raw_seed())
    finally:
        CI.STALE_UNIT_ENTRIES = sauve
    assert bruyant and "INATTENDUE" in bruyant, bruyant
    print("\n[catalog/asymetrie] %s" % rapport)


# ------------------------------------------------------------------ catalogue ABILITIES

def test_le_rattrapage_repare_exactement_les_configs_dability_qui_derivent():
    """Le rattrapage #254 repare EXACTEMENT ce qui derive -- ni moins (une config laissee perimee
    fait LEVER `AbilityConfiguration$$GetStringConstant` au cast ou au deploiement), ni plus.

    C'est l'EGALITE de deux ensembles calcules independamment qui garde ici : la derive mesuree
    d'un cote, la liste que `refresh_ability_configs` declare avoir rafraichie de l'autre.
    Comparer la synthese au seed DEJA rafraichi ne garderait rien (tautologie).

    ⚠ ET CETTE EGALITE EST DEVENUE VACUEUSE (#10039) : le catalogue est FORGE contre le gameconfig
    courant, donc `validate_abilities` rend **0** divergence -- l'assertion se reduisait a
    `set() == set()`, vraie meme si `refresh_ability_configs` ne faisait plus RIEN. Contre-epreuve
    mesuree par `probe_254bc --step 4` : le mutant « rattrapage INERTE » est passe VERT. C'est
    exactement le vice que l'en-tete de ce fichier denonce, revenu par une autre porte -- une
    assertion structurellement incapable d'echouer.

    La derive est donc FABRIQUEE ici, au lieu d'etre attendue d'un accident de build. La fraicheur
    du catalogue reste MESUREE (et rougit si elle se perd), elle n'est simplement plus ce qui porte
    la garde.
    """
    raw = _raw_seed()
    nc, ni, adiffs = CI.validate_abilities(raw)
    assert nc > 100, "peu de configs confrontees (%d)" % nc
    assert adiffs == {}, (
        "le catalogue partage porte des configs d'ability qui derivent du gameconfig -- il n'est "
        "plus une forge fraiche. Ce n'est pas une faute en soi (le rattrapage les repare au "
        "chargement), mais il faut LIRE avant de continuer : %r"
        % {k: v[:2] for k, v in adiffs.items()})

    # La derive, FABRIQUEE : trois configs auxquelles on ajoute une constante que le gameconfig
    # n'a pas. `refresh_ability_configs` doit rafraichir ces trois-la, et seulement elles.
    bc = copy.deepcopy(raw)
    pa = bc["Abilities"]["PassiveAbilities"]
    victimes = [n for n in sorted(pa) if G.ability(n) is not None][:3]
    assert len(victimes) == 3, "moins de 3 configs derivables au catalogue : %r" % victimes
    for n in victimes:
        pa[n] = dict(pa[n], Constants=dict(pa[n].get("Constants") or {}, zzConstanteFausse="42"))

    _nc2, _ni2, d2 = CI.validate_abilities(bc)
    derivees = {name for rows in d2.values() for name, _s, _r in rows}
    assert derivees == set(victimes), (
        "la derive fabriquee n'est pas celle qu'on croit : posee=%r mesuree=%r"
        % (sorted(victimes), sorted(derivees)))

    refreshed, added = CI.refresh_ability_configs(bc)
    assert set(refreshed) == derivees, (
        "le rattrapage ne repare pas exactement ce qui derive: derive=%r rafraichies=%r"
        % (sorted(derivees), sorted(refreshed)))
    _nc3, _ni3, apres = CI.validate_abilities(bc)
    assert not apres, "des configs derivent ENCORE apres rattrapage: %r" % (
        {k: v[:2] for k, v in apres.items()})
    print("\n[catalog/abilities] %d configs confrontees (%d internes moteur ignorees) ; catalogue "
          "FRAIS (0 derive) ; derive fabriquee %r reparee ; %d ajoutee(s) au chargement"
          % (nc, ni, sorted(derivees), len(added)))


# ============================================== catalogue UNITS -- l'axe AJOUT (#254-bc-r1)
#
# `STALE_UNIT_ENTRIES` garde l'ecart des entrees PRESENTES. Ce que le catalogue n'a PAS DU TOUT
# relevait de `missing_from_seed_bc`, qui enumere sans comparer : l'ecart etait passe de 17 a 21
# unites `lineup` sans qu'aucun garde le dise.
#
# ⚠ LES DEUX EPINGLES ONT CHANGE D'ORDRE DE GRANDEUR (#10039), MAIS PAS DE FORME. La forge amene
# tout le roster : `lineup` 21 -> 0 absents, `npc` 487 -> 2. Le premier devient un INVARIANT a
# zero (epingle VIDE, mais conservee : le gisement se rouvre des que le jeu livre un heros que la
# fabrique ne monte pas) ; le second, qui n'etait « rapporte et non garde » que parce que 487
# entrees n'etaient pas nommables, devient une epingle NOMINALE comme les autres.

def test_l_ecart_d_ajout_lineup_est_exactement_celui_qui_est_epingle():
    """Garde dans les DEUX sens, comme l'epingle voisine -- et l'epingle est VIDE.

    Une unite de PLUS = le gameconfig a livre un heros que la fabrique ne monte pas ; il n'est
    atteignable que par injection (`write_augmented_seed_bc`, case-92 Sec.6) et il faut l'INSCRIRE
    dans `MISSING_LINEUP_ENTRIES` apres l'avoir lu. Une unite en MOINS ne peut plus arriver : le
    zero est le plancher.

    ⚠ UNE EPINGLE VIDE N'EST PAS UNE GARDE VIDE. `obtenu == set()` mord des qu'un `lineup` sort du
    catalogue -- c'est meme la forme la plus stricte que ce test ait jamais eue : avant, 21 unites
    etaient EXEMPTEES, et une 22e n'aurait rougi que par comparaison a la liste.
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


def test_l_ecart_d_ajout_npc_est_exactement_celui_qui_est_epingle():
    """L'axe npc est passe de « rapporte, jamais garde » a EPINGLE NOMINALEMENT (#10039).

    ⚠ CE QUE L'ANCIENNE FORME GARDAIT, ET POURQUOI ELLE NE PEUT PAS RESTER. Elle disait : la
    capture ne porte que les npc de CETTE bataille, les 487 autres s'injectent a la demande, donc
    les garder rougirait a chaque MAJ pour rien -- et elle se contentait de `presents >= 4` et
    `missing > 100`. Le catalogue forge porte 489 des 491 npc : la seconde assertion mesure
    l'INVERSE de ce qu'elle gardait, et la premiere est devenue triviale.

    L'ecart est desormais assez petit pour etre NOMME, donc il est garde comme les deux autres
    axes, dans les DEUX sens. Les 2 restants ont leur cause LUE (`GetGuildWarsConfig` leve sur eux,
    inversion de voie deja documentee), pas devinee.
    """
    gap = CI.catalog_gap(_raw_seed())
    assert gap["npc"]["total"] > 400, gap["npc"]["total"]
    obtenu = set(gap["npc"]["missing"])
    assert obtenu == set(CI.MISSING_NPC_ENTRIES), {
        "neufs hors epingle": sorted(obtenu - set(CI.MISSING_NPC_ENTRIES)),
        "epingles mais presents": sorted(set(CI.MISSING_NPC_ENTRIES) - obtenu)}
    # Le temoin de `npc_witness_diff` (seul temoin non degenere du chemin npc) vit sur ces entrees.
    presents = gap["npc"]["total"] - len(obtenu)
    assert presents > 100, (
        "il ne reste que %d npc au catalogue : le temoin de `npc_witness_diff` redevient maigre"
        % presents)
    print("\n[catalog/gap] npc: %d au gameconfig, %d hors catalogue (epingles: %r)"
          % (gap["npc"]["total"], len(obtenu), sorted(obtenu)))


def test_le_rapport_d_ecart_se_TAIT_en_regime_nominal_et_PARLE_dans_les_deux_sens():
    """Un rapport qui parle tout le temps ne se lit plus. Celui-ci rend `None` tant que l'ecart est
    exactement l'epingle -- et chaque mutation le fait parler avec son propre mot.

    ⚠ LE BRAS « EPINGLEE MAIS PRESENTE » EST DEVENU INATTEIGNABLE PAR L'ETAT DU CATALOGUE
    (#10039) : `MISSING_LINEUP_ENTRIES` est vide, donc aucune unite ne peut a la fois etre
    epinglee et presente. Le bras du CODE, lui, garde toujours quelque chose -- il est ce qui
    dira, le jour ou une epingle sera posee puis resorbee, qu'il faut la retirer. On l'exerce donc
    en MUTANT l'epingle, exactement comme le bras (a) mute le gameconfig. Le supprimer aurait
    laisse une branche de `catalog_gap_report` sans aucun test.
    """
    seed = _raw_seed()
    assert CI.catalog_gap_report(seed) is None

    # (a) une unite `lineup` NEUVE au gameconfig, absente du catalogue.
    neuve = "zzUniteQuiNexistePas"
    idx = G._index()
    idx["lineup"][neuve] = {"traits": []}
    try:
        rapport = CI.catalog_gap_report(seed)
        assert rapport and "lineup NEUVES hors epingle" in rapport and neuve in rapport, rapport
    finally:
        idx["lineup"].pop(neuve, None)

    # (a bis) meme chose sur l'axe npc, qui n'etait pas garde du tout avant #10039.
    neuf = "zzNpcQuiNexistePas"
    idx["npc"][neuf] = {"traits": [], "kind": "npc"}
    try:
        rapport = CI.catalog_gap_report(seed)
        assert rapport and "npc NEUVES hors epingle" in rapport and neuf in rapport, rapport
    finally:
        idx["npc"].pop(neuf, None)

    # (b) une unite EPINGLEE qui entre au catalogue -- il faut alors la RETIRER de l'epingle.
    entree = sorted(G._index()["lineup"])[0]
    seed2 = copy.deepcopy(seed)
    seed2["Units"] = [u for u in seed2["Units"] if u["Id"].split(":")[0] != entree]
    sauve = CI.MISSING_LINEUP_ENTRIES
    try:
        CI.MISSING_LINEUP_ENTRIES = frozenset({entree})
        assert CI.catalog_gap_report(seed2) is None, "l'epingle ne couvre pas ce qu'elle nomme"
        rapport = CI.catalog_gap_report(seed)          # l'unite est de retour au catalogue
        assert rapport and "lineup epinglees mais PRESENTES" in rapport and entree in rapport, \
            rapport
    finally:
        CI.MISSING_LINEUP_ENTRIES = sauve

    # (b bis) le meme bras sur l'axe npc, avec l'epingle REELLE : un des deux npc qui revient.
    npc_epingle = sorted(CI.MISSING_NPC_ENTRIES)[0]
    seed3 = copy.deepcopy(seed)
    seed3["Units"].append({"Id": npc_epingle})
    rapport = CI.catalog_gap_report(seed3)
    assert rapport and "npc epinglees mais PRESENTES" in rapport and npc_epingle in rapport, rapport

    # (c) un SUMMON qui disparait du catalogue -- l'axe que `missing_from_seed_bc` ne voyait pas.
    smn = sorted(G._index()["summons"])[0]
    seed4 = copy.deepcopy(seed)
    seed4["Units"] = [u for u in seed4["Units"] if u["Id"].split(":")[0] != smn]
    rapport = CI.catalog_gap_report(seed4)
    assert rapport and "SUMMONS absents" in rapport and smn in rapport, rapport
    assert CI.catalog_gap_report(seed) is None       # aucune fuite d'etat entre les bras
