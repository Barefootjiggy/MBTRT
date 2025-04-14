from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Store global session driver to persist login across requests
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

def get_client_feedback_by_id(email, password, client_id, date):
    driver = init_driver(email, password)
    feedback_url = f"https://www.mydailyfeedback.com/index.php/feedbacks/tutor_edit/{date}/{client_id}"
    driver.get(feedback_url)
    time.sleep(3)

    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except Exception as e:
        print("Error retrieving client feedback:", e)
        return "[Error] Unable to fetch feedback."

def get_dashboard_sections(email, password):
    driver = init_driver(email, password)
    driver.get("https://www.mydailyfeedback.com/index.php/people/tutor_view")
    time.sleep(3)

    tutor_hub_activity = []
    weekend_reports = []
    waiting_for_response = []
    feedback_report = {
        "Missed 5+ Days": [],
        "Missed 4 Days": [],
        "Missed 3 Days": [],
        "Missed 2 Days": [],
        "Missed Yesterday": []
    }

    try:
        # Tutor Hub Activity (Top 3 only, text-only)
        try:
            activity_section = driver.find_element(By.XPATH, "//h6[contains(text(),'Tutor Hub Activity')]/following-sibling::ul[1]")
            items = activity_section.find_elements(By.TAG_NAME, "li")
            for item in items[:3]:
                tutor_hub_activity.append(item.text)
        except:
            print("Tutor Hub Activity section not found.")

        # Weekend Reports
        try:
            weekend_table = driver.find_element(By.XPATH, "//h6[contains(text(),'Weekend Reports')]/following-sibling::table[1]")
            rows = weekend_table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
            for row in rows:
                link = row.find_element(By.TAG_NAME, "a")
                name = link.text
                href = link.get_attribute("href")
                date = href.split("/")[-2]
                client_id = href.split("/")[-1]
                weekend_reports.append({"name": name, "date": date, "id": client_id})
        except:
            print("Weekend Reports section not found.")

        # Reports Waiting For A Response
        try:
            waiting_table = driver.find_element(By.XPATH, "//h6[contains(text(),'Reports Waiting For A Response')]/following-sibling::table[1]")
            rows = waiting_table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells or len(cells) < 3:
                    continue
                link = cells[0].find_element(By.TAG_NAME, "a")
                name = link.text
                href = link.get_attribute("href")
                date = cells[1].text
                client_id = href.split("/")[-1]
                date_path = href.split("/")[-2]
                waiting_for_response.append({
                    "name": name,
                    "date": date_path,
                    "submitted_when": cells[2].text,
                    "id": client_id
                })
        except:
            print("Reports Waiting For A Response section not found.")

        # Feedback Report (Missed Days)
        try:
            report_section = driver.find_element(By.XPATH, "//h5[contains(text(),'Feedback Report')]/..")
            for category in feedback_report.keys():
                try:
                    ul = report_section.find_element(By.XPATH, f".//strong[contains(text(),'{category}')]/following-sibling::ul[1]")
                    items = ul.find_elements(By.TAG_NAME, "li")
                    feedback_report[category] = [item.text for item in items]
                except:
                    continue
        except:
            print("Feedback Report section not found.")

    except Exception as e:
        print("Error parsing dashboard:", e)

    return {
        "tutor_hub_activity": tutor_hub_activity,
        "weekend_reports": weekend_reports,
        "waiting_for_response": waiting_for_response,
        "feedback_report": feedback_report
    }
