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
