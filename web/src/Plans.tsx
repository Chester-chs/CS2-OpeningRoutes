import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { DataClient, kindNames } from "./data";
import type { Catalog, Plan } from "./types";

export default function Plans({
  client,
  catalog,
  onRefresh,
  openThrow,
}: {
  client: DataClient;
  catalog: Catalog;
  onRefresh: () => void;
  openThrow: (id: string) => void;
}) {
  const [editing, setEditing] = useState<Plan | null>(null);
  const [message, setMessage] = useState("");
  const empty = (): Plan => ({
    id: crypto.randomUUID(),
    title: "",
    area: "",
    side: "CT",
    purpose: "",
    conditions: "",
    steps: [],
    counter_ids: [],
    counter_explanation: "",
    status: "draft",
  });
  return (
    <>
      <div className="section-line">
        <p className="muted">将真实投掷整理成抢占、延缓、反清与反制方案。</p>
        {client.mode === "desktop" && (
          <button
            className="button secondary"
            onClick={() => {
              setEditing(empty());
              setMessage("");
            }}
          >
            <Plus size={15} />
            整理配合方案
          </button>
        )}
      </div>
      {catalog.plans.length === 0 && !editing && (
        <div className="empty">
          <h3>先从真实投掷建立一套方案</h3>
          <p>投掷顺序、角色、条件和反制需要结合比赛逐项整理。</p>
        </div>
      )}
      {catalog.plans.map((p) => (
        <article className="panel plan" key={p.id}>
          <div className="section-line">
            <h2>{p.title}</h2>
            <span className={`side ${p.side}`}>{p.side}</span>
          </div>
          <p>
            {p.area} · {p.purpose}
          </p>
          <p className="muted">条件：{p.conditions}</p>
          <ol>
            {p.steps.map((s, i) => {
              const t = catalog.throws.find((t) => t.id === s.throw_id);
              return (
                <li key={i}>
                  <button
                    className="text-button"
                    onClick={() => openThrow(s.throw_id)}
                  >
                    {s.time}s · {s.role} · {t?.player}{" "}
                    {t ? kindNames[t.kind] : ""}
                  </button>
                  <p>{s.followup}</p>
                </li>
              );
            })}
          </ol>
          {p.counter_ids.length > 0 && (
            <p>
              关联反制：
              {p.counter_ids
                .map(
                  (id) =>
                    catalog.plans.find((v) => v.id === id)?.title ||
                    "关联方案未公开",
                )
                .join("、")}
            </p>
          )}
          {p.counter_explanation && (
            <p>反制条件与解释：{p.counter_explanation}</p>
          )}
          {client.mode === "desktop" && (
            <button
              className="button secondary"
              onClick={() => {
                setEditing(structuredClone(p));
                setMessage("");
              }}
            >
              编辑方案
            </button>
          )}
        </article>
      ))}
      {editing && (
        <section className="panel editor">
          <h2>整理配合与反制</h2>
          <div className="form-grid">
            {(["title", "area", "purpose", "conditions"] as const).map(
              (key) => (
                <label key={key}>
                  {
                    {
                      title: "方案名称",
                      area: "地图区域",
                      purpose: "目的",
                      conditions: "装备、人数与出生位条件",
                    }[key]
                  }
                  <textarea
                    value={editing[key]}
                    onChange={(e) =>
                      setEditing((v) =>
                        v ? { ...v, [key]: e.target.value } : null,
                      )
                    }
                  />
                </label>
              ),
            )}
            <label>
              阵营
              <select
                value={editing.side}
                onChange={(e) =>
                  setEditing((v) =>
                    v ? { ...v, side: e.target.value as "T" | "CT" } : null,
                  )
                }
              >
                <option>CT</option>
                <option>T</option>
              </select>
            </label>
          </div>
          {editing.steps.map((step, index) => (
            <div className="plan-step" key={index}>
              <label>
                第 {index + 1} 步 · 真实投掷
                <select
                  value={step.throw_id}
                  onChange={(e) =>
                    setEditing((v) =>
                      v
                        ? {
                            ...v,
                            steps: v.steps.map((s, i) =>
                              i === index
                                ? { ...s, throw_id: e.target.value }
                                : s,
                            ),
                          }
                        : null,
                    )
                  }
                >
                  <option value="">选择比赛中的投掷</option>
                  {catalog.throws.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.map} R{t.round_number} {t.player} {kindNames[t.kind]}{" "}
                      {t.time}s
                    </option>
                  ))}
                </select>
              </label>
              <label>
                角色
                <input
                  value={step.role}
                  onChange={(e) =>
                    setEditing((v) =>
                      v
                        ? {
                            ...v,
                            steps: v.steps.map((s, i) =>
                              i === index ? { ...s, role: e.target.value } : s,
                            ),
                          }
                        : null,
                    )
                  }
                />
              </label>
              <label>
                相对方案起点（秒）
                <input
                  type="number"
                  value={step.time}
                  onChange={(e) =>
                    setEditing((v) =>
                      v
                        ? {
                            ...v,
                            steps: v.steps.map((s, i) =>
                              i === index
                                ? { ...s, time: Number(e.target.value) }
                                : s,
                            ),
                          }
                        : null,
                    )
                  }
                />
              </label>
              <label>
                后续行动
                <textarea
                  value={step.followup}
                  onChange={(e) =>
                    setEditing((v) =>
                      v
                        ? {
                            ...v,
                            steps: v.steps.map((s, i) =>
                              i === index
                                ? { ...s, followup: e.target.value }
                                : s,
                            ),
                          }
                        : null,
                    )
                  }
                />
              </label>
              <button
                className="icon-button"
                aria-label={`删除第${index + 1}步`}
                onClick={() =>
                  setEditing((v) =>
                    v
                      ? { ...v, steps: v.steps.filter((_, i) => i !== index) }
                      : null,
                  )
                }
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          <button
            className="button secondary"
            onClick={() =>
              setEditing((v) =>
                v
                  ? {
                      ...v,
                      steps: [
                        ...v.steps,
                        { throw_id: "", role: "", time: 0, followup: "" },
                      ],
                    }
                  : null,
              )
            }
          >
            <Plus size={15} />
            添加投掷步骤
          </button>
          <label>
            对应反制方案
            <select
              multiple
              value={editing.counter_ids}
              onChange={(e) =>
                setEditing((v) =>
                  v
                    ? {
                        ...v,
                        counter_ids: Array.from(e.target.selectedOptions).map(
                          (o) => o.value,
                        ),
                      }
                    : null,
                )
              }
            >
              {catalog.plans
                .filter((p) => p.id !== editing.id)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
            </select>
          </label>
          <label>
            反制的触发条件与比赛依据
            <textarea
              value={editing.counter_explanation}
              onChange={(e) =>
                setEditing((v) =>
                  v ? { ...v, counter_explanation: e.target.value } : null,
                )
              }
            />
          </label>
          <div className="actions">
            {["draft", "published"].map((status) => (
              <button
                key={status}
                className={status === "draft" ? "button secondary" : "button"}
                onClick={async () => {
                  try {
                    await client.write(`plans/${editing.id}`, "PUT", {
                      ...editing,
                      status,
                    });
                    setMessage(
                      status === "published"
                        ? "方案已发布。"
                        : "方案草稿已保存。",
                    );
                    onRefresh();
                    if (status === "draft") setEditing(null);
                  } catch (e) {
                    setMessage((e as Error).message);
                  }
                }}
              >
                {status === "draft" ? "保存方案草稿" : "发布已验证方案"}
              </button>
            ))}
            <button className="text-button" onClick={() => setEditing(null)}>
              取消编辑
            </button>
          </div>
        </section>
      )}
      {message && (
        <p role="alert" className="notice">
          {message}
        </p>
      )}
    </>
  );
}
