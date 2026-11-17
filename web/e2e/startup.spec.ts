import { test, expect } from "@playwright/test";

for (const mode of ["desktop", "static"] as const) {
  test(`${mode} navigation waits for initialization before loading player profiles`, async ({
    page,
  }) => {
    test.skip(
      mode === "static" && !process.env.OPENINGROUTES_STATIC_URL,
      "Set OPENINGROUTES_STATIC_URL to a reviewed export server",
    );
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(
      mode === "desktop" ? "**/api/session" : "**/content/manifest.json",
      async (route) => {
        await pending;
        await route.continue();
      },
    );
    try {
      await page.goto(
        mode === "desktop" ? "/" : process.env.OPENINGROUTES_STATIC_URL!,
      );
      await expect(
        page.getByText("正在读取学习资料…", { exact: true }),
      ).toBeVisible();
      await page
        .getByRole("navigation", { name: "主要导航" })
        .getByRole("button", { name: "跟着选手学", exact: true })
        .click();
      await expect(page.locator("[data-ready]")).toHaveAttribute(
        "data-ready",
        "false",
      );
      release();
      await expect(page.locator('[data-ready="true"]')).toBeVisible();
      await expect(page.getByTestId("learning-profile")).toBeVisible();
      await expect(page.getByText(/此内容包尚未包含选手区域档案/)).toHaveCount(
        0,
      );
    } finally {
      release();
    }
  });
}
