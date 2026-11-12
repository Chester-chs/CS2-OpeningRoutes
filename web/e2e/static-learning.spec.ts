import { test, expect } from "@playwright/test";

test("reviewed static package supports both sides, pistol practice and whole-round evidence", async ({ page }) => {
  test.skip(!process.env.OPENINGROUTES_STATIC_URL, "Set OPENINGROUTES_STATIC_URL to a reviewed export server");
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(process.env.OPENINGROUTES_STATIC_URL!);
  await expect(page.locator('[data-ready="true"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "数据与内容管理", exact: true })).toHaveCount(0);
  await page.getByRole("navigation", { name: "主要导航" }).getByRole("button", { name: "跟着选手学", exact: true }).click();
  await expect(page.getByTestId("learning-profile")).toBeVisible();
  await expect(page.getByRole("button", { name: "生成方案草稿", exact: true })).toHaveCount(0);
  await page.getByLabel("学习情境", { exact: true }).selectOption("pistol");
  await expect(page.getByTestId("learning-sample").first()).toContainText("手枪局");
  await page.getByRole("button", { name: "保存跟练清单", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("已保存");
  await page.getByRole("button", { name: "查看全员完整回合", exact: true }).click();
  await page.getByRole("button", { name: "完整回合", exact: true }).click();
  await expect(page.getByLabel("回合时间轴")).toBeVisible();
  await page.getByLabel("关闭详情").click();
  await page.getByLabel("学习阵营", { exact: true }).selectOption("T");
  await expect(page.getByTestId("learning-profile")).toContainText("T ·");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
