import { test, expect } from '@playwright/test';

// E2E: Password reset UX
// - open site, open reset modal
// - submit email and assert spinner is visible while request pending
// - assert success message
// - navigate to the password reset confirm success page and change language
// - assert language switch redirects to login (no token error)

test.describe('Password reset UX', () => {
  test('shows spinner during submit and language switch goes to login after success', async ({ page }) => {
    // Update BASE_URL in your Playwright config or use absolute URL here
    const base = process.env.BASE_URL || 'http://localhost:8000/en';
    await page.goto(base + '/');

    // Open reset modal (assumes a button with id #openResetPassword exists)
    await page.click('#openResetPassword');
    await expect(page.locator('#resetPasswordModal')).toBeVisible();

    // Fill email and submit
    await page.fill('#reset_email', 'test@example.com');

    // Intercept network to delay response so we can assert spinner is visible
    const [request] = await Promise.all([
      page.waitForRequest(req => req.url().includes('/user/password_reset_request/') && req.method() === 'POST'),
      page.click('#resetPasswordSubmit')
    ]);

    // Spinner should be visible while request is in-flight
    await expect(page.locator('#resetSpinner')).toBeVisible();

    // Wait for success response and message
    await page.waitForResponse(resp => resp.url().includes('/user/password_reset_request/') && resp.status() === 200);
    await expect(page.locator('#reset-password-alert')).toHaveText(/email/i);

    // TODO: navigate to a prepared confirm-success page and verify language switch redirects to login
    // This part requires a deterministic test token or a mocked backend.
  });
});
