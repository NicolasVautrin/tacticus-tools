/** `#10046` — CAPTEUR : les QUATRE sorties muettes de la pose des unites predefinies.
 *
 *  ⚠ **INERTE tant que le bundle n'est pas rebuilde + reinjecte.** Le `register` n'arme AUCUN
 *  hook : il n'expose qu'un RPC. `arm` pose les `Interceptor`, `disarm` les retire.
 *
 *  ## Ce que le residu ne peut pas mesurer sans lui
 *
 *  `docs/rl/case-10046-pose-des-unites-predefinies.md` ferme la CHAINE mais pas l'ETAPE qui
 *  echoue : le camp adverse ne spawne pas quand les `TeamId` sont inverses, et le deroule a la
 *  main dit que ca devrait marcher. Le sous-systeme **ne leve jamais** — il n'y a donc rien a
 *  voir, par construction. Ce capteur rend les quatre points de decision OBSERVABLES.
 *
 *  Les quatre sorties, relues au decompile de
 *  `IdunBattle.Operations.SetupGameOperation$$AddPredefinedUnits` :
 *
 *    1. `StateExtensions$$GetTeam` rend un `Nullable` VIDE      -> escouade entierement passee
 *    2. `SpawnPointSetConfiguration$$GroupForPlayer` rend null  -> escouade entierement passee
 *    3. `i >= groupe.SpawnPoints.Count`                         -> reste de l'escouade abandonne
 *    4. `SetupGameOperation$$IsPredefinedUnitDisabledByModifiers` rend vrai -> unite sautee
 *
 *  ⚠ La n°4 ne figure PAS dans le case-doc (ajoutee ici) et elle est **orthogonale a l'equipe** :
 *  son corps ne lit que la liste de modificateurs indexee par `unitId`, jamais un `TeamId`. Elle
 *  est donc capturee pour ne pas etre confondue avec les trois autres, pas comme suspecte.
 *
 *  ⚠ La n°1 est, a la lecture, **STRUCTURELLEMENT INATTEIGNABLE** :
 *  `StateExtensions.u003CGetTeamPlayersu003Ed__39$$MoveNext` filtre sur `PlayerComponent+0x24`,
 *  soit le MEME champ dont `GetTeam` tire le `teamId` qu'il passe. Un joueur est donc toujours
 *  present dans l'enumeration de sa propre equipe. On l'ancre quand meme : c'est exactement le
 *  genre de deduction qu'une mesure doit confirmer plutot qu'un capteur doit presupposer.
 *
 *  ## Le piege d'ancrage : `GetTeam` a un PREMIER ARGUMENT CACHE
 *
 *  Il rend un `Nullable<ValueTuple<TeamId,TeamPlayerIndex>>` — 12 octets, donc **retourne par
 *  pointeur cache (sret)** sur Win64. Le profil REEL est :
 *
 *      GetTeam(bufferRetour /*RCX*\/, state /*RDX*\/, player /*R8*\/)
 *
 *  Ghidra nomme ses parametres a cote de la plaque : son `state` EST le buffer, son `player` EST
 *  l'etat, et le joueur reel n'apparait que comme un `in_R8` non declare. Lire `args[1]` comme
 *  « le joueur » lirait donc l'ETAT, silencieusement.
 *
 *  ⚠ **La disposition du buffer a ete MESUREE, apres qu'une lecture du decompile l'a rendue
 *  FAUSSE de 4 octets.** Le premier jet placait le `ValueTuple` en tete et `hasValue` a `+0x8` —
 *  c'est la disposition C# `{ T value; bool hasValue; }`. IL2CPP emet l'INVERSE :
 *
 *      buf+0x0  hasValue (int32)   buf+0x4  TeamId (int32)   buf+0x8  TeamPlayerIndex/rang
 *
 *  La faute etait INDETECTABLE au decompile — les deux lectures sont coherentes avec le code —
 *  et elle se presentait comme un resultat CREDIBLE : `hasValue` sortait FAUX 5 fois sur 5, soit
 *  exactement la sortie muette n°1 qu'on cherchait. Ce qui l'a tuee est un SECOND CANAL : les
 *  arguments que `GroupForPlayer` recoit juste apres sont `(teamId, rang)`, et ils coincidaient
 *  5/5 avec `buf+0x4`/`buf+0x8`, jamais avec `buf+0x0`. Corollaire de methode : un capteur qui
 *  ne se recoupe avec rien peut confirmer l'hypothese qui l'a fait naitre.
 *
 *  ## Portee
 *
 *  `GetTeam` et `GroupForPlayer` ont d'autres consommateurs que la pose. On tient donc une
 *  profondeur PAR THREAD posee par le bracket `AddPredefinedUnits`, et chaque appel est publie
 *  avec `inSetup` — les appels hors pose sont COMPTES, jamais melanges ni jetes.
 *
 *  Read-only : aucune valeur reecrite, aucun `Interceptor.replace`. La resolution est rendue au
 *  moment de l'armement — un capteur qui ne peut pas s'attacher doit le dire LA, pas se taire
 *  jusqu'a rendre zero fire.
 */
import {
    findClassAnywhere, findMethod, findMethodByParamClasses, findMethodByParamCount,
    readIl2cppString,
} from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

/** Un groupe de spawn, tel que lu dans la table du set. */
interface GroupRow {
    /** `groupe+0x10` — la cle que `GroupForPlayer` cherche par `FirstOrDefault`. */
    teamWithPlayerIndex: number | null;
    /** `groupe+0x18 -> +0x18` — la capacite, qui borne la sortie n°3. */
    spawnPointCount: number | null;
}

interface Event {
    seq: number;
    kind: "setupEnter" | "setupLeave" | "getTeam" | "groupForPlayer" | "disabledByModifiers"
        | "addUnit";
    /** Profondeur du bracket `AddPredefinedUnits` sur CE thread au moment de l'appel. */
    inSetup: boolean;

    // --- getTeam ---
    /** Surcharge ancree : "entity" ou "playerId". Les deux ont la meme arite. */
    overload?: string;
    /** Lu dans le buffer sret a l'`onLeave`. `null` = buffer illisible, jamais fabrique. */
    teamId?: number | null;
    rang?: number | null;
    /** `false` ici EST la sortie muette n°1. */
    hasValue?: boolean | null;

    // --- groupForPlayer ---
    /** Les deux entrees, telles que passees (registres, valeurs entieres). */
    argTeamId?: number;
    argPlayerNr?: number;
    /** L'index calcule par la table 2-D, re-derive ici pour confronter le natif au case-doc. */
    indexAttendu?: number | null;
    /** `true` = le natif a rendu null -> sortie muette n°2. */
    renduNull?: boolean;
    groupe?: GroupRow;

    // --- disabledByModifiers ---
    /** `true` = sortie muette n°4 (unite sautee, compteur seul incremente). */
    disabled?: boolean;

    // --- addUnit : le PLACEMENT lui-meme, en aval de la pose ---
    /** L'`unitId` que `AreTilesDisallowedAndLog` recoit. `null` = pas lu. */
    unitId?: string | null;
    /** `true` = tuile hors du jeu autorise OU **deja occupee** (`TileContentComponent$$IsFilled`).
     *  Les deux branches rendent vrai ; seul le log natif les distingue. */
    disallowed?: boolean | null;
    reserved?: boolean | null;
    inFog?: boolean | null;
    pendingDraft?: boolean | null;
    /** `true` = `AddUnitOperation$$Execute` a rendu NULL : l'unite n'existe pas. */
    executeNull?: boolean | null;

    // --- setupEnter ---
    /** La table COMPLETE des groupes du set, lue a l'entree de la pose. C'est la verite terrain
     *  contre laquelle `indexAttendu` se confronte. `null` = disposition non reconnue. */
    groupes?: GroupRow[] | null;
}

const RING_MAX = 400;

const trace = {
    armed: false,
    listeners: [] as InvocationListener[],
    events: [] as Event[],
    seq: 0,
    diag: {
        setupFires: 0,
        getTeamFires: 0, getTeamHorsPose: 0, getTeamVide: 0, getTeamBufferIllisible: 0,
        groupFires: 0, groupHorsPose: 0, groupNull: 0,
        modifierFires: 0, modifierDisabled: 0,
        addUnitFires: 0, addUnitNull: 0,
        tilesDisallowed: 0, tilesReserved: 0, tilesInFog: 0, tilesPendingDraft: 0,
        dropped: 0,
    },
};

/** Profondeur du bracket `AddPredefinedUnits`, PAR THREAD. */
const depth: Record<number, number> = {};

/** La ligne `addUnit` en cours de remplissage, PAR THREAD. Les gates (`AreTilesDisallowedAndLog`
 *  et les trois predicats) sont appeles DEPUIS `AddUnitOperation$$Execute` : on les attribue a
 *  l'`Execute` englobant plutot que d'emettre des evenements orphelins qu'aucun `unitId` ne
 *  nommerait. Un gate vu HORS `Execute` est compte, jamais attribue. */
const addUnitEnCours: Record<number, Event | undefined> = {};
/** Profondeur d'`Execute` par thread : `AddUnitOperation` peut en imbriquer (unites clonees). */
const addUnitDepth: Record<number, number> = {};

function pousser(e: Event): void {
    trace.events.push(e);
    while (trace.events.length > RING_MAX) { trace.events.shift(); trace.diag.dropped++; }
}

/** La table 2-D de `GroupForPlayer`, re-derivee ICI pour confronter le natif au case-doc.
 *  `null` = le natif leverait `ArgumentOutOfRangeException`. */
function indexAttendu(teamId: number, playerNr: number): number | null {
    if (teamId === 0) return 6;
    if (teamId === 1) return playerNr !== 0 ? 2 : 0;
    if (teamId === 2) return playerNr !== 0 ? 3 : 1;
    if (teamId === 3) return playerNr !== 0 ? 5 : 4;
    return null;
}

/** Un `SpawnPointGroupConfiguration*` -> ses deux champs utiles.
 *  `null` partout plutot qu'un zero : un champ illisible n'est pas un champ a zero. */
function lireGroupe(g: NativePointer): GroupRow {
    const row: GroupRow = { teamWithPlayerIndex: null, spawnPointCount: null };
    try { row.teamWithPlayerIndex = g.add(0x10).readS32(); } catch { /* laisse null */ }
    try {
        const pts = g.add(0x18).readPointer();
        if (!pts.isNull()) {
            const n = pts.add(0x18).readS32();
            // Garde de VRAISEMBLANCE, pas garde de signe : un pointeur mal interprete rend
            // souvent un entier positif enorme, qu'un test `< 0` laisserait passer.
            if (n >= 0 && n <= 4096) row.spawnPointCount = n;
        }
    } catch { /* laisse null */ }
    return row;
}

/** `set+0x10` = les groupes (`List<SpawnPointGroupConfiguration>`).
 *  Disposition IL2CPP standard : `+0x10` tableau, `+0x18` taille ; element i a `array+0x20+i*8`.
 *  Rend `null` si la disposition n'est pas reconnue — on ne devine pas une table. */
function lireGroupes(set: NativePointer): GroupRow[] | null {
    try {
        const liste = set.add(0x10).readPointer();
        if (liste.isNull()) return null;
        const arr = liste.add(0x10).readPointer();
        const n = liste.add(0x18).readS32();
        if (arr.isNull() || n < 0 || n > 64) return null;
        const out: GroupRow[] = [];
        for (let i = 0; i < n; i++) {
            const g = arr.add(0x20 + i * 8).readPointer();
            out.push(g.isNull() ? { teamWithPlayerIndex: null, spawnPointCount: null }
                : lireGroupe(g));
        }
        return out;
    } catch { return null; }
}

export function registerSetupSpawnTrace(ctx: Ctx): void {
    ctx.rpc.setupSpawnTrace = (
        body?: { action?: string; clear?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        const action = body?.action ?? "read";

        if (action === "disarm") {
            for (const l of trace.listeners) { try { l.detach(); } catch { /* */ } }
            trace.listeners = [];
            trace.armed = false;
            return { ok: true, armed: false };
        }

        if (action === "arm") {
            if (trace.armed) {
                return { ok: true, armed: true, note: "deja arme (aucun hook re-attache)" };
            }
            const setupCls = findClassAnywhere("IdunBattle.Operations", "SetupGameOperation");
            const stateExtCls = findClassAnywhere("IdunBattle.Entities", "StateExtensions");
            const setCls = findClassAnywhere(
                "IdunBattle.Configuration", "SpawnPointSetConfiguration");

            const mSetup = setupCls
                ? findMethodByParamCount(setupCls, "AddPredefinedUnits", 1) : null;
            const mDisabled = setupCls
                ? findMethodByParamCount(setupCls, "IsPredefinedUnitDisabledByModifiers", 2) : null;
            // Les DEUX surcharges de `GetTeam` ont la meme arite -> on desambigue par le TYPE.
            const mTeamEntity = stateExtCls
                ? findMethodByParamClasses(stateExtCls, "GetTeam", ["IMatchState", "IEntity"])
                : null;
            const mTeamPlayerId = stateExtCls
                ? findMethodByParamClasses(stateExtCls, "GetTeam", ["IMatchState", "PlayerId"])
                : null;
            const mGroup = setCls ? findMethodByParamCount(setCls, "GroupForPlayer", 2) : null;

            // --- le PLACEMENT, en aval de la pose ---
            const addCls = findClassAnywhere("IdunBattle.Operations", "AddUnitOperation");
            const mExec = addCls ? findMethod(addCls, "Execute") : null;
            const mDisallowed = addCls
                ? findMethodByParamCount(addCls, "AreTilesDisallowedAndLog", 6) : null;
            const mReserved = addCls ? findMethod(addCls, "TilesAreReserved") : null;
            const mInFog = addCls ? findMethod(addCls, "TilesAreInFog") : null;
            const mPending = addCls ? findMethod(addCls, "TilesArePendingDrafting") : null;

            const resolution = {
                setupGameOperation: !!setupCls,
                addPredefinedUnits: !!mSetup,
                isPredefinedUnitDisabledByModifiers: !!mDisabled,
                stateExtensions: !!stateExtCls,
                getTeamEntity: !!mTeamEntity,
                getTeamPlayerId: !!mTeamPlayerId,
                spawnPointSetConfiguration: !!setCls,
                groupForPlayer: !!mGroup,
                addUnitOperation: !!addCls,
                addUnitExecute: !!mExec,
                areTilesDisallowedAndLog: !!mDisallowed,
                tilesAreReserved: !!mReserved,
                tilesAreInFog: !!mInFog,
                tilesArePendingDrafting: !!mPending,
            };

            // Les deux ancres SANS lesquelles le capteur ne repondrait a rien : le bracket (qui
            // donne la portee) et `GroupForPlayer` (la seule sortie muette que la lecture n'a pas
            // pu ecarter). On REFUSE de s'armer a moitie plutot que de rendre des zeros.
            if (!mSetup) {
                return { ok: false, armed: false, resolution,
                    error: "`SetupGameOperation$$AddPredefinedUnits` non resolu : sans le bracket, "
                        + "tout appel serait publie `inSetup:false` et le capteur ne dirait rien "
                        + "de la pose." };
            }
            if (!mGroup) {
                return { ok: false, armed: false, resolution,
                    error: "`SpawnPointSetConfiguration$$GroupForPlayer` non resolu. C'est la "
                        + "sortie muette n°2, la seule que la lecture n'a pas su ecarter : "
                        + "s'armer sans elle rendrait un capteur qui ne peut pas conclure." };
            }

            // --- bracket de portee ---
            trace.listeners.push(Interceptor.attach(mSetup.ptr, {
                onEnter(this: InvocationContext, args) {
                    trace.diag.setupFires++;
                    const t = this.threadId;
                    depth[t] = (depth[t] ?? 0) + 1;
                    let groupes: GroupRow[] | null = null;
                    try {
                        const set = args[1];
                        if (set && !set.isNull()) groupes = lireGroupes(set);
                    } catch { /* laisse null */ }
                    pousser({ seq: ++trace.seq, kind: "setupEnter", inSetup: true, groupes });
                },
                onLeave(this: InvocationContext) {
                    const t = this.threadId;
                    depth[t] = Math.max(0, (depth[t] ?? 1) - 1);
                    pousser({ seq: ++trace.seq, kind: "setupLeave", inSetup: depth[t] > 0 });
                },
            }));

            // --- sortie n°1 : le Nullable de GetTeam ---
            const attacherGetTeam = (mi: { ptr: NativePointer }, overload: string) => {
                trace.listeners.push(Interceptor.attach(mi.ptr, {
                    onEnter(this: InvocationContext, args) {
                        // `args[0]` EST le buffer sret : il n'est ecrit qu'a la sortie, donc on le
                        // MEMORISE ici et on le relit a l'`onLeave`.
                        (this as { _buf?: NativePointer })._buf = args[0];
                    },
                    onLeave(this: InvocationContext) {
                        trace.diag.getTeamFires++;
                        const t = this.threadId;
                        const dedans = (depth[t] ?? 0) > 0;
                        if (!dedans) trace.diag.getTeamHorsPose++;
                        const buf = (this as { _buf?: NativePointer })._buf;
                        let teamId: number | null = null;
                        let rang: number | null = null;
                        let hasValue: boolean | null = null;
                        try {
                            if (buf && !buf.isNull()) {
                                // Ordre MESURE (cf. l'avertissement en tete) : hasValue d'abord.
                                hasValue = (buf.readU8() & 1) === 1;
                                teamId = buf.add(4).readS32();
                                rang = buf.add(8).readS32();
                            }
                        } catch { /* laisse null */ }
                        if (hasValue === null) trace.diag.getTeamBufferIllisible++;
                        else if (!hasValue) trace.diag.getTeamVide++;
                        pousser({
                            seq: ++trace.seq, kind: "getTeam", inSetup: dedans,
                            overload, teamId, rang, hasValue,
                        });
                    },
                }));
            };
            if (mTeamEntity) attacherGetTeam(mTeamEntity, "entity");
            if (mTeamPlayerId) attacherGetTeam(mTeamPlayerId, "playerId");

            // --- sortie n°2 : GroupForPlayer rend null ---
            trace.listeners.push(Interceptor.attach(mGroup.ptr, {
                onEnter(this: InvocationContext, args) {
                    // `teamId` et `playerNr` sont des ValueType d'un int, passes en registre.
                    const self = this as { _a?: number; _b?: number };
                    self._a = args[1].toInt32();
                    self._b = args[2].toInt32();
                },
                onLeave(this: InvocationContext, retval) {
                    trace.diag.groupFires++;
                    const t = this.threadId;
                    const dedans = (depth[t] ?? 0) > 0;
                    if (!dedans) trace.diag.groupHorsPose++;
                    const self = this as { _a?: number; _b?: number };
                    const a = self._a ?? 0;
                    const b = self._b ?? 0;
                    const nul = retval.isNull();
                    if (nul) trace.diag.groupNull++;
                    pousser({
                        seq: ++trace.seq, kind: "groupForPlayer", inSetup: dedans,
                        argTeamId: a, argPlayerNr: b, indexAttendu: indexAttendu(a, b),
                        renduNull: nul,
                        groupe: nul ? undefined : lireGroupe(retval as NativePointer),
                    });
                },
            }));

            // --- sortie n°4 : ecartee par les modificateurs ---
            if (mDisabled) {
                trace.listeners.push(Interceptor.attach(mDisabled.ptr, {
                    onLeave(this: InvocationContext, retval) {
                        trace.diag.modifierFires++;
                        const off = (retval.toInt32() & 1) === 1;
                        if (off) trace.diag.modifierDisabled++;
                        pousser({
                            seq: ++trace.seq, kind: "disabledByModifiers",
                            inSetup: (depth[this.threadId] ?? 0) > 0, disabled: off,
                        });
                    },
                }));
            }

            // --- sortie n°5 : le PLACEMENT refuse en aval de la pose ---
            // On bracket sur `Execute` pour que chaque verdict de gate porte un `unitId`. Les
            // quatre gates sont facultatives : le capteur reste utile sans elles, il dit
            // seulement moins. Ce qui NE serait pas acceptable, c'est de les croire absentes
            // sans le dire -- d'ou leur presence dans `resolution`.
            if (mExec) {
                trace.listeners.push(Interceptor.attach(mExec.ptr, {
                    onEnter(this: InvocationContext) {
                        const t = this.threadId;
                        addUnitDepth[t] = (addUnitDepth[t] ?? 0) + 1;
                        const row: Event = {
                            seq: ++trace.seq, kind: "addUnit",
                            inSetup: (depth[t] ?? 0) > 0,
                            unitId: null, disallowed: null, reserved: null, inFog: null,
                            pendingDraft: null, executeNull: null,
                        };
                        // Un `Execute` imbrique ne doit pas ecraser la ligne de l'externe.
                        if (addUnitDepth[t] === 1) addUnitEnCours[t] = row;
                        (this as { _row?: Event })._row = row;
                    },
                    onLeave(this: InvocationContext, retval) {
                        trace.diag.addUnitFires++;
                        const t = this.threadId;
                        addUnitDepth[t] = Math.max(0, (addUnitDepth[t] ?? 1) - 1);
                        if (addUnitDepth[t] === 0) addUnitEnCours[t] = undefined;
                        const row = (this as { _row?: Event })._row;
                        if (!row) return;
                        row.executeNull = retval.isNull();
                        if (row.executeNull) trace.diag.addUnitNull++;
                        pousser(row);
                    },
                }));
            }

            /** Ancre un gate booleen et ecrit son verdict dans la ligne `addUnit` du thread. */
            const attacherGate = (
                mi: { ptr: NativePointer }, champ: keyof Event, compteur: keyof typeof trace.diag,
            ) => {
                trace.listeners.push(Interceptor.attach(mi.ptr, {
                    onLeave(this: InvocationContext, retval) {
                        const vrai = (retval.toInt32() & 1) === 1;
                        if (vrai) (trace.diag[compteur] as number)++;
                        const row = addUnitEnCours[this.threadId];
                        // Hors `Execute` : compte, jamais attribue -- une ligne sans `unitId`
                        // ne nommerait rien.
                        if (row) (row as unknown as Record<string, unknown>)[champ] = vrai;
                    },
                }));
            };
            if (mDisallowed) {
                trace.listeners.push(Interceptor.attach(mDisallowed.ptr, {
                    onEnter(this: InvocationContext, args) {
                        const row = addUnitEnCours[this.threadId];
                        if (!row) return;
                        try { row.unitId = readIl2cppString(args[1]); } catch { /* laisse null */ }
                    },
                    onLeave(this: InvocationContext, retval) {
                        const vrai = (retval.toInt32() & 1) === 1;
                        if (vrai) trace.diag.tilesDisallowed++;
                        const row = addUnitEnCours[this.threadId];
                        if (row) row.disallowed = vrai;
                    },
                }));
            }
            if (mReserved) attacherGate(mReserved, "reserved", "tilesReserved");
            if (mInFog) attacherGate(mInFog, "inFog", "tilesInFog");
            if (mPending) attacherGate(mPending, "pendingDraft", "tilesPendingDraft");

            trace.armed = true;
            return { ok: true, armed: true, resolution };
        }

        const out = {
            ok: true, armed: trace.armed,
            diag: { ...trace.diag },
            eventCount: trace.events.length,
            events: action === "status" ? [] : trace.events,
        };
        if (body?.clear) {
            trace.events = [];
            trace.diag = {
                setupFires: 0,
                getTeamFires: 0, getTeamHorsPose: 0, getTeamVide: 0, getTeamBufferIllisible: 0,
                groupFires: 0, groupHorsPose: 0, groupNull: 0,
                modifierFires: 0, modifierDisabled: 0,
                addUnitFires: 0, addUnitNull: 0,
                tilesDisallowed: 0, tilesReserved: 0, tilesInFog: 0, tilesPendingDraft: 0,
                dropped: 0,
            };
        }
        return out;
    });
}
