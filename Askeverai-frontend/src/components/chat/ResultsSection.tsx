"use client";

import { useState } from "react";
import type { QueryResult } from "@/lib/types";

export interface ResultsSectionProps {
  result: QueryResult;
  onDownloadCsv?: () => void;
  "aria-label"?: string;
}

export function ResultsSection({
  result,
  onDownloadCsv,
  "aria-label": ariaLabel = "Query results",
}: ResultsSectionProps) {
  const { rows, columns, data } = result;
  const hasData = data && data.length > 0;
  const columnsList = hasData ? Object.keys(data[0]) : [];
  const [isExpanded, setIsExpanded] = useState(true);

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
      {isExpanded && (
        <div className="mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-900/5">
          <div className="overflow-x-auto">
            {hasData ? (
              <table className="w-full text-sm" role="table">
                <thead className="bg-slate-50/90">
                  <tr className="border-b border-slate-200">
                    {columnsList.map((col) => (
                      <th key={col} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-600" scope="col">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(data.length > 100 ? data.slice(0, 100) : data).map((row, i) => (
                    <tr key={i} className="border-b border-slate-100 transition-colors last:border-b-0 hover:bg-indigo-50/40">
                      {columnsList.map((col) => (
                        <td key={col} className="whitespace-nowrap px-4 py-2.5 font-mono text-[13px] text-slate-700">
                          {String(row[col] ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="px-4 py-8 text-center text-sm text-slate-600">No rows returned.</div>
            )}
          </div>
          {data && data.length > 100 && (
            <div className="border-t border-slate-200 bg-slate-50/80 px-4 py-2.5 text-[11px] font-medium text-slate-600">
              Showing first 100 of {data.length.toLocaleString()} rows
            </div>
          )}
        </div>
      )}
    </section>
  );
}
