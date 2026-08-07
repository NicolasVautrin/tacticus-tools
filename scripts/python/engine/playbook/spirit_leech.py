"""`1104 SpiritLeech` -- le terme LIFESTEAL, remis a son RANG natif
(`#419-r1-tr14-r5-r2-r1-r1-r3`).

## Ce qui etait faux, et ou

`ComparableAbilityGenerator._action_utility` ajoutait `ls` au **RETOUR** de
`calculate_action_utility` :

    cand = pb.calculate_action_utility(...)      # <- ShouldExecute a DEJA ete evalue ici
    if ab == SpiritLeech: u_full += ls ; u_val += ls

Le natif, lui, ne somme rien apres. Le terme entre par une TROISIEME branche de prediction, et il
est folde AVANT le gate :

    IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeHealPredictions(caster, casterTile, target, abilityState)
      -> amount  = SpiritLeechAbility$$GetHealAmountForPrediction(target, abilityState)
         targets = SpiritLeechAbility$$GetHealTargets()
         return ComparablePlaybook<T>$$GenerateHealPredictions(caster, casterTile, caster,
                                                               targets, amount, 0, <Nullable vide>)

    IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions
      = Sigma CalculateUtilityFromDamageEvent            (1re boucle)
      + Sigma CalculateUtilityFromHealEvent  (slot +0x368, 2e boucle)   <- ICI

    IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility
      u = CalculateCustomUtility + CalculateUtilityFromPredictions
      if (!ShouldExecute(caster, casterPosition.MainTile, target, u)) return Nullable_vide

L'argument de `ShouldExecute` CONTIENT donc le lifesteal.

## Ce que ce deplacement change -- et ce qu'il ne change PAS

**Il ne change AUCUNE valeur d'utilite finale** : `u_action = u_full + custom` et l'addition est
commutative. Ce qu'il change, ce sont DEUX choses :

1. **l'ETAGE `u`** que les probes confrontent au canal natif `pairUtility` (= exactement
   `CalculateUtilityFromPredictions`). Avant, `calculate_action_utility(...)["u"]` n'incluait PAS le
   lifesteal alors que le natif l'y met ; l'ecart etait masque parce que le generateur le rajoutait
   plus loin ;
2. **l'ARGUMENT du gate**. Aujourd'hui inerte pour 1104 --
   `SpiritLeechPlaybook$$ShouldExecute` = `!WillNormalAttackKill(...)`, qui **ne lit pas**
   `attackHealUtility` (mesure de `#419-r1-tr14-r5-r2-r1-r1-r1`, qui REFUTE l'annonce << ce residu
   mordra des que le gate sera porte >>). Le rang reste neanmoins FAUX tant qu'il n'est pas corrige,
   et il mordrait des qu'un gate lisant l'utilite arriverait sur cette route.

## Le calcul lui-meme est INCHANGE

Le corps deplace est celui de `_spiritleech_lifesteal_util` (#84, corrige par #339 -- bornes CAPEES
`healthDmg*`, un SEUL arrondi demi-vers-le-pair via `MinMaxDamage$$Avg`, aucun terme de bouclier).
Aucune ligne de son arithmetique n'est touchee : cette tranche deplace un terme, elle ne le
recalcule pas.
"""
from __future__ import annotations

from fractions import Fraction

from .base import register
from .normal_attack_kill_gate import SpiritLeechPlaybook
from ..dsl.base import _round_fix64            # `AAmountFormula$$RoundFix64Result` (PercentageOf roundUp=1)
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.effects.magnitude import ability_var
from ..services.min_max_damage import min_max_avg   # `MinMaxDamage$$Avg` (#333/#339)
from .. import battle_query as bq

#: `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealTargets` : faction
#: `0xc` = Tyranids (self + amis Tyranids ADJACENTS a la tuile de cast).
HEAL_FACTION: str = "Tyranids"


class SpiritLeechLifestealPlaybook(SpiritLeechPlaybook):
    """`IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook` (1104) -- la classe NATIVE homonyme, avec
    ses DEUX overrides portes : `ShouldExecute` (herite de `SpiritLeechPlaybook`, le corps partage
    par 14 classes) et `MakeHealPredictions` (le sien PROPRE -- son symbole n'a qu'UN proprietaire de
    vtable dans le build, donc les 13 autres identites du meme `ShouldExecute` gardent la base VIDE,
    et c'est pour cela que cette sous-classe n'est enregistree QUE pour 1104).

    NON PORTE, et ce n'en est pas le sujet : `SpiritLeechPlaybook$$MakeEffectPredictions` (effet
    `Pinned` de poids 0, inerte)."""

    def __init__(self):
        super().__init__(int(ActiveAbilityType.SpiritLeech))    # 0x450 = 1104

    def make_heal_predictions(self, ctx, caster_tile, target, ability_id, events) -> list:
        """`SpiritLeechPlaybook$$MakeHealPredictions` -> liste de tuples
        `(effective_heal, hp_max, is_friend, is_boss)` que `predict.heal_action_utility` folde
        (mirror de `CalculateUtilityFromHealEvent`).

        - montant = `SpiritLeechAbility$$GetHealAmountForPrediction` = `PercentageOf(
          MinMaxDamage$$Avg(AccurateHealthDamage@+0x40), hpToHealPct, roundUp: 1)`. **#339** : les
          bornes sont celles CAPEES aux PV (`healthDmgMin/Max`), pas les brutes, et il n'y a QU'UN
          arrondi (demi-vers-le-pair dans `Avg`, puis Ceiling dans `PercentageOf`) ; aucun terme de
          BOUCLIER. ⚠ Pas de court-circuit `LimitedByMinHp` -- `DamagePredictionFormula$$Calculate`
          lit `+0x40` en direct, contrairement a `IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage`.
        - cibles = `SpiritLeechAbility$$GetHealTargets` = SELF `union` (amis ADJACENTS a la tuile de
          cast, faction Tyranids). POSITION-DEPENDANT : c'est `caster_tile`, pas la MainTile.
        - par cible : `PredictHeal` = `min(lifesteal, PV manquants)`, puis
          `HealUtility` = `eff/(maxHP+1) x 100` (is_friend = True).

        `events[0]` porte la prediction de degat principale (le natif la RECALCULE dans
        `GetHealAmountForPrediction` ; approximation confrontee live, cf. l'en-tete du module)."""
        me = getattr(ctx, "me", None)
        if me is None or not events:
            return []
        cand_pred = events[0].composite_fields() or {}
        dmg = min_max_avg(cand_pred.get("healthDmgMin") or 0, cand_pred.get("healthDmgMax") or 0)
        if dmg <= 0:
            return []
        hc = ctx.heal_config(ctx.uid)
        pct = ability_var("SpiritLeech", "hpToHealPct", hc["active"],
                          multiplier_pct=hc["multiplier"]) or 0
        # `PercentageOf(dmg, pct, roundUp=1)` -> `RoundFix64Result(mode 1 = Ceiling)`.
        lifesteal = _round_fix64(Fraction(int(dmg) * int(pct), 100), 1)
        if lifesteal <= 0:
            return []
        team = me.get("team")
        heal_ids = {ctx.uid}
        for u in ctx.units:
            if u.get("id") == ctx.uid or u.get("team") != team or not u.get("alive"):
                continue
            if _faction_of(u.get("visualId")) != HEAL_FACTION:
                continue
            p = u.get("pos")
            if p and p.get("col") is not None and bq.is_adjacent(
                    caster_tile, (p["col"], p["row"]), ctx.elev_by_pos, bq.neigh_map(ctx)):
                heal_ids.add(u.get("id"))
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        out = []
        for hid in heal_ids:
            ob = obs_by_sq.get(hid) or {}
            hp_max = int(ob.get("hpMax") or 0)
            hp_cur = int(ob.get("hp") or 0)
            if hp_max <= 0:
                continue
            eff = min(lifesteal, max(0, hp_max - hp_cur))   # `PredictHeal` = min(amount, manquant)
            out.append((eff, hp_max, True, False))          # (eff, maxHP, is_friend, is_boss)
        return out


def _faction_of(visual_id):
    """Faction gameconfig d'une unite -- meme lecture que `ai.action_generators._faction`, differee
    pour ne pas creer d'arete `playbook -> ai` (le paquet `ai` importe deja `playbook`)."""
    from ..ai.action_generators import _faction
    return _faction(visual_id)


register(SpiritLeechLifestealPlaybook())
