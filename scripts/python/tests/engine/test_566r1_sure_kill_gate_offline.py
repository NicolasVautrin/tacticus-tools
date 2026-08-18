"""#566-r1 -- `EnemyCouldBeKilledWithNormalAttack` : le verdict se LIT, il ne se re-derive pas.

CE QUE CE FICHIER GARDE, ET POURQUOI IL EXISTE A COTE DU BANC LIVE
------------------------------------------------------------------
Le banc live (`tests/engine/runner/test_566_vexilla_magnifica_live.py`, bras
`sure_kill_bloque`) mesure UN regime : une cible a `blockChance > 0` que le natif ne tient pas pour
sure-kill. Il ne peut pas montrer :

  1. le **TRI-ETAT**. `ranked[].killSure` est ABSENT quand `computeWillBeKill` de
     `frida/hooks/game/damage-prediction.ts` rend `null` -- decodeur en echec sur `BlockScenarios`,
     ou plan produit par un bundle anterieur a #372. Ce n'est PAS un `false`, et fabriquer un
     `false` indiscernable est exactement ce que #372 reprochait aux trois foyers qu'il a fermes.
     Aucun montage live ne produit ce regime a la demande : seul un plan SYNTHETIQUE le peut ;
  2. que le gate ne mord PLUS sur `dmgMin >= hp` **seul**. Un banc live ou les deux coincident
     resterait vert avec l'ancienne regle ;
  3. que le COURT-CIRCUIT du `return true` natif l'emporte sur l'indecidable ;
  4. que les consommateurs sont EXACTEMENT ceux que le binaire nomme. La fiche #566 §6 en
     annoncait SIX (`HammerOfWrath`, `BloodyFury`, `VexillaMagnifica`, `Stormcaller`,
     `VigilanceEternal`, `BlackRage`) ; les xrefs entrantes de
     `IdunBattle.AI.Playbook.BasePlaybook$$EnemyWillBeKilledWithNormalAttack` en donnent TROIS
     (`GravitonRiflePlaybook$$ShouldEvaluate`, `VexillaMagnificaPlaybook$$ShouldEvaluate` -- le
     corps COMDAT que `HammerOfWrathPlaybook$$ShouldEvaluate` partage --, et
     `SupremeCommanderPlaybook$$ShouldEvaluate`, que la fiche OMETTAIT). `VigilanceEternal` teste
     `GetStat(unit, 0xc) > 1`, `BloodyFury`/`BlackRage` n'ont qu'un `GetUseProbability`,
     `Stormcaller` n'a ni l'un ni l'autre. Un compte errone fait sur-estimer le rayon de souffle
     d'un fix -- c'est ce qui avait fait DIFFERER celui-ci.

     ⚠ #566-r1-r2 -- TROIS XREFS NATIVES NE FONT PAS TROIS MODULES PYTHON, et c'est ce glissement
     qui a rendu `master` rouge. Le corps COMDAT `VexillaMagnificaPlaybook$$ShouldEvaluate` est
     partage par `HammerOfWrath` : les trois xrefs ci-dessus se portent en QUATRE modules. Le
     quatrieme (`graviton_rifle`, #975) etait deja NOMME dans ce paragraphe et absent de
     l'assertion. L'effectif Python n'etant contraint par rien de stable, le recensement est
     desormais garde par un CRITERE (adossement au symbole natif + non-confusion), pas par un
     compte.

ASCII only. Aucun runner, aucun RPC : plans SYNTHETIQUES.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # PROPRE A CE FICHIER : le foyer du gate, ses TROIS consommateurs portes, et le producteur
        # TypeScript du champ `killSure` qu'il lit -- si `projection.ts` cessait de le poser, ce
        # fichier resterait vert alors que le port serait redevenu aveugle.
        "scripts/python/engine/playbook/noncomparable/hammer_of_wrath.py",
        "scripts/python/engine/playbook/noncomparable/vexilla_magnifica.py",
        "scripts/python/engine/playbook/noncomparable/supreme_commander.py",
        # #566-r1-r2 -- le QUATRIEME lecteur, porte par #975 (`f6e2674b`). Il manquait ici EN MEME
        # TEMPS qu'il manquait a l'assertion du recensement : un declencheur derive de la liste
        # attestee herite exactement des angles morts de cette liste.
        "scripts/python/engine/playbook/noncomparable/graviton_rifle.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "frida/hooks/features/ai-step/projection.ts",
        "frida/hooks/game/damage-prediction.ts",
    ),
    "build": False,
    "toujours": False,
    "raison": "Plans SYNTHETIQUES : aucun ordinal ni offset n'est lu du build. Le verdict ne "
              "depend que du foyer Python et du champ que le hook publie.",
}

import ast
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PYDIR))

from engine.playbook.noncomparable import hammer_of_wrath as HW              # noqa: E402
from engine.playbook.noncomparable._base import NCContext                    # noqa: E402

#: Id de l'attaque NORMALE CONCRETE du caster synthetique (`GetNormalAttackType`, per-unit --
#: JAMAIS l'abstrait 17, cf. project_ability_normal_attack_concrete).
NORMAL = 69
CASTER, CIBLE = 77, 81
HP = 50


def _ctx(ranked, *, ability_id=NORMAL, hp=HP):
    """`NCContext` minimal : ce que le gate LIT, et rien de plus (unite + son attaque normale, un
    plan a une eval, les PV courants de la cible)."""
    return NCContext(
        uid=CASTER, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[],
        plan={"evals": [{"abilityId": ability_id, "targetId": CIBLE, "ranked": list(ranked)}]},
        hp_cur_by_id={CIBLE: hp},
        units=[{"id": CASTER, "abilities": [{"id": NORMAL, "kind": "normal"}]}])


# --------------------------------------------------------------- 1. les TROIS etats, un par un

def test_killSure_vrai_ETABLIT_l_existence():
    """`get_WillBeKill` vrai sur une paire (tuile, cible) => `return true` natif."""
    ctx = _ctx([{"col": 1, "row": 1, "dmgMin": 10, "dmgMax": 10, "killSure": True}])
    assert HW._normal_attack_sure_kill_state(ctx) is True
    assert HW._enemy_killed_by_normal_attack(ctx) is True


def test_killSure_faux_partout_ETABLIT_l_absence_MEME_si_dmgMin_depasse_les_PV():
    """LE CRAN DE #566-r1. `dmgMin = dmgMax = 50` contre 50 PV : l'ancienne regle re-derivee
    (`dmgMin >= hp`) rendait VRAI. Le natif, lui, a lu `BlockScenarios[0]` et rend FAUX -- c'est ce
    que `killSure` porte. Le port doit suivre le VERDICT, pas les bornes."""
    ctx = _ctx([{"col": 1, "row": 1, "dmgMin": 50, "dmgMax": 50, "killSure": False}])
    assert HW._normal_attack_sure_kill_state(ctx) is False
    assert HW._enemy_killed_by_normal_attack(ctx) is False


def test_killSure_absent_avec_une_prediction_rend_INDECIDABLE():
    """`willBeKill === null` cote hook => le champ n'est PAS pose. Le foyer rend `None`, jamais un
    `False` indiscernable d'une absence MESUREE."""
    ctx = _ctx([{"col": 1, "row": 1, "dmgMin": 50, "dmgMax": 50}])
    assert HW._normal_attack_sure_kill_state(ctx) is None


def test_la_BORNE_de_port_rabat_l_indecidable_sur_le_gate_qui_NE_MORD_PAS():
    """Borne de port NOMMEE, meme direction que les deux de
    `engine.playbook.base.will_normal_attack_kill` : `None` -> `False`. Elle reste DISCERNABLE --
    le tri-etat, lui, dit `None`."""
    ctx = _ctx([{"col": 1, "row": 1, "dmgMin": 50, "dmgMax": 50}])
    assert HW._enemy_killed_by_normal_attack(ctx) is False
    assert HW._normal_attack_sure_kill_state(ctx) is not False


# ------------------------------------------------------- 2. composition : court-circuit et bruit

def test_une_paire_VRAIE_l_emporte_sur_une_INDECIDABLE():
    """Le natif sort au PREMIER `get_WillBeKill` vrai : l'existence est etablie, l'indecidable des
    paires suivantes ne peut plus la defaire. Et l'ORDRE ne change rien."""
    sure = {"col": 1, "row": 1, "dmgMin": 10, "dmgMax": 10, "killSure": True}
    flou = {"col": 2, "row": 2, "dmgMin": 50, "dmgMax": 50}
    assert HW._normal_attack_sure_kill_state(_ctx([sure, flou])) is True
    assert HW._normal_attack_sure_kill_state(_ctx([flou, sure])) is True


def test_une_tuile_SANS_prediction_ne_salit_PAS_le_tri_etat():
    """Un `ranked` sans AUCUN champ de degat = le hook n'a pas obtenu de prediction pour cette
    tuile (`GetAllPredictions` nul ou en exception). Ce n'est pas << killSure non mesure >> : c'est
    une entree vide, et l'ignorer est ce que le port faisait deja."""
    ctx = _ctx([{"col": 1, "row": 1},
                {"col": 2, "row": 2, "dmgMin": 10, "dmgMax": 10, "killSure": False}])
    assert HW._normal_attack_sure_kill_state(ctx) is False


def test_une_eval_d_une_AUTRE_ability_est_ignoree():
    """Le natif ne balaye que `GetAllNormalAttackTargets` = l'attaque NORMALE du caster. Une eval
    d'ability ACTIVE qui sure-kill ne ferme PAS ce gate."""
    ctx = _ctx([{"col": 1, "row": 1, "dmgMin": 999, "dmgMax": 999, "killSure": True}],
               ability_id=1183)
    assert HW._normal_attack_sure_kill_state(ctx) is False


def test_une_cible_hors_de_l_etat_suivi_est_ignoree_sans_salir_le_tri_etat():
    """PV inconnus => le port ne sait pas de quelle cible il parle ; le natif, lui, en a toujours
    un. C'est une borne de substrat, pas un indecidable de VERDICT."""
    ctx = _ctx([{"col": 1, "row": 1, "dmgMin": 50, "dmgMax": 50}], hp=None)
    ctx.hp_cur_by_id = {}
    assert HW._normal_attack_sure_kill_state(ctx) is False


# --------------------------------------------------- 3. le foyer est PARTAGE par ses 3 lecteurs

def test_les_trois_should_evaluate_portes_passent_par_LE_MEME_foyer():
    """`HammerOfWrath` (1153), `VexillaMagnifica` (1183), `SupremeCommander` (1160) et, depuis #975,
    `GravitonRifle` (1206) appellent tous `_enemy_killed_by_normal_attack`. Substituer le FOYER doit
    donc les renverser d'un coup -- des corps separes auraient ete un fork du meme corps natif
    (`BasePlaybook$$ShouldEvaluate` COMDAT).

    `SupremeCommander` (`AllDeadUnits`, `FillUpStatComponent`) et `GravitonRifle`
    (`HasAnyRepairTarget`) ont d'AUTRES gates en aval : on ne verifie donc chez eux QUE le sens qui
    court-circuite (`gate vrai => False`), le seul que le foyer commande a lui seul."""
    from engine.playbook.noncomparable.graviton_rifle import GravitonRiflePlaybook
    from engine.playbook.noncomparable.hammer_of_wrath import HammerOfWrathPlaybook
    from engine.playbook.noncomparable.supreme_commander import SupremeCommanderPlaybook
    from engine.playbook.noncomparable.vexilla_magnifica import VexillaMagnificaPlaybook

    sure = _ctx([{"col": 1, "row": 1, "dmgMin": 10, "dmgMax": 10, "killSure": True}])
    pas_sure = _ctx([{"col": 1, "row": 1, "dmgMin": 50, "dmgMax": 50, "killSure": False}])
    for cls in (HammerOfWrathPlaybook, VexillaMagnificaPlaybook, SupremeCommanderPlaybook,
                GravitonRiflePlaybook):
        assert cls().should_evaluate(sure) is False, cls.__name__
    for cls in (HammerOfWrathPlaybook, VexillaMagnificaPlaybook):
        assert cls().should_evaluate(pas_sure) is True, cls.__name__


#: Le symbole natif dont `_enemy_killed_by_normal_attack` est le port. C'est LUI le discriminant,
#: pas le nombre de modules : `EnemyCouldBeKilledWithNormalAttack` (le corps SOUS-JACENT, par cible)
#: est cite par `_base` et `holy_duel`, qui n'appellent pas ce gate.
SYMBOLE_DU_GATE = "EnemyWillBeKilledWithNormalAttack"

#: Le foyer de l'AUTRE corps natif (`WillNormalAttackKill`, par CIBLE), dont les deux crans #372
#: vivent dans `engine.playbook.base`. Aucun module ne doit lire les deux : les confondre ferait
#: croire le gisement plus large qu'il n'est.
FOYER_VOISIN = "will_normal_attack_kill"

#: Les lecteurs MESURES, avec ce qui atteste chacun cote NATIF. Cette table n'est PAS le critere
#: (cf. `test_le_recensement_...`) : elle est le TEMOIN de non-rétrécissement.
LECTEURS_ATTESTES = {
    "hammer_of_wrath": "corps COMDAT partage avec `VexillaMagnificaPlaybook$$ShouldEvaluate`",
    "vexilla_magnifica": "`VexillaMagnificaPlaybook$$ShouldEvaluate`",
    "supreme_commander": "`SupremeCommanderPlaybook$$ShouldEvaluate`",
    # #566-r1-r2 -- QUATRIEME lecteur, porte par #975 (`f6e2674b`). La docstring de ce fichier le
    # NOMMAIT DEJA en tete des trois xrefs natives ; seule l'assertion ne l'avait pas, parce que le
    # module n'existait pas encore a l'ecriture. Une liste ecrite ne peut pas montrer le port qui
    # arrivera apres elle.
    "graviton_rifle": "`GravitonRiflePlaybook$$ShouldEvaluate`",
}


def _appels(arbre):
    """Les NOMS de fonction REELLEMENT appeles (`f(...)` et `o.f(...)`), par AST.

    ⚠ PAR AST, JAMAIS PAR TEXTE -- meme durcissement que `probe_498r3._appels` et que le §5 de
    `case-589-r2`. Le critere d'origine etait un `re.search(r"<nom>\\s*\\(")` sur la source entiere :
    une docstring qui EXPLIQUE le gate (`... rend `_enemy_killed_by_normal_attack(ctx)` ...`) aurait
    suffi a faire d'un module un lecteur. Mesure du 2026-08-18 : sur l'arbre courant les deux
    criteres COINCIDENT (0 module credite par la seule prose), donc ce durcissement ne change aucun
    verdict AUJOURD'HUI -- il ferme la porte, il ne repare pas un faux. C'est dit pour que personne
    ne le lise comme la cause du rouge."""
    out = set()
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            out.add(f.id)
        elif isinstance(f, ast.Attribute):
            out.add(f.attr)
    return out


def _recenser_les_lecteurs():
    """{module: {"foyer", "voisin", "cite"}} sur TOUT le paquet `noncomparable`, par AST."""
    base = PYDIR / "engine" / "playbook" / "noncomparable"
    out = {}
    for f in sorted(base.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        ap = _appels(ast.parse(src))
        out[f.stem] = {"foyer": "_enemy_killed_by_normal_attack" in ap,
                       "voisin": FOYER_VOISIN in ap,
                       "cite": SYMBOLE_DU_GATE in src}
    return out


def test_le_recensement_des_lecteurs_du_foyer_est_EXHAUSTIF():
    """Le rayon de souffle se MESURE -- mais il se mesure par un CRITERE, pas par un effectif.

    L'assertion d'origine gelait TROIS noms. Elle est tombee au quatrieme port legitime
    (`graviton_rifle`, #975) -- alors meme que la docstring de ce fichier NOMME
    `GravitonRiflePlaybook$$ShouldEvaluate` en tete des xrefs natives. La cause n'est pas le
    chiffre : **TROIS xrefs natives ne font pas TROIS modules Python**, puisque
    `VexillaMagnificaPlaybook$$ShouldEvaluate` est le corps COMDAT que `HammerOfWrath` partage.
    L'effectif Python n'est donc contraint par rien de stable.

    Ce qui EST stable, et que les quatre crans ci-dessous gardent :

      1. NON-RETRECISSEMENT -- les lecteurs attestes le restent (perdre le foyer viderait
         `test_les_trois_should_evaluate_portes_passent_par_LE_MEME_foyer`) ;
      2. ADOSSEMENT NATIF -- tout lecteur, y compris un futur cinquieme, CITE le symbole du corps
         natif qu'il porte. C'est ce qui remplace l'effectif fige : un port fait sans lire le
         decompile ne passe pas ;
      3. NON-CONFUSION -- aucun module ne lit ce foyer ET celui de `WillNormalAttackKill` (l'AUTRE
         corps natif, par CIBLE, dont les crans #372 vivent dans `engine.playbook.base`). C'est le
         fond de ce test : `stormcaller`, `bloody_fury`, `vigilance_eternal`, `black_rage` et
         `kill_maim_burn` ne sont PAS de ce gisement ;
      4. NON-VACUITE -- le balayage a bien visite le paquet."""
    rec = _recenser_les_lecteurs()
    # 4. NON-VACUITE D'ABORD : les trois assertions qui suivent portent sur des ensembles, et un
    #    paquet non visite les rendrait toutes vraies SANS RIEN AVOIR MESURE.
    assert len(rec) >= 20, (
        "le balayage n'a visite que %d module(s) de `noncomparable` -- les criteres ci-dessous "
        "seraient satisfaits sans rien avoir lu" % len(rec))
    lecteurs = {m for m, d in rec.items() if d["foyer"]}
    assert lecteurs, "aucun lecteur du foyer -- le gate a-t-il ete recable ?"

    # 1. NON-RETRECISSEMENT.
    perdus = set(LECTEURS_ATTESTES) - lecteurs
    assert not perdus, (
        "lecteur(s) atteste(s) qui n'appelle(nt) plus le foyer : %s -- le gate a ete recable ou "
        "duplique ; les bras de ce fichier ne mesurent alors plus ce qu'ils croient" % sorted(perdus))

    # 2. ADOSSEMENT NATIF -- le critere qui remplace l'effectif fige.
    sans_symbole = sorted(m for m in lecteurs if not rec[m]["cite"])
    assert not sans_symbole, (
        "lecteur(s) du foyer qui ne cite(nt) PAS `%s` : %s -- un port de ce gate se lit dans le "
        "decompile ; sans la citation, rien n'atteste que la xref native a ete verifiee."
        % (SYMBOLE_DU_GATE, sans_symbole))

    # 3. NON-CONFUSION -- les deux corps natifs ne se melangent pas.
    melange = sorted(m for m, d in rec.items() if d["foyer"] and d["voisin"])
    assert not melange, (
        "module(s) lisant les DEUX foyers : %s -- `%s` est l'AUTRE corps natif "
        "(`WillNormalAttackKill`, par CIBLE) ; les confondre fait croire le gisement plus large "
        "qu'il n'est, et c'est l'erreur que la fiche #566 §6 avait commise (SIX lecteurs annonces)"
        % (melange, FOYER_VOISIN))


def test_CONTRE_EPREUVE_le_critere_de_lecteur_est_AST_et_non_TEXTUEL():
    """SANS CE TEST, LE DURCISSEMENT AST DU PRECEDENT NE SERAIT GARDE PAR RIEN -- il resterait vert
    si quelqu'un remettait un `re.search` sur la source.

    On soumet au recenseur une source dont la DOCSTRING nomme le foyer avec ses parentheses, sans
    l'appeler. Le critere textuel d'origine la classerait lectrice ; le critere AST ne doit pas."""
    prose = ast.parse(
        'def _piege(ctx):\n'
        '    """Ce module NE lit PAS le gate : il ne fait aucun\n'
        '    `_enemy_killed_by_normal_attack(ctx)`, et ne touche pas non plus a\n'
        '    `will_normal_attack_kill(ctx, cible)`. Il le DIT, il ne le FAIT pas."""\n'
        '    return False\n')
    assert "_enemy_killed_by_normal_attack" not in _appels(prose), (
        "le foyer est credite depuis une DOCSTRING -- le critere est redevenu textuel")
    assert FOYER_VOISIN not in _appels(prose)
    # ...et la contre-epreuve de la contre-epreuve : l'APPEL REEL, lui, doit compter.
    vrai = ast.parse('def _vrai(ctx):\n    return _enemy_killed_by_normal_attack(ctx)\n')
    assert "_enemy_killed_by_normal_attack" in _appels(vrai), (
        "le critere AST ne voit plus l'appel ECRIT -- il ne mesurerait plus rien")
