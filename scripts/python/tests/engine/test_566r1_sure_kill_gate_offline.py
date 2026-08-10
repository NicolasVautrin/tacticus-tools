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
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "frida/hooks/features/ai-step/projection.ts",
        "frida/hooks/game/damage-prediction.ts",
    ),
    "build": False,
    "toujours": False,
    "raison": "Plans SYNTHETIQUES : aucun ordinal ni offset n'est lu du build. Le verdict ne "
              "depend que du foyer Python et du champ que le hook publie.",
}

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
    """`HammerOfWrath` (1153), `VexillaMagnifica` (1183) et `SupremeCommander` (1160) appellent tous
    `_enemy_killed_by_normal_attack`. Substituer le FOYER doit donc renverser les trois d'un coup --
    trois corps auraient ete un fork du meme corps natif (`BasePlaybook$$ShouldEvaluate` COMDAT).

    `SupremeCommander` a d'AUTRES gates en aval (`AllDeadUnits`, `FillUpStatComponent`) : on ne
    verifie donc chez lui QUE le sens qui court-circuite (`gate vrai => False`)."""
    from engine.playbook.noncomparable.hammer_of_wrath import HammerOfWrathPlaybook
    from engine.playbook.noncomparable.supreme_commander import SupremeCommanderPlaybook
    from engine.playbook.noncomparable.vexilla_magnifica import VexillaMagnificaPlaybook

    sure = _ctx([{"col": 1, "row": 1, "dmgMin": 10, "dmgMax": 10, "killSure": True}])
    pas_sure = _ctx([{"col": 1, "row": 1, "dmgMin": 50, "dmgMax": 50, "killSure": False}])
    for cls in (HammerOfWrathPlaybook, VexillaMagnificaPlaybook, SupremeCommanderPlaybook):
        assert cls().should_evaluate(sure) is False, cls.__name__
    for cls in (HammerOfWrathPlaybook, VexillaMagnificaPlaybook):
        assert cls().should_evaluate(pas_sure) is True, cls.__name__


def test_le_recensement_des_lecteurs_du_foyer_est_EXHAUSTIF():
    """Le rayon de souffle se MESURE. Un balayage du paquet `noncomparable` doit rendre EXACTEMENT
    les trois modules ci-dessus -- ni `bloody_fury`, ni `stormcaller`, ni `vigilance_eternal`, ni
    `black_rage` (que la fiche #566 §6 comptait), qui n'ont pas ce gate cote NATIF non plus.

    `stormcaller` et `kill_maim_burn` lisent l'AUTRE corps natif -- `WillNormalAttackKill`, par
    CIBLE --, dont le foyer (`engine.playbook.base.will_normal_attack_kill`) porte deja les deux
    crans #372. Les confondre ferait croire le gisement plus large qu'il n'est."""
    import re
    base = PYDIR / "engine" / "playbook" / "noncomparable"
    lecteurs = set()
    for f in sorted(base.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        # L'APPEL, pas l'import : `hammer_of_wrath` se cite lui-meme dans ses docstrings.
        if re.search(r"_enemy_killed_by_normal_attack\s*\(", src):
            lecteurs.add(f.stem)
    assert lecteurs == {"hammer_of_wrath", "supreme_commander", "vexilla_magnifica"}, lecteurs
