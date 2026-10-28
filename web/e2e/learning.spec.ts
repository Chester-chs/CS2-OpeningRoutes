import { test, expect } from "@playwright/test";

test("real catalog supports utility, whole-round context and independent pistol study", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /从比赛里\s*找到答案。/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "道具库", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "道具库", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator('[data-testid="throw-card"]').first(),
  ).toBeVisible();
  await page.getByLabel("搜索选手、区域或教学").fill("Magisk");
  await page.locator('[data-testid="throw-card"]').first().click();
  await expect(page.getByText("出手坐标与视角")).toBeVisible();
  await page.getByRole("button", { name: "完整回合", exact: true }).click();
  await expect(page.getByLabel("回合时间轴")).toBeVisible();
  await page.getByLabel("关闭详情").click();
  await page.getByRole("button", { name: "手枪局", exact: true }).click();
  await page.getByLabel("搜索选手、区域或教学").fill("");
  await expect(
    page.getByRole("heading", { name: "手枪局", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator('[data-testid="round-card"]').first(),
  ).toBeVisible();
  await page.locator('[data-testid="round-card"]').first().click();
  await expect(page.getByText("冻结结束装备")).toBeVisible();
});

test("teaching draft persists but missing evidence prevents publication", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "道具库", exact: true }).click();
  await page.locator('[data-testid="throw-card"]').first().click();
  await page.getByRole("button", { name: "整理教学", exact: true }).click();
  await expect(page.getByLabel("按键与投掷动作")).toBeVisible();
  await page.getByRole("button", { name: "发布完整教学", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("暂不能发布");
});

test("mobile navigation and filters remain accessible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "手枪局", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "手枪局", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("areas, lineup variants and curator queues are usable", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "道具库", exact: true }).click();
  await page.getByLabel("地图", { exact: true }).selectOption("de_mirage");
  await page.getByLabel("区域", { exact: true }).selectOption("A 包点");
  const cards = page.locator('[data-testid="throw-card"]');
  await expect(cards.first()).toContainText("A 包点");
  await cards.first().click();
  await expect(page.getByText("出手区域")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /同一投法的职业案例/ }),
  ).toBeVisible();
  await page.getByLabel("关闭详情").click();
  await page.getByRole("button", { name: "数据与内容管理" }).click();
  await expect(
    page.getByRole("heading", { name: "地图区域词表" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "异常回合复核" }),
  ).toBeVisible();
});

test("CT defence research shows patterns, method and round formation", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "CT 防守研究", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "CT 防守研究", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".pattern-card").first()).toBeVisible();
  await page.getByRole("tab", { name: "情境检验" }).click();
  await expect(page.getByRole("table", { name: "情境检验" })).toBeVisible();
  await page.getByRole("tab", { name: "方法与引用" }).click();
  await expect(page.getByText("10.1109/TG.2026.3745970")).toBeVisible();
  await page.getByRole("tab", { name: "防守阵型" }).click();
  await page.getByRole("button", { name: "代表回合" }).first().click();
  await expect(page.getByText(/CT 开局站位/)).toBeVisible();
});
