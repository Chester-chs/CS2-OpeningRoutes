import { useMemo, useState } from "react";
import { BookOpen, ClipboardPlus, Eye } from "lucide-react";
import { DataClient, kindNames } from "./data";
import type {
  AreaShares,
  Catalog,
  CTAnalysis,
  CTPattern,
  Plan,
  TeamHabit,
} from "./types";

export const AREA_NAMES: Record<string, string> = {
  A: "A 区",
  B: "B 区",
  Mid: "中路",
  CT: "CT 后场",
  other: "其他",
};
const AREA_ORDER = ["A", "Mid", "B", "CT", "other"];
const ECON_NAMES: Record<string, string> = {
  pistol: "手枪局",
  eco: "经济局",
  half_buy: "半起",
  long_gun: "长枪局",
};
const VARIABLE_NAMES: Record<string, string> = {
  ct_econ: "CT 经济",
  t_econ: "T 经济",
  score_state: "比分态势",
  prev_winner_side: "上一回合胜方",
  prev_attack_site: "上一回合 T 进攻点",
};
const TABS = [
  ["patterns", "防守阵型"],
  ["teams", "战队习惯"],
  ["context", "情境检验"],
  ["spots", "站位点"],
  ["method", "方法与引用"],
] as const;

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;
const pValue = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : v < 0.001 ? "<0.001" : v.toFixed(3);

export function placeName(catalog: Catalog, map: string, place: string) {
  const [base, suffix] = place.split("·");
  const label = catalog.places?.[map]?.[base];
  const name = label && label !== base ? `${label}（${base}）` : base;
  return suffix ? `${name} ${suffix} 号位` : name;
}

function shortName(catalog: Catalog, map: string, place: string) {
  const [base, suffix] = place.split("·");
  const name = catalog.places?.[map]?.[base] || base;
  return suffix ? `${name}·${suffix}` : name;
}

function moveName(catalog: Catalog, map: string, move: string) {
  return move
    .split(" → ")
    .map((p) => placeName(catalog, map, p))
    .join(" → ");
}

function ShareBar({ shares, label }: { shares: AreaShares; label: string }) {
  return (
    <div className="share-row">
      <span className="micro">{label}</span>
      <div
        className="share-bar"
        role="img"
        aria-label={`${label} 区域人数占比`}
      >
        {AREA_ORDER.filter((a) => (shares[a] || 0) > 0).map((a) => (
          <span
            key={a}
            className={`area-${a}`}
            style={{ width: `${(shares[a] || 0) * 100}%` }}
            title={`${AREA_NAMES[a]} ${pct(shares[a])}`}
          >
            {(shares[a] || 0) >= 0.12 ? AREA_NAMES[a].replace(" 区", "") : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

export function draftPlan(
  catalog: Catalog,
  analysis: CTAnalysis,
  pattern: CTPattern,
): Plan | null {
  const steps = catalog.throws
    .filter(
      (t) =>
        t.round_id === pattern.representative &&
        t.side === "CT" &&
        t.time <= 20,
    )
    .sort((a, b) => a.time - b.time)
    .map((t) => ({
      throw_id: t.id,
      role: t.player,
      time: Math.round(t.time * 10) / 10,
      followup: "",
    }));
  if (!steps.length) return null;
  const top = Object.entries(pattern.shares["15"] || {}).sort(
    (a, b) => b[1] - a[1],
  )[0];
  return {
    id: crypto.randomUUID(),
    title: `${analysis.map.replace("de_", "")} CT · ${pattern.name}`,
    area: top ? AREA_NAMES[top[0]] : "",
    side: "CT",
    purpose: `${pattern.rationale} 来自 ${pattern.rounds} 个职业 CT 回合的阵型统计（代表回合 ${pattern.representative}）。`,
    conditions: `常见站位：${pattern.setups
      .slice(0, 2)
      .map((s) => s.setup)
      .join(" / ")}；经济：${Object.entries(pattern.economy)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${ECON_NAMES[k] || k} ${v}`)
      .join("、")}`,
    steps,
    counter_ids: [],
    counter_explanation: "",
    status: "draft",
  };
}

export default function CTPatterns({
  client,
  catalog,
  onRefresh,
  openRound,
}: {
  client: DataClient;
  catalog: Catalog;
  onRefresh: () => void;
  openRound: (id: string) => void;
}) {
  const analyses = catalog.ct_patterns || {};
  const maps = Object.keys(analyses).sort();
  const [chosen, setMap] = useState("");
  const map = maps.includes(chosen) ? chosen : maps[0] || "";
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("patterns");
  const [message, setMessage] = useState("");
  const analysis = analyses[map];
  if (!analysis)
    return (
      <div className="empty">
        <h3>还没有可分析的 CT 回合</h3>
        <p>导入并核对职业比赛来源后，这里会按地图自动生成 CT 防守阵型。</p>
      </div>
    );
  return (
    <>
      <div className="section-line">
        <p className="muted">
          按论文 TAGNet 的流程，从职业 CT 回合的 10/12/15/18/20
          秒站位归纳防守阵型，并进一步学习每支战队、每名选手的习惯站位。
        </p>
        <div className="chips map-chips" role="tablist" aria-label="选择地图">
          {maps.map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={m === map}
              className={m === map ? "chip active" : "chip"}
              onClick={() => setMap(m)}
            >
              {m.replace("de_", "")} <b>{analyses[m].rounds}</b>
            </button>
          ))}
        </div>
      </div>
      <div className="stats">
        <div className="stat">
          <span>CT 回合</span>
          <strong>{analysis.rounds}</strong>
          <small>
            {analysis.matches} 张比赛地图 · {analysis.teams.length} 支战队
          </small>
        </div>
        <div className="stat">
          <span>防守阵型</span>
          <strong>{analysis.patterns.length}</strong>
          <small>K 按论文的三项指标排名选择</small>
        </div>
        <div className="stat">
          <span>重抽样稳定性</span>
          <strong>
            {analysis.stability_ari == null
              ? "—"
              : analysis.stability_ari.toFixed(2)}
          </strong>
          <small>ARI，1 表示每次重抽样划分都相同</small>
        </div>
        <div className="stat">
          <span>轮廓系数</span>
          <strong>{analysis.quality?.silhouette?.toFixed(2) ?? "—"}</strong>
          <small>论文计数基线 0.30，TAGNet 0.18</small>
        </div>
      </div>
      {analysis.warnings.map((w) => (
        <p className="notice" key={w}>
          {w}
        </p>
      ))}
      <div className="tabs" role="tablist" aria-label="CT 研究内容">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "tab active" : "tab"}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {message && <p role="status">{message}</p>}
      {tab === "patterns" && (
        <div className="pattern-grid">
          {analysis.patterns.map((p) => (
            <PatternCard
              key={p.id}
              catalog={catalog}
              analysis={analysis}
              pattern={p}
              canEdit={client.mode === "desktop"}
              openRound={openRound}
              onDraft={async () => {
                const plan = draftPlan(catalog, analysis, p);
                if (!plan) {
                  setMessage("代表回合在 20 秒内没有 CT 道具，无法生成草稿。");
                  return;
                }
                try {
                  await client.write(`plans/${plan.id}`, "PUT", plan);
                  setMessage(
                    `已在“控图与反制”生成草稿：${plan.title}（${plan.steps.length} 颗道具），请核对后发布。`,
                  );
                  onRefresh();
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            />
          ))}
        </div>
      )}
      {tab === "teams" && <Teams catalog={catalog} analysis={analysis} />}
      {tab === "context" && <Context analysis={analysis} />}
      {tab === "spots" && <Spots catalog={catalog} analysis={analysis} />}
      {tab === "method" && <Method analysis={analysis} />}
    </>
  );
}

function PatternCard({
  catalog,
  analysis,
  pattern: p,
  canEdit,
  openRound,
  onDraft,
}: {
  catalog: Catalog;
  analysis: CTAnalysis;
  pattern: CTPattern;
  canEdit: boolean;
  openRound: (id: string) => void;
  onDraft: () => void;
}) {
  const teams = Object.entries(p.teams)
    .filter(([t]) => t && t !== "null")
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  return (
    <article className="panel pattern-card">
      <div className="section-line">
        <div>
          <h2>{p.name}</h2>
          <p className="micro">
            论文命名：{p.paper_name}（{p.paper_name_en}） · {p.name_source}
          </p>
        </div>
        <span className="side CT">CT</span>
      </div>
      <p className="muted">{p.rationale}</p>
      <div className="pattern-facts">
        <span>
          <strong>{p.rounds}</strong> 回合
        </span>
        <span>
          <strong>{pct(p.ct_win_rate)}</strong> CT 胜率
        </span>
        <span>
          <strong>{pct(p.rounds / analysis.rounds)}</strong> 出现率
        </span>
      </div>
      <div className="share-stack">
        {["10", "15", "20"].map((s) =>
          p.shares[s] ? (
            <ShareBar key={s} label={`${s} 秒`} shares={p.shares[s]} />
          ) : null,
        )}
      </div>
      <h3>15 秒常见人数分配</h3>
      <div className="chips">
        {p.setups.slice(0, 4).map((s) => (
          <span className="chip" key={s.setup}>
            {s.setup} <b>{s.rounds}</b>
          </span>
        ))}
      </div>
      <h3>常见站位</h3>
      <div className="chips">
        {p.top_places.slice(0, 5).map((s) => (
          <span className="chip" key={s.place}>
            {placeName(catalog, analysis.map, s.place)} <b>{pct(s.share)}</b>
          </span>
        ))}
      </div>
      {p.utility_per_round.length > 0 && (
        <>
          <h3>20 秒内道具（每回合）</h3>
          <div className="chips">
            {p.utility_per_round.slice(0, 4).map((u) => (
              <span className="chip" key={`${u.kind}-${u.area}`}>
                {kindNames[u.kind] || u.kind} · {u.area} <b>{u.per_round}</b>
              </span>
            ))}
          </div>
        </>
      )}
      <p className="micro pattern-meta">
        经济：
        {Object.entries(p.economy)
          .sort((a, b) => b[1] - a[1])
          .map(([k, v]) => `${ECON_NAMES[k] || k} ${v}`)
          .join(" · ")}
        <br />
        常用战队：{teams.map(([t, v]) => `${t} ${v}`).join(" · ")}
      </p>
      <div className="card-actions">
        <button
          className="text-button"
          onClick={() => openRound(p.representative)}
        >
          <Eye size={14} /> 代表回合
        </button>
        {canEdit && (
          <button className="text-button" onClick={onDraft}>
            <ClipboardPlus size={14} /> 生成方案草稿
          </button>
        )}
      </div>
    </article>
  );
}

function Teams({
  catalog,
  analysis,
}: {
  catalog: Catalog;
  analysis: CTAnalysis;
}) {
  const habits = useMemo(
    () => [...(analysis.team_habits || [])].sort((a, b) => b.rounds - a.rounds),
    [analysis],
  );
  const [chosen, setTeam] = useState("");
  const habit: TeamHabit | undefined =
    habits.find((h) => h.team === chosen) || habits[0];
  if (!habit)
    return (
      <div className="empty">
        <h3>样本不足</h3>
        <p>每支战队至少需要 15 个 CT 回合才会生成习惯分析。</p>
      </div>
    );
  const sig = habit.differs_from_league;
  return (
    <section className="panel team-habits">
      <div className="section-line">
        <h2>
          {habit.team} · {analysis.map.replace("de_", "")} CT
        </h2>
        <select
          aria-label="选择战队"
          value={habit.team}
          onChange={(e) => setTeam(e.target.value)}
        >
          {habits.map((h) => (
            <option key={h.team} value={h.team}>
              {h.team}（{h.rounds} 回合）
            </option>
          ))}
        </select>
      </div>
      <p className="muted">
        {habit.rounds} 个 CT 回合 · {habit.matches} 张地图 · CT 胜率{" "}
        {pct(habit.ct_win_rate)}。阵型偏好与全体职业队相比：χ²={" "}
        {sig.chi2?.toFixed(1) ?? "—"}，Holm 校正 p={pValue(sig.p_holm)}
        {sig.p_holm != null && sig.p_holm < 0.05
          ? "，差异显著。"
          : "，差异不显著——这支队的阵型选择接近联盟平均，个性主要体现在选手站位上。"}
      </p>
      <h3>阵型偏好（本队 / 全体）</h3>
      <div className="mix-bars">
        {analysis.patterns.map((p, i) => (
          <div key={p.id} className="mix-bar">
            <span className="micro">{p.name}</span>
            <div>
              <i
                style={{ width: `${(habit.pattern_shares[i] || 0) * 100}%` }}
              />
              <em
                style={{ width: `${(habit.league_shares[i] || 0) * 100}%` }}
              />
            </div>
            <span className="micro">
              {pct(habit.pattern_shares[i])} / {pct(habit.league_shares[i])}
            </span>
          </div>
        ))}
      </div>
      <h3>常用人数分配（15 秒）</h3>
      <div className="chips">
        {habit.top_setups.map((s) => (
          <span className="chip" key={s.setup}>
            {s.setup} <b>{pct(s.share)}</b>
          </span>
        ))}
      </div>
      <h3>选手位置习惯</h3>
      <div className="role-table" role="table" aria-label="选手位置习惯">
        <div role="row" className="role-head">
          <span role="columnheader">选手</span>
          <span role="columnheader">15 秒常站位置</span>
          <span role="columnheader">固定程度</span>
          <span role="columnheader">10→20 秒常见移动</span>
        </div>
        {habit.roles.map((r) => (
          <div role="row" key={r.player}>
            <strong role="cell">{r.player}</strong>
            <span role="cell">
              {r.spots
                .map(
                  (s) =>
                    `${placeName(catalog, analysis.map, s.spot)} ${pct(s.share)}`,
                )
                .join("；")}
            </span>
            <span role="cell">{pct(r.consistency)}</span>
            <span role="cell">
              {r.rotations.length
                ? r.rotations
                    .slice(0, 2)
                    .map(
                      (m) =>
                        `${moveName(catalog, analysis.map, m.move)} ${pct(m.share)}`,
                    )
                    .join("；")
                : "基本不动"}
            </span>
          </div>
        ))}
      </div>
      <h3>20 秒内道具习惯（每回合 · 本队 / 全体）</h3>
      <div className="chips">
        {habit.utility_per_round.slice(0, 8).map((u) => (
          <span
            className={
              u.per_round >= u.league_per_round * 1.5 && u.per_round >= 0.2
                ? "chip strong"
                : "chip"
            }
            key={`${u.kind}-${u.area}`}
          >
            {kindNames[u.kind] || u.kind} · {AREA_NAMES[u.area] || u.area}{" "}
            <b>
              {u.per_round} / {u.league_per_round}
            </b>
          </span>
        ))}
      </div>
      <p className="micro">
        高亮项：本队用量至少是全体职业队的 1.5 倍。固定程度 =
        该选手最常站位置的回合占比。
      </p>
    </section>
  );
}

function Context({ analysis }: { analysis: CTAnalysis }) {
  const tests = analysis.context_tests || [];
  return (
    <section className="panel">
      <h2>哪些情境会改变 CT 阵型？</h2>
      <p className="muted">
        卡方独立性检验，多重比较用 Holm 校正（与论文相同）。Cramér's V
        衡量关联强度：0.1 弱、0.3 中、0.5 强。期望频数小于 5 时结论不可靠。
      </p>
      <div
        className="role-table context-table"
        role="table"
        aria-label="情境检验"
      >
        <div role="row" className="role-head">
          <span role="columnheader">情境</span>
          <span role="columnheader">χ² (自由度)</span>
          <span role="columnheader">Holm p</span>
          <span role="columnheader">Cramér's V</span>
          <span role="columnheader">结论</span>
        </div>
        {tests.map((t) => (
          <div role="row" key={t.variable}>
            <strong role="cell">
              {VARIABLE_NAMES[t.variable] || t.variable}
            </strong>
            <span role="cell">
              {t.chi2?.toFixed(1) ?? "—"} ({t.dof})
            </span>
            <span role="cell">{pValue(t.p_holm)}</span>
            <span role="cell">{t.cramers_v?.toFixed(2) ?? "—"}</span>
            <span role="cell">
              {!t.reliable
                ? "样本不足，仅供参考"
                : t.p_holm != null && t.p_holm < 0.05
                  ? "显著相关"
                  : "未发现显著关联"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Spots({
  catalog,
  analysis,
}: {
  catalog: Catalog;
  analysis: CTAnalysis;
}) {
  const spots = analysis.spots || [];
  if (!spots.length)
    return (
      <div className="empty">
        <h3>样本不足</h3>
        <p>至少 40 个 CT 回合才会学习站位点。</p>
      </div>
    );
  const xs = spots.map((s) => s.x);
  const ys = spots.map((s) => s.y);
  const [x0, x1, y0, y1] = [
    Math.min(...xs),
    Math.max(...xs),
    Math.min(...ys),
    Math.max(...ys),
  ];
  const span = Math.max(x1 - x0, y1 - y0, 1);
  const max = Math.max(...spots.map((s) => s.points));
  const sx = (x: number) => 110 + ((x - x0) / span) * 580;
  const sy = (y: number) => 30 + ((y1 - y) / span) * 580;
  return (
    <section className="panel">
      <h2>学到的 CT 站位点</h2>
      <p className="muted">
        把所有 CT 选手在 10–20 秒的位置聚成 {spots.length}
        个站位点（俯视坐标，上为地图北）。点越大，职业选手站在这里的次数越多。战队习惯里的“号位”指同一区域内的不同站位点。
      </p>
      <svg
        className="spot-map"
        viewBox={`0 0 800 ${Math.max(200, sy(y0) + 40)}`}
        role="img"
        aria-label="CT 站位点分布"
      >
        {spots.map((s) => (
          <g key={s.id}>
            <circle
              cx={sx(s.x)}
              cy={sy(s.y)}
              r={4 + 12 * Math.sqrt(s.points / max)}
            />
            <text
              x={sx(s.x) + (sx(s.x) > 400 ? -10 : 10)}
              y={sy(s.y) + 4}
              textAnchor={sx(s.x) > 400 ? "end" : "start"}
            >
              <title>{placeName(catalog, analysis.map, s.name)}</title>
              {shortName(catalog, analysis.map, s.name)}
            </text>
          </g>
        ))}
      </svg>
    </section>
  );
}

function Method({ analysis }: { analysis: CTAnalysis }) {
  const c = analysis.citation;
  return (
    <section className="panel method">
      <h2>
        <BookOpen size={17} /> 方法与引用
      </h2>
      <p>
        本页的阵型分析基于：{c.authors}. “{c.title}.” <i>{c.venue}</i>. DOI{" "}
        <a href={c.url} target="_blank" rel="noreferrer">
          {c.doi}
        </a>
        ；作者代码{" "}
        <a href={c.code} target="_blank" rel="noreferrer">
          {c.code.replace("https://", "")}
        </a>
        （MIT 许可）。
      </p>
      <h3>沿用论文的部分</h3>
      <ul>
        <li>
          冻结时间结束后 10/12/15/18/20 秒五个快照，按 A / B / 中路 / CT
          后场统计 CT 人数。
        </li>
        <li>K-Means 聚类，K 由轮廓系数、DBI、CH 三项指标的平均排名选出。</li>
        <li>按论文的 15 秒阈值规则草拟阵型名称，标注为“待人工确认”。</li>
        <li>
          经济分档（手枪 / &lt;10000 / &lt;25000 /
          长枪）、比分态势、上一回合信息的卡方检验 + Holm 校正。
        </li>
      </ul>
      <h3>本项目的改进</h3>
      <ul>
        <li>
          用论文自己的对照结论（计数基线轮廓系数 0.30 高于 TAGNet 的
          0.18，跨种子 ARI 约
          0.52）选择计数基线作为阵型主方法，并报告重抽样稳定性 ARI。
        </li>
        <li>
          K 的候选从 4 起步，且每类至少占 3% 回合，避免只分出“堆点 /
          分散”两类而无法教学。
        </li>
        <li>
          新增“站位点”：直接对选手坐标聚类，得到每名选手的固定位置、10→20
          秒移动和道具习惯。在留一场比赛的检验里，它区分战队风格的能力明显强于阵型比例（详见项目文档的研究对照）。
        </li>
        <li>
          论文只有 Dust2；这里覆盖 Mirage、Ancient
          等地图，区域划分可在“数据与内容管理”里修改。
        </li>
      </ul>
      <h3>阵型数量选择</h3>
      <div className="role-table" role="table" aria-label="K 选择">
        <div role="row" className="role-head">
          <span role="columnheader">K</span>
          <span role="columnheader">轮廓系数</span>
          <span role="columnheader">DBI</span>
          <span role="columnheader">CH</span>
          <span role="columnheader">平均排名</span>
        </div>
        {analysis.k_selection.map((r) => (
          <div
            role="row"
            key={r.k}
            className={r.k === analysis.k ? "chosen" : ""}
          >
            <strong role="cell">
              {r.k}
              {r.k === analysis.k ? " ✓" : r.eligible ? "" : "（类过小）"}
            </strong>
            <span role="cell">{r.silhouette?.toFixed(3) ?? "—"}</span>
            <span role="cell">{r.davies_bouldin?.toFixed(3) ?? "—"}</span>
            <span role="cell">{r.calinski_harabasz?.toFixed(1) ?? "—"}</span>
            <span role="cell">{r.mean_rank?.toFixed(2) ?? "—"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
