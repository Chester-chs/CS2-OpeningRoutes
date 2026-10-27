import { useEffect, useState } from "react";
import { Download, FileUp, RefreshCw, ShieldCheck } from "lucide-react";
import { DataClient } from "./data";
import type { Catalog, Job, Source } from "./types";

const stageNames: Record<string, string> = {
  queued: "等待解析",
  events: "提取回合与事件",
  routes: "提取全员路线",
  grenades: "匹配道具轨迹",
  validation: "校验与保存",
  complete: "提取完成",
};
const statusNames: Record<string, string> = {
  cancelled: "已取消",
  queued: "排队中",
  parsing: "解析中",
  complete: "已完成",
  failed: "失败",
  interrupted: "已中断",
};

export default function Manage({
  client,
  catalog,
  onRefresh,
}: {
  client: DataClient;
  catalog: Catalog;
  onRefresh: () => void;
}) {
  const [source, setSource] = useState<Source>({
    event: "",
    match: "",
    date: "",
    url: "",
    verified: false,
    reviewer: "",
  });
  const [file, setFile] = useState<File>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [download, setDownload] = useState("");
  const [exportSummary, setExportSummary] = useState("");
  useEffect(() => {
    let mounted = true;
    let prior = "";
    async function poll() {
      try {
        const response = await fetch("/api/jobs");
        if (!response.ok) return;
        const data: Job[] = await response.json();
        if (mounted) {
          setJobs(data);
          const done = data
            .filter((j) => j.status === "complete")
            .map((j) => j.id)
            .join(",");
          if (prior && prior !== done) onRefresh();
          prior = done;
        }
      } catch {
        /* Keep prior task status during a transient failure. */
      }
    }
    void poll();
    const interval = setInterval(() => void poll(), 2500);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [onRefresh]);
  async function importDemo() {
    if (!file) {
      setMessage("请先选择职业比赛 .dem 文件。");
      return;
    }
    setBusy(true);
    setMessage("正在将 Demo 导入本地…");
    try {
      const data = new FormData();
      data.append("demo", file);
      data.append("source", JSON.stringify(source));
      await client.write("import", "POST", data);
      setMessage("导入已排队，可继续浏览其他内容。");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function publish() {
    setBusy(true);
    setMessage("");
    try {
      const result = await client.write("export", "POST", {});
      setDownload(result.download);
      setExportSummary(
        `已导出 ${result.manifest.counts.throws} 份完整教学、${result.manifest.counts.rounds} 个回合。仅包含已审核内容。`,
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="manage-grid">
      <section className="panel">
        <div className="section-line">
          <h2>导入职业比赛 Demo</h2>
          <FileUp size={20} />
        </div>
        <p className="muted">
          提取全员正式回合、投掷、路线及手枪局，文件保存在本机。
        </p>
        <label className="file-zone">
          <FileUp size={28} />
          <strong>{file?.name || "选择 .dem 文件"}</strong>
          <span>CS2 SourceTV · 最大 2 GiB</span>
          <input
            aria-label="职业比赛 Demo 文件"
            type="file"
            accept=".dem"
            onChange={(e) => setFile(e.target.files?.[0])}
          />
        </label>
        <div className="form-grid">
          {(
            [
              ["event", "赛事名称"],
              ["match", "对阵 / 阶段"],
              ["date", "比赛日期"],
              ["url", "比赛来源链接"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                aria-label={label}
                required
                type={key === "date" ? "date" : key === "url" ? "url" : "text"}
                value={source[key]}
                onChange={(e) =>
                  setSource((v) => ({ ...v, [key]: e.target.value }))
                }
              />
            </label>
          ))}
        </div>
        <p className="micro">
          导入后可在下方核对比赛来源。未经核验的比赛不进入职业手枪局统计和网页导出。
        </p>
        <button
          className="button"
          disabled={busy}
          onClick={() => void importDemo()}
        >
          <FileUp size={16} />
          开始提取
        </button>
        {message && (
          <p role="alert" className="notice">
            {message}
          </p>
        )}
      </section>
      <section className="panel">
        <div className="section-line">
          <h2>提取任务</h2>
          <button
            className="icon-button"
            aria-label="刷新资料"
            onClick={onRefresh}
          >
            <RefreshCw size={17} />
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="muted">导入后在这里查看进度与结果。</p>
        ) : (
          jobs.map((job) => (
            <article className="job" key={job.id}>
              <strong>{job.source.match}</strong>
              <span className="tag">
                {statusNames[job.status] || job.status}
              </span>
              <p>{stageNames[job.stage] || job.stage}</p>
              {job.error && <p className="error">{job.error}</p>}
              {["queued", "parsing"].includes(job.status) && (
                <button
                  className="text-button"
                  onClick={async () => {
                    try {
                      await client.write(`jobs/${job.id}/cancel`, "POST", {});
                      setMessage("任务已取消，可重新选择文件导入。");
                    } catch (e) {
                      setMessage((e as Error).message);
                    }
                  }}
                >
                  取消提取
                </button>
              )}
            </article>
          ))
        )}
        <div className="export-box">
          <h3>导出到功能网页版</h3>
          <p className="muted">
            完整教学和已审核回合进入发布包；未完成的草稿继续留在桌面端。
          </p>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void publish()}
          >
            <Download size={16} />
            导出已审核内容
          </button>
          {exportSummary && <p role="status">{exportSummary}</p>}
          {download && (
            <a className="button" href={download} download>
              下载内容包 <Download size={15} />
            </a>
          )}
        </div>
      </section>
      <section className="panel wide">
        <h2>比赛来源核验</h2>
        {catalog.matches.length === 0 ? (
          <p className="muted">尚未导入比赛。</p>
        ) : (
          catalog.matches.map((match) => (
            <SourceReview
              key={match.id}
              initial={match.source}
              matchId={match.id}
              map={match.map}
              client={client}
              onRefresh={onRefresh}
            />
          ))
        )}
      </section>
    </div>
  );
}

function SourceReview({
  initial,
  matchId,
  map,
  client,
  onRefresh,
}: {
  initial: Source;
  matchId: string;
  map: string;
  client: DataClient;
  onRefresh: () => void;
}) {
  const [value, setValue] = useState(initial);
  const [message, setMessage] = useState("");
  return (
    <article className="source-review">
      <div className="section-line">
        <strong>
          {value.match} · {map.replace("de_", "")}
        </strong>
        <span className="tag">
          {initial.verified ? "来源已核对" : "来源待核验"}
        </span>
      </div>
      <a href={initial.url} target="_blank" rel="noreferrer">
        比赛来源
      </a>
      <label>
        核验记录
        <input
          aria-label={`核验记录 ${map}`}
          value={value.reviewer}
          onChange={(e) =>
            setValue((v) => ({ ...v, reviewer: e.target.value }))
          }
          placeholder="核对赛事、阵容、地图与回合结果"
        />
      </label>
      <label className="check-label">
        <input
          type="checkbox"
          checked={value.verified}
          onChange={(e) =>
            setValue((v) => ({ ...v, verified: e.target.checked }))
          }
        />
        已核对为职业赛事来源
      </label>
      <button
        className="button secondary"
        onClick={async () => {
          try {
            await client.write(`sources/${matchId}`, "PUT", value);
            setMessage("来源核验已保存。");
            onRefresh();
          } catch (e) {
            setMessage((e as Error).message);
          }
        }}
      >
        <ShieldCheck size={15} />
        保存核验
      </button>
      {message && <p role="status">{message}</p>}
    </article>
  );
}
