import { useEffect, useMemo, useState } from "react";
import { fetchLandingTape } from "../../api/stocks";

const REFRESH_MS = 60000;

const formatPrice = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const formatChange = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  return Number(value).toFixed(2);
};

export default function LandingMarketTape() {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const data = await fetchLandingTape(18);
        if (active) setRows(data);
      } catch {
        if (active) setRows([]);
      }
    };

    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const items = useMemo(() => (rows.length ? [...rows, ...rows] : []), [rows]);
  if (!items.length) return null;

  return (
    <div className="border-b border-white/10 bg-[#050816]/95">
      <div className="market-tape-mask overflow-hidden py-1.5">
        <div className="market-tape-track flex w-max items-center gap-6 whitespace-nowrap px-4 sm:px-6 lg:px-8">
          {items.map((item, idx) => {
            const change = formatChange(item.change_pct);
            const isUp = change !== null && Number(change) >= 0;
            const sign = change === null ? "" : isUp ? "+" : "";
            return (
              <span key={`${item.symbol}-${idx}`} className="inline-flex items-center gap-2 text-sm">
                <span className="font-bold tracking-wide text-slate-100">{item.symbol}</span>
                <span className="text-slate-200">{formatPrice(item.price)}</span>
                <span className={isUp ? "font-semibold text-emerald-400" : "font-semibold text-rose-400"}>
                  {change === null ? "--" : `${sign}${change}%`}
                </span>
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
