// guild-war-config — LA BC D'UN MATCH DE GUILD WAR, FABRIQUEE PAR LE JEU, SANS UN OCTET RESEAU.
//
// POURQUOI CE MODULE EXISTE
// --------------------------
// Le guild war est le SEUL mode de bataille qui n'a AUCUNE voie sandbox native. Mesure du
// 2026-08-18 sur le build courant, TROIS sources concordantes :
//
//   1. il n'existe pas de `SandboxGuildWarBattleConfig` -- les 11 classes `Sandbox*BattleConfig`
//      sont Battle, Boosts, CampaignEvent, Draft, GuildBoss, Infested, Pvp, Survival,
//      Territories, TreasureBeach, Waves ;
//   2. il n'existe pas de `BattleConfigBuilder$$GetHotseatGuildWarsConfig` -- alors que les 10
//      autres modes ont chacun leur `GetHotseat*Config` ;
//   3. `BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig` (le ROUTEUR par type) n'a pas de
//      branche GuildWars.
//
// `sandbox-mode.ts` est donc structurellement incapable de le monter, et ce n'est pas un trou de
// notre outillage : c'est une absence cote JEU.
//
// ⛔ ET LA VOIE NATIVE PARLE AU SERVEUR -- C'EST TOUT L'INTERET DE CE MODULE
// --------------------------------------------------------------------------
// `idun.shared.commands.ViewCommandExecutor$$StartGuildWarsMatch(battleData)` fonctionne, et on
// NE L'UTILISE PAS. Lu au decompile : elle alloue une `GuildWarsGameModeSource` puis appelle
// `StartMatch`. Or le squelette `AGameModeSource` appelle
// `GuildWarsGameModeSource$$SendLoadBattleGameEventInternal` PAR SLOT DE VTABLE -- ses deux
// seules xrefs sont des DATA, aucun appelant direct. Ce natif genere un battleId
// (`IdunMetaLogic.UserProgress.Util.TempBattleData$$GenerateNewBattleId`) et le pousse par un
// appel d'interface : la tentative est ENREGISTREE SERVEUR, AU CHARGEMENT.
//
// Le guild war a des tentatives limitees ET un debuff cumulatif par tentative
// (`GuildWarsAttemptDebuffWidget`, `attemptDebuffPercentage`). Monter par la voie native coute
// donc une vraie tentative sur le compte, irreversible. C'est exactement le verrou que #10020-r1
// avait deja documente pour le guild boss.
//
// CE QU'ON FAIT A LA PLACE : LA FABRIQUE, PAS LA SOURCE
// ------------------------------------------------------
// `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetGuildWarsConfig` est une fonction
// PUREMENT CONSTRUCTIVE : 14 donnees en entree, une `IdunBattle.Configuration.BattleConfiguration`
// en sortie. Elle est appelee par `GuildWarsGameModeSource$$LoadBattleInternal`, dont le corps ne
// porte AUCUN `Send*` -- `LoadBattleInternal` et `SendLoadBattleGameEventInternal` sont deux
// overrides virtuels INDEPENDANTS. On appelle donc la fabrique sans jamais instancier la source.
//
// La BC obtenue est celle du JEU, pas une reconstruction : c'est le point. Une BC de syncPvp
// re-etiquetee serait une approximation dont il faudrait prouver l'equivalence.
//
// CE QUE LA FABRIQUE ECRIT DE SPECIFIQUE, MESURE AU DECOMPILE
// ------------------------------------------------------------
//   - `BC.GameMode = idun.Shared.Battle.GameMode.GuildWars`
//   - deux `IdunBattle.Configuration.PlayerConfiguration`, PlayerIndex 1 (nous) et 2 (ennemi)
//   - `BC.Victory.VictoryConditions[VictoryConditionType.KillAllEnemyMainUnits] = 1`
//     (l'entree est ajoutee APRES `GetLevelConfigWithRealUnits`, c'est la signature du mode)
//
// ⚠ LE RANK LIMIT N'EST PAS UNE REGLE DE BATAILLE -- IL NE DESCEND PAS DANS LA BC.
// `GuildWarBattleData.RarityCap` (+0x44 du record) n'est lu QUE par
// `GuildWarsGameModeSource$$GetGameModeSpecificDeploymentHudOptionsInternal`, qui le recopie dans
// `idun.ui.GameModeSpecificUnitDeploymentHudOptions_GuildWars`. `LoadBattleInternal` ne le lit
// jamais, et `GetGuildWarsConfig` ne le prend meme pas en parametre. C'est une contrainte
// d'INTERFACE, appliquee a la SELECTION des unites. En sandbox on choisit soi-meme le roster,
// donc le cap ne s'applique pas -- et si on veut etre fidele, on filtre soi-meme la liste qu'on
// passe ici. Ne PAS aller chercher un gate de rarete dans la BC : il n'y en a pas.
//
// ⚠ CE MODULE NE MONTE RIEN. Il rend un JSON. Le montage reste le geste separe et confirme de
// `sandbox.ts` (`sandboxStartBattle`), qui ECRASE le match courant -- d'ou `confirmer` la-bas.

import {
    class_get_name, findClassAnywhere, findCtorByParamCount, findMethod,
    findMethodByParamClasses, findMethodByParamCount, methodParamClass,
    methodParamClassName, readIl2cppString, s as cstr,
} from "../il2cpp/helpers.js";
import { createManagedString, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { deserializeFromJson, isDeserializerReady, isSerializerReady, serializeToJson }
    from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
import { champPointeur, estRefus, refus } from "./lecture-champs.js";
import { getCapturedUniverse } from "./unit-visual-resolve.js";
import { Ctx } from "../controller.js";

/** Le namespace de la fabrique et de ses satellites. */
const NS_VIEW = "Idun.Source.IdunBattle.View";
/** Celui de la configuration de bataille. */
const NS_CFG = "IdunBattle.Configuration";

/** Les dependances que la fabrique exige, toutes lues sur le `ViewCommandExecutor` VIVANT.
 *  Meme foyer que `sandbox-mode.ts` : leur ABSENCE est un refus NOMME, jamais un appel tente. */
interface Deps {
    prog: NativePointer;            // IUnitProgression
    gameConfig: NativePointer;      // GameConfigDto
    logger: NativePointer;          // IIdunLogger
    featureUnlocker: NativePointer; // IFeatureUnlocker
}

function lireDeps(): Deps | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const lu: Record<string, NativePointer> = {};
    for (const nom of ["_unitProgression", "_gameConfigData", "_logger", "_featureUnlocker"]) {
        const p = champPointeur(exec as NativePointer, nom);
        if (estRefus(p)) return p;
        if ((p as NativePointer).isNull()) {
            return refus("`" + nom + "` est NUL sur le `ViewCommandExecutor` vivant "
                + "-- le meta n'est pas pleinement monte");
        }
        lu[nom] = p as NativePointer;
    }
    // `_gameConfigData` porte le DTO derriere `get_gameConfigDto` ; la fabrique veut le DTO.
    const kGcd = findClassAnywhere("IdunMetaLogic.Client.DTO.Config", "GameConfigData");
    let dto = lu["_gameConfigData"];
    if (kGcd) {
        const g = findMethod(kGcd, "get_gameConfigDto");
        if (g) {
            try {
                const r = invokeMethod(g.info, lu["_gameConfigData"], []);
                if (r && !r.isNull()) dto = r;
            } catch (e) {
                return refus("`GameConfigData$$get_gameConfigDto` a LEVE : " + (e as Error).message);
            }
        }
    }
    return {
        prog: lu["_unitProgression"], gameConfig: dto,
        logger: lu["_logger"], featureUnlocker: lu["_featureUnlocker"],
    };
}

/** Le `Func<String, IUnitModel>` que la fabrique appelle pour resoudre chaque unite ennemie.
 *
 *  ⚠ IL DOIT AGIR -- `il2cpp/delegate.ts` fabrique des delegues INERTES, ce qui ne convient pas
 *  ici : la fabrique s'en sert pour RESOUDRE, un stub muet rendrait une BC sans ennemis. On le
 *  construit donc sur une methode NATIVE existante, `UnitProgression$$GetUnit(String)`, dont la
 *  signature est exactement `String -> IUnitModel`.
 *
 *  ⚠ Et on passe par son CTOR a deux arguments (`object target, IntPtr method`), pas par une
 *  ecriture de champs : un delegue ne se re-cible pas par ecriture, et c'est le ctor qui
 *  renseigne `invoke_impl` correctement. Le piege n°1 de `delegate.ts` vise `createObject` (qui
 *  invoque le ctor avec `args = null`), pas un ctor correctement arme. */
function construireGetEnemyUnit(m: NativePointer, index: number, prog: NativePointer)
    : NativePointer | RefusVue {
    const kFunc = methodParamClass(m, index);
    if (!kFunc || kFunc.isNull()) {
        return refus("classe du parametre " + index + " (`getEnemyUnit`) illisible");
    }
    const kProg = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    if (!kProg) return refus("classe `IdunMetaLogic.UserProgress.UnitProgression` introuvable");
    const mGet = findMethodByParamCount(kProg, "GetUnit", 1);
    if (!mGet) {
        return refus("`IdunMetaLogic.UserProgress.UnitProgression$$GetUnit(String)` INTROUVABLE "
            + "sur ce build -- chemin PERIME");
    }
    const ctor = findCtorByParamCount(kFunc, 2);
    if (!ctor) {
        return refus("ctor a 2 parametres introuvable sur `"
            + cstr(class_get_name(kFunc) as NativePointer) + "`");
    }
    const d = il2cpp_object_new(kFunc);
    if (d.isNull()) return refus("allocation du `Func<String,IUnitModel>` a rendu NUL");
    gcRoot.add(d);                                  // cf. `delegate.ts` piege n°2
    // Le 2e argument du ctor est l'`IntPtr method` : c'est le `MethodInfo*`, donc `.info`.
    const argMethod = Memory.alloc(Process.pointerSize);
    argMethod.writePointer(mGet.info);
    invokeMethod(ctor.info, d, [prog, argMethod]);
    return d;
}

/** Construit une valeur managee a partir de JSON, en visant la classe du parametre `index`.
 *  C'est la technique de `sandbox-mode.ts` : on ne recopie AUCUNE signature ici -- la classe est
 *  lue au runtime, donc un renumerotage inter-build donne un refus nomme, pas un decalage muet. */
function depuisJson(m: NativePointer, index: number, json: string): NativePointer | RefusVue {
    const k = methodParamClass(m, index);
    if (!k || k.isNull()) return refus("classe du parametre " + index + " illisible");
    try {
        const v = deserializeFromJson(json, k);
        if (v.isNull()) {
            return refus("parametre " + index + " : la deserialisation a rendu NUL -- JSON "
                + "incompatible avec `" + cstr(class_get_name(k) as NativePointer) + "`");
        }
        return v;
    } catch (e) {
        return refus("parametre " + index + " : " + (e as Error).message);
    }
}

/** `List<IUnitModel>` : une interface ne se deserialise pas. On alloue la liste (classe du
 *  parametre, donc deja inflatee) et on y AJOUTE les modeles resolus par le jeu lui-meme. */
function listeDeModeles(m: NativePointer, index: number, prog: NativePointer, ids: string[])
    : NativePointer | RefusVue {
    const k = methodParamClass(m, index);
    if (!k || k.isNull()) return refus("classe du parametre " + index + " illisible");
    const kProg = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    const mGet = kProg ? findMethodByParamCount(kProg, "GetUnit", 1) : null;
    if (!mGet) return refus("`UnitProgression$$GetUnit(String)` INTROUVABLE");
    const ctor = findCtorByParamCount(k, 0);
    if (!ctor) return refus("ctor sans parametre introuvable sur la liste du parametre " + index);
    const lst = il2cpp_object_new(k);
    if (lst.isNull()) return refus("allocation de la liste du parametre " + index + " a rendu NUL");
    gcRoot.add(lst);
    invokeMethod(ctor.info, lst, []);
    const add = findMethodByParamCount(k, "Add", 1);
    if (!add) return refus("`Add` introuvable sur la liste du parametre " + index);
    const absents: string[] = [];
    for (const id of ids) {
        const mdl = invokeMethod(mGet.info, prog, [createManagedString(id)]);
        if (!mdl || mdl.isNull()) { absents.push(id); continue; }
        invokeMethod(add.info, lst, [mdl]);
    }
    if (absents.length > 0) {
        return refus("unites INCONNUES de la progression du compte : " + absents.join(", ")
            + " -- une unite non possedee n'a pas de `IUnitModel`, elle ne peut pas entrer dans "
            + "`availableMainPlayerUnits`");
    }
    return lst;
}

/** La `GuildWarPhaseProgression` VIVANTE, par le champ nomme de l'executeur.
 *
 *  ⚠ NE PAS conclure de `_liveEventState == null` que la progression est VIDE. Mesure du
 *  2026-08-18 : les deux champs `_liveEvent` / `_liveEventState` de
 *  `SingleLiveEventBasedProgression` sont NULS alors que `GetAttemptsLeft()` rend 10 et
 *  `GetGuildWarIdEvenIfItHasntStartedYet()` un GUID valide. L'etat est resolu A LA DEMANDE par la
 *  cascade `ILiveEventsProgression`, pas mis en cache dans ces champs. Un lecteur qui teste le
 *  champ conclurait « pas de guerre en cours » a tort -- c'est exactement l'erreur que ce
 *  commentaire existe pour empecher. Le discriminant est un APPEL, pas un champ. */
function progressionPhase(): NativePointer | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const p = champPointeur(exec as NativePointer, "_guildWarPhaseProgression");
    if (estRefus(p)) return p;
    if ((p as NativePointer).isNull()) {
        return refus("`_guildWarPhaseProgression` est NUL sur l'executeur vivant");
    }
    return p as NativePointer;
}

/** Invoque une methode d'instance NOMMEE et rend son retour, ou un refus NOMME. */
function appeler(k: NativePointer, sur: NativePointer, nom: string, nbArgs: number,
                 args: NativePointer[]): NativePointer | RefusVue {
    const m = findMethodByParamCount(k, nom, nbArgs);
    if (!m) return refus("`GuildWarPhaseProgression$$" + nom + "` a " + nbArgs
        + " parametre(s) INTROUVABLE -- chemin PERIME sur ce build");
    try {
        return invokeMethod(m.info, sur, args);
    } catch (e) {
        return refus("`" + nom + "` a LEVE : " + (e as Error).message);
    }
}

/** Serialise un objet manage, ou dit pourquoi il ne l'est pas. */
function enJson(p: NativePointer | RefusVue): unknown {
    if (estRefus(p)) return { erreur: (p as RefusVue).error };
    if ((p as NativePointer).isNull()) return null;
    try {
        const j = serializeToJson(p as NativePointer);
        return j === null ? { erreur: "serialisation NULLE" } : JSON.parse(j);
    } catch (e) {
        return { erreur: (e as Error).message };
    }
}

export function register(ctx: Ctx): void {
    /** LE `GuildWarConfigDto` COMPLET -- donc `zoneTypeConfigs`, donc LES CARTES.
     *
     *  POURQUOI PAR CETTE VOIE, ET PAS PAR `GetWarZoneConfig`
     *  ------------------------------------------------------
     *  `GuildWarPhaseProgression$$GetWarZoneConfig(warZoneType)` fait un lookup dans
     *  `cfg.zoneTypeConfigs` via `CollectionExtensions$$GetValueOrDefault`, un generique
     *  PLEINEMENT PARTAGE (`__Il2CppFullySharedGenericType`). Ce lookup DEREFERENCE sa cle, et
     *  aucune des trois formes d'appel ne passe la barriere du thunk -- mesure du 2026-08-18,
     *  16 ordinaux balayes a chaque fois :
     *    - `il2cpp_runtime_invoke` + valeur  -> `access violation accessing 0x219_0000000<ord>`
     *      (l'ordinal RECOLLE a un fragment de pointeur de tas) ;
     *    - entry point + valeur en registre  -> `access violation accessing 0x<ord>` ;
     *    - entry point + cle BOXEE           -> `0x<ord>` encore.
     *  Le temoin qui tranche est `ord = 0` : il NE PLANTE PAS et rend `null`, parce que 0 est
     *  le seul ordinal dont le dereferencement est benin. Le natif lit donc bien la cle comme
     *  une ADRESSE.
     *
     *  Plutot que de forcer ce thunk, on prend l'objet EN AMONT : `cfg` est passe en argument a
     *  `GuildWarsScoreCalculator$$GetAllPossibleScores`, qui est STATIQUE et NON generique. On
     *  l'ancre, on declenche `GuildWarPhaseProgression$$GetAllPossibleScores()` (0 argument,
     *  donc invocable sans piege de convention), on recupere `cfg`, on DETACHE, puis on
     *  serialise. Newtonsoft rend alors `zoneTypeConfigs` clefs PAR NOM -- ce qui supprime du
     *  meme coup le besoin de connaitre l'ordinal de `WarZoneType`, absent du dump.
     *
     *  ⚠ Le handler d'ancrage ne fait QUE deposer un pointeur : aucun appel natif, aucun travail
     *  JS. C'est la seule forme sure quand on ancre une methode situee dans la chaine de celle
     *  qu'on invoque -- « le natif depose, le pump ramasse ». Et il DETACHE avant tout usage. */
    ctx.rpc.guildWarZoneConfigs = (): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const kProg = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                        "GuildWarPhaseProgression");
        const kCalc = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                        "GuildWarsScoreCalculator");
        if (!kProg || !kCalc) {
            return { ok: false, error: "classe manquante : "
                + `progression=${kProg !== null} calculateur=${kCalc !== null}` };
        }
        const mCalc = findMethodByParamCount(kCalc, "GetAllPossibleScores", 1);
        const mProg = findMethodByParamCount(kProg, "GetAllPossibleScores", 0);
        if (!mCalc || !mProg) {
            return { ok: false, error: "`GetAllPossibleScores` INTROUVABLE : "
                + `calculateur(1)=${mCalc !== null} progression(0)=${mProg !== null}` };
        }

        let cfg: NativePointer | null = null;
        const ancre = Interceptor.attach(mCalc.ptr, {
            onEnter(args) { cfg = args[0]; },      // DEPOSE, rien d'autre
        });
        let leve: string | null = null;
        try {
            invokeMethod(mProg.info, prog as NativePointer, []);
        } catch (e) {
            leve = (e as Error).message;
        }
        ancre.detach();                            // DETACHER avant tout usage
        Interceptor.flush();

        if (cfg === null || (cfg as NativePointer).isNull()) {
            return { ok: false,
                error: "`cfg` NON CAPTURE -- `GetAllPossibleScores` n'a pas atteint le "
                    + "calculateur (guerre non demarree ?)",
                leve };
        }
        const c = cfg as NativePointer;
        const dico = c.add(0x40).readPointer();     // `zoneTypeConfigs`, offset MESURE
        return {
            ok: true,
            cfg: c.toString(),
            zoneTypeConfigsNul: dico.isNull(),
            config: enJson(c),
            leve,
        };
    });

    /** LIT la guerre de guilde EN COURS : cibles, zone, slot defensif, buffs.
     *
     *  Aucune ecriture, aucun appel reseau -- ces methodes lisent la progression deja resolue
     *  cote client. C'est la MEME forme que `guild-boss-config.ts`, et c'est ce qui evite
     *  d'INVENTER une carte ou une equipe adverse. */
    ctx.rpc.guildWarBoardRead = (body?: {
        warZoneId?: string; zonePartIndex?: number; slotIndex?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const sur = prog as NativePointer;
        const k = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                    "GuildWarPhaseProgression");
        if (!k) return { ok: false, error: "classe `GuildWarPhaseProgression` introuvable" };

        const i32 = (v: number) => { const p = Memory.alloc(4); p.writeS32(v); return p; };
        /** ⚠ `il2cpp_runtime_invoke` BOXE les types valeur : il rend un OBJET dont la valeur est
         *  a `+0x10`, pas un entier. Caster le pointeur avec `.toInt32()` rend l'adresse tronquee
         *  -- mesure du 2026-08-18 : `GetAttemptsLeft` a rendu `1176113984` la ou `viewInvoke`,
         *  qui deboxe correctement, rendait `10`. Toujours lire A TRAVERS la boite. */
        const lireInt = (nom: string): number | string => {
            const m = findMethodByParamCount(k, nom, 0);
            if (!m) return "INTROUVABLE";
            try {
                const r = invokeMethod(m.info, sur, []);
                return r.isNull() ? "NUL" : r.add(0x10).readS32();
            } catch (e) {
                return "LEVE: " + (e as Error).message;
            }
        };

        const res: Record<string, unknown> = {
            ok: true,
            guildWarId: enJson(appeler(k, sur, "GetGuildWarIdEvenIfItHasntStartedYet", 0, [])),
            attemptsLeft: lireInt("GetAttemptsLeft"),
            targets: enJson(appeler(k, sur, "GetTargets", 0, [])),
            battlefieldConfig: enJson(appeler(k, sur, "GetBattlefieldConfig", 0, [])),
            // LE ROSTER D'UNE GUERRE N'EST PAS LE ROSTER DU COMPTE : une unite ENGAGEE dans un
            // combat de guerre est EPUISEE et ne peut plus repartir. C'est le jeu qui tient cette
            // liste (`ExhaustUnits` l'alimente a chaque envoi), donc on la LIT au lieu de la
            // deviner -- un ecran de deploiement rempli du roster complet proposerait des unites
            // que le jeu refuse.
            exhaustedUnits: enJson(appeler(k, sur, "GetExhaustedUnits", 0, [])),
        };

        // LE ROSTER QUE L'ECRAN DOIT AFFICHER, tel que l'UI le calcule elle-meme.
        //
        // `GetExhaustedUnits()` ci-dessus rend la liste des unites DEJA ENGAGEES dans la guerre.
        // ⚠ Une liste VIDE y est une reponse LEGITIME (aucune bataille jouee dans cette guerre),
        // pas le signe d'un accesseur muet -- verifie aupres de l'utilisateur le 2026-08-18, apres
        // que je l'aie soupconnee a tort par analogie avec `GetWarZoneSlot`. Ne pas re-suspecter
        // cette methode sans avoir d'abord etabli qu'une unite A ete engagee.
        //
        // `GetUsableAndExhaustedUnits` donne les DEUX faces d'un coup, et c'est elle qui fait foi
        // pour remplir l'ecran : `utilisables` = roster du compte MOINS les epuisees. Elle prend
        // une adresse de bataille (`Nullable<ValueTuple<String,Int32>>`) -- on la passe VIDE, donc
        // « pas de zone particuliere ».
        //
        // Le retour est un `ValueTuple<List<IUnitModel>, List<IUnitModel>, Dictionary<...>>`, donc
        // un TYPE VALEUR : `il2cpp_runtime_invoke` le rend BOXE, et les trois references vivent
        // a `+0x10`, `+0x18`, `+0x20` de la boite.
        const mUse = findMethodByParamCount(k, "GetUsableAndExhaustedUnits", 2);
        if (mUse) {
            const inclureMow = Memory.alloc(1); inclureMow.writeU8(0);
            const adresse = Memory.alloc(24); adresse.writeByteArray(new Array(24).fill(0));
            try {
                const boite = invokeMethod(mUse.info, sur, [inclureMow, adresse]);
                if (boite.isNull()) {
                    res.usableEtEpuisees = { erreur: "retour NUL" };
                } else {
                    res.usableEtEpuisees = {
                        utilisables: enJson(boite.add(0x10).readPointer()),
                        epuisees: enJson(boite.add(0x18).readPointer()),
                    };
                }
            } catch (e) {
                res.usableEtEpuisees = { erreur: (e as Error).message.slice(0, 120) };
            }
        } else {
            res.usableEtEpuisees = { erreur: "`GetUsableAndExhaustedUnits` a 2 parametres INTROUVABLE" };
        }

        // ENUMERER les zones : `GetTargets()` ne rend que les cibles MARQUEES par la guilde (elle
        // rend `[]` quand personne n'a marque), donc elle ne peut pas servir d'inventaire. La voie
        // qui inventorie est `GetWarZone(affiliation, index)` -- on balaye les deux fronts.
        const zones: unknown[] = [];
        const mZone2 = findMethodByParamClasses(k, "GetWarZone", ["FrontLineAffiliation", "Int32"]);
        if (mZone2) {
            for (let aff = 0; aff < 3; aff++) {
                for (let idx = 0; idx < 12; idx++) {
                    let z: NativePointer;
                    try { z = invokeMethod(mZone2.info, sur, [i32(aff), i32(idx)]); } catch { break; }
                    if (!z || z.isNull()) continue;
                    const j = enJson(z);
                    if (j) zones.push({ affiliation: aff, index: idx, zone: j });
                }
            }
        }
        res.zones = zones;
        res.zonesRefus = mZone2 ? null
            : "`GetWarZone(FrontLineAffiliation, Int32)` INTROUVABLE -- chemin PERIME";

        // Une adresse de bataille (zone, part, slot) => la ZONE et le SLOT DEFENSIF reels.
        if (body?.warZoneId) {
            const id = createManagedString(body.warZoneId);
            const zp = i32(body.zonePartIndex ?? 0);
            const sl = i32(body.slotIndex ?? 0);
            const mZone1 = findMethodByParamClasses(k, "GetWarZone", ["String"]);
            const zone = mZone1 ? invokeMethod(mZone1.info, sur, [id]) : NULL;
            res.warZone = enJson(zone);
            res.warZoneSlot = enJson(appeler(k, sur, "GetWarZoneSlot", 3, [id, zp, sl]));
            res.activeBuffs = enJson(appeler(k, sur, "GetActiveBuffs", 1, [id]));
            res.occupant = enJson(appeler(k, sur, "GetOccupyingGuildMember", 2, [id, zp]));

            // LA CARTE. Mirror de `ShowGuildWarsBattlePreviewPopupCommand$$OnStartBattleButtonClicked` :
            // le `warZoneType` de la zone (champ `Nullable` a `+0x20`) alimente DEUX configs --
            // `GetWarZoneConfig` porte le BoardId (`+0x10`) et le SpawnPointsSet (`+0x18`),
            // `GetZoneConfig` porte les caps de rarete, dont `GetRarityCap(cfg, slotIndex)` tire
            // celui du slot. Rien n'est devine ici : ce sont les memes appels, dans le meme ordre.
            if (!zone.isNull()) {
                // ⚠ L'ORDINAL NE SE DEVINE PAS. `WarZoneType` est ABSENT de la table des enums
                // (Newtonsoft le serialise par NOM : "AntiAirBattery"), et lire le `Nullable` a
                // `+0x20` a rendu `1` -- valeur qui fait LEVER les deux configs. On ne suppose
                // donc rien : on BALAYE les ordinaux et on publie ce que CHACUN rend. Le mapping
                // ordinal -> board se DERIVE de la mesure, il ne se recopie pas.
                res.octetsWarZoneType = [zone.add(0x20).readS32(), zone.add(0x24).readS32()];
                const mCfg = findMethodByParamCount(k, "GetWarZoneConfig", 1);
                const balayage: unknown[] = [];
                if (mCfg) {
                    // ⚠ PAS `il2cpp_runtime_invoke` ICI, ET C'EST MESURE. Le corps de
                    // `GuildWarPhaseProgression$$GetWarZoneConfig` fait `local = param_2` puis
                    // passe `&local` a `CollectionExtensions$$GetValueOrDefault` : il attend donc
                    // l'enum PAR VALEUR, en registre. `runtime_invoke`, lui, passe un POINTEUR
                    // vers la valeur -- le natif recolle alors mon ordinal a un fragment de
                    // pointeur de tas et dereference. Signature du crash, sur les 16 ordinaux :
                    // `access violation accessing 0x219_0000000<ord>`, ou `0x219` est le prefixe
                    // du tas IL2CPP et `<ord>` exactement la valeur passee.
                    // On appelle donc l'ENTRY POINT, avec la convention IL2CPP reelle :
                    // `(this, args..., const MethodInfo*)`.
                    // ⚠ ET LA CLE DOIT ETRE BOXEE. Passer l'ordinal BRUT fait planter sur
                    // `access violation accessing 0x<ord>` -- l'adresse fautive EST la valeur,
                    // donc le natif la DEREFERENCE. C'est la signature d'un dictionnaire gshared
                    // (`__Il2CppFullySharedGenericType`) : sa cle est un OBJET, pas une valeur.
                    // Une boite IL2CPP, c'est un objet dont la valeur vit a `+0x10`.
                    const kWzt = findClassAnywhere(
                        "Idun.Source.IdunMeta.Logic.UserProgress.GuildWars", "WarZoneType");
                    res.classeWarZoneType = kWzt !== null;
                    const fn = new NativeFunction(mCfg.ptr, "pointer",
                                                  ["pointer", "pointer", "pointer"]);
                    for (let ord = 0; ord < 16; ord++) {
                        if (!kWzt) break;
                        const boite = il2cpp_object_new(kWzt);
                        if (boite.isNull()) continue;
                        gcRoot.add(boite);
                        boite.add(0x10).writeS32(ord);
                        let c: NativePointer;
                        try { c = fn(sur, boite, mCfg.info) as NativePointer; } catch (e) {
                            balayage.push({ ord, erreur: (e as Error).message.slice(0, 60) });
                            continue;
                        }
                        if (!c || c.isNull()) { balayage.push({ ord, config: null }); continue; }
                        let bid: string | null = null;
                        let sps: number | null = null;
                        try {
                            const p = c.add(0x10).readPointer();
                            bid = p.isNull() ? null : readIl2cppString(p);
                            sps = c.add(0x18).readS32();
                        } catch { /* offsets a confirmer */ }
                        balayage.push({ ord, boardId: bid, spawnPointsSet: sps, brut: enJson(c) });
                    }
                }
                res.warZoneConfigParOrdinal = balayage;
                res.warZoneConfigRefus = mCfg ? null : "`GetWarZoneConfig` INTROUVABLE";
            }
        }
        return res;
    });

    /** Resout TOUTE la chaine et rend ce qui manque. N'INVOQUE RIEN -- a jouer avant
     *  `guildWarBuildBc`, pour lire un refus AVANT de tenter plutot qu'apres coup. */
    ctx.rpc.guildWarProbe = (): Promise<unknown> => queueOnMainThread(() => {
        const kB = findClassAnywhere(NS_VIEW, "BattleConfigBuilder");
        const m = kB ? findMethodByParamCount(kB, "GetGuildWarsConfig", 14) : null;
        const kVals = findClassAnywhere(NS_VIEW, "BattleConfigGameConfigValues");
        // Le ctor VISE, celui qui prend l'univers -- pas l'autre surcharge a 2 parametres.
        const ctorVals = kVals
            ? findMethodByParamClasses(kVals, ".ctor", [null, "ITileConfigurationSource"]) : null;
        // Et la liste des surcharges, pour que le refus soit LISIBLE quand la visee echoue.
        const ctorsVals: string[] = [];
        if (kVals) {
            for (let n = 0; n <= 3; n++) {
                const c = findCtorByParamCount(kVals, n);
                if (!c) continue;
                const cls: string[] = [];
                for (let i = 0; i < n; i++) cls.push(methodParamClassName(c.info, i) ?? "?");
                ctorsVals.push("(" + cls.join(", ") + ")");
            }
        }
        const kSet = findClassAnywhere(NS_VIEW, "BattleConfigSettings");
        const mFrom = kSet ? findMethodByParamCount(kSet, "FromFeatureToggles", 1) : null;
        const deps = lireDeps();
        const univers = getCapturedUniverse();
        const params: Array<{ index: number; classe: string | null }> = [];
        if (m) {
            for (let i = 0; i < 14; i++) {
                const k = methodParamClass(m.info, i);
                params.push({
                    index: i,
                    classe: k && !k.isNull() ? cstr(class_get_name(k) as NativePointer) : null,
                });
            }
        }
        return {
            ok: true,
            fabrique: {
                classe: kB ? cstr(class_get_name(kB) as NativePointer) : null,
                getGuildWarsConfigResolue: m !== null,
                params,
            },
            gameConfigValues: kVals !== null,
            gameConfigValuesCtorVise: ctorVals !== null,
            gameConfigValuesCtors: ctorsVals,
            battleConfigSettings: mFrom !== null,
            dependances: estRefus(deps) ? null : {
                unitProgression: (deps as Deps).prog.toString(),
                gameConfigDto: (deps as Deps).gameConfig.toString(),
                logger: (deps as Deps).logger.toString(),
                featureUnlocker: (deps as Deps).featureUnlocker.toString(),
            },
            dependancesRefus: estRefus(deps) ? (deps as RefusVue).error : null,
            univers: univers ? univers.toString() : null,
            universRefus: univers ? null
                : "`IdunUniverse` NON CAPTURE -- le warmup ne l'a pas pose (rejouer "
                  + "`POST /api/admin/warmup`)",
            serialiseurPret: isSerializerReady(),
            deserialiseurPret: isDeserializerReady(),
            // Ce que `guildWarBuildBc` exigera, pour que l'appelant sache CE QUI manque.
            pret: kB !== null && m !== null && ctorVals !== null && mFrom !== null
                && !estRefus(deps) && univers !== null && isSerializerReady(),
        };
    });

    /** Fabrique la BC d'un match de guild war et la rend en JSON. AUCUN montage, AUCUN reseau. */
    ctx.rpc.guildWarBuildBc = (body?: {
        id?: string; boardId?: string; spawnPointsSet?: number;
        playerUnits?: string[]; enemyLineupJson?: string;
        playerAmmo?: number; randomizeAiInput?: boolean;
        environmentAbilitiesJson?: string; enemyMachineJson?: string;
    }): Promise<unknown> | unknown => {
        if (!body?.boardId) return { ok: false, error: "`boardId` manquant" };
        if (!body?.enemyLineupJson) {
            return { ok: false, error: "`enemyLineupJson` manquant -- c'est la liste des "
                + "`PredefinedUnit` du camp adverse, celle qu'un guild war oppose" };
        }
        const joueurs = body.playerUnits ?? [];
        if (joueurs.length === 0) return { ok: false, error: "`playerUnits` vide" };

        return queueOnMainThread(() => {
            const kB = findClassAnywhere(NS_VIEW, "BattleConfigBuilder");
            if (!kB) return { ok: false, error: "`BattleConfigBuilder` introuvable" };
            const m = findMethodByParamCount(kB, "GetGuildWarsConfig", 14);
            if (!m) {
                return { ok: false, error: "`BattleConfigBuilder$$GetGuildWarsConfig` a 14 "
                    + "parametres INTROUVABLE -- signature changee, chemin PERIME" };
            }
            const deps = lireDeps();
            if (estRefus(deps)) return { ok: false, error: (deps as RefusVue).error };
            const d = deps as Deps;
            const univers = getCapturedUniverse();
            if (!univers) {
                return { ok: false, error: "`IdunUniverse` NON CAPTURE -- rejouer le warmup" };
            }

            // --- le builder, monte comme `LoadBattleInternal` le monte -------------------------
            const kVals = findClassAnywhere(NS_VIEW, "BattleConfigGameConfigValues");
            // ⚠ DEUX ctors a 2 parametres existent : `(GameConfigDto, List<TileConfiguration>)` et
            // `(GameConfigDto, ITileConfigurationSource)`. `findCtorByParamCount` rendrait le
            // PREMIER, donc potentiellement celui qui attend une liste de tuiles -- on lui
            // passerait l'univers, et le natif fauterait plus loin sans dire pourquoi. On lie donc
            // par la CLASSE du parametre, jamais par son compte.
            const ctorVals = kVals
                ? findMethodByParamClasses(kVals, ".ctor", [null, "ITileConfigurationSource"])
                : null;
            if (!kVals || !ctorVals) {
                return { ok: false, error: "`BattleConfigGameConfigValues..ctor(GameConfigDto, "
                    + "ITileConfigurationSource)` INTROUVABLE -- l'autre surcharge attend une "
                    + "`List<TileConfiguration>` et ne convient pas ; signature changee ?" };
            }
            const vals = il2cpp_object_new(kVals);
            gcRoot.add(vals);
            invokeMethod(ctorVals.info, vals, [d.gameConfig, univers]);

            const kSet = findClassAnywhere(NS_VIEW, "BattleConfigSettings");
            const mFrom = kSet ? findMethodByParamCount(kSet, "FromFeatureToggles", 1) : null;
            if (!mFrom) {
                return { ok: false, error: "`BattleConfigSettings$$FromFeatureToggles` introuvable" };
            }
            const settings = invokeMethod(mFrom.info, NULL, [d.featureUnlocker]);

            const ctorB = findCtorByParamCount(kB, 5);
            if (!ctorB) return { ok: false, error: "`BattleConfigBuilder` ctor(5) introuvable" };
            const builder = il2cpp_object_new(kB);
            gcRoot.add(builder);
            // ⚠ `releasableUnitsSource` N'EST PAS NUL, et le supposer a coute un aller-retour.
            // `GuildWarsGameModeSource$$LoadBattleInternal` monte le builder avec
            // `(unitProgression, values, uVar9, logger, settings)` ou `uVar9 = thor.Globals+0x1e0`
            // -- LE MEME objet qu'il vient de passer comme `universe` a
            // `BattleConfigGameConfigValues..ctor`. L'`IdunUniverse` implemente donc les DEUX
            // interfaces (`ITileConfigurationSource` ET `IReleasableUnitsSource`). `GetGuildWarsConfig`
            // ne le lit peut-etre pas lui-meme, mais `GetLevelConfigWithRealUnits`, qu'elle appelle,
            // si. On passe l'univers, comme le jeu.
            invokeMethod(ctorB.info, builder, [d.prog, vals, univers, d.logger, settings]);

            // --- les 14 arguments, chacun lie contre la CLASSE de son parametre ----------------
            const mi = m.info;
            const lineup = depuisJson(mi, 3, body.enemyLineupJson as string);
            if (estRefus(lineup)) return { ok: false, error: (lineup as RefusVue).error };

            const getEnemy = construireGetEnemyUnit(mi, 4, d.prog);
            if (estRefus(getEnemy)) return { ok: false, error: (getEnemy as RefusVue).error };

            let envAb: NativePointer = NULL;
            if (body.environmentAbilitiesJson) {
                const e = depuisJson(mi, 5, body.environmentAbilitiesJson);
                if (estRefus(e)) return { ok: false, error: (e as RefusVue).error };
                envAb = e as NativePointer;
            }

            const dispo = listeDeModeles(mi, 6, d.prog, joueurs);
            if (estRefus(dispo)) return { ok: false, error: (dispo as RefusVue).error };

            const mainIds = depuisJson(mi, 8, JSON.stringify(joueurs));
            if (estRefus(mainIds)) return { ok: false, error: (mainIds as RefusVue).error };

            let enemyMachine: NativePointer = NULL;
            if (body.enemyMachineJson) {
                const em = depuisJson(mi, 12, body.enemyMachineJson);
                if (estRefus(em)) return { ok: false, error: (em as RefusVue).error };
                enemyMachine = em as NativePointer;
            }

            const i32 = (v: number) => { const p = Memory.alloc(4); p.writeS32(v); return p; };
            const b8 = (v: boolean) => { const p = Memory.alloc(1); p.writeU8(v ? 1 : 0); return p; };
            /** `Nullable<T>` est un TYPE VALEUR : `il2cpp_runtime_invoke` attend un pointeur vers
             *  LA VALEUR, jamais `NULL`. Mesure du 2026-08-18 : passer `NULL` pour
             *  `mainPlayerType` / `enemyPlayerType` fait lever `GetGuildWarsConfig` en
             *  « access violation accessing 0x0 » -- le natif lit `&param` puis dereference.
             *  Une zone a ZERO vaut `hasValue = false`, donc « pas de valeur » : c'est exactement
             *  le defaut que `LoadBattleInternal` passe (il met `0` a ces positions). */
            const nullableVide = () => {
                const p = Memory.alloc(8);
                p.writeU64(0);
                return p;
            };

            let bc: NativePointer;
            try {
                bc = invokeMethod(mi, builder, [
                    createManagedString(body.id ?? "GuildWarsSandbox"),   // 0  id
                    createManagedString(body.boardId as string),          // 1  boardId
                    i32(body.spawnPointsSet ?? 0),                        // 2  spawnPointsSet
                    lineup as NativePointer,                              // 3  opponentLineup
                    getEnemy as NativePointer,                            // 4  getEnemyUnit
                    envAb,                                                // 5  environmentAbilities
                    dispo as NativePointer,                               // 6  availableMainPlayerUnits
                    i32(body.playerAmmo ?? 0),                            // 7  playerAmmo
                    mainIds as NativePointer,                             // 8  mainPlayerUnits
                    nullableVide(),                                       // 9  mainPlayerType (defaut)
                    nullableVide(),                                       // 10 enemyPlayerType (defaut)
                    NULL,                                                 // 11 overrideMainPlayerMachine
                    enemyMachine,                                         // 12 overrideOpponentPlayerMachine
                    b8(body.randomizeAiInput === true),                   // 13 randomizeAiInput
                ]);
            } catch (e) {
                return { ok: false, error: "`GetGuildWarsConfig` a LEVE : " + (e as Error).message };
            }
            if (!bc || bc.isNull()) {
                return { ok: false, error: "`GetGuildWarsConfig` a rendu NUL" };
            }
            if (!isSerializerReady()) {
                return { ok: false, error: "serialiseur Newtonsoft non resolu -- BC construite "
                    + "mais illisible", bc: bc.toString() };
            }
            // ⚠ `serializeToJson` rend `null` quand Newtonsoft refuse -- le distinguer d'une
            // chaine vide, sinon « a refuse » et « a rendu un JSON vide » seraient indiscernables.
            let json: string | null;
            try {
                json = serializeToJson(bc);
            } catch (e) {
                return { ok: false, error: "serialisation de la BC : " + (e as Error).message };
            }
            if (json === null) {
                return { ok: false, error: "la serialisation a rendu NUL -- la BC EXISTE mais "
                    + "Newtonsoft ne l'a pas rendue", bc: bc.toString() };
            }
            return { ok: true, bc: bc.toString(), configJson: json, bytes: json.length };
        });
    };
}
