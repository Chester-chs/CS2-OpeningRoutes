import { useEffect, useMemo, useState } from "react";
import { DataClient, kindNames } from "./data";
import type { Round, Throw, Timeline as TimelineData } from "./types";

export default function Timeline({
  client,
  round,
  throwRow,
  throws,
}: {
  client: DataClient;
  round: Round;
  throwRow?: Throw;
  throws: Throw[];
}) {
  const [data, setData] = useState<TimelineData | null>(null);
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(throwRow?.time || 0);
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    client
      .timeline(round.id)
      .then((d) => {
        if (active) {
          setData(d);
          setSelected(Object.keys(d.players));
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [client, round.id]);
  const bounds = useMemo(() => {
    const points = data
      ? Object.values(data.players).flatMap((p) => p.points)
      : [];
    const xs = points.map((p) => p[1]),
      ys = points.map((p) => p[2]);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }, [data]);
  if (error) return <p className="notice">{error}</p>;
  if (!data) return <p className="muted">正在加载全回合路线…</p>;
  const x = (v: number) =>
    30 + ((v - bounds.minX) / Math.max(bounds.maxX - bounds.minX, 1)) * 640;
  const y = (v: number) =>
    440 - ((v - bounds.minY) / Math.max(bounds.maxY - bounds.minY, 1)) * 400;
  const tick = round.freeze_end_tick + seconds * data.tick_rate;
  const min = (round.start_tick - round.freeze_end_tick) / data.tick_rate;
  const max =
    ((round.end_tick || round.freeze_end_tick) - round.freeze_end_tick) /
    data.tick_rate;
  const events =
    round.observed_throws ?? throws.filter((t) => t.round_id === round.id);
  const markers = [
    ...events.map((t) => ({
      tick: t.tick,
      label: `${t.side} · ${t.player} · ${kindNames[t.kind] ?? t.kind}`,
    })),
    ...(round.opening_kill
      ? [
          {
            tick: round.opening_kill.tick,
            label: `首杀 · ${round.opening_kill.attacker} → ${round.opening_kill.victim}`,
          },
        ]
      : []),
    ...round.bomb_events.map((e) => ({
      tick: e.tick,
      label: `${({ bomb_planted: "下包", bomb_defused: "拆包", bomb_exploded: "爆炸" } as Record<string, string>)[e.kind] ?? e.kind} · ${e.player || "—"}`,
    })),
  ].sort((a, b) => a.tick - b.tick);
  return (
    <section className="timeline">
      <div className="section-line">
        <h3>完整回合路线</h3>
        <span className="micro">{data.sample_hz} Hz · 全员 / 全回合</span>
      </div>
      <svg viewBox="0 0 700 480" role="img" aria-label="选手全回合坐标路线图">
        <defs>
          <pattern
            id="grid"
            width="35"
            height="30"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M35 0H0V30"
              fill="none"
              stroke="#223a32"
              strokeWidth="0.6"
            />
          </pattern>
        </defs>
        <rect width="700" height="480" fill="url(#grid)" />
        {Object.entries(data.players)
          .filter(([id]) => selected.includes(id))
          .map(([id, p]) => {
            const elapsed = p.points.filter((v) => v[0] <= tick);
            const current = elapsed.at(-1);
            if (!current) return null;
            const color = current[4] === "CT" ? "#6abac6" : "#e2b15c";
            return (
              <g key={id}>
                <polyline
                  points={p.points
                    .map((v) => `${x(v[1])},${y(v[2])}`)
                    .join(" ")}
                  fill="none"
                  stroke={color}
                  opacity="0.15"
                  strokeWidth="1"
                />
                <polyline
                  points={elapsed.map((v) => `${x(v[1])},${y(v[2])}`).join(" ")}
                  fill="none"
                  stroke={color}
                  opacity="0.8"
                  strokeWidth="1.6"
                />
                <circle
                  cx={x(current[1])}
                  cy={y(current[2])}
                  r={current[5] ? 5 : 3}
                  fill={color}
                />
                <text
                  x={x(current[1]) + 7}
                  y={y(current[2]) - 7}
                  fill={color}
                  fontSize="11"
                >
                  {p.name}
                  {current[5] ? "" : " ×"}
                </text>
              </g>
            );
          })}
        {throwRow?.trajectory.length ? (
          <polyline
            points={throwRow.trajectory
              .map((v) => `${x(v[1])},${y(v[2])}`)
              .join(" ")}
            fill="none"
            stroke="#fff"
            strokeDasharray="4 3"
            strokeWidth="2"
          />
        ) : null}
        <text x="20" y="468" fill="#8da89a" fontSize="11">
          世界坐标示意 · Y 轴朝上 · 高度数据保留在原始记录
        </text>
      </svg>
      <div className="time-line">
        <span>冻结结束后 {seconds.toFixed(2)} 秒</span>
        <span>tick {Math.round(tick)}</span>
      </div>
      <input
        aria-label="回合时间轴"
        type="range"
        min={min}
        max={max}
        step={0.25}
        value={seconds}
        onChange={(e) => setSeconds(Number(e.target.value))}
      />
      <div className="players">
        {Object.entries(data.players).map(([id, p]) => (
          <label key={id}>
            <input
              type="checkbox"
              checked={selected.includes(id)}
              onChange={() =>
                setSelected((v) =>
                  v.includes(id) ? v.filter((x) => x !== id) : [...v, id],
                )
              }
            />
            {p.name}
          </label>
        ))}
      </div>
      <h3>回合事件</h3>
      <p className="micro">
        时间从冻结结束算起。选择事件可查看该时刻双方的位置。
      </p>
      <div className="chips">
        {markers.map((m, i) => {
          const at = (m.tick - round.freeze_end_tick) / data.tick_rate;
          return (
            <button key={i} className="chip" onClick={() => setSeconds(at)}>
              {at.toFixed(2)} 秒 · {m.label}
            </button>
          );
        })}
        {!markers.length && <span>此回合暂无可定位的事件。</span>}
      </div>
    </section>
  );
}
