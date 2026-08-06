"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r4 -- `On(0x35 = PostUnitKill)` entre dans la SEQUENCE DE MORT.

CE QUE CE FICHIER VERROUILLE. Le 5e evenement de
`IdunBattle.Operations.KillUnitOperation$$Execute` etait publie par
`move_death.py::post_unit_kill_triggers_for_move`, en tete d'`after_move_triggers` : donc PLUS TARD
que le natif (apres `UpdateCharging` / `SetMovedFlag`) et pour le SEUL crush-par-move. Double ecart,
d'ORDRE et de COUVERTURE. Il vit desormais dans le foyer `damage.py::_kill_unit_operation`, a son
rang natif.

LE RANG SE LIT A LA PILE D'ACCOLADES, PAS A LA PROFONDEUR -- et c'est le coeur de la tranche. Les
quatre derniers events sont TOUS a la profondeur 9, ce qui avait fait ecrire, dans la docstring de
`test_revive_cancels_death_events_live.py`, << TOUS a l'interieur de ce bloc, sans `else` >>. Les
piles, elles, discriminent (decompile `rnca9r7q6c`) :

    L1111  if (unitComponent != null) {
    L1131      if (!PendingRevive.HasValue) {          <- pile de On(2), On(0), On(0x36)
                   ...
    L1971          if (health.hp > 0) return;          <- GARDE HEAL
                   RemoveEffects(2) ; processor.<slot 0x55>
    L1997      } else { matchState.<slot 0x63>(killed) }
               PendingRevive@+0xa8..+0xe8 = 0
    L2033      if (dispatcher != null) { On(0x35) ; return }   <- pile de On(0x35)

TROIS CONSEQUENCES, une par bras STRUCTURE : (1) la branche REVIVE le publie aussi ; (2) la GARDE
HEAL le saute ; (3) aucun octet de `KillUnitOptions` ne le gate, donc il part pour les TROIS voies
du port (degat / crush / `KillUnitBehaviour`).

LE BRAS LIVE confronte le seul consommateur PORTE, `CosmicHorrorOnMoveAbility`, sur le seul regime
ou il soit atteignable en bataille (le Patermine marche sur son propre decoy) : le heal doit avoir
lieu UNE FOIS, et depuis `MoveUnitOperation.execute` -- pas depuis `after_move_triggers`. Le
NON-DOUBLON est la garantie neuve : deplacer une emission sans retirer l'ancienne est le mode de
panne exact de cette tranche, et une assertion d'ENSEMBLE y est structurellement aveugle.

CE QUI N'EST PAS CONFRONTE LIVE, et le dire fait partie du livrable : les trois autres voies. Le
trigger natif `CosmicHorror_OnMoveAbility$$CreateTrigger` ne porte AUCUNE gate de mouvement (relu
nœud par nœud), donc le natif soigne aussi sur une mort par DEGAT -- mais le kit du Patermine
(`Eviscerate`, 5 coups melee, aucune AoE friendly-fire) ne permet pas de le rendre tueur d'un
allie `Decoy` autrement qu'en marchant dessus. Le bras `--step consommateur` du probe MONTE ce
regime, il ne le RENCONTRE pas.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r4_post_unit_kill as P
from engine.dsl.event_trigger_type import EventTriggerType
from engine.runner.components import HealthComponent, UnitComponent

PATRIARCH_VIS = "genesPatriarch"
POST_UNIT_KILL = int(EventTriggerType.PostUnitKill)


# ================================================================================================
# (a) STRUCTURE -- le rang, ses deux gardes, et le cliquet du foyer
# ================================================================================================
@pytest.mark.parametrize("nom,fn", [(n.strip(), f) for n, f in P.VOIES],
                         ids=[n.split()[0] for n, _f in P.VOIES])
def test_les_cinq_events_partent_dans_l_ordre_natif(nom, fn):
    """Les CINQ events, DANS L'ORDRE, sur les TROIS voies qui traversent le foyer.

    `On(0x35)` n'etait le 5e sur AUCUNE d'elles : le crush-par-move le recevait APRES coup (donc
    hors de ce montage, qui n'appelle pas le pipeline de move), les deux autres pas du tout."""
    vus, _st, killer, mort = fn()
    assert vus == list(P.ORDRE_NATIF), (
        "voie %s : sequence %s, attendue %s (ordre du decompile : +0x7cc, +0x979, +0xe49, +0xefc, "
        "+0x10ac). killer=%s mort=%s" % (nom, P._fmt(vus), P._fmt(P.ORDRE_NATIF), killer, mort))


def test_la_branche_revive_publie_post_unit_kill_et_lui_seul():
    """CONSEQUENCE 1 -- `On(0x35)` est le SEUL des cinq que la garde revive n'annule pas.

    C'est ce que la pile d'accolades dit et que la profondeur cachait. Un port qui traiterait la
    garde revive comme un `return` sec (l'etat d'AVANT) rendrait `[On(1)]` : c'est exactement la
    contre-epreuve `--mutate revive-sec`, dont ce test est la face positive."""
    assert P.step_revive() == 0, (
        "la branche revive ne publie pas `On(0x35 = PostUnitKill)` seul apres `On(1)`. Le natif "
        "sort du `if/else` de la garde AVANT de le publier (pile `L2033`, pas `L1131`).")


def test_la_garde_heal_saute_post_unit_kill():
    """CONSEQUENCE 2 -- un consommateur qui SOIGNE le mourant arme `if (health.hp > 0) return;`
    @+0xf35, dont le `return` precede `On(0x35)`. Le TEMOIN (meme montage, aucun soin) rend les
    cinq : sans lui, un zero ne distinguerait pas << la garde mord >> de << rien n'est emis >>."""
    assert P.step_garde_heal() == 0, (
        "la garde HEAL ne saute pas `On(0x35 = PostUnitKill)`, ou le TEMOIN ne rend pas les cinq.")


def test_un_seul_emetteur_de_post_unit_kill():
    """CLIQUET (AST) -- l'event doit partir d'UN SEUL site : le foyer `_kill_unit_operation`.

    C'est la garde de RECHUTE de cette tranche. Un second appelant -- typiquement un vecteur de
    pipeline, comme l'etait `after_move_triggers` -- republierait l'event a un rang qui n'est pas
    le sien ET le DOUBLERAIT pour la voie concernee : deux heals du Patermine pour un crush."""
    sites = P.appelants_du_vecteur()
    assert sites == [P.FOYER], (
        "appelants de `post_unit_kill_triggers` : %r ; attendu le seul foyer %r. Un intrus rouvre "
        "l'ecart d'ORDRE que cette tranche ferme ; une absence rend l'event MUET." % (sites, P.FOYER))


def test_le_consommateur_porte_voit_les_deux_voies():
    """CONSEQUENCE 3 -- `CosmicHorrorOnMoveAbility` soigne du MEME montant que la mort vienne du
    CRUSH ou du DEGAT. Le second bras est celui que le port n'atteignait pas : il rendait delta=0.

    Le trigger natif ne porte aucune gate de mouvement -- c'est le decompile qui le dit, pas le nom
    de la classe. Ce test FIGE cette lecture cote port."""
    assert P.step_consommateur() == 0, (
        "le Patermine ne se soigne pas sur l'une des deux voies. La voie DEGAT est celle que "
        "`post_unit_kill_triggers_for_move` ne pouvait pas atteindre.")


# ================================================================================================
# (b) LIVE -- le consommateur porte, sur le seul regime atteignable en bataille
# ================================================================================================
BUILD = ["--p-units", f"{PATRIARCH_VIS},genesPrimus", "--a-units", "ultraTitus",
         "--rank", "17", "--board", "MC1_67"]


@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indispo -- montage a reparer"
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    cs = rpc("combatSnapshot", {"runnerId": rid}, 90)
    yield {"rid": rid, "board": board, "dv": dv, "ob": ob, "cs": cs, "rpc": rpc}


def _fresh(env):
    from engine.runner.snapshot import load_state
    return load_state(env["dv"], env["ob"], env["cs"], board=env["board"])


def _by_vis(st, vis):
    from engine.runner.components import StatsComponent
    for uid, e in st.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            uc = e.get_component(UnitComponent)
            if uc is not None and uc.alive:
                return uid
    return None


def test_le_heal_du_patermine_part_du_crush_et_une_seule_fois(env, monkeypatch):
    """LIVE, le seul consommateur PORTE d'`On(0x35)` sur le seul regime ou il soit atteignable.

    Trois choses a la fois, et la troisieme est NEUVE :
      * le heal a lieu (non-regression : il avait deja lieu, par un autre emetteur) ;
      * il part DANS `MoveUnitOperation.execute` -- donc avant que quoi que ce soit du pipeline
        after-move ne tourne. C'est l'ecart d'ORDRE, rendu observable par le COMPTEUR pris entre
        les deux appels ;
      * il ne part QU'UNE FOIS. Deplacer une emission sans retirer l'ancienne est le mode de panne
        de cette tranche, et l'ancien emetteur (`after_move_triggers`) est toujours appele ici.

    Les positions sont DEPLACEES (`spawn_decoy` sur une tuile adjacente choisie) plutot que subies :
    la geometrie de spawn ne decide de rien."""
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.spawn import spawn_decoy
    from engine.runner.operations.triggers.dispatch.move_death import after_move_triggers
    from engine.runner.operations.triggers.loki import cosmic_horror as CH
    from engine.runner.components import PositionComponent

    st = _fresh(env)
    board = env["board"]
    pat = _by_vis(st, PATRIARCH_VIS)
    assert pat is not None, "genesPatriarch absent du runner -- montage a reparer, pas a skipper"
    hc = st.get_entity(pat).get_component(HealthComponent)
    assert hc is not None and hc.hp_max, "Patermine sans HealthComponent -> heal non observable"
    hc.hp = max(1, int(hc.hp_max) // 4)                  # blesse : le heal doit se voir
    pc = st.get_entity(pat).get_component(PositionComponent)
    tile_a = board.id_at(pc.col, pc.row)
    occ = {(p.col, p.row) for p in
           (e.get_component(PositionComponent) for e in st.entities.values())
           if p is not None}
    tile_b = next((n for n in sorted(board.neighbours(tile_a))
                   if board.coord(n) not in occ and board.walkable(n)), None)
    assert tile_b is not None, "aucune tuile libre adjacente -- DEPLACER le Patermine, pas skipper"
    did = spawn_decoy(st, tile_b, pat)
    assert did is not None, "spawn_decoy a rendu None (pre-cond)"

    vus = []
    orig = CH.CosmicHorrorOnMoveAbility.execute_behaviour
    monkeypatch.setattr(CH.CosmicHorrorOnMoveAbility, "execute_behaviour",
                        lambda self, state, ev: (vus.append(dict(ev=int(ev.event_id),
                                                                 tgt=ev.target_id)),
                                                 orig(self, state, ev))[1])
    hp0 = int(hc.hp)
    MoveUnitOperation(pat, board.coord(tile_b)).execute(st, EventBus())
    pendant_move = len(vus)
    after_move_triggers(st, pat)
    total = len(vus)

    assert st.get_entity(did).get_component(UnitComponent).alive is False, \
        "le decoy n'a pas ete crushe -- le bras est VIDE"
    assert pendant_move == 1, (
        "`CosmicHorror_OnMove` a fire %d fois PENDANT `MoveUnitOperation.execute` (attendu 1). "
        "L'event doit partir de la sequence de mort du crush, a son rang natif." % pendant_move)
    assert total == 1, (
        "`CosmicHorror_OnMove` a fire %d fois au total : `after_move_triggers` republie `On(0x35)` "
        "alors que le foyer le publie deja -> DOUBLE heal pour UN crush." % total)
    assert vus[0]["ev"] == POST_UNIT_KILL and vus[0]["tgt"] == did, (
        "le fire ne porte pas {event = On(0x35), target = le decoy crushe} : %r" % (vus[0],))
    assert int(hc.hp) > hp0, "aucun heal applique (hp %d -> %s)" % (hp0, hc.hp)


# ================================================================================================
# (c) LIVE -- le NATIF publie-t-il `On(0x35)` sur une mort par DEGAT ? (mesure DIRECTE)
# ================================================================================================
#
# Le consommateur porte (`CosmicHorrorOnMoveAbility`) n'est atteignable que par le CRUSH : le kit
# du Patermine n'a aucune AoE friendly-fire, donc rien ne le rend tueur d'un allie `Decoy`
# autrement qu'en marchant dessus. Le regime DEGAT serait DEGENERE cote port -- et un accord en
# regime degenere ne prouve rien. On sort donc du regime en changeant de CONSOMMATEUR.
#
# `Lakrimae_SummonPoxwalker_Ability` (relique `Lakrimae`, porteur `deathTyphus`, DANS le pool) est
# le consommateur natif qu'il faut : son `CreateTrigger`, lu nœud par nœud sur `rnca9r7q6c`, porte
#
#     On(0x35, ignoreOverkill=1) & AreEnemies(Owner, Target) & IsDead(Target) & <owner-is-actor>
#       & NOT TriggeringAbilityIs(<implicit>) & IsCanAddUnit(FreeTilesOrAdjacentFreeTiles(Target))
#       & NOT IsObjectOrSteppable(Target) & NOT HasTrait(Target, 5 = Mechanical)
#       & NOT AmountIsEqualOrGreater(Filter(AllUnits, AreFriends & IsUnitWithVisualId(<const 0>)),
#                                    Get(<const 0x78>))
#       & IsInRange(Owner, Target, ContagionsOfNurgleRange(Owner, 1, 0))
#
# et son `NOT IsObjectOrSteppable(Target)` EXCLUT structurellement le crush. Un Poxwalker qui
# apparait est donc la preuve DIRECTE que le natif a publie `On(0x35)` pour une mort par DEGAT.
# L'ability n'est PAS portee : ce bras mesure le NATIF, il ne confronte pas un port.
RELIC_BUILD = ["--p-units", "deathTyphus,deathPutrifier",
               "--rank", "17", "--board", "MC1_67", "--hp-target", "1",
               "--place", "deathTyphus:3,4", "--place", "deathPutrifier:0,0",
               "--a-place", "worldJakhal:6,8"]
POXWALKER_VIS = "deathPoxwalker"


def _poxwalkers(rpc, rid) -> list:
    """Les `deathPoxwalker` VIVANTS de la vue decision -- l'observable du trigger natif."""
    dv = rpc("decisionView", {"runnerId": rid}, 90)
    units = (dv or {}).get("units") or []
    return [u for u in units if u.get("visualId") == POXWALKER_VIS]


@pytest.mark.parametrize("relic,ennemi,attendu", [
    (True, "orksNob", 1),        # POSITIF     : non-mecanique, adjacent -> un Poxwalker
    (False, "orksNob", 0),       # TEMOIN      : meme mort, pas de relique -> aucun
    (True, "necroWarden", 0),    # CONTRE-EPR. : `NOT HasTrait(Target, 5 = Mechanical)` refuse
], ids=["POSITIF-non-mecanique", "TEMOIN-sans-relique", "CONTRE-mecanique"])
def test_le_natif_publie_post_unit_kill_sur_une_mort_par_degat(live_session, rpc, build_runner,
                                                               relic, ennemi, attendu):
    """MESURE NATIVE du chemin DEGAT -- ce que le decompile annonce, confirme en bataille.

    L'ennemi est place ADJACENT a Typhus avec `--hp-target 1` (PV 1, armure 0) : il meurt du degat
    d'aura/DoT de Nurgle des l'ouverture, killer = Typhus. Aucun mouvement, aucun crush.

    Les TROIS bras sont necessaires et chacun tombe pour une raison DIFFERENTE :
      * sans la relique, le mort est le MEME -> ce n'est pas la mort qui invoque, c'est le trigger ;
      * avec un ennemi `Mechanical`, la relique est la et le mort aussi -> c'est bien CE trigger,
        avec SES gates, et non un effet de bord du montage.
    Sans eux, un Poxwalker observe ne prouverait rien (mesure faite : les deux mordent).

    `worldJakhal` (1 PV lui aussi, mais LOIN) reste vivant dans les trois bras : temoin gratuit du
    gate `IsInRange(Owner, Target, ContagionsOfNurgleRange)`."""
    extra = list(RELIC_BUILD) + ["--a-units", f"{ennemi},worldJakhal",
                                 "--a-place", f"{ennemi}:3,5"]
    if relic:
        extra += ["--equip-relic", "deathTyphus:Lakrimae:50"]
    rid = build_runner("777", extra=extra)["rid"]
    pox = _poxwalkers(rpc, rid)
    dv = rpc("decisionView", {"runnerId": rid}, 90)
    vivants = sorted((u.get("visualId"), u.get("alive")) for u in (dv or {}).get("units") or [])
    assert not any(v == ennemi and a for v, a in vivants), (
        "l'ennemi %s est encore VIVANT : le montage ne produit AUCUNE mort, le bras est VIDE "
        "(vue : %r)" % (ennemi, vivants))
    assert len(pox) == attendu, (
        "relique=%s ennemi=%s : %d `%s` sur le plateau, attendu %d. Le trigger natif "
        "`Lakrimae_SummonPoxwalker` n'ecoute QUE `On(0x35 = PostUnitKill)` et REFUSE un "
        "`Object`/`Steppable` -- un Poxwalker ici est la preuve que le natif publie cet event "
        "pour une mort par DEGAT. Vue : %r" % (relic, ennemi, len(pox), POXWALKER_VIS, attendu,
                                               vivants))
