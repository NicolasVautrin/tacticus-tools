"""#429 -- CLIQUET de couverture de l'inventaire des regles de ciblage (offline pur).

CE QUE CE FICHIER GARDE, ET POURQUOI IL TIENT LES DEUX DIRECTIONS
------------------------------------------------------------------
Le depot portait TROIS recensements concurrents de « quelles regles de ciblage ne sont pas
portees ». Aucun ne couvrait l'enum entier, aucun ne savait qu'il etait partiel, et chacun se
lisait comme une reponse a la question ENTIERE. Deux modes de defaillance distincts s'y
combinaient :

  * CONCEPTION -- une liste SAISIE ne prouve nulle part sa COUVERTURE. Elle peut ignorer 50
    membres sans qu'aucun test ne s'en emeuve.
  * DIRECTION MORTE -- rien ne rougissait quand une entree designait une classe/un membre
    DISPARU. Un inventaire peut donc pourrir des DEUX cotes.

D'ou les quatre assertions de couverture ci-dessous, sur la DIFFERENCE SYMETRIQUE
`enum <-> inventaire`, plus la confrontation de l'inventaire a la derivation AST du port.

CE QUI EST DERIVE, ET C'EST LE POINT
-------------------------------------
La colonne « portee / non portee » n'est SAISIE nulle part : elle est derivee de l'AST du port
(`probe_429_targeting_rule_inventory.rules_returned_by_port`). Une tranche qui porte une regle
neuve n'a donc RIEN a mettre a jour ici -- et une tranche qui en retire une ne peut pas laisser
une ligne de doc mentir. Seul le role NATIF est saisi, et il ne bouge qu'au changement de build,
ou la direction VIVANTE le rattrape.

CONTRE-EPREUVES JOUEES (2026-08-01), et l'une d'elles a d'abord MENTI :
  * `MutantRule = 1 << 58` ajoute au mirror `engine/runner/abilities/targeting_rule.py` -> ROUGE
    sur `test_mirror_couvre_le_dump_du_build_courant` (mirror \\ dump = ['MutantRule']).
    Restaure -> vert.
    ⚠ Le PREMIER jet nommait ce membre `__MutantRule` : `enum` IGNORE les noms prives, le mirror
    gardait ses 60 membres, et la garde restait VERTE. Un vert qui se lisait « la garde ne mord
    pas » alors que la MUTATION n'avait pas eu lieu. D'ou le controle prealable
    `assert ... , "la mutation n'a pas mordu"` dans chaque contre-epreuve integree ci-dessous.
  * assertion de la direction VIVANTE affaiblie (`manquants = []`) -> ROUGE sur
    `test_contre_epreuve_direction_vivante` (DID NOT RAISE). Restaure -> vert. C'est la preuve
    que les contre-epreuves integrees gardent bien les assertions, pas seulement les donnees.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import probe_429_targeting_rule_inventory as P
import symbols_layout
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.abilities.targeting_rule_inventory import KINDS, READERS, RULE_ROLE


def _dump_names() -> list:
    return [n for n, _v in P.enum_members()]


def _mirror_names() -> set:
    """Les noms du mirror GENERE, dans leur forme NATIVE (`None_` re-devient `None`).

    `__members__` et NON `for m in TR` : l'iteration d'un `IntFlag` ne rend que les membres
    CANONIQUES (bits simples). Elle laisse tomber le zero `None` et le composite
    `AllowObscuredTarget` -- soit exactement les deux membres qu'une garde de couverture doit
    voir. Mesure : le premier jet de ce test rougissait sur ces deux-la, et le compte de bits
    simples (58) n'est PAS le compte de membres (60)."""
    return {("None" if nom == "None_" else nom) for nom in TR.__members__}


# ---------------------------------------------------------------------------------------------
# 1. COUVERTURE -- la difference symetrique enum <-> inventaire, DANS LES DEUX SENS
# ---------------------------------------------------------------------------------------------
def test_direction_vivante_tout_membre_du_dump_est_classe():
    """`dump \\ inventaire` = VIDE. Un membre neuf (nouveau build) fait echouer tant qu'il n'est
    pas classe -- c'est ce qui empeche un inventaire de redevenir partiel en silence."""
    manquants = sorted(n for n in _dump_names() if n not in RULE_ROLE)
    assert not manquants, (
        "membres de TargetingRule NON CLASSES dans targeting_rule_inventory.RULE_ROLE : %s\n"
        "Les classer (kind + reader + armed_by), ne PAS les ignorer." % ", ".join(manquants))


def test_direction_morte_aucune_entree_ne_designe_un_membre_disparu():
    """`inventaire \\ dump` = VIDE. C'est la direction qu'aucun des trois inventaires remplaces
    ne tenait : une entree survivant a la disparition de son membre ne rougissait nulle part."""
    noms = set(_dump_names())
    fantomes = sorted(n for n in RULE_ROLE if n not in noms)
    assert not fantomes, (
        "entrees MORTES de RULE_ROLE (le membre n'existe plus dans le dump du build "
        "%s) : %s" % (symbols_layout.current_build(), ", ".join(fantomes)))


def test_mirror_couvre_le_dump_du_build_courant():
    """Le mirror GENERE et le dump du build QUI FAIT FOI decrivent le meme enum, dans les deux
    sens. Sans cette assertion, `gen_targeting_rule.py` pouvait generer depuis un build ARCHIVE
    (il prenait `sorted(glob)[0]`, pas `symbols_layout.current_build()`) : deux lecteurs qui
    partagent la meme entree perimee s'accordent parfaitement et le mensonge est invisible."""
    dump, mirror = set(_dump_names()), _mirror_names()
    assert dump == mirror, (
        "mirror \\ dump = %s ; dump \\ mirror = %s -- regenerer avec "
        "`python scripts/python/gen_targeting_rule.py`"
        % (sorted(mirror - dump), sorted(dump - mirror)))


def test_estampille_du_mirror_est_le_build_courant():
    """La docstring du mirror NOMME le dump dont il sort -- elle doit nommer le build qui fait foi.

    Trou MESURE sur moi-meme en livrant #429 : `test_mirror_couvre_le_dump_du_build_courant`
    compare les NOMS de membres, et les deux dumps declaraient le meme enum. Un mirror genere
    depuis un build ARCHIVE restait donc parfaitement vert, avec une estampille qui mentait. La
    coincidence des noms est un accident de ce build, pas une propriete."""
    import re
    from pathlib import Path
    import engine.runner.abilities.targeting_rule as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    cites = set(re.findall(r"data/symbols/([0-9a-z]+)/frida/enums\.tsv", src))
    courant = symbols_layout.current_build()
    assert cites == {courant}, (
        "le mirror dit sortir de %s, le build qui fait foi est %s -- regenerer avec "
        "`python scripts/python/gen_targeting_rule.py`" % (sorted(cites) or ["(rien)"], courant))


# ---------------------------------------------------------------------------------------------
# 2. INTEGRITE de l'inventaire
# ---------------------------------------------------------------------------------------------
def test_chaque_entree_porte_un_kind_et_un_reader_connus():
    mauvais_kind = sorted(n for n, r in RULE_ROLE.items() if r.kind not in KINDS)
    assert not mauvais_kind, "kind inconnu : %s" % ", ".join(mauvais_kind)
    lecteurs = set(READERS.values())
    mauvais_reader = sorted(n for n, r in RULE_ROLE.items()
                            if r.reader is not None and r.reader not in lecteurs)
    assert not mauvais_reader, (
        "reader hors de READERS (un symbole natif cite doit etre declare une seule fois) : %s"
        % ", ".join(mauvais_reader))


def test_reader_absent_seulement_pour_les_residus_nommes():
    """`reader is None` est reserve a `READER_UNKNOWN` (et a la valeur neutre). Sinon une entree
    pourrait perdre sa provenance sans le dire."""
    orphelins = sorted(n for n, r in RULE_ROLE.items()
                       if r.reader is None and r.kind != "READER_UNKNOWN" and n != "None")
    assert not orphelins, "entree sans reader et non classee READER_UNKNOWN : %s" % ", ".join(orphelins)


def test_reason_code_designe_un_membre_reel():
    noms = set(_dump_names())
    faux = sorted(n for n, r in RULE_ROLE.items()
                  if r.reason_code is not None and r.reason_code not in noms)
    assert not faux, "reason_code inconnu de l'enum : %s" % ", ".join(faux)


def test_bijection_armed_by_et_predicats():
    """Toute regle dont l'armement N'EST PAS son propre bit doit avoir son predicat, et
    reciproquement. C'est l'assertion qui empeche de recompter « les porteurs du bit » sur une
    regle armee par autre chose -- la faute exacte qui faisait ecrire « 0 porteur, rien a
    porter » pour `TargetIsAllowedForCaster`, armee chez 59 abilities du registre."""
    # Restreint aux GATE : `armed_by` documente aussi l'origine d'un CODE DE RAISON
    # (`AlreadyUseThisTurn` vient d'`AttackQuery$$IsAlreadyUsedThisTurn`), qui n'a pas de
    # porteurs a compter puisqu'aucun masque ne le pose.
    declarees = {n for n, r in RULE_ROLE.items()
                 if r.armed_by is not None
                 and r.kind in ("GATE_TARGET", "GATE_CASTER", "GATE_ADD_CASTER")}
    codees = set(P.ARMED_BY)
    assert declarees == codees, (
        "declarees sans predicat = %s ; predicats sans declaration = %s"
        % (sorted(declarees - codees), sorted(codees - declarees)))


def test_armed_by_default_est_un_sous_ensemble_reel():
    inconnues = sorted(n for n in P.ARMED_BY_DEFAULT if n not in RULE_ROLE)
    assert not inconnues, "ARMED_BY_DEFAULT cite un membre inconnu : %s" % ", ".join(inconnues)


# ---------------------------------------------------------------------------------------------
# 3. CONFRONTATION inventaire <-> port (la colonne DERIVEE)
# ---------------------------------------------------------------------------------------------
def test_toute_regle_derivee_est_classee():
    """Tout code de refus que le port RENDS designe un membre classe. Un `int(TR.X)` sur un
    membre inconnu de l'inventaire est un port qui a pris de l'avance sur son recensement."""
    rendues = set(P.rules_returned_by_port())
    inconnues = sorted(n for n in rendues if n not in RULE_ROLE)
    assert not inconnues, "le port rend des regles NON CLASSEES : %s" % ", ".join(inconnues)


def test_le_port_ne_rend_jamais_une_permission_qui_ne_soit_pas_un_refus_natif():
    """Une PERMISSION desarme une regle : la RENDRE comme code de refus serait inventer un refus.
    UNE seule exception, et elle est NATIVE : `AllowNullCasterTile`, que
    `TargetingQuery$$GetInvalidCasterReason` rend bel et bien quand `casterTiles` est vide sans
    permission ni `CasterHasNoTile`.

    ⚠ Cette assertion a accuse le MOTEUR pour une faute de l'ORACLE (#10012). Elle designait
    `AllowIgnoreForcedAttackTarget`, que le port n'a jamais rendu : il l'ECRIT dans un masque
    (`targeting.py::targeting_options_for_continue`), mirror 1:1 du `opts.<+0x28 rules> |=
    0x10000000000` d'`IdunBattle.Entities.Abilities.AActiveAbility$$GetTargetingOptionsForContinue`.
    C'est la DERIVATION qui comptait un `int(TR.<X>)` n'importe ou sous un `return`. Le decompile
    du build courant tranche dans les deux sens : le seul `movabs 1<<40` de tout le binaire est
    celui de `GetTargetingOptionsForContinue` (ECRITURE), et aucun des ~30 `rule = <litteral>` que
    `TargetingQuery$$GetInvalidTargetReason` passe a
    `TargetingRuleExtensions$$GenericBrokenTargetingRule` ne vaut `0x10000000000` -- le bit 40 n'y
    est LU que pour DESARMER le taunt, dont le code rendu est `TargetIsAllowedForCaster` (0x800000).
    La liste d'exceptions reste donc a UNE entree ; c'est le critere qui a ete resserre."""
    rendues = set(P.rules_returned_by_port())
    fautives = sorted(n for n in rendues
                      if RULE_ROLE.get(n) is not None
                      and RULE_ROLE[n].kind == "PERMISSION" and n != "AllowNullCasterTile")
    assert not fautives, (
        "le port rend une PERMISSION comme code de refus (refus INVENTE) : %s" % ", ".join(fautives))


#: Les `int(TR.<X>)` sous un `return` que la POSITION DE VALEUR ecarte, NOMMES un par un.
#: (nom de regle, fichier du port, fonction porteuse). Un ecarte NEUF doit etre LU et inscrit ici
#: -- c'est ce qui empeche le resserrement de #10012 de faire disparaitre un site en silence.
ECARTES_DECLARES = {
    # `AActiveAbility$$GetTargetingOptionsForContinue` : `opts.<+0x28 rules> |= 0x10000000000`.
    # Une COMPOSITION DE MASQUE, pas un code de refus -- le natif POSE ce bit, il ne le REND jamais.
    ("AllowIgnoreForcedAttackTarget", "targeting.py", "targeting_options_for_continue"),
}


def test_les_ecartes_de_la_position_de_valeur_sont_NOMMES():
    """Un filtre DIT ce qu'il filtre. Le critere « en position de valeur rendue » ECARTE des
    `int(TR.<X>)` que l'ancien critere comptait : chacun doit etre NOMME ici, jamais tu.

    Les deux directions comptent, et pour des raisons differentes :
      * un ecarte NEUF (non declare) est un site que la derivation ne compte plus SANS que
        personne l'ait lu -- exactement le mode de defaillance « la colonne se perime en
        silence » que #429 a ferme ;
      * un ecarte DECLARE mais DISPARU rend ce test VACANT : le resserrement ne serait plus
        exerce par aucun code reel, et un futur elargissement passerait inapercu."""
    mesures = P.rules_dropped_by_value_position()
    assert mesures, (
        "AUCUN site n'est ecarte par la position de valeur -- le resserrement de #10012 n'est "
        "plus exerce par le port reel, ce test ne garde plus rien")
    neufs = sorted(mesures - ECARTES_DECLARES)
    disparus = sorted(ECARTES_DECLARES - mesures)
    assert not neufs, (
        "ecarte(s) NEUF(S), a LIRE puis inscrire dans ECARTES_DECLARES (ou a corriger si le port "
        "voulait bien rendre un code de refus) : %s" % ", ".join(str(t) for t in neufs))
    assert not disparus, (
        "ecarte(s) DECLARE(S) mais DISPARU(S) -- retirer la ligne de ECARTES_DECLARES : %s"
        % ", ".join(str(t) for t in disparus))


def test_ported_by_designe_une_fonction_qui_existe_dans_le_port():
    """#447 -- une entree `ported_by` nomme (fonction du port, jeton). Si la FONCTION n'existe pas,
    la derivation rend « non portee » SANS RIEN DIRE : un faux negatif indiscernable d'un vrai
    non-port. C'est le meme mode de defaillance que le zero de methode que #429 a ferme -- on garde
    donc l'existence de la fonction, pas seulement le resultat."""
    import ast
    fns = set()
    for f in P._port_modules():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        fns |= {n.name for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    orphelines = sorted(n for n, r in RULE_ROLE.items()
                        if r.ported_by and r.ported_by[0] not in fns)
    assert not orphelines, (
        "ported_by designe une fonction ABSENTE du port (la derivation rendrait un faux "
        "« non portee ») : %s" % ", ".join(orphelines))


def test_ported_by_reserve_aux_regles_qui_ne_sont_jamais_un_code_de_refus():
    """`ported_by` est une DEROGATION au critere ordinaire (`int(TR.<X>)` rendu), et elle n'est
    legitime que la ou le NATIF lui-meme ne rend jamais le code de la regle.

    DEUX volets, et le second n'est PAS une entree de plus dans la liste :
      * une liste NOMINATIVE, pour les quatre regles de CIBLAGE concernees -- le court-circuit
        `AddCaster` et les trois POINTS D'EXTENSION. Elle reste saisie parce que rien dans leur
        `kind` (GATE_*) ne les distingue des regles qui rendent bien leur code ;
      * le kind `GATE_OPERATION` (#429-r1), qui est STRUCTURELLEMENT dans le champ de la derogation :
        sa definition meme est « regle lue hors ciblage, dont le natif ABANDONNE l'operation au lieu
        de rendre un `IBrokenTargetingRule` ». Une telle regle ne peut, par construction, jamais etre
        un code de refus rendu -- l'ouvrir nominativement aurait fait grossir la liste a chaque
        membre du meme genre.
    L'ouvrir a une regle qui rend bel et bien son code permettrait de declarer « portee » une regle
    que le port ne rend nulle part."""
    autorisees = {"AddCaster", "AddCasterIfMatchesDynamicRule",
                  "TargetMatchesDynamicRule", "CasterMatchesDynamicRule"}
    declarees = {n for n, r in RULE_ROLE.items()
                 if r.ported_by and r.kind != "GATE_OPERATION"}
    assert declarees <= autorisees, (
        "ported_by pose sur une regle qui EST un code de refus natif : %s"
        % ", ".join(sorted(declarees - autorisees)))


def test_contre_epreuve_ported_by_hors_allowlist(monkeypatch):
    """La derogation `ported_by` MORD-elle encore ? On la pose sur une regle de CIBLAGE ordinaire
    (`TargetIsEnemy`, un vrai code de refus natif) -- l'assertion doit rougir. Sans cette morsure,
    l'ouverture faite pour `GATE_OPERATION` ci-dessus pourrait avoir vide la garde de son sens."""
    from dataclasses import replace as _replace
    import engine.runner.abilities.targeting_rule_inventory as INV
    mute = dict(RULE_ROLE)
    mute["TargetIsEnemy"] = _replace(RULE_ROLE["TargetIsEnemy"],
                                     ported_by=("get_invalid_target_reason", "TargetIsEnemy"))
    monkeypatch.setattr(INV, "RULE_ROLE", mute)
    monkeypatch.setitem(globals(), "RULE_ROLE", mute)
    assert RULE_ROLE["TargetIsEnemy"].ported_by, "la mutation n'a pas mordu"
    assert RULE_ROLE["TargetIsEnemy"].kind != "GATE_OPERATION", "la mutation n'a pas mordu"
    with pytest.raises(AssertionError, match="EST un code de refus natif"):
        test_ported_by_reserve_aux_regles_qui_ne_sont_jamais_un_code_de_refus()


def test_contre_epreuve_ported_by_sans_le_jeton(monkeypatch):
    """Le jeton retire de l'entree -> la regle doit REDEVENIR non portee. Sans cette morsure,
    `ported_by` serait un interrupteur « declare portee » au lieu d'une derivation."""
    from dataclasses import replace as _replace
    cible = "AddCasterIfMatchesDynamicRule"
    assert cible in P.rules_ported_by_delegation(), "etat de depart : la regle doit etre portee"
    mute = dict(RULE_ROLE)
    mute[cible] = _replace(RULE_ROLE[cible],
                           ported_by=("get_caster_not_added_reason", "__jeton_inexistant__"))
    monkeypatch.setattr(P, "RULE_ROLE", mute)
    assert P.RULE_ROLE[cible].ported_by[1] == "__jeton_inexistant__", "la mutation n'a pas mordu"
    assert cible not in P.rules_ported_by_delegation(), (
        "la derivation rend la regle portee alors que son jeton est absent de la fonction "
        "porteuse -- `ported_by` ne derive plus rien")


def test_toute_regle_gate_a_un_compte_de_porteurs_calculable():
    """Le rapport doit etre calculable pour CHAQUE gate -- pas seulement pour ceux qu'une table
    historique avait retenus. C'est la garantie de couverture du rapport lui-meme."""
    masks = P.collect_masks()
    gates = [n for n, r in RULE_ROLE.items()
             if r.kind in ("GATE_TARGET", "GATE_CASTER", "GATE_ADD_CASTER")]
    assert gates, "aucun gate classe -- l'inventaire est vide ou mal charge"
    for n in gates:
        carriers = P.armed_carriers(n, masks)
        assert isinstance(carriers, list), "porteurs non calculables pour %s" % n


# ---------------------------------------------------------------------------------------------
# 4. CONTRE-EPREUVES INTEGREES -- la garde prouve sa MORSURE dans le meme processus
# ---------------------------------------------------------------------------------------------
# Une garde juste mais jamais exercee ne vaut rien : c'est le mode de defaillance EXECUTION
# (#427). Ces trois tests injectent la faute que chaque assertion est censee attraper et
# verifient qu'elle rougit -- ils tombent donc aussi si quelqu'un affaiblit une assertion.
# ⚠ Leur redaction est elle-meme sous surveillance : un premier jet de contre-epreuve ajoutait
# un membre nomme `__MutantRule` au mirror... que `enum` IGNORE (nom prive). La garde restait
# VERTE, et le vert lisait comme « mutation survecue » alors que la mutation n'avait pas eu
# lieu. Ici la morsure est verifiee par une assertion PREALABLE sur l'etat mute.
def test_contre_epreuve_direction_vivante(monkeypatch):
    """Un membre NEUF au dump, non classe -> la direction VIVANTE doit rougir."""
    reels = P.enum_members()
    mute = list(reels) + [("MutantRule", 1 << 58)]
    monkeypatch.setattr(P, "enum_members", lambda build=None: mute)
    assert "MutantRule" in [n for n, _v in P.enum_members()], "la mutation n'a pas mordu"
    with pytest.raises(AssertionError, match="NON CLASSES"):
        test_direction_vivante_tout_membre_du_dump_est_classe()


def test_contre_epreuve_direction_morte(monkeypatch):
    """Une entree d'inventaire dont le membre a DISPARU du dump -> la direction MORTE doit
    rougir. C'est celle qu'aucun des trois inventaires remplaces ne tenait."""
    reels = [(n, v) for n, v in P.enum_members() if n != "TargetIsHero"]
    monkeypatch.setattr(P, "enum_members", lambda build=None: reels)
    assert "TargetIsHero" not in [n for n, _v in P.enum_members()], "la mutation n'a pas mordu"
    assert "TargetIsHero" in RULE_ROLE
    with pytest.raises(AssertionError, match="MORTES"):
        test_direction_morte_aucune_entree_ne_designe_un_membre_disparu()


def test_contre_epreuve_armement_perdu(monkeypatch):
    """Un predicat d'armement retire -> la bijection doit rougir. Sans elle, le compte de
    porteurs retomberait sur le bit, donc a ZERO pour la regle concernee."""
    ampute = {k: v for k, v in P.ARMED_BY.items() if k != "TargetIsAllowedForCaster"}
    monkeypatch.setattr(P, "ARMED_BY", ampute)
    assert "TargetIsAllowedForCaster" not in P.ARMED_BY, "la mutation n'a pas mordu"
    with pytest.raises(AssertionError, match="declarees sans predicat"):
        test_bijection_armed_by_et_predicats()


def _module_synthetique(tmp_path, nom_fichier: str, source: str):
    """Ecrit un module JETABLE et le substitue au perimetre du port, pour exercer la DERIVATION
    sur une forme que le port reel n'a pas. On ne touche a aucun fichier du depot."""
    f = tmp_path / nom_fichier
    f.write_text(source, encoding="utf-8")
    return f


def test_contre_epreuve_une_permission_rendue_en_position_de_valeur_ROUGIT(tmp_path, monkeypatch):
    """Le resserrement de #10012 MORD-il encore dans le bon sens ? Un port qui rendrait vraiment
    une PERMISSION comme code de refus (`return int(TR.<permission>)`) doit toujours faire rougir.
    Sans cette morsure, la narrowing du critere pourrait avoir vide la garde de son sens."""
    f = _module_synthetique(tmp_path, "faux_refus.py", (
        "def get_invalid_target_reason_mutant(options):\n"
        "    return int(TR.AllowUntargetableTarget)\n"))
    monkeypatch.setattr(P, "_port_modules", lambda: [f])
    assert "AllowUntargetableTarget" in P.rules_returned_by_port(), "la mutation n'a pas mordu"
    assert RULE_ROLE["AllowUntargetableTarget"].kind == "PERMISSION", "la mutation n'a pas mordu"
    with pytest.raises(AssertionError, match="refus INVENTE"):
        test_le_port_ne_rend_jamais_une_permission_qui_ne_soit_pas_un_refus_natif()


def test_contre_epreuve_une_composition_de_masque_n_est_PAS_un_code_de_refus(tmp_path, monkeypatch):
    """L'autre sens : les DEUX formes que la position de valeur doit ecarter, sur du code
    synthetique -- l'operande d'un `|` dans un argument nomme (la forme reelle de
    `targeting_options_for_continue`) et le `test` d'un `IfExp` (ce qu'un test LIT n'est pas ce
    qui est RENDU). Aucune ne doit compter comme code de refus, et les DEUX doivent ressortir
    NOMMEES par `rules_dropped_by_value_position`."""
    f = _module_synthetique(tmp_path, "masque.py", (
        "def options_mutantes(options):\n"
        "    return replace(options,\n"
        "                   rules=int(options.rules) | int(TR.AllowUntargetableTarget))\n"
        "\n"
        "def aiguillage_mutant(options):\n"
        "    return 0 if int(TR.AllowSteppableUnit) else 1\n"))
    monkeypatch.setattr(P, "_port_modules", lambda: [f])
    assert P._returns_du_port(), "la mutation n'a pas mordu : aucun `return` vu"
    rendues = P.rules_returned_by_port()
    assert "AllowUntargetableTarget" not in rendues, (
        "un `int(TR.X)` operande d'un `|` est compte comme CODE DE REFUS -- le critere ne "
        "discrimine plus la COMPOSITION DE MASQUE du refus rendu")
    assert "AllowSteppableUnit" not in rendues, (
        "un `int(TR.X)` en position de TEST d'un `IfExp` est compte comme CODE DE REFUS")
    ecartes = {n for n, _f, _fn in P.rules_dropped_by_value_position()}
    assert ecartes == {"AllowUntargetableTarget", "AllowSteppableUnit"}, (
        "les ecartes ne sont pas NOMMES a l'identique de ce qui a ete filtre : %s" % sorted(ecartes))
    # ... et le CLIQUET des ecartes mord sur eux : ils ne sont pas dans `ECARTES_DECLARES`.
    with pytest.raises(AssertionError, match="ecarte"):
        test_les_ecartes_de_la_position_de_valeur_sont_NOMMES()


def test_contre_epreuve_position_de_valeur_conserve_les_formes_reelles(tmp_path, monkeypatch):
    """Le resserrement ne doit RIEN perdre des formes que le port emploie vraiment : `return
    int(TR.X)` nu, et les deux branches d'un `IfExp` (`0 if c else int(TR.X)` /
    `int(TR.X) if c else 0`), y compris IMBRIQUE
    (`targeting.py::get_target_domain_broken_rule` en a un). Mesure du 2026-08-15 : ces formes
    couvrent les 116 sites retenus du port reel, et le resserrement n'en retire QU'UN sur 117."""
    f = _module_synthetique(tmp_path, "formes.py", (
        "def nu(o):\n"
        "    return int(TR.TargetIsEnemy)\n"
        "\n"
        "def sinon(o, c):\n"
        "    return 0 if c else int(TR.TargetIsFriendly)\n"
        "\n"
        "def alors(o, c):\n"
        "    return int(TR.TargetIsHealable) if c else 0\n"
        "\n"
        "def imbrique(o, a, b):\n"
        "    return 0 if a else int(TR.TargetIsMachine) if b else 0\n"
        "\n"
        "def ou_logique(o):\n"
        "    return int(TR.TargetIsSummon) or 0\n"))
    monkeypatch.setattr(P, "_port_modules", lambda: [f])
    attendu = {"TargetIsEnemy", "TargetIsFriendly", "TargetIsHealable", "TargetIsMachine",
               "TargetIsSummon"}
    assert set(P.rules_returned_by_port()) == attendu, (
        "la position de valeur PERD une forme reellement employee par le port : manquantes = %s"
        % sorted(attendu - set(P.rules_returned_by_port())))
    assert not P.rules_dropped_by_value_position(), (
        "une forme de valeur rendue est comptee comme ECARTEE : %s"
        % sorted(P.rules_dropped_by_value_position()))
    # Et le GARDE-VACANCE du cliquet mord : plus aucun ecarte -> le resserrement n'est plus
    # exerce par du code reel, donc le test des ecartes doit REFUSER de passer pour vert.
    with pytest.raises(AssertionError, match="AUCUN site n'est ecarte"):
        test_les_ecartes_de_la_position_de_valeur_sont_NOMMES()


def test_contre_epreuve_returns_de_closure_comptes_une_seule_fois(tmp_path, monkeypatch):
    """`_returns_du_port` attribue chaque `return` a sa fonction porteuse la PLUS INTERNE. Un
    `ast.walk` imbrique compterait le `return` d'une closure DEUX fois, une fois sous le nom de
    la fonction externe -- et l'ecarte se declarerait alors sous un nom de fonction FAUX."""
    f = _module_synthetique(tmp_path, "closure.py", (
        "def fabrique(o):\n"
        "    def regle(state, tid):\n"
        "        return replace(o, rules=int(o.rules) | int(TR.AllowUntargetableTarget))\n"
        "    return regle\n"))
    monkeypatch.setattr(P, "_port_modules", lambda: [f])
    ecartes = P.rules_dropped_by_value_position()
    assert ecartes == {("AllowUntargetableTarget", "closure.py", "regle")}, (
        "le `return` de la closure n'est pas attribue a la fonction la plus interne, ou il est "
        "compte plusieurs fois : %s" % sorted(ecartes))


@pytest.mark.parametrize("nom", ["TargetIsAllowedForCaster", "TargetIsNotSteppable"])
def test_les_regles_armees_par_autre_chose_ne_comptent_pas_zero(nom):
    """CONTRE-MESURE CHIFFREE de la faute d'origine. Ces deux regles ont un compte NUL quand on
    compte les porteurs de LEUR bit, et un compte a deux chiffres quand on compte leur ARMEMENT
    reel. Si cette assertion tombe a zero, c'est que le calcul est retombe sur le bit."""
    masks = P.collect_masks()
    par_le_bit = sum(1 for _a, (r, _n) in masks.items() if r & int(getattr(TR, nom)))
    par_armement = len(P.armed_carriers(nom, masks))
    assert par_armement > par_le_bit, (
        "%s : armement=%d, porteurs du bit=%d -- le compte est retombe sur le bit"
        % (nom, par_armement, par_le_bit))
