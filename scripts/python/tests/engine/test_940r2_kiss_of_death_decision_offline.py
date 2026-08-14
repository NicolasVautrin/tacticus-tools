"""GARDE de la face DECISION de `1108 KissOfDeath` (`#940-r2`).

Ce que ce fichier garde, et pourquoi CHAQUE etage existe :

  * ETAGE 1 -- l'entree au registre `PLAYBOOKS` avec son seuil LU (`Fix64.op_Implicit(2)` INLINE
    dans `KissOfDeathPlaybook$$EvaluateNonComparable` : la classe native ne declare que `..ctor`
    et `EvaluateNonComparable`, donc AUCUN `.cctor` ne pourrait le porter).
  * ETAGE 2 -- la FORMULE, cran par cran, chacun avec le mutant qu'il tue.
  * ETAGE 3 -- **le cran que le voisinage de forme rendrait invisible** : 1108 et 1019 sont deux
    corps natifs DISTINCTS qui calculent la MEME chose. Un test qui ne verifierait que 1108
    passerait si le port avait ete cable sur 1019 par erreur (et reciproquement) ; on garde donc
    l'EGALITE des deux faces sur un temoin NON DEGENERE, **et** la distinction de leurs identites.
  * ETAGE 4 -- le foyer PARTAGE : `engine.battle_query.get_chained_units` est le mirror unique de
    `IdunBattle.Core.Services.BattleQuery$$GetChainedUnitsInternal`, et les DEUX playbooks doivent
    passer par lui (un fork d'adjacence est exactement ce que #419-r1-tr14 a evite).

⚠ TEMOIN NON DEGENERE. Les scenarios sont choisis pour que les regimes SEPARENT : une cible
isolee (1, sous le seuil), une chaine de 3 (3, au-dessus), une chaine coupee par un ennemi (1).
Si le natif ne separait pas ces regimes, l'accord ne prouverait rien.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.entities.active_ability_type import ActiveAbilityType
from engine.playbook.noncomparable import PLAYBOOKS
from engine.playbook.noncomparable._base import NCContext

DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE, pas un aveu : ce fichier importe le registre
    # `PLAYBOOKS` (donc tout `engine.playbook.noncomparable`, ses ~95 modules d'ability) ET
    # `engine.battle_query`, foyer partage dont la fermeture d'import touche la geometrie, le
    # voisinage stocke et la porte d'elevation. Un perimetre etroit ici serait un FAUX VERT :
    # l'etage 4 mute justement un module TIERS (`bq.get_chained_units`) pour prouver que les deux
    # faces l'empruntent.
    # ⚠ Les DEUX formes sont necessaires : le `**/` d'un glob exige un SEGMENT, donc
    # `scripts/python/**/*.py` ne voit PAS `scripts/python/hexgeo.py`, que ce fichier importe.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` -- aucune valeur n'est figee depuis le binaire au sens ou un changement de
    # build la perimerait : le seuil `2` et le litteral `onlyFriends = 1` sont LUS au decompile et
    # transcrits, et le substrat est `obs_units`, pas une table de symboles. Un renumerotage de
    # `ActiveAbilityType` serait vu par `probe_313`, pas ici.
    "build": False,
    # offline pur, aucun runner, < 3 s.
    "toujours": True,
    "raison": "Garde OFFLINE de la face DECISION de 1108 KissOfDeath (#940-r2) : l'entree au "
              "registre avec son seuil INLINE, la formule terme a terme (racine incluse, "
              "transitivite, arret au changement d'equipe, morts, independance a la position), "
              "l'EGALITE avec la face jumelle 1019 sur un temoin non degenere ET la DISTINCTION "
              "de leurs identites, enfin le partage effectif du foyer "
              "`engine.battle_query.get_chained_units` (mirror unique de "
              "`IdunBattle.Core.Services.BattleQuery$$GetChainedUnitsInternal`).",
}

KISS = int(ActiveAbilityType.KissOfDeath)     # 0x454 = 1108 (argument du ctor natif)
STORM = int(ActiveAbilityType.StormOfWrath)   # 0x3fb = 1019 -- le JUMEAU au decompile

#: `visualId` reel, DERIVE du gameconfig : aucun trait ne participe a cette formule (le natif ne
#: lit ni stat ni trait -- c'est ce qui rend la GREFFE legitime, cf. la docstring du port).
ANY_UNIT = "tyranSmnWarrior"


def _voisins(p):
    """Repli GEOMETRIQUE de `battle_query.is_adjacent` quand `neigh_by_pos` est absent. Ces tests
    gardent la FORMULE, pas le substrat de voisinage (qui a son propre cliquet, #433-r4-r1-r4-r2)."""
    return [(q[0], q[1]) for q in hexgeo.neighbors(p[0], p[1])]


def _ctx(**kw) -> NCContext:
    base = dict(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={}, hp_cur_by_id={})
    base.update(kw)
    return NCContext(**base)


def _obs(sq, team, pos, dead=False):
    return {"squadId": sq, "teamId": team, "visualId": ANY_UNIT,
            "col": pos[0], "row": pos[1], "isDead": dead}


def _ctx_chaine(chaine):
    """File d'unites deux a deux adjacentes depuis `(0, 0)` ; `chaine` = la liste des equipes, la
    PREMIERE entree etant la cible. Rend `(ctx, squadId de la cible)`."""
    pos = [(0, 0)]
    while len(pos) < len(chaine):
        pos.append(_voisins(pos[-1])[0])
    obs = [_obs(100 + i, t, p) for i, (t, p) in enumerate(zip(chaine, pos))]
    return _ctx(uid=1, obs_units=obs), 100


# =============================================================================================
# ETAGE 1 -- AU REGISTRE, AVEC LE SEUIL LU
# =============================================================================================
def test_1108_est_inscrit_au_registre_avec_sa_classe_propre():
    """`metadata/active_playbook_builders.tsv` : `active 1108
    IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook`. Le playbook est enregistre PAR ABILITY --
    c'est ce qui autorise la confrontation par GREFFE, ses deux seuls porteurs etant npc/summon."""
    assert KISS in PLAYBOOKS, "1108 doit etre au registre NonComparable"
    assert type(PLAYBOOKS[KISS]).__name__ == "KissOfDeathPlaybook"
    assert PLAYBOOKS[KISS].ABILITY_ID == 1108 == 0x454


def test_le_seuil_est_le_litteral_INLINE_de_la_methode():
    """`Bucket<T>$$.ctor(0, Nullable(Fix64.op_Implicit(2)))`. MUTANT qui mord : un seuil a 0 ou 1
    laisserait passer une cible ISOLEE (utilite 1), donc le Harlequin piquerait un solitaire --
    exactement ce que le natif refuse."""
    assert PLAYBOOKS[KISS].MIN_UTILITY == 2.0
    assert PLAYBOOKS[KISS].PRIORITY == 0     # hors `NATIVE_PRIORITY` (sweep #170)


# =============================================================================================
# ETAGE 2 -- LA FORMULE
# =============================================================================================
def test_une_cible_ISOLEE_vaut_UN_et_reste_sous_le_seuil():
    """`GetChainedUnitsInternal` fait `adj.Add(tile)` AVANT d'enumerer : la cible entre dans le set
    des le premier niveau (`IsFriend(cible, cible)` est vrai). Une cible isolee vaut donc **1**,
    jamais 0.

    MUTANT qui mord : ne pas inclure la racine rendrait 0 ici et 1 sur une paire -- plus aucun cast
    de 1108 ne serait jamais propose."""
    pb = PLAYBOOKS[KISS]
    ctx, cible = _ctx_chaine([2])
    assert pb.evaluate_non_comparable((0, 0), cible, ctx) == 1.0
    assert pb.evaluate_non_comparable((0, 0), cible, ctx) < pb.MIN_UTILITY


def test_la_chaine_est_TRANSITIVE():
    """La recursion propage de proche en proche : trois unites de la MEME equipe alignees valent 3,
    meme si la troisieme n'est pas adjacente a la cible.

    MUTANT qui mord : un comptage d'adjacence SIMPLE (sans recursion) rendrait 2."""
    pb = PLAYBOOKS[KISS]
    ctx, cible = _ctx_chaine([2, 2, 2])
    assert pb.evaluate_non_comparable((0, 0), cible, ctx) == 3.0


def test_la_chaine_s_arrete_au_changement_d_equipe():
    """`onlyFriends = true` -- le litteral `1` du call-site `(cible, 1, 0)`. La chaine ne traverse
    pas un ennemi DE LA CIBLE et ne reprend donc pas de l'autre cote.

    ⚠ C'est le cran qui distingue cette face de la face COMBAT (#940), dont le lambda de saut vise
    les ENNEMIS DU CASTER : la dissymetrie est NATIVE, le port la transcrit sans la reconcilier.

    MUTANT qui mord : `onlyFriends = false` compterait 3 ici au lieu de 1."""
    pb = PLAYBOOKS[KISS]
    ctx, cible = _ctx_chaine([2, 1, 2])
    assert pb.evaluate_non_comparable((0, 0), cible, ctx) == 1.0


def test_les_MORTS_coupent_la_chaine():
    """`GetUnit(tile)` passe par `TileContentComponent$$IsFilled` : une depouille ne remplit plus sa
    tuile. Substrat `obs_units.isDead` (`decisionView`, lui, GARDE les morts)."""
    pb = PLAYBOOKS[KISS]
    ctx, cible = _ctx_chaine([2, 2, 2])
    for u in ctx.obs_units:
        if u["squadId"] == cible + 1:
            u["isDead"] = True
    assert pb.evaluate_non_comparable((0, 0), cible, ctx) == 1.0


def test_le_terme_est_POSITION_INDEPENDANT():
    """La tuile candidate du caster n'entre pas dans la formule -- le natif ne la passe qu'a
    `GenerateAction`. `Bucket$$AddAction` ne remplacant que sur `>` STRICT, le caster reste donc en
    place des qu'une cible atteignable depuis l'origine atteint le maximum."""
    pb = PLAYBOOKS[KISS]
    ctx, cible = _ctx_chaine([2, 2, 2])
    valeurs = {pb.evaluate_non_comparable(P, cible, ctx) for P in [(0, 0), (5, 5), (9, 1)]}
    assert valeurs == {3.0}, "la tuile du caster ne doit RIEN changer"


def test_aucune_prediction_de_degat():
    """`KissOfDeathPlaybook` ne declare que `..ctor` et `EvaluateNonComparable` (`frida/methods.tsv`
    comme `ghidra/functions.tsv`) : ni `MakeDamagePredictions` ni gate `WillNormalAttackKill`. La
    sequence que l'oracle `ncPlaybookPredict` voit est VIDE -- resultat, pas defaut."""
    assert PLAYBOOKS[KISS].damage_predictions((0, 0), 1, _ctx()) == []


# =============================================================================================
# ETAGE 3 -- LE CRAN QUE LE VOISINAGE DE FORME RENDRAIT INVISIBLE
# =============================================================================================
@pytest.mark.parametrize("chaine,attendu", [
    ([2], 1.0),
    ([2, 2], 2.0),
    ([2, 2, 2], 3.0),
    ([2, 1, 2], 1.0),
])
def test_1108_et_1019_rendent_LE_MEME_terme(chaine, attendu):
    """Les deux corps natifs sont DISTINCTS (adresses differentes, pas une fusion d'ICF) et
    calculent la MEME chose : memes pointeurs de metadata-usage, meme `Fix64(2)`, meme slot 16
    d'`IBattleQuery`, memes litteraux `(cible, 1, 0)`.

    ⚠ TEMOIN NON DEGENERE, et c'est le point : les quatre cas rendent QUATRE regimes dont trois
    valeurs distinctes (1, 2, 3) -- un accord sur un jeu constant ne prouverait rien."""
    ctx, cible = _ctx_chaine(chaine)
    assert PLAYBOOKS[KISS].evaluate_non_comparable((0, 0), cible, ctx) == attendu
    assert PLAYBOOKS[STORM].evaluate_non_comparable((0, 0), cible, ctx) == attendu


def test_les_deux_playbooks_restent_DEUX_entrees_DISTINCTES():
    """Le pendant du test precedent : l'egalite des TERMES ne doit pas devenir une confusion des
    IDENTITES. `classes.tsv` porte deux classes, `active_playbook_builders.tsv` deux entrees.

    MUTANT qui mord : cabler `StormOfWrathPlaybook()` sous la cle 1108 (ou l'inverse) passerait
    TOUS les tests de terme ci-dessus."""
    assert PLAYBOOKS[KISS] is not PLAYBOOKS[STORM]
    assert type(PLAYBOOKS[KISS]).__name__ == "KissOfDeathPlaybook"
    assert type(PLAYBOOKS[STORM]).__name__ == "StormOfWrathPlaybook"
    assert PLAYBOOKS[KISS].ABILITY_ID != PLAYBOOKS[STORM].ABILITY_ID


# =============================================================================================
# ETAGE 4 -- LE FOYER EST PARTAGE (pas de fork d'adjacence)
# =============================================================================================
def test_les_deux_faces_passent_par_LE_MEME_foyer():
    """`IdunBattle.Core.Services.BattleQuery$$GetChainedUnitsInternal` a UN corps natif ; le port
    doit en avoir UN aussi. On le verifie par MUTATION du foyer : neutraliser
    `engine.battle_query.get_chained_units` doit eteindre les DEUX faces.

    HISSAGE EN FORME B : les deux modules font `from engine import battle_query as bq` puis
    `bq.get_chained_units(...)` -- un binding de MODULE, donc `monkeypatch.setattr` MORD (la forme
    A `from X import foo` ne mordrait pas, cf. #484)."""
    import engine.battle_query as bq
    ctx, cible = _ctx_chaine([2, 2, 2])
    assert PLAYBOOKS[KISS].evaluate_non_comparable((0, 0), cible, ctx) == 3.0
    assert PLAYBOOKS[STORM].evaluate_non_comparable((0, 0), cible, ctx) == 3.0

    reel = bq.get_chained_units
    try:
        bq.get_chained_units = lambda *a, **k: set()
        assert PLAYBOOKS[KISS].evaluate_non_comparable((0, 0), cible, ctx) == 0.0, \
            "1108 n'emprunte PAS le foyer partage -- fork d'adjacence"
        assert PLAYBOOKS[STORM].evaluate_non_comparable((0, 0), cible, ctx) == 0.0, \
            "1019 n'emprunte PAS le foyer partage -- fork d'adjacence"
    finally:
        bq.get_chained_units = reel
    assert PLAYBOOKS[KISS].evaluate_non_comparable((0, 0), cible, ctx) == 3.0
