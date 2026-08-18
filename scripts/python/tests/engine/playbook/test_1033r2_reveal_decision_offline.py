"""CLIQUET `#1033-r2` -- la face DECISION de `1107 Reveal` (`RevealPlaybook`).

Chaque etage garde UNE lecture de `IdunBattle.AI.Playbook.Loki.RevealPlaybook$$
EvaluateNonComparable` (relu sur le build `t6dpr4k06g`), et chacun a ete VU ROUGE par mutation
(`probe_1033r2_mutants.py`). Aucun n'est un seuil.

    ETAGE 1  le playbook est au REGISTRE NonComparable, avec ses constantes du `.cctor`
    ETAGE 2  l'utilite est la CONSTANTE `Fix64.op_Implicit(1)` -- elle ne lit NI la cible NI la
             position ; c'est ce qui separe 1107 de `VexillaMagnifica`/`EuphoricStrikes`, dont le
             corps a la MEME forme mais dont l'utilite est `GetStat(cible, 5 = Health)`
    ETAGE 3  la borne du `Bucket` est INCLUSIVE -- l'utilite EGALE `MIN_UTILITY` et le candidat
             SORT quand meme. C'est le cran vital : lire le gate en `>` strict ferait de ce
             playbook un MORT SILENCIEUX (0 candidat, aucune erreur)
    ETAGE 4  le gate `WillNormalAttackKill` ECARTE la cible, dans les DEUX sens
    ETAGE 5  a utilite plate, l'argmax est la PREMIERE position de l'ordre natif -- l'ORIGINE
    ETAGE 6  `ShouldEvaluate` n'est PAS surcharge, et c'est une MESURE (`probe_552r3_slot4_declare`)
    ETAGE 7  la trace de construction ne porte QUE l'event du gate (1107 n'a aucun degat)
    ETAGE 8  1107 est SORTIE du registre de dette de `probe_1021` -- c'est le CRAN A qui la garde

100 % offline : aucun runner, aucun RPC. ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre ETROIT et DERIVE : les fichiers dont une edition peut RENDRE FAUX ce que ce cliquet
#: fige. Pas de glob `scripts/python/**`, qui serait un `toujours: True` deguise.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/noncomparable/reveal.py",
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/playbook/base.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/probe_1021_face_decision_au_registre.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Ce volet ne lit ni le binaire ni les tables du build : il fige des valeurs du PORT "
              "(constantes du `.cctor` recopiees, polarite du gate `AddAction`, foyer du gate "
              "`WillNormalAttackKill`, ordre origine-d'abord, sortie du registre de dette). Le "
              "seul axe qui les perime est une edition de ces fichiers-la. `build: False` parce "
              "qu'aucune grandeur ici n'est derivee d'une adresse ni d'un dump -- la verification "
              "que la METADATA dit toujours la meme chose est le travail de "
              "`probe_552r3_slot4_declare`, qui porte `build: True`.",
}

from engine.entities.active_ability_type import ActiveAbilityType
from engine.playbook.noncomparable import PLAYBOOKS, is_noncomp, playbook_for
from engine.playbook.noncomparable._base import NCContext, NonComparablePlaybook, native_priority
from engine.playbook.noncomparable.reveal import RevealPlaybook

_REVEAL = int(ActiveAbilityType.Reveal)          # 0x453 = 1107


def _ctx(reach=((0, 0),), cibles=(7,), origin=(0, 0), **kw) -> NCContext:
    """Un contexte MINIMAL ou la paire (1107, cible) est castable depuis chaque position de
    `reach`. `cast_from_tiles=None` -> `eligible_positions` retombe sur les tuiles `ranked`, ce
    qui est exactement le repli NOMME du foyer `cast_positions`."""
    evals = [{"abilityId": _REVEAL, "targetId": t, "rankCount": len(reach),
              "ranked": [{"col": c, "row": r} for (c, r) in reach]} for t in cibles]
    champs = dict(uid=1, origin=origin, reach_nc=list(reach), epos=[], fpos=[],
                  plan={"evals": evals}, hp_cur_by_id={t: 1000 for t in cibles})
    champs.update(kw)
    return NCContext(**champs)


# ============================================================================================
#  ETAGE 1 -- le registre
# ============================================================================================

def test_etage1_1107_au_registre_noncomparable():
    """`...RevealPlaybook$$.ctor` passe `0x453` ; `$$.cctor` ecrit `Fix64.op_Implicit(1)` dans
    `statics[0]`, que `EvaluateNonComparable` relit comme `minUtility` du `Bucket`.

    ⚠ Le `.ctor` decompile NOMME `ComparablePlaybook<T>..ctor` -- corps gshared DEDUPLIQUE, donc
    mislabele. Ce qui range 1107 du cote NonComparable est sa METHODE PROPRE
    (`EvaluateNonComparable`), pas le nom du ctor."""
    pb = playbook_for(_REVEAL)
    assert pb is not None and isinstance(pb, RevealPlaybook)
    assert is_noncomp(_REVEAL)
    assert pb.ABILITY_ID == _REVEAL == 0x453
    assert pb.MIN_UTILITY == 1.0
    assert pb.PRIORITY == 0 == native_priority(_REVEAL)   # hors `NATIVE_PRIORITY` (sweep #170)
    assert PLAYBOOKS[_REVEAL] is pb


# ============================================================================================
#  ETAGE 2 -- l'utilite est une CONSTANTE
# ============================================================================================

def test_etage2_utilite_constante_independante_de_la_cible_et_de_la_position():
    """`GenerateAction(casterPosition, e.Target, Fix64.op_Implicit(1))` -- le troisieme argument
    est un LITTERAL reconstruit a chaque iteration, pas une lecture.

    Le mutant que ce cran attrape est le plus tentant de tous : recopier le voisin de forme
    (`VexillaMagnifica`, `EuphoricStrikes`, `DaemonicPatrons` -- meme squelette, meme `MIN_UTILITY`)
    et rendre `float(ctx.hp_cur_by_id[target])`. La structure resterait plausible ; la DECISION
    changerait des que deux cibles survivent au gate."""
    pb = playbook_for(_REVEAL)
    ctx = _ctx(reach=((0, 0), (1, 1)), cibles=(7, 9))
    ctx.hp_cur_by_id = {7: 10, 9: 9999}
    vus = {pb.evaluate_non_comparable(t, tgt, ctx)
           for t in ((0, 0), (1, 1)) for tgt in (7, 9)}
    assert vus == {1.0}, (
        "l'utilite de 1107 est la CONSTANTE Fix64(1) : elle ne doit varier ni avec la cible ni "
        "avec la position ; mesure : %r" % (sorted(v for v in vus if v is not None),))


# ============================================================================================
#  ETAGE 3 -- LA BORNE EST INCLUSIVE (le cran vital)
# ============================================================================================

def test_etage3_utilite_egale_a_la_borne_le_candidat_SORT():
    """`Bucket$$AddAction` -> son helper : `minUtility.HasValue == false` accepte tout, sinon
    `action.Utility >= minUtility.Value` (`op_GreaterThanOrEqual`, LU sur le build courant).

    Ici utilite == `MIN_UTILITY` == 1 : le natif ACCEPTE. Un port qui lirait le gate en `>` strict
    -- ou qui remonterait `MIN_UTILITY` au-dessus de 1 -- ne produirait JAMAIS de candidat, sans
    lever la moindre erreur. C'est exactement le no-op silencieux d'`IronkinSteeljack` (#971)."""
    pb = playbook_for(_REVEAL)
    cands = pb.generate_candidates(_ctx())
    assert len(cands) == 1, (
        "utilite (1.0) EGALE a MIN_UTILITY (1.0) : le natif accepte (`>=`), donc le port doit "
        "emettre EXACTEMENT un candidat ; mesure : %r" % (cands,))
    assert cands[0]["ability"] == _REVEAL
    assert cands[0]["pred"] == 1.0 == pb.MIN_UTILITY


# ============================================================================================
#  ETAGE 4 -- le gate `WillNormalAttackKill`, DANS LES DEUX SENS
# ============================================================================================

def test_etage4_le_gate_ecarte_la_cible_sure_kill(monkeypatch):
    """`if (BasePlaybook$$WillNormalAttackKill(caster, e.Target, casterPosition.MainTile))
    continue;` -- le natif ne gaspille pas le marquage sur une unite que sa frappe de base acheve.

    Le FOYER est `engine.playbook.base.will_normal_attack_kill` (partage avec les quinze playbooks
    de `normal_attack_kill_gate` et la route NonComparable) : c'est LUI qu'on substitue, en FORME B
    -- une liaison `from X import f` au niveau module rendrait ce patch INERTE."""
    pb = playbook_for(_REVEAL)
    ctx = _ctx(cibles=(7, 9))

    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill",
                        lambda c, t, p: int(t) == 7)
    # la cible 7 est ECARTEE, la 9 survit -> il reste un candidat, et c'est la 9
    assert pb.evaluate_non_comparable((0, 0), 7, ctx) is None
    assert pb.evaluate_non_comparable((0, 0), 9, ctx) == 1.0
    assert [c["target"] for c in pb.generate_candidates(ctx)] == [9]

    # TOUTES sure-kill -> le bucket natif est VIDE, donc le port ne propose RIEN
    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill", lambda c, t, p: True)
    assert pb.generate_candidates(ctx) == []

    # AUCUNE -> les deux passent, et c'est la PREMIERE enumeree qui gagne (tie, keep-first)
    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill", lambda c, t, p: False)
    assert [c["target"] for c in pb.generate_candidates(ctx)] == [7]


# ============================================================================================
#  ETAGE 5 -- l'ordre : ORIGINE d'abord
# ============================================================================================

def test_etage5_argmax_plat_reste_a_l_ORIGINE(monkeypatch):
    """`ctx.reach_nc` porte la position COURANTE EN TETE
    (`BattleQuery$$GetCurrentAndMovablePositionsFor`) et `Bucket$$AddAction` ne remplace que sur
    `op_GreaterThan` STRICT : a utilite plate, le natif caste SANS BOUGER.

    Et le gate, lui, est POSITIONNEL (`WillNormalAttackKill` predit la normale DEPUIS la tuile
    candidate) : si la cible est sure-kill depuis l'origine mais pas depuis une tuile de move, le
    natif BOUGE. Les deux branches sont exercees ici."""
    pb = playbook_for(_REVEAL)
    ctx = _ctx(reach=((0, 0), (1, 1)), cibles=(7,))

    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill", lambda c, t, p: False)
    cands = pb.generate_candidates(ctx)
    assert cands and cands[0]["to"] is None, (
        "utilite plate : la 1re position de `reach_nc` -- l'ORIGINE -- gagne le tie, donc "
        "`to` doit valoir None ; mesure : %r" % (cands,))

    # le gate mord A L'ORIGINE seulement -> la seule position survivante est la tuile de move
    monkeypatch.setattr("engine.playbook.base.will_normal_attack_kill",
                        lambda c, t, p: tuple(p) == (0, 0))
    cands = pb.generate_candidates(ctx)
    assert cands and cands[0]["to"] == (1, 1), (
        "le gate est POSITIONNEL : sure-kill depuis l'origine seulement -> le natif bouge ; "
        "mesure : %r" % (cands,))


# ============================================================================================
#  ETAGE 6 -- pas de surcharge du slot 4, et c'est MESURE
# ============================================================================================

def test_etage6_should_evaluate_reste_le_DEFAUT_de_base():
    """`IdunBattle.AI.Playbook.Loki.RevealPlaybook` DECLARE exactement
    `{.ctor, .cctor, EvaluateNonComparable}` dans `global-metadata.dat` -- ni `ShouldEvaluate` ni
    `GetUseProbability` (`probe_552r3_slot4_declare`, temoin BILATERAL 8/8).

    ⚠ Ce n'est PAS une deduction d'absence dans les tables de symboles : celles-ci sont indexees
    par ADRESSE et IL2CPP deduplique les corps -- c'est ainsi que le slot 4 de
    `VexillaMagnificaPlaybook` avait ete rate puis retrouve LIVE (#46). La metadata, elle, decrit
    des DEFINITIONS.

    Le cran fige donc la CONSEQUENCE : surcharger l'un des deux etages ici serait ecrire un gate
    que le natif n'a pas."""
    assert type(playbook_for(_REVEAL)).should_evaluate is NonComparablePlaybook.should_evaluate
    assert type(playbook_for(_REVEAL)).use_probability is NonComparablePlaybook.use_probability
    assert playbook_for(_REVEAL).should_evaluate(_ctx()) is True


# ============================================================================================
#  ETAGE 7 -- la trace de construction
# ============================================================================================

def test_etage7_trace_le_gate_et_rien_d_autre():
    """`damage_predictions` rend ce que l'oracle `ncPlaybookPredict` VOIT, pas l'utilite : le
    trampoline est pose sur `ProbableDamageEvent$$.ctor`, donc il capte l'event que le GATE
    construit. 1107 n'en construit aucun autre -- `gameconfig.abilities.Reveal` n'a ni `minDmg`,
    ni `nrOfHits`, ni `damageProfile`, donc le tag `"ability"` ne peut pas apparaitre.

    Predicteur absent (`ctx.scene is None`) -> `[]` : on ne fabrique pas une prediction depuis une
    non-mesure."""
    pb = playbook_for(_REVEAL)
    assert pb.damage_predictions((0, 0), 7, _ctx()) == []


# ============================================================================================
#  ETAGE 8 -- la ligne de dette est RETIREE (c'est le CRAN A qui prend le relais)
# ============================================================================================

def test_etage8_1107_est_sortie_du_registre_de_dette():
    """Une face DECISION portee qui resterait inscrite `SANS_VERDICT` dans `probe_1021.DETTE`
    serait protegee par sa VIEILLE ligne : si le port disparaissait, le CRAN A resterait muet.
    Retirer la ligne est ce qui fait tomber 1107 sous le cran -- donc ce qui la garde DESORMAIS."""
    from probe_1021_face_decision_au_registre import DETTE
    assert _REVEAL not in DETTE, (
        "1107 est PORTEE : sa ligne de dette doit etre retiree de `probe_1021.DETTE`, sinon le "
        "CRAN A ne la garde pas")
