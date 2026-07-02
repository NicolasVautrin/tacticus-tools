// Attribution des événements de trace diagnostique à un runner.
//
// Mécanisme : les RPCs qui PILOTENT une évaluation native (aiStepDryRun,
// aiPlayByUnit, aiPlayOrdered, aiDryRunAllUnits, playTurn, autoPlayRunner,
// aiPredict, aiAttackRank, decisionView, exposureView) posent EXPLICITEMENT
// l'origine juste après avoir résolu leur runner, DANS leur job
// queueOnMainThread ; la main-pump la remet à null à la fin de CHAQUE job
// drainé (drainPending, cf. runtime/main-pump.ts). Comme les jobs sont
// sérialisés sur le main thread Unity et que l'évaluation native
// (playbook / prédiction) s'exécute SYNCHRONEMENT dans le job qui l'invoque,
// tout hook de trace qui fire pendant la fenêtre appartient à CETTE origine
// — attribution exacte par construction. origin === null ⇒ hors fenêtre
// (IA du jeu LIVE, ou chemin non instrumenté).
//
// ⚠ Le set doit rester EXPLICITE par-RPC — PAS de side effect ambiant dans
// getRunner : celui-ci est aussi appelé depuis des callbacks de hooks
// (recorder, hors job) et des RPCs non-queués (disposeRunner, thread RPC,
// qui peut s'exécuter PENDANT un job car Frida relâche le lock JS autour
// des invocations natives) → un set ambiant produirait des MAUVAISES
// attributions. Avec le set explicite, le mode de défaillance d'un chemin
// oublié est un tag null (non attribué), jamais une attribution fausse.
//
// Consommateurs : scorer-damage-trace / ai-utility-trace / bucket-audit
// taguent chaque event avec `originRunnerId` (même convention de nommage
// que le recorder) ; leurs dumps acceptent un filtre `runnerId`.

let current: number | null = null;

export function setTraceOrigin(runnerId: number): void { current = runnerId; }
export function clearTraceOrigin(): void { current = null; }
export function getTraceOrigin(): number | null { return current; }

// --- Buffers PAR ORIGINE ---------------------------------------------------
// Les familles de traces ne partagent plus un tableau global : chaque
// OriginBuffers est une Map origine → bucket (origine = originRunnerId,
// null = IA live). Conséquences structurelles :
//   - le CAP devient PAR ORIGINE — un acteur bavard ne peut plus affamer la
//     capture des autres (l'ancien scorer `< CAP` global jetait les nouveaux
//     events de TOUT LE MONDE une fois plein) ;
//   - clear scopé et purge au dispose = suppression d'une clé, O(1) ;
//   - le dispose du REGISTRY (chokepoint de TOUS les chemins) appelle
//     purgeTracesForRunner — même hygiène que le purge du log recorder
//     (purgeLogForOrigin). Les instances s'auto-enregistrent au ctor, pas
//     d'import game → features.
// Éviction par bucket : "dropNew" (comportement historique scorer — plein =
// les nouveaux events sont jetés) ou "ring" (shift du plus ancien —
// comportement historique aiUtilityTrace / bucketAudit).

type Evict = "dropNew" | "ring";
const allBuffers: Array<OriginBuffers<{ seq: number }>> = [];

export class OriginBuffers<T extends { seq: number }> {
    private map = new Map<number | null, T[]>();
    constructor(private cap: number, private evict: Evict) {
        allBuffers.push(this as unknown as OriginBuffers<{ seq: number }>);
    }
    /** Push dans le bucket de l'origine COURANTE (getTraceOrigin). */
    push(ev: T): void {
        const k = getTraceOrigin();
        let b = this.map.get(k);
        if (!b) { b = []; this.map.set(k, b); }
        if (b.length >= this.cap) {
            if (this.evict === "dropNew") return;
            b.shift();
        }
        b.push(ev);
    }
    /** Events d'UNE origine (bucket direct), ou de TOUTES (concat, ordre seq). */
    entries(runnerId?: number): T[] {
        if (typeof runnerId === "number") return this.map.get(runnerId) ?? [];
        return [...this.map.values()].flat().sort((a, b) => a.seq - b.seq);
    }
    size(): number {
        let n = 0;
        for (const b of this.map.values()) n += b.length;
        return n;
    }
    clear(runnerId?: number): void {
        if (typeof runnerId === "number") this.map.delete(runnerId);
        else this.map.clear();
    }
}

/** Appelé par runner-registry.disposeRunner — drop le bucket du runner mort
 *  dans TOUTES les familles de traces. */
export function purgeTracesForRunner(runnerId: number): void {
    for (const b of allBuffers) {
        try { b.clear(runnerId); } catch { /* best effort — jamais bloquant */ }
    }
}
