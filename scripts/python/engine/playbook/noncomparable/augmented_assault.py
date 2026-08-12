"""`AugmentedAssaultPlaybook` (0x4c5 = 1221, `votanBeserk` << Havyr >>) -- face DECISION, #975.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` (extrait de
`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`) :

    active   1221   IdunBattle.AI.Playbook.Loki.AugmentedAssaultPlaybook

UNE seule entree, dans le dict `active` (+0x68) -- rien dans `triggered`, `nonowner` ni
`specific`. Ce playbook n'est donc pas du code registered-but-dead.

BASE DE HIERARCHIE -- `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv`
------------------------------------------------------------------------------
    IdunBattle.AI.Playbook.Loki.AugmentedAssaultPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1

Le `.ctor` decompile, lui, s'appelle
`ComparablePlaybook<__Il2CppFullySharedGenericType>$$.ctor(this, 0x4c5, klass)` : corps TRIVIAL
DEDUPLIQUE par IL2CPP, le meme piege que #487-r1 / `FireAndReposition` / `ExemplarOfTheMontka`.
Le `0x4c5` du ctor est l'ability_id -- LU la, jamais devine du nom.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.AugmentedAssaultPlaybook$$EvaluateNonComparable` :

    bucket  = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # cctor : Fix64(1)
    targets = BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition)
    if (targets == null) throw
    if (1 < targets.<+0x18>)                                         # <-- LE GATE : List._size > 1
        foreach entities in targets:
            target  = entities@+0x10
            utility = Fix64.op_Implicit( UnitExtensions.GetStat(target, 5 = Health, 0, 0) )
            bucket.AddAction( BasePlaybook.GenerateAction(casterPosition, target, utility) )
    return bucket

`IdunBattle.AI.Playbook.Loki.AugmentedAssaultPlaybook$$.cctor` :

    <statics+0x00> = FixMath.NET.Fix64$$op_Implicit(1)

DEUX POINTS QUI NE SE DEDUISENT PAS DU VOISIN DE FORME
------------------------------------------------------
1. **L'utilite est le patron `GetStat(cible, 5)`**, identique a `VexillaMagnificaPlaybook` (1183),
   `MindControlPlaybook` (1164) et `GravitonRiflePlaybook` (1206) -- mais SANS le `continue` de
   Vexilla (aucun `HasEffect`) et SANS le `ShouldEvaluate` de Graviton. Le corps de 1221 ne lit ni
   effet ni etat : `GetStat` puis `AddAction`, rien d'autre. Recopier Vexilla y aurait ajoute un
   filtre `Stunned` que le decompile de 1221 ne porte pas.

2. **LE GATE `targets.Count > 1` EST PROPRE A 1221**, et il n'existe chez AUCUN des trois autres.
   `1 < *(int *)(lVar8 + 0x18)` : `+0x18` est le champ `_size` de `List<T>` en layout IL2CPP
   (`+0x10 = _items`, `+0x18 = _size`, `+0x1c = _version`) -- c'est bien `Count`, pas une capacite.
   Le corps de boucle ET le `SendSumMetric` de fin d'enumeration sont TOUS DEUX a l'interieur du
   `if` : quand le gate ne passe pas, le natif ne construit meme pas l'enumerateur et rend un
   bucket VIDE. Semantique : Havyr ne depense `AugmentedAssault` que s'il a **au moins DEUX**
   cibles legales depuis la position evaluee -- son ability abaisse l'armure de la cible frappee,
   donc l'IA la reserve aux melees ou il reste du monde a frapper apres.

   ⚠ C'est un gate **PAR POSITION**, pas global : `GetEligibleTargetsSelectable(caster,
   casterPosition)` est re-evalue a chaque position balayee par
   `ActiveAbilityActionGenerator.<GenerateActions>d__7`. Une position d'ou une seule cible est
   legale rend un bucket vide, une autre d'ou deux le sont rend deux actions.

BORNES DE PORT, nommees
------------------------
* `hp_cur_by_id` absent pour la cible (unite hors de l'etat suivi) -> `None`, la cible est sautee.
  Le natif, lui, lirait `GetStat` sur une entite qu'il a par construction ; ce cas n'existe que
  cote port, quand le canal ne publie pas la cible.
* Le comptage du gate se fait sur les paires (cible, positions eligibles) du meme mirror que le
  balayage lui-meme (`_PlanTargetPlaybook.generate_candidates`), donc il herite exactement des
  memes bornes que lui -- ni plus ni moins.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook


class AugmentedAssaultPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.AugmentedAssaultPlaybook$$EvaluateNonComparable` (0x4c5 = 1221).

    utilite(cible) = `Fix64(GetStat(cible, 5 = Health))` = les PV COURANTS de la cible ennemie ;
    gate de position `|cibles eligibles| > 1`."""
    ABILITY_ID = int(ActiveAbilityType.AugmentedAssault)   # 0x4c5 = 1221
    MIN_UTILITY = 1.0     # `...AugmentedAssaultPlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)
    #: `if (1 < targets.Count)` -- le natif exige STRICTEMENT PLUS d'UNE cible eligible depuis la
    #: position evaluee. Litteral LU dans le corps (`1 < *(int *)(list + 0x18)`).
    _MIN_ELIGIBLE_TARGETS = 2

    def min_eligible_targets(self) -> int:
        """`if (1 < targets.Count)` du corps natif -- gate PAR POSITION (cf. l'en-tete du module)."""
        return self._MIN_ELIGIBLE_TARGETS

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64.op_Implicit(UnitExtensions.GetStat(entities@+0x10, 5 = Health, 0, 0))`.

        AUCUN filtre : le corps de 1221 ne lit ni effet (contraste `VexillaMagnifica`) ni tuile
        (contraste `FireAndReposition`). PV absents du canal -> `None` (cible sautee, borne INF)."""
        hp = ctx.hp_cur_by_id.get(target)                          # GetStat(cible, 5 = Health)
        if not hp or hp <= 0:
            return None
        return float(hp)
