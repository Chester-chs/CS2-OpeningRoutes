import { useEffect, useMemo, useState } from "react";
import { DataClient, kindNames, mediaUrl } from "./data";
import {
  EMPTY_LEARNING,
  controlNames,
  draftLearningPlan,
  economyNames,
  loadPractice,
  practiceFromSample,
  sampleMatchesContext,
  savePractice,
  scoreNames,
} from "./learning";
import type {
  Habit,
  LearningIndex,
  LearningProfile,
  LearningSample,
  LearningSelection,
  LearningStats,
  ObservedUtility,
  Practice,
} from "./learning";
import type { Catalog, Side } from "./types";

const percent = (n: number) => `${Math.round(n * 100)}%`;
const contextName = (key: string) =>
  key === "pistol"
    ? "仅手枪局"
    : key === "non_pistol"
      ? "非手枪局"
      : key.startsWith("economy:")
        ? economyNames[key.slice(8)] || key
        : key.startsWith("score:")
          ? scoreNames[key.slice(6)] || key
          : "全部情境";

function Choice({
  label,
  value,
  options,
  change,
}: {
  label: string;
  value: string;
  options: [string, string][];
  change: (value: string) => void;
}) {
  return (
    <label className="learning-choice">
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(e) => change(e.target.value)}
      >
        {options.map(([id, text]) => (
          <option key={id} value={id}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function PlayerAreas({
  client,
  catalog,
  seed,
  openRound,
  openThrow,
  onRefresh,
}: {
  client: DataClient;
  catalog: Catalog;
  seed: LearningSelection;
  openRound: (id: string) => void;
  openThrow: (id: string) => void;
  onRefresh: () => void;
}) {
  const [index, setIndex] = useState<LearningIndex>(EMPTY_LEARNING);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [choice, setChoice] = useState<LearningSelection>(seed);
  const [detail, setDetail] = useState<LearningProfile | null>(null);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await client.learningIndex();
        if (!active) return;
        setIndex(next);
        setLoaded(true);
        setError("");
        if (next.state === "building")
          timer = setTimeout(() => void poll(), 1500);
      } catch (e) {
        if (active) {
          setError((e as Error).message);
          setLoaded(true);
        }
      }
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [client, revision]);
  const choices = useMemo(() => {
    const requested = index.profiles.find((p) => p.id === choice.profile);
    const kind = requested?.kind || choice.kind || "player";
    const all = index.profiles
      .filter((p) => p.kind === kind)
      .sort(
        (a, b) => b.counts.rounds - a.counts.rounds || a.id.localeCompare(b.id),
      );
    const preferred = all.find(
      (p) =>
        p.map === (choice.map || "de_mirage") &&
        p.side === (choice.side || "CT") &&
        p.area === (choice.area || "A") &&
        p.counts.pistols > 0,
    );
    const subject =
      requested?.subject_id ||
      (all.some((p) => p.subject_id === choice.subject)
        ? choice.subject
        : preferred?.subject_id || all[0]?.subject_id) ||
      "";
    const subjects = [
      ...new Map(all.map((p) => [p.subject_id, p.name])).entries(),
    ].sort((a, b) => a[1].localeCompare(b[1]));
    const own = all.filter((p) => p.subject_id === subject);
    const maps = [...new Set(own.map((p) => p.map))].sort();
    const map =
      requested?.map ||
      (maps.includes(choice.map || "")
        ? choice.map!
        : maps.includes("de_mirage")
          ? "de_mirage"
          : maps[0]) ||
      "";
    const onMap = own.filter((p) => p.map === map);
    const sides = [...new Set(onMap.map((p) => p.side))].sort();
    const side =
      requested?.side ||
      (sides.includes(choice.side!) ? choice.side! : sides[0]) ||
      "CT";
    const onSide = onMap.filter((p) => p.side === side);
    const areas = [
      ...new Map(onSide.map((p) => [p.area, p.area_label])).entries(),
    ].sort();
    const area =
      requested?.area ||
      (areas.some(([id]) => id === choice.area)
        ? choice.area!
        : areas.some(([id]) => id === "A")
          ? "A"
          : areas[0]?.[0]) ||
      "";
    const periods = onSide.filter((p) => p.area === area);
    return {
      kind,
      subject,
      subjects,
      maps,
      map,
      sides,
      side,
      areas,
      area,
      periods,
      selected: requested || periods[0],
    };
  }, [index, choice]);
  const id = choices.selected?.id;
  useEffect(() => {
    if (!id) return;
    let active = true;
    client
      .learningProfile(id)
      .then((p) => {
        if (active) {
          setDetail(p);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [client, id, revision]);
  const select = (changes: LearningSelection) =>
    setChoice({ ...choice, profile: undefined, ...changes });
  async function retry() {
    try {
      if (client.mode === "desktop")
        await client.write("learning/retry", "POST", {});
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="player-learning">
      <p className="muted">
        选一个人或一支队伍，看看他们怎样进入、争夺和守住同一块区域。先看真实回合，再比较情境，最后跟练。
      </p>
      {(!loaded || index.state === "building") && (
        <p role="status" className="notice">
          正在整理选手区域档案…
          首次计算需要等待，完成后会缓存；其他页面仍可使用。
        </p>
      )}
      {(error || index.state === "error") && (
        <p role="alert" className="notice">
          {error || "档案计算失败，可重试并在本地日志检查原因。"}{" "}
          <button className="text-button" onClick={() => void retry()}>
            重试档案
          </button>
        </p>
      )}
      {loaded && index.state === "unavailable" && (
        <p className="notice">
          此内容包尚未包含选手区域档案。请使用新版桌面端重新导出；已有教学仍可浏览。
        </p>
      )}
      {index.state === "ready" && (
        <>
          <p className="micro">
            覆盖 {index.coverage.analyzed_rounds || 0} /{" "}
            {index.coverage.eligible_rounds || 0} 个来源已核验有效回合；
            {index.coverage.missing_rounds || 0} 个缺少区域路线，需重新导入原
            Demo。档案按游戏版本分开，避免混用地图更新前后的样本。
          </p>
          <div className="learning-filters">
            <Choice
              label="学习对象"
              value={choices.kind}
              options={[
                ["player", "选手"],
                ["team", "战队"],
                ["role", "已确认角色组"],
              ]}
              change={(kind) => select({ kind, subject: undefined })}
            />
            <Choice
              label="选手或战队"
              value={choices.subject}
              options={choices.subjects.map(([id, name]) => [
                id,
                choices.kind === "player" ? `${name} · ${id.slice(-4)}` : name,
              ])}
              change={(subject) => select({ subject })}
            />
            <Choice
              label="学习地图"
              value={choices.map}
              options={choices.maps.map((m) => [m, m.replace("de_", "")])}
              change={(map) => select({ map })}
            />
            <Choice
              label="学习阵营"
              value={choices.side}
              options={choices.sides.map((s) => [s, s])}
              change={(side) => select({ side: side as Side })}
            />
            <Choice
              label="学习区域"
              value={choices.area}
              options={choices.areas}
              change={(area) => select({ area })}
            />
            <Choice
              label="战队时期与版本"
              value={id || ""}
              options={choices.periods.map((p) => [
                p.id,
                `${p.team} · ${p.date_from}—${p.date_to} · ${p.version} · ${p.counts.rounds} 局`,
              ])}
              change={(profile) => select({ profile })}
            />
          </div>
          {!id && (
            <p className="notice">
              没有符合条件的档案。角色组需人工确认；可以先查看个人或战队，或导入更多比赛。
            </p>
          )}
          {id && detail?.id !== id && <p role="status">正在读取所选档案…</p>}
          {detail?.id === id && (
            <Profile
              key={id}
              profile={detail}
              client={client}
              catalog={catalog}
              pistol={seed.pistol}
              openRound={openRound}
              openThrow={openThrow}
              onRefresh={onRefresh}
            />
          )}
          {client.mode === "desktop" && (
            <GroupEditor
              key={`${choices.map}:${revision}`}
              client={client}
              index={index}
              profile={detail?.id === id ? detail : null}
              map={choices.map}
              onSaved={() => setRevision((v) => v + 1)}
            />
          )}
        </>
      )}
    </section>
  );
}

function Distribution({
  title,
  items,
  label,
}: {
  title: string;
  items: Habit[];
  label: (s: string) => string;
}) {
  return (
    <section className="panel learning-distribution">
      <h3>{title}</h3>
      {items.length ? (
        items.map((item) => (
          <div key={item.label} className="learning-habit">
            <span>{label(item.label)}</span>
            <strong>
              {item.rounds} 局 · {percent(item.share)}
            </strong>
            <meter
              aria-label={label(item.label)}
              min={0}
              max={1}
              value={item.share}
            />
            {item.interval && (
              <small>
                95% 区间 {percent(item.interval[0])}—{percent(item.interval[1])}
              </small>
            )}
          </div>
        ))
      ) : (
        <p className="micro">此情境暂无记录。</p>
      )}
    </section>
  );
}

function Confidence({ stats }: { stats: LearningStats }) {
  return (
    <p className="notice">
      样本：{stats.counts.rounds} 回合 / {stats.counts.matches} 场比赛地图 /{" "}
      {stats.counts.players} 人，含 {stats.counts.pistols} 个手枪局。 置信提示：
      {stats.confidence.status === "exploratory"
        ? "探索性样本，尚不足 30 回合或 5 场比赛，不代表稳定习惯。"
        : "描述性统计，仍需结合对手和比赛时期解读。"}
      {stats.counts.matches >= 5
        ? "比例区间按比赛整块重采样 400 次计算。"
        : "不足 5 场，不提供置信区间。"}
      区域帧缺失 {percent(stats.missing_fraction)}；本侧获胜 {stats.wins}{" "}
      局，不能据此认定某条路线造成胜利。
    </p>
  );
}

function Profile({
  profile,
  client,
  catalog,
  pistol,
  openRound,
  openThrow,
  onRefresh,
}: {
  profile: LearningProfile;
  client: DataClient;
  catalog: Catalog;
  pistol?: boolean;
  openRound: (id: string) => void;
  openThrow: (id: string) => void;
  onRefresh: () => void;
}) {
  const [context, setContext] = useState(pistol ? "pistol" : "all");
  const [chosen, setChosen] = useState("");
  const [limit, setLimit] = useState(20);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const samples = profile.samples.filter((s) =>
    sampleMatchesContext(s, context),
  );
  const sample = samples.find((s) => s.id === chosen) || samples[0];
  const round = catalog.rounds.find((r) => r.id === sample?.round_id);
  const match = catalog.matches.find((m) => m.id === round?.match_id);
  const playerName = (id: string) =>
    round?.equipment.find((e) => e.player_id === id)?.player || id;
  const eventTime = (tick: number) =>
    round && match
      ? `${((tick - round.freeze_end_tick) / match.tick_rate).toFixed(2)}s · `
      : "";
  const stats = context === "all" ? profile : profile.contexts[context];
  const place = (name: string) =>
    name
      .split(" → ")
      .map((p) => profile.place_labels[p] || p)
      .join(" → ");
  async function draft() {
    if (!sample) return;
    setBusy(true);
    setMessage("");
    try {
      const rows = await client.observedThrows(sample.utility.map((t) => t.id));
      const plan = draftLearningPlan(profile, sample, rows);
      if (!plan) {
        savePractice(practiceFromSample(profile, sample));
        setMessage("此样本无可用开局道具，已保存路线跟练清单。");
        return;
      }
      await client.write(`plans/${plan.id}`, "PUT", plan);
      savePractice(practiceFromSample(profile, sample));
      onRefresh();
      setMessage(
        "方案草稿已保存到控图与反制，跟练清单已保存到我的收藏。发布前仍需完整教学与复现核验。",
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div data-testid="learning-profile" className="learning-profile">
      <div className="section-line">
        <div>
          <p className="eyebrow">
            {profile.team} / {profile.map.replace("de_", "")}
          </p>
          <h2>
            {profile.name} · {profile.side} · {profile.area_label}
          </h2>
        </div>
        <Choice
          label="学习情境"
          value={context}
          options={[
            ["all", "全部情境"],
            ["pistol", "仅手枪局"],
            ...Object.keys(profile.contexts)
              .filter((k) => k !== "pistol")
              .map((k) => [k, contextName(k)] as [string, string]),
          ]}
          change={(v) => {
            setContext(v);
            setChosen("");
            setLimit(20);
          }}
        />
      </div>
      <p className="micro">
        {profile.date_from}—{profile.date_to} · 版本 {profile.version} ·{" "}
        {profile.kind === "player"
          ? `SteamID ${profile.subject_id}`
          : `${profile.members.length} 名选手分别保留个人档案`}{" "}
        · 曾用名：{profile.aliases.join(" / ") || profile.name}
      </p>
      <details>
        <summary>区域边界与统计方法</summary>
        <p>
          区域包含：{profile.area_places.map(place).join("、")}。按 4 Hz
          记录存活人数，连续 2
          秒只有一侧在场才标为持续占位。双方在场为争夺，缺帧为未知。占位不等于视野、火力覆盖或实际控制权；首次伤害只是接触代理。窗口从冻结结束起算。
        </p>
        <p>
          以下频率只描述参与本区域的回合，不是所有上场回合的选择概率。站位取前
          30 秒停留最久的区域；同回合多人可能各有站位，因此占比之和可超过
          100%。新 Demo、区域定义或来源复核改变后会重新计算。
        </p>
      </details>
      {stats ? (
        <>
          <Confidence stats={stats} />
          <div className="learning-columns">
            <Distribution title="常驻区域" items={stats.habits} label={place} />
            <Distribution
              title="前 30 秒移动"
              items={stats.routes}
              label={place}
            />
            <Distribution
              title="道具顺序"
              items={stats.sequences}
              label={(s) =>
                s
                  .split(" → ")
                  .map((k) => kindNames[k] || k)
                  .join(" → ")
              }
            />
          </div>
          <p className="micro">
            出手时机（中位数 / 中间 50% 范围）：
            {stats.utility_timing
              .map(
                (t) =>
                  `${kindNames[t.kind] || t.kind} ${t.median}s / ${t.p25}—${t.p75}s（${t.count} 次）`,
              )
              .join("；") || "无开局道具记录"}
          </p>
        </>
      ) : (
        <p className="notice">这个时期和区域暂无该情境样本，不能推断其习惯。</p>
      )}
      <h3>对应的完整回合 · {samples.length} 个</h3>
      <div className="learning-samples">
        <div className="learning-sample-list" aria-label="来源回合列表">
          {samples.slice(0, limit).map((s) => (
            <button
              key={s.id}
              data-testid="learning-sample"
              aria-pressed={sample?.id === s.id}
              className={
                sample?.id === s.id ? "sample-button active" : "sample-button"
              }
              onClick={() => {
                setChosen(s.id);
                setMessage("");
              }}
            >
              <strong>
                R{s.number} ·{" "}
                {s.pistol ? "手枪局" : economyNames[s.economy] || s.economy} ·{" "}
                {s.winner === profile.side ? "胜" : "负"}
              </strong>
              <span>{s.source.match}</span>
              <small>
                {s.date} · {scoreNames[s.score] || s.score}
              </small>
            </button>
          ))}
          {samples.length > limit && (
            <button
              className="text-button"
              onClick={() => setLimit((n) => n + 20)}
            >
              更多回合
            </button>
          )}
        </div>
        {sample && (
          <section className="panel sample-detail" aria-label="选中回合观察">
            <h3>
              R{sample.number} · {sample.source.match}
            </h3>
            <p className="micro">
              {sample.source.event} · {sample.date} ·{" "}
              {sample.pistol ? "正式手枪局" : economyNames[sample.economy]} ·{" "}
              {scoreNames[sample.score]}
            </p>
            {mediaUrl(sample.source.url, "web") && (
              <a
                href={mediaUrl(sample.source.url, "web")}
                target="_blank"
                rel="noreferrer"
              >
                核对比赛来源 ↗
              </a>
            )}
            <div className="actions">
              <button
                className="button secondary"
                onClick={() => openRound(sample.round_id)}
              >
                查看全员完整回合
              </button>
              <button
                className="button secondary"
                onClick={() => {
                  try {
                    savePractice(practiceFromSample(profile, sample));
                    setMessage("跟练清单已保存到我的收藏。");
                  } catch {
                    setMessage("保存失败，请检查浏览器存储空间。");
                  }
                }}
              >
                保存跟练清单
              </button>
              {client.mode === "desktop" && (
                <button
                  className="button"
                  disabled={busy}
                  onClick={() => void draft()}
                >
                  {busy ? "正在生成…" : "生成方案草稿"}
                </button>
              )}
            </div>
            {message && (
              <p role="status" className="notice">
                {message}
              </p>
            )}
            <h4>位置与移动</h4>
            {Object.entries(sample.routes).map(([pid, segments]) => (
              <p key={pid}>
                <b>
                  {catalog.rounds
                    .find((r) => r.id === sample.round_id)
                    ?.equipment.find((e) => e.player_id === pid)?.player || pid}
                </b>
                ：
                {segments
                  .map((s) => `${s.start}–${s.end}s ${place(s.place)}`)
                  .join(" → ") || "暂无有效路线"}
              </p>
            ))}
            <Occupancy sample={sample} />
            <p>
              区域首次伤害：
              {sample.first_contact
                ? `${eventTime(sample.first_contact.tick)}${place(sample.first_contact.victim_place || sample.first_contact.attacker_place || "未知")} · ${playerName(sample.first_contact.attacker_id)} → ${playerName(sample.first_contact.victim_id)}`
                : "无记录"}
              ；区域首杀：
              {sample.first_kill
                ? `${eventTime(sample.first_kill.tick)}${place(sample.first_kill.victim_place || sample.first_kill.attacker_place || "未知")}`
                : "无记录"}
              。
            </p>
            <UtilityList
              title="本方动作与时机"
              rows={sample.utility}
              place={place}
              catalog={catalog}
              openThrow={openThrow}
            />
            <UtilityList
              title="对手同期动作"
              rows={sample.opponent_utility}
              place={place}
              catalog={catalog}
              openThrow={openThrow}
            />
            <p className="micro">
              对手动作仅是同时发生的事实；是否构成反制、选手为何应对，需要观看完整回合核对。道具观察包含可能失误的投掷，生成方案时排除已标记失误。
            </p>
          </section>
        )}
      </div>
    </div>
  );
}

function UtilityList({
  title,
  rows,
  place,
  catalog,
  openThrow,
}: {
  title: string;
  rows: ObservedUtility[];
  place: (s: string) => string;
  catalog: Catalog;
  openThrow: (id: string) => void;
}) {
  return (
    <section>
      <h4>{title}</h4>
      {rows.length ? (
        <ol className="learning-utility">
          {rows.map((t) => (
            <li key={t.id}>
              {t.time}s · {t.player} · {kindNames[t.kind] || t.kind} ·{" "}
              {place(t.origin_place || "未知")} →{" "}
              {place(t.effect_place || "未知")}
              {t.effect_place_basis && (
                <small>
                  （推测落点区域，距离{" "}
                  {Math.round(t.effect_place_basis.distance)} 单位）
                </small>
              )}
              {catalog.throws.some((r) => r.id === t.id) && (
                <button className="text-button" onClick={() => openThrow(t.id)}>
                  查看已有教学
                </button>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="micro">前 30 秒无符合条件的道具；仍可跟练路线。</p>
      )}
    </section>
  );
}

function Occupancy({ sample }: { sample: LearningSample }) {
  const points = sample.control.points;
  const paths = [1, 2].map((i) =>
    points.map((p) => `${20 + p[0] * 16},${120 - Number(p[i]) * 18}`).join(" "),
  );
  return (
    <figure className="occupancy">
      <figcaption>前 30 秒区域人数 · CT（绿）/ T（黄）</figcaption>
      <svg
        viewBox="0 0 520 150"
        role="img"
        aria-label="区域内存活人数随时间变化"
      >
        {[0, 1, 2, 3, 4, 5].map((n) => (
          <g key={n}>
            <line
              x1="20"
              y1={120 - n * 18}
              x2="500"
              y2={120 - n * 18}
              stroke="currentColor"
              opacity=".12"
            />
            <text x="2" y={124 - n * 18}>
              {n}
            </text>
          </g>
        ))}
        {points
          .filter((p) => p[3] === "unknown")
          .map((p) => (
            <rect
              key={p[0]}
              x={20 + p[0] * 16}
              y="25"
              width="4"
              height="95"
              fill="currentColor"
              opacity=".1"
            />
          ))}
        <polyline
          points={paths[0]}
          fill="none"
          stroke="#8fc9b3"
          strokeWidth="2"
        />
        <polyline
          points={paths[1]}
          fill="none"
          stroke="#e1b85d"
          strokeWidth="2"
        />
        {[0, 10, 20, 30].map((n) => (
          <text key={n} x={20 + n * 16} y="142">
            {n}s
          </text>
        ))}
      </svg>
      <p className="micro">
        回合末区域状态：
        {controlNames[sample.control.end_state] || sample.control.end_state}；
        {sample.winner || "结果未知"}{" "}
        获胜。灰色为资料缺失，持续占位不等于实际控制。
      </p>
    </figure>
  );
}

function GroupEditor({
  client,
  index,
  profile,
  map,
  onSaved,
}: {
  client: DataClient;
  index: LearningIndex;
  profile: LearningProfile | null;
  map: string;
  onSaved: () => void;
}) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(form: HTMLFormElement, kind: "region" | "role") {
    const data = new FormData(form);
    setBusy(true);
    try {
      const body =
        kind === "region"
          ? {
              kind,
              map,
              label: data.get("label"),
              places: String(data.get("places"))
                .split(/[,，\s]+/)
                .filter(Boolean),
            }
          : {
              kind,
              map,
              label: data.get("label"),
              players: String(data.get("players"))
                .split(/[,，\s]+/)
                .filter(Boolean),
              side: profile!.side,
              area: profile!.area,
              team: profile!.team,
              confirmed: data.get("confirmed") === "on",
              date_from: data.get("from") || null,
              date_to: data.get("to") || null,
            };
      await client.write(`learning/groups/${crypto.randomUUID()}`, "PUT", body);
      onSaved();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="panel learning-settings">
      <summary>整理区域与角色组（本地）</summary>
      <p className="micro">
        个人档案始终保留。角色合并必须人工确认同地图、同战队、同阵营和同区域，日期可限制转会时期。保存后会重新计算。
      </p>
      {map && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit(e.currentTarget, "region");
          }}
        >
          <h3>自定义 {map.replace("de_", "")} 区域</h3>
          <label>
            区域名称
            <input name="label" required maxLength={60} />
          </label>
          <label>
            Demo 区域名（空格或逗号分隔）
            <input
              name="places"
              required
              placeholder="BombsiteA PalaceInterior"
            />
          </label>
          <p className="micro">
            可参考：
            {[
              ...new Set(
                Object.values(index.regions[map] || {}).flatMap(
                  (r) => r.places,
                ),
              ),
            ].join("、")}
          </p>
          <button className="button secondary" disabled={busy}>
            保存区域
          </button>
        </form>
      )}
      {profile && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit(e.currentTarget, "role");
          }}
        >
          <h3>
            {profile.team} · {profile.side} · {profile.area_label} 角色组
          </h3>
          <label>
            角色名称
            <input name="label" required maxLength={60} />
          </label>
          <label>
            选手 SteamID（空格或逗号分隔）
            <input
              name="players"
              defaultValue={profile.members.join(", ")}
              required
            />
          </label>
          <div className="actions">
            <label>
              起始日期
              <input name="from" type="date" />
            </label>
            <label>
              结束日期
              <input name="to" type="date" />
            </label>
          </div>
          <label>
            <input type="checkbox" name="confirmed" required />{" "}
            已核对这些选手在该时期承担相同角色
          </label>
          <button className="button secondary" disabled={busy}>
            保存角色组
          </button>
        </form>
      )}
      {Object.entries(index.groups).map(([id, g]) => (
        <p key={id}>
          {g.label} · {g.map} · {g.kind === "region" ? "区域" : "角色组"}{" "}
          <button
            className="text-button"
            onClick={() => {
              void client
                .write(`learning/groups/${id}`, "DELETE", {})
                .then(onSaved)
                .catch((e) => setMessage(e.message));
            }}
          >
            移除定义
          </button>
        </p>
      ))}
      {message && <p role="alert">{message}</p>}
    </details>
  );
}

export function PracticeShelf({
  openRound,
  openLearning,
}: {
  openRound: (id: string) => void;
  openLearning: (seed: LearningSelection) => void;
}) {
  const [rows, setRows] = useState(loadPractice);
  const [error, setError] = useState("");
  function update(next: Practice[]) {
    try {
      localStorage.setItem("or-practice", JSON.stringify(next));
      setRows(next);
    } catch {
      setError("保存失败，请检查浏览器存储空间。");
    }
  }
  return (
    <section className="practice-shelf">
      <h2>我的跟练清单</h2>
      {!rows.length && (
        <p className="muted">
          在选手区域档案中选择真实回合，保存自己的跟练清单。
        </p>
      )}
      {rows.map((row) => (
        <article className="panel" key={row.id} data-testid="practice-card">
          <h3>{row.title}</h3>
          {row.steps.map((step, i) => (
            <label className="practice-step" key={i}>
              <input
                type="checkbox"
                checked={row.checked.includes(i)}
                onChange={() =>
                  update(
                    rows.map((r) =>
                      r.id === row.id
                        ? {
                            ...r,
                            checked: r.checked.includes(i)
                              ? r.checked.filter((n) => n !== i)
                              : [...r.checked, i],
                          }
                        : r,
                    ),
                  )
                }
              />
              {step}
            </label>
          ))}
          <label>
            跟练笔记
            <textarea
              aria-label="跟练笔记"
              value={row.note}
              onChange={(e) =>
                update(
                  rows.map((r) =>
                    r.id === row.id ? { ...r, note: e.target.value } : r,
                  ),
                )
              }
            />
          </label>
          <div className="actions">
            <button
              className="text-button"
              onClick={() => openRound(row.round_id)}
            >
              打开来源回合
            </button>
            <button
              className="text-button"
              onClick={() =>
                openLearning({ profile: row.profile_id, map: row.map })
              }
            >
              返回选手档案
            </button>
            <button
              className="text-button"
              onClick={() => update(rows.filter((r) => r.id !== row.id))}
            >
              移除清单
            </button>
          </div>
        </article>
      ))}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
