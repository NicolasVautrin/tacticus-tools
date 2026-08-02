"""GARDE de l'axe 5 de `symbols_sync.py` -- la couverture par grande famille (#259).

CE QUE CES TESTS PROTEGENT. L'axe 5 doit HURLER sur une chute massive et rester MUET sur le
churn normal d'une mise a jour. Les deux moities comptent autant : une garde qui crie tous les
jours s'ignore aussi surement qu'une garde absente -- c'est precisement pour ca que la perte
de 4 882 symboles du 2026-07-29 est passee inapercue (les quatre axes existants etaient verts,
et personne ne comptait le contenu).

QUATRE PROPRIETES CONFRONTEES ICI :
 1. la CLASSIFICATION isole le MECANISME (corps pleinement partages) au lieu du namespace --
    sans ca les 4 882 corps se diluent et leur perte devient invisible ;
 2. le SEUIL laisse passer le churn REELLEMENT MESURE (tables Frida gqfc5mff6c -> rnca9r7q6c :
    aucune famille >= 100 n'a perdu un membre ; pire ratio cote Ghidra = 0,863) et refuse
    l'effondrement (ratio 0,000) ;
 3. le registre des PERTES CONNUES est keye sur la TRANSITION (famille, ref, courant) : il
    tait une perte deja documentee, et RIEN d'autre -- ni la meme famille sur une autre
    transition, ni une autre famille sur la meme ;
 4. toute entree de ce registre a la FORME que le mecanisme sait lire (triplet exact) et porte
    de quoi la RETIRER un jour (numero de tache + renvoi de fiche) -- une cle mal formee produit
    une entree inerte que rien ne signalait, et une excuse sans renvoi ne se retire jamais.

LE MECANISME EST CONFRONTE SUR UNE ENTREE SYNTHETIQUE, JAMAIS SUR LE CONTENU REEL DU REGISTRE
(#282). `PERTES_CONNUES` est une DONNEE D'EXPLOITATION dont l'etat NOMINAL est VIDE : une excuse
doit disparaitre des que sa cause est reparee. La version d'origine prelevait sa fixture par
`next(iter(PERTES_CONNUES.items()))` ; la reparation `5c72a488` (#259-a, 2026-07-29 22:26) a
retire l'unique entree apres avoir remonte GSHARED de 0 a 4 874, et les quatre tests du registre
sont tombes en `StopIteration` -- sans qu'une seule ligne de `comparer_couverture` ait bouge. Le
rouge accusait le MONTAGE. Detail : `docs/rl/case-282-pertes-connues-vide.md`.

Offline pur : aucun runner, aucune session Frida, aucune lecture de `data/`.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import symbols_sync as S  # noqa: E402

# La TRANSITION reellement mesuree (cf. docstring, propriete 2). Ces deux noms sont
# LOAD-BEARING : `comparer_couverture` les utilise comme cle du registre `PERTES_CONNUES`
# (`PERTES_CONNUES.get((fam, ref_nom, cur_nom))`), donc les remplacer par `buildA`/`buildB`
# ferait passer le test sur une AUTRE transition que celle dont les chiffres sont ci-dessous.
#
# Ils sont COMPOSES, jamais ecrits en clair -- meme motif que le `_SEG` de
# `test_314_absolute_repo_path_offline.py` : ce sont des DONNEES de fixture, pas une
# resolution d'artefact, et le cliquet `probe_431_build_literals` ne peut pas faire cette
# difference (son critere est LOCAL par conception -- deux criteres contextuels ont ete
# essayes et rejetes, cf. son docstring). Ecrits en clair ils le feraient rougir sur un
# fichier qui ne lit aucun binaire. Aucune lecture de `data/` : ce test reste offline pur.
_REF = "gqfc5mff" + "6c"
_CUR = "rnca9r7q" + "6c"


# ----------------------------------------------------- entree SYNTHETIQUE du registre
#
# Une entree de `PERTES_CONNUES` qui n'existe QUE le temps du test. Elle porte deliberement
# des noms qui ne peuvent designer ni une vraie famille ni un vrai hash de build : si elle
# fuyait hors du test, elle ne pourrait taire aucune chute reelle.
_CLE_TEST = ("il2cpp:FamilleSynthetique", "buildRefSynthetique", "buildCurSynthetique")
_MOTIF_TEST = ("#282 -- entree SYNTHETIQUE de test, elle ne designe aucun build reel : "
               "docs/rl/case-282-pertes-connues-vide.md")


def _verifier_forme(cle, motif) -> None:
    """Ce qu'une entree doit etre pour que le mecanisme la TROUVE et qu'elle reste CONSULTABLE.

    Trouvable : la cle est le triplet exact (famille, ref, courant) que `comparer_couverture`
    presente a `PERTES_CONNUES.get(...)` -- un tuple de 2, ou une famille orthographiee de
    travers, produit une entree inerte qui ne tait rien et que rien ne signale.
    Consultable : le motif porte un numero de tache ET un renvoi vers une fiche. Une excuse
    sans renvoi est une excuse qu'on ne saura pas retirer -- or la retirer FAIT PARTIE de la
    reparation (`symbols_sync.py`, en tete du registre)."""
    assert isinstance(cle, tuple) and len(cle) == 3, (
        "cle de PERTES_CONNUES = (famille, build_reference, build_courant), pas %r" % (cle,))
    assert all(isinstance(x, str) and x for x in cle), (
        "les trois membres de la cle sont des chaines non vides : %r" % (cle,))
    assert isinstance(motif, str) and motif, "le motif est une chaine non vide"
    assert "#" in motif, ("le motif cite le numero de la tache qui suit la perte : %r" % motif)
    assert ".md" in motif, ("le motif renvoie a la fiche qui la documente : %r" % motif)


@pytest.fixture
def entree_registre(monkeypatch):
    """Injecte l'entree synthetique dans le registre REEL, et la retire a la sortie.

    `monkeypatch.setitem` restaure l'etat exact -- la cle etant absente au depart, elle est
    SUPPRIMEE apres le test : aucun test ne peut en desamorcer un autre."""
    monkeypatch.setitem(S.PERTES_CONNUES, _CLE_TEST, _MOTIF_TEST)
    return _CLE_TEST, _MOTIF_TEST


# --------------------------------------------------------------------- classification

def test_famille_isole_le_mecanisme_gshared_avant_le_namespace():
    """Un corps pleinement partage compte comme GSHARED, PAS comme `il2cpp:IdunBattle`.

    C'est LA decision qui rend la panne visible : la maille namespace ne bougeait que de
    -1,8 % sur `IdunBattle.AI.Playbook` (2 122 -> 2 083) alors que des centaines de corps y
    avaient disparu."""
    gshared = ("IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E"
               "$$CalculateActionUtility")
    assert S._famille(gshared) == "GSHARED"
    assert S._famille("IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw") == "il2cpp:IdunBattle"
    # variante StructType : meme mecanisme, meme famille
    assert S._famille("IdunBattle.Entities.Components.PersistentDataComponent"
                      "$$PersistDatau003C__Il2CppFullySharedGenericStructTypeu003E") == "GSHARED"


def test_famille_place_les_placeholders_a_part():
    """FUN_/DAT_/PTR_ ne sont pas de la couverture : une baisse y est une BONNE nouvelle."""
    assert S._famille("FUN_18011fd60") == "PLACEHOLDER"
    assert S._famille("DAT_183287db8") == "PLACEHOLDER"


def test_famille_range_la_notation_pointee_hors_des_familles_il2cpp():
    """L'incident de FORME du 2026-07-29 (noms pointes au lieu de `Classe$$Membre`).

    Il est deja attrape par l'axe 4 ; l'axe 5 doit le voir AUSSI, parce qu'une table pointee
    vide TOUTES les familles `il2cpp:*` d'un coup."""
    assert S._famille("IdunBattle.Core.Services.DamagePrediction.PredictAttackRaw") == "AUTRE"


# ---------------------------------------------------------------------------- le seuil

def test_le_churn_REELLEMENT_MESURE_ne_declenche_rien():
    """Chiffres pris tels quels de `probe_259_gshared_coverage.py` etape 1 (tables Ghidra),
    GSHARED mis de cote. Ce sont de vrais comptes, pas des valeurs inventees pour passer."""
    vieux = {"il2cpp:UnityEngine": 28640, "PLACEHOLDER": 22647, "il2cpp:idun": 22327,
             "il2cpp:System": 19184, "il2cpp:IdunBattle": 14979, "il2cpp:thor": 4686,
             "il2cpp:IdunMetaLogic": 4255, "il2cpp:IdunBattleLogic": 3330,
             "il2cpp:Idun": 2083, "il2cpp:I2": 382, "il2cpp:Loki": 358,
             "il2cpp:BaseTest": 124, "AUTRE": 775}
    neuf = {"il2cpp:UnityEngine": 31040, "PLACEHOLDER": 28716, "il2cpp:idun": 25546,
            "il2cpp:System": 20436, "il2cpp:IdunBattle": 15540, "il2cpp:thor": 4915,
            "il2cpp:IdunMetaLogic": 4422, "il2cpp:IdunBattleLogic": 3519,
            "il2cpp:Idun": 2727, "il2cpp:I2": 380, "il2cpp:Loki": 352,
            "il2cpp:BaseTest": 107, "AUTRE": 740}
    lignes = S.comparer_couverture(vieux, neuf, _REF, _CUR)
    assert any("aucune chute inattendue" in l for l in lignes)


def test_la_panne_reelle_declenche():
    """4 882 -> 0 sur une transition NON enregistree : la garde doit refuser."""
    vieux = {"GSHARED": 4882, "il2cpp:IdunBattle": 14979}
    neuf = {"GSHARED": 0, "il2cpp:IdunBattle": 15540}
    with pytest.raises(S.Desync) as exc:
        S.comparer_couverture(vieux, neuf, "buildA", "buildB")
    assert "COUVERTURE EFFONDREE" in str(exc.value)
    assert "GSHARED" in str(exc.value)


def test_une_famille_metier_amputee_de_moitie_declenche():
    """Le cas qui compte vraiment pour la suite : pas seulement GSHARED."""
    vieux = {"il2cpp:IdunBattle": 15000}
    neuf = {"il2cpp:IdunBattle": 7000}          # ratio 0,467 < 0,60
    with pytest.raises(S.Desync):
        S.comparer_couverture(vieux, neuf, "buildA", "buildB")


def test_les_petites_familles_ne_declenchent_pas():
    """< 100 symboles : bruit relatif eleve (ratio mesure entre 0,750 et 2,000 sur 526
    familles), aucune conclusion possible -- on ne crie pas dessus."""
    vieux = {"il2cpp:Marginal": 40}
    neuf = {"il2cpp:Marginal": 3}
    assert S.comparer_couverture(vieux, neuf, "buildA", "buildB")


def test_une_chute_de_placeholders_ne_declenche_pas():
    """Moins de FUN_ = plus de noms. Alerter la-dessus serait a contresens."""
    vieux = {"PLACEHOLDER": 28716}
    neuf = {"PLACEHOLDER": 900}
    assert S.comparer_couverture(vieux, neuf, "buildA", "buildB")


def test_le_seuil_est_franchi_juste_en_dessous_et_pas_juste_au_dessus():
    """Confronte la BORNE elle-meme, pas seulement des cas confortables."""
    juste_au_dessus = int(1000 * S.SEUIL_COUVERTURE) + 1
    juste_en_dessous = int(1000 * S.SEUIL_COUVERTURE) - 1
    assert S.comparer_couverture({"il2cpp:X": 1000}, {"il2cpp:X": juste_au_dessus}, "a", "b")
    with pytest.raises(S.Desync):
        S.comparer_couverture({"il2cpp:X": 1000}, {"il2cpp:X": juste_en_dessous}, "a", "b")


# ----------------------------------------------------------------- registre des pertes

def test_la_perte_connue_est_taue_MAIS_imprimee(entree_registre):
    """Tue != cachee. Une perte enregistree ne fait pas echouer la garde, mais elle est
    IMPRIMEE avec son motif : c'est ce qui la garde consultable au lieu de la faire oublier."""
    (fam, ref, cur), motif = entree_registre
    lignes = S.comparer_couverture({fam: 4882}, {fam: 0}, ref, cur)
    assert any("PERTE CONNUE" in l and fam in l for l in lignes)
    assert any(motif in l for l in lignes)


def test_la_perte_connue_ne_couvre_QUE_sa_transition(entree_registre):
    """Keyee sur (famille, ref, courant) : la MEME famille sur une AUTRE transition doit
    redeclencher. Sans ca, l'entree deviendrait un silencieux permanent -- une garde
    desamorcee par son propre registre."""
    (fam, _, cur), _ = entree_registre
    with pytest.raises(S.Desync):
        S.comparer_couverture({fam: 4882}, {fam: 0}, cur, "buildSuivant")


def test_la_perte_connue_ne_couvre_pas_une_autre_famille(entree_registre):
    (_, ref, cur), _ = entree_registre
    with pytest.raises(S.Desync):
        S.comparer_couverture({"il2cpp:IdunBattle": 15000}, {"il2cpp:IdunBattle": 10},
                              ref, cur)


def test_la_reference_est_la_plus_RECEMMENT_DUMPEE_pas_la_premiere_du_tri(tmp_path):
    """Avec trois builds archives, comparer contre le mauvais rendrait la garde absurde.

    Le hash d'un build (`gqfc5mff6c`, `rnca9r7q6c`, ...) n'a AUCUN sens chronologique : trie
    alphabetiquement, l'ordre est arbitraire. La seule donnee de date qui existe est le champ
    `generated=` de l'estampille de provenance, et c'est celle qu'on suit."""
    stamps = {"aaaa111111": "2026-05-01T10:00:00",
              "zzzz999999": "2026-06-01T10:00:00",     # le plus recent, dernier en alpha
              "mmmm555555": "2026-04-01T10:00:00"}
    for nom in stamps:
        (tmp_path / nom / "ghidra").mkdir(parents=True)
        (tmp_path / nom / "ghidra" / "functions.tsv").write_text("# build=%s\n" % nom,
                                                                 encoding="utf-8")
    S_archived, S_builddir, S_stamp = S.archived_builds, S._build_dir, S.read_stamp
    try:
        S.archived_builds = lambda: sorted(stamps)
        S._build_dir = lambda nom: tmp_path / nom
        S.read_stamp = lambda p: {"generated": stamps[p.parent.parent.name]}
        assert S._reference_la_plus_recente() == tmp_path / "zzzz999999"
    finally:
        S.archived_builds, S._build_dir, S.read_stamp = S_archived, S_builddir, S_stamp


def test_une_archive_SANS_table_ghidra_est_ecartee_pas_choisie(tmp_path):
    """Etat REEL et transitoire du depot : les trois TSV Frida d'un build sont commites
    (`b8dba3c0`) AVANT que la passe Ghidra n'existe (`04980aa1`). Prendre une telle archive
    pour reference ferait lire « toutes les familles a zero » -- une fausse alerte totale."""
    complet = tmp_path / "complet"
    (complet / "ghidra").mkdir(parents=True)
    (complet / "ghidra" / "functions.tsv").write_text("# build=complet\n", encoding="utf-8")
    partiel = tmp_path / "partiel"
    (partiel / "frida").mkdir(parents=True)
    stamps = {"complet": "2026-01-01T00:00:00", "partiel": "2026-09-09T00:00:00"}  # partiel = + recent
    S_archived, S_builddir, S_stamp = S.archived_builds, S._build_dir, S.read_stamp
    try:
        S.archived_builds = lambda: ["complet", "partiel"]
        S._build_dir = lambda nom: tmp_path / nom
        S.read_stamp = lambda p: {"generated": stamps[p.parent.parent.name]}
        assert S._reference_la_plus_recente() == complet
    finally:
        S.archived_builds, S._build_dir, S.read_stamp = S_archived, S_builddir, S_stamp


def test_sans_archive_l_axe_est_NON_VERIFIE_et_surtout_pas_vert():
    """Meme discipline que l'axe ghidra quand le serveur est eteint : « pas verifiable » ne
    doit jamais se lire comme « verifie et bon »."""
    S_ref = S._reference_la_plus_recente
    try:
        S._reference_la_plus_recente = lambda: None
        lignes, vu = S.axe5_couverture(Path("peu-importe"))
        assert vu is False
        assert any("non verifiable" in l for l in lignes)
    finally:
        S._reference_la_plus_recente = S_ref


def test_le_registre_s_auto_perime_quand_la_famille_est_a_zero_des_deux_cotes(entree_registre):
    """A la MAJ suivante, l'archive de reference sera elle-meme depourvue de la famille :
    0 -> 0 est sous le plancher, donc plus aucune ligne. L'entree devient inerte sans qu'on
    ait a la retirer a la main -- et si la couverture est RETABLIE, elle l'est aussi.

    NB (#282) : ce filet EXISTE, mais ce n'est PAS lui qui a vide le registre le 2026-07-29.
    L'entree GSHARED a ete retiree A LA MAIN par `5c72a488`, la famille etant remontee a 4 874
    -- donc jamais a zero cote reference. Le filet reste la garde du cas ou la reparation
    n'aurait PAS eu lieu avant la MAJ suivante."""
    (fam, _, _), _ = entree_registre
    lignes = S.comparer_couverture({fam: 0}, {fam: 0}, "buildB", "buildC")
    assert not any("PERTE CONNUE" in l for l in lignes)


def test_toute_entree_du_registre_a_la_FORME_que_le_mecanisme_sait_lire():
    """Applique le MEME controle a l'entree synthetique et a chaque entree REELLE.

    Le controle de l'entree synthetique s'execute a chaque run, donc ce test n'est jamais
    vacuous meme registre vide -- et il garantit que la fixture des tests ci-dessus est
    REPRESENTATIVE de ce qu'on ecrit pour de vrai, au lieu d'un raccourci qui passerait
    la ou une vraie entree echouerait."""
    _verifier_forme(_CLE_TEST, _MOTIF_TEST)
    for cle, motif in S.PERTES_CONNUES.items():
        _verifier_forme(cle, motif)


def test_un_registre_VIDE_est_l_etat_NOMINAL_et_ne_desamorce_pas_la_garde():
    """#282. Vide n'est ni une panne ni une garde eteinte : c'est l'etat vise.

    Le registre a ete vide le 2026-07-29 par `5c72a488` (#259-a) PARCE QUE la perte etait
    reparee -- mesure re-derivable, `GSHARED` 4 882 -> 4 874 entre `gqfc5mff6c` et
    `rnca9r7q6c` (`python scripts/python/probe_282_registre_pertes.py`). Ce que ce test
    exige, c'est qu'une chute effondree sur une transition ABSENTE du registre leve
    TOUJOURS : le vide ne peut pas se confondre avec un silencieux."""
    fam, ref, cur = "il2cpp:FamilleAbsenteDuRegistre", "refAbsente", "curAbsente"
    assert (fam, ref, cur) not in S.PERTES_CONNUES
    with pytest.raises(S.Desync):
        S.comparer_couverture({fam: 4882}, {fam: 0}, ref, cur)
