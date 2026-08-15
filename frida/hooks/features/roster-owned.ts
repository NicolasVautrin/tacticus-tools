// roster-owned — LE ROSTER POSSEDE, demande au jeu plutot que devine a l'ecran.
//
// POURQUOI CE MODULE EXISTE. On a d'abord lu le roster en grattant l'ecran de dispatch
// d'une Operation (`expedition_roster.py`). Ca marche, mais c'est etroit sur trois axes,
// tous MESURES le 2026-08-10 :
//
//   - SCOPE PAR L'OPERATION : un ecran Imperial ne dit rien des Chaos/Xenos, et l'operation
//     Chaos du plateau n'etait pas atteignable (widget hors viewport, board virtualise).
//   - SCOPE PAR SES CRITERES PROPRES : deux operations Imperial rendent 32 et 34 eligibles
//     la ou une troisieme en montrait 51. L'eligibilite melange possession, alliance,
//     rarete et niveau -- elle n'est donc PAS un roster.
//   - TRIBUTAIRE DE L'UI : il faut naviguer, et un widget recycle fait lever le clic.
//
// Or le jeu expose la question directement :
//
//     IdunMetaLogic.UserProgress.UnitProgression$$HasUnitUnlocked(unitId:System.String)
//         : System.Boolean
//     IdunMetaLogic.UserProgress.UnitProgression$$AmountOfUnlockedUnits() : System.Int32
//
// On a deja le catalogue complet des identifiants (gameconfig, cote Python). Il suffit donc
// de POSER LA QUESTION une fois par identifiant : possession pure, toutes alliances, sans
// ecran, sans defilement, sans eligibilite melangee.
//
// LE RECOUPEMENT EST INTEGRE, ET C'EST LE POINT. `AmountOfUnlockedUnits()` est le compte que
// le JEU se donne. On le rend a cote du notre : s'ils divergent, notre catalogue d'entree est
// incomplet (ou l'unboxing est faux), et il vaut mieux le VOIR que de livrer une liste
// plausible. Un ecart n'est pas rattrape en silence -- il est publie.
//
// ⚠ UNBOXING. `invokeMethod` passe par `runtime_invoke`, qui BOXE les types valeur : un
// `System.Boolean` revient encapsule dans un objet, valeur utile a +0x10. Lire le pointeur
// lui-meme rendrait n'importe quoi -- et un « n'importe quoi » non nul se lirait `true`,
// donc un roster complet et FAUX. C'est exactement le genre de zero/un silencieux que le
// recoupement ci-dessus est la pour attraper.
//
// POSSEDER N'EST PAS POUVOIR PARTIR, et `details: true` sert exactement cet ecart. Le
// decompile de `ExpeditionUnitEligibility$$IsEligibleFor` consulte trois etats de l'unite :
// sa RARETE (`GetRarity`), son RANG (`GetRank`) et sa grande alliance. Les deux premiers ne
// se derivent PAS du gameconfig -- c'est de la progression de compte. On les demande donc au
// meme foyer, a la meme instance, dans la meme passe.
//
// ARME A LA DEMANDE. LECTURE SEULE : aucune ecriture, aucun envoi.

import {
    findClassAnywhere, findMethodByParamCount, getFieldOffset, MethodRef,
} from "../il2cpp/helpers.js";
// Le FOYER de la resolution du `ViewCommandExecutor` -- importe, jamais re-marche.
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

/** Borne sur le nombre d'identifiants interrogeables en un appel. Le catalogue en compte
 *  ~130 ; la borne est large mais elle existe pour qu'un appelant fautif ne fige pas le jeu. */
const MAX_IDS = 2000;

let instance: NativePointer | null = null;

/** L'`UnitProgression` vivante : celle captee a l'ecran, SINON celle du `ViewCommandExecutor`.
 *
 *  TROISIEME MODULE DE LA MEME FAMILLE, MEME REMEDE. L'interception ci-dessous attend qu'un
 *  ecran touchant au roster s'affiche ; ce champ-ci se LIT, donc il repond depuis n'importe
 *  ou. Mesure du 2026-08-15, build `t6dpr4k06g` : `ViewCommandExecutor._unitProgression`
 *  (+952, declare `IUnitProgression`) rend un pointeur vivant de classe REELLE
 *  `UnitProgression`, sans qu'aucun ecran de roster ait ete ouvert.
 *
 *  ⚠ Resolu PAR NOM, jamais par le +952 mesure. `getFieldOffset` rend -1 sur un nom absent,
 *  et -1 est *truthy* : tester `< 0`, jamais `||`.
 *  ⚠ Memoise dans `instance` -- donc `instanceVue` continue de dire la verite. */
function progressionUnites(): NativePointer | null {
    if (instance) return instance;
    try {
        const exec = executeurVivant();
        if (typeof exec === "object" && exec !== null && (exec as RefusVue).ok === false) {
            return null;
        }
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return null;
        const off = getFieldOffset(kExec, "_unitProgression");
        if (off < 0) return null;
        const p = (exec as NativePointer).add(off).readPointer();
        if (p.isNull()) return null;
        instance = p;
        return p;
    } catch { return null; }
}
let miHasUnlocked: MethodRef | null = null;
let miAmount: MethodRef | null = null;
let miRank: MethodRef | null = null;
let miRarity: MethodRef | null = null;
const listeners: InvocationListener[] = [];
const layout: Record<string, unknown> = {};

/** `IdunMetaLogic.UserProgress.Model.UnitRarity` -- lu dans
 *  `data/symbols/<build>/frida/enums.tsv`, jamais devine. */
const RARETES = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"];

/** Valeur d'un `System.Boolean` BOXE rendu par `runtime_invoke` (octet a +0x10). */
function boolBoxe(p: NativePointer): boolean | null {
    if (p.isNull()) return null;
    try { return p.add(0x10).readU8() !== 0; } catch { return null; }
}

/** Valeur d'un `System.Int32` BOXE. */
function intBoxe(p: NativePointer): number | null {
    if (p.isNull()) return null;
    try { return p.add(0x10).readS32(); } catch { return null; }
}

export function register(ctx: Ctx): void {
    /** Arme la capture d'instance. body: {} -> { ok, layout } */
    ctx.rpc.rosterOwnedArm = (): Promise<unknown> => queueOnMainThread(() => {
        if (listeners.length > 0) {
            return { ok: true, deja: true, instanceVue: instance !== null, layout };
        }
        const klass = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
        if (!klass) {
            return { ok: false, error: "IdunMetaLogic.UserProgress.UnitProgression introuvable" };
        }
        miHasUnlocked = findMethodByParamCount(klass, "HasUnitUnlocked", 1);
        miAmount = findMethodByParamCount(klass, "AmountOfUnlockedUnits", 0);
        // Les deux etats que l'eligibilite d'une Operation consulte (cf. `details` plus bas).
        miRank = findMethodByParamCount(klass, "GetRank", 1);
        miRarity = findMethodByParamCount(klass, "GetRarity", 1);
        layout["HasUnitUnlocked"] = miHasUnlocked ? true : "NON RESOLUE";
        layout["AmountOfUnlockedUnits"] = miAmount ? true : "NON RESOLUE";
        layout["GetRank"] = miRank ? true : "NON RESOLUE";
        layout["GetRarity"] = miRarity ? true : "NON RESOLUE";
        if (!miHasUnlocked) {
            return { ok: false, error: "HasUnitUnlocked NON RESOLUE", layout };
        }
        // On retient `this` au passage. Ces methodes sont appelees par l'UI des qu'un ecran
        // touche au roster ; on n'en declenche AUCUNE nous-memes.
        for (const [nom, arite] of [["HasUnitUnlocked", 1], ["AmountOfUnlockedUnits", 0],
                                    ["HasUnlockedAnyMachineOfWar", 0]] as Array<[string, number]>) {
            const mi = findMethodByParamCount(klass, nom, arite);
            if (!mi || mi.ptr.isNull()) continue;
            try {
                listeners.push(Interceptor.attach(mi.ptr, {
                    onEnter(args) {
                        try { if (!args[0].isNull()) instance = args[0]; } catch { /* avale */ }
                    },
                }));
            } catch { /* porte suivante */ }
        }
        Interceptor.flush();
        log("[roster-owned] arme : " + listeners.length + " porte(s)");
        return {
            ok: true, armes: listeners.length, instanceVue: instance !== null, layout,
            note: "l'instance est captee au premier ecran qui touche au roster "
                + "(accueil, Collection, dispatch) -- navigue une fois si `instanceVue` est faux",
        };
    });

    /** body: { ids: string[] } -> { ok, possedes, absents, compteJeu, coherent }
     *
     *  `ids` vient du catalogue gameconfig, cote appelant : ce module ne devine aucun
     *  identifiant, il repond OUI/NON sur ceux qu'on lui donne. */
    ctx.rpc.rosterOwned = (body?: { ids?: string[]; details?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            const ids = body?.ids;
            if (!Array.isArray(ids) || ids.length === 0) {
                return { ok: false, error: "rosterOwned: `ids` (liste non vide) requis" };
            }
            if (ids.length > MAX_IDS) {
                return { ok: false, error: "rosterOwned: " + ids.length + " ids > borne "
                                          + MAX_IDS };
            }
            const inst = progressionUnites();
            if (!inst || !miHasUnlocked) {
                return {
                    ok: false,
                    error: inst
                        ? "HasUnitUnlocked NON RESOLUE"
                        : "AUCUNE instance d'UnitProgression -- ni captee a l'ecran, ni "
                          + "lisible en `_unitProgression` sur le ViewCommandExecutor "
                          + "(champ renomme sur ce build, ou nav pas initialisee)",
                };
            }
            const possedes: string[] = [];
            const absents: string[] = [];
            const illisibles: string[] = [];
            for (const id of ids) {
                if (typeof id !== "string" || !id) { illisibles.push(String(id)); continue; }
                let v: boolean | null = null;
                try {
                    v = boolBoxe(invokeMethod(miHasUnlocked.info, inst,
                                              [createManagedString(id)]));
                } catch { v = null; }
                if (v === null) illisibles.push(id);
                else if (v) possedes.push(id);
                else absents.push(id);
            }
            // Le compte que le JEU se donne. Tri-etat : `null` = pas mesure.
            let compteJeu: number | null = null;
            if (miAmount) {
                try { compteJeu = intBoxe(invokeMethod(miAmount.info, inst, null)); }
                catch { compteJeu = null; }
            }

            // RANG ET RARETE, sur demande. Ce sont les deux etats que
            // `ExpeditionUnitEligibility$$IsEligibleFor` consulte pour dire si une unite peut
            // partir sur une Operation ; sans eux, un plan de dispatch raisonne sur la seule
            // POSSESSION et peut proposer une unite que l'operation refuse.
            // Tri-etat par unite : `null` = appel non revenu, jamais rabattu sur 0 -- un rang 0
            // se lirait comme une unite au rang minimum, donc eligible a tort.
            let details: Record<string, { rank: number | null; rarity: number | null;
                                          rarete: string | null }> | null = null;
            if (body?.details) {
                details = {};
                for (const id of possedes) {
                    const s = createManagedString(id);
                    let rank: number | null = null;
                    let rarity: number | null = null;
                    if (miRank) {
                        try { rank = intBoxe(invokeMethod(miRank.info, inst, [s])); }
                        catch { rank = null; }
                    }
                    if (miRarity) {
                        // `UnitRarity` est un enum : type VALEUR, donc BOXE comme un entier.
                        try { rarity = intBoxe(invokeMethod(miRarity.info, inst, [s])); }
                        catch { rarity = null; }
                    }
                    details[id] = {
                        rank, rarity,
                        rarete: rarity === null ? null : (RARETES[rarity] ?? "?" + rarity),
                    };
                }
            }

            return {
                ok: true,
                interroges: ids.length,
                possedes, absents, illisibles,
                nbPossedes: possedes.length,
                compteJeu,
                details,
                detailsIndisponibles: body?.details
                    ? [miRank ? null : "GetRank", miRarity ? null : "GetRarity"].filter(Boolean)
                    : null,
                // Un ecart ne prouve pas une erreur -- notre catalogue d'entree peut etre plus
                // etroit que ce que le jeu compte (machines de guerre, unites non lineup).
                // Mais il doit etre VU : une liste plausible qui diverge du compte natif est
                // exactement ce qu'on ne veut pas livrer en silence.
                coherent: compteJeu === null ? null : compteJeu === possedes.length,
                note: "`coherent: false` n'est pas forcement une faute : compare d'abord le "
                    + "PERIMETRE de `ids` a ce que le jeu compte (MoW, non-lineup).",
            };
        });

    ctx.rpc.rosterOwnedStatus = (): Promise<unknown> => queueOnMainThread(() => ({
        ok: true, arme: listeners.length > 0, instanceVue: instance !== null, layout,
    }));

    ctx.rpc.rosterOwnedDisarm = (): Promise<unknown> => queueOnMainThread(() => {
        for (const l of listeners) { try { l.detach(); } catch { /* deja parti */ } }
        listeners.length = 0;
        return { ok: true, instanceConservee: instance !== null };
    });
}
