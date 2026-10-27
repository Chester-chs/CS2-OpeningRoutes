import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Bookmark,
  CheckCircle2,
  Crosshair,
  Database,
  ExternalLink,
  Flame,
  GitCompareArrows,
  Map as MapIcon,
  Search,
  Shield,
  Swords,
  Target,
  Video,
} from "lucide-react";
import {
  areaOptions,
  DataClient,
  EMPTY,
  filterThrows,
  kindNames,
  pistolSummary,
  visibleRounds,
} from "./data";
import type { Catalog, Filters, Round, Throw } from "./types";
import Detail from "./Detail";
import Manage from "./Manage";
import Plans from "./Plans";
import Timeline from "./Timeline";

const nav = [
  { id: "home", label: "发现", icon: Crosshair },
  { id: "plans", label: "控图与反制", icon: MapIcon },
  { id: "pistol", label: "手枪局", icon: Swords },
  { id: "utility", label: "道具库", icon: Flame },
  { id: "pro", label: "职业案例", icon: Video },
  { id: "saved", label: "我的收藏", icon: Bookmark },
];
const titles: Record<string, string> = {
  home: "从比赛里找到答案。",
  plans: "控图与反制",
  pistol: "手枪局",
  utility: "道具库",
  pro: "职业案例",
  saved: "我的收藏",
  manage: "数据与内容管理",
};

function savedIds(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem("or-favorites") || "[]");
    return Array.isArray(value)
      ? value.filter((x) => typeof x === "string")
      : [];
  } catch {
    return [];
  }
}

export default function App() {
  const [client] = useState(() => new DataClient());
  const [catalog, setCatalog] = useState<Catalog>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState("home");
  const [filters, setFilters] = useState<Filters>({});
  const [limit, setLimit] = useState(24);
  const [detail, setDetail] = useState<{
    id: string;
    kind: "throw" | "round";
  } | null>(null);
  const [favorites, setFavorites] = useState(savedIds);
  const [compare, setCompare] = useState<string[]>([]);
  const [showCompare, setShowCompare] = useState(false);
  const [storageMessage, setStorageMessage] = useState("");
  const refresh = useCallback(() => {
    void client
      .catalog()
      .then(setCatalog)
      .catch((e) => setError(e.message));
  }, [client]);
  useEffect(() => {
    let active = true;
    client
      .init()
      .then((c) => {
        if (active) {
          setCatalog(c);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [client]);
  function toggleFavorite(id: string) {
    setFavorites((previous) => {
      const next = previous.includes(id)
        ? previous.filter((x) => x !== id)
        : [...previous, id];
      try {
        localStorage.setItem("or-favorites", JSON.stringify(next));
      } catch {
        setStorageMessage("收藏保存失败，请检查浏览器存储空间。");
      }
      return next;
    });
  }
  function navigate(id: string) {
    setPage(id);
    setLimit(24);
    setCompare([]);
    setShowCompare(false);
  }
  function update(key: keyof Filters, value: string) {
    setFilters((v) => ({
      ...v,
      [key]: value,
      ...(key === "side" ? { result: "" } : {}),
    }));
    setLimit(24);
  }
  const throws = useMemo(
    () =>
      filterThrows(catalog, filters).filter(
        (t) => page !== "saved" || favorites.includes(t.id),
      ),
    [catalog, filters, page, favorites],
  );
  const rounds = useMemo(
    () =>
      visibleRounds(catalog, filters, page === "pistol").filter(
        (r) => page !== "saved" || favorites.includes(r.id),
      ),
    [catalog, filters, page, favorites],
  );
  const summary = pistolSummary(rounds, filters.side);
  const unique = (key: "player" | "team") =>
    [...new Set(catalog.throws.map((t) => t[key]))].filter(Boolean).sort();
  const maps = [...new Set(catalog.matches.map((m) => m.map))].sort();
  const complete = catalog.throws.filter(
    (t) => t.gaps.length === 0 && t.teaching.status === "published",
  ).length;
  const verifiedMatches = catalog.matches.filter((m) => m.source.verified);
  const isRounds = page === "pistol" || page === "pro";
  const gear = new Map<string, number>();
  if (page === "pistol")
    rounds.forEach((r) =>
      r.equipment
        .filter(
          (e) =>
            (!filters.side || e.side === filters.side) &&
            (!filters.player || e.player === filters.player) &&
            (!filters.team || e.team === filters.team),
        )
        .forEach((e) =>
          e.inventory?.forEach((item) =>
            gear.set(item, (gear.get(item) || 0) + 1),
          ),
        ),
    );
  function backup() {
    const notes: Record<string, string> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith("or-note-"))
        notes[key.slice(8)] = localStorage.getItem(key) || "";
    }
    const blob = new Blob(
      [JSON.stringify({ version: 1, favorites, notes }, null, 2)],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "openingroutes-learning-notes.json";
    link.click();
    URL.revokeObjectURL(url);
  }
  async function restore(file?: File) {
    if (!file) return;
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error("笔记文件过大。");
      const value = JSON.parse(await file.text());
      if (
        value.version !== 1 ||
        !Array.isArray(value.favorites) ||
        typeof value.notes !== "object" ||
        value.notes === null
      )
        throw new Error("不支持的笔记格式。");
      const valid = (x: unknown): x is string =>
        typeof x === "string" && /^[A-Za-z0-9_-]{1,150}$/.test(x);
      const merged = [
        ...new Set([...favorites, ...value.favorites.filter(valid)]),
      ];
      for (const [id, note] of Object.entries(value.notes))
        if (valid(id) && typeof note === "string")
          localStorage.setItem(`or-note-${id}`, note);
      localStorage.setItem("or-favorites", JSON.stringify(merged));
      setFavorites(merged);
      setStorageMessage("学习记录已恢复到当前浏览器。");
    } catch (e) {
      setStorageMessage((e as Error).message);
    }
  }
  return (
    <div className="app-shell" data-ready={!loading}>
      <aside className="sidebar">
        <button
          className="brand"
          aria-label="返回发现"
          onClick={() => navigate("home")}
        >
          <span className="brand-mark">
            <Crosshair size={24} />
          </span>
          <span>
            OPENING
            <span className="brand-bottom">
              ROUTES <small>CS2</small>
            </span>
          </span>
        </button>
        <p className="nav-caption">学习工作台</p>
        <nav aria-label="主要导航">
          {nav.map((n) => (
            <button
              key={n.id}
              aria-current={page === n.id ? "page" : undefined}
              className={page === n.id ? "nav-item active" : "nav-item"}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={18} />
              <span>{n.label}</span>
              {n.id === "saved" && favorites.length > 0 && (
                <small>{favorites.length}</small>
              )}
            </button>
          ))}
        </nav>
        {client.mode === "desktop" && (
          <div className="admin-nav">
            <p className="nav-caption">本地资料</p>
            <button
              className={page === "manage" ? "nav-item active" : "nav-item"}
              onClick={() => navigate("manage")}
            >
              <Database size={18} />
              <span>数据与内容管理</span>
            </button>
          </div>
        )}
        <div className="sidebar-foot">
          <span className="live-dot" />
          <span>
            {client.mode === "desktop"
              ? "本地资料库"
              : client.isPreview
                ? "网页版 · 本地提取记录预览"
                : "网页版 · 已审核内容"}
          </span>
          <small>v0.2.0 {client.version && `/ ${client.version}`}</small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            OPENINGROUTES <span>/</span> {titles[page]}
          </div>
          <span className="top-badge">
            <Shield size={13} />
            职业比赛依据
          </span>
        </header>
        <main>
          {page === "home" ? (
            <section className="hero">
              <div className="hero-copy">
                <p className="eyebrow">
                  <span className="live-dot" /> PRO DEMO. REAL CONTEXT.
                </p>
                <h1>
                  从比赛里
                  <br />
                  找到答案。
                </h1>
                <p>
                  看懂职业选手为什么丢这颗道具，
                  <br />
                  再把站位、时机与配合，带进你的下一局。
                </p>
                <button className="button" onClick={() => navigate("utility")}>
                  浏览道具库 <ArrowRight size={17} />
                </button>
                <button
                  className="text-button light"
                  onClick={() => navigate("pistol")}
                >
                  研究手枪局 ↗
                </button>
              </div>
              <div className="hero-art" aria-hidden="true">
                <svg viewBox="0 0 440 330">
                  <defs>
                    <pattern
                      id="hero-grid"
                      width="28"
                      height="28"
                      patternUnits="userSpaceOnUse"
                    >
                      <path
                        d="M28 0H0V28"
                        fill="none"
                        stroke="#35554a"
                        strokeWidth=".6"
                      />
                    </pattern>
                  </defs>
                  <rect width="440" height="330" fill="url(#hero-grid)" />
                  <path
                    d="M48 260V196H132V120H220V58H372V139H286V222H213V281H113"
                    fill="#294338"
                    stroke="#668477"
                    strokeWidth="1"
                  />
                  <path
                    d="M77 245Q107 175 159 156T294 90"
                    stroke="#a6d8b0"
                    fill="none"
                    strokeWidth="2"
                    strokeDasharray="6 7"
                  />
                  <circle cx="77" cy="245" r="7" fill="#e1b85d" />
                  <circle
                    cx="294"
                    cy="90"
                    r="35"
                    fill="#b1dfba"
                    opacity=".08"
                  />
                  <circle
                    cx="294"
                    cy="90"
                    r="20"
                    fill="none"
                    stroke="#b1dfba"
                    opacity=".4"
                  />
                  <circle cx="294" cy="90" r="5" fill="#b1dfba" />
                  <text x="64" y="277" fill="#e1b85d" fontSize="11">
                    POSITION
                  </text>
                  <text x="320" y="95" fill="#b1dfba" fontSize="11">
                    CONTROL
                  </text>
                  <text x="205" y="315" fill="#759183" fontSize="10">
                    READ THE PLAY. LEARN THE DETAILS.
                  </text>
                </svg>
                <div className="art-label">
                  <Target size={17} />
                  每一次投掷，都有上下文。
                </div>
              </div>
            </section>
          ) : (
            <div className="page-title">
              <p className="eyebrow">OPENINGROUTES / LEARNING LIBRARY</p>
              <h1>{titles[page]}</h1>
              <p className="muted">
                {page === "pistol"
                  ? "独立研究正式手枪局，比较双方的装备、路线与结果。"
                  : page === "utility"
                    ? "从职业比赛提取的真实投掷，逐条整理成可复现教学。"
                    : page === "pro"
                      ? "结合全回合路线，理解职业选手的选择与后续行动。"
                      : page === "saved"
                        ? "收藏和练习笔记保存在本机浏览器。"
                        : ""}
              </p>
            </div>
          )}
          {loading && (
            <p role="status" className="notice">
              正在读取学习资料…
            </p>
          )}
          {error && (
            <div role="alert" className="notice">
              {error}
              <button
                className="text-button"
                onClick={() => window.location.reload()}
              >
                重新加载
              </button>
            </div>
          )}
          {page === "home" && (
            <>
              <div className="stats">
                <Stat
                  label="已导入比赛地图"
                  value={catalog.matches.length}
                  detail={`${verifiedMatches.length} 份来源已核对`}
                />
                <Stat
                  label="真实投掷记录"
                  value={catalog.throws.length}
                  detail="保留选手、回合与出手依据"
                />
                <Stat
                  label="正式手枪局"
                  value={
                    catalog.rounds.filter(
                      (r) =>
                        r.is_pistol &&
                        verifiedMatches.some((m) => m.id === r.match_id),
                    ).length
                  }
                  detail="胜负案例共同保留"
                />
                <Stat
                  label="完整教学"
                  value={complete}
                  detail="通过来源与复现检查"
                />
              </div>
              <div className="section-line">
                <h2>选择你的学习起点</h2>
                <span className="micro">以比赛为依据 · 以复现为目标</span>
              </div>
              <div className="entry-grid">
                {[
                  {
                    id: "plans",
                    icon: MapIcon,
                    title: "先理解控图",
                    copy: "从区域争夺进入，串起双方的道具与反制。",
                  },
                  {
                    id: "pistol",
                    icon: Swords,
                    title: "研究手枪局",
                    copy: "看装备怎么分、队伍怎么展开，如何赢下第一局。",
                  },
                  {
                    id: "utility",
                    icon: Flame,
                    title: "学会一颗道具",
                    copy: "查找投掷、对照职业示范，逐步补齐操作细节。",
                  },
                ].map((entry) => (
                  <button
                    className="entry"
                    key={entry.id}
                    onClick={() => navigate(entry.id)}
                  >
                    <entry.icon size={23} />
                    <h3>{entry.title}</h3>
                    <p>{entry.copy}</p>
                    <ArrowRight size={17} />
                  </button>
                ))}
              </div>
              <Coverage catalog={catalog} />
              <div className="section-line">
                <h2>最近提取的道具</h2>
                <button
                  className="text-button"
                  onClick={() => navigate("utility")}
                >
                  查看全部 <ArrowRight size={14} />
                </button>
              </div>
            </>
          )}
          {page === "manage" ? (
            <Manage
              client={client}
              catalog={catalog}
              onRefresh={refresh}
              onOpenRound={(id) => setDetail({ id, kind: "round" })}
            />
          ) : page === "plans" ? (
            <Plans
              client={client}
              catalog={catalog}
              onRefresh={refresh}
              openThrow={(id) => setDetail({ id, kind: "throw" })}
            />
          ) : (
            <>
              {page !== "home" && (
                <section className="filters" aria-label="内容筛选">
                  <div className="search-box">
                    <Search size={17} />
                    <input
                      aria-label="搜索选手、区域或教学"
                      placeholder="搜索选手、区域或教学…"
                      value={filters.query || ""}
                      onChange={(e) => update("query", e.target.value)}
                    />
                  </div>
                  <div className="filter-row">
                    <Select
                      label="地图"
                      value={filters.map}
                      options={maps.map((m) => [m, m.replace("de_", "")])}
                      change={(v) => update("map", v)}
                    />
                    <Select
                      label="阵营"
                      value={filters.side}
                      options={["CT", "T"].map((s) => [s, s])}
                      change={(v) => update("side", v)}
                    />
                    {!isRounds && (
                      <Select
                        label="道具类型"
                        value={filters.kind}
                        options={Object.entries(kindNames)}
                        change={(v) => update("kind", v)}
                      />
                    )}
                    {!isRounds && (
                      <Select
                        label="区域"
                        value={filters.area}
                        options={areaOptions(catalog, filters.map).map((a) => [
                          a,
                          a,
                        ])}
                        change={(v) => update("area", v)}
                      />
                    )}
                    <Select
                      label="选手"
                      value={filters.player}
                      options={unique("player").map((p) => [p, p])}
                      change={(v) => update("player", v)}
                    />
                    <Select
                      label="战队"
                      value={filters.team}
                      options={unique("team").map((p) => [p, p])}
                      change={(v) => update("team", v)}
                    />
                    <Select
                      label="比赛"
                      value={filters.match}
                      options={catalog.matches.map((m) => [
                        m.id,
                        `${m.source.date} ${m.map.replace("de_", "")} ${m.source.match}`,
                      ])}
                      change={(v) => update("match", v)}
                    />
                  </div>
                  <div className="filter-row">
                    <label className="date-filter">
                      从
                      <input
                        aria-label="起始日期"
                        type="date"
                        value={filters.dateFrom || ""}
                        onChange={(e) => update("dateFrom", e.target.value)}
                      />
                    </label>
                    <label className="date-filter">
                      至
                      <input
                        aria-label="结束日期"
                        type="date"
                        value={filters.dateTo || ""}
                        onChange={(e) => update("dateTo", e.target.value)}
                      />
                    </label>
                    {page === "pistol" ? (
                      <Select
                        label="回合结果"
                        value={filters.result}
                        options={
                          filters.side
                            ? [
                                ["win", "胜利"],
                                ["loss", "失利"],
                              ]
                            : [
                                ["T", "T 获胜"],
                                ["CT", "CT 获胜"],
                              ]
                        }
                        change={(v) => update("result", v)}
                      />
                    ) : (
                      !isRounds && (
                        <Select
                          label="教学状态"
                          value={filters.status}
                          options={["complete", "pending"].map((s) => [
                            s,
                            s === "complete" ? "资料齐全" : "教学待完善",
                          ])}
                          change={(v) => update("status", v)}
                        />
                      )
                    )}
                    <button
                      className="text-button"
                      onClick={() => {
                        setFilters({});
                        setLimit(24);
                      }}
                    >
                      清除筛选
                    </button>
                  </div>
                </section>
              )}
              {page === "pistol" && (
                <>
                  <div className="stats">
                    <Stat
                      label="正式手枪局样本"
                      value={summary.samples}
                      detail="单位：唯一回合"
                    />
                    <Stat
                      label={filters.side ? `${filters.side} 获胜` : "T 获胜"}
                      value={summary.wins ?? summary.tWins}
                      detail="仅统计结果已知的回合"
                    />
                    <Stat
                      label={filters.side ? `${filters.side} 失利` : "CT 获胜"}
                      value={summary.losses ?? summary.ctWins}
                      detail="保留失败案例"
                    />
                    <Stat
                      label="比赛地图范围"
                      value={new Set(rounds.map((r) => r.match_id)).size}
                      detail={`${rounds.reduce((n, r) => n + r.equipment.filter((e) => !filters.side || e.side === filters.side).length, 0)} 人次装备快照`}
                    />
                  </div>
                  <section className="gear-distribution">
                    <h3>
                      装备选择分布{" "}
                      <span className="micro">
                        按冻结结束快照计数 · 同一人可持有多件
                      </span>
                    </h3>
                    <div className="chips">
                      {[...gear.entries()]
                        .sort((a, b) => b[1] - a[1])
                        .map(([name, count]) => (
                          <span className="chip" key={name}>
                            {name} <b>{count}</b>
                          </span>
                        ))}
                    </div>
                  </section>
                </>
              )}
              {page === "saved" && (
                <div className="actions">
                  <button className="button secondary" onClick={backup}>
                    <ArrowDownToLine size={15} />
                    导出学习记录
                  </button>
                  <label className="button secondary file-button">
                    恢复学习记录
                    <input
                      type="file"
                      accept="application/json"
                      aria-label="恢复学习记录"
                      onChange={(e) => void restore(e.target.files?.[0])}
                    />
                  </label>
                  <span className="micro">
                    当前浏览器保存，未提供跨设备同步。
                  </span>
                </div>
              )}
              {storageMessage && (
                <p role="alert" className="notice">
                  {storageMessage}
                </p>
              )}
              {page !== "home" && (
                <div className="section-line results">
                  <p>
                    {isRounds ? "回合" : "道具"}{" "}
                    <strong>{isRounds ? rounds.length : throws.length}</strong>{" "}
                    条{page === "saved" && ` · 已收藏回合 ${rounds.length} 个`}
                  </p>
                  {!isRounds && page !== "saved" && (
                    <span className="micro">勾选两条记录可对比</span>
                  )}
                </div>
              )}
              {showCompare && compare.length === 2 && (
                <section className="compare-panel">
                  <div className="section-line">
                    <h2>投掷与完整回合对比</h2>
                    <button
                      className="text-button"
                      onClick={() => setShowCompare(false)}
                    >
                      收起对比
                    </button>
                  </div>
                  <CompareVariants
                    ids={compare}
                    catalog={catalog}
                    canEdit={client.mode === "desktop"}
                    merge={async (ids) => {
                      await client.write("variants/merge", "POST", { ids });
                      refresh();
                    }}
                  />
                  <div className="comparison">
                    {compare.map((id) => {
                      const t = catalog.throws.find((v) => v.id === id)!;
                      const r = catalog.rounds.find(
                        (v) => v.id === t.round_id,
                      )!;
                      return (
                        <div key={id}>
                          <h3>
                            {t.player} · R{t.round_number} · {t.time}s
                          </h3>
                          <Timeline client={client} round={r} throwRow={t} />
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
              {isRounds ? (
                <div className="round-grid">
                  {rounds.slice(0, limit).map((r) => (
                    <RoundCard
                      key={r.id}
                      row={r}
                      catalog={catalog}
                      onOpen={() => setDetail({ id: r.id, kind: "round" })}
                    />
                  ))}
                </div>
              ) : (
                <div className="card-grid">
                  {throws.slice(0, page === "home" ? 6 : limit).map((t) => (
                    <article className="throw-item" key={t.id}>
                      <ThrowCard
                        row={t}
                        onOpen={() => setDetail({ id: t.id, kind: "throw" })}
                      />
                      {page !== "home" && (
                        <label className="compare-check">
                          <input
                            type="checkbox"
                            aria-label={`对比 ${t.player} 第${t.round_number}回合 ${t.tick}`}
                            checked={compare.includes(t.id)}
                            onChange={() =>
                              setCompare((v) =>
                                v.includes(t.id)
                                  ? v.filter((id) => id !== t.id)
                                  : v.length < 2
                                    ? [...v, t.id]
                                    : [v[1], t.id],
                              )
                            }
                          />
                          加入对比
                        </label>
                      )}
                    </article>
                  ))}
                </div>
              )}
              {page === "saved" && rounds.length > 0 && (
                <>
                  <h2>收藏的回合</h2>
                  <div className="round-grid">
                    {rounds.map((r) => (
                      <RoundCard
                        key={r.id}
                        row={r}
                        catalog={catalog}
                        onOpen={() => setDetail({ id: r.id, kind: "round" })}
                      />
                    ))}
                  </div>
                </>
              )}
              {!loading &&
                ((isRounds && rounds.length === 0) ||
                  (!isRounds && throws.length === 0)) && (
                  <div className="empty">
                    <Target size={32} />
                    <h3>这里还没有符合条件的内容</h3>
                    <p>
                      {catalog.matches.length
                        ? "尝试调整筛选，或继续整理比赛案例。"
                        : "从一份职业比赛 Demo 开始，建立你的学习资料库。"}
                    </p>
                    {client.mode === "desktop" && !catalog.matches.length && (
                      <button
                        className="button"
                        onClick={() => navigate("manage")}
                      >
                        导入职业 Demo <ArrowRight size={15} />
                      </button>
                    )}
                  </div>
                )}
              {page !== "home" &&
                (isRounds ? rounds.length : throws.length) > limit && (
                  <button
                    className="button secondary load-more"
                    onClick={() => setLimit((n) => n + 24)}
                  >
                    加载更多（已展示 {limit} /{" "}
                    {isRounds ? rounds.length : throws.length}）
                  </button>
                )}
              {compare.length === 2 && (
                <div className="compare-bar">
                  <GitCompareArrows size={18} />
                  <span>已选择两条真实投掷</span>
                  <button
                    className="button"
                    onClick={() => {
                      setShowCompare(true);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  >
                    开始对比
                  </button>
                  <button
                    className="text-button"
                    onClick={() => {
                      setCompare([]);
                      setShowCompare(false);
                    }}
                  >
                    清空
                  </button>
                </div>
              )}
            </>
          )}
          <footer>
            OPENINGROUTES <span>观察比赛 · 理解选择 · 复现练习</span>
            <small>原始事实与教学解释分别核验</small>
          </footer>
        </main>
      </div>
      {detail && (
        <Detail
          key={detail.id}
          {...detail}
          catalog={catalog}
          client={client}
          onClose={() => setDetail(null)}
          onSaved={refresh}
          onOpen={(id) => setDetail({ id, kind: "throw" })}
          favorites={favorites}
          toggleFavorite={toggleFavorite}
        />
      )}
    </div>
  );
}

function Select({
  label,
  value,
  options,
  change,
}: {
  label: string;
  value?: string;
  options: string[][];
  change: (value: string) => void;
}) {
  return (
    <label className="select-label">
      <span>{label}</span>
      <select
        aria-label={label}
        value={value || ""}
        onChange={(e) => change(e.target.value)}
      >
        <option value="">全部{label}</option>
        {options.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}
function Stat({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
      <small>{detail}</small>
    </div>
  );
}
function CompareVariants({
  ids,
  catalog,
  canEdit,
  merge,
}: {
  ids: string[];
  catalog: Catalog;
  canEdit: boolean;
  merge: (ids: string[]) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const rows = ids.map((id) => catalog.throws.find((t) => t.id === id));
  const variantIds = rows.map((t) => t?.variant_id || "");
  const same = variantIds[0] && variantIds[0] === variantIds[1];
  const mergeable =
    !same &&
    variantIds.every(Boolean) &&
    rows[0]?.map === rows[1]?.map &&
    rows[0]?.kind === rows[1]?.kind &&
    rows[0]?.side === rows[1]?.side;
  return (
    <p className="variant-line">
      {same
        ? "两条记录属于同一投法变体。"
        : "两条记录目前属于不同投法变体（自动归组只作候选）。"}
      {canEdit && mergeable && (
        <button
          className="text-button"
          onClick={() =>
            void merge(variantIds)
              .then(() =>
                setMessage("已合并为同一投法，请在详情中补充名称并复核。"),
              )
              .catch((e) => setMessage(e.message))
          }
        >
          合并为同一投法
        </button>
      )}
      {message && <span role="status"> {message}</span>}
    </p>
  );
}
function ThrowCard({ row: t, onOpen }: { row: Throw; onOpen: () => void }) {
  const points = t.trajectory || [];
  const xs = points.map((p) => p[1]),
    ys = points.map((p) => p[2]);
  const minX = Math.min(...xs),
    minY = Math.min(...ys);
  const rangeX = Math.max(...xs) - minX,
    rangeY = Math.max(...ys) - minY;
  const plot = points
    .map(
      (p) =>
        `${20 + ((p[1] - minX) / Math.max(rangeX, 1)) * 270},${100 - ((p[2] - minY) / Math.max(rangeY, 1)) * 75}`,
    )
    .join(" ");
  return (
    <button data-testid="throw-card" className="throw-card" onClick={onOpen}>
      <div className={`card-visual ${t.kind}`}>
        <span className="map-label">
          {t.map.replace("de_", "").toUpperCase()}
        </span>
        <span className={`side ${t.side}`}>{t.side}</span>
        <svg viewBox="0 0 310 120" aria-hidden="true">
          <path
            d="M0 30H310M0 60H310M0 90H310M40 0V120M100 0V120M160 0V120M220 0V120M280 0V120"
            stroke="currentColor"
            opacity=".08"
          />
          {points.length > 0 ? (
            <polyline
              points={plot}
              stroke="currentColor"
              fill="none"
              strokeWidth="1.7"
            />
          ) : (
            <circle cx="155" cy="60" r="22" fill="none" stroke="currentColor" />
          )}
        </svg>
        <span className="visual-caption">
          {points.length ? "实际飞行轨迹 · XY 投影" : "轨迹待核验"}
        </span>
      </div>
      <div className="card-copy">
        <div className="section-line">
          <span className="kind">
            <Flame size={12} />
            {kindNames[t.kind] || t.kind}
          </span>
          <span className="micro">
            R{t.round_number} · {t.time.toFixed(1)}s
          </span>
        </div>
        <h3>
          {t.teaching.title || `${t.player} · ${kindNames[t.kind] || t.kind}`}
        </h3>
        <p>
          {t.teaching.area ||
            (t.origin_area
              ? `${t.origin_area} → ${t.effect_area || "落点区域未知"}`
              : "区域待整理")}{" "}
          <span>· {t.team || t.side}</span>
        </p>
        <div className="card-bottom">
          <span>{t.player}</span>
          <span className={t.gaps.length ? "status pending" : "status"}>
            {t.gaps.length ? (
              "教学待完善"
            ) : (
              <>
                <CheckCircle2 size={12} />
                资料齐全
              </>
            )}
          </span>
        </div>
      </div>
    </button>
  );
}
function RoundCard({
  row: r,
  catalog,
  onOpen,
}: {
  row: Round;
  catalog: Catalog;
  onOpen: () => void;
}) {
  const m = catalog.matches.find((m) => m.id === r.match_id)!;
  return (
    <button data-testid="round-card" className="round-card" onClick={onOpen}>
      <div className="section-line">
        <span className="eyebrow">
          {m.map.replace("de_", "").toUpperCase()}
        </span>
        <span className="tag">{r.is_pistol ? "手枪局" : "正式回合"}</span>
      </div>
      <div className="round-number">
        R{String(r.number).padStart(2, "0")}{" "}
        <span className={`side ${r.winner}`}>{r.winner || "未知"} 获胜</span>
      </div>
      <h3>{m.source.match}</h3>
      <p>
        {m.source.event} · {m.source.date}
      </p>
      <div className="round-fact">
        <span>首杀</span>
        <strong>
          {r.opening_kill
            ? `${r.opening_kill.attacker} → ${r.opening_kill.victim}`
            : "未记录"}
        </strong>
      </div>
      <div className="round-fact">
        <span>装备快照</span>
        <strong>
          {r.equipment.length} 名选手 · 全回合路线 <ArrowRight size={14} />
        </strong>
      </div>
    </button>
  );
}
function Coverage({ catalog }: { catalog: Catalog }) {
  return (
    <section className="coverage">
      <div>
        <Shield size={18} />
        <strong>当前内容覆盖</strong>
      </div>
      <p>
        {catalog.matches.length
          ? [
              ...new Set(catalog.matches.map((m) => m.map.replace("de_", ""))),
            ].join(" / ")
          : "尚未导入比赛"}
        <span>
          {" "}
          · {catalog.matches.length} 份比赛地图 · 教学按核验进度逐步补充
        </span>
      </p>
      <a
        href="https://github.com/Chester-chs/CS2-OpeningRoutes"
        target="_blank"
        rel="noreferrer"
        aria-label="查看项目介绍"
      >
        <ExternalLink size={16} />
      </a>
    </section>
  );
}
