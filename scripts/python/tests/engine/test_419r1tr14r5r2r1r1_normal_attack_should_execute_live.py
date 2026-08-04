"""#419-r1-tr14-r5-r2-r1-r1 -- le gate `ShouldExecute` des playbooks d'ATTAQUE NORMALE.

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
appelle le slot de vtable **+0x328** apres avoir somme `CalculateCustomUtility` et
`CalculateUtilityFromPredictions`, et AVANT les trois termes positionnels. `false` -> `Nullable`
VIDE : aucune action pour ce (tuile, cible). Les deux corps, lus verbatim :

    // IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$ShouldExecute
    if (UnitExtensions.HasTriggeredAbility(target, 0x48)) return false;   // 0x48 = 72 = Explosive
    return attackHealUtility > Fix64(0);

    // IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$ShouldExecute
    return attackHealUtility > Fix64(0);

CE QUE CE FICHIER GARDE -- six choses, aucune redondante :

  1. **LE LITTERAL ET SA CLASSE** (cran OFFLINE). `0x48` = 72 = `Explosive` dans
     `IdunBattle.Entities.Enum.TriggeredAbilityType`, et il porte sur la **CIBLE** (4e argument de
     `ShouldExecute(this, caster, casterTile, target, attackHealUtility)`). Le gate lit AUSSI
     `utility > 0`, seconde clause tout aussi absente du port avant cette tranche.
  2. **LE PERIMETRE -- SEIZE identites, UN seul playbook a part.** La cascade
     d'`AddNormalAttackAbility` distribue 16 identites d'attaque normale ; toutes derivent
     d'`ALoki_NormalAttackPlaybook<T>` et AUCUNE ne redeclare `ShouldExecute` (mesure niveau par
     niveau via `class_get_methods` : `depth 1` pour les seize). `1030 Loki_NormalBossAttack` est la
     seule a l'avoir a `depth 0`. Le cran garde le DISPATCH (`normal_attack_playbook`) : c'est lui
     qui decide laquelle des deux formes s'applique.
  3. **LE GATE, contre le natif.** Carre 2x2 sur la MEME unite attaquante, la MEME cible, la MEME
     geometrie et le MEME seed -- deux axes ECRITS dans `BC.Units[]` : `Explosive` greffe sur la
     cible, `Boss` ajoute (ou non) au caster. Le natif ne doit refuser l'attaque QUE dans
     `expl_gen`. Canal : `aiDryRunAllUnits` (= `CalculateNextActionForUnit`, sans commit).
  4. **LES TEMOINS ATTESTENT LE MONTAGE.** Les deux bras `ctrl_*` doivent ATTAQUER. Sans eux, un
     runner ou le caster n'est pas a portee rendrait « aucune attaque » partout et se lirait comme
     un gate qui mord ; et le bras `expl_boss` est le temoin de la CLAUSE ABSENTE -- un port qui
     appliquerait le gate a `1030` y rougirait.
  5. **LE PORT SUR LES CANAUX DE PRODUCTION.** Le playbook est celui que `normal_attack_playbook`
     dispatche, interroge par `calculate_action_utility` sur un `AiDecisionContext` construit par
     `engine.ai.context.build` + `scene.build_predictor` -- capteur, parsing, seed et foyer compris.
  6. **LES DEUX CONTRE-EPREUVES MORDENT, ET SEULEMENT LA.** Gate coupe (= le port d'avant cette
     tranche) et canal du `TriggeredAbilityComponent` coupe cote DECISION (= le port avant
     `scene._seed_measured_triggered`) : les deux doivent faire basculer la SEULE ligne `expl_gen`
     et rester INERTES sur les trois autres. La seconde est ce qui prouve que le gate lit bien le
     COMPOSANT MONTE et non le kit gameconfig -- `Explosive` n'a aucun porteur au seed BC, donc un
     port reste sur le kit ne peut PAS mordre.

⚠ `Explosive` (72) n'a qu'un porteur au gameconfig (`LootObj_ExplOilDrum`, npc) et **zero** au seed
BC : le montage ECRIT (`catalog_inject.graft_passive_ability`, qui pose les DEUX cotes --
`BC.Units[].PassiveAbilities` et `BC.Abilities.PassiveAbilities['Explosive']`, absente des 194
entrees) est le seul chemin de confrontation, et c'en est un.

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-r2-r1-r1-should-execute.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2r1r1_normal_attack_should_execute.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r1_normal_attack_should_execute as P
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.playbook.base import ComparablePlaybook
from engine.playbook.common import (NormalAttackPlaybook, NormalBossAttackPlaybook,
                                    normal_attack_playbook)


@pytest.fixture(scope="module")
def gate_rows(rpc, tmp_path_factory, live_session):
    """Le carre 2x2, natif ET port, plus les deux contre-epreuves. Les runners sont DISPOSES par le
    probe lui-meme (bloc `finally` de chaque bras) -- rien a liberer au teardown."""
    logs = str(tmp_path_factory.mktemp("tr14r5r2r1r1_gate"))

    def build(state_file, extra):
        return P.PT._build(state_file, ["--seed", P.SEED, *extra])

    try:
        return P.run_gate(rpc, build, logs, verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def _row(rows: list, arm: str) -> dict:
    hit = [r for r in rows if r.get("arm") == arm]
    assert len(hit) == 1, f"bras {arm!r} attendu une fois, trouve {len(hit)}"
    return hit[0]


def test_le_litteral_du_gate_et_sa_classe():
    """(1) Cran OFFLINE : `HasTriggeredAbility(target, 0x48)`, qualifie par son enum."""
    assert int(TriggeredAbilityType.Explosive) == 72, (
        f"`0x48` = 72 est `Explosive` dans `IdunBattle.Entities.Enum.TriggeredAbilityType` ; le "
        f"mirror porte {int(TriggeredAbilityType.Explosive)}. Le meme entier designe autre chose "
        f"dans les autres enums -- qualifier n'est pas une precaution de style.")


def test_le_defaut_de_should_execute_est_vrai():
    """(1bis) `ComparablePlaybook<T>$$ShouldExecute` de BASE = `return true`.

    Ce n'est pas une convention du port : le slot de vtable +0x328 de `DrachnyenPlaybook` (comme de
    `ChronometronPlaybook`, `DoomSirenPlaybook`, `ForwardObserversPlaybook`) pointe sur un corps de
    trois octets `b0 01 c3` = `mov al,1 ; ret`. Un defaut RESTRICTIF rendrait le port MUET sur
    toutes les abilities qui n'overrident pas -- l'exact inverse du bug ferme ici."""
    assert ComparablePlaybook.should_execute(ComparablePlaybook(), None, None, None, None,
                                             -1234.0) is True, (
        "le defaut du slot +0x328 est `return true` : il ne doit dependre NI de l'utilite NI de la "
        "cible. Un defaut qui gate ferait disparaitre des actions que le natif genere.")


def test_le_dispatch_separe_les_deux_seules_formes():
    """(2) SEIZE identites sur `NormalAttackPlaybook`, `1030` seul sur `NormalBossAttackPlaybook`."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.services.custom_normal_attack import (CUSTOM_NORMAL_ATTACK_BY_ACTIVE,
                                                      CUSTOM_NORMAL_ATTACK_BY_PASSIVE,
                                                      NORMAL_BOSS_ATTACK)
    cascade = ([ActiveAbilityType.Loki_NormalAttack]
               + [ActiveAbilityType[v] for v in CUSTOM_NORMAL_ATTACK_BY_PASSIVE.values()]
               + [ActiveAbilityType[v] for v in CUSTOM_NORMAL_ATTACK_BY_ACTIVE.values()])
    assert len(set(cascade)) == 16, (
        f"la cascade d'`AddNormalAttackAbility` distribue 16 identites hors branche TRAIT, "
        f"{len(set(cascade))} recensee(s) : le perimetre du gate a bouge sans repasser par la "
        f"mesure niveau-par-niveau des `ShouldExecute`.")
    bad = [int(a) for a in set(cascade)
           if not isinstance(normal_attack_playbook(int(a)), NormalAttackPlaybook)
           or isinstance(normal_attack_playbook(int(a)), NormalBossAttackPlaybook)]
    assert not bad, (
        f"ces identites de la cascade ne sont PAS dispatchees sur le playbook generique : {bad}. "
        f"Les seize derivent d'`ALoki_NormalAttackPlaybook<T>` et aucune ne redeclare "
        f"`ShouldExecute` (mesure `class_get_methods` niveau par niveau : `depth 1` pour les seize).")
    boss = normal_attack_playbook(int(ActiveAbilityType[NORMAL_BOSS_ATTACK]))
    assert isinstance(boss, NormalBossAttackPlaybook), (
        f"`{NORMAL_BOSS_ATTACK}` (1030) est la SEULE identite dont le playbook redeclare "
        f"`ShouldExecute` (`depth 0`), le dispatch rend {type(boss).__name__}.")


def test_le_natif_refuse_la_cible_explosive_sauf_pour_le_boss(gate_rows):
    """(3) Le carre 2x2 cote NATIF : une seule case bascule, et c'est `expl_gen`."""
    assert len(gate_rows) == 4, f"les quatre bras sont requis, {len(gate_rows)} mesure(s)."
    p = _row(gate_rows, "expl_gen")
    assert p["native"] is False, (
        f"cible portant `Explosive` (72), caster sans `Boss` (attaque normale {p['normal']}) : le "
        f"natif ne doit emettre AUCUNE attaque normale sur elle. Il a propose {p['msgs']}. "
        f"`ALoki_NormalAttackPlaybook<T>$$ShouldExecute` rend `false` avant meme de comparer "
        f"l'utilite.")
    b = _row(gate_rows, "expl_boss")
    assert b["native"] is True, (
        f"MEME cible `Explosive`, MEME geometrie, MEME seed -- seul le trait `Boss` du caster change "
        f"(attaque normale {b['normal']}) : le natif DOIT attaquer, "
        f"`Loki_NormalBossAttackPlaybook$$ShouldExecute` n'a pas la clause `Explosive`. Il a propose "
        f"{b['msgs']}.")


def test_les_temoins_attestent_le_montage(gate_rows):
    """(4) Les deux bras `ctrl_*` attaquent -- sinon la mesure (3) ne dit rien."""
    for arm in ("ctrl_gen", "ctrl_boss"):
        t = _row(gate_rows, arm)
        assert t["native"] is True, (
            f"[{arm}] TEMOIN : cible SANS `Explosive`, le natif doit attaquer, il a propose "
            f"{t['msgs']}. Sans ce cran, 'aucune attaque' partout (caster hors de portee, montage "
            f"mort) se lirait comme un gate qui mord.")
        assert t["port"] is True, (
            f"[{arm}] TEMOIN : le port doit produire une action -- il rend `None`, donc il gate ce "
            f"que le natif accepte. Un gate trop large est une regression RESTRICTIVE, aussi grave "
            f"que la permissive qu'on ferme.")


def test_le_port_reproduit_le_natif_sur_les_quatre_bras(gate_rows):
    """(5) `calculate_action_utility` sur les canaux de PRODUCTION, contre `aiDryRunAllUnits`."""
    bad = [(r["arm"], r["native"], r["port"]) for r in gate_rows if r["port"] != r["native"]]
    assert not bad, (
        f"le port diverge du natif sur {bad} -- format (bras, natif attaque, port attaque). Le port "
        f"lit les MEMES canaux que la production (`scene.build_predictor` -> "
        f"`UnitContext.triggered_abilities` -> `entity_triggered_ability_ids`), donc l'ecart accuse "
        f"la chaine entiere : capteur, parsing, seed, dispatch ou gate.")


def test_les_deux_contre_epreuves_mordent_sur_expl_gen_et_seulement_la(gate_rows):
    """(6) Gate coupe et canal coupe : la SEULE ligne qui bouge est `expl_gen`."""
    for key, label, why in (
        ("port_gate_cut", "gate coupe",
         "c'est le port d'AVANT cette tranche ; s'il ne bouge pas, ce n'est pas le gate qui produit "
         "le vert de (5)"),
        ("port_no_channel", "canal du TriggeredAbilityComponent coupe cote DECISION",
         "`Explosive` n'a AUCUN porteur au seed BC ni au kit du greffon : un port reste sur le kit "
         "gameconfig ne peut PAS voir la greffe, donc ne peut pas gater"),
    ):
        p = _row(gate_rows, "expl_gen")
        assert p[key] != p["port"], (
            f"contre-epreuve '{label}' INERTE sur `expl_gen` (port={p['port']}, "
            f"mute={p[key]}) : {why}.")
        debords = [r["arm"] for r in gate_rows if r[key] != r["port"] and r["arm"] != "expl_gen"]
        assert not debords, (
            f"contre-epreuve '{label}' MORD aussi sur {debords}, qui ne passent pas par le gate "
            f"`Explosive` : le port DEBORDE (il gate une cible sans le passif, ou il applique au "
            f"boss une clause que `Loki_NormalBossAttackPlaybook$$ShouldExecute` n'a pas).")
