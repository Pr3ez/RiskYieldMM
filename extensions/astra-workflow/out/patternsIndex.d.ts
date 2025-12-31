import { PatternSuggestion } from "./types.js";
interface ParsedEntry {
    title: string;
    content: string;
    source: string;
}
export declare function loadPatternEntries(workspacePath: string, memoryPath: string): Promise<ParsedEntry[]>;
export declare function suggestPatterns(workspacePath: string, memoryPath: string, contextText: string, limit?: number, threshold?: number): Promise<PatternSuggestion[]>;
export {};
//# sourceMappingURL=patternsIndex.d.ts.map