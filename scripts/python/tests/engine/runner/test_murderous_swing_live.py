"""MurderousSwing (1137, `worldExecutions` << Tarvakh >>, WorldEaters) -- FACE COMBAT, confront LIVE.

CE QUE CE FICHIER FERME : une entree du gisement `[-D]` (face DECISION portee depuis #108 --
`_SPECIAL_ABILITY_CLASSES["MurderousSwing"]`, l'IA PREDIT le splash self-centre et CHOISIT
l'ability -- pendant que la face COMBAT etait un NO-OP silencieux :
`AbilityHandler.visit_ActiveAbilityMessage` ne trouvait pas la classe, posait `unported`, executait
QUAND MEME les flags de tour, et ne mutait RIEN).

`IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1 -- l'arbre est en tete de `engine/runner/abilities/worldeaters.py`) :

    targets = AdjacentEnemies(caster@0x160)
    dmg     = If( AmountIsGreater(Count(targets), Direct(1)),               # STRICT
                  MinMaxDamage,                                              # $$GetMultipleUnitsDamage
                  Sum(MinMaxDamage, Direct(GetVariableForLevel(8))) )        # $$GetSingleUnitDamage
    Execute( AttackWithAttackDamage(caster@0x160, targets, dmg,
                                    GetDamageProfile = Piercing, GetHits = nrOfHits = 1) )

i2 : << Deals 1x [dmg] Piercing Damage to all adjacent enemies. If only one enemy is hit, deals
+[extraDmg] Damage. >>

LES QUATRE CAS, et pourquoi ILS SONT DISCRIMINANTS (aucun ne rend le meme observable) :

  (A) UN SEUL ennemi adjacent -> regime SINGLE : une seule cible frappee, degat = base + extraDmg.
      Per-coup LIVE == per-coup OFFLINE, et le delta applique == `extraDmg` de la config.
  (B) DEUX (puis TROIS) ennemis adjacents -> regime MULTI : TOUTES les cibles adjacentes sont
      frappees (pas seulement la cible du message), delta == 0 sur chacune. C'est le cas qui
      distingue `> 1` STRICT d'un `>= 1` : sous `>= 1`, le cas (A) perdrait son extraDmg.
  (C) `Count` REEVALUE PAR CIBLE (aucun `Cache` natif autour du `Count`) : avec trois ennemis a
      4 900 PV, les deux premiers MEURENT et le troisieme voit `Count == 1` -> il bascule en regime
      SINGLE DANS LE MEME CAST. Le LIVE TRANCHE, et c'est le point du montage : le 3e coup vaut
      4 854 en regime fige (il SURVIVRAIT a 4 900 PV) contre 7 846 en regime reevalue -- or le natif
      le TUE. La mort de la 3e cible est donc un observable qui separe les deux hypotheses, la ou le
      montant `Amount` est clampe aux PV et ne separe rien.
  (D) GARDE ROUGE (mutation adversariale) -- le MEME snapshot rejoue avec 1137 RETIRE de
      `ABILITY_CLASSES` : zero degat, `ported=False`, et pourtant flags de tour POSES. C'est l'etat
      d'AVANT ce port, MESURE : `cible 500000 -> 500000, caster 9537 -> 9537` alors que le MEME cast
      LIVE mutait (`mutated=True`, 84 evenements, 7 906 de degat).

Montage via la fixture NOMMEE `adjacent_swing_regime` (`_adjacent_swing_regime.py`), qui documente
les quatre pieges payes par la mesure. Aucune tuile/RVA hardcodee. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))          # helpers siblings
from _adjacent_swing_regime import (adjacent_swing_regime,      # noqa: E402,F401  (fixture)
                                    offline_state, assert_live_mutated)

import gameconfig as GC                                        # noqa: E402
from engine.runner.runner import Runner                        # noqa: E402
from engine.runner.messages import ActiveAbilityMessage        # noqa: E402
from engine.runner.components import HealthComponent, UnitComponent   # noqa: E402
from engine.runner.abilities import handler as HANDLER         # noqa: E402
from engine.runner.abilities import worldeaters as WE          # noqa: E402
from engine.entities.formulas import AAmountFormula            # noqa: E402

ABILITY = 1137


def _cfg_const(key):
    """Constante de la config 1137 -- ORACLE, jamais un litteral ecrit dans le test."""
    return int(((GC.ability("MurderousSwing") or {}).get("constants") or {}).get(key))


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _alive(state, uid):
    e = state.get_entity(uid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return bool(uc is not None and uc.alive)


def _offline_cast(state, caster, target):
    """Rejoue le cast par le VRAI point d'entree (`Runner.apply` -> `AbilityHandler`), donc a travers
    le gate de ciblage et les vecteurs d'operation -- pas par un appel direct a `execute_behaviour`."""
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=target, ability_type=ABILITY))
    return runner.ability_handler.last or {}


def _off_by_target(last):
    """{target_id: [Amount par coup]} depuis le diagnostic d'`execute_behaviour`."""
    out = {}
    for h in (last.get("hits") or []):
        a = h.get("attack") or {}
        out[h.get("target")] = list(a.get("per_hit") or [])
    return out


# ------------------------------------------------------------------ (A) regime SINGLE (+extraDmg)

def test_murderous_swing_single_enemy_gets_extra_damage(adjacent_swing_regime):
    """(A) UN seul ennemi adjacent -> `Count == 1`, donc `AmountIsGreater(Count, 1)` est FAUX
    (STRICT) et le degat est `Sum(MinMaxDamage, extraDmg)`. Per-coup LIVE == per-coup OFFLINE."""
    r = adjacent_swing_regime(k=1)
    assert_live_mutated(r)
    st = offline_state(r)
    last = _offline_cast(st, r["caster"], r["target"])
    assert last.get("ported") is True, "1137 non routee par le handler: %s" % last

    off = _off_by_target(last)
    print("\n[MS A] caster=u%d adjacents=%s" % (r["caster"], r["adjacent"]))
    print("[MS A] live=%s" % r["live_damage"])
    print("[MS A] off =%s deltas=%s extra=%s"
          % (off, last.get("per_target_delta"), last.get("extra_damage")))

    assert set(off) == set(r["adjacent"]), \
        "offline frappe %s, attendu les adjacents %s" % (sorted(off), r["adjacent"])
    assert set(r["live_damage"]) == set(off), \
        "live frappe %s, offline %s" % (sorted(r["live_damage"]), sorted(off))
    for uid, seq in off.items():
        assert seq == list(r["live_damage"].get(uid) or []), \
            "per-coup offline %s != live %s (u%s)" % (seq, r["live_damage"].get(uid), uid)
    # `GetHits()` = `GetNumberConstant(0x2f = nrOfHits)` -- confronte a l'ORACLE config.
    n_hits = _cfg_const("nrOfHits")
    for uid, seq in off.items():
        assert len(seq) == n_hits, "%d coups sur u%s != constants.nrOfHits = %d" % (len(seq), uid, n_hits)
    # REGIME SINGLE : le delta applique EST `extraDmg` (et il est non nul, sinon le cas ne teste rien).
    assert last.get("per_target_delta") == [last.get("extra_damage")], \
        "delta %s != extraDmg %s -- la branche `GetSingleUnitDamage` n'a pas ete prise" \
        % (last.get("per_target_delta"), last.get("extra_damage"))
    assert int(last.get("extra_damage") or 0) > 0, "extraDmg nul : le cas ne discrimine rien"


# ------------------------------------------------------------------ (B) regime MULTI (pas d'extra)

@pytest.mark.parametrize("k", [2, 3])
def test_murderous_swing_multi_enemies_hits_all_and_drops_extra(adjacent_swing_regime, k):
    """(B) `k >= 2` ennemis adjacents -> `Count > 1` VRAI, degat = `MinMaxDamage` SEULE, et TOUS les
    adjacents sont frappes -- y compris ceux qui ne sont PAS la cible du message (le set natif est
    `AdjacentEnemies(caster)`, la cible du message ne sert qu'au gate de ciblage)."""
    r = adjacent_swing_regime(k=k)
    assert_live_mutated(r)
    st = offline_state(r)
    last = _offline_cast(st, r["caster"], r["target"])
    assert last.get("ported") is True, "1137 non routee par le handler: %s" % last

    off = _off_by_target(last)
    print("\n[MS B k=%d] adjacents=%s cible-du-message=u%s" % (k, r["adjacent"], r["target"]))
    print("[MS B k=%d] live=%s" % (k, r["live_damage"]))
    print("[MS B k=%d] off =%s deltas=%s" % (k, off, last.get("per_target_delta")))

    assert set(off) == set(r["adjacent"]), \
        "offline frappe %s, attendu les %d adjacents %s" % (sorted(off), k, r["adjacent"])
    assert set(r["live_damage"]) == set(off), \
        "live frappe %s, offline %s -> le SET de cibles diverge" \
        % (sorted(r["live_damage"]), sorted(off))
    for uid, seq in off.items():
        assert seq == list(r["live_damage"].get(uid) or []), \
            "per-coup offline %s != live %s (u%s)" % (seq, r["live_damage"].get(uid), uid)
    assert last.get("per_target_delta") == [0] * k, \
        ("deltas %s : au moins une cible a recu `extraDmg` alors que `Count = %d > 1` -- la branche "
         "`GetMultipleUnitsDamage` doit etre prise" % (last.get("per_target_delta"), k))
    assert len(off) > 1, "le cas MULTI exige au moins 2 cibles frappees"


# ------------------------------------------------------------------ (C) `Count` REEVALUE par cible

def test_murderous_swing_count_is_reevaluated_per_target(adjacent_swing_regime, monkeypatch):
    """(C) Le natif n'enveloppe le `Count` d'AUCUN `Cache` et `AttackDamageBehaviour$$ExecuteTarget`
    evalue le noeud de degat PAR CIBLE : quand des cibles MEURENT en cours de cast, `AdjacentEnemies`
    ne les compte plus et les cibles suivantes peuvent basculer MULTI -> SINGLE.

    MONTAGE : trois ennemis a `hp` PV, choisi ENTRE le 3e coup en regime fige et le 3e coup en regime
    reevalue. Les deux premiers meurent ; le troisieme survivrait sous l'hypothese FIGEE et meurt
    sous l'hypothese REEVALUEE -- c'est le LIVE qui tranche, par une MORT (le montant `Amount`, lui,
    est clampe aux PV et ne separerait rien).

    La contre-epreuve FIGEE est jouee sur le MEME snapshot, par mutation adversariale du noeud."""
    ref = adjacent_swing_regime(k=3)                    # regime temoin : personne ne meurt
    assert_live_mutated(ref)
    st_ref = offline_state(ref)
    last_ref = _offline_cast(st_ref, ref["caster"], ref["target"])
    assert last_ref.get("ported") is True
    off_ref = _off_by_target(last_ref)
    third = ref["adjacent"][-1]
    frozen_third = sum(off_ref.get(third) or [])        # ce que vaudrait le 3e coup SANS bascule
    assert frozen_third > 0, "le regime temoin n'a rien inflige a la 3e cible"
    first_two = [sum(off_ref.get(u) or []) for u in ref["adjacent"][:2]]

    # FENETRE DE PV du regime discriminant, DERIVEE des coups mesures (jamais un litteral) :
    #   hp >  coup3_fige        -> la 3e cible SURVIT sous l'hypothese `Cache`
    #   hp <= coup1 et <= coup2 -> les deux premieres MEURENT, donc le `Count` retombe a 1
    hp = frozen_third + 1
    if hp > min(first_two):
        pytest.skip("fenetre de PV vide sur ce tirage : coup3_fige=%d, coups 1/2=%s"
                    % (frozen_third, first_two))
    r = adjacent_swing_regime(k=3, hp=hp)
    assert_live_mutated(r)
    st = offline_state(r)
    last = _offline_cast(st, r["caster"], r["target"])
    assert last.get("ported") is True, "1137 non routee par le handler: %s" % last
    off = _off_by_target(last)
    third = r["adjacent"][-1]
    print("\n[MS C] adjacents=%s hp=%d 3e-coup-temoin=%d" % (r["adjacent"], hp, frozen_third))
    print("[MS C] deltas=%s extra=%s" % (last.get("per_target_delta"), last.get("extra_damage")))
    print("[MS C] off=%s | live=%s" % (off, r["live_damage"]))

    # 1) le port bascule bien : delta 0 sur les deux premieres, `extraDmg` sur la troisieme.
    assert last.get("per_target_delta") == [0, 0, last.get("extra_damage")], \
        ("deltas %s : la bascule MULTI -> SINGLE apres les deux morts n'a pas eu lieu "
         "(le `Count` a ete FIGE au lieu d'etre reevalue)" % last.get("per_target_delta"))
    # 2) les deux premieres cibles sont bien MORTES offline (c'est ce qui fait retomber le `Count`).
    for uid in r["adjacent"][:2]:
        assert not _alive(st, uid), "u%d devait mourir (hp=%d) : le montage ne cree pas la bascule" % (uid, hp)
    # 3) LE DISCRIMINANT : la 3e cible meurt LIVE **et** offline, alors qu'elle SURVIVRAIT au coup
    #    fige (`frozen_third` < hp est faux par construction : hp < frozen_third... on verifie).
    assert sum(off.get(third) or []) > hp, \
        "3e coup reevalue %s <= hp %d : le regime ne discrimine pas" % (off.get(third), hp)
    assert not _alive(st, third), "la 3e cible devait mourir offline sous le regime reevalue"
    assert _hp_zero_live(r, third), \
        ("la 3e cible a SURVECU live : le natif n'aurait donc PAS reevalue le `Count` -- "
         "c'est le port qui serait a corriger")

    # 4) CONTRE-EPREUVE : le MEME snapshot, avec le noeud de delta FIGE au 1er appel. La vraie
    #    factory est capturee AVANT le patch (la relire depuis le module apres coup rendrait la
    #    version patchee -> recursion infinie).
    real_node = WE.murderous_swing_extra_damage_node
    monkeypatch.setattr(WE, "murderous_swing_extra_damage_node",
                        lambda targets, extra: _FrozenDelta(real_node(targets, extra)))
    st_frozen = offline_state(r)
    last_frozen = _offline_cast(st_frozen, r["caster"], r["target"])
    off_frozen = _off_by_target(last_frozen)
    print("[MS C-fige] deltas=%s off=%s alive3=%s"
          % (last_frozen.get("per_target_delta"), off_frozen, _alive(st_frozen, third)))
    assert last_frozen.get("per_target_delta") == [0, 0, 0], \
        "la mutation adversariale n'a pas fige le `Count` : %s" % last_frozen.get("per_target_delta")
    assert _alive(st_frozen, third), \
        ("sous l'hypothese FIGEE la 3e cible doit SURVIVRE -- sinon le montage ne separe pas les "
         "deux hypotheses et l'assertion (3) ne prouve rien")


def _hp_zero_live(r, uid) -> bool:
    """La cible `uid` a-t-elle encaisse, LIVE, au moins ses PV de depart ? (`Amount` est clampe aux
    PV restants -> encaisser `hp` == mourir.)"""
    return sum(r["live_damage"].get(uid) or []) >= int(r["hp_before"].get(uid) or 0)


class _FrozenDelta(AAmountFormula):
    """MUTATION ADVERSARIALE (jamais du code de production) : le noeud de delta EVALUE UNE FOIS puis
    memorise -- c'est-a-dire l'hypothese << le natif enveloppe son `Count` d'un `Cache` >>. Le
    decompile dit le contraire (aucun `Cache` dans `MurderousSwingAbility$$ExecuteBehaviour`) ; ce
    noeud sert a montrer que la difference est OBSERVABLE, donc que le mirror n'est pas cosmetique."""
    def __init__(self, inner):
        self.inner, self.value = inner, None

    def calculate(self, ctx):
        if self.value is None:
            self.value = int(self.inner.evaluate(ctx))
        return self.value


# ------------------------------------------------------------------ (D) GARDE ROUGE

def test_murderous_swing_unported_is_a_silent_noop(adjacent_swing_regime, monkeypatch):
    """(D) MUTATION ADVERSARIALE = l'etat d'AVANT ce port. Le MEME snapshot, le MEME cast, avec 1137
    RETIRE d'`ABILITY_CLASSES` : `ported=False`, ZERO degat -- et pourtant le cast est ACCEPTE (les
    flags de tour sont poses par le handler, comme le natif).

    C'est aussi la preuve que le montage n'est PAS rate (piege du harnais : un `applyAction` peut
    rendre `ok=True` sans rien muter). Le MEME snapshot rejoue avec le registre INTACT mute -- si le
    montage etait rate, les deux branches rendraient 0."""
    r = adjacent_swing_regime(k=1)
    assert_live_mutated(r)

    # --- branche ROUGE : registre ampute
    amputee = dict(HANDLER.ABILITY_CLASSES)
    amputee.pop(ABILITY, None)
    monkeypatch.setattr(HANDLER, "ABILITY_CLASSES", amputee)
    st_red = offline_state(r)
    tgt = r["adjacent"][0]
    hp_t_before, hp_c_before = _hp(st_red, tgt), _hp(st_red, r["caster"])
    last_red = _offline_cast(st_red, r["caster"], r["target"])
    print("\n[MS D-rouge] ported=%s flags=%s | cible %s -> %s | caster %s -> %s"
          % (last_red.get("ported"), last_red.get("flags"), hp_t_before, _hp(st_red, tgt),
             hp_c_before, _hp(st_red, r["caster"])))
    assert last_red.get("ported") is False, \
        "la mutation adversariale n'a pas pris (1137 encore dans le registre) : %s" % last_red
    assert _hp(st_red, tgt) == hp_t_before, "NO-OP attendu : la cible a perdu des PV sans classe portee"
    assert _hp(st_red, r["caster"]) == hp_c_before, "NO-OP attendu : le caster a perdu des PV"
    assert last_red.get("flags") is not None, \
        ("le cast doit rester ACCEPTE (flags de tour poses) meme non porte -- sinon on mesure un "
         "montage rate, pas le no-op silencieux")

    # --- branche VERTE : MEME snapshot, registre INTACT -> ca mute
    monkeypatch.undo()
    st_green = offline_state(r)
    last_green = _offline_cast(st_green, r["caster"], r["target"])
    print("[MS D-verte] ported=%s | cible %s -> %s"
          % (last_green.get("ported"), hp_t_before, _hp(st_green, tgt)))
    assert last_green.get("ported") is True, "1137 devait etre routee apres `monkeypatch.undo()`"
    assert _hp(st_green, tgt) < hp_t_before, \
        ("MONTAGE RATE (et non no-op) : le cast ne fait rien meme registre intact -- caster u%d, "
         "cible u%d" % (r["caster"], tgt))
