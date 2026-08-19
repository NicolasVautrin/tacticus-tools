// visuel-abandonne — LE PAS VISUEL QUI NE SE REFERME JAMAIS, ET L'ETAGE QUI LE LACHE (#10038).
//
// CE QUI EST MESURE, pas suppose (session 41, build `t6dpr4k06g`, 2026-08-19) :
//
//   MessageExecutionQueue._currentlyProcessingMessage reste `true` pour toujours,
//   `_lastActivity` = "Ability_Active:Loki_NormalAttack", `_lastActivityStep` = "start",
//   6 messages coinces derriere. Le groupe bloque porte `<EntityId> 85` (eldarMauganRa),
//   `<Source> "Loki_NormalAttack"`, 3 messages, `_nextMessageIndex` 0 -- aucun execute.
//   Consequence : le runner continue d'appliquer les coups, l'ECRAN est fige. Quatre des cinq
//   vues du joueur restent sur leur case de deploiement.
//
// CE QUE LE DECOMPILE ETABLIT :
//
//   IdunBattle.View.BattleStream.GroupHandlers.Ability_Power_GroupHandler$$SetupAndExecuteAbility
//       this->_ability = ability
//       AbilityVisualsBase$$Init(ability, ...)        <- pose RootGroup (+0x100) et MainGroup
//       <fabrique le delegue onFinished>
//       AbilityVisualsBase$$Execute(ability, onFinished)
//
//   `Execute` ecrit `_onFinished` (+0x118) en TOUTE PREMIERE INSTRUCTION. Sur le visuel abandonne
//   `_onFinished` est NUL, alors que `RootGroup`/`MainGroup` sont poses ==> `Init` a rendu la main
//   par une EXCEPTION, et `Execute` n'a jamais tourne. Rien entre les deux ne peut echouer
//   autrement (une allocation mise a part), donc l'etage fautif est DANS `Init`.
//
//   Le dernier geste d'`Init` est `ParseTargetsFromQueue`, qui deref sans garde a une douzaine
//   d'endroits (`GroupMessage._messages` a +0x48, `AbilityVisualsUtils` a +0x90 puis son
//   `StreamMessages` a +0x88, chaque enumerateur...). C'est le suspect, PAS une certitude --
//   d'ou ce capteur.
//
// POURQUOI UN COMPTEUR ENTREE/SORTIE, ET PAS UN TRACEUR D'EXCEPTION
// ------------------------------------------------------------------
// `exception-tracer` ancre `il2cpp_raise_exception` et `_CxxThrowException` : sur cet incident il
// a rendu ZERO ligne, parce qu'un null-deref genere par IL2CPP passe par son helper interne
// (`FUN_1801f5460`), pas par l'API publique. Le signal qui, lui, ne peut pas mentir est
// structurel : quand une fonction part en exception, le deroulage de pile SAUTE son `onLeave`.
// Un `onEnter` sans `onLeave` EST donc un jet, quel que soit le chemin emprunte.
//
// LECTURE PURE : `onEnter`/`onLeave` seulement, aucune ecriture, aucun `retval.replace`.
// Ancre au register : ce sont des chemins FROIDS (un passage par cast d'ability), pas des
// getters d'UI -- le depot ne proscrit que les `replace` de chemin chaud.

import { findClassAnywhere, findMethod, getFieldOffset } from "../il2cpp/helpers.js";
import { champTexte } from "./lecture-champs.js";
import { Ctx } from "../controller.js";

interface Ancre {
    /** Nom cite au rapport, en SYMBOLE (jamais une adresse). */
    symbole: string;
    ns: string;
    cls: string;
    methode: string;
    /** Index de l'argument qui porte le visuel d'ability, ou `null` si c'est `this` (arg 0). */
    argVisuel: number;
    entrees: number;
    sorties: number;
    /** Les `this`/visuels entres et pas encore ressortis, dans l'ordre. */
    enVol: string[];
    refus: string | null;
}

const ANCRES: Ancre[] = [
    {
        symbole: "IdunBattle.View.BattleStream.GroupHandlers.Ability_Power_GroupHandler"
            + "$$SetupAndExecuteAbility",
        ns: "IdunBattle.View.BattleStream.GroupHandlers",
        cls: "Ability_Power_GroupHandler",
        methode: "SetupAndExecuteAbility",
        argVisuel: 1,
        entrees: 0, sorties: 0, enVol: [], refus: null,
    },
    {
        symbole: "IdunBattle.View.AbilityConfigs.AbilityVisualsBase$$Init",
        ns: "IdunBattle.View.AbilityConfigs",
        cls: "AbilityVisualsBase",
        methode: "Init",
        argVisuel: 0,
        entrees: 0, sorties: 0, enVol: [], refus: null,
    },
    {
        symbole: "IdunBattle.View.AbilityConfigs.AbilityVisualsBase$$ParseTargetsFromQueue",
        ns: "IdunBattle.View.AbilityConfigs",
        cls: "AbilityVisualsBase",
        methode: "ParseTargetsFromQueue",
        argVisuel: 0,
        entrees: 0, sorties: 0, enVol: [], refus: null,
    },
    {
        symbole: "IdunBattle.View.AbilityConfigs.AbilityVisualsBase$$Execute",
        ns: "IdunBattle.View.AbilityConfigs",
        cls: "AbilityVisualsBase",
        methode: "Execute",
        argVisuel: 0,
        entrees: 0, sorties: 0, enVol: [], refus: null,
    },
];

const listeners: InvocationListener[] = [];
let ancre = false;

/** Le groupe porte par un visuel, NOMME. `null` quand le champ n'est pas encore pose --
 *  ce qui est le cas normal a l'ENTREE d'`Init`, et c'est pour ca qu'on relit au rapport. */
function decrireVisuel(p: NativePointer): Record<string, unknown> {
    const out: Record<string, unknown> = { ptr: p.toString() };
    for (const champ of ["RootGroup", "MainGroup"]) {
        try {
            const off = getFieldOffset(p.readPointer(), champ);
            if (off <= 0) { out[champ] = null; continue; }
            const g = p.add(off).readPointer();
            if (g.isNull()) { out[champ] = null; continue; }
            const desc: Record<string, unknown> = { ptr: g.toString() };
            try {
                const offEnt = getFieldOffset(g.readPointer(), "<EntityId>k__BackingField");
                desc.entityId = offEnt > 0 ? g.add(offEnt).readS32() : null;
            } catch { desc.entityId = null; }
            try {
                desc.source = champTexte(g, "<Source>k__BackingField");
            } catch { desc.source = null; }
            out[champ] = desc;
        } catch { out[champ] = null; }
    }
    // `_onFinished` est LE discriminant : pose en 1re instruction d'`Execute`.
    try {
        const off = getFieldOffset(p.readPointer(), "_onFinished");
        out.onFinished = off > 0 && !p.add(off).readPointer().isNull();
    } catch { out.onFinished = null; }
    return out;
}

function ancrer(): void {
    if (ancre) return;
    ancre = true;
    for (const a of ANCRES) {
        try {
            const klass = findClassAnywhere(a.ns, a.cls);
            if (!klass || klass.isNull()) { a.refus = "classe introuvable"; continue; }
            const mi = findMethod(klass, a.methode);
            if (!mi || mi.ptr.isNull()) { a.refus = "methode non resolue"; continue; }
            listeners.push(Interceptor.attach(mi.ptr, {
                onEnter(args) {
                    a.entrees++;
                    try { a.enVol.push(args[a.argVisuel].toString()); }
                    catch { a.enVol.push("<argument illisible>"); }
                },
                onLeave() {
                    a.sorties++;
                    // Le deroulage d'exception SAUTE ce bloc : ce qui reste dans `enVol` est
                    // exactement ce qui n'est jamais revenu.
                    a.enVol.pop();
                },
            }));
        } catch (e) {
            a.refus = (e as Error).message;
        }
    }
}

export function register(ctx: Ctx): void {
    ancrer();

    /** QUEL ETAGE A LACHE, et sur quel groupe. Read-only.
     *
     *  `ecart > 0` sur une ancre = autant d'appels partis en EXCEPTION a cet etage. L'ancre la
     *  plus PROFONDE qui montre un ecart est le foyer ; ses parentes en montrent un aussi, parce
     *  que le jet les traverse.
     *
     *  `ecart == 0` PARTOUT alors que la file est bloquee refute l'hypothese du jet -- et c'est
     *  une reponse, pas un echec du capteur. */
    ctx.rpc.visuelAbandonneEtat = (): unknown => ({
        ok: true,
        ancre,
        etages: ANCRES.map((a) => ({
            symbole: a.symbole,
            refus: a.refus,
            entrees: a.entrees,
            sorties: a.sorties,
            ecart: a.entrees - a.sorties,
            // On RELIT les objets restes en vol : a l'entree d'`Init` les groupes ne sont pas
            // encore poses, donc seule une relecture tardive les nomme.
            enVol: a.enVol.map((s) => {
                try { return decrireVisuel(ptr(s)); }
                catch { return { ptr: s, relecture: "impossible" }; }
            }),
        })),
    });
}
