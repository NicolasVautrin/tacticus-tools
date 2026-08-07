"""#419-r6-r1 -- GARDE : le selecteur de cible ne fait PAS entrer `MightCrit` dans son classement.

CE QUE CE FICHIER FIGE, ET POURQUOI IL EXISTE
----------------------------------------------
#R34 a porte `MightCrit` sur la chaine PLAYBOOK et a NOMME en residu le seul producteur restant :
`runner/operations/damage_utility._target_utility`, qui fabrique un `pred` SANS la cle. Le residu
disait << non porte faute de pouvoir le VALIDER >>, et c'etait exact : tant que le canal crit etait
muet (`CouldCrit` faux sur 106/106 unites normalisees, #419-r5), la cle absente et la cle a `False`
sont le MEME dict -- aucune mesure ne pouvait les separer.

La bascule du defaut a << equiper >> (#419-r6) ouvre `CouldCrit` sur 98/106. Le port a donc ete
ECRIT, puis CONFRONTE -- et le live l'a REFUTE. Sans ce fichier, la prochaine lecture de #R34
re-ouvrirait le meme residu et re-ecrirait le meme port faux : le residu ne dit pas que la question
a ete tranchee.

L'ORACLE, ET CE QUI LE REND LISIBLE
------------------------------------
Doombolt (1102, `thousAhriman`) : `SortUnitsByDamageUtility` gouverne l'ORDRE des cibles, et la
repartition `N = 3` coups sur 4 cibles vaut `[1, 1, 1, 0]` -- donc la cible a ZERO coup dit le
DERNIER du tri, sans ambiguite et sans hook nouveau.

Trois precautions, chacune payee par une mesure fausse (cf. `probe_419r6r1_face_decision.py`) :
  * TROIS roles d'utilite distincts. A deux roles, deux cibles ont la MEME utilite et le live
    mesure alors le TIE-BREAK (stabilite de l'`OrderBy` natif sur l'ordre source), que le port
    approxime par `id` croissant -- il rendait un ordre qu'AUCUNE des deux valeurs du flag ne
    produit.
  * `FixedArmor = Armor = 0` sur les cibles : sinon un `MightBeKill` perdu par l'armure ferait
    basculer le classement pour une raison etrangere au flag.
  * un CONTREFACTUEL joue sur le MEME etat et le MEME `state.rng` : sans lui, << c'est bit-exact >>
    ne dirait pas si le flag CHANGE quelque chose.

ASCII only (cp1252). Le montage vit dans le probe ; ce fichier n'en tire que les verdicts.
"""
from __future__ import annotations

import pytest

import probe_419r6r1_face_decision as P
from engine.runner.operations.damage_utility import _target_utility, damage_utility_weights


# --------------------------------------------------------------------------------------------
# etage 1 -- OFFLINE : le contrat du dict, et la NON-VACUITE du contrefactuel
# --------------------------------------------------------------------------------------------

class _H:
    def __init__(self, hp, mx):
        from engine.runner.components import HealthComponent
        self._c = HealthComponent(hp=hp, hp_max=mx)

    def get_component(self, cls):
        from engine.runner.components import HealthComponent
        return self._c if cls is HealthComponent else None


class _S:
    def __init__(self, d):
        self._e = {int(k): _H(*v) for k, v in d.items()}

    def get_entity(self, eid):
        return self._e.get(int(eid))


def test_le_flag_change_bien_l_utilite_offline():
    """CONTRE-EPREUVE de la garde elle-meme : dans la fenetre << letal SOUS le seuil >>, les deux
    valeurs du flag donnent des utilites DIFFERENTES.

    Sans cet etage, le test live pourrait passer parce que le flag n'a AUCUN effet nulle part --
    un vert vacueux. On exige ici que l'ecart existe, et qu'il vaille exactement le poids
    `PossibleOverkill` du BC (jamais un litteral : il est LU des poids)."""
    d = 1000
    st = _S({1: (d, d)})                       # hp == d -> letal, sur-degat 0 % -> SOUS le seuil
    wt = damage_utility_weights()
    u_sans = _target_utility(st, 1, d, d, wt, False)
    u_avec = _target_utility(st, 1, d, d, wt, True)
    attendu = wt.overkill(definite=False)      # PossibleOverkill, LU du BC
    assert attendu > 0, "PossibleOverkill nul dans ce BC : l'etage ne discriminerait rien"
    assert abs((u_avec - u_sans) - attendu) < 1e-6, (
        "le flag doit valoir exactement PossibleOverkill (%s), ecart mesure %s"
        % (attendu, u_avec - u_sans))


def test_les_entrees_publiques_ne_posent_pas_le_flag():
    """Le contrat FIGE : `sort_units_by_damage_utility` / `first_by_damage_utility` classent comme
    si `MightCrit` etait faux -- c'est ce que le live impose (etage 2). Un futur portage qui
    rebrancherait le flag ferait rougir ICI, avant meme de couter un runner."""
    from engine.runner.operations.damage_utility import (first_by_damage_utility,
                                                         sort_units_by_damage_utility)
    d = 1000
    # A dans la fenetre (le flag le ferait monter de PossibleOverkill) ; B au-dessus de A sans le
    # flag et en dessous avec -- donc l'argmax DEPEND du flag.
    st = _S({1: (d, d), 2: (d // 3, 1690)})
    wt = damage_utility_weights()
    u1_sans = _target_utility(st, 1, d, d, wt, False)
    u1_avec = _target_utility(st, 1, d, d, wt, True)
    u2 = _target_utility(st, 2, d, d, wt, False)
    if not (u1_sans < u2 < u1_avec):
        pytest.skip("regime non discriminant a ce d/maxHealth (u1=%s/%s u2=%s) -- l'etage LIVE, "
                    "lui, DERIVE son regime du runner" % (u1_sans, u1_avec, u2))
    assert first_by_damage_utility(st, [1, 2], d, d) == 2, (
        "les entrees publiques doivent classer SANS le flag (#419-r6-r1 : le natif ne le lit pas)")
    assert list(sort_units_by_damage_utility(st, [1, 2], d, d)) == [2, 1]


# --------------------------------------------------------------------------------------------
# etage 2 -- LIVE : le natif tranche
# --------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mesure_live():
    # #494-r1-r1 : la RECONNAISSANCE rend aussi l'ETAT. Depuis que la cle de tri passe par la
    # prediction complete par cible, un balayage sur stub a PV seuls reglerait le regime sur le
    # chemin DEGRADE -- et le montage cesserait d'etre discriminant en live (mesure du 2026-08-07 :
    # `montage_discriminant = False`, un ROUGE de MONTAGE qui ne juge pas le port).
    reco = P._reco_du_runner(
        "necroOverlord,necroWarden,eldarRanger,orksNob", "defaut", "31337", "MC1_67")
    if reco is None:
        pytest.fail("MONTAGE : reconnaissance du degat du noeud de tri impossible (build KO). "
                    "Ce n'est pas un verdict sur le port -- le harnais n'a pas monte le cas.")
    dmg = reco["d"]
    reg = P.etage_regime(dmg, verbose=False, reco=reco)
    if not reg.get("ok"):
        pytest.fail("MONTAGE : aucun regime discriminant a d=%s -- le cas ne separerait pas les "
                    "deux valeurs du flag, donc il ne prouverait rien." % dmg)
    r = P.etage_live(reg, "necroOverlord,necroWarden,eldarRanger,orksNob", "defaut",
                     "31337", "MC1_67", verbose=False)
    if r.get("error"):
        pytest.fail("MONTAGE : %s" % r["error"])
    return r


def test_le_natif_ne_lit_pas_might_crit_dans_le_selecteur_live(mesure_live):
    """LE VERDICT. Le port de PRODUCTION (sans le flag) est bit-exact avec le live ; le
    CONTREFACTUEL (avec le flag) diverge. Les deux ordres different, donc le montage separe bien
    les deux hypotheses -- un accord ou les deux cotes rendent la meme chose ne prouverait rien."""
    r = mesure_live
    assert r["montage_discriminant"], (
        "montage NON discriminant : les deux valeurs du flag rendent le meme ordre (%s), donc "
        "l'accord avec le live ne dit rien. PV=%s dmg_tri=%s"
        % (r["ordre_production"], r["pv"], r["dmg_tri"]))
    assert r["might_crit_owner"], (
        "`CouldCrit(owner)` FAUX : on serait dans le regime DEGENERE d'avant #419-r6, ou la "
        "question ne peut pas etre posee. stats=%s" % r["oracle_natif"])
    assert r["exact_production"], (
        "le port de PRODUCTION diverge du live -- live=%s production=%s"
        % (r["live"], r["off_production"]))
    assert not r["exact_contrefactuel"], (
        "le CONTREFACTUEL colle AUSSI au live : le montage ne separe plus les deux hypotheses "
        "(re-crafter le regime). live=%s contrefactuel=%s" % (r["live"], r["off_contrefactuel"]))


def test_le_temoin_referme_le_canal_live():
    """La CAUSALITE : le meme montage en `--no-bis-items` doit rendre les deux ordres IDENTIQUES.

    C'est ce bras qui etablit que la bascule #419-r6 est bien ce qui a rendu la question POSABLE.
    S'il echoue, c'est qu'une autre voie equipe desormais les unites -- et alors le temoin de
    toute cette famille de mesures est perdu, ce qu'il faut savoir tout de suite."""
    reco = P._reco_du_runner(
        "necroOverlord,necroWarden,eldarRanger,orksNob", "0", "31337", "MC1_67")
    if reco is None:
        pytest.fail("MONTAGE : reconnaissance impossible en regime temoin (build KO).")
    dmg = reco["d"]
    reg = P.etage_regime(dmg, verbose=False, reco=reco)
    if not reg.get("ok"):
        pytest.fail("MONTAGE : aucun regime discriminant a d=%s (temoin)." % dmg)
    r = P.etage_live(reg, "necroOverlord,necroWarden,eldarRanger,orksNob", "0",
                     "31337", "MC1_67", verbose=False)
    if r.get("error"):
        pytest.fail("MONTAGE : %s" % r["error"])
    assert not r["might_crit_owner"], (
        "`--no-bis-items` laisse `CouldCrit(owner)` VRAI (stats=%s) : le temoin du regime d'avant "
        "#419-r5 ne restitue plus le canal ferme." % r["oracle_natif"])
    assert not r["montage_discriminant"], (
        "canal ferme et pourtant les deux ordres different (%s vs %s) : le contrefactuel ne "
        "s'appuie donc pas sur `CouldCrit`."
        % (r["ordre_production"], r["ordre_contrefactuel"]))
    assert r["exact_production"], (
        "port divergent du live meme en regime temoin -- l'ecart n'a alors rien a voir avec le "
        "crit. live=%s production=%s" % (r["live"], r["off_production"]))
