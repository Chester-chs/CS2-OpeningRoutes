import { test, expect } from "@playwright/test";

test("opening strategy shows T defaults, matchups, scouting and nades.ai links per map era", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/");
  await page.getByRole("button", { name: "开局策略", exact: true }).click();
  const section = page.getByTestId("openings");
  await expect(section).toBeVisible();
  const defaults = section.getByRole("table", {
    name: "T 方默认打法",
    exact: true,
  });
  await expect(defaults).toBeVisible();
  await expect(defaults.locator("tbody tr").first()).toBeVisible();
  // Small samples only show counts, never a win rate.
  await expect(section.getByText(/少于 10 回合或 3/)).toBeVisible();
  // nades.ai links go to fixed map-level pages only.
  const links = section.getByRole("link", { name: /nades\.ai 上的/ });
  expect(await links.count()).toBeGreaterThan(0);
  for (const href of await links.evaluateAll((a) =>
    a.map((x) => (x as HTMLAnchorElement).href),
  ))
    expect(href).toMatch(
      /^https:\/\/nades\.ai\/zh\/(mirage|ancient|dust2|inferno|nuke|anubis|train|overpass)\/(smokes|flashbangs|he-grenades|molotovs)$/,
    );
  await expect(
    section.getByRole("heading", { name: "对位：T 默认打法 × CT 阵型" }),
  ).toBeVisible();
  await expect(section.getByTestId("matchups")).toBeVisible();
  // Switching period and map keeps the page usable.
  const period = section.getByLabel("开局时期");
  const options = await period.locator("option").count();
  expect(options).toBeGreaterThan(0);
  if (options > 1) {
    await period.selectOption({ index: 1 });
    await expect(defaults).toBeVisible();
  }
  const map = section.getByLabel("开局地图");
  const maps = await map.locator("option").allTextContents();
  for (const name of maps) {
    await map.selectOption({ label: name });
    await expect(
      section.getByRole("table", { name: "T 方默认打法", exact: true }),
    ).toBeVisible();
  }
  // Scouting a team lists rounds that open the whole-round view.
  await map.selectOption({ index: 0 });
  const team = section.getByLabel("侦察战队");
  await expect(team).toBeVisible();
  const roundLink = section
    .getByRole("button", { name: /查看 .* 的第 \d+ 回合/ })
    .first();
  await expect(roundLink).toBeVisible();
  await roundLink.click();
  await expect(page.locator("dialog[open]")).toBeVisible();
  expect(errors).toEqual([]);
});
