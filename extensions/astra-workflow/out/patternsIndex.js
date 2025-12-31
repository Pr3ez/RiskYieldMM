"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadPatternEntries = loadPatternEntries;
exports.suggestPatterns = suggestPatterns;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
function tokenize(text) {
    return text
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, " ")
        .split(/\s+/)
        .filter((t) => t.length > 2);
}
function termFreq(tokens) {
    const map = new Map();
    for (const t of tokens) {
        map.set(t, (map.get(t) ?? 0) + 1);
    }
    return map;
}
function cosineSim(a, b) {
    let dot = 0;
    let aMag = 0;
    let bMag = 0;
    for (const [, val] of a)
        aMag += val * val;
    for (const [, val] of b)
        bMag += val * val;
    const keys = new Set([...a.keys(), ...b.keys()]);
    for (const k of keys) {
        dot += (a.get(k) ?? 0) * (b.get(k) ?? 0);
    }
    if (aMag === 0 || bMag === 0)
        return 0;
    return dot / Math.sqrt(aMag * bMag);
}
async function readIfExists(filePath) {
    try {
        return await fs.promises.readFile(filePath, "utf8");
    }
    catch {
        return null;
    }
}
function parseMarkdownEntries(content, source) {
    const entries = [];
    const parts = content.split(/^###\s+/m).filter((p) => p.trim().length > 0);
    if (parts.length === 0) {
        // Treat entire file as one entry
        entries.push({
            title: path.basename(source),
            content,
            source,
        });
        return entries;
    }
    for (const part of parts) {
        const lines = part.split("\n");
        const title = lines.shift()?.trim() ?? "Untitled";
        const body = lines.join("\n").trim();
        entries.push({ title, content: body, source });
    }
    return entries;
}
async function loadPatternEntries(workspacePath, memoryPath) {
    const resolvedMemoryPath = path.isAbsolute(memoryPath)
        ? memoryPath
        : path.join(workspacePath, memoryPath);
    const targets = [
        path.join(resolvedMemoryPath, "knowledge", "patterns.md"),
        path.join(resolvedMemoryPath, "knowledge", "mistakes.md"),
    ];
    const entries = [];
    for (const target of targets) {
        const content = await readIfExists(target);
        if (content) {
            entries.push(...parseMarkdownEntries(content, target));
        }
    }
    return entries;
}
async function suggestPatterns(workspacePath, memoryPath, contextText, limit = 3, threshold = 0.08) {
    const entries = await loadPatternEntries(workspacePath, memoryPath);
    if (entries.length === 0 || !contextText.trim())
        return [];
    const contextVec = termFreq(tokenize(contextText));
    const scored = entries
        .map((entry) => {
        const vec = termFreq(tokenize(entry.title + " " + entry.content));
        const score = cosineSim(contextVec, vec);
        const snippet = entry.content.slice(0, 200).replace(/\s+/g, " ").trim();
        return {
            title: entry.title,
            snippet,
            score,
            source: entry.source,
        };
    })
        .filter((p) => p.score >= threshold)
        .sort((a, b) => b.score - a.score)
        .slice(0, limit);
    return scored;
}
//# sourceMappingURL=patternsIndex.js.map