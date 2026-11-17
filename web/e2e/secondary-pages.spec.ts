import { test, expect, type Page } from "@playwright/test";
import type { Catalog, Plan } from "../src/types";

async function navigate(page: Page, name: string) {
  await page
    .getByRole("button", { name: new RegExp(`^${name}(?:\\s+\\d+)?$`) })
    .click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
}

async function fitsScreen(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
}

for (const width of [1440, 390]) {
  test(`plans can be filtered, inspected and edited at ${width}px`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    const slice = await (
      await request.get("/api/catalog/maps/de_mirage")
    ).json();
    const throwId = slice.throws[0].id;
    // Synthetic plans reference a real fixture throw; no library writes are made.
    const plans: Plan[] = [
      {
        id: "synthetic-ct-plan",
        title: "Synthetic A hold",
        area: "A",
        side: "CT",
        purpose: "Delay the entry",
        conditions: "Full buy",
        status: "draft",
        steps: [
          {
            throw_id: throwId,
            role: "Anchor",
            time: 8,
            followup: "Synthetic followup",
          },
        ],
        counter_ids: ["synthetic-t-plan"],
        counter_explanation: "Synthetic counter timing",
      },
      {
        id: "synthetic-t-plan",
        title: "Synthetic mid take",
        area: "Mid",
        side: "T",
        purpose: "Take mid",
        conditions: "Pistol round",
        status: "published",
        steps: [
          { throw_id: throwId, role: "Support", time: 10, followup: "Trade" },
        ],
        counter_ids: [],
        counter_explanation: "",
      },
    ];
    await page.route("**/api/catalog/summary", async (route) => {
      const response = await route.fetch();
      await route.fulfill({
        response,
        json: { ...(await response.json()), plans },
      });
    });
    await page.goto("/");
    await navigate(page, "控图与反制");
    const table = page.getByRole("table", { name: "控图与反制方案" });
    await expect(table.locator("tbody tr")).toHaveCount(2);
    await page.getByLabel("搜索方案").fill("  SYNTHETIC A  ");
    await expect(table.locator("tbody tr")).toHaveCount(1);
    await page.getByLabel("方案阵营").selectOption("T");
    await expect(page.getByText("没有符合筛选条件的方案。")).toBeVisible();
    await page.getByRole("button", { name: "清除方案筛选" }).click();
    await page.getByLabel("方案状态").selectOption("published");
    await expect(table.locator("tbody tr")).toHaveCount(1);
    await expect(table).toContainText("Synthetic mid take");
    await page.getByRole("button", { name: "清除方案筛选" }).click();
    const row = table.getByRole("row").filter({ hasText: "Synthetic A hold" });
    await row.getByRole("button", { name: "查看步骤" }).click();
    const detail = page.getByRole("region", { name: "方案详情" });
    await expect(detail).toContainText("Synthetic followup");
    await expect(detail).toContainText("Synthetic mid take");
    await detail.getByRole("button", { name: /8s · Anchor/ }).click();
    await expect(page.getByLabel("关闭详情")).toBeVisible();
    await page.getByLabel("关闭详情").click();
    await row.getByRole("button", { name: "编辑方案" }).click();
    await expect(
      page.getByRole("textbox", { name: "方案名称", exact: true }),
    ).toHaveValue("Synthetic A hold");
    await page.getByRole("button", { name: "取消编辑" }).click();
    await fitsScreen(page);
  });

  test(`source review stays searchable and editable at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 960 });
    await page.route("**/api/catalog/summary", async (route) => {
      const response = await route.fetch();
      const catalog: Catalog = await response.json();
      catalog.matches[0].source.verified = false;
      await route.fulfill({ response, json: catalog });
    });
    await page.goto("/");
    await navigate(page, "数据与内容管理");
    const table = page.getByRole("table", { name: "比赛来源核验" });
    await expect(table.locator("tbody tr")).toHaveCount(4);
    await page.getByLabel("来源核验状态").selectOption("pending");
    await expect(table.locator("tbody tr")).toHaveCount(1);
    await expect(table).toContainText("来源待核验");
    await table.getByRole("button", { name: "核验来源" }).click();
    await expect(page.getByLabel("核验记录 de_ancient")).toBeVisible();
    await expect(page.getByRole("button", { name: "保存核验" })).toBeVisible();
    await page.getByRole("button", { name: "收起核验" }).click();
    await expect(page.getByLabel("核验记录 de_ancient")).toHaveCount(0);
    await page.getByLabel("搜索比赛来源").fill("no-such-match");
    await expect(page.getByText("没有符合筛选条件的比赛。")).toBeVisible();
    await page.getByRole("button", { name: "清除来源筛选" }).click();
    await page.getByLabel("搜索比赛来源").fill("  MIRAGE  ");
    await expect(table.locator("tbody tr")).toHaveCount(2);
    await fitsScreen(page);
  });
}

test("a saved round is not reported as an empty collection", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    localStorage.setItem(
      "or-favorites",
      JSON.stringify(["bf4c2f24a8c2a347a82e-r1"]),
    );
  });
  await page.goto("/");
  await navigate(page, "我的收藏");
  await expect(page.getByTestId("round-card")).toHaveCount(1);
  await expect(page.getByText("这里还没有符合条件的内容")).toHaveCount(0);
  await page.getByTestId("round-card").click();
  await expect(page.getByLabel("关闭详情")).toBeVisible();
  await page.getByLabel("关闭详情").click();
  await fitsScreen(page);
});

test("practice summaries keep progress and notes when collapsed or reloaded", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    if (!localStorage.getItem("or-practice")) {
      localStorage.setItem(
        "or-practice",
        JSON.stringify(
          [1, 2].map((n) => ({
            id: "synthetic-practice-" + n,
            profile_id: "synthetic-profile",
            title: "Synthetic practice " + n,
            map: "de_ancient",
            round_id: "bf4c2f24a8c2a347a82e-r1",
            steps: ["Check route", "Check timing"],
            checked: [],
            note: "",
          })),
        ),
      );
    }
  });
  await page.goto("/");
  await navigate(page, "我的收藏");
  const cards = page.getByTestId("practice-card");
  await expect(cards.first().getByRole("checkbox").first()).toBeVisible();
  await expect(cards.nth(1).getByRole("checkbox").first()).toBeHidden();
  await cards.nth(1).locator("summary").click();
  await cards.nth(1).getByRole("checkbox").first().check();
  await cards.nth(1).getByLabel("跟练笔记").fill("Synthetic saved note");
  await expect(cards.nth(1).locator("summary")).toContainText("1/2");
  await page.reload();
  await navigate(page, "我的收藏");
  await expect(cards.nth(1).locator("summary")).toContainText("1/2");
  await cards.nth(1).locator("summary").click();
  await expect(cards.nth(1).getByRole("checkbox").first()).toBeChecked();
  await expect(cards.nth(1).getByLabel("跟练笔记")).toHaveValue(
    "Synthetic saved note",
  );
  await fitsScreen(page);
});

test("vocabulary loads an unvisited map instead of asking to reimport its demo", async ({
  page,
}) => {
  let mirageLoaded = false;
  page.on("response", (response) => {
    if (response.url().endsWith("/api/catalog/maps/de_mirage") && response.ok())
      mirageLoaded = true;
  });
  await page.goto("/");
  await navigate(page, "数据与内容管理");
  await page.getByLabel("选择词表地图").selectOption("de_mirage");
  await expect.poll(() => mirageLoaded).toBe(true);
  await expect(page.locator(".place-table input").first()).toBeVisible();
  await expect(page.getByText(/这张地图的投掷还没有区域信息/)).toHaveCount(0);
});
