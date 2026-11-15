import { mapRows, recentMatches, teamRows } from "./home";
import type { Catalog } from "./types";

const mapName = (m: string) => m.replace(/^de_/, "");
const TEAM_LIMIT = 20;

export default function HomePage({
  catalog,
  openMap,
  navigate,
  openLearning,
}: {
  catalog: Catalog;
  openMap: (map: string) => void;
  navigate: (page: "utility" | "openings" | "pistol") => void;
  openLearning: () => void;
}) {
  const maps = mapRows(catalog);
  const teams = teamRows(catalog);
  const recent = recentMatches(catalog, 10);
  return (
    <div className="home" data-testid="home">
      <nav className="quick-links" aria-label="常用入口">
        <button className="text-button" onClick={() => navigate("utility")}>
          打开道具库
        </button>
        <button className="text-button" onClick={() => navigate("openings")}>
          查看开局策略
        </button>
        <button className="text-button" onClick={() => navigate("pistol")}>
          研究手枪局
        </button>
        <button className="text-button" onClick={openLearning}>
          按选手学区域
        </button>
      </nav>
      <div className="home-grid">
        <div>
          <section>
            <h2 id="home-maps">地图概览</h2>
            <div className="table-scroll">
              <table className="data-table" aria-labelledby="home-maps">
                <thead>
                  <tr>
                    <th scope="col">地图</th>
                    <th scope="col" className="num">
                      比赛
                    </th>
                    <th scope="col" className="num">
                      回合
                    </th>
                    <th scope="col" className="num">
                      投掷
                    </th>
                    <th scope="col" className="num">
                      完整教学
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {maps.map((m) => (
                    <tr key={m.map}>
                      <td>
                        <button
                          className="link-cell"
                          aria-label={`${mapName(m.map)}：在道具库中查看`}
                          title="在道具库中按这张地图筛选"
                          onClick={() => openMap(m.map)}
                        >
                          {mapName(m.map)}
                        </button>
                      </td>
                      <td className="num">{m.matches}</td>
                      <td className="num">{m.rounds}</td>
                      <td className="num">{m.throws}</td>
                      <td className="num">{m.complete}</td>
                    </tr>
                  ))}
                  {!maps.length && (
                    <tr>
                      <td colSpan={5} className="muted">
                        尚未导入比赛
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
          <section>
            <h2 id="home-recent">最近比赛</h2>
            <div className="table-scroll">
              <table className="data-table" aria-labelledby="home-recent">
                <thead>
                  <tr>
                    <th scope="col">日期</th>
                    <th scope="col">赛事</th>
                    <th scope="col">对阵</th>
                    <th scope="col">地图</th>
                    <th scope="col">来源</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((m) => (
                    <tr key={m.id}>
                      <td className="nowrap">{m.date || "—"}</td>
                      <td>{m.event}</td>
                      <td>{m.teams}</td>
                      <td>{mapName(m.map)}</td>
                      <td className={m.verified ? "nowrap" : "nowrap muted"}>
                        {m.verified ? "已核对" : "待核对"}
                      </td>
                    </tr>
                  ))}
                  {!recent.length && (
                    <tr>
                      <td colSpan={5} className="muted">
                        尚未导入比赛
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
        <section>
          <h2 id="home-teams">战队</h2>
          <div className="table-scroll">
            <table className="data-table" aria-labelledby="home-teams">
              <thead>
                <tr>
                  <th scope="col">战队</th>
                  <th scope="col" className="num">
                    比赛地图
                  </th>
                  <th scope="col" className="num">
                    最近日期
                  </th>
                </tr>
              </thead>
              <tbody>
                {teams.slice(0, TEAM_LIMIT).map((t) => (
                  <tr key={t.team}>
                    <td>{t.team}</td>
                    <td className="num">{t.matches}</td>
                    <td className="num">{t.latest || "—"}</td>
                  </tr>
                ))}
                {!teams.length && (
                  <tr>
                    <td colSpan={3} className="muted">
                      尚未导入比赛
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {teams.length > TEAM_LIMIT && (
            <p className="hint">
              按比赛地图数显示前 {TEAM_LIMIT} 支，共 {teams.length} 支。
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
