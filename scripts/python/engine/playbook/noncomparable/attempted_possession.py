"""AttemptedPossessionPlaybook -- face DECISION de `1101 AttemptedPossession` (`thousSorcerer`). #590."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import _PlanTargetPlaybook


class AttemptedPossessionPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.AttemptedPossessionPlaybook` -- MIRROR du decompile.

    ⚠ **LA BASE EST `NonComparablePlaybook`, ET LE NOM GHIDRA DIT LE CONTRAIRE.** Le ctor decompile
    affiche `ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor(this, 0x44d)` -- corps gshared
    DEDUPLIQUE, donc mislabele. La chaine de parents LUE dans `data/symbols/<build>/frida/
    classes.tsv` tranche : `IdunBattle.AI.Playbook.Loki.AttemptedPossessionPlaybook` ->
    `IdunBattle.AI.Playbook.NonComparablePlaybook`1`. C'est la STRUCTURE qui decide, jamais le nom
    (doctrine gshared) -- meme piege que `MindControlPlaybook`.

    `...AttemptedPossessionPlaybook$$.ctor` : `NonComparablePlaybook<...>..ctor(this, 0x44d)`
    -> `ABILITY_ID = 1101`.

    `...AttemptedPossessionPlaybook$$.cctor` : `<champ statique> = FixMath.NET.Fix64.op_Implicit(1)`
    -> `MIN_UTILITY = 1`.

    `...AttemptedPossessionPlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` --
    MIRROR 1:1, terme a terme :

        bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(<statique> = 1) )
        foreach (abilityEntities in BasePlaybook.GetEligibleTargetsSelectable(
                                        caster, casterPosition.MainTile)) {
            utility = Fix64.op_Implicit(1)                                    # PLANCHER
            enfants = UnitExtensions.GetChildrenUnits(target, this.state)
            if (enfants.Count > 0)                     utility = Fix64.op_Increment(utility)
            cibles  = BasePlaybook.GetEligibleTargetsForNormalAttack(
                          target, abilityEntities.TargetPosition)
            if (cibles.<+0x10>.Count > 0)              utility = Fix64.op_Increment(utility)
            bucket.AddAction( BasePlaybook.GenerateAction(casterPosition, target, utility) )
        }
        return bucket

    => l'utilite est un COMPTEUR a trois valeurs, `1 / 2 / 3`, et chacun des deux increments
    repond a une des deux facons dont le cast peut PRODUIRE quelque chose : la cible a des summons
    a retourner, et/ou elle-meme a quelqu'un a frapper. C'est le MEME couple de questions que le
    gate dynamique `GetDynamicInvalidTargetReason` pose en REFUS -- ici il les pose en PREFERENCE.

    ⚠ **LES DEUX INCREMENTS NE SONT PAS PORTES, ET LE PLANCHER L'EST -- ECART NOMME.** Le port rend
    l'utilite BASE `1` pour toute cible eligible. Les deux termes exigent des substrats que
    `NCContext` n'expose pas :
      * `GetChildrenUnits(target, state)` -- le lien `parentId` d'une unite ENNEMIE. `NCContext`
        porte `obs_units` (id/team/player/visualId/pos) mais **pas** `parentId` ;
      * `GetEligibleTargetsForNormalAttack(target, targetPosition)` -- les cibles legales de
        l'attaque normale d'une unite ENNEMIE. Le canal `ability_targets` est un RPC oriente
        CASTER, il ne repond pas cette question-la.
    Consequence MESURABLE et bornee : le port propose le cast sur toute cible eligible avec une
    utilite CONSTANTE, donc au tie d'utilite c'est la PREMIERE position/cible de l'ordre natif qui
    gagne (`Bucket.AddAction` ne remplace que sur STRICTEMENT superieur) -- le cast a lieu, mais le
    CHOIX DE CIBLE entre plusieurs eligibles n'est pas rank. Residu `#590-r7`
    (`BLOCAGE: seeding` -- il faut publier `parentId` et un canal de cibles-d'attaque par unite
    dans `NCContext`).
    Le PLANCHER, lui, est fidele : `1 >= MIN_UTILITY = 1`, donc `Bucket.AddAction` retient la
    candidate -- c'est-a-dire que le port ne REFUSE jamais un cast que le natif accepterait
    (degradation PERMISSIVE, la convention du module). L'inverse -- rendre `None` faute de mesure --
    aurait rendu l'ability INCASTABLE par l'IA, un no-op de plus.

    PAS DE `should_evaluate` PORTE, et c'est une LECTURE prudente : `AttemptedPossessionPlaybook`
    n'expose que trois corps (`.ctor`, `.cctor`, `EvaluateNonComparable`) dans les DEUX tables.
    L'absence dans les tables ne PROUVE pas l'absence de surcharge (dedup de corps triviaux) -- le
    defaut de base (`BasePlaybook$$ShouldEvaluate` = True constant) est ce que le port rend.

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : 1101 est ABSENTE de la table mesuree
    `NATIVE_PRIORITY`, donc `native_priority(1101)` rendrait `0` de toute facon."""
    ABILITY_ID = int(ActiveAbilityType.AttemptedPossession)   # 1101 = 0x44d (argument du ctor natif)
    MIN_UTILITY = 1.0                       # `...AttemptedPossessionPlaybook$$.cctor` = Fix64(1)

    #: L'utilite de DEPART de la boucle native (`Fix64.op_Implicit((void *)0x1)`), avant les deux
    #: `op_Increment` conditionnels. C'est ce que le port rend, faute de substrat pour les deux
    #: termes (cf. la docstring de classe) -- pas une constante choisie.
    BASE_UTILITY = 1.0

    def evaluate_non_comparable(self, tile, target, ctx):
        """`Fix64.op_Implicit(1)` -- le PLANCHER de la boucle native, sans les deux increments.

        Cible absente -> `None` (pas de candidat) : le natif n'entre dans la boucle que sur les
        cibles rendues par `GetEligibleTargetsSelectable`, donc une cible non resolue n'y est pas.
        """
        if target is None:
            return None
        return self.BASE_UTILITY
