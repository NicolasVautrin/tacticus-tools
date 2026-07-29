/** RPCs SNAPSHOT stats/config/effets : combatSnapshot (capteur #100 abilityStates),
 *  statModSources, effectAbilityStates, unitAbilityStates, abilityConfigProbe, varTrace*.
 *  Scinde de rpc-view.ts (2026-07-11, >2300 l. — seuil ~1000 l.) ; l'API RPC est
 *  INCHANGEE (memes noms ctx.rpc.*), agregee par registerView (rpc-view.ts). */
import {
    class_get_name, class_get_namespace, findClass, findClassAnywhere, findMethod,
    findMethodByParamClasses, findMethodByParamCount, getFieldOffset, readIl2cppString, s,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { dumpEnum } from "../../il2cpp/enum-dump.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerClass, runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import {
    EntityType, forEachComponent, forEachEntity, projectMatchState,
    readBattleStatus, unitFootComponentClass,
} from "../../game/match-state.js";
import {
    readEffectsByUnit, readEffectsByTile, readRoundCapClock, readEffectAbilityStateRaw,
} from "../../game/effects.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { abilityName } from "../../data/ability-names.js";
import { TARGETING_RULE_BITS } from "../../data/targeting-rule-names.js";
import { Ctx } from "../../controller.js";
import {
    ActionResult, ActionSpec, activeAbilityMsgClass, applyOneAction,
    attackQueryOff, battleInServicesOff, dpqInServicesOff, entityServicesClass,
    extractTiles, extractTilePtrs,
    entityExtClass, finishUnitTurnMsgClass, getMovableTilesMi, getTilesMi, getTurnsFinishedMi,
    getUnitMainTile,
    invokeBool, invokeInt, isAliveMi, isCtrlByCurMi, LIST_SIZE, moveUnitMsgClass, movementQueryOff,
    mowAbilityTypes, readTileCoord, resolveDpq, servicesOff, summarize, unitAbilityTypes,
    unitExtClass,
} from "./internals.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    classFieldsDump, computeAttackPlans, computeDangerZone, computeExposure,
    projectMowsFull, projectUnitsFull,
} from "./projection.js";

// --- Snapshot one-shot des stats de combat résolues (prédiction 100% offline, doc §16) ---
// `UnitExtensions.GetStat(actor, StatType, StatPart, Nullable<BEntityId>)` (static 4-args
// @180ed3cb0) → valeur résolue (boxée int @+0x10). StatPart.Current=0 = valeur courante.
// StatType (enum): Attack=0 Movement=1 Defense=3 Health=5 BlockChance=7 BlockDamage=8
// CriticalChance=9 CriticalDamage=10 FixedArmor=16 ExtraHits=17 ExtraPierceMelee=21
// ExtraPierceRanged=22 ExtraMaxDamage=25 ExtraPierce=26. Faction/class/profil/traits = gameconfig ;
// effets = decisionView. C'est le SEUL accès live (one-shot au chargement BC) du prédicteur offline.
const getStatMi = unitExtClass ? findMethodByParamCount(unitExtClass, "GetStat", 4) : null;
// StatType ids (enum) partagés par `combatSnapshot` + `statModSources` — source unique
// (évite la divergence si on ajoute un stat d'un côté seulement, cf. discipline « check own port »).
const COMBAT_STAT_IDS: Record<string, number> = {
    attack: 0, movement: 1, defense: 3, health: 5, blockChance: 7,
    blockDamage: 8, critChance: 9, critDamage: 10,
    turnsStarted: 12,   // #122 : UnitComponent.turnsStarted@+0x58 (incr. StartTurn) = rounds started ;
                        // GetStat(unit,0xc) = UnitTurnsStartedFormula.Calculate @180f2d6c0. Base des
                        // hits Executioner (RoundsStarted).
    fixedArmor: 16,
    extraHits: 17, activeAbilityLevel: 18, numberOfMembers: 20,
    extraPierceMelee: 21, extraPierceRanged: 22, extraHitsMelee: 23,
    // 24 ExtraRange : la table sautait de 23 a 25, et le trou etait INVISIBLE -- un port qui
    // pose ce stat n'avait aucun moyen de l'observer. Constate le 2026-07-27 sur le volet
    // Movement/Range de RealityUnbound, livre sans mesure faute de canal.
    extraRange: 24,
    extraMaxDamage: 25, extraPierce: 26,
};

// --- UnitFlag PAR UNITÉ (O5) — mirror de `IdunBattle.Entities.UnitExtensions$$HasFlag` ---
//
// `IdunBattle.Entities.Components.UnitFlagsComponent` range ses flags dans un
// `idun.shared.collections.OrderedSet<UnitFlag>` @+0x10 (cf. son `$$.ctor`), et son `$$Has` n'y
// accède QUE par un appel d'interface FULLY-SHARED générique. La disposition interne de ce set
// n'est donc pas lisible de façon fiable depuis Frida — on ne la lit PAS. On invoque à la place la
// fonction NOMMÉE que le jeu appelle lui-même (`HasFlag(unit, flag)` : c'est littéralement la ligne
// `uVar1 = UnitExtensions.HasFlag(defender, 0x13)` d'`ApplyTraitDamageLimitsToDamage`), une fois
// par valeur d'enum. Read-only intégral.
const hasFlagMi = unitExtClass ? findMethodByParamCount(unitExtClass, "HasFlag", 2) : null;

// TRAITS RUNTIME (#233) — même raison, même remède que les flags ci-dessus. Le port
// reconstruisait les traits depuis le substrat (gameconfig + dérivation d'alliance) et depuis son
// propre leaf `AddTrait` : il ne pouvait RIEN confronter. Un trait accordé EN BATAILLE lui était
// invisible.
//
// SÉMANTIQUE, lue au décompilé de `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` —
// trois collections, et la première est un VETO :
//
//   HasTrait(t) == !retirés(+0x50).Contains(t) && ( permanents(+0x40).Contains(t)
//                                                || temporaires(+0x48).Contains(t) )
//
// `IdunBattle.Operations.AddTraitOperation$$Execute` écrit `+0x40` quand `isTemporary == 0`,
// `+0x48` sinon. ⚠ `IdunBattle.Operations.RemoveTraitOperation$$RemoveTrait` NE remplit PAS `+0x50` :
// il RETIRE de `+0x40`/`+0x48` selon le même `isTemporary`. Le retrait est donc DESTRUCTIF sur les
// ensembles additifs, pas additif sur un ensemble de veto — l'écrivain de `+0x50` reste à
// identifier (résidu nommé de #233).
//
// POURQUOI ON N'EXPOSE PAS LES TROIS COLLECTIONS SÉPARÉMENT : ce sont des
// `idun.shared.collections.OrderedSet<UnitTrait>` interrogés par appel d'interface FULLY-SHARED —
// exactement la disposition que le bloc `unitFlags` déclare non lisible de façon fiable. La lire
// « quand même » reviendrait à deviner un layout, précisément ce que la doctrine interdit. On
// invoque donc la fonction NOMMÉE que le jeu appelle lui-même, `UnitExtensions$$HasTrait(unit,
// trait)`, une fois par valeur d'enum : elle rend l'ensemble EFFECTIF, veto compris — c'est-à-dire
// ce que TOUS les gates de traits lisent réellement.
const hasTraitMi = unitExtClass ? findMethodByParamCount(unitExtClass, "HasTrait", 2) : null;

// Valeurs de `IdunBattle.Entities.Enum.UnitTrait`, LUES AU RUNTIME — même discipline que
// `unitFlagTypes` : aucune table du dépôt, une renumérotation de build se propage seule.
let unitTraitTypesCache: Record<string, number> | null = null;
function unitTraitTypes(): Record<string, number> {
    if (unitTraitTypesCache) return unitTraitTypesCache;
    const raw = dumpEnum("IdunSharedAssembly.dll", "IdunBattle.Entities.Enum", "UnitTrait") ?? {};
    const out: Record<string, number> = {};
    for (const k of Object.keys(raw)) {
        const v = parseInt(raw[k], 10);
        if (Number.isFinite(v)) out[k] = v;
    }
    unitTraitTypesCache = out;
    return out;
}

// Valeurs de `IdunBattle.Entities.Enum.UnitFlag`, LUES AU RUNTIME (`dumpEnum` — littéraux de la
// métadonnée IL2CPP), jamais recopiées dans une table du dépôt : une RENUMÉROTATION au prochain
// build se propage alors toute seule. Une constante en dur, elle, resterait syntaxiquement valide
// et deviendrait FAUSSE en silence — c'est exactement le mode de panne que le diff `enums.tsv` de
// la procédure de MAJ sert à rattraper, et qu'on préfère ne pas créer. Mémoïsé : `dumpEnum` parcourt
// les champs de la classe, inutile de le refaire à chaque unité.
let unitFlagTypesCache: Record<string, number> | null = null;
function unitFlagTypes(): Record<string, number> {
    if (unitFlagTypesCache) return unitFlagTypesCache;
    const raw = dumpEnum("IdunSharedAssembly.dll", "IdunBattle.Entities.Enum", "UnitFlag") ?? {};
    const out: Record<string, number> = {};
    for (const k of Object.keys(raw)) {
        const v = parseInt(raw[k], 10);
        if (Number.isFinite(v)) out[k] = v;
    }
    unitFlagTypesCache = out;
    return out;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function registerViewSnapshot(ctx: Ctx): void {
    /** SNAPSHOT one-shot des STATS DE COMBAT RÉSOLUES par unité (prédiction 100% offline,
     *  doc §16). Lit `UnitExtensions.GetStat(entity, StatType)` pour chaque stat combat-
     *  pertinente. C'est le SEUL accès live du prédicteur offline (à appeler une fois au
     *  chargement de la BattleConfig) ; faction/class/profil viennent de gameconfig, effets de
     *  decisionView. Les TRAITS, eux, sont publiés ICI (`units[].traits`, #233) : le gameconfig ne
     *  donne que les traits de DÉPART, et un trait accordé en bataille lui échappe.
     *  Read-only. body: { runnerId } */
    ctx.rpc.combatSnapshot = (
        body?: { runnerId?: number; debugOnly?: string[] },
    ): Promise<unknown> => queueOnMainThread(() => {
        // DIAGNOSTIC #175 — `debugOnly` restreint le snapshot aux sous-lectures NOMMÉES, pour
        // isoler laquelle empoisonne un runner contenant une Machine (toute pose d'effet
        // ultérieure y devient un no-op silencieux). Absent => comportement NORMAL, inchangé :
        // c'est un levier de mesure, pas un mode de fonctionnement.
        // On ne référence QUE les sous-lectures qui INVOQUENT du natif — `readShields` est une
        // lecture mémoire pure (aucun `invokeMethod`), elle ne peut rien muter, donc pas de bouton.
        const only: string[] | null = Array.isArray(body?.debugOnly) ? body!.debugOnly! : null;
        const wants = (part: string): boolean => only === null || only.indexOf(part) >= 0;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getStatMi) return { ok: false, error: "UnitExtensions.GetStat(4) non résolu" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };

        const STAT_IDS = COMBAT_STAT_IDS;
        const idBufs: Record<string, NativePointer> = {};
        for (const k of Object.keys(STAT_IDS)) {
            const buf = Memory.alloc(4); buf.writeS32(STAT_IDS[k]); idBufs[k] = buf;
        }
        const partBuf = Memory.alloc(4); partBuf.writeS32(0);        // StatPart.Current
        const partBufInit = Memory.alloc(4); partBufInit.writeS32(3); // StatPart.Initial (=base)
        const partBufMax = Memory.alloc(4); partBufMax.writeS32(2);  // StatPart 2 = MAX agrégé (#45b')
        // Nullable<BEntityId> = null (HasValue=false) : struct zéroé (taille large par sûreté).
        const nullId = Memory.alloc(16); for (let i = 0; i < 16; i += 4) nullId.add(i).writeS32(0);
        const getStatP = (e: NativePointer, k: string, pb: NativePointer): number | null => {
            try {
                const r = invokeMethod(getStatMi!.info, null, [e, idBufs[k], pb, nullId]);
                return r.isNull() ? null : r.add(0x10).readS32();
            } catch { return null; }
        };
        const getStat = (e: NativePointer, k: string): number | null => getStatP(e, k, partBuf);

        // DÉGÂT D'ARME de l'attaque normale (one-shot) : le dégât/hits ne sont PAS des StatType
        // unité (la stat Attack agrégée ≠ dégât d'arme résolu). On capture la PRÉDICTION native
        // de l'attaque normale par paire via `CachedDamagePredictionQuery.GetNormalAttackPrediction
        // (attacker, target, attackerPosition)` (slot 13) — contrairement à `GetAllPredictions`,
        // CE chemin ne filtre PAS par portée (cible explicite) → capturable à froid au déploiement.
        // Le dégât de BASE est indépendant de la cible (cf. mesures) sauf effets de réduction sur la
        // cible → on prend le MAX sur plusieurs cibles ennemies = base NON réduite.
        //   UnitPosition (dump.cs @385083) = struct 8o {IList Tiles} ; obtenue via
        //   UnitExtensions.GetUnitPosition(unit, state). DamagePredictionResult : AccurateHealthDamage
        //   Min@0x60/Max@0x64 ; TotalDamage Min@0x90/Max@0x94 ; AppliedHits@0xBC ; MightCrit@0xB1.
        const dpq = resolveDpq(runner);
        const getNormPredMi = dpq.isNull() ? null
            : findMethodByParamCount(dpq.readPointer(), "GetNormalAttackPrediction", 3);
        const getUnitPosMi = entityExtClass
            ? findMethodByParamCount(entityExtClass, "GetUnitPosition", 2) : null;
        // Toutes les entités COMBATTANTES vivantes (cibles de référence pour la
        // prédiction ET lignes du snapshot). Machine INCLUSE (#93) : les MoW
        // portent des stats et se font attaquer comme les squads, mais elles
        // étaient absentes du snapshot — leur prédiction offline n'avait donc
        // aucune stat résolue à confronter.
        const allUnits: Array<{ e: NativePointer; id: number; entityType: number }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
            if (!invokeBool(isAliveMi, [e, statePtr])) return;
            allUnits.push({ e, id, entityType: ty });
        });
        // DÉGÂT DE BASE de l'attaque normale (one-shot, iso-AI) via `GetNormalAttackPrediction
        // (attacker, target, pos)`. Ce chemin calcule pour les cibles ATTEIGNABLES (0 sinon) ; au
        // déploiement seuls les alliés sont adjacents → ils donnent la base (le dégât de base EST
        // indépendant de la cible, cf. mesures, sauf armes Blast/multi-membres). On retient donc
        // la meilleure entrée NON NULLE = dégât de base d'arme. Les réductions par cible sont
        // appliquées offline (decisionView.effects) ; le détail par cible (Blast) = amélioration.
        const readNormalAttack = (attacker: NativePointer): Record<string, unknown> => {
            if (dpq.isNull()) return { error: "dpq null" };
            if (!getNormPredMi) return { error: "GetNormalAttackPrediction(3) non résolu sur "
                + s(class_get_name(dpq.readPointer()) as NativePointer) };
            if (!getUnitPosMi) return { error: "GetUnitPosition(2) non résolu" };
            let posPtr: NativePointer;
            try {
                const pos = invokeMethod(getUnitPosMi.info, null, [attacker, statePtr]);
                if (pos.isNull()) return { error: "GetUnitPosition null" };
                posPtr = pos.add(0x10);                              // struct UnitPosition (8o)
            } catch (err) { return { error: "GetUnitPosition: " + (err as Error).message }; }
            let best: Record<string, unknown> | null = null;
            let reachable = 0;
            for (const t of allUnits) {
                if (t.e.equals(attacker)) continue;
                // #175 — NE JAMAIS prédire contre une MACHINE. Un seul appel
                // `GetNormalAttackPrediction(attaquant, cible = Machine, pos)` suffit à rendre
                // TOUTE pose d'effet ultérieure sur CE runner un no-op SILENCIEUX (l'action est
                // consommée, `applyAction` rend ok=true, le dégât passe, mais `AddEffect` n'écrit
                // plus rien). La sortie muette est le gate d'immunité de
                // `IdunBattle.Operations.AddEffectOperation$$Execute` — l'appel d'interface slot
                // +0x28 sur la définition d'effet : c'est sa SEULE sortie qui ne logue pas, les
                // deux autres (cible nulle, `UnitExtensions$$HasFlag(cible, 6)`) tracent.
                //
                // BISSECTÉ live (`probe_175_combatsnapshot_machine.py`), pas supposé — et ça a
                // RÉFUTÉ le correctif que la fiche #175 proposait. Mesures :
                //   readNormalAttack SEULE                  -> NO-OP  (suffit à empoisonner)
                //   les 5 autres sous-lectures, chacune     -> POSE
                //   GetUnitPosition seul, sans prédiction   -> POSE
                //   MoW exclue comme ATTAQUANTE (le fix proposé) -> NO-OP  <- INERTE
                //   MoW exclue comme CIBLE (ci-dessous)     -> POSE
                // Le vecteur est donc la Machine en CIBLE, pas en attaquant : gater sur
                // l'attaquant aurait livré un correctif qui ne corrige rien, sans rien signaler.
                //
                // Ce qu'on perd : rien. Le dégât de base d'arme est indépendant de la cible (cf.
                // le commentaire de tête), et l'attaquant garde toutes les cibles UNIT. Ce qu'on
                // ne sait pas encore : POURQUOI le natif se comporte ainsi (le prédicteur cache
                // délègue, cf. `CachedDamagePredictionQuery$$GetNormalAttackPrediction`) — c'est
                // un CONTOURNEMENT mesuré, pas une réparation du natif.
                if (t.entityType === EntityType.Machine) continue;
                let boxed: NativePointer;
                try { boxed = invokeMethod(getNormPredMi.info, dpq, [attacker, t.e, posPtr]); }
                catch { continue; }
                if (boxed.isNull()) continue;
                const b = boxed.add(0x10);
                const hMax = b.add(0x64).readS32();
                if (hMax <= 0) continue;                             // cible non atteignable → 0
                reachable++;
                if (best === null || hMax > (best.maxDmg as number)) {
                    best = {
                        minDmg: b.add(0x60).readS32(), maxDmg: hMax,
                        hits: b.add(0xbc).readS32(), mightCrit: b.add(0xb1).readU8(),
                        vsTarget: t.id,
                    };
                }
            }
            if (best) { best.reachable = reachable; return best; }
            return { error: "aucune cible atteignable au déploiement (base non capturable)" };
        };

        // --- multiplier d'ability-variable PAR ENTITÉ (UnitConfiguration via BattleQuery.GetUnitConfig) ---
        // `AbilityVariablesMultiplierPercentage` (UnitConfiguration@0x74, dérivé progression) scale les
        // variables d'ability « rareté » (ex. PowerTrip.armorIgnored §17.21). PAS porté sur l'entité ; on
        // remonte via le registre `BattleQuery.GetUnitConfig(unitId)` (EntityServices.<Battle>@battleInServices).
        // Clé = la VisualId (string managée) de l'unité (UnitComponent.VisualId@0x20 ; Id==VisualId). Offsets
        // UnitConfiguration (dump gqfc5mff6c) : mult@0x74, tertiaryMult@0x78, Level@0x7C, ActiveAbilityLevel
        // @0xB8, PassiveAbilityLevel@0xBC (struct Level = int). Per-entité (≠ BC offline par visualId).
        const battleQ = (servicesOff >= 0 && battleInServicesOff >= 0)
            ? (() => {
                const sv = runner.add(servicesOff).readPointer();
                return sv.isNull() ? ptr(0) : sv.add(battleInServicesOff).readPointer();
            })() : ptr(0);
        const getUnitConfigMi = (!battleQ.isNull())
            ? findMethodByParamCount(battleQ.readPointer(), "GetUnitConfig", 1) : null;
        const unitCompClass = findClassAnywhere("IdunBattle.Entities.Components", "UnitComponent");
        const VISUALID_OFF = 0x20;     // (Base)UnitComponent.VisualId (System.String)
        const UCFG = { mult: 0x74, tertMult: 0x78, level: 0x7c, activeLvl: 0xb8, passiveLvl: 0xbc };
        const readUnitConfig = (e: NativePointer): Record<string, unknown> => {
            if (!getUnitConfigMi) return { error: "GetUnitConfig(1) non résolu" };
            if (!unitCompClass) return { error: "UnitComponent non résolu" };
            let vidPtr: NativePointer | null = null;
            forEachComponent(e, (comp, klass) => {
                if (vidPtr === null && klass.equals(unitCompClass)) {
                    const p = comp.add(VISUALID_OFF).readPointer();
                    if (!p.isNull()) vidPtr = p;
                }
            });
            if (!vidPtr) return { error: "visualId introuvable" };
            let cfg: NativePointer;
            try { cfg = invokeMethod(getUnitConfigMi.info, battleQ, [vidPtr]); }
            catch (err) { return { error: "GetUnitConfig: " + (err as Error).message }; }
            if (cfg.isNull()) return { error: "config null" };
            return {
                visualId: readIl2cppString(vidPtr),
                abilityVariablesMultiplier: cfg.add(UCFG.mult).readS32(),
                tertiaryAbilityVariablesMultiplier: cfg.add(UCFG.tertMult).readS32(),
                level: cfg.add(UCFG.level).readS32(),
                activeAbilityLevel: cfg.add(UCFG.activeLvl).readS32(),
                passiveAbilityLevel: cfg.add(UCFG.passiveLvl).readS32(),
            };
        };

        // BOUCLIERS (ShieldComponent @180fa8770) : liste d'instances @+0x10 (List<ShieldInstance>,
        // _items@+0x10/_size@+0x18 ; éléments = pointeurs, data array @+0x20). ShieldInstance :
        // id@+0x10, amount@+0x30, remaining Nullable<int>@+0x3c (None=permanent). Layout du Nullable
        // incertain → on émet remainingRaw=[s32@0x3c, s32@0x40] pour trancher en validation, + une
        // estimation `remaining` (convention .NET {hasValue@0, value@4} : has=byte@0x3c, val=s32@0x40).
        const shieldCompClass = findClassAnywhere("IdunBattle.Entities.Components", "ShieldComponent");
        const SH = { id: 0x10, amount: 0x30, rem0: 0x3c, rem1: 0x40 };
        const readShields = (e: NativePointer): Array<Record<string, unknown>> => {
            if (!shieldCompClass) return [];
            let comp: NativePointer | null = null;
            forEachComponent(e, (c, klass) => {
                if (comp === null && klass.equals(shieldCompClass)) comp = c;
            });
            if (comp === null) return [];
            const list = (comp as NativePointer).add(0x10).readPointer();
            if (list.isNull()) return [];
            const items = list.add(0x10).readPointer();
            const size = list.add(0x18).readS32();
            if (items.isNull() || size <= 0 || size > 64) return [];
            const out: Array<Record<string, unknown>> = [];
            for (let i = 0; i < size; i++) {
                const inst = items.add(0x20 + i * 8).readPointer();
                if (inst.isNull()) continue;
                const w0 = inst.add(SH.rem0).readS32();
                const w1 = inst.add(SH.rem1).readS32();
                const has = inst.add(SH.rem0).readU8();   // convention .NET hasValue@+0
                out.push({
                    id: inst.add(SH.id).readS32(),
                    amount: inst.add(SH.amount).readS32(),
                    remaining: has ? w1 : null,
                    remainingRaw: [w0, w1],
                });
            }
            return out;
        };

        // ÉTAT DE TOUR PAR UNITÉ (#223) — deux champs de `UnitComponent` qu'AUCUN RPC n'exposait,
        // et dont l'absence forçait DEUX mécaniques à se valider par contournement :
        //
        //  * `currentTurnStartTile` @+0x18c (`int`, id de TUILE ; 0 = aucune). ÉCRIT par
        //    `IdunBattle.Operations.StartTurnOperation$$Execute`, juste après le bump de
        //    `turnsStarted@+0x58`, sur le MÊME composant :
        //    `mainTile = EntityExtensions.GetMainTile(unit) ; comp[0x18c] = mainTile?.Id ?? 0`.
        //    C'est la tuile où l'unité se trouvait au DÉBUT DE SON PROPRE TOUR — surtout PAS
        //    « the hex he moved from » comme l'annonce le texte i2, qui MENT : une unité qui bouge
        //    deux fois dans le tour garde la tuile du début. RELU par
        //    `IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select`, qui rend une
        //    liste VIDE quand le champ vaut 0 -> on émet `null` (le port le représente par `None`).
        //    Sans lui, un `load_state` frais partait à `None` et le time-ghost de `thousTerminator`
        //    (`GhostRevive`/`TimeFlux_Revive`) ne se posait qu'après un `StartTurnOperation`.
        //
        //  * `chargedUnitIds` @+0x190 (`List<int>`). Second conjoint de
        //    `IdunBattle.Core.Services.BattleQuery$$IsCharging` =
        //    `AreEntitiesAdjacent(caster, target) && ChargedUnitIds.Contains(target.Id)`.
        //    Le décompilé lit `*(longlong *)(comp + 400)` — 400 décimal = 0x190 — puis
        //    `List<T>$$Contains` : c'est donc bien une LISTE, pas un `OrderedSet` (contrairement
        //    à `UnitFlagsComponent`, dont la disposition interne n'est PAS lisible et qu'on
        //    interroge par invocation). Sa disposition l'est : `_items`@+0x10, `_size`@+0x18,
        //    données du tableau @+0x20, éléments de 4 octets.
        //    Sans lui, `load_state` ne pouvait pas seeder l'état de charge : la face PRÉDICTION
        //    sur état rechargé restait restrictive, et `test_avalanche_of_muscle_live` avait dû
        //    être supprimé faute de pouvoir exprimer le prédicat (il déclarait la charge via le
        //    proxy `set_moved_flag`, que `964dd15` a cessé d'honorer).
        //
        // Lecture MÉMOIRE PURE (aucun `invokeMethod`) : comme `readShields`, elle ne peut rien
        // muter, donc pas de bouton `debugOnly`. Un seul parcours de composants pour les DEUX
        // champs. `null` = non mesuré (composant/classe introuvable), à distinguer de `0`/`[]`
        // = mesuré et vide.
        const UTS = { startTile: 0x18c, charged: 0x190 };
        const readUnitTurnState = (e: NativePointer): Record<string, unknown> => {
            if (!unitCompClass) return { currentTurnStartTile: null, chargedUnitIds: null };
            let comp: NativePointer | null = null;
            forEachComponent(e, (c, klass) => {
                if (comp === null && klass.equals(unitCompClass)) comp = c;
            });
            if (comp === null) return { currentTurnStartTile: null, chargedUnitIds: null };
            const c = comp as NativePointer;
            const startTile = c.add(UTS.startTile).readS32();
            const charged: number[] = [];
            const list = c.add(UTS.charged).readPointer();
            if (!list.isNull()) {
                const items = list.add(0x10).readPointer();
                const size = list.add(0x18).readS32();
                if (!items.isNull() && size > 0 && size <= 64) {
                    for (let i = 0; i < size; i++) charged.push(items.add(0x20 + i * 4).readS32());
                }
            }
            // 0 = « aucune tuile » côté natif (le sélecteur rend alors une liste vide) -> `null`,
            // pour que le port ne confonde pas avec la tuile d'id 0.
            return { currentTurnStartTile: startTile === 0 ? null : startTile,
                     chargedUnitIds: charged };
        };

        // FLAGS de l'unité (O5) : ids de `UnitFlag` actuellement POSÉS, par invocation de
        // `HasFlag(unit, flag)` sur chaque valeur d'enum. Valeurs DÉDUPLIQUÉES (un enum C# admet
        // des alias de même valeur ; deux noms ne font qu'un seul flag).
        //
        // `null` (et non `[]`) quand la mesure n'a PAS pu se faire — méthode irrésolue ou enum vide.
        // La distinction est le tout du canal : `[]` dit « lu, aucun flag posé », `null` dit « pas
        // lu ». Les rabattre l'un sur l'autre ferait passer un capteur MORT pour une unité sans
        // flags, et le consommateur offline retomberait silencieusement sur un défaut au lieu de
        // garder sa dérivation de repli (même discipline que `invokeInt`, cf. `internals.ts`).
        const flagTypes = wants("unitFlags") ? unitFlagTypes() : {};
        const flagValues = Array.from(new Set(Object.keys(flagTypes).map((k) => flagTypes[k])))
            .sort((a, b) => a - b);
        const flagBuf = Memory.alloc(4);
        const readUnitFlags = (e: NativePointer): number[] | null => {
            if (!hasFlagMi || flagValues.length === 0) return null;
            const out: number[] = [];
            for (const v of flagValues) {
                flagBuf.writeS32(v);
                if (invokeBool(hasFlagMi, [e, flagBuf])) out.push(v);
            }
            return out;
        };

        // TRAITS EFFECTIFS (#233) : ids `UnitTrait` que le natif considère POSÉS, veto `+0x50`
        // compris. Même forme que `readUnitFlags` — valeurs DÉDUPLIQUÉES (un enum C# admet des
        // alias), et `null` (jamais `[]`) quand la mesure n'a pas pu se faire : `[]` dit « lu,
        // aucun trait », `null` dit « pas lu ». Les confondre ferait passer un capteur MORT pour
        // une unité sans trait, et le consommateur offline retomberait en silence sur sa
        // dérivation de repli au lieu de savoir qu'il n'a rien mesuré.
        const traitTypes = wants("traits") ? unitTraitTypes() : {};
        const traitValues = Array.from(new Set(Object.keys(traitTypes).map((k) => traitTypes[k])))
            .sort((a, b) => a - b);
        const traitBuf = Memory.alloc(4);
        const readUnitTraits = (e: NativePointer): number[] | null => {
            if (!hasTraitMi || traitValues.length === 0) return null;
            const out: number[] = [];
            for (const v of traitValues) {
                traitBuf.writeS32(v);
                if (invokeBool(hasTraitMi, [e, traitBuf])) out.push(v);
            }
            return out;
        };

        const units: Array<Record<string, unknown>> = [];
        for (const { e, id, entityType } of allUnits) {
            const stats: Record<string, number | null> = {};
            // AXE STAT-MODIFICATION (§7bis prediction.md) : delta Current-Initial par StatType.
            // `CalculateModifiersFromStatModifications` @181004380 ne s'active QUE si CurrentValue !=
            // BaseValue → un delta non-nul = présence de modifications de stat (source des modifiers de
            // dégât par-cible non exposés comme effets nommés, ex. le +50% sur worldTerminator). Emis
            // pour NOMMER le modifier par capture (INPUT), pas pour deviner.
            const statDelta: Record<string, number> = {};
            if (wants("stats")) {
                for (const k of Object.keys(STAT_IDS)) {
                    stats[k] = getStat(e, k);
                    const init = getStatP(e, k, partBufInit);
                    if (init !== null && stats[k] !== null && stats[k] !== init) {
                        statDelta[k] = (stats[k] as number) - init;
                    }
                }
            }
            // #45b' : MaxHealth EFFECTIF (StatPart=2 = agrégat base+modifications, clamp cape
            // inclus) — la lecture EXACTE de `DamageUtility.<EvaluateAttackInSteps>d__2
            // @1810e2280` : `GetStat(target, Health=5, 2, null)` pour combinedMax. Le champ
            // struct MaximumValue@0x14 (observeBattle.hpMax) est la BASE : il rate les bumps
            // mid-bataille (TwistedScience +2992 sur u87, 777 s15 — utilité native 2.8836
            // reconstruite exacte avec 14036). DYNAMIQUE -> refresh par pas côté Python.
            const healthMax = wants("stats") ? getStatP(e, "health", partBufMax) : null;
            // AbilityState PER-ABILITY (#100) : {level, multiplier} de chaque entrée ActiveAbility
            // (_abilityState @0x4c, Override @0x58 prime — cf. internals.readAbilityState). C'est le
            // couple que le natif passe au playbook (5e arg MakeDamagePredictions) et qui indexe les
            // variables config (TryGetVariableArrayForLevel @181577510) — le global unitConfig
            // (activeAbilityLevel×abilityVariablesMultiplier) est un AUTRE canal (u80 : 65×120 vs 50×180).
            const abilityStates = wants("abilityStates")
                ? unitAbilityTypes(e, true)
                    .filter((a) => a.level !== undefined)
                    .map((a) => ({ id: a.id, name: a.name, kind: a.kind,
                        level: a.level, multiplier: a.multiplier }))
                : [];
            units.push({
                entityId: id, entityType,
                ctrl: wants("ctrl") ? invokeBool(isCtrlByCurMi, [e, statePtr]) : null,
                // #N11 : compteur PER-UNITÉ de tours termines (`UnitExtensions.GetTurnsFinished`),
                // lu par le gate `OwnerHasFinishedMinTurns`. `null` = non mesuré (methode
                // irresolue), a distinguer de `0` = a fini zero tour.
                turnsFinished: wants("turnsFinished")
                    ? invokeInt(getTurnsFinishedMi, [e]) : null,
                stats, statDelta, healthMax,
                // O5 : `UnitFlagsComponent` de l'unité, projeté en ids `UnitFlag` posés. Sans lui,
                // la face DÉCISION offline n'avait AUCUN accès live aux flags (`PreventOverkill`
                // =19, `Moved` =0, `Untargetable` =17, `DisableTriggers` =18…) et devait les
                // DÉRIVER de leurs effets poseurs. `null` = non mesuré, `[]` = mesuré sans flag.
                unitFlags: wants("unitFlags") ? readUnitFlags(e) : null,
                // #233 : traits REELLEMENT portes en bataille (gameconfig + AddTrait + veto de
                // retrait), la ou le port ne savait que les RECONSTRUIRE depuis le substrat.
                // C'est ce que lisent les 33 gates de traits recenses.
                traits: wants("traits") ? readUnitTraits(e) : null,
                normalAttack: wants("normalAttack") ? readNormalAttack(e) : null,
                unitConfig: wants("unitConfig") ? readUnitConfig(e) : null,
                shields: readShields(e), abilityStates,
                // #223 : `currentTurnStartTile` + `chargedUnitIds` (cf. le bloc `readUnitTurnState`).
                ...readUnitTurnState(e),
            });
        }
        // `unitFlagTypes` = {nom: id} de l'enum, au MÊME titre que `statTypes` : le consommateur
        // nomme les ids qu'il lit sans recopier de table chez lui.
        return { ok: true, runner: label, statTypes: STAT_IDS,
            unitFlagTypes: wants("unitFlags") ? flagTypes : null, units };
    });

    /** PER-SOURCE STAT-MODIFICATION breakdown — la sonde DÉFINITIVE pour SOURCER un
     *  `statDelta` opaque : « le +1298 Attack sur u92 vient de QUELLE entité ? »
     *  devient une LECTURE au lieu d'une triangulation (base↔tuile + recon allié +
     *  gameconfig). Chemin natif VÉRIFIÉ (décompilé) :
     *    `UnitExtensions.GetStat(entity, statType, StatPart=5, Nullable<BEntityId> src)`
     *    → `StatComponent.GetStatPart @180fa8bb0` case 5/9 :
     *        • src.HasValue=false → `*(int*)(comp+0x10)` = TOTAL Σ des modifications
     *        • src.HasValue=true  → `ValueModification.GetModificationFromEntity(
     *            comp+0x10, srcId) @180fadf10` → Dict<BEntityId,Modifier> keyé par
     *          l'ENTITÉ SOURCE du buff → contribution de CETTE source.
     *  On lit le total (part 5, src null) par stat ; si non-nul, on SCANNE toutes les
     *  entités comme sources candidates (BEntityId = `forEachEntity` id) et on garde
     *  les contributions non-nulles. `residual = total - Σ(sources)` : 0 = tout
     *  attribué à des entités (cas aura d'allié / self-buff) ; non-nul = une source
     *  non-entité (modif SETUP `ModifyUnit*` / système) → à investiguer, pas deviner.
     *  Ne matérialise QUE ce qui est présent dans la ValueModification À CET INSTANT
     *  (une aura d'adjacence n'y est que si l'unité est actuellement adjacente au
     *  porteur — cf. #49 : re-évaluée par candidat en prédiction). Read-only, one-shot.
     *  body: { runnerId?, unitId?, stats?: string[], minAbs?=1 } */
    ctx.rpc.statModSources = (
        body?: {
            runnerId?: number; unitId?: number; stats?: string[]; minAbs?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getStatMi) return { ok: false, error: "UnitExtensions.GetStat(4) non résolu" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };

        const requested = (Array.isArray(body?.stats) && body!.stats!.length)
            ? body!.stats!.filter((k) => k in COMBAT_STAT_IDS)
            : Object.keys(COMBAT_STAT_IDS);
        const minAbs = typeof body?.minAbs === "number"
            ? Math.abs(body.minAbs) : 1;

        const idBufs: Record<string, NativePointer> = {};
        for (const k of requested) {
            const buf = Memory.alloc(4); buf.writeS32(COMBAT_STAT_IDS[k]); idBufs[k] = buf;
        }
        const partBuf5 = Memory.alloc(4); partBuf5.writeS32(5);   // StatPart = branche modification
        // Nullable<BEntityId> — layout Mono : hasValue byte @+0, value(int32 BEntityId) @+4.
        const nullSrc = Memory.alloc(16); for (let i = 0; i < 16; i += 4) nullSrc.add(i).writeS32(0);
        const srcBuf = Memory.alloc(16); for (let i = 0; i < 16; i += 4) srcBuf.add(i).writeS32(0);
        srcBuf.writeU8(1);   // HasValue = true (réécrit srcBuf+4 = value à chaque source)
        // GetStat(4-arg) rend un int BOXÉ → valeur signée @+0x10 (idem combatSnapshot).
        const getMod = (e: NativePointer, k: string, src: NativePointer): number => {
            try {
                const r = invokeMethod(getStatMi!.info, null, [e, idBufs[k], partBuf5, src]);
                return r.isNull() ? 0 : r.add(0x10).readS32();
            } catch { return 0; }
        };

        // Toutes les entités = sources candidates ; entités COMBATTANTES vivantes
        // (filtrées par unitId) = cibles. Machine INCLUSE (#93) : une MoW porte
        // des ValueModification comme une squad — sans elle, un statDelta de MoW
        // restait insourçable.
        const allEntities: Array<{ e: NativePointer; id: number; isUnit: boolean }> = [];
        const targetUnits: Array<{ e: NativePointer; id: number; entityType: number }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            const isUnit = ty === EntityType.Unit;
            allEntities.push({ e, id, isUnit });
            const isCombatant = isUnit || ty === EntityType.Machine;
            if (isCombatant && (body?.unitId === undefined || id === body.unitId)
                && invokeBool(isAliveMi, [e, statePtr])) {
                targetUnits.push({ e, id, entityType: ty });
            }
        });

        const units: Array<Record<string, unknown>> = [];
        for (const { e, id, entityType } of targetUnits) {
            const mods: Record<string, unknown> = {};
            for (const k of requested) {
                const total = getMod(e, k, nullSrc);
                if (Math.abs(total) < minAbs) continue;          // pas de modification → skip le scan
                const bySource: Array<Record<string, unknown>> = [];
                for (const src of allEntities) {
                    srcBuf.add(4).writeS32(src.id);              // value = BEntityId de la source
                    const amount = getMod(e, k, srcBuf);
                    if (amount !== 0) {
                        bySource.push({
                            source: src.id, amount,
                            self: src.id === id, sourceIsUnit: src.isUnit,
                        });
                    }
                }
                const attributed = bySource.reduce(
                    (a, b) => a + (b.amount as number), 0);
                mods[k] = { total, residual: total - attributed, bySource };
            }
            units.push({
                entityId: id, entityType,
                ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]), mods,
            });
        }
        return { ok: true, runner: label, statTypes: COMBAT_STAT_IDS, units };
    });

    /** ABILITY-STATE BAKÉ des entités-effets (#68/#75) — lit, par effet, le struct
     *  `EffectComponent.AbilityStateReference` (@0x18) : {Owner, AbilityType, Nullable<AbilityState
     *  {Level, VariableMultiplierPercentage}>}. C'est CE state que `BaseEffect.GetAbilityState
     *  @180f11780` expose aux nœuds `ConfigVar` du bonus combat (`CreateEffectDamageBonusForAttack
     *  @180f6bee0`) — la mesure DIRECTE du multiplier combat d'un additif d'effet (SmashaEad :
     *  attendu ≠ 180 pour expliquer +300 vs prédiction 599). Read-only, one-shot, aucun Interceptor.
     *  body: { runnerId?, effectType? } */
    ctx.rpc.effectAbilityStates = (
        body?: { runnerId?: number; effectType?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const effects: Array<Record<string, unknown>> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Effect) return;
            const info = readEffectAbilityStateRaw(e);
            if (info === null) return;
            if (typeof body?.effectType === "number"
                && info.effectType !== body.effectType) return;
            effects.push({ effectId: id, ...info });
        });
        return { ok: true, runner: label, effects };
    });

    /** ABILITY-STATE des INSTANCES d'ability par unité (#68/#75) — dump brut des
     *  `ActiveAbility` (ActiveAbilityComponent.Abilities@0x20, dump gqfc5mff6c TypeDefIndex
     *  11390 : AbilityName@0x44, _abilityState{Level@0x4C, VariableMultiplierPercentage@0x50,
     *  Counter@0x54}, OverrideAbilityState(Nullable)@0x58) et des `TriggeredAbility`
     *  (TriggeredAbilityComponent+0x18, instance : Level{level@0x20, mult@0x24}, +0x28).
     *  Résolution du state combat d'un effet triggered-sourced (`UnitExtensions.GetAbilityState
     *  @180eced70` : mapping statique triggered→active `GetActiveAbilityUsedForConfig @1815808e0`
     *  PUIS `ActiveAbility.get_AbilityState @180f8fc40` = override ?? _abilityState).
     *  Read-only, one-shot. body: { runnerId?, unitId? } */
    ctx.rpc.unitAbilityStates = (
        body?: { runnerId?: number; unitId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const aacClass = findClassAnywhere("IdunBattle.Entities.Components", "ActiveAbilityComponent");
        const tacClass = findClassAnywhere("IdunBattle.Entities.Components", "TriggeredAbilityComponent");
        const aaClass = findClassAnywhere("IdunBattle.Entities.Components", "ActiveAbility");
        if (!aacClass) return { ok: false, error: "ActiveAbilityComponent non résolu" };
        const AAC_ABILITIES = getFieldOffset(aacClass, "Abilities") || 0x20;
        const AA = {
            name: aaClass ? (getFieldOffset(aaClass, "AbilityName") || 0x44) : 0x44,
            state: aaClass ? (getFieldOffset(aaClass, "_abilityState") || 0x4c) : 0x4c,
            override: aaClass ? (getFieldOffset(aaClass, "OverrideAbilityState") || 0x58) : 0x58,
        };
        // KeyedCollection/Collection<T> : IList items @0x10 → List {items@0x10, size@0x18, éléments
        // ref 8 o dès 0x20} (même walk que statModSources SH / MAJ 11 dumpTriggeredMult, validé).
        const readInstList = (collection: NativePointer): NativePointer[] => {
            const out: NativePointer[] = [];
            try {
                const list = collection.add(0x10).readPointer();
                if (list.isNull()) return out;
                const items = list.add(0x10).readPointer();
                const size = list.add(0x18).readS32();
                if (items.isNull() || size <= 0 || size > 64) return out;
                for (let i = 0; i < size; i++) {
                    const inst = items.add(0x20 + i * 8).readPointer();
                    if (!inst.isNull()) out.push(inst);
                }
            } catch { /* walk partiel */ }
            return out;
        };
        const units: Array<Record<string, unknown>> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
            if (body?.unitId !== undefined && id !== body.unitId) return;
            const actives: Array<Record<string, unknown>> = [];
            const triggered: Array<Record<string, unknown>> = [];
            forEachComponent(e, (comp, klass) => {
                if (aacClass && klass.equals(aacClass)) {
                    try {
                        const coll = comp.add(AAC_ABILITIES).readPointer();
                        if (!coll.isNull()) {
                            for (const inst of readInstList(coll)) {
                                const ov: number[] = [];
                                for (let i = 0; i < 4; i++) {
                                    try { ov.push(inst.add(AA.override + i * 4).readS32()); }
                                    catch { break; }
                                }
                                actives.push({
                                    type: inst.add(AA.name).readS32(),
                                    level: inst.add(AA.state).readS32(),
                                    mult: inst.add(AA.state + 4).readS32(),
                                    counter: inst.add(AA.state + 8).readS32(),
                                    overrideRaw: ov,
                                });
                            }
                        }
                    } catch { /* composant illisible */ }
                }
                if (tacClass && klass.equals(tacClass)) {
                    try {
                        const coll = comp.add(0x18).readPointer();
                        if (!coll.isNull()) {
                            for (const inst of readInstList(coll)) {
                                const raw: number[] = [];
                                for (let i = 0; i < 12; i++) {
                                    try { raw.push(inst.add(0x10 + i * 4).readS32()); }
                                    catch { break; }
                                }
                                triggered.push({
                                    level: inst.add(0x20).readS32(),
                                    mult: inst.add(0x24).readS32(),
                                    raw,
                                });
                            }
                        }
                    } catch { /* composant illisible */ }
                }
            });
            if (actives.length || triggered.length) {
                units.push({ entityId: id, actives, triggered });
            }
        });
        return { ok: true, runner: label, units };
    });

    /** PROBE de la config d'ability RÉELLEMENT enregistrée côté battle (#68/#75) —
     *  invoque `AbilitiesDatabase.GetConfig(<kind> id)` (registre du runner, via
     *  `EntityServices.<Abilities>@0x40`) puis `AbilityConfiguration.GetVariableForLevel
     *  @181576fb0` (varType, AbilityState{level,mult,counter}, dontThrow) sur une grille
     *  (level, mult) → la VALEUR exacte que le combat résout (formule native
     *  `round_fix64(table[level-1] x mult/100)` si var rarity-flaggée, cf.
     *  `TryGetVariableArrayForLevel @181577510`). Dump aussi la liste rarity-flag
     *  (config+0x28) + la klass concrète du config. Read-only (invokes purs).
     *  body: { runnerId?, id, kind: "triggered"|"active", varType?=8, grid?=[[lvl,mult],…] } */
    ctx.rpc.abilityConfigProbe = (
        body?: {
            runnerId?: number; id?: number; kind?: string; varType?: number;
            grid?: Array<[number, number]>;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.id !== "number") return { ok: false, error: "id requis" };
        let runner: NativePointer;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
        } else if (state.liveRunner) {
            runner = state.liveRunner;
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (servicesOff < 0) return { ok: false, error: "servicesOff non résolu" };
        const services = runner.add(servicesOff).readPointer();
        if (services.isNull()) return { ok: false, error: "services null" };
        const abilitiesOff = entityServicesClass
            ? (getFieldOffset(entityServicesClass, "<Abilities>k__BackingField") || 0x40) : 0x40;
        const db = services.add(abilitiesOff).readPointer();
        if (db.isNull()) return { ok: false, error: "AbilitiesDatabase null" };
        const dbKlass = db.readPointer();
        const paramClass = body.kind === "active" ? "ActiveAbilityType" : "TriggeredAbilityType";
        const getConfigMi = findMethodByParamClasses(dbKlass, "GetConfig", [paramClass]);
        if (!getConfigMi) return { ok: false, error: `GetConfig(${paramClass}) non résolu` };
        const idBuf = Memory.alloc(4); idBuf.writeS32(body.id);
        let cfg: NativePointer;
        try { cfg = invokeMethod(getConfigMi.info, db, [idBuf]); }
        catch (e) { return { ok: false, error: "GetConfig: " + (e as Error).message }; }
        if (cfg.isNull()) return { ok: false, error: "config null" };
        const cfgKlass = cfg.readPointer();
        const cfgClassName = s(class_get_name(cfgKlass) as NativePointer);
        // GetVariableForLevel(AbilityVariableType, AbilityState, bool) — 3 params.
        const gvflMi = findMethodByParamCount(cfgKlass, "GetVariableForLevel", 3);
        if (!gvflMi) return { ok: false, error: "GetVariableForLevel(3) non résolu", cfgClassName };
        const varType = typeof body.varType === "number" ? body.varType : 8; // extraDmg=8
        const varBuf = Memory.alloc(4); varBuf.writeS32(varType);
        const noThrow = Memory.alloc(4); noThrow.writeU8(1);
        const stateBuf = Memory.alloc(12);
        const grid: Array<[number, number]> = (body.grid && body.grid.length)
            ? body.grid
            : [[50, 180], [50, 100], [50, 90], [49, 180], [65, 100], [64, 100], [1, 180]];
        const values: Array<Record<string, unknown>> = [];
        for (const [lvl, mult] of grid) {
            stateBuf.writeS32(lvl); stateBuf.add(4).writeS32(mult); stateBuf.add(8).writeS32(0);
            let v: number | null = null; let err: string | null = null;
            try {
                const r = invokeMethod(gvflMi.info, cfg, [varBuf, stateBuf, noThrow]);
                v = r.isNull() ? null : r.add(0x10).readS32();
            } catch (e) { err = (e as Error).message; }
            values.push({ level: lvl, mult, value: v, ...(err ? { err } : {}) });
        }
        // Liste rarity-flag (`_variablesAffectedByRarityBonus`, config+0x28 d'après
        // TryGetVariableArrayForLevel @181577510) : List<AbilityVariableType> (ints).
        const rarityFlagged: number[] = [];
        try {
            const list = cfg.add(0x28).readPointer();
            if (!list.isNull()) {
                const items = list.add(0x10).readPointer();
                const size = list.add(0x18).readS32();
                if (!items.isNull() && size > 0 && size <= 64) {
                    for (let i = 0; i < size; i++) rarityFlagged.push(items.add(0x20 + i * 4).readS32());
                }
            }
        } catch { /* liste illisible */ }
        return { ok: true, cfgClassName, id: body.id, kind: paramClass, varType, values,
            rarityFlagged, cfgPtr: cfg.toString() };
    });

    // --- TRACE one-shot de la résolution de variable d'ability (#68/#75, étendu #57c-C) ---
    // Interceptor.attach TEMPORAIRE sur `AbilityConfiguration.GetVariableForLevel @181576fb0`
    // (l'API externe, basse fréquence — PAS un hot path). Capture {varType, state{level,mult},
    // cfg ptr, backtrace RVAs, VALEUR retournée (int brut RAX)} : la donnée runtime que le
    // décompilé ne peut pas donner. La VALEUR + la pile identifient la config/mécanisme sans
    // ambiguïté (leçon #57c-C : le couple {state,varType} seul est sous-déterminé — coïncidences
    // 831/1496 multi-configs ont coûté 2 fausses pistes ; c'est value=2992 dans la pile
    // GetAdditionalHitsFromEffectsInternal @180e59150 qui a tranché ExplosiveMaladies).
    // ARM ON-DEMAND uniquement (jamais auto-armé — leçon modifier-observe), à retirer via
    // varTraceRemove sitôt la mesure faite.
    let varTraceListener: InvocationListener | null = null;
    const varTraceBuf: Array<Record<string, unknown>> = [];
    ctx.rpc.varTraceInstall = (): Promise<unknown> => queueOnMainThread(() => {
        if (varTraceListener) return { ok: true, already: true };
        const cfgClass = findClassAnywhere("IdunBattle.Configuration", "AbilityConfiguration");
        if (!cfgClass) return { ok: false, error: "AbilityConfiguration non résolu" };
        // GetVariableForLevel(varType, state, noThrow) @181576fb0 — l'API EXTERNE (au-dessus de
        // TryGetVariableArrayForLevel) : onLeave lit la VALEUR RÉSOLUE (boxed int @+0x10) — la
        // donnée qui identifie la config/var sans ambiguïté (le couple {state} seul est sous-
        // déterminé : coïncidences 831/1496 multi-configs, vécu #57c-C).
        const mi = findMethodByParamCount(cfgClass, "GetVariableForLevel", 3);
        if (!mi || mi.ptr.isNull()) return { ok: false, error: "GetVariableForLevel non résolu" };
        const gaBase = Process.getModuleByName("GameAssembly.dll").base;
        varTraceListener = Interceptor.attach(mi.ptr, {
            onEnter(args) {
                try {
                    const st = args[2];
                    (this as InvocationContext & { entry?: Record<string, unknown> }).entry = {
                        varType: args[1].toInt32(),
                        level: st.readS32(),
                        mult: st.add(4).readS32(),
                        counter: st.add(8).readS32(),
                        cfg: args[0].toString(),
                        // RVAs GameAssembly de la pile d'appel (VA ghidra = RVA + 0x180000000).
                        bt: Thread.backtrace(this.context, Backtracer.ACCURATE)
                            .filter((a) => a.compare(gaBase) >= 0)
                            .slice(0, 10)
                            .map((a) => a.sub(gaBase).toString()),
                    };
                } catch { /* frame illisible */ }
            },
            onLeave(retval) {
                const entry = (this as InvocationContext & { entry?: Record<string, unknown> }).entry;
                if (!entry || varTraceBuf.length >= 500) return;
                // retour = int BRUT (registre RAX), pas un boxed object.
                entry.value = retval.toInt32();
                varTraceBuf.push(entry);
            },
        });
        return { ok: true, installed: true };
    });
    ctx.rpc.varTraceRead = (
        body?: { reset?: boolean; varType?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        const entries = (typeof body?.varType === "number")
            ? varTraceBuf.filter((e) => e.varType === body.varType)
            : varTraceBuf.slice();
        const out = { ok: true, count: varTraceBuf.length, entries };
        if (body?.reset) varTraceBuf.length = 0;
        return out;
    });
    ctx.rpc.varTraceRemove = (): Promise<unknown> => queueOnMainThread(() => {
        if (varTraceListener) { varTraceListener.detach(); varTraceListener = null; }
        varTraceBuf.length = 0;
        return { ok: true };
    });

    /** ATTACK-HISTORY par unité (`ActorStatisticsComponent` @180f92980) — capteur des compteurs
     *  runtime de combat, dont `TotalTurnsWithAttacksMade` que le natif consomme pour le buff
     *  MartialInspiration (#106 : `+33% Damage` par tour où l'unité a attaqué cette bataille ; base
     *  prédiction 1-coup = `var12 · (100 + 33·count)/100`). Compteur PER-UNIT non exposé ailleurs
     *  (ni decisionView ni combatSnapshot). Offsets CONFIRMÉS par TROIS lectures indépendantes du
     *  décompilé : `TotalAttacksMadeFormula.Calculate @180f25b90` lit `*(comp+0x20)` ;
     *  `TotalTurnsWithAttacksMadeFormula.Calculate @180f26780` lit `*(comp+0x30)` ; `RegisterAttackMade
     *  @180f91b50` incrémente `+0x20` à CHAQUE attaque et `+0x30` UNE fois/tour (gate « déjà attaqué ce
     *  tour » @+0x40). Classe résolue par NOM (findClassAnywhere) ; offset par `getFieldOffset` avec
     *  fallback décompilé. Read-only, one-shot, aucun Interceptor. body: { runnerId?, unitId? } */
    ctx.rpc.actorStats = (
        body?: { runnerId?: number; unitId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const asClass = findClassAnywhere("IdunBattle.Entities.Components", "ActorStatisticsComponent");
        if (!asClass) return { ok: false, error: "ActorStatisticsComponent non résolu" };
        // Offsets int32 sur le composant (décompilé, 3 confirmations). getFieldOffset par nom si le dump
        // le porte, sinon le fallback (offsets non-nuls -> `||` sûr, comme le reste du module).
        const OFF_TOTAL = getFieldOffset(asClass, "TotalAttacksMade") || 0x20;
        const OFF_TURNS = getFieldOffset(asClass, "TotalTurnsWithAttacksMade") || 0x30;
        const units: Array<Record<string, unknown>> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
            if (body?.unitId !== undefined && id !== body.unitId) return;
            let comp: NativePointer | null = null;
            forEachComponent(e, (c, klass) => {
                if (comp === null && klass.equals(asClass)) comp = c;
            });
            if (comp === null) return;
            const cp = comp as NativePointer;
            units.push({
                entityId: id,
                totalAttacksMade: cp.add(OFF_TOTAL).readS32(),
                totalTurnsWithAttacksMade: cp.add(OFF_TURNS).readS32(),
            });
        });
        return { ok: true, runner: label, units };
    });

}
