"""GARDE #477-r31 -- `AttractMechanicalsUtility` compte les AMIS, pas les DEUX CAMPS.

CE QUE CETTE GARDE PROTEGE. Deux choses, et la seconde a ete etablie CONTRE l'attente :

  1. la feuille `DoctrinaImperatives_AttractMechanicals` etait **INERTE** cote port :
     `meta.attract_mechanicals_neighbor` n'etait produit par AUCUN constructeur de `meta`, donc
     `AttractMechanicalsUtility.evaluate` rendait 0 partout. `apply_tile_attributes` la derive
     desormais de `ctx.friend_units[].active` ;
  2. `case-477r29` §4 annoncait que cette feuille compte **LES DEUX CAMPS**, au motif que son slot
     `0x7a` se nomme `GetAdjacentUnits` (arite 4) la ou `RadSaturationPlaybook` appelle un
     `GetAdjacentFriends` (arite 2). **C'est FAUX**, et c'est la meme faute que celle que
     `case-477r29` reprochait a `case-26` : avoir deduit le CAMP du NOM du slot.

     LE CAMP EST UN ARGUMENT. La signature reelle, lue dans `frida/methods.tsv`, est
     `GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)` ; le call-site passe
     `friendsOf = case.Unit`, `enemiesOf = null` ; et le foyer terminal
     `IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles` fait
     `if (friendsOf != null && !IsFriend(u, friendsOf, ctx)) continue;`. Le nom du slot designe
     l'ensemble AVANT filtrage.

CE QUE LE DECOMPILE DIT --
`IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :

    if (case.Unit == null)                        yield break;
    if (!UnitExtensions.HasTrait(case.Unit, 5))   yield return Fix64(0);      // Mechanical
    units = query.<slot 0x7a>(case.MovementTile, case.Unit, 0, 0);
    if (Enumerable.Any(units, f => HasActiveAbility(f, 0x45e) && f != case.Unit))
        x += GetUtilityValue("Marshal_AttractMechanicals");                  // BC = 10

DEUX MONTAGES, parce qu'un seul ne separe pas tout :
  * `camp`  : cible neutre au centre, un Marshal ALLIE et un Marshal ENNEMI a distance 2 en
    miroir, zone plate -- seul le CAMP change. Il porte AUSSI un ami NEUTRE (sans
    `DoctrinaImperatives`) place pres des tuiles temoins : sans lui, « amis porteurs du predicat »
    et « amis » coincident et le mutant `SANS-PREDICAT` ne peut pas mordre ;
  * `agreg` : DEUX Marshals ALLIES, une tuile candidate adjacente aux DEUX -- il separe `Any`
    (le natif : +10 UNE fois) de `Count` (+10 x n, ce que fait la feuille voisine 1202).

⚠ LE CONFOND, PAYE PAR UNE MESURE ROUGE. `admecMarshall` porte AU SEED la relique
`TertiaryAbility = 1457` (`KardiocoreGalvanus`), dont
`IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusNonOwnerPlaybook.
u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` rend **+20** sur les tuiles adjacentes a
son porteur, sous le gate `UnitExtensions.IsMechanical(case.Unit)` -- MEME gate, MEME camp, MEMES
tuiles que le terme mesure. Premiere mesure : `X_nat = 30` pour `X_port = 10`. Le montage
DESEQUIPE donc la relique (`catalog_inject.unequip_relic`). Le gap de port qu'elle a revele (13
des 25 `*NonOwnerPlaybook` natifs manquent au registre `non_owner.NON_OWNER_MOVE_PLAYBOOKS`) est le
residu **#477-r33** -- il n'est PAS corrige ici.
⚠ Et il dormait : `probe_477r29` ne l'avait pas vu parce que SON carrier n'est pas Mechanical.

LE PORTEUR. Le gate est un TRAIT, pas une ability : **13 heros du pool sont Mechanical**, aucune
greffe n'est necessaire pour le carrier. Le carrier retenu (`admecDominus`) a les traits les plus
minces et un passif SANS playbook natif.

Mesures fondatrices (`probe_477r31_attract_mechanicals_camp.py`, decomposition
`X = Tile(7) - Elevation - TileEffects` aux hooks EXISTANTS de `scorer-damage-trace`) :
`camp` MC1_67/777 -> 0 desaccord / 11 tuiles, `DEUX-CAMPS` mord 3, `SANS-PREDICAT` 3 ;
`camp` C4_09/31337 -> 0 / 12, `DEUX-CAMPS` 4, `SANS-PREDICAT` 2 ;
`agreg` MC1_67/777 et C4_09/31337 -> 0 / 8, `COUNT (x n)` mord 1 (la tuile a nA=2 vaut 10, pas 20).
AUCUNE de ces valeurs n'est gelee ici : les assertions re-derivent tout de la mesure du pas.

ASCII only.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from counterproof import assert_sample_confrontable  # noqa: E402

import probe_477r31_attract_mechanicals_camp as P    # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MAX_STEPS = 25

#: DEUX couples board/seed x DEUX montages : le verdict ne tient ni a une geometrie ni a un axe.
#: Les positions sont CHERCHEES par board (cf. `P.LAYOUTS_CAMP` / `P.LAYOUTS_AGREG`).
CASES = [("MC1_67", "777", "camp"), ("C4_09", "31337", "camp"),
         ("MC1_67", "777", "agreg"), ("C4_09", "31337", "agreg")]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-%s" % c)
def am_case(request, rpc, build_runner):
    """La mesure du pas ou les DEUX bras du montage sont HOOKES, hooks armes UNE fois.

    Le montage vit dans le probe (`P._seed_bc_montage` + `P.build_extra` + `P.mesurer`, `call`
    INJECTE) : un seul foyer, deux consommateurs -- la garde ne re-code ni le seed BC (dont le
    retrait de la relique CONFOND), ni les placements, ni la marche."""
    board, seed, montage = request.param
    tag = uuid.uuid4().hex[:8]
    seed_bc = ROOT / "logs" / "runners" / ("test477r31-seedbc-%s.json" % tag)
    P._seed_bc_montage(seed_bc, montage)
    extra = P.build_extra(board, montage)              # FOYER UNIQUE du montage (cf. le probe)
    extra[1] = str(seed_bc)
    rid = build_runner(seed, extra=extra, board=board)["rid"]
    mes = P.mesurer(lambda m, b, t=90: rpc(m, b, t), rid, montage, MAX_STEPS,
                    trace=lambda *_a: None)
    try:
        seed_bc.unlink()
    except OSError:
        pass
    return SimpleNamespace(rid=rid, mes=mes, montage=montage, board=board, seed=seed)


def _rows(am_case) -> list:
    """Les lignes de la mesure, ou un ROUGE qui NOMME la panne au lieu d'un `KeyError`."""
    mes = am_case.mes
    assert not mes.get("erreur"), (
        "aucune mesure (%s/%s/%s) : %s. Les gardes suivantes ne disent RIEN tant que ce point "
        "n'est pas regle (cf. `test_le_montage_a_bien_ete_mesure`)"
        % (am_case.board, am_case.seed, am_case.montage, mes.get("erreur")))
    # SECONDE panne, DISTINCTE (#10011) : le montage a abouti et les tuiles sont hookees, mais le
    # canal NATIF est muet -- `X_nat` n'existe sur aucune ligne, `divergences` rend 0 pour TOUS les
    # modeles et le verdict d'accord passerait A VIDE. Les gardes de MONTAGE restent vertes a bon
    # droit : ce n'est pas le montage qui est en cause. Mesure du 2026-08-15 : 8 F / 43 P ici.
    assert not mes.get("x_nat_indisponible"), (
        "le montage a ABOUTI (%d tuiles hookees) mais le canal NATIF est MUET : ce n'est PAS le "
        "port qui est en cause, c'est le CAPTEUR. %s"
        % (len(mes.get("rows") or ()), mes.get("x_nat_indisponible")))
    return mes["rows"]


def test_le_slot_de_la_feuille_ne_dit_PAS_le_camp():
    """ETAGE 1 (offline, aucun runner) : le slot, SON ARITE, et surtout SA SIGNATURE.

    Trois assertions, et c'est le TRIPLET qui porte le sens :
      * le slot `0x7a` est bien un `GetAdjacentUnits` d'arite 4 (c'est ce que le call-site appelle) ;
      * le slot voisin `0x83` est un `GetAdjacentFriends` d'arite 2 (celui de `RadSaturation`) ;
      * **toutes** les surcharges d'arite 4 portent le couple `(friendsOf, enemiesOf)` -- c'est
        CETTE derniere qui interdit de relire « GetAdjacentUnits » comme « les deux camps ». Si
        une surcharge sans ce couple apparaissait, le raisonnement « arg2 = friendsOf » tomberait
        et il faudrait relire le call-site AVANT de croire le port."""
    build = P._build_hash()
    tbl = P._slot_table(build)
    assert tbl.get(("IBattleQuery", 0x7a)) == ("GetAdjacentUnits", 4), (
        "slot 0x7a = %r : c'est celui qu'appelle AttractMechanicalsUtility (4 arguments apres le "
        "this)" % (tbl.get(("IBattleQuery", 0x7a)),))
    assert tbl.get(("IBattleQuery", 0x83)) == ("GetAdjacentFriends", 2), (
        "slot 0x83 = %r : celui de RadSaturationPlaybook. Le contraste d'ARITE entre les deux est "
        "reel ; ce qu'il ne dit PAS, c'est le camp" % (tbl.get(("IBattleQuery", 0x83)),))
    sigs = set(P._signature(build, "IdunBattle.Core.Services.BattleQuery.GetAdjacentUnits"))
    assert sigs, "aucune signature GetAdjacentUnits dans frida/methods.tsv : table absente ?"
    sans = [s for s in sigs if not ("friendsOf:" in s and "enemiesOf:" in s)]
    assert not sans, (
        "surcharge(s) GetAdjacentUnits sans le couple (friendsOf, enemiesOf) : %r. Le port suppose "
        "que le 2e argument du call-site (case.Unit) est `friendsOf` -- si ce n'est plus vrai, "
        "c'est la RE du camp qu'il faut refaire" % (sans,))


def test_le_poids_bc_est_positif_et_sous_sa_vraie_cle():
    """ETAGE 1 (offline) : la cle LUE au litteral (`probe_212_bc_key_literals.py --symbol ...`).

    Assertions dans les DEUX sens : la cle reelle rend un poids non nul, et elle est DISTINCTE de
    celle de la feuille voisine (`RadSaturation_AdjacentMarshals`) -- les deux valent 10 sur ce
    build, donc seul le NOM les separe, et un port qui lirait l'autre serait juste par accident."""
    from engine import weights as W
    from engine.utilities.tile import AttractMechanicalsUtility as A
    wt = W.load()
    w = wt.sub(A.WEIGHT_CATEGORY, A.WEIGHT_KEY)
    assert w > 0, (
        "la cle BC %s.%s rend %r : le litteral resolu au decompile a disparu de `Utilities.Default`"
        % (A.WEIGHT_CATEGORY, A.WEIGHT_KEY, w))
    assert (A.WEIGHT_CATEGORY, A.WEIGHT_KEY) != ("TriggeredAbilities",
                                                 "RadSaturation_AdjacentMarshals"), (
        "la feuille lirait la cle de RadSaturationPlaybook : les deux valent 10 sur ce build, "
        "l'erreur serait donc SILENCIEUSE")


def test_le_gate_est_un_TRAIT_et_le_predicat_une_ACTIVE():
    """ETAGE 1 (offline) : contre-epreuve a quatre bras sur un `ctx` synthetique.

    Le corps natif a DEUX conditions, et les confondre est indolore en valeur :
      * `HasTrait(case.Unit, 5)` -- un mover NON Mechanical ne rend rien ;
      * `HasActiveAbility(f, 0x45e)` -- un voisin dont 1118 est un id DECLENCHE ne compte pas
        (`TriggeredAbilityType(1118)` existe et nomme `TerrorsLament` : l'ordinal ne discrimine
        pas, seule la CALLEE le fait) ;
      * `f != case.Unit` -- le mover ne compte pas pour lui-meme, contrairement a 1202 ;
      * `Any` -- deux voisins porteurs valent le poids UNE fois."""
    from engine import weights as W
    from engine.utilities.tile import AttractMechanicalsUtility, apply_tile_attributes
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.traits.unit_trait import UnitTrait
    u = AttractMechanicalsUtility()
    wt = W.load()
    w = float(wt.sub(u.WEIGHT_CATEGORY, u.WEIGHT_KEY))
    aid = int(ActiveAbilityType.DoctrinaImperatives)
    neigh = {(1, 1): [(1, 0), (1, 2), (0, 1), (2, 1), (0, 0), (2, 0)]}
    base = {"elev_by_pos": {}, "neigh_by_pos": neigh, "enemy_units": [],
            "unit_traits": [int(UnitTrait.Mechanical)], "self_pos": None,
            "unit_active_abilities": ()}

    def terme(ctx):
        return u.evaluate((1, 1), apply_tile_attributes({}, (1, 1), ctx), ctx, wt)

    actif = dict(base, friend_units=[{"pos": (1, 0), "active": (aid,)}])
    assert terme(actif) == w, "un ami adjacent porteur de l'ACTIVE 0x45e doit valoir le poids"
    declenche = dict(base, friend_units=[{"pos": (1, 0), "triggered": (aid,), "active": ()}])
    assert terme(declenche) == 0.0, (
        "le port compte un voisin dont 1118 est un id DECLENCHE : il lirait `HasTriggeredAbility` "
        "quand le natif appelle `HasActiveAbility`")
    non_mech = dict(actif, unit_traits=[])
    assert terme(non_mech) == 0.0, (
        "le gate `HasTrait(case.Unit, Mechanical)` ne coupe pas : la feuille rendrait son terme a "
        "toute unite, et `probe_477r29` (carrier NON Mechanical) deviendrait rouge")
    self_seul = dict(base, friend_units=[], self_pos=(1, 0),
                     unit_active_abilities=(aid,))
    assert terme(self_seul) == 0.0, (
        "le MOVER compte pour lui-meme : le predicat natif ecrit `f != case.Unit` -- c'est ce qui "
        "distingue cette feuille de RadSaturationPlaybook, qui, lui, n'exclut PAS le self")
    deux = dict(base, friend_units=[{"pos": (1, 0), "active": (aid,)},
                                    {"pos": (0, 1), "active": (aid,)}])
    assert terme(deux) == w, (
        "deux voisins porteurs rendent %r au lieu de %r : le port somme (`Count`) la ou le natif "
        "teste (`Any`)" % (terme(deux), w))


def test_le_montage_a_bien_ete_mesure(am_case):
    """ROUGE DE SCENARIO (#462-r6) : sans mesure, aucune des gardes suivantes ne dit rien."""
    assert_sample_confrontable(
        not am_case.mes.get("erreur"),
        mutation="build %s/%s montage %r avec `--place`/`--a-place` (seed BC DESEQUIPE de la "
                 "relique KardiocoreGalvanus), puis marche de la trajectoire native jusqu'au pas "
                 "ou les DEUX bras sont HOOKES" % (am_case.board, am_case.seed, am_case.montage),
        doit_casser="un pas ou les hooks `scorerTileTermTrace` couvrent les deux groupes de tuiles "
                    "du montage",
        observe=str(am_case.mes.get("erreur")),
        remede="rejouer `python probe_477r31_attract_mechanicals_camp.py --board %s --seed %s "
               "--montage %s` : il imprime, pas par pas, le nombre de candidates et la taille des "
               "deux bras. Les hooks ne voient que les tuiles du tier COMPARABLE (les tuiles "
               "d'ATTAQUE) : si un bras est vide, c'est la geometrie qu'il faut re-etalonner"
               % (am_case.board, am_case.seed, am_case.montage))


def test_les_deux_bras_sont_hookes(am_case):
    """ROUGE DE SCENARIO : sans les DEUX bras, le mutant separateur du montage n'est pas separable."""
    mes = am_case.mes
    assert_sample_confrontable(
        bool(mes.get("bras_a")) and bool(mes.get("bras_b")),
        mutation="ventilation des tuiles HOOKEES par groupe du montage %r" % am_case.montage,
        doit_casser="au moins une tuile par groupe (camp : ALLIE seul / ENNEMI seul ; "
                    "agreg : DEUX Marshals amis / UN SEUL)",
        observe="bras_a=%s bras_b=%s" % (mes.get("bras_a"), mes.get("bras_b")),
        remede="cf. `test_le_montage_a_bien_ete_mesure`")


def test_le_natif_suit_le_modele_AMIS(am_case):
    """LE VERDICT : `X_nat == X_port`, tuile par tuile, sur toutes les tuiles hookees."""
    rows = _rows(am_case)
    ecarts = [(r["tile"], r["na"], r["ne"], r["x_nat"], r["x_port"], r["leaves"])
              for r in rows
              if r["x_nat"] is not None and abs(r["x_nat"] - r["x_port"]) > 1e-6]
    assert not ecarts, (
        "%d tuile(s) en desaccord X_nat vs X_port sur %d (%s/%s/%s) : %r -- la derniere colonne "
        "est la VENTILATION du port par feuille, a lire avant de conclure quoi que ce soit sur "
        "AttractMechanicals : un terme natif NON PORTE d'une AUTRE feuille produit exactement ce "
        "symptome (c'est ce qu'a fait KardiocoreGalvanus_AdjacentFriendly, +20, residu #477-r33)"
        % (len(ecarts), len(rows), am_case.board, am_case.seed, am_case.montage, ecarts))


def test_le_mutant_SEPARATEUR_du_montage_est_refute_par_la_mesure(am_case):
    """LA QUESTION DE CHAQUE MONTAGE : son mutant DOIT diverger du natif.

    `camp`  -> `DEUX-CAMPS` : la lecture annoncee par `case-477r29` §4, REFUTEE ici ;
    `agreg` -> `COUNT (x n)` : `Any` contre `Count`.
    Sans cette divergence, `test_le_natif_suit_le_modele_AMIS` passerait a vide -- un montage ou
    les deux modeles coincident est un REGIME DEGENERE, pas une preuve."""
    rows = _rows(am_case)
    div = P.divergences(rows)
    sep = P.MUTANT_SEPARATEUR[am_case.montage]
    assert div.get(sep, 0) > 0, (
        "le mutant %r rend exactement ce que rend le port sur les %d tuiles mesurees "
        "(divergences par modele : %r) : ce montage ne tranche RIEN" % (sep, len(rows), div))


def test_les_mutants_attendus_mordent_sur_ce_montage(am_case):
    """CONTRE-EPREUVE : chaque lecture ALTERNATIVE que CE montage separe doit diverger.

    La liste est DERIVEE du montage, pas recopiee : `camp` ne peut pas separer `Any`/`Count` (un
    seul Marshal ami par tuile) et `agreg` ne peut pas separer le camp (aucun Marshal ennemi). Un
    mutant muet ne condamne pas le port -- il dit que ce montage ne le separe pas, et c'est
    exactement ce que ce decoupage rend explicite plutot que tu.

    `ABSENT (avant)` est l'etat du port AVANT cette tranche (`meta.attract_mechanicals_neighbor`
    produit nulle part, donc terme nul partout) : sa divergence CHIFFRE le bug corrige."""
    rows = _rows(am_case)
    div = P.divergences(rows)
    attendus = (("DEUX-CAMPS", "ENNEMIS", "SANS-PREDICAT", "ABSENT (avant)") if am_case.montage == "camp"
                else ("ENNEMIS", "COUNT (x n)", "ABSENT (avant)"))
    muets = [nom for nom in attendus if not div.get(nom)]
    assert not muets, (
        "mutant(s) qui ne MORDENT PAS sur le montage %r (%s/%s) : %r (divergences mesurees : %r)"
        % (am_case.montage, am_case.board, am_case.seed, muets, div))
    assert not div.get("PORT (amis)"), (
        "le modele du port diverge de la mesure : c'est le verdict d'accord qui est rouge, pas la "
        "contre-epreuve (divergences : %r)" % div)


def test_le_volet_SELF_est_inerte_PAR_ALGEBRE_et_c_est_assertionne(am_case):
    """Le carrier ne porte pas `DoctrinaImperatives` -- le volet `f != case.Unit` ne peut pas mordre.

    Assertion dans les DEUX SENS, parce qu'une inertie non assertionnee est un trou :
      * AUCUNE ligne mesuree n'a `self = 1` -> le mover n'est jamais porteur du predicat ;
      * donc le mutant `SELF-INCLUS` ne DOIT pas mordre. S'il mordait, l'inertie declaree serait
        fausse et il faudrait relire la mesure, pas le port.
    L'exclusion elle-meme est gardee OFFLINE par `test_le_gate_est_un_TRAIT_et_le_predicat_une_ACTIVE`
    (branche `self_seul`), qui, lui, EXERCE le volet."""
    rows = _rows(am_case)
    self_actif = [r["tile"] for r in rows if r["self"]]
    div = P.divergences(rows)
    assert not self_actif, (
        "le mover porte le predicat sur %r : l'inertie declaree est fausse, et `SELF-INCLUS` doit "
        "alors figurer parmi les mutants qui mordent" % (self_actif,))
    assert not div.get("SELF-INCLUS"), (
        "`SELF-INCLUS` diverge (%d tuiles) alors qu'aucune ligne n'a self=1 : la mesure et le "
        "modele ne lisent pas le meme substrat" % div["SELF-INCLUS"])
