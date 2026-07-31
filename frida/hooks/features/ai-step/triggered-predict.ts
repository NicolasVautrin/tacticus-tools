/** #369 — la face TRIGGERED de l'oracle playbook : chargement PAR KEY-SPACE + invocation.
 *
 *  POURQUOI CE MODULE EXISTE. `playbook-predict.ts::loadPlaybook` résout
 *  `PlaybookDatabase.LoadPlaybook` en désambiguïsant par le TYPE du 1er paramètre —
 *  `ActiveAbilityType`. C'était nécessaire (un `findMethodByParamCount(1)` aveugle tombait sur
 *  l'overload `UnitSpecificBehaviourType`), mais ça FIGE le key-space : un appelant qui passe un id
 *  `TriggeredAbilityType` reçoit le playbook de l'ability ACTIVE de MÊME ID, sans aucune erreur.
 *  Mesuré : `1103` -> `SuperchargePlaybook`, `1054` -> `CallRipperSwarmsPlaybook`,
 *  `1247` -> `DefaultActiveAbilityPlaybook`. Détail : `docs/rl/case-369-oracle-triggered-playbook.md`.
 *
 *  LES QUATRE ENTRÉES NATIVES, lues dans `data/symbols/<build>/frida/methods.tsv` :
 *    `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(ActiveAbilityType, bool)`  -> `IPlaybook`
 *    `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(TriggeredAbilityType)`     -> `ITriggeredAbilityPlaybook`
 *    `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner(TriggeredAbilityType)`
 *                                                                            -> `ITriggeredAbilityNonOwnerPlaybook`
 *    `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(UnitSpecificBehaviourType)`-> `IUnitSpecificBehaviourPlaybook`
 *
 *  ⚠ LE DURCISSEMENT EST NATIF, PAS FABRIQUÉ. Les deux corps TRIGGERED n'ont PAS la paire
 *  cache-défaut / builder-défaut que porte la face ACTIVE : sur un miss du registry ils font
 *  `return 0`. Et
 *  `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext`
 *  — la boucle qui fait jouer TOUS les playbooks triggered d'un caster — traite ce `0` par un
 *  `continue`. Rendre une ERREUR sur null est donc la lecture fidèle : il n'existe aucun playbook
 *  par défaut de ce côté, et rien à inventer.
 *
 *  L'ENTRÉE INVOCABLE N'EST PAS `Evaluate`. `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1`
 *  dérive de `System.Object` (lu dans `classes.tsv`) — c'est une hiérarchie SÉPARÉE de
 *  `BasePlaybook` -> `Playbook`1` -> {`Comparable`, `NonComparable`}. Il n'a donc ni `Evaluate` ni
 *  `Make*Predictions`. Ce que le natif invoque, c'est
 *  `<ITriggeredAbilityPlaybook slot 3>.CalculateAttackUtilityInSteps(UtilityAttackCase, getUtilityVal)`,
 *  et le `UtilityAttackCase` se construit par la factory statique
 *  `IdunBattle.AI.Utilities.UtilityAttackCase$$Base(caster, casterPosition, target, abilityType)`
 *  (overload `casterPosition: UnitPosition` — celui qu'utilisent
 *  `ComparablePlaybook<T>$$CalculateActionUtility` et `Playbook<T>$$GetTargetUtilityDiffOnDisplace` ;
 *  l'homonyme prend un `casterTile: IEntity`, d'où la désambiguïsation par TYPE ci-dessous).
 *
 *  `getUtilityVal` EST OPTIONNEL, et ce n'est pas une approximation :
 *  `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue`
 *  commence par `if (dict == null || !TryGetValue(...)) { log(warning); return 0; }`. Un appel sans
 *  les poids ne lève pas — il rend 0 sur chaque poids, ce qui décale l'UTILITÉ, mais laisse INTACTE
 *  la prédiction de dégât capturée au ctor (elle vient de `GetAttackPrediction`, pas des poids).
 *  L'appelant doit donc lire `bucketUtil`/l'utilité rendue comme NON COMPARABLE au natif tant que
 *  les poids ne sont pas fournis ; les `captured`, eux, sont fidèles.
 *
 *  Aucune RVA : tout est résolu par `findClassAnywhere` + `findMethodByParamClasses`/`ByParamCount`.
 */
import {
    findClassAnywhere, findMethodByNameSuffix, findMethodByParamClasses, findMethodByParamCount,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";

/** Les trois key-spaces d'enum que `PlaybookDatabase` indexe. `active` = comportement historique. */
export type AbilityKeySpace = "active" | "triggered" | "triggeredNonOwner";

export const ABILITY_KEY_SPACES: AbilityKeySpace[] = ["active", "triggered", "triggeredNonOwner"];

/** Le type de paramètre natif qui désambiguïse chaque overload homonyme. C'est LA donnée qui
 *  sépare les key-spaces — un id égal ne dit rien, seul le TYPE tranche. */
const KEY_SPACE_PARAM_CLASS: Record<AbilityKeySpace, string> = {
    active: "ActiveAbilityType",
    triggered: "TriggeredAbilityType",
    triggeredNonOwner: "TriggeredAbilityType",
};

/** Le nom natif de la méthode par key-space (`LoadPlaybookNonOwner` n'est PAS un overload de
 *  `LoadPlaybook` : c'est un symbole distinct, avec sa propre paire de dictionnaires). */
const KEY_SPACE_METHOD: Record<AbilityKeySpace, string> = {
    active: "LoadPlaybook",
    triggered: "LoadPlaybook",
    triggeredNonOwner: "LoadPlaybookNonOwner",
};

export function isAbilityKeySpace(v: unknown): v is AbilityKeySpace {
    return typeof v === "string" && (ABILITY_KEY_SPACES as string[]).indexOf(v) >= 0;
}

/** Résultat de chargement — jamais un pointeur nu : l'appelant doit pouvoir DIRE pourquoi il n'a
 *  rien, et savoir s'il a reçu le fallback par défaut au lieu du playbook demandé. */
export interface PlaybookLoad {
    playbook: NativePointer;
    /** `"registry"` = playbook bespoke ; `"default"` = fallback `DefaultActiveAbilityPlaybook`
     *  (face ACTIVE uniquement, et seulement si l'appelant l'a autorisé). */
    source: "registry" | "default" | null;
    error?: string;
}

/** `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(TriggeredAbilityType)` — un SEUL paramètre, AUCUN
 *  `fallbackToDefault`. Le corps rend `0` quand le registry `_triggeredPlaybookBuilders` n'a pas la
 *  clef, et c'est la réponse complète : il n'existe pas de builder par défaut de ce côté.
 *  Idem pour `$$LoadPlaybookNonOwner`. */
export function loadPlaybookByKeySpace(
    db: NativePointer, abilityType: number, keySpace: AbilityKeySpace,
    allowDefault: boolean,
): PlaybookLoad {
    const dbCls = db.readPointer();
    const method = KEY_SPACE_METHOD[keySpace];
    const paramClass = KEY_SPACE_PARAM_CLASS[keySpace];
    const abilBuf = Memory.alloc(4); abilBuf.writeS32(abilityType | 0);

    if (keySpace === "active") {
        // Overload à DEUX paramètres. On l'appelle d'abord avec `fallbackToDefault = false` :
        // c'est le paramètre NATIF, pas une astuce — il sépare « playbook bespoke » de « rien ».
        const mi = findMethodByParamClasses(dbCls, method, [paramClass, null]);
        if (!mi) {
            return { playbook: ptr(0), source: null,
                error: "PlaybookDatabase.LoadPlaybook(ActiveAbilityType, bool) non résolu" };
        }
        const noFallback = Memory.alloc(1); noFallback.writeU8(0);
        let pb: NativePointer;
        try { pb = invokeMethod(mi.info, db, [abilBuf, noFallback]); }
        catch (e) {
            return { playbook: ptr(0), source: null,
                error: "LoadPlaybook(ActiveAbilityType) a levé: " + (e as Error).message };
        }
        if (!pb.isNull()) return { playbook: pb, source: "registry" };
        if (!allowDefault) {
            return { playbook: ptr(0), source: null,
                error: "aucun playbook ACTIVE bespoke pour ability " + abilityType
                    + " (le natif retomberait sur DefaultActiveAbilityPlaybook)"
                    + " — passe allowDefault:true si c'est bien ce que tu veux mesurer" };
        }
        const withFallback = Memory.alloc(1); withFallback.writeU8(1);
        try { pb = invokeMethod(mi.info, db, [abilBuf, withFallback]); }
        catch (e) {
            return { playbook: ptr(0), source: null,
                error: "LoadPlaybook(ActiveAbilityType, fallback) a levé: " + (e as Error).message };
        }
        if (pb.isNull()) {
            return { playbook: ptr(0), source: null,
                error: "LoadPlaybook(ActiveAbilityType, fallbackToDefault:true) a rendu null" };
        }
        return { playbook: pb, source: "default" };
    }

    // Faces TRIGGERED : UN paramètre, pas de fallback natif.
    const mi = findMethodByParamClasses(dbCls, method, [paramClass]);
    if (!mi) {
        return { playbook: ptr(0), source: null,
            error: "PlaybookDatabase." + method + "(TriggeredAbilityType) non résolu" };
    }
    let pb: NativePointer;
    try { pb = invokeMethod(mi.info, db, [abilBuf]); }
    catch (e) {
        return { playbook: ptr(0), source: null,
            error: method + "(TriggeredAbilityType) a levé: " + (e as Error).message };
    }
    if (pb.isNull()) {
        // Mirror EXACT du `continue` de
        // `TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext` —
        // sauf qu'ici il n'y a rien à itérer, donc c'est une réponse et non un skip.
        return { playbook: ptr(0), source: null,
            error: "aucun playbook " + (keySpace === "triggered" ? "TRIGGERED" : "TRIGGERED non-owner")
                + " pour ability " + abilityType
                + " (le natif rend null — il n'existe PAS de playbook par défaut de ce côté)" };
    }
    return { playbook: pb, source: "registry" };
}

/** `IdunBattle.AI.Utilities.UtilityAttackCase$$Base(caster, casterPosition, target, abilityType)`.
 *
 *  DEUX overloads homonymes, désambiguïsés par le TYPE du 2ᵉ paramètre :
 *    `(IEntity caster, IEntity casterTile,       IEntity target, Nullable<AbilityOrEffect>)`
 *    `(IEntity caster, UnitPosition casterPosition, IEntity target, Nullable<AbilityOrEffect>)`  <- celui-ci
 *
 *  `abilityType` est passé SANS valeur (`hasValue = false`) quand `abilityOrEffect` n'est pas
 *  fourni : c'est ce qu'un buffer zéro-rempli encode, et c'est le cas « pas d'ability nommée ».
 *  `UnitPosition` est un ValueType de 24 o boxés (8 o de données = la `List<ITile>`), d'où le
 *  pointeur DÉJÀ unboxé que rendent `unitPositionCurrent`/`unitPositionAtTile`. */
export function buildUtilityAttackCase(
    caster: NativePointer, casterPosition: NativePointer, target: NativePointer,
): { kase: NativePointer; error?: string } {
    const klass = findClassAnywhere("IdunBattle.AI.Utilities", "UtilityAttackCase");
    if (!klass) {
        return { kase: ptr(0), error: "classe IdunBattle.AI.Utilities.UtilityAttackCase introuvable" };
    }
    const mi = findMethodByParamClasses(klass, "Base", [null, "UnitPosition", null, null]);
    if (!mi) {
        return { kase: ptr(0),
            error: "UtilityAttackCase.Base(caster, UnitPosition, target, abilityType) non résolu" };
    }
    // `Nullable<AbilityOrEffect>` : `AbilityOrEffect` fait 40 o boxés (24 de données), donc le
    // Nullable tient largement dans 0x40. Zéro partout = `hasValue = false`.
    const nullableAbility = Memory.alloc(0x40);
    for (let k = 0; k < 0x40; k += 4) nullableAbility.add(k).writeU32(0);
    try {
        const kase = invokeMethod(mi.info, null, [caster, casterPosition, target, nullableAbility]);
        if (kase.isNull()) return { kase: ptr(0), error: "UtilityAttackCase.Base a rendu null" };
        return { kase };
    } catch (e) {
        return { kase: ptr(0), error: "UtilityAttackCase.Base a levé: " + (e as Error).message };
    }
}

/** Les trois entrées invocables d'un playbook TRIGGERED, telles que le natif les appelle.
 *  `inSteps` est la voie GÉNÉRIQUE (celle de `TriggeredAbilitiesUtility`) ; les deux autres sont
 *  des surcharges CONCRÈTES que seuls certains playbooks exposent (ex. `LightImUpPlaybook`) et qui
 *  sont exactement les call-sites demi-vers-le-pair de #350-r3b. */
export type TriggeredVia = "attackUtilityInSteps" | "attackUtilityForMainTarget"
    | "attackUtilityForSecondaryTarget";

export const TRIGGERED_VIAS: TriggeredVia[] = [
    "attackUtilityInSteps", "attackUtilityForMainTarget", "attackUtilityForSecondaryTarget",
];

export function isTriggeredVia(v: unknown): v is TriggeredVia {
    return typeof v === "string" && (TRIGGERED_VIAS as string[]).indexOf(v) >= 0;
}

const VIA_METHOD: Record<TriggeredVia, string> = {
    attackUtilityInSteps: "CalculateAttackUtilityInSteps",
    attackUtilityForMainTarget: "CalculateAttackUtilityForMainTarget",
    attackUtilityForSecondaryTarget: "CalculateAttackUtilityForSecondaryTarget",
};

const FIX64_ONE = 4294967296;   // 2^32 — Fix64 est un Q32.32 (cf. readFix64)

/** Invoque l'entrée demandée et rend la ou les utilités (Fix64) que le natif produit.
 *
 *  * `attackUtilityInSteps` rend un `IEnumerator<Fix64>` : on l'itère par `MoveNext`/`get_Current`
 *    comme le fait `TriggeredAbilitiesUtility`, qui SOMME les valeurs yieldées. On rend la liste
 *    ET la somme — la somme est ce que le natif accumule, la liste dit d'où elle vient.
 *  * `attackUtilityFor{Main,Secondary}Target` rendent un `Fix64` direct (arité 2 : `case`, `hits`).
 *
 *  `getUtilityVal` n'est PAS fourni (null) : voir l'en-tête du module — `GetUtilityValue` le tolère
 *  et rend 0, donc les utilités sont MINORÉES mais les prédictions capturées restent fidèles. */
export function invokeTriggeredAttackUtility(
    playbook: NativePointer, kase: NativePointer, via: TriggeredVia, hits: number,
): { utilities: number[]; total: number | null; arity: number; error?: string } {
    const pbCls = playbook.readPointer();
    const name = VIA_METHOD[via];

    if (via !== "attackUtilityInSteps") {
        const mi = findMethodByParamCount(pbCls, name, 2);
        if (!mi) {
            return { utilities: [], total: null, arity: 0,
                error: name + "(UtilityAttackCase, int) non résolu sur ce playbook" };
        }
        const hitsBuf = Memory.alloc(4); hitsBuf.writeS32(hits | 0);
        try {
            const boxed = invokeMethod(mi.info, playbook, [kase, hitsBuf]);
            if (boxed.isNull()) {
                return { utilities: [], total: null, arity: 2, error: name + " a rendu null" };
            }
            const v = boxed.add(0x10).readS64().toNumber() / FIX64_ONE;
            return { utilities: [v], total: v, arity: 2 };
        } catch (e) {
            return { utilities: [], total: null, arity: 2,
                error: name + " a levé: " + (e as Error).message };
        }
    }

    // Voie générique : `CalculateAttackUtilityInSteps(UtilityAttackCase, Func<string,int>)`.
    const mi = findMethodByParamCount(pbCls, name, 2);
    if (!mi) {
        return { utilities: [], total: null, arity: 0,
            error: name + "(UtilityAttackCase, getUtilityVal) non résolu sur ce playbook" };
    }
    let en: NativePointer;
    try { en = invokeMethod(mi.info, playbook, [kase, ptr(0)]); }
    catch (e) {
        return { utilities: [], total: null, arity: 2,
            error: name + " a levé: " + (e as Error).message };
    }
    if (en.isNull()) {
        return { utilities: [], total: null, arity: 2, error: name + " a rendu un enumerator null" };
    }
    const enCls = en.readPointer();
    const moveMi = findMethodByParamCount(enCls, "MoveNext", 0);
    // `get_Current` d'un `IEnumerator<Fix64>` est souvent une impl EXPLICITE d'interface
    // (nom qualifié) — même piège que `decodeEventsGeneric`, même parade.
    const curMi = findMethodByNameSuffix(enCls, "get_Current", 0);
    if (!moveMi || !curMi) {
        return { utilities: [], total: null, arity: 2,
            error: "IEnumerator<Fix64>: MoveNext/get_Current non résolus" };
    }
    const utilities: number[] = [];
    try {
        for (let i = 0; i < 64; i++) {
            const more = invokeMethod(moveMi.info, en, null);
            if (more.isNull() || more.add(0x10).readU8() === 0) break;
            const cur = invokeMethod(curMi.info, en, null);
            if (cur.isNull()) continue;
            utilities.push(cur.add(0x10).readS64().toNumber() / FIX64_ONE);
        }
    } catch (e) {
        return { utilities, total: null, arity: 2,
            error: "itération IEnumerator<Fix64>: " + (e as Error).message };
    }
    // `TriggeredAbilitiesUtility` accumule par `Fix64.op_Addition` ; en Q32.32 la somme des
    // valeurs décodées est la même chose (aucun arrondi intermédiaire n'est perdu ici).
    const total = utilities.reduce((a, b) => a + b, 0);
    return { utilities, total, arity: 2 };
}
