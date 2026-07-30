#!/usr/bin/env python
"""Cliquet #313 -- les mirrors `IntEnum` du MOTEUR restent en bijection avec `enums.tsv`.

POURQUOI UN CLIQUET, ET PAS SEULEMENT UNE CORRECTION
----------------------------------------------------
Le trou vient de se re-creuser une deuxieme fois. La MAJ `gqfc5mff6c` -> `rnca9r7q6c` a AJOUTE des
ids a `TriggeredAbilityType` et en a RETIRE d'autres ; #304 a du ajouter `ModifiedExoarmour`
(1529) a la main pour porter un passif, en laissant HUIT autres membres manquants et 107 membres
morts. Rien ne rougissait : le mirror n'etait garde par AUCUN test.

Et il ne l'etait pas par accident. DEUX cliquets voisins existent, et ni l'un ni l'autre ne couvre
ce cas -- verifie, pas suppose :

  * `test_enum_ordinal_ratchet_offline.py` (#283) confronte bien des mirrors Python, mais
    `probe_283_enum_ordinal_sweep.step_mirror` ne teste QUE `ref.get(membre) != valeur` sur les
    membres PRESENTS dans le mirror. Un membre que le port n'a pas ne peut pas diverger : il est
    invisible. Et son registre ne contient que quatre enums, dont aucun `*AbilityType`.
  * `test_enum_maps_ratchet_offline.py` (#275) fait bien les trois sens, mais sur `enum_maps.py`
    seulement. L'etape 4 de `probe_275_enum_maps_drift` range explicitement les mirrors
    `engine/entities/*_type.py` en "informatif, hors perimetre".

Les mirrors du moteur -- ceux que le code EXECUTABLE lit -- n'etaient donc gardes par personne.

CE QUE CE FICHIER VERIFIE, ET POURQUOI CHAQUE PARTIE COMPTE
------------------------------------------------------------
1. BIJECTION dans les DEUX sens sur les mirrors SOUS GARDE. Le sens "manquant" est celui qui a
   coute : il ne casse rien, il RETIRE en silence (`triggered_ability_ids` fait
   `__members__.get(nom)` puis `if m is not None`).
2. Le REGISTRE est EXHAUSTIF : toute classe `IntEnum`/`IntFlag` de `engine/` est soit apparie a un
   enum natif, soit justifiee HORS-MIRROR. C'est la partie qui empeche le trou de se re-creuser :
   sans elle, un mirror ajoute demain echapperait a la garde sans que rien ne le signale -- ce qui
   est EXACTEMENT ce qui est arrive a `TriggeredAbilityType`.
3. Les DETTES declarees sont au compte EXACT, controle dans les deux sens : le test rougit si la
   dette s'aggrave, et il rougit aussi si elle est resorbee -- la reponse etant alors de passer le
   mirror SOUS GARDE, pas de rafraichir le nombre. Un chiffre qu'on rafraichit n'est pas un
   cliquet, c'est un journal.
4. Le DETECTEUR mord. Un cliquet qui ne detecte rien passerait au vert sur un depot pourri : on
   lui soumet les trois formes de derive REELLEMENT observees (membre retire, membre ajoute,
   valeur REATTRIBUEE) plus les deux faux positifs qui ont failli le rendre inutilisable (l'alias
   de valeur, et le mirror qui reconventionne ses noms).
5. Les REFERENCES QUALIFIEES resolvent. C'est ce qui autorise a RETIRER un membre mort : #270
   avait etabli qu'une regeneration naive casse le port en supprimant un nom encore cite.

Offline pur : aucun runner, aucune session Frida. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"/"python"))

import probe_313_enum_mirror_bijection as P  # noqa: E402


# ------------------------------------------------------- 1. le cliquet : la bijection tient

def test_les_mirrors_sous_garde_sont_en_bijection_avec_le_build():
    """LE test. Les trois sens a la fois, sur chaque mirror sous garde.

    Le message d'echec nomme le REPARATEUR : #275 a etabli qu'un cliquet sans reparateur pousse a
    la correction a la main -- 476 lignes retranscrites, c'est-a-dire la transcription
    approximative qu'on cherche justement a eliminer."""
    build = P.current_build()
    ecarts = []
    for m in P.REGISTRE:
        if not m.garde:
            continue
        port = P.membres_mirror(m.rel, m.cls)
        assert port, "mirror %s introuvable dans %s" % (m.cls, m.rel)
        manquants, morts, renum = P.bijection(port, P.enum_natif(build, m.cle), m.strict)
        if manquants or morts or renum:
            ecarts.append(
                "  %s (%s) : MANQUANTS=%d MORTS=%d RENUMEROTES=%d\n"
                "      manquants : %s\n      morts : %s\n      renumerotes : %s"
                % (m.cls, m.rel, len(manquants), len(morts), len(renum),
                   [(v, n) for v, n in manquants[:6]] or "-",
                   [(v, n) for v, n in morts[:6]] or "-",
                   [(v, n, j) for v, n, j in renum[:6]] or "-"))
    assert not ecarts, (
        "mirror(s) desynchronise(s) du build %s :\n%s\n"
        "  MANQUANT = le jeu emet cet id, le port ne sait pas le nommer ->\n"
        "    `triggered_ability_ids()` le JETTE en silence (`if m is not None`).\n"
        "  MORT     = le port cite un id que le jeu n'emet plus -> code qui a l'air vivant.\n"
        "  Reparer      : python scripts/python/regen_enum_mirrors.py --mirror <Classe> --ecrire\n"
        "  Inventorier  : python scripts/python/probe_313_enum_mirror_bijection.py --porteurs\n"
        "  AVANT de retirer un membre mort, verifier qu'il n'est ni reference `<Classe>.<membre>`\n"
        "  dans du Python, ni nomme par le gameconfig (etapes 3 et 4 de la sonde) -- piege #270."
        % (build, "\n".join(ecarts)))


# ------------------------------ 2. le registre est exhaustif (LA partie anti-re-creusement)

def test_toute_classe_intenum_du_moteur_est_classee():
    """Sans ce test, le cliquet ne garde que ce qu'on a pense a y mettre.

    C'est exactement ainsi que `TriggeredAbilityType` a derive : personne n'avait DECIDE de ne pas
    le garder -- il n'etait dans aucune liste, et une absence ne se remarque pas."""
    trouves = P.intenums_du_moteur()
    orphelines = sorted(c for c in trouves
                        if c not in P.PAR_CLS and c not in P.HORS_MIRROR)
    assert not orphelines, (
        "classe(s) IntEnum sous engine/ ni appariee(s) ni justifiee(s) :\n%s\n"
        "  Chaque classe doit entrer dans `probe_313_enum_mirror_bijection` :\n"
        "    * REGISTRE   si elle recopie un enum natif (donner la cle EXACTE de enums.tsv --\n"
        "      la lire, ne pas la deviner : `UtilityType` vit dans `IdunBattle.Configuration`) ;\n"
        "    * HORS_MIRROR si elle n'en recopie aucun, AVEC sa raison."
        % "\n".join("  %-24s %s" % (c, trouves[c]) for c in orphelines))


def test_le_registre_ne_designe_aucun_mirror_disparu():
    """L'autre sens : une entree du registre dont le fichier ou la classe a disparu rendrait la
    garde muette sur cette classe, sans rien casser."""
    trouves = P.intenums_du_moteur()
    absents = [(m.cls, m.rel) for m in P.REGISTRE if m.cls not in trouves]
    assert not absents, ("entree(s) du registre introuvable(s) sous engine/ : %s\n"
                         "  Le mirror a ete deplace ou supprime : corriger le registre." % absents)


# -------------------------------------------- 3. les dettes declarees sont au compte EXACT

def test_les_dettes_declarees_sont_au_compte_exact():
    """Controle dans les DEUX sens -- s'aggrave ou se resorbe, le test rougit.

    Une dette qui se resorbe n'est pas un evenement neutre : c'est le moment ou le mirror doit
    passer SOUS GARDE. Si le test se contentait d'un `<=`, la resorption ne serait jamais
    remarquee et le mirror repartirait a la derive depuis un etat sain."""
    build = P.current_build()
    ecarts = []
    for m in P.REGISTRE:
        if m.garde:
            continue
        port = P.membres_mirror(m.rel, m.cls)
        manquants, morts, renum = P.bijection(port, P.enum_natif(build, m.cle), m.strict)
        compte = (len(manquants), len(morts), len(renum))
        if compte != m.dette:
            ecarts.append("  %s : mesure %s, dette declaree %s (%s)"
                          % (m.cls, compte, m.dette, m.raison))
    assert not ecarts, (
        "dette(s) declaree(s) hors compte :\n%s\n"
        "  Si la dette a AUGMENTE : un membre a ete ajoute/retire sans passer par\n"
        "    `regen_enum_mirrors.py` -- corriger le mirror, pas le chiffre.\n"
        "  Si elle a DIMINUE : la resorber jusqu'a (0, 0, 0) et passer le mirror SOUS GARDE\n"
        "    (`garde=True`), au lieu de rafraichir le nombre."%"\n".join(ecarts))


def test_les_deux_dettes_connues_sont_bien_celles_qu_on_croit():
    """Les nommer PAR MEMBRE, jamais par ordinal : c'est ce qui rend ce test survivant au
    prochain build. `EffectType` porte deux ids RENUMEROTES -- la forme la plus couteuse, celle
    qui resout et pointe ailleurs sans que rien ne proteste."""
    build = P.current_build()
    eff = P.PAR_CLS["EffectType"]
    port = P.membres_mirror(eff.rel, eff.cls)
    _, _, renum = P.bijection(port, P.enum_natif(build, eff.cle), eff.strict)
    noms_port = {n for _, n, _ in renum}
    assert noms_port == {"DA_Hero6_Passive_1", "DA_Hero6_Passive_2"}, (
        "les ids RENUMEROTES d'EffectType ont change : %s" % sorted(noms_port))
    attendus = {n for _, _, js in renum for n in js}
    assert attendus == {"SpecialIssueCombiMelta_AdditionalHits",
                        "SpecialIssueCombiMelta_ExtraDmg"}, sorted(attendus)


# ------------------------------- 4. le detecteur mord (sinon le cliquet ne prouve rien)

def test_detecte_un_membre_MANQUANT():
    """LE sens de #313 : le jeu emet un id que le port ne sait pas nommer. Il ne casse rien --
    c'est pour ca qu'il a survecu a deux MAJ."""
    manquants, morts, renum = P.bijection({0: {"A"}}, {0: {"A"}, 1543: {"PropheticSentinel"}})
    assert (manquants, morts, renum) == ([(1543, ["PropheticSentinel"])], [], [])


def test_detecte_un_membre_MORT():
    """Le sens qu'on oublie : le port cite un id que le jeu n'emet plus. Aucune erreur, jamais."""
    manquants, morts, renum = P.bijection({0: {"A"}, 1: {"RaiseSkeletons"}}, {0: {"A"}})
    assert (manquants, morts, renum) == ([], [(1, ["RaiseSkeletons"])], [])


def test_detecte_une_valeur_REATTRIBUEE():
    """Le pire cas : meme id, autre membre. Il resout, pointe ailleurs, rien ne proteste. C'est la
    forme exacte de `EffectType[1563]` (`DA_Hero6_Passive_1` la ou le jeu dit
    `SpecialIssueCombiMelta_AdditionalHits`)."""
    _, _, renum = P.bijection({1563: {"DA_Hero6_Passive_1"}},
                              {1563: {"SpecialIssueCombiMelta_AdditionalHits"}})
    assert renum == [(1563, "DA_Hero6_Passive_1", ["SpecialIssueCombiMelta_AdditionalHits"])]


def test_un_ALIAS_de_valeur_n_est_PAS_une_derive():
    """Anti-faux-positif MESURE : le jeu donne 9999 = {STRIPPED, testAssetBundles}, le port ne
    porte que `testAssetBundles`. Exiger l'EGALITE des ensembles ferait crier le cliquet sur les
    DEUX mirrors `*AbilityType` a chaque execution -- un cliquet qui crie toujours est un cliquet
    qu'on desarme."""
    assert P.bijection({9999: {"testAssetBundles"}},
                       {9999: {"STRIPPED", "testAssetBundles"}}) == ([], [], [])


def test_un_mirror_qui_RECONVENTIONNE_ses_noms_n_est_pas_signale_en_mode_valeurs():
    """Anti-faux-positif MESURE : `StatType` porte `CRIT_CHANCE` la ou le jeu dit
    `CriticalChance` -- UPPER_CASE ET abreviation, convention declaree dans sa docstring. En mode
    strict il rendrait 26 faux "renumerotes" sur 27 membres et noierait tout vrai signal."""
    port, jeu = {9: {"CRIT_CHANCE"}}, {9: {"CriticalChance"}}
    assert P.bijection(port, jeu, strict=True)[2], "le mode strict doit signaler le nom different"
    assert P.bijection(port, jeu, strict=False) == ([], [], [])


def test_le_mode_valeurs_reste_sensible_aux_deux_autres_sens():
    """`strict=False` relache les NOMS, jamais les VALEURS : un membre manquant ou mort doit
    toujours sortir, sinon `StatType` ne serait plus garde du tout."""
    manquants, morts, _ = P.bijection({0: {"X"}}, {0: {"Y"}, 5: {"Z"}}, strict=False)
    assert (manquants, morts) == ([(5, ["Z"])], [])


# --------------------------------- 5. les references qualifiees du depot resolvent

def test_toute_reference_qualifiee_resout_dans_le_mirror_et_dans_le_build():
    """`<Classe>.<membre>` dans du Python suivi -- lu par AST, donc les exemples de docstring
    (`TriggeredAbilityType.X`) ne comptent pas.

    Ce test a DEUX roles. Il attrape la typo (`AttributeError` a l'execution), et surtout il
    autorise la SUPPRESSION d'un membre mort : c'est lui qui a etabli, avant de retirer les 107
    membres morts de `TriggeredAbilityType`, qu'aucun n'etait cite -- 1438 references, 0 cassee."""
    introuvables, mortes = P.references_cassees(P.current_build())
    assert not introuvables, (
        "reference(s) qui ne resolvent pas dans le mirror (AttributeError a l'execution) :\n%s"
        % "\n".join("  %s:%d  %s.%s" % r for r in introuvables[:20]))
    assert not mortes, (
        "reference(s) a un membre que le build courant ne connait plus :\n%s\n"
        "  Elles ont l'air vivantes et ne peuvent plus rien matcher -- piege #270."
        % "\n".join("  %s:%d  %s.%s" % r for r in mortes[:20]))


def test_les_huit_membres_de_313_sont_la_ET_convertibles_depuis_le_gameconfig():
    """Le fait qui ouvre le dossier, re-derive PAR NOM (jamais par ordinal, qui bouge au build
    suivant). `triggered_ability_ids()` les convertit desormais, au lieu de les jeter."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    for nom in ("PropheticSentinel", "HeavyWarpFlamer_AttackTrackingAbility", "IconOfObstinacy",
                "WhisperingWeb", "EmpyricAmbush_Reset", "MyWillBeDoneOverlord",
                "PhasalSubjugator", "Helspear"):
        assert nom in T.__members__, "%s absent du mirror" % nom
    # `MyWillBeDoneOverlord` est porte par `necroOverlord`, lui-meme dans `rl_duel --list-pool` :
    # la conversion nom -> id doit donc reellement alimenter `triggered_ability_ids`.
    from engine.entities.triggered_ability_type import triggered_ability_ids
    assert int(T.MyWillBeDoneOverlord) in triggered_ability_ids("necroOverlord")
