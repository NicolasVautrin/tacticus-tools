// LE REGISTRE DES COMPOSITIONS — une décision, DEUX consommateurs qui lisent la même chose.
//
// LE PROBLÈME QUE ÇA RÉSOUT, ET IL EST SILENCIEUX
// ------------------------------------------------
// La composition et les buffs se posent à DEUX moments différents, et c'est structurel :
//
//   `LoadBattle.onLeave`   -- la BC vient d'être fabriquée, pas encore remise au runner. C'est la
//                             SEULE fenêtre où l'environnement soit mutable (mesuré : le runner lit
//                             `BC.EnvironmentAbilities` à son `Initialize` et personne ne relit
//                             ensuite).
//   `GetBattleLineup`      -- le FSM de déploiement demande QUI le joueur amène. Mesuré par pile :
//                             `StateMachineActions$$DeployBattleLineup` ->
//                             `VisualBattleQuery$$GetBattleLineupToDeploy` -> ici. La BC est DÉJÀ
//                             passée au runner à ce moment (on est dans `IdunMainView$$StartBattle`).
//
// Si ces deux moments lisent des sources DIFFÉRENTES, on buffe des unités qui ne se déploient pas.
// L'écart ne lève aucune erreur : les buffs s'installent, sur les mauvaises cibles, et le résultat
// se lit comme « les buffs ne marchent pas ». D'où ce registre : UN endroit, LU deux fois.
//
// LA CLÉ EST LE MODE, ET C'EST LE SEUL DÉNOMINATEUR COMMUN
// ---------------------------------------------------------
// Au `LoadBattle.onLeave` on tient la BC et la source ; à `GetBattleLineup` on ne tient que la
// source. La classe de source (`CampaignGameModeSource`, ...) est donc la seule identité
// disponible AUX DEUX endroits. Corollaire assumé et DIT : une composition retenue par mode, pas
// par nœud. Deux nœuds du même mode partagent l'entrée -- si ça devient faux pour ton usage, c'est
// la clé qu'il faut enrichir, pas un contournement à ajouter.
//
// CE QUI EST ÉCRIT, ET CE QUI NE L'EST PAS
// -----------------------------------------
// Rien n'est persisté côté jeu. Le natif reconstruit son `String[]` depuis sa propre sauvegarde à
// CHAQUE appel -- mesuré, les deux observations rendent le même `avant`. On réécrit donc pour
// l'appel en cours, et le compte reste intact dès qu'on désarme. Muter la configuration serait
// l'idéal ; ce registre est le repli honnête, et il ne prétend pas être autre chose.
//
// ⛔ MUTUELLEMENT EXCLUSIF AVEC `lineupSource`. Ce module ANCRE `GetBattleLineup` ; `lineup-lire`
// l'INVOQUE. Invoquer une méthode qu'on ancre fait retomber l'appel natif dans notre propre
// trampoline pendant que Frida veut y exécuter du JS sur un thread qui tient déjà le runtime --
// gel mesuré trois fois sur trois dans ce dépôt. `estArme()` est exporté pour que la lecture
// REFUSE au lieu de geler.
//
// ⚠ OBSERVER D'ABORD. Tant qu'aucun passage n'a établi que le retour est un tableau de chaînes ET
// sa longueur, on n'écrit RIEN -- une longueur lue de travers ferait écrire dans le tas du jeu.
// ⚠ ON N'ÉCRIT QUE DANS LES CASES QUI EXISTENT (`min(n, ids)`), et le rapport DIT la troncature.
// ⚠ ENRACINER AVANT D'ÉCRIRE : entre `il2cpp_string_new` et l'écriture, la chaîne n'est référencée
// par rien de managé et une collecte la libérerait.

import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";
import {
    class_get_name, findClassAnywhere, findMethodByParamCount, s as cstr,
} from "../il2cpp/helpers.js";
import { createManagedArray, createManagedString } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";

/** Les sources dont on sait qu'elles DÉCLARENT `GetBattleLineup(1)`. Une source absente d'ici
 *  n'est pas « sans composition » : elle n'est pas couverte par CE module, et le refus le dit. */
const CLASSES: Readonly<Record<string, string>> = {
    campagne: "CampaignGameModeSource",
    pvp: "PvpGameModeSource",
    mow: "MachinesOfWarEventGameModeSource",
    guildBoss: "GuildBossGameModeSource",
};

/** `System.String[]` : longueur en `+0x18`, éléments dès `+0x20`. Relevé sur le lecteur de
 *  `game/source-lineup.ts` -- un seul endroit connaît cette disposition à l'origine. */
const OFF_LONGUEUR = 0x18;
const OFF_ELEMENTS = 0x20;
/** Une longueur lue de travers rendrait un nombre énorme. Aucun mode n'approche 64 places. */
const PLAFOND_PLACES = 64;

interface Observation {
    classeRetour: string | null;
    longueur: number | null;
    avant: string[] | null;
    /** QUI a appelé. Adresses BRUTES, jamais nommées ici : `DebugSymbol.fromAddress` ignore les
     *  méthodes IL2CPP. La table qui donne les symboles vit HORS du process. `null` = pas mesurée. */
    pile: string[] | null;
    base: string | null;
}

/** Une composition retenue, et D'OÙ elle vient. `origine` n'est pas décoratif : au moment de
 *  buffer, savoir si la composition a été décidée en sandbox ou posée à la main change la
 *  confiance qu'on lui accorde. */
export interface CompositionRetenue {
    ids: string[];
    confirme: boolean;
    origine: string;
}

/** Clé = NOM DE CLASSE de la source (pas le libellé de mode) : c'est ce que les deux
 *  consommateurs peuvent lire chacun de leur côté. */
const registre = new Map<string, CompositionRetenue>();

let listener: InvocationListener | null = null;
let classeArmee: string | null = null;
let fires = 0;
const observations: Observation[] = [];
let dernierePose: Record<string, unknown> | null = null;

/** Vrai tant qu'un `Interceptor` est posé. `lineup-lire` le consulte pour refuser d'INVOQUER la
 *  méthode qu'on ancre. */
export function estArme(): boolean {
    return listener !== null;
}

/**
 * L'ACCESSEUR DU SECOND CONSOMMATEUR — pour le chemin des BUFFS, au `LoadBattle.onLeave`.
 *
 * `classeSource` est le nom de classe de la source (celui que `class_get_name` rend sur
 * l'instance). Rend `null` quand aucune composition n'est retenue pour ce mode : l'appelant doit
 * alors DEMANDER À LA SOURCE, pas supposer une liste vide.
 */
export function compositionRetenue(classeSource: string | null): CompositionRetenue | null {
    if (classeSource === null) return null;
    const c = registre.get(classeSource);
    return c !== undefined && c.confirme ? c : null;
}

/** Lit un `System.String` géré. Même convention que `game/source-lineup.ts`. */
function chaineGeree(p: NativePointer): string | null {
    if (p.isNull()) return null;
    try { return p.add(0x14).readUtf16String(); } catch { return null; }
}

let baseModule: string | null = null;
function baseGameAssembly(): string | null {
    if (baseModule !== null) return baseModule;
    try {
        const m = Process.findModuleByName("GameAssembly.dll");
        baseModule = m ? m.base.toString() : null;
    } catch { baseModule = null; }
    return baseModule;
}

/** LA PILE, EN ADRESSES BRUTES. `FUZZY` comme `stack-sample` : `ACCURATE` s'appuie sur des
 *  prologues que le code IL2CPP optimisé ne présente pas toujours. */
function pileBrute(contexte: CpuContext): string[] | null {
    try {
        return Thread.backtrace(contexte, Backtracer.FUZZY).slice(0, 12).map((p) => p.toString());
    } catch { return null; }
}

function lireTableau(arr: NativePointer, contexte?: CpuContext): Observation {
    let classeRetour: string | null = null;
    try { classeRetour = cstr(class_get_name(arr.readPointer()) as NativePointer); } catch { /* nul */ }
    let longueur: number | null = null;
    try { longueur = arr.add(OFF_LONGUEUR).readS32(); } catch { /* nul */ }
    const pile = contexte ? pileBrute(contexte) : null;
    const base = baseGameAssembly();
    if (longueur === null || longueur < 0 || longueur > PLAFOND_PLACES) {
        return { classeRetour, longueur, avant: null, pile, base };
    }
    const avant: string[] = [];
    for (let i = 0; i < longueur; i++) {
        try {
            avant.push(chaineGeree(arr.add(OFF_ELEMENTS + i * Process.pointerSize).readPointer())
                ?? "<illisible>");
        } catch { avant.push("<illisible>"); }
    }
    return { classeRetour, longueur, avant, pile, base };
}

/** L'ÉCRITURE. N'est appelée qu'après une observation qui a établi classe ET longueur. */
function poser(arr: NativePointer, obs: Observation, ids: string[]): Record<string, unknown> {
    const n = obs.longueur as number;
    const combien = Math.min(n, ids.length);
    const ecrits: string[] = [];
    for (let i = 0; i < combien; i++) {
        const s = createManagedString(ids[i]);
        // ENRACINER D'ABORD : entre la fabrication et l'écriture, la chaîne n'est référencée par
        // rien de managé.
        gcRoot.add(s);
        arr.add(OFF_ELEMENTS + i * Process.pointerSize).writePointer(s);
        ecrits.push(ids[i]);
    }
    return {
        ecrits, combien, placesDuTableau: n, idsFournis: ids.length,
        tronque: ids.length > n,
        // Les cases NON réécrites gardent l'id d'origine : on le DIT, sinon une composition
        // partielle se lirait comme une composition complète.
        restantesInchangees: n > combien ? (obs.avant ?? []).slice(combien) : [],
    };
}

function armer(mode: string): Record<string, unknown> {
    const nomClasse = CLASSES[mode];
    if (nomClasse === undefined) {
        return { ok: false, refus: `mode inconnu \`${mode}\` -- connus : ${Object.keys(CLASSES).join(", ")}` };
    }
    const k = findClassAnywhere(NS_SRC, nomClasse);
    if (!k) return { ok: false, refus: `${NS_SRC}.${nomClasse} INTROUVABLE sur ce build` };
    const mi = findMethodByParamCount(k, "GetBattleLineup", 1);
    if (!mi) return { ok: false, refus: `\`${nomClasse}$$GetBattleLineup(1 param)\` INTROUVABLE` };

    listener = Interceptor.attach(mi.ptr, {
        onLeave(retval: InvocationReturnValue) {
            fires++;
            const arr = retval as unknown as NativePointer;
            if (arr.isNull()) return;
            const obs = lireTableau(arr, this.context);
            if (observations.length < 12) observations.push(obs);
            const retenue = compositionRetenue(classeArmee);
            if (retenue === null) return;
            if (obs.classeRetour === null || obs.longueur === null) return;
            if (obs.longueur <= 0 || obs.longueur > PLAFOND_PLACES) return;
            try {
                dernierePose = { ...poser(arr, obs, retenue.ids), fire: fires, origine: retenue.origine };
            } catch (e) {
                dernierePose = { erreur: (e as Error).message, fire: fires };
            }
        },
    });
    Interceptor.flush();
    classeArmee = nomClasse;
    return { ok: true };
}

function etatRegistre(): Array<Record<string, unknown>> {
    return Array.from(registre.entries()).map(([classe, c]) => ({
        classe, ids: c.ids, confirme: c.confirme, origine: c.origine,
    }));
}

export function register(ctx: Ctx): void {
    /**
     * AUTO-TEST DE LA LIAISON `il2cpp_array_new` — alloue, relit, jette.
     *
     * Il existe parce que la liaison est PARESSEUSE : un export absent ne se verrait ni à la
     * compilation ni au chargement, seulement au premier usage réel -- c'est-à-dire au pire
     * moment, en pleine substitution. Ce RPC déplace cette découverte AVANT.
     *
     * Il vérifie DEUX choses d'un coup, et la seconde compte autant : que l'allocation répond, et
     * que la disposition qu'on croit connaître (`longueur` en `+0x18`, classe au pointeur de tête)
     * se relit bien sur un tableau qu'on a fabriqué NOUS-MÊMES. Un `String[]` relu comme tel sur
     * notre propre allocation est la preuve que les offsets de LECTURE valent pour l'ÉCRITURE.
     *
     * N'écrit rien dans le jeu : le tableau reste vide et n'est confié à personne.
     */
    ctx.rpc.lineupArrayAutotest = (body?: { longueur?: number }): Promise<unknown> | unknown => {
        const n = body?.longueur ?? 5;
        return queueOnMainThread(() => {
            const kStr = findClassAnywhere("System", "String");
            if (!kStr) return { ok: false, refus: "classe `System.String` INTROUVABLE" };
            let arr: NativePointer;
            try { arr = createManagedArray(kStr, n); }
            catch (e) { return { ok: false, refus: (e as Error).message }; }
            // ENRACINER tout de suite : rien de managé ne le référence.
            gcRoot.add(arr);
            let classe: string | null = null;
            try { classe = cstr(class_get_name(arr.readPointer()) as NativePointer); } catch { /* nul */ }
            let relue: number | null = null;
            try { relue = arr.add(OFF_LONGUEUR).readS32(); } catch { /* nul */ }
            // Un tableau NEUF doit avoir toutes ses cases à NUL -- si ce n'est pas le cas, c'est
            // l'offset des éléments qui est faux, pas l'allocation.
            let premieresNulles: boolean | null = null;
            try {
                premieresNulles = true;
                for (let i = 0; i < Math.min(n, 4); i++) {
                    if (!arr.add(OFF_ELEMENTS + i * Process.pointerSize).readPointer().isNull()) {
                        premieresNulles = false;
                    }
                }
            } catch { premieresNulles = null; }
            gcRoot.remove(arr);
            return {
                ok: classe !== null && relue === n,
                demandee: n, longueurRelue: relue, classe, premieresCasesNulles: premieresNulles,
                note: "le tableau est LIBERE a la sortie : rien n'est confie au jeu",
            };
        });
    };

    ctx.rpc.lineupPoserArmer = (body?: {
        armer?: boolean; mode?: string;
    }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return {
                ok: true, lecture: true, arme: listener !== null, classeArmee, fires,
                observations, registre: etatRegistre(), dernierePose,
                note: "`{ armer: true, mode? }` pour ancrer (OBSERVER). Retenir une composition "
                    + "avec `lineupPoserUnites`. ⚠ tant que c'est armé, `lineupSource` REFUSE.",
            };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (listener) { listener.detach(); Interceptor.flush(); listener = null; }
                classeArmee = null;
                return { ok: true, arme: false, action: "retire", fires };
            }
            if (listener !== null) {
                return { ok: true, arme: true, classeArmee, fires, note: "déjà armé" };
            }
            const r = armer(body.mode ?? "campagne");
            if (r.ok !== true) return r;
            return {
                ok: true, arme: true, classeArmee, fires, registre: etatRegistre(),
                note: "régime OBSERVER -- rien n'est écrit tant qu'aucune composition CONFIRMÉE "
                    + "n'est retenue pour ce mode",
            };
        });
    };

    /** RETENIR une composition pour un mode. C'est l'entrée du registre : ce que `GetBattleLineup`
     *  posera, ET ce que le chemin des buffs devra lire pour viser les mêmes unités. */
    ctx.rpc.lineupPoserUnites = (body?: {
        mode?: string; unites?: string[] | null; confirmer?: boolean; origine?: string;
    }): unknown => {
        const mode = body?.mode ?? "campagne";
        const nomClasse = CLASSES[mode];
        if (nomClasse === undefined) {
            return { ok: false, refus: `mode inconnu \`${mode}\` -- connus : ${Object.keys(CLASSES).join(", ")}` };
        }
        if (!body || body.unites === undefined) {
            return { ok: true, lecture: true, registre: etatRegistre(), fires, observations, dernierePose };
        }
        if (body.unites === null) {
            registre.delete(nomClasse);
            return { ok: true, action: "efface", mode, classe: nomClasse, registre: etatRegistre() };
        }
        if (!Array.isArray(body.unites) || body.unites.length === 0) {
            return { ok: false, refus: "`unites` doit être un tableau NON VIDE d'ids d'unité" };
        }
        if (body.unites.some((u) => typeof u !== "string" || u.length === 0)) {
            return { ok: false, refus: "chaque id doit être une chaîne non vide" };
        }
        // Le cran qui rend ce module honnête : on ne remplit pas un tableau qu'on n'a jamais vu.
        const vue = observations.find((o) => o.classeRetour !== null && o.longueur !== null);
        if (body.confirmer === true && !vue) {
            return {
                ok: false,
                refus: `AUCUNE observation n'a lu le tableau (${observations.length} passage(s), `
                    + `${fires} fire(s)). Armer, ouvrir une bataille pour OBSERVER, puis confirmer.`,
            };
        }
        registre.set(nomClasse, {
            ids: body.unites.slice(),
            confirme: body.confirmer === true,
            origine: body.origine ?? "pose manuelle",
        });
        return {
            ok: true, mode, classe: nomClasse, registre: etatRegistre(), fires,
            placesObservees: vue ? vue.longueur : null,
            note: body.confirmer === true
                ? "RETENUE ET CONFIRMÉE -- sera posée au prochain `GetBattleLineup`, et lisible "
                    + "par le chemin des buffs via `compositionRetenue()`"
                : "retenue mais NON confirmée -- ni écrite, ni visible du chemin des buffs",
        };
    };
}
