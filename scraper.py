from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

def get_feedback(email, password):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Optional: run in background
    driver = webdriver.Chrome(options=options)

    driver.get("https://www.mybodytutor.com/login")

    driver.find_element(By.NAME, "email").send_keys(email)
    driver.find_element(By.NAME, "password").send_keys(password, Keys.RETURN)

    time.sleep(5)  # Wait for dashboard to load

    feedback_elements = driver.find_elements(By.CLASS_NAME, "feedback-text")
    feedback_list = [fb.text.strip() for fb in feedback_elements]

    driver.quit()
    return feedback_list
