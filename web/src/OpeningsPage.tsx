import { useEffect, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { DataClient, kindNames } from "./data";
import { nadesLink, rateText } from "./openings";
import type { OpeningBucket, Openings as OpeningsData } from "./openings";
import type { Catalog } from "./types";

export default function OpeningsPage({
  client,
  catalog,
  openRound,
}: {
  client: DataClient;
  catalog: Catalog;
  openRound: (id: string) => void;
}) {
  const maps = useMemo(
    () => [...new Set(catalog.matches.map((m) => m.map))].sort(),
    [catalog.matches],
  );
  const [map, setMap] = useState("de_mirage");
  const current = maps.includes(map) ? map : maps[0] || "";
  const [data, setData] = useState<OpeningsData | null>(null);
  const [error, setError] = useState("");
  const [bucketId, setBucketId] = useState("");
  const [team, setTeam] = useState("");
  useEffect(() => {
    if (!current) return;
    let active = true;
    setData(null);
    setError("");
    client
      .openings(current)
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [client, current]);
  const bucket: OpeningBucket | undefined =
    data?.buckets.find((b) => b.id === bucketId) || data?.buckets[0];
  const teams = bucket
    ? Object.keys(bucket.teams).sort(
        (a, b) =>
          bucket.teams[b].T.rounds +
          bucket.teams[b].CT.rounds -
          bucket.teams[a].T.rounds -
          bucket.teams[a].CT.rounds,
      )
    : [];
  const scoutTeam = teams.includes(team) ? team : teams[0] || "";
  const tName = (id: number | null) =>
    bucket?.t.patterns.find((p) => p.id === id)?.name ?? "未归类";
  const ctName = (id: number | null) =>
    bucket?.ct.patterns.find((p) => p.id === id)?.name ?? "未归类";
  return (
    <section className="openings" data-testid="openings">
      <p className="notice">
        开局前 30 秒：T 方默认打法 × CT 防守阵型。样本少于 10 回合或 3
        场时只显示数量；胜率是比赛观察，不代表最优选择。具体道具投法请到
        nades.ai 查看。
      </p>
      <div className="learning-filters">
        <label>
          地图
          <select
            aria-label="开局地图"
            value={current}
            onChange={(e) => setMap(e.target.value)}
          >
            {maps.map((m) => (
              <option key={m} value={m}>
                {m.replace("de_", "")}
              </option>
            ))}
          </select>
        </label>
        {data && (
          <label>
            时期
            <select
              aria-label="开局时期"
              value={bucket?.id || ""}
              onChange={(e) => setBucketId(e.target.value)}
            >
              {data.buckets.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.era ? `地图时期 ${b.label}` : b.label} · {b.rounds} 回合 /{" "}
                  {b.matches} 场
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {error && <p className="notice">{error}</p>}
      {!data && !error && <p className="muted">正在计算开局分析…</p>}
      {bucket && (
        <>
          <h2>T 方默认打法</h2>
          {bucket.t.warnings.map((w) => (
            <p className="notice" key={w}>
              {w}
            </p>
          ))}
          <div className="card-grid">
            {bucket.t.patterns.map((p) => (
              <article
                className="pattern-card"
                key={p.id}
                data-testid="t-default"
              >
                <h3>{p.name}</h3>
                <p className="micro">
                  {p.rounds} 回合 · T 胜{" "}
                  {p.t_win_rate === null
                    ? "—"
                    : `${Math.round(p.t_win_rate * 100)}%`}
                  （{p.decided} 回合已分胜负）· 20 秒常见站位：
                  {p.setups.map((s) => s.setup).join(" / ")}
                </p>
                <ul>
                  {p.utility_timing.slice(0, 4).map((u) => {
                    const link = nadesLink(current, u.kind);
                    return (
                      <li key={`${u.kind}-${u.area}`}>
                        {kindNames[u.kind] || u.kind} → {u.area} · 中位{" "}
                        {u.median} 秒 · {u.count} 次
                        {link && (
                          <>
                            {" "}
                            <a
                              href={link}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              nades.ai 上的{kindNames[u.kind] || u.kind}点位{" "}
                              <ExternalLink size={12} />
                            </a>
                          </>
                        )}
                      </li>
                    );
                  })}
                </ul>
                <button
                  className="text-button"
                  onClick={() => openRound(p.representative)}
                >
                  代表回合
                </button>
              </article>
            ))}
          </div>
          <h2>对位：T 默认打法 × CT 阵型</h2>
          <div className="table-scroll">
            <table data-testid="matchups">
              <thead>
                <tr>
                  <th>T \ CT</th>
                  {bucket.ct.patterns.map((c) => (
                    <th key={c.id}>{c.name || `阵型 ${c.id + 1}`}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bucket.t.patterns.map((t) => (
                  <tr key={t.id}>
                    <th>{t.name}</th>
                    {bucket.ct.patterns.map((c) => {
                      const cell = bucket.matchups.find(
                        (m) => m.t === t.id && m.ct === c.id,
                      );
                      return (
                        <td key={c.id}>
                          {cell
                            ? rateText({
                                status: cell.status,
                                rounds: cell.rounds,
                                matches: cell.matches,
                                rate: cell.t_win_rate,
                                interval: cell.interval,
                              })
                            : "无样本"}
                          {cell?.contact && (
                            <span className="micro">
                              {" "}
                              · 首次交火 {cell.contact.place}（中位{" "}
                              {cell.contact.median_second} 秒）
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="micro">格子里是 T 方胜率及 95% 区间。</p>
          <h2>单队侦察</h2>
          <label>
            战队
            <select
              aria-label="侦察战队"
              value={scoutTeam}
              onChange={(e) => setTeam(e.target.value)}
            >
              {teams.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          {scoutTeam &&
            (["T", "CT"] as const).map((side) => {
              const scout = bucket.teams[scoutTeam][side];
              return (
                <div key={side} data-testid={`scout-${side}`}>
                  <h3>
                    {scoutTeam} · {side} · {scout.rounds} 回合 / {scout.matches}{" "}
                    场
                  </h3>
                  <ul>
                    {scout.defaults.map((d) => (
                      <li key={String(d.label)}>
                        {side === "T" ? tName(d.label) : ctName(d.label)}：
                        {rateText({
                          status: d.status,
                          rounds: d.rounds,
                          matches: d.matches,
                          rate: d.win_rate,
                          interval: d.interval,
                        })}
                        {d.examples.map((id) => (
                          <button
                            key={id}
                            className="text-button"
                            onClick={() => openRound(id)}
                          >
                            回合 {id.split("-r").pop()}
                          </button>
                        ))}
                      </li>
                    ))}
                  </ul>
                  <p className="micro">
                    对手：
                    {Object.entries(scout.opponents)
                      .map(([o, n]) => `${o} ${n} 回合`)
                      .join("、")}
                  </p>
                </div>
              );
            })}
        </>
      )}
    </section>
  );
}
