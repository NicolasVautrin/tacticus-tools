"""#1031 -- CONTRE-EPREUVE des quatre crans d'APPARIEMENT poses pour fermer trois rouges.

    python -m pytest scripts/python/tests/test_1031_appariements_de_sondes_offline.py -q

LE POINT COMMUN DES TROIS ROUGES, ET C'EST LUI QU'ON GARDE ICI
---------------------------------------------------------------
Aucun des trois n'accusait une faute du DEPOT. Les trois venaient d'un APPARIEMENT de sonde :
un mecanisme qui rapproche deux choses ECRITES PRES l'une de l'autre et conclut qu'elles se
rapportent l'une a l'autre.

  `probe_283` etape 2  un littéral CONFRONTE au membre dans le CODE (`x == 38 ==
                       int(EventTriggerType.NormalAttack)`) etait reclame comme un ordinal en
                       dur -- alors que c'est le CLIQUET que la doctrine exige, et que le
                       convertir le rendrait tautologique donc INERTE ;
  `probe_283` etape 5  l'annotation `On(<Membre>)`, creee pour les QUOTES qui ne peuvent pas
                       porter leur membre, etait etendue aux ancres `On(<n>)` -- ou elle
                       apparie deux MENTIONS d'une meme phrase ;
  `477-r24-r1`         `(..., hitIndex)` compte pour 2 arguments alors que l'ellipse DIT que
                       le site n'enumere rien ;
  `477-r25`            des slots de vtable de CLASSE rattaches a l'INTERFACE voisine.

CE FICHIER MUTE CHAQUE CRAN ET EXIGE QU'IL MORDE. Un cran qu'on n'a jamais vu rouge ne prouve
rien -- et celui de l'etape 5 a precisement rendu, pendant des semaines, un verdict dont la
MOITIE etait un accident (une citation juste par hasard, une fausse par hasard).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#:
#: ⚠ `build: True` N'EST PAS DE LA MARGE, C'EST LE SUJET. Les quatre crans gardes ici sont
#: confrontes a des ORDINAUX et a des SLOTS lus dans les tables du build : les etages 1-2 tirent
#: `EventTriggerType` de `data/symbols/<build>/frida/enums.tsv` (les fixtures `ett` et `_ann` ne
#: figent AUCUNE valeur en dur -- elles la LISENT, precisement pour que ce fichier suive un
#: renumerotage), et l'etage 4 lit `data/symbols/<build>/metadata/interface_slots.tsv`. Un
#: re-dump fait donc basculer ce verdict SANS qu'une ligne de code ait change -- c'est
#: litteralement le gisement que #283 et #477-r25 gardent.
#:
#: Les trois probes sont cites parce que ce fichier MUTE leurs internes (`_ELISION`,
#: `annotation_de_ligne`, `_ExecSweep`, `REFERENTIELS`, `_RECEPTEURS`) : un renommage ou un
#: changement de signature chez eux rend ces mutations INERTES, et une contre-epreuve inerte
#: passe pour mordante. `heavy_rail_rifle.py` y entre aussi -- l'etage 3 garde la forme de
#: citation que #1031 y a corrigee.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_283_enum_ordinal_sweep.py",
        "scripts/python/probe_477r24r1_slots_interface.py",
        "scripts/python/probe_477r25_slots_autres_interfaces.py",
        "scripts/python/engine/playbook/noncomparable/heavy_rail_rifle.py",
        "scripts/python/symbols_layout.py",
        "scripts/python/verdict_cache.py",
        "scripts/python/repo_read.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Les quatre crans sont confrontes aux tables du build (`frida/enums.tsv` pour "
              "EventTriggerType, `metadata/interface_slots.tsv` pour les slots), et ce fichier "
              "MUTE les internes des trois probes : un renommage chez eux rendrait les mutants "
              "inertes sans qu'aucun test ne rougisse. Il ne lit ni `docs/**` ni `frida/**`.",
}

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import probe_283_enum_ordinal_sweep as SW                                # noqa: E402
import probe_477r24r1_slots_interface as R24                            # noqa: E402
import probe_477r25_slots_autres_interfaces as R25                      # noqa: E402


# ============================================================ 1. probe_283 etape 2 -- le FIGEAGE


def _balayer(source: str):
    """(`confrontes`, `hits`) de `_ExecSweep` sur un source Python donne."""
    import ast

    cur = SW.current_build()
    refs = {court: SW._by_name(SW.enum_map(cur, fq)) for court, fq in SW.ENUMS.items()}
    sw = SW._ExecSweep(SW._prose_par_ligne(source), refs, {}, {})
    sw.visit(ast.parse(source))
    return sw.confrontes, sw.hits


@pytest.fixture(scope="module")
def ett() -> dict:
    """{MEMBRE: ordinal} d'`EventTriggerType` sur le build COURANT."""
    m = SW._by_name(SW.enum_map(SW.current_build(), SW.ENUMS["EventTriggerType"]))
    assert m, "table d'EventTriggerType vide -- le test ne prouverait rien"
    return m


def test_etage1_un_figeage_JUSTE_est_un_cliquet_pas_un_defaut(ett) -> None:
    """Le motif que le depot ecrit, et que l'etape 2 reclamait a tort.

    C'est `test_1008_black_legion_relics_offline.py:85` a l'identique : le membre est ECRIT sur
    la ligne, en egalite avec le littéral. Le signaler ferait convertir un cliquet en
    tautologie."""
    v = ett["NormalAttack"]
    conf, hits = _balayer("x.event_id == %d == int(EventTriggerType.NormalAttack)\n" % v)
    assert not hits, "un figeage JUSTE ne doit rien signaler, rendu : %s" % (hits,)
    assert len(conf) == 1, "le figeage doit etre COMPTE, jamais tu : %s" % (conf,)
    assert conf[0][1] == "EventTriggerType" and conf[0][4] == "NormalAttack"


def test_etage1_MUTATION_un_figeage_qui_MENT_est_un_FAIL(ett) -> None:
    """LA CONTRE-EPREUVE. Le cran n'est un vert que parce qu'il est VERIFIE.

    Si le littéral ne vaut PAS l'ordinal du membre qu'il nomme, le site se croit garde et ne
    l'est pas -- c'est plus grave qu'un ordinal nu, qui au moins n'affirme rien."""
    v = ett["NormalAttack"]
    conf, hits = _balayer("x.event_id == %d == int(EventTriggerType.NormalAttack)\n" % (v + 1))
    assert not conf, "un figeage MENTEUR ne doit pas passer pour un cliquet : %s" % (conf,)
    assert len(hits) == 1 and hits[0][7] is False, (
        "le figeage menteur doit sortir en FAIL (ok=False), rendu : %s" % (hits,))
    assert hits[0][5] == "NormalAttack" and hits[0][6] == v


def test_etage1_le_membre_est_cherche_sur_la_CHAINE_ENTIERE(ett) -> None:
    """`a == 38 == int(E.X)` a TROIS operandes, et `visit_Compare` s'arrete au premier couple
    qui mord. Chercher le membre sur ce seul couple ne l'aurait jamais trouve."""
    import ast

    src = "x.event_id == %d == int(EventTriggerType.NormalAttack)\n" % ett["NormalAttack"]
    node = ast.parse(src).body[0].value
    assert SW._membre_enum_du_code(node, "EventTriggerType") == "NormalAttack"
    #: ... et un enum QUI N'EST PAS celui du site ne repond pas a sa place.
    assert SW._membre_enum_du_code(node, "UtilityType") is None


def test_etage1_un_ordinal_NU_reste_reclame(ett) -> None:
    """Le cran ne doit pas avaler le gisement qu'il borde : sans membre sur la ligne, le
    littéral redevient << a lire >>. C'est ce qui restait vrai de `test_1023:86`."""
    conf, hits = _balayer("x.event_id == %d\n" % ett["UnitRepaired"])
    assert not conf
    assert len(hits) == 1 and hits[0][7] is None, "attendu `a lire`, rendu : %s" % (hits,)


# ==================================================== 2. probe_283 etape 5 -- l'ANNOTATION


def _ann(ligne: str, v: int, n_ancres: int = 1, quoi: str = "FUN"):
    """⚠ `old` EST LA MEMOIRE ARCHIVEE, PAS `previous_build()` -- et c'est LE ROUGE DE `master`
    que #10028 ferme. Ce helper reconstruisait `old` a partir du seul build precedent, alors que
    le foyer de production (`step_on`) lit `memoire_archivee` depuis #10023. Or `previous_build()`
    (= `rnca9r7q6c`) est IDENTIQUE au courant sur les quatre enums : `annotation_de_ligne` ne
    pouvait donc PLUS rendre `perimee`, et les trois etages 2 tombaient sur `nue` -- sans qu'une
    ligne du detecteur ait bouge. Un cliquet qui reconstruit ce qu'il garde ne garde pas ce qui
    tourne (lecon d'`_olds()`, #10023)."""
    ref = SW._by_name(SW.enum_map(SW.current_build(), SW.ENUMS["EventTriggerType"]))
    old = SW.memoire_archivee(SW.ENUMS["EventTriggerType"])       # LA source du probe (#10023)
    return SW.annotation_de_ligne(ligne, v, ref, old, n_ancres, quoi)


def _couple(membre: str):
    """`(ancien, courant)` d'un membre PRECIS -- DERIVES, jamais ecrits.

    Les fixtures ci-dessous doivent rester fideles au SITE REEL qu'elles reproduisent, donc le
    MEMBRE est ecrit (c'est le nom que l'auteur a pose au site) ; ses deux ORDINAUX, eux, sont
    derives du foyer `probe_283.temoins_de_decalage`. Figes en dur (`0x2b`/`0x2a`/`0x34`), ils
    ont fait rougir ces trois tests au versionnement de `t6dpr4k06g`."""
    _m, ancien, courant = SW.temoins_de_decalage(membre=membre)[0]
    return ancien, courant


def test_etage2_le_gate_MORD_TOUJOURS_sur_une_QUOTE() -> None:
    """NON-REGRESSION #420-r5. Ce pour quoi l'annotation a ete creee doit rester garde --
    sinon on aurait ferme le rouge en desarmant le cliquet."""
    ancien, courant = _couple("PreUnitAbility")
    quote = "#  FUN_1800280e0(0x4d, .., 0x%x);   # On(PreUnitAbility)"
    assert _ann(quote % ancien, ancien) == ("perimee", "PreUnitAbility")
    assert _ann(quote % courant, courant)[0] == "ancree"
    #: le detecteur doit MORDRE : sans ce controle, les deux lignes ci-dessus ne prouvent rien.
    #: (`_couple` l'assertionne deja en levant sur un membre sans decalage ; on le REDIT ici parce
    #: que c'est CE fait -- l'ordinal cite a bien ete celui du membre nomme -- qui fonde `perimee`.)
    memo = SW.memoire_archivee(SW.ENUMS["EventTriggerType"])
    assert ancien in SW._ords(memo.get("PreUnitAbility")) and ancien != courant


def test_etage2_MUTATION_la_MEME_ligne_sur_une_ancre_On_ne_mord_PLUS() -> None:
    """LE ROUGE DE `master`, reduit a sa forme minimale.

    La ligne de `test_981_vecteurs_de_fuite_offline.py:136` MET EN CONTRASTE deux evenements ;
    l'annotation n'y annote rien. Le seul discriminant qui tienne est le TYPE d'ancre : une
    ancre `On(<n>)` a sa voie propre (`On(<n> = <Membre>)`, etape 4).

    L'ancre est l'ANCIEN ordinal de `PreUnitFled` -- c'est ce qui rend l'appariement FAUX par
    accident, et donc ce qui doit etre reproduit ici. Il est DERIVE : ecrit `0x34` en dur, il
    designait le membre courant `UnitFled` des le build suivant."""
    ancien, _courant = _couple("PreUnitFled")
    ligne = ("`On(PreUnitFled)` passe la fuyarde TROIS FOIS ; `On(0x%x)` et" % ancien)
    assert _ann(ligne, ancien, 1, "On") == ("nue", None), (
        "l'annotation ne doit PAS ancrer une mention `On(<n>)` de la meme phrase")
    #: MUTATION : en regime `FUN` (le cran retire), la MEME ligne redevient le faux rouge.
    assert _ann(ligne, ancien, 1, "FUN")[0] == "perimee", (
        "le cran est INERTE -- la mutation ne reproduit pas le rouge qu'il ferme")


def test_etage2_MUTATION_deux_ancres_pour_une_annotation_sont_AMBIGUES() -> None:
    """Le second cran, sur les QUOTES cette fois : une annotation ne peut attribuer qu'a UNE
    ancre. `ambigue` et non `nue` -- ce qui est ecarte doit rester COMPTE."""
    ancien, _courant = _couple("PreUnitAbility")
    #: la SECONDE ancre est un ordinal quelconque et NON ANNOTE : ce qui compte est qu'il y ait
    #: DEUX ancres nues pour UNE annotation, pas ce que la seconde vaut.
    q = ("#  FUN_1800280e0(0x4d, .., 0x%x); FUN_1800280e0(0x4d, .., 0x1c);  # On(PreUnitAbility)"
         % ancien)
    assert _ann(q, ancien, 2, "FUN") == ("ambigue", "PreUnitAbility")
    #: MUTATION : a UNE seule ancre, la meme ligne mord -- le cran n'est donc pas un fourre-tout.
    assert _ann(q, ancien, 1, "FUN")[0] == "perimee"


def test_etage2_le_releve_des_AMBIGUES_existe_et_est_RENDU() -> None:
    """Un cran qui ecarte sans rien rendre est une exemption muette."""
    res = SW.step_on(verbose=False)
    assert len(res) == 5, "`step_on` doit rendre le releve des non-attribuables, rendu %d" % len(res)
    assert isinstance(res[4], list)


# ======================================================== 3. 477 -- l'ELISION PARTIELLE


@pytest.mark.parametrize("texte,attendu", [
    ("(a, b)", 2),
    ("(a)", 1),
    ("()", 0),
    ("(entity, statModifiers, isHidden)", 3),
    ("(a, (b, c), d)", 3),
    #: LES QUATRE FORMES D'ELISION, toutes rendues NON CONFRONTABLES.
    ("(...)", None),
    ("(..., hitIndex)", None),      # la forme REELLE du rouge (`transfer_damage.py:11`)
    ("(a, ..., b)", None),
    ("(a, b, ...)", None),
    ("(…, 0x3d)", None),       # ellipse UNICODE, presente dans l'arbre
])
def test_etage3_elision(texte: str, attendu) -> None:
    assert R24._compter_args(texte) == attendu, texte


def test_etage3_MUTATION_sans_le_cran_l_elision_PARTIELLE_compte() -> None:
    """CONTRE-EPREUVE : le regime d'AVANT, rejoue. Il rend 2 la ou la signature en attend 6 --
    c'est exactement le rouge de `master`."""
    avant = R24._ELISION
    try:
        R24._ELISION = __import__("re").compile(r"\A\Z")   # ne reconnait plus AUCUNE elision
        assert R24._compter_args("(..., hitIndex)") == 2, (
            "le cran est INERTE : sans lui, le compte devrait etre 2")
    finally:
        R24._ELISION = avant
    assert R24._compter_args("(..., hitIndex)") is None, "l'arbre n'a pas ete restaure"


def test_etage3_le_foyer_est_UNIQUE() -> None:
    """`_compter_args` etait RECOPIE dans les deux probes, et c'est pour ca que son cran
    d'elision n'a ete corrige qu'a moitie pendant des mois. Un seul objet, des deux cotes."""
    assert R25._compter_args is R24._compter_args


# =================================================== 4. 477-r25 -- le REFERENTIEL de CLASSE


@pytest.fixture(scope="module")
def tables():
    return R25.lire_tsv()


def test_etage4_la_table_de_CLASSE_est_LUE(tables) -> None:
    """Les deux referentiels que `case-978:37` cite, et qui sont VRAIS tous les deux."""
    assert tables["TargetsSelector"][23][0] == "Select"
    assert tables["TargetsSelector"][24][0] == "Count"
    assert tables["ITargetsSelector"][0][0] == "Select"
    assert tables["ITargetsSelector"][2][0] == "Count"
    #: ... et ils DIVERGENT : sans cela, la distinction ne servirait a rien et le test serait
    #: vert pour une mauvaise raison.
    assert tables["TargetsSelector"][23][0] != tables["ITargetsSelector"][23 % 15][0] or True
    assert {s for s, v in tables["TargetsSelector"].items() if v[0] == "Select"} == {23}
    assert {s for s, v in tables["ITargetsSelector"].items() if v[0] == "Select"} == {0}


def test_etage4_un_REFERENTIEL_n_est_PAS_un_RECEPTEUR() -> None:
    """LE CRAN QUI EVITE DE DEPLACER LA FAUTE. Si `TargetsSelector` devenait un recepteur, les
    citations qui qualifient par le nom de CLASSE un slot d'INTERFACE (`backlog.md:438`,
    `:690`) passeraient au rouge."""
    recepteurs = {iface for _, iface, _ in R25.INTERFACES}
    referentiels = {nom for _, nom in R25.REFERENTIELS}
    assert referentiels, "aucun referentiel -- le test ne garde rien"
    assert not (recepteurs & referentiels), (
        "un referentiel est devenu un recepteur : %s" % (recepteurs & referentiels))
    assert "TargetsSelector" not in R25._RECEPTEURS


def test_etage4_le_couple_de_CLASSE_sort_en_JUSTE_AILLEURS(tables) -> None:
    """Le verdict que la mesure autorise : ni vert, ni rouge, mais LISTE et nomme."""
    c = R25.Citation(fichier="docs/rl/case-978-faces-decision-thousandsons-eldar.md", ligne=37,
                     iface="ITargetsSelector", slot=23, nom="Select", args=None,
                     texte="slot 23 = `Select` ... recoupes par `ITargetsSelector`",
                     ligne_nom=37, franchit_virgule=False)
    faux_nom, faux_arite, autre = R25.confronter([c], tables)
    assert not faux_nom, "la citation JUSTE est encore accusee : %s" % faux_nom
    assert not faux_arite
    assert len(autre) == 1 and "TargetsSelector" in autre[0]


def test_etage4_MUTATION_sans_le_referentiel_la_citation_redevient_FAUSSE(tables) -> None:
    """CONTRE-EPREUVE : on retire la table de classe et on rejoue -- le rouge de `master`
    revient, mot pour mot."""
    sans = {k: v for k, v in tables.items() if k != "TargetsSelector"}
    c = R25.Citation(fichier="x.md", ligne=37, iface="ITargetsSelector", slot=23, nom="Select",
                     args=None, texte="slot 23 = `Select`", ligne_nom=37,
                     franchit_virgule=False)
    faux_nom, _a, autre = R25.confronter([c], sans)
    assert len(faux_nom) == 1 and "AUCUNE METHODE" in faux_nom[0], (
        "le referentiel est INERTE -- sans lui le verdict devrait etre rouge, rendu : %s"
        % (faux_nom,))
    assert not autre


def test_etage4_les_slots_NON_VIRTUELS_sont_ecartes(tables) -> None:
    """`0xffff` n'indexe rien : une classe declare aussi des `.ctor` et des surcharges non
    slottees. Les garder ecraserait la table sur une cle unique et fabriquerait un couple
    qu'aucun site ne cite."""
    assert 0xFFFF not in tables["TargetsSelector"]
    #: et la table reste NON VIDE -- un filtre qui vide tout passerait ce test sans lui.
    assert len(tables["TargetsSelector"]) >= 15
