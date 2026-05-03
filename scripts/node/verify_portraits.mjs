import fs from "node:fs";

const m = JSON.parse(fs.readFileSync("frida/assets/public/manifest.json"));
const am = JSON.parse(fs.readFileSync("frida/assets/public/unit-asset-map.json"));
const known = m.units;

const PORTRAIT_ALIASES = {
    "darka_deathwing_01": "darka_terminator_01",
    "necro_scarabswarm_01": "necro_scarab_01",
};
const SPLIT_TAIL_WORDS = [
    "uncommon", "common", "rare", "epic", "legendary", "mythic",
    "ability", "shield",
];

function buildCandidates(asset) {
    const out = new Set();
    if (!asset) return out;
    const clean = asset.trim();
    const lc = clean.toLowerCase();
    const versionSuffixes = ["", "_01", "_01_premium"];
    const enq = (b) => { for (const s of versionSuffixes) out.add(b + s); };
    enq(clean); enq(lc);
    if (PORTRAIT_ALIASES[clean]) enq(PORTRAIT_ALIASES[clean]);
    if (PORTRAIT_ALIASES[lc])    enq(PORTRAIT_ALIASES[lc]);
    const sing = clean.replace(/s(_\d+(?:_premium)?)?$/, "$1");
    if (sing !== clean) { enq(sing); enq(sing.toLowerCase()); }
    for (const w of SPLIT_TAIL_WORDS) {
        const re = new RegExp(`^(.+?)(${w})((?:_\\d+(?:_premium)?)?)$`, "i");
        const m2 = lc.match(re);
        if (!m2) continue;
        const head = m2[1].replace(/_$/, "");
        enq(`${head}_${m2[2]}${m2[3]}`);
    }
    return out;
}

function resolve(cfgId) {
    const asset = am[cfgId]?.assetNaming;
    if (asset) for (const c of buildCandidates(asset)) if (known[c]) return c;
    const snake = cfgId.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
    for (const c of buildCandidates(snake)) if (known[c]) return c;
    return null;
}

let total = 0, fail = 0;
const stillFailing = [];
for (const cfgId of Object.keys(am)) {
    total++;
    if (resolve(cfgId) === null) {
        stillFailing.push([cfgId, am[cfgId].assetNaming]);
        fail++;
    }
}
console.log("Total:", total, "Still failing:", fail);
for (const [c, a] of stillFailing) console.log("  " + c + " -> " + JSON.stringify(a));
