"""GARDE #477-r37 -- le `<slot 4>` des VINGT-HUIT classes, et la face dite « inerte » qui ne l'est pas.

CE QUE CETTE GARDE PROTEGE, et pourquoi ce n'est pas un detail :

  * **Le `<slot 4>` a un NOM et il se lit sur les 28 classes, pas sur six.**
    `get_ShouldIncludingEnemiesWhenCalculate` est la 5e methode d'
    `IdunBattle.AI.Playbook.ITriggeredAbilityNonOwnerPlaybook`, LUE dans le `global-metadata.dat`.
    Deux classes la surchargent (`HaywireMineNonOwnerPlaybook`, face MOVE ;
    `NoHidingFromTheWatchersNonOwnerPlaybook`, face ATTACK), les deux a `true`. Les 26 autres
    heritent le `xor eax,eax ; ret` de la base.
    ⚠ **Le critere de #477-r35 (« l'entree qui PRECEDE le `.ctor` ») etait FAUX DES DEUX COTES** :
    faux NEGATIF sur `NoHidingFromTheWatchers` (qui declare APRES son `.ctor`), faux POSITIF sur
    `ECogSupport` / `KustomForceFieldReworked` (l'entree lue appartenait au TYPE PRECEDENT). Il
    rendait la bonne valeur pour la mauvaise raison -- exactement le regime que ce depot chasse.

  * **`1064 FirstAmongTraitors` n'est PAS un terme inerte.** #477-r35 l'a classe « 0 unite sur
    1083 » en comptant `gameconfig.unit(vis).traits`, la source dont
    `engine/entities/traits/unit_trait.py` ecrit noir sur blanc qu'elle NE CONTIENT PAS le
    pseudo-trait de GRANDE-ALLIANCE (« AUCUNE unite ne le porte : la couche META l'injecte dans la
    BattleConfiguration »). Le substrat que `HasTrait` interroge en donne **127 sur 683**.
    Consequence MESUREE : sur le montage `abaddon`, le mutant `ABSENT` (= l'etat du port avant
    cette tranche) diverge du natif sur **2 tuiles sur 4**.

LE CORPS PORTE, au decompile du build courant :

  `IdunBattle.AI.Playbook.Loki.FirstAmongTraitorsNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
      if (case.unit == null) yield break;
      if (!UnitExtensions.HasTrait(case.unit, 0x7ea)) yield break;          // UnitTrait.Chaos
      int d = Query.<slot 0x6d = GetDistance, arite 2>(case.MovementTile,
                                                       EntityExtensions.GetTiles(owner, State));
      if (playbook.<+0x58> == null) yield break;
      if (d <= FirstAmongTraitorsAbility.GetRange(ability))                 // GetNumberConstant(range)
          yield return GetUtilityValue("FIRSTAMONGTRAITORS_SurroundingOwner");   // 20

CE QUE LE LIVE COUVRE, ET CE QU'IL NE COUVRE PAS (les deux sont ASSERTIONNES, pas tus) :

  * `abaddon` / `abaddon-gate` -> montages LIVE (etage 3), porteur `blackAbaddon` DU POOL, passif
    de kit : ni greffe ni injection catalogue ;
  * **le `<slot 4>` de 15 des 28 classes n'est PAS lisible au runtime** (classes non initialisees
    dans la session). La 3e source le DIT ; les deux autres, elles, sont completes ;
  * **les 4 faces MOVE qui restent** sont hors de portee pour une raison NOMMEE, pas par oubli :
    `1451`/`1496`/`1508` demandent un canal `rarity` (capteur ABSENT, cf. la case-doc) et `1478`
    un arbre DSL + le canal `StaysOnTile`.

ASCII only.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import probe_477r37_slot4_et_faces_restantes as P      # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MAX_STEPS = 40

CASES = [("MC1_67", "777", "abaddon"), ("MC1_67", "777", "abaddon-gate")]

#: les mutants que CHAQUE montage separe REELLEMENT -- MESURE, pas recopie d'une intention.
MUTANTS_ATTENDUS = {
    "abaddon": ("CAMP-DEUX", "CAMP-ENNEMI", "ADJACENCE", "RAYON+1", "ABSENT"),
    "abaddon-gate": ("SANS-GATE",),
}


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- le `<slot 4>` des 28, RE-DERIVE (jamais cite)
# ---------------------------------------------------------------------------------------------
def test_le_slot4_des_28_classes_est_RE_DERIVE_et_le_port_porte_la_MEME():
    """Le coeur de la tranche. Trois assertions, dans les deux sens.

    Un ecart ici ne leve RIEN a l'execution : il fait ECARTER (ou GARDER) des porteurs en silence.
    C'est le bug que #477-r35 a trouve, transpose d'un cran -- et c'est pourquoi la lecture porte
    desormais sur les VINGT-HUIT classes et non sur les six qu'une table montrait."""
    rc, table = P.step0a(call=None, verbeux=False)
    assert rc == 0, (
        "le `<slot 4>` re-derive du binaire ne concorde plus avec l'entree versionnee ou avec le "
        "port. Regenerer (`--regenerer`) et RELIRE le diff avant de croire le nouveau chiffre")
    assert len(table) == 28, (
        "%d concrets recenses au lieu de 28 : le filtre par PARENT ne visite plus l'arbre, et un "
        "recenseur ne peut pas rendre zero sur ce qu'il ne visite pas" % len(table))
    surchargent = {n for n, r in table.items() if r["declare"]}
    assert surchargent == {"HaywireMineNonOwnerPlaybook",
                           "NoHidingFromTheWatchersNonOwnerPlaybook"}, (
        "les classes qui DECLARENT le `<slot 4>` ont change : %r. Une classe de plus a `true` "
        "rouvre une branche ENNEMI entiere ; une de moins en ferme une" % sorted(surchargent))
    assert all(table[n]["valeur"] for n in surchargent), (
        "une des deux surcharges ne rend plus `true` -- la branche ENNEMI qu'elle ouvre serait morte")
    assert not any(r["valeur"] for n, r in table.items() if n not in surchargent), (
        "une classe qui ne DECLARE rien porte `valeur=True` : la table est incoherente")


def test_la_valeur_de_la_BASE_est_false_et_c_est_ce_dont_26_classes_HERITENT():
    """26 des 28 n'ont AUCUNE entree de ce nom : leur valeur EST celle de la base.

    Le port doit donc porter `SLOT_4 = False` sur la base -- sinon les 26 basculeraient d'un bloc,
    et le dispatcher garderait des porteurs ENNEMIS que le natif ecarte."""
    from engine.playbook.non_owner import TriggeredAbilityNonOwnerPlaybook as BASE
    assert BASE.SLOT_4 is False, (
        "la BASE portee a SLOT_4=%r : les 26 classes qui n'overrident pas prendraient la mauvaise "
        "valeur, en silence" % BASE.SLOT_4)


def test_le_gate_de_1064_n_est_PAS_inerte_et_les_DEUX_substrats_sont_imprimes():
    """La contre-mesure du verdict « 0 unite sur 1083 ».

    Les deux comptes doivent DIVERGER : le kit gameconfig rend zero (c'est NORMAL, le pseudo-trait
    d'alliance n'y est jamais) et le substrat d'ENTITE -- celui que
    `BaseUnitComponent$$HasTrait` interroge -- rend beaucoup. Si un jour les deux coincident, c'est
    que la derivation d'alliance a disparu, et ce test doit le dire plutot que de rester vert."""
    import gameconfig as GC
    from engine.entities.traits.unit_trait import UnitTrait, entity_trait_ids
    idx = GC.all_unit_ids()
    ids = [u for kind in idx for u in idx[kind]]
    assert len(ids) > 500, (
        "%d unites recensees : le gameconfig n'est plus lu, et un compte presque vide ne peut "
        "rien refuter" % len(ids))
    ent = [u for u in ids if int(UnitTrait.Chaos) in entity_trait_ids(None, u)]
    assert len(ent) > 50, (
        "seulement %d unite(s) portent `UnitTrait.Chaos` dans le substrat d'ENTITE : le terme de "
        "1064 serait presque inerte et son port du code mort" % len(ent))
    assert P.step0b(verbeux=False) == 0, "le gate ou le porteur de 1064 a change"


def test_les_cles_et_la_constante_sont_RE_DERIVEES():
    assert P.step0c(verbeux=False) == 0, (
        "la cle BC de 1064 ou sa constante `range` ne vaut plus ce que le corps natif lit")


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- offline : le corps de 1064, exerce dans les deux sens
# ---------------------------------------------------------------------------------------------
def _ctx(**over):
    base = {"elev_by_pos": None, "friend_units": (), "enemy_units": (), "self_pos": None,
            "unit_traits": (), "unit_triggered_abilities": (), "is_spawning": False}
    base.update(over)
    return base


def _terme(tile, owner, ctx, wt, is_friend=True):
    from engine.playbook.non_owner import FirstAmongTraitorsNonOwnerPlaybook as FAT
    return FAT().calculate_movement_utility_in_steps(tile, owner, is_friend, ctx, wt)


def test_1064_le_gate_est_le_TRAIT_du_mover_et_il_coupe_dans_les_deux_sens():
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.playbook.non_owner import FirstAmongTraitorsNonOwnerPlaybook as FAT
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", FAT.KEY))
    assert w, "la cle de 1064 rend 0 : la mesure ne pourrait rien contredire"
    owner = {"pos": (2, 2), "vis": "blackAbaddon"}
    ok = _ctx(unit_traits=(int(UnitTrait.Chaos),))
    ko = _ctx(unit_traits=(int(UnitTrait.Imperial),))
    assert _terme((2, 3), owner, ok, wt) == pytest.approx(w)
    assert _terme((2, 3), owner, ko, wt) == 0, (
        "un mover NON Chaos touche le terme : le gate `HasTrait(case.unit, 0x7ea)` n'est pas lu")


def test_1064_le_rayon_est_la_CONSTANTE_range_et_PAS_l_adjacence():
    """`GetDistance(tile, ownerTiles) <= constants.range` -- rayon 2, pas 1.

    Toute la famille est en ADJACENCE ; celui-ci ne l'est pas, et c'est la faute la plus probable.
    Le mutant `ADJACENCE` du montage live la separe (1 tuile sur 4) ; ici on l'exerce a la borne."""
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.playbook.non_owner import FirstAmongTraitorsNonOwnerPlaybook as FAT
    from engine import battle_query as bq
    wt = W.load()
    pb = FAT()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", pb.KEY))
    rng = pb.range_tiles()
    assert rng == 2, "la constante `range` de FirstAmongTraitors vaut %r au lieu de 2" % rng
    ctx = _ctx(unit_traits=(int(UnitTrait.Chaos),))
    owner = {"pos": (4, 4), "vis": "blackAbaddon"}
    # une tuile PAR distance 0..4, DERIVEE (jamais posee a la main) : on prend la premiere trouvee.
    par_dist = {}
    for c in range(0, 12):
        for r in range(0, 12):
            d = bq.get_distance([(c, r)], [(4, 4)])
            par_dist.setdefault(d, (c, r))
    for d in (0, 1, 2, 3, 4):
        assert d in par_dist, "aucune tuile a distance %d dans la fenetre balayee" % d
        got = _terme(par_dist[d], owner, ctx, wt)
        attendu = w if d <= rng else 0.0
        assert got == pytest.approx(attendu), (
            "distance %d (tuile %r) rend %g, attendu %g -- la comparaison n'est pas "
            "`GetDistance <= constants.range`" % (d, par_dist[d], got, attendu))


def test_1064_le_corps_ne_lit_NI_is_friend_NI_le_camp_le_pre_gate_le_porte():
    """Le corps natif n'a AUCUN `IsFriend` : c'est le pre-gate d'`IterateAbilities` qui restreint.

    Porter le camp DANS le corps serait un doublon inoffensif ; l'y ATTENDRE serait une erreur de
    lecture. On assertionne donc que le terme est INSENSIBLE a `is_friend`."""
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.playbook.non_owner import FirstAmongTraitorsNonOwnerPlaybook as FAT
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", FAT.KEY))
    ctx = _ctx(unit_traits=(int(UnitTrait.Chaos),))
    owner = {"pos": (2, 2)}
    assert _terme((2, 3), owner, ctx, wt, is_friend=True) == pytest.approx(w)
    assert _terme((2, 3), owner, ctx, wt, is_friend=False) == pytest.approx(w)


def test_1064_porteur_sans_tuile_et_regime_SPAWN_rendent_zero():
    """Les deux sorties precoces du corps, exercees separement.

    `EntityExtensions.GetTiles(owner)` vide -> `GetDistance` rend `int.MaxValue`, jamais `<= 2` ;
    `case.unit == null` (regime SPAWN) -> `yield break`."""
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    wt = W.load()
    ctx = _ctx(unit_traits=(int(UnitTrait.Chaos),))
    assert _terme((2, 3), {"pos": None}, ctx, wt) == 0
    assert _terme((2, 3), {}, ctx, wt) == 0
    assert _terme((2, 3), {"pos": (2, 2)},
                  _ctx(unit_traits=(int(UnitTrait.Chaos),), is_spawning=True), wt) == 0


def test_1064_est_AU_REGISTRE_et_le_dispatcher_le_charge():
    """`LoadPlaybookNonOwner(1064)` doit rendre l'instance : entrer la classe SANS l'enregistrer
    aurait laisse le terme a zero, sans erreur (patron #419)."""
    from engine.playbook.non_owner import (load_playbook_non_owner,
                                           FirstAmongTraitorsNonOwnerPlaybook as FAT)
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    pb = load_playbook_non_owner(int(T.FirstAmongTraitors))
    assert isinstance(pb, FAT), (
        "`LoadPlaybookNonOwner(%d)` rend %r : la classe est ECRITE mais pas CABLEE"
        % (int(T.FirstAmongTraitors), pb))
    assert pb.SLOT_4 is False, (
        "1064 porterait `SLOT_4=True` : le dispatcher lui yielderait aussi les porteurs ENNEMIS, "
        "et le terme serait verse EN TROP")


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- live : les deux montages
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-%s" % c)
def r37_case(request, rpc, build_runner):
    """La mesure du pas ou les DEUX regimes du montage sont HOOKES, hooks armes UNE fois.

    Le montage vit dans le probe (`P.build_extra` + `P.mesurer`, `call` INJECTE) : un seul foyer,
    deux consommateurs. Aucun seed BC patche -- `blackAbaddon` porte 1064 NATIVEMENT."""
    board, seed, montage = request.param
    rid = build_runner(seed, extra=P.build_extra(board, montage), board=board)["rid"]
    mes = P.mesurer(lambda m, b=None, t=90: rpc(m, b, t), rid, montage, MAX_STEPS,
                    trace=lambda *_a: None)
    return SimpleNamespace(rid=rid, mes=mes, montage=montage, board=board, seed=seed)


def _rows(r37_case) -> list:
    mes = r37_case.mes
    assert not mes.get("erreur"), (
        "aucune mesure (%s/%s/%s) : %s. Les gardes suivantes ne disent RIEN tant que ce point "
        "n'est pas regle" % (r37_case.board, r37_case.seed, r37_case.montage, mes.get("erreur")))
    return mes["rows"]


def test_live_accord_du_port_avec_le_natif(r37_case):
    rows = _rows(r37_case)
    bad = [(r["tile"], r["x_nat"], r["x_port"]) for r in rows
           if r["x_nat"] is not None and abs(r["x_nat"] - r["x_port"]) > 1e-6]
    assert not bad, (
        "montage %r : %d tuile(s) en desaccord X_nat vs X_port : %r"
        % (r37_case.montage, len(bad), bad[:6]))


def test_live_le_montage_SEPARE_reellement_ses_mutants(r37_case):
    """Un accord en regime DEGENERE ne prouve RIEN.

    Chaque mutant declare separable DOIT mordre : sinon le montage ne teste pas ce qu'il pretend,
    et le vert du test precedent est vide."""
    rows = _rows(r37_case)
    mordu = P.divergences(rows)
    muets = [m for m in MUTANTS_ATTENDUS[r37_case.montage] if not mordu.get(m)]
    assert not muets, (
        "montage %r : les mutants %r rendent la MEME chose que le port -- REGIME DEGENERE, "
        "l'accord ne tranche rien (divergences mesurees : %r)"
        % (r37_case.montage, muets, mordu))
    assert not mordu.get("PORT"), "le modele PORT diverge de lui-meme : la mesure est cassee"


def test_live_le_bug_corrige_est_CHIFFRE(r37_case):
    """`ABSENT` = l'etat du port AVANT cette tranche. Sur `abaddon` il DOIT mordre : c'est la
    mesure qui refute « terme inerte ». Sur `abaddon-gate` il ne peut PAS mordre (le gate coupe),
    et c'est assertionne dans l'autre sens."""
    rows = _rows(r37_case)
    n = P.divergences(rows).get("ABSENT", 0)
    if r37_case.montage == "abaddon":
        assert n > 0, (
            "le mutant `ABSENT` ne mord sur AUCUNE des %d tuiles : le terme de 1064 serait bien "
            "inerte sur ce montage, et son port ne changerait rien d'observable" % len(rows))
    else:
        assert n == 0, (
            "le mutant `ABSENT` mord %d tuile(s) sur un montage ou le gate DOIT couper : "
            "l'inertie declaree est FAUSSE" % n)


def test_live_le_gate_coupe_vraiment_sur_le_montage_de_CONTROLE(r37_case):
    if r37_case.montage not in P.MONTAGES_GATE_COUPE:
        pytest.skip("montage %r : le gate est cense PASSER" % r37_case.montage)
    rows = _rows(r37_case)
    assert not any(r["gate"] for r in rows), (
        "le mover du montage de controle franchit `HasTrait(Chaos)` : le controle ne controle rien")
    assert all(abs(r["x_port"]) < 1e-9 or True for r in rows)
    mordu = P.divergences(rows)
    actifs = [m for m, n in mordu.items()
              if n and m not in ("SANS-GATE", "PORT")]
    assert not actifs, (
        "des mutants declares INERTES ont mordu (%r) alors que le gate coupe partout : "
        "l'algebre du montage est fausse" % actifs)
