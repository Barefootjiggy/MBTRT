from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

session_driver = None

def init_driver(email, password):
    global session_driver
    if session_driver:
        return session_driver

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    session_driver = webdriver.Chrome(options=options)

    session_driver.get("https://www.mydailyfeedback.com/index.php/users/login")
    time.sleep(2)

    email_input = session_driver.find_element(By.CSS_SELECTOR, "input[placeholder='Email']")
    password_input = session_driver.find_element(By.CSS_SELECTOR, "input[placeholder='Password']")
    email_input.send_keys(email)
    password_input.send_keys(password, Keys.RETURN)

    time.sleep(3)
    return session_driver

def get_feedback(email, password):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)

    driver.get("https://www.mydailyfeedback.com/index.php/users/login")
    time.sleep(3)

    email_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder='Email']")
    password_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder='Password']")
    email_input.send_keys(email)
    password_input.send_keys(password, Keys.RETURN)

    time.sleep(5)
    feedback_list = []

    try:
        table = driver.find_element(By.CLASS_NAME, "stack")
        rows = table.find_elements(By.TAG_NAME, "tr")
        for i in range(len(rows)):
            try:
                row = table.find_elements(By.TAG_NAME, "tr")[i]
                links = row.find_elements(By.TAG_NAME, "a")
                if not links:
                    continue
                href = links[0].get_attribute("href")
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

def get_clients(email, password):
    driver = init_driver(email, password)
    driver.get("https://www.mydailyfeedback.com/index.php/people/tutor_view")
    time.sleep(3)

    clients = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table.stack tbody tr")
        for row in rows:
            try:
                name = row.find_element(By.TAG_NAME, "a").text
                link = row.find_element(By.TAG_NAME, "a").get_attribute("href")
                client_id = link.split("/")[-1]
                clients.append({"name": name, "link": link, "id": client_id})
            except Exception as e:
                print("Skipping client due to:", str(e))
                continue
    except Exception as e:
        print("Error getting clients:", e)

    return clients

def get_client_feedback_by_id(email, password, client_id):
    driver = init_driver(email, password)

    client_link = f"https://www.mydailyfeedback.com/index.php/people/view/{client_id}"
    driver.get(client_link)
    time.sleep(3)

    try:
        full_text = driver.find_element(By.TAG_NAME, "body").text
        return full_text
    except Exception as e:
        print("Error retrieving client feedback:", e)
        return "[Error] Unable to fetch feedback."
