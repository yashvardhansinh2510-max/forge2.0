import { expect, test } from "@playwright/test";

type Profile = {
  name: string;
  email: string | undefined;
  password: string | undefined;
  landingPath: string;
  allowed: string;
  denied: string;
};

const profiles: Profile[] = [
  { name: "Ground tiles quotations/follow-ups", email: process.env.E2E_GROUND_TILES_EMAIL, password: process.env.E2E_GROUND_TILES_PASSWORD, landingPath: "/tiles", allowed: "Tiles", denied: "Payments" },
  { name: "Ground payments/dispatches", email: process.env.E2E_GROUND_PAYMENTS_EMAIL, password: process.env.E2E_GROUND_PAYMENTS_PASSWORD, landingPath: "/payments", allowed: "Payments", denied: "Follow-ups" },
  { name: "Sanitary quotations/follow-ups", email: process.env.E2E_SANITARY_QUOTES_EMAIL, password: process.env.E2E_SANITARY_QUOTES_PASSWORD, landingPath: "/quotations", allowed: "Quotations", denied: "Purchases" },
  { name: "Sanitary purchases", email: process.env.E2E_SANITARY_PURCHASES_EMAIL, password: process.env.E2E_SANITARY_PURCHASES_PASSWORD, landingPath: "/purchases", allowed: "Purchases", denied: "Payments" },
];

async function signIn(page: import("@playwright/test").Page, profile: Profile) {
  await page.goto("/login");
  await page.getByTestId("login-email").fill(profile.email!);
  await page.getByTestId("login-password").fill(profile.password!);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(new RegExp(profile.landingPath.replace("/", "\\/")));
}

for (const profile of profiles) {
  test(`${profile.name}: assigned workspace and denied modules`, async ({ page }) => {
    test.skip(!process.env.E2E_BASE_URL || !profile.email || !profile.password, "Requires a disposable account and E2E_BASE_URL.");
    await signIn(page, profile);
    await expect(page.getByText(profile.allowed, { exact: true }).first()).toBeVisible();
    await expect(page.getByText(profile.denied, { exact: true })).toHaveCount(0);
  });
}

test("Ground tiles profile: delivery lookup is customer-specific and read-only", async ({ page }) => {
  test.skip(!process.env.E2E_BASE_URL || !process.env.E2E_GROUND_TILES_EMAIL || !process.env.E2E_GROUND_TILES_PASSWORD || !process.env.E2E_DELIVERY_CUSTOMER, "Requires disposable Ground Tiles credentials and a fixture customer.");
  await signIn(page, profiles[0]);
  await page.getByPlaceholder(/search customers/i).fill(process.env.E2E_DELIVERY_CUSTOMER!);
  await page.getByText(process.env.E2E_DELIVERY_CUSTOMER!, { exact: true }).first().click();
  await expect(page.getByText(/Pending|Ready|Partially Dispatched|Dispatched|Delivered/).first()).toBeVisible();
  await expect(page.getByText(/Create dispatch|Mark ready|Dispatch order/i)).toHaveCount(0);
});

test("temporary-password staff must change password before reaching the workspace", async ({ page }) => {
  const email = process.env.E2E_TEMP_STAFF_EMAIL;
  const temporaryPassword = process.env.E2E_TEMP_STAFF_PASSWORD;
  const newPassword = process.env.E2E_TEMP_STAFF_NEW_PASSWORD;
  test.skip(!process.env.E2E_BASE_URL || !email || !temporaryPassword || !newPassword, "Requires a disposable forced-password-change account.");
  await page.goto("/login");
  await page.getByTestId("login-email").fill(email!);
  await page.getByTestId("login-password").fill(temporaryPassword!);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("force-change-new")).toBeVisible();
  await page.getByTestId("force-change-current").fill(temporaryPassword!);
  await page.getByTestId("force-change-new").fill(newPassword!);
  await page.getByTestId("force-change-confirm").fill(newPassword!);
  await page.getByTestId("force-change-submit").click();
  await expect(page).not.toHaveURL(/set-new-password/);
});

test("logout/login does not retain the preceding account floor", async ({ page }) => {
  const first = profiles[0];
  const second = profiles[3];
  test.skip(!process.env.E2E_BASE_URL || !first.email || !first.password || !second.email || !second.password, "Requires two disposable accounts on distinct floors.");
  await signIn(page, first);
  await page.getByLabel(/sign out|logout/i).click();
  await signIn(page, second);
  await expect(page).toHaveURL(/purchases/);
  await expect(page.getByText(/Ground Floor/i)).toHaveCount(0);
});
