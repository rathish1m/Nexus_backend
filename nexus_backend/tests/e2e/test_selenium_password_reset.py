import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from django.contrib.staticfiles.testing import StaticLiveServerTestCase


@pytest.mark.e2e
class PasswordResetSeleniumTest(StaticLiveServerTestCase):
    """Simple Selenium smoke test for password-reset modal.

    Notes:
    - Requires selenium and a compatible chromedriver installed locally.
    - Intended for the dedicated e2e test suite, not for default CI runs.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.implicitly_wait(5)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        super().tearDownClass()

    def test_reset_modal_shows_spinner_and_success(self):
        self.driver.get(self.live_server_url + "/en/")
        # Assumes there is a control to open the reset modal
        open_btn = self.driver.find_element(By.ID, "openResetPassword")
        open_btn.click()
        time.sleep(0.5)
        email_input = self.driver.find_element(By.ID, "reset_email")
        email_input.send_keys("test_reset@example.com")
        submit = self.driver.find_element(By.ID, "resetPasswordSubmit")
        submit.click()
        # Spinner should appear
        spinner = self.driver.find_element(By.ID, "resetSpinner")
        assert spinner.is_displayed()
        # Wait for the alert to show up
        time.sleep(1)
        alert = self.driver.find_element(By.ID, "reset-password-alert")
        assert "envoy" in alert.text.lower() or "email" in alert.text.lower()
