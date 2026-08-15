"""#969-r4 -- `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluateTarget`, FOYER UNIQUE.

CE QUE LE NATIF FAIT, et OU. Relu sur `t6dpr4k06g` -- et la localisation de la fiche est
CORRIGEE : le `Remove` n'est PAS dans `GetEligibleTargetsSelectable` (3 surcharges) mais dans
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` (4 surcharges), que la
premiere APPELLE. Le nom du lambda le disait deja
(`...BasePlaybook$$u003CGetEligibleTargetsEntitiesu003Eb__58_0`) :

    GetEligibleTargetsEntities(this, caster, possibleCasterPosition):
        r    = IAttackQuery.<slot 0x42>(this-><+0x28>, caster, position, this-><+0x10>);
        list = r-><+0x10>;
        ListExtensions.Remove(list, new Predicate(this, <GetEligibleTargetsEntities>b__58_0));
        return list;

    <GetEligibleTargetsEntities>b__58_0(this, t):
        return !this.<vtable +0x248>(t);          // = !ShouldEvaluateTarget(t)

    BasePlaybook$$ShouldEvaluateTarget(this, target):
        if (EntityExtensions.IsUnit(target)
            && EntityExtensions.CurrentOwnerIsEnvironment(target, this-><+0x20>)) return false;
        if (UnitExtensions.IsIrrelevantObject(target)) return false;
        return true;

    EntityExtensions$$CurrentOwnerIsEnvironment(entity, state):
        return GetCurrentPlayer(entity, state)-><+0x20>-><+0x20> == 2;   // PlayerType.Environment

    UnitExtensions$$IsIrrelevantObject(unit):
        if (!TryGetComponent<BaseUnitComponent>(unit, out c)) return false;
        if (c.HasTrait(0x1b)) return true;                       // UnitTrait.Steppable
        return GetStat(unit, StatType.Attack /* 0 */) < 1 && c.HasTrait(0xd);  // UnitTrait.Object

⚠ LE SEUIL EST `Attack < 1`, PAS `Attack == 0` ni « l'unite a une arme » : c'est le litteral du
natif, et il est ce qui rend le predicat MESURABLE (cf. le porteur ci-dessous).

⚠ LE SLOT `0x248` EST VIRTUEL : un playbook peut le surcharger, et l'absence d'un
`<X>Playbook$$ShouldEvaluateTarget` dans les tables ne prouve RIEN (dedup ICF, cf. CLAUDE.md).
Ce foyer porte le corps de BASE ; une surcharge trouvee plus tard se branchera ici.

POURQUOI CE PORT N'EST PAS SPECULATIF -- LE PORTEUR EXISTE, ET IL EST MESURE (2026-08-15).
La fiche declare `BLOCAGE: porteur` (<< aucun montage n'amene une unite Environment ou un
decor >>). Re-mesure : les deux termes n'ont pas le meme sort.

  * `IsIrrelevantObject` A un porteur, et meme un TEMOIN NON DEGENERE. `unit_map.py find
    --trait Steppable` rend les POWER-UPS (`powupHits`, `powupResurrect`,
    `powupSummonSpawn_*`, ...) et `--trait Object` les `LootObj_*` (Supply Pods, Strongbox).
    Aucun n'est au seed BC (175 unites) -> `applyAddUnit` y echoue EN SILENCE ; ils entrent par
    `catalog_inject.write_augmented_seed_bc` puis `applyAddUnit`. MESURE, runner 112, board
    MC1_67 : `LootObj_Strongbox_Imp` (traits `13,28`, `stats.attack = 0`) apparait dans
    `abilityTargets(77).fromHere` A COTE d'`orksKillaKan` -- le port le retient donc comme
    cible eligible, la ou `ShouldEvaluateTarget` le RETIRE. C'est exactement la degradation
    PERMISSIVE que le residu decrit, reproduite.

  * `CurrentOwnerIsEnvironment` n'a PAS de porteur a ce jour : les trois montages joues rendent
    `False` sur toutes les unites (owner 3 / 4, `PlayerType` Human/AI). Le terme est donc PORTE
    et MESURE (le capteur #1072 est en vol et rend `False`, pas `null`), mais son regime
    DISCRIMINANT reste a atteindre. C'est un residu, pas un blocage du port.

TRI-ETAT, ET IL COMMANDE LE SENS DU DOUTE. On ne RETIRE que sur une mesure POSITIVE : un
substrat non mesure (`traits` absents, `currentOwnerIsEnvironment` a `None`, attaque inconnue)
laisse la cible EN PLACE. C'est le choix conservateur -- il preserve exactement le comportement
d'avant la ou l'on ne sait pas, au lieu de restreindre sur une supposition. La degradation
restante est donc la degradation d'AVANT, jamais une nouvelle.
"""
from __future__ import annotations

from engine.entities.traits.unit_trait import UnitTrait

#: `UnitTrait.Steppable = 0x1b` et `UnitTrait.Object = 0xd`, par leur MEMBRE -- l'ordinal se
#: re-derive du build, un litteral recopie devient faux en silence (CLAUDE.md, regle ENUM).
#: `UnitContext.traits` porte des IDS (`list[int]`), d'ou l'usage des membres et non des noms
#: (contrairement a `Scene._enmity_adjacent`, qui lit `ctx.traits` en NOMS -- deux
#: representations coexistent dans le port, et les confondre rendrait ce filtre INERTE).
TRAIT_STEPPABLE = int(UnitTrait.Steppable)
TRAIT_OBJECT = int(UnitTrait.Object)
#: `GetStat(unit, StatType.Attack) < 1` -- le litteral du natif. Ce n'est pas `== 0` : une
#: attaque negative (possible sous debuff) rend l'objet IRRELEVANT elle aussi.
ATTACK_MIN_PERTINENT = 1


def _traits_ids(ctx) -> "set[int] | None":
    """Les traits de la cible en IDS, ou `None` = PAS MESURE.

    ⚠ `UnitContext.traits` est renseigne depuis le gameconfig quand la mesure live manque
    (`traits_measured` faux). On l'accepte : le natif lit
    `BaseUnitComponent.Traits`, que `UnitFactory$$InitBaseComponent` RECOPIE de
    `UnitConfiguration.Traits`, elle-meme decalquee du catalogue. Un trait AJOUTE en bataille
    (`AddTrait`) n'est vu que par la voie mesuree -- c'est une limite CONNUE du substrat
    offline, pas de ce filtre."""
    if ctx is None:
        return None
    tr = getattr(ctx, "traits", None)
    if not tr:
        return None
    try:
        return {int(t) for t in tr}
    except (TypeError, ValueError):
        return None


def is_irrelevant_object(ctx) -> "bool | None":
    """`IdunBattle.Entities.UnitExtensions$$IsIrrelevantObject`. `None` = PAS MESURE.

    Ordre du natif conserve : le trait `Steppable` court-circuite AVANT toute lecture de stat --
    un power-up n'a pas besoin d'avoir une attaque lisible pour etre ecarte."""
    traits = _traits_ids(ctx)
    if traits is None:
        return None                     # pas de `BaseUnitComponent` lisible -> on ne tranche pas
    if TRAIT_STEPPABLE in traits:
        return True
    if TRAIT_OBJECT not in traits:
        return False                    # MESURE : ni Steppable ni Object -> pertinent
    atk = getattr(ctx, "attack", None)
    if atk is None:
        return None                     # trait Object mais attaque non lue -> indetermine
    return int(atk) < ATTACK_MIN_PERTINENT


def should_evaluate_target(ctx, *, is_unit: bool = True,
                           has_base_unit_component: bool | None = None) -> bool:
    """`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluateTarget`, mirror 1:1.

    DEUX drapeaux, et les CONFONDRE serait une faute de port :

      * `is_unit` = `IdunBattle.Entities.EntityExtensions$$IsUnit(target)`. Il ne garde QUE le
        PREMIER terme (`IsUnit && CurrentOwnerIsEnvironment`).
      * `has_base_unit_component` garde le SECOND : `IsIrrelevantObject` s'applique a toute
        entite, mais son corps commence par `TryGetComponent<BaseUnitComponent>(unit, out c)` et
        rend `false` sans composant -- une entite TUILE n'est donc JAMAIS ecartee.

    ⚠ ON NE PEUT PAS RABATTRE LE SECOND SUR LE PREMIER, et c'est un test qui l'a montre : une
    MACHINE OF WAR n'est pas forcement `IsUnit`, mais elle PORTE un `BaseUnitComponent` (son
    `MachineComponent` en DERIVE -- c'est exactement ce qui fait marcher la voie
    `GetBaseUnitComponent` de #1039). Ecrire `if not is_unit: return True` aurait donc rendu le
    filtre inerte sur les MoW. Defaut : `has_base_unit_component = is_unit or True` n'aurait
    aucun sens -- on prend `None` = « non precise » et on evalue, ce qui est le cas commun ;
    l'appelant qui SAIT que la cible est une tuile passe `False`.

    Rend `True` (= garder) des que le doute subsiste : cf. le bloc TRI-ETAT du module."""
    if is_unit and getattr(ctx, "current_owner_is_environment", None) is True:
        return False
    if has_base_unit_component is False:
        return True                     # pas de `BaseUnitComponent` -> `IsIrrelevantObject` = false
    return is_irrelevant_object(ctx) is not True


def filtrer_cibles(ctx_by_id, cibles, cle=None, kind=None, est_tuile=None):
    """Applique le `ListExtensions.Remove` du natif a une liste de cibles deja calculee.

    `ctx_by_id` = `{entityId: UnitContext}` (ou tout objet portant `traits` / `attack` /
    `current_owner_is_environment`). `cle` extrait l'`entityId` d'un element ; `kind` dit si
    l'element est une UNITE (defaut : oui) ; `est_tuile` dit s'il n'a PAS de `BaseUnitComponent`
    (defaut : deduit de `kind`, faute de mieux -- cf. les deux drapeaux de
    `should_evaluate_target`).

    ⚠ UNE CIBLE SANS `UnitContext` EST GARDEE. Le port n'hydrate pas toutes les entites (une
    entite-tuile n'en a pas), et retirer sur l'absence transformerait un trou de substrat en
    restriction -- l'inverse exact de la degradation qu'on corrige."""
    if not cibles:
        return cibles
    tab = ctx_by_id or {}
    garde = []
    for element in cibles:
        eid = cle(element) if cle is not None else element
        ctx = tab.get(eid) if eid is not None else None
        if ctx is None:
            garde.append(element)
            continue
        est_unite = True if kind is None else bool(kind(element))
        tuile = (bool(est_tuile(element)) if est_tuile is not None
                 else (kind is not None and not est_unite))
        if should_evaluate_target(ctx, is_unit=est_unite,
                                  has_base_unit_component=(False if tuile else None)):
            garde.append(element)
    return garde
