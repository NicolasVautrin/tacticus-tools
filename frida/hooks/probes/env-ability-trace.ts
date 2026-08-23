/** `#10046` (volet BOUCLIER) — CAPTEUR : les QUATRE ÉTAGES d'une ability d'environnement.
 *
 *  ⚠ **INERTE tant que le bundle n'est pas rebuildé + réinjecté.** Le `register` n'arme AUCUN
 *  hook : il n'expose qu'un RPC. `arm` pose les `Interceptor`, `disarm` les retire.
 *
 *  ## Pourquoi ce capteur existe
 *
 *  `EnvStartProtection` (1280) a produit **7 boucliers de 500** en bataille réelle avec l'ordre
 *  de tours par défaut, puis **zéro, des deux côtés** une fois `BC.Player.TurnOrder` mis à
 *  `[12,11,13]`. Et sur un runner, l'ability pré-installée dans la seed BC n'a **rien** produit
 *  non plus. Trois régimes, trois résultats, et **aucun moyen de dire à quel étage ça casse** :
 *
 *    - installée dans le réceptacle ?   -> `BC.EnvironmentAbilities` (déjà mesurable, `--etat`)
 *    - l'opération d'installation A-T-ELLE TOURNÉ ?          -> étage 1 ci-dessous
 *    - un PORTEUR a-t-il été créé pour elle ?                -> étage 2
 *    - ses abilities ont-elles été CÂBLÉES ?                 -> étage 3
 *    - un bouclier a-t-il été RÉELLEMENT posé, et sur qui ?  -> étage 4
 *
 *  « Pas de bouclier à l'écran » ne distingue aucun de ces cinq états. Ce capteur, si.
 *
 *  ## Les quatre ancres, et ce que chacune tranche
 *
 *  | étage | symbole | ce qu'un ZÉRO signifie |
 *  |---|---|---|
 *  | 1 | `IdunBattle.Operations.AddEnvironmentAbilityOperation$$Execute` | le réceptacle n'est JAMAIS consommé par ce mode -- le banc est invalide, pas la mécanique |
 *  | 2 | `IdunBattle.Operations.AddEnvironmentAbilityOperation$$CreateEntity` | aucun PORTEUR ; les abilities d'environnement en exigent un (cf. `BattleConfigBuilder$$GetAdditionalPlayersRequiredByEnvironmentAbilities`) |
 *  | 3 | `IdunBattle.Operations.AddEnvironmentAbilityOperation$$InitializeAbilities` | porteur créé mais rien de câblé |
 *  | 4 | `IdunBattle.Operations.CreateShieldOperation$$Execute` | tout est câblé et le déclencheur n'a pas mordu -- LÀ seulement l'ordre des tours est en cause |
 *
 *  ⚠ **L'étage 4 est la SEULE vérité terrain sur « un bouclier a été posé ».** `CreateShield` de
 *  `DSLBehaviors` n'est PAS ancré ici : il construit le NŒUD de l'arbre DSL à la fabrication de
 *  l'ability, pas au tir. Le confondre ferait lire « le bouclier est posé » alors que seule sa
 *  DESCRIPTION existe — exactement le genre de faux vert que ce dépôt paie cher.
 *
 *  ⚠ **L'étage 4 est PARTAGÉ** : tout bouclier de la bataille y passe (`AnvilShield` d'Arjac,
 *  etc.), pas seulement le nôtre. On compte donc les tirs **sans les attribuer** à
 *  `EnvStartProtection` — l'attribution demanderait de lire l'ability source, et une attribution
 *  fausse serait pire qu'un simple compte. Le discriminant utilisable est le MOMENT : un tir
 *  entre l'étage 3 et le premier tour est le nôtre.
 *
 *  Read-only : aucune valeur réécrite, aucun `Interceptor.replace`. La résolution est rendue à
 *  l'armement — un capteur qui ne peut pas s'attacher doit le dire LÀ, pas se taire jusqu'à
 *  rendre zéro tir.
 */
import { findClassAnywhere, findMethod } from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface Tir {
    seq: number;
    etage: 1 | 2 | 3 | 4;
    quoi: string;
    /** Pour l'étage 4 : le pointeur de l'opération, seul repère stable sans attribution. */
    ptr?: string;
}

const RING_MAX = 300;

const trace = {
    armed: false,
    listeners: [] as InvocationListener[],
    tirs: [] as Tir[],
    seq: 0,
    diag: {
        installExecute: 0, createEntity: 0, initializeAbilities: 0, createShield: 0,
        dropped: 0,
    },
};

export function registerEnvAbilityTrace(ctx: Ctx): void {
    ctx.rpc.envAbilityTrace = (
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
                return { ok: true, armed: true, note: "déjà armé (aucun hook ré-attaché)" };
            }
            const kAdd = findClassAnywhere(
                "IdunBattle.Operations", "AddEnvironmentAbilityOperation");
            const kShield = findClassAnywhere("IdunBattle.Operations", "CreateShieldOperation");
            const mExec = kAdd ? findMethod(kAdd, "Execute") : null;
            const mEntity = kAdd ? findMethod(kAdd, "CreateEntity") : null;
            const mInit = kAdd ? findMethod(kAdd, "InitializeAbilities") : null;
            const mShield = kShield ? findMethod(kShield, "Execute") : null;

            const resolution = {
                addEnvironmentAbilityOperation: !!kAdd,
                execute: !!mExec, createEntity: !!mEntity, initializeAbilities: !!mInit,
                createShieldOperation: !!kShield, createShieldExecute: !!mShield,
            };
            // L'étage 1 et l'étage 4 portent les deux verdicts qui comptent : « le réceptacle
            // est-il consommé ? » et « un bouclier est-il posé ? ». Sans l'un des deux, le
            // capteur ne peut pas conclure -- on REFUSE plutôt que de rendre des zéros muets.
            if (!mExec) {
                return { ok: false, armed: false, resolution,
                    error: "`AddEnvironmentAbilityOperation$$Execute` non résolu : sans lui, un "
                        + "« zéro bouclier » ne distingue pas « réceptacle jamais consommé » de "
                        + "« déclencheur qui n'a pas mordu » — soit les deux seules hypothèses "
                        + "en jeu." };
            }
            if (!mShield) {
                return { ok: false, armed: false, resolution,
                    error: "`CreateShieldOperation$$Execute` non résolu : c'est la SEULE vérité "
                        + "terrain sur « un bouclier a été posé ». S'armer sans elle rendrait un "
                        + "capteur qui décrit le câblage sans jamais voir le résultat." };
            }

            const ancrer = (
                mi: { ptr: NativePointer }, etage: 1 | 2 | 3 | 4, quoi: string,
                compteur: keyof typeof trace.diag,
            ) => {
                trace.listeners.push(Interceptor.attach(mi.ptr, {
                    onEnter(this: InvocationContext, args) {
                        (trace.diag[compteur] as number)++;
                        const t: Tir = { seq: ++trace.seq, etage, quoi };
                        if (etage === 4) {
                            try { t.ptr = args[0].toString(); } catch { /* laisse absent */ }
                        }
                        trace.tirs.push(t);
                        while (trace.tirs.length > RING_MAX) {
                            trace.tirs.shift(); trace.diag.dropped++;
                        }
                    },
                }));
            };
            ancrer(mExec, 1, "AddEnvironmentAbilityOperation.Execute", "installExecute");
            if (mEntity) ancrer(mEntity, 2, "…CreateEntity", "createEntity");
            if (mInit) ancrer(mInit, 3, "…InitializeAbilities", "initializeAbilities");
            ancrer(mShield, 4, "CreateShieldOperation.Execute", "createShield");

            trace.armed = true;
            return { ok: true, armed: true, resolution };
        }

        const out = {
            ok: true, armed: trace.armed,
            diag: { ...trace.diag },
            tirCount: trace.tirs.length,
            tirs: action === "status" ? [] : trace.tirs,
        };
        if (body?.clear) {
            trace.tirs = [];
            trace.diag = {
                installExecute: 0, createEntity: 0, initializeAbilities: 0, createShield: 0,
                dropped: 0,
            };
        }
        return out;
    });
}
