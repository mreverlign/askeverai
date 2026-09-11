"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { QueryResult } from "@/lib/types";

export interface ResultsSectionProps {
  result: QueryResult;
  onDownloadCsv?: () => void;
  "aria-label"?: string;
}

const MAX_VISIBLE_ROWS = 100;

function isNumericValue(value: unknown): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed !== "" && !Number.isNaN(Number(trimmed));
  }
  return false;
}

export function ResultsSection({
  result,
  onDownloadCsv,
  "aria-label": ariaLabel = "Query results",
}: ResultsSectionProps) {
  const { rows, columns, data } = result;
  const hasData = Boolean(data && data.length > 0);
  const columnsList = hasData ? Object.keys(data![0]) : [];
  const [isExpanded, setIsExpanded] = useState(true);

  const visibleRows = data ? data.slice(0, MAX_VISIBLE_ROWS) : [];

  /** Right-align columns whose values are all numeric, so figures line up. */
  const numericColumns = useMemo(() => {
    const numeric = new Set<string>();
    if (!data) return numeric;
    for (const col of Object.keys(data[0] ?? {})) {
      let sawValue = false;
      let allNumeric = true;
      for (const row of data.slice(0, MAX_VISIBLE_ROWS)) {
        const value = row[col];
        if (value === null || value === undefined || value === "") continue;
        sawValue = true;
        if (!isNumericValue(value)) {
          allNumeric = false;
          break;
        }
      }
      if (sawValue && allNumeric) numeric.add(col);
    }
    return numeric;
  }, [data]);

  // Track whether more columns exist past either edge, to show the fades.
  const scrollRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  const updateEdges = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setEdges({
      left: el.scrollLeft > 1,
      right: Math.ceil(el.scrollLeft + el.clientWidth) < el.scrollWidth - 1,
    });
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    updateEdges();
    el.addEventListener("scroll", updateEdges, { passive: true });
    const observer = new ResizeObserver(updateEdges);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", updateEdges);
      observer.disconnect();
    };
  }, [updateEdges, isExpanded, data]);

  return (
    <section aria-label={ariaLabel}>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          aria-expanded={isExpanded}
          className="flex items-center gap-2 rounded-md py-1 text-xs font-medium text-slate-600 transition-colors hover:text-slate-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-white"
        >
          <svg
            className={`w-3.5 h-3.5 transition-transform ${isExpanded ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          Data ({rows} row{rows !== 1 ? "s" : ""}, {columns} col{columns !== 1 ? "s" : ""})
        </button>
        <div className="flex items-center gap-2">
          {edges.right && (
            <span className="hidden select-none items-center gap-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400 sm:flex">
              Scroll for more
              <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m9 18 6-6-6-6" />
              </svg>
            </span>
          )}
          {onDownloadCsv && (
            <button
              type="button"
              onClick={onDownloadCsv}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-slate-600 transition-colors hover:bg-indigo-50 hover:text-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
              aria-label="Download results as CSV"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              CSV
            </button>
          )}
        </div>
      </div>
      {isExpanded && (
        <div className="relative mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-900/5">
          <div
            ref={scrollRef}
            tabIndex={0}
            role="region"
            aria-label={`${ariaLabel} table`}
            className="max-h-[26rem] overflow-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500/40"
          >
            {hasData ? (
              <table className="w-full text-sm" role="table">
                <thead className="bg-slate-50">
                  <tr className="border-b border-slate-200">
                    {columnsList.map((col) => (
                      <th
                        key={col}
                        scope="col"
                        className={`sticky top-0 z-10 whitespace-nowrap bg-slate-50 px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600 shadow-[inset_0_-1px_0_rgb(226_232_240)] ${
                          numericColumns.has(col) ? "text-right" : "text-left"
                        }`}
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-slate-100 transition-colors last:border-b-0 hover:bg-indigo-50/40"
                    >
                      {columnsList.map((col) => {
                        const value = row[col];
                        const text =
                          value === null || value === undefined ? "—" : String(value);
                        return (
                          <td
                            key={col}
                            title={text}
                            className={`whitespace-nowrap px-3 py-2 font-mono text-[12px] text-slate-700 ${
                              numericColumns.has(col) ? "text-right tabular-nums" : "text-left"
                            }`}
                          >
                            {text}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="px-4 py-8 text-center text-sm text-slate-600">No rows returned.</div>
            )}
          </div>

          {/* Edge fades: the only cue that columns exist past the viewport. */}
          {edges.left && (
            <div
              className="pointer-events-none absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-slate-900/[0.09] to-transparent"
              aria-hidden
            />
          )}
          {edges.right && (
            <div
              className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-slate-900/[0.09] to-transparent"
              aria-hidden
            />
          )}

          {data && data.length > MAX_VISIBLE_ROWS && (
            <div className="relative border-t border-slate-200 bg-slate-50/80 px-4 py-2.5 text-[11px] font-medium text-slate-600">
              Showing first {MAX_VISIBLE_ROWS} of {data.length.toLocaleString()} rows — download the CSV for the full result
            </div>
          )}
        </div>
      )}
    </section>
  );
}
