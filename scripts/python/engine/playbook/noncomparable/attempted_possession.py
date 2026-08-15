"""AttemptedPossessionPlaybook -- face DECISION de `1101 AttemptedPossession` (`thousSorcerer`). #590."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.entity_type import EntityType

from ._base import NCContext, _PlanTargetPlaybook, has_eligible_normal_attack_target

#: Le filtre que `IdunBattle.Entities.UnitExtensions$$GetChildrenUnits` applique aux enfants rendus
#: par `GetChildren` : il ne garde que ceux dont `<IEntity slot 1>.Type` vaut ce membre. Ecrit par
#: son NOM et non par l'ordinal `1` -- le canal que le port lit (`Scene.parent_by_id`) est deja
#: unit-only, donc le filtre y est STRUCTUREL ; le nommer garde la lecture visible le jour ou la
#: source changerait.
_ENFANT_RETENU = EntityType.Unit


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

    ⚠ **LES DEUX INCREMENTS SONT PORTES DEPUIS `#590-r7`, ET LA PREMISSE QUI L'INTERDISAIT ETAIT
    PERIMEE (increment 1) OU MAL ATTRIBUEE (increment 2).** L'ancienne redaction disait que les
    deux termes exigeaient des substrats absents de `NCContext` ; re-mesure :
      * `GetChildrenUnits(target, state)` -- le lien parent est publie **depuis #378** par
        `combatSnapshot.units[].parentId` (live) et par `Scene.from_state` (offline), et il arrive
        au playbook par `ctx.scene.parent_by_id`. `BLOCAGE: seeding` etait **PERIME** ;
      * `GetEligibleTargetsForNormalAttack(target, targetPosition)` -- le canal `abilityTargets`
        n'est pas << oriente CASTER >> : le hook filtre `IsControlledByCurrentPlayer`, donc tout
        allie du joueur courant repond et aucun ennemi. Le blocage etait donc `etage`, pas
        `seeding`, et l'etage EXISTE deja : le mirror offline (portee + obscurcissement) du foyer
        `_base.has_eligible_normal_attack_target`, que `ExemplarOfTheKauyonPlaybook` consomme pour
        le MEME predicat natif.
    Ce qui subsiste, et qui est ecrit sur chaque helper : les deux termes sont des **BORNES
    INFERIEURES** (un fait non mesurable n'incremente pas), donc l'utilite portee est <= celle du
    natif. Le PLANCHER reste fidele -- `1 >= MIN_UTILITY = 1`, donc `Bucket.AddAction` retient la
    candidate : le port ne REFUSE jamais un cast que le natif accepterait (degradation PERMISSIVE,
    la convention du module). Ce qui etait perdu et qui est desormais rendu, c'est le RANKING entre
    plusieurs cibles eligibles, qu'une utilite constante ecrasait au profit de la premiere enumeree.

    PAS DE `should_evaluate` PORTE, et c'est une LECTURE prudente : `AttemptedPossessionPlaybook`
    n'expose que trois corps (`.ctor`, `.cctor`, `EvaluateNonComparable`) dans les DEUX tables.
    L'absence dans les tables ne PROUVE pas l'absence de surcharge (dedup de corps triviaux) -- le
    defaut de base (`BasePlaybook$$ShouldEvaluate` = True constant) est ce que le port rend.

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : 1101 est ABSENTE de la table mesuree
    `NATIVE_PRIORITY`, donc `native_priority(1101)` rendrait `0` de toute facon."""
    ABILITY_ID = int(ActiveAbilityType.AttemptedPossession)   # 1101 = 0x44d (argument du ctor natif)
    MIN_UTILITY = 1.0                       # `...AttemptedPossessionPlaybook$$.cctor` = Fix64(1)

    #: L'utilite de DEPART de la boucle native (`Fix64.op_Implicit((void *)0x1)`), avant les deux
    #: `op_Increment` conditionnels -- pas une constante choisie.
    BASE_UTILITY = 1.0

    @staticmethod
    def _has_children_units(ctx: NCContext, target) -> bool | None:
        """`IdunBattle.Entities.UnitExtensions$$GetChildrenUnits(target, this.<+0x20 state>)
        .Count > 0` -- le PREMIER increment. RELU :

            GetChildrenUnits(unit, state)
              = [ e for e in GetChildren(unit, state, selector: null)
                    if <IEntity slot 1>.Type == EntityType.Unit ]

            GetChildren(unit, state, selector)
              = [ state.<slot 0x29>(id) for id in <composant enfants @+0x10> ]   # selector null

        SUBSTRAT, et il EXISTE des DEUX cotes -- la premisse `BLOCAGE: seeding` de la fiche est
        PERIMEE : `ctx.scene.parent_by_id` (`ChildComponent.ParentId`, capteur #378) est renseigne
        en LIVE par `combatSnapshot.units[].parentId` et OFFLINE par `Scene.from_state`. On
        l'INVERSE (le natif lit la liste du PARENT, le canal porte le lien vu de l'ENFANT).

        TROIS ECARTS NOMMES, tous de sens RESTRICTIF (ils SOUS-comptent, donc n'ajoutent jamais un
        `+1` que le natif n'aurait pas donne) :
          * le natif ne filtre PAS la vie (`selector: null`) ; `combatSnapshot.units[]` ne porte que
            les VIVANTS (`unitsNotAlive` est un bloc separe, sans `parentId`). Un summon MORT encore
            reference par le composant du parent compte chez le natif, pas ici ;
          * les MACHINES OF WAR sont hors du canal ;
          * le filtre `_ENFANT_RETENU` (= `EntityType.Unit`) du natif est ici STRUCTUREL et non
            teste : le canal ne porte que des unites (cf. la constante de module).

        TRI-ETAT : `None` = PAS MESURE (`scene` absente, ou lien parent jamais capte pour cette
        bataille) -> l'appelant N'INCREMENTE PAS, mais il ne doit pas lire ce `None` comme un
        << pas d'enfant >> mesure."""
        scene = getattr(ctx, "scene", None)
        if scene is None:
            return None
        table = getattr(scene, "parent_by_id", None)
        if not table:
            return None                     # capteur muet : jamais un `False` fabrique
        tid = target if not isinstance(target, dict) else target.get("id")
        return any(p == tid for p in table.values())

    @staticmethod
    def _target_can_attack(ctx: NCContext, target) -> bool:
        """`BasePlaybook$$GetEligibleTargetsForNormalAttack(target, entities.TargetPosition)
        .<+0x10>.Count > 0` -- le SECOND increment.

        ⚠ **LE << CASTER >> DE CETTE QUESTION EST LA CIBLE, PAS NOUS.** Le natif passe `target` et
        SA position : << cette unite, la ou elle est, a-t-elle quelqu'un a frapper ? >>. Ses
        adversaires sont donc NOS unites -- c'est pourquoi le foyer
        `_base.has_eligible_normal_attack_target` prend les positions adverses en ARGUMENT au lieu
        de les deriver : le camp adverse depend de qui l'on interroge.

        ⚠ **LA VOIE RPC EST FERMEE ICI, ET LA CAUSE N'EST PAS CELLE QU'ANNONCAIT LA FICHE.** Le
        canal `abilityTargets` n'est pas << oriente caster >> : le hook filtre
        `IsControlledByCurrentPlayer` (`frida/hooks/features/ai-step/rpc-targeting.ts`), donc TOUT
        allie du joueur courant repond et AUCUN ennemi. La cible d'`AttemptedPossession` etant un
        ENNEMI, elle rendrait `units: []` -- indistinguable d'un << aucune cible >>. Le blocage
        reel n'etait donc pas `seeding` mais `etage`, et l'etage EXISTE : le foyer offline
        (portee + obscurcissement) est le meme que celui d'`ExemplarOfTheKauyonPlaybook`.

        Adversaires derives d'`obs_units` par `teamId` -- surtout pas `ctrl`, qui designe le camp
        CONTROLE et suivrait le controle mental la ou l'equipe ne le suit pas. Les MACHINES OF WAR
        sont hors de ce canal (ecart deja nomme par `occupant_team_by_pos`) : elles ne sont pas
        comptees comme cibles potentielles de l'ennemi -> SOUS-comptage, sens RESTRICTIF.

        BORNE SUPERIEURE sur les etages portes (cf. le foyer, residu `#975-r1`) : les etages
        manquants ne peuvent que RETIRER des cibles."""
        tid = target if not isinstance(target, dict) else target.get("id")
        # `getattr` et non l'attribut : un contexte de test degrade (ou un appelant offline qui ne
        # construit pas la ligne `observeBattle`) ne doit pas faire CRASHER une face DECISION --
        # il doit rendre << pas d'increment >>, ce qui est la borne INFERIEURE assumee.
        obs = getattr(ctx, "obs_units", None) or []
        row = next((u for u in obs
                    if u.get("squadId") == tid and not u.get("isDead")), None)
        if row is None or row.get("teamId") is None or row.get("col") is None:
            return False                     # cible hors canal -> aucun increment (borne INF)
        team = int(row["teamId"])
        foes = [(u["col"], u["row"]) for u in obs
                if not u.get("isDead") and u.get("teamId") is not None
                and int(u["teamId"]) != team and u.get("col") is not None]
        return has_eligible_normal_attack_target(ctx, tid, (row["col"], row["row"]), foes)

    def evaluate_non_comparable(self, tile, target, ctx):
        """Le compteur `1 / 2 / 3` de la boucle native -- MIRROR terme a terme :

            utility = Fix64.op_Implicit(1)                                       # PLANCHER
            if (GetChildrenUnits(target, state).Count > 0)  utility++            # increment 1
            if (GetEligibleTargetsForNormalAttack(target, entities.TargetPosition)
                    .<+0x10>.Count > 0)                     utility++            # increment 2

        Les deux `op_Increment` sont INDEPENDANTS (pas d'`else`) : les quatre combinaisons existent
        et l'utilite prend bien 1, 2 ou 3.

        Cible absente -> `None` (pas de candidat) : le natif n'entre dans la boucle que sur les
        cibles rendues par `GetEligibleTargetsSelectable`, donc une cible non resolue n'y est pas.

        ⚠ **LES DEUX INCREMENTS SONT DES BORNES INFERIEURES** (cf. les deux helpers) : un terme non
        mesurable n'incremente pas. Le port ne peut donc que SOUS-estimer l'utilite, jamais la
        sur-estimer -- et le plancher `1 >= MIN_UTILITY` garantit que la candidate reste retenue par
        `Bucket$$AddAction`. Le sens de la degradation est conserve : on ne REFUSE jamais un cast
        que le natif accepterait ; on peut seulement mal RANKER deux cibles eligibles."""
        if target is None:
            return None
        u = self.BASE_UTILITY
        if self._has_children_units(ctx, target):
            u += 1.0                                    # `Fix64.op_Increment(utility)`
        if self._target_can_attack(ctx, target):
            u += 1.0                                    # `Fix64.op_Increment(utility)`
        return u
