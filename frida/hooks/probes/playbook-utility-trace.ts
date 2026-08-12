/** `#988` — CAPTEUR : l'utilite d'IA A SA SOURCE, sur les corps CONCRETS des playbooks.
 *
 *  ⚠ **INERTE tant que le bundle n'est pas rebuilde + reinjecte** (geste orchestrateur). Le
 *  `register` n'arme AUCUN hook : il n'expose qu'un RPC.
 *
 *  ## Ce qui manquait
 *
 *  L'oracle des faces DECISION ne voit que **l'action retenue**, jamais **le classement qui l'a
 *  produite** : un port peut rendre la bonne decision pour de mauvaises utilites, et rien ne le dit.
 *  Les canaux existants captent l'utilite en AVAL (ce qui est pousse dans un bucket, ce qui en est
 *  choisi, la cle de tri d'un selecteur) ; aucun ne lit le RETOUR des methodes de playbook.
 *
 *  ## Le perimetre est celui que la MESURE designe
 *
 *  Re-derive de `data/symbols/<build>/frida/methods.tsv` (corps PROPRES, donc adressables) :
 *
 *      EvaluateNonComparable            133   -> Bucket<UnitAction>   (caster, casterPosition, abilityState)
 *      CalculateCustomUtility            26   -> Fix64                (caster, casterPosition, TARGET, ability...)
 *      GetTargetUtility                   2   -> Fix64                (target) | (targetEntities)
 *      CalculateCasterPositionUtility     2   -> Fix64                (caster, casterPosition, abilityState)
 *
 *  Ce sont des **overrides concrets**, pas des corps gshared : chacun a sa propre RVA dans
 *  `frida/methods.tsv` ET dans `ghidra/functions.tsv`. Le piege du generique (`findMethod` rend le
 *  thunk d'invocation, le hook se declare `enabled` et fire ZERO fois) porte sur la BASE
 *  (`NonComparablePlaybook<T>$$...`), pas sur eux — c'est pourquoi on ancre les classes FILLES.
 *
 *  ⚠ L'exemple le plus cite (`GetTargetUtility`) est le plus PAUVRE : **2** corps, dont un seul
 *  prend une cible unitaire. Le gisement d'utilite PAR CIBLE est `CalculateCustomUtility`, dont la
 *  signature porte un `target:IdunBattle.Core.IEntity` — **26** corps. Suivre le nom cite en exemple
 *  plutot que la table aurait couvert 2 abilities au lieu de 26.
 *
 *  ## L'emission conditionnelle s'exprime par l'ADRESSE, jamais par un `if`
 *
 *  Un test dans `onEnter` n'evite rien : la traversee native -> JS a deja eu lieu. Le seul niveau ou
 *  le filtre agit AVANT le trampoline est le CHOIX DES ADRESSES qu'on instrumente. L'armement prend
 *  donc une LISTE DE PLAYBOOKS et n'ancre que les leurs. `all:true` existe, mais il faut vouloir
 *  les 163 corps.
 *
 *  Volume attendu, borne par la STRUCTURE du generateur (lue dans
 *  `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`) :
 *  `Evaluate` est appele par (unite x ability x POSITION candidate), et `CalculateCustomUtility`
 *  par (position x cible). Pour UN playbook arme, cela se compte en dizaines a quelques centaines
 *  d'appels par tour d'IA — plusieurs ordres de grandeur sous le regime de crash documente (un
 *  getter chaud a 27 000 appels/s). `diag.fires` le CONFIRMERA a la premiere fenetre : c'est une
 *  borne derivee de la structure, pas encore une mesure live.
 *
 *  ## Discipline
 *
 *  Arme a la demande, anneau borne, `disarm` detache. Read-only : aucune valeur reecrite, aucun
 *  `Interceptor.replace`, aucune invocation de natif (donc aucun risque de gel). La resolution est
 *  rendue AU MOMENT de l'armement — un capteur qui ne peut pas s'attacher doit le dire LA, pas se
 *  taire jusqu'a rendre zero fire.
 */
import {
    class_get_name, class_get_namespace, findMethod,
    assembly_get_image, domain_get, domain_get_assemblies, image_get_class,
    image_get_class_count, s,
} from "../il2cpp/helpers.js";
import { decodeBucket, chooseAction, countActions, fix64ToNumber, bucketLayoutReport,
    DecodedBucket } from "../ai-toolkit/bucket-decode.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

/** Les namespaces qui portent les playbooks concrets. Re-derives de la table : `.Loki` en porte
 *  157, la racine 6 — les deux comptent, et ne chercher que l'un en manquerait une partie. */
const PLAYBOOK_NAMESPACES = ["IdunBattle.AI.Playbook", "IdunBattle.AI.Playbook.Loki"];

/** Les methodes d'utilite ancrables, avec la position de leurs arguments interessants.
 *  `argCaster`/`argTarget` sont des index d'`args` Frida (args[0] = `this`). `null` = la signature
 *  n'en porte pas — on publie alors `null`, jamais un id fabrique. */
const ANCHORS: Record<string, {
    kind: "fix64" | "bucket"; argCaster: number | null; argTarget: number | null;
}> = {
    // (caster, casterPosition, target, ability...) -> Fix64  : l'utilite PAR CIBLE
    CalculateCustomUtility: { kind: "fix64", argCaster: 1, argTarget: 3 },
    // (target) -> Fix64 | (targetEntities) -> Fix64
    GetTargetUtility: { kind: "fix64", argCaster: null, argTarget: 1 },
    // (caster, casterPosition, abilityState) -> Fix64
    CalculateCasterPositionUtility: { kind: "fix64", argCaster: 1, argTarget: null },
    // (caster, casterPosition, abilityState) -> Bucket<UnitAction>
    EvaluateNonComparable: { kind: "bucket", argCaster: 1, argTarget: null },
};

interface UtilityCall {
    seq: number;
    /** La classe de playbook REELLEMENT ancree (jamais deduite d'un id d'ability). */
    playbook: string;
    method: string;
    /** `Entity+0x10`. `null` = non lisible ou absent de la signature — jamais fabrique. */
    casterId: number | null;
    targetId: number | null;
    /** Pour les methodes `Fix64` : l'utilite rendue, brute (base 10, exacte) et convertie. */
    utilityRaw: string | null;
    utility: number | null;
    /** Pour `EvaluateNonComparable` : le bucket rendu, decode SOUS-BUCKETS COMPRIS. */
    bucket: DecodedBucket | null;
    /** L'action que `Bucket$$ChooseAction` retiendrait (mirror en lecture pure). */
    chosenUtility: number | null;
    /** Nombre TOTAL d'actions dans l'arbre. `0` est ici une vraie vacuite — contrairement a
     *  « `best` est nul », qui ne prouve rien sur la voie a strategies multiples. */
    actionCount: number | null;
}

const RING_MAX = 600;

const trace = {
    armed: false,
    listeners: [] as InvocationListener[],
    calls: [] as UtilityCall[],
    seq: 0,
    armedAnchors: [] as string[],
    diag: {
        fires: 0, dropped: 0,
        entityReadFailed: 0, bucketDecodeFailed: 0,
        /** Fires par methode — c'est CE compteur qui tranchera le cout reel a la fenetre. */
        byMethod: {} as Record<string, number>,
    },
};

/** Un `NativePointer` de registre -> `Int64` SIGNE.
 *
 *  ⚠ `new Int64(p.toString())` SATURE : `NativePointer.toString()` rend l'hexa NON SIGNE, que
 *  `Int64` parse au-dela de `Int64.MaxValue` et rabat dessus. Mesure `#419-r7` : 100 % des cles
 *  d'un capteur voisin rendaient `9223372036854775807`, et deux regimes distincts se lisaient
 *  IDENTIQUES. Le detour par la memoire reinterprete les 64 bits en complement a deux. */
const rawBuf = Memory.alloc(8);
function toInt64(p: NativePointer): Int64 {
    rawBuf.writePointer(p);
    return rawBuf.readS64();
}

function readEntityId(p: NativePointer | undefined): number | null {
    if (!p || p.isNull()) return null;
    try { return p.add(0x10).readS32(); } catch { return null; }
}

/** Balaye les images UNE fois et collecte les classes de playbook et leurs methodes d'utilite.
 *  Un `findClassAnywhere` par classe relancerait un scan complet a chaque appel (163 scans) ;
 *  ce balayage unique rend le meme resultat pour le cout d'un seul. Aucun heap scan : on parcourt
 *  les metadonnees d'images, jamais la memoire du processus. */
function scanPlaybooks(): Map<string, { klass: NativePointer; methods: string[] }> {
    const out = new Map<string, { klass: NativePointer; methods: string[] }>();
    const domain = domain_get() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = domain_get_assemblies(domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();
    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(i * Process.pointerSize).readPointer();
        const image = assembly_get_image(assembly) as NativePointer;
        const cc = image_get_class_count(image) as number;
        for (let j = 0; j < cc; j++) {
            const k = image_get_class(image, j) as NativePointer;
            if (k.isNull()) continue;
            let ns: string;
            try { ns = s(class_get_namespace(k) as NativePointer); } catch { continue; }
            if (PLAYBOOK_NAMESPACES.indexOf(ns) < 0) continue;
            const name = s(class_get_name(k) as NativePointer);
            const methods: string[] = [];
            for (const m of Object.keys(ANCHORS)) {
                const mi = findMethod(k, m);
                if (mi && !mi.ptr.isNull()) methods.push(m);
            }
            if (methods.length > 0) out.set(name, { klass: k, methods });
        }
    }
    return out;
}

export function registerPlaybookUtilityTrace(ctx: Ctx): void {
    /** `playbookUtilityTrace` — arme / liste / lit / desarme.
     *
     *  body: { action: "arm" | "list" | "read" | "status" | "disarm",
     *          playbooks?: string[], all?: boolean, clear?: boolean } */
    ctx.rpc.playbookUtilityTrace = (
        body?: {
            action?: string; playbooks?: string[]; all?: boolean; clear?: boolean;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        const action = body?.action ?? "read";

        if (action === "disarm") {
            for (const l of trace.listeners) { try { l.detach(); } catch { /* */ } }
            trace.listeners = [];
            trace.armed = false;
            trace.armedAnchors = [];
            return { ok: true, armed: false };
        }

        if (action === "list") {
            const found = scanPlaybooks();
            const rows = [...found.entries()]
                .map(([name, v]) => ({ playbook: name, methods: v.methods }))
                .sort((a, b) => a.playbook.localeCompare(b.playbook));
            return {
                ok: true,
                // Compte DERIVE du runtime, jamais d'une table figee.
                playbookCount: rows.length,
                anchorCount: rows.reduce((n, r) => n + r.methods.length, 0),
                bucketLayout: bucketLayoutReport(),
                playbooks: rows,
            };
        }

        if (action === "arm") {
            if (trace.armed) {
                return { ok: true, armed: true, anchors: trace.armedAnchors,
                    note: "deja arme (aucun hook re-attache) — `disarm` d'abord pour changer "
                        + "la selection" };
            }
            const wanted = body?.playbooks ?? [];
            if (wanted.length === 0 && !body?.all) {
                return { ok: false, armed: false,
                    error: "rien a armer : donner `playbooks:[...]` (voir `action:\"list\"`) ou "
                        + "`all:true`. On REFUSE d'armer par defaut — le choix des ADRESSES est "
                        + "le seul filtre qui agisse avant le trampoline." };
            }
            const found = scanPlaybooks();
            const missing = wanted.filter((w) => !found.has(w));
            const targets = body?.all ? [...found.keys()] : wanted.filter((w) => found.has(w));
            if (targets.length === 0) {
                return { ok: false, armed: false, missing,
                    error: "aucun playbook demande n'a ete resolu — AUCUN hook pose" };
            }
            const anchors: string[] = [];
            for (const name of targets) {
                const entry = found.get(name);
                if (!entry) continue;
                for (const methName of entry.methods) {
                    const spec = ANCHORS[methName];
                    const mi = findMethod(entry.klass, methName);
                    if (!mi || mi.ptr.isNull()) continue;
                    const label = name + "$$" + methName;
                    anchors.push(label);
                    trace.listeners.push(Interceptor.attach(mi.ptr, {
                        onEnter(this: InvocationContext, args) {
                            trace.diag.fires++;
                            trace.diag.byMethod[methName] =
                                (trace.diag.byMethod[methName] ?? 0) + 1;
                            const row: UtilityCall = {
                                seq: ++trace.seq,
                                playbook: name, method: methName,
                                casterId: spec.argCaster !== null
                                    ? readEntityId(args[spec.argCaster]) : null,
                                targetId: spec.argTarget !== null
                                    ? readEntityId(args[spec.argTarget]) : null,
                                utilityRaw: null, utility: null,
                                bucket: null, chosenUtility: null, actionCount: null,
                            };
                            if (spec.argCaster !== null && row.casterId === null) {
                                trace.diag.entityReadFailed++;
                            }
                            (this as { _row?: UtilityCall })._row = row;
                        },
                        onLeave(this: InvocationContext, retval) {
                            const row = (this as { _row?: UtilityCall })._row;
                            if (!row) return;
                            if (spec.kind === "fix64") {
                                // `Fix64` est une struct de 8 octets => rendue dans RAX, donc
                                // `retval` EST la valeur brute. On garde la base 10 : la
                                // conversion Q32.32 perd des bits de poids faible sur un `double`,
                                // et « identique / different » doit se trancher sur l'entier exact.
                                const raw = toInt64(retval as NativePointer);
                                row.utilityRaw = raw.toString();
                                row.utility = fix64ToNumber(raw);
                            } else {
                                try {
                                    const b = decodeBucket(retval as NativePointer);
                                    row.bucket = b;
                                    if (b) {
                                        const c = chooseAction(b);
                                        row.chosenUtility = c ? c.utility : null;
                                        row.actionCount = countActions(b);
                                    } else { trace.diag.bucketDecodeFailed++; }
                                } catch { trace.diag.bucketDecodeFailed++; }
                            }
                            trace.calls.push(row);
                            while (trace.calls.length > RING_MAX) {
                                trace.calls.shift(); trace.diag.dropped++;
                            }
                        },
                    }));
                }
            }
            if (trace.listeners.length === 0) {
                return { ok: false, armed: false, missing,
                    error: "resolution vide — AUCUN hook pose" };
            }
            trace.armed = true;
            trace.armedAnchors = anchors;
            return {
                ok: true, armed: true,
                anchorCount: anchors.length, anchors, missing,
                bucketLayout: bucketLayoutReport(),
            };
        }

        const out = {
            ok: true, armed: trace.armed,
            anchors: trace.armedAnchors,
            diag: { ...trace.diag, byMethod: { ...trace.diag.byMethod } },
            callCount: trace.calls.length,
            calls: action === "status" ? [] : trace.calls,
        };
        if (body?.clear) {
            trace.calls = [];
            trace.diag = { fires: 0, dropped: 0, entityReadFailed: 0,
                bucketDecodeFailed: 0, byMethod: {} };
        }
        return out;
    });
}
