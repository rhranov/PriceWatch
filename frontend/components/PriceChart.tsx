"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { format } from "date-fns";
import type { PricePoint } from "@/lib/api";

const SOURCE_COLORS = [
  "hsl(var(--primary))",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
  "#06b6d4",
  "#ef4444",
];

interface Props {
  data: PricePoint[];
  height?: number;
}

export function PriceChart({ data, height = 120 }: Props) {
  // Collect unique sources in order of first appearance
  const sourceOrder: string[] = [];
  const sourceNames: Record<string, string> = {};
  data.forEach((d) => {
    if (!sourceOrder.includes(d.listing_id)) {
      sourceOrder.push(d.listing_id);
      sourceNames[d.listing_id] = d.source_name || d.listing_id.slice(0, 8);
    }
  });

  // One row per date bucket; columns are listing_ids
  const dateMap = new Map<string, Record<string, unknown>>();
  data.forEach((d) => {
    if (d.price_eur == null) return;
    const key = format(new Date(d.scraped_at), "dd MMM");
    if (!dateMap.has(key)) dateMap.set(key, { date: key });
    dateMap.get(key)![d.listing_id] = d.price_eur;
  });

  const chartData = Array.from(dateMap.values());
  const allPrices = data.map((d) => d.price_eur).filter((p): p is number => p != null);

  if (allPrices.length < 2) {
    return (
      <div className="h-20 flex items-center justify-center text-xs text-muted-foreground">
        Not enough data yet
      </div>
    );
  }

  const minP = Math.min(...allPrices) * 0.97;
  const maxP = Math.max(...allPrices) * 1.03;

  return (
    <div>
      {sourceOrder.length > 1 && (
        <div className="flex gap-3 mb-1">
          {sourceOrder.map((id, i) => (
            <span key={id} className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ background: SOURCE_COLORS[i % SOURCE_COLORS.length] }}
              />
              {sourceNames[id]}
            </span>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[minP, maxP]}
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `€${(v / 1000).toFixed(1)}k`}
            width={48}
          />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: "8px",
              fontSize: "12px",
              color: "hsl(var(--foreground))",
            }}
            formatter={(value: number, key: string) => [
              `€${value.toLocaleString("de-DE", { minimumFractionDigits: 2 })}`,
              sourceNames[key] ?? key,
            ]}
          />
          {sourceOrder.map((id, i) => (
            <Line
              key={id}
              type="monotone"
              dataKey={id}
              stroke={SOURCE_COLORS[i % SOURCE_COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
