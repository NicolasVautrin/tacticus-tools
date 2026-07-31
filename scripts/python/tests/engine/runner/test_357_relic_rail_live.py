"""GARDE LIVE #357 -- le port LIT-IL la relique EQUIPEE, et au bon NIVEAU ?

#237 a livre le MONTAGE d'une relique (`rl_duel build --equip-relic`), pas sa LECTURE : le rail
COMBAT derivait le kit declenche du gameconfig, qui ignore par construction l'item equipe
(`BattleConfiguration.Units[].TertiaryAbility`), etat JOUEUR et non donnee de kit. Une relique
montee etait donc INERTE cote port, SANS erreur ni trace.

CE QUE CES GARDES EXIGENT, ET DE QUEL ARTEFACT NATIF
  * `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` monte l'ability tertiaire par
    `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)`
    -> `snapshot._load_tertiary_abilities` lit ces entrees de hierarchie **3** et
    `collect_triggered_abilities` les inscrit (CINQUIEME chemin de registration) ;
  * `IdunBattle.Entities.Factories.UnitFactory$$Build` fabrique le `tertiaryAbilityState` depuis
    `UnitConfiguration+0xc0` (`TertiaryAbilityLevel`) et `+0x78`
    (`TertiaryAbilityVariablesMultiplierPercentage`) -- PAS `+0xbc`/`+0x74`, qui servent aux passifs
    -> `triggers/base.py::triggered_ability_state` rend le couple TERTIAIRE, et
    `AbilityConfiguration$$GetVariableForLevel` l'indexe.

Relique choisie : `DawnBlade` (1501). Son behaviour est deja porte (#317), donc ce qui est mesure
ici est LE RAIL et rien d'autre ; et son effet est un ENTIER lisible a l'etat
(`Repair(self, self, Get(hpToHeal[lvl]), ForRepair)` sur un kill en melee), pas un modificateur
noye dans une plage de degat.

Montage : `probe_357_relic_rail.py`, via la fixture `relic_rail_case`. ASCII only.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import probe_357_relic_rail as RELIC


def _hp_to_heal(level: int) -> int:
    from engine.entities.effects.magnitude import ability_var
    return int(ability_var(RELIC.RELIC, "hpToHeal", level, multiplier_pct=100) or 0)


@pytest.mark.parametrize("level", [8, 3])
def test_le_natif_repare_le_palier_de_la_relique_et_le_port_le_suit(relic_rail_case, level):
    """L'ACCORD, sur DEUX niveaux : natif == port == `hpToHeal[TertiaryAbilityLevel]`.

    Deux niveaux et pas un : au palier 10 (ce que rendrait une lecture du niveau PASSIF, clampe)
    l'accord serait le meme pour les deux, donc un seul bras ne separerait rien."""
    r = relic_rail_case(level)
    exp = _hp_to_heal(level)
    assert exp > 0, "hpToHeal introuvable dans le gameconfig de %s" % RELIC.RELIC
    assert r["victim_dead"], (
        "la victime n'est pas morte : sans kill, `On(UnitDeath)` n'est jamais emis et la mesure "
        "ne porte sur rien (%s)" % (r.get("attack_ack"),))
    assert r["native_delta"] == exp, (
        "NATIF : le porteur a gagne %d PV, attendu hpToHeal[%d] = %d"
        % (r["native_delta"], level, exp))
    assert r["port"]["repaired"] == exp, (
        "PORT : repare %s, attendu %d -- le rail de la relique EQUIPEE ne rend pas le bon palier"
        % (r["port"]["repaired"], exp))
    assert r["port"]["hp_delta"] == r["native_delta"], (
        "les PV du porteur ne bougent pas du meme montant des deux cotes : port %s vs natif %s"
        % (r["port"]["hp_delta"], r["native_delta"]))


def test_sans_le_canal_le_port_est_inerte(relic_rail_case):
    """CONTRE-EPREUVE 1 -- l'etat d'AVANT #357, rejoue sur LA MEME capture.

    `load_state(ability_states=False)` : le rail ne voit que le gameconfig, donc `tauFarsight`
    (dont le kit gameconfig ne porte PAS `DawnBlade` -- seuls les 5 npc `*Farsight` l'ont en dur)
    n'inscrit AUCUN trigger. Sans ce bras, le test ci-dessus serait un vert que rien ne fait
    rougir.

    ⚠ `False`, PAS `None` : depuis #363 le canal est ACTIF PAR DEFAUT des qu'un transport ambiant
    est lie -- et sous pytest il l'est (`conftest.live_session`). Un `None` ici ferait re-tirer le
    payload par ce bras meme, qui rendrait alors le MEME resultat que le nominal : la contre-epreuve
    deviendrait un vert qui ment."""
    r = relic_rail_case(8)
    assert r["port"]["tertiary"] == RELIC.RELIC, (
        "le canal ne seede pas `UnitContext.tertiary_ability` (lu : %s)" % r["port"]["tertiary"])
    assert r["port_no_rail"]["tertiary"] is None, (
        "sans le canal, `tertiary_ability` devrait rester None, lu %s"
        % r["port_no_rail"]["tertiary"])
    assert r["port_no_rail"]["events"] == 0 and r["port_no_rail"]["repaired"] == 0, (
        "sans le canal #357 le port ne doit RIEN reparer (etat d'avant), or il rend %s"
        % (r["port_no_rail"],))
    assert r["native_delta"] > 0, "le natif, lui, repare -- c'est bien un ECART que #357 ferme"


@pytest.mark.parametrize("level", [8, 3])
def test_le_niveau_lu_est_le_tertiaire_pas_celui_des_passifs(relic_rail_case, level):
    """CONTRE-EPREUVE 2 -- l'etat d'AVANT sur l'axe MAGNITUDE.

    `passive_ability_level` vaut 50 sur tout runner normalise ; `AbilityConfiguration$$
    TryGetVariableArrayForLevel` CLAMPE au dernier palier -> une lecture du niveau passif rend
    TOUJOURS `hpToHeal[10]`, quel que soit le niveau reel de la relique. Le bras mute doit donc
    diverger du natif -- sinon le montage ne separe pas les deux champs."""
    r = relic_rail_case(level)
    exp, clamped = _hp_to_heal(level), _hp_to_heal(50)
    assert clamped != exp, (
        "niveau %d : le palier demande vaut le palier clampe (%d) -- ce niveau ne separe RIEN, "
        "changer de bras" % (level, exp))
    assert r["port"]["level"] == level, (
        "`UnitContext.tertiary_ability_level` = %s, attendu %d" % (r["port"]["level"], level))
    assert r["port_passive_level"]["repaired"] == clamped, (
        "le bras mute devrait rendre le palier CLAMPE %d (niveau passif 50), il rend %s"
        % (clamped, r["port_passive_level"]["repaired"]))
    assert r["port_passive_level"]["repaired"] != r["native_delta"], (
        "la contre-epreuve ne rougit pas : lire le niveau des PASSIFS donne le meme resultat que "
        "le natif au niveau %d -- le montage ne separe pas les deux champs" % level)


def test_le_multiplicateur_tertiaire_est_un_champ_DISTINCT_du_multiplicateur_dability(
        relic_rail_case):
    """`UnitConfiguration+0x78` (tertiaire) vs `+0x74` (actif/passif) -- DEUX champs, DEUX valeurs.

    Mesure a DEUX sources independantes : l'`AbilityState` MONTE (`unitAbilityStates`, `+0x24` de
    l'instance `TriggeredAbility`) et la CONFIG (`combatSnapshot.unitConfig`). Elles doivent
    coincider -- c'est ce qui autorise a seeder le port depuis la premiere. Et le multiplicateur
    d'ability (`+0x74`) doit, lui, DIFFERER : sans ce contraste, l'egalite ci-dessus serait
    triviale (tout vaudrait 100)."""
    r = relic_rail_case(8)
    mounted, cfg = r["mounted"], r["unit_config"]
    assert mounted["abilityId"] == RELIC.RELIC_ID and mounted["level"] == 8, (
        "l'entree de hierarchie 3 lue n'est pas celle attendue : %s" % (mounted,))
    assert mounted["mult"] == cfg["tertiaryMult"], (
        "l'AbilityState monte porte mult=%s alors que `unitConfig.tertiaryAbilityVariables"
        "Multiplier` vaut %s -- les deux sources du MEME champ +0x78 divergent"
        % (mounted["mult"], cfg["tertiaryMult"]))
    assert r["port"]["mult"] == mounted["mult"], (
        "`UnitContext.tertiary_ability_variables_multiplier` = %s, mesure %s"
        % (r["port"]["mult"], mounted["mult"]))
    assert cfg["abilityMult"] != cfg["tertiaryMult"], (
        "+0x74 (%s) et +0x78 (%s) portent la MEME valeur sur ce montage : il ne peut pas etablir "
        "que le port lit le bon champ -- choisir un porteur dont les deux different"
        % (cfg["abilityMult"], cfg["tertiaryMult"]))


@pytest.mark.parametrize("regime,gate", [
    ("ranged", "IsDefeatedByMeleeAttack -- un kill A DISTANCE ne declenche rien"),
    ("fullhp", "AttackQuery$$EntityCanBeRepaired -- un porteur a PV PLEINS ne recupere rien"),
])
def test_le_rail_ne_rend_pas_le_port_permissif(relic_rail_case, regime, gate):
    """LES DEUX NEGATIFS -- inscrire la relique ne doit pas faire firer ce que le natif REFUSE.

    C'est l'autre facon de se tromper, et la plus dangereuse : on aurait echange une degradation
    MUETTE (rien ne se declenche) contre une degradation PERMISSIVE (tout se declenche), que rien
    dans le regime nominal ne verrait. Le contraste porte : SUR LE MEME MONTAGE, `melee` rend
    `hpToHeal[8]` des deux cotes, ces deux regimes rendent 0 des deux cotes."""
    nominal = relic_rail_case(8)
    r = relic_rail_case(8, regime)
    assert r["victim_dead"], "la victime n'est pas morte : le regime ne mesure rien (%s)" % gate
    assert r["port"]["tertiary"] == RELIC.RELIC, (
        "la relique n'est pas montee dans ce regime -- le refus viendrait du montage, pas du gate")
    assert r["native_delta"] == 0, (
        "NATIF : le porteur a gagne %d PV alors que le gate devrait REFUSER (%s)"
        % (r["native_delta"], gate))
    assert r["port"]["repaired"] == 0, (
        "PORT : %s PV repares alors que le natif refuse (%s)" % (r["port"]["repaired"], gate))
    assert nominal["native_delta"] > 0, (
        "le regime NOMINAL du meme montage ne repare rien non plus : les zeros ci-dessus ne "
        "prouveraient alors rien (montage inerte, pas gate qui mord)")


def test_une_relique_portee_par_les_DEUX_voies_n_est_inscrite_qu_une_fois():
    """DEDUPLICATION -- mirror du `TryAdd` sur `KeyedCollection` (natif : la 2e insertion est un
    no-op). Un npc peut porter `DawnBlade` EN DUR (`gameconfig.relicAbilities`) et se la voir
    EQUIPER par un montage : le port doit alors inscrire UN trigger, pas deux -- sinon la
    reparation serait DOUBLEE, en silence.

    OFFLINE et deterministe : la question est le CABLAGE du collecteur, elle se tranche sur un
    `State` nu (meme choix que `probe_317`)."""
    import gameconfig as GC
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import StatsComponent, UnitComponent
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.dawn_blade import DawnBladeHealAbility
    from engine.runner.state import State

    npc = "tauNpcFarsight"
    assert RELIC.RELIC in ((GC.unit(npc) or {}).get("relicAbilities") or []), (
        "%s ne porte plus %s en dur : choisir un autre porteur `relicAbilities`" % (npc, RELIC.RELIC))

    def _count(vis: str, tertiary):
        st = State()
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        ctx = UnitContext(entity_id=e.id, visual_id=vis)
        ctx.tertiary_ability = tertiary
        ctx.tertiary_ability_level = 8 if tertiary else 0
        e.add_component(StatsComponent(ctx=ctx))
        return sum(1 for x in collect_triggered_abilities(st)
                   if isinstance(x, DawnBladeHealAbility))

    assert _count(npc, None) == 1, "la voie gameconfig `relicAbilities` n'inscrit plus rien"
    assert _count("tauFarsight", RELIC.RELIC) == 1, (
        "la voie TERTIAIRE (relique EQUIPEE) n'inscrit pas le trigger")
    assert _count("tauFarsight", None) == 0, (
        "sans relique equipee, `tauFarsight` ne doit porter AUCUN trigger DawnBlade")
    assert _count(npc, RELIC.RELIC) == 1, (
        "porteur des DEUX voies : le trigger est inscrit DEUX fois -> reparation doublee")


def test_le_rail_lit_bien_la_voie_tertiaire_dans_le_collecteur():
    """GARDE DE CABLAGE (par AST + source, meme forme que la garde `relicAbilities` de #317) :
    si quelqu'un retire la branche, le trigger redevient un no-op SILENCIEUX."""
    from engine.runner.operations.triggers.dispatch import core
    src = inspect.getsource(core.collect_triggered_abilities)
    assert "tertiary_ability" in src and "RELIC_ABILITY_TRIGGERS" in src, (
        "collect_triggered_abilities ne lit plus `UnitContext.tertiary_ability` -> une relique "
        "EQUIPEE n'est plus inscrite")
    p = (Path(__file__).resolve().parents[3] / "engine" / "runner" / "snapshot.py")
    tree = ast.parse(p.read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_load_tertiary_abilities" in names, "le seed du canal tertiaire a disparu de snapshot.py"
    ls = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "load_state")
    kwonly = {a.arg for a in ls.args.args} | {a.arg for a in ls.args.kwonlyargs}
    assert "ability_states" in kwonly, "load_state n'expose plus le canal `ability_states`"


def test_un_etat_charge_hors_harnais_live_ne_change_pas_de_comportement():
    """CE QUE #363 A DEPLACE, ET CE QU'IL N'A PAS DEPLACE.

    #357 avait fait de ce canal un OPT-IN et le verrouillait par construction (`if ability_states is
    not None:` dans `load_state`). #363 l'a rendu ACTIF PAR DEFAUT -- mais seulement quand un
    transport RPC ambiant est lie. Le contrat que cette garde protegeait vraiment TIENT donc
    toujours, et c'est LUI qu'on verrouille ici plutot que la forme du `if` :

      un `State` reconstruit HORS harnais live (aucun `bind_live_rpc` -- rejeu d'une capture sur
      disque, test unitaire, outil offline) se comporte EXACTEMENT comme avant #357.

    Mesure, pas lecture de source : on demande a la resolution du tri-etat ce qu'elle rend."""
    from engine.runner import snapshot as S
    prev = S.unbind_live_rpc()
    try:
        assert S._auto_ability_states(None, {"runner": "build#1"}, {}, {}) == (None, "no-transport")
    finally:
        S.bind_live_rpc(prev)
    from engine.entities.unit_context import UnitContext
    fresh = UnitContext(entity_id=1)
    assert (fresh.tertiary_ability, fresh.tertiary_ability_level,
            fresh.tertiary_ability_variables_multiplier) == (None, 0, 100), (
        "les defauts du ctx ne sont plus neutres : une unite sans relique porterait un etat")


def test_le_refus_explicite_reste_exprimable():
    """L'AUTRE moitie de ce que #363 a change : `None` ne veut plus dire « pas de canal ».

    Sans un refus EXPRIMABLE, la contre-epreuve « sans rail » de ce fichier deviendrait, sous
    pytest, identique au bras nominal -- un vert qui ment. `False` est ce refus, et cette garde
    verrouille qu'il existe encore."""
    from engine.runner import snapshot as S
    assert S._auto_ability_states(False, {"runner": "build#1"}, {}, {}) == (None, "refused")
    src = inspect.getsource(RELIC._port_repair)
    assert "ability_states=False" in src or "`False`" in src, (
        "le probe #357 ne documente plus le refus explicite -- le bras `no-rail` risque de "
        "re-tirer le payload tout seul")
