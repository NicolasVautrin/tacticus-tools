"""#1041 -- garde OFFLINE : le recenseur de couverture d'item DERIVE ses registres, et il ne
credite jamais un montage qui ne s'execute pas.

DEUX VICES, EN SENS OPPOSES. C'est ce qui rend ce cliquet a deux faces, et c'est mesure :

  * SOUS-comptage -- `_passive_covered` testait une LISTE BLANCHE de cinq registres. Une liste
    blanche ne peut pas montrer le registre qu'elle a oublie. Bascules MESUREES au 2026-08-14 :
    `PhoenixGem` (`EFFECT_TRIGGERS`) et `HarlequinsPanoply` (`CUSTOM_TRIGGERED_ABILITIES`).
    Chacune des cinq entrees de la liste avait deja ete payee par un faux manquant du meme genre
    (`DawnBlade`, `FireOfAbsolution`, `Boltstorm`, `MartialKatah`) -- le gisement se rouvrait a
    chaque registre neuf.
  * SUR-comptage -- une entree d'`ABILITY_INIT_OWNER_EFFECTS` creditait l'item MEME QUAND l'effet
    pose n'a AUCUNE classe dans `EFFECT_CLASSES` : montage DECLARE, rien ne s'execute. Bascules
    MESUREES : les 4 mythiques `BlightedLand`, `CabalOfSorcerers`, `GuardianConstruct`,
    `MoreGitzOverEre`.

⚠ NE CORRIGER QUE LE PREMIER SENS DEGRADE LE CHIFFRE : on ferait basculer en << portee >> des
entrees dont une face manque. Les deux etages [3] et [4] sont donc aussi LOAD-BEARING que [1]/[2].

⚠ **LE GATE DU SECOND VICE A LUI-MEME DEUX CRANS DEPUIS #1024-r5** -- et le premier seul RE-OUVRAIT
le sur-comptage, dans l'autre sens : il comptait PARTIEL un montage qui n'a RIEN a porter.
<< la cible n'a aucune classe dans `EFFECT_CLASSES` >> ne signifie pas << rien ne s'execute >> ; il
faut encore que le NATIF ait une classe. Mesure sur `rnca9r7q6c` : `CabalOfSorcerers_ExtraDamagePct`
et `GuardianConstruct_ExtraDamagePct` ont chacun une classe native a **4 corps propres** (dette
REELLE), quand l'effet 1462 `TheArdentBlade` n'a **AUCUN** symbole `.Entities.Effects.*` du build --
c'est un JETON relu par un `HasEffect`, dont le `BaseEffect` generique est le mirror FIDELE.

⚠ CE FICHIER NE FIGE PAS LA LISTE COURANTE -- il DERIVE. L'etage [2] INJECTE un conteneur neuf
dans le perimetre et exige qu'il sorte MUET : c'est le seul cran qui garde le recenseur contre le
registre de DEMAIN, et il est vu ROUGE par cette mutation meme.

Usage : depuis `scripts/python/`
    python -m pytest tests/test_1041_kit_item_voies_offline.py -q
"""
from __future__ import annotations

import ast
import os
import sys

import pytest

_PYROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        # le foyer garde, et ses DEUX consommateurs
        "scripts/python/kit_item_voies.py",
        # le SUBSTRAT du second cran du gate (#1024-r5) : sans la table de symboles du build,
        # `classe_d_effet_native` rend `None` et le gate degrade entierement vers PARTIEL.
        "scripts/python/build_pin.py", "scripts/python/symbols_layout.py",
        "scripts/python/il2cpp_provenance.py",
        "scripts/python/audit_kit_coverage.py",
        "scripts/python/audit_npc_registry.py",
        # TOUT le perimetre partitionne : un conteneur neuf y naissant doit faire rejouer ce
        # fichier, sans quoi le MUET qu'il produirait ne serait vu de personne. C'est large a
        # dessein -- un declencheur trop etroit est un FAUX VERT.
        "scripts/python/engine/runner/",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/services/",
        # les tables d'enums : l'enum de la clef d'une voie s'y resout (etage [5])
        "scripts/python/enum_maps.py",
        "scripts/python/unit_map.py", "scripts/python/gameconfig.py",
        "data/i2_en.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : garde les DEUX sens du recensement de couverture d'item -- qu'aucun "
              "registre du perimetre n'echappe au recenseur (etages [1]/[2], par MUTATION), et "
              "qu'une entree creditee le soit sur une voie dont le GATE passe (etages [3]/[4]). "
              "Lit le gameconfig du build (kits, voies d'attribution) -> `build: True`.",
}

import audit_kit_coverage as AKC          # noqa: E402
import kit_item_voies as KIV              # noqa: E402


# ------------------------------------------------------------------ [1] la partition est TOTALE
def test_la_partition_du_perimetre_est_exhaustive_et_sans_muet():
    """Tout conteneur du perimetre sort dans EXACTEMENT une classe, et aucun n'est MUET.

    C'est l'invariant qui remplace la liste blanche : un registre neuf ne peut pas etre TU, il
    peut seulement etre inscrit (VOIES), ecarte (avec sa raison), ou rougir ici."""
    p = KIV.partition()
    total = sum(len(p[k]) for k in ("inscrits", "ecartes", "muets", "hors_sujet", "inertes"))
    assert total == len(KIV.conteneurs_du_perimetre()), (
        "la partition PERD des conteneurs : %d classes pour %d visites -- une classe manque, "
        "donc quelque chose sort du recensement sans etiquette"
        % (total, len(KIV.conteneurs_du_perimetre())))
    assert not p["muets"], (
        "CONTENEUR MUET dans le perimetre de couverture d'item : %s. Il designe des items de kit "
        "et n'est NI inscrit dans `kit_item_voies.VOIES` NI ecarte avec sa raison dans `ECARTES`. "
        "C'est exactement le regime qui a fait sortir `PhoenixGem` en << non portee >> alors "
        "qu'elle est portee. Inscris-le ou ecarte-le -- ne le tais pas."
        % ", ".join("%s.%s" % (m, a) for m, a, _n, _t in p["muets"]))
    assert not p["fantomes"], (
        "VOIE FANTOME : %s est declaree dans `kit_item_voies` et introuvable dans le perimetre. "
        "Un registre supprime doit sortir de la declaration, sinon la partition ment sur ce "
        "qu'elle couvre." % ", ".join("%s.%s" % c for c in p["fantomes"]))


# ------------------------------------------------------------------ [2] MUTATION : le cran DERIVE
def test_un_conteneur_NEUF_du_perimetre_sort_MUET(monkeypatch):
    """LE cran anti-liste-blanche, vu ROUGE par la mutation qu'il decrit.

    On injecte dans un module DU PERIMETRE un conteneur majuscule dont une clef designe un item de
    kit reel, sans l'inscrire nulle part. S'il ne sortait pas MUET, le recenseur serait revenu a
    une liste blanche -- il ne verrait que ce qu'on a pense a lui nommer."""
    import engine.runner.abilities.handler as H
    items = KIV.items_de_kit()
    temoin = sorted(items)[0]
    monkeypatch.setattr(H, "REGISTRE_NEUF_DE_TEST_1041", {temoin: ["classe"]}, raising=False)
    monkeypatch.setattr(
        KIV, "conteneurs_du_perimetre",
        lambda: list(_CONTENEURS_REELS) + [("engine.runner.abilities.handler",
                                            "REGISTRE_NEUF_DE_TEST_1041")])
    p = KIV.partition()
    assert any(a == "REGISTRE_NEUF_DE_TEST_1041" for _m, a, _n, _t in p["muets"]), (
        "un conteneur NEUF qui designe un item de kit n'est PAS sorti MUET -- le recenseur ne "
        "derive plus, il enumere, et le prochain registre sera tu comme `EFFECT_TRIGGERS` l'a ete")


_CONTENEURS_REELS = KIV.conteneurs_du_perimetre()


# ------------------------------------------------------------------ [3] SOUS-comptage : les deux
def test_les_deux_bascules_de_sous_comptage_sont_vues():
    """Les deux faux manquants MESURES, et les DEUX registres a clef entiere que la liste blanche
    ne lisait pas -- de clefs d'enums DIFFERENTS (`EffectType` / `TriggeredAbilityType`).

    ⚠ L'appariement voie<->cas n'est PAS une attribution de cause : `HarlequinsPanoply` est monte
    par les DEUX voies a la fois (`CUSTOM_TRIGGERED_ABILITIES` ET `EFFECT_TRIGGERS`), donc
    `EFFECT_TRIGGERS` suffit a expliquer les deux bascules. Ce que cet etage garde, c'est que
    CHAQUE registre reste lu -- pas que chacun soit necessaire a son cas."""
    for nom, voie_attendue in (("PhoenixGem", "EFFECT_TRIGGERS"),
                               ("HarlequinsPanoply", "CUSTOM_TRIGGERED_ABILITIES")):
        etat, detail = KIV.etat(nom)
        assert etat == KIV.PORTE, (
            "REGRESSION #1041 : `%s` redevient un faux MANQUANT (etat=%s). La voie `%s` n'est "
            "plus lue par le foyer, ou l'entree a disparu du registre." % (nom, etat, voie_attendue))
        assert voie_attendue in detail, (
            "`%s` est vu porte, mais PAS par `%s` (detail=%s) -- l'appariement a change de voie, "
            "donc le cas nomme ne garde plus ce qu'il pretend garder." % (nom, voie_attendue, detail))


def test_l_audit_de_kit_ne_reimporte_AUCUN_registre_de_couverture():
    """Le cran ANTI-RECIDIVE, et il est structurel : re-importer un registre dans l'auditeur, c'est
    re-ouvrir la liste blanche un cran plus loin. L'auditeur doit passer par le FOYER."""
    src = os.path.join(_PYROOT, "audit_kit_coverage.py")
    with open(src, encoding="utf-8") as f:
        arbre = ast.parse(f.read())
    interdits = {"ABILITY_TRIGGERS", "RELIC_ABILITY_TRIGGERS", "EFFECT_TRIGGERS",
                 "CUSTOM_TRIGGERED_ABILITIES", "ABILITY_INIT_OWNER_EFFECTS",
                 "ABILITY_OWNER_EFFECTS", "CUSTOM_NORMAL_ATTACK_BY_PASSIVE",
                 "IMPERATIVE_ABILITY_VECTORS", "EFFECT_CLASSES", "TRAIT_TRIGGERS",
                 "TRAIT_OWNER_EFFECTS", "TRAIT_DERIVED_ABILITIES"}
    vus = {a.name for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom)
           for a in n.names if a.name in interdits}
    assert not vus, (
        "`audit_kit_coverage` re-importe %s. C'est la LISTE BLANCHE qui repousse : ces registres "
        "se lisent par `kit_item_voies`, dont la partition rougit sur celui qu'on oublie. "
        "L'importer ici le rend invisible au foyer." % ", ".join(sorted(vus)))


# ------------------------------------------------------------------ [4] SUR-comptage : le GATE
def _poses_sans_classe_portee():
    """Les entrees d'`ABILITY_INIT_OWNER_EFFECTS` dont AUCUNE cible n'est dans `EFFECT_CLASSES`,
    VENTILEES par le second cran du gate (`kit_item_voies.classe_d_effet_native`) :

        (dette, jeton) -- `dette` = au moins une cible a une classe NATIVE que le port n'execute
                          pas ; `jeton` = AUCUNE cible n'en a, cote natif non plus.

    DERIVE des registres, jamais recopie."""
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
    items = KIV.items_de_kit()
    dette, jeton = set(), set()
    for k, effets in ABILITY_INIT_OWNER_EFFECTS.items():
        cibles = [e for e in effets if isinstance(e, str)]
        if k not in items or not cibles or any(e in EFFECT_CLASSES for e in cibles):
            continue
        (jeton if all(KIV.classe_d_effet_native(e) is False for e in cibles) else dette).add(k)
    return dette, jeton


def test_une_pose_dont_le_NATIF_a_une_classe_non_portee_est_PARTIELLE_jamais_portee():
    """L'axe INVERSE. Un montage DECLARE dont la cible a une classe NATIVE que le port n'execute pas
    ne fait RIEN de ce que le natif fait : le crediter << porte >> fait RENONCER a du travail reel.

    ⚠ **LE CRITERE A DEUX CRANS DEPUIS #1024-r5, ET N'EN LIRE QU'UN SUR-COMPTE LE TRAVAIL.**
    << pas de classe dans `EFFECT_CLASSES` >> ne veut PAS dire << rien ne s'execute >> : encore
    faut-il que le NATIF ait quelque chose a executer. Mesure : `CabalOfSorcerers_ExtraDamagePct` et
    `GuardianConstruct_ExtraDamagePct` ont chacun une classe native a 4 corps propres (dette REELLE),
    la ou l'effet 1462 `TheArdentBlade` n'a **AUCUN** symbole `.Entities.Effects.*` dans tout le
    build -- c'est un JETON relu par un `HasEffect`, et le `BaseEffect` generique en est le mirror
    FIDELE. Le compter PARTIEL envoyait un agent porter une classe qui n'existe pas."""
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS
    dette, _jeton = _poses_sans_classe_portee()
    assert dette, (
        "premisse VIDE : plus aucune entree d'`ABILITY_INIT_OWNER_EFFECTS` ne pose un effet dont le "
        "NATIF a une classe que le port n'execute pas. Si elles ont ete portees, tant mieux -- mais "
        "alors ce test ne mesure plus rien et doit etre re-ancre, pas laisse vert a vide.")
    for nom in sorted(dette):
        etat, detail = KIV.etat(nom)
        assert etat == KIV.PARTIEL, (
            "`%s` pose l'effet %s, dont le NATIF porte une classe d'effet que le port n'execute "
            "pas. Il sort pourtant `%s`. Le GATE `%s` ne mord plus : l'audit va compter porte un "
            "montage dont une face manque."
            % (nom, ABILITY_INIT_OWNER_EFFECTS[nom], etat, KIV.GATE_EFFET_CLASSE))
        assert KIV.GATE_EFFET_CLASSE in detail


def test_une_pose_dont_le_NATIF_n_a_AUCUNE_classe_est_PORTEE_jamais_partielle():
    """LE SECOND CRAN, garde dans son propre sens -- celui qui RETIRE du travail, donc le plus
    dangereux des deux. Un effet-JETON (aucune classe native) est PORTE : le `BaseEffect` generique
    que rend `EffectFactory.create` (`registry.get(name, BaseEffect)`) porte le bon `effect_type` et
    le bon flag `active`, ce qui est exactement ce que le natif a."""
    _dette, jeton = _poses_sans_classe_portee()
    assert jeton, (
        "premisse VIDE : plus aucune pose d'owner-effect n'est un JETON sans classe native. Ce test "
        "ne mesure alors plus le second cran du gate -- le re-ancrer, pas le laisser vert a vide.")
    for nom in sorted(jeton):
        etat, detail = KIV.etat(nom)
        assert etat != KIV.PARTIEL, (
            "`%s` est compte PARTIEL alors que le NATIF n'a AUCUNE classe d'effet pour sa cible : "
            "le second cran du gate ne mord plus, et l'audit va faire porter une classe qui "
            "n'existe pas (detail=%s)." % (nom, detail))


def test_MUTATION_le_second_cran_est_LOAD_BEARING(monkeypatch):
    """Contre-epreuve du cran neuf : si `classe_d_effet_native` rendait `True` partout (ou `None` =
    NON MESURE), les JETONS retomberaient PARTIEL. Sans cet etage, l'etage precedent pourrait etre
    vert pour une raison etrangere au cran -- et son mode NON MESURE, jamais exerce."""
    _dette, jeton = _poses_sans_classe_portee()
    assert jeton, "premisse VIDE (cf. l'etage precedent)"
    for verdict, libelle in ((True, "classe native PARTOUT"), (None, "NON MESURE")):
        monkeypatch.setattr(KIV, "classe_d_effet_native", lambda _e, _v=verdict: _v)
        mute = KIV.voies_par_item()
        for nom in sorted(jeton):
            assert KIV.etat(nom, mute)[0] == KIV.PARTIEL, (
                "sous la mutation << %s >>, `%s` ne redevient PAS PARTIEL : le second cran du gate "
                "n'est pas ce qui le fait sortir PORTE, donc l'etage qui le garde ne mesure rien. "
                "⚠ Le mode NON MESURE doit DEGRADER VERS LE TRAVAIL, jamais vers le silence."
                % (libelle, nom))


def test_la_mesure_des_classes_d_effet_natives_n_est_pas_DEGENERE():
    """La mesure qui porte le second cran doit etre NON VIDE et couvrir les DEUX conventions de
    nommage natives. C'est le cran qui a manque a la premiere ecriture : ne lire que `<X>Effect`
    rendait `False` sur `TerminatorArmour_ReduceDmg_Effect` -- un faux `False` fait PASSER le gate,
    donc SUR-compte en PORTE, exactement le vice que #1041 avait ouvert pour fermer."""
    natives = KIV._classes_d_effet_natives()
    assert natives, (
        "`_classes_d_effet_natives` rend %r : la table de symboles n'est pas lue. Le gate degrade "
        "alors ENTIEREMENT vers PARTIEL (sens sur, mais le second cran ne mesure plus rien)."
        % (natives,))
    assert len(natives) > 100, (
        "seulement %d classes d'effet natives mesurees -- le detecteur a perdu une convention de "
        "nommage ou un namespace." % len(natives))
    # les DEUX orthographes doivent etre representees, sans quoi le detecteur en a perdu une.
    assert "CabalOfSorcerers_ExtraDamagePct" in natives, "convention `<X>Effect` perdue"
    assert "TerminatorArmour_ReduceDmg" in natives, (
        "convention `<X>_Effect` (avec souligne) perdue -- c'est le faux `False` de #1024-r5")


def test_l_appariement_PAR_PREFIXE_est_exerce_et_garde():
    """LE CRAN QUE LA MATRICE DE MUTATION A TROUVE NON GARDE, et il fallait un temoin PROPRE.

    ⚠ Mesure du 2026-08-14 : remplacer l'appariement a deux sens de `classe_d_effet_native` par une
    EGALITE STRICTE ne faisait rougir **AUCUN** des quatorze autres etages -- parce qu'aucun item
    DANS LA PORTEE DU GATE n'en depend AUJOURD'HUI (`BlightedLand`, qui en dependait, a ete porte
    depuis et en est donc sorti). Une garde qu'on ne voit pas tomber n'est pas une garde ; l'etage
    ci-dessous la rend visible sur une propriete du BUILD, independante de l'etat du port.

    LE FAIT GARDE : le natif nomme parfois sa classe d'apres l'ABILITY et non d'apres l'`EffectType`
    -- `IdunBattle.Entities.Effects.Loki.BlightedLandEffect` porte l'effet
    `BlightedLand_ExtraDamagePct`. Un appariement par egalite y rendrait `False`, c'est-a-dire
    ferait PASSER le gate sur un item a dette REELLE."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    natives = KIV._classes_d_effet_natives()
    assert natives, "mesure absente (cf. l'etage precedent)"
    # Les effets que SEUL l'appariement par prefixe rattache a une classe native. DERIVE, et son
    # propre non-vide est assertionne : un ensemble vide passerait pour vert sans rien mesurer.
    par_prefixe = sorted(e for e in EFFECT_CLASSES
                         if e not in natives and KIV.classe_d_effet_native(e) is True)
    assert par_prefixe, (
        "premisse VIDE : plus AUCUN effet ne se rattache a sa classe native par PREFIXE. Le "
        "second sens de `classe_d_effet_native` ne mesure alors plus rien -- le re-ancrer sur le "
        "nouveau gisement, pas le laisser vert a vide.")
    assert KIV.classe_d_effet_native("BlightedLand_ExtraDamagePct") is True, (
        "`BlightedLand_ExtraDamagePct` n'est plus rattache a `BlightedLandEffect` : l'appariement "
        "est retombe sur l'EGALITE, donc un faux `False` -- le gate PASSERA sur un item a dette "
        "reelle. C'est le SUR-comptage que #1041 avait ouvert pour fermer.")


# ------------------------------------------------------------------ [5] l'ENUM de la clef est LU
def test_l_enum_de_la_clef_est_LU_et_les_faux_positifs_ordinaux_ne_passent_PAS():
    """Le partage d'ordinaux, garde comme un fait EXECUTABLE et **DERIVE**.

    ⚠ CE TEST S'EST PERIME UNE FOIS, ET C'EST LA LECON. Il citait deux couples EN DUR
    (`1451` -> `WisdomOfTheAncients`, `1508` -> `MastersOfManoeuvre`) en exigeant qu'aucun ne soit
    PORTE. Un autre agent a porte `MastersOfManoeuvre` pour de vrai pendant la tranche : le temoin
    est devenu faux, et le test rouge pour une raison qui n'etait PAS le vice garde. Une
    contre-epreuve qui nomme ses temoins se perime avec eux.

    La propriete VRAIE, elle, ne se perime pas, et elle est LOCALE A L'ORDINAL : **l'item qu'un
    ordinal apparie sous la clef DECLAREE de sa voie n'est jamais celui qu'un AUTRE enum lui
    donne**. On la derive de la table entiere. Se placer au niveau de la VOIE serait trop fort :
    un item peut etre credite par `EFFECT_TRIGGERS` via SON PROPRE ordinal tout en etant, par
    ailleurs, le nom qu'un ordinal VOISIN porte dans un autre enum -- les deux faits coexistent
    sans qu'aucun soit une faute."""
    import enum_maps as EM
    tables = {"ActiveAbilityType": EM.ACTIVE_ABILITY_TYPE,
              "TriggeredAbilityType": EM.PASSIVE_ABILITY_TYPE,
              "EffectType": EM.EFFECT_TYPE}
    items = KIV.items_de_kit()
    par_item = KIV.voies_par_item()
    couples = []          # (voie, ordinal, nom sous la clef declaree, nom sous l'autre enum)
    for v in KIV.VOIES:
        if v.cle == KIV.CLE_NOM:
            continue
        for el in (KIV.elements(v.mod, v.attr) or []):
            if isinstance(el, bool) or not isinstance(el, int):
                continue
            declare = tables[v.cle].get(int(el))
            for lib, t in tables.items():
                if lib == v.cle:
                    continue
                autre = t.get(int(el))
                if autre and autre != declare and autre in items:
                    couples.append((v.attr, int(el), declare, autre))
    assert couples, (
        "premisse VIDE : plus aucun ordinal d'une voie a clef entiere n'est partage avec un autre "
        "enum sur un item de kit. Improbable (le CLAUDE.md en chiffre des centaines) -- si les "
        "enums ont ete renumerotes, re-ancrer ce test plutot que le laisser vert a vide.")
    # (a) L'APPARIEMENT passe par le nom de l'enum DECLARE, et par lui seul. Un item apparie doit
    #     donc DERIVER de ce nom (egalite, ou prefixe `<item>_`) -- jamais du nom qu'un autre enum
    #     donne au meme ordinal. NB : les deux peuvent CONVERGER sans faute (`EffectType[1111]` =
    #     `WireweaveNet_CounterAttack` s'apparie a l'item `WireweaveNet`, que `TriggeredAbilityType`
    #     nomme directement) -- ce qui compte est le CHEMIN, pas la coincidence d'arrivee.
    for attr, ordinal, declare, autre in couples:
        v = next(x for x in KIV.VOIES if x.attr == attr)
        nom = KIV.nom_designe(ordinal, v.cle, tables)
        assert nom == tables[v.cle].get(ordinal), (
            "la voie `%s` ne resout plus ses ordinaux dans `%s` : %d rend `%s`"
            % (attr, v.cle, ordinal, nom))
        apparie = KIV._item_de(nom or "", items)
        assert apparie is None or nom == apparie or nom.startswith(apparie + "_"), (
            "FAUX POSITIF ORDINAL : dans la voie `%s`, l'ordinal %d s'apparie a l'item `%s` sans "
            "DERIVER du nom `%s` que lui donne sa clef declaree `%s`. Le seul autre nom en lice "
            "est `%s`, celui d'un AUTRE enum -- la resolution a donc fui hors de sa clef."
            % (attr, ordinal, apparie, declare, v.cle, autre))
    # (b) Le vice garde doit rester ATTEIGNABLE : si la resolution NAIVE ne fabriquait plus aucune
    #     bascule que la resolution DECLAREE refuse, ce test ne mesurerait plus rien.
    faux = set()
    for attr, ordinal, _declare, autre in couples:
        v = next(x for x in KIV.VOIES if x.attr == attr)
        declare_item = KIV._item_de(tables[v.cle].get(ordinal) or "", items)
        if declare_item != autre:
            faux.add((attr, ordinal, autre))
    assert faux, (
        "premisse VIDE : la resolution NAIVE ne fabriquerait plus AUCUNE bascule que la resolution "
        "declaree refuse -- ce test ne garde donc plus rien. Re-ancrer plutot que laisser vert a "
        "vide (c'est exactement ce qui a fait passer sa version precedente pour verte).")


@pytest.mark.parametrize("attr", sorted({v.attr for v in KIV.VOIES if v.cle != KIV.CLE_NOM}))
def test_toute_voie_a_clef_entiere_declare_un_enum_connu(attr):
    """Une voie a clef entiere ne peut pas laisser son enum implicite : c'est la seule protection
    contre le partage d'ordinaux, et elle doit etre VERIFIABLE, pas promise en commentaire."""
    v = next(x for x in KIV.VOIES if x.attr == attr)
    assert v.cle in ("ActiveAbilityType", "TriggeredAbilityType", "EffectType"), (
        "la voie `%s` declare la clef `%s`, qui n'est pas un enum connu du foyer" % (attr, v.cle))


# ------------------------------------------------------------------ [6] l'auditeur CONSOMME bien
def test_l_audit_expose_le_tri_etat_et_ne_le_rabat_pas_sur_un_booleen():
    """Le tri-etat doit ARRIVER jusqu'au document. `_passive_covered` reste un booleen pour ses
    appelants historiques, mais il rend `False` sur un PARTIEL -- le rabattre sur `True` ferait
    RENONCER a la face manquante."""
    cond = AKC.collect_conditionnelles({})
    etats = {c["etat"] for c in cond}
    assert etats <= {KIV.PORTE, KIV.PARTIEL, KIV.ABSENT}, "etat inconnu rendu par l'audit : %s" % etats
    partiels = [c["name"] for c in cond if c["etat"] == KIV.PARTIEL]
    assert partiels, (
        "premisse VIDE : plus aucune voie conditionnelle n'est PARTIELLE. Re-ancrer ce test "
        "plutot que le laisser vert a vide.")
    for nom in partiels:
        assert not AKC._passive_covered(nom), (
            "`%s` est PARTIEL et `_passive_covered` rend True : le sur-comptage est de retour, "
            "l'audit va declarer portee une entree dont une face manque." % nom)
