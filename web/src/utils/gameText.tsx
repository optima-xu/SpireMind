import type { ReactNode } from "react";
import type { PublicFactsValue } from "../types";

export function unpackFacts(value: PublicFactsValue): Record<string, unknown> {
  if (!value) return {};
  if (typeof value === "object" && "encoded" in value && typeof value.encoded === "string") {
    try {
      const parsed = JSON.parse(value.encoded);
      return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  if (typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
}

const COLOR_MAP: Record<string, string> = {
  gold: "text-amber-300 font-semibold",
  yellow: "text-amber-300 font-semibold",
  blue: "text-sky-300 font-semibold",
  aqua: "text-cyan-300 font-semibold",
  green: "text-emerald-300 font-semibold",
  red: "text-rose-400 font-semibold",
  crimson: "text-rose-400 font-semibold",
  purple: "text-violet-300 font-semibold",
  orange: "text-orange-300 font-semibold",
  gray: "text-slate-400",
  grey: "text-slate-400",
  b: "font-semibold text-slate-100",
  sine: "text-amber-200 italic",
  jitter: "text-rose-300 font-semibold",
};

interface Segment {
  text: string;
  classes: string[];
  kind: "text" | "energy" | "star" | "badge";
}

function tokenizeGameText(raw: string): Segment[] {
  const normalized = raw.replace(/\r\n/g, "\n");
  const tagRegex = /\[(\/?[a-zA-Z0-9_=-]+)\]([\s\S]*?\[\/img\])?|\[img\]([\s\S]*?)\[\/img\]/g;
  const imgRegex = /\[img\]([^[]*?)\[\/img\]/gi;

  // Replace [img]...[/img] with lightweight symbolic markers before BBCode pass.
  const pretokenized = normalized.replace(imgRegex, (_m, path: string) => {
    const lower = path.toLowerCase();
    if (lower.includes("energy")) return "\u0000ENERGY\u0000";
    if (lower.includes("star")) return "\u0000STAR\u0000";
    return "\u0000ICON\u0000";
  });

  const segments: Segment[] = [];
  const stack: { tag: string; cls: string }[] = [];
  let lastIndex = 0;

  // Simple open/close BBCode scanner for [tag] and [/tag]
  const simpleTagRe = /\[(\/?)([a-zA-Z0-9_]+)(?:=[^\]]*)?\]/g;
  void tagRegex;

  let match: RegExpExecArray | null;
  while ((match = simpleTagRe.exec(pretokenized)) !== null) {
    if (match.index > lastIndex) {
      pushWithSymbols(pretokenized.slice(lastIndex, match.index), stack, segments);
    }
    const isClose = match[1] === "/";
    const tagName = match[2].toLowerCase();
    if (isClose) {
      const idx = findLastTag(stack, tagName);
      if (idx >= 0) {
        stack.splice(idx, 1);
      }
    } else if (tagName in COLOR_MAP) {
      stack.push({ tag: tagName, cls: COLOR_MAP[tagName] });
    } else {
      // Unknown formatting tags like [center], [thinky_dots], etc. are safely stripped.
      stack.push({ tag: tagName, cls: "" });
    }
    lastIndex = simpleTagRe.lastIndex;
  }
  if (lastIndex < pretokenized.length) {
    pushWithSymbols(pretokenized.slice(lastIndex), stack, segments);
  }
  return segments;
}

function findLastTag(stack: { tag: string; cls: string }[], target: string): number {
  for (let i = stack.length - 1; i >= 0; i -= 1) {
    if (stack[i].tag === target) return i;
  }
  return -1;
}

function pushWithSymbols(
  chunk: string,
  stack: { tag: string; cls: string }[],
  out: Segment[],
): void {
  const classes = stack.map((item) => item.cls).filter(Boolean);
  const parts = chunk.split(/(\u0000ENERGY\u0000|\u0000STAR\u0000|\u0000ICON\u0000)/);
  for (const part of parts) {
    if (!part) continue;
    if (part === "\u0000ENERGY\u0000") {
      out.push({ text: "E", classes, kind: "energy" });
    } else if (part === "\u0000STAR\u0000") {
      out.push({ text: "★", classes, kind: "star" });
    } else if (part === "\u0000ICON\u0000") {
      out.push({ text: "•", classes, kind: "badge" });
    } else {
      out.push({ text: part, classes, kind: "text" });
    }
  }
}

export function GameText({ text, className = "" }: { text?: string | null; className?: string }): ReactNode {
  if (!text) return null;
  const segments = tokenizeGameText(text);
  return (
    <span className={`whitespace-pre-line break-words ${className}`}>
      {segments.map((seg, idx) => {
        if (seg.kind === "energy") {
          return (
            <span
              key={idx}
              title="Energy"
              className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500/20 px-1 text-[10px] font-bold text-amber-300 ring-1 ring-amber-400/40"
            >
              ⚡
            </span>
          );
        }
        if (seg.kind === "star") {
          return (
            <span
              key={idx}
              title="Star"
              className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-cyan-500/20 px-1 text-[10px] font-bold text-cyan-300 ring-1 ring-cyan-400/40"
            >
              ★
            </span>
          );
        }
        if (seg.kind === "badge") {
          return (
            <span key={idx} className="mx-0.5 text-slate-400">
              •
            </span>
          );
        }
        if (seg.classes.length > 0) {
          return (
            <span key={idx} className={seg.classes.join(" ")}>
              {seg.text}
            </span>
          );
        }
        return <span key={idx}>{seg.text}</span>;
      })}
    </span>
  );
}
