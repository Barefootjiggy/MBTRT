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
        # Find the Reports Waiting For A Response section first
        section = driver.find_element(By.XPATH, "//h2[contains(text(), 'Reports Waiting For A Response')]/following-sibling::table[1]")
        rows = section.find_elements(By.TAG_NAME, "tr")

        for row in rows:
            try:
                link_element = row.find_element(By.TAG_NAME, "a")
                name = link_element.text
                link = link_element.get_attribute("href")
                client_id = link.split("/")[-1]
                clients.append({"name": name, "link": link, "id": client_id})
            except Exception as e:
                print("Skipping row:", e)
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

        # Parse the text into sections
        parts = {
            "Part 1: How I Ate": full_text.split("PART 2")[0] if "PART 2" in full_text else full_text,
            "Part 2: My Movement": full_text.split("PART 2")[-1].split("PART 3")[0] if "PART 3" in full_text else "",
            "Part 3: How I Feel": full_text.split("PART 3")[-1].split("PART 4")[0] if "PART 4" in full_text else "",
            "Part 4: The New Me": full_text.split("PART 4")[-1] if "PART 4" in full_text else ""
        }

        return parts

    except Exception as e:
        print("Error retrieving client feedback:", e)
        return {
            "Part 1: How I Ate": "[Error]",
            "Part 2: My Movement": "",
            "Part 3: How I Feel": "",
            "Part 4: The New Me": ""
        }

