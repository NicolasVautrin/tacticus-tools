// deployment-draft — RENDRE L'ÉCRAN DE DÉPLOIEMENT NATIF UTILISABLE SUR UNE BATAILLE SANDBOX.
//
// LE FAIT MESURÉ (build `t6dpr4k06g`, décompilé) — LE SANDBOX STUBBE SON ROSTER
// -----------------------------------------------------------------------------
// Les deux corps, côte à côte :
//
//   `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$GetUnitsForDeploymentHUD`
//       lit la progression (`this+0x20`), construit un `Nullable` depuis `this+0x70`, appelle
//       le slot d'interface `0x15` pour obtenir une liste poolée d'unités, la MAPPE, la rend.
//
//   `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$GetUnitsForDeploymentHUD`
//       rend un conteneur poolé FRAÎCHEMENT LOUÉ, **sans lire un seul champ de `this`**.
//
// ⇒ L'écran de déploiement s'afficherait, VIDE. Ce n'est pas un défaut de notre montage : la
// source sandbox déclare le contrat et ne fournit rien. C'est le seul étage qui manque.
//
// CE QUI N'EST **PAS** UN BLOQUEUR, et il fallait le vérifier
// ------------------------------------------------------------
// `idun.Idun.Source.IdunBattle.View.Hud.UnitDeployment.UnitDeploymentHudGameModeFactory$$Create`
// ne dispatche PAS sur un enum de mode de jeu : il teste la NON-NULLITÉ de champs successifs de
// l'objet d'options (`+0x50`, `+0x30`, `+0x68`, `+0x60`, `+0x20`, `+0x28`, `+0x58`, `+0x48`,
// `+0x40`) et retombe, tous nuls, sur `UnitDeploymentHudGameModeDefault`. Or
// `SandboxGameModeSource$$GetGameModeSpecificDeploymentHudOptions` construit un
// `idun.ui.GameModeSpecificUnitDeploymentHudOptions` par défaut (il n'écrit que `+0x86 = 0`) —
// tous les champs discriminants restent nuls. **Le sandbox tombe donc sur le HUD générique, et
// il n'y a aucune branche manquante à ajouter.**
//
// LE CONTRAT, ET POURQUOI ON OBSERVE AVANT DE REMPLIR
// ----------------------------------------------------
// La méthode rend `idun.shared.collections.pools.PooledList<System.String>` — une liste d'IDS
// d'unités. Mais `classes.tsv` dit `PooledList\`1  parent=System.ValueType  isValueType=1` :
// c'est un **TYPE VALEUR**, donc le retour est une STRUCT, pas une référence. Sa disposition
// n'est pas lisible statiquement (générique ouvert, taille 0 dans la table).
//
// On ne PARIE donc pas dessus. Le module a deux régimes, et le second refuse tant que le premier
// n'a pas parlé :
//
//   OBSERVER  (défaut)  -- `onLeave` LIT le retour et rapporte ce qu'il voit (valeur brute, et le
//                          nom de classe trouvé derrière si ça pointe sur un objet géré). Écrit
//                          RIEN. C'est « un natif qui écrit s'observe d'abord », appliqué.
//   REMPLIR             -- ajoute nos ids à la liste RENDUE PAR LE STUB. On ne construit aucun
//                          conteneur : celui du stub est déjà du bon type et correctement loué —
//                          il est juste vide. La méthode `Add` est résolue AU RUNTIME sur la
//                          classe RÉELLEMENT observée, jamais sur un offset écrit ici.
//
// TROIS GARDES, toutes tirées de fautes déjà payées dans ce dépôt
// ---------------------------------------------------------------
//   * `Interceptor.attach` + écriture dans le retour, JAMAIS `Interceptor.replace` : un stop de
//     session avec un `replace` actif crashe le jeu (cf. `Ne jamais` du CLAUDE.md).
//   * on n'invoque JAMAIS `GetUnitsForDeploymentHUD` nous-mêmes — ancrer ce qu'on invoque gèle
//     le jeu, et ça a déjà coûté un gel ici (cf. `sandboxModeBcOverride`).
//   * le régime REMPLIR exige `confirmer: true` ET une observation préalable réussie.

import {
    class_get_name, findClassAnywhere, findMethodByParamCount, il2cppBase, s,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";
const METHODE = "GetUnitsForDeploymentHUD";

interface Refus { ok: false; error: string }
function refus(error: string): Refus { return { ok: false, error }; }

/** Ce que `onLeave` a VU au dernier passage — la seule base sur laquelle REMPLIR est autorisé. */
interface Observation {
    brut: string;            // le retour, en hexa
    pointeur: boolean;       // ressemble-t-il à un pointeur exploitable ?
    classe: string | null;   // nom de classe lu derrière, si lisible
    erreur: string | null;   // ce qui a empêché de lire (jamais un silence)
}

let listener: InvocationListener | null = null;
let observations: Observation[] = [];
let fires = 0;

/** Les ids à injecter. `null` = TRANSPARENT (le hook observe et ne touche à rien). */
let unites: string[] | null = null;
let dernierRemplissage: { ajoutes: number; erreur: string | null } | null = null;

/** Lit prudemment le nom de classe derrière un pointeur candidat. Ne lève jamais. */
function classeDerriere(p: NativePointer): { classe: string | null; erreur: string | null } {
    try {
        if (p.isNull()) return { classe: null, erreur: "retour NUL" };
        const klass = p.readPointer();
        if (klass.isNull()) return { classe: null, erreur: "slot de classe NUL" };
        // `il2cpp_class_get_name` rend un `char*`, JAMAIS une chaîne JS -- `s()` est le
        // convertisseur du dépôt. L'oublier rend un `[object Object]` qui se lit comme un nom.
        const nom = s(class_get_name(klass) as NativePointer);
        return { classe: nom || null, erreur: nom ? null : "class_get_name muet" };
    } catch (e) {
        return { classe: null, erreur: "lecture refusée : " + (e as Error).message };
    }
}

/** Ajoute nos ids à la liste rendue par le stub. `Add` résolu au RUNTIME sur la classe vue. */
function remplir(retour: NativePointer): { ajoutes: number; erreur: string | null } {
    const { classe, erreur } = classeDerriere(retour);
    if (classe === null) {
        return { ajoutes: 0, erreur: erreur ?? "classe du retour non identifiée" };
    }
    const klass = retour.readPointer();
    const miAdd = findMethodByParamCount(klass, "Add", 1);
    if (!miAdd) {
        return { ajoutes: 0, erreur: `\`Add\` (1 param) introuvable sur \`${classe}\` -- le retour `
            + "n'est pas le conteneur attendu ; NE RIEN ÉCRIRE" };
    }
    let n = 0;
    for (const id of unites ?? []) {
        try {
            invokeMethod(miAdd.info, retour, [createManagedString(id)]);
            n++;
        } catch (e) {
            return { ajoutes: n, erreur: `\`Add("${id}")\` a levé : ` + (e as Error).message };
        }
    }
    return { ajoutes: n, erreur: null };
}

function armer(): true | Refus {
    if (listener) return true;
    const k = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
    if (!k) return refus(`${NS_SRC}.SandboxGameModeSource INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, METHODE, 0);
    if (!mi) return refus(`\`SandboxGameModeSource$$${METHODE}\` INTROUVABLE (0 param)`);
    listener = Interceptor.attach(mi.ptr, {
        onLeave(retval) {
            fires++;
            const p = retval as unknown as NativePointer;
            const { classe, erreur } = classeDerriere(p);
            if (observations.length < 8) {
                observations.push({ brut: p.toString(), pointeur: !p.isNull(), classe, erreur });
            }
            // TRANSPARENT tant qu'aucun id n'est posé : le régime par défaut n'écrit RIEN.
            if (unites && unites.length) dernierRemplissage = remplir(p);
        },
    });
    Interceptor.flush();
    return true;
}

// ============================================================================
// PHASE DE DÉPLOIEMENT (#10020-r1) — forcer une sandbox à passer par l'écran de
// déploiement au lieu de sauter directement en `Running`.
//
// LA CHAÎNE, mesurée le 2026-08-17 (`t6dpr4k06g`), décompilée puis confrontée sur les objets
// VIVANTS (cf. `docs/rl/case-10020-lien-vue-source-sens-unique.md` §7-§8) :
//
//   IdunBattle.View.Game.IdunGameViews$$Enable(this, skipUnitDeployment)
//       si skipUnitDeployment == 0 ET <slot 0x34>(this+0x138 = _visualBattleQuery) :
//              -> IdunBattle.View.FSM.UnitSelectionFsm$$UnitDeployment       (PHASE DE DEPLOIEMENT)
//       sinon  -> IdunBattle.View.FSM.UnitSelectionFsm$$StartMatch           (direct en jeu)
//
//   IdunBattle.View.FSM.VisualBattleQuery$$ShouldShowUnitDeploymentHud  =  relais PUR vers
//       <slot 0x29>(this+0x80 = _gameModeSource : IGameModeSource)
//
// Sur une sandbox les DEUX rendent `false` (invoqués sur les objets vivants), et le corps de
// `SandboxGameModeSource$$ShouldShowUnitDeployment` est un `return 0` **CONSTANT** : aucun réglage
// de BC ni de gameconfig ne le fera basculer. D'où ce hook.
//
// ⛔ POURQUOI ON N'ANCRE PAS LA SOURCE, ET POURQUOI C'EST LE POINT CENTRAL DE CE MODULE
// -------------------------------------------------------------------------------------
// `SandboxGameModeSource$$ShouldShowUnitDeployment` résout au runtime sur un corps que **~745
// `MethodInfo` PARTAGENT** (745 xrefs DATA + 122 appels directs ; Ghidra le nomme d'après une
// classe sans rapport, `Stash.Native.StashNative$$get_IsPurchaseProcessing`). IL2CPP déduplique les
// corps triviaux : `return 0` n'a pas d'identité. S'y attacher basculerait à `true` TOUT ce qui rend
// « faux constant » dans le jeu — sans erreur, sans symptôme qui désigne la cause.
//
// Le dépôt portait déjà « l'absence dans la table ne prouve RIEN » : c'était le versant LECTURE.
// Ici c'est le versant ÉCRITURE, et il ne rate pas une conclusion — il fait un dégât.
//
// ⇒ On ancre le RELAIS, un étage au-dessus : il a un VRAI corps, donc une adresse propre
// (2 xrefs DATA : son `MethodInfo` + son entrée de vtable).
//
// ET LE GARDE EST EXÉCUTABLE, PAS ÉCRIT — une prose n'arrête pas un comportement. `teteTriviale()`
// lit les premiers octets du corps résolu et REFUSE l'attache si un `ret` (0xC3) tombe dans les 8
// premiers : un corps qui rend une constante rette en 1 à 4 octets, un relais réel commence par sa
// garde de cctor et son test de nullité. Le refus PUBLIE les octets, pour qu'on juge sur pièce et
// pas sur un verdict.
//
// RÉGIMES — `forcer` est FAUX par défaut, donc armer n'écrit RIEN.
//   OBSERVER : on lit le `skipUnitDeployment` que le jeu passe à `Enable`, et ce que le relais rend.
//              C'est la seule base sur laquelle on saura si forcer a un sens.
//   FORCER   : `onLeave` remplace le retour du relais par `true`. `Interceptor.attach`, JAMAIS
//              `replace` (un stop de session avec un `replace` actif crashe le jeu).
//
// ⚠ `VisualBattleQuery` sert TOUS les modes, pas seulement la sandbox : forcer sans désarmer ferait
// apparaître une phase de déploiement là où le jeu n'en veut pas. D'où l'armement explicite.

const NS_VBQ = "IdunBattle.View.FSM";
const CLS_VBQ = "VisualBattleQuery";
const METH_VBQ = "ShouldShowUnitDeploymentHud";
const NS_VIEWS = "IdunBattle.View.Game";
const CLS_VIEWS = "IdunGameViews";

/** Octets lus en tête de corps pour le garde de trivialité. */
const OCTETS_TETE = 8;

interface Tete {
    hex: string | null;
    /** Index du premier `ret` (0xC3) dans la tête, ou `null` s'il n'y en a pas. */
    retA: number | null;
    erreur: string | null;
}

/** Lit la tête du corps. Ne lève jamais — un refus de lecture est un refus, pas un silence. */
function lireTete(p: NativePointer): Tete {
    try {
        const buf = p.readByteArray(OCTETS_TETE);
        if (!buf) return { hex: null, retA: null, erreur: "lecture vide" };
        const o = new Uint8Array(buf);
        let retA: number | null = null;
        for (let i = 0; i < o.length; i++) {
            if (o[i] === 0xc3) { retA = i; break; }
        }
        const hex = Array.from(o).map((b) => b.toString(16).padStart(2, "0")).join(" ");
        return { hex, retA, erreur: null };
    } catch (e) {
        return { hex: null, retA: null, erreur: "lecture refusée : " + (e as Error).message };
    }
}

/** Le corps ressemble-t-il à une constante dédupliquée ? Voir l'en-tête. */
function teteTriviale(t: Tete): boolean {
    return t.retA !== null;
}

let relaisListener: InvocationListener | null = null;
let enableListener: InvocationListener | null = null;

/** `false` = OBSERVER (aucune écriture). `true` = le relais rendra `true`. */
let forcerPhase = false;

let relaisFires = 0;
let relaisForces = 0;
/** Ce que le relais a rendu AVANT toute substitution — la mesure, pas notre effet. */
const relaisRetours: number[] = [];
/** Le `skipUnitDeployment` que le jeu passe à `Enable`, tel quel. */
const enableObservations: Array<{ skip: number }> = [];

/** Ce que l'armement a établi sur les deux corps — publié, jamais résumé en booléen. */
let ancrage: {
    relais: { ghidraVA: string; tete: Tete } | null;
    enable: { ghidraVA: string; tete: Tete } | null;
} = { relais: null, enable: null };

function ghidraVA(p: NativePointer): string {
    return ptr("0x180000000").add(p.sub(il2cppBase)).toString();
}

function armerPhase(): true | Refus {
    if (relaisListener) return true;

    const kv = findClassAnywhere(NS_VBQ, CLS_VBQ);
    if (!kv) return refus(`${NS_VBQ}.${CLS_VBQ} INTROUVABLE sur ce build`);
    const mv = findMethodByParamCount(kv, METH_VBQ, 0);
    if (!mv) return refus(`\`${CLS_VBQ}$$${METH_VBQ}\` INTROUVABLE (0 param)`);

    // LE GARDE. Il vaut pour le relais comme pour n'importe quelle cible future : si le corps
    // résolu rend une constante, il est probablement PARTAGÉ, et s'y attacher est un dégât de
    // masse. On refuse en publiant les octets.
    const teteV = lireTete(mv.ptr);
    if (teteV.erreur !== null) {
        return refus(`tête du corps de \`${METH_VBQ}\` ILLISIBLE (${teteV.erreur}) -- `
            + "on ne s'attache pas à un corps qu'on n'a pas pu qualifier");
    }
    if (teteTriviale(teteV)) {
        return refus(`REFUS : \`${CLS_VBQ}$$${METH_VBQ}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${teteV.retA} ; tête = ${teteV.hex}). IL2CPP déduplique ces corps, `
            + "donc l'adresse est PARTAGÉE par N méthodes et s'y attacher les basculerait TOUTES. "
            + "Ancrer un appelant qui a un vrai corps. Cf. case-10020 §8.");
    }

    const kg = findClassAnywhere(NS_VIEWS, CLS_VIEWS);
    const mg = kg ? findMethodByParamCount(kg, "Enable", 1) : null;
    const teteG = mg ? lireTete(mg.ptr) : null;

    relaisListener = Interceptor.attach(mv.ptr, {
        onLeave(retval) {
            relaisFires++;
            // Le retour est un Boolean IL2CPP : la valeur utile est dans AL, d'où le masque.
            const brut = retval.toInt32() & 0xff;
            if (relaisRetours.length < 32) relaisRetours.push(brut);
            if (forcerPhase && brut === 0) {
                retval.replace(ptr(1));
                relaisForces++;
            }
        },
    });

    // `Enable` reste en OBSERVATION PURE, toujours : c'est lui qui dit si le drapeau
    // `skipUnitDeployment` court-circuite le prédicat, auquel cas forcer le relais ne servirait
    // à rien. Sans cette lecture, un forçage sans effet serait indiscernable d'un forçage raté.
    if (mg && teteG && teteG.erreur === null && !teteTriviale(teteG)) {
        enableListener = Interceptor.attach(mg.ptr, {
            onEnter(args) {
                if (enableObservations.length < 32) {
                    enableObservations.push({ skip: args[1].toInt32() & 0xff });
                }
            },
        });
    }

    Interceptor.flush();
    ancrage = {
        relais: { ghidraVA: ghidraVA(mv.ptr), tete: teteV },
        enable: mg && teteG ? { ghidraVA: ghidraVA(mg.ptr), tete: teteG } : null,
    };
    return true;
}

function etatPhase(): Record<string, unknown> {
    return {
        arme: relaisListener !== null,
        enableArme: enableListener !== null,
        forcer: forcerPhase,
        relaisFires, relaisForces,
        relaisRetours, enableObservations,
        ancrage,
    };
}

export function register(ctx: Ctx): void {
    /** OBSERVER / DÉSARMER. `{ armer: true }` pose le hook en régime transparent. */
    ctx.rpc.deploymentDraftArmer = (body?: { armer?: boolean }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, arme: listener !== null, fires,
                     unitesPosees: unites ? unites.length : null, observations,
                     dernierRemplissage,
                     note: "passer { armer: true } pour observer, { armer: false } pour retirer" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (listener) { listener.detach(); Interceptor.flush(); listener = null; }
                unites = null;
                return { ok: true, arme: false, action: "retire", fires };
            }
            const r = armer();
            if (r !== true) return r;
            return { ok: true, arme: true, fires, observations,
                     ancrage: `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$${METHODE}`,
                     note: "régime OBSERVER -- rien n'est écrit tant que `deploymentDraftUnites` "
                         + "n'a pas posé d'ids" };
        });
    };

    /** REMPLIR. Exige une observation préalable QUI A IDENTIFIÉ la classe du retour. */
    ctx.rpc.deploymentDraftUnites = (body?: {
        unites?: string[] | null; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body || body.unites === undefined) {
            return { ok: true, lecture: true, unitesPosees: unites, fires,
                     observations, dernierRemplissage };
        }
        return queueOnMainThread(() => {
            if (body.unites === null) {
                unites = null;
                return { ok: true, action: "retire", note: "hook redevenu TRANSPARENT" };
            }
            if (!Array.isArray(body.unites) || body.unites.some((u) => typeof u !== "string")) {
                return refus("`unites` doit être un tableau de chaînes (ids d'unité), ou null");
            }
            if (listener === null) {
                return refus("hook NON ARMÉ -- jouer `deploymentDraftArmer { armer: true }` "
                    + "d'abord, puis ouvrir l'écran de déploiement pour OBSERVER");
            }
            // Le cran qui rend ce module honnête : on ne remplit pas un conteneur qu'on n'a
            // jamais vu. Une observation qui n'a identifié AUCUNE classe = on refuse, en le
            // disant, plutôt que d'écrire dans un pointeur supposé.
            const vue = observations.find((o) => o.classe !== null);
            if (!vue) {
                return refus("AUCUNE observation n'a identifié la classe du retour ("
                    + `${observations.length} passage(s), ${fires} fire(s)). \`PooledList\` est un `
                    + "TYPE VALEUR : sa disposition doit être MESURÉE avant qu'on y écrive. "
                    + "Ouvrir l'écran de déploiement d'une sandbox, relire `deploymentDraftArmer`.");
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : au prochain affichage de l'écran de "
                    + `déploiement, ce hook ÉCRIRA dans le conteneur rendu (\`${vue.classe}\`).`);
            }
            unites = body.unites.slice();
            return { ok: true, unitesPosees: unites.length, classeVue: vue.classe,
                     note: "posé -- l'écriture aura lieu au PROCHAIN appel de "
                         + `\`SandboxGameModeSource$$${METHODE}\`` };
        });
    };

    /** ÉTAT du hook de phase de déploiement. Lecture pure. */
    ctx.rpc.deploymentPhaseStatus = (): unknown => ({ ok: true, lecture: true, ...etatPhase() });

    /**
     * ARMER / FORCER / DÉSARMER la phase de déploiement.
     *
     *   { armer: true }                      -> OBSERVER : pose les deux ancrages, n'écrit RIEN
     *   { forcer: true, confirmer: true }    -> le relais rendra `true` au prochain `Enable`
     *   { forcer: false }                    -> redevient transparent, ancrages en place
     *   { armer: false }                     -> retire tout
     *
     * `confirmer: true` est exigé pour FORCER, parce que c'est le seul geste qui écrit — et il
     * écrit dans la décision d'un objet (`VisualBattleQuery`) que TOUS les modes partagent.
     */
    ctx.rpc.deploymentPhaseArmer = (body?: {
        armer?: boolean; forcer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body || (body.armer === undefined && body.forcer === undefined)) {
            return { ok: true, lecture: true, ...etatPhase(),
                     note: "{ armer: true } pour OBSERVER ; puis { forcer: true, confirmer: true }" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (relaisListener) { relaisListener.detach(); relaisListener = null; }
                if (enableListener) { enableListener.detach(); enableListener = null; }
                Interceptor.flush();
                forcerPhase = false;
                return { ok: true, action: "retire", ...etatPhase() };
            }
            if (body.armer === true) {
                const r = armerPhase();
                if (r !== true) return r;
            }
            if (body.forcer !== undefined) {
                if (relaisListener === null) {
                    return refus("hook NON ARMÉ -- jouer `{ armer: true }` d'abord. Forcer sans "
                        + "avoir observé ne dirait pas si le drapeau `skipUnitDeployment` "
                        + "court-circuite déjà le prédicat.");
                }
                if (body.forcer === true && body.confirmer !== true) {
                    return refus("`confirmer: true` exigé : forcer écrit dans la décision de "
                        + "`VisualBattleQuery`, que TOUS les modes de jeu partagent -- une phase "
                        + "de déploiement apparaîtrait là où le jeu n'en veut pas.");
                }
                forcerPhase = body.forcer === true;
            }
            return { ok: true, action: body.armer === true ? "arme" : "regime", ...etatPhase() };
        });
    };
}
