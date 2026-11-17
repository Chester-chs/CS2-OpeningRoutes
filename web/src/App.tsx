import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  GitCompareArrows,
  Search,
  Target,
} from "lucide-react";
import {
  areaOptions,
  DataClient,
  EMPTY,
  filterThrows,
  isMisthrow,
  kindNames,
  mapOfThrow,
  mergeSlice,
  sliceOf,
  trajectoryPoints,
  pistolSummary,
  visibleRounds,
} from "./data";
import type { Catalog, Filters, Round, Throw } from "./types";
import CTPatterns from "./CTPatterns";
import OpeningsPage from "./OpeningsPage";
import Detail from "./Detail";
import Manage from "./Manage";
import Plans from "./Plans";
import Timeline from "./Timeline";
import PlayerAreas, { PracticeShelf } from "./PlayerAreas";
import HomePage from "./HomePage";
import { loadPractice } from "./learning";
import type { LearningSelection } from "./learning";

const nav = [
  { id: "home", label: "发现" },
  { id: "learn", label: "跟着选手学" },
  { id: "plans", label: "控图与反制" },
  { id: "openings", label: "开局策略" },
  { id: "ct", label: "CT 防守研究" },
  { id: "pistol", label: "手枪局" },
  { id: "utility", label: "道具库" },
  { id: "pro", label: "职业案例" },
  { id: "saved", label: "我的收藏" },
];
const titles: Record<string, string> = {
  home: "发现",
  learn: "跟着选手学",
  openings: "开局策略",
  plans: "控图与反制",
  ct: "CT 防守研究",
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
  const [learningSeed, setLearningSeed] = useState<LearningSelection>({});
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
  // Desktop studio: the summary opens the app, each map's throws load on demand.
  const latest = useRef(catalog);
  useEffect(() => {
    latest.current = catalog;
  }, [catalog]);
  const inflight = useRef(new Set<string>());
  const [mapLoading, setMapLoading] = useState<string[]>([]);
  const ensureMap = useCallback(
    (map?: string, force = false) => {
      if (!map || client.mode !== "desktop" || inflight.current.has(map))
        return;
      if (!force && (latest.current.loaded || []).includes(map)) return;
      inflight.current.add(map);
      setMapLoading([...inflight.current]);
      client
        .loadMap(map)
        .then((slice) => setCatalog((c) => mergeSlice(c, slice)))
        .catch((e) => setError(e.message))
        .finally(() => {
          inflight.current.delete(map);
          setMapLoading([...inflight.current]);
        });
    },
    [client],
  );
  const refresh = useCallback(() => {
    if (client.mode !== "desktop") {
      void client
        .catalog()
        .then(setCatalog)
        .catch((e) => setError(e.message));
      return;
    }
    const loaded = latest.current.loaded || [];
    void client
      .summary()
      .then((next) => {
        // Keep what is on screen until each loaded map has been fetched again.
        setCatalog(
          loaded.reduce(
            (c, map) => mergeSlice(c, sliceOf(latest.current, map)),
            next,
          ),
        );
        loaded.forEach((map) => ensureMap(map, true));
      })
      .catch((e) => setError(e.message));
  }, [client, ensureMap]);
  useEffect(() => {
    let active = true;
    client
      .init()
      .then((c) => {
        if (active) {
          setCatalog(c);
          setError("");
          // Start with the map that has the most throws so the library is not empty.
          const first = [...(c.maps || [])].sort(
            (a, b) => b.throws - a.throws,
          )[0];
          if (first) ensureMap(first.map);
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
  }, [client, ensureMap]);
  useEffect(() => ensureMap(filters.map), [filters.map, ensureMap]);
  useEffect(() => {
    // Saved throws, plan steps and an opened detail may sit on maps not loaded yet.
    const ids =
      page === "saved"
        ? [...favorites]
        : page === "plans"
          ? catalog.plans.flatMap((p) => p.steps.map((s) => s.throw_id))
          : [];
    if (detail) ids.push(detail.id);
    for (const id of ids) {
      const map =
        mapOfThrow(catalog, id) ||
        catalog.matches.find(
          (m) => m.id === catalog.rounds.find((r) => r.id === id)?.match_id,
        )?.map;
      ensureMap(map);
    }
  }, [page, favorites, detail, catalog, ensureMap]);
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
  function openLearning(seed: LearningSelection) {
    setLearningSeed(seed);
    setDetail(null);
    navigate("learn");
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
    [
      ...new Set(
        page === "pistol" || page === "pro"
          ? catalog.rounds.flatMap((r) => r.equipment.map((e) => e[key]))
          : catalog.throws
              .filter((t) => isMisthrow(t) === (filters.status === "misthrow"))
              .map((t) => t[key]),
      ),
    ]
      .filter(Boolean)
      .sort();
  const maps = [...new Set(catalog.matches.map((m) => m.map))].sort();
  const detailReady =
    !detail ||
    (detail.kind === "throw"
      ? catalog.throws.some((t) => t.id === detail.id)
      : catalog.rounds.some((r) => r.id === detail.id) &&
        (client.mode !== "desktop" ||
          (catalog.loaded || []).includes(
            catalog.matches.find(
              (m) =>
                m.id ===
                catalog.rounds.find((r) => r.id === detail.id)?.match_id,
            )?.map || "",
          )));
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
      [
        JSON.stringify(
          { version: 1, favorites, notes, practice: loadPractice() },
          null,
          2,
        ),
      ],
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
      if (Array.isArray(value.practice)) {
        const existing = loadPractice();
        const restored = value.practice.filter(
          (p: Record<string, unknown>) =>
            p &&
            typeof p.id === "string" &&
            typeof p.profile_id === "string" &&
            typeof p.round_id === "string" &&
            typeof p.title === "string" &&
            typeof p.map === "string" &&
            typeof p.note === "string" &&
            Array.isArray(p.steps) &&
            p.steps.every((s) => typeof s === "string") &&
            Array.isArray(p.checked) &&
            p.checked.every(Number.isInteger),
        );
        localStorage.setItem(
          "or-practice",
          JSON.stringify([
            ...existing,
            ...restored.filter(
              (p: { id: string }) => !existing.some((e) => e.id === p.id),
            ),
          ]),
        );
      }
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
          OpeningRoutes <small>CS2</small>
        </button>
        <nav aria-label="主要导航">
          {nav.map((n) => (
            <button
              key={n.id}
              aria-current={page === n.id ? "page" : undefined}
              className={page === n.id ? "nav-item active" : "nav-item"}
              onClick={() => navigate(n.id)}
            >
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
              <span>数据与内容管理</span>
            </button>
          </div>
        )}
        <div className="sidebar-foot">
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
        <main>
          <div className="page-title">
            <h1>{titles[page]}</h1>
          </div>
          {loading && (
            <p role="status" className="notice">
              正在读取学习资料…
            </p>
          )}
          {client.mode === "desktop" &&
            catalog.maps &&
            page !== "home" &&
            page !== "manage" &&
            page !== "learn" && (
              <MapLoader
                maps={catalog.maps}
                loaded={catalog.loaded || []}
                loading={mapLoading}
                load={(m) => ensureMap(m)}
              />
            )}
          {detail && !detailReady && (
            <p role="status" className="notice">
              正在载入这条记录所在地图的资料…
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
          {page === "home" ? (
            <HomePage
              catalog={catalog}
              navigate={navigate}
              openLearning={() => openLearning({})}
              openMap={(map) => {
                setFilters({ map });
                navigate("utility");
              }}
            />
          ) : page === "manage" ? (
            <Manage
              client={client}
              catalog={catalog}
              onRefresh={refresh}
              onOpenRound={(id) => setDetail({ id, kind: "round" })}
              onSelectMap={ensureMap}
              loadingMaps={mapLoading}
            />
          ) : page === "learn" ? (
            <PlayerAreas
              key={JSON.stringify(learningSeed)}
              client={client}
              catalog={catalog}
              seed={learningSeed}
              openRound={(id) => setDetail({ id, kind: "round" })}
              openThrow={(id) => setDetail({ id, kind: "throw" })}
              onRefresh={refresh}
            />
          ) : page === "openings" ? (
            <OpeningsPage
              client={client}
              catalog={catalog}
              openRound={(id) => setDetail({ id, kind: "round" })}
            />
          ) : page === "ct" ? (
            <CTPatterns
              client={client}
              catalog={catalog}
              onRefresh={refresh}
              onSelectMap={(m) => ensureMap(m)}
              loadingMaps={mapLoading}
              openRound={(id) => setDetail({ id, kind: "round" })}
              onLearn={openLearning}
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
                        options={[
                          ["complete", "资料齐全"],
                          ["pending", "教学待完善"],
                          // Only the studio keeps misthrows; exports leave them out.
                          ...(client.mode === "desktop"
                            ? [["misthrow", "已标为失误"]]
                            : []),
                        ]}
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
              {page === "pistol" && (
                <>
                  <button
                    className="button secondary"
                    onClick={() =>
                      openLearning({
                        map: filters.map,
                        side:
                          filters.side === "CT" || filters.side === "T"
                            ? filters.side
                            : undefined,
                        pistol: true,
                        subject: catalog.rounds
                          .flatMap((r) => r.equipment)
                          .find((e) => e.player === filters.player)?.player_id,
                      })
                    }
                  >
                    按选手研究手枪局
                  </button>
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
                <div className="actions saved-tools">
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
              <div className="section-line results">
                <p>
                  {isRounds ? "回合" : "道具"}{" "}
                  <strong>{isRounds ? rounds.length : throws.length}</strong> 条
                  {page === "saved" && ` · 已收藏回合 ${rounds.length} 个`}
                </p>
                {!isRounds && page !== "saved" && (
                  <span className="micro">勾选两条记录可对比</span>
                )}
              </div>
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
                          <Timeline
                            client={client}
                            round={r}
                            throwRow={t}
                            throws={catalog.throws}
                          />
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
                  {throws.slice(0, limit).map((t) => (
                    <article className="throw-item" key={t.id}>
                      <ThrowCard
                        row={t}
                        onOpen={() => setDetail({ id: t.id, kind: "throw" })}
                      />
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
                page !== "saved" &&
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
              {page === "saved" && (
                <>
                  {!loading && throws.length === 0 && rounds.length === 0 && (
                    <p className="hint">当前筛选下没有收藏的道具或回合。</p>
                  )}
                  <PracticeShelf
                    key={storageMessage}
                    openRound={(id) => setDetail({ id, kind: "round" })}
                    openLearning={openLearning}
                  />
                </>
              )}
              {(isRounds ? rounds.length : throws.length) > limit && (
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
          <footer>原始事实与教学解释分别核验</footer>
        </main>
      </div>
      {detail && detailReady && (
        <Detail
          onLearn={openLearning}
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

function MapLoader({
  maps,
  loaded,
  loading,
  load,
}: {
  maps: { map: string; throws: number; matches: number }[];
  loaded: string[];
  loading: string[];
  load: (map: string) => void;
}) {
  const done = maps.filter((m) => loaded.includes(m.map)).length;
  return (
    <section className="map-loader" aria-label="按地图载入资料">
      <span className="micro">
        资料按地图载入 · 已载入 {done}/{maps.length} 张地图
      </span>
      <div className="chips">
        {maps.map((m) => {
          const isLoaded = loaded.includes(m.map);
          const busy = loading.includes(m.map);
          return (
            <button
              key={m.map}
              className={isLoaded ? "chip active" : "chip"}
              disabled={isLoaded || busy}
              onClick={() => load(m.map)}
              aria-label={`${m.map.replace("de_", "")}：${
                isLoaded ? "已载入" : busy ? "载入中" : "点击载入"
              }`}
            >
              {m.map.replace("de_", "")}{" "}
              <b>
                {busy
                  ? "载入中…"
                  : isLoaded
                    ? m.throws.toLocaleString()
                    : `载入 ${m.throws.toLocaleString()}`}
              </b>
            </button>
          );
        })}
      </div>
    </section>
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
  const points = trajectoryPoints(t);
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
      <svg
        className={`throw-thumb ${t.kind}`}
        viewBox="0 0 310 120"
        aria-hidden="true"
      >
        {points.length > 0 ? (
          <polyline
            points={plot}
            stroke="currentColor"
            fill="none"
            strokeWidth="4"
          />
        ) : (
          <circle cx="155" cy="60" r="22" fill="none" stroke="currentColor" />
        )}
      </svg>
      <span className={`side ${t.side}`}>{t.side}</span>
      <span className="throw-main">
        <h3>
          {t.teaching.title || `${t.player} · ${kindNames[t.kind] || t.kind}`}
        </h3>
        <span className="micro">
          {kindNames[t.kind] || t.kind} ·{" "}
          {t.teaching.area ||
            (t.origin_area
              ? `${t.origin_area} → ${t.effect_area || "落点区域未知"}`
              : "区域待整理")}{" "}
          · {t.team || t.side}
          {!points.length && " · 轨迹待核验"}
        </span>
      </span>
      <span className="row-meta">
        {t.map.replace("de_", "")} · R{t.round_number} · {t.time.toFixed(1)}s
      </span>
      <span className={t.gaps.length ? "status pending" : "status"}>
        {t.gaps.length ? "教学待完善" : "资料齐全"}
      </span>
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
      <span className="round-number">R{String(r.number).padStart(2, "0")}</span>
      <span className={`side ${r.winner}`}>{r.winner || "未知"} 获胜</span>
      <span className="throw-main">
        <h3>{m.source.match}</h3>
        <span className="micro">
          {m.source.event} · {m.source.date} · {m.map.replace("de_", "")} ·{" "}
          {r.is_pistol ? "手枪局" : "正式回合"}
        </span>
      </span>
      <span className="row-meta">
        首杀{" "}
        {r.opening_kill
          ? `${r.opening_kill.attacker} → ${r.opening_kill.victim}`
          : "未记录"}{" "}
        · {r.equipment.length} 名选手
      </span>
    </button>
  );
}
