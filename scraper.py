from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

def get_feedback(email, password):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run Chrome in the background
    driver = webdriver.Chrome(options=options)

    driver.get("https://www.mydailyfeedback.com/index.php/users/login")
    time.sleep(3)

    # Log in
    email_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder='Email']")
    password_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder='Password']")
    email_input.send_keys(email)
    password_input.send_keys(password, Keys.RETURN)

    time.sleep(5)  # Allow time for the dashboard to load

    feedback_list = []

    try:
        # Locate the feedback table and rows
        table = driver.find_element(By.CLASS_NAME, "stack")
        rows = table.find_elements(By.TAG_NAME, "tr")

        # Loop through rows and follow links to detailed logs
        rows = table.find_elements(By.TAG_NAME, "tr")
        for i in range(len(rows)):
            try:
                row = table.find_elements(By.TAG_NAME, "tr")[i]  # re-fetch each time
                links = row.find_elements(By.TAG_NAME, "a")
                if not links:
                    continue
                href = links[0].get_attribute("href")

                # Navigate to report
                driver.get(href)
                time.sleep(3)

                full_text = driver.find_element(By.TAG_NAME, "body").text
                feedback_list.append(full_text)
            except Exception as e:
                print("Skipping row due to:", str(e))
                continue


    except Exception as outer_error:
        feedback_list = [f"Error scraping feedback table: {str(outer_error)}"]

    driver.quit()
    return feedback_list
