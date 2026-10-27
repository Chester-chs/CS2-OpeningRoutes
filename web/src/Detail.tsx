import { useEffect, useRef, useState } from "react";
import { Bookmark, Check, ExternalLink, Save, X } from "lucide-react";
import { DataClient, kindNames, mediaUrl, teachingLabels } from "./data";
import type { Catalog, Round, Teaching, Throw } from "./types";
import Timeline from "./Timeline";

export function Video({
  value,
  client,
  offset = 0,
}: {
  value: unknown;
  client: DataClient;
  offset?: number;
}) {
  const url = mediaUrl(value, client.mode);
  if (!url) return <p className="notice">尚未关联可播放的职业比赛片段。</p>;
  let videoId = "";
  try {
    const u = new URL(url, window.location.href);
    if (u.hostname === "youtu.be") videoId = u.pathname.slice(1);
    if (["www.youtube.com", "youtube.com"].includes(u.hostname))
      videoId = u.searchParams.get("v") || "";
  } catch {
    /* Relative media. */
  }
  if (videoId && /^[\w-]{11}$/.test(videoId))
    return (
      <>
        <iframe
          className="video"
          title="职业比赛原片"
          src={`https://www.youtube-nocookie.com/embed/${videoId}?start=${Math.floor(offset)}`}
          allow="fullscreen; picture-in-picture"
          allowFullScreen
        />
        <a href={url} target="_blank" rel="noreferrer">
          打开原片 <ExternalLink size={13} />
        </a>
      </>
    );
  if (/\.(mp4|webm)(\?|$)/i.test(url))
    return (
      <video
        className="video"
        controls
        preload="metadata"
        src={url}
        onLoadedMetadata={(e) => {
          if (offset) e.currentTarget.currentTime = offset;
        }}
      />
    );
  return (
    <a className="button secondary" href={url} target="_blank" rel="noreferrer">
      打开职业示范来源 <ExternalLink size={15} />
    </a>
  );
}

function TeachingEditor({
  row,
  client,
  onSaved,
}: {
  row: Throw;
  client: DataClient;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<Teaching>({ ...row.teaching });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: string, value: string | number | boolean) =>
    setForm((v) => ({ ...v, [key]: value }));
  async function save(status: string) {
    setBusy(true);
    setMessage("");
    try {
      await client.saveTeaching(row.id, { ...form, status });
      setMessage(status === "published" ? "完整教学已发布。" : "草稿已保存。");
      onSaved();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(key: string, file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      const data = new FormData();
      data.append("asset", file);
      const result = await client.write("media", "POST", data);
      set(key, result.url);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="editor">
      <label className="check-label">
        <input
          type="checkbox"
          checked={Boolean(form.verification_confirmed)}
          onChange={(e) => set("verification_confirmed", e.target.checked)}
        />
        已重新验证本次修改的操作、图示与地图版本
      </label>
      <div className="notice">
        先核对原比赛，再补齐复现步骤。原始视角是出手时的数值参考，按键、站位图与瞄点需要游戏内验证。
      </div>
      <div className="form-grid">
        {Object.entries(teachingLabels)
          .filter(([key]) => key !== "reproduction")
          .map(([key, label]) => (
            <label
              key={key}
              className={
                ["purpose", "operation", "counterplay"].includes(key)
                  ? "wide"
                  : ""
              }
            >
              {label}
              {[
                "stance_image",
                "aim_image",
                "pro_video",
                "recreation_video",
              ].includes(key) ? (
                <>
                  <input
                    aria-label={label}
                    value={String(form[key] || "")}
                    onChange={(e) => set(key, e.target.value)}
                    placeholder="HTTPS 地址，或从本机添加"
                  />
                  <input
                    aria-label={`添加${label}`}
                    type="file"
                    accept={
                      key.includes("image")
                        ? "image/png,image/jpeg,image/webp"
                        : "video/mp4,video/webm"
                    }
                    onChange={(e) => void upload(key, e.target.files?.[0])}
                  />
                </>
              ) : (
                <textarea
                  aria-label={label}
                  rows={key === "title" || key === "area" ? 1 : 3}
                  value={String(form[key] || "")}
                  onChange={(e) => set(key, e.target.value)}
                />
              )}
            </label>
          ))}
      </div>
      <div className="form-grid">
        <label>
          游戏内复现
          <select
            aria-label="游戏内复现"
            value={String(form.reproduction || "pending")}
            onChange={(e) => set("reproduction", e.target.value)}
          >
            <option value="pending">尚未验证</option>
            <option value="failed">复现失败，需要修正</option>
            <option value="verified">已在所填版本中验证</option>
          </select>
        </label>
        <label>
          视频对应起点（秒）
          <input
            aria-label="视频对应起点"
            type="number"
            min="0"
            value={Number(form.video_offset || 0)}
            onChange={(e) => set("video_offset", Number(e.target.value))}
          />
        </label>
      </div>
      <div className="actions">
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => void save("draft")}
        >
          <Save size={15} />
          保存草稿
        </button>
        <button
          className="button"
          disabled={busy}
          onClick={() => void save("published")}
        >
          <Check size={15} />
          发布完整教学
        </button>
        {row.teaching.status === "published" && (
          <button
            className="button secondary"
            onClick={() => void save("withdrawn")}
          >
            撤回教学
          </button>
        )}
      </div>
      {message && (
        <p role="alert" className="notice">
          {message}
        </p>
      )}
    </section>
  );
}

export default function Detail({
  id,
  kind,
  catalog,
  client,
  onClose,
  onSaved,
  favorites,
  toggleFavorite,
}: {
  id: string;
  kind: "throw" | "round";
  catalog: Catalog;
  client: DataClient;
  onClose: () => void;
  onSaved: () => void;
  favorites: string[];
  toggleFavorite: (id: string) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState("learn");
  const [note, setNote] = useState(() => {
    try {
      return localStorage.getItem(`or-note-${id}`) || "";
    } catch {
      return "";
    }
  });
  const [noteStatus, setNoteStatus] = useState("");
  const [reviewMessage, setReviewMessage] = useState("");
  const row =
    kind === "throw" ? catalog.throws.find((t) => t.id === id) : undefined;
  const round = catalog.rounds.find((r) => r.id === (row ? row.round_id : id));
  const match = catalog.matches.find((m) => m.id === round?.match_id);
  const [review, setReview] = useState(round?.review || {});
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  if (!round || !match) return null;
  const title = row
    ? row.teaching.title || `${row.player} · ${kindNames[row.kind] || row.kind}`
    : `第 ${round.number} 回合${round.is_pistol ? " · 手枪局" : ""}`;
  const samePurpose = row?.teaching.area
    ? catalog.throws.filter(
        (t) =>
          t.id !== row.id &&
          t.teaching.area === row.teaching.area &&
          t.kind === row.kind &&
          t.map === row.map,
      )
    : [];
  function saveNote() {
    try {
      localStorage.setItem(`or-note-${id}`, note);
      setNoteStatus("已保存到本机浏览器。");
    } catch {
      setNoteStatus("保存失败，请检查浏览器存储空间。");
    }
  }
  return (
    <dialog
      ref={ref}
      className="detail-dialog"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="detail-inner">
        <div className="detail-head">
          <div>
            <p className="eyebrow">
              {match.map.replace("de_", "").toUpperCase()} / ROUND{" "}
              {round.number}
            </p>
            <h2>{title}</h2>
            <p className="muted">
              {match.source.event} · {match.source.date} ·{" "}
              {row?.side || "T / CT"}
            </p>
          </div>
          <button
            className="icon-button"
            aria-label="关闭详情"
            onClick={onClose}
          >
            <X />
          </button>
        </div>
        <div className="tabs">
          <button
            className={tab === "learn" ? "active" : ""}
            onClick={() => setTab("learn")}
          >
            {row ? "学习详情" : "回合详情"}
          </button>
          <button
            className={tab === "round" ? "active" : ""}
            onClick={() => setTab("round")}
          >
            完整回合
          </button>
          {client.mode === "desktop" && row && (
            <button
              className={tab === "edit" ? "active" : ""}
              onClick={() => setTab("edit")}
            >
              整理教学
            </button>
          )}
          <button onClick={() => toggleFavorite(id)}>
            <Bookmark
              size={15}
              fill={favorites.includes(id) ? "currentColor" : "none"}
            />
            {favorites.includes(id) ? "已收藏" : "收藏"}
          </button>
        </div>
        {tab === "edit" && row ? (
          <TeachingEditor row={row} client={client} onSaved={onSaved} />
        ) : tab === "round" ? (
          <Timeline client={client} round={round} throwRow={row} />
        ) : (
          <>
            {row && (
              <>
                <div className={row.gaps.length ? "notice" : "notice success"}>
                  {row.gaps.length
                    ? `提取记录 · 教学待完善（尚缺 ${row.gaps.length} 项）`
                    : "完整教学 · 已记录游戏内复现核验"}
                </div>
                <section className="facts">
                  <h3>出手坐标与视角</h3>
                  <div className="fact-grid">
                    <div>
                      <span>投掷者</span>
                      <strong>
                        {row.player} / {row.team || "队伍未知"}
                      </strong>
                    </div>
                    <div>
                      <span>出手时间</span>
                      <strong>冻结结束后 {row.time.toFixed(3)} s</strong>
                    </div>
                    <div>
                      <span>世界坐标 X / Y / Z</span>
                      <code>
                        {row.position
                          .map((v) => v?.toFixed(3) ?? "未知")
                          .join(" / ")}
                      </code>
                    </div>
                    <div>
                      <span>视角 Pitch / Yaw</span>
                      <code>
                        {row.view.pitch?.toFixed(3) ?? "未知"} /{" "}
                        {row.view.yaw?.toFixed(3) ?? "未知"}
                      </code>
                    </div>
                  </div>
                  <p className="micro">
                    tick {row.tick} ·{" "}
                    {row.trajectory_status === "matched"
                      ? "已匹配道具飞行轨迹"
                      : "轨迹匹配不确定"}{" "}
                    · 生效位置{" "}
                    {row.effect_position
                      ?.map((v) => v?.toFixed(1) ?? "?")
                      .join(" / ") || "未解析到"}
                  </p>
                </section>
                <div className="lesson-grid">
                  {[
                    "prerequisites",
                    "stance",
                    "aim",
                    "operation",
                    "timing",
                    "effect",
                    "coordination",
                    "failures",
                    "counterplay",
                  ].map((key, i) => (
                    <section key={key}>
                      <span className="step-number">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <h3>{teachingLabels[key]}</h3>
                      <p>{row.teaching[key] || "待补充并验证"}</p>
                      {(key === "stance" || key === "aim") &&
                        mediaUrl(row.teaching[`${key}_image`], client.mode) && (
                          <img
                            alt={teachingLabels[key]}
                            src={mediaUrl(
                              row.teaching[`${key}_image`],
                              client.mode,
                            )}
                          />
                        )}
                    </section>
                  ))}
                </div>
                {samePurpose.length > 0 && (
                  <section>
                    <h3>同区域、同类型的其他投法</h3>
                    <p>
                      {samePurpose
                        .map(
                          (t) =>
                            `${t.player} · 第${t.round_number}回合 · ${t.teaching.title || "未命名投法"}`,
                        )
                        .join("；")}
                    </p>
                    <p className="micro">
                      由已整理的区域标签关联；相同落点不自动视为相同投法。
                    </p>
                  </section>
                )}
              </>
            )}
            <section>
              <h3>职业比赛原片</h3>
              <Video
                client={client}
                value={row?.teaching.pro_video || round.review.pro_video}
                offset={Number(row?.teaching.video_offset || 0)}
              />
            </section>
            {row?.teaching.recreation_video && (
              <section>
                <h3>教学复现（独立于比赛原片）</h3>
                <Video client={client} value={row.teaching.recreation_video} />
              </section>
            )}
            <RoundFacts round={round} catalog={catalog} />
            {client.mode === "desktop" && kind === "round" && (
              <section className="editor">
                <h3>审核回合教学</h3>
                <label>
                  职业原片地址
                  <input
                    aria-label="回合职业原片地址"
                    value={review.pro_video || ""}
                    onChange={(e) =>
                      setReview((v) => ({ ...v, pro_video: e.target.value }))
                    }
                  />
                </label>
                <label>
                  回合打法与观察
                  <textarea
                    value={review.description || ""}
                    onChange={(e) =>
                      setReview((v) => ({ ...v, description: e.target.value }))
                    }
                  />
                </label>
                <label>
                  核验人
                  <input
                    value={review.reviewer || ""}
                    onChange={(e) =>
                      setReview((v) => ({ ...v, reviewer: e.target.value }))
                    }
                  />
                </label>
                <button
                  className="button"
                  onClick={async () => {
                    try {
                      await client.write(`rounds/${round.id}/review`, "PUT", {
                        ...review,
                        approved: true,
                      });
                      setReviewMessage("回合已审核，可导出到网页版。");
                      onSaved();
                    } catch (e) {
                      setReviewMessage((e as Error).message);
                    }
                  }}
                >
                  审核并允许导出
                </button>
                {reviewMessage && <p role="alert">{reviewMessage}</p>}
              </section>
            )}
          </>
        )}
        <section className="source">
          <h3>比赛依据</h3>
          <p>
            {match.source.match} ·{" "}
            {match.source.verified ? "来源已核对" : "来源待核验"}
          </p>
          <a
            href={mediaUrl(match.source.url, client.mode)}
            target="_blank"
            rel="noreferrer"
          >
            查看比赛来源 <ExternalLink size={13} />
          </a>
          <p className="micro">
            游戏版本 {match.game_version || "unknown"} · 解析器{" "}
            {match.parser_version} · 文件 SHA-256 {match.sha256}
          </p>
        </section>
        <section className="notes">
          <h3>我的练习笔记</h3>
          <textarea
            aria-label="我的练习笔记"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="观察 / 自己的理解 / 下一次练习目标"
          />
          <button className="button secondary" onClick={saveNote}>
            保存笔记
          </button>
          {noteStatus && <span className="micro">{noteStatus}</span>}
        </section>
      </div>
    </dialog>
  );
}

function RoundFacts({ round, catalog }: { round: Round; catalog: Catalog }) {
  const throws = catalog.throws.filter((t) => t.round_id === round.id);
  return (
    <section>
      <div className="section-line">
        <h3>冻结结束装备</h3>
        <span className="micro">
          {round.is_pistol ? "正式手枪局" : "正式回合"} ·{" "}
          {round.winner || "结果未知"} 获胜
        </span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>选手 / 阵营</th>
              <th>装备</th>
              <th>护甲</th>
              <th>投掷</th>
            </tr>
          </thead>
          <tbody>
            {round.equipment.map((e) => (
              <tr key={e.player_id}>
                <td>
                  <span className={`side ${e.side}`}>{e.side}</span>
                  {e.player}
                  <small>{e.team}</small>
                </td>
                <td>{e.inventory?.join(" · ") || "未知"}</td>
                <td>{e.armor ?? "未知"}</td>
                <td>
                  {throws.filter((t) => t.player_id === e.player_id).length}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        首杀：
        {round.opening_kill
          ? `${round.opening_kill.attacker} → ${round.opening_kill.victim}`
          : "未记录"}{" "}
        · 下包：
        {round.bomb_events.find((e) => e.kind === "bomb_planted")?.player ||
          "无下包事件"}
      </p>
      <p className="micro">
        识别依据：{round.pistol_basis}
        {round.review_required ? " · 异常回合需要复核" : ""}
      </p>
      {round.review.description && <p>{round.review.description}</p>}
    </section>
  );
}
