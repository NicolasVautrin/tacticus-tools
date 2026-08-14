"""`CloseCombatWeaknessPlaybook` (triggered 1130 `CloseCombatWeakness`) -- la face DECISION du trait
T'AU. Corps PROPRE, DEUX faces, et elles ne disent PAS la meme chose. #1015-r1.

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.CloseCombatWeaknessPlaybook$$.ctor` appelle la base avec le litteral
`0x46a` = **1130** -- c'est ce qui identifie l'ability du playbook, pas son nom de classe.

### Face MOUVEMENT

`IdunBattle.AI.Playbook.Loki.CloseCombatWeaknessPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

    var tile    = UtilityMovementCase.get_MovementTile(case);              // la TUILE CANDIDATE
    var enemies = this.<>4__this.<query>.GetAdjacentEnemies(tile, case.<+0x10>, false);   // slot 0x7f
    int w       = getUtilityVal("CLOSECOMBATWEAKNESS_PerAdjacentEnemy");
    yield return Fix64.op_Implicit(w * enemies.Count);

Trois lectures qui ne se devinent pas :

1. **Le slot `0x7f` est `IBattleQuery.GetAdjacentEnemies`, arite 3** -- LU dans
   `data/symbols/<build>/metadata/interface_slots.tsv` (ligne `IBattleQuery 127 GetAdjacentEnemies 3`),
   pas deduit du nom du playbook. L'adjacence est donc celle de
   `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : RING-1 **avec**
   la porte d'elevation `abs(delta) < 2` -- `battle_query.is_adjacent`, jamais `hexgeo.distance == 1`
   nu (#271, 0 faux sur 4 963 paires contre 9/22/2 pour hexgeo).
   ⚠ Les slots se RE-LISENT a chaque build : la famille `AdjacentUnitPreference` emprunte, elle, la
   surcharge `0x7d` du MEME nom. C'est la table qui tranche, pas le numero cite ici.

2. **La cle de poids est un LITTERAL du corps**, `0x336efa0` dans
   `data/symbols/<build>/metadata/string_literals.tsv` = `"CLOSECOMBATWEAKNESS_PerAdjacentEnemy"` --
   l'adresse chargee par le `MoveNext` (`DAT_18336efa0` = image_base + `0x336efa0`) EST cette entree.
   Elle vaut **-40** dans `BC.Utilities.Default.TriggeredAbilities`, c'est-a-dire que le porteur
   **FUIT** le contact : -40 par ennemi adjacent a la tuile visee. La casse en capitales n'est pas
   derivable du nom de l'ability -- elle est LUE.

3. **Aucun cap, aucun filtre, aucune branche AMIS.** Le corps n'a qu'un `Count` et une
   multiplication ; il n'y a ni `Min(count, cap)` ni predicat sur le voisin, contrairement au corps
   commun d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook`. C'est pourquoi ce playbook a son
   PROPRE module et n'herite pas de cette famille : le resultat coinciderait numeriquement
   (`Count x poids plat`), mais le corps natif est distinct et le ranger la-bas ferait croire a des
   slots `vtbl+0x228/0x238/0x248/0x258` qui n'existent pas ici.

### Face ATTAQUE -- CONSTANTE ZERO, et c'est un RESULTAT

`IdunBattle.AI.Playbook.Loki.CloseCombatWeaknessPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
a pour corps ENTIER, a l'etat 0 : `Fix64.op_Implicit(0)` puis `return true` ; a l'etat 1 : `return
false`. Un seul step, valeur **0**. Aucun `getUtilityVal`, aucune query, aucun champ lu.

=> l'ability n'entre PAS dans `psyker.TRIGGERED_ATTACK_PLAYBOOKS`, et **son absence EST le
comportement natif** : la feuille ATTAQUE somme des steps, et un step a 0 ne se distingue pas d'un
playbook absent. Meme forme que `Lakrimae`/`Boltstorm` cote MOVE. Ce n'est pas un port manquant.

## Confrontabilite du porteur

Les **16** porteurs du trait sont TOUS des `units.npc` (T'au Darkstrider / Shadowsun / Marksman /
Crisis, et leurs variantes `LHE`/`Inc`), donc aucun n'entre au pool. Mais « npc-only » n'implique pas
« non confrontable » : ce playbook charge PAR ABILITY et son utilite ne lit **ni stats ni traits du
caster** (elle ne lit que la tuile candidate et les ennemis a son ring-1). Le trait se GREFFE donc sur
une unite du pool par `rl_duel build --unit-stat "<vis>:Traits=[...]"`, qui mord sur 104 des 105
membres de `UnitTrait`.

## Registre

Ability TRIGGERED : ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne s'appliquent (ces deux donnees
sont celles d'`ABILITY_CLASSES`, le registre des abilities ACTIVES castables). L'entree MOVE se fait
dans `TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`), l'homologue de
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` ; et l'ability elle-meme doit etre PRESENTEE au
dispatcher, ce que fait `entities/triggered_ability_type.py::TRAIT_TRIGGERED_ABILITY_IDS` (le trait
la derive, elle n'est dans aucun `passiveAbilities` de gameconfig).

ASCII only (cp1252).
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.triggered_ability_type import TriggeredAbilityType

#: le LITTERAL `0x336efa0` du `MoveNext`, lu dans `metadata/string_literals.tsv`.
CLOSE_COMBAT_WEAKNESS_PER_ADJACENT_ENEMY = "CLOSECOMBATWEAKNESS_PerAdjacentEnemy"


class CloseCombatWeaknessPlaybook:
    """`IdunBattle.AI.Playbook.Loki.CloseCombatWeaknessPlaybook` (triggered 1130). Sans etat, comme
    les autres entrees du registre MOVE : le natif n'en tient qu'UN singleton par type d'ability
    (`PlaybookDatabase$$LoadPlaybook`, cache dict)."""

    ability_id: int = int(TriggeredAbilityType.CloseCombatWeakness)      # 1130 = 0x46a

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        """Mirror de `<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext` (cf. en-tete) :

            w x |GetAdjacentEnemies(tuile candidate)|

        Le poids est demande UNE FOIS, hors boucle -- c'est la forme du corps natif (un `Count` puis
        un `imul`), a la difference du corps commun d'`AdjacentUnitPreference` qui appelle
        `GetAdjacentEnemyUtility(u_i)` PAR VOISIN (et dont deux concrets rendent un poids qui DEPEND
        du voisin). Ici le corps n'a aucun accesseur par-unite : rien a hisser dans une boucle.

        `enemy_units` = les ennemis VIVANTS poses (self-exclu par construction du producteur) ; le
        natif ne filtre rien de plus (pas de cap, pas de predicat)."""
        ctx = ctx or {}
        w = wt.sub("TriggeredAbilities", CLOSE_COMBAT_WEAKNESS_PER_ADJACENT_ENEMY)
        if not w:
            return 0.0
        n = bq.count_adjacent(tile, [u.get("pos") for u in (ctx.get("enemy_units") or ())
                                     if u.get("pos")],
                              ctx.get("elev_by_pos"), bq.neigh_map(ctx))
        return float(w * n)
