"""#890 -- les deux actives du Hive Tyrant Leviathan : le port frappe-t-il/buffe-t-il les MEMES ?

QUESTIONS BINAIRES, une par cas :

* `1032 Catalyst` -- l'ensemble des unites que le NATIF buffe, et les TROIS montants qu'il pose,
  sont-ils EGAUX a ceux de `CatalystAbility.execute_behaviour` ?
* `1056 StranglethornCannon` -- la SEQUENCE `(cible, montant)` des coups du NATIF est-elle EGALE,
  valeur par valeur et dans l'ordre, a celle de `StranglethornCannonAbility.execute_behaviour` ?

CE QUE CHAQUE MONTAGE EXERCE -- c'est le point, l'accord ne vaut que par la.

`catalyst` : QUATRE non-cibles, chacune pour une raison DIFFERENTE du selecteur natif
`op_Subtraction(Friends(Caster, UnitsFromFaction(AllAliveUnits, "Tyranids")), Caster)` --
(a) le CASTER (`op_Subtraction`), (b)+(c) deux allies NON-Tyranides (`UnitsFromFaction`), (d) un
Tyranide **ENNEMI** (`Friends`). Un port a qui manquerait n'importe lequel des trois filtres buffe
quelqu'un de plus, et le test le voit. Les MONTANTS discriminent sur un second axe : `extraArmor` et
`blockDmg` sont scales par `AbilityVariablesMultiplierPercentage` (200 % au palier 4 du boss),
`blockChance` NON (constante) -- trois nombres, deux regimes.

`cannon` : placements EXPLICITES pour que le ring-1 de la cible contienne A LA FOIS deux ennemis et
**un allie du caster**, un autre allie restant a distance 3. Le natif passe son ring-1 **BRUT**
(aucun wrapper `Enemies`, contraste PlasmaGrenade/HarvesterOfSouls) -> l'allie adjacent PREND un
coup. C'est la seule configuration ou un port qui aurait recopie le patron voisin diverge.

**VUE ROUGE** (`test_cannon_declaring_ranged_over_reduces_live`) : le port dont la NATURE du coup est
declaree `Ranged` au lieu d'ABSENTE. C'est l'erreur que ce port a REELLEMENT commise avant mesure --
`gameconfig.abilities.StranglethornCannon` n'a **pas** d'`attackRangeType`, donc
`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` rend « pas d'entree » et
`IsRangedAttack` est FAUX. Declarer `Ranged` arme le gate de
`IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack`
(`Direct(-1)` cappe a `Direct(1)`, sous `get_OwnerIsTarget & IsRangedAttack`) -> UN COUP DE MOINS sur
une cible adjacente a un `BigTarget` allie. Sans ce bras, l'accord du bras vert ne dirait pas que
c'est CE terme qui le produit.

Montage, decomposition et refus de mesurer un canal muet : `probe_890_hive_tyrant.py` (il LEVE si le
canal `unitAbilityStates` n'a pas ete tire -- sans lui le niveau d'ability du boss retombe a 1 et
toute la mesure serait faite deux ordres de grandeur trop bas, EN SILENCE).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_890_hive_tyrant as P                            # noqa: E402
from engine.runner.abilities.tyranids import CATALYST_TURNS  # noqa: E402

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    # PERIMETRE LARGE, et DERIVE : ce fichier CONFRONTE le port au jeu VIVANT. Il change donc de
    # verdict sur (a) tout ce que le port execute -- les deux classes d'ability, mais aussi les
    # etages PARTAGES qu'elles traversent (`snapshot` et le canal `unitAbilityStates` d'ou vient le
    # niveau d'ability du boss, `abilities/base`, `behaviours/combat`, `services/battle_query` et
    # son `attack_range_type`, `services/attack_hits_formula`, `operations/damage*`, les selecteurs
    # `entities/selectors/*`) ; (b) le GAMECONFIG, qui porte les montants, `nrOfHits`/`nrOfHits_2`
    # et surtout l'ABSENCE d'`attackRangeType` dont depend tout le bras rouge ; (c) le BUILD du jeu,
    # puisque les valeurs attendues sont celles que le natif rend.
    # Enumerer ces modules un a un serait un FAUX VERT : la chaine traversee n'est pas stable, et
    # c'est precisement un etage partage (`hits_channel_is_melee`) qui a fait rougir ce fichier la
    # premiere fois. Les DEUX formes de glob sont necessaires : `**/` exige un SEGMENT, donc
    # `scripts/python/**/*.py` ne voit PAS `scripts/python/probe_890_hive_tyrant.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    "build": True,
    "toujours": False,
    "raison": ("Confrontation LIVE : le verdict depend du port ENTIER traverse par les deux casts, "
               "du gameconfig (montants, nrOfHits, ABSENCE d'attackRangeType) et du build du jeu. "
               "Une liste de modules choisis raterait les etages partages -- c'est l'un d'eux "
               "(`hits_channel_is_melee`) qui a fait rougir ce fichier a sa premiere passe."),
}


@pytest.fixture(scope="module")
def catalyst():
    return P.case_catalyst()


@pytest.fixture(scope="module")
def cannon():
    return P.case_cannon()


# ------------------------------------------------------------------ 1032 Catalyst

def test_catalyst_buffs_exactly_the_friendly_tyranids_live(catalyst):
    """L'ensemble buffe par le NATIF == {allie Tyranide 1, allie Tyranide 2}, et RIEN d'autre.

    Le regime est EXERCE : les quatre non-cibles sont presentes et distinctes, chacune couvrant un
    filtre du selecteur. Un test qui ne les aurait pas au board ne prouverait rien."""
    r = catalyst["roles"]
    for key in ("caster", "ally_tyranid_1", "ally_tyranid_2", "ally_other_1", "ally_other_2",
                "enemy_tyranid"):
        assert r.get(key) is not None, "role %s absent -- le regime n'est pas monte" % key
    assert len({r["caster"], r["ally_tyranid_1"], r["ally_tyranid_2"], r["ally_other_1"],
                r["ally_other_2"], r["enemy_tyranid"]}) == 6, "roles non distincts"
    native = set(catalyst["native"])
    assert native == {r["ally_tyranid_1"], r["ally_tyranid_2"]}, \
        "natif buffe %s, attendu les 2 Tyranides ALLIES %s" % (
            sorted(native), sorted([r["ally_tyranid_1"], r["ally_tyranid_2"]]))
    # Les trois exclusions, nommees une par une : c'est la lecture du selecteur, pas une redite.
    assert r["caster"] not in native, "le CASTER est buffe -- `op_Subtraction(., Caster)` manquant"
    assert r["ally_other_1"] not in native and r["ally_other_2"] not in native, \
        "un allie NON-Tyranide est buffe -- `UnitsFromFaction` manquant"
    assert r["enemy_tyranid"] not in native, \
        "un Tyranide ENNEMI est buffe -- `Friends` manquant"


def test_catalyst_port_matches_native_live(catalyst):
    """Port == natif : MEME ensemble de cibles ET memes trois montants sur chacune."""
    port = {}
    for b in (catalyst["port"].get("buffs") or []):
        port.setdefault(b["unit"], {})[int(b["stat"])] = int(b["amount"])
    native = {int(u): v for u, v in catalyst["native"].items()}
    assert set(port) == set(native), "cibles port %s != natif %s" % (sorted(port), sorted(native))
    for uid, n in native.items():
        p = port[uid]
        assert p == {16: n["armor"], 7: n["chance"], 8: n["damage"]}, \
            ("u%s : port %s != natif %s (16=FixedArmor, 7=BlockChance, 8=BlockDamage)"
             % (uid, p, n))


def test_catalyst_amounts_are_not_degenerate_live(catalyst):
    """Le TEMOIN DISCRIMINE : les trois montants sont DISTINCTS et non nuls, et `blockChance` n'est
    PAS scale alors que les deux autres le sont.

    Sans ce controle, un accord pourrait venir d'un regime degenere (trois zeros, ou trois fois la
    meme valeur) ou d'un multiplicateur neutre -- et il ne dirait alors rien du scaling ni de la
    distinction variable/constante."""
    vals = next(iter(catalyst["native"].values()))
    a, c, d = vals["armor"], vals["chance"], vals["damage"]
    assert a > 0 and c > 0 and d > 0, "montants degeneres %s" % vals
    assert len({a, c, d}) == 3, "les trois montants sont confondus %s -- temoin non discriminant" % vals
    # `blockChance` est une CONSTANTE du gameconfig : le natif ne la scale pas.
    import gameconfig as GC
    raw = int(((GC.ability("Catalyst") or {}).get("constants") or {})["blockChance"])
    assert c == raw, "blockChance natif %s != constante gameconfig %s (elle serait scalee)" % (c, raw)
    # Les deux variables, elles, SONT scalees : sinon elles vaudraient leur valeur de base.
    assert a != c and d != c


def test_catalyst_duration_is_two_turns_live(catalyst):
    """`Effect_RemainingTurns == 2` -- le `System.Nullable<int>(2)` LITTERAL du decompile, deja en
    TOURS (et non un `TurnsFromRounds`, qui passerait par `ConvertRoundsToTurns`)."""
    assert catalyst["native_turns"] == [2], \
        "durees natives %s, attendu [2]" % catalyst["native_turns"]
    assert CATALYST_TURNS == 2


def test_catalyst_stat_deltas_confirm_by_a_second_channel_live(catalyst):
    """Seconde voie, INDEPENDANTE du stream : les stats RESOLUES (`combatSnapshot`, `GetStat`) ne
    bougent que sur les deux buffes, et exactement des memes montants."""
    r = catalyst["roles"]
    buffed = {r["ally_tyranid_1"], r["ally_tyranid_2"]}
    for uid, (da, dc, dd) in catalyst["deltas"].items():
        if int(uid) in buffed:
            assert (da, dc, dd) != (0, 0, 0), "u%s buffe mais aucun delta de stat" % uid
        else:
            assert (da, dc, dd) == (0, 0, 0), "u%s NON buffe mais delta %s" % (uid, (da, dc, dd))


# ------------------------------------------------------------------ 1056 StranglethornCannon

def test_cannon_geometry_is_the_discriminating_one_live(cannon):
    """Le montage EXERCE-t-il ce qu'il pretend ? cible a 2 du caster (donc `TargetIsNotAdjacent`
    satisfait ET dans `range`=3), un ALLIE a 1 de la cible, un autre allie a 3, deux ennemis a 1."""
    r, d = cannon["roles"], {int(k): v for k, v in cannon["dist_to_target"].items()}
    assert d[r["caster"]] == 2, "caster a %s de la cible -- regime non exerce" % d[r["caster"]]
    assert d[r["ally_in_ring"]] == 1, "l'allie n'est pas dans le ring-1"
    assert d[r["ally_out_of_ring"]] == 3, "le temoin negatif n'est pas hors ring-1"
    assert d[r["enemy_in_ring_1"]] == 1 and d[r["enemy_in_ring_2"]] == 1


def test_cannon_port_matches_native_hit_by_hit_live(cannon):
    """Port == natif, coup par coup ET dans l'ordre : 3 coups sur la cible (`nrOfHits`), puis 1 coup
    (`nrOfHits_2`) par unite du ring-1, triees par id (`multi=True` = l'`OrderBy` natif)."""
    assert cannon["ok_apply"] is True
    live = [(t, a) for t, a in cannon["hits"]]
    port = [(t, a) for t, a in cannon["port"]]
    assert port == live, "port %s != natif %s" % (port, live)


def test_cannon_splash_hits_the_ALLY_and_spares_the_target_live(cannon):
    """FRIENDLY FIRE, et l'exclusion du centre -- les deux proprietes du `AdjacentUnits` natif BRUT.

    L'allie du caster adjacent a la cible EST frappe (aucun wrapper `Enemies`) ; la cible ne prend
    PAS de coup splash en plus de ses 3 (`AdjacentUnits` exclut son origine) ; l'allie a distance 3
    et le caster ne prennent rien."""
    r = cannon["roles"]
    by_target = {}
    for t, a in cannon["hits"]:
        by_target.setdefault(t, []).append(a)
    assert r["ally_in_ring"] in by_target, \
        "l'ALLIE adjacent n'est pas frappe -- le ring-1 aurait ete filtre aux ennemis"
    assert len(by_target[r["ally_in_ring"]]) == 1, "l'allie doit prendre nrOfHits_2 = 1 coup"
    assert len(by_target[r["target"]]) == 3, \
        "la cible prend %s coups, attendu nrOfHits = 3 (le splash ne doit pas l'inclure)" % \
        len(by_target[r["target"]])
    assert r["ally_out_of_ring"] not in by_target, "un allie HORS ring-1 est frappe"
    assert r["caster"] not in by_target, "le CASTER est frappe"


def test_cannon_declaring_ranged_over_reduces_live(cannon):
    """VUE ROUGE -- declarer la nature `Ranged` (`is_melee=False`) change le resultat.

    C'est la mutation adversariale du SEUL terme auquel le bras vert doive son accord dans ce
    montage : le gate `IsRangedAttack` de `BigTarget_AdjacentEffect`. Si elle passait inapercue,
    l'accord pourrait venir de n'importe quoi d'autre."""
    assert cannon["attack_range_type"] is None, \
        ("`StranglethornCannon.attackRangeType` = %r -- s'il devient non nul, ce test ET le port "
         "doivent etre relus (la nature du coup serait alors DECLAREE)."
         % cannon["attack_range_type"])
    assert cannon["port_ranged"] != cannon["port"], \
        "la mutation `is_melee=False` ne change RIEN -- le bras ne prouve rien"
    assert cannon["port_ranged"] != cannon["hits"], \
        "le port MUTE reproduit quand meme le natif -- le terme mute n'est pas celui qui compte"


def test_cannon_inform_weapon_is_emitted_by_native_only_live(cannon):
    """RESIDU BORNE (#890-r1) -- le noeud `IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon`, 1er
    terme du `op_BitwiseAnd` natif, emet un event `Info` porteur du profil et du regime d'arme. Le
    port ne le materialise PAS en feuille (son aval, les TAGS d'arme, est deja porte par
    `engine/streams/inform_ops.py` et consomme par `AttackWithAttackDamage`).

    La garde FIGE le fait mesure au lieu de le taire : elle rougit si le natif cesse de l'emettre
    (le port serait alors a re-lire) comme si son contenu change."""
    assert cannon["inform"], "le natif n'emet plus l'event d'`InformWeapon`"
    tags = cannon["inform"][0]
    assert tags.get("Attack_Weapon_DamageProfile") == 18, \
        "profil d'arme %s, attendu 18 = DamageProfileType.Blast" % tags.get(
            "Attack_Weapon_DamageProfile")
    assert tags.get("Attack_Weapon_IsMelee") == 0
