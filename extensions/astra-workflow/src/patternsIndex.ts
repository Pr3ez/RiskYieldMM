import * as fs from "fs";
import * as path from "path";
import { PatternSuggestion } from "./types.js";

interface ParsedEntry {
  title: string;
  content: string;
  source: string;
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 2);
}

function termFreq(tokens: string[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const t of tokens) {
    map.set(t, (map.get(t) ?? 0) + 1);
  }
  return map;
}

function cosineSim(a: Map<string, number>, b: Map<string, number>): number {
  let dot = 0;
  let aMag = 0;
  let bMag = 0;
  for (const [, val] of a) aMag += val * val;
  for (const [, val] of b) bMag += val * val;
  const keys = new Set([...a.keys(), ...b.keys()]);
  for (const k of keys) {
    dot += (a.get(k) ?? 0) * (b.get(k) ?? 0);
  }
  if (aMag === 0 || bMag === 0) return 0;
  return dot / Math.sqrt(aMag * bMag);
}

async function readIfExists(filePath: string): Promise<string | null> {
  try {
    return await fs.promises.readFile(filePath, "utf8");
  } catch {
    return null;
  }
}

function parseMarkdownEntries(content: string, source: string): ParsedEntry[] {
  const entries: ParsedEntry[] = [];
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

export async function loadPatternEntries(workspacePath: string, memoryPath: string): Promise<ParsedEntry[]> {
  const resolvedMemoryPath = path.isAbsolute(memoryPath)
    ? memoryPath
    : path.join(workspacePath, memoryPath);
  const targets = [
    path.join(resolvedMemoryPath, "knowledge", "patterns.md"),
    path.join(resolvedMemoryPath, "knowledge", "mistakes.md"),
  ];

  const entries: ParsedEntry[] = [];
  for (const target of targets) {
    const content = await readIfExists(target);
    if (content) {
      entries.push(...parseMarkdownEntries(content, target));
    }
  }
  return entries;
}

export async function suggestPatterns(
  workspacePath: string,
  memoryPath: string,
  contextText: string,
  limit = 3,
  threshold = 0.08
): Promise<PatternSuggestion[]> {
  const entries = await loadPatternEntries(workspacePath, memoryPath);
  if (entries.length === 0 || !contextText.trim()) return [];

  const contextVec = termFreq(tokenize(contextText));
  const scored: PatternSuggestion[] = entries
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
