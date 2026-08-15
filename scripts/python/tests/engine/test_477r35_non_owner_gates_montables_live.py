"""GARDE #477-r35 -- trois `*NonOwnerPlaybook` de plus, et le `<slot 4>` qui n'est PAS une constante
de famille.

CE QUE CETTE GARDE PROTEGE, et pourquoi ce n'est pas un detail :

  * **Le `<slot 4>` est une donnee PAR CLASSE.** `#433-r4-r3` avait lu `false` sur TROIS classes et
    le dispatcher en avait fait une regle de famille : il ecartait TOUS les porteurs ennemis d'un
    bloc, avant meme de charger le playbook. Or `HaywireMineNonOwnerPlaybook` porte
    `slot 4 == true` -- son corps trivial est `UnityEngine.U2D.IK.Solver2D$$DoValidate`
    (`return 1`), la ou les deux classes qui SURCHARGENT explicitement portent
    `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId` (`return 0`). Consequence
    MESUREE : sur la tuile minee du montage `haywire`, `X_nat = -130` pour un port a `-100` --
    il manquait exactement `HaywireMine_EnemyAvoidMine` (-30).
  * **Et le premier critere de lecture rendait VERT.** Il postulait que le bloc `methodPointers`
    d'une classe COMMENCE a son `.ctor` ; les SIX classes relues le satisfaisaient, y compris
    celle qui surcharge.
    ⚠ **Son REMPLACANT (« l'entree qui PRECEDE le `.ctor` ») etait FAUX AUSSI, dans les deux
    sens** -- #477-r37 : faux negatif sur `NoHidingFromTheWatchersNonOwnerPlaybook` (qui declare
    APRES son `.ctor`), faux positif sur `ECogSupport`/`KustomForceFieldReworked` (l'entree lue
    appartenait au TYPE PRECEDENT). La lecture CORRECTE passe par le NOM du slot
    (`get_ShouldIncludingEnemiesWhenCalculate`) dans le `global-metadata.dat`, sur les VINGT-HUIT
    concrets. L'etage 1 y DELEGUE, il ne cite aucun verdict.

LES TROIS CORPS, au decompile du build courant :

  `IdunBattle.AI.Playbook.Loki.PurgeResponseNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
      if (case.unit == null) yield break;
      if (!UnitExtensions.HasFaction(case.unit, 0x14)) yield break;   // UnitFaction.LeaguesOfVotann
      if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(case.MovementTile, owner))
          yield return GetUtilityValue("PurgeResponse_FriendlyVotannLikeSteeljack");   // 20

  `IdunBattle.AI.Playbook.Loki.MawClawsOfThyraxNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
      if (case.unit != null) {
          if (AreEntitiesAdjacent(case.MovementTile, owner)
              && HasTrait(case.unit, 0x2)                            // UnitTrait.Summon
              && Query.<slot 0x92 = AreFriends, arite 3>(case.unit, owner, 0))
              yield return GetUtilityValue("MawClawsOfThyrax_AdjacentSummons");        // 5
          yield break;
      }
      if (case.parent == null) yield break;                          // BRANCHE SPAWN
      if (AreEntitiesAdjacent(case.MovementTile, owner) && AreFriends(case.parent, owner, 0))
          yield return GetUtilityValue("MawClawsOfThyrax_AdjacentSummons");

  `IdunBattle.AI.Playbook.Loki.HaywireMineNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__5$$MoveNext`
      if (case.unit == null) yield break;
      if (!TileExtensions.GetSteppableUnit(case.MovementTile, State, out u)) yield break;
      if (!UnitExtensions.HasUnitId(u, cfg.GetStringConstant(8), State)) yield break;   // unitToSpawn
      yield return GetUtilityValue(IsFriend(case.unit, owner, State)
                                   ? "HaywireMine_FriendlyAvoidMine"    // -50
                                   : "HaywireMine_EnemyAvoidMine");     // -30

CE QUE LE LIVE COUVRE, ET CE QU'IL NE PEUT PAS COUVRIR (les deux sont ASSERTIONNES, pas tus) :

  * `purge` / `purge-gate` / `haywire` -> montages LIVE (etage 3) ;
  * **`1469 MawClawsOfThyrax` : VERROU STRUCTUREL, mesure.** Son gate est `HasTrait(mover, Summon)`
    et `IdunBattle.Entities.UnitExtensions$$IsAutomatic` vaut exactement
    `HasTrait(Summon) || HasTrait(Object)`, sans exemption -- c'est le SEUL filtre de
    `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`. Tout mover qui franchit ce gate
    est donc joue au turn-start et n'entre jamais dans la trajectoire d'activation que
    `aiStepDryRun` marche : trait accorde a `eldarAutarch` (pose VERIFIEE), 25 pas, **0 activation**.
    Le gate est exerce OFFLINE, dans les deux sens (etage 2) ;
  * **le gate `HasUnitId` de 1531** : la greffe FAIT SPAWNER des mines des deux cotes, donc aucun
    montage ne peut offrir un plateau « sans mine », et le steppable temoin place a la main n'a ete
    hooke a aucun des 4 pas. Exerce OFFLINE (etage 2).

⚠⚠ **NE PAS JOUER EN PARALLELE DES AUTRES CONSOMMATEURS DE `scorerDamageTrace`** -- sauf que, depuis
#483, `scorerDamageTraceOn`/`Off` acceptent un `runnerId` et le probe le PASSE : la capture de ce
fichier n'est plus eteinte par le `finally` d'un voisin. La contrainte que #477-r33 a nommee est donc
LEVEE POUR CE FICHIER, et seulement parce qu'il passe l'argument.

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

import probe_477r35_non_owner_gates_montables as P     # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MAX_STEPS = 40

CASES = [("MC1_67", "777", "purge"), ("MC1_67", "777", "purge-gate"),
         ("MC1_67", "777", "haywire")]

#: les mutants que CHAQUE montage separe REELLEMENT -- DERIVE du montage, pas recopie.
MUTANTS_ATTENDUS = {
    "purge": ("CAMP-DEUX", "CAMP-ENNEMI", "ABSENT"),
    "purge-gate": ("SANS-GATE",),
    "haywire": ("SLOT4-OFF", "UNE-SEULE-CLE", "ABSENT"),
}


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-%s" % c)
def r37_case(request, rpc, build_runner):
    """La mesure du pas ou les DEUX regimes du montage sont HOOKES, hooks armes UNE fois.

    Le montage vit dans le probe (`P._seed_bc_montage` + `P.build_extra` + `P.mesurer`, `call`
    INJECTE) : un seul foyer, deux consommateurs."""
    board, seed, montage = request.param
    tag = uuid.uuid4().hex[:8]
    seed_bc = ROOT / "logs" / "runners" / ("test477r35-seedbc-%s.json" % tag)
    P._seed_bc_montage(seed_bc, montage)
    extra = P.build_extra(board, montage)
    extra[1] = str(seed_bc)
    rid = build_runner(seed, extra=extra, board=board)["rid"]
    mes = P.mesurer(lambda m, b, t=90: rpc(m, b, t), rid, montage, MAX_STEPS,
                    trace=lambda *_a: None)
    try:
        seed_bc.unlink()
    except OSError:
        pass
    return SimpleNamespace(rid=rid, mes=mes, montage=montage, board=board, seed=seed)


def _rows(r37_case) -> list:
    mes = r37_case.mes
    assert not mes.get("erreur"), (
        "aucune mesure (%s/%s/%s) : %s. Les gardes suivantes ne disent RIEN tant que ce point "
        "n'est pas regle" % (r37_case.board, r37_case.seed, r37_case.montage, mes.get("erreur")))
    # SECONDE panne, DISTINCTE (#10011) : montage abouti, tuiles hookees, canal NATIF muet ->
    # `X_nat` n'existe sur aucune ligne et le verdict d'accord passerait A VIDE.
    assert not mes.get("x_nat_indisponible"), (
        "le montage a ABOUTI (%d tuiles hookees) mais le canal NATIF est MUET : ce n'est PAS le "
        "port qui est en cause, c'est le CAPTEUR. %s"
        % (len(mes.get("rows") or ()), mes.get("x_nat_indisponible")))
    return mes["rows"]


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- le `<slot 4>`, RE-DERIVE du binaire classe par classe
# ---------------------------------------------------------------------------------------------
def test_le_slot4_est_une_donnee_PAR_CLASSE_et_le_port_porte_la_MEME():
    """Ce test est le coeur de la tranche : il aurait rougi sur `origin/master`.

    Il RE-DERIVE le `<slot 4>` des VINGT-HUIT concrets (metadata + PE + runtime, #477-r37) et
    confronte au port, puis re-verifie les six classes de ce cas. Deux assertions, dans les deux
    sens :
      * `HaywireMineNonOwnerPlaybook` vaut `true` -- sinon la branche ENNEMI serait morte et la cle
        `HaywireMine_EnemyAvoidMine` n'aurait aucun consommateur ;
      * les cinq autres valent `false` -- sinon le dispatcher garderait des porteurs ennemis que le
        natif ecarte, et le terme serait verse EN TROP, silencieusement."""
    assert P.step0b(P._build_hash(), verbeux=False) == 0, (
        "le `<slot 4>` re-derive du binaire ne concorde plus avec `SLOT4_ATTENDU` ou avec le port. "
        "Un ecart ici ne leve RIEN a l'execution : il fait ECARTER (ou GARDER) des porteurs en "
        "silence -- c'est exactement le bug que #477-r35 a trouve")


def test_chaque_module_engine_s_importe_SEUL_en_process_frais():
    """CLIQUET (#477-r35) : `en_echec == 0`, et il aurait attrape CETTE PR.

    Un cycle d'import Python est SENSIBLE A L'ORDRE : il se dissout des qu'un appelant importe
    `engine.entities` en premier, ce que font toutes nos passes pytest. La premiere version de
    cette tranche a mis `from .entities.traits.unit_trait import UnitTrait` dans
    `engine/battle_query.py` et a rendu `python -c "import engine.battle_query"` IMPOSSIBLE --
    avec **165 tests verts**. Seul un import ISOLE, en process NEUF, le voit.

    ⚠ Un vert ici ne dit PAS « le graphe est propre » : le 430/430 est tenu par 262 imports
    differes PORTEURS (residu #485). Il dit « aucun module ne CESSE de s'importer seul »."""
    import probe_477r35_import_isole as IMP
    mods = IMP.modules_de(IMP.PYDIR)
    assert len(mods) > 300, (
        "%d modules `engine.*` recenses : le rglob ne visite plus l'arbre, et un recenseur qui "
        "rend presque zero ne peut rien garder" % len(mods))
    res = IMP.balayer(IMP.PYDIR, mods, jobs=12)
    casses = {m: v for m, v in res.items() if v[0] != 0}
    assert not casses, (
        "%d module(s) `engine.*` ne s'importent PAS seuls en process frais : %r. C'est un cycle "
        "sensible a l'ordre -- il ne casse aucune passe pytest, mais il casse les probes VERSIONNES "
        "qui importent ce module en tete (mesure : `probe_433_r1_identity_shortcircuit.py`)."
        % (len(casses), {m: v[1][:120] for m, v in sorted(casses.items())}))


def test_le_recensement_et_les_cles_sont_RE_DERIVES():
    """Le compte ne se CITE pas et les cles non plus.

    ⚠ L'etage 0a a lui-meme rendu `0 faces MOVE` a sa premiere passe (une comparaison d'ensemble
    par egalite) et serait passe pour VERT : le probe rougit desormais sur son propre zero, et ce
    test verifie que le garde-fou est arme."""
    rc, rec = P.step0(verbeux=False)
    assert rc == 0, "le recensement ou le registre a diverge du binaire"
    assert len(rec["move"]) == 24, (
        "%d faces MOVE au lieu de 24 : le build a bouge, ou la lecture des tables est cassee "
        "(un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas)" % len(rec["move"]))
    # 18 apres #477-r35, **19** depuis #477-r37 (`1064 FirstAmongTraitors`, que #477-r35 avait
    # classe « terme inerte » sur un compte de traits fait dans le MAUVAIS substrat).
    assert len(rec["portes"]) == 19, (
        "%d faces MOVE couvertes par le registre au lieu de 19" % len(rec["portes"]))
    assert len(rec["reste"]) == 4, (
        "%d faces MOVE restent non portees au lieu de 4 (hors `RedemptionOfTheRisen`, ecrite mais "
        "volontairement hors registre)" % len(rec["reste"]))
    assert P.step0c(verbeux=False) == 0, "une cle BC ne vaut plus son litteral au gameconfig vivant"


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- offline : les gates que le LIVE ne peut pas exercer, et pourquoi
# ---------------------------------------------------------------------------------------------
def _terme(cls, tile, owner, ctx, wt, is_friend=True):
    return cls().calculate_movement_utility_in_steps(tile, owner, is_friend, ctx, wt)


def _ctx(**over):
    base = {"elev_by_pos": None, "friend_units": (), "enemy_units": (), "self_pos": None,
            "unit_traits": (), "unit_triggered_abilities": ()}
    base.update(over)
    return base


def test_PURGE_le_gate_est_la_FACTION_du_mover_et_PAS_celle_du_porteur():
    """Contre-epreuve offline : le gate lit `ctx.unit_faction`, jamais le porteur.

    Un mover Votann adjacent au porteur touche 20 ; le MEME montage avec un mover d'une autre
    faction rend 0 -- et le porteur, lui, n'a AUCUNE faction dans le `ctx`. Lire le gate sur le
    porteur (l'erreur naturelle, puisque la cle s'appelle `...VotannLikeSteeljack`) rendrait le
    terme sur des movers que le natif refuse."""
    from engine import weights as W
    from engine.entities.unit_faction import UnitFaction
    from engine.playbook.non_owner import PurgeResponseNonOwnerPlaybook as PR
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", PR.KEY))
    assert w, "la cle de 1526 rend 0 : la mesure ne pourrait rien contredire"
    owner = {"pos": (2, 2), "vis": "necroWarden"}
    ok = _ctx(unit_faction=int(UnitFaction.LeaguesOfVotann))
    ko = _ctx(unit_faction=int(UnitFaction.Necrons))
    assert _terme(PR, (2, 3), owner, ok, wt) == pytest.approx(w)
    assert _terme(PR, (2, 3), owner, ko, wt) == 0, (
        "un mover NON Votann touche le terme : le gate `HasFaction(case.unit, 0x14)` n'est pas lu")
    # `unit_faction` ABSENT du ctx -> degradation a 0, jamais une exception ni un terme fantome.
    assert _terme(PR, (2, 3), owner, _ctx(), wt) == 0
    # hors adjacence : le gate passe mais `AreEntitiesAdjacent` coupe.
    assert _terme(PR, (7, 7), owner, ok, wt) == 0


def test_MAWCLAWS_le_gate_Summon_est_exerce_OFFLINE_car_le_LIVE_ne_le_PEUT_pas():
    """VERROU STRUCTUREL, et il est ASSERTIONNE -- pas seulement raconte.

    `IsAutomatic(unit) == HasTrait(Summon) || HasTrait(Object)` est le seul filtre de
    `PlayAutomaticUnitsOperation$$Execute`. Donc **tout** mover qui franchit le gate de 1469 est
    automatique : le regime observable de cette face est le tour automatique d'un summon, que
    `aiStepDryRun` ne marche pas. Ce test exerce le gate dans les DEUX sens, plus la redondance du
    `AreFriends` (qui, elle, ne peut jamais couper : le pre-gate l'a deja exigee)."""
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.playbook.non_owner import MawClawsOfThyraxNonOwnerPlaybook as MC
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", MC.KEY))
    assert w, "la cle de 1469 rend 0"
    owner = {"pos": (2, 2), "vis": "tyranTyrantGuard"}
    summon = _ctx(unit_traits=(int(UnitTrait.Summon),))
    pas_summon = _ctx(unit_traits=(int(UnitTrait.Hero),))
    assert _terme(MC, (2, 3), owner, summon, wt) == pytest.approx(w)
    assert _terme(MC, (2, 3), owner, pas_summon, wt) == 0, (
        "un mover NON Summon touche le terme : le gate `HasTrait(case.unit, 0x2)` n'est pas lu")
    assert _terme(MC, (7, 7), owner, summon, wt) == 0, "hors adjacence, le terme doit etre nul"
    # `AreFriends(case.unit, owner, ByCurrentTeam)` == le pre-gate : il ne peut pas couper seul,
    # mais le corps le PORTE, donc le port le porte aussi. `is_friend=False` n'arrive jamais depuis
    # le dispatcher (SLOT_4 est False ici) -- c'est verifie a l'etage suivant.
    assert _terme(MC, (2, 3), owner, summon, wt, is_friend=False) == 0
    # le VERROU lui-meme : le gate de la face et le predicat `IsAutomatic` sont le MEME trait.
    assert int(UnitTrait.Summon) == 2 and int(UnitTrait.Object) == 13, (
        "les ordinaux de `IsAutomatic` ont bouge : le verrou structurel est a re-mesurer")


def test_HAYWIRE_le_gate_HasUnitId_et_les_DEUX_cles_sont_exerces_OFFLINE():
    """Le gate porte sur l'OCCUPANT de la tuile, et les DEUX branches existent.

    Le live ne peut pas offrir le controle (la greffe fait spawner des mines partout) : il est
    exerce ici. Quatre branches, toutes assertionnees :
      * occupant = la mine + porteur AMI    -> `HaywireMine_FriendlyAvoidMine` (-50) ;
      * occupant = la mine + porteur ENNEMI -> `HaywireMine_EnemyAvoidMine`    (-30) ;
      * occupant steppable qui N'EST PAS la mine -> 0 (`HasUnitId` coupe) ;
      * aucun occupant steppable                 -> 0 (`GetSteppableUnit` rend false)."""
    from engine import weights as W
    from engine.playbook.non_owner import HaywireMineNonOwnerPlaybook as HM
    wt = W.load()
    wa = float(wt.sub("TriggeredAbilitiesNonOwner", HM.KEY_FRIENDLY))
    we = float(wt.sub("TriggeredAbilitiesNonOwner", HM.KEY_ENEMY))
    assert wa and we and wa != we, (
        "les deux cles de 1531 doivent etre non nulles ET distinctes (%r / %r) : sinon aucune "
        "mesure ne pourrait separer les branches" % (wa, we))
    mines = HM().mine_unit_ids()
    assert mines, ("`constants.unitToSpawn` de `HaywireMine` est introuvable au gameconfig : le "
                   "gate ne peut plus passer nulle part")
    T = (2, 3)
    owner = {"pos": (9, 9), "vis": "necroWarden"}      # la POSITION du porteur n'est PAS lue
    une_mine = sorted(mines)[0]

    def lc(vis, traits=("Steppable",)):
        return _ctx(friend_units=({"pos": T, "traits": tuple(traits), "triggered": (),
                                   "vis": vis},))

    assert _terme(HM, T, owner, lc(une_mine), wt, is_friend=True) == pytest.approx(wa)
    assert _terme(HM, T, owner, lc(une_mine), wt, is_friend=False) == pytest.approx(we), (
        "la branche ENNEMI rend 0 : c'est l'etat du port AVANT #477-r35, et il coutait -30 par "
        "tuile minee cote natif")
    assert _terme(HM, T, owner, lc("genesSmnDecoy"), wt) == 0, (
        "un steppable qui n'est PAS la mine arme le terme : `HasUnitId` n'est pas lu")
    assert _terme(HM, T, owner, lc(une_mine, traits=("Hero",)), wt) == 0, (
        "un occupant NON steppable arme le terme : `GetSteppableUnit` n'est pas lu")
    assert _terme(HM, T, owner, _ctx(), wt) == 0, "tuile vide -> aucun terme"
    # le regime SPAWN est le residu NOMME de la feuille : les trois corps y rendent 0.
    assert _terme(HM, T, owner, _ctx(is_spawning=True), wt) == 0


def test_le_DISPATCHER_lit_le_slot4_du_PLAYBOOK_et_pas_de_la_FAMILLE():
    """Le pre-gate `playbook.<slot 4> || IsFriend(sujet, owner)`, exerce sur les DEUX cas.

    C'est le foyer que #477-r35 a corrige : il ecartait tous les porteurs ennemis d'un bloc. Deux
    assertions symetriques -- un porteur ENNEMI de 1531 DOIT etre yielde (slot 4 vrai), un porteur
    ENNEMI de 1526 NE DOIT PAS l'etre (slot 4 faux). Les deux sur le MEME dispatcher."""
    from engine import weights as W
    from engine.utilities.tile import TILE_LEAVES
    from engine.utilities.utility_type import UtilityType
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    from engine.entities.unit_faction import UnitFaction
    from engine.playbook.non_owner import (HaywireMineNonOwnerPlaybook as HM,
                                           PurgeResponseNonOwnerPlaybook as PR)
    wt = W.load()
    leaf = TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
    tile = (2, 3)
    mine = sorted(HM().mine_unit_ids())[0]
    occupant = {"pos": tile, "traits": ("Steppable",), "triggered": (), "vis": mine}

    # 1531, porteur ENNEMI : `SLOT_4 = True` -> yielde, avec la cle ENNEMI.
    ctx_hw = _ctx(friend_units=(occupant,),
                  enemy_units=({"pos": (9, 9), "traits": (), "vis": "foe",
                                "triggered": (int(T.HaywireMine),)},))
    got = leaf.evaluate(tile, None, ctx_hw, wt)
    assert got == pytest.approx(float(wt.sub("TriggeredAbilitiesNonOwner", HM.KEY_ENEMY))), (
        "le porteur ENNEMI de 1531 n'a rien verse (%r) : le dispatcher applique encore le pre-gate "
        "`IsFriend` a toute la famille" % got)

    # 1526, porteur ENNEMI : `SLOT_4 = False` -> ECARTE.
    ctx_pr = _ctx(unit_faction=int(UnitFaction.LeaguesOfVotann),
                  enemy_units=({"pos": (2, 2), "traits": (), "vis": "foe",
                                "triggered": (int(T.PurgeResponse),)},))
    assert leaf.evaluate(tile, None, ctx_pr, wt) == 0, (
        "le porteur ENNEMI de 1526 a verse son terme : le `<slot 4>` a ete relache pour TOUTE la "
        "famille au lieu d'etre lu par classe -- l'erreur SYMETRIQUE de celle qu'on corrige")
    # et le MEME porteur, AMI, verse bien.
    ctx_pr_ami = _ctx(unit_faction=int(UnitFaction.LeaguesOfVotann),
                      friend_units=({"pos": (2, 2), "traits": (), "vis": "ami",
                                     "triggered": (int(T.PurgeResponse),)},))
    assert leaf.evaluate(tile, None, ctx_pr_ami, wt) == pytest.approx(
        float(wt.sub("TriggeredAbilitiesNonOwner", PR.KEY)))


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- live : l'accord natif/port, et la contre-epreuve
# ---------------------------------------------------------------------------------------------
def test_le_montage_a_bien_ete_mesure(r37_case):
    rows = _rows(r37_case)
    assert rows, "aucune tuile hookee : rien n'est confronte"


def test_accord_natif_port_sur_toutes_les_tuiles_hookees(r37_case):
    """`X = Tile(7) - Elevation - TileEffects` doit valoir la somme des feuilles portees."""
    rows = _rows(r37_case)
    mauvais = [(r["tile"], r["x_nat"], r["x_port"]) for r in rows
               if r["x_nat"] is None or abs(r["x_nat"] - r["x_port"]) > 1e-6]
    assert not mauvais, (
        "%d tuile(s) en desaccord sur %d (%s/%s/%s) : %r"
        % (len(mauvais), len(rows), r37_case.board, r37_case.seed, r37_case.montage, mauvais[:6]))


def test_le_montage_SEPARE_ses_mutants_et_publie_ceux_qu_il_ne_separe_pas(r37_case):
    """Un accord obtenu en regime DEGENERE ne prouve rien.

    On exige que les mutants ATTENDUS mordent, et on VERIFIE que la liste des attendus est bien
    celle du montage -- un mutant qui ne separe rien ici est publie par le probe, jamais tu."""
    rows = _rows(r37_case)
    mordu = P.divergences(rows)
    attendus = MUTANTS_ATTENDUS[r37_case.montage]
    muets = [m for m in attendus if not mordu.get(m)]
    assert not muets, (
        "mutant(s) %r inertes sur %s/%s/%s : le montage n'exerce pas leur axe, donc l'accord n'y "
        "prouve rien. Divergences mesurees : %r"
        % (muets, r37_case.board, r37_case.seed, r37_case.montage, mordu))
    assert not mordu.get("PORT"), (
        "le modele `PORT` diverge de lui-meme : la mesure est incoherente")


def test_le_gate_du_montage_fait_ce_qu_il_annonce(r37_case):
    """Les montages `*-gate` doivent COUPER ; `haywire` doit passer sur la (les) tuile(s) minee(s).

    Assertionne DANS LES DEUX SENS : un `*-gate` dont le gate passerait ne controlerait rien, et un
    `haywire` sans tuile minee hookee ne mesurerait rien."""
    rows = _rows(r37_case)
    if r37_case.montage in P.MONTAGES_GATE_COUPE:
        actifs = [r["tile"] for r in rows if r["gate"]]
        assert not actifs, (
            "le gate PASSE sur %r alors que ce montage est le CONTROLE : le mover choisi franchit "
            "le gate, donc l'inertie declaree des autres mutants est fausse" % actifs)
    elif r37_case.montage == "haywire":
        assert any(r["gate"] for r in rows), (
            "aucune tuile hookee ne porte la mine : le gate `HasUnitId` n'a jamais passe, et "
            "l'accord porte alors sur un terme uniformement nul")
    else:
        assert all(r["gate"] for r in rows), (
            "le gate ne passe pas partout alors que le mover devrait le franchir")
